from __future__ import annotations

import copy
import io

import pytest
from openpyxl import load_workbook
from pypdf import PdfReader
from test_draft_constraint_review import base_case as _base_case
from test_draft_constraint_review import case as _case
from test_draft_constraint_review import inputs
from test_draft_scope import uid
from test_draft_system_matches import counts, create

from classifire.models import User
from classifire.services.draft_constraint_review import results, validate_inputs
from classifire.services.draft_estimates import create_estimate, read_estimate_revision
from classifire.services.draft_scope_reports import create_report, report_bytes
from classifire.services.draft_system_match_contract import envelope_hash, validate_envelope
from classifire.services.draft_system_matches import (
    DraftSystemMatchError,
    read_match_revision,
    revision_bytes,
    save_constraint_review,
    save_review,
)

base_case = _base_case
case = _case


def size_inputs(low="10", high="90", measured="outside_diameter", source="outside_diameter"):
    return {
        **inputs(),
        "service_size_min_mm": low,
        "service_size_max_mm": high,
        "service_size_basis": measured,
        "source_size_basis": source,
        "measurement_note": "Synthetic instances; source page 1 states outside diameter.",
    }


@pytest.mark.parametrize(
    "low,high,measured,source,status",
    [
        ("10", "90", "outside_diameter", "outside_diameter", "within_limits"),
        ("10", "10", "outside_diameter", "outside_diameter", "within_limits"),
        ("90", "90", "outside_diameter", "outside_diameter", "within_limits"),
        ("9.9999", "90", "outside_diameter", "outside_diameter", "outside_limits"),
        ("10", "90.0001", "outside_diameter", "outside_diameter", "outside_limits"),
        (None, "90", "outside_diameter", "outside_diameter", "unresolved"),
        ("10", None, "outside_diameter", "outside_diameter", "unresolved"),
        ("10", "90", "unknown", "outside_diameter", "unresolved"),
        ("10", "90", "outside_diameter", "unknown", "unresolved"),
        ("10", "90", "nominal_diameter", "outside_diameter", "unresolved"),
        ("10", "90", "nominal_diameter", "nominal_diameter", "unresolved"),
        ("10", "90", "bundle_envelope", "outside_diameter", "unresolved"),
        ("10", "90", "rectangular_dimensions", "rectangular_dimensions", "unresolved"),
    ],
)
def test_size_range_requires_explicit_supported_meanings(case, low, high, measured, source, status):
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        match = create(db, case)
        value = read_match_revision(db, actor, case["draft_id"], match.id)
    checks = results(
        value["candidates"][0],
        value["target"],
        size_inputs(low, high, measured, source),
        value["candidates"][0]["fields_sha256"],
        service_size=True,
    )
    assert len(checks) == 3
    assert checks[2]["criterion"] == "measured_service_outside_diameter_range"
    assert checks[2]["status"] == status


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "1e2", "1.00001", True, 10])
def test_invalid_size_measurements_fail_without_coercion(value):
    with pytest.raises(ValueError):
        validate_inputs(size_inputs(low=value), service_size=True)


def test_unknown_source_range_target_and_format_version(case):
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        match = create(db, case)
        value = read_match_revision(db, actor, case["draft_id"], match.id)
    candidate = value["candidates"][0]
    target = value["target"]
    digest = candidate["fields_sha256"]
    for changed, changed_target, fields_hash in (
        (candidate, target, None),
        (candidate, {**target, "service_id": None}, digest),
        (candidate, {**target, "blank_opening": True}, digest),
        (
            {**candidate, "fields": {**candidate["fields"], "minimum_service_size_mm": None}},
            target,
            digest,
        ),
        (
            {
                **candidate,
                "fields": {**candidate["fields"], "maximum_service_size_mm": "ambiguous"},
            },
            target,
            digest,
        ),
    ):
        assert (
            results(changed, changed_target, size_inputs(), fields_hash, service_size=True)[2][
                "status"
            ]
            == "unresolved"
        )
    for invalid in (size_inputs("91", "90"), {**size_inputs(), "source_size_basis": "automatic"}):
        with pytest.raises(ValueError):
            validate_inputs(invalid, service_size=True)
    with pytest.raises(ValueError):
        validate_inputs(size_inputs())  # Old input contract cannot acquire new semantics.
    with pytest.raises(ValueError):
        validate_inputs(inputs(), service_size=True)


