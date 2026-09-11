"""Bounded DNS-pinned HTTPS retrieval for externally supplied evidence files."""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import math
import os
import re
import socket
import ssl

# Fixed isolated worker only; no shell or signed URL in arguments.
import subprocess  # nosec B404
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
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
    allowed_media_types: frozenset[str] = frozenset({"application/pdf", "application/octet-stream"})
    content_kind: str = "pdf"
    maximum_uri_characters: int = 4096
    maximum_redirects: int = 3
    chunk_size: int = 64 * 1024
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 20.0
    total_timeout_seconds: float = 45.0

    @property
    def content_magic(self) -> bytes:
        return b"%PDF-" if self.content_kind == "pdf" else b"PK\x03\x04"

    @property
    def content_media_type(self) -> str:
        return {
            "pdf": "application/pdf",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }[self.content_kind]

    def __post_init__(self) -> None:
        if (
            self.content_kind not in {"pdf", "xlsx", "docx"}
            or not self.allowed_hosts
            or len(self.allowed_hosts) > 64
            or type(self.maximum_bytes) is not int
            or not 1 <= self.maximum_bytes <= 100 * 1024 * 1024
            or not self.allowed_media_types
        ):
            raise RemoteFileRetrievalError("POLICY_INVALID")
        for limit in (
            self.connect_timeout_seconds,
            self.read_timeout_seconds,
            self.total_timeout_seconds,
        ):
            if type(limit) not in {int, float} or not math.isfinite(limit) or not 0 < limit <= 120:
                raise RemoteFileRetrievalError("POLICY_INVALID")
        if (
            type(self.chunk_size) is not int
            or not 1 <= self.chunk_size <= 1024 * 1024
            or type(self.maximum_redirects) is not int
            or not 0 <= self.maximum_redirects <= 10
            or type(self.maximum_uri_characters) is not int
            or not 1 <= self.maximum_uri_characters <= 4096
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
            declared = _declared_length(response.getheader("Content-Length"), policy.maximum_bytes)
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


def _retrieve_in_process(
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
            or not body.startswith(policy.content_magic)
            or not 1 <= len(body) <= policy.maximum_bytes
        ):
            raise RemoteFileRetrievalError(policy.content_kind.upper() + "_CONTENT_REJECTED")
        if response.declared_length is not None and response.declared_length != len(body):
            raise RemoteFileRetrievalError("CONTENT_LENGTH_MISMATCH")
        return RetrievedFile(
            content=body,
            sha256=hashlib.sha256(body).hexdigest(),
            size_bytes=len(body),
            media_type=policy.content_media_type,
            host=host,
            redirect_count=redirect_count,
            resolved_address_count=response.resolved_address_count,
            tls_version=response.tls_version,
        )


def retrieve_file(
    uri: str,
    policy: RemoteFilePolicy,
    *,
    resolver: Resolver | None = None,
    transport: Transport | None = None,
) -> RetrievedFile:
    """Production downloads run in a killable worker, including DNS and HTTP reads.

    Explicit injected resolver/transport ports are for deterministic local tests;
    the MCP caller cannot supply either port.
    """
    _validate_uri(uri, policy)
    if resolver is not None or transport is not None:
        return _retrieve_in_process(
            uri,
            policy,
            resolver=resolver or resolve_public_addresses,
            transport=transport or _pinned_https_get,
        )
    values = asdict(policy)
    values["allowed_hosts"] = sorted(policy.allowed_hosts)
    values["allowed_media_types"] = sorted(policy.allowed_media_types)
    request = json.dumps({"uri": uri, "policy": values}, allow_nan=False).encode("utf-8")
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW
    try:
        completed = subprocess.run(  # noqa: S603  # nosec B603
            [sys.executable, "-I", str(Path(__file__).resolve())],
            input=request,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=policy.total_timeout_seconds,
            check=False,
            env={key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR") if key in os.environ},
            creationflags=creationflags,
        )
    except subprocess.TimeoutExpired:
        # run() kills and waits for the process before raising; no abandoned fetch.
        raise RemoteFileRetrievalError("TOTAL_TIMEOUT") from None
    except OSError:
        raise RemoteFileRetrievalError("WORKER_FAILURE") from None
    if completed.returncode != 0 or len(completed.stdout) > policy.maximum_bytes + 4096:
        raise RemoteFileRetrievalError("WORKER_FAILURE")
    try:
        header, separator, content = completed.stdout.partition(b"\n")
        if not separator or len(header) > 4096:
            raise ValueError
        metadata = json.loads(header)
        if isinstance(metadata, dict) and set(metadata) == {"error"}:
            code = metadata["error"]
            if not content and isinstance(code, str) and re.fullmatch(r"[A-Z_]{1,64}", code):
                raise RemoteFileRetrievalError(code)
            raise ValueError
        result = RetrievedFile(content=content, **metadata)
        if (
            not content.startswith(policy.content_magic)
            or not 1 <= len(content) <= policy.maximum_bytes
            or result.size_bytes != len(content)
            or result.sha256 != hashlib.sha256(content).hexdigest()
            or result.media_type != policy.content_media_type
            or result.host not in policy.allowed_hosts
            or type(result.redirect_count) is not int
            or not 0 <= result.redirect_count <= policy.maximum_redirects
        ):
            raise ValueError
        return result
    except (ValueError, TypeError):
        raise RemoteFileRetrievalError("WORKER_FAILURE") from None


def _worker_main() -> None:
    """No application imports, database configuration, URL arguments or stderr output."""
    try:
        request = json.loads(sys.stdin.buffer.read(65537))
        values = request["policy"]
        values["allowed_hosts"] = frozenset(values["allowed_hosts"])
        values["allowed_media_types"] = frozenset(values["allowed_media_types"])
        result = _retrieve_in_process(request["uri"], RemoteFilePolicy(**values))
        metadata = asdict(result)
        del metadata["content"]
        header = json.dumps(metadata, allow_nan=False).encode("utf-8")
        if len(header) > 4096:
            raise RemoteFileRetrievalError("WORKER_FAILURE")
    except Exception as exc:
        code = exc.code if isinstance(exc, RemoteFileRetrievalError) else "WORKER_FAILURE"
        sys.stdout.buffer.write(json.dumps({"error": code}).encode("ascii") + b"\n")
        return
    sys.stdout.buffer.write(header + b"\n" + result.content)


if __name__ == "__main__":
    _worker_main()
