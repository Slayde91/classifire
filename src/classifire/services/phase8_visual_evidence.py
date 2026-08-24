"""Read-only retained-evidence adapter for Phase 8 visual proposals.

This module resolves current canonical EvidenceSource and StoredFile records
into the strict content-free manifest accepted by ProposalOnlyVisualController.
It performs no inference, network, database write, admission, canonical
submission, or lock operation.
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import StoredFile
from ..physical_models import Defect, EvidenceSource
from .phase8_visual_proposal import (
    VISUAL_EVIDENCE_MANIFEST_SCHEMA,
    canonical_json_sha256,
    validate_visual_evidence_manifest,
)

VISUAL_EVIDENCE_METADATA_KEY = "phase8_visual_inference"

_ALLOWED_IMAGE_MIMES = frozenset(
    {
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/webp",
    }
)
_ALLOWED_SCAN_STATUSES = frozenset({"clean", "not_configured"})
_EXPECTED_METADATA_KEYS = frozenset(
    {
        "evidence_role",
        "relationship",
        "parent_evidence_source_id",
        "inference_allowed",
        "validation_only",
    }
)
_MAXIMUM_IMAGE_BYTES = 25 * 1024 * 1024
_MAXIMUM_PIXELS = 50_000_000
_MAXIMUM_SIDE_PX = 12_000


class Phase8VisualEvidenceError(RuntimeError):
    """A stable, path-free failure from retained visual-evidence resolution."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Phase 8 visual evidence failed: {code}.")


@dataclass(frozen=True, slots=True)
class RetainedVisualEvidenceFile:
    evidence_id: str
    path: Path
    sha256: str
    size_bytes: int
    media_type: str


@dataclass(frozen=True, slots=True)
class RetainedVisualEvidencePacket:
    manifest: dict[str, Any]
    files: tuple[RetainedVisualEvidenceFile, ...]

    @property
    def manifest_sha256(self) -> str:
        return canonical_json_sha256(self.manifest)


def _normalise_mime(value: object) -> str:
    mime = str(value or "").strip().lower()
    return "image/jpeg" if mime == "image/jpg" else mime


def _page_number(value: object) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text.isdecimal():
        raise Phase8VisualEvidenceError("PAGE_NUMBER_INVALID")
    number = int(text)
    if number < 1:
        raise Phase8VisualEvidenceError("PAGE_NUMBER_INVALID")
    return number


def _metadata(evidence: EvidenceSource) -> dict[str, Any]:
    source_json = evidence.source_json
    if not isinstance(source_json, dict):
        raise Phase8VisualEvidenceError("METADATA_REQUIRED")
    value = source_json.get(VISUAL_EVIDENCE_METADATA_KEY)
    if not isinstance(value, dict) or set(value) != _EXPECTED_METADATA_KEYS:
        raise Phase8VisualEvidenceError("METADATA_INVALID")
    parent_id = value.get("parent_evidence_source_id")
    if parent_id is not None and (not isinstance(parent_id, str) or not parent_id.strip()):
        raise Phase8VisualEvidenceError("METADATA_INVALID")
    if not isinstance(value.get("evidence_role"), str) or not value["evidence_role"].strip():
        raise Phase8VisualEvidenceError("METADATA_INVALID")
    if not isinstance(value.get("relationship"), str) or not value["relationship"].strip():
        raise Phase8VisualEvidenceError("METADATA_INVALID")
    if value.get("inference_allowed") is not True:
        raise Phase8VisualEvidenceError("EVIDENCE_NOT_APPROVED_FOR_INFERENCE")
    if value.get("validation_only") is not False:
        raise Phase8VisualEvidenceError("VALIDATION_ONLY_EVIDENCE_FORBIDDEN")
    return value


