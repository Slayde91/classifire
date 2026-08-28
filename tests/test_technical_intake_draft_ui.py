# ruff: noqa: S105, S106
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

from classifire import models, physical_models  # noqa: F401
from classifire.config import Settings, get_settings
from classifire.db import Base, get_db
from classifire.models import (
    Approval,
    AuditEvent,
    LibraryRelease,
    StoredFile,
    TechnicalDocument,
    TechnicalIntakeDraft,
    TechnicalVariant,
    User,
)
from classifire.services.technical_intake_draft import (
    TECHNICAL_INTAKE_PAYLOAD_MAX_BYTES,
)
from classifire.technical_admin import router as technical_admin_router
from classifire.technical_admin import (
    technical_document_detail,
    technical_intake_draft_editor,
    technical_intake_draft_save,
    technical_intake_draft_start,
)
from classifire.ui import technical_page


@pytest.fixture(autouse=True)
def governed_storage_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Path]:
    root = tmp_path / "storage"
    monkeypatch.setenv("CLASSIFIRE_STORAGE_ROOT", str(root))
    get_settings.cache_clear()
    try:
        yield root
    finally:
        get_settings.cache_clear()


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _user(db: Session, email: str, *, role: str = "technical_reviewer") -> User:
    user = User(
        email=email,
        full_name=email.split("@", 1)[0],
        password_hash="not-used",
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def _request(
    user: User | None,
    path: str,
    *,
    method: str = "GET",
    csrf: str = "csrf-token",
) -> Request:
    session = {"csrf_token": csrf}
    if user is not None:
        session["user_id"] = user.id
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 1234),
            "server": ("testserver", 443),
            "session": session,
        }
    )


def _document(
    db: Session,
    *,
    uploaded_by: User,
    document_id: str = "REPORT-UI-001",
    database_id: str | None = None,
) -> tuple[TechnicalDocument, StoredFile, Path]:
    content = f"%PDF-1.7\nretained evidence {document_id}\n%%EOF".encode()
    digest = hashlib.sha256(content).hexdigest()
    root = get_settings().storage_root
    path = root / digest[:2] / digest[2:4] / f"{digest}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    stored = StoredFile(
        original_filename=f"{document_id}.pdf",
        media_type="application/pdf",
        storage_path=str(path),
        sha256=digest,
        size_bytes=len(content),
        purpose="technical_evidence",
        malware_scan_status="clean",
        uploaded_by_id=uploaded_by.id,
        immutable=True,
    )
    db.add(stored)
    db.flush()
    document = TechnicalDocument(
        **({"id": database_id} if database_id is not None else {}),
        document_id=document_id,
        stored_file_id=stored.id,
        document_type="test_report",
        title=f"Test report {document_id}",
        status="draft",
    )
    db.add(document)
    db.commit()
    return document, stored, path


def _payload(document: TechnicalDocument, stored: StoredFile) -> dict[str, object]:
    field_id = str(uuid4())
    locator_id = str(uuid4())
    return {
        "schema": "technical-intake-payload-v1",
        "fields": [
            {
                "row_id": field_id,
                "ordinal": 1,
                "field_key": "minimum_service_size_mm",
                "raw_value": "  Copied source wording.\r\n",
                "normalized_value": "20",
                "unit": "mm",
                "semantics": "minimum",
                "fact_state": "Provisional",
                "material": True,
                "limitation": None,
            }
        ],
        "locators": [
            {
                "row_id": locator_id,
                "technical_document_id": document.id,
                "source_sha256": stored.sha256,
                "source_size_bytes": stored.size_bytes,
                "physical_page": 12,
                "printed_page": "10",
                "section": None,
                "clause": "4.2",
                "table": "Table 3",
                "row": "Service 1",
                "column": "Diameter",
                "footnote": None,
                "figure": None,
                "drawing": None,
                "specimen": "A",
                "option": None,
                "callout": None,
                "excerpt": "  Exact supporting excerpt.\r\n",
                "region": None,
                "visual_verification": "required",
            }
        ],
        "links": [
            {
                "row_id": str(uuid4()),
                "field_row_id": field_id,
                "locator_row_id": locator_id,
                "evidence_role": "direct",
            }
        ],
    }


