from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import pytest
import xlsxwriter
from openpyxl import Workbook  # type: ignore[import-untyped]
from openpyxl.drawing.image import Image as WorkbookImage  # type: ignore[import-untyped]
from PIL import Image, PngImagePlugin

from classifire.services.draft_pricing_worker import process, process_scope, process_scope_image
from classifire.services.draft_xlsx_image_contract import validate_image_descriptor


def picture(*, format_name="PNG", size=(18, 12)):
    output = io.BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Comment", "Synthetic metadata must not enter the served preview")
    image = Image.new("RGB", size, (24, 96, 160))
    image.save(
        output, format=format_name, **({"pnginfo": metadata} if format_name == "PNG" else {})
    )
    return output.getvalue()


def workbook(*, images=(), mode="xlsxwriter", feature=None, second_sheet=False):
    output = io.BytesIO()
    if mode == "openpyxl":
        book = Workbook()
        sheet = book.active
        sheet.title = "Defects"
        sheet.append(["ID", "Description"])
        sheet.append(["D-01", "Synthetic defect"])
        for index, data in enumerate(images):
            sheet.add_image(WorkbookImage(io.BytesIO(data)), f"C{index + 2}")
        book.save(output)
    else:
        book = xlsxwriter.Workbook(output, {"in_memory": True, "strings_to_formulas": False})
        sheet = book.add_worksheet("Defects")
        sheet.write_row(0, 0, ["ID", "Description"])
        sheet.write_row(1, 0, ["D-01", "Synthetic defect"])
        if feature == "cells":
            sheet.write(1, 3, 0)
            sheet.write_boolean(1, 4, True)
            sheet.write_datetime(
                1, 5, datetime(2026, 9, 6), book.add_format({"num_format": "yyyy-mm-dd"})
            )
            sheet.write_formula(1, 6, "=1+2", None, 999)
            sheet.write_string(1, 7, "=This is text")
        elif feature == "hidden_row":
            sheet.set_row(1, None, None, {"hidden": True})
        elif feature == "hidden_column":
            sheet.set_column(1, 1, None, None, {"hidden": True})
        elif feature == "merged":
            sheet.merge_range("A3:B3", "Unsupported merge")
        elif feature == "hidden_sheet":
            book.add_worksheet("Hidden").hide()
        elif feature == "conditional":
            sheet.conditional_format(
                "A2", {"type": "no_blanks", "format": book.add_format({"bold": True})}
            )
        elif feature == "validation":
            sheet.data_validation("A2", {"validate": "list", "source": ["One", "Two"]})
        elif feature == "defined_name":
            book.define_name("SyntheticName", "=Defects!$A$2")
        elif feature == "hyperlink":
            sheet.write_url("A3", "https://example.test/")
        elif feature == "too_many_rows":
            sheet.write(1000, 0, "Outside supported rows")
        elif feature == "too_many_columns":
            sheet.write(0, 50, "Outside supported columns")
        elif feature == "cell_length":
            sheet.write(2, 0, "x" * 4001)
        for index, data in enumerate(images):
            extension = "png" if data.startswith(b"\x89PNG") else "jpg"
            sheet.insert_image(
                index + 1, 2, f"synthetic.{extension}", {"image_data": io.BytesIO(data)}
            )
        if second_sheet:
            other = book.add_worksheet("Other")
            other.write_row(0, 0, ["ID", "Description"])
            other.write_row(1, 0, ["D-02", "Other defect"])
            other.insert_image("C2", "other.png", {"image_data": io.BytesIO(images[0])})
        book.close()
    return output.getvalue()


def modify(content, changes, additions=None):
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as source, zipfile.ZipFile(output, "w") as target:
        for entry in source.infolist():
            value = source.read(entry.filename)
            transform = changes.get(entry.filename)
            target.writestr(entry, transform(value) if transform is not None else value)
        for name, value in (additions or {}).items():
            target.writestr(name, value)
    return output.getvalue()


