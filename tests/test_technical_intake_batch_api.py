from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

from classifire import models, physical_models  # noqa: F401
from classifire.api.router import router
from classifire.config import Settings, get_settings
from classifire.db import Base, get_db
from classifire.models import (
    TechnicalIntakeBatch,
    TechnicalIntakeBatchItem,
    User,
)
from classifire.security import get_current_user
from classifire.services import storage as storage_service
from classifire.services.malware_scanning import CLEAN_VERDICT, MalwareScanResult
from classifire.services.technical_intake_batch import (
    TECHNICAL_INTAKE_BATCH_MAX_BODY_BYTES,
    canonical_json_sha256,
)
from classifire.upload_ingress import (
    TECHNICAL_UPLOAD_MULTIPART_OVERHEAD_BYTES,
    TechnicalUploadBodyLimitMiddleware,
)

_CSRF_TOKEN = "technical-intake-batch-api-csrf"  # noqa: S105
_CLIENT_REQUEST_ID = "11111111-1111-4111-8111-111111111111"
_CLIENT_ITEM_ID = "22222222-2222-4222-8222-222222222222"


@dataclass(slots=True)
class _ApiContext:
    app: FastAPI
    sessions: sessionmaker[Session]
    current_user: dict[str, User]
    owner: User
    other_owner: User
    settings: Settings


class _ContentScanner:
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


def _user(email: str, *, role: str = "administrator") -> User:
    return User(
        email=email,
        full_name=email.split("@", 1)[0],
        password_hash="not-used",  # noqa: S106
        role=role,
        is_active=True,
    )


@pytest.fixture
def api_context(tmp_path: Path) -> Iterator[_ApiContext]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions() as db:
        owner = _user("batch-owner@example.test")
        other_owner = _user("other-owner@example.test")
        db.add_all([owner, other_owner])
        db.commit()

    settings = Settings(
        _env_file=None,
        env="test",
        storage_root=tmp_path / "storage",
        clamav_host="scanner.internal",
        max_upload_mb=3,
        upload_ingress_ceiling_mb=3,
    )
    app = FastAPI()
    app.add_middleware(
        SessionMiddleware,
        secret_key="technical-intake-batch-api-secret",  # noqa: S106
    )
    app.add_middleware(
        TechnicalUploadBodyLimitMiddleware,
        maximum_body_bytes=(
            settings.upload_ingress_ceiling_bytes
            + TECHNICAL_UPLOAD_MULTIPART_OVERHEAD_BYTES
        ),
    )

    @app.get("/_test/session")
    def seed_session(request: Request) -> dict[str, bool]:
        request.session["csrf_token"] = _CSRF_TOKEN
        return {"ok": True}

    app.include_router(router)
    def override_db() -> Iterator[Session]:
        with sessions() as db:
            yield db

    current_user = {"value": owner}
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_current_user] = lambda: current_user["value"]
    try:
        yield _ApiContext(
            app,
            sessions,
            current_user,
            owner,
            other_owner,
            settings,
        )
    finally:
        engine.dispose()


def _csrf(client: TestClient) -> dict[str, str]:
    response = client.get("/_test/session")
    assert response.status_code == 200
    return {"X-CSRF-Token": _CSRF_TOKEN}


def _registration(document_id: str = "DOC-BATCH-API-001") -> dict[str, object]:
    return {
        "artifact_provenance_note": None,
        "artifact_provenance_status": "unknown",
        "declared_source_role": "primary_test",
        "document_id": document_id,
        "document_type": "fire_test_report",
        "evidence_limitations": None,
        "evidence_scope": "full_source",
        "expiry_date": None,
        "issuing_organisation": None,
        "jurisdiction": "Australia",
        "manufacturer": "Example manufacturer",
        "publication_date": None,
        "reference": "REPORT-001",
        "related_document_id": None,
        "relationship_effective_date": None,
        "relationship_reason": None,
        "relationship_scope": None,
        "relationship_type": None,
        "review_date": None,
        "revision": "1",
        "sponsor_organisation": None,
        "standards": ["AS 1530.4:2014"],
        "title": "Batch API test report",
    }


def _payload() -> dict[str, object]:
    file_bytes = b"%PDF-1.7\nbatch manifest\n%%EOF\n"
    return {
        "client_request_id": _CLIENT_REQUEST_ID,
        "items": [
            {
                "client_item_id": _CLIENT_ITEM_ID,
                "expected_sha256": hashlib.sha256(file_bytes).hexdigest(),
                "filename": "assessment.pdf",
                "ordinal": 1,
                "registration": _registration(),
                "size_bytes": len(file_bytes),
            }
        ],
    }


