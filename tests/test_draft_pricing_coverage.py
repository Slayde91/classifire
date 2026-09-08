from __future__ import annotations

import hashlib
import io
import re

import pytest
import xlsxwriter
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_pdf_intake import pdf_setup as _pdf_setup
from test_draft_pdf_ui import pdf_app as _pdf_app
from test_draft_pricing import workbook_bytes
from test_draft_pricing_profiles import sparse_mapping
from test_draft_scope import sample_payload
from test_draft_scope_ui import _csrf, _login
from test_draft_scope_ui import scope_password_hash as _password_hash
from test_shared_file_containment import postgresql_session_factory as _postgres_fixture
from test_technical_release_publication import _bound_variant, _publish

from classifire.draft_estimate_ui import router as estimate_router
from classifire.draft_pricing_ui import router as pricing_router
from classifire.models import (
    AuditEvent,
    DraftPricingEvaluationRoster,
    DraftPricingRowObservation,
    DraftPricingSystemMapping,
    Estimate,
    LibraryRelease,
    PricingLibraryRecord,
    TechnicalVariant,
    User,
)
from classifire.services import draft_estimates as estimates
from classifire.services import draft_pricing_coverage as coverage
from classifire.services import draft_pricing_intake as pricing
from classifire.services import draft_scope as scope
from classifire.services.draft_pricing_contract import FIELDS
from classifire.services.draft_system_match_contract import canonical, digest

pdf_setup = _pdf_setup
pdf_app = _pdf_app
scope_password_hash = _password_hash
postgresql_session_factory = _postgres_fixture


def _system_workbook(rate: float) -> bytes:
    stream = io.BytesIO()
    book = xlsxwriter.Workbook(stream, {"in_memory": True})
    sheet = book.add_worksheet("Systems")
    sheet.write_row(0, 0, list(FIELDS))
    for index in range(1, 4):
        sheet.write_row(
            index,
            0,
            [
                f"COVERAGE-{index + 1}",
                f"Synthetic covered system {index}",
                "each",
                rate + index,
                "AUD",
                "excluded",
                "2026-09-08",
                20,
                80,
                "Installed system",
                "No shared closure",
            ],
        )
    book.close()
    return stream.getvalue()


def _reviewed_source(db, x, owner, reviewer, kind: str, rate: float):
    source = pricing.retain_source(
        db,
        owner,
        x.ids[2],
        f"{kind}-{rate}.xlsx",
        _system_workbook(rate) if kind == "firefly_system_prices" else workbook_bytes(rate=rate),
        kind,
        settings=x.settings,
    )
    pricing.intake().scan_source(db, owner, x.ids[2], source.id, settings=x.settings)
    mapping = sparse_mapping()
    preview = pricing.preview_profile(
        db,
        owner,
        x.ids[2],
        source.id,
        1,
        1,
        mapping,
        "sell_price",
        settings=x.settings,
    )
    profile = pricing.save_profile(
        db,
        owner,
        x.ids[2],
        source.id,
        1,
        1,
        mapping,
        "sell_price",
        0,
        source.document_sha256,
        preview["preview_hash"],
        settings=x.settings,
    )
    profile_hash = hashlib.sha256(canonical(profile)).hexdigest()
    decision = pricing.save_profile_decision(
        db,
        reviewer,
        x.ids[2],
        source.id,
        profile["profile_id"],
        profile_hash,
        "approve",
        f"The exact {kind} source profile and price meaning were checked.",
    )
    return (
        source,
        profile,
        profile_hash,
        hashlib.sha256(canonical(decision)).hexdigest(),
    )


def _save_mapping(
    db,
    x,
    reviewer,
    release,
    source,
    profile,
    profile_hash,
    decision_hash,
    row_number: int,
    status: str,
    *,
    selected=None,
    candidates=(),
):
    candidate_ids = sorted(item.id for item in candidates)
    reference = f"COVERAGE-{row_number}"
    unresolved = ["configuration_identity"] if status != "mapped" else []
    preview = pricing.preview_system_mapping(
        db,
        reviewer,
        x.ids[2],
        source.id,
        profile["profile_id"],
        row_number,
        release.id,
        status,
        reference,
        selected.id if selected else None,
        candidate_ids,
        ["reference", "description"],
        "The exact row identity was reviewed for pricing coverage.",
        unresolved,
        settings=x.settings,
    )
    return pricing.save_system_mapping(
        db,
        reviewer,
        x.ids[2],
        source.id,
        profile["profile_id"],
        row_number,
        release.id,
        status,
        reference,
        selected.id if selected else None,
        candidate_ids,
        ["reference", "description"],
        "The exact row identity was reviewed for pricing coverage.",
        unresolved,
        profile_hash,
        decision_hash,
        preview["definition"]["row"]["sha256"],
        release.release_hash,
        preview["preview_hash"],
        settings=x.settings,
    )


