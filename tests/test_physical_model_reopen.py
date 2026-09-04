from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from physical_foundation_support import (
    add_estimate,
    add_evidence,
    add_opening,
    add_service,
    add_service_link,
    physical_session,
)
from sqlalchemy import func, select
from starlette.requests import Request

from classifire.api.physical_model import (
    PhysicalModelReopenRequest,
    reopen_physical_model,
)
from classifire.api.physical_model import (
    router as physical_model_router,
)
from classifire.db import get_db
from classifire.models import AuditEvent, EstimateLine, Opening, RuleEvaluation, Service, User
from classifire.physical_models import PhysicalModelLock, ServiceOpeningLink
from classifire.security import get_current_user
from classifire.services.physical_model import create_physical_model_lock
from classifire.services.physical_model_reopen import (
    PhysicalModelReopenError,
    reopen_pretechnical_physical_model,
)
from classifire.services.physical_mutation_guard import require_physical_model_mutation


def _actor(db, *, role: str = "administrator"):  # type: ignore[no-untyped-def]
    actor = User(
        email=f"physical-reopen-{role}@example.test",
        full_name="Physical Reopen Test",
        password_hash="not-used-by-direct-service-test",  # noqa: S106
        role=role,
    )
    db.add(actor)
    db.flush()
    return actor


def _locked_physical_model(db):  # type: ignore[no-untyped-def]
    estimate = add_estimate(db)
    opening = add_opening(db, estimate)
    service = add_service(db, opening)
    add_service_link(db, service, opening)
    add_evidence(db, estimate)
    lock, created = create_physical_model_lock(db, estimate)
    assert created
    return estimate, opening, lock


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "headers": [],
            "client": ("127.0.0.1", 50000),
        }
    )


def test_reopen_invalidates_only_the_unsigned_lock_and_preserves_physical_rows() -> None:
    with physical_session() as db:
        estimate, _opening, lock = _locked_physical_model(db)
        actor = _actor(db)

        receipt = reopen_pretechnical_physical_model(
            db,
            estimate,
            actor=actor,
            reason="Human review requires a governed topology amendment.",
            now=datetime(2026, 9, 4, 6, 0, tzinfo=UTC),
            source_ip="127.0.0.1",
        )

        assert receipt.invalidated_lock_ids == (lock.id,)
        assert receipt.prior_content_hashes == (lock.content_hash,)
        assert receipt.opening_count == 1
        assert receipt.service_count == 1
        assert receipt.service_opening_link_count == 1
        assert receipt.reopened_at == "2026-09-04T06:00:00Z"
        assert lock.invalidated_at == datetime(2026, 9, 4, 6, 0, tzinfo=UTC)
        assert lock.invalidation_reason == "Human review requires a governed topology amendment."
        assert lock.record_version == 2
        assert db.scalar(select(func.count(Opening.id))) == 1
        assert db.scalar(select(func.count(Service.id))) == 1
        assert db.scalar(select(func.count(ServiceOpeningLink.id))) == 1
        assert db.scalar(select(func.count(PhysicalModelLock.id))) == 1
        audit = db.get(AuditEvent, receipt.audit_event_id)
        assert audit is not None
        assert audit.actor_user_id == actor.id
        assert audit.action == "reopen_pretechnical_physical_model"
        assert audit.reason == "Human review requires a governed topology amendment."
        assert audit.previous_value == {
            "active_lock_ids": [lock.id],
            "active_lock_content_hashes": [lock.content_hash],
            "current_content_hash": receipt.current_content_hash,
            "opening_count": 1,
            "service_count": 1,
            "service_opening_link_count": 1,
        }
        assert audit.new_value == {
            "active_lock_ids": [],
            "physical_model_preserved": True,
            "amendment_state": "unlocked_pretechnical",
        }
        require_physical_model_mutation(db, estimate)


def test_reopen_is_one_shot_after_the_active_lock_is_invalidated() -> None:
    with physical_session() as db:
        estimate, _opening, lock = _locked_physical_model(db)
        actor = _actor(db)

        reopen_pretechnical_physical_model(
            db,
            estimate,
            actor=actor,
            reason="The first governed amendment reopens the retained model.",
        )

        with pytest.raises(PhysicalModelReopenError) as rejected:
            reopen_pretechnical_physical_model(
                db,
                estimate,
                actor=actor,
                reason="A second request must not create another reopening audit record.",
            )

        assert rejected.value.code == "REOPEN_ACTIVE_LOCK_REQUIRED"
        assert lock.invalidated_at is not None
        assert db.scalar(select(func.count(AuditEvent.id))) == 1


