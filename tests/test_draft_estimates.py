from __future__ import annotations

import copy
from decimal import Decimal

import pytest
from sqlalchemy import func, select, update
from test_draft_scope import sample_payload, setup, uid  # noqa: F401
from test_draft_system_matches import case as match_case  # noqa: F401

from classifire.models import (
    AuditEvent,
    DraftEstimate,
    DraftEstimateRevision,
    Estimate,
    Opening,
    Service,
    User,
)
from classifire.physical_models import PhysicalModelLock
from classifire.services import draft_estimates as service
from classifire.services.draft_estimate_contract import (
    decimal_string,
    line_amount,
    validate_envelope,
)
from classifire.services.draft_scope import create_draft_project, save_revision


def add_payload(**changes):
    return {
        "target_kind": "service",
        "target_id": uid(5),
        "unit": "each",
        "quantity": "2",
        "unit_sell_rate": "1.005",
        "description": "Synthetic service-only work",
        "source_note": "Manual fixture rate excluding shared closure",
        "reason": "",
        **changes,
    }


def prepare(db):
    actor = db.get(User, uid(100))
    draft = create_draft_project(db, actor, "SYNTHETIC-ESTIMATE", "Manual estimate")
    save_revision(db, actor, draft.id, 1, sample_payload())
    estimate = service.create_estimate(db, actor, draft.id, 2)
    db.commit()
    return actor, draft, estimate


@pytest.mark.parametrize(
    ("quantity", "rate", "amount"),
    [
        ("2", "1.005", "2.01"),
        ("3", "0.333333", "1.00"),
        ("0.000001", "0.000001", "0.00"),
        ("1", "0.005", "0.01"),
        ("999999999.999999", "999999999.999999", "999999999999998000.00"),
        (None, "1", None),
        ("0", None, None),
        ("0", "100", "0.00"),
    ],
)
def test_direct_six_decimal_unit_sell_arithmetic(quantity, rate, amount):
    assert line_amount({"status": "active", "quantity": quantity, "unit_sell_rate": rate}) == (
        amount,
        "unpriced" if amount is None else "priced",
    )


@pytest.mark.parametrize(
    "bad",
    [
        0,
        True,
        1.1,
        Decimal("1"),
        "",
        "-1",
        "1e2",
        "NaN",
        "Infinity",
        " 2",
        "+2",
        "1000000000",
        "0.0000001",
        "1.",
        ".5",
    ],
)
def test_decimal_inputs_never_coerce_or_round(bad):
    with pytest.raises(ValueError):
        decimal_string(bad)


def test_each_quantity_is_integral_and_zero_is_distinct():
    assert decimal_string("02.000000", unit="each") == "2"
    assert decimal_string("0") == "0"
    assert decimal_string(None) is None
    with pytest.raises(ValueError):
        decimal_string("1.2", unit="each")


