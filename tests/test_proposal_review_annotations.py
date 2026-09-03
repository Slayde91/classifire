from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from test_proposal_review_package_lifecycle import (
    _grant_project_reader,
    _package_and_bindings,
    _reviewer_request,
    _session,
)

from classifire.models import AuditEvent, ProposalReviewAnnotation
from classifire.services.proposal_review_package import (
    ProposalReviewPackageError,
    create_proposal_review_package_redaction,
    list_proposal_review_annotations,
    record_proposal_review_annotation,
    register_proposal_review_package,
)


def _registered_package():  # type: ignore[no-untyped-def]
    db = _session()
    package, administrator, reviewer, outsider = _package_and_bindings(db)
    record, _ = register_proposal_review_package(
        db,
        package=package,
        actor=administrator,
        registered_at=datetime(2026, 9, 4, 9, 0, tzinfo=UTC),
    )
    _grant_project_reader(
        db,
        record=record,
        administrator=administrator,
        reader=reviewer,
    )
    return db, record, administrator, reviewer, outsider


def test_administrator_annotation_is_hash_bound_idempotent_and_proposal_only() -> None:
    db, record, administrator, reviewer, outsider = _registered_package()

    annotation, created = record_proposal_review_annotation(
        db,
        package_id=record.package_id,
        scope_id="SCOPE-001",
        finding_state="human_verification_required",
        reason_code="SOURCE_CONTEXT_INCOMPLETE",
        actor=administrator,
        recorded_at=datetime(2026, 9, 4, 9, 30, tzinfo=UTC),
    )
    replay, replay_created = record_proposal_review_annotation(
        db,
        package_id=record.package_id,
        scope_id="SCOPE-001",
        finding_state="human_verification_required",
        reason_code="SOURCE_CONTEXT_INCOMPLETE",
        actor=administrator,
        recorded_at=datetime(2026, 9, 5, 9, 30, tzinfo=UTC),
    )

    assert created is True
    assert replay_created is False
    assert replay.id == annotation.id
    assert annotation.proposal_review_package_id == record.id
    assert annotation.proposal_review_package_redaction_id is None
    assert annotation.package_manifest_sha256 == record.package_manifest_sha256
    assert annotation.reviewer_summary_sha256 == record.reviewer_summary_sha256
    assert annotation.scope_id == "SCOPE-001"
    assert annotation.finding_state == "human_verification_required"
    assert annotation.proposal_only is True
    assert len(annotation.annotation_sha256) == 64
    assert list_proposal_review_annotations(db, record=record, actor=reviewer) == (annotation,)

    audit = db.scalar(
        select(AuditEvent).where(AuditEvent.action == "record_proposal_review_annotation")
    )
    assert audit is not None
    assert audit.new_value == {
        "annotation_id": annotation.annotation_id,
        "proposal_review_package_id": record.id,
        "proposal_review_package_redaction_id": None,
        "package_manifest_sha256": record.package_manifest_sha256,
        "reviewer_summary_sha256": record.reviewer_summary_sha256,
        "scope_id": "SCOPE-001",
        "finding_state": "human_verification_required",
        "reason_code": "SOURCE_CONTEXT_INCOMPLETE",
        "proposal_only": True,
        "canonical_submission_performed": False,
        "technical_selection_performed": False,
        "commercial_pricing_performed": False,
        "physical_model_lock_created": False,
        "human_release_performed": False,
    }
    with pytest.raises(ProposalReviewPackageError, match="PROPOSAL_REVIEW_PACKAGE_ADMIN_REQUIRED"):
        record_proposal_review_annotation(
            db,
            package_id=record.package_id,
            finding_state="confirmed",
            reason_code="HUMAN_REVIEW",
            actor=reviewer,
        )
    with pytest.raises(ProposalReviewPackageError, match="PROPOSAL_REVIEW_PACKAGE_ADMIN_REQUIRED"):
        record_proposal_review_annotation(
            db,
            package_id=record.package_id,
            finding_state="confirmed",
            reason_code="HUMAN_REVIEW",
            actor=outsider,
        )


def test_annotation_binds_the_visible_redacted_view_and_rejects_tampering() -> None:
    db, record, administrator, reviewer, _ = _registered_package()
    redaction, _ = create_proposal_review_package_redaction(
        db,
        proposal_review_package_id=record.id,
        redacted_scope_ids=["SCOPE-001"],
        redaction_reason_code="PERSONAL_DATA",
        actor=administrator,
    )
    annotation, _ = record_proposal_review_annotation(
        db,
        package_id=record.package_id,
        redaction_id=redaction.id,
        scope_id="SCOPE-002",
        finding_state="contradictory",
        reason_code="EVIDENCE_CONTRADICTION",
        actor=administrator,
        recorded_at=datetime(2026, 9, 4, 10, 0, tzinfo=UTC),
    )
    assert annotation.proposal_review_package_redaction_id == redaction.id
    assert annotation.reviewer_summary_sha256 == redaction.redacted_summary_sha256
    assert list_proposal_review_annotations(db, record=record, actor=reviewer) == ()
    assert list_proposal_review_annotations(
        db,
        record=record,
        actor=reviewer,
        redaction_id=redaction.id,
    ) == (annotation,)

    with pytest.raises(
        ProposalReviewPackageError,
        match="PROPOSAL_REVIEW_PACKAGE_ANNOTATION_INVALID",
    ):
        record_proposal_review_annotation(
            db,
            package_id=record.package_id,
            redaction_id=redaction.id,
            scope_id="SCOPE-001",
            finding_state="unknown",
            reason_code="REDACTED_SCOPE",
            actor=administrator,
        )

    annotation.reason_code = "FORGED_ANNOTATION"
    db.flush()
    with pytest.raises(ProposalReviewPackageError, match="PROPOSAL_REVIEW_PACKAGE_TAMPERED"):
        list_proposal_review_annotations(db, record=record, actor=reviewer)


def test_annotation_page_is_administrator_only_and_remains_proposal_only() -> None:
    from classifire.proposal_review_admin import (
        proposal_review_annotation_record,
        proposal_review_package_page,
    )

    db, record, administrator, reviewer, _ = _registered_package()
    administrator_request = _reviewer_request(administrator.id)
    reviewer_request = _reviewer_request(reviewer.id)

    administrator_detail = proposal_review_package_page(
        record.package_id,
        administrator_request,
        db,
    )
    reviewer_detail = proposal_review_package_page(record.package_id, reviewer_request, db)
    assert b"Human review annotations" in administrator_detail.body
    assert b"Record annotation" in administrator_detail.body
    assert b"Record annotation" not in reviewer_detail.body

    with pytest.raises(HTTPException) as forbidden:
        proposal_review_annotation_record(
            record.package_id,
            reviewer_request,
            db,
            csrf_token=str(reviewer_request.session["csrf_token"]),
            finding_state="confirmed",
            reason_code="HUMAN_REVIEW",
        )
    assert forbidden.value.status_code == 403

    result = proposal_review_annotation_record(
        record.package_id,
        administrator_request,
        db,
        csrf_token=str(administrator_request.session["csrf_token"]),
        finding_state="inferred",
        reason_code="HUMAN_REVIEW",
    )
    assert result.status_code == 303
    annotation = db.scalar(select(ProposalReviewAnnotation))
    assert annotation is not None
    assert annotation.scope_id is None
    assert annotation.proposal_only is True