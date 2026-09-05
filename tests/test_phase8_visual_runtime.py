from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import httpx
import pytest

from classifire.services.phase8_openresponses_transport import (
    Phase8OpenResponsesTransportError,
)
from classifire.services.phase8_visual_evidence import (
    RetainedVisualEvidenceFile,
    RetainedVisualEvidencePacket,
)
from classifire.services.phase8_visual_proposal import (
    VISUAL_EVIDENCE_MANIFEST_SCHEMA,
    VISUAL_INFERENCE_REQUEST_SCHEMA,
    VISUAL_PROPOSAL_POLICY_VERSION,
    canonical_json_sha256,
)
from classifire.services.phase8_visual_runtime import (
    EnvironmentGatewayTokenProvider,
    ManagedPhase8VisualRuntime,
    OpenClawCliGatewayRpc,
    OpenClawCliOrLoopbackGatewayRpc,
    OpenClawLoopbackGatewayRpc,
    Phase8GatewayRpcError,
    verify_phase8_no_write_gateway_readiness,
)


def _executable(tmp_path: Path) -> Path:
    path = tmp_path / "node.exe"
    path.write_bytes(b"synthetic executable")
    return path


def _packet(tmp_path: Path) -> RetainedVisualEvidencePacket:
    data = b"synthetic-image-bytes"
    image = tmp_path / "evidence.png"
    image.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    manifest = {
        "schema": VISUAL_EVIDENCE_MANIFEST_SCHEMA,
        "estimate_id": "EST-001",
        "defect_reference": "D-001",
        "human_reference_included": False,
        "artifacts": [
            {
                "evidence_id": "E-001",
                "sha256": digest,
                "size_bytes": len(data),
                "media_type": "image/png",
                "inference_allowed": True,
                "validation_only": False,
                "provenance": {
                    "source_reference": "evidence-source:E-001",
                    "page_number": 1,
                    "region_reference": "photo-1",
                    "evidence_class": "observed",
                    "evidence_role": "primary_detail",
                    "relationship": "embedded_image",
                    "parent_evidence_id": None,
                    "pixel_width": 32,
                    "pixel_height": 24,
                },
            }
        ],
    }
    return RetainedVisualEvidencePacket(
        manifest=manifest,
        files=(
            RetainedVisualEvidenceFile(
                evidence_id="E-001",
                path=image,
                sha256=digest,
                size_bytes=len(data),
                media_type="image/png",
            ),
        ),
    )


def _request(packet: RetainedVisualEvidencePacket, profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": VISUAL_INFERENCE_REQUEST_SCHEMA,
        "policy_version": VISUAL_PROPOSAL_POLICY_VERSION,
        "run_id": "RUN-001",
        "estimate_id": "EST-001",
        "defect_reference": "D-001",
        "evidence_manifest": packet.manifest,
        "evidence_manifest_sha256": packet.manifest_sha256,
        "inference_profile": profile,
        "inference_profile_sha256": canonical_json_sha256(profile),
        "human_reference_visible": False,
        "allowed_tools": [],
        "stage_input": {},
    }


