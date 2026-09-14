from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "distribution_check", ROOT / "scripts/verify_distribution.py"
)
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


@pytest.fixture
def distribution(tmp_path):
    content = {
        "classifire/__init__.py": b'"""Synthetic package."""\n',
        "classifire/templates/login.html": b"<main>Sign in</main>",
        "classifire/templates/partials/navigation.html": b"<nav>Scope</nav>",
        "classifire/static/workspace_chat.css": b".chat { display: flex; }",
        "classifire/static/workspace_chat.js": b'console.log("synthetic");',
        "classifire/static/brand/classifire-logo.png": b"synthetic-binary-placeholder",
    }
    for name, blob in content.items():
        path = tmp_path / "src" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    return tmp_path, content


def wheel(root, content):
    path = root / "synthetic.whl"
    with ZipFile(path, "w") as archive:
        for name, blob in content.items():
            archive.writestr(name, blob)
    return path


def test_distribution_preserves_all_code_and_nested_ui_bytes(distribution):
    root, content = distribution
    result = CHECK.verify_distribution(wheel(root, content), root)
    assert result["package_files"] == len(content)
    assert len(result["wheel_sha256"]) == 64


@pytest.mark.parametrize(
    "name",
    [
        "classifire/templates/login.html",
        "classifire/templates/partials/navigation.html",
        "classifire/static/workspace_chat.css",
        "classifire/static/workspace_chat.js",
        "classifire/static/brand/classifire-logo.png",
    ],
)
def test_distribution_refuses_missing_ui_resource(distribution, name):
    root, content = distribution
    del content[name]
    with pytest.raises(CHECK.DistributionError, match="Package members differ"):
        CHECK.verify_distribution(wheel(root, content), root)


def test_distribution_refuses_changed_code_bytes(distribution):
    root, content = distribution
    content["classifire/__init__.py"] = b'"""Unexpected change."""\n'
    with pytest.raises(CHECK.DistributionError, match="Package bytes differ"):
        CHECK.verify_distribution(wheel(root, content), root)


@pytest.mark.parametrize("name", ["classifire/unexpected.json", "../outside.txt"])
def test_distribution_refuses_unexpected_or_unsafe_members(distribution, name):
    root, content = distribution
    content[name] = b"unexpected"
    with pytest.raises(CHECK.DistributionError):
        CHECK.verify_distribution(wheel(root, content), root)


def test_distribution_refuses_duplicate_member(distribution):
    root, content = distribution
    path = wheel(root, content)
    with ZipFile(path, "a") as archive, pytest.warns(UserWarning, match="Duplicate name"):
        archive.writestr("classifire/__init__.py", content["classifire/__init__.py"])
    with pytest.raises(CHECK.DistributionError, match="Duplicate archive member"):
        CHECK.verify_distribution(path, root)


def test_package_declaration_covers_every_runtime_asset():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package = ROOT / "src/classifire"
    patterns = config["tool"]["setuptools"]["package-data"]["classifire"]
    declared = {path for pattern in patterns for path in package.glob(pattern) if path.is_file()}
    required = {
        path
        for directory in ("static", "templates")
        for path in (package / directory).rglob("*")
        if path.is_file()
    }
    assert required
    assert required <= declared
