"""Evidence-bound property assessments for Phase 8 physical proposals.

This contract is proposal-only. It adds uncertainty, reasoning, provenance,
credible alternatives, and bounded measurement semantics to physical fields
without exposing a database, canonical writer, admission, lock, or release path.
"""

from __future__ import annotations

from collections.abc import Collection
from decimal import Decimal, InvalidOperation
from typing import Any

from .physical_scope import (
    cable_service_semantic_error_codes,
    is_cable_bundle_service,
    is_cable_tray_service,
)

PROPERTY_ASSESSMENT_SCHEMA = "CLASSIFIRE-PHASE8-PROPERTY-ASSESSMENTS-v2"
PROPERTY_ASSESSMENT_STATUSES = frozenset(
    {"CONFIRMED", "APPROXIMATE", "INFERRED", "UNKNOWN"}
)
PROPERTY_ASSESSMENT_CONFIDENCES = frozenset({"HIGH", "MEDIUM", "LOW"})
PROPERTY_MEASUREMENT_UNITS = frozenset({"mm", "cm", "m"})

_OPENING_CODE_FIELD = "opening_code"
_SERVICE_CODE_FIELD = "service_code"
_OPENING_REQUIRED_FIELDS = frozenset(
    {
        "shape",
        "size",
        "opening_type",
        "substrate_plane",
        "substrate_type",
        "substrate_specific_type",
        "substrate_thickness",
        "orientation",
        "opening_boundary",
        "opposite_face_continuity",
    }
)
_SERVICE_REQUIRED_FIELDS = frozenset(
    {
        "quantity",
        "service_type",
        "material",
        "size",
        "insulation_or_covering",
        "arrangement",
        "primary_opening_code",
        "opening_codes",
        "link_type",
        "relationship_status",
        "concealed_continuity",
    }
)
_OPENING_OPTIONAL_FIELDS = frozenset(
    {"width_mm", "height_mm", "diameter_mm", "substrate_thickness_mm", "frl"}
)
_SERVICE_OPTIONAL_FIELDS = frozenset(
    {
        "nominal_size_mm",
        "outside_diameter_mm",
        "width_mm",
        "height_mm",
        "insulation_type",
        "insulation_thickness_mm",
        "cable_count",
        "bundle_size_class",
        "tray_width_mm",
        "tray_height_mm",
    }
)
_PROPOSAL_FIELDS = frozenset(
    {"status", "assessment_schema", "limitations", "openings", "services"}
)
_OPENING_BASE_FIELDS = frozenset(
    {_OPENING_CODE_FIELD, "external_defect_id", "property_assessments"}
)
_SERVICE_BASE_FIELDS = frozenset(
    {
        _SERVICE_CODE_FIELD,
        "evidence_status",
        "source_reference",
        "confidence",
        "property_assessments",
    }
)
_ASSESSMENT_FIELDS = {
    "status",
    "confidence",
    "reasoning",
    "evidence_refs",
    "credible_alternative",
    "additional_evidence_required",
}
_MEASUREMENT_FIELDS = frozenset({"size", "substrate_thickness"})
_POSITIVE_NUMBER_FIELDS = frozenset(
    {
        "width_mm",
        "height_mm",
        "diameter_mm",
        "substrate_thickness_mm",
        "nominal_size_mm",
        "outside_diameter_mm",
        "insulation_thickness_mm",
        "tray_width_mm",
        "tray_height_mm",
    }
)
_POSITIVE_WHOLE_NUMBER_FIELDS = frozenset({"quantity", "cable_count"})
_TEXT_FIELDS = (
    _OPENING_REQUIRED_FIELDS
    | _SERVICE_REQUIRED_FIELDS
    | _OPENING_OPTIONAL_FIELDS
    | _SERVICE_OPTIONAL_FIELDS
) - _MEASUREMENT_FIELDS - _POSITIVE_NUMBER_FIELDS - _POSITIVE_WHOLE_NUMBER_FIELDS - {
    "opening_codes"
}
_MAX_REASONING_LENGTH = 2_000
_MAX_TEXT_LENGTH = 500
_MAX_CODE_LENGTH = 200
_MAX_LIST_ITEMS = 200


