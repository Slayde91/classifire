"""Bounded post-scan structural check for foreign report attachments, never evaluation."""

from __future__ import annotations

import hashlib
import io
import json
import math
import sys
import zipfile
from contextlib import redirect_stdout

from .report_evidence_adapter import _open_verified_xlsx_report, _xlsx_archive_is_within_policy

MAX_BYTES = 8 * 1024 * 1024
SCHEMA = "CLASSIFIRE-IMPORTED-REPORT-BINARY-v1"


def process(content: bytes, format_name: str) -> bytes:
    if not 1 <= len(content) <= MAX_BYTES:
        raise ValueError("size")
    count = 0
    if format_name == "pdf":
        import pymupdf

        with pymupdf.open(stream=content, filetype="pdf") as document:
            if (
                document.is_encrypted
                or document.is_form_pdf
                or document.embfile_count()
                or not 1 <= document.page_count <= 100
            ):
                raise ValueError("unsupported PDF")
            if document.xref_length() > 20000:
                raise ValueError("PDF objects")
            forbidden = {
                "OpenAction",
                "A",
                "URI",
                "XFA",
                "AA",
                "JS",
                "JavaScript",
                "EmbeddedFiles",
                "RichMediaContent",
                "RichMediaSettings",
            }
            for index in range(1, document.xref_length()):
                keys = set(document.xref_get_keys(index))
                if keys & forbidden:
                    raise ValueError("PDF active content")
                if "S" in keys and document.xref_get_key(index, "S")[1] in (
                    "/JavaScript",
                    "/Launch",
                    "/URI",
                    "/GoToR",
                    "/SubmitForm",
                    "/ImportData",
                    "/Rendition",
                ):
                    raise ValueError("PDF action")
            for page in document:
                if not all(
                    math.isfinite(v) and 1 <= v <= 5000 for v in (page.rect.width, page.rect.height)
                ):
                    raise ValueError("PDF dimensions")
            count = document.page_count
    elif format_name == "xlsx":
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 2000 or sum(e.file_size for e in entries) > 32 * 1024 * 1024:
                raise ValueError("XLSX size")
            from defusedxml.ElementTree import fromstring  # type: ignore[import-untyped]
            from PIL import Image

            for entry in entries:
                lowered = entry.filename.casefold()
                if lowered.startswith(
                    ("xl/activex/", "xl/ctrlprops/", "xl/macrosheets/", "xl/dialogsheets/")
                ):
                    raise ValueError("XLSX active content")
                if lowered.endswith(".rels"):
                    for relationship in fromstring(archive.read(entry)):
                        if relationship.attrib.get("TargetMode", "").lower() == "external":
                            raise ValueError("XLSX external relationship")
                if lowered.startswith("xl/media/"):
                    data = archive.read(entry)
                    if len(data) > 2 * 1024 * 1024 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
                        raise ValueError("XLSX image format")
                    with Image.open(io.BytesIO(data)) as image:
                        if image.format != "PNG" or image.width * image.height > 2000000:
                            raise ValueError("XLSX image bounds")
                        image.verify()
            if any(e.file_size > MAX_BYTES for e in entries):
                raise ValueError("XLSX member size")
        _xlsx_archive_is_within_policy(content, allow_static_images=True)
        book = _open_verified_xlsx_report(content)
        try:
            if not 1 <= len(book.worksheets) <= 40:
                raise ValueError("XLSX sheets")
            if book.defined_names:
                raise ValueError("XLSX defined names")
            cells = 0
            for sheet in book.worksheets:
                if sheet.data_validations.count or len(sheet.conditional_formatting):
                    raise ValueError("XLSX dynamic rules")
                if sheet.max_row > 20000 or sheet.max_column > 80:
                    raise ValueError("XLSX grid")
                cells += sheet.max_row * sheet.max_column
                if cells > 300000:
                    raise ValueError("XLSX cells")
                for row in sheet.iter_rows():
                    for cell in row:
                        if cell.data_type == "f" or cell.hyperlink is not None:
                            raise ValueError("XLSX active content")
            count = len(book.worksheets)
        finally:
            book.close()
    else:
        raise ValueError("format")
    return json.dumps(
        {
            "schema": SCHEMA,
            "format": format_name,
            "count": count,
            "manifest": {
                "source_sha256": hashlib.sha256(content).hexdigest(),
                "source_size_bytes": len(content),
            },
            "authority": "foreign_unverified",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def main() -> None:
    if sys.platform != "win32":
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
    content = sys.stdin.buffer.read(MAX_BYTES + 1)
    try:
        with redirect_stdout(io.StringIO()):
            result = process(content, sys.argv[1])
        sys.stdout.buffer.write(result)
    except Exception:
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
