"""Deterministic, manual-only Draft Scope use cases shared by all interfaces.

Callers own their transaction. These use cases flush but never commit, invoke AI,
recalculate estimates, or write canonical defects, services, openings or locks.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import DraftScope, DraftScopeRevision, Project, User, new_id
from ..security import has_permission
from .draft_scope_evidence import (
    ENTITY_EVIDENCE_SCHEMA_VERSION,
    EVIDENCE_SCHEMA_VERSION,
    EVIDENCE_SCHEMAS,
    XLSX_EVIDENCE_SCHEMA_VERSION,
    reference_identity,
    validate_evidence_refs,
)

MAX_PAYLOAD_BYTES = 256 * 1024
SCHEMA_VERSION = "CLASSIFIRE-DRAFT-SCOPE-v1"
IMPORTED_SCHEMA_VERSION = "CLASSIFIRE-DRAFT-SCOPE-v2"
MAX_ARTIFACT_BYTES = MAX_PAYLOAD_BYTES + 32768
MAX_IMPORT_LINEAGE = 16
EvidenceState = Literal["Confirmed", "Inferred", "Provisional", "Unresolved"]
EntityId = Annotated[UUID, Field(strict=False)]
Label = Annotated[str, Field(min_length=1, max_length=200)]
Note = Annotated[str, Field(min_length=1, max_length=4000)]
DecimalText = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]{0,8})(\.[0-9]{1,6})?$")]


class DraftScopeError(ValueError):
    def __init__(self, code: str, status_code: int = 422, *, findings: list[dict] | None = None):
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.findings = findings or []


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class DraftDefect(_Contract):
    id: EntityId
    label: Label
    description: Annotated[str, Field(max_length=4000)] = ""


class DraftOpening(_Contract):
    id: EntityId
    label: Label
    defect_id: EntityId | None = None
    plane: Literal["wall", "floor", "soffit", "unknown"] = "unknown"
    substrate: Annotated[str, Field(max_length=500)] = ""
    width_mm: DecimalText | None = None
    height_mm: DecimalText | None = None
    blank: bool = False
    state: EvidenceState = "Unresolved"

    @field_validator("width_mm", "height_mm")
    @classmethod
    def normalize_dimensions(cls, value: str | None) -> str | None:
        return _decimal(value)


class DraftService(_Contract):
    id: EntityId
    label: Label
    opening_ids: Annotated[list[EntityId], Field(max_length=500)] = Field(default_factory=list)
    service_type: Annotated[str, Field(max_length=500)] = ""
    quantity: DecimalText | None = None
    unit: Literal["each", "m", "mm"] = "each"
    state: EvidenceState = "Unresolved"

    @field_validator("quantity")
    @classmethod
    def normalize_quantity(cls, value: str | None) -> str | None:
        return _decimal(value)


class DraftObservation(_Contract):
    id: EntityId
    text: Note
    state: EvidenceState = "Unresolved"


class DraftScopePayload(_Contract):
    defects: Annotated[list[DraftDefect], Field(max_length=500)] = Field(default_factory=list)
    openings: Annotated[list[DraftOpening], Field(max_length=500)] = Field(default_factory=list)
    services: Annotated[list[DraftService], Field(max_length=500)] = Field(default_factory=list)
    observations: Annotated[list[DraftObservation], Field(max_length=500)] = Field(
        default_factory=list
    )
    assumptions: Annotated[list[Note], Field(max_length=100)] = Field(default_factory=list)
    exclusions: Annotated[list[Note], Field(max_length=100)] = Field(default_factory=list)


def _decimal(value: str | None) -> str | None:
    if value is None:
        return None
    return format(Decimal(value).normalize(), "f")


def _json(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise DraftScopeError("DRAFT_PAYLOAD_INVALID") from exc


def validate_payload(payload: dict) -> tuple[DraftScopePayload, list[dict[str, str]]]:
    if not isinstance(payload, dict) or len(_json(payload)) > MAX_PAYLOAD_BYTES:
        raise DraftScopeError("DRAFT_PAYLOAD_INVALID")
    try:
        content = DraftScopePayload.model_validate(payload)
    except ValidationError as exc:
        # Field paths only; never echo submitted content or Pydantic input values.
        findings = [
            {
                "path": ".".join(str(part) for part in error["loc"]),
                "code": "INVALID_FIELD",
                "message": "Check the field type, value and length.",
                "severity": "error",
            }
            for error in exc.errors(include_input=False, include_url=False)[:50]
        ]
        raise DraftScopeError("DRAFT_PAYLOAD_INVALID", findings=findings) from exc
    if len(_json(content.model_dump(mode="json"))) > MAX_PAYLOAD_BYTES:
        raise DraftScopeError("DRAFT_PAYLOAD_INVALID")
    ids: set[UUID] = set()
    for items in (content.defects, content.openings, content.services, content.observations):
        for item in items:
            if item.id in ids:
                raise DraftScopeError("DRAFT_DUPLICATE_ID")
            ids.add(item.id)
    defects = {item.id for item in content.defects}
    openings = {item.id: item for item in content.openings}
    for opening in content.openings:
        if opening.defect_id is not None and opening.defect_id not in defects:
            raise DraftScopeError("DRAFT_INVALID_REFERENCE")
    for service in content.services:
        if len(set(service.opening_ids)) != len(service.opening_ids):
            raise DraftScopeError("DRAFT_DUPLICATE_LINK")
        for opening_id in service.opening_ids:
            if opening_id not in openings:
                raise DraftScopeError("DRAFT_INVALID_REFERENCE")
            if openings[opening_id].blank:
                raise DraftScopeError("DRAFT_BLANK_OPENING_HAS_SERVICE")
    warnings: list[dict[str, str]] = []

    def warn(code: str, path: str, message: str) -> None:
        warnings.append({"code": code, "path": path, "message": message, "severity": "warning"})

    warn(
        "MANUAL_UNREVIEWED",
        "",
        "Draft only; manual entries do not establish source evidence or approval.",
    )
    if not content.defects and not content.openings and not content.services:
        warn("SCOPE_EMPTY", "", "Add scope information when it is available.")
    for index, opening in enumerate(content.openings):
        if opening.plane == "unknown" or not opening.substrate:
            warn("OPENING_FACTS_MISSING", f"openings.{index}", "Plane or substrate is unresolved.")
        if opening.width_mm is None or opening.height_mm is None:
            warn("OPENING_DIMENSIONS_MISSING", f"openings.{index}", "Dimensions are unavailable.")
        if opening.state != "Confirmed":
            warn(
                "OPENING_REVIEW_REQUIRED", f"openings.{index}", "Opening needs evidence and review."
            )
    for index, service in enumerate(content.services):
        if not service.opening_ids or not service.service_type:
            warn(
                "SERVICE_FACTS_MISSING", f"services.{index}", "Service type or openings unresolved."
            )
        if service.quantity is None:
            warn("QUANTITY_UNRESOLVED", f"services.{index}.quantity", "No quantity is assumed.")
        if service.state != "Confirmed":
            warn(
                "SERVICE_REVIEW_REQUIRED", f"services.{index}", "Service needs evidence and review."
            )
    return content, warnings


def _actor(db: Session, actor: User, permission: str) -> User:
    if not isinstance(actor, User) or not actor.id:
        raise DraftScopeError("DRAFT_PERMISSION_DENIED", 403)
    current = db.get(User, actor.id, populate_existing=True)
    if not current or not current.is_active or not has_permission(current, permission):
        raise DraftScopeError("DRAFT_PERMISSION_DENIED", 403)
    return current


def get_draft(db: Session, actor: User, draft_id: str) -> DraftScope:
    actor = _actor(db, actor, "project:read")
    draft = db.get(DraftScope, draft_id, populate_existing=True)
    if not draft or (actor.role != "administrator" and draft.owner_user_id != actor.id):
        raise DraftScopeError("DRAFT_NOT_FOUND", 404)
    return draft


def list_drafts(db: Session, actor: User) -> list[DraftScope]:
    actor = _actor(db, actor, "project:read")
    query = select(DraftScope).order_by(DraftScope.updated_at.desc(), DraftScope.id)
    if actor.role != "administrator":
        query = query.where(DraftScope.owner_user_id == actor.id)
    return list(db.scalars(query))


@contextmanager
def _atomic(db: Session) -> Iterator[None]:
    # sqlite3 legacy transaction mode does not BEGIN for SELECT or SAVEPOINT.
    # Without this a released savepoint can commit despite caller rollback.
    connection = db.connection()
    if connection.dialect.name == "sqlite":
        driver = connection.connection.driver_connection
        if not getattr(driver, "in_transaction", False):
            connection.exec_driver_sql("BEGIN")
    with db.begin_nested():
        yield


def _create(db: Session, actor: User, project: Project) -> DraftScope:
    draft = DraftScope(
        id=new_id(), project_id=project.id, owner_user_id=actor.id, latest_revision=0
    )
    db.add(draft)
    db.flush()
    save_revision(db, actor, draft.id, 0, {})
    return draft


def create_draft_project(db: Session, actor: User, reference: str, name: str) -> DraftScope:
    actor = _actor(db, actor, "project:write")
    if (
        not isinstance(reference, str)
        or not 1 <= len(reference.strip()) <= 100
        or not isinstance(name, str)
        or not 1 <= len(name.strip()) <= 300
    ):
        raise DraftScopeError("DRAFT_PROJECT_INVALID")
    try:
        with _atomic(db):
            project = Project(id=new_id(), reference=reference.strip(), name=name.strip())
            db.add(project)
            db.flush()
            draft = _create(db, actor, project)
        return draft
    except IntegrityError as exc:
        raise DraftScopeError("DRAFT_PROJECT_CONFLICT", 409) from exc


def create_for_existing_project(db: Session, actor: User, project_id: str) -> DraftScope:
    actor = _actor(db, actor, "project:write")
    if actor.role != "administrator":
        raise DraftScopeError("DRAFT_PERMISSION_DENIED", 403)
    project = db.get(Project, project_id)
    if project is None:
        raise DraftScopeError("DRAFT_NOT_FOUND", 404)
    with _atomic(db):
        return _create(db, actor, project)


_ENVELOPE_KEYS = frozenset(
    {
        "schema_version",
        "artifact_id",
        "project_id",
        "revision",
        "parent_hash",
        "created_by",
        "created_at",
        "state",
        "provenance",
        "review_status",
        "content",
        "sha256",
    }
)
_LINEAGE_KEYS = frozenset(
    {
        "schema_version",
        "artifact_id",
        "project_id",
        "revision",
        "created_by",
        "created_at",
        "sha256",
        "file_sha256",
    }
)


def _valid_hash(value: Any) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _claim_metadata(value: dict[str, Any]) -> None:
    # These are portable claims, never proof that the named foreign identity exists.
    if value["schema_version"] not in (
        SCHEMA_VERSION,
        IMPORTED_SCHEMA_VERSION,
        *EVIDENCE_SCHEMAS,
    ):
        raise ValueError("schema")
    for name in ("artifact_id", "project_id", "created_by"):
        field = value[name]
        if type(field) is not str or str(UUID(field)) != field:
            raise ValueError("identity")
    if type(value["revision"]) is not int or not 1 <= value["revision"] <= 2_147_483_647:
        raise ValueError("revision")
    if type(value["created_at"]) is not str or len(value["created_at"]) > 40:
        raise ValueError("timestamp")
    timestamp = datetime.fromisoformat(value["created_at"])
    if timestamp.tzinfo is None or timestamp.astimezone(UTC).isoformat() != value["created_at"]:
        raise ValueError("timestamp")
    if not _valid_hash(value["sha256"]):
        raise ValueError("hash")


def _validate_lineage(entries: Any) -> None:
    if type(entries) is not list or not 1 <= len(entries) <= MAX_IMPORT_LINEAGE:
        raise ValueError("lineage")
    for entry in entries:
        if type(entry) is not dict or set(entry) != _LINEAGE_KEYS:
            raise ValueError("lineage")
        _claim_metadata(entry)
        if not _valid_hash(entry["file_sha256"]):
            raise ValueError("lineage")


def _envelope_shape(envelope: Any) -> None:
    if type(envelope) is not dict:
        raise ValueError("shape")
    version = envelope.get("schema_version")
    expected = _ENVELOPE_KEYS
    if version in (IMPORTED_SCHEMA_VERSION, *EVIDENCE_SCHEMAS):
        expected = expected | {"import_lineage"}
    if version in EVIDENCE_SCHEMAS:
        expected = expected | {"evidence_refs"}
    if set(envelope) != expected:
        raise ValueError("shape")
    if envelope["state"] != "Draft" or envelope["review_status"] != "unreviewed":
        raise ValueError("authority")
    if version == SCHEMA_VERSION:
        if envelope["provenance"] != "manual":
            raise ValueError("provenance")
    elif version == IMPORTED_SCHEMA_VERSION:
        if envelope["provenance"] not in ("imported", "manual_edit"):
            raise ValueError("provenance")
        _validate_lineage(envelope["import_lineage"])
    elif version in EVIDENCE_SCHEMAS:
        if envelope["provenance"] not in ("evidence_review", "imported", "manual_edit"):
            raise ValueError("provenance")
        if envelope["import_lineage"] != []:
            _validate_lineage(envelope["import_lineage"])
        validate_evidence_refs(envelope)
    else:
        raise ValueError("schema")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate")
        value[key] = item
    return value


def _reject_json_constant(_constant: str) -> None:
    raise ValueError("nonfinite")


def validate_portable_artifact(raw: bytes) -> dict[str, Any]:
    """Validate a bounded Draft artifact; uploaded identity/history remain untrusted."""
    try:
        if type(raw) is not bytes or not 1 <= len(raw) <= MAX_ARTIFACT_BYTES:
            raise ValueError("size")
        envelope = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
        _envelope_shape(envelope)
        envelope = cast(dict[str, Any], envelope)
        _claim_metadata(envelope)
        parent = envelope["parent_hash"]
        if (envelope["revision"] == 1 and parent is not None) or (
            envelope["revision"] > 1 and not _valid_hash(parent)
        ):
            raise ValueError("parent")
        unsigned = {key: value for key, value in envelope.items() if key != "sha256"}
        if hashlib.sha256(_json(unsigned)).hexdigest() != envelope["sha256"]:
            raise ValueError("checksum")
        content, _findings = validate_payload(envelope["content"])
        if content.model_dump(mode="json") != envelope["content"]:
            raise ValueError("content")
        return envelope
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError, OverflowError) as exc:
        raise DraftScopeError("DRAFT_IMPORT_INVALID") from exc


def _read(db: Session, draft: DraftScope, revision: int) -> dict[str, Any]:
    row = db.scalar(
        select(DraftScopeRevision)
        .where(
            DraftScopeRevision.draft_scope_id == draft.id, DraftScopeRevision.revision == revision
        )
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise DraftScopeError("DRAFT_REVISION_NOT_FOUND", 404)
    try:
        if len(row.envelope_json.encode("utf-8")) > MAX_ARTIFACT_BYTES:
            raise ValueError("oversize")
        envelope = json.loads(row.envelope_json)
        _envelope_shape(envelope)
        envelope = cast(dict[str, Any], envelope)
        digest = envelope.pop("sha256")
        if digest != row.content_hash or hashlib.sha256(_json(envelope)).hexdigest() != digest:
            raise ValueError("hash")
        if (
            envelope["artifact_id"] != draft.id
            or envelope["project_id"] != draft.project_id
            or envelope["revision"] != row.revision
            or envelope["created_by"] != row.created_by_id
            or envelope["parent_hash"] != row.parent_hash
            or envelope["state"] != "Draft"
            or envelope["review_status"] != "unreviewed"
        ):
            raise ValueError("binding")
        row_created = (
            row.created_at.replace(tzinfo=UTC) if row.created_at.tzinfo is None else row.created_at
        )
        if envelope["created_at"] != row_created.astimezone(UTC).isoformat():
            raise ValueError("timestamp")
        if revision == 1:
            if row.parent_hash is not None:
                raise ValueError("parent")
        else:
            parent = db.scalar(
                select(DraftScopeRevision.content_hash).where(
                    DraftScopeRevision.draft_scope_id == draft.id,
                    DraftScopeRevision.revision == revision - 1,
                )
            )
            if parent is None or parent != row.parent_hash:
                raise ValueError("parent")
        content, _ = validate_payload(envelope["content"])
        if content.model_dump(mode="json") != envelope["content"]:
            raise ValueError("content")
        envelope["sha256"] = digest
        if _json(envelope).decode("utf-8") != row.envelope_json:
            raise ValueError("serialization")
        return envelope
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError, OverflowError) as exc:
        raise DraftScopeError("DRAFT_REVISION_INTEGRITY_FAILED", 409) from exc


def read_revision(
    db: Session, actor: User, draft_id: str, revision: int | None = None
) -> dict[str, Any]:
    draft = get_draft(db, actor, draft_id)
    selected = draft.latest_revision if revision is None else revision
    if type(selected) is not int or selected < 1 or selected > draft.latest_revision:
        raise DraftScopeError("DRAFT_REVISION_NOT_FOUND", 404)
    return _read(db, draft, selected)


def revision_bytes(db: Session, actor: User, draft_id: str, revision: int | None = None) -> bytes:
    actor = _actor(db, actor, "project:read")
    envelope = read_revision(db, actor, draft_id, revision)
    record_audit(
        db,
        actor=actor,
        action="draft_scope.download",
        entity_type="draft_scope",
        entity_id=draft_id,
        project_id=envelope["project_id"],
        new_value={"revision": envelope["revision"], "sha256": envelope["sha256"]},
    )
    db.flush()
    return _json(envelope)


def save_revision(
    db: Session, actor: User, draft_id: str, expected_revision: int, payload: dict
) -> dict[str, Any]:
    return _append_revision(db, actor, draft_id, expected_revision, payload)


def _revision_envelope(
    *,
    draft_id: str,
    project_id: str,
    actor_id: str,
    expected_revision: int,
    created: datetime,
    content: dict[str, Any],
    prior: dict[str, Any] | None,
    import_source: dict[str, Any] | None = None,
    source_file_sha256: str | None = None,
    evidence_ref: dict[str, Any] | None = None,
    entity_evidence_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build and validate the exact next envelope without persistence or audit writes."""
    parent = prior["sha256"] if prior else None
    envelope: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": draft_id,
        "project_id": project_id,
        "revision": expected_revision + 1,
        "parent_hash": parent,
        "created_by": actor_id,
        "created_at": created.isoformat(),
        "state": "Draft",
        "provenance": "manual",
        "review_status": "unreviewed",
        "content": content,
    }
    if import_source is not None:
        lineage = list(import_source.get("import_lineage", []))
        lineage.append(
            {key: import_source[key] for key in _LINEAGE_KEYS if key != "file_sha256"}
            | {"file_sha256": source_file_sha256}
        )
        if len(lineage) > MAX_IMPORT_LINEAGE:
            raise DraftScopeError("DRAFT_IMPORT_LINEAGE_LIMIT")
        envelope.update(
            schema_version=IMPORTED_SCHEMA_VERSION,
            provenance="imported",
            import_lineage=lineage,
        )
    elif prior is not None and prior.get("import_lineage"):
        envelope.update(
            schema_version=IMPORTED_SCHEMA_VERSION,
            provenance="manual_edit",
            import_lineage=prior["import_lineage"],
        )
    basis = import_source if import_source is not None else prior
    if (
        evidence_ref is not None
        or entity_evidence_refs is not None
        or (basis and basis["schema_version"] in EVIDENCE_SCHEMAS)
    ):
        observations = {item["id"] for item in envelope["content"]["observations"]}
        refs = [
            dict(ref)
            for ref in (basis or {}).get("evidence_refs", [])
            if "target_kind" in ref or ref["observation_id"] in observations
        ]
        if import_source is not None:
            refs = [dict(ref, origin="imported_unverified") for ref in refs]
        if evidence_ref is not None:
            refs.append(dict(evidence_ref))
        if entity_evidence_refs is not None:
            replacements = {reference_identity(ref) for ref in entity_evidence_refs}
            refs = [ref for ref in refs if reference_identity(ref) not in replacements]
            refs.extend(dict(ref) for ref in entity_evidence_refs)
        entity_version = entity_evidence_refs is not None or (
            basis and basis["schema_version"] == ENTITY_EVIDENCE_SCHEMA_VERSION
        )
        xlsx_version = any(ref.get("source_kind") == "xlsx" for ref in refs) or (
            basis and basis["schema_version"] == XLSX_EVIDENCE_SCHEMA_VERSION
        )
        envelope.update(
            schema_version=XLSX_EVIDENCE_SCHEMA_VERSION
            if xlsx_version
            else ENTITY_EVIDENCE_SCHEMA_VERSION
            if entity_version
            else EVIDENCE_SCHEMA_VERSION,
            provenance="evidence_review"
            if evidence_ref is not None or entity_evidence_refs is not None
            else ("imported" if import_source is not None else "manual_edit"),
            import_lineage=envelope.get("import_lineage", []),
            evidence_refs=refs,
        )
    envelope["sha256"] = hashlib.sha256(_json(envelope)).hexdigest()
    try:
        _envelope_shape(envelope)
    except (ValueError, TypeError, KeyError) as exc:
        raise DraftScopeError("DRAFT_EVIDENCE_INVALID") from exc
    if len(_json(envelope)) > MAX_ARTIFACT_BYTES:
        raise DraftScopeError("DRAFT_ARTIFACT_TOO_LARGE")
    return envelope


