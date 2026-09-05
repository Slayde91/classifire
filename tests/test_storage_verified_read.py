from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import UploadFile
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.datastructures import Headers

from classifire import models, physical_models  # noqa: F401
from classifire.config import Settings
from classifire.db import Base
from classifire.models import StoredFile
from classifire.services.storage import (
    StoredFileBindingError,
    quarantine_stored_file_bytes_for_update,
    read_clean_stored_file_for_update,
    read_hashed_storage_artifact,
    read_verified_stored_file,
    save_upload,
)


def _stored_file(
    storage_root: Path,
    *,
    content: bytes = b'verified retained report bytes\n',
    purpose: str = 'project_evidence',
    scan_status: str = 'clean',
) -> tuple[StoredFile, Path]:
    storage_root.mkdir()
    path = storage_root / 'report.pdf'
    path.write_bytes(content)
    stored = StoredFile(
        original_filename='report.pdf',
        media_type='application/pdf',
        storage_path=str(path),
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        purpose=purpose,
        malware_scan_status=scan_status,
        immutable=True,
    )
    return stored, path


def test_verified_read_returns_the_exact_hash_bound_bytes(tmp_path: Path) -> None:
    storage_root = tmp_path / 'storage'
    payload = b'verified retained report bytes\n'
    stored, _path = _stored_file(storage_root, content=payload)

    result = read_verified_stored_file(
        stored,
        storage_root=storage_root,
        required_purpose='project_evidence',
    )

    assert result.content == payload
    assert result.size_bytes == len(payload)
    assert result.sha256 == hashlib.sha256(payload).hexdigest()
    assert result.media_type == 'application/pdf'


@pytest.mark.parametrize(
    ('purpose', 'scan_status', 'code'),
    [
        ('technical_evidence', 'clean', 'STORED_FILE_PURPOSE_MISMATCH'),
        ('project_evidence', 'pending', 'STORED_FILE_SCAN_STATUS_FORBIDDEN'),
    ],
)
def test_verified_read_rejects_file_state_outside_the_adapter_contract(
    tmp_path: Path,
    purpose: str,
    scan_status: str,
    code: str,
) -> None:
    storage_root = tmp_path / 'storage'
    stored, _path = _stored_file(
        storage_root,
        purpose=purpose,
        scan_status=scan_status,
    )

    with pytest.raises(StoredFileBindingError) as raised:
        read_verified_stored_file(
            stored,
            storage_root=storage_root,
            required_purpose='project_evidence',
        )

    assert raised.value.code == code


def test_verified_read_rejects_changed_size_before_it_returns_bytes(tmp_path: Path) -> None:
    storage_root = tmp_path / 'storage'
    stored, path = _stored_file(storage_root)
    path.write_bytes(b'changed retained report bytes')

    with pytest.raises(StoredFileBindingError) as raised:
        read_verified_stored_file(
            stored,
            storage_root=storage_root,
            required_purpose='project_evidence',
        )

    assert raised.value.code == 'STORED_FILE_SIZE_MISMATCH'


def test_verified_read_rejects_same_size_hash_tampering(tmp_path: Path) -> None:
    storage_root = tmp_path / 'storage'
    stored, path = _stored_file(storage_root)
    path.write_bytes(b'x' * stored.size_bytes)

    with pytest.raises(StoredFileBindingError) as raised:
        read_verified_stored_file(
            stored,
            storage_root=storage_root,
            required_purpose='project_evidence',
        )

    assert raised.value.code == 'STORED_FILE_HASH_MISMATCH'