def _nonblank(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _positive_decimal(value: object) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() and number > 0 else None


def _validate_measurement(value: object, *, label: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [] if _nonblank(value) and len(value) <= _MAX_TEXT_LENGTH else [
            f"{label} must be bounded text, a structured measurement, or null"
        ]
    if not isinstance(value, dict):
        return [f"{label} must be bounded text, a structured measurement, or null"]
    keys = set(value)
    single = {"value", "unit"}
    ranged = {"minimum", "maximum", "unit"}
    if keys != single and keys != ranged:
        return [f"{label} structured measurement fields are invalid"]
    if value.get("unit") not in PROPERTY_MEASUREMENT_UNITS:
        return [f"{label} structured measurement unit is unsupported"]
    if keys == single:
        if _positive_decimal(value.get("value")) is None:
            return [f"{label} structured measurement value must be positive"]
        return []
    minimum = _positive_decimal(value.get("minimum"))
    maximum = _positive_decimal(value.get("maximum"))
    if minimum is None or maximum is None or minimum > maximum:
        return [f"{label} structured measurement range is invalid"]
    return []


def _is_json_number(value: object) -> bool:
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


def _validate_physical_value(value: object, *, field: str, label: str) -> list[str]:
    if field in _MEASUREMENT_FIELDS:
        return _validate_measurement(value, label=label)
    if field in _POSITIVE_NUMBER_FIELDS:
        if value is None:
            return []
        if not _is_json_number(value) or _positive_decimal(value) is None:
            return [f"{label} must be a positive finite number or null"]
        return []
    if field in _POSITIVE_WHOLE_NUMBER_FIELDS:
        if value is None:
            return []
        number = _positive_decimal(value) if _is_json_number(value) else None
        if number is None or number != number.to_integral_value():
            return [f"{label} must be a positive whole number or null"]
        return []
    if field == "opening_codes":
        if (
            not isinstance(value, list)
            or not value
            or any(not _nonblank(item) for item in value)
            or any(len(_nonblank(item)) > _MAX_CODE_LENGTH for item in value)
            or len(value) > _MAX_LIST_ITEMS
            or len(value) != len({_nonblank(item) for item in value})
        ):
            return [f"{label} must be a non-empty array of unique opening codes"]
        return []
    if field in _TEXT_FIELDS:
        if value is None:
            return []
        if not _nonblank(value) or len(str(value)) > _MAX_TEXT_LENGTH:
            return [f"{label} must be bounded text or null"]
        return []
    return [f"{label} uses an unsupported physical value field"]


def _rows_by_code(
    payload: Any,
    *,
    collection: str,
    code_field: str,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    if not isinstance(payload, dict):
        return {}, ["physical proposal must be an object"]
    rows = payload.get(collection)
    if not isinstance(rows, list):
        return {}, [f"physical proposal {collection} must be an array"]
    result: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"{collection} record {index} must be an object")
            continue
        code = _nonblank(row.get(code_field))
        if not code:
            errors.append(f"{collection} record {index} requires {code_field}")
            continue
        if len(code) > _MAX_CODE_LENGTH:
            errors.append(f"{collection} record {index} {code_field} is too long")
            continue
        if code in result:
            errors.append(f"{collection} code is duplicated: {code}")
            continue
        result[code] = row
    return result, errors


def _field_sets(subject: str) -> tuple[frozenset[str], frozenset[str]]:
    if subject == "Opening":
        return _OPENING_REQUIRED_FIELDS, _OPENING_OPTIONAL_FIELDS
    return _SERVICE_REQUIRED_FIELDS, _SERVICE_OPTIONAL_FIELDS


def physical_property_fields_for_subject(subject: str) -> frozenset[str]:
    """Return the complete approved property vocabulary for one review subject."""

    required, optional = _field_sets(subject)
    return required | optional


def required_physical_property_fields_for_subject(subject: str) -> frozenset[str]:
    """Return the properties that every supported row must assess."""

    required, _optional = _field_sets(subject)
    return required


def validate_physical_property_value(
    value: object,
    *,
    field: str,
    label: str,
) -> list[str]:
    """Validate one physical value using the proposal contract's field semantics."""

    return _validate_physical_value(value, field=field, label=label)


def _fields_to_assess(row: dict[str, Any], *, subject: str) -> frozenset[str]:
    required, optional = _field_sets(subject)
    fields = set(required)
    fields.update(field for field in optional if field in row)
    if subject == "Service" and is_cable_bundle_service(row.get("service_type")):
        fields.add("cable_count")
        if row.get("cable_count") is None or "bundle_size_class" in row:
            fields.add("bundle_size_class")
    if subject == "Service" and is_cable_tray_service(row.get("service_type")):
        fields.update({"tray_width_mm", "tray_height_mm"})
    return frozenset(fields)


def _validate_assessment(
    assessment: Any,
    *,
    subject: str,
    code: str,
    field: str,
    value: Any,
    allowed_evidence_refs: frozenset[str] | None,
) -> list[str]:
    label = f"{subject} {code} property assessment {field}"
    if not isinstance(assessment, dict):
        return [f"{label} must be an object"]
    errors: list[str] = []
    if set(assessment) != _ASSESSMENT_FIELDS:
        errors.append(f"{label} fields do not match the approved schema")

    status = assessment.get("status")
    if status not in PROPERTY_ASSESSMENT_STATUSES:
        errors.append(f"{label} has unsupported status")
    confidence = assessment.get("confidence")
    if status in {"APPROXIMATE", "INFERRED"}:
        if confidence not in PROPERTY_ASSESSMENT_CONFIDENCES:
            errors.append(f"{label} requires HIGH, MEDIUM, or LOW confidence")
    elif confidence is not None:
        errors.append(f"{label} confidence must be null unless status is approximate or inferred")

    reasoning = _nonblank(assessment.get("reasoning"))
    if not reasoning or len(reasoning) > _MAX_REASONING_LENGTH:
        errors.append(f"{label} requires bounded reasoning")

    evidence_refs = assessment.get("evidence_refs")
    if (
        not isinstance(evidence_refs, list)
        or not evidence_refs
        or any(not _nonblank(item) for item in evidence_refs)
        or any(len(_nonblank(item)) > _MAX_TEXT_LENGTH for item in evidence_refs)
        or len(evidence_refs) > _MAX_LIST_ITEMS
        or len(evidence_refs) != len({_nonblank(item) for item in evidence_refs})
    ):
        errors.append(f"{label} requires unique non-empty evidence_refs")
    elif allowed_evidence_refs is not None and not {
        _nonblank(item) for item in evidence_refs
    }.issubset(allowed_evidence_refs):
        errors.append(f"{label} references evidence outside the approved manifest")

    alternative = assessment.get("credible_alternative")
    if alternative is not None and (
        not _nonblank(alternative) or len(str(alternative)) > _MAX_TEXT_LENGTH
    ):
        errors.append(f"{label} credible_alternative must be bounded text or null")
    if status == "CONFIRMED" and alternative is not None:
        errors.append(f"{label} confirmed status cannot retain a credible alternative")

    evidence_required = assessment.get("additional_evidence_required")
    if evidence_required is not None and (
        not _nonblank(evidence_required) or len(str(evidence_required)) > _MAX_TEXT_LENGTH
    ):
        errors.append(f"{label} additional_evidence_required must be bounded text or null")

    if status == "UNKNOWN" and value is not None:
        errors.append(f"{label} cannot be UNKNOWN while the proposal supplies a value")
    if status in {"CONFIRMED", "APPROXIMATE", "INFERRED"} and value is None:
        errors.append(f"{label} requires UNKNOWN when the proposal value is null")
    return errors


def _validate_record(
    row: dict[str, Any],
    *,
    subject: str,
    code_field: str,
    allowed_evidence_refs: frozenset[str] | None,
) -> list[str]:
    code = _nonblank(row.get(code_field)) or "?"
    errors: list[str] = []
    if subject == "Service":
        errors.extend(
            f"Service {code} {item}" for item in cable_service_semantic_error_codes(row)
        )

    raw = row.get("property_assessments")
    if not isinstance(raw, dict):
        return [*errors, f"{subject} {code} requires property_assessments"]
    required, optional = _field_sets(subject)
    allowed = required | optional
    base_fields = _OPENING_BASE_FIELDS if subject == "Opening" else _SERVICE_BASE_FIELDS
    fields_to_assess = _fields_to_assess(row, subject=subject)

    unsupported_physical = sorted(set(row) - allowed - base_fields)
    if unsupported_physical:
        errors.append(
            f"{subject} {code} includes unsupported physical fields: "
            + ", ".join(unsupported_physical)
        )

    missing_physical = sorted(field for field in required if field not in row)
    if missing_physical:
        errors.append(
            f"{subject} {code} is missing required physical fields: "
            + ", ".join(missing_physical)
        )
    unexpected = sorted(set(raw) - allowed)
    if unexpected:
        errors.append(
            f"{subject} {code} property_assessments include unsupported fields: "
            + ", ".join(unexpected)
        )
    missing = sorted(fields_to_assess - set(raw))
    if missing:
        errors.append(
            f"{subject} {code} property_assessments are missing required fields: "
            + ", ".join(missing)
        )
    detached = sorted(field for field in set(raw) & optional if field not in row)
    if detached:
        errors.append(
            f"{subject} {code} property_assessments have no matching physical field: "
            + ", ".join(detached)
        )

    for field in fields_to_assess:
        value = row.get(field)
        label = f"{subject} {code} {field}"
        errors.extend(_validate_physical_value(value, field=field, label=label))
        errors.extend(
            _validate_assessment(
                raw.get(field),
                subject=subject,
                code=code,
                field=field,
                value=value,
                allowed_evidence_refs=allowed_evidence_refs,
            )
        )
    return errors


def validate_physical_property_assessments(
    payload: Any,
    *,
    allowed_evidence_refs: Collection[str] | None = None,
) -> list[str]:
    """Validate one v2 property-assessment payload."""

    if not isinstance(payload, dict):
        return ["physical proposal must be an object"]
    if payload.get("assessment_schema") != PROPERTY_ASSESSMENT_SCHEMA:
        return ["physical proposal property assessment schema is unsupported"]

    errors = []
    unsupported_payload = sorted(set(payload) - _PROPOSAL_FIELDS)
    if unsupported_payload:
        errors.append(
            "physical proposal includes unsupported top-level fields: "
            + ", ".join(unsupported_payload)
        )

    allowed: frozenset[str] | None = None
    if allowed_evidence_refs is not None:
        values = [_nonblank(item) for item in allowed_evidence_refs]
        if any(not item for item in values) or len(values) != len(set(values)):
            return ["approved property-assessment evidence references are invalid"]
        allowed = frozenset(values)

    status = _nonblank(payload.get("status")).upper()
    if status != "MODEL_SUPPORTED":
        return errors
    openings, opening_errors = _rows_by_code(
        payload,
        collection="openings",
        code_field=_OPENING_CODE_FIELD,
    )
    services, service_errors = _rows_by_code(
        payload,
        collection="services",
        code_field=_SERVICE_CODE_FIELD,
    )
    errors.extend((*opening_errors, *service_errors))
    for row in openings.values():
        errors.extend(
            _validate_record(
                row,
                subject="Opening",
                code_field=_OPENING_CODE_FIELD,
                allowed_evidence_refs=allowed,
            )
        )
    for row in services.values():
        errors.extend(
            _validate_record(
                row,
                subject="Service",
                code_field=_SERVICE_CODE_FIELD,
                allowed_evidence_refs=allowed,
            )
        )
    return list(dict.fromkeys(errors))


def _field_issue_codes(*, subject: str, field: str) -> frozenset[str]:
    topology = {
        "MISSED_OPENING",
        "OVER_MERGED_OPENING",
        "DUPLICATED_OPENING",
        "OVER_SPLIT_OPENING",
    }
    if subject == "Opening":
        if field in {
            "substrate_type",
            "substrate_specific_type",
            "substrate_plane",
            "orientation",
        }:
            return frozenset({"MISSED_BARRIER", "WRONG_BARRIER", "WRONG_BARRIER_PLANE"})
        if field in {
            "size",
            "substrate_thickness",
            "width_mm",
            "height_mm",
            "diameter_mm",
            "substrate_thickness_mm",
        }:
            return frozenset({"UNSUPPORTED_DIMENSION"})
        if field in {"shape", "opening_boundary"}:
            return frozenset({"WRONG_OPENING_SHAPE", "UNSUPPORTED_DIMENSION"})
        if field == "opposite_face_continuity":
            return frozenset({"OPPOSITE_FACE_DOUBLE_COUNTED", "WRONG_BARRIER"})
        if field == "opening_type":
            return frozenset(topology)
        if field == "frl":
            return frozenset({"UNSUPPORTED_FRL"})
        return frozenset()

    if field in {
        "primary_opening_code",
        "opening_codes",
        "link_type",
        "relationship_status",
        "concealed_continuity",
    }:
        return frozenset({"WRONG_SERVICE_OPENING_LINK", *topology})
    if field == "service_type":
        return frozenset({"WRONG_SERVICE_CLASS"})
    if field in {"material", "insulation_type", "insulation_or_covering"}:
        return frozenset({"UNSUPPORTED_MATERIAL"})
    if field in {
        "size",
        "nominal_size_mm",
        "outside_diameter_mm",
        "width_mm",
        "height_mm",
        "insulation_thickness_mm",
        "bundle_size_class",
        "tray_width_mm",
        "tray_height_mm",
    }:
        return frozenset({"UNSUPPORTED_DIMENSION"})
    if field in {"quantity", "arrangement", "cable_count"}:
        return frozenset({"WRONG_SERVICE_GROUPING", "WRONG_SERVICE_QUANTITY"})
    return frozenset()


def _targeted_issue_codes(
    validator: Any,
    *,
    subject: str,
    code: str,
    field: str,
) -> frozenset[str]:
    if not isinstance(validator, dict) or not isinstance(validator.get("issues"), list):
        return frozenset()
    return frozenset(
        str(issue.get("code") or "").strip().upper()
        for issue in validator["issues"]
        if isinstance(issue, dict)
        and str(issue.get("subject") or "").strip().casefold() == subject.casefold()
        and _nonblank(issue.get("subject_code")) == code
        and _nonblank(issue.get("property")) == field
    )


def validate_property_assessment_correction_scope(
    previous: Any,
    corrected: Any,
    *,
    validator: Any,
) -> list[str]:
    """Require field-targeted authority for every v2 property correction."""

    errors: list[str] = []
    for subject, collection, code_field in (
        ("Opening", "openings", _OPENING_CODE_FIELD),
        ("Service", "services", _SERVICE_CODE_FIELD),
    ):
        before_rows, before_errors = _rows_by_code(
            previous,
            collection=collection,
            code_field=code_field,
        )
        after_rows, after_errors = _rows_by_code(
            corrected,
            collection=collection,
            code_field=code_field,
        )
        errors.extend(before_errors)
        errors.extend(after_errors)
        for code in sorted(before_rows.keys() & after_rows.keys()):
            before = before_rows[code]
            after = after_rows[code]
            before_assessments = before.get("property_assessments")
            after_assessments = after.get("property_assessments")
            if not isinstance(before_assessments, dict) or not isinstance(
                after_assessments, dict
            ):
                errors.append(f"{subject} {code} property assessments must be preserved")
                continue
            for field in sorted(set(before_assessments) | set(after_assessments)):
                physical_changed = before.get(field) != after.get(field)
                assessment_changed = before_assessments.get(field) != after_assessments.get(field)
                if not physical_changed and not assessment_changed:
                    continue
                authority = _targeted_issue_codes(
                    validator,
                    subject=subject,
                    code=code,
                    field=field,
                )
                if physical_changed and not assessment_changed:
                    errors.append(
                        f"{subject} {code} property assessment {field!r} must change "
                        "with its physical field"
                    )
                if physical_changed and not (authority & _field_issue_codes(
                    subject=subject,
                    field=field,
                )):
                    errors.append(
                        f"validator issues do not authorize {subject} {code} "
                        f"property {field!r} to change"
                    )
                if (
                    assessment_changed
                    and not physical_changed
                    and "UNSUPPORTED_PROPERTY_ASSESSMENT" not in authority
                ):
                    errors.append(
                        f"validator issues do not authorize {subject} {code} "
                        f"property assessment {field!r} to change alone"
                    )
    return list(dict.fromkeys(errors))


__all__ = [
    "PROPERTY_ASSESSMENT_CONFIDENCES",
    "PROPERTY_ASSESSMENT_SCHEMA",
    "PROPERTY_ASSESSMENT_STATUSES",
    "PROPERTY_MEASUREMENT_UNITS",
    "physical_property_fields_for_subject",
    "required_physical_property_fields_for_subject",
    "validate_physical_property_assessments",
    "validate_physical_property_value",
    "validate_property_assessment_correction_scope",
]
