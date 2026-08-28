from __future__ import annotations

import hashlib
import mimetypes
import os
import stat
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, cast

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import StoredFile, User
from .malware_scanning import (
    MalwareScanError,
    MalwareScanner,
    configured_malware_scanner,
    require_exact_clean_verdict,
)

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".xlsx",
    ".xlsb",
    ".xlsm",
    ".csv",
    ".json",
    ".jsonl",
    ".txt",
    ".md",
    ".png",
    ".jpg",
    ".jpeg",
    ".docx",
}

_HEX_SHA256 = frozenset("0123456789abcdef")
_REPARSE_POINT_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
_CLEANUP_FAILURE_CODES = frozenset(
    {
        "UPLOAD_RETENTION_CLEANUP_FAILED",
        "UPLOAD_TEMP_CLEANUP_FAILED",
    }
)
_STORAGE_ROOT_BINDING_CODES = frozenset(
    {
        "STORAGE_ROOT_INVALID",
        "STORAGE_ROOT_UNSAFE",
    }
)
_STORAGE_READINESS_CODES = frozenset(
    {
        "STORAGE_PROBE_CLEANUP_FAILED",
        "STORAGE_PROBE_FAILED",
        "STORAGE_ROOT_INVALID",
        "STORAGE_ROOT_NOT_WRITABLE",
        "STORAGE_ROOT_UNSAFE",
    }
)
_STORED_CONTEXT_BINDING_CODES = frozenset(
    {
        "STORED_FILE_NOT_IMMUTABLE",
        "STORED_FILE_PURPOSE_MISMATCH",
        "STORED_FILE_SCAN_NOT_CLEAN",
        "STORED_FILE_SHA256_INVALID",
        "STORED_FILE_SIZE_INVALID",
        "STORED_FILE_SUFFIX_NOT_ALLOWED",
    }
)


