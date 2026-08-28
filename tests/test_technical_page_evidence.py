from __future__ import annotations

import copy
import hashlib
import json
import struct
import zlib
from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from classifire.services.technical_page_evidence import (
    TECHNICAL_PAGE_EVIDENCE_MAX_BYTES,
    TECHNICAL_PAGE_EVIDENCE_MAX_PNG_CHUNKS,
    TechnicalPageEvidenceError,
    parse_technical_page_evidence,
)

DOCUMENT_ID = "11111111-1111-4111-8111-111111111111"
OTHER_DOCUMENT_ID = "22222222-2222-4222-8222-222222222222"
SOURCE_SHA256 = "a" * 64
SOURCE_SIZE_BYTES = 123_456
POLICY_VERSION = "technical-extraction-policy-v1"
POLICY_BYTES = b'{"policy":"technical-extraction-policy-v1"}'
POLICY_SHA256 = hashlib.sha256(POLICY_BYTES).hexdigest()
WORKER_IMAGE_DIGEST = "d" * 64
PAGE_NUMBER = 2
PAGE_COUNT = 4
PAGE_WIDTH = Decimal("612")
PAGE_HEIGHT = Decimal("792")
OCR_THRESHOLD = Decimal("80.00")


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return len(data).to_bytes(4, "big") + chunk_type + data + crc.to_bytes(4, "big")


def _png(*, width: int = 8, height: int = 6) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(b"\x00"))
        + _png_chunk(b"IEND", b"")
    )


def _native_block(
    *,
    block_id: str = "native-1",
    order: int = 1,
    text: str = "Test evidence",
) -> dict[str, object]:
    return {
        "bbox": {"x0": 10, "x1": 100, "y0": 20, "y1": 40},
        "id": block_id,
        "order": order,
        "text": text,
    }


def _ocr_block(
    *,
    block_id: str = "ocr-1",
    order: int = 1,
    confidence: object = 91.25,
) -> dict[str, object]:
    return {
        "bbox": {"x0": 12, "x1": 102, "y0": 42, "y1": 60},
        "confidence": confidence,
        "id": block_id,
        "order": order,
        "text": "OCR evidence",
    }


def _packet(image: bytes) -> dict[str, object]:
    image_sha256 = hashlib.sha256(image).hexdigest()
    return {
        "schema": "technical-page-evidence-v1",
        "source": {
            "technical_document_id": DOCUMENT_ID,
            "sha256": SOURCE_SHA256,
            "size_bytes": SOURCE_SIZE_BYTES,
        },
        "page": {
            "number": PAGE_NUMBER,
            "count": PAGE_COUNT,
            "width_points": 612,
            "height_points": 792,
            "image": {
                "sha256": image_sha256,
                "size_bytes": len(image),
                "width_pixels": 8,
                "height_pixels": 6,
            },
        },
        "extraction": {
            "policy_version": POLICY_VERSION,
            "policy_sha256": POLICY_SHA256,
            "worker_image_digest": WORKER_IMAGE_DIGEST,
            "ocr_low_confidence_threshold": 80,
            "native_text_blocks": [_native_block()],
            "ocr": {
                "status": "ocr_not_required",
                "engine": None,
                "engine_version": None,
                "language": None,
                "image_sha256": None,
                "blocks": [],
            },
            "human_review_required": False,
            "warnings": [],
        },
    }


