from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader
from run_classifire_real_uat_defectwise import _trim
from run_classifire_real_uat_deterministic import (
    REQUIRED_INTAKE_WRITE_TOOLS,
    _confidence,
    _json_from_payload,
)
from run_classifire_real_uat_intake import load_receipt, repo_root
from run_classifire_real_uat_photoaware import PhotoAwareController
from run_classifire_real_uat_windows_safe import _split_text

from classifire.canonical_models import Defect, EvidenceSource

TEXT_FACT_EVIDENCE_TYPE = "defect_text_fact_review"
TEXT_CHUNK_CHARS = 5200
GATEWAY_RPC_TIMEOUT_MS = 60000
GATEWAY_PROCESS_TIMEOUT_SECONDS = 90


class IntegratedEvidenceController(PhotoAwareController):
    """Real-report UAT with structured report-text evidence and duplicate-aware photo vision."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._photo_rows: dict[str, dict] = {}
        self._photo_visual_cache: dict[str, dict] = {}

    def preflight(self) -> None:
        config = self.openclaw("config", "validate", "--json")
        self.save_text("01-openclaw-config.json", config.stdout)

        status = None
        for attempt in range(1, 3):
            try:
                status = self.openclaw(
                    "gateway",
                    "status",
                    "--require-rpc",
                    "--timeout",
                    str(GATEWAY_RPC_TIMEOUT_MS),
                    timeout=GATEWAY_PROCESS_TIMEOUT_SECONDS,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                status = None
                print(
                    f"OpenClaw Gateway RPC probe timed out on attempt {attempt}/2; "
                    "treating the probe as unhealthy."
                )

            if status is not None and status.returncode == 0:
                self.save_text("02-openclaw-gateway.txt", status.stdout + status.stderr)
                print("PASS OpenClaw Gateway RPC")
                self.ensure_api()
                return

            if attempt == 1:
                print("OpenClaw Gateway RPC is unhealthy; restarting the managed Gateway once...")
                try:
                    self.openclaw("gateway", "restart", timeout=90, check=False)
                except subprocess.TimeoutExpired:
                    # A supervisor restart can complete after the client-side command times out.
                    print("Gateway restart command timed out; continuing to the bounded retry probe.")
                time.sleep(8)

        detail = ""
        if status is not None:
            detail = "\n".join(
                item for item in (status.stdout.strip(), status.stderr.strip()) if item
            )
        raise RuntimeError(
            "OpenClaw Gateway RPC preflight failed after one managed restart and retry."
            + (f" Details: {detail}" if detail else "")
        )

    @staticmethod
    def _compact_evidence_row(item: EvidenceSource) -> dict:
        source = item.source_json or {}
        if item.evidence_type == TEXT_FACT_EVIDENCE_TYPE:
            return {
                "evidence_id": item.id,
                "type": item.evidence_type,
                "page": item.page_number,
                "region": item.region_reference,
                "association_status": source.get("association_status"),
                "attributes": source.get("attributes") or [],
                "quantities": source.get("quantities") or [],
                "services": source.get("services") or [],
                "treatment_clues": source.get("treatment_clues") or [],
                "technical_details": source.get("technical_details") or [],
                "physical_facts": source.get("physical_facts") or [],
                "uncertainties": source.get("uncertainties") or [],
            }
        return PhotoAwareController._compact_evidence_row(item)

    def defect_physical_prompt(self, defect: Defect, evidence_text: str) -> str:
        base = super().defect_physical_prompt(defect, evidence_text)
        return base + """

Additional mandatory report-text rules:
- Use explicit defect-linked report text together with photographic evidence. Text can directly establish
  stated location, FRL, substrate, substrate plane, orientation, service description/material/size and stated
  quantities when the text is clearly associated with this defect.
- Distinguish quantity kinds. Two core holes may support opening_count=2; it does not automatically mean two
  Services. A stated service count may support service quantity only when the subject of the count is explicit.
- Proposed-resolution / treatment wording is a technical clue, not proof of the existing physical condition.
  It may support a provisional hypothesis but must not override contradictory photos or create hidden scope.
