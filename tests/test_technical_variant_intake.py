# ruff: noqa: S106
from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from classifire import models, physical_models  # noqa: F401
from classifire.config import get_settings
from classifire.db import Base
from classifire.models import (
    Approval,
    AuditEvent,
    LibraryRelease,
    StoredFile,
    TechnicalDocument,
    TechnicalVariant,
    User,
)
from classifire.services import technical_variant_intake as intake_module
from classifire.services.technical import search_variants
from classifire.services.technical_document_metadata import (
    TECHNICAL_SOURCE_REGISTRATION_SCHEMA,
)
from classifire.services.technical_document_review import (
    TECHNICAL_DOCUMENT_REVIEW_POLICY,
)
from classifire.services.technical_governance import (
    APPROVED_RELEASE_CANDIDATE,
    PENDING_TECHNICAL_REVIEW,
    TECHNICAL_REVIEW_APPROVAL_TYPE,
    release_candidate_blockers,
)
from classifire.services.technical_variant_intake import (
    TECHNICAL_VARIANT_UI_INTAKE_POLICY,
    TechnicalVariantDraftInput,
    TechnicalVariantIntakeError,
    create_initial_technical_variant_draft,
)
from classifire.technical_admin import (
    technical_document_detail,
    technical_variant_approve,
    technical_variant_create,
    technical_variant_create_page,
    technical_variant_detail,
    technical_variant_submit_review,
)


@pytest.fixture(autouse=True)
def governed_storage_root(tmp_path, monkeypatch):
    root = tmp_path / "storage"
    monkeypatch.setenv("CLASSIFIRE_STORAGE_ROOT", str(root))
    get_settings.cache_clear()
    try:
        yield root
    finally:
        get_settings.cache_clear()


@pytest.fixture
def db():
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


def _user(db: Session, email: str, role: str = "technical_reviewer") -> User:
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


def _request(user: User, *, method: str = "POST", csrf: str = "csrf-token") -> Request:
    path = "/technical"
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
            "session": {"user_id": user.id, "csrf_token": csrf},
        }
    )


def _document(
    db: Session,
    *,
    document_id: str = "REPORT-001",
    status: str = "draft",
    uploaded_by: User | None = None,
) -> TechnicalDocument:
    content = f"retained technical evidence for {document_id}".encode()
    digest = hashlib.sha256(content).hexdigest()
    root = get_settings().storage_root
    path = root / digest[:2] / digest[2:4] / f"{digest}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    stored = StoredFile(
        original_filename=f"{digest}.pdf",
        media_type="application/pdf",
        storage_path=str(path),
        sha256=digest,
        size_bytes=len(content),
        purpose="technical_evidence",
        malware_scan_status="clean",
        uploaded_by_id=uploaded_by.id if uploaded_by else None,
        immutable=True,
    )
    db.add(stored)
    db.flush()
    document = TechnicalDocument(
        document_id=document_id,
        stored_file_id=stored.id,
        document_type="test_report",
        declared_source_role="primary_test",
        artifact_provenance_status="unknown",
        evidence_scope="full_source",
        manufacturer="Example Manufacturer",
        title=f"Test report {document_id}",
        reference=document_id,
        jurisdiction="AU",
        status=status,
        metadata_json={
            "human_review_required": True,
            "source_review_policy": TECHNICAL_DOCUMENT_REVIEW_POLICY,
            "source_registration_schema": TECHNICAL_SOURCE_REGISTRATION_SCHEMA,
            "uploaded_by_id": uploaded_by.id if uploaded_by else None,
        },
    )
    db.add(document)
    db.commit()
    return document


