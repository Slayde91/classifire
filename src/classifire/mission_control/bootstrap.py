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


def bootstrap_mission_control(
    client: MissionControlClient,
    *,
    repo_url: str | None = None,
    architecture_registry: Path | None = None,
    create_tasks: bool = False,
) -> dict[str, Any]:
    """Register CLASSIFIRE agent records and optionally seed baseline tasks.

    Task creation is opt-in so Mission Control cannot dispatch work to OpenClaw
    agent IDs that have not yet been created and acceptance-tested.
    """
    probe = client.probe()

    registrations = []
    for spec in DEFAULT_AGENTS:
        registrations.append(
            client.register_agent(
                spec["name"],
                spec["role"],
                {
                    "framework": "OpenClaw",
                    "capabilities": spec["capabilities"],
                },
            )
        )

    registry: dict[str, Any] | None = None
    if architecture_registry and architecture_registry.exists():
        registry = yaml.safe_load(architecture_registry.read_text(encoding="utf-8"))

    tasks = []
    if create_tasks:
        for task_id, title, agent, priority in DEFAULT_TASKS:
            tasks.append(
                client.create_task(
                    title=f"{task_id} - {title}",
                    assigned_to=agent,
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
                    },
                )
            )

    return {
        "probe": probe,
        "agents": registrations,
        "tasks_created": create_tasks,
        "tasks": tasks,
    }
