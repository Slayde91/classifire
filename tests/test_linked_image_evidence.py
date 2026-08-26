from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from functools import partial
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pytest
from malware_scan_support import (
    CleanMalwareScanner as _CleanScanner,
)
from malware_scan_support import (
    append_clean_attestation,
    malware_scan_result,
)
from physical_foundation_support import add_estimate, physical_session
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy import update as sql_update
from sqlalchemy.orm.attributes import set_committed_value

import classifire.services.linked_image_evidence as linked_image_evidence_service
from classifire.models import AuditEvent, MalwareScanAttestation, StoredFile
from classifire.physical_models import Defect, EvidenceSource, PhysicalModelLock
from classifire.services.linked_image_evidence import (
    LINKED_IMAGE_EVIDENCE_SCHEMA,
    LinkedImageEvidenceError,
    LinkedImageMalwareQuarantinedError,
)
from classifire.services.linked_image_evidence import (
    retain_verified_linked_image as _retain_verified_linked_image,
)
from classifire.services.linked_image_retrieval import LinkedImageResult
from classifire.services.malware_scanning import (
    MalwareDetectedError,
    MalwareScanError,
    MalwareScanResult,
)
from classifire.services.phase8_visual_evidence import build_retained_visual_evidence_packet


class _RejectingScanner:
    def __init__(self, code: str) -> None:
        self.code = code

    def check_ready(self) -> None:
        pass

    def scan_stream(self, stream: BinaryIO) -> MalwareScanResult:
        payload = stream.read()
        if self.code == "MALWARE_DETECTED":
            raise MalwareDetectedError(malware_scan_result(payload, verdict="infected"))
        raise MalwareScanError(self.code)


retain_verified_linked_image = partial(
    _retain_verified_linked_image,
    malware_scanner=_CleanScanner(),
)


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
    append_clean_attestation(session, stored)
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


def test_retention_scan_failure_creates_no_stored_file_evidence_or_audit(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "storage"
    retrieval_root = tmp_path / "retrieval"
    storage_root.mkdir()
    retrieval_root.mkdir()
    with physical_session() as session:
        estimate, _defect, parent, embedded_sha256 = _setup_parent(session, storage_root)
        result = _verified_result(retrieval_root, embedded_sha256)
        before = (
            session.scalar(select(func.count()).select_from(StoredFile)),
            session.scalar(select(func.count()).select_from(EvidenceSource)),
            session.scalar(select(func.count()).select_from(AuditEvent)),
        )

        with pytest.raises(LinkedImageEvidenceError) as captured:
            _retain_verified_linked_image(
                session,
                storage_root=storage_root,
                retrieval_root=retrieval_root,
                estimate_id=estimate.id,
                parent_evidence_source_id=parent.id,
                result=result,
                operator_reference="Scanner failure test",
                malware_scanner=_RejectingScanner("MALWARE_SCANNER_UNAVAILABLE"),
            )

        assert captured.value.code == "MALWARE_SCANNER_UNAVAILABLE"
        assert (
            session.scalar(select(func.count()).select_from(StoredFile)),
            session.scalar(select(func.count()).select_from(EvidenceSource)),
            session.scalar(select(func.count()).select_from(AuditEvent)),
        ) == before


def test_retention_malware_detection_records_an_infected_receipt(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    retrieval_root = tmp_path / "retrieval"
    storage_root.mkdir()
    retrieval_root.mkdir()
    with physical_session() as session:
        estimate, _defect, parent, embedded_sha256 = _setup_parent(session, storage_root)
        result = _verified_result(retrieval_root, embedded_sha256)
        evidence_count = session.scalar(select(func.count()).select_from(EvidenceSource))
        containment_audit_count = session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.action.in_(
                    {
                        "append_malware_scan_attestation",
                        "quarantine_stored_file_after_malware_detection",
                    }
                )
            )
        )

        with pytest.raises(LinkedImageMalwareQuarantinedError) as captured:
            _retain_verified_linked_image(
                session,
                storage_root=storage_root,
                retrieval_root=retrieval_root,
                estimate_id=estimate.id,
                parent_evidence_source_id=parent.id,
                result=result,
                operator_reference="Malware containment test",
                malware_scanner=_RejectingScanner("MALWARE_DETECTED"),
            )

        assert captured.value.code == "MALWARE_DETECTED"
        blocked = session.scalar(
            select(StoredFile).where(StoredFile.sha256 == result.content_sha256)
        )
        assert blocked is not None
        assert blocked.malware_scan_status == "infected"
        assert not Path(blocked.storage_path).exists()
        attestation = session.scalar(
            select(MalwareScanAttestation).where(
                MalwareScanAttestation.stored_file_id == blocked.id
            )
        )
        assert attestation is not None
        assert attestation.verdict == "infected"
        assert attestation.scan_source == "linked_image_retention"
        assert session.scalar(select(func.count()).select_from(EvidenceSource)) == evidence_count
        assert session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.action.in_(
                    {
                        "append_malware_scan_attestation",
                        "quarantine_stored_file_after_malware_detection",
                    }
                )
            )
        ) == containment_audit_count + 2


