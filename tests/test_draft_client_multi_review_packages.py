from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_client import (  # noqa: F401
    client_case,
    confirm,
    scope_app,
    scope_password_hash,
    tool,
)
from test_draft_client_capabilities import capability_case as _capability_case
from test_draft_scope import uid
from test_draft_scope_ui import _assert_no_canonical_scope, _csrf, _login

from classifire.draft_client_auth import EXPORT, READ, TECHNICAL, WRITE
from classifire.models import DraftClientRequest, DraftProjectPackage, User
from classifire.services import draft_client_capabilities as capabilities
from classifire.services import draft_project_packages as packages
from classifire.services import draft_scope as scopes
from classifire.services import draft_system_matches as matches

capability_case = _capability_case


@pytest.fixture
def multi_review_case(capability_case):
    case = capability_case
    with case.scope.factory() as db:
        actor = db.get(User, case.scope.users["owner"])
        assert scopes._actor(db, actor, "technical:read") == actor
        rows = [
            matches.create_match(
                db,
                actor,
                case.draft_id,
                2,
                case.release_id,
                uid(2),
                service_id,
                storage_root=capabilities.get_settings().storage_root,
            )
            for service_id in (uid(5), uid(6))
        ]
        case.selection = {
            "scope_revision": 2,
            "matches": [{"match_id": row.id, "match_revision": 1} for row in rows],
        }
        db.commit()
    return case


def _state(case):
    with case.scope.factory() as db:
        return tuple(
            db.scalar(select(func.count()).select_from(model))
            for model in (DraftClientRequest, DraftProjectPackage)
        )


def _saved_package(case):
    with case.scope.factory() as db:
        actor = db.get(User, case.scope.users["owner"])
        preview = packages.preview(db, actor, case.draft_id, case.selection)
        row = packages.create_package(
            db, actor, case.draft_id, case.selection, 0, preview["preview_hash"]
        )
        db.commit()
        return row.id


@pytest.mark.parametrize("entrypoint", ["proposal", "download-link", "download-bytes"])
def test_scope_export_grant_cannot_disclose_multi_review_package(multi_review_case, entrypoint):
    case = multi_review_case
    package_id = None if entrypoint == "proposal" else _saved_package(case)
    before = _state(case)
    limited = case.token(scope=" ".join([READ, WRITE, EXPORT]))
    with TestClient(case.scope.app, base_url="https://testserver") as client:
        if entrypoint == "proposal":
            response = tool(
                client,
                limited,
                "propose_project_package",
                {"draft_id": case.draft_id, "selection": case.selection},
                error=True,
            )
            assert "CLIENT_AUTHORIZATION_REQUIRED" in str(response)
        elif entrypoint == "download-link":
            response = tool(
                client,
                limited,
                "project_package_download",
                {"draft_id": case.draft_id, "package_id": package_id},
                error=True,
            )
            assert "CLIENT_AUTHORIZATION_REQUIRED" in str(response)
        else:
            response = client.get(
                f"/api/draft-client/{case.draft_id}/packages/{package_id}",
                headers={"Authorization": "Bearer " + limited},
            )
            assert response.status_code == 403
            assert response.json() == {"detail": "CLIENT_AUTHORIZATION_REQUIRED"}
        assert _state(case) == before
    _assert_no_canonical_scope(case.scope.factory)


def test_technical_export_grant_still_needs_separate_browser_confirmation(multi_review_case):
    case = multi_review_case
    token = case.token(scope=" ".join([READ, WRITE, EXPORT, TECHNICAL]))
    with TestClient(case.scope.app, base_url="https://testserver") as client:
        pending = tool(
            client,
            token,
            "propose_project_package",
            {"draft_id": case.draft_id, "selection": case.selection},
        )
        assert pending["status"] == "pending" and pending["result"] is None
        assert _state(case) == (1, 0)
        assert (
            client.post(
                pending["review_url"],
                data={"decision": "confirm"},
                headers={"Authorization": "Bearer " + token},
            ).status_code
            == 401
        )
        assert _state(case) == (1, 0)
        _login(client)
        assert client.get(pending["review_url"]).status_code == 200
        assert _state(case) == (1, 0)
        confirm(client, pending)
        saved = tool(client, token, "read_client_request", {"request_id": pending["request_id"]})
        assert saved["status"] == "confirmed"
        assert _state(case) == (1, 1)
        info = tool(
            client,
            token,
            "project_package_download",
            {"draft_id": case.draft_id, "package_id": saved["result"]["package_id"]},
        )
        downloaded = client.get(
            info["authenticated_url"], headers={"Authorization": "Bearer " + token}
        )
        assert downloaded.status_code == 200
        assert packages.digest(downloaded.content) == info["sha256"]
        manifest, members = packages.inspect_archive(downloaded.content)
        assert manifest["schema_version"] == packages.SCHEMA_V6
        assert len(manifest["selection"]["matches"]) == 2
        assert manifest["selection"]["match_id"] is None
        assert len(members) == 3
        assert downloaded.headers["cache-control"] == "no-store"
    _assert_no_canonical_scope(case.scope.factory)


def test_removed_technical_grant_blocks_pending_collection_confirmation(multi_review_case):
    case = multi_review_case
    token = case.token(scope=" ".join([READ, WRITE, EXPORT, TECHNICAL]))
    with TestClient(case.scope.app, base_url="https://testserver") as client:
        _login(client)
        pending = tool(
            client,
            token,
            "propose_project_package",
            {"draft_id": case.draft_id, "selection": case.selection},
        )
        page = client.get(pending["review_url"])
        assert page.status_code == 200
        digest = re.search(r'name="payload_hash" value="([^"]+)"', page.text).group(1)
        body = {"decision": "confirm", "payload_hash": digest, "csrf_token": _csrf(page.text)}
        case.policy["clients"]["synthetic-client"].remove(TECHNICAL)
        case.path.write_text(json.dumps(case.policy), encoding="utf-8")
        assert client.get(pending["review_url"]).status_code == 403
        response = client.post(pending["review_url"], data=body)
        assert response.status_code == 403
        assert "CLIENT_AUTHORIZATION_REQUIRED" in response.text
        assert _state(case) == (1, 0)
        with case.scope.factory() as db:
            assert db.get(DraftClientRequest, pending["request_id"]).status == "pending"
