from __future__ import annotations

import base64
import binascii
import hashlib
import json
from typing import Annotated, Any
from urllib.parse import parse_qsl, urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from itsdangerous import BadData, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import DraftPackageImport, DraftScope, User
from .outputs.draft_system_review import sections as system_sections
from .outputs.draft_system_review import summary as system_summary
from .security import has_permission, verify_csrf
from .services.draft_register import register_context
from .services.draft_scope import (
    MAX_ARTIFACT_BYTES,
    DraftScopeError,
    apply_import,
    create_draft_project,
    get_draft,
    preview_import,
    read_revision,
    revision_bytes,
    save_revision,
    validate_payload,
)
from .services.draft_scope_evidence import reference_label, reference_status
from .services.draft_scope_reports import (
    DraftScopeReportError,
    create_report,
    list_reports,
    preview_report,
    read_report,
    report_bytes,
    report_freshness,
    report_matches,
)
from .services.draft_system_matches import list_matches, match_staleness, read_match_revision
from .ui import _context, _project_workspace, _require, templates

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


def _register_query(request: Request) -> str:
    pairs = [
        (key, value)
        for key in ("match", "estimate")
        for value in request.query_params.getlist(key)
        if value
    ]
    return "?" + urlencode(pairs) if pairs else ""


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
    actor = _require(request, db, "project:read")
    get_draft(db, actor, draft.id)
    register_selection_valid = True
    try:
        register = register_context(
            db,
            actor,
            draft.id,
            expected_revision,
            storage_root=get_settings().storage_root,
            match_selections=[value for value in request.query_params.getlist("match") if value],
            estimate_selection=request.query_params.get("estimate", ""),
        )
    except DraftScopeError as exc:
        if saved and exc.status_code == 403:
            raise _failure(exc) from exc
        register_selection_valid = False
        register = {
            "targets": {},
            "warnings": ["Saved system or pricing context is unavailable: " + exc.code],
            "match_choices": [],
            "estimate_choices": [],
            "evidence_refs": [],
        }
    return templates.TemplateResponse(
        request,
        "draft_scope.html",
        _context(
            request,
            db,
            draft=draft,
            project=draft.project,
            payload=payload,
            register=register,
            register_selection_query=_register_query(request),
            register_report_url=None
            if not register_selection_valid
            else (
                f"/scopes/{draft.id}/system-matches/"
                + register["match_selections"][0].rsplit(":", 1)[0]
                + "/reports?revision="
                + register["match_selections"][0].rsplit(":", 1)[1]
                if len(register.get("match_selections", [])) == 1
                else f"/scopes/{draft.id}/reports?"
                + urlencode(
                    [("revision", str(expected_revision))]
                    + [("matches", value) for value in register.get("match_selections", [])]
                )
            ),
            register_package_query=None
            if not register_selection_valid
            else urlencode(
                [("scope_revision", str(expected_revision))]
                + (
                    [
                        ("match_id", register["match_selections"][0].rsplit(":", 1)[0]),
                        ("match_revision", register["match_selections"][0].rsplit(":", 1)[1]),
                    ]
                    if len(register.get("match_selections", [])) == 1
                    else [("matches", value) for value in register.get("match_selections", [])]
                )
                + (
                    [
                        ("estimate_id", register["estimate_selection"].rsplit(":", 1)[0]),
                        ("estimate_revision", register["estimate_selection"].rsplit(":", 1)[1]),
                    ]
                    if register.get("estimate_selection")
                    else []
                )
            ),
            expected_revision=expected_revision,
            saved=saved,
            envelope=envelope or {},
            package_imported=db.scalar(
                select(DraftPackageImport.id).where(DraftPackageImport.draft_scope_id == draft.id)
            )
            is not None,
            evidence_links=[
                dict(
                    ref,
                    status=reference_status(ref, payload),
                    target_label=reference_label(ref, payload),
                )
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
    return _project_workspace(request, db)


@router.post("/scopes", response_model=None)
def create_scope(
    request: Request,
    db: Db,
    form: FormData,
) -> HTMLResponse | RedirectResponse:
    verify_csrf(request, form.get("csrf_token"))
    user = _require(request, db, "project:write")
    if form.get("next", "") not in {"", "evidence", "workbooks", "word"}:
        raise HTTPException(422, "Choose manual entry, PDF, Excel or Word upload")
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
        return _project_workspace(
            request,
            db,
            errors=[message],
            reference=form.get("reference", "")[:100],
            name=form.get("name", "")[:300],
            status_code=exc.status_code,
        )
    destination = f"/scopes/{draft.id}"
    if form.get("next") in {"evidence", "workbooks", "word"}:
        destination += "/" + form["next"]
    return RedirectResponse(destination, status_code=303)


@router.get("/scopes/{draft_id}", response_class=HTMLResponse)
def edit_scope(
    request: Request, db: Db, draft_id: str, revision: int | None = None
) -> HTMLResponse:
    user = _require(request, db, "project:read")
    try:
        draft = get_draft(db, user, draft_id)
        envelope = read_revision(db, user, draft_id, revision)
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
            return RedirectResponse(
                f"/scopes/{draft_id}" + _register_query(request), status_code=303
            )
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


def _report_selection(
    pairs: list[tuple[str, str]], *, form: bool = False
) -> tuple[int | None, list[dict[str, Any]]]:
    allowed = {"revision", "matches"} | ({"csrf_token"} if form else set())
    if len(pairs) > 32 or any(key not in allowed for key, _ in pairs):
        raise HTTPException(422, "Select a saved Scope revision and explicit system reviews")
    for key in allowed - {"matches"}:
        if sum(name == key for name, _ in pairs) > 1:
            raise HTTPException(422, "Duplicate report selection field")
    values = dict(pairs)
    raw = values.get("revision")
    revision = None
    if raw is not None:
        if not raw.isascii() or not raw.isdigit() or len(raw) > 10 or int(raw) < 1:
            raise HTTPException(422, "A valid saved revision is required")
        revision = int(raw)
    selected = []
    for key, value in pairs:
        if key != "matches":
            continue
        identity, separator, version = value.rpartition(":")
        try:
            if (
                not separator
                or str(UUID(identity)) != identity
                or not version.isascii()
                or not version.isdigit()
                or len(version) > 10
                or version.startswith("0")
                or int(version) < 1
            ):
                raise ValueError("review")
        except ValueError as exc:
            raise HTTPException(422, "Choose an exact saved review ID and revision") from exc
        selected.append({"match_id": identity, "match_revision": int(version)})
    if len({item["match_id"] for item in selected}) != len(selected):
        raise HTTPException(422, "Choose only one revision of each system review")
    if (form or selected) and revision is None:
        raise HTTPException(422, "A valid saved revision is required")
    return revision, selected


async def _report_form(request: Request) -> list[tuple[str, str]]:
    if request.headers.get("content-type", "").split(";")[0] != "application/x-www-form-urlencoded":
        raise HTTPException(415, "Use a standard form submission")
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > 8192:
            raise HTTPException(413, "Report selection exceeds the size limit")
        content.extend(chunk)
    try:
        return parse_qsl(
            content.decode("utf-8"), keep_blank_values=True, errors="strict", max_num_fields=32
        )
    except (UnicodeError, ValueError) as exc:
        raise HTTPException(422, "Invalid report selection form") from exc


def _report_review_sections(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"review": item, "summary": system_summary(item), "sections": system_sections(item)}
        for item in reviews
    ]


def _report_review_choices(
    db: Session, actor: User, draft_id: str, scope: dict[str, Any], selected: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    selected_ids = {item["artifact_id"] for item in selected}
    choices = list(selected)
    if has_permission(actor, "technical:read"):
        for row in list_matches(db, actor, draft_id):
            if row.id not in selected_ids and row.scope_hash == scope["sha256"]:
                try:
                    choices.append(
                        read_match_revision(db, actor, draft_id, row.id, row.latest_revision)
                    )
                except DraftScopeError:
                    continue
    result = []
    for review in choices:
        target = review["target"]
        content = review["scope"]["content"]
        opening = next(
            (item for item in content["openings"] if item["id"] == target["opening_id"]), None
        )
        service = next(
            (item for item in content["services"] if item["id"] == target["service_id"]), None
        )
        compatible = opening is not None and (service is not None or target["blank_opening"])
        result.append(
            {
                "id": review["artifact_id"],
                "revision": review["revision"],
                "value": f"{review['artifact_id']}:{review['revision']}",
                "label": " / ".join(
                    [
                        opening["label"] if opening else "Opening not selected",
                        service["label"]
                        if service
                        else "Blank opening"
                        if target["blank_opening"]
                        else "Whole opening",
                    ]
                ),
                "selected": review["artifact_id"] in selected_ids,
                "compatible": compatible,
            }
        )
    return result


@router.get("/scopes/{draft_id}/reports", response_class=HTMLResponse)
def scope_reports_page(request: Request, db: Db, draft_id: str) -> HTMLResponse:
    user = _require(request, db, "project:read")
    revision, selected = _report_selection(list(request.query_params.multi_items()))
    try:
        draft = get_draft(db, user, draft_id)
        envelope = read_revision(db, user, draft_id, revision)
        preview = preview_report(db, user, draft_id, envelope["revision"], matches=selected)
        reviews = preview["system_matches"]
        stale = any(
            read_match_revision(db, user, draft_id, item["artifact_id"])["sha256"] != item["sha256"]
            or bool(
                match_staleness(
                    db,
                    user,
                    draft_id,
                    item["artifact_id"],
                    item["revision"],
                    storage_root=get_settings().storage_root,
                )
            )
            for item in reviews
        )
        choices = _report_review_choices(db, user, draft_id, envelope, reviews)
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
            stale=stale,
            collection_mode=bool(selected),
            report_review_choices=choices,
            selected_review_refs=[f"{item['artifact_id']}:{item['revision']}" for item in reviews],
            system_reviews=_report_review_sections(reviews),
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.post("/scopes/{draft_id}/reports", response_class=RedirectResponse)
async def create_scope_report(request: Request, db: Db, draft_id: str) -> RedirectResponse:
    pairs = await _report_form(request)
    verify_csrf(request, dict(pairs).get("csrf_token"))
    user = _require(request, db, "project:write")
    revision, selected = _report_selection(pairs, form=True)
    if revision is None:
        raise HTTPException(422, "A valid saved revision is required")
    try:
        report = create_report(db, user, draft_id, revision, matches=selected)
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
            collection_mode=bool(snapshot.get("system_matches")),
            system_reviews=_report_review_sections(report_matches(snapshot)),
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
        "CLASSIFIRE-Scope-System-Report" if report_matches(snapshot) else "CLASSIFIRE-Scope-Report"
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
        stale = latest["sha256"] != match["sha256"] or bool(
            match_staleness(
                db,
                user,
                draft_id,
                match_id,
                match["revision"],
                storage_root=get_settings().storage_root,
            )
        )
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
            stale=stale,
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
