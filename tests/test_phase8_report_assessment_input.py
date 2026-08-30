from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from test_phase8_proposal_review import _manifest
from test_phase8_report_defect_review import _packet

from classifire.services.phase8_report_assessment_input import (
    Phase8ReportAssessmentInputError,
    build_phase8_report_assessment_input,
    validate_phase8_report_assessment_input,
)
from classifire.services.phase8_visual_evidence import (
    RetainedVisualEvidenceFile,
    RetainedVisualEvidencePacket,
)
from classifire.services.phase8_visual_proposal import canonical_json_sha256


def _visual_packet(*, defect_reference: str = 'D-001') -> RetainedVisualEvidencePacket:
    manifest = _manifest()
    manifest['defect_reference'] = defect_reference
    artifact = manifest['artifacts'][0]
    return RetainedVisualEvidencePacket(
        manifest=manifest,
        files=(
            RetainedVisualEvidenceFile(
                evidence_id=artifact['evidence_id'],
                path=Path('retained/visual-evidence.jpg'),
                sha256=artifact['sha256'],
                size_bytes=artifact['size_bytes'],
                media_type=artifact['media_type'],
            ),
        ),
    )


def test_combined_input_is_deterministic_content_free_and_no_run() -> None:
    report = _packet()
    visual = _visual_packet()

    first = build_phase8_report_assessment_input(
        report_packet=report,
        visual_packet=visual,
    )
    repeated = build_phase8_report_assessment_input(
        report_packet=report,
        visual_packet=visual,
    )

    assert validate_phase8_report_assessment_input(first) == []
    assert first.manifest == repeated.manifest
    assert first.manifest_sha256 == repeated.manifest_sha256
    assert first.allowed_evidence_refs == {
        'E-001',
        'report-locator:report-locator-001',
    }
    assert first.manifest['documentary_evidence_refs'] == [
        'report-locator:report-locator-001'
    ]
    assert first.manifest['visual_evidence_refs'] == ['E-001']
    assert first.manifest['runtime_inference_performed'] is False
    assert all(
        first.manifest[field] is False
        for field in (
            'canonical_submission_performed',
            'technical_selection_performed',
            'commercial_pricing_performed',
            'physical_model_lock_created',
            'human_release_performed',
        )
    )
    rendered = str(first.manifest)
    assert 'Private report heading' not in rendered
    assert 'retained/visual-evidence.jpg' not in rendered


def test_combined_input_rejects_scope_collision_and_tampering() -> None:
    report = _packet()

    with pytest.raises(Phase8ReportAssessmentInputError) as wrong_defect:
        build_phase8_report_assessment_input(
            report_packet=report,
            visual_packet=_visual_packet(defect_reference='D-OTHER'),
        )

    visual = _visual_packet()
    bad_file = replace(visual.files[0], sha256='F' * 64)
    with pytest.raises(Phase8ReportAssessmentInputError) as bad_visual_file:
        build_phase8_report_assessment_input(
            report_packet=report,
            visual_packet=replace(visual, files=(bad_file,)),
        )

    combined = build_phase8_report_assessment_input(
        report_packet=report,
        visual_packet=visual,
    )
    forged_manifest = deepcopy(combined.manifest)
    forged_manifest['allowed_evidence_refs'] = ['E-001']
    forged = replace(
        combined,
        manifest=forged_manifest,
        manifest_sha256=canonical_json_sha256(forged_manifest),
    )

    errors = validate_phase8_report_assessment_input(forged)
    malformed = replace(
        combined,
        manifest={'unsupported': object()},
        manifest_sha256='A' * 64,
    )
    malformed_errors = validate_phase8_report_assessment_input(malformed)

    assert wrong_defect.value.code == 'REPORT_ASSESSMENT_VISUAL_SCOPE_MISMATCH'
    assert bad_visual_file.value.code == 'REPORT_ASSESSMENT_VISUAL_PACKET_INVALID'
    assert any('not source-bound' in error for error in errors)
    assert any('not canonical JSON' in error for error in malformed_errors)
