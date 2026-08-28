from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager
from pathlib import Path

from sqlalchemy.orm import Session

from classifire.config import Settings
from classifire.services.readiness import (
    ReadinessCheck,
    ReadinessReport,
    RuntimeReadinessCache,
)


def _settings(tmp_path: Path, *, port: int = 8787) -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        port=port,
        storage_root=tmp_path / f"storage-{port}",
    )


def _report(code: str) -> ReadinessReport:
    return ReadinessReport(
        (
            ReadinessCheck(
                component="database",
                status="READY",
                code=code,
                retryable=True,
            ),
        )
    )


def _unused_session_factory() -> AbstractContextManager[Session]:
    raise AssertionError("the synthetic assessor must not open a database session")


def test_runtime_readiness_cache_reuses_then_expires_result(tmp_path: Path) -> None:
    now = [100.0]
    calls: list[int] = []

    def assessor(_settings: Settings, **_kwargs: object) -> ReadinessReport:
        calls.append(len(calls) + 1)
        return _report(f"READY_{calls[-1]}")

    cache = RuntimeReadinessCache(
        ttl_seconds=5,
        assessor=assessor,
        clock=lambda: now[0],
    )
    settings = _settings(tmp_path)
    first = cache.assess(settings, session_factory=_unused_session_factory)
    second = cache.assess(settings, session_factory=_unused_session_factory)
    now[0] = 105.0
    third = cache.assess(settings, session_factory=_unused_session_factory)

    assert first is second
    assert first.checks[0].code == "READY_1"
    assert third.checks[0].code == "READY_2"
    assert calls == [1, 2]


def test_runtime_readiness_cache_key_tracks_configuration(tmp_path: Path) -> None:
    calls: list[int] = []

    def assessor(_settings: Settings, **_kwargs: object) -> ReadinessReport:
        calls.append(len(calls) + 1)
        return _report(f"READY_{calls[-1]}")

    cache = RuntimeReadinessCache(assessor=assessor)
    cache.assess(_settings(tmp_path, port=8787), session_factory=_unused_session_factory)
    changed = cache.assess(
        _settings(tmp_path, port=8788),
        session_factory=_unused_session_factory,
    )

    assert changed.checks[0].code == "READY_2"
    assert calls == [1, 2]


def test_runtime_readiness_cache_single_flights_concurrent_calls(tmp_path: Path) -> None:
    calls: list[int] = []

    def assessor(_settings: Settings, **_kwargs: object) -> ReadinessReport:
        calls.append(1)
        return _report("READY_ONCE")

    cache = RuntimeReadinessCache(assessor=assessor)
    settings = _settings(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        reports = list(
            pool.map(
                lambda _index: cache.assess(
                    settings,
                    session_factory=_unused_session_factory,
                ),
                range(16),
            )
        )

    assert len(calls) == 1
    assert all(report is reports[0] for report in reports)
