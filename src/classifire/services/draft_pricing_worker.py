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


def process(content: bytes) -> bytes:
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
    _xlsx_archive_is_within_policy(content)
    workbook = _open_verified_xlsx_report(content)
    sheets: list[dict[str, Any]] = []
    total_cells = 0
    try:
        if not 1 <= len(workbook.worksheets) <= 10:
            raise ValueError("PRICING_XLSX_SHEETS")
        for index, sheet in enumerate(workbook.worksheets, 1):
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
    finally:
        workbook.close()
    document = {
        "schema": "CLASSIFIRE-DRAFT-PRICING-XLSX-v1",
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
    return result


def main() -> None:
    if sys.platform != "win32":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
        resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    try:
        content = sys.stdin.buffer.read(MAX_BYTES + 1)
        with redirect_stdout(sys.stderr):
            result = process(content)
        sys.stdout.buffer.write(result)
    except Exception:
        sys.stderr.write("PRICING_XLSX_PROCESSING_FAILED")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
