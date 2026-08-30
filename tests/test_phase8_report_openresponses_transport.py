from __future__ import annotations

import base64
import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from test_phase8_report_documentary_context import _packet as _report_packet
from test_phase8_report_runtime_input import _visual_packet
from test_report_evidence_adapter import _report_content

from classifire.services.phase8_openresponses_transport import (
    NoToolSessionAttestation,
    NoToolSessionAudit,
    Phase8OpenResponsesTransportError,
)
from classifire.services.phase8_report_assessment_input import (
    build_phase8_report_assessment_input,
)
from classifire.services.phase8_report_assessment_prompts import (
    Phase8ReportAssessmentPromptRenderer,
    build_report_assessment_inference_profile,
)
from classifire.services.phase8_report_documentary_context import (
    build_phase8_report_documentary_context,
)
from classifire.services.phase8_report_openresponses_transport import (
    Phase8ReportOpenResponsesTransport,
)
from classifire.services.phase8_report_runtime_input import (
    Phase8ReportRuntimeInput,
    build_phase8_report_runtime_input,
)
from classifire.services.phase8_visual_evidence import (
    RetainedVisualEvidenceFile,
    RetainedVisualEvidencePacket,
)
from classifire.services.phase8_visual_prompts import build_visual_inference_profile
from classifire.services.phase8_visual_proposal import (
    VISUAL_INFERENCE_REQUEST_SCHEMA,
    VISUAL_PROPOSAL_POLICY_VERSION,
    canonical_json_sha256,
)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest().upper()


def _runtime(tmp_path: Path) -> tuple[Phase8ReportRuntimeInput, bytes]:
    image_bytes = b"report-aware-retained-image"
    image_path = tmp_path / "retained-image.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(image_bytes)
    visual_manifest = deepcopy(_visual_packet().manifest)
    artifact = visual_manifest["artifacts"][0]
    artifact["evidence_id"] = "E-001"
    artifact["sha256"] = hashlib.sha256(image_bytes).hexdigest()
    artifact["size_bytes"] = len(image_bytes)
    artifact["media_type"] = "image/png"
    visual = RetainedVisualEvidencePacket(
        manifest=visual_manifest,
        files=(
            RetainedVisualEvidenceFile(
                evidence_id="E-001",
                path=image_path,
                sha256=artifact["sha256"],
                size_bytes=len(image_bytes),
                media_type="image/png",
            ),
        ),
    )
    verified_content = _report_content()
    report_packet = _report_packet(verified_content)
    assessment = build_phase8_report_assessment_input(
        report_packet=report_packet,
        visual_packet=visual,
    )
    documentary = build_phase8_report_documentary_context(
        report_packet=report_packet,
        verified_content=verified_content,
    )
    return (
        build_phase8_report_runtime_input(
            assessment_input=assessment,
            documentary_context=documentary,
        ),
        image_bytes,
    )


def _visual_profile() -> dict[str, Any]:
    return build_visual_inference_profile(
        implementation_revision="a" * 40,
        provider="test-provider",
        physical_model="physical-test-model",
        validator_model="validator-test-model",
    )


def _report_profile() -> dict[str, Any]:
    return build_report_assessment_inference_profile(
        implementation_revision="a" * 40,
        provider="test-provider",
        physical_model="physical-test-model",
        validator_model="validator-test-model",
    )


def _request(runtime: Phase8ReportRuntimeInput) -> dict[str, Any]:
    visual_profile = _visual_profile()
    return {
        "schema": VISUAL_INFERENCE_REQUEST_SCHEMA,
        "policy_version": VISUAL_PROPOSAL_POLICY_VERSION,
        "run_id": "REPORT-RUN-001",
        "estimate_id": runtime.manifest["estimate_id"],
        "defect_reference": runtime.manifest["defect_reference"],
        "evidence_manifest": deepcopy(runtime.visual_packet.manifest),
        "evidence_manifest_sha256": runtime.visual_packet.manifest_sha256,
        "inference_profile": visual_profile,
        "inference_profile_sha256": canonical_json_sha256(visual_profile),
        "human_reference_visible": False,
        "allowed_tools": [],
        "stage_input": {},
    }


def _render(runtime: Phase8ReportRuntimeInput, request: dict[str, Any]):
    return Phase8ReportAssessmentPromptRenderer().render(
        role="cf-validator",
        stage="blind_inventory",
        run_id=request["run_id"],
        runtime_input=runtime,
        inference_profile=_report_profile(),
        stage_input=request["stage_input"],
    )


class _FakeGuard:
    def __init__(self, *, audit_tools: tuple[str, ...] = ()) -> None:
        self.audit_tools = audit_tools
        self.attestations: list[dict[str, str]] = []
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
            effective_tools=(),
            receipt_sha256="A" * 64,
            policy_revision_sha256=_report_profile()["runtime_policy_sha256"],
        )

    def audit(self, *, agent_id, session_key, after_ms):
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


