from __future__ import annotations

from typing import Any

import httpx
import pytest

from classifire.mission_control.client import MissionControlClient, MissionControlError


class _StubClient:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.requests: list[tuple[str, str, dict[str, Any]]] = []

    def __enter__(self) -> _StubClient:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self.requests.append(("POST", url, kwargs))
        return self.response


def _client_with_response(monkeypatch: pytest.MonkeyPatch, response: httpx.Response) -> _StubClient:
    stub = _StubClient(response)
    monkeypatch.setattr("classifire.mission_control.client.httpx.Client", lambda **_kwargs: stub)
    return stub


def test_create_task_returns_object_response(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = _client_with_response(monkeypatch, httpx.Response(201, json={"id": "task-123"}))
    client = MissionControlClient("https://mission-control.example", "test-key")

    created = client.create_task(title="Review evidence", priority="high")

    assert created == {"id": "task-123"}
    assert stub.requests == [
        (
            "POST",
            "https://mission-control.example/api/tasks",
            {
                "headers": client.headers,
                "json": {"title": "Review evidence", "priority": "high"},
            },
        )
    ]


def test_create_task_rejects_non_object_response(monkeypatch: pytest.MonkeyPatch) -> None:
    _client_with_response(monkeypatch, httpx.Response(201, json=["task-123"]))
    client = MissionControlClient("https://mission-control.example", "test-key")

    with pytest.raises(MissionControlError, match="non-object JSON"):
        client.create_task(title="Review evidence")
