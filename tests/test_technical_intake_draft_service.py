# ruff: noqa: S106
from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, func, select, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from classifire import models, physical_models  # noqa: F401
from classifire.config import get_settings
from classifire.db import Base
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
    TECHNICAL_INTAKE_DRAFT_SCHEMA,
    TECHNICAL_INTAKE_PAYLOAD_MAX_BYTES,
    TECHNICAL_INTAKE_PAYLOAD_SCHEMA,
    TechnicalIntakeDraftError,
    get_owned_technical_intake_draft,
    list_owned_technical_intake_drafts,
    parse_technical_intake_payload,
    save_technical_intake_draft,
    start_or_resume_technical_intake_draft,
)


@pytest.fixture(autouse=True)
def governed_storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
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


def _user(
    db: Session,
    email: str,
    *,
    active: bool = True,
    user_id: str | None = None,
) -> User:
    user = User(
        email=email,
        full_name=email.split("@", 1)[0],
        password_hash="not-used",
        role="technical_reviewer",
        is_active=active,
    )
    if user_id is not None:
        user.id = user_id
    db.add(user)
    db.commit()
    return user


def _document(
    db: Session,
    *,
    uploaded_by: User,
    document_id: str = "REPORT-001",
    status: str = "draft",
    media_type: str = "application/pdf",
    stored_file_id: str | None = None,
    technical_document_db_id: str | None = None,
) -> tuple[TechnicalDocument, StoredFile, Path]:
    content = (
        f"%PDF-1.7\nretained governed technical evidence {document_id}\n%%EOF"
    ).encode()
    digest = hashlib.sha256(content).hexdigest()
    root = get_settings().storage_root
    path = root / digest[:2] / digest[2:4] / f"{digest}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    stored = StoredFile(
        original_filename=f"{document_id}.pdf",
        media_type=media_type,
        storage_path=str(path),
        sha256=digest,
        size_bytes=len(content),
        purpose="technical_evidence",
        malware_scan_status="clean",
        uploaded_by_id=uploaded_by.id,
        immutable=True,
    )
    if stored_file_id is not None:
        stored.id = stored_file_id
    db.add(stored)
    db.flush()
    document = TechnicalDocument(
        document_id=document_id,
        stored_file_id=stored.id,
        document_type="test_report",
        title=f"Report {document_id}",
        status=status,
    )
    if technical_document_db_id is not None:
        document.id = technical_document_db_id
    db.add(document)
    db.commit()
    return document, stored, path


def _payload(
    document: TechnicalDocument,
    stored: StoredFile,
    *,
    raw_value: str | None = "  20 mm\r\n",
    normalized_value: str | None = "20",
    fact_state: str = "Provisional",
    limitation: str | None = None,
    evidence_role: str = "direct",
) -> dict[str, Any]:
    field_id = str(uuid4())
    locator_id = str(uuid4())
    return {
        "schema": TECHNICAL_INTAKE_PAYLOAD_SCHEMA,
        "fields": [
            {
                "row_id": field_id,
                "ordinal": 1,
                "field_key": "minimum_service_size_mm",
                "raw_value": raw_value,
                "normalized_value": normalized_value,
                "unit": "mm",
                "semantics": "minimum",
                "fact_state": fact_state,
                "material": True,
                "limitation": limitation,
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
                "excerpt": "  Source wording is retained.\r\n",
                "region": {
                    "x0": "0.1000",
                    "y0": "0.2",
                    "x1": "0.8",
                    "y1": "1.0",
                },
                "visual_verification": "required",
            }
        ],
        "links": [
            {
                "row_id": str(uuid4()),
                "field_row_id": field_id,
                "locator_row_id": locator_id,
                "evidence_role": evidence_role,
            }
        ],
    }


