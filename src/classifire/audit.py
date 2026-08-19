from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from .models import AuditEvent, User


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def record_audit(
    db: Session,
    *,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    previous_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
    reason: str | None = None,
    project_id: str | None = None,
    source_ip: str | None = None,
    correlation_id: str | None = None,
    actor_type: str = "user",
    actor_name: str | None = None,
) -> AuditEvent:
    payload = {
        "actor": actor.id if actor else actor_name or "system",
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "previous": previous_value,
        "new": new_value,
        "reason": reason,
        "project_id": project_id,
        "correlation_id": correlation_id,
    }
    event = AuditEvent(
        actor_user_id=actor.id if actor else None,
        actor_type=actor_type,
        actor_name=actor.full_name if actor else actor_name or "QUANTIFIRE system",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=project_id,
        previous_value=previous_value,
        new_value=new_value,
        reason=reason,
        source_ip=source_ip,
        correlation_id=correlation_id,
        event_hash=hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest(),
    )
    db.add(event)
    return event
