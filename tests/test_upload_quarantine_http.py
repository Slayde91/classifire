from __future__ import annotations

import hashlib
import importlib
import re
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.middleware.sessions import SessionMiddleware

from classifire.config import Settings, get_settings
from classifire.db import Base, get_db
from classifire.models import AuditEvent, StoredFile, TechnicalDocument, User
from classifire.security import get_current_user, hash_password
from classifire.services import storage
from classifire.services.malware_scanning import MalwareDetectedError, MalwareScanError

api_module = importlib.import_module("classifire.api.router")
ui_module = importlib.import_module("classifire.ui")


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


def _harness(
    tmp_path: Path,
) -> tuple[FastAPI, sessionmaker[Session], Settings, User]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        user = User(
            email="uploader@example.test",
            full_name="Technical uploader",
            password_hash=hash_password("test-only-password"),
            role="administrator",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    settings = Settings(
        env="test",
        storage_root=tmp_path / "storage",
        _env_file=None,
    )
    app = FastAPI()
    app.add_middleware(
        SessionMiddleware,
        secret_key="upload-quarantine-test-session-secret",  # noqa: S106
    )
    app.include_router(api_module.router)
    app.include_router(ui_module.router)

    def override_db():  # type: ignore[no-untyped-def]
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings] = lambda: settings
    return app, factory, settings, user


def _request(
    client: TestClient,
    payload: bytes,
    *,
    document_id: str = "DOC-UPLOAD-001",
):
    return client.post(
        "/api/v1/technical/documents",
        data={
            "document_id": document_id,
            "document_type": "test_report",
            "title": "Controlled upload",
        },
        files={"file": ("controlled.pdf", BytesIO(payload), "application/pdf")},
    )


def _csrf(response_text: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', response_text)
    assert match is not None
    return match.group(1)


def _login(client: TestClient) -> str:
    login_page = client.get("/login")
    login = client.post(
        "/login",
        data={
            "csrf_token": _csrf(login_page.text),
            "email": "uploader@example.test",
            "password": "test-only-password",
        },
        follow_redirects=False,
    )
    assert login.status_code == 303
    return _csrf(client.get("/technical").text)


@pytest.mark.parametrize(
    ("scanner", "status_code", "expected_code", "expected_stored_rows"),
    [
        (None, 503, "MALWARE_SCANNER_UNAVAILABLE", 0),
        (_UnavailableScanner(), 503, "MALWARE_SCANNER_UNAVAILABLE", 0),
        (_InfectedScanner(), 422, "MALWARE_DETECTED", 1),
    ],
)
def test_rejected_upload_never_reaches_parser_or_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scanner: _CleanScanner | None,
    status_code: int,
    expected_code: str,
    expected_stored_rows: int,
) -> None:
    app, factory, settings, _user = _harness(tmp_path)
    parser_called = False

    def forbidden_parser(_path: Path) -> dict[str, object]:
        nonlocal parser_called
        parser_called = True
        raise AssertionError("unscanned bytes must never reach the PDF parser")

    monkeypatch.setattr(api_module, "extract_pdf_candidate_metadata", forbidden_parser)
    if scanner is not None:
        monkeypatch.setattr(storage, "configured_malware_scanner", lambda _settings: scanner)

    with TestClient(app) as client:
        response = _request(client, b"%PDF rejected fixture")

    assert response.status_code == status_code
    assert response.json() == {"detail": expected_code}
    assert parser_called is False
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(StoredFile)) == expected_stored_rows
        if expected_stored_rows:
            tombstone = db.scalar(select(StoredFile))
            assert tombstone is not None
            assert tombstone.malware_scan_status == "infected"
            assert not Path(tombstone.storage_path).exists()
        assert db.scalar(select(func.count()).select_from(TechnicalDocument)) == 0
    assert tuple(path for path in settings.storage_root.rglob("*") if path.is_file()) == ()


