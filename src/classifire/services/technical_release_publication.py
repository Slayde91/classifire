"""Fail-closed publication of one governed technical library release."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import LibraryRelease, StoredFile, TechnicalDocument, TechnicalVariant, User
from ..security import has_permission
from .storage import (
    StoredFileBindingError,
    read_clean_stored_file_for_update,
    read_verified_stored_file,
)
from .technical_validity import (
    technical_document_authority_blockers,
    technical_release_source_binding,
    technical_variant_logical_key,
    technical_variant_temporal_blockers,
)

TECHNICAL_RELEASE_MANIFEST_SCHEMA = "CLASSIFIRE-TECHNICAL-LIBRARY-RELEASE-v2"


class TechnicalReleasePublicationError(RuntimeError):
    """Safe-code failure while publishing a governed technical release."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Technical release publication failed: {code}.")


def publish_governed_technical_release(
    db: Session,
    *,
    version: str,
    notes: str,
    actor: User | None,
    storage_root: Path,
    now: datetime | None = None,
    source_ip: str | None = None,
) -> LibraryRelease:
    """Publish every current active technical variant or fail without writing.

    The caller owns the outer transaction. Bound retained source bytes are read
    and verified before the prior active release, new release, and audit event
    are changed atomically. This service never activates a Draft variant and
    grants no technical-selection, pricing, estimate, deployment, or Human
    Release authority.
    """

    current_time = _normalise_now(now)
    release_version = _required_version(version)
    release_notes = _normalise_notes(notes)
    authorised_actor = _authorised_actor(db, actor)

    existing = db.scalar(
        select(LibraryRelease)
        .where(
            LibraryRelease.library_type == "technical",
            LibraryRelease.version == release_version,
        )
        .with_for_update()
    )
    if existing is not None:
        raise TechnicalReleasePublicationError("TECHNICAL_RELEASE_VERSION_EXISTS")

    active_releases = list(
        db.scalars(
            select(LibraryRelease)
            .where(
                LibraryRelease.library_type == "technical",
                LibraryRelease.status == "active",
            )
            .order_by(LibraryRelease.created_at, LibraryRelease.id)
            .with_for_update()
        ).all()
    )
    if len(active_releases) > 1:
        raise TechnicalReleasePublicationError("TECHNICAL_RELEASE_ACTIVE_STATE_AMBIGUOUS")
    previous = active_releases[0] if active_releases else None
    records = _locked_current_technical_records(
        db,
        storage_root=storage_root,
        as_of=current_time,
    )
    payload = {
        "schema": TECHNICAL_RELEASE_MANIFEST_SCHEMA,
        "release_type": "technical",
        "version": release_version,
        "created_at": _timestamp_text(current_time),
        "created_by_id": authorised_actor.id,
        "record_count": len(records),
        "activated_draft_ids": [],
        "previous_release_id": previous.id if previous else None,
        "records": records,
        "notes": release_notes,
    }
    release_hash = _hash_manifest(payload)

    try:
        with db.begin_nested():
            if previous is not None:
                previous.status = "superseded"
                db.flush()
            release = LibraryRelease(
                library_type="technical",
                version=release_version,
                status="active",
                effective_date=current_time.date(),
                release_hash=release_hash,
                source_manifest=payload,
                notes=release_notes,
                created_by_id=authorised_actor.id,
                approved_by_id=authorised_actor.id,
                approved_at=current_time,
                supersedes_release_id=previous.id if previous else None,
            )
            db.add(release)
            db.flush()
            record_audit(
                db,
                actor=authorised_actor,
                action="publish_governed_technical_release",
                entity_type="library_release",
                entity_id=release.id,
                source_ip=source_ip,
                correlation_id=release_hash,
                previous_value=(
                    {
                        "release_id": previous.id,
                        "version": previous.version,
                        "release_hash": previous.release_hash,
                        "status": "active",
                    }
                    if previous
                    else None
                ),
                new_value={
                    "release_type": "technical",
                    "version": release_version,
                    "release_hash": release_hash,
                    "record_count": len(records),
                    "status": "active",
                    "draft_variants_activated": False,
                    "technical_selection_authority_granted": False,
                    "pricing_authority_granted": False,
                    "deployment_authority_granted": False,
                    "human_release_authority_granted": False,
                },
                reason=release_notes or f"Publish technical release {release_version}",
            )
            db.flush()
    except TechnicalReleasePublicationError:
        raise
    except SQLAlchemyError as exc:
        raise TechnicalReleasePublicationError(
            "TECHNICAL_RELEASE_PUBLICATION_WRITE_FAILED"
        ) from exc
    return release


