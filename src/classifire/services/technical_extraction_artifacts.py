"""Authority-neutral retention for validated technical page evidence.

Production must give the CLASSIFIRE application exclusive write authority over
its storage root and prove that layout through readiness checks. Windows Python
does not expose descriptor-relative hard-link creation. This boundary therefore
post-verifies every promoted canonical path and fails with cleanup-refused if a
parent swap redirects creation; it never claims or deletes escaped bytes. A
threat model that includes another local writer able to swap parent directories
also requires stronger native directory-handle primitives.
"""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import BinaryIO, Literal, cast

from ..models import TechnicalDerivedArtifact
from .storage import (
    StoredFileBindingError,
    _absolute_lexical,
    _close_descriptor,
    _is_link_or_reparse,
    _open_verified_retained_descriptor,
    _require_safe_retained_path,
    _require_safe_storage_root,
    _stat_signature,
)
from .technical_page_evidence import (
    TECHNICAL_PAGE_EVIDENCE_MAX_BYTES,
    TECHNICAL_PAGE_EVIDENCE_MAX_PAGE_IMAGE_BYTES,
    TECHNICAL_PAGE_EVIDENCE_VALIDATOR_POLICY,
    TechnicalPageEvidence,
    parse_technical_page_evidence,
)

TECHNICAL_DERIVED_ARTIFACT_SUBTREE = "technical-derived-artifacts-v1"
_INCOMING_DIRECTORY = ".incoming"
_HEX_SHA256 = frozenset("0123456789abcdef")
_DATABASE_OUTCOMES = frozenset({"known_rollback", "commit_outcome_unknown"})


@dataclass(frozen=True, slots=True)
class _ArtifactSpec:
    kind: str
    media_type: str
    suffix: str
    maximum_size_bytes: int


_ARTIFACT_SPECS = {
    "page_evidence_json": _ArtifactSpec(
        kind="page_evidence_json",
        media_type="application/json",
        suffix=".json",
        maximum_size_bytes=TECHNICAL_PAGE_EVIDENCE_MAX_BYTES,
    ),
    "page_image_png": _ArtifactSpec(
        kind="page_image_png",
        media_type="image/png",
        suffix=".png",
        maximum_size_bytes=TECHNICAL_PAGE_EVIDENCE_MAX_PAGE_IMAGE_BYTES,
    ),
}


class TechnicalExtractionArtifactError(RuntimeError):
    """A stable, path-free failure at the derived-artifact storage boundary."""

    _CODES = frozenset(
        {
            "TECHNICAL_ARTIFACT_BYTES_CHANGED",
            "TECHNICAL_ARTIFACT_CLEANUP_FAILED",
            "TECHNICAL_ARTIFACT_CLEANUP_REFUSED",
            "TECHNICAL_ARTIFACT_CONTENT_MISMATCH",
            "TECHNICAL_ARTIFACT_IDENTIFIER_INVALID",
            "TECHNICAL_ARTIFACT_PATH_COLLISION",
            "TECHNICAL_ARTIFACT_PATH_INVALID",
            "TECHNICAL_ARTIFACT_PATH_NOT_CANONICAL",
            "TECHNICAL_ARTIFACT_PATH_OUTSIDE_ROOT",
            "TECHNICAL_ARTIFACT_PATH_UNSAFE",
            "TECHNICAL_ARTIFACT_READ_FAILED",
            "TECHNICAL_ARTIFACT_RECORD_INVALID",
            "TECHNICAL_ARTIFACT_STORAGE_FAILURE",
            "TECHNICAL_ARTIFACT_STORAGE_ROOT_INVALID",
            "TECHNICAL_ARTIFACT_STORAGE_ROOT_UNSAFE",
            "TECHNICAL_ARTIFACT_TRANSACTION_OUTCOME_INVALID",
        }
    )

    def __init__(self, code: str, *, prior_code: str | None = None) -> None:
        if code not in self._CODES:
            raise ValueError("Unknown technical extraction artifact error code")
        self.code = code
        self.prior_code = prior_code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class TechnicalDerivedArtifactBinding:
    """The immutable identity and canonical location of one retained artifact."""

    artifact_id: str
    run_id: str
    page_number: int
    artifact_kind: str
    media_type: str
    sha256: str
    size_bytes: int
    storage_path: str
    validation_policy: str = TECHNICAL_PAGE_EVIDENCE_VALIDATOR_POLICY
    immutable: bool = True
    promoted_file: bool = True

    @property
    def path(self) -> Path:
        return Path(self.storage_path)