def _prepared(db, x):
    owner = db.get(User, x.ids[0])
    foreign = db.get(User, x.ids[1])
    reviewer = User(
        email="admin@scope.example.test",
        full_name="Synthetic coverage reviewer",
        role="administrator",
        is_active=True,
        password_hash=owner.password_hash,
    )
    db.add(reviewer)
    variants = [
        _bound_variant(db, x.settings.storage_root, suffix=f"COV{index}")[0]
        for index in range(1, 6)
    ]
    variants[4].labour_requirements = []
    # Keep one target deliberately bounded to a single component requirement so
    # the complete bottom-up coverage transition can be proven independently.
    variants[4].labour_requirements = []
    release = _publish(
        db,
        actor=reviewer,
        storage_root=x.settings.storage_root,
        version="TECH-COVERAGE-2026.09",
    )

    old_b = _reviewed_source(db, x, owner, reviewer, "firefly_system_prices", 100.0)
    stale = _save_mapping(
        db,
        x,
        reviewer,
        release,
        *old_b,
        2,
        "mapped",
        selected=variants[1],
    )
    current_b = _reviewed_source(db, x, owner, reviewer, "firefly_system_prices", 200.0)
    direct = _save_mapping(
        db,
        x,
        reviewer,
        release,
        *current_b,
        2,
        "mapped",
        selected=variants[0],
    )
    ambiguous = _save_mapping(
        db,
        x,
        reviewer,
        release,
        *current_b,
        3,
        "ambiguous",
        candidates=(variants[2], variants[3]),
    )

    source_a, profile_a, profile_a_hash, decision_a_hash = _reviewed_source(
        db, x, owner, reviewer, "general_pricelist", 300.0
    )
    observation_preview = pricing.preview_row_observation(
        db,
        reviewer,
        x.ids[2],
        source_a.id,
        profile_a["profile_id"],
        2,
        "material",
        "SYNTHETIC-MATERIAL",
        "confirmed",
        "The exact Dataset A row was reviewed as material evidence.",
        [],
        settings=x.settings,
    )
    observation = pricing.save_row_observation(
        db,
        reviewer,
        x.ids[2],
        source_a.id,
        profile_a["profile_id"],
        2,
        "material",
        "SYNTHETIC-MATERIAL",
        "confirmed",
        "The exact Dataset A row was reviewed as material evidence.",
        [],
        profile_a_hash,
        decision_a_hash,
        observation_preview["definition"]["row"]["sha256"],
        observation_preview["preview_hash"],
        settings=x.settings,
    )
    db.commit()
    return owner, foreign, reviewer, variants, release, stale, direct, ambiguous, observation


def _counts(db):
    return {
        model.__tablename__: db.scalar(select(func.count()).select_from(model))
        for model in (
            AuditEvent,
            DraftPricingEvaluationRoster,
            DraftPricingRowObservation,
            DraftPricingSystemMapping,
            Estimate,
            LibraryRelease,
            PricingLibraryRecord,
            TechnicalVariant,
        )
    }


def test_conflicting_dataset_b_evidence_blocks_complete_bottom_up_recipe() -> None:
    requirements = [{"id": "requirement-1"}]
    links = [
        {
            "requirement_id": "requirement-1",
            "current": True,
            "status": "linked",
            "evidence_state": "confirmed",
            "unresolved_fields": [],
        }
    ]
    stale_mapping = {
        "selected_variant_id": "target-1",
        "candidate_variant_ids": [],
        "current": False,
        "status": "mapped",
    }
    ambiguous_mapping = {
        "selected_variant_id": None,
        "candidate_variant_ids": ["target-1", "target-2"],
        "current": True,
        "status": "ambiguous",
    }
    assert (
        coverage._target_status("target-1", [stale_mapping], requirements, links)[0]
        == "stale_input"
    )
    assert (
        coverage._target_status("target-1", [ambiguous_mapping], requirements, links)[0]
        == "review_needed"
    )


def test_bottom_up_requires_every_frozen_recipe_requirement() -> None:
    requirements = [{"id": "requirement-1"}, {"id": "requirement-2"}]
    first = {
        "requirement_id": "requirement-1",
        "current": True,
        "status": "linked",
        "evidence_state": "confirmed",
        "unresolved_fields": [],
    }
    second = {**first, "requirement_id": "requirement-2"}
    assert coverage._target_status("target-1", [], requirements, [first])[0] == "review_needed"
    result = coverage._target_status("target-1", [], requirements, [first, second])
    assert result[0] == "bottom_up_a_support"
    assert result[1] == "component_activity_recipe"