def _values(variant_id: str = "VAR-001", **overrides: Any) -> TechnicalVariantDraftInput:
    values = TechnicalVariantDraftInput(
        variant_id=variant_id,
        system_id="SYS-001",
        source_page="12",
        source_table="Table 3",
        source_figure="Figure 2",
        reason="Create one report-bound Draft configuration",
        manufacturer="Example Manufacturer",
        product_family="Example System",
        service_type="pipe",
        service_material="steel",
        minimum_service_size_mm=Decimal("20"),
        maximum_service_size_mm=Decimal("100"),
        permitted_service_quantity="one",
        insulation_type="mineral wool",
        insulation_thickness_mm=Decimal("25"),
        substrate_type="flexible wall",
        minimum_substrate_thickness_mm=Decimal("75"),
        maximum_substrate_thickness_mm=Decimal("150"),
        orientation="vertical",
        installation_face="both faces",
        opening_type="circular",
        opening_dimensions="120 mm diameter",
        annular_gap_min_mm=Decimal("10"),
        annular_gap_max_mm=Decimal("20"),
        service_spacing_rules="Minimum 30 mm",
        edge_distance_rules="Minimum 50 mm",
        support_rules="Support within stated distance",
        fixing_rules="Install to report detail",
        component_requirements={"sealant": {"depth_mm": 20}},
        labour_requirements=["prepare opening", "install seal"],
        hard_exclusions="No bundled services",
        dependencies="Use tested backing material",
        frl="-/120/120",
        jurisdiction="AU",
    )
    return replace(values, **overrides)


def _route_create(
    db: Session,
    document: TechnicalDocument,
    actor: User,
    *,
    variant_id: str,
    **overrides: Any,
):
    payload: dict[str, Any] = {
        "csrf_token": "csrf-token",
        "variant_id": variant_id,
        "system_id": "SYS-001",
        "source_page": "12",
        "reason": "Create source-bound Draft technical configuration",
        "source_table": "Table 3",
        "source_figure": "Figure 2",
        "manufacturer": "Example Manufacturer",
        "product_family": "Example System",
        "service_type": "pipe",
        "service_material": "steel",
        "minimum_service_size_mm": "20",
        "maximum_service_size_mm": "100",
        "permitted_service_quantity": "one",
        "insulation_type": "mineral wool",
        "insulation_thickness_mm": "25",
        "substrate_type": "flexible wall",
        "minimum_substrate_thickness_mm": "75",
        "maximum_substrate_thickness_mm": "150",
        "orientation": "vertical",
        "installation_face": "both faces",
        "opening_type": "circular",
        "opening_dimensions": "120 mm diameter",
        "annular_gap_min_mm": "10",
        "annular_gap_max_mm": "20",
        "service_spacing_rules": "Minimum 30 mm",
        "edge_distance_rules": "Minimum 50 mm",
        "support_rules": "Support within stated distance",
        "fixing_rules": "Install to report detail",
        "component_requirements_json": '{"sealant":{"depth_mm":20}}',
        "labour_requirements_json": '["prepare opening","install seal"]',
        "hard_exclusions": "No bundled services",
        "dependencies": "Use tested backing material",
        "frl": "-/120/120",
        "jurisdiction": "AU",
    }
    payload.update(overrides)
    return technical_variant_create(
        document.id,
        _request(actor),
        db,
        **payload,
    )


def _nonblocked_candidate(
    db: Session,
    document: TechnicalDocument,
    *,
    variant_id: str,
    source_json: dict[str, Any],
) -> TechnicalVariant:
    stored = db.get(StoredFile, document.stored_file_id)
    assert stored is not None
    variant = TechnicalVariant(
        variant_id=variant_id,
        system_id="SYS-001",
        technical_document_id=document.id,
        source_document_reference=document.document_id,
        source_page="12",
        service_type="pipe",
        service_material="steel",
        frl="-/120/120",
        search_eligibility=PENDING_TECHNICAL_REVIEW,
        expert_review_required=True,
        status="draft",
        source_hash=stored.sha256,
        source_json=source_json,
    )
    db.add(variant)
    db.commit()
    return variant


