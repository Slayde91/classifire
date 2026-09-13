"""Session-authenticated Word/PDF controls over the shared retained-source intake.

The historical module name and Word routes remain compatible."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from .config import get_settings
from .draft_scope_docx_ui import FormData, UploadData
from .draft_scope_ui import Db
from .security import has_permission, verify_csrf
from .services import draft_pdf_intake as pdf
from .services import draft_scope_docx as word
from .services.draft_scope import DraftScopeError, get_draft
from .services.draft_source_intake import DraftSourceIntake
from .services.malware_scan import MAX_SCAN_BYTES
from .ui import _require

SourceKind = Literal["word", "pdf"]
router = APIRouter(prefix="/scopes/{draft_id}/assistant/{source_kind}", include_in_schema=False)


def _intake(source_kind: SourceKind) -> DraftSourceIntake:
    return word.intake() if source_kind == "word" else pdf._intake()


def _response(value: object) -> JSONResponse:
    return JSONResponse(jsonable_encoder(value), headers={"Cache-Control": "no-store"})


@router.get("")
def sources(request: Request, db: Db, draft_id: str, source_kind: SourceKind) -> JSONResponse:
    actor = _require(request, db, "project:read")
    try:
        draft = get_draft(db, actor, draft_id)
        return _response(
            {
                "draft_id": draft.id,
                "can_write": has_permission(actor, "project:write"),
                "reference": draft.project.reference,
                "name": draft.project.name,
                "sources": _intake(source_kind).list_sources(db, actor, draft_id),
                "max_upload_bytes": min(get_settings().max_upload_bytes, MAX_SCAN_BYTES),
            }
        )
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from None


@router.post("/upload")
def upload(
    request: Request, db: Db, draft_id: str, source_kind: SourceKind, data: UploadData
) -> JSONResponse:
    actor = _require(request, db, "project:write")
    try:
        api = _intake(source_kind)
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
def scan(
    request: Request,
    db: Db,
    draft_id: str,
    source_id: str,
    source_kind: SourceKind,
    form: FormData,
) -> JSONResponse:
    actor = _require(request, db, "project:write")
    verify_csrf(request, form.get("csrf_token"))
    if set(form) != {"csrf_token"}:
        raise HTTPException(422, "Use the scan control")
    try:
        api = _intake(source_kind)
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
    source_kind: SourceKind,
    page: int = Query(default=1, ge=1, le=50),
    after_block: int = Query(default=0, ge=0, le=1000),
) -> JSONResponse:
    actor = _require(request, db, "project:read")
    try:
        source, document, _ = _intake(source_kind)._document(
            db, actor, draft_id, source_id, get_settings().storage_root
        )
        if source_kind == "pdf":
            if after_block != 0 or page > len(document["pages"]):
                raise DraftScopeError("PDF_PAGE_NOT_FOUND", 404)
            return _response(
                {
                    "source_id": source.id,
                    "document_sha256": source.document_sha256,
                    "page": document["pages"][page - 1],
                    "total_pages": len(document["pages"]),
                }
            )
        if page != 1:
            raise DraftScopeError("CHAT_INPUT_INVALID", 422)
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


@router.get("/{source_id}/original")
def original(
    request: Request, db: Db, draft_id: str, source_id: str, source_kind: SourceKind
) -> Response:
    actor = _require(request, db, "project:read")
    api = _intake(source_kind)
    try:
        _, _, content = api._document(db, actor, draft_id, source_id, get_settings().storage_root)
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from None
    return Response(
        content.content,
        media_type=api.policy.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="retained-report{api.policy.extension}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
