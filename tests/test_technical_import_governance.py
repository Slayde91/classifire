from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import date, timedelta
from inspect import signature
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from classifire import models, physical_models  # noqa: F401
from classifire.cli import import_technical
from classifire.db import Base
from classifire.importers.technical import (
    PENDING_REVIEW_SEARCH_ELIGIBILITY,
    TECHNICAL_IMPORT_POLICY,
    import_technical_variants,
)
from classifire.models import (
    Estimate,
    EstimatingRule,
    LabourComponent,
    LibraryRelease,
    Opening,
    PricingLibraryRecord,
    Product,
    Project,
    Service,
    StoredFile,
    TechnicalDocument,
    TechnicalVariant,
)
from classifire.release_admin import _activate_drafts, _snapshot_records, _technical_logical_key
from classifire.services import technical_validity
from classifire.services.release_pinning import (
    PIN_FIELDS,
    active_release,
    pin_current_releases,
    validate_estimate_release_basis,
)
from classifire.services.release_scope import ReleaseScopeError, pinned_technical_ids
from classifire.services.technical import (
    mixed_service_candidate_available,
    search_for_opening,
    search_variants,
)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _active_source_row(variant_id: str = "VAR-001", system_id: str = "SYS-001") -> dict[str, str]:
    return {
        "Variant_ID": variant_id,
        "System_ID": system_id,
        "Variant_Status": "active",
        "Search_Index_Status": "ACTIVE",
        "Search_Eligibility": "INCLUDE",
        "Expert_Review_Trigger_YN": "NO",
        "Effective_Date": "2026-01-01",
        "Evidence_Expiry_Date": "2030-01-01",
        "Variant_Content_Hash": "source-controlled-hash",
        "Source_Document_ID": "TEST-REPORT-001",
        "Source_Page": "12",
        "Service_Type": "pipe",
        "Service_Material": "steel",
        "FRL_Variant": "-/120/120",
    }


def _source_file(
    tmp_path: Path,
    rows: list[dict[str, str]],
    filename: str = "technical.jsonl",
) -> tuple[Path, str]:
    path = tmp_path / filename
    payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    path.write_text(payload, encoding="utf-8", newline="\n")
    return path, payload


def _release_manifest_hash(manifest: Mapping[str, object]) -> str:
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _opening_with_directly_pinned_technical_release(db, release_id: str) -> Opening:
    project = Project(reference="DIRECT-PIN-PROJECT", name="Direct pin scope test")
    estimate = Estimate(
        project=project,
        reference="DIRECT-PIN-ESTIMATE",
        title="Direct pin scope test",
        technical_release_id=release_id,
    )
    opening = Opening(
        estimate=estimate,
        opening_code="DIRECT-PIN-OPENING",
        substrate_type="concrete",
        orientation="wall",
        frl="-/120/120",
    )
    opening.services.extend(
        [
            Service(service_code="DIRECT-PIN-PIPE", service_type="pipe", material="steel"),
            Service(service_code="DIRECT-PIN-CABLE", service_type="cable", material="copper"),
        ]
    )
    db.add(opening)
    db.flush()
    return opening


def _active_release_with_variant(
    db, *, variant_status: str
) -> tuple[LibraryRelease, TechnicalVariant]:
    release = LibraryRelease(
        library_type="technical",
        version=f"{variant_status}-variant-scope-v1",
        status="active",
    )
    db.add(release)
    db.flush()
    variant = TechnicalVariant(
        variant_id=f"{variant_status.upper()}-VARIANT-001",
        system_id=f"{variant_status.upper()}-SYSTEM-001",
        service_type="pipe",
        service_material="steel",
        frl="-/120/120",
        status=variant_status,
        expert_review_required=False,
        source_json={"fixture": f"{variant_status}-variant-scope"},
        release_id=release.id,
    )
    db.add(variant)
    db.flush()
    manifest = {"records": [{"id": variant.id}]}
    release.source_manifest = manifest
    release.release_hash = _release_manifest_hash(manifest)
    db.flush()
    return release, variant


