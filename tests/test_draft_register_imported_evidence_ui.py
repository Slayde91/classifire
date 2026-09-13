"""Read-only imported-original navigation; binary lineage is tested separately on PostgreSQL."""

from __future__ import annotations

import copy
import hashlib
from html.parser import HTMLParser
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from fastapi.testclient import TestClient
from test_draft_register_defect_evidence_ui import DEFECT, OTHER, fragment, query
from test_draft_register_defect_evidence_ui import defect_app as _defect_app
from test_draft_register_evidence_ui import HEADERS, counts
from test_draft_scope_ui import _assert_no_canonical_scope, _login, _uid
from test_draft_scope_ui import scope_app as _scope_app
from test_draft_scope_ui import scope_password_hash as _scope_password_hash

from classifire import draft_project_package_ui as package_ui
from classifire.models import User
from classifire.services import draft_import_reports as imported_reports
from classifire.services import draft_register as register
from classifire.services import draft_scope as scopes

scope_app = _scope_app
scope_password_hash = _scope_password_hash
defect_app = _defect_app
LOCAL_SOURCE = _uid(800)
FOREIGN_SOURCE = _uid(801)
MEMBER = f"origins/{_uid(802)}.zip!evidence/{FOREIGN_SOURCE}.docx"
HOSTILE = '<script>alert("foreign")</script>'


