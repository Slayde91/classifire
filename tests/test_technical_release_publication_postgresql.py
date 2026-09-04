from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker
from test_shared_file_containment import _postgres_test_url
from test_technical_release_publication import NOW, _actor, _bound_variant

from classifire import models, physical_models  # noqa: F401
from classifire.db import Base
from classifire.models import AuditEvent, LibraryRelease, User
from classifire.services.technical_release_publication import (
    TechnicalReleasePublicationError,
    publish_governed_technical_release,
)


@pytest.fixture
def postgresql_release_session_factory() -> Iterator[sessionmaker[Session]]:
    """Reset only the explicit loopback disposable PostgreSQL test database."""

    engine = create_engine(_postgres_test_url(), pool_size=4, max_overflow=0, pool_pre_ping=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _publish(
    db: Session,
    *,
    actor: User,
    storage_root: Path,
) -> LibraryRelease:
    return publish_governed_technical_release(
        db,
        version="TECH-CONCURRENT-001",
        notes="Synthetic concurrent publication",
        actor=actor,
        storage_root=storage_root,
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
    pytest.fail("The concurrent technical release publication did not block")


def test_postgresql_concurrent_exact_publication_keeps_one_active_release(
    postgresql_release_session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    factory = postgresql_release_session_factory
    storage_root = (tmp_path / "technical-release-storage").resolve()
    with factory() as setup_db:
        with setup_db.begin():
            first_actor = _actor(setup_db)
            first_actor.email = "first-release-reviewer@example.test"
            second_actor = _actor(setup_db)
            second_actor.email = "second-release-reviewer@example.test"
            _bound_variant(setup_db, storage_root)
            setup_db.flush()
            first_actor_id = first_actor.id
            second_actor_id = second_actor.id

    second_ready = threading.Event()
    second_finished = threading.Event()
    second_result: dict[str, object] = {}

    def publish_in_second_session() -> None:
        try:
            with factory() as second_db:
                with second_db.begin():
                    second_db.execute(text("SET LOCAL lock_timeout = 5000"))
                    second_result["pid"] = int(
                        second_db.scalar(text("SELECT pg_backend_pid()"))
                    )
                    actor = second_db.get(User, second_actor_id)
                    assert actor is not None
                    second_ready.set()
                    release = _publish(
                        second_db,
                        actor=actor,
                        storage_root=storage_root,
                    )
                    second_result["release_id"] = release.id
        except TechnicalReleasePublicationError as exc:
            second_result["error_code"] = exc.code
        except Exception as exc:  # pragma: no cover - assertion reports safe type only
            second_result["error_type"] = type(exc).__name__
        finally:
            second_finished.set()

    second_thread = threading.Thread(target=publish_in_second_session, daemon=True)
    with factory() as first_db:
        with first_db.begin():
            first_db.execute(text("SET LOCAL lock_timeout = 5000"))
            first_pid = int(first_db.scalar(text("SELECT pg_backend_pid()")))
            actor = first_db.get(User, first_actor_id)
            assert actor is not None
            first_release = _publish(
                first_db,
                actor=actor,
                storage_root=storage_root,
            )

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
        "error_code": "TECHNICAL_RELEASE_PUBLICATION_WRITE_FAILED",
    }

    with factory() as verification_db:
        releases = list(verification_db.scalars(select(LibraryRelease)).all())
        assert [release.id for release in releases] == [first_release.id]
        assert releases[0].status == "active"
        assert (
            verification_db.scalar(
                select(func.count(AuditEvent.id)).where(
                    AuditEvent.action == "publish_governed_technical_release"
                )
            )
            == 1
        )
