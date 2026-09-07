"""Draft pricing workbook intake and explicit source-bound rate application."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess  # nosec B404
import sys
from datetime import UTC, date, datetime
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
    DraftPricingSystemMapping,
    DraftScope,
    LibraryRelease,
    StoredFile,
    TechnicalDocument,
    TechnicalVariant,
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
    SYSTEM_MAPPING_SCHEMA,
    digest,
    preview_rows,
    profile_definition,
    row_observation_definition,
    system_mapping_definition,
    validate_dataset_kind,
    validate_profile_decision_envelope,
    validate_profile_envelope,
    validate_row_observation_envelope,
    validate_system_mapping_envelope,
)
from .draft_scope import DraftScopeError, _actor, _atomic, get_draft
from .draft_source_intake import DraftSourceIntake, SourcePolicy
from .draft_system_match_contract import canonical, validate_binding
from .release_scope import ReleaseScopeError, active_technical_release_ids
from .storage import (
    StoredFileBindingError,
    read_clean_stored_file_for_update,
    read_verified_stored_file,
)
from .technical_field_snapshot import technical_fields
from .technical_release_publication import TECHNICAL_RELEASE_MANIFEST_SCHEMA
from .technical_validity import (
    technical_document_authority_blockers,
    technical_release_source_binding,
    technical_variant_logical_key,
)

SCHEMA = "CLASSIFIRE-DRAFT-PRICING-XLSX-v1"
MAX_PROFILE_REVISIONS = 20
MAX_SYSTEM_MAPPING_VARIANTS = 20
MAX_SYSTEM_MAPPING_OPTIONS = 100


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
    dataset_kind: str = "general_pricelist",
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
    if source.dataset_kind != dataset_kind:
        code = (
            "PRICING_ROW_DATASET_A_REQUIRED"
            if dataset_kind == "general_pricelist"
            else "PRICING_ROW_DATASET_B_REQUIRED"
        )
        raise DraftScopeError(code, 409)
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


def _active_technical_release(
    db: Session,
    actor: User,
    release_id: str,
    *,
    lock: bool = False,
) -> tuple[User, LibraryRelease, dict[str, dict[str, Any]], set[str]]:
    actor = _actor(db, actor, "technical:read")
    statement = select(LibraryRelease).where(
        LibraryRelease.id == release_id,
        LibraryRelease.library_type == "technical",
    )
    if lock:
        statement = statement.with_for_update()
    release = db.scalar(statement.execution_options(populate_existing=True))
    if release is None:
        raise DraftScopeError("PRICING_TECHNICAL_RELEASE_NOT_FOUND", 404)
    if release.status != "active" or (
        release.effective_date is not None and release.effective_date > date.today()
    ):
        raise DraftScopeError("PRICING_TECHNICAL_RELEASE_STALE", 409)
    try:
        active_ids = active_technical_release_ids(db, release)
        manifest = release.source_manifest
        if (
            type(manifest) is not dict
            or manifest.get("schema") != TECHNICAL_RELEASE_MANIFEST_SCHEMA
            or type(manifest.get("records")) is not list
            or type(manifest.get("record_count")) is not int
            or manifest["record_count"] != len(manifest["records"])
            or not 1 <= len(manifest["records"]) <= 10000
            or type(release.release_hash) is not str
        ):
            raise ValueError("manifest")
        records: dict[str, dict[str, Any]] = {}
        for item in manifest["records"]:
            if (
                type(item) is not dict
                or type(item.get("id")) is not str
                or item["id"] in records
            ):
                raise ValueError("manifest")
            records[item["id"]] = item
        if set(records) != active_ids:
            raise ValueError("manifest")
    except (ReleaseScopeError, ValueError, TypeError, KeyError) as exc:
        raise DraftScopeError("PRICING_TECHNICAL_RELEASE_INVALID", 409) from exc
    return actor, release, records, active_ids


def list_system_mapping_targets(
    db: Session,
    actor: User,
    draft_id: str,
) -> dict[str, Any] | None:
    get_draft(db, actor, draft_id)
    actor = _actor(db, actor, "pricing:approve")
    actor = _actor(db, actor, "technical:read")
    releases = list(
        db.scalars(
            select(LibraryRelease)
            .where(
                LibraryRelease.library_type == "technical",
                LibraryRelease.status == "active",
            )
            .order_by(LibraryRelease.created_at.desc(), LibraryRelease.id)
            .limit(2)
        ).all()
    )
    if not releases:
        return None
    if len(releases) != 1:
        raise DraftScopeError("PRICING_TECHNICAL_RELEASE_AMBIGUOUS", 409)
    _, release, records, active_ids = _active_technical_release(
        db, actor, releases[0].id
    )
    variants = list(
        db.scalars(
            select(TechnicalVariant)
            .where(TechnicalVariant.id.in_(active_ids))
            .order_by(TechnicalVariant.variant_id, TechnicalVariant.id)
            .limit(MAX_SYSTEM_MAPPING_OPTIONS + 1)
        ).all()
    )
    options = []
    for variant in variants[:MAX_SYSTEM_MAPPING_OPTIONS]:
        record = records[variant.id]
        binding = record.get("source_binding")
        if type(binding) is not dict or binding.get("state") != "bound":
            continue
        options.append(
            {
                "id": variant.id,
                "key": record.get("key"),
                "variant_id": variant.variant_id,
                "system_id": variant.system_id,
                "manufacturer": variant.manufacturer,
                "product_family": variant.product_family,
                "frl": variant.frl,
            }
        )
    return {
        "release": {
            "id": release.id,
            "version": release.version,
            "sha256": release.release_hash,
            "effective_date": (
                release.effective_date.isoformat() if release.effective_date else None
            ),
        },
        "variants": options,
        "truncated": len(variants) > MAX_SYSTEM_MAPPING_OPTIONS,
    }


def _technical_variant_snapshot(
    db: Session,
    variant_id: str,
    records: dict[str, dict[str, Any]],
    active_ids: set[str],
    *,
    settings: Settings,
    lock: bool,
) -> dict[str, Any]:
    if variant_id not in active_ids:
        raise DraftScopeError("PRICING_TECHNICAL_VARIANT_NOT_ELIGIBLE", 409)
    statement = select(TechnicalVariant).where(TechnicalVariant.id == variant_id)
    if lock:
        statement = statement.with_for_update()
    variant = db.scalar(statement.execution_options(populate_existing=True))
    if variant is None:
        raise DraftScopeError("PRICING_TECHNICAL_VARIANT_NOT_FOUND", 404)
    record = records.get(variant.id)
    fields = technical_fields(variant)
    document: TechnicalDocument | None = None
    stored: StoredFile | None = None
    if variant.technical_document_id:
        document_statement = select(TechnicalDocument).where(
            TechnicalDocument.id == variant.technical_document_id
        )
        if lock:
            document_statement = document_statement.with_for_update()
        document = db.scalar(document_statement.execution_options(populate_existing=True))
        if document is not None:
            stored_statement = select(StoredFile).where(
                StoredFile.id == document.stored_file_id
            )
            if lock:
                stored_statement = stored_statement.with_for_update()
            stored = db.scalar(stored_statement.execution_options(populate_existing=True))
    expected_binding = technical_release_source_binding(
        technical_document_id=variant.technical_document_id,
        technical_document_key=document.document_id if document else None,
        technical_document_reference=document.reference if document else None,
        technical_document_revision=document.revision if document else None,
        stored_file_id=document.stored_file_id if document else None,
        stored_file_sha256=stored.sha256 if stored else None,
        stored_file_size_bytes=stored.size_bytes if stored else None,
        source_document_reference=variant.source_document_reference,
        source_page=variant.source_page,
        source_table=variant.source_table,
        source_figure=variant.source_figure,
    )
    try:
        if (
            type(record) is not dict
            or set(record) != {
                "id", "key", "variant_id", "system_id", "frl",
                "source_document_reference", "source_page", "source_hash",
                "record_version", "technical_fields", "source_binding",
            }
            or record["id"] != variant.id
            or record["key"] != technical_variant_logical_key(
                variant_id=variant.variant_id, source_json=variant.source_json
            )
            or record["variant_id"] != variant.variant_id
            or record["system_id"] != variant.system_id
            or record["frl"] != variant.frl
            or record["source_document_reference"] != variant.source_document_reference
            or record["source_page"] != variant.source_page
            or record["source_hash"] != variant.source_hash
            or record["record_version"] != variant.record_version
            or record["technical_fields"] != fields
            or record["source_binding"] != expected_binding
        ):
            raise ValueError("record")
        validate_binding(record["source_binding"])
        if record["source_binding"]["state"] != "bound":
            raise ValueError("binding")
        if (
            document is None
            or stored is None
            or technical_document_authority_blockers(
                status=document.status,
                expiry_date=document.expiry_date,
                stored_file_present=True,
                stored_file_purpose=stored.purpose,
                stored_file_scan_status=stored.malware_scan_status,
                stored_file_immutable=stored.immutable,
            )
            or type(variant.source_hash) is not str
            or variant.source_hash != stored.sha256
        ):
            raise ValueError("source")
        if lock and db.get_bind().dialect.name == "postgresql":
            read_clean_stored_file_for_update(
                db,
                stored_file_id=stored.id,
                storage_root=settings.storage_root,
                required_purpose="technical_evidence",
            )
        else:
            read_verified_stored_file(
                stored,
                storage_root=settings.storage_root,
                required_purpose="technical_evidence",
            )
    except (ValueError, TypeError, KeyError, StoredFileBindingError) as exc:
        raise DraftScopeError("PRICING_TECHNICAL_VARIANT_INVALID", 409) from exc
    snapshot = {
        "id": variant.id,
        "key": record["key"],
        "variant_id": variant.variant_id,
        "system_id": variant.system_id,
        "record_version": variant.record_version,
        "source_hash": variant.source_hash,
        "technical_fields": fields,
        "technical_fields_sha256": digest(fields),
        "release_record": copy.deepcopy(record),
        "release_record_sha256": digest(record),
        "source_verification": {"method": "exact_bytes"},
    }
    snapshot["sha256"] = digest(snapshot)
    return snapshot


def _mapping_variant_ids(
    mapping_status: str,
    selected_variant_id: str | None,
    candidate_variant_ids: list[str],
) -> list[str]:
    selected = selected_variant_id.strip() if type(selected_variant_id) is str else None
    selected = selected or None
    if (
        type(candidate_variant_ids) is not list
        or any(type(item) is not str or not 1 <= len(item) <= 36 for item in candidate_variant_ids)
        or candidate_variant_ids != sorted(set(candidate_variant_ids))
        or len(candidate_variant_ids) > MAX_SYSTEM_MAPPING_VARIANTS
    ):
        raise DraftScopeError("PRICING_SYSTEM_MAPPING_INVALID", 422)
    if mapping_status == "mapped":
        if selected is None or candidate_variant_ids:
            raise DraftScopeError("PRICING_SYSTEM_MAPPING_INVALID", 422)
        return [selected]
    if mapping_status == "ambiguous":
        if selected is not None or len(candidate_variant_ids) < 2:
            raise DraftScopeError("PRICING_SYSTEM_MAPPING_INVALID", 422)
        return candidate_variant_ids
    if mapping_status == "unmatched":
        if selected is not None or candidate_variant_ids:
            raise DraftScopeError("PRICING_SYSTEM_MAPPING_INVALID", 422)
        return []
    raise DraftScopeError("PRICING_SYSTEM_MAPPING_INVALID", 422)


def preview_system_mapping(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    profile_id: str,
    row_number: int,
    technical_release_id: str,
    mapping_status: str,
    normalized_reference: str,
    selected_variant_id: str | None,
    candidate_variant_ids: list[str],
    identity_evidence_fields: list[str],
    review_reason: str,
    unresolved_fields: list[str],
    *,
    settings: Settings,
) -> dict[str, Any]:
    actor, source, profile, decision, profile_value, row = _row_observation_context(
        db,
        actor,
        draft_id,
        source_id,
        profile_id,
        row_number,
        settings=settings,
        dataset_kind="firefly_system_prices",
    )
    actor, release, records, active_ids = _active_technical_release(
        db, actor, technical_release_id
    )
    variant_ids = _mapping_variant_ids(
        mapping_status, selected_variant_id, candidate_variant_ids
    )
    variants = [
        _technical_variant_snapshot(
            db,
            variant_id,
            records,
            active_ids,
            settings=settings,
            lock=False,
        )
        for variant_id in variant_ids
    ]
    try:
        definition = system_mapping_definition(
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
            technical_release={
                "id": release.id,
                "version": release.version,
                "sha256": release.release_hash,
                "effective_date": (
                    release.effective_date.isoformat()
                    if release.effective_date
                    else None
                ),
            },
            variants=variants,
            mapping_status=mapping_status,
            normalized_reference=normalized_reference,
            selected_variant_id=(
                variant_ids[0] if mapping_status == "mapped" else None
            ),
            candidate_variant_ids=variant_ids,
            identity_evidence_fields=identity_evidence_fields,
            review_reason=review_reason,
            unresolved_fields=unresolved_fields,
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise DraftScopeError("PRICING_SYSTEM_MAPPING_INVALID", 422) from exc
    return {"definition": definition, "preview_hash": digest(definition)}


def save_system_mapping(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    profile_id: str,
    row_number: int,
    technical_release_id: str,
    mapping_status: str,
    normalized_reference: str,
    selected_variant_id: str | None,
    candidate_variant_ids: list[str],
    identity_evidence_fields: list[str],
    review_reason: str,
    unresolved_fields: list[str],
    expected_profile_sha256: str,
    expected_decision_sha256: str,
    expected_row_sha256: str,
    expected_technical_release_sha256: str,
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
            dataset_kind="firefly_system_prices",
        )
        actor, release, _, _ = _active_technical_release(
            db, actor, technical_release_id, lock=True
        )
        if (
            profile.profile_sha256 != expected_profile_sha256
            or decision.decision_sha256 != expected_decision_sha256
            or row["sha256"] != expected_row_sha256
            or release.release_hash != expected_technical_release_sha256
        ):
            raise DraftScopeError("PRICING_SYSTEM_MAPPING_CHANGED", 409)
        existing = db.scalar(
            select(DraftPricingSystemMapping).where(
                DraftPricingSystemMapping.profile_id == profile_id,
                DraftPricingSystemMapping.sheet_index == row["sheet_index"],
                DraftPricingSystemMapping.row_number == row_number,
            )
        )
        if existing is not None:
            raise DraftScopeError("PRICING_SYSTEM_ALREADY_MAPPED", 409)
        preview = preview_system_mapping(
            db,
            actor,
            draft_id,
            source_id,
            profile_id,
            row_number,
            technical_release_id,
            mapping_status,
            normalized_reference,
            selected_variant_id,
            candidate_variant_ids,
            identity_evidence_fields,
            review_reason,
            unresolved_fields,
            settings=settings,
        )
        if preview["preview_hash"] != expected_preview_hash:
            raise DraftScopeError("PRICING_SYSTEM_MAPPING_CHANGED", 409)
        reviewed = datetime.now(UTC)
        mapping_id = new_id()
        envelope = {
            "schema_version": SYSTEM_MAPPING_SCHEMA,
            "mapping_id": mapping_id,
            "reviewed_at": reviewed.isoformat(),
            "reviewed_by_id": actor.id,
            "definition": preview["definition"],
            "definition_sha256": expected_preview_hash,
        }
        try:
            validate_system_mapping_envelope(envelope)
            raw = canonical(envelope)
        except (ValueError, TypeError, KeyError) as exc:
            raise DraftScopeError("PRICING_SYSTEM_MAPPING_INVALID", 422) from exc
        interpretation = envelope["definition"]["interpretation"]
        variants = envelope["definition"]["variants"]
        selected_snapshot = variants[0] if mapping_status == "mapped" else None
        stored = DraftPricingSystemMapping(
            id=mapping_id,
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
            mapping_status=interpretation["status"],
            normalized_reference=interpretation["normalized_reference"],
            review_reason=interpretation["review_reason"],
            technical_release_id=release.id,
            technical_release_sha256=cast(str, release.release_hash),
            technical_variant_id=(
                selected_snapshot["id"] if selected_snapshot else None
            ),
            technical_variant_snapshot_sha256=(
                selected_snapshot["sha256"] if selected_snapshot else None
            ),
            mapping_json=raw.decode("utf-8"),
            mapping_sha256=hashlib.sha256(raw).hexdigest(),
            reviewed_by_id=actor.id,
            created_at=reviewed,
            updated_at=reviewed,
        )
        db.add(stored)
        draft = get_draft(db, actor, draft_id)
        record_audit(
            db,
            actor=actor,
            action="draft_pricing.system_mapping.save",
            entity_type="draft_pricing_system_mapping",
            entity_id=mapping_id,
            project_id=draft.project_id,
            new_value={
                "profile_id": profile_id,
                "profile_revision": profile.revision,
                "row_number": row_number,
                "row_sha256": row["sha256"],
                "mapping_status": interpretation["status"],
                "technical_release_id": release.id,
                "technical_release_sha256": release.release_hash,
                "technical_variant_id": stored.technical_variant_id,
                "mapping_sha256": stored.mapping_sha256,
            },
            reason=interpretation["review_reason"],
        )
        db.flush()
        return envelope


def _system_mapping_value(row: DraftPricingSystemMapping) -> dict[str, Any]:
    try:
        raw = row.mapping_json.encode("utf-8")
        value = json.loads(raw)
        validate_system_mapping_envelope(value)
        definition = value["definition"]
        interpretation = definition["interpretation"]
        variants = definition["variants"]
        selected = variants[0] if interpretation["status"] == "mapped" else None
        if (
            len(raw) > 524288
            or hashlib.sha256(raw).hexdigest() != row.mapping_sha256
            or value["mapping_id"] != row.id
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
            or interpretation["status"] != row.mapping_status
            or interpretation["normalized_reference"] != row.normalized_reference
            or interpretation["review_reason"] != row.review_reason
            or definition["technical_release"]["id"] != row.technical_release_id
            or definition["technical_release"]["sha256"]
            != row.technical_release_sha256
            or (selected["id"] if selected else None) != row.technical_variant_id
            or (selected["sha256"] if selected else None)
            != row.technical_variant_snapshot_sha256
        ):
            raise ValueError("system mapping binding")
    except (ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
        raise DraftScopeError("PRICING_SYSTEM_MAPPING_INTEGRITY_FAILED", 409) from exc
    return cast(dict[str, Any], value)


def _system_mapping_dependencies_current(
    db: Session,
    actor: User,
    row: DraftPricingSystemMapping,
    value: dict[str, Any],
    *,
    settings: Settings,
) -> bool:
    try:
        _, source, profile, decision, _, source_row = _row_observation_context(
            db,
            actor,
            row.draft_scope_id,
            row.source_id,
            row.profile_id,
            row.row_number,
            settings=settings,
            dataset_kind="firefly_system_prices",
        )
        definition = value["definition"]
        release_value = definition["technical_release"]
        _, release, records, active_ids = _active_technical_release(
            db, actor, row.technical_release_id
        )
        if (
            source.source_sha256 != row.source_sha256
            or source.document_sha256 != row.document_sha256
            or profile.profile_sha256 != row.profile_sha256
            or decision.id != row.profile_decision_id
            or decision.decision_sha256 != row.decision_sha256
            or source_row["sha256"] != row.row_sha256
            or release.release_hash != row.technical_release_sha256
            or release_value["version"] != release.version
            or release_value["effective_date"]
            != (
                release.effective_date.isoformat()
                if release.effective_date
                else None
            )
        ):
            return False
        current_variants = [
            _technical_variant_snapshot(
                db,
                variant["id"],
                records,
                active_ids,
                settings=settings,
                lock=False,
            )
            for variant in definition["variants"]
        ]
        expected_variants = cast(list[dict[str, Any]], definition["variants"])
        return current_variants == expected_variants
    except DraftScopeError as exc:
        if exc.status_code == 403:
            raise
        return False


def list_system_mappings(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    profile_id: str,
    *,
    settings: Settings,
) -> list[dict[str, Any]]:
    _profile_row(db, actor, draft_id, source_id, profile_id)
    actor = _actor(db, actor, "pricing:approve")
    actor = _actor(db, actor, "technical:read")
    rows = db.scalars(
        select(DraftPricingSystemMapping)
        .where(
            DraftPricingSystemMapping.draft_scope_id == draft_id,
            DraftPricingSystemMapping.source_id == source_id,
            DraftPricingSystemMapping.profile_id == profile_id,
        )
        .order_by(DraftPricingSystemMapping.row_number)
    ).all()
    result = []
    for row in rows:
        value = _system_mapping_value(row)
        reviewer = cast(User, db.get(User, row.reviewed_by_id))
        result.append(
            {
                "id": row.id,
                "row_number": row.row_number,
                "mapping_status": row.mapping_status,
                "mapping_sha256": row.mapping_sha256,
                "reviewed_at": row.created_at,
                "reviewed_by": reviewer.full_name,
                "is_current": _system_mapping_dependencies_current(
                    db, actor, row, value, settings=settings
                ),
                "value": value,
            }
        )
    return result


def system_mapping_bytes(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    profile_id: str,
    mapping_id: str,
) -> bytes:
    _profile_row(db, actor, draft_id, source_id, profile_id)
    actor = _actor(db, actor, "pricing:approve")
    _actor(db, actor, "technical:read")
    row = db.scalar(
        select(DraftPricingSystemMapping).where(
            DraftPricingSystemMapping.id == mapping_id,
            DraftPricingSystemMapping.draft_scope_id == draft_id,
            DraftPricingSystemMapping.source_id == source_id,
            DraftPricingSystemMapping.profile_id == profile_id,
        )
    )
    if row is None:
        raise DraftScopeError("PRICING_SYSTEM_MAPPING_NOT_FOUND", 404)
    _system_mapping_value(row)
    return row.mapping_json.encode("utf-8")


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