def _encode(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _assert_error(
    code: str,
    callback: Callable[[], object],
) -> TechnicalIntakeDraftError:
    with pytest.raises(TechnicalIntakeDraftError) as caught:
        callback()
    assert caught.value.code == code
    return caught.value


def test_payload_is_strict_canonical_and_preserves_source_wording(db: Session) -> None:
    author = _user(db, "author@example.test")
    document, stored, _path = _document(db, uploaded_by=author)
    payload = _payload(document, stored)
    second = copy.deepcopy(payload["fields"][0])
    second["row_id"] = str(uuid4())
    second["ordinal"] = 2
    second["field_key"] = "maximum_service_size_mm"
    second_locator = copy.deepcopy(payload["locators"][0])
    second_locator["row_id"] = str(uuid4())
    second_link = copy.deepcopy(payload["links"][0])
    second_link["row_id"] = str(uuid4())
    second_link["field_row_id"] = second["row_id"]
    second_link["locator_row_id"] = second_locator["row_id"]
    payload["fields"] = [second, payload["fields"][0]]
    payload["locators"] = [second_locator, payload["locators"][0]]
    payload["links"] = [second_link, payload["links"][0]]

    validated = parse_technical_intake_payload(
        _encode(payload),
        technical_document_id=document.id,
        source_sha256=stored.sha256,
        source_size_bytes=stored.size_bytes,
    )
    reordered = {
        key: payload[key]
        for key in ("links", "locators", "fields", "schema")
    }
    repeated = parse_technical_intake_payload(
        json.dumps(reordered, ensure_ascii=False, indent=2),
        technical_document_id=document.id,
        source_sha256=stored.sha256,
        source_size_bytes=stored.size_bytes,
    )

    assert [row["ordinal"] for row in validated.payload["fields"]] == [1, 2]
    assert validated.payload["fields"][0]["raw_value"] == "  20 mm\r\n"
    assert (
        validated.payload["locators"][0]["excerpt"]
        == "  Source wording is retained.\r\n"
    )
    assert {
        row["region"]["x0"]
        for row in validated.payload["locators"]
    } == {"0.1"}
    assert validated.canonical_json == repeated.canonical_json
    assert validated.payload_sha256 == repeated.payload_sha256
    assert json.loads(validated.canonical_json) == validated.payload


def test_strict_json_rejects_duplicate_keys_floats_and_oversize(db: Session) -> None:
    author = _user(db, "author@example.test")
    document, stored, _path = _document(db, uploaded_by=author)
    duplicate = (
        '{"schema":"technical-intake-payload-v1",'
        '"schema":"technical-intake-payload-v1",'
        '"fields":[],"locators":[],"links":[]}'
    )

    _assert_error(
        "TECHNICAL_INTAKE_DRAFT_DUPLICATE_KEY",
        lambda: parse_technical_intake_payload(
            duplicate,
            technical_document_id=document.id,
            source_sha256=stored.sha256,
            source_size_bytes=stored.size_bytes,
        ),
    )
    _assert_error(
        "TECHNICAL_INTAKE_DRAFT_JSON_INVALID",
        lambda: parse_technical_intake_payload(
            '{"schema":"technical-intake-payload-v1","fields":[],'
            '"locators":[],"links":[],"unexpected":0.1}',
            technical_document_id=document.id,
            source_sha256=stored.sha256,
            source_size_bytes=stored.size_bytes,
        ),
    )
    _assert_error(
        "TECHNICAL_INTAKE_DRAFT_PAYLOAD_TOO_LARGE",
        lambda: parse_technical_intake_payload(
            "x" * (TECHNICAL_INTAKE_PAYLOAD_MAX_BYTES + 1),
            technical_document_id=document.id,
            source_sha256=stored.sha256,
            source_size_bytes=stored.size_bytes,
        ),
    )


def _confirmed(payload: dict[str, Any]) -> None:
    payload["fields"][0]["fact_state"] = "Confirmed"


def _unknown_field(payload: dict[str, Any]) -> None:
    payload["fields"][0]["field_key"] = "search_eligibility"


def _unresolved_without_limitation(payload: dict[str, Any]) -> None:
    payload["fields"][0]["fact_state"] = "Unresolved"
    payload["fields"][0]["normalized_value"] = None


def _unresolved_with_normalized_value(payload: dict[str, Any]) -> None:
    payload["fields"][0]["fact_state"] = "Unresolved"
    payload["fields"][0]["limitation"] = "Source does not resolve the conflict"


def _blank_non_unresolved(payload: dict[str, Any]) -> None:
    payload["fields"][0]["raw_value"] = None
    payload["fields"][0]["normalized_value"] = None


def _source_substitution(payload: dict[str, Any]) -> None:
    payload["locators"][0]["source_sha256"] = "0" * 64


def _non_integer_source_size(payload: dict[str, Any]) -> None:
    payload["locators"][0]["source_size_bytes"] = float(
        payload["locators"][0]["source_size_bytes"]
    )


def _page_only_locator(payload: dict[str, Any]) -> None:
    for key in (
        "printed_page",
        "section",
        "clause",
        "table",
        "row",
        "column",
        "footnote",
        "figure",
        "drawing",
        "specimen",
        "option",
        "callout",
        "excerpt",
        "region",
    ):
        payload["locators"][0][key] = None


def _invalid_region(payload: dict[str, Any]) -> None:
    payload["locators"][0]["region"]["x1"] = "0.1"


def _unlinked_field(payload: dict[str, Any]) -> None:
    payload["links"] = []
    payload["locators"] = []


def _unused_locator(payload: dict[str, Any]) -> None:
    extra = copy.deepcopy(payload["locators"][0])
    extra["row_id"] = str(uuid4())
    payload["locators"].append(extra)


def _duplicate_link_tuple(payload: dict[str, Any]) -> None:
    extra = copy.deepcopy(payload["links"][0])
    extra["row_id"] = str(uuid4())
    payload["links"].append(extra)


def _conflicting_resolved_fact(payload: dict[str, Any]) -> None:
    payload["links"][0]["evidence_role"] = "conflicting"


def _unsupported_resolved_fact(payload: dict[str, Any]) -> None:
    payload["links"][0]["evidence_role"] = "superseded"


def _control_character(payload: dict[str, Any]) -> None:
    payload["fields"][0]["raw_value"] = "unsafe\u0000value"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (_confirmed, "TECHNICAL_INTAKE_DRAFT_CONFIRMED_FORBIDDEN"),
        (_unknown_field, "TECHNICAL_INTAKE_DRAFT_FIELD_INVALID"),
        (_unresolved_without_limitation, "TECHNICAL_INTAKE_DRAFT_FIELD_INVALID"),
        (_unresolved_with_normalized_value, "TECHNICAL_INTAKE_DRAFT_FIELD_INVALID"),
        (_blank_non_unresolved, "TECHNICAL_INTAKE_DRAFT_FIELD_INVALID"),
        (_source_substitution, "TECHNICAL_INTAKE_DRAFT_LOCATOR_INVALID"),
        (_non_integer_source_size, "TECHNICAL_INTAKE_DRAFT_JSON_INVALID"),
        (_page_only_locator, "TECHNICAL_INTAKE_DRAFT_LOCATOR_INVALID"),
        (_invalid_region, "TECHNICAL_INTAKE_DRAFT_LOCATOR_INVALID"),
        (_unlinked_field, "TECHNICAL_INTAKE_DRAFT_EVIDENCE_INVALID"),
        (_unused_locator, "TECHNICAL_INTAKE_DRAFT_EVIDENCE_INVALID"),
        (_duplicate_link_tuple, "TECHNICAL_INTAKE_DRAFT_LINK_INVALID"),
        (_conflicting_resolved_fact, "TECHNICAL_INTAKE_DRAFT_EVIDENCE_INVALID"),
        (_unsupported_resolved_fact, "TECHNICAL_INTAKE_DRAFT_EVIDENCE_INVALID"),
        (_control_character, "TECHNICAL_INTAKE_DRAFT_FIELD_INVALID"),
    ],
)
def test_payload_rejects_unsafe_or_unsupported_claims(
    db: Session,
    mutation: Callable[[dict[str, Any]], None],
    code: str,
) -> None:
    author = _user(db, f"{uuid4()}@example.test")
    document, stored, _path = _document(
        db,
        uploaded_by=author,
        document_id=f"REPORT-{uuid4()}",
    )
    payload = _payload(document, stored)
    mutation(payload)

    _assert_error(
        code,
        lambda: parse_technical_intake_payload(
            _encode(payload),
            technical_document_id=document.id,
            source_sha256=stored.sha256,
            source_size_bytes=stored.size_bytes,
        ),
    )


