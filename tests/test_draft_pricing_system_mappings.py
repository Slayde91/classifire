from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import func, select
from test_draft_pdf_intake import pdf_setup as _pdf_setup
from test_draft_pricing import workbook_bytes
from test_draft_pricing_profiles import sparse_mapping
from test_shared_file_containment import postgresql_session_factory as _postgres_fixture
from test_technical_release_publication import _bound_variant, _publish

from classifire.models import (
    DraftPricingSystemMapping,
    Estimate,
    LibraryRelease,
    PricingLibraryRecord,
    TechnicalVariant,
    User,
)
from classifire.services import draft_pricing_intake as pricing
from classifire.services import draft_scope as scope
from classifire.services.draft_system_match_contract import canonical

pdf_setup = _pdf_setup
postgresql_session_factory = _postgres_fixture


def _prepared(db, x):
    owner = db.get(User, x.ids[0])
    foreign = db.get(User, x.ids[1])
    reviewer = User(
        email="dataset-b-reviewer@example.test",
        full_name="Dataset B reviewer",
        role="administrator",
        is_active=True,
        password_hash="unused",  # noqa: S106 - synthetic non-authenticating fixture
    )
    db.add(reviewer)
    first, _ = _bound_variant(db, x.settings.storage_root, suffix="B001")
    second, _ = _bound_variant(db, x.settings.storage_root, suffix="B002")
    release = _publish(
        db,
        actor=reviewer,
        storage_root=x.settings.storage_root,
        version="TECH-B-2026.09",
    )
    source = pricing.retain_source(
        db,
        owner,
        x.ids[2],
        "dataset-b.xlsx",
        workbook_bytes(),
        "firefly_system_prices",
        settings=x.settings,
    )
    pricing.intake().scan_source(db, owner, x.ids[2], source.id, settings=x.settings)
    mapping = sparse_mapping()
    profile_preview = pricing.preview_profile(
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
        profile_preview["preview_hash"],
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
        "The exact Dataset B source profile and price meaning were checked.",
    )
    decision_hash = hashlib.sha256(canonical(decision)).hexdigest()
    db.commit()
    return (
        owner,
        foreign,
        reviewer,
        first,
        second,
        release,
        source,
        profile,
        profile_hash,
        decision_hash,
    )


