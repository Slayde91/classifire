"""Retain and verify explicitly human-approved report evidence families.

A family is an ordered set of already retained source reports. This module does
not infer membership from names, folders, timestamps, content similarity, or
other metadata; it accepts only exact stored-file IDs and source hashes supplied
by a human review workflow. It does not combine reports, create physical-model
records, locks, technical selections, pricing, releases, or commits.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import NoReturn

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import (
    Estimate,
    ProjectEvidence,
    ReportEvidenceFamilyManifest,
    ReportEvidenceFamilyMember,
    StoredFile,
    User,
    now_utc,
)

REPORT_EVIDENCE_FAMILY_APPROVAL_SCHEMA = "CLASSIFIRE-REPORT-EVIDENCE-FAMILY-APPROVAL-v1"

_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAXIMUM_FAMILY_MEMBERS = 1_000
_PROJECT_EVIDENCE_PURPOSE = "project_evidence"


class ReportEvidenceFamilyManifestError(ValueError):
    """Stable, content-safe failure while retaining an approved report family."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ReportEvidenceFamilyMemberBinding:
    """One exact retained report in its human-approved family sequence."""

    member_sequence: int
    project_evidence_id: str
    stored_file_id: str
    source_sha256: str


@dataclass(frozen=True, slots=True)
class ApprovedReportEvidenceFamilyManifest:
    """The verified, immutable family approval safe for future proposal-only use."""

    id: str
    project_id: str
    estimate_id: str
    family_reference: str
    members: tuple[ReportEvidenceFamilyMemberBinding, ...]
    manifest_sha256: str
    approval_reference: str
    approved_by_user_id: str
    approved_at: datetime


def _fail(code: str) -> NoReturn:
    raise ReportEvidenceFamilyManifestError(code)


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


def _requested_members(value: object) -> tuple[tuple[str, str], ...]:
    if isinstance(value, (bytes, str)) or not isinstance(value, Sequence):
        _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_MEMBERS_INVALID")
    requested = tuple(value)
    if len(requested) < 2 or len(requested) > _MAXIMUM_FAMILY_MEMBERS:
        _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_MEMBERS_INVALID")

    members: list[tuple[str, str]] = []
    stored_file_ids: set[str] = set()
    for item in requested:
        if not isinstance(item, Mapping) or set(item) != {"stored_file_id", "report_sha256"}:
            _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_MEMBERS_INVALID")
        stored_file_id = _required_id(
            item["stored_file_id"],
            code="REPORT_EVIDENCE_FAMILY_MANIFEST_MEMBERS_INVALID",
        )
        source_sha256 = _source_sha256(
            item["report_sha256"],
            code="REPORT_EVIDENCE_FAMILY_MANIFEST_MEMBERS_INVALID",
        )
        if stored_file_id in stored_file_ids:
            _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_MEMBERS_INVALID")
        stored_file_ids.add(stored_file_id)
        members.append((stored_file_id, source_sha256))
    return tuple(members)


def _require_estimate(db: Session, *, project_id: str, estimate_id: str) -> Estimate:
    estimate = db.get(Estimate, estimate_id)
    if estimate is None or estimate.project_id != project_id:
        _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_PROJECT_MISMATCH")
    return estimate


