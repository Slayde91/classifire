from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import func, select
from test_draft_pdf_intake import pdf_setup as _pdf_setup
from test_draft_pricing import workbook_bytes
from test_draft_pricing_profiles import sparse_mapping
from test_shared_file_containment import postgresql_session_factory as _postgres_fixture

from classifire.models import (
    DraftPricingRowObservation,
    Estimate,
    LabourComponent,
    LibraryRelease,
    PricingLibraryRecord,
    Product,
    TechnicalVariant,
    User,
)
from classifire.services import draft_pricing_intake as pricing
from classifire.services import draft_scope as scope
from classifire.services.draft_system_match_contract import canonical

pdf_setup = _pdf_setup
postgresql_session_factory = _postgres_fixture


def test_approved_dataset_a_row_observation_is_exact_immutable_and_non_authoritative(pdf_setup):
    x = pdf_setup
    mapping = sparse_mapping()
    draft_id = x.ids[2]
    with x.factory() as db:
        owner = db.get(User, x.ids[0])
        foreign = db.get(User, x.ids[1])
        reviewer = User(
            email="row-reviewer@example.test",
            full_name="Row reviewer",
            role="administrator",
            is_active=True,
            password_hash="unused",  # noqa: S106 - synthetic non-authenticating fixture
        )
        db.add(reviewer)
        source = pricing.retain_source(
            db,
            owner,
            draft_id,
            "dataset-a.xlsx",
            workbook_bytes(),
            "general_pricelist",
            settings=x.settings,
        )
        pricing.intake().scan_source(db, owner, draft_id, source.id, settings=x.settings)
        profile_preview = pricing.preview_profile(
            db, owner, draft_id, source.id, 1, 1, mapping, "sell_price", settings=x.settings
        )
        profile = pricing.save_profile(
            db,
            owner,
            draft_id,
            source.id,
            1,
            1,
            mapping,
            "sell_price",
            0,
            source.document_sha256,
            profile_preview["preview_hash"],
            settings=x.settings,
        )
        profile_hash = hashlib.sha256(canonical(profile)).hexdigest()
        decision = pricing.save_profile_decision(
            db,
            reviewer,
            draft_id,
            source.id,
            profile["profile_id"],
            profile_hash,
            "approve",
            "The exact Dataset A mapping and sell-price meaning were checked.",
        )
        decision_hash = hashlib.sha256(canonical(decision)).hexdigest()
        db.commit()

        with pytest.raises(scope.DraftScopeError) as denied:
            pricing.preview_row_observation(
                db,
                owner,
                draft_id,
                source.id,
                profile["profile_id"],
                2,
                "service",
                "SYN-1",
                "confirmed",
                "The retained description explicitly identifies service work.",
                [],
                settings=x.settings,
            )
        assert denied.value.status_code == 403
        with pytest.raises(scope.DraftScopeError) as hidden:
            pricing.preview_row_observation(
                db,
                foreign,
                draft_id,
                source.id,
                profile["profile_id"],
                2,
                "service",
                "SYN-1",
                "confirmed",
                "The retained description explicitly identifies service work.",
                [],
                settings=x.settings,
            )
        assert hidden.value.status_code == 404
        with pytest.raises(scope.DraftScopeError, match="PRICING_ROW_UNUSABLE"):
            pricing.preview_row_observation(
                db,
                reviewer,
                draft_id,
                source.id,
                profile["profile_id"],
                4,
                "service",
                "FORMULA",
                "provisional",
                "Formula cells cannot be treated as interpreted rates.",
                ["rate"],
                settings=x.settings,
            )
        with pytest.raises(
            scope.DraftScopeError, match="PRICING_ROW_OBSERVATION_INVALID"
        ):
            pricing.preview_row_observation(
                db,
                reviewer,
                draft_id,
                source.id,
                profile["profile_id"],
                2,
                "service",
                "SYN-1",
                "confirmed",
                "Confirmed observations cannot retain unresolved fields.",
                ["materials"],
                settings=x.settings,
            )

        before = db.scalar(select(func.count()).select_from(DraftPricingRowObservation))
        preview = pricing.preview_row_observation(
            db,
            reviewer,
            draft_id,
            source.id,
            profile["profile_id"],
            2,
            "service",
            "SYN-1",
            "confirmed",
            "The retained description explicitly identifies service work.",
            [],
            settings=x.settings,
        )
        assert db.scalar(select(func.count()).select_from(DraftPricingRowObservation)) == before
        with pytest.raises(scope.DraftScopeError, match="PRICING_ROW_CHANGED"):
            pricing.save_row_observation(
                db,
                reviewer,
                draft_id,
                source.id,
                profile["profile_id"],
                2,
                "service",
                "SYN-1",
                "confirmed",
                "The retained description explicitly identifies service work.",
                [],
                profile_hash,
                decision_hash,
                "0" * 64,
                preview["preview_hash"],
                settings=x.settings,
            )
        saved = pricing.save_row_observation(
            db,
            reviewer,
            draft_id,
            source.id,
            profile["profile_id"],
            2,
            "service",
            "SYN-1",
            "confirmed",
            "The retained description explicitly identifies service work.",
            [],
            profile_hash,
            decision_hash,
            preview["definition"]["row"]["sha256"],
            preview["preview_hash"],
            settings=x.settings,
        )
        db.commit()
        exact = pricing.row_observation_bytes(
            db,
            owner,
            draft_id,
            source.id,
            profile["profile_id"],
            saved["observation_id"],
        )
        assert exact == canonical(saved)
        assert saved["definition"]["row"]["fields"]["rate"]["address"] == "D2"
        assert saved["definition"]["profile"]["decision_sha256"] == decision_hash
        assert saved["definition"]["effects"]["service_created"] is False
        assert pricing.list_row_observations(
            db, owner, draft_id, source.id, profile["profile_id"]
        )[0]["is_current"] is True
        with pytest.raises(scope.DraftScopeError, match="PRICING_ROW_ALREADY_REVIEWED"):
            pricing.save_row_observation(
                db,
                reviewer,
                draft_id,
                source.id,
                profile["profile_id"],
                2,
                "product",
                "SYN-1",
                "confirmed",
                "A replay cannot replace the reviewed classification.",
                [],
                profile_hash,
                decision_hash,
                preview["definition"]["row"]["sha256"],
                preview["preview_hash"],
                settings=x.settings,
            )
        assert db.scalar(select(func.count()).select_from(Product)) == 0
        assert db.scalar(select(func.count()).select_from(LabourComponent)) == 0
        assert db.scalar(select(func.count()).select_from(PricingLibraryRecord)) == 0
        assert db.scalar(select(func.count()).select_from(Estimate)) == 0
        assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 0
        assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 0

        pricing.retain_source(
            db,
            owner,
            draft_id,
            "dataset-a-v2.xlsx",
            workbook_bytes(rate=125),
            "general_pricelist",
            settings=x.settings,
        )
        db.commit()
        with pytest.raises(scope.DraftScopeError, match="PRICING_SOURCE_STALE"):
            pricing.preview_row_observation(
                db,
                reviewer,
                draft_id,
                source.id,
                profile["profile_id"],
                3,
                "service",
                "UNKNOWN",
                "provisional",
                "A newer source version makes this source ineligible for new review.",
                ["rate"],
                settings=x.settings,
            )
        assert pricing.list_row_observations(
            db, owner, draft_id, source.id, profile["profile_id"]
        )[0]["is_current"] is False
        stored = db.get(DraftPricingRowObservation, saved["observation_id"])
        stored.observation_json += " "
        db.commit()
        with pytest.raises(
            scope.DraftScopeError, match="PRICING_ROW_OBSERVATION_INTEGRITY_FAILED"
        ):
            pricing.row_observation_bytes(
                db,
                owner,
                draft_id,
                source.id,
                profile["profile_id"],
                saved["observation_id"],
            )
