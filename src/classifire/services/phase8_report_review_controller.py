'''Proposal-only coordination for one owned report review batch.

This boundary selects the already-bound report Defect scopes and passes their
already-determined outcomes to the inert package builder.  It cannot retrieve
reports, invoke inference, materialise files, or write canonical state.
'''

from __future__ import annotations

from collections.abc import Callable
from typing import NoReturn

from sqlalchemy.orm import Session

from .canonical_submission_state import InitialSubmissionState, initial_submission_state
from .phase8_report_review_package import (
    Phase8ReportReviewPackage,
    build_phase8_report_review_package,
)
from .report_evidence_adapter import build_report_defect_evidence_packets


class Phase8ReportReviewControllerError(RuntimeError):
    '''A stable failure while assembling a proposal-only report review batch.'''

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise Phase8ReportReviewControllerError(code)


def _identifier(value: object, *, code: str) -> str:
    if not isinstance(value, str):
        _fail(code)
    identifier = value.strip()
    if not identifier or len(identifier) > 36:
        _fail(code)
    return identifier


def _require_clean_session(db: Session) -> None:
    if db.new or db.dirty or db.deleted:
        _fail('REPORT_REVIEW_CONTROLLER_SESSION_DIRTY')


def _state(
    reader: Callable[[], InitialSubmissionState],
    *,
    estimate_id: str,
) -> InitialSubmissionState:
    try:
        state = reader()
    except Exception as exc:
        raise Phase8ReportReviewControllerError(
            'REPORT_REVIEW_CONTROLLER_PROTECTED_STATE_UNAVAILABLE'
        ) from exc
    if not isinstance(state, InitialSubmissionState) or state.estimate_id != estimate_id:
        _fail('REPORT_REVIEW_CONTROLLER_PROTECTED_STATE_INVALID')
    return state


def assemble_phase8_report_review_package(
    db: Session,
    *,
    stored_file_id: object,
    project_id: object,
    estimate_id: object,
    package_id: object,
    package_sha256: object,
    approval_reference: object,
    outcomes_by_scope: object,
    protected_state_reader: Callable[[], InitialSubmissionState] | None = None,
) -> Phase8ReportReviewPackage:
    '''Assemble one owned report review package without retrieval, inference, or writes.'''

    if not isinstance(db, Session):
        _fail('REPORT_REVIEW_CONTROLLER_SESSION_INVALID')
    selected_stored_file_id = _identifier(
        stored_file_id,
        code='REPORT_REVIEW_CONTROLLER_STORED_FILE_INVALID',
    )
    selected_project_id = _identifier(
        project_id,
        code='REPORT_REVIEW_CONTROLLER_PROJECT_INVALID',
    )
    selected_estimate_id = _identifier(
        estimate_id,
        code='REPORT_REVIEW_CONTROLLER_ESTIMATE_INVALID',
    )
    _require_clean_session(db)
    if protected_state_reader is None:

        def protected_state_reader() -> InitialSubmissionState:
            return initial_submission_state(db, estimate_id=selected_estimate_id)

    with db.no_autoflush:
        before = _state(protected_state_reader, estimate_id=selected_estimate_id)
        packets = build_report_defect_evidence_packets(
            db,
            stored_file_id=selected_stored_file_id,
            project_id=selected_project_id,
            estimate_id=selected_estimate_id,
        )
        _require_clean_session(db)
        after_selection = _state(protected_state_reader, estimate_id=selected_estimate_id)
        if after_selection != before:
            _fail('REPORT_REVIEW_CONTROLLER_PROTECTED_STATE_CHANGED')
        package = build_phase8_report_review_package(
            package_id=package_id,
            package_sha256=package_sha256,
            approval_reference=approval_reference,
            packets=packets,
            outcomes_by_scope=outcomes_by_scope,
            protected_state_before=before,
            protected_state_after=after_selection,
        )
        _require_clean_session(db)
        after_package = _state(protected_state_reader, estimate_id=selected_estimate_id)
    if after_package != before:
        _fail('REPORT_REVIEW_CONTROLLER_PROTECTED_STATE_CHANGED')
    return package


__all__ = [
    'Phase8ReportReviewControllerError',
    'assemble_phase8_report_review_package',
]