def test_coverage_represents_every_target_and_remains_read_only(pdf_setup):
    x = pdf_setup
    with x.factory() as db:
        owner, foreign, reviewer, variants, release, stale, direct, ambiguous, observation = (
            _prepared(db, x)
        )
        before = _counts(db)

        with pytest.raises(scope.DraftScopeError) as hidden:
            coverage.preview_coverage(db, foreign, x.ids[2], release.id, settings=x.settings)
        assert hidden.value.status_code == 404
        with pytest.raises(scope.DraftScopeError) as denied:
            coverage.preview_coverage(db, owner, x.ids[2], release.id, settings=x.settings)
        assert denied.value.status_code == 403

        result = coverage.preview_coverage(db, reviewer, x.ids[2], release.id, settings=x.settings)
        repeated = coverage.preview_coverage(
            db, reviewer, x.ids[2], release.id, settings=x.settings
        )
        assert result == repeated
        assert result["coverage_sha256"] == digest(
            {key: value for key, value in result.items() if key != "coverage_sha256"}
        )
        by_variant = {item["technical_target"]["variant_id"]: item for item in result["targets"]}
        assert list(by_variant) == [item.variant_id for item in variants]
        assert by_variant[variants[0].variant_id]["status"] == "direct_b_support"
        assert by_variant[variants[0].variant_id]["primary_method"] == "direct_observed_b"
        assert by_variant[variants[1].variant_id]["status"] == "stale_input"
        assert by_variant[variants[2].variant_id]["status"] == "review_needed"
        assert by_variant[variants[3].variant_id]["status"] == "review_needed"
        assert by_variant[variants[4].variant_id]["status"] == "insufficient_evidence"
        assert result["summary"]["status_counts"] == {
            "direct_b_support": 1,
            "bottom_up_a_support": 0,
            "review_needed": 2,
            "stale_input": 1,
            "insufficient_evidence": 1,
        }
        assert result["summary"]["current_unlinked_dataset_a_observations"] == 1
        assert (
            result["unlinked_dataset_a_observations"][0]["observation_id"]
            == (observation["observation_id"])
        )
        assert result["unlinked_dataset_a_observations"][0]["target_link"] is None
        assert (
            by_variant[variants[0].variant_id]["dependencies"]["dataset_b_mappings"][0][
                "mapping_id"
            ]
            == direct["mapping_id"]
        )
        assert (
            by_variant[variants[1].variant_id]["dependencies"]["dataset_b_mappings"][0][
                "mapping_id"
            ]
            == stale["mapping_id"]
        )
        assert {
            item["mapping_id"]
            for item in by_variant[variants[2].variant_id]["dependencies"]["dataset_b_mappings"]
        } == {ambiguous["mapping_id"]}
        assert result["effects"] == coverage.EFFECTS
        assert _counts(db) == before

        stored = db.get(DraftPricingSystemMapping, direct["mapping_id"])
        stored.mapping_json += " "
        db.flush()
        with pytest.raises(scope.DraftScopeError, match="PRICING_SYSTEM_MAPPING_INTEGRITY_FAILED"):
            coverage.preview_coverage(db, reviewer, x.ids[2], release.id, settings=x.settings)


def test_coverage_ui_preview_and_exact_json(pdf_app, monkeypatch):
    x = pdf_app
    monkeypatch.setattr("classifire.draft_pricing_ui.get_settings", lambda: x.settings)
    monkeypatch.setattr("classifire.draft_estimate_ui.get_settings", lambda: x.settings)
    x.app.include_router(estimate_router)
    x.app.include_router(pricing_router)
    with x.factory() as db:
        owner = db.get(User, x.ids[0])
        scope.save_revision(db, owner, x.ids[2], 1, sample_payload())
        estimate = estimates.create_estimate(db, owner, x.ids[2], 2)
        _, _, _, _, release, _, _, _, _ = _prepared(db, x)
        base = f"/scopes/{x.ids[2]}/estimates/{estimate.id}/pricing"
        release_id = release.id
        before = _counts(db)

    with TestClient(x.app) as owner_client, TestClient(x.app) as admin_client:
        _login(owner_client)
        _login(admin_client, "admin")
        owner_page = owner_client.get(base)
        assert owner_page.status_code == 200
        assert "authorised pricing reviewer" in owner_page.text
        admin_page = admin_client.get(base)
        assert admin_page.status_code == 200
        assert "Preview pricing coverage for every target" in admin_page.text
        form = {
            "csrf_token": _csrf(admin_page.text),
            "technical_release_id": release_id,
        }
        assert (
            owner_client.post(
                base + "/coverage/preview",
                data={**form, "csrf_token": _csrf(owner_page.text)},
            ).status_code
            == 403
        )
        assert (
            admin_client.post(
                base + "/coverage/preview", data={**form, "unexpected": "write"}
            ).status_code
            == 422
        )
        preview = admin_client.post(base + "/coverage/preview", data=form)
        assert preview.status_code == 200, preview.text
        assert "Coverage preview" in preview.text
        assert "No write has occurred" in preview.text
        assert "Direct B:</strong> 1" in preview.text
        assert "Bottom-up A:</strong> 0" in preview.text
        assert "Insufficient evidence" in preview.text
        assert "price withheld" in preview.text
        assert len(re.findall(r"COV[1-5]", preview.text)) >= 5
        path = re.search(r'href="([^"]+/coverage\.json\?[^\"]+)"', preview.text)
        assert path is not None
        downloaded = admin_client.get(path.group(1).replace("&amp;", "&"))
        assert downloaded.status_code == 200
        assert downloaded.headers["x-content-type-options"] == "nosniff"
        assert downloaded.headers["cache-control"] == "no-store"
        assert canonical(downloaded.json()) == downloaded.content
        assert downloaded.json()["coverage_sha256"]
        assert downloaded.json()["effects"]["estimate_changed"] is False

    with x.factory() as db:
        assert _counts(db) == before