def _disabled_preview_settings(storage_root: Path) -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        storage_root=storage_root,
        technical_pdf_preview_enabled=False,
    )


def _draft_ui_app(db: Session, settings: Settings) -> FastAPI:
    test_app = FastAPI()
    test_app.add_middleware(
        SessionMiddleware,
        secret_key="technical-intake-draft-ui-test-secret",
    )

    def override_db() -> Iterator[Session]:
        yield db

    test_app.dependency_overrides[get_db] = override_db
    test_app.dependency_overrides[get_settings] = lambda: settings

    @test_app.get("/_draft-ui-login/{user_id}")
    def login(user_id: str, request: Request) -> dict[str, bool]:
        request.session["user_id"] = user_id
        request.session["csrf_token"] = "csrf-token"
        return {"ok": True}

    test_app.include_router(technical_admin_router)
    return test_app


def test_start_save_resume_reload_and_queue_remain_authority_neutral(
    db: Session,
    governed_storage_root: Path,
) -> None:
    author = _user(db, "author@example.test")
    document, stored, _path = _document(db, uploaded_by=author)
    start_path = f"/technical/documents/{document.id}/intake-draft"

    started = technical_intake_draft_start(
        document.id,
        _request(author, start_path, method="POST"),
        db,
        "csrf-token",
    )
    assert started.status_code == 303
    assert "Draft+started" in started.headers["location"]
    draft = db.scalar(select(TechnicalIntakeDraft))
    assert draft is not None

    resumed = technical_intake_draft_start(
        document.id,
        _request(author, start_path, method="POST"),
        db,
        "csrf-token",
    )
    assert resumed.status_code == 303
    assert resumed.headers["location"].startswith(
        f"/technical/intake-drafts/{draft.id}"
    )
    assert "Draft+resumed" in resumed.headers["location"]
    assert db.scalar(select(func.count()).select_from(TechnicalIntakeDraft)) == 1

    payload = _payload(document, stored)
    saved = technical_intake_draft_save(
        draft.id,
        _request(
            author,
            f"/technical/intake-drafts/{draft.id}",
            method="POST",
        ),
        db,
        "csrf-token",
        "1",
        json.dumps(payload, ensure_ascii=False),
        "Transcribed and linked the exact cited source row.",
    )
    assert saved.status_code == 303
    assert saved.headers["location"].endswith("?success=Draft+saved")
    db.expire_all()
    persisted = db.get(TechnicalIntakeDraft, draft.id)
    assert persisted is not None
    assert persisted.record_version == 2
    assert persisted.payload_json["fields"][0]["raw_value"] == (
        "  Copied source wording.\r\n"
    )

    page = technical_intake_draft_editor(
        persisted.id,
        _request(author, f"/technical/intake-drafts/{persisted.id}"),
        db,
        _disabled_preview_settings(governed_storage_root),
    )
    html = page.body.decode()
    assert page.headers["cache-control"] == "private, no-store, max-age=0"
    assert page.headers["pragma"] == "no-cache"
    assert page.headers["referrer-policy"] == "no-referrer"
    assert f'action="/technical/intake-drafts/{persisted.id}"' in html
    assert 'name="expected_record_version" value="2"' in html
    assert "Copied source wording" in html
    assert payload["fields"][0]["row_id"] in html
    assert payload["locators"][0]["row_id"] in html
    assert "Controlled preview is disabled" in html
    assert 'data-intake-physical-page required' in html
    assert 'src="/static/js/technical-intake-draft.js"' in html
    assert 'src="/static/js/technical-preview.js"' not in html

    landing = technical_page(_request(author, "/technical"), db)
    landing_html = landing.body.decode()
    assert "My technical intake Drafts" in landing_html
    assert f'/technical/intake-drafts/{persisted.id}' in landing_html
    assert document.document_id in landing_html

    detail = technical_document_detail(
        document.id,
        _request(author, f"/technical/documents/{document.id}"),
        db,
        _disabled_preview_settings(governed_storage_root),
    )
    detail_html = detail.body.decode()
    assert f'action="{start_path}"' in detail_html
    assert "Resume my Draft" in detail_html
    assert f"/technical/documents/{document.id}/variants/new" not in detail_html

    assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 0
    assert db.scalar(select(func.count()).select_from(Approval)) == 0
    assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 0
    save_audit = db.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_type == "technical_intake_draft",
            AuditEvent.entity_id == persisted.id,
            AuditEvent.action == "save",
        )
    )
    assert save_audit is not None
    assert save_audit.reason == "Transcribed and linked the exact cited source row."


