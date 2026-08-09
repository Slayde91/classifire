from __future__ import annotations

from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from classifire import canonical_models, commercial_models  # noqa: F401
from classifire.agent_security import AGENT_SCOPE_MAP, FORBIDDEN_AGENT_SCOPES, provision_agent_principal
from classifire.api.agent_intake_physical import router as intake_physical_router
from classifire.canonical_models import Defect, EvidenceSource, ServiceOpeningLink
from classifire.db import Base, get_db
from classifire.models import Estimate, Opening, Project, Service, StoredFile


def _test_app() -> tuple[FastAPI, sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    app = FastAPI()
    app.include_router(intake_physical_router)

    def override_db():  # type: ignore[no-untyped-def]
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    return app, factory


def _credential(factory: sessionmaker[Session], agent_id: str) -> str:
    with factory() as db:
        _principal, token = provision_agent_principal(db, agent_id=agent_id)
        db.commit()
        return token


def _headers(agent_id: str, token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Classifire-Agent-ID": agent_id,
    }


def _seed_estimate(factory: sessionmaker[Session]) -> tuple[str, str]:
    with factory() as db:
        project = Project(reference="REAL-UAT-PROJECT", name="Real UAT Project")
        db.add(project)
        db.flush()
        estimate = Estimate(
            project_id=project.id,
            revision=1,
            reference="REAL-UAT-EST-001",
            title="Real report acceptance",
            status="draft",
        )
        db.add(estimate)
        stored = StoredFile(
            original_filename="report.pdf",
            media_type="application/pdf",
            storage_path="C:/controlled/report.pdf",
            sha256="1" * 64,
            size_bytes=123,
            purpose="project_evidence",
            immutable=True,
        )
        db.add(stored)
        db.commit()
        return estimate.id, stored.id


def _register_observation(client: TestClient, estimate_id: str, stored_file_id: str, token: str):
    return client.post(
        f"/api/v1/agent/estimates/{estimate_id}/evidence/register",
        headers=_headers("cf-intake-evidence", token),
        json={
            "observations": [
                {
                    "stored_file_id": stored_file_id,
                    "evidence_type": "defect_report_entry",
                    "external_defect_id": "D-001",
                    "defect_description": "Missing fire seal to copper pipe",
                    "defect_location": "Level 1 riser",
                    "source_reference": "report.pdf",
                    "page_number": "3",
                    "region_reference": "Photo 1",
                    "evidence_class": "observed",
                    "confidence": 0.95,
                }
            ]
        },
    )


def _model_payload(*, include_quantity: bool = True, material: str | None = "Copper") -> dict:
    service = {
        "service_code": "SVC-001",
        "primary_opening_code": "OP-001",
        "opening_codes": ["OP-001"],
        "service_type": "metal pipe",
        "material": material,
        "outside_diameter_mm": 25,
        "evidence_status": "confirmed",
        "confidence": 0.95,
        "source_reference": "D-001 / report p.3 / Photo 1",
    }
    if include_quantity:
        service["quantity"] = 1
    return {
        "openings": [
            {
                "opening_code": "OP-001",
                "external_defect_id": "D-001",
                "location": "Level 1 riser",
                "substrate_type": "masonry wall",
                "substrate_plane": "wall",
                "substrate_thickness_mm": 120,
                "orientation": "vertical",
                "opening_type": "core hole",
                "diameter_mm": 60,
                "frl": "-/90/90",
            }
        ],
        "services": [service],
    }


def test_new_scope_matrix_is_narrow_and_role_specific() -> None:
    assert "evidence:write" in AGENT_SCOPE_MAP["cf-intake-evidence"]
    assert "physical:write" in AGENT_SCOPE_MAP["cf-physical-model"]
    assert "physical:lock" in AGENT_SCOPE_MAP["cf-physical-model"]
    for agent_id, scopes in AGENT_SCOPE_MAP.items():
        assert not (set(scopes) & FORBIDDEN_AGENT_SCOPES), agent_id
        if agent_id != "cf-intake-evidence":
            assert "evidence:write" not in scopes
        if agent_id != "cf-physical-model":
            assert "physical:write" not in scopes
            assert "physical:lock" not in scopes


def test_cross_role_intake_and_physical_writes_fail_before_business_logic() -> None:
    app, factory = _test_app()
    physical_token = _credential(factory, "cf-physical-model")
    intake_token = _credential(factory, "cf-intake-evidence")
    technical_token = _credential(factory, "cf-technical-system")

    with TestClient(app) as client:
        physical_to_evidence = client.post(
            "/api/v1/agent/estimates/not-real/evidence/register",
            headers=_headers("cf-physical-model", physical_token),
            json={"observations": [{"stored_file_id": "x", "evidence_type": "page"}]},
        )
        intake_to_model = client.post(
            "/api/v1/agent/estimates/not-real/physical-model/initial",
            headers=_headers("cf-intake-evidence", intake_token),
            json={"openings": [], "services": []},
        )
        technical_to_lock = client.post(
            "/api/v1/agent/estimates/not-real/physical-model/lock",
            headers=_headers("cf-technical-system", technical_token),
            json={},
        )

    assert physical_to_evidence.status_code == 403
    assert "evidence:write" in physical_to_evidence.json()["detail"]
    assert intake_to_model.status_code == 403
    assert "physical:write" in intake_to_model.json()["detail"]
    assert technical_to_lock.status_code == 403
    assert "physical:lock" in technical_to_lock.json()["detail"]


def test_intake_registration_is_idempotent_and_preserves_defect_provenance() -> None:
    app, factory = _test_app()
    estimate_id, stored_file_id = _seed_estimate(factory)
    intake_token = _credential(factory, "cf-intake-evidence")

    with TestClient(app) as client:
        first = _register_observation(client, estimate_id, stored_file_id, intake_token)
        second = _register_observation(client, estimate_id, stored_file_id, intake_token)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["registered"][0]["created"] is True
    assert second.json()["registered"][0]["created"] is False
    with factory() as db:
        defects = list(db.scalars(select(Defect).where(Defect.estimate_id == estimate_id)).all())
        evidence = list(db.scalars(select(EvidenceSource).where(EvidenceSource.estimate_id == estimate_id)).all())
    assert len(defects) == 1
    assert defects[0].external_defect_id == "D-001"
    assert len(evidence) == 1
    assert evidence[0].defect_id == defects[0].id
    assert evidence[0].sha256 == "1" * 64


def test_initial_physical_model_requires_explicit_service_quantity() -> None:
    app, factory = _test_app()
    estimate_id, _stored_file_id = _seed_estimate(factory)
    physical_token = _credential(factory, "cf-physical-model")

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/agent/estimates/{estimate_id}/physical-model/initial",
            headers=_headers("cf-physical-model", physical_token),
            json=_model_payload(include_quantity=False),
        )

    assert response.status_code == 422


