from __future__ import annotations

import hashlib
import socket

import pytest

from classifire.config import Settings
from classifire.services import remote_file_retrieval as retrieval

PDF = b"%PDF-1.4\nsynthetic external evidence\n"
POLICY = retrieval.RemoteFilePolicy(
    allowed_hosts=frozenset({"files.example.test"}),
    maximum_bytes=1024,
)


def response(**overrides):
    values = {
        "status": 200,
        "content_type": "application/pdf",
        "content_encoding": "identity",
        "declared_length": len(PDF),
        "body": PDF,
        "resolved_address_count": 1,
        "tls_version": "TLSv1.3",
    }
    values.update(overrides)
    return retrieval.FetchResponse(**values)


def test_settings_parse_exact_file_host_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "CLASSIFIRE_DRAFT_CLIENT_FILE_DOWNLOAD_HOSTS",
        "files.example.test,cdn.example.test",
    )

    settings = Settings(_env_file=None)

    assert settings.draft_client_file_download_hosts == [
        "files.example.test",
        "cdn.example.test",
    ]

def test_retrieval_returns_exact_bytes_and_redacted_receipt() -> None:
    marker = "secret-download-token"
    seen: list[str] = []

    def transport(uri, policy, resolver):
        del policy, resolver
        seen.append(uri)
        return response()

    result = retrieval.retrieve_file(
        f"https://files.example.test/download.pdf?token={marker}",
        POLICY,
        transport=transport,
    )

    assert seen == [f"https://files.example.test/download.pdf?token={marker}"]
    assert result.content == PDF
    assert result.sha256 == hashlib.sha256(PDF).hexdigest()
    assert result.size_bytes == len(PDF)
    assert result.media_type == "application/pdf"
    assert result.host == "files.example.test"
    assert result.redirect_count == 0
    assert marker not in repr(result)


@pytest.mark.parametrize(
    ("uri", "code"),
    [
        ("http://files.example.test/report.pdf", "UNSAFE_SCHEME"),
        ("https://user:pass@files.example.test/report.pdf", "UNSAFE_USERINFO"),
        ("https://127.0.0.1/report.pdf", "UNAPPROVED_HOST"),
        ("https://other.example.test/report.pdf", "UNAPPROVED_HOST"),
        ("https://files.example.test:444/report.pdf", "UNSAFE_PORT"),
        ("https://files.example.test/a/../report.pdf", "UNSAFE_PATH"),
        ("https://files.example.test/report.pdf#fragment", "UNSAFE_FRAGMENT"),
        ("https://files.example.test/report.pdf?x=%ZZ", "UNSAFE_URI"),
    ],
)
def test_retrieval_rejects_unsafe_urls_before_transport(uri: str, code: str) -> None:
    called = False

    def transport(uri, policy, resolver):
        del uri, policy, resolver
        nonlocal called
        called = True
        return response()

    with pytest.raises(retrieval.RemoteFileRetrievalError) as raised:
        retrieval.retrieve_file(uri, POLICY, transport=transport)

    assert raised.value.code == code
    assert called is False
    assert uri not in str(raised.value)


def test_redirects_are_revalidated_without_leaking_signed_url() -> None:
    marker = "redirect-secret"

    def transport(uri, policy, resolver):
        del policy, resolver
        if marker in uri:
            return response(
                status=302,
                content_type=None,
                content_encoding=None,
                declared_length=None,
                body=b"",
                redirect_location="https://unapproved.example.test/report.pdf",
            )
        raise AssertionError("unexpected URI")

    uri = f"https://files.example.test/start?token={marker}"
    with pytest.raises(retrieval.RemoteFileRetrievalError) as raised:
        retrieval.retrieve_file(uri, POLICY, transport=transport)

    assert raised.value.code == "UNAPPROVED_HOST"
    assert marker not in str(raised.value)


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"status": 403}, "HTTP_STATUS_REJECTED"),
        ({"status": 503}, "TRANSIENT_HTTP_STATUS"),
        ({"content_type": "text/html"}, "CONTENT_TYPE_REJECTED"),
        ({"content_encoding": "gzip"}, "CONTENT_ENCODING_REJECTED"),
        ({"body": b"not-pdf", "declared_length": 7}, "PDF_CONTENT_REJECTED"),
        ({"declared_length": len(PDF) + 1}, "CONTENT_LENGTH_MISMATCH"),
    ],
)
def test_retrieval_refuses_invalid_responses(overrides: dict[str, object], code: str) -> None:
    def transport(uri, policy, resolver):
        del uri, policy, resolver
        return response(**overrides)

    with pytest.raises(retrieval.RemoteFileRetrievalError) as raised:
        retrieval.retrieve_file(
            "https://files.example.test/report.pdf",
            POLICY,
            transport=transport,
        )

    assert raised.value.code == code


def test_policy_and_dns_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(retrieval.RemoteFileRetrievalError, match="POLICY_INVALID"):
        retrieval.RemoteFilePolicy(allowed_hosts=frozenset(), maximum_bytes=1024)
    with pytest.raises(retrieval.RemoteFileRetrievalError, match="POLICY_INVALID"):
        retrieval.RemoteFilePolicy(
            allowed_hosts=frozenset({"*.example.test"}), maximum_bytes=1024
        )

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))
        ],
    )
    with pytest.raises(retrieval.RemoteFileRetrievalError) as raised:
        retrieval.resolve_public_addresses("files.example.test")
    assert raised.value.code == "NON_PUBLIC_DNS_ADDRESS"


def test_transport_exception_is_redacted() -> None:
    marker = "never-return-this-secret"

    def transport(uri, policy, resolver):
        del uri, policy, resolver
        raise RuntimeError(marker)

    with pytest.raises(retrieval.RemoteFileRetrievalError) as raised:
        retrieval.retrieve_file(
            f"https://files.example.test/report.pdf?token={marker}",
            POLICY,
            transport=transport,
        )

    assert raised.value.code == "NETWORK_FAILURE"
    assert marker not in str(raised.value)