def test_clean_upload_reaches_parser_once_and_creates_draft(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, factory, _settings, _user = _harness(tmp_path)
    scanner = _CleanScanner()
    parsed_paths: list[Path] = []
    payload = b"%PDF controlled clean fixture"

    monkeypatch.setattr(storage, "configured_malware_scanner", lambda _settings: scanner)

    def parser(path: Path) -> dict[str, object]:
        parsed_paths.append(path)
        assert path.read_bytes() == payload
        return {"extraction_status": "completed", "candidate_count": 0}

    monkeypatch.setattr(api_module, "extract_pdf_candidate_metadata", parser)
    with TestClient(app) as client:
        response = _request(client, payload)

    assert response.status_code == 201, response.text
    assert scanner.payloads == [payload]
    assert len(parsed_paths) == 1
    with factory() as db:
        stored = db.scalar(select(StoredFile))
        document = db.scalar(select(TechnicalDocument))
        assert stored is not None
        assert stored.malware_scan_status == "clean"
        assert document is not None
        assert document.stored_file_id == stored.id
        assert document.status == "draft"


def test_api_duplicate_bytes_cannot_reuse_a_legacy_nonclean_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, factory, settings, _user = _harness(tmp_path)
    payload = b"%PDF legacy pending duplicate"
    digest = hashlib.sha256(payload).hexdigest()
    settings.storage_root.mkdir(parents=True)
    retained = settings.storage_root / f"{digest}.pdf"
    retained.write_bytes(payload)
    with factory() as db:
        db.add(
            StoredFile(
                original_filename="legacy.pdf",
                media_type="application/pdf",
                storage_path=str(retained),
                sha256=digest,
                size_bytes=len(payload),
                purpose="technical_evidence",
                malware_scan_status="pending",
                immutable=True,
            )
        )
        db.commit()

    scanner = _CleanScanner()
    parser_called = False
    monkeypatch.setattr(storage, "configured_malware_scanner", lambda _settings: scanner)

    def forbidden_parser(_path: Path) -> dict[str, object]:
        nonlocal parser_called
        parser_called = True
        raise AssertionError("a legacy nonclean duplicate must not reach the parser")

    monkeypatch.setattr(api_module, "extract_pdf_candidate_metadata", forbidden_parser)
    with TestClient(app) as client:
        response = _request(client, payload)

    assert response.status_code == 409
    assert response.json() == {"detail": "STORED_FILE_NOT_PROCESSABLE"}
    assert scanner.payloads == [payload]
    assert parser_called is False
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(StoredFile)) == 1
        assert db.scalar(select(func.count()).select_from(TechnicalDocument)) == 0


def test_api_persists_quarantine_when_new_scan_detects_existing_exact_sha(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, factory, _settings, _user = _harness(tmp_path)
    payload = b"%PDF clean fixture later detected"
    selected_scanner: list[_CleanScanner] = [_CleanScanner()]
    monkeypatch.setattr(
        storage,
        "configured_malware_scanner",
        lambda _settings: selected_scanner[0],
    )
    monkeypatch.setattr(
        api_module,
        "extract_pdf_candidate_metadata",
        lambda _path: {"extraction_status": "completed"},
    )

    with TestClient(app) as client:
        clean = _request(client, payload, document_id="DOC-UPLOAD-CLEAN")
        selected_scanner[0] = _InfectedScanner()
        detected = _request(client, payload, document_id="DOC-UPLOAD-DETECTED")

    assert clean.status_code == 201
    assert detected.status_code == 422
    assert detected.json() == {"detail": "MALWARE_DETECTED"}
    with factory() as db:
        stored = db.scalar(select(StoredFile))
        assert stored is not None
        assert stored.malware_scan_status == "infected"
        assert db.scalar(select(func.count()).select_from(TechnicalDocument)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.action
                    == "quarantine_stored_file_after_malware_detection"
                )
            )
            == 1
        )


def test_ui_upload_cannot_bypass_missing_scanner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, factory, settings, _user = _harness(tmp_path)
    parser_called = False

    def forbidden_parser(_path: Path) -> dict[str, object]:
        nonlocal parser_called
        parser_called = True
        raise AssertionError("unscanned UI bytes must never reach the PDF parser")

    monkeypatch.setattr(ui_module, "extract_pdf_candidate_metadata", forbidden_parser)
    with TestClient(app) as client:
        csrf_token = _login(client)
        response = client.post(
            "/technical/upload",
            data={
                "csrf_token": csrf_token,
                "document_id": "DOC-UI-001",
                "document_type": "test_report",
                "title": "UI controlled upload",
            },
            files={"file": ("controlled.pdf", b"%PDF unscanned UI", "application/pdf")},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/technical?error=MALWARE_SCANNER_UNAVAILABLE"
    assert parser_called is False
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(StoredFile)) == 0
        assert db.scalar(select(func.count()).select_from(TechnicalDocument)) == 0
    assert not settings.storage_root.exists()


def test_ui_clean_upload_is_scanned_before_parser_and_draft(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, factory, _settings, _user = _harness(tmp_path)
    scanner = _CleanScanner()
    payload = b"%PDF clean UI fixture"
    parsed = 0
    monkeypatch.setattr(storage, "configured_malware_scanner", lambda _settings: scanner)

    def parser(path: Path) -> dict[str, object]:
        nonlocal parsed
        parsed += 1
        assert path.read_bytes() == payload
        return {"extraction_status": "completed"}

    monkeypatch.setattr(ui_module, "extract_pdf_candidate_metadata", parser)
    with TestClient(app) as client:
        csrf_token = _login(client)
        response = client.post(
            "/technical/upload",
            data={
                "csrf_token": csrf_token,
                "document_id": "DOC-UI-001",
                "document_type": "test_report",
                "title": "UI controlled upload",
            },
            files={"file": ("controlled.pdf", payload, "application/pdf")},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/technical"
    assert scanner.payloads == [payload]
    assert parsed == 1
    with factory() as db:
        stored = db.scalar(select(StoredFile))
        document = db.scalar(select(TechnicalDocument))
        assert stored is not None and stored.malware_scan_status == "clean"
        assert document is not None and document.stored_file_id == stored.id