class _GatewaySocket:
    def __init__(self) -> None:
        self.incoming = bytearray()
        self.requests: list[dict[str, Any]] = []
        self.closed = False

    @staticmethod
    def _server_text(payload: dict[str, Any]) -> bytes:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return bytes((0x81, len(encoded))) + encoded

    @staticmethod
    def _client_text(payload: bytes) -> dict[str, Any]:
        assert payload[0] == 0x81
        assert payload[1] & 0x80
        length = payload[1] & 0x7F
        start = 2
        if length == 126:
            length = int.from_bytes(payload[start : start + 2], "big")
            start += 2
        elif length == 127:
            length = int.from_bytes(payload[start : start + 8], "big")
            start += 8
        mask = payload[start : start + 4]
        start += 4
        encoded = bytes(
            value ^ mask[index % 4] for index, value in enumerate(payload[start : start + length])
        )
        decoded = json.loads(encoded)
        assert isinstance(decoded, dict)
        return decoded

    def close(self) -> None:
        self.closed = True

    def recv(self, size: int) -> bytes:
        if not self.incoming:
            raise TimeoutError()
        chunk = bytes(self.incoming[:size])
        del self.incoming[:size]
        return chunk

    def sendall(self, payload: bytes) -> None:
        if payload.startswith(b"GET / HTTP/1.1"):
            key = next(
                line.split(": ", 1)[1]
                for line in payload.decode("ascii").split("\r\n")
                if line.startswith("Sec-WebSocket-Key: ")
            )
            accept = base64.b64encode(
                hashlib.sha1(  # noqa: S324 - RFC 6455 Sec-WebSocket-Accept requires SHA-1
                    (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii"),
                    usedforsecurity=False,
                ).digest()
            ).decode("ascii")
            self.incoming.extend(
                (
                    "HTTP/1.1 101 Switching Protocols\r\n"
                    "Upgrade: websocket\r\n"
                    "Connection: Upgrade\r\n"
                    f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
                ).encode("ascii")
            )
            self.incoming.extend(
                self._server_text(
                    {
                        "type": "event",
                        "event": "connect.challenge",
                        "payload": {"nonce": "test-nonce"},
                    }
                )
            )
            return
        request = self._client_text(payload)
        self.requests.append(request)
        if request["method"] == "connect":
            response = {"type": "res", "id": request["id"], "ok": True, "payload": {}}
        else:
            response = {
                "type": "res",
                "id": request["id"],
                "ok": True,
                "payload": {"session": None},
            }
        self.incoming.extend(self._server_text(response))

    def settimeout(self, value: float | None) -> None:
        assert value is None or value > 0


def test_loopback_gateway_rpc_uses_authenticated_least_privilege_framing() -> None:
    created: list[_GatewaySocket] = []

    def socket_factory(address: tuple[str, int], timeout: float) -> _GatewaySocket:
        assert address == ("127.0.0.1", 18789)
        assert timeout > 0
        gateway_socket = _GatewaySocket()
        created.append(gateway_socket)
        return gateway_socket

    rpc = OpenClawLoopbackGatewayRpc(
        base_url="http://127.0.0.1:18789",
        token_provider=lambda: "runtime-secret",
        socket_factory=socket_factory,
    )
    assert rpc("sessions.describe", {"key": "classifire-phase8-readiness-no-write"}) == {
        "session": None
    }
    gateway_socket = created[0]
    assert [request["method"] for request in gateway_socket.requests] == [
        "connect",
        "sessions.describe",
    ]
    assert gateway_socket.requests[0]["params"]["scopes"] == ["operator.read"]
    assert gateway_socket.closed is True


def test_cli_unavailability_uses_loopback_for_later_calls() -> None:
    primary_calls = 0
    fallback_calls = 0

    def primary(method: str, params: dict[str, Any]) -> dict[str, Any]:
        nonlocal primary_calls
        primary_calls += 1
        raise Phase8GatewayRpcError("RPC_UNAVAILABLE")

    def fallback(method: str, params: dict[str, Any]) -> dict[str, Any]:
        nonlocal fallback_calls
        fallback_calls += 1
        return {"session": None}

    rpc = OpenClawCliOrLoopbackGatewayRpc(primary=primary, fallback=fallback)
    assert rpc("sessions.describe", {"key": "one"}) == {"session": None}
    assert rpc("sessions.describe", {"key": "two"}) == {"session": None}
    assert primary_calls == 1
    assert fallback_calls == 2


@pytest.mark.parametrize(
    "base_url",
    (
        "https://gateway.example.test",
        "http://localhost:18789",
        "http://192.0.2.1:18789",
    ),
)
def test_loopback_gateway_rpc_rejects_non_literal_loopback_endpoint(
    base_url: str,
) -> None:
    with pytest.raises(Phase8GatewayRpcError, match="LOOPBACK_GATEWAY_URL_INVALID"):
        OpenClawLoopbackGatewayRpc(
            base_url=base_url,
            token_provider=lambda: "runtime-secret",
        )


def test_cli_rpc_uses_fixed_command_shape_and_no_shell(tmp_path: Path) -> None:
    calls: list[tuple[tuple[str, ...], dict[str, Any]]] = []

    def runner(args, **kwargs):
        calls.append((tuple(args), kwargs))
        return subprocess.CompletedProcess(args, 0, '{"groups":[]}', "secret stderr")

    executable = _executable(tmp_path)
    rpc = OpenClawCliGatewayRpc(command_prefix=(executable,), runner=runner)
    result = rpc(
        "tools.effective",
        {"sessionKey": "agent:cf-validator:test", "agentId": "cf-validator"},
    )

    assert result == {"groups": []}
    args, kwargs = calls[0]
    assert args[:4] == (str(executable), "gateway", "call", "tools.effective")
    assert args[-3:] == ("--timeout", "10000", "--json")
    assert json.loads(args[args.index("--params") + 1]) == {
        "sessionKey": "agent:cf-validator:test",
        "agentId": "cf-validator",
    }
    assert kwargs == {
        "capture_output": True,
        "text": True,
        "timeout": 12.0,
        "check": False,
    }


def test_cli_rpc_rejects_unapproved_methods_params_and_outputs(tmp_path: Path) -> None:
    calls = 0

    def runner(args, **kwargs):
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(args, 0, '{"ok":true}', "")

    rpc = OpenClawCliGatewayRpc(command_prefix=(_executable(tmp_path),), runner=runner)
    with pytest.raises(Phase8GatewayRpcError, match="RPC_METHOD_FORBIDDEN"):
        rpc("sessions.delete", {"key": "agent:cf-validator:test"})
    with pytest.raises(Phase8GatewayRpcError, match="RPC_PARAMS_FORBIDDEN"):
        rpc(
            "sessions.create",
            {
                "key": "agent:cf-validator:test",
                "agentId": "cf-validator",
                "model": "provider/model",
                "message": "must never be sent",
            },
        )
    assert calls == 0

    for output in ('{"value":1,"value":2}', '{"value":NaN}', "prefix {}"):

        def invalid_runner(args, _output=output, **kwargs):
            return subprocess.CompletedProcess(args, 0, _output, "secret response")

        invalid_rpc = OpenClawCliGatewayRpc(
            command_prefix=(_executable(tmp_path),), runner=invalid_runner
        )
        with pytest.raises(Phase8GatewayRpcError) as exc_info:
            invalid_rpc(
                "tools.effective",
                {
                    "sessionKey": "agent:cf-validator:test",
                    "agentId": "cf-validator",
                },
            )
        assert exc_info.value.code == "RPC_OUTPUT_INVALID"
        assert "secret response" not in str(exc_info.value)


def test_environment_token_provider_is_lazy_and_fixed(monkeypatch) -> None:
    monkeypatch.delenv("OPENCLAW_GATEWAY_TOKEN", raising=False)
    provider = EnvironmentGatewayTokenProvider()
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "runtime-secret")
    assert provider() == "runtime-secret"


