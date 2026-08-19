from __future__ import annotations

import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.middleware.sessions import SessionMiddleware

from classifire.api.physical_model import router as physical_model_router
from classifire.api.router import router as api_router
from classifire.canonical_models import PhysicalModelLock
from classifire.config import Settings, get_settings
from classifire.db import Base, get_db
from classifire.models import Estimate, Opening, Project, User
from classifire.security import get_current_user, hash_password
from classifire.services.initial_canonicalisation_boundary import (
    InitialCanonicalisationAdmissionRequired,
    require_admission_bound_initial_canonicalisation,
)
from classifire.ui import router as ui_router


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


def _session() -> Session:
    return _session_factory()()


def _estimate(db: Session) -> Estimate:
    project = Project(reference="BOUNDARY-PROJECT", name="Boundary project")
    db.add(project)
    db.flush()
    estimate = Estimate(
        project_id=project.id,
        reference="BOUNDARY-ESTIMATE",
        title="Boundary estimate",
        status="draft",
    )
    db.add(estimate)
    db.flush()
    return estimate


def test_empty_estimate_requires_admission_when_boundary_is_enabled() -> None:
    db = _session()
    try:
        estimate = _estimate(db)

        with pytest.raises(InitialCanonicalisationAdmissionRequired):
            require_admission_bound_initial_canonicalisation(
                db,
                estimate_id=estimate.id,
                enabled=True,
            )

        require_admission_bound_initial_canonicalisation(
            db,
            estimate_id=estimate.id,
            enabled=False,
        )
    finally:
        db.close()


def test_existing_legacy_model_can_continue_through_human_edit_workflow() -> None:
    db = _session()
    try:
        estimate = _estimate(db)
        db.add(
            Opening(
                estimate_id=estimate.id,
                opening_code="O-001",
                location="Legacy opening",
                substrate_type="concrete",
                substrate_plane="wall",
                orientation="vertical",
                opening_type="service_penetration",
            )
        )
        db.flush()

        require_admission_bound_initial_canonicalisation(
            db,
            estimate_id=estimate.id,
            enabled=True,
        )
    finally:
        db.close()


def _empty_estimate_with_admin(factory: sessionmaker[Session]) -> tuple[str, User]:
    with factory() as db:
        estimate = _estimate(db)
        user = User(
            email="boundary@example.test",
            full_name="Boundary Administrator",
            password_hash=hash_password("boundary-password"),
            role="administrator",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return estimate.id, user


def _enabled_settings() -> Settings:
    return Settings(adjudicated_initial_submission_enabled=True)


def test_json_opening_route_cannot_bypass_enabled_initial_model_boundary() -> None:
    factory = _session_factory()
    estimate_id, user = _empty_estimate_with_admin(factory)
    app = FastAPI()
    app.include_router(api_router)

    def override_db():  # type: ignore[no-untyped-def]
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings] = _enabled_settings

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/estimates/{estimate_id}/openings",
            json={"opening_code": "O-001"},
        )

    assert response.status_code == 409
    with factory() as db:
        assert db.get(Estimate, estimate_id) is not None
        assert db.query(Opening).filter(Opening.estimate_id == estimate_id).count() == 0


def test_html_opening_route_cannot_bypass_enabled_initial_model_boundary() -> None:
    factory = _session_factory()
    estimate_id, _user = _empty_estimate_with_admin(factory)
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="boundary-test-session-secret")
    app.include_router(ui_router)

    def override_db():  # type: ignore[no-untyped-def]
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = _enabled_settings

    with TestClient(app) as client:
        login_page = client.get("/login")
        csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', login_page.text)
        assert csrf_match is not None
        login = client.post(
            "/login",
            data={
                "csrf_token": csrf_match.group(1),
                "email": "boundary@example.test",
                "password": "boundary-password",
            },
            follow_redirects=False,
        )
        assert login.status_code == 303
        estimate_page = client.get(f"/estimates/{estimate_id}")
        csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', estimate_page.text)
        assert csrf_match is not None
        response = client.post(
            f"/estimates/{estimate_id}/openings",
            data={"csrf_token": csrf_match.group(1), "opening_code": "O-001"},
            follow_redirects=False,
        )

    assert response.status_code == 409
    with factory() as db:
        assert db.query(Opening).filter(Opening.estimate_id == estimate_id).count() == 0


def test_human_physical_model_lock_route_is_disabled_when_admission_boundary_is_enabled() -> None:
    factory = _session_factory()
    estimate_id, user = _empty_estimate_with_admin(factory)
    app = FastAPI()
    app.include_router(physical_model_router)

    def override_db():  # type: ignore[no-untyped-def]
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings] = _enabled_settings

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/estimates/{estimate_id}/physical-model/lock",
            json={"reason": "must require a future signed lock admission"},
        )

    assert response.status_code == 410
    with factory() as db:
        assert (
            db.query(PhysicalModelLock).filter(PhysicalModelLock.estimate_id == estimate_id).count()
            == 0
        )
