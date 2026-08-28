"""Strict, authority-neutral validation for isolated page-extraction output."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import zlib
from dataclasses import dataclass
from decimal import Decimal, DecimalException
from typing import Never, cast

TECHNICAL_PAGE_EVIDENCE_SCHEMA = "technical-page-evidence-v1"
TECHNICAL_PAGE_EVIDENCE_VALIDATOR_POLICY = "technical-page-evidence-validator-v1"
TECHNICAL_PAGE_EVIDENCE_MAX_BYTES = 4 * 1024 * 1024
TECHNICAL_PAGE_EVIDENCE_MAX_SOURCE_BYTES = 1024 * 1024 * 1024
TECHNICAL_PAGE_EVIDENCE_MAX_PAGE_IMAGE_BYTES = 25 * 1024 * 1024
TECHNICAL_PAGE_EVIDENCE_MAX_POLICY_BYTES = 1024 * 1024
TECHNICAL_PAGE_EVIDENCE_MAX_PAGES = 500
TECHNICAL_PAGE_EVIDENCE_MAX_BLOCKS = 10_000
TECHNICAL_PAGE_EVIDENCE_MAX_BLOCK_TEXT_CHARACTERS = 100_000
TECHNICAL_PAGE_EVIDENCE_MAX_TEXT_CHARACTERS = 1_000_000
TECHNICAL_PAGE_EVIDENCE_MAX_WARNINGS = 100
TECHNICAL_PAGE_EVIDENCE_MAX_EDGE_PIXELS = 4096
TECHNICAL_PAGE_EVIDENCE_MAX_PIXELS = 8_000_000
TECHNICAL_PAGE_EVIDENCE_MAX_PNG_CHUNKS = 10_000

_MAX_PAGE_POINTS = Decimal("20000")
_HEX_SHA256 = frozenset("0123456789abcdef")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_UUID4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")
_SAFE_POLICY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+/-]{0,99}$")
_SAFE_ENGINE_VALUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._:+/-]{0,99}$")
_SAFE_LANGUAGE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,49}$")
_SAFE_WARNING = re.compile(r"^[A-Z][A-Z0-9_]{0,99}$")
_OCR_STATUSES = frozenset({"ocr_not_required", "ocr_completed", "low_confidence", "unreadable"})
_ERROR_CODES = frozenset(
    {
        "PAGE_EVIDENCE_BLOCK_INVALID",
        "PAGE_EVIDENCE_CONFIDENCE_INVALID",
        "PAGE_EVIDENCE_COORDINATES_INVALID",
        "PAGE_EVIDENCE_COUNT_INVALID",
        "PAGE_EVIDENCE_DOCUMENT_BINDING_MISMATCH",
        "PAGE_EVIDENCE_EMPTY",
        "PAGE_EVIDENCE_IMAGE_BINDING_MISMATCH",
        "PAGE_EVIDENCE_IMAGE_INVALID",
        "PAGE_EVIDENCE_JSON_INVALID",
        "PAGE_EVIDENCE_OCR_STATE_INVALID",
        "PAGE_EVIDENCE_PAGE_BINDING_MISMATCH",
        "PAGE_EVIDENCE_POLICY_BINDING_MISMATCH",
        "PAGE_EVIDENCE_SCHEMA_INVALID",
        "PAGE_EVIDENCE_SOURCE_BINDING_MISMATCH",
        "PAGE_EVIDENCE_STRUCTURE_INVALID",
        "PAGE_EVIDENCE_TEXT_INVALID",
        "PAGE_EVIDENCE_TOO_LARGE",
        "PAGE_EVIDENCE_WARNING_INVALID",
        "PAGE_EVIDENCE_WORKER_BINDING_MISMATCH",
    }
)


class TechnicalPageEvidenceError(ValueError):
    """A stable, path-free rejection at the isolated parser-output boundary."""

    def __init__(self, code: str) -> None:
        if code not in _ERROR_CODES:
            raise ValueError("Unknown technical page evidence error code")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class TechnicalEvidenceBox:
    x0: Decimal
    y0: Decimal
    x1: Decimal
    y1: Decimal


@dataclass(frozen=True, slots=True)
class TechnicalEvidenceTextBlock:
    block_id: str
    order: int
    bbox: TechnicalEvidenceBox
    text: str
    confidence: Decimal | None


@dataclass(frozen=True, slots=True)
class TechnicalPageImageBinding:
    sha256: str
    size_bytes: int
    width_pixels: int
    height_pixels: int


@dataclass(frozen=True, slots=True)
class TechnicalOcrEvidence:
    status: str
    engine: str | None
    engine_version: str | None
    language: str | None
    image_sha256: str | None
    blocks: tuple[TechnicalEvidenceTextBlock, ...]
    minimum_confidence: Decimal | None


@dataclass(frozen=True, slots=True)
class TechnicalPageEvidence:
    schema: str
    validator_policy: str
    packet_sha256: str
    packet_size_bytes: int
    binding_sha256: str
    technical_document_id: str
    source_sha256: str
    source_size_bytes: int
    page_number: int
    page_count: int
    page_width_points: Decimal
    page_height_points: Decimal
    image: TechnicalPageImageBinding
    extraction_policy: str
    extraction_policy_sha256: str
    worker_image_digest: str
    ocr_low_confidence_threshold: Decimal
    native_text_blocks: tuple[TechnicalEvidenceTextBlock, ...]
    ocr: TechnicalOcrEvidence
    extraction_mode: str
    human_review_required: bool
    warnings: tuple[str, ...]


def _fail(code: str) -> Never:
    raise TechnicalPageEvidenceError(code)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("PAGE_EVIDENCE_JSON_INVALID")
        result[key] = value
    return result


def _reject_nonfinite(_value: str) -> object:
    _fail("PAGE_EVIDENCE_JSON_INVALID")


def _json_decimal(value: str) -> Decimal:
    if len(value) > 100:
        _fail("PAGE_EVIDENCE_JSON_INVALID")
    try:
        parsed = Decimal(value)
        if not parsed.is_finite() or abs(parsed.adjusted()) > 100_000:
            _fail("PAGE_EVIDENCE_JSON_INVALID")
        return parsed
    except DecimalException:
        _fail("PAGE_EVIDENCE_JSON_INVALID")


def _strict_json(raw: bytes) -> dict[str, object]:
    if not isinstance(raw, bytes):
        _fail("PAGE_EVIDENCE_JSON_INVALID")
    if not raw:
        _fail("PAGE_EVIDENCE_EMPTY")
    if len(raw) > TECHNICAL_PAGE_EVIDENCE_MAX_BYTES:
        _fail("PAGE_EVIDENCE_TOO_LARGE")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_float=_json_decimal,
            parse_int=int,
            parse_constant=_reject_nonfinite,
        )
    except TechnicalPageEvidenceError:
        raise
    except (
        DecimalException,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
    ):
        _fail("PAGE_EVIDENCE_JSON_INVALID")
    if not isinstance(value, dict):
        _fail("PAGE_EVIDENCE_STRUCTURE_INVALID")
    return cast(dict[str, object], value)


def _object(
    value: object,
    keys: frozenset[str],
    *,
    code: str = "PAGE_EVIDENCE_STRUCTURE_INVALID",
) -> dict[str, object]:
    if not isinstance(value, dict) or frozenset(value) != keys:
        _fail(code)
    return cast(dict[str, object], value)


def _array(
    value: object,
    *,
    maximum: int,
    code: str = "PAGE_EVIDENCE_STRUCTURE_INVALID",
) -> list[object]:
    if not isinstance(value, list) or len(value) > maximum:
        _fail(code)
    return cast(list[object], value)


def _integer(value: object, *, minimum: int, maximum: int, code: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        _fail(code)
    return value


def _decimal(
    value: object,
    *,
    minimum: Decimal,
    maximum: Decimal,
    code: str,
    maximum_decimal_places: int | None = None,
) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        _fail(code)
    try:
        parsed = Decimal(value)
        valid = parsed.is_finite() and minimum <= parsed <= maximum
        exponent = parsed.as_tuple().exponent
        precision_valid = maximum_decimal_places is None or (
            isinstance(exponent, int) and exponent >= -maximum_decimal_places
        )
    except DecimalException:
        _fail(code)
    if not valid or not precision_valid:
        _fail(code)
    return parsed


def _sha256(value: object, *, code: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HEX_SHA256 for character in value)
    ):
        _fail(code)
    return value


def _uuid4(value: object, *, code: str) -> str:
    if not isinstance(value, str) or _UUID4.fullmatch(value) is None:
        _fail(code)
    return value


def _validated_png(png_bytes: bytes) -> TechnicalPageImageBinding:
    if (
        not isinstance(png_bytes, bytes)
        or not png_bytes
        or len(png_bytes) > TECHNICAL_PAGE_EVIDENCE_MAX_PAGE_IMAGE_BYTES
        or not png_bytes.startswith(_PNG_SIGNATURE)
    ):
        _fail("PAGE_EVIDENCE_IMAGE_INVALID")

    offset = len(_PNG_SIGNATURE)
    chunk_index = 0
    seen_plte = False
    seen_idat = False
    idat_closed = False
    idat_size = 0
    ihdr_data: bytes | None = None
    seen_iend = False

    while offset < len(png_bytes):
        if chunk_index >= TECHNICAL_PAGE_EVIDENCE_MAX_PNG_CHUNKS:
            _fail("PAGE_EVIDENCE_IMAGE_INVALID")
        if len(png_bytes) - offset < 12:
            _fail("PAGE_EVIDENCE_IMAGE_INVALID")
        chunk_size = int.from_bytes(png_bytes[offset : offset + 4], "big")
        chunk_type = png_bytes[offset + 4 : offset + 8]
        data_start = offset + 8
        data_end = data_start + chunk_size
        chunk_end = data_end + 4
        if any(
            not (65 <= character <= 90 or 97 <= character <= 122) for character in chunk_type
        ) or chunk_end > len(png_bytes):
            _fail("PAGE_EVIDENCE_IMAGE_INVALID")
        chunk_data = png_bytes[data_start:data_end]
        expected_crc = int.from_bytes(png_bytes[data_end:chunk_end], "big")
        actual_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            _fail("PAGE_EVIDENCE_IMAGE_INVALID")

        if chunk_index == 0:
            if chunk_type != b"IHDR" or chunk_size != 13:
                _fail("PAGE_EVIDENCE_IMAGE_INVALID")
            ihdr_data = chunk_data
        elif chunk_type == b"IHDR":
            _fail("PAGE_EVIDENCE_IMAGE_INVALID")
        elif chunk_type == b"PLTE":
            if seen_plte or seen_idat or chunk_size == 0 or chunk_size % 3 != 0:
                _fail("PAGE_EVIDENCE_IMAGE_INVALID")
            seen_plte = True
        elif chunk_type == b"IDAT":
            if idat_closed:
                _fail("PAGE_EVIDENCE_IMAGE_INVALID")
            seen_idat = True
            idat_size += chunk_size
        elif chunk_type == b"IEND":
            if chunk_size != 0 or not seen_idat or idat_size == 0 or chunk_end != len(png_bytes):
                _fail("PAGE_EVIDENCE_IMAGE_INVALID")
            seen_iend = True
            offset = chunk_end
            break
        else:
            if seen_idat:
                idat_closed = True
            if 65 <= chunk_type[0] <= 90:
                _fail("PAGE_EVIDENCE_IMAGE_INVALID")

        offset = chunk_end
        chunk_index += 1

    if not seen_iend or offset != len(png_bytes) or ihdr_data is None:
        _fail("PAGE_EVIDENCE_IMAGE_INVALID")

    width = int.from_bytes(ihdr_data[0:4], "big")
    height = int.from_bytes(ihdr_data[4:8], "big")
    bit_depth = ihdr_data[8]
    color_type = ihdr_data[9]
    compression = ihdr_data[10]
    filtering = ihdr_data[11]
    interlace = ihdr_data[12]
    valid_depths = {
        0: frozenset({1, 2, 4, 8, 16}),
        2: frozenset({8, 16}),
        3: frozenset({1, 2, 4, 8}),
        4: frozenset({8, 16}),
        6: frozenset({8, 16}),
    }
    if (
        width < 1
        or width > TECHNICAL_PAGE_EVIDENCE_MAX_EDGE_PIXELS
        or height < 1
        or height > TECHNICAL_PAGE_EVIDENCE_MAX_EDGE_PIXELS
        or width * height > TECHNICAL_PAGE_EVIDENCE_MAX_PIXELS
        or color_type not in valid_depths
        or bit_depth not in valid_depths[color_type]
        or compression != 0
        or filtering != 0
        or interlace not in (0, 1)
        or (color_type == 3 and not seen_plte)
    ):
        _fail("PAGE_EVIDENCE_IMAGE_INVALID")
    return TechnicalPageImageBinding(
        sha256=hashlib.sha256(png_bytes).hexdigest(),
        size_bytes=len(png_bytes),
        width_pixels=width,
        height_pixels=height,
    )


def _safe_string(value: object, pattern: re.Pattern[str], *, code: str) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        _fail(code)
    return value


def _block_text(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > TECHNICAL_PAGE_EVIDENCE_MAX_BLOCK_TEXT_CHARACTERS
    ):
        _fail("PAGE_EVIDENCE_TEXT_INVALID")
    for character in value:
        category = unicodedata.category(character)
        if category == "Cs" or (category == "Cc" and character not in "\t\n\r"):
            _fail("PAGE_EVIDENCE_TEXT_INVALID")
    return value


def _bbox(
    value: object,
    *,
    page_width: Decimal,
    page_height: Decimal,
) -> TechnicalEvidenceBox:
    item = _object(
        value,
        frozenset({"x0", "x1", "y0", "y1"}),
        code="PAGE_EVIDENCE_COORDINATES_INVALID",
    )
    x0 = _decimal(
        item["x0"],
        minimum=Decimal(0),
        maximum=page_width,
        code="PAGE_EVIDENCE_COORDINATES_INVALID",
        maximum_decimal_places=4,
    )
    x1 = _decimal(
        item["x1"],
        minimum=Decimal(0),
        maximum=page_width,
        code="PAGE_EVIDENCE_COORDINATES_INVALID",
        maximum_decimal_places=4,
    )
    y0 = _decimal(
        item["y0"],
        minimum=Decimal(0),
        maximum=page_height,
        code="PAGE_EVIDENCE_COORDINATES_INVALID",
        maximum_decimal_places=4,
    )
    y1 = _decimal(
        item["y1"],
        minimum=Decimal(0),
        maximum=page_height,
        code="PAGE_EVIDENCE_COORDINATES_INVALID",
        maximum_decimal_places=4,
    )
    if x0 >= x1 or y0 >= y1:
        _fail("PAGE_EVIDENCE_COORDINATES_INVALID")
    return TechnicalEvidenceBox(x0=x0, y0=y0, x1=x1, y1=y1)


def _text_blocks(
    value: object,
    *,
    page_width: Decimal,
    page_height: Decimal,
    ocr: bool,
) -> tuple[tuple[TechnicalEvidenceTextBlock, ...], int]:
    raw_blocks = _array(
        value,
        maximum=TECHNICAL_PAGE_EVIDENCE_MAX_BLOCKS,
        code="PAGE_EVIDENCE_COUNT_INVALID",
    )
    expected_keys = (
        frozenset({"bbox", "confidence", "id", "order", "text"})
        if ocr
        else frozenset({"bbox", "id", "order", "text"})
    )
    seen_ids: set[str] = set()
    blocks: list[TechnicalEvidenceTextBlock] = []
    text_characters = 0
    for expected_order, raw_block in enumerate(raw_blocks, start=1):
        item = _object(
            raw_block,
            expected_keys,
            code="PAGE_EVIDENCE_BLOCK_INVALID",
        )
        block_id = _safe_string(
            item["id"],
            _SAFE_ID,
            code="PAGE_EVIDENCE_BLOCK_INVALID",
        )
        if block_id in seen_ids:
            _fail("PAGE_EVIDENCE_COUNT_INVALID")
        seen_ids.add(block_id)
        order = _integer(
            item["order"],
            minimum=1,
            maximum=TECHNICAL_PAGE_EVIDENCE_MAX_BLOCKS,
            code="PAGE_EVIDENCE_COUNT_INVALID",
        )
        if order != expected_order:
            _fail("PAGE_EVIDENCE_COUNT_INVALID")
        text = _block_text(item["text"])
        text_characters += len(text)
        if text_characters > TECHNICAL_PAGE_EVIDENCE_MAX_TEXT_CHARACTERS:
            _fail("PAGE_EVIDENCE_COUNT_INVALID")
        confidence = (
            _decimal(
                item["confidence"],
                minimum=Decimal(0),
                maximum=Decimal(100),
                code="PAGE_EVIDENCE_CONFIDENCE_INVALID",
                maximum_decimal_places=2,
            )
            if ocr
            else None
        )
        blocks.append(
            TechnicalEvidenceTextBlock(
                block_id=block_id,
                order=order,
                bbox=_bbox(
                    item["bbox"],
                    page_width=page_width,
                    page_height=page_height,
                ),
                text=text,
                confidence=confidence,
            )
        )
    return tuple(blocks), text_characters


def _optional_safe_string(
    value: object,
    pattern: re.Pattern[str],
    *,
    code: str,
) -> str | None:
    if value is None:
        return None
    return _safe_string(value, pattern, code=code)


def _warnings(value: object) -> tuple[str, ...]:
    raw_warnings = _array(
        value,
        maximum=TECHNICAL_PAGE_EVIDENCE_MAX_WARNINGS,
        code="PAGE_EVIDENCE_WARNING_INVALID",
    )
    warnings: list[str] = []
    for raw_warning in raw_warnings:
        warnings.append(
            _safe_string(
                raw_warning,
                _SAFE_WARNING,
                code="PAGE_EVIDENCE_WARNING_INVALID",
            )
        )
    if warnings != sorted(set(warnings)):
        _fail("PAGE_EVIDENCE_WARNING_INVALID")
    return tuple(warnings)


def _binding_sha256(
    *,
    packet_sha256: str,
    packet_size_bytes: int,
    technical_document_id: str,
    source_sha256: str,
    source_size_bytes: int,
    page_number: int,
    page_count: int,
    page_width_points: Decimal,
    page_height_points: Decimal,
    page_image: TechnicalPageImageBinding,
    extraction_policy_sha256: str,
    worker_image_digest: str,
) -> str:
    payload = {
        "evidence_schema": TECHNICAL_PAGE_EVIDENCE_SCHEMA,
        "extraction_policy_sha256": extraction_policy_sha256,
        "packet_sha256": packet_sha256,
        "packet_size_bytes": packet_size_bytes,
        "page_count": page_count,
        "page_height_points": str(page_height_points),
        "page_image_height_pixels": page_image.height_pixels,
        "page_image_sha256": page_image.sha256,
        "page_image_size_bytes": page_image.size_bytes,
        "page_image_width_pixels": page_image.width_pixels,
        "page_number": page_number,
        "page_width_points": str(page_width_points),
        "source_sha256": source_sha256,
        "source_size_bytes": source_size_bytes,
        "technical_document_id": technical_document_id,
        "validator_policy": TECHNICAL_PAGE_EVIDENCE_VALIDATOR_POLICY,
        "worker_image_digest": worker_image_digest,
    }
    canonical = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


def parse_technical_page_evidence(
    raw: bytes,
    *,
    page_image_bytes: bytes,
    expected_technical_document_id: str,
    expected_source_sha256: str,
    expected_source_size_bytes: int,
    expected_page_number: int,
    expected_page_count: int,
    expected_page_width_points: Decimal,
    expected_page_height_points: Decimal,
    expected_page_image_sha256: str,
    expected_page_image_size_bytes: int,
    expected_page_image_width_pixels: int,
    expected_page_image_height_pixels: int,
    expected_extraction_policy: str,
    expected_extraction_policy_bytes: bytes,
    expected_extraction_policy_sha256: str,
    expected_worker_image_digest: str,
    expected_ocr_low_confidence_threshold: Decimal,
) -> TechnicalPageEvidence:
    """Parse one exact worker packet without creating or approving domain records."""

    technical_document_id = _uuid4(
        expected_technical_document_id,
        code="PAGE_EVIDENCE_DOCUMENT_BINDING_MISMATCH",
    )
    source_sha256 = _sha256(
        expected_source_sha256,
        code="PAGE_EVIDENCE_SOURCE_BINDING_MISMATCH",
    )
    source_size_bytes = _integer(
        expected_source_size_bytes,
        minimum=1,
        maximum=TECHNICAL_PAGE_EVIDENCE_MAX_SOURCE_BYTES,
        code="PAGE_EVIDENCE_SOURCE_BINDING_MISMATCH",
    )
    page_number = _integer(
        expected_page_number,
        minimum=1,
        maximum=TECHNICAL_PAGE_EVIDENCE_MAX_PAGES,
        code="PAGE_EVIDENCE_PAGE_BINDING_MISMATCH",
    )
    page_count = _integer(
        expected_page_count,
        minimum=1,
        maximum=TECHNICAL_PAGE_EVIDENCE_MAX_PAGES,
        code="PAGE_EVIDENCE_PAGE_BINDING_MISMATCH",
    )
    if page_number > page_count:
        _fail("PAGE_EVIDENCE_PAGE_BINDING_MISMATCH")
    expected_page_width = _decimal(
        expected_page_width_points,
        minimum=Decimal("0.0001"),
        maximum=_MAX_PAGE_POINTS,
        code="PAGE_EVIDENCE_COORDINATES_INVALID",
        maximum_decimal_places=4,
    )
    expected_page_height = _decimal(
        expected_page_height_points,
        minimum=Decimal("0.0001"),
        maximum=_MAX_PAGE_POINTS,
        code="PAGE_EVIDENCE_COORDINATES_INVALID",
        maximum_decimal_places=4,
    )
    computed_image = _validated_png(page_image_bytes)
    expected_image = TechnicalPageImageBinding(
        sha256=_sha256(
            expected_page_image_sha256,
            code="PAGE_EVIDENCE_IMAGE_BINDING_MISMATCH",
        ),
        size_bytes=_integer(
            expected_page_image_size_bytes,
            minimum=1,
            maximum=TECHNICAL_PAGE_EVIDENCE_MAX_PAGE_IMAGE_BYTES,
            code="PAGE_EVIDENCE_IMAGE_BINDING_MISMATCH",
        ),
        width_pixels=_integer(
            expected_page_image_width_pixels,
            minimum=1,
            maximum=TECHNICAL_PAGE_EVIDENCE_MAX_EDGE_PIXELS,
            code="PAGE_EVIDENCE_IMAGE_BINDING_MISMATCH",
        ),
        height_pixels=_integer(
            expected_page_image_height_pixels,
            minimum=1,
            maximum=TECHNICAL_PAGE_EVIDENCE_MAX_EDGE_PIXELS,
            code="PAGE_EVIDENCE_IMAGE_BINDING_MISMATCH",
        ),
    )
    if (
        expected_image.width_pixels * expected_image.height_pixels
        > TECHNICAL_PAGE_EVIDENCE_MAX_PIXELS
        or expected_image != computed_image
    ):
        _fail("PAGE_EVIDENCE_IMAGE_BINDING_MISMATCH")
    extraction_policy = _safe_string(
        expected_extraction_policy,
        _SAFE_POLICY,
        code="PAGE_EVIDENCE_POLICY_BINDING_MISMATCH",
    )
    if (
        not isinstance(expected_extraction_policy_bytes, bytes)
        or not expected_extraction_policy_bytes
        or len(expected_extraction_policy_bytes) > TECHNICAL_PAGE_EVIDENCE_MAX_POLICY_BYTES
    ):
        _fail("PAGE_EVIDENCE_POLICY_BINDING_MISMATCH")
    extraction_policy_sha256 = _sha256(
        expected_extraction_policy_sha256,
        code="PAGE_EVIDENCE_POLICY_BINDING_MISMATCH",
    )
    if hashlib.sha256(expected_extraction_policy_bytes).hexdigest() != extraction_policy_sha256:
        _fail("PAGE_EVIDENCE_POLICY_BINDING_MISMATCH")
    worker_image_digest = _sha256(
        expected_worker_image_digest,
        code="PAGE_EVIDENCE_WORKER_BINDING_MISMATCH",
    )
    ocr_threshold = _decimal(
        expected_ocr_low_confidence_threshold,
        minimum=Decimal(0),
        maximum=Decimal(100),
        code="PAGE_EVIDENCE_CONFIDENCE_INVALID",
        maximum_decimal_places=2,
    )

    root = _strict_json(raw)
    root = _object(
        root,
        frozenset({"extraction", "page", "schema", "source"}),
    )
    if root["schema"] != TECHNICAL_PAGE_EVIDENCE_SCHEMA:
        _fail("PAGE_EVIDENCE_SCHEMA_INVALID")

    source = _object(
        root["source"],
        frozenset({"sha256", "size_bytes", "technical_document_id"}),
    )
    returned_technical_document_id = _uuid4(
        source["technical_document_id"],
        code="PAGE_EVIDENCE_DOCUMENT_BINDING_MISMATCH",
    )
    if returned_technical_document_id != technical_document_id:
        _fail("PAGE_EVIDENCE_DOCUMENT_BINDING_MISMATCH")
    returned_source_sha256 = _sha256(
        source["sha256"],
        code="PAGE_EVIDENCE_SOURCE_BINDING_MISMATCH",
    )
    returned_source_size = _integer(
        source["size_bytes"],
        minimum=1,
        maximum=TECHNICAL_PAGE_EVIDENCE_MAX_SOURCE_BYTES,
        code="PAGE_EVIDENCE_SOURCE_BINDING_MISMATCH",
    )
    if returned_source_sha256 != source_sha256 or returned_source_size != source_size_bytes:
        _fail("PAGE_EVIDENCE_SOURCE_BINDING_MISMATCH")

    page = _object(
        root["page"],
        frozenset(
            {
                "count",
                "height_points",
                "image",
                "number",
                "width_points",
            }
        ),
    )
    returned_page_number = _integer(
        page["number"],
        minimum=1,
        maximum=TECHNICAL_PAGE_EVIDENCE_MAX_PAGES,
        code="PAGE_EVIDENCE_PAGE_BINDING_MISMATCH",
    )
    returned_page_count = _integer(
        page["count"],
        minimum=1,
        maximum=TECHNICAL_PAGE_EVIDENCE_MAX_PAGES,
        code="PAGE_EVIDENCE_PAGE_BINDING_MISMATCH",
    )
    if (
        returned_page_number != page_number
        or returned_page_count != page_count
        or returned_page_number > returned_page_count
    ):
        _fail("PAGE_EVIDENCE_PAGE_BINDING_MISMATCH")
    page_width = _decimal(
        page["width_points"],
        minimum=Decimal("0.0001"),
        maximum=_MAX_PAGE_POINTS,
        code="PAGE_EVIDENCE_COORDINATES_INVALID",
        maximum_decimal_places=4,
    )
    page_height = _decimal(
        page["height_points"],
        minimum=Decimal("0.0001"),
        maximum=_MAX_PAGE_POINTS,
        code="PAGE_EVIDENCE_COORDINATES_INVALID",
        maximum_decimal_places=4,
    )
    if page_width != expected_page_width or page_height != expected_page_height:
        _fail("PAGE_EVIDENCE_COORDINATES_INVALID")
    image = _object(
        page["image"],
        frozenset({"height_pixels", "sha256", "size_bytes", "width_pixels"}),
        code="PAGE_EVIDENCE_IMAGE_BINDING_MISMATCH",
    )
    returned_image = TechnicalPageImageBinding(
        sha256=_sha256(
            image["sha256"],
            code="PAGE_EVIDENCE_IMAGE_BINDING_MISMATCH",
        ),
        size_bytes=_integer(
            image["size_bytes"],
            minimum=1,
            maximum=TECHNICAL_PAGE_EVIDENCE_MAX_PAGE_IMAGE_BYTES,
            code="PAGE_EVIDENCE_IMAGE_BINDING_MISMATCH",
        ),
        width_pixels=_integer(
            image["width_pixels"],
            minimum=1,
            maximum=TECHNICAL_PAGE_EVIDENCE_MAX_EDGE_PIXELS,
            code="PAGE_EVIDENCE_IMAGE_BINDING_MISMATCH",
        ),
        height_pixels=_integer(
            image["height_pixels"],
            minimum=1,
            maximum=TECHNICAL_PAGE_EVIDENCE_MAX_EDGE_PIXELS,
            code="PAGE_EVIDENCE_IMAGE_BINDING_MISMATCH",
        ),
    )
    if (
        returned_image != expected_image
        or returned_image.width_pixels * returned_image.height_pixels
        > TECHNICAL_PAGE_EVIDENCE_MAX_PIXELS
    ):
        _fail("PAGE_EVIDENCE_IMAGE_BINDING_MISMATCH")

    extraction = _object(
        root["extraction"],
        frozenset(
            {
                "human_review_required",
                "native_text_blocks",
                "ocr",
                "ocr_low_confidence_threshold",
                "policy_sha256",
                "policy_version",
                "warnings",
                "worker_image_digest",
            }
        ),
    )
    returned_policy = _safe_string(
        extraction["policy_version"],
        _SAFE_POLICY,
        code="PAGE_EVIDENCE_POLICY_BINDING_MISMATCH",
    )
    returned_policy_sha256 = _sha256(
        extraction["policy_sha256"],
        code="PAGE_EVIDENCE_POLICY_BINDING_MISMATCH",
    )
    returned_threshold = _decimal(
        extraction["ocr_low_confidence_threshold"],
        minimum=Decimal(0),
        maximum=Decimal(100),
        code="PAGE_EVIDENCE_CONFIDENCE_INVALID",
        maximum_decimal_places=2,
    )
    if (
        returned_policy != extraction_policy
        or returned_policy_sha256 != extraction_policy_sha256
        or returned_threshold != ocr_threshold
    ):
        _fail("PAGE_EVIDENCE_POLICY_BINDING_MISMATCH")
    returned_worker_digest = _sha256(
        extraction["worker_image_digest"],
        code="PAGE_EVIDENCE_WORKER_BINDING_MISMATCH",
    )
    if returned_worker_digest != worker_image_digest:
        _fail("PAGE_EVIDENCE_WORKER_BINDING_MISMATCH")
    human_review_required = extraction["human_review_required"]
    if not isinstance(human_review_required, bool):
        _fail("PAGE_EVIDENCE_STRUCTURE_INVALID")

    native_blocks, native_characters = _text_blocks(
        extraction["native_text_blocks"],
        page_width=page_width,
        page_height=page_height,
        ocr=False,
    )
    ocr_value = _object(
        extraction["ocr"],
        frozenset(
            {
                "blocks",
                "engine",
                "engine_version",
                "image_sha256",
                "language",
                "status",
            }
        ),
        code="PAGE_EVIDENCE_OCR_STATE_INVALID",
    )
    ocr_status = ocr_value["status"]
    if not isinstance(ocr_status, str) or ocr_status not in _OCR_STATUSES:
        _fail("PAGE_EVIDENCE_OCR_STATE_INVALID")
    engine = _optional_safe_string(
        ocr_value["engine"],
        _SAFE_ENGINE_VALUE,
        code="PAGE_EVIDENCE_OCR_STATE_INVALID",
    )
    engine_version = _optional_safe_string(
        ocr_value["engine_version"],
        _SAFE_ENGINE_VALUE,
        code="PAGE_EVIDENCE_OCR_STATE_INVALID",
    )
    language = _optional_safe_string(
        ocr_value["language"],
        _SAFE_LANGUAGE,
        code="PAGE_EVIDENCE_OCR_STATE_INVALID",
    )
    raw_ocr_image_sha256 = ocr_value["image_sha256"]
    ocr_image_sha256 = (
        None
        if raw_ocr_image_sha256 is None
        else _sha256(
            raw_ocr_image_sha256,
            code="PAGE_EVIDENCE_IMAGE_BINDING_MISMATCH",
        )
    )
    ocr_blocks, ocr_characters = _text_blocks(
        ocr_value["blocks"],
        page_width=page_width,
        page_height=page_height,
        ocr=True,
    )
    if (
        len(native_blocks) + len(ocr_blocks) > TECHNICAL_PAGE_EVIDENCE_MAX_BLOCKS
        or native_characters + ocr_characters > TECHNICAL_PAGE_EVIDENCE_MAX_TEXT_CHARACTERS
        or {block.block_id for block in native_blocks} & {block.block_id for block in ocr_blocks}
    ):
        _fail("PAGE_EVIDENCE_COUNT_INVALID")

    minimum_confidence = (
        min(cast(Decimal, block.confidence) for block in ocr_blocks) if ocr_blocks else None
    )
    attempted_ocr = ocr_status != "ocr_not_required"
    if not attempted_ocr:
        if (
            engine is not None
            or engine_version is not None
            or language is not None
            or ocr_image_sha256 is not None
            or ocr_blocks
            or not native_blocks
        ):
            _fail("PAGE_EVIDENCE_OCR_STATE_INVALID")
    else:
        if (
            engine is None
            or engine_version is None
            or language is None
            or ocr_image_sha256 != expected_image.sha256
        ):
            _fail("PAGE_EVIDENCE_OCR_STATE_INVALID")
        if ocr_status == "unreadable":
            if ocr_blocks or not human_review_required:
                _fail("PAGE_EVIDENCE_OCR_STATE_INVALID")
        elif not ocr_blocks or minimum_confidence is None:
            _fail("PAGE_EVIDENCE_OCR_STATE_INVALID")
        elif minimum_confidence < ocr_threshold:
            if ocr_status != "low_confidence" or not human_review_required:
                _fail("PAGE_EVIDENCE_OCR_STATE_INVALID")
        elif ocr_status != "ocr_completed":
            _fail("PAGE_EVIDENCE_OCR_STATE_INVALID")

    if native_blocks and ocr_blocks:
        extraction_mode = "hybrid"
    elif ocr_blocks:
        extraction_mode = "ocr"
    elif native_blocks:
        extraction_mode = "native_text"
    else:
        extraction_mode = "unreadable"
    if extraction_mode == "unreadable" and not human_review_required:
        _fail("PAGE_EVIDENCE_OCR_STATE_INVALID")

    warnings = _warnings(extraction["warnings"])
    packet_sha256 = hashlib.sha256(raw).hexdigest()
    packet_size_bytes = len(raw)
    binding_sha256 = _binding_sha256(
        packet_sha256=packet_sha256,
        packet_size_bytes=packet_size_bytes,
        technical_document_id=technical_document_id,
        source_sha256=source_sha256,
        source_size_bytes=source_size_bytes,
        page_number=page_number,
        page_count=page_count,
        page_width_points=page_width,
        page_height_points=page_height,
        page_image=expected_image,
        extraction_policy_sha256=extraction_policy_sha256,
        worker_image_digest=worker_image_digest,
    )
    return TechnicalPageEvidence(
        schema=TECHNICAL_PAGE_EVIDENCE_SCHEMA,
        validator_policy=TECHNICAL_PAGE_EVIDENCE_VALIDATOR_POLICY,
        packet_sha256=packet_sha256,
        packet_size_bytes=packet_size_bytes,
        binding_sha256=binding_sha256,
        technical_document_id=technical_document_id,
        source_sha256=source_sha256,
        source_size_bytes=source_size_bytes,
        page_number=page_number,
        page_count=page_count,
        page_width_points=page_width,
        page_height_points=page_height,
        image=expected_image,
        extraction_policy=extraction_policy,
        extraction_policy_sha256=extraction_policy_sha256,
        worker_image_digest=worker_image_digest,
        ocr_low_confidence_threshold=ocr_threshold,
        native_text_blocks=native_blocks,
        ocr=TechnicalOcrEvidence(
            status=ocr_status,
            engine=engine,
            engine_version=engine_version,
            language=language,
            image_sha256=ocr_image_sha256,
            blocks=ocr_blocks,
            minimum_confidence=minimum_confidence,
        ),
        extraction_mode=extraction_mode,
        human_review_required=human_review_required,
        warnings=warnings,
    )


__all__ = [
    "TECHNICAL_PAGE_EVIDENCE_MAX_BLOCKS",
    "TECHNICAL_PAGE_EVIDENCE_MAX_BYTES",
    "TECHNICAL_PAGE_EVIDENCE_SCHEMA",
    "TECHNICAL_PAGE_EVIDENCE_VALIDATOR_POLICY",
    "TechnicalEvidenceBox",
    "TechnicalEvidenceTextBlock",
    "TechnicalOcrEvidence",
    "TechnicalPageEvidence",
    "TechnicalPageEvidenceError",
    "TechnicalPageImageBinding",
    "parse_technical_page_evidence",
]
