from __future__ import annotations

import hashlib
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_client import client_case as _client_case
from test_draft_client import rpc, tool
from test_draft_pdf_ui import pdf_app as _pdf_app
from test_draft_pdf_ui import pdf_setup as _pdf_setup
from test_draft_pricing_evaluation_rosters import _prepared, _save
from test_draft_scope_ui import _app
from test_draft_scope_ui import scope_password_hash as _password_hash
from test_shared_file_containment import postgresql_session_factory as _postgres_fixture

from classifire.draft_client import configure
from classifire.draft_client_auth import ESTIMATE, READ, TECHNICAL
from classifire.models import (
    AuditEvent,
    DraftClientRequest,
    DraftPricingEvaluationRoster,
    DraftPricingSystemMapping,
    Estimate,
    LibraryRelease,
    PricingLibraryRecord,
    TechnicalVariant,
    User,
    new_id,
)
from classifire.services import draft_pricing_evaluation_rosters as rosters
from classifire.services.draft_pricing_evaluation_contract import build_lineage_manifest
from classifire.services.draft_system_match_contract import canonical, digest

pdf_app = _pdf_app
pdf_setup = _pdf_setup
scope_password_hash = _password_hash
postgresql_session_factory = _postgres_fixture
client_case = _client_case


@pytest.fixture
def scope_app(pdf_app):
    return SimpleNamespace(
        app=pdf_app.app,
        factory=pdf_app.factory,
        users={"owner": pdf_app.ids[0], "other": pdf_app.ids[1]},
    )


@pytest.fixture
def roster_case(client_case, pdf_app, monkeypatch):
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
        _, _, reviewer, *_ = _prepared(db, pdf_app)
        preview = rosters.preview_roster(
            db, reviewer, case.draft_id, settings=case.settings
        )
        saved = _save(db, reviewer, case.draft_id, preview, case.settings)
        db.commit()
        case.roster_id = saved["roster_id"]
        case.roster = saved
    case.path.write_text(json.dumps(case.policy), encoding="utf-8")
    return case


def _counts(case):
    models = (
        AuditEvent,
        DraftClientRequest,
        DraftPricingEvaluationRoster,
        DraftPricingSystemMapping,
        Estimate,
        LibraryRelease,
        PricingLibraryRecord,
        TechnicalVariant,
    )
    with case.scope.factory() as db:
        return {
            model.__tablename__: db.scalar(select(func.count()).select_from(model))
            for model in models
        }


def _arguments(case):
    return {"draft_id": case.draft_id, "roster_id": case.roster_id}


def test_roster_client_lists_and_reads_exact_target_blind_bytes_after_restart(roster_case):
    case = roster_case
    before = _counts(case)
    expected_bytes = canonical(case.roster)
    expected_sha256 = hashlib.sha256(expected_bytes).hexdigest()

    with TestClient(case.scope.app, base_url="https://testserver") as client:
        discovery = rpc(client, case.full_token(), "tools/list")
        assert discovery.status_code == 200, discovery.text
        exposed = {
            item["name"]: item for item in discovery.json()["result"]["tools"]
        }
        for name in (
            "list_pricing_evaluation_rosters",
            "read_pricing_evaluation_roster",
        ):
            assert exposed[name]["annotations"] == {
                "readOnlyHint": True,
                "destructiveHint": False,
                "openWorldHint": False,
            }
            assert exposed[name]["_meta"]["securitySchemes"] == [
                {"type": "oauth2", "scopes": [READ, ESTIMATE, TECHNICAL]}
            ]

        listing = tool(
            client,
            case.full_token(),
            "list_pricing_evaluation_rosters",
            {"draft_id": case.draft_id},
        )
        assert listing == {
            "rosters": [
                {
                    "roster_id": case.roster_id,
                    "revision": 1,
                    "created_at": case.roster["created_at"],
                    "roster_sha256": case.roster["roster_sha256"],
                    "content_sha256": expected_sha256,
                    "manifest_sha256": case.roster["manifest"]["manifest_sha256"],
                    "mapping_inventory_sha256": case.roster[
                        "mapping_inventory_sha256"
                    ],
                    "is_current": True,
                }
            ],
            "next_before_revision": None,
            "limit": 20,
        }
        assert (
            tool(
                client,
                case.full_token(),
                "list_pricing_evaluation_rosters",
                {"draft_id": case.draft_id, "before_revision": 1},
            )["rosters"]
            == []
        )
        exact = tool(
            client,
            case.full_token(),
            "read_pricing_evaluation_roster",
            _arguments(case),
        )
        assert exact == {
            "roster": case.roster,
            "sha256": expected_sha256,
            "size_bytes": len(expected_bytes),
        }
        assert canonical(exact["roster"]) == expected_bytes
        assert exact["roster"]["effects"] == rosters.EFFECTS
        assert {
            tuple(member["target"])
            for group in exact["roster"]["manifest"]["groups"]
            for member in group["members"]
        } == {("field", "sha256")}
        assert b'"target":{"field":"rate","sha256":' in expected_bytes

    assert _counts(case) == before

    restarted_app = _app(case.scope.factory)
    mounted = configure(restarted_app, case.authority, case.scope.factory)

    @asynccontextmanager
    async def lifespan(app):
        async with mounted.router.lifespan_context(mounted):
            yield

    restarted_app.router.lifespan_context = lifespan
    with TestClient(restarted_app, base_url="https://testserver") as restarted:
        assert tool(
            restarted,
            case.full_token(),
            "read_pricing_evaluation_roster",
            _arguments(case),
        ) == exact
    assert _counts(case) == before


