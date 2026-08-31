from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy import func, select
from test_report_evidence_adapter import _defect, _scoped_report_packet, adapter_session

from classifire.models import Opening, ReportDefectScope, Service
from classifire.services.canonical_submission_state import initial_submission_state
from classifire.services.phase8_report_review_controller import (
    Phase8ReportReviewControllerError,
    assemble_phase8_report_review_package,
)
from classifire.services.phase8_report_review_package import (
    ReportDefectReviewOutcome,
    validate_phase8_report_review_package,
)
from classifire.services.report_evidence_adapter import bind_report_defect_scope


def test_controller_selects_every_owned_scope_and_proves_no_write() -> None:
    with adapter_session() as db:
        project, estimate, stored, first_defect, records = _scoped_report_packet(db, ordinal=51)
        second_defect = _defect(db, estimate, reference='D-002')
        page_records = tuple(record for record in records if record.page_number == 1)
        second_scope = bind_report_defect_scope(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
            defect_id=second_defect.id,
            report_defect_label='D-002',
            start_locator_key=page_records[0].locator_key,
            end_locator_key=page_records[-1].locator_key,
        )

        state = initial_submission_state(db, estimate_id=estimate.id)
        scopes = tuple(
            db.scalars(
                select(ReportDefectScope)
                .where(ReportDefectScope.project_evidence_id == second_scope.project_evidence_id)
                .order_by(ReportDefectScope.id)
            ).all()
        )
        package = assemble_phase8_report_review_package(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
            report_sha256=stored.sha256,
            expected_report_defect_labels=['D-001', 'D-002'],
            package_id='PACKAGE-REPORT-001',
            package_sha256='A' * 64,
            approval_reference='proposal-only batch assembly',
            outcomes_by_scope={
                scope.id: ReportDefectReviewOutcome(
                    no_proposal_status='RETRIEVAL_BLOCKED',
                    blocker_code='ACTIVE_VISUAL_EVIDENCE_REQUIRED',
                )
                for scope in scopes
            },
        )

        assert validate_phase8_report_review_package(package) == []
        assert [artifact.review['defect_reference'] for artifact in package.artifacts] == [
            first_defect.external_defect_id,
            second_defect.external_defect_id,
        ]
        assert all(
            artifact.review['review_status'] == 'RETRIEVAL_BLOCKED'
            for artifact in package.artifacts
        )
        assert (
            package.completion_receipt['protected_state_before']['fingerprint']
            == state.fingerprint
        )
        assert package.completion_receipt['protected_state_unchanged'] is True
        assert db.scalar(select(func.count()).select_from(Opening)) == 0
        assert db.scalar(select(func.count()).select_from(Service)) == 0


def test_controller_fails_closed_on_changed_state_or_dirty_session() -> None:
    with adapter_session() as db:
        project, estimate, stored, defect, _records = _scoped_report_packet(db, ordinal=52)
        before = initial_submission_state(db, estimate_id=estimate.id)
        changed = replace(before, fingerprint='B' * 64)
        states = iter((before, changed))

        with pytest.raises(Phase8ReportReviewControllerError) as changed_state:
            assemble_phase8_report_review_package(
                db,
                stored_file_id=stored.id,
                project_id=project.id,
                estimate_id=estimate.id,
                report_sha256=stored.sha256,
                expected_report_defect_labels=['D-001'],
                package_id='PACKAGE-REPORT-002',
                package_sha256='B' * 64,
                approval_reference='proposal-only batch assembly',
                outcomes_by_scope={
                    'unused': ReportDefectReviewOutcome(
                        no_proposal_status='RETRIEVAL_BLOCKED',
                        blocker_code='ACTIVE_VISUAL_EVIDENCE_REQUIRED',
                    )
                },
                protected_state_reader=lambda: next(states),
            )

        scope = db.scalar(
            select(ReportDefectScope).where(ReportDefectScope.defect_id == defect.id)
        )
        assert scope is not None
        states = iter((before, before, changed))
        with pytest.raises(Phase8ReportReviewControllerError) as after_package:
            assemble_phase8_report_review_package(
                db,
                stored_file_id=stored.id,
                project_id=project.id,
                estimate_id=estimate.id,
                report_sha256=stored.sha256,
                expected_report_defect_labels=['D-001'],
                package_id='PACKAGE-REPORT-004',
                package_sha256='D' * 64,
                approval_reference='proposal-only batch assembly',
                outcomes_by_scope={
                    scope.id: ReportDefectReviewOutcome(
                        no_proposal_status='RETRIEVAL_BLOCKED',
                        blocker_code='ACTIVE_VISUAL_EVIDENCE_REQUIRED',
                    )
                },
                protected_state_reader=lambda: next(states),
            )

        defect.description = 'pending caller change'
        with pytest.raises(Phase8ReportReviewControllerError) as dirty_session:
            assemble_phase8_report_review_package(
                db,
                stored_file_id=stored.id,
                project_id=project.id,
                estimate_id=estimate.id,
                report_sha256=stored.sha256,
                expected_report_defect_labels=['D-001'],
                package_id='PACKAGE-REPORT-003',
                package_sha256='C' * 64,
                approval_reference='proposal-only batch assembly',
                outcomes_by_scope={},
            )

    assert changed_state.value.code == 'REPORT_REVIEW_CONTROLLER_PROTECTED_STATE_CHANGED'
    assert after_package.value.code == 'REPORT_REVIEW_CONTROLLER_PROTECTED_STATE_CHANGED'
    assert dirty_session.value.code == 'REPORT_REVIEW_CONTROLLER_SESSION_DIRTY'


