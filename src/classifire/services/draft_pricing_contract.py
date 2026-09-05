"""Explicit workbook mapping and rate provenance, with no inferred prices or authority."""

from __future__ import annotations

import re
from typing import Any

from .draft_system_match_contract import canonical, digest

FIELDS = (
    "reference",
    "description",
    "unit",
    "rate",
    "currency",
    "tax_basis",
    "rate_date",
    "labour",
    "materials",
    "inclusions",
    "exclusions",
)
REQUIRED_MAPPING = ("reference", "description", "unit", "rate", "currency", "tax_basis")


def validate_mapping(mapping: Any, columns: int) -> None:
    if type(mapping) is not dict or set(mapping) != set(FIELDS):
        raise ValueError("mapping")
    used = []
    for key, value in mapping.items():
        if value is None and key not in REQUIRED_MAPPING:
            continue
        if type(value) is not int or not 1 <= value <= columns:
            raise ValueError("mapping column")
        used.append(value)
    if len(set(used)) != len(used):
        raise ValueError("duplicate mapping")


def row_values(fields: dict[str, Any]) -> tuple[dict[str, str | None], list[str]]:
    from .draft_estimate_contract import decimal_string

    values = {key: cell["value"] if cell is not None else None for key, cell in fields.items()}
    problems = []
    for key in REQUIRED_MAPPING:
        cell = fields[key]
        if cell is None or cell["kind"] not in ("text", "number") or not values[key]:
            problems.append(key + "_missing_or_unsupported")
    rate = fields["rate"]
    if rate is not None and rate["kind"] in ("text", "number"):
        try:
            values["rate"] = decimal_string(rate["value"])
        except (ValueError, ArithmeticError):
            problems.append("rate_invalid")
    else:
        values["rate"] = None
    if values["unit"] not in ("each", "m", "mm", "m2"):
        problems.append("unit_unsupported")
    if values["currency"] != "AUD":
        problems.append("currency_unsupported")
    if values["tax_basis"] not in ("excluded", "GST Exclusive"):
        problems.append("tax_basis_unsupported")
    return values, list(dict.fromkeys(problems))


def preview_rows(
    document: dict[str, Any], sheet_index: int, header_row: int, mapping: dict[str, int | None]
) -> list[dict[str, Any]]:
    if type(sheet_index) is not int or not 1 <= sheet_index <= len(document["sheets"]):
        raise ValueError("sheet")
    sheet = document["sheets"][sheet_index - 1]
    if type(header_row) is not int or not 1 <= header_row < sheet["rows"]:
        raise ValueError("header row")
    validate_mapping(mapping, sheet["columns"])
    cells = {(cell["row"], cell["column"]): cell for cell in sheet["cells"]}
    result = []
    for number in range(header_row + 1, sheet["rows"] + 1):
        fields = {
            key: cells.get((number, column)) if column is not None else None
            for key, column in mapping.items()
        }
        if not any(fields.values()):
            continue
        values, problems = row_values(fields)
        row = {
            "sheet": sheet["name"],
            "sheet_index": sheet_index,
            "row": number,
            "header_row": header_row,
            "mapping": mapping,
            "fields": fields,
            "values": values,
            "problems": problems,
        }
        row["sha256"] = digest(row)
        result.append(row)
    return result


def validate_selection(selection: Any, lines: list[dict[str, Any]]) -> None:
    if type(selection) is not dict or set(selection) != {
        "line_id",
        "event_id",
        "source_id",
        "source_sha256",
        "source_size_bytes",
        "original_filename",
        "document_sha256",
        "scan_sha256",
        "row",
        "method",
        "approval_status",
        "recovery_note",
    }:
        raise ValueError("rate provenance")
    if selection["method"] != "exact_library_rate" or selection["approval_status"] != "unreviewed":
        raise ValueError("rate authority")
    for key in ("source_sha256", "document_sha256", "scan_sha256"):
        if type(selection[key]) is not str or re.fullmatch(r"[0-9a-f]{64}", selection[key]) is None:
            raise ValueError("source hash")
    if (
        type(selection["source_size_bytes"]) is not int
        or not 1 <= selection["source_size_bytes"] <= 10485760
    ):
        raise ValueError("source size")
    for key, bound in (("source_id", 36), ("original_filename", 200), ("recovery_note", 4000)):
        if type(selection[key]) is not str or not 1 <= len(selection[key].strip()) <= bound:
            raise ValueError("source metadata")
    row = selection["row"]
    if type(row) is not dict or set(row) != {
        "sheet",
        "sheet_index",
        "row",
        "header_row",
        "mapping",
        "fields",
        "values",
        "problems",
        "sha256",
    }:
        raise ValueError("row")
    if type(row["sheet"]) is not str or not 1 <= len(row["sheet"]) <= 31:
        raise ValueError("sheet name")
    for key, maximum in (("sheet_index", 10), ("row", 1000), ("header_row", 1000)):
        if type(row[key]) is not int or not 1 <= row[key] <= maximum:
            raise ValueError("row position")
    if row["row"] <= row["header_row"]:
        raise ValueError("row position")
    validate_mapping(row["mapping"], 50)
    if type(row["fields"]) is not dict or set(row["fields"]) != set(FIELDS):
        raise ValueError("source fields")
    for key, cell in row["fields"].items():
        if cell is None:
            continue
        if type(cell) is not dict or set(cell) != {"address", "row", "column", "kind", "value"}:
            raise ValueError("source cell")
        if (
            type(cell["row"]) is not int
            or cell["row"] != row["row"]
            or type(cell["column"]) is not int
            or cell["column"] != row["mapping"][key]
            or type(cell["address"]) is not str
            or re.fullmatch(r"[A-Z]{1,2}[1-9][0-9]{0,3}", cell["address"]) is None
            or cell["kind"] not in ("text", "number", "date", "formula", "boolean", "error")
            or type(cell["value"]) is not str
            or len(cell["value"]) > 4000
        ):
            raise ValueError("source cell")
        from openpyxl.utils.cell import get_column_letter  # type: ignore[import-untyped]

        if cell["address"] != get_column_letter(cell["column"]) + str(cell["row"]):
            raise ValueError("cell address")
    values, problems = row_values(row["fields"])
    if problems or row["values"] != values or row["problems"] != []:
        raise ValueError("unusable rate")
    if row["sha256"] != digest({key: value for key, value in row.items() if key != "sha256"}):
        raise ValueError("row hash")
    line = next((item for item in lines if item["line_id"] == selection["line_id"]), None)
    event = (
        next((item for item in line["history"] if item["event_id"] == selection["event_id"]), None)
        if line
        else None
    )
    if (
        line is None
        or event is None
        or event["action"] != "override"
        or event["unit_sell_rate"] != values["rate"]
        or line["unit"] != values["unit"]
        or event["reason"] != selection["recovery_note"]
    ):
        raise ValueError("rate event")
    if len(canonical(selection)) > 65536:
        raise ValueError("selection size")
