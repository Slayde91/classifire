from __future__ import annotations

import copy
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
from test_draft_pricing_recipes import _inputs
from test_draft_scope_ui import _app
from test_draft_scope_ui import scope_password_hash as _password_hash
from test_shared_file_containment import postgresql_session_factory as _postgres_fixture

from classifire.draft_client import configure
from classifire.draft_client_auth import ESTIMATE, READ, TECHNICAL
from classifire.models import (
    AuditEvent,
    DraftClientRequest,
    DraftPricingRecipeLink,
    DraftPricingRowObservation,
    Estimate,
    LibraryRelease,
    PricingLibraryRecord,
    TechnicalVariant,
    User,
    new_id,
)
from classifire.services import draft_pricing_recipes as recipes
from classifire.services.draft_pricing_recipe_contract import recipe_link_envelope
from classifire.services.draft_system_match_contract import canonical

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
def recipe_case(client_case, pdf_app, monkeypatch):
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
        _, _, reviewer, target, release, observation, requirement = _inputs(db, pdf_app)
        kwargs = {
            "status": "linked",
            "unit": "each",
            "quantity_basis": "One reviewed unit per repair opening",
            "yield_basis": "One source unit",
            "productivity_basis": None,
            "recovery_boundary": "Material supply only; installation is separate",
            "evidence_state": "confirmed",
            "review_reason": "The frozen component and Dataset A row were reviewed.",
            "unresolved_fields": [],
            "settings": case.settings,
        }
        preview = recipes.preview_recipe_link(
            db,
            reviewer,
            case.draft_id,
            release.id,
            target.id,
            requirement["id"],
            [observation["observation_id"]],
            **kwargs,
        )
        saved = recipes.save_recipe_link(
            db,
            reviewer,
            case.draft_id,
            release.id,
            target.id,
            requirement["id"],
            [observation["observation_id"]],
            expected_release_sha256=preview["technical_release_sha256"],
            expected_variant_snapshot_sha256=preview[
                "technical_variant_snapshot_sha256"
            ],
            expected_recipe_snapshot_sha256=preview["recipe_snapshot_sha256"],
            expected_preview_hash=preview["preview_hash"],
            **kwargs,
        )
        db.commit()
        case.link_id = saved["link_id"]
        case.link = saved
        case.target_id = target.id
    case.path.write_text(json.dumps(case.policy), encoding="utf-8")
    return case


def _counts(case):
    models = (
        AuditEvent,
        DraftClientRequest,
        DraftPricingRecipeLink,
        DraftPricingRowObservation,
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
    return {"draft_id": case.draft_id, "link_id": case.link_id}


def _summary(case, *, content_sha256: str):
    definition = case.link["definition"]
    return {
        "link_id": case.link_id,
        "reviewed_at": case.link["reviewed_at"],
        "link_sha256": content_sha256,
        "definition_sha256": case.link["definition_sha256"],
        "technical_release_id": definition["technical_release"]["id"],
        "technical_release_sha256": definition["technical_release"]["sha256"],
        "technical_target_id": definition["technical_target"]["id"],
        "technical_variant_snapshot_sha256": definition["technical_target"][
            "snapshot_sha256"
        ],
        "recipe_snapshot_sha256": definition["technical_target"][
            "recipe_snapshot_sha256"
        ],
        "requirement_id": definition["requirement"]["id"],
        "requirement_kind": definition["requirement"]["kind"],
        "requirement_path": definition["requirement"]["path"],
        "requirement_label": definition["requirement"]["label"],
        "status": definition["interpretation"]["status"],
        "evidence_state": definition["interpretation"]["evidence_state"],
        "observation_count": len(definition["observations"]),
        "current": True,
    }


def test_recipe_link_client_lists_and_reads_exact_bytes_after_restart(recipe_case):
    case = recipe_case
    before = _counts(case)
    expected_bytes = canonical(case.link)
    expected_sha256 = hashlib.sha256(expected_bytes).hexdigest()

    with TestClient(case.scope.app, base_url="https://testserver") as client:
        discovery = rpc(client, case.full_token(), "tools/list")
        assert discovery.status_code == 200, discovery.text
        exposed = {
            item["name"]: item for item in discovery.json()["result"]["tools"]
        }
        for name in ("list_pricing_recipe_links", "read_pricing_recipe_link"):
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
            "list_pricing_recipe_links",
            {"draft_id": case.draft_id},
        )
        assert listing == {
            "links": [_summary(case, content_sha256=expected_sha256)],
            "next_before_link_id": None,
            "limit": 20,
        }
        exact = tool(
            client,
            case.full_token(),
            "read_pricing_recipe_link",
            _arguments(case),
        )
        assert exact == {
            "link": case.link,
            "sha256": expected_sha256,
            "size_bytes": len(expected_bytes),
        }
        assert canonical(exact["link"]) == expected_bytes
        assert all(value is False for value in exact["link"]["definition"]["effects"].values())

        with case.scope.factory() as db:
            target = db.get(TechnicalVariant, case.target_id)
            original_manufacturer = target.manufacturer
            target.manufacturer = "Changed after the reviewed recipe link"
            db.commit()
        stale = tool(
            client,
            case.full_token(),
            "list_pricing_recipe_links",
            {"draft_id": case.draft_id},
        )
        assert stale["links"][0]["current"] is False
        with case.scope.factory() as db:
            target = db.get(TechnicalVariant, case.target_id)
            target.manufacturer = original_manufacturer
            db.commit()
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
            "read_pricing_recipe_link",
            _arguments(case),
        ) == exact
    assert _counts(case) == before


