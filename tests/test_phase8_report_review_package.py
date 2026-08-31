from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace

import pytest
from test_phase8_proposal_review import _review_inputs, _state
from test_phase8_report_defect_review import _packet
from test_phase8_visual_proposal import _proposal

from classifire.services.phase8_proposal_review import build_phase8_proposal_review
from classifire.services.phase8_report_review_package import (
    REPORT_EXPECTED_LABEL_MANIFEST_SCHEMA,
    Phase8ReportReviewPackageError,
    ReportDefectReviewOutcome,
    build_phase8_report_review_package,
    materialise_phase8_report_review_package,
    validate_phase8_report_review_package,
)
from classifire.services.phase8_visual_proposal import canonical_json_sha256
from classifire.services.report_evidence_adapter import ReportDefectEvidencePacket


def _packet_for(
    *,
    defect_id: str,
    defect_reference: str,
    report_label: str,
    scope_id: str,
) -> ReportDefectEvidencePacket:
    packet = _packet()
    manifest = deepcopy(packet.manifest)
    manifest.update(
        {
            'defect_id': defect_id,
            'defect_reference': defect_reference,
            'report_defect_label': report_label,
            'scope_id': scope_id,
        }
    )
    return ReportDefectEvidencePacket(
        manifest=manifest,
        manifest_sha256=canonical_json_sha256(manifest),
    )


def _phase8_review(packet: ReportDefectEvidencePacket) -> dict[str, object]:
    return build_phase8_proposal_review(
        **_review_inputs(_proposal()),
        documentary_evidence_packet=packet,
    )


