from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import pytest
from physical_foundation_support import add_estimate, physical_session
from PIL import Image
from sqlalchemy import event, func, select

from classifire.models import AuditEvent, StoredFile
from classifire.physical_models import Defect, EvidenceSource, PhysicalModelLock
from classifire.services.linked_image_evidence import (
    LINKED_IMAGE_EVIDENCE_SCHEMA,
    LinkedImageEvidenceError,
    retain_verified_linked_image,
)
from classifire.services.linked_image_retrieval import LinkedImageResult
from classifire.services.phase8_visual_evidence import build_retained_visual_evidence_packet


def _jpeg(size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    stream = BytesIO()
    Image.new("RGB", size, color).save(stream, format="JPEG", quality=95)
    return stream.getvalue()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _setup_parent(session, storage_root: Path):
    estimate = add_estimate(session)
    defect = Defect(
        estimate_id=estimate.id,
        external_defect_id="D-001",
        evidence_status="confirmed",
        status="draft",
    )
    session.add(defect)
    session.flush()
    embedded = _jpeg((50, 50), (30, 70, 110))
    embedded_sha256 = _sha256(embedded)
    parent_path = storage_root / "embedded.jpg"
    parent_path.write_bytes(embedded)
    stored = StoredFile(
        original_filename="embedded.jpg",
        media_type="image/jpeg",
        storage_path=str(parent_path),
        sha256=embedded_sha256,
        size_bytes=len(embedded),
        purpose="technical_evidence",
        malware_scan_status="clean",
        immutable=True,
    )
    session.add(stored)
    session.flush()
    parent = EvidenceSource(
        estimate_id=estimate.id,
        defect_id=defect.id,
        stored_file_id=stored.id,
        evidence_type="inspection_photo",
        source_reference="retained-report-thumbnail",
        page_number="1",
        region_reference="P001-I01",
        sha256=embedded_sha256,
        evidence_class="observed",
        status="active",
        source_json={
            "phase8_visual_inference": {
                "evidence_role": "primary_detail",
                "relationship": "embedded_image",
                "parent_evidence_source_id": None,
                "inference_allowed": True,
                "validation_only": False,
            }
        },
    )
    session.add(parent)
    session.flush()
    return estimate, defect, parent, embedded_sha256


def _verified_result(retrieval_root: Path, embedded_sha256: str) -> LinkedImageResult:
    full = _jpeg((1200, 800), (31, 71, 111))
    content_sha256 = _sha256(full)
    relative = Path("photo-linked") / "by-sha256" / content_sha256[:2] / f"{content_sha256}.jpg"
    path = retrieval_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(full)
    return LinkedImageResult(
        photo_id="P001-I01",
        page_number=1,
        required=True,
        status="VERIFIED",
        embedded_sha256=embedded_sha256,
        embedded_width=50,
        embedded_height=50,
        photo_bbox=(10.0, 10.0, 60.0, 60.0),
        annotation_bbox=(10.0, 10.0, 60.0, 60.0),
        overlap_ratio=1.0,
        annotation_xrefs=(42,),
        uri_sha256="a" * 64,
        host="twiddle.onuptick.com",
        path_sha256="b" * 64,
        suffix=".jpg",
        query_keys=("Expires", "Key-Pair-Id", "Signature", "public_id", "transform"),
        redirect_count=0,
        resolved_address_count=1,
        tls_version="TLSv1.3",
        content_type="image/jpeg",
        declared_bytes=len(full),
        received_bytes=len(full),
        content_sha256=content_sha256,
        width=1200,
        height=800,
        thumbnail_hash_distance=1,
        thumbnail_mean_error=0.01,
        embedded_pixel_sha256="c" * 64,
        thumbnail_transform="FULL_FRAME_RESIZE",
        thumbnail_luma_stddev=0.2,
        thumbnail_entropy_bits=5.0,
        thumbnail_mean_gradient=0.02,
        thumbnail_matching_tiles=15,
        thumbnail_tile_count=16,
        thumbnail_worst_tile_mean_error=0.02,
        thumbnail_comparison_group_count=1,
        usable_detail_gradient_gain_ratio=1.5,
        usable_detail_residual=0.02,
        usable_detail_matching_tiles=12,
        stored_path=relative.as_posix(),
    )


def test_retention_creates_governed_evidence_without_committing(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    retrieval_root = tmp_path / "retrieval"
    storage_root.mkdir()
    retrieval_root.mkdir()

    with physical_session() as session:
        estimate, defect, parent, embedded_sha256 = _setup_parent(session, storage_root)
        result = _verified_result(retrieval_root, embedded_sha256)
        commits: list[bool] = []
        event.listen(session, "after_commit", lambda _session: commits.append(True))

        retained = retain_verified_linked_image(
            session,
            storage_root=storage_root,
            retrieval_root=retrieval_root,
            estimate_id=estimate.id,
            parent_evidence_source_id=parent.id,
            result=result,
            operator_reference="Synthetic test operator",
        )

        assert commits == []
        assert retained.evidence_created is True
        assert retained.stored_file_created is True
        assert retained.evidence.defect_id == defect.id
        assert retained.evidence.sha256 == result.content_sha256
        assert retained.stored_file.purpose == "technical_evidence"
        assert retained.stored_file.immutable is True
        assert Path(retained.stored_file.storage_path).is_relative_to(storage_root)
        metadata = retained.evidence.source_json
        assert metadata["phase8_visual_inference"] == {
            "evidence_role": "primary_detail",
            "relationship": "linked_original",
            "parent_evidence_source_id": parent.id,
            "inference_allowed": True,
            "validation_only": False,
        }
        assert metadata["linked_image_retrieval"]["schema"] == LINKED_IMAGE_EVIDENCE_SCHEMA
        assert "https://" not in json.dumps(metadata)
        assert "Signature=" not in json.dumps(metadata)
        audit = session.scalar(
            select(AuditEvent).where(AuditEvent.action == "retain_verified_linked_image_evidence")
        )
        assert audit is not None
        assert audit.entity_id == retained.evidence.id

        packet = build_retained_visual_evidence_packet(
            session,
            storage_root=storage_root,
            estimate_id=estimate.id,
            defect_reference="D-001",
        )
        artifacts = {item["evidence_id"]: item for item in packet.manifest["artifacts"]}
        assert artifacts[retained.evidence.id]["provenance"]["parent_evidence_id"] == parent.id
        assert artifacts[retained.evidence.id]["provenance"]["pixel_width"] == 1200
        assert artifacts[retained.evidence.id]["provenance"]["pixel_height"] == 800


def test_retention_is_idempotent_and_does_not_duplicate_audit(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    retrieval_root = tmp_path / "retrieval"
    storage_root.mkdir()
    retrieval_root.mkdir()

    with physical_session() as session:
        estimate, _defect, parent, embedded_sha256 = _setup_parent(session, storage_root)
        result = _verified_result(retrieval_root, embedded_sha256)
        first = retain_verified_linked_image(
            session,
            storage_root=storage_root,
            retrieval_root=retrieval_root,
            estimate_id=estimate.id,
            parent_evidence_source_id=parent.id,
            result=result,
            operator_reference="Synthetic test operator",
        )
        second = retain_verified_linked_image(
            session,
            storage_root=storage_root,
            retrieval_root=retrieval_root,
            estimate_id=estimate.id,
            parent_evidence_source_id=parent.id,
            result=result,
            operator_reference="Synthetic test operator",
        )

        assert second.evidence.id == first.evidence.id
        assert second.stored_file.id == first.stored_file.id
        assert second.evidence_created is False
        assert second.stored_file_created is False
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "retain_verified_linked_image_evidence")
            )
            == 1
        )


