from __future__ import annotations

import hashlib
import mimetypes
import shutil
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
