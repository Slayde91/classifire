"""Word evidence upload, explicit scan and source inspection in the shared UI."""

from __future__ import annotations

import hashlib
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from itsdangerous import BadData, URLSafeTimedSerializer

from .config import get_settings
from .draft_pdf_ui import _positive, _upload
from .draft_scope_ui import Db, _form_values, _import_session, _payload
from .draft_scope_xlsx_ui import _error, _structured
from .security import verify_csrf
from .services import draft_scope_docx as word
from .services import draft_scope_docx_review as review_service
from .services.draft_scope import DraftScopeError, get_draft, read_revision
from .ui import _context, _require, templates

router = APIRouter(include_in_schema=False)
UploadData = Annotated[dict[str, Any], Depends(_upload)]


async def _form(request: Request) -> dict[str, str]:
    return await _form_values(request, 1_200_000, max_fields=8)


FormData = Annotated[dict[str, str], Depends(_form)]


_REVIEW_FIELDS = {"csrf_token", "expected_revision", "document_sha256", "payload", "targets"}


def _signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        get_settings().secret_key,
        salt="classifire-draft-docx-scope-review-v1",
        signer_kwargs={"digest_method": hashlib.sha256},
    )


def _source_choices(
    document: dict[str, Any], source_url: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return (
        [{"locator": block["locator"], "label": block["locator"]} for block in document["blocks"]],
        [
            dict(
                picture,
                occurrence_id=picture["id"],
                label=picture["id"],
                anchor_label=picture["locator"],
                preview_url=f"{source_url}/pictures/{picture['id']}",
            )
            for picture in document["pictures"]
        ],
    )


def _page(
    request: Request,
    db: Db,
    draft_id: str,
    source_id: str | None = None,
    *,
    error: str | None = None,
    review: dict[str, Any] | None = None,
    status: int = 200,
) -> HTMLResponse:
    actor = _require(request, db, "project:read")
    source = document = None
    try:
        draft = get_draft(db, actor, draft_id)
        envelope = read_revision(db, actor, draft_id)
        sources = word.intake().list_sources(db, actor, draft_id)
        if source_id is not None:
            source = word.intake().source_info(db, actor, draft_id, source_id)
            if source["ready"]:
                _, document, _ = word.intake()._document(
                    db, actor, draft_id, source_id, get_settings().storage_root
                )
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from exc
    source_url = f"/scopes/{draft_id}/word/{source_id}"
    choices, images = _source_choices(document, source_url) if document else ([], [])
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
            review_url=source_url,
            payload=(review or {}).get("payload", envelope["content"]),
            expected_revision=(review or {}).get("expected_revision", envelope["revision"]),
            document_sha256=(review or {}).get(
                "document_sha256", (source or {}).get("document_sha256", "")
            ),
            review_targets=(review or {}).get("targets", []),
            review_sources=choices,
            sheet_images=images,
            saved=review is None,
            word_review=True,
            envelope=envelope,
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


@router.post("/scopes/{draft_id}/word/{source_id}/preview", response_class=HTMLResponse)
def preview(request: Request, db: Db, draft_id: str, source_id: str, form: FormData):
    verify_csrf(request, form.get("csrf_token"))
    actor = _require(request, db, "project:write")
    if set(form) not in (_REVIEW_FIELDS, _REVIEW_FIELDS | {"action"}):
        raise HTTPException(422, "Use the Word graph review form")
    if "action" in form and form["action"] != "edit":
        raise HTTPException(422, "Choose preview or return to editing")
    targets = _structured(form, "targets", list, 98_304, context="Word")
    payload = _payload(form)
    revision = _positive(form["expected_revision"])
    submitted = {
        "payload": payload,
        "targets": targets,
        "expected_revision": revision,
        "document_sha256": form["document_sha256"],
    }
    try:
        checked = review_service.preview_review(
            db,
            actor,
            draft_id,
            source_id,
            revision,
            payload,
            targets,
            form["document_sha256"],
            settings=get_settings(),
        )
    except DraftScopeError as exc:
        db.rollback()
        if exc.status_code in {403, 404}:
            raise HTTPException(exc.status_code, exc.code) from exc
        return _page(
            request,
            db,
            draft_id,
            source_id,
            review=submitted,
            error=_error(exc),
            status=exc.status_code,
        )
    if form.get("action") == "edit":
        return _page(request, db, draft_id, source_id, review=checked)
    binding = {
        "actor_id": actor.id,
        "draft_id": draft_id,
        "source_id": source_id,
        "session": _import_session(request),
        "review_sha256": checked["review_sha256"],
    }
    source_api = word.intake()
    try:
        draft = get_draft(db, actor, draft_id)
        source = source_api.source_info(db, actor, draft_id, source_id)
        _, document, _ = source_api._document(
            db,
            actor,
            draft_id,
            source_id,
            get_settings().storage_root,
        )
    except DraftScopeError as exc:
        db.rollback()
        if exc.status_code in {403, 404}:
            raise HTTPException(exc.status_code, exc.code) from exc
        return _page(
            request,
            db,
            draft_id,
            source_id,
            review=submitted,
            error=_error(exc),
            status=exc.status_code,
        )
    _choices, images = _source_choices(document, f"/scopes/{draft_id}/word/{source_id}")
    return templates.TemplateResponse(
        request,
        "draft_scope_docx_preview.html",
        _context(
            request,
            db,
            draft=draft,
            project=draft.project,
            source=source,
            preview=checked,
            preview_token=_signer().dumps(binding),
            errors=[],
            sheet_images=images,
            word_review=True,
            review_url=f"/scopes/{draft_id}/word/{source_id}",
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.post("/scopes/{draft_id}/word/{source_id}/confirm", response_model=None)
def confirm(request: Request, db: Db, draft_id: str, source_id: str, form: FormData):
    verify_csrf(request, form.get("csrf_token"))
    actor = _require(request, db, "project:write")
    if set(form) != _REVIEW_FIELDS | {"preview_token", "confirm"} or form["confirm"] != "save":
        raise HTTPException(422, "Confirm the reviewed Word graph before saving")
    payload = _payload(form)
    targets = _structured(form, "targets", list, 98_304, context="Word")
    revision = _positive(form["expected_revision"])
    try:
        token = form["preview_token"]
        if not token or len(token) > 2048:
            raise BadData("preview")
        binding = _signer().loads(token, max_age=900)
        expected = {
            "actor_id": actor.id,
            "draft_id": draft_id,
            "source_id": source_id,
            "session": _import_session(request),
        }
        if type(binding) is not dict or set(binding) != {*expected, "review_sha256"}:
            raise BadData("preview")
        if any(binding.get(key) != value for key, value in expected.items()):
            raise BadData("binding")
        review_service.save_review(
            db,
            actor,
            draft_id,
            source_id,
            revision,
            payload,
            targets,
            form["document_sha256"],
            binding["review_sha256"],
            settings=get_settings(),
        )
        db.commit()
    except (BadData, DraftScopeError) as exc:
        db.rollback()
        if isinstance(exc, DraftScopeError) and exc.status_code in {403, 404}:
            raise HTTPException(exc.status_code, exc.code) from exc
        return _page(
            request,
            db,
            draft_id,
            source_id,
            review={
                "payload": payload,
                "targets": targets,
                "expected_revision": revision,
                "document_sha256": form["document_sha256"],
            },
            error=(
                _error(exc)
                if isinstance(exc, DraftScopeError)
                else "The preview is invalid or expired. Review and preview again."
            ),
            status=exc.status_code if isinstance(exc, DraftScopeError) else 422,
        )
    return RedirectResponse(f"/scopes/{draft_id}", status_code=303)
