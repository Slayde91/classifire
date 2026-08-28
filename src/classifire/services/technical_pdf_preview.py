from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess  # nosec B404
import sys
import tempfile
import threading
import zlib
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Protocol, cast

from .storage import VerifiedStoredFileStream

TECHNICAL_PDF_PREVIEW_POLICY = "technical-pdf-preview-v1"
TECHNICAL_PDF_PREVIEW_DPI = 144
TECHNICAL_PDF_PREVIEW_MAX_SOURCE_BYTES = 100 * 1024 * 1024
TECHNICAL_PDF_PREVIEW_MAX_PAGES = 500
TECHNICAL_PDF_PREVIEW_MAX_EDGE_PIXELS = 4096
TECHNICAL_PDF_PREVIEW_MAX_PIXELS = 8_000_000
TECHNICAL_PDF_PREVIEW_MAX_PNG_BYTES = 25 * 1024 * 1024
TECHNICAL_PDF_PREVIEW_TIMEOUT_SECONDS = 15.0
TECHNICAL_PDF_PREVIEW_CONCURRENCY = 2

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_HEX_SHA256 = frozenset("0123456789abcdef")
_MAX_WORKER_METADATA_BYTES = 4096
_RENDERER_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
_WORKER_ERROR_CODES = frozenset(
    {
        "PREVIEW_DOCUMENT_ENCRYPTED",
        "PREVIEW_DOCUMENT_INVALID",
        "PREVIEW_INPUT_INVALID",
        "PREVIEW_OUTPUT_TOO_LARGE",
        "PREVIEW_PAGE_COUNT_INVALID",
        "PREVIEW_PAGE_DIMENSIONS_INVALID",
        "PREVIEW_PAGE_NOT_FOUND",
        "PREVIEW_RENDER_FAILED",
        "PREVIEW_RENDERER_UNAVAILABLE",
        "PREVIEW_SOURCE_BINDING_MISMATCH",
        "PREVIEW_SOURCE_TOO_LARGE",
    }
)
_preview_slots = threading.BoundedSemaphore(TECHNICAL_PDF_PREVIEW_CONCURRENCY)


