'''Transient, hash-checked documentary context for one report Defect.

The report packet intentionally contains no report text or raw PDF bytes. This
module is the narrow bridge a separately authorised controller can use to
prepare selected documentary content in memory. It accepts only already
verified bytes, proves those bytes still produce the selected locators, and
never reads a path, persists content, invokes inference, or writes canonical
state.
'''

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass, field
from typing import Any, NoReturn

import pymupdf

from .phase8_visual_proposal import canonical_json_sha256
from .report_evidence_adapter import (
    NormalisedReportEvidence,
    ReportDefectEvidencePacket,
    ReportEvidenceAdapterError,
    normalise_verified_pdf_report,
    validate_report_defect_evidence_packet,
)
from .storage import VerifiedStoredFileContent

PHASE8_REPORT_DOCUMENTARY_CONTEXT_SCHEMA = 'CLASSIFIRE-PHASE8-REPORT-DOCUMENTARY-CONTEXT-v1'

_MAX_TEXT_CHARACTERS = 1_000_000
_MAX_TABLE_ROWS = 2_000
_MAX_TABLE_COLUMNS = 200
_MAX_TABLE_CELLS = 100_000
_MAX_CONTEXT_CHARACTERS = 4_000_000
_NON_TEXT_ITEM_KINDS = frozenset({'drawing', 'image'})
_NOOP_FLAGS = (
    'canonical_submission_performed',
    'technical_selection_performed',
    'commercial_pricing_performed',
    'physical_model_lock_created',
    'human_release_performed',
)


class Phase8ReportDocumentaryContextError(ValueError):
    '''A stable, path-free documentary-context preparation failure.'''

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise Phase8ReportDocumentaryContextError(code)


@dataclass(frozen=True, slots=True)
class TransientReportDocumentaryItem:
    '''One selected report item with transient text or table content when available.'''

    evidence_id: str
    item_kind: str
    page_number: int | None
    content_sha256: str
    content: dict[str, Any] | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class Phase8ReportDocumentaryContext:
    '''One in-memory, source-bound documentary context for a selected Defect.'''

    packet: ReportDefectEvidencePacket
    manifest: dict[str, Any]
    manifest_sha256: str
    items: tuple[TransientReportDocumentaryItem, ...] = field(repr=False)

    @property
    def evidence_refs(self) -> frozenset[str]:
        return frozenset(item.evidence_id for item in self.items)


def _canonical_sha256(value: object) -> str:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
            allow_nan=False,
        ).encode('utf-8')
    except (TypeError, ValueError) as exc:
        _fail('REPORT_DOCUMENTARY_CONTEXT_SERIALISATION_INVALID')
        raise AssertionError from exc
    return hashlib.sha256(payload).hexdigest()


def _normalised_text(value: object) -> str:
    if not isinstance(value, str):
        _fail('REPORT_DOCUMENTARY_CONTEXT_CONTENT_INVALID')
    text = unicodedata.normalize('NFC', value).replace('\r\n', '\n').replace('\r', '\n')
    if len(text) > _MAX_TEXT_CHARACTERS:
        _fail('REPORT_DOCUMENTARY_CONTEXT_CONTENT_OUT_OF_POLICY')
    return text


def _text_sha256(value: object) -> str:
    return hashlib.sha256(_normalised_text(value).encode('utf-8')).hexdigest()


def _table_rows(value: object) -> tuple[list[list[str]], int]:
    if not isinstance(value, list) or len(value) > _MAX_TABLE_ROWS:
        _fail('REPORT_DOCUMENTARY_CONTEXT_CONTENT_INVALID')
    rows: list[list[str]] = []
    character_count = 0
    maximum_columns = 0
    for row in value:
        if not isinstance(row, list) or len(row) > _MAX_TABLE_COLUMNS:
            _fail('REPORT_DOCUMENTARY_CONTEXT_CONTENT_INVALID')
        cells: list[str] = []
        for cell in row:
            text = _normalised_text(cell)
            if cell != text:
                _fail('REPORT_DOCUMENTARY_CONTEXT_CONTENT_INVALID')
            character_count += len(text)
            cells.append(text)
        rows.append(cells)
        maximum_columns = max(maximum_columns, len(cells))
    if len(rows) * maximum_columns > _MAX_TABLE_CELLS:
        _fail('REPORT_DOCUMENTARY_CONTEXT_CONTENT_OUT_OF_POLICY')
    return rows, character_count