@dataclass(frozen=True, slots=True)
class RetainedTechnicalPageArtifacts:
    """Validated page evidence and its two exact retained byte bindings."""

    evidence: TechnicalPageEvidence
    packet: TechnicalDerivedArtifactBinding
    page_image: TechnicalDerivedArtifactBinding

    @property
    def bindings(self) -> tuple[TechnicalDerivedArtifactBinding, ...]:
        return (self.packet, self.page_image)


@dataclass(slots=True)
class VerifiedTechnicalDerivedArtifactStream:
    """One-shot stream over the same descriptor whose bytes were verified."""

    binding: TechnicalDerivedArtifactBinding
    _descriptor: int | None = field(repr=False)
    _claimed: bool = field(default=False, init=False, repr=False)

    @property
    def closed(self) -> bool:
        return self._descriptor is None

    def close(self) -> None:
        descriptor, self._descriptor = self._descriptor, None
        if descriptor is not None:
            _close_descriptor(descriptor)

    def __enter__(self) -> VerifiedTechnicalDerivedArtifactStream:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def __iter__(self) -> Iterator[bytes]:
        if self._claimed:
            raise RuntimeError("Verified technical artifact streams are one-shot")
        self._claimed = True
        descriptor = self._descriptor
        if descriptor is None:
            raise RuntimeError("Verified technical artifact stream is closed")
        try:
            while chunk := os.read(descriptor, 1024 * 1024):
                yield chunk
        except OSError:
            raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_READ_FAILED") from None
        finally:
            self.close()

    def claim_binary_reader(self) -> BinaryIO:
        if self._claimed:
            raise RuntimeError("Verified technical artifact streams are one-shot")
        self._claimed = True
        descriptor, self._descriptor = self._descriptor, None
        if descriptor is None:
            raise RuntimeError("Verified technical artifact stream is closed")
        try:
            return cast(BinaryIO, os.fdopen(descriptor, "rb", closefd=True))
        except (OSError, ValueError):
            _close_descriptor(descriptor)
            raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_READ_FAILED") from None


@dataclass(frozen=True, slots=True)
class _StagedArtifact:
    path: Path
    signature: tuple[int, int, int, int, int]
    sha256: str
    size_bytes: int


def _canonical_uuid4(value: object) -> str:
    if not isinstance(value, str):
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_IDENTIFIER_INVALID")
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, ValueError):
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_IDENTIFIER_INVALID") from None
    if parsed.version != 4 or str(parsed) != value:
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_IDENTIFIER_INVALID")
    return value


def _canonical_sha256(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HEX_SHA256 for character in value)
    ):
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_RECORD_INVALID")
    return value