def _storage_path(storage_root: Path, stored: StoredFile) -> Path:
    root = storage_root.resolve(strict=True)
    raw_path = Path(stored.storage_path)
    path = (raw_path if raw_path.is_absolute() else Path.cwd() / raw_path).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise Phase8VisualEvidenceError("FILE_OUTSIDE_STORAGE_ROOT") from exc
    if not path.is_file():
        raise Phase8VisualEvidenceError("STORED_FILE_UNAVAILABLE")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _image_dimensions(path: Path, *, media_type: str) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
            detected_mime = _normalise_mime(Image.MIME.get(image.format or ""))
    except (OSError, UnidentifiedImageError) as exc:
        raise Phase8VisualEvidenceError("IMAGE_DECODE_FAILED") from exc
    if detected_mime != media_type:
        raise Phase8VisualEvidenceError("IMAGE_MEDIA_TYPE_MISMATCH")
    if (
        width < 1
        or height < 1
        or width > _MAXIMUM_SIDE_PX
        or height > _MAXIMUM_SIDE_PX
        or width * height > _MAXIMUM_PIXELS
    ):
        raise Phase8VisualEvidenceError("IMAGE_DIMENSIONS_OUT_OF_POLICY")
    return width, height


def _defect(
    db: Session,
    *,
    estimate_id: str,
    defect_reference: str,
) -> Defect:
    matches = db.scalars(
        select(Defect)
        .where(
            Defect.estimate_id == estimate_id,
            or_(
                Defect.external_defect_id == defect_reference,
                Defect.defect_code == defect_reference,
            ),
        )
        .order_by(Defect.id)
    ).all()
    if not matches:
        raise Phase8VisualEvidenceError("DEFECT_NOT_FOUND")
    if len(matches) != 1:
        raise Phase8VisualEvidenceError("DEFECT_REFERENCE_AMBIGUOUS")
    return matches[0]


