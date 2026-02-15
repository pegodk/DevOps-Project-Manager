"""
Template service for YAML project template operations.

Handles loading, expanding, validating, linting, and saving
YAML project templates used by the project-designer skill.
"""

import os
import re

import yaml
from io import StringIO
from yamllint import linter
from yamllint.config import YamlLintConfig


# ---------------------------------------------------------------------------
# Custom YAML representer for block scalars
# ---------------------------------------------------------------------------

class _BlockStyleDumper(yaml.Dumper):
    """Custom YAML dumper that uses block scalars for multi-line strings.

    Strings containing bullet points (•) or numbered lists use literal
    block scalar (|) to preserve line breaks exactly.  Other multi-line
    strings use folded block scalar (>) for nicer wrapping.  Short
    single-line strings are emitted as plain scalars.
    """
    pass


def _str_representer(dumper: yaml.Dumper, data: str):
    """Choose the best YAML scalar style for *data*."""
    if "\n" in data:
        # Acceptance criteria / descriptions with bullets → literal (|)
        if "•" in data or re.search(r"^\d+\.", data, re.MULTILINE):
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
        # Other multi-line prose → folded (>)
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=">")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_BlockStyleDumper.add_representer(str, _str_representer)


# ---------------------------------------------------------------------------
# YAML loading and saving
# ---------------------------------------------------------------------------

