from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
import typer
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from classifire import cli
from classifire.api.router import health as api_health
from classifire.config import RuntimeConfigurationError, Settings
from classifire.importers.seed import (
    ACTIVE_ADMINISTRATOR_REQUIRED,
    INITIALIZATION_AUDIT_REQUIRED,
    SeedDatabaseError,
)
from classifire.main import (
    add_runtime_security_middleware,
    lifespan,
)
from classifire.main import app as runtime_app
from classifire.services.malware_scanning import MalwareScanError


def _production_settings(tmp_path: Path, **updates: Any) -> Settings:
    values: dict[str, Any] = {
        "env": "production",
        "database_url": "postgresql+psycopg://db.example.test/classifire",
        "secret_key": "C7h!g2Rz_9mK4vQ8pL3xT6nW1sY5dF0a",  # noqa: S106
        "session_https_only": True,
        "trusted_hosts": ["app.example.test"],
        "allowed_origins": ["https://app.example.test"],
        "clamav_host": "clamav.internal",
        "storage_root": tmp_path / "storage",
    }
    values.update(updates)
    return Settings(**values)


def _unsafe_production_settings(tmp_path: Path) -> Settings:
    return _production_settings(
        tmp_path,
        database_url="sqlite:///must-not-be-opened.sqlite",
        secret_key="operator-secret-must-not-leak",  # noqa: S106
        session_https_only=False,
        trusted_hosts=["*"],
        allowed_origins=["*"],
    )


@pytest.fixture(autouse=True)
def _ready_scanner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "require_malware_scanner_ready", lambda _settings: None)
    monkeypatch.setattr(
        "classifire.main.require_malware_scanner_ready",
        lambda _settings: None,
    )


def test_start_rejects_unsafe_production_before_uvicorn_or_filesystem(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _unsafe_production_settings(tmp_path)
    uvicorn_called = False

    def unexpected_uvicorn(*_args: object, **_kwargs: object) -> None:
        nonlocal uvicorn_called
        uvicorn_called = True

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli.uvicorn, "run", unexpected_uvicorn)

    result = CliRunner().invoke(cli.app, ["start"])

    assert result.exit_code != 0
    assert "PRODUCTION_SECRET_KEY_WEAK" in result.output
    assert "operator-secret-must-not-leak" not in result.output
    assert "must-not-be-opened" not in result.output
    assert uvicorn_called is False
    assert not settings.storage_root.exists()


def test_start_rejects_unavailable_scanner_before_schema_or_uvicorn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _production_settings(tmp_path)
    schema_called = False
    uvicorn_called = False

    def unavailable(_settings: Settings) -> None:
        raise MalwareScanError("MALWARE_SCANNER_UNAVAILABLE")

    def unexpected_schema(*_args: object, **_kwargs: object) -> None:
        nonlocal schema_called
        schema_called = True

    def unexpected_uvicorn(*_args: object, **_kwargs: object) -> None:
        nonlocal uvicorn_called
        uvicorn_called = True

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "require_malware_scanner_ready", unavailable)
    monkeypatch.setattr(cli, "prepare_application_schema", unexpected_schema)
    monkeypatch.setattr(cli.uvicorn, "run", unexpected_uvicorn)

    result = CliRunner().invoke(cli.app, ["start"])

    assert result.exit_code != 0
    assert "MALWARE_SCANNER_UNAVAILABLE" in result.output
    assert schema_called is False
    assert uvicorn_called is False
    assert not settings.storage_root.exists()


def test_database_command_rejects_unsafe_production_before_schema_or_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _unsafe_production_settings(tmp_path)
    schema_called = False
    session_called = False

    def unexpected_schema(*_args: object, **_kwargs: object) -> None:
        nonlocal schema_called
        schema_called = True

    def unexpected_session() -> object:
        nonlocal session_called
        session_called = True
        raise AssertionError("database session must not be created")

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "prepare_application_schema", unexpected_schema)
    monkeypatch.setattr(cli, "SessionLocal", unexpected_session)

    result = CliRunner().invoke(
        cli.app,
        [
            "init",
            "--administrator-email",
            "admin@example.test",
            "--operator-reference",
            "CHANGE-TEST",
        ],
    )

    assert result.exit_code != 0
    assert "PRODUCTION_SECRET_KEY_WEAK" in result.output
    assert schema_called is False
    assert session_called is False
    assert not settings.storage_root.exists()


