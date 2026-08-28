from __future__ import annotations

import asyncio
import importlib
import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import typer
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from test_migrations_physical_foundation import _migration_environment, _upgrade

from classifire import cli, main
from classifire.config import Settings
from classifire.db import Base
from classifire.models import TechnicalIntakeBatch, TechnicalIntakeBatchItem, User
from classifire.services.deployment_lineage import CLEAN_STACK_HEAD
from classifire.services.malware_scanning import MalwareScanError
from classifire.services.readiness import (
    ProductionReadinessError,
    ReadinessCheck,
    ReadinessReport,
    assess_runtime_readiness,
    discover_repository_migration_heads,
    require_production_readiness,
)
from classifire.services.storage import (
    StorageReadinessError,
    require_storage_root_readiness,
)

_DATABASE_SECRET = "database-password-must-not-leak"  # noqa: S105 - synthetic fixture
_RAW_ERROR_SECRET = "raw-database-error-must-not-leak"  # noqa: S105 - synthetic fixture
_INGRESS_ERROR_SECRET = "ingress-query-error-must-not-leak"  # noqa: S105
api_router = importlib.import_module("classifire.api.router")


def _production_settings(tmp_path: Path, **overrides: Any) -> Settings:
    storage_root = tmp_path / "storage"
    storage_root.mkdir(parents=True, exist_ok=True)
    values: dict[str, Any] = {
        "_env_file": None,
        "env": "production",
        "database_url": (
            "postgresql+psycopg://classifire:"
            f"{_DATABASE_SECRET}@database.internal/classifire"
        ),
        "secret_key": "s" * 32,
        "admin_password": "independent-production-password",
        "session_https_only": True,
        "storage_root": storage_root,
        "allowed_origins": ["https://classifire.example.test"],
        "trusted_hosts": ["classifire.example.test"],
        "clamav_host": "scanner.internal",
        "clamav_port": 3310,
        "clamav_stream_max_mb": 100,
        "technical_pdf_preview_enabled": False,
    }
    values.update(overrides)
    return Settings(**values)


def _database_factory(
    tmp_path: Path,
    *,
    revision: str | None = CLEAN_STACK_HEAD,
    administrator: bool = True,
) -> sessionmaker[Session]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    database_path = tmp_path / "readiness.sqlite"
    engine = create_engine(f"sqlite:///{database_path}", future=True)
    Base.metadata.create_all(engine)
    if revision is not None:
        with engine.begin() as connection:
            connection.execute(
                text("CREATE TABLE alembic_version (version_num VARCHAR(255) NOT NULL)")
            )
            connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
                {"revision": revision},
            )
    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    if administrator:
        with factory() as db:
            db.add(
                User(
                    email="production.admin@example.test",
                    full_name="Production Administrator",
                    password_hash="not-used-by-readiness",  # noqa: S106 - synthetic fixture
                    role="administrator",
                    is_active=True,
                )
            )
            db.commit()
    return factory


def _ready_report() -> ReadinessReport:
    return ReadinessReport(
        (
            ReadinessCheck(
                component="configuration",
                status="READY",
                code="PRODUCTION_CONFIGURATION_VALID",
                retryable=False,
            ),
        )
    )


def _add_intake_batch_items(
    factory: sessionmaker[Session],
    *,
    items: tuple[tuple[int, str], ...],
) -> None:
    with factory() as db:
        administrator_id = db.query(User.id).scalar()
        assert administrator_id is not None
        batch = TechnicalIntakeBatch(
            client_request_id=str(uuid.uuid4()),
            created_by_id=administrator_id,
            expected_item_count=len(items),
            manifest_sha256="a" * 64,
            status="open",
        )
        db.add(batch)
        db.flush()
        for ordinal, (declared_size_bytes, status) in enumerate(items, start=1):
            item = TechnicalIntakeBatchItem(
                batch_id=batch.id,
                client_item_id=str(uuid.uuid4()),
                ordinal=ordinal,
                original_filename=f"report-{ordinal}.pdf",
                declared_size_bytes=declared_size_bytes,
                expected_sha256="b" * 64,
                declared_document_id=f"document-{ordinal}",
                registration_snapshot={"ordinal": ordinal},
                registration_sha256="c" * 64,
                status=status,
            )
            if status == "rejected":
                item.attempt_count = 1
                item.outcome_code = "UPLOAD_SIZE_MISMATCH"
                item.outcome_retryable = False
                item.last_outcome_at = datetime.now(UTC)
                item.receipt_schema = "technical-intake-item-receipt-v1"
                item.receipt_json = {"code": "UPLOAD_SIZE_MISMATCH"}
                item.receipt_sha256 = "d" * 64
            db.add(item)
        db.commit()


