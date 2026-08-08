from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]

SIZES = {
    "favicon": 64,
    "small": 360,
    "medium": 720,
    "large": 1440,
}


def _save_resized(source: Image.Image, path: Path, max_width: int) -> None:
    image = source.copy()
    width, height = image.size
    if width > max_width:
        ratio = max_width / width
        image = image.resize((max_width, max(1, round(height * ratio))), Image.Resampling.LANCZOS)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the approved CLASSIFIRE logo assets.")
    parser.add_argument("source", type=Path, help="Path to the approved CLASSIFIRE master PNG")
    args = parser.parse_args()

    source_path = args.source.expanduser().resolve()
    if not source_path.exists():
        raise SystemExit(f"Logo source not found: {source_path}")

    with Image.open(source_path) as raw:
        image = raw.convert("RGBA")

        repo_brand = ROOT / "assets" / "brand"
        package_brand = ROOT / "src" / "classifire" / "static" / "brand"

        master_targets = [
            repo_brand / "classifire-logo-master.png",
            package_brand / "classifire-logo-master.png",
        ]
        for target in master_targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            image.save(target, format="PNG", optimize=True)

        for label, width in SIZES.items():
            for base in (repo_brand / "generated", package_brand / "generated"):
                _save_resized(image, base / f"classifire-logo-{label}.png", width)

    print("CLASSIFIRE logo installed.")
    print(f"Master source: {source_path}")
    print("Created:")
    print("  assets/brand/classifire-logo-master.png")
    print("  assets/brand/generated/classifire-logo-{favicon,small,medium,large}.png")
    print("  src/classifire/static/brand/classifire-logo-master.png")
    print("  src/classifire/static/brand/generated/classifire-logo-{favicon,small,medium,large}.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
