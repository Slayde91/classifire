from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from quantifire import canonical_models, commercial_models  # noqa: F401
from quantifire.commercial_models import GateEvidence
from quantifire.db import Base
from quantifire.main import app
from quantifire.models import Approval, AuditEvent, Estimate, Project, User
from quantifire.services.human_release import HumanReleaseError, release_estimate
from quantifire.services.validated_snapshot import SNAPSHOT_SCHEMA
from quantifire.services.workflow_db import assess_estimate_workflow


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def _estimate(db: Session) -> Estimate:
    project = Project(reference="REL-001", name="Human Release Test")
    db.add(project)
    db.flush()
    estimate = Estimate(
        project_id=project.id,
        revision=1,
        reference="REL-001-R1",
        title="Human Release Test",
        status="locked",
    )
    db.add(estimate)
    db.flush()
    return estimate


def _approver(db: Session) -> User:
    user = User(
        email="approver@example.com",
        full_name="Release Approver",
        password_hash="test-only",
        role="approver",
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def test_render_and_human_release_receipts_are_snapshot_specific() -> None:
    with _session() as db:
        estimate = _estimate(db)
        estimate.snapshot_hash = "a" * 64
        estimate.snapshot_json = {
            "schema": SNAPSHOT_SCHEMA,
            "snapshot_hash": estimate.snapshot_hash,
        }
        db.flush()

        db.add(
            AuditEvent(
                actor_type="system",
                actor_name="test",
                action="render_output",
                entity_type="estimate",
                entity_id=estimate.id,
                project_id=estimate.project_id,
                new_value={"snapshot_hash": "b" * 64},
                event_hash="1" * 64,
            )
        )
        db.add(
            Approval(
                entity_type="estimate",
                entity_id=estimate.id,
                approval_type="human_release",
                status="approved",
                snapshot_hash="b" * 64,
            )
        )
        db.flush()

        assessment = assess_estimate_workflow(db, estimate)
        assert not assessment.facts.output_rendered
        assert not assessment.facts.human_release_approved

        db.add(
            AuditEvent(
                actor_type="system",
                actor_name="test",
                action="render_output",
                entity_type="estimate",
                entity_id=estimate.id,
                project_id=estimate.project_id,
                new_value={"snapshot_hash": estimate.snapshot_hash},
                event_hash="2" * 64,
            )
        )
        db.flush()
        assessment = assess_estimate_workflow(db, estimate)
        assert assessment.facts.output_rendered
        assert not assessment.facts.human_release_approved

        db.add(
            Approval(
                entity_type="estimate",
                entity_id=estimate.id,
                approval_type="human_release",
                status="approved",
                snapshot_hash=estimate.snapshot_hash,
            )
        )
        db.flush()
        assessment = assess_estimate_workflow(db, estimate)
        assert assessment.facts.human_release_approved


def test_release_service_records_current_snapshot_and_is_idempotent(monkeypatch) -> None:
    with _session() as db:
        estimate = _estimate(db)
        user = _approver(db)
        estimate.snapshot_hash = "c" * 64
        estimate.snapshot_json = {
            "schema": SNAPSHOT_SCHEMA,
            "snapshot_hash": estimate.snapshot_hash,
            "estimate_certificate": {"final_certificate_hash": "d" * 64},
        }
        gate = GateEvidence(
            estimate_id=estimate.id,
            gate_type="FINAL_INDEPENDENT_VALIDATION",
            validator_id="test-validator",
            exception_count=0,
            result="PASS",
            run_id="QF-IV:test",
        )
        db.add(gate)
        db.flush()

        monkeypatch.setattr(
            "quantifire.services.human_release.require_estimate_action",
            lambda _db, _estimate, _action: None,
        )
        monkeypatch.setattr(
            "quantifire.services.human_release.latest_passing_gate",
            lambda _db, _estimate: gate,
        )

        first = release_estimate(
            db,
            estimate,
            approver=user,
            reason="Reviewed validated snapshot and controlled output for release.",
        )
        assert first.created
        assert first.approval.snapshot_hash == estimate.snapshot_hash
        assert first.approval.status == "approved"
        assert first.approval.decided_by_id == user.id
        assert estimate.status == "released"
        assert estimate.approved_by_id == user.id

        second = release_estimate(
            db,
            estimate,
            approver=user,
            reason="Repeat call for the same released snapshot.",
        )
        assert not second.created
        assert second.approval.id == first.approval.id
        assert db.query(Approval).filter(Approval.approval_type == "human_release").count() == 1


def test_release_service_requires_decision_reason() -> None:
    with _session() as db:
        estimate = _estimate(db)
        user = _approver(db)
        try:
            release_estimate(db, estimate, approver=user, reason="   ")
        except HumanReleaseError as exc:
            assert "reason" in str(exc).lower()
        else:
            raise AssertionError("Blank human release reason should fail closed")


def test_human_release_route_is_registered() -> None:
    paths = app.openapi()["paths"]
    path = "/api/v1/estimates/{estimate_id}/release"
    assert path in paths
    assert "post" in paths[path]
