from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
changed: list[str] = []


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    rel = path.relative_to(ROOT).as_posix()
    if rel not in changed:
        changed.append(rel)


def replace(path_str: str, replacements: list[tuple[str, str]]) -> None:
    path = ROOT / path_str
    if not path.exists():
        return
    text = _read(path)
    new = text
    for old, replacement in replacements:
        new = new.replace(old, replacement)
    if new != text:
        _write(path, new)


def replace_upper(path_str: str) -> None:
    replace(path_str, [("QUANTIFIRE", "CLASSIFIRE")])


def replace_upper_lower(path_str: str) -> None:
    replace(path_str, [("QUANTIFIRE", "CLASSIFIRE"), ("quantifire", "classifire")])


# ---------------------------------------------------------------------------
# Active operator/deployment identity.
# ---------------------------------------------------------------------------
replace(".env.example", [("QUANTIFIRE_", "CLASSIFIRE_"), ("quantifire.db", "classifire.db")])
replace_upper_lower("install.ps1")
replace_upper_lower("install.sh")
replace("scripts/publish-github.ps1", [("quantifire", "classifire")])
replace("scripts/publish-github.sh", [("quantifire", "classifire")])
replace_upper("NOTICE.md")
replace_upper("PROPRIETARY.md")
replace_upper_lower("SKILL.md")

# README is active product documentation, but the imported v2.13 source filenames
# remain historical QUANTIFIRE provenance and must not be renamed.
replace_upper_lower("README.md")
replace(
    "README.md",
    [
        ("CLASSIFIRE_14_Pricing_Library_v2.13.csv", "QUANTIFIRE_14_Pricing_Library_v2.13.csv"),
        ("CLASSIFIRE_17_Technical_System_Variants_v2.13.jsonl", "QUANTIFIRE_17_Technical_System_Variants_v2.13.jsonl"),
    ],
)
readme = ROOT / "README.md"
if readme.exists():
    text = _read(readme)
    lines = [
        line
        for line in text.splitlines()
        if not (line.strip().startswith("![CLASSIFIRE estimating system]") and "logo" in line.lower())
    ]
    new = "\n".join(lines).rstrip() + "\n"
    if new != text:
        _write(readme, new)

# ---------------------------------------------------------------------------
# Active application identity.
# ---------------------------------------------------------------------------
init_path = ROOT / "src/classifire/__init__.py"
if init_path.exists():
    text = _read(init_path)
    version_line = next((line for line in text.splitlines() if line.startswith("__version__")), '__version__ = "0.1.0"')
    new = (
        '"""CLASSIFIRE production application."""\n\n'
        f"{version_line}\n"
        'PRODUCT_NAME = "CLASSIFIRE"\n'
        'ATTRIBUTION = "CLASSIFIRE is an estimating system produced and developed by Ceasefire PFP."\n'
        'LEGACY_PRODUCT_NAME = "QUANTIFIRE"\n'
        'LEGACY_BASELINE_VERSION = "v2.13"\n'
    )
    if new != text:
        _write(init_path, new)

active_upper_files = [
    "src/classifire/api/commercial.py",
    "src/classifire/api/guarded_technical.py",
    "src/classifire/api/human_release.py",
    "src/classifire/api/physical_model.py",
    "src/classifire/api/productivity.py",
    "src/classifire/api/quantity_labour.py",
    "src/classifire/api/release_control.py",
    "src/classifire/api/repair_strategy.py",
    "src/classifire/api/router.py",
    "src/classifire/api/workflow.py",
    "src/classifire/api/workflow_actions.py",
    "src/classifire/audit.py",
    "src/classifire/main.py",
    "src/classifire/mission_control/client.py",
    "src/classifire/ui.py",
]
for path in active_upper_files:
    replace_upper(path)

# Preserve the source-lineage meaning in newly-created audit descriptions.
replace(
    "src/classifire/api/commercial.py",
    [
        (
            "CLASSIFIRE v2.13 controlled Package 14 commercial hierarchy",
            "CLASSIFIRE controlled Package 14 commercial hierarchy (QUANTIFIRE v2.13 lineage)",
        )
    ],
)
replace(
    "src/classifire/api/physical_model.py",
    [
        (
            "Evidence registered for CLASSIFIRE v2.13 physical-model workflow",
            "Evidence registered for CLASSIFIRE physical-model workflow (QUANTIFIRE v2.13 lineage)",
        )
    ],
)

# CLI is active identity. Restore only the two controlled source filenames after
# the product-facing replacement.
replace_upper("src/classifire/cli.py")
replace(
    "src/classifire/cli.py",
    [
        ("CLASSIFIRE_14_Pricing_Library_v2.13.csv", "QUANTIFIRE_14_Pricing_Library_v2.13.csv"),
        ("CLASSIFIRE_17_Technical_System_Variants_v2.13.jsonl", "QUANTIFIRE_17_Technical_System_Variants_v2.13.jsonl"),
        (
            'checks.append(("Approved logo", str(root / "assets/brand/quantifire-logo-master.png"), "PASS" if (root / "assets/brand/quantifire-logo-master.png").exists() else "FAIL"))',
            'logo = root / "assets/brand/classifire-logo-master.png"\n    checks.append(("Approved CLASSIFIRE logo", str(logo), "PASS" if logo.exists() else "WARN"))',
        ),
    ],
)

# New installs/administrators use CLASSIFIRE identity. The controlled imported
# source-corpus description remains QUANTIFIRE v2.13 provenance.
replace_upper("src/classifire/importers/seed.py")
replace(
    "src/classifire/importers/seed.py",
    [
        (
            "Supplied CLASSIFIRE v2.13 commercial source corpus",
            "Supplied QUANTIFIRE v2.13 commercial source corpus",
        )
    ],
)

# Mission Control/OpenClaw-facing development identifiers are current runtime
# identities, so qf/QF prefixes become cf/CF. Existing historic MC records are not
# rewritten; bootstrap will create current CLASSIFIRE records.
replace(
    "src/classifire/mission_control/bootstrap.py",
    [("QUANTIFIRE", "CLASSIFIRE"), ("qf-", "cf-"), ("QF-", "CF-")],
)

# ---------------------------------------------------------------------------
# Active output identity. Protocol/schema/engine IDs in services are deliberately
# untouched. Until a genuine CLASSIFIRE PNG is supplied, render text branding
# instead of displaying the old QUANTIFIRE artwork.
# ---------------------------------------------------------------------------
replace_upper("src/classifire/outputs/common.py")
common = ROOT / "src/classifire/outputs/common.py"
if common.exists():
    text = _read(common)
    start = text.find("def logo_path()")
    if start != -1:
        replacement = '''def logo_path() -> Path | None:\n    package_root = Path(__file__).resolve().parents[3]\n    candidates = [\n        Path(__file__).resolve().parents[1] / "static" / "brand" / "classifire-logo-master.png",\n        package_root / "assets" / "brand" / "classifire-logo-master.png",\n        Path.cwd() / "assets" / "brand" / "classifire-logo-master.png",\n    ]\n    for candidate in candidates:\n        if candidate.exists():\n            return candidate\n    return None\n'''
        new = text[:start].rstrip() + "\n\n\n" + replacement
        if new != text:
            _write(common, new)

replace_upper("src/classifire/outputs/xlsx.py")
replace(
    "src/classifire/outputs/xlsx.py",
    [
        (
            'def _insert_brand(sheet: xlsxwriter.worksheet.Worksheet) -> None:\n    sheet.insert_image("A1", str(logo_path()), {"x_scale": 0.16, "y_scale": 0.16, "object_position": 1})',
            'def _insert_brand(sheet: xlsxwriter.worksheet.Worksheet) -> None:\n    logo = logo_path()\n    if logo is not None:\n        sheet.insert_image("A1", str(logo), {"x_scale": 0.16, "y_scale": 0.16, "object_position": 1})\n    else:\n        sheet.write("A1", "CLASSIFIRE")',
        )
    ],
)

replace_upper("src/classifire/outputs/pdf.py")
replace(
    "src/classifire/outputs/pdf.py",
    [
        (
            '    logo = Image(str(logo_path()))\n    logo.drawHeight = 35 * mm\n    logo.drawWidth = 35 * mm * (logo.imageWidth / logo.imageHeight)\n    story.append(Table([[logo]], colWidths=[170 * mm], style=TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")])) )',
            '    logo_file = logo_path()\n    if logo_file is not None:\n        logo = Image(str(logo_file))\n        logo.drawHeight = 35 * mm\n        logo.drawWidth = 35 * mm * (logo.imageWidth / logo.imageHeight)\n        story.append(Table([[logo]], colWidths=[170 * mm], style=TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")])) )\n    else:\n        story.append(Paragraph("CLASSIFIRE", styles["title"]))',
        )
    ],
)

# ---------------------------------------------------------------------------
# Active web UI. All old logo files remain on disk as legacy assets, but active
# templates stop rendering them until a real CLASSIFIRE logo is supplied.
# ---------------------------------------------------------------------------
template_dir = ROOT / "src/classifire/templates"
if template_dir.exists():
    for path in sorted(template_dir.glob("*.html")):
        text = _read(path)
        new = text.replace("QUANTIFIRE", "CLASSIFIRE")
        if new != text:
            _write(path, new)

replace(
    "src/classifire/templates/base.html",
    [
        ('  <link rel="icon" type="image/png" href="/brand/generated/quantifire-logo-favicon.png">\n', ""),
        (
            '      <img src="/brand/generated/quantifire-logo-small.png" alt="CLASSIFIRE estimating system">',
            '      <span class="brand-text">CLASSIFIRE</span>',
        ),
    ],
)
replace(
    "src/classifire/templates/login.html",
    [
        (
            '    <img class="login-logo" src="/brand/generated/quantifire-logo-medium.png" alt="CLASSIFIRE estimating system">',
            '    <div class="login-brand">CLASSIFIRE</div>',
        )
    ],
)
css = ROOT / "src/classifire/static/css/app.css"
if css.exists():
    text = _read(css)
    extra = '.brand-text{display:block;font-size:30px;font-weight:900;letter-spacing:.08em;color:#fff;padding:22px 4px}.login-brand{text-align:center;font-size:34px;font-weight:900;letter-spacing:.08em;color:#111827;padding:18px 0 4px}'
    if ".brand-text{" not in text:
        _write(css, text.rstrip() + extra + "\n")

# ---------------------------------------------------------------------------
# Branding audit: CLASSIFIRE assets are the current approved names. Old
# QUANTIFIRE logo files are allowed to remain only as legacy review items.
# ---------------------------------------------------------------------------
branding = ROOT / "scripts/branding_audit.py"
if branding.exists():
    text = _read(branding)
    text = text.replace(
        '''APPROVED_LOGO_NAMES = {\n    "quantifire-logo-master.png",\n    "quantifire-logo-small.png",\n    "quantifire-logo-medium.png",\n    "quantifire-logo-large.png",\n    "quantifire-logo-favicon.png",\n}\n''',
        '''APPROVED_LOGO_NAMES = {\n    "classifire-logo-master.png",\n    "classifire-logo-small.png",\n    "classifire-logo-medium.png",\n    "classifire-logo-large.png",\n    "classifire-logo-favicon.png",\n}\nLEGACY_QUANTIFIRE_LOGO_NAMES = {\n    "quantifire-logo-master.png",\n    "quantifire-logo-small.png",\n    "quantifire-logo-medium.png",\n    "quantifire-logo-large.png",\n    "quantifire-logo-favicon.png",\n}\n''',
    )
    text = text.replace(
        '        if path.suffix.lower() in IMAGE_SUFFIXES and path.name not in APPROVED_LOGO_NAMES:\n            findings.append({"severity": "error", "path": rel.as_posix(), "finding": "Unapproved image asset", "sha256": sha256(path)})',
        '        if path.suffix.lower() in IMAGE_SUFFIXES and path.name in LEGACY_QUANTIFIRE_LOGO_NAMES:\n            findings.append({"severity": "review", "path": rel.as_posix(), "finding": "Legacy QUANTIFIRE logo retained; not approved for active CLASSIFIRE rendering", "sha256": sha256(path)})\n        elif path.suffix.lower() in IMAGE_SUFFIXES and path.name not in APPROVED_LOGO_NAMES:\n            findings.append({"severity": "error", "path": rel.as_posix(), "finding": "Unapproved image asset", "sha256": sha256(path)})',
    )
    if text != _read(branding):
        _write(branding, text)

print("CLASSIFIRE active-brand cutover complete.")
print(f"Changed {len(changed)} file(s):")
for item in changed:
    print(f"  - {item}")
print()
print("Preserved intentionally as QUANTIFIRE v2.13 lineage:")
for item in [
    "migration column: quantifire_version",
    "SystemRequiredComponent UUID namespace: quantifire:v2.13",
    "QUANTIFIRE-PhysicalModelLock-v2.13",
    "QUANTIFIRE-RepairStrategyLock-v2.13",
    "QUANTIFIRE-VALIDATED-ESTIMATE-SNAPSHOT-v2.13",
    "QUANTIFIRE-ESTIMATE-CERTIFICATE-v2.13",
    "QUANTIFIRE engine/validator IDs embedded in retained v2.13 records",
    "controlled QUANTIFIRE v2.13 source filenames and corpus descriptions",
]:
    print(f"  - {item}")