def _text_mapping(value: object) -> tuple[dict[str, str], int]:
    if not isinstance(value, dict):
        _fail('REPORT_DOCUMENTARY_CONTEXT_CONTENT_INVALID')
    fields: dict[str, str] = {}
    character_count = 0
    for key, raw in value.items():
        if not isinstance(key, str) or not key or len(key) > 300:
            _fail('REPORT_DOCUMENTARY_CONTEXT_CONTENT_INVALID')
        text = _normalised_text(raw)
        if raw != text:
            _fail('REPORT_DOCUMENTARY_CONTEXT_CONTENT_INVALID')
        fields[key] = text
        character_count += len(text)
    return fields, character_count


def _payload_hash_and_characters(
    *,
    item_kind: str,
    locator: object,
    content: object,
) -> tuple[str | None, int]:
    if not isinstance(locator, dict):
        _fail('REPORT_DOCUMENTARY_CONTEXT_PACKET_INVALID')
    if item_kind in _NON_TEXT_ITEM_KINDS:
        if content is not None:
            _fail('REPORT_DOCUMENTARY_CONTEXT_CONTENT_INVALID')
        return None, 0
    if not isinstance(content, dict):
        _fail('REPORT_DOCUMENTARY_CONTEXT_CONTENT_INVALID')
    if item_kind == 'metadata':
        if set(content) != {'fields'}:
            _fail('REPORT_DOCUMENTARY_CONTEXT_CONTENT_INVALID')
        fields, character_count = _text_mapping(content['fields'])
        if len(fields) != locator.get('metadata_field_count'):
            _fail('REPORT_DOCUMENTARY_CONTEXT_CONTENT_INVALID')
        metadata_hashes = {key: _text_sha256(value) for key, value in fields.items()}
        return _canonical_sha256(metadata_hashes), character_count
    if item_kind in {'page', 'text'}:
        if set(content) != {'text'}:
            _fail('REPORT_DOCUMENTARY_CONTEXT_CONTENT_INVALID')
        text = _normalised_text(content['text'])
        if content['text'] != text:
            _fail('REPORT_DOCUMENTARY_CONTEXT_CONTENT_INVALID')
        return _text_sha256(text), len(text)
    if item_kind == 'table':
        if set(content) != {'rows'}:
            _fail('REPORT_DOCUMENTARY_CONTEXT_CONTENT_INVALID')
        rows, character_count = _table_rows(content['rows'])
        if (
            len(rows) != locator.get('row_count')
            or max((len(row) for row in rows), default=0) != locator.get('column_count')
        ):
            _fail('REPORT_DOCUMENTARY_CONTEXT_CONTENT_INVALID')
        return _canonical_sha256(rows), character_count
    if item_kind == 'annotation':
        if set(content) != {'info'}:
            _fail('REPORT_DOCUMENTARY_CONTEXT_CONTENT_INVALID')
        info, character_count = _text_mapping(content['info'])
        shape = {
            'type': locator.get('annotation_type'),
            'bounds': locator.get('bounds'),
            'info_sha256': _canonical_sha256(
                {key: _text_sha256(value) for key, value in info.items()}
            ),
        }
        return _canonical_sha256(shape), character_count
    _fail('REPORT_DOCUMENTARY_CONTEXT_CONTENT_INVALID')


def _packet_artifacts(
    packet: object,
) -> tuple[ReportDefectEvidencePacket, tuple[dict[str, Any], ...]]:
    if not isinstance(packet, ReportDefectEvidencePacket):
        _fail('REPORT_DOCUMENTARY_CONTEXT_PACKET_INVALID')
    if validate_report_defect_evidence_packet(packet):
        _fail('REPORT_DOCUMENTARY_CONTEXT_PACKET_INVALID')
    artifacts = packet.manifest.get('artifacts')
    if not isinstance(artifacts, list) or any(not isinstance(item, dict) for item in artifacts):
        _fail('REPORT_DOCUMENTARY_CONTEXT_PACKET_INVALID')
    return packet, tuple(artifacts)