def test_saved_lines_preserve_originals_history_and_exact_old_bytes(setup, tmp_path):  # noqa: F811
    with setup() as db:
        actor, draft, estimate = prepare(db)
        empty = service.revision_bytes(db, actor, draft.id, estimate.id)
        first = service.add_line(db, actor, draft.id, estimate.id, 1, add_payload())
        line = first["lines"][0]
        assert (line["original_quantity"], line["original_rate"], line["subtotal_ex_tax"]) == (
            "2",
            "1.005",
            "2.01",
        )
        assert line["opening_ids"] == [uid(2), uid(3)]
        assert first["summary"]["unassessed_opening_ids"] == [uid(2), uid(3)]
        overridden = service.override_line(
            db,
            actor,
            draft.id,
            estimate.id,
            2,
            line["line_id"],
            {"quantity": "3", "unit_sell_rate": "2.000001", "reason": "Manual site allowance"},
        )
        edited = overridden["lines"][0]
        assert (
            edited["original_quantity"],
            edited["original_rate"],
            edited["subtotal_ex_tax"],
        ) == ("2", "1.005", "6.00")
        assert edited["history"][-1]["created_by"] == actor.id
        assert edited["history"][-1]["before_quantity"] == "2"
        omitted = service.set_line_status(
            db, actor, draft.id, estimate.id, 3, line["line_id"], "omitted", "Separate contract"
        )
        assert omitted["summary"]["priced_subtotal_ex_tax"] == "0.00"
        assert omitted["summary"]["omitted_line_ids"] == [line["line_id"]]
        assert all(
            item["target_id"] != uid(5) for item in omitted["summary"]["unrepresented_targets"]
        )
        with pytest.raises(service.DraftEstimateError, match="ESTIMATE_TARGET_ALREADY_REPRESENTED"):
            service.add_line(db, actor, draft.id, estimate.id, 4, add_payload())
        restored = service.set_line_status(
            db, actor, draft.id, estimate.id, 4, line["line_id"], "active", "Included again"
        )
        assert restored["summary"]["priced_subtotal_ex_tax"] == "6.00"
        assert service.revision_bytes(db, actor, draft.id, estimate.id, 1) == empty
        assert service.read_estimate_revision(db, actor, draft.id, estimate.id, 2) == first
        changed_scope = sample_payload()
        changed_scope["services"][0]["quantity"] = "9"
        save_revision(db, actor, draft.id, 2, changed_scope)
        db.commit()
        assert service.estimate_staleness(
            db, actor, draft.id, estimate.id, storage_root=tmp_path
        ) == ["ESTIMATE_SCOPE_CHANGED"]
        expected = service.revision_bytes(db, actor, draft.id, estimate.id)
        draft_id, estimate_id = draft.id, estimate.id
        db.commit()
    with setup() as db:
        actor = db.get(User, uid(100))
        assert service.revision_bytes(db, actor, draft_id, estimate_id) == expected
        for model in (Estimate, Opening, Service, PhysicalModelLock):
            assert db.scalar(select(func.count()).select_from(model)) == 0
        audits = str(
            [
                row.new_value
                for row in db.scalars(
                    select(AuditEvent).where(AuditEvent.action.like("draft_estimate.%"))
                )
            ]
        )
        assert "Manual site allowance" not in audits
        assert "1.005" not in audits


def test_unknown_zero_blank_and_sum_rounded_lines(setup):  # noqa: F811
    with setup() as db:
        actor, draft, estimate = prepare(db)
        result = service.add_line(
            db,
            actor,
            draft.id,
            estimate.id,
            1,
            add_payload(quantity="1", unit_sell_rate="0.005", reason="Manual count"),
        )
        result = service.add_line(
            db,
            actor,
            draft.id,
            estimate.id,
            2,
            add_payload(target_id=uid(6), quantity=None, unit_sell_rate="0"),
        )
        assert result["lines"][1]["pricing_status"] == "unpriced"
        result = service.add_line(
            db,
            actor,
            draft.id,
            estimate.id,
            3,
            add_payload(
                target_kind="blank_opening",
                target_id=uid(4),
                unit="m2",
                quantity="1",
                unit_sell_rate="0.005",
                reason="Manually measured blank area",
            ),
        )
        assert result["summary"]["priced_subtotal_ex_tax"] == "0.02"
        assert result["summary"]["is_partial"] is True
        assert result["tax_treatment"] == "excluded_not_calculated"
        assert result["summary"]["unrepresented_targets"] == []
        assert result["lines"][2]["original_quantity"] is None
        assert result["lines"][2]["work_basis"] == "blank_opening_closure_only"
        assert result["lines"][2]["history"][0]["reason"] == "Manually measured blank area"