def test_asgi_form_round_trip_starts_saves_and_resumes_exact_payload(
    db: Session,
    governed_storage_root: Path,
) -> None:
    author = _user(db, "browser-author@example.test")
    document, stored, _path = _document(
        db,
        uploaded_by=author,
        document_id="REPORT-BROWSER-001",
    )
    app = _draft_ui_app(
        db,
        _disabled_preview_settings(governed_storage_root),
    )
    payload = _payload(document, stored)

    with TestClient(app, base_url="https://testserver") as client:
        assert client.get(f"/_draft-ui-login/{author.id}").status_code == 200
        started = client.post(
            f"/technical/documents/{document.id}/intake-draft",
            data={"csrf_token": "csrf-token"},
            follow_redirects=False,
        )
        assert started.status_code == 303
        editor_location = started.headers["location"]
        editor = client.get(editor_location)
        assert editor.status_code == 200
        assert 'name="payload_json"' in editor.text
        draft = db.scalar(select(TechnicalIntakeDraft))
        assert draft is not None

        saved = client.post(
            f"/technical/intake-drafts/{draft.id}",
            data={
                "csrf_token": "csrf-token",
                "expected_record_version": "1",
                "payload_json": json.dumps(payload, ensure_ascii=False),
                "reason": "Browser form transcribed and linked the cited row.",
            },
            follow_redirects=False,
        )
        assert saved.status_code == 303
        assert saved.headers["location"].endswith("?success=Draft+saved")
        resumed = client.get(saved.headers["location"])
        assert resumed.status_code == 200
        assert "Copied source wording" in resumed.text
        assert 'name="expected_record_version" value="2"' in resumed.text

    assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 0
    assert db.scalar(select(func.count()).select_from(Approval)) == 0
    assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 0


def test_legacy_document_database_id_is_preserved_in_editor_and_payload(
    db: Session,
    governed_storage_root: Path,
) -> None:
    author = _user(db, "legacy-document-author@example.test")
    legacy_document_id = "legacy-technical-document-001"
    document, stored, _path = _document(
        db,
        uploaded_by=author,
        document_id="REPORT-LEGACY-001",
        database_id=legacy_document_id,
    )

    started = technical_intake_draft_start(
        legacy_document_id,
        _request(
            author,
            f"/technical/documents/{legacy_document_id}/intake-draft",
            method="POST",
        ),
        db,
        "csrf-token",
    )
    assert started.status_code == 303
    draft = db.scalar(select(TechnicalIntakeDraft))
    assert draft is not None
    assert draft.technical_document_id == legacy_document_id

    editor = technical_intake_draft_editor(
        draft.id,
        _request(author, f"/technical/intake-drafts/{draft.id}"),
        db,
        _disabled_preview_settings(governed_storage_root),
    )
    assert (
        f'data-technical-document-id="{legacy_document_id}"'
        in editor.body.decode()
    )

    payload = _payload(document, stored)
    assert payload["locators"][0]["technical_document_id"] == legacy_document_id
    saved = technical_intake_draft_save(
        draft.id,
        _request(
            author,
            f"/technical/intake-drafts/{draft.id}",
            method="POST",
        ),
        db,
        "csrf-token",
        "1",
        json.dumps(payload),
        "Preserve the exact legacy source-record identifier.",
    )
    assert saved.headers["location"].endswith("?success=Draft+saved")
    db.expire_all()
    persisted = db.get(TechnicalIntakeDraft, draft.id)
    assert persisted is not None
    assert persisted.payload_json["locators"][0][
        "technical_document_id"
    ] == legacy_document_id


