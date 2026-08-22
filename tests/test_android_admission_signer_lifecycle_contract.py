from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVITY = (
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
    / "OfflineSignerActivity.java"
)


def test_signer_clears_stale_review_and_serialises_signing_attempts() -> None:
    source = ACTIVITY.read_text(encoding="utf-8")

    clear_pending = source.split("private void clearPending()", maxsplit=1)[1]
    assert "pendingManifest = null;" in clear_pending
    assert "pendingSignedJson = null;" in clear_pending
    assert "signButton.setEnabled(false);" in clear_pending
    assert "status.setText(R.string.no_manifest_loaded);" in clear_pending

    begin_signature = source.split("private void beginSignature()", maxsplit=1)[1].split(
        "private BiometricPrompt.AuthenticationCallback", maxsplit=1
    )[0]
    assert "pendingSignedJson = null;" in begin_signature
    assert "signButton.setEnabled(false);" in begin_signature


def test_stale_biometric_callbacks_cannot_overwrite_a_new_manifest() -> None:
    source = ACTIVITY.read_text(encoding="utf-8")
    callback = source.split("private BiometricPrompt.AuthenticationCallback", maxsplit=1)[1].split(
        "private void saveSignedManifest", maxsplit=1
    )[0]

    assert callback.count("if (pendingManifest != manifest) return;") == 2
    assert callback.count("restoreSignableManifest(manifest);") == 2
    assert "if (!Instant.now().isBefore(manifest.expiresAt()))" in source