@pytest.mark.parametrize(
    "changes",
    [
        {"quantity": "3"},
        {"quantity": None},
        {"quantity": "2.2", "reason": "No each fraction"},
        {"unit": "m"},
        {"target_kind": "blank_opening", "target_id": uid(2)},
        {"target_kind": "blank_opening", "target_id": uid(4), "quantity": "1"},
        {"source_note": " "},
        {"description": " "},
        {"unexpected": "not allowed"},
    ],
)
def test_invalid_line_refuses_without_a_revision(setup, changes):  # noqa: F811
    with setup() as db:
        actor, draft, estimate = prepare(db)
        before = db.scalar(select(func.count()).select_from(AuditEvent))
        with pytest.raises(service.DraftEstimateError):
            service.add_line(db, actor, draft.id, estimate.id, 1, add_payload(**changes))
        assert service.read_estimate_revision(db, actor, draft.id, estimate.id)["revision"] == 1
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == before


def test_stale_cas_and_caller_rollback(setup):  # noqa: F811
    with setup() as db:
        actor, draft, estimate = prepare(db)
        first = service.add_line(db, actor, draft.id, estimate.id, 1, add_payload())
        db.commit()
        with pytest.raises(service.DraftEstimateError, match="ESTIMATE_REVISION_CONFLICT"):
            service.add_line(
                db, actor, draft.id, estimate.id, 1, add_payload(target_id=uid(6), quantity=None)
            )
        service.override_line(
            db,
            actor,
            draft.id,
            estimate.id,
            2,
            first["lines"][0]["line_id"],
            {"quantity": None, "unit_sell_rate": None, "reason": "Withheld pending evidence"},
        )
        db.rollback()
        assert service.read_estimate_revision(db, actor, draft.id, estimate.id) == first
        created = service.create_estimate(db, actor, draft.id, 2)
        created_id = created.id
        db.rollback()
        assert db.get(DraftEstimate, created_id) is None


def test_owner_admin_active_human_and_export_permissions(setup):  # noqa: F811
    with setup() as db:
        actor, draft, estimate = prepare(db)
        other = db.get(User, uid(101))
        with pytest.raises(service.DraftEstimateError) as denied:
            service.read_estimate_revision(db, other, draft.id, estimate.id)
        assert denied.value.status_code == 404
        admin = db.get(User, uid(102))
        assert service.read_estimate_revision(db, admin, draft.id, estimate.id)["state"] == "Draft"
        with pytest.raises(service.DraftEstimateError):
            service.read_estimate_revision(db, object(), draft.id, estimate.id)
        actor.role = "read_only"
        db.commit()
        assert service.list_estimates(db, actor, draft.id)
        with pytest.raises(service.DraftEstimateError) as denied:
            service.revision_bytes(db, actor, draft.id, estimate.id)
        assert denied.value.status_code == 403
        with pytest.raises(service.DraftEstimateError):
            service.add_line(db, actor, draft.id, estimate.id, 1, add_payload())
        actor.is_active = False
        db.commit()
        with pytest.raises(service.DraftEstimateError):
            service.read_estimate_revision(db, actor, draft.id, estimate.id)


@pytest.mark.parametrize("tamper", ["amount", "identity", "json_bytes", "parent", "scope"])
def test_retained_integrity_refuses_tampered_rows(setup, tamper):  # noqa: F811
    with setup() as db:
        actor, draft, estimate = prepare(db)
        envelope = service.add_line(db, actor, draft.id, estimate.id, 1, add_payload())
        db.commit()
        row = db.scalar(
            select(DraftEstimateRevision).where(
                DraftEstimateRevision.estimate_id == estimate.id,
                DraftEstimateRevision.revision == 2,
            )
        )
        if tamper == "amount":
            row.envelope_json = row.envelope_json.replace(
                '"subtotal_ex_tax":"2.01"', '"subtotal_ex_tax":"900.00"'
            )
        elif tamper == "identity":
            row.created_by_id = uid(102)
        elif tamper == "json_bytes":
            row.envelope_json += " "
        elif tamper == "parent":
            row.parent_hash = "0" * 64
        else:
            estimate.scope_hash = "0" * 64
        db.commit()
        with pytest.raises(service.DraftEstimateError) as invalid:
            service.revision_bytes(db, actor, draft.id, estimate.id)
        assert invalid.value.status_code == 409
        assert envelope["revision"] == 2


