from __future__ import annotations

import json
from typing import Annotated, Any, Literal
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User
from .outputs.draft_estimate import complete_coverage
from .outputs.draft_system_review import sections as system_sections
from .outputs.draft_system_review import summary as system_summary
from .security import has_permission, verify_csrf
from .services import draft_estimate_reports as estimate_reports
from .services.draft_estimates import (
    add_line,
    create_estimate,
    estimate_staleness,
    list_estimates,
    override_line,
    read_estimate_revision,
    revision_bytes,
    set_line_status,
)
from .services.draft_scope import DraftScopeError, get_draft, read_revision
from .services.draft_system_matches import list_matches
from .ui import _context, _require, templates

router = APIRouter(include_in_schema=False)
Db = Annotated[Session, Depends(get_db)]
MAX_FORM_BYTES = 64 * 1024


async def _bounded_form(request: Request) -> dict[str, str]:
    if request.headers.get("content-type", "").split(";")[0] != (
        "application/x-www-form-urlencoded"
    ):
        raise HTTPException(415, "Use a standard form submission")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_FORM_BYTES:
            raise HTTPException(413, "Estimate form exceeds the size limit")
        body.extend(chunk)
    try:
        pairs = parse_qsl(
            body.decode("utf-8"), keep_blank_values=True, errors="strict", max_num_fields=12
        )
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(422, "Invalid estimate form") from exc
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
    _require(request, db, "estimate:write" if write else "estimate:read")
    return user


def _targets(scope: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"kind": "service", "id": item["id"], "label": item["label"],
         "quantity": item["quantity"], "unit": item["unit"],
         "opening_ids": item["opening_ids"]}
        for item in scope["content"]["services"]
    ] + [
        {"kind": "blank_opening", "id": item["id"], "label": item["label"],
         "quantity": None, "unit": "each", "opening_ids": [item["id"]]}
        for item in scope["content"]["openings"] if item["blank"]
    ]


def _picker(
    request: Request, db: Session, user: User, draft_id: str,
    scope_revision: int | None = None, *, errors: list[str] | None = None,
    form_values: dict[str, str] | None = None, status_code: int = 200,
) -> HTMLResponse:
    draft = get_draft(db, user, draft_id)
    scope = read_revision(db, user, draft_id, scope_revision)
    estimates = list_estimates(db, user, draft_id)
    matches = (
        [item for item in list_matches(db, user, draft_id) if item.scope_hash == scope["sha256"]]
        if has_permission(user, "technical:read") else []
    )
    return templates.TemplateResponse(
        request, "draft_estimate.html",
        _context(
            request, db, draft=draft, project=draft.project, scope=scope,
            scope_revision=scope["revision"], envelope=None, estimates=estimates,
            matches=matches, base_url=f"/scopes/{draft.id}/estimates", estimate_url="",
            errors=errors or [], form_values=form_values or {},
        ),
        status_code=status_code, headers={"Cache-Control": "no-store"},
    )


def _detail(
    request: Request, db: Session, user: User, draft_id: str, estimate_id: str,
    revision: int | None = None, *, target: str | None = None,
    errors: list[str] | None = None, form_values: dict[str, str] | None = None,
    error_line_id: str | None = None, status_code: int = 200,
) -> HTMLResponse:
    draft = get_draft(db, user, draft_id)
    envelope = read_estimate_revision(db, user, draft_id, estimate_id, revision)
    latest = read_estimate_revision(db, user, draft_id, estimate_id)
    staleness = estimate_staleness(
        db, user, draft_id, estimate_id, envelope["revision"],
        storage_root=get_settings().storage_root,
    )
    all_targets = _targets(envelope["scope"])
    selected_target = next(
        (item for item in all_targets if f"{item['kind']}:{item['id']}" == target), None
    )
    if target and selected_target is None:
        raise HTTPException(422, "Choose a service or blank opening from this saved Scope")
    used = {(line["target_kind"], line["target_id"]) for line in envelope["lines"]}
    available_targets = [item for item in all_targets if (item["kind"], item["id"]) not in used]
    base_url = f"/scopes/{draft.id}/estimates"
    return templates.TemplateResponse(
        request, "draft_estimate.html",
        _context(
            request, db, draft=draft, project=draft.project, scope=envelope["scope"],
            envelope=envelope, latest_revision=latest["revision"], staleness=staleness,
            base_url=base_url, estimate_url=f"{base_url}/{envelope['artifact_id']}",
            available_targets=available_targets, selected_target=selected_target,
            errors=errors or [], form_values=form_values or {}, error_line_id=error_line_id,
            can_edit=(has_permission(user, "project:write")
                      and has_permission(user, "estimate:write")
                      and envelope["revision"] == latest["revision"]),
        ),
        status_code=status_code, headers={"Cache-Control": "no-store"},
    )