def test_unresolved_conflicting_fact_is_retained_explicitly(db: Session) -> None:
    author = _user(db, "author@example.test")
    document, stored, _path = _document(db, uploaded_by=author)
    payload = _payload(
        document,
        stored,
        raw_value=None,
        normalized_value=None,
        fact_state="Unresolved",
        limitation="Two retained source passages conflict.",
        evidence_role="conflicting",
    )

    validated = parse_technical_intake_payload(
        _encode(payload),
        technical_document_id=document.id,
        source_sha256=stored.sha256,
        source_size_bytes=stored.size_bytes,
    )

    assert validated.payload["fields"][0]["fact_state"] == "Unresolved"
    assert validated.payload["fields"][0]["normalized_value"] is None


def test_start_resume_creates_one_empty_owner_source_draft_and_hash_only_audit(
    db: Session,
) -> None:
    author = _user(db, "author@example.test")
    document, stored, _path = _document(db, uploaded_by=author)

    first = start_or_resume_technical_intake_draft(
        db,
        actor=author,
        technical_document_id=document.id,
    )
    second = start_or_resume_technical_intake_draft(
        db,
        actor=author,
        technical_document_id=document.id,
    )
    db.flush()

    assert first.resumed is False
    assert second.resumed is True
    assert second.draft.id == first.draft.id
    assert first.draft.draft_schema == TECHNICAL_INTAKE_DRAFT_SCHEMA
    assert first.draft.source_stored_file_id == stored.id
    assert first.draft.source_sha256 == stored.sha256
    assert first.draft.source_size_bytes == stored.size_bytes
    assert first.draft.owner_id == author.id
    assert first.draft.status == "draft"
    assert first.draft.record_version == 1
    assert first.draft.payload_json == {
        "fields": [],
        "links": [],
        "locators": [],
        "schema": TECHNICAL_INTAKE_PAYLOAD_SCHEMA,
    }
    assert db.scalar(select(func.count()).select_from(TechnicalIntakeDraft)) == 1
    audits = db.scalars(
        select(AuditEvent).where(
            AuditEvent.entity_type == "technical_intake_draft"
        )
    ).all()
    assert len(audits) == 1
    assert audits[0].previous_value is None
    assert set(audits[0].new_value or {}) == {
        "payload_sha256",
        "source_sha256",
    }


