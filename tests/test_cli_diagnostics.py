from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from classifire import cli
from classifire.config import Settings


def _doctor_root(tmp_path: Path) -> Path:
    root = tmp_path / "doctor-root"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname = 'classifire-test'\n", encoding="utf-8")
    logo = root / "assets" / "brand" / "quantifire-logo-master.png"
    logo.parent.mkdir(parents=True)
    logo.write_bytes(b"approved-logo")
    return root


class _PassingSession:
    def __enter__(self) -> _PassingSession:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, _statement: object) -> None:
        return None

    def scalar(self, _statement: object) -> int:
        return 1


def test_doctor_hides_database_url_when_connection_succeeds(
    monkeypatch,
    tmp_path: Path,
) -> None:
    sensitive_marker = "doctor-secret-must-not-appear"
    settings = Settings(
        env="test",
        database_url=(
            "postgresql+psycopg://diagnostic_user:"
            f"{sensitive_marker}@database.example.test:5432/classifire"
        ),
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "repo_root", lambda: _doctor_root(tmp_path))
    monkeypatch.setattr(cli, "SessionLocal", _PassingSession)

    result = CliRunner().invoke(cli.app, ["doctor"])

    assert result.exit_code == 0, result.output
    assert "Configured postgresql database" in result.output
    assert sensitive_marker not in result.output
    assert "database.example.test" not in result.output


def test_doctor_hides_database_url_and_exception_when_connection_fails(
    monkeypatch,
    tmp_path: Path,
) -> None:
    marker = "doctor-error-detail-must-not-appear"
    settings = Settings(
        env="test",
        database_url=(
            "postgresql+psycopg://diagnostic_user:"
            f"{marker}@database.example.test:5432/classifire"
        ),
    )

    def unavailable_session() -> None:
        raise RuntimeError(f"connection failed for {marker}")

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "repo_root", lambda: _doctor_root(tmp_path))
    monkeypatch.setattr(cli, "SessionLocal", unavailable_session)

    result = CliRunner().invoke(cli.app, ["doctor"])

    assert result.exit_code == 1
    assert "Connection failed (details withheld)" in result.output
    assert marker not in result.output
    assert "database.example.test" not in result.output


def test_database_diagnostic_hides_invalid_database_url() -> None:
    marker = "invalid-database-url-must-not-appear"

    detail = cli._database_diagnostic(f"not-a-database-url-{marker}")

    assert detail == "Configured database (invalid URL)"
    assert marker not in detail
