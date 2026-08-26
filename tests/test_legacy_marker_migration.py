from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import String


def _load_migration_module(filename: str, module_name: str):
    path = Path(__file__).parents[1] / "migrations" / "versions" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_legacy_marker_module():
    return _load_migration_module(
        "0006_legacy_adjudicated_canonical_admissions.py",
        "legacy_adjudicated_marker",
    )


def _load_clean_journal_module():
    return _load_migration_module(
        "0005_adjudicated_admission_journal.py",
        "clean_adjudicated_journal",
    )


def _load_malware_attestation_module():
    return _load_migration_module(
        "0011_malware_scan_attestations.py",
        "malware_scan_attestations",
    )


def test_postgresql_marker_widens_alembic_revision_column() -> None:
    module = _load_legacy_marker_module()
    calls: list[tuple[tuple[object, ...], dict[str, Any]]] = []
    module.op = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
        alter_column=lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    module.upgrade()

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ("alembic_version", "version_num")
    assert isinstance(kwargs["existing_type"], String)
    assert kwargs["existing_type"].length == 32
    assert isinstance(kwargs["type_"], String)
    assert kwargs["type_"].length == 64
    assert kwargs["existing_nullable"] is False


def test_sqlite_marker_remains_schema_neutral() -> None:
    module = _load_legacy_marker_module()
    calls: list[tuple[tuple[object, ...], dict[str, Any]]] = []
    module.op = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="sqlite")),
        alter_column=lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    module.upgrade()

    assert calls == []


def test_marker_downgrade_never_narrows_revision_column() -> None:
    module = _load_legacy_marker_module()
    calls: list[tuple[tuple[object, ...], dict[str, Any]]] = []
    module.op = SimpleNamespace(
        alter_column=lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    module.downgrade()

    assert calls == []


def test_postgresql_clean_branch_widens_before_its_first_long_revision() -> None:
    module = _load_clean_journal_module()
    calls: list[tuple[tuple[object, ...], dict[str, Any]]] = []
    module.op = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
        alter_column=lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    module._table_names = lambda: {"physical_model_admissions"}

    module.upgrade()

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ("alembic_version", "version_num")
    assert isinstance(kwargs["existing_type"], String)
    assert kwargs["existing_type"].length == 32
    assert isinstance(kwargs["type_"], String)
    assert kwargs["type_"].length == 64
    assert kwargs["existing_nullable"] is False


def test_sqlite_clean_branch_does_not_change_alembic_revision_width() -> None:
    module = _load_clean_journal_module()
    calls: list[tuple[tuple[object, ...], dict[str, Any]]] = []
    module.op = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="sqlite")),
        alter_column=lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    module._table_names = lambda: {"physical_model_admissions"}

    module.upgrade()

    assert calls == []


def test_all_declared_revision_ids_fit_the_postgresql_width_contract() -> None:
    repository_root = Path(__file__).parents[1]
    config = Config(str(repository_root / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(repository_root / "migrations"),
    )
    revisions = [
        str(item.revision) for item in ScriptDirectory.from_config(config).walk_revisions()
    ]

    assert revisions
    assert max(map(len, revisions)) <= 64


def test_0011_rejects_unsupported_dialect_before_any_schema_or_data_operation() -> None:
    module = _load_malware_attestation_module()

    def forbidden_operation(*_args: object, **_kwargs: object) -> None:
        pytest.fail("0011 performed an operation before rejecting the dialect")

    module.op = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="mysql")),
        create_table=forbidden_operation,
        create_index=forbidden_operation,
        execute=forbidden_operation,
    )

    with pytest.raises(
        RuntimeError,
        match="append-only triggers support only SQLite and PostgreSQL",
    ):
        module.upgrade()
