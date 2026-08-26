from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import UploadFile
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.datastructures import Headers

from classifire import models, physical_models  # noqa: F401 - register full metadata.
from classifire.config import Settings
from classifire.db import Base
from classifire.models import AuditEvent, StoredFile
from classifire.services.malware_scanning import MalwareDetectedError, MalwareScanError
from classifire.services.storage import (
    RetainedMalwareQuarantinedError,
    StoredFileSecurityError,
    require_clean_stored_file,
    save_upload,
)


class _CleanScanner:
    def __init__(self) -> None:
        self.payloads: list[bytes] = []

    def check_ready(self) -> None:
        return None

    def scan_stream(self, stream) -> None:  # type: ignore[no-untyped-def]
        self.payloads.append(stream.read())


class _InfectedScanner(_CleanScanner):
    def scan_stream(self, stream) -> None:  # type: ignore[no-untyped-def]
        self.payloads.append(stream.read())
        raise MalwareDetectedError


class _UnavailableScanner(_CleanScanner):
    def scan_stream(self, stream) -> None:  # type: ignore[no-untyped-def]
        self.payloads.append(stream.read())
        raise MalwareScanError("MALWARE_SCANNER_UNAVAILABLE")


def _database() -> tuple[Engine, Session]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def _settings(tmp_path: Path, **updates: object) -> Settings:
    values: dict[str, object] = {
        "env": "test",
        "storage_root": tmp_path / "storage",
    }
    values.update(updates)
    return Settings(_env_file=None, **values)


def _upload(payload: bytes, *, filename: str = "report.pdf") -> UploadFile:
    return UploadFile(
        filename=filename,
        file=BytesIO(payload),
        headers=Headers({"content-type": "application/pdf"}),
    )


def _incoming_files(settings: Settings) -> tuple[Path, ...]:
    incoming = settings.storage_root / ".incoming"
    return tuple(incoming.iterdir()) if incoming.exists() else ()


def test_clean_upload_is_scanned_before_immutable_promotion(tmp_path: Path) -> None:
    engine, db = _database()
    settings = _settings(tmp_path)
    payload = b"%PDF-1.7\ncontrolled clean fixture\n"
    scanner = _CleanScanner()
    try:
        stored = save_upload(
            db,
            settings,
            _upload(payload),
            purpose="technical_evidence",
            user=None,
            malware_scanner=scanner,
        )

        assert scanner.payloads == [payload]
        assert stored.malware_scan_status == "clean"
        assert stored.sha256 == hashlib.sha256(payload).hexdigest()
        assert stored.size_bytes == len(payload)
        retained = require_clean_stored_file(
            settings.storage_root,
            stored,
            allowed_purposes={"technical_evidence"},
        )
        assert retained.read_bytes() == payload
        assert _incoming_files(settings) == ()
    finally:
        db.close()
        engine.dispose()


@pytest.mark.parametrize(
    ("scanner", "expected_code"),
    [
        (_InfectedScanner(), "MALWARE_DETECTED"),
        (_UnavailableScanner(), "MALWARE_SCANNER_UNAVAILABLE"),
    ],
)
def test_refused_scan_never_promotes_bytes_and_detected_sha_is_tombstoned(
    tmp_path: Path,
    scanner: _CleanScanner,
    expected_code: str,
) -> None:
    engine, db = _database()
    settings = _settings(tmp_path)
    try:
        with pytest.raises(MalwareScanError) as rejected:
            save_upload(
                db,
                settings,
                _upload(b"%PDF hostile or unverified"),
                purpose="technical_evidence",
                user=None,
                malware_scanner=scanner,
            )

        assert rejected.value.code == expected_code
        stored_rows = list(db.scalars(select(StoredFile)).all())
        if expected_code == "MALWARE_DETECTED":
            assert len(stored_rows) == 1
            assert stored_rows[0].malware_scan_status == "infected"
            assert not Path(stored_rows[0].storage_path).exists()
        else:
            assert stored_rows == []
        assert _incoming_files(settings) == ()
        assert tuple(path for path in settings.storage_root.rglob("*") if path.is_file()) == ()
    finally:
        db.close()
        engine.dispose()


