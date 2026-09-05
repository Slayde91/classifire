from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook  # type: ignore[import-untyped]
from sqlalchemy import func, select
from test_draft_estimate_ui import (  # noqa: F401
    _add_form,
    _assert_no_estimate_pipeline,
    _csrf_form,
    _disable_downstream,
    _login,
    _new_estimate,
    _prepare,
    _RenderedForms,
    estimate_app,
    scope_app,
    scope_password_hash,
)

from classifire.models import DraftEstimateReport, User


def create(client):
    path = _prepare(client)
    detail = _new_estimate(client, path)
    assert (
        client.post(
            detail + "/lines", data=_add_form(client, detail), follow_redirects=False
        ).status_code
        == 303
    )
    preview = client.get(detail + "/reports?revision=2")
    assert preview.status_code == 200, preview.text
    form = next(
        item
        for item in _RenderedForms(preview.text).forms
        if item["url"] == detail + "/reports" and item["fields"].get("csrf_token")
    )
    assert set(form["fields"]) == {"csrf_token", "revision"}
    response = client.post(form["url"], data=form["fields"], follow_redirects=False)
    assert response.status_code == 303, response.text
    return detail, response.headers["location"]


def test_rendered_report_forms_downloads_and_stale_history(estimate_app, monkeypatch):  # noqa: F811
    _disable_downstream(monkeypatch)
    with TestClient(estimate_app.scope.app) as client:
        _login(client)
        detail, report = create(client)
        saved = client.get(report)
        assert saved.status_code == 200 and "Download saved Estimate PDF" in saved.text
        assert "Save line changes" not in saved.text
        pdf = client.get(report + "/download?format=pdf")
        xlsx = client.get(report + "/download?format=xlsx")
        assert pdf.status_code == xlsx.status_code == 200
        assert pdf.content.startswith(b"%PDF-")
        assert pdf.headers["cache-control"] == "no-store"
        assert pdf.headers["x-content-type-options"] == "nosniff"
        assert (
            'attachment; filename="CLASSIFIRE-Draft-Estimate-Report-'
            in pdf.headers["content-disposition"]
        )
        book = load_workbook(io.BytesIO(xlsx.content))
        assert book["Lines"]["G7"].value == "251.10"
        data = client.get(detail + "/download").json()
        changed = client.post(
            detail + "/lines/" + data["lines"][0]["line_id"],
            data=_csrf_form(
                client,
                detail,
                expected_revision="2",
                action="update",
                quantity="3",
                unit_sell_rate="125.55",
                reason="Later synthetic change",
            ),
            follow_redirects=False,
        )
        assert changed.status_code == 303
        stale = client.get(report)
        assert "Saved inputs are out of date" in stale.text
        assert client.get(report + "/download?format=pdf").content == pdf.content
        assert client.get(report + "/download?format=xlsx").content == xlsx.content
        assert client.get(report + "/download?format=csv").status_code == 422
        assert client.get(detail + "/reports?revision=9999").status_code == 404
    _assert_no_estimate_pipeline(estimate_app)


def test_ownership_read_only_export_and_csrf(estimate_app):  # noqa: F811
    with TestClient(estimate_app.scope.app) as client:
        _login(client)
        detail, report = create(client)
        denied = client.post(detail + "/reports", data={"revision": "2"}, follow_redirects=False)
        assert denied.status_code == 403
        with estimate_app.scope.factory() as db:
            assert db.scalar(select(func.count()).select_from(DraftEstimateReport)) == 1
            owner = db.get(User, estimate_app.scope.users["owner"])
            owner.role = "read_only"
            db.commit()
        page = client.get(report)
        assert page.status_code == 200
        assert "Download saved Estimate PDF" not in page.text
        assert client.get(report + "/download?format=pdf").status_code == 403
        assert "Create saved Estimate PDF and XLSX" not in client.get(detail + "/reports").text
    with TestClient(estimate_app.scope.app) as client:
        _login(client, "other")
        assert client.get(report).status_code in (403, 404)
        assert client.get(report + "/download?format=xlsx").status_code in (403, 404)


@pytest.mark.parametrize("extra", [{"profile": "complete"}, {"revision": "0"}, {"revision": "1e2"}])
def test_report_creation_refuses_injected_profile_or_invalid_revision(estimate_app, extra):  # noqa: F811
    with TestClient(estimate_app.scope.app) as client:
        _login(client)
        detail, _report = create(client)
        data = _csrf_form(client, detail, revision="2")
        data.update(extra)
        assert (
            client.post(detail + "/reports", data=data, follow_redirects=False).status_code == 422
        )
        with estimate_app.scope.factory() as db:
            assert db.scalar(select(func.count()).select_from(DraftEstimateReport)) == 1
