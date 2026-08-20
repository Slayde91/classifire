from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkflowStage(StrEnum):
    """The Layer 2 physical-model workflow boundary.

    Later technical, commercial, validation, and release stages intentionally do
    not appear here. This module establishes only the prerequisite that an
    opening-specific technical search needs an immutable physical model.
    """

    EVIDENCE_INTAKE = "evidence_intake"
    PHYSICAL_MODEL = "physical_model"
    PHYSICAL_MODEL_LOCK = "physical_model_lock"
    OPENING_SPECIFIC_TECHNICAL_SEARCH = "opening_specific_technical_search"
    COMPLETE = "complete"


class WorkflowAction(StrEnum):
    INGEST_EVIDENCE = "ingest_evidence"
    EDIT_PHYSICAL_MODEL = "edit_physical_model"
    LOCK_PHYSICAL_MODEL = "lock_physical_model"
    SEARCH_TECHNICAL = "search_technical"


class WorkflowTransitionError(RuntimeError):
    def __init__(self, action: WorkflowAction, blockers: tuple[str, ...]):
        self.action = action
        self.blockers = blockers
        message = f"Action '{action.value}' blocked: " + "; ".join(blockers)
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class WorkflowFacts:
    evidence_intake_complete: bool = False
    physical_model_complete: bool = False
    physical_model_locked: bool = False
    technical_search_complete: bool = False


_STAGE_SEQUENCE: tuple[tuple[WorkflowStage, str], ...] = (
    (WorkflowStage.EVIDENCE_INTAKE, "evidence_intake_complete"),
    (WorkflowStage.PHYSICAL_MODEL, "physical_model_complete"),
    (WorkflowStage.PHYSICAL_MODEL_LOCK, "physical_model_locked"),
    (WorkflowStage.OPENING_SPECIFIC_TECHNICAL_SEARCH, "technical_search_complete"),
)

_ACTION_REQUIREMENTS: dict[WorkflowAction, tuple[str, ...]] = {
    WorkflowAction.INGEST_EVIDENCE: (),
    WorkflowAction.EDIT_PHYSICAL_MODEL: ("evidence_intake_complete",),
    WorkflowAction.LOCK_PHYSICAL_MODEL: (
        "evidence_intake_complete",
        "physical_model_complete",
    ),
    WorkflowAction.SEARCH_TECHNICAL: ("physical_model_locked",),
}

_FIELD_LABELS = {
    "evidence_intake_complete": "evidence intake is not complete",
    "physical_model_complete": "physical model is not complete",
    "physical_model_locked": "Physical Model Lock is not valid",
    "technical_search_complete": "opening-specific technical search is not complete",
}


def current_stage(facts: WorkflowFacts) -> WorkflowStage:
    """Return the earliest incomplete Layer 2 stage."""
    for stage, field_name in _STAGE_SEQUENCE:
        if not getattr(facts, field_name):
            return stage
    return WorkflowStage.COMPLETE


def blockers_for(action: WorkflowAction, facts: WorkflowFacts) -> tuple[str, ...]:
    requirements = _ACTION_REQUIREMENTS[action]
    return tuple(_FIELD_LABELS[field] for field in requirements if not getattr(facts, field))


def is_action_allowed(action: WorkflowAction, facts: WorkflowFacts) -> bool:
    return not blockers_for(action, facts)


def require_action(action: WorkflowAction, facts: WorkflowFacts) -> None:
    blockers = blockers_for(action, facts)
    if blockers:
        raise WorkflowTransitionError(action, blockers)


def stage_order() -> tuple[WorkflowStage, ...]:
    return tuple(stage for stage, _ in _STAGE_SEQUENCE)


__all__ = [
    "WorkflowAction",
    "WorkflowFacts",
    "WorkflowStage",
    "WorkflowTransitionError",
    "blockers_for",
    "current_stage",
    "is_action_allowed",
    "require_action",
    "stage_order",
]
