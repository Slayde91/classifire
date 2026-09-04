from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker
from test_shared_file_containment import _postgres_test_url
from test_signed_physical_model_lock_amendment import NOW
from test_signed_physical_model_lock_amendment_admission import _register
from test_signed_physical_model_lock_amendment_preflight import _prepared_preflight

from classifire import models, physical_models  # noqa: F401
from classifire.db import Base
from classifire.models import AuditEvent, Opening, Service, User
from classifire.physical_models import (
    PhysicalModelLock,
    PhysicalModelLockAmendmentOutcome,
    ServiceOpeningLink,
)
from classifire.services.signed_physical_model_lock_amendment_execution import (
    execute_registered_signed_physical_model_lock_amendment,
)


@pytest.fixture
def postgresql_amendment_session_factory() -> Iterator[sessionmaker[Session]]:
    """Reset only the explicit loopback disposable PostgreSQL test database."""

    engine = create_engine(_postgres_test_url(), pool_size=4, max_overflow=0, pool_pre_ping=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _execute(
    db: Session,
    *,
    amendment_admission_id: str,
    amendment_envelope_sha256: str,
    public_key: str,
    actor: User,
) -> tuple[PhysicalModelLockAmendmentOutcome, bool]:
    return execute_registered_signed_physical_model_lock_amendment(
        db,
        amendment_admission_id=amendment_admission_id,
        expected_amendment_envelope_sha256=amendment_envelope_sha256,
        pinned_public_key=public_key,
        expected_issuer="classifire-governance",
        expected_key_id="amendment-p256-01",
        actor=actor,
        now=NOW,
        source_ip="127.0.0.1",
    )


def _wait_until_blocked_by(
    db: Session,
    *,
    waiting_pid: int,
    blocking_pid: int,
) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        blockers = db.scalar(
            text("SELECT pg_blocking_pids(:waiting_pid)"),
            {"waiting_pid": waiting_pid},
        )
        if blockers is not None and blocking_pid in blockers:
            return
        time.sleep(0.02)
    pytest.fail("The concurrent signed-amendment execution did not block")


def test_postgresql_exact_concurrent_execution_returns_one_outcome(
    postgresql_amendment_session_factory: sessionmaker[Session],
) -> None:
    factory = postgresql_amendment_session_factory
    with factory() as setup_db:
        with setup_db.begin():
            estimate, _opening, target_lock, payload, manifest, public_key = _prepared_preflight(
                setup_db
            )
            admission, created = _register(setup_db, payload, manifest, public_key)
            assert created is True
            first_actor = User(
                email="first-amendment-executor@example.test",
                full_name="First synthetic amendment executor",
                password_hash="not-used",  # noqa: S106 - non-authenticating fixture
                role="estimator",
                is_active=True,
            )
            second_actor = User(
                email="second-amendment-executor@example.test",
                full_name="Second synthetic amendment executor",
                password_hash="not-used",  # noqa: S106 - non-authenticating fixture
                role="estimator",
                is_active=True,
            )
            setup_db.add_all([first_actor, second_actor])
            setup_db.flush()
            estimate_id = estimate.id
            target_lock_id = target_lock.id
            first_actor_id = first_actor.id
            second_actor_id = second_actor.id
            amendment_admission_id = admission.amendment_admission_id
            amendment_envelope_sha256 = admission.amendment_envelope_sha256

    second_ready = threading.Event()
    second_finished = threading.Event()
    second_result: dict[str, object] = {}

    def execute_in_second_session() -> None:
        try:
            with factory() as second_db:
                with second_db.begin():
                    second_db.execute(text("SET LOCAL lock_timeout = 5000"))
                    second_result["pid"] = int(second_db.scalar(text("SELECT pg_backend_pid()")))
                    second_actor = second_db.get(User, second_actor_id)
                    assert second_actor is not None
                    second_ready.set()
                    outcome, created = _execute(
                        second_db,
                        amendment_admission_id=amendment_admission_id,
                        amendment_envelope_sha256=amendment_envelope_sha256,
                        public_key=public_key,
                        actor=second_actor,
                    )
                    second_result["outcome_id"] = outcome.id
                    second_result["created"] = created
        except Exception as exc:  # pragma: no cover - assertion reports safe type only
            second_result["error_type"] = type(exc).__name__
        finally:
            second_finished.set()

    second_thread = threading.Thread(target=execute_in_second_session, daemon=True)
    with factory() as first_db:
        with first_db.begin():
            first_db.execute(text("SET LOCAL lock_timeout = 5000"))
            first_pid = int(first_db.scalar(text("SELECT pg_backend_pid()")))
            first_actor = first_db.get(User, first_actor_id)
            assert first_actor is not None
            first_outcome, first_created = _execute(
                first_db,
                amendment_admission_id=amendment_admission_id,
                amendment_envelope_sha256=amendment_envelope_sha256,
                public_key=public_key,
                actor=first_actor,
            )
            assert first_created is True

            second_thread.start()
            assert second_ready.wait(5)
            _wait_until_blocked_by(
                first_db,
                waiting_pid=int(second_result["pid"]),
                blocking_pid=first_pid,
            )
            assert not second_finished.is_set()

    second_thread.join(5)
    assert second_finished.is_set()
    assert second_result == {
        "pid": second_result["pid"],
        "outcome_id": first_outcome.id,
        "created": False,
    }

    with factory() as verification_db:
        outcomes = list(verification_db.scalars(select(PhysicalModelLockAmendmentOutcome)).all())
        assert [outcome.id for outcome in outcomes] == [first_outcome.id]
        retained_lock = verification_db.get(PhysicalModelLock, target_lock_id)
        assert retained_lock is not None
        assert retained_lock.invalidated_at == NOW
        assert (
            verification_db.scalar(
                select(func.count(PhysicalModelLock.id)).where(
                    PhysicalModelLock.estimate_id == estimate_id,
                    PhysicalModelLock.invalidated_at.is_(None),
                )
            )
            == 0
        )
        assert verification_db.scalar(select(func.count(Opening.id))) == 1
        assert verification_db.scalar(select(func.count(Service.id))) == 1
        assert verification_db.scalar(select(func.count(ServiceOpeningLink.id))) == 1
        assert (
            verification_db.scalar(
                select(func.count(AuditEvent.id)).where(
                    AuditEvent.action == "execute_signed_physical_model_lock_amendment"
                )
            )
            == 1
        )
