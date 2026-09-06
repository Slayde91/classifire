from __future__ import annotations

import io
from copy import deepcopy

import pytest
from openpyxl import load_workbook
from test_draft_entity_evidence_outputs import entity_scope, report_snapshot
from test_draft_scope_outputs import _id, _pdf_text, _seal

from classifire.outputs import draft_estimate as estimate_outputs
from classifire.outputs import draft_scope as scope_outputs
from classifire.services import draft_estimate_reports as estimate_reports
from classifire.services import draft_scope_reports as scope_reports
from classifire.services.draft_scope import DraftScopeError, _envelope_shape
from classifire.services.draft_scope_evidence import observation_hash
from classifire.services.draft_scope_xlsx_contract import FIELDS, digest

PROFILES = ("scope-only", "scope-and-system", "estimate-only", "complete")
VERSIONS = dict(zip(PROFILES, (5, 6, 6, 7), strict=True))


def workbook_scope():
    scope = entity_scope()
    mapping = dict.fromkeys(FIELDS)
    mapping.update(defect_label=1, width_mm=2, quantity=3, unit=4)
    fields = dict.fromkeys(FIELDS)
    for key, column, kind, value in (
        ("defect_label", 1, "text", "D-01"),
        ("width_mm", 2, "number", "0"),
        ("quantity", 3, "formula", "=1+2"),
        ("unit", 4, "text", '<script src="https://example.invalid/x"></script>'),
    ):
        fields[key] = dict(
            address=f"{chr(64 + column)}14", row=14, column=column, kind=kind, value=value
        )
    row = dict(sheet="Defects", sheet_index=1, row=14, header_row=1, mapping=mapping, fields=fields)
    row["sha256"] = digest(row)
    images = []
    for index, anchor_row in enumerate((14, 22), 1):
        images.append(
            dict(
                occurrence_id=f"image-{index}",
                member="xl/media/image1.png",
                sha256="a" * 64,
                size_bytes=180,
                media_type="image/png",
                width=12,
                height=8,
                preview_sha256="b" * 64,
                anchor=dict(
                    kind="oneCell",
                    to=None,
                    extent=dict(width_emu=114300, height_emu=76200),
                    **{
                        "from": dict(
                            row=anchor_row, column=5, row_offset_emu=0, column_offset_emu=0
                        )
                    },
                ),
            )
        )
    common = dict(
        source_kind="xlsx",
        source_id=_id(900),
        source_sha256="c" * 64,
        source_size_bytes=12000,
        original_filename="Synthetic <defects>.xlsx",
        document_sha256="d" * 64,
        scan_sha256="e" * 64,
        row=row,
        images=images,
        reviewed_by=_id(1),
        reviewed_at="2026-09-06T02:00:00+00:00",
        method="human_xlsx_row_entity_review",
        origin="local_retained",
    )
    refs = []
    for kind, item in (
        ("defect", scope["content"]["defects"][0]),
        ("opening", scope["content"]["openings"][0]),
    ):
        refs.append(
            common
            | dict(target_kind=kind, target_id=item["id"], target_sha256=observation_hash(item))
        )
    refs.append(common | dict(target_kind="service", target_id=_id(9), target_sha256="f" * 64))
    scope["content"]["openings"][0]["substrate"] = "Changed after workbook review"
    scope["evidence_refs"].extend(refs)
    scope["schema_version"] = "CLASSIFIRE-DRAFT-SCOPE-v5"
    return _seal(scope)


def workbook_report(profile):
    snapshot = report_snapshot(profile, workbook_scope())
    snapshot["render_version"] = VERSIONS[profile]
    return _seal(snapshot)


@pytest.mark.parametrize("profile", PROFILES)
def test_workbook_and_pdf_claims_render_in_all_four_profiles_without_active_content(profile):
    snapshot = workbook_report(profile)
    before = deepcopy(snapshot)
    service = estimate_reports if "estimate" in snapshot else scope_reports
    service.validate_report_snapshot(snapshot)
    if "estimate" in snapshot:
        pdf = estimate_outputs.render_estimate_report_pdf(snapshot)
        workbook = estimate_outputs.render_estimate_report_xlsx(snapshot)
    else:
        pdf = scope_outputs.render_scope_report_pdf(snapshot)
        workbook = scope_outputs.render_scope_report_xlsx(snapshot)
    text = " ".join(_pdf_text(pdf).split())
    book = load_workbook(io.BytesIO(workbook), data_only=False)
    cells = [cell for sheet in book for row in sheet for cell in row]
    strings = " ".join(str(cell.value) for cell in cells if cell.value is not None)
    for value in (
        "Synthetic <defects>.xlsx",
        "Synthetic <report>.pdf",
        "Defects!A14 (text): D-01",
        "Defects!B14 (number): 0",
        "Defects!C14 (formula): =1+2",
        "Not mapped",
        "image-1",
        "image-2",
        "xl/media/image1.png",
        "Item changed since workbook review; review again",
        "Item removed since workbook review; historical source reference retained",
        "Imported source and review claims are unverified",
        "no technical or physical approval",
    ):
        assert value in text
        assert value in strings
    assert all(cell.data_type != "f" and cell.hyperlink is None for cell in cells)
    assert snapshot == before
    if "estimate" not in snapshot:
        assert "Target ID" in [c.value for r in book["Evidence References"] for c in r]
    else:
        assert snapshot["estimate"]["summary"]["priced_subtotal_ex_tax"] == "0.00"


@pytest.mark.parametrize("profile", PROFILES)
def test_v5_requires_its_renderer_and_v4_still_validates_at_original_version(profile):
    snapshot = workbook_report(profile)
    service = estimate_reports if "estimate" in snapshot else scope_reports
    service.validate_report_snapshot(snapshot)
    legacy = report_snapshot(profile)
    invalid = deepcopy(snapshot)
    invalid["render_version"] = legacy["render_version"]
    _seal(invalid)
    with pytest.raises(DraftScopeError, match="SNAPSHOT_INVALID"):
        service.validate_report_snapshot(invalid)
    service.validate_report_snapshot(legacy)


def test_workbook_saved_claim_template_escapes_text_and_displays_cells_and_images():
    from classifire.ui import templates

    scope = workbook_scope()
    _envelope_shape(scope)
    before = deepcopy(scope)
    html = templates.env.get_template("draft_scope_report_content.html").render(envelope=scope)
    assert "Synthetic &lt;defects&gt;.xlsx" in html
    assert "Defects!C14 (formula): =1+2" in html
    assert "image_image-2_anchor" in html or "image image-2 anchor" in html
    assert "&lt;script" in html and '<script src="https://example.invalid/x">' not in html
    assert "Item changed since workbook review; review again" in html
    assert "page None" not in html
    assert scope == before
