from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from typing import BinaryIO

import pytest
from fastapi import HTTPException, UploadFile
from physical_foundation_support import physical_session
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from starlette.datastructures import FormData, Headers
from starlette.formparsers import MultiPartException
from starlette.requests import Request

from classifire import physical_models as _physical_models  # noqa: F401
from classifire.config import Settings
from classifire.db import Base
from classifire.models import (
    AuditEvent,
    StoredFile,
    TechnicalDocument,
    TechnicalDocumentRelationship,
    TechnicalIntakeBatchItem,
    User,
)
from classifire.services import storage as storage_service
from classifire.services.malware_scanning import (
    CLEAN_VERDICT,
    MalwareDetectedError,
    MalwareScanResult,
)
from classifire.services.technical_intake import (
    TECHNICAL_DOCUMENT_TYPE_LABELS,
    TECHNICAL_DOCUMENT_TYPE_OPTIONS,
    TECHNICAL_DOCUMENT_TYPES,
    TECHNICAL_LEGACY_DOCUMENT_TYPE_LABELS,
    TechnicalIntakeError,
    create_technical_document_draft,
)
from classifire.services.technical_intake_batch import (
    TECHNICAL_INTAKE_CLAIM_TTL,
    create_technical_intake_batch,
)
from classifire.ui import technical_page, technical_upload
from classifire.upload_ingress import TECHNICAL_UPLOAD_MULTIPART_OVERHEAD_BYTES

technical_intake_service = importlib.import_module("classifire.services.technical_intake")
ui_module = importlib.import_module("classifire.ui")
upload_preflight_service = importlib.import_module(
    "classifire.services.technical_upload_preflight"
)


class _ContentScanner:
    def __init__(self) -> None:
        self.calls: list[bytes] = []

    def scan_stream(self, stream: BinaryIO) -> MalwareScanResult:
        payload = stream.read()
        self.calls.append(payload)
        if b"MALWARE" in payload:
            raise MalwareDetectedError()
        return MalwareScanResult(
            CLEAN_VERDICT,
            hashlib.sha256(payload).hexdigest(),
            len(payload),
        )


def _settings(tmp_path: Path, *, scanner_host: str | None = "scanner.internal") -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        storage_root=tmp_path / "storage",
        clamav_host=scanner_host,
        max_upload_mb=1,
    )


def _pdf(label: str) -> bytes:
    return b"%PDF-1.7\n" + label.encode("ascii") + b"\n%%EOF\n"


def _upload(payload: bytes, filename: str = "report.pdf") -> UploadFile:
    return UploadFile(
        BytesIO(payload),
        filename=filename,
        headers=Headers({"content-type": "application/pdf"}),
    )


def _user(db, *, role: str = "administrator") -> User:
    user = User(
        email=f"{role}@upload.example.test",
        full_name="Technical Upload Test",
        password_hash="not-used-in-direct-route-test",  # noqa: S106
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _request(
    user: User,
    *,
    method: str = "POST",
    accept: str = "application/json",
    csrf: str = "technical-upload-csrf",
    csrf_header: str | None = "technical-upload-csrf",
    content_type: str | None = "multipart/form-data; boundary=technical-upload-test",
    content_length_values: tuple[str, ...] = ("1",),
    batch_id_headers: tuple[str, ...] = (),
    item_id_headers: tuple[str, ...] = (),
    form: FormData | None = None,
    forbid_body: bool = False,
) -> Request:
    headers = [(b"accept", accept.encode("ascii"))]
    if csrf_header is not None:
        headers.append((b"x-csrf-token", csrf_header.encode("ascii")))
    if content_type is not None:
        headers.append((b"content-type", content_type.encode("ascii")))
    headers.extend(
        (b"content-length", value.encode("ascii"))
        for value in content_length_values
    )
    headers.extend(
        (b"x-classifire-intake-batch-id", value.encode("ascii"))
        for value in batch_id_headers
    )
    headers.extend(
        (b"x-classifire-intake-item-id", value.encode("ascii"))
        for value in item_id_headers
    )

    async def receive() -> dict[str, object]:
        if forbid_body:
            raise AssertionError("Multipart body was parsed before authentication")
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": "/technical/upload",
            "raw_path": b"/technical/upload",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 443),
            "session": {"user_id": user.id, "csrf_token": csrf},
        },
        receive=receive,
    )
    if form is not None:
        request._form = form
    return request


def _ui_form(
    upload: UploadFile,
    document_id: str,
    title: str,
    *,
    document_type: str = "fire_test_report",
    declared_source_role: str = "primary_test",
    artifact_provenance_status: str = "unknown",
    evidence_scope: str = "full_source",
    manufacturer: str = "",
    reference: str = "",
    revision: str = "",
    sponsor_organisation: str = "",
    issuing_organisation: str = "",
    publication_date: str = "",
    review_date: str = "",
    expiry_date: str = "",
    jurisdiction: str = "",
    standards: str = "",
    artifact_provenance_note: str = "",
    evidence_limitations: str = "",
    batch_id: str | None = None,
    relationship_type: str = "",
    related_document_id: str = "",
    relationship_reason: str = "",
    relationship_scope: str = "",
    relationship_effective_date: str = "",
) -> FormData:
    entries: list[tuple[str, object]] = [
            ("file", upload),
            ("document_id", document_id),
            ("document_type", document_type),
            ("declared_source_role", declared_source_role),
            ("artifact_provenance_status", artifact_provenance_status),
            ("evidence_scope", evidence_scope),
            ("title", title),
            ("manufacturer", manufacturer),
            ("reference", reference),
            ("revision", revision),
            ("sponsor_organisation", sponsor_organisation),
            ("issuing_organisation", issuing_organisation),
            ("publication_date", publication_date),
            ("review_date", review_date),
            ("expiry_date", expiry_date),
            ("jurisdiction", jurisdiction),
            ("standards", standards),
            ("artifact_provenance_note", artifact_provenance_note),
            ("evidence_limitations", evidence_limitations),
            ("relationship_type", relationship_type),
            ("related_document_id", related_document_id),
            ("relationship_reason", relationship_reason),
            ("relationship_scope", relationship_scope),
            ("relationship_effective_date", relationship_effective_date),
        ]
    if batch_id is not None:
        entries.append(("batch_id", batch_id))
    return FormData(entries)


def _create_batch_slot(
    db: Session,
    settings: Settings,
    actor: User,
    *,
    document_id: str = "DOC-PREFLIGHT-BATCH",
    filename: str = "preflight-report.pdf",
    size_bytes: int = 1024,
):
    return create_technical_intake_batch(
        db,
        settings,
        actor=actor,
        client_request_id="11111111-1111-4111-8111-111111111111",
        items=[
            {
                "client_item_id": "22222222-2222-4222-8222-222222222222",
                "expected_sha256": "a" * 64,
                "filename": filename,
                "ordinal": 1,
                "registration": {
                    "artifact_provenance_note": None,
                    "artifact_provenance_status": "unknown",
                    "declared_source_role": "primary_test",
                    "document_id": document_id,
                    "document_type": "fire_test_report",
                    "evidence_limitations": None,
                    "evidence_scope": "full_source",
                    "expiry_date": None,
                    "issuing_organisation": "Example Test Laboratory",
                    "jurisdiction": "Australia",
                    "manufacturer": "Example Manufacturer",
                    "publication_date": "2026-08-01",
                    "reference": document_id,
                    "related_document_id": None,
                    "relationship_effective_date": None,
                    "relationship_reason": None,
                    "relationship_scope": None,
                    "relationship_type": None,
                    "review_date": None,
                    "revision": "R1",
                    "sponsor_organisation": "Example Sponsor",
                    "standards": ["AS 1530.4:2014"],
                    "title": f"Report {document_id}",
                },
                "size_bytes": size_bytes,
            }
        ],
        source_ip="127.0.0.1",
    )


