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
from test_draft_pricing_profiles import sparse_mapping
from test_draft_pricing_recipes import _inputs
from test_draft_scope_ui import _app
from test_draft_scope_ui import scope_password_hash as _password_hash
from test_shared_file_containment import postgresql_session_factory as _postgres_fixture

from classifire.draft_client import configure
from classifire.draft_client_auth import ESTIMATE, READ
from classifire.models import (
    AuditEvent,
    DraftClientRequest,
    DraftPricingRowObservation,
    DraftPricingSourceProfile,
    Estimate,
    LibraryRelease,
    PricingLibraryRecord,
    TechnicalVariant,
    User,
    new_id,
)
from classifire.services import draft_pricing_intake as pricing
from classifire.services.draft_pricing_contract import validate_row_observation_envelope
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
def row_case(client_case, pdf_app, monkeypatch):
    case = client_case
    case.settings = pdf_app.settings
    case.draft_id = pdf_app.ids[2]
    case.policy["clients"]["synthetic-client"] = [READ, ESTIMATE]
    case.full_token = lambda user="owner": case.token(user=user, scope=" ".join([READ, ESTIMATE]))
    monkeypatch.setattr(
        "classifire.draft_client_capability_tools.get_settings", lambda: case.settings
    )
    with case.scope.factory() as db:
        owner = db.get(User, case.scope.users["owner"])
        owner.role = "administrator"
        _, _, reviewer, _, _, observation, _ = _inputs(db, pdf_app)
        db.commit()
        definition = observation["definition"]
        case.observation = observation
        case.observation_id = observation["observation_id"]
        case.source_id = definition["source"]["id"]
        case.profile_id = definition["profile"]["id"]
        case.reviewer_name = reviewer.full_name
    case.path.write_text(json.dumps(case.policy), encoding="utf-8")
    return case