def test_legacy_fk_ids_create_save_and_reopen_without_becoming_unreadable(
    db: Session,
) -> None:
    author = _user(
        db,
        "legacy-author@example.test",
        user_id="legacy-technical-author",
    )
    document, stored, _path = _document(
        db,
        uploaded_by=author,
        document_id="LEGACY-REPORT",
        stored_file_id="legacy-retained-pdf",
        technical_document_db_id="legacy-technical-document",
    )

    started = start_or_resume_technical_intake_draft(
        db,
        actor=author,
        technical_document_id=document.id,
    )
    assert started.resumed is False
    assert UUID(started.draft.id).version == 4
    db.commit()
    db.expire_all()

    persisted_author = db.get(User, "legacy-technical-author")
    assert persisted_author is not None
    reopened = get_owned_technical_intake_draft(
        db,
        actor=persisted_author,
        draft_id=started.draft.id,
    )
    assert reopened.owner_id == "legacy-technical-author"
    assert reopened.source_stored_file_id == "legacy-retained-pdf"
    assert reopened.technical_document_id == "legacy-technical-document"

    saved = save_technical_intake_draft(
        db,
        actor=persisted_author,
        draft_id=reopened.id,
        expected_record_version=reopened.record_version,
        payload_json=_encode(_payload(document, stored)),
        reason="Transcribe legacy retained evidence",
    )
    assert saved.draft.record_version == 2
    db.commit()
    db.expire_all()

    reopened_again = get_owned_technical_intake_draft(
        db,
        actor=persisted_author,
        draft_id=saved.draft.id,
    )
    listed = list_owned_technical_intake_drafts(
        db,
        actor=persisted_author,
        technical_document_id="legacy-technical-document",
    )
    assert reopened_again.payload_sha256 == saved.draft.payload_sha256
    assert [draft.id for draft in listed] == [saved.draft.id]


def test_whitespace_padded_legacy_document_id_is_rejected_before_insert(
    db: Session,
) -> None:
    author = _user(db, "author@example.test")
    document, _stored, _path = _document(
        db,
        uploaded_by=author,
        document_id="PADDED-ID",
        technical_document_db_id=" legacy-technical-document ",
    )

    _assert_error(
        "TECHNICAL_INTAKE_DRAFT_DOCUMENT_NOT_FOUND",
        lambda: start_or_resume_technical_intake_draft(
            db,
            actor=author,
            technical_document_id=document.id,
        ),
    )
    assert db.scalar(select(func.count()).select_from(TechnicalIntakeDraft)) == 0


def test_start_recovers_idempotently_when_an_insert_loses_the_unique_race(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    author = _user(db, "author@example.test")
    document, _stored, _path = _document(db, uploaded_by=author)
    winner = start_or_resume_technical_intake_draft(
        db,
        actor=author,
        technical_document_id=document.id,
    ).draft
    db.commit()
    original_scalar = db.scalar
    suppressed = False

    def scalar(statement: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal suppressed
        descriptions = getattr(statement, "column_descriptions", ())
        entity = descriptions[0].get("entity") if descriptions else None
        if entity is TechnicalIntakeDraft and not suppressed:
            suppressed = True
            return None
        return original_scalar(statement, *args, **kwargs)

    monkeypatch.setattr(db, "scalar", scalar)
    raced = start_or_resume_technical_intake_draft(
        db,
        actor=author,
        technical_document_id=document.id,
    )
    db.flush()

    assert raced.resumed is True
    assert raced.draft.id == winner.id
    assert db.scalar(select(func.count()).select_from(TechnicalIntakeDraft)) == 1
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.entity_type == "technical_intake_draft")
        )
        == 1
    )


def test_get_and_list_are_owner_bound_without_a_cross_owner_oracle(db: Session) -> None:
    first_owner = _user(db, "first@example.test")
    second_owner = _user(db, "second@example.test")
    document, _stored, _path = _document(db, uploaded_by=first_owner)
    first = start_or_resume_technical_intake_draft(
        db,
        actor=first_owner,
        technical_document_id=document.id,
    ).draft
    db.commit()

    _assert_error(
        "TECHNICAL_INTAKE_DRAFT_NOT_FOUND",
        lambda: get_owned_technical_intake_draft(
            db,
            actor=second_owner,
            draft_id=first.id,
        ),
    )
    assert list_owned_technical_intake_drafts(db, actor=second_owner) == ()
    second = start_or_resume_technical_intake_draft(
        db,
        actor=second_owner,
        technical_document_id=document.id,
    ).draft

    assert second.id != first.id
    assert [item.id for item in list_owned_technical_intake_drafts(
        db,
        actor=first_owner,
        technical_document_id=document.id,
    )] == [first.id]
    assert [item.id for item in list_owned_technical_intake_drafts(
        db,
        actor=second_owner,
        technical_document_id=document.id,
    )] == [second.id]


def test_cross_owner_save_is_not_found_and_changes_nothing(db: Session) -> None:
    owner = _user(db, "owner@example.test")
    other = _user(db, "other@example.test")
    document, stored, _path = _document(db, uploaded_by=owner)
    draft = start_or_resume_technical_intake_draft(
        db,
        actor=owner,
        technical_document_id=document.id,
    ).draft
    db.commit()
    original_version = draft.record_version
    original_payload_sha256 = draft.payload_sha256
    original_audit_count = db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.entity_type == "technical_intake_draft")
    )

    _assert_error(
        "TECHNICAL_INTAKE_DRAFT_NOT_FOUND",
        lambda: save_technical_intake_draft(
            db,
            actor=other,
            draft_id=draft.id,
            expected_record_version=original_version,
            payload_json=_encode(_payload(document, stored)),
            reason="Attempt a cross-owner save",
        ),
    )
    db.expire_all()
    unchanged = db.get(TechnicalIntakeDraft, draft.id)

    assert unchanged is not None
    assert unchanged.record_version == original_version
    assert unchanged.payload_sha256 == original_payload_sha256
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.entity_type == "technical_intake_draft")
        )
        == original_audit_count
    )


