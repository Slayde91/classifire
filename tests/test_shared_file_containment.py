from __future__ import annotations

import hashlib
import os
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from classifire import physical_models  # noqa: F401
from classifire.db import Base
from classifire.models import Project, StoredFile
from classifire.services.project_evidence import (
    bind_project_evidence,
    read_project_evidence_for_update,
)
from classifire.services.storage import (
    StoredFileBindingError,
    quarantine_stored_file_bytes_for_update,
)

_POSTGRES_TEST_URL = os.environ.get('CLASSIFIRE_POSTGRES_TEST_URL')


def _postgres_test_url() -> str:
    if not _POSTGRES_TEST_URL:
        pytest.skip('CLASSIFIRE_POSTGRES_TEST_URL is required for the PostgreSQL race test')
    parsed = make_url(_POSTGRES_TEST_URL)
    if parsed.get_backend_name() != 'postgresql':
        pytest.fail('The shared-file containment race test requires PostgreSQL')
    if parsed.database != 'classifire_containment_test':
        pytest.fail('The shared-file containment race test requires its dedicated test database')
    return _POSTGRES_TEST_URL


@pytest.fixture
def postgresql_session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(_postgres_test_url(), pool_size=4, max_overflow=0, pool_pre_ping=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _add_clean_stored_file(
    factory: sessionmaker[Session],
    storage_root: Path,
) -> tuple[str, str, bytes]:
    payload = b'known retained report content\n'
    storage_root.mkdir()
    path = storage_root / 'report.pdf'
    path.write_bytes(payload)
    with factory() as db:
        with db.begin():
            project = Project(
                reference='POSTGRES-CONTAINMENT-PROJECT',
                name='PostgreSQL containment project',
            )
            db.add(project)
            db.flush()
            stored = StoredFile(
                original_filename='report.pdf',
                media_type='application/pdf',
                storage_path=str(path),
                sha256=hashlib.sha256(payload).hexdigest(),
                size_bytes=len(payload),
                purpose='project_evidence',
                malware_scan_status='clean',
                immutable=True,
            )
            db.add(stored)
            db.flush()
            stored_file_id = stored.id
            bind_project_evidence(db, stored_file_id=stored.id, project_id=project.id)
            project_id = project.id
    return project_id, stored_file_id, payload


def _wait_until_reader_blocks(db: Session, reader_pid: int) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        wait_event = db.scalar(
            text('SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid'),
            {'pid': reader_pid},
        )
        if wait_event == 'Lock':
            return
        time.sleep(0.02)
    pytest.fail('The concurrent retained-file read did not block on the quarantine lock')


def test_postgresql_quarantine_blocks_and_then_denies_concurrent_clean_read(
    postgresql_session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / 'storage'
    project_id, stored_file_id, payload = _add_clean_stored_file(
        postgresql_session_factory,
        storage_root,
    )
    reader_ready = threading.Event()
    reader_finished = threading.Event()
    reader_result: dict[str, object] = {}

    def read_in_second_session() -> None:
        try:
            with postgresql_session_factory() as db:
                with db.begin():
                    db.execute(text('SET LOCAL lock_timeout = 5000'))
                    reader_result['pid'] = int(db.scalar(text('SELECT pg_backend_pid()')))
                    reader_ready.set()
                    reader_result['content'] = read_project_evidence_for_update(
                        db,
                        stored_file_id=stored_file_id,
                        project_id=project_id,
                        storage_root=storage_root,
                    ).content
        except StoredFileBindingError as exc:
            reader_result['code'] = exc.code
        finally:
            reader_finished.set()

    reader = threading.Thread(target=read_in_second_session, daemon=True)
    with postgresql_session_factory() as quarantining_db:
        with quarantining_db.begin():
            quarantine = quarantine_stored_file_bytes_for_update(
                quarantining_db,
                stored_file_id=stored_file_id,
                observed_sha256=hashlib.sha256(payload).hexdigest(),
                observed_size_bytes=len(payload),
            )
            assert quarantine.quarantined_file_ids == (stored_file_id,)
            assert quarantine.binding_mismatch_file_ids == ()
            reader.start()
            assert reader_ready.wait(5)
            _wait_until_reader_blocks(quarantining_db, int(reader_result['pid']))
            assert not reader_finished.is_set()

    reader.join(5)
    assert reader_finished.is_set()
    assert reader_result == {
        'pid': reader_result['pid'],
        'code': 'STORED_FILE_SHARED_SCAN_STATUS_FORBIDDEN',
    }
    with postgresql_session_factory() as db:
        stored = db.get(StoredFile, stored_file_id)
        assert stored is not None
        assert stored.malware_scan_status == 'malware_detected'
