from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

PACKAGE_ID = "CLASSIFIRE-OPENCLAW-MISSION-CONTROL-ESSENTIALS-v1.0"
PRODUCT = "CLASSIFIRE"
MANIFEST_NAME = "00_ESSENTIALS_MANIFEST.json"
SHA256_NAME = "SHA256SUMS.txt"

PRICING_RELATIVE = Path("knowledge/libraries/CLASSIFIRE_14_Pricing_Library_v2.13.csv")
TECHNICAL_LIBRARY_RELATIVE = Path(
    "knowledge/libraries/CLASSIFIRE_15_Technical_System_Library_v2.13.txt"
)
TECHNICAL_VARIANTS_RELATIVE = Path(
    "knowledge/libraries/CLASSIFIRE_17_Technical_System_Variants_v2.13.jsonl"
)

CONTROLLED_PREFIXES = (
    "knowledge/source_specification/",
    "knowledge/libraries/",
    "knowledge/validation/",
    "integration/03_KNOWLEDGE_MIGRATION/",
    "integration/09_LIBRARY_ADMIN/",
    "integration/10_TESTS/",
)
CONTROLLED_ROOT_FILES = {
    MANIFEST_NAME,
    SHA256_NAME,
    "00_READ_ME_FIRST.md",
    "00_SOURCE_REVIEW.csv",
    "00_REBRAND_REPORT.csv",
}


@dataclass(frozen=True)
class StagedEssentials:
    archive_sha256: str
    package_id: str
    product: str
    source_root: Path
    manifest_path: Path
    pricing_path: Path
    technical_library_path: Path
    technical_variants_path: Path
    extracted_files: int
    verified_files: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "archive_sha256": self.archive_sha256,
            "package_id": self.package_id,
            "product": self.product,
            "source_root": str(self.source_root),
            "manifest_path": str(self.manifest_path),
            "pricing_path": str(self.pricing_path),
            "technical_library_path": str(self.technical_library_path),
            "technical_variants_path": str(self.technical_variants_path),
            "extracted_files": self.extracted_files,
            "verified_files": self.verified_files,
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe archive member path: {name}")
    return path


def _find_archive_prefix(names: list[str]) -> str:
    matches = []
    for name in names:
        path = _normalise_member(name)
        if path.name == MANIFEST_NAME:
            matches.append(path)
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one {MANIFEST_NAME} in archive; found {len(matches)}."
        )
    parent = matches[0].parent.as_posix()
    return "" if parent == "." else parent.rstrip("/") + "/"


def _read_zip_text(archive: zipfile.ZipFile, member: str) -> str:
    try:
        data = archive.read(member)
    except KeyError as exc:
        raise ValueError(f"Archive is missing required member: {member}") from exc
    return data.decode("utf-8-sig")


