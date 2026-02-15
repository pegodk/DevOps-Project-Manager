# Copilot Guidelines

## Documentation

- **Always update `README.md`** after making functionality changes to the code. This includes adding, removing, or modifying features, tools, endpoints, CLI flags, configuration options, or public APIs. Ensure the README accurately reflects the current state of the project.

## Project Architecture

- The project is an **MCP server** (`src/mcp_server.py`) that exposes Azure DevOps work-item operations as MCP tools for VS Code Copilot and other MCP clients.
- Core logic lives in `src/` as reusable service modules: `devops_client.py`, `template_service.py`, `upload_service.py`, `hierarchy_service.py`.
- MCP tools in `mcp_server.py` should delegate to these service modules — avoid putting business logic directly in tool functions.
- `__init__.py` re-exports all public APIs via `__all__`. When adding or removing public functions, update both `__init__.py` and `__all__`.

## Code Style

- **Language**: Python 3.10+. Use type hints for function signatures.
- Follow existing patterns in the codebase: use `json.dumps()` for MCP tool return values, return `{"status": "error", "message": ...}` on failures.
- Use `Optional` from `typing` for optional parameters in MCP tool signatures.
- Keep MCP tool docstrings descriptive — they are surfaced to the LLM as tool descriptions.

## Testing

- All tests are in `tests/` using **pytest**. Run with `python -m pytest tests/ -v`.
- Every new feature, service function, or MCP tool should have corresponding tests.
- Tests use the `DevOpsClient` in-memory store (no live API calls). Do not add tests that require Azure DevOps credentials.
- When modifying a service module, run its corresponding test file to verify nothing breaks.

## Templates & YAML

- Project templates live in `templates/`. Template structure: `epics → features → stories → tasks`.
- Parent-child relationships use **exact title string matching** — never change a title without updating all references.
- Parameterized features use `{{name}}` placeholders; optional features use `optional: true`.
- Generated YAML goes to `data/` (gitignored). Never commit generated files.

## Environment & Credentials

- Azure DevOps credentials are loaded from `.env` via `python-dotenv`. Required vars: `AZURE_DEVOPS_ORG_NAME`, `AZURE_DEVOPS_PROJECT_NAME`, `AZURE_DEVOPS_PERSONAL_ACCESS_TOKEN`.
- Never hardcode credentials or commit `.env` files.
- The `DevOpsClient` should be used as a singleton (`_get_client()` in the MCP server).

## MCP Server

- All Azure DevOps operations are exposed as MCP tools — do not add CLI scripts for functionality that should be an MCP tool.
- **Never run custom Python scripts** (e.g. `python -c "..."`) to perform Azure DevOps operations. Always use the corresponding MCP tool. If an MCP tool is missing or insufficient, add or extend one first.
- The skill instructions in `.github/skills/project-designer/SKILL.md` document how the Copilot agent uses the MCP tools. Keep the SKILL.md in sync when adding or modifying tools.
- Dependencies: `mcp>=1.20.0`, `PyYAML`, `requests`, `python-dotenv`, `yamllint`.
