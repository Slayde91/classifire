from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from classifire.draft_client_evidence_tools import _remote_file_error
from classifire.services import remote_file_retrieval as retrieval

POLICY = retrieval.RemoteFilePolicy(
    allowed_hosts=frozenset({"allowed.example.test"}), maximum_bytes=1024
)


def test_unapproved_host_is_bounded_and_no_network_or_secret_is_exposed(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Rejected host must not reach a worker or network")

    monkeypatch.setattr(retrieval.subprocess, "run", forbidden)
    uri = "https://DELIVERY.example.test/private-path?sig=secret-query"
    with pytest.raises(retrieval.RemoteFileRetrievalError) as error:
        retrieval.retrieve_file(uri, POLICY)
    assert error.value.code == "UNAPPROVED_HOST"
    assert error.value.rejected_host == "delivery.example.test"
    message = _remote_file_error(error.value)
    assert json.loads(message)["rejected_host"] == "delivery.example.test"
    for secret in (uri, "private-path", "secret-query", "https://"):
        assert secret not in message + str(error.value) + repr(error.value)
    assert "delivery.example.test" not in str(error.value)


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "[::1]",
        "user:password@host.test",
        "host.test/path?secret=1",
        "host.test\\path",
        "host.test\nsecret",
        "UPPER.test",
        "a" * 254,
        "host_underscore.test",
    ],
)
def test_untrusted_diagnostic_values_remain_redacted(host):
    error = retrieval.RemoteFileRetrievalError("UNAPPROVED_HOST", rejected_host=host)
    assert error.rejected_host is None
    assert _remote_file_error(error) == "CLIENT_FILE_UNAPPROVED_HOST"


def test_other_failures_do_not_gain_host_diagnostics():
    error = retrieval.RemoteFileRetrievalError(
        "NETWORK_FAILURE", rejected_host="delivery.example.test"
    )
    assert error.rejected_host is None
    assert _remote_file_error(error) == "CLIENT_FILE_NETWORK_FAILURE"
    with pytest.raises(retrieval.RemoteFileRetrievalError) as unsafe:
        retrieval.retrieve_file("https://user:password@delivery.example.test/file", POLICY)
    assert unsafe.value.code == "UNSAFE_USERINFO" and unsafe.value.rejected_host is None


def test_redirect_reports_rejected_destination_without_connecting_to_it():
    seen = []

    def transport(uri, policy, resolver):
        seen.append(uri)
        return retrieval.FetchResponse(
            status=302, redirect_location="https://new.example.test/private?sig=secret"
        )

    with pytest.raises(retrieval.RemoteFileRetrievalError) as error:
        retrieval.retrieve_file("https://allowed.example.test/start", POLICY, transport=transport)
    assert seen == ["https://allowed.example.test/start"]
    assert error.value.rejected_host == "new.example.test"
    assert "secret" not in _remote_file_error(error.value)


def test_real_isolated_worker_emits_only_error_and_hostname():
    policy = asdict(POLICY)
    policy["allowed_hosts"] = sorted(policy["allowed_hosts"])
    policy["allowed_media_types"] = sorted(policy["allowed_media_types"])
    request = {"uri": "https://worker.example.test/private?sig=secret", "policy": policy}
    result = subprocess.run(  # noqa: S603 - fixed interpreter and isolated checked-in worker
        [sys.executable, "-I", retrieval.__file__],
        input=json.dumps(request).encode(),
        capture_output=True,
        check=True,
        timeout=10,
    )
    assert result.stderr == b""
    assert json.loads(result.stdout) == {
        "error": "UNAPPROVED_HOST",
        "rejected_host": "worker.example.test",
    }
    assert b"private" not in result.stdout and b"secret" not in result.stdout


@pytest.mark.parametrize(
    "metadata,expected",
    [
        ({"error": "UNAPPROVED_HOST", "rejected_host": "redirect.example.test"}, "UNAPPROVED_HOST"),
        ({"error": "UNAPPROVED_HOST"}, "UNAPPROVED_HOST"),
        (
            {"error": "UNAPPROVED_HOST", "rejected_host": "https://host.test/private?secret"},
            "WORKER_FAILURE",
        ),
        ({"error": "NETWORK_FAILURE", "rejected_host": "host.test"}, "WORKER_FAILURE"),
        ({"error": "UNAPPROVED_HOST", "rejected_host": None}, "WORKER_FAILURE"),
        ({"error": "UNAPPROVED_HOST", "rejected_host": 42}, "WORKER_FAILURE"),
        (
            {"error": "UNAPPROVED_HOST", "rejected_host": "host.test", "uri": "secret"},
            "WORKER_FAILURE",
        ),
    ],
)
def test_parent_revalidates_worker_error_protocol(monkeypatch, metadata, expected):
    monkeypatch.setattr(
        retrieval.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(metadata).encode() + b"\n"),
    )
    with pytest.raises(retrieval.RemoteFileRetrievalError) as error:
        retrieval.retrieve_file("https://allowed.example.test/file", POLICY)
    assert error.value.code == expected
    if expected == "WORKER_FAILURE":
        assert error.value.rejected_host is None
    else:
        assert error.value.rejected_host == metadata.get("rejected_host")
