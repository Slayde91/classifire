"""Actual CLI/socket checks against owned synthetic daemons, never an operational scanner."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


@pytest.mark.parametrize("mode", ["current", "stale", "bad_ping"])
def test_scanner_only_subprocess_sends_no_file_and_creates_no_state(tmp_path, mode):
    root = Path(__file__).resolve().parents[1]
    workspace = tmp_path / "empty diagnostic workspace"
    workspace.mkdir()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(15)
    port = listener.getsockname()[1]
    commands = []
    failures = []
    stamp = datetime.now(UTC) - timedelta(days=8 if mode == "stale" else 0)
    version = "ClamAV 1.5.4/28108/" + stamp.strftime("%a %b %d %H:%M:%S %Y")

    def serve():
        try:
            for expected in [b"zPING\0"] if mode == "bad_ping" else [b"zPING\0", b"zVERSION\0"]:
                with listener.accept()[0] as connection:
                    connection.settimeout(5)
                    command = bytearray()
                    while not command.endswith(b"\0") and len(command) < 32:
                        chunk = connection.recv(1)
                        assert chunk, "Diagnostic closed before completing its command"
                        command.extend(chunk)
                    commands.append(bytes(command))
                    assert command == expected
                    reply = (
                        ("INVALID" if mode == "bad_ping" else "PONG")
                        if expected == b"zPING\0"
                        else version
                    )
                    connection.sendall(reply.encode("ascii") + b"\0")
        except Exception as exc:
            failures.append(repr(exc))

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    env = dict(os.environ)
    for key in list(env):
        if key.upper().startswith(("CLASSIFIRE_", "QUANTIFIRE_", "PFEOS_", "OPENAI_")):
            env.pop(key)
    env.update(
        PYTHONPATH=str(root / "src"),
        PYTHONDONTWRITEBYTECODE="1",
        CLASSIFIRE_ENV="test",
        CLASSIFIRE_DATABASE_URL="sqlite:///./must-not-be-created.db",
        CLASSIFIRE_STORAGE_ROOT=str(workspace / "must-not-be-created-storage"),
        CLASSIFIRE_CLAMAV_HOST="127.0.0.1",
        CLASSIFIRE_CLAMAV_PORT=str(port),
    )
    try:
        result = subprocess.run(  # noqa: S603 - selected code, owned endpoint, synthetic metadata
            [sys.executable, "-m", "classifire.cli", "doctor", "--scanner-only"],
            cwd=workspace,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        thread.join(timeout=5)
        assert not thread.is_alive(), "The diagnostic left its synthetic peer waiting"
        assert failures == []
        assert commands == ([b"zPING\0"] if mode == "bad_ping" else [b"zPING\0", b"zVERSION\0"])
        assert result.returncode == (0 if mode == "current" else 1), result.stderr
        value = json.loads(result.stdout)
        assert value["file_scanned"] is False
        assert "127.0.0.1" not in result.stdout and "port" not in value
        if mode == "current":
            assert value["engine"] == "ClamAV 1.5.4"
            assert value["database_version"] == "28108"
            assert "not a malware-detection test" in value["limitation"]
        else:
            assert value["error"] == (
                "SCAN_DATABASE_STALE" if mode == "stale" else "SCAN_PING_INVALID"
            )
        assert list(workspace.iterdir()) == [], "Diagnostic created unexpected local state"
        (tmp_path / "diagnostic-output.json").write_text(
            json.dumps({"exit_code": result.returncode, "output": value}, indent=2),
            encoding="utf-8",
        )
    finally:
        listener.close()
        thread.join(timeout=6)
