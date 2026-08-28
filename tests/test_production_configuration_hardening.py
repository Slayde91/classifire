from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.exc import NoSuchModuleError

from classifire import db
from classifire.config import Settings

_DATABASE_SECRET = "database-secret-must-not-leak"  # noqa: S105 - synthetic fixture
_ERROR_SECRET = "driver-error-secret-must-not-leak"  # noqa: S105 - synthetic fixture


def _production_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "_env_file": None,
        "env": "production",
        "database_url": (
            f"postgresql+psycopg://classifire:{_DATABASE_SECRET}@database.internal/classifire"
        ),
        "secret_key": "s" * 32,
        "admin_password": "independent-production-password",
        "session_https_only": True,
        "storage_root": Path("C:/classifire/storage"),
        "trusted_hosts": ["classifire.example.test"],
        "allowed_origins": ["https://classifire.example.test"],
        "max_upload_mb": 100,
        "clamav_host": "scanner.internal",
        "clamav_port": 3310,
        "clamav_stream_max_mb": 100,
        "technical_pdf_preview_enabled": False,
        "technical_extraction_executor_enabled": False,
        "technical_parser_orphan_reconciliation_enabled": False,
    }
    values.update(overrides)
    return Settings(**values)


def _finding_codes(settings: Settings) -> tuple[str, ...]:
    return tuple(finding.code for finding in settings.production_configuration_findings())


def test_secure_production_configuration_has_no_findings() -> None:
    assert _finding_codes(_production_settings()) == ()


def test_production_rejects_enabling_unsandboxed_technical_extraction() -> None:
    assert "PRODUCTION_TECHNICAL_EXTRACTION_SANDBOX_REQUIRED" in _finding_codes(
        _production_settings(technical_extraction_executor_enabled=True)
    )


def test_technical_extraction_executor_is_default_off_and_never_allowed_in_production() -> None:
    assert Settings(_env_file=None).technical_extraction_executor_runtime_allowed is False
    assert (
        Settings(
            _env_file=None,
            env="development",
            technical_extraction_executor_enabled=True,
        ).technical_extraction_executor_runtime_allowed
        is False
    )
    assert (
        Settings(
            _env_file=None,
            env="test",
            technical_extraction_executor_enabled=True,
        ).technical_extraction_executor_runtime_allowed
        is True
    )
    assert (
        _production_settings(
            technical_extraction_executor_enabled=True
        ).technical_extraction_executor_runtime_allowed
        is False
    )


def test_orphan_reconciliation_is_default_off_test_only_and_executor_independent() -> None:
    default = Settings(_env_file=None)
    assert default.technical_parser_orphan_reconciliation_enabled is False
    assert default.technical_parser_orphan_reconciliation_runtime_allowed is False

    reconciliation_only = Settings(
        _env_file=None,
        env="test",
        technical_extraction_executor_enabled=False,
        technical_parser_orphan_reconciliation_enabled=True,
    )
    assert reconciliation_only.technical_parser_orphan_reconciliation_runtime_allowed is True
    assert reconciliation_only.technical_extraction_executor_runtime_allowed is False

    execution_only = Settings(
        _env_file=None,
        env="test",
        technical_extraction_executor_enabled=True,
        technical_parser_orphan_reconciliation_enabled=False,
    )
    assert execution_only.technical_extraction_executor_runtime_allowed is True
    assert execution_only.technical_parser_orphan_reconciliation_runtime_allowed is False

    assert (
        Settings(
            _env_file=None,
            env="development",
            technical_parser_orphan_reconciliation_enabled=True,
        ).technical_parser_orphan_reconciliation_runtime_allowed
        is False
    )


def test_production_rejects_enabling_orphan_reconciliation() -> None:
    settings = _production_settings(
        technical_parser_orphan_reconciliation_enabled=True,
    )

    assert settings.technical_parser_orphan_reconciliation_runtime_allowed is False
    assert (
        "PRODUCTION_TECHNICAL_PARSER_ORPHAN_RECONCILIATION_FORBIDDEN"
        in _finding_codes(settings)
    )


@pytest.mark.parametrize("trusted_hosts", [[], [""], ["*"], ["*.example.test"]])
def test_production_requires_explicit_trusted_hosts(trusted_hosts: list[str]) -> None:
    assert "PRODUCTION_TRUSTED_HOSTS_INVALID" in _finding_codes(
        _production_settings(trusted_hosts=trusted_hosts)
    )


@pytest.mark.parametrize(
    "allowed_origins",
    [
        ["*"],
        ["http://classifire.example.test"],
        ["https://user:password@classifire.example.test"],
        ["https://classifire.example.test/"],
        ["https://classifire.example.test/path"],
        ["https://classifire.example.test?query=value"],
        ["https://classifire.example.test#fragment"],
        [" https://classifire.example.test"],
        ["https://*.example.test"],
        ["https://classifire.example.test:"],
        ["https://classifire.example.test\\ambiguous"],
        ["https://classifire.example.test:not-a-port"],
        ["https://[malformed-ipv6"],
    ],
)
def test_production_rejects_non_exact_https_origins(allowed_origins: list[str]) -> None:
    assert "PRODUCTION_ALLOWED_ORIGINS_INVALID" in _finding_codes(
        _production_settings(allowed_origins=allowed_origins)
    )


