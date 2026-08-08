from __future__ import annotations

from pathlib import Path
from typing import Any

import xlsxwriter

from .common import ATTRIBUTION, d, logo_path, verify_snapshot


def _formats(workbook: xlsxwriter.Workbook) -> dict[str, Any]:
    return {
        "title": workbook.add_format({"bold": True, "font_size": 20, "font_color": "#111827"}),
        "subtitle": workbook.add_format({"font_size": 10, "font_color": "#6B7280"}),
        "section": workbook.add_format(
            {"bold": True, "font_size": 12, "font_color": "#FFFFFF", "bg_color": "#F01419"}
        ),
        "header": workbook.add_format(
            {"bold": True, "font_color": "#FFFFFF", "bg_color": "#111827", "border": 1, "text_wrap": True}
        ),
        "label": workbook.add_format({"bold": True, "bg_color": "#F3F4F6", "border": 1}),
        "text": workbook.add_format({"border": 1, "text_wrap": True, "valign": "top"}),
        "money": workbook.add_format({"border": 1, "num_format": '[$$-en-AU]#,##0.00', "align": "right"}),
        "percent": workbook.add_format({"border": 1, "num_format": "0.00%", "align": "right"}),
        "qty": workbook.add_format({"border": 1, "num_format": "0.000", "align": "right"}),
        "total": workbook.add_format(
            {"bold": True, "font_color": "#FFFFFF", "bg_color": "#111827", "num_format": '[$$-en-AU]#,##0.00'}
        ),
        "footer": workbook.add_format({"font_size": 8, "font_color": "#6B7280", "italic": True}),
    }


def _insert_brand(sheet: xlsxwriter.worksheet.Worksheet) -> None:
    sheet.insert_image("A1", str(logo_path()), {"x_scale": 0.16, "y_scale": 0.16, "object_position": 1})


