---
name: project-designer
description: >
  Design and upload Azure DevOps project structures with complete work item
  hierarchies (Epics, Features, User Stories, Tasks) using YAML project
  templates. Use when user asks to "design a project", "create a project plan",
  "scaffold work items", "upload to Azure DevOps", "plan a sprint", "query
  project status", or "validate project structure". Also use when user mentions
  "data platform project", "lakehouse project", or "DevOps board setup".
  Do NOT use for general Azure DevOps questions unrelated to work item
  hierarchies, or for CI/CD pipeline configuration.
---

# Project Designer

## Critical Instructions

- **Interpret Intent**: Accurately capture user intent for project structure design. Ask clarifying questions if the domain, scale, or deliverables are unclear.
- **YAML Source of Truth**: Project templates are defined as YAML files in `templates/`. The pipeline validates the YAML, expands parameterized features, saves a customized YAML to `data/`, and uploads work items to Azure DevOps.
- **Parent Matching**: Parent references must be **exact title string matches** — the upload tool uses title matching to establish parent-child links.
- **Always Generate Before Showing**: Use the `generate_project` MCP tool before presenting the hierarchy to the user. Never present a plan without a generated YAML backing it.
- **Validate Before Upload**: Always use `validate_connection` before uploading work items. If validation fails, fix issues before proceeding.
- **Use MCP Tools**: All operations (generate, upload, query) are performed via the MCP server tools. Do **not** run Python scripts from the terminal. Never run custom code (e.g. `python -c "..."`) to perform Azure DevOps operations — always use the corresponding MCP tool instead. If a tool is missing or insufficient, add or extend one first.

## Core Responsibilities

1. **Requirements Gathering**: Understand project domain, scale, team, and deliverables
2. **Hierarchy Design**: Create complete Epic → Feature → User Story → Task hierarchies
3. **Generation Pipeline**: Validate YAML → expand parameters → save customized YAML → lint via `generate_project` MCP tool
4. **Upload Pipeline**: Validate connection → upload to Azure DevOps via `upload_from_template` MCP tool
5. **Project Querying**: Connect to Azure DevOps to read and analyze existing project structures via `get_project_status` MCP tool
6. **Quality Assurance**: Ensure cross-cutting concerns (testing, docs, security, governance) are covered

## Core Principles

- **Language**: Use **Python** for all code. Dependencies: PyYAML, requests, python-dotenv, mcp.
- **Work Item Quality**: Every User Story must have acceptance criteria. Every Task must have an effort estimate. Every hierarchy link must use exact title matching.

## MCP Tools

All operations are performed through the Azure DevOps Project Manager MCP server.
The tools are prefixed with `mcp_devops-projec_` when invoked.

| Category | MCP Tool | Description |
|----------|----------|-------------|
| **Generation** | `generate_project` | Generate a customized YAML from a template (load → override → exclude → expand → validate → save → lint) |
| **Upload** | `upload_from_template` | Bulk-upload work items from a generated YAML file to Azure DevOps |
| **Upload** | `validate_connection` | Test the Azure DevOps connection before uploading |
| **Query** | `get_project_status` | Retrieve the full work-item hierarchy tree and summary stats from Azure DevOps |
| **Query** | `get_work_item` | Get a single work item by ID |
| **Query** | `search_work_items` | Search for work items by exact title |
| **Query** | `run_wiql_query` | Run a raw WIQL query against Azure DevOps |
| **Query** | `get_iterations` | List all iterations (sprints) with id, identifier, name, path, and dates |
| **Modify** | `create_new_backlog` | Create a single work item (Epic, Feature, User Story, or Task) |
| **Modify** | `update_existing_item` | Update a work item's title, description, or state |
| **Modify** | `create_iteration` | Create a new iteration (sprint) with optional dates; auto-subscribes to team |
| **Modify** | `update_iteration` | Rename an iteration and/or update its start/finish dates |
| **Modify** | `subscribe_iterations` | Subscribe all iterations to the default team so they appear on the board |
| **Context** | `read_file` | Read documentation for naming conventions, DevOps processes, and architecture patterns |
| **Context** | `semantic_search` | Search the codebase for relevant patterns and examples |
| **Context** | `grep_search` | Find specific patterns in existing templates or code |
| **Context** | `file_search` | Locate existing YAML templates |

## Requirements Gathering

**When to use**: User asks to "design", "create", "plan", or "scaffold" a project.

