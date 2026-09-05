from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest

from classifire.services.canonical_submission_state import InitialSubmissionState
from classifire.services.phase8_openresponses_transport import (
    ExecutionCompletionContext,
    ExecutionCompletionEvidence,
    NoToolSessionAttestation,
    NoToolSessionAudit,
    OpenClawGatewayNoToolSessionGuard,
    Phase8OpenResponsesTransport,
    Phase8OpenResponsesTransportError,
    validate_execution_completion,
)
from classifire.services.phase8_property_assessments import PROPERTY_ASSESSMENT_SCHEMA
from classifire.services.phase8_visual_evidence import (
    RetainedVisualEvidenceFile,
    RetainedVisualEvidencePacket,
)
from classifire.services.phase8_visual_prompts import (
    LEGACY_BLIND_PROMPT_TEMPLATE,
    LEGACY_CORRECTION_PROMPT_TEMPLATE,
    LEGACY_PHYSICAL_PROMPT_TEMPLATE,
    LEGACY_VALIDATOR_PROMPT_TEMPLATE,
    VISUAL_RUNTIME_POLICY,
    Phase8VisualPromptRenderer,
    RenderedVisualPrompt,
    build_visual_inference_profile,
)
from classifire.services.phase8_visual_proposal import (
    VISUAL_EVIDENCE_MANIFEST_SCHEMA,
    VISUAL_INFERENCE_REQUEST_SCHEMA,
    VISUAL_PROPOSAL_APPROVED,
    VISUAL_PROPOSAL_POLICY_VERSION,
    ProposalOnlyVisualController,
    canonical_json_sha256,
    validate_visual_inference_response,
)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest().upper()


def _packet(
    tmp_path: Path,
    *,
    data: bytes = b"synthetic-image-bytes",
) -> RetainedVisualEvidencePacket:
    path = tmp_path / "evidence.png"
    path.write_bytes(data)
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
                path=path,
                sha256=digest,
                size_bytes=len(data),
                media_type="image/png",
            ),
        ),
    )


def _profile() -> dict[str, Any]:
    return build_visual_inference_profile(
        implementation_revision="a" * 40,
        provider="test-provider",
        physical_model="physical-test-model",
        validator_model="validator-test-model",
    )


def _request(packet: RetainedVisualEvidencePacket, *, stage_input=None) -> dict[str, Any]:
    profile = _profile()
    return {
        "schema": VISUAL_INFERENCE_REQUEST_SCHEMA,
        "policy_version": VISUAL_PROPOSAL_POLICY_VERSION,
        "run_id": "RUN-001",
        "estimate_id": "EST-001",
        "defect_reference": "D-001",
        "evidence_manifest": deepcopy(packet.manifest),
        "evidence_manifest_sha256": packet.manifest_sha256,
        "inference_profile": profile,
        "inference_profile_sha256": canonical_json_sha256(profile),
        "human_reference_visible": False,
        "allowed_tools": [],
        "stage_input": stage_input or {},
    }


def _openresponses(payload: dict[str, Any], *, response_id: str = "resp-001") -> dict[str, Any]:
    return {
        "id": response_id,
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(payload, separators=(",", ":")),
                    }
                ],
            }
        ],
    }


class FakeGuard:
    def __init__(
        self,
        *,
        effective_tools: tuple[str, ...] = (),
        audit_tools: tuple[str, ...] = (),
        fail_audit: bool = False,
    ) -> None:
        self.effective_tools = effective_tools
        self.audit_tools = audit_tools
        self.fail_audit = fail_audit
        self.attestations: list[dict[str, Any]] = []
        self.audits: list[dict[str, Any]] = []

    def attest(self, *, agent_id, session_key, provider, model):
        self.attestations.append(
            {
                "agent_id": agent_id,
                "session_key": session_key,
                "provider": provider,
                "model": model,
            }
        )
        return NoToolSessionAttestation(
            agent_id=agent_id,
            session_id_sha256=_sha256_text(session_key),
            provider=provider,
            model=model,
            effective_tools=self.effective_tools,
            receipt_sha256="A" * 64,
            policy_revision_sha256=_sha256_text(VISUAL_RUNTIME_POLICY),
        )

    def audit(self, *, agent_id, session_key, after_ms):
        if self.fail_audit:
            raise RuntimeError("unsafe audit detail")
        self.audits.append(
            {
                "agent_id": agent_id,
                "session_key": session_key,
                "after_ms": after_ms,
            }
        )
        return NoToolSessionAudit(
            agent_id=agent_id,
            session_id_sha256=_sha256_text(session_key),
            tool_calls=self.audit_tools,
            receipt_sha256="B" * 64,
        )


def _fake_completion(context: ExecutionCompletionContext) -> ExecutionCompletionEvidence:
    # Synthetic trusted producer; never used by application/runtime composition.
    return ExecutionCompletionEvidence(
        context_sha256=context.sha256,
        receipt_sha256="C" * 64,
        terminal_at_ms=context.started_at_ms,
        coverage_from_ms=context.started_at_ms,
        coverage_through_ms=context.observed_at_ms,
        writer_enabled=True,
        writer_healthy=True,
        pending_events=0,
        dropped_events=0,
        tool_actions=0,
    )


def _transport(
    packet: RetainedVisualEvidencePacket,
    handler,
    *,
    guard: FakeGuard | None = None,
    completion_verifier=_fake_completion,
    token_provider=lambda: "secret-token",  # noqa: B008
    runtime_agent_ids: dict[str, str] | None = None,
    prompt_renderer: object | None = None,
) -> tuple[Phase8OpenResponsesTransport, FakeGuard]:
    selected_guard = guard or FakeGuard()
    selected_runtime_agent_ids = runtime_agent_ids or {
        role: role for role in ("cf-physical-model", "cf-validator")
    }
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return (
        Phase8OpenResponsesTransport(
            client=client,
            base_url="http://127.0.0.1:18789/v1",
            token_provider=token_provider,
            evidence_packet=packet,
            session_guard=selected_guard,
            completion_verifier=completion_verifier,
            runtime_agent_ids=selected_runtime_agent_ids,
            prompt_renderer=prompt_renderer,
            clock_ms=lambda: 1234567890,
        ),
        selected_guard,
    )


