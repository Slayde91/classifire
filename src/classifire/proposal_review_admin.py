"""Proposal-review pages, administrator-only annotations, and reader grants."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import (
    ProposalReviewPackage,
    ProposalReviewPackageRedaction,
    ProposalReviewReaderAssignment,
    User,
)
from .security import verify_csrf
from .services.proposal_review_package import (
    ProposalReviewPackageError,
    grant_proposal_review_reader_assignment,
    list_eligible_proposal_review_readers,
    list_proposal_review_annotations,
    list_proposal_review_packages,
    list_proposal_review_reader_assignments,
    read_proposal_review_package,
    record_proposal_review_annotation,
    record_proposal_review_package_tamper,
    revoke_proposal_review_reader_assignment,
)
from .ui import _context, _require, templates

router = APIRouter(include_in_schema=False)
Db = Annotated[Session, Depends(get_db)]


def _require_administrator_package(
    package_id: str,
    request: Request,
    db: Session,
) -> tuple[User, ProposalReviewPackage]:
    actor = _require(request, db, "proposal_review:read")
    if actor.role != "administrator":
        raise HTTPException(403, "Proposal-review administrator access is required")
    record = db.scalar(
        select(ProposalReviewPackage).where(ProposalReviewPackage.package_id == package_id)
    )
    if record is None:
        raise HTTPException(404, "Proposal-review package is unavailable")
    try:
        read_proposal_review_package(db, package_id=package_id, actor=actor)
    except ProposalReviewPackageError as exc:
        status_code = 409 if exc.code == "PROPOSAL_REVIEW_PACKAGE_TAMPERED" else 404
        raise HTTPException(status_code, "Proposal-review package is unavailable") from exc
    return actor, record


@router.get("/proposal-reviews", response_class=HTMLResponse)
def proposal_review_packages_page(request: Request, db: Db) -> HTMLResponse:
    actor = _require(request, db, "proposal_review:read")
    records = list_proposal_review_packages(db, actor=actor)
    return templates.TemplateResponse(
        request,
        "proposal_review_packages.html",
        _context(request, db, records=records),
    )


@router.get("/proposal-reviews/{package_id}", response_class=HTMLResponse)
def proposal_review_package_page(
    package_id: str,
    request: Request,
    db: Db,
    redaction_id: str | None = None,
) -> HTMLResponse:
    actor = _require(request, db, "proposal_review:read")
    record = db.scalar(
        select(ProposalReviewPackage).where(ProposalReviewPackage.package_id == package_id)
    )
    try:
        view = read_proposal_review_package(
            db,
            package_id=package_id,
            actor=actor,
            redaction_id=redaction_id,
        )
        annotations = list_proposal_review_annotations(
            db,
            record=view.record,
            actor=actor,
            redaction_id=redaction_id,
        )
    except ProposalReviewPackageError as exc:
        if exc.code == "PROPOSAL_REVIEW_PACKAGE_TAMPERED" and record is not None:
            record_proposal_review_package_tamper(
                db,
                record=record,
                actor=actor,
                error=exc,
            )
            db.commit()
        status_code = 409 if exc.code == "PROPOSAL_REVIEW_PACKAGE_TAMPERED" else 404
        raise HTTPException(status_code, "Proposal-review package is unavailable") from exc
    redactions = db.scalars(
        select(ProposalReviewPackageRedaction)
        .where(ProposalReviewPackageRedaction.proposal_review_package_id == view.record.id)
        .order_by(ProposalReviewPackageRedaction.created_at.desc())
    ).all()
    reader_assignments: tuple[ProposalReviewReaderAssignment, ...] = ()
    eligible_readers: tuple[User, ...] = ()
    if actor.role == "administrator":
        reader_assignments = list_proposal_review_reader_assignments(
            db,
            record=view.record,
            actor=actor,
        )
        eligible_readers = list_eligible_proposal_review_readers(db, actor=actor)
    return templates.TemplateResponse(
        request,
        "proposal_review_package_detail.html",
        _context(
            request,
            db,
            view=view,
            annotations=annotations,
            redactions=redactions,
            reader_assignments=reader_assignments,
            eligible_readers=eligible_readers,
        ),
    )


@router.post("/proposal-reviews/{package_id}/annotations")
def proposal_review_annotation_record(
    package_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    finding_state: Annotated[str, Form()],
    reason_code: Annotated[str, Form()],
    scope_id: Annotated[str | None, Form()] = None,
    redaction_id: str | None = None,
) -> RedirectResponse:
    """Record a proposal-only human annotation; no reviewer role gains authority."""

    verify_csrf(request, csrf_token)
    actor, _ = _require_administrator_package(package_id, request, db)
    try:
        record_proposal_review_annotation(
            db,
            package_id=package_id,
            finding_state=finding_state,
            reason_code=reason_code,
            scope_id=scope_id,
            redaction_id=redaction_id,
            actor=actor,
        )
        db.commit()
    except ProposalReviewPackageError as exc:
        db.rollback()
        status_code = 409 if exc.code == "PROPOSAL_REVIEW_PACKAGE_TAMPERED" else 400
        raise HTTPException(status_code, "Proposal-review annotation is unavailable") from exc
    suffix = f"?redaction_id={redaction_id}" if redaction_id is not None else ""
    return RedirectResponse(f"/proposal-reviews/{package_id}{suffix}", status_code=303)


@router.post("/proposal-reviews/{package_id}/reader-assignments")
def proposal_review_reader_assignment_grant(
    package_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    user_id: Annotated[str, Form()],
    scope_kind: Annotated[str, Form()],
    reason_code: Annotated[str, Form()],
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    actor, record = _require_administrator_package(package_id, request, db)
    if scope_kind == "project":
        project_id, proposal_review_package_id = record.project_id, None
    elif scope_kind == "package":
        project_id, proposal_review_package_id = None, record.id
    else:
        raise HTTPException(400, "Proposal-review reader scope is invalid")
    try:
        grant_proposal_review_reader_assignment(
            db,
            user_id=user_id,
            project_id=project_id,
            proposal_review_package_id=proposal_review_package_id,
            reason_code=reason_code,
            actor=actor,
        )
        db.commit()
    except ProposalReviewPackageError as exc:
        db.rollback()
        raise HTTPException(400, "Proposal-review reader assignment is unavailable") from exc
    return RedirectResponse(f"/proposal-reviews/{package_id}", status_code=303)


@router.post("/proposal-reviews/{package_id}/reader-assignments/{assignment_id}/revoke")
def proposal_review_reader_assignment_revoke(
    package_id: str,
    assignment_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    reason_code: Annotated[str, Form()],
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    actor, record = _require_administrator_package(package_id, request, db)
    try:
        revoke_proposal_review_reader_assignment(
            db,
            proposal_review_reader_assignment_id=assignment_id,
            record=record,
            reason_code=reason_code,
            actor=actor,
        )
        db.commit()
    except ProposalReviewPackageError as exc:
        db.rollback()
        raise HTTPException(400, "Proposal-review reader revocation is unavailable") from exc
    return RedirectResponse(f"/proposal-reviews/{package_id}", status_code=303)
