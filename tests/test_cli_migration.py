from __future__ import annotations

import pytest
import typer
from alembic.config import Config

from classifire import cli
from classifire.services.readiness import MIGRATION_SCRIPT_LOCATION

_RAW_MIGRATION_SECRET = "migration-dsn-secret-must-not-leak"  # noqa: S105


def test_migrate_uses_the_graph_shipped_with_the_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str | None, str]] = []

    def upgrade(config: Config, revision: str) -> None:
        calls.append((config.get_main_option("script_location"), revision))

    monkeypatch.setattr(cli.alembic_command, "upgrade", upgrade)

    cli.migrate_database()

    assert calls == [(MIGRATION_SCRIPT_LOCATION, "head")]


def test_migrate_failure_is_redacted(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli.alembic_command,
        "upgrade",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError(_RAW_MIGRATION_SECRET)
        ),
    )

    with pytest.raises(typer.Exit):
        cli.migrate_database()

    output = capsys.readouterr().out
    assert "DATABASE_MIGRATION_FAILED" in output
    assert _RAW_MIGRATION_SECRET not in output
