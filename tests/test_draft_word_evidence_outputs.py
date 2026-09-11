from __future__ import annotations

import io
from copy import deepcopy

import pytest
from openpyxl import load_workbook
from test_draft_entity_evidence_outputs import report_snapshot
from test_draft_scope_outputs import _id, _pdf_text, _seal
from test_draft_suggestion_evidence import successor, suggestion_scope

from classifire.outputs import draft_estimate as estimate_outputs
from classifire.outputs import draft_scope as scope_outputs
from classifire.services import draft_estimate_reports as estimate_reports
from classifire.services import draft_scope as scopes
from classifire.services import draft_scope_reports as scope_reports
from classifire.services.draft_scope_docx_document import digest
from classifire.services.draft_scope_evidence import observation_hash, reference_status


def word_scope():
    prior = suggestion_scope()
    text = '=HYPERLINK("https://example.invalid/", "untrusted Word text")'
    item = prior["content"]["defects"][0]
    ref = dict(
        source_id=_id(970),
        source_kind="docx",
        source_sha256="a" * 64,
        source_size_bytes=2000,
        original_filename="Synthetic Word.docx",
        document_sha256="b" * 64,
        scan_sha256="c" * 64,
        reviewed_by=_id(1),
        reviewed_at="2026-09-06T03:00:00+00:00",
        method="human_docx_entity_review",
        origin="local_retained",
        target_kind="defect",
        target_id=item["id"],
        target_sha256=observation_hash(item),
        block=dict(locator="body-2/row-1/cell-1/p-1", text=text, text_sha256=digest(text.encode())),
        images=[
            dict(
                id="picture-1",
                locator="body-3",
                member="word/media/image1.png",
                sha256="d" * 64,
                preview_sha256="e" * 64,
                size_bytes=80,
                media_type="image/png",
                width=12,
                height=8,
            )
        ],
    )
    return successor(prior, entity_evidence_refs=[ref])


def test_word_version_keeps_pdf_excel_ai_history_and_manual_staleness():
    prior = suggestion_scope()
    word = word_scope()
    assert word["schema_version"] == "CLASSIFIRE-DRAFT-SCOPE-v7"
    assert word["evidence_refs"][:-1] == prior["evidence_refs"]
    assert scopes.validate_portable_artifact(scopes._json(word)) == word
    altered = deepcopy(word["content"])
    altered["defects"][0]["description"] += " changed"
    saved = successor(word, altered)
    assert saved["schema_version"] == word["schema_version"]
    assert saved["evidence_refs"] == word["evidence_refs"]
    assert "changed since Word review" in reference_status(
        saved["evidence_refs"][-1], saved["content"]
    )
    rereviewed = successor(saved, entity_evidence_refs=[deepcopy(prior["evidence_refs"][0])])
    assert rereviewed["schema_version"] == word["schema_version"]
    assert rereviewed["evidence_refs"][-2]["source_kind"] == "docx"
    for version in ("CLASSIFIRE-DRAFT-SCOPE-v5", "CLASSIFIRE-DRAFT-SCOPE-v6"):
        invalid = deepcopy(word)
        invalid["schema_version"] = version
        _seal(invalid)
        with pytest.raises(scopes.DraftScopeError):
            scopes.validate_portable_artifact(scopes._json(invalid))


@pytest.mark.parametrize(
    "profile,version",
    [("scope-only", 9), ("scope-and-system", 10), ("estimate-only", 10), ("complete", 11)],
)
def test_word_outputs_keep_text_picture_provenance_literal_and_same_snapshot(
    profile, version, tmp_path
):
    snapshot = report_snapshot(profile, word_scope())
    snapshot["render_version"] = version
    _seal(snapshot)
    before = deepcopy(snapshot)
    if "estimate" in snapshot:
        estimate_reports.validate_report_snapshot(snapshot)
        pdf = estimate_outputs.render_estimate_report_pdf(snapshot)
        xlsx = estimate_outputs.render_estimate_report_xlsx(snapshot)
    else:
        scope_reports.validate_report_snapshot(snapshot)
        pdf = scope_outputs.render_scope_report_pdf(snapshot)
        xlsx = scope_outputs.render_scope_report_xlsx(snapshot)
    text = " ".join(_pdf_text(pdf).split())
    book = load_workbook(io.BytesIO(xlsx), data_only=False)
    cells = [cell for sheet in book for row in sheet for cell in row]
    strings = " ".join(str(cell.value) for cell in cells if cell.value is not None)
    for expected in (
        "Synthetic Word.docx",
        "body-2/row-1/cell-1/p-1",
        "untrusted Word text",
        "word/media/image1.png",
        "synthetic-page-suggester",
    ):
        assert expected in text and expected in strings
    assert all(cell.data_type != "f" and cell.hyperlink is None for cell in cells)
    assert snapshot == before
    (tmp_path / (profile + ".pdf")).write_bytes(pdf)
    (tmp_path / (profile + ".xlsx")).write_bytes(xlsx)