def build_retained_visual_evidence_packet(
    db: Session,
    *,
    storage_root: Path,
    estimate_id: str,
    defect_reference: str,
    allowed_evidence_source_ids: Collection[str] | None = None,
) -> RetainedVisualEvidencePacket:
    """Build a verified defect-level visual packet without mutating state."""

    estimate_id = estimate_id.strip()
    defect_reference = defect_reference.strip()
    if not estimate_id:
        raise Phase8VisualEvidenceError("ESTIMATE_ID_REQUIRED")
    if not defect_reference:
        raise Phase8VisualEvidenceError("DEFECT_REFERENCE_REQUIRED")
    if not storage_root.is_dir():
        raise Phase8VisualEvidenceError("STORAGE_ROOT_UNAVAILABLE")

    allowed_ids: frozenset[str] | None = None
    if allowed_evidence_source_ids is not None:
        raw_ids = list(allowed_evidence_source_ids)
        if not raw_ids or any(
            not isinstance(value, str) or not value.strip() or value != value.strip()
            for value in raw_ids
        ):
            raise Phase8VisualEvidenceError("EVIDENCE_SCOPE_INVALID")
        allowed_ids = frozenset(raw_ids)
        if len(allowed_ids) != len(raw_ids):
            raise Phase8VisualEvidenceError("EVIDENCE_SCOPE_INVALID")

    defect = _defect(
        db,
        estimate_id=estimate_id,
        defect_reference=defect_reference,
    )
    evidence_rows = db.scalars(
        select(EvidenceSource)
        .where(
            EvidenceSource.estimate_id == estimate_id,
            EvidenceSource.defect_id == defect.id,
            EvidenceSource.status == "active",
        )
        .order_by(EvidenceSource.id)
    ).all()
    if not evidence_rows:
        raise Phase8VisualEvidenceError("ACTIVE_EVIDENCE_REQUIRED")
    visual_evidence_rows = [
        evidence
        for evidence in evidence_rows
        if isinstance(evidence.source_json, dict)
        and VISUAL_EVIDENCE_METADATA_KEY in evidence.source_json
        and (allowed_ids is None or evidence.id in allowed_ids)
    ]
    if not visual_evidence_rows:
        raise Phase8VisualEvidenceError("ACTIVE_VISUAL_EVIDENCE_REQUIRED")

    artifacts: list[dict[str, Any]] = []
    files: list[RetainedVisualEvidenceFile] = []
    for evidence in visual_evidence_rows:
        metadata = _metadata(evidence)
        if not evidence.stored_file_id:
            raise Phase8VisualEvidenceError("STORED_FILE_REQUIRED")
        stored = db.get(StoredFile, evidence.stored_file_id)
        if stored is None:
            raise Phase8VisualEvidenceError("STORED_FILE_NOT_FOUND")
        if stored.purpose != "technical_evidence":
            raise Phase8VisualEvidenceError("STORED_FILE_PURPOSE_FORBIDDEN")
        if stored.immutable is not True:
            raise Phase8VisualEvidenceError("STORED_FILE_NOT_IMMUTABLE")
        if str(stored.malware_scan_status or "").strip().lower() not in _ALLOWED_SCAN_STATUSES:
            raise Phase8VisualEvidenceError("STORED_FILE_SCAN_STATUS_FORBIDDEN")
        media_type = _normalise_mime(stored.media_type)
        if media_type not in _ALLOWED_IMAGE_MIMES:
            raise Phase8VisualEvidenceError("VISUAL_MEDIA_TYPE_FORBIDDEN")
        if stored.size_bytes < 1 or stored.size_bytes > _MAXIMUM_IMAGE_BYTES:
            raise Phase8VisualEvidenceError("IMAGE_SIZE_OUT_OF_POLICY")

        path = _storage_path(storage_root, stored)
        actual_size = path.stat().st_size
        if actual_size != stored.size_bytes:
            raise Phase8VisualEvidenceError("FILE_SIZE_MISMATCH")
        actual_sha256 = _sha256(path)
        if actual_sha256.casefold() != stored.sha256.casefold():
            raise Phase8VisualEvidenceError("FILE_DIGEST_MISMATCH")
        if (
            not isinstance(evidence.sha256, str)
            or actual_sha256.casefold() != evidence.sha256.casefold()
        ):
            raise Phase8VisualEvidenceError("EVIDENCE_DIGEST_MISMATCH")
        width, height = _image_dimensions(path, media_type=media_type)

        evidence_id = evidence.id
        parent_id = metadata["parent_evidence_source_id"]
        artifacts.append(
            {
                "evidence_id": evidence_id,
                "sha256": actual_sha256,
                "size_bytes": actual_size,
                "media_type": media_type,
                "inference_allowed": True,
                "validation_only": False,
                "provenance": {
                    "source_reference": f"evidence-source:{evidence_id}",
                    "page_number": _page_number(evidence.page_number),
                    "region_reference": (
                        evidence.region_reference.strip()
                        if isinstance(evidence.region_reference, str)
                        and evidence.region_reference.strip()
                        else None
                    ),
                    "evidence_class": evidence.evidence_class,
                    "evidence_role": metadata["evidence_role"].strip(),
                    "relationship": metadata["relationship"].strip(),
                    "parent_evidence_id": parent_id.strip() if isinstance(parent_id, str) else None,
                    "pixel_width": width,
                    "pixel_height": height,
                },
            }
        )
        files.append(
            RetainedVisualEvidenceFile(
                evidence_id=evidence_id,
                path=path,
                sha256=actual_sha256,
                size_bytes=actual_size,
                media_type=media_type,
            )
        )

    manifest = {
        "schema": VISUAL_EVIDENCE_MANIFEST_SCHEMA,
        "estimate_id": estimate_id,
        "defect_reference": defect_reference,
        "human_reference_included": False,
        "artifacts": artifacts,
    }
    errors = validate_visual_evidence_manifest(manifest, estimate_id=estimate_id)
    if errors:
        raise Phase8VisualEvidenceError("MANIFEST_INVALID")
    return RetainedVisualEvidencePacket(
        manifest=manifest,
        files=tuple(files),
    )


__all__ = [
    "Phase8VisualEvidenceError",
    "RetainedVisualEvidenceFile",
    "RetainedVisualEvidencePacket",
    "VISUAL_EVIDENCE_METADATA_KEY",
    "build_retained_visual_evidence_packet",
]
