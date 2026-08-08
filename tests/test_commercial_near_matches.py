from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from classifire import canonical_models, commercial_models  # noqa: F401
from classifire.canonical_models import PhysicalModelLock, RepairStrategy
from classifire.db import Base
from classifire.models import (
    Estimate,
    LibraryRelease,
    Opening,
    PricingLibraryRecord,
    Project,
    Service,
    TechnicalVariant,
)
from classifire.services.commercial_near_matches import recommend_package14_matches


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def _manifest_hash(manifest: dict[str, object]) -> str:
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _release(db: Session, record_ids: list[str]) -> LibraryRelease:
    manifest: dict[str, object] = {"records": [{"id": item} for item in record_ids]}
    release = LibraryRelease(
        library_type="pricing",
        version="P14-NEAR-MATCH-TEST",
        status="active",
        release_hash=_manifest_hash(manifest),
        source_manifest=manifest,
    )
    db.add(release)
    db.flush()
    return release


def _fixture(db: Session, *, required_frl: str = "-/90/90") -> tuple[Estimate, Opening, Service]:
    project = Project(reference="NM-001", name="Near Match Test")
    db.add(project)
    db.flush()
    estimate = Estimate(
        project_id=project.id,
        revision=1,
        reference="NM-001-R1",
        title="Near Match Test",
        status="draft",
    )
    db.add(estimate)
    db.flush()
    opening = Opening(
        estimate_id=estimate.id,
        opening_code="O-001",
        substrate_type="concrete",
        substrate_plane="wall",
        orientation="vertical",
        frl=required_frl,
    )
    db.add(opening)
    db.flush()
    service = Service(
        opening_id=opening.id,
        service_code="S-001",
        service_type="pipe",
        material="copper",
        quantity=1,
    )
    db.add(service)
    db.flush()
    variant = TechnicalVariant(
        variant_id="VAR-001",
        system_id="SYS-001",
        service_type="pipe",
        service_material="copper",
        substrate_type="concrete",
        orientation="vertical",
        frl=required_frl,
        status="active",
        expert_review_required=False,
        source_hash="1" * 64,
        source_json={},
    )
    db.add(variant)
    db.flush()
    physical_lock = PhysicalModelLock(
        project_id=estimate.project_id,
        estimate_id=estimate.id,
        service_ids=[service.id],
        opening_ids=[opening.id],
        validator_result="PASS",
        content_hash="2" * 64,
    )
    db.add(physical_lock)
    db.flush()
    db.add(
        RepairStrategy(
            opening_id=opening.id,
            physical_model_lock_id=physical_lock.id,
            candidate_id="VAR-001",
            selected_technical_variant_id=variant.id,
            status="locked",
        )
    )
    db.flush()
    return estimate, opening, service


def _rate(
    db: Session,
    *,
    entry_id: str,
    frl: str,
    exact: str = "YES",
    proxy: str = "YES",
) -> PricingLibraryRecord:
    applicability = {
        "Exact_Match_Eligible_YN": exact,
        "Proxy_Eligible_YN": proxy,
        "Critical_Fields_Complete_YN": "YES",
        "Opening_Level_Reconciliation_Required_YN": "NO",
        "Duplicate_Recovery_Risk_Class": "LOW",
        "Package15_Variant_ID_Parsed": "VAR-001",
    }
    record = PricingLibraryRecord(
        pkb_entry_id=entry_id,
        entry_version="1",
        description=f"Rate {entry_id}",
        unit="each",
        rate_ex_tax=Decimal("500"),
        currency="AUD",
        tax_basis="GST Exclusive",
        service_type="pipe",
        service_class="pipe",
        service_material="copper",
        substrate="concrete",
        substrate_plane="wall",
        orientation="vertical",
        frl=frl,
        manufacturer="FIREFLY",
        repair_family="tested treatment",
        rate_inclusions={"Rate_Includes_Collar": "YES"},
        rate_exclusions={},
        applicability=applicability,
        commercial_confidence="HIGH",
        technical_status="MATCHED",
        status="active",
        source_hash=(entry_id[-1:] or "a") * 64,
        source_json={**applicability, "PKB_Entry_ID": entry_id},
    )
    db.add(record)
    db.flush()
    return record


def test_frl_mismatch_is_suggested_as_near_match_but_never_exact() -> None:
    with _session() as db:
        estimate, opening, service = _fixture(db, required_frl="-/90/90")
        candidate = _rate(db, entry_id="PKB-NEAR-001", frl="-/120/120", proxy="YES")
        estimate.pricing_release_id = _release(db, [candidate.id]).id
        db.flush()

        recommendation = recommend_package14_matches(
            db, estimate, opening=opening, service=service
        )
        assert not recommendation.exact_matches
        assert len(recommendation.suggested_near_matches) == 1
        near = recommendation.suggested_near_matches[0]
        assert near.similarity_percent == 85
        assert near.field_details["frl"]["result"] == "MISMATCH"
        assert near.field_details["frl"]["required"] == "-/90/90"
        assert near.field_details["frl"]["candidate"] == "-/120/120"
        assert not near.automatic_application_permitted
        assert near.proxy_eligible
        assert near.possible_use == "Approved Parameterised Match / Commercial Analogue"
        assert "frl_not_exact" in near.blockers
        assert recommendation.next_action == "review_parameterised_match_or_component_build"
        assert "No exact Package 14 match was found" in recommendation.message


def test_valid_exact_match_remains_separate_from_near_matches() -> None:
    with _session() as db:
        estimate, opening, service = _fixture(db, required_frl="-/90/90")
        candidate = _rate(db, entry_id="PKB-EXACT-001", frl="-/90/90", proxy="NO")
        estimate.pricing_release_id = _release(db, [candidate.id]).id
        db.flush()

        recommendation = recommend_package14_matches(
            db, estimate, opening=opening, service=service
        )
        assert len(recommendation.exact_matches) == 1
        assert not recommendation.suggested_near_matches
        exact = recommendation.exact_matches[0]
        assert exact.similarity_percent == 100
        assert exact.exact_match
        assert exact.automatic_application_permitted
        assert exact.possible_use == "Exact Library Match"
        assert recommendation.next_action == "review_exact_matches"


def test_non_proxy_near_match_is_commercial_analogue_only() -> None:
    with _session() as db:
        estimate, opening, service = _fixture(db, required_frl="-/90/90")
        candidate = _rate(db, entry_id="PKB-ANALOGUE-001", frl="-/120/120", proxy="NO")
        estimate.pricing_release_id = _release(db, [candidate.id]).id
        db.flush()

        recommendation = recommend_package14_matches(
            db, estimate, opening=opening, service=service
        )
        near = recommendation.suggested_near_matches[0]
        assert not near.proxy_eligible
        assert near.commercial_analogue
        assert near.possible_use == "Commercial Analogue only"
        assert not near.automatic_application_permitted
        assert recommendation.next_action == "component_build_using_analogue_for_context_only"
        assert "commercial analogue only" in recommendation.message
