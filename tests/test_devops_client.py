"""Tests for DevOpsClient (in-memory mode)."""

import pytest
from src.devops_client import DevOpsClient


@pytest.fixture
def client():
    """DevOpsClient without credentials uses in-memory store."""
    return DevOpsClient()


# ── CRUD ──────────────────────────────────────────────────────────────────────

def test_create_returns_id_and_title(client):
    result = client.create("Epic", {"title": "My Epic", "description": "desc"})
    assert result["id"] == 1
    assert result["title"] == "My Epic"


def test_create_increments_ids(client):
    r1 = client.create("Epic", {"title": "E1"})
    r2 = client.create("Feature", {"title": "F1"})
    assert r1["id"] == 1
    assert r2["id"] == 2


def test_create_with_parent(client):
    epic = client.create("Epic", {"title": "E"})
    feat = client.create("Feature", {"title": "F"}, parent_id=epic["id"])
    assert feat["id"] == 2


def test_find_by_title(client):
    client.create("Epic", {"title": "Unique"})
    client.create("Feature", {"title": "Other"})
    ids = client.find_by_title("Unique")
    assert ids == [1]


def test_find_by_title_no_match(client):
    assert client.find_by_title("Ghost") == []


def test_work_item_exists(client):
    client.create("Epic", {"title": "E1"})
    assert client.work_item_exists("E1") is True
    assert client.work_item_exists("E2") is False


def test_work_item_exists_with_parent(client):
    epic = client.create("Epic", {"title": "E"})
    client.create("Feature", {"title": "F"}, parent_id=epic["id"])
    assert client.work_item_exists("F", parent_id=epic["id"]) is True
    assert client.work_item_exists("F", parent_id=999) is False


def test_get_work_item(client):
    client.create("Task", {"title": "T1", "description": "do stuff"})
    item = client._get_work_item(1)
    assert item["title"] == "T1"


def test_get_missing_work_item(client):
    assert client._get_work_item(999) is None


def test_update_work_item(client):
    client.create("Epic", {"title": "Old"})
    updated = client._update_work_item(1, {"title": "New"})
    assert updated["title"] == "New"


def test_delete_work_item(client):
    client.create("Epic", {"title": "Gone"})
    result = client._delete_work_item(1)
    assert result["success"] is True
    assert client._get_work_item(1) is None


def test_delete_missing_work_item(client):
    result = client._delete_work_item(999)
    assert result["success"] is False


# ── Iteration path ────────────────────────────────────────────────────────────

def test_create_with_iteration_path(client):
    result = client.create("User Story", {
        "title": "S1",
        "iteration_path": "MyProject\\Sprint 1",
    })
    item = client._items[result["id"]]
    assert item["iteration_path"] == "MyProject\\Sprint 1"


def test_create_without_iteration_path_defaults_empty(client):
    result = client.create("Epic", {"title": "E1"})
    item = client._items[result["id"]]
    assert item["iteration_path"] == ""


def test_update_iteration_path(client):
    result = client.create("User Story", {"title": "S1"})
    client._update_work_item(result["id"], {"iteration_path": "Proj\\Sprint 2"})
    assert client._items[result["id"]]["iteration_path"] == "Proj\\Sprint 2"


def test_get_work_items_batch_maps_iteration_path(client):
    client.create("User Story", {
        "title": "S1",
        "iteration_path": "Proj\\Sprint 3",
    })
    batch = client.get_work_items_batch([1])
    assert batch[0]["fields"]["System.IterationPath"] == "Proj\\Sprint 3"


# ── Iterations ────────────────────────────────────────────────────────────────

def test_get_iterations_empty(client):
    assert client.get_iterations() == []


def test_create_iteration_basic(client):
    result = client.create_iteration("Sprint 1")
    assert result["id"] == 1
    assert result["identifier"] == "guid-1"
    assert result["name"] == "Sprint 1"
    assert "Sprint 1" in result["path"]
    assert result["start_date"] is None
    assert result["finish_date"] is None