def test_contract_rejects_claimed_complete_or_recovered_shared_work(setup):  # noqa: F811
    with setup() as db:
        actor, draft, estimate = prepare(db)
        envelope = service.add_line(db, actor, draft.id, estimate.id, 1, add_payload())
        bad = copy.deepcopy(envelope)
        bad["summary"]["is_partial"] = False
        with pytest.raises(ValueError):
            validate_envelope(bad)
        bad = copy.deepcopy(envelope)
        bad["lines"][0]["work_basis"] = "whole_opening_closure"
        with pytest.raises(ValueError):
            validate_envelope(bad)


def test_source_fractional_each_quantity_kept_without_rounding(setup):  # noqa: F811
    with setup() as db:
        actor, draft, _estimate = prepare(db)
        content = sample_payload()
        content["services"][0]["quantity"] = "2.5"
        save_revision(db, actor, draft.id, 2, content)
        estimate = service.create_estimate(db, actor, draft.id, 3)
        with pytest.raises(service.DraftEstimateError):
            service.add_line(db, actor, draft.id, estimate.id, 1, add_payload(quantity="2.5"))
        saved = service.add_line(
            db,
            actor,
            draft.id,
            estimate.id,
            1,
            add_payload(quantity=None, reason="Unsupported count withheld"),
        )
        assert saved["lines"][0]["original_quantity"] == "2.5"
        assert saved["lines"][0]["quantity"] is None


def test_optional_exact_review_retains_bytes_and_reports_later_review(match_case):  # noqa: F811
    from classifire.services.draft_system_matches import create_match, save_review

    case = match_case
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        draft_id = case["draft_id"]
        match = create_match(
            db,
            actor,
            draft_id,
            2,
            case["release_id"],
            uid(2),
            uid(5),
            storage_root=case["storage_root"],
        )
        estimate = service.create_estimate(
            db, actor, draft_id, 2, match_id=match.id, match_revision=1
        )
        frozen = service.revision_bytes(db, actor, draft_id, estimate.id)
        review = service.read_estimate_revision(db, actor, draft_id, estimate.id)["system_match"]
        assert review["scope"]["revision"] == 2
        assert review["review_status"] == "unreviewed"
        decisions = [
            {"candidate_id": item["candidate_id"], "decision": "keep", "notes": "Still unapproved"}
            for item in review["candidates"]
        ]
        save_review(db, actor, draft_id, match.id, 1, decisions)
        db.commit()
        assert "ESTIMATE_REVIEW_CHANGED" in service.estimate_staleness(
            db, actor, draft_id, estimate.id, storage_root=case["storage_root"]
        )
        assert service.revision_bytes(db, actor, draft_id, estimate.id) == frozen
        case["source_path"].write_bytes(b"changed synthetic evidence")
        assert (
            len(
                service.estimate_staleness(
                    db, actor, draft_id, estimate.id, storage_root=case["storage_root"]
                )
            )
            > 1
        )
        assert service.revision_bytes(db, actor, draft_id, estimate.id) == frozen
        # Current source status changes do not turn a saved manual estimate into approval.
        saved = service.add_line(db, actor, draft_id, estimate.id, 1, add_payload())
        assert saved["summary"]["technical_status"] == "unapproved"


