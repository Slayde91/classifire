from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .client import MissionControlClient

DEFAULT_AGENTS: list[dict[str, Any]] = [
    {
        "name": "qf-orchestrator",
        "role": "agent",
        "capabilities": ["orchestration", "routing", "status"],
    },
    {
        "name": "qf-intake-evidence",
        "role": "researcher",
        "capabilities": ["evidence-intake", "document-review", "source-provenance"],
    },
    {
        "name": "qf-physical-model",
        "role": "researcher",
        "capabilities": ["physical-scope", "opening-service-model", "quantity-analysis"],
    },
    {
        "name": "qf-technical-system",
        "role": "reviewer",
        "capabilities": ["technical-system-search", "applicability-review", "package15"],
    },
    {
        "name": "qf-commercial-engine",
        "role": "agent",
        "capabilities": ["estimating", "pricing", "package14", "component-build"],
    },
    {
        "name": "qf-validator",
        "role": "tester",
        "capabilities": ["qa", "regression", "reconciliation", "release-gates"],
    },
    {
        "name": "qf-output",
        "role": "assistant",
        "capabilities": ["controlled-output", "workbook", "proposal", "reporting"],
    },
    {
        "name": "qf-library-governance",
        "role": "reviewer",
        "capabilities": ["library-governance", "revision-review", "release-management"],
    },
    {
        "name": "qf-platform-governance",
        "role": "devops",
        "capabilities": ["platform", "security", "deployment", "backup", "rollback"],
    },
]

DEFAULT_TASKS = [
    (
        "QF-ARCH-001",
        "Confirm OpenClaw and Mission Control compatibility",
        "qf-platform-governance",
        "high",
    ),
    ("QF-DATA-001", "Validate source corpus inventory and hashes", "qf-intake-evidence", "high"),
    ("QF-XLS-001", "Run Windows Excel formula and macro parity suite", "qf-validator", "high"),
    (
        "QF-P15-001",
        "Link Active technical variants to immutable source documents",
        "qf-technical-system",
        "high",
    ),
    (
        "QF-P14-001",
        "Review Package 14 records requiring expert commercial review",
        "qf-commercial-engine",
        "high",
    ),
    (
        "QF-SEC-001",
        "Complete production security hardening and backup test",
        "qf-platform-governance",
        "high",
    ),
    ("QF-UAT-001", "Run reference-project acceptance and regression suite", "qf-validator", "high"),
]


def bootstrap_mission_control(
    client: MissionControlClient,
    *,
    repo_url: str | None = None,
    architecture_registry: Path | None = None,
    create_tasks: bool = False,
) -> dict[str, Any]:
    """Register QUANTIFIRE agent records and optionally seed baseline tasks.

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
                        "QUANTIFIRE architecture task. Mission Control manages assignment, review, "
                        "quality gates and completion receipts; QUANTIFIRE remains the canonical "
                        "domain system."
                    ),
                    metadata={
                        "task_id": task_id,
                        "project": "QUANTIFIRE",
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
