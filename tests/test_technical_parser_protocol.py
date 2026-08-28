from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from io import BytesIO
from typing import Any

import pytest

from classifire.services.technical_parser_protocol import (
    TECHNICAL_PARSER_EVIDENCE_MAX_BYTES,
    TECHNICAL_PARSER_HEADER_MAX_BYTES,
    TECHNICAL_PARSER_LAYOUT_MAX_BYTES,
    TECHNICAL_PARSER_LAYOUT_REQUEST_MAX_BYTES,
    TECHNICAL_PARSER_LAYOUT_REQUEST_SCHEMA,
    TECHNICAL_PARSER_LAYOUT_SCHEMA,
    TECHNICAL_PARSER_PAGE_FRAME_SCHEMA,
    TECHNICAL_PARSER_PNG_MAX_BYTES,
    TECHNICAL_PARSER_REQUEST_MAX_BYTES,
    TECHNICAL_PARSER_REQUEST_SCHEMA,
    TechnicalParserDocumentLayout,
    TechnicalParserLayoutErrorResult,
    TechnicalParserPageErrorFrame,
    TechnicalParserPageSuccessFrame,
    TechnicalParserProtocolError,
    encode_technical_parser_layout_request,
    encode_technical_parser_request,
    parse_technical_parser_layout,
    parse_technical_parser_layout_request,
    parse_technical_parser_layout_result,
    parse_technical_parser_page_frame,
    parse_technical_parser_request,
)

_DOCUMENT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
_SOURCE_SHA256 = "b" * 64
_SOURCE_SIZE_BYTES = 2_200_017
_POLICY = "technical-extraction-v1"
_POLICY_SHA256 = "c" * 64
_WORKER_DIGEST = "d" * 64
_LAYOUT_SHA256 = "e" * 64
_EVIDENCE = b'{"untrusted":"packet"}'
_IMAGE = b"not-yet-deep-validated-png"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _request_kwargs() -> dict[str, Any]:
    return {
        "technical_document_id": _DOCUMENT_ID,
        "source_sha256": _SOURCE_SHA256,
        "source_size_bytes": _SOURCE_SIZE_BYTES,
        "page_number": 1,
        "page_count": 2,
        "page_width_points": Decimal(612),
        "page_height_points": Decimal(792),
        "layout_sha256": _LAYOUT_SHA256,
        "extraction_policy": _POLICY,
        "extraction_policy_sha256": _POLICY_SHA256,
        "worker_image_digest": _WORKER_DIGEST,
        "ocr_low_confidence_threshold": Decimal("72.25"),
    }


def _layout_request_kwargs() -> dict[str, Any]:
    request = _request_kwargs()
    return {
        "technical_document_id": request["technical_document_id"],
        "source_sha256": request["source_sha256"],
        "source_size_bytes": request["source_size_bytes"],
        "extraction_policy": request["extraction_policy"],
        "extraction_policy_sha256": request["extraction_policy_sha256"],
        "worker_image_digest": request["worker_image_digest"],
        "ocr_low_confidence_threshold": request["ocr_low_confidence_threshold"],
    }


def _success_header(**overrides: object) -> dict[str, object]:
    header: dict[str, object] = {
        "schema": TECHNICAL_PARSER_PAGE_FRAME_SCHEMA,
        "status": "ok",
        "page_number": 1,
        "page_count": 2,
        "page_width_points": 612,
        "page_height_points": 792,
        "evidence_size_bytes": len(_EVIDENCE),
        "evidence_sha256": hashlib.sha256(_EVIDENCE).hexdigest(),
        "image_size_bytes": len(_IMAGE),
        "image_sha256": hashlib.sha256(_IMAGE).hexdigest(),
        "image_width_pixels": 1000,
        "image_height_pixels": 1200,
    }
    header.update(overrides)
    return header


def _error_header(**overrides: object) -> dict[str, object]:
    header: dict[str, object] = {
        "schema": TECHNICAL_PARSER_PAGE_FRAME_SCHEMA,
        "status": "error",
        "page_number": 1,
        "retryable": True,
        "error_code": "PARSER_PAGE_TIMEOUT",
    }
    header.update(overrides)
    return header


