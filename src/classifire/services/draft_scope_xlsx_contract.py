"""Pure, bounded workbook-row provenance for human-reviewed Draft Scope evidence."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .draft_xlsx_image_contract import validate_image_descriptor

SCHEMA = "CLASSIFIRE-DRAFT-SCOPE-XLSX-v1"
FIELDS = (
    "defect_label",
    "defect_description",
    "location",
    "opening_label",
    "plane",
    "substrate",
    "width_mm",
    "height_mm",
    "service_label",
    "service_type",
    "quantity",
    "unit",
)
KINDS = ("defect", "opening", "service")
MAX_BATCH_ROWS = 25
ROW_KEYS = {"sheet", "sheet_index", "row", "header_row", "mapping", "fields", "sha256"}
CELL_KEYS = {"address", "row", "column", "kind", "value"}


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def positive(value: Any, maximum: int) -> bool:
    return type(value) is int and 1 <= value <= maximum


def validate_mapping(mapping: Any, columns: int = 50) -> None:
    if type(mapping) is not dict or set(mapping) != set(FIELDS):
        raise ValueError("mapping fields")
    if any(value is not None and not positive(value, columns) for value in mapping.values()):
        raise ValueError("mapping column")


def validate_cell(cell: Any, *, rows: int = 1000, columns: int = 50) -> None:
    if type(cell) is not dict or set(cell) != CELL_KEYS:
        raise ValueError("cell")
    if not positive(cell["row"], rows) or not positive(cell["column"], columns):
        raise ValueError("cell coordinate")
    column = cell["column"]
    letters = ""
    while column:
        column, remainder = divmod(column - 1, 26)
        letters = chr(65 + remainder) + letters
    if cell["address"] != f"{letters}{cell['row']}":
        raise ValueError("cell address")
    if cell["kind"] not in {"text", "number", "boolean", "date", "formula", "error"}:
        raise ValueError("cell kind")
    if type(cell["value"]) is not str or len(cell["value"]) > 4000:
        raise ValueError("cell value")


def validate_row(row: Any) -> None:
    if type(row) is not dict or set(row) != ROW_KEYS:
        raise ValueError("row shape")
    if (
        type(row["sheet"]) is not str
        or not 1 <= len(row["sheet"]) <= 31
        or not positive(row["sheet_index"], 10)
        or not positive(row["row"], 1000)
        or not positive(row["header_row"], 999)
        or row["header_row"] >= row["row"]
    ):
        raise ValueError("row locator")
    validate_mapping(row["mapping"])
    if type(row["fields"]) is not dict or set(row["fields"]) != set(FIELDS):
        raise ValueError("row fields")
    for key, cell in row["fields"].items():
        if cell is None:
            continue
        validate_cell(cell)
        if cell["row"] != row["row"] or cell["column"] != row["mapping"][key]:
            raise ValueError("row mapping")
    expected = digest({key: value for key, value in row.items() if key != "sha256"})
    if row["sha256"] != expected:
        raise ValueError("row checksum")


def validate_document(document: Any) -> bool:
    if type(document) is not dict or set(document) != {"schema", "manifest", "sheets"}:
        return False
    if document["schema"] != SCHEMA:
        return False
    manifest = document["manifest"]
    if (
        type(manifest) is not dict
        or set(manifest) != {"source_sha256", "source_size_bytes"}
        or type(manifest["source_sha256"]) is not str
        or re.fullmatch(r"[0-9a-f]{64}", manifest["source_sha256"]) is None
        or not positive(manifest["source_size_bytes"], 10 * 1024 * 1024)
    ):
        return False
    sheets = document["sheets"]
    if type(sheets) is not list or not 1 <= len(sheets) <= 10:
        return False
    total_cells = 0
    total_images = 0
    names = set()
    try:
        for index, sheet in enumerate(sheets, 1):
            if type(sheet) is not dict or set(sheet) != {
                "name",
                "index",
                "rows",
                "columns",
                "cells",
                "images",
            }:
                return False
            if (
                sheet["index"] != index
                or type(sheet["index"]) is not int
                or type(sheet["name"]) is not str
                or not 1 <= len(sheet["name"]) <= 31
                or sheet["name"] in names
                or not positive(sheet["rows"], 1000)
                or not positive(sheet["columns"], 50)
            ):
                return False
            names.add(sheet["name"])
            total_cells += sheet["rows"] * sheet["columns"]
            if total_cells > 20000 or type(sheet["cells"]) is not list:
                return False
            coordinates = set()
            for cell in sheet["cells"]:
                validate_cell(cell, rows=sheet["rows"], columns=sheet["columns"])
                coordinate = (cell["row"], cell["column"])
                if coordinate in coordinates:
                    return False
                coordinates.add(coordinate)
            if type(sheet["images"]) is not list:
                return False
            image_ids = set()
            for image in sheet["images"]:
                validate_image_descriptor(image)
                if image["occurrence_id"] in image_ids:
                    return False
                image_ids.add(image["occurrence_id"])
            total_images += len(sheet["images"])
            if total_images > 50:
                return False
    except (ValueError, TypeError, KeyError):
        return False
    return True


def selected_rows(
    document: dict[str, Any], plan: Any
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if type(plan) is not dict or set(plan) != {
        "sheet_index",
        "header_row",
        "mapping",
        "selections",
    }:
        raise ValueError("plan")
    if not positive(plan["sheet_index"], len(document["sheets"])):
        raise ValueError("sheet")
    sheet = document["sheets"][plan["sheet_index"] - 1]
    if not positive(plan["header_row"], sheet["rows"] - 1):
        raise ValueError("header")
    validate_mapping(plan["mapping"], sheet["columns"])
    selections = plan["selections"]
    if type(selections) is not list or not 1 <= len(selections) <= MAX_BATCH_ROWS:
        raise ValueError("batch")
    seen = set()
    normalized = []
    for selection in selections:
        if (
            type(selection) is not dict
            or set(selection) != {"row", "kinds"}
            or not positive(selection["row"], sheet["rows"])
            or selection["row"] <= plan["header_row"]
            or selection["row"] in seen
            or type(selection["kinds"]) is not list
            or not 1 <= len(selection["kinds"]) <= 3
            or any(type(kind) is not str or kind not in KINDS for kind in selection["kinds"])
            or len(set(selection["kinds"])) != len(selection["kinds"])
        ):
            raise ValueError("row selection")
        seen.add(selection["row"])
        normalized.append({"row": selection["row"], "kinds": sorted(selection["kinds"])})
    normalized.sort(key=lambda selection: selection["row"])
    checked = dict(plan, selections=normalized)
    cells = {(cell["row"], cell["column"]): cell for cell in sheet["cells"]}
    rows = []
    for selection in normalized:
        row = {
            "sheet": sheet["name"],
            "sheet_index": sheet["index"],
            "row": selection["row"],
            "header_row": plan["header_row"],
            "mapping": dict(plan["mapping"]),
            "fields": {
                key: cells.get((selection["row"], column)) if column else None
                for key, column in plan["mapping"].items()
            },
        }
        row["sha256"] = digest(row)
        validate_row(row)
        rows.append(row)
    return checked, rows