Follow this **three-step** flow. Do not proceed to the next step until the current
step is confirmed.

**Important**: Always use the `ask_questions` tool for **every** step — including
the project name and template selection. Never fall back to plain-text questions
in the chat. The interactive prompt ensures consistent UX and prevents skipped
inputs.

### Step 1: Project Name

Use the `ask_questions` tool with `allowFreeformInput: true` (no predefined options)
to ask the user for the **project name**. This becomes the epic title and the output
filename. Examples: "Data Platform - Phase 1", "Customer Analytics Platform".

### Step 2: Template Selection

Use the `ask_questions` tool to list the available templates from `templates/` as
selectable options and ask the user to pick one. Read the chosen YAML template to
discover its features, including which are `optional` and which are `parameterized`.

| Template | File | Description |
|----------|------|-------------|
| **project-template** | `templates/project-template.yaml` | Lakehouse data platform with 7 delivery phases. Features support `parameterized` and `optional` flags. |

> When new templates are added to `templates/`, add them to this table.

### Step 3: Scope & Parameterize Features

After loading the template, **use the `ask_questions` tool** to present interactive
prompts to the user. **Never** list features as plain text — always use the
interactive multi-select and free-text input capabilities.

Structure the prompts as follows:

1. **Feature selection** (multi-select with `recommended: true` on all):
   List every feature from the template as a selectable option with its description.
   All features are pre-selected; the user deselects any they want to exclude.
   Collect deselected features for the `exclude` parameter.

2. **Parameterized instances** (one question per parameterized feature, with
   `allowFreeformInput: true`): For each parameterized feature that is included,
   show `default_instances` from the template as selectable options and allow the
   user to type additional instance names. Collect selections for the dedicated
   parameters (`datasources`, `semantic_models`, `visualizations`).

3. **Parameterized stories** (one question per parameterized story group, with
   `allowFreeformInput: true`): Some features contain parameterized stories
   (e.g. Data Modeling Layer has Dimension and Fact story templates). For each
   parameterized story that is in scope, show its `default_instances` as
   selectable options and allow the user to type additional names. Map answers
   to `dimensions` and `facts` parameters.

Batch related questions into a single `ask_questions` call (max 4 questions per
call). Use short `header` labels (max 12 chars) and clear `question` text.

### Mapping Inputs to MCP Tool Parameters

Once scope is confirmed, map the answers to `generate_project` MCP tool parameters:

| Input | Parameter | Example |
|-------|-----------|---------|
| Project name | `name` | `"Data Platform - Phase 1"` |
| Template file | `template_path` | `"templates/project-template.yaml"` |
| Excluded optional features | `exclude` | `["Semantic Layer", "Presentation Layer"]` |
| Data source systems | `datasources` | `["SAP", "Salesforce"]` |
| Dimension tables | `dimensions` | `["Customer", "Product"]` |
| Fact tables | `facts` | `["Sales", "Inventory"]` |
| Semantic model instances | `semantic_models` | `["Supply Chain", "Finance"]` |
| Presentation instances | `visualizations` | `["Customer Insights"]` |

## Hierarchy Design

### Work Item Structure

#### Epics
- Represent major project initiatives or themes
- Title format: Clear, business-oriented name (e.g., "Data Ingestion Pipeline", "User Authentication System")
- Include a concise description of the epic's scope and business value

#### Features
- Break down each Epic into 2-6 Features
- Title format: Specific capability or component (e.g., "SAP Data Connector", "OAuth2 Integration")
- Each Feature must reference its parent Epic by **exact title**

#### User Stories
- Break down each Feature into 2-8 User Stories
- Title format: `[Domain/Component] - Brief description`
- Description format: "As a [role], I want [capability], so that [benefit]"
- Include acceptance criteria for each story
- Assign story points (1, 2, 3, 5, 8, 13) based on complexity
- Each User Story must reference its parent Feature by **exact title**

#### Tasks
- Break down each User Story into 2-6 Tasks
- Title format: `[Component] - Specific action` (e.g., "[API] - Implement authentication middleware")
- Task types: Development, Testing, Documentation, Infrastructure, Data Quality, Code Review
- Include effort estimates in hours (1, 2, 4, 8, 16)
- Each Task must reference its parent User Story by **exact title**

