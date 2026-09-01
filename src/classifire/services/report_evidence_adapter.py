'''Hash-bound PDF report locators and selected Defect ranges.

This module is deliberately a documentary-evidence boundary. It records safe
positions and content hashes from one exact retained PDF, but never creates
physical-model, technical, commercial, lock, or release records.
'''

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

import pymupdf
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import (
    ProjectEvidence,
    ReportDefectScope,
    ReportEvidenceLocator,
)
from ..physical_models import Defect
from .phase8_visual_proposal import (
    VISUAL_PROPOSAL_POLICY_VERSION,
    Phase8VisualProposalError,
    canonical_json_sha256,
    validate_policy_bound_visual_physical_proposal,
)
from .project_evidence import (
    read_project_evidence_for_update,
    require_project_evidence_access,
)
from .report_expected_label_manifest import (
    ApprovedReportExpectedLabelManifest,
    ReportExpectedLabelManifestError,
    require_approved_report_expected_label_manifest,
)
from .storage import VerifiedStoredFileContent

REPORT_EVIDENCE_LOCATOR_SCHEMA = 'CLASSIFIRE-REPORT-EVIDENCE-LOCATORS-v1'
REPORT_DEFECT_EVIDENCE_PACKET_SCHEMA = 'CLASSIFIRE-REPORT-DEFECT-EVIDENCE-PACKET-v1'
REPORT_DEFECT_EVIDENCE_PACKET_SCHEMA_V2 = 'CLASSIFIRE-REPORT-DEFECT-EVIDENCE-PACKET-v2'
_PDF_MEDIA_TYPE = 'application/pdf'
_HEX_SHA256 = frozenset('0123456789abcdef')
_ITEM_KIND_ORDER = {
    'metadata': 0,
    'page': 1,
    'text': 2,
    'table': 3,
    'caption': 4,
    'drawing': 5,
    'annotation': 6,
    'image': 7,
}
_MAX_REPORT_BYTES = 100 * 1024 * 1024
_MAX_REPORT_PAGES = 2_000
_MAX_REPORT_LOCATORS = 50_000
_MAX_TEXT_CHARACTERS = 1_000_000
_MAX_TABLE_ROWS = 2_000
_MAX_TABLE_COLUMNS = 200
_MAX_TABLE_CELLS = 100_000
_MAX_TABLE_CELL_CHARACTERS = 100_000
_MAX_REPORT_LABEL = 150


class ReportEvidenceAdapterError(ValueError):
    '''A stable, path-free report-evidence adapter failure.'''

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise ReportEvidenceAdapterError(code)


@dataclass(frozen=True, slots=True)
class ReportEvidenceLocatorItem:
    '''One stable content-free documentary position inside a retained report.'''

    locator_key: str
    item_kind: str
    page_number: int | None
    content_sha256: str
    locator: dict[str, Any]


@dataclass(frozen=True, slots=True)
class NormalisedReportEvidence:
    '''Deterministic locator inventory for one exact, retained PDF report.'''

    source_sha256: str
    source_size_bytes: int
    page_count: int
    locators: tuple[ReportEvidenceLocatorItem, ...]

    @property
    def manifest(self) -> dict[str, Any]:
        return {
            'schema': REPORT_EVIDENCE_LOCATOR_SCHEMA,
            'source_sha256': self.source_sha256,
            'source_size_bytes': self.source_size_bytes,
            'page_count': self.page_count,
            'locators': [
                {
                    'locator_key': item.locator_key,
                    'item_kind': item.item_kind,
                    'page_number': item.page_number,
                    'content_sha256': item.content_sha256,
                    'locator': item.locator,
                }
                for item in self.locators
            ],
        }

@dataclass(frozen=True, slots=True)
class ReportDefectScopeBinding:
    '''One proposed report range admitted only as part of an approved label set.'''

    defect_id: str
    report_defect_label: str
    start_locator_key: str
    end_locator_key: str


@dataclass(frozen=True, slots=True)
class ReportDefectEvidencePacket:
    '''Content-safe, selected-Defect documentary evidence for v2 validation.'''

    manifest: dict[str, Any]
    manifest_sha256: str

    @property
    def evidence_refs(self) -> frozenset[str]:
        artifacts = self.manifest.get('artifacts')
        if not isinstance(artifacts, list):
            return frozenset()
        refs: set[str] = set()
        for item in artifacts:
            if isinstance(item, dict):
                evidence_id = item.get('evidence_id')
                if isinstance(evidence_id, str):
                    refs.add(evidence_id)
        return frozenset(refs)


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
        _fail('REPORT_EVIDENCE_LOCATOR_SERIALISATION_INVALID')
        raise AssertionError from exc
    return hashlib.sha256(payload).hexdigest()


def _normalise_sha256(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.casefold()
        or any(character not in _HEX_SHA256 for character in value)
    ):
        _fail('REPORT_EVIDENCE_SOURCE_INVALID')
    return value


def _finite_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail('REPORT_EVIDENCE_LOCATOR_GEOMETRY_INVALID')
    number = float(value)
    if not math.isfinite(number):
        _fail('REPORT_EVIDENCE_LOCATOR_GEOMETRY_INVALID')
    return round(number, 3)


def _bbox(value: object) -> dict[str, float]:
    try:
        coordinates = {
            coordinate: getattr(value, coordinate)
            for coordinate in ('x0', 'y0', 'x1', 'y1')
        }
    except AttributeError:
        _fail('REPORT_EVIDENCE_LOCATOR_GEOMETRY_INVALID')
    return {
        coordinate: _finite_number(coordinates[coordinate])
        for coordinate in ('x0', 'y0', 'x1', 'y1')
    }


def _normalised_text(value: object) -> str:
    if not isinstance(value, str):
        return ''
    text = unicodedata.normalize('NFC', value).replace('\r\n', '\n').replace('\r', '\n')
    if len(text) > _MAX_TEXT_CHARACTERS:
        _fail('REPORT_EVIDENCE_TEXT_OUT_OF_POLICY')
    return text


def _text_sha256(value: object) -> str:
    return hashlib.sha256(_normalised_text(value).encode('utf-8')).hexdigest()


def _media_type(value: object) -> str:
    if not isinstance(value, str):
        _fail('REPORT_EVIDENCE_MEDIA_TYPE_FORBIDDEN')
    return value.split(';', 1)[0].strip().lower()


