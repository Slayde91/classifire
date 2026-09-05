from __future__ import annotations

import json
from typing import Annotated, Any
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from .db import get_db
from .models import DraftScope, User
from .security import verify_csrf
from .services.draft_scope import (
    DraftScopeError,
    create_draft_project,
    get_draft,
    list_drafts,
    read_revision,
    revision_bytes,
    save_revision,
    validate_payload,
)
from .ui import _context, _require, templates

router = APIRouter(include_in_schema=False)
Db = Annotated[Session, Depends(get_db)]
MAX_FORM_BYTES = 300_000
MAX_PAYLOAD_BYTES = 262_144


async def _bounded_form(request: Request) -> dict[str, str]:
    if request.headers.get("content-type", "").split(";")[0] != (
        "application/x-www-form-urlencoded"
    ):
        raise HTTPException(415, "Use a standard form submission")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_FORM_BYTES:
            raise HTTPException(413, "Draft form exceeds the size limit")
        body.extend(chunk)
    try:
        pairs = parse_qsl(
            body.decode("utf-8"), keep_blank_values=True, errors="strict", max_num_fields=8
        )
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(422, "Invalid draft form") from exc
    values = dict(pairs)
    if len(values) != len(pairs):
        raise HTTPException(422, "Duplicate form fields are not accepted")
    return values


FormData = Annotated[dict[str, str], Depends(_bounded_form)]


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _payload(form: dict[str, str]) -> dict[str, Any]:
    raw = form.get("payload", "")
    if len(raw.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise HTTPException(413, "Draft exceeds the size limit")
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object)
    except (ValueError, RecursionError) as exc:
        raise HTTPException(422, "Invalid Draft Scope JSON") from exc
    if not isinstance(value, dict):
        raise HTTPException(422, "A Draft Scope object is required")
    return value


def _failure(exc: DraftScopeError) -> HTTPException:
    return HTTPException(exc.status_code, exc.code)


def _editor_error(code: str) -> str:
    return {
        "DRAFT_REVISION_CONFLICT": (
            "A newer revision was saved. Your edits remain below. Open the current draft "
            "in another tab to compare before reapplying your changes."
        ),
        "DRAFT_INVALID_REFERENCE": (
            "A linked defect or opening is missing. Review the relationships."
        ),
        "DRAFT_BLANK_OPENING_HAS_SERVICE": (
            "A blank opening cannot contain services. "
            "Remove its service links or change its status."
        ),
        "DRAFT_PAYLOAD_INVALID": "Some fields are invalid. Check the findings below.",
        "DRAFT_DUPLICATE_ID": "Each scope item must have a different identity.",
        "DRAFT_DUPLICATE_LINK": "A service cannot link to the same opening more than once.",
    }.get(code, code)


def _finding_text(finding: dict[str, str]) -> str:
    path = finding.get("path", "")
    parts = [
        str(int(part) + 1)
        if len(part) <= 3 and part.isascii() and part.isdigit()
        else part.replace("_", " ")
        for part in path.split(".")
        if part
    ]
    location = " / ".join(parts)
    return f"{location}: {finding['message']}" if location else finding["message"]


