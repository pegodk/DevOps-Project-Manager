# YAML Template Guide

Detailed reference for YAML project template structure, parameterized features,
optional features, and YAML anchors.

## Template Structure

Templates use a nested hierarchy that mirrors the Epic → Feature → Story → Task
relationship. Parent-child links are derived from nesting (no manual parent
references needed in the YAML).

```yaml
template:
  name: template-name
  description: Template description
  version: "1.0"

epics:
  - title: "Epic Title"
    description: "Epic description"
    features:
      - title: "Feature Title"
        description: "Feature description"
        stories:
          - title: "Story Title"
            story_points: 3
            description: "As a ..., I want ..., so that ..."
            acceptance_criteria: |
              • Criterion 1
              • Criterion 2
            tasks:                    # optional
              - title: "Task Title"
                estimate: 4
                description: "Task description"
```

## Required Fields

| Level | Required Fields |
|-------|----------------|
| Epic | `title`, `description` |
| Feature | `title`, `description` |
| User Story | `title`, `description`, `story_points`, `acceptance_criteria` |
| Task | `title`, `description`, `estimate` |

## Parameterized Features

Features marked with `parameterized: true` are templates that get duplicated per
instance. The `{{name}}` placeholder in titles and descriptions is replaced with
each instance name from the `default_instances` list.

```yaml
- title: "Data Source Integration - {{name}}"
  parameterized: true
  default_instances:
    - "365 Business Central"
    - "365 CRM"
  stories: [...]
```

When the user specifies different source systems, override `default_instances`
accordingly. The feature and all its child stories are duplicated for each instance.

### Expansion Logic

The `generate_project_yaml.py` script expands parameterized features by duplicating
them for each instance, replacing `{{name}}` in titles and descriptions.

For parameterized features, the parent reference in all child stories uses the
**resolved** feature title (e.g., "Data Source Integration - 365 Business Central",
not "Data Source Integration - {{name}}").

## Parameterized Stories

Some features contain parameterized stories with an `instance_key` field. These
are duplicated per instance within their parent feature.

```yaml
- title: "Dimension - {{ name }}"
  parameterized: true
  instance_key: Dimension
  default_instances:
    - "Customer"
    - "Product"
  story_points: 3
```

Override with dot notation: `"Data Modeling Layer.Dimension"="Customer,Product,Supplier"`

## Optional Features

Features marked with `optional: true` are included by default but may be removed
if the user confirms they are out of scope.

```yaml
- title: "Firm Foundation"
  optional: true
  description: "..."
```

If the user says a phase is out of scope, use the `--exclude` flag to remove
the entire feature (and its child stories and tasks) from the generated output.

## YAML Anchors

Templates may use YAML anchors (`&name`) and aliases (`*name`) to avoid repeating
identical acceptance criteria across multiple stories.

```yaml
- title: "Dimension - {{ name }}"
  parameterized: true
  instance_key: Dimension
  default_instances: ["Calendar", "Customer", "Product"]
  acceptance_criteria: &curated_model_criteria |
    • Business requirements gathered...
    • Source-to-target mapping documented...

- title: "Fact - {{ name }}"
  acceptance_criteria: *curated_model_criteria
```

## Feature Flags Summary

| Flag | Values | Behavior |
|------|--------|----------|
| `parameterized` | `true` | Feature is duplicated per instance, `{{name}}` replaced |
| `optional` | `true` | Feature can be excluded via `--exclude` |
| `instance_key` | string | Identifies story-level parameterization group |
| `default_instances` | list | Default instance names for parameterized items |

## Available Templates

| Template | File | Description |
|----------|------|-------------|
| **project-template** | `templates/project-template.yaml` | Lakehouse data platform with 6 delivery phases: Firm Foundation, Cloud Infrastructure, Data Source Integration, Data Modeling Layer, Semantic Layer, and Presentation Layer |
