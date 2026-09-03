"""Governed, immutable metadata for proposal-only report-review packages."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, NoReturn

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import (
    Estimate,
    Project,
    ProjectEvidence,
    ProposalReviewPackage,
    ProposalReviewPackageRedaction,
    ProposalReviewReaderAssignment,
    ReportExpectedLabelManifest,
    User,
)
from ..security import has_permission
from .phase8_report_evidence_family_review_package import (
    Phase8ReportEvidenceFamilyReviewPackage,
    validate_phase8_report_evidence_family_review_package,
)
from .phase8_report_review_package import (
    REPORT_EXPECTED_LABEL_MANIFEST_SCHEMA_V2,
    Phase8ReportReviewPackage,
    validate_phase8_report_review_package,
)
from .phase8_visual_proposal import canonical_json_sha256
from .report_evidence_family_manifest import (
    ReportEvidenceFamilyManifestError,
    require_approved_report_evidence_family_manifest,
)

PROPOSAL_REVIEW_PACKAGE_RECORD_SCHEMA = "CLASSIFIRE-PROPOSAL-REVIEW-PACKAGE-RECORD-v1"
PROPOSAL_REVIEW_PACKAGE_FAMILY_RECORD_SCHEMA = "CLASSIFIRE-PROPOSAL-REVIEW-FAMILY-PACKAGE-RECORD-v1"
PROPOSAL_REVIEW_PACKAGE_REDACTION_SCHEMA = "CLASSIFIRE-PROPOSAL-REVIEW-REDACTION-v1"
PROPOSAL_REVIEW_PACKAGE_SAFE_LOCATOR_SCHEMA = "CLASSIFIRE-PROPOSAL-REVIEW-LOCATOR-v1"
PROPOSAL_REVIEW_PACKAGE_FAMILY_SAFE_LOCATOR_SCHEMA = "CLASSIFIRE-PROPOSAL-REVIEW-FAMILY-LOCATOR-v1"
PROPOSAL_REVIEW_PACKAGE_KIND_SINGLE_REPORT = "single_report"
PROPOSAL_REVIEW_PACKAGE_KIND_REPORT_EVIDENCE_FAMILY = "report_evidence_family"
PROPOSAL_REVIEW_PACKAGE_RECORD_OWNER = "CLASSIFIRE"
PROPOSAL_REVIEW_PACKAGE_RETENTION_YEARS = 5
PROPOSAL_REVIEW_READER_SCOPE_PROJECT = "project"
PROPOSAL_REVIEW_READER_SCOPE_PACKAGE = "package"

_SAFE_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,99}$")
_SHA256 = re.compile(r"^[0-9A-F]{64}$")
_SOURCE_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_NOOP_FLAGS = (
    "canonical_submission_performed",
    "technical_selection_performed",
    "commercial_pricing_performed",
    "physical_model_lock_created",
    "human_release_performed",
)


class ProposalReviewPackageError(ValueError):
    """A stable, content-safe failure at the proposal-review record boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ProposalReviewPackageView:
    """One integrity-checked reviewer view, optionally with a redaction."""

    record: ProposalReviewPackage
    reviewer_summary: dict[str, Any]
    safe_locator: dict[str, Any]
    redaction: ProposalReviewPackageRedaction | None = None


def _fail(code: str) -> NoReturn:
    raise ProposalReviewPackageError(code)


def _text(value: object, *, code: str, maximum: int) -> str:
    if not isinstance(value, str):
        _fail(code)
    value = value.strip()
    if not value or len(value) > maximum:
        _fail(code)
    return value


def _hash(value: object, *, code: str) -> str:
    value = _text(value, code=code, maximum=64).upper()
    if _SHA256.fullmatch(value) is None:
        _fail(code)
    return value


def _source_hash(value: object, *, code: str) -> str:
    value = _text(value, code=code, maximum=64)
    if _SOURCE_SHA256.fullmatch(value) is None:
        _fail(code)
    return value


def _safe_code(value: object, *, code: str) -> str:
    value = _text(value, code=code, maximum=100)
    if _SAFE_CODE.fullmatch(value) is None:
        _fail(code)
    return value


def _canonical_json(value: object, *, code: str) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProposalReviewPackageError(code) from exc


def _json_hash(value: object, *, code: str) -> str:
    return hashlib.sha256(_canonical_json(value, code=code).encode("utf-8")).hexdigest().upper()


def _require_reader(actor: User | None) -> User:
    if actor is None or actor.is_active is not True:
        _fail("PROPOSAL_REVIEW_PACKAGE_HUMAN_READER_REQUIRED")
    if not has_permission(actor, "proposal_review:read"):
        _fail("PROPOSAL_REVIEW_PACKAGE_READ_FORBIDDEN")
    return actor


def _require_administrator(actor: User | None) -> User:
    if actor is None or actor.is_active is not True or actor.role != "administrator":
        _fail("PROPOSAL_REVIEW_PACKAGE_ADMIN_REQUIRED")
    return actor


def _reader_assignment_scope(
    *,
    project_id: str | None,
    proposal_review_package_id: str | None,
    code: str,
) -> tuple[str, str]:
    if (project_id is None) == (proposal_review_package_id is None):
        _fail(code)
    if project_id is not None:
        return PROPOSAL_REVIEW_READER_SCOPE_PROJECT, _text(project_id, code=code, maximum=36)
    return PROPOSAL_REVIEW_READER_SCOPE_PACKAGE, _text(
        proposal_review_package_id,
        code=code,
        maximum=36,
    )


def _require_assigned_reader(
    db: Session,
    *,
    record: ProposalReviewPackage,
    actor: User | None,
) -> User:
    actor = _require_reader(actor)
    if actor.role == "administrator":
        return actor
    assignment_id = db.scalar(
        select(ProposalReviewReaderAssignment.id).where(
            ProposalReviewReaderAssignment.user_id == actor.id,
            ProposalReviewReaderAssignment.active.is_(True),
            or_(
                and_(
                    ProposalReviewReaderAssignment.scope_kind
                    == PROPOSAL_REVIEW_READER_SCOPE_PROJECT,
                    ProposalReviewReaderAssignment.project_id == record.project_id,
                ),
                and_(
                    ProposalReviewReaderAssignment.scope_kind
                    == PROPOSAL_REVIEW_READER_SCOPE_PACKAGE,
                    ProposalReviewReaderAssignment.proposal_review_package_id == record.id,
                ),
            ),
        )
    )
    if assignment_id is None:
        _fail("PROPOSAL_REVIEW_PACKAGE_READER_ASSIGNMENT_REQUIRED")
    return actor