def test_ui_creates_two_source_bound_drafts_without_runtime_authority(db):
    author = _user(db, "author@example.test")
    document = _document(db, uploaded_by=author)

    first_response = _route_create(db, document, author, variant_id="VAR-001")
    second_response = _route_create(
        db,
        document,
        author,
        variant_id="VAR-002",
        system_id="SYS-002",
        source_page="18",
    )

    assert first_response.status_code == 303
    assert second_response.status_code == 303
    variants = db.scalars(
        select(TechnicalVariant).order_by(TechnicalVariant.variant_id)
    ).all()
    assert [item.variant_id for item in variants] == ["VAR-001", "VAR-002"]
    for variant in variants:
        assert variant.technical_document_id == document.id
        assert variant.source_document_reference == document.document_id
        assert variant.source_hash == db.get(StoredFile, document.stored_file_id).sha256
        assert variant.status == "draft"
        assert variant.search_eligibility == PENDING_TECHNICAL_REVIEW
        assert variant.expert_review_required is True
        assert variant.release_id is None
        assert variant.supersedes_id is None
        assert variant.permitted_service_quantity == "one"
        assert variant.insulation_type == "mineral wool"
        assert variant.insulation_thickness_mm == Decimal("25")
        assert variant.installation_face == "both faces"
        assert variant.source_json["intake_policy"] == TECHNICAL_VARIANT_UI_INTAKE_POLICY
        assert variant.source_json["automatic_activation_permitted"] is False
        assert variant.source_json["created_by_id"] == author.id
    assert db.scalar(select(func.count()).select_from(Approval)) == 0
    assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 0
    assert search_variants(db, service_type="pipe") == []
    audits = db.scalars(
        select(AuditEvent).where(AuditEvent.action == "create_initial_draft")
    ).all()
    assert len(audits) == 2


def test_source_page_uses_intake_draft_action_while_legacy_form_stays_bound(db):
    author = _user(db, "author@example.test")
    document = _document(db, uploaded_by=author)

    detail = technical_document_detail(
        document.id,
        _request(author, method="GET"),
        db,
        get_settings(),
    )
    form = technical_variant_create_page(
        document.id,
        _request(author, method="GET"),
        db,
    )

    detail_html = detail.body.decode()
    form_html = form.body.decode()
    assert f'/technical/documents/{document.id}/intake-draft' in detail_html
    assert f"/technical/documents/{document.id}/variants/new" not in detail_html
    assert f'action="/technical/documents/{document.id}/variants"' in form_html
    assert document.document_id in form_html
    assert db.get(StoredFile, document.stored_file_id).sha256 in form_html
    assert 'name="source_document_reference"' not in form_html
    assert "cannot approve the source" in form_html


@pytest.mark.parametrize("status", ["draft", "rejected"])
def test_ui_policy_coarse_variant_cannot_submit_directly_or_mutate_review_state(
    db,
    status,
):
    author = _user(db, "blocked-author@example.test")
    document = _document(db, uploaded_by=author)
    _route_create(db, document, author, variant_id=f"BLOCKED-{status.upper()}")
    variant = db.scalar(
        select(TechnicalVariant).where(
            TechnicalVariant.variant_id == f"BLOCKED-{status.upper()}"
        )
    )
    variant.status = status
    db.commit()

    detail = technical_variant_detail(
        variant.id,
        _request(author, method="GET"),
        db,
    )
    detail_html = detail.body.decode()
    assert "Field-level technical intake required" in detail_html
    assert f'href="/technical/documents/{document.id}"' in detail_html
    assert f'action="/technical/variants/{variant.id}/submit-review"' not in detail_html

    approval_count = db.scalar(select(func.count()).select_from(Approval))
    audit_count = db.scalar(select(func.count()).select_from(AuditEvent))
    blocked = technical_variant_submit_review(
        variant.id,
        _request(author),
        db,
        csrf_token="csrf-token",
        reason="Attempt direct review submission of a coarse UI Draft",
    )

    assert blocked.status_code == 303
    assert blocked.headers["location"].endswith(
        "?error=TECHNICAL_VARIANT_FIELD_INTAKE_REQUIRED"
    )
    db.expire_all()
    persisted = db.get(TechnicalVariant, variant.id)
    assert persisted is not None
    assert persisted.status == status
    assert db.scalar(select(func.count()).select_from(Approval)) == approval_count
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == audit_count


