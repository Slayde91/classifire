"""Run shipped assistant script behaviors when the optional Node.js test tool is available."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_workspace_session_javascript_behaviors():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable; run the standalone workspace session script tests")
    result = subprocess.run(  # noqa: S603 - discovered Node executable and fixed repository test
        [node, "--test", str(ROOT / "tests" / "js" / "workspace_session_test.cjs")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