def _archive_member_sha256(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    digest = hashlib.sha256()
    with archive.open(info, "r") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_entries(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError("Essentials manifest does not contain a files list.")
    entries: dict[str, dict[str, Any]] = {}
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("Essentials manifest contains a non-object file entry.")
        raw_path = item.get("path")
        expected_hash = item.get("sha256")
        expected_size = item.get("size_bytes")
        if not isinstance(raw_path, str) or not isinstance(expected_hash, str):
            raise ValueError("Essentials manifest contains an invalid file entry.")
        path = _normalise_member(raw_path).as_posix()
        entries[path] = {
            **item,
            "path": path,
            "sha256": expected_hash.lower(),
            "size_bytes": int(expected_size) if expected_size is not None else None,
        }
    return entries


def _should_stage(path: str) -> bool:
    return path in CONTROLLED_ROOT_FILES or any(
        path.startswith(prefix) for prefix in CONTROLLED_PREFIXES
    )


def stage_essentials_archive(
    archive_path: Path,
    destination_root: Path,
    *,
    overwrite: bool = False,
) -> StagedEssentials:
    archive_path = archive_path.expanduser().resolve()
    destination_root = destination_root.expanduser().resolve()
    if not archive_path.is_file():
        raise FileNotFoundError(f"Essentials archive not found: {archive_path}")

    archive_hash = sha256_file(archive_path)
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        prefix = _find_archive_prefix(names)
        manifest_member = prefix + MANIFEST_NAME
        manifest = json.loads(_read_zip_text(archive, manifest_member))
        if manifest.get("package_id") != PACKAGE_ID:
            raise ValueError(
                f"Unexpected essentials package_id: {manifest.get('package_id')!r}."
            )
        if manifest.get("product") != PRODUCT:
            raise ValueError(f"Unexpected essentials product: {manifest.get('product')!r}.")
        entries = _manifest_entries(manifest)

        required_paths = {
            PRICING_RELATIVE.as_posix(),
            TECHNICAL_LIBRARY_RELATIVE.as_posix(),
            TECHNICAL_VARIANTS_RELATIVE.as_posix(),
        }
        missing_manifest = sorted(required_paths.difference(entries))
        if missing_manifest:
            raise ValueError(
                "Essentials manifest is missing required controlled library entries: "
                + ", ".join(missing_manifest)
            )

        stage_entries = {
            path: meta for path, meta in entries.items() if _should_stage(path)
        }
        sha_text = _read_zip_text(archive, prefix + SHA256_NAME)
        sums: dict[str, str] = {}
        for raw_line in sha_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            digest, sep, raw_path = line.partition("  ")
            if not sep:
                raise ValueError(f"Malformed SHA256SUMS entry: {raw_line!r}")
            sums[_normalise_member(raw_path).as_posix()] = digest.lower()

        destination_root.mkdir(parents=True, exist_ok=True)
        extracted = 0
        verified = 0

        candidates = set(stage_entries)
        candidates.update(
            path for path in CONTROLLED_ROOT_FILES if prefix + path in names
        )
        for relative in sorted(candidates):
            member = prefix + relative
            try:
                info = archive.getinfo(member)
            except KeyError as exc:
                raise ValueError(f"Archive is missing staged member: {relative}") from exc
            if info.is_dir():
                continue
            target = destination_root / Path(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and not overwrite:
                existing_hash = sha256_file(target)
                expected = (
                    stage_entries.get(relative, {}).get("sha256") or sums.get(relative)
                )
                # Some controlled root files (notably SHA256SUMS.txt) cannot
                # carry their own digest in the checksum list and may not be
                # listed in the manifest. For those files, compare the staged
                # bytes directly with the authoritative archive member so a
                # verified second run is idempotent without requiring overwrite.
                if expected is None:
                    expected = _archive_member_sha256(archive, info)
                if existing_hash == expected and target.stat().st_size == info.file_size:
                    verified += 1
                    continue
                raise FileExistsError(
                    f"Controlled source already exists with different content: {target}. "
                    "Use overwrite=True only for an intentional restage."
                )

            digest = hashlib.sha256()
            size = 0
            temp = target.with_suffix(target.suffix + ".tmp")
            with archive.open(info, "r") as source, temp.open("wb") as output:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    size += len(chunk)
                    output.write(chunk)

            expected_meta = stage_entries.get(relative)
            expected_hash = (
                expected_meta.get("sha256") if expected_meta else sums.get(relative)
            )
            actual_hash = digest.hexdigest()
            if expected_hash is None:
                expected_hash = actual_hash
            expected_size = expected_meta.get("size_bytes") if expected_meta else info.file_size
            if actual_hash != expected_hash:
                temp.unlink(missing_ok=True)
                raise ValueError(
                    f"SHA-256 mismatch for {relative}: expected {expected_hash}, "
                    f"got {actual_hash}."
                )
            if expected_size is not None and size != expected_size:
                temp.unlink(missing_ok=True)
                raise ValueError(
                    f"Size mismatch for {relative}: expected {expected_size}, got {size}."
                )
            temp.replace(target)
            extracted += 1
            verified += 1

        migration_record = {
            "schema": "CLASSIFIRE-CONTROLLED-SOURCE-STAGE-v1",
            "archive": str(archive_path),
            "archive_sha256": archive_hash,
            "package_id": PACKAGE_ID,
            "product": PRODUCT,
            "verified_files": verified,
            "extracted_files": extracted,
            "manifest_sha256": sha256_file(destination_root / MANIFEST_NAME),
            "libraries": {
                "package_14_pricing": str(destination_root / PRICING_RELATIVE),
                "package_15_technical_source": str(
                    destination_root / TECHNICAL_LIBRARY_RELATIVE
                ),
                "package_17_technical_variants": str(
                    destination_root / TECHNICAL_VARIANTS_RELATIVE
                ),
            },
        }
        record_path = destination_root / "CLASSIFIRE_CONTROLLED_SOURCE_STAGE.json"
        record_path.write_text(json.dumps(migration_record, indent=2), encoding="utf-8")

    return StagedEssentials(
        archive_sha256=archive_hash,
        package_id=PACKAGE_ID,
        product=PRODUCT,
        source_root=destination_root,
        manifest_path=destination_root / MANIFEST_NAME,
        pricing_path=destination_root / PRICING_RELATIVE,
        technical_library_path=destination_root / TECHNICAL_LIBRARY_RELATIVE,
        technical_variants_path=destination_root / TECHNICAL_VARIANTS_RELATIVE,
        extracted_files=extracted,
        verified_files=verified,
    )
