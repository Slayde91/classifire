"""Fail-closed OpenResponses transport for Phase 8 proposal-only inference.

`tool_choice: none` only disables client-declared tools. This transport also
requires a runtime guard to prove that the exact OpenClaw session has no
effective server-side tools, and audits that session after every attempted turn.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx

from .phase8_visual_evidence import (
    RetainedVisualEvidenceFile,
    RetainedVisualEvidencePacket,
)
from .phase8_visual_prompts import (
    Phase8VisualPromptRenderer,
    prompt_profile_field,
)
from .phase8_visual_proposal import (
    VISUAL_INFERENCE_REQUEST_SCHEMA,
    VISUAL_INFERENCE_RESPONSE_SCHEMA,
    VISUAL_PROPOSAL_POLICY_VERSION,
    canonical_json_sha256,
    validate_phase8_visual_proposal_receipt,
    validate_visual_evidence_manifest,
    validate_visual_inference_profile,
)
from .storage import VerifiedStoredFile

_ALLOWED_ROLES = frozenset({"cf-physical-model", "cf-validator"})
_ALLOWED_IMAGE_MIMES = frozenset(
    {"image/gif", "image/jpeg", "image/png", "image/webp"}
)
_MAX_IMAGE_COUNT = 8
_MAX_IMAGE_BYTES = 10 * 1024 * 1024
_MAX_RAW_IMAGE_BYTES = 12 * 1024 * 1024
_MAX_REQUEST_BYTES = 20_000_000
_MAX_OUTPUT_TOKENS = 16_000
_REQUEST_KEYS = {
    "schema",
    "policy_version",
    "run_id",
    "estimate_id",
    "defect_reference",
    "evidence_manifest",
    "evidence_manifest_sha256",
    "inference_profile",
    "inference_profile_sha256",
    "human_reference_visible",
    "allowed_tools",
    "stage_input",
}
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
_AGENT_ID_CHARACTERS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-_")
_EVIDENCE_ID_CHARACTERS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._:"
)
OPENRESPONSES_TRANSPORT_RECEIPT_SCHEMA = (
    "CLASSIFIRE-PHASE8-OPENRESPONSES-TRANSPORT-v2"
)
OPENRESPONSES_TRANSPORT_RECEIPT_BUNDLE_SCHEMA = (
    "CLASSIFIRE-PHASE8-OPENRESPONSES-TRANSPORT-RECEIPTS-v1"
)
_TRANSPORT_RECEIPT_KEYS = {
    "schema",
    "request_sha256",
    "prompt_template_sha256",
    "session_id_sha256",
    "attestation_receipt_sha256",
    "audit_receipt_sha256",
    "evidence",
    "openresponses_response_id_sha256",
    "payload_sha256",
}
_TRANSPORT_EVIDENCE_KEYS = {
    "evidence_id",
    "stored_file_id",
    "malware_scan_attestation_id",
    "malware_scan_attestation_receipt_sha256",
    "malware_scan_sequence",
    "sha256",
    "size_bytes",
    "media_type",
}


class Phase8OpenResponsesTransportError(RuntimeError):
    """A stable transport failure that never includes secrets or response content."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Phase 8 OpenResponses transport failed: {code}.")


@dataclass(frozen=True, slots=True)
class NoToolSessionAttestation:
    agent_id: str
    session_id_sha256: str
    provider: str
    model: str
    effective_tools: tuple[str, ...]
    receipt_sha256: str
    policy_revision_sha256: str


@dataclass(frozen=True, slots=True)
class NoToolSessionAudit:
    agent_id: str
    session_id_sha256: str
    tool_calls: tuple[str, ...]
    receipt_sha256: str


class NoToolSessionGuard(Protocol):
    """Prove the server-side session boundary before and after inference."""

    def attest(
        self,
        *,
        agent_id: str,
        session_key: str,
        provider: str,
        model: str,
    ) -> NoToolSessionAttestation: ...

    def audit(
        self,
        *,
        agent_id: str,
        session_key: str,
        after_ms: int,
    ) -> NoToolSessionAudit: ...


class GatewayRpc(Protocol):
    """Minimal RPC surface used by the concrete OpenClaw guard."""

    def __call__(self, method: str, params: dict[str, Any]) -> Any: ...


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX_DIGITS for character in value)
    )


def _is_agent_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and value == value.strip().casefold()
        and 1 <= len(value) <= 64
        and value[0].isalnum()
        and all(character in _AGENT_ID_CHARACTERS for character in value)
    )


def _is_canonical_uuid(value: object) -> bool:
    if not isinstance(value, str) or value != value.strip():
        return False
    try:
        return str(uuid.UUID(value)) == value
    except ValueError:
        return False


def _is_safe_evidence_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and value == value.strip()
        and 1 <= len(value) <= 128
        and value[0].isalnum()
        and all(character in _EVIDENCE_ID_CHARACTERS for character in value)
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest().upper()


def _normalised_media_type(value: object) -> str:
    media_type = str(value or "").split(";", 1)[0].strip().lower()
    return "image/jpeg" if media_type == "image/jpg" else media_type