def test_permissions_csrf_owner_isolation_and_blank_reason_fail_closed(
    db: Session,
    governed_storage_root: Path,
) -> None:
    author = _user(db, "author@example.test")
    other = _user(db, "other@example.test")
    reader = _user(db, "reader@example.test", role="read_only")
    document, stored, _path = _document(db, uploaded_by=author)
    start_path = f"/technical/documents/{document.id}/intake-draft"

    with pytest.raises(HTTPException) as bad_csrf:
        technical_intake_draft_start(
            document.id,
            _request(author, start_path, method="POST"),
            db,
            "wrong-token",
        )
    assert bad_csrf.value.status_code == 403
    with pytest.raises(HTTPException) as forbidden:
        technical_intake_draft_start(
            document.id,
            _request(reader, start_path, method="POST"),
            db,
            "csrf-token",
        )
    assert forbidden.value.status_code == 403

    technical_intake_draft_start(
        document.id,
        _request(author, start_path, method="POST"),
        db,
        "csrf-token",
    )
    draft = db.scalar(select(TechnicalIntakeDraft))
    assert draft is not None
    draft_path = f"/technical/intake-drafts/{draft.id}"

    with pytest.raises(HTTPException) as other_owner:
        technical_intake_draft_editor(
            draft.id,
            _request(other, draft_path),
            db,
            _disabled_preview_settings(governed_storage_root),
        )
    with pytest.raises(HTTPException) as absent:
        technical_intake_draft_editor(
            str(uuid4()),
            _request(other, draft_path),
            db,
            _disabled_preview_settings(governed_storage_root),
        )
    assert (other_owner.value.status_code, other_owner.value.detail) == (
        absent.value.status_code,
        absent.value.detail,
    ) == (404, "Technical intake Draft not found")

    with pytest.raises(HTTPException) as other_save:
        technical_intake_draft_save(
            draft.id,
            _request(other, draft_path, method="POST"),
            db,
            "csrf-token",
            "1",
            json.dumps(_payload(document, stored)),
            "Attempted cross-owner save",
        )
    assert (other_save.value.status_code, other_save.value.detail) == (
        404,
        "Technical intake Draft not found",
    )

    blank_reason = technical_intake_draft_save(
        draft.id,
        _request(author, draft_path, method="POST"),
        db,
        "csrf-token",
        "1",
        json.dumps(_payload(document, stored)),
        " \r\n ",
    )
    assert blank_reason.status_code == 422
    blank_reason_html = blank_reason.body.decode()
    assert "TECHNICAL_INTAKE_DRAFT_REASON_INVALID" in blank_reason_html
    assert f'href="{draft_path}"' in blank_reason_html
    assert "Nothing was saved" in blank_reason_html
    db.refresh(draft)
    assert draft.record_version == 1
    assert draft.payload_json["fields"] == []

    first_payload = _payload(document, stored)
    first_save = technical_intake_draft_save(
        draft.id,
        _request(author, draft_path, method="POST"),
        db,
        "csrf-token",
        "1",
        json.dumps(first_payload),
        "Save the first exact source-bound transcription.",
    )
    assert first_save.headers["location"].endswith("?success=Draft+saved")
    stale_payload = json.loads(json.dumps(first_payload))
    rejected_marker = '</textarea><script>window.rejectedPayloadRan=true</script>'
    stale_payload["fields"][0]["normalized_value"] = rejected_marker
    stale_payload_json = json.dumps(stale_payload)
    db.expire_all()
    before_stale = db.get(TechnicalIntakeDraft, draft.id)
    assert before_stale is not None
    before_stale_hash = before_stale.payload_sha256
    save_audits_before = db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.entity_type == "technical_intake_draft",
            AuditEvent.entity_id == draft.id,
            AuditEvent.action == "save",
        )
    )
    stale = technical_intake_draft_save(
        draft.id,
        _request(author, draft_path, method="POST"),
        db,
        "csrf-token",
        "1",
        stale_payload_json,
        "Attempt a stale-tab overwrite.",
    )
    assert stale.status_code == 409
    assert stale.headers["cache-control"] == "private, no-store, max-age=0"
    assert stale.headers["pragma"] == "no-cache"
    assert stale.headers["referrer-policy"] == "no-referrer"
    stale_html = stale.body.decode()
    assert "TECHNICAL_INTAKE_DRAFT_STALE" in stale_html
    assert "older copy of the Draft" in stale_html
    assert f'href="{draft_path}"' in stale_html
    assert rejected_marker not in stale_html
    assert (
        "&lt;/textarea&gt;&lt;script&gt;window.rejectedPayloadRan=true"
        "&lt;/script&gt;"
    ) in stale_html
    db.expire_all()
    current = db.get(TechnicalIntakeDraft, draft.id)
    assert current is not None
    assert current.record_version == 2
    assert current.payload_json["fields"][0]["normalized_value"] == "20"
    assert current.payload_sha256 == before_stale_hash
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.entity_type == "technical_intake_draft",
                AuditEvent.entity_id == draft.id,
                AuditEvent.action == "save",
            )
        )
        == save_audits_before
    )

    replay = technical_intake_draft_save(
        draft.id,
        _request(author, draft_path, method="POST"),
        db,
        "csrf-token",
        "1",
        json.dumps(first_payload),
        "Retry the exact already-saved payload.",
    )
    assert replay.status_code == 303
    assert replay.headers["location"].endswith("?success=Draft+already+saved")

    other_landing = technical_page(_request(other, "/technical"), db)
    assert draft.id not in other_landing.body.decode()
    assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 0
    assert db.scalar(select(func.count()).select_from(Approval)) == 0
    assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 0