def test_attached_review_requires_permission_and_exact_scope(match_case):  # noqa: F811
    from classifire.services.draft_system_matches import create_match

    case = match_case
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        draft_id = case["draft_id"]
        match = create_match(
            db,
            actor,
            draft_id,
            2,
            case["release_id"],
            uid(2),
            uid(5),
            storage_root=case["storage_root"],
        )
        estimate = service.create_estimate(
            db, actor, draft_id, 2, match_id=match.id, match_revision=1
        )
        manual = service.create_estimate(db, actor, draft_id, 2)
        save_revision(db, actor, draft_id, 2, sample_payload())
        with pytest.raises(service.DraftEstimateError, match="ESTIMATE_MATCH_SCOPE_MISMATCH"):
            service.create_estimate(db, actor, draft_id, 3, match_id=match.id, match_revision=1)
        actor.role = "project_manager"
        db.commit()
        assert [row.id for row in service.list_estimates(db, actor, draft_id)] == [manual.id]
        with pytest.raises(service.DraftEstimateError) as denied:
            service.read_estimate_revision(db, actor, draft_id, estimate.id)
        assert denied.value.status_code == 403
        assert (
            service.read_estimate_revision(db, actor, draft_id, manual.id)["system_match"] is None
        )


def test_retained_review_corruption_fails_closed(match_case):  # noqa: F811
    from classifire.models import DraftSystemMatchRevision
    from classifire.services.draft_system_matches import create_match

    case = match_case
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        match = create_match(
            db,
            actor,
            case["draft_id"],
            2,
            case["release_id"],
            uid(2),
            uid(5),
            storage_root=case["storage_root"],
        )
        estimate = service.create_estimate(
            db, actor, case["draft_id"], 2, match_id=match.id, match_revision=1
        )
        row = db.scalar(
            select(DraftSystemMatchRevision).where(DraftSystemMatchRevision.match_id == match.id)
        )
        row.envelope_json += " "
        db.commit()
        with pytest.raises(service.DraftEstimateError) as invalid:
            service.read_estimate_revision(db, actor, case["draft_id"], estimate.id)
        assert invalid.value.status_code == 409


def test_imported_scope_v2_is_retained_without_reinterpreting_claims(setup):  # noqa: F811
    import hashlib

    from classifire.services.draft_scope import apply_import
    from classifire.services.draft_scope import revision_bytes as scope_bytes

    with setup() as db:
        actor, draft, _estimate = prepare(db)
        raw = scope_bytes(db, actor, draft.id)
        imported = apply_import(
            db, actor, draft.id, 2, raw, expected_source_hash=hashlib.sha256(raw).hexdigest()
        )
        estimate = service.create_estimate(db, actor, draft.id, 3)
        result = service.add_line(db, actor, draft.id, estimate.id, 1, add_payload())
        assert result["scope"] == imported
        assert result["scope"]["schema_version"] == "CLASSIFIRE-DRAFT-SCOPE-v2"
        assert result["summary"]["technical_status"] == "unapproved"


def test_final_compare_and_swap_refuses_intervening_committed_save(setup, monkeypatch):  # noqa: F811
    with setup() as db:
        actor, draft, estimate = prepare(db)
        validate = service._validate
        raced = False

        def concurrent_save(envelope, *args, **kwargs):
            nonlocal raced
            validate(envelope, *args, **kwargs)
            if not raced:
                raced = True
                with setup() as other_db:
                    other_actor = other_db.get(User, actor.id)
                    service.add_line(
                        other_db,
                        other_actor,
                        draft.id,
                        estimate.id,
                        1,
                        add_payload(target_id=uid(6), quantity=None),
                    )
                    other_db.commit()

        monkeypatch.setattr(service, "_validate", concurrent_save)
        with pytest.raises(service.DraftEstimateError, match="ESTIMATE_REVISION_CONFLICT"):
            service.add_line(db, actor, draft.id, estimate.id, 1, add_payload())
        db.rollback()
        result = service.read_estimate_revision(db, actor, draft.id, estimate.id)
        assert result["revision"] == 2
        assert [line["target_id"] for line in result["lines"]] == [uid(6)]