def test_missing_scanner_rejects_before_bytes_are_written(tmp_path: Path) -> None:
    engine, db = _database()
    settings = _settings(tmp_path)
    try:
        with pytest.raises(MalwareScanError) as rejected:
            save_upload(
                db,
                settings,
                _upload(b"%PDF not scanned"),
                purpose="technical_evidence",
                user=None,
            )

        assert rejected.value.code == "MALWARE_SCANNER_UNAVAILABLE"
        assert not settings.storage_root.exists()
        assert db.scalar(select(func.count()).select_from(StoredFile)) == 0
    finally:
        db.close()
        engine.dispose()


def test_current_upload_is_rescanned_before_clean_deduplication(tmp_path: Path) -> None:
    engine, db = _database()
    settings = _settings(tmp_path)
    payload = b"%PDF repeated evidence"
    first_scanner = _CleanScanner()
    second_scanner = _CleanScanner()
    try:
        first = save_upload(
            db,
            settings,
            _upload(payload),
            purpose="technical_evidence",
            user=None,
            malware_scanner=first_scanner,
        )
        second = save_upload(
            db,
            settings,
            _upload(payload),
            purpose="technical_evidence",
            user=None,
            malware_scanner=second_scanner,
        )

        assert second.id == first.id
        assert first_scanner.payloads == [payload]
        assert second_scanner.payloads == [payload]
        assert db.scalar(select(func.count()).select_from(StoredFile)) == 1
        assert _incoming_files(settings) == ()
    finally:
        db.close()
        engine.dispose()


def test_new_detected_verdict_quarantines_existing_exact_sha_with_audit(
    tmp_path: Path,
) -> None:
    engine, db = _database()
    settings = _settings(tmp_path)
    payload = b"%PDF previously clean bytes now detected by newer definitions"
    try:
        stored = save_upload(
            db,
            settings,
            _upload(payload),
            purpose="technical_evidence",
            user=None,
            malware_scanner=_CleanScanner(),
        )
        db.commit()

        with pytest.raises(RetainedMalwareQuarantinedError):
            save_upload(
                db,
                settings,
                _upload(payload),
                purpose="technical_evidence",
                user=None,
                malware_scanner=_InfectedScanner(),
            )
        db.commit()
        db.refresh(stored)

        assert stored.malware_scan_status == "infected"
        event = db.scalar(
            select(AuditEvent).where(
                AuditEvent.action
                == "quarantine_stored_file_after_malware_detection"
            )
        )
        assert event is not None
        assert event.entity_id == stored.id
        with pytest.raises(StoredFileSecurityError):
            require_clean_stored_file(
                settings.storage_root,
                stored,
                allowed_purposes={"technical_evidence"},
            )
    finally:
        db.close()
        engine.dispose()


def test_detected_sha_tombstone_blocks_a_later_clean_verdict(tmp_path: Path) -> None:
    engine, db = _database()
    settings = _settings(tmp_path)
    payload = b"%PDF exact bytes rejected before any clean row existed"
    try:
        with pytest.raises(RetainedMalwareQuarantinedError):
            save_upload(
                db,
                settings,
                _upload(payload),
                purpose="technical_evidence",
                user=None,
                malware_scanner=_InfectedScanner(),
            )
        db.commit()

        with pytest.raises(StoredFileSecurityError) as rejected:
            save_upload(
                db,
                settings,
                _upload(payload),
                purpose="technical_evidence",
                user=None,
                malware_scanner=_CleanScanner(),
            )

        assert rejected.value.code == "STORED_FILE_NOT_PROCESSABLE"
        tombstone = db.scalar(select(StoredFile))
        assert tombstone is not None
        assert tombstone.malware_scan_status == "infected"
        assert not Path(tombstone.storage_path).exists()
        assert _incoming_files(settings) == ()
    finally:
        db.close()
        engine.dispose()