def _append_revision(
    db: Session,
    actor: User,
    draft_id: str,
    expected_revision: int,
    payload: dict,
    *,
    import_source: dict[str, Any] | None = None,
    source_file_sha256: str | None = None,
    evidence_ref: dict[str, Any] | None = None,
    entity_evidence_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    actor = _actor(db, actor, "project:write")
    draft = get_draft(db, actor, draft_id)
    if type(expected_revision) is not int or expected_revision < 0:
        raise DraftScopeError("DRAFT_REVISION_CONFLICT", 409)
    content, _ = validate_payload(payload)
    try:
        with _atomic(db):
            changed = db.execute(
                update(DraftScope)
                .where(
                    DraftScope.id == draft.id,
                    DraftScope.latest_revision == expected_revision,
                    DraftScope.owner_user_id == draft.owner_user_id,
                )
                .values(latest_revision=expected_revision + 1)
                .execution_options(synchronize_session=False)
            )
            if changed.rowcount != 1:  # type: ignore[attr-defined]
                raise DraftScopeError("DRAFT_REVISION_CONFLICT", 409)
            prior = _read(db, draft, expected_revision) if expected_revision else None
            parent = prior["sha256"] if prior else None
            created = datetime.now(UTC)
            envelope = _revision_envelope(
                draft_id=draft.id,
                project_id=draft.project_id,
                actor_id=actor.id,
                expected_revision=expected_revision,
                created=created,
                content=content.model_dump(mode="json"),
                prior=prior,
                import_source=import_source,
                source_file_sha256=source_file_sha256,
                evidence_ref=evidence_ref,
                entity_evidence_refs=entity_evidence_refs,
            )
            db.add(
                DraftScopeRevision(
                    draft_scope_id=draft.id,
                    revision=expected_revision + 1,
                    parent_hash=parent,
                    content_hash=envelope["sha256"],
                    envelope_json=_json(envelope).decode("utf-8"),
                    created_by_id=actor.id,
                    created_at=created,
                )
            )
            record_audit(
                db,
                actor=actor,
                action="draft_scope.import" if import_source is not None else "draft_scope.save",
                entity_type="draft_scope",
                entity_id=draft.id,
                project_id=draft.project_id,
                new_value={"revision": expected_revision + 1, "sha256": envelope["sha256"]}
                | (
                    {
                        "source_file_sha256": source_file_sha256,
                        "source_sha256": import_source["sha256"],
                    }
                    if import_source is not None
                    else {}
                ),
                previous_value={"revision": expected_revision, "sha256": parent},
            )
            db.flush()
        db.refresh(draft)
        return envelope
    except IntegrityError as exc:
        raise DraftScopeError("DRAFT_REVISION_CONFLICT", 409) from exc


def _content_counts(content: dict[str, Any]) -> dict[str, int]:
    return {
        name: len(content[name])
        for name in ("defects", "openings", "services", "observations", "assumptions", "exclusions")
    }


def preview_import(db: Session, actor: User, draft_id: str, raw: bytes) -> dict[str, Any]:
    """Preview replacement of content only; no audit or persistence side effects."""
    with db.no_autoflush:
        actor = _actor(db, actor, "project:write")
        current = read_revision(db, actor, draft_id)
        source = validate_portable_artifact(raw)
        if len(source.get("import_lineage", [])) >= MAX_IMPORT_LINEAGE:
            raise DraftScopeError("DRAFT_IMPORT_LINEAGE_LIMIT")
        _content, findings = validate_payload(source["content"])
        findings.append(
            {
                "code": "IMPORT_HISTORY_UNTRUSTED",
                "path": "",
                "severity": "warning",
                "message": (
                    "Imported identities and history are unverified claims; "
                    "local approval is not granted."
                ),
            }
        )
        return {
            "expected_revision": current["revision"],
            "current_hash": current["sha256"],
            "source": source,
            "source_file_sha256": hashlib.sha256(raw).hexdigest(),
            "content": source["content"],
            "findings": findings,
            "before_counts": _content_counts(current["content"]),
            "after_counts": _content_counts(source["content"]),
        }


def apply_import(
    db: Session,
    actor: User,
    draft_id: str,
    expected_revision: int,
    raw: bytes,
    expected_source_hash: str,
) -> dict[str, Any]:
    """Explicit authorized import command; callers bind/confirm their preview separately."""
    actor = _actor(db, actor, "project:write")
    current = read_revision(db, actor, draft_id)
    if type(expected_revision) is not int or expected_revision != current["revision"]:
        raise DraftScopeError("DRAFT_REVISION_CONFLICT", 409)
    source = validate_portable_artifact(raw)
    file_hash = hashlib.sha256(raw).hexdigest()
    if not _valid_hash(expected_source_hash) or file_hash != expected_source_hash:
        raise DraftScopeError("DRAFT_IMPORT_SOURCE_CHANGED", 409)
    if len(source.get("import_lineage", [])) >= MAX_IMPORT_LINEAGE:
        raise DraftScopeError("DRAFT_IMPORT_LINEAGE_LIMIT")
    return _append_revision(
        db,
        actor,
        draft_id,
        expected_revision,
        source["content"],
        import_source=source,
        source_file_sha256=file_hash,
    )