- If report text and photos conflict on a material physical fact, preserve the conflict and return
  INSUFFICIENT_EVIDENCE when the conflict prevents a defensible physical model.
- Do not select the final treatment system here. Package 15/17 remains the technical authority after the
  Physical Model Lock.
"""

    def _text_fact_prompt(
        self,
        defect: Defect,
        page_number: int,
        chunk: str,
        chunk_number: int,
        chunk_count: int,
    ) -> str:
        identity = defect.external_defect_id or defect.defect_code or defect.id
        return f"""Extract structured passive-fire evidence from report text for ONE target CLASSIFIRE defect.
Target defect/item ID: {identity}
Retained description: {_trim(defect.description, 850)}
Retained location: {_trim(defect.location, 450)}
Source page: {page_number}
Text chunk: {chunk_number}/{chunk_count}

--- BEGIN EXTRACTED REPORT TEXT ---
{chunk}
--- END EXTRACTED REPORT TEXT ---

Return ONLY valid JSON:
{{
  "target_defect_id": "{identity}",
  "page_number": {page_number},
  "association_status": "SUPPORTED|AMBIGUOUS|NOT_VISIBLE",
  "confidence": 0.0,
  "attributes": [
    {{
      "name": "frl|substrate_type|substrate_plane|orientation|service_type|service_material|service_size|location|opening_type|other",
      "value": null,
      "status": "stated|inferred|unknown",
      "source_role": "defect_row|description|location|proposed_resolution|schedule|note|other",
      "basis": "short source-grounded basis"
    }}
  ],
  "quantities": [
    {{
      "kind": "service_count|opening_count|item_count|treatment_count|other",
      "value": null,
      "unit": null,
      "status": "stated|inferred|unknown",
      "source_role": "defect_row|description|location|proposed_resolution|schedule|note|other",
      "basis": ""
    }}
  ],
  "services": [
    {{
      "label": null,
      "service_type": null,
      "material": null,
      "size": null,
      "quantity": null,
      "status": "stated|inferred|provisional",
      "source_role": "description|proposed_resolution|schedule|note|other",
      "basis": ""
    }}
  ],
  "treatment_clues": [
    {{
      "text": "",
      "source_role": "proposed_resolution|instruction|description|note|other",
      "authority": "clue_only"
    }}
  ],
  "technical_details": [],
  "physical_facts": [],
  "uncertainties": []
}}

Hard rules:
- Extract only facts or clues associated with target {identity}; do not borrow a neighbouring defect's row.
- Preserve explicit FRL notation exactly, e.g. -/120/120, when stated.
- Preserve stated substrate and plane distinctions such as wall, floor, slab, soffit or ceiling.
- Preserve service type/material/size and location when stated.
- Distinguish opening count from service count, item count and treatment count.
- Do not infer quantity=1 from one defect row, one photo, one description or one proposed treatment.
- Proposed-resolution wording is not proof that a stated service/material physically exists; mark such service
  clues provisional/inferred unless corroborated by description or other evidence.