def _page_number(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 500:
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_RECORD_INVALID")
    return value


def _storage_root(storage_root: Path) -> Path:
    _raw_root, root = _absolute_lexical(storage_root)
    try:
        _require_safe_storage_root(root)
    except StoredFileBindingError as exc:
        code = (
            "TECHNICAL_ARTIFACT_STORAGE_ROOT_UNSAFE"
            if exc.code == "STORAGE_ROOT_UNSAFE"
            else "TECHNICAL_ARTIFACT_STORAGE_ROOT_INVALID"
        )
        raise TechnicalExtractionArtifactError(code) from None
    return root


def _safe_directory(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or not relative.parts:
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_PATH_OUTSIDE_ROOT")
    current = root
    try:
        resolved_root = root.resolve(strict=True)
        for part in relative.parts:
            if part in {"", ".", ".."} or Path(part).name != part:
                raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_PATH_OUTSIDE_ROOT")
            current /= part
            try:
                metadata = os.lstat(current)
            except FileNotFoundError:
                try:
                    current.mkdir()
                except FileExistsError:
                    pass
                metadata = os.lstat(current)
            if _is_link_or_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
                raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_PATH_UNSAFE")
        current.resolve(strict=True).relative_to(resolved_root)
    except TechnicalExtractionArtifactError:
        raise
    except ValueError:
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_PATH_OUTSIDE_ROOT") from None
    except OSError:
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_STORAGE_FAILURE") from None
    return current


def _artifact_path(
    root: Path,
    *,
    run_id: str,
    page_number: int,
    artifact_id: str,
    spec: _ArtifactSpec,
    sha256: str,
) -> Path:
    path = (
        root
        / TECHNICAL_DERIVED_ARTIFACT_SUBTREE
        / run_id
        / f"page-{page_number:04d}"
        / spec.kind
        / artifact_id
        / f"{sha256}{spec.suffix}"
    )
    if len(str(path)) > 1000:
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_PATH_INVALID")
    return path


def _remove_failed_stage(path: Path, *, prior_code: str) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        raise TechnicalExtractionArtifactError(
            "TECHNICAL_ARTIFACT_CLEANUP_FAILED",
            prior_code=prior_code,
        ) from None


def _stage_exact_bytes(
    root: Path,
    incoming: Path,
    content: bytes,
    *,
    expected_sha256: str,
    expected_size_bytes: int,
    maximum_size_bytes: int,
) -> _StagedArtifact:
    if (
        not isinstance(content, bytes)
        or not 1 <= len(content) <= maximum_size_bytes
        or len(content) != expected_size_bytes
        or hashlib.sha256(content).hexdigest() != expected_sha256
    ):
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_CONTENT_MISMATCH")
    descriptor: int | None = None
    path: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix="technical-artifact-",
            suffix=".part",
            dir=incoming,
        )
        path = Path(name)
        view = memoryview(content)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise OSError("short artifact write")
            written += count
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or _is_link_or_reparse(metadata)
            or metadata.st_size != expected_size_bytes
        ):
            raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_BYTES_CHANGED")
        signature = _stat_signature(metadata)
    except (TechnicalExtractionArtifactError, OSError) as exc:
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                raise TechnicalExtractionArtifactError(
                    "TECHNICAL_ARTIFACT_CLEANUP_FAILED",
                    prior_code=getattr(exc, "code", None),
                ) from None
        if isinstance(exc, TechnicalExtractionArtifactError):
            raise
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_STORAGE_FAILURE") from None
    finally:
        if descriptor is not None:
            _close_descriptor(descriptor)
    if path is None:
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_STORAGE_FAILURE")
    try:
        initial = _require_safe_retained_path(root, path)
        opened, digest, size = _open_verified_retained_descriptor(root, path, initial)
        _close_descriptor(opened)
    except StoredFileBindingError:
        _remove_failed_stage(
            path,
            prior_code="TECHNICAL_ARTIFACT_BYTES_CHANGED",
        )
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_BYTES_CHANGED") from None
    if (
        _stat_signature(initial) != signature
        or digest != expected_sha256
        or size != expected_size_bytes
    ):
        _remove_failed_stage(
            path,
            prior_code="TECHNICAL_ARTIFACT_BYTES_CHANGED",
        )
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_BYTES_CHANGED")
    return _StagedArtifact(path, signature, digest, size)


def _verify_staged(root: Path, staged: _StagedArtifact) -> None:
    try:
        initial = _require_safe_retained_path(root, staged.path)
        if _stat_signature(initial) != staged.signature:
            raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_BYTES_CHANGED")
        descriptor, digest, size = _open_verified_retained_descriptor(root, staged.path, initial)
        _close_descriptor(descriptor)
    except TechnicalExtractionArtifactError:
        raise
    except StoredFileBindingError:
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_BYTES_CHANGED") from None
    if digest != staged.sha256 or size != staged.size_bytes:
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_BYTES_CHANGED")


