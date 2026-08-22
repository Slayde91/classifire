"""Managed local runtime composition for Phase 8 proposal-only inference.

The runtime intentionally exposes only five read/control Gateway RPC methods.
It owns a proxy-independent loopback HTTP client and obtains the Gateway token
only after the server-side no-tool attestation succeeds.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

import httpx

from .phase8_openresponses_transport import (
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


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _reject_nonfinite(_value: str) -> None:
    raise ValueError("non-finite number")


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
            or any(
                not Path(value).is_absolute() or not Path(value).is_file()
                for value in prefix
            )
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
        rpc = OpenClawCliGatewayRpc(
            command_prefix=command_prefix,
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
                token_provider=(
                    token_provider
                    if token_provider is not None
                    else EnvironmentGatewayTokenProvider()
                ),
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
    "Phase8GatewayRpcError",
]