def _raw(packet: dict[str, object]) -> bytes:
    return json.dumps(
        packet,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _parse(
    packet: dict[str, object],
    image: bytes,
    *,
    raw: bytes | None = None,
    **overrides: object,
):  # type: ignore[no-untyped-def]
    kwargs: dict[str, object] = {
        "page_image_bytes": image,
        "expected_technical_document_id": DOCUMENT_ID,
        "expected_source_sha256": SOURCE_SHA256,
        "expected_source_size_bytes": SOURCE_SIZE_BYTES,
        "expected_page_number": PAGE_NUMBER,
        "expected_page_count": PAGE_COUNT,
        "expected_page_width_points": PAGE_WIDTH,
        "expected_page_height_points": PAGE_HEIGHT,
        "expected_page_image_sha256": hashlib.sha256(image).hexdigest(),
        "expected_page_image_size_bytes": len(image),
        "expected_page_image_width_pixels": 8,
        "expected_page_image_height_pixels": 6,
        "expected_extraction_policy": POLICY_VERSION,
        "expected_extraction_policy_bytes": POLICY_BYTES,
        "expected_extraction_policy_sha256": POLICY_SHA256,
        "expected_worker_image_digest": WORKER_IMAGE_DIGEST,
        "expected_ocr_low_confidence_threshold": OCR_THRESHOLD,
    }
    kwargs.update(overrides)
    return parse_technical_page_evidence(
        _raw(packet) if raw is None else raw,
        **kwargs,  # type: ignore[arg-type]
    )


def _assert_rejected(
    code: str,
    packet: dict[str, object],
    image: bytes,
    *,
    raw: bytes | None = None,
    **overrides: object,
) -> None:
    with pytest.raises(TechnicalPageEvidenceError) as caught:
        _parse(packet, image, raw=raw, **overrides)
    assert caught.value.code == code
    assert str(caught.value) == code
    assert "\\" not in str(caught.value)
    assert "/" not in str(caught.value)


def test_valid_native_packet_is_frozen_and_exactly_bound() -> None:
    image = _png()
    packet = _packet(image)
    raw = _raw(packet)

    evidence = _parse(packet, image, raw=raw)

    assert evidence.technical_document_id == DOCUMENT_ID
    assert evidence.page_number == PAGE_NUMBER
    assert evidence.page_count == PAGE_COUNT
    assert evidence.packet_sha256 == hashlib.sha256(raw).hexdigest()
    assert evidence.packet_size_bytes == len(raw)
    assert evidence.image.sha256 == hashlib.sha256(image).hexdigest()
    assert evidence.image.size_bytes == len(image)
    assert evidence.extraction_mode == "native_text"
    assert evidence.ocr.status == "ocr_not_required"
    assert evidence.human_review_required is False
    with pytest.raises(FrozenInstanceError):
        evidence.page_count = 99  # type: ignore[misc]


def test_packet_whitespace_changes_packet_identity_and_binding() -> None:
    image = _png()
    packet = _packet(image)
    raw = _raw(packet)

    original = _parse(packet, image, raw=raw)
    changed = _parse(packet, image, raw=raw + b" ")

    assert changed.packet_size_bytes == original.packet_size_bytes + 1
    assert changed.packet_sha256 != original.packet_sha256
    assert changed.binding_sha256 != original.binding_sha256


def test_duplicate_nested_key_is_rejected_before_binding() -> None:
    image = _png()
    packet = _packet(image)
    raw = _raw(packet)
    needle = f'"source":{{"sha256":"{SOURCE_SHA256}",'.encode()
    replacement = (
        f'"source":{{"sha256":"{SOURCE_SHA256}","sh\\u0061256":"{SOURCE_SHA256}",'
    ).encode()
    duplicate = raw.replace(needle, replacement, 1)
    assert duplicate != raw

    _assert_rejected("PAGE_EVIDENCE_JSON_INVALID", packet, image, raw=duplicate)


@pytest.mark.parametrize(
    ("mutator", "overrides", "code"),
    [
        (
            lambda packet: packet["source"].__setitem__(  # type: ignore[union-attr]
                "technical_document_id", OTHER_DOCUMENT_ID
            ),
            {},
            "PAGE_EVIDENCE_DOCUMENT_BINDING_MISMATCH",
        ),
        (
            lambda packet: None,
            {"expected_technical_document_id": OTHER_DOCUMENT_ID},
            "PAGE_EVIDENCE_DOCUMENT_BINDING_MISMATCH",
        ),
        (
            lambda packet: packet["source"].__setitem__(  # type: ignore[union-attr]
                "size_bytes", SOURCE_SIZE_BYTES + 1
            ),
            {},
            "PAGE_EVIDENCE_SOURCE_BINDING_MISMATCH",
        ),
        (
            lambda packet: packet["page"].__setitem__("count", PAGE_COUNT + 1),  # type: ignore[union-attr]
            {},
            "PAGE_EVIDENCE_PAGE_BINDING_MISMATCH",
        ),
        (
            lambda packet: None,
            {"expected_page_count": PAGE_COUNT - 1},
            "PAGE_EVIDENCE_PAGE_BINDING_MISMATCH",
        ),
        (
            lambda packet: packet["page"].__setitem__("width_points", 611),  # type: ignore[union-attr]
            {},
            "PAGE_EVIDENCE_COORDINATES_INVALID",
        ),
        (
            lambda packet: packet["extraction"].__setitem__(  # type: ignore[union-attr]
                "worker_image_digest", "e" * 64
            ),
            {},
            "PAGE_EVIDENCE_WORKER_BINDING_MISMATCH",
        ),
        (
            lambda packet: packet["extraction"].__setitem__(  # type: ignore[union-attr]
                "policy_sha256", "f" * 64
            ),
            {},
            "PAGE_EVIDENCE_POLICY_BINDING_MISMATCH",
        ),
    ],
)
def test_packet_and_trusted_envelope_mismatches_fail_closed(
    mutator,  # type: ignore[no-untyped-def]
    overrides: dict[str, object],
    code: str,
) -> None:
    image = _png()
    packet = _packet(image)
    mutator(packet)

    _assert_rejected(code, packet, image, **overrides)


def test_policy_hash_must_match_actual_canonical_policy_bytes() -> None:
    image = _png()
    packet = _packet(image)

    _assert_rejected(
        "PAGE_EVIDENCE_POLICY_BINDING_MISMATCH",
        packet,
        image,
        expected_extraction_policy_bytes=b'{"policy":"different"}',
    )


@pytest.mark.parametrize("corruption", ["signature", "ihdr_crc", "trailing", "missing_iend"])
def test_malformed_page_image_bytes_are_rejected(corruption: str) -> None:
    valid_image = _png()
    packet = _packet(valid_image)
    if corruption == "signature":
        image = b"BAD!" + valid_image[4:]
    elif corruption == "ihdr_crc":
        image = valid_image[:29] + bytes([valid_image[29] ^ 1]) + valid_image[30:]
    elif corruption == "trailing":
        image = valid_image + b"untrusted"
    else:
        image = valid_image[:-12]

    _assert_rejected(
        "PAGE_EVIDENCE_IMAGE_INVALID",
        packet,
        image,
        expected_page_image_sha256=hashlib.sha256(image).hexdigest(),
        expected_page_image_size_bytes=len(image),
    )


def test_png_chunk_count_is_bounded() -> None:
    valid_image = _png()
    ihdr_end = 33
    ancillary = _png_chunk(b"aaAa", b"")
    image = (
        valid_image[:ihdr_end]
        + ancillary * TECHNICAL_PAGE_EVIDENCE_MAX_PNG_CHUNKS
        + valid_image[ihdr_end:]
    )
    packet = _packet(valid_image)

    _assert_rejected(
        "PAGE_EVIDENCE_IMAGE_INVALID",
        packet,
        image,
        expected_page_image_sha256=hashlib.sha256(image).hexdigest(),
        expected_page_image_size_bytes=len(image),
    )


def test_png_dimensions_and_expected_image_hash_are_independently_checked() -> None:
    image = _png(width=4097, height=1)
    packet = _packet(image)
    _assert_rejected(
        "PAGE_EVIDENCE_IMAGE_INVALID",
        packet,
        image,
        expected_page_image_sha256=hashlib.sha256(image).hexdigest(),
        expected_page_image_size_bytes=len(image),
        expected_page_image_width_pixels=4097,
        expected_page_image_height_pixels=1,
    )

    valid_image = _png()
    valid_packet = _packet(valid_image)
    _assert_rejected(
        "PAGE_EVIDENCE_IMAGE_BINDING_MISMATCH",
        valid_packet,
        valid_image,
        expected_page_image_sha256="f" * 64,
    )


def test_coordinates_block_order_and_cross_stream_ids_are_strict() -> None:
    image = _png()

    outside = _packet(image)
    outside["extraction"]["native_text_blocks"][0]["bbox"]["x1"] = 613  # type: ignore[index]
    _assert_rejected("PAGE_EVIDENCE_COORDINATES_INVALID", outside, image)

    imprecise = _packet(image)
    imprecise["extraction"]["native_text_blocks"][0]["bbox"]["x0"] = 1.00001  # type: ignore[index]
    _assert_rejected("PAGE_EVIDENCE_COORDINATES_INVALID", imprecise, image)

    unordered = _packet(image)
    unordered["extraction"]["native_text_blocks"][0]["order"] = 2  # type: ignore[index]
    _assert_rejected("PAGE_EVIDENCE_COUNT_INVALID", unordered, image)

    duplicate = _packet(image)
    extraction = duplicate["extraction"]  # type: ignore[assignment]
    extraction["ocr"] = {  # type: ignore[index]
        "status": "ocr_completed",
        "engine": "tesseract",
        "engine_version": "5.0",
        "language": "eng",
        "image_sha256": hashlib.sha256(image).hexdigest(),
        "blocks": [_ocr_block(block_id="native-1")],
    }
    _assert_rejected("PAGE_EVIDENCE_COUNT_INVALID", duplicate, image)


def test_ocr_outcomes_are_explicit_and_threshold_bound() -> None:
    image = _png()
    packet = _packet(image)
    extraction = packet["extraction"]  # type: ignore[assignment]
    extraction["native_text_blocks"] = []  # type: ignore[index]
    extraction["human_review_required"] = True  # type: ignore[index]
    extraction["ocr"] = {  # type: ignore[index]
        "status": "low_confidence",
        "engine": "tesseract",
        "engine_version": "5.0",
        "language": "eng",
        "image_sha256": hashlib.sha256(image).hexdigest(),
        "blocks": [_ocr_block(confidence=79.99)],
    }

    evidence = _parse(packet, image)
    assert evidence.extraction_mode == "ocr"
    assert evidence.ocr.status == "low_confidence"
    assert evidence.ocr.minimum_confidence == Decimal("79.99")
    assert evidence.human_review_required is True

    wrong_state = copy.deepcopy(packet)
    wrong_state["extraction"]["ocr"]["status"] = "ocr_completed"  # type: ignore[index]
    _assert_rejected("PAGE_EVIDENCE_OCR_STATE_INVALID", wrong_state, image)

    imprecise = copy.deepcopy(packet)
    imprecise["extraction"]["ocr"]["blocks"][0]["confidence"] = 79.999  # type: ignore[index]
    _assert_rejected("PAGE_EVIDENCE_CONFIDENCE_INVALID", imprecise, image)


def test_unreadable_page_requires_explicit_review_state() -> None:
    image = _png()
    packet = _packet(image)
    extraction = packet["extraction"]  # type: ignore[assignment]
    extraction["native_text_blocks"] = []  # type: ignore[index]
    extraction["human_review_required"] = True  # type: ignore[index]
    extraction["ocr"] = {  # type: ignore[index]
        "status": "unreadable",
        "engine": "tesseract",
        "engine_version": "5.0",
        "language": "eng",
        "image_sha256": hashlib.sha256(image).hexdigest(),
        "blocks": [],
    }

    evidence = _parse(packet, image)
    assert evidence.extraction_mode == "unreadable"
    assert evidence.ocr.status == "unreadable"

    extraction["human_review_required"] = False  # type: ignore[index]
    _assert_rejected("PAGE_EVIDENCE_OCR_STATE_INVALID", packet, image)


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (b"", "PAGE_EVIDENCE_EMPTY"),
        (b"\xff", "PAGE_EVIDENCE_JSON_INVALID"),
        (b'{"value":1e999999999999999999999}', "PAGE_EVIDENCE_JSON_INVALID"),
        (b" " * (TECHNICAL_PAGE_EVIDENCE_MAX_BYTES + 1), "PAGE_EVIDENCE_TOO_LARGE"),
    ],
    ids=("empty", "invalid-utf8", "extreme-exponent", "too-large"),
)
def test_raw_packet_failures_never_escape_stable_errors(raw: bytes, code: str) -> None:
    image = _png()
    _assert_rejected(code, _packet(image), image, raw=raw)


def test_non_byte_packet_and_image_inputs_fail_with_stable_errors() -> None:
    image = _png()
    packet = _packet(image)
    _assert_rejected(
        "PAGE_EVIDENCE_JSON_INVALID",
        packet,
        image,
        raw=bytearray(_raw(packet)),  # type: ignore[arg-type]
    )
    _assert_rejected(
        "PAGE_EVIDENCE_IMAGE_INVALID",
        packet,
        bytearray(image),  # type: ignore[arg-type]
    )


def test_unknown_fields_text_controls_and_warning_order_fail_closed() -> None:
    image = _png()

    extra = _packet(image)
    extra["authority"] = "approved"
    _assert_rejected("PAGE_EVIDENCE_STRUCTURE_INVALID", extra, image)

    control = _packet(image)
    control["extraction"]["native_text_blocks"][0]["text"] = "bad\x00text"  # type: ignore[index]
    _assert_rejected("PAGE_EVIDENCE_TEXT_INVALID", control, image)

    warnings = _packet(image)
    warnings["extraction"]["warnings"] = ["SECOND_WARNING", "FIRST_WARNING"]  # type: ignore[index]
    _assert_rejected("PAGE_EVIDENCE_WARNING_INVALID", warnings, image)
