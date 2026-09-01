"""Retain and verify human-approved expected report Defect-label manifests.

This module records a small evidence-governance decision only. It does not
create Defects, physical-model records, locks, technical selections, pricing,
or releases, and it never commits a caller-owned transaction.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import NoReturn

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import (
    Estimate,
    ProjectEvidence,
    ReportExpectedLabelManifest,
    User,
    now_utc,
)

REPORT_EXPECTED_LABEL_APPROVAL_SCHEMA = "CLASSIFIRE-REPORT-EXPECTED-LABEL-APPROVAL-v1"

_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAXIMUM_EXPECTED_LABELS = 50_000


class ReportExpectedLabelManifestError(ValueError):
    """Stable, content-safe failure while retaining approved report labels."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ApprovedReportExpectedLabelManifest:
    """The verified, immutable approval binding safe for proposal-only use."""

    id: str
    project_evidence_id: str
    source_sha256: str
    estimate_id: str
    expected_report_defect_labels: tuple[str, ...]
    manifest_sha256: str
    approval_reference: str
    approved_by_user_id: str
    approved_at: datetime


def _fail(code: str) -> NoReturn:
    raise ReportExpectedLabelManifestError(code)


def _required_id(value: object, *, code: str) -> str:
    if not isinstance(value, str):
        _fail(code)
    identifier = value.strip()
    if not identifier or len(identifier) > 36:
        _fail(code)
    return identifier


def _required_text(value: object, *, code: str, maximum: int) -> str:
    if not isinstance(value, str):
        _fail(code)
    text = value.strip()
    if not text or len(text) > maximum:
        _fail(code)
    return text


def _source_sha256(value: object, *, code: str) -> str:
    source_sha256 = _required_text(value, code=code, maximum=64).casefold()
    if _HEX_SHA256.fullmatch(source_sha256) is None:
        _fail(code)
    return source_sha256


def _labels(value: object, *, code: str) -> tuple[str, ...]:
    if isinstance(value, (bytes, str)) or not isinstance(value, Sequence):
        _fail(code)
    labels = tuple(value)
    if not labels or len(labels) > _MAXIMUM_EXPECTED_LABELS:
        _fail(code)
    normalised: dict[str, str] = {}
    for value in labels:
        label = _required_text(value, code=code, maximum=150)
        folded = label.casefold()
        if folded in normalised:
            _fail(code)
        normalised[folded] = label
    return tuple(normalised[key] for key in sorted(normalised))


def _approval_payload(
    *,
    project_evidence_id: str,
    source_sha256: str,
    estimate_id: str,
    labels: tuple[str, ...],
    approval_reference: str,
    approved_by_user_id: str,
) -> dict[str, object]:
    return {
        "schema": REPORT_EXPECTED_LABEL_APPROVAL_SCHEMA,
        "project_evidence_id": project_evidence_id,
        "source_sha256": source_sha256,
        "estimate_id": estimate_id,
        "expected_report_defect_labels": list(labels),
        "approval_reference": approval_reference,
        "approved_by_user_id": approved_by_user_id,
    }


def _manifest_sha256(payload: dict[str, object]) -> str:
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReportExpectedLabelManifestError("REPORT_EXPECTED_LABEL_MANIFEST_INVALID") from exc
    return hashlib.sha256(encoded).hexdigest().upper()


def _project_evidence(
    db: Session,
    *,
    project_evidence_id: str,
    source_sha256: str,
    estimate_id: str,
    project_id: str,
    stored_file_id: str | None,
    lock: bool,
) -> ProjectEvidence:
    statement = select(ProjectEvidence).where(ProjectEvidence.id == project_evidence_id)
    if lock:
        statement = statement.with_for_update()
    evidence = db.scalar(statement.execution_options(populate_existing=True))
    if evidence is None:
        _fail("REPORT_EXPECTED_LABEL_MANIFEST_SOURCE_NOT_FOUND")
    if evidence.source_sha256 != source_sha256:
        _fail("REPORT_EXPECTED_LABEL_MANIFEST_SOURCE_MISMATCH")
    if stored_file_id is not None and evidence.stored_file_id != stored_file_id:
        _fail("REPORT_EXPECTED_LABEL_MANIFEST_SOURCE_MISMATCH")

    estimate = db.get(Estimate, estimate_id)
    if estimate is None or estimate.project_id != project_id:
        _fail("REPORT_EXPECTED_LABEL_MANIFEST_PROJECT_MISMATCH")
    if evidence.project_id is not None:
        if evidence.project_id != project_id:
            _fail("REPORT_EXPECTED_LABEL_MANIFEST_PROJECT_MISMATCH")
    elif evidence.estimate_id != estimate_id:
        _fail("REPORT_EXPECTED_LABEL_MANIFEST_ESTIMATE_MISMATCH")
    return evidence


