from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from run_classifire_real_uat_deterministic import _json_from_payload
from run_classifire_real_uat_fireseals_blankaware import (
    BlankAwareFireSealFocusedController,
    _model_completeness_issues,
)
from run_classifire_real_uat_intake import load_receipt, repo_root
from run_classifire_real_uat_photoaware import (
    IMAGE_VARIANT_INVENTORY_RECEIPT,
    LINKED_PHOTO_INVENTORY_RECEIPT,
    PHOTO_DETAIL_EVIDENCE_TYPE,
    PHOTO_LINK_EVIDENCE_TYPE,
    PHOTO_RECONCILIATION_EVIDENCE_TYPE,
)
from sqlalchemy import select

from classifire.canonical_models import Defect, EvidenceSource
from classifire.db import SessionLocal
from classifire.services.image_variant_resolution import load_image_variant_resolution

TOPOLOGY_POLICY_VERSION = (
    "CLASSIFIRE-FIRESEAL-PHYSICAL-v7-HIGHEST-USABLE-DETAIL-TOPOLOGY"
)
MAX_DETAIL_IMAGES = 36
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

    def _validated_image_variant_resolution(self):
        linked_path = self.receipt_dir / LINKED_PHOTO_INVENTORY_RECEIPT
        variant_path = self.receipt_dir / IMAGE_VARIANT_INVENTORY_RECEIPT
        if not linked_path.is_file() or not variant_path.is_file():
            raise RuntimeError(
                "Topology synthesis requires verified 16b and 16c image inventories."
            )
        variant_sha256 = _sha256(variant_path)
        cached = getattr(self, "_image_variant_resolution_cache", None)
        if (
            cached is not None
            and str(getattr(self, "_image_variant_receipt_sha256_cache", ""))
            == variant_sha256
        ):
            return cached
        result = load_image_variant_resolution(
            variant_path,
            artifact_root=self.receipt_dir,
            expected_report_sha256=str(self.receipt["report_sha256"]),
            expected_inventory_sha256=_sha256(linked_path),
        )
        self._image_variant_resolution_cache = result
        self._image_variant_receipt_sha256_cache = variant_sha256
        return result

    def _compact_evidence_row(self, item: EvidenceSource) -> dict:
        """Omit stale low-resolution conclusions without mutating retained evidence.

        Old photo evidence still contributes routing identifiers, allowing the fresh
        linked/variant pixels to be selected. Its visual conclusions cannot enter the
        proposal bundle unless they are bound to the current 16c receipt.
        """

        compact = super()._compact_evidence_row(item)
        if item.evidence_type not in {
            PHOTO_LINK_EVIDENCE_TYPE,
            PHOTO_DETAIL_EVIDENCE_TYPE,
            PHOTO_RECONCILIATION_EVIDENCE_TYPE,
        }:
            return compact
        source = item.source_json or {}
        current = self._image_variant_receipt_sha256()
        if str(source.get("image_variant_receipt_sha256") or "").lower() == current.lower():
            return compact

        routing: dict[str, Any] = {
            "evidence_id": item.id,
            "type": item.evidence_type,
            "page": item.page_number,
            "region": item.region_reference,
            "stale_visual_conclusions_omitted": True,
            "current_image_variant_receipt_sha256": current,
        }
        if item.evidence_type == PHOTO_LINK_EVIDENCE_TYPE:
            photo_ids: list[str] = []
            for key in (
                "associated_photo_ids",
                "uncertain_photo_ids",
                "ignored_photo_ids",
            ):
                photo_ids.extend(str(value) for value in (source.get(key) or []))
            routing["photo_ids_for_re_review"] = list(
                dict.fromkeys(value for value in photo_ids if value)
            )
        elif item.evidence_type == PHOTO_DETAIL_EVIDENCE_TYPE:
            routing["photo_id"] = source.get("photo_id")
        else:
            photo_ids: list[str] = []
            for group in source.get("photo_groups") or []:
                if isinstance(group, dict):
                    photo_ids.extend(str(value) for value in (group.get("photo_ids") or []))
            photo_ids.extend(str(value) for value in (source.get("photo_ids_reviewed") or []))
            photo_ids.extend(str(value) for value in (source.get("ignored_photo_ids") or []))
            routing["photo_ids"] = list(dict.fromkeys(value for value in photo_ids if value))
        return routing

    def _photo_inventory(self) -> dict[str, dict[str, Any]]:
        path = self.receipt_dir / LINKED_PHOTO_INVENTORY_RECEIPT
        if not path.is_file():
            raise RuntimeError(
                "Linked-photo inventory is missing; topology-aware physical synthesis "
                "requires the verified filesystem-only materialization stage."
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("Linked-photo inventory must be a JSON object.")
        if payload.get("schema") != "CLASSIFIRE-LINKED-PHOTO-INVENTORY-v1":
            raise RuntimeError("Linked-photo inventory schema is unsupported.")
        if str(payload.get("report_sha256") or "").lower() != str(
            self.receipt["report_sha256"]
        ).lower():
            raise RuntimeError("Linked-photo inventory is bound to a different report.")
        if payload.get("materialization_ok") is not True:
            raise RuntimeError("Linked-photo inventory materialization is not verified.")
        if payload.get("cache_verification_ok") is not True:
            raise RuntimeError("Linked-photo inventory cache verification is not complete.")
        photos = payload.get("photos") or []
        if not isinstance(photos, list):
            raise RuntimeError("Linked-photo inventory photos must be a list.")
        try:
            declared_count = int(payload.get("photo_occurrence_count"))
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                "Linked-photo inventory occurrence count is invalid."
            ) from exc
        if declared_count != len(photos):
            raise RuntimeError("Linked-photo inventory occurrence count is inconsistent.")
        inventory = {
            str(row.get("photo_id")): row
            for row in photos
            if isinstance(row, dict) and str(row.get("photo_id") or "").strip()
        }
        if len(inventory) != len(photos):
            raise RuntimeError("Linked-photo inventory contains invalid or duplicate photo IDs.")
        self._validated_image_variant_resolution()
        return inventory

    def _visual_files_for_defect(
        self,
        defect_index: int,
        defect: Defect,
    ) -> tuple[list[Path], list[dict[str, Any]]]:
        evidence = self._direct_evidence(defect)
        inventory = self._photo_inventory()
        report = self.workspace_report("cf-intake-evidence")
        photo_ids: list[str] = []
        pages: set[int] = set()
        stale_link_pages: set[int] = set()
        current_variant_sha256: str | None = None

        for item in evidence:
            source = item.source_json or {}
            evidence_page: int | None = None
            if item.page_number is not None and item.evidence_type in {
                PHOTO_LINK_EVIDENCE_TYPE,
                PHOTO_DETAIL_EVIDENCE_TYPE,
                PHOTO_RECONCILIATION_EVIDENCE_TYPE,
                "defect_page_layout_review",
            }:
                try:
                    evidence_page = int(str(item.page_number).strip())
                    pages.add(evidence_page)
                except ValueError:
                    pass
            if item.evidence_type == PHOTO_DETAIL_EVIDENCE_TYPE:
                value = str(source.get("photo_id") or "").strip()
                if value:
                    photo_ids.append(value)
            elif item.evidence_type == PHOTO_LINK_EVIDENCE_TYPE:
                if current_variant_sha256 is None:
                    current_variant_sha256 = self._image_variant_receipt_sha256().lower()
                current_source = (
                    str(source.get("image_variant_receipt_sha256") or "").lower()
                    == current_variant_sha256
                )
                routing_keys = (
                    ("associated_photo_ids", "uncertain_photo_ids")
                    if current_source
                    else (
                        "associated_photo_ids",
                        "uncertain_photo_ids",
                        "ignored_photo_ids",
                    )
                )
                for key in routing_keys:
                    photo_ids.extend(str(x) for x in (source.get(key) or []))
                if not current_source and evidence_page is not None:
                    stale_link_pages.add(evidence_page)
            elif item.evidence_type == PHOTO_RECONCILIATION_EVIDENCE_TYPE:
                for group in source.get("photo_groups") or []:
                    if isinstance(group, dict):
                        photo_ids.extend(str(x) for x in (group.get("photo_ids") or []))
                photo_ids.extend(str(x) for x in (source.get("photo_ids_reviewed") or []))
                if current_variant_sha256 is None:
                    current_variant_sha256 = self._image_variant_receipt_sha256().lower()
                if (
                    str(source.get("image_variant_receipt_sha256") or "").lower()
                    != current_variant_sha256
                ):
                    photo_ids.extend(str(x) for x in (source.get("ignored_photo_ids") or []))

        # A stale low-resolution linkage decision is routing evidence only. Re-review
        # every nondecorative occurrence on its recorded page so an image previously
        # dismissed as unreadable/pixelated cannot remain hidden after 16c selects a
        # verified higher-detail primary.
        for row in sorted(
            inventory.values(),
            key=lambda value: (
                int(value.get("page_number") or 0),
                int(value.get("occurrence") or 0),
                str(value.get("photo_id") or ""),
            ),
        ):
            if (
                int(row.get("page_number") or 0) in stale_link_pages
                and not bool(row.get("tiny_artifact"))
                and not bool(row.get("decorative_candidate"))
            ):
                photo_ids.append(str(row.get("photo_id") or ""))

        photo_ids = list(dict.fromkeys(item for item in photo_ids if item in inventory))
        if len(pages) > MAX_PAGE_IMAGES:
            raise RuntimeError(
                f"Defect {defect.external_defect_id or defect.id} requires {len(pages)} "
                f"labelled pages, exceeding the explicit limit of {MAX_PAGE_IMAGES}; "
                "no page context was silently truncated."
            )

        files: list[Path] = []
        manifest: list[dict[str, Any]] = []
        seen_candidate_ids: set[str] = set()
        contact_rows: list[tuple[str, Path]] = []
        for photo_id in photo_ids:
            row = inventory[photo_id]
            for source in self._preferred_photo_sources(report, row):
                candidate_id = str(source.get("candidate_id") or "")
                if not candidate_id or candidate_id in seen_candidate_ids:
                    continue
                seen_candidate_ids.add(candidate_id)
                chosen = Path(source["path"])
                provenance = str(source.get("provenance") or "")
                source_resolution = (
                    "linked_original"
                    if provenance == "REPORT_LINKED_ORIGINAL"
                    else "embedded_or_occurrence_context"
                )
                source_photo_id = str(source.get("photo_id") or photo_id)
                source_row = inventory.get(source_photo_id, row)
                status = str(
                    source_row.get("full_resolution_status") or ""
                ).strip().upper()
                expected_sha256 = str(source.get("file_sha256") or "").lower()
                if len(expected_sha256) != 64 or any(
                    character not in "0123456789abcdef" for character in expected_sha256
                ):
                    raise RuntimeError(
                        f"Image-variant candidate {candidate_id} has no valid attachment hash."
                    )
                files.append(chosen)
                manifest.append(
                    {
                        "role": "defect_photo",
                        "requested_photo_id": photo_id,
                        "photo_id": source_photo_id,
                        "page": source.get("page"),
                        "path": str(chosen),
                        "candidate_id": candidate_id,
                        "variant_group_id": source.get("group_id"),
                        "variant_role": source.get("variant_role"),
                        "primary_secondary": (
                            "PRIMARY"
                            if source.get("variant_role") == "PRIMARY"
                            else "SECONDARY"
                        ),
                        "relationship_to_primary": source.get(
                            "relationship_to_primary"
                        ),
                        "provenance": provenance,
                        "source_resolution": source_resolution,
                        "full_resolution_status": status or None,
                        "pixel_width": source.get("width"),
                        "pixel_height": source.get("height"),
                        "expected_sha256": expected_sha256,
                    }
                )
                contact_rows.append(
                    (
                        f"{source_photo_id} [{source.get('variant_role')}]",
                        chosen,
                    )
                )

        detail_count = sum(row.get("role") == "defect_photo" for row in manifest)
        if detail_count > MAX_DETAIL_IMAGES:
            raise RuntimeError(
                f"Defect {defect.external_defect_id or defect.id} requires "
                f"{detail_count} primary/mandatory-secondary images, exceeding the "
                f"explicit limit of {MAX_DETAIL_IMAGES}; no visual evidence was silently truncated."
            )

        if not any(row.get("role") == "defect_photo" for row in manifest):
            raise RuntimeError(
                f"No retained high-resolution defect photos are available for "
                f"{defect.external_defect_id or defect.id}"
            )

        for page in sorted(pages):
            labelled = self.receipt_dir / "photo-layout-labelled" / f"page-{page:04d}-labelled.png"
            if not labelled.is_file():
                raise RuntimeError(
                    f"Defect {defect.external_defect_id or defect.id} requires labelled "
                    f"page context {page}, but {labelled.name} is missing; no page "
                    "context was silently omitted."
                )
            files.append(labelled)
            manifest.append(
                {
                    "role": "labelled_full_page",
                    "page": page,
                    "path": str(labelled),
                    "primary_secondary": "SECONDARY",
                    "relationship_to_primary": "REPORT_PAGE_CONTEXT",
                    "expected_sha256": _sha256(labelled),
                }
            )

        if len(contact_rows) > 1:
            contact = self._contact_sheet(contact_rows, defect_index)
            files.append(contact)
            manifest.append(
                {
                    "role": "contact_sheet",
                    "path": str(contact),
                    "primary_secondary": "SECONDARY",
                    "relationship_to_primary": "MULTI_IMAGE_CONTEXT",
                    "expected_sha256": _sha256(contact),
                }
            )

        for index, item in enumerate(manifest, start=1):
            item["attachment_index"] = index
            item["filename"] = Path(str(item["path"])).name
        self._current_visual_manifest = manifest
        return files, manifest

    def _visual_cache_key(self, bundle: str, files: list[Path]) -> dict[str, Any]:
        manifest = getattr(self, "_current_visual_manifest", None)
        safe_manifest = [
            {
                key: (Path(str(value)).name if key == "path" else value)
                for key, value in item.items()
                if key != "path" or value
            }
            for item in manifest or []
            if isinstance(item, dict)
        ]
        return {
            "policy_version": TOPOLOGY_POLICY_VERSION,
            "image_variant_receipt_sha256": self._image_variant_receipt_sha256(),
            "bundle_sha256": hashlib.sha256(bundle.encode("utf-8")).hexdigest(),
            "ordered_attachment_manifest": safe_manifest,
            "visual_files": [
                {"name": path.name, "sha256": _sha256(path)} for path in files
            ],
        }

    def _model_visible_attachment_manifest(self) -> str:
        manifest = getattr(self, "_current_visual_manifest", None) or []
        visible = [
            {
                "attachment_index": row.get("attachment_index"),
                "filename": row.get("filename") or Path(str(row.get("path") or "")).name,
                "role": row.get("role"),
                "photo_id": row.get("photo_id"),
                "requested_photo_id": row.get("requested_photo_id"),
                "page": row.get("page"),
                "variant_group_id": row.get("variant_group_id"),
                "primary_secondary": row.get("primary_secondary"),
                "relationship_to_primary": row.get("relationship_to_primary"),
                "source_resolution": row.get("source_resolution"),
                "expected_sha256": row.get("expected_sha256"),
            }
            for row in manifest
            if isinstance(row, dict)
        ]
        return json.dumps(visible, ensure_ascii=False, separators=(",", ":"))

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
Ordered attachment manifest. Attachment indexes match the supplied file order exactly:
{self._model_visible_attachment_manifest()}

The attached files include the actual report page/contact sheet and the best verified local pixels for each
defect photograph. When a small embedded report image exposes a full-resolution link, the linked original is
materialized, hash-verified and supplied here; inference fails closed rather than substituting a magnified
thumbnail when that required original is unavailable. These actual images are PRIMARY evidence for physical
topology. Earlier AI photo summaries/reconciliation are secondary aids and must be corrected when the attached
images show more detail.
- Inspect each PRIMARY before making fine-detail conclusions. Lower-resolution equivalents are secondary only.
- Consult every MANDATORY_SECONDARY crop, annotation, contrast or page-context variant and retain its unique
  information. Never collapse AMBIGUOUS, SIMILAR_DISTINCT or derivative variants as resolution-only duplicates.

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