def _technical_document(
    db,
    *,
    status: str = "approved",
    expiry_date: date | None = None,
    stored_purpose: str = "technical_evidence",
    stored_scan_status: str = "clean",
    stored_immutable: bool = True,
) -> TechnicalDocument:
    stored = StoredFile(
        original_filename="technical-source.pdf",
        media_type="application/pdf",
        storage_path="technical/source.pdf",
        sha256="a" * 64,
        size_bytes=1,
        purpose=stored_purpose,
        malware_scan_status=stored_scan_status,
        immutable=stored_immutable,
    )
    db.add(stored)
    db.flush()
    document = TechnicalDocument(
        document_id="TECHNICAL-SOURCE-001",
        stored_file_id=stored.id,
        document_type="assessment",
        title="Technical source",
        status=status,
        expiry_date=expiry_date,
    )
    db.add(document)
    db.flush()
    return document


def _active_non_technical_releases(db) -> None:
    for release_type in sorted(set(PIN_FIELDS) - {"technical"}):
        db.add(
            LibraryRelease(
                library_type=release_type,
                version=f"{release_type}-pinning-v1",
                status="active",
            )
        )
    db.flush()


def _editable_estimate(db) -> Estimate:
    project = Project(reference="PINNING-PROJECT", name="Release pinning test")
    estimate = Estimate(
        project=project,
        reference="PINNING-ESTIMATE",
        title="Release pinning test",
    )
    db.add(estimate)
    db.flush()
    return estimate


def test_source_activation_flags_cannot_activate_imported_candidate(db, tmp_path) -> None:
    row = _active_source_row()
    path, payload = _source_file(tmp_path, [row])

    result = import_technical_variants(db, path, version="intake-v1")

    release = db.get(LibraryRelease, result["release_id"])
    variant = db.scalar(select(TechnicalVariant))
    assert release is not None
    assert variant is not None
    assert release.status == "draft"
    assert release.source_manifest["import_policy"] == TECHNICAL_IMPORT_POLICY
    assert release.source_manifest["runtime_eligible"] is False
    assert release.source_manifest["source_activity_fields_authoritative"] is False
    assert release.source_manifest["source_activity_rows"] == 1
    assert variant.status == "draft"
    assert variant.expert_review_required is True
    assert variant.search_eligibility == PENDING_REVIEW_SEARCH_ELIGIBILITY
    assert variant.effective_date is None
    assert variant.expiry_date is None
    assert variant.source_hash == hashlib.sha256(payload.encode("utf-8")).hexdigest()
    assert variant.source_json["Variant_Status"] == "active"
    assert variant.source_json["Search_Index_Status"] == "ACTIVE"
    assert variant.source_json["Search_Eligibility"] == "INCLUDE"
    assert variant.source_json["Variant_Content_Hash"] == "source-controlled-hash"


def test_imported_candidate_is_excluded_from_search_and_release_snapshot(db, tmp_path) -> None:
    path, _payload = _source_file(tmp_path, [_active_source_row()])
    import_technical_variants(db, path, version="intake-v1")

    assert search_variants(db, service_type="pipe") == []
    draft_candidates = search_variants(db, service_type="pipe", include_draft=True)
    assert len(draft_candidates) == 1
    assert "expert_review_required" in draft_candidates[0].blockers
    assert "search_excluded" in draft_candidates[0].blockers
    assert _snapshot_records(db, "technical") == []
    assert active_release(db, "technical") is None
    assert (
        db.scalar(
            select(func.count())
            .select_from(LibraryRelease)
            .where(LibraryRelease.library_type == "technical", LibraryRelease.status == "active")
        )
        == 0
    )


def test_release_admin_never_activates_a_technical_draft(db) -> None:
    variant = TechnicalVariant(
        variant_id="DRAFT-VARIANT-QFREV2",
        system_id="DRAFT-SYSTEM",
        status="draft",
        source_json={"fixture": "technical-draft"},
    )
    db.add(variant)
    db.flush()

    assert _technical_logical_key(variant) == "DRAFT-VARIANT"
    assert _activate_drafts(db, "technical") == []
    assert variant.status == "draft"
    assert _snapshot_records(db, "technical") == []


