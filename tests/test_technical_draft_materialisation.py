from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from physical_foundation_support import physical_session
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.datastructures import QueryParams

from classifire import technical_admin
from classifire.importers.technical import PENDING_REVIEW_SEARCH_ELIGIBILITY
from classifire.models import Approval, StoredFile, TechnicalDocument, TechnicalVariant, User
from classifire.services.technical import search_variants

TEST_CSRF_TOKEN = object()


def _user(db: Session, email: str) -> User:
    user = User(
        email=email,
        full_name=email,
        password_hash=email,
        role="administrator",
    )
    db.add(user)
    db.flush()
    return user


def _document(
    db: Session,
    *,
    source_root: Path,
    status: str = "draft",
    document_id: str = "TECH-MATERIALISE-SOURCE",
) -> TechnicalDocument:
    content = b"retained technical source for draft materialisation"
    digest = hashlib.sha256(content).hexdigest()
    path = source_root / digest[:2] / digest[2:4] / f"{digest}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    stored = StoredFile(
        original_filename="source.pdf",
        media_type="application/pdf",
        storage_path=str(path),
        sha256=digest,
        size_bytes=len(content),
        purpose="technical_evidence",
        malware_scan_status="clean",
        immutable=True,
    )
    db.add(stored)
    db.flush()
    document = TechnicalDocument(
        document_id=document_id,
        stored_file_id=stored.id,
        document_type="assessment",
        title="Retained technical source",
        manufacturer="Source manufacturer",
        status=status,
    )
    db.add(document)
    db.flush()
    return document


@pytest.fixture
def technical_storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    monkeypatch.setattr(
        technical_admin,
        "get_settings",
        lambda: SimpleNamespace(storage_root=storage_root),
    )
    return storage_root


@pytest.fixture
def materialise_as(monkeypatch: pytest.MonkeyPatch):
    events: list[dict[str, object]] = []
    monkeypatch.setattr(technical_admin, "verify_csrf", lambda *_args: None)
    monkeypatch.setattr(
        technical_admin,
        "record_audit",
        lambda *_args, **kwargs: events.append(kwargs),
    )

    def materialise(
        db: Session,
        document: TechnicalDocument,
        user: User,
        **overrides: str,
    ):
        monkeypatch.setattr(technical_admin, "_require", lambda *_args: user)
        values: dict[str, str] = {
            "variant_id": "TECH-DRAFT-001",
            "system_id": "SYSTEM-DRAFT-001",
            "source_page": "42",
            "source_table": "Table 7",
            "source_figure": "Figure 2",
            "product_family": "Firestop sealant",
            "service_type": "cable bundle",
            "service_material": "PVC",
            "minimum_service_size_mm": "10",
            "maximum_service_size_mm": "50",
            "substrate_type": "concrete wall",
            "minimum_substrate_thickness_mm": "100",
            "orientation": "vertical",
            "opening_type": "penetration",
            "annular_gap_max_mm": "20",
            "frl": "-/120/120",
            "component_requirements_json": '{"sealant": "source-cited"}',
            "labour_requirements_json": '["install sealant"]',
        }
        values.update(overrides)
        return technical_admin.technical_document_materialise(
            document.id,
            object(),  # type: ignore[arg-type]
            db,
            "csrf-token",
            **values,
        )

    return materialise, events


def test_materialisation_creates_a_source_bound_draft_without_authority(
    materialise_as,
    technical_storage_root: Path,
) -> None:
    materialise, events = materialise_as
    with physical_session() as db:
        writer = _user(db, "writer@example.test")
        document = _document(db, source_root=technical_storage_root)
        stored = db.get(StoredFile, document.stored_file_id)
        assert stored is not None

        result = materialise(db, document, writer)

        variant = db.scalar(
            select(TechnicalVariant).where(TechnicalVariant.variant_id == "TECH-DRAFT-001")
        )
        approvals = db.scalar(
            select(func.count())
            .select_from(Approval)
            .where(Approval.entity_type == "technical_variant")
        )
        assert "success=Source-bound+Draft+technical+variant+created" in result.headers["location"]
        assert variant is not None
        assert variant.status == "draft"
        assert variant.expert_review_required is True
        assert variant.release_id is None
        assert variant.search_eligibility == PENDING_REVIEW_SEARCH_ELIGIBILITY
        assert variant.technical_document_id == document.id
        assert variant.source_document_reference == document.document_id
        assert variant.source_page == "42"
        assert variant.source_table == "Table 7"
        assert variant.source_figure == "Figure 2"
        assert variant.source_hash == stored.sha256
        assert variant.component_requirements == {"sealant": "source-cited"}
        assert variant.labour_requirements == ["install sealant"]
        assert variant.source_json == {
            "intake_policy": "technical-document-draft-materialisation-v1",
            "source_kind": "manual_transcription_from_retained_technical_document",
            "technical_document": {
                "id": document.id,
                "document_id": document.document_id,
                "stored_file_id": stored.id,
                "sha256": stored.sha256,
                "size_bytes": stored.size_bytes,
            },
            "source_locator": {
                "page": "42",
                "table": "Table 7",
                "figure": "Figure 2",
            },
        }
        assert document.status == "draft"
        assert approvals == 0
        assert search_variants(db, service_type="cable bundle") == []
        visible_draft = search_variants(db, service_type="cable bundle", include_draft=True)
        assert len(visible_draft) == 1
        assert {"expert_review_required", "search_excluded"}.issubset(visible_draft[0].blockers)
        assert events[0]["action"] == "materialise_draft"
        assert events[0]["new_value"] == {
            "variant_id": "TECH-DRAFT-001",
            "system_id": "SYSTEM-DRAFT-001",
            "status": "draft",
            "technical_document_id": document.id,
            "source_document_reference": document.document_id,
            "source_page": "42",
            "source_sha256": stored.sha256,
            "search_eligibility": PENDING_REVIEW_SEARCH_ELIGIBILITY,
        }