def test_rejected_save_recovery_is_owner_private_and_size_bounded(
    db: Session,
    governed_storage_root: Path,
) -> None:
    author = _user(db, "recovery-author@example.test")
    other = _user(db, "recovery-other@example.test")
    document, _stored, _path = _document(
        db,
        uploaded_by=author,
        document_id="REPORT-RECOVERY-001",
    )
    technical_intake_draft_start(
        document.id,
        _request(
            author,
            f"/technical/documents/{document.id}/intake-draft",
            method="POST",
        ),
        db,
        "csrf-token",
    )
    draft = db.scalar(select(TechnicalIntakeDraft))
    assert draft is not None
    draft_path = f"/technical/intake-drafts/{draft.id}"
    initial_hash = draft.payload_sha256
    initial_audit_count = db.scalar(
        select(func.count()).select_from(AuditEvent)
    )
    app = _draft_ui_app(
        db,
        _disabled_preview_settings(governed_storage_root),
    )

    with TestClient(app, base_url="https://testserver") as client:
        assert client.get(f"/_draft-ui-login/{other.id}").status_code == 200
        cross_owner_marker = "CROSS_OWNER_REJECTED_PAYLOAD_SECRET"
        cross_owner = client.post(
            draft_path,
            data={
                "csrf_token": "csrf-token",
                "expected_record_version": "not-a-version",
                "payload_json": cross_owner_marker,
                "reason": "Must remain private.",
            },
            follow_redirects=False,
        )
        assert cross_owner.status_code == 404
        assert cross_owner_marker not in cross_owner.text
        assert "Recover your unsaved work" not in cross_owner.text

        assert client.get(f"/_draft-ui-login/{author.id}").status_code == 200
        bounded_marker = '<script>window.invalidPayloadRan=true</script>'
        invalid_precheck = client.post(
            draft_path,
            data={
                "csrf_token": "csrf-token",
                "expected_record_version": "not-a-version",
                "payload_json": bounded_marker,
                "reason": "Recover a bounded invalid submission.",
            },
            follow_redirects=False,
        )
        assert invalid_precheck.status_code == 409
        assert (
            invalid_precheck.headers["cache-control"]
            == "private, no-store, max-age=0"
        )
        assert invalid_precheck.headers["pragma"] == "no-cache"
        assert invalid_precheck.headers["referrer-policy"] == "no-referrer"
        assert bounded_marker not in invalid_precheck.text
        assert (
            "&lt;script&gt;window.invalidPayloadRan=true&lt;/script&gt;"
            in invalid_precheck.text
        )
        assert f'href="{draft_path}"' in invalid_precheck.text

        validation_marker = (
            '{"broken":"</textarea><script>'
            'window.validationPayloadRan=true</script>"'
        )
        validation_rejection = client.post(
            draft_path,
            data={
                "csrf_token": "csrf-token",
                "expected_record_version": "1",
                "payload_json": validation_marker,
                "reason": "Recover a bounded validation rejection.",
            },
            follow_redirects=False,
        )
        assert validation_rejection.status_code == 422
        assert (
            "TECHNICAL_INTAKE_DRAFT_JSON_INVALID"
            in validation_rejection.text
        )
        assert validation_marker not in validation_rejection.text
        assert (
            "&lt;/textarea&gt;&lt;script&gt;"
            "window.validationPayloadRan=true&lt;/script&gt;"
            in validation_rejection.text
        )

        oversized_marker = "OVERSIZED_REJECTED_PAYLOAD_SECRET"
        oversized_payload = (
            oversized_marker
            + "x" * TECHNICAL_INTAKE_PAYLOAD_MAX_BYTES
        )
        oversized = client.post(
            draft_path,
            data={
                "csrf_token": "csrf-token",
                "expected_record_version": "1",
                "payload_json": oversized_payload,
                "reason": "Reject an oversized submission.",
            },
            follow_redirects=False,
        )
        assert oversized.status_code == 400
        assert oversized_marker not in oversized.text
        assert "<textarea" not in oversized.text

    direct_oversized = technical_intake_draft_save(
        draft.id,
        _request(author, draft_path, method="POST"),
        db,
        "csrf-token",
        "1",
        oversized_payload,
        "Reject an oversized submission.",
    )
    assert direct_oversized.status_code == 422
    direct_oversized_html = direct_oversized.body.decode()
    assert (
        "TECHNICAL_INTAKE_DRAFT_PAYLOAD_TOO_LARGE"
        in direct_oversized_html
    )
    assert "larger than the safe display limit" in direct_oversized_html
    assert oversized_marker not in direct_oversized_html
    assert "<textarea" not in direct_oversized_html

    unencodable_marker = "\ud800UNENCODABLE_REJECTED_PAYLOAD_SECRET"
    unencodable = technical_intake_draft_save(
        draft.id,
        _request(author, draft_path, method="POST"),
        db,
        "csrf-token",
        "1",
        unencodable_marker,
        "Reject text that cannot be encoded as UTF-8.",
    )
    assert unencodable.status_code == 422
    unencodable_html = unencodable.body.decode()
    assert "TECHNICAL_INTAKE_DRAFT_JSON_INVALID" in unencodable_html
    assert "could not be safely encoded as UTF-8" in unencodable_html
    assert "UNENCODABLE_REJECTED_PAYLOAD_SECRET" not in unencodable_html
    assert "<textarea" not in unencodable_html

    db.expire_all()
    current = db.get(TechnicalIntakeDraft, draft.id)
    assert current is not None
    assert current.record_version == 1
    assert current.payload_sha256 == initial_hash
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == (
        initial_audit_count
    )


