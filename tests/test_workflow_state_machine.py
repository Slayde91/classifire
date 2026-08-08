from dataclasses import replace

import pytest

from quantifire.services.workflow import (
    WorkflowAction,
    WorkflowFacts,
    WorkflowStage,
    WorkflowTransitionError,
    current_stage,
    is_action_allowed,
    require_action,
    stage_order,
)


def test_stage_order_matches_v213_package13_hard_order() -> None:
    assert stage_order() == (
        WorkflowStage.EVIDENCE_INTAKE,
        WorkflowStage.PHYSICAL_MODEL,
        WorkflowStage.PHYSICAL_MODEL_LOCK,
        WorkflowStage.OPENING_SPECIFIC_TECHNICAL_SEARCH,
        WorkflowStage.REPAIR_STRATEGY_LOCK,
        WorkflowStage.COMPONENT_DERIVATION,
        WorkflowStage.QUANTITY_AND_LABOUR,
        WorkflowStage.COMMERCIAL_PRICING_AND_RECOVERY,
        WorkflowStage.INDEPENDENT_VALIDATION,
        WorkflowStage.VALIDATED_SNAPSHOT,
        WorkflowStage.OUTPUT_RENDERING,
        WorkflowStage.HUMAN_RELEASE,
    )


def test_first_incomplete_stage_is_returned() -> None:
    facts = WorkflowFacts()
    assert current_stage(facts) is WorkflowStage.EVIDENCE_INTAKE

    facts = replace(facts, evidence_intake_complete=True)
    assert current_stage(facts) is WorkflowStage.PHYSICAL_MODEL

    facts = replace(facts, physical_model_complete=True, physical_model_locked=True)
    assert current_stage(facts) is WorkflowStage.OPENING_SPECIFIC_TECHNICAL_SEARCH


def test_technical_search_requires_physical_model_lock() -> None:
    facts = WorkflowFacts(
        evidence_intake_complete=True,
        physical_model_complete=True,
        physical_model_locked=False,
    )
    assert not is_action_allowed(WorkflowAction.SEARCH_TECHNICAL, facts)
    with pytest.raises(WorkflowTransitionError, match="Physical Model Lock"):
        require_action(WorkflowAction.SEARCH_TECHNICAL, facts)


def test_component_derivation_requires_repair_strategy_lock() -> None:
    facts = WorkflowFacts(
        evidence_intake_complete=True,
        physical_model_complete=True,
        physical_model_locked=True,
        technical_search_complete=True,
        repair_strategy_locked=False,
    )
    with pytest.raises(WorkflowTransitionError, match="Repair Strategy Lock"):
        require_action(WorkflowAction.DERIVE_COMPONENTS, facts)


def test_commercial_pricing_requires_components_quantity_and_labour() -> None:
    facts = WorkflowFacts(
        evidence_intake_complete=True,
        physical_model_complete=True,
        physical_model_locked=True,
        technical_search_complete=True,
        repair_strategy_locked=True,
        components_derived=True,
        quantity_and_labour_complete=False,
    )
    with pytest.raises(WorkflowTransitionError, match="quantity and labour"):
        require_action(WorkflowAction.PRICE_AND_RECOVER, facts)


def test_validation_requires_full_upstream_commercial_chain() -> None:
    facts = WorkflowFacts(
        evidence_intake_complete=True,
        physical_model_complete=True,
        physical_model_locked=True,
        technical_search_complete=True,
        repair_strategy_locked=True,
        components_derived=True,
        quantity_and_labour_complete=True,
        commercial_pricing_and_recovery_complete=False,
    )
    with pytest.raises(WorkflowTransitionError, match="commercial pricing and recovery"):
        require_action(WorkflowAction.RUN_INDEPENDENT_VALIDATION, facts)


def test_snapshot_requires_independent_validation() -> None:
    facts = WorkflowFacts()
    with pytest.raises(WorkflowTransitionError, match="independent validation"):
        require_action(WorkflowAction.CREATE_VALIDATED_SNAPSHOT, facts)


def test_output_requires_validated_snapshot() -> None:
    facts = WorkflowFacts(independent_validation_passed=True)
    with pytest.raises(WorkflowTransitionError, match="validated snapshot"):
        require_action(WorkflowAction.RENDER_OUTPUT, facts)


def test_human_release_requires_validation_snapshot_and_output() -> None:
    facts = WorkflowFacts(
        independent_validation_passed=True,
        validated_snapshot_created=True,
        output_rendered=False,
    )
    with pytest.raises(WorkflowTransitionError, match="controlled output"):
        require_action(WorkflowAction.HUMAN_RELEASE, facts)


def test_complete_workflow_allows_release_and_reports_complete() -> None:
    facts = WorkflowFacts(
        evidence_intake_complete=True,
        physical_model_complete=True,
        physical_model_locked=True,
        technical_search_complete=True,
        repair_strategy_locked=True,
        components_derived=True,
        quantity_and_labour_complete=True,
        commercial_pricing_and_recovery_complete=True,
        independent_validation_passed=True,
        validated_snapshot_created=True,
        output_rendered=True,
        human_release_approved=True,
    )
    assert current_stage(facts) is WorkflowStage.COMPLETE
    assert is_action_allowed(WorkflowAction.HUMAN_RELEASE, facts)