def _report_content(content: VerifiedStoredFileContent) -> tuple[str, int, bytes]:
    source_sha256 = _normalise_sha256(content.sha256)
    if _media_type(content.media_type) != _PDF_MEDIA_TYPE:
        _fail('REPORT_EVIDENCE_MEDIA_TYPE_FORBIDDEN')
    if content.size_bytes != len(content.content) or not content.content:
        _fail('REPORT_EVIDENCE_SOURCE_INVALID')
    if content.size_bytes > _MAX_REPORT_BYTES:
        _fail('REPORT_EVIDENCE_SIZE_OUT_OF_POLICY')
    if hashlib.sha256(content.content).hexdigest() != source_sha256:
        _fail('REPORT_EVIDENCE_SOURCE_HASH_MISMATCH')
    return source_sha256, content.size_bytes, content.content


def _table_shape(rows: object) -> tuple[int, int, str]:
    if not isinstance(rows, list) or len(rows) > _MAX_TABLE_ROWS:
        _fail('REPORT_EVIDENCE_TABLE_OUT_OF_POLICY')
    normalised: list[list[str]] = []
    maximum_columns = 0
    cell_count = 0
    for row in rows:
        if not isinstance(row, list) or len(row) > _MAX_TABLE_COLUMNS:
            _fail('REPORT_EVIDENCE_TABLE_OUT_OF_POLICY')
        cell_count += len(row)
        if cell_count > _MAX_TABLE_CELLS:
            _fail('REPORT_EVIDENCE_TABLE_OUT_OF_POLICY')
        values: list[str] = []
        for cell in row:
            text = _normalised_text('' if cell is None else str(cell))
            if len(text) > _MAX_TABLE_CELL_CHARACTERS:
                _fail('REPORT_EVIDENCE_TABLE_OUT_OF_POLICY')
            values.append(text)
        normalised.append(values)
        maximum_columns = max(maximum_columns, len(values))
    return len(normalised), maximum_columns, _canonical_sha256(normalised)


def _draft_item(
    *,
    item_kind: str,
    page_number: int | None,
    content_sha256: str,
    locator: dict[str, Any],
    sort_index: int,
) -> dict[str, Any]:
    if item_kind not in _ITEM_KIND_ORDER:
        _fail('REPORT_EVIDENCE_ITEM_KIND_INVALID')
    if len(content_sha256) != 64 or any(
        character not in _HEX_SHA256 for character in content_sha256
    ):
        _fail('REPORT_EVIDENCE_CONTENT_HASH_INVALID')
    bounds = locator.get('bounds')
    if isinstance(bounds, dict):
        position = tuple(bounds.get(key, 0.0) for key in ('y0', 'x0', 'y1', 'x1'))
    else:
        position = (0.0, 0.0, 0.0, 0.0)
    return {
        'item_kind': item_kind,
        'page_number': page_number,
        'content_sha256': content_sha256,
        'locator': locator,
        'sort_key': (
            page_number or 0,
            _ITEM_KIND_ORDER[item_kind],
            *position,
            content_sha256,
            sort_index,
        ),
    }


def _page_drafts(
    page: pymupdf.Page,
    page_number: int,
) -> list[dict[str, Any]]:
    page_bounds = _bbox(page.rect)
    text = _normalised_text(page.get_text('text', sort=True))
    drafts = [
        _draft_item(
            item_kind='page',
            page_number=page_number,
            content_sha256=_text_sha256(text),
            locator={
                'item_kind': 'page',
                'page_number': page_number,
                'bounds': page_bounds,
                'rotation': int(page.rotation),
                'character_count': len(text),
            },
            sort_index=0,
        )
    ]
    for block_index, block in enumerate(page.get_text('blocks', sort=True), start=1):
        if not isinstance(block, tuple) or len(block) < 7 or int(block[6]) != 0:
            continue
        block_text = _normalised_text(block[4])
        if not block_text.strip():
            continue
        bounds = {
            'x0': _finite_number(block[0]),
            'y0': _finite_number(block[1]),
            'x1': _finite_number(block[2]),
            'y1': _finite_number(block[3]),
        }
        drafts.append(
            _draft_item(
                item_kind='text',
                page_number=page_number,
                content_sha256=_text_sha256(block_text),
                locator={
                    'item_kind': 'text',
                    'page_number': page_number,
                    'bounds': bounds,
                    'character_count': len(block_text),
                    'text_role': 'unclassified',
                    'block_index': block_index,
                },
                sort_index=block_index,
            )
        )
    try:
        tables = list(page.find_tables().tables)
    except Exception as exc:
        _fail('REPORT_EVIDENCE_TABLE_EXTRACTION_FAILED')
        raise AssertionError from exc
    for table_index, table in enumerate(tables, start=1):
        row_count, column_count, content_sha256 = _table_shape(table.extract())
        drafts.append(
            _draft_item(
                item_kind='table',
                page_number=page_number,
                content_sha256=content_sha256,
                locator={
                    'item_kind': 'table',
                    'page_number': page_number,
                    'bounds': _bbox(pymupdf.Rect(table.bbox)),
                    'row_count': row_count,
                    'column_count': column_count,
                    'table_index': table_index,
                },
                sort_index=table_index,
            )
        )
    try:
        drawings = page.get_drawings()
    except Exception as exc:
        _fail('REPORT_EVIDENCE_DRAWING_EXTRACTION_FAILED')
        raise AssertionError from exc
    for drawing_index, drawing in enumerate(drawings, start=1):
        bounds = _bbox(drawing.get('rect'))
        drawing_shape = {
            'type': str(drawing.get('type') or ''),
            'item_count': len(drawing.get('items') or []),
            'width': _finite_number(drawing.get('width') or 0),
            'bounds': bounds,
        }
        drafts.append(
            _draft_item(
                item_kind='drawing',
                page_number=page_number,
                content_sha256=_canonical_sha256(drawing_shape),
                locator={
                    'item_kind': 'drawing',
                    'page_number': page_number,
                    'bounds': bounds,
                    'drawing_type': drawing_shape['type'],
                    'path_item_count': drawing_shape['item_count'],
                    'drawing_index': drawing_index,
                },
                sort_index=drawing_index,
            )
        )
    try:
        annotations = tuple(page.annots() or ())
    except Exception as exc:
        _fail('REPORT_EVIDENCE_ANNOTATION_EXTRACTION_FAILED')
        raise AssertionError from exc
    for annotation_index, annotation in enumerate(annotations, start=1):
        annotation_type = annotation.type
        annotation_name = (
            str(annotation_type[1])
            if isinstance(annotation_type, tuple) and len(annotation_type) > 1
            else 'unknown'
        )
        annotation_shape = {
            'type': annotation_name,
            'bounds': _bbox(annotation.rect),
            'info_sha256': _canonical_sha256(
                {str(key): _text_sha256(value) for key, value in (annotation.info or {}).items()}
            ),
        }
        drafts.append(
            _draft_item(
                item_kind='annotation',
                page_number=page_number,
                content_sha256=_canonical_sha256(annotation_shape),
                locator={
                    'item_kind': 'annotation',
                    'page_number': page_number,
                    'bounds': annotation_shape['bounds'],
                    'annotation_type': annotation_name,
                    'annotation_index': annotation_index,
                },
                sort_index=annotation_index,
            )
        )
    try:
        images = page.get_images(full=True)
    except Exception as exc:
        _fail('REPORT_EVIDENCE_IMAGE_EXTRACTION_FAILED')
        raise AssertionError from exc
    for image_index, image in enumerate(images, start=1):
        if not isinstance(image, tuple) or len(image) < 6:
            _fail('REPORT_EVIDENCE_IMAGE_EXTRACTION_FAILED')
        xref = int(image[0])
        try:
            image_bounds = [_bbox(rectangle) for rectangle in page.get_image_rects(xref)]
        except Exception as exc:
            _fail('REPORT_EVIDENCE_IMAGE_EXTRACTION_FAILED')
            raise AssertionError from exc
        image_shape = {
            'xref': xref,
            'width': int(image[2]),
            'height': int(image[3]),
            'bits_per_component': int(image[4]),
            'colour_space': str(image[5]),
            'bounds': image_bounds,
        }
        drafts.append(
            _draft_item(
                item_kind='image',
                page_number=page_number,
                content_sha256=_canonical_sha256(image_shape),
                locator={
                    'item_kind': 'image',
                    'page_number': page_number,
                    **image_shape,
                    'image_index': image_index,
                },
                sort_index=image_index,
            )
        )
    return drafts


