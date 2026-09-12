"""Authenticated browser-only advisory chat; no Draft mutation endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .config import get_settings
from .draft_scope_ui import Db
from .security import verify_csrf
from .services import draft_workspace_chat as chat
from .services.draft_pdf_suggestion_transport import _json
from .services.draft_scope import DraftScopeError, get_draft
from .ui import _require

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
            value = chat.selected_context(db, actor, draft_id, data)
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
