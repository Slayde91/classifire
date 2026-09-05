from __future__ import annotations

import base64
import binascii
import hashlib
import json
from typing import Annotated, Any
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from itsdangerous import BadData, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import DraftScope, User
from .outputs.draft_system_review import sections as system_sections
from .outputs.draft_system_review import summary as system_summary
from .security import verify_csrf
from .services.draft_scope import (
    MAX_ARTIFACT_BYTES,
    DraftScopeError,
    apply_import,
    create_draft_project,
    get_draft,
    list_drafts,
    preview_import,
    read_revision,
    revision_bytes,
    save_revision,
    validate_payload,
)
from .services.draft_scope_evidence import reference_status
from .services.draft_scope_reports import (
    DraftScopeReportError,
    create_report,
    list_reports,
    read_report,
    report_bytes,
    report_freshness,
)
from .services.draft_system_matches import read_match_revision
from .ui import _context, _require, templates

router = APIRouter(include_in_schema=False)
Db = Annotated[Session, Depends(get_db)]
MAX_FORM_BYTES = 300_000
MAX_PAYLOAD_BYTES = 262_144
MAX_IMPORT_FORM_BYTES = 1_200_000
IMPORT_PREVIEW_MAX_AGE = 900


async def _form_values(request: Request, limit: int, *, max_fields: int = 8) -> dict[str, str]:
    if request.headers.get("content-type", "").split(";")[0] != (
        "application/x-www-form-urlencoded"
    ):
        raise HTTPException(415, "Use a standard form submission")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise HTTPException(413, "Draft form exceeds the size limit")
        body.extend(chunk)
    try:
        pairs = parse_qsl(
            body.decode("utf-8"), keep_blank_values=True, errors="strict", max_num_fields=max_fields
        )
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(422, "Invalid draft form") from exc
    values = dict(pairs)
    if len(values) != len(pairs):
        raise HTTPException(422, "Duplicate form fields are not accepted")
    return values


async def _bounded_form(request: Request) -> dict[str, str]:
    return await _form_values(request, MAX_FORM_BYTES)


async def _bounded_import_form(request: Request) -> dict[str, str]:
    return await _form_values(request, MAX_IMPORT_FORM_BYTES)


FormData = Annotated[dict[str, str], Depends(_bounded_form)]
ImportFormData = Annotated[dict[str, str], Depends(_bounded_import_form)]


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
    envelope: dict[str, Any] | None = None,
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
            envelope=envelope or {},
            evidence_links=[
                dict(ref, status=reference_status(ref, payload.get("observations", [])))
                for ref in (envelope or {}).get("evidence_refs", [])
            ],
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
        envelope=envelope,
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


def _import_signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        get_settings().secret_key,
        salt="classifire-draft-scope-import-v1",
        signer_kwargs={"digest_method": hashlib.sha256},
    )


