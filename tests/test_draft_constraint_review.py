from __future__ import annotations

import copy

import pytest
from test_draft_scope import uid
from test_draft_system_matches import case as _case
from test_draft_system_matches import counts, create

from classifire.models import TechnicalVariant, User
from classifire.services.draft_constraint_review import results, validate_inputs
from classifire.services.draft_system_match_contract import envelope_hash, validate_envelope
from classifire.services.draft_system_matches import (
    DraftSystemMatchError,
    read_match_revision,
    revision_bytes,
    save_constraint_review,
    save_review,
)
from classifire.services.technical_release_publication import publish_governed_technical_release

base_case = _case


@pytest.fixture
def case(base_case):
    case = dict(base_case)
    with case["factory"]() as db:
        variant = db.get(TechnicalVariant, case["variant_id"])
        variant.minimum_substrate_thickness_mm = 100
        variant.maximum_substrate_thickness_mm = 200
        variant.annular_gap_min_mm = 10
        variant.annular_gap_max_mm = 30
        release = publish_governed_technical_release(
            db,
            version="SYNTHETIC-LIMITS-2",
            notes="Synthetic numeric test only",
            actor=db.get(User, uid(102)),
            storage_root=case["storage_root"],
        )
        case["release_id"] = release.id
        db.commit()
    return case


def inputs(thickness="100", low="10", high="30"):
    return dict(
        substrate_thickness_mm=thickness,
        annular_gap_min_mm=low,
        annular_gap_max_mm=high,
        measurement_note="Synthetic measurement: page 1, all gaps",
    )


@pytest.mark.parametrize(
    "thickness,low,high,expected",
    [
        ("100", "10", "30", ["within_limits", "within_limits"]),
        ("200", "10", "30", ["within_limits", "within_limits"]),
        ("99.9999", "10", "30", ["outside_limits", "within_limits"]),
        ("200.0001", "10", "30", ["outside_limits", "within_limits"]),
        ("150", "9.9999", "30", ["within_limits", "outside_limits"]),
        ("150", "10", "30.0001", ["within_limits", "outside_limits"]),
        (None, None, None, ["unresolved", "unresolved"]),
        ("150", "10", None, ["within_limits", "unresolved"]),
    ],
)
def test_inclusive_numeric_ranges_and_missing_values(thickness, low, high, expected):
    candidate = {
        "fields": {
            "minimum_substrate_thickness_mm": "100.0000",
            "maximum_substrate_thickness_mm": "200.0000",
            "annular_gap_min_mm": "10.0000",
            "annular_gap_max_mm": "30.0000",
        },
        "fields_sha256": "a" * 64,
        "source": {"state": "bound"},
    }
    target = {"opening_id": "opening", "service_id": "service", "blank_opening": False}
    checks = results(candidate, target, inputs(thickness, low, high), "a" * 64)
    assert [item["status"] for item in checks] == expected
    assert all(
        item["status"] == "unresolved" for item in results(candidate, target, inputs(), None)
    )
    candidate["fields"]["minimum_substrate_thickness_mm"] = "ambiguous"
    assert results(candidate, target, inputs(), "a" * 64)[0]["status"] == "unresolved"
    candidate["fields"]["minimum_substrate_thickness_mm"] = "201"
    assert (
        results(candidate, target, inputs(), "a" * 64)[0]["reason"] == "source_limits_inconsistent"
    )
    target["service_id"] = None
    assert results(candidate, target, inputs(), "a" * 64)[1]["status"] == "unresolved"


@pytest.mark.parametrize(
    "value", ["NaN", "Infinity", "-1", "1e2", "1,000", "1.12345", "", True, 100]
)
def test_measurements_reject_ambiguous_units_and_nonfinite_values(value):
    with pytest.raises(ValueError):
        validate_inputs(inputs(thickness=value))


def test_reversed_range_and_missing_measurement_lineage():
    with pytest.raises(ValueError):
        validate_inputs(inputs(low="31", high="30"))
    with pytest.raises(ValueError):
        validate_inputs({**inputs(), "measurement_note": " "})


