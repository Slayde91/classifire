"""Pre-multipart request limits for governed technical-evidence uploads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

TECHNICAL_UPLOAD_PATHS = frozenset(
    {
        "/api/v1/technical/documents",
        "/technical/upload",
    }
)
TECHNICAL_UPLOAD_MULTIPART_OVERHEAD_BYTES = 1024 * 1024
TECHNICAL_UPLOAD_MAX_TEXT_PART_BYTES = 128 * 1024


def technical_upload_middleware_maximum_body_bytes(
    upload_ingress_ceiling_bytes: int,
) -> int:
    """Build a positive fail-closed middleware limit before readiness runs."""

    if (
        not isinstance(upload_ingress_ceiling_bytes, int)
        or isinstance(upload_ingress_ceiling_bytes, bool)
        or upload_ingress_ceiling_bytes <= 0
    ):
        return 1
    return upload_ingress_ceiling_bytes + TECHNICAL_UPLOAD_MULTIPART_OVERHEAD_BYTES


@dataclass(frozen=True, slots=True)
class _IngressRejection(Exception):
    status_code: int
    code: str


def _declared_content_length(scope: Scope, maximum_body_bytes: int) -> int:
    values = [
        value
        for name, value in scope.get("headers", ())
        if name.lower() == b"content-length"
    ]
    if not values:
        raise _IngressRejection(411, "UPLOAD_CONTENT_LENGTH_REQUIRED")
    if len(values) != 1 or not values[0]:
        raise _IngressRejection(400, "UPLOAD_CONTENT_LENGTH_INVALID")

    if any(character < ord("0") or character > ord("9") for character in values[0]):
        raise _IngressRejection(400, "UPLOAD_CONTENT_LENGTH_INVALID")

    declared = 0
    for character in values[0]:
        declared = declared * 10 + character - ord("0")
        if declared > maximum_body_bytes:
            raise _IngressRejection(413, "UPLOAD_SIZE_LIMIT_EXCEEDED")
    return declared


def _has_batch_routing_header(scope: Scope) -> bool:
    routing_headers = {
        b"x-classifire-intake-batch-id",
        b"x-classifire-intake-item-id",
    }
    return any(
        name.lower() in routing_headers
        for name, _value in scope.get("headers", ())
    )


def _rejection_payload(
    path: str,
    code: str,
    *,
    batch_request: bool,
) -> dict[str, Any]:
    if path == "/technical/upload" or (
        path == "/api/v1/technical/documents" and batch_request
    ):
        return {
            "ok": False,
            "code": code,
            "retryable": False,
            "fatal": True,
        }
    return {"detail": code}


def _technical_upload_route_path(scope: Scope) -> str:
    """Return the routed path without trusting lookalike root-path prefixes."""

    raw_path = scope.get("path")
    path = raw_path if isinstance(raw_path, str) else ""
    raw_root_path = scope.get("root_path")
    root_path = raw_root_path if isinstance(raw_root_path, str) else ""
    root_prefix = root_path.rstrip("/")
    if (
        root_prefix
        and root_prefix.startswith("/")
        and root_prefix != "/"
        and (
            path == root_prefix
            or path.startswith(f"{root_prefix}/")
        )
    ):
        return path[len(root_prefix) :] or "/"
    return path


class TechnicalUploadBodyLimitMiddleware:
    """Reject unsafe technical-upload lengths before multipart parsing starts."""

    def __init__(self, app: ASGIApp, *, maximum_body_bytes: int) -> None:
        if (
            not isinstance(maximum_body_bytes, int)
            or isinstance(maximum_body_bytes, bool)
            or maximum_body_bytes <= 0
        ):
            raise ValueError("maximum_body_bytes must be a positive integer")
        self.app = app
        self.maximum_body_bytes = maximum_body_bytes

    async def _reject(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        error: _IngressRejection,
    ) -> None:
        path = _technical_upload_route_path(scope)
        response = JSONResponse(
            status_code=error.status_code,
            content=_rejection_payload(
                path,
                error.code,
                batch_request=_has_batch_routing_header(scope),
            ),
        )
        await response(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = _technical_upload_route_path(scope)
        if (
            scope.get("type") != "http"
            or scope.get("method") != "POST"
            or path not in TECHNICAL_UPLOAD_PATHS
        ):
            await self.app(scope, receive, send)
            return

        try:
            declared_length = _declared_content_length(scope, self.maximum_body_bytes)
        except _IngressRejection as error:
            await self._reject(scope, receive, send, error)
            return

        received_length = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received_length
            message = await receive()
            if message["type"] == "http.disconnect":
                raise _IngressRejection(400, "UPLOAD_CONTENT_LENGTH_INVALID")
            if message["type"] != "http.request":
                return message
            body = message.get("body", b"")
            more_body = message.get("more_body", False)
            if not isinstance(body, bytes) or not isinstance(more_body, bool):
                raise _IngressRejection(400, "UPLOAD_CONTENT_LENGTH_INVALID")
            received_length += len(body)
            if received_length > self.maximum_body_bytes:
                raise _IngressRejection(413, "UPLOAD_SIZE_LIMIT_EXCEEDED")
            if received_length > declared_length:
                raise _IngressRejection(400, "UPLOAD_CONTENT_LENGTH_INVALID")
            if not more_body and received_length != declared_length:
                raise _IngressRejection(400, "UPLOAD_CONTENT_LENGTH_INVALID")
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except _IngressRejection as error:
            if response_started:
                raise
            await self._reject(scope, receive, send, error)


__all__ = [
    "TECHNICAL_UPLOAD_MAX_TEXT_PART_BYTES",
    "TECHNICAL_UPLOAD_MULTIPART_OVERHEAD_BYTES",
    "TECHNICAL_UPLOAD_PATHS",
    "TechnicalUploadBodyLimitMiddleware",
    "technical_upload_middleware_maximum_body_bytes",
]
