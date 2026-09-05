from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_scope_ui import (
    ScopeApplication,
    _assert_no_canonical_scope,
    _create,
    _csrf,
    _edit,
    _login,
    _payload,
    _uid,
)
from test_draft_scope_ui import scope_app as _scope_app
from test_draft_scope_ui import scope_password_hash as _scope_password_hash

from classifire.draft_estimate_ui import router as estimate_router
from classifire.models import AuditEvent, EstimateLine, LibraryRelease, User

scope_app = _scope_app
scope_password_hash = _scope_password_hash


@dataclass(frozen=True)
class EstimateApplication:
    scope: ScopeApplication
    storage: Path


@pytest.fixture
def estimate_app(
    scope_app: ScopeApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> EstimateApplication:
    storage = (tmp_path / "synthetic-estimate-storage").resolve()
    scope_app.app.include_router(estimate_router)
    monkeypatch.setattr(
        "classifire.draft_estimate_ui.get_settings",
        lambda: SimpleNamespace(storage_root=storage),
    )
    return EstimateApplication(scope_app, storage)


def _prepare(client: TestClient, payload: dict[str, Any] | None = None) -> str:
    path = _create(client, "MANUAL-ESTIMATE-SCOPE")
    assert _edit(client, path, _payload() if payload is None else payload).status_code == 303
    return path


def _csrf_form(client: TestClient, path: str, **values: str) -> dict[str, str]:
    response = client.get(path)
    assert response.status_code == 200, response.text
    return {"csrf_token": _csrf(response.text), **values}


def _snapshot(client: TestClient, detail: str, revision: int | None = None) -> dict[str, Any]:
    response = client.get(f"{detail}/download" + (f"?revision={revision}" if revision else ""))
    assert response.status_code == 200, response.text
    return response.json()


def _assert_no_estimate_pipeline(app: EstimateApplication) -> None:
    _assert_no_canonical_scope(app.scope.factory)
    with app.scope.factory() as db:
        assert db.scalar(select(func.count()).select_from(EstimateLine)) == 0


def _disable_downstream(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Manual Draft estimating must not run governed estimating, matching, or AI")

    for target in (
        "classifire.services.technical.search_variants",
        "classifire.services.technical.search_for_opening",
        "classifire.services.calculation.calculate_estimate_line",
        "classifire.services.calculation.recalculate_estimate",
        "classifire.services.snapshot.build_estimate_snapshot",
        "classifire.services.snapshot.lock_snapshot",
        "classifire.services.initial_canonicalisation_boundary.require_admission_bound_initial_canonicalisation",
        "classifire.services.phase8_openresponses_transport.Phase8OpenResponsesTransport.invoke",
    ):
        monkeypatch.setattr(target, forbidden)


class _RenderedForms(HTMLParser):
    """Read browser form controls and submit only the clicked action button."""

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None
        self.textarea: str | None = None
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "form":
            self.current = {"url": values.get("action"), "fields": {}, "buttons": {}}
        elif self.current is not None and "disabled" not in values:
            name = values.get("name")
            if (
                name
                and tag == "input"
                and values.get("type") not in {"submit", "button", "checkbox", "radio"}
            ):
                self.current["fields"][name] = values.get("value") or ""
            elif name and tag == "textarea":
                self.textarea = name
                self.current["fields"][name] = ""
            elif name and tag == "button":
                self.current["buttons"][values.get("value", "")] = name

    def handle_data(self, data: str) -> None:
        if self.current is not None and self.textarea is not None:
            self.current["fields"][self.textarea] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "textarea":
            self.textarea = None
        elif tag == "form" and self.current is not None:
            self.forms.append(self.current)
            self.current = None


def _rendered_status_form(
    client: TestClient, detail: str, line_id: str, action: str, reason: str
) -> dict[str, str]:
    forms = _RenderedForms(client.get(detail).text).forms
    form = next(
        item
        for item in forms
        if item["url"] == f"{detail}/lines/{line_id}"
        and (item["fields"].get("action") == action or action in item["buttons"])
    )
    return {**form["fields"], "action": action, "reason": reason}


def _create_form(
    client: TestClient, path: str, *, match_id: str = "", match_revision: str = ""
) -> dict[str, str]:
    return _csrf_form(
        client,
        f"{path}/estimates",
        scope_revision="2",
        match_id=match_id,
        match_revision=match_revision,
    )


def _new_estimate(
    client: TestClient, path: str, *, match_id: str = "", match_revision: str = ""
) -> str:
    response = client.post(
        f"{path}/estimates",
        data=_create_form(client, path, match_id=match_id, match_revision=match_revision),
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    detail = response.headers["location"]
    assert re.fullmatch(rf"{re.escape(path)}/estimates/[0-9a-f-]{{36}}", detail)
    return detail


def _add_form(
    client: TestClient, detail: str, *, revision: int = 1, **values: str
) -> dict[str, str]:
    return _csrf_form(
        client,
        detail,
        **{
            "expected_revision": str(revision),
            "target_kind": "service",
            "target_id": _uid(5),
            "unit": "each",
            "quantity": "2",
            "unit_sell_rate": "125.55",
            "description": "Synthetic service-specific repair",
            "source_note": "Manual synthetic provisional rate; excludes opening closure",
            "reason": "",
            **values,
        },
    )


def _add_line(client: TestClient, detail: str, *, revision: int = 1, **values: str) -> None:
    response = client.post(
        f"{detail}/lines",
        data=_add_form(client, detail, revision=revision, **values),
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text


def _update_form(
    client: TestClient,
    detail: str,
    revision: int,
    *,
    quantity: str = "3",
    unit_sell_rate: str = "125.55",
    reason: str = "Explicit synthetic remeasurement",
) -> dict[str, str]:
    return _csrf_form(
        client,
        detail,
        expected_revision=str(revision),
        action="update",
        quantity=quantity,
        unit_sell_rate=unit_sell_rate,
        reason=reason,
    )


def _counts(app: EstimateApplication) -> tuple[int | None, ...]:
    from classifire.models import DraftEstimate, DraftEstimateRevision

    with app.scope.factory() as db:
        return tuple(
            db.scalar(select(func.count()).select_from(model))
            for model in (DraftEstimate, DraftEstimateRevision, AuditEvent)
        )


@pytest.mark.parametrize(
    "invalid", ["missing-revision", "bad-revision", "incomplete-attachment", "unknown-field"]
)
def test_create_estimate_refuses_invalid_inputs_without_writes(
    estimate_app: EstimateApplication, invalid: str
) -> None:
    app = estimate_app
    with TestClient(app.scope.app) as client:
        _login(client)
        path = _prepare(client)
        form = _create_form(client, path)
        if invalid == "missing-revision":
            form.pop("scope_revision")
        elif invalid == "bad-revision":
            form["scope_revision"] = "-1"
        elif invalid == "incomplete-attachment":
            form["match_id"] = _uid(900)
        else:
            form["approved"] = "true"
        before = _counts(app)
        response = client.post(f"{path}/estimates", data=form, follow_redirects=False)
        assert response.status_code == 422, response.text
        assert _counts(app) == before
    _assert_no_estimate_pipeline(app)


@pytest.mark.parametrize(
    "invalid",
    [
        "nan",
        "infinite",
        "exponent",
        "negative",
        "precision",
        "unit",
        "fractional-each",
        "unit-conversion",
        "unexplained-quantity",
        "nonblank-opening",
        "foreign-target",
    ],
)
def test_invalid_line_input_is_not_saved(estimate_app: EstimateApplication, invalid: str) -> None:
    app = estimate_app
    with TestClient(app.scope.app) as client:
        _login(client)
        path = _prepare(client)
        detail = _new_estimate(client, path)
        form = _add_form(client, detail)
        changes = {
            "nan": {"unit_sell_rate": "NaN"},
            "infinite": {"quantity": "Infinity"},
            "exponent": {"unit_sell_rate": "1e2"},
            "negative": {"unit_sell_rate": "-1"},
            "precision": {"unit_sell_rate": "1.1234567"},
            "unit": {"unit": "tonnes"},
            "fractional-each": {"quantity": "1.5", "reason": "Partial counted item"},
            "unit-conversion": {"unit": "m"},
            "unexplained-quantity": {"quantity": "3"},
            "nonblank-opening": {
                "target_kind": "blank_opening",
                "target_id": _uid(2),
                "reason": "Attempt shared closure",
            },
            "foreign-target": {"target_id": _uid(901)},
        }
        form.update(changes[invalid])
        before = _counts(app)
        response = client.post(f"{detail}/lines", data=form, follow_redirects=False)
        assert response.status_code == 422, response.text
        assert _counts(app) == before
        assert client.get(f"{detail}/download?revision=2").status_code == 404


@pytest.mark.parametrize("invalid", ["oversized", "duplicate", "content-type"])
def test_estimate_http_bounds_refuse_unsafe_forms(
    estimate_app: EstimateApplication, invalid: str
) -> None:
    app = estimate_app
    with TestClient(app.scope.app) as client:
        _login(client)
        path = _prepare(client)
        form = _create_form(client, path)
        before = _counts(app)
        if invalid == "content-type":
            response = client.post(f"{path}/estimates", json=form)
        else:
            content = (
                "x" * (64 * 1024 + 1)
                if invalid == "oversized"
                else urlencode(form) + "&scope_revision=2"
            )
            response = client.post(
                f"{path}/estimates",
                content=content,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        assert (
            response.status_code
            == {"oversized": 413, "duplicate": 422, "content-type": 415}[invalid]
        )
        assert _counts(app) == before


def test_manual_estimate_roundtrip_preserves_arithmetic_override_and_exact_history(
    estimate_app: EstimateApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = estimate_app
    _disable_downstream(monkeypatch)
    with TestClient(app.scope.app) as client:
        _login(client)
        path = _prepare(client)
        before = _counts(app)
        assert client.get(f"{path}/estimates").status_code == 200
        assert _counts(app) == before
        detail = _new_estimate(client, path)
        first = _snapshot(client, detail, 1)
        assert first["scope"]["revision"] == 2
        assert first["system_match"] is None
        assert first["state"] == "Draft"
        assert first["lines"] == []
        assert first["summary"]["is_partial"] is True
        _add_line(client, detail)
        response = client.get(f"{detail}/download?revision=2")
        original_bytes = response.content
        second = response.json()
        line = second["lines"][0]
        assert line["original_quantity"] == "2"
        assert line["original_rate"] == "125.55"
        assert line["subtotal_ex_tax"] == "251.10"
        assert second["summary"]["priced_subtotal_ex_tax"] == "251.10"
        assert second["summary"]["is_partial"] is True
        assert set(second["summary"]["unassessed_opening_ids"]) == {_uid(2), _uid(3)}
        assert "tax_total" not in second["summary"]
        assert response.headers["content-type"].startswith("application/json")
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert re.fullmatch(
            r'attachment; filename="[A-Za-z0-9.-]+"', response.headers["content-disposition"]
        )
        saved = client.post(
            f"{detail}/lines/{line['line_id']}",
            data=_update_form(client, detail, 2),
            follow_redirects=False,
        )
        assert saved.status_code == 303, saved.text
        third = _snapshot(client, detail, 3)
        changed = third["lines"][0]
        assert changed["quantity"] == "3"
        assert changed["original_quantity"] == "2"
        assert changed["original_rate"] == "125.55"
        assert changed["subtotal_ex_tax"] == "376.65"
        assert third["parent_hash"] == second["sha256"]
        assert changed["history"][-1]["reason"] == "Explicit synthetic remeasurement"
        assert changed["history"][-1]["created_by"] == app.scope.users["owner"]
        assert changed["history"][-1]["created_at"]
        assert "376.65" in client.get(detail).text
        assert client.get(f"{detail}/download?revision=2").content == original_bytes
    app.scope.factory.kw["bind"].dispose()
    with TestClient(app.scope.app) as reopened:
        _login(reopened)
        assert reopened.get(f"{detail}/download?revision=2").content == original_bytes
        assert _snapshot(reopened, detail)["revision"] == 3
    with app.scope.factory() as db:
        assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 0
    _assert_no_estimate_pipeline(app)


@pytest.mark.parametrize(
    "qty,unit,rate,expected",
    [
        ("3", "each", "0.333333", "1.00"),
        ("1000", "mm", "0.001234", "1.23"),
        ("2.345678", "m", "12.345678", "28.96"),
    ],
)
def test_explicit_unit_sell_rates_keep_six_decimal_precision_until_line_rounding(
    estimate_app: EstimateApplication,
    qty: str,
    unit: str,
    rate: str,
    expected: str,
) -> None:
    payload = _payload()
    payload["services"][0]["quantity"] = qty
    payload["services"][0]["unit"] = unit
    with TestClient(estimate_app.scope.app) as client:
        _login(client)
        detail = _new_estimate(client, _prepare(client, payload))
        _add_line(client, detail, quantity=qty, unit=unit, unit_sell_rate=rate)
        saved = _snapshot(client, detail)
        assert saved["lines"][0]["unit_sell_rate"] == rate
        assert saved["lines"][0]["subtotal_ex_tax"] == expected
        assert saved["summary"]["priced_subtotal_ex_tax"] == expected


def test_partial_subtotal_sums_rounded_lines(estimate_app: EstimateApplication) -> None:
    with TestClient(estimate_app.scope.app) as client:
        _login(client)
        detail = _new_estimate(client, _prepare(client))
        _add_line(client, detail, quantity="1", unit_sell_rate="0.005", reason="Synthetic one item")
        _add_line(
            client,
            detail,
            revision=2,
            target_id=_uid(6),
            quantity="1",
            unit_sell_rate="0.005",
            reason="Synthetic measured pipe",
        )
        saved = _snapshot(client, detail)
        assert [line["subtotal_ex_tax"] for line in saved["lines"]] == ["0.01", "0.01"]
        assert saved["summary"]["priced_subtotal_ex_tax"] == "0.02"


def test_unknown_inputs_remain_unpriced_while_explicit_zero_and_manual_blank_area_are_preserved(
    estimate_app: EstimateApplication,
) -> None:
    with TestClient(estimate_app.scope.app) as client:
        _login(client)
        detail = _new_estimate(client, _prepare(client))
        _add_line(client, detail, unit_sell_rate="")
        _add_line(client, detail, revision=2, target_id=_uid(6), quantity="", unit_sell_rate="0")
        _add_line(
            client,
            detail,
            revision=3,
            target_kind="blank_opening",
            target_id=_uid(4),
            unit="m2",
            quantity="0",
            unit_sell_rate="25",
            reason="Explicit zero measured area",
        )
        saved = _snapshot(client, detail)
        by_target = {line["target_id"]: line for line in saved["lines"]}
        assert by_target[_uid(5)]["unit_sell_rate"] is None
        assert by_target[_uid(5)]["subtotal_ex_tax"] is None
        assert by_target[_uid(6)]["quantity"] is None
        assert by_target[_uid(6)]["unit_sell_rate"] == "0"
        assert by_target[_uid(6)]["subtotal_ex_tax"] is None
        assert by_target[_uid(4)]["original_quantity"] is None
        assert by_target[_uid(4)]["quantity"] == "0"
        assert by_target[_uid(4)]["subtotal_ex_tax"] == "0.00"
        assert len(saved["summary"]["unpriced_line_ids"]) == 2
        assert saved["summary"]["is_partial"] is True
        assert saved["summary"]["priced_subtotal_ex_tax"] == "0.00"
        page = client.get(detail).text.lower()
        assert "partial" in page and "unpriced" in page


def test_omitted_target_cannot_be_duplicated_and_restores_original_line(
    estimate_app: EstimateApplication,
) -> None:
    app = estimate_app
    with TestClient(app.scope.app) as client:
        _login(client)
        detail = _new_estimate(client, _prepare(client))
        _add_line(client, detail)
        line_id = _snapshot(client, detail)["lines"][0]["line_id"]
        before = _counts(app)
        duplicate = client.post(
            f"{detail}/lines",
            data=_add_form(
                client, detail, revision=2, description="Different wording does not create new work"
            ),
        )
        assert duplicate.status_code == 409
        assert _counts(app) == before
        form = _rendered_status_form(client, detail, line_id, "omit", "Pending site confirmation")
        assert (
            client.post(f"{detail}/lines/{line_id}", data=form, follow_redirects=False).status_code
            == 303
        )
        omitted = _snapshot(client, detail)
        assert omitted["lines"][0]["status"] == "omitted"
        assert omitted["summary"]["omitted_line_ids"] == [line_id]
        assert omitted["summary"]["priced_subtotal_ex_tax"] == "0.00"
        before = _counts(app)
        duplicate = client.post(f"{detail}/lines", data=_add_form(client, detail, revision=3))
        assert duplicate.status_code == 409
        assert _counts(app) == before
        form = _rendered_status_form(
            client, detail, line_id, "restore", "Return the same provisional work"
        )
        assert (
            client.post(f"{detail}/lines/{line_id}", data=form, follow_redirects=False).status_code
            == 303
        )
        restored = _snapshot(client, detail)
        assert len(restored["lines"]) == 1
        assert restored["lines"][0]["line_id"] == line_id
        assert restored["lines"][0]["status"] == "active"
        assert restored["summary"]["priced_subtotal_ex_tax"] == "251.10"


def test_stale_update_keeps_attempted_values_and_old_revision(
    estimate_app: EstimateApplication,
) -> None:
    app = estimate_app
    with TestClient(app.scope.app) as client:
        _login(client)
        detail = _new_estimate(client, _prepare(client))
        _add_line(client, detail)
        second = _snapshot(client, detail)
        line_id = second["lines"][0]["line_id"]
        form = _update_form(client, detail, 2)
        assert (
            client.post(f"{detail}/lines/{line_id}", data=form, follow_redirects=False).status_code
            == 303
        )
        accepted = client.get(f"{detail}/download?revision=3").content
        form.update(quantity="4", reason="Unsaved old-tab measurement")
        before = _counts(app)
        refused = client.post(f"{detail}/lines/{line_id}", data=form, follow_redirects=False)
        assert refused.status_code == 409
        assert "Unsaved old-tab measurement" in refused.text
        assert _counts(app) == before
        assert client.get(f"{detail}/download?revision=3").content == accepted
        assert client.get(f"{detail}/download?revision=4").status_code == 404


@pytest.mark.parametrize("invalid", ["reason", "immutable-field", "blank-area-reason"])
def test_reason_or_immutable_binding_failures_preserve_original(
    estimate_app: EstimateApplication, invalid: str
) -> None:
    app = estimate_app
    with TestClient(app.scope.app) as client:
        _login(client)
        detail = _new_estimate(client, _prepare(client))
        _add_line(client, detail)
        line = _snapshot(client, detail)["lines"][0]
        before = _counts(app)
        if invalid == "blank-area-reason":
            refused = client.post(
                f"{detail}/lines",
                data=_add_form(
                    client,
                    detail,
                    revision=2,
                    target_kind="blank_opening",
                    target_id=_uid(4),
                    unit="m2",
                    quantity="1.5",
                    reason="",
                ),
            )
        else:
            form = _update_form(
                client,
                detail,
                2,
                unit_sell_rate="150",
                reason="" if invalid == "reason" else "Attempted rebinding",
            )
            if invalid == "immutable-field":
                form["target_id"] = _uid(6)
            refused = client.post(f"{detail}/lines/{line['line_id']}", data=form)
        assert refused.status_code == 422
        assert _counts(app) == before
        assert _snapshot(client, detail)["lines"][0] == line


def test_scope_change_marks_estimate_stale_without_changing_download(
    estimate_app: EstimateApplication,
) -> None:
    app = estimate_app
    with TestClient(app.scope.app) as client:
        _login(client)
        path = _prepare(client)
        detail = _new_estimate(client, path)
        _add_line(client, detail)
        original = client.get(f"{detail}/download?revision=2").content
        payload = _payload()
        payload["services"][0]["quantity"] = "20"
        assert _edit(client, path, payload, revision=2).status_code == 303
        before = _counts(app)
        page = client.get(detail)
        assert page.status_code == 200
        assert "Estimate scope changed" in page.text
        assert _counts(app) == before
        assert client.get(f"{detail}/download?revision=2").content == original
        assert _snapshot(client, detail)["summary"]["priced_subtotal_ex_tax"] == "251.10"


def test_estimate_owner_admin_csrf_and_anonymous_boundaries(
    estimate_app: EstimateApplication,
) -> None:
    app = estimate_app
    with TestClient(app.scope.app) as owner:
        _login(owner)
        path = _prepare(owner)
        detail = _new_estimate(owner, path)
        _add_line(owner, detail)
        line_id = _snapshot(owner, detail)["lines"][0]["line_id"]
        create_form = _create_form(owner, path)
        add_form = _add_form(owner, detail, revision=2, target_id=_uid(6), quantity="")
        update_form = _update_form(owner, detail, 2)
        before = _counts(app)
        for url, form in (
            (f"{path}/estimates", create_form),
            (f"{detail}/lines", add_form),
            (f"{detail}/lines/{line_id}", update_form),
        ):
            assert owner.post(url, data={**form, "csrf_token": "forged"}).status_code == 403
        assert _counts(app) == before
    with TestClient(app.scope.app) as anonymous:
        for url in (f"{path}/estimates", detail, f"{detail}/download?revision=2"):
            assert anonymous.get(url).status_code == 401
    with TestClient(app.scope.app) as other:
        _login(other, "other")
        for url in (f"{path}/estimates", detail, f"{detail}/download?revision=2"):
            assert other.get(url).status_code == 404
        csrf = _csrf(other.get("/scopes").text)
        for url, form in (
            (f"{path}/estimates", create_form),
            (f"{detail}/lines", add_form),
            (f"{detail}/lines/{line_id}", update_form),
        ):
            assert other.post(url, data={**form, "csrf_token": csrf}).status_code == 404
    with TestClient(app.scope.app) as admin:
        _login(admin, "admin")
        assert admin.get(detail).status_code == 200
        assert admin.get(f"{detail}/download?revision=2").status_code == 200
        _add_line(admin, detail, revision=2, target_id=_uid(6), quantity="")
    _assert_no_estimate_pipeline(app)


@pytest.mark.parametrize("revoked", ["inactive", "agent", "read-only"])
def test_revoked_estimate_permissions_are_rechecked_for_each_operation(
    estimate_app: EstimateApplication, revoked: str
) -> None:
    app = estimate_app
    with TestClient(app.scope.app) as client:
        _login(client)
        detail = _new_estimate(client, _prepare(client))
        _add_line(client, detail)
        line_id = _snapshot(client, detail)["lines"][0]["line_id"]
        form = _update_form(client, detail, 2)
        with app.scope.factory() as db:
            user = db.get(User, app.scope.users["owner"])
            if revoked == "inactive":
                user.is_active = False
            else:
                user.role = "agent" if revoked == "agent" else "read_only"
            db.commit()
        before = _counts(app)
        expected = 401 if revoked == "inactive" else 403
        assert client.post(f"{detail}/lines/{line_id}", data=form).status_code == expected
        assert client.get(detail).status_code == (200 if revoked == "read-only" else expected)
        assert client.get(f"{detail}/download?revision=2").status_code == expected
        assert _counts(app) == before


def test_description_and_reason_are_escaped_but_exact_in_download(
    estimate_app: EstimateApplication,
) -> None:
    hostile = "</textarea><img src=x onerror=alert(1)>"
    with TestClient(estimate_app.scope.app) as client:
        _login(client)
        detail = _new_estimate(client, _prepare(client))
        _add_line(client, detail, description=hostile, source_note=hostile)
        saved = _snapshot(client, detail)
        line = saved["lines"][0]
        assert line["description"] == hostile
        assert line["source_note"] == hostile
        assert hostile not in client.get(detail).text
        form = _update_form(client, detail, 2, reason=hostile)
        assert (
            client.post(
                f"{detail}/lines/{line['line_id']}", data=form, follow_redirects=False
            ).status_code
            == 303
        )
        assert _snapshot(client, detail)["lines"][0]["history"][-1]["reason"] == hostile
        assert hostile not in client.get(detail).text


def _saved_match(app: EstimateApplication, path: str) -> dict[str, Any]:
    from classifire.services.draft_system_matches import create_match, read_match_revision
    from scripts.draft_system_match_demo_fixture import seed_demo_library

    with app.scope.factory() as db:
        admin = db.get(User, app.scope.users["admin"])
        owner = db.get(User, app.scope.users["owner"])
        assert admin is not None and owner is not None
        release = seed_demo_library(db, app.storage, admin)
        match = create_match(
            db,
            owner,
            path.rsplit("/", 1)[1],
            2,
            release.id,
            _uid(2),
            _uid(6),
            storage_root=app.storage,
        )
        envelope = read_match_revision(db, owner, path.rsplit("/", 1)[1], match.id)
        db.commit()
        return envelope


def test_optional_review_attachment_freezes_exact_unapproved_content_and_stale_history(
    estimate_app: EstimateApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from classifire.services.draft_system_matches import save_review

    app = estimate_app
    with TestClient(app.scope.app) as client:
        _login(client)
        path = _prepare(client)
        review = _saved_match(app, path)
        _disable_downstream(monkeypatch)
        detail = _new_estimate(client, path, match_id=review["artifact_id"], match_revision="1")
        first = client.get(f"{detail}/download?revision=1")
        assert first.json()["system_match"] == review
        assert first.json()["system_match"]["review_status"] == "unreviewed"
        with app.scope.factory() as db:
            owner = db.get(User, app.scope.users["owner"])
            assert owner is not None
            decisions = [
                {
                    "candidate_id": candidate["candidate_id"],
                    "decision": "keep",
                    "notes": "Review preference remains unapproved",
                }
                for candidate in review["candidates"]
            ]
            save_review(db, owner, path.rsplit("/", 1)[1], review["artifact_id"], 1, decisions)
            db.commit()
        before = _counts(app)
        page = client.get(detail)
        assert page.status_code == 200
        assert "Saved inputs are out of date or cannot be verified." in page.text
        assert _counts(app) == before
        assert client.get(f"{detail}/download?revision=1").content == first.content
    _assert_no_estimate_pipeline(app)


def test_attachment_requires_exact_scope_revision_and_rechecks_technical_read(
    estimate_app: EstimateApplication,
) -> None:
    app = estimate_app
    with TestClient(app.scope.app) as client:
        _login(client)
        path = _prepare(client)
        review = _saved_match(app, path)
        form = _create_form(client, path, match_id=review["artifact_id"], match_revision="1")
        form["scope_revision"] = "1"
        before = _counts(app)
        invalid = client.post(f"{path}/estimates", data=form, follow_redirects=False)
        assert invalid.status_code == 422
        assert _counts(app) == before
        attached = _new_estimate(client, path, match_id=review["artifact_id"], match_revision="1")
        plain = _new_estimate(client, path)
        with app.scope.factory() as db:
            owner = db.get(User, app.scope.users["owner"])
            owner.role = "project_manager"
            db.commit()
        before = _counts(app)
        assert client.get(plain).status_code == 200
        assert client.get(attached).status_code == 403
        assert client.get(f"{attached}/download?revision=1").status_code == 403
        assert _counts(app) == before


def test_foreign_review_cannot_be_attached_to_owned_scope(
    estimate_app: EstimateApplication,
) -> None:
    app = estimate_app
    with TestClient(app.scope.app) as owner:
        _login(owner)
        path = _prepare(owner)
        review = _saved_match(app, path)
    with TestClient(app.scope.app) as other:
        _login(other, "other")
        other_path = _create(other, "OTHER-ESTIMATE-SCOPE")
        assert _edit(other, other_path, _payload()).status_code == 303
        form = _create_form(other, other_path, match_id=review["artifact_id"], match_revision="1")
        before = _counts(app)
        refused = other.post(f"{other_path}/estimates", data=form, follow_redirects=False)
        assert refused.status_code == 404
        assert _counts(app) == before


def test_untouched_picker_form_starts_manual_estimate_without_review(
    estimate_app: EstimateApplication,
) -> None:
    with TestClient(estimate_app.scope.app) as client:
        _login(client)
        path = _prepare(client)
        page = client.get(f"{path}/estimates")
        assert page.status_code == 200
        revision_input = re.search(r'<input[^>]+name="match_revision"[^>]*>', page.text)
        assert revision_input is not None
        value = re.search(r'value="([^"]*)"', revision_input.group())
        assert value is not None and value.group(1) == ""
        response = client.post(
            f"{path}/estimates",
            data={
                "csrf_token": _csrf(page.text),
                "scope_revision": "2",
                "match_id": "",
                "match_revision": value.group(1),
            },
            follow_redirects=False,
        )
        assert response.status_code == 303, response.text
        assert _snapshot(client, response.headers["location"])["system_match"] is None


def test_corrupt_retained_subtotal_is_refused_without_export_audit(
    estimate_app: EstimateApplication,
) -> None:
    from classifire.models import DraftEstimateRevision

    app = estimate_app
    with TestClient(app.scope.app) as client:
        _login(client)
        detail = _new_estimate(client, _prepare(client))
        _add_line(client, detail)
        with app.scope.factory() as db:
            row = db.scalar(
                select(DraftEstimateRevision).where(
                    DraftEstimateRevision.estimate_id == detail.rsplit("/", 1)[1],
                    DraftEstimateRevision.revision == 2,
                )
            )
            assert row is not None
            envelope = json.loads(row.envelope_json)
            envelope["lines"][0]["subtotal_ex_tax"] = "0.01"
            row.envelope_json = json.dumps(envelope)
            db.commit()
        before = _counts(app)
        assert client.get(detail).status_code == 409
        assert client.get(f"{detail}/download?revision=2").status_code == 409
        assert _counts(app) == before
