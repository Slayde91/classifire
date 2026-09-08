from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_pdf_intake import pdf_setup as _pdf_setup
from test_draft_pdf_ui import pdf_app as _pdf_app
from test_draft_pricing_bottom_up import _linked
from test_draft_scope import sample_payload
from test_draft_scope_ui import _csrf, _login
from test_draft_scope_ui import scope_password_hash as _password_hash
from test_shared_file_containment import postgresql_session_factory as _postgres_fixture

from classifire.draft_estimate_ui import router as estimate_router
from classifire.draft_pricing_ui import router as pricing_router
from classifire.models import DraftPricingQuantityBasis
from classifire.services import draft_estimates as estimates
from classifire.services import draft_pricing_bottom_up as bottom_up
from classifire.services import draft_pricing_quantities as quantities
from classifire.services import draft_scope as scope
from classifire.services.draft_system_match_contract import canonical

pdf_setup = _pdf_setup
pdf_app = _pdf_app
scope_password_hash = _password_hash
postgresql_session_factory = _postgres_fixture


def _save_scope(db, owner, draft_id: str, payload: dict) -> dict:
    current = scope.get_draft(db, owner, draft_id).latest_revision
    return scope.save_revision(db, owner, draft_id, current, payload)


def test_quantity_preview_save_history_staleness_and_governed_calculation(pdf_setup):
    x = pdf_setup
    with x.factory() as db:
        owner, foreign, reviewer, target, release, requirement = _linked(db, x)
        envelope = _save_scope(db, owner, x.ids[2], sample_payload())
        service = envelope["content"]["services"][0]
        before = db.scalar(select(func.count()).select_from(DraftPricingQuantityBasis))
        args = (
            x.ids[2],
            release.id,
            target.id,
            requirement["id"],
            envelope["revision"],
            str(service["id"]),
            "This saved Scope service is the project quantity for this requirement.",
        )
        for actor, status in ((foreign, 404), (owner, 403)):
            with pytest.raises(scope.DraftScopeError) as denied:
                quantities.preview_quantity_basis(db, actor, *args, settings=x.settings)
            assert denied.value.status_code == status
        preview = quantities.preview_quantity_basis(db, reviewer, *args, settings=x.settings)
        assert preview["database_write_performed"] is False
        assert db.scalar(select(func.count()).select_from(DraftPricingQuantityBasis)) == before
        with pytest.raises(scope.DraftScopeError, match="PRICING_QUANTITY_BASIS_CHANGED"):
            quantities.save_quantity_basis(
                db,
                reviewer,
                *args,
                expected_scope_sha256="0" * 64,
                expected_recipe_link_sha256=preview["recipe_link_sha256"],
                expected_preview_hash=preview["preview_hash"],
                settings=x.settings,
            )
        assert db.scalar(select(func.count()).select_from(DraftPricingQuantityBasis)) == before
        saved = quantities.save_quantity_basis(
            db,
            reviewer,
            *args,
            expected_scope_sha256=preview["scope_sha256"],
            expected_recipe_link_sha256=preview["recipe_link_sha256"],
            expected_preview_hash=preview["preview_hash"],
            settings=x.settings,
        )
        db.commit()
        history = quantities.list_quantity_bases(
            db,
            reviewer,
            x.ids[2],
            settings=x.settings,
            release_id=release.id,
            target_id=target.id,
        )
        assert len(history) == 1
        assert history[0]["current"] is True
        assert history[0]["value"] == saved
        assert (
            json.loads(quantities.quantity_basis_bytes(db, reviewer, x.ids[2], saved["basis_id"]))
            == saved
        )
        result = bottom_up.preview_bottom_up(
            db, reviewer, x.ids[2], release.id, target.id, settings=x.settings
        )
        assert result["total_ex_tax"] == "600.00"
        assert result["lines"][0]["quantity_basis"]["id"] == saved["basis_id"]
        with pytest.raises(scope.DraftScopeError, match="PRICING_QUANTITY_BASIS_REPLAYED"):
            quantities.save_quantity_basis(
                db,
                reviewer,
                *args,
                expected_scope_sha256=preview["scope_sha256"],
                expected_recipe_link_sha256=preview["recipe_link_sha256"],
                expected_preview_hash=preview["preview_hash"],
                settings=x.settings,
            )
        changed = sample_payload()
        changed["services"][0]["quantity"] = "3"
        _save_scope(db, owner, x.ids[2], changed)
        db.commit()
        stale = quantities.list_quantity_bases(
            db,
            reviewer,
            x.ids[2],
            settings=x.settings,
            release_id=release.id,
            target_id=target.id,
        )
        assert stale[0]["current"] is False
        withheld = bottom_up.preview_bottom_up(
            db, reviewer, x.ids[2], release.id, target.id, settings=x.settings
        )
        assert withheld["status"] == "withheld"
        assert (
            "project_quantity_basis_required"
            in (withheld["lines"][0]["calculation"]["withheld_reasons"])
        )


