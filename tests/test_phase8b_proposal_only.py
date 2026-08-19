from __future__ import annotations

import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from classifire import (  # noqa: F401
    canonical_models,
    commercial_models,
)
from classifire.canonical_models import (
    Defect,
    EvidenceSource,
    PhysicalModelLock,
    ServiceMaterialHypothesis,
    ServiceOpeningLink,
)
from classifire.db import Base
from classifire.models import (
    AgentServicePrincipal,
    Estimate,
    Opening,
    Project,
    Service,
    User,
)

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SCRIPTS_DIR),
    )


import run_classifire_real_uat_fireseals_visualvalidated_proposal_only as proposal_only_module  # noqa: E402
from run_classifire_real_uat_fireseals_topologyaware import (  # noqa: E402
    TopologyAwareFireSealController,
)
from run_classifire_real_uat_fireseals_visualvalidated import (  # noqa: E402
    RETIRED_PHYSICAL_VISUAL_MUTATION_TOOLS,
    VisualValidatedTopologyController,
)
from run_classifire_real_uat_fireseals_visualvalidated_proposal_only import (  # noqa: E402
    FINAL_RECEIPT,
    PROPOSAL_READY_STATUS,
    PROPOSAL_RECEIPT,
    PROTECTED_STATE_COLUMN_MANIFEST,
    PROTECTED_STATE_FINGERPRINT_VERSION,
    PROTECTED_STATE_RECEIPT,
    WITHHELD_WRITE_RECEIPT,
    ProposalOnlyComplete,
    ProposalOnlyVisualValidatedTopologyController,
    _assert_no_canonical_physical_state,
    _proposal_only_protected_state_guard,
    _protected_component_fingerprints,
    _protected_state_fingerprint,
    _protected_state_snapshot_from_session,
)


def _controller(
    tmp_path: Path,
) -> tuple[
    ProposalOnlyVisualValidatedTopologyController,
    dict[str, dict[str, Any]],
]:
    controller = object.__new__(ProposalOnlyVisualValidatedTopologyController)

    controller.receipt_dir = tmp_path
    controller.estimate_id = "estimate-test"
    controller.run_id = "run-test"

    saved: dict[str, dict[str, Any]] = {}

    def save_json(
        name: str,
        payload: dict[str, Any],
    ) -> None:
        saved[name] = payload

    controller.save_json = save_json  # type: ignore[method-assign]

    return controller, saved


def test_proposal_only_preflight_checks_gateway_without_service_restart(
    tmp_path: Path,
) -> None:
    controller, _saved = _controller(tmp_path)
    calls: list[tuple[tuple[str, ...], dict[str, Any]]] = []
    api_checks: list[bool] = []

    class Result:
        def __init__(
            self,
            *,
            returncode: int = 0,
            stdout: str = "",
            stderr: str = "",
        ) -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def openclaw(
        *args: str,
        **kwargs: Any,
    ) -> Result:
        calls.append((args, kwargs))
        if args[:2] == ("config", "validate"):
            return Result(stdout='{"valid": true}')
        return Result(stdout="RPC probe: ok")

    controller.openclaw = openclaw  # type: ignore[method-assign]
    controller.ensure_api = lambda: api_checks.append(True)  # type: ignore[method-assign]

    controller.preflight()

    assert [args for args, _kwargs in calls] == [
        ("config", "validate", "--json"),
        (
            "gateway",
            "status",
            "--require-rpc",
            "--timeout",
            "60000",
        ),
    ]
    assert all("restart" not in args for args, _kwargs in calls)
    assert calls[1][1] == {
        "timeout": 90,
        "check": False,
    }
    assert api_checks == [True]
    assert (tmp_path / "01-openclaw-config.json").is_file()
    assert (tmp_path / "02-openclaw-gateway.txt").is_file()


