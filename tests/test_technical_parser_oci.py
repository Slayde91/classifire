from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pytest

import classifire.services.technical_parser_oci as technical_parser_oci
from classifire.services.technical_parser_execution import (
    TECHNICAL_PARSER_EXECUTION_OUTCOME_UNKNOWN,
    TECHNICAL_PARSER_INVOCATION_RECEIPT_SCHEMA,
    TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA,
    TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2,
    TechnicalParserExecutionError,
    TechnicalParserExecutionReceipt,
    TechnicalParserExecutionSuccess,
    TechnicalParserRuntimeAttestation,
    create_technical_parser_execution_receipt,
    create_technical_parser_runtime_attestation,
    parse_technical_parser_execution_receipt,
    parse_technical_parser_runtime_attestation,
)
from classifire.services.technical_parser_oci import (
    TECHNICAL_PARSER_OCI_CLEANUP_PROOF_SCHEMA,
    TECHNICAL_PARSER_OCI_CONTRACT_LABEL,
    TECHNICAL_PARSER_OCI_ENGINE,
    TECHNICAL_PARSER_OCI_ENTRYPOINT,
    TECHNICAL_PARSER_OCI_INVOCATION_LABEL,
    TECHNICAL_PARSER_OCI_OWNER_LABEL,
    TECHNICAL_PARSER_OCI_POLICY_LABEL,
    TECHNICAL_PARSER_OCI_POLICY_SHA256_LABEL,
    TECHNICAL_PARSER_OCI_PROFILE_SCHEMA,
    TECHNICAL_PARSER_OCI_TRANSPORT_SCHEMA,
    DigestPinnedOciTechnicalParserRunner,
    PosixFlockTechnicalParserExecutionFence,
    TechnicalParserOciCleanupProof,
    TechnicalParserOciConfigurationError,
    TechnicalParserOciRuntimeProfile,
    _BoundedCommandError,
    _BoundedCommandResult,
    _SubprocessOciRuntimeAdapter,
)
from classifire.services.technical_parser_protocol import (
    TECHNICAL_PARSER_EVIDENCE_MAX_BYTES,
    TECHNICAL_PARSER_HEADER_MAX_BYTES,
    TECHNICAL_PARSER_LAYOUT_MAX_BYTES,
    TECHNICAL_PARSER_LAYOUT_SCHEMA,
    TECHNICAL_PARSER_PAGE_FRAME_SCHEMA,
    TECHNICAL_PARSER_PNG_MAX_BYTES,
    TechnicalParserDocumentLayout,
    encode_technical_parser_layout_request,
    encode_technical_parser_request,
    parse_technical_parser_layout_result,
    parse_technical_parser_page_frame,
)

_DOCUMENT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
_SOURCE = b"%PDF-1.7\ncontrolled technical source\n%%EOF\n"
_SOURCE_SHA256 = hashlib.sha256(_SOURCE).hexdigest()
_POLICY = "technical-extraction-v1"
_POLICY_SHA256 = "b" * 64
_WORKER_DIGEST = "c" * 64
_OTHER_DIGEST = "d" * 64
_IMAGE_REFERENCE = f"registry.example/classifire/parser@sha256:{_WORKER_DIGEST}"
_IMAGE_ID = f"sha256:{'e' * 64}"
_CONTAINER_ID = "f" * 64
_RUNTIME_HOST = "unix:///run/user/1000/docker.sock"
_DAEMON_ID = "ABCDEFGHIJKLMNOPQRSTUVWX23456789"
_DAEMON_IDENTITY_SHA256 = hashlib.sha256(
    b"classifire-technical-parser-oci-daemon-v1\x00" + _DAEMON_ID.encode("ascii")
).hexdigest()
_CONTROLLER_OWNER_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
_EXECUTION_FENCE_SHA256 = "1" * 64
_RUNTIME_PAYLOAD = b"deterministic fake OCI runtime"
_INVOCATION_IDS = (
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
    "33333333-3333-4333-8333-333333333333",
)
_EVIDENCE = b'{"untrusted":"packet"}'
_IMAGE = b"transport-valid-image-bytes"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _seccomp_bytes(*, allowed_names: Sequence[str] = ("read", "write")) -> bytes:
    return _canonical(
        {
            "defaultAction": "SCMP_ACT_ERRNO",
            "syscalls": [
                {
                    "action": "SCMP_ACT_ALLOW",
                    "names": list(allowed_names),
                }
            ],
        }
    )


def _layout_output() -> bytes:
    return _canonical(
        {
            "extraction_policy": _POLICY,
            "extraction_policy_sha256": _POLICY_SHA256,
            "page_count": 1,
            "pages": [
                {
                    "count": 1,
                    "height_points": 792,
                    "number": 1,
                    "width_points": 612,
                }
            ],
            "schema": TECHNICAL_PARSER_LAYOUT_SCHEMA,
            "source_sha256": _SOURCE_SHA256,
            "source_size_bytes": len(_SOURCE),
            "technical_document_id": _DOCUMENT_ID,
            "worker_image_digest": _WORKER_DIGEST,
        }
    )


def _page_output() -> bytes:
    header = _canonical(
        {
            "evidence_sha256": hashlib.sha256(_EVIDENCE).hexdigest(),
            "evidence_size_bytes": len(_EVIDENCE),
            "image_height_pixels": 1200,
            "image_sha256": hashlib.sha256(_IMAGE).hexdigest(),
            "image_size_bytes": len(_IMAGE),
            "image_width_pixels": 1000,
            "page_count": 1,
            "page_height_points": 792,
            "page_number": 1,
            "page_width_points": 612,
            "schema": TECHNICAL_PARSER_PAGE_FRAME_SCHEMA,
            "status": "ok",
        }
    )
    return len(header).to_bytes(4, "big") + header + _EVIDENCE + _IMAGE


def _layout_request(*, worker_digest: str = _WORKER_DIGEST) -> bytes:
    return encode_technical_parser_layout_request(
        technical_document_id=_DOCUMENT_ID,
        source_sha256=_SOURCE_SHA256,
        source_size_bytes=len(_SOURCE),
        extraction_policy=_POLICY,
        extraction_policy_sha256=_POLICY_SHA256,
        worker_image_digest=worker_digest,
        ocr_low_confidence_threshold=Decimal("72.25"),
    )


def _page_request(*, worker_digest: str = _WORKER_DIGEST) -> bytes:
    return encode_technical_parser_request(
        technical_document_id=_DOCUMENT_ID,
        source_sha256=_SOURCE_SHA256,
        source_size_bytes=len(_SOURCE),
        page_number=1,
        page_count=1,
        page_width_points=Decimal(612),
        page_height_points=Decimal(792),
        layout_sha256="a" * 64,
        extraction_policy=_POLICY,
        extraction_policy_sha256=_POLICY_SHA256,
        worker_image_digest=worker_digest,
        ocr_low_confidence_threshold=Decimal("72.25"),
    )


class _NamedSource(BytesIO):
    def __init__(self, payload: bytes, *, name: str) -> None:
        super().__init__(payload)
        self.name = name


class _UnreadableSource(BytesIO):
    def read(self, size: int | None = -1) -> bytes:
        del size
        raise OSError("path-bearing detail must not escape")


@dataclass(slots=True)
class _RecordedCall:
    args: tuple[str, ...]
    timeout_seconds: float
    stdout_limit: int
    stderr_limit: int
    environment: dict[str, str]
    has_termination_callback: bool
    stdin_payload: bytes | None = None


@dataclass(frozen=True, slots=True)
class _SeccompSnapshot:
    path: Path
    sha256: str
    existed_during_create: bool


@dataclass(frozen=True, slots=True)
class _RuntimeSnapshot:
    path: Path
    sha256: str
    existed_during_call: bool


@dataclass(frozen=True, slots=True)
class _RuntimeConfigSnapshot:
    path: Path
    entries: tuple[str, ...]
    config_bytes: bytes
    existed_during_call: bool


class FakeExecutionFence:
    def __init__(self, *, identity_sha256: str = _EXECUTION_FENCE_SHA256) -> None:
        self.identity_sha256 = identity_sha256
        self.held = False
        self.wait_modes: list[bool] = []

    @contextmanager
    def hold(self, *, wait: bool) -> Iterator[None]:
        self.wait_modes.append(wait)
        if self.held:
            raise TechnicalParserExecutionError("PARSER_EXECUTION_UNAVAILABLE")
        self.held = True
        try:
            yield
        finally:
            self.held = False