@pytest.mark.parametrize(
    "allowed_origins",
    [[], ["https://classifire.example.test"], ["https://classifire.example.test:8443"]],
)
def test_production_accepts_empty_or_exact_https_origins(allowed_origins: list[str]) -> None:
    assert "PRODUCTION_ALLOWED_ORIGINS_INVALID" not in _finding_codes(
        _production_settings(allowed_origins=allowed_origins)
    )


@pytest.mark.parametrize("max_upload_mb", [0, -1, 1025])
def test_production_upload_limit_is_bounded(max_upload_mb: int) -> None:
    assert "PRODUCTION_UPLOAD_LIMIT_INVALID" in _finding_codes(
        _production_settings(max_upload_mb=max_upload_mb)
    )


def test_upload_ingress_ceiling_defaults_to_current_admission_limit() -> None:
    settings = _production_settings(max_upload_mb=73)

    assert settings.upload_ingress_ceiling_mb is None
    assert settings.upload_ingress_ceiling_bytes == 73 * 1024 * 1024


def test_explicit_upload_ingress_ceiling_can_preserve_a_higher_historical_limit() -> None:
    settings = _production_settings(
        max_upload_mb=50,
        upload_ingress_ceiling_mb=100,
    )

    assert settings.upload_ingress_ceiling_bytes == 100 * 1024 * 1024
    assert _finding_codes(settings) == ()


@pytest.mark.parametrize("upload_ingress_ceiling_mb", [0, -1, 1025])
def test_production_upload_ingress_ceiling_is_bounded(
    upload_ingress_ceiling_mb: int,
) -> None:
    assert "PRODUCTION_UPLOAD_INGRESS_CEILING_INVALID" in _finding_codes(
        _production_settings(upload_ingress_ceiling_mb=upload_ingress_ceiling_mb)
    )


def test_production_upload_ingress_ceiling_cannot_be_below_admission_limit() -> None:
    assert "PRODUCTION_UPLOAD_INGRESS_CEILING_BELOW_ADMISSION_LIMIT" in _finding_codes(
        _production_settings(
            max_upload_mb=100,
            upload_ingress_ceiling_mb=99,
        )
    )


def test_production_requires_declared_scanner_stream_limit() -> None:
    assert "MALWARE_SCANNER_STREAM_LIMIT_REQUIRED" in _finding_codes(
        _production_settings(clamav_stream_max_mb=None)
    )


@pytest.mark.parametrize("clamav_stream_max_mb", [-1, 0, 99])
def test_production_scanner_stream_limit_must_cover_uploads(
    clamav_stream_max_mb: int,
) -> None:
    assert "MALWARE_SCANNER_STREAM_LIMIT_TOO_SMALL" in _finding_codes(
        _production_settings(clamav_stream_max_mb=clamav_stream_max_mb)
    )


def test_production_scanner_stream_limit_must_cover_effective_ingress_ceiling() -> None:
    assert "MALWARE_SCANNER_STREAM_LIMIT_TOO_SMALL" in _finding_codes(
        _production_settings(
            max_upload_mb=50,
            upload_ingress_ceiling_mb=100,
            clamav_stream_max_mb=99,
        )
    )


def test_development_keeps_permissive_local_configuration_behavior() -> None:
    settings = Settings(
        _env_file=None,
        env="development",
        trusted_hosts=["*"],
        allowed_origins=["http://localhost:8787"],
        max_upload_mb=0,
        clamav_stream_max_mb=None,
    )

    assert settings.production_configuration_findings() == ()
    assert settings.max_upload_bytes == 0
    assert settings.upload_ingress_ceiling_bytes == 0


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (ModuleNotFoundError(_ERROR_SECRET), "DATABASE_DRIVER_UNAVAILABLE"),
        (NoSuchModuleError(_ERROR_SECRET), "DATABASE_DRIVER_UNAVAILABLE"),
        (ValueError(_ERROR_SECRET), "DATABASE_CONFIGURATION_INVALID"),
    ],
)
def test_database_setup_failures_are_stable_and_redacted(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    expected_code: str,
) -> None:
    def fail_create_engine(*_args: object, **_kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(db, "create_engine", fail_create_engine)

    with pytest.raises(db.DatabaseSetupError) as caught:
        db.create_database_engine(_production_settings())

    assert caught.value.code == expected_code
    assert str(caught.value) == expected_code
    assert _DATABASE_SECRET not in str(caught.value)
    assert _ERROR_SECRET not in str(caught.value)


def test_database_engine_keeps_sqlite_thread_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    sentinel = db.engine

    def record_create_engine(database_url: str, **kwargs: object) -> Any:
        calls.append((database_url, kwargs))
        return sentinel

    monkeypatch.setattr(db, "create_engine", record_create_engine)
    settings = Settings(_env_file=None, database_url="sqlite:///local.sqlite")

    assert db.create_database_engine(settings) is sentinel
    assert calls == [
        (
            "sqlite:///local.sqlite",
            {
                "pool_pre_ping": True,
                "future": True,
                "connect_args": {"check_same_thread": False},
            },
        )
    ]
