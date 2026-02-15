"""
MCP Server for Azure DevOps Project Management.

Exposes work-item CRUD, project querying, and template upload as MCP tools
so that any MCP-compatible client (VS Code Copilot, Claude Desktop, etc.)
can manage an Azure DevOps backlog conversationally.

Usage:
    # stdio transport (default – for VS Code / Claude Desktop)
    python -m src.mcp_server

    # SSE transport (for browser / remote clients)
    python -m src.mcp_server --transport sse --port 8000

Environment variables (or .env file):
    AZURE_DEVOPS_ORG_NAME
    AZURE_DEVOPS_PROJECT_NAME
    AZURE_DEVOPS_PERSONAL_ACCESS_TOKEN
    AZURE_DEVOPS_API_VERSION  (default: 7.1)
"""

from __future__ import annotations

import json
import os
from typing import Optional

# Project root directory (parent of src/)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUTPUT_DIR = os.path.join(_PROJECT_ROOT, "data")

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Local imports — reuse existing project code
# ---------------------------------------------------------------------------
from .devops_client import DevOpsClient
from .hierarchy_service import (
    fetch_hierarchy,
    build_tree,
    compute_summary,
    format_tree_text,
    tree_to_yaml_structure,
)
from .template_service import (
    load_template,
    expand_all_features,
    validate_template,
    lint_yaml,
    count_work_items,
    apply_instance_overrides,
    exclude_features,
    save_yaml,
    slugify,
)
from .upload_service import upload_from_yaml
from .models import build_work_item_data

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv()

ORG = os.getenv("AZURE_DEVOPS_ORG_NAME", "")
PROJECT = os.getenv("AZURE_DEVOPS_PROJECT_NAME", "")
PAT = os.getenv("AZURE_DEVOPS_PERSONAL_ACCESS_TOKEN", "")
API_VERSION = os.getenv("AZURE_DEVOPS_API_VERSION", "7.1")

mcp = FastMCP(
    "Azure DevOps Project Manager",
    dependencies=["requests", "python-dotenv", "pyyaml"],
)

# Singleton client
_client: DevOpsClient | None = None


def _get_client() -> DevOpsClient:
    """Return a shared DevOpsClient configured from env vars."""
    global _client
    if _client is None:
        _client = DevOpsClient(ORG, PROJECT, PAT)
    return _client



# ═══════════════════════════════════════════════════════════════════════════
# MCP TOOLS
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool()
def validate_connection() -> str:
    """Test the Azure DevOps connection and return status."""
    client = _get_client()
    ok, message = client.validate_connection()
    return json.dumps({"connected": ok, "message": message})


@mcp.tool()
def get_project_status(
    epic_title: Optional[str] = None,
    include_summary: bool = True,
) -> str:
    """
    Retrieve the full work-item hierarchy (Epics → Features → Stories → Tasks)
    from the Azure DevOps project and return a readable tree plus summary stats.

    Also saves one YAML file per epic to data/<epic-slug>.yaml containing
    the full child hierarchy (features, stories, tasks) for that epic.

    Args:
        epic_title: Optional epic title to filter the hierarchy to a single epic.
        include_summary: Whether to include count / story-point summary (default True).
    """
    client = _get_client()
    items = fetch_hierarchy(client, epic_title)

    if not items:
        return json.dumps({"error": "No work items found."})

    tree = build_tree(items)
    tree_text = "\n".join(format_tree_text(tree))

    # Save one YAML file per epic
    yaml_data = tree_to_yaml_structure(tree)
    saved_files: list[str] = []
    for epic in yaml_data.get("epics", []):
        epic_slug = slugify(epic["title"])
        output_path = os.path.join(_OUTPUT_DIR, f"{epic_slug}.yaml")
        save_yaml({"epics": [epic]}, output_path)
        saved_files.append(output_path)

    result: dict = {"tree": tree_text, "saved_files": saved_files}
    if include_summary:
        result["summary"] = compute_summary(items)

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def get_work_item(work_item_id: int) -> str:
    """
    Get a single work item by its numeric ID.

    Args:
        work_item_id: The Azure DevOps work item ID.
    """
    client = _get_client()
    item = client._get_work_item(work_item_id)
    if item is None:
        return json.dumps({"error": f"Work item {work_item_id} not found."})
    return json.dumps(item, indent=2, default=str)


