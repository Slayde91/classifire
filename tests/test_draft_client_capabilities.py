from __future__ import annotations

import hashlib
import io
import json
from types import SimpleNamespace

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_client import client_case as _client_case
from test_draft_client import confirm, scope_app, scope_password_hash, tool  # noqa: F401
from test_draft_estimates import add_payload
from test_draft_scope import sample_payload, uid
from test_draft_scope_ui import _assert_no_canonical_scope, _login
from test_technical_release_publication import _bound_variant

from classifire.draft_client_auth import ESTIMATE, EXPORT, READ, TECHNICAL, WRITE
from classifire.models import DraftClientRequest, DraftEstimate, DraftSystemMatch, User
from classifire.services import draft_estimates as estimates
from classifire.services import draft_scope as scopes
from classifire.services.technical_release_publication import publish_governed_technical_release

client_case = _client_case


@pytest.fixture
def capability_case(client_case, tmp_path, monkeypatch):
    c = client_case
    storage = tmp_path / "library"
    c.policy["clients"]["synthetic-client"] = [READ, WRITE, EXPORT, TECHNICAL, ESTIMATE]
    c.path.write_text(json.dumps(c.policy), encoding="utf-8")
    for module in (
        "services.draft_client_capabilities",
        "draft_client_capability_tools",
        "draft_system_match_ui",
        "draft_estimate_ui",
        "draft_scope_ui",
    ):
        monkeypatch.setattr(
            "classifire." + module + ".get_settings", lambda: SimpleNamespace(storage_root=storage)
        )
    with c.scope.factory() as db:
        owner = db.get(User, c.scope.users["owner"])
        draft = scopes.create_draft_project(db, owner, "CLIENT-CAPS", "Synthetic capabilities")
        payload = sample_payload()
        payload["services"][0]["service_type"] = "pipe"
        scopes.save_revision(db, owner, draft.id, 1, payload)
        variant, _ = _bound_variant(db, storage)
        release = publish_governed_technical_release(
            db,
            version="CLIENT-SYNTHETIC",
            notes="Synthetic fixture",
            actor=db.get(User, c.scope.users["admin"]),
            storage_root=storage,
        )
        db.commit()
        c.draft_id, c.release_id, c.variant_id = draft.id, release.id, variant.id
    c.full_token = lambda: c.token(scope=" ".join([READ, WRITE, EXPORT, TECHNICAL, ESTIMATE]))
    return c


def propose(client, c, action, **args):
    return tool(
        client,
        c.full_token(),
        "propose_capability",
        {"operation": {"draft_id": c.draft_id, "action": action, **args}},
    )


def saved(client, c, pending):
    confirm(client, pending)
    return tool(
        client, c.full_token(), "read_client_request", {"request_id": pending["request_id"]}
    )["result"]


def read(client, c, kind, artifact_id, **args):
    return tool(
        client,
        c.full_token(),
        "read_capability_artifact",
        {"draft_id": c.draft_id, "kind": kind, "artifact_id": artifact_id, **args},
    )


