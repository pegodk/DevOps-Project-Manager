"""
Hierarchy service for querying and analyzing Azure DevOps project structures.

Fetches Epics, Features, User Stories, and Tasks from Azure DevOps,
builds a nested tree, computes summary statistics, and formats output.
This is the single source of truth for project hierarchy logic, used by
both the MCP server and the CLI scripts.
"""

from __future__ import annotations

import re
from collections import defaultdict

from .devops_client import DevOpsClient


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WORK_ITEM_TYPES = ["Epic", "Feature", "User Story", "Task"]

FIELDS = [
    "System.Id",
    "System.Title",
    "System.WorkItemType",
    "System.State",
    "System.Description",
    "System.Parent",
    "System.IterationPath",
    "Microsoft.VSTS.Common.AcceptanceCriteria",
    "Microsoft.VSTS.Scheduling.StoryPoints",
    "Microsoft.VSTS.Scheduling.Effort",
]


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_hierarchy(client: DevOpsClient, epic_title: str | None = None) -> dict[int, dict]:
    """
    Fetch all Epics, Features, User Stories, and Tasks from the project.

    Args:
        client: A configured DevOpsClient instance.
        epic_title: Optional epic title to filter the hierarchy.

    Returns:
        Dict keyed by work item ID, each value a normalised item dict.
    """
    type_filter = " OR ".join(
        f"[System.WorkItemType] = '{t}'" for t in WORK_ITEM_TYPES
    )
    query = f"SELECT [System.Id] FROM WorkItems WHERE ({type_filter})"
    ids = client.run_wiql(query)
    if not ids:
        return {}

    raw_items = client.get_work_items_batch(ids, FIELDS)
    items: dict[int, dict] = {}
    for raw in raw_items:
        f = raw.get("fields", {})
        items[raw["id"]] = {
            "id": raw["id"],
            "type": f.get("System.WorkItemType", ""),
            "title": f.get("System.Title", ""),
            "state": f.get("System.State", ""),
            "description": f.get("System.Description", ""),
            "parent_id": f.get("System.Parent"),
            "iteration_path": f.get("System.IterationPath", ""),
            "acceptance_criteria": f.get("Microsoft.VSTS.Common.AcceptanceCriteria", ""),
            "story_points": f.get("Microsoft.VSTS.Scheduling.StoryPoints"),
            "estimate": f.get("Microsoft.VSTS.Scheduling.Effort"),
        }

    if epic_title:
        epic_ids = {
            iid
            for iid, item in items.items()
            if item["type"] == "Epic" and item["title"] == epic_title
        }
        if not epic_ids:
            return {}
        items = prune_to_subtree(items, epic_ids)

    return items


# ---------------------------------------------------------------------------
# Tree operations
# ---------------------------------------------------------------------------

def prune_to_subtree(items: dict, root_ids: set) -> dict:
    """Keep only items that are descendants of *root_ids* (or the roots themselves)."""
    children_map: dict[int, set] = defaultdict(set)
    for iid, item in items.items():
        pid = item["parent_id"]
        if pid and pid in items:
            children_map[pid].add(iid)

    keep: set[int] = set()
    queue = list(root_ids)
    while queue:
        current = queue.pop(0)
        if current in keep:
            continue
        keep.add(current)
        queue.extend(children_map.get(current, []))

    return {iid: item for iid, item in items.items() if iid in keep}


def build_tree(items: dict) -> list[dict]:
    """Build a nested tree structure from a flat items dict."""
    children_map: dict[int, list] = defaultdict(list)
    roots: list[dict] = []
    type_order = {t: i for i, t in enumerate(WORK_ITEM_TYPES)}

    for iid, item in items.items():
        pid = item["parent_id"]
        if pid and pid in items:
            children_map[pid].append(item)
        else:
            roots.append(item)

    def sort_key(item):
        return (type_order.get(item["type"], 99), item["title"])

    def build_node(item):
        node = dict(item)
        kids = sorted(children_map.get(item["id"], []), key=sort_key)
        if kids:
            node["children"] = [build_node(k) for k in kids]
        return node

    roots.sort(key=sort_key)
    return [build_node(r) for r in roots]


# ---------------------------------------------------------------------------
# Summary / statistics
# ---------------------------------------------------------------------------