def _message(code: str) -> str:
    return {
        "ESTIMATE_REVISION_CONFLICT": (
            "A newer estimate revision exists. Your attempted changes remain below. "
            "Open the latest revision in another tab and compare before reapplying them."
        ),
        "ESTIMATE_SAVE_CONFLICT": "The estimate changed during this save. Reopen and compare.",
        "ESTIMATE_TARGET_ALREADY_REPRESENTED": (
            "This Scope target already has a line. Edit or restore that existing line "
            "instead of pricing the same work twice."
        ),
        "ESTIMATE_LINE_INVALID": (
            "Check the line fields, unit and reason. Unknown values stay blank; each "
            "quantities must be whole numbers. Explain any changed Scope quantity."
        ),
        "ESTIMATE_OVERRIDE_INVALID": (
            "Check the quantity, rate and reason for change. Use nonnegative numbers "
            "with at most six decimal places, or leave unknown values blank."
        ),
        "ESTIMATE_STATUS_INVALID": "A valid line status and a reason are required.",
        "ESTIMATE_MATCH_SCOPE_MISMATCH": "The selected review must use this exact saved Scope.",
        "ESTIMATE_MATCH_INVALID": (
            "Choose both a review and its saved revision, or leave both blank."
        ),
    }.get(code, code)


@router.get("/scopes/{draft_id}/estimates", response_class=HTMLResponse)
def estimates_picker(
    request: Request, db: Db, draft_id: str, scope_revision: int | None = None,
) -> HTMLResponse:
    user = _actor(request, db)
    try:
        return _picker(request, db, user, draft_id, scope_revision)
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from exc


@router.post("/scopes/{draft_id}/estimates", response_model=None)
def start_estimate(
    request: Request, db: Db, draft_id: str, form: FormData,
) -> HTMLResponse | RedirectResponse:
    verify_csrf(request, form.get("csrf_token"))
    user = _actor(request, db, write=True)
    if set(form) != {"csrf_token", "scope_revision", "match_id", "match_revision"}:
        raise HTTPException(422, "Choose a saved Scope and optional exact review")
    scope_revision = _revision(form["scope_revision"])
    match_revision = _revision(form["match_revision"]) if form["match_revision"] else None
    try:
        estimate = create_estimate(
            db, user, draft_id, scope_revision,
            match_id=form["match_id"] or None, match_revision=match_revision,
        )
        db.commit()
    except DraftScopeError as exc:
        db.rollback()
        if exc.status_code not in {409, 422}:
            raise HTTPException(exc.status_code, exc.code) from exc
        try:
            return _picker(
                request, db, user, draft_id, scope_revision,
                errors=[_message(exc.code)], form_values=form, status_code=exc.status_code,
            )
        except DraftScopeError as render_exc:
            raise HTTPException(render_exc.status_code, render_exc.code) from render_exc
    return RedirectResponse(f"/scopes/{draft_id}/estimates/{estimate.id}", status_code=303)


@router.get("/scopes/{draft_id}/estimates/{estimate_id}", response_class=HTMLResponse)
def estimate_page(
    request: Request, db: Db, draft_id: str, estimate_id: str,
    revision: int | None = None, target: str | None = None,
) -> HTMLResponse:
    user = _actor(request, db)
    try:
        return _detail(request, db, user, draft_id, estimate_id, revision, target=target)
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from exc


def _refused_line(
    request: Request, db: Session, user: User, draft_id: str, estimate_id: str,
    expected_revision: int, form: dict[str, str], line_id: str, exc: DraftScopeError,
) -> HTMLResponse:
    db.rollback()
    if exc.status_code not in {409, 422}:
        raise HTTPException(exc.status_code, exc.code) from exc
    target = (
        f"{form.get('target_kind', '')}:{form.get('target_id', '')}" if line_id == "add" else None
    )
    try:
        return _detail(
            request, db, user, draft_id, estimate_id, expected_revision, target=target,
            errors=[_message(exc.code)], form_values=form, error_line_id=line_id,
            status_code=exc.status_code,
        )
    except DraftScopeError as render_exc:
        raise HTTPException(render_exc.status_code, render_exc.code) from render_exc