def test_proposal_only_preflight_fails_closed_without_service_restart(
    tmp_path: Path,
) -> None:
    controller, _saved = _controller(tmp_path)
    calls: list[tuple[str, ...]] = []

    class Result:
        def __init__(
            self,
            *,
            returncode: int = 0,
            stdout: str = "",
            stderr: str = "",
        ) -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def openclaw(
        *args: str,
        **_kwargs: Any,
    ) -> Result:
        calls.append(args)
        if args[:2] == ("config", "validate"):
            return Result(stdout='{"valid": true}')
        return Result(
            returncode=1,
            stderr="RPC unavailable",
        )

    controller.openclaw = openclaw  # type: ignore[method-assign]
    controller.ensure_api = lambda: pytest.fail(  # type: ignore[method-assign]
        "API startup must not follow a failed Gateway check"
    )

    with pytest.raises(
        RuntimeError,
        match="proposal-only mode will not restart",
    ):
        controller.preflight()

    assert calls == [
        ("config", "validate", "--json"),
        (
            "gateway",
            "status",
            "--require-rpc",
            "--timeout",
            "60000",
        ),
    ]
    assert all("restart" not in args for args in calls)
    assert not (tmp_path / "02-openclaw-gateway.txt").exists()


@pytest.fixture
def protected_state_db() -> tuple[
    Session,
    dict[str, Any],
]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        user = User(
            email="fingerprint@example.test",
            full_name="Fingerprint Test",
            password_hash="not-a-real-password-hash",  # noqa: S106
            role="estimator",
        )
        agent_principal = AgentServicePrincipal(
            agent_id="cf-fingerprint-test",
            display_name="Fingerprint Test Agent",
            token_hash="a" * 64,
            token_hint="test",  # noqa: S106
            scopes=["evidence:read"],
        )
        project = Project(
            reference="FINGERPRINT-PROJECT",
            name="Fingerprint Project",
        )
        db.add_all(
            [
                user,
                agent_principal,
                project,
            ]
        )
        db.flush()

        estimate = Estimate(
            project_id=project.id,
            revision=1,
            reference="FINGERPRINT-ESTIMATE-R1",
            title="Fingerprint Estimate",
            status="draft",
        )
        db.add(estimate)
        db.flush()

        defect = Defect(
            estimate_id=estimate.id,
            external_defect_id="D-001",
            defect_code="D-001",
            description="Protected defect",
            location="Level 1",
            evidence_status="confirmed",
            status="active",
        )
        db.add(defect)
        db.flush()

        evidence = EvidenceSource(
            estimate_id=estimate.id,
            defect_id=defect.id,
            evidence_type="test_fixture",
            source_reference="fixture://fingerprint",
            sha256="b" * 64,
            evidence_class="observed",
            status="active",
        )
        opening = Opening(
            estimate_id=estimate.id,
            canonical_defect_id=defect.id,
            opening_code="O-001",
            substrate_type="concrete",
            substrate_plane="wall",
            opening_type="service_penetration",
            physical_model_status="draft",
        )
        db.add_all(
            [
                evidence,
                opening,
            ]
        )
        db.flush()

        service = Service(
            opening_id=opening.id,
            service_code="S-001",
            service_type="pipe",
            material="copper",
            quantity=1,
            evidence_status="confirmed",
        )
        db.add(service)
        db.flush()

        link = ServiceOpeningLink(
            service_id=service.id,
            opening_id=opening.id,
            link_type="penetrates",
            relationship_status="confirmed",
            evidence_status="confirmed",
        )
        material_hypothesis = ServiceMaterialHypothesis(
            service_id=service.id,
            material="copper",
            evidence_status="observed",
            final_status="provisional",
        )
        historical_lock = PhysicalModelLock(
            project_id=project.id,
            estimate_id=estimate.id,
            defect_ids=[defect.id],
            evidence_hashes=["b" * 64],
            service_ids=[service.id],
            opening_ids=[opening.id],
            validator_result="APPROVED",
            content_hash="c" * 64,
            invalidated_at=datetime(
                2026,
                8,
                16,
                tzinfo=UTC,
            ),
            invalidation_reason="Historical test lock",
        )
        db.add_all(
            [
                link,
                material_hypothesis,
                historical_lock,
            ]
        )
        db.commit()

        yield (
            db,
            {
                "user": user,
                "agent_principal": agent_principal,
                "project": project,
                "estimate": estimate,
                "defect": defect,
                "evidence": evidence,
                "opening": opening,
                "service": service,
                "link": link,
                "material_hypothesis": (material_hypothesis),
                "historical_lock": historical_lock,
            },
        )

    engine.dispose()


