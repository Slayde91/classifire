from __future__ import annotations

import hashlib
import subprocess
import time
from dataclasses import replace

import pytest

from classifire.services import remote_file_retrieval as retrieval


def test_production_download_has_parent_enforced_timeout(monkeypatch):
    calls = []

    def stalled_worker(command, **kwargs):
        calls.append((command, kwargs))
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", stalled_worker)
    # The pre-fix in-process path must not contact even synthetic DNS.
    monkeypatch.setattr(retrieval.socket, "getaddrinfo", lambda *a, **k: [])
    policy = replace(
        retrieval.RemoteFilePolicy(frozenset({"files.example.test"}), 1024),
        total_timeout_seconds=1.0,
    )
    with pytest.raises(retrieval.RemoteFileRetrievalError) as error:
        retrieval.retrieve_file("https://files.example.test/file?token=secret", policy)
    assert error.value.code == "TOTAL_TIMEOUT"
    assert len(calls) == 1
    command, options = calls[0]
    assert options["timeout"] == 1.0
    assert "secret" not in repr(command)
    assert options["stderr"] == subprocess.DEVNULL


@pytest.mark.parametrize("stage", ["dns", "headers", "body", "success"])
def test_real_worker_is_reaped_and_valid_bytes_survive(monkeypatch, tmp_path, stage):
    marker = tmp_path / "entered-stage"
    shim = tmp_path / "synthetic-worker.py"
    shim.write_text(
        """
import importlib.util
import socket
import sys
import time
from pathlib import Path

module_path, stage, marker = sys.argv[1:]
spec = importlib.util.spec_from_file_location("isolated_retrieval", module_path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def stall(point):
    if stage == point:
        Path(marker).write_text(point)
        time.sleep(30)
        Path(marker).write_text("escaped deadline")


def resolve(*args, **kwargs):
    stall("dns")
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]


class Response:
    status = 200
    sent = False

    def getheader(self, key):
        return "application/pdf" if key == "Content-Type" else None

    def read(self, amount):
        stall("body")
        if self.sent:
            return b""
        self.sent = True
        return b"%PDF-1.4 synthetic exact bytes"


class Connection:
    sock = None

    def __init__(self, *args, **kwargs):
        pass

    def request(self, *args, **kwargs):
        pass

    def getresponse(self):
        stall("headers")
        return Response()

    def close(self):
        pass


socket.getaddrinfo = resolve
module._PinnedHTTPSConnection = Connection
module._worker_main()
""",
        encoding="utf-8",
    )
    real_popen = subprocess.Popen
    processes = []

    def launch(command, **kwargs):
        assert command[1] == "-I"
        assert "secret" not in repr(command)
        assert "CLASSIFIRE_TEST_SECRET" not in kwargs["env"]
        # Only the test redirects the fixed production worker to a synthetic transport.
        process = real_popen(
            [command[0], "-I", str(shim), command[2], stage, str(marker)], **kwargs
        )
        processes.append(process)
        return process

    monkeypatch.setenv("CLASSIFIRE_TEST_SECRET", "must-not-reach-worker")
    monkeypatch.setattr(subprocess, "Popen", launch)
    policy = retrieval.RemoteFilePolicy(
        frozenset({"files.example.test"}), 1024, total_timeout_seconds=2.0
    )
    started = time.monotonic()
    if stage == "success":
        result = retrieval.retrieve_file("https://files.example.test/file?token=secret", policy)
        assert result.content == b"%PDF-1.4 synthetic exact bytes"
        assert result.sha256 == hashlib.sha256(result.content).hexdigest()
        assert "secret" not in repr(result)
    else:
        with pytest.raises(retrieval.RemoteFileRetrievalError) as error:
            retrieval.retrieve_file("https://files.example.test/file?token=secret", policy)
        assert error.value.code == "TOTAL_TIMEOUT"
        assert marker.read_text() == stage
        assert processes[0].returncode != 0
    assert time.monotonic() - started < 8
    assert len(processes) == 1
    assert processes[0].poll() is not None


@pytest.mark.parametrize("limit", [0, -1, float("nan"), float("inf"), True, 121])
def test_invalid_deadline_is_refused(limit):
    with pytest.raises(retrieval.RemoteFileRetrievalError, match="POLICY_INVALID"):
        retrieval.RemoteFilePolicy(
            frozenset({"files.example.test"}), 1024, total_timeout_seconds=limit
        )


@pytest.mark.parametrize("output", [b"secret exception", b"{}\nnot-pdf", b"x" * 5121])
def test_malformed_worker_output_is_redacted(monkeypatch, output):
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 0, output)
    )
    with pytest.raises(retrieval.RemoteFileRetrievalError) as error:
        retrieval.retrieve_file(
            "https://files.example.test/file?token=secret",
            retrieval.RemoteFilePolicy(frozenset({"files.example.test"}), 1024),
        )
    assert error.value.code == "WORKER_FAILURE"
    assert "secret" not in str(error.value)