class Navigation(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.links, self.cards, self.forms, self.elements = [], [], [], []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        value = dict(attrs)
        self.elements.append((tag, value))
        if tag == "a":
            self.links.append(value)
        elif tag == "article":
            self.cards.append(value)
        elif tag == "form":
            self.forms.append(value)


def anchor(path):
    return "evidence-" + hashlib.sha256(path.encode()).hexdigest()


def forbid_actions(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Opening imported evidence navigation must not scan, download or write")

    for name in ("scan", "download", "checked_bytes", "download_original_archive"):
        monkeypatch.setattr(imported_reports, name, forbidden)
    for name in (
        "classifire.services.draft_system_matches.create_match",
        "classifire.services.draft_estimates.create_estimate",
        "classifire.services.draft_scope_reports.create_report",
        "classifire.services.calculation.recalculate_estimate",
        "classifire.services.snapshot.lock_snapshot",
    ):
        monkeypatch.setattr(name, forbidden)


def reference_context(x, monkeypatch, *, availability="imported_unverified", linked=True):
    real_reader = register.evidence_context
    calls = []
    imported_url = f"/scopes/{x.draft_id}/imported-package#{anchor(MEMBER)}"

    def read(db, actor, draft_id, **kwargs):
        calls.append((actor.id, draft_id, kwargs))
        result = real_reader(db, actor, draft_id, **kwargs)
        if result["selection"]["defect_id"] == DEFECT:
            ref = {
                "index": 7,
                "role": "selected_defect",
                "label": HOSTILE,
                "status": "imported_unverified" if availability != "verified" else "retained",
                "availability": availability,
                "metadata": {
                    "source_kind": "docx",
                    "source_id": FOREIGN_SOURCE,
                    "retained_note": HOSTILE,
                },
                "text": None,
                "fields": [],
                "images": [],
            }
            if linked:
                ref["imported_review_url"] = imported_url
            result["refs"] = [ref]
        return result

    monkeypatch.setattr(register, "evidence_context", read)
    return imported_url, calls


def package_context(x, monkeypatch, *, paths=None):
    x.app.include_router(package_ui.router)
    paths = paths or [MEMBER]
    mapping = {
        "scope": {"local_revision": 2},
        "match": None,
        "estimate": None,
        "reports": [],
        "evidence": [
            {
                "source_id": LOCAL_SOURCE,
                "original_source_id": FOREIGN_SOURCE,
                "path": path,
                "sha256": "a" * 64,
            }
            for path in paths
        ],
    }
    calls = []

    def read_import(db, actor, draft_id):
        scopes.get_draft(db, actor, draft_id)
        calls.append(("import", actor.id, draft_id))
        return (
            SimpleNamespace(archive_hash="b" * 64),
            SimpleNamespace(manifest={"project": {"reference": "FOREIGN", "name": HOSTILE}}),
            copy.deepcopy(mapping),
        )

    def source_info(db, actor, draft_id, source_id):
        scopes.get_draft(db, actor, draft_id)
        assert source_id == LOCAL_SOURCE
        calls.append(("source", actor.id, draft_id, source_id))
        return {"id": source_id, "status": "pending", "ready": False, "processing_error": None}

    monkeypatch.setattr(package_ui.materialization, "read_import", read_import)
    monkeypatch.setattr(
        imported_reports, "evidence_intake", lambda fmt: SimpleNamespace(source_info=source_info)
    )
    return mapping, calls


def test_exact_historical_defect_link_opens_matching_review_card_without_actions(
    defect_app, monkeypatch
):
    x = defect_app
    with x.factory() as db:
        actor = db.get(User, x.users["owner"])
        changed = copy.deepcopy(x.scope["content"])
        changed["defects"][0]["label"] = "Later Defect title"
        scopes.save_revision(db, actor, x.draft_id, 2, changed)
        db.commit()
    imported_url, evidence_calls = reference_context(x, monkeypatch)
    _, package_calls = package_context(x, monkeypatch)
    forbid_actions(monkeypatch)
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        url = x.path + "?" + urlencode(query())
        normal = client.get(url)
        assert normal.status_code == 200
        result = client.get(url, headers=HEADERS)
        parsed = fragment(result, x)
        links = [link for link in Navigation(result.text).links if link["href"] == imported_url]
        assert len(links) == 1 and links[0]["target"] == "_blank"
        assert "noopener" in links[0]["rel"].split()
        assert "Review retained imported original" in result.text
        assert "Scanning and downloading remain separate actions" in result.text
        assert "imported claim remains unverified" in result.text
        assert "Imported claim, unverified locally" in result.text
        assert "Retained source binding checked" not in result.text
        assert "Open source review for the current Draft" not in result.text
        assert "Unlocated defect A" in result.text and "Later Defect title" not in result.text
        assert HOSTILE not in result.text and "&lt;script&gt;" in result.text
        assert not parsed.images and "Retained source text" not in result.text
        assert all(
            "/scan" not in link["href"] and "/download" not in link["href"]
            for link in Navigation(result.text).links
        )
        card_page = client.get(imported_url)
        assert card_page.status_code == 200 and card_page.headers["cache-control"] == "no-store"
        cards = Navigation(card_page.text).cards
        assert [card["id"] for card in cards] == [urlsplit(imported_url).fragment]
        assert cards[0]["tabindex"] == "-1"
        assert FOREIGN_SOURCE in card_page.text and MEMBER in card_page.text
        reopen = next(
            link["href"]
            for link in Navigation(card_page.text).links
            if urlsplit(link["href"]).path == f"/scopes/{x.draft_id}"
        )
        assert parse_qs(urlsplit(reopen).query) == {"revision": ["2"]}
        assert counts(x) == before
        assert package_calls == [
            ("import", x.users["owner"], x.draft_id),
            ("source", x.users["owner"], x.draft_id, LOCAL_SOURCE),
        ]
        expected = {
            "scope_revision": 2,
            "opening_id": None,
            "service_id": None,
            "defect_id": DEFECT,
            "settings": x.settings,
        }
        assert evidence_calls == [(x.users["owner"], x.draft_id, expected)] * 2
        other = client.get(x.path + "?" + urlencode(query(defect_id=OTHER)), headers=HEADERS)
        assert other.status_code == 200 and "Review retained imported original" not in other.text
        assert "Unrelated defect B" in other.text and "Unlocated defect A" not in other.text
        assert counts(x) == before
    with x.factory() as db:
        assert scopes.read_revision(db, db.get(User, x.users["owner"]), x.draft_id, 2) == x.scope
    _assert_no_canonical_scope(x.factory)


@pytest.mark.parametrize("availability", ["verified", "unavailable", "imported_unverified"])
def test_no_imported_navigation_is_invented_when_resolver_supplies_no_link(
    defect_app, monkeypatch, availability
):
    x = defect_app
    reference_context(x, monkeypatch, availability=availability, linked=False)
    forbid_actions(monkeypatch)
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        result = client.get(x.path + "?" + urlencode(query()), headers=HEADERS)
        fragment(result, x)
        assert "Review retained imported original" not in result.text
        assert not any("imported-package" in link["href"] for link in Navigation(result.text).links)
        native_url = f"/scopes/{x.draft_id}/word/{FOREIGN_SOURCE}"
        assert (native_url in result.text) == (availability == "verified")
        assert counts(x) == before


def test_nested_members_with_reused_local_source_have_unique_escaped_review_cards(
    defect_app, monkeypatch
):
    x = defect_app
    hostile_path = f'origins/older/"{HOSTILE}"/evidence/{FOREIGN_SOURCE}.docx'
    paths = [MEMBER, "origins/older.zip!" + MEMBER, hostile_path]
    _, calls = package_context(x, monkeypatch, paths=paths)
    forbid_actions(monkeypatch)
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        result = client.get(f"/scopes/{x.draft_id}/imported-package")
        assert result.status_code == 200
        html = Navigation(result.text)
        assert [card["id"] for card in html.cards] == [anchor(path) for path in paths]
        assert len({card["id"] for card in html.cards}) == 3
        assert all(card["tabindex"] == "-1" for card in html.cards)
        assert HOSTILE not in result.text and "&lt;script&gt;" in result.text
        assert result.text.count("Original file identity") == 3
        assert result.text.count("Original source ID</dt><dd>" + FOREIGN_SOURCE) == 3
        assert result.text.count("Original SHA-256</dt><dd>" + "a" * 64) == 3
        assert not any("onclick" in attrs or "onerror" in attrs for _, attrs in html.elements)
        assert [item[3] for item in calls if item[0] == "source"] == [LOCAL_SOURCE] * 3
        advice = [form for form in html.forms if form.get("class") == "chat-form"]
        assert advice == [{"class": "chat-form"}]
        assert all(
            form["method"] == "post" for form in html.forms if form not in advice
        )
        assert counts(x) == before


@pytest.mark.parametrize("status", [403, 409])
def test_current_attachment_metadata_refusal_does_not_expose_identity_or_scan(
    defect_app, monkeypatch, status
):
    x = defect_app
    package_context(x, monkeypatch)
    forbid_actions(monkeypatch)

    def denied(*args, **kwargs):
        raise scopes.DraftScopeError("IMPORTED_SOURCE_UNAVAILABLE", status)

    monkeypatch.setattr(
        imported_reports, "evidence_intake", lambda fmt: SimpleNamespace(source_info=denied)
    )
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        result = client.get(f"/scopes/{x.draft_id}/imported-package")
        assert result.status_code == status
        assert FOREIGN_SOURCE not in result.text and MEMBER not in result.text
        assert "Original file identity" not in result.text
        assert counts(x) == before


def test_navigation_and_card_keep_current_owner_access_and_read_only_permissions(
    defect_app, monkeypatch
):
    x = defect_app
    reference_context(x, monkeypatch)
    _, package_calls = package_context(x, monkeypatch)
    forbid_actions(monkeypatch)
    urls = [x.path + "?" + urlencode(query()), f"/scopes/{x.draft_id}/imported-package"]
    with TestClient(x.app) as client:
        for url in urls:
            assert client.get(url).status_code == 401
        _login(client, "other")
        before = counts(x)
        for url in urls:
            result = client.get(url)
            assert result.status_code == 404
            assert MEMBER not in result.text and "Unlocated defect A" not in result.text
        assert not package_calls and counts(x) == before
    with x.factory() as db:
        db.get(User, x.users["owner"]).role = "read_only"
        db.commit()
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        assert client.get(urls[0]).status_code == 200
        card = client.get(urls[1])
        assert card.status_code == 200 and FOREIGN_SOURCE in card.text
        assert not any(
            form.get("action", "").startswith(f"/scopes/{x.draft_id}/imported-package/")
            for form in Navigation(card.text).forms
        )
        assert "Scan and check file" not in card.text
        assert counts(x) == before
        with x.factory() as db:
            db.get(User, x.users["owner"]).is_active = False
            db.commit()
        before = counts(x)
        for url in urls:
            result = client.get(url)
            assert result.status_code in (401, 403)
            assert FOREIGN_SOURCE not in result.text and MEMBER not in result.text
        assert counts(x) == before
