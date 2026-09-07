from __future__ import annotations

import hashlib
import io
import re
from datetime import UTC, datetime, timedelta

import pytest
import xlsxwriter
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_estimates import add_payload
from test_draft_pdf_intake import pdf_setup as _pdf_setup
from test_draft_pdf_ui import pdf_app as _pdf_app
from test_draft_pricing_profiles import sparse_mapping
from test_draft_scope import sample_payload
from test_draft_scope_ui import _csrf, _login
from test_draft_scope_ui import scope_password_hash as _password_hash
from test_shared_file_containment import postgresql_session_factory as _postgres_fixture
from test_technical_release_publication import _bound_variant, _publish

from classifire.draft_estimate_ui import router as estimate_router
from classifire.draft_pricing_ui import router as pricing_router
from classifire.models import (
    DraftPricingEvaluationRoster,
    Estimate,
    PricingLibraryRecord,
    User,
)
from classifire.services import draft_estimates as estimates
from classifire.services import draft_pricing_evaluation_rosters as rosters
from classifire.services import draft_pricing_intake as pricing
from classifire.services import draft_scope as scope
from classifire.services.draft_pricing_contract import FIELDS
from classifire.services.draft_system_match_contract import canonical

pdf_setup = _pdf_setup
pdf_app = _pdf_app
scope_password_hash = _password_hash
postgresql_session_factory = _postgres_fixture


def _workbook() -> bytes:
    stream = io.BytesIO()
    book = xlsxwriter.Workbook(stream, {"in_memory": True})
    sheet = book.add_worksheet("Systems")
    sheet.write_row(0, 0, list(FIELDS))
    for index in range(4):
        sheet.write_row(
            index + 1,
            0,
            [
                f"SYS-{index + 1}",
                f"Synthetic system configuration {index + 1}",
                "each",
                100 + index,
                "AUD",
                "excluded",
                "2026-09-07",
                20,
                80,
                "Installed system",
                "No shared closure",
            ],
        )
    book.close()
    return stream.getvalue()


def _prepared(db, x):
    owner = db.get(User, x.ids[0])
    foreign = db.get(User, x.ids[1])
    reviewer = User(
        email="t13-roster-reviewer@example.test",
        full_name="T13 roster reviewer",
        role="administrator",
        is_active=True,
        password_hash="unused",  # noqa: S106 - synthetic non-authenticating fixture
    )
    db.add(reviewer)
    variants = [
        _bound_variant(db, x.settings.storage_root, suffix=f"T13{index}")[0]
        for index in range(1, 4)
    ]
    release = _publish(
        db,
        actor=reviewer,
        storage_root=x.settings.storage_root,
        version="TECH-T13-2026.09",
    )
    source = pricing.retain_source(
        db,
        owner,
        x.ids[2],
        "dataset-b-t13.xlsx",
        _workbook(),
        "firefly_system_prices",
        settings=x.settings,
    )
    pricing.intake().scan_source(db, owner, x.ids[2], source.id, settings=x.settings)
    mapping = sparse_mapping()
    preview = pricing.preview_profile(
        db, owner, x.ids[2], source.id, 1, 1, mapping, "sell_price", settings=x.settings
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
        "The exact Dataset B profile and price meaning were reviewed.",
    )
    decision_hash = hashlib.sha256(canonical(decision)).hexdigest()
    saved = []
    for index, variant in enumerate(variants, start=2):
        mapping_preview = pricing.preview_system_mapping(
            db,
            reviewer,
            x.ids[2],
            source.id,
            profile["profile_id"],
            index,
            release.id,
            "mapped",
            f"SYS-{index - 1}",
            variant.id,
            [],
            ["reference", "description"],
            "The exact commercial identity matches this governed technical variant.",
            [],
            settings=x.settings,
        )
        saved.append(
            pricing.save_system_mapping(
                db,
                reviewer,
                x.ids[2],
                source.id,
                profile["profile_id"],
                index,
                release.id,
                "mapped",
                f"SYS-{index - 1}",
                variant.id,
                [],
                ["reference", "description"],
                "The exact commercial identity matches this governed technical variant.",
                [],
                profile_hash,
                decision_hash,
                mapping_preview["definition"]["row"]["sha256"],
                release.release_hash,
                mapping_preview["preview_hash"],
                settings=x.settings,
            )
        )
    unmatched_preview = pricing.preview_system_mapping(
        db,
        reviewer,
        x.ids[2],
        source.id,
        profile["profile_id"],
        5,
        release.id,
        "unmatched",
        "SYS-4",
        None,
        [],
        ["reference"],
        "No governed technical identity matches this exact commercial row.",
        ["technical_variant", "configuration_identity"],
        settings=x.settings,
    )
    unmatched = pricing.save_system_mapping(
        db,
        reviewer,
        x.ids[2],
        source.id,
        profile["profile_id"],
        5,
        release.id,
        "unmatched",
        "SYS-4",
        None,
        [],
        ["reference"],
        "No governed technical identity matches this exact commercial row.",
        ["technical_variant", "configuration_identity"],
        profile_hash,
        decision_hash,
        unmatched_preview["definition"]["row"]["sha256"],
        release.release_hash,
        unmatched_preview["preview_hash"],
        settings=x.settings,
    )
    db.commit()
    return owner, foreign, reviewer, variants, source, profile, saved, unmatched


