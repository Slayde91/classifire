from __future__ import annotations

import json
from typing import Annotated
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .security import has_permission, verify_csrf
from .services import draft_estimate_reports as estimate_reports
from .services import draft_estimates as estimates
from .services import draft_package_import as imports
from .services import draft_project_packages as packages
from .services import draft_scope as scopes
from .services import draft_scope_reports as scope_reports
from .services import draft_system_matches as matches
from .ui import _context, _require, templates
from .ui_uploads import single_file

router = APIRouter(include_in_schema=False)
Db = Annotated[Session, Depends(get_db)]


def _number(value: str) -> int:
    if not value.isascii() or not value.isdigit() or len(value) > 10:
        raise HTTPException(422, "Choose a valid saved revision")
    return int(value)


def _query(request: Request, latest: int) -> dict:
    query = request.query_params
    allowed = set(packages.Selection.model_fields)
    if set(query) - allowed or any(
        len(query.getlist(k)) > 1 for k in allowed - {"scope_reports", "estimate_reports"}
    ):
        raise HTTPException(422, "Invalid package selection")
    value = {
        "scope_revision": _number(query.get("scope_revision", str(latest))),
        "scope_reports": query.getlist("scope_reports"),
        "estimate_reports": query.getlist("estimate_reports"),
    }
    for kind in ("match", "estimate"):
        identifier = query.get(kind + "_id", "")
        value[kind + "_id"] = identifier or None
        value[kind + "_revision"] = (
            _number(query.get(kind + "_revision", "1")) if identifier else None
        )
    return value


@router.get("/scopes/{draft_id}/packages", response_class=HTMLResponse)
def package_page(request: Request, db: Db, draft_id: str) -> HTMLResponse:
    user = _require(request, db, "project:read")
    try:
        draft = scopes.get_draft(db, user, draft_id)
        chosen = packages.selection(_query(request, draft.latest_revision))
        scope = scopes.read_revision(db, user, draft_id, chosen.scope_revision)
        reviews = (
            matches.list_matches(db, user, draft_id)
            if has_permission(user, "technical:read")
            else []
        )
        costs = (
            estimates.list_estimates(db, user, draft_id)
            if has_permission(user, "estimate:read")
            else []
        )
        scoped_reports = scope_reports.list_reports(db, user, draft_id)
        cost_reports = (
            estimate_reports.list_reports(db, user, draft_id, chosen.estimate_id)
            if chosen.estimate_id
            else []
        )
        error = None
        result = None
        stale = []
        try:
            result = packages.preview(db, user, draft_id, chosen.model_dump())
            stale = packages.staleness(
                db, user, draft_id, result["manifest"], storage_root=get_settings().storage_root
            )
        except scopes.DraftScopeError as exc:
            if exc.status_code == 403:
                raise
            error = exc.code
        return templates.TemplateResponse(
            request=request,
            name="draft_project_packages.html",
            context=_context(
                request,
                db,
                active_nav="draft_scopes",
                draft=draft,
                project=scope_reports._project(db, draft),
                chosen=chosen,
                scope=scope,
                reviews=[r for r in reviews if r.scope_hash == scope["sha256"]],
                costs=[r for r in costs if r.scope_hash == scope["sha256"]],
                scoped_reports=[r for r in scoped_reports if r.scope_hash == scope["sha256"]],
                cost_reports=cost_reports,
                packages=packages.list_packages(db, user, draft_id),
                result=result,
                selection_json=packages.encode(chosen.model_dump()).decode("utf-8"),
                error=error,
                staleness=stale,
                saved=None,
            ),
        )
    except scopes.DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from exc