def _blocked_report(code: str = "DATABASE_UNAVAILABLE") -> ReadinessReport:
    return ReadinessReport(
        (
            ReadinessCheck(
                component="database",
                status="BLOCKED",
                code=code,
                retryable=True,
            ),
        )
    )


def _assess(
    settings: Settings,
    factory: sessionmaker[Session],
    **overrides: Any,
) -> ReadinessReport:
    parameters: dict[str, Any] = {
        "session_factory": factory,
        "migration_heads_provider": lambda: (CLEAN_STACK_HEAD,),
        "storage_probe": lambda _root: "STORAGE_READY",
        "scanner_probe": lambda _settings: "PONG",
    }
    parameters.update(overrides)
    return assess_runtime_readiness(settings, **parameters)


def test_repository_migration_graph_has_one_policy_head() -> None:
    assert discover_repository_migration_heads() == (CLEAN_STACK_HEAD,)


def test_alembic_upgrade_head_produces_runtime_ready_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "migrated-readiness.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)
    _upgrade(database_url, environment, "head")

    migrated_engine = create_engine(database_url, future=True)
    factory = sessionmaker(
        bind=migrated_engine,
        expire_on_commit=False,
        class_=Session,
    )
    try:
        with factory() as db:
            db.add(
                User(
                    email="migrated.admin@example.test",
                    full_name="Migrated Administrator",
                    password_hash="not-used-by-readiness",  # noqa: S106
                    role="administrator",
                    is_active=True,
                )
            )
            db.commit()

        report = _assess(_production_settings(tmp_path), factory)
    finally:
        migrated_engine.dispose()

    assert report.ready, report.failure_codes
    assert report.failure_codes == ()


def test_exact_production_runtime_is_ready(tmp_path: Path) -> None:
    settings = _production_settings(tmp_path)
    factory = _database_factory(tmp_path)

    report = _assess(settings, factory)

    assert report.ready is True
    assert report.failure_codes == ()
    assert report.as_public_dict() == {"status": "ready", "codes": []}
    assert [check.code for check in report.checks] == [
        "PRODUCTION_CONFIGURATION_VALID",
        "DATABASE_CONNECTION_READY",
        "CLEAN_STACK_HEAD_CONFIRMED",
        "TECHNICAL_UPLOAD_INGRESS_LIMIT_COVERS_ADMITTED_BATCHES",
        "ACTIVE_ADMINISTRATOR_CONFIRMED",
        "STORAGE_READY",
        "MALWARE_SCANNER_READY",
    ]


def test_ingress_ceiling_covers_every_persisted_manifest_item_including_terminal(
    tmp_path: Path,
) -> None:
    factory = _database_factory(tmp_path)
    _add_intake_batch_items(
        factory,
        items=(
            (1 * 1024 * 1024, "pending"),
            (3 * 1024 * 1024, "rejected"),
        ),
    )
    blocked_settings = _production_settings(
        tmp_path,
        max_upload_mb=1,
        upload_ingress_ceiling_mb=2,
        clamav_stream_max_mb=2,
    )

    blocked = _assess(blocked_settings, factory)

    assert blocked.failure_codes == (
        "TECHNICAL_UPLOAD_INGRESS_LIMIT_BELOW_ADMITTED_BATCH",
    )
    assert blocked.as_public_dict() == {
        "status": "not_ready",
        "codes": ["TECHNICAL_UPLOAD_INGRESS_LIMIT_BELOW_ADMITTED_BATCH"],
    }

    covered = _assess(
        _production_settings(
            tmp_path,
            max_upload_mb=1,
            upload_ingress_ceiling_mb=3,
            clamav_stream_max_mb=3,
        ),
        factory,
    )

    assert covered.ready is True
    assert any(
        check.code == "TECHNICAL_UPLOAD_INGRESS_LIMIT_COVERS_ADMITTED_BATCHES"
        for check in covered.checks
    )


