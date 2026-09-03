from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request
from test_phase8_report_review_package import _package

from classifire.db import Base
from classifire.models import (
    AuditEvent,
    Estimate,
    Project,
    ProjectEvidence,
    ProposalReviewPackage,
    ReportExpectedLabelManifest,
    StoredFile,
    User,
)
from classifire.services.proposal_review_package import (
    PROPOSAL_REVIEW_PACKAGE_RECORD_OWNER,
    ProposalReviewPackageError,
    create_proposal_review_package_redaction,
    delete_expired_proposal_review_package,
    list_proposal_review_packages,
    read_proposal_review_package,
    record_proposal_review_package_tamper,
    register_proposal_review_package,
    set_proposal_review_package_legal_hold,
)


def _session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _users(db: Session) -> tuple[User, User, User]:
    administrator = User(
        id="USER-ADMIN-001",
        email="administrator@example.test",
        full_name="Proposal package administrator",
        password_hash="not-used-in-synthetic-test",  # noqa: S106
        role="administrator",
    )
    reviewer = User(
        id="USER-REVIEWER-001",
        email="reviewer@example.test",
        full_name="Proposal package reviewer",
        password_hash="not-used-in-synthetic-test",  # noqa: S106
        role="technical_reviewer",
    )
    outsider = User(
        id="USER-OUTSIDER-001",
        email="outsider@example.test",
        full_name="Proposal package outsider",
        password_hash="not-used-in-synthetic-test",  # noqa: S106
        role="pricing_manager",
    )
    db.add_all([administrator, reviewer, outsider])
    db.flush()
    return administrator, reviewer, outsider


