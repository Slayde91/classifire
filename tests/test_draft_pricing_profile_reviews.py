from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from test_draft_pdf_intake import pdf_setup as _pdf_setup
from test_draft_pricing import workbook_bytes
from test_draft_pricing_profiles import sparse_mapping
from test_shared_file_containment import postgresql_session_factory as _postgres_fixture

from classifire.models import (
    DraftPricingSourceProfileDecision,
    Estimate,
    LibraryRelease,
    TechnicalVariant,
    User,
)
from classifire.services import draft_pricing_intake as pricing
from classifire.services import draft_scope as scope
from classifire.services.draft_pricing_contract import (
    PROFILE_DECISION_SCHEMA,
    PROFILE_DECISIONS,
    validate_profile_decision_envelope,
)
from classifire.services.draft_system_match_contract import canonical

pdf_setup = _pdf_setup
postgresql_session_factory = _postgres_fixture


def _decision(decision: str) -> dict[str, object]:
    return {
        "schema_version": PROFILE_DECISION_SCHEMA,
        "decision_id": "decision",
        "draft_scope_id": "draft",
        "source_id": "source",
        "profile_id": "profile",
        "profile_revision": 1,
        "profile_sha256": "a" * 64,
        "decision": decision,
        "reason": "Human checked the exact source interpretation.",
        "reviewed_at": datetime.now(UTC).isoformat(),
        "reviewed_by_id": "reviewer",
        "effects": {
            "rows_ingested": False,
            "library_activated": False,
            "technical_approval_granted": False,
            "system_matching_performed": False,
            "price_inference_performed": False,
            "estimate_changed": False,
            "release_performed": False,
        },
    }


@pytest.mark.parametrize("decision", PROFILE_DECISIONS)
def test_decision_contract_accepts_only_bounded_non_authoritative_human_outcomes(decision):
    value = _decision(decision)
    validate_profile_decision_envelope(value)
    value["effects"] = {**value["effects"], "estimate_changed": True}
    with pytest.raises(ValueError, match="effects"):
        validate_profile_decision_envelope(value)


