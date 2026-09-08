import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_pdf_intake import pdf_setup as _pdf_setup
from test_draft_pdf_ui import pdf_app as _pdf_app
from test_draft_pricing_recipes import _inputs
from test_draft_scope import sample_payload
from test_draft_scope_ui import _csrf, _login
from test_draft_scope_ui import scope_password_hash as _password_hash
from test_shared_file_containment import postgresql_session_factory as _postgres_fixture

from classifire.draft_estimate_ui import router as estimate_router
from classifire.draft_pricing_ui import router as pricing_router
from classifire.models import AuditEvent, DraftPricingRecipeLink, Estimate
from classifire.services import draft_estimates as estimates
from classifire.services import draft_pricing_bottom_up as bottom_up
from classifire.services import draft_pricing_recipes as recipes
from classifire.services import draft_scope as scope
from classifire.services.draft_system_match_contract import canonical, digest

pdf_setup = _pdf_setup
pdf_app = _pdf_app
scope_password_hash = _password_hash
postgresql_session_factory = _postgres_fixture


def _linked(db, x):
    owner, foreign, reviewer, target, release, observation, requirement = _inputs(db, x)
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
    db.commit()
    return owner, foreign, reviewer, target, release, requirement


def _counts(db):
    return {
        model.__tablename__: db.scalar(select(func.count()).select_from(model))
        for model in (AuditEvent, DraftPricingRecipeLink, Estimate)
    }


def test_bottom_up_calculates_exact_sell_amount_and_remains_read_only(pdf_setup):
    x = pdf_setup
    with x.factory() as db:
        owner, foreign, reviewer, target, release, requirement = _linked(db, x)
        before = _counts(db)
        for actor, expected in ((foreign, 404), (owner, 403)):
            with pytest.raises(scope.DraftScopeError) as denied:
                bottom_up.preview_bottom_up(
                    db,
                    actor,
                    x.ids[2],
                    release.id,
                    target.id,
                    {requirement["id"]: "2"},
                    settings=x.settings,
                )
            assert denied.value.status_code == expected

        withheld = bottom_up.preview_bottom_up(
            db, reviewer, x.ids[2], release.id, target.id, {}, settings=x.settings
        )
        assert withheld["status"] == "withheld"
        assert withheld["total_ex_tax"] is None
        assert withheld["effects"]["price_calculated"] is False
        assert withheld["lines"][0]["calculation"]["withheld_reasons"] == [
            "quantity_required"
        ]

        result = bottom_up.preview_bottom_up(
            db,
            reviewer,
            x.ids[2],
            release.id,
            target.id,
            {requirement["id"]: "2"},
            settings=x.settings,
        )
        assert result["status"] == "calculated"
        assert result["total_ex_tax"] == "600.00"
        assert result["effects"]["price_calculated"] is True
        assert result["lines"][0]["calculation"] == {
            "status": "calculated",
            "quantity": "2",
            "unit": "each",
            "unit_rate": "300",
            "currency": "AUD",
            "price_meaning": "sell_price",
            "tax_basis": "excluded",
            "formula": "quantity_x_unit_rate_round_half_up_2dp",
            "amount_ex_tax": "600.00",
            "withheld_reasons": [],
        }
        assert result["proposal_sha256"] == digest(
            {key: value for key, value in result.items() if key != "proposal_sha256"}
        )
        assert canonical(result) == canonical(
            bottom_up.preview_bottom_up(
                db,
                reviewer,
                x.ids[2],
                release.id,
                target.id,
                {requirement["id"]: "2.0"},
                settings=x.settings,
            )
        )
        assert _counts(db) == before

        with pytest.raises(scope.DraftScopeError, match="BOTTOM_UP_QUANTITY_INVALID"):
            bottom_up.preview_bottom_up(
                db,
                reviewer,
                x.ids[2],
                release.id,
                target.id,
                {requirement["id"]: "1.5"},
                settings=x.settings,
            )


