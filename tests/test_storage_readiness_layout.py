from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from classifire.services import storage as storage_service
from classifire.services.storage import (
    StorageReadinessError,
    require_storage_root_readiness,
)

_NONCE = b"layout-probe-001"
_PAYLOAD = b"CLASSIFIRE storage readiness probe\n" + _NONCE
_DIGEST = hashlib.sha256(_PAYLOAD).hexdigest()
_RAW_ERROR_SECRET = "private-storage-path-and-host-detail"  # noqa: S105


def _fixed_nonce(length: int) -> bytes:
    assert length == len(_NONCE)
    return _NONCE


def _assert_unsafe(call: object) -> StorageReadinessError:
    with pytest.raises(StorageReadinessError) as caught:
        call()  # type: ignore[operator]
    assert caught.value.code == "STORAGE_ROOT_UNSAFE"
    assert _RAW_ERROR_SECRET not in str(caught.value)
    return caught.value


def test_probe_exercises_upload_layout_and_leaves_empty_root_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "storage"
    root.mkdir()
    links: list[tuple[Path, Path, bool]] = []
    verified_paths: list[Path] = []
    original_link = storage_service.os.link
    original_verify = storage_service._verify_retained_bytes

    def record_link(
        source: str | os.PathLike[str],
        destination: str | os.PathLike[str],
        *,
        follow_symlinks: bool = True,
    ) -> None:
        links.append((Path(source), Path(destination), follow_symlinks))
        original_link(source, destination, follow_symlinks=follow_symlinks)

    def record_verify(
        verified_root: Path,
        path: Path,
        metadata: os.stat_result,
    ) -> tuple[str, int]:
        assert verified_root == root
        verified_paths.append(path)
        return original_verify(verified_root, path, metadata)

    monkeypatch.setattr(storage_service.os, "urandom", _fixed_nonce)
    monkeypatch.setattr(storage_service.os, "link", record_link)
    monkeypatch.setattr(storage_service, "_verify_retained_bytes", record_verify)

    assert require_storage_root_readiness(root) == "STORAGE_READY"

    assert len(links) == 1
    source, destination, follow_symlinks = links[0]
    assert source.parent == root / ".incoming"
    assert source.suffix == ".part"
    assert destination == root / _DIGEST[:2] / _DIGEST[2:4] / f"{_DIGEST}.link"
    assert follow_symlinks is False
    assert verified_paths == [source, destination]
    assert tuple(root.iterdir()) == ()


def test_probe_preserves_preexisting_upload_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "storage"
    spool = root / ".incoming"
    final_dir = root / _DIGEST[:2] / _DIGEST[2:4]
    spool.mkdir(parents=True)
    final_dir.mkdir(parents=True)
    marker = spool / "preexisting.marker"
    marker.write_text("preserve", encoding="utf-8")
    before = tuple(sorted(path.relative_to(root) for path in root.rglob("*")))
    monkeypatch.setattr(storage_service.os, "urandom", _fixed_nonce)

    assert require_storage_root_readiness(root) == "STORAGE_READY"

    assert tuple(sorted(path.relative_to(root) for path in root.rglob("*"))) == before
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_probe_nonce_failure_is_stable_and_leaves_no_residue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "storage"
    root.mkdir()

    def fail_nonce(_length: int) -> bytes:
        raise OSError(_RAW_ERROR_SECRET)

    monkeypatch.setattr(storage_service.os, "urandom", fail_nonce)

    with pytest.raises(StorageReadinessError) as caught:
        require_storage_root_readiness(root)

    assert caught.value.code == "STORAGE_PROBE_FAILED"
    assert _RAW_ERROR_SECRET not in str(caught.value)
    assert tuple(root.iterdir()) == ()


def test_probe_rejects_regular_file_incoming_directory(
    tmp_path: Path,
) -> None:
    root = tmp_path / "storage"
    root.mkdir()
    incoming = root / ".incoming"
    incoming.write_text(_RAW_ERROR_SECRET, encoding="utf-8")

    caught = _assert_unsafe(lambda: require_storage_root_readiness(root))

    assert str(root) not in str(caught)
    assert incoming.read_text(encoding="utf-8") == _RAW_ERROR_SECRET


