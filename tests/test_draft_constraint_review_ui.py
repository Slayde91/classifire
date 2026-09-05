from fastapi.testclient import TestClient
from test_draft_scope_ui import _csrf, _login
from test_draft_system_match_ui import _find, _prepare
from test_draft_system_match_ui import candidate_app as _candidate_app
from test_draft_system_match_ui import scope_app as _scope_app
from test_draft_system_match_ui import scope_password_hash as _scope_password_hash

candidate_app = _candidate_app
scope_app = _scope_app
scope_password_hash = _scope_password_hash


def test_measurement_ui_csrf_validation_history_and_unknown_limits(candidate_app):
    with TestClient(candidate_app.scope.app) as client:
        _login(client)
        scope = _prepare(client)
        detail = _find(client, scope, candidate_app.release_id)
        original = client.get(detail + "/download?revision=1").content
        envelope = client.get(detail + "/download").json()
        page = client.get(detail)
        assert "Check measured limits" in page.text
        form = {
            "csrf_token": _csrf(page.text),
            "expected_revision": "1",
            "candidate_id": envelope["candidates"][0]["candidate_id"],
            "substrate_thickness_mm": "100",
            "annular_gap_min_mm": "10",
            "annular_gap_max_mm": "30",
            "measurement_note": "Synthetic page 1 measurements",
        }
        assert (
            client.post(detail + "/constraints", data={**form, "csrf_token": "bad"}).status_code
            == 403
        )
        invalid = client.post(detail + "/constraints", data={**form, "annular_gap_min_mm": "31"})
        assert invalid.status_code == 422
        assert "Synthetic page 1 measurements" in invalid.text
        assert client.get(detail + "/download").json()["revision"] == 1
        response = client.post(detail + "/constraints", data=form, follow_redirects=False)
        assert response.status_code == 303
        saved = client.get(detail + "/download").json()
        assert saved["revision"] == 2
        assert saved["constraint_review"]["status"] == "partial_unapproved"
        assert all(
            check["status"] == "unresolved" for check in saved["constraint_review"]["checks"]
        )
        assert client.get(detail + "/download?revision=1").content == original
        stale = client.post(detail + "/constraints", data=form)
        assert stale.status_code == 409
        assert client.get(detail + "/download").json()["revision"] == 2
        assert 'action="' + detail + '/constraints"' not in client.get(detail + "?revision=1").text
