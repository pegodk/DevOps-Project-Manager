"""
Tests for src.hierarchy_service — hierarchy querying, tree building,
summary computation, and formatters.

Uses the in-memory DevOpsClient backend so no Azure connection is needed.
"""

import pytest

# conftest.py clears credentials and sets sys.path

from src.devops_client import DevOpsClient
from src.hierarchy_service import (
    WORK_ITEM_TYPES,
    FIELDS,
    fetch_hierarchy,
    prune_to_subtree,
    build_tree,
    compute_summary,
    format_tree_text,
    tree_to_yaml_structure,
    clean_html,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Return a fresh in-memory DevOpsClient."""
    return DevOpsClient("", "", "")


@pytest.fixture
def populated_client(client):
    """Return a client pre-loaded with a small hierarchy."""
    epic = client.create("Epic", {"title": "Platform Epic", "description": "Main epic"})
    feat = client.create("Feature", {"title": "Auth Feature", "description": "Auth flow"}, parent_id=epic["id"])
    story = client.create(
        "User Story",
        {
            "title": "Login Story",
            "description": "User can log in",
            "acceptance_criteria": "Given/When/Then",
            "story_points": 5,
        },
        parent_id=feat["id"],
    )
    task = client.create(
        "Task",
        {"title": "Implement login API", "description": "REST endpoint", "estimate": 8},
        parent_id=story["id"],
    )
    return client, {"epic": epic, "feature": feat, "story": story, "task": task}


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_work_item_types(self):
        assert WORK_ITEM_TYPES == ["Epic", "Feature", "User Story", "Task"]

    def test_fields_contains_essentials(self):
        assert "System.Id" in FIELDS
        assert "System.Title" in FIELDS
        assert "System.Parent" in FIELDS


# ---------------------------------------------------------------------------
# fetch_hierarchy
# ---------------------------------------------------------------------------

class TestFetchHierarchy:
    def test_empty_project(self, client):
        items = fetch_hierarchy(client)
        assert items == {}

    def test_returns_all_items(self, populated_client):
        client, ids = populated_client
        items = fetch_hierarchy(client)
        assert len(items) == 4
        assert ids["epic"]["id"] in items
        assert ids["task"]["id"] in items

    def test_item_shape(self, populated_client):
        client, ids = populated_client
        items = fetch_hierarchy(client)
        epic = items[ids["epic"]["id"]]
        assert epic["type"] == "Epic"
        assert epic["title"] == "Platform Epic"
        assert "parent_id" in epic
        assert "state" in epic

    def test_filter_by_epic_title(self, populated_client):
        client, ids = populated_client
        # Add a second unrelated epic
        client.create("Epic", {"title": "Other Epic"})
        items = fetch_hierarchy(client, epic_title="Platform Epic")
        # Should only contain the Platform Epic subtree (4 items)
        assert len(items) == 4

    def test_filter_nonexistent_epic(self, populated_client):
        client, _ = populated_client
        items = fetch_hierarchy(client, epic_title="Does Not Exist")
        assert items == {}


# ---------------------------------------------------------------------------
# prune_to_subtree
# ---------------------------------------------------------------------------

class TestPruneToSubtree:
    def test_prune_keeps_descendants(self):
        items = {
            1: {"id": 1, "type": "Epic", "title": "E1", "parent_id": None},
            2: {"id": 2, "type": "Feature", "title": "F1", "parent_id": 1},
            3: {"id": 3, "type": "User Story", "title": "S1", "parent_id": 2},
            4: {"id": 4, "type": "Epic", "title": "E2", "parent_id": None},
            5: {"id": 5, "type": "Feature", "title": "F2", "parent_id": 4},
        }
        result = prune_to_subtree(items, {1})
        assert set(result.keys()) == {1, 2, 3}

    def test_prune_single_root(self):
        items = {
            10: {"id": 10, "type": "Epic", "title": "Solo", "parent_id": None},
        }
        result = prune_to_subtree(items, {10})
        assert 10 in result


# ---------------------------------------------------------------------------
# build_tree
# ---------------------------------------------------------------------------

class TestBuildTree:
    def test_single_root(self):
        items = {
            1: {"id": 1, "type": "Epic", "title": "E1", "parent_id": None},
        }
        tree = build_tree(items)
        assert len(tree) == 1
        assert tree[0]["title"] == "E1"

    def test_nested_children(self):
        items = {
            1: {"id": 1, "type": "Epic", "title": "E1", "parent_id": None},
            2: {"id": 2, "type": "Feature", "title": "F1", "parent_id": 1},
            3: {"id": 3, "type": "User Story", "title": "S1", "parent_id": 2},
        }
        tree = build_tree(items)
        assert len(tree) == 1
        assert "children" in tree[0]
        feat = tree[0]["children"][0]
        assert feat["title"] == "F1"
        assert "children" in feat
        assert feat["children"][0]["title"] == "S1"

    def test_sorted_by_type_then_title(self):
        items = {
            1: {"id": 1, "type": "Feature", "title": "B-feat", "parent_id": None},
            2: {"id": 2, "type": "Epic", "title": "A-epic", "parent_id": None},
            3: {"id": 3, "type": "Feature", "title": "A-feat", "parent_id": None},
        }
        tree = build_tree(items)
        types = [n["type"] for n in tree]
        assert types == ["Epic", "Feature", "Feature"]
        assert tree[1]["title"] == "A-feat"
        assert tree[2]["title"] == "B-feat"


# ---------------------------------------------------------------------------
# compute_summary
# ---------------------------------------------------------------------------

class TestComputeSummary:
    def test_counts(self):
        items = {
            1: {"id": 1, "type": "Epic", "title": "E", "state": "New", "story_points": None, "estimate": None},
            2: {"id": 2, "type": "Feature", "title": "F", "state": "Active", "story_points": None, "estimate": None},
            3: {"id": 3, "type": "User Story", "title": "S", "state": "New", "story_points": 8, "estimate": None},
            4: {"id": 4, "type": "Task", "title": "T", "state": "New", "story_points": None, "estimate": 4},
        }
        s = compute_summary(items)
        assert s["total_items"] == 4
        assert s["counts"]["Epic"] == 1
        assert s["counts"]["Task"] == 1
        assert s["total_story_points"] == 8
        assert s["total_estimate_hours"] == 4

    def test_state_breakdown(self):
        items = {
            1: {"id": 1, "type": "Task", "title": "T1", "state": "Active", "story_points": None, "estimate": None},
            2: {"id": 2, "type": "Task", "title": "T2", "state": "Active", "story_points": None, "estimate": None},
            3: {"id": 3, "type": "Task", "title": "T3", "state": "Closed", "story_points": None, "estimate": None},
        }
        s = compute_summary(items)
        assert s["states"]["Task"]["Active"] == 2
        assert s["states"]["Task"]["Closed"] == 1


# ---------------------------------------------------------------------------
# format_tree_text
# ---------------------------------------------------------------------------

class TestFormatTreeText:
    def test_single_node(self):
        tree = [{"id": 1, "type": "Epic", "title": "My Epic", "state": "New"}]
        lines = format_tree_text(tree)
        assert len(lines) == 1
        assert "Epic: My Epic" in lines[0]
        assert "New" in lines[0]

    def test_nested_indentation(self):
        tree = [
            {
                "id": 1,
                "type": "Epic",
                "title": "E",
                "state": "New",
                "children": [
                    {"id": 2, "type": "Feature", "title": "F", "state": "Active"},
                ],
            }
        ]
        lines = format_tree_text(tree)
        assert len(lines) == 2
        # Child should be indented
        assert lines[1].startswith("  ")

    def test_story_points_shown(self):
        tree = [{"id": 1, "type": "User Story", "title": "S", "state": "New", "story_points": 13}]
        lines = format_tree_text(tree)
        assert "SP:13" in lines[0]

    def test_iteration_path_shown(self):
        tree = [{"id": 1, "type": "User Story", "title": "S", "state": "New",
                 "iteration_path": "Proj\\Sprint 1"}]
        lines = format_tree_text(tree)
        assert "Iteration:Proj\\Sprint 1" in lines[0]

    def test_no_iteration_path_omitted(self):
        tree = [{"id": 1, "type": "User Story", "title": "S", "state": "New"}]
        lines = format_tree_text(tree)
        assert "Iteration" not in lines[0]

    def test_no_iteration_path_omitted(self):
        tree = [{"id": 1, "type": "User Story", "title": "S", "state": "New"}]
        lines = format_tree_text(tree)
        assert "Iteration" not in lines[0]


# ---------------------------------------------------------------------------
# tree_to_yaml_structure
# ---------------------------------------------------------------------------

class TestTreeToYamlStructure:
    def test_basic_structure(self):
        tree = [
            {
                "id": 1,
                "type": "Epic",
                "title": "E1",
                "description": "Epic desc",
                "children": [
                    {
                        "id": 2,
                        "type": "Feature",
                        "title": "F1",
                        "description": "Feat desc",
                        "children": [
                            {
                                "id": 3,
                                "type": "User Story",
                                "title": "S1",
                                "description": "Story desc",
                                "story_points": 5,
                                "acceptance_criteria": "AC",
                                "children": [
                                    {
                                        "id": 4,
                                        "type": "Task",
                                        "title": "T1",
                                        "description": "Task desc",
                                        "estimate": 3,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
        result = tree_to_yaml_structure(tree)
        assert "epics" in result
        assert len(result["epics"]) == 1
        epic = result["epics"][0]
        assert epic["title"] == "E1"
        assert len(epic["features"]) == 1
        feat = epic["features"][0]
        assert feat["title"] == "F1"
        assert len(feat["stories"]) == 1
        story = feat["stories"][0]
        assert story["title"] == "S1"
        assert story["story_points"] == 5
        assert len(story["tasks"]) == 1
        assert story["tasks"][0]["title"] == "T1"

    def test_stories_without_tasks_omit_tasks_key(self):
        tree = [
            {
                "id": 1,
                "type": "Epic",
                "title": "E",
                "description": "",
                "children": [
                    {
                        "id": 2,
                        "type": "Feature",
                        "title": "F",
                        "description": "",
                        "children": [
                            {
                                "id": 3,
                                "type": "User Story",
                                "title": "S",
                                "description": "",
                                "story_points": None,
                                "acceptance_criteria": "",
                            }
                        ],
                    }
                ],
            }
        ]
        result = tree_to_yaml_structure(tree)
        story = result["epics"][0]["features"][0]["stories"][0]
        assert "tasks" not in story

    def test_iteration_path_included_when_set(self):
        tree = [
            {
                "id": 1,
                "type": "Epic",
                "title": "E",
                "description": "",
                "iteration_path": "Proj\\Sprint 1",
                "children": [
                    {
                        "id": 2,
                        "type": "Feature",
                        "title": "F",
                        "description": "",
                        "iteration_path": "Proj\\Sprint 2",
                        "children": [
                            {
                                "id": 3,
                                "type": "User Story",
                                "title": "S",
                                "description": "",
                                "story_points": None,
                                "acceptance_criteria": "",
                                "iteration_path": "Proj\\Sprint 3",
                            }
                        ],
                    }
                ],
            }
        ]
        result = tree_to_yaml_structure(tree)
        assert result["epics"][0]["iteration_path"] == "Proj\\Sprint 1"
        assert result["epics"][0]["features"][0]["iteration_path"] == "Proj\\Sprint 2"
        assert result["epics"][0]["features"][0]["stories"][0]["iteration_path"] == "Proj\\Sprint 3"

    def test_iteration_path_omitted_when_empty(self):
        tree = [
            {
                "id": 1,
                "type": "Epic",
                "title": "E",
                "description": "",
                "iteration_path": "",
                "children": [
                    {
                        "id": 2,
                        "type": "Feature",
                        "title": "F",
                        "description": "",
                        "children": [
                            {
                                "id": 3,
                                "type": "User Story",
                                "title": "S",
                                "description": "",
                                "story_points": None,
                                "acceptance_criteria": "",
                            }
                        ],
                    }
                ],
            }
        ]
        result = tree_to_yaml_structure(tree)
        assert "iteration_path" not in result["epics"][0]
        assert "iteration_path" not in result["epics"][0]["features"][0]
        assert "iteration_path" not in result["epics"][0]["features"][0]["stories"][0]


# ---------------------------------------------------------------------------
# clean_html
# ---------------------------------------------------------------------------

class TestCleanHtml:
    def test_empty_string(self):
        assert clean_html("") == ""

    def test_none(self):
        assert clean_html(None) == ""

    def test_strips_tags(self):
        assert clean_html("<b>bold</b>") == "bold"

    def test_div_to_newline(self):
        result = clean_html("<div>line1</div><div>line2</div>")
        assert "line1" in result
        assert "line2" in result

    def test_br_to_newline(self):
        result = clean_html("a<br/>b")
        assert "a" in result
        assert "b" in result


# ---------------------------------------------------------------------------
# Integration: fetch_hierarchy → build_tree → format
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_pipeline(self, populated_client):
        client, ids = populated_client
        items = fetch_hierarchy(client)
        assert len(items) == 4

        tree = build_tree(items)
        assert len(tree) == 1  # one root epic
        assert tree[0]["title"] == "Platform Epic"

        lines = format_tree_text(tree)
        assert len(lines) >= 4  # at least one line per item

        summary = compute_summary(items)
        assert summary["total_items"] == 4
        assert summary["counts"]["Epic"] == 1

        yaml_struct = tree_to_yaml_structure(tree)
        assert len(yaml_struct["epics"]) == 1
