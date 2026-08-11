from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import select

from classifire.canonical_models import Defect, EvidenceSource, PhysicalModelLock, ServiceOpeningLink
from classifire.db import SessionLocal
from classifire.models import Opening, Service
from classifire.services.physical_scope import canonical_opening_type, is_blank_opening_type
from run_classifire_real_uat_deterministic import _json_from_payload
from run_classifire_real_uat_fireseals_bounded import build_projected_defect_bundle
from run_classifire_real_uat_fireseals_resumable import ResumableFireSealFocusedController
from run_classifire_real_uat_intake import load_receipt, repo_root


AUDIT_SCHEMA = "CLASSIFIRE-OPENING-SERVICE-RELATIONSHIP-AUDIT-v1"


def _opening_row(opening: Opening, links: list[ServiceOpeningLink], service_by_id: dict[str, Service]) -> dict[str, Any]:
    linked_services: list[dict[str, Any]] = []
    for link in sorted(links, key=lambda item: (item.service_id, item.id)):
        service = service_by_id.get(link.service_id)
        linked_services.append(
            {
                "service_id": link.service_id,
                "service_code": service.service_code if service else None,
                "service_type": service.service_type if service else None,
                "material": service.material if service else None,
                "quantity": str(service.quantity) if service and service.quantity is not None else None,
                "nominal_size_mm": str(service.nominal_size_mm) if service and service.nominal_size_mm is not None else None,
                "outside_diameter_mm": str(service.outside_diameter_mm) if service and service.outside_diameter_mm is not None else None,
                "width_mm": str(service.width_mm) if service and service.width_mm is not None else None,
                "height_mm": str(service.height_mm) if service and service.height_mm is not None else None,
                "evidence_status": service.evidence_status if service else None,
                "relationship_status": link.relationship_status,
                "link_type": link.link_type,
                "source_reference": link.source_reference,
                "notes": service.notes if service else None,
            }
        )
    return {
        "opening_id": opening.id,
        "opening_code": opening.opening_code,
        "opening_type": canonical_opening_type(opening.opening_type),
        "location": opening.location,
        "substrate_type": opening.substrate_type,
        "substrate_plane": opening.substrate_plane,
        "orientation": opening.orientation,
        "width_mm": str(opening.width_mm) if opening.width_mm is not None else None,
        "height_mm": str(opening.height_mm) if opening.height_mm is not None else None,
        "diameter_mm": str(opening.diameter_mm) if opening.diameter_mm is not None else None,
        "frl": opening.frl,
        "notes": opening.notes,
        "service_count": len(linked_services),
        "services": linked_services,
    }