class FakeOciRuntimeAdapter:
    """Stateful, in-process model of only the OCI commands the runner may issue."""

    def __init__(self) -> None:
        self.calls: list[_RecordedCall] = []
        self.containers: dict[str, dict[str, object]] = {}
        self.seccomp_snapshots: list[_SeccompSnapshot] = []
        self.runtime_snapshots: list[_RuntimeSnapshot] = []
        self.runtime_config_snapshots: list[_RuntimeConfigSnapshot] = []
        self.repo_digests = [_IMAGE_REFERENCE]
        self.image_id = _IMAGE_ID
        self.image_os = "linux"
        self.image_architecture = "amd64"
        self.image_contract = TECHNICAL_PARSER_OCI_TRANSPORT_SCHEMA
        self.image_policy = _POLICY
        self.image_policy_sha256 = _POLICY_SHA256
        self.security_options: list[str] = ["name=rootless"]
        self.daemon_id = _DAEMON_ID
        self.daemon_id_responses: list[str] = []
        self.container_image_id = _IMAGE_ID
        self.container_label_overrides: dict[str, str] = {}
        self.container_inspect_interrupt: BaseException | None = None
        self.host_patch: dict[str, object] = {}
        self.create_behavior = "ok"
        self.start_error: str | None = None
        self.start_returncode = 0
        self.start_stderr = b""
        self.cleanup_stuck = False
        self.after_container_create: Callable[[], None] | None = None
        self.after_container_remove: Callable[[], None] | None = None

    @staticmethod
    def _json(value: object) -> _BoundedCommandResult:
        return _BoundedCommandResult(returncode=0, stdout=_canonical(value), stderr=b"")

    @staticmethod
    def _option(command: Sequence[str], prefix: str) -> str:
        return next(item.removeprefix(prefix) for item in command if item.startswith(prefix))

    def _register_container(self, command: tuple[str, ...]) -> None:
        label_values = [
            command[index + 1]
            for index, item in enumerate(command)
            if item == "--label"
        ]
        labels = dict(value.split("=", 1) for value in label_values)
        labels.update(self.container_label_overrides)
        seccomp_path = Path(self._option(command, "--security-opt=seccomp="))
        seccomp_payload = seccomp_path.read_bytes()
        tmpfs_value = self._option(command, "--tmpfs=/work:")
        self.seccomp_snapshots.append(
            _SeccompSnapshot(
                path=seccomp_path,
                sha256=hashlib.sha256(seccomp_payload).hexdigest(),
                existed_during_create=seccomp_path.is_file(),
            )
        )
        operation = command[-1]
        config: dict[str, object] = {
            "Cmd": [operation],
            "Entrypoint": [TECHNICAL_PARSER_OCI_ENTRYPOINT],
            "Image": command[-2],
            "Labels": labels,
            "OpenStdin": True,
            "Tty": False,
            "User": "65532:65532",
            "Volumes": None,
            "WorkingDir": "/work",
        }
        host: dict[str, object] = {
            "AutoRemove": False,
            "Binds": None,
            "CapAdd": None,
            "CapDrop": ["ALL"],
            "CgroupnsMode": "private",
            "DeviceRequests": None,
            "Devices": None,
            "IpcMode": "none",
            "LogConfig": {"Type": "none"},
            "Memory": int(self._option(command, "--memory=")),
            "MemorySwap": int(self._option(command, "--memory-swap=")),
            "Mounts": None,
            "NanoCpus": 1_000_000_000,
            "NetworkMode": "none",
            "PidMode": "private",
            "PidsLimit": int(self._option(command, "--pids-limit=")),
            "Privileged": False,
            "ReadonlyRootfs": True,
            "RestartPolicy": {"Name": "no"},
            "SecurityOpt": [
                "no-new-privileges:true",
                f"seccomp={seccomp_payload.decode('utf-8')}",
            ],
            "Tmpfs": {"/work": tmpfs_value},
            "Ulimits": [
                {"Hard": 64, "Name": "nofile", "Soft": 64},
                {"Hard": 0, "Name": "core", "Soft": 0},
            ],
            "UTSMode": "private",
        }
        host.update(self.host_patch)
        self.containers[_CONTAINER_ID] = {
            "Config": config,
            "HostConfig": host,
            "Id": _CONTAINER_ID,
            "Image": self.container_image_id,
            "State": {"Running": False, "Status": "created"},
            "labels": labels,
            "operation": operation,
        }

    def _list_containers(self, filter_values: Sequence[str]) -> _BoundedCommandResult:
        ids = list(self.containers)
        for filter_value in filter_values:
            if filter_value.startswith("label="):
                label = filter_value.removeprefix("label=")
                key, expected = label.split("=", 1)
                filtered_ids: list[str] = []
                for container_id in ids:
                    labels = self.containers[container_id]["labels"]
                    assert isinstance(labels, dict)
                    if labels.get(key) == expected:
                        filtered_ids.append(container_id)
                ids = filtered_ids
            elif filter_value.startswith("id="):
                expected_id = filter_value.removeprefix("id=")
                ids = [container_id for container_id in ids if container_id == expected_id]
            else:
                raise AssertionError(f"unexpected OCI filter: {filter_value}")
        stdout = b"".join(f"{container_id}\n".encode("ascii") for container_id in ids)
        return _BoundedCommandResult(returncode=0, stdout=stdout, stderr=b"")

    @staticmethod
    def _field(format_argument: str) -> str:
        prefix = "--format={{json "
        suffix = "}}"
        assert format_argument.startswith(prefix) and format_argument.endswith(suffix)
        return format_argument[len(prefix) : -len(suffix)].removeprefix(".")

    def _terminate(self, callback: Callable[[], None] | None) -> None:
        if callback is None:
            return
        try:
            callback()
        except Exception:
            raise _BoundedCommandError("termination_failed") from None

    def run(
        self,
        args: Sequence[str],
        *,
        stdin_writer: Callable[[BinaryIO], None] | None,
        timeout_seconds: float,
        stdout_limit: int,
        stderr_limit: int,
        environment: Mapping[str, str],
        on_terminate: Callable[[], None] | None = None,
    ) -> _BoundedCommandResult:
        arguments = tuple(args)
        assert arguments[1] == "--config"
        runtime_config_path = Path(arguments[2])
        assert arguments[3:5] == ("--host", _RUNTIME_HOST)
        runtime_path = Path(arguments[0])
        self.runtime_snapshots.append(
            _RuntimeSnapshot(
                path=runtime_path,
                sha256=hashlib.sha256(runtime_path.read_bytes()).hexdigest(),
                existed_during_call=runtime_path.is_file(),
            )
        )
        self.runtime_config_snapshots.append(
            _RuntimeConfigSnapshot(
                path=runtime_config_path,
                entries=tuple(sorted(item.name for item in runtime_config_path.iterdir())),
                config_bytes=(runtime_config_path / "config.json").read_bytes(),
                existed_during_call=runtime_config_path.is_dir(),
            )
        )
        command = arguments[5:]
        call = _RecordedCall(
            args=arguments,
            timeout_seconds=timeout_seconds,
            stdout_limit=stdout_limit,
            stderr_limit=stderr_limit,
            environment=dict(environment),
            has_termination_callback=on_terminate is not None,
        )
        self.calls.append(call)

        if stdin_writer is not None:
            sink = BytesIO()
            try:
                stdin_writer(sink)
            except BaseException:
                call.stdin_payload = sink.getvalue()
                self._terminate(on_terminate)
                raise
            call.stdin_payload = sink.getvalue()

        if command == ("info", "--format={{json .SecurityOptions}}"):
            return self._json(self.security_options)
        if command == ("info", "--format={{json .ID}}"):
            daemon_id = (
                self.daemon_id_responses.pop(0)
                if self.daemon_id_responses
                else self.daemon_id
            )
            return self._json(daemon_id)
        if command == ("info", "--format={{json .OSType}}"):
            return self._json("linux")
        if command == ("info", "--format={{json .Architecture}}"):
            return self._json("amd64")

        if command[:2] == ("image", "inspect"):
            assert command[-1] == _IMAGE_REFERENCE
            field = command[2]
            if field == "--format={{json .RepoDigests}}":
                return self._json(self.repo_digests)
            if field == "--format={{json .Id}}":
                return self._json(self.image_id)
            if field == "--format={{json .Os}}":
                return self._json(self.image_os)
            if field == "--format={{json .Architecture}}":
                return self._json(self.image_architecture)
            if field == "--format={{json .Config}}":
                return self._json(
                    {
                        "Labels": {
                            TECHNICAL_PARSER_OCI_CONTRACT_LABEL: self.image_contract,
                            TECHNICAL_PARSER_OCI_POLICY_LABEL: self.image_policy,
                            TECHNICAL_PARSER_OCI_POLICY_SHA256_LABEL: self.image_policy_sha256,
                        },
                        "Volumes": None,
                    }
                )
            raise AssertionError(f"unexpected image inspection: {command}")

        if command[:2] == ("container", "create"):
            self._register_container(command)
            if self.after_container_create is not None:
                callback = self.after_container_create
                self.after_container_create = None
                callback()
            if self.create_behavior == "ack_lost":
                raise _BoundedCommandError("timeout")
            if self.create_behavior == "malformed_ack":
                return _BoundedCommandResult(returncode=0, stdout=b"not-an-id\n", stderr=b"")
            if self.create_behavior == "nonzero":
                return _BoundedCommandResult(returncode=125, stdout=b"", stderr=b"")
            return _BoundedCommandResult(
                returncode=0,
                stdout=f"{_CONTAINER_ID}\n".encode("ascii"),
                stderr=b"",
            )

        if command[:2] == ("container", "ls"):
            assert command[2:5] == ("--all", "--quiet", "--no-trunc")
            filter_arguments = command[5:]
            assert len(filter_arguments) % 2 == 0
            assert filter_arguments[::2] == ("--filter",) * (
                len(filter_arguments) // 2
            )
            return self._list_containers(filter_arguments[1::2])

        if command[:2] == ("container", "inspect"):
            if self.container_inspect_interrupt is not None:
                interrupt = self.container_inspect_interrupt
                self.container_inspect_interrupt = None
                raise interrupt
            container_id = command[-1]
            if container_id not in self.containers:
                return _BoundedCommandResult(returncode=1, stdout=b"", stderr=b"")
            return self._json(self.containers[container_id][self._field(command[2])])

        if command[:2] == ("container", "start"):
            assert command[2:4] == ("--attach", "--interactive")
            container_id = command[-1]
            if self.start_error is not None:
                self._terminate(on_terminate)
                raise _BoundedCommandError(self.start_error)  # type: ignore[arg-type]
            container = self.containers[container_id]
            container["State"] = {
                "Dead": False,
                "Error": "",
                "ExitCode": 0,
                "OOMKilled": False,
                "Running": False,
                "Status": "exited",
            }
            output = _layout_output() if container["operation"] == "layout" else _page_output()
            return _BoundedCommandResult(
                returncode=self.start_returncode,
                stdout=output,
                stderr=self.start_stderr,
            )

        if command[:2] == ("container", "rm"):
            assert command[2:4] == ("--force", "--volumes")
            container_id = command[-1]
            if not self.cleanup_stuck:
                self.containers.pop(container_id, None)
            if self.after_container_remove is not None:
                callback = self.after_container_remove
                self.after_container_remove = None
                callback()
            return _BoundedCommandResult(returncode=0, stdout=b"", stderr=b"")

        raise AssertionError(f"unexpected OCI command: {command}")


@dataclass(frozen=True, slots=True)
class _Harness:
    runner: DigestPinnedOciTechnicalParserRunner
    adapter: FakeOciRuntimeAdapter
    runtime_path: Path
    runtime_sha256: str
    seccomp_path: Path
    seccomp_sha256: str
    controller_owner_id: str
    execution_fence: FakeExecutionFence


def _build_harness(
    tmp_path: Path,
    *,
    adapter: FakeOciRuntimeAdapter | None = None,
    image_reference: str = _IMAGE_REFERENCE,
    runtime_host: str = _RUNTIME_HOST,
    controller_owner_id: str = _CONTROLLER_OWNER_ID,
    runtime_sha256: str | None = None,
    seccomp: bytes | None = None,
    seccomp_sha256: str | None = None,
    profile: TechnicalParserOciRuntimeProfile | None = None,
    execution_fence: FakeExecutionFence | None = None,
) -> _Harness:
    tmp_path.mkdir(parents=True, exist_ok=True)
    runtime_path = (tmp_path / "fake-oci-runtime.exe").resolve()
    runtime_path.write_bytes(_RUNTIME_PAYLOAD)
    actual_runtime_sha256 = hashlib.sha256(_RUNTIME_PAYLOAD).hexdigest()
    seccomp_path = (tmp_path / "seccomp-source.json").resolve()
    seccomp_payload = _seccomp_bytes() if seccomp is None else seccomp
    seccomp_path.write_bytes(seccomp_payload)
    actual_seccomp_sha256 = hashlib.sha256(seccomp_payload).hexdigest()
    selected_adapter = adapter or FakeOciRuntimeAdapter()
    selected_fence = execution_fence or FakeExecutionFence()
    runner = DigestPinnedOciTechnicalParserRunner(
        runtime_path=runtime_path,
        runtime_executable_sha256=runtime_sha256 or actual_runtime_sha256,
        runtime_host=runtime_host,
        controller_owner_id=controller_owner_id,
        image_reference=image_reference,
        seccomp_profile_path=seccomp_path,
        seccomp_profile_sha256=seccomp_sha256 or actual_seccomp_sha256,
        profile=profile or TechnicalParserOciRuntimeProfile(platform="linux/amd64"),
        execution_fence=selected_fence,
        runtime_adapter=selected_adapter,
    )
    return _Harness(
        runner=runner,
        adapter=selected_adapter,
        runtime_path=runtime_path,
        runtime_sha256=actual_runtime_sha256,
        seccomp_path=seccomp_path,
        seccomp_sha256=actual_seccomp_sha256,
        controller_owner_id=controller_owner_id,
        execution_fence=selected_fence,
    )


def _expected_attestation(_harness: _Harness) -> TechnicalParserRuntimeAttestation:
    return create_technical_parser_runtime_attestation(
        engine=TECHNICAL_PARSER_OCI_ENGINE,
        schema=TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2,
        claims={
            "controller_owner_id": _harness.controller_owner_id,
            "execution_fence_sha256": _harness.execution_fence.identity_sha256,
            "extraction_policy": _POLICY,
            "extraction_policy_sha256": _POLICY_SHA256,
            "image_id": _IMAGE_ID,
            "image_reference": _IMAGE_REFERENCE,
            "oci_profile_schema": TECHNICAL_PARSER_OCI_PROFILE_SCHEMA,
            "oci_daemon_identity_sha256": _DAEMON_IDENTITY_SHA256,
            "platform": "linux/amd64",
            "runtime_executable_sha256": _harness.runtime_sha256,
            "runtime_host": _RUNTIME_HOST,
            "runtime_profile_sha256": _harness.runner.runtime_profile_sha256,
            "seccomp_profile_sha256": _harness.seccomp_sha256,
            "transport_schema": TECHNICAL_PARSER_OCI_TRANSPORT_SCHEMA,
            "worker_image_digest": _WORKER_DIGEST,
        },
    )


