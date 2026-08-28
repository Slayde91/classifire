"""Governed first-Draft authoring from retained technical evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..config import get_settings
from ..models import StoredFile, TechnicalDocument, TechnicalVariant, User
from .storage import StoredFileBindingError, require_stored_file_binding
from .technical_governance import (
    PENDING_TECHNICAL_REVIEW,
    TECHNICAL_VARIANT_UI_INTAKE_POLICY,
)

_AUTHORABLE_DOCUMENT_STATUSES = frozenset({"draft", "in_review", "approved"})
_DETAIL_MAX_LENGTH = 20_000
_DESCRIPTION_MAX_LENGTH = 4_000
_INDEXED_LABEL_MAX_LENGTH = 500
_JSON_MAX_LENGTH = 100_000
_REASON_MAX_LENGTH = 4_000
_ERROR_CODES = frozenset(
    {
        "TECHNICAL_DRAFT_ACTOR_INVALID",
        "TECHNICAL_DRAFT_COMPONENT_REQUIREMENTS_INVALID",
        "TECHNICAL_DRAFT_DOCUMENT_NOT_AUTHORABLE",
        "TECHNICAL_DRAFT_DOCUMENT_NOT_FOUND",
        "TECHNICAL_DRAFT_EFFECTIVE_DATE_INVALID",
        "TECHNICAL_DRAFT_FIELD_INVALID",
        "TECHNICAL_DRAFT_LABOUR_REQUIREMENTS_INVALID",
        "TECHNICAL_DRAFT_NUMERIC_RANGE_INVALID",
        "TECHNICAL_DRAFT_REASON_INVALID",
        "TECHNICAL_DRAFT_SOURCE_FILE_INVALID",
        "TECHNICAL_DRAFT_VARIANT_ID_CONFLICT",
        "TECHNICAL_DRAFT_VARIANT_ID_RESERVED",
    }
)


class TechnicalVariantIntakeError(ValueError):
    """A stable, presentation-safe first-Draft authoring failure."""

    def __init__(self, code: str) -> None:
        if code not in _ERROR_CODES:
            raise ValueError("Unknown technical-variant intake error code")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class TechnicalVariantDraftInput:
    variant_id: str
    system_id: str
    source_page: str
    reason: str
    source_table: str | None = None
    source_figure: str | None = None
    manufacturer: str | None = None
    product_family: str | None = None
    service_type: str | None = None
    service_material: str | None = None
    minimum_service_size_mm: Decimal | None = None
    maximum_service_size_mm: Decimal | None = None
    permitted_service_quantity: str | None = None
    insulation_type: str | None = None
    insulation_thickness_mm: Decimal | None = None
    substrate_type: str | None = None
    minimum_substrate_thickness_mm: Decimal | None = None
    maximum_substrate_thickness_mm: Decimal | None = None
    orientation: str | None = None
    installation_face: str | None = None
    opening_type: str | None = None
    opening_dimensions: str | None = None
    annular_gap_min_mm: Decimal | None = None
    annular_gap_max_mm: Decimal | None = None
    service_spacing_rules: str | None = None
    edge_distance_rules: str | None = None
    support_rules: str | None = None
    fixing_rules: str | None = None
    component_requirements: dict[str, Any] | list[Any] | None = None
    labour_requirements: list[str] | None = None
    hard_exclusions: str | None = None
    dependencies: str | None = None
    frl: str | None = None
    jurisdiction: str | None = None
    effective_date: date | None = None


def _text(
    value: str | None,
    *,
    maximum: int,
    required: bool = False,
    multiline: bool = False,
) -> str | None:
    if not isinstance(value, str):
        if required or value is not None:
            raise TechnicalVariantIntakeError("TECHNICAL_DRAFT_FIELD_INVALID")
        return None
    normalised = value.strip()
    if not normalised:
        if required:
            raise TechnicalVariantIntakeError("TECHNICAL_DRAFT_FIELD_INVALID")
        return None
    has_invalid_character = (
        any(
            not character.isprintable() and character not in {"\r", "\n", "\t"}
            for character in normalised
        )
        if multiline
        else any(not character.isprintable() for character in normalised)
    )
    if len(normalised) > maximum or has_invalid_character:
        raise TechnicalVariantIntakeError("TECHNICAL_DRAFT_FIELD_INVALID")
    return normalised


def _reason(value: str) -> str:
    try:
        safe = _text(value, maximum=_REASON_MAX_LENGTH, required=True)
    except TechnicalVariantIntakeError as exc:
        raise TechnicalVariantIntakeError("TECHNICAL_DRAFT_REASON_INVALID") from exc
    if safe is None:
        raise TechnicalVariantIntakeError("TECHNICAL_DRAFT_REASON_INVALID")
    return safe


def _required_text(value: str | None, *, maximum: int) -> str:
    safe = _text(value, maximum=maximum, required=True)
    if safe is None:
        raise TechnicalVariantIntakeError("TECHNICAL_DRAFT_FIELD_INVALID")
    return safe


def _number(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise TechnicalVariantIntakeError("TECHNICAL_DRAFT_NUMERIC_RANGE_INVALID")
    normalised = value.normalize()
    _sign, digits, exponent = normalised.as_tuple()
    exponent_value = int(exponent)
    fractional_digits = max(-exponent_value, 0)
    integer_digits = max(len(digits) + exponent_value, 0)
    if fractional_digits > 4 or integer_digits > 14:
        raise TechnicalVariantIntakeError("TECHNICAL_DRAFT_NUMERIC_RANGE_INVALID")
    return value


def _range(
    minimum: Decimal | None,
    maximum: Decimal | None,
) -> tuple[Decimal | None, Decimal | None]:
    safe_minimum = _number(minimum)
    safe_maximum = _number(maximum)
    if safe_minimum is not None and safe_maximum is not None and safe_minimum > safe_maximum:
        raise TechnicalVariantIntakeError("TECHNICAL_DRAFT_NUMERIC_RANGE_INVALID")
    return safe_minimum, safe_maximum


def _component_requirements(value: object) -> dict[str, Any] | list[Any] | None:
    if value is None:
        return None
    if not isinstance(value, (dict, list)):
        raise TechnicalVariantIntakeError(
            "TECHNICAL_DRAFT_COMPONENT_REQUIREMENTS_INVALID"
        )
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise TechnicalVariantIntakeError(
            "TECHNICAL_DRAFT_COMPONENT_REQUIREMENTS_INVALID"
        ) from exc
    if len(encoded) > _JSON_MAX_LENGTH:
        raise TechnicalVariantIntakeError(
            "TECHNICAL_DRAFT_COMPONENT_REQUIREMENTS_INVALID"
        )
    return value


def _labour_requirements(value: object) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list) or any(
        not isinstance(item, str)
        or not item.strip()
        or len(item.strip()) > 1_000
        or any(not character.isprintable() for character in item.strip())
        for item in value
    ):
        raise TechnicalVariantIntakeError(
            "TECHNICAL_DRAFT_LABOUR_REQUIREMENTS_INVALID"
        )
    normalised = [item.strip() for item in value]
    if len(json.dumps(normalised, ensure_ascii=False)) > _JSON_MAX_LENGTH:
        raise TechnicalVariantIntakeError(
            "TECHNICAL_DRAFT_LABOUR_REQUIREMENTS_INVALID"
        )
    return normalised


def create_initial_technical_variant_draft(
    db: Session,
    *,
    actor: User,
    technical_document_id: str,
    values: TechnicalVariantDraftInput,
    storage_root: Path | None = None,
    source_ip: str | None = None,
) -> TechnicalVariant:
    """Create one audited Draft configuration without committing or granting authority."""

    if not isinstance(actor, User) or not actor.id or db.get(User, actor.id) is None:
        raise TechnicalVariantIntakeError("TECHNICAL_DRAFT_ACTOR_INVALID")
    document = db.scalar(
        select(TechnicalDocument)
        .where(TechnicalDocument.id == technical_document_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if document is None:
        raise TechnicalVariantIntakeError("TECHNICAL_DRAFT_DOCUMENT_NOT_FOUND")
    if document.status not in _AUTHORABLE_DOCUMENT_STATUSES:
        raise TechnicalVariantIntakeError("TECHNICAL_DRAFT_DOCUMENT_NOT_AUTHORABLE")
    stored = db.scalar(
        select(StoredFile)
        .where(StoredFile.id == document.stored_file_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if stored is None:
        raise TechnicalVariantIntakeError("TECHNICAL_DRAFT_SOURCE_FILE_INVALID")
    try:
        binding = require_stored_file_binding(
            stored,
            storage_root=storage_root or get_settings().storage_root,
            required_purpose="technical_evidence",
        )
    except StoredFileBindingError as exc:
        raise TechnicalVariantIntakeError(
            "TECHNICAL_DRAFT_SOURCE_FILE_INVALID"
        ) from exc

    variant_id = _required_text(values.variant_id, maximum=300)
    system_id = _required_text(values.system_id, maximum=300)
    source_page = _required_text(values.source_page, maximum=100)
    safe_reason = _reason(values.reason)
    if "-QFREV" in variant_id.upper():
        raise TechnicalVariantIntakeError("TECHNICAL_DRAFT_VARIANT_ID_RESERVED")
    if db.scalar(
        select(TechnicalVariant.id).where(TechnicalVariant.variant_id == variant_id)
    ) is not None:
        raise TechnicalVariantIntakeError("TECHNICAL_DRAFT_VARIANT_ID_CONFLICT")

    service_minimum, service_maximum = _range(
        values.minimum_service_size_mm,
        values.maximum_service_size_mm,
    )
    substrate_minimum, substrate_maximum = _range(
        values.minimum_substrate_thickness_mm,
        values.maximum_substrate_thickness_mm,
    )
    gap_minimum, gap_maximum = _range(
        values.annular_gap_min_mm,
        values.annular_gap_max_mm,
    )
    if values.effective_date is not None and (
        not isinstance(values.effective_date, date)
        or isinstance(values.effective_date, datetime)
    ):
        raise TechnicalVariantIntakeError("TECHNICAL_DRAFT_EFFECTIVE_DATE_INVALID")

    variant = TechnicalVariant(
        variant_id=variant_id,
        system_id=system_id,
        technical_document_id=document.id,
        source_document_reference=document.document_id,
        source_page=source_page,
        source_table=_text(values.source_table, maximum=300),
        source_figure=_text(values.source_figure, maximum=300),
        manufacturer=_text(values.manufacturer, maximum=200),
        product_family=_text(values.product_family, maximum=300),
        service_type=_text(values.service_type, maximum=300),
        service_material=_text(values.service_material, maximum=300),
        minimum_service_size_mm=service_minimum,
        maximum_service_size_mm=service_maximum,
        permitted_service_quantity=_text(
            values.permitted_service_quantity,
            maximum=100,
        ),
        insulation_type=_text(
            values.insulation_type,
            maximum=_INDEXED_LABEL_MAX_LENGTH,
        ),
        insulation_thickness_mm=_number(values.insulation_thickness_mm),
        substrate_type=_text(
            values.substrate_type,
            maximum=_INDEXED_LABEL_MAX_LENGTH,
            multiline=True,
        ),
        minimum_substrate_thickness_mm=substrate_minimum,
        maximum_substrate_thickness_mm=substrate_maximum,
        orientation=_text(values.orientation, maximum=_INDEXED_LABEL_MAX_LENGTH),
        installation_face=_text(
            values.installation_face,
            maximum=_INDEXED_LABEL_MAX_LENGTH,
        ),
        opening_type=_text(values.opening_type, maximum=_INDEXED_LABEL_MAX_LENGTH),
        opening_dimensions=_text(
            values.opening_dimensions,
            maximum=_DESCRIPTION_MAX_LENGTH,
            multiline=True,
        ),
        annular_gap_min_mm=gap_minimum,
        annular_gap_max_mm=gap_maximum,
        service_spacing_rules=_text(
            values.service_spacing_rules,
            maximum=_DETAIL_MAX_LENGTH,
            multiline=True,
        ),
        edge_distance_rules=_text(
            values.edge_distance_rules,
            maximum=_DETAIL_MAX_LENGTH,
            multiline=True,
        ),
        support_rules=_text(
            values.support_rules,
            maximum=_DETAIL_MAX_LENGTH,
            multiline=True,
        ),
        fixing_rules=_text(
            values.fixing_rules,
            maximum=_DETAIL_MAX_LENGTH,
            multiline=True,
        ),
        component_requirements=_component_requirements(values.component_requirements),
        labour_requirements=_labour_requirements(values.labour_requirements),
        hard_exclusions=_text(
            values.hard_exclusions,
            maximum=_DETAIL_MAX_LENGTH,
            multiline=True,
        ),
        dependencies=_text(
            values.dependencies,
            maximum=_DETAIL_MAX_LENGTH,
            multiline=True,
        ),
        frl=_text(values.frl, maximum=100),
        jurisdiction=_text(values.jurisdiction, maximum=200),
        search_eligibility=PENDING_TECHNICAL_REVIEW,
        expert_review_required=True,
        status="draft",
        effective_date=values.effective_date,
        expiry_date=None,
        source_hash=binding.sha256,
        source_json={
            "authoring_method": "ui",
            "automatic_activation_permitted": False,
            "created_by_id": actor.id,
            "intake_policy": TECHNICAL_VARIANT_UI_INTAKE_POLICY,
            "reason": safe_reason,
            "source_document_id": document.document_id,
            "source_file_sha256": binding.sha256,
        },
        release_id=None,
        supersedes_id=None,
    )
    db.add(variant)
    db.flush()
    record_audit(
        db,
        actor=actor,
        action="create_initial_draft",
        entity_type="technical_variant",
        entity_id=variant.id,
        new_value={
            "document_id": document.document_id,
            "expert_review_required": True,
            "release_id": None,
            "search_eligibility": PENDING_TECHNICAL_REVIEW,
            "source_file_sha256": binding.sha256,
            "source_page": source_page,
            "status": "draft",
            "system_id": system_id,
            "variant_id": variant_id,
        },
        reason=safe_reason,
        source_ip=source_ip,
    )
    return variant


__all__ = [
    "TECHNICAL_VARIANT_UI_INTAKE_POLICY",
    "TechnicalVariantDraftInput",
    "TechnicalVariantIntakeError",
    "create_initial_technical_variant_draft",
]
