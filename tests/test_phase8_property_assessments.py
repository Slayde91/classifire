from __future__ import annotations

from copy import deepcopy
from typing import Any

from classifire.services.phase8_property_assessments import (
    PROPERTY_ASSESSMENT_SCHEMA,
    validate_physical_property_assessments,
    validate_property_assessment_correction_scope,
)


def _assessment(
    value: object,
    *,
    status: str | None = None,
    confidence: str | None = None,
    alternative: str | None = None,
    evidence: str = "E-001",
) -> dict[str, Any]:
    chosen = status or ("UNKNOWN" if value is None else "CONFIRMED")
    return {
        "status": chosen,
        "confidence": confidence,
        "reasoning": "The supplied evidence supports this bounded assessment.",
        "evidence_refs": [evidence],
        "credible_alternative": alternative,
        "additional_evidence_required": None,
    }


def _proposal() -> dict[str, Any]:
    opening = {
        "external_defect_id": "D-001",
        "opening_code": "O-001",
        "shape": "circular",
        "size": {"minimum": 100, "maximum": 125, "unit": "mm"},
        "opening_type": "service_penetration",
        "substrate_plane": "wall",
        "substrate_type": "masonry",
        "substrate_specific_type": "solid concrete blockwork",
        "substrate_thickness": {"value": 100, "unit": "mm"},
        "orientation": "vertical",
        "opening_boundary": "visible circular edge",
        "opposite_face_continuity": None,
    }
    service = {
        "service_code": "S-001",
        "quantity": 1,
        "service_type": "pipe",
        "material": "PVC",
        "size": {"value": 50, "unit": "mm"},
        "insulation_or_covering": "uninsulated",
        "arrangement": "single service",
        "primary_opening_code": "O-001",
        "opening_codes": ["O-001"],
        "link_type": "penetrates",
        "relationship_status": "confirmed",
        "concealed_continuity": None,
        "evidence_status": "confirmed",
        "source_reference": "E-001",
        "confidence": "0.9",
    }
    opening["property_assessments"] = {
        field: _assessment(opening[field])
        for field in (
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
        )
    }
    opening["property_assessments"]["size"] = _assessment(
        opening["size"],
        status="APPROXIMATE",
        confidence="HIGH",
        alternative="approximately 125-150 mm",
    )
    service["property_assessments"] = {
        field: _assessment(service[field])
        for field in (
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
        )
    }
    return {
        "status": "MODEL_SUPPORTED",
        "assessment_schema": PROPERTY_ASSESSMENT_SCHEMA,
        "limitations": ["The opposite face is not visible."],
        "openings": [opening],
        "services": [service],
    }


def test_v2_assessments_accept_ranges_alternatives_and_manifest_evidence() -> None:
    assert (
        validate_physical_property_assessments(
            _proposal(),
            allowed_evidence_refs={"E-001"},
        )
        == []
    )


def test_unknown_and_estimated_values_have_strict_confidence_semantics() -> None:
    proposal = _proposal()
    material = proposal["services"][0]["property_assessments"]["material"]
    material["status"] = "UNKNOWN"
    estimated = proposal["openings"][0]["property_assessments"]["size"]
    estimated["confidence"] = None

    errors = validate_physical_property_assessments(
        proposal,
        allowed_evidence_refs={"E-001"},
    )

    assert any("cannot be UNKNOWN" in error for error in errors)
    assert any("requires HIGH, MEDIUM, or LOW" in error for error in errors)


def test_every_supplied_optional_field_requires_matching_assessment() -> None:
    proposal = _proposal()
    proposal["openings"][0]["diameter_mm"] = 110

    errors = validate_physical_property_assessments(
        proposal,
        allowed_evidence_refs={"E-001"},
    )

    assert any("diameter_mm" in error and "missing required" in error for error in errors)

    proposal = _proposal()
    proposal["openings"][0]["frl"] = "-/120/120"
    errors = validate_physical_property_assessments(
        proposal,
        allowed_evidence_refs={"E-001"},
    )
    assert any("frl" in error and "missing required" in error for error in errors)


def test_undeclared_proposal_and_row_fields_are_rejected() -> None:
    proposal = _proposal()
    proposal["technical_system"] = "not part of physical assessment"
    proposal["openings"][0]["technical_system"] = "not allowed"
    proposal["services"][0]["commercial_rate"] = 123

    errors = validate_physical_property_assessments(
        proposal,
        allowed_evidence_refs={"E-001"},
    )

    assert any("unsupported top-level fields" in error for error in errors)
    assert any("Opening O-001" in error and "technical_system" in error for error in errors)
    assert any("Service S-001" in error and "commercial_rate" in error for error in errors)


def test_opening_link_codes_are_bounded() -> None:
    proposal = _proposal()
    proposal["services"][0]["opening_codes"] = ["O-" + ("x" * 500)]

    errors = validate_physical_property_assessments(
        proposal,
        allowed_evidence_refs={"E-001"},
    )

    assert any("opening_codes" in error for error in errors)


def test_out_of_manifest_reference_is_rejected() -> None:
    proposal = _proposal()
    proposal["services"][0]["property_assessments"]["material"]["evidence_refs"] = [
        "E-OUTSIDE"
    ]

    errors = validate_physical_property_assessments(
        proposal,
        allowed_evidence_refs={"E-001"},
    )

    assert any("outside the approved manifest" in error for error in errors)