def _expected_label_manifest_file(
    packet: ReportDefectEvidencePacket,
    *,
    labels: list[str] | None = None,
) -> bytes:
    manifest = packet.manifest
    return (
        json.dumps(
            {
                'schema': REPORT_EXPECTED_LABEL_MANIFEST_SCHEMA,
                'project_evidence_id': manifest['project_evidence_id'],
                'report_sha256': manifest['report_sha256'],
                'estimate_id': manifest['estimate_id'],
                'package_id': 'PACKAGE-001',
                'package_sha256': '9' * 64,
                'approval_reference': 'proposal-only approval',
                'expected_report_defect_labels': (
                    labels if labels is not None else [manifest['report_defect_label']]
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + '\n'
    ).encode('utf-8')


def _package(
    *,
    packets: list[ReportDefectEvidencePacket] | None = None,
    outcomes: dict[str, ReportDefectReviewOutcome] | None = None,
    before_fingerprint: str = 'A' * 64,
    after_fingerprint: str = 'A' * 64,
    package_id: str = 'PACKAGE-001',
    expected_label_manifest_file_bytes: bytes | None = None,
) -> object:
    first = _packet_for(
        defect_id='DEFECT-001',
        defect_reference='D-001',
        report_label='D-001',
        scope_id='SCOPE-001',
    )
    second = _packet_for(
        defect_id='DEFECT-002',
        defect_reference='D-002',
        report_label='D-002',
        scope_id='SCOPE-002',
    )
    selected_packets = packets or [second, first]
    selected_outcomes = outcomes or {
        'SCOPE-001': ReportDefectReviewOutcome(phase8_proposal_review=_phase8_review(first)),
        'SCOPE-002': ReportDefectReviewOutcome(
            no_proposal_status='RETRIEVAL_BLOCKED',
            blocker_code='ACTIVE_VISUAL_EVIDENCE_REQUIRED',
        ),
    }
    return build_phase8_report_review_package(
        package_id=package_id,
        package_sha256='9' * 64,
        approval_reference='proposal-only approval',
        packets=selected_packets,
        outcomes_by_scope=selected_outcomes,
        protected_state_before=replace(_state(), fingerprint=before_fingerprint),
        protected_state_after=replace(_state(), fingerprint=after_fingerprint),
        expected_label_manifest_file_bytes=expected_label_manifest_file_bytes,
    )


def test_package_emits_one_deterministic_artifact_per_selected_scope() -> None:
    first = _packet_for(
        defect_id='DEFECT-001',
        defect_reference='D-001',
        report_label='D-001',
        scope_id='SCOPE-001',
    )
    second = _packet_for(
        defect_id='DEFECT-002',
        defect_reference='D-002',
        report_label='D-002',
        scope_id='SCOPE-002',
    )
    outcomes = {
        'SCOPE-001': ReportDefectReviewOutcome(phase8_proposal_review=_phase8_review(first)),
        'SCOPE-002': ReportDefectReviewOutcome(
            no_proposal_status='RETRIEVAL_BLOCKED',
            blocker_code='ACTIVE_VISUAL_EVIDENCE_REQUIRED',
        ),
    }
    package = _package(packets=[second, first], outcomes=outcomes)
    reordered = _package(packets=[first, second], outcomes=outcomes)

    assert validate_phase8_report_review_package(package) == []
    assert package.manifest['selected_defect_count'] == 2
    assert [artifact.review['defect_reference'] for artifact in package.artifacts] == [
        'D-001',
        'D-002',
    ]
    assert [artifact.review['review_status'] for artifact in package.artifacts] == [
        'PHASE8_REVIEW_AVAILABLE',
        'RETRIEVAL_BLOCKED',
    ]
    assert package.files == reordered.files
    assert package.completion_receipt == reordered.completion_receipt
    assert list(package.files) == [
        'report-review-package.json',
        'report-defect-packets/0001.json',
        'report-defect-reviews/0001.json',
        'report-defect-reviews/0001.md',
        'report-defect-packets/0002.json',
        'report-defect-reviews/0002.json',
        'report-defect-reviews/0002.md',
        'completion-receipt.json',
    ]
    receipt = package.completion_receipt
    assert receipt['protected_state_unchanged'] is True
    assert receipt['artifacts'] == {
        path: hashlib.sha256(value).hexdigest().upper()
        for path, value in package.files.items()
        if path != 'completion-receipt.json'
    }
    assert receipt['reviews'][0]['phase8_review_status'] == 'ASSESSMENT_AVAILABLE'
    assert receipt['reviews'][1]['phase8_review_status'] is None
    binding = package.artifacts[0].review['phase8_review_binding']
    assert binding['package_id'] == package.manifest['package_id']
    assert binding['package_sha256'] == package.manifest['package_sha256']
    assert binding['approval_reference'] == package.manifest['approval_reference']
    assert package.completion_receipt_file_sha256 == hashlib.sha256(
        package.files['completion-receipt.json']
    ).hexdigest().upper()
    assert b'100 mm' not in package.files['report-defect-reviews/0001.md']


def test_package_rejects_missing_duplicate_cross_package_and_changed_state() -> None:
    first = _packet_for(
        defect_id='DEFECT-001',
        defect_reference='D-001',
        report_label='D-001',
        scope_id='SCOPE-001',
    )
    phase8_review = _phase8_review(first)

    with pytest.raises(
        Phase8ReportReviewPackageError,
        match='REPORT_REVIEW_PACKAGE_OUTCOMES_SCOPE_MISMATCH',
    ):
        _package(packets=[first], outcomes={})

    with pytest.raises(
        Phase8ReportReviewPackageError,
        match='REPORT_REVIEW_PACKAGE_PACKET_SCOPE_DUPLICATE',
    ):
        _package(
            packets=[first, first],
            outcomes={
                'SCOPE-001': ReportDefectReviewOutcome(
                    phase8_proposal_review=phase8_review
                )
            },
        )

    with pytest.raises(
        Phase8ReportReviewPackageError,
        match='REPORT_REVIEW_PACKAGE_PHASE8_PACKAGE_MISMATCH',
    ):
        _package(
            packets=[first],
            outcomes={
                'SCOPE-001': ReportDefectReviewOutcome(
                    phase8_proposal_review=phase8_review
                )
            },
            package_id='OTHER-PACKAGE',
        )

    with pytest.raises(
        Phase8ReportReviewPackageError,
        match='REPORT_REVIEW_PACKAGE_PROTECTED_STATE_CHANGED',
    ):
        _package(
            packets=[first],
            outcomes={
                'SCOPE-001': ReportDefectReviewOutcome(
                    phase8_proposal_review=phase8_review
                )
            },
            after_fingerprint='B' * 64,
        )


def test_package_validator_detects_tampered_preceding_artifact_bytes() -> None:
    package = _package()
    files = dict(package.files)
    files['report-defect-reviews/0002.md'] += b' '
    forged = replace(package, files=files)

    errors = validate_phase8_report_review_package(forged)

    assert any('file bytes are invalid' in error for error in errors)


def test_package_binds_and_hashes_expected_label_manifest_without_changing_history() -> None:
    first = _packet_for(
        defect_id='DEFECT-001',
        defect_reference='D-001',
        report_label='D-001',
        scope_id='SCOPE-001',
    )
    outcomes = {
        'SCOPE-001': ReportDefectReviewOutcome(phase8_proposal_review=_phase8_review(first))
    }
    historical = _package(packets=[first], outcomes=outcomes)
    expected_label_manifest_file_bytes = _expected_label_manifest_file(first)
    package = _package(
        packets=[first],
        outcomes=outcomes,
        expected_label_manifest_file_bytes=expected_label_manifest_file_bytes,
    )

    assert validate_phase8_report_review_package(historical) == []
    assert 'expected-report-defect-labels.json' not in historical.files
    assert validate_phase8_report_review_package(package) == []
    assert package.files['expected-report-defect-labels.json'] == expected_label_manifest_file_bytes
    assert (
        package.completion_receipt['artifacts']['expected-report-defect-labels.json']
        == hashlib.sha256(expected_label_manifest_file_bytes).hexdigest().upper()
    )

    files = dict(package.files)
    files['expected-report-defect-labels.json'] += b' '
    errors = validate_phase8_report_review_package(replace(package, files=files))
    assert any('file bytes are invalid' in error for error in errors)

    with pytest.raises(
        Phase8ReportReviewPackageError,
        match='REPORT_REVIEW_PACKAGE_EXPECTED_LABEL_MANIFEST_INVALID',
    ):
        _package(
            packets=[first],
            outcomes=outcomes,
            expected_label_manifest_file_bytes=_expected_label_manifest_file(
                first,
                labels=['D-002'],
            ),
        )


def test_package_materialises_exact_files_without_overwriting_output(tmp_path) -> None:
    package = _package()
    output = tmp_path / 'report-review-output'

    completion_sha256 = materialise_phase8_report_review_package(package, output=output)

    assert completion_sha256 == package.completion_receipt_file_sha256
    assert {
        path.relative_to(output).as_posix(): path.read_bytes()
        for path in output.rglob('*')
        if path.is_file()
    } == package.files
    with pytest.raises(
        Phase8ReportReviewPackageError,
        match='REPORT_REVIEW_PACKAGE_OUTPUT_EXISTS',
    ):
        materialise_phase8_report_review_package(package, output=output)
