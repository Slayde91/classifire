"""Independent scope-only Draft reporting from exact retained revisions.

Interfaces share these use cases. No estimation, matching, AI or canonical physical
writer is invoked. Mutating use cases flush; the caller commits its transaction.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, defer

from ..audit import record_audit
from ..models import DraftScope, DraftScopeReport, Project, User, new_id
from .draft_scope import (
    MAX_ARTIFACT_BYTES,
    DraftScopeError,
    _actor,
    _atomic,
    _envelope_shape,
    _valid_hash,
    get_draft,
    read_revision,
    validate_payload,
)

REPORT_SCHEMA_VERSION = "CLASSIFIRE-DRAFT-SCOPE-REPORT-v1"
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
REPORT_LIST_LIMIT = 20
MAX_REPORT_SNAPSHOT_BYTES = MAX_ARTIFACT_BYTES + 8192
REPORT_KEYS = frozenset(
    {
        "schema_version",
        "report_id",
        "project",
        "scope",
        "profile",
        "render_version",
        "created_by",
        "created_at",
        "state",
        "review_status",
        "sha256",
    }
)


class DraftScopeReportError(DraftScopeError):
    """Safe failure code for report interfaces; no scope/provider text is exposed."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _checksum(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        _canonical({key: item for key, item in value.items() if key != "sha256"})
    ).hexdigest()


def _utc_text(value: Any) -> None:
    if type(value) is not str or len(value) > 40:
        raise ValueError("timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.astimezone(UTC).isoformat() != value:
        raise ValueError("timestamp")


def _identity(value: Any) -> None:
    # Existing persisted human/project identifiers need not be newly reissued UUIDs.
    if type(value) is not str or not 1 <= len(value) <= 36:
        raise ValueError("identity")


def validate_report_snapshot(snapshot: dict[str, Any]) -> None:
    """Pure report contract validation, shared with deterministic renderers."""
    try:
        if type(snapshot) is not dict or set(snapshot) != REPORT_KEYS:
            raise ValueError("shape")
        if len(_canonical(snapshot)) > MAX_REPORT_SNAPSHOT_BYTES:
            raise ValueError("size")
        if (
            snapshot["schema_version"] != REPORT_SCHEMA_VERSION
            or snapshot["profile"] != "scope-only"
            or type(snapshot["render_version"]) is not int
            or snapshot["render_version"] != 1
            or snapshot["state"] != "Draft"
            or snapshot["review_status"] != "unreviewed"
        ):
            raise ValueError("authority")
        report_id = snapshot["report_id"]
        if type(report_id) is not str or str(UUID(report_id)) != report_id:
            raise ValueError("identity")
        _identity(snapshot["created_by"])
        _utc_text(snapshot["created_at"])
        project = snapshot["project"]
        if type(project) is not dict or set(project) != {"id", "reference", "name"}:
            raise ValueError("project")
        _identity(project["id"])
        for key, limit in (("reference", 100), ("name", 300)):
            if type(project[key]) is not str or not 1 <= len(project[key]) <= limit:
                raise ValueError("project")
        scope = snapshot["scope"]
        _envelope_shape(scope)
        for key in ("artifact_id", "project_id", "created_by"):
            _identity(scope[key])
        _utc_text(scope["created_at"])
        if (
            scope["project_id"] != project["id"]
            or type(scope["revision"]) is not int
            or scope["revision"] < 1
        ):
            raise ValueError("scope")
        if (scope["revision"] == 1 and scope["parent_hash"] is not None) or (
            scope["revision"] > 1 and not _valid_hash(scope["parent_hash"])
        ):
            raise ValueError("scope")
        content, _findings = validate_payload(scope["content"])
        if content.model_dump(mode="json") != scope["content"]:
            raise ValueError("scope")
        if not _valid_hash(scope["sha256"]) or _checksum(scope) != scope["sha256"]:
            raise ValueError("scope")
        if not _valid_hash(snapshot["sha256"]) or _checksum(snapshot) != snapshot["sha256"]:
            raise ValueError("checksum")
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError, OverflowError) as exc:
        raise DraftScopeReportError("DRAFT_REPORT_SNAPSHOT_INVALID", 422) from exc


def _access(
    db: Session, actor: User, draft_id: str, *, write: bool = False
) -> tuple[User, DraftScope]:
    try:
        actor = _actor(db, actor, "project:write" if write else "project:read")
        return actor, get_draft(db, actor, draft_id)
    except DraftScopeError as exc:
        raise DraftScopeReportError(exc.code, exc.status_code) from exc


