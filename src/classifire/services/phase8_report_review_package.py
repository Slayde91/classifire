'''Deterministic, no-write packages for selected report-Defect reviews.'''

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from .canonical_submission_state import (
    INITIAL_SUBMISSION_STATE_FINGERPRINT_VERSION,
    InitialSubmissionState,
)
from .phase8_proposal_review import validate_phase8_proposal_review
from .phase8_report_defect_review import (
    build_phase8_report_defect_review,
    render_phase8_report_defect_review_markdown,
    validate_phase8_report_defect_review,
)
from .phase8_visual_proposal import canonical_json_sha256
from .report_evidence_adapter import (
    ReportDefectEvidencePacket,
    validate_report_defect_evidence_packet,
)

REPORT_REVIEW_PACKAGE_SCHEMA = 'CLASSIFIRE-PHASE8-REPORT-REVIEW-PACKAGE-v1'
REPORT_REVIEW_COMPLETION_RECEIPT_SCHEMA = 'CLASSIFIRE-PHASE8-REPORT-REVIEW-COMPLETION-v1'

_PACKAGE_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$')
_UPPER_SHA256 = re.compile(r'^[0-9A-F]{64}$')
_STATE_COUNT_FIELDS = (
    'defect_count',
    'evidence_count',
    'opening_count',
    'service_count',
    'service_opening_link_count',
    'active_physical_model_lock_count',
)
_NOOP_FLAGS = (
    'canonical_submission_performed',
    'technical_selection_performed',
    'commercial_pricing_performed',
    'physical_model_lock_created',
    'human_release_performed',
)


class Phase8ReportReviewPackageError(ValueError):
    '''A stable fail-closed error while assembling a report-review package.'''

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ReportDefectReviewOutcome:
    '''One explicit, proposal-only result for one selected report scope.'''

    phase8_proposal_review: object | None = None
    no_proposal_status: object | None = None
    blocker_code: object | None = None


@dataclass(frozen=True, slots=True)
class ReportDefectReviewArtifact:
    '''The deterministic JSON and inert Markdown review for one report scope.'''

    packet: ReportDefectEvidencePacket
    review: dict[str, Any]
    markdown: str


@dataclass(frozen=True, slots=True)
class Phase8ReportReviewPackage:
    '''A complete in-memory proposal-only package and its exact file bytes.'''

    manifest: dict[str, Any]
    artifacts: tuple[ReportDefectReviewArtifact, ...]
    completion_receipt: dict[str, Any]
    files: dict[str, bytes]

    @property
    def completion_receipt_file_sha256(self) -> str:
        return _sha256_bytes(self.files['completion-receipt.json'])


def _fail(code: str) -> NoReturn:
    raise Phase8ReportReviewPackageError(code)


def _required_text(value: object, *, code: str, maximum: int) -> str:
    if not isinstance(value, str):
        _fail(code)
    text = value.strip()
    if not text or len(text) > maximum:
        _fail(code)
    return text


def _sha256(value: object, *, code: str) -> str:
    text = _required_text(value, code=code, maximum=64).upper()
    if _UPPER_SHA256.fullmatch(text) is None:
        _fail(code)
    return text


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _json_file_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            + '\n'
        ).encode('utf-8')
    except (TypeError, ValueError) as exc:
        raise Phase8ReportReviewPackageError('REPORT_REVIEW_PACKAGE_JSON_INVALID') from exc


def _state_binding(state: object, *, estimate_id: str) -> dict[str, Any]:
    if not isinstance(state, InitialSubmissionState) or state.estimate_id != estimate_id:
        _fail('REPORT_REVIEW_PACKAGE_PROTECTED_STATE_INVALID')
    fingerprint = _sha256(
        state.fingerprint,
        code='REPORT_REVIEW_PACKAGE_PROTECTED_STATE_INVALID',
    )
    counts = state.counts
    if (
        not isinstance(counts, dict)
        or set(counts) != set(_STATE_COUNT_FIELDS)
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in counts.values()
        )
    ):
        _fail('REPORT_REVIEW_PACKAGE_PROTECTED_STATE_INVALID')
    snapshot = state.snapshot
    if (
        not isinstance(snapshot, dict)
        or snapshot.get('schema') != INITIAL_SUBMISSION_STATE_FINGERPRINT_VERSION
    ):
        _fail('REPORT_REVIEW_PACKAGE_PROTECTED_STATE_INVALID')
    return {
        'fingerprint': fingerprint,
        'snapshot_canonical_sha256': canonical_json_sha256(snapshot),
        'counts': {field: counts[field] for field in _STATE_COUNT_FIELDS},
    }


