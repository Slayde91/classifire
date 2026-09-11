"""Word evidence upload, explicit scan and source inspection in the shared UI."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from .config import get_settings
from .draft_pdf_ui import _upload
from .draft_scope_ui import Db, _form_values
from .security import verify_csrf
from .services import draft_scope_docx as word
from .services.draft_scope import DraftScopeError, get_draft
from .ui import _context, _require, templates

router = APIRouter(include_in_schema=False)
UploadData = Annotated[dict[str, Any], Depends(_upload)]


async def _form(request: Request) -> dict[str, str]:
    return await _form_values(request, 4000, max_fields=1)


FormData = Annotated[dict[str, str], Depends(_form)]


def _page(
    request: Request,
    db: Db,
    draft_id: str,
    source_id: str | None = None,
    *,
    error: str | None = None,
    status: int = 200,
) -> HTMLResponse:
    actor = _require(request, db, "project:read")
    source = document = None
    try:
        draft = get_draft(db, actor, draft_id)
        sources = word.intake().list_sources(db, actor, draft_id)
        if source_id is not None:
            source = word.intake().source_info(db, actor, draft_id, source_id)
            if source["ready"]:
                _, document, _ = word.intake()._document(
                    db, actor, draft_id, source_id, get_settings().storage_root
                )
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from exc
    return templates.TemplateResponse(
        request,
        "draft_scope_docx.html",
        _context(
            request,
            db,
            draft=draft,
            project=draft.project,
            sources=sources,
            source=source,
            document=document,
            error=error,
            postgres=db.get_bind().dialect.name == "postgresql",
        ),
        status_code=status,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/scopes/{draft_id}/word", response_class=HTMLResponse)
def sources_page(request: Request, db: Db, draft_id: str) -> HTMLResponse:
    return _page(request, db, draft_id)


@router.post("/scopes/{draft_id}/word/upload", response_model=None)
def upload(request: Request, db: Db, draft_id: str, data: UploadData):
    actor = _require(request, db, "project:write")
    try:
        source = word.intake().retain(
            db, actor, draft_id, data["filename"], data["content"], settings=get_settings()
        )
        db.commit()
    except DraftScopeError as exc:
        db.rollback()
        if exc.status_code in {403, 404}:
            raise HTTPException(exc.status_code, exc.code) from exc
        return _page(request, db, draft_id, error=exc.code, status=exc.status_code)
    return RedirectResponse(f"/scopes/{draft_id}/word/{source.id}", status_code=303)


@router.get("/scopes/{draft_id}/word/{source_id}", response_class=HTMLResponse)
def source_page(request: Request, db: Db, draft_id: str, source_id: str) -> HTMLResponse:
    return _page(request, db, draft_id, source_id)


@router.post("/scopes/{draft_id}/word/{source_id}/scan", response_model=None)
def scan(request: Request, db: Db, draft_id: str, source_id: str, form: FormData):
    verify_csrf(request, form.get("csrf_token"))
    actor = _require(request, db, "project:write")
    if set(form) != {"csrf_token"}:
        raise HTTPException(422, "Use the scan control")
    try:
        word.intake().scan_source(db, actor, draft_id, source_id, settings=get_settings())
        db.commit()
    except DraftScopeError as exc:
        db.rollback()
        if exc.status_code in {403, 404}:
            raise HTTPException(exc.status_code, exc.code) from exc
        return _page(request, db, draft_id, source_id, error=exc.code, status=exc.status_code)
    return RedirectResponse(f"/scopes/{draft_id}/word/{source_id}", status_code=303)


@router.get("/scopes/{draft_id}/word/{source_id}/pictures/{picture_id}")
def picture(request: Request, db: Db, draft_id: str, source_id: str, picture_id: str) -> Response:
    actor = _require(request, db, "project:read")
    try:
        content = word.image_preview(
            db, actor, draft_id, source_id, picture_id, settings=get_settings()
        )
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from exc
    return Response(
        content,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/scopes/{draft_id}/word/{source_id}/original")
def original(request: Request, db: Db, draft_id: str, source_id: str) -> Response:
    actor = _require(request, db, "project:read")
    try:
        _, _, content = word.intake()._document(
            db, actor, draft_id, source_id, get_settings().storage_root
        )
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from exc
    return Response(
        content.content,
        media_type=word.MEDIA_TYPE,
        headers={
            "Content-Disposition": 'attachment; filename="retained-word-report.docx"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
