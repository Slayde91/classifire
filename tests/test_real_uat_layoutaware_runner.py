from __future__ import annotations

from pathlib import Path


def test_layoutaware_runner_preserves_defect_linkage_and_full_page_layout() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_classifire_real_uat_layoutaware.py"
    ).read_text(encoding="utf-8")

    assert 'LAYOUT_EVIDENCE_TYPE = "defect_page_layout_review"' in source
    assert '"external_defect_id": defect.external_defect_id or defect.defect_code' in source
    assert '"region_reference": f"page-layout:{page_number}:defect:{identity}"' in source
    assert "page.get_pixmap(" in source
    assert "Do not associate a photo with the target merely because it is on the same page" in source


def test_layoutaware_compaction_keeps_physical_structure() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_classifire_real_uat_layoutaware.py"
    ).read_text(encoding="utf-8")

    for field in (
        '"association_status"',
        '"opening_count"',
        '"service_count"',
        '"openings"',
        '"services"',
        '"relationships"',
        '"physical_facts"',
        '"uncertainties"',
    ):
        assert field in source


def test_pymupdf_is_declared_runtime_dependency() -> None:
    pyproject = (
        Path(__file__).resolve().parents[1] / "pyproject.toml"
    ).read_text(encoding="utf-8")
    assert '"PyMuPDF>=1.26,<2"' in pyproject