def test_release_admin_activates_only_non_technical_drafts(db) -> None:
    pricing_active = PricingLibraryRecord(
        pkb_entry_id="RATE-001",
        entry_version="v1",
        description="Active pricing record",
        source_json={"fixture": "active-pricing"},
        status="active",
    )
    pricing_draft = PricingLibraryRecord(
        pkb_entry_id="RATE-001",
        entry_version="v2",
        description="Draft pricing record",
        source_json={"fixture": "draft-pricing"},
        status="draft",
    )
    rule_active = EstimatingRule(
        rule_code="RULE-001",
        version=1,
        name="Active rule",
        category="test",
        description="Active rule",
        conditions={},
        actions={},
        status="active",
    )
    rule_draft = EstimatingRule(
        rule_code="RULE-001",
        version=2,
        name="Draft rule",
        category="test",
        description="Draft rule",
        conditions={},
        actions={},
        status="draft",
    )
    labour_active = LabourComponent(
        code="LAB-001", revision=1, name="Active labour", status="active"
    )
    labour_draft = LabourComponent(code="LAB-001", revision=2, name="Draft labour", status="draft")
    product_active = Product(sku="PROD-001", revision=1, name="Active product", status="active")
    product_draft = Product(sku="PROD-001", revision=2, name="Draft product", status="draft")
    db.add_all(
        [
            pricing_active,
            pricing_draft,
            rule_active,
            rule_draft,
            labour_active,
            labour_draft,
            product_active,
            product_draft,
        ]
    )
    db.flush()

    assert _activate_drafts(db, "pricing") == [pricing_draft.id]
    assert _activate_drafts(db, "rules") == [rule_draft.id]
    assert _activate_drafts(db, "labour") == [labour_draft.id]
    assert _activate_drafts(db, "products") == [product_draft.id]

    assert pricing_active.status == "superseded"
    assert pricing_draft.status == "active"
    assert rule_active.status == "superseded"
    assert rule_draft.status == "active"
    assert rule_draft.approved_at is not None
    assert labour_active.status == "superseded"
    assert labour_draft.status == "active"
    assert product_active.status == "superseded"
    assert product_draft.status == "active"


def test_draft_import_cannot_be_searched_through_a_directly_pinned_release(db, tmp_path) -> None:
    path, _payload = _source_file(tmp_path, [_active_source_row()])
    result = import_technical_variants(db, path, version="intake-v1")
    release = db.get(LibraryRelease, result["release_id"])
    assert release is not None
    assert release.source_manifest is not None
    # Exercise the separate activity guard with a valid immutable Draft release.
    release.release_hash = _release_manifest_hash(release.source_manifest)
    db.flush()
    opening = _opening_with_directly_pinned_technical_release(db, result["release_id"])

    with pytest.raises(ReleaseScopeError, match="Pinned technical release is not active"):
        search_for_opening(db, opening)
    with pytest.raises(ReleaseScopeError, match="Pinned technical release is not active"):
        mixed_service_candidate_available(db, opening)
    assert "Pinned technical release is not active." in validate_estimate_release_basis(
        db, opening.estimate
    )


def test_active_release_with_a_retired_variant_fails_closed(db) -> None:
    release, _variant = _active_release_with_variant(db, variant_status="retired")
    opening = _opening_with_directly_pinned_technical_release(db, release.id)

    with pytest.raises(
        ReleaseScopeError,
        match="Pinned technical release contains inactive or missing variants",
    ):
        search_for_opening(db, opening)
    with pytest.raises(
        ReleaseScopeError,
        match="Pinned technical release contains inactive or missing variants",
    ):
        mixed_service_candidate_available(db, opening)
    assert "Pinned technical release contains inactive or missing variants." in (
        validate_estimate_release_basis(db, opening.estimate)
    )


