from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .client import MissionControlClient


DEFAULT_AGENTS = [
    ("qf-orchestrator", "workflow orchestrator"),
    ("qf-intake-evidence", "evidence intake specialist"),
    ("qf-physical-model", "physical model specialist"),
    ("qf-technical-system", "technical system specialist"),
    ("qf-commercial-engine", "commercial estimating specialist"),
    ("qf-validator", "independent validation specialist"),
    ("qf-output", "controlled output renderer"),
    ("qf-library-governance", "library governance specialist"),
    ("qf-platform-governance", "platform architecture and release specialist"),
]

DEFAULT_TASKS = [
    ("QF-ARCH-001", "Confirm OpenClaw and Mission Control compatibility", "qf-platform-governance", "high"),
    ("QF-DATA-001", "Validate source corpus inventory and hashes", "qf-intake-evidence", "high"),
    ("QF-XLS-001", "Run Windows Excel formula and macro parity suite", "qf-validator", "high"),
    ("QF-P15-001", "Link Active technical variants to immutable source documents", "qf-technical-system", "high"),
    ("QF-P14-001", "Review Package 14 records requiring expert commercial review", "qf-commercial-engine", "high"),
    ("QF-SEC-001", "Complete production security hardening and backup test", "qf-platform-governance", "high"),
    ("QF-UAT-001", "Run reference-project acceptance and regression suite", "qf-validator", "high"),
]


def bootstrap_mission_control(
    client: MissionControlClient,
    *,
    repo_url: str | None = None,
    architecture_registry: Path | None = None,
) -> dict[str, Any]:
    probe = client.probe()
    registrations = []
    for name, role in DEFAULT_AGENTS:
        registrations.append(
            client.register_agent(
                name,
                role,
                {
                    "framework": "OpenClaw",
                    "project": "QUANTIFIRE",
                    "repository": repo_url,
                },
            )
        )
    registry: dict[str, Any] | None = None
    if architecture_registry and architecture_registry.exists():
        registry = yaml.safe_load(architecture_registry.read_text(encoding="utf-8"))
    tasks = []
    for task_id, title, agent, priority in DEFAULT_TASKS:
        tasks.append(
            client.create_task(
                title=f"{task_id} — {title}",
                assigned_to=agent,
                priority=priority,
                description=(
                    "QUANTIFIRE architecture task. Mission Control manages assignment, review, quality gates and "
                    "completion receipts; QUANTIFIRE remains the canonical domain system."
                ),
                metadata={"task_id": task_id, "architecture_registry": registry},
            )
        )
    return {"probe": probe, "agents": registrations, "tasks": tasks}
