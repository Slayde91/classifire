"""No-tool OpenResponses adapter for a report-bound Phase 8 assessment.

This is deliberately distinct from the visual-only transport.  It consumes the
controller's already-rendered report prompt, independently rebuilds that prompt
from the exact runtime input, and then reuses the established byte, session,
no-tool, and response safeguards.  Documentary material is supplied only as
prompt text; it is never treated as a file attachment or returned in a receipt.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import Any

import httpx

from .phase8_openresponses_transport import (
    _ALLOWED_ROLES,
    _MAX_OUTPUT_TOKENS,
    _MAX_REQUEST_BYTES,
    ExecutionCompletionLifecycle,
    ExecutionCompletionVerifier,
    ExecutionDispatchBinding,
    NoToolSessionGuard,
    Phase8OpenResponsesTransport,
    Phase8OpenResponsesTransportError,
    _expected_role,
    _sha256_text,
)
from .phase8_report_assessment_prompts import (
    Phase8ReportAssessmentPromptError,
    Phase8ReportAssessmentPromptRenderer,
    RenderedReportAssessmentPrompt,
    validate_report_assessment_inference_profile,
)
from .phase8_report_runtime_input import (
    Phase8ReportRuntimeInput,
    validate_phase8_report_runtime_input,
)
from .phase8_visual_prompts import (
    current_visual_prompt_profile_hashes,
    prompt_profile_field,
)
from .phase8_visual_proposal import (
    VISUAL_INFERENCE_REQUEST_SCHEMA,
    VISUAL_INFERENCE_RESPONSE_SCHEMA,
    VISUAL_PROPOSAL_POLICY_VERSION,
    canonical_json_sha256,
    validate_visual_evidence_manifest,
    validate_visual_inference_profile,
)

PHASE8_REPORT_OPENRESPONSES_TRANSPORT_SCHEMA = (
    "CLASSIFIRE-PHASE8-REPORT-OPENRESPONSES-TRANSPORT-v2"
)

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


class Phase8ReportOpenResponsesTransport:
    """Run one exact report-aware inference turn behind the existing no-tool guard."""

    def __init__(
        self,
        *,
        client: httpx.Client,
        base_url: str,
        token_provider: Callable[[], str],
        runtime_input: Phase8ReportRuntimeInput,
        session_guard: NoToolSessionGuard,
        completion_verifier: ExecutionCompletionVerifier | None = None,
        completion_lifecycle: ExecutionCompletionLifecycle | None = None,
        runtime_agent_ids: Mapping[str, str],
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        if not isinstance(runtime_input, Phase8ReportRuntimeInput) or (
            validate_phase8_report_runtime_input(runtime_input)
        ):
            raise Phase8OpenResponsesTransportError("REPORT_RUNTIME_INPUT_INVALID")
        self._runtime_input = runtime_input
        self._visual_transport = Phase8OpenResponsesTransport(
            client=client,
            base_url=base_url,
            token_provider=token_provider,
            evidence_packet=runtime_input.visual_packet,
            session_guard=session_guard,
            completion_verifier=completion_verifier,
            completion_lifecycle=completion_lifecycle,
            runtime_agent_ids=runtime_agent_ids,
            clock_ms=clock_ms,
        )

    def invoke(
        self,
        *,
        role: str,
        stage: str,
        request: dict[str, Any],
        rendered_prompt: RenderedReportAssessmentPrompt,
        runtime_input: Phase8ReportRuntimeInput,
        report_assessment_inference_profile: dict[str, Any],
    ) -> dict[str, Any]:
        """Invoke only a freshly reconstructed, report-bound prompt.

        The documentary context is validated in memory before token acquisition
        or gateway access.  The base transport then re-verifies each retained
        image byte and enforces its no-tool session guard around the request.
        """

        if runtime_input is not self._runtime_input or validate_phase8_report_runtime_input(
            self._runtime_input
        ):
            raise Phase8OpenResponsesTransportError("REPORT_RUNTIME_INPUT_INVALID")
        trusted_request = deepcopy(request)
        self._validate_report_request(
            role=role,
            stage=stage,
            request=trusted_request,
            report_profile=report_assessment_inference_profile,
        )
        trusted_profile = deepcopy(report_assessment_inference_profile)
        trusted_rendered = self._trusted_rendered_prompt(
            role=role,
            stage=stage,
            request=trusted_request,
            report_profile=trusted_profile,
        )
        if rendered_prompt != trusted_rendered:
            raise Phase8OpenResponsesTransportError("REPORT_PROMPT_RENDERING_MISMATCH")
        profile_field = prompt_profile_field(stage)
        if (
            trusted_rendered.template_sha256
            != trusted_profile[profile_field]
            or trusted_rendered.inference_profile_sha256
            != canonical_json_sha256(trusted_profile)
            or trusted_rendered.runtime_input_manifest_sha256
            != self._runtime_input.manifest_sha256
        ):
            raise Phase8OpenResponsesTransportError("REPORT_PROMPT_PROFILE_MISMATCH")

        content, byte_receipts = self._visual_transport._image_content(trusted_request)
        runtime_agent_id = self._visual_transport._runtime_agent_ids[role]
        report_profile_sha256 = canonical_json_sha256(trusted_profile)
        session_key = self._report_session_key(
            agent_id=runtime_agent_id,
            stage=stage,
            request=trusted_request,
            runtime_input_manifest_sha256=self._runtime_input.manifest_sha256,
            report_profile_sha256=report_profile_sha256,
        )
        session_id_sha256 = _sha256_text(session_key)
        expected_model = (
            trusted_profile["validator_model"]
            if role == "cf-validator"
            else trusted_profile["physical_model"]
        )
        try:
            attestation = self._visual_transport._guard.attest(
                agent_id=runtime_agent_id,
                session_key=session_key,
                provider=trusted_profile["provider"],
                model=expected_model,
            )
        except Phase8OpenResponsesTransportError:
            raise
        except Exception:
            raise Phase8OpenResponsesTransportError(
                "TOOL_ATTESTATION_UNAVAILABLE"
            ) from None
        self._visual_transport._validate_attestation(
            attestation,
            agent_id=runtime_agent_id,
            provider=trusted_profile["provider"],
            model=expected_model,
            session_id_sha256=session_id_sha256,
            runtime_policy_sha256=trusted_profile["runtime_policy_sha256"],
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
                        {"type": "input_text", "text": trusted_rendered.text},
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

        with self._visual_transport._completion_scope(
            ExecutionDispatchBinding(
                agent_id=runtime_agent_id,
                session_id_sha256=session_id_sha256,
                request_sha256=canonical_json_sha256(trusted_request),
                request_body_sha256=hashlib.sha256(encoded_body).hexdigest().upper(),
                attestation_receipt_sha256=attestation.receipt_sha256,
            )
        ) as started_at_ms:
            try:
                token = self._visual_transport._token_provider()
            except Exception:
                raise Phase8OpenResponsesTransportError("GATEWAY_TOKEN_UNAVAILABLE") from None
            if not isinstance(token, str) or not token.strip():
                raise Phase8OpenResponsesTransportError("GATEWAY_TOKEN_UNAVAILABLE")

            if started_at_ms is None:
                started_at_ms = self._visual_transport._clock_ms()
            response: httpx.Response | None = None
            request_error: Phase8OpenResponsesTransportError | None = None
            try:
                response = self._visual_transport._client.post(
                    self._visual_transport._endpoint,
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

            audit = self._visual_transport._audit(
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
            payload, response_id = self._visual_transport._parse_response(response)
            completion_sha256 = self._visual_transport._verify_completion(
                agent_id=runtime_agent_id,
                session_id_sha256=session_id_sha256,
                request=trusted_request,
                encoded_body=encoded_body,
                response=response,
                audit=audit,
                attestation_receipt_sha256=attestation.receipt_sha256,
                started_at_ms=started_at_ms,
            )

            receipt_sha256 = canonical_json_sha256(
                {
                    "schema": PHASE8_REPORT_OPENRESPONSES_TRANSPORT_SCHEMA,
                    "visual_request_sha256": canonical_json_sha256(trusted_request),
                    "report_prompt_sha256": canonical_json_sha256(trusted_rendered.text),
                    "report_prompt_template_sha256": trusted_rendered.template_sha256,
                    "documentary_content_sha256": trusted_rendered.documentary_content_sha256,
                    "report_runtime_input_manifest_sha256": self._runtime_input.manifest_sha256,
                    "report_assessment_inference_profile_sha256": report_profile_sha256,
                    "session_id_sha256": session_id_sha256,
                    "attestation_receipt_sha256": attestation.receipt_sha256,
                    "audit_receipt_sha256": audit.receipt_sha256,
                    "execution_completion_sha256": completion_sha256,
                    "evidence": byte_receipts,
                    "openresponses_response_id_sha256": _sha256_text(response_id),
                    "payload_sha256": canonical_json_sha256(payload),
                }
            )
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

    def _validate_report_request(
        self,
        *,
        role: str,
        stage: str,
        request: dict[str, Any],
        report_profile: object,
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
            or manifest != self._runtime_input.visual_packet.manifest
            or self._runtime_input.visual_packet.manifest_sha256
            != request.get("evidence_manifest_sha256")
            or manifest.get("defect_reference") != request["defect_reference"]
            or request["estimate_id"] != self._runtime_input.manifest["estimate_id"]
            or request["defect_reference"] != self._runtime_input.manifest["defect_reference"]
        ):
            raise Phase8OpenResponsesTransportError("REPORT_EVIDENCE_PACKET_MISMATCH")
        visual_profile = request.get("inference_profile")
        if (
            not isinstance(visual_profile, dict)
            or validate_visual_inference_profile(visual_profile)
            or canonical_json_sha256(visual_profile)
            != request.get("inference_profile_sha256")
            or any(
                str(visual_profile.get(field) or "").upper() != expected
                for field, expected in current_visual_prompt_profile_hashes().items()
            )
        ):
            raise Phase8OpenResponsesTransportError("INFERENCE_PROFILE_MISMATCH")
        if (
            not isinstance(report_profile, dict)
            or validate_report_assessment_inference_profile(report_profile)
            or any(
                visual_profile.get(field) != report_profile.get(field)
                for field in (
                    "implementation_revision",
                    "provider",
                    "physical_model",
                    "validator_model",
                )
            )
        ):
            raise Phase8OpenResponsesTransportError("REPORT_INFERENCE_PROFILE_MISMATCH")
        try:
            canonical_json_sha256(request.get("stage_input"))
        except Exception:
            raise Phase8OpenResponsesTransportError("STAGE_INPUT_INVALID") from None
        return visual_profile

    def _trusted_rendered_prompt(
        self,
        *,
        role: str,
        stage: str,
        request: dict[str, Any],
        report_profile: dict[str, Any],
    ) -> RenderedReportAssessmentPrompt:
        try:
            return Phase8ReportAssessmentPromptRenderer().render(
                role=role,
                stage=stage,
                run_id=request["run_id"],
                runtime_input=self._runtime_input,
                inference_profile=report_profile,
                stage_input=request["stage_input"],
            )
        except Phase8ReportAssessmentPromptError:
            raise Phase8OpenResponsesTransportError("REPORT_PROMPT_INVALID") from None

    @staticmethod
    def _report_session_key(
        *,
        agent_id: str,
        stage: str,
        request: dict[str, Any],
        runtime_input_manifest_sha256: str,
        report_profile_sha256: str,
    ) -> str:
        identity = canonical_json_sha256(
            {
                "run_id": request["run_id"],
                "stage": stage,
                "visual_request_sha256": canonical_json_sha256(request),
                "report_runtime_input_manifest_sha256": runtime_input_manifest_sha256,
                "report_assessment_inference_profile_sha256": report_profile_sha256,
            }
        )
        return f"agent:{agent_id}:classifire-phase8-report-{identity[:32].lower()}"


__all__ = [
    "PHASE8_REPORT_OPENRESPONSES_TRANSPORT_SCHEMA",
    "Phase8ReportOpenResponsesTransport",
]
