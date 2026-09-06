"""Optional retained PDF suggestions feeding the shared human Draft graph review."""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from itsdangerous import BadData, URLSafeTimedSerializer

from .config import get_settings
from .draft_pdf_ui import _positive, _review_error, _review_targets, _source_response
from .draft_scope_ui import Db, FormData, _finding_text, _import_session, _payload
from .security import verify_csrf
from .services import draft_pdf_intake as intake
from .services import draft_pdf_suggestions as suggestions
from .services.draft_pdf_suggestion_contract import SuggestionPort
from .services.draft_scope import DraftScopeError, get_draft
from .ui import _context, _require, templates

router = APIRouter(include_in_schema=False)
_FIELDS = {"csrf_token", "expected_revision", "payload", "targets"}


def _port(request: Request) -> SuggestionPort | None:
    return getattr(request.app.state, "draft_pdf_suggestion_port", None)


def _url(draft_id: str, source_id: str, suggestion_id: str) -> str:
    return f"/scopes/{draft_id}/evidence/{source_id}/suggestions/{suggestion_id}"


def _signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        get_settings().secret_key,
        salt="classifire-draft-pdf-suggestion-review-v1",
        signer_kwargs={"digest_method": hashlib.sha256},
    )


def _error(exc: DraftScopeError) -> str:
    messages = {
        "PDF_SUGGESTION_REVIEW_REQUIRED": (
            "Link every kept suggestion to the page, or reject that suggested item, "
            "before previewing."
        ),
        "PDF_REVIEW_TARGETS_INVALID": (
            "Keep and review at least one suggested item, or use "
            "Reject this suggestion batch to discard them all."
        ),
        "PDF_SUGGESTION_NOT_PENDING": (
            "This suggestion is closed or its saved Draft has changed. "
            "Return to the current Draft before reviewing again."
        ),
        "PDF_SUGGESTION_INPUT_CHANGED": (
            "The saved Draft or source has changed. Existing entries were not overwritten. "
            "Review the current source and request new suggestions if needed."
        ),
        "PDF_SUGGESTIONS_UNAVAILABLE": (
            "Optional suggestions are unavailable. Continue with manual page review."
        ),
        "PDF_SUGGESTION_FAILED": (
            "The provider could not return valid suggestions. No Draft changes were saved. "
            "Continue with manual page review or retry."
        ),
    }
    if exc.code in messages:
        return messages[exc.code]
    if exc.code == "DRAFT_ARTIFACT_TOO_LARGE":
        return (
            "This Draft is too large. Reject unnecessary suggestions "
            "or source links and preview again."
        )
    if exc.code.startswith("PDF_REVIEW_") or exc.code.startswith("DRAFT_REVISION_"):
        return _review_error(exc)
    return exc.code.replace("_", " ").capitalize() + ". You can continue with manual page review."


def _record(db: Db, actor: Any, draft_id: str, source_id: str, suggestion_id: str):
    value = suggestions.read_suggestion(db, actor, draft_id, suggestion_id, settings=get_settings())
    if value["source_id"] != source_id:
        raise HTTPException(404, "Suggestion not found for this PDF source")
    return value


