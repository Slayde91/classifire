from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_draft_scope_ui import _assert_no_canonical_scope, _csrf, _login
from test_draft_system_match_ui import CandidateApplication, _find, _prepare
from test_draft_system_match_ui import scope_app as _scope_app
from test_draft_system_match_ui import scope_password_hash as _scope_password_hash

from classifire.draft_system_match_ui import router
from classifire.models import User
from scripts.draft_system_match_demo_fixture import seed_demo_library

scope_app = _scope_app
scope_password_hash = _scope_password_hash


@pytest.fixture
def size_app(scope_app, tmp_path, monkeypatch):
    storage = (tmp_path / "size-library").resolve()
    with scope_app.factory() as db:
        actor = db.get(User, scope_app.users["admin"])
        release = seed_demo_library(db, storage, actor, service_size=True)
        release_id = release.id
        db.commit()
    scope_app.app.include_router(router)
    for module in ("draft_scope_ui", "draft_system_match_ui"):
        monkeypatch.setattr(
            f"classifire.{module}.get_settings",
            lambda: SimpleNamespace(storage_root=storage),
        )
    return CandidateApplication(scope_app, storage, release_id)


def test_size_ui_preserves_claims_history_and_explicit_report(size_app):
    with TestClient(size_app.scope.app) as client:
        _login(client)
        scope = _prepare(client)
        detail = _find(client, scope, size_app.release_id)
        original = client.get(detail + "/download").content
        candidate = client.get(detail + "/download").json()["candidates"][0]["candidate_id"]
        page = client.get(detail)
        assert "Smallest measured service size (mm)" in page.text
        assert "What do the selected source size limits describe?" in page.text
        form = {
            "csrf_token": _csrf(page.text),
            "expected_revision": "1",
            "candidate_id": candidate,
            "substrate_thickness_mm": "100",
            "annular_gap_min_mm": "10",
            "annular_gap_max_mm": "30",
            "service_size_min_mm": "10",
            "service_size_max_mm": "90",
            "service_size_basis": "outside_diameter",
            "source_size_basis": "outside_diameter",
            "measurement_note": "<script>alert(1)</script> Page 1, observed outside diameters.",
        }
        assert (
            client.post(detail + "/constraints", data={**form, "csrf_token": "invalid"}).status_code
            == 403
        )
        partial = dict(form)
        del partial["source_size_basis"]
        assert client.post(detail + "/constraints", data=partial).status_code == 422
        invalid = client.post(detail + "/constraints", data={**form, "service_size_min_mm": "91"})
        assert invalid.status_code == 422
        assert 'value="91"' in invalid.text
        assert "<script>alert(1)</script>" not in invalid.text
        assert client.get(detail + "/download").content == original
        assert (
            client.post(detail + "/constraints", data=form, follow_redirects=False).status_code
            == 303
        )
        saved_bytes = client.get(detail + "/download").content
        saved = client.get(detail + "/download").json()
        assert saved["schema_version"] == "CLASSIFIRE-DRAFT-SYSTEM-MATCH-v3"
        assert [c["status"] for c in saved["constraint_review"]["checks"]] == ["within_limits"] * 3
        page = client.get(detail)
        assert "<script>alert(1)</script>" not in page.text
        assert "&lt;script&gt;" in page.text
        preview = client.get(detail + "/reports?revision=2")
        assert preview.status_code == 200
        assert "Measured service sizes (mm)" in preview.text
        response = client.post(
            detail + "/reports",
            data={
                "csrf_token": _csrf(preview.text),
                "match_revision": "2",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303, response.text
        report = response.headers["location"]
        pdf = client.get(report + "/download?format=pdf").content
        assert pdf.startswith(b"%PDF-")
        form.update(expected_revision="2", service_size_max_mm="90.0001")
        assert (
            client.post(detail + "/constraints", data=form, follow_redirects=False).status_code
            == 303
        )
        assert (
            client.get(detail + "/download").json()["constraint_review"]["checks"][2]["status"]
            == "outside_limits"
        )
        form.update(expected_revision="3", source_size_basis="nominal_diameter")
        assert (
            client.post(detail + "/constraints", data=form, follow_redirects=False).status_code
            == 303
        )
        assert (
            client.get(detail + "/download").json()["constraint_review"]["checks"][2]["status"]
            == "unresolved"
        )
        assert client.get(detail + "/download?revision=2").content == saved_bytes
        assert client.get(report + "/download?format=pdf").content == pdf
        assert "Out of date:" in client.get(report).text
        _assert_no_canonical_scope(size_app.scope.factory)
        with size_app.scope.factory() as db:
            actor = db.get(User, size_app.scope.users["owner"])
            actor.role = "project_manager"
            db.commit()
        form["expected_revision"] = "4"
        assert client.post(detail + "/constraints", data=form).status_code == 403


def test_size_fixture_restart_refuses_other_fixture_adoption(size_app):
    with size_app.scope.factory() as db:
        actor = db.get(User, size_app.scope.users["admin"])
        assert (
            seed_demo_library(db, size_app.storage, actor, service_size=True).id
            == size_app.release_id
        )
        with pytest.raises(ValueError, match="non-fixture"):
            seed_demo_library(db, size_app.storage, actor, constraints=True)