- Do not choose Package 15/17 systems and do not price anything.
"""

    @staticmethod
    def _dedupe_objects(rows: list[object]) -> list[object]:
        seen: set[str] = set()
        result: list[object] = []
        for row in rows:
            key = json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)
            if key in seen:
                continue
            seen.add(key)
            result.append(row)
        return result

    def _merge_text_analyses(self, analyses: list[dict], page_number: int) -> dict:
        statuses = [str(row.get("association_status") or "NOT_VISIBLE").upper() for row in analyses]
        association_status = (
            "SUPPORTED"
            if "SUPPORTED" in statuses
            else "AMBIGUOUS"
            if "AMBIGUOUS" in statuses
            else "NOT_VISIBLE"
        )
        confidences = [_confidence(row.get("confidence"), 0.65) for row in analyses]
        merged = {
            "source": "structured_report_text_reasoning",
            "page_number": page_number,
            "association_status": association_status,
            "confidence": sum(confidences) / len(confidences) if confidences else 0.6,
            "attributes": self._dedupe_objects(
                [item for row in analyses for item in (row.get("attributes") or [])]
            ),
            "quantities": self._dedupe_objects(
                [item for row in analyses for item in (row.get("quantities") or [])]
            ),
            "services": self._dedupe_objects(
                [item for row in analyses for item in (row.get("services") or [])]
            ),
            "treatment_clues": self._dedupe_objects(
                [item for row in analyses for item in (row.get("treatment_clues") or [])]
            ),
            "technical_details": self._dedupe_objects(
                [item for row in analyses for item in (row.get("technical_details") or [])]
            ),
            "physical_facts": self._dedupe_objects(
                [item for row in analyses for item in (row.get("physical_facts") or [])]
            ),
            "uncertainties": self._dedupe_objects(
                [item for row in analyses for item in (row.get("uncertainties") or [])]
            ),
            "chunk_results": len(analyses),
        }
        return merged

    def run_structured_text_evidence(self, report: Path) -> dict[str, object]:
        reader = PdfReader(str(report))
        defects, defect_pages = self._defects_and_direct_pages()
        session = self.initialize_session("cf-intake-evidence", "14-structured-text-evidence")
        self.require_tools(
            "cf-intake-evidence",
            session,
            REQUIRED_INTAKE_WRITE_TOOLS,
            "14-structured-text-effective.json",
        )

        created = 0
        retained = 0
        for defect_index, defect in enumerate(defects, start=1):
            identity = defect.external_defect_id or defect.defect_code or defect.id
            pages = defect_pages.get(defect.id) or []
            for page_number in pages:
                region = f"text-facts:page:{page_number}:defect:{identity}"
                existing = self._existing_source(defect.id, TEXT_FACT_EVIDENCE_TYPE, region)
                if existing is not None:
                    retained += 1
                    continue
                if page_number < 1 or page_number > len(reader.pages):
                    raise RuntimeError(f"Defect {identity} references invalid PDF page {page_number}")
                page_text = reader.pages[page_number - 1].extract_text() or ""
                chunks = _split_text(page_text, TEXT_CHUNK_CHARS)
                analyses: list[dict] = []
                for chunk_index, chunk in enumerate(chunks, start=1):
                    payload = self.infer_model(
                        prompt=self._text_fact_prompt(
                            defect,
                            page_number,
                            chunk,
                            chunk_index,
                            len(chunks),
                        ),
                        receipt_name=(
                            f"14-text-d{defect_index:03d}-p{page_number:03d}-c{chunk_index:03d}"
                        ),
                        thinking="medium",
                    )
                    analysis = _json_from_payload(
                        payload,
                        context=(
                            f"Structured text extraction for defect {identity}, "
                            f"page {page_number}, chunk {chunk_index}"
                        ),
                    )
                    if str(analysis.get("target_defect_id") or "").strip() != str(identity):
                        raise RuntimeError(
                            f"Structured text extraction returned wrong target defect for {identity}"
                        )
                    try:
                        returned_page = int(analysis.get("page_number"))
                    except (TypeError, ValueError) as exc:
                        raise RuntimeError(
                            f"Structured text extraction returned invalid page for {identity}"
                        ) from exc
                    if returned_page != page_number:
                        raise RuntimeError(
                            f"Structured text extraction for {identity} returned page {returned_page}, "
                            f"expected {page_number}"
                        )
                    analyses.append(analysis)

                source_json = self._merge_text_analyses(analyses, page_number)
                self._register_direct_evidence(
                    session,
                    defect,
                    evidence_type=TEXT_FACT_EVIDENCE_TYPE,
                    page_number=page_number,
                    region_reference=region,
                    source_json=source_json,
                    receipt_name=(
                        f"14-text-d{defect_index:03d}-p{page_number:03d}-register.json"
                    ),
                )
                created += 1
                print(
                    f"PASS text defect {defect_index}/{len(defects)} {identity} page {page_number} "
                    f"-> {source_json['association_status'].lower()}"
                )

        result = {
            "defect_count": len(defects),
            "text_fact_observations_created": created,
            "text_fact_observations_retained": retained,
        }
        self.save_json("14-structured-text-summary.json", result)
        return result

    @staticmethod
    def _visual_key(row: dict) -> str:
        variant_group = str(row.get("image_variant_group_id") or "").strip()
        if variant_group:
            relationships = {
                str(value) for value in (row.get("image_variant_relationships") or [])
            }
            if str(row.get("image_variant_group_status") or "") != "RESOLVED" or (
                relationships & {"AMBIGUOUS", "SIMILAR_DISTINCT"}
            ):
                return f"variant-occurrence:{variant_group}:{row['photo_id']}"
            return f"variant-group:{variant_group}"
        linked_digest = str(row.get("full_resolution_sha256") or "").strip()
        if linked_digest:
            return f"linked-sha256:{linked_digest.lower()}"
        digest = str(row.get("digest") or "").strip()
        return f"digest:{digest}" if digest else f"photo:{row['photo_id']}"

    def _build_photo_inventory(self, report: Path) -> tuple[dict[int, list[dict]], dict[str, dict]]:
        return super()._build_photo_inventory(report)

    def _on_image_variant_inventory_ready(self, by_id: dict[str, dict]) -> None:
        groups: dict[str, list[dict]] = defaultdict(list)
        for row in by_id.values():
            groups[self._visual_key(row)].append(row)

        duplicate_occurrences = 0
        for group_key, rows in groups.items():
            rows.sort(key=lambda item: (int(item["page_number"]), int(item["occurrence"])))
            variant_result = getattr(self, "_image_variant_resolution_cache", None)
            variant_group = None
            if variant_result is not None and group_key.startswith("variant-group:"):
                wanted_group_id = group_key.removeprefix("variant-group:")
                variant_group = next(
                    (
                        item
                        for item in variant_result.groups
                        if str(item.get("group_id") or "") == wanted_group_id
                    ),
                    None,
                )
            exact_occurrences: set[str] = set()
            if variant_group is not None:
                candidate_rows = {
                    str(item.get("candidate_id") or ""): item
                    for item in variant_result.rows
                }
                exact_candidate_ids = [str(variant_group.get("primary_candidate_id") or "")]
                exact_candidate_ids.extend(
                    str(item) for item in (variant_group.get("equivalent_candidate_ids") or ())
                )
                for candidate_id in exact_candidate_ids:
                    candidate = candidate_rows.get(candidate_id)
                    if candidate is None:
                        continue
                    if str(candidate.get("relationship_to_primary") or "") in {
                        "SELF",
                        "EXACT_BYTES",
                        "EXACT_DECODED_PIXELS",
                    }:
                        exact_occurrences.add(str(candidate.get("occurrence_id") or ""))
            exact_group = len(rows) > 1 and all(
                str(item.get("photo_id") or "") in exact_occurrences for item in rows
            )
            preferred_photo_id = next(
                (
                    str(item.get("image_variant_primary_photo_id") or "")
                    for item in rows
                    if str(item.get("image_variant_primary_photo_id") or "")
                ),
                "",
            )
            canonical = next(
                (item for item in rows if str(item.get("photo_id")) == preferred_photo_id),
                rows[0],
            )
            canonical_id = str(canonical["photo_id"])
            for row in rows:
                row["visual_group_key"] = group_key
                row["canonical_photo_id"] = canonical_id
                row["duplicate_group_size"] = len(rows)
                row["exact_duplicate"] = exact_group
                row["duplicate_of_photo_id"] = (
                    None
                    if not exact_group or str(row["photo_id"]) == canonical_id
                    else canonical_id
                )
                if row["duplicate_of_photo_id"]:
                    duplicate_occurrences += 1

        self._photo_rows = by_id
        self.save_json(
            "16a-photo-dedup-map.json",
            {
                "schema": "CLASSIFIRE-PHOTO-VARIANT-GROUP-MAP-v2",
                "report_sha256": str(self.receipt["report_sha256"]),
                "image_variant_policy_version": str(
                    next(
                        iter(by_id.values()),
                        {},
                    ).get("image_variant_policy_version")
                    or ""
                ),
                "image_variant_receipt_sha256": self._image_variant_receipt_sha256(),
                "photo_occurrences": len(by_id),
                "unique_visuals": len(groups),
                "exact_duplicate_occurrences": duplicate_occurrences,
                "groups": {
                    key: [str(row["photo_id"]) for row in rows]
                    for key, rows in sorted(groups.items())
                },
            },
        )
        print(
            f"PASS image-variant grouping -> {len(by_id)} occurrences, "
            f"{len(groups)} unique visuals, {duplicate_occurrences} duplicate occurrences"
        )

    def _visual_photo_prompt(
        self,
        row: dict,
        attachment_manifest: list[dict] | None = None,
    ) -> str:
        manifest = attachment_manifest or []
        return f"""Perform a defect-neutral, high-resolution visual inspection of ONE report image for CLASSIFIRE.
