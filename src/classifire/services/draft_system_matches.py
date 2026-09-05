"""Independent saved technical-candidate review; no compatibility or write authority."""

from __future__ import annotations

import copy
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import (
    DraftScope,
    DraftSystemMatch,
    DraftSystemMatchRevision,
    LibraryRelease,
    StoredFile,
    TechnicalDocument,
    TechnicalVariant,
    User,
    new_id,
)
from .draft_scope import DraftScopeError, _actor, _atomic, _valid_hash, get_draft, read_revision
from .draft_system_match_contract import (
    COMPARISON_NAMES,
    FIELD_NAMES,
    MANIFEST_FIELDS,
    MAX_CANDIDATES,
    MAX_MATCH_BYTES,
    MAX_SOURCE_BYTES,
    SCHEMA_VERSION,
    Decision,
    basis_hash,
    canonical,
    digest,
    envelope_hash,
    target_for,
    validate_binding,
    validate_envelope,
)
from .release_scope import _manifest_hash, active_technical_release_ids
from .storage import (
    StoredFileBindingError,
    read_clean_stored_file_for_update,
    read_verified_stored_file,
)
from .technical import Candidate, search_variants
from .technical_validity import (
    technical_document_authority_blockers,
    technical_release_source_binding,
)

MATCH_LIST_LIMIT = 20
MAX_RELEASE_RECORDS = 10000


class DraftSystemMatchError(DraftScopeError):
    """Safe user-facing code. No raw source content or internal paths are exposed."""


def _access(
    db: Session, actor: User, draft_id: str, *, write: bool = False
) -> tuple[User, DraftScope]:
    try:
        actor = _actor(db, actor, "project:write" if write else "project:read")
        actor = _actor(db, actor, "technical:read")
        return actor, get_draft(db, actor, draft_id)
    except DraftScopeError as exc:
        raise DraftSystemMatchError(exc.code, exc.status_code) from exc


def _scope(db: Session, actor: User, draft_id: str, revision: int | None = None) -> dict[str, Any]:
    try:
        return read_revision(db, actor, draft_id, revision)
    except DraftScopeError as exc:
        raise DraftSystemMatchError(exc.code, exc.status_code) from exc


def list_technical_releases(db: Session, actor: User) -> list[dict[str, str]]:
    try:
        _actor(db, actor, "project:read")
        _actor(db, actor, "technical:read")
    except DraftScopeError as exc:
        raise DraftSystemMatchError(exc.code, exc.status_code) from exc
    return [
        {"id": row.id, "version": row.version}
        for row in db.scalars(
            select(LibraryRelease)
            .where(LibraryRelease.library_type == "technical", LibraryRelease.status == "active")
            .order_by(LibraryRelease.created_at.desc(), LibraryRelease.id)
            .limit(20)
        )
    ]


