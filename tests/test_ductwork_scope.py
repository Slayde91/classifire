from __future__ import annotations

from math import pi

import pytest

from classifire.services.ductwork_scope import (
    DuctProtectionMethod,
    DuctProtectionRequirement,
    DuctRunSegment,
    DuctShape,
    FireRatedDuctRun,
)
from classifire.services.frl_policy import ScopeClass


def _requirement() -> DuctProtectionRequirement:
    return DuctProtectionRequirement(
        protection_method=DuctProtectionMethod.FIRE_WRAP,
        required_frl="-/120/120",
        wrap_layers=2,
        wrap_thickness_mm=25,
    )


def test_rectangular_full_run_uses_length_and_developed_area() -> None:
    segment = DuctRunSegment(
        segment_id="SEG-1",
        length_m=10,
        shape=DuctShape.RECTANGULAR,
        width_mm=1000,
        height_mm=500,
    )
    run = FireRatedDuctRun(
        duct_run_id="DUCT-RUN-1",
        segments=(segment,),
        requirement=_requirement(),
    )

    assert run.scope_class is ScopeClass.FIRE_RATED_DUCT_RUN
    assert run.total_length_m == pytest.approx(10)
    assert run.developed_area_m2 == pytest.approx(30)


def test_circular_full_run_uses_length_and_circumference() -> None:
    segment = DuctRunSegment(
        segment_id="SEG-1",
        length_m=5,
        shape=DuctShape.CIRCULAR,
        diameter_mm=400,
    )

    assert segment.developed_area_m2 == pytest.approx(pi * 0.4 * 5)


def test_multiple_duct_segments_are_aggregated_as_one_run() -> None:
    first = DuctRunSegment(
        segment_id="SEG-A",
        length_m=4,
        shape=DuctShape.RECTANGULAR,
        width_mm=600,
        height_mm=300,
    )
    second = DuctRunSegment(
        segment_id="SEG-B",
        length_m=6,
        shape=DuctShape.RECTANGULAR,
        width_mm=800,
        height_mm=400,
    )
    run = FireRatedDuctRun(
        duct_run_id="DUCT-RUN-2",
        segments=(first, second),
        requirement=DuctProtectionRequirement(
            protection_method=DuctProtectionMethod.FIRE_SPRAY,
            required_frl="-/120/120",
            target_dft_mm=20,
            existing_dft_mm=0,
        ),
    )

    assert run.total_length_m == pytest.approx(10)
    assert run.developed_area_m2 == pytest.approx(
        first.developed_area_m2 + second.developed_area_m2
    )
    assert run.requirement.target_dft_mm == 20


def test_rectangular_segment_requires_both_dimensions() -> None:
    with pytest.raises(ValueError, match="width_mm and height_mm"):
        DuctRunSegment(
            segment_id="SEG-1",
            length_m=4,
            shape=DuctShape.RECTANGULAR,
            width_mm=600,
        )


def test_fire_rated_duct_run_cannot_be_reclassified_as_penetration() -> None:
    segment = DuctRunSegment(
        segment_id="SEG-1",
        length_m=2,
        shape=DuctShape.CIRCULAR,
        diameter_mm=300,
    )

    with pytest.raises(ValueError, match="FIRE_RATED_DUCT_RUN"):
        FireRatedDuctRun(
            duct_run_id="DUCT-RUN-3",
            segments=(segment,),
            requirement=_requirement(),
            scope_class=ScopeClass.DUCT_BARRIER_PENETRATION,
        )


def test_duplicate_segment_ids_are_rejected() -> None:
    segment = DuctRunSegment(
        segment_id="SEG-1",
        length_m=2,
        shape=DuctShape.CIRCULAR,
        diameter_mm=300,
    )

    with pytest.raises(ValueError, match="unique"):
        FireRatedDuctRun(
            duct_run_id="DUCT-RUN-4",
            segments=(segment, segment),
            requirement=_requirement(),
        )