def test_quantity_rejects_missing_and_unit_incompatible_scope_values(pdf_setup):
    x = pdf_setup
    with x.factory() as db:
        owner, _, reviewer, target, release, requirement = _linked(db, x)
        envelope = _save_scope(db, owner, x.ids[2], sample_payload())
        second_service_id = str(envelope["content"]["services"][1]["id"])
        with pytest.raises(scope.DraftScopeError, match="PRICING_QUANTITY_SCOPE_VALUE_REQUIRED"):
            quantities.preview_quantity_basis(
                db,
                reviewer,
                x.ids[2],
                release.id,
                target.id,
                requirement["id"],
                envelope["revision"],
                second_service_id,
                "Missing quantity must fail.",
                settings=x.settings,
            )
        payload = sample_payload()
        payload["services"][1]["quantity"] = "2"
        payload["services"][1]["unit"] = "m"
        envelope = _save_scope(db, owner, x.ids[2], payload)
        with pytest.raises(scope.DraftScopeError, match="PRICING_QUANTITY_UNIT_MISMATCH"):
            quantities.preview_quantity_basis(
                db,
                reviewer,
                x.ids[2],
                release.id,
                target.id,
                requirement["id"],
                envelope["revision"],
                second_service_id,
                "A metres quantity cannot satisfy an each requirement.",
                settings=x.settings,
            )


def test_quantity_ui_preview_save_restart_reopen_and_exact_download(pdf_app, monkeypatch):
    x = pdf_app
    monkeypatch.setattr("classifire.draft_pricing_ui.get_settings", lambda: x.settings)
    monkeypatch.setattr("classifire.draft_estimate_ui.get_settings", lambda: x.settings)
    x.app.include_router(estimate_router)
    x.app.include_router(pricing_router)
    with x.factory() as db:
        owner, _, _, target, release, requirement = _linked(db, x)
        envelope = _save_scope(db, owner, x.ids[2], sample_payload())
        estimate = estimates.create_estimate(db, owner, x.ids[2], envelope["revision"])
        service = envelope["content"]["services"][0]
        db.commit()
        path = (
            f"/scopes/{x.ids[2]}/estimates/{estimate.id}"
            f"/pricing-proposals/bottom-up/{release.id}/{target.id}"
        )

    with TestClient(x.app) as client:
        _login(client, "admin")
        page = client.get(path)
        assert page.status_code == 200
        assert "No current compatible project quantity is saved" in page.text
        preview = client.post(
            path + "/quantity-bases/preview",
            data={
                "csrf_token": _csrf(page.text),
                "requirement_id": requirement["id"],
                "scope_revision": str(envelope["revision"]),
                "scope_service_id": str(service["id"]),
                "review_reason": "The saved Scope service is the project quantity.",
            },
        )
        assert preview.status_code == 200, preview.text
        assert "No write has occurred" in preview.text
        with x.factory() as db:
            assert db.scalar(select(func.count()).select_from(DraftPricingQuantityBasis)) == 0
        hidden = {
            name: re.search(rf'name="{name}" value="([^"]*)"', preview.text).group(1)
            for name in (
                "requirement_id",
                "scope_revision",
                "scope_service_id",
                "review_reason",
                "scope_sha256",
                "recipe_link_sha256",
                "preview_hash",
            )
        }
        saved = client.post(
            path + "/quantity-bases",
            data={"csrf_token": _csrf(preview.text), **hidden},
            follow_redirects=False,
        )
        assert saved.status_code == 303

    with TestClient(x.app) as restarted:
        _login(restarted, "admin")
        page = restarted.get(path)
        assert page.status_code == 200
        assert "Current project quantity:" in page.text
        assert "Total excluding GST: $600.00 AUD" in page.text
        basis_id = re.search(
            r'/pricing-proposals/quantity-bases/([^/"]+)/download', page.text
        ).group(1)
        exact = restarted.get(
            path.split("/pricing-proposals/")[0]
            + f"/pricing-proposals/quantity-bases/{basis_id}/download"
        )
        assert exact.status_code == 200
        assert canonical(exact.json()) == exact.content
        expected = re.search(
            r'name="expected_proposal_sha256" value="([a-f0-9]{64})"', page.text
        ).group(1)
        proposal = restarted.post(
            path.replace("/bottom-up/", "/bottom-up-download/"),
            data={
                "csrf_token": _csrf(page.text),
                "expected_proposal_sha256": expected,
            },
        )
        assert proposal.status_code == 200
        assert proposal.json()["total_ex_tax"] == "600.00"
        assert canonical(proposal.json()) == proposal.content
