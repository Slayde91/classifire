from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from typing import Any

import pymupdf
import pytest
from test_report_evidence_adapter import _caption_report_content, _report_content

from classifire.services.phase8_report_documentary_context import (
    PHASE8_REPORT_DOCUMENTARY_CONTEXT_SCHEMA,
    Phase8ReportDocumentaryContextError,
    TransientReportDocumentaryItem,
    build_phase8_report_documentary_context,
    validate_phase8_report_documentary_context,
)
from classifire.services.phase8_visual_proposal import canonical_json_sha256
from classifire.services.report_evidence_adapter import (
    REPORT_DEFECT_EVIDENCE_PACKET_SCHEMA,
    ReportDefectEvidencePacket,
    normalise_verified_pdf_report,
)
from classifire.services.storage import VerifiedStoredFileContent


def _packet(
    content: VerifiedStoredFileContent,
    *,
    item_kind: str | None = None,
) -> ReportDefectEvidencePacket:
    report = normalise_verified_pdf_report(content)
    locators = tuple(
        locator
        for locator in report.locators
        if item_kind is None or locator.item_kind == item_kind
    )
    assert locators
    artifacts = [
        {
            'evidence_id': f'report-locator:{locator.locator_key}',
            'sequence': locator.locator['sequence'],
            'locator_key': locator.locator_key,
            'item_kind': locator.item_kind,
            'page_number': locator.page_number,
            'content_sha256': locator.content_sha256,
            'locator': deepcopy(locator.locator),
        }
        for locator in locators
    ]
    manifest = {
        'schema': REPORT_DEFECT_EVIDENCE_PACKET_SCHEMA,
        'project_evidence_id': 'PROJECT-EVIDENCE-001',
        'report_sha256': report.source_sha256,
        'source_size_bytes': report.source_size_bytes,
        'estimate_id': 'ESTIMATE-001',
        'defect_id': 'DEFECT-001',
        'defect_reference': 'D-001',
        'report_defect_label': 'D-001',
        'scope_id': 'SCOPE-001',
        'start_locator_key': artifacts[0]['locator_key'],
        'end_locator_key': artifacts[-1]['locator_key'],
        'artifacts': artifacts,
    }
    return ReportDefectEvidencePacket(
        manifest=manifest,
        manifest_sha256=canonical_json_sha256(manifest),
    )


def _content_by_kind(context: object, item_kind: str) -> dict[str, Any] | None:
    assert hasattr(context, 'items')
    return next(item.content for item in context.items if item.item_kind == item_kind)


def _table_report_content() -> VerifiedStoredFileContent:
    document = pymupdf.open()
    try:
        page = document.new_page()
        for position in (50, 150, 250):
            page.draw_line((position, 50), (position, 150))
        for position in (50, 100, 150):
            page.draw_line((50, position), (250, position))
        page.insert_text((60, 80), 'A')
        page.insert_text((160, 80), 'B')
        page.insert_text((60, 130), 'C')
        page.insert_text((160, 130), 'D')
        payload = document.tobytes(garbage=3, deflate=True)
    finally:
        document.close()
    return VerifiedStoredFileContent(
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        media_type='application/pdf',
        content=payload,
    )


def test_context_is_deterministic_selected_and_safe_to_log() -> None:
    content = _report_content()
    packet = _packet(content)

    first = build_phase8_report_documentary_context(
        report_packet=packet,
        verified_content=content,
    )
    repeated = build_phase8_report_documentary_context(
        report_packet=packet,
        verified_content=content,
    )

    assert validate_phase8_report_documentary_context(first) == []
    assert first.manifest == repeated.manifest
    assert first.manifest_sha256 == repeated.manifest_sha256
    assert first.manifest['schema'] == PHASE8_REPORT_DOCUMENTARY_CONTEXT_SCHEMA
    assert first.manifest['runtime_inference_performed'] is False
    assert first.manifest['transient_content_only'] is True
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
    assert 'Defect D-001 is described in this private report.' in _content_by_kind(
        first,
        'page',
    )['text']
    assert _content_by_kind(first, 'annotation')['info']['content'] == 'Private annotation content'
    assert _content_by_kind(first, 'drawing') is None
    assert _content_by_kind(first, 'image') is None
    assert 'Private report heading' not in str(first)
    assert 'Private annotation content' not in json.dumps(first.manifest, sort_keys=True)
    assert 'report.pdf' not in str(first)


def test_context_exposes_only_the_packet_selected_item() -> None:
    content = _report_content()
    packet = _packet(content, item_kind='text')

    context = build_phase8_report_documentary_context(
        report_packet=packet,
        verified_content=content,
    )

    assert len(context.items) == 1
    assert context.items[0].item_kind == 'text'
    assert context.items[0].content == {
        'text': 'Defect D-001 is described in this private report.\n'
    }
    assert context.evidence_refs == packet.evidence_refs


def test_context_reextracts_selected_caption_from_exact_report_bytes() -> None:
    caption_text = 'Figure 12: Proposed service penetration context.'
    content = _caption_report_content(caption_text=caption_text)
    packet = _packet(content, item_kind='caption')

    context = build_phase8_report_documentary_context(
        report_packet=packet,
        verified_content=content,
    )

    assert len(context.items) == 1
    assert context.items[0].item_kind == 'caption'
    assert context.items[0].content == {'text': f'{caption_text}\n'}
    assert caption_text not in json.dumps(context.manifest, sort_keys=True)
    assert validate_phase8_report_documentary_context(context) == []


def test_context_extracts_a_selected_table_from_exact_report_bytes() -> None:
    content = _table_report_content()
    packet = _packet(content, item_kind='table')

    context = build_phase8_report_documentary_context(
        report_packet=packet,
        verified_content=content,
    )

    assert len(context.items) == 1
    assert context.items[0].item_kind == 'table'
    assert context.items[0].content == {'rows': [['A', 'B'], ['C', 'D']]}
    assert validate_phase8_report_documentary_context(context) == []


def test_context_rejects_mismatched_or_tampered_content() -> None:
    content = _report_content()
    packet = _packet(content)
    context = build_phase8_report_documentary_context(
        report_packet=packet,
        verified_content=content,
    )
    text_item = next(item for item in context.items if item.item_kind == 'text')
    forged_item = replace(text_item, content={'text': 'Tampered report text.'})
    forged = replace(
        context,
        items=tuple(forged_item if item is text_item else item for item in context.items),
    )

    errors = validate_phase8_report_documentary_context(forged)
    assert any('content hash is invalid' in error for error in errors)

    different = VerifiedStoredFileContent(
        sha256=content.sha256,
        size_bytes=content.size_bytes,
        media_type=content.media_type,
        content=content.content + b' ',
    )
    with pytest.raises(Phase8ReportDocumentaryContextError) as raised:
        build_phase8_report_documentary_context(
            report_packet=packet,
            verified_content=different,
        )

    assert raised.value.code == 'REPORT_DOCUMENTARY_CONTEXT_REPORT_INVALID'


def test_context_validator_fails_closed_on_malformed_item_without_raising() -> None:
    content = _report_content()
    context = build_phase8_report_documentary_context(
        report_packet=_packet(content),
        verified_content=content,
    )
    malformed = TransientReportDocumentaryItem(
        evidence_id=context.items[0].evidence_id,
        item_kind=context.items[0].item_kind,
        page_number=context.items[0].page_number,
        content_sha256=context.items[0].content_sha256,
        content={'unsupported': object()},
    )
    forged = replace(context, items=(malformed, *context.items[1:]))

    errors = validate_phase8_report_documentary_context(forged)

    assert any('content is invalid' in error for error in errors)