def _scope(db: Session, actor: User, draft_id: str, revision: int | None = None) -> dict[str, Any]:
    try:
        return read_revision(db, actor, draft_id, revision)
    except DraftScopeError as exc:
        raise DraftScopeReportError(exc.code, exc.status_code) from exc


def _project(db: Session, draft: DraftScope) -> dict[str, str]:
    project = db.get(Project, draft.project_id, populate_existing=True)
    if project is None:
        raise DraftScopeReportError("DRAFT_REPORT_INTEGRITY_FAILED", 409)
    return {"id": project.id, "reference": project.reference, "name": project.name}


def _output(value: Any, format_name: str) -> bytes:
    if type(value) is not bytes or not 1 <= len(value) <= MAX_OUTPUT_BYTES:
        raise DraftScopeReportError("DRAFT_REPORT_OUTPUT_INVALID", 422)
    prefix = b"%PDF-" if format_name == "pdf" else b"PK\x03\x04"
    if not value.startswith(prefix):
        raise DraftScopeReportError("DRAFT_REPORT_OUTPUT_INVALID", 422)
    return value


def create_report(db: Session, actor: User, draft_id: str, revision: int) -> DraftScopeReport:
    """Capture one explicit saved Scope revision and atomically retain both outputs."""
    from ..outputs.draft_scope import render_scope_report_pdf, render_scope_report_xlsx

    actor, draft = _access(db, actor, draft_id, write=True)
    if type(revision) is not int or revision < 1:
        raise DraftScopeReportError("DRAFT_REVISION_NOT_FOUND", 404)
    scope = _scope(db, actor, draft_id, revision)
    created = datetime.now(UTC)
    snapshot = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_id": new_id(),
        "project": _project(db, draft),
        "scope": scope,
        "profile": "scope-only",
        "render_version": 1,
        "created_by": actor.id,
        "created_at": created.isoformat(),
        "state": "Draft",
        "review_status": "unreviewed",
    }
    snapshot["sha256"] = _checksum(snapshot)
    validate_report_snapshot(snapshot)
    frozen = _canonical(snapshot)
    try:
        pdf_input = json.loads(frozen)
        pdf = _output(render_scope_report_pdf(pdf_input), "pdf")
        if _canonical(pdf_input) != frozen:
            raise DraftScopeReportError("DRAFT_REPORT_RENDER_MUTATED", 422)
        xlsx_input = json.loads(frozen)
        xlsx = _output(render_scope_report_xlsx(xlsx_input), "xlsx")
        if _canonical(xlsx_input) != frozen:
            raise DraftScopeReportError("DRAFT_REPORT_RENDER_MUTATED", 422)
    except DraftScopeReportError:
        raise
    except Exception as exc:
        raise DraftScopeReportError("DRAFT_REPORT_RENDER_FAILED", 422) from exc
    try:
        with _atomic(db):
            actor, draft = _access(db, actor, draft_id, write=True)
            if _scope(db, actor, draft_id, revision) != scope:
                raise DraftScopeReportError("DRAFT_REPORT_SOURCE_CHANGED", 409)
            report = DraftScopeReport(
                id=snapshot["report_id"],
                draft_scope_id=draft.id,
                scope_revision=revision,
                scope_hash=scope["sha256"],
                snapshot_json=frozen.decode("utf-8"),
                snapshot_hash=snapshot["sha256"],
                created_by_id=actor.id,
                created_at=created,
                pdf_bytes=pdf,
                pdf_sha256=hashlib.sha256(pdf).hexdigest(),
                xlsx_bytes=xlsx,
                xlsx_sha256=hashlib.sha256(xlsx).hexdigest(),
            )
            db.add(report)
            record_audit(
                db,
                actor=actor,
                action="draft_scope_report.create",
                entity_type="draft_scope_report",
                entity_id=report.id,
                project_id=draft.project_id,
                new_value={
                    "scope_revision": revision,
                    "scope_sha256": report.scope_hash,
                    "snapshot_sha256": report.snapshot_hash,
                    "pdf_sha256": report.pdf_sha256,
                    "xlsx_sha256": report.xlsx_sha256,
                },
            )
            db.flush()
        return report
    except IntegrityError as exc:
        raise DraftScopeReportError("DRAFT_REPORT_SAVE_CONFLICT", 409) from exc


