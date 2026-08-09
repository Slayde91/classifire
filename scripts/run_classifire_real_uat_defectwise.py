from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from sqlalchemy import select

from classifire.canonical_models import Defect, EvidenceSource
from classifire.db import SessionLocal
from run_classifire_real_uat_deterministic import (
    REQUIRED_PHYSICAL_WRITE_TOOLS,
    _clean_optional_text,
    _confidence,
    _json_from_payload,
)
from run_classifire_real_uat_intake import load_receipt, repo_root
from run_classifire_real_uat_windows_safe import (
    MAX_FINAL_PHYSICAL_EVIDENCE_CHARS,
    WindowsSafeController,
)


MAX_EVIDENCE_ITEM_TEXT = 700


def _trim(value: object, limit: int = MAX_EVIDENCE_ITEM_TEXT) -> str | None:
    text = _clean_optional_text(value)
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


class DefectWiseController(WindowsSafeController):
    def _defects_and_evidence(self) -> tuple[list[Defect], list[EvidenceSource]]:
        with SessionLocal() as db:
            defects = list(
                db.scalars(
                    select(Defect)
                    .where(Defect.estimate_id == self.estimate_id)
                    .order_by(Defect.created_at, Defect.id)
                ).all()
            )
            evidence = list(
                db.scalars(
                    select(EvidenceSource)
                    .where(
                        EvidenceSource.estimate_id == self.estimate_id,
                        EvidenceSource.status == "active",
                    )
                    .order_by(EvidenceSource.page_number, EvidenceSource.created_at, EvidenceSource.id)
                ).all()
            )
        return defects, evidence

    @staticmethod
    def _compact_evidence_row(item: EvidenceSource) -> dict:
        source = item.source_json or {}
        row: dict[str, object] = {
            "evidence_id": item.id,
            "type": item.evidence_type,
            "page": item.page_number,
            "region": item.region_reference,
            "evidence_class": item.evidence_class,
            "confidence": str(item.confidence) if item.confidence is not None else None,
        }
        if item.evidence_type == "report_page_review":
            row["summary"] = _trim(source.get("page_summary"), 500)
            row["scope_relevant"] = source.get("scope_relevant")
        elif item.evidence_type == "report_image_review":
            row["summary"] = _trim(source.get("visible_summary"), 600)
            row["scope_relevance"] = source.get("scope_relevance")
            row["physical_facts"] = source.get("physical_facts") or []
            row["uncertainties"] = source.get("uncertainties") or []
        else:
            raw = source.get("raw_model_item") or {}
            if isinstance(raw, dict):
                row["description"] = _trim(raw.get("description"), 700)
                row["location"] = _trim(raw.get("location"), 350)
                row["classification"] = _trim(raw.get("classification"), 200)
            row["physical_facts"] = source.get("physical_facts") or []
            row["uncertainties"] = source.get("uncertainties") or []
        return row

    def _bundle_for_defect(
        self,
        defect: Defect,
        all_evidence: list[EvidenceSource],
    ) -> str:
        directly_linked = [item for item in all_evidence if item.defect_id == defect.id]
        pages = {
            str(item.page_number)
            for item in directly_linked
            if item.page_number is not None and str(item.page_number).strip()
        }

        # Page/image reviews are context only. They remain independently identified so the
        # model cannot treat a same-page image as proven evidence for this defect unless the
        # visible facts support that association.
        contextual = [
            item
            for item in all_evidence
            if item.defect_id is None
            and item.page_number is not None
            and str(item.page_number) in pages
            and item.evidence_type in {"report_page_review", "report_image_review"}
        ]

        payload = {
            "defect": {
                "canonical_defect_id": defect.id,
                "external_defect_id": defect.external_defect_id,
                "defect_code": defect.defect_code,
                "description": _trim(defect.description, 900),
                "location": _trim(defect.location, 500),
                "classification": defect.classification,
                "evidence_status": defect.evidence_status,
            },
            "direct_evidence": [self._compact_evidence_row(item) for item in directly_linked],
            "same_page_context": [self._compact_evidence_row(item) for item in contextual],
            "context_rule": (
                "same_page_context is contextual only and must not be attributed to this defect "
                "unless the content itself supports the association"
            ),
        }
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
        if len(text) > MAX_FINAL_PHYSICAL_EVIDENCE_CHARS:
            text = self._reduce_physical_evidence(text)
        return text

    def defect_physical_prompt(self, defect: Defect, evidence_text: str) -> str:
        identity = defect.external_defect_id or defect.defect_code or defect.id
        return f"""You are performing the cf-physical-model reasoning stage for ONE canonical CLASSIFIRE defect: {identity}.
Return ONLY valid JSON, no markdown and no commentary. Do not select Package 15 systems or pricing.

Evidence bundle:
---BEGIN DEFECT EVIDENCE---
{evidence_text}
---END DEFECT EVIDENCE---

Required schema:
{{
  "status": "MODEL_SUPPORTED|INSUFFICIENT_EVIDENCE",
  "limitations": [],
  "openings": [
    {{
      "opening_code": "D-O-001",
      "external_defect_id": null,
      "location": null,
      "substrate_type": null,
      "substrate_plane": null,
      "substrate_thickness_mm": null,
      "orientation": null,
      "opening_type": null,
      "width_mm": null,
      "height_mm": null,
      "diameter_mm": null,
      "frl": null,
      "notes": null
    }}
  ],
  "services": [
    {{
      "service_code": "D-S-001",
      "primary_opening_code": "D-O-001",
      "opening_codes": ["D-O-001"],
      "service_type": "pipe|cable|duct|mixed|other",
      "material": null,
      "nominal_size_mm": null,
      "outside_diameter_mm": null,
      "width_mm": null,
      "height_mm": null,
      "insulation_type": null,
      "insulation_thickness_mm": null,
      "quantity": 1,
      "centre_x_mm": null,
      "centre_y_mm": null,
      "evidence_status": "confirmed|inferred|provisional",
      "confidence": 0.0,
      "relationship_status": "confirmed|inferred|provisional",
      "link_type": "penetrates",
      "source_reference": null,
      "notes": null
    }}
  ]
}}

Hard rules:
- This defect may contain zero, one, or MULTIPLE openings and MULTIPLE services. Never force one defect into one opening/service.
- One photo, report row, or defect ID does NOT establish quantity one.
- Every service quantity must be an explicit evidence-backed count/measure greater than zero. If it cannot be supported, return INSUFFICIENT_EVIDENCE.
- Identify the substrate plane independently for every opening. Wall and floor/soffit are distinct unless evidence proves otherwise.
- Same-page image context is not automatically evidence for this defect; associate it only when content supports the linkage.
- Do not invent hidden services, dimensions, materials, FRL, substrate planes, opening relationships, or quantities.
- Use null for unknown optional fields, but if an unknown prevents a defensible opening/service model, return INSUFFICIENT_EVIDENCE.
- Preserve Confirmed/Inferred/Provisional status and source references.
"""

    def _validate_and_remap_defect_model(
        self,
        defect: Defect,
        model: dict,
        opening_start: int,
        service_start: int,
    ) -> tuple[list[dict], list[dict], int, int]:
        openings_raw = model.get("openings")
        services_raw = model.get("services")
        if not isinstance(openings_raw, list) or not isinstance(services_raw, list):
            raise RuntimeError("Defect synthesis did not return openings/services arrays")

        local_openings = [self._clean_opening(row) for row in openings_raw if isinstance(row, dict)]
        local_services = [self._clean_service(row) for row in services_raw if isinstance(row, dict)]
        if not local_openings or not local_services:
            raise RuntimeError("Defect synthesis claimed MODEL_SUPPORTED but returned empty physical scope")

        local_codes: list[str] = []
        for row in local_openings:
            code = str(row.get("opening_code") or "").strip()
            if not code or code in local_codes:
                raise RuntimeError("Defect synthesis returned blank or duplicate opening codes")
            local_codes.append(code)

        opening_map = {
            local_code: f"O-{opening_start + index:03d}"
            for index, local_code in enumerate(local_codes)
        }
        openings: list[dict] = []
        for row in local_openings:
            local_code = str(row["opening_code"])
            mapped = dict(row)
            mapped["opening_code"] = opening_map[local_code]
            mapped["external_defect_id"] = defect.external_defect_id or defect.defect_code
            openings.append(mapped)

        services: list[dict] = []
        seen_service_codes: set[str] = set()
        for index, row in enumerate(local_services):
            local_service_code = str(row.get("service_code") or "").strip()
            if not local_service_code or local_service_code in seen_service_codes:
                raise RuntimeError("Defect synthesis returned blank or duplicate service codes")
            seen_service_codes.add(local_service_code)

            primary = str(row.get("primary_opening_code") or "").strip()
            linked = row.get("opening_codes")
            if primary not in opening_map or not isinstance(linked, list) or not linked:
                raise RuntimeError(f"Service {local_service_code} has invalid opening linkage")
            if any(str(item) not in opening_map for item in linked):
                raise RuntimeError(f"Service {local_service_code} references an unknown opening")
            try:
                quantity = float(row.get("quantity"))
            except (TypeError, ValueError) as exc:
                raise RuntimeError(f"Service {local_service_code} has no explicit numeric quantity") from exc
            if quantity <= 0:
                raise RuntimeError(f"Service {local_service_code} quantity must be greater than zero")

            mapped = dict(row)
            mapped["service_code"] = f"S-{service_start + index:03d}"
            mapped["primary_opening_code"] = opening_map[primary]
            mapped["opening_codes"] = [opening_map[str(item)] for item in linked]
            services.append(mapped)

        return (
            openings,
            services,
            opening_start + len(openings),
            service_start + len(services),
        )

    def run_defectwise_physical(self) -> dict:
        existing = self.inspect_state()
        if existing["physical_lock_count"] > 0:
            print("PASS physical model already locked in retained canonical state")
            return existing
        if existing["opening_count"] or existing["service_count"]:
            report = self.workspace_report("cf-physical-model")
            return self.run_physical(report)

        session = self.initialize_session("cf-physical-model", "20-defectwise-physical")
        self.require_tools(
            "cf-physical-model",
            session,
            REQUIRED_PHYSICAL_WRITE_TOOLS,
            "20-defectwise-physical-effective.json",
        )
        self.invoke_tool(
            "cf-physical-model",
            session,
            "classifire_evidence_read",
            {"estimate_id": self.estimate_id},
            "20-defectwise-evidence-read.json",
        )

        defects, evidence = self._defects_and_evidence()
        if not defects:
            raise RuntimeError("No canonical defects exist for defect-wise physical synthesis")

        all_openings: list[dict] = []
        all_services: list[dict] = []
        limitations: list[dict] = []
        next_opening = 1
        next_service = 1

        for index, defect in enumerate(defects, start=1):
            identity = defect.external_defect_id or defect.defect_code or defect.id
            bundle = self._bundle_for_defect(defect, evidence)
            self.save_text(f"20-defect-{index:03d}-evidence.json", bundle)
            payload = self.infer_model(
                prompt=self.defect_physical_prompt(defect, bundle),
                receipt_name=f"20-defect-{index:03d}-synthesis",
                thinking="high",
            )
            model = _json_from_payload(payload, context=f"Physical synthesis for defect {identity}")
            status = str(model.get("status") or "").strip().upper()
            if status == "INSUFFICIENT_EVIDENCE":
                limitations.append(
                    {
                        "canonical_defect_id": defect.id,
                        "external_defect_id": defect.external_defect_id,
                        "defect_code": defect.defect_code,
                        "limitations": model.get("limitations") or [],
                    }
                )
                print(f"LIMIT defect {index}/{len(defects)} {identity} -> insufficient evidence")
                continue
            if status != "MODEL_SUPPORTED":
                raise RuntimeError(
                    f"Defect {identity} synthesis returned unsupported status {status!r}"
                )

            try:
                openings, services, next_opening, next_service = self._validate_and_remap_defect_model(
                    defect,
                    model,
                    next_opening,
                    next_service,
                )
            except RuntimeError as exc:
                limitations.append(
                    {
                        "canonical_defect_id": defect.id,
                        "external_defect_id": defect.external_defect_id,
                        "defect_code": defect.defect_code,
                        "limitations": [str(exc)],
                    }
                )
                print(f"LIMIT defect {index}/{len(defects)} {identity} -> {exc}")
                continue

            all_openings.extend(openings)
            all_services.extend(services)
            print(
                f"PASS defect {index}/{len(defects)} {identity} -> "
                f"openings {len(openings)}, services {len(services)}"
            )

        if limitations:
            result = {
                "status": "PARTIAL_SOURCE_OR_PHYSICAL_LIMITATION",
                "defect_count": len(defects),
                "supported_defect_count": len(defects) - len(limitations),
                "limited_defect_count": len(limitations),
                "proposed_opening_count": len(all_openings),
                "proposed_service_count": len(all_services),
                "limitations": limitations,
                "model_submitted": False,
                "reason": (
                    "At least one canonical defect lacks a defensible physical model. "
                    "CLASSIFIRE refuses partial canonical submission before Physical Model Lock."
                ),
            }
            self.save_json("20-defectwise-physical-limitations.json", result)
            print(json.dumps(result, indent=2, default=str))
            return self.inspect_state()

        if not all_openings or not all_services:
            raise RuntimeError("Defect-wise synthesis produced no physical scope")

        self.save_json(
            "20-defectwise-merged-proposal.json",
            {
                "openings": all_openings,
                "services": all_services,
            },
        )
        self.invoke_tool(
            "cf-physical-model",
            session,
            "classifire_submit_initial_physical_model",
            {
                "estimate_id": self.estimate_id,
                "openings": all_openings,
                "services": all_services,
            },
            "20-defectwise-physical-submit.json",
        )
        self.invoke_tool(
            "cf-physical-model",
            session,
            "classifire_lock_physical_model",
            {
                "estimate_id": self.estimate_id,
                "reason": (
                    "Defect-wise deterministic real-UAT Physical Model Lock after "
                    "complete evidence-backed synthesis"
                ),
            },
            "20-defectwise-physical-lock.json",
            require_ok=False,
        )
        return self.inspect_state()

    def run(self) -> dict:
        print("CLASSIFIRE defect-wise real-report physical-model UAT")
        print(f"Run ID: {self.run_id}")
        print(f"Estimate ID: {self.estimate_id}")
        print(f"Receipts: {self.receipt_dir}")
        self.preflight()
        manifest = self.stage_visuals()
        intake_report = self.workspace_report("cf-intake-evidence")
        intake_state = self.run_windows_safe_intake(intake_report, manifest)
        final_state = self.run_defectwise_physical()
        final_state["run_id"] = self.run_id
        final_state["intake_coverage_ok"] = intake_state["coverage_ok"]
        final_state["status"] = (
            "PHYSICAL_MODEL_LOCKED"
            if final_state["physical_lock_count"] > 0
            else "PARTIAL_SOURCE_OR_PHYSICAL_LIMITATION"
        )
        self.save_json("51-defectwise-final-state.json", final_state)
        print(json.dumps(final_state, indent=2, default=str))
        return final_state


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run defect-wise CLASSIFIRE physical-model acceptance from retained real-UAT evidence."
    )
    parser.add_argument("--run-id")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()

    root = repo_root()
    _receipt_path, receipt = load_receipt(root, args.run_id)
    controller = DefectWiseController(
        receipt,
        base_url=args.base_url,
        timeout_seconds=args.timeout_seconds,
    )
    try:
        state = controller.run()
        return 0 if state.get("status") in {
            "PHYSICAL_MODEL_LOCKED",
            "PARTIAL_SOURCE_OR_PHYSICAL_LIMITATION",
        } else 1
    except Exception as exc:
        print(f"CLASSIFIRE defect-wise real-report UAT failed: {exc}", file=sys.stderr)
        return 1
    finally:
        controller.close()


if __name__ == "__main__":
    raise SystemExit(main())