def test_no_write_gateway_readiness_requires_token_and_only_describes_session(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(method: str, params: dict[str, Any]) -> dict[str, Any]:
        calls.append((method, params))
        return {"session": None}

    verify_phase8_no_write_gateway_readiness(
        command_prefix=(_executable(tmp_path),),
        token_provider=lambda: "runtime-secret",
        gateway_rpc=rpc,
    )

    assert calls == [("sessions.describe", {"key": "classifire-phase8-readiness-no-write"})]
    with pytest.raises(Phase8GatewayRpcError, match="GATEWAY_TOKEN_UNAVAILABLE"):
        verify_phase8_no_write_gateway_readiness(
            command_prefix=(_executable(tmp_path),),
            token_provider=lambda: "",
            gateway_rpc=rpc,
        )
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("effective_tools", "expected_code"),
    [
        ([{"id": "classifire_evidence_read"}], "SERVER_TOOLS_NOT_EMPTY"),
        ([], "COMPLETION_EVIDENCE_UNAVAILABLE"),
    ],
)
def test_managed_runtime_registers_metadata_then_fails_before_token_and_http(
    tmp_path: Path, effective_tools: list[dict[str, str]], expected_code: str,
) -> None:
    packet = _packet(tmp_path)
    rpc_calls: list[tuple[str, dict[str, Any]]] = []
    counts = {"token": 0, "http": 0}
    session_created = False

    def runner(args, **kwargs):
        nonlocal session_created
        method = args[3]
        params = json.loads(args[args.index("--params") + 1])
        rpc_calls.append((method, params))
        if method == "sessions.create":
            session_created = True
            payload = {
                "ok": True,
                "key": params["key"],
                "sessionId": "session-id",
                "entry": {"sessionId": "session-id"},
                "runStarted": False,
            }
        elif method == "sessions.describe":
            payload = (
                {"session": None}
                if not session_created
                else {
                    "session": {
                        "key": params["key"],
                        "sessionId": "session-id",
                        "modelProvider": "test-provider",
                        "model": "validator-model",
                    }
                }
            )
        else:
            payload = {
                "groups": [
                    {
                        "name": "classifire",
                        "tools": effective_tools,
                    }
                ]
            }
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

    def token_provider() -> str:
        counts["token"] += 1
        return "secret"

    def handler(request: httpx.Request) -> httpx.Response:
        counts["http"] += 1
        return httpx.Response(500)

    with ManagedPhase8VisualRuntime(
        command_prefix=(_executable(tmp_path),),
        base_url="http://127.0.0.1:18789/v1",
        provider="test-provider",
        physical_model="physical-model",
        validator_model="validator-model",
        physical_agent_id="cf-phase8-visual-physical",
        validator_agent_id="cf-phase8-visual-validator",
        implementation_revision="a" * 40,
        evidence_packet=packet,
        token_provider=token_provider,
        http_transport=httpx.MockTransport(handler),
        rpc_runner=runner,
    ) as runtime:
        with pytest.raises(Phase8OpenResponsesTransportError) as exc_info:
            runtime.transport.invoke(
                role="cf-validator",
                stage="blind_inventory",
                request=_request(packet, runtime.profile),
            )
        assert exc_info.value.code == expected_code
        client = runtime._client

    assert [method for method, _params in rpc_calls] == [
        "sessions.describe",
        "sessions.create",
        "sessions.describe",
        "tools.effective",
    ]
    assert set(rpc_calls[1][1]) == {"key", "agentId", "model"}
    assert "message" not in rpc_calls[1][1]
    assert "task" not in rpc_calls[1][1]
    assert rpc_calls[1][1]["agentId"] == "cf-phase8-visual-validator"
    assert rpc_calls[1][1]["model"] == "test-provider/validator-model"
    assert rpc_calls[0][1]["key"].startswith("agent:cf-phase8-visual-validator:classifire-phase8-")
    assert counts == {"token": 0, "http": 0}
    assert client.is_closed


