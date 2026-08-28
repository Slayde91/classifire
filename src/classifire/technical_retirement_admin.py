from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from .audit import record_audit
from .db import get_db
from .models import Approval, LibraryRelease, TechnicalVariant
from .security import verify_csrf
from .services.release_scope import ReleaseScopeError, validate_release
from .services.technical_retirement import (
    TECHNICAL_RETIREMENT_APPROVAL_TYPE,
    TechnicalRetirementError,
    current_technical_retirement,
    latest_technical_retirement,
    technical_release_record,
    technical_retirement_decision,
    technical_retirement_decision_value,
    technical_retirement_request_context,
    technical_retirement_snapshot_hash,
    validate_pending_technical_retirement,
    validate_technical_retirement_approval,
)
from .ui import _require

router = APIRouter(include_in_schema=False)
Db = Annotated[Session, Depends(get_db)]


def _updated_exactly_one(result: Any) -> bool:
    return getattr(result, 'rowcount', 0) == 1


def _redirect(
    variant_id: str,
    *,
    error: str | None = None,
    success: str | None = None,
) -> RedirectResponse:
    if error is not None:
        target = f'/technical/variants/{variant_id}?error={quote_plus(error)}'
    else:
        target = f'/technical/variants/{variant_id}?success={quote_plus(success or "Done")}'
    return RedirectResponse(target, status_code=303)


def _lock_current_member(
    db: Session,
    variant_id: str,
) -> tuple[LibraryRelease, dict[str, Any], TechnicalVariant]:
    release = db.scalar(
        select(LibraryRelease)
        .where(
            LibraryRelease.library_type == 'technical',
            LibraryRelease.status == 'active',
            LibraryRelease.active_publication_slot == 'technical',
        )
        .order_by(LibraryRelease.id)
        .with_for_update(nowait=True)
        .execution_options(populate_existing=True)
    )
    if release is None:
        raise TechnicalRetirementError('TECHNICAL_RETIREMENT_ACTIVE_RELEASE_REQUIRED')
    try:
        validate_release(db, release, 'technical', allowed_statuses={'active'})
    except ReleaseScopeError as exc:
        raise TechnicalRetirementError(
            'TECHNICAL_RETIREMENT_ACTIVE_RELEASE_INVALID'
        ) from exc
    variant = db.scalar(
        select(TechnicalVariant)
        .where(TechnicalVariant.id == variant_id)
        .with_for_update(nowait=True)
        .execution_options(populate_existing=True)
    )
    if variant is None:
        raise TechnicalRetirementError('TECHNICAL_RETIREMENT_VARIANT_NOT_FOUND')
    if variant.status != 'active':
        raise TechnicalRetirementError('TECHNICAL_RETIREMENT_ACTIVE_MEMBER_REQUIRED')
    return release, technical_release_record(release, variant.id), variant


