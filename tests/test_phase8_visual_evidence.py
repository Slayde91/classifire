from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from physical_foundation_support import add_estimate, physical_session
from PIL import Image

from classifire.models import StoredFile
from classifire.physical_models import Defect, EvidenceSource
from classifire.services.phase8_visual_evidence import (
    VISUAL_EVIDENCE_METADATA_KEY,
    Phase8VisualEvidenceError,
    build_retained_visual_evidence_packet,
)
from classifire.services.phase8_visual_proposal import validate_visual_evidence_manifest


def _image(storage_root: Path, name: str, color: tuple[int, int, int]) -> tuple[Path, str]:
    path = storage_root / name
    Image.new("RGB", (32, 24), color).save(path, format="PNG")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _metadata(
    *,
    role: str = "primary_detail",
    relationship: str = "embedded_image",
    parent_id: str | None = None,
    inference_allowed: bool = True,
    validation_only: bool = False,
) -> dict[str, Any]:
    return {
        VISUAL_EVIDENCE_METADATA_KEY: {
            "evidence_role": role,
            "relationship": relationship,
            "parent_evidence_source_id": parent_id,
            "inference_allowed": inference_allowed,
            "validation_only": validation_only,
        }
    }


def _defect(session, estimate, *, external_id: str = "D-001", code: str | None = None):
    defect = Defect(
        estimate_id=estimate.id,
        external_defect_id=external_id,
        defect_code=code,
        evidence_status="confirmed",
        status="draft",
    )
    session.add(defect)
    session.flush()
    return defect


def _evidence(
    session,
    *,
    estimate,
    defect,
    path: Path,
    sha256: str,
    source_json: dict[str, Any] | None = None,
    purpose: str = "technical_evidence",
    page_number: str = "1",
) -> EvidenceSource:
    stored = StoredFile(
        original_filename=path.name,
        media_type="image/png",
        storage_path=str(path),
        sha256=sha256,
        size_bytes=path.stat().st_size,
        purpose=purpose,
        malware_scan_status="clean",
        immutable=True,
    )
    session.add(stored)
    session.flush()
    evidence = EvidenceSource(
        estimate_id=estimate.id,
        defect_id=defect.id,
        stored_file_id=stored.id,
        evidence_type="inspection_photo",
        source_reference="sensitive-source-location-not-for-inference",
        page_number=page_number,
        region_reference="photo-1",
        sha256=sha256,
        evidence_class="observed",
        status="active",
        source_json=source_json if source_json is not None else _metadata(),
    )
    session.add(evidence)
    session.flush()
    return evidence


