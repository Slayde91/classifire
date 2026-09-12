from __future__ import annotations

import hashlib
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
from test_draft_client_capabilities import capability_case  # noqa: F401
from test_draft_client_multi_review_packages import multi_review_case as _multi_review_case
from test_draft_estimates import add_payload
from test_draft_scope import uid
from test_draft_scope_ui import _assert_no_canonical_scope, _csrf, _login

from classifire.draft_client_auth import ESTIMATE, EXPORT, READ, TECHNICAL, WRITE
from classifire.models import DraftClientRequest, DraftEstimateReport, User
from classifire.services import draft_client_capabilities as caps
from classifire.services import draft_estimate_reports as reports
from classifire.services import draft_estimates as estimates
from classifire.services import draft_system_matches as matches
from classifire.services.draft_scope import DraftScopeError

multi_review_case = _multi_review_case


def prepared(case, *, attached=False):
    with case.scope.factory() as db:
        actor = db.get(User, case.scope.users["owner"])
        bound = case.selection["matches"][0] if attached else {}
        parent = estimates.create_estimate(db, actor, case.draft_id, 2, **bound)
        envelope = estimates.add_line(db, actor, case.draft_id, parent.id, 1, add_payload())
        db.commit()
        case.estimate_id = parent.id
        case.estimate_envelope = envelope
    return case


def operation(case, **changes):
    return {
        "action": "estimate_report",
        "draft_id": case.draft_id,
        "estimate_id": case.estimate_id,
        "estimate_revision": 2,
        "profile": "complete",
        "matches": case.selection["matches"],
        **changes,
    }


def state(case):
    with case.scope.factory() as db:
        return tuple(
            db.scalar(select(func.count()).select_from(model))
            for model in (DraftClientRequest, DraftEstimateReport)
        )


@pytest.mark.parametrize(
    "bad",
    [
        {"profile": "estimate-only"},
        {"matches": [{"match_id": uid(8), "match_revision": 1}] * 2},
        {"matches": [{"match_id": uid(8), "match_revision": True}]},
    ],
)
def test_invalid_complete_client_selection_fails(bad):
    raw = {
        "action": "estimate_report",
        "draft_id": uid(1),
        "estimate_id": uid(2),
        "estimate_revision": 1,
        "profile": "complete",
        "matches": [{"match_id": uid(8), "match_revision": 1}],
        **bad,
    }
    with pytest.raises(DraftScopeError, match="CLIENT_CAPABILITY_INPUT_INVALID"):
        caps.parse(raw)


@pytest.mark.parametrize("profile", ["estimate-only", "complete"])
def test_legacy_complete_commands_keep_pending_serialization_and_hash(multi_review_case, profile):
    case = prepared(multi_review_case)
    raw = operation(case, profile=profile)
    del raw["matches"]
    for value in (raw, {**raw, "matches": []}):
        parsed = caps.parse(value)
        assert parsed.model_dump(mode="json") == raw
        with case.scope.factory() as db:
            actor = db.get(User, case.scope.users["owner"])
            inputs = caps.inspect_inputs(
                db, case.authority, case.authority.verify(case.full_token()), actor, parsed
            )
            assert set(inputs["inputs"]) == {"scope", "match", "estimate", "release", "project"}
            assert (
                inputs["input_hash"]
                == hashlib.sha256(
                    json.dumps(
                        inputs["inputs"], sort_keys=True, separators=(",", ":"), ensure_ascii=True
                    ).encode()
                ).hexdigest()
            )


