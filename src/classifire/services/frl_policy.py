from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class ScopeClass(StrEnum):
    """Evidence-backed physical-scope classification used before technical selection."""

    SERVICE_PENETRATION = "SERVICE_PENETRATION"
    FIRE_SEAL = "FIRE_SEAL"
    LINEAR_JOINT = "LINEAR_JOINT"
    DAMPER = "DAMPER"
    DAMPER_PENETRATION = "DAMPER_PENETRATION"
    DUCT_BARRIER_PENETRATION = "DUCT_BARRIER_PENETRATION"
    FIRE_RATED_DUCT_RUN = "FIRE_RATED_DUCT_RUN"
    STEEL_BARRIER_PENETRATION = "STEEL_BARRIER_PENETRATION"
    PURLIN_BARRIER_PENETRATION = "PURLIN_BARRIER_PENETRATION"
    STRUCTURAL_STEEL_FIRE_PROTECTION = "STRUCTURAL_STEEL_FIRE_PROTECTION"
    STRUCTURAL_STEEL_COATING_REPAIR = "STRUCTURAL_STEEL_COATING_REPAIR"
    ACCESS_PANEL_OR_DOOR = "ACCESS_PANEL_OR_DOOR"
    OTHER_PASSIVE_FIRE_SCOPE = "OTHER_PASSIVE_FIRE_SCOPE"

    # Compatibility aliases for early UAT terminology. New code and outputs must use
    # the explicit canonical names above so full-run duct protection is never confused
    # with treatment of a single barrier penetration.
    DUCT_PENETRATION = "DUCT_BARRIER_PENETRATION"
    FIRE_RATED_DUCTWORK = "FIRE_RATED_DUCT_RUN"


FRLStatus = Literal["source_confirmed", "assumed", "unresolved"]
FRLFormatFamily = Literal[
    "structural_integrity_insulation",
    "structural_only",
    "unresolved",
]

PENETRATION_DEFAULT_FRL = "-/120/120"
FIRE_RATED_DUCT_RUN_DEFAULT_FRL = "-/120/120"
STRUCTURAL_STEEL_DEFAULT_FRL = "120/-/-"

PENETRATION_STYLE_SCOPES = frozenset(
    {
        ScopeClass.SERVICE_PENETRATION,
        ScopeClass.FIRE_SEAL,
        ScopeClass.DAMPER,
        ScopeClass.DAMPER_PENETRATION,
        ScopeClass.DUCT_BARRIER_PENETRATION,
        ScopeClass.STEEL_BARRIER_PENETRATION,
        ScopeClass.PURLIN_BARRIER_PENETRATION,
    }
)

FIRE_RATED_DUCT_RUN_SCOPES = frozenset({ScopeClass.FIRE_RATED_DUCT_RUN})

STRUCTURAL_STEEL_SCOPES = frozenset(
    {
        ScopeClass.STRUCTURAL_STEEL_FIRE_PROTECTION,
        ScopeClass.STRUCTURAL_STEEL_COATING_REPAIR,
    }
)


@dataclass(frozen=True, slots=True)
class FRLResolution:
    """A source value or a governed estimating assumption, never silent inference."""

    frl: str | None
    status: FRLStatus
    format_family: FRLFormatFamily
    basis_code: str
    note: str | None
    human_verification_required: bool

    @property
    def assumed(self) -> bool:
        return self.status == "assumed"


def _clean_source_frl(source_frl: str | None) -> str | None:
    if source_frl is None:
        return None
    value = str(source_frl).strip()
    if not value or value.lower() in {
        "unknown",
        "not provided",
        "not stated",
        "n/a",
        "none",
        "null",
        "-",
    }:
        return None
    return value


def resolve_frl(
    *,
    scope_class: ScopeClass | str,
    source_frl: str | None,
) -> FRLResolution:
    """Resolve FRL for estimating without allowing a hidden default.

    Source evidence always wins. Missing FRL defaults only for scope classes that
    have an explicitly approved CLASSIFIRE estimating policy. Final technical
    approval and Human Release must still verify the Project-required FRL and the
    selected tested or assessed system.
    """

    classification = ScopeClass(scope_class)
    supplied = _clean_source_frl(source_frl)
    if supplied is not None:
        family: FRLFormatFamily = (
            "structural_only"
            if classification in STRUCTURAL_STEEL_SCOPES
            else "structural_integrity_insulation"
        )
        return FRLResolution(
            frl=supplied,
            status="source_confirmed",
            format_family=family,
            basis_code="CLASSIFIRE-FRL-SOURCE-v1",
            note=None,
            human_verification_required=False,
        )

    if classification in PENETRATION_STYLE_SCOPES:
        return FRLResolution(
            frl=PENETRATION_DEFAULT_FRL,
            status="assumed",
            format_family="structural_integrity_insulation",
            basis_code="CLASSIFIRE-FRL-DEFAULT-PENETRATION-v1",
            note=(
                "FRL was not provided in the source evidence. CLASSIFIRE assumed "
                f"{PENETRATION_DEFAULT_FRL} for estimating this barrier penetration, "
                "fire seal or damper scope. Verify the required FRL and the selected "
                "approved system before technical approval or Human Release."
            ),
            human_verification_required=True,
        )

    if classification in FIRE_RATED_DUCT_RUN_SCOPES:
        return FRLResolution(
            frl=FIRE_RATED_DUCT_RUN_DEFAULT_FRL,
            status="assumed",
            format_family="structural_integrity_insulation",
            basis_code="CLASSIFIRE-FRL-DEFAULT-DUCT-RUN-v1",
            note=(
                "FRL was not provided in the source evidence. CLASSIFIRE assumed "
                f"{FIRE_RATED_DUCT_RUN_DEFAULT_FRL} for estimating protection of the "
                "complete identified duct run, not merely a barrier penetration. Verify "
                "the required FRL, protected route, duct geometry, exposure, supports, "
                "length and selected fire-wrap, fire-spray or board system before "
                "technical approval or Human Release."
            ),
            human_verification_required=True,
        )

    if classification in STRUCTURAL_STEEL_SCOPES:
        return FRLResolution(
            frl=STRUCTURAL_STEEL_DEFAULT_FRL,
            status="assumed",
            format_family="structural_only",
            basis_code="CLASSIFIRE-FRL-DEFAULT-STRUCTURAL-STEEL-v1",
            note=(
                "FRL was not provided in the source evidence. CLASSIFIRE assumed "
                f"{STRUCTURAL_STEEL_DEFAULT_FRL} for structural-steel fire-protection "
                "estimating. Verify the required FRL, critical temperature, section "
                "factor and selected approved protection system before technical "
                "approval or Human Release."
            ),
            human_verification_required=True,
        )

    return FRLResolution(
        frl=None,
        status="unresolved",
        format_family="unresolved",
        basis_code="CLASSIFIRE-FRL-NO-DEFAULT-v1",
        note=(
            "FRL was not provided and this scope class has no authorised CLASSIFIRE "
            "estimating default. Human or Project evidence is required."
        ),
        human_verification_required=True,
    )


__all__ = [
    "FIRE_RATED_DUCT_RUN_DEFAULT_FRL",
    "FRLResolution",
    "PENETRATION_DEFAULT_FRL",
    "STRUCTURAL_STEEL_DEFAULT_FRL",
    "ScopeClass",
    "resolve_frl",
]
