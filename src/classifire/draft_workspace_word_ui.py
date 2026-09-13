"""Session-authenticated Word attachment controls for the native workspace panel."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from .config import get_settings
from .draft_scope_docx_ui import FormData, UploadData
from .draft_scope_ui import Db
from .security import has_permission, verify_csrf
from .services import draft_scope_docx as word
from .services.draft_scope import DraftScopeError, get_draft
from .services.malware_scan import MAX_SCAN_BYTES
from .ui import _require

router = APIRouter(prefix="/scopes/{draft_id}/assistant/word", include_in_schema=False)


def _response(value: object) -> JSONResponse:
    return JSONResponse(jsonable_encoder(value), headers={"Cache-Control": "no-store"})


@router.get("")
def sources(request: Request, db: Db, draft_id: str) -> JSONResponse:
    actor = _require(request, db, "project:read")
    try:
        draft = get_draft(db, actor, draft_id)
        return _response(
            {
                "draft_id": draft.id,
                "can_write": has_permission(actor, "project:write"),
                "reference": draft.project.reference,
                "name": draft.project.name,
                "sources": word.intake().list_sources(db, actor, draft_id),
                "max_upload_bytes": min(get_settings().max_upload_bytes, MAX_SCAN_BYTES),
            }
        )
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from None


@router.post("/upload")
def upload(request: Request, db: Db, draft_id: str, data: UploadData) -> JSONResponse:
    actor = _require(request, db, "project:write")
    try:
        api = word.intake()
        source = api.retain(
            db, actor, draft_id, data["filename"], data["content"], settings=get_settings()
        )
        result = api.source_info(db, actor, draft_id, source.id)
        db.commit()
        return _response(result)
    except DraftScopeError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.code) from None


@router.post("/{source_id}/scan")
def scan(request: Request, db: Db, draft_id: str, source_id: str, form: FormData) -> JSONResponse:
    actor = _require(request, db, "project:write")
    verify_csrf(request, form.get("csrf_token"))
    if set(form) != {"csrf_token"}:
        raise HTTPException(422, "Use the scan control")
    try:
        api = word.intake()
        api.scan_source(db, actor, draft_id, source_id, settings=get_settings())
        result = api.source_info(db, actor, draft_id, source_id)
        db.commit()
        return _response(result)
    except DraftScopeError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.code) from None


@router.get("/{source_id}")
def evidence(
    request: Request,
    db: Db,
    draft_id: str,
    source_id: str,
    after_block: int = Query(default=0, ge=0, le=1000),
) -> JSONResponse:
    actor = _require(request, db, "project:read")
    try:
        source, document, _ = word.intake()._document(
            db, actor, draft_id, source_id, get_settings().storage_root
        )
        last = min(after_block + 5, len(document["blocks"]))
        blocks = document["blocks"][after_block:last]
        pictures = {identity for block in blocks for identity in block["pictures"]}
        return _response(
            {
                "source_id": source.id,
                "document_sha256": source.document_sha256,
                "blocks": blocks,
                "pictures": [p for p in document["pictures"] if p["id"] in pictures],
                "after_block": after_block,
                "next_after_block": last if last < len(document["blocks"]) else None,
                "total_blocks": len(document["blocks"]),
            }
        )
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from None
