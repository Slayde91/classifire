from __future__ import annotations

import hashlib
import inspect
import json
import os
import stat
import struct
import zlib
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import inspect as sqlalchemy_inspect

from classifire.services import technical_extraction_artifacts as artifact_storage
from classifire.services.technical_extraction_artifacts import (
    TECHNICAL_DERIVED_ARTIFACT_SUBTREE,
    TechnicalExtractionArtifactError,
    build_unflushed_technical_derived_artifact_rows,
    cleanup_retained_technical_page_artifacts,
    open_verified_technical_derived_artifact,
    retain_validated_technical_page_artifacts,
)
from classifire.services.technical_page_evidence import (
    TECHNICAL_PAGE_EVIDENCE_MAX_BYTES,
    TechnicalPageEvidenceError,
)

DOCUMENT_ID = "11111111-1111-4111-8111-111111111111"
RUN_ID = "33333333-3333-4333-8333-333333333333"
PACKET_ARTIFACT_ID = "44444444-4444-4444-8444-444444444444"
IMAGE_ARTIFACT_ID = "55555555-5555-4555-8555-555555555555"
SOURCE_SHA256 = "a" * 64
SOURCE_SIZE_BYTES = 123_456
POLICY_VERSION = "technical-extraction-policy-v1"
POLICY_BYTES = b'{"policy":"technical-extraction-policy-v1"}'
POLICY_SHA256 = hashlib.sha256(POLICY_BYTES).hexdigest()
WORKER_IMAGE_DIGEST = "d" * 64
PAGE_NUMBER = 2
PAGE_COUNT = 4


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return len(data).to_bytes(4, "big") + chunk_type + data + crc.to_bytes(4, "big")


def _png(*, width: int = 8, height: int = 6) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(b"\x00"))
        + _png_chunk(b"IEND", b"")
    )