def _binding_from_record(
    artifact: TechnicalDerivedArtifact | TechnicalDerivedArtifactBinding,
) -> TechnicalDerivedArtifactBinding:
    if isinstance(artifact, TechnicalDerivedArtifactBinding):
        binding = artifact
    else:
        binding = TechnicalDerivedArtifactBinding(
            artifact_id=artifact.id,
            run_id=artifact.run_id,
            page_number=artifact.page_number,
            artifact_kind=artifact.artifact_kind,
            media_type=artifact.media_type,
            sha256=artifact.sha256,
            size_bytes=artifact.size_bytes,
            storage_path=artifact.storage_path,
            validation_policy=artifact.validation_policy,
            immutable=artifact.immutable,
            promoted_file=False,
        )
    artifact_id = _canonical_uuid4(binding.artifact_id)
    run_id = _canonical_uuid4(binding.run_id)
    page_number = _page_number(binding.page_number)
    spec = _ARTIFACT_SPECS.get(binding.artifact_kind)
    if (
        spec is None
        or binding.media_type != spec.media_type
        or not isinstance(binding.size_bytes, int)
        or isinstance(binding.size_bytes, bool)
        or not 1 <= binding.size_bytes <= spec.maximum_size_bytes
        or binding.validation_policy != TECHNICAL_PAGE_EVIDENCE_VALIDATOR_POLICY
        or binding.immutable is not True
        or not isinstance(binding.storage_path, str)
        or not binding.storage_path
    ):
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_RECORD_INVALID")
    sha256 = _canonical_sha256(binding.sha256)
    return TechnicalDerivedArtifactBinding(
        artifact_id=artifact_id,
        run_id=run_id,
        page_number=page_number,
        artifact_kind=spec.kind,
        media_type=spec.media_type,
        sha256=sha256,
        size_bytes=binding.size_bytes,
        storage_path=binding.storage_path,
        validation_policy=TECHNICAL_PAGE_EVIDENCE_VALIDATOR_POLICY,
        immutable=True,
        promoted_file=binding.promoted_file,
    )


def _verified_descriptor(
    artifact: TechnicalDerivedArtifact | TechnicalDerivedArtifactBinding,
    *,
    storage_root: Path,
) -> tuple[TechnicalDerivedArtifactBinding, int]:
    binding = _binding_from_record(artifact)
    root = _storage_root(storage_root)
    spec = _ARTIFACT_SPECS[binding.artifact_kind]
    expected_path = _artifact_path(
        root,
        run_id=binding.run_id,
        page_number=binding.page_number,
        artifact_id=binding.artifact_id,
        spec=spec,
        sha256=binding.sha256,
    )
    raw_path, path = _absolute_lexical(Path(binding.storage_path))
    if raw_path != path:
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_PATH_NOT_CANONICAL")
    try:
        path.relative_to(root)
    except ValueError:
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_PATH_OUTSIDE_ROOT") from None
    if path != expected_path:
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_PATH_NOT_CANONICAL")
    try:
        initial = _require_safe_retained_path(root, path)
        resolved_root = root.resolve(strict=True)
        resolved_path = path.resolve(strict=True)
        resolved_path.relative_to(resolved_root)
        descriptor, digest, size = _open_verified_retained_descriptor(root, path, initial)
    except StoredFileBindingError as exc:
        if exc.code == "STORED_FILE_PATH_UNSAFE":
            code = "TECHNICAL_ARTIFACT_PATH_UNSAFE"
        elif exc.code in {"STORED_FILE_PATH_INVALID", "STORED_FILE_NOT_REGULAR"}:
            code = "TECHNICAL_ARTIFACT_PATH_INVALID"
        elif exc.code == "STORED_FILE_READ_FAILED":
            code = "TECHNICAL_ARTIFACT_READ_FAILED"
        else:
            code = "TECHNICAL_ARTIFACT_BYTES_CHANGED"
        raise TechnicalExtractionArtifactError(code) from None
    except ValueError:
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_PATH_OUTSIDE_ROOT") from None
    except OSError:
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_READ_FAILED") from None
    if digest != binding.sha256 or size != binding.size_bytes:
        _close_descriptor(descriptor)
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_CONTENT_MISMATCH")
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        if _stat_signature(os.fstat(descriptor)) != _stat_signature(initial):
            raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_BYTES_CHANGED")
    except TechnicalExtractionArtifactError:
        _close_descriptor(descriptor)
        raise
    except OSError:
        _close_descriptor(descriptor)
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_READ_FAILED") from None
    return binding, descriptor


