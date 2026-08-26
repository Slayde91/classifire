from __future__ import annotations

import hashlib
import mimetypes
import os
import tempfile
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, NoReturn

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..config import Settings
from ..models import StoredFile, User
from .malware_scan_attestations import (
    MalwareScanAttestationError,
    append_malware_scan_attestation,
    require_latest_clean_malware_scan_attestation,
)
from .malware_scanning import (
    MalwareDetectedError,
    MalwareScanError,
    MalwareScanner,
    MalwareScanResult,
    configured_malware_scanner,
    require_clean_stream,
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


class StoredFileSecurityError(RuntimeError):
    """A stable, safe-to-display retained-file boundary failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class RetainedMalwareQuarantinedError(MalwareDetectedError):
    """A new FOUND verdict has quarantined an existing exact-SHA record."""


@dataclass(frozen=True, slots=True)
class VerifiedStoredFile:
    """Receipt-bound token for exact retained bytes in one DB transaction."""

    stored_file_id: str
    path: Path
    content_sha256: str
    content_size_bytes: int
    media_type: str | None
    purpose: str
    scan_attestation_id: str
    scan_attestation_sha256: str
    scan_sequence: int


def sha256_stream(stream: BinaryIO) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(1024 * 1024):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def _sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return sha256_stream(stream)[0]


def _normalised_media_type(value: object) -> str:
    return str(value or "").split(";", 1)[0].strip().lower()


def _locked_stored_file_by_sha(db: Session, sha: str) -> StoredFile | None:
    """Lock and refresh one content identity before trusting its disposition."""

    return db.scalar(
        select(StoredFile)
        .where(StoredFile.sha256 == sha)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _require_compatible_retained_upload(
    settings: Settings,
    stored: StoredFile,
    *,
    purpose: str,
    media_type: str | None,
    suffix: str,
    sha: str,
) -> StoredFile:
    if str(stored.malware_scan_status or "").strip().lower() == "infected":
        raise StoredFileSecurityError("STORED_FILE_MALWARE_BLOCKED")
    retained_path = _require_retained_stored_file(
        settings.storage_root,
        stored,
        allowed_purposes={purpose},
        expected_sha256=sha,
    )
    if (
        _normalised_media_type(stored.media_type) != _normalised_media_type(media_type)
        or retained_path.suffix.lower() != suffix
    ):
        raise StoredFileSecurityError("STORED_FILE_CONTEXT_CONFLICT")
    return stored


def _require_matching_scan_result(
    result: MalwareScanResult,
    *,
    sha: str,
    size: int,
) -> None:
    if (
        not isinstance(result, MalwareScanResult)
        or result.content_sha256 != sha
        or result.content_size_bytes != size
    ):
        raise MalwareScanError("MALWARE_SCAN_RESULT_MISMATCH")


def _require_retained_stored_file_record(
    stored: StoredFile,
    *,
    allowed_purposes: Collection[str] | None = None,
    expected_sha256: str | None = None,
) -> Path:
    """Verify identity and exact retained bytes without deciding scan status."""

    digest = str(stored.sha256 or "").strip().lower()
    if (
        stored.immutable is not True
        or len(digest) != 64
        or any(character not in _HEX_SHA256 for character in digest)
        or (expected_sha256 is not None and digest != expected_sha256.lower())
    ):
        raise StoredFileSecurityError("STORED_FILE_INTEGRITY_INVALID")
    if allowed_purposes is not None and stored.purpose not in allowed_purposes:
        raise StoredFileSecurityError("STORED_FILE_CONTEXT_CONFLICT")
    try:
        raw_path = Path(stored.storage_path)
        path = (raw_path if raw_path.is_absolute() else Path.cwd() / raw_path).resolve(strict=True)
        if not path.is_file() or path.stat().st_size != stored.size_bytes:
            raise StoredFileSecurityError("STORED_FILE_INTEGRITY_INVALID")
        if _sha256_file(path) != digest:
            raise StoredFileSecurityError("STORED_FILE_INTEGRITY_INVALID")
    except StoredFileSecurityError:
        raise
    except (OSError, ValueError) as exc:
        raise StoredFileSecurityError("STORED_FILE_INTEGRITY_INVALID") from exc
    return path


def _require_retained_stored_file(
    storage_root: Path,
    stored: StoredFile,
    *,
    allowed_purposes: Collection[str] | None = None,
    expected_sha256: str | None = None,
) -> Path:
    """Return exact retained bytes only when they are inside the governed root."""

    path = _require_retained_stored_file_record(
        stored,
        allowed_purposes=allowed_purposes,
        expected_sha256=expected_sha256,
    )
    try:
        path.relative_to(storage_root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise StoredFileSecurityError("STORED_FILE_INTEGRITY_INVALID") from exc
    return path


def _selected_storage_root(db: Session, storage_root: Path | None) -> Path:
    selected_root: object = (
        storage_root if storage_root is not None else db.info.get("retained_storage_root")
    )
    if not isinstance(selected_root, (str, os.PathLike)):
        raise StoredFileSecurityError("STORED_FILE_INTEGRITY_INVALID")
    return Path(selected_root)


def _raise_stored_attestation_error(exc: MalwareScanAttestationError) -> NoReturn:
    if exc.code == "MALWARE_SCAN_ATTESTATION_REQUIRED":
        code = "STORED_FILE_ATTESTATION_REQUIRED"
    elif exc.code == "MALWARE_SCAN_ATTESTATION_NOT_CLEAN":
        code = "STORED_FILE_MALWARE_BLOCKED"
    else:
        code = "STORED_FILE_ATTESTATION_INVALID"
    raise StoredFileSecurityError(code) from None


def load_processable_stored_file(
    db: Session,
    stored: StoredFile,
    *,
    storage_root: Path | None = None,
    allowed_purposes: Collection[str] | None = None,
    expected_sha256: str | None = None,
) -> VerifiedStoredFile:
    """Lock and return a receipt-bound token for exact processable bytes."""

    try:
        locked, attestation = require_latest_clean_malware_scan_attestation(
            db,
            stored_file_id=stored.id,
        )
    except MalwareScanAttestationError as exc:
        _raise_stored_attestation_error(exc)
    path = _require_retained_stored_file(
        _selected_storage_root(db, storage_root),
        locked,
        allowed_purposes=allowed_purposes,
        expected_sha256=expected_sha256,
    )
    return VerifiedStoredFile(
        stored_file_id=locked.id,
        path=path,
        content_sha256=locked.sha256.lower(),
        content_size_bytes=locked.size_bytes,
        media_type=locked.media_type,
        purpose=locked.purpose,
        scan_attestation_id=attestation.id,
        scan_attestation_sha256=attestation.receipt_sha256,
        scan_sequence=attestation.scan_sequence,
    )


def revalidate_processable_stored_file(
    db: Session,
    verified: VerifiedStoredFile,
    *,
    storage_root: Path | None = None,
) -> None:
    """Fail if bytes or effective scan receipt changed after a token was issued."""

    try:
        locked, attestation = require_latest_clean_malware_scan_attestation(
            db,
            stored_file_id=verified.stored_file_id,
        )
    except MalwareScanAttestationError as exc:
        _raise_stored_attestation_error(exc)
    if (
        attestation.id != verified.scan_attestation_id
        or attestation.receipt_sha256 != verified.scan_attestation_sha256
        or attestation.scan_sequence != verified.scan_sequence
        or locked.sha256.lower() != verified.content_sha256
        or locked.size_bytes != verified.content_size_bytes
        or locked.media_type != verified.media_type
        or locked.purpose != verified.purpose
    ):
        raise StoredFileSecurityError("STORED_FILE_ATTESTATION_STALE")
    path = _require_retained_stored_file(
        _selected_storage_root(db, storage_root),
        locked,
        allowed_purposes={verified.purpose},
        expected_sha256=verified.content_sha256,
    )
    if path != verified.path:
        raise StoredFileSecurityError("STORED_FILE_INTEGRITY_INVALID")


def require_clean_stored_file_for_session(
    db: Session,
    stored: StoredFile,
    *,
    storage_root: Path | None = None,
    allowed_purposes: Collection[str] | None = None,
    expected_sha256: str | None = None,
) -> Path:
    """Compatibility wrapper returning a Path from the receipt-bound gate."""

    return load_processable_stored_file(
        db,
        stored,
        storage_root=storage_root,
        allowed_purposes=allowed_purposes,
        expected_sha256=expected_sha256,
    ).path


def _require_scanner(
    settings: Settings,
    scanner: MalwareScanner | None,
) -> MalwareScanner:
    selected = scanner if scanner is not None else configured_malware_scanner(settings)
    if selected is None:
        raise MalwareScanError("MALWARE_SCANNER_UNAVAILABLE")
    return selected


def record_detected_sha(
    db: Session,
    storage_root: Path,
    *,
    sha: str,
    size: int,
    filename: str,
    media_type: str | None,
    purpose: str,
    user: User | None,
    result: MalwareScanResult,
    scan_source: str,
    actor_type: str = "system",
    actor_name: str = "CLASSIFIRE malware boundary",
) -> StoredFile:
    """Persist a no-content tombstone so a concurrent clean verdict cannot win."""

    existing = _locked_stored_file_by_sha(db, sha)
    created = False
    if existing is None:
        tombstone = StoredFile(
            original_filename=filename,
            media_type=media_type,
            storage_path=str(
                storage_root / ".rejected" / f"{sha}.malware-blocked"
            ),
            sha256=sha,
            size_bytes=size,
            purpose=purpose,
            malware_scan_status="pending_attestation",
            uploaded_by_id=user.id if user else None,
            immutable=True,
        )
        try:
            # A concurrent clean transaction may have inserted the same unique
            # SHA after the lookup. Keep the outer transaction usable so that
            # row can be locked and revoked after the unique conflict resolves.
            with db.begin_nested():
                db.add(tombstone)
                db.flush()
        except IntegrityError:
            existing = _locked_stored_file_by_sha(db, sha)
            if existing is None:  # pragma: no cover - database invariant failure.
                raise
        else:
            existing = tombstone
            created = True

    _require_matching_scan_result(result, sha=sha, size=size)
    previous_status = None if created else str(existing.malware_scan_status or "")
    attestation = append_malware_scan_attestation(
        db,
        stored_file_id=existing.id,
        result=result,
        scan_source=scan_source,
        actor=user,
        actor_type=actor_type,
        actor_name=actor_name,
    )
    record_audit(
        db,
        actor=user,
        action="quarantine_stored_file_after_malware_detection",
        entity_type="stored_file",
        entity_id=existing.id,
        previous_value={"malware_scan_status": previous_status},
        new_value={
            "malware_scan_status": "infected",
            "content_retained": False if created else None,
            "malware_scan_attestation_sha256": attestation.receipt_sha256,
        },
        reason=(
            "A new scan of exact matching bytes returned a malware verdict; "
            "the SHA-256 identity was quarantined fail-closed."
        ),
        actor_type="user" if user is not None else actor_type,
        actor_name=None if user is not None else actor_name,
    )
    db.flush()
    return existing


def _accept_clean_existing_upload(
    db: Session,
    settings: Settings,
    stored: StoredFile,
    *,
    purpose: str,
    media_type: str | None,
    suffix: str,
    sha: str,
    result: MalwareScanResult,
    user: User | None,
) -> StoredFile:
    _require_compatible_retained_upload(
        settings,
        stored,
        purpose=purpose,
        media_type=media_type,
        suffix=suffix,
        sha=sha,
    )
    # A new clean verdict may extend an existing trustworthy lineage, but it
    # must not rehabilitate a pending or legacy status-only row. Establish the
    # existing file's attested-clean basis before appending the new observation.
    require_clean_stored_file_for_session(
        db,
        stored,
        storage_root=settings.storage_root,
        allowed_purposes={purpose},
        expected_sha256=sha,
    )
    append_malware_scan_attestation(
        db,
        stored_file_id=stored.id,
        result=result,
        scan_source="upload",
        actor=user,
    )
    require_clean_stored_file_for_session(
        db,
        stored,
        storage_root=settings.storage_root,
        allowed_purposes={purpose},
        expected_sha256=sha,
    )
    return stored


def save_upload(
    db: Session,
    settings: Settings,
    upload: UploadFile,
    *,
    purpose: str,
    user: User | None,
    malware_scanner: MalwareScanner | None = None,
) -> StoredFile:
    """Quarantine and scan an upload before any durable promotion or parser access."""

    filename = Path(upload.filename or "unnamed").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {suffix}")
    scanner = _require_scanner(settings, malware_scanner)
    media_type = upload.content_type or mimetypes.guess_type(filename)[0]
    spool = settings.storage_root / ".incoming"
    spool.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        size = 0
        digest = hashlib.sha256()
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix="upload-",
            suffix=".quarantine",
            dir=spool,
            delete=False,
        ) as destination:
            temporary_name = destination.name
            while chunk := upload.file.read(1024 * 1024):
                if not isinstance(chunk, bytes):
                    raise ValueError("Upload stream returned invalid bytes")
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise ValueError(f"File exceeds {settings.max_upload_mb} MB limit")
                digest.update(chunk)
                destination.write(chunk)
            destination.flush()
            os.fsync(destination.fileno())

        sha = digest.hexdigest()
        temp_path = Path(temporary_name)
        try:
            with temp_path.open("rb") as quarantined:
                scan_result = require_clean_stream(
                    scanner,
                    quarantined,
                    expected_sha256=sha,
                    expected_size_bytes=size,
                )
        except MalwareDetectedError as detected:
            _require_matching_scan_result(detected.result, sha=sha, size=size)
            record_detected_sha(
                db,
                settings.storage_root,
                sha=sha,
                size=size,
                filename=filename,
                media_type=media_type,
                purpose=purpose,
                user=user,
                result=detected.result,
                scan_source="upload",
            )
            raise RetainedMalwareQuarantinedError(detected.result) from None
        _require_matching_scan_result(scan_result, sha=sha, size=size)

        existing = _locked_stored_file_by_sha(db, sha)
        if existing is not None:
            return _accept_clean_existing_upload(
                db,
                settings,
                existing,
                purpose=purpose,
                media_type=media_type,
                suffix=suffix,
                sha=sha,
                result=scan_result,
                user=user,
            )

        final_dir = settings.storage_root / sha[:2] / sha[2:4]
        final_dir.mkdir(parents=True, exist_ok=True)
        final_path = final_dir / f"{sha}{suffix}"
        promotion_required = not final_path.exists()
        if not promotion_required:
            try:
                if (
                    not final_path.is_file()
                    or final_path.stat().st_size != size
                    or _sha256_file(final_path) != sha
                ):
                    raise StoredFileSecurityError("STORED_FILE_CONTENT_COLLISION")
            except OSError as exc:
                raise StoredFileSecurityError("STORED_FILE_CONTENT_COLLISION") from exc

        record = StoredFile(
            original_filename=filename,
            media_type=media_type,
            storage_path=str(final_path),
            sha256=sha,
            size_bytes=size,
            purpose=purpose,
            malware_scan_status="pending_attestation",
            uploaded_by_id=user.id if user else None,
            immutable=True,
        )
        try:
            # The unique SHA-256 identity serialises simultaneous clean and
            # infected verdicts. Keep a losing insert inside a savepoint so the
            # winning row can be locked, refreshed and revalidated safely.
            with db.begin_nested():
                db.add(record)
                db.flush()
                append_malware_scan_attestation(
                    db,
                    stored_file_id=record.id,
                    result=scan_result,
                    scan_source="upload",
                    actor=user,
                )
                if promotion_required:
                    os.replace(temp_path, final_path)
                    temporary_name = None
        except IntegrityError as exc:
            winner = _locked_stored_file_by_sha(db, sha)
            if winner is None:  # pragma: no cover - database invariant failure.
                raise StoredFileSecurityError("STORED_FILE_PERSISTENCE_CONFLICT") from exc
            return _accept_clean_existing_upload(
                db,
                settings,
                winner,
                purpose=purpose,
                media_type=media_type,
                suffix=suffix,
                sha=sha,
                result=scan_result,
                user=user,
            )
        except OSError as exc:
            raise StoredFileSecurityError("STORED_FILE_STORAGE_FAILURE") from exc
        require_clean_stored_file_for_session(
            db,
            record,
            storage_root=settings.storage_root,
            allowed_purposes={purpose},
            expected_sha256=sha,
        )
        return record
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass


__all__ = [
    "ALLOWED_EXTENSIONS",
    "RetainedMalwareQuarantinedError",
    "StoredFileSecurityError",
    "VerifiedStoredFile",
    "load_processable_stored_file",
    "revalidate_processable_stored_file",
    "require_clean_stored_file_for_session",
    "record_detected_sha",
    "save_upload",
    "sha256_stream",
]