@router.post("/scopes/{draft_id}/estimates/{estimate_id}/lines", response_model=None)
def add_estimate_line(
    request: Request, db: Db, draft_id: str, estimate_id: str, form: FormData,
) -> HTMLResponse | RedirectResponse:
    verify_csrf(request, form.get("csrf_token"))
    user = _actor(request, db, write=True)
    if set(form) != {
        "csrf_token", "expected_revision", "target_kind", "target_id", "unit", "quantity",
        "unit_sell_rate", "description", "source_note", "reason",
    }:
        raise HTTPException(422, "Unexpected line fields")
    expected = _revision(form["expected_revision"])
    payload: dict[str, Any] = {
        key: value for key, value in form.items() if key not in {"csrf_token", "expected_revision"}
    }
    for key in ("quantity", "unit_sell_rate"):
        payload[key] = form[key] if form[key] else None
    try:
        add_line(db, user, draft_id, estimate_id, expected, payload)
        db.commit()
    except DraftScopeError as exc:
        return _refused_line(request, db, user, draft_id, estimate_id, expected, form, "add", exc)
    return RedirectResponse(f"/scopes/{draft_id}/estimates/{estimate_id}", status_code=303)


@router.post("/scopes/{draft_id}/estimates/{estimate_id}/lines/{line_id}", response_model=None)
def change_estimate_line(
    request: Request, db: Db, draft_id: str, estimate_id: str, line_id: str, form: FormData,
) -> HTMLResponse | RedirectResponse:
    verify_csrf(request, form.get("csrf_token"))
    user = _actor(request, db, write=True)
    action = form.get("action", "")
    fields = {"csrf_token", "expected_revision", "action", "reason"}
    if action == "update":
        fields.update(("quantity", "unit_sell_rate"))
    if action not in {"update", "omit", "restore"} or set(form) != fields:
        raise HTTPException(422, "Choose a supported line action and its fields")
    expected = _revision(form["expected_revision"])
    try:
        if action == "update":
            override_line(db, user, draft_id, estimate_id, expected, line_id, {
                "quantity": form["quantity"] or None,
                "unit_sell_rate": form["unit_sell_rate"] or None, "reason": form["reason"],
            })
        else:
            set_line_status(
                db, user, draft_id, estimate_id, expected, line_id,
                "omitted" if action == "omit" else "active", form["reason"],
            )
        db.commit()
    except DraftScopeError as exc:
        return _refused_line(
            request, db, user, draft_id, estimate_id, expected, form, line_id, exc
        )
    return RedirectResponse(f"/scopes/{draft_id}/estimates/{estimate_id}", status_code=303)


@router.get("/scopes/{draft_id}/estimates/{estimate_id}/download")
def download_estimate(
    request: Request, db: Db, draft_id: str, estimate_id: str, revision: int | None = None,
) -> Response:
    user = _actor(request, db)
    _require(request, db, "estimate:export")
    try:
        envelope = read_estimate_revision(db, user, draft_id, estimate_id, revision)
        content = revision_bytes(db, user, draft_id, estimate_id, envelope["revision"])
        db.commit()
    except DraftScopeError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.code) from exc
    filename = f"CLASSIFIRE-Draft-Estimate-{envelope['artifact_id']}-r{envelope['revision']}.json"
    return Response(content, media_type="application/json", headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })


@router.get("/scopes/{draft_id}/estimates/{estimate_id}/reports", response_class=HTMLResponse)
def estimate_reports_page(
    request: Request,
    db: Db,
    draft_id: str,
    estimate_id: str,
    revision: int | None = None,
    profile: Literal["estimate-only", "complete"] = "estimate-only",
) -> HTMLResponse:
    user = _actor(request, db)
    try:
        draft = get_draft(db, user, draft_id)
        envelope = read_estimate_revision(db, user, draft_id, estimate_id, revision)
        reports = estimate_reports.list_reports(db, user, draft_id, estimate_id)
        stale = estimate_staleness(
            db,
            user,
            draft_id,
            estimate_id,
            envelope["revision"],
            storage_root=get_settings().storage_root,
        )
        latest = read_estimate_revision(db, user, draft_id, estimate_id)
        if latest["sha256"] != envelope["sha256"]:
            stale.append("REPORT_ESTIMATE_CHANGED")
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from exc
    return templates.TemplateResponse(
        request,
        "draft_estimate_reports.html",
        _context(
            request,
            db,
            draft=draft,
            project=draft.project,
            envelope=envelope,
            scope=envelope["scope"],
            reports=reports,
            report_profiles={
                item.id: json.loads(item.snapshot_json)["profile"] for item in reports
            },
            report_profile=profile,
            complete_coverage=complete_coverage(envelope) if profile == "complete" else [],
            system_summary=system_summary(envelope["system_match"])
            if profile == "complete" and envelope["system_match"]
            else [],
            system_sections=system_sections(envelope["system_match"])
            if profile == "complete" and envelope["system_match"]
            else [],
            snapshot=None,
            report_id=None,
            estimate_url=f"/scopes/{draft_id}/estimates/{estimate_id}",
            staleness=stale,
            can_edit=False,
            error_line_id=None,
            form_values={},
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.post("/scopes/{draft_id}/estimates/{estimate_id}/reports", response_class=RedirectResponse)
def create_estimate_report(
    request: Request,
    db: Db,
    draft_id: str,
    estimate_id: str,
    form: FormData,
) -> RedirectResponse:
    verify_csrf(request, form.get("csrf_token"))
    user = _actor(request, db, write=True)
    if set(form) not in ({"csrf_token", "revision"}, {"csrf_token", "revision", "profile"}):
        raise HTTPException(422, "Choose one saved estimate revision")
    revision = _revision(form["revision"])
    try:
        report = estimate_reports.create_report(
            db, user, draft_id, estimate_id, revision, profile=form.get("profile", "estimate-only")
        )
        db.commit()
    except DraftScopeError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.code) from exc
    return RedirectResponse(
        f"/scopes/{draft_id}/estimates/{estimate_id}/reports/{report.id}",
        status_code=303,
    )


@router.get(
    "/scopes/{draft_id}/estimates/{estimate_id}/reports/{report_id}", response_class=HTMLResponse
)
def estimate_report_page(
    request: Request,
    db: Db,
    draft_id: str,
    estimate_id: str,
    report_id: str,
) -> HTMLResponse:
    user = _actor(request, db)
    try:
        draft = get_draft(db, user, draft_id)
        snapshot = estimate_reports.read_report(db, user, draft_id, estimate_id, report_id)
        stale = estimate_reports.report_staleness(
            db,
            user,
            draft_id,
            estimate_id,
            report_id,
            storage_root=get_settings().storage_root,
        )
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from exc
    envelope = snapshot["estimate"]
    return templates.TemplateResponse(
        request,
        "draft_estimate_reports.html",
        _context(
            request,
            db,
            draft=draft,
            project=snapshot["project"],
            envelope=envelope,
            scope=envelope["scope"],
            reports=[],
            report_profiles={},
            report_profile=snapshot["profile"],
            complete_coverage=complete_coverage(envelope)
            if snapshot["profile"] == "complete"
            else [],
            system_summary=system_summary(envelope["system_match"])
            if snapshot["profile"] == "complete" and envelope["system_match"]
            else [],
            system_sections=system_sections(envelope["system_match"])
            if snapshot["profile"] == "complete" and envelope["system_match"]
            else [],
            snapshot=snapshot,
            report_id=report_id,
            estimate_url=f"/scopes/{draft_id}/estimates/{estimate_id}",
            staleness=stale,
            can_edit=False,
            error_line_id=None,
            form_values={},
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.get("/scopes/{draft_id}/estimates/{estimate_id}/reports/{report_id}/download")
def download_estimate_report(
    request: Request,
    db: Db,
    draft_id: str,
    estimate_id: str,
    report_id: str,
    format: str = "pdf",
) -> Response:
    user = _actor(request, db)
    _require(request, db, "estimate:export")
    try:
        snapshot = estimate_reports.read_report(db, user, draft_id, estimate_id, report_id)
        content = estimate_reports.report_bytes(db, user, draft_id, estimate_id, report_id, format)
        db.commit()
    except DraftScopeError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.code) from exc
    media_type = (
        "application/pdf"
        if format == "pdf"
        else ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    )
    label = "Complete" if snapshot["profile"] == "complete" else "Estimate"
    filename = f"CLASSIFIRE-Draft-{label}-Report-{snapshot['report_id']}.{format}"
    return Response(
        content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