class PreviewRunner(Protocol):
    def __call__(
        self,
        args: Sequence[str],
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[bytes]: ...


class TechnicalPdfPreviewError(RuntimeError):
    """Stable, path-free failure at the untrusted PDF rendering boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class TechnicalPdfPreview:
    png_bytes: bytes
    source_sha256: str
    source_size_bytes: int
    page_number: int
    page_count: int
    width_pixels: int
    height_pixels: int
    png_sha256: str
    renderer: str
    renderer_version: str
    policy_version: str
    binding_sha256: str


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _strict_json(raw: bytes) -> dict[str, object]:
    if not raw or len(raw) > _MAX_WORKER_METADATA_BYTES:
        raise TechnicalPdfPreviewError("PREVIEW_WORKER_OUTPUT_INVALID")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non-finite")),
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        raise TechnicalPdfPreviewError("PREVIEW_WORKER_OUTPUT_INVALID") from None
    if not isinstance(value, dict):
        raise TechnicalPdfPreviewError("PREVIEW_WORKER_OUTPUT_INVALID")
    return cast(dict[str, object], value)


def _exact_keys(value: Mapping[str, object], expected: set[str]) -> None:
    if set(value) != expected:
        raise TechnicalPdfPreviewError("PREVIEW_WORKER_OUTPUT_INVALID")


def _integer(value: object, *, minimum: int, maximum: int) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < minimum
        or value > maximum
    ):
        raise TechnicalPdfPreviewError("PREVIEW_WORKER_OUTPUT_INVALID")
    return value


def _sha256(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HEX_SHA256 for character in value)
    ):
        raise TechnicalPdfPreviewError("PREVIEW_WORKER_OUTPUT_INVALID")
    return value


def _safe_renderer_version(value: object) -> str:
    if not isinstance(value, str) or _RENDERER_VERSION.fullmatch(value) is None:
        raise TechnicalPdfPreviewError("PREVIEW_WORKER_OUTPUT_INVALID")
    return value


def _worker_environment() -> dict[str, str]:
    allowed = (
        "SystemRoot",
        "WINDIR",
        "PATH",
        "TEMP",
        "TMP",
        "TMPDIR",
        "LANG",
        "LC_ALL",
    )
    environment = {key: os.environ[key] for key in allowed if os.environ.get(key)}
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONUTF8"] = "1"
    return environment


def _binding_sha256(metadata: Mapping[str, object]) -> str:
    payload = json.dumps(
        dict(metadata),
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _png_ihdr_dimensions(png_bytes: bytes) -> tuple[int, int]:
    if (
        len(png_bytes) < 33
        or png_bytes[:8] != _PNG_SIGNATURE
        or int.from_bytes(png_bytes[8:12], "big") != 13
        or png_bytes[12:16] != b"IHDR"
    ):
        raise TechnicalPdfPreviewError("PREVIEW_WORKER_OUTPUT_INVALID")
    expected_crc = int.from_bytes(png_bytes[29:33], "big")
    actual_crc = zlib.crc32(png_bytes[12:29]) & 0xFFFFFFFF
    if actual_crc != expected_crc:
        raise TechnicalPdfPreviewError("PREVIEW_WORKER_OUTPUT_INVALID")
    width = int.from_bytes(png_bytes[16:20], "big")
    height = int.from_bytes(png_bytes[20:24], "big")
    if width <= 0 or height <= 0:
        raise TechnicalPdfPreviewError("PREVIEW_WORKER_OUTPUT_INVALID")
    return width, height


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        system_root = Path(os.environ.get("SystemRoot") or r"C:\Windows").resolve()
        taskkill = system_root / "System32" / "taskkill.exe"
        if taskkill.is_file():
            try:
                subprocess.run(  # noqa: S603  # nosec B603
                    (str(taskkill), "/PID", str(process.pid), "/T", "/F"),
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except (OSError, subprocess.SubprocessError):
                pass
    else:
        kill_process_group = getattr(os, "killpg", None)
        sigkill = getattr(signal, "SIGKILL", None)
        if callable(kill_process_group) and isinstance(sigkill, int):
            try:
                kill_process_group(process.pid, sigkill)
            except (OSError, ProcessLookupError):
                pass
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _run_bounded_worker(
    args: Sequence[str],
    *,
    stdin: BinaryIO,
    cwd: str,
    env: Mapping[str, str],
    creationflags: int,
) -> subprocess.CompletedProcess[bytes]:
    output_limit = (
        TECHNICAL_PDF_PREVIEW_MAX_PNG_BYTES + _MAX_WORKER_METADATA_BYTES + 1
    )
    process = subprocess.Popen(  # noqa: S603  # nosec B603
        args,
        stdin=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=cwd,
        env=dict(env),
        creationflags=creationflags,
        start_new_session=os.name != "nt",
    )
    stdout = process.stdout
    if stdout is None:
        _terminate_process_tree(process)
        raise TechnicalPdfPreviewError("PREVIEW_RENDERER_UNAVAILABLE")

    output = bytearray()
    overflow = threading.Event()
    capture_failed = threading.Event()

    def capture_stdout() -> None:
        try:
            while True:
                remaining = output_limit - len(output)
                chunk = stdout.read(min(64 * 1024, max(1, remaining + 1)))
                if not chunk:
                    return
                if len(chunk) > remaining:
                    output.extend(chunk[:remaining])
                    overflow.set()
                    _terminate_process_tree(process)
                    return
                output.extend(chunk)
        except (OSError, ValueError):
            capture_failed.set()
            _terminate_process_tree(process)
        finally:
            stdout.close()

    capture_thread = threading.Thread(
        target=capture_stdout,
        name="classifire-pdf-preview-output",
        daemon=True,
    )
    capture_thread.start()
    timed_out = False
    try:
        process.wait(timeout=TECHNICAL_PDF_PREVIEW_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_tree(process)
    finally:
        capture_thread.join(timeout=2)
        if capture_thread.is_alive():
            _terminate_process_tree(process)
            capture_thread.join(timeout=2)

    if timed_out:
        raise subprocess.TimeoutExpired(args, TECHNICAL_PDF_PREVIEW_TIMEOUT_SECONDS)
    if capture_thread.is_alive() or capture_failed.is_set() or overflow.is_set():
        raise TechnicalPdfPreviewError("PREVIEW_WORKER_OUTPUT_INVALID")
    return subprocess.CompletedProcess(
        args,
        process.returncode if process.returncode is not None else -1,
        bytes(output),
        None,
    )


@contextmanager
def _preview_capacity() -> Iterator[None]:
    if not _preview_slots.acquire(blocking=False):
        raise TechnicalPdfPreviewError("PREVIEW_BUSY")
    try:
        yield
    finally:
        _preview_slots.release()


def _worker_error(stdout: object) -> str:
    if not isinstance(stdout, bytes):
        return "PREVIEW_RENDER_FAILED"
    line = stdout.split(b"\n", 1)[0]
    try:
        value = _strict_json(line)
    except TechnicalPdfPreviewError:
        return "PREVIEW_RENDER_FAILED"
    if set(value) != {"code", "ok"} or value.get("ok") is not False:
        return "PREVIEW_RENDER_FAILED"
    code = value.get("code")
    return (
        code
        if isinstance(code, str) and code in _WORKER_ERROR_CODES
        else "PREVIEW_RENDER_FAILED"
    )


def _parse_success(
    stdout: object,
    *,
    expected_source_sha256: str,
    expected_source_size_bytes: int,
    expected_page_number: int,
) -> TechnicalPdfPreview:
    if not isinstance(stdout, bytes) or len(stdout) > (
        TECHNICAL_PDF_PREVIEW_MAX_PNG_BYTES + _MAX_WORKER_METADATA_BYTES + 1
    ):
        raise TechnicalPdfPreviewError("PREVIEW_WORKER_OUTPUT_INVALID")
    metadata_raw, separator, png_bytes = stdout.partition(b"\n")
    if not separator:
        raise TechnicalPdfPreviewError("PREVIEW_WORKER_OUTPUT_INVALID")
    metadata = _strict_json(metadata_raw)
    _exact_keys(
        metadata,
        {
            "height_pixels",
            "ok",
            "page_count",
            "page_number",
            "png_sha256",
            "policy_version",
            "renderer",
            "renderer_version",
            "source_sha256",
            "source_size_bytes",
            "width_pixels",
        },
    )
    if metadata.get("ok") is not True:
        raise TechnicalPdfPreviewError("PREVIEW_WORKER_OUTPUT_INVALID")
    if metadata.get("policy_version") != TECHNICAL_PDF_PREVIEW_POLICY:
        raise TechnicalPdfPreviewError("PREVIEW_WORKER_OUTPUT_INVALID")
    if metadata.get("renderer") != "PyMuPDF":
        raise TechnicalPdfPreviewError("PREVIEW_WORKER_OUTPUT_INVALID")
    source_sha256 = _sha256(metadata.get("source_sha256"))
    source_size_bytes = _integer(
        metadata.get("source_size_bytes"),
        minimum=1,
        maximum=TECHNICAL_PDF_PREVIEW_MAX_SOURCE_BYTES,
    )
    png_sha256 = _sha256(metadata.get("png_sha256"))
    page_number = _integer(
        metadata.get("page_number"),
        minimum=1,
        maximum=TECHNICAL_PDF_PREVIEW_MAX_PAGES,
    )
    page_count = _integer(
        metadata.get("page_count"),
        minimum=1,
        maximum=TECHNICAL_PDF_PREVIEW_MAX_PAGES,
    )
    width_pixels = _integer(
        metadata.get("width_pixels"),
        minimum=1,
        maximum=TECHNICAL_PDF_PREVIEW_MAX_EDGE_PIXELS,
    )
    height_pixels = _integer(
        metadata.get("height_pixels"),
        minimum=1,
        maximum=TECHNICAL_PDF_PREVIEW_MAX_EDGE_PIXELS,
    )
    renderer_version = _safe_renderer_version(metadata.get("renderer_version"))
    actual_width, actual_height = _png_ihdr_dimensions(png_bytes)
    if (
        source_sha256 != expected_source_sha256
        or source_size_bytes != expected_source_size_bytes
        or page_number != expected_page_number
        or page_number > page_count
        or width_pixels * height_pixels > TECHNICAL_PDF_PREVIEW_MAX_PIXELS
        or actual_width != width_pixels
        or actual_height != height_pixels
        or not png_bytes
        or len(png_bytes) > TECHNICAL_PDF_PREVIEW_MAX_PNG_BYTES
        or hashlib.sha256(png_bytes).hexdigest() != png_sha256
    ):
        raise TechnicalPdfPreviewError("PREVIEW_WORKER_OUTPUT_INVALID")
    binding = {
        "height_pixels": height_pixels,
        "page_count": page_count,
        "page_number": page_number,
        "png_sha256": png_sha256,
        "policy_version": TECHNICAL_PDF_PREVIEW_POLICY,
        "renderer": "PyMuPDF",
        "renderer_version": renderer_version,
        "source_sha256": source_sha256,
        "source_size_bytes": source_size_bytes,
        "width_pixels": width_pixels,
    }
    return TechnicalPdfPreview(
        png_bytes=png_bytes,
        source_sha256=source_sha256,
        source_size_bytes=source_size_bytes,
        page_number=page_number,
        page_count=page_count,
        width_pixels=width_pixels,
        height_pixels=height_pixels,
        png_sha256=png_sha256,
        renderer="PyMuPDF",
        renderer_version=renderer_version,
        policy_version=TECHNICAL_PDF_PREVIEW_POLICY,
        binding_sha256=_binding_sha256(binding),
    )


def _render_technical_pdf_preview_reserved(
    stream: VerifiedStoredFileStream,
    *,
    page_number: int,
    runner: PreviewRunner | None = None,
    worker_path: Path | None = None,
    interpreter_path: Path | None = None,
) -> TechnicalPdfPreview:
    if (
        not isinstance(page_number, int)
        or isinstance(page_number, bool)
        or not 1 <= page_number <= TECHNICAL_PDF_PREVIEW_MAX_PAGES
    ):
        raise TechnicalPdfPreviewError("PREVIEW_PAGE_NOT_FOUND")
    binding = stream.binding
    if (
        binding.purpose != "technical_evidence"
        or binding.suffix != ".pdf"
        or binding.size_bytes <= 0
    ):
        raise TechnicalPdfPreviewError("PREVIEW_FILE_TYPE_UNSUPPORTED")
    if binding.size_bytes > TECHNICAL_PDF_PREVIEW_MAX_SOURCE_BYTES:
        raise TechnicalPdfPreviewError("PREVIEW_SOURCE_TOO_LARGE")
    source_sha256 = _sha256(binding.sha256)
    executable = (interpreter_path or Path(sys.executable)).resolve()
    worker = (worker_path or Path(__file__).with_name("technical_pdf_preview_worker.py")).resolve()
    if not executable.is_file() or not worker.is_file():
        raise TechnicalPdfPreviewError("PREVIEW_RENDERER_UNAVAILABLE")
    command = (
        str(executable),
        "-I",
        "-B",
        "-s",
        str(worker),
        str(page_number),
        str(binding.size_bytes),
        source_sha256,
    )
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        reader = stream.claim_binary_reader()
    except (RuntimeError, OSError):
        raise TechnicalPdfPreviewError("PREVIEW_SOURCE_INVALID") from None
    try:
        with reader, tempfile.TemporaryDirectory(prefix="classifire-pdf-preview-") as working:
            if runner is None:
                completed = _run_bounded_worker(
                    command,
                    stdin=reader,
                    cwd=working,
                    env=_worker_environment(),
                    creationflags=creation_flags,
                )
            else:
                completed = runner(
                    command,
                    stdin=reader,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=TECHNICAL_PDF_PREVIEW_TIMEOUT_SECONDS,
                    check=False,
                    cwd=working,
                    env=_worker_environment(),
                    creationflags=creation_flags,
                    start_new_session=os.name != "nt",
                )
    except subprocess.TimeoutExpired:
        raise TechnicalPdfPreviewError("PREVIEW_TIMEOUT") from None
    except (OSError, subprocess.SubprocessError):
        raise TechnicalPdfPreviewError("PREVIEW_RENDERER_UNAVAILABLE") from None
    if completed.returncode != 0:
        raise TechnicalPdfPreviewError(_worker_error(completed.stdout))
    return _parse_success(
        completed.stdout,
        expected_source_sha256=source_sha256,
        expected_source_size_bytes=binding.size_bytes,
        expected_page_number=page_number,
    )


def render_technical_pdf_preview(
    stream: VerifiedStoredFileStream,
    *,
    page_number: int,
    runner: PreviewRunner | None = None,
    worker_path: Path | None = None,
    interpreter_path: Path | None = None,
) -> TechnicalPdfPreview:
    """Render one source-bound PDF page without parsing in the web process."""

    with _preview_capacity():
        return _render_technical_pdf_preview_reserved(
            stream,
            page_number=page_number,
            runner=runner,
            worker_path=worker_path,
            interpreter_path=interpreter_path,
        )


def render_technical_pdf_preview_from_factory(
    stream_factory: Callable[[], VerifiedStoredFileStream],
    *,
    page_number: int,
) -> TechnicalPdfPreview:
    """Reserve capacity before opening and hashing retained source evidence."""

    with _preview_capacity():
        stream = stream_factory()
        try:
            return _render_technical_pdf_preview_reserved(
                stream,
                page_number=page_number,
            )
        finally:
            stream.close()


__all__ = [
    "TECHNICAL_PDF_PREVIEW_MAX_PAGES",
    "TECHNICAL_PDF_PREVIEW_POLICY",
    "TechnicalPdfPreview",
    "TechnicalPdfPreviewError",
    "render_technical_pdf_preview",
    "render_technical_pdf_preview_from_factory",
]
