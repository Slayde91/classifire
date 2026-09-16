"""Native UI for explicitly scanned Draft work-photo evidence."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from .config import get_settings
from .draft_scope_ui import Db, FormData
from .security import verify_csrf
from .services import draft_work_photos as photos
from .services.draft_scope import DraftScopeError, get_draft
from .ui import _context, _require, templates
from .ui_uploads import single_file

router = APIRouter(include_in_schema=False)


async def _upload(request: Request, db: Db) -> dict[str, Any]:
    _require(request, db, "project:write")
    limit = min(
        get_settings().max_upload_bytes,
        photos.MAXIMUM_IMAGE_BYTES,
    )
    return await single_file(request, limit)


UploadData = Annotated[dict[str, Any], Depends(_upload)]


def _failure(exc: DraftScopeError) -> HTTPException:
    return HTTPException(exc.status_code, exc.code)


@router.get("/scopes/{draft_id}/work-photos", response_class=HTMLResponse)
def photo_list(request: Request, db: Db, draft_id: str) -> HTMLResponse:
    actor = _require(request, db, "project:read")
    try:
        draft = get_draft(db, actor, draft_id)
        sources = photos.list_sources(db, actor, draft_id)
    except DraftScopeError as exc:
        raise _failure(exc) from exc
    return templates.TemplateResponse(
        request,
        "draft_work_photos.html",
        _context(request, db, draft=draft, project=draft.project, sources=sources, source=None),
        headers={"Cache-Control": "no-store"},
    )


@router.post("/scopes/{draft_id}/work-photos/upload")
def upload_photo(request: Request, db: Db, draft_id: str, data: UploadData) -> RedirectResponse:
    actor = _require(request, db, "project:write")
    try:
        source = photos.retain_photo(
            db, actor, draft_id, data["filename"], data["content"], settings=get_settings()
        )
        db.commit()
    except DraftScopeError as exc:
        db.rollback()
        raise _failure(exc) from exc
    return RedirectResponse(f"/scopes/{draft_id}/work-photos/{source.id}", status_code=303)


@router.get("/scopes/{draft_id}/work-photos/{source_id}", response_class=HTMLResponse)
def photo_page(request: Request, db: Db, draft_id: str, source_id: str) -> HTMLResponse:
    actor = _require(request, db, "project:read")
    problem = None
    try:
        draft = get_draft(db, actor, draft_id)
        source = photos.source_info(db, actor, draft_id, source_id)
        document = None
        if source["ready"]:
            try:
                document, _ = photos.read_photo(
                    db, actor, draft_id, source_id, settings=get_settings()
                )
            except DraftScopeError as exc:
                if exc.status_code in {403, 404}:
                    raise
                problem = exc.code
    except DraftScopeError as exc:
        raise _failure(exc) from exc
    return templates.TemplateResponse(
        request,
        "draft_work_photos.html",
        _context(
            request,
            db,
            draft=draft,
            project=draft.project,
            sources=None,
            source=source,
            document=document,
            problem=problem,
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.post("/scopes/{draft_id}/work-photos/{source_id}/scan")
def scan_photo(
    request: Request, db: Db, draft_id: str, source_id: str, form: FormData
) -> RedirectResponse:
    actor = _require(request, db, "project:write")
    verify_csrf(request, form.get("csrf_token"))
    if set(form) != {"csrf_token"}:
        raise HTTPException(422, "Invalid scan request")
    try:
        photos.scan_source(db, actor, draft_id, source_id, settings=get_settings())
        db.commit()
    except DraftScopeError as exc:
        db.rollback()
        raise _failure(exc) from exc
    return RedirectResponse(f"/scopes/{draft_id}/work-photos/{source_id}", status_code=303)


@router.get("/scopes/{draft_id}/work-photos/{source_id}/original")
def original_photo(request: Request, db: Db, draft_id: str, source_id: str) -> Response:
    actor = _require(request, db, "project:read")
    try:
        document, content = photos.read_photo(
            db, actor, draft_id, source_id, settings=get_settings()
        )
    except DraftScopeError as exc:
        raise _failure(exc) from exc
    suffix = "jpg" if document["manifest"]["media_type"] == "image/jpeg" else "png"
    return Response(
        content.content,
        media_type=document["manifest"]["media_type"],
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'inline; filename="draft-work-photo-{source_id}.{suffix}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
