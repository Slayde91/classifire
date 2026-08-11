from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json

from sqlalchemy import delete, select

from classifire import canonical_models, commercial_models  # noqa: F401
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


CORRELATION_ID = "CLASSIFIRE-UAT-REOPEN-PRETECHNICAL-PHYSICAL-v1"


def reopen_pretechnical_physical_model(*, estimate_id: str, reason: str) -> dict:
    """Invalidate only a pretechnical Physical Model Lock and remove its physical rows.

    This is intentionally fail-closed. It is permitted only before any Repair Strategy,
    Repair Strategy Lock or system-required component exists for the current openings.
    Evidence and Defect records are preserved.
    """
    with SessionLocal() as db:
        estimate = db.get(Estimate, estimate_id)
        if estimate is None:
            raise RuntimeError(f"Estimate not found: {estimate_id}")
        if estimate.status not in {"draft", "in_review"}:
            raise RuntimeError(
                f"Estimate status {estimate.status!r} does not permit pretechnical reopening"
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
                "reopened": False,
                "reason": "No physical model exists",
                "opening_count_removed": 0,
                "service_count_removed": 0,
                "link_count_removed": 0,
                "lock_count_invalidated": 0,
            }

        active_locks = list(
            db.scalars(
                select(PhysicalModelLock).where(
                    PhysicalModelLock.estimate_id == estimate.id,
                    PhysicalModelLock.invalidated_at.is_(None),
                )
            ).all()
        )
        if not active_locks:
            raise RuntimeError(
                "Physical rows exist but no active Physical Model Lock exists. Use the unlocked-model correction workflow instead."
            )

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
                "Downstream technical/component records already depend on the Physical Model Lock. "
                "Controlled cascade invalidation is required; no records were changed."
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
            "active_physical_locks": [
                {
                    "id": item.id,
                    "content_hash": item.content_hash,
                    "validator_result": item.validator_result,
                }
                for item in active_locks
            ],
            "opening_ids": opening_ids,
            "opening_codes": [item.opening_code for item in openings],
            "service_ids": service_ids,
            "service_codes": [item.service_code for item in services],
            "service_opening_link_ids": [item.id for item in links],
            "opening_count": len(openings),
            "service_count": len(services),
            "service_opening_link_count": len(links),
        }

        now = datetime.now(timezone.utc)
        for lock in active_locks:
            lock.invalidated_at = now
            lock.invalidation_reason = reason

        db.execute(
            delete(ServiceOpeningLink).where(ServiceOpeningLink.opening_id.in_(opening_ids))
        )
        if service_ids:
            db.execute(delete(ServiceOpeningLink).where(ServiceOpeningLink.service_id.in_(service_ids)))
            db.execute(delete(Service).where(Service.id.in_(service_ids)))
        db.execute(delete(Opening).where(Opening.id.in_(opening_ids)))

        record_audit(
            db,
            actor=None,
            actor_type="system",
            actor_name="CLASSIFIRE controlled UAT topology correction",
            action="reopen_pretechnical_physical_model",
            entity_type="estimate",
            entity_id=estimate.id,
            project_id=estimate.project_id,
            previous_value=previous,
            new_value={
                "opening_count": 0,
                "service_count": 0,
                "service_opening_link_count": 0,
                "active_physical_lock_count": 0,
                "invalidated_lock_ids": [item.id for item in active_locks],
            },
            reason=reason,
            correlation_id=CORRELATION_ID,
        )
        db.commit()

        return {
            "estimate_id": estimate.id,
            "reopened": True,
            "reason": reason,
            "opening_count_removed": len(openings),
            "service_count_removed": len(services),
            "link_count_removed": len(links),
            "lock_count_invalidated": len(active_locks),
            "downstream_records_present": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Invalidate and remove only a locked pretechnical CLASSIFIRE physical model "
            "so it can be rebuilt after a governed topology/vision correction."
        )
    )
    parser.add_argument("--estimate-id", required=True)
    parser.add_argument(
        "--reason",
        default=(
            "Reopen pretechnical UAT Physical Model Lock after human review identified "
            "Opening/Service topology errors and a need for direct-image topology reconstruction."
        ),
    )
    args = parser.parse_args()
    try:
        result = reopen_pretechnical_physical_model(
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
