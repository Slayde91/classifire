from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from run_classifire_real_uat_intake import (
    Controller as BaseController,
    REQUIRED_INTAKE_TOOLS,
    REQUIRED_PHYSICAL_TOOLS,
    load_receipt,
    repo_root,
)


BATCH_SIZE = 2


def _tool_texts(value: object) -> list[str]:
    texts: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            text = node.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return texts


def _decode_json_from_text(text: str) -> object:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, char in enumerate(stripped):
        if char not in "[{":
            continue
        try:
            value, _end = decoder.raw_decode(stripped[index:])
            return value
        except json.JSONDecodeError:
            continue
    raise ValueError("No JSON value found in model/tool text")


def _json_from_payload(payload: dict, *, context: str) -> dict:
    candidates = sorted(_tool_texts(payload), key=len, reverse=True)
    errors: list[str] = []
    for text in candidates:
        try:
            value = _decode_json_from_text(text)
        except Exception as exc:
            errors.append(str(exc))
            continue
        if isinstance(value, dict):
            return value
    raise RuntimeError(
        f"{context} did not return a parseable JSON object. "
        f"Text candidates={len(candidates)}; parse errors={errors[:3]}"
    )


def _confidence(value: object, default: float = 0.7) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


def _clean_optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _scope_observation(page_number: int, item: dict, report_name: str, stored_file_id: str) -> dict:
    external_id = _clean_optional_text(item.get("external_defect_id"))
    defect_code = _clean_optional_text(item.get("defect_code"))
    description = _clean_optional_text(item.get("description")) or "Passive-fire scope observation"
    location = _clean_optional_text(item.get("location"))
    classification = _clean_optional_text(item.get("classification"))
    return {
        "stored_file_id": stored_file_id,
        "evidence_type": "defect_report_entry" if external_id or defect_code else "scope_observation",
        **({"external_defect_id": external_id} if external_id else {}),
        **({"defect_code": defect_code} if defect_code else {}),
        "defect_description": description,
        **({"defect_location": location} if location else {}),
        **({"defect_classification": classification} if classification else {}),
        "source_reference": report_name,
        "page_number": str(page_number),
        "region_reference": _clean_optional_text(item.get("region_reference")) or f"page:{page_number}:scope",
        "evidence_class": _clean_optional_text(item.get("evidence_class")) or "observed",
        "confidence": _confidence(item.get("confidence")),
        "source_json": {
            "source": "direct_pdf_analysis",
            "physical_facts": item.get("physical_facts") or [],
            "uncertainties": item.get("uncertainties") or [],
            "raw_model_item": item,
        },
    }