@pytest.mark.parametrize(
    ("prepare", "expected_code"),
    [
        (
            lambda db, estimate, opening: setattr(estimate, "status", "released"),
            "REOPEN_ESTIMATE_STATUS_INVALID",
        ),
        (
            lambda db, estimate, opening: setattr(
                opening, "selected_technical_variant_id", "technical-variant-id"
            ),
            "REOPEN_TECHNICAL_DEPENDENCY_PRESENT",
        ),
        (
            lambda db, estimate, opening: db.add(
                EstimateLine(
                    estimate_id=estimate.id,
                    line_number=1,
                    component_type="labour",
                    description="Downstream commercial record",
                )
            ),
            "REOPEN_COMMERCIAL_DEPENDENCY_PRESENT",
        ),
        (
            lambda db, estimate, opening: db.add(
                RuleEvaluation(
                    estimate_id=estimate.id,
                    rule_id="rule-id",
                    result="pass",
                    severity="info",
                    explanation="Downstream rule record",
                    inputs={},
                    output={},
                    rule_version=1,
                )
            ),
            "REOPEN_RULE_DEPENDENCY_PRESENT",
        ),
        (
            lambda db, estimate, opening: setattr(estimate, "snapshot_hash", "s" * 64),
            "REOPEN_SNAPSHOT_OR_RELEASE_PRESENT",
        ),
        (
            lambda db, estimate, opening: setattr(
                db.scalar(select(PhysicalModelLock)), "signature", "signed"
            ),
            "REOPEN_SIGNED_LOCK_UNSUPPORTED",
        ),
    ],
)
def test_reopen_refuses_unsafe_or_later_stage_state(prepare, expected_code) -> None:  # type: ignore[no-untyped-def]
    with physical_session() as db:
        estimate, opening, lock = _locked_physical_model(db)
        actor = _actor(db)
        prepare(db, estimate, opening)
        db.flush()

        with pytest.raises(PhysicalModelReopenError) as rejected:
            reopen_pretechnical_physical_model(
                db,
                estimate,
                actor=actor,
                reason="Requested amendment must stay before downstream work.",
            )

        assert rejected.value.code == expected_code
        assert lock.invalidated_at is None
        assert db.scalar(select(func.count(AuditEvent.id))) == 0


def test_reopen_requires_an_active_lock_an_active_actor_and_a_reason() -> None:
    with physical_session() as db:
        estimate, _opening, lock = _locked_physical_model(db)
        actor = _actor(db)
        lock.invalidated_at = datetime(2026, 9, 4, tzinfo=UTC)
        db.flush()

        with pytest.raises(PhysicalModelReopenError) as no_active_lock:
            reopen_pretechnical_physical_model(
                db,
                estimate,
                actor=actor,
                reason="A reason is present but no active lock remains.",
            )
        assert no_active_lock.value.code == "REOPEN_ACTIVE_LOCK_REQUIRED"

        lock.invalidated_at = None
        actor.is_active = False
        with pytest.raises(PhysicalModelReopenError) as inactive_actor:
            reopen_pretechnical_physical_model(
                db,
                estimate,
                actor=actor,
                reason="A reason is present but actor is inactive.",
            )
        assert inactive_actor.value.code == "REOPEN_ACTOR_INVALID"

        actor.is_active = True
        with pytest.raises(PhysicalModelReopenError) as missing_reason:
            reopen_pretechnical_physical_model(db, estimate, actor=actor, reason="   ")
        assert missing_reason.value.code == "REOPEN_REASON_INVALID"
        assert lock.invalidated_at is None
        assert db.scalar(select(func.count(AuditEvent.id))) == 0


def test_reopen_endpoint_commits_an_audited_unlock_for_amendment() -> None:
    with physical_session() as db:
        estimate, _opening, lock = _locked_physical_model(db)
        actor = _actor(db)

        result = reopen_physical_model(
            estimate.id,
            PhysicalModelReopenRequest(reason="Human review requires a retained amendment."),
            _request(),
            db,
            actor,
        )

        assert result["estimate_id"] == estimate.id
        assert result["invalidated_lock_ids"] == [lock.id]
        assert lock.invalidated_at is not None
        assert db.scalar(select(AuditEvent.id).where(AuditEvent.id == result["audit_event_id"]))


def _route_app(db, actor: User) -> FastAPI:  # type: ignore[no-untyped-def]
    app = FastAPI()
    app.include_router(physical_model_router)

    def override_db():  # type: ignore[no-untyped-def]
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: actor
    return app


def test_reopen_route_requires_estimate_write_and_preserves_lock_on_denial() -> None:
    with physical_session() as db:
        estimate, _opening, lock = _locked_physical_model(db)
        read_only_actor = _actor(db, role="read_only")

        with TestClient(_route_app(db, read_only_actor)) as client:
            response = client.post(
                f"/api/v1/estimates/{estimate.id}/physical-model/reopen",
                json={"reason": "A read-only user must not reopen physical state."},
            )

        assert response.status_code == 403
        assert lock.invalidated_at is None
        assert db.scalar(select(func.count(AuditEvent.id))) == 0


def test_reopen_route_applies_an_authorised_audited_unlock() -> None:
    with physical_session() as db:
        estimate, _opening, lock = _locked_physical_model(db)
        actor = _actor(db)

        with TestClient(_route_app(db, actor)) as client:
            response = client.post(
                f"/api/v1/estimates/{estimate.id}/physical-model/reopen",
                json={"reason": "An authorised human requires a governed amendment."},
            )

        assert response.status_code == 200
        assert response.json()["invalidated_lock_ids"] == [lock.id]
        assert lock.invalidated_at is not None
        assert db.scalar(select(func.count(AuditEvent.id))) == 1
