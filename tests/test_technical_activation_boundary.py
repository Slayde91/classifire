from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from physical_foundation_support import physical_session
from sqlalchemy.orm import Session

from classifire import technical_admin
from classifire.models import Approval, StoredFile, TechnicalDocument, TechnicalVariant, User


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


def _variant(
    db: Session,
    *,
    status: str = "in_review",
    source_document_reference: str = "TECH-SOURCE-TEST",
    source_page: str = "12",
) -> TechnicalVariant:
    variant = TechnicalVariant(
        variant_id="TECH-ACTIVATION-TEST",
        system_id="SYSTEM-ACTIVATION-TEST",
        source_document_reference=source_document_reference,
        source_page=source_page,
        source_json={"fixture": "technical-activation"},
        status=status,
        expert_review_required=True,
    )
    db.add(variant)
    db.flush()
    return variant


def _pending_approval(db: Session, variant: TechnicalVariant, requester: User) -> Approval:
    approval = Approval(
        entity_type="technical_variant",
        entity_id=variant.id,
        approval_type="technical_activation",
        status="pending",
        requested_by_id=requester.id,
    )
    db.add(approval)
    db.flush()
    return approval


def _technical_document(
    db: Session,
    *,
    status: str,
    source_root: Path | None = None,
    document_id: str = "TECH-SOURCE-TEST",
) -> TechnicalDocument:
    content = b"technical activation source evidence"
    digest = hashlib.sha256(content).hexdigest()
    if source_root is None:
        storage_path = "technical/source.pdf"
    else:
        path = source_root / digest[:2] / digest[2:4] / f"{digest}.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        storage_path = str(path)
    stored = StoredFile(
        original_filename="source.pdf",
        media_type="application/pdf",
        storage_path=storage_path,
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
        title="Technical source",
        status=status,
    )
    db.add(document)
    db.flush()
    return document


