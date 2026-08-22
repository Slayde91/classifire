from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIGNER = ROOT / "mobile" / "classifire-admission-signer"


def test_android_signer_ui_text_is_resource_backed() -> None:
    source_root = SIGNER / "app" / "src" / "main" / "java"
    source = "\n".join(path.read_text(encoding="utf-8") for path in source_root.rglob("*.java"))
    hard_coded_ui_call = re.compile(
        r"\.(?:setText|setHint|setTitle|setSubtitle|setMessage|setPositiveButton|"
        r"setNegativeButton)\(\s*\""
    )

    assert hard_coded_ui_call.search(source) is None

    strings = (
        SIGNER / "app" / "src" / "main" / "res" / "values" / "strings.xml"
    ).read_text(encoding="utf-8")
    for name in (
        "app_name",
        "offline_signer_notice",
        "production_key_confirmation",
        "confirm_admission_message",
        "signed_manifest_exported",
    ):
        assert f'name="{name}"' in strings

    manifest = (SIGNER / "app" / "src" / "main" / "AndroidManifest.xml").read_text(
        encoding="utf-8"
    )
    assert 'android:label="@string/app_name"' in manifest
