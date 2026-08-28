from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from typing import Any, cast

import pytest
from fastapi import FastAPI
from starlette.types import Message, Scope

from classifire.config import Settings
from classifire.upload_ingress import (
    TECHNICAL_UPLOAD_MULTIPART_OVERHEAD_BYTES,
    TechnicalUploadBodyLimitMiddleware,
    technical_upload_middleware_maximum_body_bytes,
)


def _request(
    *,
    path: str = "/technical/upload",
    root_path: str = "",
    method: str = "POST",
    headers: Iterable[tuple[bytes, bytes]] = (),
    messages: Iterable[Message] = (),
    maximum: int = 8,
) -> tuple[list[Message], bool, int]:
    output: list[Message] = []
    pending = list(messages) or [
        {"type": "http.request", "body": b"", "more_body": False}
    ]
    downstream_called = False
    receive_calls = 0

    async def downstream(scope: Scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        nonlocal downstream_called
        downstream_called = True
        while True:
            message = await receive()
            if message["type"] != "http.request" or not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive() -> Message:
        nonlocal receive_calls
        receive_calls += 1
        if pending:
            return pending.pop(0)
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        output.append(message)

    scope = cast(
        Scope,
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "root_path": root_path,
            "headers": list(headers),
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 443),
        },
    )
    middleware = TechnicalUploadBodyLimitMiddleware(
        downstream,
        maximum_body_bytes=maximum,
    )
    asyncio.run(middleware(scope, receive, send))
    return output, downstream_called, receive_calls


def _response(output: list[Message]) -> tuple[int, dict[str, Any]]:
    start = next(message for message in output if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"")
        for message in output
        if message["type"] == "http.response.body"
    )
    return int(start["status"]), json.loads(body) if body else {}


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (
            "/technical/upload",
            {
                "ok": False,
                "code": "UPLOAD_CONTENT_LENGTH_REQUIRED",
                "retryable": False,
                "fatal": True,
            },
        ),
        (
            "/api/v1/technical/documents",
            {"detail": "UPLOAD_CONTENT_LENGTH_REQUIRED"},
        ),
    ],
)
def test_missing_content_length_is_rejected_before_route_or_body_read(
    path: str,
    expected: dict[str, Any],
) -> None:
    output, downstream_called, receive_calls = _request(path=path)

    assert _response(output) == (411, expected)
    assert downstream_called is False
    assert receive_calls == 0


@pytest.mark.parametrize(
    "headers",
    [
        [(b"content-length", b"")],
        [(b"content-length", b"-1")],
        [(b"content-length", b"+1")],
        [(b"content-length", b"1.0")],
        [(b"content-length", b" 1")],
        [(b"content-length", b"9x")],
        [(b"content-length", b"1"), (b"content-length", b"1")],
    ],
)
def test_invalid_content_length_is_rejected_before_route_or_body_read(
    headers: list[tuple[bytes, bytes]],
) -> None:
    output, downstream_called, receive_calls = _request(headers=headers)

    assert _response(output)[0] == 400
    assert _response(output)[1]["code"] == "UPLOAD_CONTENT_LENGTH_INVALID"
    assert downstream_called is False
    assert receive_calls == 0


def test_declared_oversize_is_rejected_before_route_or_body_read() -> None:
    output, downstream_called, receive_calls = _request(
        headers=[(b"content-length", b"9")],
        maximum=8,
    )

    assert _response(output)[0] == 413
    assert _response(output)[1]["code"] == "UPLOAD_SIZE_LIMIT_EXCEEDED"
    assert downstream_called is False
    assert receive_calls == 0


@pytest.mark.parametrize(
    ("path", "root_path", "expected_payload"),
    [
        (
            "/prefix/technical/upload",
            "/prefix",
            {
                "ok": False,
                "code": "UPLOAD_SIZE_LIMIT_EXCEEDED",
                "retryable": False,
                "fatal": True,
            },
        ),
        (
            "/prefix/api/v1/technical/documents",
            "/prefix",
            {"detail": "UPLOAD_SIZE_LIMIT_EXCEEDED"},
        ),
    ],
)
def test_root_path_prefixed_uploads_are_limited_with_correct_response_shape(
    path: str,
    root_path: str,
    expected_payload: dict[str, Any],
) -> None:
    output, downstream_called, receive_calls = _request(
        path=path,
        root_path=root_path,
        headers=[(b"content-length", b"9")],
        maximum=8,
    )

    assert _response(output) == (413, expected_payload)
    assert downstream_called is False
    assert receive_calls == 0


def test_root_path_prefixed_valid_upload_reaches_route() -> None:
    output, downstream_called, receive_calls = _request(
        path="/prefix/technical/upload",
        root_path="/prefix",
        headers=[(b"content-length", b"5")],
        messages=[
            {"type": "http.request", "body": b"ab", "more_body": True},
            {"type": "http.request", "body": b"cde", "more_body": False},
        ],
    )

    assert _response(output)[0] == 204
    assert downstream_called is True
    assert receive_calls == 2


@pytest.mark.parametrize(
    ("path", "root_path"),
    [
        ("/prefixish/technical/upload", "/prefix"),
        ("/prefix/technical/upload", "/pre"),
        ("/prefix/technical/upload", "/prefixish"),
    ],
)
def test_root_path_lookalikes_are_not_misclassified(
    path: str,
    root_path: str,
) -> None:
    output, downstream_called, receive_calls = _request(
        path=path,
        root_path=root_path,
    )

    assert _response(output)[0] == 204
    assert downstream_called is True
    assert receive_calls == 1