def _request() -> object:
    return object()


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
def activate_as(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(technical_admin, "verify_csrf", lambda *_args: None)
    monkeypatch.setattr(technical_admin, "record_audit", lambda *_args, **_kwargs: None)

    def activate(db: Session, variant: TechnicalVariant, user: User):
        monkeypatch.setattr(technical_admin, "_require", lambda *_args: user)
        return technical_admin.technical_variant_approve(
            variant.id,
            _request(),  # type: ignore[arg-type]
            db,
            "csrf-token",
            "Independent technical approval",
        )

    return activate


@pytest.fixture
def bind_as(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(technical_admin, "verify_csrf", lambda *_args: None)
    monkeypatch.setattr(technical_admin, "record_audit", lambda *_args, **_kwargs: None)

    def bind(db: Session, variant: TechnicalVariant, user: User):
        monkeypatch.setattr(technical_admin, "_require", lambda *_args: user)
        return technical_admin.technical_variant_bind_source_document(
            variant.id,
            _request(),  # type: ignore[arg-type]
            db,
            "csrf-token",
            "Bind source document",
        )

    return bind


@pytest.fixture
def submit_review_as(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(technical_admin, "verify_csrf", lambda *_args: None)
    monkeypatch.setattr(technical_admin, "record_audit", lambda *_args, **_kwargs: None)

    def submit(db: Session, variant: TechnicalVariant, user: User):
        monkeypatch.setattr(technical_admin, "_require", lambda *_args: user)
        return technical_admin.technical_variant_submit_review(
            variant.id,
            _request(),  # type: ignore[arg-type]
            db,
            "csrf-token",
            "Submit technical variant for review",
        )

    return submit


@pytest.fixture
def revise_as(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(technical_admin, "verify_csrf", lambda *_args: None)
    monkeypatch.setattr(technical_admin, "record_audit", lambda *_args, **_kwargs: None)

    def revise(
        db: Session,
        variant: TechnicalVariant,
        user: User,
        source_document_reference: str,
        source_page: str = "13",
    ):
        monkeypatch.setattr(technical_admin, "_require", lambda *_args: user)
        return technical_admin.technical_variant_revision(
            variant.id,
            _request(),  # type: ignore[arg-type]
            db,
            "csrf-token",
            source_document_reference=source_document_reference,
            source_page=source_page,
            reason="Correct technical source reference",
        )

    return revise


def test_technical_activation_refuses_a_draft_variant(activate_as) -> None:
    with physical_session() as db:
        requester = _user(db, "requester@example.test")
        approver = _user(db, "approver@example.test")
        variant = _variant(db, status="draft")
        approval = _pending_approval(db, variant, requester)

        result = activate_as(db, variant, approver)

        assert "Only+In+Review+variants+can+be+approved" in result.headers["location"]
        assert variant.status == "draft"
        assert approval.status == "pending"
        assert approval.decided_by_id is None


def test_draft_variant_binds_only_its_exact_retained_source_document(
    bind_as,
    technical_storage_root: Path,
) -> None:
    with physical_session() as db:
        writer = _user(db, "writer@example.test")
        variant = _variant(
            db,
            status="draft",
            source_document_reference="TECH-SOURCE-TEST",
        )
        document = _technical_document(
            db,
            status="draft",
            source_root=technical_storage_root,
            document_id="TECH-SOURCE-TEST",
        )

        result = bind_as(db, variant, writer)

        assert "success=Exact+technical+source+document+bound" in result.headers["location"]
        assert variant.status == "draft"
        assert variant.technical_document_id == document.id
        assert document.status == "draft"


def test_bound_draft_variant_can_enter_review_without_activation(
    bind_as,
    submit_review_as,
    technical_storage_root: Path,
) -> None:
    with physical_session() as db:
        writer = _user(db, "writer@example.test")
        variant = _variant(
            db,
            status="draft",
            source_document_reference="TECH-SOURCE-TEST",
        )
        document = _technical_document(
            db,
            status="draft",
            source_root=technical_storage_root,
            document_id="TECH-SOURCE-TEST",
        )

        bind_as(db, variant, writer)
        result = submit_review_as(db, variant, writer)

        approval = db.query(Approval).one()
        assert "success=Submitted+for+technical+review" in result.headers["location"]
        assert variant.status == "in_review"
        assert document.status == "draft"
        assert approval.status == "pending"
        assert approval.requested_by_id == writer.id


def test_draft_variant_cannot_bind_an_altered_retained_source_document(
    bind_as,
    technical_storage_root: Path,
) -> None:
    with physical_session() as db:
        writer = _user(db, "writer@example.test")
        variant = _variant(
            db,
            status="draft",
            source_document_reference="TECH-SOURCE-TEST",
        )
        document = _technical_document(
            db,
            status="draft",
            source_root=technical_storage_root,
            document_id="TECH-SOURCE-TEST",
        )
        stored = db.get(StoredFile, document.stored_file_id)
        assert stored is not None
        Path(stored.storage_path).write_bytes(b"altered technical source evidence")

        result = bind_as(db, variant, writer)

        assert (
            "Exact+technical+source+file+must+be+clean+and+unchanged+before+binding"
            in result.headers["location"]
        )
        assert variant.status == "draft"
        assert variant.technical_document_id is None


def test_source_binding_audits_the_exact_retained_document(
    monkeypatch: pytest.MonkeyPatch,
    technical_storage_root: Path,
) -> None:
    with physical_session() as db:
        writer = _user(db, "writer@example.test")
        variant = _variant(
            db,
            status="draft",
            source_document_reference="TECH-SOURCE-TEST",
        )
        document = _technical_document(
            db,
            status="draft",
            source_root=technical_storage_root,
            document_id="TECH-SOURCE-TEST",
        )
        audited: list[dict[str, object]] = []
        monkeypatch.setattr(technical_admin, "verify_csrf", lambda *_args: None)
        monkeypatch.setattr(technical_admin, "_require", lambda *_args: writer)
        monkeypatch.setattr(
            technical_admin,
            "record_audit",
            lambda *_args, **kwargs: audited.append(kwargs),
        )

        technical_admin.technical_variant_bind_source_document(
            variant.id,
            _request(),  # type: ignore[arg-type]
            db,
            "csrf-token",
            "Bind source document",
        )

        assert len(audited) == 1
        assert audited[0]["action"] == "bind_source_document"
        assert audited[0]["new_value"] == {
            "technical_document_id": document.id,
            "document_id": "TECH-SOURCE-TEST",
            "stored_file_sha256": hashlib.sha256(
                b"technical activation source evidence"
            ).hexdigest(),
        }


def test_draft_variant_cannot_bind_a_missing_exact_source_document(bind_as) -> None:
    with physical_session() as db:
        writer = _user(db, "writer@example.test")
        variant = _variant(db, status="draft")

        result = bind_as(db, variant, writer)

        assert (
            "Exact+retained+technical+source+document+was+not+found"
            in result.headers["location"]
        )
        assert variant.status == "draft"
        assert variant.technical_document_id is None


def test_unbound_draft_variant_cannot_enter_technical_review(submit_review_as) -> None:
    with physical_session() as db:
        writer = _user(db, "writer@example.test")
        variant = _variant(db, status="draft")

        result = submit_review_as(db, variant, writer)

        assert (
            "Exact+retained+technical+source+document+must+be+bound+before+review"
            in result.headers["location"]
        )
        assert variant.status == "draft"


def test_revision_requires_a_nonblank_source_locator(revise_as) -> None:
    with physical_session() as db:
        writer = _user(db, "writer@example.test")
        original = _variant(db, status="active")

        result = revise_as(db, original, writer, "TECH-SOURCE-TEST", "   ")

        assert (
            "Source+document+reference+and+source+page+are+required+to+create+a+revision"
            in result.headers["location"]
        )
        assert db.query(TechnicalVariant).filter_by(supersedes_id=original.id).one_or_none() is None


def test_technical_review_requires_a_nonblank_source_locator(
    submit_review_as,
    technical_storage_root: Path,
) -> None:
    with physical_session() as db:
        writer = _user(db, "writer@example.test")
        variant = _variant(db, status="draft", source_page="   ")
        document = _technical_document(
            db,
            status="draft",
            source_root=technical_storage_root,
        )
        variant.technical_document_id = document.id

        result = submit_review_as(db, variant, writer)

        assert (
            "Source+document+reference+and+source+page+are+required+before+review"
            in result.headers["location"]
        )
        assert variant.status == "draft"


def test_technical_activation_requires_a_nonblank_source_locator(
    activate_as,
    technical_storage_root: Path,
) -> None:
    with physical_session() as db:
        requester = _user(db, "requester@example.test")
        approver = _user(db, "approver@example.test")
        variant = _variant(db, source_page="   ")
        document = _technical_document(
            db,
            status="approved",
            source_root=technical_storage_root,
        )
        variant.technical_document_id = document.id
        approval = _pending_approval(db, variant, requester)

        result = activate_as(db, variant, approver)

        assert (
            "Source+document+reference+and+source+page+are+required+before+approval"
            in result.headers["location"]
        )
        assert variant.status == "in_review"
        assert approval.status == "pending"


def test_technical_activation_requires_a_pending_request(activate_as) -> None:
    with physical_session() as db:
        approver = _user(db, "approver@example.test")
        variant = _variant(db)

        result = activate_as(db, variant, approver)

        assert "Pending+technical+approval+request+required" in result.headers["location"]
        assert variant.status == "in_review"


def test_technical_activation_requires_a_separate_approver(activate_as) -> None:
    with physical_session() as db:
        requester = _user(db, "requester@example.test")
        variant = _variant(db)
        approval = _pending_approval(db, variant, requester)

        result = activate_as(db, variant, requester)

        assert (
            "Technical+requester+and+approver+must+be+different+users"
            in result.headers["location"]
        )
        assert variant.status == "in_review"
        assert approval.status == "pending"
        assert approval.decided_by_id is None


def test_technical_activation_requires_a_linked_document(activate_as) -> None:
    with physical_session() as db:
        requester = _user(db, "requester@example.test")
        approver = _user(db, "approver@example.test")
        variant = _variant(db)
        approval = _pending_approval(db, variant, requester)

        result = activate_as(db, variant, approver)

        assert (
            "Technical+variant+must+be+bound+to+an+approved+technical+document"
            in result.headers["location"]
        )
        assert variant.status == "in_review"
        assert approval.status == "pending"
        assert approval.decided_by_id is None


def test_technical_activation_requires_an_approved_linked_document(activate_as) -> None:
    with physical_session() as db:
        requester = _user(db, "requester@example.test")
        approver = _user(db, "approver@example.test")
        document = _technical_document(db, status="draft")
        variant = _variant(db)
        variant.technical_document_id = document.id
        approval = _pending_approval(db, variant, requester)

        result = activate_as(db, variant, approver)

        assert "Linked+technical+document+must+be+approved" in result.headers["location"]
        assert variant.status == "in_review"
        assert approval.status == "pending"
        assert approval.decided_by_id is None


def test_technical_activation_activates_an_independently_reviewed_variant(
    activate_as,
    technical_storage_root: Path,
) -> None:
    with physical_session() as db:
        requester = _user(db, "requester@example.test")
        approver = _user(db, "approver@example.test")
        variant = _variant(db)
        document = _technical_document(
            db,
            status="approved",
            source_root=technical_storage_root,
        )
        variant.technical_document_id = document.id
        approval = _pending_approval(db, variant, requester)

        result = activate_as(db, variant, approver)

        assert "success=Technical+variant+approved+and+activated" in result.headers["location"]
        assert variant.status == "active"
        assert variant.expert_review_required is False
        assert approval.status == "approved"
        assert approval.decided_by_id == approver.id
        assert approval.decided_at is not None


def test_revision_with_changed_source_reference_drops_inherited_document_binding(
    revise_as,
) -> None:
    with physical_session() as db:
        writer = _user(db, "writer@example.test")
        original = _variant(db, status="active")
        document = _technical_document(db, status="approved")
        original.technical_document_id = document.id

        result = revise_as(db, original, writer, "TECH-SOURCE-OTHER")

        revision = db.query(TechnicalVariant).filter_by(supersedes_id=original.id).one()
        assert "success=Draft+technical+revision+created" in result.headers["location"]
        assert revision.status == "draft"
        assert revision.source_document_reference == "TECH-SOURCE-OTHER"
        assert revision.technical_document_id is None
        assert revision.source_json["technical_document_binding"] == {
            "previous_document_id": document.id,
            "inherited": False,
            "requires_exact_rebinding": True,
        }


def test_revision_with_matching_source_reference_preserves_document_binding(revise_as) -> None:
    with physical_session() as db:
        writer = _user(db, "writer@example.test")
        original = _variant(db, status="active")
        document = _technical_document(db, status="approved")
        original.technical_document_id = document.id

        revise_as(db, original, writer, "TECH-SOURCE-TEST")

        revision = db.query(TechnicalVariant).filter_by(supersedes_id=original.id).one()
        assert revision.status == "draft"
        assert revision.technical_document_id == document.id
        assert revision.source_json["technical_document_binding"] == {
            "previous_document_id": document.id,
            "inherited": True,
            "requires_exact_rebinding": False,
        }


def test_technical_review_requires_document_reference_match(
    submit_review_as,
    technical_storage_root: Path,
) -> None:
    with physical_session() as db:
        writer = _user(db, "writer@example.test")
        variant = _variant(
            db,
            status="draft",
            source_document_reference="TECH-SOURCE-OTHER",
        )
        document = _technical_document(
            db,
            status="draft",
            source_root=technical_storage_root,
        )
        variant.technical_document_id = document.id

        result = submit_review_as(db, variant, writer)

        assert (
            "Bound+technical+source+document+must+match+the+source+document+reference"
            in result.headers["location"]
        )
        assert variant.status == "draft"


def test_technical_activation_requires_document_reference_match(
    activate_as,
    technical_storage_root: Path,
) -> None:
    with physical_session() as db:
        requester = _user(db, "requester@example.test")
        approver = _user(db, "approver@example.test")
        variant = _variant(
            db,
            source_document_reference="TECH-SOURCE-OTHER",
        )
        document = _technical_document(
            db,
            status="approved",
            source_root=technical_storage_root,
        )
        variant.technical_document_id = document.id
        approval = _pending_approval(db, variant, requester)

        result = activate_as(db, variant, approver)

        assert (
            "Linked+technical+document+must+match+the+source+document+reference"
            in result.headers["location"]
        )
        assert variant.status == "in_review"
        assert approval.status == "pending"


def test_technical_activation_rechecks_the_linked_document_source(
    activate_as,
    technical_storage_root: Path,
) -> None:
    with physical_session() as db:
        requester = _user(db, "requester@example.test")
        approver = _user(db, "approver@example.test")
        variant = _variant(db)
        document = _technical_document(
            db,
            status="approved",
            source_root=technical_storage_root,
        )
        variant.technical_document_id = document.id
        approval = _pending_approval(db, variant, requester)
        stored = db.get(StoredFile, document.stored_file_id)
        assert stored is not None
        Path(stored.storage_path).write_bytes(b"altered technical activation source")

        result = activate_as(db, variant, approver)

        assert (
            "Linked+technical+document+source+must+be+clean+and+unchanged"
            in result.headers["location"]
        )
        assert variant.status == "in_review"
        assert approval.status == "pending"
        assert approval.decided_by_id is None
