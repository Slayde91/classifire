from __future__ import annotations

import io
import json
import zipfile
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_scope import sample_payload, uid
from test_draft_scope_ui import _csrf, _login
from test_draft_scope_ui import scope_app as _scope_app
from test_draft_scope_ui import scope_password_hash as _password_hash

from classifire.draft_work_record_ui import router
from classifire.models import DraftWorkRecord, User
from classifire.services import draft_scope as scopes

scope_app = _scope_app
scope_password_hash = _password_hash


class Inputs(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.fields = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and attrs.get("type") == "hidden" and attrs.get("name"):
            self.fields[attrs["name"]] = attrs.get("value", "")


@pytest.fixture
def work_app(scope_app):
    scope_app.app.include_router(router)
    with scope_app.factory() as db:
        actor = db.get(User, scope_app.users["owner"])
        draft = scopes.create_draft_project(db, actor, "WORK-UI", "Synthetic work record")
        scopes.save_revision(db, actor, draft.id, 1, sample_payload())
        db.commit()
        identity = draft.id
    return scope_app, identity


def test_panel_preview_confirmation_reopen_and_exact_zip(work_app, tmp_path):
    app, identity = work_app
    base = f"/scopes/{identity}/work-records"
    headers = {"X-Classifire-Workspace": "register"}
    with TestClient(app.app) as client:
        _login(client)
        page = client.get(
            base,
            params={"scope_revision": 2, "opening_id": uid(2), "service_id": uid(6)},
            headers=headers,
        )
        assert page.status_code == 200, page.text
        assert 'data-capability="work"' in page.text
        assert 'data-opening-id="' + uid(2) + '"' in page.text
        form = Inputs(page.text).fields | {
            "note": "Synthetic <script>unsafe()</script> reported work",
            "reported_by": "",
            "reported_role": "unknown",
            "observed_at": "",
            "unknowns": "No inspection supplied",
        }
        preview = client.post(base + "/preview", data=form, headers=headers)
        assert preview.status_code == 200, preview.text
        assert "nothing saved" in preview.text and "&lt;script&gt;" in preview.text
        with app.factory() as db:
            assert db.scalar(select(func.count()).select_from(DraftWorkRecord)) == 0
        confirm = Inputs(preview.text).fields | {"confirm": "save"}
        tampered = dict(confirm)
        content = json.loads(tampered["payload"])
        content["note"] = "Changed after review"
        tampered["payload"] = json.dumps(content)
        assert client.post(base + "/confirm", data=tampered).status_code == 409
        missing = dict(confirm)
        missing.pop("confirm")
        assert client.post(base + "/confirm", data=missing).status_code == 422
        saved = client.post(base + "/confirm", data=confirm, follow_redirects=False)
        assert saved.status_code == 303, saved.text
        url = saved.headers["location"]
        shown = client.get(url, headers=headers)
        assert shown.status_code == 200 and "Recorded work revision 1" in shown.text
        assert client.post(base + "/confirm", data=confirm).status_code == 409
        download = url.replace("?revision=", "/download?revision=")
        first = client.get(download)
        assert first.status_code == 200 and first.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(first.content)) as archive:
            report = archive.read("report.html").decode()
            assert "&lt;script&gt;" in report and "<script>unsafe()" not in report
            assert "Unknown / not supplied" in report
            (tmp_path / "work-report.html").write_text(report, encoding="utf-8")
        (tmp_path / "work-report.zip").write_bytes(first.content)
        (tmp_path / "panel.html").write_text(shown.text, encoding="utf-8")
        cookies = dict(client.cookies)
    with TestClient(app.app) as reopened:
        reopened.cookies.update(cookies)
        assert reopened.get(download).content == first.content
        edit = reopened.get(url + "&edit=true", headers=headers)
        assert edit.status_code == 200 and 'value="1"' in edit.text


def test_cross_user_session_csrf_and_stale_confirmation(work_app):
    app, identity = work_app
    base = f"/scopes/{identity}/work-records"
    with TestClient(app.app) as owner, TestClient(app.app) as other:
        _login(owner)
        _login(other, "other")
        page = owner.get(base, params={"scope_revision": 2, "opening_id": uid(4)})
        assert page.status_code == 200
        form = Inputs(page.text).fields | {
            "note": "Blank opening work assertion",
            "reported_role": "unknown",
        }
        no_csrf = dict(form)
        no_csrf.pop("csrf_token")
        assert owner.post(base + "/preview", data=no_csrf).status_code == 403
        preview = owner.post(base + "/preview", data=form)
        assert preview.status_code == 200, preview.text
        confirm = Inputs(preview.text).fields | {"confirm": "save"}
        other_form = dict(confirm)
        other_form["csrf_token"] = _csrf(other.get("/scopes").text)
        assert other.post(base + "/confirm", data=other_form).status_code == 422
        assert (
            other.get(base, params={"scope_revision": 2, "opening_id": uid(4)}).status_code == 404
        )
        with app.factory() as db:
            scopes.save_revision(
                db, db.get(User, app.users["owner"]), identity, 2, sample_payload()
            )
            db.commit()
        assert owner.post(base + "/confirm", data=confirm).status_code == 409
        with app.factory() as db:
            assert db.scalar(select(func.count()).select_from(DraftWorkRecord)) == 0