def test_recipe_link_client_fails_closed_for_scope_owner_role_id_and_integrity(recipe_case):
    case = recipe_case
    arguments = _arguments(case)
    before = _counts(case)
    with TestClient(case.scope.app, base_url="https://testserver") as client:
        for granted in ([READ, ESTIMATE], [READ, TECHNICAL]):
            denied = tool(
                client,
                case.token(scope=" ".join(granted)),
                "read_pricing_recipe_link",
                arguments,
                error=True,
            )
            assert "CLIENT_AUTHORIZATION_REQUIRED" in str(denied)

        foreign = tool(
            client,
            case.full_token("other"),
            "list_pricing_recipe_links",
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
            "read_pricing_recipe_link",
            arguments,
            error=True,
        )
        assert "DRAFT_PERMISSION_DENIED" in str(denied_role)

        with case.scope.factory() as db:
            owner = db.get(User, case.scope.users["owner"])
            owner.role = "administrator"
            stored = db.get(DraftPricingRecipeLink, case.link_id)
            original = stored.link_json
            stored.link_json += " "
            db.commit()
        corrupt = tool(
            client,
            case.full_token(),
            "read_pricing_recipe_link",
            arguments,
            error=True,
        )
        assert "PRICING_RECIPE_LINK_INTEGRITY_FAILED" in str(corrupt)
        corrupt_list = tool(
            client,
            case.full_token(),
            "list_pricing_recipe_links",
            {"draft_id": case.draft_id},
            error=True,
        )
        assert "PRICING_RECIPE_LINK_INTEGRITY_FAILED" in str(corrupt_list)

        with case.scope.factory() as db:
            stored = db.get(DraftPricingRecipeLink, case.link_id)
            stored.link_json = original
            db.commit()
        missing = tool(
            client,
            case.full_token(),
            "read_pricing_recipe_link",
            {
                "draft_id": case.draft_id,
                "link_id": "00000000-0000-0000-0000-000000000000",
            },
            error=True,
        )
        assert "PRICING_RECIPE_LINK_NOT_FOUND" in str(missing)
        invalid_page = tool(
            client,
            case.full_token(),
            "list_pricing_recipe_links",
            {
                "draft_id": case.draft_id,
                "before_link_id": "00000000-0000-0000-0000-000000000000",
            },
            error=True,
        )
        assert "PRICING_RECIPE_LINK_LIST_INVALID" in str(invalid_page)

    assert _counts(case) == before


def _append_history(case, *, total: int) -> list[str]:
    identifiers = [case.link_id]
    with case.scope.factory() as db:
        created = datetime.fromisoformat(case.link["reviewed_at"])
        for number in range(2, total + 1):
            created += timedelta(seconds=1)
            definition = copy.deepcopy(case.link["definition"])
            definition["interpretation"]["review_reason"] = (
                f"Synthetic pagination decision {number}."
            )
            link_id = new_id()
            envelope = recipe_link_envelope(
                definition,
                link_id=link_id,
                reviewed_by_id=case.link["reviewed_by_id"],
                reviewed_at=created,
            )
            raw = canonical(envelope)
            target = definition["technical_target"]
            requirement = definition["requirement"]
            interpretation = definition["interpretation"]
            db.add(
                DraftPricingRecipeLink(
                    id=link_id,
                    draft_scope_id=case.draft_id,
                    technical_release_id=definition["technical_release"]["id"],
                    technical_release_sha256=definition["technical_release"]["sha256"],
                    technical_variant_id=target["id"],
                    technical_variant_snapshot_sha256=target["snapshot_sha256"],
                    recipe_snapshot_sha256=target["recipe_snapshot_sha256"],
                    requirement_id=requirement["id"],
                    requirement_kind=requirement["kind"],
                    requirement_path=requirement["path"],
                    mapping_status=interpretation["status"],
                    evidence_state=interpretation["evidence_state"],
                    definition_sha256=envelope["definition_sha256"],
                    link_json=raw.decode("utf-8"),
                    link_sha256=hashlib.sha256(raw).hexdigest(),
                    reviewed_by_id=envelope["reviewed_by_id"],
                    created_at=created,
                    updated_at=created,
                )
            )
            identifiers.append(link_id)
        db.commit()
    return identifiers


def test_recipe_link_client_pages_twenty_newest_summaries(recipe_case):
    case = recipe_case
    identifiers = _append_history(case, total=22)
    before = _counts(case)

    with TestClient(case.scope.app, base_url="https://testserver") as client:
        first = tool(
            client,
            case.full_token(),
            "list_pricing_recipe_links",
            {"draft_id": case.draft_id},
        )
        assert [item["link_id"] for item in first["links"]] == list(
            reversed(identifiers)
        )[:20]
        assert first["next_before_link_id"] == identifiers[2]
        assert first["limit"] == 20

        second = tool(
            client,
            case.full_token(),
            "list_pricing_recipe_links",
            {
                "draft_id": case.draft_id,
                "before_link_id": first["next_before_link_id"],
            },
        )
        assert [item["link_id"] for item in second["links"]] == list(
            reversed(identifiers[:2])
        )
        assert second["next_before_link_id"] is None
        assert second["limit"] == 20

    assert _counts(case) == before