@pytest.mark.parametrize("code", ["RPC_REJECTED", "RPC_OUTPUT_INVALID", "RPC_PARAMS_FORBIDDEN"])
def test_cli_policy_failure_never_falls_back_or_changes_route(code: str) -> None:
    calls: list[str] = []

    def primary(method: str, params: dict[str, Any]) -> dict[str, Any]:
        calls.append("primary")
        raise Phase8GatewayRpcError(code)

    def fallback(method: str, params: dict[str, Any]) -> dict[str, Any]:
        calls.append("fallback")
        return {"session": None}

    rpc = OpenClawCliOrLoopbackGatewayRpc(primary=primary, fallback=fallback)
    for _ in range(2):
        with pytest.raises(Phase8GatewayRpcError) as error:
            rpc("sessions.describe", {"key": "synthetic-session"})
        assert error.value.code == code
    assert calls == ["primary", "primary"]


@pytest.mark.parametrize("invalid_on", ["primary", "fallback"])
def test_rpc_fallback_rejects_non_object_results(invalid_on: str) -> None:
    calls: list[str] = []

    def primary(method: str, params: dict[str, Any]) -> Any:
        calls.append("primary")
        if invalid_on == "fallback":
            raise Phase8GatewayRpcError("RPC_UNAVAILABLE")
        return []

    def fallback(method: str, params: dict[str, Any]) -> Any:
        calls.append("fallback")
        return []

    rpc = OpenClawCliOrLoopbackGatewayRpc(primary=primary, fallback=fallback)
    with pytest.raises(Phase8GatewayRpcError) as error:
        rpc("sessions.describe", {"key": "synthetic-session"})
    assert error.value.code == "RPC_OUTPUT_INVALID"
    assert calls == (["primary"] if invalid_on == "primary" else ["primary", "fallback"])