def _install_ui_batch_preflight_state(
    monkeypatch: pytest.MonkeyPatch,
    *,
    status: str,
    outcome_retryable: bool | None,
    attempt_started_at: datetime | None,
) -> tuple[str, str]:
    batch_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    item_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"

    def owned_batch(
        _db: Session,
        *,
        actor: User,
        batch_id: object,
    ) -> tuple[object, tuple[object, ...]]:
        assert actor.is_active is True
        assert batch_id == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        return (
            SimpleNamespace(id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            (
                SimpleNamespace(
                    id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                    declared_size_bytes=1024,
                    status=status,
                    outcome_retryable=outcome_retryable,
                    attempt_started_at=attempt_started_at,
                ),
            ),
        )

    monkeypatch.setattr(
        upload_preflight_service,
        "get_owned_technical_intake_batch",
        owned_batch,
    )
    return batch_id, item_id


def _call_ui_upload(request: Request, db, settings: Settings):
    return asyncio.run(technical_upload(request, db, settings))


def _install_scanner(
    monkeypatch: pytest.MonkeyPatch,
    scanner: _ContentScanner,
) -> None:
    monkeypatch.setattr(
        storage_service,
        "configured_malware_scanner",
        lambda _settings: scanner,
    )


def _file_backed_sessions(tmp_path: Path) -> tuple[Engine, sessionmaker[Session]]:
    database_path = tmp_path / "technical-intake-transactions.sqlite3"
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        connection.commit()
    Base.metadata.create_all(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)


def _fail_document_flush(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
) -> None:
    real_flush = db.flush

    def fail_technical_document_flush(*args, **kwargs):
        if any(isinstance(record, TechnicalDocument) for record in db.new):
            raise OperationalError(
                "simulated pre-commit document flush failure",
                {},
                RuntimeError("simulated database failure"),
            )
        return real_flush(*args, **kwargs)

    monkeypatch.setattr(db, "flush", fail_technical_document_flush)


def _create(
    db,
    settings: Settings,
    actor: User,
    *,
    payload: bytes,
    document_id: str,
    batch_id: str = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    document_type: str = "fire_test_report",
    declared_source_role: str = "primary_test",
    evidence_scope: str = "full_source",
):
    return create_technical_document_draft(
        db,
        settings,
        actor=actor,
        upload=_upload(payload, f"{document_id}.pdf"),
        document_id=document_id,
        document_type=document_type,
        declared_source_role=declared_source_role,
        artifact_provenance_status="unknown",
        evidence_scope=evidence_scope,
        title=f"Report {document_id}",
        manufacturer="Example manufacturer",
        correlation_id=batch_id,
        source_ip="127.0.0.1",
    )


EXPECTED_NEW_TECHNICAL_DOCUMENT_TYPE_OPTIONS = (
    ("fire_test_report", "Full Fire Test Report"),
    ("regulatory_information_report", "Regulatory Information Report"),
    ("fire_assessment", "Fire Assessment Report"),
    ("extended_application_report", "Extended Application Report"),
    ("field_of_application_report", "Field of Application Report"),
    (
        "fire_engineering_report_performance_solution",
        "Fire Engineering Report or Performance Solution",
    ),
    (
        "certificate_summary_of_assessment",
        "Certificate or Summary of Assessment",
    ),
    ("test_certificate", "Test Certificate"),
)


def test_technical_document_catalogue_exposes_eight_new_upload_families():
    assert TECHNICAL_DOCUMENT_TYPE_OPTIONS == (
        EXPECTED_NEW_TECHNICAL_DOCUMENT_TYPE_OPTIONS
    )
    assert set(dict(TECHNICAL_DOCUMENT_TYPE_OPTIONS)) <= (
        TECHNICAL_DOCUMENT_TYPES
    )
    assert set(TECHNICAL_LEGACY_DOCUMENT_TYPE_LABELS) <= (
        TECHNICAL_DOCUMENT_TYPES
    )
    assert not set(TECHNICAL_LEGACY_DOCUMENT_TYPE_LABELS) & set(
        dict(TECHNICAL_DOCUMENT_TYPE_OPTIONS)
    )
    assert all(
        TECHNICAL_DOCUMENT_TYPE_LABELS[value] == label
        for value, label in EXPECTED_NEW_TECHNICAL_DOCUMENT_TYPE_OPTIONS
    )


@pytest.mark.parametrize(
    ("document_type", "declared_source_role", "evidence_scope"),
    [
        ("fire_test_report", "primary_test", "full_source"),
        ("regulatory_information_report", "regulatory_summary", "summary_only"),
        ("fire_assessment", "assessment", "full_source"),
        ("extended_application_report", "assessment", "full_source"),
        ("field_of_application_report", "assessment", "full_source"),
        (
            "fire_engineering_report_performance_solution",
            "assessment",
            "full_source",
        ),
        ("certificate_summary_of_assessment", "assessment", "full_source"),
        ("test_certificate", "primary_test", "full_source"),
    ],
)
def test_each_new_report_family_is_accepted_and_persisted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    document_type: str,
    declared_source_role: str,
    evidence_scope: str,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    payload = _pdf(f"synthetic-{document_type}")

    with physical_session() as db:
        actor = _user(db)
        result = _create(
            db,
            _settings(tmp_path),
            actor,
            payload=payload,
            document_id=f"DOC-FAMILY-{document_type.upper()}",
            document_type=document_type,
            declared_source_role=declared_source_role,
            evidence_scope=evidence_scope,
        )

        assert result.document.document_type == document_type
        assert db.get(TechnicalDocument, result.document.id) is not None
        assert result.document.status == "draft"
        assert scanner.calls == [payload]


def test_clean_upload_is_bound_draft_and_extraction_is_deferred(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    parser_calls: list[Path] = []
    monkeypatch.setattr(
        "classifire.services.technical.extract_pdf_candidate_metadata",
        lambda path: parser_calls.append(path),
    )

    with physical_session() as db:
        actor = _user(db)
        result = _create(
            db,
            _settings(tmp_path),
            actor,
            payload=_pdf("clean-one"),
            document_id="DOC-CLEAN-001",
        )

        assert result.document.status == "draft"
        assert result.document.extraction_status == "awaiting_safe_extraction"
        assert result.document.metadata_json["extraction_deferred_code"] == (
            "ISOLATED_PARSER_REQUIRED"
        )
        assert result.stored_file.malware_scan_status == "clean"
        assert result.stored_file.immutable is True
        assert result.stored_file.sha256 == hashlib.sha256(_pdf("clean-one")).hexdigest()
        assert Path(result.stored_file.storage_path).read_bytes() == _pdf("clean-one")
        assert scanner.calls == [_pdf("clean-one")]
        assert parser_calls == []
        assert not list(settings_path(tmp_path).rglob("*.part"))

        event = db.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "upload",
                AuditEvent.entity_id == result.document.id,
            )
        )
        assert event is not None
        assert event.correlation_id == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        assert event.new_value["malware_scan_status"] == "clean"


def settings_path(tmp_path: Path) -> Path:
    return tmp_path / "storage"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (_pdf("MALWARE"), "MALWARE_DETECTED"),
        (b"not really a pdf", "UPLOAD_CONTENT_SIGNATURE_INVALID"),
        (b"", "UPLOAD_FILE_EMPTY"),
    ],
)
def test_rejected_upload_leaves_no_document_file_or_quarantine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
    expected: str,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)

    with physical_session() as db:
        actor = _user(db)
        with pytest.raises(TechnicalIntakeError) as caught:
            _create(
                db,
                _settings(tmp_path),
                actor,
                payload=payload,
                document_id=f"DOC-{expected}",
            )

        assert caught.value.code == expected
        assert list(db.scalars(select(StoredFile)).all()) == []
        assert list(db.scalars(select(TechnicalDocument)).all()) == []
        assert not list(settings_path(tmp_path).rglob("*.part"))
        retained = [
            path
            for path in settings_path(tmp_path).rglob("*")
            if path.is_file()
        ]
        assert retained == []
        rejection = db.scalar(
            select(AuditEvent).where(AuditEvent.action == "upload_rejected")
        )
        assert rejection is not None
        assert rejection.new_value["outcome"] == expected


@pytest.mark.parametrize(
    ("form_overrides", "expected"),
    [
        (
            {
                "artifact_provenance_status": "transformed_derivative",
                "artifact_provenance_note": "",
            },
            "ARTIFACT_PROVENANCE_NOTE_REQUIRED",
        ),
        (
            {"declared_source_role": "not-a-source-role"},
            "SOURCE_ROLE_INVALID",
        ),
        (
            {"artifact_provenance_status": "not-a-provenance-status"},
            "ARTIFACT_PROVENANCE_INVALID",
        ),
        (
            {"evidence_scope": "not-an-evidence-scope"},
            "EVIDENCE_SCOPE_INVALID",
        ),
        (
            {
                "document_type": "regulatory_information_report",
                "declared_source_role": "assessment",
                "evidence_scope": "full_source",
            },
            "SOURCE_CLASSIFICATION_INVALID",
        ),
    ],
)
def test_ui_rejects_invalid_source_registration_before_scanner_or_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    form_overrides: dict[str, str],
    expected: str,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    values = {
        "document_type": "fire_test_report",
        "declared_source_role": "primary_test",
        "artifact_provenance_status": "unknown",
        "evidence_scope": "full_source",
        "artifact_provenance_note": "",
    }
    values.update(form_overrides)

    with physical_session() as db:
        actor = _user(db)
        response = _call_ui_upload(
            _request(
                actor,
                form=_ui_form(
                    _upload(_pdf("not-scanned")),
                    f"DOC-{expected}",
                    "Invalid source registration",
                    **values,
                ),
            ),
            db,
            _settings(tmp_path),
        )

        assert response.status_code == 422
        assert json.loads(response.body)["code"] == expected
        assert scanner.calls == []
        assert list(db.scalars(select(StoredFile)).all()) == []
        assert list(db.scalars(select(TechnicalDocument)).all()) == []
        rejection = db.scalar(
            select(AuditEvent).where(AuditEvent.action == "upload_rejected")
        )
        assert rejection is not None
        assert rejection.new_value["outcome"] == expected


def test_missing_scanner_fails_before_staging(
    tmp_path: Path,
) -> None:
    with physical_session() as db:
        actor = _user(db)
        with pytest.raises(TechnicalIntakeError) as caught:
            _create(
                db,
                _settings(tmp_path, scanner_host=None),
                actor,
                payload=_pdf("clean-but-no-scanner"),
                document_id="DOC-NO-SCANNER",
            )

        assert caught.value.code == "MALWARE_SCANNER_REQUIRED"
        assert caught.value.status_code == 503
        assert not list(settings_path(tmp_path).rglob("*.part"))
        assert list(db.scalars(select(StoredFile)).all()) == []


