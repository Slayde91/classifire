from __future__ import annotations

import hashlib
import json

import pytest
from fastapi import HTTPException
from physical_foundation_support import add_estimate, add_opening, physical_session
from pydantic import ValidationError
from sqlalchemy import select
from starlette.requests import Request

from classifire.api.physical_model import EvidenceSourceInput, register_evidence_source
from classifire.models import AuditEvent, StoredFile, User
from classifire.physical_models import EvidenceSource


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


def _site_observation_json(
    *,
    status: str = "confirmed",
    value: str | None = "120 x 80",
    limitation: str | None = None,
) -> dict[str, object]:
    observation: dict[str, object] = {
        "observation_id": "SITE-O-001",
        "subject_kind": "opening",
        "subject_reference": "Opening visible in photo 4",
        "evidence_locator": "photo 4, opening at lower left",
        "fact_type": "opening_dimensions",
        "status": status,
        "unit": "mm",
    }
    if value is not None:
        observation["value"] = value
    if limitation is not None:
        observation["limitation"] = limitation
    return {
        "schema_version": "CLASSIFIRE_SITE_OBSERVATION_EVIDENCE_V1",
        "captured_at": "2026-08-25T11:00:00+10:00",
        "collected_by": "qualified-inspector-01",
        "collection_method": "site_visit",
        "governance_reference": "SITE-VISIT-2026-08-25-01",
        "location_reference": "Level 2, riser 4",
        "observations": [observation],
    }


def test_site_observation_registration_requires_bound_governed_provenance() -> None:
    with physical_session() as session:
        estimate = add_estimate(session)
        opening = add_opening(session, estimate)
        user = _user(session)
        stored = StoredFile(
            original_filename="site-observation.jpg",
            media_type="image/jpeg",
            storage_path="test/site-observation.jpg",
            sha256="c" * 64,
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
                evidence_type="site-observation",
                defect_id=opening.canonical_defect_id,
                stored_file_id=stored.id,
                source_json=_site_observation_json(),
            ),
            _request(),
            session,
            user,
        )

        evidence = session.get(EvidenceSource, result["id"])
        assert evidence is not None
        assert evidence.evidence_type == "site_observation"
        assert evidence.defect_id == opening.canonical_defect_id
        assert evidence.source_json == _site_observation_json()
        audit_event = session.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "register_evidence_source",
                AuditEvent.entity_id == evidence.id,
            )
        )
        assert audit_event is not None
        assert audit_event.new_value is not None
        expected_payload_sha256 = (
            hashlib.sha256(
                json.dumps(
                    _site_observation_json(),
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            )
            .hexdigest()
            .upper()
        )
        assert audit_event.new_value["source_json_sha256"] == expected_payload_sha256
        assert "source_json" not in audit_event.new_value


@pytest.mark.parametrize(
    ("status", "value", "limitation", "message"),
    [
        ("confirmed", None, None, "resolved site observations require a value"),
        ("unresolved", None, None, "unresolved site observations require a limitation"),
        (
            "unresolved",
            "opening depth could not be verified",
            "opposite face is inaccessible",
            "unresolved site observations must not provide a value",
        ),
    ],
)
def test_site_observation_rejects_unsupported_certainty(
    status: str,
    value: str | None,
    limitation: str | None,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        EvidenceSourceInput(
            evidence_type="site_observation",
            defect_id="defect-001",
            stored_file_id="stored-file-001",
            source_json=_site_observation_json(
                status=status,
                value=value,
                limitation=limitation,
            ),
        )


def test_site_observation_rejects_missing_defect_and_unknown_payload_keys() -> None:
    with pytest.raises(ValidationError, match="must bind to one defect"):
        EvidenceSourceInput(
            evidence_type="site_observation",
            stored_file_id="stored-file-001",
            source_json=_site_observation_json(),
        )

    source_json = _site_observation_json()
    source_json["unverified_extra"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EvidenceSourceInput(
            evidence_type="site_observation",
            defect_id="defect-001",
            stored_file_id="stored-file-001",
            source_json=source_json,
        )


def test_site_observation_requires_fact_locator_and_unique_observation_ids() -> None:
    missing_locator = _site_observation_json()
    observations = missing_locator["observations"]
    assert isinstance(observations, list)
    first_observation = observations[0]
    assert isinstance(first_observation, dict)
    first_observation.pop("evidence_locator")

    with pytest.raises(ValidationError, match="evidence_locator"):
        EvidenceSourceInput(
            evidence_type="site_observation",
            defect_id="defect-001",
            stored_file_id="stored-file-001",
            source_json=missing_locator,
        )

    duplicate_id = _site_observation_json()
    duplicate_observations = duplicate_id["observations"]
    assert isinstance(duplicate_observations, list)
    duplicate_observations.append(dict(duplicate_observations[0]))

    with pytest.raises(ValidationError, match="site observation IDs must be unique"):
        EvidenceSourceInput(
            evidence_type="site_observation",
            defect_id="defect-001",
            stored_file_id="stored-file-001",
            source_json=duplicate_id,
        )