def test_lifespan_rejects_unsafe_production_before_schema_or_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from classifire import main

    settings = _unsafe_production_settings(tmp_path)
    schema_called = False

    def unexpected_schema(*_args: object, **_kwargs: object) -> None:
        nonlocal schema_called
        schema_called = True

    async def enter_lifespan() -> None:
        async with lifespan(runtime_app):
            pass

    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "prepare_application_schema", unexpected_schema)

    with pytest.raises(RuntimeConfigurationError):
        asyncio.run(enter_lifespan())

    assert schema_called is False
    assert not settings.storage_root.exists()


def test_lifespan_rejects_unavailable_scanner_before_schema_or_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from classifire import main

    settings = _production_settings(tmp_path)
    schema_called = False

    def unavailable(_settings: Settings) -> None:
        raise MalwareScanError("MALWARE_SCANNER_UNAVAILABLE")

    def unexpected_schema(*_args: object, **_kwargs: object) -> None:
        nonlocal schema_called
        schema_called = True

    async def enter_lifespan() -> None:
        async with lifespan(runtime_app):
            pass

    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "require_malware_scanner_ready", unavailable)
    monkeypatch.setattr(main, "prepare_application_schema", unexpected_schema)

    with pytest.raises(MalwareScanError) as rejected:
        asyncio.run(enter_lifespan())

    assert rejected.value.code == "MALWARE_SCANNER_UNAVAILABLE"
    assert schema_called is False
    assert not settings.storage_root.exists()


def test_doctor_reports_unsafe_production_without_database_or_secret_disclosure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _unsafe_production_settings(tmp_path)
    database_called = False

    def unexpected_database(*_args: object, **_kwargs: object) -> object:
        nonlocal database_called
        database_called = True
        raise AssertionError("doctor must not inspect an unsafe production database")

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "_doctor_database_engine", unexpected_database)

    result = CliRunner().invoke(cli.app, ["doctor"], terminal_width=240)

    assert result.exit_code == 1
    assert "Production config" in result.output
    assert "FAIL" in result.output
    assert "not inspected" in result.output
    assert "operator-secret-must-not-leak" not in result.output
    assert "must-not-be-opened" not in result.output
    assert database_called is False
    assert not settings.storage_root.exists()


def test_doctor_blocks_database_when_live_scanner_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _production_settings(tmp_path)
    database_called = False

    def unavailable(_settings: Settings) -> None:
        raise MalwareScanError("MALWARE_SCANNER_UNAVAILABLE")

    def unexpected_database(*_args: object, **_kwargs: object) -> object:
        nonlocal database_called
        database_called = True
        raise AssertionError("database must not be inspected before scanner readiness")

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "require_malware_scanner_ready", unavailable)
    monkeypatch.setattr(cli, "_doctor_database_engine", unexpected_database)

    result = CliRunner().invoke(cli.app, ["doctor"], terminal_width=240)

    assert result.exit_code == 1
    assert "Malware scanner" in result.output
    assert "MALWARE_SCANNER_UNAVAILABLE" in result.output
    assert database_called is False
    assert not settings.storage_root.exists()


def test_valid_production_forbids_reload_before_uvicorn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _production_settings(tmp_path)
    uvicorn_called = False

    def unexpected_uvicorn(*_args: object, **_kwargs: object) -> None:
        nonlocal uvicorn_called
        uvicorn_called = True

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli.uvicorn, "run", unexpected_uvicorn)

    with pytest.raises(typer.BadParameter, match="PRODUCTION_RELOAD_FORBIDDEN"):
        cli.start(host=None, port=None, reload=True)

    assert uvicorn_called is False