def test_ingress_manifest_query_failure_is_stable_and_redacted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    declared_size_bytes = 3_145_729
    factory = _database_factory(tmp_path)
    _add_intake_batch_items(
        factory,
        items=((declared_size_bytes, "rejected"),),
    )
    settings = _production_settings(tmp_path)

    @contextmanager
    def ingress_query_failure() -> Iterator[Session]:
        with factory() as db:
            original_scalar = db.scalar

            def fail_ingress_query(
                statement: Any,
                *args: Any,
                **kwargs: Any,
            ) -> Any:
                if "max(technical_intake_batch_items.declared_size_bytes)" in str(
                    statement
                ).casefold():
                    raise RuntimeError(
                        f"{_INGRESS_ERROR_SECRET}:{declared_size_bytes}:{settings.storage_root}"
                    )
                return original_scalar(statement, *args, **kwargs)

            monkeypatch.setattr(db, "scalar", fail_ingress_query)
            yield db

    report = assess_runtime_readiness(
        settings,
        session_factory=ingress_query_failure,
        migration_heads_provider=lambda: (CLEAN_STACK_HEAD,),
        storage_probe=lambda _root: "STORAGE_READY",
        scanner_probe=lambda _settings: "PONG",
    )

    assert report.failure_codes == ("TECHNICAL_UPLOAD_INGRESS_CHECK_FAILED",)
    ingress_check = next(
        check for check in report.checks if check.component == "technical_upload_ingress"
    )
    assert ingress_check.retryable is True
    public = json.dumps(report.as_public_dict())
    assert _INGRESS_ERROR_SECRET not in public
    assert str(declared_size_bytes) not in public
    assert str(settings.storage_root) not in public


@pytest.mark.parametrize(
    ("override", "expected_code"),
    [
        ({"secret_key": "short"}, "PRODUCTION_SECRET_KEY_INVALID"),
        (
            {"admin_password": "change-me-immediately"},
            "PRODUCTION_ADMIN_PASSWORD_DEFAULT",
        ),
        ({"session_https_only": False}, "PRODUCTION_SECURE_SESSION_REQUIRED"),
        (
            {"database_url": "sqlite:///production.sqlite"},
            "PRODUCTION_DATABASE_NOT_POSTGRESQL",
        ),
        (
            {"database_url": "postgresql-not-really://database"},
            "PRODUCTION_DATABASE_NOT_POSTGRESQL",
        ),
        (
            {"storage_root": Path("relative/storage")},
            "PRODUCTION_STORAGE_ROOT_NOT_ABSOLUTE",
        ),
        ({"clamav_host": None}, "MALWARE_SCANNER_REQUIRED"),
        ({"clamav_port": 70000}, "MALWARE_SCANNER_CONFIGURATION_INVALID"),
        (
            {"upload_ingress_ceiling_mb": -1},
            "PRODUCTION_UPLOAD_INGRESS_CEILING_INVALID",
        ),
        (
            {"technical_pdf_preview_enabled": True},
            "PRODUCTION_PDF_PREVIEW_SANDBOX_REQUIRED",
        ),
    ],
)
def test_every_unsafe_production_setting_is_blocking(
    tmp_path: Path,
    override: dict[str, Any],
    expected_code: str,
) -> None:
    settings = _production_settings(tmp_path, **override)
    factory = _database_factory(tmp_path)

    report = _assess(settings, factory)

    assert report.ready is False
    assert expected_code in report.failure_codes
    with pytest.raises(ProductionReadinessError) as caught:
        require_production_readiness(
            settings,
            session_factory=factory,
            migration_heads_provider=lambda: (CLEAN_STACK_HEAD,),
            storage_probe=lambda _root: "STORAGE_READY",
            scanner_probe=lambda _settings: "PONG",
        )
    assert expected_code in caught.value.codes


