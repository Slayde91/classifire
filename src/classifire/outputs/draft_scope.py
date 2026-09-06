"""Pure scope-only Draft renderers; no estimate or database operation is invoked."""

from __future__ import annotations

import io
import math
import unicodedata
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from html import escape
from typing import Any

import pymupdf
import xlsxwriter  # type: ignore[import-untyped]
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from ..services.draft_scope_evidence import (
    ENTITY_EVIDENCE_SCHEMAS,
    WORKBOOK_EVIDENCE_SCHEMAS,
    reference_label,
    reference_status,
)
from .common import ATTRIBUTION
from .draft_branding import DraftLogo
from .draft_branding import supplied_logo_path as logo_path
from .draft_system_review import NOTICE as SYSTEM_NOTICE
from .draft_system_review import sections as system_sections
from .draft_system_review import summary as system_summary
from .xlsx import _formats

_FONT = "CLASSIFIRE-Scope-Unicode"
_DRAFT = "DRAFT - UNREVIEWED"
_UNKNOWN = "Unknown / unavailable"
_LINEAGE_KEYS = (
    "schema_version",
    "artifact_id",
    "project_id",
    "revision",
    "created_by",
    "created_at",
    "sha256",
    "file_sha256",
)


def _verified(snapshot: dict[str, Any]) -> dict[str, Any]:
    from ..services.draft_scope_reports import validate_report_snapshot

    validate_report_snapshot(snapshot)
    return deepcopy(snapshot)


@lru_cache(maxsize=1)
def _font_coverage() -> frozenset[int]:
    # This font ships with the already-required PyMuPDF dependency; no system
    # font or network lookup changes the output between Windows and hosted CI.
    font = TTFont(_FONT, io.BytesIO(pymupdf.Font("cjk").buffer))
    pdfmetrics.registerFont(font)
    return frozenset(font.face.charToGlyph)


def _control_text(value: object) -> str:
    return "".join(
        f"[U+{ord(char):04X}]"
        if unicodedata.category(char).startswith("C") and char not in "\n\r\t"
        else char
        for char in str(value)
    )


def _pdf_text(value: object) -> str:
    coverage = _font_coverage()
    text = _control_text(value).replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(
        char if char in "\n\t" or ord(char) in coverage else f"[U+{ord(char):04X}]" for char in text
    )
    return escape(text, quote=False).replace("\n", "<br/>").replace("\t", "&#160;" * 4)


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


def _quantity(value: str | None, unit: str = "") -> str:
    return _UNKNOWN if value is None else f"{value} {unit}".rstrip()


def _metadata(snapshot: dict[str, Any]) -> list[tuple[str, Any]]:
    scope = snapshot["scope"]
    return [
        ("Report status", _DRAFT),
        ("Project", snapshot["project"]["name"]),
        ("Project reference", snapshot["project"]["reference"]),
        ("Project ID", snapshot["project"]["id"]),
        ("Report ID", snapshot["report_id"]),
        ("Report snapshot SHA-256", snapshot["sha256"]),
        ("Report created at (UTC)", snapshot["created_at"]),
        ("Report created by", snapshot["created_by"]),
        ("Report schema", snapshot["schema_version"]),
        ("Profile / renderer version", f"{snapshot['profile']} / {snapshot['render_version']}"),
        ("Scope artifact ID", scope["artifact_id"]),
        ("Scope revision", scope["revision"]),
        ("Scope envelope SHA-256", scope["sha256"]),
        ("Scope parent SHA-256", scope["parent_hash"] or "None - first revision"),
        ("Scope schema", scope["schema_version"]),
        ("Scope created at (UTC)", scope["created_at"]),
        ("Scope created by", scope["created_by"]),
        ("Scope provenance", scope["provenance"]),
        ("Scope review", scope["review_status"]),
        (
            "Technical system selection",
            "Saved unapproved candidate review; compatibility unresolved"
            if snapshot.get("system_match")
            else "Unavailable - not supplied in this scope-only report",
        ),
        ("Pricing and commercial totals", "Unavailable - no estimate was run"),
        (
            "Evidence and authority",
            "Manual/imported assertions remain unreviewed. "
            + (
                "Captured technical-source provenance is not approval for this Scope."
                if snapshot.get("system_match")
                else "No source evidence or approval is established."
            ),
        ),
    ]


