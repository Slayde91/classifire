from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .common import ATTRIBUTION, d, logo_path, verify_snapshot

DARK = colors.HexColor("#111827")
CYAN = colors.HexColor("#16CBEA")
RED = colors.HexColor("#F01419")
ORANGE = colors.HexColor("#F47B0B")
GOLD = colors.HexColor("#F0B90B")
LIGHT = colors.HexColor("#F3F4F6")
MID = colors.HexColor("#6B7280")


def _currency(value: Any, currency: str) -> str:
    return f"{currency} {d(value):,.2f}"


def _page(canvas, doc) -> None:  # type: ignore[no-untyped-def]
    canvas.saveState()
    width, _height = A4
    canvas.setStrokeColor(RED)
    canvas.setLineWidth(1.3)
    canvas.line(18 * mm, 15 * mm, width - 18 * mm, 15 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MID)
    canvas.drawString(18 * mm, 10 * mm, ATTRIBUTION)
    canvas.drawRightString(width - 18 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "QFTitle", parent=base["Title"], fontName="Helvetica-Bold", fontSize=22, leading=26,
            textColor=DARK, alignment=TA_CENTER, spaceAfter=8
        ),
        "subtitle": ParagraphStyle(
            "QFSubtitle", parent=base["Normal"], fontName="Helvetica", fontSize=11, leading=15,
            textColor=MID, alignment=TA_CENTER, spaceAfter=12
        ),
        "h1": ParagraphStyle(
            "QFH1", parent=base["Heading1"], fontName="Helvetica-Bold", fontSize=14, leading=18,
            textColor=RED, spaceBefore=8, spaceAfter=6
        ),
        "h2": ParagraphStyle(
            "QFH2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=14,
            textColor=DARK, spaceBefore=5, spaceAfter=4
        ),
        "body": ParagraphStyle(
            "QFBody", parent=base["BodyText"], fontName="Helvetica", fontSize=8.5, leading=12,
            textColor=DARK
        ),
        "small": ParagraphStyle(
            "QFSmall", parent=base["BodyText"], fontName="Helvetica", fontSize=7.2, leading=9,
            textColor=DARK
        ),
        "right": ParagraphStyle(
            "QFRight", parent=base["BodyText"], fontName="Helvetica", fontSize=8.5, leading=12,
            textColor=DARK, alignment=TA_RIGHT
        ),
    }


