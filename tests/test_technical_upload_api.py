from __future__ import annotations

import importlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.formparsers import MultiPartException
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

from classifire.config import Settings, get_settings
from classifire.db import get_db
from classifire.models import TechnicalDocument, User
from classifire.security import get_current_user
from classifire.services.technical_intake_batch import TECHNICAL_INTAKE_CLAIM_TTL

api_router = importlib.import_module("classifire.api.router")
upload_preflight_service = importlib.import_module(
    "classifire.services.technical_upload_preflight"
)
_NO_USER_OVERRIDE = object()
_CSRF_TOKEN = "technical-upload-api-csrf-token"  # noqa: S105 - isolated fixture


class _UnusedDb:
    def get(self, model: object, identifier: object) -> object | None:
        if model is TechnicalDocument and identifier == "related-document-row":
            return SimpleNamespace(document_id="DOC-RELATED-001")
        return None


def _user(role: str) -> User:
    return User(
        email=f"{role}@api-upload.example.test",
        full_name="API Upload Test",
        password_hash="not-used",  # noqa: S106
        role=role,
        is_active=True,
    )


def _test_app(
    tmp_path: Path,
    *,
    user: User | object = _NO_USER_OVERRIDE,
) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        SessionMiddleware,
        secret_key="technical-upload-api-test-secret",  # noqa: S106
    )
    @app.get("/_test/session")
    def seed_session(request: Request) -> dict[str, bool]:
        request.session["csrf_token"] = _CSRF_TOKEN
        return {"ok": True}

    app.include_router(api_router.router)
    settings = Settings(
        _env_file=None,
        env="test",
        storage_root=tmp_path / "storage",
        clamav_host="scanner.internal",
    )

    def override_db() -> Iterator[Session]:
        yield cast(Session, _UnusedDb())

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    if user is not _NO_USER_OVERRIDE:
        app.dependency_overrides[get_current_user] = lambda: cast(User, user)
    return app


def _pdf() -> bytes:
    return b"%PDF-1.7\nAPI upload test\n%%EOF\n"


def _valid_parts() -> list[tuple[str, tuple[str | None, str | bytes, str | None]]]:
    return [
        ("document_id", (None, "DOC-API-001", None)),
        ("document_type", (None, "regulatory_information_report", None)),
        ("declared_source_role", (None, "regulatory_summary", None)),
        ("artifact_provenance_status", (None, "transformed_derivative", None)),
        ("evidence_scope", (None, "summary_only", None)),
        ("title", (None, "API regulatory information report", None)),
        ("manufacturer", (None, "Example manufacturer", None)),
        ("reference", (None, "SYNTHETIC-REPORT-236", None)),
        ("revision", (None, "RIR1.25A", None)),
        ("sponsor_organisation", (None, "TBA Textiles Pty Ltd", None)),
        ("issuing_organisation", (None, "Jensen Hughes Fire Testing Pty Ltd", None)),
        ("publication_date", (None, "2026-02-20", None)),
        ("review_date", (None, "2026-02-21", None)),
        ("expiry_date", (None, "2030-09-30", None)),
        ("standards", (None, "AS 1530.4:2014\nAS 4072.1:2005", None)),
        ("artifact_provenance_note", (None, "Unlocked supplied derivative", None)),
        ("evidence_limitations", (None, "Main assessment reasoning omitted", None)),
        ("relationship_type", (None, "summary_of", None)),
        ("related_document_id", (None, "DOC-RELATED-001", None)),
        ("relationship_reason", (None, "Regulatory summary of main assessment", None)),
        ("relationship_scope", (None, "Reported assessed configurations", None)),
        ("relationship_effective_date", (None, "2026-02-20", None)),
        ("jurisdiction", (None, "NSW, Australia", None)),
        ("file", ("report.pdf", _pdf(), "application/pdf")),
    ]


def _seed_csrf(client: TestClient) -> dict[str, str]:
    response = client.get("/_test/session")
    assert response.status_code == 200
    return {"X-CSRF-Token": _CSRF_TOKEN}


