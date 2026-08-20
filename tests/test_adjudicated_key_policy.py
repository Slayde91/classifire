from __future__ import annotations

import base64
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from classifire.config import Settings
from classifire.services.adjudicated_key_policy import (
    AdjudicatedKeyPolicyError,
    resolve_adjudicated_public_key,
)


def _public_key() -> str:
    key = ec.generate_private_key(ec.SECP256R1()).public_key()
    encoded = key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return base64.urlsafe_b64encode(encoded).rstrip(b"=").decode("ascii")


def test_resolves_only_an_explicit_issuer_key_binding() -> None:
    public_key = _public_key()
    assert (
        resolve_adjudicated_public_key(
            enabled=True,
            public_keys={"governance-p256-01": public_key},
            issuer_key_ids={"classifire-governance": ["governance-p256-01"]},
            issuer="classifire-governance",
            key_id="governance-p256-01",
        )
        == public_key
    )


@pytest.mark.parametrize(
    "enabled,public_keys,issuer_key_ids,issuer,key_id,code",
    [
        (
            False,
            {},
            {},
            "classifire-governance",
            "governance-p256-01",
            "ADJUDICATED_SUBMISSION_DISABLED",
        ),
        (
            True,
            {},
            {},
            "classifire-governance",
            "governance-p256-01",
            "ADMISSION_ISSUER_KEY_UNBOUND",
        ),
        (
            True,
            {},
            {"classifire-governance": ["governance-p256-02"]},
            "classifire-governance",
            "governance-p256-01",
            "ADMISSION_ISSUER_KEY_UNBOUND",
        ),
        (
            True,
            {"governance-p256-01": "not-a-key"},
            {"classifire-governance": ["governance-p256-01"]},
            "classifire-governance",
            "governance-p256-01",
            "ADMISSION_PUBLIC_KEY_INVALID",
        ),
    ],
)
def test_key_policy_fails_closed(
    enabled: bool,
    public_keys: dict[str, str],
    issuer_key_ids: dict[str, list[str]],
    issuer: str,
    key_id: str,
    code: str,
) -> None:
    with pytest.raises(AdjudicatedKeyPolicyError) as rejected:
        resolve_adjudicated_public_key(
            enabled=enabled,
            public_keys=public_keys,
            issuer_key_ids=issuer_key_ids,
            issuer=issuer,
            key_id=key_id,
        )
    assert rejected.value.code == code


def test_settings_parse_public_key_policy_from_json_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    public_key = _public_key()
    monkeypatch.setenv(
        "CLASSIFIRE_ADJUDICATED_ADMISSION_PUBLIC_KEYS",
        json.dumps({"governance-p256-01": public_key}),
    )
    monkeypatch.setenv(
        "CLASSIFIRE_ADJUDICATED_ADMISSION_ISSUER_KEY_IDS",
        json.dumps({"classifire-governance": ["governance-p256-01"]}),
    )
    settings = Settings(_env_file=None)
    assert settings.adjudicated_admission_public_keys == {"governance-p256-01": public_key}
    assert settings.adjudicated_admission_issuer_key_ids == {
        "classifire-governance": ["governance-p256-01"]
    }