@pytest.mark.parametrize(
    ("heads", "expected_code"),
    [
        ((), "MIGRATION_GRAPH_MULTIPLE_HEADS"),
        (("one", "two"), "MIGRATION_GRAPH_MULTIPLE_HEADS"),
        (("unexpected",), "MIGRATION_GRAPH_POLICY_MISMATCH"),
    ],
)
def test_migration_graph_must_be_single_and_policy_bound(
    tmp_path: Path,
    heads: tuple[str, ...],
    expected_code: str,
) -> None:
    report = _assess(
        _production_settings(tmp_path),
        _database_factory(tmp_path),
        migration_heads_provider=lambda: heads,
    )

    assert expected_code in report.failure_codes


def test_unreadable_migration_graph_is_redacted(tmp_path: Path) -> None:
    def unavailable_graph() -> tuple[str, ...]:
        raise RuntimeError(_RAW_ERROR_SECRET)

    report = _assess(
        _production_settings(tmp_path),
        _database_factory(tmp_path),
        migration_heads_provider=unavailable_graph,
    )

    assert "MIGRATION_GRAPH_UNAVAILABLE" in report.failure_codes
    assert _RAW_ERROR_SECRET not in json.dumps(report.as_public_dict())


def test_missing_or_old_database_revision_is_blocking(tmp_path: Path) -> None:
    settings = _production_settings(tmp_path)

    missing = _assess(settings, _database_factory(tmp_path / "missing", revision=None))
    old = _assess(
        settings,
        _database_factory(
            tmp_path / "old",
            revision="0010_release_publication_slot",
        ),
    )

    assert "ALEMBIC_VERSION_TABLE_MISSING" in missing.failure_codes
    assert "DATABASE_MIGRATION_REQUIRED" in old.failure_codes


def test_active_administrator_is_required_without_creating_one(tmp_path: Path) -> None:
    report = _assess(
        _production_settings(tmp_path),
        _database_factory(tmp_path, administrator=False),
    )

    assert report.failure_codes == ("ACTIVE_ADMINISTRATOR_MISSING",)


def test_database_failure_is_redacted_and_does_not_stop_later_probes(tmp_path: Path) -> None:
    settings = _production_settings(tmp_path)
    calls: list[str] = []

    @contextmanager
    def unavailable_database() -> Iterator[Session]:
        raise RuntimeError(_RAW_ERROR_SECRET)
        yield  # pragma: no cover

    def storage_probe(_root: Path) -> str:
        calls.append("storage")
        return "STORAGE_READY"

    def scanner_probe(_settings: Settings) -> str:
        calls.append("scanner")
        return "PONG"

    report = assess_runtime_readiness(
        settings,
        session_factory=unavailable_database,
        storage_probe=storage_probe,
        scanner_probe=scanner_probe,
    )

    assert report.failure_codes == ("DATABASE_UNAVAILABLE",)
    assert calls == ["storage", "scanner"]
    public = json.dumps(report.as_public_dict())
    assert _RAW_ERROR_SECRET not in public
    assert _DATABASE_SECRET not in public
    assert str(settings.storage_root) not in public
    assert settings.clamav_host is not None
    assert settings.clamav_host not in public


def test_storage_and_scanner_failures_preserve_stable_codes(tmp_path: Path) -> None:
    settings = _production_settings(tmp_path)
    factory = _database_factory(tmp_path)

    def storage_failure(_root: Path) -> str:
        raise StorageReadinessError("STORAGE_ROOT_UNSAFE")

    def scanner_failure(_settings: Settings) -> str:
        raise MalwareScanError("MALWARE_SCANNER_TIMEOUT")

    report = _assess(
        settings,
        factory,
        storage_probe=storage_failure,
        scanner_probe=scanner_failure,
    )

    assert report.failure_codes == (
        "STORAGE_ROOT_UNSAFE",
        "MALWARE_SCANNER_TIMEOUT",
    )


