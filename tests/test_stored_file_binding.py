from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from classifire.models import StoredFile
from classifire.services import storage as storage_service
from classifire.services.storage import (
    StoredFileBindingError,
    open_verified_stored_file,
    require_stored_file_binding,
)

PURPOSE = "technical_evidence"


def _retained_file(
    tmp_path: Path,
    *,
    content: bytes = b"governed technical report",
    original_filename: str = "source.PDF",
) -> tuple[Path, Path, StoredFile]:
    root = tmp_path / "storage"
    root.mkdir()
    sha256 = hashlib.sha256(content).hexdigest()
    suffix = Path(original_filename).suffix.lower()
    path = root / sha256[:2] / sha256[2:4] / f"{sha256}{suffix}"
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    stored = StoredFile(
        original_filename=original_filename,
        media_type="application/pdf",
        storage_path=str(path),
        sha256=sha256,
        size_bytes=len(content),
        purpose=PURPOSE,
        malware_scan_status="clean",
        immutable=True,
    )
    return root, path, stored


def _assert_error(stored: StoredFile, root: Path, code: str) -> StoredFileBindingError:
    with pytest.raises(StoredFileBindingError) as caught:
        require_stored_file_binding(stored, storage_root=root, required_purpose=PURPOSE)
    assert caught.value.code == code
    assert str(root) not in str(caught.value)
    return caught.value


def test_returns_frozen_binding_for_exact_retained_bytes(tmp_path: Path) -> None:
    root, path, stored = _retained_file(tmp_path)

    binding = require_stored_file_binding(
        stored,
        storage_root=root,
        required_purpose=PURPOSE,
    )

    assert binding.path == path.resolve(strict=True)
    assert binding.sha256 == stored.sha256
    assert binding.size_bytes == stored.size_bytes
    assert binding.suffix == ".pdf"
    assert binding.purpose == PURPOSE
    with pytest.raises(FrozenInstanceError):
        binding.size_bytes = 0  # type: ignore[misc]


def test_verified_descriptor_can_be_claimed_exactly_once(tmp_path: Path) -> None:
    root, _path, stored = _retained_file(tmp_path)
    stream = open_verified_stored_file(
        stored,
        storage_root=root,
        required_purpose=PURPOSE,
    )

    reader = stream.claim_binary_reader()
    descriptor = reader.fileno()

    assert reader.read() == b"governed technical report"
    assert stream.closed is True
    with pytest.raises(RuntimeError, match="one-shot"):
        stream.claim_binary_reader()
    with pytest.raises(RuntimeError, match="one-shot"):
        next(iter(stream))

    reader.close()
    with pytest.raises(OSError):
        os.fstat(descriptor)


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("purpose", "Technical_Evidence", "STORED_FILE_PURPOSE_MISMATCH"),
        ("immutable", False, "STORED_FILE_NOT_IMMUTABLE"),
        ("malware_scan_status", "Clean", "STORED_FILE_SCAN_NOT_CLEAN"),
        ("sha256", "A" * 64, "STORED_FILE_SHA256_INVALID"),
        ("size_bytes", -1, "STORED_FILE_SIZE_INVALID"),
        ("size_bytes", True, "STORED_FILE_SIZE_INVALID"),
        ("original_filename", "source.exe", "STORED_FILE_SUFFIX_NOT_ALLOWED"),
    ],
)
def test_rejects_noncanonical_record_metadata(
    tmp_path: Path,
    field: str,
    value: object,
    code: str,
) -> None:
    root, _path, stored = _retained_file(tmp_path)
    setattr(stored, field, value)

    _assert_error(stored, root, code)


def test_rejects_outside_and_non_content_addressed_paths_without_leaking_them(
    tmp_path: Path,
) -> None:
    root, _path, stored = _retained_file(tmp_path)
    outside = tmp_path / "secret-customer-report.pdf"
    outside.write_bytes(b"secret")
    stored.storage_path = str(outside)

    error = _assert_error(stored, root, "STORED_FILE_PATH_OUTSIDE_ROOT")

    assert outside.name not in str(error)

    wrong_path = root / "not-content-addressed.pdf"
    wrong_path.write_bytes(b"governed technical report")
    stored.storage_path = str(wrong_path)
    _assert_error(stored, root, "STORED_FILE_PATH_NOT_CANONICAL")


