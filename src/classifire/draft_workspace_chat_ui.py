"""Authenticated native chat and explicit proposal retention; separate Scope confirmation."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .config import get_settings
from .draft_scope_ui import Db, _form_values
from .security import verify_csrf
from .services import draft_workspace_chat as chat
from .services.draft_pdf_suggestion_transport import _json
from .services.draft_scope import DraftScopeError, get_draft
from .ui import _require, _user

router = APIRouter(include_in_schema=False)


@router.get("/scopes/{draft_id}/assistant")
def status(draft_id: str, request: Request, db: Db) -> JSONResponse:
    actor = _require(request, db, "project:read")
    try:
        get_draft(db, actor, draft_id)
        return JSONResponse(
            chat.availability(get_settings()), headers={"Cache-Control": "no-store"}
        )
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from None


@router.post("/scopes/{draft_id}/assistant/{action}")
async def interact(draft_id: str, action: str, request: Request, db: Db) -> JSONResponse:
    actor = _require(request, db, "project:read")
    verify_csrf(request, request.headers.get("X-CSRF-Token"))
    if action not in {"context", "message"}:
        raise HTTPException(404, "Not found")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > chat.MAX_BODY_BYTES:
            raise HTTPException(413, "CHAT_INPUT_TOO_LARGE")
        raw.extend(chunk)
    try:
        data = chat.parse(_json(bytes(raw)))
        if action == "context":
            # Evidence readers can wait on source locks; keep dependency cleanup and
            # other requests running while that synchronous work waits.
            value = await run_in_threadpool(chat.selected_context, db, actor, draft_id, data)
        else:
            value = await run_in_threadpool(
                chat.answer,
                db,
                actor,
                draft_id,
                data,
                settings=get_settings(),
                port=getattr(request.app.state, "workspace_chat_port", None),
            )
        return JSONResponse(value, headers={"Cache-Control": "no-store"})
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from None
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise HTTPException(422, "CHAT_INPUT_INVALID") from None


@router.get("/workspace/assistant")
def workspace_status(request: Request, db: Db) -> JSONResponse:
    if _user(request, db) is None:
        raise HTTPException(401, "Authentication required")
    return JSONResponse(chat.availability(get_settings()), headers={"Cache-Control": "no-store"})


@router.post("/workspace/assistant/{action}")
async def workspace_interact(action: str, request: Request, db: Db) -> JSONResponse:
    actor = _user(request, db)
    if actor is None:
        raise HTTPException(401, "Authentication required")
    verify_csrf(request, request.headers.get("X-CSRF-Token"))
    if action not in {"context", "message"}:
        raise HTTPException(404, "Not found")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > chat.MAX_WORKSPACE_BODY_BYTES:
            raise HTTPException(413, "CHAT_INPUT_TOO_LARGE")
        raw.extend(chunk)
    try:
        data = chat.parse_workspace(_json(bytes(raw)))
        if action == "context":
            value = await run_in_threadpool(
                chat.workspace_context, db, actor, data, settings=get_settings()
            )
        else:
            value = await run_in_threadpool(
                chat.workspace_answer,
                db,
                actor,
                data,
                settings=get_settings(),
                port=getattr(request.app.state, "workspace_chat_port", None),
            )
        return JSONResponse(value, headers={"Cache-Control": "no-store"})
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from None
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise HTTPException(422, "CHAT_INPUT_INVALID") from None


async def _proposal_form(request: Request) -> dict[str, str]:
    return await _form_values(request, 4_194_304, max_fields=3)


ProposalForm = Annotated[dict[str, str], Depends(_proposal_form)]


@router.get("/scopes/{draft_id}/native-proposals")
def proposal_list(request: Request, db: Db, draft_id: str) -> JSONResponse:
    from .services.draft_workspace_proposals import list_saved

    actor = _require(request, db, "project:read")
    try:
        return JSONResponse(
            {"proposals": list_saved(db, actor, draft_id)}, headers={"Cache-Control": "no-store"}
        )
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from None


@router.post("/scopes/{draft_id}/native-proposals")
def proposal_save(request: Request, db: Db, draft_id: str, form: ProposalForm) -> JSONResponse:
    from .services.draft_workspace_proposals import retain

    actor = _require(request, db, "project:write")
    verify_csrf(request, form.get("csrf_token"))
    if set(form) != {"csrf_token", "document", "authorization"}:
        raise HTTPException(422, "CHAT_PROPOSAL_INVALID")
    try:
        document: Any = _json(form["document"].encode())
        row = retain(db, actor, draft_id, document, form["authorization"], settings=get_settings())
        identity, digest = row.id, row.proposal_sha256
        db.commit()
        return JSONResponse(
            {"id": identity, "sha256": digest}, headers={"Cache-Control": "no-store"}
        )
    except DraftScopeError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.code) from None
    except (ValueError, TypeError, UnicodeError, RecursionError):
        db.rollback()
        raise HTTPException(422, "CHAT_PROPOSAL_INVALID") from None


@router.get("/scopes/{draft_id}/native-proposals/{proposal_id}")
def proposal_open(request: Request, db: Db, draft_id: str, proposal_id: str) -> JSONResponse:
    from .services.draft_workspace_proposals import reopen

    actor = _require(request, db, "project:read")
    try:
        return JSONResponse(
            reopen(db, actor, draft_id, proposal_id, settings=get_settings()),
            headers={"Cache-Control": "no-store"},
        )
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from None
