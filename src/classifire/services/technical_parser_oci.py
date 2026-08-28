"""Bounded, digest-pinned OCI transport for untrusted technical parsers.

This module is a host controller, not a parser and not a production-enablement
switch. It never receives a storage path, database handle, application secret,
or mutable image tag. The selected image must implement the existing parser
protocol over one exact stdin frame:

    u32 big-endian request length | canonical request | exact source bytes | EOF

Production remains blocked until an approved worker image, signed supply-chain
evidence, runtime-specific isolation UAT, and the other roadmap gates exist.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import os
import re
import signal
import stat
import subprocess  # nosec B404
import tempfile
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Literal, Never, Protocol, cast
from uuid import UUID

from .technical_parser_execution import (
    TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2,
    TechnicalParserExecutionError,
    TechnicalParserExecutionReceipt,
    TechnicalParserExecutionSuccess,
    TechnicalParserRuntimeAttestation,
    create_technical_parser_execution_receipt,
    create_technical_parser_runtime_attestation,
)
from .technical_parser_protocol import (
    TECHNICAL_PARSER_EVIDENCE_MAX_BYTES,
    TECHNICAL_PARSER_HEADER_MAX_BYTES,
    TECHNICAL_PARSER_LAYOUT_MAX_BYTES,
    TECHNICAL_PARSER_PNG_MAX_BYTES,
    TechnicalParserLayoutRequest,
    TechnicalParserProtocolError,
    TechnicalParserRequest,
    parse_technical_parser_layout_request,
    parse_technical_parser_request,
)

TECHNICAL_PARSER_OCI_PROFILE_SCHEMA = "technical-parser-oci-profile-v1"
TECHNICAL_PARSER_OCI_TRANSPORT_SCHEMA = "technical-parser-stdin-frame-v1"
TECHNICAL_PARSER_OCI_ENTRYPOINT = "/opt/classifire-parser/entrypoint"
TECHNICAL_PARSER_OCI_CONTRACT_LABEL = "com.ceasefire.classifire.technical-parser-contract"
TECHNICAL_PARSER_OCI_POLICY_LABEL = "com.ceasefire.classifire.technical-parser-policy"
TECHNICAL_PARSER_OCI_POLICY_SHA256_LABEL = "com.ceasefire.classifire.technical-parser-policy-sha256"
TECHNICAL_PARSER_OCI_INVOCATION_LABEL = "com.ceasefire.classifire.technical-parser-invocation"
TECHNICAL_PARSER_OCI_OWNER_LABEL = "com.ceasefire.classifire.technical-parser-owner"
TECHNICAL_PARSER_OCI_ENGINE = "oci"
TECHNICAL_PARSER_OCI_CLEANUP_PROOF_SCHEMA = "technical-parser-oci-cleanup-proof-v1"

_LAYOUT_OUTPUT_LIMIT = TECHNICAL_PARSER_LAYOUT_MAX_BYTES
_PAGE_OUTPUT_LIMIT = (
    4
    + TECHNICAL_PARSER_HEADER_MAX_BYTES
    + TECHNICAL_PARSER_EVIDENCE_MAX_BYTES
    + TECHNICAL_PARSER_PNG_MAX_BYTES
)
_CONTROL_OUTPUT_LIMIT = 64 * 1024
_RUNTIME_FILE_MAX_BYTES = 512 * 1024 * 1024
_SECCOMP_FILE_MAX_BYTES = 1024 * 1024
_STREAM_CHUNK_BYTES = 64 * 1024
_CONTAINER_ID = re.compile(rb"^[0-9a-f]{64}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_POLICY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+/-]{0,99}$")
_IMAGE_REFERENCE = re.compile(
    r"^(?:[a-z0-9]+(?:[.-][a-z0-9]+)*(?::[1-9][0-9]{0,4})?/)?"
    r"(?:[a-z0-9]+(?:[._-][a-z0-9]+)*/)*"
    r"[a-z0-9]+(?:[._-][a-z0-9]+)*@sha256:[0-9a-f]{64}$"
)
_PLATFORMS = frozenset({"linux/amd64", "linux/arm64"})
_CONTAINER_STATES = frozenset(
    {"created", "dead", "exited", "paused", "removing", "restarting", "running"}
)
_ROOTLESS_RUNTIME_HOST = re.compile(r"^unix:///run/user/[1-9][0-9]{0,9}/docker\.sock$")
_ARCHITECTURE_ALIASES = {
    "aarch64": "arm64",
    "arm64": "arm64",
    "amd64": "amd64",
    "x86_64": "amd64",
}
_DENIED_SECCOMP_SYSCALLS = frozenset(
    {
        "accept",
        "accept4",
        "bind",
        "connect",
        "getpeername",
        "getsockname",
        "getsockopt",
        "listen",
        "recvfrom",
        "recvmmsg",
        "recvmsg",
        "sendmmsg",
        "sendmsg",
        "sendto",
        "setsockopt",
        "shutdown",
        "socket",
        "socketcall",
        "socketpair",
    }
)
_CONFIGURATION_CODES = frozenset(
    {
        "PARSER_OCI_IMAGE_REFERENCE_INVALID",
        "PARSER_OCI_CONTROLLER_OWNER_INVALID",
        "PARSER_OCI_EXECUTION_FENCE_INVALID",
        "PARSER_OCI_PLATFORM_INVALID",
        "PARSER_OCI_RUNTIME_PATH_INVALID",
        "PARSER_OCI_RUNTIME_HOST_INVALID",
        "PARSER_OCI_RUNTIME_SHA256_INVALID",
        "PARSER_OCI_SECCOMP_PROFILE_INVALID",
        "PARSER_OCI_SECCOMP_SHA256_INVALID",
    }
)


class TechnicalParserOciConfigurationError(ValueError):
    """Stable rejection of unsafe controller configuration."""

    def __init__(self, code: str) -> None:
        if code not in _CONFIGURATION_CODES:
            raise ValueError("Unknown OCI parser configuration error code")
        self.code = code
        super().__init__(code)


class TechnicalParserExecutionFence(Protocol):
    """Host-wide exclusion shared by execution and orphan cleanup."""

    @property
    def identity_sha256(self) -> str: ...

    def hold(self, *, wait: bool) -> AbstractContextManager[None]: ...


@dataclass(frozen=True, slots=True)
class TechnicalParserOciRuntimeProfile:
    """Finite controller and container limits included in one profile digest."""

    platform: str
    layout_timeout_seconds: float = 30.0
    page_timeout_seconds: float = 90.0
    control_timeout_seconds: float = 10.0
    cleanup_timeout_seconds: float = 10.0
    memory_bytes: int = 1024 * 1024 * 1024
    memory_swap_bytes: int = 1024 * 1024 * 1024
    nano_cpus: int = 1_000_000_000
    pids_limit: int = 64
    nofile_limit: int = 64
    tmpfs_bytes: int = 192 * 1024 * 1024
    concurrency: int = 1

    def __post_init__(self) -> None:
        valid = (
            self.platform in _PLATFORMS
            and _finite_between(self.layout_timeout_seconds, 1.0, 120.0)
            and _finite_between(self.page_timeout_seconds, 1.0, 300.0)
            and _finite_between(self.control_timeout_seconds, 1.0, 30.0)
            and _finite_between(self.cleanup_timeout_seconds, 1.0, 30.0)
            and self.memory_bytes == 1024 * 1024 * 1024
            and self.memory_swap_bytes == self.memory_bytes
            and self.nano_cpus == 1_000_000_000
            and self.pids_limit == 64
            and self.nofile_limit == 64
            and self.tmpfs_bytes == 192 * 1024 * 1024
            and self.concurrency == 1
        )
        if not valid:
            raise TechnicalParserOciConfigurationError("PARSER_OCI_PLATFORM_INVALID")


@dataclass(frozen=True, slots=True)
class _BoundedCommandResult:
    returncode: int
    stdout: bytes
    stderr: bytes


class _CommandInputWriter(Protocol):
    def __call__(self, stream: BinaryIO) -> None: ...


class _OciRuntimeAdapter(Protocol):
    def run(
        self,
        args: Sequence[str],
        *,
        stdin_writer: _CommandInputWriter | None,
        timeout_seconds: float,
        stdout_limit: int,
        stderr_limit: int,
        environment: Mapping[str, str],
        on_terminate: Callable[[], None] | None = None,
    ) -> _BoundedCommandResult: ...


class _BoundedCommandError(RuntimeError):
    def __init__(
        self,
        kind: Literal[
            "input_failed",
            "stderr_output",
            "stdout_overflow",
            "termination_failed",
            "timeout",
            "unavailable",
        ],
    ) -> None:
        self.kind = kind
        super().__init__(kind)


class _OciContainmentLost(TechnicalParserExecutionError):
    def __init__(self, container_id: str | None = None) -> None:
        self.container_id = container_id
        super().__init__("PARSER_EXECUTION_CONTAINMENT_LOST")


class _HostCallbackFailure(Exception):
    """Carry an ordinary host callback failure through OCI error normalization."""

    def __init__(self, cause: Exception) -> None:
        self.cause = cause
        super().__init__(str(cause))


@dataclass(slots=True)
class _ExecutionCallbacks:
    prepare: Callable[[], None] | None
    authorize: Callable[[], None] | None
    finalize: Callable[[TechnicalParserExecutionReceipt], None] | None
    prepared: bool = False


def _finite_between(value: object, minimum: float, maximum: float) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and minimum <= float(value) <= maximum
    )


def _posix_effective_user_id() -> int:
    getter = getattr(os, "geteuid", None)
    if not callable(getter):
        raise OSError
    value = getter()
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise OSError
    return value


def _posix_flock_contract() -> tuple[
    Callable[[int, int], None],
    int,
    int,
    int,
]:
    try:
        module = importlib.import_module("fcntl")
    except ImportError:
        raise OSError from None
    flock = getattr(module, "flock", None)
    lock_ex = getattr(module, "LOCK_EX", None)
    lock_nb = getattr(module, "LOCK_NB", None)
    lock_un = getattr(module, "LOCK_UN", None)
    if (
        not callable(flock)
        or not isinstance(lock_ex, int)
        or isinstance(lock_ex, bool)
        or not isinstance(lock_nb, int)
        or isinstance(lock_nb, bool)
        or not isinstance(lock_un, int)
        or isinstance(lock_un, bool)
    ):
        raise OSError
    return cast(Callable[[int, int], None], flock), lock_ex, lock_nb, lock_un


def _sha256(value: object, *, code: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise TechnicalParserOciConfigurationError(code)
    return value


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _utc_text(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("UTC datetime required")
    safe = value.astimezone(UTC)
    return safe.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _uuid4_text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("canonical UUID4 required")
    try:
        parsed = UUID(value)
    except (AttributeError, TypeError, ValueError):
        raise ValueError("canonical UUID4 required") from None
    if parsed.version != 4 or str(parsed) != value:
        raise ValueError("canonical UUID4 required")
    return value


@dataclass(frozen=True, slots=True)
class TechnicalParserOciCleanupProof:
    """Canonical proof that orphan cleanup stayed inside one invocation."""

    schema: str
    invocation_id: str
    runtime_attestation_sha256: str
    controller_owner_id: str
    runtime_profile_sha256: str
    oci_daemon_identity_sha256: str
    execution_fence_sha256: str
    observed_container_id: str | None
    observed_container_state: str | None
    cleanup_confirmed: bool
    completed_at: datetime
    canonical_json: bytes
    sha256: str

    def __post_init__(self) -> None:
        value = _strict_json(self.canonical_json)
        expected = {
            "cleanup_confirmed": self.cleanup_confirmed,
            "completed_at": _utc_text(self.completed_at),
            "controller_owner_id": self.controller_owner_id,
            "execution_fence_sha256": self.execution_fence_sha256,
            "invocation_id": self.invocation_id,
            "observed_container_id": self.observed_container_id,
            "observed_container_state": self.observed_container_state,
            "oci_daemon_identity_sha256": self.oci_daemon_identity_sha256,
            "runtime_attestation_sha256": self.runtime_attestation_sha256,
            "runtime_profile_sha256": self.runtime_profile_sha256,
            "schema": self.schema,
        }
        try:
            owner = _uuid4_text(self.controller_owner_id)
            invocation = _uuid4_text(self.invocation_id)
        except ValueError:
            raise ValueError("Invalid OCI cleanup proof") from None
        if (
            self.schema != TECHNICAL_PARSER_OCI_CLEANUP_PROOF_SCHEMA
            or owner != self.controller_owner_id
            or invocation != self.invocation_id
            or any(
                _SHA256.fullmatch(item) is None
                for item in (
                    self.runtime_attestation_sha256,
                    self.runtime_profile_sha256,
                    self.oci_daemon_identity_sha256,
                    self.execution_fence_sha256,
                    self.sha256,
                )
            )
            or (self.observed_container_id is None)
            != (self.observed_container_state is None)
            or self.observed_container_id is not None
            and re.fullmatch(r"[0-9a-f]{64}", self.observed_container_id) is None
            or self.observed_container_state is not None
            and self.observed_container_state not in _CONTAINER_STATES
            or self.cleanup_confirmed is not True
            or not isinstance(value, dict)
            or value != expected
            or _canonical_json_bytes(value) != self.canonical_json
            or hashlib.sha256(self.canonical_json).hexdigest() != self.sha256
        ):
            raise ValueError("Invalid OCI cleanup proof")


def _cleanup_proof(
    *,
    invocation_id: str,
    attestation: TechnicalParserRuntimeAttestation,
    controller_owner_id: str,
    runtime_profile_sha256: str,
    oci_daemon_identity_sha256: str,
    execution_fence_sha256: str,
    observed_container_id: str | None,
    observed_container_state: str | None,
) -> TechnicalParserOciCleanupProof:
    completed_at = datetime.now(UTC)
    payload = {
        "cleanup_confirmed": True,
        "completed_at": _utc_text(completed_at),
        "controller_owner_id": controller_owner_id,
        "execution_fence_sha256": execution_fence_sha256,
        "invocation_id": invocation_id,
        "observed_container_id": observed_container_id,
        "observed_container_state": observed_container_state,
        "oci_daemon_identity_sha256": oci_daemon_identity_sha256,
        "runtime_attestation_sha256": attestation.sha256,
        "runtime_profile_sha256": runtime_profile_sha256,
        "schema": TECHNICAL_PARSER_OCI_CLEANUP_PROOF_SCHEMA,
    }
    canonical = _canonical_json_bytes(payload)
    return TechnicalParserOciCleanupProof(
        schema=TECHNICAL_PARSER_OCI_CLEANUP_PROOF_SCHEMA,
        invocation_id=invocation_id,
        runtime_attestation_sha256=attestation.sha256,
        controller_owner_id=controller_owner_id,
        runtime_profile_sha256=runtime_profile_sha256,
        oci_daemon_identity_sha256=oci_daemon_identity_sha256,
        execution_fence_sha256=execution_fence_sha256,
        observed_container_id=observed_container_id,
        observed_container_state=observed_container_state,
        cleanup_confirmed=True,
        completed_at=completed_at,
        canonical_json=canonical,
        sha256=hashlib.sha256(canonical).hexdigest(),
    )


class PosixFlockTechnicalParserExecutionFence:
    """Private, stable-inode POSIX flock with bounded or non-blocking entry."""

    def __init__(self, path: Path, *, wait_timeout_seconds: float = 10.0) -> None:
        if (
            os.name != "posix"
            or not isinstance(path, Path)
            or not path.is_absolute()
            or path.is_symlink()
            or not _finite_between(wait_timeout_seconds, 0.1, 30.0)
        ):
            raise TechnicalParserOciConfigurationError(
                "PARSER_OCI_EXECUTION_FENCE_INVALID"
            )
        try:
            resolved = path.resolve(strict=True)
            parent = resolved.parent
            parent_stat = parent.stat()
            if (
                resolved != path
                or not stat.S_ISDIR(parent_stat.st_mode)
                or parent_stat.st_uid != _posix_effective_user_id()
                or stat.S_IMODE(parent_stat.st_mode) & 0o022
            ):
                raise OSError
            descriptor = self._open_verified_descriptor(resolved)
            try:
                snapshot = os.fstat(descriptor)
            finally:
                os.close(descriptor)
        except OSError:
            raise TechnicalParserOciConfigurationError(
                "PARSER_OCI_EXECUTION_FENCE_INVALID"
            ) from None
        self._path = resolved
        self._device = snapshot.st_dev
        self._inode = snapshot.st_ino
        self._owner = snapshot.st_uid
        self._wait_timeout_seconds = float(wait_timeout_seconds)
        self._thread_lock = threading.Lock()
        identity = {
            "device": self._device,
            "inode": self._inode,
            "owner": self._owner,
            "path_sha256": hashlib.sha256(
                os.fsencode(str(self._path))
            ).hexdigest(),
            "schema": "technical-parser-execution-fence-v1",
        }
        self._identity_sha256 = hashlib.sha256(
            _canonical_json_bytes(identity)
        ).hexdigest()

    @staticmethod
    def _open_verified_descriptor(path: Path) -> int:
        flags = (
            os.O_RDWR
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = os.open(path, flags)
        try:
            path_stat = path.lstat()
            opened = os.fstat(descriptor)
            mode = stat.S_IMODE(opened.st_mode)
            if (
                not stat.S_ISREG(path_stat.st_mode)
                or not stat.S_ISREG(opened.st_mode)
                or path_stat.st_dev != opened.st_dev
                or path_stat.st_ino != opened.st_ino
                or opened.st_nlink != 1
                or opened.st_uid != _posix_effective_user_id()
                or mode & 0o077
                or mode & 0o600 != 0o600
            ):
                raise OSError
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    @property
    def identity_sha256(self) -> str:
        return self._identity_sha256

    @contextmanager
    def hold(self, *, wait: bool) -> Iterator[None]:
        if not isinstance(wait, bool):
            raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
        deadline = time.monotonic() + self._wait_timeout_seconds
        acquired_thread = (
            self._thread_lock.acquire(timeout=self._wait_timeout_seconds)
            if wait
            else self._thread_lock.acquire(blocking=False)
        )
        if not acquired_thread:
            raise TechnicalParserExecutionError("PARSER_EXECUTION_UNAVAILABLE")
        descriptor: int | None = None
        locked = False
        flock: Callable[[int, int], None] | None = None
        lock_un = 0
        try:
            descriptor = self._open_verified_descriptor(self._path)
            opened = os.fstat(descriptor)
            if (
                opened.st_dev != self._device
                or opened.st_ino != self._inode
                or opened.st_uid != self._owner
            ):
                raise OSError
            flock, lock_ex, lock_nb, lock_un = _posix_flock_contract()
            while True:
                try:
                    flock(descriptor, lock_ex | lock_nb)
                    locked = True
                    break
                except BlockingIOError:
                    if not wait or time.monotonic() >= deadline:
                        raise TechnicalParserExecutionError(
                            "PARSER_EXECUTION_UNAVAILABLE"
                        ) from None
                    time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
            opened = os.fstat(descriptor)
            if (
                opened.st_dev != self._device
                or opened.st_ino != self._inode
                or opened.st_uid != self._owner
            ):
                raise OSError
            yield
        except TechnicalParserExecutionError:
            raise
        except OSError:
            raise TechnicalParserExecutionError("PARSER_EXECUTION_UNAVAILABLE") from None
        finally:
            if descriptor is not None:
                if locked and flock is not None:
                    try:
                        flock(descriptor, lock_un)
                    except OSError:
                        pass
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            self._thread_lock.release()


def _strict_json(raw: bytes) -> object:
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    def reject_nonfinite(_value: str) -> object:
        raise ValueError

    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_nonfinite,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ):
        raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED") from None


def _verified_file(
    path: Path,
    *,
    expected_sha256: str,
    maximum_bytes: int,
    path_code: str,
    sha_code: str,
    retain_payload: bool = True,
) -> tuple[Path, bytes]:
    expected = _sha256(expected_sha256, code=sha_code)
    if not isinstance(path, Path) or not path.is_absolute() or path.is_symlink():
        raise TechnicalParserOciConfigurationError(path_code)
    source_fd: int | None = None
    try:
        resolved = path.resolve(strict=True)
        if resolved != path:
            raise OSError
        path_before = resolved.lstat()
        flags = (
            os.O_RDONLY
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        source_fd = os.open(resolved, flags)
        before = os.fstat(source_fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or not stat.S_ISREG(path_before.st_mode)
            or before.st_dev != path_before.st_dev
            or before.st_ino != path_before.st_ino
            or before.st_size > maximum_bytes
        ):
            raise OSError
        digest = hashlib.sha256()
        payload = bytearray()
        size = 0
        with os.fdopen(source_fd, "rb", closefd=True) as stream:
            source_fd = None
            while chunk := stream.read(_STREAM_CHUNK_BYTES):
                size += len(chunk)
                if size > maximum_bytes:
                    raise OSError
                digest.update(chunk)
                if retain_payload:
                    payload.extend(chunk)
            after = os.fstat(stream.fileno())
        path_after = resolved.lstat()
    except OSError:
        raise TechnicalParserOciConfigurationError(path_code) from None
    finally:
        if source_fd is not None:
            try:
                os.close(source_fd)
            except OSError:
                pass
    stable = (
        stat.S_ISREG(path_after.st_mode)
        and before.st_dev == after.st_dev
        and before.st_dev == path_after.st_dev
        and before.st_ino == after.st_ino
        and before.st_ino == path_after.st_ino
        and before.st_size == after.st_size == size
        and before.st_mtime_ns == after.st_mtime_ns
        and before.st_mtime_ns == path_after.st_mtime_ns
    )
    if not stable:
        raise TechnicalParserOciConfigurationError(path_code)
    if digest.hexdigest() != expected:
        raise TechnicalParserOciConfigurationError(sha_code)
    return resolved, bytes(payload)


def _copy_verified_file(
    source: Path,
    destination: Path,
    *,
    expected_sha256: str,
    maximum_bytes: int,
) -> None:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    source_fd: int | None = None
    try:
        path_before = source.lstat()
        source_fd = os.open(source, flags)
        before = os.fstat(source_fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or not stat.S_ISREG(path_before.st_mode)
            or before.st_dev != path_before.st_dev
            or before.st_ino != path_before.st_ino
            or before.st_size > maximum_bytes
        ):
            raise OSError
        digest = hashlib.sha256()
        size = 0
        with os.fdopen(source_fd, "rb", closefd=True) as input_stream:
            source_fd = None
            with destination.open("xb") as output_stream:
                while chunk := input_stream.read(_STREAM_CHUNK_BYTES):
                    size += len(chunk)
                    if size > maximum_bytes:
                        raise OSError
                    digest.update(chunk)
                    if output_stream.write(chunk) != len(chunk):
                        raise OSError
                output_stream.flush()
                os.fsync(output_stream.fileno())
            after = os.fstat(input_stream.fileno())
        path_after = source.lstat()
        destination_stat = destination.stat()
        stable = (
            stat.S_ISREG(path_after.st_mode)
            and before.st_dev == after.st_dev
            and before.st_dev == path_after.st_dev
            and before.st_ino == after.st_ino
            and before.st_ino == path_after.st_ino
            and before.st_size == after.st_size == size
            and before.st_mtime_ns == after.st_mtime_ns
            and before.st_mtime_ns == path_after.st_mtime_ns
            and stat.S_ISREG(destination_stat.st_mode)
            and destination_stat.st_size == size
        )
        if not stable or digest.hexdigest() != expected_sha256:
            raise OSError
        try:
            verified_destination, _ = _verified_file(
                destination,
                expected_sha256=expected_sha256,
                maximum_bytes=maximum_bytes,
                path_code="PARSER_OCI_RUNTIME_PATH_INVALID",
                sha_code="PARSER_OCI_RUNTIME_SHA256_INVALID",
                retain_payload=False,
            )
        except TechnicalParserOciConfigurationError:
            raise OSError from None
        if verified_destination != destination:
            raise OSError
    except OSError:
        raise TechnicalParserExecutionError("PARSER_EXECUTION_UNAVAILABLE") from None
    finally:
        if source_fd is not None:
            try:
                os.close(source_fd)
            except OSError:
                pass


def _validate_seccomp_profile(raw: bytes) -> None:
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    def reject_nonfinite(_value: str) -> object:
        raise ValueError

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_nonfinite,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ):
        raise TechnicalParserOciConfigurationError("PARSER_OCI_SECCOMP_PROFILE_INVALID") from None
    if not isinstance(value, dict) or value.get("defaultAction") != "SCMP_ACT_ERRNO":
        raise TechnicalParserOciConfigurationError("PARSER_OCI_SECCOMP_PROFILE_INVALID")
    if value.get("listenerPath") not in (None, "") or value.get("listenerMetadata") not in (
        None,
        "",
    ):
        raise TechnicalParserOciConfigurationError("PARSER_OCI_SECCOMP_PROFILE_INVALID")
    syscalls = value.get("syscalls")
    if not isinstance(syscalls, list) or not syscalls:
        raise TechnicalParserOciConfigurationError("PARSER_OCI_SECCOMP_PROFILE_INVALID")
    for entry in syscalls:
        if not isinstance(entry, dict):
            raise TechnicalParserOciConfigurationError("PARSER_OCI_SECCOMP_PROFILE_INVALID")
        names = entry.get("names")
        action = entry.get("action")
        if (
            not isinstance(names, list)
            or not all(isinstance(name, str) for name in names)
            or not isinstance(action, str)
        ):
            raise TechnicalParserOciConfigurationError("PARSER_OCI_SECCOMP_PROFILE_INVALID")
        safe_denials = {
            "SCMP_ACT_ERRNO",
            "SCMP_ACT_KILL",
            "SCMP_ACT_KILL_PROCESS",
            "SCMP_ACT_KILL_THREAD",
            "SCMP_ACT_TRAP",
        }
        if action not in safe_denials and _DENIED_SECCOMP_SYSCALLS.intersection(names):
            raise TechnicalParserOciConfigurationError("PARSER_OCI_SECCOMP_PROFILE_INVALID")


def _controller_environment() -> dict[str, str]:
    return {}


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> bool:
    if os.name != "posix":
        return False
    killpg = getattr(os, "killpg", None)
    sigkill = getattr(signal, "SIGKILL", None)
    if not callable(killpg) or not isinstance(sigkill, int):
        return False
    try:
        killpg(process.pid, sigkill)
    except ProcessLookupError:
        pass
    except OSError:
        return False
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            return False
    try:
        process.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return False
    deadline = time.monotonic() + 2.0
    while True:
        try:
            killpg(process.pid, 0)
        except ProcessLookupError:
            return process.poll() is not None
        except OSError:
            return False
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.01)


class _SubprocessOciRuntimeAdapter:
    """Shell-free controller process with concurrent bounded standard streams."""

    def run(
        self,
        args: Sequence[str],
        *,
        stdin_writer: _CommandInputWriter | None,
        timeout_seconds: float,
        stdout_limit: int,
        stderr_limit: int,
        environment: Mapping[str, str],
        on_terminate: Callable[[], None] | None = None,
    ) -> _BoundedCommandResult:
        if (
            os.name != "posix"
            or not args
            or not _finite_between(timeout_seconds, 0.1, 300.0)
            or not isinstance(stdout_limit, int)
            or isinstance(stdout_limit, bool)
            or stdout_limit < 0
            or not isinstance(stderr_limit, int)
            or isinstance(stderr_limit, bool)
            or stderr_limit < 0
        ):
            raise _BoundedCommandError("unavailable")
        with tempfile.TemporaryDirectory(prefix="classifire-parser-controller-") as working:
            try:
                process = subprocess.Popen(  # noqa: S603  # nosec B603
                    tuple(args),
                    stdin=subprocess.PIPE if stdin_writer is not None else subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=working,
                    env=dict(environment),
                    close_fds=True,
                    start_new_session=True,
                )
            except (OSError, subprocess.SubprocessError):
                raise _BoundedCommandError("unavailable") from None
            return self._communicate_bounded(
                process,
                args=tuple(args),
                stdin_writer=stdin_writer,
                timeout_seconds=float(timeout_seconds),
                stdout_limit=stdout_limit,
                stderr_limit=stderr_limit,
                on_terminate=on_terminate,
            )

    @staticmethod
    def _communicate_bounded(
        process: subprocess.Popen[bytes],
        *,
        args: Sequence[str],
        stdin_writer: _CommandInputWriter | None,
        timeout_seconds: float,
        stdout_limit: int,
        stderr_limit: int,
        on_terminate: Callable[[], None] | None,
    ) -> _BoundedCommandResult:
        stdout = process.stdout
        stderr = process.stderr
        if stdout is None or stderr is None:
            if not _terminate_process_tree(process):
                raise _BoundedCommandError("termination_failed")
            raise _BoundedCommandError("unavailable")

        termination_lock = threading.Lock()
        termination_called = False
        termination_failed = threading.Event()

        def terminate() -> None:
            nonlocal termination_called
            with termination_lock:
                if termination_called:
                    return
                termination_called = True
                try:
                    if on_terminate is not None:
                        on_terminate()
                except BaseException:
                    termination_failed.set()
                finally:
                    if not _terminate_process_tree(process):
                        termination_failed.set()

        captured_stdout = bytearray()
        captured_stderr = bytearray()
        stdout_overflow = threading.Event()
        stderr_seen = threading.Event()
        capture_failed = threading.Event()
        input_errors: list[BaseException] = []

        def capture(
            stream: BinaryIO,
            destination: bytearray,
            *,
            limit: int,
            overflow: threading.Event,
        ) -> None:
            try:
                while True:
                    remaining = limit - len(destination)
                    chunk = stream.read(min(_STREAM_CHUNK_BYTES, max(1, remaining + 1)))
                    if not chunk:
                        return
                    if not isinstance(chunk, bytes):
                        capture_failed.set()
                        terminate()
                        return
                    if len(chunk) > remaining:
                        destination.extend(chunk[:remaining])
                        overflow.set()
                        terminate()
                        return
                    destination.extend(chunk)
            except (OSError, ValueError):
                capture_failed.set()
                terminate()
            finally:
                try:
                    stream.close()
                except OSError:
                    pass

        def write_input() -> None:
            stdin = process.stdin
            if stdin is None or stdin_writer is None:
                input_errors.append(_BoundedCommandError("input_failed"))
                terminate()
                return
            try:
                stdin_writer(cast(BinaryIO, stdin))
                stdin.flush()
            except BaseException as error:
                input_errors.append(error)
                terminate()
            finally:
                try:
                    stdin.close()
                except OSError:
                    pass

        stdout_thread = threading.Thread(
            target=capture,
            args=(cast(BinaryIO, stdout), captured_stdout),
            kwargs={"limit": stdout_limit, "overflow": stdout_overflow},
            name="classifire-parser-stdout",
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=capture,
            args=(cast(BinaryIO, stderr), captured_stderr),
            kwargs={"limit": stderr_limit, "overflow": stderr_seen},
            name="classifire-parser-stderr",
            daemon=True,
        )
        input_thread = (
            threading.Thread(
                target=write_input,
                name="classifire-parser-stdin",
                daemon=True,
            )
            if stdin_writer is not None
            else None
        )
        timed_out = False
        interrupted: BaseException | None = None
        started_threads: list[threading.Thread] = []
        try:
            for thread in (stdout_thread, stderr_thread, input_thread):
                if thread is not None:
                    thread.start()
                    started_threads.append(thread)
            try:
                process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                terminate()
            except BaseException as error:
                interrupted = error
                terminate()
        except BaseException as error:
            interrupted = error
            terminate()
        finally:
            for thread in started_threads:
                thread.join(timeout=2)
            if any(thread.is_alive() for thread in started_threads):
                termination_failed.set()
                terminate()
                for thread in started_threads:
                    thread.join(timeout=2)
            for stream in (process.stdin, stdout, stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass

        if termination_failed.is_set():
            raise _BoundedCommandError("termination_failed")
        if interrupted is not None:
            raise interrupted
        if input_errors and isinstance(
            input_errors[0],
            TechnicalParserExecutionError,
        ):
            raise input_errors[0]
        if timed_out:
            raise _BoundedCommandError("timeout")
        if stdout_overflow.is_set():
            raise _BoundedCommandError("stdout_overflow")
        if stderr_seen.is_set() or captured_stderr:
            raise _BoundedCommandError("stderr_output")
        if capture_failed.is_set():
            raise _BoundedCommandError("unavailable")
        if input_errors:
            raise _BoundedCommandError("input_failed")
        if any(thread.is_alive() for thread in started_threads):
            raise _BoundedCommandError("termination_failed")
        return _BoundedCommandResult(
            returncode=process.returncode if process.returncode is not None else -1,
            stdout=bytes(captured_stdout),
            stderr=b"",
        )


def _runtime_profile_payload(
    profile: TechnicalParserOciRuntimeProfile,
    *,
    controller_owner_id: str,
    image_reference: str,
    runtime_host: str,
    runtime_executable_sha256: str,
    seccomp_profile_sha256: str,
) -> dict[str, object]:
    return {
        "capabilities": [],
        "cgroup_namespace": "private",
        "concurrency": profile.concurrency,
        "container_entrypoint": TECHNICAL_PARSER_OCI_ENTRYPOINT,
        "controller_config": "private-empty-v1",
        "controller_owner_id": controller_owner_id,
        "cleanup_timeout_seconds": format(profile.cleanup_timeout_seconds, ".17g"),
        "control_timeout_seconds": format(profile.control_timeout_seconds, ".17g"),
        "core_dump_bytes": 0,
        "image_reference": image_reference,
        "ipc_namespace": "none",
        "layout_output_bytes": _LAYOUT_OUTPUT_LIMIT,
        "layout_timeout_seconds": format(profile.layout_timeout_seconds, ".17g"),
        "log_driver": "none",
        "memory_bytes": profile.memory_bytes,
        "memory_swap_bytes": profile.memory_swap_bytes,
        "nano_cpus": profile.nano_cpus,
        "network": "none",
        "nofile_limit": profile.nofile_limit,
        "page_output_bytes": _PAGE_OUTPUT_LIMIT,
        "page_timeout_seconds": format(profile.page_timeout_seconds, ".17g"),
        "pids_limit": profile.pids_limit,
        "platform": profile.platform,
        "pull": "never",
        "read_only_root": True,
        "runtime_executable_sha256": runtime_executable_sha256,
        "runtime_host": runtime_host,
        "schema": TECHNICAL_PARSER_OCI_PROFILE_SCHEMA,
        "seccomp_profile_sha256": seccomp_profile_sha256,
        "tmpfs_bytes": profile.tmpfs_bytes,
        "transport_schema": TECHNICAL_PARSER_OCI_TRANSPORT_SCHEMA,
        "user": "65532:65532",
        "uts_namespace": "private",
    }


def _image_reference(value: object) -> tuple[str, str]:
    if not isinstance(value, str) or _IMAGE_REFERENCE.fullmatch(value) is None:
        raise TechnicalParserOciConfigurationError("PARSER_OCI_IMAGE_REFERENCE_INVALID")
    digest = value.rsplit("@sha256:", 1)[1]
    return value, digest


def _policy(value: object) -> str:
    if not isinstance(value, str) or _POLICY.fullmatch(value) is None:
        raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
    return value


def _invocation_id(value: object) -> str:
    if not isinstance(value, str):
        raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED") from None
    if parsed.version != 4 or str(parsed) != value:
        raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
    return value


def _expected_attestation_sha256(value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
    return value


def _json_string(raw: bytes) -> str:
    value = _strict_json(raw)
    if not isinstance(value, str):
        raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
    return value


def _daemon_identity_sha256(value: object) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 256
        or value != value.strip()
        or any(ord(character) < 0x21 or ord(character) > 0x7E for character in value)
    ):
        raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
    return hashlib.sha256(
        b"classifire-technical-parser-oci-daemon-v1\x00" + value.encode("ascii")
    ).hexdigest()


def _json_object(raw: bytes) -> dict[str, object]:
    value = _strict_json(raw)
    if not isinstance(value, dict):
        raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
    return cast(dict[str, object], value)


def _json_string_list(raw: bytes) -> list[str]:
    value = _strict_json(raw)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
    return cast(list[str], value)


class DigestPinnedOciTechnicalParserRunner:
    """Concrete TechnicalParserRunner using a pre-admitted local OCI image."""

    def __init__(
        self,
        *,
        runtime_path: Path,
        runtime_executable_sha256: str,
        runtime_host: str,
        controller_owner_id: str,
        image_reference: str,
        seccomp_profile_path: Path,
        seccomp_profile_sha256: str,
        profile: TechnicalParserOciRuntimeProfile,
        execution_fence: TechnicalParserExecutionFence,
        runtime_adapter: _OciRuntimeAdapter | None = None,
    ) -> None:
        reference, digest = _image_reference(image_reference)
        if (
            not isinstance(runtime_host, str)
            or _ROOTLESS_RUNTIME_HOST.fullmatch(runtime_host) is None
        ):
            raise TechnicalParserOciConfigurationError("PARSER_OCI_RUNTIME_HOST_INVALID")
        if profile.platform not in _PLATFORMS:
            raise TechnicalParserOciConfigurationError("PARSER_OCI_PLATFORM_INVALID")
        try:
            parsed_owner_id = UUID(controller_owner_id)
        except (ValueError, AttributeError, TypeError):
            raise TechnicalParserOciConfigurationError(
                "PARSER_OCI_CONTROLLER_OWNER_INVALID"
            ) from None
        if parsed_owner_id.version != 4 or str(parsed_owner_id) != controller_owner_id:
            raise TechnicalParserOciConfigurationError(
                "PARSER_OCI_CONTROLLER_OWNER_INVALID"
            )
        try:
            fence_identity = execution_fence.identity_sha256
            fence_hold = execution_fence.hold
        except (AttributeError, TypeError, ValueError):
            raise TechnicalParserOciConfigurationError(
                "PARSER_OCI_EXECUTION_FENCE_INVALID"
            ) from None
        if (
            not isinstance(fence_identity, str)
            or _SHA256.fullmatch(fence_identity) is None
            or not callable(fence_hold)
        ):
            raise TechnicalParserOciConfigurationError(
                "PARSER_OCI_EXECUTION_FENCE_INVALID"
            )
        runtime, _runtime_bytes = _verified_file(
            runtime_path,
            expected_sha256=runtime_executable_sha256,
            maximum_bytes=_RUNTIME_FILE_MAX_BYTES,
            path_code="PARSER_OCI_RUNTIME_PATH_INVALID",
            sha_code="PARSER_OCI_RUNTIME_SHA256_INVALID",
            retain_payload=False,
        )
        seccomp, seccomp_bytes = _verified_file(
            seccomp_profile_path,
            expected_sha256=seccomp_profile_sha256,
            maximum_bytes=_SECCOMP_FILE_MAX_BYTES,
            path_code="PARSER_OCI_SECCOMP_PROFILE_INVALID",
            sha_code="PARSER_OCI_SECCOMP_SHA256_INVALID",
        )
        _validate_seccomp_profile(seccomp_bytes)
        self._runtime_path = runtime
        self._runtime_executable_sha256 = runtime_executable_sha256
        self._runtime_host = runtime_host
        self._controller_owner_id = controller_owner_id
        self._image_reference = reference
        self._worker_image_digest = digest
        self._seccomp_profile_path = seccomp
        self._seccomp_profile_sha256 = seccomp_profile_sha256
        self._seccomp_profile_bytes = seccomp_bytes
        self._seccomp_profile_value = cast(
            dict[str, object],
            json.loads(seccomp_bytes.decode("utf-8")),
        )
        self._profile = profile
        self._execution_fence = execution_fence
        self._execution_fence_sha256 = fence_identity
        self._adapter = runtime_adapter or _SubprocessOciRuntimeAdapter()
        self._environment = _controller_environment()
        self._profile_payload = _runtime_profile_payload(
            profile,
            controller_owner_id=controller_owner_id,
            image_reference=reference,
            runtime_host=runtime_host,
            runtime_executable_sha256=runtime_executable_sha256,
            seccomp_profile_sha256=seccomp_profile_sha256,
        )
        self._runtime_profile_sha256 = hashlib.sha256(
            _canonical_json_bytes(self._profile_payload)
        ).hexdigest()
        self._capacity = threading.BoundedSemaphore(profile.concurrency)
        self._controller_lock = threading.RLock()
        self._attestation_lock = threading.Lock()
        self._active_runtime_path: Path | None = None
        self._active_runtime_config_path: Path | None = None
        self._containment_lost = threading.Event()

    @property
    def worker_image_digest(self) -> str:
        return self._worker_image_digest

    @property
    def runtime_profile_sha256(self) -> str:
        return self._runtime_profile_sha256

    @property
    def execution_fence_sha256(self) -> str:
        return self._execution_fence_sha256

    @contextmanager
    def _normal_execution_guard(self) -> Iterator[None]:
        # Normal work must never queue behind reconciliation: after a cleanup
        # finalizer commits, an older caller may no longer create this invocation.
        with self._execution_fence.hold(wait=False):
            with self._controller_lock:
                yield

    @staticmethod
    def _invoke_host_callback(
        callback: Callable[..., object],
        *args: object,
    ) -> None:
        try:
            callback(*args)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:
            raise _HostCallbackFailure(error) from error

    @contextmanager
    def _terminal_receipt_guard(
        self,
        callbacks: _ExecutionCallbacks,
    ) -> Iterator[None]:
        try:
            yield
        except TechnicalParserExecutionError as error:
            if (
                callbacks.prepared
                and callbacks.finalize is not None
                and error.receipt is not None
            ):
                self._invoke_host_callback(callbacks.finalize, error.receipt)
            raise

    def inspect_layout(
        self,
        request: bytes,
        *,
        source: BinaryIO,
        invocation_id: str,
        expected_attestation_sha256: str,
        prepare: Callable[[], None] | None = None,
        authorize: Callable[[], None] | None = None,
        finalize: Callable[[TechnicalParserExecutionReceipt], None] | None = None,
    ) -> TechnicalParserExecutionSuccess:
        try:
            parsed = parse_technical_parser_layout_request(request)
        except TechnicalParserProtocolError:
            raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED") from None
        return self._execute(
            "layout",
            request=request,
            parsed=parsed,
            source=source,
            invocation_id=invocation_id,
            expected_attestation_sha256=expected_attestation_sha256,
            prepare=prepare,
            authorize=authorize,
            finalize=finalize,
        )

    def extract_page(
        self,
        request: bytes,
        *,
        source: BinaryIO,
        invocation_id: str,
        expected_attestation_sha256: str,
        prepare: Callable[[], None] | None = None,
        authorize: Callable[[], None] | None = None,
        finalize: Callable[[TechnicalParserExecutionReceipt], None] | None = None,
    ) -> TechnicalParserExecutionSuccess:
        try:
            parsed = parse_technical_parser_request(request)
        except TechnicalParserProtocolError:
            raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED") from None
        return self._execute(
            "page",
            request=request,
            parsed=parsed,
            source=source,
            invocation_id=invocation_id,
            expected_attestation_sha256=expected_attestation_sha256,
            prepare=prepare,
            authorize=authorize,
            finalize=finalize,
        )

    def probe(
        self,
        *,
        extraction_policy: str,
        extraction_policy_sha256: str,
    ) -> TechnicalParserRuntimeAttestation:
        """Attest the local runtime and exact image without claiming database work."""

        policy = _policy(extraction_policy)
        if (
            not isinstance(extraction_policy_sha256, str)
            or _SHA256.fullmatch(extraction_policy_sha256) is None
        ):
            raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
        if self._containment_lost.is_set():
            raise TechnicalParserExecutionError("PARSER_EXECUTION_CONTAINMENT_LOST")
        with self._controller_lock:
            self._verify_controller_files()
            with self._materialized_controller_files() as (
                runtime_path,
                runtime_config_path,
                _seccomp_runtime_path,
            ):
                self._active_runtime_path = runtime_path
                self._active_runtime_config_path = runtime_config_path
                try:
                    with self._attestation_lock:
                        attestation, _image_id, _daemon_identity = self._attest_runtime(
                            extraction_policy=policy,
                            extraction_policy_sha256=extraction_policy_sha256,
                        )
                        return attestation
                finally:
                    self._active_runtime_config_path = None
                    self._active_runtime_path = None

    def _validated_cleanup_attestation_claims(
        self,
        attestation: object,
    ) -> dict[str, object]:
        if (
            not isinstance(attestation, TechnicalParserRuntimeAttestation)
            or attestation.schema != TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2
            or attestation.engine != TECHNICAL_PARSER_OCI_ENGINE
        ):
            raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
        payload = attestation.as_dict()
        claims = payload.get("claims")
        expected_keys = {
            "controller_owner_id",
            "execution_fence_sha256",
            "extraction_policy",
            "extraction_policy_sha256",
            "image_id",
            "image_reference",
            "oci_daemon_identity_sha256",
            "oci_profile_schema",
            "platform",
            "runtime_executable_sha256",
            "runtime_host",
            "runtime_profile_sha256",
            "seccomp_profile_sha256",
            "transport_schema",
            "worker_image_digest",
        }
        if not isinstance(claims, dict) or set(claims) != expected_keys:
            raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
        try:
            owner = _uuid4_text(claims.get("controller_owner_id"))
        except ValueError:
            raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED") from None
        image_id = claims.get("image_id")
        if (
            owner != self._controller_owner_id
            or claims.get("execution_fence_sha256")
            != self._execution_fence_sha256
            or claims.get("runtime_profile_sha256")
            != self._runtime_profile_sha256
            or claims.get("runtime_host") != self._runtime_host
            or claims.get("runtime_executable_sha256")
            != self._runtime_executable_sha256
            or claims.get("seccomp_profile_sha256")
            != self._seccomp_profile_sha256
            or claims.get("image_reference") != self._image_reference
            or claims.get("worker_image_digest") != self._worker_image_digest
            or claims.get("oci_profile_schema")
            != TECHNICAL_PARSER_OCI_PROFILE_SCHEMA
            or claims.get("transport_schema")
            != TECHNICAL_PARSER_OCI_TRANSPORT_SCHEMA
            or claims.get("platform") != self._profile.platform
            or not isinstance(image_id, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None
            or not isinstance(claims.get("oci_daemon_identity_sha256"), str)
            or _SHA256.fullmatch(cast(str, claims["oci_daemon_identity_sha256"]))
            is None
            or not isinstance(claims.get("extraction_policy_sha256"), str)
            or _SHA256.fullmatch(cast(str, claims["extraction_policy_sha256"]))
            is None
        ):
            raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
        _policy(claims.get("extraction_policy"))
        return cast(dict[str, object], claims)

    def cleanup_orphan_invocation(
        self,
        *,
        invocation_id: str,
        operation: Literal["layout", "page"],
        persisted_runtime_attestation: TechnicalParserRuntimeAttestation,
        finalize: Callable[[TechnicalParserOciCleanupProof], None] | None = None,
    ) -> TechnicalParserOciCleanupProof:
        """Clean at most one exact orphan without ever creating or starting work."""

        invocation = _invocation_id(invocation_id)
        if operation not in {"layout", "page"} or (
            finalize is not None and not callable(finalize)
        ):
            raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
        claims = self._validated_cleanup_attestation_claims(
            persisted_runtime_attestation
        )
        extraction_policy = cast(str, claims["extraction_policy"])
        extraction_policy_sha256 = cast(str, claims["extraction_policy_sha256"])
        expected_image_id = cast(str, claims["image_id"])
        daemon_identity_sha256 = cast(
            str,
            claims["oci_daemon_identity_sha256"],
        )
        label = f"{TECHNICAL_PARSER_OCI_INVOCATION_LABEL}={invocation}"
        with self._execution_fence.hold(wait=True):
            with self._controller_lock:
                self._verify_controller_files()
                with self._materialized_controller_files() as (
                    runtime_path,
                    runtime_config_path,
                    seccomp_runtime_path,
                ):
                    self._active_runtime_path = runtime_path
                    self._active_runtime_config_path = runtime_config_path
                    try:
                        with self._attestation_lock:
                            current_attestation, _current_image_id, _current_daemon = (
                                self._attest_runtime(
                                    extraction_policy=extraction_policy,
                                    extraction_policy_sha256=(
                                        extraction_policy_sha256
                                    ),
                                )
                            )
                        if current_attestation != persisted_runtime_attestation:
                            raise TechnicalParserExecutionError(
                                "PARSER_EXECUTION_FAILED"
                            )
                        container_ids = self._container_ids(
                            f"label={label}",
                            cleanup=True,
                        )
                        if len(container_ids) > 1:
                            self._containment_lost.set()
                            raise TechnicalParserExecutionError(
                                "PARSER_EXECUTION_CONTAINMENT_LOST"
                            )
                        observed_container_id: str | None = None
                        observed_container_state: str | None = None
                        if container_ids:
                            observed_container_id = container_ids[0]
                            try:
                                state = self._validate_container_profile(
                                    container_id=observed_container_id,
                                    label=label,
                                    operation=operation,
                                    expected_image_id=expected_image_id,
                                    seccomp_runtime_path=seccomp_runtime_path,
                                )
                            except TechnicalParserExecutionError:
                                self._containment_lost.set()
                                raise TechnicalParserExecutionError(
                                    "PARSER_EXECUTION_CONTAINMENT_LOST"
                                ) from None
                            status = state.get("Status")
                            if status not in _CONTAINER_STATES:
                                self._containment_lost.set()
                                raise TechnicalParserExecutionError(
                                    "PARSER_EXECUTION_CONTAINMENT_LOST"
                                )
                            observed_container_state = cast(str, status)
                            cleanup_confirmed = self._remove_and_confirm(
                                (observed_container_id,),
                                label=label,
                                expected_daemon_identity_sha256=(
                                    daemon_identity_sha256
                                ),
                                permit_quarantined=True,
                            )
                        else:
                            cleanup_confirmed = self._remove_and_confirm(
                                (),
                                label=label,
                                expected_daemon_identity_sha256=(
                                    daemon_identity_sha256
                                ),
                                permit_quarantined=True,
                            )
                        if not cleanup_confirmed:
                            self._containment_lost.set()
                            raise TechnicalParserExecutionError(
                                "PARSER_EXECUTION_CONTAINMENT_LOST"
                            )
                        self._require_daemon_identity_or_lose(
                            daemon_identity_sha256
                        )
                        proof = _cleanup_proof(
                            invocation_id=invocation,
                            attestation=persisted_runtime_attestation,
                            controller_owner_id=self._controller_owner_id,
                            runtime_profile_sha256=self._runtime_profile_sha256,
                            oci_daemon_identity_sha256=daemon_identity_sha256,
                            execution_fence_sha256=(
                                self._execution_fence_sha256
                            ),
                            observed_container_id=observed_container_id,
                            observed_container_state=observed_container_state,
                        )
                        if finalize is not None:
                            finalize(proof)
                        return proof
                    finally:
                        self._active_runtime_config_path = None
                        self._active_runtime_path = None

    def _execute(
        self,
        operation: Literal["layout", "page"],
        *,
        request: bytes,
        parsed: TechnicalParserLayoutRequest | TechnicalParserRequest,
        source: BinaryIO,
        invocation_id: str,
        expected_attestation_sha256: str,
        prepare: Callable[[], None] | None,
        authorize: Callable[[], None] | None,
        finalize: Callable[[TechnicalParserExecutionReceipt], None] | None,
    ) -> TechnicalParserExecutionSuccess:
        invocation = _invocation_id(invocation_id)
        expected_attestation = _expected_attestation_sha256(
            expected_attestation_sha256
        )
        if self._containment_lost.is_set():
            raise TechnicalParserExecutionError("PARSER_EXECUTION_CONTAINMENT_LOST")
        if parsed.worker_image_digest != self._worker_image_digest:
            raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
        callback_values = (prepare, authorize, finalize)
        if any(value is not None for value in callback_values) != all(
            callable(value) for value in callback_values
        ):
            raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
        callbacks = _ExecutionCallbacks(
            prepare=prepare,
            authorize=authorize,
            finalize=finalize,
        )
        if not self._capacity.acquire(blocking=False):
            raise TechnicalParserExecutionError("PARSER_EXECUTION_UNAVAILABLE")
        try:
            with self._normal_execution_guard(), self._terminal_receipt_guard(callbacks):
                self._verify_controller_files()
                with self._materialized_controller_files() as (
                    runtime_path,
                    runtime_config_path,
                    seccomp_runtime_path,
                ):
                    self._active_runtime_path = runtime_path
                    self._active_runtime_config_path = runtime_config_path
                    try:
                        with self._attestation_lock:
                            attestation, image_id, daemon_identity_sha256 = (
                                self._attest_runtime(
                                extraction_policy=parsed.extraction_policy,
                                extraction_policy_sha256=parsed.extraction_policy_sha256,
                                )
                            )
                        label = f"{TECHNICAL_PARSER_OCI_INVOCATION_LABEL}={invocation}"
                        try:
                            preexisting_ids = self._ids_for_preexisting_execution_or_lose(
                                label
                            )
                        except TechnicalParserExecutionError as error:
                            if error.code != "PARSER_EXECUTION_CONTAINMENT_LOST":
                                raise
                            raise self._execution_error(
                                error.code,
                                execution_state="containment_lost",
                                operation=operation,
                                invocation=invocation,
                                expected_attestation_sha256=expected_attestation,
                                attestation=attestation,
                                container_id=None,
                                started_at=None,
                                cleanup_confirmed=False,
                            ) from None
                        if preexisting_ids:
                            self._containment_lost.set()
                            raise self._execution_error(
                                "PARSER_EXECUTION_CONTAINMENT_LOST",
                                execution_state="containment_lost",
                                operation=operation,
                                invocation=invocation,
                                expected_attestation_sha256=expected_attestation,
                                attestation=attestation,
                                container_id=(
                                    preexisting_ids[0]
                                    if len(preexisting_ids) == 1
                                    else None
                                ),
                                started_at=None,
                                cleanup_confirmed=False,
                            )
                        if attestation.sha256 != expected_attestation:
                            raise self._execution_error(
                                "PARSER_EXECUTION_FAILED",
                                execution_state="not_started",
                                operation=operation,
                                invocation=invocation,
                                expected_attestation_sha256=expected_attestation,
                                attestation=attestation,
                                container_id=None,
                                started_at=None,
                                cleanup_confirmed=True,
                            )
                        if callbacks.prepare is not None:
                            self._invoke_host_callback(callbacks.prepare)
                            callbacks.prepared = True
                        try:
                            if callbacks.authorize is not None:
                                callbacks.authorize()
                        except (KeyboardInterrupt, SystemExit):
                            raise
                        except Exception:
                            raise self._execution_error(
                                "PARSER_EXECUTION_UNAVAILABLE",
                                execution_state="not_started",
                                operation=operation,
                                invocation=invocation,
                                expected_attestation_sha256=expected_attestation,
                                attestation=attestation,
                                container_id=None,
                                started_at=None,
                                cleanup_confirmed=True,
                            ) from None
                        try:
                            admitted_collision_ids = (
                                self._ids_for_preexisting_execution_or_lose(label)
                            )
                        except TechnicalParserExecutionError:
                            raise self._execution_error(
                                "PARSER_EXECUTION_CONTAINMENT_LOST",
                                execution_state="containment_lost",
                                operation=operation,
                                invocation=invocation,
                                expected_attestation_sha256=expected_attestation,
                                attestation=attestation,
                                container_id=None,
                                started_at=None,
                                cleanup_confirmed=False,
                            ) from None
                        if admitted_collision_ids:
                            self._containment_lost.set()
                            raise self._execution_error(
                                "PARSER_EXECUTION_CONTAINMENT_LOST",
                                execution_state="containment_lost",
                                operation=operation,
                                invocation=invocation,
                                expected_attestation_sha256=expected_attestation,
                                attestation=attestation,
                                container_id=(
                                    admitted_collision_ids[0]
                                    if len(admitted_collision_ids) == 1
                                    else None
                                ),
                                started_at=None,
                                cleanup_confirmed=False,
                            )
                        try:
                            self._require_daemon_identity_or_lose(
                                daemon_identity_sha256
                            )
                        except TechnicalParserExecutionError:
                            raise self._execution_error(
                                "PARSER_EXECUTION_CONTAINMENT_LOST",
                                execution_state="containment_lost",
                                operation=operation,
                                invocation=invocation,
                                expected_attestation_sha256=expected_attestation,
                                attestation=attestation,
                                container_id=None,
                                started_at=None,
                                cleanup_confirmed=False,
                            ) from None
                        container_id: str | None = None
                        started_at: datetime | None = None
                        try:
                            try:
                                container_id = self._create_container(
                                    operation=operation,
                                    invocation=invocation,
                                    label=label,
                                    expected_image_id=image_id,
                                    expected_daemon_identity_sha256=(
                                        daemon_identity_sha256
                                    ),
                                    seccomp_runtime_path=seccomp_runtime_path,
                                )
                            except (KeyboardInterrupt, SystemExit):
                                raise
                            except TechnicalParserExecutionError as error:
                                try:
                                    self._require_daemon_identity_or_lose(
                                        daemon_identity_sha256
                                    )
                                except TechnicalParserExecutionError:
                                    raise self._execution_error(
                                        "PARSER_EXECUTION_CONTAINMENT_LOST",
                                        execution_state="containment_lost",
                                        operation=operation,
                                        invocation=invocation,
                                        expected_attestation_sha256=(
                                            expected_attestation
                                        ),
                                        attestation=attestation,
                                        container_id=(
                                            error.container_id
                                            if isinstance(error, _OciContainmentLost)
                                            else None
                                        ),
                                        started_at=None,
                                        cleanup_confirmed=False,
                                    ) from None
                                if error.code == "PARSER_EXECUTION_CONTAINMENT_LOST":
                                    raise self._execution_error(
                                        error.code,
                                        execution_state="containment_lost",
                                        operation=operation,
                                        invocation=invocation,
                                        expected_attestation_sha256=expected_attestation,
                                        attestation=attestation,
                                        container_id=(
                                            error.container_id
                                            if isinstance(error, _OciContainmentLost)
                                            else None
                                        ),
                                        started_at=None,
                                        cleanup_confirmed=False,
                                    ) from None
                                raise self._execution_error(
                                    error.code,
                                    execution_state="not_started",
                                    operation=operation,
                                    invocation=invocation,
                                    expected_attestation_sha256=expected_attestation,
                                    attestation=attestation,
                                    container_id=None,
                                    started_at=None,
                                    cleanup_confirmed=True,
                                ) from None
                            started_at = datetime.now(UTC)
                            try:
                                output = self._start_container(
                                    container_id=container_id,
                                    label=label,
                                    operation=operation,
                                    expected_daemon_identity_sha256=(
                                        daemon_identity_sha256
                                    ),
                                    request=request,
                                    parsed=parsed,
                                    source=source,
                                )
                            except (KeyboardInterrupt, SystemExit):
                                raise
                            except TechnicalParserExecutionError as error:
                                if error.code == "PARSER_EXECUTION_CONTAINMENT_LOST":
                                    raise self._execution_error(
                                        error.code,
                                        execution_state="containment_lost",
                                        operation=operation,
                                        invocation=invocation,
                                        expected_attestation_sha256=expected_attestation,
                                        attestation=attestation,
                                        container_id=container_id,
                                        started_at=started_at,
                                        cleanup_confirmed=False,
                                    ) from None
                                raise self._execution_error(
                                    error.code,
                                    execution_state="failed",
                                    operation=operation,
                                    invocation=invocation,
                                    expected_attestation_sha256=expected_attestation,
                                    attestation=attestation,
                                    container_id=container_id,
                                    started_at=started_at,
                                    cleanup_confirmed=True,
                                ) from None
                        finally:
                            if container_id is not None and not self._remove_and_confirm(
                                (container_id,),
                                label=label,
                                expected_daemon_identity_sha256=(
                                    daemon_identity_sha256
                                ),
                            ):
                                self._containment_lost.set()
                                raise self._execution_error(
                                    "PARSER_EXECUTION_CONTAINMENT_LOST",
                                    execution_state="containment_lost",
                                    operation=operation,
                                    invocation=invocation,
                                    expected_attestation_sha256=expected_attestation,
                                    attestation=attestation,
                                    container_id=container_id,
                                    started_at=started_at,
                                    cleanup_confirmed=False,
                                ) from None
                            if container_id is not None:
                                try:
                                    self._require_daemon_identity_or_lose(
                                        daemon_identity_sha256
                                    )
                                except TechnicalParserExecutionError:
                                    raise self._execution_error(
                                        "PARSER_EXECUTION_CONTAINMENT_LOST",
                                        execution_state="containment_lost",
                                        operation=operation,
                                        invocation=invocation,
                                        expected_attestation_sha256=expected_attestation,
                                        attestation=attestation,
                                        container_id=container_id,
                                        started_at=started_at,
                                        cleanup_confirmed=False,
                                    ) from None
                        if container_id is None or started_at is None:
                            raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
                        receipt = create_technical_parser_execution_receipt(
                            execution_state="succeeded",
                            operation=operation,
                            invocation_id=invocation,
                            expected_attestation_sha256=expected_attestation,
                            attestation=attestation,
                            outcome_code="PARSER_EXECUTION_SUCCEEDED",
                            container_id=container_id,
                            started_at=started_at,
                            completed_at=datetime.now(UTC),
                            exit_code=0,
                            stdout_sha256=hashlib.sha256(output).hexdigest(),
                            stdout_size_bytes=len(output),
                            cleanup_confirmed=True,
                        )
                        if callbacks.prepared and callbacks.finalize is not None:
                            self._invoke_host_callback(callbacks.finalize, receipt)
                        return TechnicalParserExecutionSuccess(
                            output=output,
                            receipt=receipt,
                        )
                    finally:
                        self._active_runtime_config_path = None
                        self._active_runtime_path = None
        except _HostCallbackFailure as error:
            raise error.cause.with_traceback(error.cause.__traceback__) from None
        except TechnicalParserExecutionError:
            raise
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED") from None
        finally:
            self._capacity.release()

    @staticmethod
    def _execution_error(
        code: str,
        *,
        execution_state: Literal[
            "not_started", "failed", "execution_unknown", "containment_lost"
        ],
        operation: Literal["layout", "page"],
        invocation: str,
        expected_attestation_sha256: str,
        attestation: TechnicalParserRuntimeAttestation,
        container_id: str | None,
        started_at: datetime | None,
        cleanup_confirmed: bool,
    ) -> TechnicalParserExecutionError:
        if cleanup_confirmed != (execution_state != "containment_lost"):
            raise ValueError("Execution state contradicts cleanup proof")
        receipt = create_technical_parser_execution_receipt(
            execution_state=execution_state,
            operation=operation,
            invocation_id=invocation,
            expected_attestation_sha256=expected_attestation_sha256,
            attestation=attestation,
            outcome_code=code,
            container_id=container_id,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            exit_code=None,
            stdout_sha256=None,
            stdout_size_bytes=None,
            cleanup_confirmed=cleanup_confirmed,
        )
        return TechnicalParserExecutionError(code, receipt=receipt)

    def _verify_controller_files(self) -> None:
        try:
            runtime, _ = _verified_file(
                self._runtime_path,
                expected_sha256=self._runtime_executable_sha256,
                maximum_bytes=_RUNTIME_FILE_MAX_BYTES,
                path_code="PARSER_OCI_RUNTIME_PATH_INVALID",
                sha_code="PARSER_OCI_RUNTIME_SHA256_INVALID",
                retain_payload=False,
            )
            seccomp, raw = _verified_file(
                self._seccomp_profile_path,
                expected_sha256=self._seccomp_profile_sha256,
                maximum_bytes=_SECCOMP_FILE_MAX_BYTES,
                path_code="PARSER_OCI_SECCOMP_PROFILE_INVALID",
                sha_code="PARSER_OCI_SECCOMP_SHA256_INVALID",
            )
            _validate_seccomp_profile(raw)
        except TechnicalParserOciConfigurationError:
            raise TechnicalParserExecutionError("PARSER_EXECUTION_UNAVAILABLE") from None
        if runtime != self._runtime_path or seccomp != self._seccomp_profile_path:
            raise TechnicalParserExecutionError("PARSER_EXECUTION_UNAVAILABLE")

    @contextmanager
    def _materialized_controller_files(self) -> Iterator[tuple[Path, Path, Path]]:
        try:
            with tempfile.TemporaryDirectory(prefix="classifire-parser-runtime-") as temporary:
                directory = Path(temporary).resolve()
                if os.name != "nt":
                    directory.chmod(0o700)
                runtime_destination = directory / "runtime"
                _copy_verified_file(
                    self._runtime_path,
                    runtime_destination,
                    expected_sha256=self._runtime_executable_sha256,
                    maximum_bytes=_RUNTIME_FILE_MAX_BYTES,
                )
                if os.name != "nt":
                    runtime_destination.chmod(0o500)
                runtime_config = directory / "docker-config"
                runtime_config.mkdir()
                config_file = runtime_config / "config.json"
                with config_file.open("xb") as stream:
                    stream.write(b"{}")
                    stream.flush()
                    os.fsync(stream.fileno())
                if os.name != "nt":
                    config_file.chmod(0o400)
                    runtime_config.chmod(0o500)
                seccomp_destination = directory / "profile.json"
                with seccomp_destination.open("xb") as stream:
                    stream.write(self._seccomp_profile_bytes)
                    stream.flush()
                    os.fsync(stream.fileno())
                if os.name != "nt":
                    seccomp_destination.chmod(0o400)
                if (
                    hashlib.sha256(seccomp_destination.read_bytes()).hexdigest()
                    != self._seccomp_profile_sha256
                ):
                    raise OSError
                if config_file.read_bytes() != b"{}":
                    raise OSError
                yield runtime_destination, runtime_config, seccomp_destination
        except OSError:
            raise TechnicalParserExecutionError("PARSER_EXECUTION_UNAVAILABLE") from None

    def _command(
        self,
        *arguments: str,
    ) -> tuple[str, ...]:
        runtime_path = self._active_runtime_path
        runtime_config_path = self._active_runtime_config_path
        if runtime_path is None or runtime_config_path is None:
            raise TechnicalParserExecutionError("PARSER_EXECUTION_UNAVAILABLE")
        return (
            str(runtime_path),
            "--config",
            str(runtime_config_path),
            "--host",
            self._runtime_host,
            *arguments,
        )

    def _run_control(
        self,
        *arguments: str,
        stdout_limit: int = _CONTROL_OUTPUT_LIMIT,
        timeout_seconds: float | None = None,
    ) -> _BoundedCommandResult:
        try:
            return self._adapter.run(
                self._command(*arguments),
                stdin_writer=None,
                timeout_seconds=(
                    self._profile.control_timeout_seconds
                    if timeout_seconds is None
                    else timeout_seconds
                ),
                stdout_limit=stdout_limit,
                stderr_limit=0,
                environment=self._environment,
            )
        except _BoundedCommandError as error:
            if error.kind == "termination_failed":
                self._lose_containment()
            if error.kind in {"stderr_output", "stdout_overflow"}:
                raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED") from None
            raise TechnicalParserExecutionError("PARSER_EXECUTION_UNAVAILABLE") from None
        except TechnicalParserExecutionError:
            raise
        except Exception:
            raise TechnicalParserExecutionError("PARSER_EXECUTION_UNAVAILABLE") from None

    @staticmethod
    def _require_zero(result: _BoundedCommandResult) -> bytes:
        if result.returncode != 0 or result.stderr:
            raise TechnicalParserExecutionError("PARSER_EXECUTION_UNAVAILABLE")
        return result.stdout

    def _attest_runtime(
        self,
        *,
        extraction_policy: str,
        extraction_policy_sha256: str,
    ) -> tuple[TechnicalParserRuntimeAttestation, str, str]:
        daemon_identity_sha256 = self._live_daemon_identity_sha256()
        security_options = _json_string_list(
            self._require_zero(
                self._run_control(
                    "info",
                    "--format={{json .SecurityOptions}}",
                )
            )
        )
        if "name=rootless" not in {option.casefold() for option in security_options}:
            raise TechnicalParserExecutionError("PARSER_EXECUTION_UNAVAILABLE")

        operating_system = _json_string(
            self._require_zero(self._run_control("info", "--format={{json .OSType}}"))
        )
        architecture = _json_string(
            self._require_zero(self._run_control("info", "--format={{json .Architecture}}"))
        )
        expected_os, expected_arch = self._profile.platform.split("/", 1)
        if (
            operating_system != expected_os
            or _ARCHITECTURE_ALIASES.get(architecture) != expected_arch
        ):
            raise TechnicalParserExecutionError("PARSER_EXECUTION_UNAVAILABLE")

        repo_digests = _json_string_list(
            self._require_zero(
                self._run_control(
                    "image",
                    "inspect",
                    "--format={{json .RepoDigests}}",
                    self._image_reference,
                )
            )
        )
        digest_suffix = f"@sha256:{self._worker_image_digest}"
        if not any(item.endswith(digest_suffix) for item in repo_digests):
            raise TechnicalParserExecutionError("PARSER_EXECUTION_UNAVAILABLE")

        image_id = _json_string(
            self._require_zero(
                self._run_control(
                    "image",
                    "inspect",
                    "--format={{json .Id}}",
                    self._image_reference,
                )
            )
        )
        if re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None:
            raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")

        image_platform = _json_string(
            self._require_zero(
                self._run_control(
                    "image",
                    "inspect",
                    "--format={{json .Os}}",
                    self._image_reference,
                )
            )
        )
        image_architecture = _json_string(
            self._require_zero(
                self._run_control(
                    "image",
                    "inspect",
                    "--format={{json .Architecture}}",
                    self._image_reference,
                )
            )
        )
        if (
            image_platform != expected_os
            or _ARCHITECTURE_ALIASES.get(image_architecture) != expected_arch
        ):
            raise TechnicalParserExecutionError("PARSER_EXECUTION_UNAVAILABLE")

        image_config = _json_object(
            self._require_zero(
                self._run_control(
                    "image",
                    "inspect",
                    "--format={{json .Config}}",
                    self._image_reference,
                )
            )
        )
        labels = image_config.get("Labels")
        volumes = image_config.get("Volumes")
        if (
            not isinstance(labels, dict)
            or labels.get(TECHNICAL_PARSER_OCI_CONTRACT_LABEL)
            != TECHNICAL_PARSER_OCI_TRANSPORT_SCHEMA
            or labels.get(TECHNICAL_PARSER_OCI_POLICY_LABEL) != extraction_policy
            or labels.get(TECHNICAL_PARSER_OCI_POLICY_SHA256_LABEL) != extraction_policy_sha256
            or volumes not in (None, {})
        ):
            raise TechnicalParserExecutionError("PARSER_EXECUTION_UNAVAILABLE")
        if self._live_daemon_identity_sha256() != daemon_identity_sha256:
            raise TechnicalParserExecutionError("PARSER_EXECUTION_UNAVAILABLE")
        attestation = create_technical_parser_runtime_attestation(
            engine=TECHNICAL_PARSER_OCI_ENGINE,
            schema=TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2,
            claims={
                "controller_owner_id": self._controller_owner_id,
                "execution_fence_sha256": self._execution_fence_sha256,
                "extraction_policy": extraction_policy,
                "extraction_policy_sha256": extraction_policy_sha256,
                "image_id": image_id,
                "image_reference": self._image_reference,
                "oci_profile_schema": TECHNICAL_PARSER_OCI_PROFILE_SCHEMA,
                "oci_daemon_identity_sha256": daemon_identity_sha256,
                "platform": self._profile.platform,
                "runtime_executable_sha256": self._runtime_executable_sha256,
                "runtime_host": self._runtime_host,
                "runtime_profile_sha256": self._runtime_profile_sha256,
                "seccomp_profile_sha256": self._seccomp_profile_sha256,
                "transport_schema": TECHNICAL_PARSER_OCI_TRANSPORT_SCHEMA,
                "worker_image_digest": self._worker_image_digest,
            },
        )
        return attestation, image_id, daemon_identity_sha256

    def _live_daemon_identity_sha256(self) -> str:
        daemon_id = _json_string(
            self._require_zero(self._run_control("info", "--format={{json .ID}}"))
        )
        return _daemon_identity_sha256(daemon_id)

    def _require_daemon_identity_or_lose(self, expected_sha256: str) -> None:
        try:
            current_sha256 = self._live_daemon_identity_sha256()
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException:
            self._lose_containment()
        if current_sha256 != expected_sha256:
            self._lose_containment()

    def _create_arguments(
        self,
        *,
        operation: Literal["layout", "page"],
        invocation: str,
        seccomp_runtime_path: Path,
    ) -> tuple[str, ...]:
        container_name = f"classifire-parser-{invocation}"
        tmpfs = (
            f"rw,noexec,nosuid,nodev,size={self._profile.tmpfs_bytes},uid=65532,gid=65532,mode=0700"
        )
        return (
            "container",
            "create",
            "--name",
            container_name,
            "--label",
            f"{TECHNICAL_PARSER_OCI_INVOCATION_LABEL}={invocation}",
            "--label",
            f"{TECHNICAL_PARSER_OCI_OWNER_LABEL}={self._controller_owner_id}",
            "--pull=never",
            "--platform",
            self._profile.platform,
            "--interactive",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            f"--security-opt=seccomp={seccomp_runtime_path}",
            "--user=65532:65532",
            "--pid=private",
            "--ipc=none",
            "--uts=private",
            "--cgroupns=private",
            f"--pids-limit={self._profile.pids_limit}",
            f"--memory={self._profile.memory_bytes}",
            f"--memory-swap={self._profile.memory_swap_bytes}",
            "--cpus=1.0",
            f"--ulimit=nofile={self._profile.nofile_limit}:{self._profile.nofile_limit}",
            "--ulimit=core=0:0",
            f"--tmpfs=/work:{tmpfs}",
            "--workdir=/work",
            "--restart=no",
            "--stop-timeout=1",
            "--log-driver=none",
            f"--entrypoint={TECHNICAL_PARSER_OCI_ENTRYPOINT}",
            self._image_reference,
            operation,
        )

    def _create_container(
        self,
        *,
        operation: Literal["layout", "page"],
        invocation: str,
        label: str,
        expected_image_id: str,
        expected_daemon_identity_sha256: str,
        seccomp_runtime_path: Path,
    ) -> str:
        try:
            result = self._run_control(
                *self._create_arguments(
                    operation=operation,
                    invocation=invocation,
                    seccomp_runtime_path=seccomp_runtime_path,
                ),
                stdout_limit=256,
            )
        except (KeyboardInterrupt, SystemExit):
            # The coordinator's durable reservation remains pending for startup
            # reconciliation; never synthesize a terminal receipt on interruption.
            raise
        except BaseException:
            ids = self._ids_for_label_or_lose(label)
            cleaned_id = self._cleanup_unique_created_candidate_or_lose(
                ids,
                label=label,
                operation=operation,
                expected_image_id=expected_image_id,
                expected_daemon_identity_sha256=(
                    expected_daemon_identity_sha256
                ),
                seccomp_runtime_path=seccomp_runtime_path,
            )
            self._lose_containment(
                container_id=cleaned_id,
            )
        if result.returncode != 0:
            ids = self._ids_for_label_or_lose(label)
            self._cleanup_unique_created_candidate_or_lose(
                ids,
                label=label,
                operation=operation,
                expected_image_id=expected_image_id,
                expected_daemon_identity_sha256=(
                    expected_daemon_identity_sha256
                ),
                seccomp_runtime_path=seccomp_runtime_path,
            )
            raise TechnicalParserExecutionError("PARSER_EXECUTION_UNAVAILABLE")

        try:
            container_id = self._single_container_id(result.stdout)
            labelled_ids = self._ids_for_label_or_lose(label)
        except BaseException as error:
            candidates = self._ids_for_label_or_lose(label)
            self._cleanup_unique_created_candidate_or_lose(
                candidates,
                label=label,
                operation=operation,
                expected_image_id=expected_image_id,
                expected_daemon_identity_sha256=(
                    expected_daemon_identity_sha256
                ),
                seccomp_runtime_path=seccomp_runtime_path,
            )
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            if isinstance(error, TechnicalParserExecutionError):
                raise
            raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED") from None
        if labelled_ids != (container_id,):
            try:
                self._validate_created_container(
                    container_id=container_id,
                    label=label,
                    operation=operation,
                    expected_image_id=expected_image_id,
                    seccomp_runtime_path=seccomp_runtime_path,
                )
            except (KeyboardInterrupt, SystemExit):
                raise
            except BaseException:
                self._lose_containment()
            if not self._remove_and_confirm(
                (container_id,),
                label=label,
                expected_daemon_identity_sha256=expected_daemon_identity_sha256,
            ):
                self._lose_containment(container_id=container_id)
            self._lose_containment(container_id=container_id)
        try:
            self._validate_created_container(
                container_id=container_id,
                label=label,
                operation=operation,
                expected_image_id=expected_image_id,
                seccomp_runtime_path=seccomp_runtime_path,
            )
        except BaseException as error:
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            self._lose_containment()
        return container_id

    def _cleanup_unique_created_candidate_or_lose(
        self,
        container_ids: Sequence[str],
        *,
        label: str,
        operation: Literal["layout", "page"],
        expected_image_id: str,
        expected_daemon_identity_sha256: str,
        seccomp_runtime_path: Path,
    ) -> str | None:
        if not container_ids:
            return None
        if len(container_ids) != 1:
            self._lose_containment()
        container_id = container_ids[0]
        try:
            self._validate_created_container(
                container_id=container_id,
                label=label,
                operation=operation,
                expected_image_id=expected_image_id,
                seccomp_runtime_path=seccomp_runtime_path,
            )
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException:
            self._lose_containment()
        if not self._remove_and_confirm(
            (container_id,),
            label=label,
            expected_daemon_identity_sha256=expected_daemon_identity_sha256,
        ):
            self._lose_containment(container_id=container_id)
        return container_id

    @staticmethod
    def _single_container_id(raw: bytes) -> str:
        line = raw.rstrip(b"\r\n")
        if raw not in {line + b"\n", line + b"\r\n"} or _CONTAINER_ID.fullmatch(line) is None:
            raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
        return line.decode("ascii")

    @staticmethod
    def _container_ids_from_output(raw: bytes) -> tuple[str, ...]:
        if raw == b"":
            return ()
        if not raw.endswith(b"\n"):
            raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
        lines = raw.splitlines()
        if (
            len(lines) > 16
            or any(_CONTAINER_ID.fullmatch(line) is None for line in lines)
            or len(set(lines)) != len(lines)
        ):
            raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
        return tuple(line.decode("ascii") for line in lines)

    def _container_ids(
        self,
        filter_values: str | Sequence[str],
        *,
        cleanup: bool = False,
    ) -> tuple[str, ...]:
        filters = (
            (filter_values,)
            if isinstance(filter_values, str)
            else tuple(filter_values)
        )
        if not filters or any(
            not isinstance(value, str) or not value for value in filters
        ):
            raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
        arguments: list[str] = [
            "container",
            "ls",
            "--all",
            "--quiet",
            "--no-trunc",
        ]
        for filter_value in filters:
            arguments.extend(("--filter", filter_value))
        result = self._run_control(
            *arguments,
            stdout_limit=2048,
            timeout_seconds=(self._profile.cleanup_timeout_seconds if cleanup else None),
        )
        if result.returncode != 0:
            raise TechnicalParserExecutionError("PARSER_EXECUTION_UNAVAILABLE")
        return self._container_ids_from_output(result.stdout)

    def _ids_for_label_or_lose(self, label: str) -> tuple[str, ...]:
        try:
            return self._container_ids(f"label={label}", cleanup=True)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException:
            self._lose_containment()

    def _ids_for_preexisting_execution_or_lose(
        self,
        invocation_label: str,
    ) -> tuple[str, ...]:
        owner_label = (
            f"{TECHNICAL_PARSER_OCI_OWNER_LABEL}={self._controller_owner_id}"
        )
        try:
            invocation_ids = self._container_ids(
                f"label={invocation_label}", cleanup=True
            )
            owner_ids = self._container_ids(f"label={owner_label}", cleanup=True)
            return tuple(sorted(set(invocation_ids) | set(owner_ids)))
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException:
            self._lose_containment()

    def _remove_and_confirm(
        self,
        container_ids: Sequence[str],
        *,
        label: str,
        expected_daemon_identity_sha256: str,
        permit_quarantined: bool = False,
    ) -> bool:
        try:
            self._require_daemon_identity_or_lose(
                expected_daemon_identity_sha256
            )
            unique_ids = tuple(sorted(set(container_ids)))
            for container_id in unique_ids:
                if re.fullmatch(r"[0-9a-f]{64}", container_id) is None:
                    return False
                self._run_control(
                    "container",
                    "rm",
                    "--force",
                    "--volumes",
                    container_id,
                    stdout_limit=256,
                    timeout_seconds=self._profile.cleanup_timeout_seconds,
                )
                if self._containment_lost.is_set() and not permit_quarantined:
                    return False
            if self._container_ids(f"label={label}", cleanup=True):
                return False
            ids_absent = all(
                not self._container_ids(f"id={container_id}", cleanup=True)
                for container_id in unique_ids
            )
            self._require_daemon_identity_or_lose(
                expected_daemon_identity_sha256
            )
            return ids_absent
        except BaseException:
            return False

    def _inspect_container_value(self, container_id: str, field: str) -> object:
        result = self._run_control(
            "container",
            "inspect",
            f"--format={{{{json {field}}}}}",
            container_id,
        )
        if result.returncode != 0:
            raise TechnicalParserExecutionError("PARSER_EXECUTION_UNAVAILABLE")
        return _strict_json(result.stdout)

    def _validate_container_profile(
        self,
        *,
        container_id: str,
        label: str,
        operation: Literal["layout", "page"],
        expected_image_id: str,
        seccomp_runtime_path: Path,
    ) -> dict[str, object]:
        inspected_id = self._inspect_container_value(container_id, ".Id")
        image_id = self._inspect_container_value(container_id, ".Image")
        config = self._inspect_container_value(container_id, ".Config")
        host = self._inspect_container_value(container_id, ".HostConfig")
        state = self._inspect_container_value(container_id, ".State")
        if (
            inspected_id != container_id
            or image_id != expected_image_id
            or not isinstance(config, dict)
            or not isinstance(host, dict)
            or not isinstance(state, dict)
        ):
            raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")

        label_key, label_value = label.split("=", 1)
        labels = config.get("Labels")
        if (
            config.get("Image") != self._image_reference
            or config.get("User") != "65532:65532"
            or config.get("WorkingDir") != "/work"
            or config.get("Entrypoint") != [TECHNICAL_PARSER_OCI_ENTRYPOINT]
            or config.get("Cmd") != [operation]
            or config.get("OpenStdin") is not True
            or config.get("Tty") is not False
            or not isinstance(labels, dict)
            or labels.get(label_key) != label_value
            or labels.get(TECHNICAL_PARSER_OCI_OWNER_LABEL)
            != self._controller_owner_id
            or config.get("Volumes") not in (None, {})
        ):
            raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")

        restart_policy = host.get("RestartPolicy")
        log_config = host.get("LogConfig")
        security_options = host.get("SecurityOpt")
        cap_drop = host.get("CapDrop")
        tmpfs = host.get("Tmpfs")
        ulimits = host.get("Ulimits")
        expected_tmpfs = {
            "rw",
            "noexec",
            "nosuid",
            "nodev",
            f"size={self._profile.tmpfs_bytes}",
            "uid=65532",
            "gid=65532",
            "mode=0700",
        }
        actual_tmpfs = (
            set(cast(str, tmpfs.get("/work")).split(","))
            if isinstance(tmpfs, dict) and isinstance(tmpfs.get("/work"), str)
            else set()
        )
        security_profile_matches = False
        if isinstance(security_options, list) and all(
            isinstance(option, str) for option in security_options
        ):
            no_new_privileges = [
                option for option in security_options if option == "no-new-privileges:true"
            ]
            seccomp_values = [
                option.removeprefix("seccomp=")
                for option in security_options
                if option.startswith("seccomp=")
            ]
            if len(no_new_privileges) == 1 and len(seccomp_values) == 1:
                try:
                    security_profile_matches = (
                        _strict_json(seccomp_values[0].encode("utf-8"))
                        == self._seccomp_profile_value
                    )
                except TechnicalParserExecutionError:
                    security_profile_matches = False
        cap_drop_matches = (
            isinstance(cap_drop, list)
            and all(isinstance(capability, str) for capability in cap_drop)
            and set(cap_drop) == {"ALL"}
        )
        ulimit_entries: set[tuple[str, int, int]] = set()
        if isinstance(ulimits, list) and len(ulimits) == 2:
            ulimits_match = True
            for entry in ulimits:
                if (
                    not isinstance(entry, dict)
                    or set(entry) != {"Hard", "Name", "Soft"}
                    or not isinstance(entry.get("Name"), str)
                    or not isinstance(entry.get("Soft"), int)
                    or isinstance(entry.get("Soft"), bool)
                    or not isinstance(entry.get("Hard"), int)
                    or isinstance(entry.get("Hard"), bool)
                ):
                    ulimits_match = False
                    break
                ulimit_entries.add(
                    (
                        cast(str, entry["Name"]),
                        cast(int, entry["Soft"]),
                        cast(int, entry["Hard"]),
                    )
                )
            ulimits_match = ulimits_match and ulimit_entries == {
                ("core", 0, 0),
                ("nofile", self._profile.nofile_limit, self._profile.nofile_limit),
            }
        else:
            ulimits_match = False
        if (
            host.get("NetworkMode") != "none"
            or host.get("ReadonlyRootfs") is not True
            or host.get("Privileged") is not False
            or host.get("CapAdd") not in (None, [])
            or not cap_drop_matches
            or not security_profile_matches
            or host.get("PidMode") != "private"
            or host.get("IpcMode") != "none"
            or host.get("UTSMode") != "private"
            or host.get("CgroupnsMode") != "private"
            or host.get("PidsLimit") != self._profile.pids_limit
            or host.get("Memory") != self._profile.memory_bytes
            or host.get("MemorySwap") != self._profile.memory_swap_bytes
            or host.get("NanoCpus") != self._profile.nano_cpus
            or not ulimits_match
            or host.get("Binds") not in (None, [])
            or host.get("Mounts") not in (None, [])
            or host.get("Devices") not in (None, [])
            or host.get("DeviceRequests") not in (None, [])
            or host.get("AutoRemove") is not False
            or not isinstance(restart_policy, dict)
            or restart_policy.get("Name") != "no"
            or not isinstance(log_config, dict)
            or log_config.get("Type") != "none"
            or actual_tmpfs != expected_tmpfs
        ):
            raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
        return cast(dict[str, object], state)

    def _validate_created_container(
        self,
        *,
        container_id: str,
        label: str,
        operation: Literal["layout", "page"],
        expected_image_id: str,
        seccomp_runtime_path: Path,
    ) -> None:
        state = self._validate_container_profile(
            container_id=container_id,
            label=label,
            operation=operation,
            expected_image_id=expected_image_id,
            seccomp_runtime_path=seccomp_runtime_path,
        )
        if state.get("Status") != "created" or state.get("Running") is not False:
            raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")

    @staticmethod
    def _write_all(stream: BinaryIO, payload: bytes) -> None:
        view = memoryview(payload)
        offset = 0
        while offset < len(view):
            written = stream.write(view[offset:])
            if (
                not isinstance(written, int)
                or isinstance(written, bool)
                or written <= 0
                or written > len(view) - offset
            ):
                raise OSError
            offset += written

    def _source_writer(
        self,
        *,
        request: bytes,
        parsed: TechnicalParserLayoutRequest | TechnicalParserRequest,
        source: BinaryIO,
    ) -> _CommandInputWriter:
        def write(stream: BinaryIO) -> None:
            if not isinstance(request, bytes) or not 1 <= len(request) <= 4096:
                raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
            self._write_all(stream, len(request).to_bytes(4, "big"))
            self._write_all(stream, request)
            digest = hashlib.sha256()
            size = 0
            while True:
                try:
                    chunk = source.read(_STREAM_CHUNK_BYTES)
                except Exception:
                    raise TechnicalParserExecutionError("PARSER_EXECUTION_SOURCE_INVALID") from None
                if not isinstance(chunk, bytes) or len(chunk) > _STREAM_CHUNK_BYTES:
                    raise TechnicalParserExecutionError("PARSER_EXECUTION_SOURCE_INVALID")
                if not chunk:
                    break
                size += len(chunk)
                if size > parsed.source_size_bytes:
                    raise TechnicalParserExecutionError("PARSER_EXECUTION_SOURCE_INVALID")
                digest.update(chunk)
                self._write_all(stream, chunk)
            if size != parsed.source_size_bytes or digest.hexdigest() != parsed.source_sha256:
                raise TechnicalParserExecutionError("PARSER_EXECUTION_SOURCE_INVALID")

        return write

    def _map_parser_command_error(
        self,
        error: _BoundedCommandError,
    ) -> TechnicalParserExecutionError:
        if error.kind == "termination_failed":
            self._containment_lost.set()
            return TechnicalParserExecutionError("PARSER_EXECUTION_CONTAINMENT_LOST")
        if error.kind == "timeout":
            return TechnicalParserExecutionError("PARSER_EXECUTION_TIMEOUT")
        if error.kind == "stdout_overflow":
            return TechnicalParserExecutionError("PARSER_EXECUTION_OUTPUT_OVERFLOW")
        return TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")

    def _start_container(
        self,
        *,
        container_id: str,
        label: str,
        operation: Literal["layout", "page"],
        expected_daemon_identity_sha256: str,
        request: bytes,
        parsed: TechnicalParserLayoutRequest | TechnicalParserRequest,
        source: BinaryIO,
    ) -> bytes:
        cleanup_lock = threading.Lock()

        def terminate_container() -> None:
            with cleanup_lock:
                if not self._remove_and_confirm(
                    (container_id,),
                    label=label,
                    expected_daemon_identity_sha256=(
                        expected_daemon_identity_sha256
                    ),
                ):
                    self._containment_lost.set()
                    raise RuntimeError("containment lost")

        timeout = (
            self._profile.layout_timeout_seconds
            if operation == "layout"
            else self._profile.page_timeout_seconds
        )
        output_limit = _LAYOUT_OUTPUT_LIMIT if operation == "layout" else _PAGE_OUTPUT_LIMIT
        result: _BoundedCommandResult | None = None
        pending_error: BaseException | None = None
        try:
            result = self._adapter.run(
                self._command(
                    "container",
                    "start",
                    "--attach",
                    "--interactive",
                    container_id,
                ),
                stdin_writer=self._source_writer(
                    request=request,
                    parsed=parsed,
                    source=source,
                ),
                timeout_seconds=timeout,
                stdout_limit=output_limit,
                stderr_limit=0,
                environment=self._environment,
                on_terminate=terminate_container,
            )
            if result.returncode != 0 or result.stderr:
                pending_error = TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
            else:
                state = self._inspect_container_value(container_id, ".State")
                if (
                    not isinstance(state, dict)
                    or state.get("Status") != "exited"
                    or state.get("Running") is not False
                    or state.get("Dead") is not False
                    or state.get("OOMKilled") is not False
                    or state.get("ExitCode") != 0
                    or state.get("Error") not in ("", None)
                ):
                    pending_error = TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
        except _BoundedCommandError as error:
            pending_error = self._map_parser_command_error(error)
        except TechnicalParserExecutionError as error:
            pending_error = error
        except BaseException as error:
            pending_error = error

        with cleanup_lock:
            cleanup_confirmed = self._remove_and_confirm(
                (container_id,),
                label=label,
                expected_daemon_identity_sha256=expected_daemon_identity_sha256,
            )
        if not cleanup_confirmed:
            self._lose_containment(container_id=container_id)
        if pending_error is not None:
            raise pending_error
        if result is None:
            raise TechnicalParserExecutionError("PARSER_EXECUTION_FAILED")
        return result.stdout

    def _lose_containment(self, *, container_id: str | None = None) -> Never:
        self._containment_lost.set()
        raise _OciContainmentLost(container_id)


__all__ = [
    "TECHNICAL_PARSER_OCI_CLEANUP_PROOF_SCHEMA",
    "TECHNICAL_PARSER_OCI_CONTRACT_LABEL",
    "TECHNICAL_PARSER_OCI_ENGINE",
    "TECHNICAL_PARSER_OCI_ENTRYPOINT",
    "TECHNICAL_PARSER_OCI_INVOCATION_LABEL",
    "TECHNICAL_PARSER_OCI_OWNER_LABEL",
    "TECHNICAL_PARSER_OCI_POLICY_LABEL",
    "TECHNICAL_PARSER_OCI_POLICY_SHA256_LABEL",
    "TECHNICAL_PARSER_OCI_PROFILE_SCHEMA",
    "TECHNICAL_PARSER_OCI_TRANSPORT_SCHEMA",
    "DigestPinnedOciTechnicalParserRunner",
    "PosixFlockTechnicalParserExecutionFence",
    "TechnicalParserExecutionFence",
    "TechnicalParserOciCleanupProof",
    "TechnicalParserOciConfigurationError",
    "TechnicalParserOciRuntimeProfile",
    "TechnicalParserRuntimeAttestation",
]
