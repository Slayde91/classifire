"""Thin authenticated UI for the shared Draft PDF intake commands."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.datastructures import UploadFile

from .config import get_settings
from .draft_scope_ui import Db, FormData
from .security import verify_csrf
from .services import draft_pdf_intake as intake
from .services.draft_scope import DraftScopeError, get_draft, read_revision
from .ui import _context, _require, templates

router = APIRouter(include_in_schema=False)


async def _upload(request: Request, db: Db) -> dict[str, Any]:
    _require(request, db, "project:write")
    limit = min(get_settings().max_upload_bytes, intake.malware_scan.MAX_SCAN_BYTES) + 16384
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise HTTPException(413, "PDF upload exceeds the size limit")
        body.extend(chunk)
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": bytes(body), "more_body": False}

    parsed_request = Request(request.scope, receive=receive)
    async with parsed_request.form(max_files=1, max_fields=1) as form:
        if set(form) != {"csrf_token", "file"} or any(len(form.getlist(k)) != 1 for k in form):
            raise HTTPException(422, "Choose one PDF file")
        token = form.get("csrf_token")
        verify_csrf(request, token if isinstance(token, str) else None)
        file = form["file"]
        if not isinstance(file, UploadFile):
            raise HTTPException(422, "Choose one PDF file")
        return {"filename": file.filename or "", "content": await file.read()}


UploadData = Annotated[dict[str, Any], Depends(_upload)]


def _positive(value: str) -> int:
    if not value.isascii() or not value.isdecimal() or not 1 <= len(value) <= 10:
        raise HTTPException(422, "Choose a positive saved revision or page")
    number = int(value)
    if number < 1:
        raise HTTPException(422, "Choose a positive saved revision or page")
    return number


@router.get("/scopes/{draft_id}/evidence", response_class=HTMLResponse)
def sources_page(request: Request, db: Db, draft_id: str) -> HTMLResponse:
    user = _require(request, db, "project:read")
    try:
        draft = get_draft(db, user, draft_id)
        sources = intake.list_sources(db, user, draft_id)
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from exc
    return templates.TemplateResponse(
        request,
        "draft_pdf_sources.html",
        _context(
            request,
            db,
            draft=draft,
            project=draft.project,
            sources=sources,
            postgres=db.get_bind().dialect.name == "postgresql",
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.post("/scopes/{draft_id}/evidence")
def upload_source(request: Request, db: Db, draft_id: str, data: UploadData) -> RedirectResponse:
    user = _require(request, db, "project:write")
    try:
        source = intake.retain_pdf(
            db, user, draft_id, data["filename"], data["content"], settings=get_settings()
        )
        db.commit()
    except DraftScopeError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.code) from exc
    return RedirectResponse(f"/scopes/{draft_id}/evidence/{source.id}", status_code=303)


@router.get("/scopes/{draft_id}/evidence/{source_id}", response_class=HTMLResponse)
def source_page(
    request: Request, db: Db, draft_id: str, source_id: str, page: int = 1
) -> HTMLResponse:
    user = _require(request, db, "project:read")
    document = None
    problem = None
    try:
        draft = get_draft(db, user, draft_id)
        source = intake.source_info(db, user, draft_id, source_id)
        envelope = read_revision(db, user, draft_id)
        if source["ready"]:
            try:
                document = intake.read_document(
                    db, user, draft_id, source_id, settings=get_settings()
                )
            except DraftScopeError as exc:
                if exc.status_code == 403:
                    raise
                problem = exc.code
        if document and not 1 <= page <= len(document["pages"]):
            raise DraftScopeError("PDF_PAGE_NOT_FOUND", 404)
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from exc
    return templates.TemplateResponse(
        request,
        "draft_pdf_source.html",
        _context(
            request,
            db,
            draft=draft,
            project=draft.project,
            source=source,
            document=document,
            selected_page=document["pages"][page - 1] if document else None,
            document_hash=source["document_sha256"],
            revision=envelope["revision"],
            problem=problem,
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.post("/scopes/{draft_id}/evidence/{source_id}/scan")
def scan_pdf(
    request: Request, db: Db, draft_id: str, source_id: str, form: FormData
) -> RedirectResponse:
    user = _require(request, db, "project:write")
    verify_csrf(request, form.get("csrf_token"))
    if set(form) != {"csrf_token"}:
        raise HTTPException(422, "Invalid scan request")
    try:
        intake.scan_source(db, user, draft_id, source_id, settings=get_settings())
        db.commit()
    except DraftScopeError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.code) from exc
    return RedirectResponse(f"/scopes/{draft_id}/evidence/{source_id}", status_code=303)


@router.get("/scopes/{draft_id}/evidence/{source_id}/pages/{page_number}.png")
def preview_page(
    request: Request, db: Db, draft_id: str, source_id: str, page_number: int
) -> Response:
    user = _require(request, db, "project:read")
    try:
        content = intake.page_preview(
            db, user, draft_id, source_id, page_number, settings=get_settings()
        )
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from exc
    return Response(
        content,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@router.post("/scopes/{draft_id}/evidence/{source_id}/review")
def save_observation(
    request: Request, db: Db, draft_id: str, source_id: str, form: FormData
) -> RedirectResponse:
    user = _require(request, db, "project:write")
    verify_csrf(request, form.get("csrf_token"))
    if (
        set(form)
        != {"csrf_token", "revision", "page", "observation", "state", "document_hash", "reviewed"}
        or form["reviewed"] != "yes"
    ):
        raise HTTPException(422, "Review the page before saving an observation")
    try:
        intake.review_page(
            db,
            user,
            draft_id,
            source_id,
            _positive(form["revision"]),
            _positive(form["page"]),
            form["observation"],
            form["state"],
            form["document_hash"],
            settings=get_settings(),
        )
        db.commit()
    except DraftScopeError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.code) from exc
    return RedirectResponse(f"/scopes/{draft_id}", status_code=303)
