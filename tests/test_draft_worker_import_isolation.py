"""Fresh parser processes must not bootstrap unrelated application dependencies."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_draft_scope_docx import word_bytes
from test_draft_scope_xlsx_worker import picture, workbook

from classifire.services.draft_pricing_worker import process, process_scope, process_scope_image
from classifire.services.draft_scope_docx_document import encode, parse

# Fail at the import attempt, even if parsing could otherwise hide a caught error.
ISOLATED_WORKER = """
import importlib.abc
import sys

class NoApplicationImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        forbidden = (
            "classifire.config", "classifire.db", "classifire.models",
            "classifire.physical_models", "sqlalchemy", "fastapi", "pymupdf",
        )
        if any(fullname == name or fullname.startswith(name + ".") for name in forbidden):
            raise AssertionError("Parser imported unrelated dependency: " + fullname)

sys.meta_path.insert(0, NoApplicationImports())
from classifire.services.draft_pricing_worker import main
main()
"""


@pytest.mark.parametrize("mode", ["pricing", "scope", "scope-image", "word", "word-image"])
def test_fresh_worker_preserves_exact_output_without_application_imports(mode):
    if mode.startswith("word"):
        content = word_bytes()
        document, previews = parse(content)
        arguments = ["--word-evidence"] if mode == "word" else ["--word-image", "picture-1"]
        expected = encode(document) if mode == "word" else previews["picture-1"]
    else:
        content = workbook(images=[] if mode == "pricing" else [picture()])
        if mode == "pricing":
            arguments, expected = [], process(content)
        elif mode == "scope":
            arguments, expected = ["--scope-evidence"], process_scope(content)
        else:
            arguments = ["--scope-image", "1", "image-1"]
            expected = process_scope_image(content, 1, "image-1")
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}
    }
    environment.update(
        PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONIOENCODING="utf-8",
    )
    result = subprocess.run(  # noqa: S603 - fixed worker harness; synthetic bytes on stdin.
        [sys.executable, "-c", ISOLATED_WORKER, *arguments],
        input=content,
        capture_output=True,
        check=False,
        env=environment,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert result.stderr == b""
    assert result.stdout == expected
