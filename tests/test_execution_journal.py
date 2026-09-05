from __future__ import annotations

import json
from dataclasses import asdict, replace
from threading import Event, Thread
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from classifire.models import BackgroundJob
from classifire.services.execution_journal import (
    CaptureStart,
    ExecutionBinding,
    ExecutionJournal,
    ExecutionJournalError,
)
from classifire.services.phase8_openresponses_transport import (
    ExecutionCompletionContext,
    ExecutionCompletionEvidence,
    validate_execution_completion,
)

KEY = b"synthetic-journal-key-not-production-000"
BINDING = ExecutionBinding("cf-validator", "A" * 64, "B" * 64, "C" * 64, "D" * 64)


@pytest.fixture
def setup(tmp_path):
    engine = create_engine(
        "sqlite:///" + str(tmp_path / "journal.db"),
        connect_args={"check_same_thread": False},
    )
    BackgroundJob.__table__.create(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    clock = [100]
    run_id, owner_id = str(uuid4()), str(uuid4())
    yield sessions, clock, run_id, owner_id
    engine.dispose()


class Producer:
    def __init__(self, setup):
        self.sessions, self.clock, self.run_id, _ = setup
        self.starts = self.calls = 0
        self.context = None

    def start_capture(self, binding):
        self.starts += 1
        with self.sessions() as db:
            row = db.get(BackgroundJob, self.run_id)
            assert row.status == "preparing"
            assert row.payload["binding"] == asdict(binding)
        self.clock[0] = 110
        return CaptureStart("E" * 64, 105)

    def execute(self, binding, capture, started_at_ms):
        self.calls += 1
        # Independent session sees committed capture before simulated dispatch.
        with self.sessions() as db:
            row = db.get(BackgroundJob, self.run_id)
            assert row.status == "running"
            assert row.result["data"]["capture"] == asdict(capture)
            assert row.result["data"]["started_at_ms"] == started_at_ms == 110
        self.clock[0] = 120
        self.context = ExecutionCompletionContext(
            **asdict(binding),
            response_sha256="F" * 64,
            audit_receipt_sha256="0" * 64,
            started_at_ms=started_at_ms,
            observed_at_ms=120,
        )
        return self.context, ExecutionCompletionEvidence(
            context_sha256=self.context.sha256,
            receipt_sha256="1" * 64,
            terminal_at_ms=115,
            coverage_from_ms=105,
            coverage_through_ms=120,
            writer_enabled=True,
            writer_healthy=True,
            pending_events=0,
            dropped_events=0,
            tool_actions=0,
        )


def journal(setup, producer=None, **overrides):
    sessions, clock, _, _ = setup
    return ExecutionJournal(
        sessions=sessions,
        producer=producer or Producer(setup),
        authentication_key=overrides.get("key", KEY),
        producer_id=overrides.get("producer_id", "synthetic-producer"),
        clock_ms=lambda: clock[0],
    )


def execute(service, setup, **overrides):
    return service.execute(
        run_id=setup[2],
        owner_id=overrides.get("owner_id", setup[3]),
        binding=overrides.get("binding", BINDING),
    )


def test_committed_capture_terminal_and_restart_verification(setup):
    producer = Producer(setup)
    result = execute(journal(setup, producer), setup)
    assert result.receipt_sha256 != "1" * 64
    assert len(validate_execution_completion(result, producer.context)) == 64
    restarted = journal(setup)
    assert restarted.verify(run_id=setup[2], owner_id=setup[3], context=producer.context) == result
    assert execute(restarted, setup) == result
    assert producer.starts == producer.calls == 1
    with setup[0]() as db:
        row = db.get(BackgroundJob, setup[2])
        assert row.status == "complete"
        assert row.record_version == 3
        assert row.attempts == 1
        assert row.result["data"]["evidence"]["receipt_sha256"] == "1" * 64
        assert "synthetic-journal-key" not in json.dumps(row.result)
        assert len(db.scalars(select(BackgroundJob)).all()) == 1


@pytest.mark.parametrize("field", ["status", "record_version", "payload", "result"])
def test_tampered_storage_never_verifies(setup, field):
    producer = Producer(setup)
    execute(journal(setup, producer), setup)
    with setup[0]() as db, db.begin():
        row = db.get(BackgroundJob, setup[2])
        if field == "status":
            row.status = "running"
        elif field == "record_version":
            row.record_version += 1
        elif field == "payload":
            row.payload = {**row.payload, "owner_id": str(uuid4())}
        else:
            row.result = {**row.result, "data": {"private-response": "secret"}}
    with pytest.raises(ExecutionJournalError, match="JOURNAL_RECORD_INVALID"):
        journal(setup).verify(run_id=setup[2], owner_id=setup[3], context=producer.context)


@pytest.mark.parametrize("change", ["owner", "producer", "key", "context", "binding"])
def test_identity_and_authority_mismatch_refused(setup, change):
    producer = Producer(setup)
    execute(journal(setup, producer), setup)
    service = journal(
        setup,
        key=b"wrong-key-000000000000000000000000000" if change == "key" else KEY,
        producer_id="different-producer" if change == "producer" else "synthetic-producer",
    )
    with pytest.raises(ExecutionJournalError):
        if change == "binding":
            execute(service, setup, binding=replace(BINDING, request_sha256="9" * 64))
        else:
            service.verify(
                run_id=setup[2],
                owner_id=str(uuid4()) if change == "owner" else setup[3],
                context=(
                    replace(producer.context, response_sha256="9" * 64)
                    if change == "context"
                    else producer.context
                ),
            )


@pytest.mark.parametrize("stage", ["capture", "execution"])
def test_producer_failure_is_durable_safe_and_never_replayed(setup, stage):
    class Failing(Producer):
        def start_capture(self, binding):
            if stage == "capture":
                raise RuntimeError("private-provider-response")
            return super().start_capture(binding)

        def execute(self, *args):
            raise RuntimeError("private-provider-response")

    with pytest.raises(ExecutionJournalError, match="JOURNAL_EXECUTION_FAILED"):
        execute(journal(setup, Failing(setup)), setup)
    with setup[0]() as db:
        row = db.get(BackgroundJob, setup[2])
        assert row.status == "failed"
        assert "private-provider-response" not in json.dumps(row.result)
    with pytest.raises(ExecutionJournalError, match="JOURNAL_OUTCOME_UNAVAILABLE"):
        execute(journal(setup), setup)


@pytest.mark.parametrize("change", ["late_capture", "dropped", "future", "binding", "coverage"])
def test_unproven_producer_completion_cannot_be_sealed_successfully(setup, change):
    class Invalid(Producer):
        def start_capture(self, binding):
            result = super().start_capture(binding)
            return replace(result, started_at_ms=111) if change == "late_capture" else result

        def execute(self, *args):
            context, proof = super().execute(*args)
            if change == "dropped":
                proof = replace(proof, dropped_events=1)
            elif change == "future":
                context = replace(context, observed_at_ms=121)
                proof = replace(proof, context_sha256=context.sha256)
            elif change == "binding":
                context = replace(context, request_sha256="9" * 64)
                proof = replace(proof, context_sha256=context.sha256)
            elif change == "coverage":
                proof = replace(proof, coverage_from_ms=110)
            return context, proof

    with pytest.raises(ExecutionJournalError, match="JOURNAL_EXECUTION_FAILED"):
        execute(journal(setup, Invalid(setup)), setup)
    with setup[0]() as db:
        assert db.get(BackgroundJob, setup[2]).status == "failed"


def test_crash_recovery_does_not_redispatch_or_accept_unknown_outcome(setup):
    class Crashing(Producer):
        def execute(self, *args):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        execute(journal(setup, Crashing(setup)), setup)
    with pytest.raises(ExecutionJournalError, match="JOURNAL_NOT_EXPIRED"):
        journal(setup).interrupt_expired(run_id=setup[2], owner_id=setup[3], minimum_age_ms=100)
    setup[1][0] = 300
    journal(setup).interrupt_expired(run_id=setup[2], owner_id=setup[3], minimum_age_ms=100)
    with pytest.raises(ExecutionJournalError, match="JOURNAL_OUTCOME_UNAVAILABLE"):
        execute(journal(setup), setup)
    with setup[0]() as db:
        assert db.get(BackgroundJob, setup[2]).status == "interrupted"


@pytest.mark.parametrize("interrupt", [False, True])
def test_concurrent_duplicate_and_late_terminal_cannot_redispatch(setup, interrupt):
    entered, release = Event(), Event()
    outcomes = []

    class Waiting(Producer):
        def execute(self, *args):
            result = super().execute(*args)
            entered.set()
            assert release.wait(5)
            return result

    producer = Waiting(setup)

    def first():
        try:
            outcomes.append(execute(journal(setup, producer), setup))
        except ExecutionJournalError as exc:
            outcomes.append(exc.code)

    thread = Thread(target=first)
    thread.start()
    try:
        assert entered.wait(5)
        with pytest.raises(ExecutionJournalError, match="JOURNAL_OUTCOME_UNAVAILABLE"):
            execute(journal(setup), setup)
        if interrupt:
            setup[1][0] = 300
            journal(setup).interrupt_expired(run_id=setup[2], owner_id=setup[3], minimum_age_ms=100)
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert producer.starts == producer.calls == 1
    if interrupt:
        assert outcomes == ["JOURNAL_EXECUTION_FAILED"]
    else:
        assert len(outcomes) == 1 and isinstance(outcomes[0], ExecutionCompletionEvidence)
    with setup[0]() as db:
        row = db.get(BackgroundJob, setup[2])
        assert row.status == ("interrupted" if interrupt else "complete")


@pytest.mark.parametrize("mac", ["private-detail", "\u00e9" * 64, None, 123])
def test_invalid_stored_mac_returns_safe_error(setup, mac):
    producer = Producer(setup)
    execute(journal(setup, producer), setup)
    with setup[0]() as db, db.begin():
        row = db.get(BackgroundJob, setup[2])
        row.result = {**row.result, "mac": mac}
    with pytest.raises(ExecutionJournalError, match="JOURNAL_RECORD_INVALID"):
        journal(setup).verify(run_id=setup[2], owner_id=setup[3], context=producer.context)


@pytest.mark.parametrize("operation", ["execute", "verify", "interrupt"])
def test_unavailable_storage_is_sanitized_before_producer_dispatch(setup, operation):
    from sqlalchemy.exc import OperationalError

    producer = Producer(setup)

    def unavailable():
        raise OperationalError("private-database-address", {}, Exception("private-key"))

    service = ExecutionJournal(
        sessions=unavailable,
        producer=producer,
        authentication_key=KEY,
        producer_id="synthetic-producer",
        clock_ms=lambda: 100,
    )
    with pytest.raises(ExecutionJournalError) as error:
        if operation == "execute":
            execute(service, setup)
        elif operation == "verify":
            service.verify(run_id=setup[2], owner_id=setup[3], context=None)
        else:
            service.interrupt_expired(run_id=setup[2], owner_id=setup[3], minimum_age_ms=1)
    assert str(error.value) == "JOURNAL_STORAGE_UNAVAILABLE"
    assert producer.starts == producer.calls == 0
