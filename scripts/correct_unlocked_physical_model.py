from __future__ import annotations

import argparse
import json

from sqlalchemy import delete, select

# Load the complete governed ORM metadata before any Session operation. AuditEvent
# has a foreign key to commercial_models.AuditTrail, so omitting this import leaves
# the audit_trails table unregistered and causes SQLAlchemy mapper configuration to
# fail before the correction transaction can start.
from classifire import commercial_models  # noqa: F401
from classifire.audit import record_audit
from classifire.canonical_models import (
    PhysicalModelLock,
    RepairStrategy,
    RepairStrategyLock,
    ServiceOpeningLink,
    SystemRequiredComponent,
)
from classifire.db import SessionLocal
from classifire.models import Estimate, Opening, Service


def correct_unlocked_physical_model(*, estimate_id: str, reason: str) -> dict:
    with SessionLocal() as db:
        estimate = db.get(Estimate, estimate_id)
        if estimate is None:
            raise RuntimeError(f"Estimate not found: {estimate_id}")
        if estimate.status not in {"draft", "in_review"}:
            raise RuntimeError(
                f"Estimate status {estimate.status!r} does not permit physical-model correction"
            )

        active_lock = db.scalar(
            select(PhysicalModelLock.id).where(
                PhysicalModelLock.estimate_id == estimate.id,
                PhysicalModelLock.invalidated_at.is_(None),
            ).limit(1)
        )
        if active_lock:
            raise RuntimeError(
                "An active Physical Model Lock exists. Controlled cascade invalidation is required; "
                "this unlocked-model correction script will not proceed."
            )

        openings = list(
            db.scalars(
                select(Opening)
                .where(Opening.estimate_id == estimate.id)
                .order_by(Opening.created_at, Opening.id)
            ).all()
        )
        opening_ids = [item.id for item in openings]
        if not opening_ids:
            return {
                "estimate_id": estimate.id,
                "corrected": False,
                "reason": "No unlocked physical model exists",
                "opening_count_removed": 0,
                "service_count_removed": 0,
                "link_count_removed": 0,
            }

        downstream_strategy = db.scalar(
            select(RepairStrategy.id).where(RepairStrategy.opening_id.in_(opening_ids)).limit(1)
        )
        downstream_strategy_lock = db.scalar(
            select(RepairStrategyLock.id).where(
                RepairStrategyLock.opening_id.in_(opening_ids),
                RepairStrategyLock.invalidated_at.is_(None),
            ).limit(1)
        )
        downstream_component = db.scalar(
            select(SystemRequiredComponent.id).where(
                SystemRequiredComponent.opening_id.in_(opening_ids)
            ).limit(1)
        )
        if downstream_strategy or downstream_strategy_lock or downstream_component:
            raise RuntimeError(
                "Downstream technical/component records already depend on this physical model. "
                "A controlled cascade invalidation is required; no rows were removed."
            )

        services = list(
            db.scalars(select(Service).where(Service.opening_id.in_(opening_ids))).all()
        )
        service_ids = [item.id for item in services]
        links = list(
            db.scalars(
                select(ServiceOpeningLink).where(
                    ServiceOpeningLink.opening_id.in_(opening_ids)
                )
            ).all()
        )

        previous = {
            "opening_ids": opening_ids,
            "opening_codes": [item.opening_code for item in openings],
            "service_ids": service_ids,
            "service_codes": [item.service_code for item in services],
            "service_opening_link_ids": [item.id for item in links],
            "opening_count": len(openings),
            "service_count": len(services),
            "service_opening_link_count": len(links),
        }

        db.execute(
            delete(ServiceOpeningLink).where(ServiceOpeningLink.opening_id.in_(opening_ids))
        )
        if service_ids:
            # Defensive cleanup for any multi-opening link whose opening relationship
            # was outside the current set while its Service belonged to this estimate.
            db.execute(delete(ServiceOpeningLink).where(ServiceOpeningLink.service_id.in_(service_ids)))
            db.execute(delete(Service).where(Service.id.in_(service_ids)))
        db.execute(delete(Opening).where(Opening.id.in_(opening_ids)))

        record_audit(
            db,
            actor=None,
            actor_type="system",
            actor_name="CLASSIFIRE controlled UAT correction",
            action="correct_unlocked_physical_model",
            entity_type="estimate",
            entity_id=estimate.id,
            project_id=estimate.project_id,
            previous_value=previous,
            new_value={
                "opening_count": 0,
                "service_count": 0,
                "service_opening_link_count": 0,
                "physical_model_lock_count": 0,
            },
            reason=reason,
            correlation_id="CLASSIFIRE-UAT-PHYSICAL-CORRECTION-BLANK-OPENINGS-v1",
        )
        db.commit()

        return {
            "estimate_id": estimate.id,
            "corrected": True,
            "reason": reason,
            "opening_count_removed": len(openings),
            "service_count_removed": len(services),
            "link_count_removed": len(links),
            "active_physical_lock_count": 0,
            "downstream_records_present": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Remove only an unlocked, pre-technical CLASSIFIRE physical model so it can "
            "be rebuilt after a governed physical-scope policy correction."
        )
    )
    parser.add_argument("--estimate-id", required=True)
    parser.add_argument(
        "--reason",
        default=(
            "Correct pre-lock UAT physical model after adopting governed blank-opening "
            "scope and photo-based provisional substrate/orientation assumptions."
        ),
    )
    args = parser.parse_args()
    try:
        result = correct_unlocked_physical_model(
            estimate_id=args.estimate_id,
            reason=args.reason,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps({"ok": True, **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
