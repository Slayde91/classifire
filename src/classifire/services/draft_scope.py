"""Deterministic, manual-only Draft Scope use cases shared by all interfaces.

Callers own their transaction. These use cases flush but never commit, invoke AI,
recalculate estimates, or write canonical defects, services, openings or locks.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import DraftScope, DraftScopeRevision, Project, User, new_id
from ..security import has_permission

MAX_PAYLOAD_BYTES = 256 * 1024
SCHEMA_VERSION = "CLASSIFIRE-DRAFT-SCOPE-v1"
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
        "MANUAL_UNREVIEWED", "", "Manual Draft only; no source evidence or approval is established."
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
        if len(row.envelope_json.encode("utf-8")) > MAX_PAYLOAD_BYTES + 4096:
            raise ValueError("oversize")
        envelope = json.loads(row.envelope_json)
        expected_keys = {
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
        if not isinstance(envelope, dict) or set(envelope) != expected_keys:
            raise ValueError("shape")
        digest = envelope.pop("sha256")
        if digest != row.content_hash or hashlib.sha256(_json(envelope)).hexdigest() != digest:
            raise ValueError("hash")
        if (
            envelope["schema_version"] != SCHEMA_VERSION
            or envelope["artifact_id"] != draft.id
            or envelope["project_id"] != draft.project_id
            or envelope["revision"] != row.revision
            or envelope["created_by"] != row.created_by_id
            or envelope["parent_hash"] != row.parent_hash
            or envelope["state"] != "Draft"
            or envelope["provenance"] != "manual"
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
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError) as exc:
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
            parent = _read(db, draft, expected_revision)["sha256"] if expected_revision else None
            created = datetime.now(UTC)
            envelope = {
                "schema_version": SCHEMA_VERSION,
                "artifact_id": draft.id,
                "project_id": draft.project_id,
                "revision": expected_revision + 1,
                "parent_hash": parent,
                "created_by": actor.id,
                "created_at": created.isoformat(),
                "state": "Draft",
                "provenance": "manual",
                "review_status": "unreviewed",
                "content": content.model_dump(mode="json"),
            }
            envelope["sha256"] = hashlib.sha256(_json(envelope)).hexdigest()
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
                action="draft_scope.save",
                entity_type="draft_scope",
                entity_id=draft.id,
                project_id=draft.project_id,
                new_value={"revision": expected_revision + 1, "sha256": envelope["sha256"]},
                previous_value={"revision": expected_revision, "sha256": parent},
            )
            db.flush()
        db.refresh(draft)
        return envelope
    except IntegrityError as exc:
        raise DraftScopeError("DRAFT_REVISION_CONFLICT", 409) from exc
