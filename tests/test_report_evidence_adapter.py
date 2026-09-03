from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import datetime

import pymupdf
import pytest
import xlsxwriter
from PIL import Image
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_phase8_visual_proposal import _proposal

import classifire.services.report_evidence_adapter as report_evidence_adapter
from classifire import physical_models  # noqa: F401
from classifire.db import Base
from classifire.models import (
    Estimate,
    Opening,
    Project,
    ReportDefectScope,
    ReportEvidenceLocator,
    Service,
    StoredFile,
    User,
)
from classifire.physical_models import Defect
from classifire.services.project_evidence import bind_project_evidence
from classifire.services.report_evidence_adapter import (
    ReportDefectEvidencePacket,
    ReportDefectScopeBinding,
    ReportEvidenceAdapterError,
    _register_report_evidence_locators,
    _table_shape,
    bind_approved_report_defect_scopes,
    build_report_defect_evidence_packet,
    build_report_defect_evidence_packets,
    normalise_verified_docx_report,
    normalise_verified_pdf_report,
    normalise_verified_report,
    validate_report_defect_evidence_packet,
    validate_report_defect_v2_proposal,
)
from classifire.services.report_expected_label_manifest import (
    record_approved_report_expected_label_manifest,
)
from classifire.services.storage import VerifiedStoredFileContent


@contextmanager
def adapter_session() -> Iterator[Session]:
    engine = create_engine(
        'sqlite+pysqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _pdf_bytes() -> bytes:
    image_stream = io.BytesIO()
    Image.new('RGB', (8, 8), color=(20, 40, 60)).save(image_stream, format='PNG')
    document = pymupdf.open()
    try:
        document.set_metadata({'title': 'Private report heading', 'author': 'Example author'})
        page = document.new_page()
        page.insert_text((72, 72), 'Defect D-001 is described in this private report.')
        page.draw_rect(pymupdf.Rect(70, 100, 180, 160), color=(1, 0, 0))
        annotation = page.add_text_annot((72, 180), 'Private annotation content')
        annotation.update()
        page.insert_image(pymupdf.Rect(200, 70, 260, 130), stream=image_stream.getvalue())
        return document.tobytes(garbage=3, deflate=True)
    finally:
        document.close()


def _report_content(payload: bytes | None = None) -> VerifiedStoredFileContent:
    bytes_value = payload or _pdf_bytes()
    return VerifiedStoredFileContent(
        sha256=hashlib.sha256(bytes_value).hexdigest(),
        size_bytes=len(bytes_value),
        media_type='application/pdf',
        content=bytes_value,
    )


def _xlsx_report_content(*, hidden_worksheet: bool = False) -> VerifiedStoredFileContent:
    stream = io.BytesIO()
    workbook = xlsxwriter.Workbook(stream, {'in_memory': True})
    try:
        date_format = workbook.add_format({'num_format': 'yyyy-mm-dd'})
        first = workbook.add_worksheet('Private review data')
        first.write('A1', 'Defect D-001 is described in this private workbook.')
        first.write('B1', 42)
        first.write('C1', True)
        first.write_formula('A2', '=B1*2')
        first.write_datetime('B2', datetime(2026, 9, 3), date_format)
        second = workbook.add_worksheet('Follow-up')
        second.write('A1', 'D-002')
        if hidden_worksheet:
            second.hide()
    finally:
        workbook.close()
    payload = stream.getvalue()
    return VerifiedStoredFileContent(
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        content=payload,
    )


def _docx_report_content(
    *,
    external_relationship: bool = False,
    embedded_media: bool = False,
    forbidden_body_feature: bool = False,
) -> VerifiedStoredFileContent:
    relationship_mode = ' TargetMode="External"' if external_relationship else ''
    relationship_target = (
        'https://example.invalid/report' if external_relationship else 'word/document.xml'
    )
    content_types = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        b'  <Default Extension="rels" '
        b'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
        b'  <Default Extension="xml" ContentType="application/xml"/>\n'
        b'  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
        b'officedocument.wordprocessingml.document.main+xml"/>\n'
        b'</Types>'
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        f'Target="{relationship_target}"{relationship_mode}/>'
        '</Relationships>'
    ).encode()
    document = b'''<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>Private DOCX paragraph for Defect D-001.</w:t></w:r></w:p>
    <w:tbl>
      <w:tr>
        <w:tc><w:p><w:r><w:t>Private table left.</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Private table right.</w:t></w:r></w:p></w:tc>
      </w:tr>
      <w:tr>
        <w:tc><w:p><w:r><w:t>Follow-up 1.</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Follow-up 2.</w:t></w:r></w:p></w:tc>
      </w:tr>
    </w:tbl>
    <w:p><w:r><w:t>Private DOCX follow-up paragraph.</w:t></w:r></w:p>
    <w:sectPr/>
  </w:body>
</w:document>'''
    if forbidden_body_feature:
        document = document.replace(
            b'<w:r><w:t>Private DOCX paragraph for Defect D-001.</w:t></w:r>',
            b'<w:r><w:drawing/><w:t>Private DOCX paragraph for Defect D-001.</w:t></w:r>',
        )
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('[Content_Types].xml', content_types)
        archive.writestr('_rels/.rels', relationships)
        archive.writestr('word/document.xml', document)
        if embedded_media:
            archive.writestr('word/media/private-image.png', b'synthetic image bytes')
    payload = stream.getvalue()
    return VerifiedStoredFileContent(
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        content=payload,
    )


