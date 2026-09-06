from __future__ import annotations

import hashlib
import json

import pytest
from sqlalchemy import func, select
from test_draft_pdf_intake import pdf_setup as _pdf_setup
from test_draft_pricing import MAPPING, workbook_bytes
from test_shared_file_containment import postgresql_session_factory as _postgres_fixture

from classifire.models import (
    DraftPricingSourceProfile,
    Estimate,
    LibraryRelease,
    TechnicalVariant,
    User,
)
from classifire.services import draft_pricing_intake as pricing
from classifire.services import draft_scope as scope
from classifire.services.draft_pricing_contract import FIELDS, profile_definition
from classifire.services.draft_pricing_worker import process
from classifire.services.draft_system_match_contract import canonical

pdf_setup = _pdf_setup
postgresql_session_factory = _postgres_fixture


def sparse_mapping():
    return {
        field: MAPPING[field]
        if field in {"reference", "description", "unit", "rate", "currency", "tax_basis"}
        else None
        for field in FIELDS
    }


def test_profile_definition_exposes_basis_and_mapping_gaps_without_inventing_values():
    content = workbook_bytes()
    document = json.loads(process(content))
    definition, rows = profile_definition(
        document,
        draft_scope_id="draft",
        source_id="source",
        dataset_id="dataset",
        dataset_kind="general_pricelist",
        dataset_version=1,
        source_sha256=hashlib.sha256(content).hexdigest(),
        source_size_bytes=len(content),
        original_filename="not-authority.xlsx",
        document_sha256=hashlib.sha256(canonical(document)).hexdigest(),
        sheet_index=1,
        header_row=1,
        mapping=sparse_mapping(),
        price_meaning="unknown",
    )

    assert len(rows) == 3
    assert definition["approval_status"] == "unapproved"
    assert definition["effects"] == {
        "library_activated": False,
        "estimate_changed": False,
        "system_matching_performed": False,
        "price_inference_performed": False,
    }
    assert definition["selection"]["header_cells"]["rate"]["address"] == "D1"
    assert definition["diagnostics"]["usable_rate_rows"] == 1
    assert definition["diagnostics"]["unresolved_rows"] == 2
    assert "price_meaning_unknown" in definition["diagnostics"]["gaps"]
    assert "rate_date_unmapped" in definition["diagnostics"]["gaps"]
    assert "item_kind_not_supported_by_current_mapping" in definition["diagnostics"]["gaps"]
    assert rows[1]["values"]["rate"] is None
    assert rows[2]["fields"]["rate"]["kind"] == "formula"