def test_bottom_up_ui_calculates_and_downloads_exact_json(pdf_app, monkeypatch):
    x = pdf_app
    monkeypatch.setattr("classifire.draft_pricing_ui.get_settings", lambda: x.settings)
    monkeypatch.setattr("classifire.draft_estimate_ui.get_settings", lambda: x.settings)
    x.app.include_router(estimate_router)
    x.app.include_router(pricing_router)
    with x.factory() as db:
        owner, _, reviewer, target, release, requirement = _linked(db, x)
        scope.save_revision(db, owner, x.ids[2], 1, sample_payload())
        estimate = estimates.create_estimate(db, owner, x.ids[2], 2)
        db.commit()
        path = (
            f"/scopes/{x.ids[2]}/estimates/{estimate.id}"
            f"/pricing-proposals/bottom-up/{release.id}/{target.id}"
        )
        before = _counts(db)
        expected_preview = bottom_up.preview_bottom_up(
            db,
            reviewer,
            x.ids[2],
            release.id,
            target.id,
            {requirement["id"]: "2"},
            settings=x.settings,
        )

    with TestClient(x.app) as owner_client, TestClient(x.app) as admin_client:
        _login(owner_client)
        _login(admin_client, "admin")
        assert owner_client.get(path).status_code == 403
        page = admin_client.get(path)
        assert page.status_code == 200, page.text
        assert "Bottom-up proposal preview" in page.text
        assert "does not guess from the recipe notes" in page.text
        assert re.search(r'id="quantity-1"[^>]*\brequired\b', page.text) is None
        withheld = admin_client.post(
            path,
            data={
                "csrf_token": _csrf(page.text),
                f"quantity__{requirement['id']}": "",
            },
        )
        assert withheld.status_code == 200, withheld.text
        assert "Result: Withheld" in withheld.text
        assert "quantity required" in withheld.text
        form = {
            "csrf_token": _csrf(withheld.text),
            f"quantity__{requirement['id']}": "2",
        }
        preview = admin_client.post(path, data=form)
        assert preview.status_code == 200, preview.text
        assert "Total excluding GST: $600.00 AUD" in preview.text
        assert "2 each" in preview.text
        assert "Exact proposal dependencies" in preview.text
        assert expected_preview["coverage_sha256"] in preview.text
        assert expected_preview["technical_release"]["id"] in preview.text
        assert expected_preview["technical_release"]["sha256"] in preview.text
        assert expected_preview["technical_target"]["id"] in preview.text
        assert expected_preview["technical_target"]["snapshot_sha256"] in preview.text
        assert expected_preview["technical_target"]["release_record_sha256"] in preview.text
        assert expected_preview["lines"][0]["recipe_link"]["id"] in preview.text
        assert expected_preview["lines"][0]["recipe_link"]["sha256"] in preview.text
        assert expected_preview["lines"][0]["observation"]["id"] in preview.text
        assert expected_preview["lines"][0]["observation"]["sha256"] in preview.text
        expected = re.search(
            r'name="expected_proposal_sha256" value="([a-f0-9]{64})"', preview.text
        )
        assert expected is not None
        downloaded = admin_client.post(
            path.replace("/bottom-up/", "/bottom-up-download/"),
            data={
                "csrf_token": _csrf(preview.text),
                "expected_proposal_sha256": expected.group(1),
                f"quantity__{requirement['id']}": "2",
            },
        )
        assert downloaded.status_code == 200
        assert canonical(downloaded.json()) == downloaded.content
        assert downloaded.json()["total_ex_tax"] == "600.00"
        assert downloaded.headers["x-content-type-options"] == "nosniff"
        assert admin_client.post(
            path.replace("/bottom-up/", "/bottom-up-download/"),
            data={
                "csrf_token": _csrf(preview.text),
                "expected_proposal_sha256": "0" * 64,
                f"quantity__{requirement['id']}": "2",
            },
        ).status_code == 409

    with x.factory() as db:
        assert _counts(db) == before