@router.post('/technical/variants/{variant_db_id}/retirement/request')
def request_technical_retirement(
    variant_db_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    reason: Annotated[str, Form()],
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, 'technical:write')
    try:
        release, record, variant = _lock_current_member(db, variant_db_id)
        existing = current_technical_retirement(
            db,
            release,
            record,
            variant,
            for_update=True,
            nowait=True,
        )
        if existing is not None and existing.status == 'pending':
            raise TechnicalRetirementError(
                'TECHNICAL_RETIREMENT_REQUEST_ALREADY_PENDING'
            )
        if existing is not None and existing.status == 'approved':
            try:
                validate_technical_retirement_approval(
                    existing,
                    release,
                    record,
                    variant,
                )
            except TechnicalRetirementError as exc:
                if exc.code != 'TECHNICAL_RETIREMENT_APPROVAL_STALE':
                    raise
            else:
                raise TechnicalRetirementError(
                    'TECHNICAL_RETIREMENT_ALREADY_APPROVED'
                )
        context = technical_retirement_request_context(
            release,
            record,
            variant,
            reason,
        )
        approval = Approval(
            entity_type='technical_variant',
            entity_id=variant.id,
            approval_type=TECHNICAL_RETIREMENT_APPROVAL_TYPE,
            status='pending',
            requested_by_id=user.id,
            decision_reason=technical_retirement_decision_value(context),
            snapshot_hash=technical_retirement_snapshot_hash(context),
        )
        db.add(approval)
        record_audit(
            db,
            actor=user,
            action='request_technical_retirement',
            entity_type='technical_variant',
            entity_id=variant.id,
            previous_value={
                'status': 'active',
                'release_id': release.id,
            },
            new_value={
                'status': 'active',
                'retirement_review': 'pending',
                'retirement_snapshot_hash': approval.snapshot_hash,
            },
            reason=str(context['request_reason']),
        )
        db.commit()
    except TechnicalRetirementError as exc:
        db.rollback()
        return _redirect(variant_db_id, error=exc.code)
    except (IntegrityError, OperationalError):
        db.rollback()
        return _redirect(
            variant_db_id,
            error='TECHNICAL_RETIREMENT_STATE_CHANGED_RETRY',
        )
    return _redirect(
        variant_db_id,
        success='Retirement request submitted for independent review',
    )


@router.post('/technical/variants/{variant_db_id}/retirement/approve')
def approve_technical_retirement(
    variant_db_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    reason: Annotated[str, Form()],
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, 'technical:approve')
    try:
        release, record, variant = _lock_current_member(db, variant_db_id)
        approval = current_technical_retirement(
            db,
            release,
            record,
            variant,
            for_update=True,
            nowait=True,
        )
        if approval is None or approval.status != 'pending':
            latest = latest_technical_retirement(
                db,
                variant.id,
                for_update=True,
                nowait=True,
            )
            if latest is not None and latest.status == 'pending':
                validate_pending_technical_retirement(
                    latest,
                    release,
                    record,
                    variant,
                )
            raise TechnicalRetirementError(
                'TECHNICAL_RETIREMENT_PENDING_REQUEST_REQUIRED'
            )
        if approval.requested_by_id == user.id:
            raise TechnicalRetirementError(
                'TECHNICAL_RETIREMENT_INDEPENDENT_REVIEWER_REQUIRED'
            )
        context = validate_pending_technical_retirement(
            approval,
            release,
            record,
            variant,
        )
        pending_value = approval.decision_reason
        transition = db.execute(
            update(Approval)
            .where(
                Approval.id == approval.id,
                Approval.status == 'pending',
                Approval.snapshot_hash == approval.snapshot_hash,
                Approval.decision_reason == pending_value,
            )
            .values(
                status='approved',
                decided_by_id=user.id,
                decided_at=datetime.now(UTC),
                decision_reason=technical_retirement_decision_value(
                    context,
                    decision_reason=reason,
                ),
            )
            .execution_options(synchronize_session=False)
        )
        if not _updated_exactly_one(transition):
            raise TechnicalRetirementError(
                'TECHNICAL_RETIREMENT_DECISION_CHANGED_RETRY'
            )
        record_audit(
            db,
            actor=user,
            action='approve_technical_retirement',
            entity_type='technical_variant',
            entity_id=variant.id,
            previous_value={'status': 'active', 'retirement_review': 'pending'},
            new_value={'status': 'active', 'retirement_review': 'approved'},
            reason=reason,
        )
        db.commit()
    except TechnicalRetirementError as exc:
        db.rollback()
        return _redirect(variant_db_id, error=exc.code)
    except (IntegrityError, OperationalError):
        db.rollback()
        return _redirect(
            variant_db_id,
            error='TECHNICAL_RETIREMENT_STATE_CHANGED_RETRY',
        )
    return _redirect(
        variant_db_id,
        success='Retirement approved for the next Technical Authority Registry release',
    )