def test_independent_capabilities_human_review_and_four_exact_report_profiles(capability_case):
    c = capability_case
    with TestClient(c.scope.app, base_url="https://testserver") as client:
        _login(client)
        # Estimating is independently callable before any match exists.
        pending = propose(client, c, "create_estimate", scope_revision=2)
        with c.scope.factory() as db:
            assert db.scalar(select(func.count()).select_from(DraftEstimate)) == 0
            assert db.scalar(select(func.count()).select_from(DraftSystemMatch)) == 0
        estimate = saved(client, c, pending)["estimate_id"]
        pending = propose(
            client,
            c,
            "add_estimate_line",
            estimate_id=estimate,
            expected_revision=1,
            line=add_payload(),
        )
        assert "Synthetic service-only work" in client.get(pending["review_url"]).text
        saved(client, c, pending)
        content = read(client, c, "estimate", estimate)["artifact"]
        assert content["summary"]["priced_subtotal_ex_tax"] == "2.01"
        line_id = content["lines"][0]["line_id"]
        saved(
            client,
            c,
            propose(
                client,
                c,
                "override_estimate_line",
                estimate_id=estimate,
                expected_revision=2,
                line_id=line_id,
                override={
                    "quantity": "2",
                    "unit_sell_rate": "3.00",
                    "reason": "Synthetic reviewed correction",
                },
            ),
        )
        content = read(client, c, "estimate", estimate)["artifact"]
        assert content["lines"][0]["original_rate"] == "1.005"
        assert len(content["lines"][0]["history"]) == 2
        assert content["summary"]["priced_subtotal_ex_tax"] == "6.00"
        assert content["system_match"] is None
        release = tool(client, c.full_token(), "list_technical_releases")["releases"][0]
        assert release["id"] == c.release_id
        match = saved(
            client,
            c,
            propose(
                client,
                c,
                "create_match",
                scope_revision=2,
                release_id=c.release_id,
                opening_id=uid(2),
                service_id=uid(5),
            ),
        )["match_id"]
        matched = read(client, c, "system-match", match)["artifact"]
        assert matched["candidates"]
        decisions = [
            {
                "candidate_id": candidate["candidate_id"],
                "decision": "keep",
                "notes": "Retain for human assessment; no approval",
            }
            for candidate in matched["candidates"]
        ]
        saved(
            client,
            c,
            propose(
                client, c, "review_match", match_id=match, expected_revision=1, decisions=decisions
            ),
        )
        # Explicit separate report calls never modify the estimate or match.
        profiles = [
            ("scope_report", {"scope_revision": 2}, "scope-only", None),
            (
                "scope_report",
                {"scope_revision": 2, "match_id": match, "match_revision": 2},
                "scope-and-system",
                None,
            ),
            (
                "estimate_report",
                {"estimate_id": estimate, "estimate_revision": 3, "profile": "estimate-only"},
                "estimate-only",
                estimate,
            ),
            (
                "estimate_report",
                {"estimate_id": estimate, "estimate_revision": 3, "profile": "complete"},
                "complete",
                estimate,
            ),
        ]
        downloads = []
        for action, args, profile, parent in profiles:
            report = saved(client, c, propose(client, c, action, **args))["report_id"]
            kind = "estimate-report" if parent else "scope-report"
            snapshot = read(client, c, kind, report, estimate_id=parent)["artifact"]
            assert snapshot["profile"] == profile
            for fmt in ("pdf", "xlsx"):
                info = tool(
                    client,
                    c.full_token(),
                    "report_download",
                    {
                        "draft_id": c.draft_id,
                        "report_id": report,
                        "format_name": fmt,
                        "estimate_id": parent,
                    },
                )
                response = client.get(
                    info["authenticated_url"], headers={"Authorization": "Bearer " + c.full_token()}
                )
                assert response.status_code == 200, response.text
                assert hashlib.sha256(response.content).hexdigest() == info["sha256"]
                browser = client.get(info["browser_url"])
                assert browser.status_code == 200 and browser.content == response.content
                assert client.get(info["authenticated_url"]).status_code == 401
                assert response.headers["cache-control"] == "no-store"
                if fmt == "pdf":
                    assert response.content.startswith(b"%PDF-")
                else:
                    workbook = openpyxl.load_workbook(io.BytesIO(response.content), data_only=False)
                    assert workbook.sheetnames
                    workbook.close()
                downloads.append((info, response.content))
        assert read(client, c, "estimate", estimate)["artifact"]["revision"] == 3
        assert read(client, c, "system-match", match)["artifact"]["revision"] == 2
        with c.scope.factory() as db:
            actor = db.get(User, c.scope.users["owner"])
            scopes.save_revision(db, actor, c.draft_id, 2, sample_payload())
            db.commit()
        assert read(client, c, "scope-report", downloads[0][0]["authenticated_url"].split("/")[-2])[
            "staleness"
        ]
    # Fresh HTTP lifespan reads retained outputs, rather than rerendering.
    from contextlib import asynccontextmanager

    from test_draft_scope_ui import _app

    from classifire.draft_client import configure

    app = _app(c.scope.factory)
    mounted = configure(app, c.authority, c.scope.factory)

    @asynccontextmanager
    async def lifespan(app):
        async with mounted.router.lifespan_context(mounted):
            yield

    app.router.lifespan_context = lifespan
    with TestClient(app, base_url="https://testserver") as restarted:
        for info, expected in downloads:
            assert (
                restarted.get(
                    info["authenticated_url"], headers={"Authorization": "Bearer " + c.full_token()}
                ).content
                == expected
            )
    _assert_no_canonical_scope(c.scope.factory)


