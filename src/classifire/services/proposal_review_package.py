"""Governed, immutable metadata for proposal-only report-review packages."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, NoReturn

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import (
    Estimate,
    ProjectEvidence,
    ProposalReviewPackage,
    ProposalReviewPackageRedaction,
    ReportExpectedLabelManifest,
    User,
)
from ..security import has_permission
from .phase8_report_review_package import (
    REPORT_EXPECTED_LABEL_MANIFEST_SCHEMA_V2,
    Phase8ReportReviewPackage,
    validate_phase8_report_review_package,
)
from .phase8_visual_proposal import canonical_json_sha256

PROPOSAL_REVIEW_PACKAGE_RECORD_SCHEMA = "CLASSIFIRE-PROPOSAL-REVIEW-PACKAGE-RECORD-v1"
PROPOSAL_REVIEW_PACKAGE_REDACTION_SCHEMA = "CLASSIFIRE-PROPOSAL-REVIEW-REDACTION-v1"
PROPOSAL_REVIEW_PACKAGE_SAFE_LOCATOR_SCHEMA = "CLASSIFIRE-PROPOSAL-REVIEW-LOCATOR-v1"
PROPOSAL_REVIEW_PACKAGE_RECORD_OWNER = "CLASSIFIRE"
PROPOSAL_REVIEW_PACKAGE_RETENTION_YEARS = 5

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


def _package_values(db: Session, package: Phase8ReportReviewPackage) -> dict[str, Any]:
    if validate_phase8_report_review_package(package):
        _fail("PROPOSAL_REVIEW_PACKAGE_INPUT_INVALID")
    manifest, labels = package.manifest, _approved_label_file(package)
    try:
        values: dict[str, Any] = {
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
    if (
        any(labels[name] != values[name] for name in bound_names)
        or labels["approved_expected_label_manifest_approval_reference"]
        != values["approval_reference"]
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
        or approved.approval_reference != values["approval_reference"]
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


def _matches(record: ProposalReviewPackage, values: Mapping[str, Any]) -> bool:
    fields = (
        "package_id",
        "project_id",
        "estimate_id",
        "project_evidence_id",
        "report_sha256",
        "approved_expected_label_manifest_id",
        "approved_expected_label_manifest_sha256",
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


def _validate_record(db: Session, record: ProposalReviewPackage) -> dict[str, Any]:
    summary = record.reviewer_summary_json
    expected = {
        "schema",
        "package_id",
        "selected_defect_count",
        "outcomes",
        "proposal_only",
        *_NOOP_FLAGS,
    }
    if (
        record.record_owner != PROPOSAL_REVIEW_PACKAGE_RECORD_OWNER
        or not isinstance(summary, dict)
        or set(summary) != expected
        or summary.get("schema") != PROPOSAL_REVIEW_PACKAGE_RECORD_SCHEMA
        or summary.get("package_id") != record.package_id
        or summary.get("selected_defect_count") != record.selected_defect_count
        or summary.get("proposal_only") is not True
        or any(summary.get(flag) is not False for flag in _NOOP_FLAGS)
        or _json_hash(summary, code="PROPOSAL_REVIEW_PACKAGE_TAMPERED")
        != record.reviewer_summary_sha256
        or record.safe_locator_json != _safe_locator(record)
        or _json_hash(_safe_locator(record), code="PROPOSAL_REVIEW_PACKAGE_TAMPERED")
        != record.safe_locator_sha256
    ):
        _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")
    if (
        _hash(record.package_sha256, code="PROPOSAL_REVIEW_PACKAGE_TAMPERED")
        != record.package_sha256
        or _hash(record.package_manifest_sha256, code="PROPOSAL_REVIEW_PACKAGE_TAMPERED")
        != record.package_manifest_sha256
        or _hash(record.completion_receipt_sha256, code="PROPOSAL_REVIEW_PACKAGE_TAMPERED")
        != record.completion_receipt_sha256
        or _hash(
            record.approved_expected_label_manifest_sha256,
            code="PROPOSAL_REVIEW_PACKAGE_TAMPERED",
        )
        != record.approved_expected_label_manifest_sha256
        or _source_hash(record.report_sha256, code="PROPOSAL_REVIEW_PACKAGE_TAMPERED")
        != record.report_sha256
    ):
        _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")
    outcomes = summary["outcomes"]
    if not isinstance(outcomes, list) or len(outcomes) != record.selected_defect_count:
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
        or record.retention_until.tzinfo is None
        or record.created_at.tzinfo is None
        or record.retention_until < record.created_at
        or (record.legal_hold_active and record.legal_hold_reason_code is None)
        or (not record.legal_hold_active and record.legal_hold_reason_code is not None)
    ):
        _fail("PROPOSAL_REVIEW_PACKAGE_TAMPERED")
    return summary



def register_proposal_review_package(
    db: Session,
    *,
    package: Phase8ReportReviewPackage,
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
        raise ProposalReviewPackageError(
            "PROPOSAL_REVIEW_PACKAGE_REDACTION_CONFLICT"
        ) from exc
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

    _require_reader(actor)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        _fail("PROPOSAL_REVIEW_PACKAGE_LIST_INVALID")
    return tuple(
        db.scalars(
            select(ProposalReviewPackage)
            .order_by(ProposalReviewPackage.created_at.desc())
            .limit(limit)
        ).all()
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
    "list_proposal_review_packages",
    "read_proposal_review_package",
    "record_proposal_review_package_tamper",
    "register_proposal_review_package",
    "set_proposal_review_package_legal_hold",
]
