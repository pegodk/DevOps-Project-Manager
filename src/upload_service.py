"""
Upload service for Azure DevOps work item creation from YAML data.

Walks a YAML project hierarchy (epics → features → stories → tasks)
and uploads each item via BaseWorkItemService, skipping duplicates.
"""

from .devops_client import DevOpsClient


def _create_and_track(svc, wi_type, data, parent_id=None):
    """
    Create a work item via the service layer.

    Returns a result dict with keys: type, title, status, message, id.
    """
    title = data.get("title", "")
    try:
        if svc.work_item_exists(title, parent_id):
            return {"type": wi_type, "title": title, "status": "skipped",
                    "message": "Already exists", "id": None}

        result = svc.create(wi_type, data, parent_id)
        wi_id = result.get("id")
        return {"type": wi_type, "title": title, "status": "created",
                "message": f"ID: {wi_id}", "id": wi_id}
    except Exception as e:
        return {"type": wi_type, "title": title, "status": "error",
                "message": str(e), "id": None}


def _resolve_id(svc, result, title):
    """Return the ID from a create result, or look it up if the item was skipped."""
    wi_id = result.get("id")
    if wi_id is None:
        ids = svc.find_by_title(title)
        wi_id = ids[0] if ids else None
    return wi_id


def _print_result(result):
    """Print a single upload result line."""
    icon = {"created": "+", "skipped": "~", "error": "!"}.get(result["status"], "?")
    print(f"  [{icon}] {result['type']:12s} | {result['title'][:50]:50s} | {result.get('message', '')}")


def _build_data(item: dict) -> dict:
    """Build a work-item data dict from a YAML item, including only non-empty fields."""
    data: dict = {"title": item["title"]}
    for key in ("description", "acceptance_criteria"):
        if item.get(key):
            data[key] = item[key]
    for key in ("story_points", "estimate"):
        if item.get(key) is not None:
            data[key] = item[key]
    if item.get("iteration_path"):
        data["iteration_path"] = item["iteration_path"]
    return data


def upload_from_yaml(data, org, project, pat):
    """Walk the YAML hierarchy and upload all work items to Azure DevOps."""
    svc = DevOpsClient(org, project, pat)
    results = []

    for epic in data.get("epics", []):
        result = _create_and_track(svc, "Epic", _build_data(epic))
        results.append(result)
        _print_result(result)
        epic_id = _resolve_id(svc, result, epic["title"])

        for feat in epic.get("features", []):
            result = _create_and_track(svc, "Feature", _build_data(feat), epic_id)
            results.append(result)
            _print_result(result)
            feat_id = _resolve_id(svc, result, feat["title"])

            for story in feat.get("stories", []):
                result = _create_and_track(svc, "User Story", _build_data(story), feat_id)
                results.append(result)
                _print_result(result)
                story_id = _resolve_id(svc, result, story["title"])

                for task in story.get("tasks", []):
                    result = _create_and_track(svc, "Task", _build_data(task), story_id)
                    results.append(result)
                    _print_result(result)

    return results