def test_duplicate_document_id_is_rejected_before_second_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)

    with physical_session() as db:
        actor = _user(db)
        _create(
            db,
            _settings(tmp_path),
            actor,
            payload=_pdf("first"),
            document_id="DOC-DUPLICATE",
        )
        with pytest.raises(TechnicalIntakeError) as caught:
            _create(
                db,
                _settings(tmp_path),
                actor,
                payload=_pdf("second"),
                document_id="DOC-DUPLICATE",
            )

        assert caught.value.code == "DOCUMENT_ID_ALREADY_EXISTS"
        assert scanner.calls == [_pdf("first")]
        assert db.scalar(select(func.count()).select_from(TechnicalDocument)) == 1


def test_clean_dedup_reuses_verified_blob_but_keeps_both_document_audits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    payload = _pdf("shared-clean-bytes")

    with physical_session() as db:
        actor = _user(db)
        second_actor = _user(db, role="technical_reviewer")
        first = _create(
            db,
            _settings(tmp_path),
            actor,
            payload=payload,
            document_id="DOC-SHARED-1",
        )
        second = _create(
            db,
            _settings(tmp_path),
            second_actor,
            payload=payload,
            document_id="DOC-SHARED-2",
        )

        assert first.stored_file.id == second.stored_file.id
        assert len(scanner.calls) == 2
        assert db.scalar(select(func.count()).select_from(StoredFile)) == 1
        assert db.scalar(select(func.count()).select_from(TechnicalDocument)) == 2
        assert db.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "upload")
        ) == 2
        assert first.document.metadata_json["exact_content_duplicate_document_ids"] == []
        assert second.document.metadata_json["exact_content_duplicate_document_ids"] == [
            first.document.document_id
        ]
        assert first.document.metadata_json["upload_original_filename"] == "DOC-SHARED-1.pdf"
        assert second.document.metadata_json["upload_original_filename"] == "DOC-SHARED-2.pdf"
        assert first.document.metadata_json["uploaded_by_id"] == actor.id
        assert second.document.metadata_json["uploaded_by_id"] == second_actor.id
        assert (
            first.document.metadata_json["source_review_policy"]
            == "technical-document-review-v2"
        )
        assert (
            second.document.metadata_json["source_review_policy"]
            == "technical-document-review-v2"
        )
        assert second.stored_file.uploaded_by_id == actor.id
        second_audit = db.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "upload",
                AuditEvent.entity_id == second.document.id,
            )
        )
        assert second_audit is not None
        assert second_audit.new_value["filename"] == "DOC-SHARED-2.pdf"


def test_nonclean_existing_hash_is_never_reused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    payload = _pdf("legacy-pending")
    digest = hashlib.sha256(payload).hexdigest()
    root = settings_path(tmp_path)
    path = root / digest[:2] / digest[2:4] / f"{digest}.pdf"
    path.parent.mkdir(parents=True)
    path.write_bytes(payload)

    with physical_session() as db:
        actor = _user(db)
        db.add(
            StoredFile(
                original_filename="legacy.pdf",
                media_type="application/pdf",
                storage_path=str(path),
                sha256=digest,
                size_bytes=len(payload),
                purpose="technical_evidence",
                malware_scan_status="pending",
                immutable=True,
            )
        )
        db.commit()

        with pytest.raises(TechnicalIntakeError) as caught:
            _create(
                db,
                _settings(tmp_path),
                actor,
                payload=payload,
                document_id="DOC-UNSAFE-DEDUP",
            )

        assert caught.value.code == "STORED_FILE_CONTEXT_CONFLICT"
        assert list(db.scalars(select(TechnicalDocument)).all()) == []
        assert path.read_bytes() == payload