def _frame(
    header: dict[str, object],
    *,
    evidence: bytes = _EVIDENCE,
    image: bytes = _IMAGE,
    header_bytes: bytes | None = None,
    trailing: bytes = b"",
) -> bytes:
    encoded_header = _canonical(header) if header_bytes is None else header_bytes
    payload = b"" if header.get("status") == "error" else evidence + image
    return len(encoded_header).to_bytes(4, "big") + encoded_header + payload + trailing


def _layout(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": TECHNICAL_PARSER_LAYOUT_SCHEMA,
        "technical_document_id": _DOCUMENT_ID,
        "source_sha256": _SOURCE_SHA256,
        "source_size_bytes": _SOURCE_SIZE_BYTES,
        "extraction_policy": _POLICY,
        "extraction_policy_sha256": _POLICY_SHA256,
        "worker_image_digest": _WORKER_DIGEST,
        "page_count": 2,
        "pages": [
            {
                "number": 1,
                "count": 2,
                "width_points": 612,
                "height_points": 792,
            },
            {
                "number": 2,
                "count": 2,
                "width_points": 612.25,
                "height_points": 792.5,
            },
        ],
    }
    value.update(overrides)
    return value


def _layout_kwargs() -> dict[str, object]:
    return {
        "expected_technical_document_id": _DOCUMENT_ID,
        "expected_source_sha256": _SOURCE_SHA256,
        "expected_source_size_bytes": _SOURCE_SIZE_BYTES,
        "expected_extraction_policy": _POLICY,
        "expected_extraction_policy_sha256": _POLICY_SHA256,
        "expected_worker_image_digest": _WORKER_DIGEST,
    }


def _assert_code(error: pytest.ExceptionInfo[TechnicalParserProtocolError], code: str) -> None:
    assert error.value.code == code
    assert str(error.value) == code


def test_request_encoder_is_canonical_bounded_and_exactly_bound() -> None:
    encoded = encode_technical_parser_request(**_request_kwargs())

    assert encoded.isascii()
    assert len(encoded) <= TECHNICAL_PARSER_REQUEST_MAX_BYTES
    assert encoded == _canonical(json.loads(encoded))
    assert set(json.loads(encoded)) == {
        "extraction_policy",
        "extraction_policy_sha256",
        "layout_sha256",
        "ocr_low_confidence_threshold",
        "page_count",
        "page_height_points",
        "page_number",
        "page_width_points",
        "schema",
        "source_sha256",
        "source_size_bytes",
        "technical_document_id",
        "worker_image_digest",
    }
    request = parse_technical_parser_request(encoded)
    assert request.schema == TECHNICAL_PARSER_REQUEST_SCHEMA
    assert request.technical_document_id == _DOCUMENT_ID
    assert request.source_sha256 == _SOURCE_SHA256
    assert request.source_size_bytes == _SOURCE_SIZE_BYTES
    assert request.page_number == 1
    assert request.page_count == 2
    assert request.page_width_points == Decimal(612)
    assert request.page_height_points == Decimal(792)
    assert request.layout_sha256 == _LAYOUT_SHA256
    assert request.extraction_policy == _POLICY
    assert request.extraction_policy_sha256 == _POLICY_SHA256
    assert request.worker_image_digest == _WORKER_DIGEST
    assert request.ocr_low_confidence_threshold == Decimal("72.25")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("technical_document_id", "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"),
        ("source_sha256", "B" * 64),
        ("source_size_bytes", True),
        ("source_size_bytes", 0),
        ("page_number", 0),
        ("page_number", 501),
        ("page_count", True),
        ("page_count", 1.5),
        ("page_count", 501),
        ("page_count", 0),
        ("page_width_points", Decimal("612.00001")),
        ("page_height_points", 0),
        ("layout_sha256", "E" * 64),
        ("extraction_policy", "policy with spaces"),
        ("extraction_policy_sha256", "c" * 63),
        ("worker_image_digest", "g" * 64),
        ("ocr_low_confidence_threshold", Decimal("100.01")),
        ("ocr_low_confidence_threshold", Decimal("1.001")),
    ],
)
def test_request_encoder_rejects_invalid_types_and_ranges(field: str, value: object) -> None:
    kwargs = _request_kwargs()
    kwargs[field] = value

    with pytest.raises(TechnicalParserProtocolError) as caught:
        encode_technical_parser_request(**kwargs)

    _assert_code(caught, "PARSER_PROTOCOL_REQUEST_INVALID")


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema":"technical-parser-request-v1","schema":"duplicate"}',
        b'{"ocr_low_confidence_threshold":NaN}',
        b'\xff{"schema":"technical-parser-request-v1"}',
        b"[]",
        b" {}",
        _canonical(
            {
                **json.loads(encode_technical_parser_request(**_request_kwargs())),
                "extra": 1,
            }
        ),
    ],
)
def test_request_parser_rejects_duplicate_nonfinite_noncanonical_and_extra_json(
    raw: bytes,
) -> None:
    with pytest.raises(TechnicalParserProtocolError) as caught:
        parse_technical_parser_request(raw)

    _assert_code(caught, "PARSER_PROTOCOL_REQUEST_INVALID")


def test_request_parser_checks_the_byte_bound_before_json() -> None:
    with pytest.raises(TechnicalParserProtocolError) as caught:
        parse_technical_parser_request(b"{" + b" " * TECHNICAL_PARSER_REQUEST_MAX_BYTES)

    _assert_code(caught, "PARSER_PROTOCOL_REQUEST_TOO_LARGE")


def test_page_request_rejects_page_outside_persisted_layout() -> None:
    kwargs = _request_kwargs()
    kwargs["page_number"] = 2
    kwargs["page_count"] = 1

    with pytest.raises(TechnicalParserProtocolError) as caught:
        encode_technical_parser_request(**kwargs)

    _assert_code(caught, "PARSER_PROTOCOL_REQUEST_INVALID")


def test_layout_request_is_canonical_bounded_path_free_and_exactly_bound() -> None:
    encoded = encode_technical_parser_layout_request(**_layout_request_kwargs())

    assert encoded.isascii()
    assert len(encoded) <= TECHNICAL_PARSER_LAYOUT_REQUEST_MAX_BYTES
    assert encoded == _canonical(json.loads(encoded))
    payload = json.loads(encoded)
    assert set(payload) == {
        "extraction_policy",
        "extraction_policy_sha256",
        "ocr_low_confidence_threshold",
        "schema",
        "source_sha256",
        "source_size_bytes",
        "technical_document_id",
        "worker_image_digest",
    }
    assert all("path" not in key and "filename" not in key for key in payload)
    parsed = parse_technical_parser_layout_request(encoded)
    assert parsed.schema == TECHNICAL_PARSER_LAYOUT_REQUEST_SCHEMA
    assert parsed.technical_document_id == _DOCUMENT_ID
    assert parsed.source_sha256 == _SOURCE_SHA256
    assert parsed.source_size_bytes == _SOURCE_SIZE_BYTES
    assert parsed.extraction_policy == _POLICY
    assert parsed.extraction_policy_sha256 == _POLICY_SHA256
    assert parsed.worker_image_digest == _WORKER_DIGEST
    assert parsed.ocr_low_confidence_threshold == Decimal("72.25")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("technical_document_id", "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"),
        ("source_sha256", "B" * 64),
        ("source_size_bytes", True),
        ("extraction_policy", "policy with spaces"),
        ("extraction_policy_sha256", "c" * 63),
        ("worker_image_digest", "g" * 64),
        ("ocr_low_confidence_threshold", Decimal("1.001")),
    ],
)
def test_layout_request_rejects_invalid_trusted_bindings(
    field: str,
    value: object,
) -> None:
    kwargs = _layout_request_kwargs()
    kwargs[field] = value

    with pytest.raises(TechnicalParserProtocolError) as caught:
        encode_technical_parser_layout_request(**kwargs)

    _assert_code(caught, "PARSER_PROTOCOL_LAYOUT_REQUEST_INVALID")


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema":"technical-parser-layout-request-v1","schema":"duplicate"}',
        b'{"ocr_low_confidence_threshold":NaN}',
        b" " + encode_technical_parser_layout_request(**_layout_request_kwargs()),
        _canonical(
            {
                **json.loads(encode_technical_parser_layout_request(**_layout_request_kwargs())),
                "source_path": "C:/private/report.pdf",
            }
        ),
    ],
)
def test_layout_request_parser_rejects_noncanonical_or_extra_input(raw: bytes) -> None:
    with pytest.raises(TechnicalParserProtocolError) as caught:
        parse_technical_parser_layout_request(raw)

    _assert_code(caught, "PARSER_PROTOCOL_LAYOUT_REQUEST_INVALID")