def _approved_manifest(record: ReportExpectedLabelManifest) -> ApprovedReportExpectedLabelManifest:
    record_id = _required_id(record.id, code="REPORT_EXPECTED_LABEL_MANIFEST_INTEGRITY_INVALID")
    project_evidence_id = _required_id(
        record.project_evidence_id,
        code="REPORT_EXPECTED_LABEL_MANIFEST_INTEGRITY_INVALID",
    )
    source_sha256 = _source_sha256(
        record.source_sha256,
        code="REPORT_EXPECTED_LABEL_MANIFEST_INTEGRITY_INVALID",
    )
    estimate_id = _required_id(
        record.estimate_id,
        code="REPORT_EXPECTED_LABEL_MANIFEST_INTEGRITY_INVALID",
    )
    labels = _labels(
        record.expected_report_defect_labels,
        code="REPORT_EXPECTED_LABEL_MANIFEST_INTEGRITY_INVALID",
    )
    if list(labels) != record.expected_report_defect_labels:
        _fail("REPORT_EXPECTED_LABEL_MANIFEST_INTEGRITY_INVALID")
    approval_reference = _required_text(
        record.approval_reference,
        code="REPORT_EXPECTED_LABEL_MANIFEST_INTEGRITY_INVALID",
        maximum=500,
    )
    approved_by_user_id = _required_id(
        record.approved_by_user_id,
        code="REPORT_EXPECTED_LABEL_MANIFEST_INTEGRITY_INVALID",
    )
    if not isinstance(record.approved_at, datetime):
        _fail("REPORT_EXPECTED_LABEL_MANIFEST_INTEGRITY_INVALID")
    approved_at = record.approved_at
    if approved_at.tzinfo is None:
        approved_at = approved_at.replace(tzinfo=UTC)
    else:
        approved_at = approved_at.astimezone(UTC)
    expected_sha256 = _manifest_sha256(
        _approval_payload(
            project_evidence_id=project_evidence_id,
            source_sha256=source_sha256,
            estimate_id=estimate_id,
            labels=labels,
            approval_reference=approval_reference,
            approved_by_user_id=approved_by_user_id,
        )
    )
    if record.manifest_sha256 != expected_sha256:
        _fail("REPORT_EXPECTED_LABEL_MANIFEST_INTEGRITY_INVALID")
    return ApprovedReportExpectedLabelManifest(
        id=record_id,
        project_evidence_id=project_evidence_id,
        source_sha256=source_sha256,
        estimate_id=estimate_id,
        expected_report_defect_labels=labels,
        manifest_sha256=expected_sha256,
        approval_reference=approval_reference,
        approved_by_user_id=approved_by_user_id,
        approved_at=approved_at,
    )