def test_v3_history_restart_report_and_no_authority(case):
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        match = create(db, case)
        first = revision_bytes(db, actor, case["draft_id"], match.id)
        save_constraint_review(
            db,
            actor,
            case["draft_id"],
            match.id,
            1,
            case["variant_id"],
            inputs(),
            storage_root=case["storage_root"],
        )
        second = revision_bytes(db, actor, case["draft_id"], match.id)
        before = counts(db)
        saved = save_constraint_review(
            db,
            actor,
            case["draft_id"],
            match.id,
            2,
            case["variant_id"],
            size_inputs(),
            storage_root=case["storage_root"],
            service_size=True,
        )
        assert saved["schema_version"] == "CLASSIFIRE-DRAFT-SYSTEM-MATCH-v3"
        assert saved["constraint_review"]["checks"][2]["status"] == "within_limits"
        assert saved["constraint_review"]["status"] == "partial_unapproved"
        assert (
            "service_type_material_instances_and_size_coverage"
            in saved["constraint_review"]["unassessed"]
        )
        third = revision_bytes(db, actor, case["draft_id"], match.id)
        report = create_report(db, actor, case["draft_id"], 2, match_id=match.id, match_revision=3)
        pdf = report_bytes(db, actor, case["draft_id"], report.id, "pdf")
        xlsx = report_bytes(db, actor, case["draft_id"], report.id, "xlsx")
        assert "Measured Service Outside Diameter Range" in "\n".join(
            p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages
        )
        workbook = load_workbook(io.BytesIO(xlsx))
        values = "\n".join(
            str(c.value) for sheet in workbook for row in sheet for c in row if c.value is not None
        )
        assert "measured_service_outside_diameter_range" in values
        assert "outside_diameter" in values
        workbook.close()
        after = counts(db)
        for table in (
            "estimates",
            "openings",
            "services",
            "physical_model_locks",
            "draft_scope_revisions",
        ):
            assert before[table] == after[table]
        match_id, report_id = match.id, report.id
        db.commit()
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        assert revision_bytes(db, actor, case["draft_id"], match_id, 1) == first
        assert revision_bytes(db, actor, case["draft_id"], match_id, 2) == second
        assert revision_bytes(db, actor, case["draft_id"], match_id, 3) == third
        with pytest.raises(DraftSystemMatchError) as older_client:
            save_constraint_review(
                db,
                actor,
                case["draft_id"],
                match_id,
                3,
                case["variant_id"],
                inputs(),
                storage_root=case["storage_root"],
            )
        assert older_client.value.code == "MATCH_MEASUREMENT_VERSION_REQUIRED"
        decisions = save_review(db, actor, case["draft_id"], match_id, 3, saved["decisions"])
        assert decisions["constraint_review"] == saved["constraint_review"]
        assert decisions["schema_version"] == saved["schema_version"]
        assert report_bytes(db, actor, case["draft_id"], report_id, "pdf") == pdf
        assert report_bytes(db, actor, case["draft_id"], report_id, "xlsx") == xlsx
        changed = copy.deepcopy(saved)
        changed["constraint_review"]["inputs"]["source_size_basis"] = "unknown"
        changed["sha256"] = envelope_hash(changed)
        with pytest.raises(ValueError):
            validate_envelope(changed)


def test_explicit_estimate_accepts_exact_v3_review_without_reinterpreting_size(case):
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        match = create(db, case)
        saved = save_constraint_review(
            db,
            actor,
            case["draft_id"],
            match.id,
            1,
            case["variant_id"],
            size_inputs(),
            storage_root=case["storage_root"],
            service_size=True,
        )
        estimate = create_estimate(
            db,
            actor,
            case["draft_id"],
            2,
            match_id=match.id,
            match_revision=2,
        )
        retained = read_estimate_revision(db, actor, case["draft_id"], estimate.id)
        assert retained["system_match"] == saved
        assert retained["scope"] == saved["scope"]
        assert retained["lines"] == []
        assert retained["review_status"] == "unreviewed"
