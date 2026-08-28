"""Strict, authority-neutral authoring of field-level technical intake Drafts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, NoReturn
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..config import get_settings
from ..models import (
    StoredFile,
    TechnicalDocument,
    TechnicalIntakeDraft,
    User,
)
from .storage import StoredFileBinding, StoredFileBindingError, require_stored_file_binding

TECHNICAL_INTAKE_DRAFT_SCHEMA = "technical-intake-draft-v1"
TECHNICAL_INTAKE_PAYLOAD_SCHEMA = "technical-intake-payload-v1"
TECHNICAL_INTAKE_PAYLOAD_MAX_BYTES = 1024 * 1024
TECHNICAL_INTAKE_MAX_FIELDS = 500
TECHNICAL_INTAKE_MAX_LOCATORS = 500
TECHNICAL_INTAKE_MAX_LINKS = 5_000

TECHNICAL_INTAKE_FIELD_KEYS = frozenset(
    {
        "annular_gap_max_mm",
        "annular_gap_min_mm",
        "dependencies",
        "edge_distance_rules",
        "effective_date",
        "expiry_date",
        "fixing_rules",
        "frl",
        "hard_exclusions",
        "installation_face",
        "insulation_thickness_mm",
        "insulation_type",
        "jurisdiction",
        "manufacturer",
        "maximum_service_size_mm",
        "maximum_substrate_thickness_mm",
        "minimum_service_size_mm",
        "minimum_substrate_thickness_mm",
        "opening_dimensions",
        "opening_type",
        "orientation",
        "permitted_service_quantity",
        "product_family",
        "service_material",
        "service_spacing_rules",
        "service_type",
        "substrate_type",
        "support_rules",
        "system_id",
        "variant_id",
    }
)
TECHNICAL_INTAKE_SEMANTICS = frozenset(
    {
        "continuous_range",
        "disjoint_set",
        "enumerated",
        "exact",
        "maximum",
        "minimum",
        "nominal",
        "nominal_bore",
        "outside_diameter",
        "wall_thickness",
    }
)
TECHNICAL_INTAKE_FACT_STATES = frozenset(
    {"Confirmed", "Inferred", "Provisional", "Unresolved"}
)
TECHNICAL_INTAKE_EVIDENCE_ROLES = frozenset(
    {
        "comparison",
        "conclusion",
        "conflicting",
        "derived_reasoning",
        "direct",
        "governing",
        "superseded",
    }
)
TECHNICAL_INTAKE_VISUAL_VERIFICATION_STATES = frozenset(
    {"not_required", "required"}
)

_AUTHORABLE_DOCUMENT_STATUSES = frozenset({"approved", "draft", "in_review"})
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_REGION_DECIMAL_RE = re.compile(r"(?:0(?:\.\d{1,12})?|1(?:\.0{1,12})?)\Z")
_FIELD_KEYS = frozenset(
    {
        "fact_state",
        "field_key",
        "limitation",
        "material",
        "normalized_value",
        "ordinal",
        "raw_value",
        "row_id",
        "semantics",
        "unit",
    }
)
_LOCATOR_TEXT_KEYS = (
    "printed_page",
    "section",
    "clause",
    "table",
    "row",
    "column",
    "footnote",
    "figure",
    "drawing",
    "specimen",
    "option",
    "callout",
)
_LOCATOR_KEYS = frozenset(
    {
        "excerpt",
        "physical_page",
        "region",
        "row_id",
        "source_sha256",
        "source_size_bytes",
        "technical_document_id",
        "visual_verification",
        *_LOCATOR_TEXT_KEYS,
    }
)
_REGION_KEYS = frozenset({"x0", "x1", "y0", "y1"})
_LINK_KEYS = frozenset(
    {"evidence_role", "field_row_id", "locator_row_id", "row_id"}
)
_SUPPORTING_EVIDENCE_ROLES = TECHNICAL_INTAKE_EVIDENCE_ROLES - {
    "conflicting",
    "superseded",
}
_ERROR_CODES = frozenset(
    {
        "TECHNICAL_INTAKE_DRAFT_ACTOR_INVALID",
        "TECHNICAL_INTAKE_DRAFT_CONFIRMED_FORBIDDEN",
        "TECHNICAL_INTAKE_DRAFT_DOCUMENT_NOT_AUTHORABLE",
        "TECHNICAL_INTAKE_DRAFT_DOCUMENT_NOT_FOUND",
        "TECHNICAL_INTAKE_DRAFT_DUPLICATE_KEY",
        "TECHNICAL_INTAKE_DRAFT_EVIDENCE_INVALID",
        "TECHNICAL_INTAKE_DRAFT_FIELD_INVALID",
        "TECHNICAL_INTAKE_DRAFT_ID_INVALID",
        "TECHNICAL_INTAKE_DRAFT_JSON_INVALID",
        "TECHNICAL_INTAKE_DRAFT_LINK_INVALID",
        "TECHNICAL_INTAKE_DRAFT_LOCATOR_INVALID",
        "TECHNICAL_INTAKE_DRAFT_NOT_FOUND",
        "TECHNICAL_INTAKE_DRAFT_PAYLOAD_TOO_LARGE",
        "TECHNICAL_INTAKE_DRAFT_PERSISTENCE_CONFLICT",
        "TECHNICAL_INTAKE_DRAFT_REASON_INVALID",
        "TECHNICAL_INTAKE_DRAFT_SOURCE_FILE_INVALID",
        "TECHNICAL_INTAKE_DRAFT_STALE",
        "TECHNICAL_INTAKE_DRAFT_STRUCTURE_INVALID",
    }
)
_ERROR_STATUS = {
    "TECHNICAL_INTAKE_DRAFT_ACTOR_INVALID": 403,
    "TECHNICAL_INTAKE_DRAFT_NOT_FOUND": 404,
    "TECHNICAL_INTAKE_DRAFT_DOCUMENT_NOT_FOUND": 404,
    "TECHNICAL_INTAKE_DRAFT_STALE": 409,
    "TECHNICAL_INTAKE_DRAFT_PERSISTENCE_CONFLICT": 503,
}


class TechnicalIntakeDraftError(RuntimeError):
    """A stable, presentation-safe Draft contract or persistence failure."""

    def __init__(self, code: str) -> None:
        if code not in _ERROR_CODES:
            raise ValueError("Unknown technical-intake Draft error code")
        self.code = code
        self.status_code = _ERROR_STATUS.get(code, 422)
        self.retryable = code == "TECHNICAL_INTAKE_DRAFT_PERSISTENCE_CONFLICT"
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ValidatedTechnicalIntakePayload:
    payload: dict[str, Any]
    canonical_json: str
    payload_sha256: str
    field_row_ids: tuple[str, ...]
    locator_row_ids: tuple[str, ...]
    link_row_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TechnicalIntakeDraftStartResult:
    draft: TechnicalIntakeDraft
    resumed: bool


@dataclass(frozen=True, slots=True)
class TechnicalIntakeDraftSaveResult:
    draft: TechnicalIntakeDraft
    idempotent_replay: bool
    changed_field_row_ids: tuple[str, ...] = ()
    changed_locator_row_ids: tuple[str, ...] = ()
    changed_link_row_ids: tuple[str, ...] = ()


class _DuplicateJsonKey(ValueError):
    pass


class _RejectedJsonNumber(ValueError):
    pass


def _raise_rejected_json_number(_value: str) -> NoReturn:
    raise _RejectedJsonNumber


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateJsonKey
        value[key] = item
    return value


def _strict_json_value(payload_json: str | bytes) -> Any:
    if isinstance(payload_json, str):
        try:
            encoded = payload_json.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            raise TechnicalIntakeDraftError(
                "TECHNICAL_INTAKE_DRAFT_JSON_INVALID"
            ) from None
        text = payload_json
    elif isinstance(payload_json, bytes):
        encoded = payload_json
        try:
            text = payload_json.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise TechnicalIntakeDraftError(
                "TECHNICAL_INTAKE_DRAFT_JSON_INVALID"
            ) from None
    else:
        raise TechnicalIntakeDraftError("TECHNICAL_INTAKE_DRAFT_JSON_INVALID")
    if not encoded or len(encoded) > TECHNICAL_INTAKE_PAYLOAD_MAX_BYTES:
        code = (
            "TECHNICAL_INTAKE_DRAFT_PAYLOAD_TOO_LARGE"
            if encoded
            else "TECHNICAL_INTAKE_DRAFT_JSON_INVALID"
        )
        raise TechnicalIntakeDraftError(code)
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_raise_rejected_json_number,
            parse_float=_raise_rejected_json_number,
        )
    except _DuplicateJsonKey:
        raise TechnicalIntakeDraftError(
            "TECHNICAL_INTAKE_DRAFT_DUPLICATE_KEY"
        ) from None
    except (json.JSONDecodeError, _RejectedJsonNumber, RecursionError, ValueError):
        raise TechnicalIntakeDraftError(
            "TECHNICAL_INTAKE_DRAFT_JSON_INVALID"
        ) from None


def _canonical_uuid4(value: object, *, code: str) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise TechnicalIntakeDraftError(code)
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise TechnicalIntakeDraftError(code) from None
    if parsed.version != 4 or str(parsed) != value:
        raise TechnicalIntakeDraftError(code)
    return value


def _persisted_record_id(value: object, *, code: str) -> str:
    """Accept FK-backed legacy IDs without weakening new stable row IDs."""

    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > 36
        or any(not character.isprintable() for character in value)
    ):
        raise TechnicalIntakeDraftError(code)
    return value


def _canonical_sha256(value: object, *, code: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise TechnicalIntakeDraftError(code)
    return value


def _bounded_int(value: object, *, minimum: int, maximum: int, code: str) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not minimum <= value <= maximum
    ):
        raise TechnicalIntakeDraftError(code)
    return value


def _text(
    value: object,
    *,
    maximum: int,
    code: str,
    nullable: bool,
    multiline: bool = False,
) -> str | None:
    if value is None:
        if nullable:
            return None
        raise TechnicalIntakeDraftError(code)
    if not isinstance(value, str):
        raise TechnicalIntakeDraftError(code)
    normalized = (
        value.replace("\r\n", "\n").replace("\r", "\n").strip()
        if multiline
        else value.strip()
    )
    if not normalized or len(normalized) > maximum:
        raise TechnicalIntakeDraftError(code)
    allowed_controls = {"\n", "\t"} if multiline else set()
    if any(
        not character.isprintable() and character not in allowed_controls
        for character in normalized
    ):
        raise TechnicalIntakeDraftError(code)
    return normalized


def _source_text(
    value: object,
    *,
    maximum: int,
    code: str,
    nullable: bool,
) -> str | None:
    """Validate retained source wording without silently rewriting it."""

    if value is None:
        if nullable:
            return None
        raise TechnicalIntakeDraftError(code)
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or any(
            not character.isprintable() and character not in {"\r", "\n", "\t"}
            for character in value
        )
    ):
        raise TechnicalIntakeDraftError(code)
    return value


def _reason(value: object) -> str:
    try:
        safe = _text(
            value,
            maximum=4_000,
            code="TECHNICAL_INTAKE_DRAFT_REASON_INVALID",
            nullable=False,
            multiline=True,
        )
    except TechnicalIntakeDraftError:
        raise TechnicalIntakeDraftError(
            "TECHNICAL_INTAKE_DRAFT_REASON_INVALID"
        ) from None
    if safe is None:
        raise TechnicalIntakeDraftError("TECHNICAL_INTAKE_DRAFT_REASON_INVALID")
    return safe


def _enum(value: object, *, allowed: frozenset[str], code: str) -> str:
    safe = _text(value, maximum=100, code=code, nullable=False)
    if safe not in allowed:
        raise TechnicalIntakeDraftError(code)
    return safe


def _normalise_field(row: object) -> dict[str, Any]:
    code = "TECHNICAL_INTAKE_DRAFT_FIELD_INVALID"
    if not isinstance(row, dict) or set(row) != _FIELD_KEYS:
        raise TechnicalIntakeDraftError(code)
    fact_state = _enum(row["fact_state"], allowed=TECHNICAL_INTAKE_FACT_STATES, code=code)
    if fact_state == "Confirmed":
        raise TechnicalIntakeDraftError(
            "TECHNICAL_INTAKE_DRAFT_CONFIRMED_FORBIDDEN"
        )
    field_key = _enum(row["field_key"], allowed=TECHNICAL_INTAKE_FIELD_KEYS, code=code)
    raw_value = _source_text(
        row["raw_value"], maximum=20_000, code=code, nullable=True
    )
    normalized_value = _text(
        row["normalized_value"],
        maximum=20_000,
        code=code,
        nullable=True,
        multiline=True,
    )
    limitation = _text(
        row["limitation"], maximum=4_000, code=code, nullable=True, multiline=True
    )
    if fact_state == "Unresolved":
        if limitation is None or normalized_value is not None:
            raise TechnicalIntakeDraftError(code)
    elif raw_value is None and normalized_value is None:
        raise TechnicalIntakeDraftError(code)
    material = row["material"]
    if not isinstance(material, bool):
        raise TechnicalIntakeDraftError(code)
    return {
        "fact_state": fact_state,
        "field_key": field_key,
        "limitation": limitation,
        "material": material,
        "normalized_value": normalized_value,
        "ordinal": _bounded_int(row["ordinal"], minimum=1, maximum=500, code=code),
        "raw_value": raw_value,
        "row_id": _canonical_uuid4(row["row_id"], code=code),
        "semantics": _enum(
            row["semantics"], allowed=TECHNICAL_INTAKE_SEMANTICS, code=code
        ),
        "unit": _text(row["unit"], maximum=100, code=code, nullable=True),
    }


def _region_decimal(value: object) -> str:
    code = "TECHNICAL_INTAKE_DRAFT_LOCATOR_INVALID"
    if not isinstance(value, str) or _REGION_DECIMAL_RE.fullmatch(value) is None:
        raise TechnicalIntakeDraftError(code)
    try:
        decimal = Decimal(value)
    except InvalidOperation:
        raise TechnicalIntakeDraftError(code) from None
    if not decimal.is_finite() or not Decimal(0) <= decimal <= Decimal(1):
        raise TechnicalIntakeDraftError(code)
    if decimal == 0:
        return "0"
    if decimal == 1:
        return "1"
    return format(decimal.normalize(), "f")


def _normalise_region(value: object) -> dict[str, str] | None:
    code = "TECHNICAL_INTAKE_DRAFT_LOCATOR_INVALID"
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != _REGION_KEYS:
        raise TechnicalIntakeDraftError(code)
    region = {key: _region_decimal(value[key]) for key in sorted(_REGION_KEYS)}
    if Decimal(region["x0"]) >= Decimal(region["x1"]) or Decimal(
        region["y0"]
    ) >= Decimal(region["y1"]):
        raise TechnicalIntakeDraftError(code)
    return region


def _normalise_locator(
    row: object,
    *,
    technical_document_id: str,
    source_sha256: str,
    source_size_bytes: int,
) -> dict[str, Any]:
    code = "TECHNICAL_INTAKE_DRAFT_LOCATOR_INVALID"
    if not isinstance(row, dict) or set(row) != _LOCATOR_KEYS:
        raise TechnicalIntakeDraftError(code)
    locator_document_id = _persisted_record_id(
        row["technical_document_id"],
        code=code,
    )
    locator_sha256 = _canonical_sha256(row["source_sha256"], code=code)
    locator_size_bytes = _bounded_int(
        row["source_size_bytes"],
        minimum=1,
        maximum=1024 * 1024 * 1024,
        code=code,
    )
    if (
        locator_document_id != technical_document_id
        or locator_sha256 != source_sha256
        or locator_size_bytes != source_size_bytes
    ):
        raise TechnicalIntakeDraftError(code)
    text_values = {
        key: _text(row[key], maximum=500, code=code, nullable=True)
        for key in _LOCATOR_TEXT_KEYS
    }
    excerpt = _source_text(
        row["excerpt"], maximum=4_000, code=code, nullable=True
    )
    region = _normalise_region(row["region"])
    if (
        not any(value is not None for value in text_values.values())
        and excerpt is None
        and region is None
    ):
        raise TechnicalIntakeDraftError(code)
    return {
        "callout": text_values["callout"],
        "clause": text_values["clause"],
        "column": text_values["column"],
        "drawing": text_values["drawing"],
        "excerpt": excerpt,
        "figure": text_values["figure"],
        "footnote": text_values["footnote"],
        "option": text_values["option"],
        "physical_page": _bounded_int(
            row["physical_page"], minimum=1, maximum=500, code=code
        ),
        "printed_page": text_values["printed_page"],
        "region": region,
        "row": text_values["row"],
        "row_id": _canonical_uuid4(row["row_id"], code=code),
        "section": text_values["section"],
        "source_sha256": source_sha256,
        "source_size_bytes": source_size_bytes,
        "specimen": text_values["specimen"],
        "table": text_values["table"],
        "technical_document_id": technical_document_id,
        "visual_verification": _enum(
            row["visual_verification"],
            allowed=TECHNICAL_INTAKE_VISUAL_VERIFICATION_STATES,
            code=code,
        ),
    }


def _normalise_link(row: object) -> dict[str, str]:
    code = "TECHNICAL_INTAKE_DRAFT_LINK_INVALID"
    if not isinstance(row, dict) or set(row) != _LINK_KEYS:
        raise TechnicalIntakeDraftError(code)
    return {
        "evidence_role": _enum(
            row["evidence_role"], allowed=TECHNICAL_INTAKE_EVIDENCE_ROLES, code=code
        ),
        "field_row_id": _canonical_uuid4(row["field_row_id"], code=code),
        "locator_row_id": _canonical_uuid4(row["locator_row_id"], code=code),
        "row_id": _canonical_uuid4(row["row_id"], code=code),
    }


def _bounded_array(value: object, *, maximum: int) -> list[Any]:
    if not isinstance(value, list) or len(value) > maximum:
        raise TechnicalIntakeDraftError(
            "TECHNICAL_INTAKE_DRAFT_STRUCTURE_INVALID"
        )
    return value


def _normalise_payload_value(
    value: object,
    *,
    technical_document_id: str,
    source_sha256: str,
    source_size_bytes: int,
) -> ValidatedTechnicalIntakePayload:
    if not isinstance(value, dict) or set(value) != {"schema", "fields", "locators", "links"}:
        raise TechnicalIntakeDraftError(
            "TECHNICAL_INTAKE_DRAFT_STRUCTURE_INVALID"
        )
    if value["schema"] != TECHNICAL_INTAKE_PAYLOAD_SCHEMA:
        raise TechnicalIntakeDraftError(
            "TECHNICAL_INTAKE_DRAFT_STRUCTURE_INVALID"
        )
    fields = [
        _normalise_field(row)
        for row in _bounded_array(value["fields"], maximum=TECHNICAL_INTAKE_MAX_FIELDS)
    ]
    locators = [
        _normalise_locator(
            row,
            technical_document_id=technical_document_id,
            source_sha256=source_sha256,
            source_size_bytes=source_size_bytes,
        )
        for row in _bounded_array(
            value["locators"], maximum=TECHNICAL_INTAKE_MAX_LOCATORS
        )
    ]
    links = [
        _normalise_link(row)
        for row in _bounded_array(value["links"], maximum=TECHNICAL_INTAKE_MAX_LINKS)
    ]

    field_ids = [row["row_id"] for row in fields]
    locator_ids = [row["row_id"] for row in locators]
    link_ids = [row["row_id"] for row in links]
    ordinals = [row["ordinal"] for row in fields]
    if (
        len(field_ids) != len(set(field_ids))
        or len(locator_ids) != len(set(locator_ids))
        or len(link_ids) != len(set(link_ids))
        or len(ordinals) != len(set(ordinals))
        or len(field_ids + locator_ids + link_ids)
        != len(set(field_ids + locator_ids + link_ids))
    ):
        raise TechnicalIntakeDraftError(
            "TECHNICAL_INTAKE_DRAFT_STRUCTURE_INVALID"
        )

    field_by_id = {row["row_id"]: row for row in fields}
    locator_id_set = set(locator_ids)
    linked_fields: set[str] = set()
    linked_locators: set[str] = set()
    support_by_field: set[str] = set()
    conflicting_fields: set[str] = set()
    link_tuples: set[tuple[str, str, str]] = set()
    for link in links:
        field_id = link["field_row_id"]
        locator_id = link["locator_row_id"]
        role = link["evidence_role"]
        if field_id not in field_by_id or locator_id not in locator_id_set:
            raise TechnicalIntakeDraftError("TECHNICAL_INTAKE_DRAFT_LINK_INVALID")
        key = (field_id, locator_id, role)
        if key in link_tuples:
            raise TechnicalIntakeDraftError("TECHNICAL_INTAKE_DRAFT_LINK_INVALID")
        link_tuples.add(key)
        linked_fields.add(field_id)
        linked_locators.add(locator_id)
        if role in _SUPPORTING_EVIDENCE_ROLES:
            support_by_field.add(field_id)
        if role == "conflicting":
            conflicting_fields.add(field_id)
    if linked_fields != set(field_ids) or linked_locators != locator_id_set:
        raise TechnicalIntakeDraftError(
            "TECHNICAL_INTAKE_DRAFT_EVIDENCE_INVALID"
        )
    for field_id, field in field_by_id.items():
        if field["fact_state"] != "Unresolved" and field_id not in support_by_field:
            raise TechnicalIntakeDraftError(
                "TECHNICAL_INTAKE_DRAFT_EVIDENCE_INVALID"
            )
        if field_id in conflicting_fields and field["fact_state"] != "Unresolved":
            raise TechnicalIntakeDraftError(
                "TECHNICAL_INTAKE_DRAFT_EVIDENCE_INVALID"
            )

    sorted_fields = sorted(fields, key=lambda row: (row["ordinal"], row["row_id"]))
    sorted_links = sorted(links, key=lambda row: row["row_id"])
    sorted_locators = sorted(locators, key=lambda row: row["row_id"])
    payload: dict[str, Any] = {
        "fields": sorted_fields,
        "links": sorted_links,
        "locators": sorted_locators,
        "schema": TECHNICAL_INTAKE_PAYLOAD_SCHEMA,
    }
    canonical_json = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(canonical_json.encode("utf-8")) > TECHNICAL_INTAKE_PAYLOAD_MAX_BYTES:
        raise TechnicalIntakeDraftError(
            "TECHNICAL_INTAKE_DRAFT_PAYLOAD_TOO_LARGE"
        )
    return ValidatedTechnicalIntakePayload(
        payload=payload,
        canonical_json=canonical_json,
        payload_sha256=hashlib.sha256(canonical_json.encode("utf-8")).hexdigest(),
        field_row_ids=tuple(row["row_id"] for row in sorted_fields),
        locator_row_ids=tuple(row["row_id"] for row in sorted_locators),
        link_row_ids=tuple(row["row_id"] for row in sorted_links),
    )


def parse_technical_intake_payload(
    payload_json: str | bytes,
    *,
    technical_document_id: str,
    source_sha256: str,
    source_size_bytes: int,
) -> ValidatedTechnicalIntakePayload:
    """Parse and canonicalise one strict, duplicate-key-free payload."""

    safe_document_id = _persisted_record_id(
        technical_document_id,
        code="TECHNICAL_INTAKE_DRAFT_STRUCTURE_INVALID",
    )
    safe_sha256 = _canonical_sha256(
        source_sha256,
        code="TECHNICAL_INTAKE_DRAFT_STRUCTURE_INVALID",
    )
    safe_size = _bounded_int(
        source_size_bytes,
        minimum=1,
        maximum=1024 * 1024 * 1024,
        code="TECHNICAL_INTAKE_DRAFT_STRUCTURE_INVALID",
    )
    return _normalise_payload_value(
        _strict_json_value(payload_json),
        technical_document_id=safe_document_id,
        source_sha256=safe_sha256,
        source_size_bytes=safe_size,
    )


def _empty_payload(
    *, technical_document_id: str, source_sha256: str, source_size_bytes: int
) -> ValidatedTechnicalIntakePayload:
    return _normalise_payload_value(
        {
            "schema": TECHNICAL_INTAKE_PAYLOAD_SCHEMA,
            "fields": [],
            "locators": [],
            "links": [],
        },
        technical_document_id=technical_document_id,
        source_sha256=source_sha256,
        source_size_bytes=source_size_bytes,
    )


def _require_actor(db: Session, actor: User) -> User:
    if not isinstance(actor, User) or not actor.id:
        raise TechnicalIntakeDraftError("TECHNICAL_INTAKE_DRAFT_ACTOR_INVALID")
    persisted = db.get(User, actor.id)
    if persisted is None or persisted.is_active is not True:
        raise TechnicalIntakeDraftError("TECHNICAL_INTAKE_DRAFT_ACTOR_INVALID")
    _persisted_record_id(
        persisted.id,
        code="TECHNICAL_INTAKE_DRAFT_ACTOR_INVALID",
    )
    return persisted


def _document_id(value: object) -> str:
    return _persisted_record_id(
        value,
        code="TECHNICAL_INTAKE_DRAFT_DOCUMENT_NOT_FOUND",
    )


def _draft_id(value: object) -> str:
    return _canonical_uuid4(value, code="TECHNICAL_INTAKE_DRAFT_ID_INVALID")


def _require_authorable_source(
    db: Session,
    *,
    technical_document_id: str,
    storage_root: Path,
    expected_stored_file_id: str | None = None,
    expected_sha256: str | None = None,
    expected_size_bytes: int | None = None,
) -> tuple[TechnicalDocument, StoredFile, StoredFileBinding]:
    # Discover only the binding needed to enter the global StoredFile ->
    # TechnicalDocument lock order. The locked document must still match it.
    discovered_stored_file_id = db.scalar(
        select(TechnicalDocument.stored_file_id)
        .where(TechnicalDocument.id == technical_document_id)
    )
    if discovered_stored_file_id is None:
        raise TechnicalIntakeDraftError(
            "TECHNICAL_INTAKE_DRAFT_DOCUMENT_NOT_FOUND"
        )
    stored = db.scalar(
        select(StoredFile)
        .where(StoredFile.id == discovered_stored_file_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    document = db.scalar(
        select(TechnicalDocument)
        .where(TechnicalDocument.id == technical_document_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if document is None:
        raise TechnicalIntakeDraftError(
            "TECHNICAL_INTAKE_DRAFT_DOCUMENT_NOT_FOUND"
        )
    if document.status not in _AUTHORABLE_DOCUMENT_STATUSES:
        raise TechnicalIntakeDraftError(
            "TECHNICAL_INTAKE_DRAFT_DOCUMENT_NOT_AUTHORABLE"
        )
    if document.stored_file_id != discovered_stored_file_id:
        raise TechnicalIntakeDraftError(
            "TECHNICAL_INTAKE_DRAFT_SOURCE_FILE_INVALID"
        )
    if expected_stored_file_id is not None and document.stored_file_id != expected_stored_file_id:
        raise TechnicalIntakeDraftError(
            "TECHNICAL_INTAKE_DRAFT_SOURCE_FILE_INVALID"
        )
    if stored is None or (stored.media_type or "").strip().casefold() != "application/pdf":
        raise TechnicalIntakeDraftError(
            "TECHNICAL_INTAKE_DRAFT_SOURCE_FILE_INVALID"
        )
    _persisted_record_id(
        stored.id,
        code="TECHNICAL_INTAKE_DRAFT_SOURCE_FILE_INVALID",
    )
    try:
        binding = require_stored_file_binding(
            stored,
            storage_root=storage_root,
            required_purpose="technical_evidence",
        )
    except StoredFileBindingError as exc:
        raise TechnicalIntakeDraftError(
            "TECHNICAL_INTAKE_DRAFT_SOURCE_FILE_INVALID"
        ) from exc
    if binding.suffix != ".pdf" or binding.size_bytes < 1:
        raise TechnicalIntakeDraftError(
            "TECHNICAL_INTAKE_DRAFT_SOURCE_FILE_INVALID"
        )
    if (
        expected_sha256 is not None
        and binding.sha256 != expected_sha256
        or expected_size_bytes is not None
        and binding.size_bytes != expected_size_bytes
    ):
        raise TechnicalIntakeDraftError(
            "TECHNICAL_INTAKE_DRAFT_SOURCE_FILE_INVALID"
        )
    return document, stored, binding


def _verify_persisted_draft(draft: TechnicalIntakeDraft) -> ValidatedTechnicalIntakePayload:
    code = "TECHNICAL_INTAKE_DRAFT_PERSISTENCE_CONFLICT"
    try:
        _canonical_uuid4(draft.id, code=code)
        _persisted_record_id(draft.technical_document_id, code=code)
        _persisted_record_id(draft.source_stored_file_id, code=code)
        _persisted_record_id(draft.owner_id, code=code)
        source_sha256 = _canonical_sha256(draft.source_sha256, code=code)
        source_size_bytes = _bounded_int(
            draft.source_size_bytes,
            minimum=1,
            maximum=1024 * 1024 * 1024,
            code=code,
        )
    except TechnicalIntakeDraftError:
        raise TechnicalIntakeDraftError(code) from None
    if (
        draft.draft_schema != TECHNICAL_INTAKE_DRAFT_SCHEMA
        or draft.status != "draft"
        or not isinstance(draft.record_version, int)
        or isinstance(draft.record_version, bool)
        or draft.record_version < 1
        or not isinstance(draft.payload_json, dict)
    ):
        raise TechnicalIntakeDraftError(code)
    try:
        validated = _normalise_payload_value(
            draft.payload_json,
            technical_document_id=draft.technical_document_id,
            source_sha256=source_sha256,
            source_size_bytes=source_size_bytes,
        )
    except TechnicalIntakeDraftError:
        raise TechnicalIntakeDraftError(code) from None
    if validated.payload != draft.payload_json or validated.payload_sha256 != draft.payload_sha256:
        raise TechnicalIntakeDraftError(code)
    return validated


def start_or_resume_technical_intake_draft(
    db: Session,
    *,
    actor: User,
    technical_document_id: object,
    storage_root: Path | None = None,
    source_ip: str | None = None,
) -> TechnicalIntakeDraftStartResult:
    """Start or resume one owner/source-bound Draft without committing."""

    persisted_actor = _require_actor(db, actor)
    safe_document_id = _document_id(technical_document_id)
    document, stored, binding = _require_authorable_source(
        db,
        technical_document_id=safe_document_id,
        storage_root=storage_root or get_settings().storage_root,
    )
    existing = db.scalar(
        select(TechnicalIntakeDraft)
        .where(
            TechnicalIntakeDraft.owner_id == persisted_actor.id,
            TechnicalIntakeDraft.technical_document_id == document.id,
            TechnicalIntakeDraft.source_stored_file_id == stored.id,
            TechnicalIntakeDraft.source_sha256 == binding.sha256,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if existing is not None:
        if existing.source_size_bytes != binding.size_bytes:
            raise TechnicalIntakeDraftError(
                "TECHNICAL_INTAKE_DRAFT_SOURCE_FILE_INVALID"
            )
        _verify_persisted_draft(existing)
        return TechnicalIntakeDraftStartResult(draft=existing, resumed=True)

    empty = _empty_payload(
        technical_document_id=document.id,
        source_sha256=binding.sha256,
        source_size_bytes=binding.size_bytes,
    )
    draft = TechnicalIntakeDraft(
        draft_schema=TECHNICAL_INTAKE_DRAFT_SCHEMA,
        technical_document_id=document.id,
        source_stored_file_id=stored.id,
        source_sha256=binding.sha256,
        source_size_bytes=binding.size_bytes,
        owner_id=persisted_actor.id,
        status="draft",
        payload_json=empty.payload,
        payload_sha256=empty.payload_sha256,
        record_version=1,
    )
    created = True
    try:
        with db.begin_nested():
            db.add(draft)
            db.flush()
    except IntegrityError:
        created = False
    if not created:
        raced = db.scalar(
            select(TechnicalIntakeDraft)
            .where(
                TechnicalIntakeDraft.owner_id == persisted_actor.id,
                TechnicalIntakeDraft.technical_document_id == document.id,
                TechnicalIntakeDraft.source_stored_file_id == stored.id,
                TechnicalIntakeDraft.source_sha256 == binding.sha256,
                TechnicalIntakeDraft.source_size_bytes == binding.size_bytes,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if raced is None:
            raise TechnicalIntakeDraftError(
                "TECHNICAL_INTAKE_DRAFT_PERSISTENCE_CONFLICT"
            )
        _verify_persisted_draft(raced)
        return TechnicalIntakeDraftStartResult(draft=raced, resumed=True)
    record_audit(
        db,
        actor=persisted_actor,
        action="start",
        entity_type="technical_intake_draft",
        entity_id=draft.id,
        new_value={
            "payload_sha256": empty.payload_sha256,
            "source_sha256": binding.sha256,
        },
        reason="Started authority-neutral technical intake Draft",
        source_ip=source_ip,
        correlation_id=draft.id,
    )
    return TechnicalIntakeDraftStartResult(draft=draft, resumed=False)


def get_owned_technical_intake_draft(
    db: Session,
    *,
    actor: User,
    draft_id: object,
) -> TechnicalIntakeDraft:
    """Return one owner-bound Draft after validating its persisted contract."""

    persisted_actor = _require_actor(db, actor)
    safe_draft_id = _draft_id(draft_id)
    draft = db.scalar(
        select(TechnicalIntakeDraft)
        .where(
            TechnicalIntakeDraft.id == safe_draft_id,
            TechnicalIntakeDraft.owner_id == persisted_actor.id,
        )
        .execution_options(populate_existing=True)
    )
    if draft is None:
        raise TechnicalIntakeDraftError("TECHNICAL_INTAKE_DRAFT_NOT_FOUND")
    _verify_persisted_draft(draft)
    return draft


def list_owned_technical_intake_drafts(
    db: Session,
    *,
    actor: User,
    technical_document_id: object | None = None,
) -> tuple[TechnicalIntakeDraft, ...]:
    """List only the actor's valid Drafts, optionally for one source document."""

    persisted_actor = _require_actor(db, actor)
    statement = select(TechnicalIntakeDraft).where(
        TechnicalIntakeDraft.owner_id == persisted_actor.id
    )
    if technical_document_id is not None:
        statement = statement.where(
            TechnicalIntakeDraft.technical_document_id
            == _document_id(technical_document_id)
        )
    drafts = tuple(
        db.scalars(
            statement.order_by(
                TechnicalIntakeDraft.updated_at.desc(),
                TechnicalIntakeDraft.id,
            ).execution_options(populate_existing=True)
        ).all()
    )
    for draft in drafts:
        _verify_persisted_draft(draft)
    return drafts