def render_estimate_pdf(
    snapshot: dict[str, Any], output_path: Path, *, proposal: bool = False
) -> Path:
    verify_snapshot(snapshot)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()
    estimate = snapshot["estimate"]
    project = snapshot["project"]
    currency = estimate["currency"]
    title = "Proposal" if proposal else "Technical Estimate and Audit Report"
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=20 * mm,
        title=f"CLASSIFIRE {title} — {estimate['reference']}",
        author="Ceasefire PFP",
        subject="Passive-fire estimate",
    )
    story: list[Any] = []
    logo_source = str(logo_path())
    logo_probe = Image(logo_source)
    logo = Image(
        logo_source,
        width=35 * mm * (logo_probe.imageWidth / logo_probe.imageHeight),
        height=35 * mm,
    )
    logo.hAlign = "CENTER"
    story.append(logo)
    story.append(Paragraph(title.upper(), styles["title"]))
    story.append(Paragraph(ATTRIBUTION, styles["subtitle"]))
    info = [
        ["Project", project.get("name") or "Not provided", "Estimate", estimate["reference"]],
        [
            "Project reference",
            project.get("reference") or "Not provided",
            "Revision",
            str(estimate["revision"]),
        ],
        [
            "Client",
            project.get("customer") or "Not provided",
            "Generated",
            snapshot.get("generated_utc", "")[:19],
        ],
        [
            "Site",
            project.get("site_address") or "Not provided",
            "Jurisdiction",
            project.get("jurisdiction") or "Not provided",
        ],
        ["Snapshot", snapshot["snapshot_hash"], "Status", estimate.get("status", "")],
    ]
    info_table = Table(info, colWidths=[28 * mm, 58 * mm, 25 * mm, 59 * mm])
    info_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), LIGHT),
                ("BACKGROUND", (2, 0), (2, -1), LIGHT),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.extend([info_table, Spacer(1, 8 * mm)])

    totals = [
        ["Subtotal excluding tax", _currency(estimate["subtotal_ex_tax"], currency)],
        [estimate["tax_name"], _currency(estimate["tax_total"], currency)],
        ["TOTAL INCLUDING TAX", _currency(estimate["total_incl_tax"], currency)],
    ]
    totals_table = Table(totals, colWidths=[95 * mm, 50 * mm], hAlign="RIGHT")
    totals_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -2), "Helvetica"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("BACKGROUND", (0, -1), (-1, -1), DARK),
                ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
                ("LINEABOVE", (0, 0), (-1, 0), 1, RED),
                ("BOX", (0, 0), (-1, -1), 0.5, DARK),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(totals_table)
    story.append(Spacer(1, 8 * mm))

    story.append(Paragraph("Estimate lines", styles["h1"]))
    line_rows = [["Line", "Description", "Qty", "Unit", "Markup", "Ex tax"]]
    for line in snapshot.get("lines", []):
        line_rows.append(
            [
                str(line["line_number"]),
                Paragraph(str(line["description"]), styles["small"]),
                str(line["quantity"]),
                str(line["unit"]),
                f"{d(line['applied_markup']) * 100:.2f}%\n{line['markup_source']}",
                _currency(line["subtotal_ex_tax"], currency),
            ]
        )
    lines_table = Table(
        line_rows,
        colWidths=[11 * mm, 82 * mm, 16 * mm, 18 * mm, 24 * mm, 28 * mm],
        repeatRows=1,
    )
    lines_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), DARK),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (2, 1), (5, -1), "RIGHT"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(lines_table)

    if not proposal:
        story.extend([PageBreak(), Paragraph("Physical and technical model", styles["h1"])])
        for opening in snapshot.get("openings", []):
            service_lines = "<br/>".join(
                (
                    f"{s['service_code']}: {s['service_type']} — "
                    f"{s.get('material') or 'material not confirmed'}"
                )
                for s in opening.get("services", [])
            ) or "No Services recorded"
            block = [
                Paragraph(f"Opening {opening['opening_code']}", styles["h2"]),
                Table(
                    [
                        [
                            "Defect",
                            opening.get("defect_id") or "Not provided",
                            "Location",
                            opening.get("location") or "Not provided",
                        ],
                        [
                            "Substrate",
                            opening.get("substrate_type") or "Not confirmed",
                            "Plane",
                            opening.get("substrate_plane") or "Not confirmed",
                        ],
                        [
                            "Orientation",
                            opening.get("orientation") or "Not confirmed",
                            "FRL",
                            opening.get("frl") or "Not confirmed",
                        ],
                        [
                            "Services",
                            Paragraph(service_lines, styles["small"]),
                            "Technical status",
                            opening.get("technical_status") or "not assessed",
                        ],
                    ],
                    colWidths=[24 * mm, 62 * mm, 28 * mm, 58 * mm],
                    style=TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (0, -1), LIGHT),
                            ("BACKGROUND", (2, 0), (2, -1), LIGHT),
                            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                            ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, -1), 7.3),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                        ]
                    ),
                ),
                Spacer(1, 4 * mm),
            ]
            story.append(KeepTogether(block))

        story.append(Paragraph("Rule evaluation", styles["h1"]))
        rule_rows = [["Result", "Severity", "Rule version", "Explanation"]]
        for item in snapshot.get("rule_evaluations", []):
            rule_rows.append(
                [
                    item["result"],
                    item["severity"],
                    str(item["rule_version"]),
                    Paragraph(item["explanation"], styles["small"]),
                ]
            )
        rule_table = Table(rule_rows, colWidths=[26 * mm, 24 * mm, 24 * mm, 98 * mm], repeatRows=1)
        rule_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), RED),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                ]
            )
        )
        story.append(rule_table)

    story.extend([Spacer(1, 7 * mm), Paragraph("Qualifications", styles["h1"])])
    qualifications = estimate.get("qualifications") or [
        (
            "Technical candidates and cost allowances do not constitute independent approval "
            "of a fire-stopping system."
        ),
        (
            "All technical applicability must be verified against the cited source evidence "
            "and project configuration."
        ),
    ]
    for item in qualifications:
        story.append(Paragraph(f"• {item}", styles["body"]))
    story.append(Spacer(1, 7 * mm))
    story.append(Paragraph(f"Snapshot hash: {snapshot['snapshot_hash']}", styles["small"]))
    generated_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    story.append(Paragraph(f"Generated by CLASSIFIRE on {generated_utc}", styles["small"]))
    doc.build(story, onFirstPage=_page, onLaterPages=_page)
    return output_path