def load_template(yaml_path):
    """Load and parse a YAML template file."""
    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_yaml(data, output_path):
    """Save the processed YAML data to a file (excludes the 'template' metadata block)."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    output_data = {k: v for k, v in data.items() if k != "template"}
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(output_data, f, Dumper=_BlockStyleDumper,
                  default_flow_style=False, allow_unicode=True,
                  sort_keys=False, width=120)
    return output_path


# ---------------------------------------------------------------------------
# Parameterized feature expansion
# ---------------------------------------------------------------------------

def _replace_name(text, instance_name):
    """Replace {{name}} and {{ name }} in text with instance_name."""
    if not text:
        return text
    return text.replace("{{name}}", instance_name).replace("{{ name }}", instance_name)


def expand_parameterized(feature):
    """
    If a feature is parameterized, expand it into multiple features
    by replacing {{name}} in titles/descriptions with each instance name.
    Returns a list of features (1 if not parameterized, N if parameterized).
    """
    if not feature.get("parameterized"):
        return [feature]

    instances = feature.get("default_instances", [])
    if not instances:
        return [feature]

    expanded = []
    for instance_name in instances:
        feat_copy = {
            "title": _replace_name(feature["title"], instance_name),
            "description": _replace_name(feature.get("description") or "", instance_name),
            "stories": [],
        }
        for story in feature.get("stories", []):
            story_copy = dict(story)
            story_copy["title"] = story["title"]
            story_copy["description"] = _replace_name(story.get("description") or "", instance_name)
            if "tasks" in story:
                story_copy["tasks"] = [
                    {
                        **task,
                        "description": _replace_name(task.get("description") or "", instance_name),
                    }
                    for task in story["tasks"]
                ]
            feat_copy["stories"].append(story_copy)
        expanded.append(feat_copy)
    return expanded


def expand_parameterized_stories(feature):
    """
    Expand parameterized stories within a feature.

    Stories marked with ``parameterized: true`` are duplicated for each entry
    in their ``default_instances`` list, replacing ``{{name}}`` / ``{{ name }}``
    in titles, descriptions, and task descriptions.  Non-parameterized stories
    are kept as-is.

    Returns a new feature dict with the expanded stories list.
    """
    stories = feature.get("stories", [])
    has_param_stories = any(s.get("parameterized") for s in stories)
    if not has_param_stories:
        return feature

    feat_copy = dict(feature)
    new_stories = []
    for story in stories:
        if not story.get("parameterized"):
            new_stories.append(story)
            continue

        instances = story.get("default_instances", [])
        if not instances:
            new_stories.append(story)  # keep template as fallback
            continue

        for instance_name in instances:
            s_copy = {k: v for k, v in story.items()
                      if k not in ("parameterized", "default_instances", "instance_key")}
            s_copy["title"] = _replace_name(story["title"], instance_name)
            s_copy["description"] = _replace_name(story.get("description") or "", instance_name)
            if "acceptance_criteria" in story:
                s_copy["acceptance_criteria"] = _replace_name(
                    story["acceptance_criteria"], instance_name)
            if "tasks" in story:
                s_copy["tasks"] = [
                    {
                        **task,
                        "description": _replace_name(task.get("description") or "", instance_name),
                    }
                    for task in story["tasks"]
                ]
            new_stories.append(s_copy)

    feat_copy["stories"] = new_stories
    return feat_copy


def expand_all_features(data):
    """Expand all parameterized features and stories in place and return the data."""
    for epic in data.get("epics", []):
        new_features = []
        for feature in epic.get("features", []):
            # First expand parameterized stories within the feature
            feature = expand_parameterized_stories(feature)
            # Then expand feature-level parameterization
            new_features.extend(expand_parameterized(feature))
        epic["features"] = new_features
    return data


# ---------------------------------------------------------------------------
# Instance overrides and feature exclusion
# ---------------------------------------------------------------------------

def parse_instance_overrides(raw_list):
    """Parse --instances args like 'Integration=SAP,Salesforce' into a dict."""
    overrides = {}
    for item in (raw_list or []):
        if "=" not in item:
            continue
        key, val = item.split("=", 1)
        overrides[key.strip()] = [v.strip() for v in val.split(",")]
    return overrides


def apply_instance_overrides(data, overrides):
    """
    Apply instance overrides to parameterized features and stories.

    Supports two key formats:
      - Feature-level:  ``"Data Source Integration"="SAP,Salesforce"``
      - Story-level:    ``"Data Modeling Layer.Dimension"="Customer,Product"``

    Story-level keys use dot notation: ``FeatureKeyword.StoryKeyword``.
    The story keyword is matched against the ``instance_key`` field on
    parameterized stories, or against the story title if no key is set.
    """
    for epic in data.get("epics", []):
        for feat in epic.get("features", []):
            for keyword, instances in overrides.items():
                if "." in keyword:
                    # Story-level override: "Feature.StoryKey"="val1,val2"
                    feat_kw, story_kw = keyword.split(".", 1)
                    if feat_kw.lower() not in feat.get("title", "").lower():
                        continue
                    for story in feat.get("stories", []):
                        if not story.get("parameterized"):
                            continue
                        match_field = story.get("instance_key", story.get("title", ""))
                        if story_kw.lower() in match_field.lower():
                            story["default_instances"] = instances
                else:
                    # Feature-level override (existing behaviour)
                    if not feat.get("parameterized"):
                        continue
                    if keyword.lower() in feat["title"].lower():
                        feat["default_instances"] = instances


def exclude_features(data, keywords):
    """Remove features whose titles contain any of the given keywords."""
    if not keywords:
        return
    for epic in data.get("epics", []):
        epic["features"] = [
            f for f in epic.get("features", [])
            if not any(kw.lower() in f.get("title", "").lower() for kw in keywords)
        ]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_template(data):
    """Validate the YAML template structure. Returns list of error strings."""
    errors = []

    if "epics" not in data or not data["epics"]:
        errors.append("Template must contain at least one epic.")
        return errors

    for i, epic in enumerate(data["epics"]):
        if not epic.get("title"):
            errors.append(f"Epic {i+1}: missing title.")
        for j, feat in enumerate(epic.get("features", [])):
            if not feat.get("title"):
                errors.append(f"Epic {i+1}, Feature {j+1}: missing title.")
            for k, story in enumerate(feat.get("stories", [])):
                if not story.get("title"):
                    errors.append(f"Feature '{feat.get('title', j+1)}', Story {k+1}: missing title.")
                if not story.get("description"):
                    errors.append(f"Story '{story.get('title', k+1)}': missing description.")
                if not story.get("acceptance_criteria"):
                    errors.append(f"Story '{story.get('title', k+1)}': missing acceptance_criteria.")
                for m, task in enumerate(story.get("tasks", [])):
                    if not task.get("title"):
                        errors.append(f"Story '{story.get('title', k+1)}', Task {m+1}: missing title.")
                    if not task.get("estimate"):
                        errors.append(f"Task '{task.get('title', m+1)}': missing estimate.")
    return errors


# ---------------------------------------------------------------------------
# Linting
# ---------------------------------------------------------------------------

def lint_yaml(file_path):
    """
    Lint a YAML file using yamllint.

    Uses a relaxed config suitable for machine-generated YAML (long lines
    allowed, comments-indentation disabled).

    Returns:
        Tuple (ok: bool, messages: list[str]).
    """
    config = YamlLintConfig(
        "extends: default\n"
        "rules:\n"
        "  line-length:\n"
        "    max: 250\n"
        "  indentation:\n"
        "    spaces: consistent\n"
        "    indent-sequences: whatever\n"
        "  comments-indentation: disable\n"
        "  document-start: disable\n"
        "  truthy: disable\n"
    )
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    problems = list(linter.run(content, config, filepath=file_path))
    messages = [f"  {p.line}:{p.column} [{p.level}] {p.message} ({p.rule})" for p in problems]
    errors = [p for p in problems if p.level == "error"]
    return len(errors) == 0, messages


# ---------------------------------------------------------------------------
# Counting and utilities
# ---------------------------------------------------------------------------

def count_work_items(data):
    """Count epics, features, stories, and tasks in the YAML data."""
    epics = 0
    features = 0
    stories = 0
    tasks = 0
    for epic in data.get("epics", []):
        epics += 1
        for feat in epic.get("features", []):
            features += 1
            for story in feat.get("stories", []):
                stories += 1
                tasks += len(story.get("tasks", []))
    return epics, features, stories, tasks


def slugify(name):
    """Convert a project name to a filename-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug
