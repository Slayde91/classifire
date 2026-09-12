"""Native register fragments reuse the existing governed Draft authoring routes."""

from __future__ import annotations

from html.parser import HTMLParser
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_estimate_ui import _create_form as _estimate_form
from test_draft_estimate_ui import _RenderedForms, _update_form
from test_draft_scope_ui import _assert_no_canonical_scope, _csrf, _login, _uid
from test_draft_scope_ui import scope_app as _scope_app
from test_draft_scope_ui import scope_password_hash as _scope_password_hash
from test_draft_system_match_ui import _create_form as _match_form
from test_draft_system_match_ui import _find, _prepare, _review_form
from test_draft_system_match_ui import candidate_app as _candidate_app

from classifire.draft_estimate_ui import router as estimate_router
from classifire.models import (
    DraftEstimate,
    DraftEstimateReport,
    DraftEstimateRevision,
    DraftProjectPackage,
    DraftScopeReport,
    DraftSystemMatch,
    DraftSystemMatchRevision,
    User,
)

scope_app = _scope_app
scope_password_hash = _scope_password_hash
candidate_app = _candidate_app
HEADERS = {"X-Classifire-Workspace": "register"}


@pytest.fixture
def workbench_app(candidate_app, monkeypatch):
    candidate_app.scope.app.include_router(estimate_router)
    monkeypatch.setattr(
        "classifire.draft_estimate_ui.get_settings",
        lambda: SimpleNamespace(storage_root=candidate_app.storage),
    )
    return candidate_app


class _Fragment(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.roots = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "data-workbench-content" in values:
            assert tag == "section"
            self.roots.append(values)


def _fragment(response, capability, *, revision="", status=200):
    assert response.status_code == status, response.text
    assert "<html" not in response.text.lower()
    assert "<!doctype" not in response.text.lower()
    assert "<script" not in response.text.lower()
    assert response.headers["cache-control"] == "no-store"
    assert {"x-classifire-workspace", "cookie"} <= {
        value.strip().lower() for value in response.headers["vary"].split(",")
    }
    parsed = _Fragment(response.text)
    assert len(parsed.roots) == 1
    attributes = parsed.roots[0]
    assert attributes["data-capability"] == capability
    assert attributes["data-scope-revision"] == "2"
    assert len(attributes["data-scope-sha256"]) == 64
    assert attributes["data-artifact-revision"] == revision
    return attributes


def _add_form(client, detail, *, revision=1, **values):
    target_id = values.get("target_id", _uid(5))
    target_kind = values.get("target_kind", "service")
    selected = client.get(f"{detail}?revision={revision}&target={target_kind}:{target_id}")
    assert selected.status_code == 200, selected.text
    form = next(
        row for row in _RenderedForms(selected.text).forms if row["url"] == f"{detail}/lines"
    )
    return {
        **form["fields"],
        "quantity": "2",
        "unit_sell_rate": "125.55",
        "description": "Synthetic service-specific repair",
        "source_note": "Explicit manual synthetic rate excluding shared closure work",
        **values,
    }


def _counts(app):
    with app.scope.factory() as db:
        return tuple(
            db.scalar(select(func.count()).select_from(model))
            for model in (
                DraftSystemMatch,
                DraftSystemMatchRevision,
                DraftEstimate,
                DraftEstimateRevision,
                DraftScopeReport,
                DraftEstimateReport,
                DraftProjectPackage,
            )
        )


def test_fragment_mode_is_presentation_only_and_picker_gets_do_not_create_artifacts(workbench_app):
    app = workbench_app
    with TestClient(app.scope.app) as client:
        _login(client)
        path = _prepare(client)
        before = _counts(app)
        for suffix, capability in (("system-matches", "system"), ("estimates", "price")):
            url = f"{path}/{suffix}?scope_revision=2"
            normal = client.get(url)
            assert normal.status_code == 200
            assert "<html" in normal.text.lower()
            assert "data-workbench-content" not in normal.text
            fragment = client.get(url, headers=HEADERS)
            attributes = _fragment(fragment, capability)
            assert attributes["data-draft-id"] == path.split("/")[-1]
            assert attributes["data-artifact-id"] == ""
            assert attributes["data-artifact-sha256"] == ""
            assert f'action="{path}/{suffix}"' in fragment.text
            assert 'name="csrf_token"' in fragment.text
            assert (
                "<html" in client.get(url, headers={"X-Classifire-Workspace": "other"}).text.lower()
            )
        assert _counts(app) == before


def test_fragment_find_review_create_price_override_preserves_exact_history_and_independence(
    workbench_app,
    monkeypatch,
):
    app = workbench_app

    def forbidden(*args, **kwargs):
        pytest.fail("Register authoring must not run a downstream provider or canonical capability")

    for target in (
        "classifire.services.technical.search_for_opening",
        "classifire.services.calculation.recalculate_estimate",
        "classifire.services.snapshot.build_estimate_snapshot",
        "classifire.services.phase8_openresponses_transport.Phase8OpenResponsesTransport.invoke",
    ):
        monkeypatch.setattr(target, forbidden)
    with TestClient(app.scope.app, headers=HEADERS) as client:
        _login(client)
        path = _prepare(client)
        created = client.post(
            f"{path}/system-matches",
            data=_match_form(client, path, app.release_id),
        )
        metadata = _fragment(created, "system", revision="1")
        match_url = f"{path}/system-matches/{metadata['data-artifact-id']}"
        assert metadata["data-opening-id"] == _uid(2)
        assert metadata["data-service-id"] == _uid(6)
        first_match = client.get(f"{match_url}/download?revision=1")
        envelope = first_match.json()
        assert metadata["data-artifact-sha256"] == envelope["sha256"]
        assert _counts(app)[2:] == (0, 0, 0, 0, 0)
        review_form = _review_form(client, match_url, envelope)
        reviewed = client.post(f"{match_url}/review", data=review_form)
        _fragment(reviewed, "system", revision="2")
        second_match = client.get(f"{match_url}/download?revision=2").json()
        assert second_match["decisions"][0]["decision"] == "keep"
        assert second_match["review_status"] == "unreviewed"
        assert _counts(app)[2:] == (0, 0, 0, 0, 0)

        created = client.post(
            f"{path}/estimates",
            data=_estimate_form(
                client,
                path,
                match_id=metadata["data-artifact-id"],
                match_revision="2",
            ),
        )
        metadata = _fragment(created, "price", revision="1")
        estimate_url = f"{path}/estimates/{metadata['data-artifact-id']}"
        assert "No work lines yet" in created.text
        added = client.post(
            f"{estimate_url}/lines",
            data=_add_form(client, estimate_url, target_id=_uid(6), quantity=""),
        )
        _fragment(added, "price", revision="2")
        first_price = client.get(f"{estimate_url}/download?revision=2")
        price_envelope = first_price.json()
        line = price_envelope["lines"][0]
        assert line["quantity"] is None
        assert line["subtotal_ex_tax"] is None
        assert line["pricing_status"] == "unpriced"
        assert price_envelope["system_match"] == second_match
        changed = client.post(
            f"{estimate_url}/lines/{line['line_id']}",
            data=_update_form(
                client,
                estimate_url,
                2,
                quantity="2",
                unit_sell_rate="150",
                reason="Explicit synthetic measured quantity and revised manual rate",
            ),
        )
        metadata = _fragment(changed, "price", revision="3")
        latest = client.get(f"{estimate_url}/download?revision=3").json()
        assert latest["sha256"] == metadata["data-artifact-sha256"]
        assert latest["lines"][0]["subtotal_ex_tax"] == "300.00"
        assert latest["lines"][0]["original_rate"] == "125.55"
        assert latest["lines"][0]["original_quantity"] is None
        assert len(latest["lines"][0]["history"]) == 2
        assert latest["scope"] == envelope["scope"]
        assert latest["system_match"] == second_match
        assert client.get(f"{match_url}/download?revision=1").content == first_match.content
        assert client.get(f"{estimate_url}/download?revision=2").content == first_price.content
        assert _counts(app) == (1, 2, 1, 3, 0, 0, 0)
    _assert_no_canonical_scope(app.scope.factory)


def test_fragment_conflicts_preserve_attempts_and_do_not_append_revisions(workbench_app):
    app = workbench_app
    with TestClient(app.scope.app, headers=HEADERS) as client:
        _login(client)
        path = _prepare(client)
        match_url = _find(client, path, app.release_id)
        match = client.get(f"{match_url}/download").json()
        form = _review_form(client, match_url, match)
        assert client.post(f"{match_url}/review", data=form).status_code == 200
        form[f"notes_{match['candidates'][0]['candidate_id']}"] = "Retain my conflicted notes"
        before = _counts(app)
        refused = client.post(f"{match_url}/review", data=form)
        _fragment(refused, "system", revision="1", status=409)
        assert "Retain my conflicted notes" in refused.text
        assert _counts(app) == before
        created = client.post(f"{path}/estimates", data=_estimate_form(client, path))
        metadata = _fragment(created, "price", revision="1")
        estimate_url = f"{path}/estimates/{metadata['data-artifact-id']}"
        assert (
            client.post(f"{estimate_url}/lines", data=_add_form(client, estimate_url)).status_code
            == 200
        )
        line = client.get(f"{estimate_url}/download").json()["lines"][0]
        form = _update_form(client, estimate_url, 2)
        assert client.post(f"{estimate_url}/lines/{line['line_id']}", data=form).status_code == 200
        before = _counts(app)
        form["reason"] = "Retain my conflicted quantity and rate"
        refused = client.post(f"{estimate_url}/lines/{line['line_id']}", data=form)
        _fragment(refused, "price", revision="2", status=409)
        assert form["reason"] in refused.text
        assert _counts(app) == before
        duplicate = client.post(
            f"{estimate_url}/lines",
            data=_add_form(client, estimate_url, revision=3),
        )
        _fragment(duplicate, "price", revision="3", status=409)
        assert "already has a line" in duplicate.text
        assert _counts(app) == before


@pytest.mark.parametrize("capability", ["system", "price"])
def test_fragment_header_grants_no_owner_csrf_or_write_permission(workbench_app, capability):
    app = workbench_app
    with TestClient(app.scope.app, headers=HEADERS) as owner:
        _login(owner)
        path = _prepare(owner)
        suffix = "system-matches" if capability == "system" else "estimates"
        url = f"{path}/{suffix}"
        form = (
            _match_form(owner, path, app.release_id)
            if capability == "system"
            else _estimate_form(owner, path)
        )
        before = _counts(app)
        forged = {**form, "csrf_token": "invalid-csrf"}  # noqa: S105
        assert owner.post(url, data=forged).status_code == 403
        assert _counts(app) == before
        with app.scope.factory() as db:
            user = db.get(User, app.scope.users["owner"])
            user.role = "read_only"
            db.commit()
        assert owner.post(url, data=form).status_code == 403
        assert _counts(app) == before
    with TestClient(app.scope.app, headers=HEADERS) as other:
        _login(other, "other")
        assert other.get(url).status_code == 404
        form["csrf_token"] = _csrf(other.get("/scopes").text)
        before = _counts(app)
        assert other.post(url, data=form).status_code == 404
        assert _counts(app) == before
    with TestClient(app.scope.app, headers=HEADERS) as anonymous:
        assert anonymous.get(url).status_code == 401


def test_fragment_blank_opening_authoring_keeps_zero_services_and_unknown_quantity(workbench_app):
    app = workbench_app
    with TestClient(app.scope.app, headers=HEADERS) as client:
        _login(client)
        path = _prepare(client)
        form = _match_form(client, path, app.release_id)
        form.update(opening_id=_uid(4), service_id="")
        created = client.post(f"{path}/system-matches", data=form)
        metadata = _fragment(created, "system", revision="1")
        assert metadata["data-opening-id"] == _uid(4)
        assert metadata["data-service-id"] == ""
        match = client.get(f"{path}/system-matches/{metadata['data-artifact-id']}/download").json()
        assert match["target"]["blank_opening"] is True
        assert match["target"]["service_ids"] == []
        assert len(match["scope"]["content"]["services"]) == 2
        created = client.post(f"{path}/estimates", data=_estimate_form(client, path))
        metadata = _fragment(created, "price", revision="1")
        estimate_url = f"{path}/estimates/{metadata['data-artifact-id']}"
        added = client.post(
            f"{estimate_url}/lines",
            data=_add_form(
                client,
                estimate_url,
                target_kind="blank_opening",
                target_id=_uid(4),
                unit="m2",
                quantity="",
                description="Synthetic blank opening closure",
            ),
        )
        _fragment(added, "price", revision="2")
        estimate = client.get(f"{estimate_url}/download").json()
        assert estimate["scope"] == match["scope"]
        assert estimate["lines"][0]["work_basis"] == "blank_opening_closure_only"
        assert estimate["lines"][0]["quantity"] is None
        assert estimate["lines"][0]["subtotal_ex_tax"] is None
        assert _counts(app)[4:] == (0, 0, 0)
    _assert_no_canonical_scope(app.scope.factory)


def test_fragment_measurement_save_keeps_unknowns_and_does_not_change_scope(workbench_app):
    app = workbench_app
    with TestClient(app.scope.app, headers=HEADERS) as client:
        _login(client)
        path = _prepare(client)
        match_url = _find(client, path, app.release_id)
        first = client.get(f"{match_url}/download?revision=1").json()
        page = client.get(match_url)
        form = {
            "csrf_token": _csrf(page.text),
            "expected_revision": "1",
            "candidate_id": first["candidates"][0]["candidate_id"],
            "substrate_thickness_mm": "",
            "annular_gap_min_mm": "",
            "annular_gap_max_mm": "",
            "service_size_min_mm": "",
            "service_size_max_mm": "",
            "service_size_basis": "unknown",
            "source_size_basis": "unknown",
            "measurement_note": "Synthetic review: no reliable measurements are available",
        }
        saved = client.post(f"{match_url}/constraints", data=form)
        _fragment(saved, "system", revision="2")
        reviewed = client.get(f"{match_url}/download?revision=2").json()
        assert reviewed["scope"] == first["scope"]
        assert reviewed["constraint_review"]["inputs"]["service_size_min_mm"] is None
        assert reviewed["review_status"] == "unreviewed"
        assert _counts(app) == (1, 2, 0, 0, 0, 0, 0)
    _assert_no_canonical_scope(app.scope.factory)