def _caption_report_content(
    *,
    caption_text: str = 'Figure 12: Proposed service penetration context.',
) -> VerifiedStoredFileContent:
    document = pymupdf.open()
    try:
        page = document.new_page()
        page.insert_text((72, 72), 'Ordinary report narrative remains unclassified.')
        page.insert_text((72, 120), caption_text)
        payload = document.tobytes(garbage=3, deflate=True)
    finally:
        document.close()
    return _report_content(payload)


def test_normaliser_is_deterministic_and_keeps_raw_report_content_out_of_locators() -> None:
    content = _report_content()

    first = normalise_verified_pdf_report(content)
    second = normalise_verified_pdf_report(content)

    assert first.manifest == second.manifest
    assert first.page_count == 1
    assert {item.item_kind for item in first.locators}.issuperset(
        {'metadata', 'page', 'text', 'drawing', 'annotation', 'image'}
    )
    assert all(item.item_kind != 'caption' for item in first.locators)
    assert all(item.content_sha256 != content.sha256 for item in first.locators)
    serialised = json.dumps(first.manifest, sort_keys=True)
    assert 'Private report heading' not in serialised
    assert 'Private annotation content' not in serialised
    assert 'Defect D-001 is described' not in serialised
    assert all(item.locator['sequence'] == index for index, item in enumerate(first.locators, 1))


def test_normaliser_classifies_only_explicit_numbered_captions_without_persisting_text() -> None:
    caption_text = 'Figure 12: Proposed service penetration context.'
    content = _caption_report_content(caption_text=caption_text)

    first = normalise_verified_pdf_report(content)
    second = normalise_verified_pdf_report(content)
    caption = next(item for item in first.locators if item.item_kind == 'caption')

    assert first.manifest == second.manifest
    assert caption.locator['caption_kind'] == 'figure'
    assert set(caption.locator) == {
        'item_kind',
        'page_number',
        'bounds',
        'character_count',
        'caption_kind',
        'block_index',
        'sequence',
    }
    assert caption.content_sha256 != content.sha256
    assert caption_text not in json.dumps(first.manifest, sort_keys=True)
    assert 'Figure 12' not in json.dumps(first.manifest, sort_keys=True)
    assert any(item.item_kind == 'text' for item in first.locators)


@pytest.mark.parametrize(
    'caption_text',
    (
        'Figure this ordinary narrative remains unclassified.',
        'Figure 0: Invalid caption number.',
        'Figure 1. Missing explicit caption delimiter.',
        'Photograph 1000000: Caption number exceeds the bounded syntax.',
    ),
)
def test_normaliser_does_not_infer_captions_from_ambiguous_text(caption_text: str) -> None:
    report = normalise_verified_pdf_report(_caption_report_content(caption_text=caption_text))

    assert all(item.item_kind != 'caption' for item in report.locators)
    assert sum(item.item_kind == 'text' for item in report.locators) == 2


@pytest.mark.parametrize(
    ('content', 'code'),
    [
        (
            VerifiedStoredFileContent(
                sha256='0' * 64,
                size_bytes=4,
                media_type='application/pdf',
                content=b'test',
            ),
            'REPORT_EVIDENCE_SOURCE_HASH_MISMATCH',
        ),
        (
            VerifiedStoredFileContent(
                sha256=hashlib.sha256(b'test').hexdigest(),
                size_bytes=4,
                media_type='image/png',
                content=b'test',
            ),
            'REPORT_EVIDENCE_MEDIA_TYPE_FORBIDDEN',
        ),
    ],
)
def test_normaliser_rejects_unbound_or_non_pdf_content(
    content: VerifiedStoredFileContent,
    code: str,
) -> None:
    with pytest.raises(ReportEvidenceAdapterError) as raised:
        normalise_verified_pdf_report(content)

    assert raised.value.code == code

def test_docx_normaliser_is_deterministic_and_keeps_document_content_out_of_locators() -> None:
    content = _docx_report_content()

    first = normalise_verified_docx_report(content)
    second = normalise_verified_report(content)

    assert first.manifest == second.manifest
    assert first.page_count == 1
    assert [item.item_kind for item in first.locators] == [
        'document',
        'paragraph',
        'document_table',
        'paragraph',
    ]
    assert [
        item.locator['body_index'] for item in first.locators if item.item_kind == 'paragraph'
    ] == [1, 3]
    table = next(item for item in first.locators if item.item_kind == 'document_table')
    assert table.locator['body_index'] == 2
    assert table.locator['table_index'] == 1
    assert table.locator['row_count'] == 2
    assert table.locator['column_count'] == 2
    serialised = json.dumps(first.manifest, sort_keys=True)
    assert 'Private DOCX paragraph' not in serialised
    assert 'Private table left' not in serialised
    assert 'Defect D-001' not in serialised
    assert all(item.page_number is None for item in first.locators)
    assert all(item.locator['sequence'] == index for index, item in enumerate(first.locators, 1))