def _seed_batch_headers(
    client: TestClient,
    *,
    batch_id: str,
    item_id: str,
) -> dict[str, str]:
    headers = _seed_csrf(client)
    headers.update(
        {
            "X-Classifire-Intake-Batch-ID": batch_id,
            "X-Classifire-Intake-Item-ID": item_id,
        }
    )
    return headers


def _install_batch_preflight(
    monkeypatch: pytest.MonkeyPatch,
    *,
    batch_id: str,
    item_id: str,
    declared_size_bytes: int = 1024 * 1024,
    status: str = "pending",
    outcome_retryable: bool | None = None,
    attempt_started_at: datetime | None = None,
) -> None:
    def owned_batch(
        _db: Session,
        *,
        actor: User,
        batch_id: object,
    ) -> tuple[object, tuple[object, ...]]:
        assert actor.is_active is True
        assert batch_id == owned_batch_id
        return (
            SimpleNamespace(id=owned_batch_id),
            (
                SimpleNamespace(
                    id=item_id,
                    declared_size_bytes=declared_size_bytes,
                    status=status,
                    outcome_retryable=outcome_retryable,
                    attempt_started_at=attempt_started_at,
                ),
            ),
        )

    owned_batch_id = batch_id
    monkeypatch.setattr(
        upload_preflight_service,
        "get_owned_technical_intake_batch",
        owned_batch,
    )


@pytest.mark.parametrize(
    ("user", "expected_status"),
    [(_NO_USER_OVERRIDE, 401), (_user("read_only"), 403)],
)
def test_authentication_and_permission_run_before_multipart_parsing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    user: User | object,
    expected_status: int,
) -> None:
    calls = 0
    preflight_calls = 0

    def forbidden_form(self: Request, **_kwargs: object):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        raise AssertionError("request.form must not run before authorisation")

    def forbidden_preflight(*_args: object, **_kwargs: object) -> None:
        nonlocal preflight_calls
        preflight_calls += 1
        raise AssertionError("upload preflight must not run before authorisation")

    monkeypatch.setattr(Request, "form", forbidden_form)
    monkeypatch.setattr(api_router, "preflight_technical_upload", forbidden_preflight)
    app = _test_app(tmp_path, user=user)

    with TestClient(app) as client:
        response = client.post("/api/v1/technical/documents", files=_valid_parts())

    assert response.status_code == expected_status
    assert calls == 0
    assert preflight_calls == 0


def test_csrf_runs_before_multipart_parsing_for_authorised_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    preflight_calls = 0

    def forbidden_form(self: Request, **_kwargs: object):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        raise AssertionError("request.form must not run before CSRF validation")

    def forbidden_preflight(*_args: object, **_kwargs: object) -> None:
        nonlocal preflight_calls
        preflight_calls += 1
        raise AssertionError("upload preflight must not run before CSRF validation")

    monkeypatch.setattr(Request, "form", forbidden_form)
    monkeypatch.setattr(api_router, "preflight_technical_upload", forbidden_preflight)
    app = _test_app(tmp_path, user=_user("administrator"))

    with TestClient(app) as client:
        _seed_csrf(client)
        response = client.post("/api/v1/technical/documents", files=_valid_parts())

    assert response.status_code == 403
    assert response.json() == {"detail": "CSRF_INVALID"}
    assert calls == 0
    assert preflight_calls == 0


def test_ordinary_upload_over_current_limit_is_legacy_error_before_form_parsing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    form_calls = 0

    def forbidden_form(self: Request, **_kwargs: object):  # type: ignore[no-untyped-def]
        nonlocal form_calls
        form_calls += 1
        raise AssertionError("oversize request must not reach multipart parsing")

    monkeypatch.setattr(Request, "form", forbidden_form)
    app = _test_app(tmp_path, user=_user("administrator"))

    with TestClient(app) as client:
        headers = _seed_csrf(client)
        headers.update(
            {
                "Content-Type": "multipart/form-data; boundary=preflight-test",
                "Content-Length": str(101 * 1024 * 1024 + 1),
            }
        )
        response = client.post(
            "/api/v1/technical/documents",
            content=b"",
            headers=headers,
        )

    assert response.status_code == 413
    assert response.json() == {"detail": "UPLOAD_SIZE_LIMIT_EXCEEDED"}
    assert form_calls == 0


