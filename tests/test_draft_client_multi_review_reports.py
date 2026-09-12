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
from test_draft_scope import uid
from test_draft_scope_ui import _assert_no_canonical_scope, _csrf, _login

from classifire.draft_client_auth import EXPORT, READ, TECHNICAL, WRITE
from classifire.models import (
    DraftClientRequest,
    DraftEstimate,
    DraftScopeReport,
    DraftSystemMatch,
    User,
)
from classifire.services import draft_client_capabilities as caps
from classifire.services import draft_scope_reports as reports
from classifire.services import draft_system_matches as matches

multi_review_case = _multi_review_case


def _operation(case):
    return {"action": "scope_report", "draft_id": case.draft_id, **case.selection}


def _state(case):
    with case.scope.factory() as db:
        return tuple(
            db.scalar(select(func.count()).select_from(model))
            for model in (
                DraftClientRequest,
                DraftScopeReport,
                DraftSystemMatch,
                DraftEstimate,
            )
        )


def _report(case):
    with case.scope.factory() as db:
        row = reports.create_report(
            db,
            db.get(User, case.scope.users["owner"]),
            case.draft_id,
            2,
            matches=case.selection["matches"],
        )
        db.commit()
        return row.id


def test_legacy_report_commands_keep_serialized_shape_and_input_hash(multi_review_case):
    case = multi_review_case
    operation = {
        "action": "scope_report",
        "draft_id": case.draft_id,
        "scope_revision": 2,
        "match_id": None,
        "match_revision": None,
    }
    for raw in (operation, {**operation, "matches": []}):
        parsed = caps.parse(raw)
        assert parsed.model_dump(mode="json") == operation
        with case.scope.factory() as db:
            identity = case.authority.verify(case.full_token())
            inspected = caps.inspect_inputs(
                db, case.authority, identity, db.get(User, case.scope.users["owner"]), parsed
            )
            assert set(inspected["inputs"]) == {"scope", "match", "estimate", "release", "project"}
            legacy_json = json.dumps(
                inspected["inputs"], sort_keys=True, separators=(",", ":"), ensure_ascii=True
            )
            assert inspected["input_hash"] == hashlib.sha256(legacy_json.encode()).hexdigest()


@pytest.mark.parametrize(
    "bad",
    [
        {"matches": [{"match_id": uid(8), "match_revision": 1}] * 2},
        {
            "matches": [{"match_id": uid(8), "match_revision": 1}],
            "match_id": uid(8),
            "match_revision": 1,
        },
        {"matches": [{"match_id": uid(8), "match_revision": True}]},
    ],
)
def test_invalid_client_review_selection_is_refused(bad):
    from classifire.services.draft_scope import DraftScopeError

    with pytest.raises(DraftScopeError, match="CLIENT_CAPABILITY_INPUT_INVALID"):
        caps.parse({"action": "scope_report", "draft_id": uid(1), "scope_revision": 2, **bad})


def test_report_proposal_needs_grant_and_separate_confirmation_of_all_exact_reviews(
    multi_review_case,
):
    case = multi_review_case
    with TestClient(case.scope.app, base_url="https://testserver") as client:
        before = _state(case)
        limited = case.token(scope=" ".join([READ, WRITE, EXPORT]))
        rejected = tool(
            client, limited, "propose_capability", {"operation": _operation(case)}, error=True
        )
        assert "CLIENT_AUTHORIZATION_REQUIRED" in str(rejected)
        assert _state(case) == before
        pending = tool(
            client, case.full_token(), "propose_capability", {"operation": _operation(case)}
        )
        assert pending["status"] == "pending" and _state(case) == (1, 0, 2, 0)
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
        assert "Selected saved system reviews" in page.text
        for ref in case.selection["matches"]:
            assert ref["match_id"] in page.text
        identifiers = re.findall(r'\bid="([^"]+)"', page.text)
        assert len(identifiers) == len(set(identifiers)), "Repeated reviews need distinct HTML IDs"
        assert _state(case) == (1, 0, 2, 0)
        # A later revision must not replace the explicitly requested historical input.
        first = case.selection["matches"][0]["match_id"]
        with case.scope.factory() as db:
            actor = db.get(User, case.scope.users["owner"])
            old = matches.read_match_revision(db, actor, case.draft_id, first, 1)
            matches.save_review(db, actor, case.draft_id, first, 1, old["decisions"])
            db.commit()
        confirm(client, pending)
        result = tool(
            client, case.full_token(), "read_client_request", {"request_id": pending["request_id"]}
        )
        assert result["status"] == "confirmed" and _state(case) == (1, 1, 2, 0)
        saved = tool(
            client,
            case.full_token(),
            "read_capability_artifact",
            {
                "draft_id": case.draft_id,
                "kind": "scope-report",
                "artifact_id": result["result"]["report_id"],
            },
        )
        assert saved["artifact"]["schema_version"] == "CLASSIFIRE-DRAFT-SCOPE-REPORT-v3"
        assert {r["artifact_id"]: r["revision"] for r in saved["artifact"]["system_matches"]} == {
            ref["match_id"]: 1 for ref in case.selection["matches"]
        }
        assert saved["staleness"]
        for fmt in ("pdf", "xlsx"):
            info = tool(
                client,
                case.full_token(),
                "report_download",
                {
                    "draft_id": case.draft_id,
                    "report_id": result["result"]["report_id"],
                    "format_name": fmt,
                },
            )
            data = client.get(
                info["authenticated_url"], headers={"Authorization": "Bearer " + case.full_token()}
            )
            assert (
                data.status_code == 200
                and hashlib.sha256(data.content).hexdigest() == info["sha256"]
            )
            assert client.get(info["browser_url"]).content == data.content
    _assert_no_canonical_scope(case.scope.factory)


