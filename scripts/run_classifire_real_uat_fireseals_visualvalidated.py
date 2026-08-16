from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
from pathlib import Path
import sys
import time
from typing import Any

import httpx

from classifire.canonical_models import Defect
from classifire.visual_validation import (
    VISUAL_VALIDATOR_ISSUE_CODES,
    validate_visual_validator_payload,
    visual_validator_approved,
)
from run_classifire_real_uat_deterministic import _json_from_payload
from run_classifire_real_uat_fireseals_blankaware import _model_completeness_issues
from run_classifire_real_uat_fireseals_topologyaware import TopologyAwareFireSealController
from run_classifire_real_uat_intake import load_receipt, parse_json_envelope, repo_root


VISUAL_GATE_POLICY_VERSION = "CLASSIFIRE-FIRESEAL-VISUAL-GATE-v1"
MAX_VISUAL_CORRECTION_PASSES = 2
OPENRESPONSES_BASE_URL = "http://127.0.0.1:18789"
OPENRESPONSES_TIMEOUT_SECONDS = 300.0
OPENRESPONSES_MAX_OUTPUT_TOKENS = 8_000

ALLOWED_VISUAL_MIMES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/heic",
    "image/heif",
}

PHYSICAL_VISUAL_TOOLS = {
    "classifire_evidence_read",
    "classifire_physical_model_read",
}

VALIDATOR_VISUAL_TOOLS = {
    "classifire_evidence_read",
    "classifire_physical_model_read",
    "classifire_run_validation",
}

PHYSICAL_VISUAL_GUARDED_WRITE_TOOLS = {
    "classifire_submit_initial_physical_model",
    "classifire_lock_physical_model",
}

PHYSICAL_VISUAL_FORBIDDEN_TOOLS = {
    "classifire_derive_quantity_labour",
}


