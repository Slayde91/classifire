"""Pure rendered-form and adapter checks for optional retained page suggestions."""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from test_draft_pdf_scope_templates import Forms, context, render

from classifire import draft_pdf_suggestion_ui as ui
from classifire.services.draft_scope import DraftScopeError


def suggestion_context() -> dict[str, Any]:
    values = context()
    items = [
        {"target_kind": kind, "target_id": values["payload"][collection][0]["id"],
         "proposed_item": copy.deepcopy(values["payload"][collection][0]),
         "basis": "both", "quote": "<script>source</script>",
         "rationale": "Compare the retained page & keep uncertainty."}
        for kind, collection in (("opening", "openings"), ("observation", "observations"))
    ]
    suggestion = {
        "id": "suggestion-1", "status": "pending", "expected_revision": 3,
        "current_revision": 3, "stale": False, "applied_revision": None,
        "source_id": "source-1", "page_number": 2, "payload": values["payload"],
        "items": items, "provider": "scripted", "model": "synthetic-fixture-v1",
        "prompt_version": "draft-pdf-suggestions-v1", "generated_at": "2026-09-06T00:00:00Z",
        "input_sha256": "a" * 64, "response_sha256": "b" * 64,
        "page_image_sha256": "c" * 64,
    }
    values.update(suggestion=suggestion, source_id="source-1", can_edit=True, saved=False,
                  suggestion_review=True, suggestion_items=items, review_targets=[],
                  recovery_payload=None,
                  review_url="/scopes/draft-1/evidence/source-1/suggestions/suggestion-1")
    return values


def test_explicit_provider_request_and_retained_history_keep_manual_forms() -> None:
    values = context()
    values.update(
        suggestion_availability={"enabled": True, "provider": "configured-provider",
                                 "model": "configured-model", "demo": False},
        source_suggestions=[suggestion_context()["suggestion"]],
    )
    html = render("draft_pdf_source.html", values)
    parsed = Forms(html)
    form = next(form for form in parsed.forms if form["action"].endswith("/suggestions"))
    assert set(form["fields"]) == {
        "csrf_token", "expected_revision", "page", "document_hash", "consent",
    }
    assert form["fields"]["consent"][0]["value"] == "yes"
    assert "required" in form["fields"]["consent"][0]
    assert "Your saved Draft graph is not sent" in html
    assert "configured-provider" in html and "configured-model" in html
    assert '/suggestions/suggestion-1"' in html
    assert any(form["action"].endswith("/scope/preview") for form in parsed.forms)
    assert any(form["action"].endswith("/review") for form in parsed.forms)
    assert not parsed.nested
    assert len(parsed.ids) == len(set(parsed.ids))


@pytest.mark.parametrize("enabled,permission", [(False, True), (True, False)])
def test_unavailable_or_read_only_preserves_manual_path(enabled: bool, permission: bool) -> None:
    values = context()
    values.update(suggestion_availability={"enabled": enabled},
                  has_permission=lambda _: permission)
    html = render("draft_pdf_source.html", values)
    assert "Continue with manual page review" in html
    assert not any(form["action"].endswith("/suggestions") for form in Forms(html).forms)


def test_scripted_demo_is_explicitly_labelled() -> None:
    values = context()
    values["suggestion_availability"] = {"enabled": True, "demo": True,
                                        "provider": "scripted", "model": "synthetic-fixture-v1"}
    html = render("draft_pdf_source.html", values)
    assert "Load demonstration suggestions" in html
    assert "does not contact a live AI provider" in html
    assert "Send this selected page" not in html


def test_edit_review_has_unselected_targets_originals_and_separate_rejection() -> None:
    values = suggestion_context()
    html = render("draft_pdf_suggestion.html", values)
    parsed = Forms(html)
    graph = next(form for form in parsed.forms if form["action"].endswith("/preview"))
    assert set(graph["fields"]) == {"csrf_token", "expected_revision", "payload", "targets"}
    assert 'id="scope-initial-review-targets">[]</script>' in html
    assert 'data-suggestion-review="true"' in html
    assert 'id="scope-initial-suggestion-items"' in html
    assert "Original suggestions and source basis" in html
    assert "No live provider call" in html or "no live provider call" in html
    assert "&lt;script&gt;source&lt;/script&gt;" in html
    assert "<script>source</script>" not in html
    assert '<img src=x onerror="attack()">' not in html
    reject = next(form for form in parsed.forms if form["action"].endswith("/reject"))
    assert set(reject["fields"]) == {"csrf_token", "confirm"}
    assert reject["fields"]["confirm"][0]["value"] == "reject"
    assert "required" in reject["fields"]["confirm"][0]
    assert not parsed.nested
    assert len(parsed.ids) == len(set(parsed.ids))


@pytest.mark.parametrize("status,stale", [("applied", False), ("rejected", False),
                                           ("pending", True), ("pending", False)])