def test_storage_probe_proves_hard_link_readback_and_leaves_no_residue(
    tmp_path: Path,
) -> None:
    root = tmp_path / "storage"
    root.mkdir()
    before = tuple(root.iterdir())

    assert require_storage_root_readiness(root) == "STORAGE_READY"

    assert tuple(root.iterdir()) == before


def test_storage_probe_rejects_missing_file_and_filesystem_root(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    regular_file = tmp_path / "file-root"
    regular_file.write_text("not a directory", encoding="utf-8")

    with pytest.raises(StorageReadinessError, match="STORAGE_ROOT_INVALID"):
        require_storage_root_readiness(missing)
    with pytest.raises(StorageReadinessError, match="STORAGE_ROOT_INVALID"):
        require_storage_root_readiness(regular_file)
    with pytest.raises(StorageReadinessError, match="STORAGE_ROOT_UNSAFE"):
        require_storage_root_readiness(Path(tmp_path.anchor))


def test_storage_probe_hard_link_failure_is_redacted_and_cleans_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "storage"
    root.mkdir()

    def link_denied(*_args: object, **_kwargs: object) -> None:
        raise PermissionError(_RAW_ERROR_SECRET)

    monkeypatch.setattr("classifire.services.storage.os.link", link_denied)

    with pytest.raises(StorageReadinessError) as caught:
        require_storage_root_readiness(root)

    assert caught.value.code == "STORAGE_ROOT_NOT_WRITABLE"
    assert _RAW_ERROR_SECRET not in str(caught.value)
    assert tuple(root.iterdir()) == ()


def test_storage_probe_reports_cleanup_failure_without_leaking_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "storage"
    root.mkdir()
    original_unlink = Path.unlink

    def fail_link_cleanup(path: Path, missing_ok: bool = False) -> None:
        if str(path).endswith(".link"):
            raise OSError(_RAW_ERROR_SECRET)
        original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail_link_cleanup)
    try:
        with pytest.raises(StorageReadinessError) as caught:
            require_storage_root_readiness(root)
    finally:
        monkeypatch.undo()
        for residue in root.iterdir():
            residue.unlink()

    assert caught.value.code == "STORAGE_PROBE_CLEANUP_FAILED"
    assert _RAW_ERROR_SECRET not in str(caught.value)
    assert str(root) not in str(caught.value)


def test_production_settings_do_not_create_storage_but_local_settings_do(
    tmp_path: Path,
) -> None:
    production_root = tmp_path / "production-storage"
    development_root = tmp_path / "development-storage"

    Settings(
        _env_file=None,
        env="production",
        storage_root=production_root,
    )
    Settings(
        _env_file=None,
        env="development",
        storage_root=development_root,
    )

    assert production_root.exists() is False
    assert development_root.is_dir()


def test_production_lifespan_refuses_before_schema_or_seed_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _production_settings(tmp_path)
    calls: list[str] = []

    def blocked(*_args: object, **_kwargs: object) -> ReadinessReport:
        calls.append("readiness")
        raise ProductionReadinessError(("DATABASE_UNAVAILABLE",))

    def unexpected(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("production startup attempted a bootstrap write")

    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "require_production_readiness", blocked)
    monkeypatch.setattr(main.Base.metadata, "create_all", unexpected)
    monkeypatch.setattr(main, "seed_database", unexpected)

    async def exercise() -> None:
        with pytest.raises(ProductionReadinessError):
            async with main.lifespan(main.app):
                raise AssertionError("blocked lifespan yielded")

    asyncio.run(exercise())
    assert calls == ["readiness"]