def record_approved_report_expected_label_manifest(
    db: Session,
    *,
    project_id: object,
    estimate_id: object,
    stored_file_id: object,
    report_sha256: object,
    expected_report_defect_labels: object,
    approval_reference: object,
    approved_by_user_id: object,
) -> ApprovedReportExpectedLabelManifest:
    """Retain one human-approved label list without committing the transaction."""

    project = _required_id(project_id, code="REPORT_EXPECTED_LABEL_MANIFEST_PROJECT_INVALID")
    estimate = _required_id(estimate_id, code="REPORT_EXPECTED_LABEL_MANIFEST_ESTIMATE_INVALID")
    stored_file = _required_id(
        stored_file_id,
        code="REPORT_EXPECTED_LABEL_MANIFEST_STORED_FILE_INVALID",
    )
    source_sha256 = _source_sha256(
        report_sha256,
        code="REPORT_EXPECTED_LABEL_MANIFEST_SOURCE_INVALID",
    )
    labels = _labels(
        expected_report_defect_labels,
        code="REPORT_EXPECTED_LABEL_MANIFEST_LABELS_INVALID",
    )
    reference = _required_text(
        approval_reference,
        code="REPORT_EXPECTED_LABEL_MANIFEST_APPROVAL_REFERENCE_INVALID",
        maximum=500,
    )
    reviewer_id = _required_id(
        approved_by_user_id,
        code="REPORT_EXPECTED_LABEL_MANIFEST_REVIEWER_INVALID",
    )
    reviewer = db.get(User, reviewer_id)
    if reviewer is None or reviewer.is_active is not True:
        _fail("REPORT_EXPECTED_LABEL_MANIFEST_REVIEWER_INVALID")

    evidence = db.scalar(
        select(ProjectEvidence)
        .where(ProjectEvidence.stored_file_id == stored_file)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if evidence is None:
        _fail("REPORT_EXPECTED_LABEL_MANIFEST_SOURCE_NOT_FOUND")
    _project_evidence(
        db,
        project_evidence_id=evidence.id,
        source_sha256=source_sha256,
        estimate_id=estimate,
        project_id=project,
        stored_file_id=stored_file,
        lock=False,
    )
    payload = _approval_payload(
        project_evidence_id=evidence.id,
        source_sha256=source_sha256,
        estimate_id=estimate,
        labels=labels,
        approval_reference=reference,
        approved_by_user_id=reviewer_id,
    )
    manifest_sha256 = _manifest_sha256(payload)
    existing = db.scalar(
        select(ReportExpectedLabelManifest)
        .where(
            ReportExpectedLabelManifest.project_evidence_id == evidence.id,
            ReportExpectedLabelManifest.manifest_sha256 == manifest_sha256,
            ReportExpectedLabelManifest.approval_reference == reference,
            ReportExpectedLabelManifest.approved_by_user_id == reviewer_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if existing is not None:
        return _approved_manifest(existing)

    record = ReportExpectedLabelManifest(
        project_evidence_id=evidence.id,
        source_sha256=source_sha256,
        estimate_id=estimate,
        expected_report_defect_labels=list(labels),
        manifest_sha256=manifest_sha256,
        approval_reference=reference,
        approved_by_user_id=reviewer_id,
        approved_at=now_utc(),
    )
    try:
        with db.begin_nested():
            db.add(record)
            db.flush()
    except IntegrityError:
        existing = db.scalar(
            select(ReportExpectedLabelManifest)
            .where(
                ReportExpectedLabelManifest.project_evidence_id == evidence.id,
                ReportExpectedLabelManifest.manifest_sha256 == manifest_sha256,
                ReportExpectedLabelManifest.approval_reference == reference,
                ReportExpectedLabelManifest.approved_by_user_id == reviewer_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if existing is not None:
            return _approved_manifest(existing)
        _fail("REPORT_EXPECTED_LABEL_MANIFEST_RECORD_CONFLICT")
    return _approved_manifest(record)


def require_approved_report_expected_label_manifest(
    db: Session,
    *,
    expected_label_manifest_id: object,
    project_id: object,
    estimate_id: object,
    stored_file_id: object,
    report_sha256: object,
) -> ApprovedReportExpectedLabelManifest:
    """Load one exact, source-bound approval record under the caller transaction."""

    manifest_id = _required_id(
        expected_label_manifest_id,
        code="REPORT_EXPECTED_LABEL_MANIFEST_ID_INVALID",
    )
    project = _required_id(project_id, code="REPORT_EXPECTED_LABEL_MANIFEST_PROJECT_INVALID")
    estimate = _required_id(estimate_id, code="REPORT_EXPECTED_LABEL_MANIFEST_ESTIMATE_INVALID")
    stored_file = _required_id(
        stored_file_id,
        code="REPORT_EXPECTED_LABEL_MANIFEST_STORED_FILE_INVALID",
    )
    source_sha256 = _source_sha256(
        report_sha256,
        code="REPORT_EXPECTED_LABEL_MANIFEST_SOURCE_INVALID",
    )
    record = db.scalar(
        select(ReportExpectedLabelManifest)
        .where(ReportExpectedLabelManifest.id == manifest_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if record is None:
        _fail("REPORT_EXPECTED_LABEL_MANIFEST_NOT_FOUND")
    approved = _approved_manifest(record)
    if approved.estimate_id != estimate or approved.source_sha256 != source_sha256:
        _fail("REPORT_EXPECTED_LABEL_MANIFEST_SOURCE_MISMATCH")
    evidence = _project_evidence(
        db,
        project_evidence_id=approved.project_evidence_id,
        source_sha256=source_sha256,
        estimate_id=estimate,
        project_id=project,
        stored_file_id=stored_file,
        lock=True,
    )
    if evidence.id != approved.project_evidence_id:
        _fail("REPORT_EXPECTED_LABEL_MANIFEST_SOURCE_MISMATCH")
    return approved


__all__ = [
    "REPORT_EXPECTED_LABEL_APPROVAL_SCHEMA",
    "ApprovedReportExpectedLabelManifest",
    "ReportExpectedLabelManifestError",
    "record_approved_report_expected_label_manifest",
    "require_approved_report_expected_label_manifest",
]
