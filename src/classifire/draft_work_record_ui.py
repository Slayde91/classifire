"""Native register UI for separately confirmed Draft work assertions."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from itsdangerous import BadData, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .draft_scope_ui import _form_values, _import_session
from .security import verify_csrf
from .services import draft_work_records as work
from .services.draft_scope import DraftScopeError, get_draft, read_revision
from .ui import _context, _require, templates

router = APIRouter(include_in_schema=False)
Db = Annotated[Session, Depends(get_db)]


def _signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        get_settings().secret_key,
        salt="classifire-draft-work-preview-v1",
        signer_kwargs={"digest_method": hashlib.sha256},
    )


def _failure(exc: DraftScopeError) -> HTTPException:
    return HTTPException(exc.status_code, exc.code)


def _page(
    request: Request,
    db: Session,
    draft_id: str,
    *,
    content: dict[str, Any],
    saved: dict[str, Any] | None = None,
    proposed: dict[str, Any] | None = None,
    token: str = "",
) -> HTMLResponse:
    actor = _require(request, db, "project:read")
    draft = get_draft(db, actor, draft_id)
    scope = read_revision(db, actor, draft_id, content["scope_revision"])
    evidence = (
        work.choices(db, actor, draft_id, content, settings=get_settings())
        if content.get("opening_id") or content.get("service_id")
        else None
    )
    return templates.TemplateResponse(
        request,
        "draft_work_records.html",
        _context(
            request,
            db,
            draft=draft,
            project=draft.project,
            scope=scope,
            envelope=None,
            workbench_capability="work",
            workspace_register=request.headers.get("X-Classifire-Workspace") == "register",
            content=content,
            evidence=evidence,
            saved=saved,
            proposed=proposed,
            preview_token=token,
            payload_json=json.dumps(content),
            work_notice=work.NOTICE,
            history=work.history(db, actor, draft_id),
            current_scope_revision=draft.latest_revision,
        ),
        headers={"Cache-Control": "no-store", "Vary": "X-Classifire-Workspace, Cookie"},
    )


@router.get("/scopes/{draft_id}/work-records", response_class=HTMLResponse)
def work_page(
    request: Request,
    db: Db,
    draft_id: str,
    scope_revision: int,
    opening_id: str | None = None,
    service_id: str | None = None,
) -> HTMLResponse:
    try:
        return _page(
            request,
            db,
            draft_id,
            content={
                "record_id": str(uuid4()),
                "expected_revision": 0,
                "scope_revision": scope_revision,
                "opening_id": opening_id or None,
                "service_id": service_id or None,
                "note": "",
                "reported_by": "",
                "reported_role": "unknown",
                "observed_at": "",
                "unknowns": "",
                "evidence_indices": [],
            },
        )
    except DraftScopeError as exc:
        raise _failure(exc) from exc


@router.post("/scopes/{draft_id}/work-records/preview", response_class=HTMLResponse)
async def preview_work(request: Request, db: Db, draft_id: str) -> HTMLResponse:
    form = await _form_values(request, 40000, max_fields=50)
    verify_csrf(request, form.get("csrf_token"))
    actor = _require(request, db, "project:write")
    try:
        content: dict[str, Any] = {
            key: form.get(key, "")
            for key in (
                "record_id",
                "note",
                "reported_by",
                "reported_role",
                "observed_at",
                "unknowns",
            )
        }
        content.update(
            expected_revision=int(form.get("expected_revision", "")),
            scope_revision=int(form.get("scope_revision", "")),
            opening_id=form.get("opening_id") or None,
            service_id=form.get("service_id") or None,
            evidence_indices=[
                int(key.removeprefix("evidence_"))
                for key, value in form.items()
                if key.startswith("evidence_") and value == "include"
            ],
        )
        proposed = work.preview(db, actor, draft_id, content, settings=get_settings())
        binding = {
            "draft_id": draft_id,
            "actor_id": actor.id,
            "session": _import_session(request),
            "sha256": proposed["sha256"],
        }
        return _page(
            request,
            db,
            draft_id,
            content=proposed["content"],
            proposed=proposed,
            token=_signer().dumps(binding),
        )
    except DraftScopeError as exc:
        raise _failure(exc) from exc
    except ValueError as exc:
        raise HTTPException(422, "Check the work record fields and observation timezone.") from exc


@router.post("/scopes/{draft_id}/work-records/confirm", response_class=RedirectResponse)
async def confirm_work(request: Request, db: Db, draft_id: str) -> RedirectResponse:
    form = await _form_values(request, 40000, max_fields=4)
    verify_csrf(request, form.get("csrf_token"))
    actor = _require(request, db, "project:write")
    try:
        if form.get("confirm") != "save" or len(form.get("preview_token", "")) > 2048:
            raise ValueError("confirmation")
        binding = _signer().loads(form.get("preview_token", ""), max_age=900)
        if (
            not isinstance(binding, dict)
            or set(binding) != {"draft_id", "actor_id", "session", "sha256"}
            or binding["draft_id"] != draft_id
            or binding["actor_id"] != actor.id
            or binding["session"] != _import_session(request)
        ):
            raise ValueError("binding")
        value = work.save(
            db,
            actor,
            draft_id,
            json.loads(form.get("payload", "")),
            binding["sha256"],
            settings=get_settings(),
        )
        db.commit()
    except DraftScopeError as exc:
        db.rollback()
        raise _failure(exc) from exc
    except (BadData, ValueError, TypeError) as exc:
        db.rollback()
        raise HTTPException(422, "Preview this exact record again before confirming.") from exc
    return RedirectResponse(
        f"/scopes/{draft_id}/work-records/{value['record_id']}?revision={value['revision']}",
        status_code=303,
    )


@router.get("/scopes/{draft_id}/work-records/{record_id}", response_class=HTMLResponse)
def saved_work(
    request: Request, db: Db, draft_id: str, record_id: str, revision: int, edit: bool = False
) -> HTMLResponse:
    actor = _require(request, db, "project:read")
    try:
        value = work.read(db, actor, draft_id, record_id, revision, settings=get_settings())
        content = dict(value["record"]["content"])
        if edit:
            if revision != value["latest_revision"]:
                raise DraftScopeError("WORK_RECORD_REVISION_CONFLICT", 409)
            content["expected_revision"] = revision
            # Review current Scope explicitly; repeat the evidence selection.
            content["scope_revision"] = get_draft(db, actor, draft_id).latest_revision
            content["evidence_indices"] = []
        return _page(request, db, draft_id, content=content, saved=None if edit else value)
    except DraftScopeError as exc:
        raise _failure(exc) from exc


@router.get("/scopes/{draft_id}/work-records/{record_id}/download")
def download_work(
    request: Request, db: Db, draft_id: str, record_id: str, revision: int
) -> Response:
    actor = _require(request, db, "project:read")
    try:
        raw = work.report_archive(db, actor, draft_id, record_id, revision, settings=get_settings())
    except DraftScopeError as exc:
        raise _failure(exc) from exc
    return Response(
        raw,
        media_type="application/zip",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="draft-work-record-r{revision}.zip"',
        },
    )
