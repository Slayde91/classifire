from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from classifire import canonical_models, commercial_models  # noqa: F401
from classifire.agent_security import AGENT_SCOPE_MAP, FORBIDDEN_AGENT_SCOPES, provision_agent_principal
from classifire.api.agent_controlled_write import router as controlled_write_router
from classifire.db import Base, get_db


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
    app.include_router(controlled_write_router)

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


def test_controlled_write_scope_matrix_is_role_specific() -> None:
    assert "quantity:derive" in AGENT_SCOPE_MAP["cf-physical-model"]
    assert "technical:select" in AGENT_SCOPE_MAP["cf-technical-system"]
    assert "technical:lock" in AGENT_SCOPE_MAP["cf-technical-system"]
    assert "commercial:components" in AGENT_SCOPE_MAP["cf-commercial-engine"]
    assert "commercial:derive" in AGENT_SCOPE_MAP["cf-commercial-engine"]

    for agent_id, scopes in AGENT_SCOPE_MAP.items():
        assert not (set(scopes) & FORBIDDEN_AGENT_SCOPES), agent_id
        if agent_id != "cf-physical-model":
            assert "quantity:derive" not in scopes
        if agent_id != "cf-technical-system":
            assert "technical:select" not in scopes
            assert "technical:lock" not in scopes
        if agent_id != "cf-commercial-engine":
            assert "commercial:components" not in scopes
            assert "commercial:derive" not in scopes


def test_cross_role_write_calls_fail_before_business_logic() -> None:
    app, factory = _test_app()
    commercial_token = _credential(factory, "cf-commercial-engine")
    technical_token = _credential(factory, "cf-technical-system")
    physical_token = _credential(factory, "cf-physical-model")

    with TestClient(app) as client:
        commercial_to_technical = client.post(
            "/api/v1/agent/openings/not-real/repair-strategy",
            headers=_headers("cf-commercial-engine", commercial_token),
            json={"variant_id": "VAR-001"},
        )
        technical_to_commercial = client.post(
            "/api/v1/agent/estimates/not-real/commercial/derive",
            headers=_headers("cf-technical-system", technical_token),
            json={},
        )
        physical_to_technical_lock = client.post(
            "/api/v1/agent/openings/not-real/repair-strategy/lock",
            headers=_headers("cf-physical-model", physical_token),
        )

    assert commercial_to_technical.status_code == 403
    assert "technical:select" in commercial_to_technical.json()["detail"]
    assert technical_to_commercial.status_code == 403
    assert "commercial:derive" in technical_to_commercial.json()["detail"]
    assert physical_to_technical_lock.status_code == 403
    assert "technical:lock" in physical_to_technical_lock.json()["detail"]


def test_authorised_write_scopes_reach_business_logic() -> None:
    app, factory = _test_app()
    technical_token = _credential(factory, "cf-technical-system")
    physical_token = _credential(factory, "cf-physical-model")
    commercial_token = _credential(factory, "cf-commercial-engine")

    with TestClient(app) as client:
        technical = client.post(
            "/api/v1/agent/openings/not-real/repair-strategy",
            headers=_headers("cf-technical-system", technical_token),
            json={"variant_id": "VAR-001"},
        )
        physical = client.post(
            "/api/v1/agent/estimates/not-real/quantity-labour/derive",
            headers=_headers("cf-physical-model", physical_token),
            json={},
        )
        commercial = client.get(
            "/api/v1/agent/estimates/not-real/required-components",
            headers=_headers("cf-commercial-engine", commercial_token),
        )

    assert technical.status_code == 404
    assert physical.status_code == 404
    assert commercial.status_code == 404


def test_controlled_write_openapi_exposes_no_human_release_or_approval_route() -> None:
    app, _factory = _test_app()
    paths = set(app.openapi()["paths"])
    expected = {
        "/api/v1/agent/openings/{opening_id}/repair-strategy",
        "/api/v1/agent/openings/{opening_id}/repair-strategy/lock",
        "/api/v1/agent/estimates/{estimate_id}/quantity-labour/derive",
        "/api/v1/agent/estimates/{estimate_id}/required-components",
        "/api/v1/agent/estimates/{estimate_id}/commercial/derive",
    }
    assert expected <= paths
    forbidden_segments = {"release", "human-release", "human_release", "approve", "approval"}
    for path in paths:
        segments = {segment.lower() for segment in path.split("/") if segment}
        assert not (segments & forbidden_segments), path
