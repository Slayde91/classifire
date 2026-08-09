from __future__ import annotations

from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from classifire import canonical_models, commercial_models  # noqa: F401
from classifire.agent_security import provision_agent_principal
from classifire.api.agent_api import router as agent_router
from classifire.db import Base, get_db
from classifire.models import Estimate, Opening, Project, Service


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
    app.include_router(agent_router)

    def override_db():  # type: ignore[no-untyped-def]
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    return app, factory


def test_agent_physical_model_uses_current_orm_fields() -> None:
    app, factory = _test_app()
    with factory() as db:
        _principal, token = provision_agent_principal(db, agent_id="cf-physical-model")
        project = Project(reference="AGENT-PM-001", name="Agent Physical Model Read")
        db.add(project)
        db.flush()
        estimate = Estimate(
            project_id=project.id,
            revision=1,
            reference="AGENT-PM-001-R1",
            title="Agent Physical Model Read",
            status="draft",
        )
        db.add(estimate)
        db.flush()
        opening = Opening(
            estimate_id=estimate.id,
            defect_id="D-001",
            opening_code="O-001",
            substrate_type="concrete",
            substrate_plane="wall",
            substrate_thickness_mm=Decimal("120"),
            orientation="vertical",
            opening_type="circular",
            diameter_mm=Decimal("110"),
            frl="-/120/120",
            physical_model_status="reviewed",
            technical_status="not_assessed",
        )
        db.add(opening)
        db.flush()
        db.add(
            Service(
                opening_id=opening.id,
                service_code="S-001",
                service_type="pipe",
                material="copper",
                outside_diameter_mm=Decimal("50"),
                quantity=Decimal("1"),
                centre_x_mm=Decimal("10"),
                centre_y_mm=Decimal("20"),
                evidence_status="confirmed",
                confidence=Decimal("0.95"),
            )
        )
        db.commit()
        estimate_id = estimate.id

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Classifire-Agent-ID": "cf-physical-model",
    }
    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/agent/estimates/{estimate_id}/physical-model",
            headers=headers,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent_id"] == "cf-physical-model"
    assert len(payload["openings"]) == 1
    item = payload["openings"][0]
    assert item["defect_id"] == "D-001"
    assert item["substrate_thickness_mm"] == "120.0000"
    assert item["physical_model_status"] == "reviewed"
    assert item["technical_status"] == "not_assessed"
    service = item["services"][0]
    assert service["centre_x_mm"] == "10.0000"
    assert service["centre_y_mm"] == "20.0000"
    assert service["evidence_status"] == "confirmed"
    assert service["confidence"] == "0.9500"