def _packet_identity(packet: ReportDefectEvidencePacket) -> dict[str, str]:
    manifest = packet.manifest
    return {
        'project_evidence_id': str(manifest['project_evidence_id']),
        'report_sha256': str(manifest['report_sha256']),
        'estimate_id': str(manifest['estimate_id']),
        'defect_id': str(manifest['defect_id']),
        'defect_reference': str(manifest['defect_reference']),
        'report_defect_label': str(manifest['report_defect_label']),
        'scope_id': str(manifest['scope_id']),
        'report_packet_manifest_sha256': packet.manifest_sha256,
    }


def _selected_packets(packets: object) -> tuple[ReportDefectEvidencePacket, ...]:
    if isinstance(packets, (str, bytes)) or not isinstance(packets, Sequence):
        _fail('REPORT_REVIEW_PACKAGE_PACKETS_INVALID')
    values = tuple(packets)
    if not values or any(not isinstance(packet, ReportDefectEvidencePacket) for packet in values):
        _fail('REPORT_REVIEW_PACKAGE_PACKETS_INVALID')
    if any(validate_report_defect_evidence_packet(packet) for packet in values):
        _fail('REPORT_REVIEW_PACKAGE_PACKETS_INVALID')
    identities = [_packet_identity(packet) for packet in values]
    first = identities[0]
    shared_fields = ('project_evidence_id', 'report_sha256', 'estimate_id')
    if any(
        any(identity[field] != first[field] for field in shared_fields)
        for identity in identities[1:]
    ):
        _fail('REPORT_REVIEW_PACKAGE_PACKET_GROUP_MISMATCH')
    for field in ('scope_id', 'defect_id', 'defect_reference'):
        values_for_field = [identity[field] for identity in identities]
        if len(values_for_field) != len(set(values_for_field)):
            _fail('REPORT_REVIEW_PACKAGE_PACKET_SCOPE_DUPLICATE')
    labels = [identity['report_defect_label'].casefold() for identity in identities]
    if len(labels) != len(set(labels)):
        _fail('REPORT_REVIEW_PACKAGE_REPORT_LABEL_DUPLICATE')
    return tuple(
        sorted(
            values,
            key=lambda packet: (
                str(packet.manifest['report_defect_label']).casefold(),
                str(packet.manifest['defect_reference']),
                str(packet.manifest['scope_id']),
            ),
        )
    )


def _outcomes(
    outcomes_by_scope: object,
    *,
    packets: tuple[ReportDefectEvidencePacket, ...],
) -> dict[str, ReportDefectReviewOutcome]:
    if not isinstance(outcomes_by_scope, Mapping):
        _fail('REPORT_REVIEW_PACKAGE_OUTCOMES_INVALID')
    expected_scope_ids = {str(packet.manifest['scope_id']) for packet in packets}
    actual_scope_ids = set(outcomes_by_scope)
    if actual_scope_ids != expected_scope_ids or any(
        not isinstance(scope_id, str) or not scope_id for scope_id in actual_scope_ids
    ):
        _fail('REPORT_REVIEW_PACKAGE_OUTCOMES_SCOPE_MISMATCH')
    if any(not isinstance(item, ReportDefectReviewOutcome) for item in outcomes_by_scope.values()):
        _fail('REPORT_REVIEW_PACKAGE_OUTCOMES_INVALID')
    return dict(outcomes_by_scope)


def _phase8_review_matches_package(
    review: object,
    *,
    package_id: str,
    package_sha256: str,
    approval_reference: str,
) -> None:
    if not isinstance(review, dict) or validate_phase8_proposal_review(review):
        _fail('REPORT_REVIEW_PACKAGE_PHASE8_REVIEW_INVALID')
    if (
        review.get('package_id') != package_id
        or review.get('package_sha256') != package_sha256
        or review.get('approval_reference') != approval_reference
    ):
        _fail('REPORT_REVIEW_PACKAGE_PHASE8_PACKAGE_MISMATCH')


