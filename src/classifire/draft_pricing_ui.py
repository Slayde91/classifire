"""Thin Draft pricing workbook preview and explicit rate-selection interface."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from openpyxl.utils.cell import get_column_letter  # type: ignore[import-untyped]

from .config import get_settings
from .draft_estimate_ui import Db, _actor, _revision
from .draft_pdf_ui import _upload
from .draft_scope_ui import _form_values
from .security import verify_csrf
from .services import draft_pricing_intake as pricing
from .services.draft_estimates import read_estimate_revision
from .services.draft_pricing_contract import FIELDS
from .services.draft_scope import DraftScopeError, get_draft
from .ui import _context, _require, templates

router = APIRouter(include_in_schema=False)
UploadData = Annotated[dict[str, Any], Depends(_upload)]


async def _pricing_form(request: Request) -> dict[str, str]:
    return await _form_values(request, 64 * 1024, max_fields=20)


FormData = Annotated[dict[str, str], Depends(_pricing_form)]


def _user(request: Request, db: Db, *, write: bool = False):
    user = _actor(request, db, write=write)
    _require(request, db, "library:read")
    return user


def _form_mapping(form: dict[str, str]) -> dict[str, int | None]:
    try:
        return {key: _revision(form[key]) if form[key] else None for key in FIELDS}
    except KeyError as exc:
        raise HTTPException(422, "Map the pricing fields explicitly") from exc


def _page(
    request: Request,
    db: Db,
    user: Any,
    draft_id: str,
    estimate_id: str,
    source_id: str | None = None,
    *,
    form: dict[str, str] | None = None,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    draft = get_draft(db, user, draft_id)
    envelope = read_estimate_revision(db, user, draft_id, estimate_id)
    source = None
    document = None
    rows: list[dict[str, Any]] = []
    values = form or {}
    source_api = pricing.intake()
    if source_id is not None:
        source = source_api.source_info(db, user, draft_id, source_id)
        if source["ready"]:
            try:
                _, document, _ = source_api._document(
                    db, user, draft_id, source_id, get_settings().storage_root
                )
                if form is not None:
                    _, rows = pricing.preview(
                        db,
                        user,
                        draft_id,
                        source_id,
                        _revision(form["sheet_index"]),
                        _revision(form["header_row"]),
                        _form_mapping(form),
                        settings=get_settings(),
                    )
            except DraftScopeError as exc:
                error = exc.code
                status_code = exc.status_code
    grids = []
    if document:
        for sheet in document["sheets"]:
            cells = {(cell["row"], cell["column"]): cell for cell in sheet["cells"]}
            grids.append(
                {
                    "name": sheet["name"],
                    "index": sheet["index"],
                    "rows": [
                        {
                            "number": number,
                            "cells": [
                                cells.get((number, col)) for col in range(1, sheet["columns"] + 1)
                            ],
                        }
                        for number in range(1, min(sheet["rows"], 12) + 1)
                    ],
                    "columns": [get_column_letter(col) for col in range(1, sheet["columns"] + 1)],
                }
            )
    base_url = f"/scopes/{draft_id}/estimates/{estimate_id}"
    return templates.TemplateResponse(
        request,
        "draft_pricing.html",
        _context(
            request,
            db,
            draft=draft,
            project=draft.project,
            envelope=envelope,
            estimate_url=base_url,
            pricing_url=base_url + "/pricing",
            source=source,
            sources=source_api.list_sources(db, user, draft_id),
            document=document,
            rows=rows,
            fields=FIELDS,
            grids=grids,
            columns=[(col, get_column_letter(col)) for col in range(1, 51)],
            form_values=values,
            error=error,
            postgres=db.get_bind().dialect.name == "postgresql",
        ),
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/scopes/{draft_id}/estimates/{estimate_id}/pricing", response_class=HTMLResponse)
def pricing_page(request: Request, db: Db, draft_id: str, estimate_id: str) -> HTMLResponse:
    user = _user(request, db)
    try:
        return _page(request, db, user, draft_id, estimate_id)
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from exc


@router.post("/scopes/{draft_id}/estimates/{estimate_id}/pricing/upload")
def upload_pricing(
    request: Request, db: Db, draft_id: str, estimate_id: str, data: UploadData
) -> RedirectResponse:
    user = _user(request, db, write=True)
    try:
        read_estimate_revision(db, user, draft_id, estimate_id)
        source = pricing.intake().retain(
            db, user, draft_id, data["filename"], data["content"], settings=get_settings()
        )
        db.commit()
    except DraftScopeError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.code) from exc
    return RedirectResponse(f"/scopes/{draft_id}/estimates/{estimate_id}/pricing/{source.id}", 303)


@router.get(
    "/scopes/{draft_id}/estimates/{estimate_id}/pricing/{source_id}", response_class=HTMLResponse
)
def pricing_source(
    request: Request, db: Db, draft_id: str, estimate_id: str, source_id: str
) -> HTMLResponse:
    user = _user(request, db)
    try:
        return _page(request, db, user, draft_id, estimate_id, source_id)
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from exc


@router.post("/scopes/{draft_id}/estimates/{estimate_id}/pricing/{source_id}/scan")
def scan_pricing(
    request: Request, db: Db, draft_id: str, estimate_id: str, source_id: str, form: FormData
) -> RedirectResponse:
    verify_csrf(request, form.get("csrf_token"))
    user = _user(request, db, write=True)
    if set(form) != {"csrf_token"}:
        raise HTTPException(422, "Submit one explicit scan request")
    try:
        read_estimate_revision(db, user, draft_id, estimate_id)
        pricing.intake().scan_source(db, user, draft_id, source_id, settings=get_settings())
        db.commit()
    except DraftScopeError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.code) from exc
    return RedirectResponse(f"/scopes/{draft_id}/estimates/{estimate_id}/pricing/{source_id}", 303)


@router.post(
    "/scopes/{draft_id}/estimates/{estimate_id}/pricing/{source_id}/preview",
    response_class=HTMLResponse,
)
def preview_pricing(
    request: Request, db: Db, draft_id: str, estimate_id: str, source_id: str, form: FormData
) -> HTMLResponse:
    verify_csrf(request, form.get("csrf_token"))
    user = _user(request, db)
    if set(form) != {"csrf_token", "sheet_index", "header_row", *FIELDS}:
        raise HTTPException(422, "Map only the supported pricing fields")
    try:
        return _page(request, db, user, draft_id, estimate_id, source_id, form=form)
    except DraftScopeError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.code) from exc


@router.post(
    "/scopes/{draft_id}/estimates/{estimate_id}/pricing/{source_id}/apply", response_model=None
)
def apply_pricing(
    request: Request, db: Db, draft_id: str, estimate_id: str, source_id: str, form: FormData
) -> HTMLResponse | RedirectResponse:
    verify_csrf(request, form.get("csrf_token"))
    user = _user(request, db, write=True)
    if set(form) != {
        "csrf_token",
        "sheet_index",
        "header_row",
        *FIELDS,
        "line_id",
        "expected_revision",
        "row_number",
        "document_sha256",
        "row_sha256",
        "recovery_note",
    }:
        raise HTTPException(422, "Select one previewed row and explain its recovery scope")
    try:
        pricing.apply_rate(
            db,
            user,
            draft_id,
            estimate_id,
            _revision(form["expected_revision"]),
            form["line_id"],
            source_id,
            _revision(form["sheet_index"]),
            _revision(form["header_row"]),
            _form_mapping(form),
            _revision(form["row_number"]),
            form["document_sha256"],
            form["row_sha256"],
            form["recovery_note"],
            settings=get_settings(),
        )
        db.commit()
    except DraftScopeError as exc:
        db.rollback()
        if exc.status_code not in {409, 422}:
            raise HTTPException(exc.status_code, exc.code) from exc
        return _page(
            request,
            db,
            user,
            draft_id,
            estimate_id,
            source_id,
            form=form,
            error="No rate was applied. " + exc.code,
            status_code=exc.status_code,
        )
    return RedirectResponse(f"/scopes/{draft_id}/estimates/{estimate_id}", 303)
