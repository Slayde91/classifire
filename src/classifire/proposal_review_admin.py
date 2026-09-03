"""Read-only human reviewer pages for proposal-review package metadata."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import ProposalReviewPackage, ProposalReviewPackageRedaction
from .services.proposal_review_package import (
    ProposalReviewPackageError,
    list_proposal_review_packages,
    read_proposal_review_package,
    record_proposal_review_package_tamper,
)
from .ui import _context, _require, templates

router = APIRouter(include_in_schema=False)
Db = Annotated[Session, Depends(get_db)]


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
    return templates.TemplateResponse(
        request,
        "proposal_review_package_detail.html",
        _context(request, db, view=view, redactions=redactions),
    )