def _artifact(
    packet: ReportDefectEvidencePacket,
    *,
    outcome: ReportDefectReviewOutcome,
    package_id: str,
    package_sha256: str,
    approval_reference: str,
) -> ReportDefectReviewArtifact:
    if outcome.phase8_proposal_review is not None:
        _phase8_review_matches_package(
            outcome.phase8_proposal_review,
            package_id=package_id,
            package_sha256=package_sha256,
            approval_reference=approval_reference,
        )
    review = build_phase8_report_defect_review(
        packet=packet,
        phase8_proposal_review=outcome.phase8_proposal_review,
        no_proposal_status=outcome.no_proposal_status,
        blocker_code=outcome.blocker_code,
    )
    if validate_phase8_report_defect_review(review):
        _fail('REPORT_REVIEW_PACKAGE_REVIEW_INVALID')
    return ReportDefectReviewArtifact(
        packet=packet,
        review=review,
        markdown=render_phase8_report_defect_review_markdown(review),
    )


def _manifest(
    *,
    package_id: str,
    package_sha256: str,
    approval_reference: str,
    artifacts: tuple[ReportDefectReviewArtifact, ...],
) -> dict[str, Any]:
    first = _packet_identity(artifacts[0].packet)
    selections = []
    for ordinal, artifact in enumerate(artifacts, start=1):
        identity = _packet_identity(artifact.packet)
        selections.append(
            {
                'ordinal': ordinal,
                'scope_id': identity['scope_id'],
                'defect_id': identity['defect_id'],
                'defect_reference': identity['defect_reference'],
                'report_defect_label': identity['report_defect_label'],
                'report_packet_manifest_sha256': identity['report_packet_manifest_sha256'],
            }
        )
    return {
        'schema': REPORT_REVIEW_PACKAGE_SCHEMA,
        'package_id': package_id,
        'package_sha256': package_sha256,
        'approval_reference': approval_reference,
        'project_evidence_id': first['project_evidence_id'],
        'report_sha256': first['report_sha256'],
        'estimate_id': first['estimate_id'],
        'selected_defect_count': len(artifacts),
        'selections': selections,
        'proposal_only': True,
        'canonical_submission_performed': False,
        'technical_selection_performed': False,
        'commercial_pricing_performed': False,
        'physical_model_lock_created': False,
        'human_release_performed': False,
    }


def _artifact_paths(ordinal: int) -> tuple[str, str, str]:
    prefix = f'{ordinal:04d}'
    return (
        f'report-defect-packets/{prefix}.json',
        f'report-defect-reviews/{prefix}.json',
        f'report-defect-reviews/{prefix}.md',
    )


def _base_files(
    manifest: dict[str, Any],
    artifacts: tuple[ReportDefectReviewArtifact, ...],
) -> dict[str, bytes]:
    files: dict[str, bytes] = {'report-review-package.json': _json_file_bytes(manifest)}
    for ordinal, artifact in enumerate(artifacts, start=1):
        packet_path, review_path, markdown_path = _artifact_paths(ordinal)
        files[packet_path] = _json_file_bytes(artifact.packet.manifest)
        files[review_path] = _json_file_bytes(artifact.review)
        files[markdown_path] = artifact.markdown.encode('utf-8')
    return files