def test_unpersisted_or_inactive_actor_cannot_observe_or_start(db: Session) -> None:
    author = _user(db, "author@example.test")
    inactive = _user(db, "inactive@example.test", active=False)
    document, _stored, _path = _document(db, uploaded_by=author)
    detached = User(
        email="detached@example.test",
        full_name="detached",
        password_hash="not-used",
        role="technical_reviewer",
        is_active=True,
    )

    for actor in (inactive, detached):
        def attempt_start(actor_to_test: User = actor) -> object:
            return start_or_resume_technical_intake_draft(
                db,
                actor=actor_to_test,
                technical_document_id=document.id,
            )

        _assert_error(
            "TECHNICAL_INTAKE_DRAFT_ACTOR_INVALID",
            attempt_start,
        )
    assert db.scalar(select(func.count()).select_from(TechnicalIntakeDraft)) == 0


def test_rejected_non_pdf_or_tampered_source_fails_without_draft_mutation(
    db: Session,
) -> None:
    author = _user(db, "author@example.test")
    rejected, _stored, _path = _document(
        db,
        uploaded_by=author,
        document_id="REJECTED",
        status="rejected",
    )
    _assert_error(
        "TECHNICAL_INTAKE_DRAFT_DOCUMENT_NOT_AUTHORABLE",
        lambda: start_or_resume_technical_intake_draft(
            db,
            actor=author,
            technical_document_id=rejected.id,
        ),
    )
    non_pdf, _stored, _path = _document(
        db,
        uploaded_by=author,
        document_id="NON-PDF",
        media_type="text/plain",
    )
    _assert_error(
        "TECHNICAL_INTAKE_DRAFT_SOURCE_FILE_INVALID",
        lambda: start_or_resume_technical_intake_draft(
            db,
            actor=author,
            technical_document_id=non_pdf.id,
        ),
    )
    clean, stored, path = _document(
        db,
        uploaded_by=author,
        document_id="TAMPERED",
    )
    draft = start_or_resume_technical_intake_draft(
        db,
        actor=author,
        technical_document_id=clean.id,
    ).draft
    db.commit()
    path.write_bytes(path.read_bytes() + b"tamper")

    _assert_error(
        "TECHNICAL_INTAKE_DRAFT_SOURCE_FILE_INVALID",
        lambda: save_technical_intake_draft(
            db,
            actor=author,
            draft_id=draft.id,
            expected_record_version=1,
            payload_json=_encode(_payload(clean, stored)),
            reason="Transcribe the retained source",
        ),
    )
    db.rollback()
    persisted = db.get(TechnicalIntakeDraft, draft.id)
    assert persisted is not None
    assert persisted.record_version == 1
    assert persisted.payload_json["fields"] == []


def test_save_cas_audits_only_hashes_changed_ids_and_reason_without_authority(
    db: Session,
) -> None:
    author = _user(db, "author@example.test")
    document, stored, _path = _document(db, uploaded_by=author)
    draft = start_or_resume_technical_intake_draft(
        db,
        actor=author,
        technical_document_id=document.id,
    ).draft
    payload = _payload(document, stored)
    field_id = payload["fields"][0]["row_id"]
    locator_id = payload["locators"][0]["row_id"]
    link_id = payload["links"][0]["row_id"]

    saved = save_technical_intake_draft(
        db,
        actor=author,
        draft_id=draft.id,
        expected_record_version=1,
        payload_json=_encode(payload),
        reason="  Transcribed and linked the cited row.\r\n",
    )
    db.flush()

    assert saved.idempotent_replay is False
    assert saved.draft.record_version == 2
    assert saved.changed_field_row_ids == (field_id,)
    assert saved.changed_locator_row_ids == (locator_id,)
    assert saved.changed_link_row_ids == (link_id,)
    audits = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.entity_type == "technical_intake_draft")
        .order_by(AuditEvent.created_at, AuditEvent.id)
    ).all()
    assert [audit.action for audit in audits] == ["start", "save"]
    save_audit = audits[-1]
    assert save_audit.reason == "Transcribed and linked the cited row."
    assert set(save_audit.previous_value or {}) == {"payload_sha256"}
    assert set(save_audit.new_value or {}) == {
        "changed_field_row_ids",
        "changed_link_row_ids",
        "changed_locator_row_ids",
        "payload_sha256",
    }
    audit_json = json.dumps(
        {
            "previous": save_audit.previous_value,
            "new": save_audit.new_value,
        },
        sort_keys=True,
    )
    assert "20 mm" not in audit_json
    assert "Source wording" not in audit_json
    assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 0
    assert db.scalar(select(func.count()).select_from(Approval)) == 0
    assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 0