def test_final_permission_recheck_refuses_revocation_before_retention(setup, monkeypatch):  # noqa: F811
    with setup() as db:
        actor, draft, estimate = prepare(db)
        validate = service._validate

        def revoked(envelope, *args, **kwargs):
            validate(envelope, *args, **kwargs)
            db.execute(update(User).where(User.id == actor.id).values(role="read_only"))

        monkeypatch.setattr(service, "_validate", revoked)
        with pytest.raises(service.DraftEstimateError) as denied:
            service.add_line(db, actor, draft.id, estimate.id, 1, add_payload())
        assert denied.value.status_code == 403
        db.rollback()
        assert service.read_estimate_revision(db, actor, draft.id, estimate.id)["revision"] == 1


def test_bounds_refuse_without_truncating_existing_history(setup, monkeypatch):  # noqa: F811
    with setup() as db:
        actor, draft, estimate = prepare(db)
        saved = service.add_line(db, actor, draft.id, estimate.id, 1, add_payload())
        line_id = saved["lines"][0]["line_id"]
        monkeypatch.setattr(service, "MAX_HISTORY", 1)
        with pytest.raises(service.DraftEstimateError, match="ESTIMATE_HISTORY_LIMIT"):
            service.override_line(
                db,
                actor,
                draft.id,
                estimate.id,
                2,
                line_id,
                {"quantity": "3", "unit_sell_rate": "2", "reason": "Bound test"},
            )
        monkeypatch.setattr(service, "MAX_LINES", 1)
        with pytest.raises(service.DraftEstimateError, match="ESTIMATE_LINE_LIMIT"):
            service.add_line(
                db, actor, draft.id, estimate.id, 2, add_payload(target_id=uid(6), quantity=None)
            )
        assert service.read_estimate_revision(db, actor, draft.id, estimate.id) == saved


def test_freshness_rechecks_estimate_access_after_attached_source_checks(match_case, monkeypatch):  # noqa: F811
    from classifire.security import ROLE_PERMISSIONS
    from classifire.services.draft_system_matches import create_match

    case = match_case
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        match = create_match(
            db,
            actor,
            case["draft_id"],
            2,
            case["release_id"],
            uid(2),
            uid(5),
            storage_root=case["storage_root"],
        )
        estimate = service.create_estimate(
            db, actor, case["draft_id"], 2, match_id=match.id, match_revision=1
        )
        db.commit()
        monkeypatch.setitem(
            ROLE_PERMISSIONS, "fixture_scope_technical", {"project:read", "technical:read"}
        )

        def lose_estimate_access(*_args, **_kwargs):
            db.execute(
                update(User).where(User.id == actor.id).values(role="fixture_scope_technical")
            )
            db.flush()
            return []

        monkeypatch.setattr(service, "match_staleness", lose_estimate_access)
        with pytest.raises(service.DraftEstimateError) as denied:
            service.estimate_staleness(
                db, actor, case["draft_id"], estimate.id, storage_root=case["storage_root"]
            )
        assert denied.value.status_code == 403


def test_write_permission_does_not_replace_read_permission(setup, monkeypatch):  # noqa: F811
    from classifire.security import ROLE_PERMISSIONS

    with setup() as db:
        actor, draft, estimate = prepare(db)
        baseline = service.read_estimate_revision(db, actor, draft.id, estimate.id)
        monkeypatch.setitem(
            ROLE_PERMISSIONS,
            "fixture_estimate_write_only",
            {"project:read", "project:write", "estimate:write"},
        )
        actor.role = "fixture_estimate_write_only"
        db.commit()
        before_count = db.scalar(select(func.count()).select_from(AuditEvent))
        for action in (
            lambda: service.create_estimate(db, actor, draft.id, 2),
            lambda: service.add_line(db, actor, draft.id, estimate.id, 1, add_payload()),
        ):
            with pytest.raises(service.DraftEstimateError) as denied:
                action()
            assert denied.value.status_code == 403
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == before_count
        admin = db.get(User, uid(102))
        assert service.read_estimate_revision(db, admin, draft.id, estimate.id) == baseline
