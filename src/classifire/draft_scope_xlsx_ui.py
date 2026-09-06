"""Bounded worksheet mapping and explicit source-linked Draft Scope review UI."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from itsdangerous import BadData, URLSafeTimedSerializer

from .config import get_settings
from .draft_pdf_ui import _positive, _upload
from .draft_scope_ui import (
    Db,
    _editor_error,
    _finding_text,
    _form_values,
    _import_session,
    _payload,
    _unique_object,
)
from .security import verify_csrf
from .services import draft_scope_xlsx as xlsx
from .services.draft_scope import DraftScopeError, get_draft, read_revision
from .ui import _context, _require, templates

router = APIRouter(include_in_schema=False)
UploadData = Annotated[dict[str, Any], Depends(_upload)]
_MAPPING_FIELDS = (
    ("defect_label", "Defect label"),
    ("defect_description", "Defect description"),
    ("location", "Location / source notes"),
    ("opening_label", "Opening label"),
    ("plane", "Plane"),
    ("substrate", "Substrate"),
    ("width_mm", "Width (millimetres)"),
    ("height_mm", "Height (millimetres)"),
    ("service_label", "Service label"),
    ("service_type", "Service type"),
    ("quantity", "Service quantity"),
    ("unit", "Quantity unit"),
)
_MAP_FIELDS = {"csrf_token", "expected_revision", "document_sha256", "plan"}
_REVIEW_FIELDS = _MAP_FIELDS | {"payload", "targets"}


async def _bounded_form(request: Request) -> dict[str, str]:
    return await _form_values(request, 1_200_000, max_fields=9)


FormData = Annotated[dict[str, str], Depends(_bounded_form)]


def _structured(form: dict[str, str], key: str, kind: type, limit: int) -> Any:
    raw = form.get(key, "")
    if len(raw.encode("utf-8")) > limit:
        raise HTTPException(413, "Workbook review selection exceeds its size limit")
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object)
        if type(value) is not kind:
            raise ValueError("shape")
        return value
    except (ValueError, RecursionError) as exc:
        raise HTTPException(422, "Use the workbook mapping and review controls") from exc


def _signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        get_settings().secret_key,
        salt="classifire-draft-xlsx-scope-review-v1",
        signer_kwargs={"digest_method": hashlib.sha256},
    )


def _error(exc: DraftScopeError) -> str:
    if exc.code == "DRAFT_ARTIFACT_TOO_LARGE":
        return (
            "This reviewed batch is too large. Choose fewer rows or source links and preview again."
        )
    if exc.code == "DRAFT_REVISION_CONFLICT":
        return _editor_error(exc.code)
    return exc.code.replace("_", " ").capitalize()


def _rows(document: dict[str, Any], plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Display retained cells without inferring values or performing a mapping write."""
    sheet = next(
        (item for item in document["sheets"] if item["index"] == plan.get("sheet_index")), None
    )
    if (
        type(plan.get("sheet_index")) is not int
        or sheet is None
        or not isinstance(plan.get("mapping"), dict)
    ):
        return []
    cells = {(cell["row"], cell["column"]): cell for cell in sheet["cells"]}
    # Invalid submitted plans are shown after service rejection, never trusted as lookup keys.
    columns = {
        key: value if type(value) is int and 1 <= value <= 50 else None
        for key, value in plan["mapping"].items()
    }
    selections = plan.get("selections", [])
    if not isinstance(selections, list):
        return []
    return [
        {
            "sheet": sheet["name"],
            "sheet_index": sheet["index"],
            "row": selection["row"],
            "header_row": plan.get("header_row"),
            "mapping": plan["mapping"],
            "fields": {
                field: cells.get((selection["row"], columns.get(field)))
                for field, _label in _MAPPING_FIELDS
            },
        }
        for selection in selections[:25]
        if isinstance(selection, dict)
        and type(selection.get("row")) is int
        and 1 <= selection["row"] <= 1000
    ]


def _anchor_label(anchor: dict[str, Any]) -> str:
    def address(point: dict[str, Any]) -> str:
        column = point["column"]
        letters = ""
        while column:
            column, remainder = divmod(column - 1, 26)
            letters = chr(65 + remainder) + letters
        return f"{letters}{point['row']}"

    start = address(anchor["from"])
    end = f" to {address(anchor['to'])}" if anchor["to"] else ""
    return f"Placed at {start}{end}; placement is context only"


