from __future__ import annotations

import base64
import hashlib
import json
import traceback
from copy import deepcopy
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from test_draft_pdf_suggestion_contract import PAGE_PNG, PAGE_TEXT, output, request

from classifire.config import Settings
from classifire.services import draft_pdf_suggestion_transport as transport_module
from classifire.services.draft_pdf_suggestion_contract import SuggestionError
from classifire.services.draft_pdf_suggestion_transport import (
    ENDPOINT,
    MAX_RESPONSE_BYTES,
    OpenAIDraftPdfSuggestionPort,
    configured_port,
)


def response() -> dict[str, Any]:
    return dict(
        status="completed",
        model="configured-model-2026-09-01",
        error=None,
        incomplete_details=None,
        output=[
            dict(
                type="message",
                role="assistant",
                status="completed",
                content=[dict(type="output_text", text=json.dumps(output()))],
            )
        ],
    )


def _port(handler: Any) -> OpenAIDraftPdfSuggestionPort:
    return OpenAIDraftPdfSuggestionPort(
        model="configured-model",
        api_key=SecretStr("synthetic-key"),
        transport=httpx.MockTransport(handler),
    )


def test_request_is_one_page_only_and_result_hashes_exact_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    raw = json.dumps(response(), indent=2).encode()
    client_options = []
    actual_client = httpx.Client

    def client(**kwargs: Any) -> httpx.Client:
        client_options.append(kwargs.copy())
        return actual_client(**kwargs)

    monkeypatch.setattr(transport_module.httpx, "Client", client)

    def handle(incoming: httpx.Request) -> httpx.Response:
        calls.append(incoming)
        assert str(incoming.url) == ENDPOINT
        assert incoming.method == "POST"
        assert incoming.headers["authorization"] == "Bearer synthetic-key"
        assert incoming.headers["accept-encoding"] == "identity"
        body = json.loads(incoming.content)
        assert body["model"] == "configured-model"
        assert body["store"] is False and body["stream"] is False
        assert body["tools"] == [] and body["tool_choice"] == "none"
        assert body["text"]["format"]["type"] == "json_schema"
        assert body["text"]["format"]["strict"] is True
        assert body["input"] == [
            dict(
                role="user",
                content=[
                    dict(type="input_text", text=PAGE_TEXT),
                    dict(
                        type="input_image",
                        image_url="data:image/png;base64," + base64.b64encode(PAGE_PNG).decode(),
                    ),
                ],
            )
        ]
        assert request().input_sha256.encode() not in incoming.content
        assert "previous_response_id" not in body
        return httpx.Response(
            200, stream=_Chunks([raw]), headers={"content-type": "application/json"}
        )

    result = _port(handle).complete(request())
    assert len(calls) == 1
    assert result.provider == "openai"
    assert result.model == "configured-model-2026-09-01"
    assert result.response_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.output == output()
    assert client_options[0]["trust_env"] is False
    assert client_options[0]["follow_redirects"] is False
    assert client_options[0]["verify"] is True
    assert client_options[0]["timeout"].as_dict() == dict(
        connect=5.0, read=60.0, write=5.0, pool=5.0
    )


@pytest.mark.parametrize(
    "kind",
    [
        "incomplete",
        "error",
        "refusal",
        "tool",
        "wrong_role",
        "two_texts",
        "no_text",
        "bad_json",
        "duplicate_inner",
        "duplicate_outer",
        "nan",
        "missing_model",
        "bad_quote",
        "unknown_field",
    ],
)
def test_unusable_output_is_rejected_without_retry_or_content_leak(kind: str) -> None:
    payload = response()
    content = payload["output"][0]["content"]
    if kind == "incomplete":
        payload["status"] = "incomplete"
    elif kind == "error":
        payload["error"] = {"message": "private provider detail"}
    elif kind == "refusal":
        content[:] = [dict(type="refusal", refusal="private provider detail")]
    elif kind == "tool":
        payload["output"].append(
            dict(type="function_call", name="write_scope", arguments="private provider detail")
        )
    elif kind == "wrong_role":
        payload["output"][0]["role"] = "user"
    elif kind == "two_texts":
        content.append(deepcopy(content[0]))
    elif kind == "no_text":
        content.clear()
    elif kind == "bad_json":
        content[0]["text"] = "private provider detail"
    elif kind == "duplicate_inner":
        content[0]["text"] = (
            '{"defects":[],"defects":[],"openings":[],"services":[],"observations":[]}'
        )
    elif kind == "nan":
        content[0]["text"] = '{"defects":NaN,"openings":[],"services":[],"observations":[]}'
    elif kind == "missing_model":
        del payload["model"]
    elif kind in {"bad_quote", "unknown_field"}:
        candidate = output()
        candidate["services"][0]["quote" if kind == "bad_quote" else "approval"] = (
            "private provider detail"
        )
        content[0]["text"] = json.dumps(candidate)
    raw = json.dumps(payload).encode()
    if kind == "duplicate_outer":
        raw = b'{"status":"completed",' + raw[1:]
    calls = []

    def handle(incoming: httpx.Request) -> httpx.Response:
        calls.append(incoming)
        return httpx.Response(
            200, stream=_Chunks([raw]), headers={"content-type": "application/json"}
        )

    with pytest.raises(SuggestionError, match="SUGGESTION_PROVIDER_RESPONSE_INVALID") as caught:
        _port(handle).complete(request())
    assert len(calls) == 1
    formatted = "".join(traceback.format_exception(caught.value))
    assert "private provider detail" not in formatted
    assert "synthetic-key" not in formatted


