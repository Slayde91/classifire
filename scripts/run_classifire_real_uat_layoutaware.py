from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from sqlalchemy import select

from classifire.canonical_models import Defect, EvidenceSource
from classifire.db import SessionLocal
from run_classifire_real_uat_defectwise import DefectWiseController, _trim
from run_classifire_real_uat_deterministic import (
    REQUIRED_INTAKE_WRITE_TOOLS,
    _clean_optional_text,
    _confidence,
    _json_from_payload,
)
from run_classifire_real_uat_intake import load_receipt, repo_root


LAYOUT_EVIDENCE_TYPE = "defect_page_layout_review"
PAGE_RENDER_DPI = 180


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class LayoutAwareController(DefectWiseController):
    @staticmethod
    def _compact_evidence_row(item: EvidenceSource) -> dict:
        if item.evidence_type != LAYOUT_EVIDENCE_TYPE:
            return DefectWiseController._compact_evidence_row(item)
        source = item.source_json or {}
        return {
            "evidence_id": item.id,
            "type": item.evidence_type,
            "page": item.page_number,
            "region": item.region_reference,
            "evidence_class": item.evidence_class,
            "confidence": str(item.confidence) if item.confidence is not None else None,
            "association_status": source.get("association_status"),
            "association_confidence": source.get("association_confidence"),
            "association_basis": source.get("association_basis") or [],
            "opening_count": source.get("opening_count"),
            "service_count": source.get("service_count"),
            "openings": source.get("openings") or [],
            "services": source.get("services") or [],
            "relationships": source.get("relationships") or [],
            "physical_facts": source.get("physical_facts") or [],
            "uncertainties": source.get("uncertainties") or [],
        }

    def _render_pages(self, report: Path) -> dict[int, dict[str, object]]:
        try:
            import pymupdf
        except ImportError as exc:
            raise RuntimeError(
                "PyMuPDF is required for layout-aware UAT. Run: python -m pip install -e ."
            ) from exc

        output_dir = self.receipt_dir / "layout-pages"
        output_dir.mkdir(parents=True, exist_ok=True)
        document = pymupdf.open(str(report))
        rendered: dict[int, dict[str, object]] = {}
        try:
            for page_index in range(len(document)):
                page_number = page_index + 1
                output = output_dir / f"page-{page_number:04d}.png"
                if not output.is_file():
                    page = document.load_page(page_index)
                    pixmap = page.get_pixmap(
                        dpi=PAGE_RENDER_DPI,
                        colorspace=pymupdf.csRGB,
                        alpha=False,
                        annots=True,
                    )
                    pixmap.save(str(output))
                rendered[page_number] = {
                    "path": output,
                    "sha256": _sha256(output),
                    "size_bytes": output.stat().st_size,
                }
        finally:
            document.close()
        self.save_json(
            "15-layout-page-render-manifest.json",
            {
                "dpi": PAGE_RENDER_DPI,
                "pages": {
                    str(page): {
                        "path": str(row["path"]),
                        "sha256": row["sha256"],
                        "size_bytes": row["size_bytes"],
                    }
                    for page, row in rendered.items()
                },
            },
        )
        print(f"PASS full-page layout rendering -> {len(rendered)} pages at {PAGE_RENDER_DPI} DPI")
        return rendered

    def _defects_and_direct_pages(self) -> tuple[list[Defect], dict[str, list[int]]]:
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
                    select(EvidenceSource).where(
                        EvidenceSource.estimate_id == self.estimate_id,
                        EvidenceSource.status == "active",
                    )
                ).all()
            )
        pages: dict[str, list[int]] = {}
        for defect in defects:
            values: set[int] = set()
            for item in evidence:
                if item.defect_id != defect.id or item.page_number is None:
                    continue
                try:
                    values.add(int(str(item.page_number).strip()))
                except ValueError:
                    continue
            pages[defect.id] = sorted(values)
        return defects, pages

    def layout_prompt(self, defect: Defect, page_number: int) -> str:
        identity = defect.external_defect_id or defect.defect_code or defect.id
        return f"""You are reviewing ONE complete rendered report page for CLASSIFIRE passive-fire evidence linkage.
Target canonical defect: {identity}
Retained defect description: {_trim(defect.description, 900)}
Retained defect location: {_trim(defect.location, 500)}
Rendered source page: {page_number}

Use the ORIGINAL PAGE LAYOUT visible in the image: defect ID/row text, photo placement, captions, borders,
headings, arrows/leaders and spatial grouping. Determine only what the page itself supports about which visual
content belongs to target defect {identity}. Return ONLY valid JSON, no markdown.

Required schema:
{{
  "target_defect_id": "{identity}",
  "page_number": {page_number},
  "association_status": "SUPPORTED|AMBIGUOUS|NOT_VISIBLE",
  "association_confidence": 0.0,
  "association_basis": [],
  "opening_count": {{"value": null, "status": "confirmed|inferred|unknown", "basis": []}},
  "service_count": {{"value": null, "status": "confirmed|inferred|unknown", "basis": []}},
  "openings": [
    {{
      "label": "opening-1",
      "substrate_type": null,
      "substrate_plane": null,
      "opening_type": null,
      "dimensions": null,
      "evidence_status": "confirmed|inferred|provisional",
      "source_region": null
    }}
  ],
  "services": [
    {{
      "label": "service-1",
      "service_type": null,
      "material": null,
      "size": null,
      "quantity": null,
      "evidence_status": "confirmed|inferred|provisional",
      "source_region": null
    }}
  ],
  "relationships": [],
  "physical_facts": [],
  "uncertainties": []
}}

Hard rules:
- Do not associate a photo with the target merely because it is on the same page. Require layout/content evidence.
- A defect may contain multiple openings and multiple services.
- One photo, row or defect ID does not equal quantity one.
- A visually countable set of distinct services/openings may support a count only when the association to this defect is supported.
- Do not invent hidden services, dimensions, material, substrate plane, FRL, opening boundaries or quantities.
- Proposed-resolution wording does not prove an existing physical service unless the page evidence supports it.
- Do not select a fire-stopping system and do not price anything.
"""

    def _existing_layout_key(self, defect_id: str, page_number: int) -> bool:
        with SessionLocal() as db:
            row = db.scalar(
                select(EvidenceSource.id).where(
                    EvidenceSource.estimate_id == self.estimate_id,
                    EvidenceSource.defect_id == defect_id,
                    EvidenceSource.evidence_type == LAYOUT_EVIDENCE_TYPE,
                    EvidenceSource.page_number == str(page_number),
                ).limit(1)
            )
        return row is not None

    def run_layout_linkage(self, report: Path) -> dict[str, object]:
        rendered = self._render_pages(report)
        defects, defect_pages = self._defects_and_direct_pages()
        session = self.initialize_session("cf-intake-evidence", "15-layout-aware-evidence")
        self.require_tools(
            "cf-intake-evidence",
            session,
            REQUIRED_INTAKE_WRITE_TOOLS,
            "15-layout-aware-effective.json",
        )

        created = 0
        retained = 0
        no_page = 0
        for defect_index, defect in enumerate(defects, start=1):
            identity = defect.external_defect_id or defect.defect_code or defect.id
            pages = defect_pages.get(defect.id) or []
            if not pages:
                no_page += 1
                print(f"LIMIT layout defect {defect_index}/{len(defects)} {identity} -> no directly linked page")
                continue
            for page_number in pages:
                if self._existing_layout_key(defect.id, page_number):
                    retained += 1
                    print(
                        f"PASS layout defect {defect_index}/{len(defects)} {identity} page {page_number} -> retained"
                    )
                    continue
                rendered_row = rendered.get(page_number)
                if rendered_row is None:
                    raise RuntimeError(f"No rendered full-page image exists for page {page_number}")
                payload = self.infer_model(
                    prompt=self.layout_prompt(defect, page_number),
                    receipt_name=f"15-layout-d{defect_index:03d}-p{page_number:03d}",
                    files=[Path(str(rendered_row["path"]))],
                    thinking="medium",
                )
                model = _json_from_payload(
                    payload,
                    context=f"Layout linkage for defect {identity} page {page_number}",
                )
                returned_id = str(model.get("target_defect_id") or "").strip()
                if returned_id != str(identity):
                    raise RuntimeError(
                        f"Layout linkage returned target_defect_id={returned_id!r} for expected {identity!r}"
                    )
                try:
                    returned_page = int(model.get("page_number"))
                except (TypeError, ValueError) as exc:
                    raise RuntimeError(f"Layout linkage for {identity} returned invalid page_number") from exc
                if returned_page != page_number:
                    raise RuntimeError(
                        f"Layout linkage for {identity} returned page {returned_page}, expected {page_number}"
                    )
                association_status = str(model.get("association_status") or "AMBIGUOUS").upper()
                if association_status not in {"SUPPORTED", "AMBIGUOUS", "NOT_VISIBLE"}:
                    association_status = "AMBIGUOUS"
                source_json = {
                    "source": "full_page_layout_vision",
                    "render_dpi": PAGE_RENDER_DPI,
                    "render_sha256": rendered_row["sha256"],
                    "association_status": association_status,
                    "association_confidence": _confidence(model.get("association_confidence"), 0.5),
                    "association_basis": model.get("association_basis") or [],
                    "opening_count": model.get("opening_count"),
                    "service_count": model.get("service_count"),
                    "openings": model.get("openings") or [],
                    "services": model.get("services") or [],
                    "relationships": model.get("relationships") or [],
                    "physical_facts": model.get("physical_facts") or [],
                    "uncertainties": model.get("uncertainties") or [],
                }
                observation = {
                    "stored_file_id": self.stored_file_id,
                    "evidence_type": LAYOUT_EVIDENCE_TYPE,
                    "external_defect_id": defect.external_defect_id or defect.defect_code,
                    "source_reference": self.report_name,
                    "page_number": str(page_number),
                    "region_reference": f"page-layout:{page_number}:defect:{identity}",
                    "evidence_class": "observed",
                    "confidence": source_json["association_confidence"],
                    "source_json": source_json,
                }
                self.register_observations(
                    session,
                    [observation],
                    f"15-layout-d{defect_index:03d}-p{page_number:03d}-register.json",
                )
                created += 1
                print(
                    f"PASS layout defect {defect_index}/{len(defects)} {identity} page {page_number} "
                    f"-> {association_status.lower()}"
                )

        result = {
            "defect_count": len(defects),
            "layout_observations_created": created,
            "layout_observations_retained": retained,
            "defects_without_direct_page": no_page,
        }
        self.save_json("15-layout-aware-summary.json", result)
        return result

    def run(self) -> dict:
        print("CLASSIFIRE layout-aware real-report physical-model UAT")
        print(f"Run ID: {self.run_id}")
        print(f"Estimate ID: {self.estimate_id}")
        print(f"Receipts: {self.receipt_dir}")
        self.preflight()
        manifest = self.stage_visuals()
        intake_report = self.workspace_report("cf-intake-evidence")
        intake_state = self.run_windows_safe_intake(intake_report, manifest)
        layout_state = self.run_layout_linkage(intake_report)
        final_state = self.run_defectwise_physical()
        final_state["run_id"] = self.run_id
        final_state["intake_coverage_ok"] = intake_state["coverage_ok"]
        final_state["layout_evidence"] = layout_state
        final_state["status"] = (
            "PHYSICAL_MODEL_LOCKED"
            if final_state["physical_lock_count"] > 0
            else "PARTIAL_SOURCE_OR_PHYSICAL_LIMITATION"
        )
        self.save_json("61-layout-aware-final-state.json", final_state)
        print(json.dumps(final_state, indent=2, default=str))
        return final_state


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run layout-aware CLASSIFIRE real-report physical-model UAT."
    )
    parser.add_argument("--run-id")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()

    root = repo_root()
    _receipt_path, receipt = load_receipt(root, args.run_id)
    controller = LayoutAwareController(
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
        print(f"CLASSIFIRE layout-aware real-report UAT failed: {exc}", file=sys.stderr)
        return 1
    finally:
        controller.close()


if __name__ == "__main__":
    raise SystemExit(main())