def test_exact_declared_body_is_streamed_to_the_route() -> None:
    output, downstream_called, receive_calls = _request(
        headers=[(b"Content-Length", b"5")],
        messages=[
            {"type": "http.request", "body": b"ab", "more_body": True},
            {"type": "http.request", "body": b"cde", "more_body": False},
        ],
    )

    assert _response(output)[0] == 204
    assert downstream_called is True
    assert receive_calls == 2


def test_actual_body_larger_than_declared_is_rejected_during_streaming() -> None:
    output, downstream_called, _receive_calls = _request(
        headers=[(b"content-length", b"4")],
        messages=[
            {"type": "http.request", "body": b"abc", "more_body": True},
            {"type": "http.request", "body": b"de", "more_body": False},
        ],
    )

    assert _response(output)[0] == 400
    assert _response(output)[1]["code"] == "UPLOAD_CONTENT_LENGTH_INVALID"
    assert downstream_called is True


@pytest.mark.parametrize(
    ("content_length_headers", "expected_status", "expected_code"),
    [
        ([], 411, "UPLOAD_CONTENT_LENGTH_REQUIRED"),
        (
            [(b"content-length", b"1"), (b"content-length", b"1")],
            400,
            "UPLOAD_CONTENT_LENGTH_INVALID",
        ),
        (
            [(b"content-length", b"invalid")],
            400,
            "UPLOAD_CONTENT_LENGTH_INVALID",
        ),
        (
            [(b"content-length", b"9")],
            413,
            "UPLOAD_SIZE_LIMIT_EXCEEDED",
        ),
    ],
)
def test_api_batch_ingress_rejections_use_structured_contract_before_route(
    content_length_headers: list[tuple[bytes, bytes]],
    expected_status: int,
    expected_code: str,
) -> None:
    output, downstream_called, receive_calls = _request(
        path="/api/v1/technical/documents",
        headers=[
            (
                b"x-classifire-intake-batch-id",
                b"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            ),
            *content_length_headers,
        ],
        maximum=8,
    )

    assert _response(output) == (
        expected_status,
        {
            "ok": False,
            "code": expected_code,
            "retryable": False,
            "fatal": True,
        },
    )
    assert downstream_called is False
    assert receive_calls == 0


def test_api_batch_stream_mismatch_uses_structured_contract() -> None:
    output, downstream_called, _receive_calls = _request(
        path="/api/v1/technical/documents",
        headers=[
            (
                b"x-classifire-intake-item-id",
                b"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            ),
            (b"content-length", b"4"),
        ],
        messages=[
            {"type": "http.request", "body": b"abc", "more_body": True},
            {"type": "http.request", "body": b"de", "more_body": False},
        ],
    )

    assert _response(output) == (
        400,
        {
            "ok": False,
            "code": "UPLOAD_CONTENT_LENGTH_INVALID",
            "retryable": False,
            "fatal": True,
        },
    )
    assert downstream_called is True


def test_actual_body_over_limit_is_rejected_during_streaming() -> None:
    output, downstream_called, _receive_calls = _request(
        headers=[(b"content-length", b"8")],
        messages=[
            {"type": "http.request", "body": b"abcdefgh", "more_body": True},
            {"type": "http.request", "body": b"i", "more_body": False},
        ],
    )

    assert _response(output)[0] == 413
    assert _response(output)[1]["code"] == "UPLOAD_SIZE_LIMIT_EXCEEDED"
    assert downstream_called is True


def test_truncated_body_is_rejected_during_streaming() -> None:
    output, downstream_called, _receive_calls = _request(
        headers=[(b"content-length", b"5")],
        messages=[{"type": "http.request", "body": b"abcd", "more_body": False}],
    )

    assert _response(output)[0] == 400
    assert _response(output)[1]["code"] == "UPLOAD_CONTENT_LENGTH_INVALID"
    assert downstream_called is True


@pytest.mark.parametrize(
    ("path", "method"),
    [("/api/v1/projects", "POST"), ("/technical/upload", "GET")],
)
def test_non_target_requests_are_unchanged(path: str, method: str) -> None:
    output, downstream_called, receive_calls = _request(path=path, method=method)

    assert _response(output)[0] == 204
    assert downstream_called is True
    assert receive_calls == 1


def test_main_installs_limit_with_file_allowance_and_bounded_multipart_overhead() -> None:
    from classifire.main import app, settings

    registration = next(
        item
        for item in app.user_middleware
        if item.cls is TechnicalUploadBodyLimitMiddleware
    )

    assert registration.kwargs["maximum_body_bytes"] == (
        settings.upload_ingress_ceiling_bytes
        + TECHNICAL_UPLOAD_MULTIPART_OVERHEAD_BYTES
    )


def test_invalid_negative_ingress_ceiling_still_constructs_fail_closed_app(
    tmp_path,
) -> None:
    settings = Settings(
        _env_file=None,
        env="production",
        storage_root=tmp_path,
        upload_ingress_ceiling_mb=-1,
    )
    maximum = technical_upload_middleware_maximum_body_bytes(
        settings.upload_ingress_ceiling_bytes
    )
    app = FastAPI()
    app.add_middleware(
        TechnicalUploadBodyLimitMiddleware,
        maximum_body_bytes=maximum,
    )

    assert maximum == 1
    assert app.build_middleware_stack() is not None


def test_main_cors_allows_immutable_batch_routing_headers() -> None:
    from starlette.middleware.cors import CORSMiddleware

    from classifire.main import app

    registration = next(
        item for item in app.user_middleware if item.cls is CORSMiddleware
    )

    assert {
        "X-Classifire-Intake-Batch-ID",
        "X-Classifire-Intake-Item-ID",
    }.issubset(set(registration.kwargs["allow_headers"]))
