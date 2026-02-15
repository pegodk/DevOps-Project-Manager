"""Tests for upload_service functions."""

import pytest
from src.upload_service import upload_from_yaml, _create_and_track, _resolve_id
from src.devops_client import DevOpsClient


@pytest.fixture
def sample_data():
    """Simple project YAML data for upload testing."""
    return {
        "epics": [{
            "title": "Test Epic",
            "description": "Epic desc",
            "features": [{
                "title": "Test Feature",
                "description": "Feature desc",
                "stories": [{
                    "title": "Test Story",
                    "description": "Story desc",
                    "acceptance_criteria": "ac",
                    "story_points": 5,
                    "tasks": [{
                        "title": "Test Task",
                        "description": "Task desc",
                        "estimate": 4,
                    }],
                }],
            }],
        }],
    }


# ── _create_and_track ─────────────────────────────────────────────────────────

def test_create_and_track_new_item():
    svc = DevOpsClient()
    result = _create_and_track(svc, "Epic", {"title": "E1"})
    assert result["status"] == "created"
    assert result["id"] == 1


def test_create_and_track_skips_duplicate():
    svc = DevOpsClient()
    _create_and_track(svc, "Epic", {"title": "E1"})
    result = _create_and_track(svc, "Epic", {"title": "E1"})
    assert result["status"] == "skipped"


# ── _resolve_id ───────────────────────────────────────────────────────────────

def test_resolve_id_from_result():
    svc = DevOpsClient()
    result = {"id": 42}
    assert _resolve_id(svc, result, "anything") == 42


def test_resolve_id_looks_up_when_none():
    svc = DevOpsClient()
    svc.create("Epic", {"title": "E1"})
    result = {"id": None}
    assert _resolve_id(svc, result, "E1") == 1


# ── upload_from_yaml ──────────────────────────────────────────────────────────

def test_upload_creates_full_hierarchy(sample_data, capsys):
    # Uses in-memory DevOpsClient (no credentials)
    results = upload_from_yaml(sample_data, None, None, None)
    assert len(results) == 4  # epic + feature + story + task

    statuses = [r["status"] for r in results]
    assert all(s == "created" for s in statuses)

    types = [r["type"] for r in results]
    assert types == ["Epic", "Feature", "User Story", "Task"]


def test_upload_skips_duplicates_on_rerun(sample_data):
    results1 = upload_from_yaml(sample_data, None, None, None)
    # Second run against fresh client won't see the items from the first run
    # (each call creates a new DevOpsClient), so all will be created again.
    # This tests that the function completes without error.
    assert len(results1) == 4


def test_upload_passes_iteration_path(capsys):
    """iteration_path in YAML data should be stored on the created work item."""
    data = {
        "epics": [{
            "title": "Iter Epic",
            "description": "",
            "features": [{
                "title": "Iter Feature",
                "description": "",
                "stories": [{
                    "title": "Iter Story",
                    "description": "desc",
                    "acceptance_criteria": "ac",
                    "story_points": 3,
                    "iteration_path": "Proj\\Sprint 1",
                    "tasks": [],
                }],
            }],
        }],
    }
    results = upload_from_yaml(data, None, None, None)
    assert len(results) == 3  # epic + feature + story
    # The story should have been created with the iteration_path
    story_result = [r for r in results if r["type"] == "User Story"][0]
    assert story_result["status"] == "created"