def _inspect_layout(
    harness: _Harness,
    *,
    request: bytes | None = None,
    source: BinaryIO | None = None,
    invocation_id: str = _INVOCATION_IDS[0],
    expected_attestation_sha256: str | None = None,
    prepare: Callable[[], None] | None = None,
    authorize: Callable[[], None] | None = None,
    finalize: Callable[[TechnicalParserExecutionReceipt], None] | None = None,
) -> TechnicalParserExecutionSuccess:
    expected = _expected_attestation(harness)
    return harness.runner.inspect_layout(
        _layout_request() if request is None else request,
        source=BytesIO(_SOURCE) if source is None else source,
        invocation_id=invocation_id,
        expected_attestation_sha256=(
            expected.sha256
            if expected_attestation_sha256 is None
            else expected_attestation_sha256
        ),
        prepare=prepare,
        authorize=authorize,
        finalize=finalize,
    )


def _extract_page(
    harness: _Harness,
    *,
    request: bytes | None = None,
    source: BinaryIO | None = None,
    invocation_id: str = _INVOCATION_IDS[1],
) -> TechnicalParserExecutionSuccess:
    return harness.runner.extract_page(
        _page_request() if request is None else request,
        source=BytesIO(_SOURCE) if source is None else source,
        invocation_id=invocation_id,
        expected_attestation_sha256=_expected_attestation(harness).sha256,
    )


def _assert_configuration_code(
    error: pytest.ExceptionInfo[TechnicalParserOciConfigurationError],
    code: str,
) -> None:
    assert error.value.code == code
    assert str(error.value) == code


def _assert_execution_code(
    error: pytest.ExceptionInfo[TechnicalParserExecutionError],
    code: str,
) -> None:
    assert error.value.code == code
    assert str(error.value) == code
    assert error.value.__cause__ is None


def _operation_calls(adapter: FakeOciRuntimeAdapter, operation: str) -> list[_RecordedCall]:
    return [call for call in adapter.calls if call.args[5:7] == ("container", operation)]


def _seed_exact_container(
    harness: _Harness,
    *,
    invocation_id: str = _INVOCATION_IDS[0],
    owner_id: str = _CONTROLLER_OWNER_ID,
    state: str = "created",
) -> TechnicalParserRuntimeAttestation:
    success = _inspect_layout(harness, invocation_id=invocation_id)
    create_call = _operation_calls(harness.adapter, "create")[0]
    create_command = list(create_call.args[5:])
    seccomp_index = next(
        index
        for index, argument in enumerate(create_command)
        if argument.startswith("--security-opt=seccomp=")
    )
    create_command[seccomp_index] = (
        f"--security-opt=seccomp={harness.seccomp_path}"
    )
    harness.adapter._register_container(tuple(create_command))
    container = harness.adapter.containers[_CONTAINER_ID]
    labels = container["labels"]
    assert isinstance(labels, dict)
    labels[TECHNICAL_PARSER_OCI_OWNER_LABEL] = owner_id
    container["State"] = {"Running": state == "running", "Status": state}
    harness.adapter.calls.clear()
    harness.execution_fence.wait_modes.clear()
    return success.receipt.attestation


@pytest.mark.parametrize(
    "image_reference",
    [
        "registry.example/classifire/parser:latest",
        f"Registry.example/classifire/parser@sha256:{_WORKER_DIGEST}",
        f"registry.example/classifire/parser@sha256:{_WORKER_DIGEST[:-1]}",
    ],
)
def test_constructor_rejects_mutable_or_malformed_image_references(
    tmp_path: Path,
    image_reference: str,
) -> None:
    with pytest.raises(TechnicalParserOciConfigurationError) as error:
        _build_harness(tmp_path, image_reference=image_reference)

    _assert_configuration_code(error, "PARSER_OCI_IMAGE_REFERENCE_INVALID")


@pytest.mark.parametrize(
    "runtime_host",
    [
        "",
        "tcp://127.0.0.1:2375",
        "unix:///var/run/docker.sock",
        "unix:///run/user/0/docker.sock",
        "unix:///run/user/1000/podman.sock",
    ],
)
def test_constructor_requires_explicit_rootless_unix_runtime_host(
    tmp_path: Path,
    runtime_host: str,
) -> None:
    with pytest.raises(TechnicalParserOciConfigurationError) as error:
        _build_harness(tmp_path, runtime_host=runtime_host)

    _assert_configuration_code(error, "PARSER_OCI_RUNTIME_HOST_INVALID")


@pytest.mark.parametrize(
    "controller_owner_id",
    [
        "",
        "AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE",
        "aaaaaaaa-bbbb-1ccc-8ddd-eeeeeeeeeeee",
    ],
)
def test_constructor_requires_canonical_uuid4_controller_owner(
    tmp_path: Path,
    controller_owner_id: str,
) -> None:
    with pytest.raises(TechnicalParserOciConfigurationError) as error:
        _build_harness(tmp_path, controller_owner_id=controller_owner_id)

    _assert_configuration_code(error, "PARSER_OCI_CONTROLLER_OWNER_INVALID")


def test_constructor_requires_stable_sha256_execution_fence_identity(
    tmp_path: Path,
) -> None:
    with pytest.raises(TechnicalParserOciConfigurationError) as error:
        _build_harness(
            tmp_path,
            execution_fence=FakeExecutionFence(identity_sha256="not-a-sha256"),
        )

    _assert_configuration_code(error, "PARSER_OCI_EXECUTION_FENCE_INVALID")


@pytest.mark.skipif(os.name != "posix", reason="POSIX flock is Linux-only")
def test_posix_flock_fence_excludes_separate_instances_on_same_inode(
    tmp_path: Path,
) -> None:
    fence_path = (tmp_path / "technical-parser.lock").resolve()
    fence_path.touch(mode=0o600)
    fence_path.chmod(0o600)
    first = PosixFlockTechnicalParserExecutionFence(
        fence_path,
        wait_timeout_seconds=0.1,
    )
    second = PosixFlockTechnicalParserExecutionFence(
        fence_path,
        wait_timeout_seconds=0.1,
    )

    assert first.identity_sha256 == second.identity_sha256
    with first.hold(wait=False):
        with pytest.raises(TechnicalParserExecutionError) as error:
            with second.hold(wait=False):
                raise AssertionError("second fence must not enter")
        _assert_execution_code(error, "PARSER_EXECUTION_UNAVAILABLE")

    with second.hold(wait=False):
        pass


def test_runtime_profile_rejects_any_relaxed_fixed_limit() -> None:
    with pytest.raises(TechnicalParserOciConfigurationError) as error:
        TechnicalParserOciRuntimeProfile(platform="linux/amd64", pids_limit=65)

    _assert_configuration_code(error, "PARSER_OCI_PLATFORM_INVALID")


def test_constructor_rejects_runtime_digest_mismatch(tmp_path: Path) -> None:
    with pytest.raises(TechnicalParserOciConfigurationError) as error:
        _build_harness(tmp_path, runtime_sha256="0" * 64)

    _assert_configuration_code(error, "PARSER_OCI_RUNTIME_SHA256_INVALID")


@pytest.mark.parametrize(
    ("seccomp", "sha256", "expected_code"),
    [
        (
            _canonical({"defaultAction": "SCMP_ACT_ALLOW", "syscalls": []}),
            None,
            "PARSER_OCI_SECCOMP_PROFILE_INVALID",
        ),
        (
            _seccomp_bytes(allowed_names=("read", "socket")),
            None,
            "PARSER_OCI_SECCOMP_PROFILE_INVALID",
        ),
        (
            _canonical(
                {
                    "defaultAction": "SCMP_ACT_ERRNO",
                    "syscalls": [
                        {
                            "action": "SCMP_ACT_LOG",
                            "names": ["read", "socketcall"],
                        }
                    ],
                }
            ),
            None,
            "PARSER_OCI_SECCOMP_PROFILE_INVALID",
        ),
        (
            _canonical(
                {
                    "defaultAction": "SCMP_ACT_ERRNO",
                    "listenerPath": "/run/user/1000/seccomp-listener.sock",
                    "syscalls": [{"action": "SCMP_ACT_ALLOW", "names": ["read"]}],
                }
            ),
            None,
            "PARSER_OCI_SECCOMP_PROFILE_INVALID",
        ),
        (
            _canonical(
                {
                    "defaultAction": "SCMP_ACT_ERRNO",
                    "listenerMetadata": "external-listener",
                    "syscalls": [{"action": "SCMP_ACT_ALLOW", "names": ["read"]}],
                }
            ),
            None,
            "PARSER_OCI_SECCOMP_PROFILE_INVALID",
        ),
        (
            _seccomp_bytes(),
            "0" * 64,
            "PARSER_OCI_SECCOMP_SHA256_INVALID",
        ),
    ],
)
def test_constructor_rejects_unsafe_or_unbound_seccomp_profiles(
    tmp_path: Path,
    seccomp: bytes,
    sha256: str | None,
    expected_code: str,
) -> None:
    with pytest.raises(TechnicalParserOciConfigurationError) as error:
        _build_harness(tmp_path, seccomp=seccomp, seccomp_sha256=sha256)

    _assert_configuration_code(error, expected_code)


def test_probe_returns_exact_runtime_image_and_profile_attestation(tmp_path: Path) -> None:
    harness = _build_harness(tmp_path)

    attestation = harness.runner.probe(
        extraction_policy=_POLICY,
        extraction_policy_sha256=_POLICY_SHA256,
    )

    assert attestation == _expected_attestation(harness)
    assert attestation.schema == TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2
    assert attestation.engine == TECHNICAL_PARSER_OCI_ENGINE
    assert len(attestation.sha256) == 64
    assert parse_technical_parser_runtime_attestation(
        attestation.canonical_json,
        expected_sha256=attestation.sha256,
    ) == attestation
    assert attestation.as_dict()["claims"] == {
        "controller_owner_id": _CONTROLLER_OWNER_ID,
        "execution_fence_sha256": _EXECUTION_FENCE_SHA256,
        "extraction_policy": _POLICY,
        "extraction_policy_sha256": _POLICY_SHA256,
        "image_id": _IMAGE_ID,
        "image_reference": _IMAGE_REFERENCE,
        "oci_profile_schema": TECHNICAL_PARSER_OCI_PROFILE_SCHEMA,
        "oci_daemon_identity_sha256": _DAEMON_IDENTITY_SHA256,
        "platform": "linux/amd64",
        "runtime_executable_sha256": harness.runtime_sha256,
        "runtime_host": _RUNTIME_HOST,
        "runtime_profile_sha256": harness.runner.runtime_profile_sha256,
        "seccomp_profile_sha256": harness.seccomp_sha256,
        "transport_schema": TECHNICAL_PARSER_OCI_TRANSPORT_SCHEMA,
        "worker_image_digest": _WORKER_DIGEST,
    }
    assert [call.args[5:] for call in harness.adapter.calls] == [
        ("info", "--format={{json .ID}}"),
        ("info", "--format={{json .SecurityOptions}}"),
        ("info", "--format={{json .OSType}}"),
        ("info", "--format={{json .Architecture}}"),
        ("image", "inspect", "--format={{json .RepoDigests}}", _IMAGE_REFERENCE),
        ("image", "inspect", "--format={{json .Id}}", _IMAGE_REFERENCE),
        ("image", "inspect", "--format={{json .Os}}", _IMAGE_REFERENCE),
            ("image", "inspect", "--format={{json .Architecture}}", _IMAGE_REFERENCE),
            ("image", "inspect", "--format={{json .Config}}", _IMAGE_REFERENCE),
            ("info", "--format={{json .ID}}"),
        ]
    assert all(call.args[1] == "--config" for call in harness.adapter.calls)
    assert all(call.args[3:5] == ("--host", _RUNTIME_HOST) for call in harness.adapter.calls)
    assert all(call.environment == {} for call in harness.adapter.calls)
    assert all(call.stdin_payload is None for call in harness.adapter.calls)
    assert harness.adapter.runtime_snapshots
    for snapshot in harness.adapter.runtime_snapshots:
        assert snapshot.existed_during_call is True
        assert snapshot.path.is_absolute()
        assert snapshot.path != harness.runtime_path
        assert snapshot.sha256 == harness.runtime_sha256
        assert not snapshot.path.exists()
    assert {snapshot.path for snapshot in harness.adapter.runtime_snapshots} == {
        harness.adapter.runtime_snapshots[0].path
    }
    assert harness.adapter.runtime_config_snapshots
    for runtime_snapshot, config_snapshot in zip(
        harness.adapter.runtime_snapshots,
        harness.adapter.runtime_config_snapshots,
        strict=True,
    ):
        assert config_snapshot.existed_during_call is True
        assert config_snapshot.path.is_absolute()
        assert config_snapshot.path.parent == runtime_snapshot.path.parent
        assert config_snapshot.entries == ("config.json",)
        assert config_snapshot.config_bytes == b"{}"
        assert not config_snapshot.path.exists()
    assert {snapshot.path for snapshot in harness.adapter.runtime_config_snapshots} == {
        harness.adapter.runtime_config_snapshots[0].path
    }


