from __future__ import annotations

import hashlib
import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_classifire_real_uat_photoaware as photoaware_module  # noqa: E402
from run_classifire_real_uat_layoutaware import LayoutAwareController  # noqa: E402
from run_classifire_real_uat_photoaware import PhotoAwareController  # noqa: E402


def _source() -> str:
    return (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_classifire_real_uat_photoaware.py"
    ).read_text(encoding="utf-8")


def test_photoaware_runner_requires_native_resolution_and_zoom_fallback() -> None:
    source = _source()
    assert 'document.extract_image(xref)' in source
    assert 'PHOTO_ZOOM_DPI = 420' in source
    assert 'page.get_pixmap(' in source
    assert 'needs_zoom' in source
    assert 'native_extraction_ok' in source


def test_photoaware_runner_ignores_decorative_report_graphics() -> None:
    source = _source()
    assert 'decorative_candidate' in source
    assert 'header/footer' in source
    assert 'Company logos, header/footer' in source
    assert 'scope_relevance": "relevant|non_scope|uncertain' in source


def test_photoaware_runner_reconciles_multiple_views_without_double_counting() -> None:
    source = _source()
    assert 'same_asset_same_side_different_angle' in source
    assert 'same_service_opposite_barrier_side' in source
    assert 'same_opening_opposite_barrier_side' in source
    assert 'Photograph count NEVER equals service count or opening count.' in source
    assert 'The same service photographed on opposite faces of a wall' in source
    assert 'Multiple distinct services passing through one opening are separate Services but one Opening.' in source


def test_photoaware_evidence_is_defect_linked_before_physical_submission() -> None:
    source = _source()
    assert 'PHOTO_LINK_EVIDENCE_TYPE = "defect_page_photo_linkage_review"' in source
    assert 'PHOTO_DETAIL_EVIDENCE_TYPE = "defect_photo_detail_review"' in source
    assert 'PHOTO_RECONCILIATION_EVIDENCE_TYPE = "defect_photo_reconciliation"' in source
    assert '"external_defect_id": defect.external_defect_id or defect.defect_code' in source
    assert 'final_state = self.run_defectwise_physical()' in source


def test_pymupdf_is_a_runtime_dependency() -> None:
    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert '"PyMuPDF>=1.26,<2"' in pyproject


def _linked_row(tmp_path: Path) -> tuple[PhotoAwareController, dict, Path]:
    controller = object.__new__(PhotoAwareController)
    controller.receipt_dir = tmp_path
    staging_dir = tmp_path / "photo-linked"
    staging_dir.mkdir(parents=True)
    staging = staging_dir / "staging.jpg"
    Image.new("RGB", (1200, 900), "red").save(staging, format="JPEG")
    digest = hashlib.sha256(staging.read_bytes()).hexdigest()
    cache_dir = tmp_path / "photo-linked" / "by-sha256" / digest[:2]
    cache_dir.mkdir(parents=True)
    linked = cache_dir / f"{digest}.jpg"
    staging.replace(linked)
    row = {
        "photo_id": "P001-I01",
        "full_resolution_required": True,
        "full_resolution_status": "VERIFIED",
        "full_resolution_path": linked.relative_to(tmp_path).as_posix(),
        "full_resolution_sha256": digest,
        "full_resolution_width": 1200,
        "full_resolution_height": 900,
    }
    return controller, row, linked


def test_preferred_photo_path_accepts_verified_content_addressed_jpeg(
    tmp_path: Path,
) -> None:
    controller, row, linked = _linked_row(tmp_path)
    controller._preferred_photo_sources = lambda _report, _row: [{"path": linked.resolve()}]

    assert controller._preferred_photo_path(tmp_path / "report.pdf", row) == linked.resolve()


def test_preferred_photo_path_fails_closed_when_required_link_is_unavailable(
    tmp_path: Path,
) -> None:
    controller = object.__new__(PhotoAwareController)
    controller.receipt_dir = tmp_path
    row = {
        "photo_id": "P001-I01",
        "full_resolution_required": True,
        "full_resolution_status": "REJECTED",
        "native_path": str(tmp_path / "embedded.png"),
    }
    (tmp_path / "embedded.png").write_bytes(b"thumbnail")

    with pytest.raises(RuntimeError, match="required but was not materialized"):
        controller._preferred_photo_path(tmp_path / "report.pdf", row)


def test_preferred_photo_path_rejects_verified_file_outside_linked_cache(
    tmp_path: Path,
) -> None:
    controller, row, _linked = _linked_row(tmp_path)
    outside = tmp_path / "outside.jpg"
    Image.new("RGB", (1200, 900), "red").save(outside, format="JPEG")
    row["full_resolution_path"] = str(outside)
    row["full_resolution_sha256"] = hashlib.sha256(outside.read_bytes()).hexdigest()
    controller._preferred_photo_sources = lambda _report, _row: (_ for _ in ()).throw(
        RuntimeError("central path validation failed")
    )

    with pytest.raises(RuntimeError, match="central path validation"):
        controller._preferred_photo_path(tmp_path / "report.pdf", row)