def test_materialisation_requires_required_identity_and_locator_before_writing(
    materialise_as,
    technical_storage_root: Path,
) -> None:
    materialise, _events = materialise_as
    with physical_session() as db:
        writer = _user(db, "writer@example.test")
        document = _document(db, source_root=technical_storage_root)

        result = materialise(db, document, writer, source_page="   ")

        assert (
            "error=Variant+ID,+system+ID,+and+source+page+are+required"
            in result.headers["location"]
        )
        assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 0


def test_materialisation_rejects_invalid_requirements_and_duplicate_identity(
    materialise_as,
    technical_storage_root: Path,
) -> None:
    materialise, _events = materialise_as
    with physical_session() as db:
        writer = _user(db, "writer@example.test")
        document = _document(db, source_root=technical_storage_root)

        malformed = materialise(db, document, writer, labour_requirements_json="{}")
        assert "error=Numeric+fields+must+be+valid" in malformed.headers["location"]
        assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 0

        existing = TechnicalVariant(
            variant_id="TECH-DRAFT-001",
            system_id="EXISTING-SYSTEM",
            source_json={"fixture": "existing"},
        )
        db.add(existing)
        db.flush()
        duplicate = materialise(db, document, writer)

        assert "error=Technical+variant+ID+already+exists" in duplicate.headers["location"]
        assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 1


def test_materialisation_rechecks_the_retained_source_before_writing(
    materialise_as,
    technical_storage_root: Path,
) -> None:
    materialise, _events = materialise_as
    with physical_session() as db:
        writer = _user(db, "writer@example.test")
        document = _document(db, source_root=technical_storage_root)
        stored = db.get(StoredFile, document.stored_file_id)
        assert stored is not None
        Path(stored.storage_path).write_bytes(b"tampered retained technical source")

        result = materialise(db, document, writer)

        assert (
            "error=Technical+source+file+must+be+clean+and+unchanged" in result.headers["location"]
        )
        assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 0


def test_materialised_variant_still_requires_independent_document_approval(
    materialise_as,
    technical_storage_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    materialise, _events = materialise_as
    monkeypatch.setattr(technical_admin, "verify_csrf", lambda *_args: None)
    monkeypatch.setattr(technical_admin, "record_audit", lambda *_args, **_kwargs: None)
    with physical_session() as db:
        writer = _user(db, "writer@example.test")
        approver = _user(db, "approver@example.test")
        document = _document(db, source_root=technical_storage_root)
        materialise(db, document, writer)
        variant = db.scalar(
            select(TechnicalVariant).where(TechnicalVariant.variant_id == "TECH-DRAFT-001")
        )
        assert variant is not None

        monkeypatch.setattr(technical_admin, "_require", lambda *_args: writer)
        submitted = technical_admin.technical_variant_submit_review(
            variant.id,
            object(),  # type: ignore[arg-type]
            db,
            "csrf-token",
            "Submit source-bound Draft candidate",
        )
        monkeypatch.setattr(technical_admin, "_require", lambda *_args: approver)
        activated = technical_admin.technical_variant_approve(
            variant.id,
            object(),  # type: ignore[arg-type]
            db,
            "csrf-token",
            "Attempt independent technical approval",
        )

        assert "success=Submitted+for+technical+review" in submitted.headers["location"]
        assert "error=Linked+technical+document+must+be+approved" in activated.headers["location"]
        assert variant.status == "in_review"
        assert variant.expert_review_required is True


def test_materialisation_handles_a_competing_variant_identity(
    materialise_as,
    technical_storage_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    materialise, _events = materialise_as
    with physical_session() as db:
        writer = _user(db, "writer@example.test")
        document = _document(db, source_root=technical_storage_root)
        db.add(
            TechnicalVariant(
                variant_id="TECH-DRAFT-001",
                system_id="EXISTING-SYSTEM",
                source_json={"fixture": "existing"},
            )
        )
        db.commit()
        original_scalar = db.scalar
        monkeypatch.setattr(db, "scalar", lambda *_args, **_kwargs: None)

        result = materialise(db, document, writer)

        monkeypatch.setattr(db, "scalar", original_scalar)
        assert "error=Technical+variant+ID+already+exists" in result.headers["location"]
        db.expire_all()
        assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 1


def test_materialisation_template_is_registered() -> None:
    assert (
        technical_admin.templates.get_template("technical_document_materialisation.html")
        is not None
    )


def test_materialisation_template_renders_the_draft_boundary_and_source_form() -> None:
    html = technical_admin.templates.get_template("technical_document_materialisation.html").render(
        request=SimpleNamespace(query_params=QueryParams()),
        user=SimpleNamespace(full_name="Technical writer", role="administrator"),
        csrf_token=TEST_CSRF_TOKEN,
        attribution="CLASSIFIRE",
        document=SimpleNamespace(
            id="document-record-id",
            document_id="TECH-MATERIALISE-SOURCE",
            title="Retained technical source",
            manufacturer="Source manufacturer",
            status="draft",
        ),
    )

    assert "Draft only." in html
    assert "Create source-bound Draft candidate" in html
    assert 'action="/technical/documents/document-record-id/materialise"' in html
    assert 'name="variant_id"' in html
    assert 'name="system_id"' in html
    assert 'name="source_page"' in html
    assert 'name="search_eligibility"' not in html