def _editor(
    request: Request,
    db: Session,
    draft: DraftScope,
    payload: dict[str, Any],
    expected_revision: int,
    *,
    saved: bool,
    errors: list[str] | None = None,
    findings: list[str] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "draft_scope.html",
        _context(
            request,
            db,
            draft=draft,
            project=draft.project,
            payload=payload,
            expected_revision=expected_revision,
            saved=saved,
            errors=errors or [],
            findings=findings or [],
        ),
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/scopes", response_class=HTMLResponse)
def scopes_page(request: Request, db: Db) -> HTMLResponse:
    user = _require(request, db, "project:read")
    try:
        drafts = list_drafts(db, user)
    except DraftScopeError as exc:
        raise _failure(exc) from exc
    return templates.TemplateResponse(
        request,
        "draft_scopes.html",
        _context(
            request,
            db,
            drafts=[
                {
                    "id": draft.id,
                    "reference": draft.project.reference,
                    "name": draft.project.name,
                    "latest_revision": draft.latest_revision,
                }
                for draft in drafts
            ],
            errors=[],
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.post("/scopes", response_model=None)
def create_scope(
    request: Request,
    db: Db,
    form: FormData,
) -> HTMLResponse | RedirectResponse:
    verify_csrf(request, form.get("csrf_token"))
    user = _require(request, db, "project:write")
    try:
        draft = create_draft_project(db, user, form.get("reference", ""), form.get("name", ""))
        db.commit()
    except DraftScopeError as exc:
        db.rollback()
        if exc.status_code not in {409, 422}:
            raise _failure(exc) from exc
        message = (
            "That project reference is already in use. Choose another reference."
            if exc.status_code == 409
            else "Check the project reference and name."
        )
        drafts = list_drafts(db, user)
        return templates.TemplateResponse(
            request,
            "draft_scopes.html",
            _context(
                request,
                db,
                errors=[message],
                reference=form.get("reference", "")[:100],
                name=form.get("name", "")[:300],
                drafts=[
                    {
                        "id": item.id,
                        "reference": item.project.reference,
                        "name": item.project.name,
                        "latest_revision": item.latest_revision,
                    }
                    for item in drafts
                ],
            ),
            status_code=exc.status_code,
            headers={"Cache-Control": "no-store"},
        )
    return RedirectResponse(f"/scopes/{draft.id}", status_code=303)


@router.get("/scopes/{draft_id}", response_class=HTMLResponse)
def edit_scope(request: Request, db: Db, draft_id: str) -> HTMLResponse:
    user = _require(request, db, "project:read")
    try:
        draft = get_draft(db, user, draft_id)
        envelope = read_revision(db, user, draft_id)
        _model, warnings = validate_payload(envelope["content"])
    except DraftScopeError as exc:
        raise _failure(exc) from exc
    return _editor(
        request,
        db,
        draft,
        envelope["content"],
        envelope["revision"],
        saved=True,
        findings=[_finding_text(item) for item in warnings],
    )


@router.post("/scopes/{draft_id}", response_model=None)
def update_scope(
    request: Request,
    db: Db,
    draft_id: str,
    form: FormData,
) -> HTMLResponse | RedirectResponse:
    verify_csrf(request, form.get("csrf_token"))
    user: User = _require(request, db, "project:write")
    try:
        draft = get_draft(db, user, draft_id)
    except DraftScopeError as exc:
        raise _failure(exc) from exc
    payload = _payload(form)
    try:
        expected_revision = int(form.get("expected_revision", ""))
        if expected_revision < 1:
            raise ValueError("Invalid revision")
    except ValueError as exc:
        raise HTTPException(422, "A valid saved revision is required") from exc
    action = form.get("action", "")
    if action not in {"save", "validate"}:
        raise HTTPException(422, "Choose Validate or Save")
    try:
        _model, warnings = validate_payload(payload)
        if action == "save":
            save_revision(db, user, draft_id, expected_revision, payload)
            db.commit()
            return RedirectResponse(f"/scopes/{draft_id}", status_code=303)
    except DraftScopeError as exc:
        db.rollback()
        return _editor(
            request,
            db,
            draft,
            payload,
            expected_revision,
            saved=False,
            errors=[_editor_error(exc.code), *[_finding_text(item) for item in exc.findings]],
            status_code=exc.status_code,
        )
    return _editor(
        request,
        db,
        draft,
        payload,
        expected_revision,
        saved=False,
        findings=[_finding_text(item) for item in warnings],
    )


@router.get("/scopes/{draft_id}/download")
def download_scope(
    request: Request,
    db: Db,
    draft_id: str,
    revision: int | None = None,
) -> Response:
    user = _require(request, db, "project:read")
    try:
        draft = get_draft(db, user, draft_id)
        envelope = read_revision(db, user, draft_id, revision)
        content = revision_bytes(db, user, draft_id, envelope["revision"])
    except DraftScopeError as exc:
        raise _failure(exc) from exc
    db.commit()
    return Response(
        content,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="CLASSIFIRE-Scope-{draft.id}-r{envelope["revision"]}.json"'
            ),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