def test_api_batch_header_failure_is_structured_before_form_parsing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    form_calls = 0

    def forbidden_form(self: Request, **_kwargs: object):  # type: ignore[no-untyped-def]
        nonlocal form_calls
        form_calls += 1
        raise AssertionError("invalid batch headers must not reach multipart parsing")

    monkeypatch.setattr(Request, "form", forbidden_form)
    app = _test_app(tmp_path, user=_user("administrator"))

    with TestClient(app) as client:
        headers = _seed_csrf(client)
        headers["X-Classifire-Intake-Batch-ID"] = (
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        )
        response = client.post(
            "/api/v1/technical/documents",
            files=_valid_parts(),
            headers=headers,
        )

    assert response.status_code == 422
    assert response.json() == {
        "ok": False,
        "code": "INTAKE_BATCH_ITEM_ID_INVALID",
        "retryable": False,
        "fatal": True,
    }
    assert form_calls == 0


@pytest.mark.parametrize(
    ("item_status", "outcome_retryable", "active", "expected_code", "retryable"),
    [
        ("needs_attention", False, False, "INTAKE_BATCH_ITEM_NOT_RETRYABLE", False),
        ("rejected", False, False, "INTAKE_BATCH_ITEM_NOT_RETRYABLE", False),
        ("processing", None, False, "INTAKE_BATCH_ITEM_NOT_RETRYABLE", False),
        ("processing", None, True, "INTAKE_BATCH_ITEM_IN_PROGRESS", True),
    ],
)
def test_api_batch_lifecycle_rejection_runs_before_form_or_services(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    item_status: str,
    outcome_retryable: bool | None,
    active: bool,
    expected_code: str,
    retryable: bool,
) -> None:
    batch_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    item_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    form_calls = 0
    service_calls = 0

    def forbidden_form(self: Request, **_kwargs: object):  # type: ignore[no-untyped-def]
        nonlocal form_calls
        form_calls += 1
        raise AssertionError("ineligible item must not reach multipart parsing")

    def forbidden_service(*_args: object, **_kwargs: object) -> None:
        nonlocal service_calls
        service_calls += 1
        raise AssertionError("ineligible item must not reach upload services")

    _install_batch_preflight(
        monkeypatch,
        batch_id=batch_id,
        item_id=item_id,
        status=item_status,
        outcome_retryable=outcome_retryable,
        attempt_started_at=datetime.now(UTC) if active else None,
    )
    monkeypatch.setattr(Request, "form", forbidden_form)
    monkeypatch.setattr(
        api_router,
        "claim_technical_intake_batch_item",
        forbidden_service,
    )
    monkeypatch.setattr(
        api_router,
        "create_technical_document_draft",
        forbidden_service,
    )
    app = _test_app(tmp_path, user=_user("administrator"))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/technical/documents",
            files=_valid_parts(),
            headers=_seed_batch_headers(
                client,
                batch_id=batch_id,
                item_id=item_id,
            ),
        )

    assert response.status_code == 409
    assert response.json() == {
        "ok": False,
        "code": expected_code,
        "retryable": retryable,
        "fatal": False,
    }
    assert form_calls == 0
    assert service_calls == 0


@pytest.mark.parametrize(
    ("item_status", "outcome_retryable", "stale"),
    [
        ("accepted", False, False),
        ("rejected", True, False),
        ("processing", None, True),
    ],
)
def test_api_batch_preflight_allows_replay_retry_and_stale_reclaim_to_parser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    item_status: str,
    outcome_retryable: bool | None,
    stale: bool,
) -> None:
    batch_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    item_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    form_calls = 0

    def parsing_started(self: Request, **_kwargs: object):  # type: ignore[no-untyped-def]
        nonlocal form_calls
        form_calls += 1
        raise MultiPartException("synthetic parser stop")

    def forbidden_service(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("synthetic parser stop must precede upload services")

    started_at = (
        datetime.now(UTC) - TECHNICAL_INTAKE_CLAIM_TTL - timedelta(seconds=1)
        if stale
        else None
    )
    _install_batch_preflight(
        monkeypatch,
        batch_id=batch_id,
        item_id=item_id,
        status=item_status,
        outcome_retryable=outcome_retryable,
        attempt_started_at=started_at,
    )
    monkeypatch.setattr(Request, "form", parsing_started)
    monkeypatch.setattr(
        api_router,
        "claim_technical_intake_batch_item",
        forbidden_service,
    )
    monkeypatch.setattr(
        api_router,
        "create_technical_document_draft",
        forbidden_service,
    )
    app = _test_app(tmp_path, user=_user("administrator"))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/technical/documents",
            files=_valid_parts(),
            headers=_seed_batch_headers(
                client,
                batch_id=batch_id,
                item_id=item_id,
            ),
        )

    assert response.status_code == 422
    assert response.json() == {
        "ok": False,
        "code": "TECHNICAL_UPLOAD_FORM_INVALID",
        "retryable": False,
        "fatal": True,
    }
    assert form_calls == 1


def test_api_batch_form_failure_remains_structured_after_valid_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    item_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"

    def forbidden_service(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("invalid batch form must not claim or persist")

    _install_batch_preflight(
        monkeypatch,
        batch_id=batch_id,
        item_id=item_id,
    )
    monkeypatch.setattr(
        api_router,
        "claim_technical_intake_batch_item",
        forbidden_service,
    )
    monkeypatch.setattr(
        api_router,
        "create_technical_document_draft",
        forbidden_service,
    )
    parts = [
        (
            name,
            (None, "", None) if name == "document_id" else value,
        )
        for name, value in _valid_parts()
    ]
    parts.insert(-1, ("batch_id", (None, batch_id, None)))
    parts.insert(-1, ("item_id", (None, item_id, None)))
    app = _test_app(tmp_path, user=_user("administrator"))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/technical/documents",
            files=parts,
            headers=_seed_batch_headers(
                client,
                batch_id=batch_id,
                item_id=item_id,
            ),
        )

    assert response.status_code == 422
    assert response.json() == {
        "ok": False,
        "code": "DOCUMENT_ID_INVALID",
        "retryable": False,
        "fatal": True,
    }


def test_authorised_upload_uses_tight_parser_limits_and_one_shared_service_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser_calls: list[dict[str, object]] = []
    service_calls: list[dict[str, Any]] = []
    captured_uploads: list[object] = []
    original_form = Request.form

    def tracking_form(self: Request, **kwargs: object):  # type: ignore[no-untyped-def]
        parser_calls.append(kwargs)
        return original_form(self, **kwargs)

    def create_draft(_db: Session, _settings: Settings, **kwargs: Any) -> object:
        service_calls.append(kwargs)
        captured_uploads.append(kwargs["upload"])
        assert kwargs["upload"].file.closed is False
        return SimpleNamespace(
            document=SimpleNamespace(
                id="technical-document-row",
                document_id=kwargs["document_id"],
                document_type=kwargs["document_type"],
                declared_source_role=kwargs["declared_source_role"],
                artifact_provenance_status=kwargs["artifact_provenance_status"],
                evidence_scope=kwargs["evidence_scope"],
                status="draft",
                extraction_status="awaiting_safe_extraction",
                metadata_json={"human_review_required": True},
            ),
            stored_file=SimpleNamespace(
                sha256="a" * 64,
                malware_scan_status="clean",
            ),
            correlation_id=kwargs["correlation_id"],
            batch_item_id=None,
            idempotent_replay=False,
            receipt_sha256=None,
            receipt=None,
            relationship=SimpleNamespace(
                related_document_id="related-document-row",
                relationship_type=kwargs["relationship_type"],
                reason=kwargs["relationship_reason"],
            ),
            exact_content_duplicate_document_ids=("DOC-EXACT-001",),
        )

    monkeypatch.setattr(Request, "form", tracking_form)
    monkeypatch.setattr(api_router, "create_technical_document_draft", create_draft)
    app = _test_app(tmp_path, user=_user("administrator"))
    large_evidence_limitations = ("耐火\r\n" * 3_000).strip()
    parts = [
        (
            name,
            (
                (None, large_evidence_limitations, None)
                if name == "evidence_limitations"
                else value
            ),
        )
        for name, value in _valid_parts()
    ]

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/technical/documents",
            files=parts,
            headers=_seed_csrf(client),
        )

    assert response.status_code == 201
    assert response.json()["document_id"] == "DOC-API-001"
    assert parser_calls == [
        {"max_files": 1, "max_fields": 25, "max_part_size": 128 * 1024}
    ]
    assert len(service_calls) == 1
    assert service_calls[0]["document_type"] == "regulatory_information_report"
    assert service_calls[0]["declared_source_role"] == "regulatory_summary"
    assert service_calls[0]["artifact_provenance_status"] == "transformed_derivative"
    assert service_calls[0]["evidence_scope"] == "summary_only"
    assert service_calls[0]["sponsor_organisation"] == "TBA Textiles Pty Ltd"
    assert service_calls[0]["publication_date"] == "2026-02-20"
    assert service_calls[0]["standards"] == "AS 1530.4:2014\nAS 4072.1:2005"
    assert service_calls[0]["jurisdiction"] == "NSW, Australia"
    assert service_calls[0]["relationship_type"] == "summary_of"
    assert service_calls[0]["related_document_id"] == "DOC-RELATED-001"
    assert service_calls[0]["relationship_reason"] == "Regulatory summary of main assessment"
    assert service_calls[0]["relationship_scope"] == "Reported assessed configurations"
    assert service_calls[0]["evidence_limitations"] == large_evidence_limitations
    assert service_calls[0]["relationship_effective_date"] == "2026-02-20"
    assert service_calls[0]["correlation_id"] is None
    assert response.json()["relationship"] == {
        "relationship_type": "summary_of",
        "related_document_id": "DOC-RELATED-001",
    }
    assert response.json()["document_type"] == "regulatory_information_report"
    assert response.json()["declared_source_role"] == "regulatory_summary"
    assert response.json()["artifact_provenance_status"] == "transformed_derivative"
    assert response.json()["evidence_scope"] == "summary_only"
    assert response.json()["exact_content_duplicate_document_ids"] == [
        "DOC-EXACT-001"
    ]
    assert captured_uploads[0].file.closed is True


