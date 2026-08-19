from __future__ import annotations

import pytest

from classifire.services.workflow import (
    WorkflowAction,
    WorkflowFacts,
    WorkflowTransitionError,
    require_action,
)


def test_lock_requires_evidence_and_a_complete_physical_model() -> None:
    with pytest.raises(WorkflowTransitionError) as raised:
        require_action(WorkflowAction.LOCK_PHYSICAL_MODEL, WorkflowFacts())

    assert raised.value.action is WorkflowAction.LOCK_PHYSICAL_MODEL
    assert "evidence intake is not complete" in raised.value.blockers
    assert "physical model is not complete" in raised.value.blockers


def test_technical_search_requires_a_valid_physical_model_lock() -> None:
    facts = WorkflowFacts(
        evidence_intake_complete=True,
        physical_model_complete=True,
        physical_model_locked=False,
    )

    with pytest.raises(WorkflowTransitionError) as raised:
        require_action(WorkflowAction.SEARCH_TECHNICAL, facts)

    assert raised.value.action is WorkflowAction.SEARCH_TECHNICAL
    assert raised.value.blockers == ("Physical Model Lock is not valid",)


def test_complete_physical_facts_allow_lock_and_opening_specific_search() -> None:
    facts = WorkflowFacts(
        evidence_intake_complete=True,
        physical_model_complete=True,
        physical_model_locked=True,
    )

    require_action(WorkflowAction.LOCK_PHYSICAL_MODEL, facts)
    require_action(WorkflowAction.SEARCH_TECHNICAL, facts)