@pytest.mark.parametrize("blocked_component", ["first", "second"])
def test_probe_rejects_regular_file_in_nested_hash_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    blocked_component: str,
) -> None:
    root = tmp_path / "storage"
    root.mkdir()
    first_prefix = root / _DIGEST[:2]
    if blocked_component == "first":
        blocked = first_prefix
    else:
        first_prefix.mkdir()
        blocked = first_prefix / _DIGEST[2:4]
    blocked.write_text(_RAW_ERROR_SECRET, encoding="utf-8")
    monkeypatch.setattr(storage_service.os, "urandom", _fixed_nonce)

    caught = _assert_unsafe(lambda: require_storage_root_readiness(root))

    assert str(root) not in str(caught)
    assert blocked.read_text(encoding="utf-8") == _RAW_ERROR_SECRET
    assert not (root / ".incoming").exists()


@pytest.mark.parametrize("linked_component", ["incoming", "first_prefix"])
def test_probe_rejects_link_or_reparse_upload_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    linked_component: str,
) -> None:
    root = tmp_path / "storage"
    target = tmp_path / "outside-target"
    root.mkdir()
    target.mkdir()
    linked = root / (".incoming" if linked_component == "incoming" else _DIGEST[:2])
    try:
        os.symlink(target, linked, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks unavailable: {type(exc).__name__}")
    monkeypatch.setattr(storage_service.os, "urandom", _fixed_nonce)

    caught = _assert_unsafe(lambda: require_storage_root_readiness(root))

    assert str(root) not in str(caught)
    assert linked.is_symlink()
    assert tuple(target.iterdir()) == ()


@pytest.mark.parametrize("unsafe_component", ["incoming", "first_prefix", "second_prefix"])
def test_probe_rejects_component_classified_as_reparse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unsafe_component: str,
) -> None:
    root = tmp_path / "storage"
    incoming = root / ".incoming"
    first_prefix = root / _DIGEST[:2]
    second_prefix = first_prefix / _DIGEST[2:4]
    second_prefix.mkdir(parents=True)
    incoming.mkdir()
    selected = {
        "incoming": incoming,
        "first_prefix": first_prefix,
        "second_prefix": second_prefix,
    }[unsafe_component]
    selected_metadata = os.lstat(selected)
    selected_identity = (selected_metadata.st_dev, selected_metadata.st_ino)
    original_classifier = storage_service._is_link_or_reparse

    def classify_selected_as_reparse(metadata: os.stat_result) -> bool:
        identity = (metadata.st_dev, metadata.st_ino)
        return identity == selected_identity or original_classifier(metadata)

    monkeypatch.setattr(storage_service.os, "urandom", _fixed_nonce)
    monkeypatch.setattr(
        storage_service,
        "_is_link_or_reparse",
        classify_selected_as_reparse,
    )

    caught = _assert_unsafe(lambda: require_storage_root_readiness(root))

    assert str(root) not in str(caught)
    assert selected.is_dir()


def test_probe_directory_cleanup_failure_is_stable_and_path_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "storage"
    incoming = root / ".incoming"
    root.mkdir()
    original_os_rmdir = os.rmdir

    def fail_os_rmdir(
        path: str | os.PathLike[str],
        *,
        dir_fd: int | None = None,
    ) -> None:
        if Path(path) == incoming:
            raise OSError(_RAW_ERROR_SECRET)
        original_os_rmdir(path, dir_fd=dir_fd)

    monkeypatch.setattr(storage_service.os, "urandom", _fixed_nonce)
    monkeypatch.setattr(storage_service.os, "rmdir", fail_os_rmdir)
    try:
        with pytest.raises(StorageReadinessError) as caught:
            require_storage_root_readiness(root)
    finally:
        monkeypatch.undo()
        if incoming.exists():
            incoming.rmdir()

    assert caught.value.code == "STORAGE_PROBE_CLEANUP_FAILED"
    assert _RAW_ERROR_SECRET not in str(caught.value)
    assert str(root) not in str(caught.value)
    assert tuple(root.iterdir()) == ()