def test_invalid_persisted_payload_never_initializes_the_editor(
    db: Session,
    governed_storage_root: Path,
) -> None:
    author = _user(db, "author@example.test")
    document, _stored, _path = _document(db, uploaded_by=author)
    technical_intake_draft_start(
        document.id,
        _request(
            author,
            f"/technical/documents/{document.id}/intake-draft",
            method="POST",
        ),
        db,
        "csrf-token",
    )
    draft = db.scalar(select(TechnicalIntakeDraft))
    assert draft is not None
    draft.payload_json = {
        "schema": "technical-intake-payload-v1",
        "fields": [{"search_eligibility": "active"}],
        "locators": [],
        "links": [],
    }
    db.commit()

    with pytest.raises(HTTPException) as corrupted:
        technical_intake_draft_editor(
            draft.id,
            _request(author, f"/technical/intake-drafts/{draft.id}"),
            db,
            _disabled_preview_settings(governed_storage_root),
        )
    assert (corrupted.value.status_code, corrupted.value.detail) == (
        503,
        "TECHNICAL_INTAKE_DRAFT_PERSISTENCE_CONFLICT",
    )


def test_editor_preview_binding_and_disabled_manual_fallback(
    db: Session,
    governed_storage_root: Path,
) -> None:
    author = _user(db, "author@example.test")
    document, stored, _path = _document(db, uploaded_by=author)
    technical_intake_draft_start(
        document.id,
        _request(
            author,
            f"/technical/documents/{document.id}/intake-draft",
            method="POST",
        ),
        db,
        "csrf-token",
    )
    draft = db.scalar(select(TechnicalIntakeDraft))
    assert draft is not None
    enabled = Settings(
        _env_file=None,
        env="test",
        storage_root=governed_storage_root,
        technical_pdf_preview_enabled=True,
    )

    preview_page = technical_intake_draft_editor(
        draft.id,
        _request(author, f"/technical/intake-drafts/{draft.id}"),
        db,
        enabled,
    )
    preview_html = preview_page.body.decode()
    assert 'data-technical-pdf-preview' in preview_html
    assert f'data-source-sha256="{stored.sha256}"' in preview_html
    assert f'data-source-size="{stored.size_bytes}"' in preview_html
    assert (
        f'/technical/documents/{document.id}/preview/{stored.sha256}/pages/'
        in preview_html
    )
    assert preview_html.index("technical-intake-draft.js") < preview_html.index(
        "technical-preview.js"
    )
    assert "Use verified page" in preview_html
    assert "<iframe" not in preview_html.casefold()
    assert "<object" not in preview_html.casefold()
    assert "<embed" not in preview_html.casefold()
    for forbidden_name in (
        "status",
        "search_eligibility",
        "release_id",
        "expert_review_required",
    ):
        assert f'name="{forbidden_name}"' not in preview_html

    disabled_page = technical_intake_draft_editor(
        draft.id,
        _request(author, f"/technical/intake-drafts/{draft.id}"),
        db,
        _disabled_preview_settings(governed_storage_root),
    )
    disabled_html = disabled_page.body.decode()
    assert "Controlled preview is disabled" in disabled_html
    assert "enter its physical PDF page" in disabled_html
    assert 'data-intake-physical-page required' in disabled_html
    assert 'src="/static/js/technical-preview.js"' not in disabled_html


