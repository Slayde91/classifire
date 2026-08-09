from __future__ import annotations

import json

from sqlalchemy import select

from classifire.agent_security import AGENT_SCOPE_MAP, FORBIDDEN_AGENT_SCOPES, scopes_for_agent
from classifire.audit import record_audit
from classifire.db import SessionLocal
from classifire.models import AgentServicePrincipal


def main() -> int:
    changed: list[dict[str, object]] = []
    unchanged: list[str] = []
    missing: list[str] = []

    with SessionLocal() as db:
        for agent_id in sorted(AGENT_SCOPE_MAP):
            principal = db.scalar(
                select(AgentServicePrincipal).where(
                    AgentServicePrincipal.agent_id == agent_id
                )
            )
            if principal is None:
                missing.append(agent_id)
                continue

            desired = scopes_for_agent(agent_id)
            if set(desired) & FORBIDDEN_AGENT_SCOPES:
                raise RuntimeError(f"Forbidden machine scope configured for {agent_id}")

            previous = sorted(str(scope) for scope in (principal.scopes or []))
            if previous == desired:
                unchanged.append(agent_id)
                continue

            principal.scopes = desired
            principal.record_version += 1
            changed.append(
                {
                    "agent_id": agent_id,
                    "previous_scopes": previous,
                    "new_scopes": desired,
                    "token_rotated": False,
                }
            )
            record_audit(
                db,
                actor=None,
                actor_type="system",
                actor_name="CLASSIFIRE agent scope synchronizer",
                action="sync_agent_service_scopes",
                entity_type="agent_service_principal",
                entity_id=principal.id,
                previous_value={"scopes": previous},
                new_value={"scopes": desired, "token_rotated": False},
                reason="Synchronise persisted machine scopes with governed AGENT_SCOPE_MAP without rotating credentials",
            )

        if missing:
            raise RuntimeError(
                "Cannot synchronise agent scopes because these principals are missing: "
                + ", ".join(missing)
            )
        db.commit()

    print(
        json.dumps(
            {
                "ok": True,
                "changed": changed,
                "unchanged": unchanged,
                "token_rotation_performed": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