def test_layout_request_parser_checks_byte_bound_before_json() -> None:
    with pytest.raises(TechnicalParserProtocolError) as caught:
        parse_technical_parser_layout_request(
            b"{" + b" " * TECHNICAL_PARSER_LAYOUT_REQUEST_MAX_BYTES
        )

    _assert_code(caught, "PARSER_PROTOCOL_LAYOUT_REQUEST_TOO_LARGE")


class _ChunkedReader(BytesIO):
    def read(self, size: int = -1) -> bytes:
        return super().read(min(size, 3) if size >= 0 else 3)


def test_success_frame_round_trips_exact_bytes_and_page_bindings() -> None:
    raw = _frame(_success_header())

    parsed = parse_technical_parser_page_frame(
        _ChunkedReader(raw),
        expected_page_number=1,
        expected_page_count=2,
        expected_page_width_points=Decimal(612),
        expected_page_height_points=Decimal(792),
    )

    assert isinstance(parsed, TechnicalParserPageSuccessFrame)
    assert parsed.status == "ok"
    assert parsed.page.number == 1
    assert parsed.page.count == 2
    assert parsed.page.width_points == Decimal(612)
    assert parsed.page.height_points == Decimal(792)
    assert parsed.evidence_bytes == _EVIDENCE
    assert parsed.image_bytes == _IMAGE
    assert parsed.evidence_sha256 == hashlib.sha256(_EVIDENCE).hexdigest()
    assert parsed.image_sha256 == hashlib.sha256(_IMAGE).hexdigest()
    # Framing deliberately does not duplicate the authoritative deep PNG validator.
    assert not parsed.image_bytes.startswith(b"\x89PNG")


def test_error_frame_has_an_exact_header_and_no_payload() -> None:
    parsed = parse_technical_parser_page_frame(_frame(_error_header()), expected_page_number=1)

    assert parsed == TechnicalParserPageErrorFrame(
        schema=TECHNICAL_PARSER_PAGE_FRAME_SCHEMA,
        status="error",
        page_number=1,
        retryable=True,
        error_code="PARSER_PAGE_TIMEOUT",
    )


@pytest.mark.parametrize(
    "header",
    [
        _success_header(extra="not-allowed"),
        _success_header(schema="wrong-schema"),
        _success_header(status="success"),
        _success_header(page_number=True),
        _success_header(evidence_size_bytes=0),
        _success_header(image_size_bytes="10"),
        _success_header(evidence_sha256="A" * 64),
        _success_header(image_width_pixels=4096, image_height_pixels=4096),
        _error_header(extra="not-allowed"),
        _error_header(retryable=1),
        _error_header(error_code="not_safe"),
        {**_success_header(), "status": "error"},
    ],
)
def test_frame_rejects_wrong_schema_keys_types_ranges_and_status_shape(
    header: dict[str, object],
) -> None:
    with pytest.raises(TechnicalParserProtocolError) as caught:
        parse_technical_parser_page_frame(_frame(header))

    _assert_code(caught, "PARSER_PROTOCOL_FRAME_HEADER_INVALID")