def test_ui_requests_isolate_good_bad_good(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    with physical_session() as db:
        actor = _user(db)
        settings = _settings(tmp_path)
        responses = [
            _call_ui_upload(
                _request(
                    actor,
                    form=_ui_form(
                        _upload(_pdf("good-one"), "good-one.pdf"),
                        "DOC-GOOD-ONE",
                        "Good one",
                    ),
                ),
                db,
                settings,
            ),
            _call_ui_upload(
                _request(
                    actor,
                    form=_ui_form(
                        _upload(_pdf("MALWARE"), "bad.pdf"),
                        "DOC-BAD",
                        "Bad report",
                    ),
                ),
                db,
                settings,
            ),
            _call_ui_upload(
                _request(
                    actor,
                    form=_ui_form(
                        _upload(_pdf("good-two"), "good-two.pdf"),
                        "DOC-GOOD-TWO",
                        "Good two",
                    ),
                ),
                db,
                settings,
            ),
        ]

        payloads = [json.loads(response.body) for response in responses]
        assert [response.status_code for response in responses] == [201, 422, 201]
        assert [payload["ok"] for payload in payloads] == [True, False, True]
        assert payloads[1]["code"] == "MALWARE_DETECTED"
        assert payloads[1]["fatal"] is False
        correlation_ids = [
            payload.get("batch_id") for payload in (payloads[0], payloads[2])
        ]
        assert all(isinstance(value, str) for value in correlation_ids)
        assert correlation_ids[0] != correlation_ids[1]
        assert db.scalar(select(func.count()).select_from(TechnicalDocument)) == 2
        events = list(
            db.scalars(
                select(AuditEvent)
                .where(
                    AuditEvent.action.in_(
                        ("upload", "upload_rejected")
                    )
                )
                .order_by(AuditEvent.created_at)
            ).all()
        )
        assert [event.action for event in events] == [
            "upload",
            "upload_rejected",
            "upload",
        ]
        assert len({event.correlation_id for event in events}) == 3


def test_ui_upload_returns_relationship_and_exact_duplicate_receipts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    parser_calls: list[dict[str, object]] = []
    original_form = Request.form

    def tracking_form(self: Request, **kwargs: object):  # type: ignore[no-untyped-def]
        parser_calls.append(kwargs)
        return original_form(self, **kwargs)

    monkeypatch.setattr(Request, "form", tracking_form)
    with physical_session() as db:
        actor = _user(db)
        settings = _settings(tmp_path)
        large_evidence_limitations = ("耐火\r\n" * 3_000).strip()
        _create(
            db,
            settings,
            actor,
            payload=_pdf("base-source"),
            document_id="DOC-BASE-SOURCE",
        )

        linked = _call_ui_upload(
            _request(
                actor,
                form=_ui_form(
                    _upload(_pdf("linked-revision"), "revision.pdf"),
                    "DOC-LINKED-REVISION",
                    "Linked revision",
                    document_type="regulatory_information_report",
                    declared_source_role="regulatory_summary",
                    artifact_provenance_status="transformed_derivative",
                    evidence_scope="summary_only",
                    reference="SYNTHETIC-REPORT-236",
                    revision="RIR1.25A",
                    sponsor_organisation="TBA Textiles Pty Ltd",
                    issuing_organisation="Jensen Hughes Fire Testing Pty Ltd",
                    publication_date="2026-02-20",
                    expiry_date="2030-09-30",
                    jurisdiction="Australia",
                    standards="AS 1530.4:2014, AS 4072.1:2005",
                    artifact_provenance_note="Unlocked supplied derivative",
                    evidence_limitations=large_evidence_limitations,
                    relationship_type="summary_of",
                    related_document_id="DOC-BASE-SOURCE",
                    relationship_reason="Regulatory summary of the main assessment",
                    relationship_scope=(
                        "Reported assessed configurations\r\n"
                        "Section 4\rservice groups"
                    ),
                    relationship_effective_date="2026-02-20",
                ),
            ),
            db,
            settings,
        )
        linked_receipt = json.loads(linked.body)
        assert linked.status_code == 201
        assert linked_receipt["document_type"] == "regulatory_information_report"
        assert linked_receipt["declared_source_role"] == "regulatory_summary"
        assert linked_receipt["artifact_provenance_status"] == "transformed_derivative"
        assert linked_receipt["evidence_scope"] == "summary_only"
        assert linked_receipt["relationship"] == {
            "relationship_type": "summary_of",
            "related_document_id": "DOC-BASE-SOURCE",
        }
        assert linked_receipt["exact_content_duplicate_document_ids"] == []
        linked_document = db.scalar(
            select(TechnicalDocument).where(
                TechnicalDocument.document_id == "DOC-LINKED-REVISION"
            )
        )
        assert linked_document is not None
        assert linked_document.reference == "SYNTHETIC-REPORT-236"
        assert linked_document.revision == "RIR1.25A"
        assert linked_document.sponsor_organisation == "TBA Textiles Pty Ltd"
        assert linked_document.evidence_limitations == (
            ("耐火\n" * 3_000).strip()
        )
        relationship = db.scalar(
            select(TechnicalDocumentRelationship).where(
                TechnicalDocumentRelationship.document_id == linked_document.id
            )
        )
        assert relationship is not None
        assert relationship.scope == (
            "Reported assessed configurations\nSection 4\nservice groups"
        )
        assert relationship.effective_date.isoformat() == "2026-02-20"

        duplicate = _call_ui_upload(
            _request(
                actor,
                form=_ui_form(
                    _upload(_pdf("linked-revision"), "copy.pdf"),
                    "DOC-EXACT-COPY",
                    "Exact copy",
                ),
            ),
            db,
            settings,
        )
        duplicate_receipt = json.loads(duplicate.body)
        assert duplicate.status_code == 201
        assert duplicate_receipt["relationship"] is None
        assert duplicate_receipt["exact_content_duplicate_document_ids"] == [
            "DOC-LINKED-REVISION"
        ]

    assert parser_calls == [
        {"max_files": 1, "max_fields": 25, "max_part_size": 128 * 1024},
        {"max_files": 1, "max_fields": 25, "max_part_size": 128 * 1024},
    ]


@pytest.mark.parametrize("csrf_header", [None, "wrong-csrf"])
def test_ui_returns_stable_json_for_invalid_csrf_before_scanner_or_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    csrf_header: str | None,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    preflight_calls = 0

    def forbidden_preflight(*_args: object, **_kwargs: object) -> None:
        nonlocal preflight_calls
        preflight_calls += 1
        raise AssertionError("upload preflight must not run before CSRF validation")

    monkeypatch.setattr(ui_module, "preflight_technical_upload", forbidden_preflight)

    with physical_session() as db:
        actor = _user(db)
        response = _call_ui_upload(
            _request(actor, csrf_header=csrf_header, forbid_body=True),
            db,
            _settings(tmp_path),
        )

        assert response.status_code == 403
        assert json.loads(response.body) == {
            "ok": False,
            "code": "CSRF_INVALID",
            "retryable": False,
            "fatal": True,
        }
        assert scanner.calls == []
        assert preflight_calls == 0
        assert list(db.scalars(select(StoredFile)).all()) == []


def test_ui_returns_stable_json_for_missing_permission_before_scanning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    preflight_calls = 0

    def forbidden_preflight(*_args: object, **_kwargs: object) -> None:
        nonlocal preflight_calls
        preflight_calls += 1
        raise AssertionError("upload preflight must not run before permission checks")

    monkeypatch.setattr(ui_module, "preflight_technical_upload", forbidden_preflight)

    with physical_session() as db:
        actor = _user(db, role="read_only")
        response = _call_ui_upload(
            _request(actor, forbid_body=True),
            db,
            _settings(tmp_path),
        )

        assert response.status_code == 403
        assert json.loads(response.body) == {
            "ok": False,
            "code": "PERMISSION_DENIED",
            "retryable": False,
            "fatal": True,
        }
        assert scanner.calls == []
        assert preflight_calls == 0
        assert list(db.scalars(select(StoredFile)).all()) == []


def test_ui_returns_stable_json_when_session_has_expired(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)

    with physical_session() as db:
        actor = _user(db)
        request = _request(actor, forbid_body=True)
        request.session.pop("user_id")
        response = _call_ui_upload(
            request,
            db,
            _settings(tmp_path),
        )

        assert response.status_code == 401
        assert json.loads(response.body) == {
            "ok": False,
            "code": "AUTHENTICATION_REQUIRED",
            "retryable": False,
            "fatal": True,
        }
        assert scanner.calls == []
        assert list(db.scalars(select(StoredFile)).all()) == []


@pytest.mark.parametrize(
    ("content_length_values", "expected_status", "expected_code"),
    [
        ((), 411, "UPLOAD_CONTENT_LENGTH_REQUIRED"),
        (("1", "1"), 400, "UPLOAD_CONTENT_LENGTH_INVALID"),
        (("+1",), 400, "UPLOAD_CONTENT_LENGTH_INVALID"),
        (
            (
                "0" * 5_000
                + str(
                    1024 * 1024
                    + TECHNICAL_UPLOAD_MULTIPART_OVERHEAD_BYTES
                    + 1
                ),
            ),
            413,
            "UPLOAD_SIZE_LIMIT_EXCEEDED",
        ),
    ],
)
def test_ui_rejects_ordinary_upload_length_before_multipart_parsing(
    tmp_path: Path,
    content_length_values: tuple[str, ...],
    expected_status: int,
    expected_code: str,
) -> None:
    with physical_session() as db:
        actor = _user(db)
        response = _call_ui_upload(
            _request(
                actor,
                content_length_values=content_length_values,
                forbid_body=True,
            ),
            db,
            _settings(tmp_path),
        )

        assert response.status_code == expected_status
        assert json.loads(response.body) == {
            "ok": False,
            "code": expected_code,
            "retryable": False,
            "fatal": True,
        }
        assert list(db.scalars(select(StoredFile)).all()) == []
        assert list(db.scalars(select(TechnicalDocument)).all()) == []


@pytest.mark.parametrize(
    ("batch_headers", "item_headers", "expected_status", "expected_code"),
    [
        (
            ("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",),
            (),
            422,
            "INTAKE_BATCH_ITEM_ID_INVALID",
        ),
        (
            (
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            ),
            ("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",),
            422,
            "INTAKE_BATCH_ID_INVALID",
        ),
        (
            ("not-a-uuid",),
            ("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",),
            422,
            "INTAKE_BATCH_ID_INVALID",
        ),
        (
            ("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",),
            ("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",),
            404,
            "INTAKE_BATCH_NOT_FOUND",
        ),
    ],
)
def test_ui_rejects_invalid_batch_routing_headers_before_form_parsing(
    tmp_path: Path,
    batch_headers: tuple[str, ...],
    item_headers: tuple[str, ...],
    expected_status: int,
    expected_code: str,
) -> None:
    with physical_session() as db:
        actor = _user(db)
        response = _call_ui_upload(
            _request(
                actor,
                batch_id_headers=batch_headers,
                item_id_headers=item_headers,
                forbid_body=True,
            ),
            db,
            _settings(tmp_path),
        )

        assert response.status_code == expected_status
        assert json.loads(response.body) == {
            "ok": False,
            "code": expected_code,
            "retryable": False,
            "fatal": True,
        }
        assert list(db.scalars(select(StoredFile)).all()) == []
        assert list(db.scalars(select(TechnicalDocument)).all()) == []


@pytest.mark.parametrize(
    ("item_status", "outcome_retryable", "active", "expected_code", "retryable"),
    [
        ("needs_attention", False, False, "INTAKE_BATCH_ITEM_NOT_RETRYABLE", False),
        ("rejected", False, False, "INTAKE_BATCH_ITEM_NOT_RETRYABLE", False),
        ("processing", None, False, "INTAKE_BATCH_ITEM_NOT_RETRYABLE", False),
        ("processing", None, True, "INTAKE_BATCH_ITEM_IN_PROGRESS", True),
    ],
)
def test_ui_batch_lifecycle_rejection_runs_before_form_or_services(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    item_status: str,
    outcome_retryable: bool | None,
    active: bool,
    expected_code: str,
    retryable: bool,
) -> None:
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

    batch_id, item_id = _install_ui_batch_preflight_state(
        monkeypatch,
        status=item_status,
        outcome_retryable=outcome_retryable,
        attempt_started_at=datetime.now(UTC) if active else None,
    )
    monkeypatch.setattr(Request, "form", forbidden_form)
    monkeypatch.setattr(
        ui_module,
        "claim_technical_intake_batch_item",
        forbidden_service,
    )
    monkeypatch.setattr(
        ui_module,
        "create_technical_document_draft",
        forbidden_service,
    )
    with physical_session() as db:
        actor = _user(db)
        response = _call_ui_upload(
            _request(
                actor,
                batch_id_headers=(batch_id,),
                item_id_headers=(item_id,),
            ),
            db,
            _settings(tmp_path),
        )

    assert response.status_code == 409
    assert json.loads(response.body) == {
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
def test_ui_batch_preflight_allows_replay_retry_and_stale_reclaim_to_parser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    item_status: str,
    outcome_retryable: bool | None,
    stale: bool,
) -> None:
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
    batch_id, item_id = _install_ui_batch_preflight_state(
        monkeypatch,
        status=item_status,
        outcome_retryable=outcome_retryable,
        attempt_started_at=started_at,
    )
    monkeypatch.setattr(Request, "form", parsing_started)
    monkeypatch.setattr(
        ui_module,
        "claim_technical_intake_batch_item",
        forbidden_service,
    )
    monkeypatch.setattr(
        ui_module,
        "create_technical_document_draft",
        forbidden_service,
    )
    with physical_session() as db:
        actor = _user(db)
        response = _call_ui_upload(
            _request(
                actor,
                batch_id_headers=(batch_id,),
                item_id_headers=(item_id,),
            ),
            db,
            _settings(tmp_path),
        )

    assert response.status_code == 422
    assert json.loads(response.body) == {
        "ok": False,
        "code": "TECHNICAL_UPLOAD_FORM_INVALID",
        "retryable": False,
        "fatal": True,
    }
    assert form_calls == 1


def test_ui_batch_preflight_hides_foreign_batches_before_form_parsing(
    tmp_path: Path,
) -> None:
    with physical_session() as db:
        owner = _user(db, role="technical_reviewer")
        actor = _user(db)
        created = _create_batch_slot(db, _settings(tmp_path), owner)
        response = _call_ui_upload(
            _request(
                actor,
                batch_id_headers=(created.batch.id,),
                item_id_headers=(created.items[0].id,),
                forbid_body=True,
            ),
            db,
            _settings(tmp_path),
        )

        assert response.status_code == 404
        assert json.loads(response.body) == {
            "ok": False,
            "code": "INTAKE_BATCH_NOT_FOUND",
            "retryable": False,
            "fatal": True,
        }


def test_ui_rejects_header_form_identity_mismatch_without_claim_or_side_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_service(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("header/form mismatch must not claim or persist")

    monkeypatch.setattr(
        ui_module,
        "claim_technical_intake_batch_item",
        forbidden_service,
    )
    monkeypatch.setattr(
        ui_module,
        "create_technical_document_draft",
        forbidden_service,
    )
    with physical_session() as db:
        actor = _user(db)
        settings = _settings(tmp_path)
        created = _create_batch_slot(db, settings, actor)
        entries = list(
            _ui_form(
                _upload(_pdf("not-read"), "preflight-report.pdf"),
                "DOC-PREFLIGHT-BATCH",
                "Preflight report",
                batch_id=created.batch.id,
            ).multi_items()
        )
        entries.append(("item_id", "cccccccc-cccc-4ccc-8ccc-cccccccccccc"))
        response = _call_ui_upload(
            _request(
                actor,
                batch_id_headers=(created.batch.id,),
                item_id_headers=(created.items[0].id,),
                form=FormData(entries),
            ),
            db,
            settings,
        )

        assert response.status_code == 409
        assert json.loads(response.body) == {
            "ok": False,
            "code": "INTAKE_BATCH_HEADER_MISMATCH",
            "retryable": False,
            "fatal": True,
        }
        db.expire_all()
        item = db.get(TechnicalIntakeBatchItem, created.items[0].id)
        assert item is not None
        assert item.status == "pending"
        assert item.attempt_count == 0
        assert list(db.scalars(select(StoredFile)).all()) == []
        assert list(db.scalars(select(TechnicalDocument)).all()) == []


def test_ui_marks_shared_scanner_failure_as_batch_fatal(tmp_path: Path) -> None:
    with physical_session() as db:
        actor = _user(db)
        response = _call_ui_upload(
            _request(
                actor,
                form=_ui_form(
                    _upload(_pdf("not-read")),
                    "DOC-SCANNER",
                    "Scanner unavailable report",
                ),
            ),
            db,
            _settings(tmp_path, scanner_host=None),
        )

        assert response.status_code == 503
        assert json.loads(response.body) == {
            "ok": False,
            "code": "MALWARE_SCANNER_REQUIRED",
            "retryable": True,
            "fatal": True,
        }
        assert list(db.scalars(select(TechnicalDocument)).all()) == []


def test_ui_marks_secure_storage_failure_as_batch_fatal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def storage_failure(*_args: object, **_kwargs: object) -> None:
        raise TechnicalIntakeError("STORED_FILE_STORAGE_FAILURE")

    monkeypatch.setattr(ui_module, "create_technical_document_draft", storage_failure)
    with physical_session() as db:
        actor = _user(db)
        response = _call_ui_upload(
            _request(
                actor,
                form=_ui_form(
                    _upload(_pdf("not-retained")),
                    "DOC-STORAGE-FAILURE",
                    "Storage failure report",
                ),
            ),
            db,
            _settings(tmp_path),
        )

    assert response.status_code == 503
    assert json.loads(response.body) == {
        "ok": False,
        "code": "STORED_FILE_STORAGE_FAILURE",
        "retryable": True,
        "fatal": True,
    }


def test_ui_surfaces_incomplete_relationship_before_scanning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)

    with physical_session() as db:
        actor = _user(db)
        response = _call_ui_upload(
            _request(
                actor,
                form=_ui_form(
                    _upload(_pdf("not-read")),
                    "DOC-INCOMPLETE-RELATIONSHIP",
                    "Incomplete relationship",
                    relationship_type="revision_of",
                ),
            ),
            db,
            _settings(tmp_path),
        )

        assert response.status_code == 422
        assert json.loads(response.body) == {
            "ok": False,
            "code": "RELATIONSHIP_FIELDS_INCOMPLETE",
            "retryable": False,
            "fatal": False,
        }
        assert scanner.calls == []
        assert list(db.scalars(select(TechnicalDocument)).all()) == []


def test_non_json_ui_request_preserves_standard_csrf_failure(
    tmp_path: Path,
) -> None:
    with physical_session() as db:
        actor = _user(db)
        with pytest.raises(HTTPException) as caught:
            _call_ui_upload(
                _request(
                    actor,
                    accept="text/html",
                    csrf_header="wrong-csrf",
                    forbid_body=True,
                ),
                db,
                _settings(tmp_path),
            )

        assert caught.value.status_code == 403


@pytest.mark.parametrize(
    "case",
    [
        "wrong_content_type",
        "duplicate_file",
        "duplicate_document_id",
        "non_string_text",
        "missing_required_text",
        "empty_required_text",
        "missing_file",
        "unexpected_field",
    ],
)
def test_ui_rejects_invalid_manual_multipart_form_before_intake(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    entries: list[tuple[str, object]] = [
        ("file", _upload(_pdf("not-read"))),
        ("document_id", "DOC-INVALID-FORM"),
        ("document_type", "fire_test_report"),
        ("declared_source_role", "primary_test"),
        ("artifact_provenance_status", "unknown"),
        ("evidence_scope", "full_source"),
        ("title", "Invalid form report"),
        ("batch_id", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
    ]
    content_type = "multipart/form-data; boundary=technical-upload-test"
    if case == "wrong_content_type":
        content_type = "application/json"
    elif case == "duplicate_file":
        entries.append(("file", _upload(_pdf("second"), "second.pdf")))
    elif case == "duplicate_document_id":
        entries.append(("document_id", "DOC-DUPLICATE"))
    elif case == "non_string_text":
        entries = [
            (name, _upload(_pdf("not-text"), "title.pdf") if name == "title" else value)
            for name, value in entries
        ]
    elif case == "missing_required_text":
        entries = [(name, value) for name, value in entries if name != "title"]
    elif case == "empty_required_text":
        entries = [
            (name, "   " if name == "title" else value)
            for name, value in entries
        ]
    elif case == "missing_file":
        entries = [(name, value) for name, value in entries if name != "file"]
    elif case == "unexpected_field":
        entries.append(("unexpected", "value"))

    with physical_session() as db:
        actor = _user(db)
        response = _call_ui_upload(
            _request(
                actor,
                content_type=content_type,
                form=FormData(entries),
            ),
            db,
            _settings(tmp_path),
        )

        assert response.status_code == 422
        assert json.loads(response.body) == {
            "ok": False,
            "code": "TECHNICAL_UPLOAD_FORM_INVALID",
            "retryable": False,
            "fatal": True,
        }
        assert scanner.calls == []
        assert list(db.scalars(select(StoredFile)).all()) == []
        assert list(db.scalars(select(TechnicalDocument)).all()) == []


@pytest.mark.parametrize(
    ("missing_field", "expected_code"),
    [
        ("item_id", "INTAKE_BATCH_ITEM_ID_INVALID"),
        ("batch_id", "INTAKE_BATCH_ID_INVALID"),
    ],
)
def test_ui_batch_and_item_ids_must_be_paired_before_intake_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing_field: str,
    expected_code: str,
) -> None:
    def forbidden_service(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("unpaired batch identity must not reach intake")

    entries = list(
        _ui_form(
            _upload(_pdf("not-read")),
            "DOC-UNPAIRED-BATCH-IDENTITY",
            "Unpaired batch identity",
        ).multi_items()
    )
    if missing_field == "item_id":
        entries.append(("batch_id", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"))
    else:
        entries = [(name, value) for name, value in entries if name != "batch_id"]
        entries.append(("item_id", "cccccccc-cccc-4ccc-8ccc-cccccccccccc"))

    monkeypatch.setattr(
        ui_module,
        "claim_technical_intake_batch_item",
        forbidden_service,
    )
    monkeypatch.setattr(
        ui_module,
        "create_technical_document_draft",
        forbidden_service,
    )
    with physical_session() as db:
        actor = _user(db)
        response = _call_ui_upload(
            _request(actor, form=FormData(entries)),
            db,
            _settings(tmp_path),
        )

    assert response.status_code == 422
    assert json.loads(response.body) == {
        "ok": False,
        "code": expected_code,
        "retryable": False,
        "fatal": False,
    }


def test_non_json_ui_request_preserves_standard_invalid_form_failure(
    tmp_path: Path,
) -> None:
    with physical_session() as db:
        actor = _user(db)
        with pytest.raises(HTTPException) as caught:
            _call_ui_upload(
                _request(
                    actor,
                    accept="text/html",
                    form=FormData(
                        [
                            ("file", _upload(_pdf("not-read"))),
                            ("document_id", "DOC-ONE"),
                            ("document_id", "DOC-TWO"),
                            ("document_type", "fire_test_report"),
                            ("declared_source_role", "primary_test"),
                            ("artifact_provenance_status", "unknown"),
                            ("evidence_scope", "full_source"),
                            ("title", "Duplicate identity"),
                        ]
                    ),
                ),
                db,
                _settings(tmp_path),
            )

        assert caught.value.status_code == 422
        assert caught.value.detail == "TECHNICAL_UPLOAD_FORM_INVALID"


def test_technical_page_exposes_multi_report_controls_and_same_origin_script(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    with physical_session() as db:
        actor = _user(db)
        _create(
            db,
            _settings(tmp_path),
            actor,
            payload=_pdf("existing-source"),
            document_id="DOC-EXISTING-SOURCE",
        )
        _create(
            db,
            _settings(tmp_path),
            actor,
            payload=_pdf("legacy-existing-source"),
            document_id="DOC-LEGACY-SOURCE",
            document_type="engineering_assessment",
            declared_source_role="assessment",
        )
        response = technical_page(_request(actor, method="GET", accept="text/html"), db)
        html = response.body.decode("utf-8")

    assert 'id="technical-files"' in html
    assert "multiple required" in html
    assert 'id="technical-upload-item-template"' in html
    assert 'data-max-files="20"' in html
    assert 'data-request-timeout-ms="120000"' in html
    assert 'src="/static/js/technical-upload.js"' in html
    assert "Automatic extraction is paused" in html
    assert 'data-field="relationship_type"' in html
    assert 'data-field="related_document_id"' in html
    assert 'data-field="relationship_reason"' in html
    assert 'data-field="relationship_scope"' in html
    assert 'data-field="relationship_effective_date"' in html
    assert 'data-field="declared_source_role"' in html
    assert 'data-field="artifact_provenance_status"' in html
    assert 'data-field="evidence_scope"' in html
    assert '<option value="">Select report type</option>' in html
    for value, label in EXPECTED_NEW_TECHNICAL_DOCUMENT_TYPE_OPTIONS:
        assert f'<option value="{value}">{label}</option>' in html
    for value, label in TECHNICAL_LEGACY_DOCUMENT_TYPE_LABELS.items():
        assert f'<option value="{value}" hidden>{label}</option>' in html
    assert '<option value="">Select source role</option>' in html
    assert '<option value="">Select evidence scope</option>' in html
    assert 'placeholder="Enter the title shown inside the report"' in html
    assert 'value="regulatory_information_report"' in html
    assert "Current-standards evidence check" in html
    assert "Missing declared reference: NCC 2022, AS 1530.4:2014, AS 4072.1:2005" in html
    assert "Full Fire Test Report" in html
    assert "Engineering Assessment (legacy)" in html
    assert 'value="summary_of"' in html
    assert "CLASSIFIRE source registration ID" in html
    assert "Report reference or number" in html
    assert (
        'data-field="jurisdiction" maxlength="200" '
        'value="NSW/ACT, Australia" required'
    ) in html
    assert '<option value="DOC-EXISTING-SOURCE">' in html


def test_batch_script_exposes_final_fail_closed_browser_guards() -> None:
    script = (
        Path(__file__).parents[1]
        / "src"
        / "classifire"
        / "static"
        / "js"
        / "technical-upload.js"
    ).read_text(encoding="utf-8")
    template = (
        Path(__file__).parents[1]
        / "src"
        / "classifire"
        / "templates"
        / "technical.html"
    ).read_text(encoding="utf-8")

    assert 'data-batch-create-endpoint="/api/v1/technical/upload-batches"' in template
    assert 'data-batch-read-prefix="/api/v1/technical/upload-batches/"' in template
    assert (
        'data-batch-lookup-prefix="/api/v1/technical/upload-batches/'
        'by-client-request/"'
    ) in template
    assert 'data-batch-storage-key="classifire.technical.intake_batch"' in template
    assert 'id="technical-upload-new-batch"' in template
    assert "data-retry-file-control hidden" in template
    assert "data-retry-file type=\"file\"" in template
    assert 'regulatory_information_report: ["regulatory_summary", "summary_only"]' in script
    for ambiguous_type in (
        "extended_application_report",
        "field_of_application_report",
        "fire_engineering_report_performance_solution",
        "certificate_summary_of_assessment",
        "test_certificate",
    ):
        assert f"{ambiguous_type}:" not in script

    assert "let batchRunning = false" in script
    assert "let currentBatchId = null" in script
    assert "let currentManifest = null" in script
    assert 'request.setRequestHeader("X-CSRF-Token", csrfInput.value)' in script
    assert (
        'request.setRequestHeader(\n'
        '        "X-Classifire-Intake-Batch-ID",\n'
        "        correlationId,"
    ) in script
    assert (
        'request.setRequestHeader(\n'
        '        "X-Classifire-Intake-Item-ID",\n'
        "        item.itemId,"
    ) in script
    assert '"X-CSRF-Token": csrfInput.value' in script
    assert 'payload.append("csrf_token"' not in script
    assert '"Content-Type": "application/json"' in script
    assert "credentials: \"same-origin\"" in script
    assert "-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-" in script

    assert 'globalThis.crypto.subtle.digest("SHA-256", bytes)' in script
    assert "fileHashQueue.then(() => sha256File(file))" in script
    assert "await hashFileSequentially(item.file)" in script
    assert "for (let index = 0; index < selected.length; index += 1)" in script
    assert "client_request_id: manifest.client_request_id" in script
    assert "registration: item.identity" in script
    assert "expected_sha256: item.expectedSha256" in script
    assert "size_bytes: item.sizeBytes" in script
    assert "return await validateBatchPayload(payload, {manifest})" in script
    assert "payload.client_request_id !== manifest.client_request_id" in script
    assert "canonicalJson(item.registration)" in script
    assert "const reconstructedManifest = {" in script
    assert "await sha256CanonicalJson(reconstructedManifest)" in script
    assert "!== payload.manifest_sha256" in script
    assert (
        "await sha256CanonicalJson(item.registration)\n"
        "          !== item.registration_sha256"
    ) in script
    assert "!await validateBatchItemReceipt(item, payload.batch_id)" in script
    assert "receipt.batch_id === batchId" in script
    assert "receipt.item_id === item.item_id" in script
    assert "receipt.id === item.technical_document_id" in script
    assert "const retainedEvidenceAttentionCodes = new Set([" in script
    for integrity_code in [
        "MALWARE_DETECTED",
        "STORED_FILE_CONTENT_COLLISION",
        "STORED_FILE_CONTEXT_CONFLICT",
        "UPLOAD_CONTENT_SIGNATURE_INVALID",
        "UPLOAD_STAGED_BYTES_CHANGED",
    ]:
        assert integrity_code in script
    assert "(!hasNoAcceptedEvidence && !hasRetainedAcceptedEvidence)" in script
    assert "payload.counts[state] !== actualCounts[state]" in script
    assert "payload.status !== derivedStatus" in script
    assert "terminal !== (payload.completed_at !== null)" in script

    assert 'payload.append("batch_id", correlationId)' in script
    assert 'payload.append("item_id", item.itemId)' in script
    assert "response.item_id !== item.itemId" in script
    assert "response.file_sha256 !== item.expectedSha256" in script
    assert "response.idempotent_replay !== (httpStatus === 200)" in script
    assert 'schema: "technical-intake-item-receipt-v1"' in script
    assert "await sha256CanonicalJson(receipt) === response.receipt_sha256" in script
    assert "const workerCount = Math.min(2, queue.length)" in script

    assert "batchReadPrefix + batchId" in script
    assert script.count('cache: "no-store"') >= 3
    assert "return await fetchBatch(candidate, manifest)" in script
    assert "await reconcileCurrentBatch()" in script
    assert 'request.addEventListener("error"' in script
    assert 'request.addEventListener("timeout"' in script
    assert 'request.addEventListener("abort"' in script
    assert "UPLOAD_RESPONSE_MALFORMED" in script

    assert "globalThis.sessionStorage.setItem(batchStorageKey, batchId)" in script
    assert 'url.searchParams.set("intake_batch", batchId)' in script
    assert 'searchParams.get("intake_batch")' in script
    assert "void restoreBatch(batchToRestore)" in script
    assert "lockIdentity(item, true)" in script
    assert "populateIdentity(item, item.identity)" in script

    assert "file.name === item.filename && file.size === item.sizeBytes" in script
    assert "digest !== item.expectedSha256" in script
    assert "Reselect the exact file to retry." in script
    assert '["pending", "processing", "rejected"].includes' in script
    assert "item.serverItem.retryable === true" in script
    assert 'serverItem.status === "processing"\n        || !immutableFileMatches' in script
    assert '"claim_expires_at"' in script
    assert "The earlier server claim expired." in script
    assert "typeof item.claim_expires_at !== \"string\"" in script
    assert "isCanonicalFilename(file.name)" in script
    assert "&& [...value].length <= 500" in script
    assert "&& value.length <= 500" not in script
    assert "&& /^.+\\.(pdf|docx|xlsx|xlsb)$/i.test(value)" in script
    assert '!/[<>:"/\\\\|?*]/.test(value)' in script
    assert '/[\\p{C}\\p{Z}]/u.test(character)' in script
    assert '"jurisdiction", "title"' in script
    assert 'field(row, "title").value = reportStem(file.name)' not in script
    for code in (
        "ARTIFACT_PROVENANCE_INVALID",
        "ARTIFACT_PROVENANCE_NOTE_REQUIRED",
        "SOURCE_CLASSIFICATION_INVALID",
        "SOURCE_METADATA_FIELD_INVALID",
        "SOURCE_ROLE_INVALID",
        "SUMMARY_SOURCE_TARGET_INVALID",
    ):
        assert f"{code}:" in script
    assert 'regulatory_information_report: ["regulatory_summary", "summary_only"]' in script
    assert "isValidDuplicateReceipt(" in script
    assert "response.exact_content_duplicate_document_ids" in script
    assert "Exact content already exists as:" in script
    for code in [
        "TECHNICAL_INTAKE_AUDIT_FAILURE",
        "UPLOAD_MULTIPLE_CLEANUP_FAILED",
        "UPLOAD_RETENTION_CLEANUP_FAILED",
        "UPLOAD_TEMP_CLEANUP_FAILED",
        "RELATIONSHIP_FIELDS_INCOMPLETE",
        "RELATIONSHIP_TYPE_INVALID",
        "RELATED_DOCUMENT_NOT_FOUND",
    ]:
        assert code in script


def test_batch_script_stops_starting_uploads_after_fatal_response() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable for the browser queue regression")

    repository_root = Path(__file__).parents[1]
    script = (
        repository_root
        / "src"
        / "classifire"
        / "static"
        / "js"
        / "technical-upload.js"
    )
    harness = (
        repository_root
        / "tests"
        / "js"
        / "technical_upload_fatal_queue_harness.cjs"
    )
    completed = subprocess.run(  # noqa: S603
        (node, str(harness), str(script)),
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr

    source = script.read_text(encoding="utf-8")
    assert source.index("if (preserveQueueRefreshLock(outcome))") < source.index(
        "if (outcome.reconciliationRequired)"
    )
    assert (
        "if (fatalQueueRefreshLockCode !== null) {\n"
        "        batchRequiresRefresh = true;"
    ) in source


def test_batch_script_keeps_blank_standards_canonical_across_restore() -> None:
    script = (
        Path(__file__).parents[1]
        / "src"
        / "classifire"
        / "static"
        / "js"
        / "technical-upload.js"
    ).read_text(encoding="utf-8")

    assert "return standards.length ? Object.freeze(standards) : null;" in script
    assert 'identity[name] = standardsSnapshot(value);' in script
    assert "return value === null || (" in script
    assert "Array.isArray(serverItem.registration.standards)" in script
    assert "? Object.freeze([...serverItem.registration.standards])" in script
    assert "canonicalJson(item.registration)" in script
    assert "canonicalJson(expected.registration)" in script
    assert 'input.value.replace(/\\r\\n?/g, "\\n")' in script
    assert '"PENDING_REQUEST_STORAGE_REQUIRED", "STORED_FILE_STORAGE_FAILURE"' in script
    assert "createPersistedServerBatch(currentManifest)" in script


def test_ui_marks_ambiguous_item_acknowledgement_retryable_but_nonfatal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def ambiguous_acknowledgement(*_args: object, **_kwargs: object) -> None:
        raise TechnicalIntakeError(
            "INTAKE_BATCH_ITEM_ACKNOWLEDGEMENT_UNKNOWN"
        )

    monkeypatch.setattr(
        ui_module,
        "create_technical_document_draft",
        ambiguous_acknowledgement,
    )
    with physical_session() as db:
        actor = _user(db)
        response = _call_ui_upload(
            _request(
                actor,
                form=_ui_form(
                    _upload(_pdf("not-read")),
                    "DOC-AMBIGUOUS-ACK",
                    "Ambiguous acknowledgement",
                ),
            ),
            db,
            _settings(tmp_path),
        )

    assert response.status_code == 503
    assert json.loads(response.body) == {
        "ok": False,
        "code": "INTAKE_BATCH_ITEM_ACKNOWLEDGEMENT_UNKNOWN",
        "retryable": True,
        "fatal": False,
    }


def test_batch_script_requires_storage_then_reuses_ambiguous_create_request() -> None:
    script = (
        Path(__file__).parents[1]
        / "src"
        / "classifire"
        / "static"
        / "js"
        / "technical-upload.js"
    ).read_text(encoding="utf-8")
    template = (
        Path(__file__).parents[1]
        / "src"
        / "classifire"
        / "templates"
        / "technical.html"
    ).read_text(encoding="utf-8")

    assert 'data-storage-namespace="{{ user.id }}"' in template
    assert 'data-storage-namespace="{{ user.id }}:{{ csrf_token }}"' not in template
    assert (
        'data-batch-lookup-prefix="/api/v1/technical/upload-batches/'
        'by-client-request/"'
    ) in template
    assert 'const batchStorageKey = batchStorageKeyBase + "." + storageNamespace;' in script
    assert "|| !storageNamespace" in script
    assert (
        'const pendingRequestStorageKey = batchStorageKey '
        '+ ".pending_client_request";'
    ) in script
    assert "const persistPendingRequestId = (clientRequestId) =>" in script
    assert "pendingRequestStorageKey,\n        clientRequestId," in script
    assert "pendingRequestStorageKey,\n        JSON.stringify" not in script
    assert "normalisePendingManifest" not in script
    assert "requestedPendingManifest" not in script
    assert "currentManifest = await prepareManifest();" in script
    assert "const createPersistedServerBatch = async (manifest) =>" in script
    assert "if (!persistPendingRequestId(manifest.client_request_id))" in script
    assert "globalThis.sessionStorage.getItem(pendingRequestStorageKey)" in script
    assert "const created = await createPersistedServerBatch(currentManifest);" in script
    assert 'new Error("PENDING_REQUEST_STORAGE_REQUIRED")' in script
    assert "let ambiguousAttempt = false;" in script
    assert "if (!ambiguousAttempt)" in script
    assert "ambiguousAttempt = true;" in script
    assert (
        "const reconciled = await reconcilePendingRequest(\n"
        "          manifest.client_request_id,"
    ) in script
    assert "          manifest,\n        );" in script
    assert "{manifest, readResponse: true}" in script
    assert "A failed lookup cannot make an earlier ambiguous POST definite." in script
    assert "if (error && error.definite === true)" in script
    assert "clearPendingRequestId();" in script
    assert "applyPendingManifest(currentManifest);" in script
    assert "const pendingRequestToRestore = requestedPendingRequestId();" in script
    assert "void restorePendingRequest(pendingRequestToRestore);" in script
    assert "batchLookupPrefix + encodeURIComponent(clientRequestId)" in script
    assert "for (let attempt = 0; attempt < 2; attempt += 1)" in script
    assert "batch.client_request_id !== clientRequestId" in script
    assert "batchRequiresRefresh = true;" in script
    assert "Batch creation remains unconfirmed for request" in script
    assert "if you intend to abandon this request." in script
    assert "The same request ID and manifest" in script
    assert "digest !== item.expectedSha256" in script


def test_file_backed_sqlite_precommit_failure_rolls_back_row_and_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    engine, session_factory = _file_backed_sessions(tmp_path)
    settings = _settings(tmp_path)
    try:
        with session_factory() as db:
            actor = _user(db)
            _fail_document_flush(monkeypatch, db)

            with pytest.raises(TechnicalIntakeError) as caught:
                _create(
                    db,
                    settings,
                    actor,
                    payload=_pdf("precommit-failure"),
                    document_id="DOC-PRECOMMIT-FAIL",
                )

            assert caught.value.code == "STORED_FILE_PERSISTENCE_CONFLICT"

        with session_factory() as observer:
            assert observer.scalar(select(func.count()).select_from(StoredFile)) == 0
            assert observer.scalar(select(func.count()).select_from(TechnicalDocument)) == 0
            rejection = observer.scalar(
                select(AuditEvent).where(AuditEvent.action == "upload_rejected")
            )
            assert rejection is not None
            assert rejection.new_value["outcome"] == "STORED_FILE_PERSISTENCE_CONFLICT"
        assert [path for path in settings.storage_root.rglob("*") if path.is_file()] == []
    finally:
        engine.dispose()


def test_retained_cleanup_failure_is_stable_and_audits_prior_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    settings = _settings(tmp_path)
    original_unlink = Path.unlink

    def fail_retained_cleanup(path: Path, *args, **kwargs):
        if path.suffix == ".pdf":
            raise PermissionError("simulated retained cleanup denial")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_retained_cleanup)
    with physical_session() as db:
        actor = _user(db)
        _fail_document_flush(monkeypatch, db)

        with pytest.raises(TechnicalIntakeError) as caught:
            _create(
                db,
                settings,
                actor,
                payload=_pdf("retained-cleanup-failure"),
                document_id="DOC-RETAINED-CLEANUP",
            )

        assert caught.value.code == "UPLOAD_RETENTION_CLEANUP_FAILED"
        assert db.scalar(select(func.count()).select_from(StoredFile)) == 0
        rejection = db.scalar(
            select(AuditEvent).where(AuditEvent.action == "upload_rejected")
        )
        assert rejection is not None
        assert rejection.new_value["outcome"] == "UPLOAD_RETENTION_CLEANUP_FAILED"
        assert rejection.new_value["prior_outcome"] == "STORED_FILE_PERSISTENCE_CONFLICT"
        assert rejection.new_value["cleanup_failures"] == [
            "UPLOAD_RETENTION_CLEANUP_FAILED"
        ]
        retained = [
            path for path in settings.storage_root.rglob("*.pdf") if path.is_file()
        ]
        assert len(retained) == 1


def test_temp_cleanup_failure_is_stable_and_audits_prior_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    settings = _settings(tmp_path)
    original_unlink = Path.unlink

    def fail_temp_cleanup(path: Path, *args, **kwargs):
        if path.suffix == ".part":
            raise PermissionError("simulated temp cleanup denial")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_temp_cleanup)
    with physical_session() as db:
        actor = _user(db)

        with pytest.raises(TechnicalIntakeError) as caught:
            _create(
                db,
                settings,
                actor,
                payload=_pdf("MALWARE"),
                document_id="DOC-TEMP-CLEANUP",
            )

        assert caught.value.code == "UPLOAD_TEMP_CLEANUP_FAILED"
        rejection = db.scalar(
            select(AuditEvent).where(AuditEvent.action == "upload_rejected")
        )
        assert rejection is not None
        assert rejection.new_value["outcome"] == "UPLOAD_TEMP_CLEANUP_FAILED"
        assert rejection.new_value["prior_outcome"] == "MALWARE_DETECTED"
        assert rejection.new_value["cleanup_failures"] == ["UPLOAD_TEMP_CLEANUP_FAILED"]
        assert len(list(settings.storage_root.rglob("*.part"))) == 1


def test_commit_outcome_ambiguity_retains_possibly_committed_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    engine, session_factory = _file_backed_sessions(tmp_path)
    settings = _settings(tmp_path)
    try:
        with session_factory() as db:
            actor = _user(db)
            real_commit = db.commit

            def commit_then_disconnect() -> None:
                real_commit()
                raise OperationalError(
                    "simulated lost commit acknowledgement",
                    {},
                    RuntimeError("simulated connection loss"),
                    connection_invalidated=True,
                )

            monkeypatch.setattr(db, "commit", commit_then_disconnect)
            with pytest.raises(TechnicalIntakeError) as caught:
                _create(
                    db,
                    settings,
                    actor,
                    payload=_pdf("ambiguous-commit"),
                    document_id="DOC-AMBIGUOUS-COMMIT",
                )

            assert caught.value.code == "STORED_FILE_PERSISTENCE_CONFLICT"

        with session_factory() as observer:
            stored = observer.scalar(select(StoredFile))
            document = observer.scalar(select(TechnicalDocument))
            assert stored is not None
            assert document is not None
            assert Path(stored.storage_path).read_bytes() == _pdf("ambiguous-commit")
            assert observer.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "upload")
            ) == 1
            assert observer.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "upload_rejected")
            ) == 0
    finally:
        engine.dispose()


def test_internal_final_binding_failure_compensates_and_has_stable_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    settings = _settings(tmp_path)

    def reject_final_binding(*_args, **_kwargs):
        raise storage_service.StoredFileBindingError(
            "STORED_FILE_CHANGED_DURING_VALIDATION"
        )

    monkeypatch.setattr(
        storage_service,
        "require_stored_file_binding",
        reject_final_binding,
    )
    with physical_session() as db:
        actor = _user(db)
        with pytest.raises(TechnicalIntakeError) as caught:
            _create(
                db,
                settings,
                actor,
                payload=_pdf("binding-failure"),
                document_id="DOC-BINDING-FAILURE",
            )

        assert caught.value.code == "STORED_FILE_CONTENT_COLLISION"
        assert db.scalar(select(func.count()).select_from(StoredFile)) == 0
        assert db.scalar(select(func.count()).select_from(TechnicalDocument)) == 0
        rejection = db.scalar(
            select(AuditEvent).where(AuditEvent.action == "upload_rejected")
        )
        assert rejection is not None
        assert rejection.new_value["outcome"] == "STORED_FILE_CONTENT_COLLISION"
        assert [path for path in settings.storage_root.rglob("*") if path.is_file()] == []


def test_rejection_audit_failure_is_explicit_and_preserves_attempted_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    attempted_audits: list[dict[str, object]] = []
    real_record_audit = technical_intake_service.record_audit

    def capture_attempted_audit(*args, **kwargs):
        attempted_audits.append(dict(kwargs["new_value"]))
        return real_record_audit(*args, **kwargs)

    monkeypatch.setattr(
        technical_intake_service,
        "record_audit",
        capture_attempted_audit,
    )
    settings = _settings(tmp_path)
    with physical_session() as db:
        actor = _user(db)

        def fail_audit_commit() -> None:
            raise OperationalError(
                "simulated rejection audit failure",
                {},
                RuntimeError("simulated database failure"),
            )

        monkeypatch.setattr(db, "commit", fail_audit_commit)
        with pytest.raises(TechnicalIntakeError) as caught:
            _create(
                db,
                settings,
                actor,
                payload=_pdf("MALWARE"),
                document_id="DOC-AUDIT-FAILURE",
            )

        assert caught.value.code == "TECHNICAL_INTAKE_AUDIT_FAILURE"
        assert caught.value.prior_code == "MALWARE_DETECTED"
        assert caught.value.retryable is True
        assert caught.value.operator_attention is True
        assert attempted_audits == [
            {
                "document_id": "DOC-AUDIT-FAILURE",
                "filename": "DOC-AUDIT-FAILURE.pdf",
                "outcome": "MALWARE_DETECTED",
            }
        ]
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0
        assert db.scalar(select(func.count()).select_from(StoredFile)) == 0
        assert [path for path in settings.storage_root.rglob("*") if path.is_file()] == []


def test_rejection_rollback_failure_invalidates_the_session() -> None:
    invalidations: list[bool] = []

    class _RollbackFailureSession:
        def rollback(self) -> None:
            raise OperationalError(
                "simulated rejection rollback failure",
                {},
                RuntimeError("simulated database failure"),
            )

        def invalidate(self) -> None:
            invalidations.append(True)

    with pytest.raises(TechnicalIntakeError) as caught:
        technical_intake_service._record_rejection(
            _RollbackFailureSession(),
            actor=User(
                email="rollback-failure@example.test",
                full_name="Rollback Failure Test",
                password_hash="not-used",  # noqa: S106
                role="administrator",
                is_active=True,
            ),
            code="STORED_FILE_CONTENT_COLLISION",
            document_id="DOC-ROLLBACK-FAILURE",
            filename="report.pdf",
            correlation_id=None,
            source_ip=None,
        )

    assert caught.value.code == "TECHNICAL_INTAKE_AUDIT_FAILURE"
    assert caught.value.prior_code == "STORED_FILE_CONTENT_COLLISION"
    assert caught.value.retryable is True
    assert caught.value.operator_attention is True
    assert invalidations == [True]


def test_two_session_sqlite_same_sha_converges_without_duplicate_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    engine, session_factory = _file_backed_sessions(tmp_path)
    settings = _settings(tmp_path)
    rendezvous = Barrier(2)
    original_lookup = storage_service._locked_stored_file_by_sha

    def synchronised_absent_lookup(db: Session, sha256: str):
        existing = original_lookup(db, sha256)
        rendezvous.wait(timeout=10)
        return existing

    monkeypatch.setattr(
        storage_service,
        "_locked_stored_file_by_sha",
        synchronised_absent_lookup,
    )
    payload = _pdf("concurrent-shared-hash")
    try:
        with session_factory() as setup:
            actor_id = _user(setup).id

        def submit(document_id: str) -> tuple[str, str]:
            with session_factory() as db:
                actor = db.get(User, actor_id)
                assert actor is not None
                try:
                    result = _create(
                        db,
                        settings,
                        actor,
                        payload=payload,
                        document_id=document_id,
                    )
                except TechnicalIntakeError as exc:
                    return "rejected", exc.code
                return "created", result.stored_file.id

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(submit, "DOC-CONCURRENT-A"),
                executor.submit(submit, "DOC-CONCURRENT-B"),
            ]
            outcomes = [future.result(timeout=20) for future in futures]

        assert [outcome[0] for outcome in outcomes].count("created") == 1
        assert [outcome[0] for outcome in outcomes].count("rejected") == 1
        rejected = next(outcome for outcome in outcomes if outcome[0] == "rejected")
        assert rejected[1] == "STORED_FILE_PERSISTENCE_CONFLICT"

        with session_factory() as observer:
            assert observer.scalar(select(func.count()).select_from(StoredFile)) == 1
            assert observer.scalar(select(func.count()).select_from(TechnicalDocument)) == 1
            assert observer.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "upload")
            ) == 1
            assert observer.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "upload_rejected")
            ) == 1
            stored = observer.scalar(select(StoredFile))
            assert stored is not None
            assert Path(stored.storage_path).read_bytes() == payload
        assert len(list(settings.storage_root.rglob("*.pdf"))) == 1
        assert not list(settings.storage_root.rglob("*.part"))
    finally:
        engine.dispose()
