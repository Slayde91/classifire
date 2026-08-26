"""Retain one verified linked original as governed visual evidence.

The retrieval service proves that a downloaded JPEG is bound to an embedded
report thumbnail.  This module performs the separate persistence step: it
revalidates the proof-bearing result, enforces the physical-model mutation
guard, retains immutable bytes, and records parent-linked provenance.  It
flushes but never commits the caller's transaction.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import Estimate, StoredFile
from ..physical_models import Defect, EvidenceSource
from .linked_image_retrieval import (
    DEFAULT_LINKED_IMAGE_POLICY,
    READY_STATUSES,
    LinkedImageError,
    LinkedImageMalwareDetectedError,
    LinkedImagePolicy,
    LinkedImageResult,
    preferred_verified_linked_path,
)
from .malware_scan_attestations import (
    MalwareScanAttestationError,
    append_malware_scan_attestation,
)
from .malware_scanning import (
    MalwareDetectedError,
    MalwareScanError,
    MalwareScanner,
    MalwareScanResult,
    require_clean_bytes,
)
from .phase8_visual_evidence import VISUAL_EVIDENCE_METADATA_KEY
from .physical_mutation_guard import PhysicalMutationError, require_evidence_intake
from .storage import (
    StoredFileSecurityError,
    record_detected_sha,
    require_clean_stored_file_for_session,
)
from .workflow import WorkflowTransitionError

LINKED_IMAGE_EVIDENCE_SCHEMA = "CLASSIFIRE-LINKED-IMAGE-EVIDENCE-v1"
_HEX_SHA256 = frozenset("0123456789abcdef")
_VISUAL_MEDIA_TYPES = frozenset({"image/gif", "image/jpeg", "image/png", "image/webp"})
_PARENT_METADATA_KEYS = frozenset(
    {
        "evidence_role",
        "relationship",
        "parent_evidence_source_id",
        "inference_allowed",
        "validation_only",
    }
)


_REPORT_DERIVED_PARENT_EVIDENCE_TYPE = "defect_photo_detail_review"


class LinkedImageEvidenceError(RuntimeError):
    """A stable, path-free linked-image retention failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Linked image evidence retention failed: {code}.")


class LinkedImageMalwareQuarantinedError(LinkedImageEvidenceError):
    """Carries the safe exact-byte verdict across a caller savepoint rollback."""

    def __init__(self, result: MalwareScanResult) -> None:
        self.result = result
        super().__init__("MALWARE_DETECTED")


def _require_clean_retained_bytes(
    malware_scanner: MalwareScanner,
    payload: bytes,
) -> MalwareScanResult:
    try:
        return require_clean_bytes(malware_scanner, payload)
    except MalwareDetectedError as exc:
        raise LinkedImageMalwareDetectedError(exc.result) from None
    except MalwareScanError as exc:
        raise LinkedImageEvidenceError(exc.code) from None


@dataclass(frozen=True, slots=True)
class LinkedImageEvidenceRetention:
    evidence: EvidenceSource
    stored_file: StoredFile
    evidence_created: bool
    stored_file_created: bool


def _normalised_sha256(value: object, *, code: str) -> str:
    text = str(value or "").strip().lower()
    if len(text) != 64 or any(character not in _HEX_SHA256 for character in text):
        raise LinkedImageEvidenceError(code)
    return text


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _contained_file(storage_root: Path, stored: StoredFile) -> Path:
    try:
        root = storage_root.resolve(strict=True)
        raw_path = Path(stored.storage_path)
        path = (raw_path if raw_path.is_absolute() else Path.cwd() / raw_path).resolve(strict=True)
        path.relative_to(root)
    except (OSError, ValueError) as exc:
        raise LinkedImageEvidenceError("STORED_FILE_INVALID") from exc
    if not path.is_file():
        raise LinkedImageEvidenceError("STORED_FILE_INVALID")
    return path