@router.post('/technical/variants/{variant_db_id}/retirement/reject')
def reject_technical_retirement(
    variant_db_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    reason: Annotated[str, Form()],
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, 'technical:approve')
    try:
        release = db.scalar(
            select(LibraryRelease)
            .where(
                LibraryRelease.library_type == 'technical',
                LibraryRelease.status == 'active',
                LibraryRelease.active_publication_slot == 'technical',
            )
            .order_by(LibraryRelease.id)
            .with_for_update(nowait=True)
            .execution_options(populate_existing=True)
        )
        variant = db.scalar(
            select(TechnicalVariant)
            .where(TechnicalVariant.id == variant_db_id)
            .with_for_update(nowait=True)
            .execution_options(populate_existing=True)
        )
        if variant is None:
            raise TechnicalRetirementError('TECHNICAL_RETIREMENT_VARIANT_NOT_FOUND')
        current: Approval | None = None
        if release is not None and variant.status == 'active':
            try:
                record = technical_release_record(release, variant.id)
            except TechnicalRetirementError as exc:
                if exc.code != 'TECHNICAL_RETIREMENT_NOT_CURRENT_MEMBER':
                    raise
            else:
                try:
                    validate_release(db, release, 'technical', allowed_statuses={'active'})
                except ReleaseScopeError as exc:
                    raise TechnicalRetirementError(
                        'TECHNICAL_RETIREMENT_ACTIVE_RELEASE_INVALID'
                    ) from exc
                current = current_technical_retirement(
                    db,
                    release,
                    record,
                    variant,
                    for_update=True,
                    nowait=True,
                )
        if current is not None and current.status == 'approved':
            raise TechnicalRetirementError('TECHNICAL_RETIREMENT_ALREADY_APPROVED')
        approval = current or latest_technical_retirement(
            db,
            variant.id,
            for_update=True,
            nowait=True,
        )
        if approval is None or approval.status != 'pending':
            raise TechnicalRetirementError(
                'TECHNICAL_RETIREMENT_PENDING_REQUEST_REQUIRED'
            )
        if approval.requested_by_id == user.id:
            raise TechnicalRetirementError(
                'TECHNICAL_RETIREMENT_INDEPENDENT_REVIEWER_REQUIRED'
            )
        context, decision_reason = technical_retirement_decision(approval)
        if (
            decision_reason is not None
            or approval.snapshot_hash
            != technical_retirement_snapshot_hash(context)
        ):
            raise TechnicalRetirementError(
                'TECHNICAL_RETIREMENT_REQUEST_INVALID'
            )
        pending_value = approval.decision_reason
        transition = db.execute(
            update(Approval)
            .where(
                Approval.id == approval.id,
                Approval.status == 'pending',
                Approval.snapshot_hash == approval.snapshot_hash,
                Approval.decision_reason == pending_value,
            )
            .values(
                status='rejected',
                decided_by_id=user.id,
                decided_at=datetime.now(UTC),
                decision_reason=technical_retirement_decision_value(
                    context,
                    decision_reason=reason,
                ),
            )
            .execution_options(synchronize_session=False)
        )
        if not _updated_exactly_one(transition):
            raise TechnicalRetirementError(
                'TECHNICAL_RETIREMENT_DECISION_CHANGED_RETRY'
            )
        record_audit(
            db,
            actor=user,
            action='reject_technical_retirement',
            entity_type='technical_variant',
            entity_id=variant.id,
            previous_value={'status': variant.status, 'retirement_review': 'pending'},
            new_value={'status': variant.status, 'retirement_review': 'rejected'},
            reason=reason,
        )
        db.commit()
    except TechnicalRetirementError as exc:
        db.rollback()
        return _redirect(variant_db_id, error=exc.code)
    except (IntegrityError, OperationalError):
        db.rollback()
        return _redirect(
            variant_db_id,
            error='TECHNICAL_RETIREMENT_STATE_CHANGED_RETRY',
        )
    return _redirect(variant_db_id, success='Retirement request rejected')


__all__ = [
    'approve_technical_retirement',
    'reject_technical_retirement',
    'request_technical_retirement',
    'router',
]