def normalise_verified_pdf_report(content: VerifiedStoredFileContent) -> NormalisedReportEvidence:
    '''Normalise one exact PDF into bounded, content-free stable locators.'''

    source_sha256, source_size_bytes, report_bytes = _report_content(content)
    try:
        document = pymupdf.open(stream=report_bytes, filetype='pdf')
    except Exception as exc:
        _fail('REPORT_EVIDENCE_PDF_INVALID')
        raise AssertionError from exc
    try:
        page_count = int(document.page_count)
        if page_count < 1 or page_count > _MAX_REPORT_PAGES:
            _fail('REPORT_EVIDENCE_PAGE_COUNT_OUT_OF_POLICY')
        metadata_values = document.metadata or {}
        metadata_hashes = {
            str(key): _text_sha256(value)
            for key, value in metadata_values.items()
            if value is not None
        }
        drafts = [
            _draft_item(
                item_kind='metadata',
                page_number=None,
                content_sha256=_canonical_sha256(metadata_hashes),
                locator={
                    'item_kind': 'metadata',
                    'metadata_field_count': len(metadata_hashes),
                },
                sort_index=0,
            )
        ]
        for page_number in range(1, page_count + 1):
            try:
                page = document.load_page(page_number - 1)
                drafts.extend(_page_drafts(page, page_number))
            except ReportEvidenceAdapterError:
                raise
            except Exception as exc:
                _fail('REPORT_EVIDENCE_PDF_EXTRACTION_FAILED')
                raise AssertionError from exc
            if len(drafts) > _MAX_REPORT_LOCATORS:
                _fail('REPORT_EVIDENCE_LOCATOR_COUNT_OUT_OF_POLICY')
    finally:
        document.close()
    drafts.sort(key=lambda item: item['sort_key'])
    kind_ordinals: dict[tuple[int | None, str], int] = {}
    locators: list[ReportEvidenceLocatorItem] = []
    for sequence, draft in enumerate(drafts, start=1):
        page_number = draft['page_number']
        item_kind = draft['item_kind']
        ordinal_key = (page_number, item_kind)
        ordinal = kind_ordinals.get(ordinal_key, 0) + 1
        kind_ordinals[ordinal_key] = ordinal
        page_token = page_number if page_number is not None else 0
        content_sha256 = draft['content_sha256']
        locator_key = (
            f'report-{source_sha256[:16]}-p{page_token:04d}-'
            f'{item_kind}-{ordinal:04d}-{content_sha256[:16]}'
        )
        locator = dict(draft['locator'])
        locator['sequence'] = sequence
        locators.append(
            ReportEvidenceLocatorItem(
                locator_key=locator_key,
                item_kind=item_kind,
                page_number=page_number,
                content_sha256=content_sha256,
                locator=locator,
            )
        )
    return NormalisedReportEvidence(
        source_sha256=source_sha256,
        source_size_bytes=source_size_bytes,
        page_count=page_count,
        locators=tuple(locators),
    )


def _report_owner(
    db: Session,
    *,
    stored_file_id: str,
    project_id: str,
    estimate_id: str | None,
) -> ProjectEvidence:
    try:
        return require_project_evidence_access(
            db,
            stored_file_id=stored_file_id,
            project_id=project_id,
            estimate_id=estimate_id,
        )
    except ValueError as exc:
        _fail(str(exc))
    raise AssertionError