def _synthetic_protected_snapshot() -> dict[str, Any]:
    return {
        "fingerprint_version": (PROTECTED_STATE_FINGERPRINT_VERSION),
        "estimate_id": "estimate-test",
        "estimate": {
            "id": "estimate-test",
            "status": "draft",
        },
        "workflow": {
            "stage": "physical_model",
            "facts": {
                "evidence_intake_complete": True,
                "physical_model_complete": False,
            },
        },
        "defects": [],
        "evidence_sources": [],
        "openings": [],
        "services": [],
        "service_opening_links": [],
        "service_material_hypotheses": [],
        "physical_model_locks": [],
    }


@pytest.mark.parametrize(
    "tool_name",
    sorted(RETIRED_PHYSICAL_VISUAL_MUTATION_TOOLS),
)
def test_proposal_only_withholds_all_physical_writes(
    tmp_path: Path,
    tool_name: str,
) -> None:
    controller, saved = _controller(tmp_path)

    (tmp_path / PROPOSAL_RECEIPT).write_text(
        "{}",
        encoding="utf-8",
    )

    with pytest.raises(ProposalOnlyComplete) as caught:
        controller.invoke_tool(
            "cf-physical-model",
            "agent:cf-physical-model:test",
            tool_name,
            {
                "estimate_id": "estimate-test",
            },
            "test-receipt.json",
        )

    assert caught.value.tool_name == tool_name

    receipt = saved[WITHHELD_WRITE_RECEIPT]

    assert receipt["status"] == PROPOSAL_READY_STATUS

    assert receipt["withheld_tool"] == tool_name

    assert receipt["canonical_write_performed"] is False


def test_proposal_only_fails_closed_without_merged_proposal(
    tmp_path: Path,
) -> None:
    controller, _saved = _controller(tmp_path)

    with pytest.raises(
        RuntimeError,
        match="merged proposal receipt",
    ):
        controller.invoke_tool(
            "cf-physical-model",
            "agent:cf-physical-model:test",
            "classifire_submit_initial_physical_model",
            {
                "estimate_id": "estimate-test",
            },
            "test-receipt.json",
        )


def test_proposal_only_preserves_its_withheld_receipt_for_retired_legacy_runner_path(
    tmp_path: Path,
) -> None:
    controller, saved = _controller(tmp_path)
    (tmp_path / PROPOSAL_RECEIPT).write_text("{}", encoding="utf-8")

    with pytest.raises(ProposalOnlyComplete) as caught:
        controller.withhold_legacy_physical_mutation(
            source_stage="visual-validated-proposal",
            proposal_receipt=PROPOSAL_RECEIPT,
            proposed_opening_count=1,
            proposed_service_count=1,
            receipt_name="ignored-by-proposal-only.json",
        )

    assert caught.value.tool_name == "classifire_submit_initial_physical_model"
    receipt = saved[WITHHELD_WRITE_RECEIPT]
    assert receipt["status"] == PROPOSAL_READY_STATUS
    assert receipt["canonical_write_performed"] is False
    assert receipt["physical_model_lock_created"] is False


@pytest.mark.parametrize(
    (
        "opening_count",
        "service_count",
        "physical_lock_count",
    ),
    [
        (1, 0, 0),
        (0, 1, 0),
        (0, 0, 1),
    ],
)
def test_proposal_only_rejects_canonical_physical_mutation(
    tmp_path: Path,
    opening_count: int,
    service_count: int,
    physical_lock_count: int,
) -> None:
    controller, _saved = _controller(tmp_path)

    state = {
        "opening_count": opening_count,
        "service_count": service_count,
        "physical_lock_count": physical_lock_count,
    }

    with pytest.raises(
        RuntimeError,
        match="canonical Physical state exists",
    ):
        _assert_no_canonical_physical_state(
            controller,
            state,
        )


