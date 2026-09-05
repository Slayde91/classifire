from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User
from .security import verify_csrf
from .services.draft_scope import DraftScopeError, get_draft, read_revision
from .services.draft_system_matches import (
    DraftSystemMatchError,
    create_match,
    list_matches,
    list_technical_releases,
    match_staleness,
    read_match_revision,
    revision_bytes,
    save_review,
)
from .ui import _context, _require, templates

router = APIRouter(include_in_schema=False)
Db = Annotated[Session, Depends(get_db)]
MAX_FORM_BYTES = 384 * 1024


async def _bounded_form(request: Request) -> dict[str, str]:
    if request.headers.get("content-type", "").split(";")[0] != (
        "application/x-www-form-urlencoded"
    ):
        raise HTTPException(415, "Use a standard form submission")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_FORM_BYTES:
            raise HTTPException(413, "Candidate review form exceeds the size limit")
        body.extend(chunk)
    try:
        pairs = parse_qsl(
            body.decode("utf-8"), keep_blank_values=True, errors="strict", max_num_fields=44
        )
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(422, "Invalid candidate review form") from exc
    values = dict(pairs)
    if len(values) != len(pairs):
        raise HTTPException(422, "Duplicate form fields are not accepted")
    return values


FormData = Annotated[dict[str, str], Depends(_bounded_form)]


def _revision(raw: str) -> int:
    if not raw.isascii() or not raw.isdigit() or len(raw) > 10 or int(raw) < 1:
        raise HTTPException(422, "A valid saved revision is required")
    return int(raw)


def _actor(request: Request, db: Session, *, write: bool = False) -> User:
    user = _require(request, db, "project:write" if write else "project:read")
    _require(request, db, "technical:read")
    return user


def _picker(
    request: Request, db: Session, user: User, draft_id: str,
    scope_revision: int | None = None, *, errors: list[str] | None = None,
    form_values: dict[str, str] | None = None, status_code: int = 200,
) -> HTMLResponse:
    draft = get_draft(db, user, draft_id)
    scope = read_revision(db, user, draft_id, scope_revision)
    matches = list_matches(db, user, draft_id)
    releases = list_technical_releases(db, user)
    return templates.TemplateResponse(
        request, "draft_system_match.html",
        _context(
            request, db, draft=draft, project=draft.project, scope=scope,
            scope_revision=scope["revision"], envelope=None,
            releases=releases, matches=matches, base_url=f"/scopes/{draft.id}/system-matches",
            match_url="", errors=errors or [], form_values=form_values or {},
        ),
        status_code=status_code, headers={"Cache-Control": "no-store"},
    )


def _detail(
    request: Request, db: Session, user: User, draft_id: str, match_id: str,
    revision: int | None = None, *, errors: list[str] | None = None,
    form_values: dict[str, str] | None = None, status_code: int = 200,
) -> HTMLResponse:
    draft = get_draft(db, user, draft_id)
    envelope = read_match_revision(db, user, draft_id, match_id, revision)
    latest = read_match_revision(db, user, draft_id, match_id)
    staleness = match_staleness(
        db, user, draft_id, match_id, envelope["revision"],
        storage_root=get_settings().storage_root,
    )
    base_url = f"/scopes/{draft.id}/system-matches"
    return templates.TemplateResponse(
        request, "draft_system_match.html",
        _context(
            request, db, draft=draft, project=draft.project, scope=envelope["scope"],
            envelope=envelope, staleness=staleness, base_url=base_url,
            match_url=f"{base_url}/{envelope['artifact_id']}",
            latest_revision=latest["revision"], errors=errors or [],
            form_values=form_values or {},
        ),
        status_code=status_code, headers={"Cache-Control": "no-store"},
    )


@router.get("/scopes/{draft_id}/system-matches", response_class=HTMLResponse)
def candidate_picker(
    request: Request, db: Db, draft_id: str, scope_revision: int | None = None,
) -> HTMLResponse:
    user = _actor(request, db)
    try:
        return _picker(request, db, user, draft_id, scope_revision)
    except (DraftScopeError, DraftSystemMatchError) as exc:
        raise HTTPException(exc.status_code, exc.code) from exc


