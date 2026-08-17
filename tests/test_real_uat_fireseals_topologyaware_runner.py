from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_classifire_real_uat_fireseals_topologyaware import (  # noqa: E402
    PHOTO_LINK_EVIDENCE_TYPE,
    TOPOLOGY_POLICY_VERSION,
    TopologyAwareFireSealController,
)


def test_topology_policy_is_direct_image_and_newer_than_blankaware() -> None:
    assert "HIGHEST-USABLE-DETAIL-TOPOLOGY" in TOPOLOGY_POLICY_VERSION
    assert "_visual_files_for_defect" in TopologyAwareFireSealController.__dict__
    assert "_synthesise_defect" in TopologyAwareFireSealController.__dict__


def test_runner_forbids_one_opening_per_service_and_supports_mixed_services() -> None:
    source = (SCRIPTS / "run_classifire_real_uat_fireseals_topologyaware.py").read_text(
        encoding="utf-8"
    )
    assert "NEVER create one Opening per Service type" in source
    assert "Multiple unlike Services may share one Opening" in source
    assert "cable_bundle" in source
    assert "conduit" in source
    assert "flexible_duct" in source
    assert "aircon_bundle" in source
    assert "two similar PEX pipes" in source


def test_runtime_does_not_read_human_answer_fixture() -> None:
    source = (SCRIPTS / "run_classifire_real_uat_fireseals_topologyaware.py").read_text(
        encoding="utf-8"
    )
    forbidden = "real_uat_20260809_human_physical_reference"
    assert forbidden not in source
    assert "tests/fixtures" not in source
    assert "PRIMARY evidence" in source


def test_topology_stage_passes_actual_visual_files_to_model() -> None:
    source = (SCRIPTS / "run_classifire_real_uat_fireseals_topologyaware.py").read_text(
        encoding="utf-8"
    )
    assert "files=files" in source
    assert "_preferred_photo_sources" in source
    assert "photo-layout-labelled" in source
    assert "self._contact_sheet(contact_rows, defect_index)" in source


def test_topology_prefers_verified_linked_original_over_existing_zoom(
    tmp_path: Path,
) -> None:
    controller = object.__new__(TopologyAwareFireSealController)
    controller.receipt_dir = tmp_path
    staging_dir = tmp_path / "photo-linked"
    staging_dir.mkdir(parents=True)
    staging = staging_dir / "staging.jpg"
    Image.new("RGB", (1200, 900), "blue").save(staging, format="JPEG")
    digest = hashlib.sha256(staging.read_bytes()).hexdigest()
    cache_dir = tmp_path / "photo-linked" / "by-sha256" / digest[:2]
    cache_dir.mkdir(parents=True)
    linked = cache_dir / f"{digest}.jpg"
    staging.replace(linked)
    zoom = tmp_path / "photo-zoom" / "P001-I01-zoom.png"
    zoom.parent.mkdir()
    Image.new("RGB", (220, 220), "blue").save(zoom, format="PNG")
    report = tmp_path / "report.pdf"
    report.write_bytes(b"test report placeholder")
    row = {
        "photo_id": "P001-I01",
        "page_number": 1,
        "digest": "embedded-digest",
        "full_resolution_required": True,
        "full_resolution_status": "VERIFIED",
        "full_resolution_path": linked.relative_to(tmp_path).as_posix(),
        "full_resolution_sha256": digest,
        "full_resolution_width": 1200,
        "full_resolution_height": 900,
    }
    evidence = SimpleNamespace(
        page_number=None,
        evidence_type="defect_photo_detail_review",
        source_json={"photo_id": "P001-I01"},
    )
    controller._direct_evidence = lambda _defect: [evidence]
    controller._photo_inventory = lambda: {"P001-I01": row}
    controller.workspace_report = lambda _agent_id: report
    controller._preferred_photo_sources = lambda _report, _row: [
        {
            "path": linked.resolve(),
            "candidate_id": "P001-I01:linked-original",
            "group_id": "group-1",
            "variant_role": "PRIMARY",
            "relationship_to_primary": "SELF",
            "provenance": "REPORT_LINKED_ORIGINAL",
            "photo_id": "P001-I01",
            "page": 1,
            "width": 1200,
            "height": 900,
            "file_sha256": digest,
        }
    ]
    defect = SimpleNamespace(id="d1", external_defect_id="147031")

    files, manifest = controller._visual_files_for_defect(1, defect)

    assert files == [linked.resolve()]
    assert manifest[0]["source_resolution"] == "linked_original"
    assert manifest[0]["full_resolution_status"] == "VERIFIED"
    assert manifest[0]["pixel_width"] == 1200
    assert manifest[0]["pixel_height"] == 900
    assert manifest[0]["attachment_index"] == 1
    assert manifest[0]["primary_secondary"] == "PRIMARY"
    assert manifest[0]["expected_sha256"] == digest


