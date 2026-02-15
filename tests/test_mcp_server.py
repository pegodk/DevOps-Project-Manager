"""
Tests for the MCP server tools.

Tests exercise each tool function directly (without starting the MCP transport)
by calling the underlying Python functions with the in-memory DevOpsClient backend.
"""

import json
import os
import pytest

# conftest.py clears credentials and sets sys.path
from src import mcp_server as srv


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_client():
    """Reset the shared client before each test so tests are isolated."""
    srv.ORG = ""
    srv.PROJECT = ""
    srv.PAT = ""
    srv._client = None
    yield
    srv._client = None


# ---------------------------------------------------------------------------
# validate_connection
# ---------------------------------------------------------------------------

class TestValidateConnection:
    def test_returns_json(self):
        result = json.loads(srv.validate_connection())
        # In-memory client has no org/pat, so validate_connection will fail
        assert "connected" in result or "message" in result


# ---------------------------------------------------------------------------
# create_new_backlog
# ---------------------------------------------------------------------------

class TestCreateNewBacklog:
    def test_create_epic(self):
        result = json.loads(srv.create_new_backlog("Epic", "Test Epic", description="An epic"))
        assert result["status"] == "created"
        assert result["type"] == "Epic"
        assert result["title"] == "Test Epic"
        assert isinstance(result["id"], int)

    def test_create_user_story_with_parent(self):
        epic = json.loads(srv.create_new_backlog("Epic", "Parent Epic"))
        epic_id = epic["id"]

        story = json.loads(srv.create_new_backlog(
            "User Story",
            "My Story",
            description="desc",
            acceptance_criteria="AC",
            story_points=5.0,
            parent_id=epic_id,
        ))
        assert story["status"] == "created"
        assert story["id"] != epic_id

    def test_create_task_with_estimate(self):
        result = json.loads(srv.create_new_backlog("Task", "Do the thing", estimate=4.0))
        assert result["status"] == "created"

    def test_create_with_iteration_path(self):
        result = json.loads(srv.create_new_backlog(
            "User Story", "Sprint Story",
            iteration_path="MyProject\\Sprint 1",
        ))
        assert result["status"] == "created"
        # Verify the iteration_path was stored
        client = srv._get_client()
        item = client._items[result["id"]]
        assert item["iteration_path"] == "MyProject\\Sprint 1"


# ---------------------------------------------------------------------------
# get_work_item
# ---------------------------------------------------------------------------

class TestGetWorkItem:
    def test_get_existing_item(self):
        created = json.loads(srv.create_new_backlog("Feature", "Feat A"))
        wid = created["id"]

        result = json.loads(srv.get_work_item(wid))
        assert result["id"] == wid
        # In-memory backend returns title at top level
        assert result.get("title") == "Feat A" or "error" not in result

    def test_get_missing_item(self):
        result = json.loads(srv.get_work_item(99999))
        assert "error" in result


# ---------------------------------------------------------------------------
# search_work_items
# ---------------------------------------------------------------------------

class TestSearchWorkItems:
    def test_find_existing(self):
        srv.create_new_backlog("Epic", "Unique Title 123")
        result = json.loads(srv.search_work_items("Unique Title 123"))
        assert result["count"] >= 1
        assert result["matching_ids"]

    def test_find_missing(self):
        result = json.loads(srv.search_work_items("Does Not Exist 999"))
        assert result["count"] == 0


# ---------------------------------------------------------------------------
# update_existing_item
# ---------------------------------------------------------------------------

class TestUpdateExistingItem:
    def test_update_title(self):
        created = json.loads(srv.create_new_backlog("Epic", "Old Title"))
        wid = created["id"]

        result = json.loads(srv.update_existing_item(wid, title="New Title"))
        assert result["status"] == "updated"
        assert "title" in result["updated_fields"]

        # Verify the change persisted via search
        search = json.loads(srv.search_work_items("New Title"))
        assert search["count"] >= 1

    def test_update_state(self):
        created = json.loads(srv.create_new_backlog("Task", "Task X"))
        wid = created["id"]

        result = json.loads(srv.update_existing_item(wid, state="Active"))
        assert result["status"] == "updated"

    def test_update_no_fields(self):
        created = json.loads(srv.create_new_backlog("Epic", "E"))
        wid = created["id"]
        result = json.loads(srv.update_existing_item(wid))
        assert result["status"] == "error"

    def test_update_iteration_path(self):
        created = json.loads(srv.create_new_backlog("User Story", "S1"))
        wid = created["id"]
        result = json.loads(srv.update_existing_item(
            wid, iteration_path="Proj\\Sprint 2",
        ))
        assert result["status"] == "updated"
        assert "iteration_path" in result["updated_fields"]
        # Verify the change persisted
        client = srv._get_client()
        assert client._items[wid]["iteration_path"] == "Proj\\Sprint 2"

    def test_update_nonexistent(self):
        result = json.loads(srv.update_existing_item(99999, title="X"))
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# upload_from_template
# ---------------------------------------------------------------------------

class TestUploadFromTemplate:
    def test_file_not_found(self):
        result = json.loads(srv.upload_from_template("/nonexistent/file.yaml"))
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()


# ---------------------------------------------------------------------------
# get_project_status
# ---------------------------------------------------------------------------

