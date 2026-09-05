from __future__ import annotations

import base64
import hashlib
import json
import subprocess
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
    ExecutionCompletionContext,
    ExecutionCompletionEvidence,
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
from classifire.services.phase8_visual_runtime import (
    ManagedPhase8ReportAssessmentRuntime,
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
    runtime: Phase8ReportRuntimeInput,
    handler,
    *,
    guard: _FakeGuard | None = None,
    completion_verifier=_fake_completion,
    completion_lifecycle=None,
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
            completion_verifier=completion_verifier,
            completion_lifecycle=completion_lifecycle,
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


def test_managed_report_runtime_uses_report_policy_before_token_or_http(
    tmp_path: Path,
) -> None:
    runtime_input, _image_bytes = _runtime(tmp_path)
    executable = tmp_path / "node.exe"
    executable.write_bytes(b"synthetic executable")
    rpc_calls: list[tuple[str, dict[str, Any]]] = []
    counts = {"token": 0, "http": 0}
    session_created = False

    def runner(args, **_kwargs):
        nonlocal session_created
        method = args[3]
        params = json.loads(args[args.index("--params") + 1])
        rpc_calls.append((method, params))
        if method == "sessions.create":
            session_created = True
            payload: dict[str, Any] = {
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
                        "model": "validator-test-model",
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

    def handler(_request: httpx.Request) -> httpx.Response:
        counts["http"] += 1
        return httpx.Response(500)

    request = _request(runtime_input)
    with ManagedPhase8ReportAssessmentRuntime(
        command_prefix=(executable,),
        base_url="http://127.0.0.1:18789/v1",
        provider="test-provider",
        physical_model="physical-test-model",
        validator_model="validator-test-model",
        physical_agent_id="cf-phase8-report-physical",
        validator_agent_id="cf-phase8-report-validator",
        implementation_revision="a" * 40,
        runtime_input=runtime_input,
        token_provider=token_provider,
        http_transport=httpx.MockTransport(handler),
        rpc_runner=runner,
    ) as runtime:
        assert runtime.visual_profile == _visual_profile()
        assert runtime.report_assessment_profile == _report_profile()
        with pytest.raises(Phase8OpenResponsesTransportError) as raised:
            runtime.transport.invoke(
                role="cf-validator",
                stage="blind_inventory",
                request=request,
                rendered_prompt=_render(runtime_input, request),
                runtime_input=runtime_input,
                report_assessment_inference_profile=runtime.report_assessment_profile,
            )
        assert raised.value.code == "SERVER_TOOLS_NOT_EMPTY"
        client = runtime._client

    assert [method for method, _params in rpc_calls] == [
        "sessions.describe",
        "sessions.create",
        "sessions.describe",
        "tools.effective",
    ]
    assert rpc_calls[1][1]["agentId"] == "cf-phase8-report-validator"
    assert rpc_calls[1][1]["model"] == "test-provider/validator-test-model"
    assert "classifire-phase8-report" in rpc_calls[0][1]["key"]
    assert counts == {"token": 0, "http": 0}
    assert client.is_closed


@pytest.mark.parametrize(
    "mode", ["missing", "untrusted", "mismatch", "incomplete", "error", "valid"]
)
def test_report_completion_gate_prevents_unverified_proposal(tmp_path: Path, mode: str) -> None:
    runtime, _ = _runtime(tmp_path)
    request = _request(runtime)
    counts = {"token": 0, "http": 0}
    wire = {}

    def token():
        counts["token"] += 1
        return "synthetic-token"

    def handler(provider_request):
        counts["http"] += 1
        response = httpx.Response(200, json=_completed_response({"accepted": True}))
        wire["request"] = provider_request.content
        wire["response"] = response.content
        return response

    contexts = []

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
            return replace(proof, dropped_events=1)
        return proof

    transport, guard = _transport(
        runtime,
        handler,
        token_provider=token,
        completion_verifier=None if mode == "missing" else verifier,
    )
    kwargs = {
        "role": "cf-validator",
        "stage": "blind_inventory",
        "request": request,
        "rendered_prompt": _render(runtime, request),
        "runtime_input": runtime,
        "report_assessment_inference_profile": _report_profile(),
    }
    if mode == "valid":
        result = transport.invoke(**kwargs)
        assert result["payload"] == {"accepted": True}
        assert (
            contexts[0].request_body_sha256 == hashlib.sha256(wire["request"]).hexdigest().upper()
        )
        assert contexts[0].response_sha256 == hashlib.sha256(wire["response"]).hexdigest().upper()
        assert contexts[0].request_sha256 == canonical_json_sha256(request)
        assert contexts[0].agent_id == "cf-validator"
        assert counts == {"token": 1, "http": 1}
        assert len(guard.audits) == 1
        transport._visual_transport._completion_verifier = lambda context: replace(
            _fake_completion(context),
            receipt_sha256="F" * 64,
        )
        changed = transport.invoke(**kwargs)
        assert changed["transport_receipt_sha256"] != result["transport_receipt_sha256"]
    else:
        with pytest.raises(Phase8OpenResponsesTransportError) as error:
            transport.invoke(**kwargs)
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