def test_capability_scope_owner_revocation_stale_and_domain_rejection(capability_case):
    c = capability_case
    with TestClient(c.scope.app, base_url="https://testserver") as client:
        _login(client)
        args = {
            "operation": {"draft_id": c.draft_id, "action": "create_estimate", "scope_revision": 2}
        }
        assert "CLIENT_AUTHORIZATION_REQUIRED" in str(
            tool(client, c.token(), "propose_capability", args, error=True)
        )
        foreign = c.token(user="admin", scope=" ".join([READ, WRITE, EXPORT, TECHNICAL, ESTIMATE]))
        assert "DRAFT_NOT_FOUND" in str(
            tool(client, foreign, "propose_capability", args, error=True)
        )
        estimate = saved(client, c, propose(client, c, "create_estimate", scope_revision=2))[
            "estimate_id"
        ]
        first = propose(
            client,
            c,
            "add_estimate_line",
            estimate_id=estimate,
            expected_revision=1,
            line=add_payload(),
        )
        stale = propose(
            client,
            c,
            "add_estimate_line",
            estimate_id=estimate,
            expected_revision=1,
            line=add_payload(),
        )
        saved(client, c, first)
        assert client.get(stale["review_url"]).status_code == 409
        duplicate = propose(
            client,
            c,
            "add_estimate_line",
            estimate_id=estimate,
            expected_revision=2,
            line=add_payload(),
        )
        confirm(client, duplicate, status=409)
        with c.scope.factory() as db:
            assert db.get(DraftClientRequest, duplicate["request_id"]).status == "pending"
            assert (
                estimates.read_estimate_revision(
                    db, db.get(User, c.scope.users["owner"]), c.draft_id, estimate
                )["revision"]
                == 2
            )
        pending = propose(
            client,
            c,
            "estimate_report",
            estimate_id=estimate,
            estimate_revision=2,
            profile="complete",
        )
        c.policy["clients"]["synthetic-client"].remove(ESTIMATE)
        c.path.write_text(json.dumps(c.policy), encoding="utf-8")
        assert client.get(pending["review_url"]).status_code == 403


