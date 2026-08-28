from __future__ import annotations

import hashlib
import os
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pytest
from fastapi import UploadFile
from physical_foundation_support import physical_session
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.datastructures import Headers

from classifire import physical_models as _physical_models  # noqa: F401
from classifire.config import Settings
from classifire.db import Base
from classifire.models import StoredFile
from classifire.services import storage as storage_service
from classifire.services.malware_scanning import CLEAN_VERDICT, MalwareScanResult
from classifire.services.storage import (
    StoredFileBindingError,
    StoredFileSecurityError,
    cleanup_uncommitted_upload,
    save_verified_upload,
)


class _ExactScanner:
    def __init__(self) -> None:
        self.calls: list[bytes] = []

    def scan_stream(self, stream: BinaryIO) -> MalwareScanResult:
        payload = stream.read()
        self.calls.append(payload)
        return MalwareScanResult(
            CLEAN_VERDICT,
            hashlib.sha256(payload).hexdigest(),
            len(payload),
        )


class _WrongBindingScanner:
    def scan_stream(self, stream: BinaryIO) -> MalwareScanResult:
        payload = stream.read()
        return MalwareScanResult(CLEAN_VERDICT, "0" * 64, len(payload))


class _MutatingScanner:
    def scan_stream(self, stream: BinaryIO) -> MalwareScanResult:
        payload = stream.read()
        result = MalwareScanResult(
            CLEAN_VERDICT,
            hashlib.sha256(payload).hexdigest(),
            len(payload),
        )
        stream.seek(0)
        stream.write(b"X")
        stream.flush()
        return result


class _InterruptingScanner:
    def scan_stream(self, stream: BinaryIO) -> MalwareScanResult:
        stream.read(1)
        raise KeyboardInterrupt


def _settings(tmp_path: Path, *, maximum_mb: int = 1) -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        storage_root=tmp_path / "storage",
        max_upload_mb=maximum_mb,
        clamav_host="scanner.internal",
    )


def _upload(
    payload: bytes,
    *,
    filename: str = "report.pdf",
    content_type: str = "application/pdf",
) -> UploadFile:
    return UploadFile(
        BytesIO(payload),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def _pdf(label: str) -> bytes:
    return b"%PDF-1.7\n" + label.encode("ascii") + b"\n%%EOF\n"


def _assert_code(code: str, callback) -> None:
    with pytest.raises(ValueError) as caught:
        callback()
    assert getattr(caught.value, "code", None) == code
    assert str(caught.value) == code


def _parts(settings: Settings) -> list[Path]:
    return list(settings.storage_root.rglob("*.part"))


def _file_backed_sessions(tmp_path: Path) -> tuple[Engine, sessionmaker[Session]]:
    database_path = tmp_path / "upload-transactions.sqlite3"
    engine = create_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)


def test_exact_clean_upload_uses_canonical_content_path_and_no_temp_residue(
    tmp_path: Path,
) -> None:
    payload = _pdf("exact-clean")
    settings = _settings(tmp_path)
    scanner = _ExactScanner()

    with physical_session() as db:
        result = save_verified_upload(
            db,
            settings,
            _upload(payload),
            purpose="technical_evidence",
            user=None,
            malware_scanner=scanner,
        )

        digest = hashlib.sha256(payload).hexdigest()
        assert result.created_record is True
        assert result.promoted_file is True
        assert result.binding.path == (
            settings.storage_root.resolve()
            / digest[:2]
            / digest[2:4]
            / f"{digest}.pdf"
        )
        assert result.binding.path.read_bytes() == payload
        assert result.stored_file.malware_scan_status == "clean"
        assert scanner.calls == [payload]
        assert _parts(settings) == []