def test_batch_replay_projects_immutable_receipt_after_document_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    item_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    receipt = {
        "artifact_provenance_status": "unknown",
        "batch_id": batch_id,
        "declared_source_role": "regulatory_summary",
        "document_id": "DOC-API-001",
        "document_type": "regulatory_information_report",
        "evidence_scope": "summary_only",
        "exact_content_duplicate_document_ids": ["DOC-EXACT-001"],
        "extraction_status": "awaiting_safe_extraction",
        "file_sha256": "a" * 64,
        "http_status": 201,
        "id": "technical-document-row",
        "item_id": item_id,
        "malware_scan_status": "clean",
        "ok": True,
        "relationship": {
            "relationship_type": "summary_of",
            "related_document_id": "DOC-RELATED-001",
        },
        "schema": "technical-intake-item-receipt-v1",
        "status": "draft",
        "status_url": f"/api/v1/technical/upload-batches/{batch_id}",
    }

    def claim_item(*_args: object, **_kwargs: object) -> object:
        return SimpleNamespace(batch_id=batch_id, item_id=item_id)

    def replay_draft(_db: Session, _settings: Settings, **_kwargs: Any) -> object:
        return SimpleNamespace(
            document=SimpleNamespace(
                id="technical-document-row",
                document_id="DOC-API-001",
                document_type="fire_assessment",
                declared_source_role="assessment",
                artifact_provenance_status="issuer_original",
                evidence_scope="full_source",
                status="reviewed",
                extraction_status="reviewed_extraction",
                metadata_json={"later_review_note": "metadata changed"},
            ),
            stored_file=SimpleNamespace(
                sha256="a" * 64,
                malware_scan_status="clean",
            ),
            correlation_id=batch_id,
            batch_item_id=item_id,
            idempotent_replay=True,
            receipt_sha256="f" * 64,
            receipt=receipt,
            relationship=SimpleNamespace(
                relationship_type="revision_of",
                related_document_id="different-related-row",
            ),
            exact_content_duplicate_document_ids=("DOC-LATER-DUPLICATE",),
        )

    monkeypatch.setattr(
        api_router,
        "claim_technical_intake_batch_item",
        claim_item,
    )
    monkeypatch.setattr(
        api_router,
        "create_technical_document_draft",
        replay_draft,
    )
    _install_batch_preflight(
        monkeypatch,
        batch_id=batch_id,
        item_id=item_id,
    )
    parts = _valid_parts()
    parts.insert(-1, ("batch_id", (None, batch_id, None)))
    parts.insert(-1, ("item_id", (None, item_id, None)))
    app = _test_app(tmp_path, user=_user("administrator"))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/technical/documents",
            files=parts,
            headers=_seed_batch_headers(
                client,
                batch_id=batch_id,
                item_id=item_id,
            ),
        )

    assert response.status_code == 200
    payload = response.json()
    for key in (
        "artifact_provenance_status",
        "batch_id",
        "declared_source_role",
        "document_id",
        "document_type",
        "evidence_scope",
        "extraction_status",
        "file_sha256",
        "id",
        "item_id",
        "malware_scan_status",
        "relationship",
        "status",
        "status_url",
    ):
        assert payload[key] == receipt[key]
    assert payload["exact_content_duplicate_document_ids"] == receipt[
        "exact_content_duplicate_document_ids"
    ]
    assert payload["metadata"] == {"later_review_note": "metadata changed"}
    assert payload["idempotent_replay"] is True


@pytest.mark.parametrize(
    ("missing_field", "expected_code"),
    [
        ("item_id", "INTAKE_BATCH_ITEM_ID_INVALID"),
        ("batch_id", "INTAKE_BATCH_ID_INVALID"),
    ],
)
def test_batch_and_item_ids_must_be_paired_before_intake_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing_field: str,
    expected_code: str,
) -> None:
    def forbidden_service(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("unpaired batch identity must not reach intake")

    parts = _valid_parts()
    if missing_field == "item_id":
        parts.insert(
            -1,
            ("batch_id", (None, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", None)),
        )
    else:
        parts = [(name, value) for name, value in parts if name != "batch_id"]
        parts.insert(
            -1,
            ("item_id", (None, "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", None)),
        )

    monkeypatch.setattr(
        api_router,
        "claim_technical_intake_batch_item",
        forbidden_service,
    )
    monkeypatch.setattr(
        api_router,
        "create_technical_document_draft",
        forbidden_service,
    )
    app = _test_app(tmp_path, user=_user("administrator"))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/technical/documents",
            files=parts,
            headers=_seed_csrf(client),
        )

    assert response.status_code == 422
    assert response.json() == {"detail": expected_code}


def test_scanner_required_error_is_stable_through_http_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_calls = 0
    captured_uploads: list[Any] = []

    def scanner_required(_db: Session, _settings: Settings, **kwargs: Any) -> None:
        nonlocal service_calls
        service_calls += 1
        captured_uploads.append(kwargs["upload"])
        raise api_router.TechnicalIntakeError("MALWARE_SCANNER_REQUIRED")

    monkeypatch.setattr(
        api_router,
        "create_technical_document_draft",
        scanner_required,
    )
    app = _test_app(tmp_path, user=_user("administrator"))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/technical/documents",
            files=_valid_parts(),
            headers=_seed_csrf(client),
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "MALWARE_SCANNER_REQUIRED"}
    assert service_calls == 1
    assert captured_uploads[0].file.closed is True


@pytest.mark.parametrize(
    ("code", "expected_status", "retryable", "fatal"),
    [
        ("MALWARE_DETECTED", 422, False, False),
        ("MALWARE_SCANNER_REQUIRED", 503, True, True),
    ],
)
def test_batch_item_intake_errors_use_the_browser_failure_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    code: str,
    expected_status: int,
    retryable: bool,
    fatal: bool,
) -> None:
    batch_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    item_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    captured_uploads: list[Any] = []

    def claim_item(*_args: object, **_kwargs: object) -> object:
        return SimpleNamespace(batch_id=batch_id, item_id=item_id)

    def fail_intake(_db: Session, _settings: Settings, **kwargs: Any) -> None:
        captured_uploads.append(kwargs["upload"])
        raise api_router.TechnicalIntakeError(code)

    monkeypatch.setattr(api_router, "claim_technical_intake_batch_item", claim_item)
    monkeypatch.setattr(api_router, "create_technical_document_draft", fail_intake)
    _install_batch_preflight(
        monkeypatch,
        batch_id=batch_id,
        item_id=item_id,
    )
    parts = _valid_parts()
    parts.insert(-1, ("batch_id", (None, batch_id, None)))
    parts.insert(-1, ("item_id", (None, item_id, None)))
    app = _test_app(tmp_path, user=_user("administrator"))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/technical/documents",
            files=parts,
            headers=_seed_batch_headers(
                client,
                batch_id=batch_id,
                item_id=item_id,
            ),
        )

    assert response.status_code == expected_status
    assert response.json() == {
        "ok": False,
        "code": code,
        "retryable": retryable,
        "fatal": fatal,
    }
    assert captured_uploads[0].file.closed is True