def _release(
    db: Session, release_id: str
) -> tuple[LibraryRelease, dict[str, dict[str, Any]], set[str]]:
    release = db.scalar(
        select(LibraryRelease)
        .where(LibraryRelease.id == release_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if release is None:
        raise DraftSystemMatchError("MATCH_RELEASE_NOT_FOUND", 404)
    try:
        manifest = release.source_manifest
        if type(manifest) is not dict or type(manifest.get("records")) is not list:
            raise ValueError("manifest")
        records = manifest["records"]
        if not 1 <= len(records) <= MAX_RELEASE_RECORDS:
            raise ValueError("records")
        if "record_count" in manifest and (
            type(manifest["record_count"]) is not int or manifest["record_count"] != len(records)
        ):
            raise ValueError("records")
        by_id: dict[str, dict[str, Any]] = {}
        for record in records:
            if (
                type(record) is not dict
                or type(record.get("id")) is not str
                or not 1 <= len(record["id"]) <= 36
                or record["id"] in by_id
            ):
                raise ValueError("records")
            by_id[record["id"]] = record
        if release.effective_date and release.effective_date > date.today():
            raise ValueError("effective_date")
        ids = active_technical_release_ids(db, release)
        for variant in db.scalars(
            select(TechnicalVariant)
            .where(TechnicalVariant.id.in_(ids))
            .with_for_update()
            .execution_options(populate_existing=True)
        ):
            record = by_id[variant.id]
            for key in (
                "variant_id",
                "system_id",
                "frl",
                "source_document_reference",
                "source_page",
                "source_hash",
                "record_version",
            ):
                if key in record and (
                    record[key] != getattr(variant, key)
                    or (key == "record_version" and type(record[key]) is not int)
                ):
                    raise ValueError("published_record")
        return release, by_id, ids
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        RecursionError,
        ArithmeticError,
    ) as exc:
        raise DraftSystemMatchError("MATCH_RELEASE_INVALID", 422) from exc


def _fields(variant: TechnicalVariant) -> dict[str, str | bool | None]:
    return {
        key: (
            value if key == "expert_review_required" else str(value) if value is not None else None
        )
        for key in FIELD_NAMES
        for value in (getattr(variant, key),)
    }


def _bound_rows(
    db: Session, variant: TechnicalVariant
) -> tuple[TechnicalDocument | None, StoredFile | None]:
    document = (
        db.scalar(
            select(TechnicalDocument)
            .where(TechnicalDocument.id == variant.technical_document_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if variant.technical_document_id
        else None
    )
    stored = (
        db.get(StoredFile, document.stored_file_id, populate_existing=True) if document else None
    )
    return document, stored


def _binding(
    variant: TechnicalVariant, document: TechnicalDocument | None, stored: StoredFile | None
) -> dict[str, Any]:
    return technical_release_source_binding(
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


def _verify_files(db: Session, files: dict[str, StoredFile], storage_root: Path) -> None:
    total = 0
    for stored in files.values():
        if type(stored.size_bytes) is not int or not 1 <= stored.size_bytes <= MAX_SOURCE_BYTES:
            raise DraftSystemMatchError("MATCH_SOURCE_LIMIT", 422)
        total += stored.size_bytes
    if total > MAX_SOURCE_BYTES:
        raise DraftSystemMatchError("MATCH_SOURCE_LIMIT", 422)
    try:
        for stored in files.values():
            if db.get_bind().dialect.name == "postgresql":
                read_clean_stored_file_for_update(
                    db,
                    stored_file_id=stored.id,
                    storage_root=storage_root,
                    required_purpose="technical_evidence",
                )
            else:
                read_verified_stored_file(
                    stored, storage_root=storage_root, required_purpose="technical_evidence"
                )
    except StoredFileBindingError as exc:
        raise DraftSystemMatchError("MATCH_SOURCE_INVALID", 422) from exc


def _candidate(
    db: Session, result: Candidate, record: dict[str, Any], at: str, files: dict[str, StoredFile]
) -> dict[str, Any]:
    variant = result.variant
    fields = _fields(variant)
    document, stored = _bound_rows(db, variant)
    published = {key: copy.deepcopy(record[key]) for key in MANIFEST_FIELDS if key in record}
    binding = published.get("source_binding")
    blockers = list(result.blockers)
    source: dict[str, Any] = {
        "state": "manifest_unbound",
        "binding": _binding(variant, document, stored),
        "variant_source_hash": variant.source_hash,
        "verified_at": None,
        "verification": "unresolved",
    }
    if binding is not None:
        try:
            validate_binding(binding)
        except (ValueError, TypeError, KeyError) as exc:
            raise DraftSystemMatchError("MATCH_RELEASE_INVALID", 422) from exc
        if binding != _binding(variant, document, stored):
            raise DraftSystemMatchError("MATCH_RELEASE_INVALID", 422)
        if binding["state"] == "bound":
            if (
                document is None
                or stored is None
                or not _valid_hash(variant.source_hash)
                or variant.source_hash != stored.sha256
                or record.get("source_hash") != stored.sha256
            ):
                raise DraftSystemMatchError("MATCH_SOURCE_INVALID", 422)
            if technical_document_authority_blockers(
                status=document.status,
                expiry_date=document.expiry_date,
                stored_file_present=True,
                stored_file_purpose=stored.purpose,
                stored_file_scan_status=stored.malware_scan_status,
                stored_file_immutable=stored.immutable,
            ):
                raise DraftSystemMatchError("MATCH_SOURCE_INVALID", 422)
            source = {
                "state": "bound",
                "binding": binding,
                "variant_source_hash": variant.source_hash,
                "verified_at": at,
                "verification": "exact_bytes",
            }
            files[stored.id] = stored
        else:
            source["state"] = "legacy_unbound"
            source["binding"] = binding
    if source["state"] != "bound":
        blockers.append("source_binding_unresolved")
    if "record_version" not in record:
        blockers.append("published_record_version_unresolved")
    return {
        "candidate_id": variant.id,
        "variant_id": variant.variant_id,
        "system_id": variant.system_id,
        "record_version": variant.record_version,
        "fields": fields,
        "fields_sha256": digest(fields),
        "release_record": published,
        "source": source,
        "score": str(result.score),
        "comparisons": result.comparisons,
        "blockers": list(dict.fromkeys(blockers)),
    }


def _retrieval(scope: dict[str, Any], target: dict[str, Any], at: str) -> dict[str, Any]:
    openings = {item["id"]: item for item in scope["content"]["openings"]}
    services = {item["id"]: item for item in scope["content"]["services"]}
    opening = openings.get(target["opening_id"])
    service = services.get(target["service_id"])
    inputs: dict[str, str | None] = {key: None for key in COMPARISON_NAMES}
    inputs["service_type"] = service["service_type"] or None if service else None
    inputs["substrate"] = opening["substrate"] or None if opening else None
    missing = [
        key
        for key, item in inputs.items()
        if item is None or str(item).strip().casefold() in {"unknown", "unresolved", "not stated"}
    ]
    missing.extend(
        [
            "service_size",
            "substrate_thickness",
            "insulation",
            "installation_face",
            "annular_gap",
            "service_spacing",
            "edge_distances",
            "support",
            "fixings",
            "jurisdiction",
        ]
    )
    if opening is None:
        missing.append("selected_opening")
    if service is None and not target["blank_opening"]:
        missing.append("selected_service")
    return {
        "version": 1,
        "inputs": inputs,
        "missing_criteria": missing,
        "unassessed_criteria": [
            "technical_applicability",
            "shared_opening_configuration",
            "hard_exclusions",
            "dependencies",
            "authorised_evidence_review",
            "other_scope_items",
        ],
        "truncated": False,
        "candidate_limit": MAX_CANDIDATES,
        "evaluated_at": at,
    }


def _validate(
    value: dict[str, Any], code: str = "MATCH_ARTIFACT_INVALID", status: int = 422
) -> None:
    try:
        validate_envelope(value)
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        RecursionError,
        ArithmeticError,
    ) as exc:
        raise DraftSystemMatchError(code, status) from exc


def _audit(
    db: Session,
    actor: User,
    draft: DraftScope,
    match_id: str,
    action: str,
    envelope: dict[str, Any],
) -> None:
    record_audit(
        db,
        actor=actor,
        action="draft_system_match." + action,
        entity_type="draft_system_match",
        entity_id=match_id,
        project_id=draft.project_id,
        new_value={
            "revision": envelope["revision"],
            "sha256": envelope["sha256"],
            "scope_sha256": envelope["scope"]["sha256"],
            "release_sha256": envelope["release"]["sha256"],
        },
    )


def create_match(
    db: Session,
    actor: User,
    draft_id: str,
    scope_revision: int,
    release_id: str,
    opening_id: str | None,
    service_id: str | None,
    *,
    storage_root: Path,
) -> DraftSystemMatch:
    actor, draft = _access(db, actor, draft_id, write=True)
    if type(scope_revision) is not int or scope_revision < 1:
        raise DraftSystemMatchError("DRAFT_REVISION_NOT_FOUND", 404)
    scope = _scope(db, actor, draft_id, scope_revision)
    try:
        target = target_for(scope, opening_id, service_id)
    except (ValueError, TypeError, KeyError) as exc:
        raise DraftSystemMatchError("MATCH_TARGET_INVALID", 422) from exc
    try:
        with _atomic(db):
            actor, draft = _access(db, actor, draft_id, write=True)
            release, records, ids = _release(db, release_id)
            selected_release_hash = release.release_hash
            created = datetime.now(UTC)
            at = created.isoformat()
            retrieval = _retrieval(scope, target, at)
            results = search_variants(
                db,
                **retrieval["inputs"],
                release_record_ids=ids,
                limit=MAX_CANDIDATES + 1,
                include_draft=False,
            )
            retrieval["truncated"] = len(results) > MAX_CANDIDATES
            files: dict[str, StoredFile] = {}
            candidates = [
                _candidate(db, result, records[result.variant.id], at, files)
                for result in results[:MAX_CANDIDATES]
            ]
            _verify_files(db, files, storage_root)
            if _scope(db, actor, draft_id, scope_revision) != scope:
                raise DraftSystemMatchError("MATCH_SCOPE_CHANGED", 409)
            if _release(db, release_id)[0].release_hash != selected_release_hash:
                raise DraftSystemMatchError("MATCH_RELEASE_CHANGED", 409)
            for candidate in candidates:
                current_variant = db.get(
                    TechnicalVariant, candidate["candidate_id"], populate_existing=True
                )
                if (
                    current_variant is None
                    or digest(_fields(current_variant)) != candidate["fields_sha256"]
                ):
                    raise DraftSystemMatchError("MATCH_CANDIDATE_CHANGED", 409)
            actor, draft = _access(db, actor, draft_id, write=True)
            envelope = {
                "schema_version": SCHEMA_VERSION,
                "artifact_id": new_id(),
                "project_id": draft.project_id,
                "revision": 1,
                "parent_hash": None,
                "created_by": actor.id,
                "created_at": at,
                "state": "Draft",
                "review_status": "unreviewed",
                "provenance": "manual_review",
                "coverage": "selected_target_only",
                "scope": scope,
                "release": {
                    "id": release.id,
                    "version": release.version,
                    "sha256": release.release_hash,
                    "effective_date": release.effective_date.isoformat()
                    if release.effective_date
                    else None,
                },
                "target": target,
                "retrieval": retrieval,
                "candidates": candidates,
                "decisions": [
                    {"candidate_id": item["candidate_id"], "decision": "unreviewed", "notes": ""}
                    for item in candidates
                ],
            }
            envelope["sha256"] = envelope_hash(envelope)
            _validate(envelope)
            match = DraftSystemMatch(
                id=envelope["artifact_id"],
                draft_scope_id=draft.id,
                scope_revision=scope_revision,
                scope_hash=scope["sha256"],
                release_id=release.id,
                release_hash=release.release_hash,
                latest_revision=1,
                latest_hash=envelope["sha256"],
                basis_hash=basis_hash(envelope),
                created_by_id=actor.id,
                created_at=created,
            )
            db.add(match)
            db.flush()
            db.add(
                DraftSystemMatchRevision(
                    match_id=match.id,
                    revision=1,
                    parent_hash=None,
                    content_hash=envelope["sha256"],
                    envelope_json=canonical(envelope).decode("utf-8"),
                    created_by_id=actor.id,
                    created_at=created,
                )
            )
            _audit(db, actor, draft, match.id, "create", envelope)
            db.flush()
        return match
    except IntegrityError as exc:
        raise DraftSystemMatchError("MATCH_SAVE_CONFLICT", 409) from exc


def _match(
    db: Session, actor: User, draft_id: str, match_id: str, *, write: bool = False
) -> tuple[User, DraftScope, DraftSystemMatch]:
    actor, draft = _access(db, actor, draft_id, write=write)
    match = db.scalar(
        select(DraftSystemMatch)
        .where(DraftSystemMatch.id == match_id, DraftSystemMatch.draft_scope_id == draft.id)
        .execution_options(populate_existing=True)
    )
    if match is None:
        raise DraftSystemMatchError("MATCH_NOT_FOUND", 404)
    return actor, draft, match


def _read(
    db: Session, actor: User, draft: DraftScope, match: DraftSystemMatch, revision: int
) -> dict[str, Any]:
    if type(revision) is not int or not 1 <= revision <= match.latest_revision:
        raise DraftSystemMatchError("MATCH_REVISION_NOT_FOUND", 404)
    row = db.scalar(
        select(DraftSystemMatchRevision)
        .where(
            DraftSystemMatchRevision.match_id == match.id,
            DraftSystemMatchRevision.revision == revision,
        )
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise DraftSystemMatchError("MATCH_REVISION_INTEGRITY_FAILED", 409)
    try:
        if len(row.envelope_json.encode("utf-8")) > MAX_MATCH_BYTES:
            raise ValueError("size")
        envelope = cast(dict[str, Any], json.loads(row.envelope_json))
        validate_envelope(envelope)
        created = (
            row.created_at.replace(tzinfo=UTC) if row.created_at.tzinfo is None else row.created_at
        )
        if (
            envelope["artifact_id"] != match.id
            or envelope["project_id"] != draft.project_id
            or envelope["revision"] != row.revision
            or envelope["parent_hash"] != row.parent_hash
            or envelope["created_by"] != row.created_by_id
            or envelope["created_at"] != created.astimezone(UTC).isoformat()
            or envelope["sha256"] != row.content_hash
            or canonical(envelope).decode("utf-8") != row.envelope_json
            or basis_hash(envelope) != match.basis_hash
        ):
            raise ValueError("binding")
        if (
            envelope["scope"]["artifact_id"] != draft.id
            or envelope["scope"]["revision"] != match.scope_revision
            or envelope["scope"]["sha256"] != match.scope_hash
            or envelope["release"]["id"] != match.release_id
            or envelope["release"]["sha256"] != match.release_hash
        ):
            raise ValueError("dependency")
        if _scope(db, actor, draft.id, match.scope_revision) != envelope["scope"]:
            raise ValueError("scope")
        if revision == match.latest_revision and row.content_hash != match.latest_hash:
            raise ValueError("latest")
        if revision > 1:
            parent = db.scalar(
                select(DraftSystemMatchRevision.content_hash).where(
                    DraftSystemMatchRevision.match_id == match.id,
                    DraftSystemMatchRevision.revision == revision - 1,
                )
            )
            if row.parent_hash != parent or parent is None:
                raise ValueError("parent")
        return envelope
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        RecursionError,
        ArithmeticError,
    ) as exc:
        raise DraftSystemMatchError("MATCH_REVISION_INTEGRITY_FAILED", 409) from exc


def read_match_revision(
    db: Session, actor: User, draft_id: str, match_id: str, revision: int | None = None
) -> dict[str, Any]:
    actor, draft, match = _match(db, actor, draft_id, match_id)
    return _read(db, actor, draft, match, match.latest_revision if revision is None else revision)


def list_matches(db: Session, actor: User, draft_id: str) -> list[DraftSystemMatch]:
    actor, draft = _access(db, actor, draft_id)
    matches = list(
        db.scalars(
            select(DraftSystemMatch)
            .where(DraftSystemMatch.draft_scope_id == draft.id)
            .order_by(DraftSystemMatch.created_at.desc(), DraftSystemMatch.id)
            .limit(MATCH_LIST_LIMIT)
        )
    )
    for match in matches:
        _read(db, actor, draft, match, match.latest_revision)
    return matches


def save_review(
    db: Session,
    actor: User,
    draft_id: str,
    match_id: str,
    expected_revision: int,
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    actor, draft, match = _match(db, actor, draft_id, match_id, write=True)
    if type(expected_revision) is not int or expected_revision != match.latest_revision:
        raise DraftSystemMatchError("MATCH_REVISION_CONFLICT", 409)
    prior = _read(db, actor, draft, match, expected_revision)
    try:
        if type(decisions) is not list or len(decisions) > MAX_CANDIDATES:
            raise ValueError("decisions")
        parsed = TypeAdapter(list[Decision]).validate_python(decisions, strict=True)
        by_id = {item.candidate_id: item.model_dump(mode="json") for item in parsed}
        candidate_ids = [item["candidate_id"] for item in prior["candidates"]]
        if len(by_id) != len(parsed) or set(by_id) != set(candidate_ids):
            raise ValueError("decisions")
    except (ValueError, TypeError, ValidationError) as exc:
        raise DraftSystemMatchError("MATCH_DECISIONS_INVALID", 422) from exc
    envelope = copy.deepcopy(prior)
    created = datetime.now(UTC)
    envelope.update(
        revision=expected_revision + 1,
        parent_hash=prior["sha256"],
        created_by=actor.id,
        created_at=created.isoformat(),
        decisions=[by_id[key] for key in candidate_ids],
    )
    envelope["sha256"] = envelope_hash(envelope)
    _validate(envelope)
    try:
        with _atomic(db):
            actor, draft = _access(db, actor, draft_id, write=True)
            changed = db.execute(
                update(DraftSystemMatch)
                .where(
                    DraftSystemMatch.id == match.id,
                    DraftSystemMatch.draft_scope_id == draft.id,
                    DraftSystemMatch.latest_revision == expected_revision,
                    DraftSystemMatch.latest_hash == prior["sha256"],
                    DraftSystemMatch.basis_hash == basis_hash(prior),
                )
                .values(latest_revision=expected_revision + 1, latest_hash=envelope["sha256"])
                .execution_options(synchronize_session=False)
            )
            if changed.rowcount != 1:  # type: ignore[attr-defined]
                raise DraftSystemMatchError("MATCH_REVISION_CONFLICT", 409)
            db.add(
                DraftSystemMatchRevision(
                    match_id=match.id,
                    revision=expected_revision + 1,
                    parent_hash=prior["sha256"],
                    content_hash=envelope["sha256"],
                    envelope_json=canonical(envelope).decode("utf-8"),
                    created_by_id=actor.id,
                    created_at=created,
                )
            )
            _audit(db, actor, draft, match.id, "review", envelope)
            db.flush()
        db.refresh(match)
        return envelope
    except IntegrityError as exc:
        raise DraftSystemMatchError("MATCH_REVISION_CONFLICT", 409) from exc


def revision_bytes(
    db: Session, actor: User, draft_id: str, match_id: str, revision: int | None = None
) -> bytes:
    actor, draft = _access(db, actor, draft_id)
    envelope = read_match_revision(db, actor, draft_id, match_id, revision)
    _audit(db, actor, draft, match_id, "download", envelope)
    db.flush()
    return canonical(envelope)


def match_staleness(
    db: Session,
    actor: User,
    draft_id: str,
    match_id: str,
    revision: int | None = None,
    *,
    storage_root: Path,
) -> list[str]:
    envelope = read_match_revision(db, actor, draft_id, match_id, revision)
    reasons: list[str] = []
    current_scope = _scope(db, actor, draft_id)
    if current_scope["sha256"] != envelope["scope"]["sha256"]:
        reasons.append("SCOPE_CHANGED")
    release = db.get(LibraryRelease, envelope["release"]["id"], populate_existing=True)
    if release is None:
        reasons.append("RELEASE_UNAVAILABLE")
    elif release.status != "active":
        reasons.append("RELEASE_NO_LONGER_ACTIVE")
    if release is not None:
        try:
            if (
                release.release_hash != envelope["release"]["sha256"]
                or type(release.source_manifest) is not dict
                or _manifest_hash(release.source_manifest) != release.release_hash
            ):
                reasons.append("RELEASE_CHANGED")
        except (ValueError, TypeError, RecursionError, OverflowError):
            reasons.append("RELEASE_CHANGED")
    current_release_id = db.scalar(
        select(LibraryRelease.id)
        .where(LibraryRelease.library_type == "technical", LibraryRelease.status == "active")
        .order_by(LibraryRelease.created_at.desc(), LibraryRelease.id)
        .limit(1)
    )
    if current_release_id is not None and current_release_id != envelope["release"]["id"]:
        reasons.append("NEW_TECHNICAL_RELEASE_AVAILABLE")
    if release is not None:
        if release.library_type != "technical" or (
            release.effective_date and release.effective_date > date.today()
        ):
            reasons.append("RELEASE_NO_LONGER_ELIGIBLE")
        if (
            release.version != envelope["release"]["version"]
            or (release.effective_date.isoformat() if release.effective_date else None)
            != envelope["release"]["effective_date"]
        ):
            reasons.append("RELEASE_CHANGED")
    files: dict[str, StoredFile] = {}
    for candidate in envelope["candidates"]:
        variant = db.get(TechnicalVariant, candidate["candidate_id"], populate_existing=True)
        if variant is None:
            reasons.append("CANDIDATE_UNAVAILABLE")
            continue
        if (
            variant.record_version != candidate["record_version"]
            or variant.variant_id != candidate["variant_id"]
            or variant.system_id != candidate["system_id"]
            or digest(_fields(variant)) != candidate["fields_sha256"]
        ):
            reasons.append("CANDIDATE_CHANGED")
        if (
            variant.status != "active"
            or (variant.effective_date and variant.effective_date > date.today())
            or (variant.expiry_date and variant.expiry_date < date.today())
        ):
            reasons.append("CANDIDATE_NO_LONGER_CURRENT")
        document, stored = _bound_rows(db, variant)
        if (
            variant.source_hash != candidate["source"]["variant_source_hash"]
            or _binding(variant, document, stored) != candidate["source"]["binding"]
        ):
            reasons.append("SOURCE_BINDING_CHANGED")
        if candidate["source"]["state"] != "bound":
            continue
        if document is None or stored is None:
            reasons.append("SOURCE_UNAVAILABLE")
            continue
        if (
            _binding(variant, document, stored) != candidate["source"]["binding"]
            or variant.source_hash != stored.sha256
        ):
            reasons.append("SOURCE_BINDING_CHANGED")
            continue
        if technical_document_authority_blockers(
            status=document.status,
            expiry_date=document.expiry_date,
            stored_file_present=True,
            stored_file_purpose=stored.purpose,
            stored_file_scan_status=stored.malware_scan_status,
            stored_file_immutable=stored.immutable,
        ):
            reasons.append("SOURCE_AUTHORITY_CHANGED")
            continue
        files[stored.id] = stored
    try:
        _verify_files(db, files, storage_root)
    except DraftSystemMatchError:
        reasons.append("SOURCE_BYTES_UNAVAILABLE_OR_CHANGED")
    return list(dict.fromkeys(reasons))
