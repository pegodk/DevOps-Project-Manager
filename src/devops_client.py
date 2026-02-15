"""
Azure DevOps REST API client for work item operations.
"""

import requests
from requests.auth import HTTPBasicAuth


class DevOpsClient:
    """Client for Azure DevOps work item CRUD operations."""
    
    def __init__(self, organization=None, project=None, pat=None):
        self.organization = organization
        self.project = project
        self.pat = pat
        self.api_version = "7.1"
        self._auth = None
        self._items = {}  # In-memory store for testing
        self._next_id = 1
        self._iterations = []  # In-memory iteration store for testing
        self._next_iteration_id = 1
    
    @property
    def auth(self):
        """Get HTTPBasicAuth object."""
        if self._auth is None and self.pat:
            self._auth = HTTPBasicAuth("", self.pat)
        return self._auth
    
    @property
    def base_url(self):
        """Get base URL for Azure DevOps API."""
        return f"https://dev.azure.com/{self.organization}/{self.project}/_apis/wit"
    
    def configure(self, organization, project, pat):
        """Configure the service with Azure DevOps credentials."""
        self.organization = organization
        self.project = project
        self.pat = pat
        self._auth = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(self, work_item_type, data, parent_id=None):
        """
        Create a work item of any type.

        Args:
            work_item_type: "Epic", "Feature", "User Story", or "Task".
            data: dict with title (required), description, acceptance_criteria,
                  estimate, story_points (all optional).
            parent_id: Numeric ID of the parent work item (optional).

        Returns:
            Dict with at least 'id' and 'title' keys.
        """
        return self._create_work_item(work_item_type, data, parent_id)

    def find_by_title(self, title):
        """
        Find work item IDs by exact title using WIQL.

        Returns:
            List of integer IDs, or empty list if none found.
        """
        if not self.organization or not self.pat:
            return [
                item["id"] for item in self._items.values()
                if item.get("title") == title
            ]

        url = f"{self.base_url}/wiql?api-version={self.api_version}"
        safe_title = title.replace("'", "''")
        query = {"query": f"SELECT [System.Id] FROM workitems WHERE [System.Title] = '{safe_title}'"}
        resp = requests.post(url, json=query, auth=self.auth)
        if resp.status_code != 200:
            return []
        return [wi["id"] for wi in resp.json().get("workItems", [])]

    def work_item_exists(self, title, parent_id=None):
        """
        Check whether a work item with the given title (and optional parent)
        already exists.

        Returns:
            True if at least one matching work item exists.
        """
        if not self.organization or not self.pat:
            for item in self._items.values():
                if item.get("title") == title:
                    if parent_id is None or item.get("parent_id") == parent_id:
                        return True
            return False

        url = f"{self.base_url}/wiql?api-version={self.api_version}"
        safe_title = title.replace("'", "''")
        if parent_id:
            q = (f"SELECT [System.Id] FROM WorkItems "
                 f"WHERE [System.Title] = '{safe_title}' AND [System.Parent] = {parent_id}")
        else:
            q = f"SELECT [System.Id] FROM WorkItems WHERE [System.Title] = '{safe_title}'"
        resp = requests.post(url, json={"query": q}, auth=self.auth)
        if resp.status_code != 200:
            return False
        return len(resp.json().get("workItems", [])) > 0

    def run_wiql(self, query_text):
        """
        Execute a WIQL query and return matching work item IDs.

        Args:
            query_text: A WIQL query string.

        Returns:
            List of integer work item IDs.
        """
        if not self.organization or not self.pat:
            return list(self._items.keys())

        url = f"{self.base_url}/wiql?api-version={self.api_version}"
        resp = requests.post(url, json={"query": query_text}, auth=self.auth, timeout=30)
        resp.raise_for_status()
        return [item["id"] for item in resp.json().get("workItems", [])]

    def get_work_items_batch(self, ids, fields=None):
        """
        Fetch work item details in batches of 200 (API limit).

        Args:
            ids: List of work item IDs.
            fields: List of field reference names. Uses default set if None.

        Returns:
            List of raw work item dicts from the API.
        """
        if not self.organization or not self.pat:
            # Map internal in-memory keys to the System.* field names
            # that the real API returns, so consumers get a consistent shape.
            _MAP = {
                "type": "System.WorkItemType",
                "title": "System.Title",
                "state": "System.State",
                "description": "System.Description",
                "parent_id": "System.Parent",
                "acceptance_criteria": "Microsoft.VSTS.Common.AcceptanceCriteria",
                "story_points": "Microsoft.VSTS.Scheduling.StoryPoints",
                "estimate": "Microsoft.VSTS.Scheduling.Effort",
                "iteration_path": "System.IterationPath",
            }
            result = []
            for iid in ids:
                if iid not in self._items:
                    continue
                raw = self._items[iid]
                mapped = {}
                for internal_key, api_key in _MAP.items():
                    if internal_key in raw:
                        mapped[api_key] = raw[internal_key]
                mapped["System.Id"] = iid
                result.append({"id": iid, "fields": mapped})
            return result

        if fields is None:
            fields = [
                "System.Id", "System.Title", "System.WorkItemType",
                "System.State", "System.Description", "System.Parent",
                "System.IterationPath",
                "Microsoft.VSTS.Common.AcceptanceCriteria",
                "Microsoft.VSTS.Scheduling.StoryPoints",
                "Microsoft.VSTS.Scheduling.Effort",
            ]

        items = []
        fields_csv = ",".join(fields)
        for i in range(0, len(ids), 200):
            batch = ids[i:i + 200]
            url = (
                f"{self.base_url}/workitems"
                f"?ids={','.join(map(str, batch))}"
                f"&fields={fields_csv}"
                f"&api-version={self.api_version}"
            )
            resp = requests.get(url, auth=self.auth, timeout=30)
            resp.raise_for_status()
            items.extend(resp.json().get("value", []))
        return items

    def get_iterations(self) -> list[dict]:
        """
        List all iterations (sprints) defined in the project.

        Returns:
            List of dicts with keys: id, name, path, start_date, finish_date.
        """
        if not self.organization or not self.pat:
            return list(self._iterations)

        url = (
            f"https://dev.azure.com/{self.organization}/{self.project}"
            f"/_apis/wit/classificationnodes/iterations"
            f"?%24depth=10&api-version={self.api_version}"
        )
        resp = requests.get(url, auth=self.auth, timeout=30)
        resp.raise_for_status()
        root = resp.json()
        results: list[dict] = []
        for child in root.get("children", []):
            results.extend(self._flatten_iteration_nodes(child))
        return results

    def create_iteration(
        self, name: str, start_date: str | None = None, finish_date: str | None = None
    ) -> dict:
        """
        Create a new iteration (sprint) in the project and subscribe it
        to the default team so it appears on the board.

        Args:
            name: Iteration name (e.g. "Sprint 1").
            start_date: Optional ISO-8601 date string (e.g. "2026-03-01").
            finish_date: Optional ISO-8601 date string (e.g. "2026-03-14").

        Returns:
            Dict with id, identifier, name, path, start_date, finish_date.
        """
        if not self.organization or not self.pat:
            return self._create_iteration_in_memory(name, start_date, finish_date)

        url = (
            f"https://dev.azure.com/{self.organization}/{self.project}"
            f"/_apis/wit/classificationnodes/iterations"
            f"?api-version={self.api_version}"
        )
        body: dict = {"name": name}
        attributes: dict = {}
        if start_date:
            attributes["startDate"] = start_date
        if finish_date:
            attributes["finishDate"] = finish_date
        if attributes:
            body["attributes"] = attributes

        resp = requests.post(url, json=body, auth=self.auth, timeout=30)
        resp.raise_for_status()
        node = resp.json()
        attrs = node.get("attributes", {})
        identifier = node.get("identifier", "")

        # Subscribe the new iteration to the default team
        if identifier:
            self._subscribe_iteration_to_team(identifier)

        return {
            "id": node.get("id"),
            "identifier": identifier,
            "name": node.get("name", name),
            "path": node.get("path", f"\\{self.project}\\Iteration\\{name}"),
            "start_date": attrs.get("startDate"),
            "finish_date": attrs.get("finishDate"),
        }

    # ------------------------------------------------------------------
    # Iteration helpers
    # ------------------------------------------------------------------

    def update_iteration(
        self,
        current_name: str,
        new_name: str | None = None,
        start_date: str | None = None,
        finish_date: str | None = None,
    ) -> dict:
        """
        Update an existing iteration (rename and/or set dates).

        Args:
            current_name: Current iteration name (e.g. "Iteration 1").
            new_name: New name for the iteration (optional).
            start_date: New start date in ISO-8601 format (optional).
            finish_date: New finish date in ISO-8601 format (optional).

        Returns:
            Dict with id, name, path, start_date, finish_date.
        """
        if not self.organization or not self.pat:
            return self._update_iteration_in_memory(
                current_name, new_name, start_date, finish_date
            )

        encoded_name = requests.utils.quote(current_name, safe="")
        url = (
            f"https://dev.azure.com/{self.organization}/{self.project}"
            f"/_apis/wit/classificationnodes/iterations/{encoded_name}"
            f"?api-version={self.api_version}"
        )
        body: dict = {}
        if new_name:
            body["name"] = new_name
        attributes: dict = {}
        if start_date is not None:
            attributes["startDate"] = (
                start_date if "T" in start_date else f"{start_date}T00:00:00Z"
            )
        if finish_date is not None:
            attributes["finishDate"] = (
                finish_date if "T" in finish_date else f"{finish_date}T00:00:00Z"
            )
        if attributes:
            body["attributes"] = attributes

        resp = requests.patch(url, json=body, auth=self.auth, timeout=30)
        resp.raise_for_status()
        node = resp.json()
        attrs = node.get("attributes", {})
        return {
            "id": node.get("id"),
            "name": node.get("name", new_name or current_name),
            "path": node.get("path", ""),
            "start_date": attrs.get("startDate"),
            "finish_date": attrs.get("finishDate"),
        }

    @staticmethod
    def _flatten_iteration_nodes(node: dict, prefix: str = "") -> list[dict]:
        """Recursively flatten an iteration classification-node into a list."""
        results: list[dict] = []
        path = node.get("path", prefix)
        attrs = node.get("attributes", {})
        results.append({
            "id": node.get("id"),
            "identifier": node.get("identifier", ""),
            "name": node.get("name", ""),
            "path": path,
            "start_date": attrs.get("startDate"),
            "finish_date": attrs.get("finishDate"),
        })
        for child in node.get("children", []):
            results.extend(DevOpsClient._flatten_iteration_nodes(child, path))
        return results

    def subscribe_iteration(self, identifier: str) -> dict:
        """Subscribe an iteration to the default team so it shows on the board.

        Args:
            identifier: The iteration identifier (GUID) from get_iterations.

        Returns:
            Dict with status and identifier.
        """
        if not self.organization or not self.pat:
            return {"status": "subscribed", "identifier": identifier}

        url = (
            f"https://dev.azure.com/{self.organization}/{self.project}"
            f"/_apis/work/teamsettings/iterations"
            f"?api-version={self.api_version}"
        )
        resp = requests.post(
            url, json={"id": identifier}, auth=self.auth, timeout=30
        )
        # 409 Conflict means it's already subscribed — that's fine
        if resp.status_code == 409:
            return {"status": "already_subscribed", "identifier": identifier}
        resp.raise_for_status()
        return {"status": "subscribed", "identifier": identifier}

    def _subscribe_iteration_to_team(self, identifier: str) -> None:
        """Subscribe an iteration to the default team (internal helper)."""
        self.subscribe_iteration(identifier)

    def _create_iteration_in_memory(self, name, start_date, finish_date):
        """Create iteration in memory (for testing)."""
        iteration = {
            "id": self._next_iteration_id,
            "identifier": f"guid-{self._next_iteration_id}",
            "name": name,
            "path": f"\\Project\\Iteration\\{name}",
            "start_date": start_date,
            "finish_date": finish_date,
        }
        self._next_iteration_id += 1
        self._iterations.append(iteration)
        return iteration

    def _update_iteration_in_memory(self, current_name, new_name, start_date, finish_date):
        """Update iteration in memory (for testing)."""
        for iteration in self._iterations:
            if iteration["name"] == current_name:
                if new_name:
                    iteration["name"] = new_name
                    iteration["path"] = f"\\Project\\Iteration\\{new_name}"
                if start_date is not None:
                    iteration["start_date"] = start_date
                if finish_date is not None:
                    iteration["finish_date"] = finish_date
                return dict(iteration)
        raise Exception(f"Iteration '{current_name}' not found")

    def validate_connection(self):
        """
        Test the Azure DevOps connection.

        Returns:
            Tuple (ok: bool, message: str).
        """
        url = f"https://dev.azure.com/{self.organization}/_apis/projects/{self.project}?api-version={self.api_version}"
        try:
            resp = requests.get(url, auth=self.auth, timeout=10)
            if resp.status_code == 200:
                name = resp.json().get("name", self.project)
                return True, f"Connected to project: {name}"
            elif resp.status_code == 401:
                return False, "Authentication failed — PAT may be expired or invalid."
            elif resp.status_code == 404:
                return False, f"Project '{self.project}' not found in org '{self.organization}'."
            else:
                return False, f"Connection failed: HTTP {resp.status_code}"
        except requests.exceptions.RequestException as e:
            return False, f"Connection error: {e}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_html(text):
        """Convert plain text to HTML for Azure DevOps rich-text fields.

        * Lines starting with ``•`` become ``<li>`` items inside a ``<ul>``.
        * Other non-empty lines become ``<p>`` paragraphs.
        * Blank lines are ignored.
        """
        if not text:
            return text

        lines = text.splitlines()
        html_parts = []
        bullet_buffer = []

        def _flush_bullets():
            if bullet_buffer:
                items = "".join(f"<li>{b}</li>" for b in bullet_buffer)
                html_parts.append(f"<ul>{items}</ul>")
                bullet_buffer.clear()

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("•"):
                bullet_buffer.append(stripped.lstrip("• ").strip())
            else:
                _flush_bullets()
                html_parts.append(f"<p>{stripped}</p>")

        _flush_bullets()
        return "".join(html_parts)

    def _create_work_item(self, work_item_type, data, parent_id=None):
        """Create a work item in Azure DevOps."""
        # If no credentials configured, use in-memory store (for testing)
        if not self.organization or not self.pat:
            return self._create_in_memory(work_item_type, data, parent_id)
        
        url = f"{self.base_url}/workitems/${work_item_type}?api-version={self.api_version}"
        
        body = [
            {"op": "add", "path": "/fields/System.Title", "value": data.get("title", "")},
        ]
        
        if data.get("description"):
            body.append({"op": "add", "path": "/fields/System.Description",
                         "value": self._to_html(data["description"])})

        if data.get("acceptance_criteria"):
            body.append({"op": "add", "path": "/fields/Microsoft.VSTS.Common.AcceptanceCriteria",
                         "value": self._to_html(data["acceptance_criteria"])})

        if data.get("estimate") and str(data["estimate"]).strip():
            try:
                body.append({"op": "add", "path": "/fields/Microsoft.VSTS.Scheduling.Effort",
                             "value": float(data["estimate"])})
            except (ValueError, TypeError):
                pass

        if data.get("story_points") and str(data["story_points"]).strip():
            try:
                body.append({"op": "add", "path": "/fields/Microsoft.VSTS.Scheduling.StoryPoints",
                             "value": float(data["story_points"])})
            except (ValueError, TypeError):
                pass

        if data.get("iteration_path"):
            body.append({"op": "add", "path": "/fields/System.IterationPath",
                         "value": data["iteration_path"]})
        
        if parent_id:
            body.append({
                "op": "add",
                "path": "/relations/-",
                "value": {
                    "rel": "System.LinkTypes.Hierarchy-Reverse",
                    "url": f"https://dev.azure.com/{self.organization}/_apis/wit/workItems/{parent_id}"
                }
            })
        
        headers = {"Content-Type": "application/json-patch+json"}
        response = requests.post(url, json=body, auth=self.auth, headers=headers)
        
        if response.status_code in [200, 201]:
            return response.json()
        else:
            raise Exception(f"Failed to create {work_item_type}: {response.text}")
    
    def _get_work_item(self, work_item_id):
        """Get a work item by ID."""
        # If no credentials configured, use in-memory store (for testing)
        if not self.organization or not self.pat:
            return self._get_in_memory(work_item_id)
        
        url = f"{self.base_url}/workitems/{work_item_id}?api-version={self.api_version}"
        response = requests.get(url, auth=self.auth)
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            return None
        else:
            raise Exception(f"Failed to get work item: {response.text}")
    
    def _update_work_item(self, work_item_id, data):
        """Update a work item."""
        # If no credentials configured, use in-memory store (for testing)
        if not self.organization or not self.pat:
            return self._update_in_memory(work_item_id, data)
        
        url = f"{self.base_url}/workitems/{work_item_id}?api-version={self.api_version}"
        
        body = []
        if "title" in data:
            body.append({"op": "replace", "path": "/fields/System.Title", "value": data["title"]})
        if "description" in data:
            body.append({"op": "replace", "path": "/fields/System.Description", "value": data["description"]})
        if "state" in data:
            body.append({"op": "replace", "path": "/fields/System.State", "value": data["state"]})
        if "iteration_path" in data:
            body.append({"op": "replace", "path": "/fields/System.IterationPath", "value": data["iteration_path"]})
        
        headers = {"Content-Type": "application/json-patch+json"}
        response = requests.patch(url, json=body, auth=self.auth, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Failed to update work item: {response.text}")
    
    def _delete_work_item(self, work_item_id):
        """Delete a work item."""
        # If no credentials configured, use in-memory store (for testing)
        if not self.organization or not self.pat:
            return self._delete_in_memory(work_item_id)
        
        url = f"{self.base_url}/workitems/{work_item_id}?api-version={self.api_version}"
        response = requests.delete(url, auth=self.auth)
        
        if response.status_code in [200, 204]:
            return {"success": True, "id": work_item_id}
        else:
            raise Exception(f"Failed to delete work item: {response.text}")
    
    # In-memory methods for testing without Azure DevOps connection
    def _create_in_memory(self, work_item_type, data, parent_id=None):
        """Create work item in memory (for testing)."""
        item_id = self._next_id
        self._next_id += 1
        
        item = {
            "id": item_id,
            "type": work_item_type,
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "parent_id": parent_id,
            "state": "New",
            "iteration_path": data.get("iteration_path", ""),
        }
        self._items[item_id] = item
        return item
    
    def _get_in_memory(self, work_item_id):
        """Get work item from memory (for testing)."""
        item = self._items.get(work_item_id)
        if item:
            return {"id": item["id"], "title": item["title"], "description": item["description"]}
        return None
    
    def _update_in_memory(self, work_item_id, data):
        """Update work item in memory (for testing)."""
        if work_item_id in self._items:
            item = self._items[work_item_id]
            if "title" in data:
                item["title"] = data["title"]
            if "description" in data:
                item["description"] = data["description"]
            if "state" in data:
                item["state"] = data["state"]
            if "iteration_path" in data:
                item["iteration_path"] = data["iteration_path"]
            return item
        raise Exception(f"Work item {work_item_id} not found")
    
    def _delete_in_memory(self, work_item_id):
        """Delete work item from memory (for testing)."""
        if work_item_id in self._items:
            del self._items[work_item_id]
            return {"success": True, "id": work_item_id}
        return {"success": False, "id": work_item_id}