def test_runtime_attestation_rejects_noncanonical_duplicate_or_unbound_payloads(
    tmp_path: Path,
) -> None:
    attestation = _expected_attestation(_build_harness(tmp_path))
    noncanonical = json.dumps(attestation.as_dict()).encode("ascii")
    duplicate_key = (
        b'{"claims":{"claim":"value"},"engine":"oci",'
        b'"schema":"technical-parser-runtime-attestation-v1",'
        b'"schema":"technical-parser-runtime-attestation-v1"}'
    )

    with pytest.raises(ValueError):
        parse_technical_parser_runtime_attestation(noncanonical)
    with pytest.raises(ValueError):
        parse_technical_parser_runtime_attestation(duplicate_key)
    with pytest.raises(ValueError):
        parse_technical_parser_runtime_attestation(
            attestation.canonical_json,
            expected_sha256="0" * 64,
        )
    with pytest.raises(ValueError):
        create_technical_parser_runtime_attestation(
            engine="oci",
            claims={"oversized_claim": "x" * (16 * 1024 + 1)},
        )

    copied = attestation.as_dict()
    copied_claims = copied["claims"]
    assert isinstance(copied_claims, dict)
    copied_claims["image_id"] = "tampered"
    assert attestation.as_dict()["claims"] != copied_claims


def test_runtime_attestation_v1_remains_parse_compatible() -> None:
    legacy = create_technical_parser_runtime_attestation(
        engine="legacy-test",
        claims={"compatibility": "retained"},
    )

    assert legacy.schema == TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA
    assert parse_technical_parser_runtime_attestation(
        legacy.canonical_json,
        expected_sha256=legacy.sha256,
    ) == legacy


def test_execution_unknown_has_one_stable_exclusive_outcome_code(
    tmp_path: Path,
) -> None:
    attestation = _expected_attestation(_build_harness(tmp_path))
    completed_at = datetime.now(UTC)
    receipt = create_technical_parser_execution_receipt(
        execution_state="execution_unknown",
        operation="layout",
        invocation_id=_INVOCATION_IDS[0],
        expected_attestation_sha256=attestation.sha256,
        attestation=attestation,
        outcome_code=TECHNICAL_PARSER_EXECUTION_OUTCOME_UNKNOWN,
        container_id=None,
        started_at=None,
        completed_at=completed_at,
        exit_code=None,
        stdout_sha256=None,
        stdout_size_bytes=None,
        cleanup_confirmed=True,
    )

    assert receipt.outcome_code == "PARSER_EXECUTION_OUTCOME_UNKNOWN"
    assert parse_technical_parser_execution_receipt(
        receipt.canonical_json,
        expected_sha256=receipt.sha256,
    ) == receipt

    otherwise_valid_states = (
        {
            "cleanup_confirmed": True,
            "container_id": None,
            "execution_state": "not_started",
            "exit_code": None,
            "started_at": None,
            "stdout_sha256": None,
            "stdout_size_bytes": None,
        },
        {
            "cleanup_confirmed": True,
            "container_id": _CONTAINER_ID,
            "execution_state": "succeeded",
            "exit_code": 0,
            "started_at": completed_at,
            "stdout_sha256": "0" * 64,
            "stdout_size_bytes": 1,
        },
        {
            "cleanup_confirmed": True,
            "container_id": _CONTAINER_ID,
            "execution_state": "failed",
            "exit_code": None,
            "started_at": completed_at,
            "stdout_sha256": None,
            "stdout_size_bytes": None,
        },
        {
            "cleanup_confirmed": False,
            "container_id": None,
            "execution_state": "containment_lost",
            "exit_code": None,
            "started_at": None,
            "stdout_sha256": None,
            "stdout_size_bytes": None,
        },
    )
    for state in otherwise_valid_states:
        with pytest.raises(ValueError):
            create_technical_parser_execution_receipt(
                operation="layout",
                invocation_id=_INVOCATION_IDS[0],
                expected_attestation_sha256=attestation.sha256,
                attestation=attestation,
                outcome_code=TECHNICAL_PARSER_EXECUTION_OUTCOME_UNKNOWN,
                completed_at=completed_at,
                **state,  # type: ignore[arg-type]
            )
    invalid_unknown_fields = (
        {"started_at": completed_at},
        {"exit_code": 0},
        {"stdout_sha256": "0" * 64, "stdout_size_bytes": 1},
        {"cleanup_confirmed": False},
        {"outcome_code": "PARSER_EXECUTION_FAILED"},
    )
    for changes in invalid_unknown_fields:
        values: dict[str, object] = {
            "cleanup_confirmed": True,
            "container_id": None,
            "execution_state": "execution_unknown",
            "exit_code": None,
            "outcome_code": TECHNICAL_PARSER_EXECUTION_OUTCOME_UNKNOWN,
            "started_at": None,
            "stdout_sha256": None,
            "stdout_size_bytes": None,
        }
        values.update(changes)
        with pytest.raises(ValueError):
            create_technical_parser_execution_receipt(
                operation="layout",
                invocation_id=_INVOCATION_IDS[0],
                expected_attestation_sha256=attestation.sha256,
                attestation=attestation,
                completed_at=completed_at,
                **values,  # type: ignore[arg-type]
            )
    with pytest.raises(ValueError):
        TechnicalParserExecutionError(
            TECHNICAL_PARSER_EXECUTION_OUTCOME_UNKNOWN
        )


def test_daemon_identity_change_changes_v2_runtime_attestation(tmp_path: Path) -> None:
    harness = _build_harness(tmp_path)
    first = harness.runner.probe(
        extraction_policy=_POLICY,
        extraction_policy_sha256=_POLICY_SHA256,
    )
    harness.adapter.daemon_id = "ZYXWVUTSRQPONMLKJIHGFEDC98765432"

    second = harness.runner.probe(
        extraction_policy=_POLICY,
        extraction_policy_sha256=_POLICY_SHA256,
    )

    first_claims = first.as_dict()["claims"]
    second_claims = second.as_dict()["claims"]
    assert isinstance(first_claims, dict)
    assert isinstance(second_claims, dict)
    assert first.sha256 != second.sha256
    assert (
        first_claims["oci_daemon_identity_sha256"]
        != second_claims["oci_daemon_identity_sha256"]
    )


@pytest.mark.parametrize("daemon_id", ["", " leading", "trailing ", "nonascii-\u2603"])
def test_malformed_daemon_identity_fails_closed_before_other_probes(
    tmp_path: Path,
    daemon_id: str,
) -> None:
    adapter = FakeOciRuntimeAdapter()
    adapter.daemon_id = daemon_id
    harness = _build_harness(tmp_path, adapter=adapter)

    with pytest.raises(TechnicalParserExecutionError) as error:
        harness.runner.probe(
            extraction_policy=_POLICY,
            extraction_policy_sha256=_POLICY_SHA256,
        )

    _assert_execution_code(error, "PARSER_EXECUTION_FAILED")
    assert [call.args[5:] for call in adapter.calls] == [
        ("info", "--format={{json .ID}}")
    ]


@pytest.mark.parametrize(
    "security_options",
    [
        ["rootless"],
        ["name=rootlesskit"],
        ["security=name=rootless"],
        ["name=seccomp", "name=cgroupns"],
    ],
)
def test_attestation_requires_exact_rootless_security_option(
    tmp_path: Path,
    security_options: list[str],
) -> None:
    adapter = FakeOciRuntimeAdapter()
    adapter.security_options = security_options
    harness = _build_harness(tmp_path, adapter=adapter)

    with pytest.raises(TechnicalParserExecutionError) as error:
        harness.runner.probe(
            extraction_policy=_POLICY,
            extraction_policy_sha256=_POLICY_SHA256,
        )

    _assert_execution_code(error, "PARSER_EXECUTION_UNAVAILABLE")
    assert [call.args[5:] for call in adapter.calls] == [
        ("info", "--format={{json .ID}}"),
        ("info", "--format={{json .SecurityOptions}}")
    ]


def test_runtime_source_replacement_after_construction_fails_before_adapter_access(
    tmp_path: Path,
) -> None:
    harness = _build_harness(tmp_path)
    replacement = (tmp_path / "replacement-runtime").resolve()
    replacement.write_bytes(b"unexpected replacement runtime")
    replacement.replace(harness.runtime_path)

    with pytest.raises(TechnicalParserExecutionError) as error:
        harness.runner.probe(
            extraction_policy=_POLICY,
            extraction_policy_sha256=_POLICY_SHA256,
        )

    _assert_execution_code(error, "PARSER_EXECUTION_UNAVAILABLE")
    assert harness.adapter.calls == []


def test_authorization_runs_under_nonblocking_fence_immediately_before_create(
    tmp_path: Path,
) -> None:
    harness = _build_harness(tmp_path)
    callback_call_offsets: list[int] = []
    finalized: list[TechnicalParserExecutionReceipt] = []

    def prepare() -> None:
        assert harness.execution_fence.held is True
        assert not _operation_calls(harness.adapter, "create")

    def authorize() -> None:
        assert harness.execution_fence.held is True
        assert not _operation_calls(harness.adapter, "create")
        assert not _operation_calls(harness.adapter, "start")
        callback_call_offsets.append(len(harness.adapter.calls))

    def finalize(receipt: TechnicalParserExecutionReceipt) -> None:
        assert harness.execution_fence.held is True
        assert harness.adapter.containers == {}
        finalized.append(receipt)

    success = _inspect_layout(
        harness,
        prepare=prepare,
        authorize=authorize,
        finalize=finalize,
    )

    assert success.output == _layout_output()
    assert callback_call_offsets
    calls_after_authorize = harness.adapter.calls[callback_call_offsets[0] :]
    assert [call.args[5:7] for call in calls_after_authorize[:2]] == [
        ("container", "ls"),
        ("container", "ls"),
    ]
    assert calls_after_authorize[2].args[5:] == (
        "info",
        "--format={{json .ID}}",
    )
    assert calls_after_authorize[3].args[5:7] == ("container", "create")
    assert finalized == [success.receipt]
    assert harness.execution_fence.wait_modes == [False]
    assert harness.execution_fence.held is False


