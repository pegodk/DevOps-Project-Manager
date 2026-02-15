# DevOps Project Template Builder

An MCP server and VS Code Copilot skill that designs Azure DevOps project structures using YAML project templates. Validates and uploads work items (Epics, Features, User Stories, Tasks) to Azure DevOps.

## Features

- **MCP Server** — Exposes all Azure DevOps operations as MCP tools for VS Code Copilot, Claude Desktop, and other MCP-compatible clients
- **Copilot Skill** — Use the `project-designer` skill in VS Code Copilot agent mode to interactively design and upload projects
- **YAML Templates** — Reusable, parameterized project templates with optional and parameterized features
- **Generate Pipeline** — Load template → apply overrides → exclude features → expand parameters → validate → save → lint
- **Upload Pipeline** — Validate connection → bulk-upload work items to Azure DevOps with parent-child linking
- **Azure DevOps Integration** — REST API v7.1 client with hierarchical parent-child linking
- **Project Querying** — Read and analyze existing Azure DevOps project structures (tree + summary)
- **Iteration Path Support** — Assign work items to sprints/iterations via YAML or MCP tools; tracked through generate, upload, and query pipelines
- **Rich Text Support** — Automatic HTML conversion for acceptance criteria (bullet points → `<ul><li>`)

## MCP Tools

The MCP server exposes 13 tools:

| Tool | Description |
|------|-------------|
| `validate_connection` | Test the Azure DevOps connection |
| `get_project_status` | Retrieve the full work-item hierarchy tree and summary stats. Saves one YAML file per epic to `data/<epic-slug>.yaml` |
| `get_work_item` | Get a single work item by ID |
| `search_work_items` | Search for work items by exact title |
| `generate_project` | Generate a customized YAML from a template (load → override → exclude → expand → validate → save → lint) |
| `upload_from_template` | Bulk-upload work items from a generated YAML file to Azure DevOps |
| `create_new_backlog` | Create a single work item (Epic, Feature, User Story, or Task) with optional iteration path |
| `update_existing_item` | Update a work item's title, description, state, or iteration path |
| `get_iterations` | List all iterations (sprints) defined in the project |
| `create_iteration` | Create a new iteration (sprint) with optional start/finish dates and auto-subscribe to team |
| `update_iteration` | Rename an iteration and/or update its start/finish dates |
| `subscribe_iterations` | Subscribe all iterations to the default team so they appear on the Azure Board |
| `run_wiql_query` | Run a raw WIQL query against Azure DevOps |

## Delivery Phases

The included `project-template.yaml` defines a lakehouse / data-platform project with **six delivery phases**. Each phase maps to one or more Features in the work item hierarchy. Features can be **optional** (removable via the `exclude` parameter) or **parameterized** (expanded into multiple instances).

| # | Phase | Feature Flags | Description |
|---|-------|---------------|-------------|
| 1 | **Firm Foundation** | optional | Business assessment, solution design, UAT, change management |
| 2 | **Cloud Infrastructure** | optional | Cloud infrastructure provisioning, CI/CD pipelines, lakehouse framework |
| 3 | **Data Source Integration** | parameterized | Data ingestion from source systems (e.g. SAP, Salesforce, SharePoint). One feature instance per source system |
| 4 | **Data Modeling Layer** | optional | Dimensional modelling (Kimball-style dimensions & facts) in the gold layer |
| 5 | **Semantic Layer** | parameterized, optional | Semantic models (e.g. Finance, Supply Chain) via Tabular Editor or Databricks metric views |
| 6 | **Presentation Layer** | parameterized, optional | Reports, dashboards, and apps — Power BI, Databricks dashboards, Streamlit apps |

When using the Copilot skill interactively, the agent walks through each phase, confirms scope, and collects instance names before generating the final YAML.

## Project Structure

```
devops-project/
├── .github/
│   ├── copilot-instructions.md          # Copilot coding guidelines
│   └── skills/
│       └── project-designer/
│           ├── SKILL.md                 # Full skill instructions (MCP-based)
│           └── references/
│               └── yaml-template-guide.md
├── src/
│   ├── __init__.py            # Re-exports all public APIs
│   ├── mcp_server.py          # MCP server — exposes 13 tools
│   ├── devops_client.py       # Azure DevOps REST API client
│   ├── hierarchy_service.py   # Work item hierarchy fetch, tree, summary
│   ├── template_service.py    # YAML template load, expand, validate, lint
│   └── upload_service.py      # Work item upload orchestration
├── tests/
│   ├── conftest.py                 # Shared fixtures & credential isolation
│   ├── test_devops_client.py
│   ├── test_hierarchy_service.py
│   ├── test_mcp_server.py
│   ├── test_template_service.py
│   ├── test_upload_service.py
│   └── test_mcp_server.py
├── templates/
│   └── project-template.yaml      # Lakehouse project template
├── data/                    # Generated project YAML files (gitignored)
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Setup Instructions

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd devops-project
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   source .venv/bin/activate  # Linux/Mac
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your Azure DevOps credentials:
   #   AZURE_DEVOPS_ORG_NAME=<org>
   #   AZURE_DEVOPS_PROJECT_NAME=<project>
   #   AZURE_DEVOPS_PERSONAL_ACCESS_TOKEN=<pat>
   ```

## Installing the MCP Server

### VS Code (Copilot / GitHub Copilot Chat)