### Quality Rules
- Include at least one Documentation task per Feature
- Include at least one Testing-related User Story per Feature
- Consider cross-cutting concerns: security, monitoring, documentation, and testing
- User Story descriptions must always follow "As a... I want... So that..." format

## Iteration (Sprint) Management

### Naming Convention

Iterations must follow the format: **`Sprint <N> (W<start>-<end>)`** where `<start>` and `<end>` are ISO week numbers covered by the sprint.

Examples:
- `Sprint 1 (W9-11)` — 3-week sprint covering weeks 9 through 11
- `Sprint 2 (W12-14)` — next 3-week sprint

### Creating Iterations

When the user asks to set up sprints:

1. **Ask** for sprint duration (default: 3 weeks), start week, and number of sprints.
2. **Create** each iteration using the `create_iteration` MCP tool with `name`, `start_date`, and `finish_date`.
3. **Name** each sprint using the `Sprint <N> (W<start>-<end>)` format.
4. **Dates**: Each sprint starts on a Monday and ends on a Sunday. Sprints are contiguous (no gaps).

### Updating Iterations

Use the `update_iteration` MCP tool to rename or set dates. Dates must be in ISO-8601 format (e.g. `2026-02-23`).

### Subscribing Iterations

After creating iterations, use `subscribe_iterations` to ensure they appear on the Azure Board.

## Generation & Upload Pipeline

### Generate Project

Use the `generate_project` MCP tool to produce a customized, expanded YAML.

**Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `template_path` | Yes | Path to YAML template (e.g. `templates/project-template.yaml`) |
| `name` | No | Project name (overrides the epic title) |
| `datasources` | No | List of data source system names |
| `dimensions` | No | List of dimension table names |
| `facts` | No | List of fact table names |
| `semantic_models` | No | List of semantic model instance names |
| `visualizations` | No | List of presentation layer instance names |
| `exclude` | No | List of feature keywords to exclude |
| `output_path` | No | Custom output path (default: `data/<project-name>.yaml`) |

#### Generation Steps

1. **Load** the YAML template and apply `name` override
2. **Apply** instance overrides from dedicated parameters
3. **Exclude** optional features if `exclude` is specified
4. **Expand** parameterized stories, then parameterized features into concrete instances
5. **Validate** structure (titles, descriptions, acceptance criteria, estimates)
6. **Save** to `data/<project-name>.yaml`
7. **Lint** with yamllint

The tool returns the full hierarchy tree and summary in its response.

### Upload to Azure DevOps

Use the `upload_from_template` MCP tool to upload a generated YAML:

**Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `yaml_path` | Yes | Path to the generated YAML file |

#### Upload Steps

1. **Load** the generated YAML and validate structure
2. **Expand** any remaining parameterized features (safe on pre-expanded YAML)
3. **Upload** each work item, skipping duplicates

### Workflow

1. Generate the expanded YAML using the `generate_project` MCP tool (always generate before asking for feedback — the tool returns the hierarchy tree)
2. Apply any requested changes directly on the generated YAML file in `data/`
3. Use `validate_connection` to verify the Azure DevOps connection
4. Use `upload_from_template` with the generated file to upload
5. Confirm work item counts and check Azure DevOps

## Querying Existing Projects

**When to use**: User asks to "query", "read", "show", "analyze", "validate", or
"inspect" an existing Azure DevOps project's work items.

### The get_project_status Tool

The `get_project_status` MCP tool connects to Azure DevOps and retrieves
the full work item hierarchy (Epics, Features, User Stories, Tasks).

**Prerequisites**: The user must have a `.env` file with required environment variables:
- `AZURE_DEVOPS_ORG_NAME`
- `AZURE_DEVOPS_PROJECT_NAME`
- `AZURE_DEVOPS_PERSONAL_ACCESS_TOKEN`
- `AZURE_DEVOPS_API_VERSION` (optional, default: 7.1)

### Usage

| MCP Tool | Parameters | Use Case |
|----------|------------|----------|
| `get_project_status` | (none) | Full hierarchy tree with summary stats |
| `get_project_status` | `epic_title="My Epic"` | Filter to a single epic |
| `get_project_status` | `include_summary=False` | Tree only, no summary |

### Workflow: Analyze Then Design

A common pattern is to query an existing project, then use the output to extend it:

1. **Query** the current state using `get_project_status`
2. **Compare** with a template from `templates/` to identify gaps
3. **Design** additional work items to fill the gaps
4. **Generate** a YAML with only the new items via `generate_project` and upload via `upload_from_template`

