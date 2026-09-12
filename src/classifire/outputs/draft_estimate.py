"""Pure Estimate and complete report profiles over a validated retained snapshot."""

from __future__ import annotations

import io
import math
import unicodedata
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from typing import Any

import xlsxwriter  # type: ignore[import-untyped]
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from ..services.draft_scope_evidence import ENTITY_EVIDENCE_SCHEMAS, WORKBOOK_EVIDENCE_SCHEMAS
from .common import ATTRIBUTION
from .draft_branding import DraftLogo as _Logo
from .draft_branding import supplied_logo_path as _logo_path
from .draft_scope import (
    _FONT,
    _append_scope_content,
    _collection_reviews,
    _control_text,
    _font_coverage,
    _page_reference_fields,
    _page_reference_id,
    _pdf_text,
    _segments,
)
from .draft_system_review import sections as system_sections
from .draft_system_review import summary as system_summary
from .xlsx import _formats

_UNKNOWN = "Unknown / unavailable"
_COMPLETE_NOTICE = (
    "Complete report profile means all available saved sections are included, not that the "
    "evidence or estimate is complete. Physical claims remain unreviewed; technical "
    "applicability, complete commercial recovery, tax and human release remain unavailable. "
    "Only the selected saved Estimate and its embedded Scope/review are reported."
)


def complete_coverage(estimate: dict[str, Any]) -> list[tuple[str, str]]:
    """Describe retained section availability without calculating new results."""
    return [
        ("Report coverage", _COMPLETE_NOTICE),
        ("Physical Scope", "Saved Draft Scope; assertions and quantities remain unreviewed"),
        (
            "Technical review",
            "Saved unapproved candidate review; suitability remains unresolved"
            if estimate["system_match"] is not None
            else "Unavailable - no System Match attached to this Estimate revision",
        ),
        (
            "Commercial work",
            "Saved provisional lines and changes; unknown or omitted work is not recovered"
            if estimate["lines"]
            else "Unavailable - no Estimate work lines recorded; zero subtotal is not a quote",
        ),
    ]


_COLLECTION_NOTICE = (
    "Complete report profile includes the selected saved Estimate and selected row reviews; "
    "it does not establish complete evidence, technical suitability, commercial recovery "
    "or human release. The Estimate and its prices are unchanged. Additional report-only "
    "reviews are context, not pricing inputs. Shared Services remain distinct at each "
    "Opening; a blank opening has no Service. Review records are not work quantities."
)


def complete_report_coverage(
    estimate: dict[str, Any], reviews: list[dict[str, Any]]
) -> list[tuple[str, str]]:
    """Collection coverage over validated exact inputs, without changing the Estimate."""
    bound = estimate["system_match"]
    legacy = complete_coverage(estimate)
    return [
        ("Report coverage", _COLLECTION_NOTICE),
        legacy[1],
        (
            "Estimate-bound review",
            f"{bound['artifact_id']} / revision {bound['revision']} / SHA-256 {bound['sha256']}. "
            "Unapproved saved reference; no technical suitability is established."
            if bound is not None
            else "None attached to this Estimate; selected reviews are report-only context",
        ),
        (
            "Additional technical context",
            f"{len(reviews) - (1 if bound is not None else 0)} additional saved row reviews. "
            "Unapproved report-only context; no price, quantity or recovery change.",
        ),
        legacy[3],
    ]


