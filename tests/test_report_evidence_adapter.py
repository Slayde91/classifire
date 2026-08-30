from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace

import pymupdf
import pytest
from PIL import Image
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

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
)
from classifire.physical_models import Defect
from classifire.services.project_evidence import bind_project_evidence
from classifire.services.report_evidence_adapter import (
    ReportEvidenceAdapterError,
    _register_report_evidence_locators,
    _table_shape,
    bind_report_defect_scope,
    normalise_verified_pdf_report,
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
        scope = bind_report_defect_scope(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
            defect_id=defect.id,
            report_defect_label='D-001',
            start_locator_key=page_locators[0].locator_key,
            end_locator_key=page_locators[-1].locator_key,
        )
        repeated_scope = bind_report_defect_scope(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
            defect_id=defect.id,
            report_defect_label='D-001',
            start_locator_key=page_locators[0].locator_key,
            end_locator_key=page_locators[-1].locator_key,
        )

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
            bind_report_defect_scope(
                db,
                stored_file_id=stored.id,
                project_id=other_project.id,
                estimate_id=other_estimate.id,
                defect_id=defect.id,
                report_defect_label='D-001',
                start_locator_key=page_locators[0].locator_key,
                end_locator_key=page_locators[-1].locator_key,
            )
        with pytest.raises(ReportEvidenceAdapterError) as reversed_range:
            bind_report_defect_scope(
                db,
                stored_file_id=stored.id,
                project_id=project.id,
                estimate_id=estimate.id,
                defect_id=defect.id,
                report_defect_label='D-001',
                start_locator_key=page_locators[-1].locator_key,
                end_locator_key=page_locators[0].locator_key,
            )

    assert changed_manifest.value.code == 'REPORT_EVIDENCE_LOCATOR_CONFLICT'
    assert unsafe_manifest.value.code == 'REPORT_EVIDENCE_LOCATOR_INVALID'
    assert cross_project.value.code == 'PROJECT_EVIDENCE_CROSS_PROJECT_FORBIDDEN'
    assert reversed_range.value.code == 'REPORT_EVIDENCE_RANGE_INVALID'