def render_technical_workbook(snapshot: dict[str, Any], output_path: Path) -> Path:
    verify_snapshot(snapshot)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb = xlsxwriter.Workbook(str(output_path), {"constant_memory": False})
    f = _formats(wb)
    wb.set_properties(
        {
            "title": f"QUANTIFIRE Technical Estimate — {snapshot['estimate']['reference']}",
            "author": "Ceasefire PFP",
            "comments": ATTRIBUTION,
        }
    )
    summary = wb.add_worksheet("Estimate Summary")
    _insert_brand(summary)
    summary.set_column("A:A", 24)
    summary.set_column("B:B", 52)
    summary.set_column("C:C", 24)
    summary.set_column("D:D", 52)
    summary.set_row(0, 85)
    summary.write("A6", "QUANTIFIRE Technical Estimate", f["title"])
    summary.write("A7", ATTRIBUTION, f["subtitle"])
    rows = [
        ("Project", snapshot["project"].get("name"), "Estimate reference", snapshot["estimate"]["reference"]),
        ("Project reference", snapshot["project"].get("reference"), "Revision", snapshot["estimate"]["revision"]),
        ("Site", snapshot["project"].get("site_address"), "Jurisdiction", snapshot["project"].get("jurisdiction")),
        ("Snapshot hash", snapshot["snapshot_hash"], "Status", snapshot["estimate"].get("status")),
    ]
    for row_index, row in enumerate(rows, 9):
        summary.write(row_index, 0, row[0], f["label"])
        summary.write(row_index, 1, row[1] or "Not provided", f["text"])
        summary.write(row_index, 2, row[2], f["label"])
        summary.write(row_index, 3, row[3] or "Not provided", f["text"])
    summary.write("A15", "Commercial Summary", f["section"])
    summary.merge_range("A15:D15", "Commercial Summary", f["section"])
    summary.write("C17", "Subtotal excluding tax", f["label"])
    summary.write_number("D17", float(d(snapshot["estimate"]["subtotal_ex_tax"])), f["money"])
    summary.write("C18", snapshot["estimate"]["tax_name"], f["label"])
    summary.write_number("D18", float(d(snapshot["estimate"]["tax_total"])), f["money"])
    summary.write("C19", "Total including tax", f["header"])
    summary.write_number("D19", float(d(snapshot["estimate"]["total_incl_tax"])), f["total"])
    summary.write("A22", ATTRIBUTION, f["footer"])
    summary.freeze_panes(8, 0)

    lines = wb.add_worksheet("Pricing Lines")
    line_headers = [
        "Line", "Opening", "Service", "Component Type", "Reference", "Description", "Quantity", "Unit",
        "Base Unit Cost", "Waste", "Markup", "Markup Source", "Unit Sell", "Subtotal Ex Tax", "Tax",
        "Total Incl Tax", "Pricing Method", "Recovery Status", "Rate Source", "Formula Version"
    ]
    for col, header in enumerate(line_headers):
        lines.write(0, col, header, f["header"])
    for row, item in enumerate(snapshot.get("lines", []), 1):
        values = [
            item["line_number"], item.get("opening_id"), item.get("service_id"), item["component_type"],
            item.get("component_reference"), item["description"], float(d(item["quantity"])), item["unit"],
            float(d(item["base_unit_cost"])), float(d(item["waste_factor"])), float(d(item["applied_markup"])),
            item["markup_source"], float(d(item["unit_sell"])), float(d(item["subtotal_ex_tax"])),
            float(d(item["tax"])), float(d(item["total_incl_tax"])), item["pricing_method"],
            item["commercial_recovery_status"], item.get("rate_source"), item["formula_version"]
        ]
        for col, value in enumerate(values):
            fmt = f["text"]
            if col in {6}:
                fmt = f["qty"]
            elif col in {8, 12, 13, 14, 15}:
                fmt = f["money"]
            elif col in {9, 10}:
                fmt = f["percent"]
            if isinstance(value, (int, float)):
                lines.write_number(row, col, value, fmt)
            else:
                lines.write(row, col, value, fmt)
    lines.autofilter(0, 0, max(len(snapshot.get("lines", [])), 1), len(line_headers) - 1)
    lines.freeze_panes(1, 6)
    lines.set_column(0, 0, 8)
    lines.set_column(1, 4, 16)
    lines.set_column(5, 5, 55)
    lines.set_column(6, 19, 16)

    openings = wb.add_worksheet("Openings and Services")
    open_headers = [
        "Opening", "Defect", "Location", "Substrate", "Plane", "Thickness mm", "Orientation", "FRL",
        "Physical Status", "Technical Status", "Service", "Service Type", "Material", "Diameter mm", "Quantity",
        "Evidence Status"
    ]
    for col, header in enumerate(open_headers):
        openings.write(0, col, header, f["header"])
    row = 1
    for opening in snapshot.get("openings", []):
        services = opening.get("services") or [None]
        for service in services:
            values = [
                opening["opening_code"], opening.get("defect_id"), opening.get("location"),
                opening.get("substrate_type"), opening.get("substrate_plane"), opening.get("substrate_thickness_mm"),
                opening.get("orientation"), opening.get("frl"), opening.get("physical_model_status"),
                opening.get("technical_status"), service.get("service_code") if service else None,
                service.get("service_type") if service else None, service.get("material") if service else None,
                service.get("outside_diameter_mm") if service else None, service.get("quantity") if service else None,
                service.get("evidence_status") if service else None,
            ]
            for col, value in enumerate(values):
                openings.write(row, col, value, f["text"])
            row += 1
    openings.autofilter(0, 0, max(row - 1, 1), len(open_headers) - 1)
    openings.freeze_panes(1, 3)
    openings.set_column(0, 1, 14)
    openings.set_column(2, 2, 35)
    openings.set_column(3, 15, 18)

    rules = wb.add_worksheet("Rule Evidence")
    rule_headers = ["Result", "Severity", "Opening", "Rule ID", "Rule Version", "Explanation", "Source", "Inputs", "Output"]
    for col, header in enumerate(rule_headers):
        rules.write(0, col, header, f["header"])
    import json
    for row, item in enumerate(snapshot.get("rule_evaluations", []), 1):
        values = [
            item["result"], item["severity"], item.get("opening_id"), item["rule_id"], item["rule_version"],
            item["explanation"], item.get("source_reference"), json.dumps(item.get("inputs"), ensure_ascii=False),
            json.dumps(item.get("output"), ensure_ascii=False)
        ]
        for col, value in enumerate(values):
            rules.write(row, col, value, f["text"])
    rules.freeze_panes(1, 0)
    rules.set_column(0, 4, 18)
    rules.set_column(5, 8, 55)

    manifest = wb.add_worksheet("Version Manifest")
    manifest.write("A1", "Snapshot hash", f["label"])
    manifest.write("B1", snapshot["snapshot_hash"], f["text"])
    manifest.write("A3", "Release type", f["header"])
    manifest.write("B3", "Release ID", f["header"])
    for row, (kind, release_id) in enumerate(snapshot.get("release_pins", {}).items(), 4):
        manifest.write(row - 1, 0, kind, f["text"])
        manifest.write(row - 1, 1, release_id or "Not pinned", f["text"])
    manifest.write("A12", ATTRIBUTION, f["footer"])
    manifest.set_column("A:A", 28)
    manifest.set_column("B:B", 70)

    wb.close()
    return output_path


