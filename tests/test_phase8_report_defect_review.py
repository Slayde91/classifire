from __future__ import annotations

from copy import deepcopy

import pytest
from test_phase8_proposal_review import _review_inputs
from test_phase8_visual_proposal import _proposal

from classifire.services.phase8_proposal_review import (
    Phase8ProposalReviewError,
    build_phase8_proposal_review,
)
from classifire.services.phase8_report_defect_review import (
    PHASE8_REPORT_DEFECT_REVIEW_SCHEMA,
    Phase8ReportDefectReviewError,
    build_phase8_report_defect_review,
    render_phase8_report_defect_review_markdown,
    validate_phase8_report_defect_review,
)
from classifire.services.phase8_visual_proposal import canonical_json_sha256
from classifire.services.report_evidence_adapter import (
    REPORT_DEFECT_EVIDENCE_PACKET_SCHEMA,
    ReportDefectEvidencePacket,
)


def _packet() -> ReportDefectEvidencePacket:
    manifest = {
        'schema': REPORT_DEFECT_EVIDENCE_PACKET_SCHEMA,
        'project_evidence_id': 'PROJECT-EVIDENCE-001',
        'report_sha256': 'a' * 64,
        'source_size_bytes': 1,
        'estimate_id': 'EST-001',
        'defect_id': 'DEFECT-001',
        'defect_reference': 'D-001',
        'report_defect_label': 'D-001',
        'scope_id': 'SCOPE-001',
        'start_locator_key': 'report-locator-001',
        'end_locator_key': 'report-locator-001',
        'artifacts': [
            {
                'evidence_id': 'report-locator:report-locator-001',
                'sequence': 1,
                'locator_key': 'report-locator-001',
                'item_kind': 'text',
                'page_number': 1,
                'content_sha256': 'b' * 64,
                'locator': {
                    'item_kind': 'text',
                    'page_number': 1,
                    'bounds': {'x0': 0.0, 'y0': 0.0, 'x1': 1.0, 'y1': 1.0},
                    'character_count': 1,
                    'text_role': 'unclassified',
                    'block_index': 1,
                    'sequence': 1,
                },
            }
        ],
    }
    return ReportDefectEvidencePacket(
        manifest=manifest,
        manifest_sha256=canonical_json_sha256(manifest),
    )


def test_report_defect_review_binds_a_valid_phase8_review_without_copying_content() -> None:
    packet = _packet()
    phase8_review = build_phase8_proposal_review(
        **_review_inputs(_proposal()),
        documentary_evidence_packet=packet,
    )

    review = build_phase8_report_defect_review(
        packet=packet,
        phase8_proposal_review=phase8_review,
    )
    markdown = render_phase8_report_defect_review_markdown(review)

    assert review['schema'] == PHASE8_REPORT_DEFECT_REVIEW_SCHEMA
    assert review['review_status'] == 'PHASE8_REVIEW_AVAILABLE'
    assert (
        review['report_packet_manifest_sha256']
        == canonical_json_sha256(packet.manifest)
    )
    assert (
        review['phase8_review_binding']['phase8_proposal_review_canonical_sha256']
        == canonical_json_sha256(phase8_review)
    )
    assert review['phase8_review_binding']['phase8_review_status'] == 'ASSESSMENT_AVAILABLE'
    assert (
        review['phase8_review_binding']['documentary_packet_canonical_sha256']
        == canonical_json_sha256(packet.manifest)
    )
    assert review['blocker_code'] is None
    assert validate_phase8_report_defect_review(review) == []
    assert '# CLASSIFIRE report Defect proposal-only review' in markdown
    assert 'Bound Phase 8 review' in markdown
    assert '100 mm' not in markdown
    assert all(
        review[field] is False
        for field in (
            'canonical_submission_performed',
            'technical_selection_performed',
            'commercial_pricing_performed',
            'physical_model_lock_created',
            'human_release_performed',
        )
    )


@pytest.mark.parametrize(
    ('status', 'code'),
    [
        ('RETRIEVAL_BLOCKED', 'ACTIVE_VISUAL_EVIDENCE_REQUIRED'),
        ('MALFORMED_INPUT', 'REPORT_EVIDENCE_PACKET_INVALID'),
    ],
)
def test_report_defect_review_records_only_safe_no_proposal_outcomes(
    status: str,
    code: str,
) -> None:
    review = build_phase8_report_defect_review(
        packet=_packet(),
        no_proposal_status=status,
        blocker_code=code,
    )

    assert review['review_status'] == status
    assert review['blocker_code'] == code
    assert all(value is None for value in review['phase8_review_binding'].values())
    assert validate_phase8_report_defect_review(review) == []
    markdown = render_phase8_report_defect_review_markdown(review)
    assert code.replace('_', '\\_') in markdown
    assert 'No physical conclusion has been created' in markdown