def test_stage_visuals_always_ensures_linked_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = object.__new__(PhotoAwareController)
    report = tmp_path / "report.pdf"
    report.write_bytes(b"report placeholder")
    calls: list[tuple[str, Path]] = []
    monkeypatch.setattr(
        LayoutAwareController,
        "stage_visuals",
        lambda _self: {"page_count": 1},
    )
    controller.workspace_report = lambda _agent_id: report
    controller._ensure_linked_photo_inventory = lambda path: calls.append(("16b", path))
    controller._ensure_image_variant_inventory = lambda path: calls.append(("16c", path))

    manifest = controller.stage_visuals()

    assert manifest == {"page_count": 1}
    assert calls == [("16b", report), ("16c", report)]


def test_high_detail_runner_is_fail_closed_and_content_binds_derived_visuals() -> None:
    source = _source()
    assert 'IMAGE_VARIANT_INVENTORY_RECEIPT = IMAGE_VARIANT_RECEIPT_FILENAME' in source
    assert 'self._ensure_image_variant_inventory(report)' in source
    assert 'proven highest-usable-detail PRIMARY' in source
    assert 'no photos were silently truncated' in source
    assert 'image_variant_receipt_sha256' in source
    assert 'defect-{defect_index:03d}-binding.json' in source
    assert 'if output.is_file() and binding_path.is_file():' in source
    variant_stage = inspect.getsource(PhotoAwareController._ensure_image_variant_inventory)
    assert "SessionLocal" not in variant_stage
    assert "invoke_tool" not in variant_stage
    assert "register_observations" not in variant_stage


def test_contact_sheet_regenerates_when_visual_input_changes(tmp_path: Path) -> None:
    controller = object.__new__(PhotoAwareController)
    controller.receipt_dir = tmp_path
    controller._image_variant_receipt_sha256 = lambda: "b" * 64
    image = tmp_path / "primary.png"
    Image.new("RGB", (80, 60), "red").save(image)

    output = controller._contact_sheet([("P001-I01 [PRIMARY]", image)], 1)
    first_sha = hashlib.sha256(output.read_bytes()).hexdigest()
    Image.new("RGB", (80, 60), "blue").save(image)

    regenerated = controller._contact_sheet([("P001-I01 [PRIMARY]", image)], 1)
    second_sha = hashlib.sha256(regenerated.read_bytes()).hexdigest()

    assert regenerated == output
    assert second_sha != first_sha
    binding = json.loads(
        (tmp_path / "photo-contact-sheets" / "defect-001-binding.json").read_text(
            encoding="utf-8"
        )
    )
    assert binding["binding"]["image_variant_receipt_sha256"] == "b" * 64
    assert binding["output_sha256"] == second_sha