def test_topology_keeps_later_page_primary_and_mandatory_context_in_order(
    tmp_path: Path,
) -> None:
    controller = object.__new__(TopologyAwareFireSealController)
    controller.receipt_dir = tmp_path
    primary = tmp_path / "appendix-primary.jpg"
    context = tmp_path / "page-context.png"
    Image.new("RGB", (1600, 1200), "green").save(primary)
    Image.new("RGB", (400, 300), "green").save(context)
    report = tmp_path / "report.pdf"
    report.write_bytes(b"report")
    row = {"photo_id": "P001-I01", "page_number": 1}
    evidence = SimpleNamespace(
        page_number=None,
        evidence_type="defect_photo_detail_review",
        source_json={"photo_id": "P001-I01"},
    )
    controller._direct_evidence = lambda _defect: [evidence]
    controller._photo_inventory = lambda: {"P001-I01": row}
    controller.workspace_report = lambda _agent_id: report
    controller._preferred_photo_sources = lambda _report, _row: [
        {
            "path": primary,
            "candidate_id": "P010-I03:embedded",
            "group_id": "group-1",
            "variant_role": "PRIMARY",
            "relationship_to_primary": "SELF",
            "provenance": "PDF_EMBEDDED",
            "photo_id": "P010-I03",
            "page": 10,
            "width": 1600,
            "height": 1200,
            "file_sha256": hashlib.sha256(primary.read_bytes()).hexdigest(),
        },
        {
            "path": context,
            "candidate_id": "P001-I01:page-context",
            "group_id": "group-1",
            "variant_role": "MANDATORY_SECONDARY",
            "relationship_to_primary": "ANNOTATED_VARIANT",
            "provenance": "PDF_PAGE_CONTEXT",
            "photo_id": "P001-I01",
            "page": 1,
            "width": 400,
            "height": 300,
            "file_sha256": hashlib.sha256(context.read_bytes()).hexdigest(),
        },
    ]
    contact = tmp_path / "contact.png"
    Image.new("RGB", (20, 20), "white").save(contact)
    controller._contact_sheet = lambda _rows, _index: contact
    defect = SimpleNamespace(id="d1", external_defect_id="147031")

    files, manifest = controller._visual_files_for_defect(1, defect)

    assert files[:2] == [primary, context]
    assert [item["primary_secondary"] for item in manifest[:2]] == [
        "PRIMARY",
        "SECONDARY",
    ]
    assert manifest[0]["page"] == 10
    assert manifest[1]["relationship_to_primary"] == "ANNOTATED_VARIANT"


