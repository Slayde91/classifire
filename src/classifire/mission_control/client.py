from __future__ import annotations

from dataclasses import dataclass
import time
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

            # Mission Control currently serves its OpenAPI document from /api/docs.
            # Older or alternate builds may expose /openapi.json or /api/openapi.json.
            # Contract discovery is diagnostic and must not fail bootstrap when an
            # endpoint returns HTML or another non-JSON success response.
            openapi_candidates = ("/api/docs", "/openapi.json", "/api/openapi.json")
            findings["openapi_status"] = None
            findings["openapi_endpoint"] = None
            findings["openapi_version"] = None
            findings["endpoint_count"] = 0
            findings["paths"] = []

            for endpoint in openapi_candidates:
                response = client.get(self._url(endpoint), headers=self.headers)
                findings["openapi_status"] = response.status_code

                if not response.is_success:
                    continue

                try:
                    payload = response.json()
                except ValueError:
                    continue

                if not isinstance(payload, dict) or not isinstance(payload.get("paths"), dict):
                    continue

                findings["openapi_endpoint"] = endpoint
                findings["openapi_version"] = payload.get("openapi")
                findings["endpoint_count"] = len(payload["paths"])
                findings["paths"] = sorted(payload["paths"].keys())
                break

        return findings

    def register_agent(self, name: str, role: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {"name": name, "role": role, **(metadata or {})}

        # Mission Control self-registration is rate-limited to 5 requests/minute
        # per IP. A full QUANTIFIRE fleet contains nine agents, so bootstrap must
        # tolerate 429 responses instead of failing after the fifth registration.
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    self._url("/api/agents/register"),
                    headers=self.headers,
                    json=payload,
                )

            if response.status_code != 429:
                break

            if attempt >= max_attempts:
                break

            retry_after = response.headers.get("Retry-After")
            try:
                wait_seconds = max(1, int(retry_after)) if retry_after else 61
            except ValueError:
                wait_seconds = 61

            print(
                f"Mission Control registration rate limit reached while registering {name}; "
                f"waiting {wait_seconds}s before retry {attempt + 1}/{max_attempts}..."
            )
            time.sleep(wait_seconds)

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