@pytest.mark.parametrize(
    "header_raw",
    [
        b'{"schema":"technical-parser-page-frame-v1","schema":"duplicate"}',
        b'{"schema":"technical-parser-page-frame-v1","status":"ok","page_width_points":NaN}',
        b"\xff",
        b" " + _canonical(_error_header()),
    ],
)
def test_frame_header_requires_strict_canonical_ascii_json(header_raw: bytes) -> None:
    with pytest.raises(TechnicalParserProtocolError) as caught:
        parse_technical_parser_page_frame(len(header_raw).to_bytes(4, "big") + header_raw)

    _assert_code(caught, "PARSER_PROTOCOL_FRAME_HEADER_INVALID")


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (b"\x00\x00", "PARSER_PROTOCOL_FRAME_TRUNCATED"),
        (b"\x00\x00\x00\x00", "PARSER_PROTOCOL_FRAME_HEADER_INVALID"),
        (
            (TECHNICAL_PARSER_HEADER_MAX_BYTES + 1).to_bytes(4, "big"),
            "PARSER_PROTOCOL_FRAME_HEADER_TOO_LARGE",
        ),
        (
            (10).to_bytes(4, "big") + b"{}",
            "PARSER_PROTOCOL_FRAME_TRUNCATED",
        ),
    ],
)
def test_frame_prefix_and_header_are_exactly_bounded(raw: bytes, code: str) -> None:
    with pytest.raises(TechnicalParserProtocolError) as caught:
        parse_technical_parser_page_frame(raw)

    _assert_code(caught, code)


def test_frame_rejects_declared_payloads_above_each_independent_bound() -> None:
    evidence_header = _success_header(evidence_size_bytes=TECHNICAL_PARSER_EVIDENCE_MAX_BYTES + 1)
    with pytest.raises(TechnicalParserProtocolError) as evidence_error:
        parse_technical_parser_page_frame(_frame(evidence_header, evidence=b"", image=b""))
    _assert_code(evidence_error, "PARSER_PROTOCOL_EVIDENCE_TOO_LARGE")

    image_header = _success_header(image_size_bytes=TECHNICAL_PARSER_PNG_MAX_BYTES + 1)
    with pytest.raises(TechnicalParserProtocolError) as image_error:
        parse_technical_parser_page_frame(_frame(image_header, evidence=b"", image=b""))
    _assert_code(image_error, "PARSER_PROTOCOL_IMAGE_TOO_LARGE")


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (
            _frame(_success_header(), evidence=_EVIDENCE[:-1], image=b""),
            "PARSER_PROTOCOL_FRAME_TRUNCATED",
        ),
        (
            _frame(_success_header(), evidence=b"X" * len(_EVIDENCE)),
            "PARSER_PROTOCOL_HASH_MISMATCH",
        ),
        (
            _frame(_success_header(), image=b"X" * len(_IMAGE)),
            "PARSER_PROTOCOL_HASH_MISMATCH",
        ),
        (
            _frame(_success_header(), trailing=b"x"),
            "PARSER_PROTOCOL_TRAILING_BYTES",
        ),
        (
            _frame(_error_header(), trailing=b"x"),
            "PARSER_PROTOCOL_TRAILING_BYTES",
        ),
    ],
)
def test_frame_rejects_truncation_hash_mismatch_and_trailing_bytes(
    raw: bytes,
    code: str,
) -> None:
    with pytest.raises(TechnicalParserProtocolError) as caught:
        parse_technical_parser_page_frame(raw)

    _assert_code(caught, code)


@pytest.mark.parametrize(
    "expectations",
    [
        {"expected_page_number": 2},
        {"expected_page_count": 1},
        {"expected_page_width_points": Decimal("612.1")},
        {"expected_page_height_points": Decimal("792.1")},
    ],
)
def test_success_frame_rejects_host_page_binding_mismatch(
    expectations: dict[str, object],
) -> None:
    with pytest.raises(TechnicalParserProtocolError) as caught:
        parse_technical_parser_page_frame(_frame(_success_header()), **expectations)

    _assert_code(caught, "PARSER_PROTOCOL_BINDING_MISMATCH")


def test_error_frame_rejects_host_page_binding_mismatch() -> None:
    with pytest.raises(TechnicalParserProtocolError) as caught:
        parse_technical_parser_page_frame(_frame(_error_header()), expected_page_number=2)

    _assert_code(caught, "PARSER_PROTOCOL_BINDING_MISMATCH")