def test_draft_javascript_contracts_and_verified_preview_event() -> None:
    repository_root = Path(__file__).parents[1]
    draft_script = (
        repository_root
        / "src"
        / "classifire"
        / "static"
        / "js"
        / "technical-intake-draft.js"
    )
    preview_script = (
        repository_root
        / "src"
        / "classifire"
        / "static"
        / "js"
        / "technical-preview.js"
    )
    source = draft_script.read_text(encoding="utf-8")
    preview_source = preview_script.read_text(encoding="utf-8")
    assert 'schema: "technical-intake-payload-v1"' in source
    assert "crypto.randomUUID" in source
    assert "fields," in source
    assert "locators:" in source
    assert "links:" in source
    assert "sourceValueOrNull" in source
    assert "retainedSourceValue" in source
    assert "normalizedTextareaValue" in source
    assert "failInitialization()" in source
    assert "data-intake-use-verified-page" in source
    assert "classifire:technical-preview-page-verified" in source
    assert "uuid4Pattern.test(technicalDocumentId)" not in source
    assert "technicalDocumentId.length > 36" in source
    assert "technicalDocumentId !== technicalDocumentId.trim()" in source
    assert "new CustomEvent(verifiedPageEvent" in preview_source
    assert preview_source.index("actualBindingSha256 !== receipt.bindingSha256") < (
        preview_source.index("host.dispatchEvent(new CustomEvent")
    )
    assert preview_source.index("await image.decode()") < preview_source.index(
        "host.dispatchEvent(new CustomEvent"
    )

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable for Draft JavaScript verification")
    for script in (draft_script, preview_script):
        syntax = subprocess.run(  # noqa: S603
            (node, "--check", str(script)),
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert syntax.returncode == 0, syntax.stderr
    harness = (
        repository_root
        / "tests"
        / "js"
        / "technical_preview_verified_page_harness.cjs"
    )
    verified_event = subprocess.run(  # noqa: S603
        (node, str(harness), str(preview_script)),
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert verified_event.returncode == 0, verified_event.stderr
    source_value_harness = (
        repository_root
        / "tests"
        / "js"
        / "technical_intake_draft_source_value_harness.cjs"
    )
    source_value = subprocess.run(  # noqa: S603
        (node, str(source_value_harness), str(draft_script)),
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert source_value.returncode == 0, source_value.stderr