def test_verified_read_rejects_path_outside_the_configured_storage_root(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / 'storage'
    stored, _path = _stored_file(storage_root)
    outside = tmp_path / 'outside.pdf'
    outside.write_bytes(b'outside storage root')
    stored.storage_path = str(outside)

    with pytest.raises(StoredFileBindingError) as raised:
        read_verified_stored_file(
            stored,
            storage_root=storage_root,
            required_purpose='project_evidence',
        )

    assert raised.value.code == 'STORED_FILE_PATH_OUTSIDE_ROOT'


def test_verified_read_rejects_symbolic_linked_retained_file(tmp_path: Path) -> None:
    storage_root = tmp_path / 'storage'
    stored, path = _stored_file(storage_root)
    target = storage_root / 'target.pdf'
    target.write_bytes(b'separate retained report bytes')
    path.unlink()
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip('symbolic links are unavailable in this environment')

    with pytest.raises(StoredFileBindingError) as raised:
        read_verified_stored_file(
            stored,
            storage_root=storage_root,
            required_purpose='project_evidence',
        )

    assert raised.value.code == 'STORED_FILE_PATH_UNSAFE'


def test_hashed_storage_artifact_returns_exact_safe_bytes(tmp_path: Path) -> None:
    storage_root = tmp_path / 'storage'
    storage_root.mkdir()
    path = storage_root / 'desk-quote.pdf'
    payload = b'generated desk quote bytes\n'
    path.write_bytes(payload)

    result = read_hashed_storage_artifact(storage_root=storage_root, path=path)

    assert result.content == payload
    assert result.size_bytes == len(payload)
    assert result.sha256 == hashlib.sha256(payload).hexdigest()
    assert result.media_type is None


def test_hashed_storage_artifact_rejects_paths_outside_storage_root(tmp_path: Path) -> None:
    storage_root = tmp_path / 'storage'
    storage_root.mkdir()
    outside = tmp_path / 'outside.pdf'
    outside.write_bytes(b'outside storage root')

    with pytest.raises(StoredFileBindingError) as raised:
        read_hashed_storage_artifact(storage_root=storage_root, path=outside)

    assert raised.value.code == 'STORED_FILE_PATH_OUTSIDE_ROOT'


def test_serialized_clean_read_requires_an_open_transaction() -> None:
    engine = create_engine('sqlite+pysqlite:///:memory:')
    with Session(engine) as db:
        with pytest.raises(StoredFileBindingError) as raised:
            read_clean_stored_file_for_update(
                db,
                stored_file_id='stored-file-id',
                storage_root=Path('storage'),
                required_purpose='project_evidence',
            )

    assert raised.value.code == 'STORED_FILE_CONTAINMENT_TRANSACTION_REQUIRED'


def test_serialized_containment_rejects_a_non_postgresql_transaction() -> None:
    engine = create_engine('sqlite+pysqlite:///:memory:')
    with Session(engine) as db:
        with db.begin():
            with pytest.raises(StoredFileBindingError) as raised:
                quarantine_stored_file_bytes_for_update(
                    db,
                    stored_file_id='stored-file-id',
                    observed_sha256='a' * 64,
                    observed_size_bytes=1,
                )

    assert raised.value.code == 'STORED_FILE_CONTAINMENT_SERIALIZATION_UNAVAILABLE'


def _upload(filename: str, content: bytes) -> UploadFile:
    return UploadFile(
        file=BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": "application/pdf"}),
    )


def test_upload_refuses_identical_bytes_for_a_different_evidence_purpose(
    tmp_path: Path,
) -> None:
    engine = create_engine(
        'sqlite+pysqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    settings = Settings(storage_root=tmp_path / 'storage')
    payload = b'identical retained source bytes\n'
    try:
        with Session(engine) as db:
            project_source = save_upload(
                db,
                settings,
                _upload('report.pdf', payload),
                purpose='project_evidence',
                user=None,
            )
            db.commit()

            with pytest.raises(ValueError, match='different evidence purpose'):
                save_upload(
                    db,
                    settings,
                    _upload('technical.pdf', payload),
                    purpose='technical_evidence',
                    user=None,
                )

            retained = list(db.scalars(select(StoredFile)))
            assert retained == [project_source]
            assert project_source.purpose == 'project_evidence'
            assert list((settings.storage_root / '.incoming').iterdir()) == []
    finally:
        engine.dispose()


def test_upload_reuses_identical_bytes_for_the_same_evidence_purpose(
    tmp_path: Path,
) -> None:
    engine = create_engine(
        'sqlite+pysqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    settings = Settings(storage_root=tmp_path / 'storage')
    payload = b'identical retained technical source bytes\n'
    try:
        with Session(engine) as db:
            first = save_upload(
                db,
                settings,
                _upload('technical.pdf', payload),
                purpose='technical_evidence',
                user=None,
            )
            db.commit()

            second = save_upload(
                db,
                settings,
                _upload('technical-copy.pdf', payload),
                purpose='technical_evidence',
                user=None,
            )

            assert second.id == first.id
            assert list(db.scalars(select(StoredFile))) == [first]
            assert list((settings.storage_root / '.incoming').iterdir()) == []
    finally:
        engine.dispose()


@pytest.mark.parametrize("failure", ["empty", "oversize", "corrupt_existing"])
def test_upload_failures_clean_temporary_files_and_never_overwrite(tmp_path, failure):
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    settings = Settings(storage_root=tmp_path / "storage", max_upload_mb=1, _env_file=None)
    payload = b"" if failure == "empty" else b"x" * (1048577 if failure == "oversize" else 10)
    final = None
    if failure == "corrupt_existing":
        digest = hashlib.sha256(payload).hexdigest()
        final = settings.storage_root / digest[:2] / digest[2:4] / (digest + ".pdf")
        final.parent.mkdir(parents=True)
        final.write_bytes(b"retained recovery bytes")
    with Session(engine) as db:
        with pytest.raises(ValueError):
            save_upload(
                db, settings, _upload("same.pdf", payload), purpose="project_evidence", user=None
            )
        assert list(db.scalars(select(StoredFile))) == []
    assert list((settings.storage_root / ".incoming").iterdir()) == []
    if final:
        assert final.read_bytes() == b"retained recovery bytes"
    engine.dispose()


def test_upload_refuses_linked_parent_before_creating_child(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Platform does not permit directory symlinks")
    settings = Settings(storage_root=link / "must-not-create", _env_file=None)
    with Session(create_engine("sqlite+pysqlite://")) as db:
        with pytest.raises(StoredFileBindingError):
            save_upload(
                db,
                settings,
                _upload("same.pdf", b"synthetic"),
                purpose="project_evidence",
                user=None,
            )
    assert list(outside.iterdir()) == []


def test_concurrent_identical_filenames_keep_distinct_complete_bytes(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    engine = create_engine("sqlite:///" + (tmp_path / "uploads.sqlite").as_posix())
    Base.metadata.create_all(engine)
    settings = Settings(storage_root=tmp_path / "storage", _env_file=None)
    start = Barrier(2)

    class Stream(BytesIO):
        def __init__(self, content):
            super().__init__(content)
            self.first = True

        def read(self, size=-1):
            if self.first:
                self.first = False
                start.wait(timeout=10)
            return super().read(size)

    def upload(content):
        with Session(engine) as db:
            source = UploadFile(filename="same.pdf", file=Stream(content))
            row = save_upload(db, settings, source, purpose="project_evidence", user=None)
            db.commit()
            return Path(row.storage_path).read_bytes()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(upload, [b"first synthetic", b"second synthetic"])) == [
            b"first synthetic",
            b"second synthetic",
        ]
    assert list((settings.storage_root / ".incoming").iterdir()) == []
    engine.dispose()
