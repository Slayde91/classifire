from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker
from test_shared_file_containment import _postgres_test_url
from test_signed_physical_model_lock_amendment import NOW
from test_signed_physical_model_lock_replacement import (
    _executed_amendment,
    _replacement_manifest,
)
from test_signed_physical_model_lock_replacement_admission import _register

from classifire import models, physical_models  # noqa: F401
from classifire.db import Base
from classifire.models import AuditEvent, Opening, Service, User
from classifire.physical_models import (
    PhysicalModelLock,
    PhysicalModelLockReplacementOutcome,
    ServiceOpeningLink,
)
from classifire.services.signed_physical_model_lock_replacement_execution import (
    execute_registered_signed_physical_model_lock_replacement,
)


@pytest.fixture
def postgresql_replacement_session_factory() -> Iterator[sessionmaker[Session]]:
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
    replacement_lock_admission_id: str,
    replacement_lock_envelope_sha256: str,
    public_key: str,
    actor: User,
) -> tuple[PhysicalModelLockReplacementOutcome, bool]:
    return execute_registered_signed_physical_model_lock_replacement(
        db,
        replacement_lock_admission_id=replacement_lock_admission_id,
        expected_replacement_lock_envelope_sha256=replacement_lock_envelope_sha256,
        pinned_public_key=public_key,
        expected_issuer="classifire-governance",
        expected_key_id="replacement-lock-p256-01",
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
    pytest.fail("The concurrent signed replacement-lock execution did not block")


def test_postgresql_exact_concurrent_execution_returns_one_lock_and_outcome(
    postgresql_replacement_session_factory: sessionmaker[Session],
) -> None:
    factory = postgresql_replacement_session_factory
    with factory() as setup_db:
        with setup_db.begin():
            estimate, _opening, superseded_lock, amendment_admission, amendment_outcome = (
                _executed_amendment(setup_db)
            )
            manifest, public_key = _replacement_manifest(
                setup_db,
                estimate,
                superseded_lock,
                amendment_admission,
                amendment_outcome,
            )
            admission, created = _register(setup_db, manifest, public_key)
            assert created is True
            first_actor = User(
                email="first-replacement-executor@example.test",
                full_name="First synthetic replacement-lock executor",
                password_hash="not-used",  # noqa: S106 - non-authenticating fixture
                role="estimator",
                is_active=True,
            )
            second_actor = User(
                email="second-replacement-executor@example.test",
                full_name="Second synthetic replacement-lock executor",
                password_hash="not-used",  # noqa: S106 - non-authenticating fixture
                role="estimator",
                is_active=True,
            )
            setup_db.add_all([first_actor, second_actor])
            setup_db.flush()
            estimate_id = estimate.id
            superseded_lock_id = superseded_lock.id
            first_actor_id = first_actor.id
            second_actor_id = second_actor.id
            replacement_lock_admission_id = admission.replacement_lock_admission_id
            replacement_lock_envelope_sha256 = admission.replacement_lock_envelope_sha256

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
                        replacement_lock_admission_id=replacement_lock_admission_id,
                        replacement_lock_envelope_sha256=(replacement_lock_envelope_sha256),
                        public_key=public_key,
                        actor=second_actor,
                    )
                    second_result["outcome_id"] = outcome.id
                    second_result["replacement_lock_id"] = outcome.replacement_lock_id
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
                replacement_lock_admission_id=replacement_lock_admission_id,
                replacement_lock_envelope_sha256=replacement_lock_envelope_sha256,
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
        "replacement_lock_id": first_outcome.replacement_lock_id,
        "created": False,
    }

    with factory() as verification_db:
        outcomes = list(verification_db.scalars(select(PhysicalModelLockReplacementOutcome)).all())
        assert [outcome.id for outcome in outcomes] == [first_outcome.id]
        superseded = verification_db.get(PhysicalModelLock, superseded_lock_id)
        replacement = verification_db.get(PhysicalModelLock, first_outcome.replacement_lock_id)
        assert superseded is not None and superseded.invalidated_at is not None
        assert replacement is not None and replacement.invalidated_at is None
        assert (
            verification_db.scalar(
                select(func.count(PhysicalModelLock.id)).where(
                    PhysicalModelLock.estimate_id == estimate_id,
                    PhysicalModelLock.invalidated_at.is_(None),
                )
            )
            == 1
        )
        assert verification_db.scalar(select(func.count(Opening.id))) == 1
        assert verification_db.scalar(select(func.count(Service.id))) == 1
        assert verification_db.scalar(select(func.count(ServiceOpeningLink.id))) == 1
        assert (
            verification_db.scalar(
                select(func.count(AuditEvent.id)).where(
                    AuditEvent.action == "execute_signed_physical_model_lock_replacement"
                )
            )
            == 1
        )