def test_ordinary_authorization_failure_returns_not_started_without_create(
    tmp_path: Path,
) -> None:
    harness = _build_harness(tmp_path)
    observed_held: list[bool] = []
    finalized: list[TechnicalParserExecutionReceipt] = []

    def authorize() -> None:
        observed_held.append(harness.execution_fence.held)
        raise RuntimeError("host authorization rejected the stale attempt")

    with pytest.raises(TechnicalParserExecutionError) as error:
        _inspect_layout(
            harness,
            prepare=lambda: None,
            authorize=authorize,
            finalize=finalized.append,
        )

    _assert_execution_code(error, "PARSER_EXECUTION_UNAVAILABLE")
    receipt = error.value.receipt
    assert receipt is not None
    assert receipt.execution_state == "not_started"
    assert receipt.cleanup_confirmed is True
    assert receipt.container_id is None
    assert receipt.started_at is None
    assert finalized == [receipt]
    assert observed_held == [True]
    assert harness.execution_fence.wait_modes == [False]
    assert harness.execution_fence.held is False
    assert not _operation_calls(harness.adapter, "create")
    assert not _operation_calls(harness.adapter, "start")


@pytest.mark.parametrize(
    ("interrupt", "expected_type"),
    [(KeyboardInterrupt(), KeyboardInterrupt), (SystemExit(41), SystemExit)],
)
def test_authorization_interrupt_propagates_before_create_and_releases_fence(
    tmp_path: Path,
    interrupt: BaseException,
    expected_type: type[BaseException],
) -> None:
    harness = _build_harness(tmp_path)
    finalized: list[TechnicalParserExecutionReceipt] = []

    def authorize() -> None:
        assert harness.execution_fence.held is True
        raise interrupt

    with pytest.raises(expected_type) as error:
        _inspect_layout(
            harness,
            prepare=lambda: None,
            authorize=authorize,
            finalize=finalized.append,
        )

    assert error.value is interrupt
    assert finalized == []
    assert harness.execution_fence.held is False
    assert not _operation_calls(harness.adapter, "create")
    assert not _operation_calls(harness.adapter, "start")


def test_execution_does_not_wait_or_create_behind_reconciliation_fence(
    tmp_path: Path,
) -> None:
    harness = _build_harness(tmp_path)

    with harness.execution_fence.hold(wait=True):
        with pytest.raises(TechnicalParserExecutionError) as error:
            _inspect_layout(harness)
        assert harness.execution_fence.held is True

    _assert_execution_code(error, "PARSER_EXECUTION_UNAVAILABLE")
    assert error.value.receipt is None
    assert harness.execution_fence.wait_modes == [True, False]
    assert harness.adapter.calls == []
    assert harness.adapter.containers == {}


def test_cleanup_proves_absence_and_finalizes_under_same_fence(
    tmp_path: Path,
) -> None:
    harness = _build_harness(tmp_path)
    persisted = harness.runner.probe(
        extraction_policy=_POLICY,
        extraction_policy_sha256=_POLICY_SHA256,
    )
    harness.adapter.calls.clear()
    finalized: list[TechnicalParserOciCleanupProof] = []

    def finalize(proof: TechnicalParserOciCleanupProof) -> None:
        assert harness.execution_fence.held is True
        assert harness.adapter.containers == {}
        finalized.append(proof)

    proof = harness.runner.cleanup_orphan_invocation(
        invocation_id=_INVOCATION_IDS[0],
        operation="layout",
        persisted_runtime_attestation=persisted,
        finalize=finalize,
    )

    assert finalized == [proof]
    assert proof.schema == TECHNICAL_PARSER_OCI_CLEANUP_PROOF_SCHEMA
    assert proof.invocation_id == _INVOCATION_IDS[0]
    assert proof.runtime_attestation_sha256 == persisted.sha256
    assert proof.controller_owner_id == _CONTROLLER_OWNER_ID
    assert proof.runtime_profile_sha256 == harness.runner.runtime_profile_sha256
    assert proof.oci_daemon_identity_sha256 == _DAEMON_IDENTITY_SHA256
    assert proof.execution_fence_sha256 == _EXECUTION_FENCE_SHA256
    assert proof.observed_container_id is None
    assert proof.observed_container_state is None
    assert proof.cleanup_confirmed is True
    assert hashlib.sha256(proof.canonical_json).hexdigest() == proof.sha256
    assert harness.execution_fence.wait_modes == [True]
    assert harness.execution_fence.held is False
    assert not _operation_calls(harness.adapter, "create")
    assert not _operation_calls(harness.adapter, "start")
    assert not _operation_calls(harness.adapter, "rm")
    label_filter = (
        f"label={TECHNICAL_PARSER_OCI_INVOCATION_LABEL}={_INVOCATION_IDS[0]}"
    )
    assert [call.args[-1] for call in _operation_calls(harness.adapter, "ls")] == [
        label_filter,
        label_filter,
    ]

    with pytest.raises(ValueError):
        replace(proof, sha256="0" * 64)


@pytest.mark.parametrize("state", ["created", "running", "exited"])
def test_cleanup_removes_one_exact_owned_container_and_proves_id_absence(
    tmp_path: Path,
    state: str,
) -> None:
    harness = _build_harness(tmp_path)
    persisted = _seed_exact_container(harness, state=state)

    proof = harness.runner.cleanup_orphan_invocation(
        invocation_id=_INVOCATION_IDS[0],
        operation="layout",
        persisted_runtime_attestation=persisted,
    )

    assert proof.observed_container_id == _CONTAINER_ID
    assert proof.observed_container_state == state
    assert proof.cleanup_confirmed is True
    assert harness.adapter.containers == {}
    assert harness.execution_fence.wait_modes == [True]
    assert len(_operation_calls(harness.adapter, "rm")) == 1
    assert not _operation_calls(harness.adapter, "create")
    assert not _operation_calls(harness.adapter, "start")
    list_filters = [call.args[-1] for call in _operation_calls(harness.adapter, "ls")]
    assert (
        f"label={TECHNICAL_PARSER_OCI_INVOCATION_LABEL}={_INVOCATION_IDS[0]}"
        in list_filters
    )
    assert f"id={_CONTAINER_ID}" in list_filters


def test_cleanup_finalizer_failure_propagates_and_releases_fence(
    tmp_path: Path,
) -> None:
    harness = _build_harness(tmp_path)
    persisted = harness.runner.probe(
        extraction_policy=_POLICY,
        extraction_policy_sha256=_POLICY_SHA256,
    )
    harness.adapter.calls.clear()
    finalized: list[TechnicalParserOciCleanupProof] = []

    def finalize(proof: TechnicalParserOciCleanupProof) -> None:
        assert harness.execution_fence.held is True
        finalized.append(proof)
        raise RuntimeError("database transaction rolled back")

    with pytest.raises(RuntimeError, match="database transaction rolled back"):
        harness.runner.cleanup_orphan_invocation(
            invocation_id=_INVOCATION_IDS[0],
            operation="layout",
            persisted_runtime_attestation=persisted,
            finalize=finalize,
        )

    assert len(finalized) == 1
    assert harness.execution_fence.held is False
    assert not _operation_calls(harness.adapter, "create")
    assert not _operation_calls(harness.adapter, "start")


def test_cleanup_rejects_foreign_owner_without_removing_container(
    tmp_path: Path,
) -> None:
    harness = _build_harness(tmp_path)
    persisted = _seed_exact_container(
        harness,
        owner_id=_INVOCATION_IDS[2],
    )
    finalized: list[TechnicalParserOciCleanupProof] = []

    with pytest.raises(TechnicalParserExecutionError) as error:
        harness.runner.cleanup_orphan_invocation(
            invocation_id=_INVOCATION_IDS[0],
            operation="layout",
            persisted_runtime_attestation=persisted,
            finalize=finalized.append,
        )

    _assert_execution_code(error, "PARSER_EXECUTION_CONTAINMENT_LOST")
    assert finalized == []
    assert _CONTAINER_ID in harness.adapter.containers
    assert harness.execution_fence.held is False
    assert not _operation_calls(harness.adapter, "rm")
    assert not _operation_calls(harness.adapter, "create")
    assert not _operation_calls(harness.adapter, "start")
    label_filter = (
        f"label={TECHNICAL_PARSER_OCI_INVOCATION_LABEL}={_INVOCATION_IDS[0]}"
    )
    assert label_filter in [
        call.args[-1] for call in _operation_calls(harness.adapter, "ls")
    ]


def test_cleanup_rejects_multiple_global_invocation_matches_without_removal(
    tmp_path: Path,
) -> None:
    harness = _build_harness(tmp_path)
    persisted = _seed_exact_container(harness)
    second_id = "8" * 64
    second = dict(harness.adapter.containers[_CONTAINER_ID])
    second["Id"] = second_id
    harness.adapter.containers[second_id] = second
    finalized: list[TechnicalParserOciCleanupProof] = []

    with pytest.raises(TechnicalParserExecutionError) as error:
        harness.runner.cleanup_orphan_invocation(
            invocation_id=_INVOCATION_IDS[0],
            operation="layout",
            persisted_runtime_attestation=persisted,
            finalize=finalized.append,
        )

    _assert_execution_code(error, "PARSER_EXECUTION_CONTAINMENT_LOST")
    assert finalized == []
    assert set(harness.adapter.containers) == {_CONTAINER_ID, second_id}
    assert not _operation_calls(harness.adapter, "rm")
    assert not _operation_calls(harness.adapter, "create")
    assert not _operation_calls(harness.adapter, "start")


def test_cleanup_requires_verified_absence_before_finalization(
    tmp_path: Path,
) -> None:
    harness = _build_harness(tmp_path)
    persisted = _seed_exact_container(harness)
    harness.adapter.cleanup_stuck = True
    finalized: list[TechnicalParserOciCleanupProof] = []

    with pytest.raises(TechnicalParserExecutionError) as error:
        harness.runner.cleanup_orphan_invocation(
            invocation_id=_INVOCATION_IDS[0],
            operation="layout",
            persisted_runtime_attestation=persisted,
            finalize=finalized.append,
        )

    _assert_execution_code(error, "PARSER_EXECUTION_CONTAINMENT_LOST")
    assert finalized == []
    assert _CONTAINER_ID in harness.adapter.containers
    assert len(_operation_calls(harness.adapter, "rm")) == 1
    assert not _operation_calls(harness.adapter, "create")
    assert not _operation_calls(harness.adapter, "start")


@pytest.mark.parametrize(
    ("claim", "replacement", "enters_fence"),
    [
        ("controller_owner_id", _INVOCATION_IDS[2], False),
        ("runtime_profile_sha256", "2" * 64, False),
        ("execution_fence_sha256", "2" * 64, False),
        ("oci_daemon_identity_sha256", "2" * 64, True),
    ],
)
def test_cleanup_requires_exact_persisted_owner_runtime_daemon_and_fence(
    tmp_path: Path,
    claim: str,
    replacement: str,
    enters_fence: bool,
) -> None:
    harness = _build_harness(tmp_path)
    persisted = harness.runner.probe(
        extraction_policy=_POLICY,
        extraction_policy_sha256=_POLICY_SHA256,
    )
    payload = persisted.as_dict()
    claims = payload["claims"]
    assert isinstance(claims, dict)
    claims[claim] = replacement
    mismatched = create_technical_parser_runtime_attestation(
        engine=TECHNICAL_PARSER_OCI_ENGINE,
        schema=TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2,
        claims=claims,
    )
    harness.adapter.calls.clear()

    with pytest.raises(TechnicalParserExecutionError) as error:
        harness.runner.cleanup_orphan_invocation(
            invocation_id=_INVOCATION_IDS[0],
            operation="layout",
            persisted_runtime_attestation=mismatched,
        )

    _assert_execution_code(error, "PARSER_EXECUTION_FAILED")
    assert harness.execution_fence.wait_modes == ([True] if enters_fence else [])
    assert not _operation_calls(harness.adapter, "ls")
    assert not _operation_calls(harness.adapter, "rm")
    assert not _operation_calls(harness.adapter, "create")
    assert not _operation_calls(harness.adapter, "start")


