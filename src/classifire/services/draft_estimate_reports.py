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
from ..security import has_permission
from .draft_estimate_contract import MAX_ESTIMATE_BYTES, validate_envelope
from .draft_estimates import _estimate, estimate_staleness, read_estimate_revision
from .draft_scope import DraftScopeError, _actor, _atomic, _valid_hash
from .draft_scope_evidence import (
    ENTITY_EVIDENCE_SCHEMA_VERSION,
    SUGGESTION_EVIDENCE_SCHEMA_VERSION,
    WORD_EVIDENCE_SCHEMA_VERSION,
    XLSX_EVIDENCE_SCHEMA_VERSION,
)
from .draft_scope_reports import (
    _canonical,
    _checksum,
    _identity,
    _output,
    _project,
    _utc_text,
)
from .draft_system_match_contract import MAX_MATCH_BYTES
from .draft_system_match_contract import validate_envelope as validate_match
from .draft_system_matches import match_staleness, read_match_revision

REPORT_SCHEMA_VERSION = "CLASSIFIRE-DRAFT-ESTIMATE-REPORT-v1"
COMPLETE_SCHEMA_VERSION = "CLASSIFIRE-DRAFT-ESTIMATE-REPORT-v2"
MULTI_COMPLETE_SCHEMA_VERSION = "CLASSIFIRE-DRAFT-ESTIMATE-REPORT-v3"
MULTI_COMPLETE_RENDER_VERSION = 12
MAX_REPORT_MATCHES = 30
MAX_COLLECTION_REPORT_SNAPSHOT_BYTES = (
    MAX_ESTIMATE_BYTES + MAX_REPORT_MATCHES * MAX_MATCH_BYTES + 8192
)
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


def _render_version(estimate: dict[str, Any], *, complete: bool) -> int:
    if estimate["scope"].get("schema_version") == WORD_EVIDENCE_SCHEMA_VERSION:
        return 11 if complete else 10
    if estimate["scope"].get("schema_version") == SUGGESTION_EVIDENCE_SCHEMA_VERSION:
        return 9 if complete else 8
    if estimate["scope"].get("schema_version") == XLSX_EVIDENCE_SCHEMA_VERSION:
        return 7 if complete else 6
    if estimate["scope"].get("schema_version") == ENTITY_EVIDENCE_SCHEMA_VERSION:
        return 5 if complete else 4
    return 3 if complete else 2 if estimate.get("pricing_sources") else 1