def _counts(case):
    models = (
        AuditEvent,
        DraftClientRequest,
        DraftPricingRowObservation,
        DraftPricingSourceProfile,
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
    return {
        "draft_id": case.draft_id,
        "source_id": case.source_id,
        "profile_id": case.profile_id,
        "observation_id": case.observation_id,
    }


def _summary(case, *, observation=None):
    value = observation or case.observation
    definition = value["definition"]
    return {
        "observation_id": value["observation_id"],
        "reviewed_at": value["reviewed_at"],
        "reviewed_by": case.reviewer_name,
        "content_sha256": hashlib.sha256(canonical(value)).hexdigest(),
        "definition_sha256": value["definition_sha256"],
        "dataset_id": definition["dataset"]["id"],
        "dataset_version": definition["dataset"]["version"],
        "source_sha256": definition["source"]["sha256"],
        "profile_revision": definition["profile"]["revision"],
        "profile_sha256": definition["profile"]["sha256"],
        "row_number": definition["row"]["row"],
        "row_sha256": definition["row"]["sha256"],
        "item_kind": definition["interpretation"]["item_kind"],
        "normalized_reference": definition["interpretation"]["normalized_reference"],
        "evidence_state": definition["interpretation"]["evidence_state"],
        "unresolved_fields": definition["interpretation"]["unresolved_fields"],
        "is_current": True,
    }


def test_row_observation_client_lists_reads_exact_bytes_and_reports_staleness_after_restart(
    row_case,
):
    case = row_case
    before = _counts(case)
    expected_bytes = canonical(case.observation)
    expected_sha256 = hashlib.sha256(expected_bytes).hexdigest()

    with TestClient(case.scope.app, base_url="https://testserver") as client:
        discovery = rpc(client, case.full_token(), "tools/list")
        assert discovery.status_code == 200, discovery.text
        exposed = {item["name"]: item for item in discovery.json()["result"]["tools"]}
        for name in (
            "list_pricing_row_observations",
            "read_pricing_row_observation",
        ):
            assert exposed[name]["annotations"] == {
                "readOnlyHint": True,
                "destructiveHint": False,
                "openWorldHint": False,
            }
            assert exposed[name]["_meta"]["securitySchemes"] == [
                {"type": "oauth2", "scopes": [READ, ESTIMATE]}
            ]

        listing = tool(
            client,
            case.full_token(),
            "list_pricing_row_observations",
            {
                "draft_id": case.draft_id,
                "source_id": case.source_id,
                "profile_id": case.profile_id,
            },
        )
        assert listing == {
            "observations": [_summary(case)],
            "next_after_observation_id": None,
            "limit": 20,
        }
        exact = tool(
            client,
            case.full_token(),
            "read_pricing_row_observation",
            _arguments(case),
        )
        assert exact == {
            "observation": case.observation,
            "sha256": expected_sha256,
            "size_bytes": len(expected_bytes),
        }
        assert canonical(exact["observation"]) == expected_bytes
        assert all(
            value is False for value in exact["observation"]["definition"]["effects"].values()
        )
    assert _counts(case) == before

    restarted_app = _app(case.scope.factory)
    mounted = configure(restarted_app, case.authority, case.scope.factory)

    @asynccontextmanager
    async def lifespan(app):
        async with mounted.router.lifespan_context(mounted):
            yield

    restarted_app.router.lifespan_context = lifespan
    with TestClient(restarted_app, base_url="https://testserver") as restarted:
        assert (
            tool(
                restarted,
                case.full_token(),
                "read_pricing_row_observation",
                _arguments(case),
            )
            == exact
        )

        with case.scope.factory() as db:
            owner = db.get(User, case.scope.users["owner"])
            source = case.observation["definition"]["source"]
            profile = case.observation["definition"]["profile"]
            mapping = sparse_mapping()
            preview = pricing.preview_profile(
                db,
                owner,
                case.draft_id,
                case.source_id,
                1,
                1,
                mapping,
                profile["price_meaning"],
                settings=case.settings,
            )
            pricing.save_profile(
                db,
                owner,
                case.draft_id,
                case.source_id,
                1,
                1,
                mapping,
                profile["price_meaning"],
                profile["revision"],
                source["document_sha256"],
                preview["preview_hash"],
                settings=case.settings,
            )
            db.commit()
        after_revision = _counts(case)
        stale = tool(
            restarted,
            case.full_token(),
            "list_pricing_row_observations",
            {
                "draft_id": case.draft_id,
                "source_id": case.source_id,
                "profile_id": case.profile_id,
            },
        )
        assert stale["observations"][0]["is_current"] is False
        assert _counts(case) == after_revision


def test_row_observation_client_fails_closed_for_scope_owner_role_id_and_integrity(
    row_case,
):
    case = row_case
    arguments = _arguments(case)
    before = _counts(case)
    with TestClient(case.scope.app, base_url="https://testserver") as client:
        denied = tool(
            client,
            case.token(scope=READ),
            "read_pricing_row_observation",
            arguments,
            error=True,
        )
        assert "CLIENT_AUTHORIZATION_REQUIRED" in str(denied)

        foreign = tool(
            client,
            case.full_token("other"),
            "list_pricing_row_observations",
            {
                "draft_id": case.draft_id,
                "source_id": case.source_id,
                "profile_id": case.profile_id,
            },
            error=True,
        )
        assert "DRAFT_NOT_FOUND" in str(foreign)

        with case.scope.factory() as db:
            owner = db.get(User, case.scope.users["owner"])
            owner.role = "project_manager"
            db.commit()
        denied_role = tool(
            client,
            case.full_token(),
            "read_pricing_row_observation",
            arguments,
            error=True,
        )
        assert "DRAFT_PERMISSION_DENIED" in str(denied_role)

        with case.scope.factory() as db:
            owner = db.get(User, case.scope.users["owner"])
            owner.role = "administrator"
            stored = db.get(DraftPricingRowObservation, case.observation_id)
            original = stored.observation_json
            stored.observation_json += " "
            db.commit()
        corrupt = tool(
            client,
            case.full_token(),
            "read_pricing_row_observation",
            arguments,
            error=True,
        )
        assert "PRICING_ROW_OBSERVATION_INTEGRITY_FAILED" in str(corrupt)
        corrupt_list = tool(
            client,
            case.full_token(),
            "list_pricing_row_observations",
            {
                "draft_id": case.draft_id,
                "source_id": case.source_id,
                "profile_id": case.profile_id,
            },
            error=True,
        )
        assert "PRICING_ROW_OBSERVATION_INTEGRITY_FAILED" in str(corrupt_list)

        with case.scope.factory() as db:
            stored = db.get(DraftPricingRowObservation, case.observation_id)
            stored.observation_json = original
            db.commit()
        missing = tool(
            client,
            case.full_token(),
            "read_pricing_row_observation",
            arguments | {"observation_id": "00000000-0000-0000-0000-000000000000"},
            error=True,
        )
        assert "PRICING_ROW_OBSERVATION_NOT_FOUND" in str(missing)
        invalid_page = tool(
            client,
            case.full_token(),
            "list_pricing_row_observations",
            {
                "draft_id": case.draft_id,
                "source_id": case.source_id,
                "profile_id": case.profile_id,
                "after_observation_id": "00000000-0000-0000-0000-000000000000",
            },
            error=True,
        )
        assert "PRICING_ROW_OBSERVATION_LIST_INVALID" in str(invalid_page)

    assert _counts(case) == before


def _append_history(case, *, total):
    observations = [case.observation]
    with case.scope.factory() as db:
        base = db.get(DraftPricingRowObservation, case.observation_id)
        created = datetime.fromisoformat(case.observation["reviewed_at"])
        for number in range(3, total + 2):
            created += timedelta(seconds=1)
            value = copy.deepcopy(case.observation)
            definition = value["definition"]
            row = definition["row"]
            row["row"] = number
            for cell in row["fields"].values():
                if cell is None:
                    continue
                cell["row"] = number
                column = "".join(character for character in cell["address"] if character.isalpha())
                cell["address"] = column + str(number)
            row["sha256"] = digest({key: item for key, item in row.items() if key != "sha256"})
            definition["interpretation"]["review_reason"] = (
                f"Synthetic reviewed Dataset A row {number}."
            )
            observation_id = new_id()
            value["observation_id"] = observation_id
            value["reviewed_at"] = created.isoformat()
            value["definition_sha256"] = digest(definition)
            validate_row_observation_envelope(value)
            raw = canonical(value)
            interpretation = definition["interpretation"]
            db.add(
                DraftPricingRowObservation(
                    id=observation_id,
                    draft_scope_id=base.draft_scope_id,
                    source_id=base.source_id,
                    profile_id=base.profile_id,
                    profile_decision_id=base.profile_decision_id,
                    dataset_id=base.dataset_id,
                    dataset_version=base.dataset_version,
                    source_sha256=base.source_sha256,
                    document_sha256=base.document_sha256,
                    profile_revision=base.profile_revision,
                    profile_sha256=base.profile_sha256,
                    decision_sha256=base.decision_sha256,
                    sheet_index=row["sheet_index"],
                    row_number=number,
                    row_sha256=row["sha256"],
                    item_kind=interpretation["item_kind"],
                    normalized_reference=interpretation["normalized_reference"],
                    evidence_state=interpretation["evidence_state"],
                    review_reason=interpretation["review_reason"],
                    observation_json=raw.decode("utf-8"),
                    observation_sha256=hashlib.sha256(raw).hexdigest(),
                    reviewed_by_id=value["reviewed_by_id"],
                    created_at=created,
                    updated_at=created,
                )
            )
            observations.append(value)
        db.commit()
    return observations


def test_row_observation_client_pages_twenty_in_worksheet_order(row_case):
    case = row_case
    observations = _append_history(case, total=22)
    before = _counts(case)

    with TestClient(case.scope.app, base_url="https://testserver") as client:
        first = tool(
            client,
            case.full_token(),
            "list_pricing_row_observations",
            {
                "draft_id": case.draft_id,
                "source_id": case.source_id,
                "profile_id": case.profile_id,
            },
        )
        assert [item["observation_id"] for item in first["observations"]] == [
            item["observation_id"] for item in observations[:20]
        ]
        assert first["next_after_observation_id"] == observations[19]["observation_id"]
        assert first["limit"] == 20

        second = tool(
            client,
            case.full_token(),
            "list_pricing_row_observations",
            {
                "draft_id": case.draft_id,
                "source_id": case.source_id,
                "profile_id": case.profile_id,
                "after_observation_id": first["next_after_observation_id"],
            },
        )
        assert [item["observation_id"] for item in second["observations"]] == [
            item["observation_id"] for item in observations[20:]
        ]
        assert second["next_after_observation_id"] is None

    assert _counts(case) == before
