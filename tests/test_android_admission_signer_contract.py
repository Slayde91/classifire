from __future__ import annotations

import json
from pathlib import Path

from classifire.services.adjudicated_admission import (
    ADMISSION_MANIFEST_SCHEMA,
    ADMISSION_PURPOSE,
    ADMISSION_SIGNATURE_ALGORITHM,
    admission_identity,
    admission_signing_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
SIGNER = ROOT / "mobile" / "classifire-admission-signer"
RESOURCES = SIGNER / "app" / "src" / "test" / "resources"
ANDROID = "{http://schemas.android.com/apk/res/android}"


def test_android_and_backend_share_exact_canonical_signing_vector() -> None:
    manifest_bytes = (RESOURCES / "admission-manifest-v2-input.json").read_bytes()
    expected = (RESOURCES / "admission-manifest-v2-signing-canonical.json").read_bytes().rstrip(
        b"\r\n"
    )
    manifest = json.loads(manifest_bytes)

    assert manifest["schema"] == ADMISSION_MANIFEST_SCHEMA
    assert manifest["purpose"] == ADMISSION_PURPOSE
    assert manifest["signature_algorithm"] == ADMISSION_SIGNATURE_ALGORITHM
    assert admission_identity(manifest) == ("classifire-governance", "governance-p256-01")
    assert admission_signing_bytes(manifest_bytes) == expected


def test_android_manifest_is_offline_and_fail_closed() -> None:
    manifest_path = SIGNER / "app" / "src" / "main" / "AndroidManifest.xml"
    manifest = manifest_path.read_text(encoding="utf-8")

    assert manifest.count("<uses-permission") == 1
    assert 'android:name="android.permission.USE_BIOMETRIC"' in manifest
    assert "android.permission.INTERNET" not in manifest
    assert 'android:allowBackup="false"' in manifest
    assert 'android:fullBackupContent="false"' in manifest
    assert 'android:usesCleartextTraffic="false"' in manifest
    assert 'android:dataExtractionRules="@xml/data_extraction_rules"' in manifest
    assert 'android:name=".MainActivity"' in manifest
    assert 'android:name=".OfflineSignerActivity"' in manifest
    assert manifest.count('android:exported="true"') == 1
    assert manifest.count('android:exported="false"') == 1
    assert "android.intent.category.LAUNCHER" in manifest


def test_android_signer_source_has_no_network_or_canonical_write_client() -> None:
    source_root = SIGNER / "app" / "src" / "main" / "java"
    source = "\n".join(path.read_text(encoding="utf-8") for path in source_root.rglob("*.java"))

    assert "Intent.EXTRA_LOCAL_ONLY" in source
    assert "BIOMETRIC_STRONG" in source
    assert source.count("FLAG_SECURE") == 2
    for forbidden in (
        "java.net.",
        "okhttp",
        "retrofit",
        "physical_model_admissions",
        "physical_model_submission_receipts",
        "canonical submission",
        "PhysicalModelLock",
    ):
        assert forbidden not in source