def test_save_uses_stored_file_document_then_draft_global_lock_order(
    db: Session,
) -> None:
    author = _user(db, "author@example.test")
    document, stored, _path = _document(db, uploaded_by=author)
    draft = start_or_resume_technical_intake_draft(
        db,
        actor=author,
        technical_document_id=document.id,
    ).draft
    expected_entities = (StoredFile, TechnicalDocument, TechnicalIntakeDraft)
    locked_entities: list[type[object]] = []

    def observe_lock(execute_state: Any) -> None:
        statement = execute_state.statement
        if getattr(statement, "_for_update_arg", None) is None:
            return
        entities = tuple(
            description.get("entity")
            for description in getattr(statement, "column_descriptions", ())
        )
        for entity in expected_entities:
            if entity in entities:
                locked_entities.append(entity)
                break

    event.listen(db, "do_orm_execute", observe_lock)
    try:
        save_technical_intake_draft(
            db,
            actor=author,
            draft_id=draft.id,
            expected_record_version=1,
            payload_json=_encode(_payload(document, stored)),
            reason="Verify consistent lock ordering",
        )
    finally:
        event.remove(db, "do_orm_execute", observe_lock)

    assert tuple(locked_entities) == expected_entities


def test_source_binding_change_between_discovery_and_document_lock_is_rejected(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    author = _user(db, "binding-race-author@example.test")
    document, _stored, _path = _document(
        db,
        uploaded_by=author,
        document_id="BINDING-RACE-SOURCE",
    )
    _replacement_document, replacement, _replacement_path = _document(
        db,
        uploaded_by=author,
        document_id="BINDING-RACE-REPLACEMENT",
    )
    original_scalar = db.scalar
    binding_changed = False

    def scalar(statement: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal binding_changed
        result = original_scalar(statement, *args, **kwargs)
        descriptions = getattr(statement, "column_descriptions", ())
        entity = descriptions[0].get("entity") if descriptions else None
        if (
            entity is StoredFile
            and getattr(statement, "_for_update_arg", None) is not None
            and not binding_changed
        ):
            binding_changed = True
            db.execute(
                update(TechnicalDocument)
                .where(TechnicalDocument.id == document.id)
                .values(stored_file_id=replacement.id)
                .execution_options(synchronize_session=False)
            )
        return result

    monkeypatch.setattr(db, "scalar", scalar)

    _assert_error(
        "TECHNICAL_INTAKE_DRAFT_SOURCE_FILE_INVALID",
        lambda: start_or_resume_technical_intake_draft(
            db,
            actor=author,
            technical_document_id=document.id,
        ),
    )
    assert binding_changed is True


def test_save_rejects_blank_reason_without_mutating_the_draft(db: Session) -> None:
    author = _user(db, "author@example.test")
    document, stored, _path = _document(db, uploaded_by=author)
    draft = start_or_resume_technical_intake_draft(
        db,
        actor=author,
        technical_document_id=document.id,
    ).draft
    db.commit()

    _assert_error(
        "TECHNICAL_INTAKE_DRAFT_REASON_INVALID",
        lambda: save_technical_intake_draft(
            db,
            actor=author,
            draft_id=draft.id,
            expected_record_version=1,
            payload_json=_encode(_payload(document, stored)),
            reason=" \t\r\n ",
        ),
    )
    db.rollback()
    persisted = db.get(TechnicalIntakeDraft, draft.id)
    assert persisted is not None
    assert persisted.record_version == 1
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.entity_type == "technical_intake_draft")
        )
        == 1
    )