def test_docx_paragraphs_and_tables_can_form_an_approved_proposal_only_defect_scope() -> None:
    content = _docx_report_content()
    report = normalise_verified_report(content)
    with adapter_session() as db:
        project = _project(db, 50)
        estimate = _estimate(db, project, 50)
        stored = _bound_report(db, project, content)
        defect = _defect(db, estimate)
        records = _register_report_evidence_locators(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
            report=report,
        )
        paragraph = next(record for record in records if record.item_kind == 'paragraph')
        table = next(record for record in records if record.item_kind == 'document_table')
        document = next(record for record in records if record.item_kind == 'document')
        manifest_id = _approved_expected_label_manifest_id(
            db,
            project=project,
            estimate=estimate,
            stored=stored,
            labels=['D-001'],
            ordinal=50,
        )
        with pytest.raises(ReportEvidenceAdapterError) as document_range:
            bind_approved_report_defect_scopes(
                db,
                stored_file_id=stored.id,
                project_id=project.id,
                estimate_id=estimate.id,
                expected_label_manifest_id=manifest_id,
                scope_bindings=(
                    ReportDefectScopeBinding(
                        defect_id=defect.id,
                        report_defect_label='D-001',
                        start_locator_key=document.locator_key,
                        end_locator_key=paragraph.locator_key,
                    ),
                ),
            )
        assert document_range.value.code == 'REPORT_EVIDENCE_RANGE_INVALID'
        bind_approved_report_defect_scopes(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
            expected_label_manifest_id=manifest_id,
            scope_bindings=(
                ReportDefectScopeBinding(
                    defect_id=defect.id,
                    report_defect_label='D-001',
                    start_locator_key=paragraph.locator_key,
                    end_locator_key=table.locator_key,
                ),
            ),
        )
        packet = build_report_defect_evidence_packet(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
            defect_id=defect.id,
        )

        assert validate_report_defect_evidence_packet(packet) == []
        assert [artifact['item_kind'] for artifact in packet.manifest['artifacts']] == [
            'paragraph',
            'document_table',
        ]
        assert 'Private DOCX paragraph' not in json.dumps(packet.manifest, sort_keys=True)
        assert db.scalar(select(func.count()).select_from(Opening)) == 0
        assert db.scalar(select(func.count()).select_from(Service)) == 0

def test_docx_normaliser_fails_closed_on_external_links_and_embedded_features() -> None:
    with pytest.raises(ReportEvidenceAdapterError) as external:
        normalise_verified_report(_docx_report_content(external_relationship=True))
    with pytest.raises(ReportEvidenceAdapterError) as media:
        normalise_verified_report(_docx_report_content(embedded_media=True))
    with pytest.raises(ReportEvidenceAdapterError) as body_feature:
        normalise_verified_report(_docx_report_content(forbidden_body_feature=True))

    assert external.value.code == 'REPORT_EVIDENCE_DOCX_FEATURE_FORBIDDEN'
    assert media.value.code == 'REPORT_EVIDENCE_DOCX_FEATURE_FORBIDDEN'
    assert body_feature.value.code == 'REPORT_EVIDENCE_DOCX_FEATURE_FORBIDDEN'


def test_xlsx_normaliser_is_deterministic_and_keeps_workbook_content_out_of_locators() -> None:
    content = _xlsx_report_content()

    first = normalise_verified_report(content)
    second = normalise_verified_report(content)

    assert first.manifest == second.manifest
    assert first.page_count == 2
    assert {item.item_kind for item in first.locators} == {'worksheet', 'cell'}
    worksheets = [item for item in first.locators if item.item_kind == 'worksheet']
    assert [item.locator['worksheet_index'] for item in worksheets] == [1, 2]
    assert all(item.page_number is None for item in first.locators)
    assert all(
        set(item.locator)
        == {
            'item_kind',
            'page_number',
            'worksheet_index',
            'max_row',
            'max_column',
            'nonempty_cell_count',
            'sequence',
        }
        for item in worksheets
    )
    serialised = json.dumps(first.manifest, sort_keys=True)
    assert 'Private review data' not in serialised
    assert 'Defect D-001 is described' not in serialised
    assert '=B1*2' not in serialised
    assert all(item.locator['sequence'] == index for index, item in enumerate(first.locators, 1))

    with adapter_session() as db:
        project = _project(db, 48)
        estimate = _estimate(db, project, 48)
        stored = _bound_report(db, project, content)
        records = _register_report_evidence_locators(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
            report=first,
        )
        assert [record.item_kind for record in records] == [
            item.item_kind for item in first.locators
        ]
        assert all(record.page_number is None for record in records)
        assert 'Private review data' not in json.dumps(
            [record.locator_json for record in records],
            sort_keys=True,
        )