def _save(db, reviewer, draft_id, preview, settings):
    roster = preview["roster"]
    return rosters.save_roster(
        db,
        reviewer,
        draft_id,
        roster_id=roster["roster_id"],
        manifest_id=roster["manifest_id"],
        created_at=roster["created_at"],
        expected_revision=roster["revision"],
        expected_parent_manifest_sha256=roster["parent_manifest_sha256"],
        expected_mapping_inventory_sha256=roster["mapping_inventory_sha256"],
        expected_preview_hash=preview["preview_hash"],
        settings=settings,
    )


def test_roster_preview_save_reopen_staleness_and_no_authority(pdf_setup):
    x = pdf_setup
    with x.factory() as db:
        owner, foreign, reviewer, variants, _source, _profile, saved, unmatched = _prepared(
            db, x
        )
        draft_id = x.ids[2]
        before = db.scalar(select(func.count()).select_from(DraftPricingEvaluationRoster))

        with pytest.raises(scope.DraftScopeError) as hidden:
            rosters.preview_roster(db, foreign, draft_id, settings=x.settings)
        assert hidden.value.status_code == 404
        with pytest.raises(scope.DraftScopeError) as denied:
            rosters.preview_roster(db, owner, draft_id, settings=x.settings)
        assert denied.value.status_code == 403

        preview = rosters.preview_roster(db, reviewer, draft_id, settings=x.settings)
        assert preview["can_save"] is True
        assert preview["eligible_count"] == 3
        assert preview["exclusions"] == [
            {
                "mapping_id": unmatched["mapping_id"],
                "mapping_sha256": hashlib.sha256(canonical(unmatched)).hexdigest(),
                "reason": "status_unmatched",
            }
        ]
        assert db.scalar(select(func.count()).select_from(DraftPricingEvaluationRoster)) == before
        manifest = preview["roster"]["manifest"]
        assert {group["split"] for group in manifest["groups"]} == {
            "training",
            "validation",
            "holdout",
        }
        assert {
            tuple(member["target"])
            for group in manifest["groups"]
            for member in group["members"]
        } == {("field", "sha256")}
        assert {item["mapping_id"] for item in preview["roster"]["mapping_inventory"]} == {
            *(item["mapping_id"] for item in saved),
            unmatched["mapping_id"],
        }

        future_preview = rosters.preview_roster(
            db,
            reviewer,
            draft_id,
            settings=x.settings,
            created_at=(datetime.now(UTC) + timedelta(minutes=2)).isoformat(),
        )
        with pytest.raises(
            scope.DraftScopeError, match="PRICING_EVALUATION_ROSTER_CHANGED"
        ):
            _save(db, reviewer, draft_id, future_preview, x.settings)

        with pytest.raises(
            scope.DraftScopeError, match="PRICING_EVALUATION_ROSTER_CHANGED"
        ):
            rosters.save_roster(
                db,
                reviewer,
                draft_id,
                roster_id=preview["roster"]["roster_id"],
                manifest_id=preview["roster"]["manifest_id"],
                created_at=preview["roster"]["created_at"],
                expected_revision=1,
                expected_parent_manifest_sha256=None,
                expected_mapping_inventory_sha256="0" * 64,
                expected_preview_hash=preview["preview_hash"],
                settings=x.settings,
            )
        retained = _save(db, reviewer, draft_id, preview, x.settings)
        db.commit()
        exact = rosters.roster_bytes(db, reviewer, draft_id, retained["roster_id"])
        assert exact == canonical(retained)
        assert b'"target":{"field":"rate","sha256":' in exact
        history = rosters.list_rosters(db, reviewer, draft_id, settings=x.settings)
        assert len(history) == 1
        assert history[0]["is_current"] is True
        assert db.scalar(select(func.count()).select_from(PricingLibraryRecord)) == 0
        assert db.scalar(select(func.count()).select_from(Estimate)) == 0

        replay = rosters.preview_roster(db, reviewer, draft_id, settings=x.settings)
        with pytest.raises(
            scope.DraftScopeError, match="PRICING_EVALUATION_ROSTER_ALREADY_CURRENT"
        ):
            _save(db, reviewer, draft_id, replay, x.settings)

        original = variants[0].manufacturer
        variants[0].manufacturer = "Changed after roster"
        db.commit()
        insufficient = rosters.preview_roster(db, reviewer, draft_id, settings=x.settings)
        assert insufficient["can_save"] is False
        assert insufficient["code"] == "PRICING_EVALUATION_INSUFFICIENT_GROUPS"
        assert insufficient["eligible_count"] == 2
        assert rosters.list_rosters(db, reviewer, draft_id, settings=x.settings)[0][
            "is_current"
        ] is False
        variants[0].manufacturer = original
        db.commit()

        stored = db.get(DraftPricingEvaluationRoster, retained["roster_id"])
        stored.roster_json += " "
        db.commit()
        with pytest.raises(
            scope.DraftScopeError,
            match="PRICING_EVALUATION_ROSTER_INTEGRITY_FAILED",
        ):
            rosters.roster_bytes(db, reviewer, draft_id, retained["roster_id"])


