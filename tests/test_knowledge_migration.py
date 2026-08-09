from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

import pytest

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


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