def test_valid_production_start_requires_initialization_before_uvicorn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _production_settings(tmp_path)
    uvicorn_called = False

    class SessionContext:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, *_args: object) -> None:
            return None

    def missing_initialization(_db: object) -> None:
        raise SeedDatabaseError(INITIALIZATION_AUDIT_REQUIRED)

    def unexpected_uvicorn(*_args: object, **_kwargs: object) -> None:
        nonlocal uvicorn_called
        uvicorn_called = True

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "prepare_application_schema", lambda *_args: None)
    monkeypatch.setattr(cli, "SessionLocal", SessionContext)
    monkeypatch.setattr(cli, "require_seed_database_ready", missing_initialization)
    monkeypatch.setattr(cli.uvicorn, "run", unexpected_uvicorn)

    with pytest.raises(typer.BadParameter, match=INITIALIZATION_AUDIT_REQUIRED):
        cli.start(host=None, port=None, reload=False)

    assert uvicorn_called is False
    assert not settings.storage_root.exists()


def test_valid_production_start_reaches_uvicorn_after_initialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _production_settings(tmp_path)
    invocation: dict[str, object] = {}

    class SessionContext:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, *_args: object) -> None:
            return None

    def capture_uvicorn(target: str, **kwargs: object) -> None:
        invocation["target"] = target
        invocation.update(kwargs)

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "prepare_application_schema", lambda *_args: None)
    monkeypatch.setattr(cli, "SessionLocal", SessionContext)
    monkeypatch.setattr(cli, "require_seed_database_ready", lambda _db: object())
    monkeypatch.setattr(cli.uvicorn, "run", capture_uvicorn)

    cli.start(host=None, port=None, reload=False)

    assert invocation["target"] == "classifire.main:app"
    assert invocation["host"] == "127.0.0.1"


def test_lifespan_requires_initialization_before_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from classifire import main

    settings = _production_settings(tmp_path)

    class SessionContext:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, *_args: object) -> None:
            return None

    def missing_initialization(_db: object) -> None:
        raise SeedDatabaseError(INITIALIZATION_AUDIT_REQUIRED)

    async def enter_lifespan() -> None:
        async with lifespan(runtime_app):
            pass

    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "prepare_application_schema", lambda *_args: None)
    monkeypatch.setattr(main, "SessionLocal", SessionContext)
    monkeypatch.setattr(main, "require_seed_database_ready", missing_initialization)

    with pytest.raises(SeedDatabaseError, match=INITIALIZATION_AUDIT_REQUIRED):
        asyncio.run(enter_lifespan())

    assert not settings.storage_root.exists()


def test_development_start_remains_available(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(env="development")
    invocation: dict[str, object] = {}

    def capture_uvicorn(target: str, **kwargs: object) -> None:
        invocation["target"] = target
        invocation.update(kwargs)

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli.uvicorn, "run", capture_uvicorn)

    result = CliRunner().invoke(cli.app, ["start"])

    assert result.exit_code == 0, result.output
    assert invocation["target"] == "classifire.main:app"
    assert invocation["host"] == "127.0.0.1"
    assert invocation["port"] == 8787


def test_create_admin_rejects_blank_password_before_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema_called = False

    def unexpected_schema() -> Settings:
        nonlocal schema_called
        schema_called = True
        return Settings(env="test")

    monkeypatch.setattr(cli, "_prepare_database_schema", unexpected_schema)

    with pytest.raises(typer.BadParameter, match="--password must not be blank"):
        cli.create_admin(
            email="admin@example.test",
            full_name="Test administrator",
            password="   ",  # noqa: S106 - intentionally blank-only test input.
            operator_reference="CHANGE-TEST",
        )

    assert schema_called is False