def _source_matches_packet(
    packet: ReportDefectEvidencePacket,
    artifacts: tuple[dict[str, Any], ...],
    source: NormalisedReportEvidence,
) -> None:
    if source.source_sha256 != packet.manifest['report_sha256'] or (
        source.source_size_bytes != packet.manifest['source_size_bytes']
    ):
        _fail('REPORT_DOCUMENTARY_CONTEXT_SOURCE_MISMATCH')
    locators = {item.locator_key: item for item in source.locators}
    for artifact in artifacts:
        actual = locators.get(artifact['locator_key'])
        if actual is None or (
            actual.item_kind != artifact['item_kind']
            or actual.page_number != artifact['page_number']
            or actual.content_sha256 != artifact['content_sha256']
            or actual.locator != artifact['locator']
            or actual.locator.get('sequence') != artifact['sequence']
        ):
            _fail('REPORT_DOCUMENTARY_CONTEXT_SOURCE_MISMATCH')


def _metadata_content(document: Any) -> dict[str, Any]:
    values = document.metadata or {}
    if not isinstance(values, dict):
        _fail('REPORT_DOCUMENTARY_CONTEXT_REPORT_INVALID')
    return {
        'fields': {
            str(key): _normalised_text(value)
            for key, value in values.items()
            if value is not None
        }
    }


def _page(document: Any, page_number: object) -> Any:
    if not isinstance(page_number, int) or page_number < 1:
        _fail('REPORT_DOCUMENTARY_CONTEXT_PACKET_INVALID')
    try:
        return document.load_page(page_number - 1)
    except Exception as exc:
        raise Phase8ReportDocumentaryContextError(
            'REPORT_DOCUMENTARY_CONTEXT_SOURCE_MISMATCH'
        ) from exc


def _text_content(page: Any, locator: dict[str, Any]) -> dict[str, Any]:
    block_index = locator.get('block_index')
    if not isinstance(block_index, int) or block_index < 1:
        _fail('REPORT_DOCUMENTARY_CONTEXT_PACKET_INVALID')
    try:
        blocks = list(page.get_text('blocks', sort=True))
    except Exception as exc:
        raise Phase8ReportDocumentaryContextError(
            'REPORT_DOCUMENTARY_CONTEXT_REPORT_INVALID'
        ) from exc
    if block_index > len(blocks):
        _fail('REPORT_DOCUMENTARY_CONTEXT_SOURCE_MISMATCH')
    block = blocks[block_index - 1]
    if not isinstance(block, tuple) or len(block) < 7 or int(block[6]) != 0:
        _fail('REPORT_DOCUMENTARY_CONTEXT_SOURCE_MISMATCH')
    return {'text': _normalised_text(block[4])}


def _table_content(page: Any, locator: dict[str, Any]) -> dict[str, Any]:
    table_index = locator.get('table_index')
    if not isinstance(table_index, int) or table_index < 1:
        _fail('REPORT_DOCUMENTARY_CONTEXT_PACKET_INVALID')
    try:
        tables = list(page.find_tables().tables)
    except Exception as exc:
        raise Phase8ReportDocumentaryContextError(
            'REPORT_DOCUMENTARY_CONTEXT_REPORT_INVALID'
        ) from exc
    if table_index > len(tables):
        _fail('REPORT_DOCUMENTARY_CONTEXT_SOURCE_MISMATCH')
    try:
        extracted = tables[table_index - 1].extract()
    except Exception as exc:
        raise Phase8ReportDocumentaryContextError(
            'REPORT_DOCUMENTARY_CONTEXT_REPORT_INVALID'
        ) from exc
    if not isinstance(extracted, list):
        _fail('REPORT_DOCUMENTARY_CONTEXT_SOURCE_MISMATCH')
    rows = [
        [_normalised_text('' if cell is None else str(cell)) for cell in row]
        for row in extracted
        if isinstance(row, list)
    ]
    if len(rows) != len(extracted):
        _fail('REPORT_DOCUMENTARY_CONTEXT_SOURCE_MISMATCH')
    return {'rows': rows}


