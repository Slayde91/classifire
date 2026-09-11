"""Retained, scanned Word evidence. Inspection never changes the physical scope."""

from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from ..config import Settings
from ..models import DraftScopeDocxSource, User
from .draft_scope import DraftScopeError, _actor, get_draft
from .draft_scope_docx_document import MEDIA_TYPE, SCHEMA, validate_document
from .draft_scope_xlsx import _run_worker
from .draft_source_intake import DraftSourceIntake, SourcePolicy


def _process(content: bytes) -> bytes:
    return _run_worker(content, "--word-evidence", word=True)


def intake() -> DraftSourceIntake:
    return DraftSourceIntake(
        SourcePolicy(
            model=DraftScopeDocxSource,
            purpose="draft_scope_docx",
            extension=".docx",
            magic=b"PK",
            media_type=MEDIA_TYPE,
            schema=SCHEMA,
            code_prefix="SCOPE_DOCX_",
            audit_name="draft_scope_docx",
            process=_process,
            valid_document=validate_document,
        )
    )


def image_preview(
    db: Session, actor: User, draft_id: str, source_id: str, picture_id: str, *, settings: Settings
) -> bytes:
    _, document, content = intake()._document(db, actor, draft_id, source_id, settings.storage_root)
    descriptor = next((item for item in document["pictures"] if item["id"] == picture_id), None)
    if descriptor is None:
        raise DraftScopeError("SCOPE_DOCX_IMAGE_NOT_FOUND", 404)
    preview = _run_worker(content.content, "--word-image", picture_id, image=True, word=True)
    if hashlib.sha256(preview).hexdigest() != descriptor["preview_sha256"]:
        raise DraftScopeError("SCOPE_DOCX_IMAGE_CHANGED", 409)
    _actor(db, actor, "project:read")
    get_draft(db, actor, draft_id)
    return preview