def open_verified_technical_derived_artifact(
    artifact: TechnicalDerivedArtifact | TechnicalDerivedArtifactBinding,
    *,
    storage_root: Path,
) -> VerifiedTechnicalDerivedArtifactStream:
    """Return a one-shot descriptor for exact, canonical retained artifact bytes."""

    binding, descriptor = _verified_descriptor(
        artifact,
        storage_root=storage_root,
    )
    return VerifiedTechnicalDerivedArtifactStream(
        binding=binding,
        _descriptor=descriptor,
    )


def _remove_exact_bindings(
    bindings: tuple[TechnicalDerivedArtifactBinding, ...],
    *,
    storage_root: Path,
) -> None:
    root = _storage_root(storage_root)
    verified: list[VerifiedTechnicalDerivedArtifactStream] = []
    try:
        for binding in bindings:
            try:
                verified.append(
                    open_verified_technical_derived_artifact(
                        binding,
                        storage_root=root,
                    )
                )
            except TechnicalExtractionArtifactError as exc:
                raise TechnicalExtractionArtifactError(
                    "TECHNICAL_ARTIFACT_CLEANUP_REFUSED",
                    prior_code=exc.code,
                ) from None

        # Keep every verified descriptor open through deletion. This makes the
        # final lstat/fstat identity check reject a path swapped after hashing.
        for stream in verified:
            descriptor = stream._descriptor
            if descriptor is None:
                raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_CLEANUP_REFUSED")
            try:
                current = _require_safe_retained_path(root, stream.binding.path)
                opened = os.fstat(descriptor)
            except (OSError, StoredFileBindingError):
                raise TechnicalExtractionArtifactError(
                    "TECHNICAL_ARTIFACT_CLEANUP_REFUSED"
                ) from None
            if not os.path.samestat(current, opened):
                raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_CLEANUP_REFUSED")

        for stream in reversed(verified):
            descriptor = stream._descriptor
            if descriptor is None:
                raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_CLEANUP_REFUSED")
            try:
                current = _require_safe_retained_path(root, stream.binding.path)
                opened = os.fstat(descriptor)
                if not os.path.samestat(current, opened):
                    raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_CLEANUP_REFUSED")
                if os.name == "nt":
                    # Windows does not grant delete sharing to os.open. Close
                    # only this descriptor, then repeat the exact signature
                    # check immediately before unlinking the canonical path.
                    stream.close()
                    current = _require_safe_retained_path(root, stream.binding.path)
                    if not os.path.samestat(current, opened) or _stat_signature(
                        current
                    ) != _stat_signature(opened):
                        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_CLEANUP_REFUSED")
                stream.binding.path.unlink()
            except TechnicalExtractionArtifactError:
                raise
            except StoredFileBindingError:
                raise TechnicalExtractionArtifactError(
                    "TECHNICAL_ARTIFACT_CLEANUP_REFUSED"
                ) from None
            except OSError:
                raise TechnicalExtractionArtifactError(
                    "TECHNICAL_ARTIFACT_CLEANUP_FAILED"
                ) from None
    finally:
        for stream in verified:
            stream.close()


