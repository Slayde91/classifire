"""Managed local runtime composition for Phase 8 proposal-only inference.

The runtime intentionally exposes only five read/control Gateway RPC methods.
It owns a proxy-independent loopback HTTP client and obtains the Gateway token
only after the server-side no-tool attestation succeeds.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import socket
import subprocess
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import urlparse

import httpx

from .phase8_openresponses_transport import (
    GatewayRpc,
    OpenClawGatewayNoToolSessionGuard,
    Phase8OpenResponsesTransport,
)
from .phase8_visual_evidence import RetainedVisualEvidencePacket
from .phase8_visual_prompts import build_visual_inference_profile

_ALLOWED_RPC_METHODS = frozenset(
    {
        "sessions.create",
        "sessions.describe",
        "tools.effective",
        "audit.activity.list",
        "audit.list",
    }
)
_MAX_RPC_OUTPUT_BYTES = 1_000_000
_NO_WRITE_READINESS_SESSION_KEY = "classifire-phase8-readiness-no-write"
_MAX_WEBSOCKET_HANDSHAKE_BYTES = 16_384


class Phase8GatewayRpcError(RuntimeError):
    """A stable local Gateway RPC failure without command or response content."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Phase 8 Gateway RPC failed: {code}.")


class CommandRunner(Protocol):
    def __call__(
        self,
        args: Sequence[str],
        *,
        capture_output: bool,
        text: bool,
        timeout: float,
        check: bool,
    ) -> subprocess.CompletedProcess[str]: ...


class GatewaySocket(Protocol):
    def close(self) -> object: ...

    def recv(self, size: int) -> bytes: ...

    def sendall(self, data: bytes) -> object: ...

    def settimeout(self, value: float | None) -> object: ...


class GatewaySocketFactory(Protocol):
    def __call__(self, address: tuple[str, int], timeout: float) -> GatewaySocket: ...


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _reject_nonfinite(_value: str) -> None:
    raise ValueError("non-finite number")


def _parse_gateway_json(payload: str) -> dict[str, Any]:
    try:
        parsed = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        raise Phase8GatewayRpcError("RPC_OUTPUT_INVALID") from None
    if not isinstance(parsed, dict):
        raise Phase8GatewayRpcError("RPC_OUTPUT_INVALID")
    return parsed


def _validate_rpc_params(method: str, params: dict[str, Any]) -> None:
    if method not in _ALLOWED_RPC_METHODS or not isinstance(params, dict):
        raise Phase8GatewayRpcError("RPC_METHOD_FORBIDDEN")
    strings: Sequence[Any]
    if method == "sessions.create":
        if set(params) != {"key", "agentId", "model"}:
            raise Phase8GatewayRpcError("RPC_PARAMS_FORBIDDEN")
        strings = (params.get("key"), params.get("agentId"), params.get("model"))
    elif method == "sessions.describe":
        if set(params) != {"key"}:
            raise Phase8GatewayRpcError("RPC_PARAMS_FORBIDDEN")
        strings = (params.get("key"),)
    elif method == "tools.effective":
        if set(params) != {"sessionKey", "agentId"}:
            raise Phase8GatewayRpcError("RPC_PARAMS_FORBIDDEN")
        strings = (params.get("sessionKey"), params.get("agentId"))
    else:
        if (
            set(params) != {"sessionKey", "agentId", "kind", "after", "limit"}
            or params.get("kind") != "tool_action"
            or not isinstance(params.get("after"), int)
            or isinstance(params.get("after"), bool)
            or params["after"] < 0
            or not isinstance(params.get("limit"), int)
            or isinstance(params.get("limit"), bool)
            or not 1 <= params["limit"] <= 100
        ):
            raise Phase8GatewayRpcError("RPC_PARAMS_FORBIDDEN")
        strings = (params.get("sessionKey"), params.get("agentId"))
    if any(not isinstance(value, str) or not value.strip() for value in strings):
        raise Phase8GatewayRpcError("RPC_PARAMS_FORBIDDEN")