def compute_summary(items: dict) -> dict:
    """Compute count and story-point summary statistics."""
    counts: dict[str, int] = defaultdict(int)
    state_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    total_sp = 0
    total_estimate = 0

    for item in items.values():
        wtype = item["type"]
        counts[wtype] += 1
        state_counts[wtype][item["state"]] += 1
        if item.get("story_points"):
            total_sp += item["story_points"]
        if item.get("estimate"):
            total_estimate += item["estimate"]

    return {
        "total_items": len(items),
        "counts": dict(counts),
        "states": {k: dict(v) for k, v in state_counts.items()},
        "total_story_points": total_sp,
        "total_estimate_hours": total_estimate,
    }


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def format_tree_text(tree: list[dict], indent: int = 0) -> list[str]:
    """Format a tree as a readable text hierarchy with connectors."""
    lines: list[str] = []
    for i, node in enumerate(tree):
        is_last = i == len(tree) - 1
        prefix = "  " * indent
        connector = ("└── " if is_last else "├── ") if indent else ""

        label = f"{node['type']}: {node['title']}"
        extras = []
        if node.get("state"):
            extras.append(node["state"])
        if node.get("story_points"):
            extras.append(f"SP:{node['story_points']}")
        if node.get("estimate"):
            extras.append(f"Est:{node['estimate']}h")
        if node.get("iteration_path"):
            extras.append(f"Iteration:{node['iteration_path']}")
        if extras:
            label += f"  ({', '.join(extras)})"
        lines.append(f"{prefix}{connector}{label}")

        children = node.get("children", [])
        if children:
            lines.extend(format_tree_text(children, indent + 1))
    return lines


def tree_to_yaml_structure(tree: list[dict]) -> dict:
    """Convert a tree to a YAML-compatible dict matching the project-designer template format.

    Every work-item level carries **only** the fields appropriate for its
    type, following the Pydantic models in ``models.py``:

    * **Epic / Feature** — ``title``, ``description``, ``id``, ``state``,
      ``iteration_path`` (never ``story_points`` or ``estimate``).
    * **User Story** — adds ``story_points`` and ``acceptance_criteria``
      (never ``estimate``).
    * **Task** — adds ``estimate`` (never ``story_points`` or
      ``acceptance_criteria``).

    Fields that are empty / ``None`` are omitted so the YAML stays clean.
    """

    # Mapping: work-item type → (child collection key, expected child type)
    _CHILDREN_CONFIG: dict[str, tuple[str, str]] = {
        "Epic": ("features", "Feature"),
        "Feature": ("stories", "User Story"),
        "User Story": ("tasks", "Task"),
    }

    def _build_item(node: dict) -> dict:
        """Build a single YAML item dict from a tree node, recursing into children."""
        item: dict = {"title": node["title"]}

        # Optional scalar fields — only include when non-empty
        if node.get("id"):
            item["id"] = node["id"]
        if node.get("state"):
            item["state"] = node["state"]

        desc = clean_html(node.get("description", ""))
        if desc:
            item["description"] = desc

        # Type-specific fields
        wi_type = node.get("type", "")
        if wi_type == "User Story":
            ac = clean_html(node.get("acceptance_criteria", ""))
            if ac:
                item["acceptance_criteria"] = ac
            if node.get("story_points") is not None:
                item["story_points"] = node["story_points"]
        elif wi_type == "Task":
            if node.get("estimate") is not None:
                item["estimate"] = node["estimate"]

        if node.get("iteration_path"):
            item["iteration_path"] = node["iteration_path"]

        # Recursively build children if this type has a child collection
        config = _CHILDREN_CONFIG.get(wi_type)
        if config:
            child_key, child_type = config
            kids = [
                _build_item(c)
                for c in node.get("children", [])
                if c["type"] == child_type
            ]
            if kids:
                item[child_key] = kids

        return item

    epics = [_build_item(n) for n in tree if n["type"] == "Epic"]
    return {"epics": epics}


def clean_html(text: str) -> str:
    """Strip basic HTML tags from Azure DevOps rich text fields."""
    if not text:
        return ""
    text = re.sub(r"<div>", "\n", text)
    text = re.sub(r"</div>", "", text)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()