def _remove_staged(paths: list[Path]) -> None:
    cleanup_failed = False
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            cleanup_failed = True
    if cleanup_failed:
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_CLEANUP_FAILED")


def _replay_target_exists_exactly(root: Path, path: Path) -> bool:
    """Return whether one safe canonical target is the directory's only entry."""

    try:
        relative_parent = path.parent.relative_to(root)
    except ValueError:
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_PATH_OUTSIDE_ROOT") from None
    parent = _safe_directory(root, relative_parent)
    try:
        initial_parent = os.lstat(parent)
        entries = tuple(parent.iterdir())
    except OSError:
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_PATH_UNSAFE") from None
    if _is_link_or_reparse(initial_parent) or not stat.S_ISDIR(initial_parent.st_mode):
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_PATH_UNSAFE")

    target_exists = False
    for entry in entries:
        try:
            metadata = os.lstat(entry)
        except OSError:
            raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_PATH_UNSAFE") from None
        if _is_link_or_reparse(metadata) or not stat.S_ISREG(metadata.st_mode):
            raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_PATH_UNSAFE")
        if entry.name != path.name:
            raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_PATH_COLLISION")
        target_exists = True

    try:
        final_parent = os.lstat(parent)
    except OSError:
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_PATH_UNSAFE") from None
    if (
        _is_link_or_reparse(final_parent)
        or not stat.S_ISDIR(final_parent.st_mode)
        or not os.path.samestat(initial_parent, final_parent)
        or _stat_signature(initial_parent) != _stat_signature(final_parent)
    ):
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_PATH_UNSAFE")
    return target_exists


def _verify_exact_replay_binding(
    binding: TechnicalDerivedArtifactBinding,
    *,
    storage_root: Path,
) -> None:
    """Verify exact bytes and the artifact-ID directory while holding the file."""

    if not _replay_target_exists_exactly(storage_root, binding.path):
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_PATH_COLLISION")
    with open_verified_technical_derived_artifact(
        binding,
        storage_root=storage_root,
    ) as verified:
        if not _replay_target_exists_exactly(storage_root, binding.path):
            raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_PATH_COLLISION")
        descriptor = verified._descriptor
        if descriptor is None:
            raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_BYTES_CHANGED")
        try:
            current = _require_safe_retained_path(storage_root, binding.path)
            opened = os.fstat(descriptor)
        except (OSError, StoredFileBindingError):
            raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_BYTES_CHANGED") from None
        if not os.path.samestat(current, opened):
            raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_BYTES_CHANGED")