def _page_reference_fields(scope: dict[str, Any], ref: dict[str, Any]) -> list[tuple[str, Any]]:
    """Display saved target status without implying a fresh source or approval check."""
    fields: list[tuple[str, Any]] = []
    if scope["schema_version"] in ENTITY_EVIDENCE_SCHEMAS:
        fields.extend(
            [
                ("target", reference_label(ref, scope["content"])),
                ("saved_revision_review_status", reference_status(ref, scope["content"])),
            ]
        )
    if ref.get("source_kind") == "xlsx":
        fields.extend((key, value) for key, value in ref.items() if key not in {"row", "images"})
        row = ref["row"]
        for key in ("sheet", "sheet_index", "row", "header_row", "sha256"):
            fields.append(("source_row_" + key, row[key]))
        for key, cell in row["fields"].items():
            if cell is None:
                description = (
                    "Not mapped"
                    if row["mapping"][key] is None
                    else f"Column {row['mapping'][key]}: blank source cell"
                )
            else:
                description = f"{row['sheet']}!{cell['address']} ({cell['kind']}): {cell['value']}"
            fields.append(("mapped_" + key, description))
        import json

        for image in ref["images"]:
            for key, value in image.items():
                fields.append(
                    (
                        f"image_{image['occurrence_id']}_{key}",
                        json.dumps(value, sort_keys=True) if isinstance(value, dict) else value,
                    )
                )
    elif "suggestion" in ref:
        fields.extend((key, value) for key, value in ref.items() if key != "suggestion")
        fields.append(
            (
                "suggestion_notice",
                "Original AI proposal retained separately from human-edited facts; "
                "no approval or execution authority",
            )
        )
        for key, value in ref["suggestion"].items():
            if key == "proposed_item":
                import json

                for item_key, item_value in value.items():
                    fields.append(
                        (
                            "original_proposed_" + item_key,
                            "Unknown"
                            if item_value is None
                            else json.dumps(item_value, ensure_ascii=False)
                            if isinstance(item_value, (list, dict))
                            else item_value,
                        )
                    )
            else:
                fields.append(("suggestion_" + key, value))
    else:
        fields.extend(ref.items())
    return fields


def _page_reference_id(ref: dict[str, Any]) -> str:
    return str(ref["target_id"] if "target_kind" in ref else ref["observation_id"])