def _stored_source(
    db: Session,
    *,
    stored_file_id: str,
    source_sha256: str,
) -> StoredFile:
    stored = db.scalar(
        select(StoredFile)
        .where(StoredFile.id == stored_file_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if stored is None:
        _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_SOURCE_NOT_FOUND")
    if stored.purpose != _PROJECT_EVIDENCE_PURPOSE or stored.immutable is not True:
        _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_SOURCE_INVALID")
    if stored.sha256 != source_sha256:
        _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_SOURCE_MISMATCH")
    if (
        not isinstance(stored.size_bytes, int)
        or isinstance(stored.size_bytes, bool)
        or stored.size_bytes < 1
    ):
        _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_SOURCE_INVALID")
    return stored


def _project_evidence(
    db: Session,
    *,
    project_id: str,
    estimate_id: str,
    stored_file_id: str,
    source_sha256: str,
) -> ProjectEvidence:
    evidence = db.scalar(
        select(ProjectEvidence)
        .where(ProjectEvidence.stored_file_id == stored_file_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if evidence is None:
        _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_SOURCE_NOT_FOUND")
    if evidence.source_sha256 != source_sha256:
        _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_SOURCE_MISMATCH")
    if evidence.project_id is not None:
        if evidence.project_id != project_id:
            _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_PROJECT_MISMATCH")
    elif evidence.estimate_id != estimate_id:
        _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_ESTIMATE_MISMATCH")

    stored = _stored_source(
        db,
        stored_file_id=stored_file_id,
        source_sha256=source_sha256,
    )
    if (
        evidence.stored_file_id != stored.id
        or evidence.source_sha256 != stored.sha256
        or evidence.source_size_bytes != stored.size_bytes
    ):
        _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_SOURCE_MISMATCH")
    return evidence


def _resolved_members(
    db: Session,
    *,
    project_id: str,
    estimate_id: str,
    requested_members: tuple[tuple[str, str], ...],
) -> tuple[ReportEvidenceFamilyMemberBinding, ...]:
    _require_estimate(db, project_id=project_id, estimate_id=estimate_id)
    resolved: dict[str, ReportEvidenceFamilyMemberBinding] = {}
    requested_by_stored_file = dict(requested_members)
    for stored_file_id in sorted(requested_by_stored_file):
        source_sha256 = requested_by_stored_file[stored_file_id]
        evidence = _project_evidence(
            db,
            project_id=project_id,
            estimate_id=estimate_id,
            stored_file_id=stored_file_id,
            source_sha256=source_sha256,
        )
        resolved[stored_file_id] = ReportEvidenceFamilyMemberBinding(
            member_sequence=0,
            project_evidence_id=evidence.id,
            stored_file_id=stored_file_id,
            source_sha256=source_sha256,
        )
    return tuple(
        ReportEvidenceFamilyMemberBinding(
            member_sequence=sequence,
            project_evidence_id=resolved[stored_file_id].project_evidence_id,
            stored_file_id=stored_file_id,
            source_sha256=source_sha256,
        )
        for sequence, (stored_file_id, source_sha256) in enumerate(requested_members, start=1)
    )


def _approval_payload(
    *,
    project_id: str,
    estimate_id: str,
    family_reference: str,
    members: tuple[ReportEvidenceFamilyMemberBinding, ...],
    approval_reference: str,
    approved_by_user_id: str,
) -> dict[str, object]:
    return {
        "schema": REPORT_EVIDENCE_FAMILY_APPROVAL_SCHEMA,
        "project_id": project_id,
        "estimate_id": estimate_id,
        "family_reference": family_reference,
        "members": [
            {
                "member_sequence": member.member_sequence,
                "project_evidence_id": member.project_evidence_id,
                "stored_file_id": member.stored_file_id,
                "source_sha256": member.source_sha256,
            }
            for member in members
        ],
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
        raise ReportEvidenceFamilyManifestError(
            "REPORT_EVIDENCE_FAMILY_MANIFEST_INVALID"
        ) from exc
    return hashlib.sha256(encoded).hexdigest().upper()


def _member_binding(record: ReportEvidenceFamilyMember) -> ReportEvidenceFamilyMemberBinding:
    member_sequence = record.member_sequence
    if (
        not isinstance(member_sequence, int)
        or isinstance(member_sequence, bool)
        or member_sequence < 1
    ):
        _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_INTEGRITY_INVALID")
    return ReportEvidenceFamilyMemberBinding(
        member_sequence=member_sequence,
        project_evidence_id=_required_id(
            record.project_evidence_id,
            code="REPORT_EVIDENCE_FAMILY_MANIFEST_INTEGRITY_INVALID",
        ),
        stored_file_id=_required_id(
            record.stored_file_id,
            code="REPORT_EVIDENCE_FAMILY_MANIFEST_INTEGRITY_INVALID",
        ),
        source_sha256=_source_sha256(
            record.source_sha256,
            code="REPORT_EVIDENCE_FAMILY_MANIFEST_INTEGRITY_INVALID",
        ),
    )


def _members_for_manifest(
    db: Session,
    *,
    report_evidence_family_manifest_id: str,
) -> tuple[ReportEvidenceFamilyMemberBinding, ...]:
    records = db.scalars(
        select(ReportEvidenceFamilyMember)
        .where(
            ReportEvidenceFamilyMember.report_evidence_family_manifest_id
            == report_evidence_family_manifest_id
        )
        .order_by(ReportEvidenceFamilyMember.member_sequence)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    members = tuple(_member_binding(record) for record in records)
    if len({member.member_sequence for member in members}) != len(members):
        _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_INTEGRITY_INVALID")
    if len({member.project_evidence_id for member in members}) != len(members):
        _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_INTEGRITY_INVALID")
    if len({member.stored_file_id for member in members}) != len(members):
        _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_INTEGRITY_INVALID")
    return members


def _approved_manifest(
    record: ReportEvidenceFamilyManifest,
    *,
    members: tuple[ReportEvidenceFamilyMemberBinding, ...],
) -> ApprovedReportEvidenceFamilyManifest:
    record_id = _required_id(record.id, code="REPORT_EVIDENCE_FAMILY_MANIFEST_INTEGRITY_INVALID")
    project_id = _required_id(
        record.project_id,
        code="REPORT_EVIDENCE_FAMILY_MANIFEST_INTEGRITY_INVALID",
    )
    estimate_id = _required_id(
        record.estimate_id,
        code="REPORT_EVIDENCE_FAMILY_MANIFEST_INTEGRITY_INVALID",
    )
    family_reference = _required_text(
        record.family_reference,
        code="REPORT_EVIDENCE_FAMILY_MANIFEST_INTEGRITY_INVALID",
        maximum=150,
    )
    if record.member_count != len(members) or len(members) < 2:
        _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_INTEGRITY_INVALID")
    if tuple(member.member_sequence for member in members) != tuple(range(1, len(members) + 1)):
        _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_INTEGRITY_INVALID")
    approval_reference = _required_text(
        record.approval_reference,
        code="REPORT_EVIDENCE_FAMILY_MANIFEST_INTEGRITY_INVALID",
        maximum=500,
    )
    approved_by_user_id = _required_id(
        record.approved_by_user_id,
        code="REPORT_EVIDENCE_FAMILY_MANIFEST_INTEGRITY_INVALID",
    )
    if not isinstance(record.approved_at, datetime):
        _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_INTEGRITY_INVALID")
    approved_at = record.approved_at
    if approved_at.tzinfo is None:
        approved_at = approved_at.replace(tzinfo=UTC)
    else:
        approved_at = approved_at.astimezone(UTC)
    expected_sha256 = _manifest_sha256(
        _approval_payload(
            project_id=project_id,
            estimate_id=estimate_id,
            family_reference=family_reference,
            members=members,
            approval_reference=approval_reference,
            approved_by_user_id=approved_by_user_id,
        )
    )
    if record.manifest_sha256 != expected_sha256:
        _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_INTEGRITY_INVALID")
    return ApprovedReportEvidenceFamilyManifest(
        id=record_id,
        project_id=project_id,
        estimate_id=estimate_id,
        family_reference=family_reference,
        members=members,
        manifest_sha256=expected_sha256,
        approval_reference=approval_reference,
        approved_by_user_id=approved_by_user_id,
        approved_at=approved_at,
    )


def _load_approved_manifest(
    db: Session,
    *,
    record: ReportEvidenceFamilyManifest,
) -> ApprovedReportEvidenceFamilyManifest:
    return _approved_manifest(
        record,
        members=_members_for_manifest(db, report_evidence_family_manifest_id=record.id),
    )


def record_approved_report_evidence_family_manifest(
    db: Session,
    *,
    project_id: object,
    estimate_id: object,
    family_reference: object,
    report_members: object,
    approval_reference: object,
    approved_by_user_id: object,
) -> ApprovedReportEvidenceFamilyManifest:
    """Retain one exact, human-approved report family without committing."""

    project = _required_id(project_id, code="REPORT_EVIDENCE_FAMILY_MANIFEST_PROJECT_INVALID")
    estimate = _required_id(estimate_id, code="REPORT_EVIDENCE_FAMILY_MANIFEST_ESTIMATE_INVALID")
    reference = _required_text(
        family_reference,
        code="REPORT_EVIDENCE_FAMILY_MANIFEST_REFERENCE_INVALID",
        maximum=150,
    )
    requested_members = _requested_members(report_members)
    approval = _required_text(
        approval_reference,
        code="REPORT_EVIDENCE_FAMILY_MANIFEST_APPROVAL_REFERENCE_INVALID",
        maximum=500,
    )
    reviewer_id = _required_id(
        approved_by_user_id,
        code="REPORT_EVIDENCE_FAMILY_MANIFEST_REVIEWER_INVALID",
    )
    reviewer = db.get(User, reviewer_id)
    if reviewer is None or reviewer.is_active is not True:
        _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_REVIEWER_INVALID")

    members = _resolved_members(
        db,
        project_id=project,
        estimate_id=estimate,
        requested_members=requested_members,
    )
    manifest_sha256 = _manifest_sha256(
        _approval_payload(
            project_id=project,
            estimate_id=estimate,
            family_reference=reference,
            members=members,
            approval_reference=approval,
            approved_by_user_id=reviewer_id,
        )
    )
    existing = db.scalar(
        select(ReportEvidenceFamilyManifest)
        .where(
            ReportEvidenceFamilyManifest.estimate_id == estimate,
            ReportEvidenceFamilyManifest.manifest_sha256 == manifest_sha256,
            ReportEvidenceFamilyManifest.approval_reference == approval,
            ReportEvidenceFamilyManifest.approved_by_user_id == reviewer_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if existing is not None:
        return _load_approved_manifest(db, record=existing)

    record = ReportEvidenceFamilyManifest(
        project_id=project,
        estimate_id=estimate,
        family_reference=reference,
        member_count=len(members),
        manifest_sha256=manifest_sha256,
        approval_reference=approval,
        approved_by_user_id=reviewer_id,
        approved_at=now_utc(),
    )
    try:
        with db.begin_nested():
            db.add(record)
            db.flush()
            db.add_all(
                [
                    ReportEvidenceFamilyMember(
                        report_evidence_family_manifest_id=record.id,
                        member_sequence=member.member_sequence,
                        project_evidence_id=member.project_evidence_id,
                        stored_file_id=member.stored_file_id,
                        source_sha256=member.source_sha256,
                    )
                    for member in members
                ]
            )
            db.flush()
    except IntegrityError:
        existing = db.scalar(
            select(ReportEvidenceFamilyManifest)
            .where(
                ReportEvidenceFamilyManifest.estimate_id == estimate,
                ReportEvidenceFamilyManifest.manifest_sha256 == manifest_sha256,
                ReportEvidenceFamilyManifest.approval_reference == approval,
                ReportEvidenceFamilyManifest.approved_by_user_id == reviewer_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if existing is not None:
            return _load_approved_manifest(db, record=existing)
        _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_RECORD_CONFLICT")
    return _approved_manifest(record, members=members)


def require_approved_report_evidence_family_manifest(
    db: Session,
    *,
    report_evidence_family_manifest_id: object,
    project_id: object,
    estimate_id: object,
) -> ApprovedReportEvidenceFamilyManifest:
    """Load one exact family approval and recheck every retained source binding."""

    manifest_id = _required_id(
        report_evidence_family_manifest_id,
        code="REPORT_EVIDENCE_FAMILY_MANIFEST_ID_INVALID",
    )
    project = _required_id(project_id, code="REPORT_EVIDENCE_FAMILY_MANIFEST_PROJECT_INVALID")
    estimate = _required_id(estimate_id, code="REPORT_EVIDENCE_FAMILY_MANIFEST_ESTIMATE_INVALID")
    record = db.scalar(
        select(ReportEvidenceFamilyManifest)
        .where(ReportEvidenceFamilyManifest.id == manifest_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if record is None:
        _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_NOT_FOUND")
    approved = _load_approved_manifest(db, record=record)
    if approved.project_id != project or approved.estimate_id != estimate:
        _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_SOURCE_MISMATCH")
    _require_estimate(db, project_id=project, estimate_id=estimate)
    for member in approved.members:
        evidence = _project_evidence(
            db,
            project_id=project,
            estimate_id=estimate,
            stored_file_id=member.stored_file_id,
            source_sha256=member.source_sha256,
        )
        if evidence.id != member.project_evidence_id:
            _fail("REPORT_EVIDENCE_FAMILY_MANIFEST_SOURCE_MISMATCH")
    return approved


__all__ = [
    "REPORT_EVIDENCE_FAMILY_APPROVAL_SCHEMA",
    "ApprovedReportEvidenceFamilyManifest",
    "ReportEvidenceFamilyManifestError",
    "ReportEvidenceFamilyMemberBinding",
    "record_approved_report_evidence_family_manifest",
    "require_approved_report_evidence_family_manifest",
]