@mcp.tool()
def generate_project(
    template_path: str,
    name: Optional[str] = None,
    datasources: Optional[list[str]] = None,
    dimensions: Optional[list[str]] = None,
    facts: Optional[list[str]] = None,
    semantic_models: Optional[list[str]] = None,
    visualizations: Optional[list[str]] = None,
    exclude: Optional[list[str]] = None,
    output_path: Optional[str] = None,
) -> str:
    """
    Generate a customized project YAML from a template.

    Loads a YAML template, applies project name and instance overrides,
    excludes optional features, expands parameterized features/stories,
    validates, saves to data/, and lints. Returns the hierarchy tree
    and summary.

    Args:
        template_path: Path to the YAML template file (e.g. "templates/project-template.yaml").
        name: Project name (overrides the epic title from the template).
        datasources: Data source system names for Data Source Integration features.
        dimensions: Dimension table names for the Data Modeling Layer.
        facts: Fact table names for the Data Modeling Layer.
        semantic_models: Semantic model instance names.
        visualizations: Presentation layer instance names.
        exclude: List of feature name keywords to exclude (optional features only).
        output_path: Custom output file path (default: data/<project-name>.yaml).
    """
    if not os.path.isfile(template_path):
        return json.dumps({"status": "error", "message": f"Template not found: {template_path}"})

    try:
        # 1. Load template
        data = load_template(template_path)

        # Override epic title with project name
        if name and data.get("epics"):
            data["epics"][0]["title"] = name

        # 2. Apply instance overrides from dedicated flags
        overrides = {}
        _flag_map = {
            "datasources": ("Data Source Integration", datasources),
            "dimensions": ("Data Modeling Layer.Dimension", dimensions),
            "facts": ("Data Modeling Layer.Fact", facts),
            "semantic_models": ("Semantic Model", semantic_models),
            "visualizations": ("Presentation Layer", visualizations),
        }
        for _, (override_key, values) in _flag_map.items():
            if values:
                overrides[override_key] = values
        if overrides:
            apply_instance_overrides(data, overrides)

        # 3. Exclude optional features
        if exclude:
            exclude_features(data, exclude)

        # 4. Expand parameterized features and stories
        expand_all_features(data)

        # 5. Validate
        errors = validate_template(data)
        if errors:
            return json.dumps({"status": "error", "validation_errors": errors})

        # 6. Count work items
        e, f, s, t = count_work_items(data)
        total = e + f + s + t

        # 7. Save YAML
        if output_path is None:
            project_name = data.get("epics", [{}])[0].get("title", "project")
            output_path = os.path.join("data", f"{slugify(project_name)}.yaml")
        save_yaml(data, output_path)

        # 8. Lint
        lint_ok, lint_msgs = lint_yaml(output_path)

        # 9. Build hierarchy tree text for display
        lines = []
        for epic in data.get("epics", []):
            lines.append(f"Epic: {epic['title']}")
            features = epic.get("features", [])
            for i, feat in enumerate(features):
                is_last = i == len(features) - 1
                prefix = "└── " if is_last else "├── "
                child_prefix = "    " if is_last else "│   "
                stories = feat.get("stories", [])
                sp = sum(st.get("story_points", 0) for st in stories)
                opt = " (optional)" if feat.get("optional") else ""
                lines.append(f"  {prefix}Feature: {feat['title']}{opt}  [{len(stories)} stories, {sp} SP]")
                for j, story in enumerate(stories):
                    is_last_s = j == len(stories) - 1
                    s_prefix = "└── " if is_last_s else "├── "
                    s_child = "    " if is_last_s else "│   "
                    lines.append(f"  {child_prefix}{s_prefix}Story: {story['title']}  (SP: {story.get('story_points', 0)})")
                    for k, task in enumerate(story.get("tasks", [])):
                        is_last_t = k == len(story.get("tasks", [])) - 1
                        t_prefix = "└── " if is_last_t else "├── "
                        lines.append(f"  {child_prefix}{s_child}{t_prefix}Task: {task['title']}  ({task.get('estimate', 0)}h)")

        tree_text = "\n".join(lines)

        # Calculate totals
        total_sp = sum(
            st.get("story_points", 0)
            for epic in data.get("epics", [])
            for feat in epic.get("features", [])
            for st in feat.get("stories", [])
        )
        total_hours = sum(
            task.get("estimate", 0)
            for epic in data.get("epics", [])
            for feat in epic.get("features", [])
            for st in feat.get("stories", [])
            for task in st.get("tasks", [])
        )

        return json.dumps({
            "status": "generated",
            "output_path": output_path,
            "tree": tree_text,
            "summary": {
                "epics": e,
                "features": f,
                "stories": s,
                "tasks": t,
                "total_items": total,
                "story_points": total_sp,
                "estimate_hours": total_hours,
            },
            "lint_ok": lint_ok,
            "lint_messages": lint_msgs if lint_msgs else [],
        }, indent=2)
    except Exception as ex:
        return json.dumps({"status": "error", "message": str(ex)})