def test_controller_rejects_a_wrong_report_hash_before_package_assembly() -> None:
    with adapter_session() as db:
        project, estimate, stored, _defect, _records = _scoped_report_packet(db, ordinal=53)

        with pytest.raises(Phase8ReportReviewControllerError) as raised:
            assemble_phase8_report_review_package(
                db,
                stored_file_id=stored.id,
                project_id=project.id,
                estimate_id=estimate.id,
                report_sha256='0' * 64,
                expected_report_defect_labels=['D-001'],
                package_id='PACKAGE-REPORT-005',
                package_sha256='E' * 64,
                approval_reference='proposal-only batch assembly',
                outcomes_by_scope={},
            )

        assert db.scalar(select(func.count()).select_from(Opening)) == 0
        assert db.scalar(select(func.count()).select_from(Service)) == 0

    assert raised.value.code == 'REPORT_REVIEW_CONTROLLER_REPORT_SHA_MISMATCH'


def test_controller_rejects_missing_or_duplicate_expected_labels() -> None:
    with adapter_session() as db:
        project, estimate, stored, _first_defect, records = _scoped_report_packet(db, ordinal=54)
        second_defect = _defect(db, estimate, reference='D-002')
        page_records = tuple(record for record in records if record.page_number == 1)
        bind_report_defect_scope(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
            defect_id=second_defect.id,
            report_defect_label='D-002',
            start_locator_key=page_records[0].locator_key,
            end_locator_key=page_records[-1].locator_key,
        )

        with pytest.raises(Phase8ReportReviewControllerError) as omitted:
            assemble_phase8_report_review_package(
                db,
                stored_file_id=stored.id,
                project_id=project.id,
                estimate_id=estimate.id,
                report_sha256=stored.sha256.upper(),
                expected_report_defect_labels=['D-001'],
                package_id='PACKAGE-REPORT-006',
                package_sha256='F' * 64,
                approval_reference='proposal-only batch assembly',
                outcomes_by_scope={},
            )
        with pytest.raises(Phase8ReportReviewControllerError) as duplicate:
            assemble_phase8_report_review_package(
                db,
                stored_file_id=stored.id,
                project_id=project.id,
                estimate_id=estimate.id,
                report_sha256=stored.sha256,
                expected_report_defect_labels=['D-001', 'd-001'],
                package_id='PACKAGE-REPORT-007',
                package_sha256='1' * 64,
                approval_reference='proposal-only batch assembly',
                outcomes_by_scope={},
            )

    assert omitted.value.code == 'REPORT_REVIEW_CONTROLLER_EXPECTED_LABELS_MISMATCH'
    assert duplicate.value.code == 'REPORT_REVIEW_CONTROLLER_EXPECTED_LABELS_INVALID'