def _validate_retained_image_identity(
    storage_root: Path,
    stored: StoredFile,
    expected_sha256: str,
) -> None:
    if (
        stored.purpose != "technical_evidence"
        or stored.immutable is not True
        or str(stored.media_type or "").strip().lower() not in {"image/jpeg", "image/jpg"}
        or stored.sha256.lower() != expected_sha256
    ):
        raise LinkedImageEvidenceError("STORED_FILE_INVALID")
    path = _contained_file(storage_root, stored)
    try:
        if path.stat().st_size != stored.size_bytes or _sha256_file(path) != expected_sha256:
            raise LinkedImageEvidenceError("STORED_FILE_INVALID")
    except OSError as exc:
        raise LinkedImageEvidenceError("STORED_FILE_INVALID") from exc


def _validate_stored_file(
    db: Session,
    storage_root: Path,
    stored: StoredFile,
    expected_sha256: str,
) -> None:
    _validate_retained_image_identity(storage_root, stored, expected_sha256)
    try:
        require_clean_stored_file_for_session(
            db,
            stored,
            storage_root=storage_root,
            allowed_purposes={"technical_evidence"},
            expected_sha256=expected_sha256,
        )
    except StoredFileSecurityError:
        raise LinkedImageEvidenceError("STORED_FILE_INVALID") from None


