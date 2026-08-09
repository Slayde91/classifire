from __future__ import annotations

from classifire.mission_control.bootstrap import DEFAULT_TASKS, baseline_task_statuses, bootstrap_mission_control
from classifire.mission_control.client import MissionControlClient


def test_ensure_task_reuses_existing(monkeypatch):
    client = MissionControlClient("http://mission-control.test", "secret")
    existing = {"id": 41, "title": "CF-ARCH-001 - Confirm OpenClaw and Mission Control compatibility"}

    monkeypatch.setattr(client, "find_task", lambda **_kwargs: existing)

    def unexpected_create(**_kwargs):
        raise AssertionError("create_task must not run when the task already exists")

    monkeypatch.setattr(client, "create_task", unexpected_create)

    result = client.ensure_task(
        task_id="CF-ARCH-001",
        title=existing["title"],
        assigned_to="cf-platform-governance",
        priority="high",
    )

    assert result == {"created": False, "task_id": "CF-ARCH-001", "task": existing}


def test_ensure_task_creates_missing(monkeypatch):
    client = MissionControlClient("http://mission-control.test", "secret")
    monkeypatch.setattr(client, "find_task", lambda **_kwargs: None)
    monkeypatch.setattr(
        client,
        "create_task",
        lambda **kwargs: {"task": {"id": 42, "title": kwargs["title"], "assigned_to": kwargs["assigned_to"]}},
    )

    result = client.ensure_task(
        task_id="CF-UAT-001",
        title="CF-UAT-001 - Run reference-project acceptance and regression suite",
        assigned_to="cf-validator",
        priority="high",
    )

    assert result["created"] is True
    assert result["task_id"] == "CF-UAT-001"
    assert result["task"]["id"] == 42


class FakeMissionControlClient:
    def __init__(self):
        self.ensured: list[str] = []

    def probe(self):
        return {"status_endpoint": 200}

    def register_agent(self, name, role, metadata=None):
        return {"agent": {"name": name, "role": role}, "registered": False}

    def ensure_task(self, *, task_id, title, **_kwargs):
        self.ensured.append(task_id)
        return {"created": False, "task_id": task_id, "task": {"title": title}}


def test_bootstrap_uses_idempotent_ensure_task_for_all_baseline_tasks():
    client = FakeMissionControlClient()

    result = bootstrap_mission_control(client, create_tasks=True)

    expected_ids = [task_id for task_id, _title, _agent, _priority in DEFAULT_TASKS]
    assert client.ensured == expected_ids
    assert len(result["tasks"]) == len(DEFAULT_TASKS)
    assert all(item["created"] is False for item in result["tasks"])


def test_baseline_task_statuses_reports_dispatch_and_filters_secret_linkage():
    class StatusClient:
        def find_task(self, *, task_id=None, title=None):
            if task_id == "CF-ARCH-001":
                return {
                    "id": 14,
                    "title": title,
                    "assigned_to": "cf-platform-governance",
                    "priority": "high",
                    "status": "in_progress",
                    "dispatch_attempts": 1,
                    "gateway_session_id": "session-123",
                    "gateway_token": "must-not-leak",
                }
            return None

    rows = baseline_task_statuses(StatusClient())
    arch = next(row for row in rows if row["task_id"] == "CF-ARCH-001")
    data = next(row for row in rows if row["task_id"] == "CF-DATA-001")

    assert arch["mission_control_id"] == 14
    assert arch["status"] == "in_progress"
    assert arch["dispatch_attempts"] == 1
    assert arch["linkage"] == {"gateway_session_id": "session-123", "dispatch_attempts": 1}
    assert data["status"] == "missing"
