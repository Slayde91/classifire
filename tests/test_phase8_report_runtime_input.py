from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from test_phase8_report_documentary_context import _packet
from test_report_evidence_adapter import _report_content

from classifire.services.phase8_report_assessment_input import (
    build_phase8_report_assessment_input,
)
from classifire.services.phase8_report_documentary_context import (
    build_phase8_report_documentary_context,
)
from classifire.services.phase8_report_runtime_input import (
    PHASE8_REPORT_RUNTIME_INPUT_SCHEMA,
    Phase8ReportRuntimeInputError,
    build_phase8_report_runtime_input,
    validate_phase8_report_runtime_input,
)
from classifire.services.phase8_visual_evidence import (
    RetainedVisualEvidenceFile,
    RetainedVisualEvidencePacket,
)
from classifire.services.phase8_visual_proposal import (
    VISUAL_EVIDENCE_MANIFEST_SCHEMA,
    canonical_json_sha256,
)


def _visual_packet() -> RetainedVisualEvidencePacket:
    manifest = {
        'schema': VISUAL_EVIDENCE_MANIFEST_SCHEMA,
        'estimate_id': 'ESTIMATE-001',
        'defect_reference': 'D-001',
        'human_reference_included': False,
        'artifacts': [
            {
                'evidence_id': 'VISUAL-001',
                'sha256': '1' * 64,
                'size_bytes': 1024,
                'media_type': 'image/jpeg',
                'inference_allowed': True,
                'validation_only': False,
                'provenance': {
                    'source_reference': 'report.pdf#page=1-image=1',
                    'page_number': 1,
                    'region_reference': 'image-1',
                    'evidence_class': 'observed',
                    'evidence_role': 'primary_detail',
                    'relationship': 'embedded_image',
                    'parent_evidence_id': None,
                    'pixel_width': 1600,
                    'pixel_height': 1200,
                },
            }
        ],
    }
    artifact = manifest['artifacts'][0]
    return RetainedVisualEvidencePacket(
        manifest=manifest,
        files=(
            RetainedVisualEvidenceFile(
                evidence_id=artifact['evidence_id'],
                path=Path('retained/runtime-input-visual.jpg'),
                sha256=artifact['sha256'],
                size_bytes=artifact['size_bytes'],
                media_type=artifact['media_type'],
            ),
        ),
    )


def _components() -> tuple[object, object, object, object]:
    content = _report_content()
    packet = _packet(content)
    assessment = build_phase8_report_assessment_input(
        report_packet=packet,
        visual_packet=_visual_packet(),
    )
    documentary = build_phase8_report_documentary_context(
        report_packet=packet,
        verified_content=content,
    )
    runtime = build_phase8_report_runtime_input(
        assessment_input=assessment,
        documentary_context=documentary,
    )
    return content, assessment, documentary, runtime


def test_runtime_input_is_deterministic_content_safe_and_no_run() -> None:
    _content, assessment, documentary, first = _components()
    repeated = build_phase8_report_runtime_input(
        assessment_input=assessment,
        documentary_context=documentary,
    )

    assert validate_phase8_report_runtime_input(first) == []
    assert first.manifest == repeated.manifest
    assert first.manifest_sha256 == repeated.manifest_sha256
    assert first.manifest['schema'] == PHASE8_REPORT_RUNTIME_INPUT_SCHEMA
    assert first.visual_packet is assessment.visual_packet
    assert first.allowed_evidence_refs == assessment.allowed_evidence_refs
    assert first.manifest['documentary_content_item_count'] == len(documentary.items)
    assert first.manifest['visual_file_count'] == 1
    assert all(
        first.manifest[field] is False
        for field in (
            'runtime_inference_performed',
            'canonical_submission_performed',
            'technical_selection_performed',
            'commercial_pricing_performed',
            'physical_model_lock_created',
            'human_release_performed',
        )
    )
    assert 'Private annotation content' not in str(first)
    assert 'runtime-input-visual.jpg' not in str(first)
    assert 'runtime-input-visual.jpg' not in str(assessment)


def test_runtime_input_rejects_a_different_documentary_scope() -> None:
    content, assessment, _documentary, _runtime = _components()
    other_context = build_phase8_report_documentary_context(
        report_packet=_packet(content, item_kind='text'),
        verified_content=content,
    )

    with pytest.raises(Phase8ReportRuntimeInputError) as raised:
        build_phase8_report_runtime_input(
            assessment_input=assessment,
            documentary_context=other_context,
        )

    assert raised.value.code == 'REPORT_RUNTIME_DOCUMENTARY_BINDING_INVALID'


def test_runtime_input_validator_detects_manifest_tampering_without_raising() -> None:
    _content, _assessment, _documentary, runtime = _components()
    manifest = deepcopy(runtime.manifest)
    manifest['allowed_evidence_refs'] = ['VISUAL-001']
    forged = replace(
        runtime,
        manifest=manifest,
        manifest_sha256=canonical_json_sha256(manifest),
    )

    errors = validate_phase8_report_runtime_input(forged)

    assert any('not source-bound' in error for error in errors)