def test_batch_item_claim_errors_use_the_browser_failure_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    item_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"

    def fail_claim(*_args: object, **_kwargs: object) -> None:
        raise api_router.TechnicalIntakeBatchError(
            "INTAKE_BATCH_ITEM_IN_PROGRESS"
        )

    def forbidden_intake(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("a failed claim must not reach intake")

    monkeypatch.setattr(api_router, "claim_technical_intake_batch_item", fail_claim)
    monkeypatch.setattr(api_router, "create_technical_document_draft", forbidden_intake)
    _install_batch_preflight(
        monkeypatch,
        batch_id=batch_id,
        item_id=item_id,
    )
    parts = _valid_parts()
    parts.insert(-1, ("batch_id", (None, batch_id, None)))
    parts.insert(-1, ("item_id", (None, item_id, None)))
    app = _test_app(tmp_path, user=_user("administrator"))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/technical/documents",
            files=parts,
            headers=_seed_batch_headers(
                client,
                batch_id=batch_id,
                item_id=item_id,
            ),
        )

    assert response.status_code == 409
    assert response.json() == {
        "ok": False,
        "code": "INTAKE_BATCH_ITEM_IN_PROGRESS",
        "retryable": True,
        "fatal": False,
    }


def test_wrong_content_type_is_stable_and_never_parsed_or_persisted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    form_calls = 0

    def forbidden_form(self: Request, **_kwargs: object):  # type: ignore[no-untyped-def]
        nonlocal form_calls
        form_calls += 1
        raise AssertionError("wrong content type must not be parsed")

    def forbidden_service(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("malformed form must not reach intake")

    monkeypatch.setattr(Request, "form", forbidden_form)
    monkeypatch.setattr(api_router, "create_technical_document_draft", forbidden_service)
    app = _test_app(tmp_path, user=_user("administrator"))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/technical/documents",
            json={"document_id": "DOC-JSON"},
            headers=_seed_csrf(client),
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "TECHNICAL_UPLOAD_FORM_INVALID"}
    assert form_calls == 0