def test_cleanup_rejects_v1_attestation_before_fence_or_runtime_access(
    tmp_path: Path,
) -> None:
    harness = _build_harness(tmp_path)
    current = _expected_attestation(harness)
    payload = current.as_dict()
    claims = payload["claims"]
    assert isinstance(claims, dict)
    legacy = create_technical_parser_runtime_attestation(
        engine=TECHNICAL_PARSER_OCI_ENGINE,
        claims=claims,
    )

    with pytest.raises(TechnicalParserExecutionError) as error:
        harness.runner.cleanup_orphan_invocation(
            invocation_id=_INVOCATION_IDS[0],
            operation="layout",
            persisted_runtime_attestation=legacy,
        )

    _assert_execution_code(error, "PARSER_EXECUTION_FAILED")
    assert harness.execution_fence.wait_modes == []
    assert harness.adapter.calls == []


def test_cleanup_rejects_changed_live_daemon_before_container_access(
    tmp_path: Path,
) -> None:
    harness = _build_harness(tmp_path)
    persisted = harness.runner.probe(
        extraction_policy=_POLICY,
        extraction_policy_sha256=_POLICY_SHA256,
    )
    harness.adapter.daemon_id = "ZYXWVUTSRQPONMLKJIHGFEDC98765432"
    harness.adapter.calls.clear()

    with pytest.raises(TechnicalParserExecutionError) as error:
        harness.runner.cleanup_orphan_invocation(
            invocation_id=_INVOCATION_IDS[0],
            operation="layout",
            persisted_runtime_attestation=persisted,
        )

    _assert_execution_code(error, "PARSER_EXECUTION_FAILED")
    assert harness.execution_fence.wait_modes == [True]
    assert not _operation_calls(harness.adapter, "ls")
    assert not _operation_calls(harness.adapter, "rm")
    assert not _operation_calls(harness.adapter, "create")
    assert not _operation_calls(harness.adapter, "start")


def test_cleanup_daemon_switch_during_remove_never_emits_proof_or_finalizes(
    tmp_path: Path,
) -> None:
    harness = _build_harness(tmp_path)
    persisted = _seed_exact_container(harness)
    replacement_daemon = "ZYXWVUTSRQPONMLKJIHGFEDC98765432"
    harness.adapter.after_container_remove = lambda: setattr(
        harness.adapter,
        "daemon_id",
        replacement_daemon,
    )
    finalized: list[TechnicalParserOciCleanupProof] = []

    with pytest.raises(TechnicalParserExecutionError) as error:
        harness.runner.cleanup_orphan_invocation(
            invocation_id=_INVOCATION_IDS[0],
            operation="layout",
            persisted_runtime_attestation=persisted,
            finalize=finalized.append,
        )

    _assert_execution_code(error, "PARSER_EXECUTION_CONTAINMENT_LOST")
    assert finalized == []
    assert len(_operation_calls(harness.adapter, "rm")) == 1
    assert not _operation_calls(harness.adapter, "create")
    assert not _operation_calls(harness.adapter, "start")


def test_layout_and_page_use_fixed_create_contract_and_exact_source_frame(
    tmp_path: Path,
) -> None:
    harness = _build_harness(tmp_path)
    layout_request = _layout_request()
    page_request = _page_request()
    layout_source_name = str(tmp_path / "customer-layout-source.pdf")
    page_source_name = str(tmp_path / "customer-page-source.pdf")

    layout_success = _inspect_layout(
        harness,
        request=layout_request,
        source=_NamedSource(_SOURCE, name=layout_source_name),
    )
    page_success = _extract_page(
        harness,
        request=page_request,
        source=_NamedSource(_SOURCE, name=page_source_name),
    )
    layout_bytes = layout_success.output
    page_bytes = page_success.output

    assert layout_bytes == _layout_output()
    parsed_layout = parse_technical_parser_layout_result(
        layout_bytes,
        expected_technical_document_id=_DOCUMENT_ID,
        expected_source_sha256=_SOURCE_SHA256,
        expected_source_size_bytes=len(_SOURCE),
        expected_extraction_policy=_POLICY,
        expected_extraction_policy_sha256=_POLICY_SHA256,
        expected_worker_image_digest=_WORKER_DIGEST,
    )
    assert isinstance(parsed_layout, TechnicalParserDocumentLayout)
    assert parsed_layout.page_count == 1
    assert page_bytes == _page_output()
    parsed_page = parse_technical_parser_page_frame(
        page_bytes,
        expected_page_number=1,
        expected_page_count=1,
        expected_page_width_points=Decimal(612),
        expected_page_height_points=Decimal(792),
    )
    assert parsed_page.status == "ok"
    for success, operation, invocation_id, expected_output in (
        (layout_success, "layout", _INVOCATION_IDS[0], _layout_output()),
        (page_success, "page", _INVOCATION_IDS[1], _page_output()),
    ):
        receipt = success.receipt
        assert receipt.receipt_schema == TECHNICAL_PARSER_INVOCATION_RECEIPT_SCHEMA
        assert receipt.execution_state == "succeeded"
        assert receipt.operation == operation
        assert receipt.invocation_id == invocation_id
        assert receipt.attestation == _expected_attestation(harness)
        assert receipt.expected_attestation_sha256 == receipt.attestation.sha256
        assert receipt.container_id == _CONTAINER_ID
        assert receipt.exit_code == 0
        assert receipt.stdout_sha256 == hashlib.sha256(expected_output).hexdigest()
        assert receipt.stdout_size_bytes == len(expected_output)
        assert receipt.cleanup_confirmed is True
        assert receipt.started_at is not None
        assert receipt.completed_at >= receipt.started_at
        assert parse_technical_parser_execution_receipt(
            receipt.canonical_json,
            expected_sha256=receipt.sha256,
        ) == receipt

    create_calls = _operation_calls(harness.adapter, "create")
    start_calls = _operation_calls(harness.adapter, "start")
    assert len(create_calls) == len(start_calls) == 2
    for index, (operation, invocation_id, request, source_name) in enumerate(
        (
            ("layout", _INVOCATION_IDS[0], layout_request, layout_source_name),
            ("page", _INVOCATION_IDS[1], page_request, page_source_name),
        )
    ):
        create = create_calls[index]
        runtime_argument = create.args[0]
        runtime_config_argument = create.args[2]
        seccomp_option = next(
            item for item in create.args if item.startswith("--security-opt=seccomp=")
        )
        expected_args = (
            runtime_argument,
            "--config",
            runtime_config_argument,
            "--host",
            _RUNTIME_HOST,
            "container",
            "create",
            "--name",
            f"classifire-parser-{invocation_id}",
            "--label",
            f"{TECHNICAL_PARSER_OCI_INVOCATION_LABEL}={invocation_id}",
            "--label",
            f"{TECHNICAL_PARSER_OCI_OWNER_LABEL}={_CONTROLLER_OWNER_ID}",
            "--pull=never",
            "--platform",
            "linux/amd64",
            "--interactive",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            seccomp_option,
            "--user=65532:65532",
            "--pid=private",
            "--ipc=none",
            "--uts=private",
            "--cgroupns=private",
            "--pids-limit=64",
            f"--memory={1024 * 1024 * 1024}",
            f"--memory-swap={1024 * 1024 * 1024}",
            "--cpus=1.0",
            "--ulimit=nofile=64:64",
            "--ulimit=core=0:0",
            "--tmpfs=/work:rw,noexec,nosuid,nodev,"
            f"size={192 * 1024 * 1024},uid=65532,gid=65532,mode=0700",
            "--workdir=/work",
            "--restart=no",
            "--stop-timeout=1",
            "--log-driver=none",
            f"--entrypoint={TECHNICAL_PARSER_OCI_ENTRYPOINT}",
            _IMAGE_REFERENCE,
            operation,
        )
        assert create.args == expected_args
        assert create.environment == {}
        assert "--env" not in create.args and "-e" not in create.args
        assert source_name not in "\0".join(create.args)
        assert str(harness.runtime_path) not in create.args
        assert str(harness.seccomp_path) not in create.args

        start = start_calls[index]
        assert start.args == (
            runtime_argument,
            "--config",
            runtime_config_argument,
            "--host",
            _RUNTIME_HOST,
            "container",
            "start",
            "--attach",
            "--interactive",
            _CONTAINER_ID,
        )
        assert start.environment == {}
        assert start.stderr_limit == 0
        assert start.timeout_seconds == (30.0 if operation == "layout" else 90.0)
        assert start.stdout_limit == (
            TECHNICAL_PARSER_LAYOUT_MAX_BYTES
            if operation == "layout"
            else 4
            + TECHNICAL_PARSER_HEADER_MAX_BYTES
            + TECHNICAL_PARSER_EVIDENCE_MAX_BYTES
            + TECHNICAL_PARSER_PNG_MAX_BYTES
        )
        assert start.stdin_payload is not None
        request_size = int.from_bytes(start.stdin_payload[:4], "big")
        assert request_size == len(request)
        assert start.stdin_payload[4 : 4 + request_size] == request
        transmitted_source = start.stdin_payload[4 + request_size :]
        assert transmitted_source == _SOURCE
        assert hashlib.sha256(transmitted_source).hexdigest() == _SOURCE_SHA256
        assert source_name.encode() not in start.stdin_payload

    assert len(harness.adapter.seccomp_snapshots) == 2
    for index, seccomp_snapshot in enumerate(harness.adapter.seccomp_snapshots):
        assert seccomp_snapshot.existed_during_create is True
        assert seccomp_snapshot.sha256 == harness.seccomp_sha256
        assert seccomp_snapshot.path != harness.seccomp_path
        assert seccomp_snapshot.path.parent == Path(create_calls[index].args[0]).parent
        assert seccomp_snapshot.path.name == "profile.json"
        assert not seccomp_snapshot.path.exists()
    for runtime_snapshot in harness.adapter.runtime_snapshots:
        assert runtime_snapshot.existed_during_call is True
        assert runtime_snapshot.path.is_absolute()
        assert runtime_snapshot.path != harness.runtime_path
        assert runtime_snapshot.sha256 == harness.runtime_sha256
        assert runtime_snapshot.path.parent.name.startswith("classifire-parser-")
        assert not runtime_snapshot.path.exists()
    assert harness.adapter.runtime_config_snapshots
    for runtime_snapshot, config_snapshot in zip(
        harness.adapter.runtime_snapshots,
        harness.adapter.runtime_config_snapshots,
        strict=True,
    ):
        assert config_snapshot.existed_during_call is True
        assert config_snapshot.path.parent == runtime_snapshot.path.parent
        assert config_snapshot.entries == ("config.json",)
        assert config_snapshot.config_bytes == b"{}"
        assert not config_snapshot.path.exists()
    assert len({snapshot.path for snapshot in harness.adapter.runtime_config_snapshots}) == 2
    assert harness.adapter.containers == {}
    assert len(_operation_calls(harness.adapter, "rm")) >= 2


def test_request_worker_digest_mismatch_fails_before_runtime_access(tmp_path: Path) -> None:
    harness = _build_harness(tmp_path)

    with pytest.raises(TechnicalParserExecutionError) as error:
        _inspect_layout(
            harness,
            request=_layout_request(worker_digest=_OTHER_DIGEST),
            source=BytesIO(_SOURCE),
        )

    _assert_execution_code(error, "PARSER_EXECUTION_FAILED")
    assert harness.adapter.calls == []