def _locked_stored_file_by_id(db: Session, stored_file_id: str) -> StoredFile | None:
    return db.scalar(
        select(StoredFile)
        .where(StoredFile.id == stored_file_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _locked_stored_file_by_sha(db: Session, content_sha256: str) -> StoredFile | None:
    return db.scalar(
        select(StoredFile)
        .where(StoredFile.sha256 == content_sha256)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _locked_parent_evidence(db: Session, evidence_id: str) -> EvidenceSource | None:
    return db.scalar(
        select(EvidenceSource)
        .where(EvidenceSource.id == evidence_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _locked_defect(db: Session, defect_id: str) -> Defect | None:
    """Serialise one defect's linked-evidence replay identity."""

    return db.scalar(
        select(Defect)
        .where(Defect.id == defect_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _validate_parent(
    db: Session,
    storage_root: Path,
    parent: EvidenceSource,
    stored: StoredFile,
    *,
    result: LinkedImageResult,
    source_report_sha256: str | None,
) -> None:
    if str(parent.page_number or "").strip() != str(result.page_number):
        raise LinkedImageEvidenceError("PARENT_PAGE_MISMATCH")
    if _is_report_derived_parent(parent, stored):
        _validate_report_derived_parent(
            db,
            storage_root,
            parent,
            stored,
            result=result,
            source_report_sha256=source_report_sha256,
        )
        return
    if (
        parent.status != "active"
        or parent.stored_file_id != stored.id
        or parent.sha256 is None
        or parent.sha256.lower()
        != _normalised_sha256(result.embedded_sha256, code="EMBEDDED_DIGEST_INVALID")
        or stored.sha256.lower() != parent.sha256.lower()
        or stored.purpose != "technical_evidence"
        or stored.immutable is not True
        or str(stored.media_type or "").strip().lower() not in _VISUAL_MEDIA_TYPES
        or stored.size_bytes < 1
        or stored.size_bytes > DEFAULT_LINKED_IMAGE_POLICY.maximum_image_bytes
    ):
        raise LinkedImageEvidenceError("PARENT_EVIDENCE_INVALID")
    if str(parent.region_reference or "").strip() != result.photo_id:
        raise LinkedImageEvidenceError("PARENT_PHOTO_MISMATCH")
    metadata = parent.source_json
    visual = metadata.get(VISUAL_EVIDENCE_METADATA_KEY) if isinstance(metadata, dict) else None
    if (
        not isinstance(visual, dict)
        or set(visual) != _PARENT_METADATA_KEYS
        or visual.get("evidence_role") != "primary_detail"
        or visual.get("relationship") != "embedded_image"
        or visual.get("parent_evidence_source_id") is not None
        or visual.get("inference_allowed") is not True
        or visual.get("validation_only") is not False
    ):
        raise LinkedImageEvidenceError("PARENT_METADATA_INVALID")
    try:
        require_clean_stored_file_for_session(
            db,
            stored,
            storage_root=storage_root,
            allowed_purposes={"technical_evidence"},
            expected_sha256=parent.sha256,
        )
    except StoredFileSecurityError:
        raise LinkedImageEvidenceError("PARENT_EVIDENCE_INVALID") from None


def _is_report_derived_parent(parent: EvidenceSource, stored: StoredFile) -> bool:
    return (
        parent.evidence_type == _REPORT_DERIVED_PARENT_EVIDENCE_TYPE
        and str(stored.media_type or "").strip().lower() == "application/pdf"
    )


def _normalised_bbox(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        bbox = tuple(float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if any(not math.isfinite(item) for item in bbox):
        return None
    return bbox  # type: ignore[return-value]


def _validate_report_derived_parent(
    db: Session,
    storage_root: Path,
    parent: EvidenceSource,
    stored: StoredFile,
    *,
    result: LinkedImageResult,
    source_report_sha256: str | None,
) -> None:
    report_sha256 = _normalised_sha256(
        source_report_sha256,
        code="PARENT_EVIDENCE_INVALID",
    )
    metadata = parent.source_json
    native_pixels = metadata.get("native_pixels") if isinstance(metadata, dict) else None
    source_bbox = metadata.get("source_bbox") if isinstance(metadata, dict) else None
    normalised_source_bbox = _normalised_bbox(source_bbox)
    normalised_result_bbox = _normalised_bbox(result.photo_bbox)
    if (
        parent.status != "active"
        or parent.stored_file_id != stored.id
        or parent.sha256 is None
        or parent.sha256.lower() != report_sha256
        or stored.sha256.lower() != report_sha256
        or stored.purpose != "project_evidence"
        or stored.immutable is not True
        or str(stored.media_type or "").strip().lower() != "application/pdf"
        or not isinstance(metadata, dict)
        or metadata.get("source") != "native_or_zoom_photo_vision"
        or metadata.get("photo_id") != result.photo_id
        or metadata.get("native_extraction_ok") is not True
        or not isinstance(native_pixels, list)
        or len(native_pixels) != 2
        or any(
            isinstance(item, bool) or not isinstance(item, int) or item < 1
            for item in native_pixels
        )
        or result.embedded_width != native_pixels[0]
        or result.embedded_height != native_pixels[1]
        or normalised_source_bbox is None
        or normalised_result_bbox is None
        or normalised_source_bbox != normalised_result_bbox
    ):
        raise LinkedImageEvidenceError("PARENT_EVIDENCE_INVALID")
    try:
        require_clean_stored_file_for_session(
            db,
            stored,
            storage_root=storage_root,
            allowed_purposes={"project_evidence"},
            expected_sha256=report_sha256,
        )
    except StoredFileSecurityError:
        raise LinkedImageEvidenceError("PARENT_EVIDENCE_INVALID") from None


def _verified_source(
    result: LinkedImageResult,
    retrieval_root: Path,
    policy: LinkedImagePolicy,
    malware_scanner: MalwareScanner,
) -> tuple[bytes, str, MalwareScanResult]:
    if result.status.upper() not in READY_STATUSES:
        raise LinkedImageEvidenceError("RESULT_NOT_VERIFIED")
    if (
        not isinstance(result.photo_id, str)
        or not result.photo_id.strip()
        or len(result.photo_id) > 300
        or result.photo_id != result.photo_id.strip()
        or result.page_number < 1
    ):
        raise LinkedImageEvidenceError("RESULT_IDENTITY_INVALID")
    content_sha256 = _normalised_sha256(result.content_sha256, code="CONTENT_DIGEST_INVALID")
    _normalised_sha256(result.embedded_sha256, code="EMBEDDED_DIGEST_INVALID")
    _normalised_sha256(result.uri_sha256, code="URI_DIGEST_INVALID")
    _normalised_sha256(result.path_sha256, code="URI_PATH_DIGEST_INVALID")
    if (
        result.content_type != "image/jpeg"
        or not isinstance(result.width, int)
        or not isinstance(result.height, int)
        or result.width < 1
        or result.height < 1
        or max(result.width, result.height) > policy.maximum_side_px
        or result.width * result.height > policy.maximum_pixels
        or result.host not in policy.allowed_hosts
        or result.suffix not in policy.allowed_suffixes
        or frozenset(result.query_keys) != policy.expected_query_keys
        or result.overlap_ratio is None
        or result.overlap_ratio < policy.minimum_overlap_ratio
        or not result.annotation_xrefs
        or result.thumbnail_transform not in policy.thumbnail_transforms
        or result.thumbnail_hash_distance is None
        or result.thumbnail_mean_error is None
        or result.embedded_pixel_sha256 is None
        or result.thumbnail_luma_stddev is None
        or result.thumbnail_entropy_bits is None
        or result.thumbnail_mean_gradient is None
        or result.thumbnail_matching_tiles is None
        or result.thumbnail_tile_count is None
        or result.thumbnail_worst_tile_mean_error is None
        or result.thumbnail_comparison_group_count is None
        or result.usable_detail_gradient_gain_ratio is None
        or result.usable_detail_residual is None
        or result.usable_detail_matching_tiles is None
        or not isinstance(result.received_bytes, int)
        or result.received_bytes < 1
        or result.stored_path is None
    ):
        raise LinkedImageEvidenceError("RESULT_PROOF_INCOMPLETE")
    _normalised_sha256(result.embedded_pixel_sha256, code="RESULT_PROOF_INCOMPLETE")
    try:
        path = preferred_verified_linked_path(
            result.receipt_row(),
            retrieval_root,
            malware_scanner=malware_scanner,
            policy=policy,
        )
    except LinkedImageMalwareDetectedError:
        raise
    except LinkedImageError as exc:
        if exc.code.startswith("MALWARE_"):
            raise LinkedImageEvidenceError(exc.code) from None
        raise
    if path is None:
        raise LinkedImageEvidenceError("VERIFIED_SOURCE_INVALID")
    try:
        body = path.read_bytes()
    except OSError as exc:
        raise LinkedImageEvidenceError("VERIFIED_SOURCE_INVALID") from exc
    scan_result = _require_clean_retained_bytes(malware_scanner, body)
    if (
        _sha256_bytes(body) != content_sha256
        or len(body) != result.received_bytes
        or len(body) > policy.maximum_image_bytes
        or scan_result.content_sha256 != content_sha256
        or scan_result.content_size_bytes != len(body)
    ):
        raise LinkedImageEvidenceError("VERIFIED_SOURCE_INVALID")
    return body, content_sha256, scan_result


def _provenance(result: LinkedImageResult) -> dict[str, Any]:
    return {
        "schema": LINKED_IMAGE_EVIDENCE_SCHEMA,
        "photo_id": result.photo_id,
        "page_number": result.page_number,
        "retrieval_status": result.status.upper(),
        "embedded_sha256": str(result.embedded_sha256).lower(),
        "content_sha256": str(result.content_sha256).lower(),
        "uri_sha256": str(result.uri_sha256).lower(),
        "origin_host": result.host,
        "uri_path_sha256": str(result.path_sha256).lower(),
        "query_key_names": list(result.query_keys),
        "decoded_width": result.width,
        "decoded_height": result.height,
        "thumbnail_transform": result.thumbnail_transform,
        "thumbnail_crop_box_normalized": (
            list(result.thumbnail_crop_box) if result.thumbnail_crop_box else None
        ),
        "thumbnail_hash_distance": result.thumbnail_hash_distance,
        "thumbnail_mean_error": result.thumbnail_mean_error,
        "embedded_pixel_sha256": result.embedded_pixel_sha256,
        "usable_detail_gradient_gain_ratio": result.usable_detail_gradient_gain_ratio,
        "usable_detail_residual": result.usable_detail_residual,
        "usable_detail_matching_tiles": result.usable_detail_matching_tiles,
    }


def _source_reference(result: LinkedImageResult) -> str:
    return f"phase8-linked-original:{result.page_number}:{result.photo_id}"


def _existing_evidence(
    db: Session,
    *,
    estimate_id: str,
    defect_id: str,
    source_reference: str,
    parent_id: str,
    content_sha256: str,
    source_json: dict[str, Any],
) -> EvidenceSource | None:
    matches = db.scalars(
        select(EvidenceSource)
        .where(
            EvidenceSource.estimate_id == estimate_id,
            EvidenceSource.defect_id == defect_id,
            EvidenceSource.source_reference == source_reference,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    if not matches:
        return None
    if len(matches) != 1:
        raise LinkedImageEvidenceError("EVIDENCE_REPLAY_CONFLICT")
    existing = matches[0]
    metadata = existing.source_json if isinstance(existing.source_json, dict) else {}
    visual = metadata.get(VISUAL_EVIDENCE_METADATA_KEY)
    if (
        existing.status != "active"
        or existing.sha256 is None
        or existing.sha256.lower() != content_sha256
        or existing.evidence_type != "inspection_photo"
        or existing.evidence_class != "observed"
        or existing.page_number != str(source_json["linked_image_retrieval"]["page_number"])
        or existing.region_reference != source_json["linked_image_retrieval"]["photo_id"]
        or visual != source_json[VISUAL_EVIDENCE_METADATA_KEY]
        or metadata.get("linked_image_retrieval") != source_json["linked_image_retrieval"]
        or not isinstance(visual, dict)
        or visual.get("parent_evidence_source_id") != parent_id
        or not existing.stored_file_id
    ):
        raise LinkedImageEvidenceError("EVIDENCE_REPLAY_CONFLICT")
    return existing


def _accept_clean_existing_linked_image(
    db: Session,
    *,
    storage_root: Path,
    stored: StoredFile,
    content_sha256: str,
    scan_result: MalwareScanResult,
    operator_reference: str,
) -> None:
    if str(stored.malware_scan_status or "").strip().lower() == "infected":
        raise LinkedImageEvidenceError("STORED_FILE_MALWARE_BLOCKED")
    _validate_retained_image_identity(storage_root, stored, content_sha256)
    if (
        scan_result.content_sha256 != content_sha256
        or scan_result.content_size_bytes != stored.size_bytes
    ):
        raise LinkedImageEvidenceError("MALWARE_SCAN_RESULT_MISMATCH")
    # Reuse may extend an existing attested-clean lineage, but a new scan must
    # not silently promote pending or legacy status-only evidence.
    _validate_stored_file(db, storage_root, stored, content_sha256)
    try:
        append_malware_scan_attestation(
            db,
            stored_file_id=stored.id,
            result=scan_result,
            scan_source="linked_image_retention",
            actor=None,
            actor_type="human_operator",
            actor_name=operator_reference,
        )
    except MalwareScanAttestationError as exc:
        if exc.code == "MALWARE_SCAN_ATTESTATION_NOT_CLEAN":
            raise LinkedImageEvidenceError("STORED_FILE_MALWARE_BLOCKED") from None
        raise
    _validate_stored_file(db, storage_root, stored, content_sha256)


def _store_bytes(
    db: Session,
    *,
    storage_root: Path,
    body: bytes,
    content_sha256: str,
    scan_result: MalwareScanResult,
    operator_reference: str,
) -> tuple[StoredFile, bool]:
    existing = _locked_stored_file_by_sha(db, content_sha256)
    if existing is not None:
        _accept_clean_existing_linked_image(
            db,
            storage_root=storage_root,
            stored=existing,
            content_sha256=content_sha256,
            scan_result=scan_result,
            operator_reference=operator_reference,
        )
        return existing, False

    root = storage_root.resolve(strict=True)
    target = (root / content_sha256[:2] / content_sha256[2:4] / f"{content_sha256}.jpg").resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise LinkedImageEvidenceError("STORAGE_PATH_INVALID") from exc
    temporary_name: str | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not target.is_file() or _sha256_file(target) != content_sha256:
                raise LinkedImageEvidenceError("STORAGE_CONTENT_COLLISION")
        else:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix="linked-evidence-",
                suffix=".part",
                dir=target.parent,
                delete=False,
            ) as temporary:
                temporary.write(body)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_name = temporary.name
            if _sha256_file(Path(temporary_name)) != content_sha256:
                raise LinkedImageEvidenceError("STORAGE_HASH_MISMATCH")

        stored = StoredFile(
            original_filename=f"linked-image-{content_sha256[:12]}.jpg",
            media_type="image/jpeg",
            storage_path=str(target),
            sha256=content_sha256,
            size_bytes=len(body),
            purpose="technical_evidence",
            malware_scan_status="pending_attestation",
            immutable=True,
        )
        try:
            with db.begin_nested():
                db.add(stored)
                db.flush()
                append_malware_scan_attestation(
                    db,
                    stored_file_id=stored.id,
                    result=scan_result,
                    scan_source="linked_image_retention",
                    actor=None,
                    actor_type="human_operator",
                    actor_name=operator_reference,
                )
                if temporary_name is not None:
                    try:
                        os.rename(temporary_name, target)
                        temporary_name = None
                    except FileExistsError:
                        if not target.is_file() or _sha256_file(target) != content_sha256:
                            raise LinkedImageEvidenceError(
                                "STORAGE_CONTENT_COLLISION"
                            ) from None
        except IntegrityError as exc:
            winner = _locked_stored_file_by_sha(db, content_sha256)
            if winner is None:  # pragma: no cover - database invariant failure.
                raise LinkedImageEvidenceError("STORAGE_PERSISTENCE_CONFLICT") from exc
            _accept_clean_existing_linked_image(
                db,
                storage_root=storage_root,
                stored=winner,
                content_sha256=content_sha256,
                scan_result=scan_result,
                operator_reference=operator_reference,
            )
            return winner, False
        _validate_stored_file(db, storage_root, stored, content_sha256)
        return stored, True
    except LinkedImageEvidenceError:
        raise
    except OSError as exc:
        raise LinkedImageEvidenceError("STORAGE_FAILURE") from exc
    finally:
        if temporary_name:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass


def retain_verified_linked_image(
    db: Session,
    *,
    storage_root: Path,
    retrieval_root: Path,
    estimate_id: str,
    parent_evidence_source_id: str,
    result: LinkedImageResult,
    operator_reference: str,
    malware_scanner: MalwareScanner,
    policy: LinkedImagePolicy = DEFAULT_LINKED_IMAGE_POLICY,
    source_report_sha256: str | None = None,
) -> LinkedImageEvidenceRetention:
    """Retain verified bytes and provenance without committing the transaction."""

    estimate_id = str(estimate_id or "").strip()
    parent_evidence_source_id = str(parent_evidence_source_id or "").strip()
    operator_reference = str(operator_reference or "").strip()
    if not estimate_id or not parent_evidence_source_id or not operator_reference:
        raise LinkedImageEvidenceError("RETENTION_CONTEXT_INVALID")
    if not storage_root.is_dir() or not retrieval_root.is_dir():
        raise LinkedImageEvidenceError("RETENTION_ROOT_UNAVAILABLE")

    estimate = db.get(Estimate, estimate_id)
    if estimate is None:
        raise LinkedImageEvidenceError("ESTIMATE_NOT_FOUND")
    try:
        require_evidence_intake(db, estimate)
    except (PhysicalMutationError, WorkflowTransitionError) as exc:
        raise LinkedImageEvidenceError("EVIDENCE_MUTATION_FORBIDDEN") from exc

    parent = _locked_parent_evidence(db, parent_evidence_source_id)
    if parent is None or parent.estimate_id != estimate.id or parent.defect_id is None:
        raise LinkedImageEvidenceError("PARENT_EVIDENCE_INVALID")
    parent_stored = (
        _locked_stored_file_by_id(db, parent.stored_file_id)
        if parent.stored_file_id
        else None
    )
    if parent_stored is None:
        raise LinkedImageEvidenceError("PARENT_EVIDENCE_INVALID")
    _validate_parent(
        db,
        storage_root,
        parent,
        parent_stored,
        result=result,
        source_report_sha256=source_report_sha256,
    )

    try:
        body, content_sha256, scan_result = _verified_source(
            result,
            retrieval_root,
            policy,
            malware_scanner,
        )
    except LinkedImageMalwareDetectedError as detected:
        expected_sha256 = _normalised_sha256(
            result.content_sha256,
            code="CONTENT_DIGEST_INVALID",
        )
        if (
            not isinstance(result.received_bytes, int)
            or detected.result.content_sha256 != expected_sha256
            or detected.result.content_size_bytes != result.received_bytes
        ):
            raise LinkedImageEvidenceError("MALWARE_SCAN_RESULT_MISMATCH") from None
        try:
            record_detected_sha(
                db,
                storage_root,
                sha=expected_sha256,
                size=result.received_bytes,
                filename=f"linked-image-{expected_sha256[:12]}.jpg",
                media_type="image/jpeg",
                purpose="technical_evidence",
                user=None,
                result=detected.result,
                scan_source="linked_image_retention",
                actor_type="human_operator",
                actor_name=operator_reference,
            )
        except MalwareScanError as exc:
            raise LinkedImageEvidenceError(exc.code) from None
        raise LinkedImageMalwareQuarantinedError(detected.result) from None
    visual_metadata = {
        "evidence_role": "primary_detail",
        "relationship": "linked_original",
        "parent_evidence_source_id": parent.id,
        "inference_allowed": True,
        "validation_only": False,
    }
    source_json = {
        VISUAL_EVIDENCE_METADATA_KEY: visual_metadata,
        "linked_image_retrieval": _provenance(result),
    }
    reference = _source_reference(result)
    defect = _locked_defect(db, parent.defect_id)
    if defect is None or defect.estimate_id != estimate.id:
        raise LinkedImageEvidenceError("PARENT_EVIDENCE_INVALID")
    existing_evidence = _existing_evidence(
        db,
        estimate_id=estimate.id,
        defect_id=parent.defect_id,
        source_reference=reference,
        parent_id=parent.id,
        content_sha256=content_sha256,
        source_json=source_json,
    )
    if existing_evidence is not None:
        existing_stored = (
            _locked_stored_file_by_id(db, existing_evidence.stored_file_id)
            if existing_evidence.stored_file_id
            else None
        )
        if existing_stored is None:
            raise LinkedImageEvidenceError("EVIDENCE_REPLAY_CONFLICT")
        _accept_clean_existing_linked_image(
            db,
            storage_root=storage_root,
            stored=existing_stored,
            content_sha256=content_sha256,
            scan_result=scan_result,
            operator_reference=operator_reference,
        )
        return LinkedImageEvidenceRetention(
            evidence=existing_evidence,
            stored_file=existing_stored,
            evidence_created=False,
            stored_file_created=False,
        )

    stored, stored_created = _store_bytes(
        db,
        storage_root=storage_root,
        body=body,
        content_sha256=content_sha256,
        scan_result=scan_result,
        operator_reference=operator_reference,
    )
    evidence = EvidenceSource(
        estimate_id=estimate.id,
        defect_id=parent.defect_id,
        stored_file_id=stored.id,
        evidence_type="inspection_photo",
        source_reference=reference,
        page_number=str(result.page_number),
        region_reference=result.photo_id,
        sha256=content_sha256,
        evidence_class="observed",
        confidence=parent.confidence,
        status="active",
        source_json=source_json,
    )
    db.add(evidence)
    db.flush()
    proof_sha256 = hashlib.sha256(
        json.dumps(
            source_json["linked_image_retrieval"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    record_audit(
        db,
        actor=None,
        actor_type="human_operator",
        actor_name=operator_reference,
        action="retain_verified_linked_image_evidence",
        entity_type="evidence_source",
        entity_id=evidence.id,
        project_id=estimate.project_id,
        new_value={
            "estimate_id": estimate.id,
            "defect_id": evidence.defect_id,
            "parent_evidence_source_id": parent.id,
            "photo_id": result.photo_id,
            "sha256": content_sha256,
            "retrieval_proof_sha256": proof_sha256,
        },
        reason="Verified linked original retained as immutable visual evidence.",
    )
    db.flush()
    return LinkedImageEvidenceRetention(
        evidence=evidence,
        stored_file=stored,
        evidence_created=True,
        stored_file_created=stored_created,
    )


__all__ = [
    "LINKED_IMAGE_EVIDENCE_SCHEMA",
    "LinkedImageEvidenceError",
    "LinkedImageEvidenceRetention",
    "LinkedImageMalwareQuarantinedError",
    "retain_verified_linked_image",
]