def _import_bytes(form: dict[str, str]) -> bytes:
    encoded = form.get("artifact_b64", "")
    if len(encoded) > 4 * ((MAX_ARTIFACT_BYTES + 2) // 3):
        raise HTTPException(413, "The saved Scope file exceeds the size limit.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(422, "Choose a valid saved Draft Scope JSON file.") from exc
    if not raw:
        raise HTTPException(422, "Choose a saved Draft Scope JSON file.")
    if len(raw) > MAX_ARTIFACT_BYTES:
        raise HTTPException(413, "The saved Scope file exceeds the size limit.")
    return raw


def _import_session(request: Request) -> str:
    return hashlib.sha256(request.session["csrf_token"].encode("utf-8")).hexdigest()


def _import_page(
    request: Request,
    db: Session,
    draft: DraftScope,
    *,
    errors: list[str] | None = None,
    preview: dict[str, Any] | None = None,
    artifact_b64: str = "",
    preview_token: str = "",
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "draft_scope_import.html",
        _context(
            request,
            db,
            draft=draft,
            project=draft.project,
            current_revision=draft.latest_revision,
            errors=errors or [],
            preview=preview,
            artifact_b64=artifact_b64,
            preview_token=preview_token,
        ),
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


def _import_error(exc: DraftScopeError) -> str:
    if exc.code == "DRAFT_REVISION_CONFLICT":
        return "This Draft has changed. Open it and preview the import again before replacing it."
    if exc.code == "DRAFT_PERMISSION_DENIED":
        return "Your account cannot replace this Draft."
    if exc.code == "DRAFT_IMPORT_LINEAGE_LIMIT":
        return (
            "This file has reached the supported limit of 16 import records. "
            "Its history cannot be silently removed to import it again."
        )
    if exc.code == "DRAFT_IMPORT_SOURCE_CHANGED":
        return "The file differs from the preview. Choose it and preview the import again."
    if exc.code == "DRAFT_REVISION_INTEGRITY_FAILED":
        return "The saved Draft failed its integrity check. No changes were saved."
    return (
        "The file could not be imported. It must be a supported, unchanged Draft Scope "
        "download with valid fields, relationships and history. "
        "No changes were saved."
    )


@router.get("/scopes/{draft_id}/import", response_class=HTMLResponse)
def import_scope_page(request: Request, db: Db, draft_id: str) -> HTMLResponse:
    user = _require(request, db, "project:write")
    try:
        draft = get_draft(db, user, draft_id)
        read_revision(db, user, draft_id)
    except DraftScopeError as exc:
        raise _failure(exc) from exc
    return _import_page(request, db, draft)


@router.post("/scopes/{draft_id}/import/preview", response_class=HTMLResponse)
def preview_scope_import(
    request: Request, db: Db, draft_id: str, form: ImportFormData
) -> HTMLResponse:
    verify_csrf(request, form.get("csrf_token"))
    user = _require(request, db, "project:write")
    try:
        draft = get_draft(db, user, draft_id)
    except DraftScopeError as exc:
        raise _failure(exc) from exc
    try:
        raw = _import_bytes(form)
        preview = preview_import(db, user, draft_id, raw)
    except HTTPException as exc:
        return _import_page(
            request, db, draft, errors=[str(exc.detail)], status_code=exc.status_code
        )
    except DraftScopeError as exc:
        return _import_page(
            request, db, draft, errors=[_import_error(exc)], status_code=exc.status_code
        )
    binding = {
        "actor_id": user.id,
        "draft_id": draft.id,
        "revision": preview["expected_revision"],
        "target_hash": preview["current_hash"],
        "source_file_sha256": preview["source_file_sha256"],
        "session": _import_session(request),
    }
    return _import_page(
        request,
        db,
        draft,
        preview=preview,
        artifact_b64=form["artifact_b64"],
        preview_token=_import_signer().dumps(binding),
    )


@router.post("/scopes/{draft_id}/import/confirm", response_model=None)
def confirm_scope_import(
    request: Request, db: Db, draft_id: str, form: ImportFormData
) -> HTMLResponse | RedirectResponse:
    verify_csrf(request, form.get("csrf_token"))
    user = _require(request, db, "project:write")
    try:
        draft = get_draft(db, user, draft_id)
    except DraftScopeError as exc:
        raise _failure(exc) from exc
    try:
        if form.get("confirm") != "replace":
            raise HTTPException(422, "Confirm replacement after reviewing the import preview.")
        raw = _import_bytes(form)
        token = form.get("preview_token", "")
        if not token or len(token) > 2048:
            raise HTTPException(422, "Preview the file again before confirming its import.")
        try:
            binding = _import_signer().loads(token, max_age=IMPORT_PREVIEW_MAX_AGE)
        except BadData as exc:
            raise HTTPException(
                422, "The preview is invalid or expired. Preview the file again."
            ) from exc
        if (
            not isinstance(binding, dict)
            or set(binding)
            != {"actor_id", "draft_id", "revision", "target_hash", "source_file_sha256", "session"}
            or binding["actor_id"] != user.id
            or binding["draft_id"] != draft.id
            or binding["session"] != _import_session(request)
            or binding["source_file_sha256"] != hashlib.sha256(raw).hexdigest()
        ):
            raise HTTPException(
                422, "The file or destination differs from the preview. Preview again."
            )
        current = read_revision(db, user, draft_id)
        if (
            current["revision"] != binding["revision"]
            or current["sha256"] != binding["target_hash"]
        ):
            raise DraftScopeError("DRAFT_REVISION_CONFLICT", 409)
        apply_import(
            db,
            user,
            draft_id,
            binding["revision"],
            raw,
            expected_source_hash=binding["source_file_sha256"],
        )
        db.commit()
    except HTTPException as exc:
        db.rollback()
        return _import_page(
            request, db, draft, errors=[str(exc.detail)], status_code=exc.status_code
        )
    except DraftScopeError as exc:
        db.rollback()
        return _import_page(
            request, db, draft, errors=[_import_error(exc)], status_code=exc.status_code
        )
    return RedirectResponse(f"/scopes/{draft_id}", status_code=303)


@router.get("/scopes/{draft_id}/reports", response_class=HTMLResponse)
def scope_reports_page(
    request: Request, db: Db, draft_id: str, revision: int | None = None
) -> HTMLResponse:
    user = _require(request, db, "project:read")
    try:
        draft = get_draft(db, user, draft_id)
        envelope = read_revision(db, user, draft_id, revision)
        reports = list_reports(db, user, draft_id)
    except (DraftScopeError, DraftScopeReportError) as exc:
        raise HTTPException(exc.status_code, exc.code) from exc
    return templates.TemplateResponse(
        request,
        "draft_scope_reports.html",
        _context(
            request,
            db,
            draft=draft,
            project=draft.project,
            envelope=envelope,
            reports=reports,
            report=None,
            snapshot=None,
            stale=False,
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.post("/scopes/{draft_id}/reports", response_class=RedirectResponse)
def create_scope_report(
    request: Request, db: Db, draft_id: str, form: FormData
) -> RedirectResponse:
    verify_csrf(request, form.get("csrf_token"))
    user = _require(request, db, "project:write")
    raw_revision = form.get("revision", "")
    if not raw_revision.isascii() or not raw_revision.isdigit() or len(raw_revision) > 10:
        raise HTTPException(422, "A valid saved revision is required")
    revision = int(raw_revision)
    if revision < 1:
        raise HTTPException(422, "A valid saved revision is required")
    try:
        report = create_report(db, user, draft_id, revision)
        db.commit()
    except (DraftScopeError, DraftScopeReportError) as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.code) from exc
    return RedirectResponse(f"/scopes/{draft_id}/reports/{report.id}", status_code=303)


@router.get("/scopes/{draft_id}/reports/{report_id}", response_class=HTMLResponse)
def scope_report_page(request: Request, db: Db, draft_id: str, report_id: str) -> HTMLResponse:
    user = _require(request, db, "project:read")
    try:
        draft = get_draft(db, user, draft_id)
        snapshot = read_report(db, user, draft_id, report_id)
        stale = report_freshness(
            db, user, draft_id, report_id, storage_root=get_settings().storage_root
        )
    except (DraftScopeError, DraftScopeReportError) as exc:
        raise HTTPException(exc.status_code, exc.code) from exc
    return templates.TemplateResponse(
        request,
        "draft_scope_reports.html",
        _context(
            request,
            db,
            draft=draft,
            project=snapshot["project"],
            envelope=snapshot["scope"],
            reports=[],
            report=report_id,
            snapshot=snapshot,
            stale=stale,
            system_summary=system_summary(snapshot["system_match"])
            if snapshot.get("system_match")
            else [],
            system_sections=system_sections(snapshot["system_match"])
            if snapshot.get("system_match")
            else [],
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.get("/scopes/{draft_id}/reports/{report_id}/download")
def download_scope_report(
    request: Request, db: Db, draft_id: str, report_id: str, format: str = "pdf"
) -> Response:
    user = _require(request, db, "project:read")
    try:
        snapshot = read_report(db, user, draft_id, report_id)
        content = report_bytes(db, user, draft_id, report_id, format)
        db.commit()
    except (DraftScopeError, DraftScopeReportError) as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.code) from exc
    media_type = (
        "application/pdf"
        if format == "pdf"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    prefix = (
        "CLASSIFIRE-Scope-System-Report"
        if snapshot.get("system_match")
        else "CLASSIFIRE-Scope-Report"
    )
    filename = f"{prefix}-{snapshot['report_id']}.{format}"
    return Response(
        content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/scopes/{draft_id}/system-matches/{match_id}/reports", response_class=HTMLResponse)
def system_reports_page(
    request: Request,
    db: Db,
    draft_id: str,
    match_id: str,
    revision: int | None = None,
) -> HTMLResponse:
    user = _require(request, db, "project:read")
    _require(request, db, "technical:read")
    try:
        draft = get_draft(db, user, draft_id)
        match = read_match_revision(db, user, draft_id, match_id, revision)
        latest = read_match_revision(db, user, draft_id, match_id)
        reports = list_reports(db, user, draft_id)
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from exc
    return templates.TemplateResponse(
        request,
        "draft_scope_reports.html",
        _context(
            request,
            db,
            draft=draft,
            project=draft.project,
            envelope=match["scope"],
            match_envelope=match,
            latest_match_revision=latest["revision"],
            system_sections=system_sections(match),
            system_summary=system_summary(match),
            reports=reports,
            report=None,
            snapshot=None,
            stale=False,
            preview_url=f"/scopes/{draft_id}/system-matches/{match_id}/reports",
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.post("/scopes/{draft_id}/system-matches/{match_id}/reports")
def create_system_report(
    request: Request,
    db: Db,
    draft_id: str,
    match_id: str,
    form: FormData,
) -> RedirectResponse:
    verify_csrf(request, form.get("csrf_token"))
    user = _require(request, db, "project:write")
    _require(request, db, "technical:read")
    if set(form) != {"csrf_token", "match_revision"}:
        raise HTTPException(422, "Select one saved review revision")
    raw = form["match_revision"]
    if not raw.isascii() or not raw.isdigit() or len(raw) > 10 or int(raw) < 1:
        raise HTTPException(422, "A valid saved review revision is required")
    try:
        match = read_match_revision(db, user, draft_id, match_id, int(raw))
        report = create_report(
            db,
            user,
            draft_id,
            match["scope"]["revision"],
            match_id=match_id,
            match_revision=match["revision"],
        )
        db.commit()
    except DraftScopeError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.code) from exc
    return RedirectResponse(f"/scopes/{draft_id}/reports/{report.id}", 303)
