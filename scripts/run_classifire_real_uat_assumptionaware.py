from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

from classifire.canonical_models import Defect
from run_classifire_real_uat_intake import load_receipt, repo_root
from run_classifire_real_uat_resilient import ResilientIntegratedController


DEFAULT_ASSUMED_FRL = "-/120/120"
DEFAULT_ASSUMED_FRL_NOTE = (
    "FRL not provided in source report; -/120/120 (120 minutes integrity/insulation) "
    "assumed for estimating only. Verify the required FRL before technical approval or Human Release."
)
DIRECT_API_TIMEOUT_SECONDS = 60


class AssumptionAwareController(ResilientIntegratedController):
    """Integrated real-report UAT with evidence-based estimation defaults.

    OpenClaw/GPT remains the reasoning engine. Canonical CLASSIFIRE reads/writes use the
    role-scoped loopback API directly in this runner so Gateway `tools.invoke` transport
    latency cannot abort a real-report UAT. The API still authenticates the same controlled
    service-principal bearer token, enforces its scope, and writes the normal audit events.
    """

    def _token_for_agent(self, agent_id: str) -> str:
        token_file = Path.home() / ".openclaw" / "classifire-agent-tokens.json"
        if not token_file.is_file():
            raise RuntimeError(f"CLASSIFIRE agent token file is missing: {token_file}")
        payload = json.loads(token_file.read_text(encoding="utf-8"))
        if payload.get("schema") != "CLASSIFIRE-AGENT-TOKENS-v1":
            raise RuntimeError("Unexpected CLASSIFIRE agent token-file schema")
        token = str((payload.get("tokens") or {}).get(agent_id) or "").strip()
        if not token:
            raise RuntimeError(f"CLASSIFIRE token file has no bearer token for {agent_id}")
        return token

    def _direct_api_request(
        self,
        agent_id: str,
        *,
        path: str,
        method: str,
        body: dict | None,
        receipt_name: str,
        require_ok: bool,
    ) -> dict:
        token = self._token_for_agent(agent_id)
        data = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Classifire-Agent-ID": agent_id,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=DIRECT_API_TIMEOUT_SECONDS) as response:
                raw = response.read().decode("utf-8", errors="replace")
                status = int(response.status)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            status = int(exc.code)
            result = {
                "ok": False,
                "transport": "direct_classifire_api",
                "agent_id": agent_id,
                "http_status": status,
                "error": raw,
            }
            self.save_json(receipt_name, result)
            if require_ok:
                raise RuntimeError(
                    f"CLASSIFIRE direct API {method} {path} failed with HTTP {status}: {raw}"
                ) from exc
            return result
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"CLASSIFIRE direct API {method} {path} could not be reached: {exc}"
            ) from exc

        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        result = {
            "ok": 200 <= status < 300,
            "transport": "direct_classifire_api",
            "agent_id": agent_id,
            "http_status": status,
            "result": parsed,
        }
        self.save_json(receipt_name, result)
        if require_ok and result["ok"] is not True:
            raise RuntimeError(f"CLASSIFIRE direct API call failed: {json.dumps(result)}")
        return result

    def invoke_tool(
        self,
        agent_id: str,
        session_key: str,
        tool_name: str,
        tool_args: dict,
        receipt_name: str,
        *,
        require_ok: bool = True,
    ) -> dict:
        estimate_id = str(tool_args.get("estimate_id") or self.estimate_id)
        if estimate_id != self.estimate_id:
            raise RuntimeError(
                f"Controlled UAT tool request targets unexpected estimate {estimate_id}"
            )

        if tool_name == "classifire_register_evidence_observations":
            return self._direct_api_request(
                agent_id,
                path=f"/api/v1/agent/estimates/{estimate_id}/evidence/register",
                method="POST",
                body={"observations": tool_args.get("observations") or []},
                receipt_name=receipt_name,
                require_ok=require_ok,
            )
        if tool_name == "classifire_evidence_read":
            return self._direct_api_request(
                agent_id,
                path=f"/api/v1/agent/estimates/{estimate_id}/evidence",
                method="GET",
                body=None,
                receipt_name=receipt_name,
                require_ok=require_ok,
            )
        if tool_name == "classifire_submit_initial_physical_model":
            return self._direct_api_request(
                agent_id,
                path=f"/api/v1/agent/estimates/{estimate_id}/physical-model/initial",
                method="POST",
                body={
                    "openings": tool_args.get("openings") or [],
                    "services": tool_args.get("services") or [],
                },
                receipt_name=receipt_name,
                require_ok=require_ok,
            )
        if tool_name == "classifire_lock_physical_model":
            return self._direct_api_request(
                agent_id,
                path=f"/api/v1/agent/estimates/{estimate_id}/physical-model/lock",
                method="POST",
                body={
                    "reason": tool_args.get("reason")
                    or "Assumption-aware deterministic real-UAT Physical Model Lock"
                },
                receipt_name=receipt_name,
                require_ok=require_ok,
            )
        return super().invoke_tool(
            agent_id,
            session_key,
            tool_name,
            tool_args,
            receipt_name,
            require_ok=require_ok,
        )

    def defect_physical_prompt(self, defect: Defect, evidence_text: str) -> str:
        base = super().defect_physical_prompt(defect, evidence_text)
        return base + f"""

Mandatory CLASSIFIRE estimating-assumption policy for this run:
- Use this evidence hierarchy for physical facts: (1) explicit defect-linked report text, then
  (2) reconciled full-resolution / zoomed photos, then (3) a combined AI best estimate.
- Missing exact service SIZE is NOT by itself a reason to stop. Make the most defensible size estimate from
  descriptions, visible proportions, fittings, insulation, known service type and nearby scale clues.
  For a pipe-like service, provide a best-estimate nominal_size_mm and/or outside_diameter_mm where reasonably
  possible. For cable/duct/bundle geometry use the most applicable numeric fields. Mark an estimated value
  provisional, reduce confidence appropriately, and state in notes that the size was AI-estimated from evidence.
- Missing exact service QUANTITY is NOT by itself a reason to stop. Use reconciled distinct physical services
  plus report wording to make the best defensible integer count. A singular named service may support quantity 1;
  wording such as "multiple" must be reconciled against visible distinct services. Never use photograph count as
  service quantity, and never default to quantity 1 merely because there is one defect row.
- When quantity is best-estimated rather than explicitly stated, set evidence_status and relationship_status to
  provisional or inferred as appropriate, lower confidence, and record the counting basis in notes/source_reference.
- If an exact value cannot be known but a rational best estimate can be made from the supplied evidence, prefer a
  clearly labelled provisional estimate over INSUFFICIENT_EVIDENCE. Use INSUFFICIENT_EVIDENCE only when there is
  genuinely no rational basis to estimate the physical scope.
- FRL must come from explicit source evidence when supplied. Do NOT guess FRL from appearance. If no FRL is
  provided, leave frl null in your proposal; the CLASSIFIRE controller will deterministically apply the estimating
  default {DEFAULT_ASSUMED_FRL} and annotate that it was assumed.
- Missing FRL alone is never a reason to return INSUFFICIENT_EVIDENCE in this estimating workflow.
- Proposed treatment wording remains clue-only. Do not let it bypass Package 15/17 technical selection.
"""

    @staticmethod
    def _append_note(existing: object, note: str) -> str:
        current = str(existing or "").strip()
        if not current:
            return note
        if note.lower() in current.lower():
            return current
        return f"{current} | {note}"

    def _apply_estimation_defaults(self, model: dict) -> dict:
        openings = model.get("openings")
        if isinstance(openings, list):
            for row in openings:
                if not isinstance(row, dict):
                    continue
                frl = str(row.get("frl") or "").strip().lower()
                if frl in {"", "unknown", "not provided", "n/a", "none", "null"}:
                    row["frl"] = DEFAULT_ASSUMED_FRL
                    row["notes"] = self._append_note(
                        row.get("notes"),
                        DEFAULT_ASSUMED_FRL_NOTE,
                    )

        services = model.get("services")
        if isinstance(services, list):
            for row in services:
                if not isinstance(row, dict):
                    continue
                notes = str(row.get("notes") or "")
                quantity = row.get("quantity")
                try:
                    quantity_value = float(quantity)
                except (TypeError, ValueError):
                    quantity_value = 0.0
                if quantity_value > 0 and any(
                    marker in notes.lower()
                    for marker in ("estimate", "estimated", "inferred", "provisional")
                ):
                    row["evidence_status"] = "provisional"
                    row["relationship_status"] = "provisional"
        return model

    def _validate_and_remap_defect_model(
        self,
        defect: Defect,
        model: dict,
        opening_start: int,
        service_start: int,
    ):
        self._apply_estimation_defaults(model)
        return super()._validate_and_remap_defect_model(
            defect,
            model,
            opening_start,
            service_start,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run CLASSIFIRE real-report UAT with AI best-estimate size/quantity policy, "
            "120-minute missing-FRL estimating assumption, and direct controlled API writes."
        )
    )
    parser.add_argument("--run-id")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()

    root = repo_root()
    _receipt_path, receipt = load_receipt(root, args.run_id)
    controller = AssumptionAwareController(
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
        print(f"CLASSIFIRE assumption-aware real-report UAT failed: {exc}", file=sys.stderr)
        return 1
    finally:
        controller.close()


if __name__ == "__main__":
    raise SystemExit(main())
