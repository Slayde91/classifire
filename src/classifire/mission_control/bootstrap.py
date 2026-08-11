from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .client import MissionControlClient


DEFAULT_AGENTS: list[dict[str, Any]] = [
    {
        "name": "cf-orchestrator",
        "role": "agent",
        "capabilities": ["orchestration", "routing", "status"],
    },
    {
        "name": "cf-intake-evidence",
        "role": "researcher",
        "capabilities": ["evidence-intake", "document-review", "source-provenance"],
    },
    {
        "name": "cf-physical-model",
        "role": "researcher",
        "capabilities": ["physical-scope", "opening-service-model", "quantity-analysis"],
    },
    {
        "name": "cf-technical-system",
        "role": "reviewer",
        "capabilities": ["technical-system-search", "applicability-review", "package15"],
    },
    {
        "name": "cf-commercial-engine",
        "role": "agent",
        "capabilities": ["estimating", "pricing", "package14", "component-build"],
    },
    {
        "name": "cf-validator",
        "role": "tester",
        "capabilities": ["qa", "regression", "reconciliation", "release-gates"],
    },
    {
        "name": "cf-output",
        "role": "assistant",
        "capabilities": ["controlled-output", "workbook", "proposal", "reporting"],
    },
    {
        "name": "cf-library-governance",
        "role": "reviewer",
        "capabilities": ["library-governance", "revision-review", "release-management"],
    },
    {
        "name": "cf-platform-governance",
        "role": "devops",
        "capabilities": ["platform", "security", "deployment", "backup", "rollback"],
    },
]

DEFAULT_TASKS = [
    ("CF-ARCH-001", "Confirm OpenClaw and Mission Control compatibility", "cf-platform-governance", "high"),
    ("CF-DATA-001", "Validate source corpus inventory and hashes", "cf-intake-evidence", "high"),
    ("CF-XLS-001", "Run Windows Excel formula and macro parity suite", "cf-validator", "high"),
    ("CF-P15-001", "Link Active technical variants to immutable source documents", "cf-technical-system", "high"),
    ("CF-P14-001", "Review Package 14 records requiring expert commercial review", "cf-commercial-engine", "high"),
    ("CF-SEC-001", "Complete production security hardening and backup test", "cf-platform-governance", "high"),
    ("CF-UAT-001", "Run reference-project acceptance and regression suite", "cf-validator", "high"),
]


def baseline_task_statuses(client: MissionControlClient) -> list[dict[str, Any]]:
    """Return a compact, non-secret status snapshot for the seven baseline tasks."""
    rows: list[dict[str, Any]] = []
    for task_id, title, assigned_agent, priority in DEFAULT_TASKS:
        full_title = f"{task_id} - {title}"
        task = client.find_task(task_id=task_id, title=full_title)
        if task is None:
            rows.append(
                {
                    "task_id": task_id,
                    "mission_control_id": None,
                    "title": full_title,
                    "assigned_to": assigned_agent,
                    "priority": priority,
                    "status": "missing",
                    "dispatch_attempts": 0,
                    "outcome": None,
                    "error_message": None,
                    "linkage": {},
                }
            )
            continue

        linkage: dict[str, Any] = {}
        for key, value in task.items():
            lowered = str(key).lower()
            if not any(marker in lowered for marker in ("session", "gateway", "runtime", "dispatch")):
                continue
            if value in (None, "", [], {}, False, 0):
                continue
            # Never surface anything that looks like a secret/token field.
            if any(marker in lowered for marker in ("token", "secret", "key", "credential")):
                continue
            linkage[str(key)] = value

        rows.append(
            {
                "task_id": task_id,
                "mission_control_id": task.get("id"),
                "title": task.get("title", full_title),
                "assigned_to": task.get("assigned_to", assigned_agent),
                "priority": task.get("priority", priority),
                "status": task.get("status", "unknown"),
                "dispatch_attempts": task.get("dispatch_attempts", 0) or 0,
                "outcome": task.get("outcome"),
                "error_message": task.get("error_message"),
                "linkage": linkage,
            }
        )
    return rows


def bootstrap_mission_control(
    client: MissionControlClient,
    *,
    repo_url: str | None = None,
    architecture_registry: Path | None = None,
    create_tasks: bool = False,
) -> dict[str, Any]:
    """Register CLASSIFIRE agent records and optionally seed baseline tasks.

    Mission Control sync can name an OpenClaw agent from identity.name while
    CLASSIFIRE refers to it by stable cf-* OpenClaw ID. Bootstrap therefore
    reconciles config.openclawId before falling back to Mission Control name so
    it cannot create a second row for the same OpenClaw agent.

    Task creation is opt-in so Mission Control cannot dispatch work to OpenClaw
    agent IDs that have not yet been created and acceptance-tested. Baseline task
    seeding is idempotent by stable CLASSIFIRE task ID and exact title.
    """
    probe = client.probe()

    existing_agents = client.list_agents()
    registrations: list[dict[str, Any]] = []
    mission_control_names: dict[str, str] = {}

    for spec in DEFAULT_AGENTS:
        existing = client.find_agent(
            openclaw_id=spec["name"],
            name=spec["name"],
            agents=existing_agents,
        )
        if existing is not None:
            registrations.append(
                {
                    "agent": existing,
                    "registered": False,
                    "message": "Agent already present in Mission Control",
                    "matched_by": (
                        "openclaw_id"
                        if isinstance(existing.get("config"), dict)
                        and existing["config"].get("openclawId") == spec["name"]
                        else "name"
                    ),
                }
            )
            mission_control_names[spec["name"]] = str(existing.get("name") or spec["name"])
            continue

        registration = client.register_agent(
            spec["name"],
            spec["role"],
            {
                "framework": "OpenClaw",
                "capabilities": spec["capabilities"],
            },
        )
        registrations.append(registration)
        registered_agent = registration.get("agent") if isinstance(registration, dict) else None
        if isinstance(registered_agent, dict) and registered_agent.get("name"):
            mission_control_names[spec["name"]] = str(registered_agent["name"])
        else:
            mission_control_names[spec["name"]] = spec["name"]

    registry: dict[str, Any] | None = None
    if architecture_registry and architecture_registry.exists():
        registry = yaml.safe_load(architecture_registry.read_text(encoding="utf-8"))

    tasks = []
    if create_tasks:
        for task_id, title, agent, priority in DEFAULT_TASKS:
            full_title = f"{task_id} - {title}"
            tasks.append(
                client.ensure_task(
                    task_id=task_id,
                    title=full_title,
                    assigned_to=mission_control_names.get(agent, agent),
                    priority=priority,
                    description=(
                        "CLASSIFIRE architecture task. Mission Control manages assignment, review, "
                        "quality gates and completion receipts; CLASSIFIRE remains the canonical "
                        "domain system."
                    ),
                    metadata={
                        "task_id": task_id,
                        "project": "CLASSIFIRE",
                        "repository": repo_url,
                        "architecture_registry": registry,
                        "openclaw_agent_id": agent,
                    },
                )
            )

    return {
        "probe": probe,
        "agents": registrations,
        "agent_name_map": mission_control_names,
        "tasks_created": create_tasks,
        "tasks": tasks,
    }