def _stored_utc(value: datetime, *, code: str) -> datetime:
    """Normalise a database timestamp without mutating stored proposal metadata."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    try:
        return value.astimezone(UTC)
    except ValueError as exc:
        raise ProposalReviewPackageError(code) from exc


def _retention_until(value: datetime) -> datetime:
    if value.tzinfo is None:
        _fail("PROPOSAL_REVIEW_PACKAGE_REGISTERED_AT_INVALID")
    value = value.astimezone(UTC)
    try:
        return value.replace(year=value.year + PROPOSAL_REVIEW_PACKAGE_RETENTION_YEARS)
    except ValueError:
        return value.replace(
            year=value.year + PROPOSAL_REVIEW_PACKAGE_RETENTION_YEARS,
            month=2,
            day=28,
        )


def _reviewer_summary(package: Phase8ReportReviewPackage) -> dict[str, Any]:
    outcomes = []
    for artifact in package.artifacts:
        review = artifact.review
        blocker = review.get("blocker_code")
        outcomes.append(
            {
                "scope_id": _text(
                    review.get("scope_id"),
                    code="PROPOSAL_REVIEW_PACKAGE_REVIEW_INVALID",
                    maximum=36,
                ),
                "defect_id": _text(
                    review.get("defect_id"),
                    code="PROPOSAL_REVIEW_PACKAGE_REVIEW_INVALID",
                    maximum=36,
                ),
                "defect_reference": _text(
                    review.get("defect_reference"),
                    code="PROPOSAL_REVIEW_PACKAGE_REVIEW_INVALID",
                    maximum=150,
                ),
                "report_defect_label": _text(
                    review.get("report_defect_label"),
                    code="PROPOSAL_REVIEW_PACKAGE_REVIEW_INVALID",
                    maximum=150,
                ),
                "review_status": _safe_code(
                    review.get("review_status"),
                    code="PROPOSAL_REVIEW_PACKAGE_REVIEW_INVALID",
                ),
                "blocker_code": (
                    _safe_code(blocker, code="PROPOSAL_REVIEW_PACKAGE_REVIEW_INVALID")
                    if blocker is not None
                    else None
                ),
            }
        )
    return {
        "schema": PROPOSAL_REVIEW_PACKAGE_RECORD_SCHEMA,
        "package_id": package.manifest["package_id"],
        "selected_defect_count": len(outcomes),
        "outcomes": outcomes,
        "proposal_only": True,
        **{flag: False for flag in _NOOP_FLAGS},
    }


def _safe_locator(record: ProposalReviewPackage | Mapping[str, Any]) -> dict[str, Any]:
    def value(name: str) -> Any:
        return record[name] if isinstance(record, Mapping) else getattr(record, name)

    package_kind = value("package_kind")
    if package_kind == PROPOSAL_REVIEW_PACKAGE_KIND_SINGLE_REPORT:
        return {
            "schema": PROPOSAL_REVIEW_PACKAGE_SAFE_LOCATOR_SCHEMA,
            "record_owner": PROPOSAL_REVIEW_PACKAGE_RECORD_OWNER,
            "project_id": value("project_id"),
            "estimate_id": value("estimate_id"),
            "project_evidence_id": value("project_evidence_id"),
            "report_sha256": value("report_sha256"),
            "approved_expected_label_manifest_id": value("approved_expected_label_manifest_id"),
            "approved_expected_label_manifest_sha256": value(
                "approved_expected_label_manifest_sha256"
            ),
            "approval_reference": value("approval_reference"),
            "package_id": value("package_id"),
            "package_sha256": value("package_sha256"),
            "package_manifest_sha256": value("package_manifest_sha256"),
            "completion_receipt_sha256": value("completion_receipt_sha256"),
        }
    if package_kind == PROPOSAL_REVIEW_PACKAGE_KIND_REPORT_EVIDENCE_FAMILY:
        return {
            "schema": PROPOSAL_REVIEW_PACKAGE_FAMILY_SAFE_LOCATOR_SCHEMA,
            "record_owner": PROPOSAL_REVIEW_PACKAGE_RECORD_OWNER,
            "package_kind": package_kind,
            "project_id": value("project_id"),
            "estimate_id": value("estimate_id"),
            "report_evidence_family_manifest_id": value("report_evidence_family_manifest_id"),
            "report_evidence_family_manifest_sha256": value(
                "report_evidence_family_manifest_sha256"
            ),
            "report_evidence_family_manifest_approval_reference": value(
                "report_evidence_family_manifest_approval_reference"
            ),
            "approval_reference": value("approval_reference"),
            "package_id": value("package_id"),
            "package_sha256": value("package_sha256"),
            "package_manifest_sha256": value("package_manifest_sha256"),
            "completion_receipt_sha256": value("completion_receipt_sha256"),
        }
    _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")


def _approved_label_file(package: Phase8ReportReviewPackage) -> dict[str, Any]:
    raw = package.expected_label_manifest_file_bytes
    if not isinstance(raw, bytes):
        _fail("PROPOSAL_REVIEW_PACKAGE_APPROVED_LABEL_MANIFEST_REQUIRED")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProposalReviewPackageError(
            "PROPOSAL_REVIEW_PACKAGE_APPROVED_LABEL_MANIFEST_INVALID"
        ) from exc
    required = {
        "schema",
        "project_evidence_id",
        "report_sha256",
        "estimate_id",
        "package_id",
        "package_sha256",
        "approval_reference",
        "expected_report_defect_labels",
        "approved_expected_label_manifest_id",
        "approved_expected_label_manifest_sha256",
        "approved_expected_label_manifest_approval_reference",
    }
    if (
        not isinstance(value, dict)
        or set(value) != required
        or value["schema"] != REPORT_EXPECTED_LABEL_MANIFEST_SCHEMA_V2
    ):
        _fail("PROPOSAL_REVIEW_PACKAGE_APPROVED_LABEL_MANIFEST_INVALID")
    return value


def _single_report_package_values(
    db: Session,
    package: Phase8ReportReviewPackage,
    *,
    require_matching_package_approval_reference: bool = True,
) -> dict[str, Any]:
    if validate_phase8_report_review_package(package):
        _fail("PROPOSAL_REVIEW_PACKAGE_INPUT_INVALID")
    manifest, labels = package.manifest, _approved_label_file(package)
    try:
        values: dict[str, Any] = {
            "package_kind": PROPOSAL_REVIEW_PACKAGE_KIND_SINGLE_REPORT,
            "package_id": _text(
                manifest["package_id"],
                code="PROPOSAL_REVIEW_PACKAGE_MANIFEST_INVALID",
                maximum=128,
            ),
            "project_evidence_id": _text(
                manifest["project_evidence_id"],
                code="PROPOSAL_REVIEW_PACKAGE_MANIFEST_INVALID",
                maximum=36,
            ),
            "report_sha256": _source_hash(
                manifest["report_sha256"],
                code="PROPOSAL_REVIEW_PACKAGE_MANIFEST_INVALID",
            ),
            "estimate_id": _text(
                manifest["estimate_id"],
                code="PROPOSAL_REVIEW_PACKAGE_MANIFEST_INVALID",
                maximum=36,
            ),
            "package_sha256": _hash(
                manifest["package_sha256"],
                code="PROPOSAL_REVIEW_PACKAGE_MANIFEST_INVALID",
            ),
            "approval_reference": _text(
                manifest["approval_reference"],
                code="PROPOSAL_REVIEW_PACKAGE_MANIFEST_INVALID",
                maximum=500,
            ),
            "approved_expected_label_manifest_id": _text(
                labels["approved_expected_label_manifest_id"],
                code="PROPOSAL_REVIEW_PACKAGE_APPROVED_LABEL_MANIFEST_INVALID",
                maximum=36,
            ),
            "approved_expected_label_manifest_sha256": _hash(
                labels["approved_expected_label_manifest_sha256"],
                code="PROPOSAL_REVIEW_PACKAGE_APPROVED_LABEL_MANIFEST_INVALID",
            ),
            "report_evidence_family_manifest_id": None,
            "report_evidence_family_manifest_sha256": None,
            "report_evidence_family_manifest_approval_reference": None,
        }
    except KeyError as exc:
        raise ProposalReviewPackageError("PROPOSAL_REVIEW_PACKAGE_MANIFEST_INVALID") from exc
    bound_names = (
        "package_id",
        "project_evidence_id",
        "report_sha256",
        "estimate_id",
        "package_sha256",
        "approval_reference",
    )
    if any(labels[name] != values[name] for name in bound_names):
        _fail("PROPOSAL_REVIEW_PACKAGE_APPROVED_LABEL_MANIFEST_INVALID")
    expected_label_approval_reference = _text(
        labels["approved_expected_label_manifest_approval_reference"],
        code="PROPOSAL_REVIEW_PACKAGE_APPROVED_LABEL_MANIFEST_INVALID",
        maximum=500,
    )
    if (
        require_matching_package_approval_reference
        and expected_label_approval_reference != values["approval_reference"]
    ):
        _fail("PROPOSAL_REVIEW_PACKAGE_APPROVED_LABEL_MANIFEST_INVALID")
    evidence = db.get(ProjectEvidence, values["project_evidence_id"])
    estimate = db.get(Estimate, values["estimate_id"])
    approved = db.get(
        ReportExpectedLabelManifest,
        values["approved_expected_label_manifest_id"],
    )
    if evidence is None or estimate is None or approved is None:
        _fail("PROPOSAL_REVIEW_PACKAGE_BINDING_NOT_FOUND")
    if (
        evidence.source_sha256 != values["report_sha256"]
        or (evidence.project_id != estimate.project_id and evidence.estimate_id != estimate.id)
        or approved.project_evidence_id != evidence.id
        or approved.source_sha256 != values["report_sha256"]
        or approved.estimate_id != estimate.id
        or approved.manifest_sha256 != values["approved_expected_label_manifest_sha256"]
        or approved.approval_reference != expected_label_approval_reference
        or (
            require_matching_package_approval_reference
            and approved.approval_reference != values["approval_reference"]
        )
    ):
        _fail("PROPOSAL_REVIEW_PACKAGE_BINDING_MISMATCH")
    summary = _reviewer_summary(package)
    if summary["selected_defect_count"] != manifest["selected_defect_count"]:
        _fail("PROPOSAL_REVIEW_PACKAGE_REVIEW_INVALID")
    values.update(
        {
            "project_id": estimate.project_id,
            "package_manifest_sha256": canonical_json_sha256(manifest),
            "completion_receipt_sha256": package.completion_receipt_file_sha256,
            "selected_defect_count": summary["selected_defect_count"],
            "reviewer_summary_json": summary,
            "reviewer_summary_sha256": _json_hash(
                summary,
                code="PROPOSAL_REVIEW_PACKAGE_REVIEW_INVALID",
            ),
        }
    )
    values["safe_locator_json"] = _safe_locator(values)
    values["safe_locator_sha256"] = _json_hash(
        values["safe_locator_json"],
        code="PROPOSAL_REVIEW_PACKAGE_REVIEW_INVALID",
    )
    return values


def _family_reviewer_summary(
    package: Phase8ReportEvidenceFamilyReviewPackage,
    member_values: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    if len(package.artifacts) != len(member_values) or not member_values:
        _fail("PROPOSAL_REVIEW_PACKAGE_REVIEW_INVALID")
    outcomes: list[dict[str, Any]] = []
    members: list[dict[str, Any]] = []
    seen_scope_ids: set[str] = set()
    for artifact, values in zip(package.artifacts, member_values, strict=True):
        member = artifact.member
        summary = values["reviewer_summary_json"]
        member_binding = {
            "member_sequence": member.member_sequence,
            "project_evidence_id": member.project_evidence_id,
            "stored_file_id": member.stored_file_id,
            "report_sha256": member.source_sha256,
            "approved_expected_label_manifest_id": values["approved_expected_label_manifest_id"],
            "approved_expected_label_manifest_sha256": values[
                "approved_expected_label_manifest_sha256"
            ],
            "approved_expected_label_manifest_approval_reference": _text(
                _approved_label_file(artifact.report_review_package)[
                    "approved_expected_label_manifest_approval_reference"
                ],
                code="PROPOSAL_REVIEW_PACKAGE_REVIEW_INVALID",
                maximum=500,
            ),
            "report_review_package_id": values["package_id"],
            "report_review_package_manifest_sha256": values["package_manifest_sha256"],
            "report_review_completion_receipt_sha256": values["completion_receipt_sha256"],
            "selected_defect_count": values["selected_defect_count"],
        }
        if (
            values["project_evidence_id"] != member.project_evidence_id
            or values["report_sha256"] != member.source_sha256
            or values["selected_defect_count"] != summary["selected_defect_count"]
        ):
            _fail("PROPOSAL_REVIEW_PACKAGE_BINDING_MISMATCH")
        members.append(member_binding)
        for outcome in summary["outcomes"]:
            scope_id = outcome["scope_id"]
            if scope_id in seen_scope_ids:
                _fail("PROPOSAL_REVIEW_PACKAGE_REVIEW_INVALID")
            seen_scope_ids.add(scope_id)
            outcomes.append(
                {
                    "member_sequence": member.member_sequence,
                    "project_evidence_id": member.project_evidence_id,
                    "report_sha256": member.source_sha256,
                    **outcome,
                }
            )
    return {
        "schema": PROPOSAL_REVIEW_PACKAGE_FAMILY_RECORD_SCHEMA,
        "package_id": package.manifest["package_id"],
        "member_count": len(members),
        "selected_defect_count": len(outcomes),
        "members": members,
        "outcomes": outcomes,
        "proposal_only": True,
        **{flag: False for flag in _NOOP_FLAGS},
    }


def _family_package_values(
    db: Session,
    package: Phase8ReportEvidenceFamilyReviewPackage,
) -> dict[str, Any]:
    if validate_phase8_report_evidence_family_review_package(package):
        _fail("PROPOSAL_REVIEW_PACKAGE_INPUT_INVALID")
    manifest = package.manifest
    try:
        values: dict[str, Any] = {
            "package_kind": PROPOSAL_REVIEW_PACKAGE_KIND_REPORT_EVIDENCE_FAMILY,
            "package_id": _text(
                manifest["package_id"],
                code="PROPOSAL_REVIEW_PACKAGE_MANIFEST_INVALID",
                maximum=128,
            ),
            "project_id": _text(
                manifest["project_id"],
                code="PROPOSAL_REVIEW_PACKAGE_MANIFEST_INVALID",
                maximum=36,
            ),
            "estimate_id": _text(
                manifest["estimate_id"],
                code="PROPOSAL_REVIEW_PACKAGE_MANIFEST_INVALID",
                maximum=36,
            ),
            "report_evidence_family_manifest_id": _text(
                manifest["report_evidence_family_manifest_id"],
                code="PROPOSAL_REVIEW_PACKAGE_MANIFEST_INVALID",
                maximum=36,
            ),
            "report_evidence_family_manifest_sha256": _hash(
                manifest["report_evidence_family_manifest_sha256"],
                code="PROPOSAL_REVIEW_PACKAGE_MANIFEST_INVALID",
            ),
            "report_evidence_family_manifest_approval_reference": _text(
                manifest["report_evidence_family_manifest_approval_reference"],
                code="PROPOSAL_REVIEW_PACKAGE_MANIFEST_INVALID",
                maximum=500,
            ),
            "approval_reference": _text(
                manifest["approval_reference"],
                code="PROPOSAL_REVIEW_PACKAGE_MANIFEST_INVALID",
                maximum=500,
            ),
            "package_sha256": _hash(
                manifest["package_sha256"],
                code="PROPOSAL_REVIEW_PACKAGE_MANIFEST_INVALID",
            ),
        }
    except KeyError as exc:
        raise ProposalReviewPackageError("PROPOSAL_REVIEW_PACKAGE_MANIFEST_INVALID") from exc
    try:
        approved_family = require_approved_report_evidence_family_manifest(
            db,
            report_evidence_family_manifest_id=values["report_evidence_family_manifest_id"],
            project_id=values["project_id"],
            estimate_id=values["estimate_id"],
        )
    except ReportEvidenceFamilyManifestError as exc:
        raise ProposalReviewPackageError("PROPOSAL_REVIEW_PACKAGE_BINDING_NOT_FOUND") from exc
    if (
        approved_family.manifest_sha256 != values["report_evidence_family_manifest_sha256"]
        or approved_family.approval_reference
        != values["report_evidence_family_manifest_approval_reference"]
        or approved_family.project_id != values["project_id"]
        or approved_family.estimate_id != values["estimate_id"]
        or len(package.artifacts) != len(approved_family.members)
    ):
        _fail("PROPOSAL_REVIEW_PACKAGE_BINDING_MISMATCH")
    member_values = tuple(
        _single_report_package_values(
            db,
            artifact.report_review_package,
            require_matching_package_approval_reference=False,
        )
        for artifact in package.artifacts
    )
    for artifact, member_values_item, approved_member in zip(
        package.artifacts,
        member_values,
        approved_family.members,
        strict=True,
    ):
        member = artifact.member
        if (
            member != approved_member
            or member_values_item["project_evidence_id"] != member.project_evidence_id
            or member_values_item["report_sha256"] != member.source_sha256
            or member_values_item["estimate_id"] != values["estimate_id"]
        ):
            _fail("PROPOSAL_REVIEW_PACKAGE_BINDING_MISMATCH")
    summary = _family_reviewer_summary(package, member_values)
    if summary["member_count"] != len(approved_family.members) or not summary["outcomes"]:
        _fail("PROPOSAL_REVIEW_PACKAGE_REVIEW_INVALID")
    values.update(
        {
            "project_evidence_id": None,
            "report_sha256": None,
            "approved_expected_label_manifest_id": None,
            "approved_expected_label_manifest_sha256": None,
            "package_manifest_sha256": canonical_json_sha256(manifest),
            "completion_receipt_sha256": package.completion_receipt_file_sha256,
            "selected_defect_count": summary["selected_defect_count"],
            "reviewer_summary_json": summary,
            "reviewer_summary_sha256": _json_hash(
                summary,
                code="PROPOSAL_REVIEW_PACKAGE_REVIEW_INVALID",
            ),
        }
    )
    values["safe_locator_json"] = _safe_locator(values)
    values["safe_locator_sha256"] = _json_hash(
        values["safe_locator_json"],
        code="PROPOSAL_REVIEW_PACKAGE_REVIEW_INVALID",
    )
    return values


def _package_values(
    db: Session,
    package: Phase8ReportReviewPackage | Phase8ReportEvidenceFamilyReviewPackage,
) -> dict[str, Any]:
    if isinstance(package, Phase8ReportReviewPackage):
        return _single_report_package_values(db, package)
    if isinstance(package, Phase8ReportEvidenceFamilyReviewPackage):
        return _family_package_values(db, package)
    _fail("PROPOSAL_REVIEW_PACKAGE_INPUT_INVALID")


def _matches(record: ProposalReviewPackage, values: Mapping[str, Any]) -> bool:
    fields = (
        "package_id",
        "package_kind",
        "project_id",
        "estimate_id",
        "project_evidence_id",
        "report_sha256",
        "approved_expected_label_manifest_id",
        "approved_expected_label_manifest_sha256",
        "report_evidence_family_manifest_id",
        "report_evidence_family_manifest_sha256",
        "report_evidence_family_manifest_approval_reference",
        "approval_reference",
        "package_sha256",
        "package_manifest_sha256",
        "completion_receipt_sha256",
        "selected_defect_count",
        "reviewer_summary_json",
        "reviewer_summary_sha256",
        "safe_locator_json",
        "safe_locator_sha256",
    )
    return all(getattr(record, field) == values[field] for field in fields)


def _validate_lifecycle_state(record: ProposalReviewPackage) -> None:
    retention_until = _stored_utc(
        record.retention_until,
        code="PROPOSAL_REVIEW_PACKAGE_TAMPERED",
    )
    created_at = _stored_utc(
        record.created_at,
        code="PROPOSAL_REVIEW_PACKAGE_TAMPERED",
    )
    if (
        record.record_owner != PROPOSAL_REVIEW_PACKAGE_RECORD_OWNER
        or retention_until < created_at
        or (record.legal_hold_active and record.legal_hold_reason_code is None)
        or (not record.legal_hold_active and record.legal_hold_reason_code is not None)
    ):
        _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")
    for value in (
        record.package_sha256,
        record.package_manifest_sha256,
        record.completion_receipt_sha256,
        record.reviewer_summary_sha256,
        record.safe_locator_sha256,
    ):
        _hash(value, code="PROPOSAL_REVIEW_PACKAGE_TAMPERED")


def _validate_single_report_outcomes(outcomes: object, *, selected_defect_count: int) -> None:
    if not isinstance(outcomes, list) or len(outcomes) != selected_defect_count:
        _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")
    seen: set[str] = set()
    for outcome in outcomes:
        if not isinstance(outcome, dict) or set(outcome) != {
            "scope_id",
            "defect_id",
            "defect_reference",
            "report_defect_label",
            "review_status",
            "blocker_code",
        }:
            _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")
        scope_id = _text(
            outcome["scope_id"],
            code="PROPOSAL_REVIEW_PACKAGE_TAMPERED",
            maximum=36,
        )
        if scope_id in seen:
            _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")
        seen.add(scope_id)
        for field, maximum in (
            ("defect_id", 36),
            ("defect_reference", 150),
            ("report_defect_label", 150),
        ):
            _text(outcome[field], code="PROPOSAL_REVIEW_PACKAGE_TAMPERED", maximum=maximum)
        _safe_code(outcome["review_status"], code="PROPOSAL_REVIEW_PACKAGE_TAMPERED")
        if outcome["blocker_code"] is not None:
            _safe_code(outcome["blocker_code"], code="PROPOSAL_REVIEW_PACKAGE_TAMPERED")


def _validate_single_report_record(
    db: Session,
    record: ProposalReviewPackage,
    summary: dict[str, Any],
) -> dict[str, Any]:
    expected = {
        "schema",
        "package_id",
        "selected_defect_count",
        "outcomes",
        "proposal_only",
        *_NOOP_FLAGS,
    }
    if (
        record.project_evidence_id is None
        or record.report_sha256 is None
        or record.approved_expected_label_manifest_id is None
        or record.approved_expected_label_manifest_sha256 is None
        or record.report_evidence_family_manifest_id is not None
        or record.report_evidence_family_manifest_sha256 is not None
        or record.report_evidence_family_manifest_approval_reference is not None
        or set(summary) != expected
        or summary.get("schema") != PROPOSAL_REVIEW_PACKAGE_RECORD_SCHEMA
        or summary.get("package_id") != record.package_id
        or summary.get("selected_defect_count") != record.selected_defect_count
        or summary.get("proposal_only") is not True
        or any(summary.get(flag) is not False for flag in _NOOP_FLAGS)
        or _hash(
            record.approved_expected_label_manifest_sha256,
            code="PROPOSAL_REVIEW_PACKAGE_TAMPERED",
        )
        != record.approved_expected_label_manifest_sha256
        or _source_hash(record.report_sha256, code="PROPOSAL_REVIEW_PACKAGE_TAMPERED")
        != record.report_sha256
    ):
        _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")
    _validate_single_report_outcomes(
        summary["outcomes"],
        selected_defect_count=record.selected_defect_count,
    )
    evidence = db.get(ProjectEvidence, record.project_evidence_id)
    estimate = db.get(Estimate, record.estimate_id)
    approved = db.get(ReportExpectedLabelManifest, record.approved_expected_label_manifest_id)
    if (
        evidence is None
        or estimate is None
        or approved is None
        or estimate.project_id != record.project_id
        or evidence.source_sha256 != record.report_sha256
        or (evidence.project_id != record.project_id and evidence.estimate_id != record.estimate_id)
        or approved.project_evidence_id != evidence.id
        or approved.source_sha256 != record.report_sha256
        or approved.estimate_id != record.estimate_id
        or approved.manifest_sha256 != record.approved_expected_label_manifest_sha256
        or approved.approval_reference != record.approval_reference
    ):
        _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")
    return summary


def _validate_family_members(
    db: Session,
    *,
    record: ProposalReviewPackage,
    summary: dict[str, Any],
) -> dict[int, dict[str, Any]]:
    if (
        record.report_evidence_family_manifest_id is None
        or record.report_evidence_family_manifest_sha256 is None
        or record.report_evidence_family_manifest_approval_reference is None
    ):
        _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")
    try:
        approved_family = require_approved_report_evidence_family_manifest(
            db,
            report_evidence_family_manifest_id=record.report_evidence_family_manifest_id,
            project_id=record.project_id,
            estimate_id=record.estimate_id,
        )
    except ReportEvidenceFamilyManifestError as exc:
        raise ProposalReviewPackageError("PROPOSAL_REVIEW_PACKAGE_TAMPERED") from exc
    if (
        approved_family.manifest_sha256 != record.report_evidence_family_manifest_sha256
        or approved_family.approval_reference
        != record.report_evidence_family_manifest_approval_reference
    ):
        _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")
    members = summary["members"]
    if (
        not isinstance(members, list)
        or len(members) != len(approved_family.members)
        or summary["member_count"] != len(members)
    ):
        _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")
    expected_fields = {
        "member_sequence",
        "project_evidence_id",
        "stored_file_id",
        "report_sha256",
        "approved_expected_label_manifest_id",
        "approved_expected_label_manifest_sha256",
        "approved_expected_label_manifest_approval_reference",
        "report_review_package_id",
        "report_review_package_manifest_sha256",
        "report_review_completion_receipt_sha256",
        "selected_defect_count",
    }
    bindings: dict[int, dict[str, Any]] = {}
    for stored_member, approved_member in zip(members, approved_family.members, strict=True):
        if not isinstance(stored_member, dict) or set(stored_member) != expected_fields:
            _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")
        sequence = stored_member["member_sequence"]
        count = stored_member["selected_defect_count"]
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence != approved_member.member_sequence
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count <= 0
            or sequence in bindings
            or _text(
                stored_member["project_evidence_id"],
                code="PROPOSAL_REVIEW_PACKAGE_TAMPERED",
                maximum=36,
            )
            != approved_member.project_evidence_id
            or _text(
                stored_member["stored_file_id"],
                code="PROPOSAL_REVIEW_PACKAGE_TAMPERED",
                maximum=36,
            )
            != approved_member.stored_file_id
            or _source_hash(
                stored_member["report_sha256"],
                code="PROPOSAL_REVIEW_PACKAGE_TAMPERED",
            )
            != approved_member.source_sha256
            or not _text(
                stored_member["approved_expected_label_manifest_id"],
                code="PROPOSAL_REVIEW_PACKAGE_TAMPERED",
                maximum=36,
            )
            or _hash(
                stored_member["approved_expected_label_manifest_sha256"],
                code="PROPOSAL_REVIEW_PACKAGE_TAMPERED",
            )
            != stored_member["approved_expected_label_manifest_sha256"]
            or not _text(
                stored_member["approved_expected_label_manifest_approval_reference"],
                code="PROPOSAL_REVIEW_PACKAGE_TAMPERED",
                maximum=500,
            )
            or not _text(
                stored_member["report_review_package_id"],
                code="PROPOSAL_REVIEW_PACKAGE_TAMPERED",
                maximum=128,
            )
            or _hash(
                stored_member["report_review_package_manifest_sha256"],
                code="PROPOSAL_REVIEW_PACKAGE_TAMPERED",
            )
            != stored_member["report_review_package_manifest_sha256"]
            or _hash(
                stored_member["report_review_completion_receipt_sha256"],
                code="PROPOSAL_REVIEW_PACKAGE_TAMPERED",
            )
            != stored_member["report_review_completion_receipt_sha256"]
        ):
            _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")
        evidence = db.get(ProjectEvidence, approved_member.project_evidence_id)
        approved_labels = db.get(
            ReportExpectedLabelManifest,
            stored_member["approved_expected_label_manifest_id"],
        )
        if (
            evidence is None
            or approved_labels is None
            or evidence.source_sha256 != approved_member.source_sha256
            or (
                evidence.project_id != record.project_id
                and evidence.estimate_id != record.estimate_id
            )
            or approved_labels.project_evidence_id != evidence.id
            or approved_labels.source_sha256 != approved_member.source_sha256
            or approved_labels.estimate_id != record.estimate_id
            or approved_labels.manifest_sha256
            != stored_member["approved_expected_label_manifest_sha256"]
            or approved_labels.approval_reference
            != stored_member["approved_expected_label_manifest_approval_reference"]
        ):
            _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")
        bindings[sequence] = stored_member
    return bindings


def _validate_family_outcomes(
    outcomes: object,
    *,
    bindings: Mapping[int, Mapping[str, Any]],
    selected_defect_count: int,
) -> None:
    if not isinstance(outcomes, list) or len(outcomes) != selected_defect_count:
        _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")
    expected_fields = {
        "member_sequence",
        "project_evidence_id",
        "report_sha256",
        "scope_id",
        "defect_id",
        "defect_reference",
        "report_defect_label",
        "review_status",
        "blocker_code",
    }
    seen_scope_ids: set[str] = set()
    counts = {sequence: 0 for sequence in bindings}
    for outcome in outcomes:
        if not isinstance(outcome, dict) or set(outcome) != expected_fields:
            _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")
        sequence = outcome["member_sequence"]
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence not in bindings:
            _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")
        binding = bindings[sequence]
        if (
            outcome["project_evidence_id"] != binding["project_evidence_id"]
            or outcome["report_sha256"] != binding["report_sha256"]
        ):
            _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")
        scope_id = _text(
            outcome["scope_id"],
            code="PROPOSAL_REVIEW_PACKAGE_TAMPERED",
            maximum=36,
        )
        if scope_id in seen_scope_ids:
            _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")
        seen_scope_ids.add(scope_id)
        for field, maximum in (
            ("defect_id", 36),
            ("defect_reference", 150),
            ("report_defect_label", 150),
        ):
            _text(outcome[field], code="PROPOSAL_REVIEW_PACKAGE_TAMPERED", maximum=maximum)
        _safe_code(outcome["review_status"], code="PROPOSAL_REVIEW_PACKAGE_TAMPERED")
        if outcome["blocker_code"] is not None:
            _safe_code(outcome["blocker_code"], code="PROPOSAL_REVIEW_PACKAGE_TAMPERED")
        counts[sequence] += 1
    if any(
        counts[sequence] != binding["selected_defect_count"]
        for sequence, binding in bindings.items()
    ):
        _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")


def _validate_family_record(
    db: Session,
    record: ProposalReviewPackage,
    summary: dict[str, Any],
) -> dict[str, Any]:
    expected = {
        "schema",
        "package_id",
        "member_count",
        "selected_defect_count",
        "members",
        "outcomes",
        "proposal_only",
        *_NOOP_FLAGS,
    }
    if (
        record.project_evidence_id is not None
        or record.report_sha256 is not None
        or record.approved_expected_label_manifest_id is not None
        or record.approved_expected_label_manifest_sha256 is not None
        or set(summary) != expected
        or summary.get("schema") != PROPOSAL_REVIEW_PACKAGE_FAMILY_RECORD_SCHEMA
        or summary.get("package_id") != record.package_id
        or summary.get("proposal_only") is not True
        or any(summary.get(flag) is not False for flag in _NOOP_FLAGS)
        or isinstance(summary.get("member_count"), bool)
        or not isinstance(summary.get("member_count"), int)
        or summary["member_count"] < 2
        or summary.get("selected_defect_count") != record.selected_defect_count
    ):
        _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")
    bindings = _validate_family_members(db, record=record, summary=summary)
    _validate_family_outcomes(
        summary["outcomes"],
        bindings=bindings,
        selected_defect_count=record.selected_defect_count,
    )
    return summary


def _validate_record(db: Session, record: ProposalReviewPackage) -> dict[str, Any]:
    summary = record.reviewer_summary_json
    if (
        not isinstance(summary, dict)
        or _json_hash(summary, code="PROPOSAL_REVIEW_PACKAGE_TAMPERED")
        != record.reviewer_summary_sha256
        or record.safe_locator_json != _safe_locator(record)
        or _json_hash(_safe_locator(record), code="PROPOSAL_REVIEW_PACKAGE_TAMPERED")
        != record.safe_locator_sha256
    ):
        _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")
    _validate_lifecycle_state(record)
    if record.package_kind == PROPOSAL_REVIEW_PACKAGE_KIND_SINGLE_REPORT:
        return _validate_single_report_record(db, record, summary)
    if record.package_kind == PROPOSAL_REVIEW_PACKAGE_KIND_REPORT_EVIDENCE_FAMILY:
        return _validate_family_record(db, record, summary)
    _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")


def register_proposal_review_package(
    db: Session,
    *,
    package: Phase8ReportReviewPackage | Phase8ReportEvidenceFamilyReviewPackage,
    actor: User | None,
    registered_at: datetime | None = None,
) -> tuple[ProposalReviewPackage, bool]:
    """Persist validated metadata only; never package bytes or operational authority."""

    actor = _require_administrator(actor)
    values = _package_values(db, package)
    existing = db.scalar(
        select(ProposalReviewPackage).where(
            ProposalReviewPackage.package_id == values["package_id"]
        )
    ) or db.scalar(
        select(ProposalReviewPackage).where(
            ProposalReviewPackage.package_manifest_sha256 == values["package_manifest_sha256"]
        )
    )
    if existing is not None:
        _validate_record(db, existing)
        if _matches(existing, values):
            return existing, False
        _fail("PROPOSAL_REVIEW_PACKAGE_REPLAY_CONFLICT")
    created_at = registered_at or datetime.now(UTC)
    if created_at.tzinfo is None:
        _fail("PROPOSAL_REVIEW_PACKAGE_REGISTERED_AT_INVALID")
    created_at = created_at.astimezone(UTC)
    item = ProposalReviewPackage(
        **values,
        record_owner=PROPOSAL_REVIEW_PACKAGE_RECORD_OWNER,
        retention_until=_retention_until(created_at),
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(item)
    try:
        db.flush()
    except IntegrityError as exc:
        raise ProposalReviewPackageError("PROPOSAL_REVIEW_PACKAGE_REPLAY_CONFLICT") from exc
    record_audit(
        db,
        actor=actor,
        action="register_proposal_review_package",
        entity_type="proposal_review_package",
        entity_id=item.id,
        project_id=item.project_id,
        new_value={
            "record_owner": item.record_owner,
            "package_id": item.package_id,
            "package_manifest_sha256": item.package_manifest_sha256,
            "completion_receipt_sha256": item.completion_receipt_sha256,
            "retention_until": item.retention_until.isoformat(),
            "proposal_only": True,
            **{flag: False for flag in _NOOP_FLAGS},
        },
        reason="Stored immutable proposal-only review metadata; no package bytes or authority.",
    )
    return item, True


def _redacted_summary(
    record: ProposalReviewPackage,
    summary: dict[str, Any],
    scope_ids: list[str],
    reason: str,
) -> dict[str, Any]:
    visible = [
        outcome for outcome in summary["outcomes"] if outcome["scope_id"] not in set(scope_ids)
    ]
    return {
        "schema": PROPOSAL_REVIEW_PACKAGE_REDACTION_SCHEMA,
        "package_id": record.package_id,
        "original_reviewer_summary_sha256": record.reviewer_summary_sha256,
        "redaction_reason_code": reason,
        "redacted_scope_ids": scope_ids,
        "visible_defect_count": len(visible),
        "outcomes": visible,
        "proposal_only": True,
        **{flag: False for flag in _NOOP_FLAGS},
    }


def create_proposal_review_package_redaction(
    db: Session,
    *,
    proposal_review_package_id: str,
    redacted_scope_ids: Sequence[str],
    redaction_reason_code: str,
    actor: User | None,
) -> tuple[ProposalReviewPackageRedaction, bool]:
    """Create a separate redacted view without changing the source package."""

    actor = _require_administrator(actor)
    record = db.get(ProposalReviewPackage, proposal_review_package_id)
    if record is None:
        _fail("PROPOSAL_REVIEW_PACKAGE_NOT_FOUND")
    _require_assigned_reader(db, record=record, actor=actor)
    summary = _validate_record(db, record)
    if isinstance(redacted_scope_ids, (str, bytes)):
        _fail("PROPOSAL_REVIEW_PACKAGE_REDACTION_INVALID")
    scope_ids = sorted(
        {
            _text(value, code="PROPOSAL_REVIEW_PACKAGE_REDACTION_INVALID", maximum=36)
            for value in redacted_scope_ids
        }
    )
    known = {outcome["scope_id"] for outcome in summary["outcomes"]}
    if not scope_ids or not set(scope_ids).issubset(known):
        _fail("PROPOSAL_REVIEW_PACKAGE_REDACTION_INVALID")
    reason = _safe_code(
        redaction_reason_code,
        code="PROPOSAL_REVIEW_PACKAGE_REDACTION_INVALID",
    )
    redacted_summary = _redacted_summary(record, summary, scope_ids, reason)
    summary_sha256 = _json_hash(
        redacted_summary,
        code="PROPOSAL_REVIEW_PACKAGE_REDACTION_INVALID",
    )
    existing = db.scalar(
        select(ProposalReviewPackageRedaction).where(
            ProposalReviewPackageRedaction.proposal_review_package_id == record.id,
            ProposalReviewPackageRedaction.redacted_summary_sha256 == summary_sha256,
        )
    )
    if existing is not None:
        return existing, False
    redaction = ProposalReviewPackageRedaction(
        proposal_review_package_id=record.id,
        redaction_reason_code=reason,
        redacted_scope_ids=scope_ids,
        redacted_summary_json=redacted_summary,
        redacted_summary_sha256=summary_sha256,
        created_by_user_id=actor.id,
    )
    db.add(redaction)
    try:
        db.flush()
    except IntegrityError as exc:
        raise ProposalReviewPackageError("PROPOSAL_REVIEW_PACKAGE_REDACTION_CONFLICT") from exc
    record_audit(
        db,
        actor=actor,
        action="create_proposal_review_package_redaction",
        entity_type="proposal_review_package_redaction",
        entity_id=redaction.id,
        project_id=record.project_id,
        new_value={
            "proposal_review_package_id": record.id,
            "package_manifest_sha256": record.package_manifest_sha256,
            "redaction_reason_code": reason,
            "redacted_scope_count": len(scope_ids),
            "redacted_summary_sha256": summary_sha256,
            "proposal_only": True,
        },
        reason="Created a separate reviewer redaction without changing package metadata.",
    )
    return redaction, True


def _validate_redaction(
    record: ProposalReviewPackage,
    redaction: ProposalReviewPackageRedaction,
    summary: dict[str, Any],
) -> dict[str, Any]:
    scope_ids = redaction.redacted_scope_ids
    if (
        redaction.proposal_review_package_id != record.id
        or not isinstance(scope_ids, list)
        or scope_ids != sorted(set(scope_ids))
        or not scope_ids
        or any(not isinstance(value, str) for value in scope_ids)
    ):
        _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")
    reason = _safe_code(
        redaction.redaction_reason_code,
        code="PROPOSAL_REVIEW_PACKAGE_TAMPERED",
    )
    expected = _redacted_summary(record, summary, scope_ids, reason)
    if (
        redaction.redacted_summary_json != expected
        or _json_hash(expected, code="PROPOSAL_REVIEW_PACKAGE_TAMPERED")
        != redaction.redacted_summary_sha256
    ):
        _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")
    return expected


def grant_proposal_review_reader_assignment(
    db: Session,
    *,
    user_id: str,
    project_id: str | None = None,
    proposal_review_package_id: str | None = None,
    reason_code: str,
    actor: User | None,
) -> tuple[ProposalReviewReaderAssignment, bool]:
    """Grant or reactivate exactly one human reader scope without changing a package."""

    actor = _require_administrator(actor)
    scope_kind, target_id = _reader_assignment_scope(
        project_id=project_id,
        proposal_review_package_id=proposal_review_package_id,
        code="PROPOSAL_REVIEW_PACKAGE_READER_ASSIGNMENT_INVALID",
    )
    reader = db.get(
        User,
        _text(user_id, code="PROPOSAL_REVIEW_PACKAGE_READER_ASSIGNMENT_INVALID", maximum=36),
    )
    if (
        reader is None
        or reader.is_active is not True
        or not has_permission(reader, "proposal_review:read")
    ):
        _fail("PROPOSAL_REVIEW_PACKAGE_READER_ASSIGNMENT_INVALID")
    reason = _safe_code(reason_code, code="PROPOSAL_REVIEW_PACKAGE_READER_ASSIGNMENT_INVALID")
    if scope_kind == PROPOSAL_REVIEW_READER_SCOPE_PROJECT:
        project = db.get(Project, target_id)
        if project is None:
            _fail("PROPOSAL_REVIEW_PACKAGE_READER_ASSIGNMENT_NOT_FOUND")
        project_id, proposal_review_package_id, audit_project_id = project.id, None, project.id
    else:
        record = db.get(ProposalReviewPackage, target_id)
        if record is None:
            _fail("PROPOSAL_REVIEW_PACKAGE_READER_ASSIGNMENT_NOT_FOUND")
        _validate_record(db, record)
        project_id, proposal_review_package_id, audit_project_id = (
            None,
            record.id,
            record.project_id,
        )
    existing = db.scalar(
        select(ProposalReviewReaderAssignment).where(
            ProposalReviewReaderAssignment.user_id == reader.id,
            ProposalReviewReaderAssignment.scope_kind == scope_kind,
            ProposalReviewReaderAssignment.project_id == project_id,
            ProposalReviewReaderAssignment.proposal_review_package_id == proposal_review_package_id,
        )
    )
    now = datetime.now(UTC)
    if existing is not None and existing.active:
        return existing, False
    previous = None
    if existing is None:
        assignment = ProposalReviewReaderAssignment(
            user_id=reader.id,
            scope_kind=scope_kind,
            project_id=project_id,
            proposal_review_package_id=proposal_review_package_id,
            active=True,
            granted_by_user_id=actor.id,
            granted_at=now,
        )
        db.add(assignment)
        action = "grant_proposal_review_reader_assignment"
    else:
        assignment = existing
        previous = {
            "active": assignment.active,
            "revoked_at": assignment.revoked_at.isoformat() if assignment.revoked_at else None,
            "revocation_reason_code": assignment.revocation_reason_code,
        }
        assignment.active = True
        assignment.granted_by_user_id = actor.id
        assignment.granted_at = now
        assignment.revoked_by_user_id = None
        assignment.revoked_at = None
        assignment.revocation_reason_code = None
        action = "reactivate_proposal_review_reader_assignment"
    try:
        db.flush()
    except IntegrityError as exc:
        raise ProposalReviewPackageError(
            "PROPOSAL_REVIEW_PACKAGE_READER_ASSIGNMENT_CONFLICT"
        ) from exc
    record_audit(
        db,
        actor=actor,
        action=action,
        entity_type="proposal_review_reader_assignment",
        entity_id=assignment.id,
        project_id=audit_project_id,
        previous_value=previous,
        new_value={
            "user_id": reader.id,
            "scope_kind": scope_kind,
            "project_id": project_id,
            "proposal_review_package_id": proposal_review_package_id,
            "active": True,
            "reason_code": reason,
            "proposal_only": True,
        },
        reason="Granted only controlled proposal-review reader access.",
    )
    return assignment, True


def revoke_proposal_review_reader_assignment(
    db: Session,
    *,
    proposal_review_reader_assignment_id: str,
    record: ProposalReviewPackage,
    reason_code: str,
    actor: User | None,
) -> tuple[ProposalReviewReaderAssignment, bool]:
    """Revoke one reader assignment without altering package evidence or review content."""

    actor = _require_administrator(actor)
    assignment = db.get(ProposalReviewReaderAssignment, proposal_review_reader_assignment_id)
    if assignment is None:
        _fail("PROPOSAL_REVIEW_PACKAGE_READER_ASSIGNMENT_NOT_FOUND")
    _validate_record(db, record)
    if (
        (
            assignment.scope_kind == PROPOSAL_REVIEW_READER_SCOPE_PROJECT
            and assignment.project_id != record.project_id
        )
        or (
            assignment.scope_kind == PROPOSAL_REVIEW_READER_SCOPE_PACKAGE
            and assignment.proposal_review_package_id != record.id
        )
        or assignment.scope_kind
        not in {
            PROPOSAL_REVIEW_READER_SCOPE_PROJECT,
            PROPOSAL_REVIEW_READER_SCOPE_PACKAGE,
        }
    ):
        _fail("PROPOSAL_REVIEW_PACKAGE_READER_ASSIGNMENT_NOT_FOUND")
    if not assignment.active:
        return assignment, False
    reason = _safe_code(reason_code, code="PROPOSAL_REVIEW_PACKAGE_READER_ASSIGNMENT_INVALID")
    audit_project_id = assignment.project_id
    if assignment.proposal_review_package_id is not None:
        package_record = db.get(
            ProposalReviewPackage,
            assignment.proposal_review_package_id,
        )
        if package_record is None:
            _fail("PROPOSAL_REVIEW_PACKAGE_READER_ASSIGNMENT_NOT_FOUND")
        audit_project_id = package_record.project_id
    assignment.active = False
    assignment.revoked_by_user_id = actor.id
    assignment.revoked_at = datetime.now(UTC)
    assignment.revocation_reason_code = reason
    db.flush()
    record_audit(
        db,
        actor=actor,
        action="revoke_proposal_review_reader_assignment",
        entity_type="proposal_review_reader_assignment",
        entity_id=assignment.id,
        project_id=audit_project_id,
        previous_value={"active": True},
        new_value={
            "user_id": assignment.user_id,
            "scope_kind": assignment.scope_kind,
            "project_id": assignment.project_id,
            "proposal_review_package_id": assignment.proposal_review_package_id,
            "active": False,
            "revocation_reason_code": reason,
            "proposal_only": True,
        },
        reason="Revoked only controlled proposal-review reader access.",
    )
    return assignment, True


def list_proposal_review_reader_assignments(
    db: Session,
    *,
    record: ProposalReviewPackage,
    actor: User | None,
) -> tuple[ProposalReviewReaderAssignment, ...]:
    """List only Project and exact-package assignments relevant to one package."""

    _require_administrator(actor)
    return tuple(
        db.scalars(
            select(ProposalReviewReaderAssignment)
            .where(
                or_(
                    and_(
                        ProposalReviewReaderAssignment.scope_kind
                        == PROPOSAL_REVIEW_READER_SCOPE_PROJECT,
                        ProposalReviewReaderAssignment.project_id == record.project_id,
                    ),
                    and_(
                        ProposalReviewReaderAssignment.scope_kind
                        == PROPOSAL_REVIEW_READER_SCOPE_PACKAGE,
                        ProposalReviewReaderAssignment.proposal_review_package_id == record.id,
                    ),
                )
            )
            .order_by(
                ProposalReviewReaderAssignment.active.desc(),
                ProposalReviewReaderAssignment.created_at.desc(),
            )
        ).all()
    )


def list_eligible_proposal_review_readers(
    db: Session,
    *,
    actor: User | None,
) -> tuple[User, ...]:
    """Return eligible active internal human readers for an administrator-only form."""

    _require_administrator(actor)
    return tuple(
        user
        for user in db.scalars(
            select(User).where(User.is_active.is_(True)).order_by(User.full_name)
        ).all()
        if has_permission(user, "proposal_review:read")
    )


def read_proposal_review_package(
    db: Session,
    *,
    package_id: str,
    actor: User | None,
    redaction_id: str | None = None,
) -> ProposalReviewPackageView:
    """Return an integrity-checked human reviewer view and nothing more."""

    _require_reader(actor)
    package_id = _text(package_id, code="PROPOSAL_REVIEW_PACKAGE_NOT_FOUND", maximum=128)
    record = db.scalar(
        select(ProposalReviewPackage).where(ProposalReviewPackage.package_id == package_id)
    )
    if record is None:
        _fail("PROPOSAL_REVIEW_PACKAGE_NOT_FOUND")
    _require_assigned_reader(db, record=record, actor=actor)
    summary = _validate_record(db, record)
    if redaction_id is None:
        return ProposalReviewPackageView(record, summary, record.safe_locator_json)
    redaction = db.get(ProposalReviewPackageRedaction, redaction_id)
    if redaction is None:
        _fail("PROPOSAL_REVIEW_PACKAGE_REDACTION_NOT_FOUND")
    return ProposalReviewPackageView(
        record,
        _validate_redaction(record, redaction, summary),
        record.safe_locator_json,
        redaction,
    )


def list_proposal_review_packages(
    db: Session,
    *,
    actor: User | None,
    limit: int = 200,
) -> tuple[ProposalReviewPackage, ...]:
    """List metadata only after the human-only reader gate."""

    actor = _require_reader(actor)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        _fail("PROPOSAL_REVIEW_PACKAGE_LIST_INVALID")
    statement = select(ProposalReviewPackage)
    if actor.role != "administrator":
        statement = statement.join(
            ProposalReviewReaderAssignment,
            or_(
                and_(
                    ProposalReviewReaderAssignment.scope_kind
                    == PROPOSAL_REVIEW_READER_SCOPE_PROJECT,
                    ProposalReviewReaderAssignment.project_id == ProposalReviewPackage.project_id,
                ),
                and_(
                    ProposalReviewReaderAssignment.scope_kind
                    == PROPOSAL_REVIEW_READER_SCOPE_PACKAGE,
                    ProposalReviewReaderAssignment.proposal_review_package_id
                    == ProposalReviewPackage.id,
                ),
            ),
        ).where(
            ProposalReviewReaderAssignment.user_id == actor.id,
            ProposalReviewReaderAssignment.active.is_(True),
        )
    return tuple(
        db.scalars(statement.order_by(ProposalReviewPackage.created_at.desc()).limit(limit))
        .unique()
        .all()
    )


def record_proposal_review_package_tamper(
    db: Session,
    *,
    record: ProposalReviewPackage,
    actor: User | None,
    error: ProposalReviewPackageError,
) -> None:
    """Record a blocked render without keeping untrusted package content."""

    actor = _require_reader(actor)
    if error.code != "PROPOSAL_REVIEW_PACKAGE_TAMPERED":
        _fail("PROPOSAL_REVIEW_PACKAGE_TAMPER_AUDIT_INVALID")
    record_audit(
        db,
        actor=actor,
        action="reject_tampered_proposal_review_package",
        entity_type="proposal_review_package",
        entity_id=record.id,
        project_id=record.project_id,
        new_value={
            "package_id": record.package_id,
            "package_manifest_sha256": record.package_manifest_sha256,
            "error_code": error.code,
            "proposal_only": True,
        },
        reason="Reviewer rendering blocked because proposal metadata failed integrity checks.",
    )


def set_proposal_review_package_legal_hold(
    db: Session,
    *,
    proposal_review_package_id: str,
    active: bool,
    reason_code: str | None,
    actor: User | None,
) -> ProposalReviewPackage:
    """Change only the lifecycle hold flag; immutable package metadata stays intact."""

    actor = _require_administrator(actor)
    record = db.get(ProposalReviewPackage, proposal_review_package_id)
    if record is None:
        _fail("PROPOSAL_REVIEW_PACKAGE_NOT_FOUND")
    _validate_record(db, record)
    if not isinstance(active, bool) or (not active and reason_code is not None):
        _fail("PROPOSAL_REVIEW_PACKAGE_LEGAL_HOLD_INVALID")
    reason = (
        _safe_code(reason_code, code="PROPOSAL_REVIEW_PACKAGE_LEGAL_HOLD_INVALID")
        if active
        else None
    )
    previous = {
        "legal_hold_active": record.legal_hold_active,
        "legal_hold_reason_code": record.legal_hold_reason_code,
    }
    record.legal_hold_active = active
    record.legal_hold_reason_code = reason
    db.flush()
    record_audit(
        db,
        actor=actor,
        action="set_proposal_review_package_legal_hold",
        entity_type="proposal_review_package",
        entity_id=record.id,
        project_id=record.project_id,
        previous_value=previous,
        new_value={
            "legal_hold_active": active,
            "legal_hold_reason_code": reason,
            "package_manifest_sha256": record.package_manifest_sha256,
        },
        reason="Changed only the proposal-review retention hold state.",
    )
    return record


def delete_expired_proposal_review_package(
    db: Session,
    *,
    proposal_review_package_id: str,
    actor: User | None,
    now: datetime | None = None,
) -> None:
    """Delete only expired, non-held metadata and retain a content-safe tombstone."""

    actor = _require_administrator(actor)
    record = db.get(ProposalReviewPackage, proposal_review_package_id)
    if record is None:
        _fail("PROPOSAL_REVIEW_PACKAGE_NOT_FOUND")
    _validate_record(db, record)
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        _fail("PROPOSAL_REVIEW_PACKAGE_DELETE_TIME_INVALID")
    if record.legal_hold_active:
        _fail("PROPOSAL_REVIEW_PACKAGE_LEGAL_HOLD_ACTIVE")
    if current.astimezone(UTC) < record.retention_until.astimezone(UTC):
        _fail("PROPOSAL_REVIEW_PACKAGE_RETENTION_ACTIVE")
    tombstone = {
        "record_owner": record.record_owner,
        "package_id": record.package_id,
        "package_manifest_sha256": record.package_manifest_sha256,
        "completion_receipt_sha256": record.completion_receipt_sha256,
        "retention_until": record.retention_until.isoformat(),
        "proposal_only": True,
    }
    record_id, project_id = record.id, record.project_id
    db.delete(record)
    db.flush()
    record_audit(
        db,
        actor=actor,
        action="delete_expired_proposal_review_package",
        entity_type="proposal_review_package",
        entity_id=record_id,
        project_id=project_id,
        new_value=tombstone,
        reason="Deleted expired proposal-review metadata after retention and legal-hold checks.",
    )


__all__ = [
    "PROPOSAL_REVIEW_PACKAGE_RECORD_OWNER",
    "PROPOSAL_REVIEW_PACKAGE_RECORD_SCHEMA",
    "PROPOSAL_REVIEW_PACKAGE_REDACTION_SCHEMA",
    "PROPOSAL_REVIEW_PACKAGE_RETENTION_YEARS",
    "ProposalReviewPackageError",
    "ProposalReviewPackageView",
    "create_proposal_review_package_redaction",
    "delete_expired_proposal_review_package",
    "grant_proposal_review_reader_assignment",
    "list_eligible_proposal_review_readers",
    "list_proposal_review_reader_assignments",
    "list_proposal_review_packages",
    "read_proposal_review_package",
    "record_proposal_review_package_tamper",
    "revoke_proposal_review_reader_assignment",
    "register_proposal_review_package",
    "set_proposal_review_package_legal_hold",
]