def test_ready_production_lifespan_never_creates_schema_or_seeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _production_settings(tmp_path)
    yielded: list[bool] = []

    def ready(*_args: object, **_kwargs: object) -> ReadinessReport:
        return _ready_report()

    def unexpected(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("production startup attempted a bootstrap write")

    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "require_production_readiness", ready)
    monkeypatch.setattr(main.Base.metadata, "create_all", unexpected)
    monkeypatch.setattr(main, "seed_database", unexpected)

    async def exercise() -> None:
        async with main.lifespan(main.app):
            yielded.append(True)

    asyncio.run(exercise())
    assert yielded == [True]


def test_production_lifespan_refuses_orphan_reconciliation_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _production_settings(
        tmp_path,
        technical_parser_orphan_reconciliation_enabled=True,
    )
    calls: list[str] = []

    def blocked(value: Settings, **_kwargs: object) -> ReadinessReport:
        code = "PRODUCTION_TECHNICAL_PARSER_ORPHAN_RECONCILIATION_FORBIDDEN"
        assert code in {
            finding.code for finding in value.production_configuration_findings()
        }
        calls.append("readiness")
        raise ProductionReadinessError((code,))

    def unexpected(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("production startup attempted a write")

    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "require_production_readiness", blocked)
    monkeypatch.setattr(main.Base.metadata, "create_all", unexpected)
    monkeypatch.setattr(main, "seed_database", unexpected)

    async def exercise() -> None:
        with pytest.raises(ProductionReadinessError):
            async with main.lifespan(main.app):
                raise AssertionError("blocked lifespan yielded")

    asyncio.run(exercise())
    assert calls == ["readiness"]


def test_local_lifespan_retains_explicit_development_bootstrap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        env="test",
        storage_root=tmp_path / "storage",
    )
    calls: list[str] = []

    class EmptySession:
        def __enter__(self) -> EmptySession:
            calls.append("session")
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def scalar(self, _statement: object) -> None:
            return None

    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(
        main.Base.metadata,
        "create_all",
        lambda **_kwargs: calls.append("create_all"),
    )
    monkeypatch.setattr(main, "SessionLocal", EmptySession)
    monkeypatch.setattr(
        main,
        "seed_database",
        lambda *_args, **_kwargs: calls.append("seed"),
    )

    async def exercise() -> None:
        async with main.lifespan(main.app):
            calls.append("yield")

    asyncio.run(exercise())
    assert calls == ["create_all", "session", "seed", "yield"]


def test_liveness_is_dependency_free_while_readiness_can_be_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main,
        "assess_cached_runtime_readiness",
        lambda *_args, **_kwargs: _blocked_report("DATABASE_UNAVAILABLE"),
    )

    assert main.healthz()["status"] == "ok"
    response = main.readyz()

    assert response.status_code == 503
    assert json.loads(response.body) == {
        "status": "not_ready",
        "codes": ["DATABASE_UNAVAILABLE"],
    }
    assert response.headers["cache-control"] == "no-store"


def test_actual_local_asgi_liveness_and_readiness_routes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        env="test",
        database_url=f"sqlite:///{tmp_path / 'application.sqlite'}",
        storage_root=tmp_path / "storage",
    )
    test_engine = create_engine(settings.database_url, future=True)
    test_sessions = sessionmaker(
        bind=test_engine,
        expire_on_commit=False,
        class_=Session,
    )
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "engine", test_engine)
    monkeypatch.setattr(main, "SessionLocal", test_sessions)

    try:
        with TestClient(main.app, base_url="http://localhost") as client:
            live = client.get("/healthz")
            ready = client.get("/readyz")
    finally:
        test_engine.dispose()

    assert live.status_code == 200
    assert live.json()["status"] == "ok"
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "codes": []}
    assert ready.headers["cache-control"] == "no-store"
    assert not list(settings.storage_root.glob(".classifire-readiness-*"))


def test_legacy_api_health_preserves_deprecated_diagnostic_contract(
    tmp_path: Path,
) -> None:
    factory = _database_factory(tmp_path / "legacy-health")
    with factory() as db:
        response = api_router.health(db, _production_settings(tmp_path))

    assert response["status"] == "ok"
    assert response["product"] == "QUANTIFIRE"
    assert response["version"] == "0.1.0"
    assert response["environment"] == "production"
    assert response["production_findings"] == []
    assert isinstance(response["timestamp"], str)


