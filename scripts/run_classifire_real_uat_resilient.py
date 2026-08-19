from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from run_classifire_real_uat_intake import (
    ADMISSION_BOUND_CANONICAL_WRITE_STATUS,
    load_receipt,
    repo_root,
)
from run_classifire_real_uat_integrated import IntegratedEvidenceController

# `tools.effective` is diagnostic inventory only. ROLE_TOOL_CONTRACT governs
# which callable tools each real-UAT agent role may require. Native multimodal
# evidence supplied as OpenResponses `input_image` content is transport input,
# not a callable agent tool and therefore does not belong in this contract.
# CLASSIFIRE plugin calls remain fail-closed at both the OpenClaw plugin
# boundary and the CLASSIFIRE API service-principal scope boundary.
ROLE_TOOL_CONTRACT: dict[str, set[str]] = {
    "cf-intake-evidence": {
        "classifire_register_evidence_observations",
    },
    "cf-physical-model": {
        "classifire_evidence_read",
        "classifire_physical_model_read",
    },
    "cf-validator": {
        "classifire_evidence_read",
        "classifire_physical_model_read",
        "classifire_run_validation",
    },
}

ROLE_SCOPE_CONTRACT: dict[str, set[str]] = {
    "cf-intake-evidence": {
        "evidence:read",
        "evidence:write",
    },
    "cf-physical-model": {
        "evidence:read",
        "physical:read",
    },
    "cf-validator": {
        "evidence:read",
        "physical:read",
        "validation:run",
    },
}

GATEWAY_CALL_TIMEOUT_MS = 120_000
GATEWAY_CALL_PROCESS_TIMEOUT_SECONDS = 140


class ResilientIntegratedController(IntegratedEvidenceController):
    """Integrated UAT without a mandatory `tools.effective` catalog RPC per sub-session."""

    def require_tools(
        self,
        agent_id: str,
        session_key: str,
        tools: set[str],
        receipt_name: str,
    ) -> None:
        expected_tools = ROLE_TOOL_CONTRACT.get(agent_id)
        if expected_tools is None:
            raise RuntimeError(f"No governed CLASSIFIRE UAT role contract exists for {agent_id}")

        missing_from_contract = sorted(tools - expected_tools)
        if missing_from_contract:
            raise RuntimeError(
                f"{agent_id} requests tools outside the governed UAT role contract: "
                + ", ".join(missing_from_contract)
            )

        token_file = Path.home() / ".openclaw" / "classifire-agent-tokens.json"
        if not token_file.is_file():
            raise RuntimeError(f"CLASSIFIRE agent token file is missing: {token_file}")
        token_doc = json.loads(token_file.read_text(encoding="utf-8"))
        if token_doc.get("schema") != "CLASSIFIRE-AGENT-TOKENS-v1":
            raise RuntimeError("Unexpected CLASSIFIRE agent token-file schema")

        tokens = token_doc.get("tokens") or {}
        if not tokens.get(agent_id):
            raise RuntimeError(f"CLASSIFIRE agent token file has no bearer token for {agent_id}")

        expected_scopes = ROLE_SCOPE_CONTRACT.get(agent_id, set())
        persisted_scopes = set((token_doc.get("scopes") or {}).get(agent_id) or [])
        if agent_id == "cf-physical-model":
            retired_scopes = sorted(
                persisted_scopes
                & {
                    "physical:write",
                    "physical:lock",
                    "physical:adjudicated:submit",
                }
            )
            if retired_scopes:
                self.save_json(
                    receipt_name,
                    {
                        "ok": False,
                        "status": ADMISSION_BOUND_CANONICAL_WRITE_STATUS,
                        "reason_code": "STALE_CF_PHYSICAL_MODEL_MUTATION_SCOPE",
                        "agent_id": agent_id,
                        "retired_scopes": retired_scopes,
                        "canonical_write_performed": False,
                        "physical_model_lock_created": False,
                        "next_action": (
                            "Remove stale mutation scopes from cf-physical-model. Only the "
                            "separate admission-bound writer may hold its dedicated submit scope."
                        ),
                    },
                )
                raise RuntimeError(
                    "cf-physical-model has retired mutation scope(s): "
                    + ", ".join(retired_scopes)
                )
        missing_scopes = sorted(expected_scopes - persisted_scopes)
        if missing_scopes:
            raise RuntimeError(
                f"{agent_id} token metadata is missing governed scope(s): "
                + ", ".join(missing_scopes)
            )

        self.save_json(
            receipt_name,
            {
                "ok": True,
                "verification": "local_role_contract_plus_runtime_invoke_enforcement",
                "agent_id": agent_id,
                "session_key_present": bool(session_key),
                "required_tools": sorted(tools),
                "role_contract_tools": sorted(expected_tools),
                "required_scopes": sorted(expected_scopes),
                "persisted_scopes": sorted(persisted_scopes),
                "tools_effective_rpc_skipped": True,
                "runtime_enforcement": (
                    "Actual tools.invoke calls remain subject to the OpenClaw plugin role boundary "
                    "and CLASSIFIRE API service-principal scopes."
                ),
            },
        )
        print(
            f"PASS {agent_id} required tools "
            "(governed local contract; runtime authority enforced on actual invocation)"
        )

    def gateway_call(self, method: str, params: dict, receipt_name: str) -> dict:
        raw_params = json.dumps(params, separators=(",", ":"), ensure_ascii=False)
        result = self.openclaw(
            "gateway",
            "call",
            method,
            "--params",
            raw_params,
            "--timeout",
            str(GATEWAY_CALL_TIMEOUT_MS),
            "--json",
            timeout=GATEWAY_CALL_PROCESS_TIMEOUT_SECONDS,
            check=False,
        )
        raw = "\n".join(x for x in (result.stdout.strip(), result.stderr.strip()) if x)
        self.save_text(receipt_name, raw)
        if result.returncode != 0:
            raise RuntimeError(f"Gateway call {method} failed: {raw}")
        from run_classifire_real_uat_intake import parse_json_envelope

        return parse_json_envelope(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run resilient integrated CLASSIFIRE text + duplicate-aware photo real-report UAT."
        )
    )
    parser.add_argument("--run-id")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()

    root = repo_root()
    _receipt_path, receipt = load_receipt(root, args.run_id)
    controller = ResilientIntegratedController(
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
        print(f"CLASSIFIRE resilient integrated real-report UAT failed: {exc}", file=sys.stderr)
        return 1
    finally:
        controller.close()


if __name__ == "__main__":
    raise SystemExit(main())