def _completion_receipt(
    *,
    manifest: dict[str, Any],
    artifacts: tuple[ReportDefectReviewArtifact, ...],
    files: dict[str, bytes],
    protected_state_before: dict[str, Any],
    protected_state_after: dict[str, Any],
) -> dict[str, Any]:
    reviews = []
    for ordinal, artifact in enumerate(artifacts, start=1):
        packet_path, review_path, markdown_path = _artifact_paths(ordinal)
        identity = _packet_identity(artifact.packet)
        reviews.append(
            {
                'ordinal': ordinal,
                'scope_id': identity['scope_id'],
                'defect_id': identity['defect_id'],
                'defect_reference': identity['defect_reference'],
                'report_defect_label': identity['report_defect_label'],
                'review_status': artifact.review['review_status'],
                'phase8_review_status': artifact.review['phase8_review_binding'][
                    'phase8_review_status'
                ],
                'report_packet_manifest_sha256': identity['report_packet_manifest_sha256'],
                'review_canonical_sha256': canonical_json_sha256(artifact.review),
                'report_packet_file_sha256': _sha256_bytes(files[packet_path]),
                'review_file_sha256': _sha256_bytes(files[review_path]),
                'review_markdown_file_sha256': _sha256_bytes(files[markdown_path]),
            }
        )
    return {
        'schema': REPORT_REVIEW_COMPLETION_RECEIPT_SCHEMA,
        'status': 'COMPLETE_PROPOSAL_ONLY',
        'package_id': manifest['package_id'],
        'package_sha256': manifest['package_sha256'],
        'approval_reference': manifest['approval_reference'],
        'project_evidence_id': manifest['project_evidence_id'],
        'report_sha256': manifest['report_sha256'],
        'estimate_id': manifest['estimate_id'],
        'report_review_package_manifest_canonical_sha256': canonical_json_sha256(manifest),
        'selected_defect_count': len(artifacts),
        'reviews': reviews,
        'artifacts': {path: _sha256_bytes(value) for path, value in files.items()},
        'protected_state_before': protected_state_before,
        'protected_state_after': protected_state_after,
        'protected_state_unchanged': True,
        'proposal_only': True,
        'canonical_submission_performed': False,
        'technical_selection_performed': False,
        'commercial_pricing_performed': False,
        'physical_model_lock_created': False,
        'human_release_performed': False,
    }


def build_phase8_report_review_package(
    *,
    package_id: object,
    package_sha256: object,
    approval_reference: object,
    packets: object,
    outcomes_by_scope: object,
    protected_state_before: object,
    protected_state_after: object,
) -> Phase8ReportReviewPackage:
    '''Build complete in-memory files without retrieval, inference, or writes.'''

    identifier = _required_text(
        package_id,
        code='REPORT_REVIEW_PACKAGE_ID_INVALID',
        maximum=128,
    )
    if _PACKAGE_ID.fullmatch(identifier) is None:
        _fail('REPORT_REVIEW_PACKAGE_ID_INVALID')
    package_hash = _sha256(package_sha256, code='REPORT_REVIEW_PACKAGE_HASH_INVALID')
    approval = _required_text(
        approval_reference,
        code='REPORT_REVIEW_PACKAGE_APPROVAL_INVALID',
        maximum=500,
    )
    selected_packets = _selected_packets(packets)
    outcomes = _outcomes(outcomes_by_scope, packets=selected_packets)
    estimate_id = str(selected_packets[0].manifest['estimate_id'])
    before = _state_binding(protected_state_before, estimate_id=estimate_id)
    after = _state_binding(protected_state_after, estimate_id=estimate_id)
    if before != after:
        _fail('REPORT_REVIEW_PACKAGE_PROTECTED_STATE_CHANGED')
    artifacts = tuple(
        _artifact(
            packet,
            outcome=outcomes[str(packet.manifest['scope_id'])],
            package_id=identifier,
            package_sha256=package_hash,
            approval_reference=approval,
        )
        for packet in selected_packets
    )
    manifest = _manifest(
        package_id=identifier,
        package_sha256=package_hash,
        approval_reference=approval,
        artifacts=artifacts,
    )
    files = _base_files(manifest, artifacts)
    receipt = _completion_receipt(
        manifest=manifest,
        artifacts=artifacts,
        files=files,
        protected_state_before=before,
        protected_state_after=after,
    )
    files['completion-receipt.json'] = _json_file_bytes(receipt)
    result = Phase8ReportReviewPackage(
        manifest=manifest,
        artifacts=artifacts,
        completion_receipt=receipt,
        files=files,
    )
    if validate_phase8_report_review_package(result):
        _fail('REPORT_REVIEW_PACKAGE_BUILD_INVALID')
    return result


