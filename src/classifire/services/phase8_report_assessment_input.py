'''Content-free, no-run bindings for one report scope and visual evidence packet.'''

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NoReturn

from .phase8_visual_evidence import (
    RetainedVisualEvidenceFile,
    RetainedVisualEvidencePacket,
)
from .phase8_visual_proposal import canonical_json_sha256, validate_visual_evidence_manifest
from .report_evidence_adapter import (
    ReportDefectEvidencePacket,
    validate_report_defect_evidence_packet,
)

PHASE8_REPORT_ASSESSMENT_INPUT_SCHEMA = 'CLASSIFIRE-PHASE8-REPORT-ASSESSMENT-INPUT-v1'

_HASH = re.compile(r'^[0-9A-F]{64}$')
_NOOP_FLAGS = (
    'runtime_inference_performed',
    'canonical_submission_performed',
    'technical_selection_performed',
    'commercial_pricing_performed',
    'physical_model_lock_created',
    'human_release_performed',
)


class Phase8ReportAssessmentInputError(ValueError):
    '''A stable failure while preparing a no-run report assessment input.'''

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise Phase8ReportAssessmentInputError(code)


@dataclass(frozen=True, slots=True)
class Phase8ReportAssessmentInput:
    '''One exact report scope paired with verified visual evidence, without a run.'''

    report_packet: ReportDefectEvidencePacket
    visual_packet: RetainedVisualEvidencePacket = field(repr=False)
    manifest: dict[str, Any]
    manifest_sha256: str

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
        raise Phase8ReportAssessmentInputError(code) from exc


def _report_packet(value: object) -> ReportDefectEvidencePacket:
    if not isinstance(value, ReportDefectEvidencePacket):
        _fail('REPORT_ASSESSMENT_REPORT_PACKET_INVALID')
    if validate_report_defect_evidence_packet(value):
        _fail('REPORT_ASSESSMENT_REPORT_PACKET_INVALID')
    return value


def _visual_packet(
    value: object,
    *,
    estimate_id: str,
    defect_reference: str,
) -> tuple[RetainedVisualEvidencePacket, frozenset[str]]:
    if not isinstance(value, RetainedVisualEvidencePacket):
        _fail('REPORT_ASSESSMENT_VISUAL_PACKET_INVALID')
    manifest = value.manifest
    errors = validate_visual_evidence_manifest(manifest, estimate_id=estimate_id)
    if errors:
        _fail('REPORT_ASSESSMENT_VISUAL_PACKET_INVALID')
    if manifest.get('defect_reference') != defect_reference:
        _fail('REPORT_ASSESSMENT_VISUAL_SCOPE_MISMATCH')
    artifacts = manifest.get('artifacts')
    files = value.files
    if not isinstance(artifacts, list) or not isinstance(files, tuple) or not files:
        _fail('REPORT_ASSESSMENT_VISUAL_PACKET_INVALID')
    artifacts_by_id: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        if not isinstance(artifact, dict) or not isinstance(artifact.get('evidence_id'), str):
            _fail('REPORT_ASSESSMENT_VISUAL_PACKET_INVALID')
        evidence_id = artifact['evidence_id']
        if evidence_id in artifacts_by_id:
            _fail('REPORT_ASSESSMENT_VISUAL_PACKET_INVALID')
        artifacts_by_id[evidence_id] = artifact
    if len(files) != len(artifacts_by_id):
        _fail('REPORT_ASSESSMENT_VISUAL_PACKET_INVALID')
    file_ids: set[str] = set()
    for item in files:
        if not isinstance(item, RetainedVisualEvidenceFile) or not isinstance(item.path, Path):
            _fail('REPORT_ASSESSMENT_VISUAL_PACKET_INVALID')
        artifact = artifacts_by_id.get(item.evidence_id)
        if (
            item.evidence_id in file_ids
            or artifact is None
            or not isinstance(item.sha256, str)
            or item.sha256.casefold() != str(artifact.get('sha256') or '').casefold()
            or item.size_bytes != artifact.get('size_bytes')
            or item.media_type != artifact.get('media_type')
        ):
            _fail('REPORT_ASSESSMENT_VISUAL_PACKET_INVALID')
        file_ids.add(item.evidence_id)
    return value, frozenset(artifacts_by_id)


