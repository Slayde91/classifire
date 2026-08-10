from __future__ import annotations

import pytest

from classifire.services.frl_policy import (
    FIRE_RATED_DUCT_RUN_DEFAULT_FRL,
    PENETRATION_DEFAULT_FRL,
    STRUCTURAL_STEEL_DEFAULT_FRL,
    ScopeClass,
    resolve_frl,
)


@pytest.mark.parametrize(
    "scope_class",
    [
        ScopeClass.SERVICE_PENETRATION,
        ScopeClass.FIRE_SEAL,
        ScopeClass.DAMPER,
        ScopeClass.DAMPER_PENETRATION,
        ScopeClass.DUCT_BARRIER_PENETRATION,
        ScopeClass.STEEL_BARRIER_PENETRATION,
        ScopeClass.PURLIN_BARRIER_PENETRATION,
    ],
)
def test_penetration_style_scope_uses_governed_120_minute_default(
    scope_class: ScopeClass,
) -> None:
    result = resolve_frl(scope_class=scope_class, source_frl=None)

    assert result.frl == PENETRATION_DEFAULT_FRL
    assert result.status == "assumed"
    assert result.format_family == "structural_integrity_insulation"
    assert result.basis_code == "CLASSIFIRE-FRL-DEFAULT-PENETRATION-v1"
    assert result.human_verification_required is True
    assert "barrier penetration" in str(result.note)


def test_full_fire_rated_duct_run_is_not_treated_as_a_penetration() -> None:
    result = resolve_frl(
        scope_class=ScopeClass.FIRE_RATED_DUCT_RUN,
        source_frl=None,
    )

    assert result.frl == FIRE_RATED_DUCT_RUN_DEFAULT_FRL
    assert result.status == "assumed"
    assert result.format_family == "structural_integrity_insulation"
    assert result.basis_code == "CLASSIFIRE-FRL-DEFAULT-DUCT-RUN-v1"
    assert "complete identified duct run" in str(result.note)
    assert "not merely a barrier penetration" in str(result.note)
    assert "length" in str(result.note)


def test_legacy_ductwork_scope_alias_resolves_to_full_run_class() -> None:
    assert ScopeClass.FIRE_RATED_DUCTWORK is ScopeClass.FIRE_RATED_DUCT_RUN
    assert ScopeClass.DUCT_PENETRATION is ScopeClass.DUCT_BARRIER_PENETRATION


@pytest.mark.parametrize(
    "scope_class",
    [
        ScopeClass.STRUCTURAL_STEEL_FIRE_PROTECTION,
        ScopeClass.STRUCTURAL_STEEL_COATING_REPAIR,
    ],
)
def test_structural_steel_scope_uses_structural_only_default(
    scope_class: ScopeClass,
) -> None:
    result = resolve_frl(scope_class=scope_class, source_frl="not provided")

    assert result.frl == STRUCTURAL_STEEL_DEFAULT_FRL
    assert result.status == "assumed"
    assert result.format_family == "structural_only"
    assert result.basis_code == "CLASSIFIRE-FRL-DEFAULT-STRUCTURAL-STEEL-v1"
    assert result.human_verification_required is True
    assert "section factor" in str(result.note)


def test_source_frl_wins_over_default() -> None:
    result = resolve_frl(
        scope_class=ScopeClass.SERVICE_PENETRATION,
        source_frl="-/90/90",
    )

    assert result.frl == "-/90/90"
    assert result.status == "source_confirmed"
    assert result.basis_code == "CLASSIFIRE-FRL-SOURCE-v1"
    assert result.note is None
    assert result.human_verification_required is False


def test_source_duct_run_frl_wins_over_default() -> None:
    result = resolve_frl(
        scope_class=ScopeClass.FIRE_RATED_DUCT_RUN,
        source_frl="-/60/60",
    )

    assert result.frl == "-/60/60"
    assert result.status == "source_confirmed"
    assert result.basis_code == "CLASSIFIRE-FRL-SOURCE-v1"


def test_source_structural_frl_retains_structural_format_family() -> None:
    result = resolve_frl(
        scope_class=ScopeClass.STRUCTURAL_STEEL_FIRE_PROTECTION,
        source_frl="90/-/-",
    )

    assert result.frl == "90/-/-"
    assert result.status == "source_confirmed"
    assert result.format_family == "structural_only"


def test_scope_without_authorised_default_remains_unresolved() -> None:
    result = resolve_frl(
        scope_class=ScopeClass.OTHER_PASSIVE_FIRE_SCOPE,
        source_frl=None,
    )

    assert result.frl is None
    assert result.status == "unresolved"
    assert result.format_family == "unresolved"
    assert result.basis_code == "CLASSIFIRE-FRL-NO-DEFAULT-v1"
    assert result.human_verification_required is True


def test_unknown_scope_class_is_rejected() -> None:
    with pytest.raises(ValueError):
        resolve_frl(scope_class="NOT_A_REAL_SCOPE", source_frl=None)
