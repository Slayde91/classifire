from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from classifire.services.canonical_submission_state import InitialSubmissionState
from classifire.services.phase8_openresponses_transport import (
    OPENRESPONSES_TRANSPORT_RECEIPT_BUNDLE_SCHEMA,
    NoToolSessionAttestation,
    NoToolSessionAudit,
    OpenClawGatewayNoToolSessionGuard,
    Phase8OpenResponsesTransport,
    Phase8OpenResponsesTransportError,
    build_phase8_openresponses_transport_receipt_bundle,
    validate_phase8_openresponses_transport_receipt_bundle,
)
from classifire.services.phase8_visual_evidence import (
    RetainedVisualEvidenceFile,
    RetainedVisualEvidencePacket,
)
from classifire.services.phase8_visual_prompts import (
    VISUAL_RUNTIME_POLICY,
    Phase8VisualPromptRenderer,
    build_visual_inference_profile,
)
from classifire.services.phase8_visual_proposal import (
    VISUAL_EVIDENCE_MANIFEST_SCHEMA,
    VISUAL_INFERENCE_REQUEST_SCHEMA,
    VISUAL_PROPOSAL_APPROVED,
    VISUAL_PROPOSAL_BLOCKED,
    VISUAL_PROPOSAL_POLICY_VERSION,
    ProposalOnlyVisualController,
    canonical_json_sha256,
    validate_visual_inference_response,
)
from classifire.services.storage import VerifiedStoredFile

_STORED_FILE_ID = "00000000-0000-4000-8000-000000000001"
_SCAN_ATTESTATION_ID = "00000000-0000-4000-8000-000000000002"
_OTHER_STORED_FILE_ID = "00000000-0000-4000-8000-000000000003"
_OTHER_SCAN_ATTESTATION_ID = "00000000-0000-4000-8000-000000000004"


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
    verification_token = VerifiedStoredFile(
        stored_file_id=_STORED_FILE_ID,
        path=path,
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
                path=path,
                sha256=digest,
                size_bytes=len(data),
                media_type="image/png",
                verification_token=verification_token,
            ),
        ),
    )


def _replace_verification_token(
    packet: RetainedVisualEvidencePacket,
    **changes: Any,
) -> RetainedVisualEvidencePacket:
    token = replace(packet.files[0].verification_token, **changes)
    item = replace(packet.files[0], verification_token=token)
    return replace(packet, files=(item,))


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


def _accept_evidence_packet(_packet: RetainedVisualEvidencePacket) -> None:
    return None


def _transport(
    packet: RetainedVisualEvidencePacket,
    handler,
    *,
    guard: FakeGuard | None = None,
    token_provider=lambda: "secret-token",  # noqa: B008
    runtime_agent_ids: dict[str, str] | None = None,
    evidence_packet_verifier=None,
    transport_receipt_sink=None,
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
            evidence_packet_verifier=(
                evidence_packet_verifier
                if evidence_packet_verifier is not None
                else _accept_evidence_packet
            ),
            session_guard=selected_guard,
            runtime_agent_ids=selected_runtime_agent_ids,
            transport_receipt_sink=transport_receipt_sink,
            clock_ms=lambda: 1234567890,
        ),
        selected_guard,
    )


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
    verified: list[RetainedVisualEvidencePacket] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_openresponses({"ok": True}))

    transport, guard = _transport(packet, handler, evidence_packet_verifier=verified.append)
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
    assert verified == [packet]
    assert "secret-token" not in str(result)
    assert str(packet.files[0].path) not in str(result)


