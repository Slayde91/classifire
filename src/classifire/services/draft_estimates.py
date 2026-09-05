"""Independent manual Draft Estimates with governed ownership and immutable revisions."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import (
    DraftEstimate,
    DraftEstimateRevision,
    DraftScope,
    DraftSystemMatch,
    User,
    new_id,
)
from ..security import has_permission
from .draft_estimate_contract import (
    MAX_ESTIMATE_BYTES,
    MAX_HISTORY,
    MAX_LINES,
    SCHEMA_VERSION,
    AddLine,
    Override,
    basis_hash,
    canonical,
    decimal_string,
    envelope_hash,
    line_amount,
    same_quantity,
    summary_for,
    target_for,
    validate_envelope,
)
from .draft_scope import DraftScopeError, _actor, _atomic, get_draft, read_revision
from .draft_system_matches import match_staleness, read_match_revision

ESTIMATE_LIST_LIMIT = 20


class DraftEstimateError(DraftScopeError):
    """Safe code only; customer descriptions, reasons, and rates never enter errors."""


def _access(
    db: Session,
    actor: User,
    draft_id: str,
    *,
    write: bool = False,
    attached: bool = False,
    export: bool = False,
) -> tuple[User, DraftScope]:
    try:
        actor = _actor(db, actor, "project:write" if write else "project:read")
        actor = _actor(db, actor, "estimate:read")
        if write:
            actor = _actor(db, actor, "estimate:write")
        if export:
            actor = _actor(db, actor, "estimate:export")
        if attached:
            actor = _actor(db, actor, "technical:read")
        return actor, get_draft(db, actor, draft_id)
    except DraftScopeError as exc:
        raise DraftEstimateError(exc.code, exc.status_code) from exc


def _estimate(
    db: Session,
    actor: User,
    draft_id: str,
    estimate_id: str,
    *,
    write: bool = False,
    export: bool = False,
) -> tuple[User, DraftScope, DraftEstimate]:
    actor, draft = _access(db, actor, draft_id, write=write, export=export)
    estimate = db.scalar(
        select(DraftEstimate)
        .where(DraftEstimate.id == estimate_id, DraftEstimate.draft_scope_id == draft.id)
        .execution_options(populate_existing=True)
    )
    if estimate is None:
        raise DraftEstimateError("ESTIMATE_NOT_FOUND", 404)
    actor, draft = _access(
        db, actor, draft_id, write=write, export=export, attached=estimate.match_id is not None
    )
    return actor, draft, estimate


def _scope(db: Session, actor: User, draft_id: str, revision: int | None = None) -> dict[str, Any]:
    try:
        return read_revision(db, actor, draft_id, revision)
    except DraftScopeError as exc:
        raise DraftEstimateError(exc.code, exc.status_code) from exc


def _match(db: Session, actor: User, draft_id: str, match_id: str, revision: int) -> dict[str, Any]:
    try:
        return read_match_revision(db, actor, draft_id, match_id, revision)
    except DraftScopeError as exc:
        raise DraftEstimateError(exc.code, exc.status_code) from exc


def _validate(
    envelope: dict[str, Any], code: str = "ESTIMATE_ARTIFACT_INVALID", status: int = 422
) -> None:
    try:
        validate_envelope(envelope)
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        RecursionError,
        ArithmeticError,
    ) as exc:
        raise DraftEstimateError(code, status) from exc


def _audit(
    db: Session,
    actor: User,
    draft: DraftScope,
    estimate_id: str,
    action: str,
    envelope: dict[str, Any],
) -> None:
    record_audit(
        db,
        actor=actor,
        action="draft_estimate." + action,
        entity_type="draft_estimate",
        entity_id=estimate_id,
        project_id=draft.project_id,
        new_value={
            "revision": envelope["revision"],
            "sha256": envelope["sha256"],
            "scope_sha256": envelope["scope"]["sha256"],
            "match_sha256": envelope["system_match"]["sha256"]
            if envelope["system_match"] is not None
            else None,
        },
    )


def _row(estimate_id: str, envelope: dict[str, Any], created: datetime) -> DraftEstimateRevision:
    return DraftEstimateRevision(
        estimate_id=estimate_id,
        revision=envelope["revision"],
        parent_hash=envelope["parent_hash"],
        content_hash=envelope["sha256"],
        envelope_json=canonical(envelope).decode("utf-8"),
        created_by_id=envelope["created_by"],
        created_at=created,
    )


def create_estimate(
    db: Session,
    actor: User,
    draft_id: str,
    scope_revision: int,
    *,
    currency: str = "AUD",
    match_id: str | None = None,
    match_revision: int | None = None,
) -> DraftEstimate:
    actor, draft = _access(db, actor, draft_id, write=True, attached=match_id is not None)
    if currency != "AUD":
        raise DraftEstimateError("ESTIMATE_CURRENCY_INVALID", 422)
    if type(scope_revision) is not int or scope_revision < 1:
        raise DraftEstimateError("DRAFT_REVISION_NOT_FOUND", 404)
    if (match_id is None) != (match_revision is None) or (
        match_revision is not None and (type(match_revision) is not int or match_revision < 1)
    ):
        raise DraftEstimateError("ESTIMATE_MATCH_INVALID", 422)
    scope = _scope(db, actor, draft_id, scope_revision)
    match = (
        _match(db, actor, draft_id, match_id, match_revision)
        if match_id is not None and match_revision is not None
        else None
    )
    if match is not None and match["scope"] != scope:
        raise DraftEstimateError("ESTIMATE_MATCH_SCOPE_MISMATCH", 422)
    try:
        with _atomic(db):
            actor, draft = _access(db, actor, draft_id, write=True, attached=match is not None)
            if _scope(db, actor, draft_id, scope_revision) != scope:
                raise DraftEstimateError("ESTIMATE_INPUT_CHANGED", 409)
            if (
                match is not None
                and _match(db, actor, draft_id, match["artifact_id"], match["revision"]) != match
            ):
                raise DraftEstimateError("ESTIMATE_INPUT_CHANGED", 409)
            actor, draft = _access(db, actor, draft_id, write=True, attached=match is not None)
            created = datetime.now(UTC)
            envelope = {
                "schema_version": SCHEMA_VERSION,
                "artifact_id": new_id(),
                "project_id": draft.project_id,
                "revision": 1,
                "parent_hash": None,
                "created_by": actor.id,
                "created_at": created.isoformat(),
                "state": "Draft",
                "review_status": "unreviewed",
                "provenance": "manual_unit_sell",
                "currency": currency,
                "tax_treatment": "excluded_not_calculated",
                "calculation_version": 1,
                "scope": scope,
                "system_match": match,
                "lines": [],
                "summary": summary_for(scope, []),
            }
            envelope["sha256"] = envelope_hash(envelope)
            _validate(envelope)
            estimate = DraftEstimate(
                id=envelope["artifact_id"],
                draft_scope_id=draft.id,
                scope_revision=scope_revision,
                scope_hash=scope["sha256"],
                match_id=match_id,
                match_revision=match_revision,
                match_hash=match["sha256"] if match is not None else None,
                latest_revision=1,
                latest_hash=envelope["sha256"],
                basis_hash=basis_hash(envelope),
                created_by_id=actor.id,
                created_at=created,
            )
            db.add(estimate)
            db.flush()
            db.add(_row(estimate.id, envelope, created))
            _audit(db, actor, draft, estimate.id, "create", envelope)
            db.flush()
        return estimate
    except IntegrityError as exc:
        raise DraftEstimateError("ESTIMATE_SAVE_CONFLICT", 409) from exc


def _read(
    db: Session, actor: User, draft: DraftScope, estimate: DraftEstimate, revision: int
) -> dict[str, Any]:
    if type(revision) is not int or not 1 <= revision <= estimate.latest_revision:
        raise DraftEstimateError("ESTIMATE_REVISION_NOT_FOUND", 404)
    row = db.scalar(
        select(DraftEstimateRevision)
        .where(
            DraftEstimateRevision.estimate_id == estimate.id,
            DraftEstimateRevision.revision == revision,
        )
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise DraftEstimateError("ESTIMATE_REVISION_INTEGRITY_FAILED", 409)
    try:
        if len(row.envelope_json.encode("utf-8")) > MAX_ESTIMATE_BYTES:
            raise ValueError("size")
        envelope = cast(dict[str, Any], json.loads(row.envelope_json))
        validate_envelope(envelope)
        created = (
            row.created_at.replace(tzinfo=UTC) if row.created_at.tzinfo is None else row.created_at
        )
        if (
            envelope["artifact_id"] != estimate.id
            or envelope["project_id"] != draft.project_id
            or envelope["revision"] != row.revision
            or envelope["parent_hash"] != row.parent_hash
            or envelope["created_by"] != row.created_by_id
            or envelope["created_at"] != created.astimezone(UTC).isoformat()
            or envelope["sha256"] != row.content_hash
            or canonical(envelope).decode("utf-8") != row.envelope_json
            or basis_hash(envelope) != estimate.basis_hash
        ):
            raise ValueError("binding")
        if (
            envelope["scope"]["artifact_id"] != draft.id
            or envelope["scope"]["revision"] != estimate.scope_revision
            or envelope["scope"]["sha256"] != estimate.scope_hash
            or _scope(db, actor, draft.id, estimate.scope_revision) != envelope["scope"]
        ):
            raise ValueError("scope")
        match = envelope["system_match"]
        if match is None:
            if any(
                value is not None
                for value in (estimate.match_id, estimate.match_revision, estimate.match_hash)
            ):
                raise ValueError("match")
        elif (
            match["artifact_id"] != estimate.match_id
            or match["revision"] != estimate.match_revision
            or match["sha256"] != estimate.match_hash
            or _match(db, actor, draft.id, match["artifact_id"], match["revision"]) != match
        ):
            raise ValueError("match")
        if revision == estimate.latest_revision and row.content_hash != estimate.latest_hash:
            raise ValueError("latest")
        if revision > 1:
            parent = db.scalar(
                select(DraftEstimateRevision.content_hash).where(
                    DraftEstimateRevision.estimate_id == estimate.id,
                    DraftEstimateRevision.revision == revision - 1,
                )
            )
            if parent is None or row.parent_hash != parent:
                raise ValueError("parent")
        return envelope
    except DraftScopeError as exc:
        if exc.status_code == 403:
            raise DraftEstimateError(exc.code, 403) from exc
        raise DraftEstimateError("ESTIMATE_REVISION_INTEGRITY_FAILED", 409) from exc
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        RecursionError,
        ArithmeticError,
    ) as exc:
        raise DraftEstimateError("ESTIMATE_REVISION_INTEGRITY_FAILED", 409) from exc


def read_estimate_revision(
    db: Session, actor: User, draft_id: str, estimate_id: str, revision: int | None = None
) -> dict[str, Any]:
    actor, draft, estimate = _estimate(db, actor, draft_id, estimate_id)
    return _read(
        db, actor, draft, estimate, estimate.latest_revision if revision is None else revision
    )


def list_estimates(db: Session, actor: User, draft_id: str) -> list[DraftEstimate]:
    actor, draft = _access(db, actor, draft_id)
    query = select(DraftEstimate).where(DraftEstimate.draft_scope_id == draft.id)
    if not has_permission(actor, "technical:read"):
        query = query.where(DraftEstimate.match_id.is_(None))
    estimates = list(
        db.scalars(
            query.order_by(DraftEstimate.created_at.desc(), DraftEstimate.id).limit(
                ESTIMATE_LIST_LIMIT
            )
        )
    )
    for estimate in estimates:
        _read(db, actor, draft, estimate, estimate.latest_revision)
    return estimates


def _editable(
    db: Session, actor: User, draft_id: str, estimate_id: str, expected_revision: int
) -> tuple[User, DraftScope, DraftEstimate, dict[str, Any]]:
    actor, draft, estimate = _estimate(db, actor, draft_id, estimate_id, write=True)
    if type(expected_revision) is not int or expected_revision != estimate.latest_revision:
        raise DraftEstimateError("ESTIMATE_REVISION_CONFLICT", 409)
    return actor, draft, estimate, _read(db, actor, draft, estimate, expected_revision)


def _save(
    db: Session,
    actor: User,
    draft: DraftScope,
    estimate: DraftEstimate,
    prior: dict[str, Any],
    envelope: dict[str, Any],
    action: str,
    created: datetime,
) -> dict[str, Any]:
    expected = prior["revision"]
    envelope.update(
        revision=expected + 1,
        parent_hash=prior["sha256"],
        created_by=actor.id,
        created_at=created.isoformat(),
        summary=summary_for(envelope["scope"], envelope["lines"]),
    )
    envelope["sha256"] = envelope_hash(envelope)
    _validate(envelope)
    try:
        with _atomic(db):
            actor, draft = _access(
                db, actor, draft.id, write=True, attached=estimate.match_id is not None
            )
            # Recheck retained dependencies before the CAS; upstream new revisions may be stale,
            # but corruption or lost access to the captured revision must refuse the mutation.
            _read(db, actor, draft, estimate, expected)
            actor, draft = _access(
                db, actor, draft.id, write=True, attached=estimate.match_id is not None
            )
            changed = db.execute(
                update(DraftEstimate)
                .where(
                    DraftEstimate.id == estimate.id,
                    DraftEstimate.draft_scope_id == draft.id,
                    DraftEstimate.latest_revision == expected,
                    DraftEstimate.latest_hash == prior["sha256"],
                    DraftEstimate.basis_hash == basis_hash(prior),
                )
                .values(latest_revision=expected + 1, latest_hash=envelope["sha256"])
                .execution_options(synchronize_session=False)
            )
            if changed.rowcount != 1:  # type: ignore[attr-defined]
                raise DraftEstimateError("ESTIMATE_REVISION_CONFLICT", 409)
            db.add(_row(estimate.id, envelope, created))
            _audit(db, actor, draft, estimate.id, action, envelope)
            db.flush()
        return envelope
    except IntegrityError as exc:
        raise DraftEstimateError("ESTIMATE_SAVE_CONFLICT", 409) from exc


def _event(
    actor: User,
    created: datetime,
    action: str,
    before_quantity: str | None,
    quantity: str | None,
    before_rate: str | None,
    rate: str | None,
    reason: str,
) -> dict[str, Any]:
    return {
        "event_id": new_id(),
        "action": action,
        "before_quantity": before_quantity,
        "quantity": quantity,
        "before_rate": before_rate,
        "unit_sell_rate": rate,
        "reason": reason,
        "created_by": actor.id,
        "created_at": created.isoformat(),
    }


def add_line(
    db: Session,
    actor: User,
    draft_id: str,
    estimate_id: str,
    expected_revision: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    actor, draft, estimate, prior = _editable(db, actor, draft_id, estimate_id, expected_revision)
    try:
        parsed = AddLine.model_validate(payload, strict=True).model_dump()
        target = target_for(prior["scope"], parsed["target_kind"], parsed["target_id"])
        if ("unit" in target and parsed["unit"] != target["unit"]) or (
            parsed["target_kind"] == "blank_opening" and parsed["unit"] not in ("each", "m2")
        ):
            raise ValueError("unit")
        quantity = decimal_string(parsed["quantity"], unit=parsed["unit"])
        rate = decimal_string(parsed["unit_sell_rate"])
        if (
            not parsed["description"].strip()
            or not parsed["source_note"].strip()
            or (
                not same_quantity(target["original_quantity"], quantity)
                and not parsed["reason"].strip()
            )
        ):
            raise ValueError("reason")
    except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
        raise DraftEstimateError("ESTIMATE_LINE_INVALID", 422) from exc
    recovery_key = parsed["target_kind"] + ":" + parsed["target_id"]
    if any(line["recovery_key"] == recovery_key for line in prior["lines"]):
        raise DraftEstimateError("ESTIMATE_TARGET_ALREADY_REPRESENTED", 409)
    if len(prior["lines"]) >= MAX_LINES:
        raise DraftEstimateError("ESTIMATE_LINE_LIMIT", 422)
    created = datetime.now(UTC)
    line = {
        **target,
        "line_id": new_id(),
        "recovery_key": recovery_key,
        "unit": parsed["unit"],
        "description": parsed["description"],
        "source_note": parsed["source_note"],
        "original_rate": rate,
        "quantity": quantity,
        "unit_sell_rate": rate,
        "status": "active",
        "omission_reason": "",
        "created_by": actor.id,
        "created_at": created.isoformat(),
        "history": [
            _event(
                actor,
                created,
                "added",
                target["original_quantity"],
                quantity,
                rate,
                rate,
                parsed["reason"],
            )
        ],
    }
    line["subtotal_ex_tax"], line["pricing_status"] = line_amount(line)
    envelope = copy.deepcopy(prior)
    envelope["lines"].append(line)
    return _save(db, actor, draft, estimate, prior, envelope, "add_line", created)


def _line(envelope: dict[str, Any], line_id: str) -> dict[str, Any]:
    line = next((item for item in envelope["lines"] if item["line_id"] == line_id), None)
    if line is None:
        raise DraftEstimateError("ESTIMATE_LINE_NOT_FOUND", 404)
    if len(line["history"]) >= MAX_HISTORY:
        raise DraftEstimateError("ESTIMATE_HISTORY_LIMIT", 422)
    return cast(dict[str, Any], line)


def override_line(
    db: Session,
    actor: User,
    draft_id: str,
    estimate_id: str,
    expected_revision: int,
    line_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    actor, draft, estimate, prior = _editable(db, actor, draft_id, estimate_id, expected_revision)
    envelope = copy.deepcopy(prior)
    line = _line(envelope, line_id)
    try:
        parsed = Override.model_validate(payload, strict=True).model_dump()
        quantity = decimal_string(parsed["quantity"], unit=line["unit"])
        rate = decimal_string(parsed["unit_sell_rate"])
        if not parsed["reason"].strip() or (
            quantity == line["quantity"] and rate == line["unit_sell_rate"]
        ):
            raise ValueError("reason_or_unchanged")
    except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
        raise DraftEstimateError("ESTIMATE_OVERRIDE_INVALID", 422) from exc
    created = datetime.now(UTC)
    line["history"].append(
        _event(
            actor,
            created,
            "override",
            line["quantity"],
            quantity,
            line["unit_sell_rate"],
            rate,
            parsed["reason"],
        )
    )
    line.update(quantity=quantity, unit_sell_rate=rate)
    line["subtotal_ex_tax"], line["pricing_status"] = line_amount(line)
    return _save(db, actor, draft, estimate, prior, envelope, "override_line", created)


def set_line_status(
    db: Session,
    actor: User,
    draft_id: str,
    estimate_id: str,
    expected_revision: int,
    line_id: str,
    status: str,
    reason: str,
) -> dict[str, Any]:
    actor, draft, estimate, prior = _editable(db, actor, draft_id, estimate_id, expected_revision)
    envelope = copy.deepcopy(prior)
    line = _line(envelope, line_id)
    if (
        status not in ("active", "omitted")
        or status == line["status"]
        or type(reason) is not str
        or not 1 <= len(reason.strip()) <= 4000
        or len(reason) > 4000
    ):
        raise DraftEstimateError("ESTIMATE_STATUS_INVALID", 422)
    created = datetime.now(UTC)
    action = "omitted" if status == "omitted" else "restored"
    line["history"].append(
        _event(
            actor,
            created,
            action,
            line["quantity"],
            line["quantity"],
            line["unit_sell_rate"],
            line["unit_sell_rate"],
            reason,
        )
    )
    line.update(status=status, omission_reason=reason if status == "omitted" else "")
    line["subtotal_ex_tax"], line["pricing_status"] = line_amount(line)
    return _save(db, actor, draft, estimate, prior, envelope, action, created)


def revision_bytes(
    db: Session, actor: User, draft_id: str, estimate_id: str, revision: int | None = None
) -> bytes:
    actor, draft, estimate = _estimate(db, actor, draft_id, estimate_id, export=True)
    envelope = _read(
        db, actor, draft, estimate, estimate.latest_revision if revision is None else revision
    )
    _audit(db, actor, draft, estimate.id, "download", envelope)
    db.flush()
    return canonical(envelope)


def estimate_staleness(
    db: Session,
    actor: User,
    draft_id: str,
    estimate_id: str,
    revision: int | None = None,
    *,
    storage_root: Path,
) -> list[str]:
    actor, draft, estimate = _estimate(db, actor, draft_id, estimate_id)
    envelope = _read(
        db, actor, draft, estimate, estimate.latest_revision if revision is None else revision
    )
    reasons = []
    if _scope(db, actor, draft_id)["sha256"] != envelope["scope"]["sha256"]:
        reasons.append("ESTIMATE_SCOPE_CHANGED")
    match = envelope["system_match"]
    if match is not None:
        current = db.get(DraftSystemMatch, match["artifact_id"], populate_existing=True)
        if (
            current is None
            or current.latest_revision != match["revision"]
            or current.latest_hash != match["sha256"]
        ):
            reasons.append("ESTIMATE_REVIEW_CHANGED")
        try:
            reasons.extend(
                match_staleness(
                    db,
                    actor,
                    draft_id,
                    match["artifact_id"],
                    match["revision"],
                    storage_root=storage_root,
                )
            )
        except DraftScopeError as exc:
            if exc.status_code == 403:
                raise DraftEstimateError(exc.code, 403) from exc
            reasons.append("ESTIMATE_REVIEW_DEPENDENCY_UNAVAILABLE")
    _access(db, actor, draft_id, attached=match is not None)
    return list(dict.fromkeys(reasons))