@pytest.mark.parametrize("entrypoint", ["list", "read", "download-link", "pdf", "xlsx"])
def test_limited_client_cannot_disclose_multi_review_report(multi_review_case, entrypoint):
    case = multi_review_case
    report_id = _report(case)
    limited = case.token(scope=" ".join([READ, WRITE, EXPORT]))
    before = _state(case)
    with TestClient(case.scope.app, base_url="https://testserver") as client:
        if entrypoint == "list":
            value = tool(
                client,
                limited,
                "list_capability_artifacts",
                {"draft_id": case.draft_id, "kind": "scope-report"},
            )
            assert value["artifacts"] == []
        elif entrypoint == "read":
            value = tool(
                client,
                limited,
                "read_capability_artifact",
                {"draft_id": case.draft_id, "kind": "scope-report", "artifact_id": report_id},
                error=True,
            )
            assert "CLIENT_AUTHORIZATION_REQUIRED" in str(value)
        else:
            args = {
                "draft_id": case.draft_id,
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
    assert _state(case) == before


def test_revoked_technical_grant_blocks_pending_multi_review_report(multi_review_case):
    case = multi_review_case
    with TestClient(case.scope.app, base_url="https://testserver") as client:
        _login(client)
        pending = tool(
            client, case.full_token(), "propose_capability", {"operation": _operation(case)}
        )
        page = client.get(pending["review_url"])
        assert page.status_code == 200
        payload_hash = re.search(r'name="payload_hash" value="([^"]+)"', page.text).group(1)
        body = {"decision": "confirm", "payload_hash": payload_hash, "csrf_token": _csrf(page.text)}
        case.policy["clients"]["synthetic-client"].remove(TECHNICAL)
        case.path.write_text(json.dumps(case.policy), encoding="utf-8")
        assert client.get(pending["review_url"]).status_code == 403
        assert client.post(pending["review_url"], data=body).status_code == 403
        assert _state(case) == (1, 0, 2, 0)


def test_two_measured_reviews_keep_distinct_confirmation_sections(multi_review_case):
    case = multi_review_case
    with case.scope.factory() as db:
        actor = db.get(User, case.scope.users["owner"])
        for reference in case.selection["matches"]:
            prior = matches.read_match_revision(db, actor, case.draft_id, reference["match_id"], 1)
            assert prior["candidates"]
            saved = matches.save_constraint_review(
                db,
                actor,
                case.draft_id,
                reference["match_id"],
                1,
                prior["candidates"][0]["candidate_id"],
                {
                    "substrate_thickness_mm": None,
                    "annular_gap_min_mm": None,
                    "annular_gap_max_mm": None,
                    "measurement_note": "Synthetic: measurements unavailable",
                },
                storage_root=caps.get_settings().storage_root,
            )
            reference["match_revision"] = saved["revision"]
        db.commit()
    with TestClient(case.scope.app, base_url="https://testserver") as client:
        _login(client)
        pending = tool(
            client, case.full_token(), "propose_capability", {"operation": _operation(case)}
        )
        page = client.get(pending["review_url"])
        assert page.status_code == 200
        assert page.text.count("Check measured limits") == 2
        identifiers = re.findall(r'\bid="([^"]+)"', page.text)
        assert len(identifiers) == len(set(identifiers)), "Measured review headings must be unique"
        assert _state(case) == (1, 0, 2, 0)