def retain_validated_technical_page_artifacts(
    raw_packet: bytes,
    *,
    page_image_bytes: bytes,
    storage_root: Path,
    run_id: str,
    expected_technical_document_id: str,
    expected_source_sha256: str,
    expected_source_size_bytes: int,
    expected_page_number: int,
    expected_page_count: int,
    expected_page_width_points: Decimal,
    expected_page_height_points: Decimal,
    expected_page_image_sha256: str,
    expected_page_image_size_bytes: int,
    expected_page_image_width_pixels: int,
    expected_page_image_height_pixels: int,
    expected_extraction_policy: str,
    expected_extraction_policy_bytes: bytes,
    expected_extraction_policy_sha256: str,
    expected_worker_image_digest: str,
    expected_ocr_low_confidence_threshold: Decimal,
    packet_artifact_id: str | None = None,
    page_image_artifact_id: str | None = None,
    allow_existing_artifact_replay: bool = False,
) -> RetainedTechnicalPageArtifacts:
    """Validate first, then retain the exact packet and PNG without a DB write."""

    # This must remain the first operation: invalid worker output must not even
    # create the dedicated artifact subtree or an incoming staging file.
    evidence = parse_technical_page_evidence(
        raw_packet,
        page_image_bytes=page_image_bytes,
        expected_technical_document_id=expected_technical_document_id,
        expected_source_sha256=expected_source_sha256,
        expected_source_size_bytes=expected_source_size_bytes,
        expected_page_number=expected_page_number,
        expected_page_count=expected_page_count,
        expected_page_width_points=expected_page_width_points,
        expected_page_height_points=expected_page_height_points,
        expected_page_image_sha256=expected_page_image_sha256,
        expected_page_image_size_bytes=expected_page_image_size_bytes,
        expected_page_image_width_pixels=expected_page_image_width_pixels,
        expected_page_image_height_pixels=expected_page_image_height_pixels,
        expected_extraction_policy=expected_extraction_policy,
        expected_extraction_policy_bytes=expected_extraction_policy_bytes,
        expected_extraction_policy_sha256=expected_extraction_policy_sha256,
        expected_worker_image_digest=expected_worker_image_digest,
        expected_ocr_low_confidence_threshold=expected_ocr_low_confidence_threshold,
    )

    if not isinstance(allow_existing_artifact_replay, bool):
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_RECORD_INVALID")
    if allow_existing_artifact_replay and (
        packet_artifact_id is None or page_image_artifact_id is None
    ):
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_IDENTIFIER_INVALID")

    canonical_run_id = _canonical_uuid4(run_id)
    packet_id = _canonical_uuid4(packet_artifact_id or str(uuid.uuid4()))
    image_id = _canonical_uuid4(page_image_artifact_id or str(uuid.uuid4()))
    if packet_id == image_id:
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_IDENTIFIER_INVALID")
    root = _storage_root(storage_root)
    packet_spec = _ARTIFACT_SPECS["page_evidence_json"]
    image_spec = _ARTIFACT_SPECS["page_image_png"]
    packet_path = _artifact_path(
        root,
        run_id=canonical_run_id,
        page_number=evidence.page_number,
        artifact_id=packet_id,
        spec=packet_spec,
        sha256=evidence.packet_sha256,
    )
    image_path = _artifact_path(
        root,
        run_id=canonical_run_id,
        page_number=evidence.page_number,
        artifact_id=image_id,
        spec=image_spec,
        sha256=evidence.image.sha256,
    )
    incoming = _safe_directory(
        root,
        Path(TECHNICAL_DERIVED_ARTIFACT_SUBTREE) / _INCOMING_DIRECTORY,
    )
    staged_paths: list[Path] = []
    promoted: list[TechnicalDerivedArtifactBinding] = []
    primary_error: BaseException | None = None
    try:
        staged_packet = _stage_exact_bytes(
            root,
            incoming,
            raw_packet,
            expected_sha256=evidence.packet_sha256,
            expected_size_bytes=evidence.packet_size_bytes,
            maximum_size_bytes=packet_spec.maximum_size_bytes,
        )
        staged_paths.append(staged_packet.path)
        staged_image = _stage_exact_bytes(
            root,
            incoming,
            page_image_bytes,
            expected_sha256=evidence.image.sha256,
            expected_size_bytes=evidence.image.size_bytes,
            maximum_size_bytes=image_spec.maximum_size_bytes,
        )
        staged_paths.append(staged_image.path)

        for staged, path, artifact_id, spec in (
            (staged_packet, packet_path, packet_id, packet_spec),
            (staged_image, image_path, image_id, image_spec),
        ):
            _verify_staged(root, staged)
            relative_parent = path.parent.relative_to(root)
            _safe_directory(root, relative_parent)
            target_exists = (
                _replay_target_exists_exactly(root, path)
                if allow_existing_artifact_replay
                else False
            )
            promoted_file = not target_exists
            if promoted_file:
                try:
                    os.link(staged.path, path, follow_symlinks=False)
                except FileExistsError:
                    if not allow_existing_artifact_replay:
                        raise TechnicalExtractionArtifactError(
                            "TECHNICAL_ARTIFACT_PATH_COLLISION"
                        ) from None
                    promoted_file = False
                except OSError:
                    raise TechnicalExtractionArtifactError(
                        "TECHNICAL_ARTIFACT_STORAGE_FAILURE"
                    ) from None
            binding = TechnicalDerivedArtifactBinding(
                artifact_id=artifact_id,
                run_id=canonical_run_id,
                page_number=evidence.page_number,
                artifact_kind=spec.kind,
                media_type=spec.media_type,
                sha256=staged.sha256,
                size_bytes=staged.size_bytes,
                storage_path=str(path),
                promoted_file=promoted_file,
            )
            promoted.append(binding)
            if allow_existing_artifact_replay:
                _verify_exact_replay_binding(binding, storage_root=root)
            else:
                with open_verified_technical_derived_artifact(
                    binding,
                    storage_root=root,
                ):
                    pass
            try:
                staged.path.unlink()
            except OSError:
                raise TechnicalExtractionArtifactError(
                    "TECHNICAL_ARTIFACT_CLEANUP_FAILED"
                ) from None
            staged_paths.remove(staged.path)

        return RetainedTechnicalPageArtifacts(
            evidence=evidence,
            packet=promoted[0],
            page_image=promoted[1],
        )
    except Exception as exc:
        primary_error = exc
        newly_promoted = tuple(binding for binding in promoted if binding.promoted_file)
        if newly_promoted:
            try:
                _remove_exact_bindings(newly_promoted, storage_root=root)
                promoted.clear()
            except TechnicalExtractionArtifactError as cleanup_exc:
                raise TechnicalExtractionArtifactError(
                    cleanup_exc.code,
                    prior_code=getattr(exc, "code", None),
                ) from None
        raise
    finally:
        try:
            _remove_staged(staged_paths)
        except TechnicalExtractionArtifactError as cleanup_exc:
            if primary_error is not None:
                raise TechnicalExtractionArtifactError(
                    cleanup_exc.code,
                    prior_code=getattr(primary_error, "code", None),
                ) from None
            raise