def test_dataset_b_mapping_is_exact_immutable_and_non_authoritative(pdf_setup):
    x = pdf_setup
    with x.factory() as db:
        (
            owner,
            foreign,
            reviewer,
            first,
            second,
            release,
            source,
            profile,
            profile_hash,
            decision_hash,
        ) = _prepared(db, x)
        draft_id = x.ids[2]
        profile_id = profile["profile_id"]

        with pytest.raises(scope.DraftScopeError) as denied:
            pricing.preview_system_mapping(
                db,
                owner,
                draft_id,
                source.id,
                profile_id,
                2,
                release.id,
                "mapped",
                "SYN-1",
                first.id,
                [],
                ["reference"],
                "The retained reference identifies the reviewed technical variant.",
                [],
                settings=x.settings,
            )
        assert denied.value.status_code == 403
        with pytest.raises(scope.DraftScopeError) as hidden:
            pricing.preview_system_mapping(
                db,
                foreign,
                draft_id,
                source.id,
                profile_id,
                2,
                release.id,
                "unmatched",
                "SYN-1",
                None,
                [],
                [],
                "The foreign project must remain hidden.",
                ["technical_variant"],
                settings=x.settings,
            )
        assert hidden.value.status_code == 404
        with pytest.raises(scope.DraftScopeError, match="PRICING_ROW_UNUSABLE"):
            pricing.preview_system_mapping(
                db,
                reviewer,
                draft_id,
                source.id,
                profile_id,
                4,
                release.id,
                "unmatched",
                "FORMULA",
                None,
                [],
                [],
                "Formula prices cannot become reviewed system mappings.",
                ["rate", "technical_variant"],
                settings=x.settings,
            )
        with pytest.raises(
            scope.DraftScopeError, match="PRICING_SYSTEM_MAPPING_INVALID"
        ):
            pricing.preview_system_mapping(
                db,
                reviewer,
                draft_id,
                source.id,
                profile_id,
                2,
                release.id,
                "mapped",
                "SYN-1",
                first.id,
                [],
                ["rate"],
                "Price alone cannot prove technical system identity.",
                [],
                settings=x.settings,
            )

        ambiguous = pricing.preview_system_mapping(
            db,
            reviewer,
            draft_id,
            source.id,
            profile_id,
            2,
            release.id,
            "ambiguous",
            "SYN-1",
            None,
            sorted([first.id, second.id]),
            ["reference", "description"],
            "Two source-bound technical variants remain plausible.",
            ["configuration_identity"],
            settings=x.settings,
        )
        assert len(ambiguous["definition"]["variants"]) == 2
        unmatched = pricing.preview_system_mapping(
            db,
            reviewer,
            draft_id,
            source.id,
            profile_id,
            2,
            release.id,
            "unmatched",
            "SYN-1",
            None,
            [],
            [],
            "No eligible technical variant is identified by this commercial row.",
            ["technical_variant", "configuration_identity"],
            settings=x.settings,
        )
        assert unmatched["definition"]["variants"] == []

        before = db.scalar(select(func.count()).select_from(DraftPricingSystemMapping))
        preview = pricing.preview_system_mapping(
            db,
            reviewer,
            draft_id,
            source.id,
            profile_id,
            2,
            release.id,
            "mapped",
            "SYN-1",
            first.id,
            [],
            ["reference", "description"],
            "The exact reference and description identify this reviewed variant.",
            [],
            settings=x.settings,
        )
        assert db.scalar(select(func.count()).select_from(DraftPricingSystemMapping)) == before
        with pytest.raises(
            scope.DraftScopeError, match="PRICING_SYSTEM_MAPPING_CHANGED"
        ):
            pricing.save_system_mapping(
                db,
                reviewer,
                draft_id,
                source.id,
                profile_id,
                2,
                release.id,
                "mapped",
                "SYN-1",
                first.id,
                [],
                ["reference", "description"],
                "The exact reference and description identify this reviewed variant.",
                [],
                profile_hash,
                decision_hash,
                preview["definition"]["row"]["sha256"],
                "0" * 64,
                preview["preview_hash"],
                settings=x.settings,
            )
        saved = pricing.save_system_mapping(
            db,
            reviewer,
            draft_id,
            source.id,
            profile_id,
            2,
            release.id,
            "mapped",
            "SYN-1",
            first.id,
            [],
            ["reference", "description"],
            "The exact reference and description identify this reviewed variant.",
            [],
            profile_hash,
            decision_hash,
            preview["definition"]["row"]["sha256"],
            release.release_hash,
            preview["preview_hash"],
            settings=x.settings,
        )
        db.commit()
        exact = pricing.system_mapping_bytes(
            db, reviewer, draft_id, source.id, profile_id, saved["mapping_id"]
        )
        assert exact == canonical(saved)
        definition = saved["definition"]
        assert definition["row"]["fields"]["rate"]["address"] == "D2"
        assert definition["variants"][0]["source_verification"] == {
            "method": "exact_bytes"
        }
        assert definition["variants"][0]["technical_fields_sha256"]
        assert definition["variants"][0]["release_record_sha256"]
        assert definition["effects"] == {
            "pricing_system_mapping_recorded": True,
            "rows_ingested": False,
            "library_activated": False,
            "technical_approval_granted": False,
            "technical_applicability_assessed": False,
            "system_match_package_changed": False,
            "price_inference_performed": False,
            "estimate_changed": False,
            "holdout_assigned": False,
            "release_performed": False,
        }
        assert pricing.list_system_mappings(
            db, reviewer, draft_id, source.id, profile_id, settings=x.settings
        )[0]["is_current"] is True
        with pytest.raises(
            scope.DraftScopeError, match="PRICING_SYSTEM_ALREADY_MAPPED"
        ):
            pricing.save_system_mapping(
                db,
                reviewer,
                draft_id,
                source.id,
                profile_id,
                2,
                release.id,
                "mapped",
                "SYN-1",
                first.id,
                [],
                ["reference", "description"],
                "Replay cannot replace the immutable reviewed result.",
                [],
                profile_hash,
                decision_hash,
                preview["definition"]["row"]["sha256"],
                release.release_hash,
                preview["preview_hash"],
                settings=x.settings,
            )
        assert db.scalar(select(func.count()).select_from(PricingLibraryRecord)) == 0
        assert db.scalar(select(func.count()).select_from(Estimate)) == 0
        assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 1
        assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 2

        original_manufacturer = first.manufacturer
        first.manufacturer = "Changed after release"
        db.commit()
        assert pricing.list_system_mappings(
            db, reviewer, draft_id, source.id, profile_id, settings=x.settings
        )[0]["is_current"] is False
        first.manufacturer = original_manufacturer
        db.commit()
        assert pricing.list_system_mappings(
            db, reviewer, draft_id, source.id, profile_id, settings=x.settings
        )[0]["is_current"] is True
        release.status = "superseded"
        db.commit()
        assert pricing.list_system_mappings(
            db, reviewer, draft_id, source.id, profile_id, settings=x.settings
        )[0]["is_current"] is False
        release.status = "active"
        db.commit()
        pricing.retain_source(
            db,
            owner,
            draft_id,
            "dataset-b-v2.xlsx",
            workbook_bytes(rate=125),
            "firefly_system_prices",
            settings=x.settings,
        )
        db.commit()
        assert pricing.list_system_mappings(
            db, reviewer, draft_id, source.id, profile_id, settings=x.settings
        )[0]["is_current"] is False
        stored = db.get(DraftPricingSystemMapping, saved["mapping_id"])
        stored.mapping_json += " "
        db.commit()
        with pytest.raises(
            scope.DraftScopeError, match="PRICING_SYSTEM_MAPPING_INTEGRITY_FAILED"
        ):
            pricing.system_mapping_bytes(
                db, reviewer, draft_id, source.id, profile_id, saved["mapping_id"]
            )