def test_detected_sha_recovers_from_a_concurrent_unique_insert(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, db = _database()
    settings = _settings(tmp_path)
    payload = b"%PDF concurrent clean row"
    digest = hashlib.sha256(payload).hexdigest()
    retained = settings.storage_root / digest[:2] / digest[2:4] / f"{digest}.pdf"
    retained.parent.mkdir(parents=True)
    retained.write_bytes(payload)
    existing = StoredFile(
        original_filename="report.pdf",
        media_type="application/pdf",
        storage_path=str(retained),
        sha256=digest,
        size_bytes=len(payload),
        purpose="technical_evidence",
        malware_scan_status="clean",
        immutable=True,
    )
    db.add(existing)
    db.commit()
    real_scalar = db.scalar
    lookup_count = 0

    def stale_first_lookup(statement, *args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal lookup_count
        lookup_count += 1
        if lookup_count == 1:
            return None
        return real_scalar(statement, *args, **kwargs)

    monkeypatch.setattr(db, "scalar", stale_first_lookup)
    try:
        with pytest.raises(RetainedMalwareQuarantinedError):
            save_upload(
                db,
                settings,
                _upload(payload),
                purpose="technical_evidence",
                user=None,
                malware_scanner=_InfectedScanner(),
            )
        db.commit()
        db.refresh(existing)

        assert lookup_count == 2
        assert existing.malware_scan_status == "infected"
        assert db.scalar(select(func.count()).select_from(StoredFile)) == 1
    finally:
        db.close()
        engine.dispose()


def test_clean_sha_recovers_from_a_concurrent_compatible_insert(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, db = _database()
    settings = _settings(tmp_path)
    payload = b"%PDF concurrent compatible clean row"
    digest = hashlib.sha256(payload).hexdigest()
    retained = settings.storage_root / digest[:2] / digest[2:4] / f"{digest}.pdf"
    retained.parent.mkdir(parents=True)
    retained.write_bytes(payload)
    winner = StoredFile(
        original_filename="report.pdf",
        media_type="application/pdf",
        storage_path=str(retained),
        sha256=digest,
        size_bytes=len(payload),
        purpose="technical_evidence",
        malware_scan_status="clean",
        immutable=True,
    )
    db.add(winner)
    db.commit()
    real_scalar = db.scalar
    lookup_count = 0

    def stale_first_lookup(statement, *args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal lookup_count
        lookup_count += 1
        assert statement._for_update_arg is not None
        assert statement.get_execution_options().get("populate_existing") is True
        if lookup_count == 1:
            return None
        return real_scalar(statement, *args, **kwargs)

    monkeypatch.setattr(db, "scalar", stale_first_lookup)
    try:
        stored = save_upload(
            db,
            settings,
            _upload(payload),
            purpose="technical_evidence",
            user=None,
            malware_scanner=_CleanScanner(),
        )
        db.commit()

        assert lookup_count == 2
        assert stored.id == winner.id
        assert real_scalar(select(func.count()).select_from(StoredFile)) == 1
    finally:
        db.close()
        engine.dispose()


def test_clean_sha_conflict_cannot_rehabilitate_infected_winner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, db = _database()
    settings = _settings(tmp_path)
    payload = b"%PDF concurrent infected winner"
    digest = hashlib.sha256(payload).hexdigest()
    tombstone = StoredFile(
        original_filename="report.pdf",
        media_type="application/pdf",
        storage_path=str(settings.storage_root / ".rejected" / f"{digest}.malware-blocked"),
        sha256=digest,
        size_bytes=len(payload),
        purpose="technical_evidence",
        malware_scan_status="infected",
        immutable=True,
    )
    db.add(tombstone)
    db.commit()
    real_scalar = db.scalar
    lookup_count = 0

    def stale_first_lookup(statement, *args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal lookup_count
        lookup_count += 1
        if lookup_count == 1:
            return None
        return real_scalar(statement, *args, **kwargs)

    monkeypatch.setattr(db, "scalar", stale_first_lookup)
    try:
        final_path = settings.storage_root / digest[:2] / digest[2:4] / f"{digest}.pdf"
        with pytest.raises(StoredFileSecurityError) as rejected:
            save_upload(
                db,
                settings,
                _upload(payload),
                purpose="technical_evidence",
                user=None,
                malware_scanner=_CleanScanner(),
            )

        assert rejected.value.code == "STORED_FILE_NOT_PROCESSABLE"
        assert lookup_count == 2
        assert db.scalar(select(func.count()).select_from(StoredFile)) == 1
        db.refresh(tombstone)
        assert tombstone.malware_scan_status == "infected"
        assert not final_path.exists()
        assert _incoming_files(settings) == ()
    finally:
        db.close()
        engine.dispose()


@pytest.mark.parametrize("status", ["pending", "not_configured", "infected", "failed", ""])
def test_deduplication_cannot_reuse_nonclean_legacy_row(
    tmp_path: Path,
    status: str,
) -> None:
    engine, db = _database()
    settings = _settings(tmp_path)
    settings.storage_root.mkdir(parents=True)
    payload = b"%PDF legacy unclean evidence"
    digest = hashlib.sha256(payload).hexdigest()
    retained = settings.storage_root / f"{digest}.pdf"
    retained.write_bytes(payload)
    db.add(
        StoredFile(
            original_filename="legacy.pdf",
            media_type="application/pdf",
            storage_path=str(retained),
            sha256=digest,
            size_bytes=len(payload),
            purpose="technical_evidence",
            malware_scan_status=status,
            immutable=True,
        )
    )
    db.commit()
    try:
        with pytest.raises(StoredFileSecurityError) as rejected:
            save_upload(
                db,
                settings,
                _upload(payload),
                purpose="technical_evidence",
                user=None,
                malware_scanner=_CleanScanner(),
            )

        assert rejected.value.code == "STORED_FILE_NOT_PROCESSABLE"
        assert db.scalar(select(func.count()).select_from(StoredFile)) == 1
        assert _incoming_files(settings) == ()
    finally:
        db.close()
        engine.dispose()


def test_clean_deduplication_rejects_context_or_retained_byte_mismatch(tmp_path: Path) -> None:
    engine, db = _database()
    settings = _settings(tmp_path)
    payload = b"%PDF immutable evidence"
    try:
        stored = save_upload(
            db,
            settings,
            _upload(payload),
            purpose="technical_evidence",
            user=None,
            malware_scanner=_CleanScanner(),
        )
        Path(stored.storage_path).write_bytes(b"tampered")

        with pytest.raises(StoredFileSecurityError) as rejected:
            save_upload(
                db,
                settings,
                _upload(payload),
                purpose="technical_evidence",
                user=None,
                malware_scanner=_CleanScanner(),
            )

        assert rejected.value.code == "STORED_FILE_INTEGRITY_INVALID"
        assert _incoming_files(settings) == ()
    finally:
        db.close()
        engine.dispose()


def test_flush_failure_never_deletes_shared_content_addressed_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, db = _database()
    settings = _settings(tmp_path)
    payload = b"%PDF clean bytes that a concurrent winner may reference"
    digest = hashlib.sha256(payload).hexdigest()
    final_path = settings.storage_root / digest[:2] / digest[2:4] / f"{digest}.pdf"
    final_path.parent.mkdir(parents=True)
    final_path.write_bytes(payload)
    original_flush = db.flush

    def fail_flush(*args: object, **kwargs: object) -> None:
        if any(isinstance(item, StoredFile) for item in db.new):
            raise RuntimeError("synthetic persistence failure")
        original_flush(*args, **kwargs)

    monkeypatch.setattr(db, "flush", fail_flush)
    try:
        with pytest.raises(RuntimeError, match="synthetic persistence failure"):
            save_upload(
                db,
                settings,
                _upload(payload),
                purpose="technical_evidence",
                user=None,
                malware_scanner=_CleanScanner(),
            )

        assert final_path.read_bytes() == payload
        assert _incoming_files(settings) == ()
        monkeypatch.setattr(db, "flush", original_flush)
        db.rollback()
        assert db.scalar(select(func.count()).select_from(StoredFile)) == 0
    finally:
        db.close()
        engine.dispose()


def test_flush_failure_does_not_promote_quarantined_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, db = _database()
    settings = _settings(tmp_path)
    payload = b"%PDF clean quarantine that must not be promoted"
    digest = hashlib.sha256(payload).hexdigest()
    final_path = settings.storage_root / digest[:2] / digest[2:4] / f"{digest}.pdf"
    original_flush = db.flush

    def fail_flush(*args: object, **kwargs: object) -> None:
        if any(isinstance(item, StoredFile) for item in db.new):
            raise RuntimeError("synthetic persistence failure")
        original_flush(*args, **kwargs)

    monkeypatch.setattr(db, "flush", fail_flush)
    try:
        with pytest.raises(RuntimeError, match="synthetic persistence failure"):
            save_upload(
                db,
                settings,
                _upload(payload),
                purpose="technical_evidence",
                user=None,
                malware_scanner=_CleanScanner(),
            )

        assert not final_path.exists()
        assert _incoming_files(settings) == ()
        monkeypatch.setattr(db, "flush", original_flush)
        db.rollback()
        assert db.scalar(select(func.count()).select_from(StoredFile)) == 0
    finally:
        db.close()
        engine.dispose()