@router.post("/scopes/{draft_id}/system-matches", response_model=None)
def find_candidates(
    request: Request, db: Db, draft_id: str, form: FormData,
) -> HTMLResponse | RedirectResponse:
    verify_csrf(request, form.get("csrf_token"))
    user = _actor(request, db, write=True)
    if set(form) != {"csrf_token", "scope_revision", "release_id", "opening_id", "service_id"}:
        raise HTTPException(422, "Choose a saved Scope, release and explicit target")
    scope_revision = _revision(form["scope_revision"])
    try:
        match = create_match(
            db, user, draft_id, scope_revision, form["release_id"],
            form["opening_id"] or None, form["service_id"] or None,
            storage_root=get_settings().storage_root,
        )
        db.commit()
    except (DraftScopeError, DraftSystemMatchError) as exc:
        db.rollback()
        if exc.status_code not in {409, 422}:
            raise HTTPException(exc.status_code, exc.code) from exc
        try:
            return _picker(
                request, db, user, draft_id, scope_revision,
                errors=["No review was created. " + exc.code],
                form_values=form, status_code=exc.status_code,
            )
        except (DraftScopeError, DraftSystemMatchError) as render_exc:
            raise HTTPException(render_exc.status_code, render_exc.code) from render_exc
    return RedirectResponse(f"/scopes/{draft_id}/system-matches/{match.id}", status_code=303)


@router.get("/scopes/{draft_id}/system-matches/{match_id}", response_class=HTMLResponse)
def candidate_review(
    request: Request, db: Db, draft_id: str, match_id: str, revision: int | None = None,
) -> HTMLResponse:
    user = _actor(request, db)
    try:
        return _detail(request, db, user, draft_id, match_id, revision)
    except (DraftScopeError, DraftSystemMatchError) as exc:
        raise HTTPException(exc.status_code, exc.code) from exc


@router.post("/scopes/{draft_id}/system-matches/{match_id}/review", response_model=None)
def save_candidate_review(
    request: Request, db: Db, draft_id: str, match_id: str, form: FormData,
) -> HTMLResponse | RedirectResponse:
    verify_csrf(request, form.get("csrf_token"))
    user = _actor(request, db, write=True)
    expected_revision = _revision(form.get("expected_revision", ""))
    try:
        envelope = read_match_revision(db, user, draft_id, match_id, expected_revision)
        expected_fields = {"csrf_token", "expected_revision"}
        decisions: list[dict[str, Any]] = []
        for candidate in envelope["candidates"]:
            candidate_id = candidate["candidate_id"]
            decision_key, notes_key = f"candidate_{candidate_id}", f"notes_{candidate_id}"
            expected_fields.update((decision_key, notes_key))
            decisions.append({
                "candidate_id": candidate_id, "decision": form.get(decision_key, ""),
                "notes": form.get(notes_key, ""),
            })
        if set(form) != expected_fields:
            raise HTTPException(422, "Review each saved candidate; unexpected fields are refused")
        save_review(db, user, draft_id, match_id, expected_revision, decisions)
        db.commit()
    except (DraftScopeError, DraftSystemMatchError) as exc:
        db.rollback()
        if exc.status_code not in {409, 422}:
            raise HTTPException(exc.status_code, exc.code) from exc
        message = (
            "A newer review revision exists. Your notes remain below. Open the latest review "
            "in another tab and compare before reapplying your changes."
            if exc.status_code == 409 else "No changes were saved. " + exc.code
        )
        try:
            return _detail(
                request, db, user, draft_id, match_id, expected_revision,
                errors=[message], form_values=form, status_code=exc.status_code,
            )
        except (DraftScopeError, DraftSystemMatchError) as render_exc:
            raise HTTPException(render_exc.status_code, render_exc.code) from render_exc
    return RedirectResponse(f"/scopes/{draft_id}/system-matches/{match_id}", status_code=303)


@router.get("/scopes/{draft_id}/system-matches/{match_id}/download")
def download_candidate_review(
    request: Request, db: Db, draft_id: str, match_id: str, revision: int | None = None,
) -> Response:
    user = _actor(request, db)
    try:
        envelope = read_match_revision(db, user, draft_id, match_id, revision)
        content = revision_bytes(db, user, draft_id, match_id, envelope["revision"])
        db.commit()
    except (DraftScopeError, DraftSystemMatchError) as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.code) from exc
    filename = (
        f"CLASSIFIRE-System-Candidates-{envelope['artifact_id']}-r{envelope['revision']}.json"
    )
    return Response(content, media_type="application/json", headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })
