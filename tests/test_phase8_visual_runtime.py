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
from classifire.services.storage import VerifiedStoredFile

_STORED_FILE_ID = "00000000-0000-4000-8000-000000000001"
_SCAN_ATTESTATION_ID = "00000000-0000-4000-8000-000000000002"


def _executable(tmp_path: Path) -> Path:
    path = tmp_path / "node.exe"
    path.write_bytes(b"synthetic executable")
    return path


def _packet(tmp_path: Path) -> RetainedVisualEvidencePacket:
    data = b"synthetic-image-bytes"
    image = tmp_path / "evidence.png"
    image.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    verification_token = VerifiedStoredFile(
        stored_file_id=_STORED_FILE_ID,
        path=image,
        content_sha256=digest,
        content_size_bytes=len(data),
        media_type="image/png",
        purpose="technical_evidence",
        scan_attestation_id=_SCAN_ATTESTATION_ID,
        scan_attestation_sha256="C" * 64,
        scan_sequence=1,
    )
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
                verification_token=verification_token,
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


def test_managed_runtime_registers_metadata_then_fails_before_token_and_http(
    tmp_path: Path,
) -> None:
    packet = _packet(tmp_path)
    rpc_calls: list[tuple[str, dict[str, Any]]] = []
    counts = {"token": 0, "http": 0}
    verified: list[RetainedVisualEvidencePacket] = []
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
                        "tools": [{"id": "classifire_evidence_read"}],
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
        evidence_packet_verifier=verified.append,
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
        assert exc_info.value.code == "SERVER_TOOLS_NOT_EMPTY"
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
    assert verified == [packet]
    assert client.is_closed
