from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_pdf_intake import pdf_setup as _pdf_setup
from test_draft_pdf_ui import pdf_app as _pdf_app
from test_draft_pricing_coverage import _prepared
from test_draft_scope import sample_payload
from test_draft_scope_ui import _csrf, _login
from test_draft_scope_ui import scope_password_hash as _password_hash
from test_shared_file_containment import postgresql_session_factory as _postgres_fixture

from classifire.draft_estimate_ui import router as estimate_router
from classifire.draft_pricing_ui import router as pricing_router
from classifire.models import DraftPricingRecipeLink, DraftPricingRowObservation, User
from classifire.services import draft_estimates as estimates
from classifire.services import draft_pricing_coverage as coverage
from classifire.services import draft_pricing_recipes as recipes
from classifire.services import draft_scope as scope
from classifire.services.draft_system_match_contract import canonical

pdf_setup = _pdf_setup
pdf_app = _pdf_app
scope_password_hash = _password_hash
postgresql_session_factory = _postgres_fixture


def _inputs(db, x):
    owner, foreign, reviewer, variants, release, *_rest, observation = _prepared(db, x)
    target = variants[4]
    record = next(item for item in release.source_manifest["records"] if item["id"] == target.id)
    requirement = record["recipe_snapshot"]["requirements"][0]
    return owner, foreign, reviewer, target, release, observation, requirement


def test_recipe_link_preview_save_reopen_download_and_replay(pdf_setup):
    x = pdf_setup
    with x.factory() as db:
        owner, foreign, reviewer, target, release, observation, requirement = _inputs(db, x)
        before = db.scalar(select(func.count()).select_from(DraftPricingRecipeLink))
        kwargs = {
            "status": "linked",
            "unit": "each",
            "quantity_basis": "One reviewed unit per repair opening",
            "yield_basis": "One source unit",
            "productivity_basis": None,
            "recovery_boundary": "Material supply only; installation is separate",
            "evidence_state": "confirmed",
            "review_reason": "The exact frozen component and Dataset A row were reviewed.",
            "unresolved_fields": [],
            "settings": x.settings,
        }
        preview = recipes.preview_recipe_link(
            db,
            reviewer,
            x.ids[2],
            release.id,
            target.id,
            requirement["id"],
            [observation["observation_id"]],
            **kwargs,
        )
        assert preview["database_write_performed"] is False
        assert db.scalar(select(func.count()).select_from(DraftPricingRecipeLink)) == before
        for actor, expected in ((foreign, 404), (owner, 403)):
            with pytest.raises(scope.DraftScopeError) as denied:
                recipes.preview_recipe_link(
                    db,
                    actor,
                    x.ids[2],
                    release.id,
                    target.id,
                    requirement["id"],
                    [observation["observation_id"]],
                    **kwargs,
                )
            assert denied.value.status_code == expected
        saved = recipes.save_recipe_link(
            db,
            reviewer,
            x.ids[2],
            release.id,
            target.id,
            requirement["id"],
            [observation["observation_id"]],
            expected_release_sha256=preview["technical_release_sha256"],
            expected_variant_snapshot_sha256=preview["technical_variant_snapshot_sha256"],
            expected_recipe_snapshot_sha256=preview["recipe_snapshot_sha256"],
            expected_preview_hash=preview["preview_hash"],
            **kwargs,
        )
        db.commit()
        links = recipes.list_recipe_links(
            db,
            reviewer,
            x.ids[2],
            settings=x.settings,
            release_id=release.id,
            variant_id=target.id,
        )
        assert len(links) == 1
        assert links[0]["current"] is True
        assert links[0]["value"] == saved
        assert (
            json.loads(recipes.recipe_link_bytes(db, reviewer, x.ids[2], saved["link_id"])) == saved
        )
        result = coverage.preview_coverage(db, reviewer, x.ids[2], release.id, settings=x.settings)
        target_coverage = next(
            item for item in result["targets"] if item["technical_target"]["id"] == target.id
        )
        assert target_coverage["status"] == "bottom_up_a_support"
        assert target_coverage["primary_method"] == "component_activity_recipe"
        assert target_coverage["dependencies"]["recipe_links"][0]["link_id"] == saved["link_id"]
        assert result["summary"]["current_unlinked_dataset_a_observations"] == 0
        with pytest.raises(scope.DraftScopeError, match="PRICING_RECIPE_LINK_REPLAYED"):
            recipes.save_recipe_link(
                db,
                reviewer,
                x.ids[2],
                release.id,
                target.id,
                requirement["id"],
                [observation["observation_id"]],
                expected_release_sha256=preview["technical_release_sha256"],
                expected_variant_snapshot_sha256=preview["technical_variant_snapshot_sha256"],
                expected_recipe_snapshot_sha256=preview["recipe_snapshot_sha256"],
                expected_preview_hash=preview["preview_hash"],
                **kwargs,
            )


