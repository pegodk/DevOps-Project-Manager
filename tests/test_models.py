"""Tests for Pydantic work-item models and field filtering."""

import pytest
from src.models import (
    EpicItem,
    FeatureItem,
    StoryItem,
    TaskItem,
    ProjectData,
    WORK_ITEM_MODELS,
    build_work_item_data,
)


# ── Model construction ───────────────────────────────────────────────────────

class TestEpicItem:
    def test_required_fields(self):
        epic = EpicItem(title="E1")
        assert epic.title == "E1"
        assert epic.features == []

    def test_optional_fields(self):
        epic = EpicItem(title="E1", description="desc", state="New", iteration_path="Proj\\S1")
        assert epic.description == "desc"
        assert epic.state == "New"
        assert epic.iteration_path == "Proj\\S1"

    def test_ignores_story_points_field(self):
        """Epics silently ignore story_points (extra='ignore')."""
        epic = EpicItem(title="E1", story_points=5)
        assert not hasattr(epic, "story_points")

    def test_ignores_estimate_field(self):
        """Epics silently ignore estimate (extra='ignore')."""
        epic = EpicItem(title="E1", estimate=8)
        assert not hasattr(epic, "estimate")


class TestFeatureItem:
    def test_required_fields(self):
        feat = FeatureItem(title="F1")
        assert feat.title == "F1"
        assert feat.stories == []

    def test_template_fields(self):
        feat = FeatureItem(title="F1", optional=True, parameterized=True, default_instances=["A"])
        assert feat.optional is True
        assert feat.parameterized is True
        assert feat.default_instances == ["A"]

    def test_ignores_story_points_field(self):
        """Features silently ignore story_points."""
        feat = FeatureItem(title="F1", story_points=5)
        assert not hasattr(feat, "story_points")

    def test_ignores_estimate_field(self):
        """Features silently ignore estimate."""
        feat = FeatureItem(title="F1", estimate=8)
        assert not hasattr(feat, "estimate")


class TestStoryItem:
    def test_required_fields(self):
        story = StoryItem(title="S1")
        assert story.title == "S1"
        assert story.tasks == []

    def test_story_points(self):
        story = StoryItem(title="S1", story_points=8)
        assert story.story_points == 8

    def test_acceptance_criteria(self):
        story = StoryItem(title="S1", acceptance_criteria="AC text")
        assert story.acceptance_criteria == "AC text"

    def test_ignores_estimate_field(self):
        """Stories silently ignore estimate."""
        story = StoryItem(title="S1", estimate=4)
        assert not hasattr(story, "estimate")

    def test_template_fields(self):
        story = StoryItem(title="S1", parameterized=True, instance_key="Dim", default_instances=["A"])
        assert story.parameterized is True
        assert story.instance_key == "Dim"


class TestTaskItem:
    def test_required_fields(self):
        task = TaskItem(title="T1")
        assert task.title == "T1"

    def test_estimate(self):
        task = TaskItem(title="T1", estimate=4.0)
        assert task.estimate == 4.0

    def test_ignores_story_points_field(self):
        """Tasks silently ignore story_points."""
        task = TaskItem(title="T1", story_points=5)
        assert not hasattr(task, "story_points")

    def test_ignores_acceptance_criteria_field(self):
        """Tasks silently ignore acceptance_criteria."""
        task = TaskItem(title="T1", acceptance_criteria="AC")
        assert not hasattr(task, "acceptance_criteria")


# ── ProjectData ───────────────────────────────────────────────────────────────

class TestProjectData:
    def test_full_hierarchy(self):
        data = ProjectData(epics=[
            EpicItem(title="E1", features=[
                FeatureItem(title="F1", stories=[
                    StoryItem(title="S1", story_points=5, tasks=[
                        TaskItem(title="T1", estimate=3),
                    ]),
                ]),
            ]),
        ])
        assert len(data.epics) == 1
        assert data.epics[0].features[0].stories[0].story_points == 5
        assert data.epics[0].features[0].stories[0].tasks[0].estimate == 3


# ── WORK_ITEM_MODELS lookup ──────────────────────────────────────────────────

class TestWorkItemModels:
    def test_all_types_present(self):
        assert "Epic" in WORK_ITEM_MODELS
        assert "Feature" in WORK_ITEM_MODELS
        assert "User Story" in WORK_ITEM_MODELS
        assert "Task" in WORK_ITEM_MODELS


# ── build_work_item_data ──────────────────────────────────────────────────────

class TestBuildWorkItemData:
    def test_epic_strips_story_points_and_estimate(self):
        raw = {"title": "E", "description": "d", "story_points": 5, "estimate": 8}
        result = build_work_item_data("Epic", raw)
        assert result == {"title": "E", "description": "d"}

    def test_feature_strips_story_points_and_estimate(self):
        raw = {"title": "F", "story_points": 5, "estimate": 8, "acceptance_criteria": "ac"}
        result = build_work_item_data("Feature", raw)
        assert result == {"title": "F"}

    def test_story_keeps_story_points_strips_estimate(self):
        raw = {"title": "S", "story_points": 8, "estimate": 4, "acceptance_criteria": "ac"}
        result = build_work_item_data("User Story", raw)
        assert "story_points" in result
        assert result["story_points"] == 8
        assert "acceptance_criteria" in result
        assert "estimate" not in result

    def test_task_keeps_estimate_strips_story_points(self):
        raw = {"title": "T", "estimate": 4, "story_points": 5, "acceptance_criteria": "ac"}
        result = build_work_item_data("Task", raw)
        assert "estimate" in result
        assert result["estimate"] == 4
        assert "story_points" not in result
        assert "acceptance_criteria" not in result

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown work item type"):
            build_work_item_data("Bug", {"title": "B"})

    def test_iteration_path_kept_for_all_types(self):
        raw = {"title": "X", "iteration_path": "Proj\\Sprint 1"}
        for wi_type in ("Epic", "Feature", "User Story", "Task"):
            result = build_work_item_data(wi_type, raw)
            assert result["iteration_path"] == "Proj\\Sprint 1"


# ── Integration: field filtering through DevOpsClient ─────────────────────────

class TestFieldFilteringIntegration:
    """Verify that creating work items via DevOpsClient only stores type-appropriate fields."""

    def test_epic_has_no_story_points_or_estimate(self):
        from src.devops_client import DevOpsClient
        client = DevOpsClient()
        result = client.create("Epic", {
            "title": "E", "story_points": 5, "estimate": 8,
        })
        item = client._items[result["id"]]
        assert "story_points" not in item
        assert "estimate" not in item

    def test_feature_has_no_story_points_or_estimate(self):
        from src.devops_client import DevOpsClient
        client = DevOpsClient()
        result = client.create("Feature", {
            "title": "F", "story_points": 5, "estimate": 8,
        })
        item = client._items[result["id"]]
        assert "story_points" not in item
        assert "estimate" not in item

    def test_story_has_story_points_no_estimate(self):
        from src.devops_client import DevOpsClient
        client = DevOpsClient()
        result = client.create("User Story", {
            "title": "S", "story_points": 5, "estimate": 8,
            "acceptance_criteria": "AC",
        })
        item = client._items[result["id"]]
        assert item.get("story_points") == 5
        assert item.get("acceptance_criteria") == "AC"
        assert "estimate" not in item

    def test_task_has_estimate_no_story_points(self):
        from src.devops_client import DevOpsClient
        client = DevOpsClient()
        result = client.create("Task", {
            "title": "T", "estimate": 4, "story_points": 5,
        })
        item = client._items[result["id"]]
        assert item.get("estimate") == 4
        assert "story_points" not in item
