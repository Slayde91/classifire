from __future__ import annotations

import pytest
from fastapi import HTTPException
from physical_foundation_support import (
    add_estimate,
    add_evidence,
    add_service_link,
    physical_session,
)
from physical_foundation_support import (
    add_opening as add_physical_opening,
)
from physical_foundation_support import (
    add_service as add_physical_service,
)
from sqlalchemy import func, select
from starlette.requests import Request

from classifire.api.router import (
    add_line,
    add_opening,
    add_service,
    evaluate_rules,
    export_estimate,
    lock_estimate,
    recalculate,
)
from classifire.config import Settings
from classifire.estimate_pinning import refresh as refresh_release_basis
from classifire.models import EstimateLine, Opening, Service, User
from classifire.physical_models import ServiceOpeningLink
from classifire.schemas import EstimateLineInput, OpeningInput, ServiceInput
from classifire.security import create_human_session
from classifire.services.physical_model import create_physical_model_lock
from classifire.services.workflow_guard import (
    PhysicalModelLockRequiredError,
    require_active_physical_model_lock,
)
from classifire.ui import estimate_add_line, estimate_evaluate, estimate_lock

_PHYSICAL_BOUNDARY_CSRF = "c" * 43  # noqa: S105 - isolated test value.


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "headers": [],
            "client": ("127.0.0.1", 50000),
        }
    )


def _ui_request(session, user: User) -> Request:  # type: ignore[no-untyped-def]
    token = create_human_session(session, user)
    return Request(
        {
            "type": "http",
            "method": "POST",
            "headers": [],
            "client": ("127.0.0.1", 50000),
            "session": {
                "session_schema": 1,
                "session_token": token,
                "csrf_token": _PHYSICAL_BOUNDARY_CSRF,
            },
        }
    )


def _user(session) -> User:  # type: ignore[no-untyped-def]
    user = User(
        email="physical-boundary@example.test",
        full_name="Physical Boundary Test",
        password_hash="not-used-by-direct-handler-test",  # noqa: S106 - direct handler bypasses auth.
        role="administrator",
    )
    session.add(user)
    session.flush()
    return user


def test_human_opening_route_requires_retained_evidence() -> None:
    with physical_session() as session:
        estimate = add_estimate(session)
        user = _user(session)

        with pytest.raises(HTTPException) as blocked:
            add_opening(
                estimate.id,
                OpeningInput(opening_code="O-001"),
                _request(),
                session,
                user,
            )

        assert blocked.value.status_code == 409
        assert session.scalar(select(func.count(Opening.id))) == 0


def test_human_service_route_creates_canonical_link_and_locked_model_rejects_opening() -> None:
    with physical_session() as session:
        estimate = add_estimate(session)
        add_evidence(session, estimate)
        user = _user(session)
        request = _request()
        legacy_settings = Settings(adjudicated_initial_submission_enabled=False)

        opening_result = add_opening(
            estimate.id,
            OpeningInput(
                opening_code="O-001",
                defect_id="D-001",
                opening_type="service_penetration",
                substrate_type="concrete",
                substrate_plane="wall",
                orientation="horizontal",
                frl="-/120/120",
            ),
            request,
            session,
            user,
            legacy_settings,
        )
        opening = session.get(Opening, opening_result["id"])
        assert opening is not None

        service_result = add_service(
            opening.id,
            ServiceInput(service_code="S-001", service_type="pipe", material="PVC"),
            request,
            session,
            user,
        )
        assert session.get(Service, service_result["id"]) is not None
        assert (
            session.scalar(
                select(func.count(ServiceOpeningLink.id)).where(
                    ServiceOpeningLink.opening_id == opening.id
                )
            )
            == 1
        )

        lock, created = create_physical_model_lock(session, estimate)
        assert created
        assert lock.validator_result == "PASS"

        with pytest.raises(HTTPException) as blocked:
            add_opening(
                estimate.id,
                OpeningInput(opening_code="O-002"),
                request,
                session,
                user,
                legacy_settings,
            )

        assert blocked.value.status_code == 409
        assert session.scalar(select(Opening).where(Opening.opening_code == "O-002")) is None


def _assert_physical_lock_conflict(operation) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(HTTPException) as blocked:
        operation()

    assert blocked.value.status_code == 409
    assert "Physical Model Lock" in str(blocked.value.detail)


