from __future__ import annotations

import hashlib
import mimetypes
import os
import shutil
import stat
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import StoredFile, User

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

_HEX_SHA256 = frozenset('0123456789abcdef')
_REPARSE_POINT_ATTRIBUTE = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x0400)


class StoredFileBindingError(RuntimeError):
    '''A stable, path-free retained-file binding failure.'''

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f'Stored file binding failed: {code}.')


@dataclass(frozen=True, slots=True)
class VerifiedStoredFileContent:
    '''The exact retained bytes that were checked against one StoredFile record.'''

    sha256: str
    size_bytes: int
    media_type: str | None
    content: bytes


@dataclass(frozen=True, slots=True)
class _StoredFileReadContext:
    root: Path
    path: Path
    initial: os.stat_result
    sha256: str
    size_bytes: int


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
    attributes = int(getattr(metadata, 'st_file_attributes', 0))
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
        raise _binding_error('STORAGE_ROOT_UNSAFE')
    root_metadata = _safe_lstat(
        root,
        missing_code='STORAGE_ROOT_INVALID',
        unsafe_code='STORAGE_ROOT_UNSAFE',
    )
    for component in _path_lineage(root):
        _safe_lstat(
            component,
            missing_code='STORAGE_ROOT_INVALID',
            unsafe_code='STORAGE_ROOT_UNSAFE',
        )
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise _binding_error('STORAGE_ROOT_INVALID')


def _require_safe_retained_path(root: Path, path: Path) -> os.stat_result:
    try:
        relative = path.relative_to(root)
    except ValueError:
        raise _binding_error('STORED_FILE_PATH_OUTSIDE_ROOT') from None
    current = root
    for part in relative.parts[:-1]:
        current /= part
        metadata = _safe_lstat(
            current,
            missing_code='STORED_FILE_PATH_INVALID',
            unsafe_code='STORED_FILE_PATH_UNSAFE',
        )
        if not stat.S_ISDIR(metadata.st_mode):
            raise _binding_error('STORED_FILE_PATH_INVALID')
    metadata = _safe_lstat(
        path,
        missing_code='STORED_FILE_PATH_INVALID',
        unsafe_code='STORED_FILE_PATH_UNSAFE',
    )
    if not stat.S_ISREG(metadata.st_mode):
        raise _binding_error('STORED_FILE_NOT_REGULAR')
    return metadata


def _stat_signature(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
    )


def _normalise_scan_statuses(statuses: Collection[str]) -> frozenset[str]:
    if isinstance(statuses, (str, bytes)):
        raise ValueError('allowed_scan_statuses must be a non-empty collection of status strings')
    values = tuple(statuses)
    if not values or any(not isinstance(value, str) or value != value.strip() for value in values):
        raise ValueError('allowed_scan_statuses must be a non-empty collection of status strings')
    return frozenset(value.casefold() for value in values)


def _stored_file_read_context(
    stored: StoredFile,
    *,
    storage_root: Path,
    required_purpose: str,
    allowed_scan_statuses: Collection[str],
) -> _StoredFileReadContext:
    if (
        not isinstance(required_purpose, str)
        or not required_purpose
        or required_purpose != required_purpose.strip()
    ):
        raise ValueError('required_purpose must be a non-empty, trimmed string')
    allowed_statuses = _normalise_scan_statuses(allowed_scan_statuses)
    if stored.purpose != required_purpose:
        raise _binding_error('STORED_FILE_PURPOSE_MISMATCH')
    if stored.immutable is not True:
        raise _binding_error('STORED_FILE_NOT_IMMUTABLE')
    scan_status = stored.malware_scan_status
    if (
        not isinstance(scan_status, str)
        or scan_status != scan_status.strip()
        or scan_status.casefold() not in allowed_statuses
    ):
        raise _binding_error('STORED_FILE_SCAN_STATUS_FORBIDDEN')
    sha256 = stored.sha256
    if (
        not isinstance(sha256, str)
        or len(sha256) != 64
        or any(character not in _HEX_SHA256 for character in sha256.casefold())
    ):
        raise _binding_error('STORED_FILE_SHA256_INVALID')
    size_bytes = stored.size_bytes
    if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 1:
        raise _binding_error('STORED_FILE_SIZE_INVALID')
    if not isinstance(stored.storage_path, str) or not stored.storage_path.strip():
        raise _binding_error('STORED_FILE_PATH_INVALID')

    raw_root, root = _absolute_lexical(storage_root)
    if raw_root != root:
        raise _binding_error('STORAGE_ROOT_INVALID')
    _require_safe_storage_root(root)
    raw_path, path = _absolute_lexical(Path(stored.storage_path))
    if raw_path != path:
        raise _binding_error('STORED_FILE_PATH_INVALID')
    try:
        path.relative_to(root)
    except ValueError:
        raise _binding_error('STORED_FILE_PATH_OUTSIDE_ROOT') from None
    return _StoredFileReadContext(
        root=root,
        path=path,
        initial=_require_safe_retained_path(root, path),
        sha256=sha256.casefold(),
        size_bytes=size_bytes,
    )


