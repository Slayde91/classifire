from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from audit_classifire_opening_service_relationships import _deterministic_findings  # noqa: E402


def test_multi_service_opening_is_retained_not_split() -> None:
    findings = _deterministic_findings(
        [
            {
                "opening_code": "O-001",
                "opening_type": "service_penetration",
                "service_count": 3,
                "services": [
                    {"service_code": "S-001", "material": "PVC"},
                    {"service_code": "S-002", "material": "copper"},
                    {"service_code": "S-003", "material": "cable"},
                ],
            }
        ]
    )
    assert any("multi-service Opening" in item["issue"] for item in findings)
    assert not any(item["severity"] == "ERROR" for item in findings)


def test_blank_opening_with_zero_services_is_valid() -> None:
    findings = _deterministic_findings(
        [
            {
                "opening_code": "O-001",
                "opening_type": "blank_core_hole",
                "service_count": 0,
                "services": [],
            }
        ]
    )
    assert findings == []


def test_blank_opening_with_service_is_error() -> None:
    findings = _deterministic_findings(
        [
            {
                "opening_code": "O-001",
                "opening_type": "blank_core_hole",
                "service_count": 1,
                "services": [{"service_code": "S-001", "material": "PVC"}],
            }
        ]
    )
    assert any(item["severity"] == "ERROR" for item in findings)


def test_unresolved_material_requires_review() -> None:
    findings = _deterministic_findings(
        [
            {
                "opening_code": "O-001",
                "opening_type": "service_penetration",
                "service_count": 1,
                "services": [{"service_code": "S-001", "material": None}],
            }
        ]
    )
    assert any(item["severity"] == "REVIEW" for item in findings)


def test_audit_prompt_contains_mixed_service_ontology() -> None:
    source = (SCRIPTS / "audit_classifire_opening_service_relationships.py").read_text(
        encoding="utf-8"
    )
    assert "ONE Opening may contain ONE OR MANY Services" in source
    assert "cable bundle + PVC pipe + metal pipe" in source
    assert "Never infer one Opening per Service" in source
    assert "Opposite faces or different angles" in source
    assert "read-only" in source.lower()
