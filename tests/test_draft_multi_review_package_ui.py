"""Synthetic multi-review package selection, confirmation and historical reopening."""

from __future__ import annotations

import html
import json
import re
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_estimates import add_payload
from test_draft_project_package_ui import fields
from test_draft_scope_ui import _assert_no_canonical_scope, _login, _payload, _uid
from test_draft_scope_ui import scope_app as _scope_app
from test_draft_scope_ui import scope_password_hash as _scope_password_hash
from test_draft_system_match_ui import candidate_app as _candidate_app

from classifire.config import Settings
from classifire.db import Base
from classifire.draft_project_package_ui import router
from classifire.models import DraftProjectPackage, User
from classifire.services import draft_estimate_reports, draft_scope_reports
from classifire.services import draft_estimates as estimates
from classifire.services import draft_package_import as inspection
from classifire.services import draft_package_materialization as materialization
from classifire.services import draft_project_packages as packages
from classifire.services import draft_scope as scopes
from classifire.services import draft_system_matches as matches

scope_app = _scope_app
scope_password_hash = _scope_password_hash
candidate_app = _candidate_app


@pytest.fixture
def package_app(candidate_app, monkeypatch):
    app = candidate_app.scope
    app.app.include_router(router)
    settings = Settings(_env_file=None, storage_root=candidate_app.storage)
    for module in ("draft_project_package_ui", "draft_scope_ui", "services.draft_project_packages"):
        monkeypatch.setattr(f"classifire.{module}.get_settings", lambda: settings)
    with app.factory() as db:
        actor = db.get(User, app.users["owner"])
        draft = scopes.create_draft_project(db, actor, "MULTI-REVIEW", "Synthetic linked reviews")
        scopes.save_revision(db, actor, draft.id, 1, _payload())
        reviews = [
            matches.create_match(
                db,
                actor,
                draft.id,
                2,
                candidate_app.release_id,
                opening,
                _uid(5),
                storage_root=candidate_app.storage,
            )
            for opening in (_uid(2), _uid(3))
        ]
        estimate = estimates.create_estimate(
            db,
            actor,
            draft.id,
            2,
            match_id=reviews[0].id,
            match_revision=1,
        )
        estimates.add_line(db, actor, draft.id, estimate.id, 1, add_payload())
        original_review = matches.read_match_revision(db, actor, draft.id, reviews[0].id, 1)
        matches.save_review(
            db,
            actor,
            draft.id,
            reviews[0].id,
            1,
            [dict(item, notes="Later synthetic review") for item in original_review["decisions"]],
        )
        x = SimpleNamespace(
            app=app.app,
            factory=app.factory,
            users=app.users,
            draft_id=draft.id,
            review_ids=[item.id for item in reviews],
            estimate_id=estimate.id,
            storage=candidate_app.storage,
            release_id=candidate_app.release_id,
            scope=scopes.read_revision(db, actor, draft.id, 2),
            review_bytes=matches.revision_bytes(db, actor, draft.id, reviews[0].id, 1),
        )
        db.commit()
    x.path = f"/scopes/{x.draft_id}/packages"
    x.query = [
        ("scope_revision", "2"),
        *(("matches", f"{identity}:1") for identity in reversed(x.review_ids)),
        ("estimate_id", x.estimate_id),
        ("estimate_revision", "2"),
    ]
    return x


def counts(app):
    with app.factory() as db:
        return {
            table.name: db.scalar(select(func.count()).select_from(table))
            for table in Base.metadata.sorted_tables
        }


def reopen_url(page):
    found = re.search(r'href="([^"]+)">Reopen saved workspace</a>', page)
    assert found is not None
    return html.unescape(found.group(1))