def test_initial_physical_model_creates_opening_service_and_canonical_link_once() -> None:
    app, factory = _test_app()
    estimate_id, stored_file_id = _seed_estimate(factory)
    intake_token = _credential(factory, "cf-intake-evidence")
    physical_token = _credential(factory, "cf-physical-model")

    with TestClient(app) as client:
        assert _register_observation(client, estimate_id, stored_file_id, intake_token).status_code == 200
        first = client.post(
            f"/api/v1/agent/estimates/{estimate_id}/physical-model/initial",
            headers=_headers("cf-physical-model", physical_token),
            json=_model_payload(),
        )
        second = client.post(
            f"/api/v1/agent/estimates/{estimate_id}/physical-model/initial",
            headers=_headers("cf-physical-model", physical_token),
            json=_model_payload(),
        )

    assert first.status_code == 200, first.text
    assert second.status_code == 409
    with factory() as db:
        opening = db.scalar(select(Opening).where(Opening.estimate_id == estimate_id))
        assert opening is not None
        service = db.scalar(select(Service).where(Service.opening_id == opening.id))
        assert service is not None
        link = db.scalar(select(ServiceOpeningLink).where(Service.service_id == service.id, ServiceOpeningLink.opening_id == opening.id))
        assert link is not None
        assert service.quantity == Decimal("1.0000")
        assert opening.canonical_defect_id is not None


def test_authorised_physical_lock_reaches_workflow_guard() -> None:
    app, factory = _test_app()
    estimate_id, stored_file_id = _seed_estimate(factory)
    intake_token = _credential(factory, "cf-intake-evidence")
    physical_token = _credential(factory, "cf-physical-model")

    with TestClient(app) as client:
        assert _register_observation(client, estimate_id, stored_file_id, intake_token).status_code == 200
        assert client.post(
            f"/api/v1/agent/estimates/{estimate_id}/physical-model/initial",
            headers=_headers("cf-physical-model", physical_token),
            json=_model_payload(),
        ).status_code == 200
        lock = client.post(
            f"/api/v1/agent/estimates/{estimate_id}/physical-model/lock",
            headers=_headers("cf-physical-model", physical_token),
            json={"reason": "test controlled lock"},
        )

    # The endpoint passed role authentication. Depending on seeded workflow/release
    # prerequisites it may lock or fail closed in the deterministic workflow guard.
    assert lock.status_code in {200, 409}
    assert lock.status_code != 403


def test_intake_physical_openapi_exposes_no_human_release_or_approval_route() -> None:
    app, _factory = _test_app()
    paths = set(app.openapi()["paths"])
    expected = {
        "/api/v1/agent/estimates/{estimate_id}/evidence/register",
        "/api/v1/agent/estimates/{estimate_id}/physical-model/initial",
        "/api/v1/agent/estimates/{estimate_id}/physical-model/lock",
    }
    assert expected <= paths
    forbidden_segments = {"release", "human-release", "human_release", "approve", "approval"}
    for path in paths:
        segments = {segment.lower() for segment in path.split("/") if segment}
        assert not (segments & forbidden_segments), path