def render_proposal_workbook(snapshot: dict[str, Any], output_path: Path) -> Path:
    verify_snapshot(snapshot)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb = xlsxwriter.Workbook(str(output_path))
    f = _formats(wb)
    summary = wb.add_worksheet("Proposal Summary")
    pricing = wb.add_worksheet("Defect Pricing")
    _insert_brand(summary)
    summary.set_row(0, 85)
    summary.set_column("A:A", 26)
    summary.set_column("B:B", 60)
    summary.set_column("C:C", 24)
    summary.set_column("D:D", 32)
    summary.write("A6", "QUANTIFIRE Proposal", f["title"])
    summary.write("A7", ATTRIBUTION, f["subtitle"])
    data = [
        ("Project", snapshot["project"].get("name")),
        ("Site", snapshot["project"].get("site_address")),
        ("Client", snapshot["project"].get("customer")),
        ("Estimate", snapshot["estimate"]["reference"]),
        ("Revision", snapshot["estimate"]["revision"]),
        ("Jurisdiction", snapshot["project"].get("jurisdiction")),
        ("Snapshot hash", snapshot["snapshot_hash"]),
    ]
    for row, (label, value) in enumerate(data, 9):
        summary.write(row, 0, label, f["label"])
        summary.merge_range(row, 1, row, 3, value or "Not provided", f["text"])
    summary.write("A18", "Commercial Summary", f["section"])
    summary.merge_range("A18:D18", "Commercial Summary", f["section"])
    summary.write("C20", "Subtotal excluding tax", f["label"])
    summary.write_number("D20", float(d(snapshot["estimate"]["subtotal_ex_tax"])), f["money"])
    summary.write("C21", snapshot["estimate"]["tax_name"], f["label"])
    summary.write_number("D21", float(d(snapshot["estimate"]["tax_total"])), f["money"])
    summary.write("C22", "Total including tax", f["header"])
    summary.write_number("D22", float(d(snapshot["estimate"]["total_incl_tax"])), f["total"])
    summary.write("A25", "Qualifications", f["section"])
    summary.merge_range("A25:D25", "Qualifications", f["section"])
    qualifications = snapshot["estimate"].get("qualifications") or [
        "Technical candidates and cost allowances require verification against applicable source evidence.",
        "No unsupported compliance claim is made by this proposal.",
    ]
    for row, value in enumerate(qualifications, 26):
        summary.merge_range(row, 0, row, 3, f"• {value}", f["text"])
    summary.write(34, 0, ATTRIBUTION, f["footer"])

    headers = ["Defect", "Opening", "Location", "Description", "Quantity", "Unit", "Price Ex Tax", "Tax", "Price Incl Tax", "Status / Qualification"]
    for col, header in enumerate(headers):
        pricing.write(0, col, header, f["header"])
    opening_index = {o["id"]: o for o in snapshot.get("openings", [])}
    for row, line in enumerate(snapshot.get("lines", []), 1):
        opening = opening_index.get(line.get("opening_id"), {})
        values = [
            opening.get("defect_id"), opening.get("opening_code"), opening.get("location"), line["description"],
            float(d(line["quantity"])), line["unit"], float(d(line["subtotal_ex_tax"])), float(d(line["tax"])),
            float(d(line["total_incl_tax"])), line["commercial_recovery_status"]
        ]
        for col, value in enumerate(values):
            fmt = f["money"] if col in {6, 7, 8} else f["qty"] if col == 4 else f["text"]
            if isinstance(value, (int, float)):
                pricing.write_number(row, col, value, fmt)
            else:
                pricing.write(row, col, value, fmt)
    pricing.autofilter(0, 0, max(len(snapshot.get("lines", [])), 1), len(headers) - 1)
    pricing.freeze_panes(1, 3)
    pricing.set_column(0, 2, 17)
    pricing.set_column(3, 3, 60)
    pricing.set_column(4, 9, 18)
    wb.close()
    return output_path
