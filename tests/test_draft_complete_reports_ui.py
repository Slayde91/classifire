from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from test_draft_estimate_ui import (  # noqa: F401
    _add_form,
    _assert_no_estimate_pipeline,
    _csrf_form,
    _disable_downstream,
    _login,
    _new_estimate,
    _prepare,
    _saved_match,
    estimate_app,
    scope_app,
    scope_password_hash,
)

from classifire.models import User


@pytest.mark.parametrize("attached", [False, True])
def test_explicit_complete_preview_create_download_and_rights(estimate_app, attached, monkeypatch):  # noqa: F811
    app = estimate_app
    with TestClient(app.scope.app) as client:
        _login(client)
        path = _prepare(client)
        review = _saved_match(app, path) if attached else None
        _disable_downstream(monkeypatch)
        detail = _new_estimate(
            client,
            path,
            **({"match_id": review["artifact_id"], "match_revision": "1"} if review else {}),
        )
        assert (
            client.post(
                detail + "/lines", data=_add_form(client, detail), follow_redirects=False
            ).status_code
            == 303
        )
        preview = client.get(detail + "/reports?revision=2&profile=complete")
        assert preview.status_code == 200
        assert preview.text.lstrip("\ufeff \r\n\t").startswith("<!doctype html>")
        assert (
            "Complete Draft Report" in preview.text
            and 'name="profile" value="complete"' in preview.text
        )
        assert "Saved Scope content" in preview.text and "Saved technical review" in preview.text
        assert (
            "Saved review and coverage" if attached else "Unavailable - no System Match"
        ) in preview.text
        assert "Save line changes" not in preview.text
        assert client.get(detail + "/reports?profile=canonical").status_code == 422
        assert (
            client.post(
                detail + "/reports", data={"revision": "2", "profile": "complete"}
            ).status_code
            == 403
        )
        response = client.post(
            detail + "/reports",
            data=_csrf_form(client, detail, revision="2", profile="complete"),
            follow_redirects=False,
        )
        assert response.status_code == 303
        report = response.headers["location"]
        page = client.get(report)
        assert page.text.lstrip("\ufeff \r\n\t").startswith("<!doctype html>")
        assert "Download saved Complete PDF" in page.text
        assert "Complete &middot; Estimate revision 2" in client.get(detail + "/reports").text
        pdf = client.get(report + "/download?format=pdf")
        xlsx = client.get(report + "/download?format=xlsx")
        assert pdf.status_code == xlsx.status_code == 200
        assert "CLASSIFIRE-Draft-Complete-Report-" in pdf.headers["content-disposition"]
        assert pdf.headers["cache-control"] == "no-store"
        assert "251.10" in "\n".join(
            p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages
        )
        data = client.get(detail + "/download").json()
        assert (
            client.post(
                detail + "/lines/" + data["lines"][0]["line_id"],
                data=_csrf_form(
                    client,
                    detail,
                    expected_revision="2",
                    action="update",
                    quantity="3",
                    unit_sell_rate="125.55",
                    reason="Later synthetic input",
                ),
                follow_redirects=False,
            ).status_code
            == 303
        )
        assert "Saved inputs are out of date" in client.get(report).text
        historical_preview = client.get(detail + "/reports?revision=2&profile=complete")
        assert historical_preview.status_code == 200
        assert "Report estimate changed" in historical_preview.text
        assert client.get(report + "/download?format=pdf").content == pdf.content
        assert client.get(report + "/download?format=xlsx").content == xlsx.content
        with app.scope.factory() as db:
            actor = db.get(User, app.scope.users["owner"])
            actor.role = "project_manager" if attached else "read_only"
            db.commit()
        assert client.get(report).status_code == (403 if attached else 200)
        assert client.get(report + "/download?format=pdf").status_code == 403
    with TestClient(app.scope.app) as client:
        _login(client, "other")
        assert client.get(report).status_code in (403, 404)
    _assert_no_estimate_pipeline(app)
