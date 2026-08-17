from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageEnhance, ImageOps

from classifire.services import image_variant_resolution as variants


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _scene(size: tuple[int, int] = (240, 180), *, phase: int = 0) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size)
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            pixels[x, y] = (
                (x * 7 + y * 3 + phase * 11) % 256,
                (x * 2 + y * 9 + phase * 17) % 256,
                (x * 5 + y * 5 + phase * 23) % 256,
            )
    draw = ImageDraw.Draw(image)
    line_width = max(2, min(width, height) // 35)
    draw.ellipse(
        (width // 8, height // 7, width * 5 // 8, height * 5 // 7),
        outline=(250, 240, 20),
        width=line_width,
    )
    draw.line(
        (0, height * 4 // 5, width, height // 5),
        fill=(245, 245, 245),
        width=line_width,
    )
    draw.rectangle(
        (width * 2 // 3, height // 8, width * 9 // 10, height * 3 // 8),
        fill=(20, 30, 220),
    )
    return image


def _save(
    image: Image.Image,
    path: Path,
    *,
    image_format: str | None = None,
    quality: int = 92,
) -> Path:
    options: dict[str, object] = {}
    chosen_format = image_format or path.suffix.lstrip(".").upper()
    if chosen_format in {"JPG", "JPEG"}:
        chosen_format = "JPEG"
        options["quality"] = quality
    image.save(path, format=chosen_format, **options)
    return path


def _inputs(tmp_path: Path) -> tuple[Path, Path, str, str]:
    report = tmp_path / "active-report.pdf"
    report.write_bytes(b"%PDF-1.7\ncontrolled image-variant test\n%%EOF")
    inventory = tmp_path / "16b-photo-inventory-linked.json"
    inventory.write_text(
        json.dumps({"schema": "CLASSIFIRE-LINKED-PHOTO-INVENTORY-v1"}),
        encoding="utf-8",
    )
    return report, inventory, _sha256(report), _sha256(inventory)


def _occurrence(
    occurrence_id: str,
    photo_id: str,
    page_number: int,
    embedded_path: Path,
    *,
    xref: int = 10,
) -> variants.ImageOccurrence:
    return variants.ImageOccurrence(
        occurrence_id=occurrence_id,
        photo_id=photo_id,
        page_number=page_number,
        xref=xref,
        bbox=(10.0, 20.0, 60.0, 70.0),
        embedded_path=embedded_path,
    )


def _candidate(
    candidate_id: str,
    occurrence_id: str,
    path: Path,
    *,
    provenance: str = "LINKED_ORIGINAL",
    context_tags: tuple[str, ...] = (),
) -> variants.ImageCandidate:
    return variants.ImageCandidate(
        candidate_id=candidate_id,
        occurrence_id=occurrence_id,
        path=path,
        provenance=provenance,
        context_tags=context_tags,
    )


def _resolve(
    tmp_path: Path,
    occurrences: list[variants.ImageOccurrence],
    candidates: list[variants.ImageCandidate],
) -> variants.ImageVariantResolution:
    report, inventory, report_sha256, inventory_sha256 = _inputs(tmp_path)
    return variants.resolve_image_variants(
        report_path=report,
        linked_inventory_path=inventory,
        occurrences=occurrences,
        candidates=candidates,
        artifact_root=tmp_path,
        expected_report_sha256=report_sha256,
        expected_inventory_sha256=inventory_sha256,
    )


def _row(result: variants.ImageVariantResolution, candidate_id: str) -> dict:
    return dict(next(row for row in result.rows if row["candidate_id"] == candidate_id))


def test_exact_bytes_and_decoded_pixels_are_cryptographic_equivalents(
    tmp_path: Path,
) -> None:
    source = _scene((120, 90))
    embedded = _save(source, tmp_path / "embedded.png", image_format="PNG")
    same_pixels = _save(source, tmp_path / "same-pixels.bmp", image_format="BMP")
    occurrence = _occurrence("occ-1", "P001-I01", 1, embedded)

    result = _resolve(
        tmp_path,
        [occurrence],
        [
            _candidate("exact-bytes", "occ-1", embedded),
            _candidate("same-pixels", "occ-1", same_pixels),
        ],
    )

    relationships = {
        _row(result, "exact-bytes")["relationship_to_primary"],
        _row(result, "same-pixels")["relationship_to_primary"],
        _row(result, "embedded:occ-1")["relationship_to_primary"],
    }
    assert variants.EXACT_BYTES in relationships
    assert variants.EXACT_DECODED_PIXELS in relationships
    assert _row(result, "embedded:occ-1")["role"] == variants.MANDATORY_SECONDARY
    assert all(
        row["role"] in {variants.PRIMARY, variants.EQUIVALENT, variants.MANDATORY_SECONDARY}
        for row in result.rows
    )


def test_rejpeg_and_resize_require_all_full_frame_gates(tmp_path: Path) -> None:
    source = _scene((360, 270))
    original = _save(source, tmp_path / "original.jpg", quality=96)
    embedded_image = source.resize((90, 68), Image.Resampling.LANCZOS)
    embedded = _save(embedded_image, tmp_path / "embedded.jpg", quality=78)

    result = _resolve(
        tmp_path,
        [_occurrence("occ-1", "P001-I01", 2, embedded)],
        [_candidate("full-original", "occ-1", original)],
    )

    assert result.groups[0]["primary_candidate_id"] == "full-original"
    thumbnail = _row(result, "embedded:occ-1")
    assert thumbnail["relationship_to_primary"] == variants.FULL_FRAME_EQUIVALENT
    assert thumbnail["role"] == variants.MANDATORY_SECONDARY
    assert {
        "ASPECT_GATE_PASS",
        "DHASH_GATE_PASS",
        "MEAN_ERROR_GATE_PASS",
        "CORRELATION_GATE_PASS",
        "EDGE_GATE_PASS",
        "LUMA_MEAN_GATE_PASS",
        "LUMA_STDDEV_GATE_PASS",
    }.issubset(thumbnail["relationship_reason_codes"])


def test_verified_center_crop_linked_original_is_primary_with_explicit_binding(
    tmp_path: Path,
) -> None:
    report = tmp_path / "active-report.pdf"
    report.write_bytes(b"%PDF-1.7\ncenter-crop binding test\n%%EOF")
    source = Image.new("RGB", (3024, 4032))
    draw = ImageDraw.Draw(source)
    for row in range(12):
        for column in range(9):
            draw.rectangle(
                (column * 336, row * 336, (column + 1) * 336, (row + 1) * 336),
                fill=(
                    (column * 37 + row * 19) % 256,
                    (column * 11 + row * 43) % 256,
                    (column * 53 + row * 7) % 256,
                ),
            )
    noise = Image.effect_noise(source.size, 36.0).convert("RGB")
    source = Image.blend(source, noise, 0.16)
    draw = ImageDraw.Draw(source)
    draw.rectangle((250, 700, 2750, 3300), outline=(255, 220, 10), width=35)
    draw.line((200, 3200, 2800, 900), fill=(10, 220, 255), width=28)
    linked = _save(source, tmp_path / "linked-original.jpg", quality=93)
    with Image.open(linked) as decoded:
        embedded_image = ImageOps.fit(
            decoded.convert("RGB"),
            (50, 50),
            Image.Resampling.LANCZOS,
        )
    embedded = _save(embedded_image, tmp_path / "embedded.png", image_format="PNG")
    inventory = tmp_path / "16b-photo-inventory-linked.json"
    inventory.write_text(
        json.dumps(
            {
                "schema": "CLASSIFIRE-LINKED-PHOTO-INVENTORY-v1",
                "report_sha256": _sha256(report),
                "photos": [
                    {
                        "photo_id": "P001-I01",
                        "page_number": 1,
                        "full_resolution_status": "VERIFIED",
                        "full_resolution_path": linked.relative_to(tmp_path).as_posix(),
                        "full_resolution_sha256": _sha256(linked),
                        "full_resolution_width": 3024,
                        "full_resolution_height": 4032,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = variants.resolve_image_variants(
        report_path=report,
        linked_inventory_path=inventory,
        occurrences=[_occurrence("occ-1", "P001-I01", 1, embedded)],
        candidates=[
            _candidate(
                "linked-original",
                "occ-1",
                linked,
                provenance="REPORT_LINKED_ORIGINAL",
                context_tags=("VERIFIED_THUMBNAIL_BINDING",),
            )
        ],
        artifact_root=tmp_path,
        expected_report_sha256=_sha256(report),
        expected_inventory_sha256=_sha256(inventory),
    )

    assert result.groups[0]["primary_candidate_id"] == "linked-original"
    assert result.groups[0]["status"] == variants.RESOLVED
    binding = _row(result, "linked-original")["verified_linked_binding"]
    assert binding["transform"] == "CENTER_CROP_COVER"
    assert binding["normalized_crop_box"] == pytest.approx([0.0, 0.125, 1.0, 0.875])
    embedded_row = _row(result, "embedded:occ-1")
    assert embedded_row["role"] == variants.MANDATORY_SECONDARY
    assert embedded_row["relationship_to_primary"] == variants.CROP_VARIANT
    assert "LEFT_IS_CROP" in embedded_row["relationship_reason_codes"]


def test_appendix_higher_detail_becomes_primary_and_keeps_occurrence_provenance(
    tmp_path: Path,
) -> None:
    source = _scene((480, 360))
    low = _save(
        source.resize((80, 60), Image.Resampling.LANCZOS),
        tmp_path / "body-thumb.jpg",
        quality=82,
    )
    appendix = _save(source, tmp_path / "appendix-original.png", image_format="PNG")

    result = _resolve(
        tmp_path,
        [
            _occurrence("body-occ", "P001-I01", 1, low, xref=11),
            _occurrence("appendix-occ", "P010-I01", 10, appendix, xref=99),
        ],
        [
            _candidate("body-copy", "body-occ", low, provenance="BODY"),
            _candidate("appendix-copy", "appendix-occ", appendix, provenance="APPENDIX"),
        ],
    )

    assert len(result.groups) == 1
    group = result.groups[0]
    assert group["primary_candidate_id"] in {"appendix-copy", "embedded:appendix-occ"}
    assert group["primary_width"] == 480
    assert group["primary_height"] == 360
    assert {
        (item["occurrence_id"], item["page_number"], item["xref"])
        for item in group["member_occurrences"]
    } == {
        ("body-occ", 1, 11),
        ("appendix-occ", 10, 99),
    }


def test_crop_annotation_and_contrast_are_mandatory_secondary_context(
    tmp_path: Path,
) -> None:
    source = _scene((240, 180))
    embedded = _save(source, tmp_path / "embedded.png", image_format="PNG")
    crop_image = source.crop((45, 15, 195, 165))
    crop = _save(crop_image, tmp_path / "crop.png", image_format="PNG")
    annotated_image = source.copy()
    draw = ImageDraw.Draw(annotated_image)
    draw.rectangle((12, 12, 58, 42), fill=(255, 20, 20))
    annotation = _save(annotated_image, tmp_path / "annotation.png", image_format="PNG")
    contrast_image = ImageEnhance.Contrast(source).enhance(1.8)
    contrast = _save(contrast_image, tmp_path / "contrast.png", image_format="PNG")

    result = _resolve(
        tmp_path,
        [_occurrence("occ-1", "P001-I01", 3, embedded)],
        [
            _candidate("base", "occ-1", embedded),
            _candidate("crop", "occ-1", crop),
            _candidate("annotation", "occ-1", annotation),
            _candidate("contrast", "occ-1", contrast),
        ],
    )

    assert _row(result, "crop")["relationship_to_primary"] == variants.CROP_VARIANT
    assert _row(result, "annotation")["relationship_to_primary"] == variants.ANNOTATED_VARIANT
    assert _row(result, "contrast")["relationship_to_primary"] == variants.CONTRAST_VARIANT
    for candidate_id in ("crop", "annotation", "contrast"):
        assert _row(result, candidate_id)["role"] == variants.MANDATORY_SECONDARY
    assert {item["candidate_id"] for item in result.groups[0]["mandatory_secondary"]} >= {
        "crop",
        "annotation",
        "contrast",
    }


def test_blurry_upscale_cannot_win_primary_ranking(tmp_path: Path) -> None:
    source = _scene((96, 72))
    embedded = _save(source, tmp_path / "native.png", image_format="PNG")
    blurry = _save(
        source.resize((384, 288), Image.Resampling.BICUBIC),
        tmp_path / "blurry-upscale.png",
        image_format="PNG",
    )

    result = _resolve(
        tmp_path,
        [_occurrence("occ-1", "P001-I01", 1, embedded)],
        [
            _candidate("native-copy", "occ-1", embedded),
            _candidate("blurry-upscale", "occ-1", blurry),
        ],
    )

    assert _row(result, "blurry-upscale")["likely_upscaled"] is True
    assert _row(result, "blurry-upscale")["proven_detail_area"] == 96 * 72
    assert result.groups[0]["primary_candidate_id"] != "blurry-upscale"


def test_similar_but_distinct_occurrences_are_not_merged(tmp_path: Path) -> None:
    first_image = _scene((200, 150))
    second_image = first_image.copy()
    draw = ImageDraw.Draw(second_image)
    draw.rectangle((0, 0, 90, 95), fill=(15, 220, 90))
    first = _save(first_image, tmp_path / "first.png", image_format="PNG")
    second = _save(second_image, tmp_path / "second.png", image_format="PNG")

    result = _resolve(
        tmp_path,
        [
            _occurrence("occ-a", "P001-I01", 1, first),
            _occurrence("occ-b", "P002-I01", 2, second),
        ],
        [
            _candidate("first-copy", "occ-a", first),
            _candidate("second-copy", "occ-b", second),
        ],
    )

    assert len(result.groups) == 2
    assert all(len(group["member_occurrences"]) == 1 for group in result.groups)
    cross_relationships = {
        item["relationship"]
        for group in result.groups
        for item in group["mandatory_secondary"]
        if item["candidate_id"] in {"first-copy", "second-copy", "embedded:occ-a", "embedded:occ-b"}
    }
    assert variants.SIMILAR_DISTINCT in cross_relationships


def test_localized_substitution_cannot_pass_full_frame_spatial_gates(
    tmp_path: Path,
) -> None:
    first_image = _scene((240, 180))
    second_image = first_image.copy()
    ImageDraw.Draw(second_image).rectangle((110, 80, 129, 99), fill=(255, 0, 0))
    first = _save(first_image, tmp_path / "first.png", image_format="PNG")
    second = _save(second_image, tmp_path / "second.png", image_format="PNG")

    first_asset = variants._load_asset(
        candidate_id="metric-a",
        occurrence_id="metric-a",
        path=first,
        provenance="TEST",
        context_tags=(),
        automatic_embedded=True,
        artifact_root=tmp_path,
        policy=variants.DEFAULT_IMAGE_VARIANT_POLICY,
    )
    second_asset = variants._load_asset(
        candidate_id="metric-b",
        occurrence_id="metric-b",
        path=second,
        provenance="TEST",
        context_tags=(),
        automatic_embedded=True,
        artifact_root=tmp_path,
        policy=variants.DEFAULT_IMAGE_VARIANT_POLICY,
    )
    direct = variants._classify_full_frame_pair(
        first_asset,
        second_asset,
        variants.DEFAULT_IMAGE_VARIANT_POLICY,
    )
    assert (
        direct.correlation >= variants.DEFAULT_IMAGE_VARIANT_POLICY.minimum_full_frame_correlation
    )
    assert direct.edge_correlation >= (
        variants.DEFAULT_IMAGE_VARIANT_POLICY.minimum_full_frame_edge_correlation
    )
    assert direct.mean_error <= variants.DEFAULT_IMAGE_VARIANT_POLICY.maximum_full_frame_mean_error
    assert "LOCALIZED_CHANGE_GATE_FAILED" in direct.reason_codes

    result = _resolve(
        tmp_path,
        [
            _occurrence("occ-a", "P001-I01", 1, first),
            _occurrence("occ-b", "P002-I01", 2, second),
        ],
        [
            _candidate("first-copy", "occ-a", first),
            _candidate("second-copy", "occ-b", second),
        ],
    )

    assert len(result.groups) == 2
    cross_relationships = {
        item["relationship"]
        for group in result.groups
        for item in group["mandatory_secondary"]
        if item["candidate_id"] in {"first-copy", "second-copy"}
    }
    assert cross_relationships
    assert variants.FULL_FRAME_EQUIVALENT not in cross_relationships


def test_low_information_uniform_images_require_cryptographic_identity(
    tmp_path: Path,
) -> None:
    gray_128 = _save(
        Image.new("RGB", (240, 180), (128, 128, 128)),
        tmp_path / "gray-128.png",
        image_format="PNG",
    )
    gray_134 = _save(
        Image.new("RGB", (240, 180), (134, 134, 134)),
        tmp_path / "gray-134.png",
        image_format="PNG",
    )
    gray_128_large = _save(
        Image.new("RGB", (480, 360), (128, 128, 128)),
        tmp_path / "gray-128-large.png",
        image_format="PNG",
    )

    result = _resolve(
        tmp_path,
        [
            _occurrence("occ-a", "P001-I01", 1, gray_128),
            _occurrence("occ-b", "P002-I01", 2, gray_134),
            _occurrence("occ-c", "P003-I01", 3, gray_128_large),
        ],
        [
            _candidate("copy-a", "occ-a", gray_128),
            _candidate("copy-b", "occ-b", gray_134),
            _candidate("copy-c", "occ-c", gray_128_large),
        ],
    )

    assert len(result.groups) == 3
    assert all(len(group["member_occurrences"]) == 1 for group in result.groups)


def test_sparse_shared_frame_with_distinct_labels_is_not_equivalent(
    tmp_path: Path,
) -> None:
    first_image = Image.new("RGB", (240, 180), "white")
    first_draw = ImageDraw.Draw(first_image)
    first_draw.rectangle((15, 15, 224, 164), outline="black", width=2)
    first_draw.line((30, 145, 210, 145), fill="black", width=2)
    first_draw.line((30, 145, 30, 30), fill="black", width=2)
    first_draw.rectangle((80, 74, 82, 76), fill="red")
    second_image = first_image.copy()
    second_draw = ImageDraw.Draw(second_image)
    second_draw.rectangle((80, 74, 82, 76), fill="white")
    second_draw.rectangle((166, 48, 168, 50), fill="blue")
    first = _save(first_image, tmp_path / "diagram-a.png", image_format="PNG")
    second = _save(second_image, tmp_path / "diagram-b.png", image_format="PNG")

    result = _resolve(
        tmp_path,
        [
            _occurrence("occ-a", "P001-I01", 1, first),
            _occurrence("occ-b", "P002-I01", 2, second),
        ],
        [
            _candidate("copy-a", "occ-a", first),
            _candidate("copy-b", "occ-b", second),
        ],
    )

    assert len(result.groups) == 2
    assert all(len(group["member_occurrences"]) == 1 for group in result.groups)


def test_unproven_candidate_is_ambiguous_mandatory_context(tmp_path: Path) -> None:
    embedded = _save(_scene((160, 120)), tmp_path / "embedded.png", image_format="PNG")
    unrelated = _save(
        _scene((160, 120), phase=9).transpose(Image.Transpose.FLIP_TOP_BOTTOM),
        tmp_path / "unrelated.png",
        image_format="PNG",
    )

    result = _resolve(
        tmp_path,
        [_occurrence("occ-1", "P001-I01", 1, embedded)],
        [
            _candidate("base", "occ-1", embedded),
            _candidate("unproven", "occ-1", unrelated),
        ],
    )

    row = _row(result, "unproven")
    assert row["role"] == variants.MANDATORY_SECONDARY
    assert row["relationship_to_primary"] == variants.AMBIGUOUS
    assert result.groups[0]["status"] == variants.AMBIGUOUS_STATUS
    assert "unproven" in result.groups[0]["ambiguity_candidate_ids"]


def test_receipt_is_deterministic_sanitized_and_fresh_process_loadable(
    tmp_path: Path,
) -> None:
    embedded = _save(_scene((128, 96)), tmp_path / "embedded.png", image_format="PNG")
    occurrence = _occurrence("occ-1", "P001-I01", 4, embedded)
    candidate = _candidate("linked", "occ-1", embedded, provenance="LINKED_ORIGINAL")
    report, inventory, report_sha256, inventory_sha256 = _inputs(tmp_path)
    kwargs = {
        "report_path": report,
        "linked_inventory_path": inventory,
        "occurrences": [occurrence],
        "candidates": [candidate],
        "artifact_root": tmp_path,
        "expected_report_sha256": report_sha256,
        "expected_inventory_sha256": inventory_sha256,
    }

    first = variants.resolve_image_variants(**kwargs)
    second = variants.resolve_image_variants(**kwargs)
    assert first.to_dict() == second.to_dict()
    serialized = json.dumps(first.to_dict(), sort_keys=True)
    assert str(tmp_path) not in serialized
    assert "http://" not in serialized and "https://" not in serialized
    receipt_path = tmp_path / variants.IMAGE_VARIANT_RECEIPT_FILENAME
    receipt_path.write_text(json.dumps(first.to_dict()), encoding="utf-8")

    loaded = variants.load_image_variant_resolution(
        receipt_path,
        artifact_root=tmp_path,
        expected_report_sha256=report_sha256,
        expected_inventory_sha256=inventory_sha256,
    )
    assert loaded.to_dict() == first.to_dict()
    assert list(variants.validated_primary_paths(loaded, artifact_root=tmp_path)) == [
        first.groups[0]["primary_candidate_id"]
    ]


def test_expected_hash_and_on_disk_tamper_fail_closed(tmp_path: Path) -> None:
    embedded = _save(_scene((128, 96)), tmp_path / "embedded.png", image_format="PNG")
    report, inventory, report_sha256, inventory_sha256 = _inputs(tmp_path)
    occurrence = _occurrence("occ-1", "P001-I01", 1, embedded)
    candidate = _candidate("linked", "occ-1", embedded)

    with pytest.raises(variants.ImageVariantResolutionError, match="REPORT_SHA256_MISMATCH"):
        variants.resolve_image_variants(
            report_path=report,
            linked_inventory_path=inventory,
            occurrences=[occurrence],
            candidates=[candidate],
            artifact_root=tmp_path,
            expected_report_sha256="0" * 64,
            expected_inventory_sha256=inventory_sha256,
        )

    result = variants.resolve_image_variants(
        report_path=report,
        linked_inventory_path=inventory,
        occurrences=[occurrence],
        candidates=[candidate],
        artifact_root=tmp_path,
        expected_report_sha256=report_sha256,
        expected_inventory_sha256=inventory_sha256,
    )
    receipt_path = tmp_path / variants.IMAGE_VARIANT_RECEIPT_FILENAME
    receipt_path.write_text(json.dumps(result.to_dict()), encoding="utf-8")
    embedded.write_bytes(b"tampered")

    with pytest.raises(variants.ImageVariantResolutionError, match="CANDIDATE_FILE_TAMPERED"):
        variants.load_image_variant_resolution(
            receipt_path,
            artifact_root=tmp_path,
            expected_report_sha256=report_sha256,
            expected_inventory_sha256=inventory_sha256,
        )


def test_serialized_relationship_tamper_breaks_resolution_manifest(tmp_path: Path) -> None:
    embedded = _save(_scene((128, 96)), tmp_path / "embedded.png", image_format="PNG")
    report, inventory, report_sha256, inventory_sha256 = _inputs(tmp_path)
    result = variants.resolve_image_variants(
        report_path=report,
        linked_inventory_path=inventory,
        occurrences=[_occurrence("occ-1", "P001-I01", 1, embedded)],
        candidates=[_candidate("linked", "occ-1", embedded)],
        artifact_root=tmp_path,
        expected_report_sha256=report_sha256,
        expected_inventory_sha256=inventory_sha256,
    )
    payload = result.to_dict()
    payload["rows"][0]["relationship_reason_codes"] = ["TAMPERED"]
    receipt_path = tmp_path / variants.IMAGE_VARIANT_RECEIPT_FILENAME
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(variants.ImageVariantResolutionError, match="RESOLUTION_MANIFEST_MISMATCH"):
        variants.load_image_variant_resolution(
            receipt_path,
            artifact_root=tmp_path,
            expected_report_sha256=report_sha256,
            expected_inventory_sha256=inventory_sha256,
        )


@pytest.mark.parametrize(
    ("failure_mode", "expected_code"),
    (
        ("inventory", "TRUSTED_LINKED_INVENTORY_BINDING_FAILED"),
        ("changed-file", "TRUSTED_LINKED_INVENTORY_BINDING_FAILED"),
        ("wrong-thumbnail", "TRUSTED_LINKED_BINDING_RECONFIRMATION_FAILED"),
    ),
)
def test_verified_linked_binding_failures_never_downgrade_to_generic_matching(
    tmp_path: Path,
    failure_mode: str,
    expected_code: str,
) -> None:
    report = tmp_path / "active-report.pdf"
    report.write_bytes(b"%PDF-1.7\ntrusted binding failure test\n%%EOF")
    source = _scene((300, 400), phase=3).resize((900, 1200), Image.Resampling.LANCZOS)
    linked = _save(source, tmp_path / "linked.jpg", quality=94)
    if failure_mode == "wrong-thumbnail":
        thumbnail_source = _scene((300, 400), phase=71).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        embedded_image = ImageOps.fit(
            thumbnail_source,
            (50, 50),
            Image.Resampling.LANCZOS,
        )
    else:
        with Image.open(linked) as decoded:
            embedded_image = ImageOps.fit(
                decoded.convert("RGB"),
                (50, 50),
                Image.Resampling.LANCZOS,
            )
    embedded = _save(embedded_image, tmp_path / "embedded.png", image_format="PNG")
    inventory_sha = _sha256(linked) if failure_mode != "inventory" else "0" * 64
    inventory = tmp_path / "16b-photo-inventory-linked.json"
    inventory.write_text(
        json.dumps(
            {
                "schema": "CLASSIFIRE-LINKED-PHOTO-INVENTORY-v1",
                "report_sha256": _sha256(report),
                "photos": [
                    {
                        "photo_id": "P001-I01",
                        "page_number": 1,
                        "full_resolution_status": "VERIFIED",
                        "full_resolution_path": "linked.jpg",
                        "full_resolution_sha256": inventory_sha,
                        "full_resolution_width": 900,
                        "full_resolution_height": 1200,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    if failure_mode == "changed-file":
        _save(
            _scene((300, 400), phase=19).resize((900, 1200), Image.Resampling.LANCZOS),
            linked,
            quality=94,
        )

    with pytest.raises(variants.ImageVariantResolutionError, match=expected_code):
        variants.resolve_image_variants(
            report_path=report,
            linked_inventory_path=inventory,
            occurrences=[_occurrence("occ-1", "P001-I01", 1, embedded)],
            candidates=[
                _candidate(
                    "linked",
                    "occ-1",
                    linked,
                    provenance="REPORT_LINKED_ORIGINAL",
                    context_tags=("VERIFIED_THUMBNAIL_BINDING",),
                )
            ],
            artifact_root=tmp_path,
            expected_report_sha256=_sha256(report),
            expected_inventory_sha256=_sha256(inventory),
        )


def test_recomputed_manifest_cannot_promote_forced_page_context(tmp_path: Path) -> None:
    source = _scene((480, 360))
    embedded = _save(
        source.resize((80, 60), Image.Resampling.LANCZOS),
        tmp_path / "embedded.png",
        image_format="PNG",
    )
    linked = _save(
        source.resize((240, 180), Image.Resampling.LANCZOS),
        tmp_path / "linked.png",
        image_format="PNG",
    )
    page_context = _save(source, tmp_path / "page-context.png", image_format="PNG")
    report, inventory, report_sha256, inventory_sha256 = _inputs(tmp_path)
    result = variants.resolve_image_variants(
        report_path=report,
        linked_inventory_path=inventory,
        occurrences=[_occurrence("occ-1", "P001-I01", 1, embedded)],
        candidates=[
            _candidate("linked", "occ-1", linked),
            _candidate(
                "page-context",
                "occ-1",
                page_context,
                provenance="PDF_PAGE_CONTEXT",
                context_tags=("ANNOTATIONS_AND_CROP_CONTEXT",),
            ),
        ],
        artifact_root=tmp_path,
        expected_report_sha256=report_sha256,
        expected_inventory_sha256=inventory_sha256,
    )
    payload = result.to_dict()
    rows = {row["candidate_id"]: row for row in payload["rows"]}
    group = payload["groups"][0]
    old_primary_id = group["primary_candidate_id"]
    old_primary = rows[old_primary_id]
    forced = rows["page-context"]
    old_primary["role"] = variants.MANDATORY_SECONDARY
    old_primary["relationship_to_primary"] = variants.FULL_FRAME_EQUIVALENT
    forced["role"] = variants.PRIMARY
    forced["relationship_to_primary"] = variants.SELF
    group.update(
        {
            "primary_candidate_id": "page-context",
            "primary_path": forced["path"],
            "primary_file_sha256": forced["file_sha256"],
            "primary_width": forced["width"],
            "primary_height": forced["height"],
        }
    )
    group["mandatory_secondary"] = [
        item for item in group["mandatory_secondary"] if item["candidate_id"] != "page-context"
    ]
    group["mandatory_secondary"].append(
        {
            "candidate_id": old_primary_id,
            "path": old_primary["path"],
            "role": variants.MANDATORY_SECONDARY,
            "relationship": variants.FULL_FRAME_EQUIVALENT,
            "occurrence_id": old_primary["occurrence_id"],
            "photo_id": old_primary["photo_id"],
            "page_number": old_primary["page_number"],
        }
    )
    payload["receipt"]["resolution_manifest_sha256"] = variants._resolution_manifest(
        payload["rows"], payload["groups"]
    )
    receipt_path = tmp_path / variants.IMAGE_VARIANT_RECEIPT_FILENAME
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        variants.ImageVariantResolutionError,
        match="RECEIPT_FORCED_CONTEXT_ROLE_INVALID",
    ):
        variants.load_image_variant_resolution(
            receipt_path,
            artifact_root=tmp_path,
            expected_report_sha256=report_sha256,
            expected_inventory_sha256=inventory_sha256,
        )


def test_empty_report_produces_a_normal_bound_loadable_receipt(tmp_path: Path) -> None:
    report, inventory, report_sha256, inventory_sha256 = _inputs(tmp_path)

    result = variants.resolve_image_variants(
        report_path=report,
        linked_inventory_path=inventory,
        occurrences=(),
        candidates=(),
        artifact_root=tmp_path,
        expected_report_sha256=report_sha256,
        expected_inventory_sha256=inventory_sha256,
    )

    assert result.rows == ()
    assert result.groups == ()
    assert result.receipt["occurrence_count"] == 0
    assert result.receipt["candidate_count"] == 0
    receipt_path = tmp_path / variants.IMAGE_VARIANT_RECEIPT_FILENAME
    receipt_path.write_text(json.dumps(result.to_dict()), encoding="utf-8")
    loaded = variants.load_image_variant_resolution(
        receipt_path,
        artifact_root=tmp_path,
        expected_report_sha256=report_sha256,
        expected_inventory_sha256=inventory_sha256,
    )
    assert loaded.to_dict() == result.to_dict()
    assert variants.validated_primary_paths(loaded, artifact_root=tmp_path) == {}
    assert variants.validated_mandatory_secondary_paths(loaded, artifact_root=tmp_path) == {}


def test_declared_page_and_annotation_context_can_never_be_primary(tmp_path: Path) -> None:
    source = _scene((480, 360))
    embedded = _save(
        source.resize((80, 60), Image.Resampling.LANCZOS),
        tmp_path / "embedded.jpg",
        quality=84,
    )
    linked = _save(
        source.resize((240, 180), Image.Resampling.LANCZOS),
        tmp_path / "linked.png",
        image_format="PNG",
    )
    page_context = _save(source, tmp_path / "page-context.png", image_format="PNG")
    annotation_context = _save(
        source,
        tmp_path / "annotation-context.bmp",
        image_format="BMP",
    )

    result = _resolve(
        tmp_path,
        [_occurrence("occ-1", "P001-I01", 1, embedded)],
        [
            _candidate("linked", "occ-1", linked),
            _candidate(
                "page-context",
                "occ-1",
                page_context,
                provenance="PDF_PAGE_CONTEXT",
            ),
            _candidate(
                "annotation-context",
                "occ-1",
                annotation_context,
                context_tags=("ANNOTATIONS_AND_CROP_CONTEXT",),
            ),
        ],
    )

    assert result.groups[0]["primary_candidate_id"] == "linked"
    assert result.groups[0]["status"] == variants.RESOLVED
    for candidate_id in (
        "page-context",
        "annotation-context",
        "embedded:occ-1",
    ):
        row = _row(result, candidate_id)
        assert row["role"] == variants.MANDATORY_SECONDARY
        assert candidate_id in variants.validated_mandatory_secondary_paths(
            result, artifact_root=tmp_path
        )
    assert _row(result, "page-context")["relationship_to_primary"] != variants.AMBIGUOUS
    assert _row(result, "annotation-context")["relationship_to_primary"] != variants.AMBIGUOUS


def test_occurrence_clustering_requires_complete_link_pairwise_agreement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = []
    for index in range(3):
        paths.append(
            _save(
                _scene((128, 96), phase=index * 7),
                tmp_path / f"image-{index}.png",
                image_format="PNG",
            )
        )
    occurrences = [
        _occurrence(f"occ-{name}", f"P00{index + 1}-I01", index + 1, paths[index])
        for index, name in enumerate(("a", "b", "c"))
    ]
    candidates = [
        _candidate(f"copy-{name}", f"occ-{name}", paths[index])
        for index, name in enumerate(("a", "b", "c"))
    ]
    original = variants._classify_full_frame_pair

    def controlled_pair(left, right, policy):
        embedded_pair = left.automatic_embedded and right.automatic_embedded
        occurrence_pair = frozenset((left.occurrence_id, right.occurrence_id))
        if embedded_pair and occurrence_pair in {
            frozenset(("occ-a", "occ-b")),
            frozenset(("occ-a", "occ-c")),
        }:
            return variants._PairEvidence(
                variants.FULL_FRAME_EQUIVALENT,
                ("CONTROLLED_DIRECT_MATCH",),
                0,
                0.0,
                1.0,
                1.0,
                0.0,
                1.0,
            )
        if embedded_pair and occurrence_pair == frozenset(("occ-b", "occ-c")):
            return variants._PairEvidence(
                variants.AMBIGUOUS,
                ("CONTROLLED_PAIRWISE_FAILURE",),
                64,
                1.0,
                0.0,
                0.0,
                1.0,
                0.0,
            )
        return original(left, right, policy)

    monkeypatch.setattr(variants, "_classify_full_frame_pair", controlled_pair)
    result = _resolve(tmp_path, occurrences, candidates)

    member_sets = {
        frozenset(item["occurrence_id"] for item in group["member_occurrences"])
        for group in result.groups
    }
    assert len(result.groups) == 2
    assert sorted(len(members) for members in member_sets) == [1, 2]
    assert frozenset(("occ-a", "occ-b", "occ-c")) not in member_sets
    assert not any({"occ-b", "occ-c"}.issubset(members) for members in member_sets)


def test_actual_scale_asset_count_has_bounded_crop_searches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    occurrences: list[variants.ImageOccurrence] = []
    candidates: list[variants.ImageCandidate] = []
    inventory_photos: list[dict[str, object]] = []
    for index in range(41):
        occurrence_id = f"occ-{index:03d}"
        photo_id = f"P{index + 1:03d}-I01"
        source = _scene((72, 96), phase=index + 1)
        linked: Path | None = None
        if index < 31:
            linked = _save(
                source,
                tmp_path / f"linked-{index:03d}.jpg",
                quality=94,
            )
            with Image.open(linked) as decoded:
                embedded_image = ImageOps.fit(
                    decoded.convert("RGB"),
                    (48, 48),
                    Image.Resampling.LANCZOS,
                )
        else:
            embedded_image = ImageOps.fit(source, (48, 48), Image.Resampling.LANCZOS)
        embedded = _save(
            embedded_image,
            tmp_path / f"embedded-{index:03d}.png",
            image_format="PNG",
        )
        occurrences.append(
            _occurrence(
                occurrence_id,
                photo_id,
                index + 1,
                embedded,
                xref=100 + index,
            )
        )
        candidates.append(
            _candidate(
                f"page-context-{index:03d}",
                occurrence_id,
                embedded,
                provenance="PDF_PAGE_CONTEXT",
                context_tags=("DISPLAYED_OCCURRENCE", "ANNOTATIONS_AND_CROP_CONTEXT"),
            )
        )
        if linked is not None:
            candidates.append(
                _candidate(
                    f"linked-{index:03d}",
                    occurrence_id,
                    linked,
                    provenance="REPORT_LINKED_ORIGINAL",
                    context_tags=("VERIFIED_THUMBNAIL_BINDING",),
                )
            )
            inventory_photos.append(
                {
                    "photo_id": photo_id,
                    "page_number": index + 1,
                    "full_resolution_status": "VERIFIED",
                    "full_resolution_path": linked.relative_to(tmp_path).as_posix(),
                    "full_resolution_sha256": _sha256(linked),
                    "full_resolution_width": 72,
                    "full_resolution_height": 96,
                }
            )

    crop_calls = 0
    original = variants._best_crop_match

    def counted_crop(*args, **kwargs):
        nonlocal crop_calls
        crop_calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(variants, "_best_crop_match", counted_crop)
    report = tmp_path / "active-report.pdf"
    report.write_bytes(b"%PDF-1.7\nactual-scale variant test\n%%EOF")
    inventory = tmp_path / "16b-photo-inventory-linked.json"
    inventory.write_text(
        json.dumps(
            {
                "schema": "CLASSIFIRE-LINKED-PHOTO-INVENTORY-v1",
                "report_sha256": _sha256(report),
                "photos": inventory_photos,
            }
        ),
        encoding="utf-8",
    )
    result = variants.resolve_image_variants(
        report_path=report,
        linked_inventory_path=inventory,
        occurrences=occurrences,
        candidates=candidates,
        artifact_root=tmp_path,
        expected_report_sha256=_sha256(report),
        expected_inventory_sha256=_sha256(inventory),
    )

    assert result.receipt["candidate_count"] == 113
    assert result.receipt["occurrence_count"] == 41
    assert crop_calls <= 70