def test_report_defect_review_rejects_unbound_assessment_statuses_and_tampering() -> None:
    packet = _packet()
    phase8_review = build_phase8_proposal_review(**_review_inputs(_proposal()))

    with pytest.raises(
        Phase8ReportDefectReviewError,
        match='REPORT_DEFECT_REVIEW_DOCUMENTARY_BINDING_INVALID',
    ):
        build_phase8_report_defect_review(
            packet=packet,
            phase8_proposal_review=phase8_review,
        )
    phase8_review = build_phase8_proposal_review(
        **_review_inputs(_proposal()),
        documentary_evidence_packet=packet,
    )

    with pytest.raises(
        Phase8ReportDefectReviewError,
        match='REPORT_DEFECT_REVIEW_NO_PROPOSAL_INVALID',
    ):
        build_phase8_report_defect_review(
            packet=packet,
            no_proposal_status='INSUFFICIENT_EVIDENCE',
            blocker_code='NOT_ENOUGH_EVIDENCE',
        )

    mismatched_manifest = deepcopy(packet.manifest)
    mismatched_manifest['defect_reference'] = 'D-OTHER'
    mismatched_packet = ReportDefectEvidencePacket(
        manifest=mismatched_manifest,
        manifest_sha256=canonical_json_sha256(mismatched_manifest),
    )
    with pytest.raises(
        Phase8ProposalReviewError,
        match='PROPOSAL_REVIEW_REPORT_PACKET_SCOPE_MISMATCH',
    ):
        build_phase8_proposal_review(
            **_review_inputs(_proposal()),
            documentary_evidence_packet=mismatched_packet,
        )
    with pytest.raises(
        Phase8ReportDefectReviewError,
        match='REPORT_DEFECT_REVIEW_PHASE8_SCOPE_MISMATCH',
    ):
        build_phase8_report_defect_review(
            packet=mismatched_packet,
            phase8_proposal_review=phase8_review,
        )

    different_scope_manifest = deepcopy(packet.manifest)
    different_scope_manifest['scope_id'] = 'SCOPE-OTHER'
    different_scope_packet = ReportDefectEvidencePacket(
        manifest=different_scope_manifest,
        manifest_sha256=canonical_json_sha256(different_scope_manifest),
    )
    wrong_scope_review = build_phase8_proposal_review(
        **_review_inputs(_proposal()),
        documentary_evidence_packet=different_scope_packet,
    )
    with pytest.raises(
        Phase8ReportDefectReviewError,
        match='REPORT_DEFECT_REVIEW_DOCUMENTARY_BINDING_INVALID',
    ):
        build_phase8_report_defect_review(
            packet=packet,
            phase8_proposal_review=wrong_scope_review,
        )

    no_proposal = build_phase8_report_defect_review(
        packet=packet,
        no_proposal_status='RETRIEVAL_BLOCKED',
        blocker_code='ACTIVE_VISUAL_EVIDENCE_REQUIRED',
    )
    no_proposal['phase8_review_binding']['controller_receipt_file_sha256'] = 'A' * 64
    no_proposal_errors = validate_phase8_report_defect_review(no_proposal)
    assert any('must not bind a Phase 8 review' in error for error in no_proposal_errors)

    forged = build_phase8_report_defect_review(
        packet=packet,
        phase8_proposal_review=phase8_review,
    )
    forged = deepcopy(forged)
    forged['phase8_review_binding']['controller_receipt_file_sha256'] = 'not-a-hash'

    errors = validate_phase8_report_defect_review(forged)

    assert any('binding controller_receipt_file_sha256 is invalid' in error for error in errors)
    with pytest.raises(
        Phase8ReportDefectReviewError,
        match='REPORT_DEFECT_REVIEW_RENDER_INVALID',
    ):
        render_phase8_report_defect_review_markdown(forged)


def test_report_defect_review_carries_insufficient_evidence_only_from_bound_review() -> None:
    proposal = _proposal()
    proposal['status'] = 'INSUFFICIENT_EVIDENCE'
    proposal['limitations'] = ['The selected images do not show the opposite face.']
    proposal['openings'] = []
    proposal['services'] = []
    phase8_review = build_phase8_proposal_review(
        **_review_inputs(proposal),
        documentary_evidence_packet=_packet(),
    )

    review = build_phase8_report_defect_review(
        packet=_packet(),
        phase8_proposal_review=phase8_review,
    )

    assert phase8_review['review_status'] == 'INSUFFICIENT_EVIDENCE'
    assert review['review_status'] == 'PHASE8_REVIEW_AVAILABLE'
    assert review['phase8_review_binding']['phase8_review_status'] == 'INSUFFICIENT_EVIDENCE'
    assert validate_phase8_report_defect_review(review) == []