def test_legacy_candidate_without_ui_policy_can_still_submit_for_review(db):
    submitter = _user(db, "legacy-submit@example.test")
    document = _document(db, uploaded_by=submitter)
    variant = _nonblocked_candidate(
        db,
        document,
        variant_id="LEGACY-CANDIDATE",
        source_json={"legacy_import": True},
    )

    submitted = technical_variant_submit_review(
        variant.id,
        _request(submitter),
        db,
        csrf_token="csrf-token",
        reason="Submit retained legacy candidate for independent review",
    )

    assert submitted.status_code == 303
    assert submitted.headers["location"].endswith(
        "?success=Submitted+for+technical+review"
    )
    db.refresh(variant)
    assert variant.status == "in_review"
    approval = db.scalar(
        select(Approval).where(
            Approval.entity_type == "technical_variant",
            Approval.entity_id == variant.id,
        )
    )
    assert approval is not None
    assert approval.status == "pending"
    assert db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.entity_type == "technical_variant",
            AuditEvent.entity_id == variant.id,
            AuditEvent.action == "submit_review",
        )
    ) == 1


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"variant_id": "ROOT-QFREV01"}, "TECHNICAL_DRAFT_VARIANT_ID_RESERVED"),
        (
            {"minimum_service_size_mm": Decimal("-1")},
            "TECHNICAL_DRAFT_NUMERIC_RANGE_INVALID",
        ),
        (
            {
                "minimum_service_size_mm": Decimal("101"),
                "maximum_service_size_mm": Decimal("100"),
            },
            "TECHNICAL_DRAFT_NUMERIC_RANGE_INVALID",
        ),
        (
            {"minimum_service_size_mm": Decimal("1.00001")},
            "TECHNICAL_DRAFT_NUMERIC_RANGE_INVALID",
        ),
        (
            {"minimum_service_size_mm": Decimal("100000000000000")},
            "TECHNICAL_DRAFT_NUMERIC_RANGE_INVALID",
        ),
        (
            {"minimum_service_size_mm": Decimal("Infinity")},
            "TECHNICAL_DRAFT_NUMERIC_RANGE_INVALID",
        ),
        (
            {"variant_id": "BAD\nID"},
            "TECHNICAL_DRAFT_FIELD_INVALID",
        ),
        (
            {"orientation": "x" * 501},
            "TECHNICAL_DRAFT_FIELD_INVALID",
        ),
        (
            {"component_requirements": cast(Any, "not structured")},
            "TECHNICAL_DRAFT_COMPONENT_REQUIREMENTS_INVALID",
        ),
        (
            {"labour_requirements": cast(Any, ["valid", ""])},
            "TECHNICAL_DRAFT_LABOUR_REQUIREMENTS_INVALID",
        ),
    ],
)
def test_invalid_draft_values_fail_atomically(db, overrides, code):
    author = _user(db, "author@example.test")
    document = _document(db, uploaded_by=author)

    with pytest.raises(TechnicalVariantIntakeError, match=code):
        create_initial_technical_variant_draft(
            db,
            actor=author,
            technical_document_id=document.id,
            values=_values(**overrides),
        )

    assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 0
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_rejected_or_tampered_source_cannot_create_a_draft(db):
    author = _user(db, "author@example.test")
    rejected = _document(
        db,
        document_id="REJECTED",
        status="rejected",
        uploaded_by=author,
    )

    with pytest.raises(
        TechnicalVariantIntakeError,
        match="TECHNICAL_DRAFT_DOCUMENT_NOT_AUTHORABLE",
    ):
        create_initial_technical_variant_draft(
            db,
            actor=author,
            technical_document_id=rejected.id,
            values=_values(),
        )

    clean = _document(db, document_id="TAMPERED", uploaded_by=author)
    stored = db.get(StoredFile, clean.stored_file_id)
    with open(stored.storage_path, "ab") as handle:
        handle.write(b"tampered")
    with pytest.raises(
        TechnicalVariantIntakeError,
        match="TECHNICAL_DRAFT_SOURCE_FILE_INVALID",
    ):
        create_initial_technical_variant_draft(
            db,
            actor=author,
            technical_document_id=clean.id,
            values=_values(),
        )

    assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 0
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_route_rejects_malformed_forms_permissions_and_csrf(db):
    author = _user(db, "author@example.test")
    reader = _user(db, "reader@example.test", role="read_only")
    document = _document(db, uploaded_by=author)

    malformed_json = _route_create(
        db,
        document,
        author,
        variant_id="BAD-JSON",
        component_requirements_json="{",
    )
    invalid_range = _route_create(
        db,
        document,
        author,
        variant_id="BAD-RANGE",
        minimum_service_size_mm="101",
        maximum_service_size_mm="100",
    )
    assert "TECHNICAL_DRAFT_JSON_INVALID" in malformed_json.headers["location"]
    assert "TECHNICAL_DRAFT_NUMERIC_RANGE_INVALID" in invalid_range.headers["location"]

    with pytest.raises(HTTPException) as denied:
        _route_create(db, document, reader, variant_id="DENIED")
    assert denied.value.status_code == 403

    with pytest.raises(HTTPException) as bad_csrf:
        technical_variant_create(
            document.id,
            _request(author),
            db,
            csrf_token="wrong",
            variant_id="BAD-CSRF",
            system_id="SYS",
            source_page="1",
            reason="Should not be created",
        )
    assert bad_csrf.value.status_code == 403
    assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 0
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_database_unique_constraint_wins_if_duplicate_precheck_races(
    db,
    monkeypatch,
):
    author = _user(db, "author@example.test")
    document = _document(db, uploaded_by=author)
    created = _route_create(db, document, author, variant_id="RACE-VAR")
    assert created.status_code == 303
    original_scalar = db.scalar

    def hide_duplicate(statement, *args, **kwargs):
        descriptions = getattr(statement, "column_descriptions", ())
        if descriptions and descriptions[0].get("entity") is TechnicalVariant:
            return None
        return original_scalar(statement, *args, **kwargs)

    monkeypatch.setattr(db, "scalar", hide_duplicate)
    raced = _route_create(db, document, author, variant_id="RACE-VAR")

    assert "TECHNICAL_DRAFT_VARIANT_ID_CONFLICT" in raced.headers["location"]
    assert original_scalar(select(func.count()).select_from(TechnicalVariant)) == 1
    assert (
        original_scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "create_initial_draft")
        )
        == 1
    )