def test_xlsx_cells_can_form_an_approved_proposal_only_defect_scope() -> None:
    content = _xlsx_report_content()
    report = normalise_verified_report(content)
    with adapter_session() as db:
        project = _project(db, 49)
        estimate = _estimate(db, project, 49)
        stored = _bound_report(db, project, content)
        defect = _defect(db, estimate)
        records = _register_report_evidence_locators(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
            report=report,
        )
        cells = [record for record in records if record.item_kind == 'cell']
        manifest_id = _approved_expected_label_manifest_id(
            db,
            project=project,
            estimate=estimate,
            stored=stored,
            labels=['D-001'],
            ordinal=49,
        )
        worksheet = next(record for record in records if record.item_kind == 'worksheet')
        with pytest.raises(ReportEvidenceAdapterError) as worksheet_range:
            bind_approved_report_defect_scopes(
                db,
                stored_file_id=stored.id,
                project_id=project.id,
                estimate_id=estimate.id,
                expected_label_manifest_id=manifest_id,
                scope_bindings=(
                    ReportDefectScopeBinding(
                        defect_id=defect.id,
                        report_defect_label='D-001',
                        start_locator_key=worksheet.locator_key,
                        end_locator_key=cells[-1].locator_key,
                    ),
                ),
            )
        assert worksheet_range.value.code == 'REPORT_EVIDENCE_RANGE_INVALID'
        scopes = bind_approved_report_defect_scopes(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
            expected_label_manifest_id=manifest_id,
            scope_bindings=(
                ReportDefectScopeBinding(
                    defect_id=defect.id,
                    report_defect_label='D-001',
                    start_locator_key=cells[0].locator_key,
                    end_locator_key=cells[-1].locator_key,
                ),
            ),
        )
        packet = build_report_defect_evidence_packet(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
            defect_id=defect.id,
        )

        assert len(scopes) == 1
        assert validate_report_defect_evidence_packet(packet) == []
        assert all(artifact['item_kind'] == 'cell' for artifact in packet.manifest['artifacts'])
        assert all(artifact['page_number'] is None for artifact in packet.manifest['artifacts'])
        assert 'Defect D-001 is described' not in json.dumps(packet.manifest, sort_keys=True)
        assert db.scalar(select(func.count()).select_from(Opening)) == 0
        assert db.scalar(select(func.count()).select_from(Service)) == 0

def test_xlsx_normaliser_fails_closed_on_hidden_worksheets_and_embedded_media() -> None:
    with pytest.raises(ReportEvidenceAdapterError) as hidden:
        normalise_verified_report(_xlsx_report_content(hidden_worksheet=True))

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('[Content_Types].xml', '<Types/>')
        archive.writestr('xl/media/image.png', b'synthetic image bytes')
    unsafe_bytes = stream.getvalue()
    unsafe_content = VerifiedStoredFileContent(
        sha256=hashlib.sha256(unsafe_bytes).hexdigest(),
        size_bytes=len(unsafe_bytes),
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        content=unsafe_bytes,
    )
    with pytest.raises(ReportEvidenceAdapterError) as media:
        normalise_verified_report(unsafe_content)

    assert hidden.value.code == 'REPORT_EVIDENCE_XLSX_FEATURE_FORBIDDEN'
    assert media.value.code == 'REPORT_EVIDENCE_XLSX_FEATURE_FORBIDDEN'