def test_roster_ui_preview_save_reopen_and_exact_download(pdf_app, monkeypatch):
    x = pdf_app
    monkeypatch.setattr("classifire.draft_pricing_ui.get_settings", lambda: x.settings)
    monkeypatch.setattr("classifire.draft_estimate_ui.get_settings", lambda: x.settings)
    x.app.include_router(estimate_router)
    x.app.include_router(pricing_router)
    with x.factory() as db:
        owner = db.get(User, x.ids[0])
        scope.save_revision(db, owner, x.ids[2], 1, sample_payload())
        estimate = estimates.create_estimate(db, owner, x.ids[2], 2)
        estimates.add_line(db, owner, x.ids[2], estimate.id, 1, add_payload())
        _, _, reviewer, *_ = _prepared(db, x)
        reviewer.email = "admin@scope.example.test"
        reviewer.password_hash = owner.password_hash
        db.commit()
        base = f"/scopes/{x.ids[2]}/estimates/{estimate.id}/pricing"

    with TestClient(x.app) as owner_client, TestClient(x.app) as admin:
        _login(owner_client)
        _login(admin, "admin")
        owner_page = owner_client.get(base)
        assert owner_page.status_code == 200
        assert "Pricing evaluation roster" in owner_page.text
        assert "must manage evaluation rosters" in owner_page.text
        admin_page = admin.get(base)
        assert "Preview current target-blind roster" in admin_page.text
        assert (
            admin.post(
                base + "/evaluation-roster/preview",
                data={"csrf_token": "bad"},
            ).status_code
            == 403
        )
        preview = admin.post(
            base + "/evaluation-roster/preview",
            data={"csrf_token": _csrf(admin_page.text)},
        )
        assert preview.status_code == 200, preview.text
        assert "No write has occurred" in preview.text
        assert "Save immutable roster" in preview.text
        assert "Training" in preview.text
        assert "Validation" in preview.text
        assert "Holdout" in preview.text

        def hidden(name):
            match = re.search(r'name="' + name + r'" value="([^"]*)"', preview.text)
            assert match is not None
            return match.group(1)

        saved = admin.post(
            base + "/evaluation-rosters",
            data={
                "csrf_token": _csrf(preview.text),
                **{
                    name: hidden(name)
                    for name in (
                        "roster_id",
                        "manifest_id",
                        "created_at",
                        "revision",
                        "parent_manifest_sha256",
                        "mapping_inventory_sha256",
                        "preview_hash",
                    )
                },
            },
            follow_redirects=False,
        )
        assert saved.status_code == 303, saved.text

    with TestClient(x.app) as reopened:
        _login(reopened, "admin")
        page = reopened.get(base)
        assert page.status_code == 200
        assert "Saved roster history" in page.text
        assert "<strong>Current</strong>" in page.text
        match = re.search(
            r'href="([^"]+/evaluation-rosters/[^"]+/download)"',
            page.text,
        )
        assert match is not None
        download = reopened.get(match.group(1))
        assert download.status_code == 200
        assert download.headers["x-content-type-options"] == "nosniff"
        assert canonical(download.json()) == download.content
        assert download.json()["effects"]["prediction_performed"] is False
