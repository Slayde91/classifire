from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from starlette.requests import Request
from test_phase8_report_evidence_family_review_package import (
    _approved_family_with_packages,
    _build,
)
from test_report_evidence_adapter import adapter_session

from classifire.models import AuditEvent, ReportEvidenceFamilyManifest, User
from classifire.services.proposal_review_package import (
    PROPOSAL_REVIEW_PACKAGE_FAMILY_RECORD_SCHEMA,
    PROPOSAL_REVIEW_PACKAGE_FAMILY_SAFE_LOCATOR_SCHEMA,
    PROPOSAL_REVIEW_PACKAGE_KIND_REPORT_EVIDENCE_FAMILY,
    ProposalReviewPackageError,
    create_proposal_review_package_redaction,
    grant_proposal_review_reader_assignment,
    list_proposal_review_packages,
    read_proposal_review_package,
    register_proposal_review_package,
)


def _administrator(db) -> User:  # type: ignore[no-untyped-def]
    actor = User(
        email="family-package-administrator@example.test",
        full_name="Family package administrator",
        password_hash="not-used-by-synthetic-tests",  # noqa: S106
        role="administrator",
    )
    db.add(actor)
    db.flush()
    return actor


def _reader(db) -> User:  # type: ignore[no-untyped-def]
    actor = User(
        email="family-package-reader@example.test",
        full_name="Family package reader",
        password_hash="not-used-by-synthetic-tests",  # noqa: S106
        role="technical_reviewer",
    )
    db.add(actor)
    db.flush()
    return actor


def _family_package(db):  # type: ignore[no-untyped-def]
    (
        project,
        estimate,
        first_stored,
        first_package,
        second_stored,
        second_package,
        family,
        state,
    ) = _approved_family_with_packages(db)
    package = _build(
        db,
        project=project,
        estimate=estimate,
        first_stored=first_stored,
        first_package=first_package,
        second_stored=second_stored,
        second_package=second_package,
        family=family,
        state=state,
    )
    return package, project, family


def test_registers_approved_family_as_read_only_hash_bound_metadata() -> None:
    with adapter_session() as db:
        package, project, family = _family_package(db)
        administrator = _administrator(db)
        reader = _reader(db)

        record, created = register_proposal_review_package(
            db,
            package=package,
            actor=administrator,
            registered_at=datetime(2026, 9, 4, 8, 0, tzinfo=UTC),
        )
        replay, replay_created = register_proposal_review_package(
            db,
            package=package,
            actor=administrator,
            registered_at=datetime(2026, 9, 5, 8, 0, tzinfo=UTC),
        )

        assert created is True
        assert replay_created is False
        assert replay.id == record.id
        assert record.package_kind == PROPOSAL_REVIEW_PACKAGE_KIND_REPORT_EVIDENCE_FAMILY
        assert record.project_evidence_id is None
        assert record.report_sha256 is None
        assert record.approved_expected_label_manifest_id is None
        assert record.report_evidence_family_manifest_id == family.id
        assert (
            record.reviewer_summary_json["schema"] == PROPOSAL_REVIEW_PACKAGE_FAMILY_RECORD_SCHEMA
        )
        assert record.reviewer_summary_json["member_count"] == 2
        assert record.reviewer_summary_json["selected_defect_count"] == 2
        assert [
            member["project_evidence_id"] for member in record.reviewer_summary_json["members"]
        ] == [artifact.member.project_evidence_id for artifact in package.artifacts]
        assert [
            outcome["member_sequence"] for outcome in record.reviewer_summary_json["outcomes"]
        ] == [1, 2]
        assert (
            record.safe_locator_json["schema"] == PROPOSAL_REVIEW_PACKAGE_FAMILY_SAFE_LOCATOR_SCHEMA
        )
        assert record.safe_locator_json["report_evidence_family_manifest_id"] == family.id
        assert "storage_path" not in str(record.reviewer_summary_json)
        assert "storage_path" not in str(record.safe_locator_json)

        grant_proposal_review_reader_assignment(
            db,
            user_id=reader.id,
            project_id=project.id,
            reason_code="CONTROLLED_UAT",
            actor=administrator,
        )
        view = read_proposal_review_package(db, package_id=record.package_id, actor=reader)
        assert view.record.id == record.id
        assert view.reviewer_summary == record.reviewer_summary_json
        assert list_proposal_review_packages(db, actor=reader) == (record,)
        assert db.scalar(
            select(AuditEvent).where(AuditEvent.action == "register_proposal_review_package")
        )


def test_family_record_redaction_and_integrity_refusal_keep_member_sources_separate() -> None:
    with adapter_session() as db:
        package, project, family = _family_package(db)
        administrator = _administrator(db)
        reader = _reader(db)
        record, _ = register_proposal_review_package(
            db,
            package=package,
            actor=administrator,
            registered_at=datetime(2026, 9, 4, 8, 0, tzinfo=UTC),
        )
        grant_proposal_review_reader_assignment(
            db,
            user_id=reader.id,
            project_id=project.id,
            reason_code="CONTROLLED_UAT",
            actor=administrator,
        )
        redaction, created = create_proposal_review_package_redaction(
            db,
            proposal_review_package_id=record.id,
            redacted_scope_ids=[record.reviewer_summary_json["outcomes"][0]["scope_id"]],
            redaction_reason_code="PERSONAL_DATA",
            actor=administrator,
        )
        redacted_view = read_proposal_review_package(
            db,
            package_id=record.package_id,
            actor=reader,
            redaction_id=redaction.id,
        )
        assert created is True
        assert redacted_view.reviewer_summary["visible_defect_count"] == 1
        assert redacted_view.reviewer_summary["outcomes"][0]["member_sequence"] == 2

        family_record = db.get(ReportEvidenceFamilyManifest, family.id)
        assert family_record is not None
        family_record.manifest_sha256 = "0" * 64
        db.flush()
        with pytest.raises(
            ProposalReviewPackageError,
            match="PROPOSAL_REVIEW_PACKAGE_TAMPERED",
        ):
            read_proposal_review_package(db, package_id=record.package_id, actor=reader)


def _reviewer_request(user_id: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/proposal-reviews",
            "query_string": b"",
            "headers": [],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "session": {"user_id": user_id, "csrf_token": "synthetic-csrf"},
        }
    )


def test_read_only_reviewer_ui_keeps_family_members_visible_and_separate() -> None:
    from classifire.proposal_review_admin import (
        proposal_review_package_page,
        proposal_review_packages_page,
    )

    with adapter_session() as db:
        package, project, family = _family_package(db)
        administrator = _administrator(db)
        reader = _reader(db)
        record, _ = register_proposal_review_package(
            db,
            package=package,
            actor=administrator,
            registered_at=datetime(2026, 9, 4, 8, 0, tzinfo=UTC),
        )
        grant_proposal_review_reader_assignment(
            db,
            user_id=reader.id,
            project_id=project.id,
            reason_code="CONTROLLED_UAT",
            actor=administrator,
        )

        request = _reviewer_request(reader.id)
        listing = proposal_review_packages_page(request, db)
        detail = proposal_review_package_page(record.package_id, request, db)

        assert b"Approved report family" in listing.body
        assert b"Family member" in detail.body
        assert b"Report family manifest" in detail.body
        assert family.id.encode("ascii") in detail.body