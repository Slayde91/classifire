'''No-run runtime input binding selected documentary and visual report evidence.

This is not an inference controller or transport. It is the sole in-memory
handoff a later, separately authorised report-assessment runtime may consume.
It refuses to pair report text from one selected scope with images, locators,
or identities from another scope.
'''

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, NoReturn

from .phase8_report_assessment_input import (
    Phase8ReportAssessmentInput,
    validate_phase8_report_assessment_input,
)
from .phase8_report_documentary_context import (
    Phase8ReportDocumentaryContext,
    validate_phase8_report_documentary_context,
)
from .phase8_visual_evidence import RetainedVisualEvidencePacket
from .phase8_visual_proposal import canonical_json_sha256

PHASE8_REPORT_RUNTIME_INPUT_SCHEMA = 'CLASSIFIRE-PHASE8-REPORT-RUNTIME-INPUT-v1'

_HASH = re.compile(r'^[0-9A-F]{64}$')
_NOOP_FLAGS = (
    'runtime_inference_performed',
    'canonical_submission_performed',
    'technical_selection_performed',
    'commercial_pricing_performed',
    'physical_model_lock_created',
    'human_release_performed',
)


class Phase8ReportRuntimeInputError(ValueError):
    '''A stable, content-safe failure while preparing a future runtime input.'''

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise Phase8ReportRuntimeInputError(code)


@dataclass(frozen=True, slots=True)
class Phase8ReportRuntimeInput:
    '''An exact no-run assessment handoff, with transient evidence hidden from repr.'''

    assessment_input: Phase8ReportAssessmentInput = field(repr=False)
    documentary_context: Phase8ReportDocumentaryContext = field(repr=False)
    manifest: dict[str, Any]
    manifest_sha256: str

    @property
    def visual_packet(self) -> RetainedVisualEvidencePacket:
        '''Return the already-validated retained visual packet for a later runtime.'''

        return self.assessment_input.visual_packet

    @property
    def allowed_evidence_refs(self) -> frozenset[str]:
        values = self.manifest.get('allowed_evidence_refs')
        if not isinstance(values, list):
            return frozenset()
        return frozenset(value for value in values if isinstance(value, str))


def _canonical_hash(value: object, *, code: str) -> str:
    try:
        return canonical_json_sha256(value)
    except Exception as exc:
        raise Phase8ReportRuntimeInputError(code) from exc


def _assessment_input(value: object) -> Phase8ReportAssessmentInput:
    if not isinstance(value, Phase8ReportAssessmentInput):
        _fail('REPORT_RUNTIME_ASSESSMENT_INPUT_INVALID')
    if validate_phase8_report_assessment_input(value):
        _fail('REPORT_RUNTIME_ASSESSMENT_INPUT_INVALID')
    return value


def _documentary_context(value: object) -> Phase8ReportDocumentaryContext:
    if not isinstance(value, Phase8ReportDocumentaryContext):
        _fail('REPORT_RUNTIME_DOCUMENTARY_CONTEXT_INVALID')
    if validate_phase8_report_documentary_context(value):
        _fail('REPORT_RUNTIME_DOCUMENTARY_CONTEXT_INVALID')
    return value


def _bound_inputs(
    assessment_input: object,
    documentary_context: object,
) -> tuple[Phase8ReportAssessmentInput, Phase8ReportDocumentaryContext]:
    assessment = _assessment_input(assessment_input)
    documentary = _documentary_context(documentary_context)
    assessment_manifest = assessment.manifest
    documentary_manifest = documentary.manifest
    report_packet = assessment.report_packet
    if (
        documentary.packet.manifest != report_packet.manifest
        or documentary.packet.manifest_sha256 != report_packet.manifest_sha256
        or (
            documentary_manifest.get('report_packet_manifest_sha256')
            != report_packet.manifest_sha256
        )
    ):
        _fail('REPORT_RUNTIME_DOCUMENTARY_BINDING_INVALID')
    shared_fields = (
        'project_evidence_id',
        'report_sha256',
        'estimate_id',
        'defect_id',
        'defect_reference',
        'report_defect_label',
        'scope_id',
    )
    if any(
        documentary_manifest.get(field) != assessment_manifest.get(field)
        for field in shared_fields
    ):
        _fail('REPORT_RUNTIME_DOCUMENTARY_BINDING_INVALID')
    documentary_refs = assessment_manifest.get('documentary_evidence_refs')
    visual_refs = assessment_manifest.get('visual_evidence_refs')
    allowed_refs = assessment_manifest.get('allowed_evidence_refs')
    if (
        not isinstance(documentary_refs, list)
        or not isinstance(visual_refs, list)
        or not isinstance(allowed_refs, list)
        or set(documentary_refs) != documentary.evidence_refs
        or set(documentary_refs) & set(visual_refs)
        or set(allowed_refs) != set(documentary_refs) | set(visual_refs)
    ):
        _fail('REPORT_RUNTIME_EVIDENCE_REFS_INVALID')
    return assessment, documentary


