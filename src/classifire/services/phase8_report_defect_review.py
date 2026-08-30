'''Deterministic, proposal-only review artifacts for selected report Defects.'''

from __future__ import annotations

import re
from typing import Any, NoReturn

from .phase8_proposal_review import (
    PHASE8_PROPOSAL_REVIEW_SCHEMA,
    validate_phase8_proposal_review,
)
from .phase8_visual_proposal import canonical_json_sha256
from .report_evidence_adapter import (
    ReportDefectEvidencePacket,
    validate_report_defect_evidence_packet,
)

PHASE8_REPORT_DEFECT_REVIEW_SCHEMA = 'CLASSIFIRE-PHASE8-REPORT-DEFECT-REVIEW-v1'

_NO_PROPOSAL_STATUSES = frozenset({'RETRIEVAL_BLOCKED', 'MALFORMED_INPUT'})
_PHASE8_REVIEW_STATUSES = frozenset(
    {
        'ASSESSMENT_AVAILABLE',
        'NO_PROPOSAL',
        'LEGACY_POLICY_UNASSESSED',
        'INVALID_BLOCKED_PROPOSAL',
        'NON_REVIEWABLE_CONTROLLER_OUTCOME',
        'INSUFFICIENT_EVIDENCE',
    }
)
_NOOP_FLAGS = (
    'canonical_submission_performed',
    'technical_selection_performed',
    'commercial_pricing_performed',
    'physical_model_lock_created',
    'human_release_performed',
)
_BINDING_FIELDS = (
    'phase8_proposal_review_canonical_sha256',
    'phase8_review_status',
    'controller_receipt_file_sha256',
    'controller_receipt_canonical_sha256',
    'visual_evidence_manifest_canonical_sha256',
    'inference_profile_sha256',
    'proposal_file_sha256',
    'proposal_canonical_sha256',
)
_CANONICAL_HASH = re.compile(r'^[0-9A-F]{64}$')
_SOURCE_HASH = re.compile(r'^[0-9a-f]{64}$')
_SAFE_CODE = re.compile(r'^[A-Z][A-Z0-9_]{0,119}$')


class Phase8ReportDefectReviewError(ValueError):
    '''A stable, content-safe failure while preparing a report-Defect review.'''

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise Phase8ReportDefectReviewError(code)