def _effective_tool_names(value: Any) -> tuple[str, ...]:
    if not isinstance(value, dict) or not isinstance(value.get("groups"), list):
        raise Phase8OpenResponsesTransportError("TOOL_ATTESTATION_INVALID")
    names: set[str] = set()
    for group in value["groups"]:
        if not isinstance(group, dict):
            raise Phase8OpenResponsesTransportError("TOOL_ATTESTATION_INVALID")
        tools = group.get("tools")
        if not isinstance(tools, list):
            raise Phase8OpenResponsesTransportError("TOOL_ATTESTATION_INVALID")
        for tool in tools:
            if not isinstance(tool, dict) or not isinstance(tool.get("id"), str):
                raise Phase8OpenResponsesTransportError("TOOL_ATTESTATION_INVALID")
            name = tool["id"].strip()
            if not name:
                raise Phase8OpenResponsesTransportError("TOOL_ATTESTATION_INVALID")
            names.add(name)
    return tuple(sorted(names))


def _nonblank(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _valid_transport_evidence(value: object) -> bool:
    if not isinstance(value, list) or not value or len(value) > _MAX_IMAGE_COUNT:
        return False
    evidence_ids: set[str] = set()
    total_size_bytes = 0
    for item in value:
        if not isinstance(item, dict) or set(item) != _TRANSPORT_EVIDENCE_KEYS:
            return False
        evidence_id = _nonblank(item.get("evidence_id"))
        stored_file_id = _nonblank(item.get("stored_file_id"))
        scan_attestation_id = _nonblank(item.get("malware_scan_attestation_id"))
        sequence = item.get("malware_scan_sequence")
        size_bytes = item.get("size_bytes")
        if (
            item.get("evidence_id") != evidence_id
            or not _is_safe_evidence_id(evidence_id)
            or evidence_id in evidence_ids
            or item.get("stored_file_id") != stored_file_id
            or not _is_canonical_uuid(stored_file_id)
            or item.get("malware_scan_attestation_id") != scan_attestation_id
            or not _is_canonical_uuid(scan_attestation_id)
            or not _is_sha256(item.get("malware_scan_attestation_receipt_sha256"))
            or isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence < 1
            or not _is_sha256(item.get("sha256"))
            or isinstance(size_bytes, bool)
            or not isinstance(size_bytes, int)
            or not 1 <= size_bytes <= _MAX_IMAGE_BYTES
            or item.get("media_type") not in _ALLOWED_IMAGE_MIMES
        ):
            return False
        evidence_ids.add(evidence_id)
        total_size_bytes += size_bytes
    return total_size_bytes <= _MAX_RAW_IMAGE_BYTES


def validate_phase8_openresponses_transport_receipt_bundle(
    bundle: Any,
    *,
    controller_receipt: Any,
) -> list[str]:
    """Validate exact retained transport preimages against controller stages."""

    if not isinstance(bundle, dict):
        return ["transport receipt bundle must be an object"]
    errors: list[str] = []
    expected_bundle_keys = {
        "schema",
        "run_id",
        "evidence_manifest_sha256",
        "controller_receipt_canonical_json_sha256",
        "records",
    }
    if set(bundle) != expected_bundle_keys:
        errors.append("transport receipt bundle fields do not match the approved schema")
    if bundle.get("schema") != OPENRESPONSES_TRANSPORT_RECEIPT_BUNDLE_SCHEMA:
        errors.append("transport receipt bundle schema is unsupported")

    controller = controller_receipt if isinstance(controller_receipt, dict) else {}
    if validate_phase8_visual_proposal_receipt(controller_receipt):
        errors.append("transport receipt bundle controller receipt is invalid")
    if bundle.get("run_id") != controller.get("run_id"):
        errors.append("transport receipt bundle run_id does not match the controller")
    if bundle.get("evidence_manifest_sha256") != controller.get(
        "evidence_manifest_sha256"
    ):
        errors.append("transport receipt bundle evidence manifest does not match the controller")
    try:
        controller_sha256 = canonical_json_sha256(controller)
    except Exception:
        controller_sha256 = None
    if bundle.get("controller_receipt_canonical_json_sha256") != controller_sha256:
        errors.append("transport receipt bundle controller hash does not match")

    controller_stages = controller.get("stages")
    successful_stages = (
        [
            stage
            for stage in controller_stages
            if isinstance(stage, dict) and stage.get("failed") is not True
        ]
        if isinstance(controller_stages, list)
        else []
    )
    records = bundle.get("records")
    if not isinstance(records, list):
        errors.append("transport receipt bundle records must be an array")
        records = []
    if not successful_stages or not records:
        errors.append("transport receipt bundle requires a successful controller stage")
    if len(records) != len(successful_stages):
        errors.append("transport receipt bundle does not match successful controller stages")

    baseline_evidence: object = None
    seen_receipts: set[str] = set()
    expected_record_keys = {
        "sequence",
        "stage",
        "role",
        "transport_receipt_sha256",
        "receipt",
    }
    for index, (record, stage) in enumerate(
        zip(records, successful_stages, strict=False),
        start=1,
    ):
        if not isinstance(record, dict) or set(record) != expected_record_keys:
            errors.append(f"transport receipt bundle record {index} is invalid")
            continue
        if (
            record.get("sequence") != stage.get("sequence")
            or record.get("stage") != stage.get("stage")
            or record.get("role") != stage.get("role")
        ):
            errors.append(f"transport receipt bundle record {index} stage identity is invalid")
        recorded_sha256 = record.get("transport_receipt_sha256")
        if (
            not _is_sha256(recorded_sha256)
            or recorded_sha256 != stage.get("transport_receipt_sha256")
            or recorded_sha256 in seen_receipts
        ):
            errors.append(f"transport receipt bundle record {index} hash binding is invalid")
        elif isinstance(recorded_sha256, str):
            seen_receipts.add(recorded_sha256)

        receipt = record.get("receipt")
        if not isinstance(receipt, dict) or set(receipt) != _TRANSPORT_RECEIPT_KEYS:
            errors.append(f"transport receipt bundle record {index} preimage is invalid")
            continue
        if receipt.get("schema") != OPENRESPONSES_TRANSPORT_RECEIPT_SCHEMA:
            errors.append(f"transport receipt bundle record {index} schema is invalid")
        for field_name in (
            "request_sha256",
            "prompt_template_sha256",
            "session_id_sha256",
            "attestation_receipt_sha256",
            "audit_receipt_sha256",
            "openresponses_response_id_sha256",
            "payload_sha256",
        ):
            if not _is_sha256(receipt.get(field_name)):
                errors.append(
                    f"transport receipt bundle record {index} requires {field_name}"
                )
        for field_name in ("request_sha256", "session_id_sha256", "payload_sha256"):
            if receipt.get(field_name) != stage.get(field_name):
                errors.append(
                    f"transport receipt bundle record {index} {field_name} does not match"
                )
        evidence = receipt.get("evidence")
        if not _valid_transport_evidence(evidence):
            errors.append(f"transport receipt bundle record {index} evidence is invalid")
        elif baseline_evidence is None:
            baseline_evidence = evidence
        elif evidence != baseline_evidence:
            errors.append("transport receipt bundle evidence changed between stages")
        try:
            actual_sha256 = canonical_json_sha256(receipt)
        except Exception:
            actual_sha256 = None
        if actual_sha256 != recorded_sha256:
            errors.append(f"transport receipt bundle record {index} preimage hash does not match")

    try:
        serialized = json.dumps(
            bundle,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        errors.append("transport receipt bundle is not canonical JSON")
    else:
        forbidden_fragments = (
            "http://",
            "https://",
            "authorization",
            "signature=",
            "key-pair-id=",
            "input_image",
            "input_text",
        )
        lowered = serialized.casefold()
        if any(fragment in lowered for fragment in forbidden_fragments):
            errors.append("transport receipt bundle exposes forbidden content")
    return list(dict.fromkeys(errors))


def build_phase8_openresponses_transport_receipt_bundle(
    records: Sequence[Mapping[str, Any]],
    *,
    controller_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a deterministic sidecar from successful transport preimages."""

    try:
        retained_records = [
            {
                "sequence": index,
                "stage": record.get("stage"),
                "role": record.get("role"),
                "transport_receipt_sha256": canonical_json_sha256(record.get("receipt")),
                "receipt": deepcopy(record.get("receipt")),
            }
            for index, record in enumerate(records, start=1)
        ]
        bundle = {
            "schema": OPENRESPONSES_TRANSPORT_RECEIPT_BUNDLE_SCHEMA,
            "run_id": controller_receipt.get("run_id"),
            "evidence_manifest_sha256": controller_receipt.get("evidence_manifest_sha256"),
            "controller_receipt_canonical_json_sha256": canonical_json_sha256(
                controller_receipt
            ),
            "records": retained_records,
        }
    except Exception:
        raise Phase8OpenResponsesTransportError("TRANSPORT_RECEIPT_BUNDLE_INVALID") from None
    if validate_phase8_openresponses_transport_receipt_bundle(
        bundle,
        controller_receipt=controller_receipt,
    ):
        raise Phase8OpenResponsesTransportError("TRANSPORT_RECEIPT_BUNDLE_INVALID")
    return bundle


class OpenClawGatewayNoToolSessionGuard:
    """Use OpenClaw Gateway RPCs to attest effective tools and audit activity."""

    def __init__(
        self,
        *,
        gateway_rpc: GatewayRpc,
        provider: str,
        agent_models: dict[str, str],
        policy_revision_sha256: str,
    ) -> None:
        if not _is_sha256(policy_revision_sha256):
            raise Phase8OpenResponsesTransportError("GUARD_POLICY_REVISION_INVALID")
        if not isinstance(provider, str) or not provider.strip():
            raise Phase8OpenResponsesTransportError("GUARD_MODEL_POLICY_INVALID")
        if len(agent_models) != len(_ALLOWED_ROLES) or any(
            not _is_agent_id(key) for key in agent_models
        ) or any(
            not isinstance(value, str) or not value.strip() for value in agent_models.values()
        ):
            raise Phase8OpenResponsesTransportError("GUARD_MODEL_POLICY_INVALID")
        self._gateway_rpc = gateway_rpc
        self._provider = provider.strip()
        self._agent_models = {key: value.strip() for key, value in agent_models.items()}
        self._policy_revision_sha256 = policy_revision_sha256.upper()

    def attest(
        self,
        *,
        agent_id: str,
        session_key: str,
        provider: str,
        model: str,
    ) -> NoToolSessionAttestation:
        if (
            provider != self._provider
            or agent_id not in self._agent_models
            or model != self._agent_models[agent_id]
        ):
            raise Phase8OpenResponsesTransportError("TOOL_ATTESTATION_MODEL_MISMATCH")
        try:
            existing = self._gateway_rpc("sessions.describe", {"key": session_key})
            if not isinstance(existing, dict) or "session" not in existing:
                raise Phase8OpenResponsesTransportError(
                    "TOOL_ATTESTATION_SESSION_INVALID"
                )
            if existing["session"] is not None:
                raise Phase8OpenResponsesTransportError(
                    "TOOL_ATTESTATION_SESSION_EXISTS"
                )
            created = self._gateway_rpc(
                "sessions.create",
                {
                    "key": session_key,
                    "agentId": agent_id,
                    "model": f"{self._provider}/{self._agent_models[agent_id]}",
                },
            )
            if (
                not isinstance(created, dict)
                or created.get("ok") is not True
                or created.get("key") != session_key
                or not isinstance(created.get("sessionId"), str)
                or not created["sessionId"].strip()
                or not isinstance(created.get("entry"), dict)
                or created["entry"].get("sessionId") != created["sessionId"]
                or created.get("runStarted") is not False
                or "runError" in created
                or "worktree" in created
            ):
                raise Phase8OpenResponsesTransportError(
                    "TOOL_ATTESTATION_SESSION_INVALID"
                )
            described = self._gateway_rpc("sessions.describe", {"key": session_key})
            session = described.get("session") if isinstance(described, dict) else None
            if (
                not isinstance(session, dict)
                or session.get("key") != session_key
                or session.get("sessionId") != created["sessionId"]
                or session.get("modelProvider") != self._provider
                or session.get("model") != self._agent_models[agent_id]
            ):
                raise Phase8OpenResponsesTransportError(
                    "TOOL_ATTESTATION_MODEL_MISMATCH"
                )
            result = self._gateway_rpc(
                "tools.effective",
                {"sessionKey": session_key, "agentId": agent_id},
            )
            tools = _effective_tool_names(result)
            receipt_sha256 = canonical_json_sha256(
                {
                    "methods": [
                        "sessions.describe",
                        "sessions.create",
                        "sessions.describe",
                        "tools.effective",
                    ],
                    "session_id_sha256": _sha256_text(session_key),
                    "existing": existing,
                    "created": created,
                    "described": described,
                    "result": result,
                }
            )
        except Phase8OpenResponsesTransportError:
            raise
        except Exception:
            raise Phase8OpenResponsesTransportError("TOOL_ATTESTATION_UNAVAILABLE") from None
        return NoToolSessionAttestation(
            agent_id=agent_id,
            session_id_sha256=_sha256_text(session_key),
            provider=self._provider,
            model=self._agent_models[agent_id],
            effective_tools=tools,
            receipt_sha256=receipt_sha256,
            policy_revision_sha256=self._policy_revision_sha256,
        )

    def audit(
        self,
        *,
        agent_id: str,
        session_key: str,
        after_ms: int,
    ) -> NoToolSessionAudit:
        params = {
            "sessionKey": session_key,
            "agentId": agent_id,
            "kind": "tool_action",
            "after": after_ms,
            "limit": 100,
        }
        method = "audit.activity.list"
        try:
            try:
                result = self._gateway_rpc(method, params)
            except Exception:
                method = "audit.list"
                result = self._gateway_rpc(method, params)
        except Exception:
            raise Phase8OpenResponsesTransportError("TOOL_AUDIT_UNAVAILABLE") from None
        if not isinstance(result, dict) or not isinstance(result.get("events"), list):
            raise Phase8OpenResponsesTransportError("TOOL_AUDIT_INVALID")
        names: set[str] = set()
        for event in result["events"]:
            if not isinstance(event, dict):
                raise Phase8OpenResponsesTransportError("TOOL_AUDIT_INVALID")
            value = event.get("toolName") or event.get("tool") or event.get("action")
            names.add(str(value or "unknown").strip() or "unknown")
        return NoToolSessionAudit(
            agent_id=agent_id,
            session_id_sha256=_sha256_text(session_key),
            tool_calls=tuple(sorted(names)),
            receipt_sha256=canonical_json_sha256(
                {
                    "method": method,
                    "session_id_sha256": _sha256_text(session_key),
                    "result": result,
                }
            ),
        )


def _openresponses_endpoint(base_url: str) -> str:
    try:
        parts = urlsplit(base_url.strip())
        host = parts.hostname
        address = ipaddress.ip_address(host) if host else None
    except ValueError:
        raise Phase8OpenResponsesTransportError("GATEWAY_URL_FORBIDDEN") from None
    if (
        parts.scheme not in {"http", "https"}
        or address is None
        or not address.is_loopback
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or parts.path not in {"", "/", "/v1", "/v1/"}
    ):
        raise Phase8OpenResponsesTransportError("GATEWAY_URL_FORBIDDEN")
    try:
        port = parts.port
    except ValueError:
        raise Phase8OpenResponsesTransportError("GATEWAY_URL_FORBIDDEN") from None
    netloc = f"[{host}]" if address.version == 6 else str(host)
    if port is not None:
        netloc += f":{port}"
    return urlunsplit((parts.scheme, netloc, "/v1/responses", "", ""))


def _expected_role(stage: str) -> str | None:
    if stage in {"blind_inventory", "blind_inventory_retry"} or stage.startswith(
        "conditioned_validator_"
    ):
        return "cf-validator"
    if stage == "physical_proposal" or stage.startswith(
        ("physical_structural_retry_", "physical_correction_")
    ):
        return "cf-physical-model"
    return None


class Phase8OpenResponsesTransport:
    """Invoke one image-bound OpenResponses turn behind a no-tool guard."""

    def __init__(
        self,
        *,
        client: httpx.Client,
        base_url: str,
        token_provider: Callable[[], str],
        evidence_packet: RetainedVisualEvidencePacket,
        evidence_packet_verifier: Callable[[RetainedVisualEvidencePacket], None],
        session_guard: NoToolSessionGuard,
        runtime_agent_ids: Mapping[str, str],
        transport_receipt_sink: Callable[[dict[str, Any]], None] | None = None,
        prompt_renderer: Phase8VisualPromptRenderer | None = None,
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        self._client = client
        self._endpoint = _openresponses_endpoint(base_url)
        self._token_provider = token_provider
        self._packet = evidence_packet
        if not callable(evidence_packet_verifier):
            raise Phase8OpenResponsesTransportError("EVIDENCE_PACKET_VERIFIER_INVALID")
        self._evidence_packet_verifier = evidence_packet_verifier
        self._guard = session_guard
        selected_agent_ids = dict(runtime_agent_ids)
        if (
            set(selected_agent_ids) != _ALLOWED_ROLES
            or len(set(selected_agent_ids.values())) != len(_ALLOWED_ROLES)
            or any(not _is_agent_id(value) for value in selected_agent_ids.values())
        ):
            raise Phase8OpenResponsesTransportError("RUNTIME_AGENT_POLICY_INVALID")
        self._runtime_agent_ids = selected_agent_ids
        if transport_receipt_sink is not None and not callable(transport_receipt_sink):
            raise Phase8OpenResponsesTransportError("TRANSPORT_RECEIPT_SINK_INVALID")
        self._transport_receipt_sink = transport_receipt_sink
        self._renderer = prompt_renderer or Phase8VisualPromptRenderer()
        self._clock_ms = clock_ms or (lambda: int(time.time() * 1000))

    def invoke(
        self,
        *,
        role: str,
        stage: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        profile = self._validate_request(role=role, stage=stage, request=request)
        rendered = self._renderer.render(role=role, stage=stage, request=request)
        profile_field = prompt_profile_field(stage)
        if rendered.template_sha256.upper() != str(profile[profile_field]).upper():
            raise Phase8OpenResponsesTransportError("PROMPT_PROFILE_MISMATCH")

        attestation_receipts = self._attestation_receipts(request)
        try:
            self._evidence_packet_verifier(self._packet)
        except Exception:
            raise Phase8OpenResponsesTransportError(
                "EVIDENCE_ATTESTATION_REVALIDATION_FAILED"
            ) from None
        content, byte_receipts = self._image_content(
            request,
            attestation_receipts=attestation_receipts,
        )
        runtime_agent_id = self._runtime_agent_ids[role]
        session_key = self._session_key(
            agent_id=runtime_agent_id,
            stage=stage,
            request=request,
        )
        session_id_sha256 = _sha256_text(session_key)
        expected_model = (
            profile["validator_model"] if role == "cf-validator" else profile["physical_model"]
        )
        try:
            attestation = self._guard.attest(
                agent_id=runtime_agent_id,
                session_key=session_key,
                provider=profile["provider"],
                model=expected_model,
            )
        except Phase8OpenResponsesTransportError:
            raise
        except Exception:
            raise Phase8OpenResponsesTransportError("TOOL_ATTESTATION_UNAVAILABLE") from None
        self._validate_attestation(
            attestation,
            agent_id=runtime_agent_id,
            provider=profile["provider"],
            model=expected_model,
            session_id_sha256=session_id_sha256,
            runtime_policy_sha256=profile["runtime_policy_sha256"],
        )

        body = {
            "model": "openclaw",
            "stream": False,
            "tools": [],
            "tool_choice": "none",
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": rendered.text},
                        *content,
                    ],
                }
            ],
            "max_output_tokens": _MAX_OUTPUT_TOKENS,
        }
        try:
            encoded_body = json.dumps(
                body,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError):
            raise Phase8OpenResponsesTransportError("REQUEST_SERIALIZATION_FAILED") from None
        if len(encoded_body) > _MAX_REQUEST_BYTES:
            raise Phase8OpenResponsesTransportError("REQUEST_BODY_TOO_LARGE")

        try:
            token = self._token_provider()
        except Exception:
            raise Phase8OpenResponsesTransportError("GATEWAY_TOKEN_UNAVAILABLE") from None
        if not isinstance(token, str) or not token.strip():
            raise Phase8OpenResponsesTransportError("GATEWAY_TOKEN_UNAVAILABLE")

        started_at_ms = self._clock_ms()
        response: httpx.Response | None = None
        request_error: Phase8OpenResponsesTransportError | None = None
        try:
            response = self._client.post(
                self._endpoint,
                content=encoded_body,
                headers={
                    "Authorization": f"Bearer {token.strip()}",
                    "Content-Type": "application/json",
                    "x-openclaw-agent-id": runtime_agent_id,
                    "x-openclaw-session-key": session_key,
                },
                follow_redirects=False,
            )
        except httpx.TimeoutException:
            request_error = Phase8OpenResponsesTransportError("GATEWAY_TIMEOUT")
        except httpx.HTTPError:
            request_error = Phase8OpenResponsesTransportError("GATEWAY_REQUEST_FAILED")
        except Exception:
            request_error = Phase8OpenResponsesTransportError("GATEWAY_REQUEST_FAILED")
        finally:
            del token

        audit = self._audit(
            agent_id=runtime_agent_id,
            session_key=session_key,
            session_id_sha256=session_id_sha256,
            after_ms=started_at_ms,
        )
        if audit.tool_calls:
            raise Phase8OpenResponsesTransportError("SERVER_TOOL_ACTION_DETECTED")
        if request_error is not None:
            raise request_error
        if response is None:
            raise Phase8OpenResponsesTransportError("GATEWAY_REQUEST_FAILED")
        payload, response_id = self._parse_response(response)

        receipt = {
            "schema": OPENRESPONSES_TRANSPORT_RECEIPT_SCHEMA,
            "request_sha256": canonical_json_sha256(request),
            "prompt_template_sha256": rendered.template_sha256,
            "session_id_sha256": session_id_sha256,
            "attestation_receipt_sha256": attestation.receipt_sha256,
            "audit_receipt_sha256": audit.receipt_sha256,
            "evidence": byte_receipts,
            "openresponses_response_id_sha256": _sha256_text(response_id),
            "payload_sha256": canonical_json_sha256(payload),
        }
        receipt_sha256 = canonical_json_sha256(receipt)
        if self._transport_receipt_sink is not None:
            try:
                self._transport_receipt_sink(
                    deepcopy({"stage": stage, "role": role, "receipt": receipt})
                )
            except Exception:
                raise Phase8OpenResponsesTransportError(
                    "TRANSPORT_RECEIPT_RETENTION_FAILED"
                ) from None
        return {
            "schema": VISUAL_INFERENCE_RESPONSE_SCHEMA,
            "agent_id": role,
            "provider": attestation.provider,
            "model": attestation.model,
            "session_id_sha256": session_id_sha256,
            "transport_receipt_sha256": receipt_sha256,
            "tool_calls": [],
            "payload": payload,
        }

    def _validate_request(
        self,
        *,
        role: str,
        stage: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        if role not in _ALLOWED_ROLES or _expected_role(stage) != role:
            raise Phase8OpenResponsesTransportError("STAGE_ROLE_FORBIDDEN")
        if not isinstance(request, dict) or set(request) != _REQUEST_KEYS:
            raise Phase8OpenResponsesTransportError("CONTROLLER_REQUEST_INVALID")
        if (
            request.get("schema") != VISUAL_INFERENCE_REQUEST_SCHEMA
            or request.get("policy_version") != VISUAL_PROPOSAL_POLICY_VERSION
            or request.get("human_reference_visible") is not False
            or request.get("allowed_tools") != []
        ):
            raise Phase8OpenResponsesTransportError("CONTROLLER_REQUEST_INVALID")
        for name in ("run_id", "estimate_id", "defect_reference"):
            if not isinstance(request.get(name), str) or not request[name].strip():
                raise Phase8OpenResponsesTransportError("CONTROLLER_REQUEST_INVALID")
        manifest = request.get("evidence_manifest")
        manifest_errors = validate_visual_evidence_manifest(
            manifest,
            estimate_id=request["estimate_id"],
        )
        if (
            manifest_errors
            or canonical_json_sha256(manifest) != request.get("evidence_manifest_sha256")
            or manifest != self._packet.manifest
            or self._packet.manifest_sha256 != request.get("evidence_manifest_sha256")
            or manifest.get("defect_reference") != request["defect_reference"]
        ):
            raise Phase8OpenResponsesTransportError("EVIDENCE_PACKET_MISMATCH")
        profile = request.get("inference_profile")
        if (
            not isinstance(profile, dict)
            or validate_visual_inference_profile(profile)
            or canonical_json_sha256(profile) != request.get("inference_profile_sha256")
        ):
            raise Phase8OpenResponsesTransportError("INFERENCE_PROFILE_MISMATCH")
        try:
            canonical_json_sha256(request.get("stage_input"))
        except Exception:
            raise Phase8OpenResponsesTransportError("STAGE_INPUT_INVALID") from None
        return profile

    def _image_content(
        self,
        request: dict[str, Any],
        *,
        attestation_receipts: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        files = self._packet.files
        artifacts = request["evidence_manifest"]["artifacts"]
        if (
            not files
            or len(files) != len(artifacts)
            or len(files) != len(attestation_receipts)
            or len(files) > _MAX_IMAGE_COUNT
        ):
            raise Phase8OpenResponsesTransportError("EVIDENCE_FILE_COUNT_INVALID")
        content: list[dict[str, Any]] = []
        receipts: list[dict[str, Any]] = []
        total_bytes = 0
        for item, attestation_receipt in zip(files, attestation_receipts, strict=True):
            try:
                if not item.path.is_file():
                    raise OSError
                raw = item.path.read_bytes()
            except OSError:
                raise Phase8OpenResponsesTransportError("EVIDENCE_FILE_UNAVAILABLE") from None
            actual_sha256 = hashlib.sha256(raw).hexdigest()
            if (
                len(raw) != item.size_bytes
                or actual_sha256.casefold() != item.sha256.casefold()
            ):
                raise Phase8OpenResponsesTransportError("EVIDENCE_FILE_CHANGED")
            if len(raw) > _MAX_IMAGE_BYTES:
                raise Phase8OpenResponsesTransportError("EVIDENCE_FILE_TOO_LARGE")
            total_bytes += len(raw)
            if total_bytes > _MAX_RAW_IMAGE_BYTES:
                raise Phase8OpenResponsesTransportError("EVIDENCE_PACKET_TOO_LARGE")
            content.append(
                {
                    "type": "input_image",
                    "source": {
                        "type": "base64",
                        "media_type": item.media_type,
                        "data": base64.b64encode(raw).decode("ascii"),
                    },
                }
            )
            receipts.append(
                attestation_receipt
                | {
                    "sha256": actual_sha256.upper(),
                    "size_bytes": len(raw),
                    "media_type": item.media_type,
                }
            )
        return content, receipts

    def _attestation_receipts(
        self,
        request: dict[str, Any],
    ) -> list[dict[str, Any]]:
        files = self._packet.files
        artifacts = request["evidence_manifest"]["artifacts"]
        if not files or len(files) != len(artifacts) or len(files) > _MAX_IMAGE_COUNT:
            raise Phase8OpenResponsesTransportError("EVIDENCE_FILE_COUNT_INVALID")
        receipts: list[dict[str, Any]] = []
        for item, artifact in zip(files, artifacts, strict=True):
            if (
                item.evidence_id != artifact.get("evidence_id")
                or not _is_sha256(item.sha256)
                or item.sha256.casefold() != str(artifact.get("sha256") or "").casefold()
                or isinstance(item.size_bytes, bool)
                or not isinstance(item.size_bytes, int)
                or item.size_bytes != artifact.get("size_bytes")
                or item.media_type != artifact.get("media_type")
                or item.media_type not in _ALLOWED_IMAGE_MIMES
            ):
                raise Phase8OpenResponsesTransportError("EVIDENCE_FILE_METADATA_MISMATCH")
            token = item.verification_token
            if not self._token_matches_file(token, item):
                raise Phase8OpenResponsesTransportError("EVIDENCE_ATTESTATION_INVALID")
            receipts.append(
                {
                    "evidence_id": item.evidence_id,
                    "stored_file_id": token.stored_file_id,
                    "malware_scan_attestation_id": token.scan_attestation_id,
                    "malware_scan_attestation_receipt_sha256": (
                        token.scan_attestation_sha256.upper()
                    ),
                    "malware_scan_sequence": token.scan_sequence,
                }
            )
        return receipts

    @staticmethod
    def _token_matches_file(token: object, item: RetainedVisualEvidenceFile) -> bool:
        return (
            isinstance(token, VerifiedStoredFile)
            and _is_canonical_uuid(token.stored_file_id)
            and isinstance(token.path, Path)
            and token.path == item.path
            and _is_sha256(token.content_sha256)
            and token.content_sha256.casefold() == item.sha256.casefold()
            and isinstance(token.content_size_bytes, int)
            and not isinstance(token.content_size_bytes, bool)
            and token.content_size_bytes == item.size_bytes
            and _normalised_media_type(token.media_type) == item.media_type
            and token.purpose == "technical_evidence"
            and _is_canonical_uuid(token.scan_attestation_id)
            and _is_sha256(token.scan_attestation_sha256)
            and isinstance(token.scan_sequence, int)
            and not isinstance(token.scan_sequence, bool)
            and token.scan_sequence >= 1
        )

    @staticmethod
    def _session_key(
        *,
        agent_id: str,
        stage: str,
        request: dict[str, Any],
    ) -> str:
        # Recovery reconstructs this established identity from the retained
        # controller receipt. Malware-scan lineage is instead committed by the
        # v2 transport receipt and revalidated before every attempted turn.
        identity = canonical_json_sha256(
            {
                "run_id": request["run_id"],
                "stage": stage,
                "request_sha256": canonical_json_sha256(request),
            }
        )
        return f"agent:{agent_id}:classifire-phase8-{identity[:32].lower()}"

    @staticmethod
    def _validate_attestation(
        attestation: Any,
        *,
        agent_id: str,
        provider: str,
        model: str,
        session_id_sha256: str,
        runtime_policy_sha256: str,
    ) -> None:
        if not isinstance(attestation, NoToolSessionAttestation):
            raise Phase8OpenResponsesTransportError("TOOL_ATTESTATION_INVALID")
        if (
            attestation.agent_id != agent_id
            or attestation.provider != provider
            or attestation.model != model
            or attestation.session_id_sha256.upper() != session_id_sha256
            or attestation.policy_revision_sha256.upper() != runtime_policy_sha256.upper()
            or not _is_sha256(attestation.receipt_sha256)
        ):
            raise Phase8OpenResponsesTransportError("TOOL_ATTESTATION_MISMATCH")
        if attestation.effective_tools:
            raise Phase8OpenResponsesTransportError("SERVER_TOOLS_NOT_EMPTY")

    def _audit(
        self,
        *,
        agent_id: str,
        session_key: str,
        session_id_sha256: str,
        after_ms: int,
    ) -> NoToolSessionAudit:
        try:
            audit = self._guard.audit(
                agent_id=agent_id,
                session_key=session_key,
                after_ms=after_ms,
            )
        except Phase8OpenResponsesTransportError:
            raise
        except Exception:
            raise Phase8OpenResponsesTransportError("TOOL_AUDIT_UNAVAILABLE") from None
        if not isinstance(audit, NoToolSessionAudit):
            raise Phase8OpenResponsesTransportError("TOOL_AUDIT_INVALID")
        if (
            audit.agent_id != agent_id
            or audit.session_id_sha256.upper() != session_id_sha256
            or not _is_sha256(audit.receipt_sha256)
        ):
            raise Phase8OpenResponsesTransportError("TOOL_AUDIT_MISMATCH")
        return audit

    @staticmethod
    def _parse_response(response: httpx.Response) -> tuple[dict[str, Any], str]:
        if response.status_code < 200 or response.status_code >= 300:
            raise Phase8OpenResponsesTransportError("GATEWAY_STATUS_REJECTED")
        try:
            value = response.json()
        except ValueError:
            raise Phase8OpenResponsesTransportError("GATEWAY_RESPONSE_NOT_JSON") from None
        if not isinstance(value, dict):
            raise Phase8OpenResponsesTransportError("GATEWAY_RESPONSE_INVALID")
        response_id = value.get("id")
        if (
            not isinstance(response_id, str)
            or not response_id.strip()
            or value.get("status") != "completed"
            or not isinstance(value.get("output"), list)
        ):
            raise Phase8OpenResponsesTransportError("GATEWAY_RESPONSE_INVALID")
        texts: list[str] = []
        for item in value["output"]:
            if not isinstance(item, dict):
                raise Phase8OpenResponsesTransportError("GATEWAY_RESPONSE_INVALID")
            item_type = item.get("type")
            if item_type == "function_call":
                raise Phase8OpenResponsesTransportError("CLIENT_TOOL_CALL_DETECTED")
            if item_type == "reasoning":
                continue
            if item_type != "message" or item.get("role") != "assistant":
                raise Phase8OpenResponsesTransportError("GATEWAY_RESPONSE_INVALID")
            parts = item.get("content")
            if not isinstance(parts, list):
                raise Phase8OpenResponsesTransportError("GATEWAY_RESPONSE_INVALID")
            for part in parts:
                if not isinstance(part, dict):
                    raise Phase8OpenResponsesTransportError("GATEWAY_RESPONSE_INVALID")
                if part.get("type") != "output_text" or not isinstance(part.get("text"), str):
                    raise Phase8OpenResponsesTransportError("GATEWAY_RESPONSE_INVALID")
                if part["text"].strip():
                    texts.append(part["text"].strip())
        if len(texts) != 1:
            raise Phase8OpenResponsesTransportError("ASSISTANT_OUTPUT_COUNT_INVALID")
        try:
            payload = json.loads(
                texts[0],
                object_pairs_hook=_reject_duplicate_json_keys,
                parse_constant=_reject_json_constant,
            )
        except (json.JSONDecodeError, ValueError):
            raise Phase8OpenResponsesTransportError("ASSISTANT_OUTPUT_NOT_JSON") from None
        if not isinstance(payload, dict):
            raise Phase8OpenResponsesTransportError("ASSISTANT_OUTPUT_INVALID")
        return payload, response_id.strip()


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"non-standard JSON constant: {value}")


__all__ = [
    "GatewayRpc",
    "NoToolSessionAttestation",
    "NoToolSessionAudit",
    "NoToolSessionGuard",
    "OPENRESPONSES_TRANSPORT_RECEIPT_BUNDLE_SCHEMA",
    "OPENRESPONSES_TRANSPORT_RECEIPT_SCHEMA",
    "OpenClawGatewayNoToolSessionGuard",
    "Phase8OpenResponsesTransport",
    "Phase8OpenResponsesTransportError",
    "build_phase8_openresponses_transport_receipt_bundle",
    "validate_phase8_openresponses_transport_receipt_bundle",
]