def test_scan_token_accepts_the_existing_jpeg_media_type_alias(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    packet = replace(
        packet,
        manifest=deepcopy(packet.manifest),
        files=(
            replace(
                packet.files[0],
                media_type="image/jpeg",
                verification_token=replace(
                    packet.files[0].verification_token,
                    media_type="image/jpg",
                ),
            ),
        ),
    )
    packet.manifest["artifacts"][0]["media_type"] = "image/jpeg"
    transport, _guard = _transport(
        packet,
        lambda _request: httpx.Response(200, json=_openresponses({"ok": True})),
    )

    result = transport.invoke(
        role="cf-validator",
        stage="blind_inventory",
        request=_request(packet),
    )

    assert result["payload"] == {"ok": True}


@pytest.mark.parametrize("invalid_token", [None, object()])
def test_missing_or_invalid_scan_token_fails_before_verifier_guard_token_or_http(
    tmp_path: Path,
    invalid_token: object,
) -> None:
    packet = _packet(tmp_path)
    packet = replace(
        packet,
        files=(
            replace(
                packet.files[0],
                verification_token=cast(VerifiedStoredFile, invalid_token),
            ),
        ),
    )
    counts = {"verifier": 0, "token": 0, "http": 0}

    def verifier(_packet: RetainedVisualEvidencePacket) -> None:
        counts["verifier"] += 1

    def token_provider() -> str:
        counts["token"] += 1
        return "secret"

    def handler(_request: httpx.Request) -> httpx.Response:
        counts["http"] += 1
        return httpx.Response(500)

    transport, guard = _transport(
        packet,
        handler,
        token_provider=token_provider,
        evidence_packet_verifier=verifier,
    )
    with pytest.raises(Phase8OpenResponsesTransportError) as exc_info:
        transport.invoke(
            role="cf-validator",
            stage="blind_inventory",
            request=_request(packet),
        )

    assert exc_info.value.code == "EVIDENCE_ATTESTATION_INVALID"
    assert counts == {"verifier": 0, "token": 0, "http": 0}
    assert guard.attestations == []


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("stored_file_id", ""),
        ("stored_file_id", f" {_STORED_FILE_ID} "),
        ("content_sha256", "D" * 64),
        ("content_size_bytes", 999),
        ("media_type", "image/jpeg"),
        ("purpose", "project_evidence"),
        ("scan_attestation_id", ""),
        ("scan_attestation_id", f" {_SCAN_ATTESTATION_ID} "),
        ("scan_attestation_sha256", "not-a-sha256"),
        ("scan_sequence", 0),
        ("scan_sequence", True),
    ],
)
def test_mismatched_scan_token_fails_before_verifier_guard_token_or_http(
    tmp_path: Path,
    field: str,
    invalid_value: object,
) -> None:
    packet = _replace_verification_token(_packet(tmp_path), **{field: invalid_value})
    calls: list[str] = []

    transport, guard = _transport(
        packet,
        lambda _request: pytest.fail("HTTP must not run"),
        token_provider=lambda: pytest.fail("token provider must not run"),
        evidence_packet_verifier=lambda _packet: calls.append("verifier"),
    )
    with pytest.raises(Phase8OpenResponsesTransportError) as exc_info:
        transport.invoke(
            role="cf-validator",
            stage="blind_inventory",
            request=_request(packet),
        )

    assert exc_info.value.code == "EVIDENCE_ATTESTATION_INVALID"
    assert calls == []
    assert guard.attestations == []


def test_scan_token_path_mismatch_fails_before_verifier_guard_or_http(tmp_path: Path) -> None:
    packet = _replace_verification_token(_packet(tmp_path), path=tmp_path / "other.png")
    calls: list[str] = []
    transport, guard = _transport(
        packet,
        lambda _request: pytest.fail("HTTP must not run"),
        token_provider=lambda: pytest.fail("token provider must not run"),
        evidence_packet_verifier=lambda _packet: calls.append("verifier"),
    )

    with pytest.raises(Phase8OpenResponsesTransportError) as exc_info:
        transport.invoke(
            role="cf-validator",
            stage="blind_inventory",
            request=_request(packet),
        )

    assert exc_info.value.code == "EVIDENCE_ATTESTATION_INVALID"
    assert calls == []
    assert guard.attestations == []