def test_layout_validates_bindings_contiguous_pages_dimensions_and_raw_digest() -> None:
    raw = _canonical(_layout())

    parsed = parse_technical_parser_layout_result(raw, **_layout_kwargs())

    assert isinstance(parsed, TechnicalParserDocumentLayout)
    assert parsed.schema == TECHNICAL_PARSER_LAYOUT_SCHEMA
    assert parsed.technical_document_id == _DOCUMENT_ID
    assert parsed.source_sha256 == _SOURCE_SHA256
    assert parsed.source_size_bytes == _SOURCE_SIZE_BYTES
    assert parsed.extraction_policy == _POLICY
    assert parsed.extraction_policy_sha256 == _POLICY_SHA256
    assert parsed.worker_image_digest == _WORKER_DIGEST
    assert parsed.page_count == 2
    assert [page.number for page in parsed.pages] == [1, 2]
    assert all(page.count == 2 for page in parsed.pages)
    assert parsed.pages[1].width_points == Decimal("612.25")
    assert parsed.pages[1].height_points == Decimal("792.5")
    assert parsed.layout_sha256 == hashlib.sha256(raw).hexdigest()
    assert parsed.layout_size_bytes == len(raw)


@pytest.mark.parametrize(
    "raw",
    [
        json.dumps(_layout(), ensure_ascii=True).encode("ascii"),
        _canonical(_layout()) + b"\n",
        b" " + _canonical(_layout()),
    ],
)
def test_layout_success_requires_exact_canonical_ascii_full_buffer(raw: bytes) -> None:
    with pytest.raises(TechnicalParserProtocolError) as caught:
        parse_technical_parser_layout_result(raw, **_layout_kwargs())

    _assert_code(caught, "PARSER_PROTOCOL_LAYOUT_INVALID")


def test_layout_result_error_envelope_is_canonical_exact_and_payload_free() -> None:
    raw = _canonical(
        {
            "schema": TECHNICAL_PARSER_LAYOUT_SCHEMA,
            "status": "error",
            "retryable": True,
            "error_code": "PARSER_LAYOUT_TIMEOUT",
        }
    )

    parsed = parse_technical_parser_layout_result(raw, **_layout_kwargs())

    assert parsed == TechnicalParserLayoutErrorResult(
        schema=TECHNICAL_PARSER_LAYOUT_SCHEMA,
        status="error",
        retryable=True,
        error_code="PARSER_LAYOUT_TIMEOUT",
    )
    with pytest.raises(TechnicalParserProtocolError) as success_only:
        parse_technical_parser_layout(raw, **_layout_kwargs())
    _assert_code(success_only, "PARSER_PROTOCOL_LAYOUT_INVALID")


@pytest.mark.parametrize(
    "value",
    [
        {
            "schema": TECHNICAL_PARSER_LAYOUT_SCHEMA,
            "status": "ok",
            "retryable": True,
            "error_code": "PARSER_LAYOUT_TIMEOUT",
        },
        {
            "schema": TECHNICAL_PARSER_LAYOUT_SCHEMA,
            "status": "error",
            "retryable": 1,
            "error_code": "PARSER_LAYOUT_TIMEOUT",
        },
        {
            "schema": TECHNICAL_PARSER_LAYOUT_SCHEMA,
            "status": "error",
            "retryable": True,
            "error_code": "private/report.pdf",
        },
        {
            "schema": TECHNICAL_PARSER_LAYOUT_SCHEMA,
            "status": "error",
            "retryable": True,
            "error_code": "PARSER_LAYOUT_TIMEOUT",
            "detail": "not allowed",
        },
    ],
)
def test_layout_result_error_rejects_wrong_or_extra_fields(
    value: dict[str, object],
) -> None:
    with pytest.raises(TechnicalParserProtocolError) as caught:
        parse_technical_parser_layout_result(_canonical(value), **_layout_kwargs())

    _assert_code(caught, "PARSER_PROTOCOL_LAYOUT_INVALID")


def test_layout_result_error_rejects_noncanonical_or_trailing_bytes() -> None:
    value = {
        "schema": TECHNICAL_PARSER_LAYOUT_SCHEMA,
        "status": "error",
        "retryable": True,
        "error_code": "PARSER_LAYOUT_TIMEOUT",
    }
    for raw in (
        json.dumps(value).encode("ascii"),
        _canonical(value) + b"\n",
        _canonical(value) + _canonical(value),
    ):
        with pytest.raises(TechnicalParserProtocolError) as caught:
            parse_technical_parser_layout_result(raw, **_layout_kwargs())
        _assert_code(caught, "PARSER_PROTOCOL_LAYOUT_INVALID")


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema":"technical-parser-layout-v1","schema":"duplicate"}',
        b'{"schema":"technical-parser-layout-v1","page_count":NaN}',
        b"\xff",
        b"[]",
    ],
)
def test_layout_rejects_duplicate_nonfinite_non_utf8_and_non_object_json(raw: bytes) -> None:
    with pytest.raises(TechnicalParserProtocolError) as caught:
        parse_technical_parser_layout(raw, **_layout_kwargs())

    _assert_code(caught, "PARSER_PROTOCOL_LAYOUT_INVALID")