Image occurrence ID: {row['photo_id']} from source page {row['page_number']}.
The ordered attachment manifest is authoritative:
{json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))}
Attachment 1 is the proven greatest-usable-detail PRIMARY regardless of where it occurs in the report. Inspect it
first for fine detail. Inspect every MANDATORY_SECONDARY attachment for unique crop, annotation, contrast, label or
page-context information. Do not base detailed conclusions on a lower-resolution equivalent when the primary is
clearer, and do not collapse AMBIGUOUS, SIMILAR_DISTINCT or derivative versions as resolution-only.

Return ONLY valid JSON:
{{
  "photo_id": "{row['photo_id']}",
  "scope_relevance": "relevant|non_scope|uncertain",
  "visible_summary": "",
  "viewpoint": "same_side_angle|wall_face_a|wall_face_b|floor_top|soffit_underside|unknown",
  "barrier_face": null,
  "visible_services": [],
  "visible_openings": [],
  "distinctive_features": [],
  "physical_facts": [],
  "uncertainties": [],
  "needs_zoom": false
}}

Rules:
- Company logos, header/footer graphics, signatures, icons and report furniture are non_scope.
- Inspect only visible physical evidence; do not infer a defect association in this step.
- One image does not establish one Service, Opening, repair or quantity one.
- Record individually distinguishable services/openings and viewpoint clues without inventing hidden scope.
- Record service arrangement, colours, fittings, insulation, opening shape, barrier face and nearby landmarks
  useful for comparing this image with other views.