def test_roster_client_fails_closed_for_scope_owner_role_id_and_integrity(roster_case):
    case = roster_case
    arguments = _arguments(case)
    before = _counts(case)
    with TestClient(case.scope.app, base_url="https://testserver") as client:
        for granted in ([READ, ESTIMATE], [READ, TECHNICAL]):
            denied = tool(
                client,
                case.token(scope=" ".join(granted)),
                "read_pricing_evaluation_roster",
                arguments,
                error=True,
            )
            assert "CLIENT_AUTHORIZATION_REQUIRED" in str(denied)

        foreign = tool(
            client,
            case.full_token("other"),
            "list_pricing_evaluation_rosters",
            {"draft_id": case.draft_id},
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
            "read_pricing_evaluation_roster",
            arguments,
            error=True,
        )
        assert "DRAFT_PERMISSION_DENIED" in str(denied_role)

        with case.scope.factory() as db:
            owner = db.get(User, case.scope.users["owner"])
            owner.role = "administrator"
            stored = db.get(DraftPricingEvaluationRoster, case.roster_id)
            original = stored.roster_json
            stored.roster_json += " "
            db.commit()
        corrupt = tool(
            client,
            case.full_token(),
            "read_pricing_evaluation_roster",
            arguments,
            error=True,
        )
        assert "PRICING_EVALUATION_ROSTER_INTEGRITY_FAILED" in str(corrupt)
        corrupt_list = tool(
            client,
            case.full_token(),
            "list_pricing_evaluation_rosters",
            {"draft_id": case.draft_id},
            error=True,
        )
        assert "PRICING_EVALUATION_ROSTER_INTEGRITY_FAILED" in str(corrupt_list)

        with case.scope.factory() as db:
            stored = db.get(DraftPricingEvaluationRoster, case.roster_id)
            stored.roster_json = original
            db.commit()
        missing = tool(
            client,
            case.full_token(),
            "read_pricing_evaluation_roster",
            {
                "draft_id": case.draft_id,
                "roster_id": "00000000-0000-0000-0000-000000000000",
            },
            error=True,
        )
        assert "PRICING_EVALUATION_ROSTER_NOT_FOUND" in str(missing)
        invalid_page = tool(
            client,
            case.full_token(),
            "list_pricing_evaluation_rosters",
            {"draft_id": case.draft_id, "before_revision": 0},
            error=True,
        )
        assert "PRICING_EVALUATION_ROSTER_LIST_INVALID" in str(invalid_page)

    assert _counts(case) == before


def _append_history(case, *, through_revision: int) -> None:
    with case.scope.factory() as db:
        previous = case.roster
        created = datetime.fromisoformat(previous["created_at"])
        for revision in range(2, through_revision + 1):
            created += timedelta(seconds=1)
            created_at = created.isoformat()
            observations = [
                {**member, "split": group["split"]}
                for group in previous["manifest"]["groups"]
                for member in group["members"]
            ]
            manifest = build_lineage_manifest(
                manifest_id=previous["manifest_id"],
                draft_scope_id=case.draft_id,
                revision=revision,
                parent_manifest_sha256=previous["manifest"]["manifest_sha256"],
                created_at=created_at,
                created_by_id=previous["created_by_id"],
                feature_cutoff_at=created_at,
                observations=observations,
                feature_declarations=previous["manifest"]["feature_declarations"],
            )
            roster = {
                **previous,
                "roster_id": new_id(),
                "revision": revision,
                "parent_manifest_sha256": previous["manifest"]["manifest_sha256"],
                "created_at": created_at,
                "feature_cutoff_at": created_at,
                "manifest": manifest,
            }
            roster["roster_sha256"] = digest(
                {key: value for key, value in roster.items() if key != "roster_sha256"}
            )
            raw = canonical(roster)
            db.add(
                DraftPricingEvaluationRoster(
                    id=roster["roster_id"],
                    draft_scope_id=case.draft_id,
                    revision=revision,
                    manifest_id=roster["manifest_id"],
                    parent_manifest_sha256=roster["parent_manifest_sha256"],
                    mapping_inventory_sha256=roster["mapping_inventory_sha256"],
                    manifest_sha256=manifest["manifest_sha256"],
                    feature_cutoff_at=created,
                    roster_json=raw.decode("utf-8"),
                    roster_sha256=hashlib.sha256(raw).hexdigest(),
                    created_by_id=roster["created_by_id"],
                    created_at=created,
                    updated_at=created,
                )
            )
            previous = roster
        db.commit()


def test_roster_client_pages_twenty_summaries_and_marks_only_latest_current(roster_case):
    case = roster_case
    _append_history(case, through_revision=22)
    before = _counts(case)

    with TestClient(case.scope.app, base_url="https://testserver") as client:
        first = tool(
            client,
            case.full_token(),
            "list_pricing_evaluation_rosters",
            {"draft_id": case.draft_id},
        )
        assert [item["revision"] for item in first["rosters"]] == list(
            range(22, 2, -1)
        )
        assert [item["is_current"] for item in first["rosters"]] == [True] + [
            False
        ] * 19
        assert first["next_before_revision"] == 3
        assert first["limit"] == 20

        second = tool(
            client,
            case.full_token(),
            "list_pricing_evaluation_rosters",
            {"draft_id": case.draft_id, "before_revision": 3},
        )
        assert [item["revision"] for item in second["rosters"]] == [2, 1]
        assert all(item["is_current"] is False for item in second["rosters"])
        assert second["next_before_revision"] is None
        assert second["limit"] == 20

    assert _counts(case) == before