def _deterministic_findings(opening_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for opening in opening_rows:
        opening_type = canonical_opening_type(opening.get("opening_type"))
        service_count = int(opening.get("service_count") or 0)
        code = str(opening.get("opening_code") or "")
        if is_blank_opening_type(opening_type) and service_count:
            findings.append(
                {
                    "severity": "ERROR",
                    "opening_code": code,
                    "issue": "blank opening has linked Services",
                }
            )
        if not is_blank_opening_type(opening_type) and service_count == 0:
            findings.append(
                {
                    "severity": "ERROR",
                    "opening_code": code,
                    "issue": "non-blank Opening has no linked Service",
                }
            )
        if service_count > 1:
            findings.append(
                {
                    "severity": "INFO",
                    "opening_code": code,
                    "issue": f"multi-service Opening retained with {service_count} linked Services",
                }
            )
        for service in opening.get("services") or []:
            if not str(service.get("material") or "").strip():
                findings.append(
                    {
                        "severity": "REVIEW",
                        "opening_code": code,
                        "service_code": service.get("service_code"),
                        "issue": "Service material unresolved; inspect retained photographs/evidence",
                    }
                )
    return findings


def _audit_prompt(*, defect: Defect, current_model: dict[str, Any], evidence_bundle: str) -> str:
    identity = defect.external_defect_id or defect.defect_code or defect.id
    return f"""You are the independent CLASSIFIRE physical-relationship auditor for ONE passive-fire defect.
Return ONLY valid JSON. You are auditing the locked physical grouping; do not select a technical system and do not price anything.

Target defect: {identity}
Current locked physical model:
{json.dumps(current_model, ensure_ascii=False, separators=(",", ":"), default=str)}

Retained direct evidence bundle:
{evidence_bundle}

Mandatory ontology and audit rules:
- An Opening is ONE physical aperture/hole through ONE fire-rated barrier plane.
- ONE Opening may contain ZERO Services when it is an evidenced blank aperture/redundant core/empty core hole.
- ONE Opening may contain ONE OR MANY Services. Different service types/materials do NOT require separate Openings.
- Example: a cable bundle + PVC pipe + metal pipe through one large aperture = ONE Opening with THREE Services.
- Never infer one Opening per Service. Never infer one Opening per photograph.
- Separate Openings are justified only when evidence supports physically distinct apertures/holes or distinct barrier planes.
- Opposite faces or different angles of the same barrier penetration normally remain the same Opening unless evidence proves otherwise.
- Exact duplicate photographs must not increase Opening or Service count.
- A cable bundle may be one Service/group where the evidence supports a bundle rather than individually countable cables.
- Preserve each distinct supported Service within a mixed-service Opening.
- Audit Service quantity from physical count/report wording, never photo count.
- If Service material is missing, use retained photo/text evidence to suggest the most defensible material only when rational. Mark it inferred/provisional; otherwise unresolved.
- Proposed-resolution wording is clue-only and cannot by itself prove a Service or material.
- `-/120/120` may be an assumed FRL in this scope; do not treat that assumption as evidence of physical grouping.

Return this schema exactly:
{{
  "status": "PASS|REVIEW_REQUIRED",
  "confidence": 0.0,
  "current_opening_count_supported": true,
  "recommended_opening_count": null,
  "opening_findings": [
    {{
      "current_opening_code": "O-001",
      "finding": "SUPPORTED|POSSIBLE_OVER_SPLIT|POSSIBLE_OVER_MERGE|BLANK_SUPPORTED|SERVICE_ASSIGNMENT_ISSUE|EVIDENCE_LIMITED",
      "basis": [],
      "current_service_codes": [],
      "service_codes_that_should_share_opening": []
    }}
  ],
  "service_findings": [
    {{
      "service_code": "S-001",
      "quantity_status": "SUPPORTED|REVIEW_REQUIRED|UNRESOLVED",
      "quantity_basis": [],
      "material_current": null,
      "material_suggested": null,
      "material_status": "CONFIRMED|INFERRED|PROVISIONAL|UNRESOLVED",
      "material_basis": []
    }}
  ],
  "recommended_grouping": [
    {{
      "physical_opening_label": "physical-opening-1",
      "current_opening_codes": [],
      "service_codes": [],
      "blank_opening": false,
      "basis": []
    }}
  ],
  "issues": [],
  "notes": []
}}

A PASS means the current number of physical Openings and assignment of Services to those Openings is defensible from the retained evidence. REVIEW_REQUIRED means there is a material possibility that the locked physical grouping is wrong or a Service/material/quantity needs human or renewed evidence review before technical-system search.
"""


def run_audit(*, run_id: str, estimate_id: str | None = None, timeout_seconds: int = 1200) -> dict[str, Any]:
    root = repo_root()
    _receipt_path, receipt = load_receipt(root, run_id)
    controller = ResumableFireSealFocusedController(
        receipt,
        base_url="http://127.0.0.1:8787",
        timeout_seconds=timeout_seconds,
    )
    try:
        target_estimate_id = estimate_id or controller.estimate_id
        if target_estimate_id != controller.estimate_id:
            raise RuntimeError(
                f"Run {run_id} belongs to estimate {controller.estimate_id}, not {target_estimate_id}"
            )

        with SessionLocal() as db:
            active_lock = db.scalar(
                select(PhysicalModelLock).where(
                    PhysicalModelLock.estimate_id == target_estimate_id,
                    PhysicalModelLock.invalidated_at.is_(None),
                ).limit(1)
            )
            if active_lock is None:
                raise RuntimeError("No active Physical Model Lock exists; relationship audit requires a locked model")

            defects = list(
                db.scalars(
                    select(Defect)
                    .where(Defect.estimate_id == target_estimate_id)
                    .order_by(Defect.created_at, Defect.id)
                ).all()
            )
            openings = list(
                db.scalars(
                    select(Opening)
                    .where(Opening.estimate_id == target_estimate_id)
                    .order_by(Opening.created_at, Opening.id)
                ).all()
            )
            opening_ids = [item.id for item in openings]
            links = (
                list(
                    db.scalars(
                        select(ServiceOpeningLink).where(ServiceOpeningLink.opening_id.in_(opening_ids))
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
            evidence = list(
                db.scalars(
                    select(EvidenceSource).where(
                        EvidenceSource.estimate_id == target_estimate_id,
                        EvidenceSource.status == "active",
                    )
                ).all()
            )

        service_by_id = {item.id: item for item in services}
        links_by_opening: dict[str, list[ServiceOpeningLink]] = defaultdict(list)
        for link in links:
            links_by_opening[link.opening_id].append(link)
        openings_by_defect: dict[str, list[Opening]] = defaultdict(list)
        for opening in openings:
            if opening.canonical_defect_id:
                openings_by_defect[opening.canonical_defect_id].append(opening)

        audit_rows: list[dict[str, Any]] = []
        review_required = False
        for index, defect in enumerate(defects, start=1):
            identity = defect.external_defect_id or defect.defect_code or defect.id
            defect_openings = openings_by_defect.get(defect.id, [])
            current_openings = [
                _opening_row(opening, links_by_opening.get(opening.id, []), service_by_id)
                for opening in defect_openings
            ]
            deterministic = _deterministic_findings(current_openings)

            direct_evidence = [item for item in evidence if item.defect_id == defect.id]
            compact_rows = [controller._compact_evidence_row(item) for item in direct_evidence]
            defect_payload = {
                "canonical_defect_id": defect.id,
                "external_defect_id": defect.external_defect_id,
                "defect_code": defect.defect_code,
                "description": defect.description,
                "location": defect.location,
                "classification": defect.classification,
                "evidence_status": defect.evidence_status,
            }
            evidence_bundle = build_projected_defect_bundle(defect_payload, compact_rows)
            current_model = {
                "defect_id": identity,
                "opening_count": len(current_openings),
                "openings": current_openings,
            }
            payload = controller.infer_model(
                prompt=_audit_prompt(
                    defect=defect,
                    current_model=current_model,
                    evidence_bundle=evidence_bundle,
                ),
                receipt_name=f"25-opening-service-audit-{index:03d}",
                thinking="high",
            )
            model_audit = _json_from_payload(
                payload,
                context=f"Opening/Service relationship audit for defect {identity}",
            )
            status = str(model_audit.get("status") or "").strip().upper()
            if status not in {"PASS", "REVIEW_REQUIRED"}:
                raise RuntimeError(f"Defect {identity} audit returned unsupported status {status!r}")
            if status == "REVIEW_REQUIRED" or any(
                item.get("severity") in {"ERROR", "REVIEW"} for item in deterministic
            ):
                review_required = True

            row = {
                "external_defect_id": defect.external_defect_id,
                "canonical_defect_id": defect.id,
                "current_opening_count": len(current_openings),
                "current_service_count": sum(int(item.get("service_count") or 0) for item in current_openings),
                "deterministic_findings": deterministic,
                "independent_audit": model_audit,
            }
            audit_rows.append(row)
            print(
                f"AUDIT defect {index}/{len(defects)} {identity} -> {status}, "
                f"openings {row['current_opening_count']}, services {row['current_service_count']}"
            )

        result = {
            "schema": AUDIT_SCHEMA,
            "run_id": run_id,
            "estimate_id": target_estimate_id,
            "physical_model_lock_id": active_lock.id,
            "physical_model_lock_hash": active_lock.content_hash,
            "opening_count": len(openings),
            "service_count": len(services),
            "relationship_audit_status": "REVIEW_REQUIRED" if review_required else "PASS",
            "technical_search_permitted_by_this_audit": not review_required,
            "defects": audit_rows,
        }
        controller.save_json("25-opening-service-relationship-audit.json", result)
        print(json.dumps(result, indent=2, default=str))
        return result
    finally:
        controller.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only independent audit of CLASSIFIRE Opening/Service grouping before "
            "opening-specific technical-system search."
        )
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--estimate-id")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()
    try:
        result = run_audit(
            run_id=args.run_id,
            estimate_id=args.estimate_id,
            timeout_seconds=args.timeout_seconds,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    # REVIEW_REQUIRED is an audit result, not a script execution failure.
    return 0 if result.get("relationship_audit_status") in {"PASS", "REVIEW_REQUIRED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