def test_stale_save_accepts_only_exact_current_hash_as_idempotent_replay(
    db: Session,
) -> None:
    author = _user(db, "author@example.test")
    document, stored, _path = _document(db, uploaded_by=author)
    draft = start_or_resume_technical_intake_draft(
        db,
        actor=author,
        technical_document_id=document.id,
    ).draft
    first_payload = _payload(document, stored)
    first = save_technical_intake_draft(
        db,
        actor=author,
        draft_id=draft.id,
        expected_record_version=1,
        payload_json=_encode(first_payload),
        reason="First save",
    )
    db.flush()
    audit_count = db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.entity_type == "technical_intake_draft")
    )

    replay = save_technical_intake_draft(
        db,
        actor=author,
        draft_id=draft.id,
        expected_record_version=1,
        payload_json=_encode(first_payload),
        reason="Network replay",
    )
    changed = copy.deepcopy(first_payload)
    changed["fields"][0]["normalized_value"] = "25"
    _assert_error(
        "TECHNICAL_INTAKE_DRAFT_STALE",
        lambda: save_technical_intake_draft(
            db,
            actor=author,
            draft_id=draft.id,
            expected_record_version=1,
            payload_json=_encode(changed),
            reason="Stale conflicting edit",
        ),
    )
    _assert_error(
        "TECHNICAL_INTAKE_DRAFT_STALE",
        lambda: save_technical_intake_draft(
            db,
            actor=author,
            draft_id=draft.id,
            expected_record_version=3,
            payload_json=_encode(first_payload),
            reason="Future version is not a replay",
        ),
    )

    assert first.draft.record_version == 2
    assert replay.idempotent_replay is True
    assert replay.draft.record_version == 2
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.entity_type == "technical_intake_draft")
        )
        == audit_count
    )


def test_get_and_list_reject_noncanonical_or_hash_tampered_persistence(
    db: Session,
) -> None:
    author = _user(db, "author@example.test")
    document, stored, _path = _document(db, uploaded_by=author)
    draft = start_or_resume_technical_intake_draft(
        db,
        actor=author,
        technical_document_id=document.id,
    ).draft
    saved = save_technical_intake_draft(
        db,
        actor=author,
        draft_id=draft.id,
        expected_record_version=1,
        payload_json=_encode(_payload(document, stored)),
        reason="Persist one canonical row",
    ).draft
    db.commit()
    corrupted = copy.deepcopy(saved.payload_json)
    corrupted["locators"][0]["region"]["x0"] = "0.10"
    saved.payload_json = corrupted
    saved.payload_sha256 = hashlib.sha256(
        json.dumps(
            corrupted,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    db.commit()

    _assert_error(
        "TECHNICAL_INTAKE_DRAFT_PERSISTENCE_CONFLICT",
        lambda: get_owned_technical_intake_draft(
            db,
            actor=author,
            draft_id=saved.id,
        ),
    )
    _assert_error(
        "TECHNICAL_INTAKE_DRAFT_PERSISTENCE_CONFLICT",
        lambda: list_owned_technical_intake_drafts(db, actor=author),
    )


def test_get_rejects_float_source_size_even_when_it_compares_equal_to_root(
    db: Session,
) -> None:
    author = _user(db, "author@example.test")
    document, stored, _path = _document(db, uploaded_by=author)
    draft = start_or_resume_technical_intake_draft(
        db,
        actor=author,
        technical_document_id=document.id,
    ).draft
    saved = save_technical_intake_draft(
        db,
        actor=author,
        draft_id=draft.id,
        expected_record_version=1,
        payload_json=_encode(_payload(document, stored)),
        reason="Persist one canonical row",
    ).draft
    db.commit()
    corrupted = copy.deepcopy(saved.payload_json)
    corrupted["locators"][0]["source_size_bytes"] = float(stored.size_bytes)
    assert corrupted["locators"][0]["source_size_bytes"] == stored.size_bytes
    saved.payload_json = corrupted
    saved.payload_sha256 = hashlib.sha256(
        json.dumps(
            corrupted,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    db.commit()

    _assert_error(
        "TECHNICAL_INTAKE_DRAFT_PERSISTENCE_CONFLICT",
        lambda: get_owned_technical_intake_draft(
            db,
            actor=author,
            draft_id=saved.id,
        ),
    )


def test_service_never_commits_the_callers_transaction(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    author = _user(db, "author@example.test")
    document, stored, _path = _document(db, uploaded_by=author)

    def unexpected_commit() -> None:
        pytest.fail("Draft service must not commit the caller's transaction")

    monkeypatch.setattr(db, "commit", unexpected_commit)
    draft = start_or_resume_technical_intake_draft(
        db,
        actor=author,
        technical_document_id=document.id,
    ).draft
    result = save_technical_intake_draft(
        db,
        actor=author,
        draft_id=draft.id,
        expected_record_version=1,
        payload_json=_encode(_payload(document, stored)),
        reason="Save within the caller-owned transaction",
    )

    assert result.draft.record_version == 2
