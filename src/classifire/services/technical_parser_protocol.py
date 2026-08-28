"""Engine-neutral framing for untrusted technical-document parser output.

This module defines bytes-on-the-wire contracts only. It deliberately does not
launch a parser, select a container runtime, retain artifacts, or grant technical
authority. The existing ``technical_page_evidence`` validator remains responsible
for deep evidence-packet and PNG validation after a frame has been decoded.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from decimal import Decimal, DecimalException
from io import BytesIO
from typing import BinaryIO, Literal, Never, TypeAlias, cast

from .technical_page_evidence import (
    TECHNICAL_PAGE_EVIDENCE_MAX_BYTES,
    TECHNICAL_PAGE_EVIDENCE_MAX_EDGE_PIXELS,
    TECHNICAL_PAGE_EVIDENCE_MAX_PAGE_IMAGE_BYTES,
    TECHNICAL_PAGE_EVIDENCE_MAX_PAGES,
    TECHNICAL_PAGE_EVIDENCE_MAX_PIXELS,
    TECHNICAL_PAGE_EVIDENCE_MAX_SOURCE_BYTES,
)

TECHNICAL_PARSER_REQUEST_SCHEMA = "technical-parser-request-v1"
TECHNICAL_PARSER_LAYOUT_REQUEST_SCHEMA = "technical-parser-layout-request-v1"
TECHNICAL_PARSER_PAGE_FRAME_SCHEMA = "technical-parser-page-frame-v1"
TECHNICAL_PARSER_LAYOUT_SCHEMA = "technical-parser-layout-v1"

TECHNICAL_PARSER_REQUEST_MAX_BYTES = 4096
TECHNICAL_PARSER_LAYOUT_REQUEST_MAX_BYTES = 4096
TECHNICAL_PARSER_HEADER_MAX_BYTES = 4096
TECHNICAL_PARSER_LAYOUT_MAX_BYTES = 128 * 1024
TECHNICAL_PARSER_EVIDENCE_MAX_BYTES = TECHNICAL_PAGE_EVIDENCE_MAX_BYTES
TECHNICAL_PARSER_PNG_MAX_BYTES = TECHNICAL_PAGE_EVIDENCE_MAX_PAGE_IMAGE_BYTES

_MAX_PAGE_POINTS = Decimal("20000")
_HEX_SHA256 = frozenset("0123456789abcdef")
_UUID4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_SAFE_POLICY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+/-]{0,99}$")
_SAFE_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,99}$")

_REQUEST_KEYS = frozenset(
    {
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
)
_LAYOUT_REQUEST_KEYS = frozenset(
    {
        "extraction_policy",
        "extraction_policy_sha256",
        "ocr_low_confidence_threshold",
        "schema",
        "source_sha256",
        "source_size_bytes",
        "technical_document_id",
        "worker_image_digest",
    }
)
_SUCCESS_HEADER_KEYS = frozenset(
    {
        "evidence_sha256",
        "evidence_size_bytes",
        "image_height_pixels",
        "image_sha256",
        "image_size_bytes",
        "image_width_pixels",
        "page_count",
        "page_height_points",
        "page_number",
        "page_width_points",
        "schema",
        "status",
    }
)
_ERROR_HEADER_KEYS = frozenset(
    {
        "error_code",
        "page_number",
        "retryable",
        "schema",
        "status",
    }
)
_LAYOUT_KEYS = frozenset(
    {
        "extraction_policy",
        "extraction_policy_sha256",
        "page_count",
        "pages",
        "schema",
        "source_sha256",
        "source_size_bytes",
        "technical_document_id",
        "worker_image_digest",
    }
)
_LAYOUT_PAGE_KEYS = frozenset({"count", "height_points", "number", "width_points"})
_LAYOUT_ERROR_KEYS = frozenset({"error_code", "retryable", "schema", "status"})

_ERROR_CODES = frozenset(
    {
        "PARSER_PROTOCOL_BINDING_MISMATCH",
        "PARSER_PROTOCOL_EVIDENCE_TOO_LARGE",
        "PARSER_PROTOCOL_FRAME_HEADER_INVALID",
        "PARSER_PROTOCOL_FRAME_HEADER_TOO_LARGE",
        "PARSER_PROTOCOL_FRAME_TRUNCATED",
        "PARSER_PROTOCOL_HASH_MISMATCH",
        "PARSER_PROTOCOL_IMAGE_TOO_LARGE",
        "PARSER_PROTOCOL_IO_ERROR",
        "PARSER_PROTOCOL_LAYOUT_INVALID",
        "PARSER_PROTOCOL_LAYOUT_REQUEST_INVALID",
        "PARSER_PROTOCOL_LAYOUT_REQUEST_TOO_LARGE",
        "PARSER_PROTOCOL_LAYOUT_TOO_LARGE",
        "PARSER_PROTOCOL_REQUEST_INVALID",
        "PARSER_PROTOCOL_REQUEST_TOO_LARGE",
        "PARSER_PROTOCOL_TRAILING_BYTES",
    }
)


class TechnicalParserProtocolError(ValueError):
    """A stable, path-free protocol rejection."""

    def __init__(self, code: str) -> None:
        if code not in _ERROR_CODES:
            raise ValueError("Unknown technical parser protocol error code")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class TechnicalParserRequest:
    schema: str
    technical_document_id: str
    source_sha256: str
    source_size_bytes: int
    page_number: int
    page_count: int
    page_width_points: Decimal
    page_height_points: Decimal
    layout_sha256: str
    extraction_policy: str
    extraction_policy_sha256: str
    worker_image_digest: str
    ocr_low_confidence_threshold: Decimal


@dataclass(frozen=True, slots=True)
class TechnicalParserLayoutRequest:
    schema: str
    technical_document_id: str
    source_sha256: str
    source_size_bytes: int
    extraction_policy: str
    extraction_policy_sha256: str
    worker_image_digest: str
    ocr_low_confidence_threshold: Decimal


@dataclass(frozen=True, slots=True)
class TechnicalParserPageDimensions:
    number: int
    count: int
    width_points: Decimal
    height_points: Decimal


@dataclass(frozen=True, slots=True)
class TechnicalParserDocumentLayout:
    schema: str
    technical_document_id: str
    source_sha256: str
    source_size_bytes: int
    extraction_policy: str
    extraction_policy_sha256: str
    worker_image_digest: str
    page_count: int
    pages: tuple[TechnicalParserPageDimensions, ...]
    layout_sha256: str
    layout_size_bytes: int


@dataclass(frozen=True, slots=True)
class TechnicalParserLayoutErrorResult:
    schema: str
    status: Literal["error"]
    retryable: bool
    error_code: str


TechnicalParserLayoutResult: TypeAlias = (
    TechnicalParserDocumentLayout | TechnicalParserLayoutErrorResult
)


@dataclass(frozen=True, slots=True)
class TechnicalParserPageSuccessFrame:
    schema: str
    status: Literal["ok"]
    page: TechnicalParserPageDimensions
    evidence_sha256: str
    evidence_size_bytes: int
    image_sha256: str
    image_size_bytes: int
    image_width_pixels: int
    image_height_pixels: int
    evidence_bytes: bytes
    image_bytes: bytes


@dataclass(frozen=True, slots=True)
class TechnicalParserPageErrorFrame:
    schema: str
    status: Literal["error"]
    page_number: int
    retryable: bool
    error_code: str


TechnicalParserPageFrame: TypeAlias = (
    TechnicalParserPageSuccessFrame | TechnicalParserPageErrorFrame
)


def _fail(code: str) -> Never:
    raise TechnicalParserProtocolError(code)


def _reject_nonfinite(_value: str) -> object:
    raise ValueError("non-finite JSON number")


def _parse_json_integer(value: str) -> int:
    if len(value) > 100:
        raise ValueError("JSON integer token is too long")
    return int(value)


def _parse_json_decimal(value: str) -> Decimal:
    if len(value) > 100:
        raise ValueError("JSON decimal token is too long")
    try:
        parsed = Decimal(value)
    except DecimalException as exc:
        raise ValueError("invalid JSON decimal") from exc
    if not parsed.is_finite() or abs(parsed.adjusted()) > 100_000:
        raise ValueError("JSON decimal is outside parser bounds")
    return parsed


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _strict_json_object(
    raw: bytes,
    *,
    maximum_bytes: int,
    invalid_code: str,
    too_large_code: str,
) -> dict[str, object]:
    if not isinstance(raw, bytes) or not raw:
        _fail(invalid_code)
    if len(raw) > maximum_bytes:
        _fail(too_large_code)
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
            parse_float=_parse_json_decimal,
            parse_int=_parse_json_integer,
        )
    except (
        DecimalException,
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ):
        _fail(invalid_code)
    if not isinstance(value, dict):
        _fail(invalid_code)
    return cast(dict[str, object], value)


def _canonical_decimal(value: Decimal) -> str:
    if value == 0:
        return "0"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _canonical_json_text(value: object) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        return _canonical_decimal(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True, separators=(",", ":"))
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_canonical_json_text(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("canonical JSON object keys must be strings")
        return (
            "{"
            + ",".join(
                _canonical_json_text(key) + ":" + _canonical_json_text(value[key])
                for key in sorted(value)
            )
            + "}"
        )
    raise TypeError("unsupported canonical JSON value")


def _canonical_json_bytes(value: object) -> bytes:
    return _canonical_json_text(value).encode("ascii")


def _object(value: object, keys: frozenset[str], *, code: str) -> dict[str, object]:
    if not isinstance(value, dict) or frozenset(value) != keys:
        _fail(code)
    return cast(dict[str, object], value)


def _integer(value: object, *, minimum: int, maximum: int, code: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        _fail(code)
    return value


def _decimal(
    value: object,
    *,
    minimum: Decimal,
    maximum: Decimal,
    decimal_places: int,
    code: str,
) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        _fail(code)
    try:
        parsed = Decimal(value)
        exponent = parsed.as_tuple().exponent
        valid_places = isinstance(exponent, int) and exponent >= -decimal_places
    except DecimalException:
        _fail(code)
    if not parsed.is_finite() or not minimum <= parsed <= maximum or not valid_places:
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


def _policy(value: object, *, code: str) -> str:
    if not isinstance(value, str) or _SAFE_POLICY.fullmatch(value) is None:
        _fail(code)
    return value


def _error_code(value: object, *, code: str) -> str:
    if not isinstance(value, str) or _SAFE_ERROR_CODE.fullmatch(value) is None:
        _fail(code)
    return value


def _payload_size(value: object, *, maximum: int, too_large_code: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        _fail("PARSER_PROTOCOL_FRAME_HEADER_INVALID")
    if value > maximum:
        _fail(too_large_code)
    return value


def _page_dimensions(
    value: dict[str, object],
    *,
    code: str,
) -> TechnicalParserPageDimensions:
    number = _integer(
        value["number"],
        minimum=1,
        maximum=TECHNICAL_PAGE_EVIDENCE_MAX_PAGES,
        code=code,
    )
    count = _integer(
        value["count"],
        minimum=1,
        maximum=TECHNICAL_PAGE_EVIDENCE_MAX_PAGES,
        code=code,
    )
    if number > count:
        _fail(code)
    return TechnicalParserPageDimensions(
        number=number,
        count=count,
        width_points=_decimal(
            value["width_points"],
            minimum=Decimal("0.0001"),
            maximum=_MAX_PAGE_POINTS,
            decimal_places=4,
            code=code,
        ),
        height_points=_decimal(
            value["height_points"],
            minimum=Decimal("0.0001"),
            maximum=_MAX_PAGE_POINTS,
            decimal_places=4,
            code=code,
        ),
    )


def _request_from_object(value: dict[str, object]) -> TechnicalParserRequest:
    item = _object(value, _REQUEST_KEYS, code="PARSER_PROTOCOL_REQUEST_INVALID")
    if item["schema"] != TECHNICAL_PARSER_REQUEST_SCHEMA:
        _fail("PARSER_PROTOCOL_REQUEST_INVALID")
    page = _page_dimensions(
        {
            "count": item["page_count"],
            "height_points": item["page_height_points"],
            "number": item["page_number"],
            "width_points": item["page_width_points"],
        },
        code="PARSER_PROTOCOL_REQUEST_INVALID",
    )
    return TechnicalParserRequest(
        schema=TECHNICAL_PARSER_REQUEST_SCHEMA,
        technical_document_id=_uuid4(
            item["technical_document_id"], code="PARSER_PROTOCOL_REQUEST_INVALID"
        ),
        source_sha256=_sha256(item["source_sha256"], code="PARSER_PROTOCOL_REQUEST_INVALID"),
        source_size_bytes=_integer(
            item["source_size_bytes"],
            minimum=1,
            maximum=TECHNICAL_PAGE_EVIDENCE_MAX_SOURCE_BYTES,
            code="PARSER_PROTOCOL_REQUEST_INVALID",
        ),
        page_number=page.number,
        page_count=page.count,
        page_width_points=page.width_points,
        page_height_points=page.height_points,
        layout_sha256=_sha256(item["layout_sha256"], code="PARSER_PROTOCOL_REQUEST_INVALID"),
        extraction_policy=_policy(
            item["extraction_policy"], code="PARSER_PROTOCOL_REQUEST_INVALID"
        ),
        extraction_policy_sha256=_sha256(
            item["extraction_policy_sha256"], code="PARSER_PROTOCOL_REQUEST_INVALID"
        ),
        worker_image_digest=_sha256(
            item["worker_image_digest"], code="PARSER_PROTOCOL_REQUEST_INVALID"
        ),
        ocr_low_confidence_threshold=_decimal(
            item["ocr_low_confidence_threshold"],
            minimum=Decimal(0),
            maximum=Decimal(100),
            decimal_places=2,
            code="PARSER_PROTOCOL_REQUEST_INVALID",
        ),
    )


def _request_payload(request: TechnicalParserRequest) -> dict[str, object]:
    return {
        "extraction_policy": request.extraction_policy,
        "extraction_policy_sha256": request.extraction_policy_sha256,
        "layout_sha256": request.layout_sha256,
        "ocr_low_confidence_threshold": request.ocr_low_confidence_threshold,
        "page_count": request.page_count,
        "page_height_points": request.page_height_points,
        "page_number": request.page_number,
        "page_width_points": request.page_width_points,
        "schema": request.schema,
        "source_sha256": request.source_sha256,
        "source_size_bytes": request.source_size_bytes,
        "technical_document_id": request.technical_document_id,
        "worker_image_digest": request.worker_image_digest,
    }


def encode_technical_parser_request(
    *,
    technical_document_id: str,
    source_sha256: str,
    source_size_bytes: int,
    page_number: int,
    page_count: int,
    page_width_points: Decimal,
    page_height_points: Decimal,
    layout_sha256: str,
    extraction_policy: str,
    extraction_policy_sha256: str,
    worker_image_digest: str,
    ocr_low_confidence_threshold: Decimal,
) -> bytes:
    """Encode one canonical, path-free parser request without launching a worker."""

    request = _request_from_object(
        {
            "extraction_policy": extraction_policy,
            "extraction_policy_sha256": extraction_policy_sha256,
            "layout_sha256": layout_sha256,
            "ocr_low_confidence_threshold": ocr_low_confidence_threshold,
            "page_count": page_count,
            "page_height_points": page_height_points,
            "page_number": page_number,
            "page_width_points": page_width_points,
            "schema": TECHNICAL_PARSER_REQUEST_SCHEMA,
            "source_sha256": source_sha256,
            "source_size_bytes": source_size_bytes,
            "technical_document_id": technical_document_id,
            "worker_image_digest": worker_image_digest,
        }
    )
    encoded = _canonical_json_bytes(_request_payload(request))
    if len(encoded) > TECHNICAL_PARSER_REQUEST_MAX_BYTES:
        _fail("PARSER_PROTOCOL_REQUEST_TOO_LARGE")
    return encoded


def parse_technical_parser_request(raw: bytes) -> TechnicalParserRequest:
    """Validate the worker-side request contract without accessing source files."""

    value = _strict_json_object(
        raw,
        maximum_bytes=TECHNICAL_PARSER_REQUEST_MAX_BYTES,
        invalid_code="PARSER_PROTOCOL_REQUEST_INVALID",
        too_large_code="PARSER_PROTOCOL_REQUEST_TOO_LARGE",
    )
    request = _request_from_object(value)
    if not raw.isascii() or raw != _canonical_json_bytes(_request_payload(request)):
        _fail("PARSER_PROTOCOL_REQUEST_INVALID")
    return request


def _layout_request_from_object(value: dict[str, object]) -> TechnicalParserLayoutRequest:
    code = "PARSER_PROTOCOL_LAYOUT_REQUEST_INVALID"
    item = _object(value, _LAYOUT_REQUEST_KEYS, code=code)
    if item["schema"] != TECHNICAL_PARSER_LAYOUT_REQUEST_SCHEMA:
        _fail(code)
    return TechnicalParserLayoutRequest(
        schema=TECHNICAL_PARSER_LAYOUT_REQUEST_SCHEMA,
        technical_document_id=_uuid4(item["technical_document_id"], code=code),
        source_sha256=_sha256(item["source_sha256"], code=code),
        source_size_bytes=_integer(
            item["source_size_bytes"],
            minimum=1,
            maximum=TECHNICAL_PAGE_EVIDENCE_MAX_SOURCE_BYTES,
            code=code,
        ),
        extraction_policy=_policy(item["extraction_policy"], code=code),
        extraction_policy_sha256=_sha256(item["extraction_policy_sha256"], code=code),
        worker_image_digest=_sha256(item["worker_image_digest"], code=code),
        ocr_low_confidence_threshold=_decimal(
            item["ocr_low_confidence_threshold"],
            minimum=Decimal(0),
            maximum=Decimal(100),
            decimal_places=2,
            code=code,
        ),
    )


def _layout_request_payload(request: TechnicalParserLayoutRequest) -> dict[str, object]:
    return {
        "extraction_policy": request.extraction_policy,
        "extraction_policy_sha256": request.extraction_policy_sha256,
        "ocr_low_confidence_threshold": request.ocr_low_confidence_threshold,
        "schema": request.schema,
        "source_sha256": request.source_sha256,
        "source_size_bytes": request.source_size_bytes,
        "technical_document_id": request.technical_document_id,
        "worker_image_digest": request.worker_image_digest,
    }


def encode_technical_parser_layout_request(
    *,
    technical_document_id: str,
    source_sha256: str,
    source_size_bytes: int,
    extraction_policy: str,
    extraction_policy_sha256: str,
    worker_image_digest: str,
    ocr_low_confidence_threshold: Decimal,
) -> bytes:
    """Encode one canonical, path-free request for document layout discovery."""

    request = _layout_request_from_object(
        {
            "extraction_policy": extraction_policy,
            "extraction_policy_sha256": extraction_policy_sha256,
            "ocr_low_confidence_threshold": ocr_low_confidence_threshold,
            "schema": TECHNICAL_PARSER_LAYOUT_REQUEST_SCHEMA,
            "source_sha256": source_sha256,
            "source_size_bytes": source_size_bytes,
            "technical_document_id": technical_document_id,
            "worker_image_digest": worker_image_digest,
        }
    )
    encoded = _canonical_json_bytes(_layout_request_payload(request))
    if len(encoded) > TECHNICAL_PARSER_LAYOUT_REQUEST_MAX_BYTES:
        _fail("PARSER_PROTOCOL_LAYOUT_REQUEST_TOO_LARGE")
    return encoded


def parse_technical_parser_layout_request(raw: bytes) -> TechnicalParserLayoutRequest:
    """Validate the exact worker-side layout request without opening a source."""

    value = _strict_json_object(
        raw,
        maximum_bytes=TECHNICAL_PARSER_LAYOUT_REQUEST_MAX_BYTES,
        invalid_code="PARSER_PROTOCOL_LAYOUT_REQUEST_INVALID",
        too_large_code="PARSER_PROTOCOL_LAYOUT_REQUEST_TOO_LARGE",
    )
    request = _layout_request_from_object(value)
    if not raw.isascii() or raw != _canonical_json_bytes(_layout_request_payload(request)):
        _fail("PARSER_PROTOCOL_LAYOUT_REQUEST_INVALID")
    return request


def _stream(value: bytes | BinaryIO) -> BinaryIO:
    if isinstance(value, bytes):
        return BytesIO(value)
    if not callable(getattr(value, "read", None)):
        _fail("PARSER_PROTOCOL_IO_ERROR")
    return value


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    result = bytearray(size)
    offset = 0
    remaining = size
    while remaining:
        try:
            chunk = stream.read(remaining)
        except Exception:
            _fail("PARSER_PROTOCOL_IO_ERROR")
        if not isinstance(chunk, bytes) or len(chunk) > remaining:
            _fail("PARSER_PROTOCOL_IO_ERROR")
        if not chunk:
            _fail("PARSER_PROTOCOL_FRAME_TRUNCATED")
        result[offset : offset + len(chunk)] = chunk
        offset += len(chunk)
        remaining -= len(chunk)
    return bytes(result)


def _require_eof(stream: BinaryIO) -> None:
    try:
        trailing = stream.read(1)
    except Exception:
        _fail("PARSER_PROTOCOL_IO_ERROR")
    if not isinstance(trailing, bytes) or len(trailing) > 1:
        _fail("PARSER_PROTOCOL_IO_ERROR")
    if trailing:
        _fail("PARSER_PROTOCOL_TRAILING_BYTES")


def _require_canonical_json(
    raw: bytes,
    value: dict[str, object],
    *,
    code: str,
) -> None:
    try:
        canonical = _canonical_json_bytes(value)
    except (TypeError, ValueError):
        _fail(code)
    if not raw.isascii() or not hmac.compare_digest(raw, canonical):
        _fail(code)


def _require_canonical_header(raw: bytes, value: dict[str, object]) -> None:
    _require_canonical_json(
        raw,
        value,
        code="PARSER_PROTOCOL_FRAME_HEADER_INVALID",
    )


def _expected_page_binding(
    page: TechnicalParserPageDimensions,
    *,
    expected_page_number: int | None,
    expected_page_count: int | None,
    expected_page_width_points: Decimal | None,
    expected_page_height_points: Decimal | None,
) -> None:
    expectations = (
        (expected_page_number, page.number, 1, TECHNICAL_PAGE_EVIDENCE_MAX_PAGES, 0),
        (expected_page_count, page.count, 1, TECHNICAL_PAGE_EVIDENCE_MAX_PAGES, 0),
    )
    for expected, actual, minimum, maximum, _places in expectations:
        if expected is not None and (
            _integer(
                expected,
                minimum=minimum,
                maximum=maximum,
                code="PARSER_PROTOCOL_BINDING_MISMATCH",
            )
            != actual
        ):
            _fail("PARSER_PROTOCOL_BINDING_MISMATCH")
    decimal_expectations = (
        (expected_page_width_points, page.width_points),
        (expected_page_height_points, page.height_points),
    )
    for expected_decimal, actual_decimal in decimal_expectations:
        if expected_decimal is not None and (
            _decimal(
                expected_decimal,
                minimum=Decimal("0.0001"),
                maximum=_MAX_PAGE_POINTS,
                decimal_places=4,
                code="PARSER_PROTOCOL_BINDING_MISMATCH",
            )
            != actual_decimal
        ):
            _fail("PARSER_PROTOCOL_BINDING_MISMATCH")


def parse_technical_parser_page_frame(
    framed: bytes | BinaryIO,
    *,
    expected_page_number: int | None = None,
    expected_page_count: int | None = None,
    expected_page_width_points: Decimal | None = None,
    expected_page_height_points: Decimal | None = None,
) -> TechnicalParserPageFrame:
    """Decode exactly one bounded page frame and require immediate EOF."""

    stream = _stream(framed)
    header_size = int.from_bytes(_read_exact(stream, 4), "big")
    if header_size == 0:
        _fail("PARSER_PROTOCOL_FRAME_HEADER_INVALID")
    if header_size > TECHNICAL_PARSER_HEADER_MAX_BYTES:
        _fail("PARSER_PROTOCOL_FRAME_HEADER_TOO_LARGE")
    header_raw = _read_exact(stream, header_size)
    header = _strict_json_object(
        header_raw,
        maximum_bytes=TECHNICAL_PARSER_HEADER_MAX_BYTES,
        invalid_code="PARSER_PROTOCOL_FRAME_HEADER_INVALID",
        too_large_code="PARSER_PROTOCOL_FRAME_HEADER_TOO_LARGE",
    )
    if header.get("schema") != TECHNICAL_PARSER_PAGE_FRAME_SCHEMA:
        _fail("PARSER_PROTOCOL_FRAME_HEADER_INVALID")
    status = header.get("status")
    if status == "error":
        item = _object(
            header,
            _ERROR_HEADER_KEYS,
            code="PARSER_PROTOCOL_FRAME_HEADER_INVALID",
        )
        page_number = _integer(
            item["page_number"],
            minimum=1,
            maximum=TECHNICAL_PAGE_EVIDENCE_MAX_PAGES,
            code="PARSER_PROTOCOL_FRAME_HEADER_INVALID",
        )
        retryable = item["retryable"]
        if not isinstance(retryable, bool):
            _fail("PARSER_PROTOCOL_FRAME_HEADER_INVALID")
        error_code = _error_code(
            item["error_code"],
            code="PARSER_PROTOCOL_FRAME_HEADER_INVALID",
        )
        _require_canonical_header(header_raw, item)
        if expected_page_number is not None and page_number != _integer(
            expected_page_number,
            minimum=1,
            maximum=TECHNICAL_PAGE_EVIDENCE_MAX_PAGES,
            code="PARSER_PROTOCOL_BINDING_MISMATCH",
        ):
            _fail("PARSER_PROTOCOL_BINDING_MISMATCH")
        _require_eof(stream)
        return TechnicalParserPageErrorFrame(
            schema=TECHNICAL_PARSER_PAGE_FRAME_SCHEMA,
            status="error",
            page_number=page_number,
            retryable=retryable,
            error_code=error_code,
        )
    if status != "ok":
        _fail("PARSER_PROTOCOL_FRAME_HEADER_INVALID")

    item = _object(
        header,
        _SUCCESS_HEADER_KEYS,
        code="PARSER_PROTOCOL_FRAME_HEADER_INVALID",
    )
    page = _page_dimensions(
        {
            "count": item["page_count"],
            "height_points": item["page_height_points"],
            "number": item["page_number"],
            "width_points": item["page_width_points"],
        },
        code="PARSER_PROTOCOL_FRAME_HEADER_INVALID",
    )
    evidence_size = _payload_size(
        item["evidence_size_bytes"],
        maximum=TECHNICAL_PARSER_EVIDENCE_MAX_BYTES,
        too_large_code="PARSER_PROTOCOL_EVIDENCE_TOO_LARGE",
    )
    image_size = _payload_size(
        item["image_size_bytes"],
        maximum=TECHNICAL_PARSER_PNG_MAX_BYTES,
        too_large_code="PARSER_PROTOCOL_IMAGE_TOO_LARGE",
    )
    evidence_sha256 = _sha256(item["evidence_sha256"], code="PARSER_PROTOCOL_FRAME_HEADER_INVALID")
    image_sha256 = _sha256(item["image_sha256"], code="PARSER_PROTOCOL_FRAME_HEADER_INVALID")
    image_width = _integer(
        item["image_width_pixels"],
        minimum=1,
        maximum=TECHNICAL_PAGE_EVIDENCE_MAX_EDGE_PIXELS,
        code="PARSER_PROTOCOL_FRAME_HEADER_INVALID",
    )
    image_height = _integer(
        item["image_height_pixels"],
        minimum=1,
        maximum=TECHNICAL_PAGE_EVIDENCE_MAX_EDGE_PIXELS,
        code="PARSER_PROTOCOL_FRAME_HEADER_INVALID",
    )
    if image_width * image_height > TECHNICAL_PAGE_EVIDENCE_MAX_PIXELS:
        _fail("PARSER_PROTOCOL_FRAME_HEADER_INVALID")
    _require_canonical_header(header_raw, item)
    _expected_page_binding(
        page,
        expected_page_number=expected_page_number,
        expected_page_count=expected_page_count,
        expected_page_width_points=expected_page_width_points,
        expected_page_height_points=expected_page_height_points,
    )
    evidence_bytes = _read_exact(stream, evidence_size)
    image_bytes = _read_exact(stream, image_size)
    _require_eof(stream)
    if not hmac.compare_digest(hashlib.sha256(evidence_bytes).hexdigest(), evidence_sha256):
        _fail("PARSER_PROTOCOL_HASH_MISMATCH")
    if not hmac.compare_digest(hashlib.sha256(image_bytes).hexdigest(), image_sha256):
        _fail("PARSER_PROTOCOL_HASH_MISMATCH")
    return TechnicalParserPageSuccessFrame(
        schema=TECHNICAL_PARSER_PAGE_FRAME_SCHEMA,
        status="ok",
        page=page,
        evidence_sha256=evidence_sha256,
        evidence_size_bytes=evidence_size,
        image_sha256=image_sha256,
        image_size_bytes=image_size,
        image_width_pixels=image_width,
        image_height_pixels=image_height,
        evidence_bytes=evidence_bytes,
        image_bytes=image_bytes,
    )


def validate_technical_parser_layout(
    raw: bytes,
    *,
    expected_technical_document_id: str,
    expected_source_sha256: str,
    expected_source_size_bytes: int,
    expected_extraction_policy: str,
    expected_extraction_policy_sha256: str,
    expected_worker_image_digest: str,
) -> TechnicalParserDocumentLayout:
    """Validate one bounded document layout against exact host-side bindings."""

    value = _strict_json_object(
        raw,
        maximum_bytes=TECHNICAL_PARSER_LAYOUT_MAX_BYTES,
        invalid_code="PARSER_PROTOCOL_LAYOUT_INVALID",
        too_large_code="PARSER_PROTOCOL_LAYOUT_TOO_LARGE",
    )
    item = _object(value, _LAYOUT_KEYS, code="PARSER_PROTOCOL_LAYOUT_INVALID")
    if item["schema"] != TECHNICAL_PARSER_LAYOUT_SCHEMA:
        _fail("PARSER_PROTOCOL_LAYOUT_INVALID")
    technical_document_id = _uuid4(
        item["technical_document_id"], code="PARSER_PROTOCOL_LAYOUT_INVALID"
    )
    source_sha256 = _sha256(item["source_sha256"], code="PARSER_PROTOCOL_LAYOUT_INVALID")
    source_size_bytes = _integer(
        item["source_size_bytes"],
        minimum=1,
        maximum=TECHNICAL_PAGE_EVIDENCE_MAX_SOURCE_BYTES,
        code="PARSER_PROTOCOL_LAYOUT_INVALID",
    )
    extraction_policy = _policy(item["extraction_policy"], code="PARSER_PROTOCOL_LAYOUT_INVALID")
    extraction_policy_sha256 = _sha256(
        item["extraction_policy_sha256"], code="PARSER_PROTOCOL_LAYOUT_INVALID"
    )
    worker_image_digest = _sha256(
        item["worker_image_digest"], code="PARSER_PROTOCOL_LAYOUT_INVALID"
    )
    expected_bindings = (
        (
            technical_document_id,
            _uuid4(
                expected_technical_document_id,
                code="PARSER_PROTOCOL_BINDING_MISMATCH",
            ),
        ),
        (
            source_sha256,
            _sha256(expected_source_sha256, code="PARSER_PROTOCOL_BINDING_MISMATCH"),
        ),
        (
            source_size_bytes,
            _integer(
                expected_source_size_bytes,
                minimum=1,
                maximum=TECHNICAL_PAGE_EVIDENCE_MAX_SOURCE_BYTES,
                code="PARSER_PROTOCOL_BINDING_MISMATCH",
            ),
        ),
        (
            extraction_policy,
            _policy(
                expected_extraction_policy,
                code="PARSER_PROTOCOL_BINDING_MISMATCH",
            ),
        ),
        (
            extraction_policy_sha256,
            _sha256(
                expected_extraction_policy_sha256,
                code="PARSER_PROTOCOL_BINDING_MISMATCH",
            ),
        ),
        (
            worker_image_digest,
            _sha256(
                expected_worker_image_digest,
                code="PARSER_PROTOCOL_BINDING_MISMATCH",
            ),
        ),
    )
    if any(actual != expected for actual, expected in expected_bindings):
        _fail("PARSER_PROTOCOL_BINDING_MISMATCH")

    page_count = _integer(
        item["page_count"],
        minimum=1,
        maximum=TECHNICAL_PAGE_EVIDENCE_MAX_PAGES,
        code="PARSER_PROTOCOL_LAYOUT_INVALID",
    )
    raw_pages = item["pages"]
    if not isinstance(raw_pages, list) or len(raw_pages) != page_count:
        _fail("PARSER_PROTOCOL_LAYOUT_INVALID")
    pages: list[TechnicalParserPageDimensions] = []
    for expected_number, raw_page in enumerate(raw_pages, start=1):
        page_item = _object(
            raw_page,
            _LAYOUT_PAGE_KEYS,
            code="PARSER_PROTOCOL_LAYOUT_INVALID",
        )
        page = _page_dimensions(page_item, code="PARSER_PROTOCOL_LAYOUT_INVALID")
        if page.number != expected_number or page.count != page_count:
            _fail("PARSER_PROTOCOL_LAYOUT_INVALID")
        pages.append(page)
    _require_canonical_json(
        raw,
        item,
        code="PARSER_PROTOCOL_LAYOUT_INVALID",
    )
    return TechnicalParserDocumentLayout(
        schema=TECHNICAL_PARSER_LAYOUT_SCHEMA,
        technical_document_id=technical_document_id,
        source_sha256=source_sha256,
        source_size_bytes=source_size_bytes,
        extraction_policy=extraction_policy,
        extraction_policy_sha256=extraction_policy_sha256,
        worker_image_digest=worker_image_digest,
        page_count=page_count,
        pages=tuple(pages),
        layout_sha256=hashlib.sha256(raw).hexdigest(),
        layout_size_bytes=len(raw),
    )


def parse_technical_parser_layout_result(
    raw: bytes,
    *,
    expected_technical_document_id: str,
    expected_source_sha256: str,
    expected_source_size_bytes: int,
    expected_extraction_policy: str,
    expected_extraction_policy_sha256: str,
    expected_worker_image_digest: str,
) -> TechnicalParserLayoutResult:
    """Parse exactly one complete canonical layout success or error result."""

    value = _strict_json_object(
        raw,
        maximum_bytes=TECHNICAL_PARSER_LAYOUT_MAX_BYTES,
        invalid_code="PARSER_PROTOCOL_LAYOUT_INVALID",
        too_large_code="PARSER_PROTOCOL_LAYOUT_TOO_LARGE",
    )
    if "status" not in value:
        return validate_technical_parser_layout(
            raw,
            expected_technical_document_id=expected_technical_document_id,
            expected_source_sha256=expected_source_sha256,
            expected_source_size_bytes=expected_source_size_bytes,
            expected_extraction_policy=expected_extraction_policy,
            expected_extraction_policy_sha256=expected_extraction_policy_sha256,
            expected_worker_image_digest=expected_worker_image_digest,
        )

    item = _object(value, _LAYOUT_ERROR_KEYS, code="PARSER_PROTOCOL_LAYOUT_INVALID")
    if item["schema"] != TECHNICAL_PARSER_LAYOUT_SCHEMA or item["status"] != "error":
        _fail("PARSER_PROTOCOL_LAYOUT_INVALID")
    retryable = item["retryable"]
    if not isinstance(retryable, bool):
        _fail("PARSER_PROTOCOL_LAYOUT_INVALID")
    error_code = _error_code(
        item["error_code"],
        code="PARSER_PROTOCOL_LAYOUT_INVALID",
    )
    _require_canonical_json(
        raw,
        item,
        code="PARSER_PROTOCOL_LAYOUT_INVALID",
    )
    return TechnicalParserLayoutErrorResult(
        schema=TECHNICAL_PARSER_LAYOUT_SCHEMA,
        status="error",
        retryable=retryable,
        error_code=error_code,
    )


parse_technical_parser_layout = validate_technical_parser_layout


__all__ = [
    "TECHNICAL_PARSER_EVIDENCE_MAX_BYTES",
    "TECHNICAL_PARSER_HEADER_MAX_BYTES",
    "TECHNICAL_PARSER_LAYOUT_MAX_BYTES",
    "TECHNICAL_PARSER_LAYOUT_REQUEST_MAX_BYTES",
    "TECHNICAL_PARSER_LAYOUT_REQUEST_SCHEMA",
    "TECHNICAL_PARSER_LAYOUT_SCHEMA",
    "TECHNICAL_PARSER_PAGE_FRAME_SCHEMA",
    "TECHNICAL_PARSER_PNG_MAX_BYTES",
    "TECHNICAL_PARSER_REQUEST_MAX_BYTES",
    "TECHNICAL_PARSER_REQUEST_SCHEMA",
    "TechnicalParserDocumentLayout",
    "TechnicalParserLayoutErrorResult",
    "TechnicalParserLayoutRequest",
    "TechnicalParserLayoutResult",
    "TechnicalParserPageDimensions",
    "TechnicalParserPageErrorFrame",
    "TechnicalParserPageFrame",
    "TechnicalParserPageSuccessFrame",
    "TechnicalParserProtocolError",
    "TechnicalParserRequest",
    "encode_technical_parser_layout_request",
    "encode_technical_parser_request",
    "parse_technical_parser_layout",
    "parse_technical_parser_layout_request",
    "parse_technical_parser_layout_result",
    "parse_technical_parser_page_frame",
    "parse_technical_parser_request",
    "validate_technical_parser_layout",
]
