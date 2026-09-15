from __future__ import annotations

import json
from pathlib import Path

import pytest
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



@pytest.mark.parametrize("failure", [False, True])
def test_scanner_only_doctor_does_not_open_database_or_read_sources(monkeypatch, failure):
    from classifire.services import malware_scan

    marker = "private-scanner-host.example.test"
    settings = Settings(_env_file=None, env="test", clamav_host=marker, clamav_port=3311)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    def forbidden(*args):
        raise AssertionError("Scanner-only check must not touch database or source files")

    monkeypatch.setattr(cli, "SessionLocal", forbidden)
    monkeypatch.setattr(cli, "repo_root", forbidden)
    monkeypatch.setattr(cli, "_prepare_cli_write", forbidden)
    calls = []

    def status(*, host, port):
        calls.append((host, port))
        if failure:
            raise malware_scan.MalwareScanError("SCAN_UNAVAILABLE")
        return malware_scan.ScannerStatus(
            "ClamAV 1.5.4", "28108", "synthetic-date", "synthetic-time"
        )

    monkeypatch.setattr(malware_scan, "scanner_status", status)
    result = CliRunner().invoke(cli.app, ["doctor", "--scanner-only"])
    assert result.exit_code == int(failure), result.output
    value = json.loads(result.output)
    assert value["file_scanned"] is False
    assert marker not in result.output
    assert calls == [(marker, 3311)]
    if failure:
        assert value == {"error": "SCAN_UNAVAILABLE", "file_scanned": False}
    else:
        assert value["check"] == "scanner_reachability_and_signature_freshness"
        assert value["engine"] == "ClamAV 1.5.4"
        assert "not a malware-detection test" in value["limitation"]


def test_default_doctor_does_not_implicitly_contact_scanner(monkeypatch, tmp_path):
    from classifire.services import malware_scan

    def forbidden(**kwargs):
        raise AssertionError("Default doctor must not contact scanner")

    monkeypatch.setattr(malware_scan, "scanner_status", forbidden)
    monkeypatch.setattr(cli, "get_settings", lambda: Settings(_env_file=None, env="test"))
    monkeypatch.setattr(cli, "repo_root", lambda: _doctor_root(tmp_path))
    monkeypatch.setattr(cli, "SessionLocal", _PassingSession)
    result = CliRunner().invoke(cli.app, ["doctor"])
    assert result.exit_code == 0, result.output