def test_retention_rejects_tampered_verified_source(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    retrieval_root = tmp_path / "retrieval"
    storage_root.mkdir()
    retrieval_root.mkdir()

    with physical_session() as session:
        estimate, _defect, parent, embedded_sha256 = _setup_parent(session, storage_root)
        result = _verified_result(retrieval_root, embedded_sha256)
        (retrieval_root / str(result.stored_path)).write_bytes(b"tampered")

        with pytest.raises(LinkedImageEvidenceError) as caught:
            retain_verified_linked_image(
                session,
                storage_root=storage_root,
                retrieval_root=retrieval_root,
                estimate_id=estimate.id,
                parent_evidence_source_id=parent.id,
                result=result,
                operator_reference="Synthetic test operator",
            )

        assert caught.value.code == "VERIFIED_SOURCE_INVALID"


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("status", "NETWORK_FAILURE", "RESULT_NOT_VERIFIED"),
        ("embedded_sha256", "d" * 64, "PARENT_EVIDENCE_INVALID"),
        ("thumbnail_transform", None, "RESULT_PROOF_INCOMPLETE"),
        ("host", "example.invalid", "RESULT_PROOF_INCOMPLETE"),
    ],
)
def test_retention_rejects_unverified_or_unbound_results(
    tmp_path: Path,
    field: str,
    value: object,
    code: str,
) -> None:
    storage_root = tmp_path / "storage"
    retrieval_root = tmp_path / "retrieval"
    storage_root.mkdir()
    retrieval_root.mkdir()

    with physical_session() as session:
        estimate, _defect, parent, embedded_sha256 = _setup_parent(session, storage_root)
        result = _verified_result(retrieval_root, embedded_sha256)
        changed = replace(result, **{field: value})

        with pytest.raises(LinkedImageEvidenceError) as caught:
            retain_verified_linked_image(
                session,
                storage_root=storage_root,
                retrieval_root=retrieval_root,
                estimate_id=estimate.id,
                parent_evidence_source_id=parent.id,
                result=changed,
                operator_reference="Synthetic test operator",
            )

        assert caught.value.code == code


