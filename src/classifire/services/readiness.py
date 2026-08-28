"""Fail-closed runtime readiness without canonical or bootstrap writes."""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import TechnicalIntakeBatchItem, User
from .deployment_lineage import CLEAN_STACK_HEAD, assess_deployment_lineage
from .malware_scanning import MalwareScanError, require_malware_scanner_readiness
from .storage import StorageReadinessError, require_storage_root_readiness

ReadinessStatus = Literal["READY", "BLOCKED"]
SessionFactory = Callable[[], AbstractContextManager[Session]]
MigrationHeadsProvider = Callable[[], tuple[str, ...]]
StorageProbe = Callable[[Path], str]
ScannerProbe = Callable[[Settings], str]
RuntimeReadinessAssessor = Callable[..., "ReadinessReport"]

_RUNTIME_READINESS_CACHE_SECONDS = 5.0
MIGRATION_SCRIPT_LOCATION = "classifire:migrations"


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    component: str
    status: ReadinessStatus
    code: str
    retryable: bool


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    checks: tuple[ReadinessCheck, ...]

    @property
    def ready(self) -> bool:
        return all(check.status == "READY" for check in self.checks)

    @property
    def failure_codes(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(check.code for check in self.checks if check.status == "BLOCKED")
        )

    def as_public_dict(self) -> dict[str, object]:
        return {
            "status": "ready" if self.ready else "not_ready",
            "codes": list(self.failure_codes),
        }


class ProductionReadinessError(RuntimeError):
    """A redacted startup refusal containing only stable readiness codes."""

    def __init__(self, codes: tuple[str, ...]) -> None:
        self.codes = codes
        super().__init__("CLASSIFIRE_PRODUCTION_NOT_READY:" + ",".join(codes))


def discover_repository_migration_heads() -> tuple[str, ...]:
    """Return the migration heads shipped in the installed application package."""

    config = Config()
    config.set_main_option("script_location", MIGRATION_SCRIPT_LOCATION)
    return tuple(sorted(ScriptDirectory.from_config(config).get_heads()))


def _check(
    component: str,
    *,
    ready: bool,
    code: str,
    retryable: bool,
) -> ReadinessCheck:
    return ReadinessCheck(
        component=component,
        status="READY" if ready else "BLOCKED",
        code=code,
        retryable=retryable,
    )


def assess_runtime_readiness(
    settings: Settings,
    *,
    session_factory: SessionFactory,
    migration_heads_provider: MigrationHeadsProvider = discover_repository_migration_heads,
    storage_probe: StorageProbe = require_storage_root_readiness,
    scanner_probe: ScannerProbe = require_malware_scanner_readiness,
) -> ReadinessReport:
    """Inspect runtime dependencies without changing database or governed state."""

    checks: list[ReadinessCheck] = []
    production = settings.env == "production"

    if production:
        findings = settings.production_configuration_findings()
        if findings:
            checks.extend(
                _check(
                    "configuration",
                    ready=False,
                    code=finding.code,
                    retryable=False,
                )
                for finding in findings
            )
        else:
            checks.append(
                _check(
                    "configuration",
                    ready=True,
                    code="PRODUCTION_CONFIGURATION_VALID",
                    retryable=False,
                )
            )

    try:
        with session_factory() as db:
            db.execute(select(1))
            checks.append(
                _check(
                    "database",
                    ready=True,
                    code="DATABASE_CONNECTION_READY",
                    retryable=True,
                )
            )
            if production:
                try:
                    migration_heads = migration_heads_provider()
                except Exception:
                    checks.append(
                        _check(
                            "database_migrations",
                            ready=False,
                            code="MIGRATION_GRAPH_UNAVAILABLE",
                            retryable=False,
                        )
                    )
                else:
                    if len(migration_heads) != 1:
                        checks.append(
                            _check(
                                "database_migrations",
                                ready=False,
                                code="MIGRATION_GRAPH_MULTIPLE_HEADS",
                                retryable=False,
                            )
                        )
                    elif migration_heads != (CLEAN_STACK_HEAD,):
                        checks.append(
                            _check(
                                "database_migrations",
                                ready=False,
                                code="MIGRATION_GRAPH_POLICY_MISMATCH",
                                retryable=False,
                            )
                        )
                    else:
                        lineage = assess_deployment_lineage(db)
                        checks.append(
                            _check(
                                "database_migrations",
                                ready=lineage.status == "READY",
                                code=lineage.code,
                                retryable=lineage.code == "DATABASE_MIGRATION_REQUIRED",
                            )
                        )
                        if lineage.status == "READY":
                            try:
                                maximum_admitted_size_bytes = db.scalar(
                                    select(
                                        func.max(
                                            TechnicalIntakeBatchItem.declared_size_bytes
                                        )
                                    )
                                )
                            except Exception:
                                checks.append(
                                    _check(
                                        "technical_upload_ingress",
                                        ready=False,
                                        code="TECHNICAL_UPLOAD_INGRESS_CHECK_FAILED",
                                        retryable=True,
                                    )
                                )
                            else:
                                ingress_covers_admitted_batches = (
                                    maximum_admitted_size_bytes is None
                                    or maximum_admitted_size_bytes
                                    <= settings.upload_ingress_ceiling_bytes
                                )
                                checks.append(
                                    _check(
                                        "technical_upload_ingress",
                                        ready=ingress_covers_admitted_batches,
                                        code=(
                                            "TECHNICAL_UPLOAD_INGRESS_LIMIT_COVERS_ADMITTED_BATCHES"
                                            if ingress_covers_admitted_batches
                                            else (
                                                "TECHNICAL_UPLOAD_INGRESS_LIMIT_"
                                                "BELOW_ADMITTED_BATCH"
                                            )
                                        ),
                                        retryable=False,
                                    )
                                )
                                administrator_id = db.scalar(
                                    select(User.id)
                                    .where(
                                        User.role == "administrator",
                                        User.is_active.is_(True),
                                    )
                                    .limit(1)
                                )
                                checks.append(
                                    _check(
                                        "administrator",
                                        ready=administrator_id is not None,
                                        code=(
                                            "ACTIVE_ADMINISTRATOR_CONFIRMED"
                                            if administrator_id is not None
                                            else "ACTIVE_ADMINISTRATOR_MISSING"
                                        ),
                                        retryable=False,
                                    )
                                )
    except Exception:
        checks = [
            check
            for check in checks
            if check.component
            not in {
                "administrator",
                "database",
                "database_migrations",
                "technical_upload_ingress",
            }
        ]
        checks.append(
            _check(
                "database",
                ready=False,
                code="DATABASE_UNAVAILABLE",
                retryable=True,
            )
        )

    try:
        storage_code = storage_probe(settings.storage_root)
    except StorageReadinessError as exc:
        checks.append(
            _check(
                "storage",
                ready=False,
                code=exc.code,
                retryable=exc.code in {"STORAGE_PROBE_FAILED", "STORAGE_ROOT_NOT_WRITABLE"},
            )
        )
    except Exception:
        checks.append(
            _check(
                "storage",
                ready=False,
                code="STORAGE_PROBE_FAILED",
                retryable=True,
            )
        )
    else:
        checks.append(
            _check(
                "storage",
                ready=True,
                code=storage_code,
                retryable=True,
            )
        )

    if production:
        try:
            scanner_probe(settings)
        except MalwareScanError as exc:
            checks.append(
                _check(
                    "malware_scanner",
                    ready=False,
                    code=exc.code,
                    retryable=exc.code
                    in {
                        "MALWARE_SCANNER_TIMEOUT",
                        "MALWARE_SCANNER_UNAVAILABLE",
                    },
                )
            )
        except Exception:
            checks.append(
                _check(
                    "malware_scanner",
                    ready=False,
                    code="MALWARE_SCANNER_ERROR",
                    retryable=True,
                )
            )
        else:
            checks.append(
                _check(
                    "malware_scanner",
                    ready=True,
                    code="MALWARE_SCANNER_READY",
                    retryable=True,
                )
            )

    return ReadinessReport(tuple(checks))


