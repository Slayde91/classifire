from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import record_audit
from .models import Approval, LibraryRelease, PricingLibraryRecord, TechnicalVariant, User
from .security import has_permission
from .v213_release_validation import SOURCE_VERSION, validate_v213_releases

RUNTIME_VERSION = "2.13-runtime"


class V213PromotionError(RuntimeError):
    pass


def _canonical_hash(payload: Any) -> str:
    # Keep this byte-for-byte compatible with services.release_scope._manifest_hash.
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _source_release(db: Session, library_type: str, release_id: str) -> LibraryRelease:
    release = db.get(LibraryRelease, release_id)
    if release is None:
        raise V213PromotionError(f"Validated {library_type} source release is missing.")
    if release.library_type != library_type or release.version != SOURCE_VERSION:
        raise V213PromotionError(
            f"Validated {library_type} source release identity no longer matches v{SOURCE_VERSION}."
        )
    if release.status != "draft":
        raise V213PromotionError(
            f"Validated {library_type} source release is no longer draft: {release.status}."
        )
    return release


def _existing_runtime_release(
    db: Session,
    library_type: str,
    runtime_version: str,
) -> LibraryRelease | None:
    return db.scalar(
        select(LibraryRelease).where(
            LibraryRelease.library_type == library_type,
            LibraryRelease.version == runtime_version,
        )
    )


def _latest_active_release(db: Session, library_type: str) -> LibraryRelease | None:
    return db.scalar(
        select(LibraryRelease)
        .where(
            LibraryRelease.library_type == library_type,
            LibraryRelease.status == "active",
        )
        .order_by(LibraryRelease.created_at.desc())
    )


def _pricing_records(db: Session, source_release_id: str) -> list[PricingLibraryRecord]:
    records = list(
        db.scalars(
            select(PricingLibraryRecord)
            .where(PricingLibraryRecord.release_id == source_release_id)
            .order_by(PricingLibraryRecord.pkb_entry_id, PricingLibraryRecord.id)
        ).all()
    )
    if len(records) != 897:
        raise V213PromotionError(
            f"Validated Package 14 source release now contains {len(records)} records, expected 897."
        )
    if any(record.status != "active" for record in records):
        raise V213PromotionError("All validated Package 14 records must remain active before promotion.")
    return records


def _technical_records(db: Session, source_release_id: str) -> list[TechnicalVariant]:
    records = list(
        db.scalars(
            select(TechnicalVariant)
            .where(TechnicalVariant.release_id == source_release_id)
            .order_by(TechnicalVariant.variant_id, TechnicalVariant.id)
        ).all()
    )
    if len(records) != 2861:
        raise V213PromotionError(
            f"Validated Package 17 source release now contains {len(records)} records, expected 2861."
        )
    active = [record for record in records if record.status == "active"]
    inactive = [record for record in records if record.status != "active"]
    if len(active) != 2860 or len(inactive) != 1:
        raise V213PromotionError(
            "Validated Package 17 active/inactive record split changed; expected 2860 active / 1 inactive."
        )
    return active


def _pricing_manifest_records(records: list[PricingLibraryRecord]) -> list[dict[str, Any]]:
    return [
        {
            "id": record.id,
            "key": record.pkb_entry_id,
            "entry_version": record.entry_version,
            "rate_ex_tax": str(record.rate_ex_tax),
            "source_hash": record.source_hash,
            "record_version": record.record_version,
        }
        for record in records
    ]


def _technical_manifest_records(records: list[TechnicalVariant]) -> list[dict[str, Any]]:
    return [
        {
            "id": record.id,
            "key": record.variant_id,
            "variant_id": record.variant_id,
            "system_id": record.system_id,
            "frl": record.frl,
            "source_document_reference": record.source_document_reference,
            "source_page": record.source_page,
            "source_hash": record.source_hash,
            "record_version": record.record_version,
            "migration_provenance": (record.source_json or {}).get("CLASSIFIRE_Migration"),
        }
        for record in records
    ]


def _runtime_manifest(
    *,
    library_type: str,
    runtime_version: str,
    source_release: LibraryRelease,
    validation: dict[str, Any],
    records: list[dict[str, Any]],
    approver: User,
    acknowledgements: list[str],
) -> dict[str, Any]:
    return {
        "schema": "CLASSIFIRE-V213-RUNTIME-RELEASE-v1",
        "release_type": library_type,
        "version": runtime_version,
        "source_version": SOURCE_VERSION,
        "source_release_id": source_release.id,
        "source_release_file_hash": source_release.release_hash,
        "validation_schema": validation.get("schema"),
        "validation_approval_token": validation.get("approval_token"),
        "validation_source_hashes": (validation.get("approval_basis") or {}).get("source_hashes", {}),
        "acknowledged_condition_ids": acknowledgements,
        "approved_by_id": approver.id,
        "approved_by_email": approver.email,
        "record_count": len(records),
        "records": records,
    }