@pytest.mark.parametrize(
    "invocation_id",
    [
        "",
        "11111111-1111-1111-8111-111111111111",
        "11111111-1111-4111-8111-11111111111A",
    ],
)
def test_execution_requires_coordinator_supplied_canonical_uuid4(
    tmp_path: Path,
    invocation_id: str,
) -> None:
    harness = _build_harness(tmp_path)

    with pytest.raises(TechnicalParserExecutionError) as error:
        _inspect_layout(harness, invocation_id=invocation_id)

    _assert_execution_code(error, "PARSER_EXECUTION_FAILED")
    assert error.value.receipt is None
    assert harness.adapter.calls == []


def test_attestation_hash_is_rechecked_after_empty_owned_invocation_preflight(
    tmp_path: Path,
) -> None:
    harness = _build_harness(tmp_path)

    with pytest.raises(TechnicalParserExecutionError) as error:
        _inspect_layout(harness, expected_attestation_sha256="0" * 64)

    _assert_execution_code(error, "PARSER_EXECUTION_FAILED")
    receipt = error.value.receipt
    assert receipt is not None
    assert receipt.execution_state == "not_started"
    assert receipt.operation == "layout"
    assert receipt.invocation_id == _INVOCATION_IDS[0]
    assert receipt.expected_attestation_sha256 == "0" * 64
    assert receipt.attestation == _expected_attestation(harness)
    assert receipt.container_id is None
    assert receipt.started_at is None
    assert receipt.cleanup_confirmed is True
    assert parse_technical_parser_execution_receipt(
        receipt.canonical_json,
        expected_sha256=receipt.sha256,
    ) == receipt
    assert not _operation_calls(harness.adapter, "create")
    preflight = _operation_calls(harness.adapter, "ls")[-2:]
    assert [call.args[10:] for call in preflight] == [
        (
            "--filter",
            f"label={TECHNICAL_PARSER_OCI_INVOCATION_LABEL}={_INVOCATION_IDS[0]}",
        ),
        (
            "--filter",
            f"label={TECHNICAL_PARSER_OCI_OWNER_LABEL}={_CONTROLLER_OWNER_ID}",
        ),
    ]


def test_preexisting_owned_invocation_fails_closed_before_create_with_receipt(
    tmp_path: Path,
) -> None:
    adapter = FakeOciRuntimeAdapter()
    preexisting_id = "9" * 64
    adapter.containers[preexisting_id] = {
        "labels": {
            TECHNICAL_PARSER_OCI_OWNER_LABEL: _CONTROLLER_OWNER_ID,
            TECHNICAL_PARSER_OCI_INVOCATION_LABEL: _INVOCATION_IDS[0],
        }
    }
    harness = _build_harness(tmp_path, adapter=adapter)

    with pytest.raises(TechnicalParserExecutionError) as error:
        _inspect_layout(harness)

    _assert_execution_code(error, "PARSER_EXECUTION_CONTAINMENT_LOST")
    receipt = error.value.receipt
    assert receipt is not None
    assert receipt.execution_state == "containment_lost"
    assert receipt.invocation_id == _INVOCATION_IDS[0]
    assert receipt.container_id == preexisting_id
    assert receipt.cleanup_confirmed is False
    assert receipt.attestation == _expected_attestation(harness)
    assert preexisting_id in adapter.containers
    assert not _operation_calls(adapter, "create")


@pytest.mark.parametrize(
    "labels",
    [
        pytest.param(
            {
                TECHNICAL_PARSER_OCI_OWNER_LABEL: _CONTROLLER_OWNER_ID,
                TECHNICAL_PARSER_OCI_INVOCATION_LABEL: _INVOCATION_IDS[1],
            },
            id="same-owner-different-invocation",
        ),
        pytest.param(
            {
                TECHNICAL_PARSER_OCI_OWNER_LABEL: _INVOCATION_IDS[2],
                TECHNICAL_PARSER_OCI_INVOCATION_LABEL: _INVOCATION_IDS[0],
            },
            id="foreign-owner-same-invocation",
        ),
    ],
)
def test_global_preflight_rejects_owned_or_foreign_collision_without_deletion(
    tmp_path: Path,
    labels: dict[str, str],
) -> None:
    adapter = FakeOciRuntimeAdapter()
    collision_id = "9" * 64
    adapter.containers[collision_id] = {"labels": labels}
    harness = _build_harness(tmp_path, adapter=adapter)

    with pytest.raises(TechnicalParserExecutionError) as error:
        _inspect_layout(harness)

    _assert_execution_code(error, "PARSER_EXECUTION_CONTAINMENT_LOST")
    assert collision_id in adapter.containers
    assert not _operation_calls(adapter, "rm")
    assert not _operation_calls(adapter, "create")
    assert not _operation_calls(adapter, "start")


def test_daemon_switch_after_admission_blocks_create_and_finalizes_under_fence(
    tmp_path: Path,
) -> None:
    harness = _build_harness(tmp_path)
    replacement_daemon = "ZYXWVUTSRQPONMLKJIHGFEDC98765432"
    harness.adapter.daemon_id_responses = [
        _DAEMON_ID,
        _DAEMON_ID,
        replacement_daemon,
    ]
    events: list[str] = []
    finalized: list[TechnicalParserExecutionReceipt] = []

    def prepare() -> None:
        assert harness.execution_fence.held is True
        events.append("prepare")

    def authorize() -> None:
        assert harness.execution_fence.held is True
        events.append("authorize")

    def finalize(receipt: TechnicalParserExecutionReceipt) -> None:
        assert harness.execution_fence.held is True
        events.append("finalize")
        finalized.append(receipt)

    with pytest.raises(TechnicalParserExecutionError) as error:
        _inspect_layout(
            harness,
            prepare=prepare,
            authorize=authorize,
            finalize=finalize,
        )

    _assert_execution_code(error, "PARSER_EXECUTION_CONTAINMENT_LOST")
    assert events == ["prepare", "authorize", "finalize"]
    assert finalized == [error.value.receipt]
    assert finalized[0].cleanup_confirmed is False
    assert not _operation_calls(harness.adapter, "create")
    assert not _operation_calls(harness.adapter, "start")


def test_collision_injected_during_admission_is_rejected_without_deletion(
    tmp_path: Path,
) -> None:
    harness = _build_harness(tmp_path)
    collision_id = "9" * 64
    finalized: list[TechnicalParserExecutionReceipt] = []

    def authorize() -> None:
        harness.adapter.containers[collision_id] = {
            "labels": {
                TECHNICAL_PARSER_OCI_OWNER_LABEL: _INVOCATION_IDS[2],
                TECHNICAL_PARSER_OCI_INVOCATION_LABEL: _INVOCATION_IDS[0],
            }
        }

    with pytest.raises(TechnicalParserExecutionError) as error:
        _inspect_layout(
            harness,
            prepare=lambda: None,
            authorize=authorize,
            finalize=finalized.append,
        )

    _assert_execution_code(error, "PARSER_EXECUTION_CONTAINMENT_LOST")
    assert finalized == [error.value.receipt]
    assert collision_id in harness.adapter.containers
    assert not _operation_calls(harness.adapter, "rm")
    assert not _operation_calls(harness.adapter, "create")
    assert not _operation_calls(harness.adapter, "start")


def test_create_ack_loss_never_deletes_foreign_label_candidate(
    tmp_path: Path,
) -> None:
    adapter = FakeOciRuntimeAdapter()
    adapter.create_behavior = "ack_lost"
    adapter.container_label_overrides = {
        TECHNICAL_PARSER_OCI_OWNER_LABEL: _INVOCATION_IDS[2]
    }
    harness = _build_harness(tmp_path, adapter=adapter)

    with pytest.raises(TechnicalParserExecutionError) as error:
        _inspect_layout(harness)

    _assert_execution_code(error, "PARSER_EXECUTION_CONTAINMENT_LOST")
    assert _CONTAINER_ID in adapter.containers
    assert not _operation_calls(adapter, "rm")
    assert not _operation_calls(adapter, "start")


@pytest.mark.parametrize(
    ("mismatch", "expected_code", "container_created"),
    [
        ("repo_digest", "PARSER_EXECUTION_UNAVAILABLE", False),
        ("policy", "PARSER_EXECUTION_UNAVAILABLE", False),
        ("image", "PARSER_EXECUTION_CONTAINMENT_LOST", True),
        ("owner", "PARSER_EXECUTION_CONTAINMENT_LOST", True),
        ("profile", "PARSER_EXECUTION_CONTAINMENT_LOST", True),
    ],
)
def test_attestation_or_unverified_created_container_mismatch_fails_closed(
    tmp_path: Path,
    mismatch: str,
    expected_code: str,
    container_created: bool,
) -> None:
    adapter = FakeOciRuntimeAdapter()
    if mismatch == "repo_digest":
        adapter.repo_digests = [f"registry.example/classifire/parser@sha256:{_OTHER_DIGEST}"]
    elif mismatch == "policy":
        adapter.image_policy = "different-policy"
    elif mismatch == "image":
        adapter.container_image_id = f"sha256:{'1' * 64}"
    elif mismatch == "owner":
        adapter.container_label_overrides = {
            TECHNICAL_PARSER_OCI_OWNER_LABEL: _INVOCATION_IDS[2]
        }
    elif mismatch == "profile":
        adapter.host_patch = {"NetworkMode": "bridge"}
    harness = _build_harness(tmp_path, adapter=adapter)

    with pytest.raises(TechnicalParserExecutionError) as error:
        _inspect_layout(harness)

    _assert_execution_code(error, expected_code)
    assert bool(_operation_calls(adapter, "create")) is container_created
    if container_created:
        receipt = error.value.receipt
        assert receipt is not None
        assert receipt.execution_state == "containment_lost"
        assert receipt.invocation_id == _INVOCATION_IDS[0]
        assert receipt.container_id is None
        assert receipt.cleanup_confirmed is False
        assert _CONTAINER_ID in adapter.containers
        assert not _operation_calls(adapter, "rm")
        assert not _operation_calls(adapter, "start")
    else:
        assert adapter.containers == {}


@pytest.mark.parametrize(
    ("field", "malformed_value"),
    [
        ("SecurityOpt", {"seccomp": "unexpected-mapping"}),
        ("CapDrop", [["ALL"]]),
        ("Tmpfs", []),
        ("RestartPolicy", "no"),
        ("LogConfig", ["none"]),
        ("ReadonlyRootfs", "true"),
    ],
)
def test_malformed_host_config_types_quarantine_without_unverified_cleanup(
    tmp_path: Path,
    field: str,
    malformed_value: object,
) -> None:
    adapter = FakeOciRuntimeAdapter()
    adapter.host_patch = {field: malformed_value}
    harness = _build_harness(tmp_path, adapter=adapter)

    with pytest.raises(TechnicalParserExecutionError) as error:
        _inspect_layout(harness)

    _assert_execution_code(error, "PARSER_EXECUTION_CONTAINMENT_LOST")
    assert _CONTAINER_ID in adapter.containers
    assert not _operation_calls(adapter, "rm")
    assert not _operation_calls(adapter, "start")