def test_linked_inventory_receipt_is_written_even_when_report_has_no_images(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pymupdf

    report = tmp_path / "report.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(report)
    document.close()
    captured: dict = {}

    def fake_materialize(_report, rows, destination_root, **kwargs):
        captured["rows"] = rows
        captured["destination_root"] = destination_root
        captured["kwargs"] = kwargs
        return SimpleNamespace(rows=[], receipt={"status": "PASS"}, results=[], ok=True)

    monkeypatch.setattr(photoaware_module, "materialize_linked_images", fake_materialize)
    controller = object.__new__(PhotoAwareController)
    controller.receipt_dir = tmp_path
    controller.receipt = {
        "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
    }

    pages, rows = controller._build_photo_inventory(report)

    assert pages == {}
    assert rows == {}
    inventory = json.loads(
        (tmp_path / "16b-photo-inventory-linked.json").read_text(encoding="utf-8")
    )
    assert inventory["materialization_ok"] is True
    assert inventory["cache_verification_ok"] is True
    assert inventory["photo_occurrence_count"] == 0
    assert captured["rows"] == []
    assert captured["destination_root"] == tmp_path
    assert captured["kwargs"]["prior_receipt"] is None
    controller._linked_photo_inventory_cache = (pages, rows)
    variant_result = controller._ensure_image_variant_inventory(report)
    assert variant_result.rows == ()
    assert variant_result.groups == ()
    assert (tmp_path / "16c-image-variant-resolution.json").is_file()


def test_runner_writes_and_consumes_bound_16c_inventory_for_all_page_images(
    tmp_path: Path,
) -> None:
    import pymupdf

    source_image = tmp_path / "source.png"
    Image.new("RGB", (320, 240), "orange").save(source_image)
    report = tmp_path / "report.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_image(pymupdf.Rect(72, 72, 392, 312), filename=str(source_image))
    document.save(report)
    document.close()

    controller = object.__new__(PhotoAwareController)
    controller.receipt_dir = tmp_path
    controller.receipt = {
        "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
    }

    result = controller._ensure_image_variant_inventory(report)
    payload = json.loads(
        (tmp_path / "16c-image-variant-resolution.json").read_text(encoding="utf-8")
    )
    _pages, by_id = controller._ensure_linked_photo_inventory(report)
    row = next(iter(by_id.values()))
    sources = controller._preferred_photo_sources(report, row)

    assert result.to_dict()["schema"] == "CLASSIFIRE-IMAGE-VARIANT-RESOLUTION-v1"
    assert payload["receipt"]["report"]["sha256"] == controller.receipt["report_sha256"]
    assert row["image_variant_group_id"]
    assert sources[0]["variant_role"] == "PRIMARY"
    assert any(item["variant_role"] == "MANDATORY_SECONDARY" for item in sources)


def test_variant_path_maps_are_cached_but_each_selected_file_is_rehashed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = object.__new__(PhotoAwareController)
    controller.receipt_dir = tmp_path
    receipt_path = tmp_path / "16c-image-variant-resolution.json"
    receipt_path.write_text("{}", encoding="utf-8")
    receipt_sha256 = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    controller._image_variant_receipt_sha256 = lambda: receipt_sha256

    paths = {
        "primary-1": tmp_path / "primary-1.bin",
        "secondary-1": tmp_path / "secondary-1.bin",
        "primary-2": tmp_path / "primary-2.bin",
    }
    for candidate_id, path in paths.items():
        path.write_bytes(candidate_id.encode("ascii"))

    def candidate(candidate_id: str, occurrence_id: str, role: str) -> dict:
        path = paths[candidate_id]
        return {
            "candidate_id": candidate_id,
            "occurrence_id": occurrence_id,
            "photo_id": occurrence_id,
            "page_number": 1,
            "path": path.relative_to(tmp_path).as_posix(),
            "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "width": 10,
            "height": 10,
            "provenance": "PDF_EMBEDDED",
            "context_tags": [],
            "role": role,
        }

    result = SimpleNamespace(
        rows=(
            candidate("primary-1", "P001-I01", "PRIMARY"),
            candidate("secondary-1", "P001-I01", "MANDATORY_SECONDARY"),
            candidate("primary-2", "P002-I01", "PRIMARY"),
        ),
        groups=(
            {
                "group_id": "group-1",
                "primary_candidate_id": "primary-1",
                "member_occurrences": [{"occurrence_id": "P001-I01"}],
                "mandatory_secondary": [
                    {
                        "candidate_id": "secondary-1",
                        "relationship": "ANNOTATED_VARIANT",
                    }
                ],
            },
            {
                "group_id": "group-2",
                "primary_candidate_id": "primary-2",
                "member_occurrences": [{"occurrence_id": "P002-I01"}],
                "mandatory_secondary": [],
            },
        ),
    )
    controller._ensure_image_variant_inventory = lambda _report: result
    calls = {"primary": 0, "secondary": 0}

    def primary_validator(_result: object, *, artifact_root: Path) -> dict[str, Path]:
        assert artifact_root == tmp_path
        calls["primary"] += 1
        return {key: paths[key].resolve() for key in ("primary-1", "primary-2")}

    def secondary_validator(_result: object, *, artifact_root: Path) -> dict[str, Path]:
        assert artifact_root == tmp_path
        calls["secondary"] += 1
        return {"secondary-1": paths["secondary-1"].resolve()}

    monkeypatch.setattr(photoaware_module, "validated_primary_paths", primary_validator)
    monkeypatch.setattr(
        photoaware_module,
        "validated_mandatory_secondary_paths",
        secondary_validator,
    )
    report = tmp_path / "report.pdf"
    first = controller._preferred_photo_sources(
        report,
        {"photo_id": "P001-I01", "image_variant_group_id": "group-1"},
    )
    second = controller._preferred_photo_sources(
        report,
        {"photo_id": "P002-I01", "image_variant_group_id": "group-2"},
    )

    assert [item["candidate_id"] for item in first] == ["primary-1", "secondary-1"]
    assert [item["candidate_id"] for item in second] == ["primary-2"]
    assert calls == {"primary": 1, "secondary": 1}

    paths["primary-2"].write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="changed after central validation"):
        controller._preferred_photo_sources(
            report,
            {"photo_id": "P002-I01", "image_variant_group_id": "group-2"},
        )
    assert calls == {"primary": 1, "secondary": 1}
