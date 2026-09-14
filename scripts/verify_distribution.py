"""Verify that a built wheel retains every application module and runtime resource."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile


class DistributionError(ValueError):
    """The wheel does not match the reviewed application source."""


def verify_distribution(wheel: Path, repository: Path) -> dict[str, str | int]:
    package = repository / "src" / "classifire"
    if not package.is_dir() or package.is_symlink():
        raise DistributionError("Application source directory is missing or linked")
    expected = {}
    for path in package.rglob("*"):
        if path.is_symlink() or not path.resolve().is_relative_to(package.resolve()):
            raise DistributionError("Linked application resource refused")
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_file():
            expected[path.relative_to(package.parent).as_posix()] = path
    if not expected:
        raise DistributionError("Application source is empty")
    with ZipFile(wheel) as archive:
        names = [info.filename for info in archive.infolist()]
        if len(names) != len(set(names)):
            raise DistributionError("Duplicate archive member")
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name:
                raise DistributionError("Invalid archive member path")
        packaged = {
            info.filename: info
            for info in archive.infolist()
            if info.filename.startswith("classifire/") and not info.is_dir()
        }
        if set(packaged) != set(expected):
            missing = sorted(set(expected) - set(packaged))
            extra = sorted(set(packaged) - set(expected))
            raise DistributionError(f"Package members differ: missing={missing}; extra={extra}")
        for name, source in expected.items():
            info = packaged[name]
            if info.file_size != source.stat().st_size or archive.read(info) != source.read_bytes():
                raise DistributionError(f"Package bytes differ: {name}")
    return {
        "package_files": len(expected),
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel_directory", type=Path)
    args = parser.parse_args()
    wheels = list(args.wheel_directory.glob("*.whl"))
    if len(wheels) != 1:
        parser.error("Expected exactly one built wheel")
    try:
        result = verify_distribution(wheels[0], Path(__file__).resolve().parents[1])
    except (DistributionError, BadZipFile, OSError) as exc:
        print(f"Distribution verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
