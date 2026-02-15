"""
Pydantic models for Azure DevOps work item types.

Each model enforces the correct fields per work-item level:

* **Epic** and **Feature** carry only common fields (title, description,
  state, iteration_path).  They never have ``story_points`` or ``estimate``.
* **Story** (User Story) adds ``story_points`` and ``acceptance_criteria``
  but never ``estimate``.
* **Task** adds ``estimate`` (hours) but never ``story_points`` or
  ``acceptance_criteria``.

Template-specific metadata (``optional``, ``parameterized``,
``default_instances``, ``instance_key``) lives on Feature and Story models
so YAML templates can be loaded directly into the hierarchy.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Work-item models
# ---------------------------------------------------------------------------

class TaskItem(BaseModel):
    """A Task work item — the lowest level in the hierarchy.

    Tasks have an ``estimate`` (effort in hours) but never ``story_points``.
    """

    title: str
    description: Optional[str] = None
    estimate: Optional[float] = None
    id: Optional[int] = None
    state: Optional[str] = None
    iteration_path: Optional[str] = None


class StoryItem(BaseModel):
    """A User Story work item.

    Stories carry ``story_points`` and ``acceptance_criteria`` but never
    an ``estimate``.
    """

    title: str
    description: Optional[str] = None
    story_points: Optional[float] = None
    acceptance_criteria: Optional[str] = None
    id: Optional[int] = None
    state: Optional[str] = None
    iteration_path: Optional[str] = None
    tasks: list[TaskItem] = []

    # Template-specific fields (used during expansion, stripped before upload)
    parameterized: Optional[bool] = None
    instance_key: Optional[str] = None
    default_instances: Optional[list[str]] = None


class FeatureItem(BaseModel):
    """A Feature work item.

    Features have neither ``story_points`` nor ``estimate``.
    """

    title: str
    description: Optional[str] = None
    id: Optional[int] = None
    state: Optional[str] = None
    iteration_path: Optional[str] = None
    stories: list[StoryItem] = []

    # Template-specific fields
    optional: Optional[bool] = None
    parameterized: Optional[bool] = None
    default_instances: Optional[list[str]] = None


class EpicItem(BaseModel):
    """An Epic work item — the top level of the hierarchy.

    Epics have neither ``story_points`` nor ``estimate``.
    """

    title: str
    description: Optional[str] = None
    id: Optional[int] = None
    state: Optional[str] = None
    iteration_path: Optional[str] = None
    features: list[FeatureItem] = []


class ProjectData(BaseModel):
    """Root container for the project YAML structure."""

    epics: list[EpicItem]
    template: Optional[dict] = None


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

#: Map Azure DevOps type name → Pydantic model class.
WORK_ITEM_MODELS: dict[str, type[BaseModel]] = {
    "Epic": EpicItem,
    "Feature": FeatureItem,
    "User Story": StoryItem,
    "Task": TaskItem,
}

#: Fields that may appear in an API data dict for each work-item type.
#: Used by ``build_work_item_data`` to strip invalid keys.
_ALLOWED_DATA_FIELDS: dict[str, set[str]] = {
    "Epic": {"title", "description", "iteration_path"},
    "Feature": {"title", "description", "iteration_path"},
    "User Story": {
        "title", "description", "acceptance_criteria",
        "story_points", "iteration_path",
    },
    "Task": {"title", "description", "estimate", "iteration_path"},
}


def build_work_item_data(work_item_type: str, data: dict) -> dict:
    """Return a copy of *data* containing only the fields valid for *work_item_type*.

    Unknown / type-inappropriate keys are silently dropped.  This is the
    single gatekeeper used by the DevOps client and upload service before
    creating work items.
    """
    allowed = _ALLOWED_DATA_FIELDS.get(work_item_type)
    if allowed is None:
        raise ValueError(f"Unknown work item type: {work_item_type}")
    return {k: v for k, v in data.items() if k in allowed}