def test_closed_stale_and_read_only_reviews_cannot_submit(status: str, stale: bool) -> None:
    values = suggestion_context()
    values["suggestion"].update(status=status, stale=stale,
                                applied_revision=4 if status == "applied" else None)
    values["can_edit"] = status == "pending" and not stale
    if status == "pending" and not stale:
        values["has_permission"] = lambda _: False
    html = render("draft_pdf_suggestion.html", values)
    assert not Forms(html).forms
    assert "Original proposed graph (read-only)" in html
    if status == "applied":
        assert "can differ from the edited graph that was saved" in html
        assert '/download?revision=4"' in html
    if stale:
        assert "Draft has changed" in html


def test_stale_submission_displays_attempted_graph_without_stale_save() -> None:
    values = suggestion_context()
    values["payload"] = copy.deepcopy(values["payload"])
    values["payload"]["observations"][0]["text"] = "My unsaved attempted correction"
    values.update(can_edit=False, errors=["Draft changed"])
    values["suggestion"]["stale"] = True
    html = render("draft_pdf_suggestion.html", values)
    assert "My unsaved attempted correction" in html
    assert "Unsaved attempted graph" in html
    assert not Forms(html).forms


def test_unverifiable_source_has_only_escaped_recovery_no_editor_or_image() -> None:
    values = suggestion_context()
    values.update(suggestion=None, can_edit=False, errors=["Source unavailable"],
                  recovery_payload=values["payload"], recovery_targets=values["review_targets"])
    html = render("draft_pdf_suggestion.html", values)
    parsed = Forms(html)
    assert "Submitted graph (read-only JSON)" in html
    assert "These submitted entries have not been saved" in html
    assert not parsed.forms and not parsed.image_sources
    assert "scope-editor" not in parsed.ids
    assert '<img src=x onerror="attack()">' not in html


def test_preview_preserves_exact_graph_and_original_metadata_without_editable_claims() -> None:
    values = suggestion_context()
    values["payload"] = copy.deepcopy(values["payload"])
    values["payload"]["openings"][0]["substrate"] = "Edited manually"
    values["payload"]["observations"] = []
    targets = [{"target_kind": "opening", "target_id": "opening-1"}]
    values["preview"] = {"payload": values["payload"], "targets": targets,
                         "expected_revision": 3, "page": 2, "findings": [],
                         "suggestion_document": {"never-editable": "server-owned"}}
    html = render("draft_pdf_suggestion_preview.html", values)
    parsed = Forms(html)
    confirm = next(form for form in parsed.forms if form["action"].endswith("/confirm"))
    fields = confirm["fields"]
    assert set(fields) == {"csrf_token", "expected_revision", "payload", "targets",
                           "preview_token", "confirm"}
    assert json.loads(fields["payload"][0]["value"]) == values["payload"]
    assert json.loads(fields["targets"][0]["value"]) == targets
    assert fields["confirm"][0]["value"] == "save" and "required" in fields["confirm"][0]
    back = next(form for form in parsed.forms if form["action"].endswith("/preview"))
    assert back["fields"]["action"][0]["value"] == "edit"
    assert "Kept with edits" in html and "Rejected" in html
    assert "Unknown / 0 mm" in html and "Unknown each" in html
    assert "never-editable" not in html
    assert not parsed.nested


@pytest.mark.parametrize("updates", [{"errors": ["Stale preview"]},
                                      {"has_permission": lambda _: False}])
def test_failed_or_read_only_suggestion_preview_cannot_confirm(updates: dict[str, Any]) -> None:
    values = suggestion_context()
    values["preview"] = {"payload": values["payload"], "targets": [],
                         "expected_revision": 3, "page": 2, "findings": []}
    values.update(updates)
    assert not any(form["action"].endswith("/confirm") for form in
                   Forms(render("draft_pdf_suggestion_preview.html", values)).forms)


def test_record_rejects_different_source_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ui.suggestions, "read_suggestion", lambda *a, **k: {"source_id": "other"})
    with pytest.raises(HTTPException) as exc:
        ui._record(None, None, "draft", "source", "suggestion")
    assert exc.value.status_code == 404


def test_port_is_only_taken_from_guarded_application_state() -> None:
    port = object()
    request = Request({"type": "http", "app": SimpleNamespace(state=SimpleNamespace(
        draft_pdf_suggestion_port=port)), "query_string": b"provider=scripted"})
    assert ui._port(request) is port
    request.scope["app"].state = SimpleNamespace()
    assert ui._port(request) is None


def test_review_error_explains_required_selection_and_manual_fallback() -> None:
    assert "every kept suggestion" in ui._error(DraftScopeError("PDF_SUGGESTION_REVIEW_REQUIRED"))
    assert "manual page review" in ui._error(DraftScopeError("PDF_SUGGESTIONS_UNAVAILABLE"))