- Do not invent dimensions, material identity, FRL, substrate plane, treatment system or pricing.
"""

    def _analyse_photo_detail(
        self,
        report: Path,
        defect: Defect,
        row: dict,
        defect_index: int,
    ) -> dict:
        # Exact duplicate image bytes are visually analysed once for the whole report. Each occurrence still
        # receives its own page-layout linkage evidence, so repeated placement under different defect rows is
        # not silently treated as the same defect association.
        variant_fingerprint = self._image_variant_receipt_sha256()
        visual_key = f"{variant_fingerprint}:{self._visual_key(row)}"
        cached = self._photo_visual_cache.get(visual_key)
        if cached is None:
            sources = self._preferred_photo_sources(report, row)
            files = [Path(item["path"]) for item in sources]
            attachment_manifest = self._attachment_manifest(sources)
            payload = self.infer_model(
                prompt=self._visual_photo_prompt(row, attachment_manifest),
                receipt_name=(
                    f"16a-visual-v2-{variant_fingerprint[:12]}-"
                    f"{row['canonical_photo_id']}"
                ),
                files=files,
                thinking="medium",
            )
            cached = _json_from_payload(payload, context=f"Unique visual {row['photo_id']}")
            if str(cached.get("photo_id") or "") != str(row["photo_id"]):
                raise RuntimeError(f"Unique visual review returned wrong photo_id for {row['photo_id']}")
            cached["native_extraction_ok"] = bool(row.get("native_extraction_ok"))
            cached["full_resolution_status"] = row.get("full_resolution_status")
            cached["native_pixels"] = [
                sources[0].get("width"),
                sources[0].get("height"),
            ]
            cached["primary_photo_id"] = sources[0].get("photo_id")
            cached["primary_page"] = sources[0].get("page")
            cached["source_bbox"] = row.get("bbox")
            cached["zoom_refinement_performed"] = True
            cached["image_variant_receipt_sha256"] = variant_fingerprint
            cached["image_variant_group_id"] = row.get("image_variant_group_id")
            cached["attachment_manifest"] = attachment_manifest
            self._photo_visual_cache[visual_key] = copy.deepcopy(cached)
        else:
            cached = copy.deepcopy(cached)

        model = copy.deepcopy(cached)
        model["photo_id"] = row["photo_id"]
        # Defect association is established by the page-layout linkage step, not by the cached visual review.
        model["target_link"] = "ambiguous"
        features = list(model.get("distinctive_features") or [])
        features.append(f"IMAGE_VARIANT_GROUP:{visual_key}")
        if row.get("exact_duplicate"):
            features.append(f"EXACT_IMAGE_GROUP:{visual_key}")
        features.append(f"CANONICAL_PHOTO_ID:{row['canonical_photo_id']}")
        if row.get("duplicate_of_photo_id"):
            features.append(f"EXACT_DUPLICATE_OF:{row['duplicate_of_photo_id']}")
        model["distinctive_features"] = list(dict.fromkeys(str(item) for item in features))
        model["exact_duplicate"] = bool(row.get("exact_duplicate"))
        model["duplicate_of_photo_id"] = row.get("duplicate_of_photo_id")
        return model

    @staticmethod
    def _detail_visual_group(item: dict) -> str:
        for feature in item.get("distinctive_features") or []:
            text = str(feature)
            if text.startswith("EXACT_IMAGE_GROUP:"):
                return text.removeprefix("EXACT_IMAGE_GROUP:")
        return f"photo:{item.get('photo_id')}"

    def _contact_sheet(self, rows: list[tuple[str, Path]], defect_index: int) -> Path:
        unique_rows: list[tuple[str, Path]] = []
        seen: set[str] = set()
        for label, path in rows:
            key = str(path.resolve()).casefold()
            if key in seen:
                continue
            seen.add(key)
            unique_rows.append((label, path))
        return super()._contact_sheet(unique_rows, defect_index)

    def reconciliation_prompt(self, defect: Defect, details: list[dict]) -> str:
        unique_details: list[dict] = []
        seen: set[str] = set()
        for item in details:
            key = self._detail_visual_group(item)
            if key in seen:
                continue
            seen.add(key)
            unique_details.append(item)
        base = super().reconciliation_prompt(defect, unique_details)
        return base + """

