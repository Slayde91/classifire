"""Independent, release-bound retirement receipts for technical variants."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Approval, LibraryRelease, TechnicalVariant
from .technical_governance import (
    GOVERNED_TECHNICAL_RELEASE_POLICIES,
    technical_approval_binding,
    technical_variant_snapshot_hash,
)

TECHNICAL_RETIREMENT_APPROVAL_TYPE = "technical_retirement"
TECHNICAL_RETIREMENT_POLICY = "technical-retirement-v1"
TECHNICAL_RETIREMENT_REASON_SCHEMA = "technical-retirement-reasons-v1"

_CONTEXT_FIELDS = frozenset(
    {
        "policy",
        "predecessor_release_id",
        "predecessor_release_hash",
        "predecessor_release_policy",
        "predecessor_record_id",
        "predecessor_record_hash",
        "predecessor_record_manifest_hash",
        "variant_snapshot_hash",
        "logical_key",
        "request_reason",
    }
)
_DECISION_FIELDS = frozenset({"schema", "request", "decision_reason"})
_BINDING_FIELDS = frozenset(
    {"policy", "request_context", "approval_binding", "decision_reason"}
)
_REASON_MAX_LENGTH = 4_000


class TechnicalRetirementError(ValueError):
    """A stable, presentation-safe retirement-governance failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _required_reason(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TechnicalRetirementError(code)
    normalised = value.strip()
    if len(normalised) > _REASON_MAX_LENGTH or any(
        not character.isprintable() and character not in {"\r", "\n", "\t"}
        for character in normalised
    ):
        raise TechnicalRetirementError(code)
    return normalised


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _canonical_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def technical_release_record_manifest_hash(record: dict[str, Any]) -> str:
    return _canonical_hash(record)


def technical_release_record(
    release: LibraryRelease,
    variant_id: str,
) -> dict[str, Any]:
    records = (release.source_manifest or {}).get("records")
    if not isinstance(records, list):
        raise TechnicalRetirementError("TECHNICAL_RETIREMENT_RELEASE_INVALID")
    matches = [
        item
        for item in records
        if isinstance(item, dict) and item.get("id") == variant_id
    ]
    if len(matches) != 1:
        raise TechnicalRetirementError("TECHNICAL_RETIREMENT_NOT_CURRENT_MEMBER")
    return matches[0]


def technical_retirement_request_context(
    release: LibraryRelease,
    record: dict[str, Any],
    variant: TechnicalVariant,
    request_reason: str,
) -> dict[str, Any]:
    manifest = release.source_manifest or {}
    policy = manifest.get("governance_policy")
    if (
        release.library_type != "technical"
        or policy not in GOVERNED_TECHNICAL_RELEASE_POLICIES
        or not isinstance(release.release_hash, str)
        or not release.release_hash
        or _canonical_hash(manifest) != release.release_hash
    ):
        raise TechnicalRetirementError("TECHNICAL_RETIREMENT_RELEASE_INVALID")
    if record.get("id") != variant.id:
        raise TechnicalRetirementError("TECHNICAL_RETIREMENT_RECORD_INVALID")
    record_hash = record.get("record_hash")
    logical_key = record.get("key")
    if (
        not isinstance(record_hash, str)
        or not record_hash
        or not isinstance(logical_key, str)
        or not logical_key
    ):
        raise TechnicalRetirementError("TECHNICAL_RETIREMENT_RECORD_INVALID")
    return {
        "policy": TECHNICAL_RETIREMENT_POLICY,
        "predecessor_release_id": release.id,
        "predecessor_release_hash": release.release_hash,
        "predecessor_release_policy": policy,
        "predecessor_record_id": variant.id,
        "predecessor_record_hash": record_hash,
        "predecessor_record_manifest_hash": technical_release_record_manifest_hash(
            record
        ),
        "variant_snapshot_hash": technical_variant_snapshot_hash(variant),
        "logical_key": logical_key,
        "request_reason": _required_reason(
            request_reason,
            "TECHNICAL_RETIREMENT_REQUEST_REASON_REQUIRED",
        ),
    }


def technical_retirement_snapshot_hash(context: dict[str, Any]) -> str:
    if set(context) != _CONTEXT_FIELDS:
        raise TechnicalRetirementError("TECHNICAL_RETIREMENT_CONTEXT_INVALID")
    return _canonical_hash(context)


def technical_retirement_decision_value(
    context: dict[str, Any],
    *,
    decision_reason: str | None = None,
) -> str:
    technical_retirement_snapshot_hash(context)
    value = {
        "schema": TECHNICAL_RETIREMENT_REASON_SCHEMA,
        "request": context,
        "decision_reason": (
            _required_reason(
                decision_reason,
                "TECHNICAL_RETIREMENT_DECISION_REASON_REQUIRED",
            )
            if decision_reason is not None
            else None
        ),
    }
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def technical_retirement_decision(
    approval: Approval,
) -> tuple[dict[str, Any], str | None]:
    try:
        value = json.loads(approval.decision_reason or "")
    except (TypeError, ValueError) as exc:
        raise TechnicalRetirementError("TECHNICAL_RETIREMENT_RECEIPT_INVALID") from exc
    if (
        not isinstance(value, dict)
        or set(value) != _DECISION_FIELDS
        or value.get("schema") != TECHNICAL_RETIREMENT_REASON_SCHEMA
        or not isinstance(value.get("request"), dict)
        or set(value["request"]) != _CONTEXT_FIELDS
    ):
        raise TechnicalRetirementError("TECHNICAL_RETIREMENT_RECEIPT_INVALID")
    decision_reason = value.get("decision_reason")
    if decision_reason is not None and not isinstance(decision_reason, str):
        raise TechnicalRetirementError("TECHNICAL_RETIREMENT_RECEIPT_INVALID")
    return value["request"], decision_reason


def latest_technical_retirement(
    db: Session,
    variant_id: str,
    *,
    for_update: bool = False,
    nowait: bool = False,
) -> Approval | None:
    receipts = technical_retirements(
        db,
        variant_id,
        for_update=for_update,
        nowait=nowait,
    )
    return (
        max(receipts, key=lambda receipt: (receipt.created_at, receipt.id))
        if receipts
        else None
    )


def technical_retirements(
    db: Session,
    variant_id: str,
    *,
    for_update: bool = False,
    nowait: bool = False,
) -> list[Approval]:
    statement = (
        select(Approval)
        .where(
            Approval.entity_type == "technical_variant",
            Approval.entity_id == variant_id,
            Approval.approval_type == TECHNICAL_RETIREMENT_APPROVAL_TYPE,
        )
        .order_by(Approval.id)
    )
    if for_update:
        statement = statement.with_for_update(nowait=nowait)
    return list(db.scalars(statement).all())


def validate_pending_technical_retirement(
    approval: Approval,
    release: LibraryRelease,
    record: dict[str, Any],
    variant: TechnicalVariant,
) -> dict[str, Any]:
    context, decision_reason = technical_retirement_decision(approval)
    if (
        approval.entity_type != "technical_variant"
        or approval.entity_id != variant.id
        or approval.approval_type != TECHNICAL_RETIREMENT_APPROVAL_TYPE
        or approval.status != "pending"
        or not approval.requested_by_id
        or approval.decided_by_id is not None
        or approval.decided_at is not None
        or decision_reason is not None
        or not approval.snapshot_hash
    ):
        raise TechnicalRetirementError("TECHNICAL_RETIREMENT_REQUEST_INVALID")
    expected = technical_retirement_request_context(
        release,
        record,
        variant,
        str(context.get("request_reason") or ""),
    )
    if context != expected or approval.snapshot_hash != technical_retirement_snapshot_hash(
        expected
    ):
        raise TechnicalRetirementError("TECHNICAL_RETIREMENT_REQUEST_STALE")
    return context


def validate_technical_retirement_approval(
    approval: Approval,
    release: LibraryRelease,
    record: dict[str, Any],
    variant: TechnicalVariant,
) -> dict[str, Any]:
    context, decision_reason = technical_retirement_decision(approval)
    normalised_decision_reason = _required_reason(
        decision_reason,
        "TECHNICAL_RETIREMENT_APPROVAL_INVALID",
    )
    if (
        approval.entity_type != "technical_variant"
        or approval.entity_id != variant.id
        or approval.approval_type != TECHNICAL_RETIREMENT_APPROVAL_TYPE
        or approval.status != "approved"
        or not approval.requested_by_id
        or not approval.decided_by_id
        or approval.requested_by_id == approval.decided_by_id
        or not approval.requested_at
        or not approval.decided_at
        or normalised_decision_reason != decision_reason
        or not approval.snapshot_hash
    ):
        raise TechnicalRetirementError("TECHNICAL_RETIREMENT_APPROVAL_INVALID")
    expected = technical_retirement_request_context(
        release,
        record,
        variant,
        str(context.get("request_reason") or ""),
    )
    if context != expected or approval.snapshot_hash != technical_retirement_snapshot_hash(
        expected
    ):
        raise TechnicalRetirementError("TECHNICAL_RETIREMENT_APPROVAL_STALE")
    return {
        "policy": TECHNICAL_RETIREMENT_POLICY,
        "request_context": context,
        "approval_binding": technical_approval_binding(approval),
        "decision_reason": decision_reason,
    }


def current_technical_retirement(
    db: Session,
    release: LibraryRelease,
    record: dict[str, Any],
    variant: TechnicalVariant,
    *,
    for_update: bool = False,
    nowait: bool = False,
) -> Approval | None:
    """Return the one exact-current live receipt, ignoring valid stale history."""

    current: list[Approval] = []
    for approval in technical_retirements(
        db,
        variant.id,
        for_update=for_update,
        nowait=nowait,
    ):
        if approval.status == "pending":
            try:
                validate_pending_technical_retirement(
                    approval,
                    release,
                    record,
                    variant,
                )
            except TechnicalRetirementError as exc:
                if exc.code == "TECHNICAL_RETIREMENT_REQUEST_STALE":
                    continue
                raise
            current.append(approval)
        elif approval.status == "approved":
            try:
                validate_technical_retirement_approval(
                    approval,
                    release,
                    record,
                    variant,
                )
            except TechnicalRetirementError as exc:
                if exc.code == "TECHNICAL_RETIREMENT_APPROVAL_STALE":
                    continue
                raise
            current.append(approval)
    if len(current) > 1:
        raise TechnicalRetirementError(
            "TECHNICAL_RETIREMENT_DUPLICATE_CURRENT_RECEIPTS"
        )
    return current[0] if current else None


def validate_technical_retirement_binding(
    binding: dict[str, Any],
    approval: Approval,
    release: LibraryRelease,
    record: dict[str, Any],
    variant: TechnicalVariant,
    *,
    publisher_id: str,
) -> None:
    if set(binding) != _BINDING_FIELDS:
        raise TechnicalRetirementError("TECHNICAL_RETIREMENT_BINDING_INVALID")
    expected = validate_technical_retirement_approval(
        approval,
        release,
        record,
        variant,
    )
    if binding != expected:
        raise TechnicalRetirementError("TECHNICAL_RETIREMENT_BINDING_INVALID")
    if publisher_id in {approval.requested_by_id, approval.decided_by_id}:
        raise TechnicalRetirementError(
            "TECHNICAL_RETIREMENT_INDEPENDENT_PUBLISHER_REQUIRED"
        )


__all__ = [
    "TECHNICAL_RETIREMENT_APPROVAL_TYPE",
    "TECHNICAL_RETIREMENT_POLICY",
    "TechnicalRetirementError",
    "current_technical_retirement",
    "latest_technical_retirement",
    "technical_release_record",
    "technical_retirement_decision",
    "technical_retirement_decision_value",
    "technical_retirement_request_context",
    "technical_retirement_snapshot_hash",
    "technical_retirements",
    "validate_pending_technical_retirement",
    "validate_technical_retirement_approval",
    "validate_technical_retirement_binding",
]
