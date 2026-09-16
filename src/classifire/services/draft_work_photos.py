"""Draft-owned direct photo intake with explicit scan and exact-byte reads."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess  # nosec B404 - fixed local parser module only
import sys
from pathlib import Path
from typing import Any, cast

from sqlalchemy.orm import Session

from ..config import Settings
from ..models import DraftWorkPhotoSource, User
from . import malware_scan
from .draft_scope import DraftScopeError
from .draft_source_intake import DraftSourceIntake, SourcePolicy
from .storage import VerifiedStoredFileContent

PURPOSE = "draft_work_photo"
SCHEMA = "CLASSIFIRE-DRAFT-WORK-PHOTO-v1"
MAX_SOURCES = 20
MAXIMUM_IMAGE_BYTES = min(25 * 1024 * 1024, malware_scan.MAX_SCAN_BYTES)
_FORMATS = {
    ".jpg": (b"\xff\xd8\xff", "image/jpeg"),
    ".jpeg": (b"\xff\xd8\xff", "image/jpeg"),
    ".png": (b"\x89PNG\r\n\x1a\n", "image/png"),
}


def _valid_document(document: dict[str, Any]) -> bool:
    try:
        manifest = document["manifest"]
        return (
            set(document) == {"schema", "manifest"}
            and set(manifest)
            == {"source_sha256", "source_size_bytes", "media_type", "width_px", "height_px"}
            and manifest["media_type"] in {"image/jpeg", "image/png"}
            and type(manifest["width_px"]) is int
            and type(manifest["height_px"]) is int
            and 1 <= manifest["width_px"] <= 12_000
            and 1 <= manifest["height_px"] <= 12_000
            and manifest["width_px"] * manifest["height_px"] <= 50_000_000
        )
    except (KeyError, TypeError):
        return False


def _process(content: bytes) -> bytes:
    command = [sys.executable, "-m", "classifire.services.draft_work_photo_worker"]
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}
    }
    environment.update(
        PYTHONPATH=str(Path(__file__).resolve().parents[2]),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONIOENCODING="utf-8",
    )
    try:
        result = subprocess.run(  # noqa: S603  # nosec B603
            command,
            input=content,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=20,
            check=False,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DraftScopeError("PHOTO_PROCESSING_FAILED", 422) from exc
    if result.returncode != 0 or not 1 <= len(result.stdout) <= 16_384:
        raise DraftScopeError("PHOTO_PROCESSING_FAILED", 422)
    try:
        document = json.loads(result.stdout)
        if (
            document["schema"] != SCHEMA
            or document["manifest"]["source_sha256"] != hashlib.sha256(content).hexdigest()
            or document["manifest"]["source_size_bytes"] != len(content)
            or not _valid_document(document)
        ):
            raise ValueError("worker binding")
    except (KeyError, TypeError, ValueError) as exc:
        raise DraftScopeError("PHOTO_PROCESSING_FAILED", 422) from exc
    return result.stdout


def _intake(suffix: str = ".jpg") -> DraftSourceIntake:
    try:
        magic, media_type = _FORMATS[suffix]
    except KeyError as exc:
        raise DraftScopeError("PHOTO_UPLOAD_INVALID", 422) from exc
    return DraftSourceIntake(
        SourcePolicy(
            model=DraftWorkPhotoSource,
            purpose=PURPOSE,
            extension=suffix,
            magic=magic,
            media_type=media_type,
            schema=SCHEMA,
            code_prefix="PHOTO_",
            audit_name="draft_work_photo",
            process=_process,
            valid_document=_valid_document,
            max_sources=MAX_SOURCES,
        )
    )


def list_sources(db: Session, actor: User, draft_id: str) -> list[dict[str, Any]]:
    return _intake().list_sources(db, actor, draft_id)


def source_info(db: Session, actor: User, draft_id: str, source_id: str) -> dict[str, Any]:
    return _intake().source_info(db, actor, draft_id, source_id)


def retain_photo(
    db: Session, actor: User, draft_id: str, filename: str, content: bytes, *, settings: Settings
) -> DraftWorkPhotoSource:
    suffix = Path(filename).suffix.lower()
    if type(content) is not bytes or not 1 <= len(content) <= MAXIMUM_IMAGE_BYTES:
        raise DraftScopeError("PHOTO_UPLOAD_INVALID", 422)
    return cast(
        DraftWorkPhotoSource,
        _intake(suffix).retain(db, actor, draft_id, filename, content, settings=settings),
    )


def scan_source(
    db: Session, actor: User, draft_id: str, source_id: str, *, settings: Settings
) -> dict[str, Any]:
    return _intake().scan_source(db, actor, draft_id, source_id, settings=settings)


def _document(
    db: Session, actor: User, draft_id: str, source_id: str, storage_root: Path
) -> tuple[DraftWorkPhotoSource, dict[str, Any], VerifiedStoredFileContent]:
    source, document, content = _intake()._document(db, actor, draft_id, source_id, storage_root)
    return cast(DraftWorkPhotoSource, source), document, content


def read_photo(
    db: Session, actor: User, draft_id: str, source_id: str, *, settings: Settings
) -> tuple[dict[str, Any], VerifiedStoredFileContent]:
    _, document, content = _document(db, actor, draft_id, source_id, settings.storage_root)
    if document["manifest"]["media_type"] != content.media_type:
        raise DraftScopeError("PHOTO_SOURCE_NOT_READY", 409)
    return document, content


def dependencies(
    db: Session,
    actor: User,
    draft_id: str,
    source_ids: list[str],
    *,
    settings: Settings,
) -> list[dict[str, Any]]:
    if len(source_ids) > MAX_SOURCES or len(set(source_ids)) != len(source_ids):
        raise DraftScopeError("WORK_RECORD_PHOTOS_INVALID", 422)
    selected = []
    for source_id in sorted(source_ids):
        source, document, content = _document(
            db, actor, draft_id, source_id, settings.storage_root
        )
        manifest = document["manifest"]
        selected.append(
            {
                "source_id": source.id,
                "original_filename": source.original_filename,
                "source_sha256": content.sha256,
                "source_size_bytes": content.size_bytes,
                "media_type": manifest["media_type"],
                "width_px": manifest["width_px"],
                "height_px": manifest["height_px"],
            }
        )
    return selected


__all__ = [
    "MAXIMUM_IMAGE_BYTES",
    "PURPOSE",
    "dependencies",
    "list_sources",
    "read_photo",
    "retain_photo",
    "scan_source",
    "source_info",
]
