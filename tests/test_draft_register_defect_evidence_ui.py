"""Defect-only evidence uses exact saved identity without inventing physical rows."""

from __future__ import annotations

import copy
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from fastapi.testclient import TestClient
from test_draft_register_evidence_ui import HEADERS, Markup, counts
from test_draft_scope_ui import _assert_no_canonical_scope, _login, _payload, _uid
from test_draft_scope_ui import scope_app as _scope_app
from test_draft_scope_ui import scope_password_hash as _scope_password_hash

from classifire.models import User
from classifire.services import draft_register as register
from classifire.services import draft_scope as scopes

scope_app = _scope_app
scope_password_hash = _scope_password_hash
DEFECT = _uid(91)
OTHER = _uid(92)


@pytest.fixture
def defect_app(scope_app, monkeypatch, tmp_path):
    x = SimpleNamespace(**vars(scope_app))
    x.settings = SimpleNamespace(storage_root=tmp_path / "storage")
    monkeypatch.setattr("classifire.draft_scope_ui.get_settings", lambda: x.settings)
    with x.factory() as db:
        actor = db.get(User, x.users["owner"])
        draft = scopes.create_draft_project(
            db, actor, "SYNTHETIC-DEFECT-EVIDENCE", "Defect-only fixture"
        )
        payload = _payload()
        payload.update(
            defects=[
                {
                    "id": DEFECT,
                    "label": "Unlocated defect A",
                    "description": "No physical relationships established",
                },
                {
                    "id": OTHER,
                    "label": "Unrelated defect B",
                    "description": "Separate saved finding",
                },
            ],
            openings=[],
            services=[],
        )
        scopes.save_revision(db, actor, draft.id, 1, payload)
        x.draft_id = draft.id
        x.scope = scopes.read_revision(db, actor, draft.id, 2)
        db.commit()
    x.path = f"/scopes/{x.draft_id}/register-evidence"
    return x


def query(**changes):
    return {"revision": "2", "defect_id": DEFECT, **changes}


def fragment(response, x):
    assert response.status_code == 200, response.text
    parsed = Markup(response.text)
    assert len(parsed.roots) == 1
    root = parsed.roots[0]
    assert root["data-capability"] == "evidence"
    assert root["data-draft-id"] == x.draft_id
    assert root["data-defect-id"] == DEFECT
    assert root["data-opening-id"] == root["data-service-id"] == ""
    assert root["data-scope-revision"] == "2"
    assert root["data-scope-sha256"] == x.scope["sha256"]
    assert not {"html", "script", "form"} & set(parsed.tags)
    assert response.headers["cache-control"] == "no-store"
    assert {"cookie", "x-classifire-workspace"} <= {
        part.strip().lower() for part in response.headers["vary"].split(",")
    }
    return parsed


def test_defect_only_manual_history_and_fragment_never_create_physical_rows(
    defect_app, monkeypatch
):
    x = defect_app
    with x.factory() as db:
        actor = db.get(User, x.users["owner"])
        current = copy.deepcopy(x.scope["content"])
        current["defects"][0]["label"] = "Later finding title"
        scopes.save_revision(db, actor, x.draft_id, 2, current)
        db.commit()
    for target in (
        "classifire.services.draft_system_matches.create_match",
        "classifire.services.draft_estimates.create_estimate",
        "classifire.services.draft_scope_reports.create_report",
        "classifire.services.calculation.recalculate_estimate",
        "classifire.services.snapshot.lock_snapshot",
    ):
        monkeypatch.setattr(
            target, lambda *a, **k: pytest.fail("Defect evidence must not run another capability")
        )
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        url = x.path + "?" + urlencode(query())
        normal = client.get(url)
        assert normal.status_code == 200 and "html" in Markup(normal.text).tags
        result = client.get(url, headers=HEADERS)
        fragment(result, x)
        assert (
            "Unlocated defect A" in result.text
            and "No physical relationships established" in result.text
        )
        assert "Unrelated defect B" not in result.text and "Later finding title" not in result.text
        assert "No retained evidence references" in result.text
        assert "Saved Scope revision 2" in result.text
        latest = client.get(x.path + "?" + urlencode(query(revision="3")), headers=HEADERS)
        assert latest.status_code == 200 and "Later finding title" in latest.text
        assert client.post(url).status_code == 405
        assert counts(x) == before
    with x.factory() as db:
        actor = db.get(User, x.users["owner"])
        for revision in (2, 3):
            saved = scopes.read_revision(db, actor, x.draft_id, revision)
            assert saved["content"]["openings"] == saved["content"]["services"] == []
        assert scopes.read_revision(db, actor, x.draft_id, 2) == x.scope
    _assert_no_canonical_scope(x.factory)


