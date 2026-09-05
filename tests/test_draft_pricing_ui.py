from __future__ import annotations

from fastapi.testclient import TestClient
from test_draft_estimates import add_payload
from test_draft_pdf_ui import pdf_app as _pdf_app
from test_draft_pdf_ui import pdf_setup as _pdf_setup
from test_draft_pricing import MAPPING, workbook_bytes
from test_draft_scope import sample_payload
from test_draft_scope_ui import _csrf, _login
from test_draft_scope_ui import scope_password_hash as _password_hash
from test_shared_file_containment import postgresql_session_factory as _postgres_fixture

from classifire.draft_estimate_ui import router as estimate_router
from classifire.draft_pricing_ui import router
from classifire.models import User
from classifire.services import draft_estimates as estimates
from classifire.services import draft_scope as scope

pdf_app = _pdf_app
pdf_setup = _pdf_setup
scope_password_hash = _password_hash
postgresql_session_factory = _postgres_fixture


def test_upload_map_select_download_and_http_boundaries(pdf_app, monkeypatch):
    x = pdf_app
    monkeypatch.setattr("classifire.draft_pricing_ui.get_settings", lambda: x.settings)
    monkeypatch.setattr("classifire.draft_estimate_ui.get_settings", lambda: x.settings)
    x.app.include_router(estimate_router)
    x.app.include_router(router)
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        scope.save_revision(db, actor, x.ids[2], 1, sample_payload())
        estimate = estimates.create_estimate(db, actor, x.ids[2], 2)
        envelope = estimates.add_line(db, actor, x.ids[2], estimate.id, 1, add_payload())
        line_id = envelope["lines"][0]["line_id"]
        base = f"/scopes/{x.ids[2]}/estimates/{estimate.id}"
        db.commit()
    with TestClient(x.app) as client, TestClient(x.app) as other:
        _login(client)
        _login(other, "other")
        page = client.get(base + "/pricing")
        assert page.status_code == 200
        response = client.post(
            base + "/pricing/upload",
            data={"csrf_token": _csrf(page.text)},
            files={"file": ("synthetic.xlsx", workbook_bytes())},
            follow_redirects=False,
        )
        assert response.status_code == 303, response.text
        path = response.headers["location"]
        assert other.get(path).status_code == 404
        assert client.post(path + "/scan", data={"csrf_token": "bad"}).status_code == 403
        token = _csrf(client.get(path).text)
        response = client.post(path + "/scan", data={"csrf_token": token}, follow_redirects=False)
        assert response.status_code == 303, response.text
        form = {
            "csrf_token": token,
            "sheet_index": "1",
            "header_row": "1",
            **{key: str(value) for key, value in MAPPING.items()},
        }
        bad = client.post(path + "/preview", data={**form, "rate": "1"})
        assert bad.status_code == 422
        page = client.post(path + "/preview", data=form)
        assert page.status_code == 200, page.text
        assert "Apply row 2 rate" in page.text
        assert "Apply row 4 rate" not in page.text
        assert "D2: 120.25" in page.text
        import re

        def hidden(name):
            return re.search(r'name="' + name + r'" value="([^"]+)"', page.text).group(1)

        apply = {
            **form,
            "expected_revision": "2",
            "line_id": line_id,
            "row_number": "2",
            "document_sha256": hidden("document_sha256"),
            "row_sha256": hidden("row_sha256"),
            "recovery_note": "Service work only; excludes shared closure",
        }
        response = client.post(path + "/apply", data=apply, follow_redirects=False)
        assert response.status_code == 303, response.text
        download = client.get(base + "/download?revision=3")
        assert download.status_code == 200, download.text
        assert download.json()["pricing_sources"][0]["row"]["fields"]["rate"]["address"] == "D2"
        assert client.post(path + "/apply", data=apply).status_code == 409