def test_literal_legacy_v1_prompt_and_runtime_fingerprints_are_frozen() -> None:
    assert _sha256_text(LEGACY_BLIND_PROMPT_TEMPLATE) == (
        "D5EBEB80B3FF6F60FED3131BF136ECEBC65E20C30A674C807EC9FA9DB5F67785"
    )
    assert _sha256_text(LEGACY_PHYSICAL_PROMPT_TEMPLATE) == (
        "22E3E5F3F59585992162D3FC03B3AF8DBBF692880CD03A11CEF42EABA02A820F"
    )
    assert _sha256_text(LEGACY_VALIDATOR_PROMPT_TEMPLATE) == (
        "2987072B49A84E2AE4F91E1D3AC397CF5D1B75D2A17239FAAF5985EF207FCC5F"
    )
    assert _sha256_text(LEGACY_CORRECTION_PROMPT_TEMPLATE) == (
        "7E7BA92613EC0B776226597F595AC9CFD27D6508AED2105091909F19A35F9258"
    )
    assert _sha256_text(VISUAL_RUNTIME_POLICY) == (
        "4F7710D5005D45696DDECFC1CA75238E881EBDC401002A8D87F8D3FD164A053C"
    )


def test_mixed_policy_profile_fails_before_guard_token_or_http(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    request = _request(packet)
    request["inference_profile"]["correction_prompt_sha256"] = _sha256_text(
        LEGACY_CORRECTION_PROMPT_TEMPLATE
    )
    request["inference_profile_sha256"] = canonical_json_sha256(
        request["inference_profile"]
    )
    guard = FakeGuard()
    token_called = False

    def token_provider() -> str:
        nonlocal token_called
        token_called = True
        return "secret-token"

    def handler(_request: httpx.Request) -> httpx.Response:
        pytest.fail("HTTP must not run for a mixed policy profile")

    transport, _ = _transport(
        packet,
        handler,
        guard=guard,
        token_provider=token_provider,
    )

    with pytest.raises(Phase8OpenResponsesTransportError) as caught:
        transport.invoke(role="cf-validator", stage="blind_inventory", request=request)

    assert caught.value.code == "INFERENCE_PROFILE_MISMATCH"
    assert guard.attestations == []
    assert token_called is False


def test_renderer_cannot_claim_a_hash_for_different_prompt_bytes(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    request = _request(packet)
    guard = FakeGuard()

    class _FalseHashRenderer:
        def render(self, *, role: str, stage: str, request: dict[str, Any]):
            trusted = Phase8VisualPromptRenderer().render(
                role=role,
                stage=stage,
                request=request,
            )
            return RenderedVisualPrompt(
                text=trusted.text + "unbound instruction\n",
                template_sha256=trusted.template_sha256,
            )

    def handler(_request: httpx.Request) -> httpx.Response:
        pytest.fail("HTTP must not run for untrusted prompt bytes")

    transport, _ = _transport(
        packet,
        handler,
        guard=guard,
        prompt_renderer=_FalseHashRenderer(),
    )

    with pytest.raises(Phase8OpenResponsesTransportError) as caught:
        transport.invoke(role="cf-validator", stage="blind_inventory", request=request)

    assert caught.value.code == "PROMPT_RENDERING_MISMATCH"
    assert guard.attestations == []


def test_renderer_cannot_mutate_request_after_validation(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    request = _request(packet)
    original = deepcopy(request)
    guard = FakeGuard()

    class _MutatingRenderer:
        def render(self, *, role: str, stage: str, request: dict[str, Any]):
            request["stage_input"]["injected_after_validation"] = "untrusted instruction"
            return Phase8VisualPromptRenderer().render(
                role=role,
                stage=stage,
                request=request,
            )

    def handler(_request: httpx.Request) -> httpx.Response:
        pytest.fail("HTTP must not run for a renderer-mutated request")

    transport, _ = _transport(
        packet,
        handler,
        guard=guard,
        prompt_renderer=_MutatingRenderer(),
    )

    with pytest.raises(Phase8OpenResponsesTransportError) as caught:
        transport.invoke(role="cf-validator", stage="blind_inventory", request=request)

    assert caught.value.code == "PROMPT_RENDERING_MISMATCH"
    assert request == original
    assert guard.attestations == []


def test_profile_and_rendering_are_deterministic_and_role_bound(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    request = _request(packet)
    renderer = Phase8VisualPromptRenderer()

    first = renderer.render(role="cf-validator", stage="blind_inventory", request=request)
    second = renderer.render(role="cf-validator", stage="blind_inventory", request=request)

    assert first == second
    assert first.template_sha256 == request["inference_profile"]["blind_prompt_sha256"]
    assert "human reference" in first.text.lower()
    assert "blank (the JSON boolean true" in first.text
    assert "candidate_opening_ids, detail, and" in first.text
    assert "classification, or photo_relationship" in first.text
    assert "globally unique across candidate_openings" in first.text
    assert "do not reuse an ID in a different list" in first.text

    physical = renderer.render(role="cf-physical-model", stage="physical_proposal", request=request)
    assert physical.template_sha256 == request["inference_profile"]["physical_prompt_sha256"]
    assert "opening_type must be exactly" in physical.text
    assert "blank_opening or blank_core_hole" in physical.text

    validator = renderer.render(
        role="cf-validator", stage="conditioned_validator_0", request=request
    )
    assert validator.template_sha256 == request["inference_profile"]["validator_prompt_sha256"]
    assert "MISSED_OPENING" in validator.text
    assert "UNSUPPORTED_SIZE_OR_QUANTITY" in validator.text
    assert "DUPLICATE_OR_SAME_ITEM" in validator.text
    assert "RESOLVED_NONSTRUCTURAL" in validator.text
    assert "NOT_TOPOLOGY and RESOLVED_NONSTRUCTURAL require" in validator.text
    assert "proposal_refs to be an empty array" in validator.text

    correction = renderer.render(
        role="cf-physical-model", stage="physical_correction_1", request=request
    )
    assert correction.template_sha256 == request["inference_profile"]["correction_prompt_sha256"]
    assert "never replace a null or unknown value with a guess" in correction.text
    assert "substrate_type, substrate_plane, and orientation may change only" in correction.text
    assert "MISSED_BARRIER" in correction.text
    assert "WRONG_BARRIER_PLANE" in correction.text
    assert 'Do not make unrelated "cleanup" changes.' in correction.text
    with pytest.raises(Exception, match="INFERENCE_STAGE_ROLE_MISMATCH"):
        renderer.render(role="cf-physical-model", stage="blind_inventory", request=request)


def test_success_revalidates_bytes_and_emits_strict_no_tool_request(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_openresponses({"ok": True}))

    transport, guard = _transport(packet, handler)
    request = _request(packet)

    result = transport.invoke(role="cf-validator", stage="blind_inventory", request=request)

    assert (
        validate_visual_inference_response(
            result,
            role="cf-validator",
            profile=request["inference_profile"],
        )
        == []
    )
    assert result["payload"] == {"ok": True}
    assert captured["url"] == "http://127.0.0.1:18789/v1/responses"
    assert captured["headers"]["authorization"] == "Bearer secret-token"
    assert captured["headers"]["x-openclaw-agent-id"] == "cf-validator"
    assert captured["body"]["tools"] == []
    assert captured["body"]["tool_choice"] == "none"
    assert captured["body"]["stream"] is False
    image = captured["body"]["input"][0]["content"][1]
    assert base64_decode(image["source"]["data"]) == b"synthetic-image-bytes"
    assert len(guard.attestations) == 1
    assert len(guard.audits) == 1
    assert "secret-token" not in str(result)
    assert str(packet.files[0].path) not in str(result)


def test_logical_role_uses_dedicated_runtime_agent_identity(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json=_openresponses({"ok": True}))

    transport, guard = _transport(
        packet,
        handler,
        runtime_agent_ids={
            "cf-physical-model": "cf-phase8-visual-physical",
            "cf-validator": "cf-phase8-visual-validator",
        },
    )
    request = _request(packet)

    result = transport.invoke(
        role="cf-validator",
        stage="blind_inventory",
        request=request,
    )

    assert result["agent_id"] == "cf-validator"
    assert captured["headers"]["x-openclaw-agent-id"] == ("cf-phase8-visual-validator")
    assert guard.attestations[0]["agent_id"] == "cf-phase8-visual-validator"
    assert guard.audits[0]["agent_id"] == "cf-phase8-visual-validator"
    assert guard.attestations[0]["session_key"].startswith(
        "agent:cf-phase8-visual-validator:classifire-phase8-"
    )


@pytest.mark.parametrize(
    "runtime_agent_ids",
    [
        {"cf-validator": "cf-phase8-visual-validator"},
        {
            "cf-physical-model": "same-agent",
            "cf-validator": "same-agent",
        },
        {
            "cf-physical-model": "cf-phase8-visual-physical",
            "cf-validator": "INVALID AGENT",
        },
    ],
)
def test_invalid_runtime_agent_mapping_is_rejected(
    tmp_path: Path,
    runtime_agent_ids: dict[str, str],
) -> None:
    packet = _packet(tmp_path)
    with pytest.raises(Phase8OpenResponsesTransportError) as exc_info:
        Phase8OpenResponsesTransport(
            client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
            base_url="http://127.0.0.1:18789/v1",
            token_provider=lambda: "token",
            evidence_packet=packet,
            session_guard=FakeGuard(),
            runtime_agent_ids=runtime_agent_ids,
        )
    assert exc_info.value.code == "RUNTIME_AGENT_POLICY_INVALID"


def base64_decode(value: str) -> bytes:
    import base64

    return base64.b64decode(value)


def test_non_loopback_and_dns_gateway_names_are_rejected(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    for url in ("https://example.com/v1", "http://localhost:18789/v1"):
        with pytest.raises(Phase8OpenResponsesTransportError) as exc_info:
            Phase8OpenResponsesTransport(
                client=client,
                base_url=url,
                token_provider=lambda: "token",
                evidence_packet=packet,
                session_guard=FakeGuard(),
                runtime_agent_ids={
                    "cf-physical-model": "cf-physical-model",
                    "cf-validator": "cf-validator",
                },
            )
        assert exc_info.value.code == "GATEWAY_URL_FORBIDDEN"


def test_effective_server_tools_fail_before_token_or_http(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    counts = {"token": 0, "http": 0}

    def token_provider() -> str:
        counts["token"] += 1
        return "secret"

    def handler(request: httpx.Request) -> httpx.Response:
        counts["http"] += 1
        return httpx.Response(200, json=_openresponses({"ok": True}))

    transport, guard = _transport(
        packet,
        handler,
        guard=FakeGuard(effective_tools=("classifire_evidence_read",)),
        token_provider=token_provider,
    )
    with pytest.raises(Phase8OpenResponsesTransportError) as exc_info:
        transport.invoke(
            role="cf-validator",
            stage="blind_inventory",
            request=_request(packet),
        )

    assert exc_info.value.code == "SERVER_TOOLS_NOT_EMPTY"
    assert counts == {"token": 0, "http": 0}
    assert len(guard.attestations) == 1
    assert guard.audits == []


def test_changed_evidence_fails_before_guard_token_or_http(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    packet.files[0].path.write_bytes(b"changed")
    counts = {"token": 0, "http": 0}

    def token_provider() -> str:
        counts["token"] += 1
        return "secret"

    def handler(request: httpx.Request) -> httpx.Response:
        counts["http"] += 1
        return httpx.Response(200, json=_openresponses({"ok": True}))

    transport, guard = _transport(packet, handler, token_provider=token_provider)
    with pytest.raises(Phase8OpenResponsesTransportError) as exc_info:
        transport.invoke(
            role="cf-validator",
            stage="blind_inventory",
            request=_request(packet),
        )

    assert exc_info.value.code == "EVIDENCE_FILE_CHANGED"
    assert counts == {"token": 0, "http": 0}
    assert guard.attestations == []


def test_manifest_and_prompt_profile_tampering_fail_before_http(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    http_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal http_calls
        http_calls += 1
        return httpx.Response(200, json=_openresponses({"ok": True}))

    transport, guard = _transport(packet, handler)
    bad_manifest = _request(packet)
    bad_manifest["evidence_manifest"] = deepcopy(packet.manifest)
    bad_manifest["evidence_manifest"]["defect_reference"] = "D-OTHER"
    bad_manifest["evidence_manifest_sha256"] = canonical_json_sha256(
        bad_manifest["evidence_manifest"]
    )
    with pytest.raises(Phase8OpenResponsesTransportError) as manifest_error:
        transport.invoke(
            role="cf-validator",
            stage="blind_inventory",
            request=bad_manifest,
        )
    assert manifest_error.value.code == "EVIDENCE_PACKET_MISMATCH"

    bad_prompt = _request(packet)
    bad_prompt["inference_profile"]["blind_prompt_sha256"] = "F" * 64
    bad_prompt["inference_profile_sha256"] = canonical_json_sha256(bad_prompt["inference_profile"])
    with pytest.raises(Phase8OpenResponsesTransportError) as prompt_error:
        transport.invoke(
            role="cf-validator",
            stage="blind_inventory",
            request=bad_prompt,
        )
    assert prompt_error.value.code == "INFERENCE_PROFILE_MISMATCH"
    assert http_calls == 0
    assert guard.attestations == []


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (
            httpx.Response(302, headers={"location": "https://example.com"}),
            "GATEWAY_STATUS_REJECTED",
        ),
        (httpx.Response(200, text="not-json"), "GATEWAY_RESPONSE_NOT_JSON"),
        (
            httpx.Response(
                200,
                json={
                    "id": "resp-tool",
                    "status": "completed",
                    "output": [{"type": "function_call", "name": "unsafe"}],
                },
            ),
            "CLIENT_TOOL_CALL_DETECTED",
        ),
        (
            httpx.Response(
                200,
                json={
                    "id": "resp-multiple",
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {"type": "output_text", "text": "{}"},
                                {"type": "output_text", "text": "{}"},
                            ],
                        }
                    ],
                },
            ),
            "ASSISTANT_OUTPUT_COUNT_INVALID",
        ),
        (
            httpx.Response(200, json=_openresponses({"ok": True}) | {"status": "failed"}),
            "GATEWAY_RESPONSE_INVALID",
        ),
        (
            httpx.Response(
                200,
                json={
                    "id": "resp-duplicate-json",
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": '{"value":1,"value":2}'}],
                        }
                    ],
                },
            ),
            "ASSISTANT_OUTPUT_NOT_JSON",
        ),
        (
            httpx.Response(
                200,
                json={
                    "id": "resp-nan-json",
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": '{"value":NaN}'}],
                        }
                    ],
                },
            ),
            "ASSISTANT_OUTPUT_NOT_JSON",
        ),
    ],
)
def test_failed_or_unsafe_responses_are_audited(
    tmp_path: Path,
    response: httpx.Response,
    code: str,
) -> None:
    packet = _packet(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return response

    transport, guard = _transport(packet, handler)
    with pytest.raises(Phase8OpenResponsesTransportError) as exc_info:
        transport.invoke(
            role="cf-validator",
            stage="blind_inventory",
            request=_request(packet),
        )
    assert exc_info.value.code == code
    assert len(guard.audits) == 1


def test_post_turn_tool_action_and_unavailable_audit_fail_closed(tmp_path: Path) -> None:
    packet = _packet(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openresponses({"ok": True}))

    transport, _ = _transport(packet, handler, guard=FakeGuard(audit_tools=("shell",)))
    with pytest.raises(Phase8OpenResponsesTransportError) as tool_error:
        transport.invoke(
            role="cf-validator",
            stage="blind_inventory",
            request=_request(packet),
        )
    assert tool_error.value.code == "SERVER_TOOL_ACTION_DETECTED"

    transport, _ = _transport(packet, handler, guard=FakeGuard(fail_audit=True))
    with pytest.raises(Phase8OpenResponsesTransportError) as audit_error:
        transport.invoke(
            role="cf-validator",
            stage="blind_inventory",
            request=_request(packet),
        )
    assert audit_error.value.code == "TOOL_AUDIT_UNAVAILABLE"
    assert "unsafe audit detail" not in str(audit_error.value)


def test_gateway_transport_exception_is_still_audited(tmp_path: Path) -> None:
    packet = _packet(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("secret endpoint detail", request=request)

    transport, guard = _transport(packet, handler)
    with pytest.raises(Phase8OpenResponsesTransportError) as exc_info:
        transport.invoke(
            role="cf-validator",
            stage="blind_inventory",
            request=_request(packet),
        )
    assert exc_info.value.code == "GATEWAY_REQUEST_FAILED"
    assert "secret endpoint detail" not in str(exc_info.value)
    assert len(guard.audits) == 1


def test_unexpected_client_exception_is_sanitized_and_audited(tmp_path: Path) -> None:
    packet = _packet(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("secret client detail")

    transport, guard = _transport(packet, handler)
    with pytest.raises(Phase8OpenResponsesTransportError) as exc_info:
        transport.invoke(
            role="cf-validator",
            stage="blind_inventory",
            request=_request(packet),
        )
    assert exc_info.value.code == "GATEWAY_REQUEST_FAILED"
    assert "secret client detail" not in str(exc_info.value)
    assert len(guard.audits) == 1


def test_concrete_gateway_guard_proves_empty_tools_and_records_audit() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    session_created = False

    def rpc(method: str, params: dict[str, Any]):
        nonlocal session_created
        calls.append((method, params))
        if method == "sessions.create":
            session_created = True
            return {
                "ok": True,
                "key": params["key"],
                "sessionId": "session-id",
                "entry": {"sessionId": "session-id"},
                "runStarted": False,
            }
        if method == "sessions.describe":
            if not session_created:
                return {"session": None}
            return {
                "session": {
                    "key": params["key"],
                    "sessionId": "session-id",
                    "modelProvider": "provider",
                    "model": "model",
                }
            }
        if method == "tools.effective":
            return {"groups": [{"name": "builtins", "tools": []}]}
        return {"events": []}

    guard = OpenClawGatewayNoToolSessionGuard(
        gateway_rpc=rpc,
        provider="provider",
        agent_models={
            "cf-physical-model": "physical-model",
            "cf-validator": "model",
        },
        policy_revision_sha256="C" * 64,
    )
    attestation = guard.attest(
        agent_id="cf-validator",
        session_key="agent:cf-validator:test",
        provider="provider",
        model="model",
    )
    audit = guard.audit(
        agent_id="cf-validator",
        session_key="agent:cf-validator:test",
        after_ms=123,
    )

    assert attestation.effective_tools == ()
    assert audit.tool_calls == ()
    assert [method for method, _params in calls] == [
        "sessions.describe",
        "sessions.create",
        "sessions.describe",
        "tools.effective",
        "audit.activity.list",
    ]
    assert calls[0][1] == {"key": "agent:cf-validator:test"}
    assert calls[1][1] == {
        "key": "agent:cf-validator:test",
        "agentId": "cf-validator",
        "model": "provider/model",
    }
    assert calls[2][1] == {"key": "agent:cf-validator:test"}
    assert calls[3][1] == {
        "sessionKey": "agent:cf-validator:test",
        "agentId": "cf-validator",
    }
    assert all(
        _is_safe_receipt(value) for value in (attestation.receipt_sha256, audit.receipt_sha256)
    )
    with pytest.raises(Phase8OpenResponsesTransportError) as exc_info:
        guard.attest(
            agent_id="cf-validator",
            session_key="agent:cf-validator:test",
            provider="provider",
            model="unreviewed-model",
        )
    assert exc_info.value.code == "TOOL_ATTESTATION_MODEL_MISMATCH"


@pytest.mark.parametrize(
    "changed_response",
    [
        {"runStarted": True},
        {"sessionId": "different-session"},
        {"entry": {"sessionId": "different-session"}},
    ],
)
def test_concrete_gateway_guard_rejects_unsafe_session_creation(
    changed_response: dict[str, Any],
) -> None:
    calls: list[str] = []

    def rpc(method: str, params: dict[str, Any]):
        calls.append(method)
        if method == "sessions.describe":
            return {"session": None}
        created = {
            "ok": True,
            "key": params["key"],
            "sessionId": "session-id",
            "entry": {"sessionId": "session-id"},
            "runStarted": False,
        }
        return created | changed_response

    guard = OpenClawGatewayNoToolSessionGuard(
        gateway_rpc=rpc,
        provider="provider",
        agent_models={
            "cf-physical-model": "physical-model",
            "cf-validator": "model",
        },
        policy_revision_sha256="C" * 64,
    )
    with pytest.raises(Phase8OpenResponsesTransportError) as exc_info:
        guard.attest(
            agent_id="cf-validator",
            session_key="agent:cf-validator:test",
            provider="provider",
            model="model",
        )

    assert exc_info.value.code == "TOOL_ATTESTATION_SESSION_INVALID"
    assert calls == ["sessions.describe", "sessions.create"]


def test_concrete_gateway_guard_rejects_resolved_model_mismatch() -> None:
    calls: list[str] = []
    session_created = False

    def rpc(method: str, params: dict[str, Any]):
        nonlocal session_created
        calls.append(method)
        if method == "sessions.create":
            session_created = True
            return {
                "ok": True,
                "key": params["key"],
                "sessionId": "session-id",
                "entry": {"sessionId": "session-id"},
                "runStarted": False,
            }
        if not session_created:
            return {"session": None}
        return {
            "session": {
                "key": params["key"],
                "sessionId": "session-id",
                "modelProvider": "different-provider",
                "model": "model",
            }
        }

    guard = OpenClawGatewayNoToolSessionGuard(
        gateway_rpc=rpc,
        provider="provider",
        agent_models={
            "cf-physical-model": "physical-model",
            "cf-validator": "model",
        },
        policy_revision_sha256="C" * 64,
    )
    with pytest.raises(Phase8OpenResponsesTransportError) as exc_info:
        guard.attest(
            agent_id="cf-validator",
            session_key="agent:cf-validator:test",
            provider="provider",
            model="model",
        )

    assert exc_info.value.code == "TOOL_ATTESTATION_MODEL_MISMATCH"
    assert calls == ["sessions.describe", "sessions.create", "sessions.describe"]


def test_concrete_gateway_guard_rejects_existing_session_without_reset() -> None:
    calls: list[str] = []

    def rpc(method: str, params: dict[str, Any]):
        calls.append(method)
        return {
            "session": {
                "key": params["key"],
                "sessionId": "prior-session",
                "modelProvider": "provider",
                "model": "model",
            }
        }

    guard = OpenClawGatewayNoToolSessionGuard(
        gateway_rpc=rpc,
        provider="provider",
        agent_models={
            "cf-physical-model": "physical-model",
            "cf-validator": "model",
        },
        policy_revision_sha256="C" * 64,
    )
    with pytest.raises(Phase8OpenResponsesTransportError) as exc_info:
        guard.attest(
            agent_id="cf-validator",
            session_key="agent:cf-validator:test",
            provider="provider",
            model="model",
        )

    assert exc_info.value.code == "TOOL_ATTESTATION_SESSION_EXISTS"
    assert calls == ["sessions.describe"]


def _is_safe_receipt(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789ABCDEF" for character in value)


def _blind_inventory() -> dict[str, Any]:
    return {
        "status": "COMPLETE",
        "observed_opening_count": 1,
        "observed_service_group_count": 1,
        "candidate_openings": [
            {
                "candidate_id": "V-O-001",
                "blank": False,
                "detail": "one opening",
                "evidence_refs": ["E-001"],
            }
        ],
        "candidate_services": [
            {
                "candidate_id": "V-S-001",
                "service_type": "pipe",
                "material": "PVC",
                "quantity": 1,
                "candidate_opening_ids": ["V-O-001"],
                "detail": "one service group",
                "evidence_refs": ["E-001"],
            }
        ],
        "unresolved_candidates": [],
        "limitations": [],
    }


def _assessment(value: object) -> dict[str, Any]:
    return {
        "status": "UNKNOWN" if value is None else "CONFIRMED",
        "confidence": None,
        "reasoning": (
            "The supplied view cannot support this value."
            if value is None
            else "The supplied synthetic evidence directly supports this value."
        ),
        "evidence_refs": ["E-001"],
        "credible_alternative": None,
        "additional_evidence_required": None,
    }


def _proposal() -> dict[str, Any]:
    opening = {
        "external_defect_id": "D-001",
        "opening_code": "O-001",
        "shape": "circular",
        "size": {"value": 100, "unit": "mm"},
        "opening_type": "service_penetration",
        "substrate_plane": "wall",
        "substrate_type": "concrete",
        "substrate_specific_type": "solid concrete wall",
        "substrate_thickness": {"value": 100, "unit": "mm"},
        "orientation": "vertical",
        "opening_boundary": "visible circular boundary",
        "opposite_face_continuity": None,
    }
    service = {
        "service_code": "S-001",
        "quantity": 1,
        "service_type": "pipe",
        "material": "PVC",
        "size": {"value": 50, "unit": "mm"},
        "insulation_or_covering": "uninsulated",
        "arrangement": "single service",
        "primary_opening_code": "O-001",
        "opening_codes": ["O-001"],
        "link_type": "penetrates",
        "relationship_status": "confirmed",
        "concealed_continuity": None,
        "evidence_status": "confirmed",
        "source_reference": "E-001",
        "confidence": "0.9",
    }
    opening["property_assessments"] = {
        field: _assessment(opening[field])
        for field in (
            "shape",
            "size",
            "opening_type",
            "substrate_plane",
            "substrate_type",
            "substrate_specific_type",
            "substrate_thickness",
            "orientation",
            "opening_boundary",
            "opposite_face_continuity",
        )
    }
    service["property_assessments"] = {
        field: _assessment(service[field])
        for field in (
            "quantity",
            "service_type",
            "material",
            "size",
            "insulation_or_covering",
            "arrangement",
            "primary_opening_code",
            "opening_codes",
            "link_type",
            "relationship_status",
            "concealed_continuity",
        )
    }
    return {
        "status": "MODEL_SUPPORTED",
        "assessment_schema": PROPERTY_ASSESSMENT_SCHEMA,
        "limitations": [],
        "openings": [opening],
        "services": [service],
    }


def _validator() -> dict[str, Any]:
    return {
        "verdict": "APPROVED",
        "issues": [],
        "limitations": [],
        "observed_opening_count": 1,
        "observed_service_group_count": 1,
        "blind_reconciliation": [
            {
                "blind_candidate_id": "V-O-001",
                "disposition": "ACCOUNTED_FOR",
                "proposal_refs": ["O-001"],
                "detail": "accounted for",
                "evidence_refs": ["E-001"],
            },
            {
                "blind_candidate_id": "V-S-001",
                "disposition": "ACCOUNTED_FOR",
                "proposal_refs": ["S-001"],
                "detail": "accounted for",
                "evidence_refs": ["E-001"],
            },
        ],
    }


def test_transport_composes_with_controller_without_write_capability(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    scripted = iter((_blind_inventory(), _proposal(), _validator()))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openresponses(next(scripted)))

    transport, guard = _transport(packet, handler)
    state = InitialSubmissionState(
        estimate_id="EST-001",
        fingerprint="D" * 64,
        counts={
            "defect_count": 1,
            "evidence_count": 1,
            "opening_count": 0,
            "service_count": 0,
            "service_opening_link_count": 0,
            "active_physical_model_lock_count": 0,
        },
        snapshot={"schema": "CLASSIFIRE-INITIAL-SUBMISSION-STATE-v1"},
    )
    controller = ProposalOnlyVisualController(
        run_id="RUN-001",
        estimate_id="EST-001",
        evidence_manifest=packet.manifest,
        inference_profile=_profile(),
        inference_port=transport,
        protected_state_reader=lambda: state,
    )

    result = controller.run()

    assert result.status == VISUAL_PROPOSAL_APPROVED
    assert result.approved is True
    assert len(guard.attestations) == 3
    assert len(guard.audits) == 3
    assert {item["agent_id"] for item in guard.attestations} == {
        "cf-validator",
        "cf-physical-model",
    }
    assert len({item["session_key"] for item in guard.attestations}) == 3
    assert result.receipt["controller_canonical_write_performed"] is False
    assert result.receipt["write_or_lock_capability_exposed"] is False


def _audit_contract_guard(rpc) -> OpenClawGatewayNoToolSessionGuard:
    return OpenClawGatewayNoToolSessionGuard(
        gateway_rpc=rpc,
        provider="provider",
        agent_models={"cf-physical-model": "physical-model", "cf-validator": "model"},
        policy_revision_sha256="C" * 64,
    )


def test_audit_fallback_preserves_exact_scope_and_hash_bound_receipt() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(method: str, params: dict[str, Any]) -> dict[str, Any]:
        calls.append((method, dict(params)))
        if method == "audit.activity.list":
            raise RuntimeError("synthetic-private-gateway-message")
        return {"events": []}

    guard = _audit_contract_guard(rpc)
    audit = guard.audit(
        agent_id="cf-validator", session_key="agent:cf-validator:synthetic-audit", after_ms=123
    )
    expected_params = {
        "sessionKey": "agent:cf-validator:synthetic-audit",
        "agentId": "cf-validator",
        "kind": "tool_action",
        "after": 123,
        "limit": 100,
    }
    assert calls == [("audit.activity.list", expected_params), ("audit.list", expected_params)]
    assert audit.agent_id == "cf-validator"
    assert audit.session_id_sha256 == _sha256_text("agent:cf-validator:synthetic-audit")
    assert audit.tool_calls == ()
    # Frozen synthetic legacy audit receipt; changing it needs compatibility review.
    assert audit.receipt_sha256 == (
        "315779AE87AE71419225DAE96AED7A2C47B7CC3DF04D7676EE158D91412961C1"
    )
    assert "synthetic-private" not in repr(audit)


@pytest.mark.parametrize("result", [None, [], {}, {"events": None}, {"events": [None]}])
def test_malformed_audit_response_is_not_hidden_by_fallback(result: Any) -> None:
    calls: list[str] = []

    def rpc(method: str, params: dict[str, Any]) -> Any:
        calls.append(method)
        return result

    with pytest.raises(Phase8OpenResponsesTransportError) as error:
        _audit_contract_guard(rpc).audit(
            agent_id="cf-validator", session_key="agent:cf-validator:synthetic-audit", after_ms=123
        )
    assert error.value.code == "TOOL_AUDIT_INVALID"
    assert calls == ["audit.activity.list"]


def test_both_audit_endpoints_unavailable_fail_with_content_safe_error() -> None:
    calls: list[str] = []

    def rpc(method: str, params: dict[str, Any]) -> dict[str, Any]:
        calls.append(method)
        raise RuntimeError("synthetic-private-gateway-message")

    with pytest.raises(Phase8OpenResponsesTransportError) as error:
        _audit_contract_guard(rpc).audit(
            agent_id="cf-validator", session_key="agent:cf-validator:synthetic-audit", after_ms=123
        )
    assert error.value.code == "TOOL_AUDIT_UNAVAILABLE"
    assert calls == ["audit.activity.list", "audit.list"]
    assert "synthetic-private" not in str(error.value)
    assert error.value.__suppress_context__ is True


@pytest.mark.parametrize("endpoint", ["audit.activity.list", "audit.list"])
@pytest.mark.parametrize(
    "result",
    [
        {"events": [], "nextCursor": "123"},
        {"events": [], "nextCursor": ""},
        {"events": [], "nextCursor": None},
        {"events": [{"toolName": "synthetic-tool"}] * 100, "nextCursor": "123"},
        {"events": [{"toolName": "synthetic-tool"}] * 101},
    ],
)
def test_audit_refuses_incomplete_or_oversized_page_without_retry(
    endpoint: str,
    result: dict[str, Any],
) -> None:
    calls = []

    def rpc(method, params):
        calls.append(method)
        if method != endpoint:
            raise RuntimeError("synthetic unsupported endpoint")
        return result

    with pytest.raises(Phase8OpenResponsesTransportError) as error:
        _audit_contract_guard(rpc).audit(
            agent_id="cf-validator",
            session_key="agent:cf-validator:synthetic-audit",
            after_ms=123,
        )
    assert error.value.code == "TOOL_AUDIT_INVALID"
    assert calls == (
        ["audit.activity.list"]
        if endpoint == "audit.activity.list"
        else ["audit.activity.list", "audit.list"]
    )


def test_terminal_full_audit_page_preserves_tool_detection_without_paging() -> None:
    calls = []

    def rpc(method, params):
        calls.append((method, params))
        return {"events": [{"toolName": "synthetic-tool"}] * 100}

    audit = _audit_contract_guard(rpc).audit(
        agent_id="cf-validator",
        session_key="agent:cf-validator:synthetic-audit",
        after_ms=123,
    )
    assert audit.tool_calls == ("synthetic-tool",)
    assert len(calls) == 1
    assert calls[0][1]["limit"] == 100


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"context_sha256": "D" * 64}, "COMPLETION_EVIDENCE_MISMATCH"),
        ({"receipt_sha256": "untrusted-detail"}, "COMPLETION_EVIDENCE_INVALID"),
        ({"terminal_at_ms": 99}, "COMPLETION_EVIDENCE_INCOMPLETE"),
        ({"terminal_at_ms": 201}, "COMPLETION_EVIDENCE_INCOMPLETE"),
        ({"coverage_from_ms": 101}, "COMPLETION_EVIDENCE_INCOMPLETE"),
        ({"coverage_through_ms": 99}, "COMPLETION_EVIDENCE_INCOMPLETE"),
        ({"coverage_through_ms": 201}, "COMPLETION_EVIDENCE_INCOMPLETE"),
        ({"writer_enabled": False}, "COMPLETION_EVIDENCE_INCOMPLETE"),
        ({"writer_healthy": False}, "COMPLETION_EVIDENCE_INCOMPLETE"),
        ({"pending_events": 1}, "COMPLETION_EVIDENCE_INCOMPLETE"),
        ({"dropped_events": 1}, "COMPLETION_EVIDENCE_INCOMPLETE"),
        ({"tool_actions": 1}, "COMPLETION_EVIDENCE_INCOMPLETE"),
        ({"pending_events": True}, "COMPLETION_EVIDENCE_INVALID"),
        ({"dropped_events": -1}, "COMPLETION_EVIDENCE_INVALID"),
        ({"tool_actions": 0.0}, "COMPLETION_EVIDENCE_INVALID"),
        ({"writer_enabled": 1}, "COMPLETION_EVIDENCE_INVALID"),
        ({"terminal_at_ms": "100"}, "COMPLETION_EVIDENCE_INVALID"),
    ],
)
def test_completion_evidence_rejects_unproven_capture(change, code) -> None:
    context = ExecutionCompletionContext(
        agent_id="cf-validator",
        session_id_sha256="A" * 64,
        request_sha256="B" * 64,
        request_body_sha256="C" * 64,
        response_sha256="D" * 64,
        audit_receipt_sha256="E" * 64,
        attestation_receipt_sha256="F" * 64,
        started_at_ms=100,
        observed_at_ms=200,
    )
    valid = _fake_completion(context)
    assert len(validate_execution_completion(valid, context)) == 64
    with pytest.raises(Phase8OpenResponsesTransportError) as error:
        validate_execution_completion(replace(valid, **change), context)
    assert error.value.code == code
    assert error.value.receipt_safe_code == code
    assert "untrusted-detail" not in str(error.value)