def test_protected_state_snapshot_is_deterministic(
    protected_state_db: tuple[
        Session,
        dict[str, Any],
    ],
) -> None:
    db, rows = protected_state_db
    estimate = rows["estimate"]

    first = _protected_state_snapshot_from_session(
        db,
        estimate.id,
    )
    second = _protected_state_snapshot_from_session(
        db,
        estimate.id,
    )

    assert first == second
    assert _protected_state_fingerprint(first) == _protected_state_fingerprint(second)
    assert len(first["defects"]) == 1
    assert len(first["evidence_sources"]) == 1
    assert len(first["openings"]) == 1
    assert len(first["services"]) == 1
    assert len(first["service_opening_links"]) == 1
    assert len(first["service_material_hypotheses"]) == 1
    assert len(first["physical_model_locks"]) == 1
    assert first["physical_model_locks"][0]["invalidated_at"] is not None


@pytest.mark.parametrize(
    ("component", "model"),
    [
        ("estimate", Estimate),
        ("defects", Defect),
        ("evidence_sources", EvidenceSource),
        ("openings", Opening),
        ("services", Service),
        ("service_opening_links", ServiceOpeningLink),
        ("service_material_hypotheses", ServiceMaterialHypothesis),
        ("physical_model_locks", PhysicalModelLock),
    ],
)
def test_protected_state_v1_column_manifest_matches_current_models(
    component: str,
    model: type[Any],
) -> None:
    assert (
        tuple(column.key for column in model.__table__.columns)
        == (PROTECTED_STATE_COLUMN_MANIFEST[component])
    )


def test_protected_state_snapshot_includes_cross_linked_service_scope(
    protected_state_db: tuple[
        Session,
        dict[str, Any],
    ],
) -> None:
    db, rows = protected_state_db
    estimate = rows["estimate"]
    other_estimate = Estimate(
        project_id=rows["project"].id,
        revision=2,
        reference="FINGERPRINT-CROSS-LINK-R2",
        title="Cross-link source estimate",
        status="draft",
    )
    db.add(other_estimate)
    db.flush()

    other_opening = Opening(
        estimate_id=other_estimate.id,
        opening_code="CROSS-O-001",
        substrate_type="concrete",
        substrate_plane="wall",
        orientation="wall",
        opening_type="service_penetration",
        frl="-/120/120",
        physical_model_status="draft",
    )
    db.add(other_opening)
    db.flush()

    cross_linked_service = Service(
        opening_id=other_opening.id,
        service_code="CROSS-S-001",
        service_type="pipe",
        material="steel",
        quantity=1,
        evidence_status="confirmed",
    )
    db.add(cross_linked_service)
    db.flush()

    target_link = ServiceOpeningLink(
        service_id=cross_linked_service.id,
        opening_id=rows["opening"].id,
        link_type="penetrates",
        relationship_status="confirmed",
        evidence_status="confirmed",
    )
    primary_link = ServiceOpeningLink(
        service_id=cross_linked_service.id,
        opening_id=other_opening.id,
        link_type="primary",
        relationship_status="confirmed",
        evidence_status="confirmed",
    )
    hypothesis = ServiceMaterialHypothesis(
        service_id=cross_linked_service.id,
        material="steel",
        evidence_status="observed",
        final_status="provisional",
    )
    db.add_all([target_link, primary_link, hypothesis])
    db.commit()

    snapshot = _protected_state_snapshot_from_session(db, estimate.id)

    assert cross_linked_service.id in {row["id"] for row in snapshot["services"]}
    assert {target_link.id, primary_link.id}.issubset(
        {row["id"] for row in snapshot["service_opening_links"]}
    )
    assert hypothesis.id in {row["id"] for row in snapshot["service_material_hypotheses"]}


