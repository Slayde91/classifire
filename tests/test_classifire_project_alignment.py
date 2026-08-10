from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from audit_classifire_project_alignment import audit_project  # noqa: E402


def test_project_and_knowledge_alignment_has_no_hard_errors() -> None:
    result = audit_project(ROOT)
    assert result["ok"] is True, result["errors"]
    assert result["error_count"] == 0


def test_missing_private_source_pack_is_warning_until_k1_gate() -> None:
    result = audit_project(ROOT, require_source_pack=False)
    published = ROOT / "knowledge/source/CLASSIFIRE_Knowledge_Source_Pack_v2.13.zip"
    if not published.exists():
        assert any("source pack" in warning.lower() for warning in result["warnings"])


def test_alignment_audit_tracks_known_migrations_without_false_pass() -> None:
    result = audit_project(ROOT)
    warnings = "\n".join(result["warnings"])
    assert "package15_release_id" in warnings
    assert "quantity of 1" in warnings
