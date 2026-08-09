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


def health_payload(base_url: str, timeout: float = 2.0) -> dict | None:
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/healthz", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    if isinstance(payload, dict) and payload.get("status") == "ok" and payload.get("product") == "CLASSIFIRE":
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    controller = repo_root / "scripts" / "run_classifire_openclaw_reference_uat.py"
    receipt_dir = repo_root / "data" / "uat" / args.run_id
    receipt_dir.mkdir(parents=True, exist_ok=True)

    managed_process: subprocess.Popen[str] | None = None
    log_handle = None
    try:
        if health_payload(args.base_url) is None:
            parsed = urlparse(args.base_url)
            if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
                raise RuntimeError(
                    "CLASSIFIRE API is unavailable and the UAT launcher only auto-starts a loopback HTTP server. "
                    f"Requested base URL: {args.base_url}"
                )
            port = parsed.port or 80
            bind_host = "127.0.0.1" if parsed.hostname == "localhost" else parsed.hostname
            log_path = receipt_dir / "00-classifire-server.log"
            log_handle = log_path.open("w", encoding="utf-8")
            print(f"CLASSIFIRE API is offline; starting managed UAT server on {bind_host}:{port}...")
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
                    detail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
                    raise RuntimeError(
                        f"Managed CLASSIFIRE UAT server exited with code {managed_process.returncode}. "
                        f"Log tail:\n{detail}"
                    )
                if health_payload(args.base_url) is not None:
                    print("PASS managed CLASSIFIRE API -> healthy")
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError(
                    f"Managed CLASSIFIRE UAT server did not become healthy at {args.base_url}/healthz within 30 seconds. "
                    f"See {log_path}"
                )
        else:
            print("PASS existing CLASSIFIRE API -> healthy")

        command = [
            sys.executable,
            str(controller),
            "--run-id",
            args.run_id,
            "--timeout-seconds",
            str(args.timeout_seconds),
            "--base-url",
            args.base_url,
        ]
        return subprocess.call(command, cwd=repo_root)
    finally:
        if managed_process is not None:
            print("Stopping managed CLASSIFIRE UAT server...")
            terminate_process(managed_process)
        if log_handle is not None:
            log_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
