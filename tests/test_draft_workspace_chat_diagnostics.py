"""Offline failure diagnosis: one request, fixed metadata, no sensitive log content."""

import json
import logging
from uuid import UUID

import httpx
import pytest
from test_draft_workspace_chat import payload, response_body, settings

from classifire.services import draft_workspace_chat as chat
from classifire.services import draft_workspace_chat_transport as transport
from classifire.services.draft_scope import DraftScopeError

PRIVATE = "synthetic-private-question-reply-key-header-path"


def diagnostics(caplog):
    return [r for r in caplog.records if r.name == transport.__name__]


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        (httpx.ConnectTimeout, "connect_timeout"),
        (httpx.ReadTimeout, "read_timeout"),
        (httpx.WriteTimeout, "write_timeout"),
        (httpx.PoolTimeout, "pool_timeout"),
        (httpx.ConnectError, "connection_error"),
        (httpx.RemoteProtocolError, "http_error"),
        (OSError, "io_error"),
    ],
)
def test_network_failures_have_safe_categories_without_retry(caplog, failure, reason):
    calls = []

    def handler(request):
        calls.append(request)
        raise failure(PRIVATE)

    port = transport.OpenAIWorkspaceChatPort(settings(), transport=httpx.MockTransport(handler))
    with caplog.at_level(logging.WARNING), pytest.raises(DraftScopeError) as error:
        port.complete({"private": PRIVATE}, chat.parse(payload(question=PRIVATE)))
    assert str(error.value) == "CHAT_PROVIDER_FAILED" and error.value.__cause__ is None
    assert error.value.status_code == 502 and len(calls) == 1
    (record,) = diagnostics(caplog)
    request_id = calls[0].headers["X-Client-Request-Id"]
    assert str(UUID(request_id)) == request_id
    assert record.args[:3] == (reason, request_id, None)
    assert type(record.args[3]) is int and record.args[3] >= 0
    assert record.args[4] == 0
    assert record.exc_info is None and record.stack_info is None
    assert PRIVATE not in caplog.text and len(record.getMessage()) < 250


@pytest.mark.parametrize(
    ("kind", "reason"),
    [
        ("status", "http_status"),
        ("redirect", "http_status"),
        ("content_type", "content_type"),
        ("encoding", "content_encoding"),
        ("oversize", "response_too_large"),
        ("json", "invalid_json"),
        ("duplicate", "invalid_json"),
        ("incomplete", "incomplete_response"),
        ("tool", "unexpected_output"),
        ("refusal", "unexpected_content"),
        ("count", "output_count"),
        ("advice", "invalid_advice"),
    ],
)
def test_response_failure_stage_is_retained_but_untrusted_content_is_not(caplog, kind, reason):
    calls = []
    body = response_body()
    headers = {"Content-Type": "application/json", "x-request-id": PRIVATE, "Location": PRIVATE}
    status = 429 if kind == "status" else 302 if kind == "redirect" else 200
    if kind == "content_type":
        headers["Content-Type"] = PRIVATE
    if kind == "encoding":
        headers["Content-Encoding"] = PRIVATE
    if kind == "incomplete":
        body.update(status="incomplete", incomplete_details={"reason": PRIVATE})
    if kind == "tool":
        body["output"] = [{"type": "function_call", "arguments": PRIVATE}]
    if kind == "refusal":
        body["output"][0]["content"] = [{"type": "refusal", "refusal": PRIVATE}]
    if kind == "count":
        body["output"] = []
    if kind == "advice":
        body["output"][0]["content"][0]["text"] = json.dumps({"secret": PRIVATE})
    raw = json.dumps(body).encode()
    if kind == "oversize":
        raw = PRIVATE.encode() * 2000
    if kind == "json":
        raw = PRIVATE.encode()
    if kind == "duplicate":
        raw = b'{"status":"completed","status":"completed"}'

    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers=headers, stream=httpx.ByteStream(raw))

    port = transport.OpenAIWorkspaceChatPort(settings(), transport=httpx.MockTransport(handler))
    with caplog.at_level(logging.WARNING), pytest.raises(DraftScopeError) as error:
        port.complete({"private": PRIVATE}, chat.parse(payload(question=PRIVATE)))
    assert str(error.value) == "CHAT_PROVIDER_FAILED" and len(calls) == 1
    (record,) = diagnostics(caplog)
    assert record.args[:3] == (reason, calls[0].headers["X-Client-Request-Id"], status)
    assert 0 <= record.args[4] <= transport.MAX_RESPONSE_BYTES
    assert PRIVATE not in caplog.text and record.exc_info is None


def test_followup_failure_has_distinct_reference_and_does_not_log_conversation(caplog):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 2:
            raise httpx.ReadTimeout(PRIVATE)
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            stream=httpx.ByteStream(json.dumps(response_body()).encode()),
        )

    port = transport.OpenAIWorkspaceChatPort(settings(), transport=httpx.MockTransport(handler))
    first = chat.parse_workspace({"screen": {"name": "workspace"}, "question": PRIVATE})
    followup = chat.parse_workspace(
        {
            "screen": {"name": "workspace"},
            "question": "Summarise the unknowns.",
            "turns": [
                {"role": "user", "content": PRIVATE},
                {"role": "assistant", "content": PRIVATE},
            ],
        }
    )
    with caplog.at_level(logging.WARNING):
        assert port.complete({"quantity": None}, first)["uncertainty"]
        with pytest.raises(DraftScopeError, match="CHAT_PROVIDER_FAILED"):
            port.complete({"quantity": None}, followup)
    assert len(calls) == 2
    ids = [r.headers["X-Client-Request-Id"] for r in calls]
    assert ids[0] != ids[1]
    (record,) = diagnostics(caplog)
    assert record.args[:3] == ("read_timeout", ids[1], None)
    assert PRIVATE not in caplog.text
    for call in calls:
        assert call.extensions["timeout"] == {
            "connect": 5.0,
            "read": 30.0,
            "write": 5.0,
            "pool": 5.0,
        }
        body = json.loads(call.content)
        assert body["store"] is False and body["tools"] == [] and body["max_output_tokens"] == 5000


@pytest.mark.parametrize("kind", ["elapsed", "read_timeout"])
def test_partial_response_failures_close_stream_and_keep_only_byte_count(caplog, monkeypatch, kind):
    clock = [10.0]
    monkeypatch.setattr(transport, "time", type("Clock", (), {"monotonic": lambda: clock[0]}))
    calls = []
    closed = []

    class Partial(httpx.SyncByteStream):
        def __iter__(self):
            yield PRIVATE.encode()
            if kind == "read_timeout":
                raise httpx.ReadTimeout(PRIVATE)
            clock[0] = 56.0
            yield b"later"

        def close(self):
            closed.append(True)

    def handler(request):
        calls.append(request)
        return httpx.Response(200, headers={"Content-Type": "application/json"}, stream=Partial())

    port = transport.OpenAIWorkspaceChatPort(settings(), transport=httpx.MockTransport(handler))
    with (
        caplog.at_level(logging.WARNING),
        pytest.raises(DraftScopeError, match="CHAT_PROVIDER_FAILED"),
    ):
        port.complete({"private": PRIVATE}, chat.parse(payload()))
    (record,) = diagnostics(caplog)
    assert record.args[0] == ("elapsed_budget" if kind == "elapsed" else "read_timeout")
    assert record.args[2] == 200 and record.args[4] == len(PRIVATE.encode())
    assert closed == [True] and len(calls) == 1
    assert PRIVATE not in caplog.text
