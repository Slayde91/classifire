"""Browser form contracts and escaping for retained-PDF graph review."""

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader, select_autoescape


class Forms(HTMLParser):
    def __init__(self, html: str) -> None:
        super().__init__()
        self.forms: list[dict[str, Any]] = []
        self.active: dict[str, Any] | None = None
        self.nested = False
        self.ids: list[str] = []
        self.image_sources: list[str] = []
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(str(values["id"]))
        if tag == "img":
            self.image_sources.append(str(values.get("src")))
        if tag == "form":
            self.nested = self.nested or self.active is not None
            self.active = {"action": values.get("action"), "fields": {}}
            self.forms.append(self.active)
        elif tag in {"input", "button", "textarea", "select"} and self.active is not None:
            if values.get("name"):
                self.active["fields"].setdefault(values["name"], []).append(values)

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self.active = None


def context() -> dict[str, Any]:
    payload = {
        "defects": [{"id": "defect-1", "label": '<img src=x onerror="attack()">',
                     "description": "A quoted \"note\" & <page>"}],
        "openings": [{"id": "opening-1", "label": "Shared opening", "defect_id": "defect-1",
                      "plane": "unknown", "substrate": "", "width_mm": None,
                      "height_mm": "0", "blank": False, "state": "Unresolved"}],
        "services": [{"id": "service-1", "label": "Cable bundle", "opening_ids": ["opening-1"],
                      "service_type": "", "quantity": None, "unit": "each",
                      "state": "Provisional"}],
        "observations": [{"id": "observation-1", "text": "Existing page observation",
                          "state": "Inferred"}],
        "assumptions": ["Access unknown"], "exclusions": [],
    }
    page = {"page_number": 2, "text": "Unreviewed source text"}
    return {
        "draft": {"id": "draft-1"}, "project": {"reference": "CF-TEST", "name": "Test"},
        "source": {"id": "source-1", "filename": "Synthetic <report>.pdf", "sha256": "a" * 64,
                   "status": "clean", "size_bytes": 1000, "scan": None,
                   "processing_error": None},
        "document": {"pages": [{"page_number": 1, "text": "Page one"}, page]},
        "selected_page": page, "revision": 3, "expected_revision": 3,
        "document_hash": "b" * 64, "payload": payload, "saved": True,
        "envelope": {}, "evidence_links": [], "errors": [], "findings": [],
        "review_targets": [{"target_kind": "opening", "target_id": "opening-1"}],
        "page_review": True, "review_url": "/scopes/draft-1/evidence/source-1/scope",
        "csrf_token": "synthetic-csrf", "has_permission": lambda _permission: True,
        "problem": None, "preview_token": "synthetic-preview-token",
    }


def render(name: str, values: dict[str, Any]) -> str:
    templates = Path(__file__).resolve().parents[1] / "src" / "classifire" / "templates"
    environment = Environment(
        loader=ChoiceLoader([
            DictLoader({"base.html": "{% block content %}{% endblock %}"}),
            FileSystemLoader(templates),
        ]),
        autoescape=select_autoescape(("html",)),
    )
    return environment.get_template(name).render(**values)


def preview_context() -> dict[str, Any]:
    values = context()
    values["preview"] = {
        "payload": values["payload"], "targets": values["review_targets"], "findings": [],
        "expected_revision": 3, "page": 2, "document_hash": "b" * 64,
        "current_hash": "c" * 64, "review_sha256": "d" * 64,
    }
    return values


def test_pdf_editor_keeps_graph_and_observation_forms_separate() -> None:
    html = render("draft_pdf_source.html", context())
    parsed = Forms(html)
    assert not parsed.nested
    assert len(parsed.ids) == len(set(parsed.ids))
    graph = next(item for item in parsed.forms if item["action"].endswith("/scope/preview"))
    assert set(graph["fields"]) == {
        "csrf_token", "expected_revision", "payload", "page", "document_hash", "targets",
    }
    assert graph["fields"]["page"][0]["value"] == "2"
    assert graph["fields"]["expected_revision"][0]["value"] == "3"
    assert any(item["action"].endswith("/review") for item in parsed.forms)
    assert "scope-initial-review-targets" in parsed.ids
    assert 'src=x onerror="attack()"' not in html


def test_preview_round_trips_exact_payload_and_requires_explicit_confirmation() -> None:
    values = preview_context()
    html = render("draft_pdf_scope_preview.html", values)
    parsed = Forms(html)
    assert not parsed.nested
    confirmation = next(item for item in parsed.forms if item["action"].endswith("/confirm"))
    fields = confirmation["fields"]
    assert set(fields) == {
        "csrf_token", "expected_revision", "payload", "page", "document_hash", "targets",
        "preview_token", "confirm",
    }
    assert fields["confirm"][0]["type"] == "checkbox"
    assert fields["confirm"][0]["value"] == "save"
    assert "required" in fields["confirm"][0]
    assert json.loads(fields["payload"][0]["value"]) == values["payload"]
    assert json.loads(fields["targets"][0]["value"]) == values["review_targets"]
    assert parsed.image_sources == ["/scopes/draft-1/evidence/source-1/pages/2.png"]
    assert "Unknown each" in html
    assert "Unknown / 0 mm" in html
    assert "Shared opening" in html and "Existing page observation" in html
    editing = next(item for item in parsed.forms if item["action"].endswith("/preview"))
    assert editing["fields"]["action"][0]["value"] == "edit"
    assert json.loads(editing["fields"]["payload"][0]["value"]) == values["payload"]


def test_failed_or_read_only_preview_cannot_offer_confirmation() -> None:
    for updates in ({"errors": ["A newer revision exists"]},
                    {"has_permission": lambda _permission: False}):
        values = preview_context()
        values.update(updates)
        parsed = Forms(render("draft_pdf_scope_preview.html", values))
        assert not any(item["action"].endswith("/confirm") for item in parsed.forms)
        assert any(item["action"].endswith("/preview") for item in parsed.forms)


def test_shared_editor_preserves_manual_scope_submission() -> None:
    values = context()
    values.pop("page_review")
    html = render("draft_scope.html", values)
    parsed = Forms(html)
    form = next(item for item in parsed.forms if item["action"] == "/scopes/draft-1")
    assert set(form["fields"]) == {"csrf_token", "expected_revision", "payload", "action"}
    assert [item["value"] for item in form["fields"]["action"]] == ["validate", "save"]
    assert "scope-initial-review-targets" not in parsed.ids
    assert not parsed.nested


def test_source_unavailable_preserves_submitted_data_without_review_controls() -> None:
    values = context()
    values.update(document=None, selected_page=None, saved=False, errors=["Source unavailable"])
    html = render("draft_pdf_source.html", values)
    parsed = Forms(html)
    assert "Recover your unsaved entries" in html
    assert "Submitted Draft graph (read-only JSON)" in html
    assert "Existing page observation" in html
    assert "scope-editor" not in parsed.ids
    assert not parsed.image_sources
    assert not any(item["action"].endswith(("/preview", "/confirm")) for item in parsed.forms)
    assert '<img src=x onerror="attack()">' not in html
