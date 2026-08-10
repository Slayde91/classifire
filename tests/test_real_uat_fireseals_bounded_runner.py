from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_classifire_real_uat_fireseals_bounded import (  # noqa: E402
    BOUNDED_DEFECT_EVIDENCE_CHARS,
    BoundedFireSealFocusedController,
    _supported_scope_present,
    build_projected_defect_bundle,
)


def test_measured_real_uat_bundle_uses_revised_budget() -> None:
    assert BOUNDED_DEFECT_EVIDENCE_CHARS == 12_000
    assert 9_923 < BOUNDED_DEFECT_EVIDENCE_CHARS


def test_field_aware_projection_bounds_large_nested_direct_evidence() -> None:
    rows = []
    for index in range(18):
        rows.append(
            {
                "type": "defect_text_fact_review" if index % 2 == 0 else "defect_photo_reconciliation",
                "page": str(index + 1),
                "region": f"region-{index}",
                "association_status": "SUPPORTED",
                "attributes": [
                    {
                        "name": "service_type",
                        "value": "electrical and plumbing services " * 20,
                        "status": "stated",
                        "source_role": "description",
                        "basis": "source basis " * 80,
                    }
                    for _ in range(12)
                ],
                "quantities": [
                    {
                        "kind": "service_count",
                        "value": 4,
                        "unit": "services",
                        "status": "inferred",
                        "basis": "counting basis " * 80,
                    }
                    for _ in range(10)
                ],
                "services": [
                    {
                        "label": f"service-{item}",
                        "service_type": "pipe",
                        "material": "copper",
                        "size": "25 mm",
                        "quantity": 1,
                        "status": "inferred",
                        "basis": "visual basis " * 80,
                    }
                    for item in range(10)
                ],
                "opening_count": {"value": 1, "status": "inferred", "basis": ["visible opening"]},
                "service_count": {"value": 4, "status": "inferred", "basis": ["visible services"]},
                "openings": [{"label": "opening-1", "substrate_plane": "wall"}],
                "relationships": ["same opening"],
                "physical_facts": ["physical fact " * 60 for _ in range(12)],
                "uncertainties": ["uncertainty " * 60 for _ in range(12)],
            }
        )

    bundle = build_projected_defect_bundle(
        {
            "external_defect_id": "147044",
            "description": "Multiple electrical and plumbing services through wall",
            "location": "Unisex toilet",
        },
        rows,
    )

    assert len(bundle) <= BOUNDED_DEFECT_EVIDENCE_CHARS
    assert "technical_selection_deferred" in bundle
    assert "photo_count_is_not_quantity" in bundle


def test_supported_status_requires_actual_openings_and_services() -> None:
    assert _supported_scope_present(
        {
            "status": "MODEL_SUPPORTED",
            "openings": [{"opening_code": "D-O-001"}],
            "services": [{"service_code": "D-S-001"}],
        }
    ) is True
    assert _supported_scope_present(
        {"status": "MODEL_SUPPORTED", "openings": [], "services": []}
    ) is False
    assert _supported_scope_present(
        {"status": "INSUFFICIENT_EVIDENCE", "openings": [], "services": []}
    ) is False


def test_bounded_runner_overrides_bundle_cache_and_synthesis_validation() -> None:
    assert "_bundle_for_defect" in BoundedFireSealFocusedController.__dict__
    assert "_cached_supported_model" in BoundedFireSealFocusedController.__dict__
    assert "_synthesise_defect" in BoundedFireSealFocusedController.__dict__
    assert "run" not in BoundedFireSealFocusedController.__dict__


def test_bounded_runner_retains_deterministic_non_reduction_path() -> None:
    source = (SCRIPTS / "run_classifire_real_uat_fireseals_bounded.py").read_text(
        encoding="utf-8"
    )
    assert "build_projected_defect_bundle" in source
    assert "max_chars=BOUNDED_DEFECT_EVIDENCE_CHARS" in source
    assert "_reduce_physical_evidence" not in source
    assert "AI reduction pass" in source
    assert "Never\nreturn MODEL_SUPPORTED with empty openings or services" in source