def build_unflushed_technical_derived_artifact_rows(
    retained: RetainedTechnicalPageArtifacts,
) -> tuple[TechnicalDerivedArtifact, TechnicalDerivedArtifact]:
    """Build transient ORM rows; the caller retains all flush/commit authority."""

    rows: list[TechnicalDerivedArtifact] = []
    for raw_binding in retained.bindings:
        binding = _binding_from_record(raw_binding)
        rows.append(
            TechnicalDerivedArtifact(
                id=binding.artifact_id,
                artifact_schema="technical-derived-artifact-v1",
                run_id=binding.run_id,
                page_number=binding.page_number,
                artifact_kind=binding.artifact_kind,
                media_type=binding.media_type,
                sha256=binding.sha256,
                size_bytes=binding.size_bytes,
                storage_path=binding.storage_path,
                validation_policy=binding.validation_policy,
                immutable=True,
            )
        )
    return rows[0], rows[1]


def cleanup_retained_technical_page_artifacts(
    retained: RetainedTechnicalPageArtifacts,
    *,
    storage_root: Path,
    database_outcome: Literal["known_rollback", "commit_outcome_unknown"],
) -> tuple[str, ...]:
    """Compensate only a known rollback; unknown commit outcomes retain bytes."""

    if database_outcome not in _DATABASE_OUTCOMES:
        raise TechnicalExtractionArtifactError("TECHNICAL_ARTIFACT_TRANSACTION_OUTCOME_INVALID")
    if database_outcome == "commit_outcome_unknown":
        return ()
    bindings = tuple(binding for binding in retained.bindings if binding.promoted_file)
    _remove_exact_bindings(bindings, storage_root=storage_root)
    return tuple(binding.artifact_id for binding in bindings)


__all__ = [
    "TECHNICAL_DERIVED_ARTIFACT_SUBTREE",
    "RetainedTechnicalPageArtifacts",
    "TechnicalDerivedArtifactBinding",
    "TechnicalExtractionArtifactError",
    "VerifiedTechnicalDerivedArtifactStream",
    "build_unflushed_technical_derived_artifact_rows",
    "cleanup_retained_technical_page_artifacts",
    "open_verified_technical_derived_artifact",
    "retain_validated_technical_page_artifacts",
]
