from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import defaultdict
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
from run_classifire_real_uat_defectwise import _trim
from run_classifire_real_uat_deterministic import (
    REQUIRED_INTAKE_WRITE_TOOLS,
    _confidence,
    _json_from_payload,
)
from run_classifire_real_uat_intake import load_receipt, repo_root
from run_classifire_real_uat_layoutaware import LayoutAwareController
from sqlalchemy import select

from classifire.canonical_models import Defect, EvidenceSource
from classifire.db import SessionLocal
from classifire.services.image_variant_resolution import (
    DEFAULT_IMAGE_VARIANT_POLICY,
    IMAGE_VARIANT_POLICY_VERSION,
    IMAGE_VARIANT_RECEIPT_FILENAME,
    ImageCandidate,
    ImageOccurrence,
    ImageVariantResolution,
    load_image_variant_resolution,
    resolve_image_variants,
    validated_mandatory_secondary_paths,
    validated_primary_paths,
)
from classifire.services.linked_image_retrieval import (
    DEFAULT_LINKED_IMAGE_POLICY,
    materialize_linked_images,
    preferred_verified_linked_path,
)

PHOTO_LINK_EVIDENCE_TYPE = "defect_page_photo_linkage_review"
PHOTO_DETAIL_EVIDENCE_TYPE = "defect_photo_detail_review"
PHOTO_RECONCILIATION_EVIDENCE_TYPE = "defect_photo_reconciliation"
PHOTO_ZOOM_DPI = 420
LOW_RES_LONG_SIDE_PX = 900
CONTACT_THUMBNAIL = (900, 650)
MAX_RECONCILIATION_PHOTOS = 24
MAX_RECONCILIATION_VISUALS = 72
LINKED_PHOTO_INVENTORY_RECEIPT = "16b-photo-inventory-linked.json"
LINKED_PHOTO_MATERIALIZATION_RECEIPT = "16b-photo-materialization.json"
IMAGE_VARIANT_INVENTORY_RECEIPT = IMAGE_VARIANT_RECEIPT_FILENAME
PHOTO_VISUAL_POLICY_VERSION = "CLASSIFIRE-PHOTO-VISUAL-v2-HIGHEST-USABLE-DETAIL"
FULL_RESOLUTION_READY_STATUSES = frozenset({"VERIFIED", "CACHED"})