def _annotation_content(page: Any, locator: dict[str, Any]) -> dict[str, Any]:
    annotation_index = locator.get('annotation_index')
    if not isinstance(annotation_index, int) or annotation_index < 1:
        _fail('REPORT_DOCUMENTARY_CONTEXT_PACKET_INVALID')
    try:
        annotations = tuple(page.annots() or ())
    except Exception as exc:
        raise Phase8ReportDocumentaryContextError(
            'REPORT_DOCUMENTARY_CONTEXT_REPORT_INVALID'
        ) from exc
    if annotation_index > len(annotations):
        _fail('REPORT_DOCUMENTARY_CONTEXT_SOURCE_MISMATCH')
    info = annotations[annotation_index - 1].info or {}
    if not isinstance(info, dict):
        _fail('REPORT_DOCUMENTARY_CONTEXT_SOURCE_MISMATCH')
    return {'info': {str(key): _normalised_text(value) for key, value in info.items()}}


def _content(document: Any, artifact: dict[str, Any]) -> dict[str, Any] | None:
    item_kind = artifact['item_kind']
    locator = artifact['locator']
    if item_kind in _NON_TEXT_ITEM_KINDS:
        return None
    if item_kind == 'metadata':
        return _metadata_content(document)
    page = _page(document, artifact['page_number'])
    if item_kind == 'page':
        try:
            return {'text': _normalised_text(page.get_text('text', sort=True))}
        except Exception as exc:
            raise Phase8ReportDocumentaryContextError(
                'REPORT_DOCUMENTARY_CONTEXT_REPORT_INVALID'
            ) from exc
    if item_kind == 'text':
        return _text_content(page, locator)
    if item_kind == 'table':
        return _table_content(page, locator)
    if item_kind == 'annotation':
        return _annotation_content(page, locator)
    _fail('REPORT_DOCUMENTARY_CONTEXT_PACKET_INVALID')


def _manifest(
    packet: ReportDefectEvidencePacket,
    items: tuple[TransientReportDocumentaryItem, ...],
) -> dict[str, Any]:
    source = packet.manifest
    return {
        'schema': PHASE8_REPORT_DOCUMENTARY_CONTEXT_SCHEMA,
        'report_packet_manifest_sha256': packet.manifest_sha256,
        'project_evidence_id': source['project_evidence_id'],
        'report_sha256': source['report_sha256'],
        'source_size_bytes': source['source_size_bytes'],
        'estimate_id': source['estimate_id'],
        'defect_id': source['defect_id'],
        'defect_reference': source['defect_reference'],
        'report_defect_label': source['report_defect_label'],
        'scope_id': source['scope_id'],
        'selected_item_count': len(items),
        'items': [
            {
                'evidence_id': item.evidence_id,
                'item_kind': item.item_kind,
                'page_number': item.page_number,
                'content_sha256': item.content_sha256,
                'content_available': item.content is not None,
            }
            for item in items
        ],
        'transient_content_only': True,
        'runtime_inference_performed': False,
        **{flag: False for flag in _NOOP_FLAGS},
    }


