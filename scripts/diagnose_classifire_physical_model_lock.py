from __future__ import annotations

import argparse
import json

from sqlalchemy import select

from classifire.canonical_models import ServiceOpeningLink
from classifire.db import SessionLocal
from classifire.models import Estimate, Opening, Service
from classifire.services.physical_scope import assess_physical_model_completeness
from classifire.services.workflow_guard import check_estimate_action
from classifire.services.workflow import WorkflowAction


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose why a CLASSIFIRE Physical Model Lock is blocked."
    )
    parser.add_argument("--estimate-id", required=True)
    args = parser.parse_args()

    with SessionLocal() as db:
        estimate = db.get(Estimate, args.estimate_id)
        if estimate is None:
            raise SystemExit(f"Estimate not found: {args.estimate_id}")

        openings = list(
            db.scalars(
                select(Opening)
                .where(Opening.estimate_id == estimate.id)
                .order_by(Opening.opening_code, Opening.id)
            ).all()
        )
        opening_ids = [item.id for item in openings]
        links = (
            list(
                db.scalars(
                    select(ServiceOpeningLink)
                    .where(ServiceOpeningLink.opening_id.in_(opening_ids))
                    .order_by(ServiceOpeningLink.opening_id, ServiceOpeningLink.service_id)
                ).all()
            )
            if opening_ids
            else []
        )
        service_ids = sorted({item.service_id for item in links})
        services = (
            list(db.scalars(select(Service).where(Service.id.in_(service_ids))).all())
            if service_ids
            else []
        )
        service_by_id = {item.id: item for item in services}
        links_by_opening: dict[str, list[ServiceOpeningLink]] = {
            item.id: [] for item in openings
        }
        for link in links:
            links_by_opening.setdefault(link.opening_id, []).append(link)

        physical = assess_physical_model_completeness(db, estimate.id)
        completeness_by_id = {row.opening_id: row for row in physical.openings}
        incomplete: list[dict[str, object]] = []
        opening_rows: list[dict[str, object]] = []
        for opening in openings:
            opening_links = links_by_opening.get(opening.id, [])
            completeness = completeness_by_id[opening.id]
            row = {
                "opening_id": opening.id,
                "opening_code": opening.opening_code,
                "external_defect_id": opening.defect_id,
                "canonical_defect_id": opening.canonical_defect_id,
                "opening_type": completeness.opening_type,
                "blank_opening": completeness.blank_opening,
                "substrate_type": opening.substrate_type,
                "substrate_plane": opening.substrate_plane,
                "orientation": opening.orientation,
                "frl": opening.frl,
                "service_link_count": len(opening_links),
                "linked_services": [
                    {
                        "service_id": link.service_id,
                        "service_code": (
                            service_by_id[link.service_id].service_code
                            if link.service_id in service_by_id
                            else None
                        ),
                        "service_type": (
                            service_by_id[link.service_id].service_type
                            if link.service_id in service_by_id
                            else None
                        ),
                        "material": (
                            service_by_id[link.service_id].material
                            if link.service_id in service_by_id
                            else None
                        ),
                        "quantity": (
                            str(service_by_id[link.service_id].quantity)
                            if link.service_id in service_by_id
                            else None
                        ),
                    }
                    for link in opening_links
                ],
                "missing_for_lock": list(completeness.missing_fields),
            }
            opening_rows.append(row)
            if not completeness.complete:
                incomplete.append(row)

        guard = check_estimate_action(db, estimate, WorkflowAction.LOCK_PHYSICAL_MODEL)
        result = {
            "schema": "CLASSIFIRE-PHYSICAL-MODEL-LOCK-DIAGNOSTIC-v2",
            "estimate_id": estimate.id,
            "workflow_stage": guard.stage,
            "lock_allowed": guard.allowed,
            "lock_blockers": list(guard.blockers),
            "opening_count": len(openings),
            "service_count_linked": len(service_ids),
            "service_opening_link_count": len(links),
            "scope_aware_physical_model_complete": physical.complete,
            "incomplete_opening_count": len(incomplete),
            "incomplete_openings": incomplete,
            "openings": opening_rows,
            "workflow_diagnostics": guard.diagnostics,
        }
        print(json.dumps(result, indent=2, default=str))
        return 0 if guard.allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())
