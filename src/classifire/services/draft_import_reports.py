"""Original imported report attachments reuse shared owner/scan/quarantine checks."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess  # nosec B404
import sys
from functools import partial
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..audit import record_audit
from ..config import Settings
from ..models import DraftImportedReportSource, User
from .draft_scope import DraftScopeError
from .draft_source_intake import DraftSourceIntake, SourcePolicy

SCHEMA = "CLASSIFIRE-IMPORTED-REPORT-BINARY-v1"


def _process(content: bytes, *, format_name: str) -> bytes:
    environment = {
        k: v
        for k, v in os.environ.items()
        if k.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}
    }
    environment.update(
        PYTHONPATH=str(Path(__file__).resolve().parents[2]),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONIOENCODING="utf-8",
    )
    try:
        result = subprocess.run(  # noqa: S603 # nosec B603
            [sys.executable, "-m", "classifire.services.draft_import_report_worker", format_name],
            input=content,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            env=environment,
            check=False,
        )
        if result.returncode != 0 or not 1 <= len(result.stdout) <= 8192:
            raise ValueError("worker")
        value = json.loads(result.stdout)
        if (
            value.get("schema") != SCHEMA
            or value["format"] != format_name
            or value["manifest"]
            != {
                "source_sha256": hashlib.sha256(content).hexdigest(),
                "source_size_bytes": len(content),
            }
        ):
            raise ValueError("binding")
        return result.stdout
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        raise DraftScopeError("IMPORTED_REPORT_PROCESSING_FAILED", 422) from exc


def intake(format_name: str) -> DraftSourceIntake:
    if format_name not in ("pdf", "xlsx"):
        raise DraftScopeError("IMPORTED_REPORT_FORMAT_INVALID", 422)
    return DraftSourceIntake(
        SourcePolicy(
            model=DraftImportedReportSource,
            purpose="draft_import_report_" + format_name,
            extension="." + format_name,
            magic=b"%PDF-" if format_name == "pdf" else b"PK\x03\x04",
            media_type="application/pdf"
            if format_name == "pdf"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            schema=SCHEMA,
            code_prefix="IMPORTED_REPORT_",
            audit_name="draft_import_report",
            process=partial(_process, format_name=format_name),
            valid_document=lambda d: (
                d.get("format") == format_name and d.get("authority") == "foreign_unverified"
            ),
            allow_supplied_content_reuse=True,
            max_sources=128,
        )
    )


def _member(db: Session, actor: User, draft_id: str, source_id: str, *, export: bool = False):
    from .draft_package_materialization import read_import

    row, original, mapping = read_import(db, actor, draft_id, export=export)
    for report in mapping["reports"]:
        for fmt, member in report["members"].items():
            if member["source_id"] == source_id:
                return row, original, fmt, member
    raise DraftScopeError("IMPORTED_REPORT_NOT_FOUND", 404)


def scan(
    db: Session, actor: User, draft_id: str, source_id: str, *, settings: Settings
) -> dict[str, Any]:
    _row, _original, fmt, _member_ref = _member(db, actor, draft_id, source_id)
    return intake(fmt).scan_source(db, actor, draft_id, source_id, settings=settings)


def checked_bytes(
    db: Session, actor: User, draft_id: str, source_id: str, *, settings: Settings
) -> bytes:
    _row, original, fmt, member = _member(db, actor, draft_id, source_id, export=True)
    _source, _document, content = intake(fmt)._document(
        db, actor, draft_id, source_id, settings.storage_root
    )
    if content.content != original.resolve(member["path"]) or content.sha256 != member["sha256"]:
        raise DraftScopeError("IMPORTED_REPORT_INTEGRITY_FAILED", 409)
    _member(db, actor, draft_id, source_id, export=True)
    return content.content


def download(
    db: Session, actor: User, draft_id: str, source_id: str, *, settings: Settings
) -> bytes:
    value = checked_bytes(db, actor, draft_id, source_id, settings=settings)
    record_audit(
        db,
        actor=actor,
        action="draft_import_report.download",
        entity_type="draft_import_report_source",
        entity_id=source_id,
        new_value={"sha256": hashlib.sha256(value).hexdigest()},
    )
    db.flush()
    return value


def original_archive(db: Session, actor: User, draft_id: str, *, settings: Settings) -> bytes:
    from .draft_package_materialization import read_import

    row, _original, mapping = read_import(db, actor, draft_id, export=True)
    for report in mapping["reports"]:
        for member in report["members"].values():
            checked_bytes(db, actor, draft_id, member["source_id"], settings=settings)
    return row.archive_bytes


def download_original_archive(
    db: Session, actor: User, draft_id: str, *, settings: Settings
) -> bytes:
    content = original_archive(db, actor, draft_id, settings=settings)
    from .draft_scope import get_draft

    draft = get_draft(db, actor, draft_id)
    record_audit(
        db,
        actor=actor,
        action="draft_package.original_download",
        entity_type="draft_scope",
        entity_id=draft_id,
        project_id=draft.project_id,
        new_value={"archive_sha256": hashlib.sha256(content).hexdigest()},
    )
    db.flush()
    return content
