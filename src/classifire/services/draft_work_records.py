"""Attributed Draft work assertions over saved Scope/evidence, with no downstream work."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..config import Settings
from ..models import DraftScope, DraftScopeRevision, DraftWorkRecord, DraftWorkRecordRevision, User
from .draft_register import evidence_context
from .draft_scope import DraftScopeError, _actor, _atomic, _json, get_draft, read_revision

SCHEMA = "CLASSIFIRE-DRAFT-WORK-RECORD-v1"
NOTICE = (
    "Reported work, unverified. This is not inspection acceptance, "
    "compliance certification or Human Release."
)


class WorkInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    record_id: Annotated[UUID, Field(strict=False)]
    expected_revision: Annotated[int, Field(ge=0, le=2147483646)]
    scope_revision: Annotated[int, Field(ge=1, le=2147483647)]
    opening_id: Annotated[UUID, Field(strict=False)] | None = None
    service_id: Annotated[UUID, Field(strict=False)] | None = None
    note: Annotated[str, Field(min_length=1, max_length=4000)]
    reported_by: Annotated[str, Field(max_length=200)] = ""
    reported_role: Literal["unknown", "installer", "observer", "other"] = "unknown"
    observed_at: Annotated[str, Field(max_length=40)] = ""
    unknowns: Annotated[str, Field(max_length=4000)] = ""
    evidence_indices: Annotated[list[int], Field(max_length=30)] = Field(default_factory=list)

    @field_validator("observed_at")
    @classmethod
    def timestamp(cls, value: str) -> str:
        if not value:
            return value
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("Observation time needs an explicit timezone")
        return parsed.astimezone(UTC).isoformat()

    @field_validator("evidence_indices")
    @classmethod
    def indices(cls, value: list[int]) -> list[int]:
        if any(i < 0 for i in value) or len(set(value)) != len(value):
            raise ValueError("Select distinct saved evidence references")
        return sorted(value)


def _parse(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        if len(_json(payload)) > 20000:
            raise ValueError("size")
        return WorkInput.model_validate(payload).model_dump(mode="json")
    except (ValidationError, ValueError, TypeError) as exc:
        raise DraftScopeError("WORK_RECORD_INPUT_INVALID", 422) from exc


def _hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def _row(db: Session, draft_id: str, record_id: str) -> DraftWorkRecord:
    row = db.get(DraftWorkRecord, record_id, populate_existing=True)
    if row is None or row.draft_scope_id != draft_id:
        raise DraftScopeError("WORK_RECORD_NOT_FOUND", 404)
    return row


def _read(db: Session, draft_id: str, record_id: str, revision: int) -> dict[str, Any]:
    row = _row(db, draft_id, record_id)
    if type(revision) is not int or revision < 1 or revision > row.latest_revision:
        raise DraftScopeError("WORK_RECORD_NOT_FOUND", 404)
    saved = db.scalar(
        select(DraftWorkRecordRevision).where(
            DraftWorkRecordRevision.work_record_id == record_id,
            DraftWorkRecordRevision.revision == revision,
        )
    )
    if saved is None:
        raise DraftScopeError("WORK_RECORD_NOT_FOUND", 404)
    try:
        envelope = json.loads(saved.envelope_json)
        checksum = envelope.pop("sha256")
        valid = (
            _hash(envelope) == checksum == saved.content_hash
            and envelope["schema_version"] == SCHEMA
            and envelope["state"] == "Draft"
            and envelope["review_status"] == "unverified"
            and envelope["record_id"] == record_id
            and envelope["draft_scope_id"] == draft_id
            and envelope["revision"] == revision
            and envelope["parent_hash"] == saved.parent_hash
            and envelope["recorded_by"] == saved.created_by_id
            and envelope["scope_revision_id"] == saved.scope_revision_id
        )
        envelope["sha256"] = checksum
        if not valid or _json(envelope).decode("utf-8") != saved.envelope_json:
            raise ValueError("binding")
        return cast(dict[str, Any], envelope)
    except (ValueError, KeyError, TypeError) as exc:
        raise DraftScopeError("WORK_RECORD_INTEGRITY_FAILED", 409) from exc


def choices(
    db: Session, actor: User, draft_id: str, payload: dict[str, Any], *, settings: Settings
) -> dict[str, Any]:
    """Read an explicit saved target through existing permission and scan checks."""
    return evidence_context(
        db,
        actor,
        draft_id,
        payload["scope_revision"],
        payload.get("opening_id"),
        payload.get("service_id"),
        settings=settings,
    )


def _dependencies(
    db: Session, actor: User, draft_id: str, content: dict[str, Any], settings: Settings
) -> dict[str, Any]:
    context = choices(db, actor, draft_id, content, settings=settings)
    available = {item["index"]: item for item in context["refs"]}
    selected = []
    scope = read_revision(db, actor, draft_id, content["scope_revision"])
    for index in content["evidence_indices"]:
        item = available.get(index)
        if item is None or item["availability"] != "verified" or item["claim_changed"]:
            raise DraftScopeError("WORK_RECORD_EVIDENCE_UNAVAILABLE", 409)
        selected.append({"index": index, "reference": scope["evidence_refs"][index]})
    selection = context["selection"]
    targets = {
        name: [item for item in scope["content"][name] if item["id"] == selection[key]]
        for name, key in (
            ("defects", "defect_id"),
            ("openings", "opening_id"),
            ("services", "service_id"),
        )
    }
    return {
        "scope_sha256": scope["sha256"],
        "selection": selection,
        "targets": targets,
        "evidence": selected,
    }


def preview(
    db: Session, actor: User, draft_id: str, payload: dict[str, Any], *, settings: Settings
) -> dict[str, Any]:
    """No writes; the exact preview hash must be separately confirmed."""
    with db.no_autoflush:
        actor = _actor(db, actor, "project:write")
        draft = get_draft(db, actor, draft_id)
        content = _parse(payload)
        if draft.latest_revision != content["scope_revision"]:
            raise DraftScopeError("WORK_RECORD_SCOPE_STALE", 409)
        parent = None
        existing = db.get(DraftWorkRecord, content["record_id"], populate_existing=True)
        if content["expected_revision"]:
            existing = _row(db, draft_id, content["record_id"])
            if existing.latest_revision != content["expected_revision"]:
                raise DraftScopeError("WORK_RECORD_REVISION_CONFLICT", 409)
            prior = _read(db, draft_id, existing.id, existing.latest_revision)
            if any(prior["content"][key] != content[key] for key in ("opening_id", "service_id")):
                raise DraftScopeError("WORK_RECORD_TARGET_CHANGED", 409)
            parent = prior["sha256"]
        elif existing is not None:
            raise DraftScopeError("WORK_RECORD_REVISION_CONFLICT", 409)
        value = {
            "draft_scope_id": draft_id,
            "actor_id": actor.id,
            "content": content,
            "parent_hash": parent,
            "dependencies": _dependencies(db, actor, draft_id, content, settings),
        }
        if len(_json(value)) > 240000:
            raise DraftScopeError("WORK_RECORD_TOO_LARGE", 422)
        return value | {"sha256": _hash(value)}


def save(
    db: Session,
    actor: User,
    draft_id: str,
    payload: dict[str, Any],
    expected_hash: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    """Append one reviewed assertion. Caller commits; replay is a conflict."""
    try:
        with _atomic(db):
            draft = get_draft(db, actor, draft_id)
            db.scalar(
                select(DraftScope)
                .where(DraftScope.id == draft_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            proposed = preview(db, actor, draft_id, payload, settings=settings)
            if proposed["sha256"] != expected_hash:
                raise DraftScopeError("WORK_RECORD_PREVIEW_CHANGED", 409)
            content = proposed["content"]
            identity, previous = content["record_id"], content["expected_revision"]
            if previous:
                changed = db.execute(
                    update(DraftWorkRecord)
                    .where(
                        DraftWorkRecord.id == identity,
                        DraftWorkRecord.draft_scope_id == draft_id,
                        DraftWorkRecord.latest_revision == previous,
                    )
                    .values(latest_revision=previous + 1)
                    .execution_options(synchronize_session=False)
                )
                if changed.rowcount != 1:  # type: ignore[attr-defined]
                    raise DraftScopeError("WORK_RECORD_REVISION_CONFLICT", 409)
            else:
                db.add(DraftWorkRecord(id=identity, draft_scope_id=draft_id, latest_revision=1))
                db.flush()
            scope_row = db.scalar(
                select(DraftScopeRevision).where(
                    DraftScopeRevision.draft_scope_id == draft_id,
                    DraftScopeRevision.revision == content["scope_revision"],
                )
            )
            if scope_row is None:
                raise DraftScopeError("WORK_RECORD_SCOPE_STALE", 409)
            value = {
                "schema_version": SCHEMA,
                "state": "Draft",
                "review_status": "unverified",
                "notice": NOTICE,
                "record_id": identity,
                "draft_scope_id": draft_id,
                "project_id": draft.project_id,
                "revision": previous + 1,
                "recorded_by": actor.id,
                "recorded_at": datetime.now(UTC).isoformat(),
                "scope_revision_id": scope_row.id,
                "parent_hash": proposed["parent_hash"],
                "content": content,
                "dependencies": proposed["dependencies"],
            }
            value["sha256"] = _hash(value)
            db.add(
                DraftWorkRecordRevision(
                    work_record_id=identity,
                    scope_revision_id=scope_row.id,
                    revision=previous + 1,
                    parent_hash=value["parent_hash"],
                    content_hash=value["sha256"],
                    envelope_json=_json(value).decode("utf-8"),
                    created_by_id=actor.id,
                )
            )
            record_audit(
                db,
                actor=actor,
                action="draft_work_record.save",
                entity_type="draft_work_record",
                entity_id=identity,
                project_id=draft.project_id,
                new_value={"revision": previous + 1, "sha256": value["sha256"]},
            )
            db.flush()
            return value
    except IntegrityError as exc:
        raise DraftScopeError("WORK_RECORD_REVISION_CONFLICT", 409) from exc


def history(db: Session, actor: User, draft_id: str) -> list[dict[str, Any]]:
    get_draft(db, actor, draft_id)
    rows = db.scalars(
        select(DraftWorkRecordRevision)
        .join(DraftWorkRecord)
        .where(
            DraftWorkRecord.draft_scope_id == draft_id,
        )
        .order_by(DraftWorkRecordRevision.created_at.desc(), DraftWorkRecordRevision.id.desc())
        .limit(200)
    )
    return [
        {"record_id": row.work_record_id, "revision": row.revision, "recorded_at": row.created_at}
        for row in rows
    ]


def read(
    db: Session, actor: User, draft_id: str, record_id: str, revision: int, *, settings: Settings
) -> dict[str, Any]:
    draft = get_draft(db, actor, draft_id)
    value = _read(db, draft_id, record_id, revision)
    deps = _dependencies(db, actor, draft_id, value["content"], settings)
    if deps != value["dependencies"]:
        raise DraftScopeError("WORK_RECORD_DEPENDENCY_CHANGED", 409)
    return {
        "record": value,
        "stale": draft.latest_revision != value["content"]["scope_revision"],
        "latest_revision": _row(db, draft_id, record_id).latest_revision,
    }


def report_archive(
    db: Session,
    actor: User,
    draft_id: str,
    record_id: str,
    revision: int,
    *,
    settings: Settings,
) -> bytes:
    """Explicit saved-revision export with byte-exact originals; no matching/costing."""
    from . import draft_pdf_intake, draft_scope_docx, draft_scope_xlsx

    result = read(db, actor, draft_id, record_id, revision, settings=settings)
    if result["stale"]:
        raise DraftScopeError("WORK_RECORD_SCOPE_STALE", 409)
    value = result["record"]
    from ..outputs.draft_work_records import render_work_report

    members = {"work-record.json": _json(value), "report.html": render_work_report(value)}
    for item in value["dependencies"]["evidence"]:
        ref = item["reference"]
        kind = ref.get("source_kind", "pdf")
        name = f"evidence/{ref['source_id']}.{kind}"
        if name in members:
            continue
        intake = {
            "pdf": draft_pdf_intake._intake,
            "docx": draft_scope_docx.intake,
            "xlsx": draft_scope_xlsx.intake,
        }[kind]()
        _, _, content = intake._document(
            db, actor, draft_id, ref["source_id"], settings.storage_root
        )
        if content.sha256 != ref["source_sha256"] or content.size_bytes != ref["source_size_bytes"]:
            raise DraftScopeError("WORK_RECORD_DEPENDENCY_CHANGED", 409)
        if sum(map(len, members.values())) + content.size_bytes > 100 * 1024 * 1024:
            raise DraftScopeError("WORK_RECORD_EXPORT_TOO_LARGE", 422)
        members[name] = content.content
    if sum(map(len, members.values())) > 100 * 1024 * 1024:
        raise DraftScopeError("WORK_RECORD_EXPORT_TOO_LARGE", 422)
    members["manifest.json"] = _json(
        {
            "schema_version": SCHEMA,
            "notice": NOTICE,
            "members": {
                name: {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}
                for name, raw in members.items()
            },
            "exclusions": [
                "Unselected evidence",
                "Inspection acceptance",
                "Technical approval",
                "Prices",
                "Human Release",
            ],
        }
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(members.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, raw)
    get_draft(db, actor, draft_id)
    return buffer.getvalue()
