from __future__ import annotations

import base64
import hashlib
import html
import json
import re
from typing import Any
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from httpx import Response
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
from test_draft_scope_ui import (
    scope_app as _scope_app,
)
from test_draft_scope_ui import (
    scope_password_hash as _scope_password_hash,
)

from classifire.models import AuditEvent, DraftScope, DraftScopeRevision, Project, User

scope_app = _scope_app
scope_password_hash = _scope_password_hash


def _bytes(envelope: dict[str, Any]) -> bytes:
    return json.dumps(
        envelope, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _rehash(envelope: dict[str, Any]) -> bytes:
    envelope.pop("sha256", None)
    envelope["sha256"] = hashlib.sha256(_bytes(envelope)).hexdigest()
    return _bytes(envelope)


def _hidden(page: str, name: str) -> str:
    fields = re.findall(rf'name="{name}"[^>]*value="([^"]*)"', page)
    assert fields, f"The rendered form must carry {name}"
    return html.unescape(fields[-1])


def _source(client: TestClient) -> tuple[str, bytes]:
    source_path = _create(client, "IMPORT-SOURCE")
    assert _edit(client, source_path, _payload()).status_code == 303
    response = client.get(f"{source_path}/download?revision=2")
    assert response.status_code == 200
    return source_path, response.content


def _preview(client: TestClient, path: str, artifact: bytes) -> Response:
    page = client.get(f"{path}/import")
    assert page.status_code == 200
    return client.post(
        f"{path}/import/preview",
        data={
            "csrf_token": _csrf(page.text),
            "artifact_b64": base64.b64encode(artifact).decode("ascii"),
        },
        follow_redirects=False,
    )


def _confirm(
    client: TestClient,
    path: str,
    preview: Response,
    *,
    overrides: dict[str, str] | None = None,
) -> Response:
    form = {
        "csrf_token": _csrf(preview.text),
        "artifact_b64": _hidden(preview.text, "artifact_b64"),
        "preview_token": _hidden(preview.text, "preview_token"),
        "confirm": "replace",
    }
    form.update(overrides or {})
    return client.post(f"{path}/import/confirm", data=form, follow_redirects=False)


def _state(scope_app: ScopeApplication) -> tuple[int | None, ...]:
    with scope_app.factory() as db:
        return tuple(
            db.scalar(select(func.count()).select_from(model))
            for model in (Project, DraftScope, DraftScopeRevision, AuditEvent)
        )


def test_import_preview_confirm_and_manual_edit_preserve_local_authority_and_history(
    scope_app: ScopeApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_downstream(*args: object, **kwargs: object) -> None:
        pytest.fail("Importing a Draft must not invoke downstream or AI workflows")

    for target in (
        "classifire.services.technical.search_for_opening",
        "classifire.services.calculation.recalculate_estimate",
        "classifire.services.snapshot.build_estimate_snapshot",
        "classifire.services.snapshot.lock_snapshot",
        "classifire.services.initial_canonicalisation_boundary.require_admission_bound_initial_canonicalisation",
        "classifire.services.phase8_openresponses_transport.Phase8OpenResponsesTransport.invoke",
    ):
        monkeypatch.setattr(target, forbidden_downstream)
    with TestClient(scope_app.app) as client:
        _login(client)
        source_path, source = _source(client)
        foreign = json.loads(source)
        foreign["artifact_id"] = _uid(700)
        foreign["project_id"] = _uid(701)
        foreign["created_by"] = _uid(702)
        artifact = b" \n" + _rehash(foreign) + b"\n"
        target_path = _create(client, "IMPORT-TARGET")
        original = client.get(f"{target_path}/download?revision=1")
        before = _state(scope_app)
        preview = _preview(client, target_path, artifact)
        assert preview.status_code == 200, preview.text
        assert "Draft" in preview.text
        assert "Insulation and fire rating require evidence" in preview.text
        assert _state(scope_app) == before
        confirmed = _confirm(client, target_path, preview)
        assert confirmed.status_code == 303, confirmed.text
        assert confirmed.headers["location"] == target_path
        imported_response = client.get(f"{target_path}/download?revision=2")
        imported = imported_response.json()
        assert imported["schema_version"] == "CLASSIFIRE-DRAFT-SCOPE-v2"
        assert imported["provenance"] == "imported"
        assert imported["state"] == "Draft"
        assert imported["review_status"] == "unreviewed"
        assert imported["artifact_id"] == target_path.rsplit("/", 1)[1]
        assert imported["project_id"] == original.json()["project_id"]
        assert imported["created_by"] == scope_app.users["owner"]
        assert imported["parent_hash"] == original.json()["sha256"]
        assert imported["content"] == foreign["content"]
        lineage = imported["import_lineage"]
        assert len(lineage) == 1
        assert lineage[0]["artifact_id"] == foreign["artifact_id"]
        assert lineage[0]["project_id"] == foreign["project_id"]
        assert lineage[0]["created_by"] == foreign["created_by"]
        assert lineage[0]["file_sha256"] == hashlib.sha256(artifact).hexdigest()
        assert lineage[0]["sha256"] == foreign["sha256"]
        assert client.get(f"{target_path}/download?revision=1").content == original.content
        assert client.get(f"{source_path}/download?revision=2").content == source
        edited_payload = imported["content"]
        edited_payload["assumptions"].append("Manual adjustment after imported review")
        assert _edit(client, target_path, edited_payload, revision=2).status_code == 303
        edited = client.get(f"{target_path}/download?revision=3").json()
        assert edited["schema_version"] == "CLASSIFIRE-DRAFT-SCOPE-v2"
        assert edited["provenance"] == "manual_edit"
        assert edited["import_lineage"] == lineage
        assert edited["parent_hash"] == imported["sha256"]
        assert client.get(f"{target_path}/download?revision=2").content == imported_response.content
    _assert_no_canonical_scope(scope_app.factory)


def test_import_confirmation_requires_explicit_replace_and_preview_token(
    scope_app: ScopeApplication,
) -> None:
    with TestClient(scope_app.app) as client:
        _login(client)
        _, artifact = _source(client)
        path = _create(client, "IMPORT-TARGET")
        preview = _preview(client, path, artifact)
        assert preview.status_code == 200
        before = _state(scope_app)
        missing_confirmation = _confirm(client, path, preview, overrides={"confirm": ""})
        assert missing_confirmation.status_code == 422
        missing_token = _confirm(client, path, preview, overrides={"preview_token": ""})
        assert missing_token.status_code == 422
        assert _state(scope_app) == before


@pytest.mark.parametrize("mismatch", ["token", "file", "target", "stale", "replay"])
def test_import_confirmation_is_bound_to_preview_and_current_target(
    scope_app: ScopeApplication,
    mismatch: str,
) -> None:
    with TestClient(scope_app.app) as client:
        _login(client)
        _, artifact = _source(client)
        path = _create(client, "IMPORT-TARGET")
        preview = _preview(client, path, artifact)
        assert preview.status_code == 200
        overrides: dict[str, str] = {}
        if mismatch == "token":
            overrides["preview_token"] = _hidden(preview.text, "preview_token") + "forged"
        elif mismatch == "file":
            changed = json.loads(artifact)
            changed["content"]["assumptions"].append("Changed after preview")
            overrides["artifact_b64"] = base64.b64encode(_rehash(changed)).decode("ascii")
        elif mismatch == "target":
            path = _create(client, "IMPORT-OTHER-TARGET")
        elif mismatch == "stale":
            assert _edit(client, path, {"assumptions": ["Newer saved edit"]}).status_code == 303
        elif mismatch == "replay":
            assert _confirm(client, path, preview).status_code == 303
        before = _state(scope_app)
        refused = _confirm(client, path, preview, overrides=overrides)
        assert refused.status_code == (409 if mismatch in {"stale", "replay"} else 422)
        assert _state(scope_app) == before


@pytest.mark.parametrize("invalid", ["hash", "schema", "authority", "duplicate-json", "nonfinite"])
def test_invalid_import_is_refused_without_preview_or_writes(
    scope_app: ScopeApplication,
    invalid: str,
) -> None:
    with TestClient(scope_app.app) as client:
        _login(client)
        _, artifact = _source(client)
        path = _create(client, "IMPORT-TARGET")
        envelope = json.loads(artifact)
        if invalid == "hash":
            envelope["sha256"] = "0" * 64
            artifact = _bytes(envelope)
        elif invalid == "schema":
            envelope["schema_version"] = "CLASSIFIRE-DRAFT-SCOPE-v999"
            artifact = _rehash(envelope)
        elif invalid == "authority":
            envelope["state"] = "Released"
            envelope["review_status"] = "approved"
            artifact = _rehash(envelope)
        elif invalid == "duplicate-json":
            artifact = artifact[:-1] + b',"state":"Draft"}'
        else:
            artifact = artifact[:-1] + b',"extra":NaN}'
        before = _state(scope_app)
        rejected = _preview(client, path, artifact)
        assert rejected.status_code == 422
        assert 'name="preview_token"' not in rejected.text
        assert _state(scope_app) == before


def test_preview_escapes_imported_text_and_confirmation_preserves_it_as_data(
    scope_app: ScopeApplication,
) -> None:
    hostile = "</script><img src=x onerror=alert(1)>"
    with TestClient(scope_app.app) as client:
        _login(client)
        _, artifact = _source(client)
        envelope = json.loads(artifact)
        envelope["content"]["observations"][0]["text"] = hostile
        path = _create(client, "IMPORT-TARGET")
        preview = _preview(client, path, _rehash(envelope))
        assert preview.status_code == 200
        assert hostile not in preview.text
        assert _confirm(client, path, preview).status_code == 303
        imported = client.get(f"{path}/download?revision=2").json()
        assert imported["content"]["observations"][0]["text"] == hostile


def test_import_routes_preserve_owner_and_active_human_boundaries(
    scope_app: ScopeApplication,
) -> None:
    with TestClient(scope_app.app) as owner:
        _login(owner)
        _, artifact = _source(owner)
        path = _create(owner, "IMPORT-TARGET")
        preview = _preview(owner, path, artifact)
        assert preview.status_code == 200
    before = _state(scope_app)
    with TestClient(scope_app.app) as anonymous:
        assert anonymous.get(f"{path}/import").status_code == 401
    with TestClient(scope_app.app) as other:
        _login(other, "other")
        assert other.get(f"{path}/import").status_code == 404
        csrf = _csrf(other.get("/scopes").text)
        assert (
            other.post(
                f"{path}/import/preview",
                data={
                    "csrf_token": csrf,
                    "artifact_b64": base64.b64encode(artifact).decode("ascii"),
                },
            ).status_code
            == 404
        )
        assert _confirm(other, path, preview, overrides={"csrf_token": csrf}).status_code == 404
    with TestClient(scope_app.app) as reader:
        _login(reader, "reader")
        assert reader.get(f"{path}/import").status_code == 403
        csrf = _csrf(reader.get("/projects").text)
        assert _confirm(reader, path, preview, overrides={"csrf_token": csrf}).status_code == 403
    with TestClient(scope_app.app) as admin:
        _login(admin, "admin")
        assert admin.get(f"{path}/import").status_code == 200
        actor_mismatch = _confirm(
            admin,
            path,
            preview,
            overrides={"csrf_token": _csrf(admin.get(f"{path}/import").text)},
        )
        assert actor_mismatch.status_code == 422
    with TestClient(scope_app.app) as inactive:
        _login(inactive)
        csrf = _csrf(inactive.get(f"{path}/import").text)
        with scope_app.factory() as db:
            user = db.get(User, scope_app.users["owner"])
            assert user is not None
            user.is_active = False
            db.commit()
        refused = _confirm(inactive, path, preview, overrides={"csrf_token": csrf})
        assert refused.status_code == 401
    assert _state(scope_app) == before


def test_import_preview_and_confirmation_require_valid_csrf(scope_app: ScopeApplication) -> None:
    with TestClient(scope_app.app) as client:
        _login(client)
        _, artifact = _source(client)
        path = _create(client, "IMPORT-TARGET")
        preview = _preview(client, path, artifact)
        before = _state(scope_app)
        refused_preview = client.post(
            f"{path}/import/preview",
            data={
                "csrf_token": "forged",
                "artifact_b64": base64.b64encode(artifact).decode("ascii"),
            },
        )
        assert refused_preview.status_code == 403
        assert (
            _confirm(client, path, preview, overrides={"csrf_token": "forged"}).status_code == 403
        )
        assert _state(scope_app) == before


@pytest.mark.parametrize("invalid", ["base64", "duplicate-form", "oversized", "oversized-form"])
def test_import_http_bounds_refuse_unsafe_requests_without_writes(
    scope_app: ScopeApplication,
    invalid: str,
) -> None:
    with TestClient(scope_app.app) as client:
        _login(client)
        path = _create(client, "IMPORT-TARGET")
        page = client.get(f"{path}/import")
        assert page.status_code == 200
        form = {"csrf_token": _csrf(page.text), "artifact_b64": "%%%%"}
        if invalid == "duplicate-form":
            body = urlencode(form) + "&artifact_b64=duplicate"
        elif invalid == "oversized":
            body = urlencode({**form, "artifact_b64": "A" * 800_000})
        elif invalid == "oversized-form":
            body = "x" * 1_200_001
        else:
            body = urlencode(form)
        before = _state(scope_app)
        rejected = client.post(
            f"{path}/import/preview",
            content=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert rejected.status_code == (413 if invalid in {"oversized", "oversized-form"} else 422)
        assert _state(scope_app) == before


@pytest.mark.parametrize("invalid", ["expired", "new-session"])
def test_import_confirmation_expires_and_cannot_cross_human_sessions(
    scope_app: ScopeApplication,
    monkeypatch: pytest.MonkeyPatch,
    invalid: str,
) -> None:
    with TestClient(scope_app.app) as client:
        _login(client)
        _, artifact = _source(client)
        path = _create(client, "IMPORT-TARGET")
        preview = _preview(client, path, artifact)
        assert preview.status_code == 200
        overrides: dict[str, str] = {}
        if invalid == "expired":
            monkeypatch.setattr("classifire.draft_scope_ui.IMPORT_PREVIEW_MAX_AGE", -1)
        else:
            logged_out = client.post(
                "/logout",
                data={"csrf_token": _csrf(preview.text)},
                follow_redirects=False,
            )
            assert logged_out.status_code == 303
            _login(client)
            overrides["csrf_token"] = _csrf(client.get(f"{path}/import").text)
        before = _state(scope_app)
        refused = _confirm(client, path, preview, overrides=overrides)
        assert refused.status_code == 422
        assert _state(scope_app) == before
