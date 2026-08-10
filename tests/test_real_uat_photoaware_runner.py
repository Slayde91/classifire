from __future__ import annotations

from pathlib import Path


def _source() -> str:
    return (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_classifire_real_uat_photoaware.py"
    ).read_text(encoding="utf-8")


def test_photoaware_runner_requires_native_resolution_and_zoom_fallback() -> None:
    source = _source()
    assert 'document.extract_image(xref)' in source
    assert 'PHOTO_ZOOM_DPI = 420' in source
    assert 'page.get_pixmap(' in source
    assert 'needs_zoom' in source
    assert 'native_extraction_ok' in source


def test_photoaware_runner_ignores_decorative_report_graphics() -> None:
    source = _source()
    assert 'decorative_candidate' in source
    assert 'header/footer' in source
    assert 'Company logos, header/footer' in source
    assert 'scope_relevance": "relevant|non_scope|uncertain' in source


def test_photoaware_runner_reconciles_multiple_views_without_double_counting() -> None:
    source = _source()
    assert 'same_asset_same_side_different_angle' in source
    assert 'same_service_opposite_barrier_side' in source
    assert 'same_opening_opposite_barrier_side' in source
    assert 'Photograph count NEVER equals service count or opening count.' in source
    assert 'The same service photographed on opposite faces of a wall' in source
    assert 'Multiple distinct services passing through one opening are separate Services but one Opening.' in source


def test_photoaware_evidence_is_defect_linked_before_physical_submission() -> None:
    source = _source()
    assert 'PHOTO_LINK_EVIDENCE_TYPE = "defect_page_photo_linkage_review"' in source
    assert 'PHOTO_DETAIL_EVIDENCE_TYPE = "defect_photo_detail_review"' in source
    assert 'PHOTO_RECONCILIATION_EVIDENCE_TYPE = "defect_photo_reconciliation"' in source
    assert '"external_defect_id": defect.external_defect_id or defect.defect_code' in source
    assert 'final_state = self.run_defectwise_physical()' in source


def test_pymupdf_is_a_runtime_dependency() -> None:
    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert '"PyMuPDF>=1.26,<2"' in pyproject