def _manifest(
    report: ReportDefectEvidencePacket,
    visual: RetainedVisualEvidencePacket,
    *,
    visual_refs: frozenset[str],
) -> dict[str, Any]:
    report_manifest = report.manifest
    report_refs = report.evidence_refs
    if not report_refs or report_refs & visual_refs:
        _fail('REPORT_ASSESSMENT_EVIDENCE_REFS_INVALID')
    allowed_refs = sorted(report_refs | visual_refs)
    return {
        'schema': PHASE8_REPORT_ASSESSMENT_INPUT_SCHEMA,
        'project_evidence_id': report_manifest['project_evidence_id'],
        'report_sha256': report_manifest['report_sha256'],
        'estimate_id': report_manifest['estimate_id'],
        'defect_id': report_manifest['defect_id'],
        'defect_reference': report_manifest['defect_reference'],
        'report_defect_label': report_manifest['report_defect_label'],
        'scope_id': report_manifest['scope_id'],
        'report_packet_manifest_sha256': report.manifest_sha256,
        'visual_evidence_manifest_sha256': visual.manifest_sha256,
        'visual_evidence_family_inventory_sha256': visual.evidence_family_inventory_sha256,
        'documentary_evidence_refs': sorted(report_refs),
        'visual_evidence_refs': sorted(visual_refs),
        'allowed_evidence_refs': allowed_refs,
        'proposal_only': True,
        **{flag: False for flag in _NOOP_FLAGS},
    }


def build_phase8_report_assessment_input(
    *,
    report_packet: object,
    visual_packet: object,
) -> Phase8ReportAssessmentInput:
    '''Bind one selected report scope and visual packet without reading or running either.'''

    report = _report_packet(report_packet)
    report_manifest = report.manifest
    visual, visual_refs = _visual_packet(
        visual_packet,
        estimate_id=str(report_manifest['estimate_id']),
        defect_reference=str(report_manifest['defect_reference']),
    )
    manifest = _manifest(report, visual, visual_refs=visual_refs)
    result = Phase8ReportAssessmentInput(
        report_packet=report,
        visual_packet=visual,
        manifest=manifest,
        manifest_sha256=_canonical_hash(manifest, code='REPORT_ASSESSMENT_MANIFEST_INVALID'),
    )
    if validate_phase8_report_assessment_input(result):
        _fail('REPORT_ASSESSMENT_BUILD_INVALID')
    return result


def validate_phase8_report_assessment_input(value: object) -> list[str]:
    '''Validate a combined input before a separately authorised runtime consumes it.'''

    if not isinstance(value, Phase8ReportAssessmentInput):
        return ['report assessment input has an unsupported type']
    errors: list[str] = []
    try:
        report = _report_packet(value.report_packet)
        report_manifest = report.manifest
        visual, visual_refs = _visual_packet(
            value.visual_packet,
            estimate_id=str(report_manifest['estimate_id']),
            defect_reference=str(report_manifest['defect_reference']),
        )
        expected_manifest = _manifest(report, visual, visual_refs=visual_refs)
    except Phase8ReportAssessmentInputError as exc:
        return [exc.code]
    if value.manifest != expected_manifest:
        errors.append('report assessment input manifest is not source-bound')
    try:
        actual_hash = _canonical_hash(value.manifest, code='REPORT_ASSESSMENT_MANIFEST_INVALID')
    except Phase8ReportAssessmentInputError:
        errors.append('report assessment input manifest is not canonical JSON')
    else:
        if not isinstance(value.manifest_sha256, str) or value.manifest_sha256 != actual_hash:
            errors.append('report assessment input manifest hash does not match its contents')
    manifest = value.manifest
    if (
        not isinstance(manifest, dict)
        or manifest.get('schema') != PHASE8_REPORT_ASSESSMENT_INPUT_SCHEMA
        or not _HASH.fullmatch(str(manifest.get('report_packet_manifest_sha256') or ''))
        or not _HASH.fullmatch(str(manifest.get('visual_evidence_manifest_sha256') or ''))
        or not _HASH.fullmatch(
            str(manifest.get('visual_evidence_family_inventory_sha256') or '')
        )
        or manifest.get('proposal_only') is not True
        or any(manifest.get(flag) is not False for flag in _NOOP_FLAGS)
    ):
        errors.append('report assessment input manifest is invalid')
    return list(dict.fromkeys(errors))


__all__ = [
    'PHASE8_REPORT_ASSESSMENT_INPUT_SCHEMA',
    'Phase8ReportAssessmentInput',
    'Phase8ReportAssessmentInputError',
    'build_phase8_report_assessment_input',
    'validate_phase8_report_assessment_input',
]
