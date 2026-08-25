from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import (
    AuditEvent,
    EstimatingRule,
    LabourComponent,
    LibraryRelease,
    MarkupProfile,
    User,
)

ACTIVE_ADMINISTRATOR_REQUIRED = "active_administrator_required"
INITIALIZATION_AUDIT_REQUIRED = "initialization_audit_required"
INITIALIZATION_ALREADY_RECORDED = "initialization_already_recorded"
LEGACY_BASELINE_ADOPTION_REQUIRED = "legacy_baseline_adoption_required"
OPERATOR_REFERENCE_REQUIRED = "operator_reference_required"


class SeedDatabaseError(RuntimeError):
    """A safe, stable failure raised before controlled defaults are seeded."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _active_administrator(db: Session, *, email: str | None = None) -> User:
    statement = select(User).where(
        User.role == "administrator",
        User.is_active.is_(True),
    )
    if email is not None:
        statement = statement.where(func.lower(User.email) == email.strip().lower())
    administrator = db.scalar(
        statement.order_by(func.lower(User.email), User.email, User.id).limit(1)
    )
    if administrator is None:
        raise SeedDatabaseError(ACTIVE_ADMINISTRATOR_REQUIRED)
    return administrator


def _initialization_audit_exists(db: Session) -> bool:
    return (
        db.scalar(
            select(AuditEvent.id)
            .where(
                AuditEvent.action == "seed_controlled_defaults",
                AuditEvent.entity_type == "application_bootstrap",
                AuditEvent.entity_id == "QF-BASELINE-1",
            )
            .limit(1)
        )
        is not None
    )


def _legacy_baseline_artifacts_exist(db: Session) -> bool:
    candidates = (
        db.scalar(
            select(LibraryRelease.id).where(
                LibraryRelease.library_type == "rules",
                LibraryRelease.version == "QF-RULES-1",
            )
        ),
        db.scalar(
            select(LibraryRelease.id).where(
                LibraryRelease.library_type == "formulas",
                LibraryRelease.version == "QF-CALC-1",
            )
        ),
        db.scalar(
            select(LibraryRelease.id).where(
                LibraryRelease.library_type == "brand",
                LibraryRelease.version == "QF-BRAND-1",
            )
        ),
        db.scalar(
            select(MarkupProfile.id).where(
                MarkupProfile.scope_type == "global",
                MarkupProfile.scope_id.is_(None),
            )
        ),
        db.scalar(
            select(LabourComponent.id).where(LabourComponent.code == "LAB-PASSIVE-FIRE-INSTALLER")
        ),
        db.scalar(
            select(EstimatingRule.id).where(
                EstimatingRule.rule_code == "QF-PROX-001",
                EstimatingRule.version == 1,
            )
        ),
    )
    return any(candidate is not None for candidate in candidates)


def require_seed_database_ready(db: Session) -> User:
    """Require an active administrator and an audited explicit initialization."""

    administrator = _active_administrator(db)
    if not _initialization_audit_exists(db):
        raise SeedDatabaseError(INITIALIZATION_AUDIT_REQUIRED)
    return administrator


def ensure_release(
    db: Session,
    library_type: str,
    version: str,
    *,
    administrator: User,
    approved_at: datetime,
    status: str = "active",
) -> LibraryRelease:
    release = db.scalar(
        select(LibraryRelease).where(
            LibraryRelease.library_type == library_type,
            LibraryRelease.version == version,
        )
    )
    if release:
        return release
    payload = {"library_type": library_type, "version": version, "status": status}
    release = LibraryRelease(
        library_type=library_type,
        version=version,
        status=status,
        effective_date=date.today(),
        release_hash=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
        source_manifest=payload,
        notes="Initial QUANTIFIRE application release record.",
        created_by_id=administrator.id,
        approved_by_id=administrator.id,
        approved_at=approved_at,
    )
    db.add(release)
    db.flush()
    return release


def seed_database(
    db: Session,
    *,
    administrator_email: str,
    operator_reference: str,
    jurisdiction: str,
) -> dict[str, str]:
    if not operator_reference.strip():
        raise SeedDatabaseError(OPERATOR_REFERENCE_REQUIRED)
    user = _active_administrator(db, email=administrator_email)
    if _initialization_audit_exists(db):
        raise SeedDatabaseError(INITIALIZATION_ALREADY_RECORDED)
    if _legacy_baseline_artifacts_exist(db):
        raise SeedDatabaseError(LEGACY_BASELINE_ADOPTION_REQUIRED)
    approved_at = datetime.now(UTC)

    rules_release = ensure_release(
        db,
        "rules",
        "QF-RULES-1",
        administrator=user,
        approved_at=approved_at,
    )
    formula_release = ensure_release(
        db,
        "formulas",
        "QF-CALC-1",
        administrator=user,
        approved_at=approved_at,
    )
    brand_release = ensure_release(
        db,
        "brand",
        "QF-BRAND-1",
        administrator=user,
        approved_at=approved_at,
    )

    global_markup = db.scalar(
        select(MarkupProfile).where(
            MarkupProfile.scope_type == "global", MarkupProfile.scope_id.is_(None)
        )
    )
    if not global_markup:
        db.add(
            MarkupProfile(
                name="Global default markups",
                scope_type="global",
                product_markup=Decimal("0.30"),
                material_markup=Decimal("0.30"),
                labour_markup=Decimal("0.00"),
                status="active",
                effective_date=date.today(),
                created_by_id=user.id,
                approved_by_id=user.id,
            )
        )

    labour = db.scalar(
        select(LabourComponent).where(LabourComponent.code == "LAB-PASSIVE-FIRE-INSTALLER")
    )
    if not labour:
        db.add(
            LabourComponent(
                code="LAB-PASSIVE-FIRE-INSTALLER",
                revision=1,
                name="Passive-fire installer",
                trade_or_grade="Passive-fire installer",
                category="installation",
                unit="person_hour",
                base_rate=Decimal("130.00"),
                default_hours=Decimal("1"),
                crew_size=Decimal("1"),
                default_markup=Decimal("0"),
                productivity_source="Supplied QUANTIFIRE v2.13 commercial source corpus",
                effective_date=date.today(),
                status="active",
                release_id=formula_release.id,
            )
        )

    proximity_rule = db.scalar(
        select(EstimatingRule).where(
            EstimatingRule.rule_code == "QF-PROX-001", EstimatingRule.version == 1
        )
    )
    if not proximity_rule:
        db.add(
            EstimatingRule(
                rule_code="QF-PROX-001",
                version=1,
                name="Configurable service proximity review",
                category="service_proximity",
                description=(
                    "Evaluate edge-to-edge separation between Services. "
                    "The initial 40 mm value is a configurable estimating assumption "
                    "and review trigger, not a universal law or automatic technical approval."
                ),
                conditions={
                    "minimum_separation_mm": 40,
                    "measurement": "edge_to_edge",
                    "allow_system_specific_override": True,
                    "allow_manufacturer_specific_override": True,
                    "allow_jurisdiction_override": True,
                },
                actions={
                    "message": (
                        "Review mixed-service evidence or a technically approved "
                        "bulkhead/construction strategy."
                    ),
                    "mixed_service_search_required": True,
                    "bulkhead_allowance_permitted_only_as_provisional": True,
                    "automatic_solution_approved": False,
                },
                severity="hold",
                jurisdiction=jurisdiction,
                source_reference=(
                    "Authorised user-configurable estimating assumption; "
                    "technical system evidence controls."
                ),
                priority=10,
                status="active",
                effective_date=date.today(),
                test_cases=[
                    {"gap_mm": 39.99, "expected": "TRIGGERED"},
                    {"gap_mm": 40, "expected": "PASS"},
                    {"gap_mm": 40.01, "expected": "PASS"},
                ],
                author_id=user.id,
                reviewer_id=user.id,
                approver_id=user.id,
                approved_at=approved_at,
                release_id=rules_release.id,
            )
        )

    result = {
        "admin_user_id": user.id,
        "rules_release_id": rules_release.id,
        "formula_release_id": formula_release.id,
        "brand_release_id": brand_release.id,
    }
    record_audit(
        db,
        actor=user,
        action="seed_controlled_defaults",
        entity_type="application_bootstrap",
        entity_id="QF-BASELINE-1",
        new_value=result,
        reason=operator_reference,
    )
    db.commit()
    return result
