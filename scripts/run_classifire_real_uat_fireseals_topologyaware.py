from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import select

from classifire.canonical_models import Defect, EvidenceSource
from classifire.db import SessionLocal
from run_classifire_real_uat_deterministic import _json_from_payload
from run_classifire_real_uat_fireseals_blankaware import (
    BlankAwareFireSealFocusedController,
    _model_completeness_issues,
)
from run_classifire_real_uat_intake import load_receipt, repo_root


TOPOLOGY_POLICY_VERSION = "CLASSIFIRE-FIRESEAL-PHYSICAL-v5-DIRECT-IMAGE-TOPOLOGY"
MAX_DETAIL_IMAGES = 12
MAX_PAGE_IMAGES = 3


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class TopologyAwareFireSealController(BlankAwareFireSealFocusedController):
    """Reconstruct Opening/Service topology from the actual retained images.

    Previous UAT stages compressed image understanding into text evidence and then
    asked later models to reconstruct topology from those summaries. This runner
    deliberately restores the original visual evidence at the physical-model stage.
    The human-reviewed regression fixture is not read or used by this class.
    """

    def _direct_evidence(self, defect: Defect) -> list[EvidenceSource]:
        with SessionLocal() as db:
            return list(
                db.scalars(
                    select(EvidenceSource).where(
                        EvidenceSource.estimate_id == self.estimate_id,
                        EvidenceSource.defect_id == defect.id,
                        EvidenceSource.status == "active",
                    )
                ).all()
            )

    def _photo_inventory(self) -> dict[str, dict[str, Any]]:
        path = self.receipt_dir / "16-photo-inventory.json"
        if not path.is_file():
            raise RuntimeError(
                "Retained photo inventory is missing; topology-aware physical synthesis "
                "requires the original staged visual evidence."
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        photos = payload.get("photos") or []
        return {
            str(row.get("photo_id")): row
            for row in photos
            if isinstance(row, dict) and str(row.get("photo_id") or "").strip()
        }

    def _visual_files_for_defect(
        self,
        defect_index: int,
        defect: Defect,
    ) -> tuple[list[Path], list[dict[str, Any]]]:
        evidence = self._direct_evidence(defect)
        inventory = self._photo_inventory()
        photo_ids: list[str] = []
        pages: set[int] = set()

        for item in evidence:
            source = item.source_json or {}
            if item.page_number is not None:
                try:
                    pages.add(int(str(item.page_number).strip()))
                except ValueError:
                    pass
            if item.evidence_type == "defect_photo_detail_review":
                value = str(source.get("photo_id") or "").strip()
                if value:
                    photo_ids.append(value)
            elif item.evidence_type == "defect_page_photo_linkage_review":
                photo_ids.extend(str(x) for x in (source.get("associated_photo_ids") or []))
                photo_ids.extend(str(x) for x in (source.get("uncertain_photo_ids") or []))
            elif item.evidence_type == "defect_photo_reconciliation":
                for group in source.get("photo_groups") or []:
                    if isinstance(group, dict):
                        photo_ids.extend(str(x) for x in (group.get("photo_ids") or []))

        photo_ids = list(dict.fromkeys(item for item in photo_ids if item in inventory))
        files: list[Path] = []
        manifest: list[dict[str, Any]] = []
        seen_visual_digests: set[str] = set()

        contact = self.receipt_dir / "photo-contact-sheets" / f"defect-{defect_index:03d}.png"
        if contact.is_file():
            files.append(contact)
            manifest.append({"role": "contact_sheet", "path": str(contact)})

        for page in sorted(pages)[:MAX_PAGE_IMAGES]:
            labelled = self.receipt_dir / "photo-layout-labelled" / f"page-{page:04d}-labelled.png"
            if labelled.is_file():
                files.append(labelled)
                manifest.append({"role": "labelled_full_page", "page": page, "path": str(labelled)})

        detail_count = 0
        for photo_id in photo_ids:
            if detail_count >= MAX_DETAIL_IMAGES:
                break
            row = inventory[photo_id]
            digest = str(row.get("digest") or "").strip()
            if digest and digest in seen_visual_digests:
                continue
            if digest:
                seen_visual_digests.add(digest)

            zoom = self.receipt_dir / "photo-zoom" / f"{photo_id}-zoom.png"
            native_raw = str(row.get("native_path") or "").strip()
            native = Path(native_raw) if native_raw else None
            chosen = zoom if zoom.is_file() else native if native is not None and native.is_file() else None
            if chosen is None:
                continue
            files.append(chosen)
            manifest.append(
                {
                    "role": "defect_photo",
                    "photo_id": photo_id,
                    "page": row.get("page_number"),
                    "digest": digest or None,
                    "path": str(chosen),
                }
            )
            detail_count += 1

        if not any(row.get("role") == "defect_photo" for row in manifest):
            raise RuntimeError(
                f"No retained high-resolution defect photos are available for "
                f"{defect.external_defect_id or defect.id}"
            )
        return files, manifest

    def _visual_cache_key(self, bundle: str, files: list[Path]) -> dict[str, Any]:
        return {
            "policy_version": TOPOLOGY_POLICY_VERSION,
            "bundle_sha256": hashlib.sha256(bundle.encode("utf-8")).hexdigest(),
            "visual_files": [
                {"name": path.name, "sha256": _sha256(path)} for path in files if path.is_file()
            ],
        }

    def _cached_topology_model(
        self,
        defect_index: int,
        bundle: str,
        files: list[Path],
    ) -> dict | None:
        cache_path = self.receipt_dir / f"20-topology-defect-{defect_index:03d}-cache.json"
        final_path = self.receipt_dir / f"20-topology-defect-{defect_index:03d}-final.json"
        if not cache_path.is_file() or not final_path.is_file():
            return None
        try:
            cached_key = json.loads(cache_path.read_text(encoding="utf-8"))
            model = json.loads(final_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if cached_key != self._visual_cache_key(bundle, files):
            return None
        if (
            str(model.get("status") or "").strip().upper() == "MODEL_SUPPORTED"
            and not _model_completeness_issues(model)
        ):
            print(f"PASS defect {defect_index} topology cache -> retained direct-image proposal")
            return model
        return None

    def defect_physical_prompt(self, defect: Defect, evidence_text: str) -> str:
        base = super().defect_physical_prompt(defect, evidence_text)
        return base + f"""

Binding direct-image topology policy ({TOPOLOGY_POLICY_VERSION}):
The attached files include the actual report page/contact sheet and high-resolution defect photographs.
They are PRIMARY evidence for physical topology. Earlier AI photo summaries/reconciliation are secondary aids
and must be corrected when the attached images show more detail.

Before producing the JSON result, reconstruct the physical topology in this order:
1. VIEW RECONCILIATION — decide which photographs are different angles/opposite faces of the same defect area.
2. BARRIER PLANES — identify each distinct wall/slab/floor/soffit barrier plane visible or defensibly inferred.
3. OPENINGS — identify each distinct physical aperture/core hole through each barrier. Count holes, not Services.
4. SERVICES — inventory every distinct Service or homogeneous Service group passing through each Opening.
5. RELATIONSHIPS — map each Service/group to its actual Opening. Multiple unlike Services may share one Opening.

Mandatory topology rules:
- NEVER create one Opening per Service type. A PVC pipe, PEX pipes and a cable bundle can all share one Opening.
- NEVER create one Opening per photograph. Multiple photographs may be alternate angles or opposite barrier faces.
- A physically separate hole/core is a separate Opening even when close to another hole.
- A single defect may contain Openings through DIFFERENT barrier planes; for example one wall Opening and one slab Opening.
- A redundant/empty core is `blank_core_hole` with zero Services.
- A Service Opening is `service_penetration` and may contain one or many Services/service groups.
- Use a Service row for a homogeneous physical group when appropriate: e.g. two similar PEX pipes in the same
  Opening may be one Service row with quantity 2; two similar conduits may be one conduit row with quantity 2.
- Treat an identifiable cable bundle as one `cable_bundle` Service group unless individual cable treatment is physically required.
- Do NOT combine unlike Services into one generic row. PVC, PEX, copper, metal pipe, conduit, cable/cable bundle,
  flexible duct and air-conditioning bundle are distinct service classes.
- service_type may therefore use `pipe`, `cable`, `cable_bundle`, `conduit`, `duct`, `flexible_duct`,
  `aircon_bundle`, `mixed` or `other` as physically appropriate.
- You may infer service class/material provisionally from visible colour, rigidity, fittings, insulation and form when
  the photographs provide a rational basis. Record that basis in notes and use provisional/inferred evidence status.
- Proposed-resolution text is corroborating clue only. It must not create a Service, Opening or count that the
  physical evidence does not support.
- Use photos to make defensible provisional substrate_type, substrate_plane and orientation assumptions when text is silent.
- Missing FRL follows the existing governed `-/120/120` estimating-assumption policy.
- If exact count is visually approximate, choose the most defensible physical estimate and label it provisional;
  do not discard clearly visible Services merely because exact dimensions are unavailable.

Return only the existing required physical-model JSON schema from the parent prompt. Do not include reasoning prose.
"""

    def _topology_retry_prompt(
        self,
        defect: Defect,
        bundle: str,
        first_model: dict,
        issues: list[str] | None = None,
    ) -> str:
        return self.defect_physical_prompt(defect, bundle) + f"""

The first direct-image topology pass was incomplete or internally inconsistent.
Issues: {json.dumps(issues or first_model.get('limitations') or [], ensure_ascii=False, separators=(',', ':'))}

Reinspect ALL attached visual files together. Explicitly challenge these failure modes before returning the final JSON:
- separate Services incorrectly turned into separate Openings;
- different angles/opposite faces incorrectly turned into separate defects/openings;
- separate physical holes accidentally merged;
- blank core holes given invented Services;
- visible service classes omitted because earlier text summaries were uncertain;
- proposed-resolution quantities substituted for physical visual counts.
Return MODEL_SUPPORTED when a rational provisional topology can be reconstructed from the actual images.
"""

    def _synthesise_defect(
        self,
        defect_index: int,
        defect: Defect,
        bundle: str,
    ) -> dict:
        files, manifest = self._visual_files_for_defect(defect_index, defect)
        self.save_json(f"20-topology-defect-{defect_index:03d}-visual-manifest.json", manifest)
        cached = self._cached_topology_model(defect_index, bundle, files)
        if cached is not None:
            return cached

        payload = self.infer_model(
            prompt=self.defect_physical_prompt(defect, bundle),
            receipt_name=f"20-topology-defect-{defect_index:03d}-synthesis",
            files=files,
            thinking="high",
        )
        model = _json_from_payload(
            payload,
            context=f"Direct-image topology synthesis for defect {defect.external_defect_id or defect.id}",
        )
        status = str(model.get("status") or "").strip().upper()
        issues = _model_completeness_issues(model) if status == "MODEL_SUPPORTED" else []

        if status == "INSUFFICIENT_EVIDENCE" or issues:
            retry = self.infer_model(
                prompt=self._topology_retry_prompt(defect, bundle, model, issues),
                receipt_name=f"20-topology-defect-{defect_index:03d}-retry",
                files=files,
                thinking="high",
            )
            model = _json_from_payload(
                retry,
                context=f"Direct-image topology retry for defect {defect.external_defect_id or defect.id}",
            )
            status = str(model.get("status") or "").strip().upper()
            issues = _model_completeness_issues(model) if status == "MODEL_SUPPORTED" else []

        if status == "MODEL_SUPPORTED" and issues:
            return {
                "status": "INSUFFICIENT_EVIDENCE",
                "limitations": issues,
                "openings": [],
                "services": [],
            }

        if status == "MODEL_SUPPORTED":
            self.save_json(f"20-topology-defect-{defect_index:03d}-final.json", model)
            self.save_json(
                f"20-topology-defect-{defect_index:03d}-cache.json",
                self._visual_cache_key(bundle, files),
            )
        return model


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild CLASSIFIRE fire-seal/penetration physical topology using the actual "
            "retained high-resolution defect photographs at the final physical-model stage."
        )
    )
    parser.add_argument("--run-id")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()

    root = repo_root()
    _receipt_path, receipt = load_receipt(root, args.run_id)
    controller = TopologyAwareFireSealController(
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
        print(f"CLASSIFIRE topology-aware real-report UAT failed: {exc}", file=sys.stderr)
        return 1
    finally:
        controller.close()


if __name__ == "__main__":
    raise SystemExit(main())