def _transport(
    runtime: Phase8ReportRuntimeInput,
    handler,
    *,
    guard: _FakeGuard | None = None,
    token_provider=lambda: "secret-token",  # noqa: B008
) -> tuple[Phase8ReportOpenResponsesTransport, _FakeGuard]:
    selected_guard = guard or _FakeGuard()
    return (
        Phase8ReportOpenResponsesTransport(
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            base_url="http://127.0.0.1:18789/v1",
            token_provider=token_provider,
            runtime_input=runtime,
            session_guard=selected_guard,
            runtime_agent_ids={
                "cf-physical-model": "cf-physical-model",
                "cf-validator": "cf-validator",
            },
            clock_ms=lambda: 1234567890,
        ),
        selected_guard,
    )


def _completed_response(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "resp-report-001",
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


def test_report_transport_sends_only_the_bound_prompt_and_retained_image(
    tmp_path: Path,
) -> None:
    runtime, image_bytes = _runtime(tmp_path)
    request = _request(runtime)
    rendered = _render(runtime, request)
    observed: dict[str, Any] = {}

    def handler(provider_request: httpx.Request) -> httpx.Response:
        observed["url"] = str(provider_request.url)
        body = json.loads(provider_request.content)
        observed["body"] = body
        return httpx.Response(200, json=_completed_response({"accepted": True}))

    transport, guard = _transport(runtime, handler)
    response = transport.invoke(
        role="cf-validator",
        stage="blind_inventory",
        request=request,
        rendered_prompt=rendered,
        runtime_input=runtime,
        report_assessment_inference_profile=_report_profile(),
    )

    body = observed["body"]
    parts = body["input"][0]["content"]
    assert observed["url"] == "http://127.0.0.1:18789/v1/responses"
    assert body["tools"] == []
    assert body["tool_choice"] == "none"
    assert [part["type"] for part in parts] == ["input_text", "input_image"]
    assert "Private annotation content" in parts[0]["text"]
    assert base64.b64decode(parts[1]["source"]["data"]) == image_bytes
    assert response["payload"] == {"accepted": True}
    assert response["tool_calls"] == []
    assert "Private annotation content" not in str(response)
    assert len(guard.attestations) == len(guard.audits) == 1
    assert "classifire-phase8-report" in guard.attestations[0]["session_key"]


def test_report_transport_rejects_an_unbound_prompt_before_guard_or_http(
    tmp_path: Path,
) -> None:
    runtime, _image_bytes = _runtime(tmp_path)
    request = _request(runtime)
    rendered = replace(_render(runtime, request), text="unbound documentary instruction")
    guard = _FakeGuard()
    token_called = False

    def token_provider() -> str:
        nonlocal token_called
        token_called = True
        return "secret-token"

    def handler(_provider_request: httpx.Request) -> httpx.Response:
        pytest.fail("HTTP must not run for an unbound report prompt")

    transport, _ = _transport(
        runtime,
        handler,
        guard=guard,
        token_provider=token_provider,
    )

    with pytest.raises(Phase8OpenResponsesTransportError) as raised:
        transport.invoke(
            role="cf-validator",
            stage="blind_inventory",
            request=request,
            rendered_prompt=rendered,
            runtime_input=runtime,
            report_assessment_inference_profile=_report_profile(),
        )

    assert raised.value.code == "REPORT_PROMPT_RENDERING_MISMATCH"
    assert guard.attestations == []
    assert token_called is False


def test_report_transport_rejects_a_substituted_runtime_before_guard_or_http(
    tmp_path: Path,
) -> None:
    runtime, _image_bytes = _runtime(tmp_path)
    other_runtime, _other_image_bytes = _runtime(tmp_path / "other")
    request = _request(runtime)
    guard = _FakeGuard()

    def handler(_provider_request: httpx.Request) -> httpx.Response:
        pytest.fail("HTTP must not run for a substituted report runtime")

    transport, _ = _transport(runtime, handler, guard=guard)

    with pytest.raises(Phase8OpenResponsesTransportError) as raised:
        transport.invoke(
            role="cf-validator",
            stage="blind_inventory",
            request=request,
            rendered_prompt=_render(runtime, request),
            runtime_input=other_runtime,
            report_assessment_inference_profile=_report_profile(),
        )

    assert raised.value.code == "REPORT_RUNTIME_INPUT_INVALID"
    assert guard.attestations == []


def test_report_transport_fails_closed_when_the_post_turn_audit_records_a_tool(
    tmp_path: Path,
) -> None:
    runtime, _image_bytes = _runtime(tmp_path)
    request = _request(runtime)

    def handler(_provider_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completed_response({"accepted": True}))

    transport, guard = _transport(runtime, handler, guard=_FakeGuard(audit_tools=("write",)))

    with pytest.raises(Phase8OpenResponsesTransportError) as raised:
        transport.invoke(
            role="cf-validator",
            stage="blind_inventory",
            request=request,
            rendered_prompt=_render(runtime, request),
            runtime_input=runtime,
            report_assessment_inference_profile=_report_profile(),
        )

    assert raised.value.code == "SERVER_TOOL_ACTION_DETECTED"
    assert len(guard.attestations) == len(guard.audits) == 1