def _safe_text(value: object, *, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text if text and len(text) <= maximum else None


def _packet_manifest(packet: object) -> dict[str, Any]:
    if not isinstance(packet, ReportDefectEvidencePacket):
        _fail('REPORT_DEFECT_REVIEW_PACKET_INVALID')
    if validate_report_defect_evidence_packet(packet):
        _fail('REPORT_DEFECT_REVIEW_PACKET_INVALID')
    return packet.manifest


def _empty_phase8_binding() -> dict[str, None]:
    return {field: None for field in _BINDING_FIELDS}


def _phase8_binding(
    review: object,
    *,
    manifest: dict[str, Any],
) -> dict[str, str | None]:
    errors = validate_phase8_proposal_review(review)
    if errors or not isinstance(review, dict):
        _fail('REPORT_DEFECT_REVIEW_PHASE8_REVIEW_INVALID')
    if review.get('schema') != PHASE8_PROPOSAL_REVIEW_SCHEMA:
        _fail('REPORT_DEFECT_REVIEW_PHASE8_REVIEW_INVALID')
    if (
        review.get('estimate_id') != manifest['estimate_id']
        or review.get('defect_reference') != manifest['defect_reference']
    ):
        _fail('REPORT_DEFECT_REVIEW_PHASE8_SCOPE_MISMATCH')
    input_bindings = review.get('input_bindings')
    if not isinstance(input_bindings, dict):
        _fail('REPORT_DEFECT_REVIEW_PHASE8_REVIEW_INVALID')
    return {
        'phase8_proposal_review_canonical_sha256': canonical_json_sha256(review),
        'phase8_review_status': str(review['review_status']),
        'controller_receipt_file_sha256': str(input_bindings['controller_receipt_file_sha256']),
        'controller_receipt_canonical_sha256': str(
            input_bindings['controller_receipt_canonical_sha256']
        ),
        'visual_evidence_manifest_canonical_sha256': str(
            input_bindings['evidence_manifest_canonical_sha256']
        ),
        'inference_profile_sha256': str(input_bindings['inference_profile_sha256']),
        'proposal_file_sha256': (
            str(input_bindings['proposal_file_sha256'])
            if input_bindings['proposal_file_sha256'] is not None
            else None
        ),
        'proposal_canonical_sha256': (
            str(input_bindings['proposal_canonical_sha256'])
            if input_bindings['proposal_canonical_sha256'] is not None
            else None
        ),
    }


def _review_base(manifest: dict[str, Any]) -> dict[str, Any]:
    artifacts = manifest['artifacts']
    return {
        'schema': PHASE8_REPORT_DEFECT_REVIEW_SCHEMA,
        'review_status': None,
        'report_packet_manifest_sha256': canonical_json_sha256(manifest),
        'report_sha256': manifest['report_sha256'],
        'estimate_id': manifest['estimate_id'],
        'defect_id': manifest['defect_id'],
        'defect_reference': manifest['defect_reference'],
        'report_defect_label': manifest['report_defect_label'],
        'scope_id': manifest['scope_id'],
        'start_locator_key': manifest['start_locator_key'],
        'end_locator_key': manifest['end_locator_key'],
        'scope_locator_count': len(artifacts),
        'phase8_review_binding': _empty_phase8_binding(),
        'blocker_code': None,
        'proposal_only': True,
        'canonical_submission_performed': False,
        'technical_selection_performed': False,
        'commercial_pricing_performed': False,
        'physical_model_lock_created': False,
        'human_release_performed': False,
    }


def build_phase8_report_defect_review(
    *,
    packet: object,
    phase8_proposal_review: object | None = None,
    no_proposal_status: object | None = None,
    blocker_code: object | None = None,
) -> dict[str, Any]:
    '''Build one report-bound review without performing inference or writes.'''

    manifest = _packet_manifest(packet)
    review = _review_base(manifest)
    if phase8_proposal_review is not None:
        if no_proposal_status is not None or blocker_code is not None:
            _fail('REPORT_DEFECT_REVIEW_INPUT_CONFLICT')
        review['review_status'] = 'PHASE8_REVIEW_AVAILABLE'
        review['phase8_review_binding'] = _phase8_binding(
            phase8_proposal_review,
            manifest=manifest,
        )
        return review

    status = _safe_text(no_proposal_status, maximum=80)
    code = _safe_text(blocker_code, maximum=120)
    if status not in _NO_PROPOSAL_STATUSES or code is None or _SAFE_CODE.fullmatch(code) is None:
        _fail('REPORT_DEFECT_REVIEW_NO_PROPOSAL_INVALID')
    review['review_status'] = status
    review['blocker_code'] = code
    return review


def validate_phase8_report_defect_review(review: object) -> list[str]:
    '''Validate a report-bound review before rendering or downstream retention.'''

    if not isinstance(review, dict):
        return ['report Defect review must be an object']
    expected = {
        'schema',
        'review_status',
        'report_packet_manifest_sha256',
        'report_sha256',
        'estimate_id',
        'defect_id',
        'defect_reference',
        'report_defect_label',
        'scope_id',
        'start_locator_key',
        'end_locator_key',
        'scope_locator_count',
        'phase8_review_binding',
        'blocker_code',
        'proposal_only',
        *_NOOP_FLAGS,
    }
    errors: list[str] = []
    if set(review) != expected:
        errors.append('report Defect review fields do not match the approved schema')
    if review.get('schema') != PHASE8_REPORT_DEFECT_REVIEW_SCHEMA:
        errors.append('report Defect review schema is unsupported')
    status = review.get('review_status')
    if status not in {*_NO_PROPOSAL_STATUSES, 'PHASE8_REVIEW_AVAILABLE'}:
        errors.append('report Defect review status is unsupported')
    if not _CANONICAL_HASH.fullmatch(str(review.get('report_packet_manifest_sha256') or '')):
        errors.append('report Defect review packet hash is invalid')
    if not _SOURCE_HASH.fullmatch(str(review.get('report_sha256') or '')):
        errors.append('report Defect review report hash is invalid')
    for field, maximum in (
        ('estimate_id', 36),
        ('defect_id', 36),
        ('defect_reference', 150),
        ('report_defect_label', 150),
        ('scope_id', 36),
        ('start_locator_key', 300),
        ('end_locator_key', 300),
    ):
        if _safe_text(review.get(field), maximum=maximum) is None:
            errors.append(f'report Defect review {field} is invalid')
    count = review.get('scope_locator_count')
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        errors.append('report Defect review scope locator count is invalid')
    if review.get('proposal_only') is not True:
        errors.append('report Defect review must remain proposal-only')
    for field in _NOOP_FLAGS:
        if review.get(field) is not False:
            errors.append(f'report Defect review {field} must be false')

    binding = review.get('phase8_review_binding')
    if not isinstance(binding, dict) or set(binding) != set(_BINDING_FIELDS):
        errors.append('report Defect review Phase 8 binding is invalid')
    elif status == 'PHASE8_REVIEW_AVAILABLE':
        if binding.get('phase8_review_status') not in _PHASE8_REVIEW_STATUSES:
            errors.append('report Defect review Phase 8 status is invalid')
        for field, value in binding.items():
            if field in {'proposal_file_sha256', 'proposal_canonical_sha256'} and value is None:
                continue
            if field == 'phase8_review_status':
                continue
            if not _CANONICAL_HASH.fullmatch(str(value or '')):
                errors.append(f'report Defect review binding {field} is invalid')
        if review.get('blocker_code') is not None:
            errors.append('proposal-backed report Defect review cannot have a blocker code')
    elif status in _NO_PROPOSAL_STATUSES:
        if any(value is not None for value in binding.values()):
            errors.append('no-proposal report Defect review must not bind a Phase 8 review')
        code = review.get('blocker_code')
        if not isinstance(code, str) or _SAFE_CODE.fullmatch(code) is None:
            errors.append('no-proposal report Defect review blocker code is invalid')
    return list(dict.fromkeys(errors))


def _markdown_text(value: object) -> str:
    text = ' '.join(str(value or 'Unknown').split())
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    text = text.replace('://', ': //').replace('www.', 'www .')
    for character in '\\`[]()!#*_|':
        text = text.replace(character, chr(92) + character)
    return text or 'Unknown'


def render_phase8_report_defect_review_markdown(review: object) -> str:
    '''Render a validated report-bound review without active Markdown content.'''

    errors = validate_phase8_report_defect_review(review)
    if errors:
        raise Phase8ReportDefectReviewError('REPORT_DEFECT_REVIEW_RENDER_INVALID')
    if not isinstance(review, dict):
        raise Phase8ReportDefectReviewError('REPORT_DEFECT_REVIEW_RENDER_INVALID')
    lines = [
        '# CLASSIFIRE report Defect proposal-only review',
        '',
        f"- Defect: {_markdown_text(review['defect_reference'])}",
        f"- Report label: {_markdown_text(review['report_defect_label'])}",
        f"- Review status: {_markdown_text(review['review_status'])}",
        f"- Report hash: {_markdown_text(review['report_sha256'])}",
        (
            '- This record does not approve a physical model, select a technical '
            'system, price work, lock state, or release an output.'
        ),
    ]
    if review['review_status'] == 'PHASE8_REVIEW_AVAILABLE':
        binding = review['phase8_review_binding']
        lines.extend(
            [
                '',
                '## Bound Phase 8 review',
                '',
                f"- Status: {_markdown_text(binding['phase8_review_status'])}",
                (
                    '- The controller receipt, evidence manifest, inference profile, '
                    'proposal, and package bindings remain in the hash-bound Phase 8 '
                    'review artifact.'
                ),
            ]
        )
    else:
        lines.extend(
            [
                '',
                '## No-proposal outcome',
                '',
                f"- Blocker code: {_markdown_text(review['blocker_code'])}",
                '- No physical conclusion has been created from this report range.',
            ]
        )
    return '\n'.join(lines) + '\n'


__all__ = [
    'PHASE8_REPORT_DEFECT_REVIEW_SCHEMA',
    'Phase8ReportDefectReviewError',
    'build_phase8_report_defect_review',
    'render_phase8_report_defect_review_markdown',
    'validate_phase8_report_defect_review',
]