class VisualValidatedTopologyController(TopologyAwareFireSealController):
    """Require an independent actual-image validator pass before canonical physical write.

    This controller deliberately keeps the existing canonical write path owned by
    cf-physical-model. The only change is the draft gate: each defect topology must
    first be built from the actual retained multi-image set under the cf-physical-model
    session and independently challenged against the same images under cf-validator.
    A rejected or blocked final visual review is converted to INSUFFICIENT_EVIDENCE,
    which causes the parent runner to withhold the entire canonical physical model.
    """

    def __init__(
        self,
        *args: Any,
        openresponses_timeout_seconds: float | None = None,
        **kwargs: Any,
    ) -> None:
        configured_timeout = openresponses_timeout_seconds

        if configured_timeout is None:
            configured_timeout = kwargs.get(
                "timeout_seconds"
            )

        if configured_timeout is None:
            configured_timeout = (
                OPENRESPONSES_TIMEOUT_SECONDS
            )

        configured_timeout = float(
            configured_timeout
        )

        if configured_timeout <= 0:
            raise ValueError(
                "OpenResponses timeout must be greater than zero"
            )

        self._openresponses_timeout_seconds = (
            configured_timeout
        )

        super().__init__(*args, **kwargs)

        self._visual_physical_session: str | None = None
        self._visual_validator_session: str | None = None

    def _ensure_visual_sessions(self) -> tuple[str, str]:
        if self._visual_physical_session is None:
            session = self.initialize_session("cf-physical-model", "21-visual-physical")
            self.require_tools(
                "cf-physical-model",
                session,
                PHYSICAL_VISUAL_TOOLS,
                "21-visual-physical-effective.json",
            )
            self._assert_physical_visual_readonly(
                session
            )
            self.invoke_tool(
                "cf-physical-model",
                session,
                "classifire_evidence_read",
                {"estimate_id": self.estimate_id},
                "21-visual-physical-evidence-read.json",
            )
            self._visual_physical_session = session

        if self._visual_validator_session is None:
            session = self.initialize_session("cf-validator", "21-visual-validator")
            self.require_tools(
                "cf-validator",
                session,
                VALIDATOR_VISUAL_TOOLS,
                "21-visual-validator-effective.json",
            )
            self.invoke_tool(
                "cf-validator",
                session,
                "classifire_evidence_read",
                {"estimate_id": self.estimate_id},
                "21-visual-validator-evidence-read.json",
            )
            self._visual_validator_session = session

        return self._visual_physical_session, self._visual_validator_session

    @staticmethod
    def _effective_tool_names(value: Any) -> set[str]:
        if not isinstance(value, dict):
            raise RuntimeError(
                "tools.effective response is not an object"
            )

        groups = value.get("groups")

        if not isinstance(groups, list):
            raise RuntimeError(
                "tools.effective response has no groups list"
            )

        names: set[str] = set()

        for group in groups:
            if not isinstance(group, dict):
                continue

            tools = group.get("tools") or []

            if not isinstance(tools, list):
                continue

            for tool in tools:
                if not isinstance(tool, dict):
                    continue

                tool_id = tool.get("id")

                if isinstance(tool_id, str):
                    names.add(tool_id)

        return names

    def _assert_physical_visual_readonly(
        self,
        session_key: str,
    ) -> None:
        effective = self.gateway_call(
            "tools.effective",
            {
                "sessionKey": session_key,
            },
            "21-visual-physical-runtime-effective.json",
        )

        names = self._effective_tool_names(
            effective
        )

        missing_reads = (
            PHYSICAL_VISUAL_TOOLS - names
        )

        missing_guarded_writes = (
            PHYSICAL_VISUAL_GUARDED_WRITE_TOOLS
            - names
        )

        forbidden = (
            PHYSICAL_VISUAL_FORBIDDEN_TOOLS
            & names
        )

        if missing_reads:
            raise RuntimeError(
                "Physical visual session is missing required "
                "read tool(s): "
                + ", ".join(
                    sorted(missing_reads)
                )
            )

        if missing_guarded_writes:
            raise RuntimeError(
                "Physical Phase 8 policy is missing guarded "
                "canonical write tool(s): "
                + ", ".join(
                    sorted(missing_guarded_writes)
                )
            )

        if forbidden:
            raise RuntimeError(
                "Physical visual policy exposes forbidden "
                "downstream tool(s): "
                + ", ".join(
                    sorted(forbidden)
                )
            )

    def _assert_no_visual_tool_actions(
        self,
        *,
        session_key: str,
        after_ms: int,
        receipt_name: str,
    ) -> None:
        params = {
            "sessionKey": session_key,
            "kind": "tool_action",
            "after": after_ms,
            "limit": 100,
        }

        receipt = (
            receipt_name
            + "-tool-audit.json"
        )

        try:
            audit = self.gateway_call(
                "audit.activity.list",
                params,
                receipt,
            )
        except RuntimeError as exc:
            message = str(exc)

            if (
                "unknown method: "
                "audit.activity.list"
                not in message
            ):
                raise

            audit = self.gateway_call(
                "audit.list",
                params,
                receipt,
            )

        events = audit.get("events")

        if not isinstance(events, list):
            raise RuntimeError(
                "OpenClaw audit response has "
                "no events list"
            )

        if events:
            tool_names = sorted(
                {
                    str(
                        event.get("toolName")
                        or event.get("tool")
                        or event.get("action")
                        or "unknown"
                    )
                    for event in events
                    if isinstance(event, dict)
                }
            )

            raise RuntimeError(
                "Visual agent turn used "
                "OpenClaw tool(s); "
                "visual independence failed: "
                + ", ".join(tool_names)
            )

    @staticmethod
    def _gateway_token() -> str:
        token = os.getenv(
            "OPENCLAW_GATEWAY_TOKEN",
            "",
        ).strip()

        if not token:
            raise RuntimeError(
                "OPENCLAW_GATEWAY_TOKEN is required for "
                "OpenResponses visual inference. Load the "
                "existing OpenClaw Gateway token into the "
                "runner process environment before starting UAT."
            )

        return token

    @staticmethod
    def _openresponses_output_texts(
        value: Any,
    ) -> list[str]:
        texts: list[str] = []

        if isinstance(value, dict):
            item_type = str(value.get("type") or "")
            text = value.get("text")

            if (
                item_type in {"output_text", "text"}
                and isinstance(text, str)
                and text.strip()
            ):
                texts.append(text.strip())

            for child in value.values():
                texts.extend(
                    VisualValidatedTopologyController
                    ._openresponses_output_texts(child)
                )

        elif isinstance(value, list):
            for child in value:
                texts.extend(
                    VisualValidatedTopologyController
                    ._openresponses_output_texts(child)
                )

        return texts

    def _invoke_visual_agent_json(
        self,
        *,
        agent_id: str,
        session_key: str,
        files: list[Path],
        prompt: str,
        receipt_name: str,
    ) -> dict[str, Any]:
        if not files:
            raise RuntimeError(
                f"No actual images supplied for {receipt_name}"
            )

        missing = [
            str(path)
            for path in files
            if not path.is_file()
        ]

        if missing:
            raise RuntimeError(
                "Visual input file(s) are missing for "
                f"{receipt_name}: "
                + ", ".join(missing)
            )

        content: list[dict[str, Any]] = [
            {
                "type": "input_text",
                "text": prompt,
            }
        ]

        safe_files: list[dict[str, Any]] = []

        for path in files:
            mime_type, _encoding = mimetypes.guess_type(
                path.name
            )

            if mime_type == "image/jpg":
                mime_type = "image/jpeg"

            if mime_type not in ALLOWED_VISUAL_MIMES:
                raise RuntimeError(
                    f"Unsupported visual MIME type for {path}: "
                    f"{mime_type!r}"
                )

            raw = path.read_bytes()

            content.append(
                {
                    "type": "input_image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": base64.b64encode(raw).decode(
                            "ascii"
                        ),
                    },
                }
            )

            safe_files.append(
                {
                    "path": str(path),
                    "mime_type": mime_type,
                    "bytes": len(raw),
                }
            )

        request_payload = {
            "model": "openclaw",
            "stream": False,
            "tool_choice": "none",
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": content,
                }
            ],
            "max_output_tokens": (
                OPENRESPONSES_MAX_OUTPUT_TOKENS
            ),
        }

        gateway_url = os.getenv(
            "OPENCLAW_GATEWAY_HTTP_URL",
            OPENRESPONSES_BASE_URL,
        ).strip().rstrip("/")

        if not gateway_url:
            raise RuntimeError(
                "OpenResponses Gateway URL is empty"
            )

        token = self._gateway_token()

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "x-openclaw-agent-id": agent_id,
            "x-openclaw-session-key": session_key,
        }

        visual_request_started_ms = int(
            time.time() * 1000
        )

        try:
            with httpx.Client(
                base_url=gateway_url,
                headers={
                    "Authorization": f"Bearer {token}"
                },
                timeout=self._openresponses_timeout_seconds,
            ) as client:
                response = client.post(
                    "/v1/responses",
                    headers=headers,
                    json=request_payload,
                )
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                "OpenResponses visual request timed out after "
                f"{self._openresponses_timeout_seconds:g}s for "
                f"{agent_id}/{receipt_name}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(
                "OpenResponses visual request failed for "
                f"{agent_id}/{receipt_name}: {exc}"
            ) from exc

        if response.status_code >= 400:
            raise RuntimeError(
                "OpenResponses visual request returned "
                f"HTTP {response.status_code} for "
                f"{agent_id}/{receipt_name}: "
                + response.text[:2000]
            )

        try:
            response_payload = response.json()
        except ValueError as exc:
            raise RuntimeError(
                "OpenResponses visual request did not "
                f"return JSON for {agent_id}/{receipt_name}: "
                + response.text[:1000]
            ) from exc

        self._assert_no_visual_tool_actions(
            session_key=session_key,
            after_ms=visual_request_started_ms,
            receipt_name=receipt_name,
        )

        self.save_json(
            receipt_name + ".json",
            {
                "transport": "openresponses",
                "timeout_seconds": self._openresponses_timeout_seconds,
                "agent_id": agent_id,
                "session_key": session_key,
                "files": safe_files,
                "response_id": response_payload.get("id"),
                "status": response_payload.get("status"),
                "output": response_payload.get("output"),
                "usage": response_payload.get("usage"),
            },
        )

        output_texts = self._openresponses_output_texts(
            response_payload.get("output", [])
        )

        direct_text = response_payload.get("output_text")

        if (
            isinstance(direct_text, str)
            and direct_text.strip()
        ):
            output_texts.append(direct_text.strip())

        if not output_texts:
            raise RuntimeError(
                "OpenResponses returned no assistant output "
                f"for {agent_id}/{receipt_name}"
            )

        return _json_from_payload(
            {
                "text": output_texts[-1],
            },
            context=(
                f"{agent_id} actual-image receipt "
                f"{receipt_name}"
            ),
        )

    def _physical_visual_prompt(self, defect: Defect, bundle: str) -> str:
        return self.defect_physical_prompt(defect, bundle) + f"""

Execution role: cf-physical-model actual-image draft pass.
This is a non-canonical draft. Reinspect all supplied images together and return the complete
physical-model JSON only. Do not rely on an earlier topology cache. The independent validator
has not yet reviewed this proposal.

Do not call any OpenClaw or CLASSIFIRE tool during this visual inference turn.
Use only the supplied retained images and the direct evidence already present in this prompt.
Do not read the existing canonical Physical Model.

Policy: {VISUAL_GATE_POLICY_VERSION}.
"""

    def _validator_prompt(self, defect: Defect, bundle: str, proposal: dict[str, Any]) -> str:
        issue_codes = sorted(VISUAL_VALIDATOR_ISSUE_CODES)
        return f"""You are the independent cf-validator visual-topology gate for CLASSIFIRE.
Inspect ALL supplied images together. They are the same actual retained defect images supplied
to cf-physical-model. Attempt to DISPROVE the draft below; do not repair it and do not make a
new canonical model. Never use or infer from any human UAT reference fixture.

Do not call any OpenClaw or CLASSIFIRE tool during this visual validation turn.
Use only the supplied retained images, the direct evidence already present in this prompt,
and the draft proposal included below. Do not read the existing canonical Physical Model.

Defect: {defect.external_defect_id or defect.defect_code or defect.id}
Direct evidence bundle (secondary to the actual images):
{bundle}

Draft physical topology to challenge:
{json.dumps(proposal, ensure_ascii=False, separators=(",", ":"), default=str)}

Check, at minimum:
- whether different photos are duplicate angles or opposite faces of the same subject;
- whether distinct wall/slab/soffit barrier planes were merged;
- whether separate physical holes were merged or one hole was split into many;
- whether empty/redundant cores were missed or given invented Services;
- whether mixed Services sharing one Opening were collapsed, omitted, or mislinked;
- whether unlike service classes were merged;
- whether homogeneous groups and quantities are defensible from the visible evidence;
- whether material, size, substrate, orientation, or quantity claims exceed the evidence.

Allowed issue codes:
{json.dumps(issue_codes, separators=(",", ":"))}

Return ONLY valid JSON using exactly this shape:
{{
  "verdict": "APPROVED|REJECTED|BLOCKED",
  "observed_opening_count": 0,
  "observed_service_group_count": 0,
  "issues": [
    {{
      "code": "MISSED_OPENING",
      "detail": "specific evidence-backed defect in the draft",
      "evidence_refs": ["photo id or filename"]
    }}
  ],
  "limitations": []
}}

APPROVED means the draft topology is supported by the actual images and no blocking visual issue
remains. REJECTED requires at least one structured issue. BLOCKED means the available images are
insufficient to validate the topology and must state the missing/ambiguous evidence. Counts are
Service GROUP counts, not the sum of quantity values. Policy: {VISUAL_GATE_POLICY_VERSION}.
"""

    def _validator_retry_prompt(
        self,
        defect: Defect,
        bundle: str,
        proposal: dict[str, Any],
        validation_errors: list[str],
    ) -> str:
        return self._validator_prompt(defect, bundle, proposal) + f"""

Your previous validator receipt was structurally invalid and cannot pass the gate.
Receipt errors: {json.dumps(validation_errors, ensure_ascii=False, separators=(",", ":"))}
Reinspect the same images and return one corrected validator JSON object only.
"""

    def _physical_correction_prompt(
        self,
        defect: Defect,
        bundle: str,
        proposal: dict[str, Any],
        validator: dict[str, Any],
    ) -> str:
        return self.defect_physical_prompt(defect, bundle) + f"""

Execution role: cf-physical-model bounded correction pass under {VISUAL_GATE_POLICY_VERSION}.
The independent cf-validator rejected the previous non-canonical draft. Reinspect ALL supplied
images yourself. Treat validator findings as challenge inputs, not as facts to copy blindly.
Return a complete replacement physical-model JSON only.

Previous draft:
{json.dumps(proposal, ensure_ascii=False, separators=(",", ":"), default=str)}

Independent validator receipt:
{json.dumps(validator, ensure_ascii=False, separators=(",", ":"), default=str)}
"""

    def _visual_gate_cache_key(self, bundle: str, files: list[Path]) -> dict[str, Any]:
        return {
            **self._visual_cache_key(bundle, files),
            "visual_gate_policy_version": VISUAL_GATE_POLICY_VERSION,
        }

    def _cached_visual_approved_model(
        self,
        defect_index: int,
        bundle: str,
        files: list[Path],
    ) -> dict[str, Any] | None:
        key_path = self.receipt_dir / f"21-visual-defect-{defect_index:03d}-cache.json"
        model_path = self.receipt_dir / f"21-visual-defect-{defect_index:03d}-approved-model.json"
        validator_path = self.receipt_dir / f"21-visual-defect-{defect_index:03d}-approved-validator.json"
        if not key_path.is_file() or not model_path.is_file() or not validator_path.is_file():
            return None
        try:
            key = json.loads(key_path.read_text(encoding="utf-8"))
            model = json.loads(model_path.read_text(encoding="utf-8"))
            validator = json.loads(validator_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if key != self._visual_gate_cache_key(bundle, files):
            return None
        if str(model.get("status") or "").strip().upper() != "MODEL_SUPPORTED":
            return None
        if _model_completeness_issues(model):
            return None
        if not visual_validator_approved(validator, model):
            return None
        print(f"PASS defect {defect_index} visual gate cache -> retained validator-approved proposal")
        return model

    @staticmethod
    def _insufficient_from_visual_gate(*limitations: str) -> dict[str, Any]:
        return {
            "status": "INSUFFICIENT_EVIDENCE",
            "limitations": [item for item in limitations if item],
            "openings": [],
            "services": [],
        }

    def _synthesise_defect(
        self,
        defect_index: int,
        defect: Defect,
        bundle: str,
    ) -> dict:
        physical_session, validator_session = self._ensure_visual_sessions()
        files, manifest = self._visual_files_for_defect(defect_index, defect)
        self.save_json(f"21-visual-defect-{defect_index:03d}-manifest.json", manifest)

        cached = self._cached_visual_approved_model(defect_index, bundle, files)
        if cached is not None:
            return cached

        proposal = self._invoke_visual_agent_json(
            agent_id="cf-physical-model",
            session_key=physical_session,
            files=files,
            prompt=self._physical_visual_prompt(defect, bundle),
            receipt_name=f"21-visual-defect-{defect_index:03d}-physical-pass-0",
        )

        for correction_pass in range(MAX_VISUAL_CORRECTION_PASSES + 1):
            status = str(proposal.get("status") or "").strip().upper()
            completeness = _model_completeness_issues(proposal) if status == "MODEL_SUPPORTED" else []
            if status != "MODEL_SUPPORTED" or completeness:
                if correction_pass >= MAX_VISUAL_CORRECTION_PASSES:
                    reasons = completeness or list(proposal.get("limitations") or []) or [
                        f"physical visual draft returned status {status or 'MISSING'}"
                    ]
                    return self._insufficient_from_visual_gate(*[str(item) for item in reasons])
                proposal = self._invoke_visual_agent_json(
                    agent_id="cf-physical-model",
                    session_key=physical_session,
                    files=files,
                    prompt=self._topology_retry_prompt(defect, bundle, proposal, completeness),
                    receipt_name=(
                        f"21-visual-defect-{defect_index:03d}-physical-structural-retry-"
                        f"{correction_pass + 1}"
                    ),
                )
                continue

            validator = self._invoke_visual_agent_json(
                agent_id="cf-validator",
                session_key=validator_session,
                files=files,
                prompt=self._validator_prompt(defect, bundle, proposal),
                receipt_name=f"21-visual-defect-{defect_index:03d}-validator-pass-{correction_pass}",
            )
            receipt_errors = validate_visual_validator_payload(validator, proposal)
            if receipt_errors:
                validator = self._invoke_visual_agent_json(
                    agent_id="cf-validator",
                    session_key=validator_session,
                    files=files,
                    prompt=self._validator_retry_prompt(defect, bundle, proposal, receipt_errors),
                    receipt_name=(
                        f"21-visual-defect-{defect_index:03d}-validator-format-retry-"
                        f"{correction_pass}"
                    ),
                )
                receipt_errors = validate_visual_validator_payload(validator, proposal)
                if receipt_errors:
                    self.save_json(
                        f"21-visual-defect-{defect_index:03d}-validator-invalid.json",
                        {"receipt": validator, "errors": receipt_errors},
                    )
                    return self._insufficient_from_visual_gate(
                        "Independent visual-validator receipt remained invalid: "
                        + "; ".join(receipt_errors)
                    )

            if visual_validator_approved(validator, proposal):
                self.save_json(
                    f"21-visual-defect-{defect_index:03d}-approved-model.json",
                    proposal,
                )
                self.save_json(
                    f"21-visual-defect-{defect_index:03d}-approved-validator.json",
                    validator,
                )
                self.save_json(
                    f"21-visual-defect-{defect_index:03d}-cache.json",
                    self._visual_gate_cache_key(bundle, files),
                )
                print(
                    f"PASS defect {defect_index} independent visual gate -> APPROVED "
                    f"({len(proposal.get('openings') or [])} openings, "
                    f"{len(proposal.get('services') or [])} service groups)"
                )
                return proposal

            verdict = str(validator.get("verdict") or "").strip().upper()
            if verdict == "BLOCKED":
                reasons = [
                    str(item.get("detail") or item.get("code") or "")
                    for item in (validator.get("issues") or [])
                    if isinstance(item, dict)
                ] + [str(item) for item in (validator.get("limitations") or [])]
                return self._insufficient_from_visual_gate(
                    "Independent visual validator BLOCKED: " + "; ".join(item for item in reasons if item)
                )

            if correction_pass >= MAX_VISUAL_CORRECTION_PASSES:
                issue_text = "; ".join(
                    f"{item.get('code')}: {item.get('detail')}"
                    for item in (validator.get("issues") or [])
                    if isinstance(item, dict)
                )
                return self._insufficient_from_visual_gate(
                    "Independent visual validator remained REJECTED after bounded corrections: "
                    + issue_text
                )

            proposal = self._invoke_visual_agent_json(
                agent_id="cf-physical-model",
                session_key=physical_session,
                files=files,
                prompt=self._physical_correction_prompt(defect, bundle, proposal, validator),
                receipt_name=(
                    f"21-visual-defect-{defect_index:03d}-physical-correction-"
                    f"{correction_pass + 1}"
                ),
            )

        return self._insufficient_from_visual_gate("Visual gate exhausted without an approved proposal")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild CLASSIFIRE fire-seal physical topology with actual-image cf-physical-model "
            "drafting and independent actual-image cf-validator approval before canonical write."
        )
    )
    parser.add_argument("--run-id")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()

    root = repo_root()
    _receipt_path, receipt = load_receipt(root, args.run_id)
    controller = VisualValidatedTopologyController(
        receipt,
        base_url=args.base_url,
        timeout_seconds=args.timeout_seconds,
    )
    try:
        state = controller.run()
        return 0 if state.get("status") in {
            "PHYSICAL_MODEL_LOCKED",
            "PARTIAL_SOURCE_OR_PHYSICAL_LIMITATION",
        } else 1
    except Exception as exc:
        print(f"CLASSIFIRE visual-validated real-report UAT failed: {exc}", file=sys.stderr)
        return 1
    finally:
        controller.close()


if __name__ == "__main__":
    raise SystemExit(main())