def test_retention_requires_exact_parent_photo_binding(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    retrieval_root = tmp_path / "retrieval"
    storage_root.mkdir()
    retrieval_root.mkdir()

    with physical_session() as session:
        estimate, _defect, parent, embedded_sha256 = _setup_parent(session, storage_root)
        parent.region_reference = "P001-I02"
        session.flush()
        result = _verified_result(retrieval_root, embedded_sha256)

        with pytest.raises(LinkedImageEvidenceError) as caught:
            retain_verified_linked_image(
                session,
                storage_root=storage_root,
                retrieval_root=retrieval_root,
                estimate_id=estimate.id,
                parent_evidence_source_id=parent.id,
                result=result,
                operator_reference="Synthetic test operator",
            )

        assert caught.value.code == "PARENT_PHOTO_MISMATCH"


def test_retention_requires_approved_embedded_parent_metadata(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    retrieval_root = tmp_path / "retrieval"
    storage_root.mkdir()
    retrieval_root.mkdir()

    with physical_session() as session:
        estimate, _defect, parent, embedded_sha256 = _setup_parent(session, storage_root)
        parent.source_json["phase8_visual_inference"]["validation_only"] = True
        session.flush()
        result = _verified_result(retrieval_root, embedded_sha256)

        with pytest.raises(LinkedImageEvidenceError) as caught:
            retain_verified_linked_image(
                session,
                storage_root=storage_root,
                retrieval_root=retrieval_root,
                estimate_id=estimate.id,
                parent_evidence_source_id=parent.id,
                result=result,
                operator_reference="Synthetic test operator",
            )

        assert caught.value.code == "PARENT_METADATA_INVALID"


def test_retention_fails_closed_after_physical_model_lock(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    retrieval_root = tmp_path / "retrieval"
    storage_root.mkdir()
    retrieval_root.mkdir()

    with physical_session() as session:
        estimate, _defect, parent, embedded_sha256 = _setup_parent(session, storage_root)
        session.add(
            PhysicalModelLock(
                project_id=estimate.project_id,
                estimate_id=estimate.id,
                service_ids=[],
                opening_ids=[],
                validator_result="PASS",
                content_hash="f" * 64,
            )
        )
        session.flush()
        result = _verified_result(retrieval_root, embedded_sha256)

        with pytest.raises(LinkedImageEvidenceError) as caught:
            retain_verified_linked_image(
                session,
                storage_root=storage_root,
                retrieval_root=retrieval_root,
                estimate_id=estimate.id,
                parent_evidence_source_id=parent.id,
                result=result,
                operator_reference="Synthetic test operator",
            )

        assert caught.value.code == "EVIDENCE_MUTATION_FORBIDDEN"


def test_retention_rejects_conflicting_replay(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    retrieval_root = tmp_path / "retrieval"
    storage_root.mkdir()
    retrieval_root.mkdir()

    with physical_session() as session:
        estimate, defect, parent, embedded_sha256 = _setup_parent(session, storage_root)
        result = _verified_result(retrieval_root, embedded_sha256)
        session.add(
            EvidenceSource(
                estimate_id=estimate.id,
                defect_id=defect.id,
                stored_file_id=parent.stored_file_id,
                evidence_type="inspection_photo",
                source_reference="phase8-linked-original:1:P001-I01",
                page_number="1",
                region_reference="P001-I01",
                sha256=embedded_sha256,
                evidence_class="observed",
                status="active",
                source_json=parent.source_json,
            )
        )
        session.flush()

        with pytest.raises(LinkedImageEvidenceError) as caught:
            retain_verified_linked_image(
                session,
                storage_root=storage_root,
                retrieval_root=retrieval_root,
                estimate_id=estimate.id,
                parent_evidence_source_id=parent.id,
                result=result,
                operator_reference="Synthetic test operator",
            )

        assert caught.value.code == "EVIDENCE_REPLAY_CONFLICT"
