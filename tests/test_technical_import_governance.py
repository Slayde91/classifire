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
from classifire.models import LibraryRelease, TechnicalVariant
from classifire.release_admin import _snapshot_records
from classifire.services.release_pinning import active_release
from classifire.services.technical import search_variants


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


def _active_source_row(variant_id="VAR-001", system_id="SYS-001"):
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


def _source_file(tmp_path, rows, filename="technical.jsonl"):
    path = tmp_path / filename
    payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    path.write_text(payload, encoding="utf-8", newline="\n")
    return path, payload


def test_source_activation_flags_cannot_activate_imported_candidate(db, tmp_path):
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


def test_imported_candidate_is_excluded_from_search_and_release_snapshot(db, tmp_path):
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


def test_cli_has_no_activation_override():
    assert "status" not in signature(import_technical).parameters
    assert "Draft candidates" in (import_technical.__doc__ or "")


def test_non_draft_status_is_rejected_before_file_or_database_access(db, tmp_path):
    missing = tmp_path / "missing.jsonl"

    with pytest.raises(ValueError, match="Draft candidates only"):
        import_technical_variants(db, missing, version="intake-v1", status="active")

    assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 0
    assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 0


def test_exact_draft_reimport_is_idempotent(db, tmp_path):
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


def test_same_version_different_source_hash_fails_without_writes(db, tmp_path):
    first_path, _payload = _source_file(
        tmp_path,
        [_active_source_row()],
        filename="first.jsonl",
    )
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


def test_exact_legacy_active_import_requires_explicit_migration(db, tmp_path):
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


def test_new_import_does_not_mutate_existing_legacy_active_state(db, tmp_path):
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


def test_variant_id_collision_rolls_back_the_new_import_batch(db, tmp_path):
    first_path, _payload = _source_file(
        tmp_path,
        [_active_source_row()],
        filename="first.jsonl",
    )
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