def test_saved_checks_restart_old_history_tamper_and_no_authority(case):
    with case["factory"]() as db:
        match = create(db, case)
        actor = db.get(User, uid(100))
        before = counts(db)
        first = revision_bytes(db, actor, case["draft_id"], match.id)
        saved = save_constraint_review(
            db,
            actor,
            case["draft_id"],
            match.id,
            1,
            case["variant_id"],
            inputs(),
            storage_root=case["storage_root"],
        )
        assert saved["schema_version"] == "CLASSIFIRE-DRAFT-SYSTEM-MATCH-v2"
        assert [item["status"] for item in saved["constraint_review"]["checks"]] == [
            "within_limits"
        ] * 2
        assert saved["review_status"] == "unreviewed"
        assert saved["constraint_review"]["unassessed"]
        second = revision_bytes(db, actor, case["draft_id"], match.id, 2)
        third = save_review(db, actor, case["draft_id"], match.id, 2, saved["decisions"])
        assert third["constraint_review"] == saved["constraint_review"]
        assert revision_bytes(db, actor, case["draft_id"], match.id, 1) == first
        after = counts(db)
        for table in (
            "estimates",
            "openings",
            "services",
            "physical_model_locks",
            "draft_scope_revisions",
        ):
            assert after[table] == before[table]
        match_id = match.id
        db.commit()
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        assert revision_bytes(db, actor, case["draft_id"], match_id, 2) == second
        assert read_match_revision(db, actor, case["draft_id"], match_id)["revision"] == 3
    tampered = copy.deepcopy(saved)
    tampered["constraint_review"]["checks"][0]["status"] = "applicable"
    tampered["sha256"] = envelope_hash(tampered)
    with pytest.raises(ValueError):
        validate_envelope(tampered)


def test_stale_revision_source_and_permission_denied(case):
    with case["factory"]() as db:
        match = create(db, case)
        actor = db.get(User, uid(100))
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
        with pytest.raises(DraftSystemMatchError, match="MATCH_REVISION_CONFLICT"):
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
        with pytest.raises(DraftSystemMatchError):
            save_constraint_review(
                db,
                db.get(User, uid(101)),
                case["draft_id"],
                match.id,
                2,
                case["variant_id"],
                inputs(),
                storage_root=case["storage_root"],
            )
        case["source_path"].write_bytes(b"changed synthetic source")
        with pytest.raises(DraftSystemMatchError, match="MATCH_BASIS_STALE"):
            save_constraint_review(
                db,
                actor,
                case["draft_id"],
                match.id,
                2,
                case["variant_id"],
                inputs(),
                storage_root=case["storage_root"],
            )
        assert read_match_revision(db, actor, case["draft_id"], match.id)["revision"] == 2


def test_unversioned_limit_drift_blocks_new_checks(case):
    with case["factory"]() as db:
        match = create(db, case)
        actor = db.get(User, uid(100))
        db.get(TechnicalVariant, case["variant_id"]).minimum_substrate_thickness_mm = 99
        db.flush()
        with pytest.raises(DraftSystemMatchError, match="MATCH_RELEASE_INVALID"):
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
        assert read_match_revision(db, actor, case["draft_id"], match.id)["revision"] == 1


def test_older_release_cannot_gain_published_limit_authority(case):
    from classifire.models import LibraryRelease
    from classifire.services.release_scope import _manifest_hash

    with case["factory"]() as db:
        release = db.get(LibraryRelease, case["release_id"])
        manifest = copy.deepcopy(release.source_manifest)
        manifest["schema"] = "CLASSIFIRE-TECHNICAL-LIBRARY-RELEASE-v2"
        for record in manifest["records"]:
            del record["technical_fields"]
        release.source_manifest = manifest
        release.release_hash = _manifest_hash(manifest)
        db.flush()
        match = create(db, case)
        saved = save_constraint_review(
            db,
            db.get(User, uid(100)),
            case["draft_id"],
            match.id,
            1,
            case["variant_id"],
            inputs(),
            storage_root=case["storage_root"],
        )
        assert saved["constraint_review"]["published_fields_sha256"] is None
        assert all(item["status"] == "unresolved" for item in saved["constraint_review"]["checks"])


def test_saved_v2_remains_independent_and_marks_dependent_estimate_stale(case):
    from classifire.services import draft_estimates

    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        match = create(db, case)
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
        estimate = draft_estimates.create_estimate(
            db,
            actor,
            case["draft_id"],
            2,
            match_id=match.id,
            match_revision=2,
        )
        before = draft_estimates.revision_bytes(db, actor, case["draft_id"], estimate.id)
        save_constraint_review(
            db,
            actor,
            case["draft_id"],
            match.id,
            2,
            case["variant_id"],
            inputs(thickness="201"),
            storage_root=case["storage_root"],
        )
        assert draft_estimates.revision_bytes(db, actor, case["draft_id"], estimate.id) == before
        assert draft_estimates.estimate_staleness(
            db, actor, case["draft_id"], estimate.id, storage_root=case["storage_root"]
        )
