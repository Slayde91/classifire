from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_classifire_real_uat_fireseals_resumable import (  # noqa: E402
    ResumableFireSealFocusedController,
)


def test_gateway_timeout_detection_is_narrow() -> None:
    assert ResumableFireSealFocusedController._is_gateway_timeout(
        RuntimeError("GatewayTransportError: gateway timeout after 120000ms")
    ) is True
    assert ResumableFireSealFocusedController._is_gateway_timeout(
        RuntimeError("GatewayTransportError: authentication failed")
    ) is False
    assert ResumableFireSealFocusedController._is_gateway_timeout(
        RuntimeError("MODEL_SUPPORTED with empty physical scope")
    ) is False


def test_resumable_runner_preserves_bounded_controller() -> None:
    names = {base.__name__ for base in ResumableFireSealFocusedController.__mro__}
    assert "BoundedFireSealFocusedController" in names
    assert "FireSealFocusedController" in names


def test_local_fallback_keeps_openclaw_model_probe_semantics() -> None:
    source = (SCRIPTS / "run_classifire_real_uat_fireseals_resumable.py").read_text(
        encoding="utf-8"
    )
    assert '"--local"' in source
    assert '"--model"' in source
    assert "INFER_MODEL" in source
    assert '"--thinking"' in source
    assert '"--prompt"' in source
    assert "GatewayTransportError" in source
    assert "gateway timeout" in source
    assert "return super().infer_model" in source


def test_transport_patch_does_not_override_physical_bundle_or_run() -> None:
    assert "_bundle_for_defect" not in ResumableFireSealFocusedController.__dict__
    assert "run" not in ResumableFireSealFocusedController.__dict__
    assert "infer_model" in ResumableFireSealFocusedController.__dict__
