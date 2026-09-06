"""Source mapping forms, safe error redisplay and shared-editor boundaries."""

from __future__ import annotations

import copy
import json

import pytest
from test_draft_pdf_scope_templates import Forms, context, render

from classifire.draft_scope_xlsx_ui import _MAPPING_FIELDS, _error, _rows, _source_choices
from classifire.services.draft_scope import DraftScopeError


def workbook_context():
    values = context()
    values.pop("page_review")
    mapping = {key: None for key, _ in _MAPPING_FIELDS}
    mapping.update(defect_label=1, quantity=2)
    plan = {
        "sheet_index": 1,
        "header_row": 1,
        "mapping": mapping,
        "selections": [{"row": 15, "kinds": ["defect", "opening", "service"]}],
    }
    picture = {
        "occurrence_id": "image-1",
        "sha256": "e" * 64,
        "anchor": {
            "kind": "twoCell",
            "from": {"row": 15, "column": 1},
            "to": {"row": 18, "column": 3},
            "extent": None,
        },
    }
    document = {
        "sheets": [
            {
                "index": 1,
                "name": "Defects <source>",
                "rows": 30,
                "columns": 2,
                "cells": [
                    {
                        "row": 15,
                        "column": 1,
                        "address": "A15",
                        "kind": "text",
                        "value": '<script>untrusted & "quoted"</script>',
                    },
                    {"row": 15, "column": 2, "address": "B15", "kind": "number", "value": "0"},
                ],
                "images": [picture],
            }
        ]
    }
    source_url = "/scopes/draft-1/workbooks/source-1"
    choices, images = _source_choices(document, plan, source_url)
    targets = [
        {"target_kind": "opening", "target_id": "opening-1", "row": 15, "image_ids": ["image-1"]}
    ]
    values.update(
        document=document,
        plan=plan,
        start_row=1,
        workbook_review=True,
        review_url=source_url,
        source_url=source_url,
        base_url="/scopes/draft-1/workbooks",
        fields=_MAPPING_FIELDS,
        document_sha256="b" * 64,
        sources=[],
        postgres=True,
        review_sources=choices,
        sheet_images=images,
        rows=_rows(document, plan),
        review_targets=targets,
        review=None,
    )
    values["source"]["filename"] = "Synthetic <report>.xlsx"
    return values


def reviewed_context():
    values = workbook_context()
    values["saved"] = False
    values["review"] = {"payload": values["payload"]}
    values["preview"] = {
        "payload": values["payload"],
        "targets": values["review_targets"],
        "rows": values["rows"],
        "plan": values["plan"],
        "findings": [],
        "document_sha256": "b" * 64,
        "current_hash": "c" * 64,
        "review_sha256": "d" * 64,
        "expected_revision": 3,
    }
    return values


def test_mapping_form_has_only_bounded_plan_fields_and_all_column_choices():
    values = workbook_context()
    html = render("draft_scope_xlsx.html", values)
    parsed = Forms(html)
    mapping = next(form for form in parsed.forms if form["action"].endswith("/map"))
    assert set(mapping["fields"]) == {"csrf_token", "expected_revision", "document_sha256", "plan"}
    assert len(parsed.ids) == len(set(parsed.ids))
    assert not parsed.nested
    assert "xlsx-next" in parsed.ids and "xlsx-start-row" in parsed.ids
    assert all("xlsx-map-" + key in parsed.ids for key, _ in _MAPPING_FIELDS)
    assert "<script>untrusted" not in html
    assert "Formulas are shown as source text and never evaluated" in html


def test_editor_keeps_original_payload_and_independent_upload_scan_forms():
    html = render("draft_scope_xlsx.html", reviewed_context())
    parsed = Forms(html)
    graph = next(form for form in parsed.forms if form["action"].endswith("/preview"))
    assert set(graph["fields"]) == {
        "csrf_token",
        "expected_revision",
        "document_sha256",
        "plan",
        "payload",
        "targets",
    }
    assert "scope-initial-row-sources" in parsed.ids
    assert "scope-initial-sheet-images" in parsed.ids
    assert "scope-initial-review-targets" in parsed.ids
    assert "Connect the physical model explicitly" in html
    assert "A15" in html and "B15" in html
    assert not parsed.nested
    assert len(parsed.ids) == len(set(parsed.ids))


