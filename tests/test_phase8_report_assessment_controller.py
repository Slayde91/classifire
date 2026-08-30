from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace

import pytest
from test_phase8_proposal_review import _Port as VisualPort
from test_phase8_proposal_review import _profile as visual_profile
from test_phase8_report_documentary_context import _packet
from test_phase8_report_runtime_input import _visual_packet
from test_phase8_visual_proposal import _proposal
from test_report_evidence_adapter import _report_content

from classifire.services.canonical_submission_state import InitialSubmissionState
from classifire.services.phase8_proposal_review import (
    Phase8ProposalReviewError,
    build_phase8_proposal_review,
    validate_phase8_proposal_review,
)
from classifire.services.phase8_report_assessment_controller import (
    Phase8ReportAssessmentController,
    Phase8ReportAssessmentControllerError,
    validate_phase8_report_assessment_receipt,
)
from classifire.services.phase8_report_assessment_input import (
    build_phase8_report_assessment_input,
)
from classifire.services.phase8_report_assessment_prompts import (
    build_report_assessment_inference_profile,
)
from classifire.services.phase8_report_documentary_context import (
    build_phase8_report_documentary_context,
)
from classifire.services.phase8_report_runtime_input import (
    Phase8ReportRuntimeInput,
    build_phase8_report_runtime_input,
)
from classifire.services.phase8_visual_evidence import RetainedVisualEvidencePacket


def _state() -> InitialSubmissionState:
    return InitialSubmissionState(
        estimate_id='ESTIMATE-001',
        fingerprint='A' * 64,
        counts={
            'defect_count': 0,
            'evidence_count': 0,
            'opening_count': 0,
            'service_count': 0,
            'service_opening_link_count': 0,
            'active_physical_model_lock_count': 0,
        },
        snapshot={'schema': 'CLASSIFIRE-INITIAL-SUBMISSION-STATE-v1'},
    )


def _runtime() -> Phase8ReportRuntimeInput:
    content = _report_content()
    packet = _packet(content)
    source_visual = _visual_packet()
    manifest = deepcopy(source_visual.manifest)
    manifest['artifacts'][0]['evidence_id'] = 'E-001'
    visual = RetainedVisualEvidencePacket(
        manifest=manifest,
        files=(replace(source_visual.files[0], evidence_id='E-001'),),
    )
    assessment = build_phase8_report_assessment_input(
        report_packet=packet,
        visual_packet=visual,
    )
    documentary = build_phase8_report_documentary_context(
        report_packet=packet,
        verified_content=content,
    )
    return build_phase8_report_runtime_input(
        assessment_input=assessment,
        documentary_context=documentary,
    )


def _report_profile() -> dict[str, object]:
    return build_report_assessment_inference_profile(
        implementation_revision='a' * 40,
        provider='test-provider',
        physical_model='physical-test-model',
        validator_model='validator-test-model',
    )


class _ReportPort:
    def __init__(self, proposal: dict[str, object]) -> None:
        self._visual = VisualPort(proposal)
        self.prompts: list[object] = []

    def invoke(
        self,
        *,
        role,
        stage,
        request,
        rendered_prompt,
        runtime_input,
        report_assessment_inference_profile,
    ):
        self.prompts.append(rendered_prompt)
        assert runtime_input.manifest['runtime_inference_performed'] is False
        assert report_assessment_inference_profile == _report_profile()
        assert 'Private annotation content' in rendered_prompt.text
        return self._visual.invoke(role=role, stage=stage, request=request)


def _documentary_grounded_proposal(runtime: Phase8ReportRuntimeInput) -> dict[str, object]:
    proposal = _proposal()
    documentary_ref = next(
        value for value in runtime.allowed_evidence_refs if value != 'E-001'
    )
    for subject in ('openings', 'services'):
        for record in proposal[subject]:
            for assessment in record['property_assessments'].values():
                assessment['evidence_refs'] = [documentary_ref]
    proposal['services'][0]['source_reference'] = documentary_ref
    return proposal


