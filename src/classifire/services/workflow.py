from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkflowStage(StrEnum):
    EVIDENCE_INTAKE = "evidence_intake"
    PHYSICAL_MODEL = "physical_model"
    PHYSICAL_MODEL_LOCK = "physical_model_lock"
    OPENING_SPECIFIC_TECHNICAL_SEARCH = "opening_specific_technical_search"
    REPAIR_STRATEGY_LOCK = "repair_strategy_lock"
    COMPONENT_DERIVATION = "component_derivation"
    QUANTITY_AND_LABOUR = "quantity_and_labour"
    COMMERCIAL_PRICING_AND_RECOVERY = "commercial_pricing_and_recovery"
    INDEPENDENT_VALIDATION = "independent_validation"
    VALIDATED_SNAPSHOT = "validated_snapshot"
    OUTPUT_RENDERING = "output_rendering"
    HUMAN_RELEASE = "human_release"
    COMPLETE = "complete"


class WorkflowAction(StrEnum):
    INGEST_EVIDENCE = "ingest_evidence"
    EDIT_PHYSICAL_MODEL = "edit_physical_model"
    LOCK_PHYSICAL_MODEL = "lock_physical_model"
    SEARCH_TECHNICAL = "search_technical"
    LOCK_REPAIR_STRATEGY = "lock_repair_strategy"
    DERIVE_COMPONENTS = "derive_components"
    CALCULATE_QUANTITY_AND_LABOUR = "calculate_quantity_and_labour"
    PRICE_AND_RECOVER = "price_and_recover"
    RUN_INDEPENDENT_VALIDATION = "run_independent_validation"
    CREATE_VALIDATED_SNAPSHOT = "create_validated_snapshot"
    RENDER_OUTPUT = "render_output"
    HUMAN_RELEASE = "human_release"


class WorkflowTransitionError(RuntimeError):
    def __init__(self, action: WorkflowAction, blockers: tuple[str, ...]):
        self.action = action
        self.blockers = blockers
        message = f"Action '{action.value}' blocked: " + "; ".join(blockers)
        super().__init__(message)


@dataclass(frozen=True)
class WorkflowFacts:
    evidence_intake_complete: bool = False
    physical_model_complete: bool = False
    physical_model_locked: bool = False
    technical_search_complete: bool = False
    repair_strategy_locked: bool = False
    components_derived: bool = False
    quantity_and_labour_complete: bool = False
    commercial_pricing_and_recovery_complete: bool = False
    independent_validation_passed: bool = False
    validated_snapshot_created: bool = False
    output_rendered: bool = False
    human_release_approved: bool = False


_STAGE_SEQUENCE: tuple[tuple[WorkflowStage, str], ...] = (
    (WorkflowStage.EVIDENCE_INTAKE, "evidence_intake_complete"),
    (WorkflowStage.PHYSICAL_MODEL, "physical_model_complete"),
    (WorkflowStage.PHYSICAL_MODEL_LOCK, "physical_model_locked"),
    (WorkflowStage.OPENING_SPECIFIC_TECHNICAL_SEARCH, "technical_search_complete"),
    (WorkflowStage.REPAIR_STRATEGY_LOCK, "repair_strategy_locked"),
    (WorkflowStage.COMPONENT_DERIVATION, "components_derived"),
    (WorkflowStage.QUANTITY_AND_LABOUR, "quantity_and_labour_complete"),
    (
        WorkflowStage.COMMERCIAL_PRICING_AND_RECOVERY,
        "commercial_pricing_and_recovery_complete",
    ),
    (WorkflowStage.INDEPENDENT_VALIDATION, "independent_validation_passed"),
    (WorkflowStage.VALIDATED_SNAPSHOT, "validated_snapshot_created"),
    (WorkflowStage.OUTPUT_RENDERING, "output_rendered"),
    (WorkflowStage.HUMAN_RELEASE, "human_release_approved"),
)


_ACTION_REQUIREMENTS: dict[WorkflowAction, tuple[str, ...]] = {
    WorkflowAction.INGEST_EVIDENCE: (),
    WorkflowAction.EDIT_PHYSICAL_MODEL: ("evidence_intake_complete",),
    WorkflowAction.LOCK_PHYSICAL_MODEL: (
        "evidence_intake_complete",
        "physical_model_complete",
    ),
    WorkflowAction.SEARCH_TECHNICAL: ("physical_model_locked",),
    WorkflowAction.LOCK_REPAIR_STRATEGY: (
        "physical_model_locked",
        "technical_search_complete",
    ),
    WorkflowAction.DERIVE_COMPONENTS: ("repair_strategy_locked",),
    WorkflowAction.CALCULATE_QUANTITY_AND_LABOUR: (
        "repair_strategy_locked",
        "components_derived",
    ),
    WorkflowAction.PRICE_AND_RECOVER: (
        "repair_strategy_locked",
        "components_derived",
        "quantity_and_labour_complete",
    ),
    WorkflowAction.RUN_INDEPENDENT_VALIDATION: (
        "physical_model_locked",
        "repair_strategy_locked",
        "components_derived",
        "quantity_and_labour_complete",
        "commercial_pricing_and_recovery_complete",
    ),
    WorkflowAction.CREATE_VALIDATED_SNAPSHOT: ("independent_validation_passed",),
    WorkflowAction.RENDER_OUTPUT: ("validated_snapshot_created",),
    WorkflowAction.HUMAN_RELEASE: (
        "independent_validation_passed",
        "validated_snapshot_created",
        "output_rendered",
    ),
}


_FIELD_LABELS = {
    "evidence_intake_complete": "evidence intake is not complete",
    "physical_model_complete": "physical model is not complete",
    "physical_model_locked": "Physical Model Lock is not valid",
    "technical_search_complete": "opening-specific technical search is not complete",
    "repair_strategy_locked": "Repair Strategy Lock is not valid",
    "components_derived": "required component derivation is not complete",
    "quantity_and_labour_complete": "quantity and labour derivation is not complete",
    "commercial_pricing_and_recovery_complete": "commercial pricing and recovery is not complete",
    "independent_validation_passed": "independent validation has not passed",
    "validated_snapshot_created": "validated snapshot does not exist",
    "output_rendered": "controlled output has not been rendered",
    "human_release_approved": "human release approval has not been recorded",
}


def current_stage(facts: WorkflowFacts) -> WorkflowStage:
    """Return the first incomplete QUANTIFIRE v2.13 hard stage."""
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
