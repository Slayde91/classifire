from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_pdf_intake import pdf_setup as _pdf_setup
from test_draft_pdf_ui import pdf_app as _pdf_app
from test_draft_scope import sample_payload, uid
from test_draft_scope_ui import _csrf, _login
from test_draft_scope_ui import scope_password_hash as _password_hash
from test_draft_work_photos import photo_bytes
from test_draft_work_records_ui import Inputs
from test_shared_file_containment import postgresql_session_factory as _postgres

from classifire.draft_work_photo_ui import router as photo_router
from classifire.draft_work_record_ui import router as work_router
from classifire.models import DraftWorkRecord, User
from classifire.services import draft_scope as scopes

pdf_app = _pdf_app
pdf_setup = _pdf_setup
postgresql_session_factory = _postgres
scope_password_hash = _password_hash


@pytest.fixture
def photo_app(pdf_app, monkeypatch):
    x = pdf_app
    x.app.include_router(photo_router)
    x.app.include_router(work_router)
    monkeypatch.setattr("classifire.draft_work_photo_ui.get_settings", lambda: x.settings)
    monkeypatch.setattr("classifire.draft_work_record_ui.get_settings", lambda: x.settings)
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        saved = scopes.save_revision(db, actor, x.ids[2], 1, sample_payload())
        db.commit()
        x.scope_revision = saved["revision"]
    return x


def test_rendered_http_photo_upload_scan_work_preview_confirm_reopen_and_zip(photo_app):
    x = photo_app
    raw = photo_bytes()
    photo_base = f"/scopes/{x.ids[2]}/work-photos"
    work_base = f"/scopes/{x.ids[2]}/work-records"
    with TestClient(x.app) as client:
        _login(client)
        page = client.get(photo_base)
        assert page.status_code == 200 and "Retain photo for explicit scan" in page.text
        upload = client.post(
            photo_base + "/upload",
            data={"csrf_token": _csrf(page.text)},
            files={"file": ("site.png", raw, "image/png")},
            follow_redirects=False,
        )
        assert upload.status_code == 303, upload.text
        photo_url = upload.headers["location"]
        source_id = photo_url.rsplit("/", 1)[-1]
        assert client.get(photo_url + "/original").status_code == 409
        detail = client.get(photo_url)
        assert detail.status_code == 200 and "pending" in detail.text
        scanned = client.post(
            photo_url + "/scan",
            data={"csrf_token": _csrf(detail.text)},
            follow_redirects=False,
        )
        assert scanned.status_code == 303
        original = client.get(photo_url + "/original")
        assert original.status_code == 200
        assert original.headers["content-type"] == "image/png" and original.content == raw

        page = client.get(
            work_base,
            params={
                "scope_revision": x.scope_revision,
                "opening_id": uid(2),
                "service_id": uid(6),
            },
        )
        assert page.status_code == 200 and "site.png" in page.text
        form = Inputs(page.text).fields | {
            "note": "Synthetic reported work with one direct photo.",
            "reported_by": "",
            "reported_role": "unknown",
            "observed_at": "",
            "unknowns": "Inspection evidence remains unknown.",
            f"photo_{source_id}": "include",
        }
        preview = client.post(work_base + "/preview", data=form)
        assert preview.status_code == 200, preview.text
        assert "1 explicitly selected direct photo" in preview.text
        with x.factory() as db:
            assert db.scalar(select(func.count()).select_from(DraftWorkRecord)) == 0
        confirm = Inputs(preview.text).fields | {"confirm": "save"}
        saved = client.post(work_base + "/confirm", data=confirm, follow_redirects=False)
        assert saved.status_code == 303, saved.text
        saved_url = saved.headers["location"]
        shown = client.get(saved_url)
        assert shown.status_code == 200 and "Selected direct photos" in shown.text
        assert "site.png" in shown.text and "not inspection acceptance" in shown.text
        download_url = saved_url.replace("?revision=", "/download?revision=")
        package = client.get(download_url)
        assert package.status_code == 200
        with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
            photo_names = [
                name for name in archive.namelist() if name.startswith("evidence/photos/")
            ]
            assert len(photo_names) == 1 and archive.read(photo_names[0]) == raw
            assert json.loads(archive.read("work-record.json"))["dependencies"]["photos"][0][
                "source_id"
            ] == source_id
        cookies = dict(client.cookies)
    with TestClient(x.app) as reopened:
        reopened.cookies.update(cookies)
        assert reopened.get(photo_url + "/original").content == raw
        assert reopened.get(download_url).content == package.content


def test_photo_ui_foreign_user_cannot_discover_source(photo_app):
    x = photo_app
    base = f"/scopes/{x.ids[2]}/work-photos"
    with TestClient(x.app) as owner, TestClient(x.app) as other:
        _login(owner)
        page = owner.get(base)
        upload = owner.post(
            base + "/upload",
            data={"csrf_token": _csrf(page.text)},
            files={"file": ("site.png", photo_bytes(), "image/png")},
            follow_redirects=False,
        )
        _login(other, "other")
        assert other.get(upload.headers["location"]).status_code == 404