def test_rejects_non_regular_and_missing_canonical_paths(tmp_path: Path) -> None:
    root, path, stored = _retained_file(tmp_path)
    path.unlink()
    path.mkdir()
    _assert_error(stored, root, "STORED_FILE_NOT_REGULAR")

    path.rmdir()
    _assert_error(stored, root, "STORED_FILE_PATH_INVALID")


def test_rejects_size_and_hash_mismatches(tmp_path: Path) -> None:
    root, path, stored = _retained_file(tmp_path)
    path.write_bytes(b"x" * stored.size_bytes)
    _assert_error(stored, root, "STORED_FILE_HASH_MISMATCH")

    path.write_bytes(b"different length")
    _assert_error(stored, root, "STORED_FILE_SIZE_MISMATCH")


def _symlink_or_skip(link: Path, target: Path, *, directory: bool) -> None:
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"Symlinks unavailable on this runner: {exc.__class__.__name__}")


def test_rejects_symlinked_storage_root(tmp_path: Path) -> None:
    root, path, stored = _retained_file(tmp_path)
    linked_root = tmp_path / "linked-storage"
    _symlink_or_skip(linked_root, root, directory=True)
    relative = path.relative_to(root)
    stored.storage_path = str(linked_root / relative)

    _assert_error(stored, linked_root, "STORAGE_ROOT_UNSAFE")


def test_rejects_symlinked_content_address_parent(tmp_path: Path) -> None:
    content = b"governed technical report"
    sha256 = hashlib.sha256(content).hexdigest()
    root = tmp_path / "storage"
    root.mkdir()
    external = tmp_path / "external-prefix"
    (external / sha256[2:4]).mkdir(parents=True)
    path = external / sha256[2:4] / f"{sha256}.pdf"
    path.write_bytes(content)
    _symlink_or_skip(root / sha256[:2], external, directory=True)
    stored = StoredFile(
        original_filename="source.pdf",
        media_type="application/pdf",
        storage_path=str(root / sha256[:2] / sha256[2:4] / f"{sha256}.pdf"),
        sha256=sha256,
        size_bytes=len(content),
        purpose=PURPOSE,
        malware_scan_status="clean",
        immutable=True,
    )

    _assert_error(stored, root, "STORED_FILE_PATH_UNSAFE")


def test_rejects_symlinked_retained_file(tmp_path: Path) -> None:
    content = b"governed technical report"
    sha256 = hashlib.sha256(content).hexdigest()
    root = tmp_path / "storage"
    canonical = root / sha256[:2] / sha256[2:4] / f"{sha256}.pdf"
    canonical.parent.mkdir(parents=True)
    external = tmp_path / "external-report.pdf"
    external.write_bytes(content)
    _symlink_or_skip(canonical, external, directory=False)
    stored = StoredFile(
        original_filename="source.pdf",
        media_type="application/pdf",
        storage_path=str(canonical),
        sha256=sha256,
        size_bytes=len(content),
        purpose=PURPOSE,
        malware_scan_status="clean",
        immutable=True,
    )

    _assert_error(stored, root, "STORED_FILE_PATH_UNSAFE")


@pytest.mark.parametrize(
    ("mode", "attributes"),
    [(stat.S_IFLNK, 0), (stat.S_IFDIR, 0x0400)],
)
def test_link_and_windows_reparse_metadata_are_treated_as_unsafe(
    mode: int,
    attributes: int,
) -> None:
    metadata = cast(
        os.stat_result,
        SimpleNamespace(st_mode=mode, st_file_attributes=attributes),
    )

    assert storage_service._is_link_or_reparse(metadata) is True


def test_rejects_file_changed_while_it_is_being_hashed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, path, stored = _retained_file(tmp_path)
    original_hash = storage_service._sha256_descriptor

    def hash_then_touch(descriptor: int) -> tuple[str, int]:
        result = original_hash(descriptor)
        metadata = path.stat()
        os.utime(
            path,
            ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 2_000_000_000),
        )
        return result

    monkeypatch.setattr(storage_service, "_sha256_descriptor", hash_then_touch)

    _assert_error(stored, root, "STORED_FILE_CHANGED_DURING_VALIDATION")