def test_cli_timeout_contract_is_unavailable_and_does_not_expose_process_output(
    tmp_path: Path,
) -> None:
    def runner(args, **kwargs):
        raise subprocess.TimeoutExpired(
            args, timeout=12, output="synthetic-private-output", stderr="synthetic-private-stderr"
        )

    rpc = OpenClawCliGatewayRpc(command_prefix=(_executable(tmp_path),), runner=runner)
    with pytest.raises(Phase8GatewayRpcError) as error:
        rpc("sessions.describe", {"key": "synthetic-session"})
    assert error.value.code == "RPC_UNAVAILABLE"
    assert "synthetic-private" not in str(error.value)
    assert error.value.__suppress_context__ is True


@pytest.mark.parametrize("failure", ["timeout", "process", "os"])
def test_uncertain_session_creation_never_replays_or_switches_route(
    tmp_path: Path, failure: str
) -> None:
    calls: list[tuple[str, str]] = []
    created: list[str] = []
    params = {"key": "synthetic-session", "agentId": "cf-validator", "model": "provider/model"}

    def runner(args, **kwargs):
        method = args[3]
        calls.append(("primary", method))
        if method == "sessions.describe":
            return subprocess.CompletedProcess(args, 0, '{"session":null}', "")
        assert method == "sessions.create"
        created.append(json.loads(args[args.index("--params") + 1])["key"])
        if failure == "timeout":
            raise subprocess.TimeoutExpired(
                args, timeout=12, output="private-output", stderr="private-stderr"
            )
        if failure == "process":
            raise subprocess.SubprocessError("private-process-detail")
        raise OSError("private-os-detail")

    def fallback(method: str, values: dict[str, Any]) -> dict[str, Any]:
        calls.append(("fallback", method))
        created.append(values["key"])
        return {"ok": True}

    rpc = OpenClawCliOrLoopbackGatewayRpc(
        primary=OpenClawCliGatewayRpc(command_prefix=(_executable(tmp_path),), runner=runner),
        fallback=fallback,
    )
    with pytest.raises(Phase8GatewayRpcError) as error:
        rpc("sessions.create", params)
    assert error.value.code == "RPC_OUTCOME_UNKNOWN"
    assert str(error.value) == "Phase 8 Gateway RPC failed: RPC_OUTCOME_UNKNOWN."
    assert error.value.__suppress_context__ is True
    assert created == ["synthetic-session"]
    assert rpc("sessions.describe", {"key": "synthetic-session"}) == {"session": None}
    assert calls == [("primary", "sessions.create"), ("primary", "sessions.describe")]


