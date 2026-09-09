"""Bounded DNS-pinned HTTPS retrieval for externally supplied evidence files."""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import re
import socket
import ssl
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from urllib.parse import unquote, urljoin, urlsplit

REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
TRANSIENT_STATUSES = frozenset({408, 429, 502, 503, 504})
_BAD_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_DNS_HOST = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z"
)


class RemoteFileRetrievalError(RuntimeError):
    """A deliberately redacted remote-file failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Remote file retrieval failed: {code}")


@dataclass(frozen=True)
class RemoteFilePolicy:
    allowed_hosts: frozenset[str]
    maximum_bytes: int
    allowed_media_types: frozenset[str] = frozenset(
        {"application/pdf", "application/octet-stream"}
    )
    maximum_uri_characters: int = 4096
    maximum_redirects: int = 3
    chunk_size: int = 64 * 1024
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 20.0
    total_timeout_seconds: float = 45.0

    def __post_init__(self) -> None:
        if (
            not self.allowed_hosts
            or type(self.maximum_bytes) is not int
            or not 1 <= self.maximum_bytes <= 100 * 1024 * 1024
            or not self.allowed_media_types
        ):
            raise RemoteFileRetrievalError("POLICY_INVALID")
        for host in self.allowed_hosts:
            if (
                not isinstance(host, str)
                or host != host.strip().lower()
                or not host.isascii()
                or _DNS_HOST.fullmatch(host) is None
            ):
                raise RemoteFileRetrievalError("POLICY_INVALID")
            try:
                ipaddress.ip_address(host)
            except ValueError:
                pass
            else:
                raise RemoteFileRetrievalError("POLICY_INVALID")


@dataclass(frozen=True)
class FetchResponse:
    status: int
    content_type: str | None = None
    content_encoding: str | None = None
    declared_length: int | None = None
    body: bytes = field(default=b"", repr=False)
    redirect_location: str | None = field(default=None, repr=False)
    resolved_address_count: int = 0
    tls_version: str | None = None


@dataclass(frozen=True)
class RetrievedFile:
    content: bytes = field(repr=False)
    sha256: str = ""
    size_bytes: int = 0
    media_type: str = ""
    host: str = ""
    redirect_count: int = 0
    resolved_address_count: int = 0
    tls_version: str | None = None


Resolver = Callable[[str, int], Sequence[tuple[int, str]]]
Transport = Callable[[str, RemoteFilePolicy, Resolver], FetchResponse]


def _contains_controls(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _validate_uri(uri: str, policy: RemoteFilePolicy) -> str:
    if (
        not isinstance(uri, str)
        or not uri
        or len(uri) > policy.maximum_uri_characters
        or not uri.isascii()
        or _contains_controls(uri)
        or any(character.isspace() for character in uri)
        or "\\" in uri
        or _BAD_PERCENT_ESCAPE.search(uri)
    ):
        raise RemoteFileRetrievalError("UNSAFE_URI")
    try:
        parsed = urlsplit(uri)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        raise RemoteFileRetrievalError("UNSAFE_URI") from None
    if parsed.scheme.lower() != "https":
        raise RemoteFileRetrievalError("UNSAFE_SCHEME")
    if parsed.username is not None or parsed.password is not None:
        raise RemoteFileRetrievalError("UNSAFE_USERINFO")
    if host not in policy.allowed_hosts:
        raise RemoteFileRetrievalError("UNAPPROVED_HOST")
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        pass
    else:
        raise RemoteFileRetrievalError("IP_LITERAL_HOST")
    if port not in {None, 443}:
        raise RemoteFileRetrievalError("UNSAFE_PORT")
    if parsed.fragment:
        raise RemoteFileRetrievalError("UNSAFE_FRAGMENT")
    if not parsed.path.startswith("/") or _contains_controls(parsed.path):
        raise RemoteFileRetrievalError("UNSAFE_PATH")
    try:
        decoded_path = unquote(parsed.path, errors="strict")
    except (UnicodeDecodeError, ValueError):
        raise RemoteFileRetrievalError("UNSAFE_PATH") from None
    if "\\" in decoded_path or _contains_controls(decoded_path):
        raise RemoteFileRetrievalError("UNSAFE_PATH")
    if re.search(r"%(?:2f|5c)", parsed.path, flags=re.IGNORECASE):
        raise RemoteFileRetrievalError("UNSAFE_PATH")
    if any(segment in {".", ".."} for segment in decoded_path.split("/")):
        raise RemoteFileRetrievalError("UNSAFE_PATH")
    if _contains_controls(parsed.query) or "\\" in parsed.query:
        raise RemoteFileRetrievalError("UNSAFE_QUERY")
    return host


def _public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return bool(
        address.is_global
        and not address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_multicast
        and not address.is_reserved
        and not address.is_unspecified
    )


def resolve_public_addresses(host: str, port: int = 443) -> tuple[tuple[int, str], ...]:
    try:
        resolved = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        raise RemoteFileRetrievalError("DNS_FAILURE") from None
    addresses: list[tuple[int, str]] = []
    for family, _type, _proto, _canonname, sockaddr in resolved:
        value = str(sockaddr[0])
        if not _public_ip(value):
            raise RemoteFileRetrievalError("NON_PUBLIC_DNS_ADDRESS")
        item = (int(family), value)
        if item not in addresses:
            addresses.append(item)
    if not addresses:
        raise RemoteFileRetrievalError("DNS_FAILURE")
    return tuple(addresses)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        host: str,
        pinned_address: str,
        *,
        timeout: float,
        context: ssl.SSLContext,
    ) -> None:
        super().__init__(host=host, port=443, timeout=timeout, context=context)
        self._pinned_address = pinned_address
        self._ssl_context = context

    def connect(self) -> None:
        raw_socket = socket.create_connection(
            (self._pinned_address, self.port), timeout=self.timeout
        )
        try:
            self.sock = self._ssl_context.wrap_socket(raw_socket, server_hostname=self.host)
        except BaseException:
            raw_socket.close()
            raise


def _declared_length(value: str | None, maximum: int) -> int | None:
    if value is None:
        return None
    if re.fullmatch(r"[0-9]+", value.strip()) is None:
        raise RemoteFileRetrievalError("INVALID_CONTENT_LENGTH")
    length = int(value)
    if length > maximum:
        raise RemoteFileRetrievalError("FILE_TOO_LARGE")
    return length


def _pinned_https_get(
    uri: str,
    policy: RemoteFilePolicy,
    resolver: Resolver,
) -> FetchResponse:
    host = _validate_uri(uri, policy)
    parsed = urlsplit(uri)
    addresses = tuple(resolver(host, 443))
    if not addresses or any(not _public_ip(address) for _family, address in addresses):
        raise RemoteFileRetrievalError("NON_PUBLIC_DNS_ADDRESS")
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    for _family, address in addresses:
        connection = _PinnedHTTPSConnection(
            host,
            address,
            timeout=policy.connect_timeout_seconds,
            context=context,
        )
        try:
            target = parsed.path + (f"?{parsed.query}" if parsed.query else "")
            connection.request(
                "GET",
                target,
                headers={
                    "Accept": ", ".join(sorted(policy.allowed_media_types)),
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                    "Host": host,
                    "User-Agent": "CLASSIFIRE-remote-file-retrieval/1",
                },
            )
            response = connection.getresponse()
            if connection.sock is not None:
                connection.sock.settimeout(policy.read_timeout_seconds)
            status = int(response.status)
            tls_version = connection.sock.version() if connection.sock is not None else None
            if status in REDIRECT_STATUSES:
                return FetchResponse(
                    status=status,
                    redirect_location=response.getheader("Location"),
                    resolved_address_count=len(addresses),
                    tls_version=tls_version,
                )
            declared = _declared_length(
                response.getheader("Content-Length"), policy.maximum_bytes
            )
            chunks: list[bytes] = []
            received = 0
            while True:
                chunk = response.read(policy.chunk_size)
                if not chunk:
                    break
                received += len(chunk)
                if received > policy.maximum_bytes:
                    raise RemoteFileRetrievalError("FILE_TOO_LARGE")
                chunks.append(chunk)
            return FetchResponse(
                status=status,
                content_type=response.getheader("Content-Type"),
                content_encoding=response.getheader("Content-Encoding"),
                declared_length=declared,
                body=b"".join(chunks),
                resolved_address_count=len(addresses),
                tls_version=tls_version,
            )
        except RemoteFileRetrievalError:
            raise
        except (OSError, ssl.SSLError, http.client.HTTPException):
            pass
        finally:
            connection.close()
    raise RemoteFileRetrievalError("NETWORK_FAILURE") from None


def retrieve_file(
    uri: str,
    policy: RemoteFilePolicy,
    *,
    resolver: Resolver = resolve_public_addresses,
    transport: Transport = _pinned_https_get,
) -> RetrievedFile:
    current = uri
    started = time.monotonic()
    redirect_count = 0
    while True:
        if time.monotonic() - started > policy.total_timeout_seconds:
            raise RemoteFileRetrievalError("TOTAL_TIMEOUT")
        host = _validate_uri(current, policy)
        try:
            response = transport(current, policy, resolver)
        except RemoteFileRetrievalError:
            raise
        except Exception:
            raise RemoteFileRetrievalError("NETWORK_FAILURE") from None
        if time.monotonic() - started > policy.total_timeout_seconds:
            raise RemoteFileRetrievalError("TOTAL_TIMEOUT")
        if response.status in REDIRECT_STATUSES:
            if redirect_count >= policy.maximum_redirects or not response.redirect_location:
                raise RemoteFileRetrievalError("REDIRECT_REJECTED")
            current = urljoin(current, response.redirect_location)
            _validate_uri(current, policy)
            redirect_count += 1
            continue
        if response.status in TRANSIENT_STATUSES:
            raise RemoteFileRetrievalError("TRANSIENT_HTTP_STATUS")
        if response.status != 200:
            raise RemoteFileRetrievalError("HTTP_STATUS_REJECTED")
        encoding = str(response.content_encoding or "identity").strip().lower()
        if encoding not in {"", "identity"}:
            raise RemoteFileRetrievalError("CONTENT_ENCODING_REJECTED")
        media_type = str(response.content_type or "").split(";", 1)[0].strip().lower()
        if media_type not in policy.allowed_media_types:
            raise RemoteFileRetrievalError("CONTENT_TYPE_REJECTED")
        body = response.body
        if (
            not isinstance(body, bytes)
            or not body.startswith(b"%PDF-")
            or not 1 <= len(body) <= policy.maximum_bytes
        ):
            raise RemoteFileRetrievalError("PDF_CONTENT_REJECTED")
        if response.declared_length is not None and response.declared_length != len(body):
            raise RemoteFileRetrievalError("CONTENT_LENGTH_MISMATCH")
        return RetrievedFile(
            content=body,
            sha256=hashlib.sha256(body).hexdigest(),
            size_bytes=len(body),
            media_type="application/pdf",
            host=host,
            redirect_count=redirect_count,
            resolved_address_count=response.resolved_address_count,
            tls_version=response.tls_version,
        )