def _valid_state_binding(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {
        'fingerprint',
        'snapshot_canonical_sha256',
        'counts',
    }:
        return False
    counts = value.get('counts')
    return (
        _UPPER_SHA256.fullmatch(str(value.get('fingerprint') or '')) is not None
        and _UPPER_SHA256.fullmatch(str(value.get('snapshot_canonical_sha256') or '')) is not None
        and isinstance(counts, dict)
        and set(counts) == set(_STATE_COUNT_FIELDS)
        and all(
            not isinstance(count, bool) and isinstance(count, int) and count >= 0
            for count in counts.values()
        )
    )


def _valid_manifest_shape(manifest: object) -> bool:
    expected = {
        'schema',
        'package_id',
        'package_sha256',
        'approval_reference',
        'project_evidence_id',
        'report_sha256',
        'estimate_id',
        'selected_defect_count',
        'selections',
        'proposal_only',
        *_NOOP_FLAGS,
    }
    if not isinstance(manifest, dict) or set(manifest) != expected:
        return False
    if manifest.get('schema') != REPORT_REVIEW_PACKAGE_SCHEMA:
        return False
    if _PACKAGE_ID.fullmatch(str(manifest.get('package_id') or '')) is None:
        return False
    if _UPPER_SHA256.fullmatch(str(manifest.get('package_sha256') or '')) is None:
        return False
    report_sha256 = str(manifest.get('report_sha256') or '')
    if (
        len(report_sha256) != 64
        or report_sha256 != report_sha256.casefold()
        or any(character not in '0123456789abcdef' for character in report_sha256)
    ):
        return False
    if (
        not isinstance(manifest.get('selections'), list)
        or manifest.get('proposal_only') is not True
    ):
        return False
    if any(manifest.get(flag) is not False for flag in _NOOP_FLAGS):
        return False
    try:
        for field, maximum in (
            ('approval_reference', 500),
            ('project_evidence_id', 36),
            ('estimate_id', 36),
        ):
            _required_text(manifest.get(field), code='VALUE_INVALID', maximum=maximum)
    except Phase8ReportReviewPackageError:
        return False
    count = manifest.get('selected_defect_count')
    return not isinstance(count, bool) and isinstance(count, int) and count > 0


def validate_phase8_report_review_package(package: object) -> list[str]:
    '''Validate every file, scope, receipt, and no-write binding in a package.'''

    if not isinstance(package, Phase8ReportReviewPackage):
        return ['report review package has an unsupported type']
    manifest = package.manifest
    artifacts = package.artifacts
    receipt = package.completion_receipt
    files = package.files
    errors: list[str] = []
    if not _valid_manifest_shape(manifest):
        return ['report review package manifest is invalid']
    if not isinstance(artifacts, tuple) or len(artifacts) != manifest['selected_defect_count']:
        return ['report review package artifact count is invalid']

    packets: list[ReportDefectEvidencePacket] = []
    for ordinal, artifact in enumerate(artifacts, start=1):
        if not isinstance(artifact, ReportDefectReviewArtifact):
            errors.append(f'report review package artifact {ordinal} is invalid')
            continue
        if validate_report_defect_evidence_packet(artifact.packet):
            errors.append(f'report review package packet {ordinal} is invalid')
            continue
        if validate_phase8_report_defect_review(artifact.review):
            errors.append(f'report review package review {ordinal} is invalid')
            continue
        if artifact.markdown != render_phase8_report_defect_review_markdown(artifact.review):
            errors.append(f'report review package Markdown {ordinal} is invalid')
        identity = _packet_identity(artifact.packet)
        if any(
            artifact.review.get(field) != identity[field]
            for field in (
                'scope_id',
                'defect_id',
                'defect_reference',
                'report_defect_label',
                'report_packet_manifest_sha256',
            )
        ):
            errors.append(f'report review package review {ordinal} is not scope-bound')
        binding = artifact.review['phase8_review_binding']
        if binding['phase8_review_status'] is not None and (
            binding['package_id'] != manifest['package_id']
            or binding['package_sha256'] != manifest['package_sha256']
            or binding['approval_reference'] != manifest['approval_reference']
        ):
            errors.append(f'report review package review {ordinal} package binding is invalid')
        packets.append(artifact.packet)
    if errors:
        return list(dict.fromkeys(errors))
    try:
        if tuple(packets) != _selected_packets(packets):
            errors.append('report review package artifact order is not deterministic')
    except Phase8ReportReviewPackageError:
        errors.append('report review package packet collection is invalid')
    expected_manifest = _manifest(
        package_id=str(manifest['package_id']),
        package_sha256=str(manifest['package_sha256']),
        approval_reference=str(manifest['approval_reference']),
        artifacts=artifacts,
    )
    if manifest != expected_manifest:
        errors.append('report review package manifest is not scope-bound')
    base_files = _base_files(manifest, artifacts)
    if not isinstance(receipt, dict) or not _valid_state_binding(
        receipt.get('protected_state_before')
    ):
        errors.append('report review completion receipt protected state is invalid')
    elif receipt.get('protected_state_before') != receipt.get('protected_state_after'):
        errors.append('report review completion receipt protected state changed')
    else:
        expected_receipt = _completion_receipt(
            manifest=manifest,
            artifacts=artifacts,
            files=base_files,
            protected_state_before=receipt['protected_state_before'],
            protected_state_after=receipt['protected_state_after'],
        )
        if receipt != expected_receipt:
            errors.append('report review completion receipt is invalid')
    if not isinstance(files, dict):
        errors.append('report review package files are invalid')
    else:
        expected_files = dict(base_files)
        expected_files['completion-receipt.json'] = _json_file_bytes(receipt)
        if set(files) != set(expected_files) or any(
            not isinstance(value, bytes) for value in files.values()
        ):
            errors.append('report review package file paths are invalid')
        elif any(files[path] != value for path, value in expected_files.items()):
            errors.append('report review package file bytes are invalid')
    return list(dict.fromkeys(errors))


def materialise_phase8_report_review_package(
    package: object,
    *,
    output: object,
) -> str:
    '''Write an already-validated package once, without overwriting an output.'''

    if validate_phase8_report_review_package(package):
        _fail('REPORT_REVIEW_PACKAGE_OUTPUT_INVALID')
    if not isinstance(package, Phase8ReportReviewPackage) or not isinstance(output, Path):
        _fail('REPORT_REVIEW_PACKAGE_OUTPUT_INVALID')
    if not output.name:
        _fail('REPORT_REVIEW_PACKAGE_OUTPUT_INVALID')
    try:
        parent = output.parent.resolve(strict=True)
    except OSError as exc:
        raise Phase8ReportReviewPackageError('REPORT_REVIEW_PACKAGE_OUTPUT_INVALID') from exc
    target = parent / output.name
    if not parent.is_dir() or target.exists():
        _fail('REPORT_REVIEW_PACKAGE_OUTPUT_EXISTS')
    temporary = Path(tempfile.mkdtemp(prefix='.classifire-report-review-', dir=parent))
    try:
        for relative_path, expected_bytes in package.files.items():
            destination = temporary / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(expected_bytes)
            if destination.read_bytes() != expected_bytes:
                _fail('REPORT_REVIEW_PACKAGE_OUTPUT_VERIFICATION_FAILED')
        if target.exists():
            _fail('REPORT_REVIEW_PACKAGE_OUTPUT_EXISTS')
        temporary.replace(target)
    except Phase8ReportReviewPackageError:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    except OSError as exc:
        shutil.rmtree(temporary, ignore_errors=True)
        raise Phase8ReportReviewPackageError('REPORT_REVIEW_PACKAGE_OUTPUT_WRITE_FAILED') from exc
    completion = target / 'completion-receipt.json'
    try:
        if completion.read_bytes() != package.files['completion-receipt.json']:
            _fail('REPORT_REVIEW_PACKAGE_OUTPUT_VERIFICATION_FAILED')
    except OSError as exc:
        raise Phase8ReportReviewPackageError(
            'REPORT_REVIEW_PACKAGE_OUTPUT_VERIFICATION_FAILED'
        ) from exc
    return _sha256_bytes(package.files['completion-receipt.json'])


__all__ = [
    'Phase8ReportReviewPackage',
    'Phase8ReportReviewPackageError',
    'REPORT_REVIEW_COMPLETION_RECEIPT_SCHEMA',
    'REPORT_REVIEW_PACKAGE_SCHEMA',
    'ReportDefectReviewArtifact',
    'ReportDefectReviewOutcome',
    'build_phase8_report_review_package',
    'materialise_phase8_report_review_package',
    'validate_phase8_report_review_package',
]