def test_layout_checks_the_byte_bound_before_json() -> None:
    raw = b"{" + b" " * TECHNICAL_PARSER_LAYOUT_MAX_BYTES

    with pytest.raises(TechnicalParserProtocolError) as caught:
        parse_technical_parser_layout(raw, **_layout_kwargs())

    _assert_code(caught, "PARSER_PROTOCOL_LAYOUT_TOO_LARGE")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("technical_document_id", "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"),
        ("source_sha256", "e" * 64),
        ("source_size_bytes", _SOURCE_SIZE_BYTES + 1),
        ("extraction_policy", "technical-extraction-v2"),
        ("extraction_policy_sha256", "e" * 64),
        ("worker_image_digest", "e" * 64),
    ],
)
def test_layout_rejects_every_host_binding_mismatch(field: str, value: object) -> None:
    kwargs = _layout_kwargs()
    kwargs[f"expected_{field}"] = value

    with pytest.raises(TechnicalParserProtocolError) as caught:
        parse_technical_parser_layout(_canonical(_layout()), **kwargs)

    _assert_code(caught, "PARSER_PROTOCOL_BINDING_MISMATCH")


@pytest.mark.parametrize(
    "layout",
    [
        _layout(extra="not-allowed"),
        _layout(schema="wrong-schema"),
        _layout(page_count=True),
        _layout(page_count=1),
        _layout(pages="not-a-list"),
        _layout(
            pages=[
                {"number": 1, "count": 2, "width_points": 612, "height_points": 792},
                {"number": 1, "count": 2, "width_points": 612, "height_points": 792},
            ]
        ),
        _layout(
            pages=[
                {"number": 2, "count": 2, "width_points": 612, "height_points": 792},
                {"number": 1, "count": 2, "width_points": 612, "height_points": 792},
            ]
        ),
        _layout(
            pages=[
                {"number": 1, "count": 1, "width_points": 612, "height_points": 792},
                {"number": 2, "count": 2, "width_points": 612, "height_points": 792},
            ]
        ),
        _layout(
            pages=[
                {"number": 1, "count": 2, "width_points": 0, "height_points": 792},
                {"number": 2, "count": 2, "width_points": 612, "height_points": 792},
            ]
        ),
        _layout(
            pages=[
                {
                    "number": 1,
                    "count": 2,
                    "width_points": 612.00001,
                    "height_points": 792,
                },
                {"number": 2, "count": 2, "width_points": 612, "height_points": 792},
            ]
        ),
        _layout(
            pages=[
                {
                    "number": 1,
                    "count": 2,
                    "width_points": 612,
                    "height_points": 792,
                    "extra": 1,
                },
                {"number": 2, "count": 2, "width_points": 612, "height_points": 792},
            ]
        ),
    ],
)
def test_layout_rejects_noncontiguous_duplicate_malformed_or_imprecise_pages(
    layout: dict[str, object],
) -> None:
    with pytest.raises(TechnicalParserProtocolError) as caught:
        parse_technical_parser_layout(_canonical(layout), **_layout_kwargs())

    _assert_code(caught, "PARSER_PROTOCOL_LAYOUT_INVALID")


def test_protocol_errors_never_include_untrusted_values() -> None:
    untrusted_path = "C:/customer/reports/private-report.pdf"
    with pytest.raises(TechnicalParserProtocolError) as caught:
        parse_technical_parser_page_frame(_frame(_error_header(error_code=untrusted_path)))

    _assert_code(caught, "PARSER_PROTOCOL_FRAME_HEADER_INVALID")
    assert untrusted_path not in str(caught.value)