def test_cli_start_refuses_before_uvicorn_when_production_is_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: _production_settings(tmp_path))
    monkeypatch.setattr(
        cli,
        "require_production_readiness",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ProductionReadinessError(("DATABASE_UNAVAILABLE",))
        ),
    )
    monkeypatch.setattr(
        cli.uvicorn,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("uvicorn started while readiness was blocked")
        ),
    )

    with pytest.raises(typer.Exit):
        cli.start(host=None, port=None, reload=False)


def test_cli_worker_refuses_before_importing_runtime_when_production_is_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: _production_settings(tmp_path))
    monkeypatch.setattr(
        cli,
        "require_production_readiness",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ProductionReadinessError(("DATABASE_UNAVAILABLE",))
        ),
    )

    with pytest.raises(typer.Exit):
        cli.worker(interval=0.01)


def test_doctor_redacts_database_url_and_raw_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = _production_settings(tmp_path)

    class BrokenSession:
        def __enter__(self) -> BrokenSession:
            raise RuntimeError(_RAW_ERROR_SECRET)

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "SessionLocal", BrokenSession)
    monkeypatch.setattr(
        cli,
        "assess_runtime_readiness",
        lambda *_args, **_kwargs: _blocked_report("DATABASE_UNAVAILABLE"),
    )

    with pytest.raises(typer.Exit):
        cli.doctor()

    output = capsys.readouterr().out
    assert "DATABASE_UNAVAILABLE" in output
    assert _DATABASE_SECRET not in output
    assert _RAW_ERROR_SECRET not in output


def test_production_database_commands_do_not_create_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _production_settings(tmp_path)
    monkeypatch.setattr(
        cli.Base.metadata,
        "create_all",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("production command attempted create_all")
        ),
    )

    cli._create_local_schema(settings)


def test_production_admin_and_import_commands_never_bootstrap_schema_or_seed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _production_settings(tmp_path)
    added: list[object] = []
    commits: list[bool] = []

    class CommandSession:
        def __enter__(self) -> CommandSession:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def scalar(self, *_args: object, **_kwargs: object) -> None:
            return None

        def add(self, value: object) -> None:
            added.append(value)

        def commit(self) -> None:
            commits.append(True)

    def unexpected(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("production command attempted bootstrap state")

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli.Base.metadata, "create_all", unexpected)
    monkeypatch.setattr(cli, "seed_database", unexpected)
    monkeypatch.setattr(cli, "SessionLocal", CommandSession)
    monkeypatch.setattr(cli, "hash_password", lambda _password: "synthetic-hash")
    monkeypatch.setattr(
        cli,
        "import_pricing_library",
        lambda *_args, **_kwargs: {"status": "pricing-imported"},
    )
    monkeypatch.setattr(
        cli,
        "import_technical_variants",
        lambda *_args, **_kwargs: {"status": "technical-imported"},
    )

    cli.create_admin(
        email="production.admin@example.test",
        full_name="Production Administrator",
        password="synthetic-password",  # noqa: S106 - synthetic fixture
    )
    cli.import_pricing(tmp_path / "pricing.csv", version="test")
    cli.import_technical(tmp_path / "technical.jsonl", version="test")

    supplied = tmp_path / "supplied"
    supplied.mkdir()
    (supplied / "QUANTIFIRE_14_Pricing_Library_v2.13.csv").write_text(
        "fixture",
        encoding="utf-8",
    )
    (supplied / "QUANTIFIRE_17_Technical_System_Variants_v2.13.jsonl").write_text(
        "fixture",
        encoding="utf-8",
    )
    cli.import_supplied_v213(supplied)

    assert len(added) == 1
    assert commits == [True]


def test_production_init_is_refused_before_schema_or_seed_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _production_settings(tmp_path)

    def unexpected(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("production init attempted a bootstrap write")

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli.Base.metadata, "create_all", unexpected)
    monkeypatch.setattr(cli, "seed_database", unexpected)

    with pytest.raises(typer.Exit):
        cli.init_database()