def test_controller_delivers_bound_report_prompts_and_emits_content_free_receipt() -> None:
    runtime = _runtime()
    port = _ReportPort(_documentary_grounded_proposal(runtime))
    result = Phase8ReportAssessmentController(
        run_id='REPORT-RUN-001',
        runtime_input=runtime,
        visual_inference_profile=visual_profile(),
        report_assessment_inference_profile=_report_profile(),
        inference_port=port,
        protected_state_reader=_state,
        max_correction_passes=0,
    ).run()

    assert result.visual_result.approved is True
    assert validate_phase8_report_assessment_receipt(result.receipt) == []
    assert len(port.prompts) == len(result.receipt['stages']) == 3
    assert result.receipt['report_runtime_input_manifest_sha256'] == runtime.manifest_sha256
    assert result.receipt['runtime_inference_performed'] is True
    assert 'Private annotation content' not in str(result)
    assert all('Private annotation content' not in str(prompt) for prompt in port.prompts)
    assert all(stage['documentary_content_sha256'] for stage in result.receipt['stages'])


def test_controller_fails_closed_when_profiles_do_not_describe_the_same_runtime() -> None:
    profile = _report_profile()
    profile['physical_model'] = 'different-model'

    with pytest.raises(Phase8ReportAssessmentControllerError) as raised:
        Phase8ReportAssessmentController(
            run_id='REPORT-RUN-001',
            runtime_input=_runtime(),
            visual_inference_profile=visual_profile(),
            report_assessment_inference_profile=profile,
            inference_port=_ReportPort(_proposal()),
            protected_state_reader=_state,
        )

    assert raised.value.code == 'REPORT_ASSESSMENT_CONTROLLER_PROFILE_MISMATCH'


def test_receipt_rejects_a_prompt_stage_detached_from_its_visual_request() -> None:
    runtime = _runtime()
    result = Phase8ReportAssessmentController(
        run_id='REPORT-RUN-001',
        runtime_input=runtime,
        visual_inference_profile=visual_profile(),
        report_assessment_inference_profile=_report_profile(),
        inference_port=_ReportPort(_documentary_grounded_proposal(runtime)),
        protected_state_reader=_state,
        max_correction_passes=0,
    ).run()
    forged = deepcopy(result.receipt)
    forged['stages'][0]['visual_request_sha256'] = '0' * 64

    errors = validate_phase8_report_assessment_receipt(forged)

    assert any('not visual-receipt bound' in error for error in errors)


def test_proposal_review_requires_the_matching_report_aware_receipt() -> None:
    runtime = _runtime()
    result = Phase8ReportAssessmentController(
        run_id='REPORT-RUN-001',
        runtime_input=runtime,
        visual_inference_profile=visual_profile(),
        report_assessment_inference_profile=_report_profile(),
        inference_port=_ReportPort(_documentary_grounded_proposal(runtime)),
        protected_state_reader=_state,
        max_correction_passes=0,
    ).run()
    assert result.visual_result.proposal is not None
    proposal_bytes = json.dumps(result.visual_result.proposal, sort_keys=True).encode('utf-8')
    visual_receipt_bytes = json.dumps(result.visual_result.receipt, sort_keys=True).encode('utf-8')
    report_receipt_bytes = json.dumps(result.receipt, sort_keys=True).encode('utf-8')
    inputs = {
        'package_id': 'PACKAGE-REPORT-001',
        'package_sha256': '9' * 64,
        'approval_reference': 'report-aware proposal-only review',
        'proposal_file_bytes': proposal_bytes,
        'proposal_file_sha256': hashlib.sha256(proposal_bytes).hexdigest(),
        'controller_receipt_file_bytes': visual_receipt_bytes,
        'controller_receipt_file_sha256': hashlib.sha256(visual_receipt_bytes).hexdigest(),
        'evidence_manifest': runtime.visual_packet.manifest,
        'documentary_evidence_packet': runtime.assessment_input.report_packet,
        'report_assessment_controller_receipt_file_bytes': report_receipt_bytes,
        'report_assessment_controller_receipt_file_sha256': hashlib.sha256(
            report_receipt_bytes
        ).hexdigest(),
    }

    review = build_phase8_proposal_review(**inputs)

    assert validate_phase8_proposal_review(review) == []
    assert review['input_bindings']['report_runtime_input_manifest_sha256'] == (
        runtime.manifest_sha256
    )
    inputs['report_assessment_controller_receipt_file_bytes'] += b' '
    with pytest.raises(Phase8ProposalReviewError) as tampered:
        build_phase8_proposal_review(**inputs)
    assert tampered.value.code == 'PROPOSAL_REVIEW_REPORT_RECEIPT_TAMPERED'