def test_xlsx_normaliser_fails_closed_without_defused_xml(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(report_evidence_adapter, 'DEFUSEDXML', False)

    with pytest.raises(ReportEvidenceAdapterError) as raised:
        normalise_verified_report(_xlsx_report_content())

    assert raised.value.code == 'REPORT_EVIDENCE_XLSX_PARSER_UNSAFE'

def test_table_shape_rejects_an_excessive_total_cell_count() -> None:
    with pytest.raises(ReportEvidenceAdapterError) as raised:
        _table_shape([[''] * 200 for _ in range(501)])

    assert raised.value.code == 'REPORT_EVIDENCE_TABLE_OUT_OF_POLICY'


def _project(db: Session, ordinal: int) -> Project:
    project = Project(
        reference=f'REPORT-ADAPTER-{ordinal}',
        name=f'Report adapter {ordinal}',
    )
    db.add(project)
    db.flush()
    return project


def _estimate(db: Session, project: Project, ordinal: int) -> Estimate:
    estimate = Estimate(
        project_id=project.id,
        revision=ordinal,
        reference=f'REPORT-ADAPTER-ESTIMATE-{ordinal}',
        title=f'Report adapter estimate {ordinal}',
    )
    db.add(estimate)
    db.flush()
    return estimate


def _bound_report(db: Session, project: Project, content: VerifiedStoredFileContent) -> StoredFile:
    stored = StoredFile(
        original_filename='report.pdf',
        media_type=content.media_type,
        storage_path='storage/report.pdf',
        sha256=content.sha256,
        size_bytes=content.size_bytes,
        purpose='project_evidence',
        malware_scan_status='clean',
        immutable=True,
    )
    db.add(stored)
    db.flush()
    bind_project_evidence(db, stored_file_id=stored.id, project_id=project.id)
    return stored


def _defect(db: Session, estimate: Estimate, reference: str = 'D-001') -> Defect:
    defect = Defect(
        estimate_id=estimate.id,
        external_defect_id=reference,
        defect_code=reference,
        evidence_status='provisional',
        status='draft',
    )
    db.add(defect)
    db.flush()
    return defect

def _approved_expected_label_manifest_id(
    db: Session,
    *,
    project: Project,
    estimate: Estimate,
    stored: StoredFile,
    labels: list[str],
    ordinal: int,
) -> str:
    reviewer = User(
        email=f'report-scope-reviewer-{ordinal}@example.test',
        full_name='Report scope reviewer',
        password_hash='not-used-by-synthetic-tests',  # noqa: S106
        role='reviewer',
    )
    db.add(reviewer)
    db.flush()
    approved = record_approved_report_expected_label_manifest(
        db,
        project_id=project.id,
        estimate_id=estimate.id,
        stored_file_id=stored.id,
        report_sha256=stored.sha256,
        expected_report_defect_labels=labels,
        approval_reference=f'synthetic report scope approval {ordinal}',
        approved_by_user_id=reviewer.id,
    )
    return approved.id



def _scoped_report_packet(
    db: Session,
    *,
    ordinal: int,
) -> tuple[Project, Estimate, StoredFile, Defect, tuple[ReportEvidenceLocator, ...]]:
    project = _project(db, ordinal)
    estimate = _estimate(db, project, ordinal)
    content = _report_content()
    stored = _bound_report(db, project, content)
    defect = _defect(db, estimate)
    records = _register_report_evidence_locators(
        db,
        stored_file_id=stored.id,
        project_id=project.id,
        estimate_id=estimate.id,
        report=normalise_verified_pdf_report(content),
    )
    page_records = tuple(record for record in records if record.page_number == 1)
    manifest_id = _approved_expected_label_manifest_id(
        db,
        project=project,
        estimate=estimate,
        stored=stored,
        labels=['D-001'],
        ordinal=ordinal,
    )
    bind_approved_report_defect_scopes(
        db,
        stored_file_id=stored.id,
        project_id=project.id,
        estimate_id=estimate.id,
        expected_label_manifest_id=manifest_id,
        scope_bindings=(
            ReportDefectScopeBinding(
                defect_id=defect.id,
                report_defect_label='D-001',
                start_locator_key=page_records[0].locator_key,
                end_locator_key=page_records[-1].locator_key,
            ),
        ),
    )
    return project, estimate, stored, defect, records

def _multi_scoped_report_packet(
    db: Session,
    *,
    ordinal: int,
) -> tuple[
    Project,
    Estimate,
    StoredFile,
    Defect,
    Defect,
    tuple[ReportEvidenceLocator, ...],
    tuple[ReportDefectScope, ...],
]:
    project = _project(db, ordinal)
    estimate = _estimate(db, project, ordinal)
    content = _report_content()
    stored = _bound_report(db, project, content)
    first_defect = _defect(db, estimate, reference='D-001')
    second_defect = _defect(db, estimate, reference='D-002')
    records = _register_report_evidence_locators(
        db,
        stored_file_id=stored.id,
        project_id=project.id,
        estimate_id=estimate.id,
        report=normalise_verified_pdf_report(content),
    )
    page_records = tuple(record for record in records if record.page_number == 1)
    manifest_id = _approved_expected_label_manifest_id(
        db,
        project=project,
        estimate=estimate,
        stored=stored,
        labels=['D-001', 'D-002'],
        ordinal=ordinal,
    )
    scopes = bind_approved_report_defect_scopes(
        db,
        stored_file_id=stored.id,
        project_id=project.id,
        estimate_id=estimate.id,
        expected_label_manifest_id=manifest_id,
        scope_bindings=(
            ReportDefectScopeBinding(
                defect_id=first_defect.id,
                report_defect_label='D-001',
                start_locator_key=page_records[0].locator_key,
                end_locator_key=page_records[-1].locator_key,
            ),
            ReportDefectScopeBinding(
                defect_id=second_defect.id,
                report_defect_label='D-002',
                start_locator_key=page_records[0].locator_key,
                end_locator_key=page_records[-1].locator_key,
            ),
        ),
    )
    return project, estimate, stored, first_defect, second_defect, records, scopes



def _documentary_v2_proposal(evidence_ref: str) -> dict[str, object]:
    proposal = deepcopy(_proposal())
    for collection in ('openings', 'services'):
        for row in proposal[collection]:
            for assessment in row['property_assessments'].values():
                assessment['evidence_refs'] = [evidence_ref]
    return proposal


def test_locators_and_selected_defect_scope_are_idempotent_and_noncanonical() -> None:
    content = _report_content()
    report = normalise_verified_pdf_report(content)
    with adapter_session() as db:
        project = _project(db, 1)
        estimate = _estimate(db, project, 1)
        stored = _bound_report(db, project, content)
        defect = _defect(db, estimate)

        first = _register_report_evidence_locators(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
            report=report,
        )
        second = _register_report_evidence_locators(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
            report=report,
        )
        page_locators = [record for record in first if record.page_number == 1]
        manifest_id = _approved_expected_label_manifest_id(
            db,
            project=project,
            estimate=estimate,
            stored=stored,
            labels=['D-001'],
            ordinal=1,
        )
        binding = ReportDefectScopeBinding(
            defect_id=defect.id,
            report_defect_label='D-001',
            start_locator_key=page_locators[0].locator_key,
            end_locator_key=page_locators[-1].locator_key,
        )
        scope = bind_approved_report_defect_scopes(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
            expected_label_manifest_id=manifest_id,
            scope_bindings=(binding,),
        )[0]
        repeated_scope = bind_approved_report_defect_scopes(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
            expected_label_manifest_id=manifest_id,
            scope_bindings=(binding,),
        )[0]

        assert [record.id for record in first] == [record.id for record in second]
        assert scope.id == repeated_scope.id
        assert scope.source_sha256 == stored.sha256
        assert (
            db.scalar(select(func.count()).select_from(ReportEvidenceLocator))
            == len(report.locators)
        )
        assert db.scalar(select(func.count()).select_from(ReportDefectScope)) == 1
        assert db.scalar(select(func.count()).select_from(Opening)) == 0
        assert db.scalar(select(func.count()).select_from(Service)) == 0

def test_scope_admission_requires_the_complete_approved_set_and_retains_its_binding() -> None:
    content = _report_content()
    with adapter_session() as db:
        project = _project(db, 1101)
        estimate = _estimate(db, project, 1101)
        stored = _bound_report(db, project, content)
        first_defect = _defect(db, estimate, reference='D-001')
        second_defect = _defect(db, estimate, reference='D-002')
        records = _register_report_evidence_locators(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
            report=normalise_verified_pdf_report(content),
        )
        page_records = tuple(record for record in records if record.page_number == 1)
        manifest_id = _approved_expected_label_manifest_id(
            db,
            project=project,
            estimate=estimate,
            stored=stored,
            labels=['D-001', 'D-002'],
            ordinal=1101,
        )
        first_binding = ReportDefectScopeBinding(
            defect_id=first_defect.id,
            report_defect_label='D-001',
            start_locator_key=page_records[0].locator_key,
            end_locator_key=page_records[-1].locator_key,
        )
        second_binding = ReportDefectScopeBinding(
            defect_id=second_defect.id,
            report_defect_label='D-002',
            start_locator_key=page_records[0].locator_key,
            end_locator_key=page_records[-1].locator_key,
        )

        with pytest.raises(ReportEvidenceAdapterError) as incomplete:
            bind_approved_report_defect_scopes(
                db,
                stored_file_id=stored.id,
                project_id=project.id,
                estimate_id=estimate.id,
                expected_label_manifest_id=manifest_id,
                scope_bindings=(first_binding,),
            )

        assert incomplete.value.code == 'REPORT_EVIDENCE_EXPECTED_LABELS_MISMATCH'
        assert db.scalar(select(func.count()).select_from(ReportDefectScope)) == 0

        scopes = bind_approved_report_defect_scopes(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
            expected_label_manifest_id=manifest_id,
            scope_bindings=(second_binding, first_binding),
        )
        packets = build_report_defect_evidence_packets(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
        )

        assert [scope.report_defect_label for scope in scopes] == ['D-001', 'D-002']
        assert {scope.approved_expected_label_manifest_id for scope in scopes} == {manifest_id}
        assert all(
            packet.manifest['schema'] == 'CLASSIFIRE-REPORT-DEFECT-EVIDENCE-PACKET-v2'
            for packet in packets
        )
        assert {
            packet.manifest['approved_expected_label_manifest_id'] for packet in packets
        } == {manifest_id}
        assert all(validate_report_defect_evidence_packet(packet) == [] for packet in packets)



def test_scope_admission_rolls_back_every_scope_if_one_range_is_invalid() -> None:
    content = _report_content()
    with adapter_session() as db:
        project = _project(db, 1102)
        estimate = _estimate(db, project, 1102)
        stored = _bound_report(db, project, content)
        first_defect = _defect(db, estimate, reference='D-001')
        second_defect = _defect(db, estimate, reference='D-002')
        records = _register_report_evidence_locators(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
            report=normalise_verified_pdf_report(content),
        )
        page_records = tuple(record for record in records if record.page_number == 1)
        manifest_id = _approved_expected_label_manifest_id(
            db,
            project=project,
            estimate=estimate,
            stored=stored,
            labels=['D-001', 'D-002'],
            ordinal=1102,
        )

        with pytest.raises(ReportEvidenceAdapterError) as invalid_range:
            bind_approved_report_defect_scopes(
                db,
                stored_file_id=stored.id,
                project_id=project.id,
                estimate_id=estimate.id,
                expected_label_manifest_id=manifest_id,
                scope_bindings=(
                    ReportDefectScopeBinding(
                        defect_id=first_defect.id,
                        report_defect_label='D-001',
                        start_locator_key=page_records[0].locator_key,
                        end_locator_key=page_records[-1].locator_key,
                    ),
                    ReportDefectScopeBinding(
                        defect_id=second_defect.id,
                        report_defect_label='D-002',
                        start_locator_key=page_records[-1].locator_key,
                        end_locator_key=page_records[0].locator_key,
                    ),
                ),
            )

        assert invalid_range.value.code == 'REPORT_EVIDENCE_RANGE_INVALID'
        assert db.scalar(select(func.count()).select_from(ReportDefectScope)) == 0
def test_selected_report_scope_is_content_safe_and_feeds_existing_v2_policy() -> None:
    with adapter_session() as db:
        project, estimate, stored, defect, records = _scoped_report_packet(db, ordinal=4)
        packet = build_report_defect_evidence_packet(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
            defect_id=defect.id,
        )
        repeated = build_report_defect_evidence_packet(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
            defect_id=defect.id,
        )
        assert packet.manifest == repeated.manifest
        assert validate_report_defect_evidence_packet(packet) == []
        assert packet.manifest['report_sha256'] == stored.sha256
        assert packet.manifest['defect_reference'] == 'D-001'
        assert len(packet.evidence_refs) == len(packet.manifest['artifacts'])
        assert all(
            reference.startswith('report-locator:') for reference in packet.evidence_refs
        )
        serialised = json.dumps(packet.manifest, sort_keys=True)
        assert 'Private report heading' not in serialised
        assert 'Private annotation content' not in serialised
        assert 'Defect D-001 is described' not in serialised
        proposal = _documentary_v2_proposal(next(iter(packet.evidence_refs)))
        assert validate_report_defect_v2_proposal(packet, proposal) == []
        metadata = next(record for record in records if record.page_number is None)
        proposal['openings'][0]['property_assessments']['size']['evidence_refs'] = [
            f'report-locator:{metadata.locator_key}'
        ]
        errors = validate_report_defect_v2_proposal(packet, proposal)
        assert any('outside the approved manifest' in error for error in errors)
        tampered = ReportDefectEvidencePacket(
            manifest=deepcopy(packet.manifest),
            manifest_sha256=packet.manifest_sha256,
        )
        tampered.manifest['artifacts'][0]['locator']['raw_text'] = 'tampered packet text'
        assert any(
            'hash does not match' in error
            for error in validate_report_defect_evidence_packet(tampered)
        )
        assert validate_report_defect_v2_proposal(tampered, proposal)
        assert db.scalar(select(func.count()).select_from(Opening)) == 0
        assert db.scalar(select(func.count()).select_from(Service)) == 0


def test_all_selected_report_scopes_are_returned_in_stable_package_order() -> None:
    with adapter_session() as db:
        project, estimate, stored, first_defect, second_defect, _records, scopes = (
            _multi_scoped_report_packet(db, ordinal=45)
        )
        second_scope = next(scope for scope in scopes if scope.defect_id == second_defect.id)
        first_packet = build_report_defect_evidence_packet(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
            defect_id=first_defect.id,
        )

        packets = build_report_defect_evidence_packets(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
        )
        repeated = build_report_defect_evidence_packets(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
        )

        assert [packet.manifest['report_defect_label'] for packet in packets] == ['D-001', 'D-002']
        assert [packet.manifest['defect_id'] for packet in packets] == [
            first_defect.id,
            second_defect.id,
        ]
        assert {packet.manifest['scope_id'] for packet in packets} == {
            second_scope.id,
            first_packet.manifest['scope_id'],
        }
        assert [packet.manifest_sha256 for packet in packets] == [
            packet.manifest_sha256 for packet in repeated
        ]
        assert all(validate_report_defect_evidence_packet(packet) == [] for packet in packets)
        assert db.scalar(select(func.count()).select_from(Opening)) == 0
        assert db.scalar(select(func.count()).select_from(Service)) == 0


def test_all_selected_report_scopes_fail_closed_when_none_are_bound() -> None:
    with adapter_session() as db:
        project = _project(db, 46)
        estimate = _estimate(db, project, 46)
        stored = _bound_report(db, project, _report_content())

        with pytest.raises(ReportEvidenceAdapterError) as raised:
            build_report_defect_evidence_packets(
                db,
                stored_file_id=stored.id,
                project_id=project.id,
                estimate_id=estimate.id,
            )

    assert raised.value.code == 'REPORT_EVIDENCE_DEFECT_SCOPE_REQUIRED'


def test_selected_report_scope_fails_closed_on_cross_project_and_tampered_locator() -> None:
    with adapter_session() as db:
        project, estimate, stored, defect, records = _scoped_report_packet(db, ordinal=5)
        other_project = _project(db, 6)
        other_estimate = _estimate(db, other_project, 6)
        with pytest.raises(ReportEvidenceAdapterError) as cross_project:
            build_report_defect_evidence_packet(
                db,
                stored_file_id=stored.id,
                project_id=other_project.id,
                estimate_id=other_estimate.id,
                defect_id=defect.id,
            )
        scoped_record = next(record for record in records if record.page_number == 1)
        scoped_record.locator_json = {
            **scoped_record.locator_json,
            'raw_text': 'must never enter a report packet',
        }
        db.flush()
        with pytest.raises(ReportEvidenceAdapterError) as tampered_locator:
            build_report_defect_evidence_packet(
                db,
                stored_file_id=stored.id,
                project_id=project.id,
                estimate_id=estimate.id,
                defect_id=defect.id,
            )

    assert cross_project.value.code == 'PROJECT_EVIDENCE_CROSS_PROJECT_FORBIDDEN'
    assert tampered_locator.value.code == 'REPORT_EVIDENCE_LOCATOR_INVALID'


def test_caption_locator_registration_rejects_tampered_category_or_raw_text() -> None:
    content = _caption_report_content()
    report = normalise_verified_pdf_report(content)
    caption = next(item for item in report.locators if item.item_kind == 'caption')

    unsafe_reports = (
        replace(caption, locator={**caption.locator, 'caption_kind': 'unclassified'}),
        replace(
            caption,
            locator={**caption.locator, 'raw_caption': 'must never be persisted'},
        ),
    )
    with adapter_session() as db:
        project = _project(db, 47)
        estimate = _estimate(db, project, 47)
        stored = _bound_report(db, project, content)
        for unsafe_caption in unsafe_reports:
            unsafe_report = replace(
                report,
                locators=tuple(
                    unsafe_caption if item.locator_key == unsafe_caption.locator_key else item
                    for item in report.locators
                ),
            )
            with pytest.raises(ReportEvidenceAdapterError) as raised:
                _register_report_evidence_locators(
                    db,
                    stored_file_id=stored.id,
                    project_id=project.id,
                    estimate_id=estimate.id,
                    report=unsafe_report,
                )
            assert raised.value.code == 'REPORT_EVIDENCE_LOCATOR_INVALID'


def test_locator_registration_and_scope_fail_closed_on_conflict_or_wrong_project() -> None:
    content = _report_content()
    report = normalise_verified_pdf_report(content)
    with adapter_session() as db:
        project = _project(db, 2)
        estimate = _estimate(db, project, 2)
        stored = _bound_report(db, project, content)
        defect = _defect(db, estimate)
        locators = _register_report_evidence_locators(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
            report=report,
        )
        page_locators = [record for record in locators if record.page_number == 1]
        manifest_id = _approved_expected_label_manifest_id(
            db,
            project=project,
            estimate=estimate,
            stored=stored,
            labels=['D-001'],
            ordinal=2,
        )
        binding = ReportDefectScopeBinding(
            defect_id=defect.id,
            report_defect_label='D-001',
            start_locator_key=page_locators[0].locator_key,
            end_locator_key=page_locators[-1].locator_key,
        )
        other_project = _project(db, 3)
        other_estimate = _estimate(db, other_project, 3)

        changed_item = replace(report.locators[0], content_sha256='f' * 64)
        changed_report = replace(
            report,
            locators=(changed_item, *report.locators[1:]),
        )
        text_item = next(item for item in report.locators if item.item_kind == 'text')
        unsafe_item = replace(
            text_item,
            locator={**text_item.locator, 'raw_text': 'must never be persisted'},
        )
        unsafe_report = replace(
            report,
            locators=tuple(
                unsafe_item if item.locator_key == unsafe_item.locator_key else item
                for item in report.locators
            ),
        )
        with pytest.raises(ReportEvidenceAdapterError) as changed_manifest:
            _register_report_evidence_locators(
                db,
                stored_file_id=stored.id,
                project_id=project.id,
                estimate_id=estimate.id,
                report=changed_report,
            )
        with pytest.raises(ReportEvidenceAdapterError) as unsafe_manifest:
            _register_report_evidence_locators(
                db,
                stored_file_id=stored.id,
                project_id=project.id,
                estimate_id=estimate.id,
                report=unsafe_report,
            )
        with pytest.raises(ReportEvidenceAdapterError) as cross_project:
            bind_approved_report_defect_scopes(
                db,
                stored_file_id=stored.id,
                project_id=other_project.id,
                estimate_id=other_estimate.id,
                expected_label_manifest_id=manifest_id,
                scope_bindings=(binding,),
            )
        with pytest.raises(ReportEvidenceAdapterError) as reversed_range:
            bind_approved_report_defect_scopes(
                db,
                stored_file_id=stored.id,
                project_id=project.id,
                estimate_id=estimate.id,
                expected_label_manifest_id=manifest_id,
                scope_bindings=(
                    replace(
                        binding,
                        start_locator_key=page_locators[-1].locator_key,
                        end_locator_key=page_locators[0].locator_key,
                    ),
                ),
            )

    assert changed_manifest.value.code == 'REPORT_EVIDENCE_LOCATOR_CONFLICT'
    assert unsafe_manifest.value.code == 'REPORT_EVIDENCE_LOCATOR_INVALID'
    assert cross_project.value.code == 'PROJECT_EVIDENCE_CROSS_PROJECT_FORBIDDEN'
    assert reversed_range.value.code == 'REPORT_EVIDENCE_RANGE_INVALID'