Exact-duplicate rule:
- Exact duplicate image occurrences have already been collapsed to one unique visual before this reconciliation.
  They are one piece of visual content and must never increase service count or opening count merely because the
  same image was embedded/displayed more than once in the report.
"""

    def run(self) -> dict:
        print("CLASSIFIRE integrated text + duplicate-aware photo real-report UAT")
        print(f"Run ID: {self.run_id}")
        print(f"Estimate ID: {self.estimate_id}")
        print(f"Receipts: {self.receipt_dir}")
        self.preflight()
        manifest = self.stage_visuals()
        intake_report = self.workspace_report("cf-intake-evidence")
        intake_state = self.run_windows_safe_intake(intake_report, manifest)
        text_state = self.run_structured_text_evidence(intake_report)
        photo_state = self.run_photo_aware_evidence(intake_report)
        final_state = self.run_defectwise_physical()
        final_state["run_id"] = self.run_id
        final_state["intake_coverage_ok"] = intake_state["coverage_ok"]
        final_state["text_evidence"] = text_state
        final_state["photo_evidence"] = photo_state
        final_state["status"] = (
            "PHYSICAL_MODEL_LOCKED"
            if final_state["physical_lock_count"] > 0
            else "PARTIAL_SOURCE_OR_PHYSICAL_LIMITATION"
        )
        self.save_json("81-integrated-final-state.json", final_state)
        print(json.dumps(final_state, indent=2, default=str))
        return final_state


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run structured-text and duplicate-aware full-resolution photo CLASSIFIRE real-report UAT."
        )
    )
    parser.add_argument("--run-id")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()

    root = repo_root()
    _receipt_path, receipt = load_receipt(root, args.run_id)
    controller = IntegratedEvidenceController(
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
        print(f"CLASSIFIRE integrated real-report UAT failed: {exc}", file=sys.stderr)
        return 1
    finally:
        controller.close()


if __name__ == "__main__":
    raise SystemExit(main())