@pytest.mark.parametrize(
    (
        "row_name",
        "field_name",
        "replacement",
        "component",
    ),
    [
        (
            "estimate",
            "title",
            "Changed estimate title",
            "estimate",
        ),
        (
            "defect",
            "description",
            "Changed defect",
            "defects",
        ),
        (
            "evidence",
            "status",
            "superseded",
            "evidence_sources",
        ),
        (
            "opening",
            "notes",
            "Changed opening",
            "openings",
        ),
        (
            "service",
            "notes",
            "Changed service",
            "services",
        ),
        (
            "link",
            "notes",
            "Changed link",
            "service_opening_links",
        ),
        (
            "material_hypothesis",
            "final_status",
            "rejected",
            "service_material_hypotheses",
        ),
        (
            "historical_lock",
            "invalidation_reason",
            "Changed historical lock",
            "physical_model_locks",
        ),
    ],
)
def test_protected_state_fingerprint_detects_count_preserving_mutation(
    protected_state_db: tuple[
        Session,
        dict[str, Any],
    ],
    row_name: str,
    field_name: str,
    replacement: str,
    component: str,
) -> None:
    db, rows = protected_state_db
    estimate = rows["estimate"]
    before = _protected_state_snapshot_from_session(
        db,
        estimate.id,
    )

    setattr(
        rows[row_name],
        field_name,
        replacement,
    )
    db.commit()

    after = _protected_state_snapshot_from_session(
        db,
        estimate.id,
    )
    before_components = _protected_component_fingerprints(before)
    after_components = _protected_component_fingerprints(after)

    assert _protected_state_fingerprint(before) != _protected_state_fingerprint(after)
    assert before_components[component] != after_components[component]


def test_protected_state_fingerprint_detects_workflow_change(
    protected_state_db: tuple[
        Session,
        dict[str, Any],
    ],
) -> None:
    db, rows = protected_state_db
    estimate = rows["estimate"]
    before = _protected_state_snapshot_from_session(db, estimate.id)

    rows["opening"].orientation = "wall"
    rows["opening"].frl = "-/120/120"
    db.commit()

    after = _protected_state_snapshot_from_session(db, estimate.id)
    before_components = _protected_component_fingerprints(before)
    after_components = _protected_component_fingerprints(after)

    assert before["workflow"] != after["workflow"]
    assert before_components["workflow"] != after_components["workflow"]


def test_protected_state_fingerprint_detects_added_or_deleted_rows(
    protected_state_db: tuple[
        Session,
        dict[str, Any],
    ],
) -> None:
    db, rows = protected_state_db
    estimate = rows["estimate"]
    before = _protected_state_snapshot_from_session(
        db,
        estimate.id,
    )

    db.delete(rows["link"])
    db.commit()

    after_delete = _protected_state_snapshot_from_session(
        db,
        estimate.id,
    )
    assert _protected_state_fingerprint(before) != _protected_state_fingerprint(after_delete)

    added = EvidenceSource(
        estimate_id=estimate.id,
        defect_id=rows["defect"].id,
        evidence_type="test_fixture",
        source_reference="fixture://added",
        sha256="d" * 64,
        status="active",
    )
    db.add(added)
    db.commit()

    after_add = _protected_state_snapshot_from_session(
        db,
        estimate.id,
    )
    assert _protected_state_fingerprint(after_delete) != _protected_state_fingerprint(after_add)


def test_protected_state_fingerprint_ignores_unrelated_runtime_rows(
    protected_state_db: tuple[
        Session,
        dict[str, Any],
    ],
) -> None:
    db, rows = protected_state_db
    estimate = rows["estimate"]
    before = _protected_state_snapshot_from_session(
        db,
        estimate.id,
    )

    rows["user"].last_login_at = datetime(
        2026,
        8,
        17,
        tzinfo=UTC,
    )
    rows["agent_principal"].last_used_at = datetime(
        2026,
        8,
        17,
        tzinfo=UTC,
    )
    db.commit()

    after = _protected_state_snapshot_from_session(
        db,
        estimate.id,
    )
    assert _protected_state_fingerprint(before) == _protected_state_fingerprint(after)


def test_protected_state_fingerprint_ignores_other_estimate(
    protected_state_db: tuple[
        Session,
        dict[str, Any],
    ],
) -> None:
    db, rows = protected_state_db
    estimate = rows["estimate"]
    before = _protected_state_snapshot_from_session(
        db,
        estimate.id,
    )

    other_estimate = Estimate(
        project_id=rows["project"].id,
        revision=2,
        reference="FINGERPRINT-ESTIMATE-R2",
        title="Other estimate",
        status="draft",
    )
    db.add(other_estimate)
    db.flush()
    db.add(
        Defect(
            estimate_id=other_estimate.id,
            external_defect_id="OTHER-D-001",
            defect_code="OTHER-D-001",
            description="Other estimate defect",
            evidence_status="confirmed",
            status="active",
        )
    )
    db.commit()

    after = _protected_state_snapshot_from_session(
        db,
        estimate.id,
    )
    assert _protected_state_fingerprint(before) == _protected_state_fingerprint(after)


