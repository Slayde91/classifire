from __future__ import annotations

import hashlib
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from physical_foundation_support import physical_session
from sqlalchemy import select
from sqlalchemy.orm import Session

from classifire import technical_admin
from classifire.models import Approval, StoredFile, TechnicalDocument, User


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
    scan_status: str = "clean",
) -> TechnicalDocument:
    content = b"technical source evidence"
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
        malware_scan_status=scan_status,
        immutable=True,
    )
    db.add(stored)
    db.flush()
    document = TechnicalDocument(
        document_id="TECH-DOCUMENT-REVIEW-TEST",
        stored_file_id=stored.id,
        document_type="assessment",
        title="Technical source",
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


def _pending_review(db: Session, document: TechnicalDocument, requester: User) -> Approval:
    approval = Approval(
        entity_type="technical_document",
        entity_id=document.id,
        approval_type="technical_document_review",
        status="pending",
        requested_by_id=requester.id,
    )
    db.add(approval)
    db.flush()
    return approval


@pytest.fixture
def review_as(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(technical_admin, "verify_csrf", lambda *_args: None)
    monkeypatch.setattr(technical_admin, "record_audit", lambda *_args, **_kwargs: None)

    def review(db: Session, document: TechnicalDocument, user: User, action: str):
        monkeypatch.setattr(technical_admin, "_require", lambda *_args: user)
        handlers = {
            "submit": technical_admin.technical_document_submit_review,
            "approve": technical_admin.technical_document_approve,
            "reject": technical_admin.technical_document_reject,
        }
        return handlers[action](
            document.id,
            object(),  # type: ignore[arg-type]
            db,
            "csrf-token",
            "Independent technical document review",
        )

    return review


def test_technical_document_submission_creates_a_pending_review(
    review_as,
    technical_storage_root: Path,
) -> None:
    with physical_session() as db:
        requester = _user(db, "requester@example.test")
        document = _document(db, source_root=technical_storage_root)

        result = review_as(db, document, requester, "submit")

        approval = db.scalar(
            select(Approval).where(
                Approval.entity_type == "technical_document",
                Approval.entity_id == document.id,
            )
        )
        assert "success=Submitted+for+technical+review" in result.headers["location"]
        assert document.status == "in_review"
        assert approval is not None
        assert approval.status == "pending"
        assert approval.requested_by_id == requester.id
        assert approval.decided_by_id is None


def test_technical_document_submission_does_not_reuse_another_approval_type(
    review_as,
    technical_storage_root: Path,
) -> None:
    with physical_session() as db:
        requester = _user(db, "requester@example.test")
        document = _document(db, source_root=technical_storage_root)
        unrelated = Approval(
            entity_type="technical_document",
            entity_id=document.id,
            approval_type="another_document_action",
            status="approved",
            requested_by_id=requester.id,
        )
        db.add(unrelated)
        db.flush()

        review_as(db, document, requester, "submit")

        review = db.scalar(
            select(Approval).where(
                Approval.entity_type == "technical_document",
                Approval.entity_id == document.id,
                Approval.approval_type == "technical_document_review",
            )
        )
        assert unrelated.status == "approved"
        assert review is not None
        assert review.status == "pending"


def test_technical_document_approval_refuses_a_draft_document(
    review_as,
    technical_storage_root: Path,
) -> None:
    with physical_session() as db:
        approver = _user(db, "approver@example.test")
        document = _document(db, source_root=technical_storage_root)

        result = review_as(db, document, approver, "approve")

        assert "Only+In+Review+documents+can+be+approved" in result.headers["location"]
        assert document.status == "draft"


def test_technical_document_approval_requires_a_pending_review(
    review_as,
    technical_storage_root: Path,
) -> None:
    with physical_session() as db:
        approver = _user(db, "approver@example.test")
        document = _document(db, source_root=technical_storage_root, status="in_review")

        result = review_as(db, document, approver, "approve")

        assert "Pending+technical+document+review+required" in result.headers["location"]
        assert document.status == "in_review"


def test_technical_document_approval_requires_a_separate_approver(
    review_as,
    technical_storage_root: Path,
) -> None:
    with physical_session() as db:
        requester = _user(db, "requester@example.test")
        document = _document(db, source_root=technical_storage_root, status="in_review")
        approval = _pending_review(db, document, requester)

        result = review_as(db, document, requester, "approve")

        assert (
            "Technical+document+requester+and+approver+must+be+different+users"
            in result.headers["location"]
        )
        assert document.status == "in_review"
        assert approval.status == "pending"
        assert approval.decided_by_id is None


def test_technical_document_approval_refuses_an_expired_source(
    review_as,
    technical_storage_root: Path,
) -> None:
    with physical_session() as db:
        requester = _user(db, "requester@example.test")
        approver = _user(db, "approver@example.test")
        document = _document(
            db,
            source_root=technical_storage_root,
            status="in_review",
        )
        document.expiry_date = date.today() - timedelta(days=1)
        approval = _pending_review(db, document, requester)

        result = review_as(db, document, approver, "approve")

        assert "Technical+source+document+has+expired" in result.headers["location"]
        assert document.status == "in_review"
        assert approval.status == "pending"
        assert approval.decided_by_id is None


def test_technical_document_approval_records_an_independent_decision(
    review_as,
    technical_storage_root: Path,
) -> None:
    with physical_session() as db:
        requester = _user(db, "requester@example.test")
        approver = _user(db, "approver@example.test")
        document = _document(db, source_root=technical_storage_root)

        review_as(db, document, requester, "submit")
        result = review_as(db, document, approver, "approve")

        approval = db.scalar(
            select(Approval).where(
                Approval.entity_type == "technical_document",
                Approval.entity_id == document.id,
            )
        )
        assert "success=Technical+source+document+approved" in result.headers["location"]
        assert document.status == "approved"
        assert document.reviewed_by_id == approver.id
        assert document.approved_by_id == approver.id
        assert document.approved_at is not None
        assert approval is not None
        assert approval.status == "approved"
        assert approval.decided_by_id == approver.id
        assert approval.decided_at is not None


def test_technical_document_rejection_requires_an_independent_decision(
    review_as,
    technical_storage_root: Path,
) -> None:
    with physical_session() as db:
        requester = _user(db, "requester@example.test")
        reviewer = _user(db, "reviewer@example.test")
        document = _document(db, source_root=technical_storage_root)

        review_as(db, document, requester, "submit")
        result = review_as(db, document, reviewer, "reject")

        approval = db.scalar(
            select(Approval).where(
                Approval.entity_type == "technical_document",
                Approval.entity_id == document.id,
            )
        )
        assert "success=Technical+source+document+rejected" in result.headers["location"]
        assert document.status == "rejected"
        assert document.reviewed_by_id == reviewer.id
        assert document.approved_by_id is None
        assert document.approved_at is None
        assert approval is not None
        assert approval.status == "rejected"
        assert approval.decided_by_id == reviewer.id
        assert approval.decided_at is not None


def test_technical_document_submission_requires_a_clean_source(
    review_as,
    technical_storage_root: Path,
) -> None:
    with physical_session() as db:
        requester = _user(db, "requester@example.test")
        document = _document(
            db,
            source_root=technical_storage_root,
            scan_status="pending",
        )

        result = review_as(db, document, requester, "submit")

        assert (
            "Technical+source+file+must+be+clean+and+unchanged+before+review"
            in result.headers["location"]
        )
        assert document.status == "draft"
        assert db.scalar(
            select(Approval).where(
                Approval.entity_type == "technical_document",
                Approval.entity_id == document.id,
            )
        ) is None


def test_technical_document_approval_rechecks_the_retained_source(
    review_as,
    technical_storage_root: Path,
) -> None:
    with physical_session() as db:
        requester = _user(db, "requester@example.test")
        approver = _user(db, "approver@example.test")
        document = _document(db, source_root=technical_storage_root)

        review_as(db, document, requester, "submit")
        stored = db.get(StoredFile, document.stored_file_id)
        assert stored is not None
        Path(stored.storage_path).write_bytes(b"tampered technical source evidence")

        result = review_as(db, document, approver, "approve")

        approval = db.scalar(
            select(Approval).where(
                Approval.entity_type == "technical_document",
                Approval.entity_id == document.id,
                Approval.approval_type == "technical_document_review",
            )
        )
        assert (
            "Technical+source+file+must+be+clean+and+unchanged+before+review"
            in result.headers["location"]
        )
        assert document.status == "in_review"
        assert approval is not None
        assert approval.status == "pending"
