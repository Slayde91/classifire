from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIGNER = ROOT / "mobile" / "classifire-admission-signer"
ACTIVITY = (
    SIGNER
    / "app"
    / "src"
    / "main"
    / "java"
    / "au"
    / "com"
    / "classifire"
    / "admissionsigner"
    / "MainActivity.java"
)


def test_existing_key_public_proof_is_fail_closed_and_non_mutating() -> None:
    source = ACTIVITY.read_text(encoding="utf-8")
    recovery = source.split(
        "private void showExistingProductionKey", maxsplit=1
    )[1].split("private void beginProof", maxsplit=1)[0]

    assert "store.containsAlias(alias)" in recovery
    assert "KeystoreSecurity.isHardwareBacked(keyInfo)" in recovery
    assert "getSharedPreferences(" in recovery
    assert '"classifire_admission_signer"' in recovery
    assert "MODE_PRIVATE" in recovery
    assert '"production_issuer_" + keyId' in recovery
    assert '"production_custodian_" + keyId' in recovery
    assert '"production_fingerprint_" + keyId' in recovery
    assert "publicKey.getParams().getCurve().getField().getFieldSize() != 256" in recovery
    assert "P256_ORDER.equals(publicKey.getParams().getOrder())" in recovery
    assert "fingerprint.equals(storedFingerprint)" in recovery
    assert "R.string.production_key_recovered" in recovery
    assert "generateKeyPair" not in recovery
    assert "deleteEntry" not in recovery
    assert "initSign" not in recovery


def test_existing_key_public_proof_has_explicit_ui_resources() -> None:
    strings = (
        SIGNER / "app" / "src" / "main" / "res" / "values" / "strings.xml"
    ).read_text(encoding="utf-8")

    assert 'name="show_existing_public_key_button"' in strings
    assert 'name="production_key_recovered"' in strings
    assert 'name="production_key_not_found"' in strings