def test_recipe_link_integrity_and_changed_basis_fail_closed(pdf_setup):
    x = pdf_setup
    with x.factory() as db:
        _, _, reviewer, target, release, observation, requirement = _inputs(db, x)
        kwargs = {
            "status": "unresolved",
            "unit": None,
            "quantity_basis": None,
            "yield_basis": None,
            "productivity_basis": None,
            "recovery_boundary": None,
            "evidence_state": "unresolved",
            "review_reason": "No compatible Dataset A row.",
            "unresolved_fields": ["observation", "unit"],
            "settings": x.settings,
        }
        preview = recipes.preview_recipe_link(
            db, reviewer, x.ids[2], release.id, target.id, requirement["id"], [], **kwargs
        )
        with pytest.raises(scope.DraftScopeError, match="PRICING_RECIPE_BASIS_CHANGED"):
            recipes.save_recipe_link(
                db,
                reviewer,
                x.ids[2],
                release.id,
                target.id,
                requirement["id"],
                [],
                expected_release_sha256="0" * 64,
                expected_variant_snapshot_sha256=preview["technical_variant_snapshot_sha256"],
                expected_recipe_snapshot_sha256=preview["recipe_snapshot_sha256"],
                expected_preview_hash=preview["preview_hash"],
                **kwargs,
            )
        saved = recipes.save_recipe_link(
            db,
            reviewer,
            x.ids[2],
            release.id,
            target.id,
            requirement["id"],
            [],
            expected_release_sha256=preview["technical_release_sha256"],
            expected_variant_snapshot_sha256=preview["technical_variant_snapshot_sha256"],
            expected_recipe_snapshot_sha256=preview["recipe_snapshot_sha256"],
            expected_preview_hash=preview["preview_hash"],
            **kwargs,
        )
        db.commit()
        row = db.get(DraftPricingRecipeLink, saved["link_id"])
        created = row.created_at
        row.created_at = created + timedelta(seconds=1)
        db.flush()
        with pytest.raises(scope.DraftScopeError, match="PRICING_RECIPE_LINK_INTEGRITY_FAILED"):
            recipes.recipe_link_bytes(db, reviewer, x.ids[2], row.id)
        row.created_at = created
        row.link_json += " "
        db.flush()
        with pytest.raises(scope.DraftScopeError, match="PRICING_RECIPE_LINK_INTEGRITY_FAILED"):
            recipes.recipe_link_bytes(db, reviewer, x.ids[2], row.id)


def test_v3_release_remains_readable_but_cannot_offer_recipe_review(pdf_setup):
    x = pdf_setup
    with x.factory() as db:
        _, _, reviewer, target, release, *_ = _inputs(db, x)
        manifest = copy.deepcopy(release.source_manifest)
        manifest["schema"] = "CLASSIFIRE-TECHNICAL-LIBRARY-RELEASE-v3"
        for record in manifest["records"]:
            record.pop("recipe_snapshot")
        release.source_manifest = manifest
        release.release_hash = hashlib.sha256(canonical(manifest)).hexdigest()
        db.flush()
        result = coverage.preview_coverage(db, reviewer, x.ids[2], release.id, settings=x.settings)
        selected = next(
            item for item in result["targets"] if item["technical_target"]["id"] == target.id
        )
        assert selected["technical_target"]["recipe_available"] is False
        with pytest.raises(scope.DraftScopeError, match="PRICING_RECIPE_SNAPSHOT_REQUIRED"):
            recipes.recipe_review_context(
                db, reviewer, x.ids[2], release.id, target.id, settings=x.settings
            )


