from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from run_classifire_openclaw_reference_uat import Controller, parse_json_envelope

GATEWAY_RPC_TIMEOUT_MS = 30_000
GATEWAY_RPC_RETRIES = 2


def health_payload(base_url: str, timeout: float = 2.0) -> dict | None:
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/healthz", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    if (
        isinstance(payload, dict)
        and payload.get("status") == "ok"
        and payload.get("product") == "CLASSIFIRE"
    ):
        return payload
    return None


def terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


class ResilientController(Controller):
    """Reference-UAT controller with explicit OpenClaw RPC budgets and retry."""

    def gateway_call(self, method: str, params: dict, receipt_name: str) -> dict:
        params_json = json.dumps(params, separators=(",", ":"), ensure_ascii=False)
        last_detail = ""

        for attempt in range(1, GATEWAY_RPC_RETRIES + 1):
            result = self.openclaw(
                "gateway",
                "call",
                method,
                "--params",
                params_json,
                "--timeout",
                str(GATEWAY_RPC_TIMEOUT_MS),
                "--json",
                timeout=45,
                check=False,
            )
            raw = result.stdout.strip()
            stderr = result.stderr.strip()

            if result.returncode == 0:
                self.save(receipt_name, raw)
                if stderr:
                    self.save(f"{receipt_name}.stderr.txt", stderr)
                return parse_json_envelope(raw)

            last_detail = "\n".join(part for part in (raw, stderr) if part)
            compact = last_detail.replace(" ", "").lower()
            is_timeout = (
                "gateway timeout" in last_detail.lower()
                or '"kind":"timeout"' in compact
            )
            if is_timeout and attempt < GATEWAY_RPC_RETRIES:
                print(
                    f"OpenClaw Gateway RPC {method} timed out after "
                    f"{GATEWAY_RPC_TIMEOUT_MS}ms; retrying once with the same request identity..."
                )
                time.sleep(2)
                continue

            self.save(f"{receipt_name}.error.txt", last_detail)
            raise RuntimeError(
                f"OpenClaw Gateway RPC {method} failed with exit code "
                f"{result.returncode}: {last_detail}"
            )

        raise RuntimeError(f"OpenClaw Gateway RPC {method} failed: {last_detail}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    receipt_dir = repo_root / "data" / "uat" / args.run_id
    receipt_dir.mkdir(parents=True, exist_ok=True)

    managed_process: subprocess.Popen[str] | None = None
    log_handle = None
    try:
        if health_payload(args.base_url) is None:
            parsed = urlparse(args.base_url)
            if (
                parsed.scheme != "http"
                or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            ):
                raise RuntimeError(
                    "CLASSIFIRE API is unavailable and the UAT launcher only auto-starts "
                    "a loopback HTTP server. "
                    f"Requested base URL: {args.base_url}"
                )
            port = parsed.port or 80
            bind_host = "127.0.0.1" if parsed.hostname == "localhost" else parsed.hostname
            log_path = receipt_dir / "00-classifire-server.log"
            log_handle = log_path.open("w", encoding="utf-8")
            print(
                f"CLASSIFIRE API is offline; starting managed UAT server on "
                f"{bind_host}:{port}..."
            )
            managed_process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "classifire.main:app",
                    "--host",
                    bind_host,
                    "--port",
                    str(port),
                    "--log-level",
                    "info",
                ],
                cwd=repo_root,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
            )

            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if managed_process.poll() is not None:
                    log_handle.flush()
                    detail = log_path.read_text(
                        encoding="utf-8", errors="replace"
                    )[-4000:]
                    raise RuntimeError(
                        f"Managed CLASSIFIRE UAT server exited with code "
                        f"{managed_process.returncode}. Log tail:\n{detail}"
                    )
                if health_payload(args.base_url) is not None:
                    print("PASS managed CLASSIFIRE API -> healthy")
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError(
                    f"Managed CLASSIFIRE UAT server did not become healthy at "
                    f"{args.base_url}/healthz within 30 seconds. See {log_path}"
                )
        else:
            print("PASS existing CLASSIFIRE API -> healthy")

        ResilientController(
            args.run_id,
            args.timeout_seconds,
            args.base_url,
        ).run()
        return 0
    finally:
        if managed_process is not None:
            print("Stopping managed CLASSIFIRE UAT server...")
            terminate_process(managed_process)
        if log_handle is not None:
            log_handle.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("UAT cancelled.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"CLASSIFIRE managed UAT launcher failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
