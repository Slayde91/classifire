from __future__ import annotations

import argparse
import json

from sqlalchemy import select

from classifire.canonical_models import ServiceOpeningLink
from classifire.db import SessionLocal
from classifire.models import Estimate, Opening, Service
from classifire.services.workflow_db import assess_estimate_workflow


REQUIRED_OPENING_FIELDS = (
    "substrate_type",
    "substrate_plane",
    "orientation",
    "frl",
)


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

        incomplete: list[dict[str, object]] = []
        opening_rows: list[dict[str, object]] = []
        for opening in openings:
            missing_fields = [
                field for field in REQUIRED_OPENING_FIELDS if not getattr(opening, field, None)
            ]
            opening_links = links_by_opening.get(opening.id, [])
            if not opening_links:
                missing_fields.append("service_opening_link")
            row = {
                "opening_id": opening.id,
                "opening_code": opening.opening_code,
                "external_defect_id": opening.external_defect_id,
                "canonical_defect_id": opening.canonical_defect_id,
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
                "missing_for_lock": missing_fields,
            }
            opening_rows.append(row)
            if missing_fields:
                incomplete.append(row)

        assessment = assess_estimate_workflow(db, estimate)
        result = {
            "schema": "CLASSIFIRE-PHYSICAL-MODEL-LOCK-DIAGNOSTIC-v1",
            "estimate_id": estimate.id,
            "workflow_stage": assessment.stage,
            "workflow_facts": {
                "evidence_intake_complete": assessment.facts.evidence_intake_complete,
                "physical_model_complete": assessment.facts.physical_model_complete,
                "physical_model_locked": assessment.facts.physical_model_locked,
            },
            "opening_count": len(openings),
            "service_count_linked": len(service_ids),
            "service_opening_link_count": len(links),
            "incomplete_opening_count": len(incomplete),
            "incomplete_openings": incomplete,
            "openings": opening_rows,
            "workflow_diagnostics": assessment.diagnostics,
        }
        print(json.dumps(result, indent=2, default=str))
        return 0 if not incomplete else 2


if __name__ == "__main__":
    raise SystemExit(main())
