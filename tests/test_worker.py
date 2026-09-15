from datetime import UTC, datetime, timedelta
from threading import Event, Thread, current_thread
from uuid import UUID

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from test_shared_file_containment import postgresql_session_factory as _postgres_fixture

from classifire import worker
from classifire.models import BackgroundJob

postgresql_session_factory = _postgres_fixture
NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is not None else NOW.replace(tzinfo=None)


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr(worker, "datetime", Clock)


@pytest.fixture
def queue(tmp_path, monkeypatch, clock):
    engine = create_engine("sqlite:///" + (tmp_path / "queue.sqlite3").as_posix())
    BackgroundJob.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(worker, "SessionLocal", factory)
    yield factory
    engine.dispose()


def job(number, *, status="queued", run_after=None, age=0):
    return BackgroundJob(
        id=str(UUID(int=number)),
        job_type="synthetic-unregistered",
        status=status,
        payload={"synthetic": True},
        run_after=run_after,
        created_at=NOW - timedelta(minutes=age),
    )


def snapshot(factory):
    with factory() as db:
        return sorted(repr(tuple(row)) for row in db.execute(select(BackgroundJob.__table__)))


@pytest.mark.parametrize(
    "status", ["queued", "preparing", "running", "complete", "failed", "interrupted"]
)
def test_future_and_nonqueued_records_are_not_claimed(queue, status):
    with queue() as db:
        db.add(
            job(
                1, status=status, run_after=NOW + timedelta(hours=1) if status == "queued" else None
            )
        )
        db.commit()
    before = snapshot(queue)
    assert worker.run_once() is False
    assert snapshot(queue) == before


def test_due_boundary_unscheduled_and_oldest_eligible_order(queue):
    with queue() as db:
        db.add_all(
            [
                job(1, run_after=NOW + timedelta(hours=1), age=30),
                job(2, run_after=NOW - timedelta(seconds=1), age=20),
                job(3, age=10),
                job(4, run_after=NOW),
            ]
        )
        db.commit()
    for number in (2, 3, 4):
        assert worker.run_once() is True
        with queue() as db:
            row = db.get(BackgroundJob, str(UUID(int=number)))
            assert row.status == "failed"  # No handlers are registered; preserve that outcome.
            assert row.attempts == 1 and row.started_at is not None and row.finished_at is not None
            assert row.error == "No registered handler for synthetic-unregistered"
            future = db.get(BackgroundJob, str(UUID(int=1)))
            assert future.status == "queued" and future.attempts == 0
            assert future.started_at is None and future.finished_at is None
    assert worker.run_once() is False


def test_equal_creation_times_have_stable_identity_order(queue):
    with queue() as db:
        db.add_all([job(9), job(8)])
        db.commit()
    assert worker.run_once() is True
    with queue() as db:
        assert db.get(BackgroundJob, str(UUID(int=8))).status == "failed"
        assert db.get(BackgroundJob, str(UUID(int=9))).status == "queued"


def test_postgresql_claim_leaves_other_due_job_available(
    postgresql_session_factory, monkeypatch, clock
):
    factory = postgresql_session_factory
    with factory() as db:
        bind = db.get_bind()
        db.add_all([job(1), job(2), job(3, run_after=NOW + timedelta(hours=1))])
        db.commit()
    claimed, release = Event(), Event()
    results, errors = [], []

    class PausedClaim(Session):
        held = False

        def commit(self):
            if not self.held:
                self.held = True
                claimed.set()
                if not release.wait(10):
                    raise AssertionError("The test did not release the claimed row")
            return super().commit()

    paused = sessionmaker(bind=bind, class_=PausedClaim, expire_on_commit=False)
    monkeypatch.setattr(
        worker,
        "SessionLocal",
        lambda: paused() if current_thread().name == "claim-owner" else factory(),
    )

    def claim_first():
        try:
            results.append(worker.run_once())
        except BaseException as exc:
            errors.append(exc)

    thread = Thread(target=claim_first, name="claim-owner", daemon=True)
    thread.start()
    try:
        assert claimed.wait(10), "The first worker never reached its claimed-row transaction"
        second = worker.run_once()
    finally:
        release.set()
        thread.join(10)
    assert not thread.is_alive() and not errors
    assert results == [True]
    assert second is True, "The first claim locked other eligible jobs"
    with factory() as db:
        rows = list(db.scalars(select(BackgroundJob).order_by(BackgroundJob.id)))
        assert [row.status for row in rows] == ["failed", "failed", "queued"]
        assert [row.attempts for row in rows] == [1, 1, 0]
        assert rows[2].started_at is None and rows[2].finished_at is None
