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


def _variant(db: Session, *, status: str = "in_review") -> TechnicalVariant:
    variant = TechnicalVariant(
        variant_id="TECH-ACTIVATION-TEST",
        system_id="SYSTEM-ACTIVATION-TEST",
        source_document_reference="TECH-SOURCE-TEST",
        source_page="12",
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
        document_id="TECH-DOC-ACTIVATION-TEST",
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