def _append_scope_content(
    scope: dict[str, Any],
    text: Callable[..., None],
    heading: ParagraphStyle,
    item_heading: ParagraphStyle,
    small: ParagraphStyle,
) -> None:
    """Append the same retained physical content to Scope and complete reports."""

    def detail(label: str, value: object) -> None:
        text(f"{label}: {value}")

    content = scope["content"]
    text("Scope overview", heading)
    text(" | ".join(f"{key.replace('_', ' ').title()}: {len(content[key])}" for key in content))
    defects = {item["id"]: item["label"] for item in content["defects"]}
    openings = {item["id"]: item["label"] for item in content["openings"]}

    text("Defects", heading)
    for item in content["defects"]:
        text(item["label"], item_heading)
        text(f"Defect ID: {item['id']}", small)
        text(item["description"] or "No description supplied.")
    if not content["defects"]:
        text("No defects supplied.")
    text("Openings", heading)
    for item in content["openings"]:
        text(item["label"], item_heading)
        text(f"Opening ID: {item['id']}", small)
        related = item["defect_id"]
        detail(
            "Related defect",
            f"{defects[related]} ({related})" if related else "Not linked / unknown",
        )
        detail("Plane / substrate", f"{item['plane']} / {item['substrate'] or _UNKNOWN}")
        detail(
            "Width / height",
            f"{_quantity(item['width_mm'], 'mm')} / {_quantity(item['height_mm'], 'mm')}",
        )
        detail("Blank opening", "Yes - no linked services" if item["blank"] else "No")
        detail("Evidence state", f"{item['state']} - unreviewed")
    if not content["openings"]:
        text("No openings supplied.")
    text("Services", heading)
    for item in content["services"]:
        text(item["label"], item_heading)
        text(f"Service ID: {item['id']}", small)
        detail("Type", item["service_type"] or _UNKNOWN)
        detail("Quantity", _quantity(item["quantity"], item["unit"]))
        detail("Quantity unit", item["unit"])
        detail("Evidence state", f"{item['state']} - unreviewed")
        for identifier in item["opening_ids"]:
            detail("Linked opening", f"{openings[identifier]} ({identifier})")
        if not item["opening_ids"]:
            detail("Linked openings", "Not linked / unknown")
    if not content["services"]:
        text("No services supplied.")
    text("Observations", heading)
    for item in content["observations"]:
        text(f"Observation ID: {item['id']}", small)
        text(item["text"])
        detail("Evidence state", f"{item['state']} - unreviewed")
    if not content["observations"]:
        text("No observations supplied.")
    for key in ("assumptions", "exclusions"):
        text(key.title(), heading)
        for index, value in enumerate(content[key], 1):
            text(f"{index}. {value}")
        if not content[key]:
            text("None supplied.")


