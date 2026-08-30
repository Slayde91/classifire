'''Controlled report-aware assessment wrapper around the Phase 8 visual workflow.

The established visual-only controller remains unchanged. This wrapper supplies
the separately validated documentary prompt on every inference turn, expands
allowed evidence references only from the exact report runtime input, and emits
a content-free receipt that proves that binding.
'''

from __future__ import annotations

import re
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from .canonical_submission_state import InitialSubmissionState
from .phase8_report_assessment_prompts import (
    Phase8ReportAssessmentPromptRenderer,
    RenderedReportAssessmentPrompt,
    validate_report_assessment_inference_profile,
)
from .phase8_report_runtime_input import (
    Phase8ReportRuntimeInput,
    validate_phase8_report_runtime_input,
)
from .phase8_visual_proposal import (
    Phase8VisualProposalResult,
    ProposalOnlyVisualController,
    canonical_json_sha256,
    validate_phase8_visual_proposal_receipt,
    validate_visual_inference_profile,
)

PHASE8_REPORT_ASSESSMENT_RECEIPT_SCHEMA = 'CLASSIFIRE-PHASE8-REPORT-ASSESSMENT-RECEIPT-v1'

_HASH = re.compile(r'^[0-9A-F]{64}$')
_NOOP_FLAGS = (
    'controller_database_write_performed',
    'controller_canonical_write_performed',
    'write_or_lock_capability_exposed',
    'human_reference_visible_to_inference',
)