def test_protected_state_snapshot_fails_closed_for_missing_estimate(
    protected_state_db: tuple[
        Session,
        dict[str, Any],
    ],
) -> None:
    db, _rows = protected_state_db

    with pytest.raises(
        RuntimeError,
        match="prepared estimate disappeared",
    ):
        _protected_state_snapshot_from_session(
            db,
            "missing-estimate",
        )


def test_protected_state_guard_records_matching_fingerprints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, saved = _controller(tmp_path)
    snapshot = _synthetic_protected_snapshot()
    snapshots = [
        deepcopy(snapshot),
        deepcopy(snapshot),
    ]
    monkeypatch.setattr(
        proposal_only_module,
        "_protected_state_snapshot",
        lambda _estimate_id: snapshots.pop(0),
    )

    with _proposal_only_protected_state_guard(controller) as result:
        pass

    assert result["protected_state_unchanged"] is True
    assert result["before_fingerprint"] == result["after_fingerprint"]
    receipt = saved[PROTECTED_STATE_RECEIPT]
    assert receipt["status"] == "PASS"
    assert receipt["changed_components"] == []


def test_protected_state_guard_fails_closed_on_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, saved = _controller(tmp_path)
    before = _synthetic_protected_snapshot()
    after = deepcopy(before)
    after["defects"].append(
        {
            "id": "unexpected-defect",
        }
    )
    snapshots = [
        before,
        after,
    ]
    monkeypatch.setattr(
        proposal_only_module,
        "_protected_state_snapshot",
        lambda _estimate_id: snapshots.pop(0),
    )

    with pytest.raises(
        RuntimeError,
        match="protected canonical state changed",
    ):
        with _proposal_only_protected_state_guard(controller):
            pass

    receipt = saved[PROTECTED_STATE_RECEIPT]
    assert receipt["status"] == "FAIL"
    assert receipt["protected_state_unchanged"] is False
    assert receipt["changed_components"] == ["defects"]


def test_protected_state_guard_records_state_when_guarded_work_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, saved = _controller(tmp_path)
    snapshot = _synthetic_protected_snapshot()
    snapshots = [
        deepcopy(snapshot),
        deepcopy(snapshot),
    ]
    monkeypatch.setattr(
        proposal_only_module,
        "_protected_state_snapshot",
        lambda _estimate_id: snapshots.pop(0),
    )

    with pytest.raises(
        ValueError,
        match="simulated inference failure",
    ):
        with _proposal_only_protected_state_guard(controller):
            raise ValueError("simulated inference failure")

    receipt = saved[PROTECTED_STATE_RECEIPT]
    assert receipt["status"] == "PASS"
    assert receipt["protected_state_unchanged"] is True
    assert receipt["before_fingerprint"] == receipt["after_fingerprint"]
    assert receipt["guarded_operation_error"] == {
        "type": "ValueError",
        "message": "simulated inference failure",
    }


def test_protected_state_guard_reports_mutation_and_guarded_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, saved = _controller(tmp_path)
    before = _synthetic_protected_snapshot()
    after = deepcopy(before)
    after["defects"].append({"id": "unexpected-defect"})
    snapshots = [before, after]
    monkeypatch.setattr(
        proposal_only_module,
        "_protected_state_snapshot",
        lambda _estimate_id: snapshots.pop(0),
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "protected canonical state changed.*"
            "guarded operation also failed with ValueError: simulated inference failure"
        ),
    ) as caught:
        with _proposal_only_protected_state_guard(controller):
            raise ValueError("simulated inference failure")

    assert isinstance(caught.value.__cause__, ValueError)
    receipt = saved[PROTECTED_STATE_RECEIPT]
    assert receipt["status"] == "FAIL"
    assert receipt["changed_components"] == ["defects"]
    assert receipt["guarded_operation_error"] == {
        "type": "ValueError",
        "message": "simulated inference failure",
    }


