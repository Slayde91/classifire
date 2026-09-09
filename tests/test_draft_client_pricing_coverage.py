from __future__ import annotations

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_client import client_case as _client_case
from test_draft_client import rpc, tool
from test_draft_pdf_ui import pdf_app as _pdf_app
from test_draft_pdf_ui import pdf_setup as _pdf_setup
from test_draft_pricing_coverage import _counts, _prepared
from test_draft_scope_ui import _app
from test_draft_scope_ui import scope_password_hash as _password_hash
from test_shared_file_containment import postgresql_session_factory as _postgres_fixture

from classifire.draft_client import configure
from classifire.draft_client_auth import ESTIMATE, READ, TECHNICAL
from classifire.models import DraftClientRequest, User
from classifire.services import draft_pricing_coverage as coverage

pdf_app = _pdf_app
pdf_setup = _pdf_setup
scope_password_hash = _password_hash
postgresql_session_factory = _postgres_fixture
client_case = _client_case


@pytest.fixture
def scope_app(pdf_app):
    """Reuse client identity setup with the real PostgreSQL containment fixture."""
    return SimpleNamespace(
        app=pdf_app.app,
        factory=pdf_app.factory,
        users={"owner": pdf_app.ids[0], "other": pdf_app.ids[1]},
    )


@pytest.fixture
def pricing_coverage_case(client_case, pdf_app, monkeypatch):
    case = client_case
    case.settings = pdf_app.settings
    case.draft_id = pdf_app.ids[2]
    case.policy["clients"]["synthetic-client"] = [READ, ESTIMATE, TECHNICAL]
    case.full_token = lambda user="owner": case.token(
        user=user, scope=" ".join([READ, ESTIMATE, TECHNICAL])
    )
    monkeypatch.setattr(
        "classifire.draft_client_capability_tools.get_settings", lambda: case.settings
    )
    with case.scope.factory() as db:
        owner = db.get(User, case.scope.users["owner"])
        owner.role = "administrator"
        _, _, _, variants, release, _, _, _, _ = _prepared(db, pdf_app)
        db.commit()
        case.release_id = release.id
        case.variant_ids = [variant.variant_id for variant in variants]
    case.path.write_text(json.dumps(case.policy), encoding="utf-8")
    return case


def _database_counts(case):
    with case.scope.factory() as db:
        return _counts(db) | {
            "draft_client_requests": db.scalar(
                select(func.count()).select_from(DraftClientRequest)
            )
        }


def test_pricing_coverage_tool_is_exact_read_only_and_survives_client_restart(
    pricing_coverage_case,
):
    case = pricing_coverage_case
    with case.scope.factory() as db:
        expected = coverage.preview_coverage(
            db,
            db.get(User, case.scope.users["owner"]),
            case.draft_id,
            case.release_id,
            settings=case.settings,
        )
    before = _database_counts(case)

    with TestClient(case.scope.app, base_url="https://testserver") as client:
        discovery = rpc(client, case.full_token(), "tools/list")
        assert discovery.status_code == 200, discovery.text
        exposed = {
            item["name"]: item for item in discovery.json()["result"]["tools"]
        }["preview_pricing_coverage"]
        assert exposed["annotations"] == {
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        }
        assert exposed["_meta"]["securitySchemes"] == [
            {"type": "oauth2", "scopes": [READ, ESTIMATE, TECHNICAL]}
        ]
        first = tool(
            client,
            case.full_token(),
            "preview_pricing_coverage",
            {"draft_id": case.draft_id, "technical_release_id": case.release_id},
        )
        assert first == expected
        assert [item["technical_target"]["variant_id"] for item in first["targets"]] == (
            case.variant_ids
        )
        assert first["effects"] == coverage.EFFECTS

    assert _database_counts(case) == before

    restarted_app = _app(case.scope.factory)
    mounted = configure(restarted_app, case.authority, case.scope.factory)

    @asynccontextmanager
    async def lifespan(app):
        async with mounted.router.lifespan_context(mounted):
            yield

    restarted_app.router.lifespan_context = lifespan
    with TestClient(restarted_app, base_url="https://testserver") as restarted:
        repeated = tool(
            restarted,
            case.full_token(),
            "preview_pricing_coverage",
            {"draft_id": case.draft_id, "technical_release_id": case.release_id},
        )
    assert repeated == first
    assert _database_counts(case) == before


def test_pricing_coverage_tool_enforces_client_project_and_domain_boundaries(
    pricing_coverage_case,
):
    case = pricing_coverage_case
    arguments = {
        "draft_id": case.draft_id,
        "technical_release_id": case.release_id,
    }
    before = _database_counts(case)
    with TestClient(case.scope.app, base_url="https://testserver") as client:
        for scopes in ([READ, ESTIMATE], [READ, TECHNICAL]):
            denied = tool(
                client,
                case.token(scope=" ".join(scopes)),
                "preview_pricing_coverage",
                arguments,
                error=True,
            )
            assert "CLIENT_AUTHORIZATION_REQUIRED" in str(denied)

        foreign = tool(
            client,
            case.full_token("other"),
            "preview_pricing_coverage",
            arguments,
            error=True,
        )
        assert "DRAFT_NOT_FOUND" in str(foreign)

        with case.scope.factory() as db:
            owner = db.get(User, case.scope.users["owner"])
            owner.role = "estimator"
            db.commit()
        denied_role = tool(
            client,
            case.full_token(),
            "preview_pricing_coverage",
            arguments,
            error=True,
        )
        assert "DRAFT_PERMISSION_DENIED" in str(denied_role)

        with case.scope.factory() as db:
            owner = db.get(User, case.scope.users["owner"])
            owner.role = "administrator"
            db.commit()
        missing_release = tool(
            client,
            case.full_token(),
            "preview_pricing_coverage",
            {
                **arguments,
                "technical_release_id": "00000000-0000-0000-0000-000000000000",
            },
            error=True,
        )
        assert "TECHNICAL_RELEASE_NOT_FOUND" in str(missing_release)

    assert _database_counts(case) == before
