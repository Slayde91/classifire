from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from classifire import canonical_models as _canonical_models  # noqa: F401
from classifire import commercial_models as _commercial_models  # noqa: F401
from classifire.db import Base
from classifire.file_hashing import sha256_file
from classifire.importers.technical import import_technical_variants
from classifire.knowledge_migration import (
    MANIFEST_NAME,
    PACKAGE_ID,
    PRICING_RELATIVE,
    PRODUCT,
    SHA256_NAME,
    TECHNICAL_LIBRARY_RELATIVE,
    TECHNICAL_VARIANTS_RELATIVE,
    stage_essentials_archive,
)
from classifire.knowledge_migration import sha256_file as migration_sha256_file
from classifire.models import TechnicalVariant
from classifire.v213_release_validation import sha256_file as release_sha256_file

COLLIDING_ID = "TSL-TEST-COLLISION-VAR01"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_shared_file_hashing_matches_sha256(tmp_path: Path) -> None:
    path = tmp_path / "source.bin"
    payload = b"CLASSIFIRE\x00controlled-source"
    path.write_bytes(payload)

    assert sha256_file(path) == _digest(payload)
    assert migration_sha256_file is sha256_file
    assert release_sha256_file is sha256_file


def _write_archive(path: Path, *, tamper_hash: bool = False, unsafe: bool = False) -> None:
    prefix = "CLASSIFIRE_OpenClaw_Mission_Control_Essentials_v1.0/"
    payloads = {
        PRICING_RELATIVE.as_posix(): b"PKB_Entry_ID\nPKB-1\n",
        TECHNICAL_LIBRARY_RELATIVE.as_posix(): b"technical source\n",
        TECHNICAL_VARIANTS_RELATIVE.as_posix(): b'{"Variant_ID":"V1","System_ID":"S1"}\n',
    }
    files = []
    for name, data in payloads.items():
        digest = (
            "0" * 64
            if tamper_hash and name == PRICING_RELATIVE.as_posix()
            else _digest(data)
        )
        files.append(
            {
                "path": name,
                "sha256": digest,
                "size_bytes": len(data),
                "purpose": "test",
                "source": "test",
            }
        )
    if unsafe:
        files.append(
            {
                "path": "../escape.txt",
                "sha256": _digest(b"escape"),
                "size_bytes": 6,
            }
        )
    manifest = json.dumps(
        {
            "package_id": PACKAGE_ID,
            "product": PRODUCT,
            "files": files,
        },
        indent=2,
    ).encode()
    sums = [f"{_digest(manifest)}  {MANIFEST_NAME}"]
    for name, data in payloads.items():
        sums.append(f"{_digest(data)}  {name}")

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(prefix + MANIFEST_NAME, manifest)
        archive.writestr(prefix + SHA256_NAME, "\n".join(sums) + "\n")
        for name, data in payloads.items():
            archive.writestr(prefix + name, data)


def _write_collision_source(path: Path) -> None:
    rows = [
        {
            "Variant_ID": COLLIDING_ID,
            "System_ID": "TSL-TEST-COLLISION",
            "FRL_Variant": "-/90/90",
            "Variant_Status": "ACTIVE",
            "Search_Index_Status": "ACTIVE",
            "Variant_Content_Hash": "a" * 64,
            "Substrate_Type": "120 mm masonry wall",
        },
        {
            "Variant_ID": COLLIDING_ID,
            "System_ID": "TSL-TEST-COLLISION",
            "FRL_Variant": "-/60/60",
            "Variant_Status": "ACTIVE",
            "Search_Index_Status": "ACTIVE",
            "Variant_Content_Hash": "b" * 64,
            "Substrate_Type": "100 mm masonry wall",
        },
    ]
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _collision_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'collision.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def test_stage_essentials_extracts_and_verifies_controlled_sources(tmp_path: Path) -> None:
    archive_path = tmp_path / "essentials.zip"
    destination = tmp_path / "controlled"
    _write_archive(archive_path)

    staged = stage_essentials_archive(archive_path, destination)

    assert staged.package_id == PACKAGE_ID
    assert staged.product == PRODUCT
    assert staged.pricing_path.read_bytes() == b"PKB_Entry_ID\nPKB-1\n"
    assert staged.technical_library_path.read_text() == "technical source\n"
    assert staged.technical_variants_path.exists()
    assert (destination / "CLASSIFIRE_CONTROLLED_SOURCE_STAGE.json").exists()