@pytest.mark.parametrize(
    "mode", ["missing", "untrusted", "mismatch", "incomplete", "error", "valid"]
)
def test_visual_completion_gate_prevents_unverified_proposal(tmp_path: Path, mode: str) -> None:
    packet = _packet(tmp_path)
    counts = {"token": 0, "http": 0}
    wire = {}
    contexts = []

    def token():
        counts["token"] += 1
        return "synthetic-token"

    def handler(request):
        counts["http"] += 1
        response = httpx.Response(200, json=_openresponses({"ok": True}))
        wire["request"] = request.content
        wire["response"] = response.content
        return response

    def verifier(context):
        contexts.append(context)
        if mode == "untrusted":
            return {"complete": True}
        if mode == "error":
            raise RuntimeError("private-verifier-detail")
        proof = _fake_completion(context)
        if mode == "mismatch":
            return replace(proof, context_sha256="F" * 64)
        if mode == "incomplete":
            return replace(proof, pending_events=1)
        return proof

    transport, guard = _transport(
        packet,
        handler,
        token_provider=token,
        completion_verifier=None if mode == "missing" else verifier,
    )
    if mode == "valid":
        result = transport.invoke(
            role="cf-validator", stage="blind_inventory", request=_request(packet)
        )
        assert result["payload"] == {"ok": True}
        assert (
            contexts[0].request_body_sha256 == hashlib.sha256(wire["request"]).hexdigest().upper()
        )
        assert contexts[0].response_sha256 == hashlib.sha256(wire["response"]).hexdigest().upper()
        assert contexts[0].request_sha256 == canonical_json_sha256(_request(packet))
        assert contexts[0].agent_id == "cf-validator"
        assert counts == {"token": 1, "http": 1}
        assert len(guard.audits) == 1
        first_receipt = result["transport_receipt_sha256"]
        transport._completion_verifier = lambda context: replace(
            _fake_completion(context),
            receipt_sha256="F" * 64,
        )
        changed = transport.invoke(
            role="cf-validator", stage="blind_inventory", request=_request(packet)
        )
        assert changed["transport_receipt_sha256"] != first_receipt
    else:
        with pytest.raises(Phase8OpenResponsesTransportError) as error:
            transport.invoke(role="cf-validator", stage="blind_inventory", request=_request(packet))
        assert (
            error.value.code
            == {
                "missing": "COMPLETION_EVIDENCE_UNAVAILABLE",
                "untrusted": "COMPLETION_EVIDENCE_INVALID",
                "mismatch": "COMPLETION_EVIDENCE_MISMATCH",
                "incomplete": "COMPLETION_EVIDENCE_INCOMPLETE",
                "error": "COMPLETION_EVIDENCE_UNAVAILABLE",
            }[mode]
        )
        assert "private-verifier-detail" not in str(error.value)
        if mode == "missing":
            assert counts == {"token": 0, "http": 0}
            assert guard.audits == []
        else:
            assert counts == {"token": 1, "http": 1}
            assert len(guard.audits) == 1


@pytest.mark.parametrize(
    "field",
    [
        "agent_id",
        "session_id_sha256",
        "request_sha256",
        "request_body_sha256",
        "response_sha256",
        "audit_receipt_sha256",
        "attestation_receipt_sha256",
        "started_at_ms",
        "observed_at_ms",
    ],
)
def test_completion_cannot_be_reused_for_changed_invocation(field: str) -> None:
    context = ExecutionCompletionContext(
        agent_id="cf-validator",
        session_id_sha256="A" * 64,
        request_sha256="B" * 64,
        request_body_sha256="C" * 64,
        response_sha256="D" * 64,
        audit_receipt_sha256="E" * 64,
        attestation_receipt_sha256="F" * 64,
        started_at_ms=100,
        observed_at_ms=200,
    )
    value = getattr(context, field)
    changed = (
        value + 1
        if type(value) is int
        else ("cf-physical-model" if field == "agent_id" else "0" * 64)
    )
    with pytest.raises(Phase8OpenResponsesTransportError) as error:
        validate_execution_completion(
            _fake_completion(context), replace(context, **{field: changed})
        )
    assert error.value.code == "COMPLETION_EVIDENCE_MISMATCH"