@router.post("/scopes/{draft_id}/packages")
async def save_package(request: Request, db: Db, draft_id: str) -> RedirectResponse:
    if request.headers.get("content-type", "").split(";")[0] != "application/x-www-form-urlencoded":
        raise HTTPException(415, "Use a standard form")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 8192:
            raise HTTPException(413, "Package selection exceeds limit")
        body.extend(chunk)
    try:
        pairs = parse_qsl(
            body.decode("utf-8"), keep_blank_values=True, errors="strict", max_num_fields=4
        )
        form = dict(pairs)
        if len(form) != len(pairs) or set(form) != {
            "csrf_token",
            "selection",
            "expected_revision",
            "preview_hash",
        }:
            raise ValueError("form")
        verify_csrf(request, form["csrf_token"])
        user = _require(request, db, "project:write")
        row = packages.create_package(
            db,
            user,
            draft_id,
            json.loads(form["selection"]),
            _number(form["expected_revision"]),
            form["preview_hash"],
        )
        db.commit()
    except scopes.DraftScopeError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.code) from exc
    except (ValueError, UnicodeError, RecursionError) as exc:
        db.rollback()
        raise HTTPException(422, "Invalid package form") from exc
    return RedirectResponse(f"/scopes/{draft_id}/packages/{row.id}", status_code=303)


@router.get("/scopes/{draft_id}/packages/{package_id}", response_class=HTMLResponse)
def saved_package(request: Request, db: Db, draft_id: str, package_id: str) -> HTMLResponse:
    user = _require(request, db, "project:read")
    try:
        row, manifest = packages.read_package(db, user, draft_id, package_id)
        stale = packages.staleness(
            db, user, draft_id, manifest, storage_root=get_settings().storage_root
        )
        return templates.TemplateResponse(
            request=request,
            name="draft_project_packages.html",
            context=_context(
                request,
                db,
                active_nav="draft_scopes",
                draft=scopes.get_draft(db, user, draft_id),
                project=manifest["project"],
                result={"manifest": manifest},
                staleness=stale,
                error=None,
                saved=row,
            ),
        )
    except scopes.DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from exc


@router.get("/scopes/{draft_id}/packages/{package_id}/download")
def download_package(request: Request, db: Db, draft_id: str, package_id: str) -> Response:
    user = _require(request, db, "project:read")
    try:
        content = packages.package_bytes(db, user, draft_id, package_id)
        db.commit()
    except scopes.DraftScopeError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.code) from exc
    return Response(
        content,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="CLASSIFIRE-Draft-ProjectPackage-{package_id}.zip"'
            ),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _import_preview_page(
    request: Request,
    db: Db,
    result: dict | None = None,
    error: str | None = None,
    status: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="draft_package_import.html",
        context=_context(
            request,
            db,
            active_nav="draft_scopes",
            result=result,
            error=error,
            max_bytes=min(get_settings().max_upload_bytes, packages.MAX_ARCHIVE),
        ),
        status_code=status,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/package-import", response_class=HTMLResponse)
def package_import_page(request: Request, db: Db) -> HTMLResponse:
    _require(request, db, "project:write")
    return _import_preview_page(request, db)


@router.post("/package-import/preview", response_class=HTMLResponse)
async def preview_package_import(request: Request, db: Db) -> HTMLResponse:
    user = _require(request, db, "project:write")
    try:
        upload = await single_file(
            request, min(get_settings().max_upload_bytes, packages.MAX_ARCHIVE)
        )
        result = imports.preview_import(db, user, upload["content"])
        return _import_preview_page(request, db, result=result)
    except scopes.DraftScopeError as exc:
        if exc.status_code == 403:
            raise HTTPException(
                403, "Your account cannot inspect the included capabilities"
            ) from exc
        return _import_preview_page(
            request,
            db,
            error=(
                "The package could not be validated. Choose an unchanged supported CLASSIFIRE "
                "project ZIP with complete selected artifacts and matching dependencies. "
                "No project was created."
            ),
            status=exc.status_code,
        )
    except HTTPException as exc:
        if exc.status_code == 403:
            raise
        return _import_preview_page(request, db, error=str(exc.detail), status=exc.status_code)
