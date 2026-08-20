from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from physical_foundation_support import add_estimate, physical_session
from sqlalchemy import func, select
from starlette.requests import Request
from test_adjudicated_physical_submission import _admission

from classifire.agent_security import provision_agent_principal, require_agent_scope
from classifire.api.agent_api import (
    InitialPhysicalModelSubmissionRequest,
    agent_health,
    agent_submit_initial_physical_model,
)
from classifire.models import AgentServicePrincipal, AuditEvent, Opening, Service
from classifire.physical_models import PhysicalModelLock, PhysicalModelSubmissionReceipt


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "headers": [],
            "client": ("127.0.0.1", 50000),
        }
    )


def _writer(db) -> AgentServicePrincipal:  # type: ignore[no-untyped-def]
    principal, _token = provision_agent_principal(
        db,
        agent_id="cf-adjudicated-physical-writer",
        display_name="Adjudicated physical writer",
    )
    return principal


def test_agent_route_consumes_only_admission_and_returns_durable_receipt() -> None:
    with physical_session() as db:
        estimate = add_estimate(db)
        admission = _admission(db, estimate)
        principal = _writer(db)
        payload = InitialPhysicalModelSubmissionRequest(
            admission_id=admission.admission_id,
            idempotency_key="submission-request-0001",
        )

        result = agent_submit_initial_physical_model(payload, _request(), db, principal)

        assert result["canonical_write_performed"] is True
        assert result["physical_model_lock_created"] is False
        assert result["idempotent_replay"] is False
        assert db.scalar(select(func.count(Opening.id))) == 1
        assert db.scalar(select(func.count(Service.id))) == 1
        assert db.scalar(select(func.count(PhysicalModelSubmissionReceipt.id))) == 1
        assert db.scalar(select(func.count(PhysicalModelLock.id))) == 0
        audit = db.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "submit_adjudicated_initial_physical_model"
            )
        )
        assert audit is not None
        assert audit.actor_name == principal.agent_id
        assert audit.correlation_id != payload.idempotency_key

        replay = agent_submit_initial_physical_model(payload, _request(), db, principal)
        assert replay["receipt_sha256"] == result["receipt_sha256"]
        assert replay["idempotent_replay"] is True
        assert db.scalar(select(func.count(Opening.id))) == 1
        assert db.scalar(select(func.count(PhysicalModelSubmissionReceipt.id))) == 1

        with pytest.raises(HTTPException) as mismatched_replay:
            agent_submit_initial_physical_model(
                InitialPhysicalModelSubmissionRequest(
                    admission_id=admission.admission_id,
                    idempotency_key="submission-request-different",
                ),
                _request(),
                db,
                principal,
            )
        assert mismatched_replay.value.status_code == 409
        assert mismatched_replay.value.detail == {"code": "ADMISSION_IDEMPOTENCY_KEY_MISMATCH"}
        assert db.scalar(select(func.count(Opening.id))) == 1
        assert db.scalar(select(func.count(PhysicalModelSubmissionReceipt.id))) == 1


def test_agent_route_rejects_expired_admission_without_canonical_writes() -> None:
    with physical_session() as db:
        estimate = add_estimate(db)
        admission = _admission(db, estimate)
        admission.expires_at = datetime.now(UTC)
        principal = _writer(db)

        with pytest.raises(HTTPException) as rejected:
            agent_submit_initial_physical_model(
                InitialPhysicalModelSubmissionRequest(
                    admission_id=admission.admission_id,
                    idempotency_key="submission-request-expired",
                ),
                _request(),
                db,
                principal,
            )

        assert rejected.value.status_code == 409
        assert rejected.value.detail == {"code": "ADMISSION_EXPIRED"}
        assert db.scalar(select(func.count(Opening.id))) == 0
        assert db.scalar(select(func.count(PhysicalModelSubmissionReceipt.id))) == 0
        assert db.scalar(select(func.count(PhysicalModelLock.id))) == 0


def test_only_dedicated_writer_has_the_submission_scope() -> None:
    with physical_session() as db:
        writer = _writer(db)
        physical, _token = provision_agent_principal(db, agent_id="cf-physical-model")
        dependency = require_agent_scope("physical:adjudicated:submit")

        assert dependency(writer).id == writer.id
        assert agent_health(writer)["adjudicated_submission_exposed"] is True
        assert agent_health(writer)["physical_mutation_exposed"] is True
        assert agent_health(writer)["physical_lock_exposed"] is False
        with pytest.raises(HTTPException) as denied:
            dependency(physical)
        assert denied.value.status_code == 403


def test_agent_request_schema_cannot_accept_physical_facts_or_lock_fields() -> None:
    assert set(InitialPhysicalModelSubmissionRequest.model_fields) == {
        "admission_id",
        "idempotency_key",
    }
