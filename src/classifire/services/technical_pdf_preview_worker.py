from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, cast

POLICY_VERSION = "technical-pdf-preview-v1"
RENDER_DPI = 144
MAX_SOURCE_BYTES = 100 * 1024 * 1024
MAX_PAGES = 500
MAX_EDGE_PIXELS = 4096
MAX_PIXELS = 8_000_000
MAX_PNG_BYTES = 25 * 1024 * 1024
_CHUNK_BYTES = 1024 * 1024
_HEX_SHA256 = frozenset("0123456789abcdef")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _emit(value: dict[str, object], payload: bytes = b"") -> None:
    metadata = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    sys.stdout.buffer.write(metadata + b"\n" + payload)
    sys.stdout.buffer.flush()


def _fail(code: str) -> int:
    try:
        _emit({"code": code, "ok": False})
    except OSError:
        pass
    return 2


def _positive_integer(value: str, *, maximum: int) -> int | None:
    if not value.isascii() or not value.isdecimal():
        return None
    parsed = int(value)
    return parsed if 1 <= parsed <= maximum else None


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in _HEX_SHA256 for character in value)


def _apply_posix_resource_limits() -> None:
    try:
        import resource
    except ImportError:
        return
    resource_api = cast(Any, resource)
    limits = (
        (resource_api.RLIMIT_AS, 1024 * 1024 * 1024),
        (resource_api.RLIMIT_CPU, 15),
        (
            resource_api.RLIMIT_FSIZE,
            MAX_SOURCE_BYTES + MAX_PNG_BYTES,
        ),
        (resource_api.RLIMIT_NOFILE, 64),
    )
    for kind, requested in limits:
        try:
            getrlimit = resource_api.getrlimit
            setrlimit = resource_api.setrlimit
            _soft, hard = getrlimit(kind)
            value = requested if hard < 0 else min(requested, hard)
            setrlimit(kind, (value, value))
        except (AttributeError, OSError, ValueError):
            continue


def _copy_verified_input(
    destination: Path,
    *,
    expected_size: int,
    expected_sha256: str,
) -> str | None:
    digest = hashlib.sha256()
    size = 0
    try:
        with destination.open("xb") as output:
            while chunk := sys.stdin.buffer.read(_CHUNK_BYTES):
                size += len(chunk)
                if size > MAX_SOURCE_BYTES or size > expected_size:
                    return "PREVIEW_SOURCE_TOO_LARGE"
                digest.update(chunk)
                output.write(chunk)
    except OSError:
        return "PREVIEW_INPUT_INVALID"
    if size != expected_size or digest.hexdigest() != expected_sha256:
        return "PREVIEW_SOURCE_BINDING_MISMATCH"
    return None


def _render(
    source: Path,
    *,
    page_number: int,
    source_sha256: str,
    source_size_bytes: int,
) -> tuple[dict[str, object], bytes] | str:
    try:
        import pymupdf
    except ImportError:
        return "PREVIEW_RENDERER_UNAVAILABLE"
    try:
        document = pymupdf.open(str(source), filetype="pdf")
    except Exception:
        return "PREVIEW_DOCUMENT_INVALID"
    try:
        if document.is_pdf is not True:
            return "PREVIEW_DOCUMENT_INVALID"
        if document.needs_pass:
            return "PREVIEW_DOCUMENT_ENCRYPTED"
        page_count = document.page_count
        if (
            not isinstance(page_count, int)
            or isinstance(page_count, bool)
            or not 1 <= page_count <= MAX_PAGES
        ):
            return "PREVIEW_PAGE_COUNT_INVALID"
        if page_number > page_count:
            return "PREVIEW_PAGE_NOT_FOUND"
        try:
            page = document.load_page(page_number - 1)
            width_points = float(page.rect.width)
            height_points = float(page.rect.height)
        except Exception:
            return "PREVIEW_DOCUMENT_INVALID"
        if (
            not math.isfinite(width_points)
            or not math.isfinite(height_points)
            or width_points <= 0
            or height_points <= 0
        ):
            return "PREVIEW_PAGE_DIMENSIONS_INVALID"
        base_scale = RENDER_DPI / 72.0
        scale = min(
            base_scale,
            MAX_EDGE_PIXELS / width_points,
            MAX_EDGE_PIXELS / height_points,
            math.sqrt(MAX_PIXELS / (width_points * height_points)),
        )
        if not math.isfinite(scale) or scale <= 0:
            return "PREVIEW_PAGE_DIMENSIONS_INVALID"
        try:
            pixmap = page.get_pixmap(
                matrix=pymupdf.Matrix(scale, scale),
                colorspace=pymupdf.csRGB,
                alpha=False,
                annots=True,
            )
            width_pixels = int(pixmap.width)
            height_pixels = int(pixmap.height)
            if (
                not 1 <= width_pixels <= MAX_EDGE_PIXELS
                or not 1 <= height_pixels <= MAX_EDGE_PIXELS
                or width_pixels * height_pixels > MAX_PIXELS
            ):
                return "PREVIEW_PAGE_DIMENSIONS_INVALID"
            png_bytes = bytes(pixmap.tobytes("png"))
        except Exception:
            return "PREVIEW_RENDER_FAILED"
        if (
            not png_bytes.startswith(_PNG_SIGNATURE)
            or not png_bytes
            or len(png_bytes) > MAX_PNG_BYTES
        ):
            return "PREVIEW_OUTPUT_TOO_LARGE"
        renderer_version = str(getattr(pymupdf, "__version__", "unknown"))
        metadata: dict[str, object] = {
            "height_pixels": height_pixels,
            "ok": True,
            "page_count": page_count,
            "page_number": page_number,
            "png_sha256": hashlib.sha256(png_bytes).hexdigest(),
            "policy_version": POLICY_VERSION,
            "renderer": "PyMuPDF",
            "renderer_version": renderer_version,
            "source_sha256": source_sha256,
            "source_size_bytes": source_size_bytes,
            "width_pixels": width_pixels,
        }
        return metadata, png_bytes
    finally:
        document.close()


def main() -> int:
    if len(sys.argv) != 4:
        return _fail("PREVIEW_INPUT_INVALID")
    page_number = _positive_integer(sys.argv[1], maximum=MAX_PAGES)
    expected_size = _positive_integer(sys.argv[2], maximum=MAX_SOURCE_BYTES)
    expected_sha256 = sys.argv[3]
    if page_number is None or expected_size is None or not _valid_sha256(expected_sha256):
        return _fail("PREVIEW_INPUT_INVALID")
    _apply_posix_resource_limits()
    source = Path("source.pdf")
    binding_error = _copy_verified_input(
        source,
        expected_size=expected_size,
        expected_sha256=expected_sha256,
    )
    if binding_error is not None:
        return _fail(binding_error)
    try:
        result = _render(
            source,
            page_number=page_number,
            source_sha256=expected_sha256,
            source_size_bytes=expected_size,
        )
    except (MemoryError, OSError, ValueError):
        return _fail("PREVIEW_RENDER_FAILED")
    if isinstance(result, str):
        return _fail(result)
    metadata, png_bytes = result
    try:
        _emit(metadata, png_bytes)
    except OSError:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