def test_read_only_fallback_selection_allows_one_later_creation() -> None:
    calls: list[tuple[str, str]] = []

    def primary(method: str, params: dict[str, Any]) -> dict[str, Any]:
        calls.append(("primary", method))
        raise Phase8GatewayRpcError("RPC_UNAVAILABLE")

    def fallback(method: str, params: dict[str, Any]) -> dict[str, Any]:
        calls.append(("fallback", method))
        return {"session": None} if method == "sessions.describe" else {"ok": True}

    rpc = OpenClawCliOrLoopbackGatewayRpc(primary=primary, fallback=fallback)
    assert rpc("sessions.describe", {"key": "synthetic-session"}) == {"session": None}
    assert rpc(
        "sessions.create",
        {"key": "synthetic-session", "agentId": "cf-validator", "model": "provider/model"},
    ) == {"ok": True}
    assert calls == [
        ("primary", "sessions.describe"),
        ("fallback", "sessions.describe"),
        ("fallback", "sessions.create"),
    ]


def test_managed_runtime_stops_after_uncertain_creation_before_fallback_or_inference(
    tmp_path: Path, monkeypatch
) -> None:
    packet = _packet(tmp_path)
    calls: list[str] = []
    counts = {"fallback": 0, "token": 0, "http": 0}

    def runner(args, **kwargs):
        method = args[3]
        calls.append(method)
        if method == "sessions.describe":
            return subprocess.CompletedProcess(args, 0, '{"session":null}', "")
        assert method == "sessions.create"
        raise subprocess.TimeoutExpired(args, timeout=12, output="private-output")

    def fallback(self, method, params):
        counts["fallback"] += 1
        raise Phase8GatewayRpcError("RPC_UNAVAILABLE")

    monkeypatch.setattr(OpenClawLoopbackGatewayRpc, "__call__", fallback)

    def token_provider() -> str:
        counts["token"] += 1
        return "synthetic-token"

    def handler(request: httpx.Request) -> httpx.Response:
        counts["http"] += 1
        return httpx.Response(500)

    with ManagedPhase8VisualRuntime(
        command_prefix=(_executable(tmp_path),),
        base_url="http://127.0.0.1:18789/v1",
        provider="test-provider",
        physical_model="physical-model",
        validator_model="validator-model",
        physical_agent_id="cf-phase8-visual-physical",
        validator_agent_id="cf-phase8-visual-validator",
        implementation_revision="a" * 40,
        evidence_packet=packet,
        token_provider=token_provider,
        http_transport=httpx.MockTransport(handler),
        rpc_runner=runner,
    ) as runtime:
        with pytest.raises(Phase8OpenResponsesTransportError) as error:
            runtime.transport.invoke(
                role="cf-validator",
                stage="blind_inventory",
                request=_request(packet, runtime.profile),
            )
        assert error.value.code == "TOOL_ATTESTATION_UNAVAILABLE"
        assert "private-output" not in str(error.value)
        assert error.value.__suppress_context__ is True
    assert calls == ["sessions.describe", "sessions.create"]
    assert counts == {"fallback": 0, "token": 0, "http": 0}


