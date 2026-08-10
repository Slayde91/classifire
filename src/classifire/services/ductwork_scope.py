from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import pi

from .frl_policy import ScopeClass


class DuctShape(StrEnum):
    RECTANGULAR = "RECTANGULAR"
    CIRCULAR = "CIRCULAR"


class DuctProtectionMethod(StrEnum):
    FIRE_WRAP = "FIRE_WRAP"
    FIRE_SPRAY = "FIRE_SPRAY"
    FIRE_BOARD = "FIRE_BOARD"
    OTHER_APPROVED_SYSTEM = "OTHER_APPROVED_SYSTEM"


def _positive(value: float, field_name: str) -> float:
    number = float(value)
    if number <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
    return number


@dataclass(frozen=True, slots=True)
class DuctRunSegment:
    """One measurable segment of an entire duct run requiring fire protection."""

    segment_id: str
    length_m: float
    shape: DuctShape
    width_mm: float | None = None
    height_mm: float | None = None
    diameter_mm: float | None = None
    start_location: str | None = None
    end_location: str | None = None
    orientation: str | None = None
    evidence_status: str = "provisional"
    confidence: float | None = None

    def __post_init__(self) -> None:
        if not self.segment_id.strip():
            raise ValueError("segment_id cannot be blank")
        _positive(self.length_m, "length_m")
        if self.shape is DuctShape.RECTANGULAR:
            if self.width_mm is None or self.height_mm is None:
                raise ValueError("Rectangular duct segments require width_mm and height_mm")
            _positive(self.width_mm, "width_mm")
            _positive(self.height_mm, "height_mm")
        elif self.shape is DuctShape.CIRCULAR:
            if self.diameter_mm is None:
                raise ValueError("Circular duct segments require diameter_mm")
            _positive(self.diameter_mm, "diameter_mm")

    @property
    def developed_area_m2(self) -> float:
        """External duct surface area before laps, waste and system-specific allowances."""

        if self.shape is DuctShape.RECTANGULAR:
            assert self.width_mm is not None
            assert self.height_mm is not None
            perimeter_m = 2.0 * (self.width_mm + self.height_mm) / 1000.0
            return perimeter_m * self.length_m
        assert self.diameter_mm is not None
        circumference_m = pi * self.diameter_mm / 1000.0
        return circumference_m * self.length_m


@dataclass(frozen=True, slots=True)
class DuctProtectionRequirement:
    """Provisional requirement for protecting the full identified duct route."""

    protection_method: DuctProtectionMethod
    required_frl: str | None
    wrap_layers: int | None = None
    wrap_thickness_mm: float | None = None
    target_dft_mm: float | None = None
    existing_dft_mm: float | None = None
    technical_system_id: str | None = None
    evidence_status: str = "provisional"

    def __post_init__(self) -> None:
        if self.wrap_layers is not None and self.wrap_layers <= 0:
            raise ValueError("wrap_layers must be greater than zero")
        if self.wrap_thickness_mm is not None:
            _positive(self.wrap_thickness_mm, "wrap_thickness_mm")
        if self.target_dft_mm is not None:
            _positive(self.target_dft_mm, "target_dft_mm")
        if self.existing_dft_mm is not None and self.existing_dft_mm < 0:
            raise ValueError("existing_dft_mm cannot be negative")


@dataclass(frozen=True, slots=True)
class FireRatedDuctRun:
    """Entire run of ductwork requiring wrap, spray, board or another approved system."""

    duct_run_id: str
    segments: tuple[DuctRunSegment, ...]
    requirement: DuctProtectionRequirement
    location: str | None = None
    notes: str | None = None
    scope_class: ScopeClass = ScopeClass.FIRE_RATED_DUCT_RUN

    def __post_init__(self) -> None:
        if not self.duct_run_id.strip():
            raise ValueError("duct_run_id cannot be blank")
        if not self.segments:
            raise ValueError("A fire-rated duct run must contain at least one measured segment")
        segment_ids = [segment.segment_id for segment in self.segments]
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError("Duct segment IDs must be unique within a run")
        if self.scope_class is not ScopeClass.FIRE_RATED_DUCT_RUN:
            raise ValueError("FireRatedDuctRun must use FIRE_RATED_DUCT_RUN scope_class")

    @property
    def total_length_m(self) -> float:
        return sum(segment.length_m for segment in self.segments)

    @property
    def developed_area_m2(self) -> float:
        return sum(segment.developed_area_m2 for segment in self.segments)


__all__ = [
    "DuctProtectionMethod",
    "DuctProtectionRequirement",
    "DuctRunSegment",
    "DuctShape",
    "FireRatedDuctRun",
]