@pytest.mark.parametrize("schema,remove_recipe", [
    ("CLASSIFIRE-TECHNICAL-LIBRARY-RELEASE-v4", True),
    ("CLASSIFIRE-TECHNICAL-LIBRARY-RELEASE-v3", False),
])
def test_recipe_presence_must_match_release_version(pdf_setup, schema, remove_recipe):
    x = pdf_setup
    with x.factory() as db:
        _, _, reviewer, _, release, *_ = _inputs(db, x)
        manifest = copy.deepcopy(release.source_manifest)
        manifest["schema"] = schema
        if remove_recipe:
            for record in manifest["records"]:
                record.pop("recipe_snapshot")
        release.source_manifest = manifest
        release.release_hash = hashlib.sha256(canonical(manifest)).hexdigest()
        db.flush()
        with pytest.raises(scope.DraftScopeError, match="PRICING_TECHNICAL_RELEASE_INVALID"):
            coverage.preview_coverage(db, reviewer, x.ids[2], release.id, settings=x.settings)


def test_recipe_review_context_fails_closed_for_corrupt_observation(pdf_setup):
    x = pdf_setup
    with x.factory() as db:
        _, _, reviewer, target, release, observation, _ = _inputs(db, x)
        stored = db.get(DraftPricingRowObservation, observation["observation_id"])
        stored.observation_json += " "
        db.flush()
        with pytest.raises(scope.DraftScopeError, match="PRICING_ROW_OBSERVATION_INTEGRITY_FAILED"):
            recipes.recipe_review_context(
                db, reviewer, x.ids[2], release.id, target.id, settings=x.settings
            )


def test_recipe_review_ui_preview_save_reopen_and_download(pdf_app, monkeypatch):
    x = pdf_app
    monkeypatch.setattr("classifire.draft_pricing_ui.get_settings", lambda: x.settings)
    monkeypatch.setattr("classifire.draft_estimate_ui.get_settings", lambda: x.settings)
    x.app.include_router(estimate_router)
    x.app.include_router(pricing_router)
    with x.factory() as db:
        owner = db.get(User, x.ids[0])
        scope.save_revision(db, owner, x.ids[2], 1, sample_payload())
        estimate = estimates.create_estimate(db, owner, x.ids[2], 2)
        _, _, _, target, release, observation, requirement = _inputs(db, x)
        base = (
            f"/scopes/{x.ids[2]}/estimates/{estimate.id}/pricing/recipes/{release.id}/{target.id}"
        )
        observation_id = observation["observation_id"]
    with TestClient(x.app) as client:
        _login(client, "admin")
        page = client.get(base)
        assert page.status_code == 200, page.text
        assert "Component and activity recipe review" in page.text
        assert requirement["label"] in page.text
        assert requirement["path"] in page.text
        assert requirement["source_value_sha256"] in page.text
        assert "cartridge" in page.text
        form = {
            "csrf_token": _csrf(page.text),
            "requirement_id": requirement["id"],
            "observation_id_1": observation_id,
            "observation_id_2": "",
            "observation_id_3": "",
            "status": "linked",
            "unit": "each",
            "quantity_basis": "One reviewed unit per repair opening",
            "yield_basis": "One source unit",
            "productivity_basis": "",
            "recovery_boundary": "Material supply only",
            "evidence_state": "confirmed",
            "review_reason": "The exact UI evidence was reviewed.",
            "unresolved_fields": "",
        }
        assert client.post(base + "/preview", data={**form, "unexpected": "x"}).status_code == 422
        preview = client.post(base + "/preview", data=form)
        assert preview.status_code == 200, preview.text
        assert "No write has occurred" in preview.text
        assert observation_id in preview.text
        assert hashlib.sha256(canonical(observation)).hexdigest() in preview.text
        assert observation["definition"]["interpretation"]["normalized_reference"] in preview.text
        save_form = {key: value for key, value in form.items() if key != "csrf_token"}
        save_form["csrf_token"] = _csrf(preview.text)
        for name in (
            "technical_release_sha256",
            "technical_variant_snapshot_sha256",
            "recipe_snapshot_sha256",
            "preview_hash",
        ):
            match = re.search(rf'name="{name}" value="([^"]+)"', preview.text)
            assert match is not None
            save_form[name] = match.group(1)
        saved = client.post(base + "/links", data=save_form, follow_redirects=True)
        assert saved.status_code == 200, saved.text
        assert "Immutable review history" in saved.text
        path = re.search(r'href="([^"]+/recipe-links/[^"]+/download)"', saved.text)
        assert path is not None
        downloaded = client.get(path.group(1))
        assert downloaded.status_code == 200
        assert downloaded.headers["x-content-type-options"] == "nosniff"
        assert downloaded.json()["definition"]["requirement"]["id"] == requirement["id"]
