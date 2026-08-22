from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "mobile"
    / "classifire-admission-signer"
    / "app"
    / "src"
    / "main"
    / "java"
    / "au"
    / "com"
    / "classifire"
    / "admissionsigner"
)


def test_secure_hardware_check_is_centralised_and_fail_closed() -> None:
    helper = (SOURCE / "KeystoreSecurity.java").read_text(encoding="utf-8")

    assert "Build.VERSION.SDK_INT >= Build.VERSION_CODES.S" in helper
    assert "KeyProperties.SECURITY_LEVEL_TRUSTED_ENVIRONMENT" in helper
    assert "KeyProperties.SECURITY_LEVEL_STRONGBOX" in helper
    assert "return false;" in helper
    assert '@SuppressWarnings("deprecation")' in helper

    for name in ("MainActivity.java", "OfflineSignerActivity.java"):
        source = (SOURCE / name).read_text(encoding="utf-8")
        assert "KeystoreSecurity.isHardwareBacked(" in source
        assert "isInsideSecureHardware()" not in source
