"""Read-only register evidence HTTP boundaries over isolated synthetic Scope fixtures."""

from __future__ import annotations

import copy
import re
from html.parser import HTMLParser
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_scope_ui import _assert_no_canonical_scope, _login, _payload, _uid
from test_draft_scope_ui import scope_app as _scope_app
from test_draft_scope_ui import scope_password_hash as _scope_password_hash

from classifire.db import Base
from classifire.models import User
from classifire.services import draft_register as register
from classifire.services import draft_scope as scopes

scope_app = _scope_app
scope_password_hash = _scope_password_hash
HEADERS = {"X-Classifire-Workspace": "register"}


class Markup(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.roots, self.images, self.tags = [], [], []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        self.tags.append(tag)
        if "data-workbench-content" in values:
            self.roots.append(values)
        if tag == "img":
            self.images.append(values)


@pytest.fixture
def evidence_app(scope_app, monkeypatch, tmp_path):
    x = SimpleNamespace(**vars(scope_app))
    x.settings = SimpleNamespace(storage_root=tmp_path / "storage")
    monkeypatch.setattr("classifire.draft_scope_ui.get_settings", lambda: x.settings)
    with x.factory() as db:
        actor = db.get(User, x.users["owner"])
        draft = scopes.create_draft_project(db, actor, "SYNTHETIC-EVIDENCE", "Row evidence fixture")
        payload = _payload()
        payload["services"].append(
            {
                "id": _uid(8),
                "label": "Unlinked synthetic service",
                "opening_ids": [],
                "quantity": None,
                "unit": "each",
                "state": "Unresolved",
            }
        )
        scopes.save_revision(db, actor, draft.id, 1, payload)
        x.draft_id = draft.id
        x.scope = scopes.read_revision(db, actor, draft.id, 2)
        db.commit()
    x.path = f"/scopes/{x.draft_id}/register-evidence"
    return x


def query(**changes):
    return {"revision": "2", "opening_id": _uid(2), "service_id": _uid(5), **changes}


def counts(x):
    with x.factory() as db:
        return {
            table.name: db.scalar(select(func.count()).select_from(table))
            for table in Base.metadata.sorted_tables
        }


def assert_fragment(response, x, *, opening_id=_uid(2), service_id=_uid(5)):
    assert response.status_code == 200, response.text
    parsed = Markup(response.text)
    assert not {"html", "script", "form"} & set(parsed.tags)
    assert len(parsed.roots) == 1
    root = parsed.roots[0]
    assert root["data-capability"] == "evidence"
    assert root["data-draft-id"] == x.draft_id
    assert root["data-scope-revision"] == "2"
    assert root["data-scope-sha256"] == x.scope["sha256"]
    assert root["data-opening-id"] == (opening_id or "")
    assert root["data-service-id"] == (service_id or "")
    assert (
        root["data-artifact-id"]
        == root["data-artifact-revision"]
        == root["data-artifact-sha256"]
        == ""
    )
    assert response.headers["cache-control"] == "no-store"
    assert {"cookie", "x-classifire-workspace"} <= {
        s.strip().lower() for s in response.headers["vary"].split(",")
    }
    return parsed


def test_real_manual_row_full_page_fragment_history_and_no_writes(evidence_app, monkeypatch):
    x = evidence_app
    for target in (
        "classifire.services.draft_system_matches.create_match",
        "classifire.services.draft_estimates.create_estimate",
        "classifire.services.draft_scope_reports.create_report",
        "classifire.services.calculation.recalculate_estimate",
        "classifire.services.snapshot.lock_snapshot",
    ):
        monkeypatch.setattr(target, lambda *a, **k: pytest.fail("Implicit downstream capability"))
    with x.factory() as db:
        actor = db.get(User, x.users["owner"])
        changed = copy.deepcopy(x.scope["content"])
        changed["services"][0]["label"] = "Later Service label is not historical"
        scopes.save_revision(db, actor, x.draft_id, 2, changed)
        db.commit()
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        url = x.path + "?" + urlencode(query())
        normal = client.get(url)
        assert normal.status_code == 200 and "html" in Markup(normal.text).tags
        fragment = client.get(url, headers=HEADERS)
        assert_fragment(fragment, x)
        assert "Cable group" in fragment.text and "Later Service label" not in fragment.text
        assert "Saved Scope revision 2" in fragment.text
        assert "No retained evidence references" in fragment.text
        assert "Manual values and unknowns remain as saved" in fragment.text
        assert (
            "data-workbench-content"
            not in client.get(url, headers={"X-Classifire-Workspace": "other"}).text
        )
        assert client.post(url).status_code == 405
        assert counts(x) == before
    _assert_no_canonical_scope(x.factory)


@pytest.mark.parametrize("selection", ["blank", "opening", "unlinked"])
def test_real_blank_opening_and_unlinked_service_are_readable_without_invented_links(
    evidence_app, selection
):
    x = evidence_app
    values = {"revision": "2"}
    if selection == "unlinked":
        values["service_id"] = _uid(8)
    else:
        values["opening_id"] = _uid(4 if selection == "blank" else 2)
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        response = client.get(x.path + "?" + urlencode(values), headers=HEADERS)
        assert_fragment(
            response, x, opening_id=values.get("opening_id"), service_id=values.get("service_id")
        )
        assert "No retained evidence references" in response.text
        if selection == "unlinked":
            assert "Unlinked synthetic service" in response.text
        assert counts(x) == before


@pytest.mark.parametrize(
    "bad",
    [
        [("opening_id", _uid(2))],
        [("revision", "2")],
        [*query().items(), ("revision", "2")],
        [*query().items(), ("opening_id", _uid(3))],
        [*query().items(), ("unknown", "x")],
        list(query(revision="0").items()),
        list(query(revision="02").items()),
        list(query(revision="-1").items()),
        list(query(revision="2147483648").items()),
        list(query(revision="?").items()),
        list(query(opening_id="").items()),
        list(query(service_id="../other").items()),
        list(query(service_id="a" * 600).items()),
    ],
)
def test_invalid_queries_fail_before_source_context(evidence_app, monkeypatch, bad):
    x = evidence_app
    monkeypatch.setattr(
        register,
        "evidence_context",
        lambda *a, **k: pytest.fail("Invalid query reached source reader"),
    )
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        response = client.get(x.path + "?" + urlencode(bad), headers=HEADERS)
        assert response.status_code == 422
        assert "data-workbench-content" not in response.text
        assert counts(x) == before


@pytest.mark.parametrize(
    "values",
    [
        query(opening_id=_uid(4)),
        {"revision": "2", "service_id": _uid(5)},
        query(service_id=_uid(999)),
        query(revision="1"),
    ],
)
def test_real_missing_historical_or_mismatched_row_is_not_substituted(evidence_app, values):
    x = evidence_app
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        response = client.get(x.path + "?" + urlencode(values))
        assert response.status_code == 422, response.text
        assert counts(x) == before


def test_owner_read_only_foreign_and_anonymous_boundaries(evidence_app):
    x = evidence_app
    url = x.path + "?" + urlencode(query())
    image_url = x.path + "/image?" + urlencode(query(ref_index="0", image_id="page"))
    with TestClient(x.app) as client:
        assert client.get(url).status_code == 401
        assert client.get(image_url).status_code == 401
        _login(client, "other")
        before = counts(x)
        assert client.get(url).status_code == 404
        assert client.get(image_url).status_code == 404
        assert counts(x) == before
    with x.factory() as db:
        db.get(User, x.users["owner"]).role = "read_only"
        db.commit()
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        assert_fragment(client.get(url, headers=HEADERS), x)
        assert client.get(image_url).status_code == 404
        assert counts(x) == before


def context(x, *, available=True):
    hostile = '<script>alert("synthetic")</script><img src=x onerror=evil()>'
    return {
        "scope": copy.deepcopy(x.scope),
        "selection": {
            "opening_id": _uid(2),
            "service_id": _uid(5),
            "defect_id": _uid(1),
            "relationship_warnings": [hostile],
        },
        "notices": ["Synthetic context only"],
        "refs": [
            {
                "index": 4,
                "role": "selected_service",
                "label": hostile,
                "status": "retained",
                "availability": "verified" if available else "unavailable",
                "metadata": {"filename": hostile, "source_sha256": "a" * 64},
                "text": hostile if available else None,
                "fields": [
                    {"label": hostile, "value": hostile},
                    {"label": "quantity", "value": None},
                ]
                if available
                else [],
                "images": [{"id": "picture:1&x=<bad>", "label": hostile}] if available else [],
            }
        ],
    }


@pytest.mark.parametrize("available", [False, True])
def test_template_escapes_source_context_and_unavailable_refs_have_no_body(
    evidence_app, monkeypatch, available
):
    x = evidence_app
    forwarded = []

    def read(db, actor, draft_id, **kwargs):
        forwarded.append((actor.id, draft_id, kwargs))
        return context(x, available=available)

    monkeypatch.setattr(register, "evidence_context", read)
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        response = client.get(x.path + "?" + urlencode(query()), headers=HEADERS)
        parsed = assert_fragment(response, x)
        assert forwarded == [
            (
                x.users["owner"],
                x.draft_id,
                {
                    "scope_revision": 2,
                    "opening_id": _uid(2),
                    "service_id": _uid(5),
                    "settings": x.settings,
                },
            )
        ]
        assert "&lt;script&gt;" in response.text and "<script>" not in response.text
        assert "<img src=x" not in response.text
        if available:
            assert (
                "Retained source text" in response.text
                and "Retained source binding checked" in response.text
            )
            assert len(parsed.images) == 1
            image_url = urlsplit(parsed.images[0]["src"])
            assert image_url.path == x.path + "/image"
            assert parse_qs(image_url.query) == {
                **{key: [value] for key, value in query().items()},
                "ref_index": ["4"],
                "image_id": ["picture:1&x=<bad>"],
            }
            assert "<td>Unknown / unavailable</td>" in response.text
        else:
            assert "Source preview unavailable" in response.text
            assert "Retained source text" not in response.text and "<table" not in response.text
            assert parsed.images == []
        assert counts(x) == before


def test_mapped_blank_cell_is_distinct_from_unmapped_field(evidence_app, monkeypatch):
    x = evidence_app
    source = context(x)
    source["refs"][0]["fields"] = [
        {"label": "Mapped quantity", "value": None, "address": None, "mapped": True},
        {"label": "Unmapped substrate", "value": None, "address": None, "mapped": False},
    ]
    monkeypatch.setattr(register, "evidence_context", lambda *a, **k: copy.deepcopy(source))
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        response = client.get(x.path + "?" + urlencode(query()), headers=HEADERS)
        assert_fragment(response, x)
        rows = re.findall(r"<tr><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td></tr>", response.text)
        assert rows == [
            ("Mapped quantity", "Mapped cell is blank", "Unknown / unavailable"),
            ("Unmapped substrate", "Not mapped", "Unknown / unavailable"),
        ]
        assert counts(x) == before


def test_image_endpoint_forwards_exact_binding_and_uses_safe_content_headers(
    evidence_app, monkeypatch
):
    x = evidence_app
    forwarded = []
    content = b"\x89PNG\r\n\x1a\nsynthetic-preview"

    def image(db, actor, draft_id, **kwargs):
        forwarded.append((actor.id, draft_id, kwargs))
        return content, "image/png"

    monkeypatch.setattr(register, "evidence_image", image)
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        result = client.get(
            x.path + "/image?" + urlencode(query(ref_index="4", image_id="picture:1"))
        )
        assert result.status_code == 200 and result.content == content
        assert result.headers["content-type"] == "image/png"
        assert result.headers["cache-control"] == "no-store"
        assert result.headers["x-content-type-options"] == "nosniff"
        assert "cookie" in result.headers["vary"].lower()
        assert forwarded == [
            (
                x.users["owner"],
                x.draft_id,
                {
                    "scope_revision": 2,
                    "opening_id": _uid(2),
                    "service_id": _uid(5),
                    "ref_index": 4,
                    "image_id": "picture:1",
                    "settings": x.settings,
                },
            )
        ]
        assert counts(x) == before


@pytest.mark.parametrize(
    "changes",
    [
        {"ref_index": "-1"},
        {"ref_index": "01"},
        {"ref_index": "10000"},
        {"ref_index": ""},
        {"image_id": ""},
        {"image_id": "x" * 129},
        {"source_id": _uid(99)},
    ],
)
def test_image_invalid_binding_never_reaches_reader(evidence_app, monkeypatch, changes):
    x = evidence_app
    monkeypatch.setattr(
        register,
        "evidence_image",
        lambda *a, **k: pytest.fail("Invalid image query reached reader"),
    )
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        values = (
            query(ref_index="4", image_id="page", **changes)
            if not ({"ref_index", "image_id"} & set(changes))
            else {**query(ref_index="4", image_id="page"), **changes}
        )
        assert client.get(x.path + "/image?" + urlencode(values)).status_code == 422
        assert counts(x) == before


@pytest.mark.parametrize(
    "status, code",
    [
        (403, "PERMISSION_DENIED"),
        (404, "REGISTER_EVIDENCE_IMAGE_NOT_FOUND"),
        (409, "REGISTER_EVIDENCE_SOURCE_UNAVAILABLE"),
    ],
)
def test_image_refusal_preserves_status_without_replacement_body(
    evidence_app, monkeypatch, status, code
):
    x = evidence_app

    def unavailable(*a, **k):
        raise scopes.DraftScopeError(code, status)

    monkeypatch.setattr(register, "evidence_image", unavailable)
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        result = client.get(x.path + "/image?" + urlencode(query(ref_index="4", image_id="page")))
        assert result.status_code == status and result.json()["detail"] == code
        assert result.headers["content-type"].startswith("application/json")
        assert counts(x) == before