def _locked_current_technical_records(
    db: Session,
    *,
    storage_root: Path,
    as_of: datetime,
) -> list[dict[str, Any]]:
    variants = list(
        db.scalars(
            select(TechnicalVariant)
            .where(TechnicalVariant.status == "active")
            .order_by(TechnicalVariant.variant_id, TechnicalVariant.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
    )
    if not variants:
        raise TechnicalReleasePublicationError("TECHNICAL_RELEASE_NO_ACTIVE_VARIANTS")

    by_key: dict[str, TechnicalVariant] = {}
    for variant in variants:
        if technical_variant_temporal_blockers(
            effective_date=variant.effective_date,
            expiry_date=variant.expiry_date,
            as_of=as_of.date(),
        ):
            raise TechnicalReleasePublicationError("TECHNICAL_RELEASE_ACTIVE_VARIANT_INELIGIBLE")
        key = technical_variant_logical_key(
            variant_id=variant.variant_id, source_json=variant.source_json
        )
        if key in by_key:
            raise TechnicalReleasePublicationError("TECHNICAL_RELEASE_ACTIVE_VARIANT_AMBIGUOUS")
        by_key[key] = variant

    document_ids = {
        variant.technical_document_id for variant in variants if variant.technical_document_id
    }
    documents = (
        list(
            db.scalars(
                select(TechnicalDocument)
                .where(TechnicalDocument.id.in_(document_ids))
                .order_by(TechnicalDocument.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            ).all()
        )
        if document_ids
        else []
    )
    documents_by_id = {document.id: document for document in documents}
    if set(documents_by_id) != document_ids:
        raise TechnicalReleasePublicationError("TECHNICAL_RELEASE_ACTIVE_VARIANT_INELIGIBLE")

    stored_file_ids = {document.stored_file_id for document in documents}
    stored_files = (
        list(
            db.scalars(
                select(StoredFile)
                .where(StoredFile.id.in_(stored_file_ids))
                .order_by(StoredFile.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            ).all()
        )
        if stored_file_ids
        else []
    )
    stored_files_by_id = {stored.id: stored for stored in stored_files}
    if set(stored_files_by_id) != stored_file_ids:
        raise TechnicalReleasePublicationError("TECHNICAL_RELEASE_ACTIVE_VARIANT_INELIGIBLE")

    for document in documents:
        stored = stored_files_by_id[document.stored_file_id]
        if technical_document_authority_blockers(
            status=document.status,
            expiry_date=document.expiry_date,
            stored_file_present=True,
            stored_file_purpose=stored.purpose,
            stored_file_scan_status=stored.malware_scan_status,
            stored_file_immutable=stored.immutable,
            as_of=as_of.date(),
        ):
            raise TechnicalReleasePublicationError("TECHNICAL_RELEASE_ACTIVE_VARIANT_INELIGIBLE")
        _verify_source_bytes(
            db,
            stored=stored,
            storage_root=storage_root,
        )

    return [
        _technical_record(by_key[key], documents_by_id, stored_files_by_id)
        for key in sorted(by_key)
    ]


def _verify_source_bytes(
    db: Session,
    *,
    stored: StoredFile,
    storage_root: Path,
) -> None:
    try:
        if str(db.get_bind().dialect.name).casefold() == "postgresql":
            read_clean_stored_file_for_update(
                db,
                stored_file_id=stored.id,
                storage_root=storage_root,
                required_purpose="technical_evidence",
            )
        else:
            read_verified_stored_file(
                stored,
                storage_root=storage_root,
                required_purpose="technical_evidence",
            )
    except StoredFileBindingError as exc:
        raise TechnicalReleasePublicationError("TECHNICAL_RELEASE_SOURCE_BYTES_INVALID") from exc


def _technical_record(
    variant: TechnicalVariant,
    documents_by_id: dict[str, TechnicalDocument],
    stored_files_by_id: dict[str, StoredFile],
) -> dict[str, Any]:
    document = documents_by_id.get(variant.technical_document_id or "")
    stored = stored_files_by_id.get(document.stored_file_id) if document else None
    return {
        "id": variant.id,
        "key": technical_variant_logical_key(
            variant_id=variant.variant_id, source_json=variant.source_json
        ),
        "variant_id": variant.variant_id,
        "system_id": variant.system_id,
        "frl": variant.frl,
        "source_document_reference": variant.source_document_reference,
        "source_page": variant.source_page,
        "source_hash": variant.source_hash,
        "record_version": variant.record_version,
        "source_binding": technical_release_source_binding(
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
        ),
    }


def _authorised_actor(db: Session, actor: User | None) -> User:
    if actor is None or not actor.id:
        raise TechnicalReleasePublicationError("TECHNICAL_RELEASE_PUBLICATION_PERMISSION_DENIED")
    retained = db.scalar(select(User).where(User.id == actor.id).with_for_update())
    if (
        retained is None
        or not retained.is_active
        or not has_permission(retained, "technical:approve")
    ):
        raise TechnicalReleasePublicationError("TECHNICAL_RELEASE_PUBLICATION_PERMISSION_DENIED")
    return retained


def _required_version(value: object) -> str:
    if not isinstance(value, str):
        raise TechnicalReleasePublicationError("TECHNICAL_RELEASE_VERSION_INVALID")
    normalised = value.strip()
    if not normalised or len(normalised) > 50:
        raise TechnicalReleasePublicationError("TECHNICAL_RELEASE_VERSION_INVALID")
    return normalised


def _normalise_notes(value: object) -> str:
    if not isinstance(value, str):
        raise TechnicalReleasePublicationError("TECHNICAL_RELEASE_NOTES_INVALID")
    return value.strip()


def _normalise_now(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise TechnicalReleasePublicationError("TECHNICAL_RELEASE_TIME_INVALID")
    return current.astimezone(UTC)


def _timestamp_text(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hash_manifest(value: dict[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "TECHNICAL_RELEASE_MANIFEST_SCHEMA",
    "TechnicalReleasePublicationError",
    "publish_governed_technical_release",
]