class _Chunks(httpx.SyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    def __iter__(self):
        yield from self.chunks


@pytest.mark.parametrize(
    "kind,code",
    [
        ("redirect", "STATUS_REJECTED"),
        ("bad_content_type", "RESPONSE_INVALID"),
        ("compressed", "RESPONSE_INVALID"),
        ("oversized", "RESPONSE_TOO_LARGE"),
        ("timeout", "TIMEOUT"),
        ("network", "REQUEST_FAILED"),
    ],
)
def test_network_boundaries_fail_closed(kind: str, code: str) -> None:
    calls = []

    def handle(incoming: httpx.Request) -> httpx.Response:
        calls.append(incoming)
        if kind == "timeout":
            raise httpx.ReadTimeout("private provider detail", request=incoming)
        if kind == "network":
            raise httpx.ConnectError("private provider detail", request=incoming)
        if kind == "redirect":
            return httpx.Response(307, headers={"location": "https://elsewhere.invalid"})
        headers = {
            "content-type": "text/html" if kind == "bad_content_type" else "application/json"
        }
        if kind == "compressed":
            headers["content-encoding"] = "gzip"
        chunks = [b"x" * 8192] * 33 if kind == "oversized" else [json.dumps(response()).encode()]
        assert kind != "oversized" or sum(map(len, chunks)) > MAX_RESPONSE_BYTES
        return httpx.Response(200, headers=headers, stream=_Chunks(chunks))

    with pytest.raises(SuggestionError, match=f"SUGGESTION_PROVIDER_{code}") as caught:
        _port(handle).complete(request())
    assert len(calls) == 1
    assert "private provider detail" not in "".join(traceback.format_exception(caught.value))


def test_elapsed_response_budget_stops_reading(monkeypatch: pytest.MonkeyPatch) -> None:
    times = iter([0.0, 91.0])
    monkeypatch.setattr(transport_module.time, "monotonic", lambda: next(times))
    port = _port(
        lambda incoming: httpx.Response(
            200,
            stream=_Chunks([json.dumps(response()).encode()]),
            headers={"content-type": "application/json"},
        )
    )
    with pytest.raises(SuggestionError, match="SUGGESTION_PROVIDER_TIMEOUT"):
        port.complete(request())


@pytest.mark.parametrize(
    "model,key",
    [
        ("", "key"),
        ("https://example.invalid", "key"),
        ("model", ""),
        ("model", "two words"),
        ("model", "key\nvalue"),
    ],
)
def test_invalid_provider_configuration_is_rejected(model: str, key: str) -> None:
    with pytest.raises(SuggestionError, match="SUGGESTION_CONFIGURATION_INVALID"):
        OpenAIDraftPdfSuggestionPort(model=model, api_key=SecretStr(key))


def test_optional_configuration_is_disabled_by_default_and_secret_is_excluded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in ("ENABLED", "MODEL", "API_KEY"):
        monkeypatch.delenv("CLASSIFIRE_DRAFT_PDF_SUGGESTIONS_" + key, raising=False)
    settings = Settings(_env_file=None)
    assert configured_port(settings) is None
    settings.draft_pdf_suggestions_enabled = True
    with pytest.raises(SuggestionError, match="SUGGESTION_CONFIGURATION_INVALID"):
        configured_port(settings)
    settings.draft_pdf_suggestions_model = "configured-model"
    with pytest.raises(SuggestionError, match="SUGGESTION_CONFIGURATION_INVALID"):
        configured_port(settings)
    settings.draft_pdf_suggestions_api_key = SecretStr("synthetic-private-key")
    assert isinstance(configured_port(settings), OpenAIDraftPdfSuggestionPort)
    assert "draft_pdf_suggestions_api_key" not in settings.model_dump()
    assert "synthetic-private-key" not in repr(settings)


def test_tiny_trickling_chunks_are_checked_before_fixed_buffer_fills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 0.0}
    chunks_read = []
    monkeypatch.setattr(transport_module.time, "monotonic", lambda: clock["now"])

    class Trickle(httpx.SyncByteStream):
        def __iter__(self):
            for elapsed in (1.0, 30.0, 60.0, 91.0, 120.0):
                clock["now"] = elapsed
                chunks_read.append(elapsed)
                yield b"x"

    port = _port(
        lambda incoming: httpx.Response(
            200, stream=Trickle(), headers={"content-type": "application/json"}
        )
    )
    with pytest.raises(SuggestionError, match="SUGGESTION_PROVIDER_TIMEOUT"):
        port.complete(request())
    assert chunks_read == [1.0, 30.0, 60.0, 91.0]


def test_elapsed_budget_is_checked_when_empty_body_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 0.0}
    monkeypatch.setattr(transport_module.time, "monotonic", lambda: clock["now"])

    class Empty(httpx.SyncByteStream):
        def __iter__(self):
            clock["now"] = 91.0
            return iter(())

    port = _port(
        lambda incoming: httpx.Response(
            200, stream=Empty(), headers={"content-type": "application/json"}
        )
    )
    with pytest.raises(SuggestionError, match="SUGGESTION_PROVIDER_TIMEOUT"):
        port.complete(request())