def _complete_reviews(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    if not snapshot.get("system_matches"):
        return []
    from ..services.draft_estimate_reports import report_matches
    from ..services.draft_scope_reports import MULTI_SYSTEM_REPORT_SCHEMA_VERSION

    # Adapt only the presentation fields; _verified already validated the Complete snapshot.
    result = _collection_reviews(
        {
            "schema_version": MULTI_SYSTEM_REPORT_SCHEMA_VERSION,
            "scope": snapshot["estimate"]["scope"],
            "system_matches": report_matches(snapshot),
        }
    )
    bound = snapshot["estimate"]["system_match"]
    bound_key = f"{bound['artifact_id']} / revision {bound['revision']}" if bound else None
    for review in result:
        review["identity"].insert(
            0,
            (
                "Relationship to Estimate",
                "Estimate-bound review - unapproved saved reference"
                if review["key"] == bound_key
                else "Additional report-only context - not a pricing input",
            ),
        )
    return result


_LIMITS = (
    "Draft, unreviewed and provisional. Partial AUD subtotal excluding tax; tax is not calculated. "
    "Service lines exclude shared-opening closure. Nonblank-opening work is unassessed. "
    "This report does not establish technical compatibility, complete recovery or human release."
)


def _verified(snapshot: dict[str, Any]) -> dict[str, Any]:
    from ..services.draft_estimate_reports import validate_report_snapshot

    validate_report_snapshot(snapshot)
    return deepcopy(snapshot)


def _number(value: str | None) -> str:
    return _UNKNOWN if value is None else value


def _metadata(report: dict[str, Any]) -> list[tuple[str, Any]]:
    estimate = report["estimate"]
    rows: list[tuple[str, Any]] = [
        ("Project", report["project"]["name"]),
        ("Project reference", report["project"]["reference"]),
        ("Status", "DRAFT - UNREVIEWED"),
        (
            "Coverage",
            _LIMITS
            + (
                " Imported values and source/approval claims are foreign and unverified."
                if estimate.get("import_origin")
                else ""
            ),
        ),
        (
            "Partial priced subtotal excluding tax (AUD)",
            estimate["summary"]["priced_subtotal_ex_tax"],
        ),
        ("Tax", "Not calculated"),
        ("Technical status", "Unapproved"),
        ("Priced lines", estimate["summary"]["priced_line_count"]),
        ("Unpriced lines", len(estimate["summary"]["unpriced_line_ids"])),
        ("Omitted lines", len(estimate["summary"]["omitted_line_ids"])),
        ("Report ID", report["report_id"]),
        ("Report snapshot SHA-256", report["sha256"]),
        ("Report created at (UTC)", report["created_at"]),
        ("Report created by", report["created_by"]),
        ("Report schema", report["schema_version"]),
        ("Profile / renderer version", f"{report['profile']} / {report['render_version']}"),
        ("Estimate ID", estimate["artifact_id"]),
        ("Estimate revision", estimate["revision"]),
        ("Estimate SHA-256", estimate["sha256"]),
        ("Estimate created at (UTC)", estimate["created_at"]),
        ("Estimate created by", estimate["created_by"]),
        (
            "Pricing basis",
            (
                "Manual rates and explicitly selected exact workbook rates; "
                "source selections remain unapproved"
                if estimate.get("pricing_sources")
                else "User-defined manual unit sell rates; no pricing library or inferred rate"
            ),
        ),
        (
            "Calculation",
            "Multiply quantity by unrounded rate; round each line half up to cents; "
            "sum the rounded active priced lines. Unknown or omitted work is excluded.",
        ),
        ("Scope ID", estimate["scope"]["artifact_id"]),
        ("Scope revision", estimate["scope"]["revision"]),
        ("Scope SHA-256", estimate["scope"]["sha256"]),
        ("Scope provenance", estimate["scope"]["provenance"]),
    ]
    match = estimate["system_match"]
    if match is None:
        rows.append(("Candidate review", "Unavailable - none attached"))
    else:
        rows.extend(
            [
                ("Candidate review ID", match["artifact_id"]),
                ("Candidate review revision", match["revision"]),
                ("Candidate review SHA-256", match["sha256"]),
                ("Candidate review status", "Unapproved reference only; not a selected system"),
            ]
        )
    if report["profile"] == "complete":
        rows.extend(
            complete_report_coverage(estimate, report["system_matches"])
            if report.get("system_matches")
            else complete_coverage(estimate)
        )
    return rows


def _context_rows(report: dict[str, Any]) -> list[list[Any]]:
    estimate = report["estimate"]
    rows: list[list[Any]] = []
    scope = estimate["scope"]["content"]
    for kind in ("defects", "openings", "services", "observations"):
        for item in scope[kind]:
            for key, value in item.items():
                rows.append(
                    [
                        kind,
                        item["id"],
                        key,
                        ", ".join(value)
                        if isinstance(value, list)
                        else _UNKNOWN
                        if value is None
                        else str(value),
                    ]
                )
    for kind in ("assumptions", "exclusions"):
        for index, value in enumerate(scope[kind], 1):
            rows.append([kind, str(index), "text", value])
    for index, source in enumerate(estimate["scope"].get("import_lineage", []), 1):
        for key, value in source.items():
            rows.append(["Unverified imported claim", str(index), key, str(value)])
    for ref in estimate["scope"].get("evidence_refs", []):
        for key, value in _page_reference_fields(estimate["scope"], ref):
            rows.append(
                [
                    "Saved evidence-review claim"
                    if estimate["scope"]["schema_version"] in WORKBOOK_EVIDENCE_SCHEMAS
                    else "Saved page-review claim",
                    _page_reference_id(ref),
                    key,
                    str(value),
                ]
            )
    return rows


def _pricing_rows(report: dict[str, Any]) -> list[list[str]]:
    rows = []
    for selection in report["estimate"].get("pricing_sources", []):
        identity = selection["line_id"] + " / " + selection["event_id"]
        source = selection["original_filename"] + " / " + selection["row"]["sheet"]
        for key in (
            "method",
            "approval_status",
            "recovery_note",
            "source_sha256",
            "document_sha256",
            "scan_sha256",
        ):
            rows.append([identity, source, key, "", str(selection[key])])
        for key, cell in selection["row"]["fields"].items():
            rows.append(
                [
                    identity,
                    source,
                    key,
                    cell["address"] if cell else "",
                    (cell["value"] + " (" + cell["kind"] + ")") if cell else _UNKNOWN,
                ]
            )
    return rows


def _coverage_rows(report: dict[str, Any]) -> list[list[str]]:
    estimate = report["estimate"]
    openings = {item["id"]: item["label"] for item in estimate["scope"]["content"]["openings"]}
    rows = [
        ["No estimate line", item["target_kind"], item["target_id"], item["label"]]
        for item in estimate["summary"]["unrepresented_targets"]
    ]
    rows.extend(
        [
            ["Opening work unassessed", "opening", item, openings[item]]
            for item in estimate["summary"]["unassessed_opening_ids"]
        ]
    )
    rows.extend(
        [
            [line["pricing_status"], line["target_kind"], line["target_id"], line["label"]]
            for line in estimate["lines"]
            if line["pricing_status"] != "priced"
        ]
    )
    return rows


def render_estimate_report_pdf(snapshot: dict[str, Any]) -> bytes:
    report = _verified(snapshot)
    collection = _complete_reviews(report)
    _font_coverage()
    body = ParagraphStyle("EstimateBody", fontName=_FONT, fontSize=9, leading=13, spaceAfter=5)
    heading = ParagraphStyle(
        "EstimateHeading",
        parent=body,
        fontSize=14,
        leading=18,
        spaceBefore=12,
        spaceAfter=8,
        keepWithNext=True,
        textColor=colors.HexColor("#d9232b"),
    )
    title = ParagraphStyle("EstimateTitle", parent=heading, fontSize=23, leading=29)
    small = ParagraphStyle("EstimateSmall", parent=body, fontSize=7, leading=10)
    story: list[Any] = [_Logo(), Spacer(1, 5 * mm)]

    def text(value: object, style: ParagraphStyle = body) -> None:
        story.append(Paragraph(_pdf_text(value), style))

    complete = report["profile"] == "complete"
    report_title = "Complete Draft Report" if complete else "Draft Estimate Report"
    text(report_title, title)
    for label, value in _metadata(report)[:10]:
        text(f"{label}: {value}")
    estimate = report["estimate"]
    if complete:
        text("Included sections and limitations", heading)
        for label, value in (
            complete_report_coverage(estimate, report["system_matches"])
            if collection
            else complete_coverage(estimate)
        ):
            text(f"{label}: {value}")
        item_heading = ParagraphStyle(
            "CompleteItem",
            parent=body,
            fontSize=11,
            leading=15,
            spaceBefore=9,
            keepWithNext=True,
        )
        _append_scope_content(estimate["scope"], text, heading, item_heading, small)
        text("Saved technical review summary", heading)
        if collection:
            for review in collection:
                text(review["label"], item_heading)
                for label, value in [*review["identity"], *review["summary"]]:
                    text(f"{label}: {value}")
        elif estimate["system_match"] is not None:
            for label, value in system_summary(estimate["system_match"]):
                text(f"{label}: {value}")
        else:
            text("Unavailable - no System Match attached to this Estimate revision.")
    text("Saved work lines", heading)
    if not estimate["lines"]:
        text("No work lines. No work is priced.")
    for index, line in enumerate(estimate["lines"], 1):
        text(f"{index}. {line['label']} - {line['pricing_status']}", heading)
        text(line["description"])
        for label, value in [
            ("Unit", line["unit"]),
            ("Quantity", _number(line["quantity"])),
            ("Unit sell rate excluding tax (AUD)", _number(line["unit_sell_rate"])),
            ("Line subtotal excluding tax (AUD)", _number(line["subtotal_ex_tax"])),
            ("Original quantity", _number(line["original_quantity"])),
            ("Original unit sell rate (AUD)", _number(line["original_rate"])),
            ("Work basis", line["work_basis"].replace("_", " ")),
            ("Rate / work source note", line["source_note"]),
            ("Omission reason", line["omission_reason"] or "None"),
            ("Line ID", line["line_id"]),
            ("Target", line["recovery_key"]),
            ("Related opening IDs", ", ".join(line["opening_ids"]) or "None / unresolved"),
        ]:
            text(f"{label}: {value}")
        text("Original values and changes", heading)
        for event in line["history"]:
            text(f"{event['action']} - {event['created_at']} - {event['created_by']}")
            text(
                f"Quantity: {_number(event['before_quantity'])} to {_number(event['quantity'])}; "
                f"rate: {_number(event['before_rate'])} to {_number(event['unit_sell_rate'])} AUD"
            )
            text("Reason: " + (event["reason"] or "Initial values recorded"))
            text("Event ID: " + event["event_id"], small)
    if estimate.get("pricing_sources"):
        text("Workbook rate selections - unapproved", heading)
        text("Historical source selections remain below even after a later manual rate override.")
        for identity, source, field, cell, value in _pricing_rows(report):
            text(f"{source} / {field} / {cell}: {value}", small)
            if field == "method":
                text("Line / event: " + identity, small)
    text("Unpriced and unassessed work", heading)
    text(_LIMITS)
    for status, kind, identifier, label in _coverage_rows(report):
        text(f"{status}: {label} ({kind}, {identifier})")
    text("Saved Scope provenance" if complete else "Saved Scope context and source claims", heading)
    text(
        "Scope assertions and imported history remain unreviewed. No technical approval is implied."
    )
    if estimate["scope"]["schema_version"] in ENTITY_EVIDENCE_SCHEMAS:
        text(
            "Review status compares saved claims with this selected Scope revision. "
            "Current source and scan checks are performed separately; "
            "no physical approval is granted."
        )
    for kind, identifier, label, value in _context_rows(report):
        if complete and kind in estimate["scope"]["content"]:
            continue
        text(f"{kind} / {identifier} / {label}: {value}", small)
    if collection:
        text("Retained technical evidence and decisions", heading)
        for review in collection:
            text(review["label"], heading)
            text("Exact saved review: " + review["key"], small)
            text(review["identity"][0][1], small)
            for section in review["sections"]:
                text(section["title"], heading)
                for label, value in section["rows"]:
                    text(f"{label}: {value}", small)
    elif complete and estimate["system_match"] is not None:
        text("Retained technical evidence and decisions", heading)
        for section in system_sections(estimate["system_match"]):
            text(section["title"], heading)
            for label, value in section["rows"]:
                text(f"{label}: {value}", small)
    text("Report provenance", heading)
    for label, value in _metadata(report)[10:]:
        text(f"{label}: {value}", small)

    def footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setFont(_FONT, 7)
        canvas.drawString(
            17 * mm,
            14 * mm,
            "CLASSIFIRE | DRAFT - UNREVIEWED | " + ("Complete" if complete else "Estimate-only"),
        )
        canvas.drawRightString(A4[0] - 17 * mm, 14 * mm, f"Page {document.page}")
        canvas.setFont(_FONT, 6)
        canvas.drawString(17 * mm, 10 * mm, ATTRIBUTION)
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
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def _safe_numeric(value: str | None) -> float | None:
    """Optional numeric convenience; exact text remains authoritative in every case."""
    if value is None:
        return None
    decimal = Decimal(value)
    number = float(decimal)
    significant = list(decimal.as_tuple().digits)
    while significant and significant[-1] == 0:
        significant.pop()
    if len(significant) > 15 or Decimal(str(number)) != decimal:
        return None
    return number


def render_estimate_report_xlsx(snapshot: dict[str, Any]) -> bytes:
    report = _verified(snapshot)
    collection = _complete_reviews(report)
    complete = report["profile"] == "complete"
    report_title = "Complete Draft Report" if complete else "Draft Estimate Report"
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
    formats = _formats(workbook)
    number_format = workbook.add_format({"border": 1, "num_format": "0.00", "valign": "top"})
    integer_format = workbook.add_format({"border": 1, "num_format": "0", "valign": "top"})
    workbook.set_properties(
        {
            "title": "CLASSIFIRE " + report_title,
            "author": "Ceasefire PFP",
            "created": datetime.fromisoformat(report["created_at"]).replace(tzinfo=None),
            "comments": report["sha256"],
        }
    )

    def table(name: str, headers: list[str], rows: list[list[Any]], widths: list[int]) -> None:
        sheet = workbook.add_worksheet(name)
        sheet.set_column(0, 0, 8)
        for column, width in enumerate(widths, 1):
            sheet.set_column(column, column, width)
        if name == "Summary":
            sheet.write_string(
                0,
                2,
                "CLASSIFIRE " + report_title,
                workbook.add_format(
                    {
                        "font_size": 20,
                        "bold": True,
                        "valign": "vcenter",
                        "text_wrap": True,
                    }
                ),
            )
        else:
            sheet.merge_range(
                0,
                1,
                0,
                len(headers),
                ("CLASSIFIRE Complete Draft - " if complete else "CLASSIFIRE Draft Estimate - ")
                + name,
                formats["title"],
            )
        sheet.set_row(0, 32)
        if name == "Summary":
            # Original square PNG remains embedded byte-for-byte, with white canvas.
            sheet.set_row(0, 110)
            sheet.insert_image(
                0,
                1,
                str(_logo_path()),
                {
                    "x_scale": 140 / 1254,
                    "y_scale": 140 / 1254,
                    "object_position": 1,
                },
            )
        sheet.merge_range(
            1,
            1,
            1,
            len(headers),
            "DRAFT - UNREVIEWED | Partial AUD amounts | Tax not calculated",
            formats["subtitle"],
        )
        sheet.merge_range(
            2,
            1,
            2,
            len(headers),
            "Estimate revision "
            + str(report["estimate"]["revision"])
            + " | Report "
            + report["report_id"],
            formats["subtitle"],
        )
        sheet.merge_range(
            3,
            1,
            3,
            len(headers),
            "Exact decimal text is authoritative. Numeric subtotal is optional and blank "
            "beyond safe precision. No formulas or automatic recalculation.",
            formats["text"],
        )
        sheet.set_row(3, 32)
        for column, label in enumerate(["Part", *headers]):
            sheet.write_string(5, column, label, formats["header"])
        sheet.set_row(5, 36)
        current = 6
        for values in rows:
            chunks = [
                _segments(_control_text(value), max(width - 3, 8))
                if isinstance(value, str)
                else [value]
                for value, width in zip(values, widths, strict=True)
            ]
            count = max(len(parts) for parts in chunks)
            for part in range(count):
                sheet.write_string(current, 0, f"{part + 1}/{count}", formats["text"])
                height = 24
                for column, (parts, width) in enumerate(zip(chunks, widths, strict=True), 1):
                    value = parts[part] if part < len(parts) else None
                    if part and column == 1 and len(parts) == 1:
                        value = parts[0]
                    if value is None:
                        sheet.write_blank(current, column, None, formats["text"])
                    elif isinstance(value, (int, float)):
                        sheet.write_number(
                            current,
                            column,
                            value,
                            integer_format if isinstance(value, int) else number_format,
                        )
                    else:
                        sheet.write_string(current, column, value, formats["text"])
                        height = max(
                            height,
                            15
                            * sum(
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
                            )
                            + 8,
                        )
                sheet.set_row(current, min(height, 180))
                current += 1
        sheet.autofilter(5, 0, max(5, current - 1), len(headers))
        sheet.freeze_panes(6, 2)
        sheet.hide_gridlines(2)
        sheet.set_landscape()
        sheet.fit_to_pages(1, 0)
        sheet.repeat_rows(5)
        sheet.set_header("&LCLASSIFIRE " + report_title + "&RUnreviewed")
        sheet.set_footer("&L" + report["report_id"] + "&RPage &P of &N")
        sheet.print_area(0, 0, max(6, current - 1), len(headers))

    table("Summary", ["Field", "Value"], [list(row) for row in _metadata(report)], [44, 105])
    estimate = report["estimate"]
    table(
        "Lines",
        [
            "Line ID",
            "Label",
            "Unit",
            "Exact quantity",
            "Exact rate AUD",
            "Exact subtotal AUD",
            "Numeric subtotal AUD",
            "Status",
            "Target / recovery key",
        ],
        [
            [
                line["line_id"],
                line["label"],
                line["unit"],
                _number(line["quantity"]),
                _number(line["unit_sell_rate"]),
                _number(line["subtotal_ex_tax"]),
                _safe_numeric(line["subtotal_ex_tax"]),
                line["pricing_status"],
                line["recovery_key"],
            ]
            for line in estimate["lines"]
        ],
        [38, 38, 10, 24, 24, 28, 24, 14, 48],
    )
    if estimate.get("pricing_sources"):
        table(
            "Pricing sources",
            ["Line / event", "Source", "Field", "Cell", "Exact source value"],
            _pricing_rows(report),
            [40, 40, 28, 14, 70],
        )
    details = []
    history = []
    for line in estimate["lines"]:
        for key in (
            "description",
            "source_note",
            "original_quantity",
            "original_rate",
            "work_basis",
            "omission_reason",
            "created_by",
            "created_at",
        ):
            details.append([line["line_id"], key.replace("_", " "), _number(line[key])])
        for opening in line["opening_ids"]:
            details.append([line["line_id"], "opening ID", opening])
        for event in line["history"]:
            for key, value in event.items():
                history.append(
                    [line["line_id"], event["event_id"], key.replace("_", " "), _number(value)]
                )
    table("Line details", ["Line ID", "Field", "Value"], details, [38, 28, 100])
    table("History", ["Line ID", "Event ID", "Field", "Value"], history, [38, 38, 24, 90])
    table(
        "Coverage",
        ["Status", "Kind", "Target ID", "Label"],
        _coverage_rows(report),
        [32, 20, 38, 60],
    )
    table(
        "Scope context",
        ["Kind", "Item ID", "Field", "Value"],
        _context_rows(report),
        [30, 38, 28, 90],
    )
    if collection:
        table(
            "Technical summary",
            ["Exact review", "Field", "Saved finding"],
            [
                [review["key"], label, value]
                for review in collection
                for label, value in [
                    ("Selected row", review["label"]),
                    *review["identity"],
                    *review["summary"],
                ]
            ],
            [45, 40, 100],
        )
        table(
            "Review and coverage",
            ["Exact review", "Field", "Saved value"],
            [
                [review["key"], *row]
                for review in collection
                for row in [review["identity"][0], *review["sections"][0]["rows"]]
            ],
            [45, 40, 100],
        )
        table(
            "System candidates",
            ["Exact review", "Candidate", "Field", "Saved value"],
            [
                [review["key"], part["title"], *row]
                for review in collection
                for part in review["sections"][1:-1]
                for row in part["rows"]
            ],
            [45, 36, 55, 100],
        )
        table(
            "Measured limits",
            ["Exact review", "Field", "Saved value"],
            [
                [review["key"], *row]
                for review in collection
                for row in review["sections"][-1]["rows"]
            ],
            [45, 55, 100],
        )
    elif complete:
        match = estimate["system_match"]
        table(
            "Technical summary",
            ["Field", "Saved finding"],
            [list(row) for row in system_summary(match)]
            if match is not None
            else [
                [
                    "Technical review",
                    "Unavailable - no System Match attached to this Estimate revision",
                ]
            ],
            [55, 100],
        )
        if match is not None:
            parts = system_sections(match)
            table(
                "Review and coverage",
                ["Field", "Saved value"],
                [list(row) for row in parts[0]["rows"]],
                [55, 100],
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
