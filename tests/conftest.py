"""
Shared test configuration.

Clears Azure DevOps credentials from the environment so that all tests
use the in-memory DevOpsClient backend.  This runs once per session,
before any test module is imported.
"""

import os
import sys

# Ensure src is importable from all test files
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Strip Azure DevOps credentials from the process environment so that
# load_dotenv() in mcp_server.py (or any other module) cannot inject them.
# This guarantees every DevOpsClient instance stays in in-memory mode.
# ---------------------------------------------------------------------------
_CREDENTIAL_VARS = [
    "AZURE_DEVOPS_ORG_NAME",
    "AZURE_DEVOPS_PROJECT_NAME",
    "AZURE_DEVOPS_PERSONAL_ACCESS_TOKEN",
]

for var in _CREDENTIAL_VARS:
    os.environ.pop(var, None)

# Prevent python-dotenv from re-loading .env during this process.
# Setting the vars to empty strings means load_dotenv(override=False)
# — the default — will see them as "already set" and skip them.
for var in _CREDENTIAL_VARS:
    os.environ[var] = ""
