"""Independent Draft report profiles over exact saved inputs; no upstream writer runs."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, defer

from ..audit import record_audit
from ..models import DraftEstimateReport, User, new_id
from .draft_estimate_contract import MAX_ESTIMATE_BYTES, validate_envelope
from .draft_estimates import _estimate, estimate_staleness, read_estimate_revision
from .draft_scope import DraftScopeError, _atomic, _valid_hash
from .draft_scope_reports import (
    _canonical,
    _checksum,
    _identity,
    _output,
    _project,
    _utc_text,
)

REPORT_SCHEMA_VERSION = "CLASSIFIRE-DRAFT-ESTIMATE-REPORT-v1"
COMPLETE_SCHEMA_VERSION = "CLASSIFIRE-DRAFT-ESTIMATE-REPORT-v2"
REPORT_PROFILES = ("estimate-only", "complete")
MAX_REPORT_SNAPSHOT_BYTES = MAX_ESTIMATE_BYTES + 8192
REPORT_LIST_LIMIT = 20
REPORT_KEYS = frozenset(
    {
        "schema_version",
        "report_id",
        "project",
        "estimate",
        "profile",
        "render_version",
        "created_by",
        "created_at",
        "state",
        "review_status",
        "sha256",
    }
)


class DraftEstimateReportError(DraftScopeError):
    """Safe code only; report text, prices and customer data never enter errors."""


def validate_report_snapshot(snapshot: dict[str, Any]) -> None:
    try:
        if type(snapshot) is not dict or set(snapshot) != REPORT_KEYS:
            raise ValueError("shape")
        if len(_canonical(snapshot)) > MAX_REPORT_SNAPSHOT_BYTES:
            raise ValueError("size")
        complete = snapshot["profile"] == "complete"
        if (
            snapshot["profile"] not in REPORT_PROFILES
            or snapshot["schema_version"]
            != (COMPLETE_SCHEMA_VERSION if complete else REPORT_SCHEMA_VERSION)
            or type(snapshot["render_version"]) is not int
            or snapshot["render_version"]
            != (3 if complete else 2 if snapshot["estimate"].get("pricing_sources") else 1)
            or snapshot["state"] != "Draft"
            or snapshot["review_status"] != "unreviewed"
        ):
            raise ValueError("authority")
        if (
            type(snapshot["report_id"]) is not str
            or str(UUID(snapshot["report_id"])) != (snapshot["report_id"])
        ):
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
        validate_envelope(snapshot["estimate"])
        if snapshot["estimate"]["project_id"] != project["id"]:
            raise ValueError("project")
        if not _valid_hash(snapshot["sha256"]) or _checksum(snapshot) != snapshot["sha256"]:
            raise ValueError("checksum")
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        RecursionError,
        ArithmeticError,
        UnicodeError,
    ) as exc:
        raise DraftEstimateReportError("ESTIMATE_REPORT_SNAPSHOT_INVALID", 422) from exc


def create_report(
    db: Session,
    actor: User,
    draft_id: str,
    estimate_id: str,
    revision: int,
    *,
    profile: str = "estimate-only",
) -> DraftEstimateReport:
    """Render one explicit revision, then retain both outputs in one transaction."""
    from ..outputs.draft_estimate import render_estimate_report_pdf, render_estimate_report_xlsx

    if type(profile) is not str or profile not in REPORT_PROFILES:
        raise DraftEstimateReportError("ESTIMATE_REPORT_PROFILE_INVALID", 422)
    complete = profile == "complete"
    actor, draft, _parent = _estimate(db, actor, draft_id, estimate_id, write=True)
    if type(revision) is not int or revision < 1:
        raise DraftEstimateReportError("ESTIMATE_REVISION_NOT_FOUND", 404)
    envelope = read_estimate_revision(db, actor, draft_id, estimate_id, revision)
    created = datetime.now(UTC)
    snapshot = {
        "schema_version": COMPLETE_SCHEMA_VERSION if complete else REPORT_SCHEMA_VERSION,
        "report_id": new_id(),
        "project": _project(db, draft),
        "estimate": envelope,
        "profile": profile,
        "render_version": 3 if complete else 2 if envelope.get("pricing_sources") else 1,
        "created_by": actor.id,
        "created_at": created.isoformat(),
        "state": "Draft",
        "review_status": "unreviewed",
    }
    snapshot["sha256"] = _checksum(snapshot)
    validate_report_snapshot(snapshot)
    frozen = _canonical(snapshot)
    outputs = {}
    try:
        for name, render in (
            ("pdf", render_estimate_report_pdf),
            ("xlsx", render_estimate_report_xlsx),
        ):
            source = json.loads(frozen)
            outputs[name] = _output(render(source), name)
            if _canonical(source) != frozen:
                raise DraftEstimateReportError("ESTIMATE_REPORT_RENDER_MUTATED", 422)
    except DraftEstimateReportError:
        raise
    except Exception as exc:
        raise DraftEstimateReportError("ESTIMATE_REPORT_RENDER_FAILED", 422) from exc
    try:
        with _atomic(db):
            actor, draft, _parent = _estimate(db, actor, draft_id, estimate_id, write=True)
            if read_estimate_revision(db, actor, draft_id, estimate_id, revision) != envelope:
                raise DraftEstimateReportError("ESTIMATE_REPORT_SOURCE_CHANGED", 409)
            if _project(db, draft) != snapshot["project"]:
                raise DraftEstimateReportError("ESTIMATE_REPORT_PROJECT_CHANGED", 409)
            row = DraftEstimateReport(
                id=snapshot["report_id"],
                draft_scope_id=draft_id,
                estimate_id=estimate_id,
                estimate_revision=revision,
                estimate_hash=envelope["sha256"],
                snapshot_json=frozen.decode("utf-8"),
                snapshot_hash=snapshot["sha256"],
                created_by_id=actor.id,
                created_at=created,
                pdf_bytes=outputs["pdf"],
                pdf_sha256=hashlib.sha256(outputs["pdf"]).hexdigest(),
                xlsx_bytes=outputs["xlsx"],
                xlsx_sha256=hashlib.sha256(outputs["xlsx"]).hexdigest(),
            )
            db.add(row)
            record_audit(
                db,
                actor=actor,
                action="draft_estimate_report.create",
                entity_type="draft_estimate_report",
                entity_id=row.id,
                project_id=draft.project_id,
                new_value={
                    "estimate_id": estimate_id,
                    "estimate_revision": revision,
                    "snapshot_sha256": row.snapshot_hash,
                    "pdf_sha256": row.pdf_sha256,
                    "xlsx_sha256": row.xlsx_sha256,
                },
            )
            db.flush()
        return row
    except IntegrityError as exc:
        raise DraftEstimateReportError("ESTIMATE_REPORT_SAVE_CONFLICT", 409) from exc


def _retained(
    db: Session,
    actor: User,
    draft_id: str,
    estimate_id: str,
    report_id: str,
    *,
    export: bool = False,
) -> tuple[DraftEstimateReport, dict[str, Any]]:
    actor, draft, _parent = _estimate(db, actor, draft_id, estimate_id, export=export)
    row = db.scalar(
        select(DraftEstimateReport)
        .options(defer(DraftEstimateReport.pdf_bytes), defer(DraftEstimateReport.xlsx_bytes))
        .where(
            DraftEstimateReport.id == report_id,
            DraftEstimateReport.draft_scope_id == draft_id,
            DraftEstimateReport.estimate_id == estimate_id,
        )
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise DraftEstimateReportError("ESTIMATE_REPORT_NOT_FOUND", 404)
    try:
        if len(row.snapshot_json.encode("utf-8")) > MAX_REPORT_SNAPSHOT_BYTES:
            raise ValueError("size")
        snapshot = cast(dict[str, Any], json.loads(row.snapshot_json))
        validate_report_snapshot(snapshot)
        timestamp = row.created_at
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        if (
            snapshot["report_id"] != row.id
            or snapshot["project"]["id"] != draft.project_id
            or snapshot["estimate"]["artifact_id"] != estimate_id
            or snapshot["estimate"]["revision"] != row.estimate_revision
            or snapshot["estimate"]["sha256"] != row.estimate_hash
            or snapshot["created_by"] != row.created_by_id
            or snapshot["created_at"] != timestamp.astimezone(UTC).isoformat()
            or snapshot["sha256"] != row.snapshot_hash
            or _canonical(snapshot).decode("utf-8") != row.snapshot_json
            or read_estimate_revision(db, actor, draft_id, estimate_id, row.estimate_revision)
            != snapshot["estimate"]
        ):
            raise ValueError("binding")
        for name in ("pdf", "xlsx"):
            content = _output(getattr(row, name + "_bytes"), name)
            if hashlib.sha256(content).hexdigest() != getattr(row, name + "_sha256"):
                raise ValueError("output")
    except DraftScopeError as exc:
        if exc.status_code == 403:
            raise
        raise DraftEstimateReportError("ESTIMATE_REPORT_INTEGRITY_FAILED", 409) from exc
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError, OverflowError) as exc:
        raise DraftEstimateReportError("ESTIMATE_REPORT_INTEGRITY_FAILED", 409) from exc
    _estimate(db, actor, draft_id, estimate_id, export=export)
    return row, snapshot


def list_reports(
    db: Session, actor: User, draft_id: str, estimate_id: str
) -> list[DraftEstimateReport]:
    actor, _draft, _parent = _estimate(db, actor, draft_id, estimate_id)
    rows = list(
        db.scalars(
            select(DraftEstimateReport)
            .options(defer(DraftEstimateReport.pdf_bytes), defer(DraftEstimateReport.xlsx_bytes))
            .where(
                DraftEstimateReport.draft_scope_id == draft_id,
                DraftEstimateReport.estimate_id == estimate_id,
            )
            .order_by(DraftEstimateReport.created_at.desc(), DraftEstimateReport.id)
            .limit(REPORT_LIST_LIMIT)
        )
    )
    for row in rows:
        _retained(db, actor, draft_id, estimate_id, row.id)
        db.expire(row, ["pdf_bytes", "xlsx_bytes"])
    return rows


def read_report(
    db: Session,
    actor: User,
    draft_id: str,
    estimate_id: str,
    report_id: str,
) -> dict[str, Any]:
    row, snapshot = _retained(db, actor, draft_id, estimate_id, report_id)
    db.expire(row, ["pdf_bytes", "xlsx_bytes"])
    return snapshot


def report_bytes(
    db: Session,
    actor: User,
    draft_id: str,
    estimate_id: str,
    report_id: str,
    format_name: str,
) -> bytes:
    if format_name not in ("pdf", "xlsx"):
        raise DraftEstimateReportError("ESTIMATE_REPORT_FORMAT_INVALID", 422)
    row, snapshot = _retained(db, actor, draft_id, estimate_id, report_id, export=True)
    value = cast(bytes, getattr(row, format_name + "_bytes"))
    actor, draft, _parent = _estimate(db, actor, draft_id, estimate_id, export=True)
    record_audit(
        db,
        actor=actor,
        action="draft_estimate_report.download",
        entity_type="draft_estimate_report",
        entity_id=row.id,
        project_id=draft.project_id,
        new_value={
            "format": format_name,
            "snapshot_sha256": snapshot["sha256"],
            "output_sha256": getattr(row, format_name + "_sha256"),
        },
    )
    db.flush()
    return value


def report_staleness(
    db: Session,
    actor: User,
    draft_id: str,
    estimate_id: str,
    report_id: str,
    *,
    storage_root: Path,
) -> list[str]:
    row, snapshot = _retained(db, actor, draft_id, estimate_id, report_id)
    db.expire(row, ["pdf_bytes", "xlsx_bytes"])
    reasons = estimate_staleness(
        db,
        actor,
        draft_id,
        estimate_id,
        snapshot["estimate"]["revision"],
        storage_root=storage_root,
    )
    latest = read_estimate_revision(db, actor, draft_id, estimate_id)
    if latest["sha256"] != snapshot["estimate"]["sha256"]:
        reasons.append("REPORT_ESTIMATE_CHANGED")
    actor, draft, _parent = _estimate(db, actor, draft_id, estimate_id)
    if _project(db, draft) != snapshot["project"]:
        reasons.append("REPORT_PROJECT_CHANGED")
    return reasons