def test_dataset_versions_and_profile_revisions_are_separate_unapproved_history(pdf_setup):
    x = pdf_setup
    first_profile_id = None
    first_bytes = None
    source_id = None
    draft_id = x.ids[2]
    first_content = workbook_bytes()
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        first = pricing.retain_source(
            db,
            actor,
            draft_id,
            "anything.xlsx",
            first_content,
            "general_pricelist",
            settings=x.settings,
        )
        same = pricing.retain_source(
            db,
            actor,
            draft_id,
            "renamed.xlsx",
            first_content,
            "general_pricelist",
            settings=x.settings,
        )
        assert same.id == first.id
        assert first.dataset_kind == "general_pricelist"
        assert first.dataset_version == 1
        assert first.dataset_id
        with pytest.raises(scope.DraftScopeError, match="PRICING_DATASET_KIND_CONFLICT"):
            pricing.retain_source(
                db,
                actor,
                draft_id,
                "same-bytes-different-name.xlsx",
                first_content,
                "firefly_system_prices",
                settings=x.settings,
            )
        second = pricing.retain_source(
            db,
            actor,
            draft_id,
            "replacement.xlsx",
            workbook_bytes(rate=121),
            "general_pricelist",
            settings=x.settings,
        )
        firefly = pricing.retain_source(
            db,
            actor,
            draft_id,
            "not-proof-of-kind.xlsx",
            workbook_bytes(rate=222),
            "firefly_system_prices",
            settings=x.settings,
        )
        assert second.dataset_id == first.dataset_id
        assert second.dataset_version == 2
        assert firefly.dataset_id != first.dataset_id
        assert firefly.dataset_version == 1
        pricing.intake().scan_source(db, actor, draft_id, first.id, settings=x.settings)
        db.commit()

        mapping = sparse_mapping()
        preview = pricing.preview_profile(
            db,
            actor,
            draft_id,
            first.id,
            1,
            1,
            mapping,
            "unknown",
            settings=x.settings,
        )
        assert db.scalar(select(func.count()).select_from(DraftPricingSourceProfile)) == 0
        with pytest.raises(scope.DraftScopeError, match="PRICING_SOURCE_CHANGED"):
            pricing.save_profile(
                db,
                actor,
                draft_id,
                first.id,
                1,
                1,
                mapping,
                "unknown",
                0,
                "0" * 64,
                preview["preview_hash"],
                settings=x.settings,
            )
        assert db.scalar(select(func.count()).select_from(DraftPricingSourceProfile)) == 0
        saved = pricing.save_profile(
            db,
            actor,
            draft_id,
            first.id,
            1,
            1,
            mapping,
            "unknown",
            0,
            first.document_sha256,
            preview["preview_hash"],
            settings=x.settings,
        )
        db.commit()
        first_profile_id = saved["profile_id"]
        source_id = first.id
        first_bytes = pricing.profile_bytes(
            db, actor, draft_id, first.id, first_profile_id
        )
        assert first_bytes == canonical(saved)
        assert saved["definition"]["dataset"] == {
            "id": first.dataset_id,
            "kind": "general_pricelist",
            "version": 1,
        }
        assert saved["definition"]["approval_status"] == "unapproved"
        assert db.scalar(select(func.count()).select_from(Estimate)) == 0
        assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 0
        assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 0

        next_preview = pricing.preview_profile(
            db,
            actor,
            draft_id,
            first.id,
            1,
            1,
            mapping,
            "sell_price",
            settings=x.settings,
        )
        second_profile = pricing.save_profile(
            db,
            actor,
            draft_id,
            first.id,
            1,
            1,
            mapping,
            "sell_price",
            1,
            first.document_sha256,
            next_preview["preview_hash"],
            settings=x.settings,
        )
        db.commit()
        assert second_profile["revision"] == 2
        assert second_profile["parent_profile_sha256"] == hashlib.sha256(first_bytes).hexdigest()
        assert pricing.profile_bytes(db, actor, draft_id, first.id, first_profile_id) == first_bytes
        with pytest.raises(scope.DraftScopeError, match="PRICING_PROFILE_STALE"):
            pricing.save_profile(
                db,
                actor,
                draft_id,
                first.id,
                1,
                1,
                mapping,
                "sell_price",
                1,
                first.document_sha256,
                next_preview["preview_hash"],
                settings=x.settings,
            )
        assert db.scalar(select(func.count()).select_from(DraftPricingSourceProfile)) == 2
        foreign = db.get(User, x.ids[1])
        with pytest.raises(scope.DraftScopeError) as denied:
            pricing.read_profile(db, foreign, draft_id, first.id, first_profile_id)
        assert denied.value.status_code == 404

    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        reopened = pricing.read_profile(
            db, actor, draft_id, source_id, first_profile_id
        )
        assert reopened["revision"] == 1
        assert reopened["definition"]["commercial_basis"]["price_meaning"] == "unknown"
        assert (
            pricing.profile_bytes(db, actor, draft_id, source_id, first_profile_id)
            == first_bytes
        )
        stored = db.get(DraftPricingSourceProfile, first_profile_id)
        stored.profile_json += " "
        db.commit()
        with pytest.raises(scope.DraftScopeError, match="PRICING_PROFILE_INTEGRITY_FAILED"):
            pricing.read_profile(db, actor, draft_id, source_id, first_profile_id)
