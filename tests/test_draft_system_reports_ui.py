from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient
from test_draft_scope_ui import _assert_no_canonical_scope, _csrf, _login
from test_draft_system_match_ui import (
    _find,
    _prepare,
    _review_form,
)
from test_draft_system_match_ui import candidate_app as _candidate_app
from test_draft_system_match_ui import scope_app as _scope_app
from test_draft_system_match_ui import scope_password_hash as _scope_password_hash

from classifire.models import User

candidate_app = _candidate_app
scope_app = _scope_app
scope_password_hash = _scope_password_hash


def test_independent_report_screen_download_history_and_permissions(candidate_app, monkeypatch):
    app = candidate_app
    monkeypatch.setattr(
        "classifire.draft_scope_ui.get_settings",
        lambda: SimpleNamespace(storage_root=app.storage),
    )
    with TestClient(app.scope.app) as client:
        _login(client)
        path = _prepare(client)
        match = _find(client, path, app.release_id)
        assert "Scope and system PDF/Excel reports" in client.get(match).text
        preview = client.get(match + "/reports")
        assert preview.status_code == 200
        assert "Create Scope and System PDF and Excel" in preview.text
        assert "Keeping a candidate is not technical approval" in preview.text
        token = _csrf(preview.text)
        assert client.post(match + "/reports", data={"match_revision": "1"}).status_code == 403
        assert (
            client.post(
                match + "/reports",
                data={
                    "csrf_token": token,
                    "match_revision": "0",
                },
            ).status_code
            == 422
        )
        response = client.post(
            match + "/reports",
            data={
                "csrf_token": token,
                "match_revision": "1",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303, response.text
        report = response.headers["location"]
        page = client.get(report)
        assert page.status_code == 200, page.text
        assert "Saved system review" in page.text
        assert "No measured-limit review saved" in page.text
        pdf = client.get(report + "/download?format=pdf")
        xlsx = client.get(report + "/download?format=xlsx")
        assert pdf.status_code == xlsx.status_code == 200
        assert "CLASSIFIRE-Scope-System-Report" in pdf.headers["content-disposition"]
        assert pdf.headers["cache-control"] == "no-store"
        assert pdf.content.startswith(b"%PDF-")
        assert xlsx.content.startswith(b"PK")
        envelope = client.get(match + "/download").json()
        form = _review_form(client, match, envelope)
        assert client.post(match + "/review", data=form, follow_redirects=False).status_code == 303
        historical_preview = client.get(match + "/reports?revision=1")
        assert historical_preview.status_code == 200
        assert "Selected review is out of date:" in historical_preview.text
        stale = client.get(report)
        assert "Out of date:" in stale.text
        assert f'href="{match}/reports"' in stale.text
        assert client.get(report + "/download?format=pdf").content == pdf.content
        assert client.get(report + "/download?format=xlsx").content == xlsx.content
        _assert_no_canonical_scope(app.scope.factory)
        with app.scope.factory() as db:
            actor = db.get(User, app.scope.users["owner"])
            actor.role = "project_manager"
            db.commit()
        for url in (match + "/reports", report, report + "/download?format=pdf"):
            assert client.get(url).status_code == 403
        listing = client.get(path + "/reports")
        assert listing.status_code == 200
        assert report not in listing.text