def _create_runtime_release(
    db: Session,
    *,
    library_type: str,
    runtime_version: str,
    source_release: LibraryRelease,
    validation: dict[str, Any],
    records: list[dict[str, Any]],
    approver: User,
    acknowledgements: list[str],
) -> LibraryRelease:
    manifest = _runtime_manifest(
        library_type=library_type,
        runtime_version=runtime_version,
        source_release=source_release,
        validation=validation,
        records=records,
        approver=approver,
        acknowledgements=acknowledgements,
    )
    release_hash = _canonical_hash(manifest)
    existing = _existing_runtime_release(db, library_type, runtime_version)
    if existing:
        if (
            existing.release_hash == release_hash
            and existing.source_manifest == manifest
            and existing.status == "active"
        ):
            return existing
        raise V213PromotionError(
            f"A {library_type} runtime release {runtime_version!r} already exists with different content or status."
        )

    previous = _latest_active_release(db, library_type)
    if previous is not None:
        previous.status = "superseded"

    release = LibraryRelease(
        library_type=library_type,
        version=runtime_version,
        status="active",
        effective_date=date.today(),
        release_hash=release_hash,
        source_manifest=manifest,
        notes=(
            f"Human-approved CLASSIFIRE v{SOURCE_VERSION} runtime {library_type} release, "
            "scoped only to records from the validated controlled migration source release."
        ),
        created_by_id=approver.id,
        approved_by_id=approver.id,
        approved_at=datetime.now(timezone.utc),
        supersedes_release_id=previous.id if previous else None,
    )
    db.add(release)
    db.flush()

    approval = Approval(
        entity_type="library_release",
        entity_id=release.id,
        approval_type=f"{library_type}_runtime_release_activation",
        status="approved",
        requested_by_id=approver.id,
        decided_by_id=approver.id,
        requested_at=datetime.now(timezone.utc),
        decided_at=datetime.now(timezone.utc),
        decision_reason=(
            f"Human approval of validated CLASSIFIRE v{SOURCE_VERSION} runtime {library_type} release. "
            f"Validation token {validation.get('approval_token')}. "
            f"Acknowledged conditions: {', '.join(acknowledgements) if acknowledgements else 'none'}."
        ),
        snapshot_hash=release_hash,
    )
    db.add(approval)

    record_audit(
        db,
        actor=approver,
        action="promote_v213_runtime_release",
        entity_type="library_release",
        entity_id=release.id,
        previous_value={
            "previous_active_release_id": previous.id if previous else None,
            "source_release_id": source_release.id,
        },
        new_value={
            "library_type": library_type,
            "runtime_version": runtime_version,
            "release_hash": release_hash,
            "record_count": len(records),
            "validation_token": validation.get("approval_token"),
            "acknowledged_condition_ids": acknowledgements,
        },
        reason="Controlled human promotion of validated v2.13 source library to runtime release",
        correlation_id=str(validation.get("approval_token") or ""),
    )
    return release


def promote_v213_runtime_releases(
    db: Session,
    source_root: Path,
    *,
    approval_token: str,
    acknowledged_condition_ids: set[str],
    pricing_approver: User,
    technical_approver: User,
    runtime_version: str = RUNTIME_VERSION,
) -> dict[str, Any]:
    validation = validate_v213_releases(db, source_root)
    if not validation.get("hard_gates_passed"):
        raise V213PromotionError("v2.13 validation hard gates no longer pass; promotion is blocked.")
    live_token = str(validation.get("approval_token") or "")
    if not approval_token or approval_token != live_token:
        raise V213PromotionError("Approval token does not match the current validated source state.")

    required_conditions = {
        str(item.get("condition_id"))
        for item in validation.get("conditions", [])
        if item.get("condition_id")
    }
    missing_acknowledgements = sorted(required_conditions - set(acknowledged_condition_ids))
    if missing_acknowledgements:
        raise V213PromotionError(
            "Human approval is missing required condition acknowledgements: "
            + ", ".join(missing_acknowledgements)
        )

    if not has_permission(pricing_approver, "pricing:approve"):
        raise V213PromotionError(
            f"Pricing approver {pricing_approver.email!r} lacks pricing:approve authority."
        )
    if not has_permission(technical_approver, "technical:approve"):
        raise V213PromotionError(
            f"Technical approver {technical_approver.email!r} lacks technical:approve authority."
        )

    basis = validation.get("approval_basis") or {}
    pricing_source_id = str(basis.get("pricing_source_release_id") or "")
    technical_source_id = str(basis.get("technical_source_release_id") or "")
    if not pricing_source_id or not technical_source_id:
        raise V213PromotionError("Validation receipt has no source release IDs.")

    pricing_source = _source_release(db, "pricing", pricing_source_id)
    technical_source = _source_release(db, "technical", technical_source_id)
    pricing_records = _pricing_records(db, pricing_source.id)
    technical_records = _technical_records(db, technical_source.id)
    acknowledgements = sorted(required_conditions)

    pricing_runtime = _create_runtime_release(
        db,
        library_type="pricing",
        runtime_version=runtime_version,
        source_release=pricing_source,
        validation=validation,
        records=_pricing_manifest_records(pricing_records),
        approver=pricing_approver,
        acknowledgements=acknowledgements,
    )
    technical_runtime = _create_runtime_release(
        db,
        library_type="technical",
        runtime_version=runtime_version,
        source_release=technical_source,
        validation=validation,
        records=_technical_manifest_records(technical_records),
        approver=technical_approver,
        acknowledgements=acknowledgements,
    )
    db.commit()

    return {
        "schema": "CLASSIFIRE-V213-RUNTIME-PROMOTION-RECEIPT-v1",
        "source_version": SOURCE_VERSION,
        "runtime_version": runtime_version,
        "validation_approval_token": live_token,
        "acknowledged_condition_ids": acknowledgements,
        "pricing_runtime_release": {
            "release_id": pricing_runtime.id,
            "release_hash": pricing_runtime.release_hash,
            "record_count": len(pricing_records),
            "approver_email": pricing_approver.email,
        },
        "technical_runtime_release": {
            "release_id": technical_runtime.id,
            "release_hash": technical_runtime.release_hash,
            "record_count": len(technical_records),
            "approver_email": technical_approver.email,
        },
    }