def _package_and_bindings(db: Session) -> tuple[object, User, User, User]:
    administrator, reviewer, outsider = _users(db)
    project = Project(
        id="PROJECT-001",
        reference="PROPOSAL-REVIEW-001",
        name="Synthetic proposal-review project",
    )
    estimate = Estimate(
        id="EST-001",
        project_id=project.id,
        revision=1,
        reference="PROPOSAL-REVIEW-001-R1",
        title="Synthetic proposal-review estimate",
    )
    stored = StoredFile(
        id="FILE-REPORT-001",
        original_filename="synthetic-report.pdf",
        storage_path="synthetic/report.pdf",
        sha256="a" * 64,
        size_bytes=1,
        purpose="project_evidence",
        immutable=True,
    )
    evidence = ProjectEvidence(
        id="PROJECT-EVIDENCE-001",
        project_id=project.id,
        stored_file_id=stored.id,
        source_sha256=stored.sha256,
        source_size_bytes=stored.size_bytes,
    )
    approved = ReportExpectedLabelManifest(
        id="EXPECTED-LABELS-001",
        project_evidence_id=evidence.id,
        source_sha256=evidence.source_sha256,
        estimate_id=estimate.id,
        expected_report_defect_labels=["D-001", "D-002"],
        manifest_sha256="E" * 64,
        approval_reference="proposal-only approval",
        approved_by_user_id=administrator.id,
        approved_at=datetime(2026, 9, 3, tzinfo=UTC),
    )
    db.add_all([project, estimate, stored, evidence, approved])
    db.flush()
    expected_labels = {
        "schema": "CLASSIFIRE-PHASE8-REPORT-EXPECTED-LABELS-v2",
        "project_evidence_id": evidence.id,
        "report_sha256": evidence.source_sha256,
        "estimate_id": estimate.id,
        "package_id": "PACKAGE-001",
        "package_sha256": "9" * 64,
        "approval_reference": approved.approval_reference,
        "expected_report_defect_labels": ["D-001", "D-002"],
        "approved_expected_label_manifest_id": approved.id,
        "approved_expected_label_manifest_sha256": approved.manifest_sha256,
        "approved_expected_label_manifest_approval_reference": approved.approval_reference,
    }
    package = _package(
        expected_label_manifest_file_bytes=(
            json.dumps(expected_labels, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8")
    )
    return package, administrator, reviewer, outsider


def test_registers_only_hash_bound_metadata_and_allows_exact_replay() -> None:
    db = _session()
    package, administrator, reviewer, outsider = _package_and_bindings(db)
    registered_at = datetime(2026, 9, 3, 11, 30, tzinfo=UTC)

    record, created = register_proposal_review_package(
        db,
        package=package,
        actor=administrator,
        registered_at=registered_at,
    )
    replay, replay_created = register_proposal_review_package(
        db,
        package=package,
        actor=administrator,
        registered_at=registered_at + timedelta(days=1),
    )

    assert created is True
    assert replay_created is False
    assert replay.id == record.id
    assert record.record_owner == PROPOSAL_REVIEW_PACKAGE_RECORD_OWNER
    assert record.retention_until == datetime(2031, 9, 3, 11, 30, tzinfo=UTC)
    assert set(record.reviewer_summary_json) == {
        "schema",
        "package_id",
        "selected_defect_count",
        "outcomes",
        "proposal_only",
        "canonical_submission_performed",
        "technical_selection_performed",
        "commercial_pricing_performed",
        "physical_model_lock_created",
        "human_release_performed",
    }
    assert record.reviewer_summary_json["proposal_only"] is True
    assert all(
        record.reviewer_summary_json[name] is False
        for name in (
            "canonical_submission_performed",
            "technical_selection_performed",
            "commercial_pricing_performed",
            "physical_model_lock_created",
            "human_release_performed",
        )
    )
    assert record.safe_locator_json["project_evidence_id"] == "PROJECT-EVIDENCE-001"
    assert "storage_path" not in record.safe_locator_json
    assert "synthetic/report.pdf" not in json.dumps(record.reviewer_summary_json)
    assert len(list_proposal_review_packages(db, actor=reviewer)) == 1
    assert (
        read_proposal_review_package(
            db,
            package_id=record.package_id,
            actor=reviewer,
        ).reviewer_summary
        == record.reviewer_summary_json
    )
    with pytest.raises(
        ProposalReviewPackageError,
        match="PROPOSAL_REVIEW_PACKAGE_READ_FORBIDDEN",
    ):
        read_proposal_review_package(db, package_id=record.package_id, actor=outsider)
    assert db.scalar(
        select(AuditEvent).where(AuditEvent.action == "register_proposal_review_package")
    )


def test_redaction_hold_retention_and_delete_preserve_the_governed_boundary() -> None:
    db = _session()
    package, administrator, reviewer, _ = _package_and_bindings(db)
    record, _ = register_proposal_review_package(
        db,
        package=package,
        actor=administrator,
        registered_at=datetime(2026, 9, 3, tzinfo=UTC),
    )

    redaction, created = create_proposal_review_package_redaction(
        db,
        proposal_review_package_id=record.id,
        redacted_scope_ids=["SCOPE-001"],
        redaction_reason_code="PERSONAL_DATA",
        actor=administrator,
    )
    view = read_proposal_review_package(
        db,
        package_id=record.package_id,
        actor=reviewer,
        redaction_id=redaction.id,
    )
    assert created is True
    assert record.reviewer_summary_json["selected_defect_count"] == 2
    assert view.redaction is not None
    assert view.reviewer_summary["visible_defect_count"] == 1
    assert view.reviewer_summary["redacted_scope_ids"] == ["SCOPE-001"]

    set_proposal_review_package_legal_hold(
        db,
        proposal_review_package_id=record.id,
        active=True,
        reason_code="LEGAL_REVIEW",
        actor=administrator,
    )
    with pytest.raises(
        ProposalReviewPackageError,
        match="PROPOSAL_REVIEW_PACKAGE_LEGAL_HOLD_ACTIVE",
    ):
        delete_expired_proposal_review_package(
            db,
            proposal_review_package_id=record.id,
            actor=administrator,
            now=record.retention_until + timedelta(seconds=1),
        )
    set_proposal_review_package_legal_hold(
        db,
        proposal_review_package_id=record.id,
        active=False,
        reason_code=None,
        actor=administrator,
    )
    with pytest.raises(
        ProposalReviewPackageError,
        match="PROPOSAL_REVIEW_PACKAGE_RETENTION_ACTIVE",
    ):
        delete_expired_proposal_review_package(
            db,
            proposal_review_package_id=record.id,
            actor=administrator,
            now=record.retention_until - timedelta(seconds=1),
        )
    delete_expired_proposal_review_package(
        db,
        proposal_review_package_id=record.id,
        actor=administrator,
        now=record.retention_until + timedelta(seconds=1),
    )
    assert db.get(ProposalReviewPackage, record.id) is None
    assert db.scalar(
        select(AuditEvent).where(AuditEvent.action == "delete_expired_proposal_review_package")
    )


def test_tamper_blocks_reviewer_render_and_creates_only_safe_audit_metadata() -> None:
    db = _session()
    package, administrator, reviewer, _ = _package_and_bindings(db)
    record, _ = register_proposal_review_package(
        db,
        package=package,
        actor=administrator,
        registered_at=datetime(2026, 9, 3, tzinfo=UTC),
    )
    record.reviewer_summary_json = {
        **record.reviewer_summary_json,
        "package_id": "FORGED-PACKAGE",
    }
    db.flush()

    with pytest.raises(
        ProposalReviewPackageError, match="PROPOSAL_REVIEW_PACKAGE_TAMPERED"
    ) as error:
        read_proposal_review_package(
            db,
            package_id=record.package_id,
            actor=reviewer,
        )
    record_proposal_review_package_tamper(
        db,
        record=record,
        actor=reviewer,
        error=error.value,
    )
    audit = db.scalar(
        select(AuditEvent).where(AuditEvent.action == "reject_tampered_proposal_review_package")
    )
    assert audit is not None
    assert audit.new_value == {
        "package_id": "PACKAGE-001",
        "package_manifest_sha256": record.package_manifest_sha256,
        "error_code": "PROPOSAL_REVIEW_PACKAGE_TAMPERED",
        "proposal_only": True,
    }


def _reviewer_request(user_id: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "path": "/proposal-reviews",
            "raw_path": b"/proposal-reviews",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
            "session": {"user_id": user_id, "csrf_token": "synthetic-csrf"},
        }
    )


def test_read_only_route_renders_intact_metadata_and_blocks_tampering() -> None:
    from classifire.proposal_review_admin import (
        proposal_review_package_page,
        proposal_review_packages_page,
    )

    db = _session()
    package, administrator, reviewer, _ = _package_and_bindings(db)
    record, _ = register_proposal_review_package(
        db,
        package=package,
        actor=administrator,
        registered_at=datetime(2026, 9, 3, tzinfo=UTC),
    )
    request = _reviewer_request(reviewer.id)

    listing = proposal_review_packages_page(request, db)
    detail = proposal_review_package_page(record.package_id, request, db)
    assert b"Retained package register" in listing.body
    assert b"Proposal-only, read-only record" in detail.body
    assert record.package_manifest_sha256.encode("ascii") in detail.body

    record.safe_locator_json = {**record.safe_locator_json, "package_id": "FORGED-PACKAGE"}
    db.flush()
    with pytest.raises(HTTPException) as blocked:
        proposal_review_package_page(record.package_id, request, db)
    assert blocked.value.status_code == 409
    assert db.scalar(
        select(AuditEvent).where(AuditEvent.action == "reject_tampered_proposal_review_package")
    )