def _changed_row_ids(
    previous: dict[str, Any], current: dict[str, Any], collection: str
) -> tuple[str, ...]:
    old_rows = {row["row_id"]: row for row in previous[collection]}
    new_rows = {row["row_id"]: row for row in current[collection]}
    return tuple(
        sorted(
            row_id
            for row_id in old_rows.keys() | new_rows.keys()
            if old_rows.get(row_id) != new_rows.get(row_id)
        )
    )


def save_technical_intake_draft(
    db: Session,
    *,
    actor: User,
    draft_id: object,
    expected_record_version: object,
    payload_json: str | bytes,
    reason: str,
    storage_root: Path | None = None,
    source_ip: str | None = None,
) -> TechnicalIntakeDraftSaveResult:
    """CAS-save one strict Draft payload without committing or granting authority."""

    persisted_actor = _require_actor(db, actor)
    safe_draft_id = _draft_id(draft_id)
    expected_version = _bounded_int(
        expected_record_version,
        minimum=1,
        maximum=2_147_483_647,
        code="TECHNICAL_INTAKE_DRAFT_STALE",
    )
    safe_reason = _reason(reason)
    draft = db.scalar(
        select(TechnicalIntakeDraft)
        .where(
            TechnicalIntakeDraft.id == safe_draft_id,
            TechnicalIntakeDraft.owner_id == persisted_actor.id,
        )
        .execution_options(populate_existing=True)
    )
    if draft is None:
        raise TechnicalIntakeDraftError("TECHNICAL_INTAKE_DRAFT_NOT_FOUND")
    _verify_persisted_draft(draft)
    source_identity = (
        draft.technical_document_id,
        draft.source_stored_file_id,
        draft.source_sha256,
        draft.source_size_bytes,
    )
    _require_authorable_source(
        db,
        technical_document_id=source_identity[0],
        storage_root=storage_root or get_settings().storage_root,
        expected_stored_file_id=source_identity[1],
        expected_sha256=source_identity[2],
        expected_size_bytes=source_identity[3],
    )
    db.expire(draft)
    draft = db.scalar(
        select(TechnicalIntakeDraft)
        .where(
            TechnicalIntakeDraft.id == safe_draft_id,
            TechnicalIntakeDraft.owner_id == persisted_actor.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if draft is None:
        raise TechnicalIntakeDraftError("TECHNICAL_INTAKE_DRAFT_NOT_FOUND")
    if (
        draft.technical_document_id,
        draft.source_stored_file_id,
        draft.source_sha256,
        draft.source_size_bytes,
    ) != source_identity:
        raise TechnicalIntakeDraftError(
            "TECHNICAL_INTAKE_DRAFT_SOURCE_FILE_INVALID"
        )
    previous = _verify_persisted_draft(draft)
    submitted = parse_technical_intake_payload(
        payload_json,
        technical_document_id=draft.technical_document_id,
        source_sha256=draft.source_sha256,
        source_size_bytes=draft.source_size_bytes,
    )

    if expected_version != draft.record_version:
        if (
            expected_version < draft.record_version
            and submitted.payload_sha256 == draft.payload_sha256
        ):
            return TechnicalIntakeDraftSaveResult(draft=draft, idempotent_replay=True)
        raise TechnicalIntakeDraftError("TECHNICAL_INTAKE_DRAFT_STALE")
    if submitted.payload_sha256 == draft.payload_sha256:
        return TechnicalIntakeDraftSaveResult(draft=draft, idempotent_replay=True)

    changed_fields = _changed_row_ids(previous.payload, submitted.payload, "fields")
    changed_locators = _changed_row_ids(previous.payload, submitted.payload, "locators")
    changed_links = _changed_row_ids(previous.payload, submitted.payload, "links")
    new_version = expected_version + 1
    result = db.execute(
        update(TechnicalIntakeDraft)
        .where(
            TechnicalIntakeDraft.id == draft.id,
            TechnicalIntakeDraft.owner_id == persisted_actor.id,
            TechnicalIntakeDraft.draft_schema == TECHNICAL_INTAKE_DRAFT_SCHEMA,
            TechnicalIntakeDraft.status == "draft",
            TechnicalIntakeDraft.technical_document_id == draft.technical_document_id,
            TechnicalIntakeDraft.source_stored_file_id == draft.source_stored_file_id,
            TechnicalIntakeDraft.source_sha256 == draft.source_sha256,
            TechnicalIntakeDraft.source_size_bytes == draft.source_size_bytes,
            TechnicalIntakeDraft.record_version == expected_version,
        )
        .values(
            payload_json=submitted.payload,
            payload_sha256=submitted.payload_sha256,
            record_version=new_version,
        )
        .execution_options(synchronize_session=False)
    )
    if getattr(result, "rowcount", 0) != 1:
        db.expire(draft)
        current = db.scalar(
            select(TechnicalIntakeDraft)
            .where(
                TechnicalIntakeDraft.id == safe_draft_id,
                TechnicalIntakeDraft.owner_id == persisted_actor.id,
            )
            .execution_options(populate_existing=True)
        )
        if current is None:
            raise TechnicalIntakeDraftError("TECHNICAL_INTAKE_DRAFT_NOT_FOUND")
        _verify_persisted_draft(current)
        if (
            expected_version < current.record_version
            and submitted.payload_sha256 == current.payload_sha256
        ):
            return TechnicalIntakeDraftSaveResult(
                draft=current,
                idempotent_replay=True,
            )
        raise TechnicalIntakeDraftError("TECHNICAL_INTAKE_DRAFT_STALE")

    record_audit(
        db,
        actor=persisted_actor,
        action="save",
        entity_type="technical_intake_draft",
        entity_id=draft.id,
        previous_value={"payload_sha256": previous.payload_sha256},
        new_value={
            "changed_field_row_ids": list(changed_fields),
            "changed_link_row_ids": list(changed_links),
            "changed_locator_row_ids": list(changed_locators),
            "payload_sha256": submitted.payload_sha256,
        },
        reason=safe_reason,
        source_ip=source_ip,
        correlation_id=draft.id,
    )
    db.expire(draft)
    db.refresh(draft)
    return TechnicalIntakeDraftSaveResult(
        draft=draft,
        idempotent_replay=False,
        changed_field_row_ids=changed_fields,
        changed_locator_row_ids=changed_locators,
        changed_link_row_ids=changed_links,
    )


__all__ = [
    "TECHNICAL_INTAKE_DRAFT_SCHEMA",
    "TECHNICAL_INTAKE_EVIDENCE_ROLES",
    "TECHNICAL_INTAKE_FACT_STATES",
    "TECHNICAL_INTAKE_FIELD_KEYS",
    "TECHNICAL_INTAKE_MAX_FIELDS",
    "TECHNICAL_INTAKE_MAX_LINKS",
    "TECHNICAL_INTAKE_MAX_LOCATORS",
    "TECHNICAL_INTAKE_PAYLOAD_MAX_BYTES",
    "TECHNICAL_INTAKE_PAYLOAD_SCHEMA",
    "TECHNICAL_INTAKE_SEMANTICS",
    "TECHNICAL_INTAKE_VISUAL_VERIFICATION_STATES",
    "TechnicalIntakeDraftError",
    "TechnicalIntakeDraftSaveResult",
    "TechnicalIntakeDraftStartResult",
    "ValidatedTechnicalIntakePayload",
    "get_owned_technical_intake_draft",
    "list_owned_technical_intake_drafts",
    "parse_technical_intake_payload",
    "save_technical_intake_draft",
    "start_or_resume_technical_intake_draft",
]
