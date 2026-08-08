from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _rewrite(path: Path, replacements: list[tuple[str, str]]) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8-sig")
    new = text
    for old, replacement in replacements:
        new = new.replace(old, replacement)
    if new == text:
        return False
    path.write_text(new, encoding="utf-8")
    return True


def main() -> int:
    master = ROOT / "assets" / "brand" / "classifire-logo-master.png"
    packaged = ROOT / "src" / "classifire" / "static" / "brand" / "classifire-logo-master.png"
    favicon = ROOT / "src" / "classifire" / "static" / "brand" / "generated" / "classifire-logo-favicon.png"
    small = ROOT / "src" / "classifire" / "static" / "brand" / "generated" / "classifire-logo-small.png"
    medium = ROOT / "src" / "classifire" / "static" / "brand" / "generated" / "classifire-logo-medium.png"

    missing = [str(path) for path in (master, packaged, favicon, small, medium) if not path.exists()]
    if missing:
        raise SystemExit(
            "CLASSIFIRE logo assets are not installed. Run scripts/install_classifire_logo.py first. Missing: "
            + ", ".join(missing)
        )

    changed: list[str] = []

    base = ROOT / "src" / "classifire" / "templates" / "base.html"
    if _rewrite(
        base,
        [
            (
                '<title>{% block title %}CLASSIFIRE{% endblock %}</title>\n',
                '<title>{% block title %}CLASSIFIRE{% endblock %}</title>\n  <link rel="icon" type="image/png" href="/brand/generated/classifire-logo-favicon.png">\n',
            ),
            (
                '<span class="brand-text">CLASSIFIRE</span>',
                '<img src="/brand/generated/classifire-logo-small.png" alt="CLASSIFIRE estimating system">',
            ),
            (
                '/brand/generated/quantifire-logo-small.png',
                '/brand/generated/classifire-logo-small.png',
            ),
            ('alt="QUANTIFIRE estimating system"', 'alt="CLASSIFIRE estimating system"'),
        ],
    ):
        changed.append(base.relative_to(ROOT).as_posix())

    login = ROOT / "src" / "classifire" / "templates" / "login.html"
    if _rewrite(
        login,
        [
            (
                '<div class="login-brand">CLASSIFIRE</div>',
                '<img class="login-logo" src="/brand/generated/classifire-logo-medium.png" alt="CLASSIFIRE estimating system">',
            ),
            (
                '/brand/generated/quantifire-logo-medium.png',
                '/brand/generated/classifire-logo-medium.png',
            ),
            ('alt="QUANTIFIRE estimating system"', 'alt="CLASSIFIRE estimating system"'),
        ],
    ):
        changed.append(login.relative_to(ROOT).as_posix())

    readme = ROOT / "README.md"
    if readme.exists():
        text = readme.read_text(encoding="utf-8-sig")
        image_line = "![CLASSIFIRE estimating system](assets/brand/generated/classifire-logo-medium.png)"
        if image_line not in text:
            lines = text.splitlines()
            insert_at = 1 if lines and lines[0].startswith("# ") else 0
            lines[insert_at:insert_at] = ["", image_line]
            readme.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
            changed.append("README.md")

    print("CLASSIFIRE active logo references enabled.")
    if changed:
        for item in changed:
            print(f"  {item}")
    else:
        print("  No text changes were required; logo references were already active.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