@pytest.mark.parametrize("attached", [False, True])
def test_complete_collection_requires_separate_confirmation_and_preserves_estimate(
    multi_review_case, attached
):
    case = prepared(multi_review_case, attached=attached)
    with TestClient(case.scope.app, base_url="https://testserver") as client:
        limited = case.token(scope=" ".join([READ, WRITE, EXPORT, ESTIMATE]))
        denied = tool(
            client, limited, "propose_capability", {"operation": operation(case)}, error=True
        )
        assert "CLIENT_AUTHORIZATION_REQUIRED" in str(denied) and state(case) == (0, 0)
        pending = tool(
            client, case.full_token(), "propose_capability", {"operation": operation(case)}
        )
        assert pending["status"] == "pending" and state(case) == (1, 0)
        assert (
            client.post(
                pending["review_url"],
                data={"decision": "confirm"},
                headers={"Authorization": "Bearer " + case.full_token()},
            ).status_code
            == 401
        )
        _login(client)
        page = client.get(pending["review_url"])
        assert page.status_code == 200
        assert "Additional report context only" in page.text
        if attached:
            assert "This exact review is attached to the saved Estimate" in page.text
        ids = re.findall(r'\bid="([^"]+)"', page.text)
        assert len(ids) == len(set(ids))
        first = case.selection["matches"][0]["match_id"]
        with case.scope.factory() as db:
            actor = db.get(User, case.scope.users["owner"])
            old = matches.read_match_revision(db, actor, case.draft_id, first, 1)
            matches.save_review(db, actor, case.draft_id, first, 1, old["decisions"])
            db.commit()
        confirm(client, pending)
        saved = tool(
            client, case.full_token(), "read_client_request", {"request_id": pending["request_id"]}
        )
        assert saved["status"] == "confirmed" and state(case) == (1, 1)
        report_id = saved["result"]["report_id"]
        view = tool(
            client,
            case.full_token(),
            "read_capability_artifact",
            {
                "draft_id": case.draft_id,
                "kind": "estimate-report",
                "estimate_id": case.estimate_id,
                "artifact_id": report_id,
            },
        )
        snapshot = view["artifact"]
        assert snapshot["schema_version"] == "CLASSIFIRE-DRAFT-ESTIMATE-REPORT-v3"
        assert snapshot["estimate"] == case.estimate_envelope and view["staleness"]
        assert {r["artifact_id"]: r["revision"] for r in snapshot["system_matches"]} == {
            r["match_id"]: 1 for r in case.selection["matches"]
        }
        for fmt in ("pdf", "xlsx"):
            info = tool(
                client,
                case.full_token(),
                "report_download",
                {
                    "draft_id": case.draft_id,
                    "estimate_id": case.estimate_id,
                    "report_id": report_id,
                    "format_name": fmt,
                },
            )
            download = client.get(
                info["authenticated_url"], headers={"Authorization": "Bearer " + case.full_token()}
            )
            assert (
                download.status_code == 200
                and hashlib.sha256(download.content).hexdigest() == info["sha256"]
            )
            assert client.get(info["browser_url"]).content == download.content
        with case.scope.factory() as db:
            assert (
                estimates.read_estimate_revision(
                    db, db.get(User, case.scope.users["owner"]), case.draft_id, case.estimate_id
                )
                == case.estimate_envelope
            )
    _assert_no_canonical_scope(case.scope.factory)


@pytest.mark.parametrize("entrypoint", ["list", "read", "download-link", "pdf", "xlsx"])
def test_limited_client_cannot_read_additional_complete_reviews(multi_review_case, entrypoint):
    case = prepared(multi_review_case)
    with case.scope.factory() as db:
        row = reports.create_report(
            db,
            db.get(User, case.scope.users["owner"]),
            case.draft_id,
            case.estimate_id,
            2,
            profile="complete",
            matches=case.selection["matches"],
        )
        db.commit()
        report_id = row.id
    limited = case.token(scope=" ".join([READ, WRITE, EXPORT, ESTIMATE]))
    before = state(case)
    with TestClient(case.scope.app, base_url="https://testserver") as client:
        if entrypoint == "list":
            result = tool(
                client,
                limited,
                "list_capability_artifacts",
                {
                    "draft_id": case.draft_id,
                    "estimate_id": case.estimate_id,
                    "kind": "estimate-report",
                },
            )
            assert result["artifacts"] == []
        elif entrypoint == "read":
            result = tool(
                client,
                limited,
                "read_capability_artifact",
                {
                    "draft_id": case.draft_id,
                    "estimate_id": case.estimate_id,
                    "kind": "estimate-report",
                    "artifact_id": report_id,
                },
                error=True,
            )
            assert "CLIENT_AUTHORIZATION_REQUIRED" in str(result)
        else:
            args = {
                "draft_id": case.draft_id,
                "estimate_id": case.estimate_id,
                "report_id": report_id,
                "format_name": entrypoint if entrypoint in ("pdf", "xlsx") else "pdf",
            }
            if entrypoint == "download-link":
                assert "CLIENT_AUTHORIZATION_REQUIRED" in str(
                    tool(client, limited, "report_download", args, error=True)
                )
            else:
                info = tool(client, case.full_token(), "report_download", args)
                response = client.get(
                    info["authenticated_url"], headers={"Authorization": "Bearer " + limited}
                )
                assert response.status_code == 403 and response.json() == {
                    "detail": "CLIENT_AUTHORIZATION_REQUIRED"
                }
    assert state(case) == before


def test_revoked_grant_blocks_pending_complete_report(multi_review_case):
    case = prepared(multi_review_case)
    with TestClient(case.scope.app, base_url="https://testserver") as client:
        _login(client)
        pending = tool(
            client, case.full_token(), "propose_capability", {"operation": operation(case)}
        )
        page = client.get(pending["review_url"])
        assert page.status_code == 200
        payload = re.search(r'name="payload_hash" value="([^"]+)"', page.text).group(1)
        body = {"decision": "confirm", "payload_hash": payload, "csrf_token": _csrf(page.text)}
        case.policy["clients"]["synthetic-client"].remove(TECHNICAL)
        case.path.write_text(json.dumps(case.policy), encoding="utf-8")
        assert client.get(pending["review_url"]).status_code == 403
        assert client.post(pending["review_url"], data=body).status_code == 403
        assert state(case) == (1, 0)