def report_matches(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Exact report context; the Estimate itself retains its independent dependencies."""
    if snapshot.get("schema_version") == MULTI_COMPLETE_SCHEMA_VERSION:
        return cast(list[dict[str, Any]], snapshot["system_matches"])
    review = snapshot["estimate"].get("system_match")
    return [review] if review is not None else []


def _validate_collection(estimate: dict[str, Any], reviews: Any) -> None:
    from .draft_project_packages import validate_match_collection

    if type(reviews) is not list or not 1 <= len(reviews) <= MAX_REPORT_MATCHES:
        raise ValueError("review collection")
    for review in reviews:
        validate_match(review)
    identities = [review["artifact_id"] for review in reviews]
    if identities != sorted(set(identities)):
        raise ValueError("review order or identity")
    try:
        validate_match_collection(estimate["scope"], reviews)
    except DraftScopeError as exc:
        raise ValueError("review target or Scope") from exc
    if estimate["system_match"] is not None and estimate["system_match"] not in reviews:
        raise ValueError("Estimate review dependency")


def validate_report_snapshot(snapshot: dict[str, Any]) -> None:
    try:
        if type(snapshot) is not dict:
            raise ValueError("shape")
        collection = snapshot.get("schema_version") == MULTI_COMPLETE_SCHEMA_VERSION
        if set(snapshot) != REPORT_KEYS | ({"system_matches"} if collection else set()):
            raise ValueError("shape")
        if len(_canonical(snapshot)) > (
            MAX_COLLECTION_REPORT_SNAPSHOT_BYTES if collection else MAX_REPORT_SNAPSHOT_BYTES
        ):
            raise ValueError("size")
        complete = snapshot["profile"] == "complete"
        if (
            snapshot["profile"] not in REPORT_PROFILES
            or snapshot["schema_version"]
            != (
                MULTI_COMPLETE_SCHEMA_VERSION
                if collection
                else COMPLETE_SCHEMA_VERSION
                if complete
                else REPORT_SCHEMA_VERSION
            )
            or (collection and not complete)
            or type(snapshot["render_version"]) is not int
            or snapshot["render_version"]
            != (
                MULTI_COMPLETE_RENDER_VERSION
                if collection
                else _render_version(snapshot["estimate"], complete=complete)
            )
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
        if collection:
            _validate_collection(snapshot["estimate"], snapshot["system_matches"])
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


def preview_report(
    db: Session,
    actor: User,
    draft_id: str,
    estimate_id: str,
    revision: int,
    *,
    profile: str = "estimate-only",
    matches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Read exact authorized report inputs without calculation, rendering or writes."""
    if type(profile) is not str or profile not in REPORT_PROFILES:
        raise DraftEstimateReportError("ESTIMATE_REPORT_PROFILE_INVALID", 422)
    if matches is not None and type(matches) is not list:
        raise DraftEstimateReportError("ESTIMATE_REPORT_MATCH_SELECTION_INVALID", 422)
    if matches and profile != "complete":
        raise DraftEstimateReportError("ESTIMATE_REPORT_PROFILE_INVALID", 422)
    actor, draft, _parent = _estimate(db, actor, draft_id, estimate_id)
    if type(revision) is not int or revision < 1:
        raise DraftEstimateReportError("ESTIMATE_REVISION_NOT_FOUND", 404)
    envelope = read_estimate_revision(db, actor, draft_id, estimate_id, revision)
    reviews = []
    if matches:
        from .draft_project_packages import selection, validate_match_collection

        selected = selection({"scope_revision": envelope["scope"]["revision"], "matches": matches})
        reviews = [
            read_match_revision(db, actor, draft_id, item.match_id, item.match_revision)
            for item in selected.matches
        ]
        validate_match_collection(envelope["scope"], reviews)
        if envelope["system_match"] is not None and envelope["system_match"] not in reviews:
            raise DraftEstimateReportError("ESTIMATE_REPORT_MATCH_DEPENDENCY_REQUIRED", 409)
    elif envelope["system_match"] is not None:
        reviews = [envelope["system_match"]]
    return {
        "estimate": envelope,
        "project": _project(db, draft),
        "system_matches": reviews,
        "profile": profile,
        "render_version": MULTI_COMPLETE_RENDER_VERSION
        if matches
        else _render_version(envelope, complete=profile == "complete"),
    }


def create_report(
    db: Session,
    actor: User,
    draft_id: str,
    estimate_id: str,
    revision: int,
    *,
    profile: str = "estimate-only",
    matches: list[dict[str, Any]] | None = None,
) -> DraftEstimateReport:
    """Render one explicit revision, then retain both outputs in one transaction."""
    from ..outputs.draft_estimate import render_estimate_report_pdf, render_estimate_report_xlsx

    actor, draft, _parent = _estimate(db, actor, draft_id, estimate_id, write=True)
    inputs = preview_report(
        db, actor, draft_id, estimate_id, revision, profile=profile, matches=matches
    )
    envelope = inputs["estimate"]
    reviews = inputs["system_matches"] if matches else []
    created = datetime.now(UTC)
    snapshot = {
        "schema_version": MULTI_COMPLETE_SCHEMA_VERSION
        if matches
        else COMPLETE_SCHEMA_VERSION
        if profile == "complete"
        else REPORT_SCHEMA_VERSION,
        "report_id": new_id(),
        "project": inputs["project"],
        "estimate": envelope,
        "profile": profile,
        "render_version": inputs["render_version"],
        "created_by": actor.id,
        "created_at": created.isoformat(),
        "state": "Draft",
        "review_status": "unreviewed",
    }
    if matches:
        snapshot["system_matches"] = reviews
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
            for review in reviews:
                if (
                    read_match_revision(
                        db, actor, draft_id, review["artifact_id"], review["revision"]
                    )
                    != review
                ):
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
        if len(row.snapshot_json.encode("utf-8")) > MAX_COLLECTION_REPORT_SNAPSHOT_BYTES:
            raise ValueError("size")
        snapshot = cast(dict[str, Any], json.loads(row.snapshot_json))
        if (
            isinstance(snapshot, dict)
            and snapshot.get("schema_version") == MULTI_COMPLETE_SCHEMA_VERSION
        ):
            actor = _actor(db, actor, "technical:read")
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
        if snapshot["schema_version"] == MULTI_COMPLETE_SCHEMA_VERSION:
            for review in report_matches(snapshot):
                if (
                    read_match_revision(
                        db, actor, draft_id, review["artifact_id"], review["revision"]
                    )
                    != review
                ):
                    raise ValueError("review binding")
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
    if snapshot["schema_version"] == MULTI_COMPLETE_SCHEMA_VERSION:
        _actor(db, actor, "technical:read")
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
    visible = []
    for row in rows:
        if not has_permission(actor, "technical:read"):
            try:
                if len(row.snapshot_json.encode("utf-8")) > MAX_COLLECTION_REPORT_SNAPSHOT_BYTES:
                    raise ValueError("size")
                if (
                    json.loads(row.snapshot_json).get("schema_version")
                    == MULTI_COMPLETE_SCHEMA_VERSION
                ):
                    continue
            except (ValueError, TypeError, AttributeError, RecursionError, UnicodeError) as exc:
                raise DraftEstimateReportError("ESTIMATE_REPORT_INTEGRITY_FAILED", 409) from exc
        _retained(db, actor, draft_id, estimate_id, row.id)
        visible.append(row)
        db.expire(row, ["pdf_bytes", "xlsx_bytes"])
    return visible


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
    if snapshot["schema_version"] == MULTI_COMPLETE_SCHEMA_VERSION:
        for review in report_matches(snapshot):
            latest_review = read_match_revision(db, actor, draft_id, review["artifact_id"])
            if latest_review["sha256"] != review["sha256"]:
                reasons.append("REPORT_REVIEW_CHANGED")
            reasons.extend(
                match_staleness(
                    db,
                    actor,
                    draft_id,
                    review["artifact_id"],
                    review["revision"],
                    storage_root=storage_root,
                )
            )
    latest = read_estimate_revision(db, actor, draft_id, estimate_id)
    if latest["sha256"] != snapshot["estimate"]["sha256"]:
        reasons.append("REPORT_ESTIMATE_CHANGED")
    actor, draft, _parent = _estimate(db, actor, draft_id, estimate_id)
    if _project(db, draft) != snapshot["project"]:
        reasons.append("REPORT_PROJECT_CHANGED")
    return (
        list(dict.fromkeys(reasons))
        if snapshot["schema_version"] == MULTI_COMPLETE_SCHEMA_VERSION
        else reasons
    )