def _read_verified_retained_bytes(context: _StoredFileReadContext) -> tuple[bytes, str, int]:
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    try:
        descriptor = os.open(context.path, flags)
    except OSError:
        raise _binding_error('STORED_FILE_READ_FAILED') from None
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or _stat_signature(opened) != _stat_signature(
            context.initial
        ):
            raise _binding_error('STORED_FILE_CHANGED_DURING_READ')
        digest = hashlib.sha256()
        content = bytearray()
        while chunk := os.read(descriptor, 1024 * 1024):
            content.extend(chunk)
            if len(content) > context.size_bytes:
                raise _binding_error('STORED_FILE_SIZE_MISMATCH')
            digest.update(chunk)
        finished = os.fstat(descriptor)
        try:
            _require_safe_storage_root(context.root)
            final = _require_safe_retained_path(context.root, context.path)
        except StoredFileBindingError:
            raise _binding_error('STORED_FILE_CHANGED_DURING_READ') from None
        signature = _stat_signature(context.initial)
        if _stat_signature(finished) != signature or _stat_signature(final) != signature:
            raise _binding_error('STORED_FILE_CHANGED_DURING_READ')
        return bytes(content), digest.hexdigest(), len(content)
    except StoredFileBindingError:
        raise
    except OSError:
        raise _binding_error('STORED_FILE_READ_FAILED') from None
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass


def read_verified_stored_file(
    stored: StoredFile,
    *,
    storage_root: Path,
    required_purpose: str,
    allowed_scan_statuses: Collection[str] = ('clean',),
) -> VerifiedStoredFileContent:
    '''Return the exact bytes bound to one immutable, allowed StoredFile record.

    No path or live stream escapes this boundary. Consumers therefore cannot
    accidentally reopen different bytes after the identity and content checks.
    The caller still owns any database transaction needed to serialize a later
    scan-state transition with its wider workflow.
    '''

    context = _stored_file_read_context(
        stored,
        storage_root=storage_root,
        required_purpose=required_purpose,
        allowed_scan_statuses=allowed_scan_statuses,
    )
    content, actual_sha256, actual_size = _read_verified_retained_bytes(context)
    if actual_size != context.size_bytes:
        raise _binding_error('STORED_FILE_SIZE_MISMATCH')
    if actual_sha256 != context.sha256:
        raise _binding_error('STORED_FILE_HASH_MISMATCH')
    return VerifiedStoredFileContent(
        sha256=context.sha256,
        size_bytes=context.size_bytes,
        media_type=stored.media_type,
        content=content,
    )


def sha256_stream(stream: BinaryIO) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(1024 * 1024):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def save_upload(
    db: Session,
    settings: Settings,
    upload: UploadFile,
    *,
    purpose: str,
    user: User | None,
) -> StoredFile:
    filename = Path(upload.filename or "unnamed").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {suffix}")
    spool = settings.storage_root / ".incoming"
    spool.mkdir(parents=True, exist_ok=True)
    temp_path = spool / f"upload-{hashlib.sha256(filename.encode()).hexdigest()[:12]}-{filename}"
    size = 0
    digest = hashlib.sha256()
    with temp_path.open("wb") as destination:
        while chunk := upload.file.read(1024 * 1024):
            size += len(chunk)
            if size > settings.max_upload_bytes:
                destination.close()
                temp_path.unlink(missing_ok=True)
                raise ValueError(f"File exceeds {settings.max_upload_mb} MB limit")
            digest.update(chunk)
            destination.write(chunk)
    sha = digest.hexdigest()
    existing = db.scalar(select(StoredFile).where(StoredFile.sha256 == sha))
    if existing:
        temp_path.unlink(missing_ok=True)
        return existing
    final_dir = settings.storage_root / sha[:2] / sha[2:4]
    final_dir.mkdir(parents=True, exist_ok=True)
    final_path = final_dir / f"{sha}{suffix}"
    shutil.move(str(temp_path), final_path)
    media_type = upload.content_type or mimetypes.guess_type(filename)[0]
    record = StoredFile(
        original_filename=filename,
        media_type=media_type,
        storage_path=str(final_path),
        sha256=sha,
        size_bytes=size,
        purpose=purpose,
        malware_scan_status="not_configured" if not settings.clamav_host else "pending",
        uploaded_by_id=user.id if user else None,
        immutable=True,
    )
    db.add(record)
    db.flush()
    return record
