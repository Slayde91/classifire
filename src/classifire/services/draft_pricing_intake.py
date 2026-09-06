"""Draft pricing workbook intake and explicit source-bound rate application."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess  # nosec B404
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..config import Settings
from ..models import (
    DraftPricingRowObservation,
    DraftPricingSource,
    DraftPricingSourceProfile,
    DraftPricingSourceProfileDecision,
    DraftScope,
    User,
    new_id,
)
from . import draft_estimates as estimates
from .draft_estimate_contract import line_amount
from .draft_pricing_contract import (
    PROFILE_DECISION_SCHEMA,
    PROFILE_DECISIONS,
    PROFILE_SCHEMA,
    ROW_OBSERVATION_SCHEMA,
    digest,
    preview_rows,
    profile_definition,
    row_observation_definition,
    validate_dataset_kind,
    validate_profile_decision_envelope,
    validate_profile_envelope,
    validate_row_observation_envelope,
)
from .draft_scope import DraftScopeError, _actor, _atomic, get_draft
from .draft_source_intake import DraftSourceIntake, SourcePolicy
from .draft_system_match_contract import canonical

SCHEMA = "CLASSIFIRE-DRAFT-PRICING-XLSX-v1"
MAX_PROFILE_REVISIONS = 20


def _process(content: bytes) -> bytes:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}
    }
    environment.update(
        PYTHONPATH=str(Path(__file__).resolve().parents[2]),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONIOENCODING="utf-8",
    )
    try:
        result = subprocess.run(  # noqa: S603 # nosec B603
            [sys.executable, "-m", "classifire.services.draft_pricing_worker"],
            input=content,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
            env=environment,
        )
        if result.returncode != 0 or not 1 <= len(result.stdout) <= 2 * 1024 * 1024:
            raise ValueError("parser")
        value = json.loads(result.stdout)
        if (
            value["schema"] != SCHEMA
            or value["manifest"]["source_sha256"] != hashlib.sha256(content).hexdigest()
            or value["manifest"]["source_size_bytes"] != len(content)
            or not 1 <= len(value["sheets"]) <= 10
        ):
            raise ValueError("parser binding")
        return result.stdout
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError) as exc:
        raise DraftScopeError("PRICING_XLSX_PROCESSING_FAILED", 422) from exc


def intake() -> DraftSourceIntake:
    return DraftSourceIntake(
        SourcePolicy(
            model=DraftPricingSource,
            purpose="draft_pricing_xlsx",
            extension=".xlsx",
            magic=b"PK",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            schema=SCHEMA,
            code_prefix="PRICING_XLSX_",
            audit_name="draft_pricing",
            process=_process,
            valid_document=lambda value: 1 <= len(value["sheets"]) <= 10,
            read_permissions=("estimate:read", "library:read"),
            write_permissions=("estimate:write",),
        )
    )


def retain_source(
    db: Session,
    actor: User,
    draft_id: str,
    filename: str,
    content: bytes,
    dataset_kind: str,
    *,
    settings: Settings,
) -> DraftPricingSource:
    try:
        dataset_kind = validate_dataset_kind(dataset_kind)
    except ValueError as exc:
        raise DraftScopeError("PRICING_DATASET_KIND_INVALID", 422) from exc
    source_api = intake()
    with _atomic(db):
        source = cast(
            DraftPricingSource,
            source_api.retain(db, actor, draft_id, filename, content, settings=settings),
        )
        actor, locked = source_api._source(
            db, actor, draft_id, source.id, write=True, lock=True
        )
        source = cast(DraftPricingSource, locked)
        if source.dataset_kind is not None:
            if source.dataset_kind != dataset_kind:
                raise DraftScopeError("PRICING_DATASET_KIND_CONFLICT", 409)
            return source
        draft = get_draft(db, actor, draft_id)
        db.scalar(select(DraftScope.id).where(DraftScope.id == draft_id).with_for_update())
        prior = db.scalars(
            select(DraftPricingSource)
            .where(
                DraftPricingSource.draft_scope_id == draft_id,
                DraftPricingSource.dataset_kind == dataset_kind,
            )
            .order_by(DraftPricingSource.dataset_version.desc())
            .with_for_update()
        ).all()
        source.dataset_id = prior[0].dataset_id if prior else new_id()
        source.dataset_kind = dataset_kind
        source.dataset_version = (cast(int, prior[0].dataset_version) + 1) if prior else 1
        record_audit(
            db,
            actor=actor,
            action="draft_pricing.dataset_version.create",
            entity_type="draft_pricing_source",
            entity_id=source.id,
            project_id=draft.project_id,
            new_value={
                "dataset_id": source.dataset_id,
                "dataset_kind": source.dataset_kind,
                "dataset_version": source.dataset_version,
                "source_sha256": source.source_sha256,
            },
        )
        db.flush()
        return source


def source_info(
    db: Session, actor: User, draft_id: str, source_id: str
) -> dict[str, Any]:
    source_api = intake()
    value = source_api.source_info(db, actor, draft_id, source_id)
    _, row = source_api._source(db, actor, draft_id, source_id)
    source = cast(DraftPricingSource, row)
    latest = db.scalar(
        select(func.max(DraftPricingSourceProfile.revision)).where(
            DraftPricingSourceProfile.source_id == source_id,
            DraftPricingSourceProfile.draft_scope_id == draft_id,
        )
    )
    value.update(
        dataset_id=source.dataset_id,
        dataset_kind=source.dataset_kind,
        dataset_version=source.dataset_version,
        latest_profile_revision=latest or 0,
    )
    return value


def list_sources(db: Session, actor: User, draft_id: str) -> list[dict[str, Any]]:
    return [
        source_info(db, actor, draft_id, item["id"])
        for item in intake().list_sources(db, actor, draft_id)
    ]


def preview_profile(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    sheet_index: int,
    header_row: int,
    mapping: dict[str, int | None],
    price_meaning: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    source, document, _ = intake()._document(
        db, actor, draft_id, source_id, settings.storage_root
    )
    source = cast(DraftPricingSource, source)
    if (
        source.dataset_id is None
        or source.dataset_kind is None
        or source.dataset_version is None
        or source.document_sha256 is None
    ):
        raise DraftScopeError("PRICING_DATASET_KIND_REQUIRED", 409)
    try:
        definition, rows = profile_definition(
            document,
            draft_scope_id=draft_id,
            source_id=source.id,
            dataset_id=source.dataset_id,
            dataset_kind=source.dataset_kind,
            dataset_version=source.dataset_version,
            source_sha256=source.source_sha256,
            source_size_bytes=source.source_size_bytes,
            original_filename=source.original_filename,
            document_sha256=source.document_sha256,
            sheet_index=sheet_index,
            header_row=header_row,
            mapping=mapping,
            price_meaning=price_meaning,
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise DraftScopeError("PRICING_PROFILE_INVALID", 422) from exc
    return {"definition": definition, "preview_hash": digest(definition), "rows": rows}


def _profile_row(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    profile_id: str,
) -> tuple[DraftPricingSource, DraftPricingSourceProfile]:
    _, source_row = intake()._source(db, actor, draft_id, source_id)
    source = cast(DraftPricingSource, source_row)
    row = db.scalar(
        select(DraftPricingSourceProfile).where(
            DraftPricingSourceProfile.id == profile_id,
            DraftPricingSourceProfile.source_id == source_id,
            DraftPricingSourceProfile.draft_scope_id == draft_id,
        )
    )
    if row is None:
        raise DraftScopeError("PRICING_PROFILE_NOT_FOUND", 404)
    return source, row


def _profile_value(
    source: DraftPricingSource, row: DraftPricingSourceProfile
) -> dict[str, Any]:
    try:
        raw = row.profile_json.encode("utf-8")
        value = json.loads(raw)
        validate_profile_envelope(value)
        definition = value["definition"]
        if (
            len(raw) > 131072
            or hashlib.sha256(raw).hexdigest() != row.profile_sha256
            or value["profile_id"] != row.id
            or value["revision"] != row.revision
            or value["parent_profile_sha256"] != row.parent_profile_sha256
            or value["created_by_id"] != row.created_by_id
            or definition["draft_scope_id"] != row.draft_scope_id
            or definition["source"]["id"] != source.id
            or definition["source"]["sha256"] != source.source_sha256
            or definition["source"]["size_bytes"] != source.source_size_bytes
            or definition["source"]["document_sha256"] != source.document_sha256
            or definition["dataset"]["id"] != source.dataset_id
            or definition["dataset"]["kind"] != source.dataset_kind
            or definition["dataset"]["version"] != source.dataset_version
        ):
            raise ValueError("profile binding")
    except (ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
        raise DraftScopeError("PRICING_PROFILE_INTEGRITY_FAILED", 409) from exc
    return cast(dict[str, Any], value)


def read_profile(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    profile_id: str,
) -> dict[str, Any]:
    source, row = _profile_row(db, actor, draft_id, source_id, profile_id)
    return _profile_value(source, row)


def profile_bytes(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    profile_id: str,
) -> bytes:
    source, row = _profile_row(db, actor, draft_id, source_id, profile_id)
    _profile_value(source, row)
    return row.profile_json.encode("utf-8")


def list_profiles(
    db: Session, actor: User, draft_id: str, source_id: str
) -> list[dict[str, Any]]:
    _, source_row = intake()._source(db, actor, draft_id, source_id)
    source = cast(DraftPricingSource, source_row)
    rows = db.scalars(
        select(DraftPricingSourceProfile)
        .where(
            DraftPricingSourceProfile.source_id == source_id,
            DraftPricingSourceProfile.draft_scope_id == draft_id,
        )
        .order_by(DraftPricingSourceProfile.revision.desc())
        .limit(MAX_PROFILE_REVISIONS)
    ).all()
    return [
        {
            "id": row.id,
            "revision": row.revision,
            "profile_sha256": row.profile_sha256,
            "created_at": row.created_at,
            "value": _profile_value(source, row),
        }
        for row in rows
    ]


def _decision_value(
    source: DraftPricingSource,
    profile: DraftPricingSourceProfile,
    row: DraftPricingSourceProfileDecision,
) -> dict[str, Any]:
    _profile_value(source, profile)
    try:
        raw = row.decision_json.encode("utf-8")
        value = json.loads(raw)
        validate_profile_decision_envelope(value)
        if (
            len(raw) > 16384
            or hashlib.sha256(raw).hexdigest() != row.decision_sha256
            or value["decision_id"] != row.id
            or value["draft_scope_id"] != row.draft_scope_id
            or value["source_id"] != row.source_id
            or value["profile_id"] != row.profile_id
            or value["profile_revision"] != row.profile_revision
            or value["profile_sha256"] != row.profile_sha256
            or value["decision"] != row.decision
            or value["reason"] != row.reason
            or value["reviewed_by_id"] != row.reviewed_by_id
            or row.draft_scope_id != profile.draft_scope_id
            or row.source_id != profile.source_id
            or row.profile_id != profile.id
            or row.profile_revision != profile.revision
            or row.profile_sha256 != profile.profile_sha256
        ):
            raise ValueError("profile decision binding")
    except (ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
        raise DraftScopeError("PRICING_PROFILE_DECISION_INTEGRITY_FAILED", 409) from exc
    return cast(dict[str, Any], value)


def list_profile_decisions(
    db: Session, actor: User, draft_id: str, source_id: str
) -> list[dict[str, Any]]:
    _, source_row = intake()._source(db, actor, draft_id, source_id)
    source = cast(DraftPricingSource, source_row)
    latest_revision = db.scalar(
        select(func.max(DraftPricingSourceProfile.revision)).where(
            DraftPricingSourceProfile.source_id == source_id,
            DraftPricingSourceProfile.draft_scope_id == draft_id,
        )
    )
    rows = db.execute(
        select(DraftPricingSourceProfileDecision, DraftPricingSourceProfile)
        .join(
            DraftPricingSourceProfile,
            DraftPricingSourceProfile.id == DraftPricingSourceProfileDecision.profile_id,
        )
        .where(
            DraftPricingSourceProfileDecision.source_id == source_id,
            DraftPricingSourceProfileDecision.draft_scope_id == draft_id,
        )
        .order_by(DraftPricingSourceProfileDecision.created_at.desc())
        .limit(MAX_PROFILE_REVISIONS)
    ).all()
    return [
        {
            "id": decision.id,
            "profile_id": profile.id,
            "profile_revision": profile.revision,
            "decision_sha256": decision.decision_sha256,
            "reviewed_at": decision.created_at,
            "reviewed_by": cast(User, db.get(User, decision.reviewed_by_id)).full_name,
            "is_current": profile.revision == latest_revision,
            "value": _decision_value(source, profile, decision),
        }
        for decision, profile in rows
    ]


def _decision_row(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    profile_id: str,
    decision_id: str,
) -> tuple[DraftPricingSource, DraftPricingSourceProfile, DraftPricingSourceProfileDecision]:
    source, profile = _profile_row(db, actor, draft_id, source_id, profile_id)
    row = db.scalar(
        select(DraftPricingSourceProfileDecision).where(
            DraftPricingSourceProfileDecision.id == decision_id,
            DraftPricingSourceProfileDecision.profile_id == profile_id,
            DraftPricingSourceProfileDecision.source_id == source_id,
            DraftPricingSourceProfileDecision.draft_scope_id == draft_id,
        )
    )
    if row is None:
        raise DraftScopeError("PRICING_PROFILE_DECISION_NOT_FOUND", 404)
    return source, profile, row


def read_profile_decision(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    profile_id: str,
    decision_id: str,
) -> dict[str, Any]:
    source, profile, row = _decision_row(
        db, actor, draft_id, source_id, profile_id, decision_id
    )
    return _decision_value(source, profile, row)


def profile_decision_bytes(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    profile_id: str,
    decision_id: str,
) -> bytes:
    source, profile, row = _decision_row(
        db, actor, draft_id, source_id, profile_id, decision_id
    )
    _decision_value(source, profile, row)
    return row.decision_json.encode("utf-8")


def save_profile_decision(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    profile_id: str,
    expected_profile_sha256: str,
    decision: str,
    reason: str,
) -> dict[str, Any]:
    with _atomic(db):
        source, _ = _profile_row(db, actor, draft_id, source_id, profile_id)
        actor = _actor(db, actor, "pricing:approve")
        source_api = intake()
        source_api._postgres(db)
        source = cast(
            DraftPricingSource,
            db.scalar(
                select(DraftPricingSource)
                .where(
                    DraftPricingSource.id == source_id,
                    DraftPricingSource.draft_scope_id == draft_id,
                )
                .execution_options(populate_existing=True)
                .with_for_update()
            ),
        )
        profile = db.scalar(
            select(DraftPricingSourceProfile)
            .where(
                DraftPricingSourceProfile.id == profile_id,
                DraftPricingSourceProfile.source_id == source_id,
                DraftPricingSourceProfile.draft_scope_id == draft_id,
            )
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if profile is None:
            raise DraftScopeError("PRICING_PROFILE_NOT_FOUND", 404)
        _profile_value(source, profile)
        latest = db.scalar(
            select(DraftPricingSourceProfile)
            .where(
                DraftPricingSourceProfile.source_id == source_id,
                DraftPricingSourceProfile.draft_scope_id == draft_id,
            )
            .order_by(DraftPricingSourceProfile.revision.desc())
            .limit(1)
            .with_for_update()
        )
        if latest is None or latest.id != profile.id:
            raise DraftScopeError("PRICING_PROFILE_STALE", 409)
        if expected_profile_sha256 != profile.profile_sha256:
            raise DraftScopeError("PRICING_PROFILE_CHANGED", 409)
        existing = db.scalar(
            select(DraftPricingSourceProfileDecision).where(
                DraftPricingSourceProfileDecision.profile_id == profile_id
            )
        )
        if existing is not None:
            raise DraftScopeError("PRICING_PROFILE_ALREADY_REVIEWED", 409)
        normalized_reason = reason.strip() if type(reason) is str else reason
        if decision not in PROFILE_DECISIONS or type(normalized_reason) is not str:
            raise DraftScopeError("PRICING_PROFILE_DECISION_INVALID", 422)
        reviewed = datetime.now(UTC)
        decision_id = new_id()
        envelope = {
            "schema_version": PROFILE_DECISION_SCHEMA,
            "decision_id": decision_id,
            "draft_scope_id": draft_id,
            "source_id": source_id,
            "profile_id": profile_id,
            "profile_revision": profile.revision,
            "profile_sha256": profile.profile_sha256,
            "decision": decision,
            "reason": normalized_reason,
            "reviewed_at": reviewed.isoformat(),
            "reviewed_by_id": actor.id,
            "effects": {
                "rows_ingested": False,
                "library_activated": False,
                "technical_approval_granted": False,
                "system_matching_performed": False,
                "price_inference_performed": False,
                "estimate_changed": False,
                "release_performed": False,
            },
        }
        try:
            validate_profile_decision_envelope(envelope)
            raw = canonical(envelope)
        except (ValueError, TypeError, KeyError) as exc:
            raise DraftScopeError("PRICING_PROFILE_DECISION_INVALID", 422) from exc
        row = DraftPricingSourceProfileDecision(
            id=decision_id,
            draft_scope_id=draft_id,
            source_id=source_id,
            profile_id=profile_id,
            profile_revision=profile.revision,
            profile_sha256=profile.profile_sha256,
            decision=decision,
            reason=normalized_reason,
            decision_json=raw.decode("utf-8"),
            decision_sha256=hashlib.sha256(raw).hexdigest(),
            reviewed_by_id=actor.id,
            created_at=reviewed,
            updated_at=reviewed,
        )
        db.add(row)
        draft = get_draft(db, actor, draft_id)
        record_audit(
            db,
            actor=actor,
            action="draft_pricing.profile.review",
            entity_type="draft_pricing_source_profile_decision",
            entity_id=row.id,
            project_id=draft.project_id,
            new_value={
                "decision": decision,
                "profile_id": profile_id,
                "profile_revision": profile.revision,
                "profile_sha256": profile.profile_sha256,
                "decision_sha256": row.decision_sha256,
            },
            reason=normalized_reason,
        )
        db.flush()
        return envelope


def _row_observation_context(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    profile_id: str,
    row_number: int,
    *,
    settings: Settings,
    lock: bool = False,
) -> tuple[
    User,
    DraftPricingSource,
    DraftPricingSourceProfile,
    DraftPricingSourceProfileDecision,
    dict[str, Any],
    dict[str, Any],
]:
    source, _ = _profile_row(db, actor, draft_id, source_id, profile_id)
    actor = _actor(db, actor, "pricing:approve")
    if lock:
        intake()._postgres(db)
        source = cast(
            DraftPricingSource,
            db.scalar(
                select(DraftPricingSource)
                .where(
                    DraftPricingSource.id == source_id,
                    DraftPricingSource.draft_scope_id == draft_id,
                )
                .execution_options(populate_existing=True)
                .with_for_update()
            ),
        )
    profile = db.scalar(
        select(DraftPricingSourceProfile)
        .where(
            DraftPricingSourceProfile.id == profile_id,
            DraftPricingSourceProfile.source_id == source_id,
            DraftPricingSourceProfile.draft_scope_id == draft_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update(nowait=False) if lock else
        select(DraftPricingSourceProfile).where(
            DraftPricingSourceProfile.id == profile_id,
            DraftPricingSourceProfile.source_id == source_id,
            DraftPricingSourceProfile.draft_scope_id == draft_id,
        )
    )
    if profile is None:
        raise DraftScopeError("PRICING_PROFILE_NOT_FOUND", 404)
    profile_value = _profile_value(source, profile)
    definition = profile_value["definition"]
    if source.dataset_kind != "general_pricelist":
        raise DraftScopeError("PRICING_ROW_DATASET_A_REQUIRED", 409)
    latest_source = db.scalar(
        select(DraftPricingSource)
        .where(
            DraftPricingSource.draft_scope_id == draft_id,
            DraftPricingSource.dataset_id == source.dataset_id,
        )
        .order_by(DraftPricingSource.dataset_version.desc())
        .limit(1)
        .with_for_update() if lock else
        select(DraftPricingSource)
        .where(
            DraftPricingSource.draft_scope_id == draft_id,
            DraftPricingSource.dataset_id == source.dataset_id,
        )
        .order_by(DraftPricingSource.dataset_version.desc())
        .limit(1)
    )
    if latest_source is None or latest_source.id != source.id:
        raise DraftScopeError("PRICING_SOURCE_STALE", 409)
    latest_profile = db.scalar(
        select(DraftPricingSourceProfile)
        .where(
            DraftPricingSourceProfile.source_id == source_id,
            DraftPricingSourceProfile.draft_scope_id == draft_id,
        )
        .order_by(DraftPricingSourceProfile.revision.desc())
        .limit(1)
        .with_for_update() if lock else
        select(DraftPricingSourceProfile)
        .where(
            DraftPricingSourceProfile.source_id == source_id,
            DraftPricingSourceProfile.draft_scope_id == draft_id,
        )
        .order_by(DraftPricingSourceProfile.revision.desc())
        .limit(1)
    )
    if latest_profile is None or latest_profile.id != profile.id:
        raise DraftScopeError("PRICING_PROFILE_STALE", 409)
    decision = db.scalar(
        select(DraftPricingSourceProfileDecision)
        .where(DraftPricingSourceProfileDecision.profile_id == profile_id)
        .with_for_update() if lock else
        select(DraftPricingSourceProfileDecision).where(
            DraftPricingSourceProfileDecision.profile_id == profile_id
        )
    )
    if decision is None:
        raise DraftScopeError("PRICING_PROFILE_APPROVAL_REQUIRED", 409)
    decision_value = _decision_value(source, profile, decision)
    if decision_value["decision"] != "approve":
        raise DraftScopeError("PRICING_PROFILE_APPROVAL_REQUIRED", 409)
    if definition["commercial_basis"]["price_meaning"] == "unknown":
        raise DraftScopeError("PRICING_PRICE_MEANING_REQUIRED", 409)
    document_source, document, _ = intake()._document(
        db, actor, draft_id, source_id, settings.storage_root
    )
    if document_source.id != source.id or document_source.document_sha256 != source.document_sha256:
        raise DraftScopeError("PRICING_SOURCE_CHANGED", 409)
    selection = definition["selection"]
    try:
        rows = preview_rows(
            document,
            selection["sheet_index"],
            selection["header_row"],
            selection["mapping"],
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise DraftScopeError("PRICING_ROW_INVALID", 422) from exc
    row = next((item for item in rows if item["row"] == row_number), None)
    if row is None:
        raise DraftScopeError("PRICING_ROW_NOT_FOUND", 404)
    if row["problems"]:
        raise DraftScopeError("PRICING_ROW_UNUSABLE", 422)
    return actor, source, profile, decision, profile_value, row


def preview_row_observation(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    profile_id: str,
    row_number: int,
    item_kind: str,
    normalized_reference: str,
    evidence_state: str,
    review_reason: str,
    unresolved_fields: list[str],
    *,
    settings: Settings,
) -> dict[str, Any]:
    _, source, profile, decision, profile_value, row = _row_observation_context(
        db,
        actor,
        draft_id,
        source_id,
        profile_id,
        row_number,
        settings=settings,
    )
    try:
        definition = row_observation_definition(
            draft_scope_id=draft_id,
            dataset={
                "id": source.dataset_id,
                "kind": source.dataset_kind,
                "version": source.dataset_version,
            },
            source={
                "id": source.id,
                "sha256": source.source_sha256,
                "size_bytes": source.source_size_bytes,
                "document_sha256": source.document_sha256,
            },
            profile={
                "id": profile.id,
                "revision": profile.revision,
                "sha256": profile.profile_sha256,
                "decision_id": decision.id,
                "decision_sha256": decision.decision_sha256,
                "price_meaning": profile_value["definition"]["commercial_basis"][
                    "price_meaning"
                ],
            },
            row=row,
            item_kind=item_kind,
            normalized_reference=normalized_reference,
            evidence_state=evidence_state,
            review_reason=review_reason,
            unresolved_fields=unresolved_fields,
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise DraftScopeError("PRICING_ROW_OBSERVATION_INVALID", 422) from exc
    return {"definition": definition, "preview_hash": digest(definition)}


def save_row_observation(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    profile_id: str,
    row_number: int,
    item_kind: str,
    normalized_reference: str,
    evidence_state: str,
    review_reason: str,
    unresolved_fields: list[str],
    expected_profile_sha256: str,
    expected_decision_sha256: str,
    expected_row_sha256: str,
    expected_preview_hash: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    with _atomic(db):
        actor, source, profile, decision, _, row = _row_observation_context(
            db,
            actor,
            draft_id,
            source_id,
            profile_id,
            row_number,
            settings=settings,
            lock=True,
        )
        if (
            profile.profile_sha256 != expected_profile_sha256
            or decision.decision_sha256 != expected_decision_sha256
            or row["sha256"] != expected_row_sha256
        ):
            raise DraftScopeError("PRICING_ROW_CHANGED", 409)
        existing = db.scalar(
            select(DraftPricingRowObservation).where(
                DraftPricingRowObservation.profile_id == profile_id,
                DraftPricingRowObservation.sheet_index == row["sheet_index"],
                DraftPricingRowObservation.row_number == row_number,
            )
        )
        if existing is not None:
            raise DraftScopeError("PRICING_ROW_ALREADY_REVIEWED", 409)
        try:
            preview = preview_row_observation(
                db,
                actor,
                draft_id,
                source_id,
                profile_id,
                row_number,
                item_kind,
                normalized_reference,
                evidence_state,
                review_reason,
                unresolved_fields,
                settings=settings,
            )
        except (ValueError, TypeError, KeyError) as exc:
            raise DraftScopeError("PRICING_ROW_OBSERVATION_INVALID", 422) from exc
        if preview["preview_hash"] != expected_preview_hash:
            raise DraftScopeError("PRICING_ROW_CHANGED", 409)
        reviewed = datetime.now(UTC)
        observation_id = new_id()
        envelope = {
            "schema_version": ROW_OBSERVATION_SCHEMA,
            "observation_id": observation_id,
            "reviewed_at": reviewed.isoformat(),
            "reviewed_by_id": actor.id,
            "definition": preview["definition"],
            "definition_sha256": expected_preview_hash,
        }
        try:
            validate_row_observation_envelope(envelope)
            raw = canonical(envelope)
        except (ValueError, TypeError, KeyError) as exc:
            raise DraftScopeError("PRICING_ROW_OBSERVATION_INVALID", 422) from exc
        interpretation = envelope["definition"]["interpretation"]
        stored = DraftPricingRowObservation(
            id=observation_id,
            draft_scope_id=draft_id,
            source_id=source_id,
            profile_id=profile_id,
            profile_decision_id=decision.id,
            dataset_id=cast(str, source.dataset_id),
            dataset_version=cast(int, source.dataset_version),
            source_sha256=source.source_sha256,
            document_sha256=cast(str, source.document_sha256),
            profile_revision=profile.revision,
            profile_sha256=profile.profile_sha256,
            decision_sha256=decision.decision_sha256,
            sheet_index=row["sheet_index"],
            row_number=row_number,
            row_sha256=row["sha256"],
            item_kind=interpretation["item_kind"],
            normalized_reference=interpretation["normalized_reference"],
            evidence_state=interpretation["evidence_state"],
            review_reason=interpretation["review_reason"],
            observation_json=raw.decode("utf-8"),
            observation_sha256=hashlib.sha256(raw).hexdigest(),
            reviewed_by_id=actor.id,
            created_at=reviewed,
            updated_at=reviewed,
        )
        db.add(stored)
        draft = get_draft(db, actor, draft_id)
        record_audit(
            db,
            actor=actor,
            action="draft_pricing.row_observation.save",
            entity_type="draft_pricing_row_observation",
            entity_id=observation_id,
            project_id=draft.project_id,
            new_value={
                "profile_id": profile_id,
                "profile_revision": profile.revision,
                "row_number": row_number,
                "row_sha256": row["sha256"],
                "item_kind": interpretation["item_kind"],
                "evidence_state": interpretation["evidence_state"],
                "observation_sha256": stored.observation_sha256,
            },
            reason=interpretation["review_reason"],
        )
        db.flush()
        return envelope


def _row_observation_value(row: DraftPricingRowObservation) -> dict[str, Any]:
    try:
        raw = row.observation_json.encode("utf-8")
        value = json.loads(raw)
        validate_row_observation_envelope(value)
        definition = value["definition"]
        if (
            len(raw) > 131072
            or hashlib.sha256(raw).hexdigest() != row.observation_sha256
            or value["observation_id"] != row.id
            or value["reviewed_by_id"] != row.reviewed_by_id
            or definition["draft_scope_id"] != row.draft_scope_id
            or definition["dataset"]["id"] != row.dataset_id
            or definition["dataset"]["version"] != row.dataset_version
            or definition["source"]["id"] != row.source_id
            or definition["source"]["sha256"] != row.source_sha256
            or definition["source"]["document_sha256"] != row.document_sha256
            or definition["profile"]["id"] != row.profile_id
            or definition["profile"]["revision"] != row.profile_revision
            or definition["profile"]["sha256"] != row.profile_sha256
            or definition["profile"]["decision_id"] != row.profile_decision_id
            or definition["profile"]["decision_sha256"] != row.decision_sha256
            or definition["row"]["sheet_index"] != row.sheet_index
            or definition["row"]["row"] != row.row_number
            or definition["row"]["sha256"] != row.row_sha256
            or definition["interpretation"]["item_kind"] != row.item_kind
            or definition["interpretation"]["normalized_reference"] != row.normalized_reference
            or definition["interpretation"]["evidence_state"] != row.evidence_state
            or definition["interpretation"]["review_reason"] != row.review_reason
        ):
            raise ValueError("row observation binding")
    except (ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
        raise DraftScopeError("PRICING_ROW_OBSERVATION_INTEGRITY_FAILED", 409) from exc
    return cast(dict[str, Any], value)


def list_row_observations(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    profile_id: str,
) -> list[dict[str, Any]]:
    source, profile = _profile_row(db, actor, draft_id, source_id, profile_id)
    latest_source = db.scalar(
        select(DraftPricingSource)
        .where(
            DraftPricingSource.draft_scope_id == draft_id,
            DraftPricingSource.dataset_id == source.dataset_id,
        )
        .order_by(DraftPricingSource.dataset_version.desc())
        .limit(1)
    )
    latest_profile = db.scalar(
        select(DraftPricingSourceProfile)
        .where(
            DraftPricingSourceProfile.source_id == source_id,
            DraftPricingSourceProfile.draft_scope_id == draft_id,
        )
        .order_by(DraftPricingSourceProfile.revision.desc())
        .limit(1)
    )
    rows = db.scalars(
        select(DraftPricingRowObservation)
        .where(
            DraftPricingRowObservation.draft_scope_id == draft_id,
            DraftPricingRowObservation.source_id == source_id,
            DraftPricingRowObservation.profile_id == profile_id,
        )
        .order_by(DraftPricingRowObservation.row_number)
    ).all()
    return [
        {
            "id": row.id,
            "row_number": row.row_number,
            "observation_sha256": row.observation_sha256,
            "reviewed_at": row.created_at,
            "reviewed_by": cast(User, db.get(User, row.reviewed_by_id)).full_name,
            "is_current": (
                latest_source is not None
                and latest_source.id == source.id
                and latest_profile is not None
                and latest_profile.id == profile.id
            ),
            "value": _row_observation_value(row),
        }
        for row in rows
    ]


def row_observation_bytes(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    profile_id: str,
    observation_id: str,
) -> bytes:
    _profile_row(db, actor, draft_id, source_id, profile_id)
    row = db.scalar(
        select(DraftPricingRowObservation).where(
            DraftPricingRowObservation.id == observation_id,
            DraftPricingRowObservation.draft_scope_id == draft_id,
            DraftPricingRowObservation.source_id == source_id,
            DraftPricingRowObservation.profile_id == profile_id,
        )
    )
    if row is None:
        raise DraftScopeError("PRICING_ROW_OBSERVATION_NOT_FOUND", 404)
    _row_observation_value(row)
    return row.observation_json.encode("utf-8")


def save_profile(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    sheet_index: int,
    header_row: int,
    mapping: dict[str, int | None],
    price_meaning: str,
    expected_profile_revision: int,
    expected_document_sha256: str,
    expected_preview_hash: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    with _atomic(db):
        source_api = intake()
        actor, locked_source = source_api._source(
            db, actor, draft_id, source_id, write=True, lock=True
        )
        source = cast(DraftPricingSource, locked_source)
        document_source, document, _ = source_api._document(
            db, actor, draft_id, source_id, settings.storage_root
        )
        if document_source.id != source.id:
            raise DraftScopeError("PRICING_SOURCE_CHANGED", 409)
        if source.document_sha256 != expected_document_sha256:
            raise DraftScopeError("PRICING_SOURCE_CHANGED", 409)
        latest = db.scalar(
            select(DraftPricingSourceProfile)
            .where(
                DraftPricingSourceProfile.source_id == source_id,
                DraftPricingSourceProfile.draft_scope_id == draft_id,
            )
            .order_by(DraftPricingSourceProfile.revision.desc())
            .limit(1)
            .with_for_update()
        )
        current_revision = latest.revision if latest else 0
        if (
            type(expected_profile_revision) is not int
            or expected_profile_revision != current_revision
        ):
            raise DraftScopeError("PRICING_PROFILE_STALE", 409)
        if current_revision >= MAX_PROFILE_REVISIONS:
            raise DraftScopeError("PRICING_PROFILE_LIMIT", 409)
        if (
            source.dataset_id is None
            or source.dataset_kind is None
            or source.dataset_version is None
            or source.document_sha256 is None
        ):
            raise DraftScopeError("PRICING_DATASET_KIND_REQUIRED", 409)
        try:
            definition, _ = profile_definition(
                document,
                draft_scope_id=draft_id,
                source_id=source.id,
                dataset_id=source.dataset_id,
                dataset_kind=source.dataset_kind,
                dataset_version=source.dataset_version,
                source_sha256=source.source_sha256,
                source_size_bytes=source.source_size_bytes,
                original_filename=source.original_filename,
                document_sha256=source.document_sha256,
                sheet_index=sheet_index,
                header_row=header_row,
                mapping=mapping,
                price_meaning=price_meaning,
            )
        except (ValueError, TypeError, KeyError) as exc:
            raise DraftScopeError("PRICING_PROFILE_INVALID", 422) from exc
        if digest(definition) != expected_preview_hash:
            raise DraftScopeError("PRICING_PROFILE_CHANGED", 409)
        created = datetime.now(UTC)
        profile_id = new_id()
        envelope = {
            "schema_version": PROFILE_SCHEMA,
            "profile_id": profile_id,
            "revision": current_revision + 1,
            "parent_profile_sha256": latest.profile_sha256 if latest else None,
            "created_at": created.isoformat(),
            "created_by_id": actor.id,
            "definition": definition,
            "definition_sha256": expected_preview_hash,
        }
        try:
            validate_profile_envelope(envelope)
            raw = canonical(envelope)
        except (ValueError, TypeError, KeyError) as exc:
            raise DraftScopeError("PRICING_PROFILE_INVALID", 422) from exc
        row = DraftPricingSourceProfile(
            id=profile_id,
            draft_scope_id=draft_id,
            source_id=source_id,
            revision=current_revision + 1,
            parent_profile_sha256=latest.profile_sha256 if latest else None,
            profile_json=raw.decode("utf-8"),
            profile_sha256=hashlib.sha256(raw).hexdigest(),
            created_by_id=actor.id,
            created_at=created,
            updated_at=created,
        )
        db.add(row)
        draft = get_draft(db, actor, draft_id)
        record_audit(
            db,
            actor=actor,
            action="draft_pricing.profile.save",
            entity_type="draft_pricing_source_profile",
            entity_id=row.id,
            project_id=draft.project_id,
            previous_value=(
                {"revision": latest.revision, "sha256": latest.profile_sha256}
                if latest
                else None
            ),
            new_value={
                "revision": row.revision,
                "sha256": row.profile_sha256,
                "source_id": source_id,
                "dataset_id": source.dataset_id,
                "dataset_kind": source.dataset_kind,
                "dataset_version": source.dataset_version,
                "approval_status": "unapproved",
            },
        )
        db.flush()
        return envelope


def preview(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    sheet_index: int,
    header_row: int,
    mapping: dict[str, int | None],
    *,
    settings: Settings,
) -> tuple[DraftPricingSource, list[dict[str, Any]]]:
    source, document, _ = intake()._document(db, actor, draft_id, source_id, settings.storage_root)
    try:
        return cast(DraftPricingSource, source), preview_rows(
            document, sheet_index, header_row, mapping
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise DraftScopeError("PRICING_MAPPING_INVALID", 422) from exc


def apply_rate(
    db: Session,
    actor: User,
    draft_id: str,
    estimate_id: str,
    expected_revision: int,
    line_id: str,
    source_id: str,
    sheet_index: int,
    header_row: int,
    mapping: dict[str, int | None],
    row_number: int,
    expected_document_hash: str,
    expected_row_hash: str,
    recovery_note: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    with _atomic(db):
        actor, draft, estimate, prior = estimates._editable(
            db,
            actor,
            draft_id,
            estimate_id,
            expected_revision,
        )
        source, rows = preview(
            db, actor, draft_id, source_id, sheet_index, header_row, mapping, settings=settings
        )
        if source.document_sha256 != expected_document_hash:
            raise DraftScopeError("PRICING_SOURCE_CHANGED", 409)
        row = next((item for item in rows if item["row"] == row_number), None)
        if row is None or row["sha256"] != expected_row_hash:
            raise DraftScopeError("PRICING_ROW_CHANGED", 409)
        if row["problems"]:
            raise DraftScopeError("PRICING_RATE_UNRESOLVED", 422)
        envelope = copy.deepcopy(prior)
        line = estimates._line(envelope, line_id)
        if row["values"]["unit"] != line["unit"]:
            raise DraftScopeError("PRICING_UNIT_MISMATCH", 422)
        if type(recovery_note) is not str or not 1 <= len(recovery_note.strip()) <= 4000:
            raise DraftScopeError("PRICING_RECOVERY_NOTE_REQUIRED", 422)
        created = datetime.now(UTC)
        rate = row["values"]["rate"]
        event = estimates._event(
            actor,
            created,
            "override",
            line["quantity"],
            line["quantity"],
            line["unit_sell_rate"],
            rate,
            recovery_note,
        )
        line["history"].append(event)
        line["unit_sell_rate"] = rate
        line["subtotal_ex_tax"], line["pricing_status"] = line_amount(line)
        if "import_origin" in envelope:
            envelope["content_schema_version"] = "CLASSIFIRE-DRAFT-ESTIMATE-v2"
        else:
            envelope["schema_version"] = "CLASSIFIRE-DRAFT-ESTIMATE-v2"
            envelope["provenance"] = "manual_and_workbook_unit_sell"
        envelope.setdefault("pricing_sources", []).append(
            {
                "line_id": line_id,
                "event_id": event["event_id"],
                "source_id": source.id,
                "source_sha256": source.source_sha256,
                "source_size_bytes": source.source_size_bytes,
                "original_filename": source.original_filename,
                "document_sha256": source.document_sha256,
                "scan_sha256": hashlib.sha256(
                    cast(str, source.scan_json).encode("utf-8")
                ).hexdigest(),
                "row": row,
                "method": "exact_library_rate",
                "approval_status": "unreviewed",
                "recovery_note": recovery_note,
            }
        )
        actor = intake()._actor(db, actor, write=True)
        return estimates._save(
            db, actor, draft, estimate, prior, envelope, "select_workbook_rate", created
        )


def pricing_staleness(
    db: Session, actor: User, draft_id: str, envelope: dict[str, Any], *, storage_root: Path
) -> list[str]:
    reasons = []
    checked = set()
    for ref in envelope.get("pricing_sources", []):
        key = (ref["source_id"], ref["document_sha256"], ref["scan_sha256"])
        if key in checked:
            continue
        checked.add(key)
        try:
            source, _, content = intake()._document(
                db, actor, draft_id, ref["source_id"], storage_root
            )
            if (
                content.sha256 != ref["source_sha256"]
                or source.document_sha256 != ref["document_sha256"]
                or hashlib.sha256(cast(str, source.scan_json).encode("utf-8")).hexdigest()
                != ref["scan_sha256"]
            ):
                reasons.append("PRICING_SOURCE_CHANGED")
        except DraftScopeError as exc:
            if exc.status_code == 403:
                raise
            reasons.append("PRICING_SOURCE_UNAVAILABLE")
    return list(dict.fromkeys(reasons))