def _upload_parts(
    *,
    batch_id: str,
    item_id: str,
    file_bytes: bytes,
    registration: dict[str, object],
) -> list[tuple[str, tuple[str | None, str | bytes, str | None]]]:
    parts: list[tuple[str, tuple[str | None, str | bytes, str | None]]] = []
    for name, raw_value in registration.items():
        if isinstance(raw_value, list):
            value = "\n".join(str(item) for item in raw_value)
        elif raw_value is None:
            value = ""
        else:
            value = str(raw_value)
        parts.append((name, (None, value, None)))
    parts.extend(
        [
            ("batch_id", (None, batch_id, None)),
            ("item_id", (None, item_id, None)),
            ("file", ("historical.pdf", file_bytes, "application/pdf")),
        ]
    )
    return parts


def test_create_replay_read_and_owner_boundary(api_context: _ApiContext) -> None:
    with TestClient(api_context.app) as client:
        headers = _csrf(client)
        created = client.post(
            "/api/v1/technical/upload-batches",
            json=_payload(),
            headers=headers,
        )
        replayed = client.post(
            "/api/v1/technical/upload-batches",
            json=_payload(),
            headers=headers,
        )

        assert created.status_code == 201
        assert created.headers["cache-control"] == "private, no-store"
        assert created.headers["pragma"] == "no-cache"
        created_payload = created.json()
        replayed_payload = replayed.json()
        assert created_payload["ok"] is True
        assert created_payload["idempotent_replay"] is False
        assert created_payload["status"] == "open"
        assert created_payload["counts"]["pending"] == 1
        assert created_payload["batch_id"] != _CLIENT_REQUEST_ID
        assert created_payload["items"][0]["item_id"] != _CLIENT_ITEM_ID
        assert created_payload["items"][0]["client_item_id"] == _CLIENT_ITEM_ID
        assert replayed.status_code == 200
        assert replayed.headers["cache-control"] == "private, no-store"
        assert replayed_payload["batch_id"] == created_payload["batch_id"]
        assert replayed_payload["items"][0]["item_id"] == created_payload["items"][0]["item_id"]
        assert replayed_payload["idempotent_replay"] is True

        read = client.get(created_payload["status_url"])
        assert read.status_code == 200
        assert read.headers["cache-control"] == "private, no-store"
        assert read.json()["batch_id"] == created_payload["batch_id"]
        assert read.json()["idempotent_replay"] is False

        api_context.current_user["value"] = api_context.other_owner
        hidden = client.get(created_payload["status_url"])
        assert hidden.status_code == 404
        assert hidden.headers["cache-control"] == "private, no-store"
        assert hidden.json() == {"detail": "INTAKE_BATCH_NOT_FOUND"}

    with api_context.sessions() as db:
        assert db.scalar(select(func.count()).select_from(TechnicalIntakeBatch)) == 1
        assert db.scalar(select(func.count()).select_from(TechnicalIntakeBatchItem)) == 1