def test_production_worker_requires_initialization_before_running(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from classifire import worker as worker_module

    settings = _production_settings(tmp_path)
    worker_called = False

    class SessionContext:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, *_args: object) -> None:
            return None

    def missing_initialization(_db: object) -> None:
        raise SeedDatabaseError(INITIALIZATION_AUDIT_REQUIRED)

    def unexpected_worker(_interval: float) -> None:
        nonlocal worker_called
        worker_called = True

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "prepare_application_schema", lambda *_args: None)
    monkeypatch.setattr(cli, "SessionLocal", SessionContext)
    monkeypatch.setattr(cli, "require_seed_database_ready", missing_initialization)
    monkeypatch.setattr(worker_module, "run_forever", unexpected_worker)

    with pytest.raises(typer.BadParameter, match=INITIALIZATION_AUDIT_REQUIRED):
        cli.worker(interval=0.1)

    assert worker_called is False


def test_production_worker_rejects_unavailable_scanner_before_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from classifire import worker as worker_module

    settings = _production_settings(tmp_path)
    schema_called = False
    worker_called = False

    def unavailable(_settings: Settings) -> None:
        raise MalwareScanError("MALWARE_SCANNER_UNAVAILABLE")

    def unexpected_schema(*_args: object, **_kwargs: object) -> None:
        nonlocal schema_called
        schema_called = True

    def unexpected_worker(_interval: float) -> None:
        nonlocal worker_called
        worker_called = True

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "require_malware_scanner_ready", unavailable)
    monkeypatch.setattr(cli, "prepare_application_schema", unexpected_schema)
    monkeypatch.setattr(worker_module, "run_forever", unexpected_worker)

    with pytest.raises(typer.BadParameter, match="MALWARE_SCANNER_UNAVAILABLE"):
        cli.worker(interval=0.1)

    assert schema_called is False
    assert worker_called is False
    assert not settings.storage_root.exists()


def test_init_reports_explicit_first_administrator_requirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SessionContext:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(cli, "_prepare_database_schema", lambda: Settings(env="test"))
    monkeypatch.setattr(cli, "SessionLocal", SessionContext)

    def missing_administrator(*_args: object, **_kwargs: object) -> dict[str, str]:
        raise SeedDatabaseError(ACTIVE_ADMINISTRATOR_REQUIRED)

    monkeypatch.setattr(cli, "seed_database", missing_administrator)

    result = CliRunner().invoke(
        cli.app,
        [
            "init",
            "--administrator-email",
            "admin@example.test",
            "--operator-reference",
            "CHANGE-TEST",
        ],
    )

    assert result.exit_code != 0
    assert ACTIVE_ADMINISTRATOR_REQUIRED in result.output
    assert "classifire create-admin" in result.output


def test_import_pricing_does_not_seed_an_administrator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "pricing.csv"
    source.write_text("header\n", encoding="utf-8")

    class SessionContext:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(cli, "_prepare_database_schema", lambda: Settings(env="test"))
    monkeypatch.setattr(cli, "SessionLocal", SessionContext)
    monkeypatch.setattr(cli, "_require_seed_ready_for_cli", lambda: None)

    def unexpected_seed(*_args: object, **_kwargs: object) -> dict[str, str]:
        raise AssertionError("import must not seed controlled defaults or users")

    monkeypatch.setattr(cli, "seed_database", unexpected_seed)
    monkeypatch.setattr(
        cli,
        "import_pricing_library",
        lambda *_args, **_kwargs: {"records_inserted": 0},
    )

    result = CliRunner().invoke(cli.app, ["import-pricing", str(source)])

    assert result.exit_code == 0, result.output
    assert "records_inserted" in result.output


def test_import_pricing_rejects_missing_initialization_before_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "pricing.csv"
    source.write_text("header\n", encoding="utf-8")
    import_called = False

    monkeypatch.setattr(cli, "_prepare_database_schema", lambda: Settings(env="test"))

    def missing_initialization() -> None:
        raise typer.BadParameter("Database bootstrap rejected: active_administrator_required")

    def unexpected_import(*_args: object, **_kwargs: object) -> dict[str, object]:
        nonlocal import_called
        import_called = True
        return {}

    monkeypatch.setattr(cli, "_require_seed_ready_for_cli", missing_initialization)
    monkeypatch.setattr(cli, "import_pricing_library", unexpected_import)

    result = CliRunner().invoke(cli.app, ["import-pricing", str(source)])

    assert result.exit_code != 0
    assert "active_administrator_required" in result.output
    assert import_called is False


