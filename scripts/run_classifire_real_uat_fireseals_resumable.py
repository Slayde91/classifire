from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from run_classifire_real_uat_deterministic import INFER_MODEL
from run_classifire_real_uat_fireseals_bounded import BoundedFireSealFocusedController
from run_classifire_real_uat_intake import load_receipt, repo_root


class ResumableFireSealFocusedController(BoundedFireSealFocusedController):
    """Keep the bounded fire-seal UAT resumable across Gateway inference timeouts.

    Canonical CLASSIFIRE writes remain role-scoped through the controlled API.
    OpenClaw remains the AI runtime. A local/in-process OpenClaw model probe is
    used only when the equivalent Gateway model probe fails specifically with a
    GatewayTransportError timeout. Business/model validation failures do not
    trigger this fallback.
    """

    @staticmethod
    def _is_gateway_timeout(exc: BaseException) -> bool:
        text = str(exc).lower()
        return "gatewaytransporterror" in text and "gateway timeout" in text

    def _local_infer_model(
        self,
        *,
        prompt: str,
        receipt_name: str,
        files: list[Path] | None = None,
        thinking: str = "medium",
    ) -> dict:
        command = [
            "infer",
            "model",
            "run",
            "--local",
            "--model",
            INFER_MODEL,
            "--thinking",
            thinking,
            "--prompt",
            prompt,
        ]
        for file in files or []:
            command.extend(["--file", str(file)])
        command.append("--json")

        print(
            f"RETRY {receipt_name} -> Gateway inference timed out; "
            "using OpenClaw local/in-process model transport"
        )
        result = self.openclaw(
            *command,
            timeout=self.timeout_seconds + 60,
            check=False,
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if stdout:
            self.save_text(receipt_name + ".local-fallback.stdout.json", stdout)
        if stderr:
            self.save_text(receipt_name + ".local-fallback.stderr.txt", stderr)
        if result.returncode != 0:
            detail = "\n".join(part for part in (stdout, stderr) if part)
            raise RuntimeError(
                f"OpenClaw local inference fallback failed for {receipt_name} "
                f"with exit code {result.returncode}: {detail}"
            )

        payload = self._parse_infer_envelope(
            stdout,
            context=receipt_name + " local fallback",
        )
        self.save_json(receipt_name + ".local-fallback.json", payload)
        if payload.get("ok") is False or payload.get("status") in {"error", "timeout"}:
            raise RuntimeError(
                "OpenClaw local inference fallback returned failure: "
                + json.dumps(payload)
            )
        return payload

    def infer_model(
        self,
        *,
        prompt: str,
        receipt_name: str,
        files: list[Path] | None = None,
        thinking: str = "medium",
    ) -> dict:
        try:
            return super().infer_model(
                prompt=prompt,
                receipt_name=receipt_name,
                files=files,
                thinking=thinking,
            )
        except RuntimeError as exc:
            if not self._is_gateway_timeout(exc):
                raise
            return self._local_infer_model(
                prompt=prompt,
                receipt_name=receipt_name,
                files=files,
                thinking=thinking,
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Resume the retained CLASSIFIRE fire-seal/penetration real-report UAT "
            "with bounded evidence, cache reuse and an OpenClaw local-transport "
            "fallback only for Gateway inference timeouts."
        )
    )
    parser.add_argument("--run-id")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()

    root = repo_root()
    _receipt_path, receipt = load_receipt(root, args.run_id)
    controller = ResumableFireSealFocusedController(
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
        print(
            f"CLASSIFIRE resumable fire-seal real-report UAT failed: {exc}",
            file=sys.stderr,
        )
        return 1
    finally:
        controller.close()


if __name__ == "__main__":
    raise SystemExit(main())
