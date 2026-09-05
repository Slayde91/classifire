"""Disposable PDF normalization/render worker; bounded stdin and output, no DB config."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from contextlib import redirect_stdout
from typing import Any

import pymupdf

from .report_evidence_adapter import _normalised_text, normalise_verified_pdf_report
from .storage import VerifiedStoredFileContent

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_PREVIEW_BYTES = 4 * 1024 * 1024


def process(content: bytes, page_number: int | None = None) -> bytes:
    if not 1 <= len(content) <= MAX_PDF_BYTES or not content.startswith(b"%PDF-"):
        raise ValueError("PDF_INVALID")
    digest = hashlib.sha256(content).hexdigest()
    with pymupdf.open(stream=content, filetype="pdf") as pdf:
        if pdf.is_encrypted or not 1 <= pdf.page_count <= 50 or pdf.embfile_count():
            raise ValueError("PDF_UNSUPPORTED")
        if page_number is not None:
            if not 1 <= page_number <= pdf.page_count:
                raise ValueError("PDF_PAGE_INVALID")
            page = pdf[page_number - 1]
            width, height = page.rect.width, page.rect.height
            if not all(math.isfinite(v) and 1 <= v <= 5000 for v in (width, height)):
                raise ValueError("PDF_PAGE_SIZE_INVALID")
            scale = min(1200 / width, 1600 / height, 2)
            result = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes(
                "png"
            )
            if len(result) > MAX_PREVIEW_BYTES:
                raise ValueError("PDF_PREVIEW_TOO_LARGE")
            return bytes(result)
        pages: list[dict[str, Any]] = []
        for index in range(pdf.page_count):
            page = pdf[index]
            if not all(
                math.isfinite(v) and 1 <= v <= 5000 for v in (page.rect.width, page.rect.height)
            ):
                raise ValueError("PDF_PAGE_SIZE_INVALID")
            extracted = _normalised_text(page.get_text("text", sort=True))
            if len(extracted) > 20000:
                raise ValueError("PDF_TEXT_TOO_LARGE")
            pages.append({"page_number": index + 1, "text": extracted})
    normalized = normalise_verified_pdf_report(
        VerifiedStoredFileContent(digest, len(content), "application/pdf", content)
    )
    for page in pages:
        locator = next(
            item
            for item in normalized.locators
            if item.item_kind == "page" and item.page_number == page["page_number"]
        )
        page.update(locator_key=locator.locator_key, page_text_sha256=locator.content_sha256)
    metadata: dict[str, Any] = {
        "schema": "CLASSIFIRE-DRAFT-PDF-v1",
        "parser": "PyMuPDF " + pymupdf.VersionBind,
        "manifest": normalized.manifest,
        "pages": pages,
    }
    data = json.dumps(
        metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    if len(data) > MAX_DOCUMENT_BYTES:
        raise ValueError("PDF_DOCUMENT_TOO_LARGE")
    return data


def main() -> None:
    # Linux workers also have OS resource limits. Windows keeps the parent's hard
    # timeout and all byte/page/pixel limits; this is process isolation, not a sandbox.
    if sys.platform != "win32":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
        resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    try:
        data = sys.stdin.buffer.read(MAX_PDF_BYTES + 1)
        page = int(sys.argv[1]) if len(sys.argv) > 1 else None
        with redirect_stdout(sys.stderr):
            result = process(data, page)
        sys.stdout.buffer.write(result)
    except Exception:
        # No parser/source text or filesystem paths enter logs.
        sys.stderr.write("PDF_PROCESSING_FAILED")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