def _response(
    request: Request,
    db: Db,
    draft_id: str,
    source_id: str,
    suggestion_id: str,
    *,
    payload: dict[str, Any] | None = None,
    targets: list[dict[str, str]] | None = None,
    errors: list[str] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    actor = _require(request, db, "project:read")
    try:
        draft = get_draft(db, actor, draft_id)
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from exc
    try:
        suggestion = _record(db, actor, draft_id, source_id, suggestion_id)
        source = intake.source_info(db, actor, draft_id, source_id)
        document = intake.read_document(db, actor, draft_id, source_id, settings=get_settings())
    except DraftScopeError as exc:
        if exc.status_code in {403, 404}:
            raise HTTPException(exc.status_code, exc.code) from exc
        return templates.TemplateResponse(
            request,
            "draft_pdf_suggestion.html",
            _context(
                request,
                db,
                draft=draft,
                suggestion=None,
                source_id=source_id,
                recovery_payload=payload,
                recovery_targets=targets,
                errors=[*(errors or []), _error(exc)],
                can_edit=False,
            ),
            status_code=exc.status_code,
            headers={"Cache-Control": "no-store"},
        )
    can_edit = suggestion["status"] == "pending" and not suggestion["stale"]
    return templates.TemplateResponse(
        request,
        "draft_pdf_suggestion.html",
        _context(
            request,
            db,
            draft=draft,
            project=draft.project,
            source=source,
            source_id=source_id,
            document=document,
            selected_page=document["pages"][suggestion["page_number"] - 1],
            suggestion=suggestion,
            can_edit=can_edit,
            payload=suggestion["payload"] if payload is None else payload,
            review_targets=[] if targets is None else targets,
            expected_revision=suggestion["expected_revision"],
            saved=False,
            page_review=True,
            suggestion_review=True,
            suggestion_items=suggestion["items"],
            review_url=_url(draft_id, source_id, suggestion_id),
            errors=errors or [],
            findings=[],
            recovery_payload=None,
        ),
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


@router.post("/scopes/{draft_id}/evidence/{source_id}/suggestions", response_model=None)
def generate(request: Request, db: Db, draft_id: str, source_id: str, form: FormData):
    verify_csrf(request, form.get("csrf_token"))
    actor = _require(request, db, "project:write")
    if (
        set(form) != {"csrf_token", "expected_revision", "page", "document_hash", "consent"}
        or form["consent"] != "yes"
    ):
        raise HTTPException(422, "Confirm the selected page and configured suggestion provider")
    revision, page = _positive(form["expected_revision"]), _positive(form["page"])
    try:
        record = suggestions.generate(
            db,
            actor,
            draft_id,
            source_id,
            revision,
            page,
            form["document_hash"],
            settings=get_settings(),
            port=_port(request),
        )
        db.commit()
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
            errors=[_error(exc)],
            status_code=exc.status_code,
        )
    return RedirectResponse(_url(draft_id, source_id, record.id), status_code=303)


@router.get(
    "/scopes/{draft_id}/evidence/{source_id}/suggestions/{suggestion_id}",
    response_class=HTMLResponse,
)
def detail(request: Request, db: Db, draft_id: str, source_id: str, suggestion_id: str):
    return _response(request, db, draft_id, source_id, suggestion_id)


@router.post(
    "/scopes/{draft_id}/evidence/{source_id}/suggestions/{suggestion_id}/preview",
    response_class=HTMLResponse,
)
def preview(
    request: Request, db: Db, draft_id: str, source_id: str, suggestion_id: str, form: FormData
):
    verify_csrf(request, form.get("csrf_token"))
    actor = _require(request, db, "project:write")
    if set(form) not in (_FIELDS, _FIELDS | {"action"}) or (
        "action" in form and form["action"] != "edit"
    ):
        raise HTTPException(422, "Use the suggestion graph review form")
    payload, targets = _payload(form), _review_targets(form)
    revision = _positive(form["expected_revision"])
    try:
        record = _record(db, actor, draft_id, source_id, suggestion_id)
        checked = suggestions.preview_suggestion(
            db,
            actor,
            draft_id,
            suggestion_id,
            revision,
            payload,
            targets,
            settings=get_settings(),
        )
        if form.get("action") == "edit":
            return _response(
                request, db, draft_id, source_id, suggestion_id, payload=payload, targets=targets
            )
        draft = get_draft(db, actor, draft_id)
        source = intake.source_info(db, actor, draft_id, source_id)
    except DraftScopeError as exc:
        db.rollback()
        if exc.status_code in {403, 404}:
            raise HTTPException(exc.status_code, exc.code) from exc
        return _response(
            request,
            db,
            draft_id,
            source_id,
            suggestion_id,
            payload=payload,
            targets=targets,
            errors=[_error(exc), *[_finding_text(item) for item in exc.findings]],
            status_code=exc.status_code,
        )
    binding = {
        "actor_id": actor.id,
        "draft_id": draft_id,
        "source_id": source_id,
        "suggestion_id": suggestion_id,
        "session": _import_session(request),
        "review_sha256": checked["review_sha256"],
    }
    return templates.TemplateResponse(
        request,
        "draft_pdf_suggestion_preview.html",
        _context(
            request,
            db,
            draft=draft,
            project=draft.project,
            source=source,
            suggestion=record,
            preview=checked,
            errors=[],
            suggestion_review=True,
            preview_token=_signer().dumps(binding),
            review_url=_url(draft_id, source_id, suggestion_id),
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.post(
    "/scopes/{draft_id}/evidence/{source_id}/suggestions/{suggestion_id}/confirm",
    response_model=None,
)
def confirm(
    request: Request, db: Db, draft_id: str, source_id: str, suggestion_id: str, form: FormData
):
    verify_csrf(request, form.get("csrf_token"))
    actor = _require(request, db, "project:write")
    if set(form) != _FIELDS | {"preview_token", "confirm"} or form["confirm"] != "save":
        raise HTTPException(422, "Explicitly confirm the complete reviewed Draft")
    payload, targets = _payload(form), _review_targets(form)
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
            "suggestion_id": suggestion_id,
            "session": _import_session(request),
        }
        if (
            type(binding) is not dict
            or set(binding) != {*expected, "review_sha256"}
            or any(binding.get(key) != value for key, value in expected.items())
        ):
            raise BadData("binding")
        _record(db, actor, draft_id, source_id, suggestion_id)
        suggestions.save_suggestion(
            db,
            actor,
            draft_id,
            suggestion_id,
            revision,
            payload,
            targets,
            binding["review_sha256"],
            settings=get_settings(),
        )
        db.commit()
    except (BadData, DraftScopeError) as exc:
        db.rollback()
        if isinstance(exc, DraftScopeError) and exc.status_code in {403, 404}:
            raise HTTPException(exc.status_code, exc.code) from exc
        return _response(
            request,
            db,
            draft_id,
            source_id,
            suggestion_id,
            payload=payload,
            targets=targets,
            errors=[
                _error(exc)
                if isinstance(exc, DraftScopeError)
                else "The preview is invalid or expired. Review and preview again."
            ],
            status_code=exc.status_code if isinstance(exc, DraftScopeError) else 422,
        )
    return RedirectResponse(f"/scopes/{draft_id}", status_code=303)


@router.post(
    "/scopes/{draft_id}/evidence/{source_id}/suggestions/{suggestion_id}/reject",
    response_model=None,
)
def reject(
    request: Request, db: Db, draft_id: str, source_id: str, suggestion_id: str, form: FormData
):
    verify_csrf(request, form.get("csrf_token"))
    actor = _require(request, db, "project:write")
    if set(form) != {"csrf_token", "confirm"} or form["confirm"] != "reject":
        raise HTTPException(422, "Confirm rejection of this suggestion batch")
    try:
        _record(db, actor, draft_id, source_id, suggestion_id)
        suggestions.reject_suggestion(db, actor, draft_id, suggestion_id, settings=get_settings())
        db.commit()
    except DraftScopeError as exc:
        db.rollback()
        if exc.status_code in {403, 404}:
            raise HTTPException(exc.status_code, exc.code) from exc
        return _response(
            request,
            db,
            draft_id,
            source_id,
            suggestion_id,
            errors=[_error(exc)],
            status_code=exc.status_code,
        )
    return RedirectResponse(_url(draft_id, source_id, suggestion_id), status_code=303)