@pytest.mark.parametrize(
    "ulimits",
    [
        pytest.param(
            [{"Hard": 64, "Name": "nofile", "Soft": 64}],
            id="missing-core",
        ),
        pytest.param(
            [
                {"Hard": 64, "Name": "nofile", "Soft": 64},
                {"Hard": 0, "Name": "core", "Soft": 0},
                {"Hard": 0, "Name": "core", "Soft": 0},
            ],
            id="extra-entry",
        ),
        pytest.param(
            [
                {"Hard": 64, "Name": "nofile", "Soft": 64},
                {"Hard": 64, "Name": "nofile", "Soft": 64},
            ],
            id="duplicate-nofile",
        ),
        pytest.param(
            [
                {"Hard": 64, "Name": "nofile", "Soft": [64]},
                {"Hard": 0, "Name": "core", "Soft": 0},
            ],
            id="unhashable-soft-value",
        ),
        pytest.param(
            [
                {"Hard": [64], "Name": "nofile", "Soft": 64},
                {"Hard": 0, "Name": "core", "Soft": 0},
            ],
            id="unhashable-hard-value",
        ),
    ],
)
def test_host_config_requires_exact_ulimits_without_unverified_cleanup(
    tmp_path: Path,
    ulimits: object,
) -> None:
    adapter = FakeOciRuntimeAdapter()
    adapter.host_patch = {"Ulimits": ulimits}
    harness = _build_harness(tmp_path, adapter=adapter)

    with pytest.raises(TechnicalParserExecutionError) as error:
        _inspect_layout(harness)

    _assert_execution_code(error, "PARSER_EXECUTION_CONTAINMENT_LOST")
    assert _CONTAINER_ID in adapter.containers
    assert not _operation_calls(adapter, "rm")
    assert not _operation_calls(adapter, "start")


@pytest.mark.parametrize(
    ("create_behavior", "expected_code", "trips_circuit_breaker"),
    [
        ("ack_lost", "PARSER_EXECUTION_CONTAINMENT_LOST", True),
        ("malformed_ack", "PARSER_EXECUTION_FAILED", False),
        ("nonzero", "PARSER_EXECUTION_UNAVAILABLE", False),
    ],
)
def test_create_acknowledgement_failure_reconciles_and_removes_labelled_container(
    tmp_path: Path,
    create_behavior: str,
    expected_code: str,
    trips_circuit_breaker: bool,
) -> None:
    adapter = FakeOciRuntimeAdapter()
    adapter.create_behavior = create_behavior
    harness = _build_harness(tmp_path, adapter=adapter)

    with pytest.raises(TechnicalParserExecutionError) as error:
        _inspect_layout(harness)

    _assert_execution_code(error, expected_code)
    assert adapter.containers == {}
    assert len(_operation_calls(adapter, "create")) == 1
    assert not _operation_calls(adapter, "start")
    assert _operation_calls(adapter, "rm")
    list_filters = [call.args[-1] for call in _operation_calls(adapter, "ls")]
    assert any(value.startswith("label=") for value in list_filters)
    assert f"id={_CONTAINER_ID}" in list_filters
    calls_after_reconciliation = len(adapter.calls)
    if trips_circuit_breaker:
        receipt = error.value.receipt
        assert receipt is not None
        assert receipt.execution_state == "containment_lost"
        assert receipt.invocation_id == _INVOCATION_IDS[0]
        assert receipt.container_id == _CONTAINER_ID
        assert receipt.started_at is None
        assert receipt.cleanup_confirmed is False
        assert parse_technical_parser_execution_receipt(
            receipt.canonical_json,
            expected_sha256=receipt.sha256,
        ) == receipt
        with pytest.raises(TechnicalParserExecutionError) as circuit_error:
            harness.runner.probe(
                extraction_policy=_POLICY,
                extraction_policy_sha256=_POLICY_SHA256,
            )
        _assert_execution_code(circuit_error, "PARSER_EXECUTION_CONTAINMENT_LOST")
        assert len(adapter.calls) == calls_after_reconciliation
    else:
        receipt = error.value.receipt
        assert receipt is not None
        assert receipt.execution_state == "not_started"
        assert receipt.invocation_id == _INVOCATION_IDS[0]
        assert receipt.container_id is None
        assert receipt.cleanup_confirmed is True


@pytest.mark.parametrize(
    ("interrupt", "expected_type"),
    [
        (KeyboardInterrupt(), KeyboardInterrupt),
        (SystemExit(23), SystemExit),
    ],
)
def test_post_create_interrupt_propagates_without_unverified_deletion(
    tmp_path: Path,
    interrupt: BaseException,
    expected_type: type[BaseException],
) -> None:
    adapter = FakeOciRuntimeAdapter()
    adapter.container_inspect_interrupt = interrupt
    harness = _build_harness(tmp_path, adapter=adapter)

    with pytest.raises(expected_type) as error:
        _inspect_layout(harness)

    assert error.value is interrupt
    assert _CONTAINER_ID in adapter.containers
    assert not _operation_calls(adapter, "rm")
    assert not _operation_calls(adapter, "start")


def test_unverified_interrupt_is_never_converted_when_cleanup_is_unavailable(
    tmp_path: Path,
) -> None:
    adapter = FakeOciRuntimeAdapter()
    adapter.container_inspect_interrupt = KeyboardInterrupt()
    adapter.cleanup_stuck = True
    harness = _build_harness(tmp_path, adapter=adapter)

    with pytest.raises(KeyboardInterrupt):
        _inspect_layout(harness)

    assert _CONTAINER_ID in adapter.containers
    assert not _operation_calls(adapter, "rm")


@pytest.mark.parametrize(
    ("start_error", "expected_code"),
    [
        ("timeout", "PARSER_EXECUTION_TIMEOUT"),
        ("stdout_overflow", "PARSER_EXECUTION_OUTPUT_OVERFLOW"),
        ("stderr_output", "PARSER_EXECUTION_FAILED"),
    ],
)
def test_parser_timeout_or_output_failure_terminates_and_verifies_cleanup(
    tmp_path: Path,
    start_error: str,
    expected_code: str,
) -> None:
    adapter = FakeOciRuntimeAdapter()
    adapter.start_error = start_error
    harness = _build_harness(tmp_path, adapter=adapter)

    with pytest.raises(TechnicalParserExecutionError) as error:
        _inspect_layout(harness)

    _assert_execution_code(error, expected_code)
    receipt = error.value.receipt
    assert receipt is not None
    assert receipt.execution_state == "failed"
    assert receipt.operation == "layout"
    assert receipt.invocation_id == _INVOCATION_IDS[0]
    assert receipt.expected_attestation_sha256 == receipt.attestation.sha256
    assert receipt.container_id == _CONTAINER_ID
    assert receipt.started_at is not None
    assert receipt.completed_at >= receipt.started_at
    assert receipt.exit_code is None
    assert receipt.stdout_sha256 is None
    assert receipt.stdout_size_bytes is None
    assert receipt.cleanup_confirmed is True
    start = _operation_calls(adapter, "start")[0]
    assert start.has_termination_callback is True
    assert start.stderr_limit == 0
    assert adapter.containers == {}
    assert _operation_calls(adapter, "rm")
    assert f"id={_CONTAINER_ID}" in [call.args[-1] for call in _operation_calls(adapter, "ls")]


def test_cleanup_timeout_is_propagated_and_changes_runtime_profile_digest(
    tmp_path: Path,
) -> None:
    first_profile = TechnicalParserOciRuntimeProfile(
        platform="linux/amd64",
        control_timeout_seconds=3.25,
        cleanup_timeout_seconds=4.5,
    )
    first = _build_harness(tmp_path / "first", profile=first_profile)
    second = _build_harness(
        tmp_path / "second",
        profile=TechnicalParserOciRuntimeProfile(
            platform="linux/amd64",
            control_timeout_seconds=3.25,
            cleanup_timeout_seconds=4.75,
        ),
    )

    assert first.runner.runtime_profile_sha256 != second.runner.runtime_profile_sha256
    assert (
        _inspect_layout(first).output == _layout_output()
    )

    remove_calls = _operation_calls(first.adapter, "rm")
    id_confirmation_calls = [
        call for call in _operation_calls(first.adapter, "ls") if call.args[-1].startswith("id=")
    ]
    label_calls = [
        call for call in _operation_calls(first.adapter, "ls") if call.args[-1].startswith("label=")
    ]
    assert remove_calls and id_confirmation_calls
    assert all(call.timeout_seconds == 4.5 for call in remove_calls)
    assert all(call.timeout_seconds == 4.5 for call in id_confirmation_calls)
    assert label_calls
    assert all(call.timeout_seconds == 4.5 for call in label_calls)


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(BytesIO(_SOURCE + b"changed"), id="changed-size"),
        pytest.param(_UnreadableSource(_SOURCE), id="read-failure"),
    ],
)
def test_source_failure_is_path_free_and_container_is_removed(
    tmp_path: Path,
    source: BinaryIO,
) -> None:
    adapter = FakeOciRuntimeAdapter()
    harness = _build_harness(tmp_path, adapter=adapter)

    with pytest.raises(TechnicalParserExecutionError) as error:
        _inspect_layout(harness, source=source)

    _assert_execution_code(error, "PARSER_EXECUTION_SOURCE_INVALID")
    assert "path-bearing" not in str(error.value)
    assert adapter.containers == {}
    assert _operation_calls(adapter, "rm")


def test_unverified_cleanup_trips_permanent_containment_loss_circuit_breaker(
    tmp_path: Path,
) -> None:
    adapter = FakeOciRuntimeAdapter()
    adapter.start_error = "timeout"
    adapter.cleanup_stuck = True
    harness = _build_harness(tmp_path, adapter=adapter)

    with pytest.raises(TechnicalParserExecutionError) as first_error:
        _inspect_layout(harness)

    _assert_execution_code(first_error, "PARSER_EXECUTION_CONTAINMENT_LOST")
    receipt = first_error.value.receipt
    assert receipt is not None
    assert receipt.execution_state == "containment_lost"
    assert receipt.invocation_id == _INVOCATION_IDS[0]
    assert receipt.container_id == _CONTAINER_ID
    assert receipt.started_at is not None
    assert receipt.cleanup_confirmed is False
    assert parse_technical_parser_execution_receipt(
        receipt.canonical_json,
        expected_sha256=receipt.sha256,
    ) == receipt
    assert _CONTAINER_ID in adapter.containers
    calls_after_loss = len(adapter.calls)

    with pytest.raises(TechnicalParserExecutionError) as second_error:
        harness.runner.probe(
            extraction_policy=_POLICY,
            extraction_policy_sha256=_POLICY_SHA256,
        )

    _assert_execution_code(second_error, "PARSER_EXECUTION_CONTAINMENT_LOST")
    assert len(adapter.calls) == calls_after_loss


def test_thread_start_failure_invokes_cleanup_and_reports_termination_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeProcess:
        def __init__(self) -> None:
            self.stdout = BytesIO()
            self.stderr = BytesIO()
            self.stdin = None

        def wait(self, *, timeout: float) -> int:
            del timeout
            raise AssertionError("process wait must not run after thread-start failure")

    class _StartFailingThread:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def start(self) -> None:
            raise RuntimeError("thread start failed")

        def join(self, *, timeout: float) -> None:
            del timeout

        def is_alive(self) -> bool:
            return False

    process = _FakeProcess()
    cleanup_calls: list[str] = []
    termination_calls: list[_FakeProcess] = []

    def cleanup() -> None:
        cleanup_calls.append("called")
        raise RuntimeError("container cleanup was not confirmed")

    def terminate(candidate: _FakeProcess) -> bool:
        termination_calls.append(candidate)
        return True

    monkeypatch.setattr(technical_parser_oci.threading, "Thread", _StartFailingThread)
    monkeypatch.setattr(technical_parser_oci, "_terminate_process_tree", terminate)

    with pytest.raises(_BoundedCommandError) as error:
        _SubprocessOciRuntimeAdapter._communicate_bounded(
            process,  # type: ignore[arg-type]
            args=("runtime",),
            stdin_writer=None,
            timeout_seconds=1.0,
            stdout_limit=1,
            stderr_limit=0,
            on_terminate=cleanup,
        )

    assert error.value.kind == "termination_failed"
    assert cleanup_calls == ["called"]
    assert termination_calls == [process]