def test_default_pricing_schema_and_exact_bytes_remain_unchanged():
    content = workbook()
    expected = {
        "schema": "CLASSIFIRE-DRAFT-PRICING-XLSX-v1",
        "manifest": {
            "source_sha256": hashlib.sha256(content).hexdigest(),
            "source_size_bytes": len(content),
        },
        "sheets": [
            {
                "name": "Defects",
                "index": 1,
                "rows": 2,
                "columns": 2,
                "cells": [
                    {"address": "A1", "row": 1, "column": 1, "kind": "text", "value": "ID"},
                    {
                        "address": "B1",
                        "row": 1,
                        "column": 2,
                        "kind": "text",
                        "value": "Description",
                    },
                    {"address": "A2", "row": 2, "column": 1, "kind": "text", "value": "D-01"},
                    {
                        "address": "B2",
                        "row": 2,
                        "column": 2,
                        "kind": "text",
                        "value": "Synthetic defect",
                    },
                ],
            }
        ],
    }
    assert (
        process(content)
        == json.dumps(expected, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    )
    scope = json.loads(process_scope(content))
    assert scope["schema"] == "CLASSIFIRE-DRAFT-SCOPE-XLSX-v1"
    assert scope["sheets"][0].pop("images") == []
    scope["schema"] = expected["schema"]
    assert scope == expected
    with pytest.raises((ValueError, RuntimeError)):
        process(workbook(images=[picture()]))


def test_scope_cells_keep_kinds_and_never_use_formula_cache_or_fill_blanks():
    content = workbook(feature="cells")
    document = json.loads(process_scope(content))
    cells = {cell["address"]: cell for cell in document["sheets"][0]["cells"]}
    assert "C2" not in cells
    assert cells["D2"]["value"] == "0"
    assert cells["E2"] == {
        "address": "E2",
        "row": 2,
        "column": 5,
        "kind": "boolean",
        "value": "true",
    }
    assert cells["F2"]["kind"] == "date"
    assert cells["G2"]["kind"] == "formula" and cells["G2"]["value"] == "=1+2"
    assert cells["H2"]["kind"] == "text" and cells["H2"]["value"] == "=This is text"
    assert document["manifest"]["source_sha256"] == hashlib.sha256(content).hexdigest()


@pytest.mark.parametrize("mode,kind", [("xlsxwriter", "twoCell"), ("openpyxl", "oneCell")])
@pytest.mark.parametrize("format_name,media_type", [("PNG", "image/png"), ("JPEG", "image/jpeg")])
def test_exact_picture_anchors_original_bytes_and_sanitized_preview(
    mode, kind, format_name, media_type
):
    data = picture(format_name=format_name)
    content = workbook(images=[data], mode=mode)
    raw = process_scope(content)
    image = json.loads(raw)["sheets"][0]["images"][0]
    validate_image_descriptor(image)
    assert image["occurrence_id"] == "image-1"
    assert image["sha256"] == hashlib.sha256(data).hexdigest()
    assert image["size_bytes"] == len(data) and image["media_type"] == media_type
    assert (image["width"], image["height"]) == (18, 12)
    assert image["anchor"]["kind"] == kind
    assert image["anchor"]["from"] == {
        "row": 2,
        "column": 3,
        "row_offset_emu": 0,
        "column_offset_emu": 0,
    }
    assert (image["anchor"]["extent"] is None) == (kind == "twoCell")
    assert (image["anchor"]["to"] is None) == (kind == "oneCell")
    preview = process_scope_image(content, 1, "image-1")
    assert hashlib.sha256(preview).hexdigest() == image["preview_sha256"]
    with Image.open(io.BytesIO(preview)) as decoded:
        assert decoded.format == "PNG" and decoded.size == (18, 12)
        assert decoded.info == {}
    assert raw == process_scope(content)
    assert preview == process_scope_image(content, 1, "image-1")


def test_duplicate_picture_bytes_keep_distinct_occurrences_and_sheet_identity():
    data = picture()
    content = workbook(images=[data, data], second_sheet=True)
    document = json.loads(process_scope(content))
    first, second = document["sheets"][0]["images"]
    other = document["sheets"][1]["images"][0]
    assert (first["occurrence_id"], second["occurrence_id"], other["occurrence_id"]) == (
        "image-1",
        "image-2",
        "image-1",
    )
    assert first["sha256"] == second["sha256"] == other["sha256"]
    assert first["anchor"] != second["anchor"]
    assert first["member"] == second["member"]
    assert process_scope_image(content, 2, "image-1") == process_scope_image(content, 1, "image-1")


@pytest.mark.parametrize(
    "feature",
    [
        "hidden_row",
        "hidden_column",
        "merged",
        "hidden_sheet",
        "conditional",
        "validation",
        "defined_name",
        "hyperlink",
        "too_many_rows",
        "too_many_columns",
        "cell_length",
    ],
)
def test_unsupported_layout_or_active_cells_are_refused(feature):
    with pytest.raises((ValueError, RuntimeError)):
        process_scope(workbook(feature=feature))


@pytest.mark.parametrize(
    "mode",
    [
        "external",
        "unmarked_external",
        "crop",
        "rotation",
        "shape",
        "negative_offset",
        "outside_anchor",
        "unknown_relationship",
        "image_type",
        "image_bytes",
        "orphan_image",
        "orphan_drawing",
        "active_part",
        "macro",
    ],
)
def test_unsupported_picture_content_and_relationships_are_never_stripped(mode):
    data = picture()
    content = workbook(images=[data])
    drawing, relationship = "xl/drawings/drawing1.xml", "xl/drawings/_rels/drawing1.xml.rels"
    changes, additions = {}, {}
    if mode == "external":
        changes[relationship] = lambda value: value.replace(
            b'Target="../media/', b'TargetMode="External" Target="https://example.test/'
        )
    elif mode == "unmarked_external":
        changes[relationship] = lambda value: value.replace(
            b'Target="../media/', b'Target="https://example.test/'
        )
    elif mode == "crop":
        changes[drawing] = lambda value: value.replace(
            b"<a:stretch>", b'<a:srcRect l="1000"/><a:stretch>'
        )
    elif mode == "rotation":
        changes[drawing] = lambda value: value.replace(b"<a:xfrm>", b'<a:xfrm rot="5400000">')
    elif mode == "shape":
        changes[drawing] = lambda value: value.replace(b"xdr:pic>", b"xdr:sp>")
    elif mode == "negative_offset":
        changes[drawing] = lambda value: value.replace(
            b"<xdr:colOff>0</xdr:colOff>", b"<xdr:colOff>-1</xdr:colOff>"
        )
    elif mode == "outside_anchor":
        changes[drawing] = lambda value: value.replace(
            b"<xdr:row>1</xdr:row>", b"<xdr:row>1000</xdr:row>"
        )
    elif mode == "unknown_relationship":
        changes[relationship] = lambda value: value.replace(
            b"/relationships/image", b"/relationships/unknown"
        )
    elif mode == "image_type":
        changes["xl/media/image1.png"] = lambda value: b'<svg xmlns="http://www.w3.org/2000/svg"/>'
    elif mode == "image_bytes":
        changes["xl/media/image1.png"] = lambda value: value + b"x" * (2 * 1024 * 1024)
    elif mode == "orphan_image":
        additions["xl/media/orphan.png"] = data
    elif mode == "orphan_drawing":
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            additions["xl/drawings/orphan.xml"] = archive.read(drawing)
    elif mode == "active_part":
        additions["xl/activeX/activeX1.bin"] = b"synthetic"
    elif mode == "macro":
        additions["xl/vbaProject.bin"] = b"synthetic"
    with pytest.raises((ValueError, RuntimeError, OSError)):
        process_scope(modify(content, changes, additions))


def test_image_pixel_and_occurrence_limits_are_enforced():
    with pytest.raises((ValueError, RuntimeError)):
        process_scope(workbook(images=[picture(size=(2001, 1000))]))
    with pytest.raises((ValueError, RuntimeError)):
        process_scope(workbook(images=[picture()] * 51))


@pytest.mark.parametrize(
    "sheet,identity",
    [
        (True, "image-1"),
        (0, "image-1"),
        ("1", "image-1"),
        (2, "image-1"),
        (1, "image-2"),
        (1, "../../other"),
    ],
)
def test_unknown_or_malformed_image_selection_cannot_read_another_member(sheet, identity):
    with pytest.raises(ValueError, match="SCOPE_XLSX_IMAGE_NOT_FOUND"):
        process_scope_image(workbook(images=[picture()]), sheet, identity)


@pytest.mark.parametrize(
    "change",
    [
        "member",
        "preview_hash",
        "byte_size",
        "pixel_size",
        "type",
        "occurrence",
        "anchor_bool",
        "anchor_extra",
        "zero_extent",
    ],
)
def test_portable_image_descriptor_refuses_forged_shapes_without_reading_images(change):
    image = json.loads(process_scope(workbook(images=[picture()], mode="openpyxl")))["sheets"][0][
        "images"
    ][0]
    if change == "member":
        image["member"] = "xl/media/../../outside.png"
    elif change == "preview_hash":
        image["preview_sha256"] = "F" * 64
    elif change == "byte_size":
        image["size_bytes"] = True
    elif change == "pixel_size":
        image["width"] = 2_000_000
    elif change == "type":
        image["media_type"] = "image/jpeg"
    elif change == "occurrence":
        image["occurrence_id"] = "image-51"
    elif change == "anchor_bool":
        image["anchor"]["from"]["row"] = True
    elif change == "anchor_extra":
        image["anchor"]["executable"] = "unsupported"
    elif change == "zero_extent":
        image["anchor"]["extent"]["height_emu"] = 0
    with pytest.raises(ValueError):
        validate_image_descriptor(image)


def test_cli_scope_document_image_and_default_pricing_modes():
    content = workbook(images=[picture()])
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}
    }
    environment.update(
        PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"), PYTHONDONTWRITEBYTECODE="1"
    )
    command = [sys.executable, "-m", "classifire.services.draft_pricing_worker"]
    document = subprocess.run(  # noqa: S603 - fixed module/flags; synthetic bytes go only to stdin.
        command + ["--scope-evidence"],
        input=content,
        capture_output=True,
        check=True,
        env=environment,
        timeout=30,
    )
    preview = subprocess.run(  # noqa: S603 - fixed module/flags; synthetic bytes go only to stdin.
        command + ["--scope-image", "1", "image-1"],
        input=content,
        capture_output=True,
        check=True,
        env=environment,
        timeout=30,
    )
    assert document.stdout == process_scope(content)
    assert preview.stdout == process_scope_image(content, 1, "image-1")
    denied = subprocess.run(  # noqa: S603 - fixed module/flags; synthetic bytes go only to stdin.
        command, input=content, capture_output=True, check=False, env=environment, timeout=30
    )
    assert denied.returncode == 1 and denied.stdout == b""
    assert denied.stderr == b"PRICING_XLSX_PROCESSING_FAILED"