class DeterministicController(BaseController):
    def page_analysis_prompt(self, pages: list[int]) -> str:
        return f"""You are performing source-preserving passive-fire evidence review for CLASSIFIRE.
Analyze ONLY PDF pages {pages}. Return ONLY valid JSON, no markdown and no commentary.

Required schema:
{{
  "pages": [
    {{
      "page_number": 1,
      "page_summary": "concise factual summary",
      "scope_relevant": true,
      "confidence": 0.0,
      "scope_observations": [
        {{
          "external_defect_id": null,
          "defect_code": null,
          "description": "factual report observation",
          "location": null,
          "classification": null,
          "region_reference": "table/row/photo/section reference if visible",
          "evidence_class": "observed",
          "confidence": 0.0,
          "physical_facts": [],
          "uncertainties": []
        }}
      ]
    }}
  ]
}}

Rules:
- One photo, row, or defect ID does NOT imply one Service, one Opening, one repair, or quantity one.
- Do not choose technical systems or pricing.
- Do not invent hidden services, dimensions, materials, substrate planes, quantities, defect IDs, or locations.
- Preserve uncertainty explicitly.
- Include every supplied page exactly once in pages[].
"""

    def image_analysis_prompt(self, rows: list[dict]) -> str:
        names = [str(row["filename"]) for row in rows]
        return f"""Analyze these passive-fire report images in the supplied order.
Return ONLY valid JSON, no markdown and no commentary.

Input filenames in order: {json.dumps(names)}

Required schema:
{{
  "images": [
    {{
      "index": 1,
      "visible_summary": "only what is visibly supported",
      "scope_relevance": "relevant|non_scope|uncertain",
      "confidence": 0.0,
      "physical_facts": [],
      "uncertainties": []
    }}
  ]
}}

Rules:
- Return exactly one images[] item per supplied image, in the same order.
- Do not infer a service count, opening count, material, dimension, substrate plane, or quantity unless visibly supported.
- Logos, decorative graphics, signatures, and report furniture must be labelled non_scope when appropriate.
- One photo does NOT equal one Service, penetration, repair, or quantity.
"""

    def register_observations(self, session_key: str, observations: list[dict], receipt_name: str) -> None:
        if not observations:
            return
        self.invoke_tool(
            "cf-intake-evidence",
            session_key,
            "classifire_register_evidence_observations",
            {"estimate_id": self.estimate_id, "observations": observations},
            receipt_name,
        )

    def run_direct_intake(self, report: Path, manifest: dict) -> dict:
        missing_pages, missing_images = self.coverage_gaps(manifest)
        if not missing_pages and not missing_images:
            print("PASS deterministic intake coverage already complete")
            return self.verify_intake_coverage(manifest)

        session = self.initialize_session("cf-intake-evidence", "10-direct-intake")
        self.require_tools(
            "cf-intake-evidence",
            session,
            REQUIRED_INTAKE_TOOLS,
            "10-direct-intake-effective.json",
        )

        page_numbers = list(range(1, int(manifest["page_count"]) + 1))
        batches = [page_numbers[i : i + BATCH_SIZE] for i in range(0, len(page_numbers), BATCH_SIZE)]

        for batch_number, pages in enumerate(batches, start=1):
            missing_pages, missing_images = self.coverage_gaps(manifest)
            page_targets = [page for page in pages if f"page:{page}" in missing_pages]
            image_targets = [
                row for row in manifest["images"]
                if int(row["page_number"]) in pages
                and f"image:{row['filename']}" in missing_images
            ]
            observations: list[dict] = []

            if page_targets:
                page_filter = ",".join(str(page) for page in page_targets)
                payload = self.invoke_tool(
                    "cf-intake-evidence",
                    session,
                    "pdf",
                    {
                        "pdf": str(report),
                        "pages": page_filter,
                        "prompt": self.page_analysis_prompt(page_targets),
                    },
                    f"10-direct-b{batch_number:02d}-pdf.json",
                )
                analysis = _json_from_payload(payload, context=f"PDF batch {batch_number}")
                rows = analysis.get("pages")
                if not isinstance(rows, list):
                    raise RuntimeError(f"PDF batch {batch_number} JSON has no pages array")
                by_page: dict[int, dict] = {}
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    try:
                        page_number = int(row.get("page_number"))
                    except (TypeError, ValueError):
                        continue
                    by_page[page_number] = row
                missing_from_model = [page for page in page_targets if page not in by_page]
                if missing_from_model:
                    raise RuntimeError(
                        f"PDF batch {batch_number} omitted page analysis for {missing_from_model}"
                    )
                for page in page_targets:
                    row = by_page[page]
                    observations.append(
                        {
                            "stored_file_id": self.stored_file_id,
                            "evidence_type": "report_page_review",
                            "source_reference": self.report_name,
                            "page_number": str(page),
                            "region_reference": f"page:{page}",
                            "evidence_class": "observed",
                            "confidence": _confidence(row.get("confidence"), 0.8),
                            "source_json": {
                                "source": "direct_pdf_analysis",
                                "page_summary": _clean_optional_text(row.get("page_summary")) or "Reviewed",
                                "scope_relevant": row.get("scope_relevant"),
                                "raw_model_page": row,
                            },
                        }
                    )
                    scope_rows = row.get("scope_observations") or []
                    if isinstance(scope_rows, list):
                        for item in scope_rows:
                            if isinstance(item, dict):
                                observations.append(
                                    _scope_observation(
                                        page,
                                        item,
                                        self.report_name,
                                        self.stored_file_id,
                                    )
                                )

            if image_targets:
                image_paths = [str(report.parent / "visuals" / row["filename"]) for row in image_targets]
                payload = self.invoke_tool(
                    "cf-intake-evidence",
                    session,
                    "image",
                    {
                        "images": image_paths,
                        "prompt": self.image_analysis_prompt(image_targets),
                        "maxImages": len(image_paths),
                    },
                    f"10-direct-b{batch_number:02d}-images.json",
                )
                analysis = _json_from_payload(payload, context=f"Image batch {batch_number}")
                image_rows = analysis.get("images")
                if not isinstance(image_rows, list) or len(image_rows) != len(image_targets):
                    raise RuntimeError(
                        f"Image batch {batch_number} returned {len(image_rows) if isinstance(image_rows, list) else 'no'} "
                        f"image rows for {len(image_targets)} inputs"
                    )
                for position, source_row in enumerate(image_targets, start=1):
                    model_row = image_rows[position - 1]
                    if not isinstance(model_row, dict):
                        raise RuntimeError(f"Image batch {batch_number} item {position} is not an object")
                    observations.append(
                        {
                            "stored_file_id": self.stored_file_id,
                            "evidence_type": "report_image_review",
                            "source_reference": self.report_name,
                            "page_number": str(source_row["page_number"]),
                            "region_reference": f"image:{source_row['filename']}",
                            "evidence_class": "observed",
                            "confidence": _confidence(model_row.get("confidence"), 0.75),
                            "source_json": {
                                "source": "direct_image_analysis",
                                "filename": source_row["filename"],
                                "sha256": source_row["sha256"],
                                "visible_summary": _clean_optional_text(model_row.get("visible_summary")) or "Reviewed",
                                "scope_relevance": _clean_optional_text(model_row.get("scope_relevance")) or "uncertain",
                                "physical_facts": model_row.get("physical_facts") or [],
                                "uncertainties": model_row.get("uncertainties") or [],
                                "raw_model_image": model_row,
                            },
                        }
                    )

            self.register_observations(
                session,
                observations,
                f"10-direct-b{batch_number:02d}-register.json",
            )
            after_pages, after_images = self.coverage_gaps(manifest)
            remaining_pages = [page for page in pages if f"page:{page}" in after_pages]
            remaining_images = [
                row["filename"] for row in manifest["images"]
                if int(row["page_number"]) in pages
                and f"image:{row['filename']}" in after_images
            ]
            if remaining_pages or remaining_images:
                raise RuntimeError(
                    f"Deterministic intake batch {batch_number} did not persist complete coverage. "
                    f"Missing pages={remaining_pages}; missing images={remaining_images}"
                )
            print(
                f"PASS deterministic intake batch {batch_number}/{len(batches)} -> "
                f"pages {pages[0]}-{pages[-1]}, images {len(image_targets)}"
            )

        return self.verify_intake_coverage(manifest)

    def physical_model_prompt(self, evidence_text: str) -> str:
        return f"""You are `cf-physical-model`. Produce a physical model proposal from retained CLASSIFIRE evidence.
Do NOT call tools. Return ONLY valid JSON, no markdown and no commentary.

Canonical evidence follows:
---BEGIN EVIDENCE---
{evidence_text}
---END EVIDENCE---

Required output schema:
{{
  "status": "MODEL_SUPPORTED|INSUFFICIENT_EVIDENCE",
  "limitations": [],
  "openings": [
    {{
      "opening_code": "O-001",
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
      "service_code": "S-001",
      "primary_opening_code": "O-001",
      "opening_codes": ["O-001"],
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
- Defect -> Opening(s) -> Service(s); one defect can contain multiple openings/services.
- Identify substrate plane independently for every opening. Wall and floor/soffit are separate unless evidence proves otherwise.
- NEVER default quantity to 1 merely because there is one photo, row, defect ID, or opening. `quantity` must be an explicit evidence-backed count/measure and greater than zero.
- Do not invent material, dimensions, hidden services, FRL, substrate plane, or opening relationships.
- Use null for unknown optional values and describe material limitations.
- If at least one opening/service cannot be modelled defensibly, use INSUFFICIENT_EVIDENCE rather than inventing scope.
- Do not select Package 15 or price anything.
"""

    def _clean_opening(self, row: dict) -> dict:
        allowed = {
            "opening_code", "external_defect_id", "location", "substrate_type", "substrate_plane",
            "substrate_thickness_mm", "orientation", "opening_type", "width_mm", "height_mm",
            "diameter_mm", "frl", "notes",
        }
        return {key: row.get(key) for key in allowed if row.get(key) is not None}

    def _clean_service(self, row: dict) -> dict:
        allowed = {
            "service_code", "primary_opening_code", "opening_codes", "service_type", "material",
            "nominal_size_mm", "outside_diameter_mm", "width_mm", "height_mm", "insulation_type",
            "insulation_thickness_mm", "quantity", "centre_x_mm", "centre_y_mm", "evidence_status",
            "confidence", "relationship_status", "link_type", "source_reference", "notes",
        }
        return {key: row.get(key) for key in allowed if row.get(key) is not None}

    def run_deterministic_physical(self) -> dict:
        existing = self.inspect_state()
        if existing["physical_lock_count"] > 0:
            print("PASS physical model already locked in retained canonical state")
            return existing
        if existing["opening_count"] or existing["service_count"]:
            print("Canonical physical model already exists; using base lock path without resubmission")
            report = self.workspace_report("cf-physical-model")
            return self.run_physical(report)

        session = self.initialize_session("cf-physical-model", "20-direct-physical")
        self.require_tools(
            "cf-physical-model",
            session,
            REQUIRED_PHYSICAL_TOOLS,
            "20-direct-physical-effective.json",
        )
        evidence_payload = self.invoke_tool(
            "cf-physical-model",
            session,
            "classifire_evidence_read",
            {"estimate_id": self.estimate_id},
            "20-direct-evidence-read.json",
        )
        evidence_texts = _tool_texts(evidence_payload)
        evidence_text = max(evidence_texts, key=len) if evidence_texts else json.dumps(evidence_payload)

        synthesis = self.agent_turn(
            "cf-physical-model",
            session,
            self.physical_model_prompt(evidence_text),
            "20-direct-physical-synthesis",
        )
        if synthesis.get("recoverable_empty_result"):
            raise RuntimeError(
                "Physical-model synthesis returned empty_result before any canonical model existed. "
                "No scope was invented; rerun or inspect the synthesis receipt."
            )
        model = _json_from_payload(synthesis, context="Physical-model synthesis")
        status = str(model.get("status") or "").strip().upper()
        if status == "INSUFFICIENT_EVIDENCE":
            self.save_json("20-direct-physical-limitation.json", model)
            print("Physical-model synthesis found insufficient evidence; no model submitted.")
            return self.inspect_state()
        if status != "MODEL_SUPPORTED":
            raise RuntimeError(f"Physical-model synthesis returned unsupported status {status!r}")

        openings_raw = model.get("openings")
        services_raw = model.get("services")
        if not isinstance(openings_raw, list) or not isinstance(services_raw, list):
            raise RuntimeError("Physical-model synthesis did not return openings/services arrays")
        openings = [self._clean_opening(row) for row in openings_raw if isinstance(row, dict)]
        services = [self._clean_service(row) for row in services_raw if isinstance(row, dict)]
        if not openings or not services:
            raise RuntimeError("Physical-model synthesis claimed MODEL_SUPPORTED but returned empty scope")

        opening_codes = [str(row.get("opening_code") or "").strip() for row in openings]
        if any(not code for code in opening_codes) or len(set(opening_codes)) != len(opening_codes):
            raise RuntimeError("Physical-model opening codes are blank or duplicated")
        known_openings = set(opening_codes)
        service_codes: set[str] = set()
        for row in services:
            code = str(row.get("service_code") or "").strip()
            if not code or code in service_codes:
                raise RuntimeError("Physical-model service codes are blank or duplicated")
            service_codes.add(code)
            primary = str(row.get("primary_opening_code") or "").strip()
            linked = row.get("opening_codes")
            if primary not in known_openings or not isinstance(linked, list) or not linked:
                raise RuntimeError(f"Service {code} has invalid opening linkage")
            if any(str(item) not in known_openings for item in linked):
                raise RuntimeError(f"Service {code} references an unknown opening")
            try:
                quantity = float(row.get("quantity"))
            except (TypeError, ValueError):
                raise RuntimeError(f"Service {code} has no explicit numeric quantity")
            if quantity <= 0:
                raise RuntimeError(f"Service {code} quantity must be greater than zero")

        self.invoke_tool(
            "cf-physical-model",
            session,
            "classifire_submit_initial_physical_model",
            {"estimate_id": self.estimate_id, "openings": openings, "services": services},
            "20-direct-physical-submit.json",
        )
        after_submit = self.inspect_state()
        self.save_json("20-direct-physical-after-submit.json", after_submit)

        self.invoke_tool(
            "cf-physical-model",
            session,
            "classifire_lock_physical_model",
            {
                "estimate_id": self.estimate_id,
                "reason": "Deterministic real-UAT lock after evidence-backed physical-model synthesis",
            },
            "20-direct-physical-lock.json",
            require_ok=False,
        )
        return self.inspect_state()

    def run(self) -> dict:
        print("CLASSIFIRE deterministic real-report intake + physical-model UAT")
        print(f"Run ID: {self.run_id}")
        print(f"Estimate ID: {self.estimate_id}")
        print(f"Receipts: {self.receipt_dir}")
        self.preflight()
        manifest = self.stage_visuals()
        intake_report = self.workspace_report("cf-intake-evidence")
        intake_state = self.run_direct_intake(intake_report, manifest)
        final_state = self.run_deterministic_physical()
        final_state["run_id"] = self.run_id
        final_state["intake_coverage_ok"] = intake_state["coverage_ok"]
        final_state["status"] = (
            "PHYSICAL_MODEL_LOCKED"
            if final_state["physical_lock_count"] > 0
            else "PARTIAL_SOURCE_OR_PHYSICAL_LIMITATION"
        )
        self.save_json("31-deterministic-final-state.json", final_state)
        print(json.dumps(final_state, indent=2, default=str))
        return final_state


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic CLASSIFIRE real-report intake and physical-model acceptance."
    )
    parser.add_argument("--run-id")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()

    root = repo_root()
    _receipt_path, receipt = load_receipt(root, args.run_id)
    controller = DeterministicController(
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
        print(f"CLASSIFIRE deterministic real-report UAT failed: {exc}", file=sys.stderr)
        return 1
    finally:
        controller.close()


if __name__ == "__main__":
    raise SystemExit(main())
