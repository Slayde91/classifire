from __future__ import annotations

from pathlib import Path


def _source() -> str:
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_classifire_real_uat_defectwise.py"
    )
    source = path.read_text(encoding="utf-8")
    compile(source, str(path), "exec")
    return source


def test_defectwise_runner_compiles_and_does_not_force_one_to_one_scope() -> None:
    source = _source()
    assert "This defect may contain zero, one, or MULTIPLE openings and MULTIPLE services" in source
    assert "One photo, report row, or defect ID does NOT establish quantity one" in source


def test_defectwise_runner_refuses_partial_canonical_submission() -> None:
    source = _source()
    assert "if limitations:" in source
    assert '"model_submitted": False' in source
    assert "CLASSIFIRE refuses partial canonical submission before Physical Model Lock" in source


def test_defectwise_runner_requires_explicit_positive_service_quantity() -> None:
    source = _source()
    assert "has no explicit numeric quantity" in source
    assert "quantity must be greater than zero" in source
