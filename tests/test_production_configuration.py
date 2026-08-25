from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from classifire.config import (
    RuntimeConfigurationError,
    RuntimeConfigurationFinding,
    Settings,
    require_runtime_configuration,
)


def _production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "env": "production",
        "database_url": "postgresql+psycopg://classifire@database.example/classifire",
        "secret_key": "C7h!g2Rz_9mK4vQ8pL3xT6nW1sY5dF0a",
        "session_https_only": True,
        "trusted_hosts": ["app.example.com"],
        "allowed_origins": ["https://app.example.com"],
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _finding_codes(settings: Settings) -> set[str]:
    return {finding.code for finding in settings.production_findings()}


def test_valid_production_configuration_has_no_findings() -> None:
    settings = _production_settings(
        trusted_hosts=["APP.EXAMPLE.COM"],
        allowed_origins=["https://app.example.com:8443"],
    )

    assert settings.production_findings() == ()
    assert settings.validate_production() == []
    assert require_runtime_configuration(settings) is None


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        (
            {"secret_key": "change-this-to-a-long-random-value"},
            "PRODUCTION_SECRET_KEY_WEAK",
        ),
        ({"secret_key": "too-short"}, "PRODUCTION_SECRET_KEY_WEAK"),
        ({"secret_key": "A" * 64}, "PRODUCTION_SECRET_KEY_WEAK"),
        ({"secret_key": "0123456789" * 4}, "PRODUCTION_SECRET_KEY_WEAK"),
        ({"session_https_only": False}, "PRODUCTION_SESSION_HTTPS_REQUIRED"),
        ({"database_url": "sqlite:///./private.db"}, "PRODUCTION_POSTGRESQL_REQUIRED"),
        ({"database_url": "mysql://database.example/classifire"}, "PRODUCTION_POSTGRESQL_REQUIRED"),
        (
            {"database_url": "postgresql://classifire@database.example/classifire"},
            "PRODUCTION_POSTGRESQL_REQUIRED",
        ),
        (
            {"database_url": ("postgresql+unknown://classifire@database.example/classifire")},
            "PRODUCTION_POSTGRESQL_REQUIRED",
        ),
        ({"database_url": "postgresql:not-a-url"}, "PRODUCTION_POSTGRESQL_REQUIRED"),
        ({"database_url": "postgresql://"}, "PRODUCTION_POSTGRESQL_REQUIRED"),
        (
            {"database_url": "postgresql://user:password@/classifire"},
            "PRODUCTION_POSTGRESQL_REQUIRED",
        ),
        (
            {"database_url": "postgresql://user:password@database.example"},
            "PRODUCTION_POSTGRESQL_REQUIRED",
        ),
        ({"trusted_hosts": []}, "PRODUCTION_TRUSTED_HOSTS_REQUIRED"),
        ({"trusted_hosts": ["*"]}, "PRODUCTION_TRUSTED_HOST_WILDCARD"),
        (
            {"trusted_hosts": ["https://app.example.com"]},
            "PRODUCTION_TRUSTED_HOST_INVALID",
        ),
        ({"trusted_hosts": ["app.example.com:443"]}, "PRODUCTION_TRUSTED_HOST_INVALID"),
        ({"trusted_hosts": ["::1"]}, "PRODUCTION_TRUSTED_HOST_INVALID"),
        ({"allowed_origins": []}, "PRODUCTION_ALLOWED_ORIGINS_REQUIRED"),
        ({"allowed_origins": ["*"]}, "PRODUCTION_ALLOWED_ORIGIN_WILDCARD"),
        (
            {"allowed_origins": ["http://app.example.com"]},
            "PRODUCTION_ALLOWED_ORIGIN_HTTPS_REQUIRED",
        ),
        (
            {"allowed_origins": ["https://app.example.com/"]},
            "PRODUCTION_ALLOWED_ORIGIN_INVALID",
        ),
        (
            {"allowed_origins": ["https://user:password@app.example.com"]},
            "PRODUCTION_ALLOWED_ORIGIN_INVALID",
        ),
        (
            {"allowed_origins": ["https://app.example.com?token=private"]},
            "PRODUCTION_ALLOWED_ORIGIN_INVALID",
        ),
        (
            {"allowed_origins": ["https://app.example.com:"]},
            "PRODUCTION_ALLOWED_ORIGIN_INVALID",
        ),
        (
            {"allowed_origins": ["HTTPS://APP.EXAMPLE.COM"]},
            "PRODUCTION_ALLOWED_ORIGIN_INVALID",
        ),
        (
            {"allowed_origins": ["https://app.example.com:443"]},
            "PRODUCTION_ALLOWED_ORIGIN_INVALID",
        ),
        (
            {"allowed_origins": ["https://app.example.com\\@other.example"]},
            "PRODUCTION_ALLOWED_ORIGIN_INVALID",
        ),
        (
            {"allowed_origins": ["https://other.example.com"]},
            "PRODUCTION_ALLOWED_ORIGIN_HOST_UNTRUSTED",
        ),
    ],
)
def test_unsafe_production_values_have_stable_finding_codes(
    overrides: dict[str, object],
    expected_code: str,
) -> None:
    settings = _production_settings(**overrides)

    assert expected_code in _finding_codes(settings)
    with pytest.raises(RuntimeConfigurationError) as rejected:
        require_runtime_configuration(settings)
    assert expected_code in {finding.code for finding in rejected.value.findings}


def test_findings_are_immutable_and_legacy_messages_match() -> None:
    settings = _production_settings(session_https_only=False)
    findings = settings.production_findings()

    assert isinstance(findings, tuple)
    assert settings.validate_production() == [finding.message for finding in findings]
    assert isinstance(findings[0], RuntimeConfigurationFinding)
    with pytest.raises(FrozenInstanceError):
        findings[0].code = "CHANGED"  # type: ignore[misc]


def test_configuration_errors_never_echo_private_values() -> None:
    private_secret = "private-secret-value-that-must-not-appear-123456789"  # noqa: S105
    private_database_url = "sqlite:///C:/private/customer.db?token=database-private-token"
    private_origin = "https://other.private.example/path?token=origin-private-token"
    settings = _production_settings(
        secret_key=private_secret,
        database_url=private_database_url,
        allowed_origins=[private_origin],
    )

    with pytest.raises(RuntimeConfigurationError) as rejected:
        require_runtime_configuration(settings)

    rendered = f"{rejected.value!s} {rejected.value.findings!r}"
    assert private_secret not in rendered
    assert private_database_url not in rendered
    assert private_origin not in rendered
    assert "database-private-token" not in rendered
    assert "origin-private-token" not in rendered


@pytest.mark.parametrize("environment", ["development", "test"])
def test_non_production_keeps_convenient_defaults(environment: str) -> None:
    settings = Settings(env=environment, _env_file=None)

    assert settings.production_findings() == ()
    assert settings.validate_production() == []
    assert require_runtime_configuration(settings) is None


def test_constructing_settings_does_not_create_storage_directory(tmp_path: Path) -> None:
    storage_root = tmp_path / "not-created" / "storage"

    Settings(storage_root=storage_root, _env_file=None)

    assert not storage_root.exists()