def test_topology_fails_instead_of_silently_truncating_mandatory_images(
    tmp_path: Path,
) -> None:
    controller = object.__new__(TopologyAwareFireSealController)
    controller.receipt_dir = tmp_path
    report = tmp_path / "report.pdf"
    report.write_bytes(b"report")
    image = tmp_path / "detail.png"
    Image.new("RGB", (20, 20), "white").save(image)
    row = {"photo_id": "P001-I01", "page_number": 1}
    evidence = SimpleNamespace(
        page_number=1,
        evidence_type="defect_photo_detail_review",
        source_json={"photo_id": "P001-I01"},
    )
    controller._direct_evidence = lambda _defect: [evidence]
    controller._photo_inventory = lambda: {"P001-I01": row}
    controller.workspace_report = lambda _agent_id: report
    controller._preferred_photo_sources = lambda _report, _row: [
        {
            "path": image,
            "candidate_id": f"candidate-{index}",
            "group_id": "group-1",
            "variant_role": "PRIMARY" if index == 0 else "MANDATORY_SECONDARY",
            "relationship_to_primary": "SELF" if index == 0 else "CROP_VARIANT",
            "provenance": "PDF_EMBEDDED",
            "photo_id": "P001-I01",
            "page": 1,
            "width": 20,
            "height": 20,
            "file_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        }
        for index in range(37)
    ]
    defect = SimpleNamespace(id="d1", external_defect_id="147031")

    with pytest.raises(RuntimeError, match="no visual evidence was silently truncated"):
        controller._visual_files_for_defect(1, defect)


def test_stale_photo_detail_conclusions_are_reduced_to_routing_only() -> None:
    controller = object.__new__(TopologyAwareFireSealController)
    controller._image_variant_receipt_sha256 = lambda: "c" * 64
    evidence = SimpleNamespace(
        id="e1",
        page_number=2,
        region_reference="photo-detail:P002-I01:defect:d1",
        evidence_type="defect_photo_detail_review",
        source_json={
            "photo_id": "P002-I01",
            "image_variant_receipt_sha256": "old",
            "visible_services": ["unsupported stale conclusion"],
            "physical_facts": ["unsupported stale fact"],
        },
    )

    compact = controller._compact_evidence_row(evidence)

    assert compact["photo_id"] == "P002-I01"
    assert compact["stale_visual_conclusions_omitted"] is True
    assert "visible_services" not in compact
    assert "physical_facts" not in compact


def test_stale_photo_link_categories_become_unclassified_routing() -> None:
    controller = object.__new__(TopologyAwareFireSealController)
    controller._image_variant_receipt_sha256 = lambda: "c" * 64
    evidence = SimpleNamespace(
        id="e1",
        page_number=2,
        region_reference="photo-linkage:page:2:defect:d1",
        evidence_type=PHOTO_LINK_EVIDENCE_TYPE,
        source_json={
            "image_variant_receipt_sha256": "old",
            "associated_photo_ids": ["P002-I01"],
            "uncertain_photo_ids": ["P002-I02"],
            "ignored_photo_ids": ["P002-I03"],
            "association_basis": ["unsupported stale conclusion"],
        },
    )

    compact = controller._compact_evidence_row(evidence)

    assert compact["photo_ids_for_re_review"] == [
        "P002-I01",
        "P002-I02",
        "P002-I03",
    ]
    assert compact["stale_visual_conclusions_omitted"] is True
    assert "associated_photo_ids" not in compact
    assert "uncertain_photo_ids" not in compact
    assert "ignored_photo_ids" not in compact
    assert "association_basis" not in compact


def test_stale_linkage_re_reviews_ignored_and_unclassified_page_images(
    tmp_path: Path,
) -> None:
    controller = object.__new__(TopologyAwareFireSealController)
    controller.receipt_dir = tmp_path
    controller._image_variant_receipt_sha256 = lambda: "c" * 64
    report = tmp_path / "report.pdf"
    report.write_bytes(b"report")
    inventory: dict[str, dict] = {}
    image_paths: dict[str, Path] = {}
    for occurrence, photo_id in enumerate(
        ("P001-I01", "P001-I02", "P001-I03", "P001-I04"),
        start=1,
    ):
        image_path = tmp_path / f"{photo_id}.png"
        Image.new("RGB", (20, 20), "white").save(image_path)
        image_paths[photo_id] = image_path
        inventory[photo_id] = {
            "photo_id": photo_id,
            "page_number": 1,
            "occurrence": occurrence,
            "tiny_artifact": False,
            "decorative_candidate": photo_id == "P001-I04",
        }
    evidence = SimpleNamespace(
        page_number=1,
        evidence_type=PHOTO_LINK_EVIDENCE_TYPE,
        source_json={
            "image_variant_receipt_sha256": "old",
            "associated_photo_ids": ["P001-I01"],
            "uncertain_photo_ids": [],
            "ignored_photo_ids": ["P001-I02"],
        },
    )
    controller._direct_evidence = lambda _defect: [evidence]
    controller._photo_inventory = lambda: inventory
    controller.workspace_report = lambda _agent_id: report
    controller._preferred_photo_sources = lambda _report, row: [
        {
            "path": image_paths[row["photo_id"]],
            "candidate_id": f"{row['photo_id']}:primary",
            "group_id": f"group:{row['photo_id']}",
            "variant_role": "PRIMARY",
            "relationship_to_primary": "SELF",
            "provenance": "PDF_EMBEDDED",
            "photo_id": row["photo_id"],
            "page": 1,
            "width": 20,
            "height": 20,
            "file_sha256": hashlib.sha256(
                image_paths[row["photo_id"]].read_bytes()
            ).hexdigest(),
        }
    ]
    contact = tmp_path / "contact.png"
    Image.new("RGB", (20, 20), "white").save(contact)
    controller._contact_sheet = lambda _rows, _index: contact
    labelled_dir = tmp_path / "photo-layout-labelled"
    labelled_dir.mkdir()
    Image.new("RGB", (20, 20), "white").save(
        labelled_dir / "page-0001-labelled.png"
    )
    defect = SimpleNamespace(id="d1", external_defect_id="147031")

    _files, manifest = controller._visual_files_for_defect(1, defect)

    reviewed = [
        item["requested_photo_id"]
        for item in manifest
        if item.get("role") == "defect_photo"
    ]
    assert reviewed == ["P001-I01", "P001-I02", "P001-I03"]
    assert "P001-I04" not in reviewed


def test_topology_fails_if_required_labelled_page_context_is_missing(
    tmp_path: Path,
) -> None:
    controller = object.__new__(TopologyAwareFireSealController)
    controller.receipt_dir = tmp_path
    report = tmp_path / "report.pdf"
    report.write_bytes(b"report")
    image = tmp_path / "detail.png"
    Image.new("RGB", (20, 20), "white").save(image)
    row = {"photo_id": "P001-I01", "page_number": 1}
    evidence = SimpleNamespace(
        page_number=1,
        evidence_type="defect_photo_detail_review",
        source_json={"photo_id": "P001-I01"},
    )
    controller._direct_evidence = lambda _defect: [evidence]
    controller._photo_inventory = lambda: {"P001-I01": row}
    controller.workspace_report = lambda _agent_id: report
    controller._preferred_photo_sources = lambda _report, _row: [
        {
            "path": image,
            "candidate_id": "P001-I01:primary",
            "group_id": "group-1",
            "variant_role": "PRIMARY",
            "relationship_to_primary": "SELF",
            "provenance": "PDF_EMBEDDED",
            "photo_id": "P001-I01",
            "page": 1,
            "width": 20,
            "height": 20,
            "file_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        }
    ]
    defect = SimpleNamespace(id="d1", external_defect_id="147031")

    with pytest.raises(RuntimeError, match="no page context was silently omitted"):
        controller._visual_files_for_defect(1, defect)
