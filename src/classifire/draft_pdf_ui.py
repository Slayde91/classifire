"""Thin authenticated UI for the shared Draft PDF intake commands."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from itsdangerous import BadData, URLSafeTimedSerializer

from .config import get_settings
from .draft_scope_ui import (
    Db,
    FormData,
    _editor_error,
    _finding_text,
    _import_session,
    _payload,
    _unique_object,
)
from .security import verify_csrf
from .services import draft_pdf_intake as intake
from .services.draft_scope import DraftScopeError, get_draft, read_revision, validate_payload
from .ui import _context, _require, templates
from .ui_uploads import single_file

router = APIRouter(include_in_schema=False)


async def _upload(request: Request, db: Db) -> dict[str, Any]:
    _require(request, db, "project:write")
    limit = min(get_settings().max_upload_bytes, intake.malware_scan.MAX_SCAN_BYTES)
    return await single_file(request, limit)


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
    return _source_response(request, db, draft_id, source_id, page)


def _source_response(
    request: Request,
    db: Db,
    draft_id: str,
    source_id: str,
    page: int,
    *,
    payload: dict[str, Any] | None = None,
    expected_revision: int | None = None,
    targets: list[dict[str, str]] | None = None,
    errors: list[str] | None = None,
    status_code: int = 200,
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
            payload=envelope["content"] if payload is None else payload,
            expected_revision=envelope["revision"]
            if expected_revision is None
            else expected_revision,
            saved=payload is None,
            envelope=envelope,
            errors=errors or [],
            findings=[],
            review_targets=targets or [],
            page_review=True,
            review_url=f"/scopes/{draft_id}/evidence/{source_id}/scope",
        ),
        status_code=status_code,
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


_REVIEW_FORM_FIELDS = {
    "csrf_token",
    "expected_revision",
    "page",
    "document_hash",
    "payload",
    "targets",
}


def _review_signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        get_settings().secret_key,
        salt="classifire-draft-pdf-scope-review-v1",
        signer_kwargs={"digest_method": hashlib.sha256},
    )


def _review_targets(form: dict[str, str]) -> list[dict[str, str]]:
    raw = form.get("targets", "")
    if len(raw.encode("utf-8")) > 16384:
        raise HTTPException(413, "Too many page links")
    try:
        targets = json.loads(raw, object_pairs_hook=_unique_object)
        if type(targets) is not list:
            raise ValueError("targets")
        return targets
    except (ValueError, RecursionError) as exc:
        raise HTTPException(422, "Select the items reviewed against this page") from exc


def _review_error(exc: DraftScopeError) -> str:
    return {
        "PDF_REVIEW_TARGETS_INVALID": (
            "Select at least one existing defect, opening or service for this page."
        ),
        "PDF_REVIEW_REFERENCE_LIMIT": (
            "This Draft has reached its supported limit of 100 page links."
        ),
        "PDF_REVIEW_SOURCE_CHANGED": (
            "The source changed. Inspect the current page and preview again."
        ),
        "PDF_REVIEW_PREVIEW_CHANGED": (
            "The page, scan or submitted graph differs from the preview. Review and preview again."
        ),
    }.get(exc.code, _editor_error(exc.code))


@router.post("/scopes/{draft_id}/evidence/{source_id}/scope/preview", response_class=HTMLResponse)
def preview_page_scope(
    request: Request, db: Db, draft_id: str, source_id: str, form: FormData
) -> HTMLResponse:
    verify_csrf(request, form.get("csrf_token"))
    user = _require(request, db, "project:write")
    if set(form) not in (_REVIEW_FORM_FIELDS, _REVIEW_FORM_FIELDS | {"action"}):
        raise HTTPException(422, "Use the page review form")
    if "action" in form and form["action"] != "edit":
        raise HTTPException(422, "Choose preview or return to editing")
    payload, targets = _payload(form), _review_targets(form)
    revision, page = _positive(form["expected_revision"]), _positive(form["page"])
    try:
        if form.get("action") == "edit":
            validate_payload(payload)
            return _source_response(
                request,
                db,
                draft_id,
                source_id,
                page,
                payload=payload,
                expected_revision=revision,
                targets=targets,
            )
        preview = intake.preview_scope_page(
            db,
            user,
            draft_id,
            source_id,
            revision,
            page,
            payload,
            targets,
            form["document_hash"],
            settings=get_settings(),
        )
    except DraftScopeError as exc:
        db.rollback()
        if exc.status_code in {403, 404}:
            raise HTTPException(exc.status_code, exc.code) from exc
        return _source_response(
            request,
            db,
            draft_id,
            source_id,
            page,
            payload=payload,
            expected_revision=revision,
            targets=targets,
            errors=[_review_error(exc), *[_finding_text(item) for item in exc.findings]],
            status_code=exc.status_code,
        )
    binding = {
        "actor_id": user.id,
        "draft_id": draft_id,
        "source_id": source_id,
        "session": _import_session(request),
        "review_sha256": preview["review_sha256"],
    }
    draft = get_draft(db, user, draft_id)
    return templates.TemplateResponse(
        request,
        "draft_pdf_scope_preview.html",
        _context(
            request,
            db,
            draft=draft,
            project=draft.project,
            source=intake.source_info(db, user, draft_id, source_id),
            preview=preview,
            preview_token=_review_signer().dumps(binding),
            errors=[],
            review_url=f"/scopes/{draft_id}/evidence/{source_id}/scope",
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.post("/scopes/{draft_id}/evidence/{source_id}/scope/confirm", response_model=None)
def confirm_page_scope(
    request: Request, db: Db, draft_id: str, source_id: str, form: FormData
) -> HTMLResponse | RedirectResponse:
    verify_csrf(request, form.get("csrf_token"))
    user = _require(request, db, "project:write")
    if set(form) != _REVIEW_FORM_FIELDS | {"preview_token", "confirm"} or form["confirm"] != "save":
        raise HTTPException(422, "Confirm the reviewed graph before saving")
    payload, targets = _payload(form), _review_targets(form)
    revision, page = _positive(form["expected_revision"]), _positive(form["page"])
    token = form["preview_token"]
    try:
        if not token or len(token) > 2048:
            raise BadData("preview")
        binding = _review_signer().loads(token, max_age=900)
        if (
            type(binding) is not dict
            or set(binding) != {"actor_id", "draft_id", "source_id", "session", "review_sha256"}
            or any(
                binding.get(key) != value
                for key, value in {
                    "actor_id": user.id,
                    "draft_id": draft_id,
                    "source_id": source_id,
                    "session": _import_session(request),
                }.items()
            )
        ):
            raise BadData("binding")
        intake.save_scope_page(
            db,
            user,
            draft_id,
            source_id,
            revision,
            page,
            payload,
            targets,
            form["document_hash"],
            binding["review_sha256"],
            settings=get_settings(),
        )
        db.commit()
    except (BadData, DraftScopeError) as exc:
        db.rollback()
        if isinstance(exc, DraftScopeError) and exc.status_code in {403, 404}:
            raise HTTPException(exc.status_code, exc.code) from exc
        return _source_response(
            request,
            db,
            draft_id,
            source_id,
            page,
            payload=payload,
            expected_revision=revision,
            targets=targets,
            errors=[
                _review_error(exc)
                if isinstance(exc, DraftScopeError)
                else "The preview is invalid or expired. Inspect the page and preview again."
            ],
            status_code=exc.status_code if isinstance(exc, DraftScopeError) else 422,
        )
    return RedirectResponse(f"/scopes/{draft_id}", status_code=303)
