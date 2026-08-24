from __future__ import annotations

import hashlib
import json
import math
import re
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageOps, ImageStat, UnidentifiedImageError, __version__

from classifire.services.linked_image_retrieval import (
    DEFAULT_LINKED_IMAGE_POLICY,
    LinkedImageError,
    ThumbnailBindingEvidence,
    confirm_image_binding,
)

IMAGE_VARIANT_RECEIPT_SCHEMA = "CLASSIFIRE-IMAGE-VARIANT-RESOLUTION-v1"
IMAGE_VARIANT_RECEIPT_FILENAME = "16c-image-variant-resolution.json"
IMAGE_VARIANT_POLICY_VERSION = "CLASSIFIRE-IMAGE-VARIANT-POLICY-v1"

PRIMARY = "PRIMARY"
EQUIVALENT = "EQUIVALENT"
MANDATORY_SECONDARY = "MANDATORY_SECONDARY"

SELF = "SELF"
EXACT_BYTES = "EXACT_BYTES"
EXACT_DECODED_PIXELS = "EXACT_DECODED_PIXELS"
FULL_FRAME_EQUIVALENT = "FULL_FRAME_EQUIVALENT"
CROP_VARIANT = "CROP_VARIANT"
ANNOTATED_VARIANT = "ANNOTATED_VARIANT"
CONTRAST_VARIANT = "CONTRAST_VARIANT"
SIMILAR_DISTINCT = "SIMILAR_DISTINCT"
AMBIGUOUS = "AMBIGUOUS"

RESOLVED = "RESOLVED"
AMBIGUOUS_STATUS = "AMBIGUOUS"

_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_URI_MARKER = re.compile(r"(?i)(?:https?://|[?&](?:signature|token|expires|credential)=)")
_FORCED_SECONDARY_CONTEXT = frozenset({"PDF_PAGE_CONTEXT", "ANNOTATIONS_AND_CROP_CONTEXT"})