def test_historical_manifest_upload_survives_reduced_admission_limit_through_http(
    api_context: _ApiContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    monkeypatch.setattr(
        storage_service,
        "configured_malware_scanner",
        lambda _settings: scanner,
    )
    file_bytes = b"%PDF-1.7\n" + (b"x" * 2_200_000) + b"\n%%EOF\n"
    registration = _registration("DOC-HISTORICAL-HTTP-001")
    manifest = {
        "client_request_id": _CLIENT_REQUEST_ID,
        "items": [
            {
                "client_item_id": _CLIENT_ITEM_ID,
                "expected_sha256": hashlib.sha256(file_bytes).hexdigest(),
                "filename": "historical.pdf",
                "ordinal": 1,
                "registration": registration,
                "size_bytes": len(file_bytes),
            }
        ],
    }

    with TestClient(api_context.app) as client:
        csrf_headers = _csrf(client)
        created = client.post(
            "/api/v1/technical/upload-batches",
            json=manifest,
            headers=csrf_headers,
        )
        assert created.status_code == 201
        batch = created.json()
        batch_id = batch["batch_id"]
        item_id = batch["items"][0]["item_id"]

        reduced_settings = Settings(
            _env_file=None,
            env="test",
            storage_root=api_context.settings.storage_root,
            clamav_host="scanner.internal",
            max_upload_mb=1,
            upload_ingress_ceiling_mb=3,
        )
        api_context.app.dependency_overrides[get_settings] = (
            lambda: reduced_settings
        )
        parts = _upload_parts(
            batch_id=batch_id,
            item_id=item_id,
            file_bytes=file_bytes,
            registration=registration,
        )

        without_routing_headers = client.post(
            "/api/v1/technical/documents",
            files=parts,
            headers=csrf_headers,
        )
        assert without_routing_headers.status_code == 413
        assert without_routing_headers.json() == {
            "detail": "UPLOAD_SIZE_LIMIT_EXCEEDED"
        }
        assert scanner.calls == []

        upload_headers = {
            **csrf_headers,
            "X-Classifire-Intake-Batch-ID": batch_id,
            "X-Classifire-Intake-Item-ID": item_id,
        }
        first = client.post(
            "/api/v1/technical/documents",
            files=parts,
            headers=upload_headers,
        )
        replay = client.post(
            "/api/v1/technical/documents",
            files=parts,
            headers=upload_headers,
        )

    assert first.status_code == 201
    assert first.json()["idempotent_replay"] is False
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["id"] == first.json()["id"]
    assert scanner.calls == [file_bytes, file_bytes]


@pytest.mark.parametrize("filename", ["assessment.csv", "assessment.xlsm"])
def test_create_rejects_storage_only_extensions(
    api_context: _ApiContext,
    filename: str,
) -> None:
    payload = _payload()
    payload["items"][0]["filename"] = filename  # type: ignore[index]
    with TestClient(api_context.app) as client:
        response = client.post(
            "/api/v1/technical/upload-batches",
            json=payload,
            headers=_csrf(client),
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "INTAKE_BATCH_MANIFEST_INVALID"}
    assert response.headers["cache-control"] == "private, no-store"
    with api_context.sessions() as db:
        assert db.scalar(select(func.count()).select_from(TechnicalIntakeBatch)) == 0
        assert db.scalar(select(func.count()).select_from(TechnicalIntakeBatchItem)) == 0


def test_get_fails_closed_for_persisted_receipt_digest_mismatch(
    api_context: _ApiContext,
) -> None:
    with TestClient(api_context.app) as client:
        created = client.post(
            "/api/v1/technical/upload-batches",
            json=_payload(),
            headers=_csrf(client),
        )
        assert created.status_code == 201
        batch_id = created.json()["batch_id"]
        item_id = created.json()["items"][0]["item_id"]

        with api_context.sessions() as db:
            batch = db.get(TechnicalIntakeBatch, batch_id)
            item = db.get(TechnicalIntakeBatchItem, item_id)
            assert batch is not None
            assert item is not None
            receipt = {
                "batch_id": batch_id,
                "code": "MALWARE_DETECTED",
                "expected_sha256": item.expected_sha256,
                "expected_size_bytes": item.declared_size_bytes,
                "http_status": 422,
                "item_id": item_id,
                "ok": False,
                "operator_attention": False,
                "retryable": False,
                "schema": "technical-intake-item-receipt-v1",
            }
            item.status = "rejected"
            item.attempt_count = 1
            item.outcome_code = "MALWARE_DETECTED"
            item.outcome_retryable = False
            item.last_outcome_at = datetime.now(UTC)
            item.receipt_schema = "technical-intake-item-receipt-v1"
            item.receipt_json = receipt
            item.receipt_sha256 = "f" * 64
            batch.status = "completed_with_rejections"
            batch.completed_at = datetime.now(UTC)
            db.commit()
            assert canonical_json_sha256(receipt) != item.receipt_sha256

        response = client.get(f"/api/v1/technical/upload-batches/{batch_id}")

    assert response.status_code == 503
    assert response.json() == {"detail": "INTAKE_BATCH_PERSISTENCE_CONFLICT"}
    assert response.headers["cache-control"] == "private, no-store"


def test_read_by_client_request_is_owner_bound_and_validates_uuid(
    api_context: _ApiContext,
) -> None:
    with TestClient(api_context.app) as client:
        created = client.post(
            "/api/v1/technical/upload-batches",
            json=_payload(),
            headers=_csrf(client),
        )
        assert created.status_code == 201
        batch_id = created.json()["batch_id"]
        lookup_url = (
            "/api/v1/technical/upload-batches/by-client-request/"
            f"{_CLIENT_REQUEST_ID}"
        )

        owner_lookup = client.get(lookup_url)
        assert owner_lookup.status_code == 200
        assert owner_lookup.headers["cache-control"] == "private, no-store"
        assert owner_lookup.json()["batch_id"] == batch_id
        assert owner_lookup.json()["client_request_id"] == _CLIENT_REQUEST_ID
        assert owner_lookup.json()["idempotent_replay"] is False

        api_context.current_user["value"] = api_context.other_owner
        hidden = client.get(lookup_url)
        assert hidden.status_code == 404
        assert hidden.headers["cache-control"] == "private, no-store"
        assert hidden.json() == {"detail": "INTAKE_BATCH_NOT_FOUND"}

        api_context.current_user["value"] = api_context.owner
        invalid = client.get(
            "/api/v1/technical/upload-batches/by-client-request/not-a-uuid"
        )
        assert invalid.status_code == 422
        assert invalid.headers["cache-control"] == "private, no-store"
        assert invalid.json() == {"detail": "INTAKE_BATCH_ID_INVALID"}


def test_authentication_and_csrf_precede_body_streaming(
    api_context: _ApiContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream_calls = 0

    async def forbidden_stream(_request: Request):
        nonlocal stream_calls
        stream_calls += 1
        raise AssertionError("request body was streamed before authentication and CSRF")
        yield b""  # pragma: no cover

    monkeypatch.setattr(Request, "stream", forbidden_stream)
    encoded = json.dumps(_payload()).encode("utf-8")
    api_context.app.dependency_overrides.pop(get_current_user)
    with TestClient(api_context.app) as client:
        unauthenticated = client.post(
            "/api/v1/technical/upload-batches",
            content=encoded,
            headers={"Content-Type": "application/json"},
        )
    assert unauthenticated.status_code == 401
    assert stream_calls == 0

    api_context.app.dependency_overrides[get_current_user] = (
        lambda: api_context.current_user["value"]
    )
    with TestClient(api_context.app) as client:
        _csrf(client)
        invalid_csrf = client.post(
            "/api/v1/technical/upload-batches",
            content=encoded,
            headers={"Content-Type": "application/json"},
        )
    assert invalid_csrf.status_code == 403
    assert invalid_csrf.json() == {"detail": "CSRF_INVALID"}
    assert stream_calls == 0


@pytest.mark.parametrize(
    ("content", "content_type", "expected_code"),
    [
        (b"{}", "application/json; charset=utf-8", "INTAKE_BATCH_CONTENT_TYPE_INVALID"),
        (b"{", "application/json", "INTAKE_BATCH_BODY_INVALID"),
        (
            json.dumps(
                {
                    "client_request_id": _CLIENT_REQUEST_ID,
                    "items": [],
                    "unexpected": True,
                }
            ).encode("utf-8"),
            "application/json",
            "INTAKE_BATCH_BODY_INVALID",
        ),
        (
            b'{"client_request_id":"11111111-1111-4111-8111-111111111111",'
            b'"client_request_id":"11111111-1111-4111-8111-111111111111",'
            b'"items":[]}',
            "application/json",
            "INTAKE_BATCH_BODY_INVALID",
        ),
    ],
)
def test_create_rejects_non_exact_content_and_json_shape(
    api_context: _ApiContext,
    content: bytes,
    content_type: str,
    expected_code: str,
) -> None:
    with TestClient(api_context.app) as client:
        response = client.post(
            "/api/v1/technical/upload-batches",
            content=content,
            headers={
                **_csrf(client),
                "Content-Type": content_type,
            },
        )

    assert response.status_code == 422
    assert response.json() == {"detail": expected_code}


def test_create_rejects_oversized_declared_body_before_streaming(
    api_context: _ApiContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream_calls = 0

    async def forbidden_stream(_request: Request):
        nonlocal stream_calls
        stream_calls += 1
        raise AssertionError("oversized declared body was streamed")
        yield b""  # pragma: no cover

    monkeypatch.setattr(Request, "stream", forbidden_stream)
    with TestClient(api_context.app) as client:
        response = client.post(
            "/api/v1/technical/upload-batches",
            content=b"{}",
            headers={
                **_csrf(client),
                "Content-Type": "application/json",
                "Content-Length": str(TECHNICAL_INTAKE_BATCH_MAX_BODY_BYTES + 1),
            },
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "INTAKE_BATCH_BODY_INVALID"}
    assert stream_calls == 0


def test_create_rejects_pathologically_long_numeric_length_before_streaming(
    api_context: _ApiContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream_calls = 0

    async def forbidden_stream(_request: Request):
        nonlocal stream_calls
        stream_calls += 1
        raise AssertionError("pathological declared body was streamed")
        yield b""  # pragma: no cover

    monkeypatch.setattr(Request, "stream", forbidden_stream)
    with TestClient(api_context.app) as client:
        response = client.post(
            "/api/v1/technical/upload-batches",
            content=b"{}",
            headers={
                **_csrf(client),
                "Content-Type": "application/json",
                "Content-Length": "9" * 5_000,
            },
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "INTAKE_BATCH_BODY_INVALID"}
    assert stream_calls == 0


def test_create_rejects_duplicate_csrf_header_before_streaming(
    api_context: _ApiContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream_calls = 0

    async def forbidden_stream(_request: Request):
        nonlocal stream_calls
        stream_calls += 1
        raise AssertionError("duplicate CSRF request body was streamed")
        yield b""  # pragma: no cover

    monkeypatch.setattr(Request, "stream", forbidden_stream)
    encoded = json.dumps(_payload()).encode("utf-8")
    with TestClient(api_context.app) as client:
        _csrf(client)
        response = client.post(
            "/api/v1/technical/upload-batches",
            content=encoded,
            headers=[
                ("Content-Type", "application/json"),
                ("X-CSRF-Token", _CSRF_TOKEN),
                ("X-CSRF-Token", _CSRF_TOKEN),
            ],
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "CSRF_INVALID"}
    assert stream_calls == 0