def test_unsupported_extension_fails_before_scanner_or_staging(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    scanner = _ExactScanner()

    with physical_session() as db:
        _assert_code(
            "UPLOAD_FILE_TYPE_UNSUPPORTED",
            lambda: save_verified_upload(
                db,
                settings,
                _upload(b"payload", filename="report.exe"),
                purpose="technical_evidence",
                user=None,
                malware_scanner=scanner,
            ),
        )

        assert scanner.calls == []
        assert list(db.scalars(select(StoredFile)).all()) == []
        assert _parts(settings) == []


def test_oversize_upload_is_removed_before_scanning(tmp_path: Path) -> None:
    settings = _settings(tmp_path, maximum_mb=0)
    scanner = _ExactScanner()

    with physical_session() as db:
        _assert_code(
            "UPLOAD_SIZE_LIMIT_EXCEEDED",
            lambda: save_verified_upload(
                db,
                settings,
                _upload(_pdf("too-large")),
                purpose="technical_evidence",
                user=None,
                malware_scanner=scanner,
            ),
        )

        assert scanner.calls == []
        assert list(db.scalars(select(StoredFile)).all()) == []
        assert _parts(settings) == []


def test_spoofed_pdf_is_removed_before_scanning(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    scanner = _ExactScanner()

    with physical_session() as db:
        _assert_code(
            "UPLOAD_CONTENT_SIGNATURE_INVALID",
            lambda: save_verified_upload(
                db,
                settings,
                _upload(b"MZ executable bytes"),
                purpose="technical_evidence",
                user=None,
                malware_scanner=scanner,
            ),
        )

        assert scanner.calls == []
        assert list(db.scalars(select(StoredFile)).all()) == []
        assert _parts(settings) == []


def test_scanner_hash_mismatch_never_promotes_or_persists(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    with physical_session() as db:
        _assert_code(
            "MALWARE_SCANNER_RESPONSE_MALFORMED",
            lambda: save_verified_upload(
                db,
                settings,
                _upload(_pdf("wrong-hash")),
                purpose="technical_evidence",
                user=None,
                malware_scanner=_WrongBindingScanner(),
            ),
        )

        assert list(db.scalars(select(StoredFile)).all()) == []
        assert _parts(settings) == []
        assert [path for path in settings.storage_root.rglob("*") if path.is_file()] == []


def test_post_scan_staged_binding_mismatch_is_rejected(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)

    with physical_session() as db:
        _assert_code(
            "UPLOAD_STAGED_BYTES_CHANGED",
            lambda: save_verified_upload(
                db,
                settings,
                _upload(_pdf("mutated-after-scan")),
                purpose="technical_evidence",
                user=None,
                malware_scanner=_MutatingScanner(),
            ),
        )

        assert list(db.scalars(select(StoredFile)).all()) == []
        assert _parts(settings) == []


def test_conflicting_preexisting_content_path_is_never_overwritten(tmp_path: Path) -> None:
    payload = _pdf("content-collision")
    settings = _settings(tmp_path)
    digest = hashlib.sha256(payload).hexdigest()
    final_path = (
        settings.storage_root.resolve()
        / digest[:2]
        / digest[2:4]
        / f"{digest}.pdf"
    )
    final_path.parent.mkdir(parents=True)
    forged = b"X" * len(payload)
    final_path.write_bytes(forged)

    with physical_session() as db:
        _assert_code(
            "STORED_FILE_CONTENT_COLLISION",
            lambda: save_verified_upload(
                db,
                settings,
                _upload(payload),
                purpose="technical_evidence",
                user=None,
                malware_scanner=_ExactScanner(),
            ),
        )
        db.rollback()

        assert final_path.read_bytes() == forged
        assert list(db.scalars(select(StoredFile)).all()) == []
        assert _parts(settings) == []


def test_same_filename_uploads_use_independent_staging_and_content_paths(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    scanner = _ExactScanner()

    with physical_session() as db:
        first = save_verified_upload(
            db,
            settings,
            _upload(_pdf("first"), filename="same.pdf"),
            purpose="technical_evidence",
            user=None,
            malware_scanner=scanner,
        )
        second = save_verified_upload(
            db,
            settings,
            _upload(_pdf("second"), filename="same.pdf"),
            purpose="technical_evidence",
            user=None,
            malware_scanner=scanner,
        )

        assert first.binding.path != second.binding.path
        assert first.binding.path.read_bytes() == _pdf("first")
        assert second.binding.path.read_bytes() == _pdf("second")
        assert _parts(settings) == []


def test_file_backed_sqlite_upload_stays_in_outer_transaction(tmp_path: Path) -> None:
    engine, session_factory = _file_backed_sessions(tmp_path)
    settings = _settings(tmp_path)
    try:
        with session_factory() as writer:
            result = save_verified_upload(
                writer,
                settings,
                _upload(_pdf("outer-transaction")),
                purpose="technical_evidence",
                user=None,
                malware_scanner=_ExactScanner(),
            )
            with session_factory() as observer:
                assert observer.scalar(select(func.count()).select_from(StoredFile)) == 0

            cleanup_error = cleanup_uncommitted_upload(
                result,
                prior_code="STORED_FILE_PERSISTENCE_CONFLICT",
            )
            assert cleanup_error is None
            writer.rollback()

        with session_factory() as observer:
            assert observer.scalar(select(func.count()).select_from(StoredFile)) == 0
        assert result.binding.path.exists() is False
    finally:
        engine.dispose()


def test_matching_orphan_final_bytes_are_safely_adopted(tmp_path: Path) -> None:
    engine, session_factory = _file_backed_sessions(tmp_path)
    settings = _settings(tmp_path)
    payload = _pdf("matching-orphan")
    digest = hashlib.sha256(payload).hexdigest()
    orphan_path = (
        settings.storage_root.resolve()
        / digest[:2]
        / digest[2:4]
        / f"{digest}.pdf"
    )
    orphan_path.parent.mkdir(parents=True)
    orphan_path.write_bytes(payload)
    try:
        with session_factory() as db:
            result = save_verified_upload(
                db,
                settings,
                _upload(payload),
                purpose="technical_evidence",
                user=None,
                malware_scanner=_ExactScanner(),
            )
            assert result.created_record is True
            assert result.promoted_file is False
            assert result.binding.path == orphan_path
            db.commit()

        with session_factory() as observer:
            stored = observer.scalar(select(StoredFile))
            assert stored is not None
            assert stored.sha256 == digest
            assert orphan_path.read_bytes() == payload
        assert _parts(settings) == []
    finally:
        engine.dispose()


def test_simultaneous_retained_and_temp_cleanup_failures_are_combined(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)

    def reject_binding(*_args, **_kwargs):
        raise StoredFileSecurityError("STORED_FILE_CONTEXT_CONFLICT")

    original_unlink = Path.unlink

    def fail_upload_cleanup(path: Path, *args, **kwargs):
        if path.suffix in {".part", ".pdf"}:
            raise PermissionError("simulated cleanup denial")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(storage_service, "require_stored_file_binding", reject_binding)
    monkeypatch.setattr(Path, "unlink", fail_upload_cleanup)

    with physical_session() as db:
        with pytest.raises(StoredFileSecurityError) as caught:
            save_verified_upload(
                db,
                settings,
                _upload(_pdf("dual-cleanup")),
                purpose="technical_evidence",
                user=None,
                malware_scanner=_ExactScanner(),
            )

        assert caught.value.code == "UPLOAD_MULTIPLE_CLEANUP_FAILED"
        assert caught.value.prior_code == "STORED_FILE_CONTEXT_CONFLICT"
        assert set(caught.value.cleanup_codes) == {
            "UPLOAD_RETENTION_CLEANUP_FAILED",
            "UPLOAD_TEMP_CLEANUP_FAILED",
        }
        db.rollback()


@pytest.mark.skipif(os.name != "nt", reason="Windows hardlink behavior")
def test_windows_hardlink_promotion_leaves_one_canonical_link(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with physical_session() as db:
        result = save_verified_upload(
            db,
            settings,
            _upload(_pdf("windows-hardlink")),
            purpose="technical_evidence",
            user=None,
            malware_scanner=_ExactScanner(),
        )

        assert result.promoted_file is True
        assert os.stat(result.binding.path).st_nlink == 1
        assert _parts(settings) == []
        assert cleanup_uncommitted_upload(
            result,
            prior_code="STORED_FILE_PERSISTENCE_CONFLICT",
        ) is None
        db.rollback()


def test_storage_root_binding_failure_has_stable_storage_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ExactScanner()

    def reject_root(_root: Path) -> None:
        raise StoredFileBindingError("STORAGE_ROOT_UNSAFE")

    monkeypatch.setattr(storage_service, "_require_safe_storage_root", reject_root)
    with physical_session() as db:
        _assert_code(
            "STORED_FILE_STORAGE_FAILURE",
            lambda: save_verified_upload(
                db,
                _settings(tmp_path),
                _upload(_pdf("unsafe-root")),
                purpose="technical_evidence",
                user=None,
                malware_scanner=scanner,
            ),
        )

        assert scanner.calls == []
        assert list(db.scalars(select(StoredFile)).all()) == []


def test_staged_binding_failure_has_stable_changed_bytes_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    original = storage_service._require_safe_retained_path

    def reject_staged(root: Path, path: Path):
        if path.suffix == ".part":
            raise StoredFileBindingError("STORED_FILE_PATH_UNSAFE")
        return original(root, path)

    monkeypatch.setattr(storage_service, "_require_safe_retained_path", reject_staged)
    with physical_session() as db:
        _assert_code(
            "UPLOAD_STAGED_BYTES_CHANGED",
            lambda: save_verified_upload(
                db,
                settings,
                _upload(_pdf("unsafe-staged-path")),
                purpose="technical_evidence",
                user=None,
                malware_scanner=_ExactScanner(),
            ),
        )

        assert list(db.scalars(select(StoredFile)).all()) == []
        assert [path for path in settings.storage_root.rglob("*") if path.is_file()] == []


def test_process_control_exception_is_not_replaced_by_temp_cleanup_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    original_unlink = Path.unlink

    def fail_temp_cleanup(path: Path, *args, **kwargs):
        if path.suffix == ".part":
            raise PermissionError("simulated temp cleanup denial")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_temp_cleanup)
    with physical_session() as db:
        with pytest.raises(KeyboardInterrupt):
            save_verified_upload(
                db,
                settings,
                _upload(_pdf("process-control")),
                purpose="technical_evidence",
                user=None,
                malware_scanner=_InterruptingScanner(),
            )

        assert list(db.scalars(select(StoredFile)).all()) == []
        assert len(_parts(settings)) == 1
