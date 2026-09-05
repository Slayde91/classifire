from __future__ import annotations

import hashlib
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
import test_phase8_openresponses_transport as visual
import test_phase8_report_openresponses_transport as report
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from classifire.models import BackgroundJob
from classifire.services.execution_journal import (
    CaptureStart,
    ExecutionJournal,
    JournalCompletionLifecycle,
)
from classifire.services.phase8_openresponses_transport import Phase8OpenResponsesTransportError

NOW = 1234567890


@pytest.fixture
def sessions(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "lifecycle.db"))
    BackgroundJob.__table__.create(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.mark.parametrize("kind", ["visual", "report"])
@pytest.mark.parametrize(
    "mode",
    [
        "valid",
        "capture_failure",
        "token_failure",
        "http_failure",
        "bad_response",
        "lost_capture",
        "verifier_failure",
        "interrupted",
        "duplicate_begin",
        "tool_action",
    ],
)
def test_journal_transport_lifecycle(tmp_path, sessions, kind, mode):
    run_id, owner_id = str(uuid4()), str(uuid4())
    clock = [NOW]
    calls = {"capture": 0, "token": 0, "http": 0, "verify": 0}
    contexts = []

    class Producer:
        def start_capture(self, binding):
            calls["capture"] += 1
            with sessions() as db:
                row = db.get(BackgroundJob, run_id)
                assert row.status == "preparing"
                assert row.payload["binding"]["request_body_sha256"] == binding.request_body_sha256
            if mode == "capture_failure":
                raise RuntimeError("private-capture-detail")
            return CaptureStart("E" * 64, NOW)

        def execute(self, *args):
            raise AssertionError("Transport execution must not recurse into producer execution")

    def verified_capture(binding, capture, context):
        calls["verify"] += 1
        contexts.append(context)
        with sessions() as db:
            assert db.get(BackgroundJob, run_id).status == "running"
        assert capture.receipt_sha256 == "E" * 64
        assert context.request_body_sha256 == binding.request_body_sha256
        if mode == "verifier_failure":
            raise RuntimeError("private-capture-detail")
        evidence = visual._fake_completion(context)
        return replace(evidence, dropped_events=1) if mode == "lost_capture" else evidence

    journal = ExecutionJournal(
        sessions=sessions,
        producer=Producer(),
        completion_verifier=verified_capture,
        authentication_key=b"synthetic-lifecycle-key-not-production",
        producer_id="synthetic-capture",
        clock_ms=lambda: clock[0],
    )
    lifecycle = JournalCompletionLifecycle(journal, run_id=run_id, owner_id=owner_id)

    def token():
        calls["token"] += 1
        with sessions() as db:
            assert db.get(BackgroundJob, run_id).status == "running"
        if mode == "token_failure":
            raise RuntimeError("private-token-detail")
        return "synthetic-token"

    def handler(request):
        calls["http"] += 1
        with sessions() as db:
            row = db.get(BackgroundJob, run_id)
            assert row.status == "running"
            assert row.result["data"]["capture"]["receipt_sha256"] == "E" * 64
            assert row.payload["binding"]["request_body_sha256"] == (
                hashlib.sha256(request.content).hexdigest().upper()
            )
        if mode == "duplicate_begin":
            with pytest.raises(Phase8OpenResponsesTransportError):
                invoke()
            with sessions() as db:
                assert db.get(BackgroundJob, run_id).status == "running"
        if mode == "interrupted":
            clock[0] += 10
            journal.interrupt_expired(run_id=run_id, owner_id=owner_id, minimum_age_ms=1)
        if mode == "http_failure":
            raise httpx.ReadTimeout("private-http-detail")
        if mode == "bad_response":
            return httpx.Response(200, content=b"not-json")
        response = (
            visual._openresponses({"accepted": True})
            if kind == "visual"
            else report._completed_response({"accepted": True})
        )
        return httpx.Response(200, json=response)

    if kind == "visual":
        packet = visual._packet(tmp_path)
        transport, guard = visual._transport(
            packet,
            handler,
            token_provider=token,
            completion_verifier=None,
            completion_lifecycle=lifecycle,
        )
        kwargs = dict(role="cf-validator", stage="blind_inventory", request=visual._request(packet))
    else:
        runtime, _ = report._runtime(tmp_path)
        request = report._request(runtime)
        transport, guard = report._transport(
            runtime,
            handler,
            token_provider=token,
            completion_verifier=None,
            completion_lifecycle=lifecycle,
        )
        kwargs = dict(
            role="cf-validator",
            stage="blind_inventory",
            request=request,
            rendered_prompt=report._render(runtime, request),
            runtime_input=runtime,
            report_assessment_inference_profile=report._report_profile(),
        )
    if mode == "tool_action":
        guard.audit_tools = ("synthetic-tool",)

    def invoke():
        return transport.invoke(**kwargs)

    if mode in {"valid", "duplicate_begin"}:
        result = invoke()
        assert result["payload"] == {"accepted": True}
        with sessions() as db:
            row = db.get(BackgroundJob, run_id)
            assert row.status == "complete"
            assert row.record_version == 3
        evidence = journal.verify(run_id=run_id, owner_id=owner_id, context=contexts[0])
        assert journal.complete(run_id=run_id, owner_id=owner_id, context=contexts[0]) == evidence
        with pytest.raises(Phase8OpenResponsesTransportError):
            invoke()
        assert calls == {"capture": 1, "token": 1, "http": 1, "verify": 1}
        with sessions() as db:
            assert db.get(BackgroundJob, run_id).status == "complete"
    else:
        with pytest.raises(Phase8OpenResponsesTransportError) as error:
            invoke()
        assert "private" not in str(error.value)
        with sessions() as db:
            row = db.get(BackgroundJob, run_id)
            assert row.status == ("interrupted" if mode == "interrupted" else "failed")
        assert calls["capture"] == 1
        if mode == "capture_failure":
            assert calls["token"] == calls["http"] == calls["verify"] == 0
        elif mode == "token_failure":
            assert calls["http"] == calls["verify"] == 0
        elif mode in {"http_failure", "bad_response", "tool_action", "interrupted"}:
            assert calls["http"] == 1 and calls["verify"] == 0
        else:
            assert calls["verify"] == 1


def test_conflicting_verifier_and_lifecycle_are_refused(tmp_path):
    class Lifecycle:
        def begin(self, binding):
            raise AssertionError

        def complete(self, context):
            raise AssertionError

        def abort(self):
            raise AssertionError

    with pytest.raises(Phase8OpenResponsesTransportError, match="COMPLETION_EVIDENCE_INVALID"):
        visual._transport(
            visual._packet(tmp_path),
            lambda request: httpx.Response(200),
            completion_lifecycle=Lifecycle(),
        )


@pytest.mark.parametrize("mode", ["begin_failure", "future_start", "abort_failure"])
def test_lifecycle_cleanup_preserves_safe_failure(tmp_path, caplog, mode):
    calls = {"abort": 0, "http": 0}

    class Lifecycle:
        def begin(self, binding):
            if mode == "begin_failure":
                raise RuntimeError("private-begin-detail")
            return NOW + 1 if mode == "future_start" else NOW

        def complete(self, context):
            raise AssertionError("Failed HTTP must not complete")

        def abort(self):
            calls["abort"] += 1
            if mode == "abort_failure":
                raise RuntimeError("private-abort-detail")

    def handler(request):
        calls["http"] += 1
        raise httpx.ReadTimeout("private-http-detail")

    transport, _ = visual._transport(
        visual._packet(tmp_path),
        handler,
        completion_verifier=None,
        completion_lifecycle=Lifecycle(),
    )
    with pytest.raises(Phase8OpenResponsesTransportError) as error:
        transport.invoke(
            role="cf-validator",
            stage="blind_inventory",
            request=visual._request(transport._packet),
        )
    assert error.value.code == (
        "GATEWAY_TIMEOUT" if mode == "abort_failure" else "COMPLETION_EVIDENCE_UNAVAILABLE"
    )
    assert calls["abort"] == (0 if mode == "begin_failure" else 1)
    assert calls["http"] == (1 if mode == "abort_failure" else 0)
    assert "private" not in str(error.value) + caplog.text