def _positive_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _valid_bounds(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {'x0', 'y0', 'x1', 'y1'}:
        return False
    try:
        return all(math.isfinite(float(value[key])) for key in value)
    except (TypeError, ValueError):
        return False


def _valid_locator(item: ReportEvidenceLocatorItem, *, sequence: int) -> bool:
    if (
        item.item_kind not in _ITEM_KIND_ORDER
        or item.item_kind == 'caption'
        or not isinstance(item.locator_key, str)
        or not item.locator_key.strip()
        or len(item.locator_key) > 300
        or not isinstance(item.locator, dict)
        or item.locator.get('item_kind') != item.item_kind
        or item.locator.get('sequence') != sequence
        or item.locator.get('page_number') != item.page_number
        or len(item.content_sha256) != 64
        or item.content_sha256 != item.content_sha256.casefold()
        or any(character not in _HEX_SHA256 for character in item.content_sha256)
    ):
        return False
    if item.item_kind == 'metadata':
        return item.page_number is None and set(item.locator) == {
            'item_kind',
            'metadata_field_count',
            'sequence',
        } and isinstance(item.locator.get('metadata_field_count'), int)
    if not _positive_integer(item.page_number):
        return False
    allowed_keys = {
        'page': {'item_kind', 'page_number', 'bounds', 'rotation', 'character_count', 'sequence'},
        'text': {
            'item_kind',
            'page_number',
            'bounds',
            'character_count',
            'text_role',
            'block_index',
            'sequence',
        },
        'table': {
            'item_kind',
            'page_number',
            'bounds',
            'row_count',
            'column_count',
            'table_index',
            'sequence',
        },
        'drawing': {
            'item_kind',
            'page_number',
            'bounds',
            'drawing_type',
            'path_item_count',
            'drawing_index',
            'sequence',
        },
        'annotation': {
            'item_kind',
            'page_number',
            'bounds',
            'annotation_type',
            'annotation_index',
            'sequence',
        },
        'image': {
            'item_kind',
            'page_number',
            'xref',
            'width',
            'height',
            'bits_per_component',
            'colour_space',
            'bounds',
            'image_index',
            'sequence',
        },
    }
    if set(item.locator) != allowed_keys[item.item_kind]:
        return False
    if item.item_kind == 'image':
        bounds = item.locator.get('bounds')
        return (
            isinstance(bounds, list)
            and all(_valid_bounds(value) for value in bounds)
            and all(
                _positive_integer(item.locator.get(field))
                for field in ('xref', 'width', 'height', 'bits_per_component', 'image_index')
            )
            and isinstance(item.locator.get('colour_space'), str)
        )
    if not _valid_bounds(item.locator.get('bounds')):
        return False
    if item.item_kind == 'text':
        return (
            item.locator.get('text_role') == 'unclassified'
            and _positive_integer(item.locator.get('block_index'))
            and isinstance(item.locator.get('character_count'), int)
        )
    return all(
        isinstance(item.locator.get(field), int)
        for field in {
            'page': ('rotation', 'character_count'),
            'table': ('row_count', 'column_count', 'table_index'),
            'drawing': ('path_item_count', 'drawing_index'),
            'annotation': ('annotation_index',),
        }[item.item_kind]
    )


def _validate_report(report: NormalisedReportEvidence) -> None:
    _normalise_sha256(report.source_sha256)
    if not _positive_integer(report.source_size_bytes) or not _positive_integer(report.page_count):
        _fail('REPORT_EVIDENCE_SOURCE_INVALID')
    if not report.locators or len(report.locators) > _MAX_REPORT_LOCATORS:
        _fail('REPORT_EVIDENCE_LOCATORS_REQUIRED')
    locator_keys = [item.locator_key for item in report.locators]
    if len(set(locator_keys)) != len(locator_keys) or any(
        not _valid_locator(item, sequence=sequence)
        for sequence, item in enumerate(report.locators, start=1)
    ):
        _fail('REPORT_EVIDENCE_LOCATOR_INVALID')


def _require_report_binding(
    evidence: ProjectEvidence,
    report: NormalisedReportEvidence,
) -> None:
    _validate_report(report)
    if (
        evidence.source_sha256 != report.source_sha256
        or evidence.source_size_bytes != report.source_size_bytes
    ):
        _fail('REPORT_EVIDENCE_SOURCE_BINDING_DRIFT')
    if not report.locators:
        _fail('REPORT_EVIDENCE_LOCATORS_REQUIRED')


def _same_locator(
    record: ReportEvidenceLocator,
    item: ReportEvidenceLocatorItem,
    *,
    sequence: int,
    source_sha256: str,
) -> bool:
    return (
        record.source_sha256 == source_sha256
        and record.sequence == sequence
        and record.locator_key == item.locator_key
        and record.item_kind == item.item_kind
        and record.page_number == item.page_number
        and record.content_sha256 == item.content_sha256
        and record.locator_json == item.locator
    )


def _register_report_evidence_locators(
    db: Session,
    *,
    stored_file_id: str,
    project_id: str,
    report: NormalisedReportEvidence,
    estimate_id: str | None = None,
) -> tuple[ReportEvidenceLocator, ...]:
    '''Persist one exact normalised report after its clean-byte read is locked.'''

    evidence = _report_owner(
        db,
        stored_file_id=stored_file_id,
        project_id=project_id,
        estimate_id=estimate_id,
    )
    _require_report_binding(evidence, report)
    existing = tuple(
        db.scalars(
            select(ReportEvidenceLocator)
            .where(ReportEvidenceLocator.project_evidence_id == evidence.id)
            .order_by(ReportEvidenceLocator.sequence)
        ).all()
    )
    if existing:
        if len(existing) == len(report.locators) and all(
            _same_locator(
                record,
                item,
                sequence=sequence,
                source_sha256=report.source_sha256,
            )
            for sequence, (record, item) in enumerate(
                zip(existing, report.locators, strict=True),
                start=1,
            )
        ):
            return existing
        _fail('REPORT_EVIDENCE_LOCATOR_CONFLICT')
    records = tuple(
        ReportEvidenceLocator(
            project_evidence_id=evidence.id,
            source_sha256=report.source_sha256,
            sequence=sequence,
            locator_key=item.locator_key,
            item_kind=item.item_kind,
            page_number=item.page_number,
            content_sha256=item.content_sha256,
            locator_json=item.locator,
        )
        for sequence, item in enumerate(report.locators, start=1)
    )
    try:
        with db.begin_nested():
            db.add_all(records)
            db.flush()
    except IntegrityError:
        _fail('REPORT_EVIDENCE_LOCATOR_CONFLICT')
    return records


def materialise_project_report_locators_for_update(
    db: Session,
    *,
    stored_file_id: str,
    project_id: str,
    storage_root: Path,
    estimate_id: str | None = None,
) -> tuple[ReportEvidenceLocator, ...]:
    '''Read clean exact report bytes, then persist their stable locators.'''

    try:
        content = read_project_evidence_for_update(
            db,
            stored_file_id=stored_file_id,
            project_id=project_id,
            estimate_id=estimate_id,
            storage_root=storage_root,
        )
    except ValueError as exc:
        _fail(str(exc))
    report = normalise_verified_pdf_report(content)
    return _register_report_evidence_locators(
        db,
        stored_file_id=stored_file_id,
        project_id=project_id,
        estimate_id=estimate_id,
        report=report,
    )


def _required_text(value: object, *, code: str, maximum: int) -> str:
    if not isinstance(value, str):
        _fail(code)
    text = value.strip()
    if not text or len(text) > maximum:
        _fail(code)
    return text


def _defect_reference(defect: Defect) -> str:
    for value in (defect.external_defect_id, defect.defect_code):
        if isinstance(value, str) and value.strip() and len(value.strip()) <= 150:
            return value.strip()
    _fail('REPORT_EVIDENCE_DEFECT_REFERENCE_INVALID')


def _scope_locator_records(
    db: Session,
    *,
    evidence: ProjectEvidence,
    scope: ReportDefectScope,
) -> tuple[ReportEvidenceLocator, ...]:
    start = db.get(ReportEvidenceLocator, scope.start_locator_id)
    end = db.get(ReportEvidenceLocator, scope.end_locator_id)
    if (
        start is None
        or end is None
        or start.project_evidence_id != evidence.id
        or end.project_evidence_id != evidence.id
        or start.source_sha256 != evidence.source_sha256
        or end.source_sha256 != evidence.source_sha256
        or start.sequence > end.sequence
    ):
        _fail('REPORT_EVIDENCE_SCOPE_BINDING_INVALID')
    records = tuple(
        db.scalars(
            select(ReportEvidenceLocator)
            .where(
                ReportEvidenceLocator.project_evidence_id == evidence.id,
                ReportEvidenceLocator.sequence >= start.sequence,
                ReportEvidenceLocator.sequence <= end.sequence,
            )
            .order_by(ReportEvidenceLocator.sequence)
        ).all()
    )
    if (
        not records
        or records[0].id != start.id
        or records[-1].id != end.id
        or len(records) != end.sequence - start.sequence + 1
    ):
        _fail('REPORT_EVIDENCE_SCOPE_BINDING_INVALID')
    return records


def _packet_artifact(
    record: ReportEvidenceLocator,
    *,
    source_sha256: str,
    previous_sequence: int | None,
) -> dict[str, Any]:
    if (
        record.source_sha256 != source_sha256
        or not isinstance(record.locator_json, dict)
        or previous_sequence is not None
        and record.sequence != previous_sequence + 1
    ):
        _fail('REPORT_EVIDENCE_LOCATOR_INVALID')
    item = ReportEvidenceLocatorItem(
        locator_key=record.locator_key,
        item_kind=record.item_kind,
        page_number=record.page_number,
        content_sha256=record.content_sha256,
        locator=deepcopy(record.locator_json),
    )
    if not _valid_locator(item, sequence=record.sequence):
        _fail('REPORT_EVIDENCE_LOCATOR_INVALID')
    return {
        'evidence_id': f'report-locator:{item.locator_key}',
        'sequence': record.sequence,
        'locator_key': item.locator_key,
        'item_kind': item.item_kind,
        'page_number': item.page_number,
        'content_sha256': item.content_sha256,
        'locator': item.locator,
    }


def validate_report_defect_evidence_packet(packet: object) -> list[str]:
    '''Validate a selected-Defect report manifest before v2 proposal validation.'''

    if not isinstance(packet, ReportDefectEvidencePacket):
        return ['report defect evidence packet has an unsupported type']
    manifest = packet.manifest
    if not isinstance(manifest, dict):
        return ['report defect evidence manifest must be an object']
    legacy_expected = {
        'schema',
        'project_evidence_id',
        'report_sha256',
        'source_size_bytes',
        'estimate_id',
        'defect_id',
        'defect_reference',
        'report_defect_label',
        'scope_id',
        'start_locator_key',
        'end_locator_key',
        'artifacts',
    }
    schema = manifest.get('schema')
    if schema == REPORT_DEFECT_EVIDENCE_PACKET_SCHEMA:
        expected = legacy_expected
    elif schema == REPORT_DEFECT_EVIDENCE_PACKET_SCHEMA_V2:
        expected = legacy_expected | {
            'approved_expected_label_manifest_id',
            'approved_expected_label_manifest_sha256',
            'approved_expected_label_manifest_approval_reference',
        }
    else:
        expected = set()
    errors: list[str] = []
    if set(manifest) != expected:
        errors.append('report defect evidence manifest fields are unsupported')
    if schema not in {
        REPORT_DEFECT_EVIDENCE_PACKET_SCHEMA,
        REPORT_DEFECT_EVIDENCE_PACKET_SCHEMA_V2,
    }:
        errors.append('report defect evidence manifest schema is unsupported')
    for field, maximum in (
        ('project_evidence_id', 36),
        ('estimate_id', 36),
        ('defect_id', 36),
        ('defect_reference', 150),
        ('report_defect_label', _MAX_REPORT_LABEL),
        ('scope_id', 36),
        ('start_locator_key', 300),
        ('end_locator_key', 300),
    ):
        value = manifest.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            errors.append(f'report defect evidence manifest {field} is invalid')
    try:
        _normalise_sha256(manifest.get('report_sha256'))
    except ReportEvidenceAdapterError:
        errors.append('report defect evidence manifest report_sha256 is invalid')
    if not _positive_integer(manifest.get('source_size_bytes')):
        errors.append('report defect evidence manifest source_size_bytes is invalid')
    if schema == REPORT_DEFECT_EVIDENCE_PACKET_SCHEMA_V2:
        for field, maximum in (
            ('approved_expected_label_manifest_id', 36),
            ('approved_expected_label_manifest_approval_reference', 500),
        ):
            value = manifest.get(field)
            if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                errors.append(f'report defect evidence manifest {field} is invalid')
        approval_hash = manifest.get('approved_expected_label_manifest_sha256')
        if (
            not isinstance(approval_hash, str)
            or len(approval_hash) != 64
            or approval_hash != approval_hash.upper()
            or any(character not in _HEX_SHA256 for character in approval_hash.casefold())
        ):
            errors.append('report defect evidence manifest approval hash is invalid')
    artifacts = manifest.get('artifacts')
    if not isinstance(artifacts, list) or not artifacts or len(artifacts) > _MAX_REPORT_LOCATORS:
        return [*errors, 'report defect evidence manifest artifacts are invalid']
    previous_sequence: int | None = None
    artifact_ids: set[str] = set()
    for index, artifact in enumerate(artifacts, start=1):
        if not isinstance(artifact, dict):
            errors.append(f'report defect evidence artifact {index} is invalid')
            continue
        expected_artifact = {
            'evidence_id',
            'sequence',
            'locator_key',
            'item_kind',
            'page_number',
            'content_sha256',
            'locator',
        }
        if set(artifact) != expected_artifact:
            errors.append(f'report defect evidence artifact {index} fields are unsupported')
            continue
        evidence_id = artifact.get('evidence_id')
        locator_key = artifact.get('locator_key')
        item_kind = artifact.get('item_kind')
        page_number = artifact.get('page_number')
        content_sha256 = artifact.get('content_sha256')
        locator = artifact.get('locator')
        sequence = artifact.get('sequence')
        if (
            not isinstance(evidence_id, str)
            or not isinstance(locator_key, str)
            or not isinstance(item_kind, str)
            or page_number is not None
            and not isinstance(page_number, int)
            or not isinstance(content_sha256, str)
            or not isinstance(locator, dict)
            or evidence_id != f'report-locator:{locator_key}'
            or evidence_id in artifact_ids
            or not isinstance(sequence, int)
            or not _positive_integer(sequence)
            or previous_sequence is not None
            and sequence != previous_sequence + 1
        ):
            errors.append(f'report defect evidence artifact {index} identity is invalid')
            continue
        item = ReportEvidenceLocatorItem(
            locator_key=locator_key,
            item_kind=item_kind,
            page_number=page_number,
            content_sha256=content_sha256,
            locator=locator,
        )
        if not _valid_locator(item, sequence=sequence):
            errors.append(f'report defect evidence artifact {index} locator is invalid')
            continue
        artifact_ids.add(evidence_id)
        previous_sequence = sequence
    if artifacts and isinstance(artifacts[0], dict) and isinstance(artifacts[-1], dict):
        if artifacts[0].get('locator_key') != manifest.get('start_locator_key'):
            errors.append('report defect evidence start locator does not match artifacts')
        if artifacts[-1].get('locator_key') != manifest.get('end_locator_key'):
            errors.append('report defect evidence end locator does not match artifacts')
    try:
        manifest_sha256 = canonical_json_sha256(manifest)
    except Phase8VisualProposalError:
        errors.append('report defect evidence manifest must contain JSON values only')
    else:
        if (
            not isinstance(packet.manifest_sha256, str)
            or len(packet.manifest_sha256) != 64
            or packet.manifest_sha256 != manifest_sha256
        ):
            errors.append('report defect evidence manifest hash does not match its contents')
    return list(dict.fromkeys(errors))


def _scope_admission_packet_binding(
    db: Session,
    *,
    project_id: str,
    stored_file_id: str,
    evidence: ProjectEvidence,
    estimate_id: str,
    scope: ReportDefectScope,
) -> dict[str, str]:
    manifest_id = scope.approved_expected_label_manifest_id
    if manifest_id is None:
        return {}
    try:
        approved = require_approved_report_expected_label_manifest(
            db,
            expected_label_manifest_id=manifest_id,
            project_id=project_id,
            estimate_id=estimate_id,
            stored_file_id=stored_file_id,
            report_sha256=evidence.source_sha256,
        )
    except ReportExpectedLabelManifestError as exc:
        raise ReportEvidenceAdapterError('REPORT_EVIDENCE_SCOPE_BINDING_INVALID') from exc
    if scope.report_defect_label not in approved.expected_report_defect_labels:
        _fail('REPORT_EVIDENCE_SCOPE_BINDING_INVALID')
    return {
        'approved_expected_label_manifest_id': approved.id,
        'approved_expected_label_manifest_sha256': approved.manifest_sha256,
        'approved_expected_label_manifest_approval_reference': approved.approval_reference,
    }


def _build_report_defect_evidence_packet(
    db: Session,
    *,
    evidence: ProjectEvidence,
    project_id: str,
    stored_file_id: str,
    estimate_id: str,
    defect: Defect,
    scope: ReportDefectScope,
) -> ReportDefectEvidencePacket:
    if scope.source_sha256 != evidence.source_sha256:
        _fail('REPORT_EVIDENCE_SCOPE_BINDING_INVALID')
    records = _scope_locator_records(db, evidence=evidence, scope=scope)
    admission_binding = _scope_admission_packet_binding(
        db,
        project_id=project_id,
        stored_file_id=stored_file_id,
        evidence=evidence,
        estimate_id=estimate_id,
        scope=scope,
    )

    artifacts: list[dict[str, Any]] = []
    previous_sequence: int | None = None
    for record in records:
        artifacts.append(
            _packet_artifact(
                record,
                source_sha256=evidence.source_sha256,
                previous_sequence=previous_sequence,
            )
        )
        previous_sequence = record.sequence
    manifest = {
        'schema': (
            REPORT_DEFECT_EVIDENCE_PACKET_SCHEMA_V2
            if admission_binding
            else REPORT_DEFECT_EVIDENCE_PACKET_SCHEMA
        ),
        'project_evidence_id': evidence.id,
        'report_sha256': evidence.source_sha256,
        'source_size_bytes': evidence.source_size_bytes,
        'estimate_id': estimate_id,
        'defect_id': defect.id,
        'defect_reference': _defect_reference(defect),
        'report_defect_label': scope.report_defect_label,
        'scope_id': scope.id,
        'start_locator_key': records[0].locator_key,
        'end_locator_key': records[-1].locator_key,
        'artifacts': artifacts,
    }
    manifest.update(admission_binding)
    packet = ReportDefectEvidencePacket(
        manifest=manifest,
        manifest_sha256=canonical_json_sha256(manifest),
    )
    errors = validate_report_defect_evidence_packet(packet)
    if errors:
        _fail('REPORT_EVIDENCE_PACKET_INVALID')
    return packet


def build_report_defect_evidence_packet(
    db: Session,
    *,
    stored_file_id: str,
    project_id: str,
    estimate_id: str,
    defect_id: str,
) -> ReportDefectEvidencePacket:
    '''Expose one report-selected Defect range as v2-approved documentary refs.'''

    estimate_id = _required_text(estimate_id, code='REPORT_EVIDENCE_ESTIMATE_INVALID', maximum=36)
    defect_id = _required_text(defect_id, code='REPORT_EVIDENCE_DEFECT_INVALID', maximum=36)
    evidence = _report_owner(
        db,
        stored_file_id=stored_file_id,
        project_id=project_id,
        estimate_id=estimate_id,
    )
    defect = db.get(Defect, defect_id)
    if defect is None:
        _fail('REPORT_EVIDENCE_DEFECT_NOT_FOUND')
    if defect.estimate_id != estimate_id:
        _fail('REPORT_EVIDENCE_DEFECT_SCOPE_FORBIDDEN')
    scope = db.scalar(
        select(ReportDefectScope).where(
            ReportDefectScope.project_evidence_id == evidence.id,
            ReportDefectScope.defect_id == defect.id,
        )
    )
    if scope is None:
        _fail('REPORT_EVIDENCE_DEFECT_SCOPE_REQUIRED')
    return _build_report_defect_evidence_packet(
        db,
        evidence=evidence,
        project_id=project_id,
        stored_file_id=stored_file_id,
        estimate_id=estimate_id,
        defect=defect,
        scope=scope,
    )


def build_report_defect_evidence_packets(
    db: Session,
    *,
    stored_file_id: str,
    project_id: str,
    estimate_id: str,
) -> tuple[ReportDefectEvidencePacket, ...]:
    '''Expose every selected Defect range for one owned report and estimate.'''

    estimate_id = _required_text(estimate_id, code='REPORT_EVIDENCE_ESTIMATE_INVALID', maximum=36)
    evidence = _report_owner(
        db,
        stored_file_id=stored_file_id,
        project_id=project_id,
        estimate_id=estimate_id,
    )
    scopes = tuple(
        db.scalars(
            select(ReportDefectScope)
            .where(ReportDefectScope.project_evidence_id == evidence.id)
            .order_by(ReportDefectScope.report_defect_label, ReportDefectScope.id)
        ).all()
    )
    if not scopes:
        _fail('REPORT_EVIDENCE_DEFECT_SCOPE_REQUIRED')
    selections: list[tuple[ReportDefectScope, Defect]] = []
    for scope in scopes:
        if scope.source_sha256 != evidence.source_sha256:
            _fail('REPORT_EVIDENCE_SCOPE_BINDING_INVALID')
        defect = db.get(Defect, scope.defect_id)
        if defect is None:
            _fail('REPORT_EVIDENCE_SCOPE_BINDING_INVALID')
        if defect.estimate_id != estimate_id:
            _fail('REPORT_EVIDENCE_DEFECT_SCOPE_FORBIDDEN')
        selections.append((scope, defect))
    return tuple(
        _build_report_defect_evidence_packet(
            db,
            evidence=evidence,
            project_id=project_id,
            stored_file_id=stored_file_id,
            estimate_id=estimate_id,
            defect=defect,
            scope=scope,
        )
        for scope, defect in sorted(
            selections,
            key=lambda selection: (
                selection[0].report_defect_label.casefold(),
                _defect_reference(selection[1]),
                selection[0].id,
            ),
        )
    )


def validate_report_defect_v2_proposal(
    packet: object,
    proposal: object,
) -> list[str]:
    '''Apply the existing v2 proposal policy to exactly one report-selected range.'''

    if not isinstance(packet, ReportDefectEvidencePacket):
        return ['report defect evidence packet has an unsupported type']
    errors = validate_report_defect_evidence_packet(packet)
    if errors:
        return errors
    return validate_policy_bound_visual_physical_proposal(
        proposal,
        defect_reference=str(packet.manifest['defect_reference']),
        policy_version=VISUAL_PROPOSAL_POLICY_VERSION,
        allowed_evidence_refs=packet.evidence_refs,
    )


def _bind_report_defect_scope(
    db: Session,
    *,
    stored_file_id: str,
    project_id: str,
    estimate_id: str,
    defect_id: str,
    report_defect_label: str,
    start_locator_key: str,
    end_locator_key: str,
    approved_expected_label_manifest_id: str,
) -> ReportDefectScope:
    '''Bind one ordered locator range to an existing Defect without model writes.'''

    estimate_id = _required_text(estimate_id, code='REPORT_EVIDENCE_ESTIMATE_INVALID', maximum=36)
    defect_id = _required_text(defect_id, code='REPORT_EVIDENCE_DEFECT_INVALID', maximum=36)
    report_defect_label = _required_text(
        report_defect_label,
        code='REPORT_EVIDENCE_DEFECT_LABEL_INVALID',
        maximum=_MAX_REPORT_LABEL,
    )
    start_locator_key = _required_text(
        start_locator_key,
        code='REPORT_EVIDENCE_RANGE_INVALID',
        maximum=300,
    )
    end_locator_key = _required_text(
        end_locator_key,
        code='REPORT_EVIDENCE_RANGE_INVALID',
        maximum=300,
    )
    approved_expected_label_manifest_id = _required_text(
        approved_expected_label_manifest_id,
        code='REPORT_EVIDENCE_EXPECTED_LABEL_MANIFEST_INVALID',
        maximum=36,
    )
    evidence = _report_owner(
        db,
        stored_file_id=stored_file_id,
        project_id=project_id,
        estimate_id=estimate_id,
    )
    defect = db.get(Defect, defect_id)
    if defect is None:
        _fail('REPORT_EVIDENCE_DEFECT_NOT_FOUND')
    if defect.estimate_id != estimate_id:
        _fail('REPORT_EVIDENCE_DEFECT_SCOPE_FORBIDDEN')
    locators = {
        record.locator_key: record
        for record in db.scalars(
            select(ReportEvidenceLocator).where(
                ReportEvidenceLocator.project_evidence_id == evidence.id,
                ReportEvidenceLocator.locator_key.in_((start_locator_key, end_locator_key)),
            )
        ).all()
    }
    start = locators.get(start_locator_key)
    end = locators.get(end_locator_key)
    if (
        start is None
        or end is None
        or start.page_number is None
        or end.page_number is None
        or start.sequence > end.sequence
    ):
        _fail('REPORT_EVIDENCE_RANGE_INVALID')
    existing = db.scalar(
        select(ReportDefectScope).where(
            ReportDefectScope.project_evidence_id == evidence.id,
            ReportDefectScope.defect_id == defect.id,
        )
    )
    if existing is not None:
        if (
            existing.source_sha256 == evidence.source_sha256
            and existing.report_defect_label == report_defect_label
            and existing.start_locator_id == start.id
            and existing.end_locator_id == end.id
            and existing.approved_expected_label_manifest_id == approved_expected_label_manifest_id
        ):
            return existing
        _fail('REPORT_EVIDENCE_DEFECT_SCOPE_CONFLICT')
    scope = ReportDefectScope(
        project_evidence_id=evidence.id,
        source_sha256=evidence.source_sha256,
        defect_id=defect.id,
        report_defect_label=report_defect_label,
        approved_expected_label_manifest_id=approved_expected_label_manifest_id,
        start_locator_id=start.id,
        end_locator_id=end.id,
    )
    try:
        with db.begin_nested():
            db.add(scope)
            db.flush()
    except IntegrityError:
        _fail('REPORT_EVIDENCE_DEFECT_SCOPE_CONFLICT')
    return scope


def _normalised_scope_bindings(value: object) -> tuple[ReportDefectScopeBinding, ...]:
    if isinstance(value, (bytes, str)) or not isinstance(value, Sequence):
        _fail('REPORT_EVIDENCE_SCOPE_ADMISSION_INVALID')
    raw_bindings = tuple(value)
    if not raw_bindings or len(raw_bindings) > _MAX_REPORT_LOCATORS:
        _fail('REPORT_EVIDENCE_SCOPE_ADMISSION_INVALID')
    bindings: list[ReportDefectScopeBinding] = []
    label_keys: set[str] = set()
    defect_ids: set[str] = set()
    for value in raw_bindings:
        if not isinstance(value, ReportDefectScopeBinding):
            _fail('REPORT_EVIDENCE_SCOPE_ADMISSION_INVALID')
        defect_id = _required_text(
            value.defect_id,
            code='REPORT_EVIDENCE_DEFECT_INVALID',
            maximum=36,
        )
        label = _required_text(
            value.report_defect_label,
            code='REPORT_EVIDENCE_DEFECT_LABEL_INVALID',
            maximum=_MAX_REPORT_LABEL,
        )
        start_locator_key = _required_text(
            value.start_locator_key,
            code='REPORT_EVIDENCE_RANGE_INVALID',
            maximum=300,
        )
        end_locator_key = _required_text(
            value.end_locator_key,
            code='REPORT_EVIDENCE_RANGE_INVALID',
            maximum=300,
        )
        label_key = label.casefold()
        if label_key in label_keys or defect_id in defect_ids:
            _fail('REPORT_EVIDENCE_SCOPE_ADMISSION_INVALID')
        label_keys.add(label_key)
        defect_ids.add(defect_id)
        bindings.append(
            ReportDefectScopeBinding(
                defect_id=defect_id,
                report_defect_label=label,
                start_locator_key=start_locator_key,
                end_locator_key=end_locator_key,
            )
        )
    return tuple(sorted(bindings, key=lambda binding: binding.report_defect_label.casefold()))


def _approved_scope_manifest(
    db: Session,
    *,
    expected_label_manifest_id: object,
    project_id: str,
    estimate_id: str,
    stored_file_id: str,
    evidence: ProjectEvidence,
    bindings: tuple[ReportDefectScopeBinding, ...],
) -> ApprovedReportExpectedLabelManifest:
    try:
        approved = require_approved_report_expected_label_manifest(
            db,
            expected_label_manifest_id=expected_label_manifest_id,
            project_id=project_id,
            estimate_id=estimate_id,
            stored_file_id=stored_file_id,
            report_sha256=evidence.source_sha256,
        )
    except ReportExpectedLabelManifestError as exc:
        raise ReportEvidenceAdapterError(
            'REPORT_EVIDENCE_EXPECTED_LABEL_MANIFEST_INVALID'
        ) from exc
    if tuple(binding.report_defect_label for binding in bindings) != (
        approved.expected_report_defect_labels
    ):
        _fail('REPORT_EVIDENCE_EXPECTED_LABELS_MISMATCH')
    return approved


def bind_approved_report_defect_scopes(
    db: Session,
    *,
    stored_file_id: object,
    project_id: object,
    estimate_id: object,
    expected_label_manifest_id: object,
    scope_bindings: object,
) -> tuple[ReportDefectScope, ...]:
    '''Atomically admit every scope from one source-bound approved label set.'''

    stored_file = _required_text(
        stored_file_id,
        code='REPORT_EVIDENCE_STORED_FILE_INVALID',
        maximum=36,
    )
    project = _required_text(project_id, code='REPORT_EVIDENCE_PROJECT_INVALID', maximum=36)
    estimate = _required_text(estimate_id, code='REPORT_EVIDENCE_ESTIMATE_INVALID', maximum=36)
    bindings = _normalised_scope_bindings(scope_bindings)
    evidence = _report_owner(
        db,
        stored_file_id=stored_file,
        project_id=project,
        estimate_id=estimate,
    )
    approved = _approved_scope_manifest(
        db,
        expected_label_manifest_id=expected_label_manifest_id,
        project_id=project,
        estimate_id=estimate,
        stored_file_id=stored_file,
        evidence=evidence,
        bindings=bindings,
    )
    existing = tuple(
        db.scalars(
            select(ReportDefectScope).where(
                ReportDefectScope.project_evidence_id == evidence.id
            )
        ).all()
    )
    binding_defect_ids = {binding.defect_id for binding in bindings}
    if existing and (
        len(existing) != len(bindings)
        or {scope.defect_id for scope in existing} != binding_defect_ids
        or any(
            scope.approved_expected_label_manifest_id != approved.id for scope in existing
        )
    ):
        _fail('REPORT_EVIDENCE_DEFECT_SCOPE_CONFLICT')
    try:
        with db.begin_nested():
            scopes = tuple(
                _bind_report_defect_scope(
                    db,
                    stored_file_id=stored_file,
                    project_id=project,
                    estimate_id=estimate,
                    defect_id=binding.defect_id,
                    report_defect_label=binding.report_defect_label,
                    start_locator_key=binding.start_locator_key,
                    end_locator_key=binding.end_locator_key,
                    approved_expected_label_manifest_id=approved.id,
                )
                for binding in bindings
            )
    except IntegrityError:
        _fail('REPORT_EVIDENCE_DEFECT_SCOPE_CONFLICT')
    return scopes


__all__ = [
    'NormalisedReportEvidence',
    'REPORT_DEFECT_EVIDENCE_PACKET_SCHEMA',
    'REPORT_EVIDENCE_LOCATOR_SCHEMA',
    'ReportDefectEvidencePacket',
    'ReportEvidenceAdapterError',
    'ReportEvidenceLocatorItem',
    'ReportDefectScopeBinding',
    'bind_approved_report_defect_scopes',
    'build_report_defect_evidence_packet',
    'build_report_defect_evidence_packets',
    'materialise_project_report_locators_for_update',
    'normalise_verified_pdf_report',
    'validate_report_defect_evidence_packet',
    'validate_report_defect_v2_proposal',
]