### Workflow: Validate Against Template

Compare a live project against a template to find missing or extra items:

1. **Query** with `get_project_status`
2. **Read** the template from `templates/project-template.yaml`
3. **Diff** the two structures to identify:
   - Features/stories in the template but missing from the project
   - Items in the project not covered by the template
   - State distribution (how many items are still New vs Active vs Closed)
4. **Report** gaps and progress to the user

## Output Format

**Always show the full project structure by default** — list every Epic, Feature,
User Story, and Task. Never abbreviate or collapse sections with "..." or summary
counts. The user should see the complete hierarchy at a glance without having to
ask for details.

Use this tree format:

```
## Project: [Project Name]

### Epic 1: [Epic Title]
  ├── Feature 1.1: [Feature Title]
  │   ├── Story 1.1.1: [Story Title] (SP: X)
  │   │   ├── Task: [Task Title] (Est: Xh)
  │   │   └── Task: [Task Title] (Est: Xh)
  │   └── Story 1.1.2: [Story Title] (SP: X)
  │       ├── Task: [Task Title] (Est: Xh)
  │       └── Task: [Task Title] (Est: Xh)
  ├── Feature 1.2: [Feature Title]
  │   ├── Story 1.2.1: [Story Title] (SP: X)
  │   └── Story 1.2.2: [Story Title] (SP: X)
  └── Feature 1.3: [Feature Title]
      └── Story 1.3.1: [Story Title] (SP: X)
```

Every feature must list all of its stories. Every story must list all of its
tasks (if any). Do not use "└── ..." or similar shorthand.

After presenting the structure:
1. Confirm the design with the user
2. Use `upload_from_template` MCP tool to upload to Azure DevOps
3. Summarize with total counts of each work item type

## Project Templates

Pre-built project templates are stored as YAML files in the `templates/` directory
at the repository root. Templates provide a complete, reusable work item hierarchy
that can be customized and uploaded to Azure DevOps.

### Available Templates

| Template | File | Description |
|----------|------|-------------|
| **project-template** | `templates/project-template.yaml` | Lakehouse data platform with 6 delivery phases: Firm Foundation, Cloud Infrastructure, Data Source Integration, Data Modeling Layer, Semantic Layer, and Presentation Layer. Features support `parameterized` and `optional` flags. |

### YAML Template Structure

Templates use a nested hierarchy: Epic → Feature → Story → Task. Parent-child
links are derived from nesting. For the full schema, parameterized features,
optional features, YAML anchors, and expansion logic, consult
`references/yaml-template-guide.md`.

Key concepts:
- **Parameterized features** (`parameterized: true`): duplicated per instance, `{{name}}` replaced
- **Optional features** (`optional: true`): included by default, removable via `exclude`
- **Parameterized stories** (`instance_key`): story-level duplication within a feature
- **YAML anchors**: reuse identical acceptance criteria across stories

### Using a Template

When the user asks to use a template (e.g., "use the project-template"):

1. **Gather requirements** — follow the three-step flow in "Requirements Gathering":
   collect the project name (Step 1), select the template (Step 2), and scope
   optional/parameterized features (Step 3).
2. **Generate YAML first** — use the `generate_project` MCP tool with `name`, dedicated instance parameters (`datasources`, `dimensions`, `facts`, etc.), and `exclude` parameters to produce the expanded YAML in `data/`. **Always generate the file before asking the user for feedback.**
3. **Data Modeling Layer tables** — if the Data Modeling Layer feature is in scope, the `dimensions` and `facts` parameters control which tables are generated. The template defaults are Calendar, Customer, Product (dimensions) and Sales (facts). Each table story reuses the `curated_model_criteria` acceptance criteria. Assign story points based on complexity (1 for simple lookups like Calendar, 3 for medium, 5 for complex facts).
4. **Display** — the `generate_project` tool returns the hierarchy tree in its response. **Always present the full hierarchy to the user** — show every Feature, User Story, and Task. Never abbreviate or collapse the output. The user must see the complete structure without asking for more detail.
5. **Customize** based on feedback — apply changes (add/remove stories, adjust estimates, rename items, etc.) **directly on the generated YAML file in `data/`**. Do not re-run the generation pipeline; edit the file in place.
6. **Upload** by using the `upload_from_template` MCP tool with the generated YAML file path.
7. **Confirm** work item counts and check Azure DevOps.

