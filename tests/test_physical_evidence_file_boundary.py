from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi import HTTPException
from physical_foundation_support import add_estimate, physical_session
from starlette.requests import Request

from classifire.api.physical_model import EvidenceSourceInput, register_evidence_source
from classifire.config import Settings
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


def _settings(tmp_path: Path) -> Settings:
    return Settings(env="test", storage_root=tmp_path, _env_file=None)


def _stored_file(
    tmp_path: Path,
    *,
    purpose: str = "technical_evidence",
    immutable: bool = True,
    scan_status: str = "clean",
) -> StoredFile:
    payload = b"controlled retained physical evidence"
    retained_path = tmp_path / "evidence.pdf"
    retained_path.write_bytes(payload)
    return StoredFile(
        original_filename="evidence.pdf",
        media_type="application/pdf",
        storage_path=str(retained_path),
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        purpose=purpose,
        immutable=immutable,
        malware_scan_status=scan_status,
    )


def test_evidence_registration_requires_an_immutable_stored_file(tmp_path: Path) -> None:
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
                _settings(tmp_path),
            )

        assert blocked.value.status_code == 422


def test_evidence_registration_accepts_an_immutable_scanned_technical_file(
    tmp_path: Path,
) -> None:
    with physical_session() as session:
        estimate = add_estimate(session)
        user = _user(session)
        stored = _stored_file(tmp_path)
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
            _settings(tmp_path),
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
        ("technical_evidence", True, "not_configured"),
        ("technical_evidence", True, "infected"),
        ("technical_evidence", True, "scan_error"),
    ],
)
def test_evidence_registration_rejects_stored_files_outside_the_safe_evidence_class(
    tmp_path: Path,
    purpose: str,
    immutable: bool,
    scan_status: str,
) -> None:
    with physical_session() as session:
        estimate = add_estimate(session)
        user = _user(session)
        stored = _stored_file(
            tmp_path,
            purpose=purpose,
            immutable=immutable,
            scan_status=scan_status,
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
                _settings(tmp_path),
            )

        assert blocked.value.status_code == 409


@pytest.mark.parametrize("failure", ["missing", "tampered"])
def test_evidence_registration_rejects_missing_or_tampered_retained_bytes(
    tmp_path: Path,
    failure: str,
) -> None:
    with physical_session() as session:
        estimate = add_estimate(session)
        user = _user(session)
        stored = _stored_file(tmp_path)
        session.add(stored)
        session.flush()
        path = Path(stored.storage_path)
        if failure == "missing":
            path.unlink()
        else:
            path.write_bytes(b"tampered after clean scan")

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
                _settings(tmp_path),
            )

        assert blocked.value.status_code == 409
        assert blocked.value.detail == "STORED_EVIDENCE_FILE_INTEGRITY_INVALID"