def _setup_report_derived_parent(session, storage_root: Path):
    estimate = add_estimate(session)
    defect = Defect(
        estimate_id=estimate.id,
        external_defect_id="D-REPORT-001",
        evidence_status="confirmed",
        status="draft",
    )
    session.add(defect)
    session.flush()
    report = b"%PDF-1.4\nsynthetic retained report\n"
    report_sha256 = _sha256(report)
    report_path = storage_root / "retained-report.pdf"
    report_path.write_bytes(report)
    stored = StoredFile(
        original_filename="retained-report.pdf",
        media_type="application/pdf",
        storage_path=str(report_path),
        sha256=report_sha256,
        size_bytes=len(report),
        purpose="project_evidence",
        malware_scan_status="clean",
        immutable=True,
    )
    session.add(stored)
    session.flush()
    append_clean_attestation(session, stored)
    parent = EvidenceSource(
        estimate_id=estimate.id,
        defect_id=defect.id,
        stored_file_id=stored.id,
        evidence_type="defect_photo_detail_review",
        source_reference="retained-report-photo-review",
        page_number="1",
        region_reference="photo-detail:P001-I01:defect:D-REPORT-001",
        sha256=report_sha256,
        evidence_class="observed",
        status="active",
        source_json={
            "source": "native_or_zoom_photo_vision",
            "photo_id": "P001-I01",
            "native_extraction_ok": True,
            "native_pixels": [50, 50],
            "source_bbox": [10.0, 10.0, 60.0, 60.0],
        },
    )
    session.add(parent)
    session.flush()
    embedded_sha256 = _sha256(_jpeg((50, 50), (30, 70, 110)))
    return estimate, defect, parent, embedded_sha256, report_sha256


