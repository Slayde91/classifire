from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from pypdf import PdfReader
from sqlalchemy import select

from classifire.canonical_models import Defect, EvidenceSource
from classifire.db import SessionLocal
from run_classifire_real_uat_deterministic import (
    DeterministicController,
    REQUIRED_INTAKE_WRITE_TOOLS,
    REQUIRED_PHYSICAL_WRITE_TOOLS,
    _clean_optional_text,
    _confidence,
    _json_from_payload,
    _scope_observation,
)
from run_classifire_real_uat_intake import load_receipt, repo_root


# Keep every OpenClaw `infer model run --prompt ...` call comfortably below
# Windows CreateProcess command-line limits. Evidence is split, never truncated.
TEXT_CHUNK_CHARS = 6000
MAX_IMAGE_FILES_PER_CALL = 4
REGISTER_OBSERVATIONS_PER_CALL = 8
MAX_FINAL_PHYSICAL_EVIDENCE_CHARS = 7000
MAX_REDUCTION_PASSES = 3


def _split_text(value: str, max_chars: int = TEXT_CHUNK_CHARS) -> list[str]:
    text = value.strip()
    if not text:
        return ["[NO EXTRACTABLE TEXT]"]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            boundary = text.rfind("\n", start, end)
            if boundary <= start + max_chars // 2:
                boundary = text.rfind(" ", start, end)
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = max(end, start + 1)
    return chunks or ["[NO EXTRACTABLE TEXT]"]


def _trim_text(value: object, limit: int = 500) -> str | None:
    text = _clean_optional_text(value)
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