def forbid_capabilities(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Package selection must not run a downstream capability")

    monkeypatch.setattr(matches, "create_match", forbidden)
    monkeypatch.setattr(estimates, "create_estimate", forbidden)
    monkeypatch.setattr(draft_scope_reports, "create_report", forbidden)
    monkeypatch.setattr(draft_estimate_reports, "create_report", forbidden)


def test_explicit_multi_review_preview_confirm_and_exact_workspace_reopen(package_app, monkeypatch):
    x = package_app
    forbid_capabilities(monkeypatch)
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        page = client.get(x.path + "?" + urlencode(x.query))
        assert page.status_code == 200, page.text
        assert page.headers["cache-control"] == "no-store"
        form = fields(page)
        selected = json.loads(form["selection"])
        assert selected["matches"] == [
            {"match_id": identity, "match_revision": 1} for identity in sorted(x.review_ids)
        ]
        assert selected["match_id"] is None and selected["match_revision"] is None
        for identity in x.review_ids:
            assert f'name="matches" value="{identity}:1" checked' in page.text
        assert f'name="matches" value="{x.review_ids[0]}:2"' not in page.text
        assert counts(x) == before
        assert client.post(x.path, data={**form, "csrf_token": "bad"}).status_code == 403
        assert client.post(x.path, data={**form, "preview_hash": "0" * 64}).status_code == 409
        assert counts(x) == before
        saved = client.post(x.path, data=form, follow_redirects=False)
        assert saved.status_code == 303, saved.text
        saved_path = saved.headers["location"]
        after = counts(x)
        assert after["draft_project_packages"] == before["draft_project_packages"] + 1
        assert after["audit_events"] == before["audit_events"] + 1
        assert {
            k: v for k, v in after.items() if k not in {"draft_project_packages", "audit_events"}
        } == {
            k: v for k, v in before.items() if k not in {"draft_project_packages", "audit_events"}
        }
        detail = client.get(saved_path)
        link = reopen_url(detail.text)
        assert parse_qs(urlsplit(link).query) == {
            "revision": ["2"],
            "match": [f"{identity}:1" for identity in sorted(x.review_ids)],
            "estimate": [f"{x.estimate_id}:2"],
        }
        reopened = client.get(link)
        assert reopened.status_code == 200, reopened.text
        assert 'name="expected_revision" value="2"' in reopened.text
        assert counts(x) == after
        content = client.get(saved_path + "/download").content
        manifest, members = packages.inspect_archive(content)
        assert manifest["schema_version"] == packages.SCHEMA_V6
        assert members[packages.match_member_path(x.review_ids[0])] == x.review_bytes
        assert json.loads(members["artifacts/scope.json"]) == x.scope
        assert client.post(x.path, data=form).status_code == 409
        with x.factory() as db:
            actor = db.get(User, x.users["owner"])
            changed = _payload()
            changed["services"][0]["quantity"] = "3"
            scopes.save_revision(db, actor, x.draft_id, 2, changed)
            db.commit()
        assert reopen_url(client.get(saved_path).text) == link
        assert client.get(link).status_code == 200
        assert client.get(saved_path + "/download").content == content
    _assert_no_canonical_scope(x.factory)


def test_explicit_old_reviews_survive_recent_list_limit_and_legacy_selection(package_app):
    x = package_app
    with x.factory() as db:
        actor = db.get(User, x.users["owner"])
        for _ in range(matches.MATCH_LIST_LIMIT):
            matches.create_match(
                db,
                actor,
                x.draft_id,
                2,
                x.release_id,
                _uid(2),
                _uid(6),
                storage_root=x.storage,
            )
        db.commit()
        assert not set(x.review_ids) & {
            row.id for row in matches.list_matches(db, actor, x.draft_id)
        }
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        page = client.get(x.path + "?" + urlencode(x.query))
        assert page.status_code == 200, page.text
        for identity in x.review_ids:
            assert f'name="matches" value="{identity}:1" checked' in page.text
        assert f'name="matches" value="{x.review_ids[0]}:2"' not in page.text
        legacy = client.get(
            x.path,
            params={
                "scope_revision": "2",
                "match_id": x.review_ids[0],
                "match_revision": "1",
            },
        )
        assert legacy.status_code == 200, legacy.text
        assert f'<option value="{x.review_ids[0]}" selected>' in legacy.text
        selection = json.loads(fields(legacy)["selection"])
        assert "matches" not in selection
        assert selection["match_id"] == x.review_ids[0] and selection["match_revision"] == 1
        assert counts(x) == before
        saved = client.post(x.path, data=fields(legacy), follow_redirects=False)
        assert saved.status_code == 303
        assert parse_qs(urlsplit(reopen_url(client.get(saved.headers["location"]).text)).query) == {
            "revision": ["2"],
            "match": [f"{x.review_ids[0]}:1"],
        }


@pytest.mark.parametrize(
    "bad",
    [
        "duplicate",
        "different_revision",
        "mixed",
        "leading_zero",
        "missing_revision",
        "invalid_id",
        "too_many",
        "duplicate_scope",
    ],
)
def test_multi_review_query_refuses_malformed_duplicate_and_mixed_selection(package_app, bad):
    x = package_app
    chosen = ("matches", f"{x.review_ids[0]}:1")
    query = {
        "duplicate": [chosen, chosen],
        "different_revision": [chosen, ("matches", f"{x.review_ids[0]}:2")],
        "mixed": [chosen, ("match_id", x.review_ids[0]), ("match_revision", "1")],
        "leading_zero": [("matches", f"{x.review_ids[0]}:01")],
        "missing_revision": [("matches", x.review_ids[0])],
        "invalid_id": [("matches", "not-an-id:1")],
        "too_many": [chosen] * (packages.MAX_SELECTED_MATCHES + 1),
        "duplicate_scope": [("scope_revision", "1"), ("scope_revision", "2")],
    }[bad]
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        assert client.get(x.path + "?" + urlencode(query)).status_code == 422
        assert counts(x) == before


def test_unselected_picker_and_permission_loss_do_not_select_or_expose_reviews(package_app):
    x = package_app
    with TestClient(x.app) as client:
        _login(client)
        initial = client.get(x.path + "?scope_revision=2")
        assert initial.status_code == 200
        selection = json.loads(fields(initial)["selection"])
        assert "matches" not in selection and selection["match_id"] is None
        assert not re.search(r'name="matches"[^>]+checked', initial.text)
        preview = client.get(x.path + "?" + urlencode(x.query))
        saved = client.post(x.path, data=fields(preview), follow_redirects=False)
        assert saved.status_code == 303
        with x.factory() as db:
            actor = db.get(User, x.users["owner"])
            actor.role = "project_manager"
            db.commit()
        before = counts(x)
        assert client.get(x.path + "?" + urlencode(x.query)).status_code == 403
        assert client.get(saved.headers["location"]).status_code == 403
        assert client.post(x.path, data=fields(preview)).status_code == 403
        assert counts(x) == before
    with TestClient(x.app) as client:
        _login(client, "other")
        before = counts(x)
        assert client.get(x.path + "?" + urlencode(x.query)).status_code == 404
        assert client.get(saved.headers["location"]).status_code == 404
        assert counts(x) == before
    with x.factory() as db:
        assert db.scalar(select(func.count()).select_from(DraftProjectPackage)) == 1


def test_selected_estimate_outside_recent_list_remains_in_exact_package_picker(package_app):
    x = package_app
    with x.factory() as db:
        actor = db.get(User, x.users["owner"])
        for _ in range(estimates.ESTIMATE_LIST_LIMIT):
            estimates.create_estimate(db, actor, x.draft_id, 2)
        db.commit()
        assert x.estimate_id not in {
            row.id for row in estimates.list_estimates(db, actor, x.draft_id)
        }
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        page = client.get(x.path + "?" + urlencode(x.query))
        assert page.status_code == 200, page.text
        assert f'<option value="{x.estimate_id}" selected>' in page.text
        selected = json.loads(fields(page)["selection"])
        assert selected["estimate_id"] == x.estimate_id and selected["estimate_revision"] == 2
        assert counts(x) == before


@pytest.mark.parametrize("collection", [True, False], ids=["multi-review-v6", "legacy-single"])
def test_import_landing_reopens_exact_mapped_workspace_and_package_selection(
    package_app, monkeypatch, collection
):
    x = package_app
    with x.factory() as db:
        actor = db.get(User, x.users["owner"])
        selected = {
            "scope_revision": 2,
            "estimate_id": x.estimate_id,
            "estimate_revision": 2,
        }
        if collection:
            selected["matches"] = [
                {"match_id": identity, "match_revision": 1} for identity in x.review_ids
            ]
        else:
            selected.update(match_id=x.review_ids[0], match_revision=1)
        preview = packages.preview(db, actor, x.draft_id, selected)
        package = packages.create_package(
            db, actor, x.draft_id, selected, 0, preview["preview_hash"]
        )
        imported = materialization.create_import(
            db,
            actor,
            package.archive_bytes,
            expected_sha256=package.archive_hash,
            reference="MAPPED-LINKS",
            name="Synthetic imported review links",
            settings=Settings(_env_file=None, storage_root=x.storage),
        )
        imported_id = imported.draft_scope_id
        mapping = json.loads(imported.mapping_json)
        bound_reviews = sorted(
            inspection.match_mappings(mapping), key=lambda item: item["local_id"]
        )
        assert len(bound_reviews) == (2 if collection else 1)
        assert ("matches" in mapping) is collection
        # Later local edits must not change what the import landing page reopens.
        for bound in bound_reviews:
            review = matches.read_match_revision(db, actor, imported_id, bound["local_id"], 1)
            matches.save_review(
                db,
                actor,
                imported_id,
                bound["local_id"],
                1,
                [dict(item, notes="Later local review") for item in review["decisions"]],
            )
        changed = scopes.read_revision(db, actor, imported_id, 2)["content"]
        changed["services"][0]["quantity"] = "4"
        scopes.save_revision(db, actor, imported_id, 2, changed)
        db.commit()
    forbid_capabilities(monkeypatch)
    path = f"/scopes/{imported_id}/imported-package"
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        page = client.get(path)
        assert page.status_code == 200, page.text
        assert page.headers["cache-control"] == "no-store"
        links = {
            label: html.unescape(url)
            for url, label in re.findall(r'href="([^"]+)">([^<]+)</a>', page.text)
        }
        expected_refs = [f"{item['local_id']}:{item['local_revision']}" for item in bound_reviews]
        reopened = links["Reopen imported workspace"]
        assert urlsplit(reopened).path == f"/scopes/{imported_id}"
        assert parse_qs(urlsplit(reopened).query) == {
            "revision": [str(mapping["scope"]["local_revision"])],
            "match": expected_refs,
            "estimate": [
                f"{mapping['estimate']['local_id']}:{mapping['estimate']['local_revision']}"
            ],
        }
        assert client.get(reopened).status_code == 200
        review_urls = [value for value in links.values() if "/system-matches/" in value]
        assert set(review_urls) == {
            f"/scopes/{imported_id}/system-matches/{bound['local_id']}?revision={bound['local_revision']}"
            for bound in bound_reviews
        }
        for link in review_urls:
            response = client.get(link)
            assert response.status_code == 200, response.text
        assert links["Review imported Estimate revision 1"] == (
            f"/scopes/{imported_id}/estimates/{mapping['estimate']['local_id']}?revision=1"
        )
        configured = links["Configure new package"]
        expected_query = {
            "scope_revision": ["2"],
            "estimate_id": [mapping["estimate"]["local_id"]],
            "estimate_revision": ["1"],
        }
        if collection:
            expected_query["matches"] = expected_refs
        else:
            expected_query.update(match_id=[bound_reviews[0]["local_id"]], match_revision=["1"])
        assert parse_qs(urlsplit(configured).query) == expected_query
        configured_page = client.get(configured)
        assert configured_page.status_code == 200, configured_page.text
        package_selection = json.loads(fields(configured_page)["selection"])
        assert package_selection["scope_revision"] == 2
        assert [
            f"{item.match_id}:{item.match_revision}"
            for item in packages.selected_match_references(packages.selection(package_selection))
        ] == expected_refs
        assert ("matches" in package_selection) is collection
        assert package_selection["estimate_revision"] == 1
        assert counts(x) == before
        with x.factory() as db:
            db.get(User, x.users["owner"]).role = "project_manager"
            db.commit()
        before = counts(x)
        assert client.get(path).status_code == 403
        assert counts(x) == before
    with TestClient(x.app) as client:
        _login(client, "other")
        before = counts(x)
        assert client.get(path).status_code == 404
        assert counts(x) == before
    _assert_no_canonical_scope(x.factory)