class Phase8ReportAssessmentControllerError(RuntimeError):
    '''Stable fail-closed error before a report-aware assessment can run.'''

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class Phase8ReportAssessmentInferencePort(Protocol):
    '''The only execution capability exposed by the report-aware wrapper.'''

    def invoke(
        self,
        *,
        role: str,
        stage: str,
        request: dict[str, Any],
        rendered_prompt: RenderedReportAssessmentPrompt,
        runtime_input: Phase8ReportRuntimeInput,
        report_assessment_inference_profile: dict[str, Any],
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class Phase8ReportAssessmentControllerResult:
    '''A visual workflow result plus the report-aware receipt that binds it.'''

    visual_result: Phase8VisualProposalResult = field(repr=False)
    receipt: dict[str, Any]

    @property
    def receipt_sha256(self) -> str:
        return canonical_json_sha256(self.receipt)


def _fail(code: str) -> None:
    raise Phase8ReportAssessmentControllerError(code)


def _valid_hash(value: object) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _runtime(value: object) -> Phase8ReportRuntimeInput:
    if not isinstance(value, Phase8ReportRuntimeInput):
        _fail('REPORT_ASSESSMENT_CONTROLLER_RUNTIME_INPUT_INVALID')
    if validate_phase8_report_runtime_input(value):
        _fail('REPORT_ASSESSMENT_CONTROLLER_RUNTIME_INPUT_INVALID')
    return cast(Phase8ReportRuntimeInput, value)


def _profile(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail('REPORT_ASSESSMENT_CONTROLLER_PROFILE_INVALID')
    if validate_report_assessment_inference_profile(value):
        _fail('REPORT_ASSESSMENT_CONTROLLER_PROFILE_INVALID')
    return deepcopy(cast(dict[str, Any], value))


def _profiles_match(
    *,
    visual_profile: object,
    report_profile: dict[str, Any],
) -> None:
    if not isinstance(visual_profile, dict):
        _fail('REPORT_ASSESSMENT_CONTROLLER_VISUAL_PROFILE_INVALID')
    if validate_visual_inference_profile(visual_profile):
        _fail('REPORT_ASSESSMENT_CONTROLLER_VISUAL_PROFILE_INVALID')
    selected_visual_profile = cast(dict[str, Any], visual_profile)
    for profile_field in (
        'implementation_revision',
        'provider',
        'physical_model',
        'validator_model',
    ):
        if selected_visual_profile.get(profile_field) != report_profile.get(profile_field):
            _fail('REPORT_ASSESSMENT_CONTROLLER_PROFILE_MISMATCH')


class _ReportAwareVisualController(ProposalOnlyVisualController):
    '''Reuse the bounded workflow with evidence refs sourced only from the runtime input.'''

    def __init__(self, *, runtime_input: Phase8ReportRuntimeInput, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.property_assessment_evidence_refs = runtime_input.allowed_evidence_refs


class _ReportAwarePort:
    '''Render and record the documentary prompt before every delegated invocation.'''

    def __init__(
        self,
        *,
        port: Phase8ReportAssessmentInferencePort,
        runtime_input: Phase8ReportRuntimeInput,
        report_profile: dict[str, Any],
    ) -> None:
        self._port = port
        self._runtime_input = runtime_input
        self._report_profile = deepcopy(report_profile)
        self._renderer = Phase8ReportAssessmentPromptRenderer()
        self.prompts: list[dict[str, Any]] = []

    def invoke(self, *, role: str, stage: str, request: dict[str, Any]) -> Any:
        rendered = self._renderer.render(
            role=role,
            stage=stage,
            run_id=str(request.get('run_id') or ''),
            runtime_input=self._runtime_input,
            inference_profile=self._report_profile,
            stage_input=request.get('stage_input'),
        )
        self.prompts.append(
            {
                'stage': stage,
                'role': role,
                'visual_request_sha256': canonical_json_sha256(request),
                'report_prompt_sha256': canonical_json_sha256(rendered.text),
                'report_prompt_template_sha256': rendered.template_sha256,
                'documentary_content_sha256': rendered.documentary_content_sha256,
                'runtime_input_manifest_sha256': rendered.runtime_input_manifest_sha256,
                'inference_profile_sha256': rendered.inference_profile_sha256,
            }
        )
        return self._port.invoke(
            role=role,
            stage=stage,
            request=deepcopy(request),
            rendered_prompt=rendered,
            runtime_input=self._runtime_input,
            report_assessment_inference_profile=deepcopy(self._report_profile),
        )


def _stage_receipts(
    *,
    visual_receipt: dict[str, Any],
    prompts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    visual_stages = visual_receipt.get('stages')
    if not isinstance(visual_stages, list) or len(visual_stages) != len(prompts):
        _fail('REPORT_ASSESSMENT_CONTROLLER_STAGE_BINDING_INVALID')
    selected_visual_stages = cast(list[Any], visual_stages)
    records: list[dict[str, Any]] = []
    for sequence, (visual_stage, prompt) in enumerate(
        zip(selected_visual_stages, prompts, strict=True),
        start=1,
    ):
        if not isinstance(visual_stage, dict) or (
            visual_stage.get('stage') != prompt['stage']
            or visual_stage.get('role') != prompt['role']
            or visual_stage.get('request_sha256') != prompt['visual_request_sha256']
        ):
            _fail('REPORT_ASSESSMENT_CONTROLLER_STAGE_BINDING_INVALID')
        response_sha256 = visual_stage.get('response_sha256')
        if not _valid_hash(response_sha256):
            _fail('REPORT_ASSESSMENT_CONTROLLER_STAGE_BINDING_INVALID')
        records.append({
            'sequence': sequence,
            **prompt,
            'response_sha256': response_sha256,
        })
    return records


def _receipt(
    *,
    visual_result: Phase8VisualProposalResult,
    runtime_input: Phase8ReportRuntimeInput,
    report_profile: dict[str, Any],
    prompts: list[dict[str, Any]],
) -> dict[str, Any]:
    visual_receipt = visual_result.receipt
    if validate_phase8_visual_proposal_receipt(visual_receipt):
        _fail('REPORT_ASSESSMENT_CONTROLLER_VISUAL_RECEIPT_INVALID')
    stages = _stage_receipts(visual_receipt=visual_receipt, prompts=prompts)
    report_profile_sha256 = canonical_json_sha256(report_profile)
    receipt = {
        'schema': PHASE8_REPORT_ASSESSMENT_RECEIPT_SCHEMA,
        'status': visual_result.status,
        'run_id': visual_receipt['run_id'],
        'estimate_id': visual_receipt['estimate_id'],
        'defect_reference': visual_receipt['defect_reference'],
        'visual_controller_receipt': deepcopy(visual_receipt),
        'visual_controller_receipt_sha256': canonical_json_sha256(visual_receipt),
        'report_runtime_input_manifest_sha256': runtime_input.manifest_sha256,
        'report_documentary_context_manifest_sha256': (
            runtime_input.documentary_context.manifest_sha256
        ),
        'report_assessment_inference_profile_sha256': report_profile_sha256,
        'stages': stages,
        'runtime_inference_performed': bool(stages),
        **{flag: False for flag in _NOOP_FLAGS},
    }
    if validate_phase8_report_assessment_receipt(receipt):
        _fail('REPORT_ASSESSMENT_CONTROLLER_RECEIPT_INVALID')
    return receipt


def validate_phase8_report_assessment_receipt(receipt: object) -> list[str]:
    '''Validate a content-free receipt emitted by the report-aware wrapper.'''

    if not isinstance(receipt, dict):
        return ['report assessment receipt must be an object']
    expected = {
        'schema', 'status', 'run_id', 'estimate_id', 'defect_reference',
        'visual_controller_receipt', 'visual_controller_receipt_sha256',
        'report_runtime_input_manifest_sha256', 'report_documentary_context_manifest_sha256',
        'report_assessment_inference_profile_sha256', 'stages', 'runtime_inference_performed',
        *_NOOP_FLAGS,
    }
    errors: list[str] = []
    if set(receipt) != expected:
        errors.append('report assessment receipt fields do not match the approved schema')
    if receipt.get('schema') != PHASE8_REPORT_ASSESSMENT_RECEIPT_SCHEMA:
        errors.append('report assessment receipt schema is unsupported')
    visual = receipt.get('visual_controller_receipt')
    visual_errors = validate_phase8_visual_proposal_receipt(visual)
    if visual_errors or not isinstance(visual, dict):
        errors.append('report assessment receipt visual controller receipt is invalid')
    else:
        if receipt.get('status') != visual.get('status'):
            errors.append('report assessment receipt status does not match visual receipt')
        for field in ('run_id', 'estimate_id', 'defect_reference'):
            if receipt.get(field) != visual.get(field):
                errors.append(f'report assessment receipt {field} does not match visual receipt')
        if receipt.get('visual_controller_receipt_sha256') != canonical_json_sha256(visual):
            errors.append('report assessment receipt visual receipt hash is invalid')
        visual_stages = visual.get('stages')
        stages = receipt.get('stages')
        if (
            not isinstance(stages, list)
            or not isinstance(visual_stages, list)
            or len(stages) != len(visual_stages)
        ):
            errors.append('report assessment receipt stages are invalid')
        else:
            for index, (stage, visual_stage) in enumerate(
                zip(stages, visual_stages, strict=True),
                start=1,
            ):
                if not isinstance(stage, dict) or not isinstance(visual_stage, dict):
                    errors.append('report assessment receipt stage is invalid')
                    continue
                required = {
                    'sequence', 'stage', 'role', 'visual_request_sha256', 'report_prompt_sha256',
                    'report_prompt_template_sha256', 'documentary_content_sha256',
                    'runtime_input_manifest_sha256', 'inference_profile_sha256', 'response_sha256',
                }
                if set(stage) != required or stage.get('sequence') != index:
                    errors.append('report assessment receipt stage fields are invalid')
                    continue
                hash_fields = required - {'sequence', 'stage', 'role'}
                if any(not _valid_hash(stage.get(item)) for item in hash_fields):
                    errors.append('report assessment receipt stage hashes are invalid')
                if (
                    stage.get('stage') != visual_stage.get('stage')
                    or stage.get('role') != visual_stage.get('role')
                ):
                    errors.append('report assessment receipt stage identity is invalid')
                if (
                    stage.get('visual_request_sha256') != visual_stage.get('request_sha256')
                    or stage.get('response_sha256') != visual_stage.get('response_sha256')
                ):
                    errors.append('report assessment receipt stage is not visual-receipt bound')
    for field in (
        'visual_controller_receipt_sha256', 'report_runtime_input_manifest_sha256',
        'report_documentary_context_manifest_sha256', 'report_assessment_inference_profile_sha256',
    ):
        if not _valid_hash(receipt.get(field)):
            errors.append(f'report assessment receipt {field} is invalid')
    if receipt.get('runtime_inference_performed') is not bool(receipt.get('stages')):
        errors.append('report assessment receipt runtime flag is invalid')
    if any(receipt.get(flag) is not False for flag in _NOOP_FLAGS):
        errors.append('report assessment receipt must remain no-write and no-human-reference')
    return list(dict.fromkeys(errors))


class Phase8ReportAssessmentController:
    '''Run the bounded visual workflow only through a report-aware evidence port.'''

    def __init__(
        self,
        *,
        run_id: str,
        runtime_input: object,
        visual_inference_profile: object,
        report_assessment_inference_profile: object,
        inference_port: Phase8ReportAssessmentInferencePort,
        protected_state_reader: Callable[[], InitialSubmissionState],
        max_correction_passes: int = 2,
    ) -> None:
        self._runtime_input = _runtime(runtime_input)
        self._report_profile = _profile(report_assessment_inference_profile)
        _profiles_match(
            visual_profile=visual_inference_profile,
            report_profile=self._report_profile,
        )
        self._port = _ReportAwarePort(
            port=inference_port,
            runtime_input=self._runtime_input,
            report_profile=self._report_profile,
        )
        self._visual = _ReportAwareVisualController(
            runtime_input=self._runtime_input,
            run_id=run_id,
            estimate_id=str(self._runtime_input.manifest['estimate_id']),
            evidence_manifest=self._runtime_input.visual_packet.manifest,
            inference_profile=visual_inference_profile,
            inference_port=self._port,
            protected_state_reader=protected_state_reader,
            max_correction_passes=max_correction_passes,
        )
        self._has_run = False

    def run(self) -> Phase8ReportAssessmentControllerResult:
        if self._has_run:
            _fail('REPORT_ASSESSMENT_CONTROLLER_ALREADY_RUN')
        self._has_run = True
        visual_result = self._visual.run()
        return Phase8ReportAssessmentControllerResult(
            visual_result=visual_result,
            receipt=_receipt(
                visual_result=visual_result,
                runtime_input=self._runtime_input,
                report_profile=self._report_profile,
                prompts=self._port.prompts,
            ),
        )


__all__ = [
    'PHASE8_REPORT_ASSESSMENT_RECEIPT_SCHEMA',
    'Phase8ReportAssessmentController',
    'Phase8ReportAssessmentControllerError',
    'Phase8ReportAssessmentControllerResult',
    'Phase8ReportAssessmentInferencePort',
    'validate_phase8_report_assessment_receipt',
]