@pytest.mark.parametrize(
    ("fault", "expected"),
    [
        ("close", "RPC_UNAVAILABLE"),
        ("eof", "RPC_UNAVAILABLE"),
        ("timeout", "RPC_UNAVAILABLE"),
        ("os_error", "RPC_UNAVAILABLE"),
        ("reserved_bits", "RPC_OUTPUT_INVALID"),
        ("fragmented", "RPC_OUTPUT_INVALID"),
        ("masked", "RPC_OUTPUT_INVALID"),
        ("binary", "RPC_OUTPUT_INVALID"),
        ("invalid_utf8", "RPC_OUTPUT_INVALID"),
        ("invalid_json", "RPC_OUTPUT_INVALID"),
        ("oversized", "RPC_OUTPUT_INVALID"),
        ("wrong_request_id", "RPC_UNAVAILABLE"),
        ("wrong_connect_id", "RPC_UNAVAILABLE"),
    ],
)
def test_loopback_socket_failures_close_without_repeating_creation(
    fault: str,
    expected: str,
) -> None:
    class FaultSocket(_GatewaySocket):
        def sendall(self, payload: bytes) -> None:
            super().sendall(payload)
            if not self.requests:
                return
            method = self.requests[-1]["method"]
            if fault == "wrong_connect_id" and method == "connect":
                self.incoming = bytearray(
                    self._server_text(
                        {"type": "res", "id": "unrelated-connect", "ok": True, "payload": {}},
                    )
                )
                return
            if method == "connect":
                return
            invalid_frames = {
                "close": b"\x88\x00",
                "eof": b"",
                "timeout": b"",
                "os_error": b"",
                "reserved_bits": b"\xc1\x00",
                "fragmented": b"\x01\x00",
                "masked": b"\x81\x80",
                "binary": b"\x82\x00",
                "invalid_utf8": b"\x81\x01\xff",
                "invalid_json": b"\x81\x01{",
                "oversized": b"\x81\x7f" + (1_000_001).to_bytes(8, "big"),
                "wrong_request_id": self._server_text(
                    {"type": "res", "id": "unrelated-request", "ok": True, "payload": {}},
                ),
            }
            self.incoming = bytearray(invalid_frames[fault])

        def recv(self, size: int) -> bytes:
            if self.requests and self.requests[-1]["method"] == "sessions.create":
                if fault == "eof":
                    return b""
                if fault == "timeout":
                    raise TimeoutError("synthetic-private-timeout")
                if fault == "os_error":
                    raise OSError("synthetic-private-socket-detail")
            return super().recv(size)

    gateway_socket = FaultSocket()
    factory_calls = []

    def socket_factory(address, timeout):
        factory_calls.append(address)
        return gateway_socket

    rpc = OpenClawLoopbackGatewayRpc(
        base_url="http://127.0.0.1:18789",
        token_provider=lambda: "synthetic-token",
        socket_factory=socket_factory,
    )
    with pytest.raises(Phase8GatewayRpcError) as error:
        rpc(
            "sessions.create",
            {
                "key": "synthetic-session",
                "agentId": "cf-validator",
                "model": "provider/model",
            },
        )
    assert error.value.code == expected
    assert "synthetic-private" not in str(error.value)
    assert gateway_socket.closed is True
    assert factory_calls == [("127.0.0.1", 18789)]
    assert [request["method"] for request in gateway_socket.requests] == (
        ["connect"] if fault == "wrong_connect_id" else ["connect", "sessions.create"]
    )
    assert gateway_socket.requests[0]["params"]["scopes"] == ["operator.write"]


@pytest.mark.parametrize("late_stage", ["receive", "decode"])
def test_loopback_reply_received_after_deadline_is_refused_and_socket_closed(
    monkeypatch,
    late_stage: str,
) -> None:
    from classifire.services import phase8_visual_runtime

    now = [100.0]
    original_parse = phase8_visual_runtime._parse_gateway_json

    def parse_reply(value):
        result = original_parse(value)
        if late_stage == "decode" and result.get("payload") == {"session": None}:
            now[0] = 111.0
        return result

    monkeypatch.setattr(phase8_visual_runtime, "_parse_gateway_json", parse_reply)
    monkeypatch.setattr(
        "classifire.services.phase8_visual_runtime.time.monotonic",
        lambda: now[0],
    )

    class LateReplySocket(_GatewaySocket):
        def recv(self, size: int) -> bytes:
            chunk = super().recv(size)
            if (
                late_stage == "receive"
                and self.requests
                and self.requests[-1]["method"] == "sessions.describe"
            ):
                now[0] = 111.0
            return chunk

    gateway_socket = LateReplySocket()
    rpc = OpenClawLoopbackGatewayRpc(
        base_url="http://127.0.0.1:18789",
        token_provider=lambda: "synthetic-token",
        timeout_seconds=10,
        socket_factory=lambda address, timeout: gateway_socket,
    )
    with pytest.raises(Phase8GatewayRpcError) as error:
        rpc("sessions.describe", {"key": "synthetic-session"})
    assert error.value.code == "RPC_UNAVAILABLE"
    assert gateway_socket.closed is True
    assert [request["method"] for request in gateway_socket.requests] == [
        "connect",
        "sessions.describe",
    ]
