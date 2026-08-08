from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class MissionControlError(RuntimeError):
    pass


@dataclass
class MissionControlClient:
    base_url: str
    api_key: str
    timeout: float = 20.0

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    def probe(self) -> dict[str, Any]:
        findings: dict[str, Any] = {"base_url": self.base_url}
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            status = client.get(self._url("/api/status"), headers=self.headers)
            findings["status_endpoint"] = status.status_code
            openapi = client.get(self._url("/openapi.json"), headers=self.headers)
            if openapi.status_code == 404:
                openapi = client.get(self._url("/api/openapi.json"), headers=self.headers)
            findings["openapi_status"] = openapi.status_code
            if openapi.is_success:
                payload = openapi.json()
                findings["openapi_version"] = payload.get("openapi")
                findings["endpoint_count"] = len(payload.get("paths", {}))
                findings["paths"] = sorted(payload.get("paths", {}).keys())
        return findings

    def register_agent(self, name: str, role: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {"name": name, "role": role, **(metadata or {})}
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(self._url("/api/agents/register"), headers=self.headers, json=payload)
        if response.status_code not in {200, 201, 409}:
            raise MissionControlError(
                f"Agent registration failed ({response.status_code}): {response.text[:500]}"
            )
        return response.json() if response.content else {"status": response.status_code}

    def create_task(
        self,
        *,
        title: str,
        assigned_to: str | None = None,
        priority: str = "medium",
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"title": title, "priority": priority}
        if assigned_to:
            payload["assigned_to"] = assigned_to
        if description:
            payload["description"] = description
        if metadata:
            payload["metadata"] = metadata
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(self._url("/api/tasks"), headers=self.headers, json=payload)
        if response.status_code not in {200, 201}:
            raise MissionControlError(
                f"Task creation failed ({response.status_code}): {response.text[:500]}"
            )
        return response.json()
