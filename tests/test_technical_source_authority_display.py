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


def test_variant_detail_maps_each_revision_to_its_retained_document(monkeypatch) -> None:
    with physical_session() as db:
        document = _document(db)
        variant = _variant(db, technical_document_id=document.id)

        context = _detail_context(monkeypatch, db, variant)

        assert context["history_documents_by_id"] == {document.id: document}


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
        "history_documents_by_id": {},
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


def test_variant_detail_template_renders_read_only_revision_source_lineage() -> None:
    template = technical_admin.templates.get_template("technical_variant_detail.html")
    document = SimpleNamespace(
        id="document-record-id",
        document_id="TECH-SOURCE-AUTHORITY-TEST",
    )
    history = (
        SimpleNamespace(
            id="revision-record-id",
            variant_id="TECH-SOURCE-AUTHORITY-TEST-QFREV1",
            frl="- / 120 / 120",
            status="draft",
            technical_document_id=document.id,
            source_document_reference=document.document_id,
            source_page="42",
            source_table="Table 7",
            source_figure="Figure 2",
            created_at="2026-09-03T00:00:00Z",
        ),
    )

    template_context = {"csrf_token": "test-csrf-token"}
    html = template.render(
        request=SimpleNamespace(query_params=QueryParams()),
        user=SimpleNamespace(full_name="Technical reviewer", role="administrator"),
        **template_context,
        attribution="CLASSIFIRE",
        has_permission=lambda _permission: False,
        variant=SimpleNamespace(
            id="variant-record-id",
            variant_id="TECH-SOURCE-AUTHORITY-TEST",
            status="active",
            system_id="SYSTEM-SOURCE-AUTHORITY-TEST",
            expert_review_required=True,
        ),
        history=history,
        history_documents_by_id={document.id: document},
        approvals=(),
        linked_document=None,
        matching_document=None,
        source_authority_state="unbound",
        source_authority_messages=(),
    )

    assert "read-only evidence lineage; it does not approve or activate a variant" in html
    assert 'href="/technical/documents/document-record-id"' in html
    assert "TECH-SOURCE-AUTHORITY-TEST" in html
    assert "Document: TECH-SOURCE-AUTHORITY-TEST" in html
    assert "Page: 42 · Table: Table 7 · Figure: Figure 2" in html


def test_variant_detail_template_marks_unbound_and_missing_revision_sources() -> None:
    template = technical_admin.templates.get_template("technical_variant_detail.html")
    history = (
        SimpleNamespace(
            id="legacy-record-id",
            variant_id="TECH-SOURCE-AUTHORITY-TEST",
            frl=None,
            status="superseded",
            technical_document_id=None,
            source_document_reference="LEGACY-REF",
            source_page="7",
            source_table=None,
            source_figure=None,
            created_at="2026-09-02T00:00:00Z",
        ),
        SimpleNamespace(
            id="missing-document-record-id",
            variant_id="TECH-SOURCE-AUTHORITY-TEST-QFREV1",
            frl=None,
            status="draft",
            technical_document_id="missing-document-id",
            source_document_reference="MISSING-REF",
            source_page="8",
            source_table=None,
            source_figure=None,
            created_at="2026-09-03T00:00:00Z",
        ),
    )

    template_context = {"csrf_token": "test-csrf-token"}
    html = template.render(
        request=SimpleNamespace(query_params=QueryParams()),
        user=SimpleNamespace(full_name="Technical reviewer", role="administrator"),
        **template_context,
        attribution="CLASSIFIRE",
        has_permission=lambda _permission: False,
        variant=SimpleNamespace(
            id="variant-record-id",
            variant_id="TECH-SOURCE-AUTHORITY-TEST",
            status="active",
            system_id="SYSTEM-SOURCE-AUTHORITY-TEST",
            expert_review_required=True,
        ),
        history=history,
        history_documents_by_id={},
        approvals=(),
        linked_document=None,
        matching_document=None,
        source_authority_state="unbound",
        source_authority_messages=(),
    )

    assert "Unbound legacy record" in html
    assert "Missing bound document" in html


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