def build_phase8_report_documentary_context(
    *,
    report_packet: object,
    verified_content: object,
) -> Phase8ReportDocumentaryContext:
    '''Prepare only one selected report scope from exact, already-verified bytes.'''

    packet, artifacts = _packet_artifacts(report_packet)
    if not isinstance(verified_content, VerifiedStoredFileContent):
        _fail('REPORT_DOCUMENTARY_CONTEXT_SOURCE_INVALID')
    try:
        source = normalise_verified_pdf_report(verified_content)
    except ReportEvidenceAdapterError as exc:
        raise Phase8ReportDocumentaryContextError(
            'REPORT_DOCUMENTARY_CONTEXT_REPORT_INVALID'
        ) from exc
    _source_matches_packet(packet, artifacts, source)
    try:
        document = pymupdf.open(stream=verified_content.content, filetype='pdf')
    except Exception as exc:
        raise Phase8ReportDocumentaryContextError(
            'REPORT_DOCUMENTARY_CONTEXT_REPORT_INVALID'
        ) from exc
    try:
        items: list[TransientReportDocumentaryItem] = []
        character_count = 0
        for artifact in artifacts:
            content = _content(document, artifact)
            payload_hash, payload_characters = _payload_hash_and_characters(
                item_kind=artifact['item_kind'],
                locator=artifact['locator'],
                content=content,
            )
            if payload_hash is not None and payload_hash != artifact['content_sha256']:
                _fail('REPORT_DOCUMENTARY_CONTEXT_SOURCE_MISMATCH')
            character_count += payload_characters
            if character_count > _MAX_CONTEXT_CHARACTERS:
                _fail('REPORT_DOCUMENTARY_CONTEXT_CONTENT_OUT_OF_POLICY')
            items.append(
                TransientReportDocumentaryItem(
                    evidence_id=artifact['evidence_id'],
                    item_kind=artifact['item_kind'],
                    page_number=artifact['page_number'],
                    content_sha256=artifact['content_sha256'],
                    content=content,
                )
            )
    finally:
        document.close()
    selected = tuple(items)
    manifest = _manifest(packet, selected)
    context = Phase8ReportDocumentaryContext(
        packet=packet,
        manifest=manifest,
        manifest_sha256=canonical_json_sha256(manifest),
        items=selected,
    )
    if validate_phase8_report_documentary_context(context):
        _fail('REPORT_DOCUMENTARY_CONTEXT_INVALID')
    return context


def validate_phase8_report_documentary_context(value: object) -> list[str]:
    '''Validate a transient context without reopening or reading the source report.'''

    if not isinstance(value, Phase8ReportDocumentaryContext):
        return ['report documentary context has an unsupported type']
    errors: list[str] = []
    try:
        packet, artifacts = _packet_artifacts(value.packet)
    except Phase8ReportDocumentaryContextError:
        return ['report documentary context packet is invalid']
    if not isinstance(value.items, tuple) or len(value.items) != len(artifacts):
        return ['report documentary context item count is invalid']
    character_count = 0
    for ordinal, (artifact, item) in enumerate(zip(artifacts, value.items, strict=True), start=1):
        if not isinstance(item, TransientReportDocumentaryItem):
            errors.append(f'report documentary context item {ordinal} is invalid')
            continue
        if (
            item.evidence_id != artifact['evidence_id']
            or item.item_kind != artifact['item_kind']
            or item.page_number != artifact['page_number']
            or item.content_sha256 != artifact['content_sha256']
        ):
            errors.append(f'report documentary context item {ordinal} is not packet-bound')
            continue
        try:
            payload_hash, payload_characters = _payload_hash_and_characters(
                item_kind=item.item_kind,
                locator=artifact['locator'],
                content=item.content,
            )
        except Phase8ReportDocumentaryContextError:
            errors.append(f'report documentary context item {ordinal} content is invalid')
            continue
        if payload_hash is not None and payload_hash != item.content_sha256:
            errors.append(f'report documentary context item {ordinal} content hash is invalid')
        character_count += payload_characters
    if character_count > _MAX_CONTEXT_CHARACTERS:
        errors.append('report documentary context content exceeds policy')
    try:
        expected_manifest = _manifest(packet, value.items)
        expected_hash = canonical_json_sha256(expected_manifest)
    except (TypeError, ValueError):
        errors.append('report documentary context manifest is not canonical JSON')
    else:
        if value.manifest != expected_manifest:
            errors.append('report documentary context manifest is not source-bound')
        if value.manifest_sha256 != expected_hash:
            errors.append('report documentary context manifest hash does not match its contents')
    return list(dict.fromkeys(errors))


__all__ = [
    'PHASE8_REPORT_DOCUMENTARY_CONTEXT_SCHEMA',
    'Phase8ReportDocumentaryContext',
    'Phase8ReportDocumentaryContextError',
    'TransientReportDocumentaryItem',
    'build_phase8_report_documentary_context',
    'validate_phase8_report_documentary_context',
]
