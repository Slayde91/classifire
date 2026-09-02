from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from physical_foundation_support import physical_session
from sqlalchemy.orm import Session
from starlette.datastructures import QueryParams

from classifire import technical_admin
from classifire.models import StoredFile, TechnicalDocument, TechnicalVariant


def _variant(db: Session, *, technical_document_id: str | None = None) -> TechnicalVariant:
    variant = TechnicalVariant(
        variant_id="TECH-SOURCE-AUTHORITY-TEST",
        system_id="SYSTEM-SOURCE-AUTHORITY-TEST",
        source_document_reference="TECH-SOURCE-AUTHORITY-TEST",
        source_page="12",
        source_json={"fixture": "source-authority-display"},
        status="active",
        expert_review_required=True,
        technical_document_id=technical_document_id,
    )
    db.add(variant)
    db.flush()
    return variant


def _document(
    db: Session,
    *,
    status: str = "approved",
    expiry_date: date | None = None,
    scan_status: str = "clean",
) -> TechnicalDocument:
    stored = StoredFile(
        original_filename="source.pdf",
        media_type="application/pdf",
        storage_path="technical/source.pdf",
        sha256="a" * 64,
        size_bytes=1,
        purpose="technical_evidence",
        malware_scan_status=scan_status,
        immutable=True,
    )
    db.add(stored)
    db.flush()
    document = TechnicalDocument(
        document_id="TECH-SOURCE-AUTHORITY-TEST",
        stored_file_id=stored.id,
        document_type="assessment",
        title="Technical source",
        status=status,
        expiry_date=expiry_date,
    )
    db.add(document)
    db.flush()
    return document


def _detail_context(
    monkeypatch,
    db: Session,
    variant: TechnicalVariant,
) -> dict[str, object]:
    captured: dict[str, object] = {}
    monkeypatch.setattr(technical_admin, "_require", lambda *_args: object())
    monkeypatch.setattr(
        technical_admin,
        "_context",
        lambda _request, _db, **values: values,
    )
    monkeypatch.setattr(
        technical_admin.templates,
        "TemplateResponse",
        lambda _request, name, context: captured.update(name=name, context=context),
    )

    technical_admin.technical_variant_detail(variant.id, object(), db)  # type: ignore[arg-type]

    return captured["context"]  # type: ignore[return-value]


def test_variant_detail_displays_current_bound_source_authority(monkeypatch) -> None:
    with physical_session() as db:
        document = _document(db)
        variant = _variant(db, technical_document_id=document.id)

        context = _detail_context(monkeypatch, db, variant)

        assert context["source_authority_state"] == "current"
        assert context["source_authority_messages"] == ()


def test_variant_detail_displays_safe_reasons_when_bound_source_is_blocked(monkeypatch) -> None:
    with physical_session() as db:
        document = _document(
            db,
            expiry_date=date.today() - timedelta(days=1),
            scan_status="malware_detected",
        )
        variant = _variant(db, technical_document_id=document.id)

        context = _detail_context(monkeypatch, db, variant)

        assert context["source_authority_state"] == "blocked"
        assert context["source_authority_messages"] == (
            "The source document has expired.",
            "The retained file does not have a clean scan state.",
        )


def test_variant_detail_displays_legacy_unbound_status_without_claiming_current_authority(
    monkeypatch,
) -> None:
    with physical_session() as db:
        variant = _variant(db)

        context = _detail_context(monkeypatch, db, variant)

        assert context["source_authority_state"] == "unbound"
        assert context["source_authority_messages"] == ()


def test_variant_detail_template_renders_current_blocked_and_unbound_source_authority() -> None:
    template = technical_admin.templates.get_template("technical_variant_detail.html")
    common = {
        "request": SimpleNamespace(query_params=QueryParams()),
        "user": SimpleNamespace(full_name="Technical reviewer", role="administrator"),
        "csrf_token": "test-csrf-token",
        "attribution": "CLASSIFIRE",
        "has_permission": lambda _permission: False,
        "variant": SimpleNamespace(
            id="variant-record-id",
            variant_id="TECH-SOURCE-AUTHORITY-TEST",
            status="active",
            system_id="SYSTEM-SOURCE-AUTHORITY-TEST",
            expert_review_required=True,
        ),
        "history": (),
        "approvals": (),
        "linked_document": None,
        "matching_document": None,
    }

    current_html = template.render(
        **common,
        source_authority_state="current",
        source_authority_messages=(),
    )
    blocked_html = template.render(
        **common,
        source_authority_state="blocked",
        source_authority_messages=("The source document has expired.",),
    )
    unbound_html = template.render(
        **common,
        source_authority_state="unbound",
        source_authority_messages=(),
    )

    assert "Bound source authority" in current_html
    assert "This does not replace technical approval." in current_html
    assert "The source document has expired." in blocked_html
    assert 'badge badge-blocked">Blocked' in blocked_html
    assert "Unbound legacy record" in unbound_html


def _document_detail_context(
    monkeypatch,
    db: Session,
    document: TechnicalDocument,
) -> dict[str, object]:
    captured: dict[str, object] = {}
    monkeypatch.setattr(technical_admin, "_require", lambda *_args: object())
    monkeypatch.setattr(
        technical_admin,
        "_context",
        lambda _request, _db, **values: values,
    )
    monkeypatch.setattr(
        technical_admin.templates,
        "TemplateResponse",
        lambda _request, name, context: captured.update(name=name, context=context),
    )

    technical_admin.technical_document_detail(document.id, object(), db)  # type: ignore[arg-type]

    return captured["context"]  # type: ignore[return-value]


def test_document_detail_displays_current_source_authority(monkeypatch) -> None:
    with physical_session() as db:
        document = _document(db)

        context = _document_detail_context(monkeypatch, db, document)

        assert context["source_authority_state"] == "current"
        assert context["source_authority_messages"] == ()


def test_document_detail_displays_safe_reasons_when_source_is_blocked(monkeypatch) -> None:
    with physical_session() as db:
        document = _document(db, status="in_review", scan_status="malware_detected")

        context = _document_detail_context(monkeypatch, db, document)

        assert context["source_authority_state"] == "blocked"
        assert context["source_authority_messages"] == (
            "The source document is not approved.",
            "The retained file does not have a clean scan state.",
        )


def test_document_detail_template_renders_current_and_blocked_source_authority() -> None:
    template = technical_admin.templates.get_template("technical_document_detail.html")
    common = {
        "request": SimpleNamespace(query_params=QueryParams()),
        "user": SimpleNamespace(full_name="Technical reviewer", role="administrator"),
        "csrf_token": "test-csrf-token",
        "attribution": "CLASSIFIRE",
        "has_permission": lambda _permission: False,
        "document": SimpleNamespace(
            id="document-record-id",
            document_id="TECH-SOURCE-AUTHORITY-TEST",
            title="Technical source",
            status="approved",
            document_type="assessment",
            manufacturer=None,
            reference=None,
            revision=None,
            extraction_status="complete",
        ),
        "linked": (),
        "approvals": (),
    }

    current_html = template.render(
        **common,
        source_authority_state="current",
        source_authority_messages=(),
    )
    blocked_html = template.render(
        **common,
        source_authority_state="blocked",
        source_authority_messages=("The source document is not approved.",),
    )

    assert "Current source authority" in current_html
    assert "This is a read-only current-use check" in current_html
    assert "The source document is not approved." in blocked_html
    assert 'badge badge-blocked">Blocked' in blocked_html