def test_preview_keeps_exact_graph_row_and_image_choices_with_explicit_confirm():
    values = reviewed_context()
    html = render("draft_scope_xlsx_preview.html", values)
    parsed = Forms(html)
    form = next(item for item in parsed.forms if item["action"].endswith("/confirm"))
    assert set(form["fields"]) == {
        "csrf_token",
        "expected_revision",
        "document_sha256",
        "plan",
        "payload",
        "targets",
        "preview_token",
        "confirm",
    }
    for key in ("payload", "plan"):
        assert json.loads(form["fields"][key][0]["value"]) == values[key]
    assert json.loads(form["fields"]["targets"][0]["value"]) == values["review_targets"]
    assert "required" in form["fields"]["confirm"][0]
    assert form["fields"]["confirm"][0]["value"] == "save"
    edit = next(item for item in parsed.forms if item["action"].endswith("/preview"))
    assert edit["fields"]["action"][0]["value"] == "edit"
    assert json.loads(edit["fields"]["targets"][0]["value"]) == values["review_targets"]
    assert "Unknown / 0 mm" in html and "Unknown each" in html
    assert "worksheet 1, row 15" in html and "Placed at A15 to C18" in html
    assert "Existing page observation" in html
    assert "<script>untrusted" not in html and '<img src=x onerror="attack()">' not in html
    assert not parsed.nested


@pytest.mark.parametrize(
    "updates",
    [{"errors": ["A newer revision exists"]}, {"has_permission": lambda _permission: False}],
)
def test_error_or_read_only_preview_has_no_save_form(updates):
    values = reviewed_context()
    values.update(updates)
    parsed = Forms(render("draft_scope_xlsx_preview.html", values))
    assert not any(form["action"].endswith("/confirm") for form in parsed.forms)


def test_unavailable_source_retains_graph_and_refs_without_image_or_save_controls():
    values = reviewed_context()
    values.update(document=None, errors=["Source unavailable"])
    html = render("draft_scope_xlsx.html", values)
    parsed = Forms(html)
    assert "Recover your unsaved entries" in html
    assert "Existing page observation" in html and "image-1" in html
    assert "scope-editor" not in parsed.ids
    assert not parsed.image_sources
    assert not any(form["action"].endswith(("/preview", "/confirm")) for form in parsed.forms)


@pytest.mark.parametrize("invalid", [[], {}, True, "A", -1, 100])
def test_rejected_mapping_can_be_redisplayed_without_unhashable_lookup(invalid):
    values = workbook_context()
    plan = copy.deepcopy(values["plan"])
    plan["mapping"]["defect_label"] = invalid
    rows = _rows(values["document"], plan)
    assert rows[0]["fields"]["defect_label"] is None
    assert rows[0]["fields"]["quantity"]["value"] == "0"
    values.update(plan=plan, errors=["Scope xlsx mapping invalid"], review={"plan": plan})
    assert "Draft changes were not saved" in render("draft_scope_xlsx.html", values)


def test_saved_scope_links_workbook_refs_to_rows_and_legacy_pdf_refs_to_pages():
    values = context()
    values.pop("page_review")
    common = {
        "original_filename": "Synthetic source",
        "target_label": "Opening",
        "target_kind": "opening",
        "status": "Unreviewed",
        "origin": "local_retained",
        "source_sha256": "a" * 64,
        "source_id": "source-1",
    }
    values["evidence_links"] = [
        dict(common, page_number=2),
        dict(common, source_kind="xlsx", row={"sheet": "Defects", "sheet_index": 1, "row": 15}),
    ]
    html = render("draft_scope.html", values)
    assert "/evidence/source-1?page=2" in html
    assert "/workbooks/source-1?sheet=1&amp;row=15" in html
    assert "Inspect source row" in html and "Inspect source page" in html
    values["evidence_links"] = values["evidence_links"][:1]
    assert "Saved page-review references (1)" in render("draft_scope.html", values)


def test_oversized_preview_explains_how_to_reduce_the_reviewed_batch():
    message = _error(DraftScopeError("DRAFT_ARTIFACT_TOO_LARGE"))
    assert "Choose fewer rows or source links" in message
    assert "preview again" in message