def test_scan_revalidation_runs_before_every_stage_and_blocks_stale_packet(
    tmp_path: Path,
) -> None:
    packet = _packet(tmp_path)
    counts = {"verifier": 0, "token": 0, "http": 0}

    def verifier(current_packet: RetainedVisualEvidencePacket) -> None:
        assert current_packet is packet
        counts["verifier"] += 1
        if counts["verifier"] == 2:
            raise RuntimeError("unsafe database detail")

    def token_provider() -> str:
        counts["token"] += 1
        return "secret"

    def handler(_request: httpx.Request) -> httpx.Response:
        counts["http"] += 1
        return httpx.Response(200, json=_openresponses({"ok": True}))

    transport, guard = _transport(
        packet,
        handler,
        token_provider=token_provider,
        evidence_packet_verifier=verifier,
    )
    transport.invoke(
        role="cf-validator",
        stage="blind_inventory",
        request=_request(packet),
    )
    with pytest.raises(Phase8OpenResponsesTransportError) as exc_info:
        transport.invoke(
            role="cf-physical-model",
            stage="physical_proposal",
            request=_request(packet),
        )

    assert exc_info.value.code == "EVIDENCE_ATTESTATION_REVALIDATION_FAILED"
    assert "unsafe database detail" not in str(exc_info.value)
    assert counts == {"verifier": 2, "token": 1, "http": 1}
    assert len(guard.attestations) == 1
    assert len(guard.audits) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"stored_file_id": _OTHER_STORED_FILE_ID},
        {"scan_attestation_id": _OTHER_SCAN_ATTESTATION_ID},
        {"scan_attestation_sha256": "D" * 64},
        {"scan_sequence": 2},
    ],
)
def test_transport_receipt_binds_scan_identity_without_exposing_it(
    tmp_path: Path,
    changes: dict[str, Any],
) -> None:
    packet = _packet(tmp_path)
    changed_packet = _replace_verification_token(packet, **changes)
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=_openresponses({"ok": True}))

    original_transport, _ = _transport(packet, handler)
    changed_transport, _ = _transport(changed_packet, handler)
    original = original_transport.invoke(
        role="cf-validator",
        stage="blind_inventory",
        request=_request(packet),
    )
    changed = changed_transport.invoke(
        role="cf-validator",
        stage="blind_inventory",
        request=_request(changed_packet),
    )

    assert bodies[0] == bodies[1]
    assert original["session_id_sha256"] == changed["session_id_sha256"]
    assert original["transport_receipt_sha256"] != changed["transport_receipt_sha256"]
    scan_values = {
        packet.files[0].verification_token.stored_file_id,
        packet.files[0].verification_token.scan_attestation_id,
        packet.files[0].verification_token.scan_attestation_sha256,
        changed_packet.files[0].verification_token.stored_file_id,
        changed_packet.files[0].verification_token.scan_attestation_id,
        changed_packet.files[0].verification_token.scan_attestation_sha256,
    }
    public_output = json.dumps({"bodies": bodies, "responses": [original, changed]})
    assert all(value not in public_output for value in scan_values)
    assert str(packet.files[0].path) not in public_output


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
            evidence_packet_verifier=_accept_evidence_packet,
            session_guard=FakeGuard(),
            runtime_agent_ids=runtime_agent_ids,
        )
    assert exc_info.value.code == "RUNTIME_AGENT_POLICY_INVALID"