def _safe_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _unique_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class PhotoAwareController(LayoutAwareController):
    def stage_visuals(self) -> dict:
        manifest = super().stage_visuals()
        report = self.workspace_report("cf-intake-evidence")
        self._ensure_linked_photo_inventory(report)
        self._ensure_image_variant_inventory(report)
        return manifest

    def _prior_linked_photo_receipt(self) -> dict | None:
        path = self.receipt_dir / LINKED_PHOTO_MATERIALIZATION_RECEIPT
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _ensure_linked_photo_inventory(
        self,
        report: Path,
    ) -> tuple[dict[int, list[dict]], dict[str, dict]]:
        cached = getattr(self, "_linked_photo_inventory_cache", None)
        if cached is not None:
            return cached
        inventory = self._build_photo_inventory(report)
        self._linked_photo_inventory_cache = inventory
        return inventory

    def _ensure_image_variant_inventory(self, report: Path) -> ImageVariantResolution:
        """Resolve all report-image versions before any visual inference.

        This is deliberately filesystem-only. It consumes the verified 16b inventory,
        inventories every PDF image occurrence and its displayed page context, and saves
        one report-bound 16c receipt. It never writes canonical or EvidenceSource state.
        """

        cached = getattr(self, "_image_variant_resolution_cache", None)
        if cached is not None:
            return cached

        _pages, by_id = self._ensure_linked_photo_inventory(report)
        linked_inventory_path = self.receipt_dir / LINKED_PHOTO_INVENTORY_RECEIPT
        if not linked_inventory_path.is_file():
            raise RuntimeError("Linked-photo inventory is missing before image-variant resolution.")

        occurrences: list[ImageOccurrence] = []
        candidates: list[ImageCandidate] = []
        ordered_rows = sorted(
            by_id.values(),
            key=lambda item: (
                int(item.get("page_number") or 0),
                int(item.get("occurrence") or 0),
                str(item.get("photo_id") or ""),
            ),
        )
        for row in ordered_rows:
            photo_id = str(row.get("photo_id") or "").strip()
            if not photo_id:
                raise RuntimeError("Photo inventory contains an occurrence without a photo_id.")
            native_raw = str(row.get("native_path") or "").strip()
            native = Path(native_raw) if native_raw else None
            if native is None or not native.is_file():
                raise RuntimeError(
                    "Image-variant resolution cannot bind an embedded occurrence "
                    f"without extracted pixels: {photo_id}."
                )
            bbox_raw = row.get("bbox")
            bbox = (
                tuple(float(value) for value in bbox_raw)
                if isinstance(bbox_raw, (list, tuple)) and len(bbox_raw) == 4
                else None
            )
            xref_raw = row.get("xref")
            try:
                xref = int(xref_raw) if xref_raw not in (None, "") else None
            except (TypeError, ValueError):
                xref = None
            occurrences.append(
                ImageOccurrence(
                    occurrence_id=photo_id,
                    photo_id=photo_id,
                    page_number=int(row.get("page_number") or 0),
                    xref=xref,
                    bbox=bbox,
                    embedded_path=native,
                )
            )

            zoom = self._ensure_zoom_crop(report, row)
            if zoom.resolve() != native.resolve():
                candidates.append(
                    ImageCandidate(
                        candidate_id=f"{photo_id}:page-context",
                        occurrence_id=photo_id,
                        path=zoom,
                        provenance="PDF_PAGE_CONTEXT",
                        context_tags=("DISPLAYED_OCCURRENCE", "ANNOTATIONS_AND_CROP_CONTEXT"),
                    )
                )

            status = str(row.get("full_resolution_status") or "").strip().upper()
            if status in FULL_RESOLUTION_READY_STATUSES:
                linked = preferred_verified_linked_path(row, self.receipt_dir)
                if linked is None:
                    raise RuntimeError(
                        "Linked full-resolution receipt could not be verified during "
                        f"image-variant resolution for photo {photo_id}."
                    )
                candidates.append(
                    ImageCandidate(
                        candidate_id=f"{photo_id}:linked-original",
                        occurrence_id=photo_id,
                        path=linked,
                        provenance="REPORT_LINKED_ORIGINAL",
                        context_tags=(
                            "REPORT_IMAGE_LINK",
                            "FULL_RESOLUTION",
                            "VERIFIED_THUMBNAIL_BINDING",
                        ),
                    )
                )

        result = resolve_image_variants(
            report_path=report,
            linked_inventory_path=linked_inventory_path,
            occurrences=occurrences,
            candidates=candidates,
            artifact_root=self.receipt_dir,
            expected_report_sha256=str(self.receipt["report_sha256"]),
            expected_inventory_sha256=_sha256_file(linked_inventory_path),
            policy=DEFAULT_IMAGE_VARIANT_POLICY,
        )
        payload = result.to_dict()
        self.save_json(IMAGE_VARIANT_INVENTORY_RECEIPT, payload)
        receipt_path = self.receipt_dir / IMAGE_VARIANT_INVENTORY_RECEIPT
        if not receipt_path.is_file():
            raise RuntimeError("Image-variant resolution receipt was not saved.")
        result = load_image_variant_resolution(
            receipt_path,
            artifact_root=self.receipt_dir,
            expected_report_sha256=str(self.receipt["report_sha256"]),
            expected_inventory_sha256=_sha256_file(linked_inventory_path),
        )
        self._image_variant_receipt_sha256_cache = _sha256_file(receipt_path)

        groups_by_occurrence: dict[str, Mapping[str, Any]] = {}
        variant_rows_by_candidate = {
            str(item.get("candidate_id") or ""): item for item in result.rows
        }
        for group in result.groups:
            for member in group.get("member_occurrences") or ():
                occurrence_id = str(member.get("occurrence_id") or "").strip()
                if occurrence_id:
                    groups_by_occurrence[occurrence_id] = group
        for photo_id, row in by_id.items():
            group = groups_by_occurrence.get(photo_id)
            if group is None:
                raise RuntimeError(f"Image-variant resolution omitted photo occurrence {photo_id}.")
            row["image_variant_group_id"] = str(group.get("group_id") or "")
            row["image_variant_group_status"] = str(group.get("status") or "")
            row["image_variant_primary_candidate_id"] = str(
                group.get("primary_candidate_id") or ""
            )
            primary_row = variant_rows_by_candidate.get(
                row["image_variant_primary_candidate_id"]
            )
            row["image_variant_primary_photo_id"] = (
                str(primary_row.get("photo_id") or "") if primary_row is not None else ""
            )
            row["image_variant_relationships"] = sorted(
                {
                    str(item.get("relationship_to_primary") or "")
                    for item in result.rows
                    if str(item.get("group_id") or "") == row["image_variant_group_id"]
                    and str(item.get("occurrence_id") or "") == photo_id
                    and str(item.get("relationship_to_primary") or "")
                }
            )
            row["image_variant_policy_version"] = IMAGE_VARIANT_POLICY_VERSION
            row["image_variant_receipt_sha256"] = self._image_variant_receipt_sha256_cache

        self._image_variant_resolution_cache = result
        self._on_image_variant_inventory_ready(by_id)
        return result

    def _on_image_variant_inventory_ready(self, by_id: dict[str, dict]) -> None:
        """Hook for runners that derive report-wide group metadata after 16c exists."""

    def _image_variant_receipt_sha256(self) -> str:
        cached = getattr(self, "_image_variant_receipt_sha256_cache", None)
        if cached:
            return str(cached)
        path = self.receipt_dir / IMAGE_VARIANT_INVENTORY_RECEIPT
        if not path.is_file():
            raise RuntimeError("Image-variant resolution receipt is missing.")
        digest = _sha256_file(path)
        self._image_variant_receipt_sha256_cache = digest
        return digest

    def _validated_image_variant_path_maps(
        self,
        result: ImageVariantResolution,
    ) -> tuple[dict[str, Path], dict[str, Path]]:
        """Validate the complete 16c asset set once per controller/receipt/root."""

        receipt_path = self.receipt_dir / IMAGE_VARIANT_INVENTORY_RECEIPT
        if not receipt_path.is_file():
            raise RuntimeError("Image-variant resolution receipt is missing.")
        actual_receipt_sha256 = _sha256_file(receipt_path)
        if actual_receipt_sha256 != self._image_variant_receipt_sha256():
            raise RuntimeError("Image-variant resolution receipt changed after validation.")
        cache_key = (actual_receipt_sha256, str(self.receipt_dir.resolve()))
        cached = getattr(self, "_image_variant_validated_path_maps_cache", None)
        if isinstance(cached, tuple) and len(cached) == 3 and cached[0] == cache_key:
            return cached[1], cached[2]

        raw_primary = validated_primary_paths(result, artifact_root=self.receipt_dir)
        raw_secondary = validated_mandatory_secondary_paths(
            result,
            artifact_root=self.receipt_dir,
        )
        if not isinstance(raw_primary, Mapping) or not isinstance(raw_secondary, Mapping):
            raise RuntimeError("Image-variant path validator returned an unsupported value.")
        primary = {
            str(candidate_id): Path(path).resolve()
            for candidate_id, path in raw_primary.items()
            if str(candidate_id).strip()
        }
        secondary = {
            str(candidate_id): Path(path).resolve()
            for candidate_id, path in raw_secondary.items()
            if str(candidate_id).strip()
        }
        if len(primary) != len(raw_primary) or len(secondary) != len(raw_secondary):
            raise RuntimeError("Image-variant path validator returned an invalid candidate ID.")
        self._image_variant_validated_path_maps_cache = (cache_key, primary, secondary)
        return primary, secondary

    def _preferred_photo_sources(self, report: Path, row: dict) -> list[dict[str, Any]]:
        """Return the proven-detail primary followed by every mandatory context view."""

        result = self._ensure_image_variant_inventory(report)
        group_id = str(row.get("image_variant_group_id") or "").strip()
        if not group_id:
            photo_id = str(row.get("photo_id") or "").strip()
            for group in result.groups:
                members = group.get("member_occurrences") or ()
                if any(str(item.get("occurrence_id") or "") == photo_id for item in members):
                    group_id = str(group.get("group_id") or "")
                    break
        group = next(
            (item for item in result.groups if str(item.get("group_id") or "") == group_id),
            None,
        )
        if group is None:
            raise RuntimeError(
                f"No image-variant group is available for photo {row.get('photo_id')}."
            )

        primary_paths, secondary_paths = self._validated_image_variant_path_maps(result)
        rows_by_candidate = {
            str(item.get("candidate_id") or ""): item for item in result.rows
        }
        selections: list[tuple[str, str]] = [
            (str(group.get("primary_candidate_id") or ""), "SELF")
        ]
        selections.extend(
            (
                str(item.get("candidate_id") or ""),
                str(item.get("relationship") or "AMBIGUOUS"),
            )
            for item in (group.get("mandatory_secondary") or ())
        )
        selected: list[dict[str, Any]] = []
        for index, (candidate_id, group_relationship) in enumerate(selections):
            candidate_row = rows_by_candidate.get(candidate_id)
            if candidate_row is None:
                raise RuntimeError(
                    f"Image-variant group {group_id} references unknown candidate {candidate_id}."
                )
            relative = Path(str(candidate_row.get("path") or ""))
            resolved = (self.receipt_dir / relative).resolve()
            validated = primary_paths if index == 0 else secondary_paths
            if validated.get(candidate_id) != resolved:
                raise RuntimeError(
                    f"Image-variant candidate {candidate_id} failed central path validation."
                )
            declared_sha256 = str(candidate_row.get("file_sha256") or "").lower()
            try:
                selected_sha256 = _sha256_file(resolved)
            except OSError as exc:
                raise RuntimeError(
                    f"Image-variant candidate {candidate_id} is unavailable at attachment time."
                ) from exc
            if selected_sha256 != declared_sha256:
                raise RuntimeError(
                    f"Image-variant candidate {candidate_id} changed after central validation."
                )
            selected.append(
                {
                    "path": resolved,
                    "candidate_id": candidate_id,
                    "group_id": group_id,
                    "variant_role": "PRIMARY" if index == 0 else "MANDATORY_SECONDARY",
                    "relationship_to_primary": group_relationship,
                    "provenance": candidate_row.get("provenance"),
                    "occurrence_id": candidate_row.get("occurrence_id"),
                    "photo_id": candidate_row.get("photo_id"),
                    "page": candidate_row.get("page_number"),
                    "width": candidate_row.get("width"),
                    "height": candidate_row.get("height"),
                    "file_sha256": declared_sha256,
                    "context_tags": list(candidate_row.get("context_tags") or ()),
                }
            )
        if not selected:
            raise RuntimeError(f"Image-variant group {group_id} has no usable primary.")
        return selected

    def _preferred_photo_path(self, report: Path, row: dict) -> Path:
        """Return the highest-usable-detail pixels for one PDF image occurrence.

        Linked originals and whole-document variants are resolved before inference.
        A required original never silently falls back to an embedded thumbnail, and a
        lower-detail earlier-page occurrence never overrides a proven better version.
        """

        required = bool(row.get("full_resolution_required"))
        status = str(row.get("full_resolution_status") or "").strip().upper()

        if required and status not in FULL_RESOLUTION_READY_STATUSES:
            raise RuntimeError(
                "Linked full-resolution image is required but was not materialized "
                f"for photo {row.get('photo_id')} (status={status or 'MISSING'})."
            )

        sources = self._preferred_photo_sources(report, row)
        return Path(sources[0]["path"])

    @staticmethod
    def _compact_evidence_row(item: EvidenceSource) -> dict:
        source = item.source_json or {}
        if item.evidence_type == PHOTO_LINK_EVIDENCE_TYPE:
            return {
                "evidence_id": item.id,
                "type": item.evidence_type,
                "page": item.page_number,
                "region": item.region_reference,
                "association_status": source.get("association_status"),
                "association_confidence": source.get("association_confidence"),
                "association_basis": source.get("association_basis") or [],
                "associated_photo_ids": source.get("associated_photo_ids") or [],
                "ignored_photo_ids": source.get("ignored_photo_ids") or [],
                "uncertain_photo_ids": source.get("uncertain_photo_ids") or [],
                "physical_facts": source.get("physical_facts") or [],
                "uncertainties": source.get("uncertainties") or [],
            }
        if item.evidence_type == PHOTO_DETAIL_EVIDENCE_TYPE:
            return {
                "evidence_id": item.id,
                "type": item.evidence_type,
                "page": item.page_number,
                "region": item.region_reference,
                "photo_id": source.get("photo_id"),
                "scope_relevance": source.get("scope_relevance"),
                "target_link": source.get("target_link"),
                "viewpoint": source.get("viewpoint"),
                "barrier_face": source.get("barrier_face"),
                "visible_services": source.get("visible_services") or [],
                "visible_openings": source.get("visible_openings") or [],
                "distinctive_features": source.get("distinctive_features") or [],
                "physical_facts": source.get("physical_facts") or [],
                "uncertainties": source.get("uncertainties") or [],
            }
        if item.evidence_type == PHOTO_RECONCILIATION_EVIDENCE_TYPE:
            return {
                "evidence_id": item.id,
                "type": item.evidence_type,
                "page": item.page_number,
                "region": item.region_reference,
                "status": source.get("status"),
                "photo_groups": source.get("photo_groups") or [],
                "counting_decisions": source.get("counting_decisions") or [],
                "opening_count": source.get("opening_count"),
                "service_count": source.get("service_count"),
                "openings": source.get("openings") or [],
                "services": source.get("services") or [],
                "relationships": source.get("relationships") or [],
                "physical_facts": source.get("physical_facts") or [],
                "uncertainties": source.get("uncertainties") or [],
            }
        return LayoutAwareController._compact_evidence_row(item)

    def defect_physical_prompt(self, defect: Defect, evidence_text: str) -> str:
        base = super().defect_physical_prompt(defect, evidence_text)
        return base + """

Additional mandatory photo-reconciliation rules:
- Different photographs are NOT different physical items by default.
- When defect_photo_reconciliation evidence groups photos as the same asset/service/opening from different
  angles, treat the group as one physical subject unless separate evidence proves otherwise.
- A service photographed from opposite faces of the same wall, or from top and soffit sides of the same floor
  penetration, remains one service crossing one opening unless evidence proves multiple services/openings.
- Different services visible within the same opening remain separate Services when individually supported.
- Never derive service/opening quantity from the number of photos.
- If photo-reconciliation remains uncertain about whether images depict the same or different physical subjects,
  return INSUFFICIENT_EVIDENCE rather than double-counting or collapsing them without support.
"""

    def _existing_source(self, defect_id: str, evidence_type: str, region_reference: str) -> dict | None:
        with SessionLocal() as db:
            row = db.scalar(
                select(EvidenceSource).where(
                    EvidenceSource.estimate_id == self.estimate_id,
                    EvidenceSource.defect_id == defect_id,
                    EvidenceSource.evidence_type == evidence_type,
                    EvidenceSource.region_reference == region_reference,
                    EvidenceSource.status == "active",
                ).limit(1)
            )
            return dict(row.source_json or {}) if row is not None else None

    def _build_photo_inventory(self, report: Path) -> tuple[dict[int, list[dict]], dict[str, dict]]:
        try:
            import pymupdf
        except ImportError as exc:
            raise RuntimeError(
                "PyMuPDF is required for photo-aware UAT. Run: python -m pip install -e ."
            ) from exc

        native_dir = self.receipt_dir / "photo-native"
        native_dir.mkdir(parents=True, exist_ok=True)
        document = pymupdf.open(str(report))
        pages: dict[int, list[dict]] = defaultdict(list)
        by_id: dict[str, dict] = {}
        digest_pages: dict[str, set[int]] = defaultdict(set)
        try:
            for page_index in range(len(document)):
                page = document.load_page(page_index)
                page_number = page_index + 1
                page_rect = page.rect
                page_area = max(float(page_rect.width * page_rect.height), 1.0)
                infos = page.get_image_info(hashes=True, xrefs=True)
                for occurrence, info in enumerate(infos, start=1):
                    bbox = pymupdf.Rect(info.get("bbox"))
                    if bbox.is_empty or bbox.is_infinite:
                        continue
                    digest_raw = info.get("digest")
                    digest = digest_raw.hex() if isinstance(digest_raw, (bytes, bytearray)) else str(digest_raw or "")
                    if digest:
                        digest_pages[digest].add(page_number)
                    photo_id = f"P{page_number:03d}-I{occurrence:02d}"
                    width = int(info.get("width") or 0)
                    height = int(info.get("height") or 0)
                    xref = int(info.get("xref") or 0)
                    bbox_area_ratio = float(max(bbox.width, 0) * max(bbox.height, 0) / page_area)
                    row = {
                        "photo_id": photo_id,
                        "page_number": page_number,
                        "occurrence": occurrence,
                        "xref": xref,
                        "digest": digest,
                        "width": width,
                        "height": height,
                        "bbox": [float(bbox.x0), float(bbox.y0), float(bbox.x1), float(bbox.y1)],
                        "bbox_normalized": [
                            float((bbox.x0 - page_rect.x0) / page_rect.width),
                            float((bbox.y0 - page_rect.y0) / page_rect.height),
                            float((bbox.x1 - page_rect.x0) / page_rect.width),
                            float((bbox.y1 - page_rect.y0) / page_rect.height),
                        ],
                        "display_area_ratio": bbox_area_ratio,
                        "page_width": float(page_rect.width),
                        "page_height": float(page_rect.height),
                        "native_path": None,
                        "native_extraction_ok": False,
                    }
                    if xref > 0:
                        try:
                            extracted = document.extract_image(xref)
                            raw = extracted.get("image") if isinstance(extracted, dict) else None
                            if raw:
                                target = native_dir / f"{photo_id}.png"
                                with Image.open(BytesIO(raw)) as image:
                                    image.load()
                                    if image.mode not in {"RGB", "RGBA", "L"}:
                                        image = image.convert("RGB")
                                    image.save(target, format="PNG")
                                    row["native_path"] = str(target)
                                    row["native_extraction_ok"] = True
                                    row["native_width"] = image.width
                                    row["native_height"] = image.height
                        except Exception as exc:
                            row["native_extraction_error"] = str(exc)
                    pages[page_number].append(row)
                    by_id[photo_id] = row
        finally:
            document.close()

        page_count = max(len(pages), 1)
        repeated_threshold = max(3, math.ceil(page_count * 0.5))
        for row in by_id.values():
            normalized = row["bbox_normalized"]
            repeated_pages = len(digest_pages.get(str(row["digest"]), set())) if row["digest"] else 0
            in_header_or_footer = normalized[3] <= 0.20 or normalized[1] >= 0.80
            tiny_artifact = (
                int(row["width"]) <= 8
                or int(row["height"]) <= 8
                or float(row["display_area_ratio"]) < 0.0004
            )
            repeated_header_footer = (
                repeated_pages >= repeated_threshold
                and in_header_or_footer
                and float(row["display_area_ratio"]) < 0.12
            )
            row["repeated_on_pages"] = repeated_pages
            row["tiny_artifact"] = tiny_artifact
            row["decorative_candidate"] = bool(repeated_header_footer)
            reasons: list[str] = []
            if tiny_artifact:
                reasons.append("tiny/pseudo-image candidate")
            if repeated_header_footer:
                reasons.append(
                    f"same image digest repeated on {repeated_pages} pages in header/footer region"
                )
            row["non_scope_candidate_reasons"] = reasons

        self.save_json(
            "16-photo-inventory.json",
            {
                "page_count": page_count,
                "photo_occurrence_count": len(by_id),
                "photos": list(by_id.values()),
            },
        )
        print(f"PASS native photo inventory -> {len(by_id)} displayed image occurrences")

        batch = materialize_linked_images(
            report,
            list(by_id.values()),
            self.receipt_dir,
            report_sha256=str(self.receipt["report_sha256"]),
            policy=DEFAULT_LINKED_IMAGE_POLICY,
            prior_receipt=self._prior_linked_photo_receipt(),
        )
        self.save_json(LINKED_PHOTO_MATERIALIZATION_RECEIPT, batch.receipt)

        enriched_rows = [dict(row) for row in batch.rows]
        enriched_by_id = {
            str(row.get("photo_id")): row
            for row in enriched_rows
            if str(row.get("photo_id") or "").strip()
        }
        if set(enriched_by_id) != set(by_id) or len(enriched_rows) != len(by_id):
            raise RuntimeError(
                "Linked-photo materialization returned an incomplete or duplicate inventory."
            )
        enriched_pages = {
            page_number: [enriched_by_id[str(row["photo_id"])] for row in rows]
            for page_number, rows in pages.items()
        }
        cache_verification_error: Exception | None = None
        try:
            for row in enriched_rows:
                status = str(row.get("full_resolution_status") or "").strip().upper()
                if status in FULL_RESOLUTION_READY_STATUSES and (
                    preferred_verified_linked_path(row, self.receipt_dir) is None
                ):
                    raise RuntimeError("verified path was not returned")
        except Exception as exc:
            cache_verification_error = exc

        self.save_json(
            LINKED_PHOTO_INVENTORY_RECEIPT,
            {
                "schema": "CLASSIFIRE-LINKED-PHOTO-INVENTORY-v1",
                "report_sha256": str(self.receipt["report_sha256"]),
                "linked_image_policy_version": batch.receipt.get("policy_version"),
                "materialization_receipt": LINKED_PHOTO_MATERIALIZATION_RECEIPT,
                "materialization_ok": bool(batch.ok),
                "cache_verification_ok": cache_verification_error is None,
                "page_count": page_count,
                "photo_occurrence_count": len(enriched_rows),
                "photos": enriched_rows,
            },
        )
        if cache_verification_error is not None:
            raise RuntimeError(
                "Linked full-resolution cache verification failed before inference; "
                f"see {LINKED_PHOTO_MATERIALIZATION_RECEIPT}."
            ) from cache_verification_error
        if not batch.ok or any(
            bool(row.get("full_resolution_required"))
            and str(row.get("full_resolution_status") or "").strip().upper()
            not in FULL_RESOLUTION_READY_STATUSES
            for row in enriched_rows
        ):
            raise RuntimeError(
                "Required linked full-resolution image materialization failed; "
                f"see {LINKED_PHOTO_MATERIALIZATION_RECEIPT}."
            )
        print(
            "PASS linked photo inventory -> "
            f"{len(enriched_rows)} occurrences, filesystem-only materialization verified"
        )
        return enriched_pages, enriched_by_id

    def _annotated_page(
        self,
        rendered_path: Path,
        page_rows: list[dict],
        page_number: int,
    ) -> Path:
        output_dir = self.receipt_dir / "photo-layout-labelled"
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f"page-{page_number:04d}-labelled.png"
        if output.is_file():
            return output
        with Image.open(rendered_path) as source:
            image = source.convert("RGB")
        draw = ImageDraw.Draw(image)
        for row in page_rows:
            if row.get("tiny_artifact"):
                continue
            x0, y0, x1, y1 = row["bbox_normalized"]
            box = (
                int(x0 * image.width),
                int(y0 * image.height),
                int(x1 * image.width),
                int(y1 * image.height),
            )
            draw.rectangle(box, outline="white", width=4)
            label = str(row["photo_id"])
            if row.get("decorative_candidate"):
                label += " DECOR?"
            text_box = draw.textbbox((box[0], max(0, box[1] - 18)), label)
            draw.rectangle(text_box, fill="black")
            draw.text((box[0], max(0, box[1] - 18)), label, fill="white")
        image.save(output, format="PNG")
        return output

    def _ensure_zoom_crop(self, report: Path, row: dict) -> Path:
        try:
            import pymupdf
        except ImportError as exc:
            raise RuntimeError("PyMuPDF is required for photo zoom rendering") from exc
        output_dir = self.receipt_dir / "photo-zoom"
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f"{row['photo_id']}-zoom.png"
        if output.is_file():
            return output
        document = pymupdf.open(str(report))
        try:
            page = document.load_page(int(row["page_number"]) - 1)
            bbox = pymupdf.Rect(row["bbox"])
            pad = 8.0
            clip = pymupdf.Rect(
                max(page.rect.x0, bbox.x0 - pad),
                max(page.rect.y0, bbox.y0 - pad),
                min(page.rect.x1, bbox.x1 + pad),
                min(page.rect.y1, bbox.y1 + pad),
            )
            pixmap = page.get_pixmap(
                dpi=PHOTO_ZOOM_DPI,
                colorspace=pymupdf.csRGB,
                alpha=False,
                annots=True,
                clip=clip,
            )
            pixmap.save(str(output))
        finally:
            document.close()
        return output

    def photo_link_prompt(self, defect: Defect, page_number: int, candidates: list[dict]) -> str:
        identity = defect.external_defect_id or defect.defect_code or defect.id
        metadata = [
            {
                "photo_id": row["photo_id"],
                "bbox_normalized": row["bbox_normalized"],
                "native_pixels": [row.get("native_width") or row["width"], row.get("native_height") or row["height"]],
                "decorative_candidate": row.get("decorative_candidate", False),
                "candidate_reasons": row.get("non_scope_candidate_reasons") or [],
            }
            for row in candidates
            if not row.get("tiny_artifact")
        ]
        return f"""Review this COMPLETE rendered and labelled report page for CLASSIFIRE.
Target defect: {identity}
Retained defect description: {_trim(defect.description, 900)}
Retained defect location: {_trim(defect.location, 500)}
Page: {page_number}

The page image contains labels such as P003-I04 around displayed PDF images. Candidate metadata:
{json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))}

Determine which labelled photos are actually evidence for target defect {identity}. Company logos, header/footer
branding, decorative icons, signatures and unrelated report furniture are NON-SCOPE and must be ignored.
Do not link a photo merely because it is on the same page. Use row boundaries, captions, layout, defect text,
photo placement and visible content.

Return ONLY valid JSON:
{{
  "target_defect_id": "{identity}",
  "page_number": {page_number},
  "association_status": "SUPPORTED|AMBIGUOUS|NOT_VISIBLE",
  "association_confidence": 0.0,
  "association_basis": [],
  "associated_photo_ids": [],
  "ignored_photo_ids": [],
  "uncertain_photo_ids": [],
  "physical_facts": [],
  "uncertainties": []
}}

Rules:
- Every labelled non-tiny candidate photo must be associated, ignored, or uncertain exactly once.
- A repeated header/footer logo candidate is normally non-scope, but verify from the page rather than blindly relying on metadata.
- Multiple photos may show the SAME service/opening from different angles or opposite sides of a wall/floor.
  Do not convert photo count into service/opening count at this stage.
- Do not select a fire-stopping system and do not price anything.
"""

    @staticmethod
    def _attachment_manifest(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "attachment_index": index,
                "filename": Path(str(source["path"])).name,
                "photo_id": source.get("photo_id"),
                "page": source.get("page"),
                "variant_role": source.get("variant_role"),
                "relationship_to_primary": source.get("relationship_to_primary"),
                "provenance": source.get("provenance"),
                "group_id": source.get("group_id"),
            }
            for index, source in enumerate(sources, start=1)
        ]

    def photo_detail_prompt(
        self,
        defect: Defect,
        row: dict,
        *,
        refinement: bool = False,
        attachment_manifest: list[dict[str, Any]] | None = None,
    ) -> str:
        identity = defect.external_defect_id or defect.defect_code or defect.id
        mode = (
            "REFINEMENT using the best verified source and page-zoom views of the same photo"
            if refinement
            else "best-verified-resolution photo review"
        )
        manifest = attachment_manifest or []
        return f"""Perform {mode} for CLASSIFIRE target defect {identity}.
Photo ID: {row['photo_id']} from report page {row['page_number']}.
Retained defect description: {_trim(defect.description, 800)}
Retained defect location: {_trim(defect.location, 400)}
Ordered attachment manifest (the attachment index is authoritative):
{json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))}

Return ONLY valid JSON:
{{
  "photo_id": "{row['photo_id']}",
  "scope_relevance": "relevant|non_scope|uncertain",
  "target_link": "supported|ambiguous|not_target",
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
- Inspect attachment 1, the proven highest-usable-detail PRIMARY, before detailed conclusions.
- MANDATORY_SECONDARY attachments preserve crop, annotation, contrast or report-page context. Consult every
  one and retain unique information, but do not base fine visual detail on a lower-resolution equivalent when
  the PRIMARY is clearer.
- Treat two files as the same underlying image only when the supplied relationship says so. AMBIGUOUS,
  SIMILAR_DISTINCT and derivative variants must not be silently collapsed.
- Inspect only visible evidence. Company logos/header/footer branding/decorative graphics are non_scope.
- One photo does not establish one service, one opening, one repair or quantity one.
- Describe individually distinguishable visible services/openings, but do not assume hidden continuation or hidden count.
- Record clues useful for matching this view with another angle or opposite side: service arrangement, colours,
  fittings, insulation, penetrant order, opening shape, nearby structure, wall/floor face, background landmarks.
- If resolution prevents reliable detail, set needs_zoom=true and say why.
- Do not invent dimensions, material, FRL or substrate plane.
"""

    def _analyse_photo_detail(self, report: Path, defect: Defect, row: dict, defect_index: int) -> dict:
        sources = self._preferred_photo_sources(report, row)
        files = [Path(item["path"]) for item in sources]
        attachment_manifest = self._attachment_manifest(sources)
        receipt_tag = self._image_variant_receipt_sha256()[:12]
        payload = self.infer_model(
            prompt=self.photo_detail_prompt(
                defect,
                row,
                attachment_manifest=attachment_manifest,
            ),
            receipt_name=(
                f"16-photo-v2-{receipt_tag}-d{defect_index:03d}-"
                f"{row['photo_id']}-detail"
            ),
            files=files,
            thinking="medium",
        )
        model = _json_from_payload(payload, context=f"Photo detail {row['photo_id']}")
        if str(model.get("photo_id") or "") != str(row["photo_id"]):
            raise RuntimeError(f"Photo detail returned wrong photo_id for {row['photo_id']}")

        source_long_side = max(
            int(sources[0].get("width") or 0),
            int(sources[0].get("height") or 0),
        )
        needs_refinement = bool(model.get("needs_zoom")) or source_long_side < LOW_RES_LONG_SIDE_PX
        if needs_refinement:
            refined = self.infer_model(
                prompt=self.photo_detail_prompt(
                    defect,
                    row,
                    refinement=True,
                    attachment_manifest=attachment_manifest,
                ),
                receipt_name=(
                    f"16-photo-v2-{receipt_tag}-d{defect_index:03d}-"
                    f"{row['photo_id']}-refined"
                ),
                files=files,
                thinking="medium",
            )
            model = _json_from_payload(refined, context=f"Photo refinement {row['photo_id']}")
            if str(model.get("photo_id") or "") != str(row["photo_id"]):
                raise RuntimeError(f"Photo refinement returned wrong photo_id for {row['photo_id']}")
            model["zoom_refinement_performed"] = True
        else:
            model["zoom_refinement_performed"] = False
        model["native_extraction_ok"] = bool(row.get("native_extraction_ok"))
        model["full_resolution_status"] = row.get("full_resolution_status")
        model["native_pixels"] = [
            sources[0].get("width"),
            sources[0].get("height"),
        ]
        model["primary_photo_id"] = sources[0].get("photo_id")
        model["primary_page"] = sources[0].get("page")
        model["source_bbox"] = row.get("bbox")
        model["image_variant_receipt_sha256"] = self._image_variant_receipt_sha256()
        model["image_variant_group_id"] = row.get("image_variant_group_id")
        model["attachment_manifest"] = attachment_manifest
        return model

    def _contact_sheet(self, rows: list[tuple[str, Path]], defect_index: int) -> Path:
        unique_rows: list[tuple[str, Path]] = []
        seen_paths: set[str] = set()
        for label, path in rows:
            resolved_key = str(path.resolve()).casefold()
            if resolved_key in seen_paths:
                continue
            seen_paths.add(resolved_key)
            unique_rows.append((label, path))
        rows = unique_rows
        if len(rows) > MAX_RECONCILIATION_VISUALS:
            raise RuntimeError(
                f"Photo contact sheet requires {len(rows)} primary/secondary visuals, "
                f"exceeding the explicit limit of {MAX_RECONCILIATION_VISUALS}; "
                "no visual context was silently truncated."
            )
        output_dir = self.receipt_dir / "photo-contact-sheets"
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f"defect-{defect_index:03d}.png"
        binding_path = output_dir / f"defect-{defect_index:03d}-binding.json"
        binding = {
            "policy_version": PHOTO_VISUAL_POLICY_VERSION,
            "image_variant_receipt_sha256": self._image_variant_receipt_sha256(),
            "contact_thumbnail": list(CONTACT_THUMBNAIL),
            "inputs": [
                {
                    "label": photo_id,
                    "filename": path.name,
                    "sha256": _sha256_file(path),
                }
                for photo_id, path in rows
            ],
        }
        if output.is_file() and binding_path.is_file():
            try:
                prior = json.loads(binding_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                prior = None
            if (
                isinstance(prior, dict)
                and prior.get("binding") == binding
                and str(prior.get("output_sha256") or "") == _sha256_file(output)
            ):
                return output
        columns = 2
        cell_w = CONTACT_THUMBNAIL[0] + 40
        cell_h = CONTACT_THUMBNAIL[1] + 70
        row_count = math.ceil(len(rows) / columns)
        canvas = Image.new("RGB", (columns * cell_w, max(1, row_count) * cell_h), "white")
        draw = ImageDraw.Draw(canvas)
        for index, (photo_id, path) in enumerate(rows):
            x = (index % columns) * cell_w + 20
            y = (index // columns) * cell_h + 40
            with Image.open(path) as raw:
                image = raw.convert("RGB")
                image.thumbnail(CONTACT_THUMBNAIL)
            canvas.paste(image, (x, y))
            draw.text((x, 10 + (index // columns) * cell_h), photo_id, fill="black")
        canvas.save(output, format="PNG")
        self.save_json(
            f"photo-contact-sheets/{binding_path.name}",
            {"binding": binding, "output_sha256": _sha256_file(output)},
        )
        return output

    def reconciliation_prompt(self, defect: Defect, details: list[dict]) -> str:
        identity = defect.external_defect_id or defect.defect_code or defect.id
        compact = []
        for item in details:
            compact.append(
                {
                    "photo_id": item.get("photo_id"),
                    "scope_relevance": item.get("scope_relevance"),
                    "target_link": item.get("target_link"),
                    "viewpoint": item.get("viewpoint"),
                    "barrier_face": item.get("barrier_face"),
                    "visible_summary": _trim(item.get("visible_summary"), 320),
                    "visible_services": item.get("visible_services") or [],
                    "visible_openings": item.get("visible_openings") or [],
                    "distinctive_features": item.get("distinctive_features") or [],
                    "uncertainties": item.get("uncertainties") or [],
                }
            )
        return f"""Reconcile all candidate photographs for ONE CLASSIFIRE defect: {identity}.
A labelled contact sheet is attached. Structured high-resolution photo reviews follow:
{json.dumps(compact, ensure_ascii=False, separators=(",", ":"), default=str)}

Determine which photos depict the same physical service/opening versus different physical subjects.
Return ONLY valid JSON:
{{
  "status": "RECONCILED|INSUFFICIENT_EVIDENCE",
  "photo_groups": [
    {{
      "group_id": "G1",
      "photo_ids": [],
      "relationship": "same_asset_same_side_different_angle|same_service_opposite_barrier_side|same_opening_opposite_barrier_side|different_service_same_opening|different_opening|uncertain_relationship",
      "basis": [],
      "counting_instruction": ""
    }}
  ],
  "counting_decisions": [],
  "opening_count": {{"value": null, "status": "confirmed|inferred|unknown", "basis": []}},
  "service_count": {{"value": null, "status": "confirmed|inferred|unknown", "basis": []}},
  "openings": [],
  "services": [],
  "relationships": [],
  "physical_facts": [],
  "ignored_photo_ids": [],
  "uncertainties": []
}}

Mandatory counting rules:
- Photograph count NEVER equals service count or opening count.
- The same pipe/cable/duct photographed from multiple angles is one Service, not multiple Services.
- The same service photographed on opposite faces of a wall, or top/soffit sides of a floor, remains one
  Service crossing one Opening unless evidence proves otherwise.
- Multiple distinct services passing through one opening are separate Services but one Opening.
- Multiple distinct openings remain separate even when photographed together.
- Only group photos when matching visible features/location/barrier relationships support the match.
- If the relationship between views is materially uncertain, use uncertain_relationship and return
  INSUFFICIENT_EVIDENCE when that uncertainty prevents a defensible physical count.
- Do not select Package 15 systems or pricing.
"""

    def _register_direct_evidence(
        self,
        session: str,
        defect: Defect,
        *,
        evidence_type: str,
        page_number: int | None,
        region_reference: str,
        source_json: dict,
        receipt_name: str,
    ) -> None:
        self.register_observations(
            session,
            [
                {
                    "stored_file_id": self.stored_file_id,
                    "evidence_type": evidence_type,
                    "external_defect_id": defect.external_defect_id or defect.defect_code,
                    "source_reference": self.report_name,
                    "page_number": str(page_number) if page_number is not None else None,
                    "region_reference": region_reference,
                    "evidence_class": "observed",
                    "confidence": _confidence(
                        source_json.get("association_confidence")
                        if "association_confidence" in source_json
                        else source_json.get("confidence"),
                        0.6,
                    ),
                    "source_json": source_json,
                }
            ],
            receipt_name,
        )

    def run_photo_aware_evidence(self, report: Path) -> dict[str, object]:
        rendered = self._render_pages(report)
        inventory_by_page, inventory_by_id = self._ensure_linked_photo_inventory(report)
        defects, defect_pages = self._defects_and_direct_pages()
        session = self.initialize_session("cf-intake-evidence", "16-photo-aware-evidence")
        self.require_tools(
            "cf-intake-evidence",
            session,
            REQUIRED_INTAKE_WRITE_TOOLS,
            "16-photo-aware-effective.json",
        )

        layout_created = 0
        detail_created = 0
        reconciliation_created = 0
        for defect_index, defect in enumerate(defects, start=1):
            identity = defect.external_defect_id or defect.defect_code or defect.id
            pages = defect_pages.get(defect.id) or []
            if not pages:
                print(f"LIMIT photo defect {defect_index}/{len(defects)} {identity} -> no linked source page")
                continue

            candidate_photo_ids: list[str] = []
            ignored_photo_ids: list[str] = []
            for page_number in pages:
                region = f"photo-linkage:page:{page_number}:defect:{identity}"
                existing = self._existing_source(defect.id, PHOTO_LINK_EVIDENCE_TYPE, region)
                page_rows = [row for row in inventory_by_page.get(page_number, []) if not row.get("tiny_artifact")]
                if existing is None:
                    rendered_row = rendered.get(page_number)
                    if rendered_row is None:
                        raise RuntimeError(f"No full-page render for page {page_number}")
                    labelled = self._annotated_page(Path(str(rendered_row["path"])), page_rows, page_number)
                    payload = self.infer_model(
                        prompt=self.photo_link_prompt(defect, page_number, page_rows),
                        receipt_name=f"16-photo-d{defect_index:03d}-p{page_number:03d}-link",
                        files=[labelled],
                        thinking="medium",
                    )
                    model = _json_from_payload(payload, context=f"Photo linkage {identity} page {page_number}")
                    if str(model.get("target_defect_id") or "") != str(identity):
                        raise RuntimeError(f"Photo linkage returned wrong target defect for {identity}")
                    candidate_ids = {str(row["photo_id"]) for row in page_rows}
                    associated = [item for item in _unique_strings(model.get("associated_photo_ids")) if item in candidate_ids]
                    ignored = [item for item in _unique_strings(model.get("ignored_photo_ids")) if item in candidate_ids]
                    uncertain = [item for item in _unique_strings(model.get("uncertain_photo_ids")) if item in candidate_ids]
                    # Resolve overlap conservatively: associated > uncertain > ignored, then retain uncategorised as uncertain.
                    associated_set = set(associated)
                    uncertain_set = set(uncertain) - associated_set
                    ignored_set = set(ignored) - associated_set - uncertain_set
                    missing = candidate_ids - associated_set - uncertain_set - ignored_set
                    uncertain_set.update(missing)
                    source_json = {
                        "source": "full_page_photo_linkage_with_labels",
                        "image_variant_receipt_sha256": self._image_variant_receipt_sha256(),
                        "association_status": str(model.get("association_status") or "AMBIGUOUS").upper(),
                        "association_confidence": _confidence(model.get("association_confidence"), 0.5),
                        "association_basis": model.get("association_basis") or [],
                        "associated_photo_ids": sorted(associated_set),
                        "ignored_photo_ids": sorted(ignored_set),
                        "uncertain_photo_ids": sorted(uncertain_set),
                        "physical_facts": model.get("physical_facts") or [],
                        "uncertainties": model.get("uncertainties") or [],
                        "photo_inventory": [
                            {
                                "photo_id": row["photo_id"],
                                "bbox": row["bbox"],
                                "native_pixels": [row.get("native_width") or row["width"], row.get("native_height") or row["height"]],
                                "decorative_candidate": row.get("decorative_candidate"),
                                "candidate_reasons": row.get("non_scope_candidate_reasons") or [],
                            }
                            for row in page_rows
                        ],
                    }
                    self._register_direct_evidence(
                        session,
                        defect,
                        evidence_type=PHOTO_LINK_EVIDENCE_TYPE,
                        page_number=page_number,
                        region_reference=region,
                        source_json=source_json,
                        receipt_name=f"16-photo-d{defect_index:03d}-p{page_number:03d}-link-register.json",
                    )
                    layout_created += 1
                    existing = source_json
                candidate_photo_ids.extend(existing.get("associated_photo_ids") or [])
                candidate_photo_ids.extend(existing.get("uncertain_photo_ids") or [])
                ignored_photo_ids.extend(existing.get("ignored_photo_ids") or [])

            candidate_photo_ids = list(dict.fromkeys(candidate_photo_ids))
            if len(candidate_photo_ids) > MAX_RECONCILIATION_PHOTOS:
                raise RuntimeError(
                    "Photo reconciliation requires "
                    f"{len(candidate_photo_ids)} photos, exceeding the explicit "
                    f"limit of {MAX_RECONCILIATION_PHOTOS}; no photos were silently truncated."
                )
            details: list[dict] = []
            contact_paths: list[tuple[str, Path]] = []
            for photo_id in candidate_photo_ids:
                row = inventory_by_id.get(photo_id)
                if row is None:
                    continue
                region = f"photo-detail:{photo_id}:defect:{identity}"
                existing_detail = self._existing_source(defect.id, PHOTO_DETAIL_EVIDENCE_TYPE, region)
                if existing_detail is None:
                    detail = self._analyse_photo_detail(report, defect, row, defect_index)
                    source_json = {
                        "source": "linked_original_or_native_or_zoom_photo_vision",
                        "photo_id": photo_id,
                        "image_variant_receipt_sha256": self._image_variant_receipt_sha256(),
                        "image_variant_group_id": row.get("image_variant_group_id"),
                        "scope_relevance": detail.get("scope_relevance"),
                        "target_link": detail.get("target_link"),
                        "visible_summary": detail.get("visible_summary"),
                        "viewpoint": detail.get("viewpoint"),
                        "barrier_face": detail.get("barrier_face"),
                        "visible_services": detail.get("visible_services") or [],
                        "visible_openings": detail.get("visible_openings") or [],
                        "distinctive_features": detail.get("distinctive_features") or [],
                        "physical_facts": detail.get("physical_facts") or [],
                        "uncertainties": detail.get("uncertainties") or [],
                        "zoom_refinement_performed": detail.get("zoom_refinement_performed"),
                        "native_extraction_ok": detail.get("native_extraction_ok"),
                        "full_resolution_status": detail.get("full_resolution_status"),
                        "native_pixels": detail.get("native_pixels"),
                        "source_bbox": detail.get("source_bbox"),
                    }
                    self._register_direct_evidence(
                        session,
                        defect,
                        evidence_type=PHOTO_DETAIL_EVIDENCE_TYPE,
                        page_number=int(row["page_number"]),
                        region_reference=region,
                        source_json=source_json,
                        receipt_name=f"16-photo-d{defect_index:03d}-{photo_id}-detail-register.json",
                    )
                    detail_created += 1
                    existing_detail = source_json
                details.append(existing_detail)
                for source in self._preferred_photo_sources(report, row):
                    source_path = Path(source["path"])
                    if source_path.is_file():
                        label = f"{photo_id} [{source['variant_role']}]"
                        contact_paths.append((label, source_path))

            reconciliation_region = f"photo-reconciliation:defect:{identity}"
            reconciliation = self._existing_source(
                defect.id,
                PHOTO_RECONCILIATION_EVIDENCE_TYPE,
                reconciliation_region,
            )
            if reconciliation is None:
                usable_details = [
                    item
                    for item in details
                    if str(item.get("scope_relevance") or "").lower() != "non_scope"
                    and str(item.get("target_link") or "").lower() != "not_target"
                ]
                if not usable_details or not contact_paths:
                    reconciliation = {
                        "source": "photo_reconciliation",
                        "image_variant_receipt_sha256": self._image_variant_receipt_sha256(),
                        "status": "INSUFFICIENT_EVIDENCE",
                        "photo_groups": [],
                        "counting_decisions": [],
                        "opening_count": {"value": None, "status": "unknown", "basis": []},
                        "service_count": {"value": None, "status": "unknown", "basis": []},
                        "openings": [],
                        "services": [],
                        "relationships": [],
                        "physical_facts": [],
                        "ignored_photo_ids": sorted(set(ignored_photo_ids)),
                        "uncertainties": ["No defect-linked photo set could be reconciled defensibly."],
                    }
                else:
                    contact = self._contact_sheet(contact_paths, defect_index)
                    receipt_tag = self._image_variant_receipt_sha256()[:12]
                    payload = self.infer_model(
                        prompt=self.reconciliation_prompt(defect, usable_details),
                        receipt_name=(
                            f"16-photo-v2-{receipt_tag}-d{defect_index:03d}-reconciliation"
                        ),
                        files=[contact],
                        thinking="high",
                    )
                    model = _json_from_payload(payload, context=f"Photo reconciliation {identity}")
                    reconciliation = {
                        "source": "photo_reconciliation",
                        "image_variant_receipt_sha256": self._image_variant_receipt_sha256(),
                        "status": str(model.get("status") or "INSUFFICIENT_EVIDENCE").upper(),
                        "photo_groups": model.get("photo_groups") or [],
                        "counting_decisions": model.get("counting_decisions") or [],
                        "opening_count": model.get("opening_count"),
                        "service_count": model.get("service_count"),
                        "openings": model.get("openings") or [],
                        "services": model.get("services") or [],
                        "relationships": model.get("relationships") or [],
                        "physical_facts": model.get("physical_facts") or [],
                        "ignored_photo_ids": sorted(
                            set(ignored_photo_ids + _unique_strings(model.get("ignored_photo_ids")))
                        ),
                        "uncertainties": model.get("uncertainties") or [],
                        "photo_ids_reviewed": [item.get("photo_id") for item in usable_details],
                    }
                self._register_direct_evidence(
                    session,
                    defect,
                    evidence_type=PHOTO_RECONCILIATION_EVIDENCE_TYPE,
                    page_number=pages[0] if pages else None,
                    region_reference=reconciliation_region,
                    source_json=reconciliation,
                    receipt_name=f"16-photo-d{defect_index:03d}-reconciliation-register.json",
                )
                reconciliation_created += 1
            print(
                f"PASS photo defect {defect_index}/{len(defects)} {identity} -> "
                f"candidates {len(candidate_photo_ids)}, reconciliation {str(reconciliation.get('status') or '').lower()}"
            )

        result = {
            "defect_count": len(defects),
            "photo_linkage_created": layout_created,
            "photo_detail_created": detail_created,
            "photo_reconciliation_created": reconciliation_created,
            "photo_inventory_occurrences": len(inventory_by_id),
        }
        self.save_json("16-photo-aware-summary.json", result)
        return result

    def run(self) -> dict:
        print("CLASSIFIRE full-resolution photo-aware real-report UAT")
        print(f"Run ID: {self.run_id}")
        print(f"Estimate ID: {self.estimate_id}")
        print(f"Receipts: {self.receipt_dir}")
        self.preflight()
        manifest = self.stage_visuals()
        intake_report = self.workspace_report("cf-intake-evidence")
        intake_state = self.run_windows_safe_intake(intake_report, manifest)
        photo_state = self.run_photo_aware_evidence(intake_report)
        final_state = self.run_defectwise_physical()
        final_state["run_id"] = self.run_id
        final_state["intake_coverage_ok"] = intake_state["coverage_ok"]
        final_state["photo_evidence"] = photo_state
        final_state["status"] = (
            "PHYSICAL_MODEL_LOCKED"
            if final_state["physical_lock_count"] > 0
            else "PARTIAL_SOURCE_OR_PHYSICAL_LIMITATION"
        )
        self.save_json("71-photo-aware-final-state.json", final_state)
        print(json.dumps(final_state, indent=2, default=str))
        return final_state


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run full-resolution photo-aware CLASSIFIRE real-report UAT."
    )
    parser.add_argument("--run-id")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()

    root = repo_root()
    _receipt_path, receipt = load_receipt(root, args.run_id)
    controller = PhotoAwareController(
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
        print(f"CLASSIFIRE photo-aware real-report UAT failed: {exc}", file=sys.stderr)
        return 1
    finally:
        controller.close()


if __name__ == "__main__":
    raise SystemExit(main())
