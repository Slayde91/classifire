from __future__ import annotations

import hashlib
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIGNER = ROOT / "mobile" / "classifire-admission-signer"


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert data[12:16] == b"IHDR"
    return struct.unpack(">II", data[16:24])


def test_launcher_icon_uses_the_approved_classifire_logo_without_mutation() -> None:
    master = ROOT / "assets" / "brand" / "classifire-logo-master.png"
    assert hashlib.sha256(master.read_bytes()).hexdigest() == (
        "dc527f714afc8960daf8135fdf850899e7bbbeab7c60156b72e0aacb46831acf"
    )

    manifest = (SIGNER / "app" / "src" / "main" / "AndroidManifest.xml").read_text(
        encoding="utf-8"
    )
    assert 'android:icon="@mipmap/ic_launcher"' in manifest
    assert 'android:roundIcon="@mipmap/ic_launcher_round"' in manifest

    res = SIGNER / "app" / "src" / "main" / "res"
    assert _png_size(res / "drawable-nodpi" / "ic_launcher_foreground.png") == (1024, 1024)
    colors = (res / "values" / "colors.xml").read_text(encoding="utf-8")
    assert '<color name="launcher_icon_background">#FFFFFFFF</color>' in colors
    adaptive = (res / "mipmap-anydpi" / "ic_launcher.xml").read_text(
        encoding="utf-8"
    )
    assert '@color/launcher_icon_background' in adaptive
    assert '@drawable/ic_launcher_foreground' in adaptive
    assert '<monochrome android:drawable="@drawable/ic_launcher_foreground" />' in adaptive