def test_downstream_api_routes_fail_closed_without_a_physical_model_lock(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with physical_session() as session:
        estimate = add_estimate(session)
        user = _user(session)
        request = _request()
        line = EstimateLineInput(component_type="labour", description="Must not be written")

        for operation in (
            lambda: add_line(estimate.id, line, request, session, user),
            lambda: recalculate(estimate.id, request, session, user),
            lambda: evaluate_rules(estimate.id, request, session, user),
            lambda: lock_estimate(estimate.id, "must not lock", request, session, user),
            lambda: export_estimate(
                estimate.id,
                "technical-pdf",
                session,
                user,
                Settings(storage_root=tmp_path / "exports"),
            ),
        ):
            _assert_physical_lock_conflict(operation)

        assert session.scalar(select(func.count(EstimateLine.id))) == 0
        assert estimate.snapshot_hash is None


def test_downstream_ui_and_release_routes_fail_closed_without_a_physical_model_lock() -> None:
    with physical_session() as session:
        estimate = add_estimate(session)
        user = _user(session)
        request = _ui_request(session, user)

        for operation in (
            lambda: estimate_add_line(
                estimate.id,
                request,
                session,
                _PHYSICAL_BOUNDARY_CSRF,
                "labour",
                "Must not be written",
                "1",
                "each",
                "1",
            ),
            lambda: estimate_evaluate(
                estimate.id,
                request,
                session,
                _PHYSICAL_BOUNDARY_CSRF,
            ),
            lambda: estimate_lock(
                estimate.id,
                request,
                session,
                _PHYSICAL_BOUNDARY_CSRF,
                "must not lock",
            ),
            lambda: refresh_release_basis(
                estimate.id,
                request,
                session,
                _PHYSICAL_BOUNDARY_CSRF,
                "must not refresh release basis",
            ),
        ):
            _assert_physical_lock_conflict(operation)

        assert session.scalar(select(func.count(EstimateLine.id))) == 0
        assert estimate.snapshot_hash is None


def test_every_downstream_route_rejects_a_stale_physical_model_lock(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with physical_session() as session:
        estimate = add_estimate(session)
        add_evidence(session, estimate)
        opening = add_physical_opening(session, estimate, opening_type="service_penetration")
        service = add_physical_service(session, opening)
        add_service_link(session, service, opening)
        lock, created = create_physical_model_lock(session, estimate)
        assert created
        assert lock.validator_result == "PASS"

        opening.notes = "Physical facts changed after lock"
        session.flush()

        user = _user(session)
        request = _request()
        ui_request = _ui_request(session, user)
        line = EstimateLineInput(component_type="labour", description="Must not be written")

        for operation in (
            lambda: add_line(estimate.id, line, request, session, user),
            lambda: recalculate(estimate.id, request, session, user),
            lambda: evaluate_rules(estimate.id, request, session, user),
            lambda: lock_estimate(estimate.id, "must not lock", request, session, user),
            lambda: export_estimate(
                estimate.id,
                "technical-pdf",
                session,
                user,
                Settings(storage_root=tmp_path / "exports"),
            ),
            lambda: estimate_add_line(
                estimate.id,
                ui_request,
                session,
                _PHYSICAL_BOUNDARY_CSRF,
                "labour",
                "Must not be written",
                "1",
                "each",
                "1",
            ),
            lambda: estimate_evaluate(
                estimate.id,
                ui_request,
                session,
                _PHYSICAL_BOUNDARY_CSRF,
            ),
            lambda: estimate_lock(
                estimate.id,
                ui_request,
                session,
                _PHYSICAL_BOUNDARY_CSRF,
                "must not lock",
            ),
            lambda: refresh_release_basis(
                estimate.id,
                ui_request,
                session,
                _PHYSICAL_BOUNDARY_CSRF,
                "must not refresh release basis",
            ),
        ):
            _assert_physical_lock_conflict(operation)

        assert session.scalar(select(func.count(EstimateLine.id))) == 0
        assert estimate.snapshot_hash is None


def test_downstream_guard_allows_a_current_passing_physical_model_lock() -> None:
    with physical_session() as session:
        estimate = add_estimate(session)
        add_evidence(session, estimate)
        opening = add_physical_opening(session, estimate, opening_type="service_penetration")
        service = add_physical_service(session, opening)
        add_service_link(session, service, opening)
        lock, created = create_physical_model_lock(session, estimate)

        assert created
        assert lock.validator_result == "PASS"
        assert require_active_physical_model_lock(session, estimate).facts.physical_model_locked


def test_downstream_guard_rejects_an_estimate_without_a_lock() -> None:
    with physical_session() as session:
        estimate = add_estimate(session)

        with pytest.raises(PhysicalModelLockRequiredError):
            require_active_physical_model_lock(session, estimate)