def test_admission_registration_rejects_unsafe_production_before_input_or_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = tmp_path / "manifest.json"
    receipt = tmp_path / "receipt.json"
    manifest.write_text("{}", encoding="utf-8")
    receipt.write_text("{}", encoding="utf-8")
    settings = _unsafe_production_settings(tmp_path).model_copy(
        update={"adjudicated_initial_submission_enabled": True}
    )
    schema_called = False
    input_called = False

    def unexpected_schema(*_args: object, **_kwargs: object) -> None:
        nonlocal schema_called
        schema_called = True

    def unexpected_read(_path: Path) -> bytes:
        nonlocal input_called
        input_called = True
        raise AssertionError("admission input must not be read")

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "prepare_application_schema", unexpected_schema)
    monkeypatch.setattr(Path, "read_bytes", unexpected_read)

    with pytest.raises(typer.BadParameter, match="PRODUCTION_SECRET_KEY_WEAK"):
        cli.register_adjudicated_admission(manifest, receipt, "operator")

    assert schema_called is False
    assert input_called is False
    assert not settings.storage_root.exists()


def test_runtime_middleware_enforces_cookie_host_and_exact_cors(
    tmp_path: Path,
) -> None:
    settings = _production_settings(
        tmp_path,
        trusted_hosts=["APP.EXAMPLE.TEST"],
    )
    application = FastAPI()

    @application.get("/session")
    def issue_session(request: Request) -> dict[str, str]:
        request.session["test"] = "value"
        return {"status": "ok", "host": request.headers["host"]}

    add_runtime_security_middleware(application, settings)

    with TestClient(application, base_url="https://app.example.test") as client:
        response = client.get("/session")
        cookie = response.headers["set-cookie"].lower()
        assert response.status_code == 200
        assert "secure" in cookie
        assert "httponly" in cookie
        assert "samesite=lax" in cookie
        assert "max-age=43200" in cookie

        rejected_host = client.get(
            "/session",
            headers={"host": "untrusted.example.test"},
        )
        assert rejected_host.status_code == 400

        valid_port = client.get(
            "/session",
            headers={"host": "APP.EXAMPLE.TEST:8443"},
        )
        assert valid_port.status_code == 200
        assert valid_port.json()["host"] == "app.example.test:8443"

        for invalid_host in (
            "app.example.test:evil",
            "app.example.test:443@evil",
            "app.example.test:443:evil",
            f"app.example.test:{'9' * 100}",
        ):
            rejected_malformed_host = client.get(
                "/session",
                headers={"host": invalid_host},
            )
            assert rejected_malformed_host.status_code == 400

        allowed_origin = client.options(
            "/session",
            headers={
                "origin": "https://app.example.test",
                "access-control-request-method": "GET",
            },
        )
        assert allowed_origin.status_code == 200
        assert allowed_origin.headers["access-control-allow-origin"] == "https://app.example.test"

        untrusted_host_preflight = client.options(
            "/session",
            headers={
                "host": "untrusted.example.test",
                "origin": "https://app.example.test",
                "access-control-request-method": "GET",
            },
        )
        assert untrusted_host_preflight.status_code == 400
        assert "access-control-allow-origin" not in untrusted_host_preflight.headers

        rejected_origin = client.options(
            "/session",
            headers={
                "origin": "https://untrusted.example.test",
                "access-control-request-method": "GET",
            },
        )
        assert rejected_origin.status_code == 400
        assert "access-control-allow-origin" not in rejected_origin.headers


def test_public_api_health_omits_environment_and_configuration_findings(
    tmp_path: Path,
) -> None:
    class Database:
        def execute(self, _statement: object) -> None:
            return None

    payload = api_health(  # type: ignore[arg-type]
        Database(),
        _unsafe_production_settings(tmp_path),
    )

    assert payload["status"] == "ok"
    assert "environment" not in payload
    assert "production_findings" not in payload