def test_stage_essentials_is_idempotent_for_verified_existing_files(tmp_path: Path) -> None:
    archive_path = tmp_path / "essentials.zip"
    destination = tmp_path / "controlled"
    _write_archive(archive_path)

    first = stage_essentials_archive(archive_path, destination)
    second = stage_essentials_archive(archive_path, destination)

    assert first.extracted_files > 0
    assert second.extracted_files == 0
    assert second.verified_files == first.verified_files
    assert (destination / SHA256_NAME).exists()


def test_stage_essentials_rejects_changed_existing_root_control_file(tmp_path: Path) -> None:
    archive_path = tmp_path / "essentials.zip"
    destination = tmp_path / "controlled"
    _write_archive(archive_path)
    stage_essentials_archive(archive_path, destination)

    (destination / SHA256_NAME).write_text("tampered\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="different content"):
        stage_essentials_archive(archive_path, destination)


def test_stage_essentials_rejects_manifest_hash_mismatch(tmp_path: Path) -> None:
    archive_path = tmp_path / "essentials.zip"
    _write_archive(archive_path, tamper_hash=True)

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        stage_essentials_archive(archive_path, tmp_path / "controlled")


def test_stage_essentials_rejects_unsafe_manifest_paths(tmp_path: Path) -> None:
    archive_path = tmp_path / "essentials.zip"
    _write_archive(archive_path, unsafe=True)

    with pytest.raises(ValueError, match="Unsafe archive member path"):
        stage_essentials_archive(archive_path, tmp_path / "controlled")


def test_authorised_material_variant_id_collision_preserves_both_rows(
    tmp_path: Path,
) -> None:
    source = tmp_path / "variants.jsonl"
    _write_collision_source(source)
    Session = _collision_session(tmp_path)

    with Session() as db:
        result = import_technical_variants(
            db,
            source,
            version="test-collision",
            status="draft",
            allowed_identity_collisions={COLLIDING_ID},
        )
        records = list(db.scalars(select(TechnicalVariant)).all())

    assert result["records_inserted"] == 2
    assert result["identity_collisions_remapped"] == 1
    assert len(records) == 2
    original = next(item for item in records if item.variant_id == COLLIDING_ID)
    remapped = next(item for item in records if item.variant_id != COLLIDING_ID)
    assert original.frl == "-/90/90"
    assert remapped.frl == "-/60/60"
    assert remapped.variant_id == f"{COLLIDING_ID}-QFSRC-{'B' * 12}"
    migration = (remapped.source_json or {}).get("CLASSIFIRE_Migration") or {}
    assert migration["source_variant_id"] == COLLIDING_ID
    assert migration["identity_collision"] is True
    assert migration["collision_resolution"] == "deterministic_content_hash_suffix"

    with Session() as db:
        rerun = import_technical_variants(
            db,
            source,
            version="test-collision",
            status="draft",
            allowed_identity_collisions={COLLIDING_ID},
        )
        count = len(list(db.scalars(select(TechnicalVariant)).all()))

    assert rerun["records_inserted"] == 0
    assert rerun["records_skipped"] == 2
    assert rerun["identity_collisions_remapped"] == 1
    assert count == 2


def test_unapproved_material_variant_id_collision_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "variants.jsonl"
    _write_collision_source(source)
    Session = _collision_session(tmp_path)

    with Session() as db:
        with pytest.raises(ValueError, match="collision is not authorised"):
            import_technical_variants(
                db,
                source,
                version="test-unapproved-collision",
                status="draft",
            )