### Expansion Logic (Internal)

The `generate_project` MCP tool expands parameterized features by duplicating
them for each instance, replacing `{{name}}` in titles and descriptions.

For parameterized features, the parent reference in all child stories uses the
**resolved** feature title (e.g., "Data Source Integration - 365 Business Central", not
"Data Source Integration - {{name}}").

## Examples

### Example 1: New Data Platform Project

User says: "Create a data platform project for Contoso"

Actions:
1. Ask for project name → "Contoso Data Platform"
2. Select template → `project-template`
3. Scope features → include all
4. Configure instances → Data Sources: SAP, Salesforce; Dimensions: Customer, Product; Facts: Sales, Inventory
5. Use `generate_project` MCP tool with:
   - `template_path`: `"templates/project-template.yaml"`
   - `name`: `"Contoso Data Platform"`
   - `datasources`: `["SAP", "Salesforce"]`
   - `dimensions`: `["Customer", "Product"]`
   - `facts`: `["Sales", "Inventory"]`
6. Use `validate_connection` then `upload_from_template` with `yaml_path`: `"data/contoso-data-platform.yaml"`

Result: 39+ work items uploaded, user confirms in Azure DevOps.

### Example 2: Query Existing Project

User says: "Show me the current state of our DevOps board"

Actions:
1. Use `get_project_status` MCP tool (no parameters)
2. Present counts by type and state, total story points
3. Offer to compare against template

Result: Summary statistics presented, gaps identified.

### Example 3: Extend Existing Project

User says: "Add a new Data Source Integration for SharePoint"

Actions:
1. Use `get_project_status` to view current hierarchy
2. Compare with template to find the Data Source Integration feature structure
3. Create a minimal YAML with just the new feature and its stories
4. Use `upload_from_template` with the new YAML

Result: New feature with stories added to existing project.

## Error Handling

### Common Errors and Solutions

**Error: `generate_project` returns validation errors**
- Cause: Missing required fields (title, description, acceptance_criteria) in YAML
- Solution: Check the YAML structure matches the template schema. Ensure every story has `acceptance_criteria` and every task has `estimate`.

**Error: `upload_from_template` returns 401 Unauthorized**
- Cause: Invalid or expired Personal Access Token (PAT)
- Solution: Verify `AZURE_DEVOPS_PERSONAL_ACCESS_TOKEN` in `.env`. Ensure the PAT has "Work Items (Read, Write)" scope. Regenerate if expired.

**Error: `upload_from_template` returns 404 Not Found**
- Cause: Incorrect organization or project name
- Solution: Verify `AZURE_DEVOPS_ORG_NAME` and `AZURE_DEVOPS_PROJECT_NAME` in `.env`. Check spelling matches exactly what appears in Azure DevOps URL.

**Error: Duplicate work items created**
- Cause: Re-running upload without checking for existing items
- Solution: The upload tool skips items with matching titles. If duplicates exist, delete them manually in Azure DevOps before re-uploading.

**Error: Lint warnings in generated YAML**
- Cause: Indentation or formatting problems in generated YAML
- Solution: The `generate_project` tool auto-lints. If editing the output YAML manually, ensure consistent 2-space indentation and proper YAML syntax.

**Error: Parent-child links not created**
- Cause: Title mismatch between parent reference and actual parent title
- Solution: Parent references use **exact title matching**. Verify titles match character-for-character, including spaces, hyphens, and casing.

## Troubleshooting

### Skill doesn't trigger
If this skill doesn't activate when expected, try using phrases like:
- "Design a project", "Create a project plan", "Scaffold work items"
- "Upload to Azure DevOps", "Plan a data platform project"
- "Query project status", "Validate project structure"

### Azure DevOps Connection Issues
1. Verify `.env` file exists in the project root with required variables
2. Use `validate_connection` MCP tool to test
3. Check PAT permissions: must include "Work Items (Read, Write, & Manage)"
4. If behind a proxy, ensure `HTTPS_PROXY` is set

### Generated YAML looks wrong
1. Re-read the template to verify feature names match `exclude` and instance parameters
2. Check that instance names don't contain special characters that break YAML
3. Re-run `generate_project` to regenerate

## References

For detailed documentation, consult these bundled reference files:

- `references/yaml-template-guide.md` — YAML template structure, parameterized features, optional features, anchors
