from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from classifire import canonical_models, commercial_models  # noqa: F401
from classifire.agent_security import AGENT_SCOPE_MAP, FORBIDDEN_AGENT_SCOPES, provision_agent_principal
from classifire.api.agent_api import router as agent_router
from classifire.api.agent_intake_physical import router as intake_physical_router
from classifire.db import Base, get_db
from classifire.models import Estimate, Project


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
    app.include_router(intake_physical_router)

    def override_db():  # type: ignore[no-untyped-def]
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    return app, factory


def test_validator_can_read_evidence_and_physical_model_but_cannot_mutate_upstream_state() -> None:
    app, factory = _test_app()
    with factory() as db:
        _principal, token = provision_agent_principal(db, agent_id="cf-validator")
        project = Project(reference="VAL-READ-001", name="Validator Read Boundary")
        db.add(project)
        db.flush()
        estimate = Estimate(
            project_id=project.id,
            revision=1,
            reference="VAL-READ-001-R1",
            title="Validator Read Boundary",
            status="draft",
        )
        db.add(estimate)
        db.commit()
        estimate_id = estimate.id

    scopes = AGENT_SCOPE_MAP["cf-validator"]
    assert {"evidence:read", "physical:read", "validation:run"} <= scopes
    assert not (
        scopes
        & {
            "evidence:write",
            "physical:write",
            "physical:lock",
            "technical:select",
            "technical:lock",
            "commercial:derive",
            "snapshot:lock",
        }
    )
    assert not (scopes & FORBIDDEN_AGENT_SCOPES)

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Classifire-Agent-ID": "cf-validator",
    }

    with TestClient(app) as client:
        evidence = client.get(
            f"/api/v1/agent/estimates/{estimate_id}/evidence",
            headers=headers,
        )
        physical = client.get(
            f"/api/v1/agent/estimates/{estimate_id}/physical-model",
            headers=headers,
        )

        evidence_write = client.post(
            f"/api/v1/agent/estimates/{estimate_id}/evidence/register",
            headers=headers,
            json={
                "observations": [
                    {
                        "stored_file_id": "not-authorised-before-file-lookup",
                        "evidence_type": "photo",
                    }
                ]
            },
        )
        physical_write = client.post(
            f"/api/v1/agent/estimates/{estimate_id}/physical-model/initial",
            headers=headers,
            json={
                "openings": [{"opening_code": "O-001"}],
                "services": [
                    {
                        "service_code": "S-001",
                        "primary_opening_code": "O-001",
                        "opening_codes": ["O-001"],
                        "service_type": "pipe",
                        "quantity": "1",
                    }
                ],
            },
        )
        physical_lock = client.post(
            f"/api/v1/agent/estimates/{estimate_id}/physical-model/lock",
            headers=headers,
            json={"reason": "Validator must not create a Physical Model Lock"},
        )
        snapshot_lock = client.post(
            f"/api/v1/agent/estimates/{estimate_id}/lock",
            headers=headers,
            json={"reason": "Validator must not create a validated snapshot"},
        )

    assert evidence.status_code == 200
    assert evidence.json()["agent_id"] == "cf-validator"
    assert evidence.json()["evidence"] == []

    assert physical.status_code == 200
    assert physical.json()["agent_id"] == "cf-validator"
    assert physical.json()["openings"] == []

    assert evidence_write.status_code == 403
    assert evidence_write.json()["detail"] == "Agent scope required: evidence:write"

    assert physical_write.status_code == 403
    assert physical_write.json()["detail"] == "Agent scope required: physical:write"

    assert physical_lock.status_code == 403
    assert physical_lock.json()["detail"] == "Agent scope required: physical:lock"

    assert snapshot_lock.status_code == 403
    assert snapshot_lock.json()["detail"] == "Agent scope required: snapshot:lock"