def _manifest(
    assessment: Phase8ReportAssessmentInput,
    documentary: Phase8ReportDocumentaryContext,
) -> dict[str, Any]:
    assessment_manifest = assessment.manifest
    return {
        'schema': PHASE8_REPORT_RUNTIME_INPUT_SCHEMA,
        'assessment_input_manifest_sha256': assessment.manifest_sha256,
        'documentary_context_manifest_sha256': documentary.manifest_sha256,
        'report_packet_manifest_sha256': assessment_manifest['report_packet_manifest_sha256'],
        'visual_evidence_manifest_sha256': assessment_manifest['visual_evidence_manifest_sha256'],
        'visual_evidence_family_inventory_sha256': assessment_manifest[
            'visual_evidence_family_inventory_sha256'
        ],
        'project_evidence_id': assessment_manifest['project_evidence_id'],
        'report_sha256': assessment_manifest['report_sha256'],
        'estimate_id': assessment_manifest['estimate_id'],
        'defect_id': assessment_manifest['defect_id'],
        'defect_reference': assessment_manifest['defect_reference'],
        'report_defect_label': assessment_manifest['report_defect_label'],
        'scope_id': assessment_manifest['scope_id'],
        'documentary_evidence_refs': list(assessment_manifest['documentary_evidence_refs']),
        'visual_evidence_refs': list(assessment_manifest['visual_evidence_refs']),
        'allowed_evidence_refs': list(assessment_manifest['allowed_evidence_refs']),
        'documentary_content_item_count': len(documentary.items),
        'visual_file_count': len(assessment.visual_packet.files),
        'proposal_only': True,
        'transient_content_only': True,
        **{flag: False for flag in _NOOP_FLAGS},
    }


def build_phase8_report_runtime_input(
    *,
    assessment_input: object,
    documentary_context: object,
) -> Phase8ReportRuntimeInput:
    '''Prepare an exact future-runtime handoff without reading files or running inference.'''

    assessment, documentary = _bound_inputs(assessment_input, documentary_context)
    manifest = _manifest(assessment, documentary)
    result = Phase8ReportRuntimeInput(
        assessment_input=assessment,
        documentary_context=documentary,
        manifest=manifest,
        manifest_sha256=_canonical_hash(manifest, code='REPORT_RUNTIME_MANIFEST_INVALID'),
    )
    if validate_phase8_report_runtime_input(result):
        _fail('REPORT_RUNTIME_BUILD_INVALID')
    return result


def validate_phase8_report_runtime_input(value: object) -> list[str]:
    '''Validate a future-runtime handoff without file reads, inference, or writes.'''

    if not isinstance(value, Phase8ReportRuntimeInput):
        return ['report runtime input has an unsupported type']
    errors: list[str] = []
    try:
        assessment, documentary = _bound_inputs(
            value.assessment_input,
            value.documentary_context,
        )
        expected_manifest = _manifest(assessment, documentary)
    except Phase8ReportRuntimeInputError as exc:
        return [exc.code]
    if value.manifest != expected_manifest:
        errors.append('report runtime input manifest is not source-bound')
    try:
        actual_hash = _canonical_hash(value.manifest, code='REPORT_RUNTIME_MANIFEST_INVALID')
    except Phase8ReportRuntimeInputError:
        errors.append('report runtime input manifest is not canonical JSON')
    else:
        if value.manifest_sha256 != actual_hash:
            errors.append('report runtime input manifest hash does not match its contents')
    manifest = value.manifest
    hash_fields = (
        'assessment_input_manifest_sha256',
        'documentary_context_manifest_sha256',
        'report_packet_manifest_sha256',
        'visual_evidence_manifest_sha256',
        'visual_evidence_family_inventory_sha256',
    )
    if (
        not isinstance(manifest, dict)
        or manifest.get('schema') != PHASE8_REPORT_RUNTIME_INPUT_SCHEMA
        or any(not _HASH.fullmatch(str(manifest.get(field) or '')) for field in hash_fields)
        or manifest.get('proposal_only') is not True
        or manifest.get('transient_content_only') is not True
        or any(manifest.get(flag) is not False for flag in _NOOP_FLAGS)
    ):
        errors.append('report runtime input manifest is invalid')
    return list(dict.fromkeys(errors))


__all__ = [
    'PHASE8_REPORT_RUNTIME_INPUT_SCHEMA',
    'Phase8ReportRuntimeInput',
    'Phase8ReportRuntimeInputError',
    'build_phase8_report_runtime_input',
    'validate_phase8_report_runtime_input',
]