class WindowsSafeController(DeterministicController):
    def page_chunk_prompt(
        self,
        *,
        page_number: int,
        chunk_number: int,
        chunk_count: int,
        extracted_text: str,
    ) -> str:
        return f"""You are performing source-preserving passive-fire evidence review for CLASSIFIRE.
Analyze ONLY extracted text chunk {chunk_number} of {chunk_count} from PDF page {page_number}.
Embedded images are analyzed separately; never infer image content from text. Return ONLY valid JSON,
no markdown and no commentary.

--- PAGE {page_number} TEXT CHUNK {chunk_number}/{chunk_count} ---
{extracted_text}
--- END CHUNK ---

Required schema:
{{
  "page_number": {page_number},
  "chunk_summary": "concise factual summary",
  "scope_relevant": true,
  "confidence": 0.0,
  "scope_observations": [
    {{
      "external_defect_id": null,
      "defect_code": null,
      "description": "factual report observation",
      "location": null,
      "classification": null,
      "region_reference": "table/row/section reference if supported",
      "evidence_class": "observed",
      "confidence": 0.0,
      "physical_facts": [],
      "uncertainties": []
    }}
  ]
}}

Rules:
- One row or defect ID does NOT imply one Service, Opening, repair, or quantity one.
- Do not choose technical systems or pricing.
- Do not invent hidden services, dimensions, materials, substrate planes, quantities, defect IDs, or locations.
- Preserve uncertainty explicitly, including extraction/layout uncertainty.
"""

    def _analyse_page_text(self, report: Path, page_number: int) -> list[dict]:
        reader = PdfReader(str(report))
        if page_number < 1 or page_number > len(reader.pages):
            raise RuntimeError(f"Requested page {page_number} is outside the PDF page range")
        try:
            extracted = reader.pages[page_number - 1].extract_text() or ""
        except Exception as exc:
            raise RuntimeError(f"Unable to extract text from PDF page {page_number}: {exc}") from exc

        chunks = _split_text(extracted)
        summaries: list[str] = []
        scope_rows: list[dict] = []
        confidences: list[float] = []
        relevant = False

        for index, chunk in enumerate(chunks, start=1):
            payload = self.infer_model(
                prompt=self.page_chunk_prompt(
                    page_number=page_number,
                    chunk_number=index,
                    chunk_count=len(chunks),
                    extracted_text=chunk,
                ),
                receipt_name=f"10-win-p{page_number:03d}-c{index:03d}",
                thinking="medium",
            )
            analysis = _json_from_payload(
                payload,
                context=f"Page {page_number} text chunk {index}",
            )
            try:
                returned_page = int(analysis.get("page_number"))
            except (TypeError, ValueError) as exc:
                raise RuntimeError(
                    f"Page {page_number} chunk {index} returned no valid page_number"
                ) from exc
            if returned_page != page_number:
                raise RuntimeError(
                    f"Page {page_number} chunk {index} returned page_number={returned_page}"
                )
            summary = _trim_text(analysis.get("chunk_summary"), 700)
            if summary:
                summaries.append(summary)
            relevant = relevant or analysis.get("scope_relevant") is True
            confidences.append(_confidence(analysis.get("confidence"), 0.75))
            rows = analysis.get("scope_observations") or []
            if isinstance(rows, list):
                scope_rows.extend(item for item in rows if isinstance(item, dict))

        page_summary = " | ".join(summaries) or "Reviewed; no extractable page text."
        if len(page_summary) > 2200:
            page_summary = page_summary[:2197] + "..."
        page_confidence = sum(confidences) / len(confidences) if confidences else 0.7

        observations: list[dict] = [
            {
                "stored_file_id": self.stored_file_id,
                "evidence_type": "report_page_review",
                "source_reference": self.report_name,
                "page_number": str(page_number),
                "region_reference": f"page:{page_number}",
                "evidence_class": "observed",
                "confidence": page_confidence,
                "source_json": {
                    "source": "openclaw_infer_chunked_page_text",
                    "text_chunk_count": len(chunks),
                    "page_summary": page_summary,
                    "scope_relevant": relevant,
                    "chunk_summaries": summaries,
                },
            }
        ]
        for item in scope_rows:
            observations.append(
                _scope_observation(
                    page_number,
                    item,
                    self.report_name,
                    self.stored_file_id,
                )
            )
        return observations

    def _analyse_images(self, report: Path, rows: list[dict], page_number: int) -> list[dict]:
        observations: list[dict] = []
        for start in range(0, len(rows), MAX_IMAGE_FILES_PER_CALL):
            batch = rows[start : start + MAX_IMAGE_FILES_PER_CALL]
            files = [report.parent / "visuals" / str(row["filename"]) for row in batch]
            payload = self.infer_model(
                prompt=self.image_analysis_prompt(batch),
                receipt_name=(
                    f"10-win-p{page_number:03d}-images-"
                    f"{start + 1:03d}-{start + len(batch):03d}"
                ),
                files=files,
                thinking="low",
            )
            analysis = _json_from_payload(payload, context=f"Page {page_number} image batch")
            model_rows = analysis.get("images")
            if not isinstance(model_rows, list) or len(model_rows) != len(batch):
                raise RuntimeError(
                    f"Page {page_number} image batch returned "
                    f"{len(model_rows) if isinstance(model_rows, list) else 'no'} rows for "
                    f"{len(batch)} images"
                )
            for source_row, model_row in zip(batch, model_rows, strict=True):
                if not isinstance(model_row, dict):
                    raise RuntimeError(f"Page {page_number} image analysis returned a non-object row")
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
                            "source": "openclaw_infer_image_input",
                            "filename": source_row["filename"],
                            "sha256": source_row["sha256"],
                            "visible_summary": _trim_text(model_row.get("visible_summary"), 900)
                            or "Reviewed",
                            "scope_relevance": _clean_optional_text(
                                model_row.get("scope_relevance")
                            )
                            or "uncertain",
                            "physical_facts": model_row.get("physical_facts") or [],
                            "uncertainties": model_row.get("uncertainties") or [],
                        },
                    }
                )
        return observations

    def _register_small_batches(
        self,
        session_key: str,
        observations: list[dict],
        prefix: str,
    ) -> None:
        for index, start in enumerate(
            range(0, len(observations), REGISTER_OBSERVATIONS_PER_CALL),
            start=1,
        ):
            self.register_observations(
                session_key,
                observations[start : start + REGISTER_OBSERVATIONS_PER_CALL],
                f"{prefix}-register-{index:03d}.json",
            )

    def run_windows_safe_intake(self, report: Path, manifest: dict) -> dict:
        missing_pages, missing_images = self.coverage_gaps(manifest)
        if not missing_pages and not missing_images:
            print("PASS Windows-safe intake coverage already complete")
            return self.verify_intake_coverage(manifest)

        session = self.initialize_session("cf-intake-evidence", "10-windows-safe-intake")
        self.require_tools(
            "cf-intake-evidence",
            session,
            REQUIRED_INTAKE_WRITE_TOOLS,
            "10-windows-safe-intake-effective.json",
        )

        page_count = int(manifest["page_count"])
        for page in range(1, page_count + 1):
            missing_pages, missing_images = self.coverage_gaps(manifest)
            need_page = f"page:{page}" in missing_pages
            image_rows = [
                row
                for row in manifest["images"]
                if int(row["page_number"]) == page
                and f"image:{row['filename']}" in missing_images
            ]
            if not need_page and not image_rows:
                print(f"PASS Windows-safe intake page {page}/{page_count} -> retained")
                continue

            observations: list[dict] = []
            if need_page:
                observations.extend(self._analyse_page_text(report, page))
            if image_rows:
                observations.extend(self._analyse_images(report, image_rows, page))
            self._register_small_batches(
                session,
                observations,
                f"10-win-p{page:03d}",
            )

            after_pages, after_images = self.coverage_gaps(manifest)
            page_missing = f"page:{page}" in after_pages
            images_missing = [
                row["filename"]
                for row in manifest["images"]
                if int(row["page_number"]) == page
                and f"image:{row['filename']}" in after_images
            ]
            if page_missing or images_missing:
                raise RuntimeError(
                    f"Windows-safe intake page {page} did not persist complete coverage. "
                    f"page_missing={page_missing}; images_missing={images_missing}"
                )
            print(
                f"PASS Windows-safe intake page {page}/{page_count} -> "
                f"images {len(image_rows)}"
            )

        return self.verify_intake_coverage(manifest)

    def _compact_physical_evidence(self) -> str:
        with SessionLocal() as db:
            defects = list(
                db.scalars(
                    select(Defect).where(Defect.estimate_id == self.estimate_id)
                ).all()
            )
            evidence = list(
                db.scalars(
                    select(EvidenceSource)
                    .where(EvidenceSource.estimate_id == self.estimate_id)
                    .order_by(EvidenceSource.page_number, EvidenceSource.created_at)
                ).all()
            )

        rows: list[dict] = []
        for item in evidence:
            source = item.source_json or {}
            if item.evidence_type == "report_page_review":
                if source.get("scope_relevant") is False:
                    continue
                rows.append(
                    {
                        "type": "page",
                        "page": item.page_number,
                        "summary": _trim_text(source.get("page_summary"), 450),
                    }
                )
            elif item.evidence_type == "report_image_review":
                relevance = str(source.get("scope_relevance") or "uncertain").lower()
                if relevance == "non_scope":
                    continue
                rows.append(
                    {
                        "type": "image",
                        "page": item.page_number,
                        "region": item.region_reference,
                        "summary": _trim_text(source.get("visible_summary"), 450),
                        "physical_facts": source.get("physical_facts") or [],
                        "uncertainties": source.get("uncertainties") or [],
                    }
                )
            elif item.evidence_type in {"defect_report_entry", "scope_observation"}:
                rows.append(
                    {
                        "type": item.evidence_type,
                        "page": item.page_number,
                        "region": item.region_reference,
                        "defect_id": item.defect_id,
                        "physical_facts": source.get("physical_facts") or [],
                        "uncertainties": source.get("uncertainties") or [],
                        "raw": source.get("raw_model_item") or source,
                    }
                )

        payload = {
            "defects": [
                {
                    "id": defect.id,
                    "external_defect_id": defect.external_defect_id,
                    "defect_code": defect.defect_code,
                    "description": _trim_text(defect.description, 700),
                    "location": _trim_text(defect.location, 400),
                    "classification": defect.classification,
                }
                for defect in defects
            ],
            "evidence": rows,
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)

    def physical_reduction_prompt(self, chunk: str, part: int, total: int) -> str:
        return f"""Extract only evidence-supported passive-fire physical facts from canonical CLASSIFIRE
evidence part {part} of {total}. Return ONLY valid JSON, no markdown.

EVIDENCE PART:
{chunk}

Required schema:
{{"facts":[{{"external_defect_id":null,"location":null,"opening_facts":[],"service_facts":[],"source_refs":[],"uncertainties":[]}}],"limitations":[]}}

Rules:
- Do not invent quantities, materials, dimensions, substrate planes, FRL, services, or openings.
- One photo/row/defect ID does not imply quantity one.
- Preserve uncertainty and source references.
- This is fact extraction only, not Package 15 selection or pricing.
"""

    def _reduce_physical_evidence(self, evidence_text: str) -> str:
        current = evidence_text
        for reduction_pass in range(1, MAX_REDUCTION_PASSES + 1):
            if len(current) <= MAX_FINAL_PHYSICAL_EVIDENCE_CHARS:
                return current
            chunks = _split_text(current, TEXT_CHUNK_CHARS)
            facts: list[object] = []
            limitations: list[object] = []
            for index, chunk in enumerate(chunks, start=1):
                payload = self.infer_model(
                    prompt=self.physical_reduction_prompt(
                        chunk,
                        index,
                        len(chunks),
                    ),
                    receipt_name=(
                        f"20-win-reduce-p{reduction_pass:02d}-c{index:03d}"
                    ),
                    thinking="medium",
                )
                analysis = _json_from_payload(
                    payload,
                    context=f"Physical evidence reduction {reduction_pass}/{index}",
                )
                if isinstance(analysis.get("facts"), list):
                    facts.extend(analysis["facts"])
                if isinstance(analysis.get("limitations"), list):
                    limitations.extend(analysis["limitations"])
            # Deterministic de-duplication by canonical JSON representation.
            seen: set[str] = set()
            deduped: list[object] = []
            for fact in facts:
                key = json.dumps(fact, sort_keys=True, separators=(",", ":"), default=str)
                if key not in seen:
                    seen.add(key)
                    deduped.append(fact)
            current = json.dumps(
                {"facts": deduped, "limitations": limitations},
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            )
        if len(current) > MAX_FINAL_PHYSICAL_EVIDENCE_CHARS:
            raise RuntimeError(
                "Physical evidence remains too large for a Windows-safe final synthesis after "
                f"{MAX_REDUCTION_PASSES} loss-controlled reduction passes. No model was submitted."
            )
        return current

    def run_windows_safe_physical(self) -> dict:
        existing = self.inspect_state()
        if existing["physical_lock_count"] > 0:
            print("PASS physical model already locked in retained canonical state")
            return existing
        if existing["opening_count"] or existing["service_count"]:
            report = self.workspace_report("cf-physical-model")
            return self.run_physical(report)

        session = self.initialize_session("cf-physical-model", "20-windows-safe-physical")
        self.require_tools(
            "cf-physical-model",
            session,
            REQUIRED_PHYSICAL_WRITE_TOOLS,
            "20-windows-safe-physical-effective.json",
        )
        # Retain an auditable canonical evidence-read receipt under the physical role.
        self.invoke_tool(
            "cf-physical-model",
            session,
            "classifire_evidence_read",
            {"estimate_id": self.estimate_id},
            "20-windows-safe-evidence-read.json",
        )

        compact = self._reduce_physical_evidence(self._compact_physical_evidence())
        self.save_text("20-windows-safe-compact-evidence.json", compact)
        synthesis = self.infer_model(
            prompt=self.physical_model_prompt(compact),
            receipt_name="20-windows-safe-physical-synthesis",
            thinking="high",
        )
        model = _json_from_payload(synthesis, context="Windows-safe physical-model synthesis")
        status = str(model.get("status") or "").strip().upper()
        if status == "INSUFFICIENT_EVIDENCE":
            self.save_json("20-windows-safe-physical-limitation.json", model)
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
            except (TypeError, ValueError) as exc:
                raise RuntimeError(f"Service {code} has no explicit numeric quantity") from exc
            if quantity <= 0:
                raise RuntimeError(f"Service {code} quantity must be greater than zero")

        self.invoke_tool(
            "cf-physical-model",
            session,
            "classifire_submit_initial_physical_model",
            {"estimate_id": self.estimate_id, "openings": openings, "services": services},
            "20-windows-safe-physical-submit.json",
        )
        self.invoke_tool(
            "cf-physical-model",
            session,
            "classifire_lock_physical_model",
            {
                "estimate_id": self.estimate_id,
                "reason": "Windows-safe deterministic real-UAT lock after evidence-backed synthesis",
            },
            "20-windows-safe-physical-lock.json",
            require_ok=False,
        )
        return self.inspect_state()

    def run(self) -> dict:
        print("CLASSIFIRE Windows-safe deterministic real-report UAT")
        print(f"Run ID: {self.run_id}")
        print(f"Estimate ID: {self.estimate_id}")
        print(f"Receipts: {self.receipt_dir}")
        self.preflight()
        manifest = self.stage_visuals()
        intake_report = self.workspace_report("cf-intake-evidence")
        intake_state = self.run_windows_safe_intake(intake_report, manifest)
        final_state = self.run_windows_safe_physical()
        final_state["run_id"] = self.run_id
        final_state["intake_coverage_ok"] = intake_state["coverage_ok"]
        final_state["status"] = (
            "PHYSICAL_MODEL_LOCKED"
            if final_state["physical_lock_count"] > 0
            else "PARTIAL_SOURCE_OR_PHYSICAL_LIMITATION"
        )
        self.save_json("41-windows-safe-final-state.json", final_state)
        print(json.dumps(final_state, indent=2, default=str))
        return final_state


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run Windows-safe chunked CLASSIFIRE real-report intake and physical-model acceptance."
        )
    )
    parser.add_argument("--run-id")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()

    root = repo_root()
    _receipt_path, receipt = load_receipt(root, args.run_id)
    controller = WindowsSafeController(
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
        print(f"CLASSIFIRE Windows-safe real-report UAT failed: {exc}", file=sys.stderr)
        return 1
    finally:
        controller.close()


if __name__ == "__main__":
    raise SystemExit(main())