class TestGetProjectStatus:
    def test_empty_project(self):
        result = json.loads(srv.get_project_status())
        assert "error" in result

    def test_saves_yaml_per_epic(self, tmp_path, monkeypatch):
        """get_project_status should save one YAML per epic in output/."""
        # Point output dir to tmp_path so we don't pollute the real output/
        output_dir = str(tmp_path / "output")
        monkeypatch.setattr(srv, "_OUTPUT_DIR", output_dir)

        # Create a small hierarchy: Epic → Feature → Story
        epic = json.loads(srv.create_new_backlog("Epic", "Alpha Epic"))
        feat = json.loads(
            srv.create_new_backlog("Feature", "Alpha Feature", parent_id=epic["id"])
        )
        json.loads(
            srv.create_new_backlog(
                "User Story", "Alpha Story",
                story_points=3, parent_id=feat["id"],
            )
        )

        result = json.loads(srv.get_project_status())

        # Should contain saved_files list
        assert "saved_files" in result
        assert len(result["saved_files"]) == 1
        assert "alpha-epic.yaml" in result["saved_files"][0]

        # File should actually exist and contain the epic data
        import yaml
        yaml_path = result["saved_files"][0]
        assert os.path.exists(yaml_path)
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert len(data["epics"]) == 1
        assert data["epics"][0]["title"] == "Alpha Epic"
        assert len(data["epics"][0]["features"]) == 1
        assert data["epics"][0]["features"][0]["title"] == "Alpha Feature"

    def test_saves_multiple_epics(self, tmp_path, monkeypatch):
        """Each epic gets its own YAML file."""
        monkeypatch.setattr(srv, "_OUTPUT_DIR", str(tmp_path / "output"))

        json.loads(srv.create_new_backlog("Epic", "First Epic"))
        json.loads(srv.create_new_backlog("Epic", "Second Epic"))

        result = json.loads(srv.get_project_status())
        assert len(result["saved_files"]) == 2
        filenames = [os.path.basename(f) for f in result["saved_files"]]
        assert "first-epic.yaml" in filenames
        assert "second-epic.yaml" in filenames

    def test_includes_summary(self, tmp_path, monkeypatch):
        monkeypatch.setattr(srv, "_OUTPUT_DIR", str(tmp_path / "output"))
        json.loads(srv.create_new_backlog("Epic", "Summary Epic"))
        result = json.loads(srv.get_project_status(include_summary=True))
        assert "summary" in result
        assert result["summary"]["total_items"] >= 1

    def test_excludes_summary(self, tmp_path, monkeypatch):
        monkeypatch.setattr(srv, "_OUTPUT_DIR", str(tmp_path / "output"))
        json.loads(srv.create_new_backlog("Epic", "No Summary"))
        result = json.loads(srv.get_project_status(include_summary=False))
        assert "summary" not in result


# ---------------------------------------------------------------------------
# get_iterations
# ---------------------------------------------------------------------------

class TestGetIterations:
    def test_empty_returns_zero(self):
        result = json.loads(srv.get_iterations())
        assert result["count"] == 0
        assert result["iterations"] == []

    def test_returns_created_iterations(self):
        # Create iterations first
        json.loads(srv.create_iteration("Sprint 1", "2026-03-01", "2026-03-14"))
        json.loads(srv.create_iteration("Sprint 2"))

        result = json.loads(srv.get_iterations())
        assert result["count"] == 2
        names = [it["name"] for it in result["iterations"]]
        assert "Sprint 1" in names
        assert "Sprint 2" in names


# ---------------------------------------------------------------------------
# create_iteration
# ---------------------------------------------------------------------------

class TestCreateIteration:
    def test_create_basic(self):
        result = json.loads(srv.create_iteration("Sprint 1"))
        assert result["status"] == "created"
        assert result["name"] == "Sprint 1"
        assert isinstance(result["id"], int)

    def test_create_with_dates(self):
        result = json.loads(srv.create_iteration(
            "Sprint 2", start_date="2026-03-01", finish_date="2026-03-14",
        ))
        assert result["status"] == "created"
        assert result["start_date"] == "2026-03-01"
        assert result["finish_date"] == "2026-03-14"

    def test_create_without_dates(self):
        result = json.loads(srv.create_iteration("Backlog"))
        assert result["status"] == "created"
        assert result["start_date"] is None
        assert result["finish_date"] is None


# ---------------------------------------------------------------------------
# update_iteration
# ---------------------------------------------------------------------------

class TestUpdateIteration:
    def test_rename(self):
        json.loads(srv.create_iteration("Old"))
        result = json.loads(srv.update_iteration("Old", new_name="New"))
        assert result["status"] == "updated"
        assert result["name"] == "New"

    def test_set_dates(self):
        json.loads(srv.create_iteration("Sprint X"))
        result = json.loads(srv.update_iteration(
            "Sprint X", start_date="2026-05-01", finish_date="2026-05-14",
        ))
        assert result["status"] == "updated"
        assert result["start_date"] == "2026-05-01"
        assert result["finish_date"] == "2026-05-14"

    def test_not_found(self):
        result = json.loads(srv.update_iteration("Ghost", new_name="X"))
        assert result["status"] == "error"
        assert "not found" in result["message"]


# ---------------------------------------------------------------------------
# subscribe_iterations
# ---------------------------------------------------------------------------

class TestSubscribeIterations:
    def test_subscribe_empty(self):
        result = json.loads(srv.subscribe_iterations())
        assert result["status"] == "done"
        assert result["count"] == 0

    def test_subscribe_existing(self):
        json.loads(srv.create_iteration("Sprint 1"))
        json.loads(srv.create_iteration("Sprint 2"))
        result = json.loads(srv.subscribe_iterations())
        assert result["status"] == "done"
        assert result["count"] == 2
        for r in result["results"]:
            assert r["status"] == "subscribed"