def render_scope_report_pdf(snapshot: dict[str, Any]) -> bytes:
    """Render every scope item as flowing text, including long notes and links."""
    report = _verified(snapshot)
    coverage = _font_coverage()
    body = ParagraphStyle("ScopeBody", fontName=_FONT, fontSize=9, leading=13, spaceAfter=5)
    small = ParagraphStyle(
        "ScopeSmall", parent=body, fontSize=7, leading=10, textColor=colors.HexColor("#586779")
    )
    heading = ParagraphStyle(
        "ScopeHeading",
        parent=body,
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#d9232b"),
        spaceBefore=16,
        spaceAfter=9,
        keepWithNext=True,
    )
    item_heading = ParagraphStyle(
        "ScopeItemHeading", parent=body, fontSize=11, leading=15, spaceBefore=9, keepWithNext=True
    )
    title = ParagraphStyle("ScopeTitle", parent=body, fontSize=23, leading=29, spaceAfter=12)
    story: list[Any] = []

    def text(value: object, style: ParagraphStyle = body) -> None:
        story.append(Paragraph(_pdf_text(value), style))

    def detail(label: str, value: object) -> None:
        text(f"{label}: {value}")

    story.extend([DraftLogo(), Spacer(1, 5 * mm)])
    report_title = (
        "Draft Scope and System Review" if report.get("system_match") else "Draft Scope Report"
    )
    text(report_title, title)
    text(report["project"]["name"], item_heading)
    text(f"{report['project']['reference']} | Saved scope revision {report['scope']['revision']}")
    text(_DRAFT, heading)
    text(
        SYSTEM_NOTICE
        if report.get("system_match")
        else "Scope-only record. Technical selection, pricing and release are unavailable. "
        "Confirmed labels are manual or imported assertions, not approved physical truth."
    )
    if any(
        ord(char) not in coverage
        or (unicodedata.category(char).startswith("C") and char not in "\n\r\t")
        for value in _strings(report)
        for char in value
        if char not in "\n\r\t"
    ):
        text(
            "Text display: unsupported PDF glyphs and control characters are shown as [U+XXXX]. "
            "Original Unicode text remains in the saved Scope JSON; the workbook retains "
            "supported text characters.",
            small,
        )
    if report.get("system_match"):
        text("Saved technical review summary", heading)
        for label, value in system_summary(report["system_match"]):
            detail(label, value)
    _append_scope_content(report["scope"], text, heading, item_heading, small)
    if report.get("system_match"):
        for section in system_sections(report["system_match"]):
            text(section["title"], heading)
            for label, value in section["rows"]:
                text(f"{label}: {value}", small)
    text("Imported source history", heading)
    text(
        "Source identities, authors and ancestry are unverified declarations. "
        "They confer no local ownership or approval."
    )
    for index, entry in enumerate(report["scope"].get("import_lineage", []), 1):
        text(f"Source record {index}", item_heading)
        for key in _LINEAGE_KEYS:
            text(f"{key.replace('_', ' ').title()}: {entry[key]}", small)
    if not report["scope"].get("import_lineage"):
        text("No imported source history. Draft remains unreviewed.")
    if report["scope"].get("evidence_refs"):
        text(
            "Saved evidence-review references"
            if report["scope"]["schema_version"] in WORKBOOK_EVIDENCE_SCHEMAS
            else "Saved page-review references",
            heading,
        )
        text(
            "These are saved Draft review claims. Current source/scan availability may change; "
            "the application checks it separately. No technical or physical approval is granted."
        )
        for ref in report["scope"]["evidence_refs"]:
            for key, value in _page_reference_fields(report["scope"], ref):
                text(f"{key.replace('_', ' ')}: {value}", small)
    text("Report and source identity", heading)
    for label, value in _metadata(report):
        text(f"{label}: {value}", small)

    def footer(canvas: Canvas, document: SimpleDocTemplate) -> None:
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d9232b"))
        canvas.line(17 * mm, 17 * mm, A4[0] - 17 * mm, 17 * mm)
        canvas.setFont(_FONT, 7)
        canvas.drawString(
            17 * mm, 12 * mm, f"{_DRAFT} | Scope revision {report['scope']['revision']}"
        )
        canvas.drawRightString(A4[0] - 17 * mm, 12 * mm, f"Page {document.page}")
        canvas.setFont(_FONT, 6)
        canvas.drawString(17 * mm, 8 * mm, ATTRIBUTION)
        canvas.restoreState()

    output = io.BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=17 * mm,
        rightMargin=17 * mm,
        topMargin=16 * mm,
        bottomMargin=23 * mm,
        title="CLASSIFIRE " + report_title,
        author="Ceasefire PFP",
        subject=_DRAFT,
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def _segments(value: str, width: int) -> list[str]:
    """Split without dropping text; continuation rows remain readable in Excel."""
    if not value:
        return [""]
    parts: list[str] = []
    chunk = ""
    lines = 1
    column = 0
    for char in value:
        amount = 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
        if char == "\n":
            lines += 1
            column = 0
        else:
            column += amount
            if column > width:
                lines += 1
                column = amount
        if lines > 8 or len(chunk) >= 600:
            parts.append(chunk)
            chunk = ""
            lines = 1
            column = 0
        chunk += char
    if chunk:
        parts.append(chunk)
    return parts


