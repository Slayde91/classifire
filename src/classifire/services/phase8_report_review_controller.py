'''Proposal-only coordination for one owned report review batch.

This boundary selects the already-bound report Defect scopes and passes their
already-determined outcomes to the inert package builder.  It cannot retrieve
reports, invoke inference, materialise files, or write canonical state.
'''

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import NoReturn

from sqlalchemy.orm import Session

from .canonical_submission_state import InitialSubmissionState, initial_submission_state
from .phase8_report_review_package import (
    Phase8ReportReviewPackage,
    build_phase8_report_review_package,
)
from .report_evidence_adapter import (
    REPORT_DEFECT_EVIDENCE_PACKET_SCHEMA_V2,
    ReportDefectEvidencePacket,
    build_report_defect_evidence_packets,
)
from .report_expected_label_manifest import (
    ApprovedReportExpectedLabelManifest,
    ReportExpectedLabelManifestError,
    require_approved_report_expected_label_manifest,
)


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


def _report_sha256(value: object) -> str:
    if not isinstance(value, str):
        _fail('REPORT_REVIEW_CONTROLLER_REPORT_SHA_INVALID')
    sha256 = value.strip().casefold()
    if (
        len(sha256) != 64
        or any(character not in '0123456789abcdef' for character in sha256)
    ):
        _fail('REPORT_REVIEW_CONTROLLER_REPORT_SHA_INVALID')
    return sha256


def _expected_report_defect_labels(value: object) -> frozenset[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail('REPORT_REVIEW_CONTROLLER_EXPECTED_LABELS_INVALID')
    labels: set[str] = set()
    for raw_label in value:
        if not isinstance(raw_label, str):
            _fail('REPORT_REVIEW_CONTROLLER_EXPECTED_LABELS_INVALID')
        label = raw_label.strip()
        if not label or len(label) > 150:
            _fail('REPORT_REVIEW_CONTROLLER_EXPECTED_LABELS_INVALID')
        normalised = label.casefold()
        if normalised in labels:
            _fail('REPORT_REVIEW_CONTROLLER_EXPECTED_LABELS_INVALID')
        labels.add(normalised)
    if not labels:
        _fail('REPORT_REVIEW_CONTROLLER_EXPECTED_LABELS_INVALID')
    return frozenset(labels)


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


def _approved_expected_label_manifest(
    db: Session,
    *,
    approved_expected_label_manifest_id: object,
    project_id: str,
    estimate_id: str,
    stored_file_id: str,
    report_sha256: str,
) -> ApprovedReportExpectedLabelManifest:
    try:
        return require_approved_report_expected_label_manifest(
            db,
            expected_label_manifest_id=approved_expected_label_manifest_id,
            project_id=project_id,
            estimate_id=estimate_id,
            stored_file_id=stored_file_id,
            report_sha256=report_sha256,
        )
    except ReportExpectedLabelManifestError as exc:
        raise Phase8ReportReviewControllerError(
            'REPORT_REVIEW_CONTROLLER_EXPECTED_LABEL_MANIFEST_INVALID'
        ) from exc


def _require_approved_scope_packets(
    packets: tuple[ReportDefectEvidencePacket, ...],
    *,
    approved_expected_label_manifest: ApprovedReportExpectedLabelManifest,
) -> None:
    expected_labels = approved_expected_label_manifest.expected_report_defect_labels
    actual_labels = tuple(
        str(packet.manifest['report_defect_label']) for packet in packets
    )
    if actual_labels != expected_labels:
        _fail('REPORT_REVIEW_CONTROLLER_EXPECTED_LABELS_MISMATCH')
    for packet in packets:
        manifest = packet.manifest
        if (
            manifest.get('schema') != REPORT_DEFECT_EVIDENCE_PACKET_SCHEMA_V2
            or manifest.get('approved_expected_label_manifest_id')
            != approved_expected_label_manifest.id
            or manifest.get('approved_expected_label_manifest_sha256')
            != approved_expected_label_manifest.manifest_sha256
            or manifest.get('approved_expected_label_manifest_approval_reference')
            != approved_expected_label_manifest.approval_reference
        ):
            _fail('REPORT_REVIEW_CONTROLLER_SCOPE_ADMISSION_INVALID')


def assemble_phase8_report_review_package(
    db: Session,
    *,
    stored_file_id: object,
    project_id: object,
    estimate_id: object,
    report_sha256: object,
    expected_report_defect_labels: object,
    package_id: object,
    package_sha256: object,
    approval_reference: object,
    outcomes_by_scope: object,
    protected_state_reader: Callable[[], InitialSubmissionState] | None = None,
    approved_expected_label_manifest_id: object = None,
) -> Phase8ReportReviewPackage:
    '''Assemble one owned report review package only from an approved scope admission.'''

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
    expected_report_sha256 = _report_sha256(report_sha256)
    expected_labels = _expected_report_defect_labels(expected_report_defect_labels)
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
        actual_report_sha256 = str(packets[0].manifest['report_sha256'])
        if actual_report_sha256 != expected_report_sha256:
            _fail('REPORT_REVIEW_CONTROLLER_REPORT_SHA_MISMATCH')
        actual_labels = frozenset(
            str(packet.manifest['report_defect_label']).casefold()
            for packet in packets
        )
        if actual_labels != expected_labels:
            _fail('REPORT_REVIEW_CONTROLLER_EXPECTED_LABELS_MISMATCH')
        approved_expected_label_manifest = _approved_expected_label_manifest(
            db,
            approved_expected_label_manifest_id=approved_expected_label_manifest_id,
            project_id=selected_project_id,
            estimate_id=selected_estimate_id,
            stored_file_id=selected_stored_file_id,
            report_sha256=expected_report_sha256,
        )
        if frozenset(
            label.casefold()
            for label in approved_expected_label_manifest.expected_report_defect_labels
        ) != expected_labels:
            _fail('REPORT_REVIEW_CONTROLLER_EXPECTED_LABELS_MISMATCH')
        _require_approved_scope_packets(
            packets,
            approved_expected_label_manifest=approved_expected_label_manifest,
        )
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
