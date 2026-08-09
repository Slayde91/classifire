from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request


def parse_json_envelope(raw: str) -> dict:
    text = raw.strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise RuntimeError(f"OpenClaw did not return a JSON object. Output: {text}")
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise RuntimeError("Expected a JSON object from OpenClaw.")
    return value


def locate_openclaw_entry() -> tuple[str, str]:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("node.exe was not found on PATH.")

    candidates: list[Path] = []
    explicit = os.environ.get("OPENCLAW_CLI_MJS")
    if explicit:
        candidates.append(Path(explicit))

    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "npm" / "node_modules" / "openclaw" / "openclaw.mjs")

    command = shutil.which("openclaw")
    if command:
        candidates.append(Path(command).resolve().parent / "node_modules" / "openclaw" / "openclaw.mjs")

    for candidate in candidates:
        if candidate.is_file():
            return node, str(candidate)

    checked = ", ".join(str(path) for path in candidates) or "(no candidates)"
    raise RuntimeError(
        "OpenClaw CLI entrypoint was not found. Checked: "
        f"{checked}. Set OPENCLAW_CLI_MJS to openclaw.mjs if installed elsewhere."
    )


class Controller:
    def __init__(self, run_id: str, timeout_seconds: int, base_url: str) -> None:
        self.run_id = run_id
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url.rstrip("/")
        self.repo_root = Path(__file__).resolve().parents[1]
        self.helper = self.repo_root / "scripts" / "classifire_reference_uat.py"
        self.receipt_dir = self.repo_root / "data" / "uat" / run_id
        self.receipt_dir.mkdir(parents=True, exist_ok=True)
        node, openclaw_mjs = locate_openclaw_entry()
        self.openclaw_prefix = [node, openclaw_mjs]

    def save(self, name: str, content: str) -> None:
        (self.receipt_dir / name).write_text(content, encoding="utf-8")

    def run_process(self, command: list[str], *, timeout: int | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            command,
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout or self.timeout_seconds,
            check=False,
        )
        if check and result.returncode != 0:
            detail = "\n".join(x for x in (result.stdout.strip(), result.stderr.strip()) if x)
            raise RuntimeError(f"Command failed with exit code {result.returncode}: {detail}")
        return result

    def openclaw(self, *args: str, timeout: int | None = None, check: bool = True):
        return self.run_process([*self.openclaw_prefix, *args], timeout=timeout, check=check)

    def helper_call(self, *args: str) -> dict:
        result = self.run_process([sys.executable, str(self.helper), *args], timeout=180)
        raw = result.stdout.strip()
        if not raw:
            raise RuntimeError(f"CLASSIFIRE UAT helper returned no JSON for {' '.join(args)}.")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise RuntimeError("CLASSIFIRE UAT helper did not return a JSON object.")
        return value

    def preflight(self) -> None:
        print("Validating OpenClaw configuration...")
        result = self.openclaw("config", "validate", "--json")
        print(result.stdout.strip())

        print("Checking live OpenClaw Gateway RPC...")
        status = self.openclaw("gateway", "status", "--require-rpc", "--timeout", "30000", timeout=40, check=False)
        if status.returncode != 0:
            if status.stdout.strip():
                print(status.stdout.strip())
            if status.stderr.strip():
                print(status.stderr.strip())
            print("Gateway RPC probe failed; restarting once and retrying...")
            restart = self.openclaw("gateway", "restart", timeout=60, check=False)
            if restart.returncode != 0:
                detail = "\n".join(x for x in (restart.stdout.strip(), restart.stderr.strip()) if x)
                raise RuntimeError(f"OpenClaw Gateway restart failed: {detail}")
            time.sleep(5)
            status = self.openclaw("gateway", "status", "--require-rpc", "--timeout", "30000", timeout=40, check=False)
        if status.returncode != 0:
            detail = "\n".join(x for x in (status.stdout.strip(), status.stderr.strip()) if x)
            raise RuntimeError(f"OpenClaw Gateway RPC preflight failed after retry: {detail}")
        print(status.stdout.strip())

        print("Checking CLASSIFIRE API...")
        with urllib.request.urlopen(f"{self.base_url}/healthz", timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("status") != "ok" or payload.get("product") != "CLASSIFIRE":
            raise RuntimeError(f"CLASSIFIRE API health check failed: {payload}")

    def prepare(self) -> dict:
        print("Preparing governed synthetic reference estimate...")
        fixture = self.helper_call("prepare", "--run-id", self.run_id)
        self.save("00-fixture.json", json.dumps(fixture, indent=2))
        if not fixture.get("ok"):
            raise RuntimeError(f"Reference UAT fixture creation returned failure: {fixture}")
        return fixture

    def verify(self, estimate_id: str, expected_stage: str, receipt_name: str) -> dict:
        payload = self.helper_call("verify", "--estimate-id", estimate_id, "--expect-stage", expected_stage)
        self.save(receipt_name, json.dumps(payload, indent=2))
        if not payload.get("ok"):
            errors = "; ".join(str(x) for x in payload.get("errors", []))
            raise RuntimeError(
                f"CLASSIFIRE UAT verification failed for expected stage '{expected_stage}': {errors}\n"
                f"{json.dumps(payload, indent=2)}"
            )
        print(f"PASS CLASSIFIRE stage -> {expected_stage}")
        return payload

    def initialize_session(self, stage: str, agent_id: str) -> str:
        alias = f"classifire-uat-{self.run_id}-{stage}"
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".txt",
            prefix=f"classifire-uat-{self.run_id}-{stage}-", delete=False,
        ) as handle:
            handle.write(
                "Controlled CLASSIFIRE UAT session readiness check. Reply exactly READY. "
                "Do not call any tools. Mandatory governed actions are invoked separately by the UAT controller."
            )
            prompt_path = handle.name

        try:
            print(f"Opening {stage} session for {agent_id}...")
            result = self.openclaw(
                "agent", "--agent", agent_id, "--session-key", alias,
                "--message-file", prompt_path, "--timeout", str(self.timeout_seconds),
                "--verbose", "full", "--json", timeout=self.timeout_seconds + 30,
            )
            raw = result.stdout.strip()
            self.save(f"{stage}.session.json", raw)
            if result.stderr.strip():
                self.save(f"{stage}.session.stderr.txt", result.stderr)
            envelope = parse_json_envelope(raw)
            session_key = (
                envelope.get("result", {}).get("meta", {})
                .get("systemPromptReport", {}).get("sessionKey")
            )
            if not session_key:
                session_key = f"agent:{agent_id}:{alias}"
            if not str(session_key).startswith(f"agent:{agent_id}:"):
                raise RuntimeError(
                    f"OpenClaw returned session '{session_key}' for {stage}, which does not belong to agent {agent_id}."
                )
            print(f"PASS OpenClaw session {stage} / {agent_id}")
            return str(session_key)
        finally:
            try:
                Path(prompt_path).unlink()
            except OSError:
                pass

    def gateway_call(self, method: str, params: dict, receipt_name: str) -> dict:
        params_json = json.dumps(params, separators=(",", ":"), ensure_ascii=False)
        result = self.openclaw(
            "gateway", "call", method, "--params", params_json, "--json", timeout=120,
        )
        raw = result.stdout.strip()
        self.save(receipt_name, raw)
        if result.stderr.strip():
            self.save(f"{receipt_name}.stderr.txt", result.stderr)
        return parse_json_envelope(raw)

    def assert_effective_tool(self, stage: str, agent_id: str, session_key: str, tool_name: str) -> None:
        payload = self.gateway_call("tools.effective", {"sessionKey": session_key}, f"{stage}.effective.json")
        if tool_name not in json.dumps(payload, separators=(",", ":")):
            raise RuntimeError(
                f"{agent_id} does not have effective OpenClaw tool {tool_name} in session {session_key}."
            )

    def invoke_tool(
        self, stage: str, agent_id: str, session_key: str,
        tool_name: str, tool_args: dict, receipt_name: str,
    ) -> dict:
        self.assert_effective_tool(stage, agent_id, session_key, tool_name)
        params = {
            "name": tool_name,
            "args": tool_args,
            "sessionKey": session_key,
            "agentId": agent_id,
            "idempotencyKey": f"classifire-uat-{self.run_id}-{stage}-{tool_name}-{receipt_name}",
        }
        print(f"Invoking {tool_name} as {agent_id}...")
        payload = self.gateway_call("tools.invoke", params, receipt_name)
        invoke_ok = payload.get("ok")
        if invoke_ok is None and isinstance(payload.get("result"), dict):
            invoke_ok = payload["result"].get("ok")
        if invoke_ok is not True:
            raise RuntimeError(
                f"OpenClaw policy/tool invocation returned ok=false for {tool_name}/{agent_id}. {json.dumps(payload)}"
            )
        print(f"PASS tool {tool_name} / {agent_id}")
        return payload

    def run(self) -> None:
        print("CLASSIFIRE controlled OpenClaw reference UAT")
        print(f"Run ID: {self.run_id}")
        print(f"Receipts: {self.receipt_dir}")
        self.preflight()
        fixture = self.prepare()

        estimate_id = str(fixture["estimate_id"])
        opening_id = str(fixture["opening_id"])
        variant_id = str(fixture["variant_id"])
        pricing_entry_id = str(fixture["pricing_entry_id"])
        self.verify(estimate_id, "opening_specific_technical_search", "01-initial-state.json")

        technical_agent = "cf-technical-system"
        technical_session = self.initialize_session("10-technical", technical_agent)
        self.invoke_tool("10-technical", technical_agent, technical_session, "classifire_workflow_status", {"estimate_id": estimate_id}, "10a-technical-workflow.json")
        self.invoke_tool("10-technical", technical_agent, technical_session, "classifire_technical_search", {"opening_id": opening_id}, "10b-technical-search.json")
        self.invoke_tool(
            "10-technical", technical_agent, technical_session, "classifire_select_repair_strategy",
            {
                "opening_id": opening_id,
                "variant_id": variant_id,
                "match_classification": "opening_specific_candidate",
                "treatment_description": "Controlled reference UAT exact Package 15 collar treatment",
                "assumptions": [], "limitations": [],
            },
            "10c-technical-select.json",
        )
        self.invoke_tool("10-technical", technical_agent, technical_session, "classifire_lock_repair_strategy", {"opening_id": opening_id}, "10d-technical-lock.json")
        after_technical = self.verify(estimate_id, "quantity_and_labour", "11-after-technical.json")
        required_components = after_technical.get("required_components") or []
        if len(required_components) != 1:
            raise RuntimeError("Reference UAT expected exactly one Package 15 required component after technical lock.")
        required_component_id = str(required_components[0]["id"])

        quantity_agent = "cf-physical-model"
        quantity_session = self.initialize_session("20-quantity", quantity_agent)
        self.invoke_tool("20-quantity", quantity_agent, quantity_session, "classifire_workflow_status", {"estimate_id": estimate_id}, "20a-quantity-workflow.json")
        self.invoke_tool(
            "20-quantity", quantity_agent, quantity_session, "classifire_derive_quantity_labour",
            {"estimate_id": estimate_id, "component_inputs": {}, "labour_adjustments": {}},
            "20b-quantity-derive.json",
        )
        self.verify(estimate_id, "commercial_pricing_and_recovery", "21-after-quantity.json")

        commercial_agent = "cf-commercial-engine"
        commercial_session = self.initialize_session("30-commercial", commercial_agent)
        self.invoke_tool("30-commercial", commercial_agent, commercial_session, "classifire_workflow_status", {"estimate_id": estimate_id}, "30a-commercial-workflow.json")
        self.invoke_tool("30-commercial", commercial_agent, commercial_session, "classifire_required_components", {"estimate_id": estimate_id}, "30b-required-components.json")
        self.invoke_tool("30-commercial", commercial_agent, commercial_session, "classifire_package14_recommendation", {"component_id": required_component_id}, "30c-package14-recommendation.json")
        self.invoke_tool(
            "30-commercial", commercial_agent, commercial_session, "classifire_derive_commercial",
            {
                "estimate_id": estimate_id,
                "library_selections": {}, "parameterised_selections": {},
                "component_builds": {}, "expert_estimates": {},
            },
            "30d-commercial-derive.json",
        )
        after_commercial = self.verify(estimate_id, "independent_validation", "31-after-commercial.json")
        methods = after_commercial.get("commercial_methods") or []
        if len(methods) != 1 or str(methods[0].get("selected_pricing_method")) != "Exact Library Match":
            raise RuntimeError(
                "Reference UAT did not retain exactly one Exact Library Match commercial method for "
                f"{pricing_entry_id}."
            )

        validator_agent = "cf-validator"
        validator_session = self.initialize_session("40-validation", validator_agent)
        self.invoke_tool("40-validation", validator_agent, validator_session, "classifire_workflow_status", {"estimate_id": estimate_id}, "40a-validation-workflow.json")
        self.invoke_tool("40-validation", validator_agent, validator_session, "classifire_run_validation", {"estimate_id": estimate_id}, "40b-validation-run.json")
        self.verify(estimate_id, "validated_snapshot", "41-after-validation.json")

        output_agent = "cf-output"
        output_session = self.initialize_session("50-output", output_agent)
        self.invoke_tool("50-output", output_agent, output_session, "classifire_workflow_status", {"estimate_id": estimate_id}, "50a-output-workflow.json")
        self.invoke_tool(
            "50-output", output_agent, output_session, "classifire_lock_snapshot",
            {"estimate_id": estimate_id, "reason": "Controlled OpenClaw reference UAT after passing deterministic validation"},
            "50b-snapshot-lock.json",
        )
        self.invoke_tool("50-output", output_agent, output_session, "classifire_render_output", {"estimate_id": estimate_id, "artifact_type": "technical-xlsx"}, "50c-technical-xlsx.json")
        self.invoke_tool("50-output", output_agent, output_session, "classifire_render_output", {"estimate_id": estimate_id, "artifact_type": "proposal-xlsx"}, "50d-proposal-xlsx.json")
        final = self.verify(estimate_id, "human_release", "51-final-state.json")

        print("Recording CF-UAT-001 review receipt in Mission Control...")
        mc = self.helper_call("receipt", "--run-id", self.run_id, "--estimate-id", estimate_id)
        self.save("60-mission-control-review.json", json.dumps(mc, indent=2))
        if not mc.get("ok") or mc.get("status") != "review":
            raise RuntimeError(f"Mission Control did not accept CF-UAT-001 into review. {json.dumps(mc)}")
        print("PASS Mission Control CF-UAT-001 -> review")

        print()
        print("CLASSIFIRE controlled multi-agent reference UAT PASSED.")
        print(f"Estimate: {final.get('estimate_reference')}")
        print(f"Final stage: {(final.get('workflow') or {}).get('stage')}")
        print(f"Snapshot: {final.get('snapshot_hash')}")
        print(f"Certificate: {final.get('certificate_hash')}")
        print(f"Human Release approvals: {final.get('human_release_approval_count')} (must be 0)")
        print("Mission Control: CF-UAT-001 is in review")
        print(f"Receipts retained at: {self.receipt_dir}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=time.strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    args = parser.parse_args()
    try:
        Controller(args.run_id, args.timeout_seconds, args.base_url).run()
        return 0
    except KeyboardInterrupt:
        print("UAT cancelled.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"CLASSIFIRE UAT failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