class ImageVariantResolutionError(RuntimeError):
    """A stable, deliberately sanitized image-variant failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Image variant resolution failed: {code}")


@dataclass(frozen=True)
class ImageOccurrence:
    occurrence_id: str
    photo_id: str
    page_number: int
    xref: int | None
    bbox: tuple[float, float, float, float] | None
    embedded_path: Path


@dataclass(frozen=True)
class ImageCandidate:
    candidate_id: str
    occurrence_id: str
    path: Path
    provenance: str
    context_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ImageVariantPolicy:
    version: str = IMAGE_VARIANT_POLICY_VERSION
    maximum_occurrences: int = 1_000
    maximum_candidates: int = 4_000
    maximum_file_bytes: int = 50 * 1024 * 1024
    maximum_pixels: int = 50_000_000
    maximum_side_px: int = 12_000
    # Forty-eight pixels keeps every comparison at or below the 50 px native
    # thumbnails used by the report. Comparing above the smaller representation's
    # native sampling grid would manufacture interpolation differences.
    comparison_size: int = 48
    detail_preview_max_side: int = 512
    maximum_full_frame_aspect_error: float = 0.01
    maximum_full_frame_hash_distance: int = 6
    maximum_full_frame_mean_error: float = 0.10
    minimum_full_frame_correlation: float = 0.985
    minimum_full_frame_edge_correlation: float = 0.90
    maximum_full_frame_luma_mean_delta: float = 0.03
    maximum_full_frame_luma_stddev_ratio_error: float = 0.10
    minimum_full_frame_luma_stddev: float = 0.06
    minimum_full_frame_entropy_bits: float = 3.5
    minimum_full_frame_mean_gradient: float = 0.005
    full_frame_tile_grid: int = 4
    maximum_full_frame_spatial_side_px: int = 256
    maximum_full_frame_tile_mean_error: float = 0.12
    minimum_full_frame_matching_tile_ratio: float = 0.75
    maximum_full_frame_worst_tile_mean_error: float = 0.14
    maximum_full_frame_tile_error_concentration_ratio: float = 3.0
    maximum_full_frame_tile_error_additive_floor: float = 0.025
    full_frame_localized_tile_grid: int = 8
    full_frame_localized_pixel_error_threshold: int = 60
    maximum_full_frame_localized_changed_fraction: float = 0.01
    maximum_full_frame_localized_concentration_ratio: float = 3.0
    crop_scales: tuple[float, ...] = (
        1.0,
        0.9,
        0.875,
        0.833333,
        0.8,
        0.75,
        0.666667,
        0.625,
        0.6,
        0.5,
    )
    crop_offsets: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)
    maximum_crop_hash_distance: int = 10
    maximum_crop_mean_error: float = 0.10
    minimum_crop_correlation: float = 0.975
    maximum_crop_retained_area_ratio: float = 0.95
    minimum_annotation_correlation: float = 0.92
    minimum_annotation_edge_correlation: float = 0.80
    minimum_annotation_changed_fraction: float = 0.002
    maximum_annotation_changed_fraction: float = 0.20
    maximum_annotation_mean_error: float = 0.10
    minimum_contrast_correlation: float = 0.97
    minimum_contrast_edge_correlation: float = 0.88
    maximum_contrast_hash_distance: int = 10
    minimum_similar_correlation: float = 0.78
    minimum_similar_crop_correlation: float = 0.90
    minimum_upscale_area_ratio: float = 1.50
    maximum_upscale_reconstruction_error: float = 0.025
    maximum_upscale_detail_gain_ratio: float = 1.10


DEFAULT_IMAGE_VARIANT_POLICY = ImageVariantPolicy()


@dataclass(frozen=True)
class ImageVariantResolution:
    receipt: Mapping[str, Any]
    rows: tuple[Mapping[str, Any], ...]
    groups: tuple[Mapping[str, Any], ...]
    schema: str = IMAGE_VARIANT_RECEIPT_SCHEMA
    _validated_artifact_root: Path | None = field(default=None, repr=False, compare=False)
    _validated_paths: Mapping[str, Path] = field(default_factory=dict, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        # JSON round-tripping produces an isolated JSON-compatible copy and prevents
        # callers from mutating the frozen result through nested dictionaries.
        return json.loads(
            json.dumps(
                {
                    "schema": self.schema,
                    "receipt": self.receipt,
                    "rows": self.rows,
                    "groups": self.groups,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )


@dataclass(frozen=True)
class _Asset:
    candidate_id: str
    occurrence_id: str
    path: Path
    relative_path: str
    provenance: str
    context_tags: tuple[str, ...]
    file_sha256: str
    decoded_pixel_sha256: str
    width: int
    height: int
    mode: str
    detail_score: float
    comparison: Image.Image
    comparison_hash: int
    comparison_vector: tuple[float, ...]
    edge_vector: tuple[float, ...]
    luma_mean: float
    luma_stddev: float
    information_luma_stddev: float
    entropy_bits: float
    mean_gradient: float
    preview: Image.Image
    detail_preview: Image.Image
    automatic_embedded: bool

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def aspect(self) -> float:
        return self.width / self.height


@dataclass(frozen=True)
class _PairEvidence:
    relationship: str
    reason_codes: tuple[str, ...]
    hash_distance: int
    mean_error: float
    correlation: float
    edge_correlation: float
    changed_fraction: float
    crop_correlation: float
    crop_side: str | None = None
    matching_tiles: int = 0
    tile_count: int = 0
    worst_tile_mean_error: float = 1.0
    localized_global_changed_fraction: float = 1.0
    localized_worst_tile_changed_fraction: float = 1.0


def _trusted_binding_pair(evidence: ThumbnailBindingEvidence) -> _PairEvidence:
    """Translate the independently verified v2 thumbnail binding into v1 relations."""

    shared_reasons = (
        "BOUND_16B_REPORT_LINKED_ORIGINAL",
        "URI_FREE_BINDING_RECONFIRMED",
        f"LINKED_BINDING_TRANSFORM_{evidence.transform}",
        "NORMALIZED_CROP_BOX_RECORDED",
        "USABLE_DETAIL_GAIN_RECONFIRMED",
    )
    tile_ratio = evidence.matching_tiles / max(1, evidence.tile_count)
    approximate_correlation = max(0.0, min(1.0, 1.0 - evidence.mean_error))
    if evidence.transform == "FULL_FRAME_RESIZE":
        return _PairEvidence(
            FULL_FRAME_EQUIVALENT,
            shared_reasons,
            evidence.hash_distance,
            evidence.mean_error,
            approximate_correlation,
            tile_ratio,
            0.0,
            approximate_correlation,
            None,
            evidence.matching_tiles,
            evidence.tile_count,
            evidence.worst_tile_mean_error,
        )
    if evidence.transform == "CENTER_CROP_COVER":
        return _PairEvidence(
            CROP_VARIANT,
            (*shared_reasons, "RIGHT_IS_CROP", "CANDIDATE_CONTAINS_EMBEDDED_FRAME"),
            evidence.hash_distance,
            evidence.mean_error,
            approximate_correlation,
            tile_ratio,
            0.0,
            approximate_correlation,
            "RIGHT",
            evidence.matching_tiles,
            evidence.tile_count,
            evidence.worst_tile_mean_error,
        )
    raise ImageVariantResolutionError("UNSUPPORTED_LINKED_BINDING_TRANSFORM")


def _trusted_binding_receipt(evidence: ThumbnailBindingEvidence) -> dict[str, Any]:
    def rounded(value: float | None) -> float | None:
        return None if value is None else round(float(value), 10)

    return {
        "source": "LINKED_IMAGE_RETRIEVAL_CONFIRM_IMAGE_BINDING",
        "policy_version": DEFAULT_LINKED_IMAGE_POLICY.version,
        "transform": evidence.transform,
        "normalized_crop_box": [round(float(value), 10) for value in evidence.crop_box],
        "hash_distance": evidence.hash_distance,
        "mean_error": rounded(evidence.mean_error),
        "matching_tiles": evidence.matching_tiles,
        "tile_count": evidence.tile_count,
        "worst_tile_mean_error": rounded(evidence.worst_tile_mean_error),
        "comparison_group_count": evidence.comparison_group_count,
        "usable_detail_gradient_gain_ratio": rounded(evidence.usable_detail_gradient_gain_ratio),
        "usable_detail_residual": rounded(evidence.usable_detail_residual),
        "usable_detail_matching_tiles": evidence.usable_detail_matching_tiles,
    }


def _reverse_pair_evidence(evidence: _PairEvidence) -> _PairEvidence:
    crop_side = evidence.crop_side
    if crop_side == "LEFT":
        crop_side = "RIGHT"
    elif crop_side == "RIGHT":
        crop_side = "LEFT"
    reasons = tuple(
        "LEFT_IS_CROP"
        if reason == "RIGHT_IS_CROP"
        else "RIGHT_IS_CROP"
        if reason == "LEFT_IS_CROP"
        else reason
        for reason in evidence.reason_codes
    )
    return _PairEvidence(
        evidence.relationship,
        reasons,
        evidence.hash_distance,
        evidence.mean_error,
        evidence.correlation,
        evidence.edge_correlation,
        evidence.changed_fraction,
        evidence.crop_correlation,
        crop_side,
        evidence.matching_tiles,
        evidence.tile_count,
        evidence.worst_tile_mean_error,
        evidence.localized_global_changed_fraction,
        evidence.localized_worst_tile_changed_fraction,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_token(value: str, code: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value) or _URI_MARKER.search(value):
        raise ImageVariantResolutionError(code)
    return value


def _safe_bbox(value: tuple[float, float, float, float] | None) -> list[float] | None:
    if value is None:
        return None
    if len(value) != 4 or any(not math.isfinite(float(item)) for item in value):
        raise ImageVariantResolutionError("INVALID_OCCURRENCE_BBOX")
    x0, y0, x1, y1 = (float(item) for item in value)
    if x1 <= x0 or y1 <= y0:
        raise ImageVariantResolutionError("INVALID_OCCURRENCE_BBOX")
    return [round(x0, 6), round(y0, 6), round(x1, 6), round(y1, 6)]


def _inside_root(path: Path, root: Path, code: str) -> tuple[Path, str]:
    try:
        resolved = path.resolve(strict=True)
        relative = resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        raise ImageVariantResolutionError(code) from None
    if not resolved.is_file():
        raise ImageVariantResolutionError(code)
    relative_text = relative.as_posix()
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ImageVariantResolutionError(code)
    return resolved, relative_text


def _read_linked_inventory(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ImageVariantResolutionError("INVENTORY_JSON_INVALID") from None
    if not isinstance(value, dict):
        raise ImageVariantResolutionError("INVENTORY_JSON_INVALID")
    return value


def _inventory_confirms_linked_asset(
    inventory: Mapping[str, Any],
    *,
    photo_id: str,
    page_number: int,
    relative_path: str,
    file_sha256: str,
    width: int,
    height: int,
) -> bool:
    photos = inventory.get("photos")
    if not isinstance(photos, list):
        return False
    matches = [row for row in photos if isinstance(row, dict) and row.get("photo_id") == photo_id]
    if len(matches) != 1:
        return False
    row = matches[0]
    raw_path = row.get("full_resolution_path")
    if not isinstance(raw_path, str) or _URI_MARKER.search(raw_path):
        return False
    inventory_path = Path(raw_path)
    if inventory_path.is_absolute() or ".." in inventory_path.parts:
        return False
    try:
        inventory_width = int(row.get("full_resolution_width"))
        inventory_height = int(row.get("full_resolution_height"))
        inventory_page_number = int(row.get("page_number"))
    except (TypeError, ValueError):
        return False
    return bool(
        str(row.get("full_resolution_status") or "").upper() in {"VERIFIED", "CACHED"}
        and inventory_path.as_posix() == relative_path
        and row.get("full_resolution_sha256") == file_sha256
        and (inventory_width, inventory_height) == (width, height)
        and inventory_page_number == page_number
    )


def _difference_hash(image: Image.Image) -> int:
    resized = ImageOps.grayscale(image).resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(resized.getdata())
    value = 0
    for row in range(8):
        for column in range(8):
            value <<= 1
            if pixels[row * 9 + column] > pixels[row * 9 + column + 1]:
                value |= 1
    return value


def _normalized_vector(image: Image.Image) -> tuple[float, ...]:
    values = [float(value) for value in ImageOps.grayscale(image).getdata()]
    mean = sum(values) / len(values)
    centered = [value - mean for value in values]
    norm = math.sqrt(sum(value * value for value in centered))
    if norm <= 1e-12:
        return tuple(0.0 for _ in centered)
    return tuple(value / norm for value in centered)


def _correlation(left: Image.Image, right: Image.Image) -> float:
    if left.size != right.size:
        right = right.resize(left.size, Image.Resampling.LANCZOS)
    left_vector = _normalized_vector(left)
    right_vector = _normalized_vector(right)
    if not any(left_vector) or not any(right_vector):
        return 1.0 if ImageChops.difference(left, right).getbbox() is None else 0.0
    return max(
        -1.0,
        min(1.0, sum(a * b for a, b in zip(left_vector, right_vector, strict=True))),
    )


def _vector_correlation(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if not any(left) or not any(right):
        return 1.0 if left == right else 0.0
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right, strict=True))))


def _edge_image(image: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(image)
    width, height = gray.size
    pixels = list(gray.getdata())
    edges: list[int] = []
    for y in range(height):
        for x in range(width):
            here = pixels[y * width + x]
            horizontal = abs(here - pixels[y * width + min(x + 1, width - 1)])
            vertical = abs(here - pixels[min(y + 1, height - 1) * width + x])
            edges.append(min(255, horizontal + vertical))
    result = Image.new("L", (width, height))
    result.putdata(edges)
    return result


def _mean_error(left: Image.Image, right: Image.Image) -> float:
    if left.size != right.size:
        right = right.resize(left.size, Image.Resampling.LANCZOS)
    means = ImageStat.Stat(ImageChops.difference(left.convert("RGB"), right.convert("RGB"))).mean
    return sum(means) / (len(means) * 255.0)


def _luma_stats(image: Image.Image) -> tuple[float, float]:
    statistics = ImageStat.Stat(ImageOps.grayscale(image))
    return statistics.mean[0] / 255.0, statistics.stddev[0] / 255.0


def _image_information(image: Image.Image) -> tuple[float, float, float]:
    grayscale = ImageOps.grayscale(image)
    luma_stddev = float(ImageStat.Stat(grayscale).stddev[0]) / 255.0
    entropy_bits = float(grayscale.entropy())
    if grayscale.width < 2 or grayscale.height < 2:
        return luma_stddev, entropy_bits, 0.0
    horizontal = ImageChops.difference(
        grayscale.crop((1, 0, grayscale.width, grayscale.height)),
        grayscale.crop((0, 0, grayscale.width - 1, grayscale.height)),
    )
    vertical = ImageChops.difference(
        grayscale.crop((0, 1, grayscale.width, grayscale.height)),
        grayscale.crop((0, 0, grayscale.width, grayscale.height - 1)),
    )
    mean_gradient = (
        float(ImageStat.Stat(horizontal).mean[0]) + float(ImageStat.Stat(vertical).mean[0])
    ) / (2.0 * 255.0)
    return luma_stddev, entropy_bits, mean_gradient


def _changed_fraction(left: Image.Image, right: Image.Image, threshold: int = 20) -> float:
    if left.size != right.size:
        right = right.resize(left.size, Image.Resampling.LANCZOS)
    difference = ImageChops.difference(left.convert("RGB"), right.convert("RGB"))
    changed = sum(1 for pixel in difference.getdata() if max(pixel) > threshold)
    return changed / (left.width * left.height)


def _detail_score(image: Image.Image) -> float:
    gray = ImageOps.grayscale(image)
    width, height = gray.size
    values = list(gray.getdata())
    total = 0
    comparisons = 0
    for y in range(height):
        row = y * width
        for x in range(width):
            here = values[row + x]
            if x + 1 < width:
                total += abs(here - values[row + x + 1])
                comparisons += 1
            if y + 1 < height:
                total += abs(here - values[row + width + x])
                comparisons += 1
    return total / (max(1, comparisons) * 255.0)


def _limited_preview(image: Image.Image, maximum_side: int) -> Image.Image:
    result = image.copy()
    result.thumbnail((maximum_side, maximum_side), Image.Resampling.LANCZOS)
    return result


def _load_asset(
    *,
    candidate_id: str,
    occurrence_id: str,
    path: Path,
    provenance: str,
    context_tags: tuple[str, ...],
    automatic_embedded: bool,
    artifact_root: Path,
    policy: ImageVariantPolicy,
) -> _Asset:
    resolved, relative = _inside_root(path, artifact_root, "UNSAFE_CANDIDATE_PATH")
    try:
        size_bytes = resolved.stat().st_size
    except OSError:
        raise ImageVariantResolutionError("CANDIDATE_READ_FAILED") from None
    if size_bytes <= 0 or size_bytes > policy.maximum_file_bytes:
        raise ImageVariantResolutionError("CANDIDATE_FILE_SIZE_REJECTED")
    file_sha256 = _sha256_file(resolved)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(resolved) as probe:
                width, height = probe.size
                if (
                    width <= 0
                    or height <= 0
                    or max(width, height) > policy.maximum_side_px
                    or width * height > policy.maximum_pixels
                ):
                    raise ImageVariantResolutionError("CANDIDATE_DIMENSIONS_REJECTED")
                probe.verify()
            with Image.open(resolved) as decoded:
                decoded.load()
                image = ImageOps.exif_transpose(decoded).convert("RGB")
    except ImageVariantResolutionError:
        raise
    except (
        OSError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise ImageVariantResolutionError("CANDIDATE_DECODE_FAILED") from None
    width, height = image.size
    pixel_digest = hashlib.sha256()
    pixel_digest.update(f"RGB:{width}:{height}:".encode("ascii"))
    pixel_digest.update(image.tobytes())
    comparison = image.resize(
        (policy.comparison_size, policy.comparison_size), Image.Resampling.LANCZOS
    )
    comparison_hash = _difference_hash(comparison)
    comparison_vector = _normalized_vector(comparison)
    edge_vector = _normalized_vector(_edge_image(comparison))
    luma_mean, luma_stddev = _luma_stats(comparison)
    preview = _limited_preview(image, policy.comparison_size * 2)
    detail_preview = _limited_preview(image, policy.detail_preview_max_side)
    information_preview = _limited_preview(image, policy.maximum_full_frame_spatial_side_px)
    information_luma_stddev, entropy_bits, mean_gradient = _image_information(information_preview)
    return _Asset(
        candidate_id=candidate_id,
        occurrence_id=occurrence_id,
        path=resolved,
        relative_path=relative,
        provenance=provenance,
        context_tags=context_tags,
        file_sha256=file_sha256,
        decoded_pixel_sha256=pixel_digest.hexdigest(),
        width=width,
        height=height,
        mode="RGB",
        detail_score=_detail_score(detail_preview),
        comparison=comparison,
        comparison_hash=comparison_hash,
        comparison_vector=comparison_vector,
        edge_vector=edge_vector,
        luma_mean=luma_mean,
        luma_stddev=luma_stddev,
        information_luma_stddev=information_luma_stddev,
        entropy_bits=entropy_bits,
        mean_gradient=mean_gradient,
        preview=preview,
        detail_preview=detail_preview,
        automatic_embedded=automatic_embedded,
    )


def _direct_metrics(left: _Asset, right: _Asset) -> tuple[int, float, float, float, float]:
    hash_distance = (left.comparison_hash ^ right.comparison_hash).bit_count()
    mean_error = _mean_error(left.comparison, right.comparison)
    correlation = _vector_correlation(left.comparison_vector, right.comparison_vector)
    edge_correlation = _vector_correlation(left.edge_vector, right.edge_vector)
    changed_fraction = _changed_fraction(left.comparison, right.comparison)
    return hash_distance, mean_error, correlation, edge_correlation, changed_fraction


def _best_crop_match(
    possible_crop: _Asset,
    possible_container: _Asset,
    policy: ImageVariantPolicy,
) -> tuple[int, float, float, float]:
    target = possible_crop.comparison
    target_hash = possible_crop.comparison_hash
    container_area = possible_container.preview.width * possible_container.preview.height
    width, height = possible_container.preview.size
    container_aspect = width / height
    if container_aspect >= possible_crop.aspect:
        maximum_height = float(height)
        maximum_width = maximum_height * possible_crop.aspect
    else:
        maximum_width = float(width)
        maximum_height = maximum_width / possible_crop.aspect
    geometric_best = (65, 1.0, -1.0, 1.0)
    seen: set[tuple[int, int, int, int]] = set()
    for scale in policy.crop_scales:
        crop_width = max(2, min(width, round(maximum_width * scale)))
        crop_height = max(2, min(height, round(maximum_height * scale)))
        available_x = width - crop_width
        available_y = height - crop_height
        for x_fraction in policy.crop_offsets:
            for y_fraction in policy.crop_offsets:
                x0 = round(available_x * x_fraction)
                y0 = round(available_y * y_fraction)
                box = (x0, y0, x0 + crop_width, y0 + crop_height)
                if box in seen:
                    continue
                seen.add(box)
                raw_crop = possible_container.preview.crop(box)
                distance = (target_hash ^ _difference_hash(raw_crop)).bit_count()
                if distance > policy.maximum_crop_hash_distance:
                    continue
                crop = raw_crop.resize(
                    (policy.comparison_size, policy.comparison_size), Image.Resampling.LANCZOS
                )
                error = _mean_error(target, crop)
                correlation = _correlation(target, crop)
                retained = (crop_width * crop_height) / container_area
                candidate = (distance, error, correlation, retained)
                if (correlation, -error, -distance) > (
                    geometric_best[2],
                    -geometric_best[1],
                    -geometric_best[0],
                ):
                    geometric_best = candidate
    return geometric_best


def _full_frame_comparison_images(
    left: _Asset,
    right: _Asset,
    policy: ImageVariantPolicy,
) -> tuple[Image.Image, Image.Image]:
    reference = min((left, right), key=lambda asset: (asset.area, asset.candidate_id))
    maximum_side = min(
        policy.maximum_full_frame_spatial_side_px,
        max(reference.width, reference.height),
    )
    scale = maximum_side / max(reference.width, reference.height)
    target_size = (
        max(1, round(reference.width * scale)),
        max(1, round(reference.height * scale)),
    )
    return (
        left.detail_preview.resize(target_size, Image.Resampling.LANCZOS),
        right.detail_preview.resize(target_size, Image.Resampling.LANCZOS),
    )


def _spatial_tile_metrics(
    left: _Asset,
    right: _Asset,
    policy: ImageVariantPolicy,
    comparison_images: tuple[Image.Image, Image.Image] | None = None,
) -> tuple[int, int, float]:
    grid = policy.full_frame_tile_grid
    left_image, right_image = comparison_images or _full_frame_comparison_images(
        left, right, policy
    )
    target_size = left_image.size
    if grid <= 0 or min(target_size) < grid:
        return 0, max(1, grid * grid), 1.0
    difference = ImageChops.difference(left_image.convert("RGB"), right_image.convert("RGB"))
    tile_errors: list[float] = []
    for row in range(grid):
        for column in range(grid):
            box = (
                round(column * target_size[0] / grid),
                round(row * target_size[1] / grid),
                round((column + 1) * target_size[0] / grid),
                round((row + 1) * target_size[1] / grid),
            )
            means = ImageStat.Stat(difference.crop(box)).mean
            tile_errors.append(sum(means) / (len(means) * 255.0))
    return (
        sum(error <= policy.maximum_full_frame_tile_mean_error for error in tile_errors),
        len(tile_errors),
        max(tile_errors),
    )


def _localized_change_metrics(
    left: _Asset,
    right: _Asset,
    policy: ImageVariantPolicy,
    comparison_images: tuple[Image.Image, Image.Image] | None = None,
) -> tuple[float, float]:
    grid = policy.full_frame_localized_tile_grid
    left_image, right_image = comparison_images or _full_frame_comparison_images(
        left, right, policy
    )
    width, height = left_image.size
    if grid <= 0 or min(width, height) < grid:
        return 1.0, 1.0
    difference = ImageChops.difference(left_image.convert("RGB"), right_image.convert("RGB"))
    red, green, blue = difference.split()
    maximum_difference = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    threshold = policy.full_frame_localized_pixel_error_threshold
    changed_mask = maximum_difference.point(
        [0 if value <= threshold else 255 for value in range(256)]
    )
    global_fraction = float(ImageStat.Stat(changed_mask).mean[0]) / 255.0
    tile_fractions: list[float] = []
    for row in range(grid):
        for column in range(grid):
            x0 = round(column * width / grid)
            y0 = round(row * height / grid)
            x1 = round((column + 1) * width / grid)
            y1 = round((row + 1) * height / grid)
            tile = changed_mask.crop((x0, y0, x1, y1))
            tile_fractions.append(float(ImageStat.Stat(tile).mean[0]) / 255.0)
    return global_fraction, max(tile_fractions)


def _classify_full_frame_pair(
    left: _Asset,
    right: _Asset,
    policy: ImageVariantPolicy,
) -> _PairEvidence:
    if left.file_sha256 == right.file_sha256:
        return _PairEvidence(EXACT_BYTES, ("FILE_SHA256_MATCH",), 0, 0.0, 1.0, 1.0, 0.0, 1.0)
    if left.decoded_pixel_sha256 == right.decoded_pixel_sha256:
        return _PairEvidence(
            EXACT_DECODED_PIXELS,
            ("DECODED_PIXEL_SHA256_MATCH",),
            0,
            0.0,
            1.0,
            1.0,
            0.0,
            1.0,
        )
    distance, error, correlation, edge_correlation, changed = _direct_metrics(left, right)
    aspect_error = abs(left.aspect - right.aspect) / max(left.aspect, right.aspect)
    luma_mean_delta = abs(left.luma_mean - right.luma_mean)
    luma_stddev_ratio_error = abs(left.luma_stddev - right.luma_stddev) / max(
        left.luma_stddev, right.luma_stddev, 1e-12
    )
    comparison_images = _full_frame_comparison_images(left, right, policy)
    matching_tiles, tile_count, worst_tile_mean_error = _spatial_tile_metrics(
        left, right, policy, comparison_images
    )
    localized_global_fraction, localized_worst_tile_fraction = _localized_change_metrics(
        left, right, policy, comparison_images
    )
    localized_change_gate = bool(
        localized_worst_tile_fraction <= policy.maximum_full_frame_localized_changed_fraction
        or localized_worst_tile_fraction
        <= localized_global_fraction * policy.maximum_full_frame_localized_concentration_ratio
    )
    full_frame = (
        aspect_error <= policy.maximum_full_frame_aspect_error
        and distance <= policy.maximum_full_frame_hash_distance
        and error <= policy.maximum_full_frame_mean_error
        and correlation >= policy.minimum_full_frame_correlation
        and edge_correlation >= policy.minimum_full_frame_edge_correlation
        and luma_mean_delta <= policy.maximum_full_frame_luma_mean_delta
        and luma_stddev_ratio_error <= policy.maximum_full_frame_luma_stddev_ratio_error
        and min(left.information_luma_stddev, right.information_luma_stddev)
        >= policy.minimum_full_frame_luma_stddev
        and min(left.entropy_bits, right.entropy_bits) >= policy.minimum_full_frame_entropy_bits
        and min(left.mean_gradient, right.mean_gradient) >= policy.minimum_full_frame_mean_gradient
        and matching_tiles / tile_count >= policy.minimum_full_frame_matching_tile_ratio
        and worst_tile_mean_error <= policy.maximum_full_frame_worst_tile_mean_error
        and worst_tile_mean_error
        <= max(
            policy.maximum_full_frame_tile_error_additive_floor,
            error * policy.maximum_full_frame_tile_error_concentration_ratio,
        )
        and localized_change_gate
    )
    if full_frame:
        return _PairEvidence(
            FULL_FRAME_EQUIVALENT,
            (
                "ASPECT_GATE_PASS",
                "DHASH_GATE_PASS",
                "MEAN_ERROR_GATE_PASS",
                "CORRELATION_GATE_PASS",
                "EDGE_GATE_PASS",
                "LUMA_MEAN_GATE_PASS",
                "LUMA_STDDEV_GATE_PASS",
                "INFORMATION_LUMA_GATE_PASS",
                "INFORMATION_ENTROPY_GATE_PASS",
                "INFORMATION_GRADIENT_GATE_PASS",
                "SPATIAL_TILE_RATIO_GATE_PASS",
                "SPATIAL_WORST_TILE_GATE_PASS",
                "SPATIAL_CONCENTRATION_GATE_PASS",
                "LOCALIZED_CHANGE_GATE_PASS",
            ),
            distance,
            error,
            correlation,
            edge_correlation,
            changed,
            correlation,
            None,
            matching_tiles,
            tile_count,
            worst_tile_mean_error,
            localized_global_fraction,
            localized_worst_tile_fraction,
        )
    failed_reasons = ["FULL_FRAME_GATES_FAILED"]
    if not localized_change_gate:
        failed_reasons.append("LOCALIZED_CHANGE_GATE_FAILED")
    if (
        min(left.information_luma_stddev, right.information_luma_stddev)
        < policy.minimum_full_frame_luma_stddev
        or min(left.entropy_bits, right.entropy_bits) < policy.minimum_full_frame_entropy_bits
        or min(left.mean_gradient, right.mean_gradient) < policy.minimum_full_frame_mean_gradient
    ):
        failed_reasons.append("INFORMATION_FLOOR_FAILED")
    return _PairEvidence(
        AMBIGUOUS,
        tuple(failed_reasons),
        distance,
        error,
        correlation,
        edge_correlation,
        changed,
        -1.0,
        None,
        matching_tiles,
        tile_count,
        worst_tile_mean_error,
        localized_global_fraction,
        localized_worst_tile_fraction,
    )


def _classify_non_crop_pair(
    left: _Asset,
    right: _Asset,
    policy: ImageVariantPolicy,
) -> _PairEvidence:
    direct = _classify_full_frame_pair(left, right, policy)
    if direct.relationship != AMBIGUOUS:
        return direct
    distance = direct.hash_distance
    error = direct.mean_error
    correlation = direct.correlation
    edge_correlation = direct.edge_correlation
    changed = direct.changed_fraction
    aspect_error = abs(left.aspect - right.aspect) / max(left.aspect, right.aspect)
    annotation = (
        aspect_error <= policy.maximum_full_frame_aspect_error
        and correlation >= policy.minimum_annotation_correlation
        and edge_correlation >= policy.minimum_annotation_edge_correlation
        and policy.minimum_annotation_changed_fraction
        <= changed
        <= policy.maximum_annotation_changed_fraction
        and error <= policy.maximum_annotation_mean_error
    )
    if annotation:
        return _PairEvidence(
            ANNOTATED_VARIANT,
            ("LOCALIZED_CHANGE_DETECTED", "ANNOTATION_CORRELATION_GATE_PASS"),
            distance,
            error,
            correlation,
            edge_correlation,
            changed,
            -1.0,
        )
    contrast = (
        aspect_error <= policy.maximum_full_frame_aspect_error
        and distance <= policy.maximum_contrast_hash_distance
        and correlation >= policy.minimum_contrast_correlation
        and edge_correlation >= policy.minimum_contrast_edge_correlation
    )
    if contrast:
        return _PairEvidence(
            CONTRAST_VARIANT,
            ("GLOBAL_LUMA_CORRELATION_GATE_PASS", "FULL_FRAME_EQUIVALENCE_NOT_PROVEN"),
            distance,
            error,
            correlation,
            edge_correlation,
            changed,
            -1.0,
        )
    if correlation >= policy.minimum_similar_correlation:
        return _PairEvidence(
            SIMILAR_DISTINCT,
            ("PERCEPTUAL_SIMILARITY_ONLY", "EQUIVALENCE_GATES_FAILED"),
            distance,
            error,
            correlation,
            edge_correlation,
            changed,
            -1.0,
        )
    return _PairEvidence(
        AMBIGUOUS,
        ("NO_EQUIVALENCE_PROVEN",),
        distance,
        error,
        correlation,
        edge_correlation,
        changed,
        -1.0,
    )


def _classify_pair(
    left: _Asset,
    right: _Asset,
    policy: ImageVariantPolicy,
) -> _PairEvidence:
    direct = _classify_non_crop_pair(left, right, policy)
    if direct.relationship in {
        EXACT_BYTES,
        EXACT_DECODED_PIXELS,
        FULL_FRAME_EQUIVALENT,
        ANNOTATED_VARIANT,
        CONTRAST_VARIANT,
    }:
        return direct
    distance = direct.hash_distance
    error = direct.mean_error
    correlation = direct.correlation
    edge_correlation = direct.edge_correlation
    changed = direct.changed_fraction
    if left.area <= right.area:
        first_crop = _best_crop_match(left, right, policy)
        first_side = "LEFT"
        second_crop = (
            _best_crop_match(right, left, policy)
            if right.area / max(1, left.area) < 1.2
            else (65, 1.0, -1.0, 1.0)
        )
        second_side = "RIGHT"
    else:
        first_crop = _best_crop_match(right, left, policy)
        first_side = "RIGHT"
        second_crop = (
            _best_crop_match(left, right, policy)
            if left.area / max(1, right.area) < 1.2
            else (65, 1.0, -1.0, 1.0)
        )
        second_side = "LEFT"
    candidates = ((first_side, first_crop), (second_side, second_crop))
    passing_crops = [
        (side, crop)
        for side, crop in candidates
        if crop[0] <= policy.maximum_crop_hash_distance
        and crop[1] <= policy.maximum_crop_mean_error
        and crop[2] >= policy.minimum_crop_correlation
        and crop[3] <= policy.maximum_crop_retained_area_ratio
    ]
    if passing_crops:
        crop_side, chosen = max(
            passing_crops,
            key=lambda item: (item[1][2], -item[1][1], -item[1][0], item[0]),
        )
        return _PairEvidence(
            CROP_VARIANT,
            (
                f"{crop_side}_IS_CROP",
                "CROP_DHASH_GATE_PASS",
                "CROP_ERROR_GATE_PASS",
                "CROP_CORRELATION_GATE_PASS",
            ),
            distance,
            error,
            correlation,
            edge_correlation,
            changed,
            chosen[2],
            crop_side,
        )
    best_crop_correlation = max(first_crop[2], second_crop[2])
    if (
        direct.relationship == SIMILAR_DISTINCT
        or best_crop_correlation >= policy.minimum_similar_crop_correlation
    ):
        return _PairEvidence(
            SIMILAR_DISTINCT,
            ("PERCEPTUAL_SIMILARITY_ONLY", "EQUIVALENCE_GATES_FAILED"),
            distance,
            error,
            correlation,
            edge_correlation,
            changed,
            best_crop_correlation,
        )
    return _PairEvidence(
        AMBIGUOUS,
        ("NO_EQUIVALENCE_PROVEN",),
        distance,
        error,
        correlation,
        edge_correlation,
        changed,
        best_crop_correlation,
    )


def _likely_upscaled(
    larger: _Asset,
    smaller: _Asset,
    relationship: str,
    policy: ImageVariantPolicy,
) -> bool:
    if relationship not in {EXACT_BYTES, EXACT_DECODED_PIXELS, FULL_FRAME_EQUIVALENT}:
        return False
    if larger.area / smaller.area < policy.minimum_upscale_area_ratio:
        return False
    target = larger.detail_preview
    reconstructed = smaller.detail_preview.resize(target.size, Image.Resampling.BICUBIC)
    reconstruction_error = _mean_error(target, reconstructed)
    reconstructed_detail = _detail_score(reconstructed)
    detail_gain_ratio = larger.detail_score / max(reconstructed_detail, 1e-12)
    return (
        reconstruction_error <= policy.maximum_upscale_reconstruction_error
        and detail_gain_ratio <= policy.maximum_upscale_detail_gain_ratio
    )


def _policy_dict(policy: ImageVariantPolicy) -> dict[str, Any]:
    return json.loads(json.dumps(asdict(policy), sort_keys=True, separators=(",", ":")))


def _manifest_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    keys = (
        "candidate_id",
        "occurrence_id",
        "photo_id",
        "page_number",
        "xref",
        "bbox",
        "path",
        "provenance",
        "context_tags",
        "file_sha256",
        "decoded_pixel_sha256",
        "width",
        "height",
        "mode",
        "detail_score",
        "proven_detail_area",
        "likely_upscaled",
    )
    return [
        {key: row.get(key) for key in keys}
        for row in sorted(rows, key=lambda item: str(item["candidate_id"]))
    ]


def _resolution_manifest(
    rows: Sequence[Mapping[str, Any]], groups: Sequence[Mapping[str, Any]]
) -> str:
    return _sha256_json(
        {
            "rows": sorted(rows, key=lambda item: str(item["candidate_id"])),
            "groups": sorted(groups, key=lambda item: str(item["group_id"])),
        }
    )


def resolve_image_variants(
    *,
    report_path: Path,
    linked_inventory_path: Path,
    occurrences: Sequence[ImageOccurrence],
    candidates: Sequence[ImageCandidate],
    artifact_root: Path | None = None,
    expected_report_sha256: str | None = None,
    expected_inventory_sha256: str | None = None,
    policy: ImageVariantPolicy = DEFAULT_IMAGE_VARIANT_POLICY,
) -> ImageVariantResolution:
    """Resolve local image representations without network or PDF interpretation.

    Full-frame equivalence requires all independent gates. Occurrence clustering and
    final row classification are always direct-to-anchor/direct-to-primary; a match
    through an intermediate candidate is never used as proof.
    """

    if policy.version != IMAGE_VARIANT_POLICY_VERSION:
        raise ImageVariantResolutionError("UNSUPPORTED_POLICY_VERSION")
    if len(occurrences) > policy.maximum_occurrences:
        raise ImageVariantResolutionError("OCCURRENCE_COUNT_REJECTED")
    if len(candidates) > policy.maximum_candidates:
        raise ImageVariantResolutionError("CANDIDATE_COUNT_REJECTED")
    if not occurrences and candidates:
        raise ImageVariantResolutionError("CANDIDATES_WITHOUT_OCCURRENCES")
    if occurrences and not candidates:
        raise ImageVariantResolutionError("MISSING_OCCURRENCE_CANDIDATES")
    root = (artifact_root or linked_inventory_path.parent).resolve(strict=True)
    if not root.is_dir():
        raise ImageVariantResolutionError("INVALID_ARTIFACT_ROOT")
    report = report_path.resolve(strict=True)
    if not report.is_file():
        raise ImageVariantResolutionError("REPORT_NOT_FOUND")
    inventory, inventory_relative = _inside_root(
        linked_inventory_path, root, "UNSAFE_INVENTORY_PATH"
    )
    report_sha256 = _sha256_file(report)
    inventory_sha256 = _sha256_file(inventory)
    if expected_report_sha256 is not None and report_sha256 != expected_report_sha256.lower():
        raise ImageVariantResolutionError("REPORT_SHA256_MISMATCH")
    if (
        expected_inventory_sha256 is not None
        and inventory_sha256 != expected_inventory_sha256.lower()
    ):
        raise ImageVariantResolutionError("INVENTORY_SHA256_MISMATCH")
    inventory_payload = _read_linked_inventory(inventory)
    inventory_report_sha256 = inventory_payload.get("report_sha256")
    if inventory_report_sha256 is not None and inventory_report_sha256 != report_sha256:
        raise ImageVariantResolutionError("INVENTORY_REPORT_SHA256_MISMATCH")

    occurrence_by_id: dict[str, ImageOccurrence] = {}
    for occurrence in occurrences:
        occurrence_id = _safe_token(occurrence.occurrence_id, "INVALID_OCCURRENCE_ID")
        _safe_token(occurrence.photo_id, "INVALID_PHOTO_ID")
        if occurrence_id in occurrence_by_id:
            raise ImageVariantResolutionError("DUPLICATE_OCCURRENCE_ID")
        if occurrence.page_number < 1:
            raise ImageVariantResolutionError("INVALID_PAGE_NUMBER")
        if occurrence.xref is not None and occurrence.xref < 0:
            raise ImageVariantResolutionError("INVALID_XREF")
        _safe_bbox(occurrence.bbox)
        occurrence_by_id[occurrence_id] = occurrence

    candidates_by_occurrence: dict[str, list[ImageCandidate]] = {
        occurrence_id: [] for occurrence_id in occurrence_by_id
    }
    candidate_ids: set[str] = set()
    for candidate in candidates:
        candidate_id = _safe_token(candidate.candidate_id, "INVALID_CANDIDATE_ID")
        occurrence_id = _safe_token(candidate.occurrence_id, "INVALID_OCCURRENCE_ID")
        _safe_token(candidate.provenance, "INVALID_PROVENANCE")
        if candidate_id.startswith("embedded:") or candidate_id in candidate_ids:
            raise ImageVariantResolutionError("DUPLICATE_CANDIDATE_ID")
        if occurrence_id not in occurrence_by_id:
            raise ImageVariantResolutionError("UNKNOWN_CANDIDATE_OCCURRENCE")
        for tag in candidate.context_tags:
            _safe_token(tag, "INVALID_CONTEXT_TAG")
        candidate_ids.add(candidate_id)
        candidates_by_occurrence[occurrence_id].append(candidate)
    if any(not items for items in candidates_by_occurrence.values()):
        raise ImageVariantResolutionError("MISSING_OCCURRENCE_CANDIDATES")

    assets: dict[str, _Asset] = {}
    embedded_ids: dict[str, str] = {}
    for occurrence_id in sorted(occurrence_by_id):
        occurrence = occurrence_by_id[occurrence_id]
        embedded_id = f"embedded:{occurrence_id}"
        embedded_ids[occurrence_id] = embedded_id
        assets[embedded_id] = _load_asset(
            candidate_id=embedded_id,
            occurrence_id=occurrence_id,
            path=occurrence.embedded_path,
            provenance="PDF_EMBEDDED",
            context_tags=(),
            automatic_embedded=True,
            artifact_root=root,
            policy=policy,
        )
    for occurrence_id in sorted(candidates_by_occurrence):
        for candidate in sorted(
            candidates_by_occurrence[occurrence_id], key=lambda item: item.candidate_id
        ):
            assets[candidate.candidate_id] = _load_asset(
                candidate_id=candidate.candidate_id,
                occurrence_id=occurrence_id,
                path=candidate.path,
                provenance=candidate.provenance,
                context_tags=tuple(sorted(candidate.context_tags)),
                automatic_embedded=False,
                artifact_root=root,
                policy=policy,
            )

    trusted_binding_pairs: dict[str, _PairEvidence] = {}
    trusted_binding_receipts: dict[str, dict[str, Any]] = {}
    for occurrence_id in sorted(candidates_by_occurrence):
        occurrence = occurrence_by_id[occurrence_id]
        embedded = assets[embedded_ids[occurrence_id]]
        for candidate in sorted(
            candidates_by_occurrence[occurrence_id], key=lambda item: item.candidate_id
        ):
            asset = assets[candidate.candidate_id]
            binding_requested = "VERIFIED_THUMBNAIL_BINDING" in asset.context_tags
            if not binding_requested:
                continue
            if asset.provenance != "REPORT_LINKED_ORIGINAL":
                raise ImageVariantResolutionError("TRUSTED_LINKED_PROVENANCE_INVALID")
            if not _inventory_confirms_linked_asset(
                inventory_payload,
                photo_id=occurrence.photo_id,
                page_number=occurrence.page_number,
                relative_path=asset.relative_path,
                file_sha256=asset.file_sha256,
                width=asset.width,
                height=asset.height,
            ):
                raise ImageVariantResolutionError("TRUSTED_LINKED_INVENTORY_BINDING_FAILED")
            try:
                binding = confirm_image_binding(
                    embedded.path,
                    asset.path.read_bytes(),
                    require_usable_detail_gain=True,
                )
            except (OSError, LinkedImageError):
                raise ImageVariantResolutionError(
                    "TRUSTED_LINKED_BINDING_RECONFIRMATION_FAILED"
                ) from None
            trusted_binding_pairs[candidate.candidate_id] = _trusted_binding_pair(binding)
            trusted_binding_receipts[candidate.candidate_id] = _trusted_binding_receipt(binding)

    direct_pair_cache: dict[tuple[str, str], _PairEvidence] = {}
    context_pair_cache: dict[tuple[str, str], _PairEvidence] = {}
    non_crop_pair_cache: dict[tuple[str, str], _PairEvidence] = {}

    def self_evidence() -> _PairEvidence:
        return _PairEvidence(SELF, ("PRIMARY_SELF",), 0, 0.0, 1.0, 1.0, 0.0, 1.0)

    def classify_direct(left_id: str, right_id: str) -> _PairEvidence:
        if left_id == right_id:
            return self_evidence()
        key = (left_id, right_id)
        if key not in direct_pair_cache:
            direct_pair_cache[key] = _classify_full_frame_pair(
                assets[left_id], assets[right_id], policy
            )
        return direct_pair_cache[key]

    def classify_context(left_id: str, right_id: str) -> _PairEvidence:
        if left_id == right_id:
            return self_evidence()
        key = (left_id, right_id)
        if key not in context_pair_cache:
            context_pair_cache[key] = _classify_pair(assets[left_id], assets[right_id], policy)
        return context_pair_cache[key]

    def classify_non_crop(left_id: str, right_id: str) -> _PairEvidence:
        if left_id == right_id:
            return self_evidence()
        key = (left_id, right_id)
        if key not in non_crop_pair_cache:
            non_crop_pair_cache[key] = _classify_non_crop_pair(
                assets[left_id], assets[right_id], policy
            )
        return non_crop_pair_cache[key]

    upscale_sources: dict[str, list[str]] = {candidate_id: [] for candidate_id in assets}
    confirmed_upscale_pairs: set[frozenset[str]] = set()

    def record_confirmed_upscale(left_id: str, right_id: str, evidence: _PairEvidence) -> None:
        if evidence.relationship not in {
            EXACT_BYTES,
            EXACT_DECODED_PIXELS,
            FULL_FRAME_EQUIVALENT,
        }:
            return
        pair_key = frozenset((left_id, right_id))
        if pair_key in confirmed_upscale_pairs:
            return
        confirmed_upscale_pairs.add(pair_key)
        left = assets[left_id]
        right = assets[right_id]
        if left.area > right.area and _likely_upscaled(left, right, evidence.relationship, policy):
            upscale_sources[left_id].append(right_id)
        elif right.area > left.area and _likely_upscaled(
            right, left, evidence.relationship, policy
        ):
            upscale_sources[right_id].append(left_id)

    own_candidate_evidence: dict[str, _PairEvidence] = {}
    for occurrence_id in sorted(candidates_by_occurrence):
        embedded_id = embedded_ids[occurrence_id]
        for candidate in sorted(
            candidates_by_occurrence[occurrence_id], key=lambda item: item.candidate_id
        ):
            evidence = trusted_binding_pairs.get(candidate.candidate_id)
            if evidence is None:
                evidence = classify_context(candidate.candidate_id, embedded_id)
            asset = assets[candidate.candidate_id]
            declared_context = {asset.provenance, *asset.context_tags}
            if declared_context & _FORCED_SECONDARY_CONTEXT and evidence.relationship in {
                AMBIGUOUS,
                SIMILAR_DISTINCT,
            }:
                evidence = _PairEvidence(
                    ANNOTATED_VARIANT,
                    (
                        "TRUSTED_PDF_CONTEXT_DERIVATION",
                        "PIXEL_EQUIVALENCE_NOT_CLAIMED",
                        "MANDATORY_SECONDARY_NON_SUBSTITUTING",
                    ),
                    evidence.hash_distance,
                    evidence.mean_error,
                    evidence.correlation,
                    evidence.edge_correlation,
                    evidence.changed_fraction,
                    evidence.crop_correlation,
                    evidence.crop_side,
                    evidence.matching_tiles,
                    evidence.tile_count,
                    evidence.worst_tile_mean_error,
                    evidence.localized_global_changed_fraction,
                    evidence.localized_worst_tile_changed_fraction,
                )
            own_candidate_evidence[candidate.candidate_id] = evidence
            record_confirmed_upscale(candidate.candidate_id, embedded_id, evidence)

    sorted_occurrence_ids = sorted(occurrence_by_id)
    for index, left_occurrence_id in enumerate(sorted_occurrence_ids):
        for right_occurrence_id in sorted_occurrence_ids[index + 1 :]:
            left_id = embedded_ids[left_occurrence_id]
            right_id = embedded_ids[right_occurrence_id]
            evidence = classify_direct(left_id, right_id)
            record_confirmed_upscale(left_id, right_id, evidence)

    proven_area: dict[str, int] = {}
    for candidate_id, asset in assets.items():
        sources = upscale_sources[candidate_id]
        proven_area[candidate_id] = (
            min(assets[source].area for source in sources) if sources else asset.area
        )

    def rank(candidate_id: str) -> tuple[int, float, int, str]:
        asset = assets[candidate_id]
        # The final negative lexical component is deliberately not attempted here;
        # callers use an explicit candidate-id tie break after reverse numeric sort.
        return (proven_area[candidate_id], asset.detail_score, asset.area, candidate_id)

    def forced_secondary(candidate_id: str, primary_id: str | None = None) -> bool:
        asset = assets[candidate_id]
        declared_context = {asset.provenance, *asset.context_tags}
        if declared_context & _FORCED_SECONDARY_CONTEXT:
            return True
        return bool(
            primary_id is not None
            and asset.automatic_embedded
            and not assets[primary_id].automatic_embedded
        )

    # Cluster PDF occurrences only by direct cryptographic/full-frame evidence to a
    # single anchor. This deliberately avoids connected-component transitive closure.
    remaining = set(occurrence_by_id)
    occurrence_clusters: list[list[str]] = []
    anchor_order = sorted(
        remaining,
        key=lambda item: (
            -rank(embedded_ids[item])[0],
            -rank(embedded_ids[item])[1],
            -rank(embedded_ids[item])[2],
            item,
        ),
    )
    for anchor_occurrence_id in anchor_order:
        if anchor_occurrence_id not in remaining:
            continue
        cluster = [anchor_occurrence_id]
        remaining.remove(anchor_occurrence_id)
        for other_occurrence_id in sorted(remaining):
            other_id = embedded_ids[other_occurrence_id]
            direct_relationships = [
                classify_direct(other_id, embedded_ids[member]).relationship for member in cluster
            ]
            if all(
                relationship in {EXACT_BYTES, EXACT_DECODED_PIXELS, FULL_FRAME_EQUIVALENT}
                for relationship in direct_relationships
            ):
                cluster.append(other_occurrence_id)
        for member in cluster[1:]:
            remaining.remove(member)
        occurrence_clusters.append(sorted(cluster))

    built_groups: list[dict[str, Any]] = []
    row_state: dict[str, dict[str, Any]] = {}
    group_primary_assets: dict[str, str] = {}

    for cluster in sorted(occurrence_clusters, key=lambda item: tuple(item)):
        pool_ids: list[str] = []
        eligible_ids: list[str] = []
        for occurrence_id in cluster:
            embedded_id = embedded_ids[occurrence_id]
            pool_ids.append(embedded_id)
            eligible_ids.append(embedded_id)
            for candidate in sorted(
                candidates_by_occurrence[occurrence_id], key=lambda item: item.candidate_id
            ):
                pool_ids.append(candidate.candidate_id)
                if forced_secondary(candidate.candidate_id):
                    continue
                evidence = own_candidate_evidence[candidate.candidate_id]
                if evidence.relationship in {
                    EXACT_BYTES,
                    EXACT_DECODED_PIXELS,
                    FULL_FRAME_EQUIVALENT,
                } or (
                    candidate.candidate_id in trusted_binding_pairs
                    and evidence.relationship == CROP_VARIANT
                    and evidence.crop_side == "RIGHT"
                ):
                    eligible_ids.append(candidate.candidate_id)
        primary_id = sorted(
            set(eligible_ids),
            key=lambda item: (
                -rank(item)[0],
                -rank(item)[1],
                -rank(item)[2],
                int(assets[item].automatic_embedded),
                item,
            ),
        )[0]
        group_seed = "\x00".join(cluster).encode("utf-8")
        group_id = "IVG-" + hashlib.sha256(group_seed).hexdigest()[:16]
        group_primary_assets[group_id] = primary_id
        secondary: list[dict[str, Any]] = []
        ambiguity_ids: list[str] = []
        equivalent_ids: list[str] = []
        for candidate_id in sorted(set(pool_ids)):
            asset = assets[candidate_id]
            occurrence = occurrence_by_id[asset.occurrence_id]
            if (
                asset.automatic_embedded
                and primary_id in trusted_binding_pairs
                and assets[primary_id].occurrence_id == asset.occurrence_id
            ):
                evidence = _reverse_pair_evidence(trusted_binding_pairs[primary_id])
            else:
                evidence = classify_context(candidate_id, primary_id)
            declared_context = {asset.provenance, *asset.context_tags}
            if declared_context & _FORCED_SECONDARY_CONTEXT and evidence.relationship in {
                AMBIGUOUS,
                SIMILAR_DISTINCT,
            }:
                own_evidence = own_candidate_evidence.get(candidate_id)
                if own_evidence is not None and own_evidence.relationship in {
                    CROP_VARIANT,
                    ANNOTATED_VARIANT,
                    CONTRAST_VARIANT,
                }:
                    evidence = _PairEvidence(
                        own_evidence.relationship,
                        (
                            *own_evidence.reason_codes,
                            "TRUSTED_OCCURRENCE_CONTEXT_DERIVATION",
                            "MANDATORY_SECONDARY_NON_SUBSTITUTING",
                        ),
                        own_evidence.hash_distance,
                        own_evidence.mean_error,
                        own_evidence.correlation,
                        own_evidence.edge_correlation,
                        own_evidence.changed_fraction,
                        own_evidence.crop_correlation,
                        own_evidence.crop_side,
                    )
            if candidate_id == primary_id:
                role = PRIMARY
                relationship = SELF
                reason_codes = ("PRIMARY_BY_PROVEN_DETAIL",)
            elif forced_secondary(candidate_id, primary_id):
                role = MANDATORY_SECONDARY
                relationship = evidence.relationship
                reason_codes = (*evidence.reason_codes, "FORCED_CONTEXT_ROLE")
                secondary.append(
                    {
                        "candidate_id": candidate_id,
                        "path": asset.relative_path,
                        "role": MANDATORY_SECONDARY,
                        "relationship": relationship,
                        "occurrence_id": asset.occurrence_id,
                        "photo_id": occurrence.photo_id,
                        "page_number": occurrence.page_number,
                    }
                )
                if relationship == AMBIGUOUS:
                    ambiguity_ids.append(candidate_id)
            elif evidence.relationship in {
                EXACT_BYTES,
                EXACT_DECODED_PIXELS,
                FULL_FRAME_EQUIVALENT,
            }:
                role = EQUIVALENT
                relationship = evidence.relationship
                reason_codes = evidence.reason_codes
                equivalent_ids.append(candidate_id)
            else:
                role = MANDATORY_SECONDARY
                relationship = evidence.relationship
                reason_codes = evidence.reason_codes
                secondary.append(
                    {
                        "candidate_id": candidate_id,
                        "path": asset.relative_path,
                        "role": MANDATORY_SECONDARY,
                        "relationship": relationship,
                        "occurrence_id": asset.occurrence_id,
                        "photo_id": occurrence.photo_id,
                        "page_number": occurrence.page_number,
                    }
                )
                if relationship == AMBIGUOUS:
                    ambiguity_ids.append(candidate_id)
            row_state[candidate_id] = {
                "candidate_id": candidate_id,
                "occurrence_id": asset.occurrence_id,
                "photo_id": occurrence.photo_id,
                "page_number": occurrence.page_number,
                "xref": occurrence.xref,
                "bbox": _safe_bbox(occurrence.bbox),
                "path": asset.relative_path,
                "provenance": asset.provenance,
                "context_tags": list(asset.context_tags),
                "file_sha256": asset.file_sha256,
                "decoded_pixel_sha256": asset.decoded_pixel_sha256,
                "width": asset.width,
                "height": asset.height,
                "mode": asset.mode,
                "detail_score": round(asset.detail_score, 10),
                "proven_detail_area": proven_area[candidate_id],
                "likely_upscaled": bool(upscale_sources[candidate_id]),
                "group_id": group_id,
                "role": role,
                "relationship_to_primary": relationship,
                "relationship_reason_codes": list(reason_codes),
                "verified_linked_binding": trusted_binding_receipts.get(candidate_id),
            }
        primary = assets[primary_id]
        member_occurrences = []
        for occurrence_id in cluster:
            occurrence = occurrence_by_id[occurrence_id]
            member_occurrences.append(
                {
                    "occurrence_id": occurrence_id,
                    "photo_id": occurrence.photo_id,
                    "page_number": occurrence.page_number,
                    "xref": occurrence.xref,
                    "bbox": _safe_bbox(occurrence.bbox),
                }
            )
        built_groups.append(
            {
                "group_id": group_id,
                "status": AMBIGUOUS_STATUS if ambiguity_ids else RESOLVED,
                "primary_candidate_id": primary_id,
                "primary_path": primary.relative_path,
                "primary_file_sha256": primary.file_sha256,
                "primary_width": primary.width,
                "primary_height": primary.height,
                "member_occurrences": member_occurrences,
                "equivalent_candidate_ids": sorted(equivalent_ids),
                "equivalent_paths": [
                    assets[candidate_id].relative_path for candidate_id in sorted(equivalent_ids)
                ],
                "mandatory_secondary": sorted(
                    secondary,
                    key=lambda item: (str(item["candidate_id"]), str(item["relationship"])),
                ),
                "ambiguity_candidate_ids": sorted(ambiguity_ids),
            }
        )

    # Similar-but-distinct and non-transitive strong matches remain explicit context
    # across groups; groups are never merged by this pass.
    group_by_id = {group["group_id"]: group for group in built_groups}
    sorted_group_ids = sorted(group_by_id)
    for index, left_group_id in enumerate(sorted_group_ids):
        for right_group_id in sorted_group_ids[index + 1 :]:
            left_primary = group_primary_assets[left_group_id]
            right_primary = group_primary_assets[right_group_id]
            evidence = classify_non_crop(left_primary, right_primary)
            relationship = evidence.relationship
            if relationship in {EXACT_BYTES, EXACT_DECODED_PIXELS, FULL_FRAME_EQUIVALENT}:
                relationship = AMBIGUOUS
                reason_codes = ("NO_TRANSITIVE_CLOSURE", "CROSS_GROUP_EQUIVALENCE_NOT_MERGED")
            elif relationship not in {
                CROP_VARIANT,
                ANNOTATED_VARIANT,
                CONTRAST_VARIANT,
                SIMILAR_DISTINCT,
            }:
                continue
            else:
                reason_codes = evidence.reason_codes
            for owner_group_id, context_candidate_id in (
                (left_group_id, right_primary),
                (right_group_id, left_primary),
            ):
                owner = group_by_id[owner_group_id]
                context_asset = assets[context_candidate_id]
                occurrence = occurrence_by_id[context_asset.occurrence_id]
                entry = {
                    "candidate_id": context_candidate_id,
                    "path": context_asset.relative_path,
                    "role": MANDATORY_SECONDARY,
                    "relationship": relationship,
                    "occurrence_id": context_asset.occurrence_id,
                    "photo_id": occurrence.photo_id,
                    "page_number": occurrence.page_number,
                }
                owner["mandatory_secondary"].append(entry)
                owner["mandatory_secondary"] = sorted(
                    {
                        (str(item["candidate_id"]), str(item["relationship"])): item
                        for item in owner["mandatory_secondary"]
                    }.values(),
                    key=lambda item: (str(item["candidate_id"]), str(item["relationship"])),
                )
                if relationship == AMBIGUOUS:
                    owner["status"] = AMBIGUOUS_STATUS
                    owner["ambiguity_candidate_ids"] = sorted(
                        set(owner["ambiguity_candidate_ids"]) | {context_candidate_id}
                    )
            # Reason codes are retained in rows for own-group relationships; a cross-
            # group relationship is fully identified by the mandatory entry vocabulary.
            _ = reason_codes

    role_order = {PRIMARY: 0, EQUIVALENT: 1, MANDATORY_SECONDARY: 2}
    rows = tuple(
        sorted(
            row_state.values(),
            key=lambda item: (
                str(item["group_id"]),
                role_order[str(item["role"])],
                str(item["candidate_id"]),
            ),
        )
    )
    groups = tuple(sorted(built_groups, key=lambda item: str(item["group_id"])))
    input_manifest_sha256 = _sha256_json(_manifest_rows(rows))
    resolution_manifest_sha256 = _resolution_manifest(rows, groups)
    receipt = {
        "report": {
            "sha256": report_sha256,
            "size_bytes": report.stat().st_size,
        },
        "linked_inventory": {
            "filename": inventory_relative,
            "sha256": inventory_sha256,
            "size_bytes": inventory.stat().st_size,
        },
        "policy": _policy_dict(policy),
        "pillow_version": __version__,
        "occurrence_count": len(occurrences),
        "candidate_count": len(rows),
        "supplied_candidate_count": len(candidates),
        "group_count": len(groups),
        "input_manifest_sha256": input_manifest_sha256,
        "resolution_manifest_sha256": resolution_manifest_sha256,
    }
    return ImageVariantResolution(
        receipt=receipt,
        rows=rows,
        groups=groups,
        _validated_artifact_root=root,
        _validated_paths={candidate_id: asset.path for candidate_id, asset in assets.items()},
    )


def _validate_serialized_asset(row: Mapping[str, Any], artifact_root: Path) -> Path:
    relative = row.get("path")
    if not isinstance(relative, str) or not relative or _URI_MARKER.search(relative):
        raise ImageVariantResolutionError("INVALID_SERIALIZED_PATH")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ImageVariantResolutionError("INVALID_SERIALIZED_PATH")
    resolved, normalized = _inside_root(
        artifact_root / candidate, artifact_root, "SERIALIZED_PATH_ESCAPE"
    )
    if normalized != candidate.as_posix():
        raise ImageVariantResolutionError("NON_CANONICAL_SERIALIZED_PATH")
    expected_sha256 = row.get("file_sha256")
    if not isinstance(expected_sha256, str) or not _HEX_SHA256.fullmatch(expected_sha256):
        raise ImageVariantResolutionError("INVALID_SERIALIZED_SHA256")
    if _sha256_file(resolved) != expected_sha256:
        raise ImageVariantResolutionError("CANDIDATE_FILE_TAMPERED")
    try:
        if resolved.stat().st_size > DEFAULT_IMAGE_VARIANT_POLICY.maximum_file_bytes:
            raise ImageVariantResolutionError("CANDIDATE_FILE_SIZE_REJECTED")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(resolved) as image:
                raw_width, raw_height = image.size
                if (
                    raw_width <= 0
                    or raw_height <= 0
                    or max(raw_width, raw_height) > DEFAULT_IMAGE_VARIANT_POLICY.maximum_side_px
                    or raw_width * raw_height > DEFAULT_IMAGE_VARIANT_POLICY.maximum_pixels
                ):
                    raise ImageVariantResolutionError("CANDIDATE_DIMENSIONS_REJECTED")
                image.load()
                decoded = ImageOps.exif_transpose(image).convert("RGB")
    except ImageVariantResolutionError:
        raise
    except (
        OSError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise ImageVariantResolutionError("CANDIDATE_DECODE_FAILED") from None
    width = row.get("width")
    height = row.get("height")
    if (
        not isinstance(width, int)
        or isinstance(width, bool)
        or not isinstance(height, int)
        or isinstance(height, bool)
        or [decoded.width, decoded.height] != [width, height]
    ):
        raise ImageVariantResolutionError("CANDIDATE_DIMENSIONS_TAMPERED")
    if row.get("mode") != "RGB":
        raise ImageVariantResolutionError("CANDIDATE_MODE_TAMPERED")
    pixel_digest = hashlib.sha256()
    pixel_digest.update(f"RGB:{decoded.width}:{decoded.height}:".encode("ascii"))
    pixel_digest.update(decoded.tobytes())
    if pixel_digest.hexdigest() != row.get("decoded_pixel_sha256"):
        raise ImageVariantResolutionError("CANDIDATE_PIXELS_TAMPERED")
    detail_score = row.get("detail_score")
    recalculated_detail_score = round(
        _detail_score(
            _limited_preview(decoded, DEFAULT_IMAGE_VARIANT_POLICY.detail_preview_max_side)
        ),
        10,
    )
    if (
        not isinstance(detail_score, (int, float))
        or isinstance(detail_score, bool)
        or not math.isfinite(float(detail_score))
        or abs(float(detail_score) - recalculated_detail_score) > 1e-10
    ):
        raise ImageVariantResolutionError("CANDIDATE_DETAIL_SCORE_TAMPERED")
    proven_area = row.get("proven_detail_area")
    likely_upscaled = row.get("likely_upscaled")
    area = decoded.width * decoded.height
    if (
        not isinstance(proven_area, int)
        or isinstance(proven_area, bool)
        or not 0 < proven_area <= area
        or not isinstance(likely_upscaled, bool)
        or (not likely_upscaled and proven_area != area)
        or (likely_upscaled and proven_area >= area)
    ):
        raise ImageVariantResolutionError("CANDIDATE_DETAIL_EVIDENCE_INVALID")
    return resolved


def _validate_result_structure(result: ImageVariantResolution) -> None:
    if result.schema != IMAGE_VARIANT_RECEIPT_SCHEMA:
        raise ImageVariantResolutionError("RECEIPT_SCHEMA_MISMATCH")
    row_by_id: dict[str, Mapping[str, Any]] = {}
    rows_by_group: dict[str, list[Mapping[str, Any]]] = {}
    for row in result.rows:
        candidate_id = row.get("candidate_id")
        if (
            not isinstance(candidate_id, str)
            or not _TOKEN.fullmatch(candidate_id)
            or candidate_id in row_by_id
        ):
            raise ImageVariantResolutionError("RECEIPT_ROW_ID_INVALID")
        occurrence_id = row.get("occurrence_id")
        photo_id = row.get("photo_id")
        group_id = row.get("group_id")
        provenance = row.get("provenance")
        if not all(
            isinstance(value, str) and _TOKEN.fullmatch(value)
            for value in (occurrence_id, photo_id, group_id, provenance)
        ):
            raise ImageVariantResolutionError("RECEIPT_ROW_METADATA_INVALID")
        context_tags = row.get("context_tags")
        if (
            not isinstance(context_tags, list)
            or any(not isinstance(tag, str) or not _TOKEN.fullmatch(tag) for tag in context_tags)
            or context_tags != sorted(set(context_tags))
        ):
            raise ImageVariantResolutionError("RECEIPT_CONTEXT_TAGS_INVALID")
        page_number = row.get("page_number")
        xref = row.get("xref")
        if (
            not isinstance(page_number, int)
            or isinstance(page_number, bool)
            or page_number < 1
            or (
                xref is not None
                and (not isinstance(xref, int) or isinstance(xref, bool) or xref < 0)
            )
        ):
            raise ImageVariantResolutionError("RECEIPT_ROW_METADATA_INVALID")
        try:
            normalized_bbox = _safe_bbox(row.get("bbox"))
        except (TypeError, ValueError):
            raise ImageVariantResolutionError("RECEIPT_ROW_METADATA_INVALID") from None
        if normalized_bbox != row.get("bbox"):
            raise ImageVariantResolutionError("RECEIPT_ROW_METADATA_INVALID")
        role = row.get("role")
        relationship = row.get("relationship_to_primary")
        if role not in {PRIMARY, EQUIVALENT, MANDATORY_SECONDARY}:
            raise ImageVariantResolutionError("RECEIPT_ROLE_INVALID")
        if relationship not in {
            SELF,
            EXACT_BYTES,
            EXACT_DECODED_PIXELS,
            FULL_FRAME_EQUIVALENT,
            CROP_VARIANT,
            ANNOTATED_VARIANT,
            CONTRAST_VARIANT,
            SIMILAR_DISTINCT,
            AMBIGUOUS,
        }:
            raise ImageVariantResolutionError("RECEIPT_RELATIONSHIP_INVALID")
        if (role == PRIMARY) != (relationship == SELF):
            raise ImageVariantResolutionError("RECEIPT_ROLE_RELATIONSHIP_INVALID")
        if role == EQUIVALENT and relationship not in {
            EXACT_BYTES,
            EXACT_DECODED_PIXELS,
            FULL_FRAME_EQUIVALENT,
        }:
            raise ImageVariantResolutionError("RECEIPT_EQUIVALENT_RELATIONSHIP_INVALID")
        declared_context = {str(provenance), *context_tags}
        if declared_context & _FORCED_SECONDARY_CONTEXT and role != MANDATORY_SECONDARY:
            raise ImageVariantResolutionError("RECEIPT_FORCED_CONTEXT_ROLE_INVALID")
        automatic_embedded = candidate_id.startswith("embedded:")
        if automatic_embedded != (provenance == "PDF_EMBEDDED") or (
            automatic_embedded and candidate_id != f"embedded:{occurrence_id}"
        ):
            raise ImageVariantResolutionError("RECEIPT_EMBEDDED_IDENTITY_INVALID")
        binding = row.get("verified_linked_binding")
        trusted_binding_declared = bool(
            provenance == "REPORT_LINKED_ORIGINAL" and "VERIFIED_THUMBNAIL_BINDING" in context_tags
        )
        if (binding is not None) != trusted_binding_declared:
            raise ImageVariantResolutionError("RECEIPT_LINKED_BINDING_INVALID")
        if binding is not None:
            if (
                not isinstance(binding, dict)
                or binding.get("source") != "LINKED_IMAGE_RETRIEVAL_CONFIRM_IMAGE_BINDING"
                or binding.get("policy_version") != DEFAULT_LINKED_IMAGE_POLICY.version
                or binding.get("transform") not in {"FULL_FRAME_RESIZE", "CENTER_CROP_COVER"}
            ):
                raise ImageVariantResolutionError("RECEIPT_LINKED_BINDING_INVALID")
            crop_box = binding.get("normalized_crop_box")
            if (
                not isinstance(crop_box, list)
                or len(crop_box) != 4
                or any(
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not math.isfinite(float(value))
                    or not 0.0 <= float(value) <= 1.0
                    for value in crop_box
                )
                or float(crop_box[2]) <= float(crop_box[0])
                or float(crop_box[3]) <= float(crop_box[1])
            ):
                raise ImageVariantResolutionError("RECEIPT_LINKED_BINDING_INVALID")
        row_by_id[candidate_id] = row
        rows_by_group.setdefault(str(group_id), []).append(row)
    seen_groups: set[str] = set()
    for group in result.groups:
        group_id = group.get("group_id")
        if (
            not isinstance(group_id, str)
            or not _TOKEN.fullmatch(group_id)
            or group_id in seen_groups
        ):
            raise ImageVariantResolutionError("RECEIPT_GROUP_ID_INVALID")
        seen_groups.add(group_id)
        if group.get("status") not in {RESOLVED, AMBIGUOUS_STATUS}:
            raise ImageVariantResolutionError("RECEIPT_GROUP_STATUS_INVALID")
        group_rows = rows_by_group.get(group_id, [])
        primary_rows = [row for row in group_rows if row.get("role") == PRIMARY]
        if len(primary_rows) != 1:
            raise ImageVariantResolutionError("RECEIPT_PRIMARY_COUNT_INVALID")
        primary_id = group.get("primary_candidate_id")
        primary = row_by_id.get(str(primary_id))
        if primary is not primary_rows[0] or primary.get("group_id") != group_id:
            raise ImageVariantResolutionError("RECEIPT_PRIMARY_INVALID")
        if any(
            group.get(group_key) != primary.get(row_key)
            for group_key, row_key in (
                ("primary_path", "path"),
                ("primary_file_sha256", "file_sha256"),
                ("primary_width", "width"),
                ("primary_height", "height"),
            )
        ):
            raise ImageVariantResolutionError("RECEIPT_PRIMARY_METADATA_MISMATCH")

        member_occurrences = group.get("member_occurrences")
        if not isinstance(member_occurrences, list):
            raise ImageVariantResolutionError("RECEIPT_MEMBER_OCCURRENCES_INVALID")
        occurrence_metadata: dict[str, tuple[Any, ...]] = {}
        for row in group_rows:
            occurrence_id = str(row["occurrence_id"])
            metadata = (
                row.get("photo_id"),
                row.get("page_number"),
                row.get("xref"),
                row.get("bbox"),
            )
            if (
                occurrence_id in occurrence_metadata
                and occurrence_metadata[occurrence_id] != metadata
            ):
                raise ImageVariantResolutionError("RECEIPT_OCCURRENCE_METADATA_MISMATCH")
            occurrence_metadata[occurrence_id] = metadata
        serialized_occurrences: dict[str, tuple[Any, ...]] = {}
        for item in member_occurrences:
            if not isinstance(item, dict) or not isinstance(item.get("occurrence_id"), str):
                raise ImageVariantResolutionError("RECEIPT_MEMBER_OCCURRENCES_INVALID")
            occurrence_id = str(item["occurrence_id"])
            if occurrence_id in serialized_occurrences:
                raise ImageVariantResolutionError("RECEIPT_MEMBER_OCCURRENCES_INVALID")
            serialized_occurrences[occurrence_id] = (
                item.get("photo_id"),
                item.get("page_number"),
                item.get("xref"),
                item.get("bbox"),
            )
        if serialized_occurrences != occurrence_metadata:
            raise ImageVariantResolutionError("RECEIPT_MEMBER_OCCURRENCES_INVALID")
        expected_group_id = (
            "IVG-"
            + hashlib.sha256("\x00".join(sorted(occurrence_metadata)).encode("utf-8")).hexdigest()[
                :16
            ]
        )
        if group_id != expected_group_id:
            raise ImageVariantResolutionError("RECEIPT_GROUP_BINDING_INVALID")
        embedded_occurrences = {
            str(row["occurrence_id"])
            for row in group_rows
            if row.get("provenance") == "PDF_EMBEDDED"
        }
        if embedded_occurrences != set(occurrence_metadata):
            raise ImageVariantResolutionError("RECEIPT_EMBEDDED_COVERAGE_INVALID")

        equivalent_ids = group.get("equivalent_candidate_ids")
        equivalent_paths = group.get("equivalent_paths")
        if not isinstance(equivalent_ids, list) or not isinstance(equivalent_paths, list):
            raise ImageVariantResolutionError("RECEIPT_EQUIVALENT_INVALID")
        expected_equivalent_ids = sorted(
            str(row["candidate_id"]) for row in group_rows if row.get("role") == EQUIVALENT
        )
        if equivalent_ids != expected_equivalent_ids or equivalent_paths != [
            row_by_id[candidate_id]["path"] for candidate_id in expected_equivalent_ids
        ]:
            raise ImageVariantResolutionError("RECEIPT_EQUIVALENT_INVALID")

        mandatory_secondary = group.get("mandatory_secondary")
        if not isinstance(mandatory_secondary, list):
            raise ImageVariantResolutionError("RECEIPT_SECONDARY_INVALID")
        own_secondary_ids: set[str] = set()
        ambiguous_ids: set[str] = set()
        seen_secondary_ids: set[str] = set()
        for item in mandatory_secondary:
            if not isinstance(item, dict):
                raise ImageVariantResolutionError("RECEIPT_SECONDARY_INVALID")
            candidate_id = item.get("candidate_id")
            row = row_by_id.get(str(candidate_id))
            relationship = item.get("relationship")
            if (
                row is None
                or candidate_id in seen_secondary_ids
                or item.get("path") != row.get("path")
                or item.get("occurrence_id") != row.get("occurrence_id")
                or item.get("photo_id") != row.get("photo_id")
                or item.get("page_number") != row.get("page_number")
                or relationship
                not in {
                    EXACT_BYTES,
                    EXACT_DECODED_PIXELS,
                    FULL_FRAME_EQUIVALENT,
                    CROP_VARIANT,
                    ANNOTATED_VARIANT,
                    CONTRAST_VARIANT,
                    SIMILAR_DISTINCT,
                    AMBIGUOUS,
                }
            ):
                raise ImageVariantResolutionError("RECEIPT_SECONDARY_INVALID")
            if item.get("role") != MANDATORY_SECONDARY:
                raise ImageVariantResolutionError("RECEIPT_SECONDARY_ROLE_INVALID")
            seen_secondary_ids.add(str(candidate_id))
            if relationship == AMBIGUOUS:
                ambiguous_ids.add(str(candidate_id))
            if row.get("group_id") == group_id:
                if (
                    row.get("role") != MANDATORY_SECONDARY
                    or row.get("relationship_to_primary") != relationship
                ):
                    raise ImageVariantResolutionError("RECEIPT_SECONDARY_MEMBERSHIP_INVALID")
                own_secondary_ids.add(str(candidate_id))
            elif row.get("role") != PRIMARY or relationship not in {
                CROP_VARIANT,
                ANNOTATED_VARIANT,
                CONTRAST_VARIANT,
                SIMILAR_DISTINCT,
                AMBIGUOUS,
            }:
                raise ImageVariantResolutionError("RECEIPT_CROSS_GROUP_CONTEXT_INVALID")
        expected_own_secondary_ids = {
            str(row["candidate_id"]) for row in group_rows if row.get("role") == MANDATORY_SECONDARY
        }
        if own_secondary_ids != expected_own_secondary_ids:
            raise ImageVariantResolutionError("RECEIPT_SECONDARY_COVERAGE_INVALID")
        serialized_ambiguity = group.get("ambiguity_candidate_ids")
        if not isinstance(serialized_ambiguity, list) or serialized_ambiguity != sorted(
            ambiguous_ids
        ):
            raise ImageVariantResolutionError("RECEIPT_AMBIGUITY_COVERAGE_INVALID")
        expected_status = AMBIGUOUS_STATUS if ambiguous_ids else RESOLVED
        if group.get("status") != expected_status:
            raise ImageVariantResolutionError("RECEIPT_GROUP_STATUS_INVALID")

        eligible_rows = [row for row in group_rows if row.get("role") in {PRIMARY, EQUIVALENT}]
        expected_primary = sorted(
            eligible_rows,
            key=lambda row: (
                -int(row["proven_detail_area"]),
                -float(row["detail_score"]),
                -(int(row["width"]) * int(row["height"])),
                int(row.get("provenance") == "PDF_EMBEDDED"),
                str(row["candidate_id"]),
            ),
        )[0]
        if expected_primary is not primary:
            raise ImageVariantResolutionError("RECEIPT_PRIMARY_RANK_INVALID")
    if set(rows_by_group) != seen_groups:
        raise ImageVariantResolutionError("RECEIPT_ROW_GROUP_INVALID")


def _revalidate_serialized_linked_bindings(
    result: ImageVariantResolution,
    inventory: Mapping[str, Any],
    validated_paths: Mapping[str, Path],
) -> None:
    embedded_by_occurrence = {
        str(row["occurrence_id"]): row
        for row in result.rows
        if row.get("provenance") == "PDF_EMBEDDED"
    }
    group_by_id = {str(group["group_id"]): group for group in result.groups}
    for row in result.rows:
        context_tags = row.get("context_tags")
        if not isinstance(context_tags, list) or "VERIFIED_THUMBNAIL_BINDING" not in context_tags:
            continue
        candidate_id = str(row["candidate_id"])
        occurrence_id = str(row["occurrence_id"])
        embedded_row = embedded_by_occurrence.get(occurrence_id)
        if embedded_row is None or not _inventory_confirms_linked_asset(
            inventory,
            photo_id=str(row["photo_id"]),
            page_number=int(row["page_number"]),
            relative_path=str(row["path"]),
            file_sha256=str(row["file_sha256"]),
            width=int(row["width"]),
            height=int(row["height"]),
        ):
            raise ImageVariantResolutionError("TRUSTED_LINKED_INVENTORY_BINDING_FAILED")
        try:
            evidence = confirm_image_binding(
                validated_paths[str(embedded_row["candidate_id"])],
                validated_paths[candidate_id].read_bytes(),
                require_usable_detail_gain=True,
            )
        except (KeyError, OSError, LinkedImageError):
            raise ImageVariantResolutionError(
                "TRUSTED_LINKED_BINDING_RECONFIRMATION_FAILED"
            ) from None
        if row.get("verified_linked_binding") != _trusted_binding_receipt(evidence):
            raise ImageVariantResolutionError("TRUSTED_LINKED_BINDING_RECEIPT_MISMATCH")
        group = group_by_id[str(row["group_id"])]
        if group.get("primary_candidate_id") == candidate_id:
            expected_relation = _trusted_binding_pair(evidence).relationship
            if (
                embedded_row.get("group_id") != row.get("group_id")
                or embedded_row.get("role") != MANDATORY_SECONDARY
                or embedded_row.get("relationship_to_primary") != expected_relation
            ):
                raise ImageVariantResolutionError("TRUSTED_LINKED_PRIMARY_RELATION_INVALID")


def load_image_variant_resolution(
    path: Path,
    *,
    artifact_root: Path,
    expected_report_sha256: str,
    expected_inventory_sha256: str,
) -> ImageVariantResolution:
    root = artifact_root.resolve(strict=True)
    receipt_path, _relative = _inside_root(path, root, "UNSAFE_RECEIPT_PATH")
    try:
        if receipt_path.stat().st_size > 10 * 1024 * 1024:
            raise ImageVariantResolutionError("RECEIPT_TOO_LARGE")
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except ImageVariantResolutionError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ImageVariantResolutionError("RECEIPT_READ_FAILED") from None
    if not isinstance(payload, dict) or payload.get("schema") != IMAGE_VARIANT_RECEIPT_SCHEMA:
        raise ImageVariantResolutionError("RECEIPT_SCHEMA_MISMATCH")
    receipt = payload.get("receipt")
    rows = payload.get("rows")
    groups = payload.get("groups")
    if not isinstance(receipt, dict) or not isinstance(rows, list) or not isinstance(groups, list):
        raise ImageVariantResolutionError("RECEIPT_SHAPE_INVALID")
    report = receipt.get("report")
    inventory = receipt.get("linked_inventory")
    if not isinstance(report, dict) or report.get("sha256") != expected_report_sha256.lower():
        raise ImageVariantResolutionError("REPORT_SHA256_MISMATCH")
    if (
        not isinstance(inventory, dict)
        or inventory.get("sha256") != expected_inventory_sha256.lower()
    ):
        raise ImageVariantResolutionError("INVENTORY_SHA256_MISMATCH")
    filename = inventory.get("filename")
    if not isinstance(filename, str) or not filename:
        raise ImageVariantResolutionError("INVENTORY_PATH_INVALID")
    inventory_path = Path(filename)
    if inventory_path.is_absolute() or ".." in inventory_path.parts:
        raise ImageVariantResolutionError("INVENTORY_PATH_INVALID")
    resolved_inventory, normalized_inventory = _inside_root(
        root / inventory_path, root, "INVENTORY_PATH_INVALID"
    )
    if normalized_inventory != inventory_path.as_posix():
        raise ImageVariantResolutionError("INVENTORY_PATH_INVALID")
    if _sha256_file(resolved_inventory) != expected_inventory_sha256.lower():
        raise ImageVariantResolutionError("INVENTORY_FILE_TAMPERED")
    inventory_payload = _read_linked_inventory(resolved_inventory)
    inventory_report_sha256 = inventory_payload.get("report_sha256")
    if (
        inventory_report_sha256 is not None
        and inventory_report_sha256 != expected_report_sha256.lower()
    ):
        raise ImageVariantResolutionError("INVENTORY_REPORT_SHA256_MISMATCH")
    if receipt.get("policy") != _policy_dict(DEFAULT_IMAGE_VARIANT_POLICY):
        raise ImageVariantResolutionError("POLICY_BINDING_MISMATCH")
    if receipt.get("pillow_version") != __version__:
        raise ImageVariantResolutionError("PILLOW_VERSION_MISMATCH")
    result = ImageVariantResolution(
        receipt=receipt,
        rows=tuple(rows),
        groups=tuple(groups),
    )
    _validate_result_structure(result)
    if receipt.get("occurrence_count") != len(
        {str(row.get("occurrence_id")) for row in result.rows}
    ):
        raise ImageVariantResolutionError("RECEIPT_OCCURRENCE_COUNT_MISMATCH")
    if receipt.get("candidate_count") != len(result.rows):
        raise ImageVariantResolutionError("RECEIPT_CANDIDATE_COUNT_MISMATCH")
    if receipt.get("group_count") != len(result.groups):
        raise ImageVariantResolutionError("RECEIPT_GROUP_COUNT_MISMATCH")
    if receipt.get("input_manifest_sha256") != _sha256_json(_manifest_rows(result.rows)):
        raise ImageVariantResolutionError("INPUT_MANIFEST_MISMATCH")
    if receipt.get("resolution_manifest_sha256") != _resolution_manifest(
        result.rows, result.groups
    ):
        raise ImageVariantResolutionError("RESOLUTION_MANIFEST_MISMATCH")
    validated_paths = {
        str(row["candidate_id"]): _validate_serialized_asset(row, root) for row in result.rows
    }
    _revalidate_serialized_linked_bindings(result, inventory_payload, validated_paths)
    return ImageVariantResolution(
        receipt=result.receipt,
        rows=result.rows,
        groups=result.groups,
        schema=result.schema,
        _validated_artifact_root=root,
        _validated_paths=validated_paths,
    )


def _validated_result_path(
    result: ImageVariantResolution,
    row: Mapping[str, Any],
    root: Path,
) -> Path:
    candidate_id = str(row["candidate_id"])
    cached = result._validated_paths.get(candidate_id)
    if cached is None or result._validated_artifact_root != root:
        return _validate_serialized_asset(row, root)
    resolved, normalized = _inside_root(cached, root, "SERIALIZED_PATH_ESCAPE")
    if normalized != row.get("path"):
        raise ImageVariantResolutionError("NON_CANONICAL_SERIALIZED_PATH")
    if _sha256_file(resolved) != row.get("file_sha256"):
        raise ImageVariantResolutionError("CANDIDATE_FILE_TAMPERED")
    return resolved


def validated_primary_paths(
    result: ImageVariantResolution,
    *,
    artifact_root: Path,
) -> dict[str, Path]:
    root = artifact_root.resolve(strict=True)
    _validate_result_structure(result)
    rows = {str(row["candidate_id"]): row for row in result.rows}
    validated: dict[str, Path] = {}
    for group in sorted(result.groups, key=lambda item: str(item["group_id"])):
        candidate_id = str(group["primary_candidate_id"])
        validated[candidate_id] = _validated_result_path(result, rows[candidate_id], root)
    return validated


def validated_mandatory_secondary_paths(
    result: ImageVariantResolution,
    *,
    artifact_root: Path,
) -> dict[str, Path]:
    root = artifact_root.resolve(strict=True)
    _validate_result_structure(result)
    rows = {str(row["candidate_id"]): row for row in result.rows}
    validated: dict[str, Path] = {}
    for group in sorted(result.groups, key=lambda item: str(item["group_id"])):
        for item in sorted(
            group["mandatory_secondary"],
            key=lambda value: (str(value["candidate_id"]), str(value["relationship"])),
        ):
            candidate_id = str(item["candidate_id"])
            if candidate_id not in validated:
                validated[candidate_id] = _validated_result_path(result, rows[candidate_id], root)
    return validated