class RuntimeReadinessCache:
    """Coalesce expensive deep dependency probes for a short, bounded period."""

    def __init__(
        self,
        *,
        ttl_seconds: float = _RUNTIME_READINESS_CACHE_SECONDS,
        assessor: RuntimeReadinessAssessor = assess_runtime_readiness,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 0 < ttl_seconds <= 30:
            raise ValueError("Readiness cache TTL must be between 0 and 30 seconds")
        self._ttl_seconds = ttl_seconds
        self._assessor = assessor
        self._clock = clock
        self._lock = threading.Lock()
        self._key: tuple[bytes, int] | None = None
        self._expires_at = 0.0
        self._report: ReadinessReport | None = None

    @staticmethod
    def _cache_key(settings: Settings, session_factory: SessionFactory) -> tuple[bytes, int]:
        configuration_digest = hashlib.sha256(
            settings.model_dump_json().encode("utf-8")
        ).digest()
        return configuration_digest, id(session_factory)

    def assess(
        self,
        settings: Settings,
        *,
        session_factory: SessionFactory,
    ) -> ReadinessReport:
        key = self._cache_key(settings, session_factory)
        with self._lock:
            now = self._clock()
            if self._key == key and self._report is not None and now < self._expires_at:
                return self._report
            report = self._assessor(settings, session_factory=session_factory)
            self._key = key
            self._report = report
            self._expires_at = self._clock() + self._ttl_seconds
            return report


_runtime_readiness_cache = RuntimeReadinessCache()


def assess_cached_runtime_readiness(
    settings: Settings,
    *,
    session_factory: SessionFactory,
) -> ReadinessReport:
    """Return the shared short-lived readiness result used by HTTP probes."""

    return _runtime_readiness_cache.assess(settings, session_factory=session_factory)


def require_production_readiness(
    settings: Settings,
    *,
    session_factory: SessionFactory,
    migration_heads_provider: MigrationHeadsProvider = discover_repository_migration_heads,
    storage_probe: StorageProbe = require_storage_root_readiness,
    scanner_probe: ScannerProbe = require_malware_scanner_readiness,
) -> ReadinessReport:
    """Raise a redacted error before production traffic when any gate is blocked."""

    report = assess_runtime_readiness(
        settings,
        session_factory=session_factory,
        migration_heads_provider=migration_heads_provider,
        storage_probe=storage_probe,
        scanner_probe=scanner_probe,
    )
    if settings.env == "production" and not report.ready:
        raise ProductionReadinessError(report.failure_codes)
    return report


__all__ = [
    "MigrationHeadsProvider",
    "MIGRATION_SCRIPT_LOCATION",
    "ProductionReadinessError",
    "ReadinessCheck",
    "ReadinessReport",
    "ScannerProbe",
    "SessionFactory",
    "StorageProbe",
    "RuntimeReadinessCache",
    "assess_runtime_readiness",
    "assess_cached_runtime_readiness",
    "discover_repository_migration_heads",
    "require_production_readiness",
]
