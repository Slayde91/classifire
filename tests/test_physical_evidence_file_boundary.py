from __future__ import annotations

import pytest
from fastapi import HTTPException
from physical_foundation_support import add_estimate, physical_session
from starlette.requests import Request

from classifire.api.physical_model import EvidenceSourceInput, register_evidence_source
from classifire.models import StoredFile, User


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "headers": [],
            "client": ("127.0.0.1", 50000),
        }
    )


def _user(session) -> User:  # type: ignore[no-untyped-def]
    user = User(
        email="evidence-boundary@example.test",
        full_name="Evidence Boundary Test",
        password_hash="not-used-by-direct-handler-test",  # noqa: S106 - direct handler bypasses auth.
        role="administrator",
    )
    session.add(user)
    session.flush()
    return user


def test_evidence_registration_requires_an_immutable_stored_file() -> None:
    with physical_session() as session:
        estimate = add_estimate(session)
        user = _user(session)

        with pytest.raises(HTTPException) as blocked:
            register_evidence_source(
                estimate.id,
                EvidenceSourceInput(evidence_type="inspection_photo"),
                _request(),
                session,
                user,
            )

        assert blocked.value.status_code == 422


def test_evidence_registration_accepts_an_immutable_scanned_technical_file() -> None:
    with physical_session() as session:
        estimate = add_estimate(session)
        user = _user(session)
        stored = StoredFile(
            original_filename="evidence.pdf",
            media_type="application/pdf",
            storage_path="test/evidence.pdf",
            sha256="a" * 64,
            size_bytes=1024,
            purpose="technical_evidence",
            immutable=True,
            malware_scan_status="clean",
        )
        session.add(stored)
        session.flush()

        result = register_evidence_source(
            estimate.id,
            EvidenceSourceInput(
                evidence_type="inspection_photo",
                stored_file_id=stored.id,
            ),
            _request(),
            session,
            user,
        )

        assert result["estimate_id"] == estimate.id
        assert result["sha256"] == stored.sha256
        assert result["status"] == "active"


@pytest.mark.parametrize(
    ("purpose", "immutable", "scan_status"),
    [
        ("unrelated_upload", True, "clean"),
        ("technical_evidence", False, "clean"),
        ("technical_evidence", True, "pending"),
    ],
)
def test_evidence_registration_rejects_stored_files_outside_the_safe_evidence_class(
    purpose: str,
    immutable: bool,
    scan_status: str,
) -> None:
    with physical_session() as session:
        estimate = add_estimate(session)
        user = _user(session)
        stored = StoredFile(
            original_filename="evidence.pdf",
            media_type="application/pdf",
            storage_path="test/evidence.pdf",
            sha256="b" * 64,
            size_bytes=1024,
            purpose=purpose,
            immutable=immutable,
            malware_scan_status=scan_status,
        )
        session.add(stored)
        session.flush()

        with pytest.raises(HTTPException) as blocked:
            register_evidence_source(
                estimate.id,
                EvidenceSourceInput(
                    evidence_type="inspection_photo",
                    stored_file_id=stored.id,
                ),
                _request(),
                session,
                user,
            )

        assert blocked.value.status_code == 409