@mcp.tool()
def search_work_items(title: str) -> str:
    """
    Search for work items by exact title.

    Args:
        title: The exact title to search for.

    Returns:
        JSON list of matching work item IDs.
    """
    client = _get_client()
    ids = client.find_by_title(title)
    return json.dumps({"matching_ids": ids, "count": len(ids)})


@mcp.tool()
def create_new_backlog(
    work_item_type: str,
    title: str,
    description: str = "",
    acceptance_criteria: str = "",
    story_points: Optional[float] = None,
    estimate: Optional[float] = None,
    parent_id: Optional[int] = None,
    iteration_path: Optional[str] = None,
) -> str:
    """
    Create a new work item (backlog item) in Azure DevOps.

    Only fields appropriate for the given *work_item_type* are persisted:

    * **Epic / Feature** — title, description, iteration_path.
    * **User Story** — adds story_points and acceptance_criteria.
    * **Task** — adds estimate (hours).

    Fields that don't belong to the chosen type are silently ignored.

    Args:
        work_item_type: One of "Epic", "Feature", "User Story", or "Task".
        title: The work item title.
        description: Optional description text.
        acceptance_criteria: Optional acceptance criteria (User Story only).
        story_points: Optional story points (User Story only).
        estimate: Optional effort/estimate in hours (Task only).
        parent_id: Optional parent work item ID for hierarchy linking.
        iteration_path: Optional iteration path (e.g. "MyProject\\Sprint 1").
    """
    client = _get_client()
    raw: dict = {"title": title}
    if description:
        raw["description"] = description
    if acceptance_criteria:
        raw["acceptance_criteria"] = acceptance_criteria
    if story_points is not None:
        raw["story_points"] = story_points
    if estimate is not None:
        raw["estimate"] = estimate
    if iteration_path is not None:
        raw["iteration_path"] = iteration_path

    # Filter to only the fields valid for this work-item type
    data = build_work_item_data(work_item_type, raw)

    try:
        result = client.create(work_item_type, data, parent_id)
        return json.dumps(
            {
                "status": "created",
                "id": result.get("id"),
                "title": title,
                "type": work_item_type,
            }
        )
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
def update_existing_item(
    work_item_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    state: Optional[str] = None,
    iteration_path: Optional[str] = None,
) -> str:
    """
    Update an existing work item's title, description, state, or iteration path.

    Args:
        work_item_id: The numeric ID of the work item to update.
        title: New title (leave empty to keep current).
        description: New description (leave empty to keep current).
        state: New state, e.g. "New", "Active", "Closed" (leave empty to keep current).
        iteration_path: New iteration path (e.g. "MyProject\\Sprint 1").
    """
    client = _get_client()
    data: dict = {}
    if title is not None:
        data["title"] = title
    if description is not None:
        data["description"] = description
    if state is not None:
        data["state"] = state
    if iteration_path is not None:
        data["iteration_path"] = iteration_path

    if not data:
        return json.dumps({"status": "error", "message": "No fields to update."})

    try:
        result = client._update_work_item(work_item_id, data)
        return json.dumps(
            {
                "status": "updated",
                "id": work_item_id,
                "updated_fields": list(data.keys()),
            }
        )
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
def upload_from_template(yaml_path: str) -> str:
    """
    Bulk-upload work items from a YAML project template file to Azure DevOps.

    The YAML file should follow the project-designer template format with
    epics → features → stories → tasks hierarchy.

    Args:
        yaml_path: Path to the YAML template file to upload.
    """
    if not os.path.isfile(yaml_path):
        return json.dumps({"status": "error", "message": f"File not found: {yaml_path}"})

    try:
        data = load_template(yaml_path)

        # Validate structure
        errors = validate_template(data)
        if errors:
            return json.dumps({"status": "error", "validation_errors": errors})

        # Expand parameterized features
        data = expand_all_features(data)

        # Upload
        results = upload_from_yaml(data, ORG, PROJECT, PAT)

        created = sum(1 for r in results if r["status"] == "created")
        skipped = sum(1 for r in results if r["status"] == "skipped")
        errored = sum(1 for r in results if r["status"] == "error")

        return json.dumps(
            {
                "status": "completed",
                "created": created,
                "skipped": skipped,
                "errors": errored,
                "details": results,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
def get_iterations() -> str:
    """
    List all iterations (sprints) defined in the Azure DevOps project.

    Returns a JSON array of iterations with id, name, path, start_date,
    and finish_date for each.
    """
    client = _get_client()
    try:
        iterations = client.get_iterations()
        return json.dumps(
            {"iterations": iterations, "count": len(iterations)},
            indent=2,
            default=str,
        )
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
def create_iteration(
    name: str,
    start_date: Optional[str] = None,
    finish_date: Optional[str] = None,
) -> str:
    """
    Create a new iteration (sprint) in the Azure DevOps project.

    Args:
        name: Iteration name (e.g. "Sprint 1").
        start_date: Optional start date in ISO-8601 format (e.g. "2026-03-01").
        finish_date: Optional finish date in ISO-8601 format (e.g. "2026-03-14").
    """
    client = _get_client()
    try:
        result = client.create_iteration(name, start_date, finish_date)
        return json.dumps(
            {"status": "created", **result},
            indent=2,
            default=str,
        )
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
def update_iteration(
    current_name: str,
    new_name: Optional[str] = None,
    start_date: Optional[str] = None,
    finish_date: Optional[str] = None,
) -> str:
    """
    Update an existing iteration (sprint) — rename it and/or set dates.

    Args:
        current_name: The current name of the iteration (e.g. "Iteration 1").
        new_name: New name for the iteration (e.g. "Sprint 1"). Leave empty to keep current name.
        start_date: New start date in ISO-8601 format (e.g. "2026-03-01"). Leave empty to keep current.
        finish_date: New finish date in ISO-8601 format (e.g. "2026-03-14"). Leave empty to keep current.
    """
    client = _get_client()
    try:
        result = client.update_iteration(current_name, new_name, start_date, finish_date)
        return json.dumps(
            {"status": "updated", **result},
            indent=2,
            default=str,
        )
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
def subscribe_iterations() -> str:
    """
    Subscribe all project iterations to the default team so they appear
    on the Azure Board.  Calls get_iterations to discover every iteration
    and then subscribes each one.  Already-subscribed iterations are
    silently skipped (HTTP 409).

    No arguments required — operates on every iteration in the project.
    """
    client = _get_client()
    try:
        iterations = client.get_iterations()
        results = []
        for it in iterations:
            identifier = it.get("identifier", "")
            if not identifier:
                results.append({"name": it["name"], "status": "skipped", "reason": "no identifier"})
                continue
            res = client.subscribe_iteration(identifier)
            results.append({"name": it["name"], **res})
        return json.dumps({"status": "done", "results": results, "count": len(results)}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
def run_wiql_query(query: str) -> str:
    """
    Run a raw WIQL (Work Item Query Language) query against Azure DevOps
    and return matching work item IDs.

    Args:
        query: A WIQL query string, e.g.
               "SELECT [System.Id] FROM WorkItems WHERE [System.State] = 'Active'"
    """
    client = _get_client()
    try:
        ids = client.run_wiql(query)
        return json.dumps({"matching_ids": ids, "count": len(ids)})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


# ═══════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Azure DevOps MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for SSE transport (default: 8000)",
    )
    args = parser.parse_args()

    if args.transport == "sse":
        mcp.run(transport="sse", port=args.port)
    else:
        mcp.run(transport="stdio")
