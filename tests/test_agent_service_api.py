from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from classifire import canonical_models, commercial_models  # noqa: F401
from classifire.agent_security import (
    AGENT_SCOPE_MAP,
    FORBIDDEN_AGENT_SCOPES,
    provision_agent_principal,
)
from classifire.api.agent_api import router as agent_router
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


def test_valid_agent_token_reaches_health_and_never_exposes_human_release() -> None:
    app, factory = _test_app()
    token = _credential(factory, "cf-orchestrator")
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/agent/health",
            headers=_headers("cf-orchestrator", token),
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["agent_id"] == "cf-orchestrator"
    assert payload["human_release_exposed"] is False
    assert "workflow:read" in payload["scopes"]

    paths = app.openapi()["paths"]
    assert not any(path.startswith("/api/v1/agent") and path.endswith("/release") for path in paths)


def test_agent_id_header_cannot_impersonate_another_agent_token() -> None:
    app, factory = _test_app()
    token = _credential(factory, "cf-orchestrator")
    _credential(factory, "cf-validator")
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/agent/health",
            headers=_headers("cf-validator", token),
        )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid agent token"


def test_missing_agent_scope_fails_before_endpoint_business_logic() -> None:
    app, factory = _test_app()
    token = _credential(factory, "cf-validator")
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/agent/library/releases",
            headers=_headers("cf-validator", token),
        )
    assert response.status_code == 403
    assert "library:read" in response.json()["detail"]


def test_orchestrator_can_read_workflow_but_cannot_run_validation() -> None:
    app, factory = _test_app()
    token = _credential(factory, "cf-orchestrator")
    with factory() as db:
        project = Project(reference="AGENT-001", name="Agent API Test")
        db.add(project)
        db.flush()
        estimate = Estimate(
            project_id=project.id,
            revision=1,
            reference="AGENT-001-R1",
            title="Agent API Test",
            status="draft",
        )
        db.add(estimate)
        db.commit()
        estimate_id = estimate.id

    with TestClient(app) as client:
        workflow = client.get(
            f"/api/v1/agent/estimates/{estimate_id}/workflow",
            headers=_headers("cf-orchestrator", token),
        )
        validation = client.post(
            f"/api/v1/agent/estimates/{estimate_id}/independent-validation",
            headers=_headers("cf-orchestrator", token),
        )
    assert workflow.status_code == 200
    assert workflow.json()["stage"] == "evidence_intake"
    assert validation.status_code == 403
    assert "validation:run" in validation.json()["detail"]


def test_rotating_service_token_invalidates_previous_token() -> None:
    app, factory = _test_app()
    first = _credential(factory, "cf-platform-governance")
    second = _credential(factory, "cf-platform-governance")
    with TestClient(app) as client:
        old_response = client.get(
            "/api/v1/agent/health",
            headers=_headers("cf-platform-governance", first),
        )
        new_response = client.get(
            "/api/v1/agent/health",
            headers=_headers("cf-platform-governance", second),
        )
    assert old_response.status_code == 401
    assert new_response.status_code == 200


def test_controlled_agent_scope_map_contains_no_human_release_authority() -> None:
    for agent_id, scopes in AGENT_SCOPE_MAP.items():
        assert not (set(scopes) & FORBIDDEN_AGENT_SCOPES), agent_id
        assert "human_release" not in scopes
        assert "estimate:approve" not in scopes