@pytest.mark.parametrize(
    "values",
    [
        [("defect_id", DEFECT)],
        list(query(revision="02").items()),
        list(query(defect_id="").items()),
        list(query(defect_id="../other").items()),
        list(query(defect_id="00000000-0000-0000-0000-00000000005B").items()),
        [*query().items(), ("defect_id", OTHER)],
        [*query().items(), ("opening_id", _uid(2))],
        [*query().items(), ("service_id", _uid(5))],
        [*query().items(), ("opening_id", "")],
        [*query().items(), ("unknown", "1")],
    ],
)
def test_invalid_or_mixed_defect_selection_is_refused_before_core(defect_app, monkeypatch, values):
    x = defect_app
    monkeypatch.setattr(
        register,
        "evidence_context",
        lambda *a, **k: pytest.fail("Invalid Defect selection reached core"),
    )
    monkeypatch.setattr(
        register,
        "evidence_image",
        lambda *a, **k: pytest.fail("Invalid Defect image selection reached core"),
    )
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        assert client.get(x.path + "?" + urlencode(values)).status_code == 422
        assert (
            client.get(
                x.path + "/image?" + urlencode([*values, ("ref_index", "0"), ("image_id", "page")])
            ).status_code
            == 422
        )
        assert counts(x) == before


@pytest.mark.parametrize(
    "values", [query(defect_id=_uid(999)), query(revision="1"), query(revision="99")]
)
def test_defect_identity_must_exist_in_the_exact_revision(defect_app, values):
    x = defect_app
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        result = client.get(x.path + "?" + urlencode(values))
        assert result.status_code == (404 if values["revision"] == "99" else 422), result.text
        assert "Unlocated defect A" not in result.text
        assert counts(x) == before


def test_defect_evidence_requires_current_owner_access_but_allows_read_only_owner(defect_app):
    x = defect_app
    url = x.path + "?" + urlencode(query())
    image_url = x.path + "/image?" + urlencode(query(ref_index="0", image_id="page"))
    with TestClient(x.app) as client:
        assert client.get(url).status_code == client.get(image_url).status_code == 401
        _login(client, "other")
        before = counts(x)
        assert client.get(url).status_code == client.get(image_url).status_code == 404
        assert counts(x) == before
    with x.factory() as db:
        actor = db.get(User, x.users["other"])
        foreign = scopes.create_draft_project(db, actor, "FOREIGN-DEFECT", "Other project")
        foreign_id = foreign.id
        scopes.save_revision(db, actor, foreign_id, 1, x.scope["content"])
        db.get(User, x.users["owner"]).role = "read_only"
        db.commit()
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        fragment(client.get(url, headers=HEADERS), x)
        assert (
            client.get(f"/scopes/{foreign_id}/register-evidence?" + urlencode(query())).status_code
            == 404
        )
        assert client.get(image_url).status_code == 404
        assert counts(x) == before
        with x.factory() as db:
            db.get(User, x.users["owner"]).is_active = False
            db.commit()
        before = counts(x)
        assert client.get(url).status_code in (401, 403)
        assert client.get(image_url).status_code in (401, 403)
        assert counts(x) == before


def test_defect_fragment_and_image_forward_only_exact_defect_binding(defect_app, monkeypatch):
    x = defect_app
    calls = []

    def read(db, actor, draft_id, **kwargs):
        calls.append(("context", actor.id, draft_id, kwargs))
        return {
            "scope": copy.deepcopy(x.scope),
            "selection": {
                "defect_id": DEFECT,
                "opening_id": None,
                "service_id": None,
                "relationship_warnings": [],
            },
            "notices": [],
            "refs": [
                {
                    "index": 7,
                    "role": "selected_defect",
                    "label": "Synthetic Defect source",
                    "status": "retained",
                    "availability": "verified",
                    "metadata": {"source_kind": "pdf", "source_id": _uid(999)},
                    "text": "<script>Untrusted source text</script>",
                    "fields": [],
                    "images": [{"id": "page", "label": "Original page context"}],
                }
            ],
        }

    image_bytes = b"\x89PNG\r\n\x1a\nsynthetic-defect-preview"

    def image(db, actor, draft_id, **kwargs):
        calls.append(("image", actor.id, draft_id, kwargs))
        return image_bytes, "image/png"

    monkeypatch.setattr(register, "evidence_context", read)
    monkeypatch.setattr(register, "evidence_image", image)
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        result = client.get(x.path + "?" + urlencode(query()), headers=HEADERS)
        parsed = fragment(result, x)
        assert (
            "Defect evidence claim" in result.text and "Defect context</strong>" not in result.text
        )
        assert "&lt;script&gt;" in result.text and "<script>" not in result.text
        assert len(parsed.images) == 1
        image_url = urlsplit(parsed.images[0]["src"])
        assert image_url.path == x.path + "/image"
        assert parse_qs(image_url.query) == {
            "revision": ["2"],
            "defect_id": [DEFECT],
            "ref_index": ["7"],
            "image_id": ["page"],
        }
        response = client.get(parsed.images[0]["src"])
        assert response.status_code == 200 and response.content == image_bytes
        assert response.headers["content-type"] == "image/png"
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        core_args = {
            "scope_revision": 2,
            "opening_id": None,
            "service_id": None,
            "defect_id": DEFECT,
            "settings": x.settings,
        }
        assert calls == [
            ("context", x.users["owner"], x.draft_id, core_args),
            (
                "image",
                x.users["owner"],
                x.draft_id,
                {**core_args, "ref_index": 7, "image_id": "page"},
            ),
        ]
        assert counts(x) == before