def test_retention_creates_governed_evidence_without_committing(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    retrieval_root = tmp_path / "retrieval"
    storage_root.mkdir()
    retrieval_root.mkdir()

    with physical_session() as session:
        estimate, defect, parent, embedded_sha256 = _setup_parent(session, storage_root)
        result = _verified_result(retrieval_root, embedded_sha256)
        outer_transaction = session.get_transaction()
        assert outer_transaction is not None

        retained = retain_verified_linked_image(
            session,
            storage_root=storage_root,
            retrieval_root=retrieval_root,
            estimate_id=estimate.id,
            parent_evidence_source_id=parent.id,
            result=result,
            operator_reference="Synthetic test operator",
        )

        assert session.get_transaction() is outer_transaction
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


def test_retention_accepts_report_derived_parent_only_with_exact_report_binding(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "storage"
    retrieval_root = tmp_path / "retrieval"
    storage_root.mkdir()
    retrieval_root.mkdir()

    with physical_session() as session:
        estimate, defect, parent, embedded_sha256, report_sha256 = _setup_report_derived_parent(
            session,
            storage_root,
        )
        result = _verified_result(retrieval_root, embedded_sha256)

        retained = retain_verified_linked_image(
            session,
            storage_root=storage_root,
            retrieval_root=retrieval_root,
            estimate_id=estimate.id,
            parent_evidence_source_id=parent.id,
            result=result,
            operator_reference="Synthetic test operator",
            source_report_sha256=report_sha256,
        )

        assert retained.evidence.defect_id == defect.id
        assert (
            retained.evidence.source_json["phase8_visual_inference"]["parent_evidence_source_id"]
            == parent.id
        )


@pytest.mark.parametrize("invalid_source_report_sha256", [None, "f" * 64])
def test_retention_rejects_report_derived_parent_without_exact_report_binding(
    tmp_path: Path,
    invalid_source_report_sha256: str | None,
) -> None:
    storage_root = tmp_path / "storage"
    retrieval_root = tmp_path / "retrieval"
    storage_root.mkdir()
    retrieval_root.mkdir()

    with physical_session() as session:
        estimate, _defect, parent, embedded_sha256, _report_sha256 = _setup_report_derived_parent(
            session,
            storage_root,
        )
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
                source_report_sha256=invalid_source_report_sha256,
            )

        assert caught.value.code == "PARENT_EVIDENCE_INVALID"


def test_retention_rejects_report_derived_parent_with_mismatched_photo_bounds(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "storage"
    retrieval_root = tmp_path / "retrieval"
    storage_root.mkdir()
    retrieval_root.mkdir()

    with physical_session() as session:
        estimate, _defect, parent, embedded_sha256, report_sha256 = _setup_report_derived_parent(
            session,
            storage_root,
        )
        parent.source_json = {
            **parent.source_json,
            "source_bbox": [11.0, 10.0, 60.0, 60.0],
        }
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
                source_report_sha256=report_sha256,
            )

        assert caught.value.code == "PARENT_EVIDENCE_INVALID"


def test_retention_rejects_report_derived_parent_when_both_bounds_are_missing(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "storage"
    retrieval_root = tmp_path / "retrieval"
    storage_root.mkdir()
    retrieval_root.mkdir()

    with physical_session() as session:
        estimate, _defect, parent, embedded_sha256, report_sha256 = _setup_report_derived_parent(
            session, storage_root
        )
        parent.source_json = {**parent.source_json, "source_bbox": None}
        session.flush()
        result = replace(
            _verified_result(retrieval_root, embedded_sha256),
            photo_bbox=None,
        )

        with pytest.raises(LinkedImageEvidenceError) as caught:
            retain_verified_linked_image(
                session,
                storage_root=storage_root,
                retrieval_root=retrieval_root,
                estimate_id=estimate.id,
                parent_evidence_source_id=parent.id,
                result=result,
                operator_reference="Synthetic test operator",
                source_report_sha256=report_sha256,
            )

        assert caught.value.code == "PARENT_EVIDENCE_INVALID"


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


def test_retention_locks_the_defect_before_checking_replay_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_root = tmp_path / "storage"
    retrieval_root = tmp_path / "retrieval"
    storage_root.mkdir()
    retrieval_root.mkdir()

    with physical_session() as session:
        estimate, _defect, parent, embedded_sha256 = _setup_parent(session, storage_root)
        result = _verified_result(retrieval_root, embedded_sha256)
        real_lock = linked_image_evidence_service._locked_defect
        real_replay_lookup = linked_image_evidence_service._existing_evidence
        events: list[str] = []

        def tracked_lock(db, defect_id):  # type: ignore[no-untyped-def]
            events.append("defect_locked")
            return real_lock(db, defect_id)

        def tracked_replay_lookup(*args, **kwargs):  # type: ignore[no-untyped-def]
            assert events == ["defect_locked"]
            events.append("replay_checked")
            return real_replay_lookup(*args, **kwargs)

        monkeypatch.setattr(linked_image_evidence_service, "_locked_defect", tracked_lock)
        monkeypatch.setattr(
            linked_image_evidence_service,
            "_existing_evidence",
            tracked_replay_lookup,
        )
        retain_verified_linked_image(
            session,
            storage_root=storage_root,
            retrieval_root=retrieval_root,
            estimate_id=estimate.id,
            parent_evidence_source_id=parent.id,
            result=result,
            operator_reference="Replay lock ordering",
        )

        assert events == ["defect_locked", "replay_checked"]


def test_different_parent_cannot_duplicate_the_same_linked_replay_identity(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "storage"
    retrieval_root = tmp_path / "retrieval"
    storage_root.mkdir()
    retrieval_root.mkdir()

    with physical_session() as session:
        estimate, defect, parent, embedded_sha256 = _setup_parent(session, storage_root)
        second_parent = EvidenceSource(
            estimate_id=estimate.id,
            defect_id=defect.id,
            stored_file_id=parent.stored_file_id,
            evidence_type="inspection_photo",
            source_reference="second-retained-report-thumbnail",
            page_number="1",
            region_reference="P001-I01",
            sha256=embedded_sha256,
            evidence_class="observed",
            status="active",
            source_json=json.loads(json.dumps(parent.source_json)),
        )
        session.add(second_parent)
        session.flush()
        result = _verified_result(retrieval_root, embedded_sha256)
        retain_verified_linked_image(
            session,
            storage_root=storage_root,
            retrieval_root=retrieval_root,
            estimate_id=estimate.id,
            parent_evidence_source_id=parent.id,
            result=result,
            operator_reference="First replay identity",
        )

        with pytest.raises(LinkedImageEvidenceError) as caught:
            retain_verified_linked_image(
                session,
                storage_root=storage_root,
                retrieval_root=retrieval_root,
                estimate_id=estimate.id,
                parent_evidence_source_id=second_parent.id,
                result=result,
                operator_reference="Conflicting replay identity",
            )

        assert caught.value.code == "EVIDENCE_REPLAY_CONFLICT"
        assert (
            session.scalar(
                select(func.count())
                .select_from(EvidenceSource)
                .where(
                    EvidenceSource.source_reference
                    == "phase8-linked-original:1:P001-I01"
                )
            )
            == 1
        )


def test_retention_recovers_from_a_concurrent_compatible_stored_file_insert(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_root = tmp_path / "storage"
    retrieval_root = tmp_path / "retrieval"
    storage_root.mkdir()
    retrieval_root.mkdir()

    with physical_session() as session:
        estimate, _defect, parent, embedded_sha256 = _setup_parent(session, storage_root)
        result = _verified_result(retrieval_root, embedded_sha256)
        body = (retrieval_root / str(result.stored_path)).read_bytes()
        target = (
            storage_root
            / str(result.content_sha256)[:2]
            / str(result.content_sha256)[2:4]
            / f"{result.content_sha256}.jpg"
        )
        target.parent.mkdir(parents=True)
        target.write_bytes(body)
        winner = StoredFile(
            original_filename="linked-image-winner.jpg",
            media_type="image/jpeg",
            storage_path=str(target),
            sha256=str(result.content_sha256),
            size_bytes=len(body),
            purpose="technical_evidence",
            malware_scan_status="clean",
            immutable=True,
        )
        session.add(winner)
        session.flush()
        append_clean_attestation(session, winner)
        session.commit()
        real_lookup = linked_image_evidence_service._locked_stored_file_by_sha
        lookup_count = 0

        def stale_first_lookup(db, content_sha256):  # type: ignore[no-untyped-def]
            nonlocal lookup_count
            lookup_count += 1
            if lookup_count == 1:
                return None
            return real_lookup(db, content_sha256)

        monkeypatch.setattr(
            linked_image_evidence_service,
            "_locked_stored_file_by_sha",
            stale_first_lookup,
        )
        retained = retain_verified_linked_image(
            session,
            storage_root=storage_root,
            retrieval_root=retrieval_root,
            estimate_id=estimate.id,
            parent_evidence_source_id=parent.id,
            result=result,
            operator_reference="Concurrent compatible winner",
        )

        assert lookup_count == 2
        assert retained.stored_file.id == winner.id
        assert retained.stored_file_created is False
        assert session.scalar(select(func.count()).select_from(StoredFile)) == 2
        assert (
            session.scalar(select(func.count()).select_from(MalwareScanAttestation))
            == 3
        )


def test_retention_conflict_cannot_reuse_an_infected_stored_file_winner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_root = tmp_path / "storage"
    retrieval_root = tmp_path / "retrieval"
    storage_root.mkdir()
    retrieval_root.mkdir()

    with physical_session() as session:
        estimate, _defect, parent, embedded_sha256 = _setup_parent(session, storage_root)
        result = _verified_result(retrieval_root, embedded_sha256)
        tombstone = StoredFile(
            original_filename="linked-image-blocked.jpg",
            media_type="image/jpeg",
            storage_path=str(
                storage_root / ".rejected" / f"{result.content_sha256}.malware-blocked"
            ),
            sha256=str(result.content_sha256),
            size_bytes=int(result.received_bytes),
            purpose="technical_evidence",
            malware_scan_status="infected",
            immutable=True,
        )
        session.add(tombstone)
        session.commit()
        real_lookup = linked_image_evidence_service._locked_stored_file_by_sha
        lookup_count = 0

        def stale_first_lookup(db, content_sha256):  # type: ignore[no-untyped-def]
            nonlocal lookup_count
            lookup_count += 1
            if lookup_count == 1:
                return None
            return real_lookup(db, content_sha256)

        monkeypatch.setattr(
            linked_image_evidence_service,
            "_locked_stored_file_by_sha",
            stale_first_lookup,
        )
        with pytest.raises(LinkedImageEvidenceError) as caught:
            retain_verified_linked_image(
                session,
                storage_root=storage_root,
                retrieval_root=retrieval_root,
                estimate_id=estimate.id,
                parent_evidence_source_id=parent.id,
                result=result,
                operator_reference="Concurrent infected winner",
            )

        assert caught.value.code == "STORED_FILE_MALWARE_BLOCKED"
        assert lookup_count == 2
        promoted = (
            storage_root
            / str(result.content_sha256)[:2]
            / str(result.content_sha256)[2:4]
            / f"{result.content_sha256}.jpg"
        )
        assert not promoted.exists()
        assert tuple(storage_root.rglob("*.part")) == ()
        assert session.scalar(select(func.count()).select_from(StoredFile)) == 2
        assert (
            session.scalar(
                select(func.count())
                .select_from(EvidenceSource)
                .where(EvidenceSource.source_reference.like("phase8-linked-original:%"))
            )
            == 0
        )


def test_retention_locked_refresh_rejects_cached_parent_that_became_infected(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "storage"
    retrieval_root = tmp_path / "retrieval"
    storage_root.mkdir()
    retrieval_root.mkdir()

    with physical_session() as session:
        estimate, _defect, parent, embedded_sha256 = _setup_parent(session, storage_root)
        result = _verified_result(retrieval_root, embedded_sha256)
        session.commit()
        session.execute(
            sql_update(StoredFile)
            .where(StoredFile.id == parent.stored_file_id)
            .values(malware_scan_status="infected"),
            execution_options={"synchronize_session": False},
        )
        session.commit()
        cached = session.get(StoredFile, parent.stored_file_id)
        assert cached is not None and cached.malware_scan_status == "infected"
        set_committed_value(cached, "malware_scan_status", "clean")

        with pytest.raises(LinkedImageEvidenceError) as caught:
            retain_verified_linked_image(
                session,
                storage_root=storage_root,
                retrieval_root=retrieval_root,
                estimate_id=estimate.id,
                parent_evidence_source_id=parent.id,
                result=result,
                operator_reference="Cached parent infection",
            )

        assert caught.value.code == "PARENT_EVIDENCE_INVALID"
        assert cached.malware_scan_status == "infected"


def test_retention_replay_locked_refresh_rejects_file_that_became_infected(
    tmp_path: Path,
) -> None:
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
            operator_reference="Initial retention",
        )
        session.commit()
        session.execute(
            sql_update(StoredFile)
            .where(StoredFile.id == first.stored_file.id)
            .values(malware_scan_status="infected"),
            execution_options={"synchronize_session": False},
        )
        session.commit()
        cached = session.get(StoredFile, first.stored_file.id)
        assert cached is not None and cached.malware_scan_status == "infected"
        set_committed_value(cached, "malware_scan_status", "clean")

        with pytest.raises(LinkedImageEvidenceError) as caught:
            retain_verified_linked_image(
                session,
                storage_root=storage_root,
                retrieval_root=retrieval_root,
                estimate_id=estimate.id,
                parent_evidence_source_id=parent.id,
                result=result,
                operator_reference="Replay after infection",
            )

        assert caught.value.code == "STORED_FILE_MALWARE_BLOCKED"
        assert cached.malware_scan_status == "infected"


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
        visual_metadata = dict(parent.source_json["phase8_visual_inference"])
        visual_metadata["validation_only"] = True
        parent.source_json = {
            **parent.source_json,
            "phase8_visual_inference": visual_metadata,
        }
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
