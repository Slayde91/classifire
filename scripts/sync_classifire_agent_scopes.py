from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select

# Load the full governed ORM registry before writing AuditEvent rows. AuditEvent
# references audit_trails.id, whose table is defined in commercial_models.py.
# Standalone scripts do not automatically import the application model registry.
from classifire import canonical_models as _canonical_models  # noqa: F401
from classifire import commercial_models as _commercial_models  # noqa: F401
from classifire.agent_security import AGENT_SCOPE_MAP, FORBIDDEN_AGENT_SCOPES, scopes_for_agent
from classifire.audit import record_audit
from classifire.db import SessionLocal
from classifire.models import AgentServicePrincipal


def _sync_token_file_metadata(path: Path, *, agent_ids: set[str]) -> bool:
    path = path.expanduser().resolve()
    if not path.is_file():
        return False

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "CLASSIFIRE-AGENT-TOKENS-v1":
        raise RuntimeError(f"Unexpected CLASSIFIRE token-file schema: {path}")

    tokens = payload.get("tokens")
    if not isinstance(tokens, dict):
        raise RuntimeError(f"CLASSIFIRE token file has no tokens object: {path}")
    missing_tokens = [agent_id for agent_id in agent_ids if not tokens.get(agent_id)]
    if missing_tokens:
        raise RuntimeError(
            "CLASSIFIRE token file is missing agent token(s): " + ", ".join(sorted(missing_tokens))
        )

    # Preserve bearer tokens byte-for-byte; only refresh the non-secret scope metadata snapshot.
    existing_scopes = payload.get("scopes")
    if not isinstance(existing_scopes, dict):
        existing_scopes = {}
    payload["scopes"] = {
        **existing_scopes,
        **{
            agent_id: scopes_for_agent(agent_id)
            for agent_id in sorted(agent_ids)
        },
    }
    temp = path.with_suffix(path.suffix + ".scope-sync.tmp")
    temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp.replace(path)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Synchronise persisted CLASSIFIRE agent scopes with AGENT_SCOPE_MAP without rotating "
            "or replacing any existing bearer token."
        )
    )
    parser.add_argument(
        "--token-file",
        type=Path,
        default=Path.home() / ".openclaw" / "classifire-agent-tokens.json",
    )
    parser.add_argument(
        "--agent",
        choices=sorted(AGENT_SCOPE_MAP),
        help=(
            "Synchronise one existing agent only. Use for a staged deployment where "
            "a newer agent principal has not yet been provisioned."
        ),
    )
    args = parser.parse_args()

    target_agent_ids = {args.agent} if args.agent else set(AGENT_SCOPE_MAP)

    changed: list[dict[str, object]] = []
    unchanged: list[str] = []
    missing: list[str] = []

    with SessionLocal() as db:
        for agent_id in sorted(target_agent_ids):
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
                reason=(
                    "Synchronise persisted machine scopes with governed AGENT_SCOPE_MAP "
                    "without rotating credentials"
                ),
            )

        if missing:
            raise RuntimeError(
                "Cannot synchronise agent scopes because these principals are missing: "
                + ", ".join(missing)
            )
        db.commit()

    token_file_updated = _sync_token_file_metadata(
        args.token_file,
        agent_ids=target_agent_ids,
    )

    print(
        json.dumps(
            {
                "ok": True,
                "changed": changed,
                "unchanged": unchanged,
                "token_rotation_performed": False,
                "target_agents": sorted(target_agent_ids),
                "token_file_metadata_updated": token_file_updated,
                "token_file": str(args.token_file.expanduser().resolve()),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