def render_scope_report_xlsx(snapshot: dict[str, Any]) -> bytes:
    """Render literal source strings and typed quantities, never inferred totals."""
    report = _verified(snapshot)
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(
        output,
        {
            "in_memory": True,
            "strings_to_formulas": False,
            "strings_to_urls": False,
            "strings_to_numbers": False,
        },
    )
    report_title = (
        "Draft Scope and System Review" if report.get("system_match") else "Draft Scope Report"
    )
    formats = _formats(workbook)
    formats["quantity"] = workbook.add_format(
        {"border": 1, "num_format": "0.######", "valign": "top"}
    )
    formats["integer"] = workbook.add_format({"border": 1, "num_format": "0", "valign": "top"})
    workbook.set_properties(
        {
            "title": "CLASSIFIRE " + report_title,
            "subject": _DRAFT,
            "author": "Ceasefire PFP",
            "created": datetime.fromisoformat(report["created_at"]).replace(tzinfo=None),
            "comments": report["sha256"],
        }
    )
    content = report["scope"]["content"]

    def table(
        name: str,
        headers: list[str],
        rows: list[list[Any]],
        widths: list[int],
        *,
        brand: bool = False,
    ) -> None:
        sheet = workbook.add_worksheet(name)
        sheet.set_column(0, 0, 8)
        for column, width in enumerate(widths, 1):
            sheet.set_column(column, column, width)
        if brand:
            sheet.set_row(0, 110)
            sheet.write_string(0, 2, "CLASSIFIRE", formats["title"])
            scale = 140 / 1254
            sheet.insert_image(
                0,
                0,
                str(logo_path()),
                {"x_scale": scale, "y_scale": scale, "object_position": 1},
            )
            sheet.merge_range(1, 1, 1, 2, "CLASSIFIRE " + report_title, formats["section"])
        elif report.get("system_match"):
            sheet.set_row(0, 32)
            sheet.merge_range(0, 1, 0, len(headers), f"CLASSIFIRE {name}", formats["title"])
        else:
            sheet.write_string(0, 1, f"CLASSIFIRE {name}", formats["title"])
        sheet.write_string(
            2, 1, f"{_DRAFT} | Scope revision {report['scope']['revision']}", formats["subtitle"]
        )
        sheet.write_string(3, 1, f"Report ID: {report['report_id']}", formats["subtitle"])
        sheet.merge_range(
            4,
            0,
            4,
            len(headers),
            "Continuation rows retain text; numeric values occur only on the first part. "
            "No technical approval or prices.",
            formats["subtitle"],
        )
        sheet.set_row(4, 28)
        for column, label in enumerate(["Part", *headers]):
            sheet.write_string(5, column, label, formats["header"])
        sheet.set_row(5, 30)
        row_number = 6
        for values in rows:
            chunks = [
                _segments(_control_text(value), max(width - 3, 8))
                if isinstance(value, str)
                else [value]
                for value, width in zip(values, widths, strict=True)
            ]
            count = max(len(parts) for parts in chunks)
            for part in range(count):
                sheet.write_string(row_number, 0, f"{part + 1}/{count}", formats["text"])
                line_count = 1
                for column, (parts, width) in enumerate(zip(chunks, widths, strict=True), 1):
                    value = parts[part] if part < len(parts) else None
                    if part and column == 1 and len(parts) == 1 and isinstance(parts[0], str):
                        value = parts[0]
                    if value is None:
                        sheet.write_blank(row_number, column, None, formats["text"])
                    elif isinstance(value, bool):
                        sheet.write_boolean(row_number, column, value, formats["text"])
                    elif isinstance(value, (Decimal, float)):
                        sheet.write_number(row_number, column, float(value), formats["quantity"])
                    elif isinstance(value, int):
                        sheet.write_number(row_number, column, value, formats["integer"])
                    else:
                        sheet.write_string(row_number, column, value, formats["text"])
                        line_count = max(
                            line_count,
                            sum(
                                max(
                                    1,
                                    math.ceil(
                                        sum(
                                            2
                                            if unicodedata.east_asian_width(c) in {"W", "F"}
                                            else 1
                                            for c in line
                                        )
                                        / max(width - 3, 8)
                                    ),
                                )
                                for line in value.split("\n")
                            ),
                        )
                sheet.set_row(row_number, min(150, max(24, line_count * 15 + 8)))
                row_number += 1
        if not rows:
            sheet.write_string(6, 1, "None supplied", formats["text"])
        sheet.autofilter(5, 0, max(row_number - 1, 6), len(headers))
        sheet.freeze_panes(6, 2)
        sheet.set_landscape()
        sheet.fit_to_pages(1, 0)
        sheet.repeat_rows(0, 5)
        sheet.set_footer("&L" + _DRAFT + "&RPage &P of &N")
        sheet.hide_gridlines(2)

    metadata = [[label, value] for label, value in _metadata(report)]
    metadata += [[f"{key.title()} count", len(content[key])] for key in content]
    metadata.append(
        [
            "Text controls",
            "Unsafe control characters are displayed as [U+XXXX]. "
            "Exact original content remains in saved Scope JSON.",
        ]
    )
    table("Summary", ["Field", "Value"], metadata, [31, 94], brand=True)
    table(
        "Defects",
        ["Defect ID", "Label", "Description"],
        [[x["id"], x["label"], x["description"]] for x in content["defects"]],
        [39, 35, 78],
    )
    table(
        "Openings",
        [
            "Opening ID",
            "Label",
            "Defect ID",
            "Plane",
            "Substrate",
            "Width (mm)",
            "Height (mm)",
            "Blank opening",
            "Evidence state",
        ],
        [
            [
                x["id"],
                x["label"],
                x["defect_id"] or "Not linked / unknown",
                x["plane"],
                x["substrate"] or _UNKNOWN,
                Decimal(x["width_mm"]) if x["width_mm"] is not None else _UNKNOWN,
                Decimal(x["height_mm"]) if x["height_mm"] is not None else _UNKNOWN,
                x["blank"],
                x["state"],
            ]
            for x in content["openings"]
        ],
        [39, 30, 39, 15, 38, 23, 23, 18, 20],
    )
    table(
        "Services",
        ["Service ID", "Label", "Service type", "Quantity", "Unit", "Evidence state"],
        [
            [
                x["id"],
                x["label"],
                x["service_type"] or _UNKNOWN,
                Decimal(x["quantity"]) if x["quantity"] is not None else _UNKNOWN,
                x["unit"],
                x["state"],
            ]
            for x in content["services"]
        ],
        [39, 40, 42, 24, 12, 20],
    )
    table(
        "Service Links",
        ["Service ID", "Opening ID"],
        [
            [service["id"], opening]
            for service in content["services"]
            for opening in service["opening_ids"]
        ],
        [39, 39],
    )
    table(
        "Observations",
        ["Observation ID", "Observation", "Evidence state"],
        [[x["id"], x["text"], x["state"]] for x in content["observations"]],
        [39, 85, 20],
    )
    for key in ("assumptions", "exclusions"):
        table(
            key.title(),
            ["Note", "Text"],
            [[index, value] for index, value in enumerate(content[key], 1)],
            [12, 110],
        )
    table(
        "Import History",
        ["Source record", *[key.replace("_", " ").title() for key in _LINEAGE_KEYS]],
        [
            [index, *[entry[key] for key in _LINEAGE_KEYS]]
            for index, entry in enumerate(report["scope"].get("import_lineage", []), 1)
        ],
        [15, 38, 39, 39, 12, 39, 32, 68, 68],
    )
    if report["scope"].get("evidence_refs"):
        table(
            "Evidence References"
            if report["scope"]["schema_version"] in WORKBOOK_EVIDENCE_SCHEMAS
            else "Page Review References",
            [
                "Target ID"
                if report["scope"]["schema_version"] in ENTITY_EVIDENCE_SCHEMAS
                else "Observation ID",
                "Field",
                "Saved claim",
            ],
            [
                [_page_reference_id(ref), key.replace("_", " "), str(value)]
                for ref in report["scope"]["evidence_refs"]
                for key, value in _page_reference_fields(report["scope"], ref)
            ],
            [39, 28, 100],
        )
    if report.get("system_match"):
        parts = system_sections(report["system_match"])
        table(
            "Review and coverage",
            ["Field", "Saved value"],
            [list(row) for row in parts[0]["rows"]],
            [40, 100],
        )
        table(
            "System candidates",
            ["Candidate", "Field", "Saved value"],
            [[part["title"], *row] for part in parts[1:-1] for row in part["rows"]],
            [36, 55, 100],
        )
        table(
            "Measured limits",
            ["Field", "Saved value"],
            [list(row) for row in parts[-1]["rows"]],
            [55, 100],
        )
    workbook.close()
    return output.getvalue()