def _packet(image: bytes, *, native_text: str = "Test evidence") -> bytes:
    packet = {
        "schema": "technical-page-evidence-v1",
        "source": {
            "technical_document_id": DOCUMENT_ID,
            "sha256": SOURCE_SHA256,
            "size_bytes": SOURCE_SIZE_BYTES,
        },
        "page": {
            "number": PAGE_NUMBER,
            "count": PAGE_COUNT,
            "width_points": 612,
            "height_points": 792,
            "image": {
                "sha256": hashlib.sha256(image).hexdigest(),
                "size_bytes": len(image),
                "width_pixels": 8,
                "height_pixels": 6,
            },
        },
        "extraction": {
            "policy_version": POLICY_VERSION,
            "policy_sha256": POLICY_SHA256,
            "worker_image_digest": WORKER_IMAGE_DIGEST,
            "ocr_low_confidence_threshold": 80,
            "native_text_blocks": [
                {
                    "bbox": {"x0": 10, "x1": 100, "y0": 20, "y1": 40},
                    "id": "native-1",
                    "order": 1,
                    "text": native_text,
                }
            ],
            "ocr": {
                "status": "ocr_not_required",
                "engine": None,
                "engine_version": None,
                "language": None,
                "image_sha256": None,
                "blocks": [],
            },
            "human_review_required": False,
            "warnings": [],
        },
    }
    return json.dumps(
        packet,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _retain(
    storage_root: Path,
    *,
    raw: bytes | None = None,
    image: bytes | None = None,
    packet_artifact_id: str | None = PACKET_ARTIFACT_ID,
    page_image_artifact_id: str | None = IMAGE_ARTIFACT_ID,
    allow_existing_artifact_replay: bool = False,
):
    page_image = _png() if image is None else image
    packet = _packet(page_image) if raw is None else raw
    return retain_validated_technical_page_artifacts(
        packet,
        page_image_bytes=page_image,
        storage_root=storage_root,
        run_id=RUN_ID,
        expected_technical_document_id=DOCUMENT_ID,
        expected_source_sha256=SOURCE_SHA256,
        expected_source_size_bytes=SOURCE_SIZE_BYTES,
        expected_page_number=PAGE_NUMBER,
        expected_page_count=PAGE_COUNT,
        expected_page_width_points=Decimal("612"),
        expected_page_height_points=Decimal("792"),
        expected_page_image_sha256=hashlib.sha256(page_image).hexdigest(),
        expected_page_image_size_bytes=len(page_image),
        expected_page_image_width_pixels=8,
        expected_page_image_height_pixels=6,
        expected_extraction_policy=POLICY_VERSION,
        expected_extraction_policy_bytes=POLICY_BYTES,
        expected_extraction_policy_sha256=POLICY_SHA256,
        expected_worker_image_digest=WORKER_IMAGE_DIGEST,
        expected_ocr_low_confidence_threshold=Decimal("80"),
        packet_artifact_id=packet_artifact_id,
        page_image_artifact_id=page_image_artifact_id,
        allow_existing_artifact_replay=allow_existing_artifact_replay,
    )


def _assert_artifact_error(
    expected_code: str,
    operation,  # type: ignore[no-untyped-def]
) -> TechnicalExtractionArtifactError:
    with pytest.raises(TechnicalExtractionArtifactError) as caught:
        operation()
    assert caught.value.code == expected_code
    assert str(caught.value) == expected_code
    assert "\\" not in str(caught.value)
    assert "/" not in str(caught.value)
    return caught.value


def test_valid_retention_open_and_transient_rows_are_exact(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    image = _png()
    raw = _packet(image)

    retained = _retain(storage_root, raw=raw, image=image)

    assert retained.evidence.packet_sha256 == hashlib.sha256(raw).hexdigest()
    assert retained.packet.sha256 == hashlib.sha256(raw).hexdigest()
    assert retained.packet.size_bytes == len(raw)
    assert retained.packet.media_type == "application/json"
    assert retained.page_image.sha256 == hashlib.sha256(image).hexdigest()
    assert retained.page_image.size_bytes == len(image)
    assert retained.page_image.media_type == "image/png"
    for binding, exact_bytes in ((retained.packet, raw), (retained.page_image, image)):
        assert binding.path.is_absolute()
        assert binding.path.is_relative_to(storage_root)
        assert TECHNICAL_DERIVED_ARTIFACT_SUBTREE in binding.path.parts
        assert RUN_ID in binding.path.parts
        assert f"page-{PAGE_NUMBER:04d}" in binding.path.parts
        assert binding.artifact_id in binding.path.parts
        assert binding.path.name.startswith(binding.sha256)
        assert binding.path.read_bytes() == exact_bytes
        with open_verified_technical_derived_artifact(
            binding,
            storage_root=storage_root,
        ) as verified:
            assert b"".join(verified) == exact_bytes

    packet_row, image_row = build_unflushed_technical_derived_artifact_rows(retained)
    assert sqlalchemy_inspect(packet_row).transient
    assert sqlalchemy_inspect(image_row).transient
    assert packet_row.id == PACKET_ARTIFACT_ID
    assert image_row.id == IMAGE_ARTIFACT_ID
    assert packet_row.storage_path == retained.packet.storage_path
    assert image_row.storage_path == retained.page_image.storage_path
    with pytest.raises(FrozenInstanceError):
        retained.packet.size_bytes = 1  # type: ignore[misc]


def test_malformed_packet_creates_no_retention_files_or_subtree(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    image = _png()
    malformed = _packet(image)[:-1]

    with pytest.raises(TechnicalPageEvidenceError):
        _retain(storage_root, raw=malformed, image=image)

    assert not (storage_root / TECHNICAL_DERIVED_ARTIFACT_SUBTREE).exists()
    assert list(storage_root.rglob("*")) == []


def test_second_promotion_failure_rolls_back_first_and_all_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    real_link = os.link
    calls = 0

    def fail_second_link(
        source: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        destination: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        *,
        follow_symlinks: bool = True,
    ) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated second promotion failure")
        real_link(source, destination, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(artifact_storage.os, "link", fail_second_link)

    _assert_artifact_error(
        "TECHNICAL_ARTIFACT_STORAGE_FAILURE",
        lambda: _retain(storage_root),
    )

    assert calls == 2
    assert [path for path in storage_root.rglob("*") if path.is_file()] == []


def test_create_new_collision_never_reuses_or_overwrites_existing_bytes(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    image = _png()
    raw = _packet(image)
    first = _retain(storage_root, raw=raw, image=image)
    before = {
        first.packet.path: first.packet.path.read_bytes(),
        first.page_image.path: first.page_image.path.read_bytes(),
    }

    _assert_artifact_error(
        "TECHNICAL_ARTIFACT_PATH_COLLISION",
        lambda: _retain(storage_root, raw=raw, image=image),
    )

    assert {path: path.read_bytes() for path in before} == before
    files = [path for path in storage_root.rglob("*") if path.is_file()]
    assert sorted(files) == sorted(before)


def test_opt_in_exact_replay_reuses_verified_files_and_cleanup_leaves_them(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    image = _png()
    raw = _packet(image)
    first = _retain(
        storage_root,
        raw=raw,
        image=image,
        allow_existing_artifact_replay=True,
    )
    before = {
        first.packet.path: first.packet.path.read_bytes(),
        first.page_image.path: first.page_image.path.read_bytes(),
    }
    assert all(binding.promoted_file for binding in first.bindings)

    replayed = _retain(
        storage_root,
        raw=raw,
        image=image,
        allow_existing_artifact_replay=True,
    )

    assert replayed.evidence == first.evidence
    assert all(not binding.promoted_file for binding in replayed.bindings)
    assert [
        (
            binding.artifact_id,
            binding.storage_path,
            binding.sha256,
            binding.size_bytes,
        )
        for binding in replayed.bindings
    ] == [
        (
            binding.artifact_id,
            binding.storage_path,
            binding.sha256,
            binding.size_bytes,
        )
        for binding in first.bindings
    ]
    assert (
        cleanup_retained_technical_page_artifacts(
            replayed,
            storage_root=storage_root,
            database_outcome="known_rollback",
        )
        == ()
    )
    assert {path: path.read_bytes() for path in before} == before
    assert sorted(path for path in storage_root.rglob("*") if path.is_file()) == sorted(before)


def test_opt_in_replay_rejects_divergent_sha_path_without_creating_a_sibling(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    image = _png()
    first_raw = _packet(image)
    divergent_raw = _packet(image, native_text="Different valid evidence")
    first = _retain(storage_root, raw=first_raw, image=image)
    assert hashlib.sha256(divergent_raw).digest() != hashlib.sha256(first_raw).digest()

    _assert_artifact_error(
        "TECHNICAL_ARTIFACT_PATH_COLLISION",
        lambda: _retain(
            storage_root,
            raw=divergent_raw,
            image=image,
            allow_existing_artifact_replay=True,
        ),
    )

    assert first.packet.path.read_bytes() == first_raw
    assert first.page_image.path.read_bytes() == image
    assert [path for path in first.packet.path.parent.iterdir()] == [first.packet.path]


def test_opt_in_replay_rejects_changed_existing_bytes(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    image = _png()
    raw = _packet(image)
    first = _retain(storage_root, raw=raw, image=image)
    changed = bytearray(raw)
    changed[-2] ^= 1
    first.packet.path.write_bytes(changed)

    _assert_artifact_error(
        "TECHNICAL_ARTIFACT_CONTENT_MISMATCH",
        lambda: _retain(
            storage_root,
            raw=raw,
            image=image,
            allow_existing_artifact_replay=True,
        ),
    )

    assert first.packet.path.read_bytes() == changed
    assert first.page_image.path.read_bytes() == image


def test_opt_in_replay_rejects_extra_sibling_without_removing_prior_reuse(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    image = _png()
    raw = _packet(image)
    first = _retain(storage_root, raw=raw, image=image)
    sibling = first.page_image.path.parent / "unexpected-sibling.png"
    sibling.write_bytes(b"unmanaged")

    _assert_artifact_error(
        "TECHNICAL_ARTIFACT_PATH_COLLISION",
        lambda: _retain(
            storage_root,
            raw=raw,
            image=image,
            allow_existing_artifact_replay=True,
        ),
    )

    assert first.packet.path.read_bytes() == raw
    assert first.page_image.path.read_bytes() == image
    assert sibling.read_bytes() == b"unmanaged"
    assert sorted(path for path in storage_root.rglob("*") if path.is_file()) == sorted(
        (first.packet.path, first.page_image.path, sibling)
    )


def test_opt_in_replay_rejects_unsafe_target_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    image = _png()
    raw = _packet(image)
    first = _retain(storage_root, raw=raw, image=image)
    real_lstat = os.lstat

    def simulate_unsafe_target(path):  # type: ignore[no-untyped-def]
        metadata = real_lstat(path)
        if Path(path) == first.packet.path:
            return SimpleNamespace(
                st_file_attributes=0,
                st_mode=stat.S_IFLNK | stat.S_IMODE(metadata.st_mode),
            )
        return metadata

    monkeypatch.setattr(artifact_storage.os, "lstat", simulate_unsafe_target)

    _assert_artifact_error(
        "TECHNICAL_ARTIFACT_PATH_UNSAFE",
        lambda: _retain(
            storage_root,
            raw=raw,
            image=image,
            allow_existing_artifact_replay=True,
        ),
    )

    assert first.packet.path.read_bytes() == raw
    assert first.page_image.path.read_bytes() == image


def test_second_promotion_collision_removes_only_new_first_promotion(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    image = _png()
    raw = _packet(image)
    first = _retain(storage_root, raw=raw, image=image)
    first.packet.path.unlink()
    existing_image = first.page_image.path.read_bytes()

    _assert_artifact_error(
        "TECHNICAL_ARTIFACT_PATH_COLLISION",
        lambda: _retain(storage_root, raw=raw, image=image),
    )

    assert not first.packet.path.exists()
    assert first.page_image.path.read_bytes() == existing_image
    files = [path for path in storage_root.rglob("*") if path.is_file()]
    assert files == [first.page_image.path]


def test_escaped_promotion_is_rejected_without_deleting_unverified_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    escaped_root = tmp_path / "escaped"
    escaped_root.mkdir()
    real_link = os.link
    escaped_target: Path | None = None

    def simulate_parent_reparse_swap(
        source: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        destination: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        *,
        follow_symlinks: bool = True,
    ) -> None:
        nonlocal escaped_target
        # This deterministically models the result of a parent directory being
        # replaced by a reparse point between validation and a path-based link.
        escaped_target = escaped_root / Path(destination).name
        real_link(source, escaped_target, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(
        artifact_storage.os,
        "link",
        simulate_parent_reparse_swap,
    )

    caught = _assert_artifact_error(
        "TECHNICAL_ARTIFACT_CLEANUP_REFUSED",
        lambda: _retain(storage_root),
    )

    assert caught.prior_code == "TECHNICAL_ARTIFACT_PATH_INVALID"
    assert escaped_target is not None
    assert escaped_target.exists()
    assert escaped_target.read_bytes() == _packet(_png())
    assert [path for path in storage_root.rglob("*") if path.is_file()] == []


def test_open_rejects_tampered_bytes_path_substitution_and_escape(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    image = _png()
    raw = _packet(image)
    retained = _retain(storage_root, raw=raw, image=image)
    packet_row, _ = build_unflushed_technical_derived_artifact_rows(retained)

    changed = bytearray(raw)
    changed[-2] ^= 1
    retained.packet.path.write_bytes(changed)
    _assert_artifact_error(
        "TECHNICAL_ARTIFACT_CONTENT_MISMATCH",
        lambda: open_verified_technical_derived_artifact(
            retained.packet,
            storage_root=storage_root,
        ),
    )

    packet_row.storage_path = retained.page_image.storage_path
    _assert_artifact_error(
        "TECHNICAL_ARTIFACT_PATH_NOT_CANONICAL",
        lambda: open_verified_technical_derived_artifact(
            packet_row,
            storage_root=storage_root,
        ),
    )
    packet_row.storage_path = str(tmp_path / "outside.json")
    _assert_artifact_error(
        "TECHNICAL_ARTIFACT_PATH_OUTSIDE_ROOT",
        lambda: open_verified_technical_derived_artifact(
            packet_row,
            storage_root=storage_root,
        ),
    )


def test_open_rejects_symlink_or_reparse_substitution(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    retained = _retain(storage_root)
    outside = tmp_path / "outside.json"
    outside.write_bytes(retained.packet.path.read_bytes())
    retained.packet.path.unlink()
    try:
        retained.packet.path.symlink_to(outside)
    except OSError:
        pytest.skip("This Windows account cannot create a test symlink")

    _assert_artifact_error(
        "TECHNICAL_ARTIFACT_PATH_UNSAFE",
        lambda: open_verified_technical_derived_artifact(
            retained.packet,
            storage_root=storage_root,
        ),
    )


def test_cleanup_retains_unknown_commit_and_removes_only_exact_new_files(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    retained = _retain(storage_root)
    unrelated = retained.packet.path.parent / "operator-note.txt"
    unrelated.write_bytes(b"not managed by artifact cleanup")

    assert (
        cleanup_retained_technical_page_artifacts(
            retained,
            storage_root=storage_root,
            database_outcome="commit_outcome_unknown",
        )
        == ()
    )
    assert all(binding.path.exists() for binding in retained.bindings)

    removed = cleanup_retained_technical_page_artifacts(
        retained,
        storage_root=storage_root,
        database_outcome="known_rollback",
    )
    assert removed == (PACKET_ARTIFACT_ID, IMAGE_ARTIFACT_ID)
    assert all(not binding.path.exists() for binding in retained.bindings)
    assert unrelated.read_bytes() == b"not managed by artifact cleanup"

    _assert_artifact_error(
        "TECHNICAL_ARTIFACT_CLEANUP_REFUSED",
        lambda: cleanup_retained_technical_page_artifacts(
            retained,
            storage_root=storage_root,
            database_outcome="known_rollback",
        ),
    )


def test_cleanup_refuses_to_delete_changed_promoted_bytes(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    retained = _retain(storage_root)
    retained.packet.path.write_bytes(b"changed after promotion")

    caught = _assert_artifact_error(
        "TECHNICAL_ARTIFACT_CLEANUP_REFUSED",
        lambda: cleanup_retained_technical_page_artifacts(
            retained,
            storage_root=storage_root,
            database_outcome="known_rollback",
        ),
    )

    assert caught.prior_code == "TECHNICAL_ARTIFACT_CONTENT_MISMATCH"
    assert retained.packet.path.exists()
    assert retained.page_image.path.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("media_type", "text/plain"),
        ("sha256", "A" * 64),
        ("size_bytes", TECHNICAL_PAGE_EVIDENCE_MAX_BYTES + 1),
        ("immutable", False),
        ("validation_policy", "untrusted-validator"),
    ],
)
def test_open_enforces_exact_packet_record_contract(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    retained = _retain(storage_root)
    changed = replace(retained.packet, **{field: value})

    _assert_artifact_error(
        "TECHNICAL_ARTIFACT_RECORD_INVALID",
        lambda: open_verified_technical_derived_artifact(
            changed,
            storage_root=storage_root,
        ),
    )


def test_service_is_authority_neutral_and_has_no_database_transaction_power(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    retained = _retain(storage_root)
    rows = build_unflushed_technical_derived_artifact_rows(retained)

    assert all(sqlalchemy_inspect(row).transient for row in rows)
    assert {row.artifact_kind for row in rows} == {
        "page_evidence_json",
        "page_image_png",
    }
    source = inspect.getsource(artifact_storage)
    assert "TechnicalVariant" not in source
    assert "TechnicalDocumentApproval" not in source
    assert "LibraryRelease" not in source
    assert ".commit(" not in source
    assert ".flush(" not in source