def test_create_iteration_with_dates(client):
    result = client.create_iteration("Sprint 2", "2026-03-01", "2026-03-14")
    assert result["name"] == "Sprint 2"
    assert result["start_date"] == "2026-03-01"
    assert result["finish_date"] == "2026-03-14"


def test_get_iterations_returns_created(client):
    client.create_iteration("S1")
    client.create_iteration("S2", "2026-04-01", "2026-04-14")
    iterations = client.get_iterations()
    assert len(iterations) == 2
    assert iterations[0]["name"] == "S1"
    assert iterations[1]["name"] == "S2"


def test_create_iteration_ids_increment(client):
    r1 = client.create_iteration("A")
    r2 = client.create_iteration("B")
    assert r1["id"] == 1
    assert r2["id"] == 2


def test_update_iteration_rename(client):
    client.create_iteration("Old Name")
    result = client.update_iteration("Old Name", new_name="New Name")
    assert result["name"] == "New Name"
    assert "New Name" in result["path"]
    assert client.get_iterations()[0]["name"] == "New Name"


def test_update_iteration_dates(client):
    client.create_iteration("Sprint 1")
    result = client.update_iteration(
        "Sprint 1", start_date="2026-03-01", finish_date="2026-03-14"
    )
    assert result["start_date"] == "2026-03-01"
    assert result["finish_date"] == "2026-03-14"


def test_update_iteration_rename_and_dates(client):
    client.create_iteration("Iter 1")
    result = client.update_iteration(
        "Iter 1", new_name="Sprint 1",
        start_date="2026-04-01", finish_date="2026-04-14",
    )
    assert result["name"] == "Sprint 1"
    assert result["start_date"] == "2026-04-01"


def test_update_iteration_not_found(client):
    with pytest.raises(Exception, match="not found"):
        client.update_iteration("Ghost")


def test_subscribe_iteration(client):
    """subscribe_iteration returns success dict in-memory."""
    result = client.subscribe_iteration("some-guid-123")
    assert result["status"] == "subscribed"
    assert result["identifier"] == "some-guid-123"


def test_flatten_iteration_nodes():
    """_flatten_iteration_nodes should extract node and all descendants."""
    node = {
        "id": 10,
        "identifier": "abc-123",
        "name": "Sprint 1",
        "path": "\\Project\\Iteration\\Sprint 1",
        "attributes": {"startDate": "2026-01-01", "finishDate": "2026-01-14"},
        "children": [
            {
                "id": 11,
                "identifier": "def-456",
                "name": "Week 1",
                "path": "\\Project\\Iteration\\Sprint 1\\Week 1",
                "attributes": {},
            },
        ],
    }
    result = DevOpsClient._flatten_iteration_nodes(node)
    assert len(result) == 2
    assert result[0]["name"] == "Sprint 1"
    assert result[0]["identifier"] == "abc-123"
    assert result[0]["start_date"] == "2026-01-01"
    assert result[1]["name"] == "Week 1"
    assert result[1]["identifier"] == "def-456"
    assert result[1]["start_date"] is None


# ── HTML conversion ───────────────────────────────────────────────────────────

def test_to_html_bullets():
    text = "• Item one\n• Item two\n• Item three\n"
    html = DevOpsClient._to_html(text)
    assert html == "<ul><li>Item one</li><li>Item two</li><li>Item three</li></ul>"


def test_to_html_paragraphs():
    text = "First paragraph\nSecond paragraph\n"
    html = DevOpsClient._to_html(text)
    assert html == "<p>First paragraph</p><p>Second paragraph</p>"


def test_to_html_mixed():
    text = "Overview:\n• A\n• B\nFooter note\n"
    html = DevOpsClient._to_html(text)
    assert html == "<p>Overview:</p><ul><li>A</li><li>B</li></ul><p>Footer note</p>"


def test_to_html_empty():
    assert DevOpsClient._to_html("") == ""
    assert DevOpsClient._to_html(None) is None
