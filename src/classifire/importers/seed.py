from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import (
    EstimatingRule,
    LabourComponent,
    LibraryRelease,
    MarkupProfile,
    User,
)
from ..security import hash_password


def ensure_release(
    db: Session, library_type: str, version: str, status: str = "active"
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
    )
    db.add(release)
    db.flush()
    return release


def seed_database(db: Session, settings: Settings) -> dict[str, str]:
    user = db.scalar(select(User).where(User.email == settings.admin_email.lower()))
    if not user:
        user = User(
            email=settings.admin_email.lower(),
            full_name="QUANTIFIRE Administrator",
            password_hash=hash_password(settings.admin_password),
            role="administrator",
            is_active=True,
        )
        db.add(user)
        db.flush()

    rules_release = ensure_release(db, "rules", "QF-RULES-1")
    formula_release = ensure_release(db, "formulas", "QF-CALC-1")
    brand_release = ensure_release(db, "brand", "QF-BRAND-1")

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
                    "Evaluate edge-to-edge separation between Services. The initial "
                    "40 mm value is a configurable estimating assumption and review "
                    "trigger, not a universal law or automatic technical approval."
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
                jurisdiction=settings.jurisdiction,
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
                approved_at=user.created_at,
                release_id=rules_release.id,
            )
        )

    db.commit()
    return {
        "admin_user_id": user.id,
        "rules_release_id": rules_release.id,
        "formula_release_id": formula_release.id,
        "brand_release_id": brand_release.id,
    }
