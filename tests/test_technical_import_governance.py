from __future__ import annotations

import hashlib
import json
from inspect import signature

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
from classifire.models import Estimate, LibraryRelease, Opening, Project, Service, TechnicalVariant
from classifire.release_admin import _snapshot_records
from classifire.services.release_pinning import active_release, validate_estimate_release_basis
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
    tmp_path,
    rows: list[dict[str, str]],
    filename: str = "technical.jsonl",
) -> tuple[object, str]:
    path = tmp_path / filename
    payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    path.write_text(payload, encoding="utf-8", newline="\n")
    return path, payload


def _release_manifest_hash(manifest: dict[str, object]) -> str:
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


def test_active_release_with_current_variant_remains_searchable(db) -> None:
    release, variant = _active_release_with_variant(db, variant_status="active")
    opening = _opening_with_directly_pinned_technical_release(db, release.id)

    assert pinned_technical_ids(db, opening.estimate) == {variant.id}
    result = search_for_opening(db, opening)
    assert result["services"][0]["candidates"][0]["variant_id"] == variant.variant_id
    assert "Pinned technical release contains inactive or missing variants." not in (
        validate_estimate_release_basis(db, opening.estimate)
    )


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
