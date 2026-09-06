"""Bounded disposable XLSX reader; retains cell kinds and never evaluates formulas."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from contextlib import redirect_stdout
from typing import Any

from .report_evidence_adapter import (
    _open_verified_xlsx_report,
    _xlsx_archive_is_within_policy,
    _xlsx_cell_value,
)

MAX_BYTES = 10 * 1024 * 1024
MAX_METADATA_BYTES = 2 * 1024 * 1024


def _process(content: bytes, *, scope_evidence: bool) -> tuple[bytes, dict[tuple[int, str], bytes]]:
    if type(content) is not bytes or not 1 <= len(content) <= MAX_BYTES:
        raise ValueError("PRICING_XLSX_SIZE")
    # Tighter interactive bounds before the existing shared archive policy/parser.
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        entries = archive.infolist()
        names = [entry.filename.replace("\\", "/").casefold() for entry in entries]
        if not 1 <= len(entries) <= 2000 or len(set(names)) != len(names):
            raise ValueError("PRICING_XLSX_ARCHIVE")
        if sum(entry.file_size for entry in entries) > 32 * 1024 * 1024:
            raise ValueError("PRICING_XLSX_ARCHIVE")
        for entry in entries:
            if entry.file_size > 8 * 1024 * 1024 or entry.compress_type not in (
                zipfile.ZIP_STORED,
                zipfile.ZIP_DEFLATED,
            ):
                raise ValueError("PRICING_XLSX_ARCHIVE")
        if scope_evidence and any(
            name.startswith(("xl/activex/", "xl/ctrlprops/", "xl/macrosheets/", "xl/dialogsheets/"))
            for name in names
        ):
            raise ValueError("SCOPE_XLSX_ACTIVE_CONTENT")
    image_sheets: list[dict[str, Any]] = []
    previews: dict[tuple[int, str], bytes] = {}
    if scope_evidence:
        from .draft_xlsx_images import inspect_scope_images

        _xlsx_archive_is_within_policy(content, allow_static_images=True)
        image_sheets, previews = inspect_scope_images(content)
    else:
        _xlsx_archive_is_within_policy(content)
    workbook = _open_verified_xlsx_report(content)
    sheets: list[dict[str, Any]] = []
    total_cells = 0
    try:
        if not 1 <= len(workbook.worksheets) <= 10:
            raise ValueError("PRICING_XLSX_SHEETS")
        if scope_evidence and (
            workbook.defined_names or len(image_sheets) != len(workbook.worksheets)
        ):
            raise ValueError("SCOPE_XLSX_LAYOUT")
        for index, sheet in enumerate(workbook.worksheets, 1):
            if scope_evidence and (
                sheet.data_validations.count
                or len(sheet.conditional_formatting)
                or any(dimension.hidden for dimension in sheet.row_dimensions.values())
                or any(dimension.hidden for dimension in sheet.column_dimensions.values())
                or sheet._charts
                or image_sheets[index - 1]["name"] != sheet.title
                or len(sheet._images) != len(image_sheets[index - 1]["images"])
            ):
                raise ValueError("SCOPE_XLSX_LAYOUT")
            if sheet.sheet_state != "visible" or sheet.merged_cells.ranges:
                raise ValueError("PRICING_XLSX_LAYOUT")
            if not 1 <= sheet.max_row <= 1000 or not 1 <= sheet.max_column <= 50:
                raise ValueError("PRICING_XLSX_GRID")
            total_cells += sheet.max_row * sheet.max_column
            if total_cells > 20000:
                raise ValueError("PRICING_XLSX_GRID")
            cells = []
            for row in sheet.iter_rows():
                for cell in row:
                    if cell.comment is not None or cell.hyperlink is not None:
                        raise ValueError("PRICING_XLSX_ACTIVE_CONTENT")
                    if cell.value is None:
                        continue
                    kind, value = _xlsx_cell_value(cell)
                    if len(value) > 4000:
                        raise ValueError("PRICING_XLSX_CELL")
                    cells.append(
                        {
                            "address": cell.coordinate,
                            "row": cell.row,
                            "column": cell.column,
                            "kind": kind,
                            "value": value,
                        }
                    )
            sheets.append(
                {
                    "name": sheet.title,
                    "index": index,
                    "rows": sheet.max_row,
                    "columns": sheet.max_column,
                    "cells": cells,
                }
            )
            if scope_evidence:
                sheets[-1]["images"] = image_sheets[index - 1]["images"]
    finally:
        workbook.close()
    document = {
        "schema": "CLASSIFIRE-DRAFT-SCOPE-XLSX-v1"
        if scope_evidence
        else "CLASSIFIRE-DRAFT-PRICING-XLSX-v1",
        "manifest": {
            "source_sha256": hashlib.sha256(content).hexdigest(),
            "source_size_bytes": len(content),
        },
        "sheets": sheets,
    }
    result = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    if len(result) > MAX_METADATA_BYTES:
        raise ValueError("PRICING_XLSX_METADATA")
    return result, previews


def process(content: bytes) -> bytes:
    """Preserve the original pricing document schema, bytes and default-deny image policy."""
    return _process(content, scope_evidence=False)[0]


def process_scope(content: bytes) -> bytes:
    return _process(content, scope_evidence=True)[0]


def process_scope_image(content: bytes, sheet_index: int, occurrence_id: str) -> bytes:
    if type(sheet_index) is not int or not 1 <= sheet_index <= 10 or type(occurrence_id) is not str:
        raise ValueError("SCOPE_XLSX_IMAGE_NOT_FOUND")
    _, previews = _process(content, scope_evidence=True)
    try:
        return previews[(sheet_index, occurrence_id)]
    except KeyError as exc:
        raise ValueError("SCOPE_XLSX_IMAGE_NOT_FOUND") from exc


def main() -> None:
    if sys.platform != "win32":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
        resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    try:
        content = sys.stdin.buffer.read(MAX_BYTES + 1)
        with redirect_stdout(sys.stderr):
            if not sys.argv[1:]:
                result = process(content)
            elif sys.argv[1:] == ["--scope-evidence"]:
                result = process_scope(content)
            elif len(sys.argv) == 4 and sys.argv[1] == "--scope-image":
                result = process_scope_image(content, int(sys.argv[2]), sys.argv[3])
            else:
                raise ValueError("worker arguments")
        sys.stdout.buffer.write(result)
    except Exception:
        sys.stderr.write(
            "SCOPE_XLSX_PROCESSING_FAILED" if sys.argv[1:] else "PRICING_XLSX_PROCESSING_FAILED"
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