def _source_choices(
    document: dict[str, Any],
    plan: dict[str, Any],
    source_url: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sheet = next(
        (item for item in document["sheets"] if item["index"] == plan.get("sheet_index")), None
    )
    if sheet is None:
        return [], []
    images = [
        dict(
            item,
            preview_url=f"{source_url}/images/{sheet['index']}/"
            f"{quote(item['occurrence_id'], safe='')}.png",
            label=f"Image {index + 1} ({item['occurrence_id']})",
            anchor_label=_anchor_label(item["anchor"]),
        )
        for index, item in enumerate(sheet.get("images", []))
    ]
    return [
        {"row": row["row"], "label": f"{sheet['name']} row {row['row']}"}
        for row in _rows(document, plan)
    ], images


def _page(
    request: Request,
    db: Db,
    draft_id: str,
    source_id: str | None = None,
    *,
    review: dict[str, Any] | None = None,
    errors: list[str] | None = None,
    status_code: int = 200,
    sheet: int = 1,
    row: int = 1,
) -> HTMLResponse:
    actor = _require(request, db, "project:read")
    document = None
    source = None
    problems = list(errors or [])
    try:
        draft = get_draft(db, actor, draft_id)
        envelope = read_revision(db, actor, draft_id)
        source_api = xlsx.intake()
        sources = source_api.list_sources(db, actor, draft_id)
        if source_id is not None:
            source = source_api.source_info(db, actor, draft_id, source_id)
            if source["ready"]:
                try:
                    _, document, _ = source_api._document(
                        db,
                        actor,
                        draft_id,
                        source_id,
                        get_settings().storage_root,
                    )
                except DraftScopeError as exc:
                    if exc.status_code in {403, 404}:
                        raise
                    problems.append(_error(exc))
                    status_code = exc.status_code
    except DraftScopeError as exc:
        raise HTTPException(exc.status_code, exc.code) from exc
    base_url = f"/scopes/{draft_id}/workbooks"
    source_url = f"{base_url}/{source_id}" if source_id else ""
    plan = (review or {}).get(
        "plan",
        {
            "sheet_index": sheet,
            "header_row": 1,
            "mapping": {key: None for key, _label in _MAPPING_FIELDS},
            "selections": [],
        },
    )
    choices, images = _source_choices(document, plan, source_url) if document else ([], [])
    return templates.TemplateResponse(
        request,
        "draft_scope_xlsx.html",
        _context(
            request,
            db,
            draft=draft,
            project=draft.project,
            sources=sources,
            source=source,
            document=document,
            base_url=base_url,
            source_url=source_url,
            review_url=source_url,
            fields=_MAPPING_FIELDS,
            plan=plan,
            start_row=max(1, min(row, 1000)),
            review=review,
            payload=(review or {}).get("payload", envelope["content"]),
            expected_revision=(review or {}).get("expected_revision", envelope["revision"]),
            document_sha256=(review or {}).get(
                "document_sha256", (source or {}).get("document_sha256", "")
            ),
            saved=review is None,
            envelope=envelope,
            errors=problems,
            findings=(review or {}).get("findings", []),
            rows=(review or {}).get("rows", _rows(document, plan) if document else []),
            review_targets=(review or {}).get("targets", []),
            review_sources=choices,
            sheet_images=images,
            workbook_review=True,
            postgres=db.get_bind().dialect.name == "postgresql",
        ),
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/scopes/{draft_id}/workbooks", response_class=HTMLResponse)
def sources_page(request: Request, db: Db, draft_id: str) -> HTMLResponse:
    return _page(request, db, draft_id)


@router.post("/scopes/{draft_id}/workbooks/upload", response_model=None)
def upload(request: Request, db: Db, draft_id: str, data: UploadData):
    actor = _require(request, db, "project:write")
    try:
        source = xlsx.intake().retain(
            db,
            actor,
            draft_id,
            data["filename"],
            data["content"],
            settings=get_settings(),
        )
        db.commit()
    except DraftScopeError as exc:
        db.rollback()
        if exc.status_code in {403, 404}:
            raise HTTPException(exc.status_code, exc.code) from exc
        return _page(request, db, draft_id, errors=[_error(exc)], status_code=exc.status_code)
    return RedirectResponse(f"/scopes/{draft_id}/workbooks/{source.id}", status_code=303)


@router.get("/scopes/{draft_id}/workbooks/{source_id}", response_class=HTMLResponse)
def source_page(
    request: Request,
    db: Db,
    draft_id: str,
    source_id: str,
    sheet: int = 1,
    row: int = 1,
) -> HTMLResponse:
    return _page(request, db, draft_id, source_id, sheet=sheet, row=row)


@router.post("/scopes/{draft_id}/workbooks/{source_id}/scan", response_model=None)
def scan(request: Request, db: Db, draft_id: str, source_id: str, form: FormData):
    verify_csrf(request, form.get("csrf_token"))
    actor = _require(request, db, "project:write")
    if set(form) != {"csrf_token"}:
        raise HTTPException(422, "Use the scan control")
    try:
        xlsx.intake().scan_source(db, actor, draft_id, source_id, settings=get_settings())
        db.commit()
    except DraftScopeError as exc:
        db.rollback()
        if exc.status_code in {403, 404}:
            raise HTTPException(exc.status_code, exc.code) from exc
        return _page(
            request, db, draft_id, source_id, errors=[_error(exc)], status_code=exc.status_code
        )
    return RedirectResponse(f"/scopes/{draft_id}/workbooks/{source_id}", status_code=303)


@router.post("/scopes/{draft_id}/workbooks/{source_id}/map", response_class=HTMLResponse)
def map_rows(request: Request, db: Db, draft_id: str, source_id: str, form: FormData):
    verify_csrf(request, form.get("csrf_token"))
    actor = _require(request, db, "project:write")
    if set(form) != _MAP_FIELDS:
        raise HTTPException(422, "Use the worksheet mapping form")
    plan = _structured(form, "plan", dict, 16_384)
    revision = _positive(form["expected_revision"])
    try:
        review = xlsx.prepare_mapping(
            db,
            actor,
            draft_id,
            source_id,
            revision,
            plan,
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
            review={
                "plan": plan,
                "expected_revision": revision,
                "document_sha256": form["document_sha256"],
            },
            errors=[_error(exc), *[_finding_text(item) for item in exc.findings]],
            status_code=exc.status_code,
        )
    return _page(request, db, draft_id, source_id, review=review)


@router.post("/scopes/{draft_id}/workbooks/{source_id}/preview", response_class=HTMLResponse)
def preview(request: Request, db: Db, draft_id: str, source_id: str, form: FormData):
    verify_csrf(request, form.get("csrf_token"))
    actor = _require(request, db, "project:write")
    if set(form) not in (_REVIEW_FIELDS, _REVIEW_FIELDS | {"action"}):
        raise HTTPException(422, "Use the workbook graph review form")
    if "action" in form and form["action"] != "edit":
        raise HTTPException(422, "Choose preview or return to editing")
    plan = _structured(form, "plan", dict, 16_384)
    targets = _structured(form, "targets", list, 98_304)
    payload = _payload(form)
    revision = _positive(form["expected_revision"])
    submitted = {
        "payload": payload,
        "plan": plan,
        "targets": targets,
        "expected_revision": revision,
        "document_sha256": form["document_sha256"],
    }
    try:
        checked = xlsx.preview_review(
            db,
            actor,
            draft_id,
            source_id,
            revision,
            payload,
            plan,
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
            errors=[_error(exc), *[_finding_text(item) for item in exc.findings]],
            status_code=exc.status_code,
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
    source_api = xlsx.intake()
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
            errors=[_error(exc)],
            status_code=exc.status_code,
        )
    _choices, images = _source_choices(
        document, checked["plan"], f"/scopes/{draft_id}/workbooks/{source_id}"
    )
    return templates.TemplateResponse(
        request,
        "draft_scope_xlsx_preview.html",
        _context(
            request,
            db,
            draft=draft,
            project=draft.project,
            source=source,
            preview=checked,
            preview_token=_signer().dumps(binding),
            errors=[],
            fields=_MAPPING_FIELDS,
            sheet_images=images,
            workbook_review=True,
            review_url=f"/scopes/{draft_id}/workbooks/{source_id}",
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.post("/scopes/{draft_id}/workbooks/{source_id}/confirm", response_model=None)
def confirm(request: Request, db: Db, draft_id: str, source_id: str, form: FormData):
    verify_csrf(request, form.get("csrf_token"))
    actor = _require(request, db, "project:write")
    if set(form) != _REVIEW_FIELDS | {"preview_token", "confirm"} or form["confirm"] != "save":
        raise HTTPException(422, "Confirm the reviewed workbook graph before saving")
    payload = _payload(form)
    plan = _structured(form, "plan", dict, 16_384)
    targets = _structured(form, "targets", list, 98_304)
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
        xlsx.save_review(
            db,
            actor,
            draft_id,
            source_id,
            revision,
            payload,
            plan,
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
                "plan": plan,
                "targets": targets,
                "expected_revision": revision,
                "document_sha256": form["document_sha256"],
            },
            errors=[
                _error(exc)
                if isinstance(exc, DraftScopeError)
                else "The preview is invalid or expired. Review and preview again."
            ],
            status_code=exc.status_code if isinstance(exc, DraftScopeError) else 422,
        )
    return RedirectResponse(f"/scopes/{draft_id}", status_code=303)


@router.get("/scopes/{draft_id}/workbooks/{source_id}/images/{sheet}/{occurrence}.png")
def image(
    request: Request,
    db: Db,
    draft_id: str,
    source_id: str,
    sheet: int,
    occurrence: str,
) -> Response:
    actor = _require(request, db, "project:read")
    try:
        content = xlsx.image_preview(
            db,
            actor,
            draft_id,
            source_id,
            sheet,
            occurrence,
            settings=get_settings(),
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