def test_exact_profile_review_history_fails_closed_and_changes_no_downstream_state(pdf_setup):
    x = pdf_setup
    mapping = sparse_mapping()
    draft_id = x.ids[2]
    with x.factory() as db:
        owner = db.get(User, x.ids[0])
        foreign = db.get(User, x.ids[1])
        reviewer = User(
            email="pricing-reviewer@example.test",
            full_name="Pricing reviewer",
            role="administrator",
            is_active=True,
            password_hash="unused",  # noqa: S106 - synthetic non-authenticating fixture
        )
        db.add(reviewer)
        source = pricing.retain_source(
            db,
            owner,
            draft_id,
            "review-source.xlsx",
            workbook_bytes(),
            "general_pricelist",
            settings=x.settings,
        )
        pricing.intake().scan_source(db, owner, draft_id, source.id, settings=x.settings)
        db.commit()

        preview_one = pricing.preview_profile(
            db, owner, draft_id, source.id, 1, 1, mapping, "unknown", settings=x.settings
        )
        profile_one = pricing.save_profile(
            db,
            owner,
            draft_id,
            source.id,
            1,
            1,
            mapping,
            "unknown",
            0,
            source.document_sha256,
            preview_one["preview_hash"],
            settings=x.settings,
        )
        preview_two = pricing.preview_profile(
            db, owner, draft_id, source.id, 1, 1, mapping, "sell_price", settings=x.settings
        )
        profile_two = pricing.save_profile(
            db,
            owner,
            draft_id,
            source.id,
            1,
            1,
            mapping,
            "sell_price",
            1,
            source.document_sha256,
            preview_two["preview_hash"],
            settings=x.settings,
        )
        db.commit()

        with pytest.raises(scope.DraftScopeError, match="PRICING_PROFILE_STALE"):
            pricing.save_profile_decision(
                db,
                reviewer,
                draft_id,
                source.id,
                profile_one["profile_id"],
                hashlib.sha256(canonical(profile_one)).hexdigest(),
                "reject",
                "A newer interpretation exists.",
            )
        with pytest.raises(scope.DraftScopeError) as denied:
            pricing.save_profile_decision(
                db,
                owner,
                draft_id,
                source.id,
                profile_two["profile_id"],
                hashlib.sha256(canonical(profile_two)).hexdigest(),
                "approve",
                "Owner cannot approve their own pricing profile.",
            )
        assert denied.value.status_code == 403
        with pytest.raises(scope.DraftScopeError) as hidden:
            pricing.save_profile_decision(
                db,
                foreign,
                draft_id,
                source.id,
                profile_two["profile_id"],
                hashlib.sha256(canonical(profile_two)).hexdigest(),
                "approve",
                "Foreign project must stay hidden.",
            )
        assert hidden.value.status_code == 404
        with pytest.raises(scope.DraftScopeError, match="PRICING_PROFILE_CHANGED"):
            pricing.save_profile_decision(
                db,
                reviewer,
                draft_id,
                source.id,
                profile_two["profile_id"],
                "0" * 64,
                "approve",
                "Hash mismatch must fail.",
            )

        profile_bytes = pricing.profile_bytes(
            db, owner, draft_id, source.id, profile_two["profile_id"]
        )
        saved = pricing.save_profile_decision(
            db,
            reviewer,
            draft_id,
            source.id,
            profile_two["profile_id"],
            hashlib.sha256(profile_bytes).hexdigest(),
            "approve",
            "The exact mapping and declared sell-price basis were checked.",
        )
        db.commit()
        decision_bytes = pricing.profile_decision_bytes(
            db,
            owner,
            draft_id,
            source.id,
            profile_two["profile_id"],
            saved["decision_id"],
        )
        assert decision_bytes == canonical(saved)
        assert (
            pricing.profile_bytes(db, owner, draft_id, source.id, profile_two["profile_id"])
            == profile_bytes
        )
        assert saved["profile_sha256"] == hashlib.sha256(profile_bytes).hexdigest()
        assert saved["reviewed_by_id"] == reviewer.id
        assert saved["effects"]["rows_ingested"] is False
        with pytest.raises(scope.DraftScopeError, match="PRICING_PROFILE_ALREADY_REVIEWED"):
            pricing.save_profile_decision(
                db,
                reviewer,
                draft_id,
                source.id,
                profile_two["profile_id"],
                saved["profile_sha256"],
                "reject",
                "A replay cannot replace immutable history.",
            )
        assert db.scalar(select(func.count()).select_from(DraftPricingSourceProfileDecision)) == 1
        assert db.scalar(select(func.count()).select_from(Estimate)) == 0
        assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 0
        assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 0

        preview_three = pricing.preview_profile(
            db, owner, draft_id, source.id, 1, 1, mapping, "quoted_price", settings=x.settings
        )
        pricing.save_profile(
            db,
            owner,
            draft_id,
            source.id,
            1,
            1,
            mapping,
            "quoted_price",
            2,
            source.document_sha256,
            preview_three["preview_hash"],
            settings=x.settings,
        )
        db.commit()
        history = pricing.list_profile_decisions(db, owner, draft_id, source.id)
        assert len(history) == 1
        assert history[0]["is_current"] is False
        assert history[0]["value"] == saved

        stored = db.get(DraftPricingSourceProfileDecision, saved["decision_id"])
        stored.decision_json += " "
        db.commit()
        with pytest.raises(
            scope.DraftScopeError, match="PRICING_PROFILE_DECISION_INTEGRITY_FAILED"
        ):
            pricing.read_profile_decision(
                db,
                owner,
                draft_id,
                source.id,
                profile_two["profile_id"],
                saved["decision_id"],
            )