def test_invalid_evidence_packet_verifier_is_rejected(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    with pytest.raises(Phase8OpenResponsesTransportError) as exc_info:
        Phase8OpenResponsesTransport(
            client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
            base_url="http://127.0.0.1:18789/v1",
            token_provider=lambda: "token",
            evidence_packet=packet,
            evidence_packet_verifier=cast(Any, None),
            session_guard=FakeGuard(),
            runtime_agent_ids={
                "cf-physical-model": "cf-physical-model",
                "cf-validator": "cf-validator",
            },
        )

    assert exc_info.value.code == "EVIDENCE_PACKET_VERIFIER_INVALID"


def test_invalid_transport_receipt_sink_is_rejected(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    with pytest.raises(Phase8OpenResponsesTransportError) as exc_info:
        Phase8OpenResponsesTransport(
            client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
            base_url="http://127.0.0.1:18789/v1",
            token_provider=lambda: "token",
            evidence_packet=packet,
            evidence_packet_verifier=_accept_evidence_packet,
            session_guard=FakeGuard(),
            runtime_agent_ids={
                "cf-physical-model": "cf-physical-model",
                "cf-validator": "cf-validator",
            },
            transport_receipt_sink=cast(Any, "not-callable"),
        )

    assert exc_info.value.code == "TRANSPORT_RECEIPT_SINK_INVALID"


def test_transport_receipt_sink_failure_blocks_the_success_response(tmp_path: Path) -> None:
    packet = _packet(tmp_path)

    def fail_retention(_record: dict[str, Any]) -> None:
        raise RuntimeError("private sink detail")

    transport, guard = _transport(
        packet,
        lambda _request: httpx.Response(200, json=_openresponses({"ok": True})),
        transport_receipt_sink=fail_retention,
    )

    with pytest.raises(Phase8OpenResponsesTransportError) as exc_info:
        transport.invoke(
            role="cf-validator",
            stage="blind_inventory",
            request=_request(packet),
        )

    assert exc_info.value.code == "TRANSPORT_RECEIPT_RETENTION_FAILED"
    assert "private sink detail" not in str(exc_info.value)
    assert len(guard.attestations) == 1
    assert len(guard.audits) == 1


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
                evidence_packet_verifier=_accept_evidence_packet,
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
    assert prompt_error.value.code == "PROMPT_PROFILE_MISMATCH"
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


def _proposal() -> dict[str, Any]:
    return {
        "status": "MODEL_SUPPORTED",
        "limitations": [],
        "openings": [
            {
                "external_defect_id": "D-001",
                "opening_code": "O-001",
                "substrate_type": "concrete",
                "substrate_plane": "wall",
                "orientation": "vertical",
                "opening_type": "service_penetration",
            }
        ],
        "services": [
            {
                "service_code": "S-001",
                "service_type": "pipe",
                "material": "PVC",
                "quantity": 1,
                "primary_opening_code": "O-001",
                "opening_codes": ["O-001"],
                "evidence_status": "confirmed",
                "relationship_status": "confirmed",
                "link_type": "penetrates",
                "source_reference": "E-001",
                "confidence": "0.9",
            }
        ],
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
    transport_receipt_records: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openresponses(next(scripted)))

    transport, guard = _transport(
        packet,
        handler,
        transport_receipt_sink=transport_receipt_records.append,
    )
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
    bundle = build_phase8_openresponses_transport_receipt_bundle(
        transport_receipt_records,
        controller_receipt=result.receipt,
    )
    assert bundle["schema"] == OPENRESPONSES_TRANSPORT_RECEIPT_BUNDLE_SCHEMA
    assert validate_phase8_openresponses_transport_receipt_bundle(
        bundle,
        controller_receipt=result.receipt,
    ) == []
    assert len(bundle["records"]) == 3
    for record, stage in zip(bundle["records"], result.receipt["stages"], strict=True):
        assert canonical_json_sha256(record["receipt"]) == stage["transport_receipt_sha256"]
        assert record["receipt"]["request_sha256"] == stage["request_sha256"]
        assert record["receipt"]["session_id_sha256"] == stage["session_id_sha256"]
        assert record["receipt"]["payload_sha256"] == stage["payload_sha256"]
    serialized = json.dumps(bundle)
    assert str(packet.files[0].path) not in serialized
    assert "synthetic-image-bytes" not in serialized
    assert "input_image" not in serialized

    tampered = deepcopy(bundle)
    tampered["records"][0]["receipt"]["evidence"][0][
        "malware_scan_attestation_id"
    ] = _OTHER_SCAN_ATTESTATION_ID
    assert validate_phase8_openresponses_transport_receipt_bundle(
        tampered,
        controller_receipt=result.receipt,
    )
    unsafe_evidence_id = deepcopy(bundle)
    unsafe_evidence_id["records"][0]["receipt"]["evidence"][0][
        "evidence_id"
    ] = "https://example.invalid/evidence"
    assert validate_phase8_openresponses_transport_receipt_bundle(
        unsafe_evidence_id,
        controller_receipt=result.receipt,
    )
    missing = deepcopy(bundle)
    missing["records"].pop()
    extra = deepcopy(bundle)
    extra["records"].append(deepcopy(extra["records"][-1]))
    reordered = deepcopy(bundle)
    reordered["records"].reverse()
    request_mismatch = deepcopy(bundle)
    request_mismatch["records"][0]["receipt"]["request_sha256"] = "0" * 64
    for invalid_bundle in (missing, extra, reordered, request_mismatch):
        assert validate_phase8_openresponses_transport_receipt_bundle(
            invalid_bundle,
            controller_receipt=result.receipt,
        )

    no_stage_controller = deepcopy(result.receipt)
    no_stage_controller["status"] = VISUAL_PROPOSAL_BLOCKED
    no_stage_controller["stages"] = []
    no_stage_controller["result_hashes"] = {
        "blind_inventory_sha256": None,
        "proposal_sha256": None,
        "validator_sha256": None,
    }
    no_stage_controller["errors"] = ["No successful inference stage was retained."]
    no_stage_controller["runtime_inference_performed"] = False
    with pytest.raises(Phase8OpenResponsesTransportError) as empty:
        build_phase8_openresponses_transport_receipt_bundle(
            [],
            controller_receipt=no_stage_controller,
        )
    assert empty.value.code == "TRANSPORT_RECEIPT_BUNDLE_INVALID"