Add the server to your VS Code MCP settings (`.vscode/mcp.json` or User Settings):

```json
{
  "servers": {
    "devops-project": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "src.mcp_server"],
      "cwd": "<path-to-devops-project>"
    }
  }
}
```

Replace `<path-to-devops-project>` with the absolute path to this repository.

### Claude Desktop

Add to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "devops-project": {
      "command": "python",
      "args": ["-m", "src.mcp_server"],
      "cwd": "<path-to-devops-project>"
    }
  }
}
```

### SSE Transport (Remote / Browser Clients)

Start the server with SSE transport for remote access:

```bash
python -m src.mcp_server --transport sse --port 8000
```

### Verifying the Installation

Once configured, the MCP client should discover 13 tools prefixed with `devops-project`. You can verify the connection by calling the `validate_connection` tool.

## Usage

### VS Code Copilot (Recommended)

Use the `project-designer` skill in VS Code Copilot agent mode to:

- Design project structures interactively — the agent walks through each delivery phase
- Collect instance names for parameterized features (sources, models, reports)
- Generate, customize, and upload work items to Azure DevOps via MCP tools
- Query and analyze existing project structures

### MCP Tools Directly

All operations are available as MCP tools. Examples:

**Generate a project from a template:**
```
generate_project(
  template_path="templates/project-template.yaml",
  name="Acme Data Platform",
  datasources=["SAP", "Salesforce"],
  dimensions=["Customer", "Product"],
  facts=["Sales", "Inventory"],
  semantic_models=["Finance"],
  visualizations=["Sales Dashboard"]
)
```

**Upload to Azure DevOps:**
```
validate_connection()
upload_from_template(yaml_path="data/acme-data-platform.yaml")
```

**Query existing project:**
```
get_project_status()
get_project_status(epic_title="Acme Data Platform")
```

**Create individual work items:**
```
create_new_backlog(
  work_item_type="User Story",
  title="Implement login page",
  description="As a user, I want to log in so that I can access my data.",
  story_points=3,
  parent_id=1234,
  iteration_path="MyProject\\Sprint 1"
)
```

**Assign a work item to an iteration:**
```
update_existing_item(
  work_item_id=1234,
  iteration_path="MyProject\\Sprint 2"
)
```

**List all iterations (sprints):**
```
get_iterations()
```

**Create a new iteration:**
```
create_iteration(
  name="Sprint 3",
  start_date="2026-03-01",
  finish_date="2026-03-14"
)
```

**Rename an iteration:**
```
update_iteration(
  current_name="Iteration 1",
  new_name="Sprint 1"
)
```

**Subscribe all iterations to the board:**
```
subscribe_iterations()
```

### Services API

The `src/` package exposes reusable service modules:

```python
from src import (
    DevOpsClient,
    load_template, expand_all_features, save_yaml, lint_yaml,
    validate_template, count_work_items, apply_instance_overrides,
    exclude_features, slugify,
    upload_from_yaml,
    fetch_hierarchy, build_tree, compute_summary, format_tree_text,
)
```

## Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run a specific test module
python -m pytest tests/test_mcp_server.py -v
```

## Template Customisation

### Parameterized Features

Features marked `parameterized: true` in the template contain `{{name}}` placeholders in titles. During expansion, each instance name replaces the placeholder, producing a separate feature with its full user story subtree. Pass instance names via the `datasources`, `semantic_models`, or `visualizations` parameters in the `generate_project` tool.

Example: `datasources=["SAP", "Salesforce", "SharePoint"]` generates three complete feature subtrees: *Data Source Integration - SAP*, *Data Source Integration - Salesforce*, and *Data Source Integration - SharePoint*.

### Parameterized Stories

Some features contain parameterized stories (e.g. the Data Modeling Layer has Dimension and Fact story templates). Pass instance names via the `dimensions` and `facts` parameters:

- `dimensions=["Calendar", "Customer", "Product"]` → *Dimension - Calendar*, *Dimension - Customer*, *Dimension - Product*
- `facts=["Sales", "Inventory"]` → *Fact - Sales*, *Fact - Inventory*

### Optional Features

Features marked `optional: true` are included by default but can be removed with the `exclude` parameter:

```
exclude=["Semantic Layer", "Presentation Layer"]
```

### Project Naming

Use `name` to override the top-level Epic title. The name is also used to derive the output filename (e.g. `data/acme-data-platform.yaml`).

### Iteration Path

Work items can be assigned to iterations (sprints) via the `iteration_path` field at any level of the YAML hierarchy. The path uses the Azure DevOps iteration format: `ProjectName\Iteration\Sprint`.

```yaml
epics:
- title: Acme Data Platform
  features:
  - title: Firm Foundation
    stories:
    - title: Business Assessment
      story_points: 8
      iteration_path: "devops-project\\Sprint 1"
    - title: Solution Design
      story_points: 5
      iteration_path: "devops-project\\Sprint 2"
```

When uploading, the `iteration_path` is sent as `System.IterationPath` to Azure DevOps. When querying with `get_project_status`, existing iteration paths are included in the downloaded YAML files.

## Creating a Personal Access Token (PAT)

1. Go to Azure DevOps → User Settings → Personal Access Tokens
2. Click **New Token**
3. Set scope to **Work Items: Read, Write, & Manage**
4. Copy the token and add it to `.env` as `AZURE_DEVOPS_PERSONAL_ACCESS_TOKEN`