"""Tests for template_service functions."""

import os
import tempfile

import pytest
import yaml

from src.template_service import (
    load_template,
    expand_parameterized,
    expand_parameterized_stories,
    expand_all_features,
    validate_template,
    count_work_items,

    apply_instance_overrides,
    exclude_features,
    slugify,
    save_yaml,
    lint_yaml,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def minimal_data():
    """Minimal valid project data."""
    return {
        "epics": [{
            "title": "E1",
            "features": [{
                "title": "F1",
                "stories": [{
                    "title": "S1",
                    "description": "desc",
                    "acceptance_criteria": "ac",
                    "tasks": [{
                        "title": "T1",
                        "estimate": 4,
                    }],
                }],
            }],
        }],
    }


@pytest.fixture
def parameterized_data():
    """Data with a parameterized feature."""
    return {
        "epics": [{
            "title": "E",
            "features": [{
                "title": "Data Source Integration - {{name}}",
                "description": "Integrate {{name}}",
                "parameterized": True,
                "default_instances": ["SAP", "SharePoint"],
                "stories": [{
                    "title": "Ingest",
                    "description": "Ingest {{name}} data",
                    "acceptance_criteria": "ac",
                    "tasks": [{"title": "Connect", "estimate": 4, "description": ""}],
                }],
            }],
        }],
    }

@pytest.fixture
def parameterized_stories_data():
    """Data with parameterized stories inside a non-parameterized feature."""
    return {
        "epics": [{
            "title": "E",
            "features": [{
                "title": "Data Modeling Layer",
                "optional": True,
                "description": "Transform and model data.",
                "stories": [
                    {
                        "title": "Dimension - {{ name }}",
                        "parameterized": True,
                        "instance_key": "Dimension",
                        "default_instances": ["Calendar", "Customer", "Product"],
                        "story_points": 3,
                        "description": "Implement a {{ name }} Dimension.",
                        "acceptance_criteria": "ac",
                    },
                    {
                        "title": "Fact - {{ name }}",
                        "parameterized": True,
                        "instance_key": "Fact",
                        "default_instances": ["Sales"],
                        "story_points": 5,
                        "description": "Implement a {{ name }} Fact table.",
                        "acceptance_criteria": "ac",
                    },
                ],
            }],
        }],
    }

# ── load / save ───────────────────────────────────────────────────────────────

def test_load_and_save_roundtrip(minimal_data):
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        yaml.dump(minimal_data, f)
        path = f.name
    try:
        loaded = load_template(path)
        assert loaded["epics"][0]["title"] == "E1"

        out_path = path + ".out.yaml"
        save_yaml(loaded, out_path)
        reloaded = load_template(out_path)
        assert reloaded == loaded
        os.unlink(out_path)
    finally:
        os.unlink(path)


# ── expand ────────────────────────────────────────────────────────────────────

def test_expand_parameterized_creates_instances():
    feat = {
        "title": "Data Source Integration - {{name}}",
        "description": "Integrate {{name}}",
        "parameterized": True,
        "default_instances": ["SAP", "SF"],
        "stories": [{"title": "S", "description": "d {{name}}"}],
    }
    result = expand_parameterized(feat)
    assert len(result) == 2
    assert result[0]["title"] == "Data Source Integration - SAP"
    assert result[1]["title"] == "Data Source Integration - SF"
    assert "{{name}}" not in result[0]["stories"][0]["description"]


def test_expand_non_parameterized_passes_through():
    feat = {"title": "Plain", "stories": []}
    result = expand_parameterized(feat)
    assert result == [feat]


def test_expand_all_features_in_place(parameterized_data):
    expand_all_features(parameterized_data)
    features = parameterized_data["epics"][0]["features"]
    assert len(features) == 2
    assert features[0]["title"] == "Data Source Integration - SAP"


# ── parameterized stories ───────────────────────────────────────────────────────

def test_expand_parameterized_stories_creates_instances():
    feat = {
        "title": "Data Modeling Layer",
        "stories": [
            {
                "title": "Dimension - {{ name }}",
                "parameterized": True,
                "instance_key": "Dimension",
                "default_instances": ["Calendar", "Customer", "Product"],
                "description": "Build {{ name }} dim.",
                "acceptance_criteria": "ac",
                "story_points": 3,
            },
            {
                "title": "Fact - {{ name }}",
                "parameterized": True,
                "instance_key": "Fact",
                "default_instances": ["Sales"],
                "description": "Build {{ name }} fact.",
                "acceptance_criteria": "ac",
                "story_points": 5,
            },
        ],
    }
    result = expand_parameterized_stories(feat)
    titles = [s["title"] for s in result["stories"]]
    assert titles == [
        "Dimension - Calendar",
        "Dimension - Customer",
        "Dimension - Product",
        "Fact - Sales",
    ]
    # Verify {{name}} replaced in descriptions
    assert "Calendar" in result["stories"][0]["description"]
    assert "Customer" in result["stories"][1]["description"]
    assert "Product" in result["stories"][2]["description"]
    assert "Sales" in result["stories"][3]["description"]
    # Verify parameterized/instance_key/default_instances stripped from expanded stories
    for s in result["stories"]:
        assert "parameterized" not in s
        assert "instance_key" not in s
        assert "default_instances" not in s


def test_expand_parameterized_stories_no_param_stories():
    feat = {"title": "Plain", "stories": [{"title": "S1", "description": "d"}]}
    result = expand_parameterized_stories(feat)
    assert result is feat  # unchanged


def test_expand_all_with_parameterized_stories(parameterized_stories_data):
    expand_all_features(parameterized_stories_data)
    feat = parameterized_stories_data["epics"][0]["features"][0]
    titles = [s["title"] for s in feat["stories"]]
    assert titles == [
        "Dimension - Calendar",
        "Dimension - Customer",
        "Dimension - Product",
        "Fact - Sales",
    ]
    # All stories should have parameterized fields stripped
    for s in feat["stories"]:
        assert "parameterized" not in s
        assert "instance_key" not in s
        assert "default_instances" not in s


# ── instance overrides ────────────────────────────────────────────────────────

def test_apply_instance_overrides(parameterized_data):
    overrides = {"Data Source Integration": ["Dynamics365"]}
    apply_instance_overrides(parameterized_data, overrides)
    feat = parameterized_data["epics"][0]["features"][0]
    assert feat["default_instances"] == ["Dynamics365"]


def test_apply_story_instance_overrides_dot_notation(parameterized_stories_data):
    overrides = {
        "Data Modeling Layer.Dimension": ["Supplier", "Region"],
        "Data Modeling Layer.Fact": ["Inventory"],
    }
    apply_instance_overrides(parameterized_stories_data, overrides)
    stories = parameterized_stories_data["epics"][0]["features"][0]["stories"]
    dim_story = next(s for s in stories if s.get("instance_key") == "Dimension")
    fact_story = next(s for s in stories if s.get("instance_key") == "Fact")
    assert dim_story["default_instances"] == ["Supplier", "Region"]
    assert fact_story["default_instances"] == ["Inventory"]


# ── exclude ───────────────────────────────────────────────────────────────────

def test_exclude_features():
    data = {"epics": [{"features": [
        {"title": "Infrastructure"},
        {"title": "Data Source Integration - SAP"},
        {"title": "Presentation Layer - Report"},
    ]}]}
    exclude_features(data, ["Data Source Integration", "Presentation Layer"])
    titles = [f["title"] for f in data["epics"][0]["features"]]
    assert titles == ["Infrastructure"]


# ── validate ──────────────────────────────────────────────────────────────────

def test_validate_valid_template(minimal_data):
    assert validate_template(minimal_data) == []


def test_validate_missing_epic_title():
    data = {"epics": [{"title": "", "features": []}]}
    errors = validate_template(data)
    assert any("missing title" in e for e in errors)


def test_validate_missing_story_fields():
    data = {"epics": [{"title": "E", "features": [{"title": "F", "stories": [
        {"title": "S", "description": "", "acceptance_criteria": ""},
    ]}]}]}
    errors = validate_template(data)
    assert len(errors) >= 2  # missing description and acceptance_criteria


# ── count ─────────────────────────────────────────────────────────────────────

def test_count_work_items(minimal_data):
    e, f, s, t = count_work_items(minimal_data)
    assert (e, f, s, t) == (1, 1, 1, 1)


# ── slugify ───────────────────────────────────────────────────────────────────

def test_slugify():
    assert slugify("Acme Data Platform") == "acme-data-platform"
    assert slugify("My Project!!!") == "my-project"
    assert slugify("  spaces  and---dashes  ") == "spaces-and-dashes"


# ── lint ──────────────────────────────────────────────────────────────────────

def test_lint_valid_yaml(minimal_data):
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        yaml.dump(minimal_data, f, default_flow_style=False)
        path = f.name
    try:
        ok, msgs = lint_yaml(path)
        assert ok is True
    finally:
        os.unlink(path)