def _loopback_websocket_endpoint(base_url: str) -> tuple[str, int, str]:
    if not isinstance(base_url, str) or not base_url.strip():
        raise Phase8GatewayRpcError("LOOPBACK_GATEWAY_URL_INVALID")
    try:
        parsed = urlparse(base_url.strip())
        address = ipaddress.ip_address(parsed.hostname) if parsed.hostname else None
        port = parsed.port
    except ValueError:
        raise Phase8GatewayRpcError("LOOPBACK_GATEWAY_URL_INVALID") from None
    if (
        parsed.scheme != "http"
        or address is None
        or not address.is_loopback
        or parsed.username is not None
        or parsed.password is not None
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/", "/v1", "/v1/")
    ):
        raise Phase8GatewayRpcError("LOOPBACK_GATEWAY_URL_INVALID")
    host = str(address)
    effective_port = port or 80
    host_header = f"[{host}]" if address.version == 6 else host
    if effective_port != 80:
        host_header = f"{host_header}:{effective_port}"
    return host, effective_port, host_header


def validate_phase8_loopback_gateway_url(base_url: str) -> None:
    """Require a literal numeric loopback URL before any Gateway token can be sent."""

    _loopback_websocket_endpoint(base_url)


def _remaining_timeout(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise Phase8GatewayRpcError("RPC_UNAVAILABLE")
    return remaining


def _take_socket_bytes(
    gateway_socket: GatewaySocket,
    buffered: bytearray,
    size: int,
    deadline: float,
) -> bytes:
    while len(buffered) < size:
        gateway_socket.settimeout(_remaining_timeout(deadline))
        chunk = gateway_socket.recv(max(4_096, size - len(buffered)))
        if not chunk:
            raise Phase8GatewayRpcError("RPC_UNAVAILABLE")
        buffered.extend(chunk)
        if len(buffered) > _MAX_RPC_OUTPUT_BYTES + _MAX_WEBSOCKET_HANDSHAKE_BYTES:
            raise Phase8GatewayRpcError("RPC_OUTPUT_INVALID")
    result = bytes(buffered[:size])
    del buffered[:size]
    return result


def _send_websocket_frame(
    gateway_socket: GatewaySocket,
    *,
    opcode: int,
    payload: bytes,
    deadline: float,
) -> None:
    if len(payload) > _MAX_RPC_OUTPUT_BYTES:
        raise Phase8GatewayRpcError("RPC_OUTPUT_INVALID")
    header = bytearray((0x80 | opcode,))
    length = len(payload)
    if length < 126:
        header.append(0x80 | length)
    elif length <= 0xFFFF:
        header.append(0x80 | 126)
        header.extend(length.to_bytes(2, "big"))
    else:
        header.append(0x80 | 127)
        header.extend(length.to_bytes(8, "big"))
    mask = os.urandom(4)
    masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    gateway_socket.settimeout(_remaining_timeout(deadline))
    gateway_socket.sendall(bytes(header) + mask + masked)


def _read_websocket_text(
    gateway_socket: GatewaySocket,
    buffered: bytearray,
    deadline: float,
) -> str:
    while True:
        header = _take_socket_bytes(gateway_socket, buffered, 2, deadline)
        first, second = header
        if first & 0x70 or not first & 0x80 or second & 0x80:
            raise Phase8GatewayRpcError("RPC_OUTPUT_INVALID")
        opcode = first & 0x0F
        payload_length = second & 0x7F
        if payload_length == 126:
            payload_length = int.from_bytes(
                _take_socket_bytes(gateway_socket, buffered, 2, deadline), "big"
            )
        elif payload_length == 127:
            payload_length = int.from_bytes(
                _take_socket_bytes(gateway_socket, buffered, 8, deadline), "big"
            )
        if payload_length > _MAX_RPC_OUTPUT_BYTES:
            raise Phase8GatewayRpcError("RPC_OUTPUT_INVALID")
        payload = _take_socket_bytes(gateway_socket, buffered, payload_length, deadline)
        if opcode == 0x9:
            _send_websocket_frame(gateway_socket, opcode=0xA, payload=payload, deadline=deadline)
            continue
        if opcode == 0x8:
            raise Phase8GatewayRpcError("RPC_UNAVAILABLE")
        if opcode != 0x1:
            raise Phase8GatewayRpcError("RPC_OUTPUT_INVALID")
        try:
            return payload.decode("utf-8")
        except UnicodeDecodeError:
            raise Phase8GatewayRpcError("RPC_OUTPUT_INVALID") from None


class OpenClawLoopbackGatewayRpc:
    """Use only the local Gateway protocol when the installed CLI is unavailable."""

    def __init__(
        self,
        *,
        base_url: str,
        token_provider: Callable[[], str],
        timeout_seconds: float = 10.0,
        socket_factory: GatewaySocketFactory = socket.create_connection,
    ) -> None:
        if (
            not isinstance(timeout_seconds, (int, float))
            or isinstance(timeout_seconds, bool)
            or not 0 < timeout_seconds <= 60
        ):
            raise Phase8GatewayRpcError("LOOPBACK_GATEWAY_URL_INVALID")
        self._host, self._port, self._host_header = _loopback_websocket_endpoint(base_url)
        self._token_provider = token_provider
        self._timeout_seconds = float(timeout_seconds)
        self._socket_factory = socket_factory

    def __call__(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        _validate_rpc_params(method, params)
        try:
            token = self._token_provider()
        except Exception:
            raise Phase8GatewayRpcError("GATEWAY_TOKEN_UNAVAILABLE") from None
        if not isinstance(token, str) or not token.strip():
            raise Phase8GatewayRpcError("GATEWAY_TOKEN_UNAVAILABLE")
        deadline = time.monotonic() + self._timeout_seconds
        gateway_socket: GatewaySocket | None = None
        try:
            gateway_socket = self._socket_factory(
                (self._host, self._port), _remaining_timeout(deadline)
            )
            buffered = self._open_websocket(gateway_socket, deadline)
            return self._call_authenticated(
                gateway_socket,
                buffered,
                deadline,
                method=method,
                params=params,
                token=token,
            )
        except Phase8GatewayRpcError:
            raise
        except (OSError, UnicodeError, ValueError):
            raise Phase8GatewayRpcError("RPC_UNAVAILABLE") from None
        finally:
            if gateway_socket is not None:
                try:
                    gateway_socket.close()
                except OSError:
                    pass

    def _open_websocket(self, gateway_socket: GatewaySocket, deadline: float) -> bytearray:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            "GET / HTTP/1.1\r\n"
            f"Host: {self._host_header}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode("ascii")
        gateway_socket.settimeout(_remaining_timeout(deadline))
        gateway_socket.sendall(request)
        buffered = bytearray()
        while b"\r\n\r\n" not in buffered:
            gateway_socket.settimeout(_remaining_timeout(deadline))
            chunk = gateway_socket.recv(4_096)
            if not chunk:
                raise Phase8GatewayRpcError("RPC_UNAVAILABLE")
            buffered.extend(chunk)
            if len(buffered) > _MAX_WEBSOCKET_HANDSHAKE_BYTES:
                raise Phase8GatewayRpcError("RPC_UNAVAILABLE")
        raw_headers, remaining = bytes(buffered).split(b"\r\n\r\n", 1)
        try:
            lines = raw_headers.decode("ascii").split("\r\n")
        except UnicodeDecodeError:
            raise Phase8GatewayRpcError("RPC_UNAVAILABLE") from None
        if not lines or lines[0] != "HTTP/1.1 101 Switching Protocols":
            raise Phase8GatewayRpcError("RPC_UNAVAILABLE")
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if ":" not in line:
                raise Phase8GatewayRpcError("RPC_UNAVAILABLE")
            name, value = line.split(":", 1)
            normalized_name = name.strip().lower()
            if not normalized_name or normalized_name in headers:
                raise Phase8GatewayRpcError("RPC_UNAVAILABLE")
            headers[normalized_name] = value.strip()
        expected_accept = base64.b64encode(
            hashlib.sha1(  # noqa: S324 - RFC 6455 Sec-WebSocket-Accept requires SHA-1
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii"),
                usedforsecurity=False,
            ).digest()
        ).decode("ascii")
        if (
            headers.get("upgrade", "").lower() != "websocket"
            or "upgrade" not in headers.get("connection", "").lower()
            or headers.get("sec-websocket-accept") != expected_accept
        ):
            raise Phase8GatewayRpcError("RPC_UNAVAILABLE")
        return bytearray(remaining)

    def _call_authenticated(
        self,
        gateway_socket: GatewaySocket,
        buffered: bytearray,
        deadline: float,
        *,
        method: str,
        params: dict[str, Any],
        token: str,
    ) -> dict[str, Any]:
        connect_id = str(uuid.uuid4())
        request_id = str(uuid.uuid4())
        connect_sent = False
        request_sent = False
        scope = "operator.write" if method == "sessions.create" else "operator.read"
        for _ in range(8):
            frame = _parse_gateway_json(_read_websocket_text(gateway_socket, buffered, deadline))
            if frame.get("type") == "event" and frame.get("event") == "connect.challenge":
                payload = frame.get("payload")
                if (
                    connect_sent
                    or not isinstance(payload, dict)
                    or not isinstance(payload.get("nonce"), str)
                    or not payload["nonce"].strip()
                ):
                    raise Phase8GatewayRpcError("RPC_UNAVAILABLE")
                connect = {
                    "type": "req",
                    "id": connect_id,
                    "method": "connect",
                    "params": {
                        "minProtocol": 4,
                        "maxProtocol": 4,
                        "client": {
                            "id": "cli",
                            "version": "2026.7.1-2",
                            "platform": "win32",
                            "mode": "cli",
                            "instanceId": str(uuid.uuid4()),
                        },
                        "caps": [],
                        "auth": {"token": token},
                        "role": "operator",
                        "scopes": [scope],
                    },
                }
                _send_websocket_frame(
                    gateway_socket,
                    opcode=0x1,
                    payload=json.dumps(connect, allow_nan=False, separators=(",", ":")).encode(
                        "utf-8"
                    ),
                    deadline=deadline,
                )
                connect_sent = True
                continue
            if frame.get("type") != "res" or not isinstance(frame.get("id"), str):
                continue
            if frame["id"] == connect_id:
                if not connect_sent or frame.get("ok") is not True:
                    raise Phase8GatewayRpcError("RPC_REJECTED")
                if request_sent:
                    raise Phase8GatewayRpcError("RPC_OUTPUT_INVALID")
                request = {
                    "type": "req",
                    "id": request_id,
                    "method": method,
                    "params": params,
                }
                _send_websocket_frame(
                    gateway_socket,
                    opcode=0x1,
                    payload=json.dumps(request, allow_nan=False, separators=(",", ":")).encode(
                        "utf-8"
                    ),
                    deadline=deadline,
                )
                request_sent = True
                continue
            if frame["id"] == request_id:
                if not request_sent or frame.get("ok") is not True:
                    raise Phase8GatewayRpcError("RPC_REJECTED")
                result = frame.get("payload")
                if not isinstance(result, dict):
                    raise Phase8GatewayRpcError("RPC_OUTPUT_INVALID")
                return result
        raise Phase8GatewayRpcError("RPC_UNAVAILABLE")


class OpenClawCliOrLoopbackGatewayRpc:
    """Fall back only from an unavailable CLI to the same local Gateway RPC."""

    def __init__(self, *, primary: GatewayRpc, fallback: GatewayRpc) -> None:
        self._primary = primary
        self._fallback = fallback
        self._primary_is_unavailable = False

    def __call__(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self._primary_is_unavailable:
            try:
                result = self._primary(method, params)
                if not isinstance(result, dict):
                    raise Phase8GatewayRpcError("RPC_OUTPUT_INVALID")
                return cast(dict[str, Any], result)
            except Phase8GatewayRpcError as exc:
                if exc.code != "RPC_UNAVAILABLE":
                    raise
                self._primary_is_unavailable = True
        result = self._fallback(method, params)
        if not isinstance(result, dict):
            raise Phase8GatewayRpcError("RPC_OUTPUT_INVALID")
        return cast(dict[str, Any], result)


class OpenClawCliGatewayRpc:
    """Call an explicit local OpenClaw CLI entry with a fixed RPC allowlist."""

    def __init__(
        self,
        *,
        command_prefix: Sequence[str | Path],
        timeout_seconds: float = 10.0,
        runner: CommandRunner = subprocess.run,
    ) -> None:
        if isinstance(command_prefix, (str, bytes)) or not command_prefix:
            raise Phase8GatewayRpcError("CLI_COMMAND_INVALID")
        prefix = tuple(str(value) for value in command_prefix)
        if (
            any(not value.strip() for value in prefix)
            or any(not Path(value).is_absolute() or not Path(value).is_file() for value in prefix)
            or not isinstance(timeout_seconds, (int, float))
            or isinstance(timeout_seconds, bool)
            or not 0 < timeout_seconds <= 60
        ):
            raise Phase8GatewayRpcError("CLI_COMMAND_INVALID")
        self._command_prefix = prefix
        self._timeout_seconds = float(timeout_seconds)
        self._runner = runner

    def __call__(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        _validate_rpc_params(method, params)
        try:
            encoded = json.dumps(
                params,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        except (TypeError, ValueError):
            raise Phase8GatewayRpcError("RPC_PARAMS_FORBIDDEN") from None
        args = (
            *self._command_prefix,
            "gateway",
            "call",
            method,
            "--params",
            encoded,
            "--timeout",
            str(round(self._timeout_seconds * 1000)),
            "--json",
        )
        try:
            completed = self._runner(
                args,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds + 2,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            raise Phase8GatewayRpcError("RPC_UNAVAILABLE") from None
        if completed.returncode != 0:
            raise Phase8GatewayRpcError("RPC_REJECTED")
        output = completed.stdout
        if not isinstance(output, str) or len(output.encode("utf-8")) > _MAX_RPC_OUTPUT_BYTES:
            raise Phase8GatewayRpcError("RPC_OUTPUT_INVALID")
        try:
            result = json.loads(
                output,
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_nonfinite,
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            raise Phase8GatewayRpcError("RPC_OUTPUT_INVALID") from None
        if not isinstance(result, dict):
            raise Phase8GatewayRpcError("RPC_OUTPUT_INVALID")
        if result.get("ok") is False:
            raise Phase8GatewayRpcError("RPC_REJECTED")
        return result


class EnvironmentGatewayTokenProvider:
    """Read the fixed Gateway token environment variable only when called."""

    def __init__(self, environment: Mapping[str, str] | None = None) -> None:
        self._environment = environment if environment is not None else os.environ

    def __call__(self) -> str:
        return self._environment.get("OPENCLAW_GATEWAY_TOKEN", "")


def _gateway_rpc_with_loopback_fallback(
    *,
    command_prefix: Sequence[str | Path],
    base_url: str | None,
    token_provider: Callable[[], str],
    timeout_seconds: float = 10.0,
    runner: CommandRunner = subprocess.run,
) -> GatewayRpc:
    primary = OpenClawCliGatewayRpc(
        command_prefix=command_prefix,
        timeout_seconds=timeout_seconds,
        runner=runner,
    )
    if base_url is None:
        return primary
    fallback = OpenClawLoopbackGatewayRpc(
        base_url=base_url,
        token_provider=token_provider,
        timeout_seconds=timeout_seconds,
    )
    return OpenClawCliOrLoopbackGatewayRpc(primary=primary, fallback=fallback)


def verify_phase8_no_write_gateway_readiness(
    *,
    command_prefix: Sequence[str | Path],
    gateway_base_url: str | None = None,
    token_provider: Callable[[], str] | None = None,
    gateway_rpc: GatewayRpc | None = None,
) -> None:
    """Confirm local inference prerequisites without creating a session or request.

    The gateway token is checked only for presence. The single permitted RPC is
    ``sessions.describe`` against a fixed probe key, which must not exist.
    Neither the token nor the Gateway response is retained or reported.
    """

    provider = token_provider if token_provider is not None else EnvironmentGatewayTokenProvider()
    try:
        token = provider()
    except Exception:
        raise Phase8GatewayRpcError("GATEWAY_TOKEN_UNAVAILABLE") from None
    if not isinstance(token, str) or not token.strip():
        raise Phase8GatewayRpcError("GATEWAY_TOKEN_UNAVAILABLE")

    rpc = (
        gateway_rpc
        if gateway_rpc is not None
        else _gateway_rpc_with_loopback_fallback(
            command_prefix=command_prefix,
            base_url=gateway_base_url,
            token_provider=provider,
        )
    )
    try:
        response = rpc(
            "sessions.describe",
            {"key": _NO_WRITE_READINESS_SESSION_KEY},
        )
    except Phase8GatewayRpcError:
        raise
    except Exception:
        raise Phase8GatewayRpcError("GATEWAY_RPC_UNAVAILABLE") from None
    if not isinstance(response, dict) or "session" not in response:
        raise Phase8GatewayRpcError("GATEWAY_READINESS_INVALID")
    if response["session"] is not None:
        raise Phase8GatewayRpcError("GATEWAY_READINESS_SESSION_EXISTS")


class ManagedPhase8VisualRuntime:
    """Own the no-tool guard, loopback client, profile, and transport lifecycle."""

    def __init__(
        self,
        *,
        command_prefix: Sequence[str | Path],
        base_url: str,
        provider: str,
        physical_model: str,
        validator_model: str,
        physical_agent_id: str,
        validator_agent_id: str,
        implementation_revision: str,
        evidence_packet: RetainedVisualEvidencePacket,
        token_provider: Callable[[], str] | None = None,
        http_transport: httpx.BaseTransport | None = None,
        rpc_runner: CommandRunner = subprocess.run,
        gateway_timeout_seconds: float = 10.0,
        inference_timeout_seconds: float = 120.0,
    ) -> None:
        if (
            not isinstance(inference_timeout_seconds, (int, float))
            or isinstance(inference_timeout_seconds, bool)
            or not 0 < inference_timeout_seconds <= 600
        ):
            raise Phase8GatewayRpcError("HTTP_TIMEOUT_INVALID")
        self.profile = build_visual_inference_profile(
            implementation_revision=implementation_revision,
            provider=provider,
            physical_model=physical_model,
            validator_model=validator_model,
        )
        gateway_token_provider = (
            token_provider if token_provider is not None else EnvironmentGatewayTokenProvider()
        )
        rpc = _gateway_rpc_with_loopback_fallback(
            command_prefix=command_prefix,
            base_url=base_url,
            token_provider=gateway_token_provider,
            timeout_seconds=gateway_timeout_seconds,
            runner=rpc_runner,
        )
        guard = OpenClawGatewayNoToolSessionGuard(
            gateway_rpc=rpc,
            provider=provider,
            agent_models={
                physical_agent_id: physical_model,
                validator_agent_id: validator_model,
            },
            policy_revision_sha256=self.profile["runtime_policy_sha256"],
        )
        self._client = httpx.Client(
            transport=http_transport,
            timeout=inference_timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        )
        try:
            self.transport = Phase8OpenResponsesTransport(
                client=self._client,
                base_url=base_url,
                token_provider=gateway_token_provider,
                evidence_packet=evidence_packet,
                session_guard=guard,
                runtime_agent_ids={
                    "cf-physical-model": physical_agent_id,
                    "cf-validator": validator_agent_id,
                },
            )
        except BaseException:
            self._client.close()
            raise

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ManagedPhase8VisualRuntime:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()


__all__ = [
    "EnvironmentGatewayTokenProvider",
    "ManagedPhase8VisualRuntime",
    "OpenClawCliGatewayRpc",
    "OpenClawLoopbackGatewayRpc",
    "Phase8GatewayRpcError",
    "validate_phase8_loopback_gateway_url",
    "verify_phase8_no_write_gateway_readiness",
]
