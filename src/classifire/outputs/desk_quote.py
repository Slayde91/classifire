"""Client-facing renderers for the explicitly non-technical desk-quote path."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import xlsxwriter  # type: ignore[import-untyped]
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ..services.desk_quote import verify_desk_quote_snapshot
from .common import d, logo_path
from .pdf import DARK, LIGHT, RED, _currency, _page, _styles
from .xlsx import _formats, _insert_brand

DESK_QUOTE_ATTRIBUTION = "CLASSIFIRE is a passive-fire estimating system produced by Ceasefire PFP."


def _money(value: Any, currency: str) -> float:
    return float(d(value))


def _evidence_text(assumption: dict[str, Any]) -> str:
    return "\n".join(
        (
            f"{item['evidence_reference']} [evidence {item['evidence_source_id']}; "
            f"SHA-256 {item['file_sha256']}] - {item['locator']}"
        )
        for item in assumption["evidence_locators"]
    )


def _rate_binding_text(allowance: dict[str, Any]) -> str:
    """Return the immutable pricing evidence behind a rendered allowance."""
    binding = allowance["rate_binding"]
    entry_version = binding.get("entry_version")
    entry = binding["pkb_entry_id"]
    if entry_version:
        entry = f"{entry} v{entry_version}"
    return (
        f"{entry}; pricing release {binding['pricing_release_version']} "
        f"(SHA-256 {binding['pricing_release_hash']}); record "
        f"{binding['pricing_record_id']} (SHA-256 {binding['record_source_hash']})"
    )


def render_desk_quote_workbook(snapshot: dict[str, Any], output_path: Path) -> Path:
    """Render a source-linked desk quote without pretending it is a locked estimate."""

    verify_desk_quote_snapshot(snapshot)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    quote = snapshot["quote"]
    totals = snapshot["totals"]
    currency = quote["currency"]
    workbook = xlsxwriter.Workbook(str(output_path))
    formats = _formats(workbook)
    workbook.set_properties(
        {
            "title": f"CLASSIFIRE Desk Quote - {quote['quote_reference']}",
            "author": "Ceasefire PFP",
            "comments": DESK_QUOTE_ATTRIBUTION,
            "subject": "Assumption-led passive-fire commercial proposal",
        }
    )

    summary = workbook.add_worksheet("Desk Quote Summary")
    allowances_sheet = workbook.add_worksheet("Commercial Allowances")
    register = workbook.add_worksheet("Assumption Register")
    _insert_brand(summary)
    summary.set_row(0, 85)
    summary.set_column("A:A", 28)
    summary.set_column("B:B", 58)
    summary.set_column("C:C", 24)
    summary.set_column("D:D", 34)
    summary.write("A6", "CLASSIFIRE Desk Quote Proposal", formats["title"])
    summary.merge_range(
        "A7:D7", "ASSUMPTION-LED COMMERCIAL ALLOWANCE - SUBJECT TO VERIFICATION", formats["header"]
    )
    summary.write("A8", DESK_QUOTE_ATTRIBUTION, formats["subtitle"])

    details = [
        ("Project", quote["project_name"], "Quote", quote["quote_reference"]),
        ("Project reference", quote["project_reference"], "Client", quote.get("client_name")),
        ("Site", quote.get("site_address"), "Technical position", snapshot["technical_position"]),
        ("Report scope", quote["report_scope"], "Snapshot hash", snapshot["snapshot_hash"]),
    ]
    for row, (left_label, left_value, right_label, right_value) in enumerate(details, 10):
        summary.write(row, 0, left_label, formats["label"])
        summary.write(row, 1, left_value or "Not provided", formats["text"])
        summary.write(row, 2, right_label, formats["label"])
        summary.write(row, 3, right_value or "Not provided", formats["text"])

    summary.write("A15", "Commercial Summary", formats["section"])
    summary.merge_range("A15:D15", "Commercial Summary", formats["section"])
    summary.write("C17", "Subtotal excluding tax", formats["label"])
    summary.write_number("D17", _money(totals["subtotal_ex_tax"], currency), formats["money"])
    summary.write("C18", quote["tax_name"], formats["label"])
    summary.write_number("D18", _money(totals["tax_total"], currency), formats["money"])
    summary.write("C19", "Total including tax", formats["header"])
    summary.write_number("D19", _money(totals["total_incl_tax"], currency), formats["total"])

    row = 22
    summary.write(row, 0, "Mandatory Qualifications", formats["section"])
    summary.merge_range(row, 0, row, 3, "Mandatory Qualifications", formats["section"])
    for value in snapshot["qualifications"]:
        row += 1
        summary.merge_range(row, 0, row, 3, f"• {value}", formats["text"])
    row += 2
    summary.write(row, 0, "Exclusions and Variation Risks", formats["section"])
    summary.merge_range(row, 0, row, 3, "Exclusions and Variation Risks", formats["section"])
    if snapshot["exclusions"]:
        for value in snapshot["exclusions"]:
            row += 1
            summary.merge_range(row, 0, row, 3, f"• {value}", formats["text"])
    else:
        row += 1
        summary.merge_range(row, 0, row, 3, "• No additional exclusions recorded.", formats["text"])
    row += 2
    summary.merge_range(row, 0, row, 3, f"Generated {snapshot['generated_utc']}", formats["footer"])
    summary.freeze_panes(9, 0)

    allowance_headers = [
        "Allowance",
        "Description",
        "Quantity",
        "Unit",
        "Unit Rate Ex Tax",
        "Subtotal Ex Tax",
        "Governed Pricing Record",
        "Assumption References",
    ]
    for column, header in enumerate(allowance_headers):
        allowances_sheet.write(0, column, header, formats["header"])
    for row, allowance in enumerate(snapshot["allowances"], 1):
        subtotal = Decimal(allowance["quantity"]) * Decimal(allowance["unit_rate_ex_tax"])
        values = [
            allowance["allowance_id"],
            allowance["description"],
            _money(allowance["quantity"], currency),
            allowance["unit"],
            _money(allowance["unit_rate_ex_tax"], currency),
            float(subtotal),
            _rate_binding_text(allowance),
            ", ".join(allowance["assumption_ids"]),
        ]
        for column, value in enumerate(values):
            if column in {2}:
                allowances_sheet.write_number(row, column, value, formats["qty"])
            elif column in {4, 5}:
                allowances_sheet.write_number(row, column, value, formats["money"])
            else:
                allowances_sheet.write(row, column, value, formats["text"])
    allowances_sheet.autofilter(
        0, 0, max(len(snapshot["allowances"]), 1), len(allowance_headers) - 1
    )
    allowances_sheet.freeze_panes(1, 2)
    allowances_sheet.set_column(0, 0, 18)
    allowances_sheet.set_column(1, 1, 58)
    allowances_sheet.set_column(2, 5, 18)
    allowances_sheet.set_column(6, 7, 42)

    register_headers = [
        "Assumption",
        "Subject",
        "Fact Type",
        "Assumed Value",
        "Status",
        "Probability",
        "Confidence",
        "Evidence Location",
        "Rationale",
        "Alternative Explanation",
        "Commercial Treatment",
        "Required Verification",
    ]
    for column, header in enumerate(register_headers):
        register.write(0, column, header, formats["header"])
    for row, assumption in enumerate(snapshot["assumptions"], 1):
        values = [
            assumption["assumption_id"],
            assumption["subject_reference"],
            assumption["fact_type"],
            assumption.get("value") or "Unresolved",
            assumption["status"],
            f"{assumption['probability_percent']}%",
            assumption["confidence"],
            _evidence_text(assumption),
            assumption["rationale"],
            assumption["alternative_explanation"],
            assumption["commercial_treatment"],
            assumption["verification_action"],
        ]
        for column, value in enumerate(values):
            register.write(row, column, value, formats["text"])
    register.autofilter(0, 0, max(len(snapshot["assumptions"]), 1), len(register_headers) - 1)
    register.freeze_panes(1, 3)
    register.set_column(0, 2, 20)
    register.set_column(3, 6, 16)
    register.set_column(7, 11, 45)

    workbook.close()
    return output_path


def render_desk_quote_pdf(snapshot: dict[str, Any], output_path: Path) -> Path:
    """Render a PDF desk quote with assumptions, exclusions, and pricing inseparable."""

    verify_desk_quote_snapshot(snapshot)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    quote = snapshot["quote"]
    totals = snapshot["totals"]
    styles = _styles()
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=(210 * mm, 297 * mm),
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=20 * mm,
        title=f"CLASSIFIRE Desk Quote - {quote['quote_reference']}",
        author="Ceasefire PFP",
        subject="Assumption-led passive-fire commercial proposal",
    )
    story: list[Any] = []
    logo = Image(str(logo_path()), width=45 * mm, height=25 * mm, kind="proportional")
    story.append(
        Table(
            [[logo]],
            colWidths=[170 * mm],
            style=TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]),
        )
    )
    story.append(Paragraph("CLASSIFIRE DESK QUOTE PROPOSAL", styles["title"]))
    story.append(
        Paragraph(
            "ASSUMPTION-LED COMMERCIAL ALLOWANCE - SUBJECT TO VERIFICATION", styles["subtitle"]
        )
    )
    story.append(Paragraph(DESK_QUOTE_ATTRIBUTION, styles["subtitle"]))
    info = [
        ["Project", quote["project_name"], "Quote", quote["quote_reference"]],
        [
            "Project reference",
            quote["project_reference"],
            "Client",
            quote.get("client_name") or "Not provided",
        ],
        [
            "Site",
            quote.get("site_address") or "Not provided",
            "Generated",
            snapshot["generated_utc"][:19],
        ],
        [
            "Technical position",
            snapshot["technical_position"],
            "Snapshot",
            snapshot["snapshot_hash"],
        ],
    ]
    info_table = Table(info, colWidths=[30 * mm, 55 * mm, 30 * mm, 55 * mm])
    info_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), LIGHT),
                ("BACKGROUND", (2, 0), (2, -1), LIGHT),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
            ]
        )
    )
    story.extend([info_table, Spacer(1, 7 * mm)])
    story.append(Paragraph("Commercial allowances", styles["h1"]))
    allowance_rows: list[list[str | Paragraph]] = [
        ["Allowance", "Description", "Qty", "Unit", "Ex tax", "Assumptions"]
    ]
    for allowance in snapshot["allowances"]:
        subtotal = Decimal(allowance["quantity"]) * Decimal(allowance["unit_rate_ex_tax"])
        allowance_rows.append(
            [
                allowance["allowance_id"],
                Paragraph(allowance["description"], styles["small"]),
                allowance["quantity"],
                allowance["unit"],
                _currency(subtotal, quote["currency"]),
                ", ".join(allowance["assumption_ids"]),
            ]
        )
    allowance_table = Table(
        allowance_rows,
        colWidths=[18 * mm, 64 * mm, 16 * mm, 18 * mm, 28 * mm, 36 * mm],
        repeatRows=1,
    )
    allowance_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), DARK),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (2, 1), (4, -1), "RIGHT"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
            ]
        )
    )
    story.append(allowance_table)
    story.append(Spacer(1, 5 * mm))
    total_rows = [
        ["Subtotal excluding tax", _currency(totals["subtotal_ex_tax"], quote["currency"])],
        [quote["tax_name"], _currency(totals["tax_total"], quote["currency"])],
        ["TOTAL INCLUDING TAX", _currency(totals["total_incl_tax"], quote["currency"])],
    ]
    total_table = Table(total_rows, colWidths=[95 * mm, 50 * mm], hAlign="RIGHT")
    total_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -2), "Helvetica"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("BACKGROUND", (0, -1), (-1, -1), DARK),
                ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("BOX", (0, 0), (-1, -1), 0.5, DARK),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
            ]
        )
    )
    story.extend(
        [total_table, Spacer(1, 7 * mm), Paragraph("Commercial pricing basis", styles["h1"])]
    )
    story.append(
        Paragraph(
            "Each allowance uses an active, hash-bound pricing-library record. "
            "This commercial rate basis does not establish technical suitability.",
            styles["body"],
        )
    )
    for allowance in snapshot["allowances"]:
        story.append(
            Paragraph(
                f"<b>{allowance['allowance_id']}</b>: {_rate_binding_text(allowance)}",
                styles["small"],
            )
        )
    story.extend([Spacer(1, 7 * mm), Paragraph("Assumption register", styles["h1"])])
    assumption_rows: list[list[str | Paragraph]] = [
        ["ID", "Assumed condition", "Evidence", "Probability", "Treatment", "Verification"]
    ]
    for assumption in snapshot["assumptions"]:
        assumed_condition = (
            f"{assumption['subject_reference']} - "
            f"{assumption.get('value') or 'Unresolved'}<br/>"
            f"{assumption['rationale']}<br/><b>Alternative:</b> "
            f"{assumption['alternative_explanation']}"
        )
        assumption_rows.append(
            [
                assumption["assumption_id"],
                Paragraph(assumed_condition, styles["small"]),
                Paragraph(_evidence_text(assumption).replace("\n", "<br/>"), styles["small"]),
                f"{assumption['probability_percent']}%\n{assumption['confidence']}",
                assumption["commercial_treatment"],
                Paragraph(assumption["verification_action"], styles["small"]),
            ]
        )
    assumption_table = Table(
        assumption_rows,
        colWidths=[16 * mm, 50 * mm, 35 * mm, 18 * mm, 25 * mm, 30 * mm],
        repeatRows=1,
    )
    assumption_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), RED),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 6.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
            ]
        )
    )
    story.append(assumption_table)
    story.extend([Spacer(1, 7 * mm), Paragraph("Mandatory qualifications", styles["h1"])])
    for qualification in snapshot["qualifications"]:
        story.append(Paragraph(f"• {qualification}", styles["body"]))
    story.append(Paragraph("Exclusions and variation risks", styles["h1"]))
    for exclusion in snapshot["exclusions"] or ["No additional exclusions recorded."]:
        story.append(Paragraph(f"• {exclusion}", styles["body"]))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(f"Snapshot hash: {snapshot['snapshot_hash']}", styles["small"]))
    document.build(story, onFirstPage=_page, onLaterPages=_page)
    return output_path


__all__ = ["render_desk_quote_pdf", "render_desk_quote_workbook"]
