from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

APPROVED_LOGO_NAMES = {
    "classifire-logo-master.png",
    "classifire-logo-small.png",
    "classifire-logo-medium.png",
    "classifire-logo-large.png",
    "classifire-logo-favicon.png",
}
LEGACY_QUANTIFIRE_LOGO_NAMES = {
    "quantifire-logo-master.png",
    "quantifire-logo-small.png",
    "quantifire-logo-medium.png",
    "quantifire-logo-large.png",
    "quantifire-logo-favicon.png",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico"}
EXCLUDED_PARTS = {".git", ".venv", "node_modules", "knowledge", "data"}
LEGACY_TERMS = ("PFEOS", "Ceasefire Logo", "placeholder logo")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    findings: list[dict[str, str]] = []

    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root)
        if any(part in EXCLUDED_PARTS for part in rel.parts):
            continue
        if path.suffix.lower() in IMAGE_SUFFIXES and path.name in LEGACY_QUANTIFIRE_LOGO_NAMES:
            findings.append({"severity": "review", "path": rel.as_posix(), "finding": "Legacy QUANTIFIRE logo retained; not approved for active CLASSIFIRE rendering", "sha256": sha256(path)})
        elif path.suffix.lower() in IMAGE_SUFFIXES and path.name not in APPROVED_LOGO_NAMES:
            findings.append({"severity": "error", "path": rel.as_posix(), "finding": "Unapproved image asset", "sha256": sha256(path)})
        if rel.as_posix() in {"scripts/branding_audit.py", "docs/reports/branding-audit-current.json"}:
            continue
        if path.suffix.lower() in {".py", ".md", ".txt", ".html", ".css", ".js", ".json", ".yaml", ".yml", ".toml"}:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for term in LEGACY_TERMS:
                if term.lower() in text.lower():
                    findings.append({"severity": "review", "path": rel.as_posix(), "finding": f"Legacy term: {term}"})

    report = {"root": str(root), "approved_logo_names": sorted(APPROVED_LOGO_NAMES), "findings": findings}
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    for finding in findings:
        print(f"{finding['severity'].upper()}: {finding['path']}: {finding['finding']}")
    errors = [f for f in findings if f["severity"] == "error"]
    print(f"Branding audit: {len(errors)} error(s), {len(findings) - len(errors)} review item(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