def test_main_records_both_protected_fingerprints_in_final_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: dict[str, dict[str, Any]] = {}
    snapshot = _synthetic_protected_snapshot()
    snapshots = [deepcopy(snapshot), deepcopy(snapshot)]

    class FakeController:
        def __init__(
            self,
            _receipt: dict[str, Any],
            **_kwargs: Any,
        ) -> None:
            self.run_id = "run-test"
            self.estimate_id = "estimate-test"
            self.receipt_dir = tmp_path

        def run(self) -> dict[str, Any]:
            return {
                "status": proposal_only_module.PARTIAL_STATUS,
                "opening_count": 0,
                "service_count": 0,
                "physical_lock_count": 0,
            }

        def save_json(
            self,
            name: str,
            payload: dict[str, Any],
        ) -> None:
            saved[name] = payload

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        proposal_only_module,
        "ProposalOnlyVisualValidatedTopologyController",
        FakeController,
    )
    monkeypatch.setattr(
        proposal_only_module,
        "repo_root",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        proposal_only_module,
        "load_receipt",
        lambda _root, _run_id: (tmp_path / "receipt.json", {}),
    )
    monkeypatch.setattr(
        proposal_only_module,
        "_protected_state_snapshot",
        lambda _estimate_id: snapshots.pop(0),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "proposal-only",
            "--run-id",
            "run-test",
        ],
    )

    assert proposal_only_module.main() == 0

    protected_state = saved[FINAL_RECEIPT]["protected_state"]
    assert protected_state["fingerprint_version"] == PROTECTED_STATE_FINGERPRINT_VERSION
    assert protected_state["protected_state_unchanged"] is True
    assert protected_state["before_fingerprint"] == protected_state["after_fingerprint"]


def test_proposal_only_delegates_non_write_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, saved = _controller(tmp_path)

    calls: list[
        tuple[
            tuple[Any, ...],
            dict[str, Any],
        ]
    ] = []

    def fake_invoke_tool(
        self: VisualValidatedTopologyController,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        calls.append(
            (
                args,
                kwargs,
            )
        )

        return {
            "ok": True,
        }

    monkeypatch.setattr(
        VisualValidatedTopologyController,
        "invoke_tool",
        fake_invoke_tool,
    )

    result = controller.invoke_tool(
        "cf-physical-model",
        "agent:cf-physical-model:test",
        "classifire_evidence_read",
        {
            "estimate_id": "estimate-test",
        },
        "test-receipt.json",
    )

    assert result == {
        "ok": True,
    }

    assert len(calls) == 1
    assert saved == {}


@pytest.mark.parametrize(
    (
        "runner_timeout",
        "explicit_timeout",
        "expected_timeout",
    ),
    [
        (1800, None, 1800.0),
        (1800, 900.0, 900.0),
    ],
)
def test_visual_openresponses_timeout_is_configurable(
    monkeypatch: pytest.MonkeyPatch,
    runner_timeout: int,
    explicit_timeout: float | None,
    expected_timeout: float,
) -> None:
    def fake_parent_init(
        self: TopologyAwareFireSealController,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        return None

    monkeypatch.setattr(
        TopologyAwareFireSealController,
        "__init__",
        fake_parent_init,
    )

    kwargs: dict[str, Any] = {
        "timeout_seconds": runner_timeout,
    }

    if explicit_timeout is not None:
        kwargs["openresponses_timeout_seconds"] = explicit_timeout

    controller = VisualValidatedTopologyController(
        **kwargs,
    )

    assert controller._openresponses_timeout_seconds == expected_timeout


def test_visual_openresponses_timeout_rejects_nonpositive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_parent_init(
        self: TopologyAwareFireSealController,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        return None

    monkeypatch.setattr(
        TopologyAwareFireSealController,
        "__init__",
        fake_parent_init,
    )

    with pytest.raises(
        ValueError,
        match="greater than zero",
    ):
        VisualValidatedTopologyController(
            timeout_seconds=0,
        )