def test_nested_capabilities_cannot_escape_through_reports_or_packages(capability_case):
    c = capability_case
    with TestClient(c.scope.app, base_url="https://testserver") as client:
        _login(client)
        match = saved(
            client,
            c,
            propose(
                client,
                c,
                "create_match",
                scope_revision=2,
                release_id=c.release_id,
                opening_id=uid(2),
                service_id=uid(5),
            ),
        )["match_id"]
        estimate = saved(
            client,
            c,
            propose(
                client, c, "create_estimate", scope_revision=2, match_id=match, match_revision=1
            ),
        )["estimate_id"]
        report = saved(
            client,
            c,
            propose(
                client,
                c,
                "estimate_report",
                estimate_id=estimate,
                estimate_revision=1,
                profile="complete",
            ),
        )["report_id"]
        limited = c.token(scope=" ".join([READ, WRITE, EXPORT, ESTIMATE]))
        for kind, artifact, parent in (
            ("system-match", match, None),
            ("estimate", estimate, None),
            ("estimate-report", report, estimate),
        ):
            result = tool(
                client,
                limited,
                "read_capability_artifact",
                {
                    "draft_id": c.draft_id,
                    "kind": kind,
                    "artifact_id": artifact,
                    "estimate_id": parent,
                },
                error=True,
            )
            assert "CLIENT_AUTHORIZATION_REQUIRED" in str(result)
        info = tool(
            client,
            c.full_token(),
            "report_download",
            {
                "draft_id": c.draft_id,
                "estimate_id": estimate,
                "report_id": report,
                "format_name": "pdf",
            },
        )
        assert (
            client.get(
                info["authenticated_url"], headers={"Authorization": "Bearer " + limited}
            ).status_code
            == 403
        )
        selection = {
            "scope_revision": 2,
            "match_id": match,
            "match_revision": 1,
            "estimate_id": estimate,
            "estimate_revision": 1,
            "estimate_reports": [report],
        }
        assert "CLIENT_AUTHORIZATION_REQUIRED" in str(
            tool(
                client,
                limited,
                "propose_project_package",
                {"draft_id": c.draft_id, "selection": selection},
                error=True,
            )
        )
        pending = tool(
            client,
            c.full_token(),
            "propose_project_package",
            {"draft_id": c.draft_id, "selection": selection},
        )
        package = saved(client, c, pending)["package_id"]
        info = tool(
            client,
            c.full_token(),
            "project_package_download",
            {"draft_id": c.draft_id, "package_id": package},
        )
        assert (
            client.get(
                info["authenticated_url"], headers={"Authorization": "Bearer " + limited}
            ).status_code
            == 403
        )
        assert "CLIENT_AUTHORIZATION_REQUIRED" in str(
            tool(
                client,
                limited,
                "project_package_download",
                {"draft_id": c.draft_id, "package_id": package},
                error=True,
            )
        )
        assert (
            tool(
                client,
                limited,
                "list_capability_artifacts",
                {"draft_id": c.draft_id, "kind": "estimate"},
            )["artifacts"]
            == []
        )


def test_estimate_status_rejection_and_replay_preserve_history(capability_case):
    import re

    from test_draft_scope_ui import _csrf

    c = capability_case
    with TestClient(c.scope.app, base_url="https://testserver") as client:
        _login(client)
        estimate = saved(client, c, propose(client, c, "create_estimate", scope_revision=2))[
            "estimate_id"
        ]
        saved(
            client,
            c,
            propose(
                client,
                c,
                "add_estimate_line",
                estimate_id=estimate,
                expected_revision=1,
                line=add_payload(),
            ),
        )
        line = read(client, c, "estimate", estimate)["artifact"]["lines"][0]
        rejected = propose(
            client,
            c,
            "set_estimate_line_status",
            estimate_id=estimate,
            expected_revision=2,
            line_id=line["line_id"],
            status="omitted",
            reason="Review this removal",
        )
        confirm(client, rejected, decision="reject")
        assert read(client, c, "estimate", estimate)["artifact"]["revision"] == 2
        pending = propose(
            client,
            c,
            "set_estimate_line_status",
            estimate_id=estimate,
            expected_revision=2,
            line_id=line["line_id"],
            status="omitted",
            reason="Confirmed duplicate scope",
        )
        page = client.get(pending["review_url"])
        digest = re.search(r'name="payload_hash" value="([^"]+)"', page.text).group(1)
        saved(client, c, pending)
        replay = client.post(
            pending["review_url"],
            data={"csrf_token": _csrf(page.text), "payload_hash": digest, "decision": "confirm"},
        )
        assert replay.status_code == 409
        content = read(client, c, "estimate", estimate)["artifact"]
        assert content["revision"] == 3 and content["lines"][0]["status"] == "omitted"
        assert len(content["lines"][0]["history"]) == 2
