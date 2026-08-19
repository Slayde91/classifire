from __future__ import annotations

from importlib import import_module


def test_classifire_runtime_package_and_entry_modules_import() -> None:
    assert import_module("classifire").__name__ == "classifire"
    assert import_module("classifire.cli").app is not None
    assert import_module("classifire.asgi").app is not None