@pytest.mark.parametrize(
    ("field_name", "field_value", "expected_blocker"),
    [
        ("effective_date", date(2026, 9, 13), "not_yet_effective"),
        ("expiry_date", date(2026, 9, 11), "expired"),
    ],
)
def test_active_release_with_a_temporally_ineligible_variant_fails_closed(
    db,
    field_name: str,
    field_value: date,
    expected_blocker: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Collection and execution can straddle midnight in the full suite.
    # Freeze the review clock without changing eligibility rules or assertions.
    class ReviewDate(date):
        @classmethod
        def today(cls) -> date:
            return date(2026, 9, 12)

    monkeypatch.setattr(technical_validity, "date", ReviewDate)
    release, variant = _active_release_with_variant(db, variant_status="active")
    setattr(variant, field_name, field_value)
    db.flush()
    opening = _opening_with_directly_pinned_technical_release(db, release.id)

    with pytest.raises(
        ReleaseScopeError,
        match="Pinned technical release contains inactive or missing variants",
    ):
        search_for_opening(db, opening)
    assert search_variants(db, service_type="pipe") == []
    admin_candidates = search_variants(db, service_type="pipe", include_draft=True)
    assert len(admin_candidates) == 1
    assert expected_blocker in admin_candidates[0].blockers
    assert _snapshot_records(db, "technical") == []


def test_active_release_with_an_expired_bound_source_fails_closed(db) -> None:
    release, variant = _active_release_with_variant(db, variant_status="active")
    variant.technical_document_id = _technical_document(
        db,
        expiry_date=date.today() - timedelta(days=1),
    ).id
    db.flush()
    opening = _opening_with_directly_pinned_technical_release(db, release.id)

    with pytest.raises(
        ReleaseScopeError,
        match="Pinned technical release contains inactive or missing variants",
    ):
        search_for_opening(db, opening)
    assert search_variants(db, service_type="pipe") == []
    admin_candidates = search_variants(db, service_type="pipe", include_draft=True)
    assert len(admin_candidates) == 1
    assert "source_document_expired" in admin_candidates[0].blockers
    assert _snapshot_records(db, "technical") == []


@pytest.mark.parametrize(
    (
        "document_status",
        "stored_purpose",
        "stored_scan_status",
        "stored_immutable",
        "stored_file_present",
        "expected_blocker",
    ),
    [
        ("in_review", "technical_evidence", "clean", True, True, "source_document_not_approved"),
        ("approved", "technical_evidence", "malware_detected", True, True, "source_file_not_clean"),
        ("approved", "technical_evidence", "clean", False, True, "source_file_not_immutable"),
        ("approved", "project_evidence", "clean", True, True, "source_file_wrong_purpose"),
        ("approved", "technical_evidence", "clean", True, False, "source_file_missing"),
    ],
)
def test_active_release_with_an_unsafe_bound_source_fails_closed(
    db,
    document_status: str,
    stored_purpose: str,
    stored_scan_status: str,
    stored_immutable: bool,
    stored_file_present: bool,
    expected_blocker: str,
) -> None:
    release, variant = _active_release_with_variant(db, variant_status="active")
    document = _technical_document(
        db,
        status=document_status,
        stored_purpose=stored_purpose,
        stored_scan_status=stored_scan_status,
        stored_immutable=stored_immutable,
    )
    if not stored_file_present:
        document.stored_file_id = "missing-source-file"
    variant.technical_document_id = document.id
    db.flush()
    opening = _opening_with_directly_pinned_technical_release(db, release.id)

    with pytest.raises(
        ReleaseScopeError,
        match="Pinned technical release contains inactive or missing variants",
    ):
        search_for_opening(db, opening)
    assert search_variants(db, service_type="pipe") == []
    admin_candidates = search_variants(db, service_type="pipe", include_draft=True)
    assert len(admin_candidates) == 1
    assert expected_blocker in admin_candidates[0].blockers
    assert _snapshot_records(db, "technical") == []


def test_active_release_with_a_missing_bound_source_fails_closed(db) -> None:
    release, variant = _active_release_with_variant(db, variant_status="active")
    variant.technical_document_id = "missing-technical-document"
    db.flush()
    opening = _opening_with_directly_pinned_technical_release(db, release.id)

    with pytest.raises(
        ReleaseScopeError,
        match="Pinned technical release contains inactive or missing variants",
    ):
        search_for_opening(db, opening)
    assert search_variants(db, service_type="pipe") == []
    admin_candidates = search_variants(db, service_type="pipe", include_draft=True)
    assert len(admin_candidates) == 1
    assert "source_document_missing" in admin_candidates[0].blockers
    assert _snapshot_records(db, "technical") == []


def test_active_release_with_current_variant_remains_searchable(db) -> None:
    release, variant = _active_release_with_variant(db, variant_status="active")
    opening = _opening_with_directly_pinned_technical_release(db, release.id)

    assert pinned_technical_ids(db, opening.estimate) == {variant.id}
    result = search_for_opening(db, opening)
    assert result["services"][0]["candidates"][0]["variant_id"] == variant.variant_id
    assert "Pinned technical release contains inactive or missing variants." not in (
        validate_estimate_release_basis(db, opening.estimate)
    )
    assert _snapshot_records(db, "technical")[0]["source_binding"] == {
        "schema": "technical-release-source-binding-v1",
        "state": "legacy_unbound",
        "source_locator": {
            "document_reference": None,
            "page": None,
            "table": None,
            "figure": None,
        },
    }


def test_active_release_with_a_current_bound_source_remains_searchable(db) -> None:
    release, variant = _active_release_with_variant(db, variant_status="active")
    variant.technical_document_id = _technical_document(db).id
    db.flush()
    opening = _opening_with_directly_pinned_technical_release(db, release.id)

    assert pinned_technical_ids(db, opening.estimate) == {variant.id}
    result = search_for_opening(db, opening)
    assert result["services"][0]["candidates"][0]["variant_id"] == variant.variant_id
    assert [record["id"] for record in _snapshot_records(db, "technical")] == [variant.id]


def test_technical_snapshot_binds_retained_source_document_file_and_locator(db) -> None:
    _release, variant = _active_release_with_variant(db, variant_status="active")
    document = _technical_document(db)
    stored = db.get(StoredFile, document.stored_file_id)
    assert stored is not None
    document.reference = "ASSESSMENT-2026-001"
    document.revision = "Rev 3"
    variant.technical_document_id = document.id
    variant.source_document_reference = document.document_id
    variant.source_page = "42"
    variant.source_table = "Table 7"
    variant.source_figure = "Figure 2"
    variant.source_hash = stored.sha256
    db.flush()

    record = _snapshot_records(db, "technical")[0]

    assert record["source_binding"] == {
        "schema": "technical-release-source-binding-v1",
        "state": "bound",
        "technical_document": {
            "id": document.id,
            "document_id": document.document_id,
            "reference": "ASSESSMENT-2026-001",
            "revision": "Rev 3",
            "stored_file": {
                "id": stored.id,
                "sha256": stored.sha256,
                "size_bytes": stored.size_bytes,
            },
        },
        "source_locator": {
            "document_reference": document.document_id,
            "page": "42",
            "table": "Table 7",
            "figure": "Figure 2",
        },
    }


def test_pinned_technical_release_rejects_source_lineage_drift(db) -> None:
    release, variant = _active_release_with_variant(db, variant_status="active")
    document = _technical_document(db)
    stored = db.get(StoredFile, document.stored_file_id)
    assert stored is not None
    variant.technical_document_id = document.id
    variant.source_document_reference = document.document_id
    variant.source_page = "42"
    variant.source_hash = stored.sha256
    db.flush()
    manifest = {"records": _snapshot_records(db, "technical")}
    release.source_manifest = manifest
    release.release_hash = _release_manifest_hash(manifest)
    db.flush()
    opening = _opening_with_directly_pinned_technical_release(db, release.id)

    assert pinned_technical_ids(db, opening.estimate) == {variant.id}

    stored.sha256 = "b" * 64
    db.flush()

    with pytest.raises(
        ReleaseScopeError,
        match="Pinned technical release source lineage does not match the published manifest",
    ):
        pinned_technical_ids(db, opening.estimate)


def test_release_basis_refresh_rejects_an_active_release_with_retired_variants(db) -> None:
    _active_release_with_variant(db, variant_status="retired")
    _active_non_technical_releases(db)
    estimate = _editable_estimate(db)

    with pytest.raises(
        ValueError,
        match="Pinned technical release contains inactive or missing variants",
    ):
        pin_current_releases(db, estimate)

    assert all(getattr(estimate, field) is None for field in PIN_FIELDS.values())


def test_release_basis_refresh_pins_an_active_release_with_active_variants(db) -> None:
    release, _variant = _active_release_with_variant(db, variant_status="active")
    _active_non_technical_releases(db)
    estimate = _editable_estimate(db)

    basis = pin_current_releases(db, estimate)

    assert basis["technical"]["release_id"] == release.id
    assert estimate.technical_release_id == release.id
    assert all(getattr(estimate, field) is not None for field in PIN_FIELDS.values())


def test_cli_has_no_activation_override() -> None:
    assert "status" not in signature(import_technical).parameters
    assert "Draft candidates" in (import_technical.__doc__ or "")


def test_non_draft_status_is_rejected_before_file_or_database_access(db, tmp_path) -> None:
    missing = tmp_path / "missing.jsonl"

    with pytest.raises(ValueError, match="Draft candidates only"):
        import_technical_variants(db, missing, version="intake-v1", status="active")

    assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 0
    assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 0


def test_exact_draft_reimport_is_idempotent(db, tmp_path) -> None:
    path, _payload = _source_file(tmp_path, [_active_source_row()])

    first = import_technical_variants(db, path, version="intake-v1")
    second = import_technical_variants(db, path, version="intake-v1")

    assert second["release_id"] == first["release_id"]
    assert second["release_status"] == "draft"
    assert second["import_policy"] == TECHNICAL_IMPORT_POLICY
    assert second["records_inserted"] == 0
    assert second["records_skipped"] == 1
    assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 1
    assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 1


def test_same_version_different_source_hash_fails_without_writes(db, tmp_path) -> None:
    first_path, _payload = _source_file(tmp_path, [_active_source_row()], filename="first.jsonl")
    second_path, _payload = _source_file(
        tmp_path,
        [_active_source_row(variant_id="VAR-002")],
        filename="second.jsonl",
    )
    import_technical_variants(db, first_path, version="intake-v1")

    with pytest.raises(ValueError, match="TECHNICAL_IMPORT_VERSION_COLLISION"):
        import_technical_variants(db, second_path, version="intake-v1")

    assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 1
    assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 1
    assert db.scalar(select(TechnicalVariant.variant_id)) == "VAR-001"


def test_exact_legacy_active_import_requires_explicit_migration(db, tmp_path) -> None:
    path, payload = _source_file(tmp_path, [_active_source_row()])
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    legacy_release = LibraryRelease(
        library_type="technical",
        version="legacy-v1",
        status="active",
        release_hash=digest,
        source_manifest={"filename": path.name, "sha256": digest},
    )
    db.add(legacy_release)
    db.commit()

    with pytest.raises(ValueError, match="LEGACY_TECHNICAL_IMPORT_REQUIRES_MIGRATION"):
        import_technical_variants(db, path, version="legacy-v1")

    db.refresh(legacy_release)
    assert legacy_release.status == "active"
    assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 1
    assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 0


def test_new_import_does_not_mutate_existing_legacy_active_state(db, tmp_path) -> None:
    legacy_digest = hashlib.sha256(b"legacy-source").hexdigest()
    legacy_release = LibraryRelease(
        library_type="technical",
        version="legacy-v1",
        status="active",
        release_hash=legacy_digest,
        source_manifest={"filename": "legacy.jsonl", "sha256": legacy_digest},
    )
    db.add(legacy_release)
    db.flush()
    legacy_variant = TechnicalVariant(
        variant_id="LEGACY-VAR-001",
        system_id="LEGACY-SYS-001",
        status="active",
        expert_review_required=False,
        source_hash="legacy-row-hash",
        source_json={"legacy": True},
        release_id=legacy_release.id,
    )
    db.add(legacy_variant)
    db.commit()
    path, _payload = _source_file(tmp_path, [_active_source_row()])

    result = import_technical_variants(db, path, version="intake-v1")

    db.refresh(legacy_release)
    db.refresh(legacy_variant)
    imported = db.scalar(select(TechnicalVariant).where(TechnicalVariant.variant_id == "VAR-001"))
    assert legacy_release.status == "active"
    assert legacy_variant.status == "active"
    assert imported is not None
    assert imported.status == "draft"
    assert result["release_status"] == "draft"


def test_variant_id_collision_rolls_back_the_new_import_batch(db, tmp_path) -> None:
    first_path, _payload = _source_file(tmp_path, [_active_source_row()], filename="first.jsonl")
    second_path, _payload = _source_file(
        tmp_path,
        [_active_source_row(system_id="DIFFERENT-SYSTEM")],
        filename="second.jsonl",
    )
    import_technical_variants(db, first_path, version="intake-v1")

    with pytest.raises(ValueError, match="TECHNICAL_VARIANT_ID_COLLISION"):
        import_technical_variants(db, second_path, version="intake-v2")

    assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 1
    assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 1
    assert db.scalar(select(TechnicalVariant.system_id)) == "SYS-001"