def test_property_values_reject_invalid_types_negative_sizes_and_fractional_counts() -> None:
    proposal = _proposal()
    opening = proposal["openings"][0]
    service = proposal["services"][0]
    opening["diameter_mm"] = -100
    opening["property_assessments"]["diameter_mm"] = _assessment(-100)
    service["arrangement"] = {"invented": True}
    service["quantity"] = 1.5

    errors = validate_physical_property_assessments(
        proposal,
        allowed_evidence_refs={"E-001"},
    )

    assert any("diameter_mm must be a positive finite number" in error for error in errors)
    assert any("arrangement must be bounded text or null" in error for error in errors)
    assert any("quantity must be a positive whole number" in error for error in errors)


def _cable_bundle(*, cable_count: int | None) -> dict[str, Any]:
    proposal = _proposal()
    service = proposal["services"][0]
    service["service_type"] = "cable_bundle"
    service["cable_count"] = cable_count
    service["property_assessments"]["cable_count"] = _assessment(cable_count)
    if cable_count is None:
        service["bundle_size_class"] = "medium"
        service["property_assessments"]["bundle_size_class"] = _assessment(
            "medium",
            status="INFERRED",
            confidence="MEDIUM",
        )
    return proposal


def test_known_cable_count_does_not_require_bundle_class() -> None:
    assert (
        validate_physical_property_assessments(
            _cable_bundle(cable_count=8),
            allowed_evidence_refs={"E-001"},
        )
        == []
    )


def test_unknown_cable_count_requires_bundle_class() -> None:
    proposal = _cable_bundle(cable_count=None)
    del proposal["services"][0]["bundle_size_class"]
    del proposal["services"][0]["property_assessments"]["bundle_size_class"]

    errors = validate_physical_property_assessments(
        proposal,
        allowed_evidence_refs={"E-001"},
    )

    assert any("CABLE_BUNDLE_SIZE_CLASS_REQUIRED" in error for error in errors)


def test_tray_and_bundle_specific_fields_cannot_leak_between_service_types() -> None:
    proposal = _proposal()
    service = proposal["services"][0]
    service["service_type"] = "cable_tray"
    service["tray_width_mm"] = 300
    service["tray_height_mm"] = None
    service["property_assessments"]["tray_width_mm"] = _assessment(
        300,
        status="APPROXIMATE",
        confidence="MEDIUM",
    )
    service["property_assessments"]["tray_height_mm"] = _assessment(None)

    assert (
        validate_physical_property_assessments(
            proposal,
            allowed_evidence_refs={"E-001"},
        )
        == []
    )

    service["cable_count"] = 10
    service["property_assessments"]["cable_count"] = _assessment(10)
    errors = validate_physical_property_assessments(
        proposal,
        allowed_evidence_refs={"E-001"},
    )
    assert any("CABLE_TRAY_BUNDLE_FIELDS_INVALID" in error for error in errors)


def test_assessment_only_correction_requires_exact_target() -> None:
    previous = _proposal()
    corrected = deepcopy(previous)
    corrected["openings"][0]["property_assessments"]["size"]["confidence"] = "MEDIUM"
    wrong_target = {
        "issues": [
            {
                "code": "UNSUPPORTED_PROPERTY_ASSESSMENT",
                "subject": "Service",
                "subject_code": "S-001",
                "property": "size",
            }
        ]
    }

    errors = validate_property_assessment_correction_scope(
        previous,
        corrected,
        validator=wrong_target,
    )
    assert any("change alone" in error for error in errors)

    exact_target = deepcopy(wrong_target)
    exact_target["issues"][0].update(
        {"subject": "Opening", "subject_code": "O-001"}
    )
    assert (
        validate_property_assessment_correction_scope(
            previous,
            corrected,
            validator=exact_target,
        )
        == []
    )


def test_physical_correction_requires_matching_assessment_and_targeted_issue() -> None:
    previous = _proposal()
    corrected = deepcopy(previous)
    corrected["services"][0]["quantity"] = 2
    validator = {
        "issues": [
            {
                "code": "WRONG_SERVICE_QUANTITY",
                "subject": "Service",
                "subject_code": "S-001",
                "property": "quantity",
            }
        ]
    }
    errors = validate_property_assessment_correction_scope(
        previous,
        corrected,
        validator=validator,
    )
    assert any("must change with its physical field" in error for error in errors)

    corrected["services"][0]["property_assessments"]["quantity"]["reasoning"] = (
        "Two distinct groups are supported by the supplied evidence."
    )
    assert (
        validate_property_assessment_correction_scope(
            previous,
            corrected,
            validator=validator,
        )
        == []
    )


def test_frl_correction_requires_explicit_frl_issue_authority() -> None:
    previous = _proposal()
    opening = previous["openings"][0]
    opening["frl"] = "-/120/120"
    opening["property_assessments"]["frl"] = _assessment("-/120/120")
    corrected = deepcopy(previous)
    corrected_opening = corrected["openings"][0]
    corrected_opening["frl"] = "-/90/90"
    corrected_opening["property_assessments"]["frl"]["reasoning"] = (
        "The report annotation supports the corrected required FRL."
    )
    validator = {
        "issues": [
            {
                "code": "UNSUPPORTED_FRL",
                "subject": "Opening",
                "subject_code": "O-001",
                "property": "frl",
            }
        ]
    }

    assert (
        validate_property_assessment_correction_scope(
            previous,
            corrected,
            validator=validator,
        )
        == []
    )
    wrong_authority = deepcopy(validator)
    wrong_authority["issues"][0]["code"] = "UNSUPPORTED_DIMENSION"
    errors = validate_property_assessment_correction_scope(
        previous,
        corrected,
        validator=wrong_authority,
    )
    assert any("do not authorize Opening O-001 property 'frl'" in error for error in errors)