def test_audit_failure_rolls_back_the_flushed_variant(db, monkeypatch):
    author = _user(db, "author@example.test")
    document = _document(db, uploaded_by=author)

    def fail_audit(*args, **kwargs):
        raise SQLAlchemyError("forced audit failure")

    monkeypatch.setattr(intake_module, "record_audit", fail_audit)
    response = _route_create(db, document, author, variant_id="ROLLBACK-VAR")

    assert "TECHNICAL_DRAFT_PERSISTENCE_CONFLICT" in response.headers["location"]
    assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 0
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_initial_draft_author_cannot_approve_after_another_user_submits(db):
    author = _user(db, "author@example.test")
    submitter = _user(db, "submitter@example.test")
    document = _document(db, uploaded_by=author)
    variant = _nonblocked_candidate(
        db,
        document,
        variant_id="VAR-INDEPENDENT",
        source_json={
            "user_revision": True,
            "revision_created_by_id": author.id,
            "source_authority_preserved": True,
        },
    )

    submitted = technical_variant_submit_review(
        variant.id,
        _request(submitter),
        db,
        csrf_token="csrf-token",
        reason="Submit the author's Draft for independent review",
    )
    attempted = technical_variant_approve(
        variant.id,
        _request(author),
        db,
        csrf_token="csrf-token",
        reason="Attempt self-approval",
    )

    assert submitted.status_code == 303
    assert "Draft+author+cannot+approve" in attempted.headers["location"]
    db.refresh(variant)
    assert variant.status == "in_review"
    approval = db.scalar(
        select(Approval).where(
            Approval.entity_type == "technical_variant",
            Approval.entity_id == variant.id,
        )
    )
    assert approval.status == "pending"
    assert approval.decided_by_id is None
    assert search_variants(db, service_type="pipe") == []


def test_release_blocker_rejects_forged_creator_approval(db):
    author = _user(db, "author@example.test")
    requester = _user(db, "requester@example.test")
    document = _document(db, uploaded_by=author)
    _route_create(db, document, author, variant_id="FORGED-APPROVAL")
    variant = db.scalar(
        select(TechnicalVariant).where(
            TechnicalVariant.variant_id == "FORGED-APPROVAL"
        )
    )
    now = datetime.now(UTC)
    variant.status = "approved"
    variant.search_eligibility = APPROVED_RELEASE_CANDIDATE
    db.add(
        Approval(
            entity_type="technical_variant",
            entity_id=variant.id,
            approval_type=TECHNICAL_REVIEW_APPROVAL_TYPE,
            status="approved",
            requested_by_id=requester.id,
            decided_by_id=author.id,
            requested_at=now,
            decided_at=now,
            decision_reason="Forged creator approval",
            snapshot_hash="0" * 64,
        )
    )
    db.commit()

    blockers, approval, _binding = release_candidate_blockers(db, variant)

    assert approval is not None
    assert "independent_candidate_author_reviewer_required" in blockers