def _retained(
    db: Session, actor: User, draft_id: str, report_id: str
) -> tuple[DraftScopeReport, dict[str, Any]]:
    actor, draft = _access(db, actor, draft_id)
    row = db.scalar(
        select(DraftScopeReport)
        .options(defer(DraftScopeReport.pdf_bytes), defer(DraftScopeReport.xlsx_bytes))
        .where(
            DraftScopeReport.id == report_id,
            DraftScopeReport.draft_scope_id == draft_id,
        )
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise DraftScopeReportError("DRAFT_REPORT_NOT_FOUND", 404)
    try:
        if len(row.snapshot_json.encode("utf-8")) > MAX_REPORT_SNAPSHOT_BYTES:
            raise ValueError("size")
        snapshot = cast(dict[str, Any], json.loads(row.snapshot_json))
        validate_report_snapshot(snapshot)
        timestamp = (
            row.created_at.replace(tzinfo=UTC) if row.created_at.tzinfo is None else row.created_at
        )
        if (
            snapshot["report_id"] != row.id
            or snapshot["project"]["id"] != draft.project_id
            or snapshot["scope"]["artifact_id"] != draft.id
            or snapshot["scope"]["revision"] != row.scope_revision
            or snapshot["scope"]["sha256"] != row.scope_hash
            or snapshot["created_by"] != row.created_by_id
            or snapshot["created_at"] != timestamp.astimezone(UTC).isoformat()
            or snapshot["sha256"] != row.snapshot_hash
            or _canonical(snapshot).decode("utf-8") != row.snapshot_json
        ):
            raise ValueError("binding")
        if _scope(db, actor, draft_id, row.scope_revision) != snapshot["scope"]:
            raise ValueError("source")
        for format_name in ("pdf", "xlsx"):
            output = _output(getattr(row, format_name + "_bytes"), format_name)
            if hashlib.sha256(output).hexdigest() != getattr(row, format_name + "_sha256"):
                raise ValueError("output")
        return row, snapshot
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError, OverflowError) as exc:
        raise DraftScopeReportError("DRAFT_REPORT_INTEGRITY_FAILED", 409) from exc


def list_reports(db: Session, actor: User, draft_id: str) -> list[DraftScopeReport]:
    actor, _draft = _access(db, actor, draft_id)
    reports = list(
        db.scalars(
            select(DraftScopeReport)
            .options(defer(DraftScopeReport.pdf_bytes), defer(DraftScopeReport.xlsx_bytes))
            .where(
                DraftScopeReport.draft_scope_id == draft_id,
            )
            .order_by(DraftScopeReport.created_at.desc(), DraftScopeReport.id)
            .limit(REPORT_LIST_LIMIT)
        )
    )
    for report in reports:
        _retained(db, actor, draft_id, report.id)
        db.expire(report, ["pdf_bytes", "xlsx_bytes"])
    return reports


def read_report(db: Session, actor: User, draft_id: str, report_id: str) -> dict[str, Any]:
    row, snapshot = _retained(db, actor, draft_id, report_id)
    db.expire(row, ["pdf_bytes", "xlsx_bytes"])
    return snapshot


def report_bytes(
    db: Session, actor: User, draft_id: str, report_id: str, format_name: str
) -> bytes:
    actor, draft = _access(db, actor, draft_id)
    row, _snapshot = _retained(db, actor, draft_id, report_id)
    if format_name not in ("pdf", "xlsx"):
        raise DraftScopeReportError("DRAFT_REPORT_FORMAT_INVALID", 422)
    value = cast(bytes, getattr(row, format_name + "_bytes"))
    record_audit(
        db,
        actor=actor,
        action="draft_scope_report.download",
        entity_type="draft_scope_report",
        entity_id=row.id,
        project_id=draft.project_id,
        new_value={
            "format": format_name,
            "snapshot_sha256": row.snapshot_hash,
            "output_sha256": getattr(row, format_name + "_sha256"),
        },
    )
    db.flush()
    return value


def report_freshness(db: Session, actor: User, draft_id: str, report_id: str) -> bool:
    """True means stale; retained snapshots and outputs are never rewritten."""
    actor, draft = _access(db, actor, draft_id)
    row, snapshot = _retained(db, actor, draft_id, report_id)
    db.expire(row, ["pdf_bytes", "xlsx_bytes"])
    current = _scope(db, actor, draft_id)
    return bool(
        current["revision"] != snapshot["scope"]["revision"]
        or current["sha256"] != snapshot["scope"]["sha256"]
        or _project(db, draft) != snapshot["project"]
    )
