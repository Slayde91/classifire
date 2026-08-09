from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def _candidate_openclaw_entries() -> list[Path]:
    candidates: list[Path] = []

    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "npm" / "node_modules" / "openclaw" / "openclaw.mjs")

    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm:
        try:
            result = subprocess.run(
                [npm, "root", "-g"],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
            if result.returncode == 0 and result.stdout.strip():
                candidates.append(Path(result.stdout.strip()) / "openclaw" / "openclaw.mjs")
        except (OSError, subprocess.SubprocessError):
            pass

    # Common Unix/global-node fallbacks keep the helper portable outside Windows.
    for root in (Path("/usr/local/lib/node_modules"), Path("/usr/lib/node_modules")):
        candidates.append(root / "openclaw" / "openclaw.mjs")

    return candidates


def resolve_openclaw_entry() -> Path:
    for candidate in _candidate_openclaw_entries():
        if candidate.is_file():
            return candidate
    raise RuntimeError(
        "Unable to locate the OpenClaw CLI entry module. Expected a global OpenClaw installation "
        "such as %APPDATA%\\npm\\node_modules\\openclaw\\openclaw.mjs."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Call an OpenClaw Gateway RPC with argv-safe JSON transport."
    )
    parser.add_argument("--method", required=True)
    parser.add_argument("--params-file", required=True)
    parser.add_argument("--timeout-ms", type=int, default=30000)
    args = parser.parse_args()

    params_path = Path(args.params_file)
    payload = json.loads(params_path.read_text(encoding="utf-8"))
    params_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    node = shutil.which("node") or shutil.which("node.exe")
    if not node:
        raise RuntimeError("node.exe/node is not available on PATH.")
    openclaw_entry = resolve_openclaw_entry()

    command = [
        node,
        str(openclaw_entry),
        "gateway",
        "call",
        args.method,
        "--params",
        params_json,
        "--timeout",
        str(args.timeout_ms),
        "--json",
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)

    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # fail closed with a concise diagnostic for PowerShell
        print(f"OpenClaw RPC helper failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