@pytest.mark.parametrize(
    ("parts", "expected_code"),
    [
        (
            [
                ("document_id", (None, "DOC-ONE", None)),
                ("document_id", (None, "DOC-TWO", None)),
                ("document_type", (None, "fire_test_report", None)),
                ("title", (None, "Duplicate identity", None)),
                ("file", ("report.pdf", _pdf(), "application/pdf")),
            ],
            "DOCUMENT_ID_INVALID",
        ),
        (
            [
                ("document_id", (None, "", None)),
                ("document_type", (None, "fire_test_report", None)),
                ("title", (None, "Empty identity", None)),
                ("file", ("report.pdf", _pdf(), "application/pdf")),
            ],
            "DOCUMENT_ID_INVALID",
        ),
        (
            [
                ("document_id", (None, "DOC-MISSING-TITLE", None)),
                ("document_type", (None, "fire_test_report", None)),
                ("file", ("report.pdf", _pdf(), "application/pdf")),
            ],
            "INTAKE_FIELD_INVALID",
        ),
        (
            [
                ("document_id", (None, "DOC-NON-TEXT", None)),
                ("document_type", (None, "fire_test_report", None)),
                ("title", ("title.txt", b"not a text field", "text/plain")),
            ],
            "INTAKE_FIELD_INVALID",
        ),
        (
            [
                ("document_id", (None, "DOC-DUPLICATE-OPTIONAL", None)),
                ("document_type", (None, "fire_test_report", None)),
                ("title", (None, "Duplicate optional", None)),
                ("manufacturer", (None, "One", None)),
                ("manufacturer", (None, "Two", None)),
                ("file", ("report.pdf", _pdf(), "application/pdf")),
            ],
            "INTAKE_FIELD_INVALID",
        ),
        (
            [
                ("document_id", (None, "DOC-DUPLICATE-RELATIONSHIP", None)),
                ("document_type", (None, "fire_test_report", None)),
                ("title", (None, "Duplicate relationship field", None)),
                ("relationship_type", (None, "revision_of", None)),
                ("relationship_type", (None, "assessment_of", None)),
                ("file", ("report.pdf", _pdf(), "application/pdf")),
            ],
            "INTAKE_FIELD_INVALID",
        ),
        (
            [
                ("document_id", (None, "DOC-MULTI-FILE", None)),
                ("document_type", (None, "fire_test_report", None)),
                ("title", (None, "Multiple files", None)),
                ("file", ("one.pdf", _pdf(), "application/pdf")),
                ("file", ("two.pdf", _pdf(), "application/pdf")),
            ],
            "TECHNICAL_UPLOAD_FORM_INVALID",
        ),
        (
            [
                ("document_id", (None, "DOC-UNKNOWN-FIELD", None)),
                ("document_type", (None, "fire_test_report", None)),
                ("title", (None, "Unknown field", None)),
                ("unexpected", (None, "not allowed", None)),
                ("file", ("report.pdf", _pdf(), "application/pdf")),
            ],
            "TECHNICAL_UPLOAD_FORM_INVALID",
        ),
    ],
)
def test_malformed_or_ambiguous_form_is_stable_and_never_persisted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    parts: list[tuple[str, tuple[str | None, str | bytes, str | None]]],
    expected_code: str,
) -> None:
    service_calls = 0

    def forbidden_service(*_args: object, **_kwargs: object) -> None:
        nonlocal service_calls
        service_calls += 1
        raise AssertionError("malformed form must not reach intake")

    monkeypatch.setattr(api_router, "create_technical_document_draft", forbidden_service)
    app = _test_app(tmp_path, user=_user("administrator"))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/technical/documents",
            files=parts,
            headers=_seed_csrf(client),
        )

    assert response.status_code == 422
    assert response.json() == {"detail": expected_code}
    assert service_calls == 0


def test_missing_multipart_boundary_is_a_stable_form_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_service(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("malformed form must not reach intake")

    monkeypatch.setattr(api_router, "create_technical_document_draft", forbidden_service)
    app = _test_app(tmp_path, user=_user("administrator"))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/technical/documents",
            headers={
                "content-type": "multipart/form-data",
                **_seed_csrf(client),
            },
            content=b"not-a-valid-multipart-body",
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "TECHNICAL_UPLOAD_FORM_INVALID"}