def test_adapter_builds_hash_bound_packet_without_exposing_storage_path(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    first_path, first_sha = _image(storage_root, "first.png", (10, 20, 30))
    second_path, second_sha = _image(storage_root, "second.png", (40, 50, 60))

    with physical_session() as session:
        estimate = add_estimate(session)
        defect = _defect(session, estimate)
        first = _evidence(
            session,
            estimate=estimate,
            defect=defect,
            path=first_path,
            sha256=first_sha,
            source_json=_metadata(role="page_context"),
        )
        second = _evidence(
            session,
            estimate=estimate,
            defect=defect,
            path=second_path,
            sha256=second_sha,
            source_json=_metadata(
                relationship="linked_original",
                parent_id=first.id,
            ),
        )

        packet = build_retained_visual_evidence_packet(
            session,
            storage_root=storage_root,
            estimate_id=estimate.id,
            defect_reference="D-001",
        )
        assert not session.new
        assert not session.dirty
        assert not session.deleted

    assert validate_visual_evidence_manifest(packet.manifest, estimate_id=estimate.id) == []
    assert packet.manifest_sha256
    assert [item.evidence_id for item in packet.files] == sorted([first.id, second.id])
    artifacts = {item["evidence_id"]: item for item in packet.manifest["artifacts"]}
    assert artifacts[second.id]["provenance"]["parent_evidence_id"] == first.id
    assert artifacts[first.id]["provenance"]["pixel_width"] == 32
    assert artifacts[first.id]["provenance"]["pixel_height"] == 24
    assert all(
        artifact["provenance"]["source_reference"].startswith("evidence-source:")
        for artifact in artifacts.values()
    )
    assert "sensitive-source-location" not in str(packet.manifest)
    assert str(storage_root) not in str(packet.manifest)


def test_adapter_excludes_evidence_bound_to_another_defect(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    first_path, first_sha = _image(storage_root, "first.png", (10, 20, 30))
    second_path, second_sha = _image(storage_root, "second.png", (40, 50, 60))

    with physical_session() as session:
        estimate = add_estimate(session)
        target = _defect(session, estimate)
        other = _defect(session, estimate, external_id="D-002")
        target_evidence = _evidence(
            session,
            estimate=estimate,
            defect=target,
            path=first_path,
            sha256=first_sha,
        )
        _evidence(
            session,
            estimate=estimate,
            defect=other,
            path=second_path,
            sha256=second_sha,
        )

        packet = build_retained_visual_evidence_packet(
            session,
            storage_root=storage_root,
            estimate_id=estimate.id,
            defect_reference="D-001",
        )

    assert [item.evidence_id for item in packet.files] == [target_evidence.id]


def test_adapter_rejects_tampered_retained_bytes(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    path, sha256 = _image(storage_root, "evidence.png", (10, 20, 30))

    with physical_session() as session:
        estimate = add_estimate(session)
        defect = _defect(session, estimate)
        _evidence(
            session,
            estimate=estimate,
            defect=defect,
            path=path,
            sha256=sha256,
        )
        Image.new("RGB", (32, 24), (99, 98, 97)).save(path, format="PNG")

        with pytest.raises(Phase8VisualEvidenceError) as rejected:
            build_retained_visual_evidence_packet(
                session,
                storage_root=storage_root,
                estimate_id=estimate.id,
                defect_reference="D-001",
            )

    assert rejected.value.code in {"FILE_SIZE_MISMATCH", "FILE_DIGEST_MISMATCH"}


def test_adapter_rejects_file_outside_storage_root(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    outside = tmp_path / "outside.png"
    Image.new("RGB", (32, 24), (10, 20, 30)).save(outside, format="PNG")
    sha256 = hashlib.sha256(outside.read_bytes()).hexdigest()

    with physical_session() as session:
        estimate = add_estimate(session)
        defect = _defect(session, estimate)
        _evidence(
            session,
            estimate=estimate,
            defect=defect,
            path=outside,
            sha256=sha256,
        )

        with pytest.raises(Phase8VisualEvidenceError) as rejected:
            build_retained_visual_evidence_packet(
                session,
                storage_root=storage_root,
                estimate_id=estimate.id,
                defect_reference="D-001",
            )

    assert rejected.value.code == "FILE_OUTSIDE_STORAGE_ROOT"


@pytest.mark.parametrize(
    ("source_json", "expected_code"),
    [
        (None, "METADATA_REQUIRED"),
        (_metadata(inference_allowed=False), "EVIDENCE_NOT_APPROVED_FOR_INFERENCE"),
        (_metadata(validation_only=True), "VALIDATION_ONLY_EVIDENCE_FORBIDDEN"),
    ],
)
def test_adapter_requires_explicit_inference_metadata(
    tmp_path: Path,
    source_json: dict[str, Any] | None,
    expected_code: str,
) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    path, sha256 = _image(storage_root, "evidence.png", (10, 20, 30))

    with physical_session() as session:
        estimate = add_estimate(session)
        defect = _defect(session, estimate)
        evidence = _evidence(
            session,
            estimate=estimate,
            defect=defect,
            path=path,
            sha256=sha256,
        )
        evidence.source_json = source_json
        session.flush()

        with pytest.raises(Phase8VisualEvidenceError) as rejected:
            build_retained_visual_evidence_packet(
                session,
                storage_root=storage_root,
                estimate_id=estimate.id,
                defect_reference="D-001",
            )

    assert rejected.value.code == expected_code


def test_adapter_rejects_human_reference_provenance(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    path, sha256 = _image(storage_root, "evidence.png", (10, 20, 30))

    with physical_session() as session:
        estimate = add_estimate(session)
        defect = _defect(session, estimate)
        _evidence(
            session,
            estimate=estimate,
            defect=defect,
            path=path,
            sha256=sha256,
            source_json=_metadata(role="human_reference"),
        )

        with pytest.raises(Phase8VisualEvidenceError) as rejected:
            build_retained_visual_evidence_packet(
                session,
                storage_root=storage_root,
                estimate_id=estimate.id,
                defect_reference="D-001",
            )

    assert rejected.value.code == "MANIFEST_INVALID"


def test_adapter_rejects_ambiguous_defect_reference(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()

    with physical_session() as session:
        estimate = add_estimate(session)
        _defect(session, estimate, external_id="D-001")
        _defect(session, estimate, external_id="D-002", code="D-001")

        with pytest.raises(Phase8VisualEvidenceError) as rejected:
            build_retained_visual_evidence_packet(
                session,
                storage_root=storage_root,
                estimate_id=estimate.id,
                defect_reference="D-001",
            )

    assert rejected.value.code == "DEFECT_REFERENCE_AMBIGUOUS"


def test_adapter_requires_active_defect_bound_evidence(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()

    with physical_session() as session:
        estimate = add_estimate(session)
        _defect(session, estimate)

        with pytest.raises(Phase8VisualEvidenceError) as rejected:
            build_retained_visual_evidence_packet(
                session,
                storage_root=storage_root,
                estimate_id=estimate.id,
                defect_reference="D-001",
            )

    assert rejected.value.code == "ACTIVE_EVIDENCE_REQUIRED"


def test_adapter_rejects_invalid_page_number_and_file_purpose(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    path, sha256 = _image(storage_root, "evidence.png", (10, 20, 30))

    with physical_session() as session:
        estimate = add_estimate(session)
        defect = _defect(session, estimate)
        evidence = _evidence(
            session,
            estimate=estimate,
            defect=defect,
            path=path,
            sha256=sha256,
            page_number="page one",
        )
        stored = session.get(StoredFile, evidence.stored_file_id)
        assert stored is not None

        with pytest.raises(Phase8VisualEvidenceError) as rejected:
            build_retained_visual_evidence_packet(
                session,
                storage_root=storage_root,
                estimate_id=estimate.id,
                defect_reference="D-001",
            )
        assert rejected.value.code == "PAGE_NUMBER_INVALID"

        evidence.page_number = "1"
        stored.purpose = "initial_adjudicated_canonicalisation"
        session.flush()
        with pytest.raises(Phase8VisualEvidenceError) as rejected:
            build_retained_visual_evidence_packet(
                session,
                storage_root=storage_root,
                estimate_id=estimate.id,
                defect_reference="D-001",
            )

    assert rejected.value.code == "STORED_FILE_PURPOSE_FORBIDDEN"