class StoredFileBindingError(RuntimeError):
    """A stable, path-free failure to bind a retained file record to its bytes."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Stored file binding failed: {code}.")


class StorageReadinessError(RuntimeError):
    """A stable, path-free storage readiness failure."""

    def __init__(self, code: str) -> None:
        if code not in _STORAGE_READINESS_CODES:
            raise ValueError("Unknown storage readiness error code")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class StoredFileBinding:
    """The verified immutable relationship between a StoredFile row and retained bytes."""

    path: Path
    sha256: str
    size_bytes: int
    suffix: str
    purpose: str


@dataclass(frozen=True, slots=True)
class _StoredFileContext:
    root: Path
    path: Path
    initial: os.stat_result
    sha256: str
    size_bytes: int
    suffix: str
    purpose: str

    def binding(self) -> StoredFileBinding:
        return StoredFileBinding(
            path=self.path,
            sha256=self.sha256,
            size_bytes=self.size_bytes,
            suffix=self.suffix,
            purpose=self.purpose,
        )


@dataclass(slots=True)
class VerifiedStoredFileStream:
    """One-shot stream over the same descriptor whose exact bytes were verified."""

    binding: StoredFileBinding
    _descriptor: int | None = field(repr=False)
    _claimed: bool = field(default=False, init=False, repr=False)

    @property
    def closed(self) -> bool:
        return self._descriptor is None

    def close(self) -> None:
        descriptor, self._descriptor = self._descriptor, None
        if descriptor is not None:
            _close_descriptor(descriptor)

    def __enter__(self) -> VerifiedStoredFileStream:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def __iter__(self) -> Iterator[bytes]:
        if self._claimed:
            raise RuntimeError("Verified stored-file streams are one-shot")
        self._claimed = True
        descriptor = self._descriptor
        if descriptor is None:
            raise RuntimeError("Verified stored-file stream is closed")
        try:
            while chunk := os.read(descriptor, 1024 * 1024):
                yield chunk
        except OSError:
            raise _binding_error("STORED_FILE_READ_FAILED") from None
        finally:
            self.close()

    def claim_binary_reader(self) -> BinaryIO:
        """Transfer the verified descriptor to one binary reader.

        This is intended for fixed subprocess boundaries that must consume the
        exact descriptor already checked by ``open_verified_stored_file``. The
        returned reader owns the descriptor and the caller must close it.
        """

        if self._claimed:
            raise RuntimeError("Verified stored-file streams are one-shot")
        self._claimed = True
        descriptor, self._descriptor = self._descriptor, None
        if descriptor is None:
            raise RuntimeError("Verified stored-file stream is closed")
        try:
            return cast(BinaryIO, os.fdopen(descriptor, "rb", closefd=True))
        except (OSError, ValueError):
            _close_descriptor(descriptor)
            raise _binding_error("STORED_FILE_READ_FAILED") from None


@dataclass(frozen=True, slots=True)
class StoredUpload:
    """A clean retained upload that remains part of the caller's transaction.

    This service never commits. If ``promoted_file`` is true, the caller owns
    compensation for a known pre-commit failure and must remove the promoted
    bytes before rolling back. A commit whose outcome is unknown must retain
    the bytes so a possibly committed row never points at a deleted file.
    """

    stored_file: StoredFile
    binding: StoredFileBinding
    created_record: bool
    promoted_file: bool


class StoredFileSecurityError(ValueError):
    """A stable, redacted retained-file boundary failure."""

    _CODES = frozenset(
        {
            "STORED_FILE_CONTENT_COLLISION",
            "STORED_FILE_CONTEXT_CONFLICT",
            "STORED_FILE_PERSISTENCE_CONFLICT",
            "STORED_FILE_STORAGE_FAILURE",
            "UPLOAD_CONTENT_SIGNATURE_INVALID",
            "UPLOAD_FILE_EMPTY",
            "UPLOAD_FILE_TYPE_UNSUPPORTED",
            "UPLOAD_EXPECTED_CONTENT_MISMATCH",
            "UPLOAD_SIZE_LIMIT_EXCEEDED",
            "UPLOAD_STAGED_BYTES_CHANGED",
            "UPLOAD_STREAM_INVALID",
            "UPLOAD_TEMP_CLEANUP_FAILED",
            "UPLOAD_RETENTION_CLEANUP_FAILED",
            "UPLOAD_MULTIPLE_CLEANUP_FAILED",
        }
    )

    def __init__(
        self,
        code: str,
        *,
        prior_code: str | None = None,
        cleanup_codes: tuple[str, ...] = (),
        content_sha256: str | None = None,
        content_size_bytes: int | None = None,
    ) -> None:
        if code not in self._CODES:
            raise ValueError("Unknown stored-file security error code")
        self.code = code
        self.prior_code = prior_code
        self.cleanup_codes = cleanup_codes
        self.content_sha256 = content_sha256
        self.content_size_bytes = content_size_bytes
        super().__init__(code)


def cleanup_uncommitted_upload(
    upload: StoredUpload | None,
    *,
    prior_code: str,
) -> StoredFileSecurityError | None:
    """Compensate a known pre-commit failure while its SHA row is still locked.

    The caller must invoke this before rolling back the database transaction.
    Returning an error instead of suppressing it lets the intake audit expose a
    stable, path-free cleanup outcome.
    """

    if upload is None or not upload.promoted_file:
        return None
    try:
        upload.binding.path.unlink(missing_ok=True)
    except OSError:
        return StoredFileSecurityError(
            "UPLOAD_RETENTION_CLEANUP_FAILED",
            prior_code=prior_code,
            cleanup_codes=("UPLOAD_RETENTION_CLEANUP_FAILED",),
        )
    return None


def _prior_outcome_code(exc: BaseException) -> str | None:
    prior_code = getattr(exc, "prior_code", None)
    if isinstance(prior_code, str):
        return prior_code
    code = getattr(exc, "code", None)
    if not isinstance(code, str) or code in _CLEANUP_FAILURE_CODES:
        return None
    if code == "UPLOAD_MULTIPLE_CLEANUP_FAILED":
        return None
    return code


def _binding_error(code: str) -> StoredFileBindingError:
    return StoredFileBindingError(code)


def _absolute_lexical(path: Path) -> tuple[Path, Path]:
    raw = path if path.is_absolute() else Path.cwd() / path
    return raw, Path(os.path.abspath(raw))


def _path_lineage(path: Path) -> tuple[Path, ...]:
    current = Path(path.anchor)
    lineage: list[Path] = []
    for part in path.parts[1:]:
        current /= part
        lineage.append(current)
    return tuple(lineage)


def _is_link_or_reparse(metadata: os.stat_result) -> bool:
    attributes = int(getattr(metadata, "st_file_attributes", 0))
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & _REPARSE_POINT_ATTRIBUTE)


def _safe_lstat(path: Path, *, missing_code: str, unsafe_code: str) -> os.stat_result:
    try:
        metadata = os.lstat(path)
    except OSError:
        raise _binding_error(missing_code) from None
    if _is_link_or_reparse(metadata):
        raise _binding_error(unsafe_code)
    return metadata


def _require_safe_storage_root(root: Path) -> None:
    if root == Path(root.anchor):
        raise _binding_error("STORAGE_ROOT_UNSAFE")
    try:
        root_metadata = os.lstat(root)
    except OSError:
        raise _binding_error("STORAGE_ROOT_INVALID") from None
    for component in _path_lineage(root):
        _safe_lstat(
            component,
            missing_code="STORAGE_ROOT_INVALID",
            unsafe_code="STORAGE_ROOT_UNSAFE",
        )
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise _binding_error("STORAGE_ROOT_INVALID")


def _prepare_readiness_directory(
    root: Path,
    path: Path,
    created_directories: list[Path],
) -> Path:
    """Create one probe directory and reject unsafe existing components."""

    try:
        relative = path.relative_to(root)
    except ValueError:
        raise StorageReadinessError("STORAGE_ROOT_UNSAFE") from None
    if not relative.parts:
        raise StorageReadinessError("STORAGE_ROOT_UNSAFE")

    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        try:
            path.mkdir()
        except FileExistsError:
            pass
        except PermissionError:
            raise StorageReadinessError("STORAGE_ROOT_NOT_WRITABLE") from None
        except OSError:
            raise StorageReadinessError("STORAGE_PROBE_FAILED") from None
        else:
            created_directories.append(path)
        try:
            metadata = os.lstat(path)
        except PermissionError:
            raise StorageReadinessError("STORAGE_ROOT_NOT_WRITABLE") from None
        except OSError:
            raise StorageReadinessError("STORAGE_PROBE_FAILED") from None
    except PermissionError:
        raise StorageReadinessError("STORAGE_ROOT_NOT_WRITABLE") from None
    except OSError:
        raise StorageReadinessError("STORAGE_PROBE_FAILED") from None

    if _is_link_or_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
        raise StorageReadinessError("STORAGE_ROOT_UNSAFE")

    current = root
    for part in relative.parts:
        current /= part
        try:
            component = os.lstat(current)
        except PermissionError:
            raise StorageReadinessError("STORAGE_ROOT_NOT_WRITABLE") from None
        except OSError:
            raise StorageReadinessError("STORAGE_PROBE_FAILED") from None
        if _is_link_or_reparse(component) or not stat.S_ISDIR(component.st_mode):
            raise StorageReadinessError("STORAGE_ROOT_UNSAFE")
    return path


def _cleanup_readiness_file(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        path.unlink(missing_ok=True)
    except OSError:
        # A second primitive is best-effort residue containment. The original
        # failure still blocks readiness because ordinary cleanup was not sound.
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        except OSError:
            pass
        return True
    return False


def _cleanup_readiness_directory(path: Path) -> bool:
    try:
        path.rmdir()
    except OSError:
        # As with files, contain residue where possible but retain the failure.
        try:
            os.rmdir(path)
        except FileNotFoundError:
            pass
        except OSError:
            pass
        return True
    return False


def require_storage_root_readiness(storage_root: Path) -> str:
    """Prove the configured root supports the exact upload retention layout."""

    raw_root, root = _absolute_lexical(storage_root)
    if raw_root != root:
        raise StorageReadinessError("STORAGE_ROOT_INVALID")
    try:
        _require_safe_storage_root(root)
    except StoredFileBindingError as exc:
        raise StorageReadinessError(exc.code) from None

    payload = b"CLASSIFIRE storage readiness probe\n"
    created_directories: list[Path] = []
    source_path: Path | None = None
    linked_path: Path | None = None
    descriptor: int | None = None
    failure: StorageReadinessError | None = None
    try:
        payload += os.urandom(16)
        expected_sha256 = hashlib.sha256(payload).hexdigest()
        spool = _prepare_readiness_directory(
            root,
            root / ".incoming",
            created_directories,
        )
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".classifire-readiness-",
            suffix=".part",
            dir=spool,
        )
        source_path = Path(temporary_name)
        os.write(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None

        first_prefix = _prepare_readiness_directory(
            root,
            root / expected_sha256[:2],
            created_directories,
        )
        final_dir = _prepare_readiness_directory(
            root,
            first_prefix / expected_sha256[2:4],
            created_directories,
        )
        candidate_link = final_dir / f"{expected_sha256}.link"
        os.link(source_path, candidate_link, follow_symlinks=False)
        linked_path = candidate_link

        _require_safe_storage_root(root)
        source_metadata = _require_safe_retained_path(root, source_path)
        linked_metadata = _require_safe_retained_path(root, linked_path)
        if not os.path.samestat(source_metadata, linked_metadata):
            raise StorageReadinessError("STORAGE_PROBE_FAILED")
        source_digest, source_size = _verify_retained_bytes(
            root,
            source_path,
            source_metadata,
        )
        linked_digest, linked_size = _verify_retained_bytes(
            root,
            linked_path,
            linked_metadata,
        )
        if (
            source_digest != expected_sha256
            or linked_digest != expected_sha256
            or source_size != len(payload)
            or linked_size != len(payload)
        ):
            raise StorageReadinessError("STORAGE_PROBE_FAILED")
    except StorageReadinessError as exc:
        failure = exc
    except StoredFileBindingError as exc:
        if exc.code in {"STORAGE_ROOT_INVALID", "STORAGE_ROOT_UNSAFE"}:
            code = exc.code
        elif exc.code in {"STORED_FILE_PATH_INVALID", "STORED_FILE_PATH_UNSAFE"}:
            code = "STORAGE_ROOT_UNSAFE"
        else:
            code = "STORAGE_PROBE_FAILED"
        failure = StorageReadinessError(code)
    except PermissionError:
        failure = StorageReadinessError("STORAGE_ROOT_NOT_WRITABLE")
    except OSError:
        failure = StorageReadinessError("STORAGE_PROBE_FAILED")
    finally:
        if descriptor is not None:
            _close_descriptor(descriptor)
        cleanup_failed = any(
            (
                _cleanup_readiness_file(linked_path),
                _cleanup_readiness_file(source_path),
                *(
                    _cleanup_readiness_directory(path)
                    for path in reversed(created_directories)
                ),
            )
        )
        if cleanup_failed:
            raise StorageReadinessError("STORAGE_PROBE_CLEANUP_FAILED") from None

    if failure is not None:
        raise failure
    return "STORAGE_READY"


def _require_safe_retained_path(root: Path, path: Path) -> os.stat_result:
    relative = path.relative_to(root)
    current = root
    for part in relative.parts[:-1]:
        current /= part
        metadata = _safe_lstat(
            current,
            missing_code="STORED_FILE_PATH_INVALID",
            unsafe_code="STORED_FILE_PATH_UNSAFE",
        )
        if not stat.S_ISDIR(metadata.st_mode):
            raise _binding_error("STORED_FILE_PATH_INVALID")
    metadata = _safe_lstat(
        path,
        missing_code="STORED_FILE_PATH_INVALID",
        unsafe_code="STORED_FILE_PATH_UNSAFE",
    )
    if not stat.S_ISREG(metadata.st_mode):
        raise _binding_error("STORED_FILE_NOT_REGULAR")
    return metadata


def _stat_signature(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
    )


def _sha256_descriptor(descriptor: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while chunk := os.read(descriptor, 1024 * 1024):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def _close_descriptor(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:
        # The descriptor is no longer safe to reuse after a failed close.
        pass


def _open_verified_retained_descriptor(
    root: Path,
    path: Path,
    initial: os.stat_result,
) -> tuple[int, str, int]:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise _binding_error("STORED_FILE_READ_FAILED") from None
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or _stat_signature(opened) != _stat_signature(initial):
            raise _binding_error("STORED_FILE_CHANGED_DURING_VALIDATION")
        digest, size = _sha256_descriptor(descriptor)
        finished = os.fstat(descriptor)
        try:
            _require_safe_storage_root(root)
            final = _require_safe_retained_path(root, path)
        except StoredFileBindingError:
            raise _binding_error("STORED_FILE_CHANGED_DURING_VALIDATION") from None
        signature = _stat_signature(initial)
        if _stat_signature(finished) != signature or _stat_signature(final) != signature:
            raise _binding_error("STORED_FILE_CHANGED_DURING_VALIDATION")
    except StoredFileBindingError:
        _close_descriptor(descriptor)
        raise
    except OSError:
        _close_descriptor(descriptor)
        raise _binding_error("STORED_FILE_READ_FAILED") from None
    return descriptor, digest, size


def _verify_retained_bytes(
    root: Path,
    path: Path,
    initial: os.stat_result,
) -> tuple[str, int]:
    descriptor, digest, size = _open_verified_retained_descriptor(root, path, initial)
    _close_descriptor(descriptor)
    return digest, size


def _stored_file_context(
    stored: StoredFile,
    *,
    storage_root: Path,
    required_purpose: str,
) -> _StoredFileContext:
    if stored.purpose != required_purpose:
        raise _binding_error("STORED_FILE_PURPOSE_MISMATCH")
    if stored.immutable is not True:
        raise _binding_error("STORED_FILE_NOT_IMMUTABLE")
    if stored.malware_scan_status != "clean":
        raise _binding_error("STORED_FILE_SCAN_NOT_CLEAN")
    sha256 = stored.sha256
    if (
        not isinstance(sha256, str)
        or len(sha256) != 64
        or any(character not in _HEX_SHA256 for character in sha256)
    ):
        raise _binding_error("STORED_FILE_SHA256_INVALID")
    size_bytes = stored.size_bytes
    if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
        raise _binding_error("STORED_FILE_SIZE_INVALID")
    suffix = Path(stored.original_filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise _binding_error("STORED_FILE_SUFFIX_NOT_ALLOWED")

    _raw_root, root = _absolute_lexical(storage_root)
    _require_safe_storage_root(root)
    raw_path, path = _absolute_lexical(Path(stored.storage_path))
    if raw_path != path:
        raise _binding_error("STORED_FILE_PATH_NOT_CANONICAL")
    try:
        path.relative_to(root)
    except ValueError:
        raise _binding_error("STORED_FILE_PATH_OUTSIDE_ROOT") from None
    expected_path = root / sha256[:2] / sha256[2:4] / f"{sha256}{suffix}"
    if path != expected_path:
        raise _binding_error("STORED_FILE_PATH_NOT_CANONICAL")

    initial = _require_safe_retained_path(root, path)
    try:
        resolved_root = root.resolve(strict=True)
        resolved_path = path.resolve(strict=True)
        resolved_path.relative_to(resolved_root)
    except (OSError, ValueError):
        raise _binding_error("STORED_FILE_PATH_OUTSIDE_ROOT") from None
    return _StoredFileContext(
        root=root,
        path=resolved_path,
        initial=initial,
        sha256=sha256,
        size_bytes=size_bytes,
        suffix=suffix,
        purpose=required_purpose,
    )


def _require_expected_content(
    context: _StoredFileContext,
    *,
    digest: str,
    size: int,
) -> None:
    if size != context.size_bytes:
        raise _binding_error("STORED_FILE_SIZE_MISMATCH")
    if digest != context.sha256:
        raise _binding_error("STORED_FILE_HASH_MISMATCH")


def require_stored_file_binding(
    stored: StoredFile,
    *,
    storage_root: Path,
    required_purpose: str,
) -> StoredFileBinding:
    """Fail closed unless a retained StoredFile exactly matches governed local bytes."""

    context = _stored_file_context(
        stored,
        storage_root=storage_root,
        required_purpose=required_purpose,
    )
    digest, actual_size = _verify_retained_bytes(
        context.root,
        context.path,
        context.initial,
    )
    _require_expected_content(context, digest=digest, size=actual_size)
    return context.binding()


def open_verified_stored_file(
    stored: StoredFile,
    *,
    storage_root: Path,
    required_purpose: str,
) -> VerifiedStoredFileStream:
    """Open and rewind the same retained-file descriptor whose bytes are verified.

    Callers must close the returned stream. Iterating it closes the descriptor in
    a finally block, and response callers should also register close as a
    completion callback so disconnects cannot retain the descriptor.
    """

    context = _stored_file_context(
        stored,
        storage_root=storage_root,
        required_purpose=required_purpose,
    )
    descriptor, digest, size = _open_verified_retained_descriptor(
        context.root,
        context.path,
        context.initial,
    )
    try:
        _require_expected_content(context, digest=digest, size=size)
        os.lseek(descriptor, 0, os.SEEK_SET)
        rewound = os.fstat(descriptor)
        if _stat_signature(rewound) != _stat_signature(context.initial):
            raise _binding_error("STORED_FILE_CHANGED_DURING_VALIDATION")
    except StoredFileBindingError:
        _close_descriptor(descriptor)
        raise
    except OSError:
        _close_descriptor(descriptor)
        raise _binding_error("STORED_FILE_READ_FAILED") from None
    return VerifiedStoredFileStream(binding=context.binding(), _descriptor=descriptor)


def sha256_stream(stream: BinaryIO) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(1024 * 1024):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def _normalised_media_type(value: object) -> str:
    return str(value or "").split(";", 1)[0].strip().lower()


def _resolved_storage_root(settings: Settings) -> Path:
    _raw_root, root = _absolute_lexical(settings.storage_root)
    try:
        _require_safe_storage_root(root)
    except StoredFileBindingError:
        raise StoredFileSecurityError("STORED_FILE_STORAGE_FAILURE") from None
    return root


def _controlled_directory(root: Path, path: Path) -> Path:
    try:
        path.relative_to(root)
        path.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError):
        raise StoredFileSecurityError("STORED_FILE_STORAGE_FAILURE") from None
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        try:
            metadata = os.lstat(current)
        except OSError:
            raise StoredFileSecurityError("STORED_FILE_STORAGE_FAILURE") from None
        if _is_link_or_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
            raise StoredFileSecurityError("STORED_FILE_STORAGE_FAILURE")
    return path


def _require_content_signature(header: bytes, suffix: str) -> None:
    if not header:
        raise StoredFileSecurityError("UPLOAD_FILE_EMPTY")
    valid = True
    if suffix == ".pdf":
        valid = header.startswith(b"%PDF-")
    elif suffix in {".docx", ".xlsx", ".xlsb", ".xlsm"}:
        valid = header.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"))
    elif suffix == ".png":
        valid = header.startswith(b"\x89PNG\r\n\x1a\n")
    elif suffix in {".jpg", ".jpeg"}:
        valid = header.startswith(b"\xff\xd8\xff")
    if not valid:
        raise StoredFileSecurityError("UPLOAD_CONTENT_SIGNATURE_INVALID")


def _locked_stored_file_by_sha(db: Session, sha256: str) -> StoredFile | None:
    return db.scalar(
        select(StoredFile)
        .where(StoredFile.sha256 == sha256)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _require_compatible_clean_upload(
    settings: Settings,
    stored: StoredFile,
    *,
    purpose: str,
    suffix: str,
    sha256: str,
    size_bytes: int,
) -> StoredFileBinding:
    try:
        binding = require_stored_file_binding(
            stored,
            storage_root=settings.storage_root,
            required_purpose=purpose,
        )
    except StoredFileBindingError as exc:
        if exc.code in _STORAGE_ROOT_BINDING_CODES:
            raise StoredFileSecurityError("STORED_FILE_STORAGE_FAILURE") from None
        if exc.code in _STORED_CONTEXT_BINDING_CODES:
            raise StoredFileSecurityError("STORED_FILE_CONTEXT_CONFLICT") from None
        raise StoredFileSecurityError("STORED_FILE_CONTENT_COLLISION") from None
    if (
        binding.sha256 != sha256
        or binding.size_bytes != size_bytes
        or binding.suffix != suffix
    ):
        raise StoredFileSecurityError("STORED_FILE_CONTEXT_CONFLICT")
    return binding


def save_verified_upload(
    db: Session,
    settings: Settings,
    upload: UploadFile,
    *,
    purpose: str,
    user: User | None,
    malware_scanner: MalwareScanner | None = None,
    expected_sha256: str | None = None,
    expected_size_bytes: int | None = None,
    manifest_admitted_size_bytes: int | None = None,
) -> StoredUpload:
    """Quarantine and scan exact bytes without committing the caller's transaction.

    The caller must roll back the Session after any exception. On a later known
    pre-commit failure, it must first call :func:`cleanup_uncommitted_upload`
    and then roll back. This preserves unrelated transaction ownership while
    avoiding SQLite SAVEPOINTs that can commit before the outer unit of work.
    """

    if manifest_admitted_size_bytes is not None and (
        manifest_admitted_size_bytes <= 0
        or expected_size_bytes != manifest_admitted_size_bytes
    ):
        raise StoredFileSecurityError("UPLOAD_EXPECTED_CONTENT_MISMATCH")
    upload_size_limit = (
        manifest_admitted_size_bytes
        if manifest_admitted_size_bytes is not None
        else settings.max_upload_bytes
    )
    filename = Path(upload.filename or "unnamed").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise StoredFileSecurityError("UPLOAD_FILE_TYPE_UNSUPPORTED")
    scanner = (
        malware_scanner if malware_scanner is not None else configured_malware_scanner(settings)
    )
    if scanner is None:
        raise MalwareScanError("MALWARE_SCANNER_REQUIRED")

    media_type = (
        _normalised_media_type(upload.content_type or mimetypes.guess_type(filename)[0]) or None
    )
    root = _resolved_storage_root(settings)
    spool = _controlled_directory(root, root / ".incoming")
    temp_path: Path | None = None
    final_path: Path | None = None
    promoted_new_file = False
    primary_error: BaseException | None = None
    cleanup_failures: list[str] = []
    process_control_interrupted = False
    try:
        size_bytes = 0
        digest = hashlib.sha256()
        staged_signature: tuple[int, int, int, int, int] | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w+b",
                prefix="upload-",
                suffix=".part",
                dir=spool,
                delete=False,
            ) as staged:
                temp_path = Path(staged.name)
                while True:
                    try:
                        chunk = upload.file.read(1024 * 1024)
                    except Exception:
                        raise StoredFileSecurityError("UPLOAD_STREAM_INVALID") from None
                    if not isinstance(chunk, bytes):
                        raise StoredFileSecurityError("UPLOAD_STREAM_INVALID")
                    if not chunk:
                        break
                    size_bytes += len(chunk)
                    if size_bytes > upload_size_limit:
                        raise StoredFileSecurityError("UPLOAD_SIZE_LIMIT_EXCEEDED")
                    digest.update(chunk)
                    staged.write(chunk)
                staged.flush()
                os.fsync(staged.fileno())
                staged_metadata = os.fstat(staged.fileno())
                if (
                    not stat.S_ISREG(staged_metadata.st_mode)
                    or _is_link_or_reparse(staged_metadata)
                ):
                    raise StoredFileSecurityError("UPLOAD_STAGED_BYTES_CHANGED")
                staged_signature = _stat_signature(staged_metadata)

                sha256 = digest.hexdigest()
                if expected_sha256 is not None or expected_size_bytes is not None:
                    if (
                        expected_sha256 is None
                        or expected_size_bytes is None
                        or sha256 != expected_sha256
                        or size_bytes != expected_size_bytes
                    ):
                        raise StoredFileSecurityError(
                            "UPLOAD_EXPECTED_CONTENT_MISMATCH"
                        )
                staged.seek(0)
                _require_content_signature(staged.read(1024), suffix)
                staged.seek(0)
                require_exact_clean_verdict(
                    scanner,
                    cast(BinaryIO, staged),
                    expected_sha256=sha256,
                    expected_size_bytes=size_bytes,
                )
                after_scan = os.fstat(staged.fileno())
                if _stat_signature(after_scan) != staged_signature:
                    raise StoredFileSecurityError("UPLOAD_STAGED_BYTES_CHANGED")
                staged.seek(0)
                staged_sha256, staged_size = sha256_stream(cast(BinaryIO, staged))
                if staged_sha256 != sha256 or staged_size != size_bytes:
                    raise StoredFileSecurityError("UPLOAD_STAGED_BYTES_CHANGED")
        except MalwareScanError as exc:
            raise MalwareScanError(
                exc.code,
                content_sha256=sha256,
                content_size_bytes=size_bytes,
            ) from None
        except (StoredFileSecurityError, ValueError):
            raise
        except OSError:
            raise StoredFileSecurityError("STORED_FILE_STORAGE_FAILURE") from None

        try:
            staged_path_metadata = _require_safe_retained_path(root, temp_path)
        except StoredFileBindingError:
            raise StoredFileSecurityError("UPLOAD_STAGED_BYTES_CHANGED") from None
        if staged_signature is None or _stat_signature(staged_path_metadata) != staged_signature:
            raise StoredFileSecurityError("UPLOAD_STAGED_BYTES_CHANGED")

        try:
            existing = _locked_stored_file_by_sha(db, sha256)
        except SQLAlchemyError:
            raise StoredFileSecurityError("STORED_FILE_PERSISTENCE_CONFLICT") from None
        if existing is not None:
            binding = _require_compatible_clean_upload(
                settings,
                existing,
                purpose=purpose,
                suffix=suffix,
                sha256=sha256,
                size_bytes=size_bytes,
            )
            return StoredUpload(existing, binding, created_record=False, promoted_file=False)

        final_dir = _controlled_directory(root, root / sha256[:2] / sha256[2:4])
        final_path = final_dir / f"{sha256}{suffix}"
        record = StoredFile(
            original_filename=filename,
            media_type=media_type,
            storage_path=str(final_path),
            sha256=sha256,
            size_bytes=size_bytes,
            purpose=purpose,
            malware_scan_status="clean",
            uploaded_by_id=user.id if user else None,
            immutable=True,
        )
        try:
            db.add(record)
            db.flush()
        except IntegrityError:
            raise StoredFileSecurityError("STORED_FILE_PERSISTENCE_CONFLICT") from None
        except SQLAlchemyError:
            raise StoredFileSecurityError("STORED_FILE_PERSISTENCE_CONFLICT") from None

        try:
            if final_path.exists() or final_path.is_symlink():
                if final_path.is_symlink():
                    raise StoredFileSecurityError("STORED_FILE_CONTENT_COLLISION")
                initial_final = _require_safe_retained_path(root, final_path)
                final_sha256, final_size = _verify_retained_bytes(
                    root,
                    final_path,
                    initial_final,
                )
                if final_sha256 != sha256 or final_size != size_bytes:
                    raise StoredFileSecurityError("STORED_FILE_CONTENT_COLLISION")
                promotion_required = False
            else:
                promotion_required = True
        except StoredFileSecurityError:
            raise
        except StoredFileBindingError as exc:
            if exc.code in _STORAGE_ROOT_BINDING_CODES:
                raise StoredFileSecurityError("STORED_FILE_STORAGE_FAILURE") from None
            raise StoredFileSecurityError("STORED_FILE_CONTENT_COLLISION") from None
        except OSError:
            raise StoredFileSecurityError("STORED_FILE_STORAGE_FAILURE") from None

        if promotion_required:
            try:
                os.link(temp_path, final_path, follow_symlinks=False)
                promoted_new_file = True
            except FileExistsError:
                try:
                    raced_metadata = _require_safe_retained_path(root, final_path)
                    raced_sha256, raced_size = _verify_retained_bytes(
                        root,
                        final_path,
                        raced_metadata,
                    )
                except StoredFileBindingError:
                    raise StoredFileSecurityError(
                        "STORED_FILE_CONTENT_COLLISION"
                    ) from None
                if raced_sha256 != sha256 or raced_size != size_bytes:
                    raise StoredFileSecurityError("STORED_FILE_CONTENT_COLLISION") from None
            except OSError:
                raise StoredFileSecurityError("STORED_FILE_STORAGE_FAILURE") from None

        try:
            binding = require_stored_file_binding(
                record,
                storage_root=settings.storage_root,
                required_purpose=purpose,
            )
        except StoredFileBindingError as exc:
            if exc.code in _STORAGE_ROOT_BINDING_CODES:
                raise StoredFileSecurityError("STORED_FILE_STORAGE_FAILURE") from None
            raise StoredFileSecurityError("STORED_FILE_CONTENT_COLLISION") from None
        if promoted_new_file:
            try:
                temp_path.unlink()
            except OSError:
                raise StoredFileSecurityError("UPLOAD_TEMP_CLEANUP_FAILED") from None
            temp_path = None
        return StoredUpload(
            record,
            binding,
            created_record=True,
            promoted_file=promoted_new_file,
        )
    except Exception as exc:
        primary_error = exc
        existing_cleanup_codes = getattr(exc, "cleanup_codes", ())
        if existing_cleanup_codes:
            cleanup_failures.extend(existing_cleanup_codes)
        else:
            exc_code = getattr(exc, "code", None)
            if isinstance(exc_code, str) and exc_code in _CLEANUP_FAILURE_CODES:
                cleanup_failures.append(exc_code)
        if promoted_new_file and final_path is not None:
            try:
                final_path.unlink(missing_ok=True)
                promoted_new_file = False
            except OSError:
                cleanup_failures.append("UPLOAD_RETENTION_CLEANUP_FAILED")
        if cleanup_failures:
            unique_cleanup_failures = tuple(dict.fromkeys(cleanup_failures))
            code = (
                "UPLOAD_MULTIPLE_CLEANUP_FAILED"
                if len(unique_cleanup_failures) > 1
                else unique_cleanup_failures[0]
            )
            raise StoredFileSecurityError(
                code,
                prior_code=_prior_outcome_code(exc),
                cleanup_codes=unique_cleanup_failures,
                content_sha256=getattr(exc, "content_sha256", None),
                content_size_bytes=getattr(exc, "content_size_bytes", None),
            ) from None
        raise
    except BaseException:
        # Cancellation, process exit, and keyboard interrupts must keep their
        # identity. Only best-effort temporary cleanup runs in ``finally``.
        process_control_interrupted = True
        raise
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                if not process_control_interrupted:
                    cleanup_failures.append("UPLOAD_TEMP_CLEANUP_FAILED")
                    code = (
                        "UPLOAD_MULTIPLE_CLEANUP_FAILED"
                        if len(set(cleanup_failures)) > 1
                        else "UPLOAD_TEMP_CLEANUP_FAILED"
                    )
                    raise StoredFileSecurityError(
                        code,
                        prior_code=(
                            _prior_outcome_code(primary_error)
                            if primary_error is not None
                            else None
                        ),
                        cleanup_codes=tuple(dict.fromkeys(cleanup_failures)),
                        content_sha256=(
                            getattr(primary_error, "content_sha256", None)
                            if primary_error is not None
                            else None
                        ),
                        content_size_bytes=(
                            getattr(primary_error, "content_size_bytes", None)
                            if primary_error is not None
                            else None
                        ),
                    ) from None


def save_upload(
    db: Session,
    settings: Settings,
    upload: UploadFile,
    *,
    purpose: str,
    user: User | None,
    malware_scanner: MalwareScanner | None = None,
) -> StoredFile:
    return save_verified_upload(
        db,
        settings,
        upload,
        purpose=purpose,
        user=user,
        malware_scanner=malware_scanner,
    ).stored_file


__all__ = [
    "ALLOWED_EXTENSIONS",
    "StoredFileBinding",
    "StoredFileBindingError",
    "StoredFileSecurityError",
    "StorageReadinessError",
    "StoredUpload",
    "VerifiedStoredFileStream",
    "cleanup_uncommitted_upload",
    "open_verified_stored_file",
    "require_stored_file_binding",
    "require_storage_root_readiness",
    "save_upload",
    "save_verified_upload",
    "sha256_stream",
]
