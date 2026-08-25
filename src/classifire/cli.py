from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import typer
import uvicorn
from rich.console import Console
from rich.table import Table
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from . import (
    __version__,
    physical_models,  # noqa: F401
)
from .audit import record_audit
from .config import get_settings
from .db import SessionLocal, engine
from .importers import import_pricing_library, import_technical_variants, seed_database
from .mission_control import MissionControlClient, bootstrap_mission_control
from .models import PricingLibraryRecord, Product, TechnicalVariant, User
from .security import (
    hash_password,
    revoke_all_human_sessions,
    update_user_security,
)
from .services.adjudicated_admission import AdmissionVerificationError, admission_identity
from .services.adjudicated_admission_registration import (
    AdmissionRegistrationError,
    register_verified_admission_from_preflight,
)
from .services.adjudicated_key_policy import (
    AdjudicatedKeyPolicyError,
    resolve_adjudicated_public_key,
)
from .services.schema_bootstrap import (
    SchemaBootstrapError,
    prepare_application_schema,
)

app = typer.Typer(help="CLASSIFIRE administration, import, run and integration commands.", no_args_is_help=True)
console = Console()


def repo_root() -> Path:
    candidates = [Path.cwd(), Path(__file__).resolve().parents[2]]
    for candidate in candidates:
        if (candidate / "pyproject.toml").exists():
            return candidate
    return Path.cwd()


def _required_cli_text(value: str, *, option_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise typer.BadParameter(f"{option_name} must not be blank")
    return normalized


def _prepare_database_schema() -> None:
    settings = get_settings()
    try:
        prepare_application_schema(engine, settings.env)
    except SchemaBootstrapError as exc:
        raise typer.BadParameter(str(exc)) from exc


def _database_identity(database_url: str) -> str:
    """Return only the configured driver name, never URL authority or query data."""

    try:
        parsed = make_url(database_url)
    except ArgumentError:
        return "configured database"
    return f"{parsed.drivername} database"


def _sqlite_sidecars(database_path: Path) -> tuple[Path, ...]:
    return tuple(
        Path(f"{database_path}{suffix}")
        for suffix in ("-journal", "-shm", "-wal")
    )


def _require_closed_sqlite_state(database_path: Path) -> None:
    for sidecar_path in _sqlite_sidecars(database_path):
        try:
            sidecar_path.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise SchemaBootstrapError(
                "SQLITE_DIAGNOSTIC_SIDECAR_INSPECTION_FAILED",
                "SQLite sidecar state could not be verified; immutable inspection "
                "was not started",
            ) from exc
        raise SchemaBootstrapError(
            "SQLITE_DIAGNOSTIC_SIDECAR_PRESENT",
            "immutable inspection requires a closed, checkpointed SQLite database; "
            "do not remove journal, SHM or WAL files manually",
        )


def _sqlite_file_identity(database_path: Path) -> tuple[int, int, int, int]:
    state = database_path.stat()
    return (state.st_dev, state.st_ino, state.st_size, state.st_mtime_ns)


@contextmanager
def _doctor_database_engine(bind: Engine) -> Iterator[Engine]:
    """Yield a diagnostic engine that cannot trigger SQLite write pragmas."""

    database = bind.url.database
    if bind.dialect.name != "sqlite" or database in {None, "", ":memory:"}:
        yield bind
        return

    database_path = Path(str(database)).resolve()
    _require_closed_sqlite_state(database_path)
    before_identity = _sqlite_file_identity(database_path)
    read_only_uri = f"{database_path.as_uri()}?mode=ro&immutable=1"

    def connect_read_only() -> sqlite3.Connection:
        _require_closed_sqlite_state(database_path)
        connection = sqlite3.connect(
            read_only_uri,
            uri=True,
            check_same_thread=False,
        )
        try:
            _require_closed_sqlite_state(database_path)
        except Exception:
            connection.close()
            raise
        return connection

    diagnostic_engine = create_engine(
        "sqlite+pysqlite://",
        creator=connect_read_only,
        future=True,
        poolclass=NullPool,
    )
    try:
        yield diagnostic_engine
    finally:
        diagnostic_engine.dispose()
        _require_closed_sqlite_state(database_path)
        if _sqlite_file_identity(database_path) != before_identity:
            raise SchemaBootstrapError(
                "SQLITE_DIAGNOSTIC_RACE_DETECTED",
                "SQLite database changed during immutable inspection; retry only "
                "after all writers are stopped",
            )


@app.command()
def version() -> None:
    """Print the installed CLASSIFIRE version."""
    console.print(f"CLASSIFIRE {__version__}")


@app.command("init")
def init_database() -> None:
    """Create database tables and seed controlled defaults."""
    settings = get_settings()
    findings = settings.validate_production()
    if findings:
        console.print("[yellow]Production configuration findings:[/yellow]")
        for item in findings:
            console.print(f"  - {item}")
    _prepare_database_schema()
    with SessionLocal() as db:
        result = seed_database(db, settings)
    console.print("[green]Database initialised.[/green]")
    console.print_json(data=result)


@app.command("create-admin")
def create_admin(
    email: str = typer.Option(..., prompt=True),
    full_name: str = typer.Option("CLASSIFIRE Administrator"),
    password: str = typer.Option(..., prompt=True, hide_input=True, confirmation_prompt=True),
    operator_reference: str = typer.Option(
        ...,
        "--operator-reference",
        help="Auditable identity or change reference for this administrator operation.",
    ),
) -> None:
    """Create an administrator or reset one while revoking all prior sessions."""

    email_address = _required_cli_text(email, option_name="--email").lower()
    operator = _required_cli_text(
        operator_reference,
        option_name="--operator-reference",
    )
    _prepare_database_schema()
    password_digest = hash_password(password)
    reset_existing = False
    revoked_count = 0
    with SessionLocal() as db:
        user = db.scalar(
            select(User)
            .where(User.email == email_address)
            .with_for_update()
        )
        if user:
            reset_existing = True
            revoked_count = update_user_security(
                db,
                user,
                actor=None,
                reason="Administrator credential reset and reactivation",
                actor_name=operator,
                password_hash=password_digest,
                full_name=full_name,
                role="administrator",
                is_active=True,
            )
        else:
            user = User(
                email=email_address,
                full_name=full_name,
                password_hash=password_digest,
                role="administrator",
                is_active=True,
            )
            db.add(user)
            db.flush()
            record_audit(
                db,
                actor=None,
                actor_type="system",
                actor_name=operator,
                action="create_administrator",
                entity_type="user",
                entity_id=user.id,
                new_value={
                    "email": email_address,
                    "full_name": full_name,
                    "role": "administrator",
                    "is_active": True,
                },
                reason="Administrator account created",
            )
        db.commit()
    if reset_existing:
        console.print(
            "[green]Administrator reset and prior sessions revoked:[/green] "
            f"{email_address} ({revoked_count} active session(s))"
        )
    else:
        console.print(f"[green]Administrator created:[/green] {email_address}")


@app.command("revoke-user-sessions")
def revoke_user_sessions(
    email: str = typer.Option(..., "--email"),
    reason: str = typer.Option(
        ...,
        "--reason",
        help="Auditable reason for revoking every current human session.",
    ),
    operator_reference: str = typer.Option(
        ...,
        "--operator-reference",
        help="Auditable identity or change reference for this revocation.",
    ),
) -> None:
    """Permanently revoke every currently issued session for one human user."""

    email_address = _required_cli_text(email, option_name="--email").lower()
    audit_reason = _required_cli_text(reason, option_name="--reason")
    operator = _required_cli_text(
        operator_reference,
        option_name="--operator-reference",
    )
    _prepare_database_schema()
    with SessionLocal() as db:
        user = db.scalar(
            select(User)
            .where(User.email == email_address)
            .with_for_update()
        )
        if user is None:
            raise typer.BadParameter("No user exists for --email")
        revoked_count = revoke_all_human_sessions(
            db,
            user,
            actor=None,
            reason=audit_reason,
            actor_name=operator,
        )
        db.commit()
    console.print(
        "[green]All human sessions revoked:[/green] "
        f"{email_address} ({revoked_count} active session(s))"
    )


@app.command("import-pricing")
def import_pricing(
    path: Path = typer.Argument(..., exists=True, readable=True),
    version: str = typer.Option("2.13"),
) -> None:
    """Import Package 14 into the editable versioned pricing database."""
    _prepare_database_schema()
    with SessionLocal() as db:
        seed_database(db, get_settings())
        result = import_pricing_library(db, path, version=version)
    console.print_json(data=result)


@app.command("import-technical")
def import_technical(
    path: Path = typer.Argument(..., exists=True, readable=True),
    version: str = typer.Option("2.13"),
) -> None:
    """Import Package 15 executable variants into the technical database."""
    _prepare_database_schema()
    with SessionLocal() as db:
        seed_database(db, get_settings())
        result = import_technical_variants(db, path, version=version)
    console.print_json(data=result)


@app.command("import-supplied-v213")
def import_supplied_v213(source_root: Optional[Path] = None) -> None:
    """Import the supplied v2.13 pricing and technical libraries."""
    root = source_root or repo_root() / "knowledge" / "source" / "v2.13"
    pricing = root / "QUANTIFIRE_14_Pricing_Library_v2.13.csv"
    technical = root / "QUANTIFIRE_17_Technical_System_Variants_v2.13.jsonl"
    missing = [str(path) for path in (pricing, technical) if not path.exists()]
    if missing:
        raise typer.BadParameter(f"Missing supplied source file(s): {missing}")
    _prepare_database_schema()
    with SessionLocal() as db:
        seed_database(db, get_settings())
        p = import_pricing_library(db, pricing, version="2.13")
        t = import_technical_variants(db, technical, version="2.13")
    console.print("[green]Supplied v2.13 libraries imported.[/green]")
    console.print_json(data={"pricing": p, "technical": t})


@app.command()
def start(
    host: Optional[str] = typer.Option(None),
    port: Optional[int] = typer.Option(None),
    reload: bool = typer.Option(False),
) -> None:
    """Start the CLASSIFIRE application."""
    settings = get_settings()
    uvicorn.run(
        "classifire.main:app",
        host=host or settings.host,
        port=port or settings.port,
        reload=reload,
        log_level="info",
    )


@app.command()
def worker(interval: float = typer.Option(2.0)) -> None:
    """Run the background job worker."""
    from .worker import run_forever

    _prepare_database_schema()
    run_forever(interval)


@app.command()
def doctor() -> None:
    """Run non-destructive environment, source and database checks."""
    settings = get_settings()
    root = repo_root()
    checks: list[tuple[str, str, str]] = []
    checks.append(("Python", sys.version.split()[0], "PASS" if sys.version_info >= (3, 11) else "FAIL"))
    checks.append(("Repository", str(root), "PASS" if (root / "pyproject.toml").exists() else "WARN"))
    checks.append(("Approved logo", str(root / "assets/brand/quantifire-logo-master.png"), "PASS" if (root / "assets/brand/quantifire-logo-master.png").exists() else "FAIL"))
    p14 = root / "knowledge/source/v2.13/QUANTIFIRE_14_Pricing_Library_v2.13.csv"
    p15 = root / "knowledge/source/v2.13/QUANTIFIRE_17_Technical_System_Variants_v2.13.jsonl"
    calc = root / "knowledge/source/raw-calculator/Penetration Calculator.xlsb"
    for label, path in [("Package 14", p14), ("Package 15 variants", p15), ("Raw calculator", calc)]:
        checks.append((label, str(path), "PASS" if path.exists() else "BLOCKED"))
    display_database_identity = _database_identity(settings.database_url)
    try:
        with _doctor_database_engine(engine) as diagnostic_engine:
            preparation = prepare_application_schema(
                diagnostic_engine,
                settings.env,
                create_empty=False,
            )
            with Session(diagnostic_engine) as db:
                db.execute(select(1))
                users = db.scalar(select(func.count()).select_from(User)) or 0
                pricing = db.scalar(select(func.count()).select_from(PricingLibraryRecord)) or 0
                technical = db.scalar(select(func.count()).select_from(TechnicalVariant)) or 0
        checks.append(
            (
                "Database",
                f"{display_database_identity} ({preparation.code})",
                "PASS",
            )
        )
        checks.append(("Users", str(users), "PASS" if users else "WARN"))
        checks.append(("Pricing rows", str(pricing), "PASS" if pricing else "WARN"))
        checks.append(("Technical variants", str(technical), "PASS" if technical else "WARN"))
    except Exception as exc:
        failure = str(exc) if isinstance(exc, SchemaBootstrapError) else type(exc).__name__
        checks.append(("Database", f"{display_database_identity} ({failure})", "FAIL"))
    for finding in settings.validate_production():
        checks.append(("Production config", finding, "WARN"))
    table = Table("Check", "Detail", "Result")
    for item in checks:
        table.add_row(*item)
    console.print(table)
    if any(result == "FAIL" for _, _, result in checks):
        raise typer.Exit(1)


@app.command("mission-control-bootstrap")
def mission_control_bootstrap(
    url: Optional[str] = typer.Option(None),
    api_key: Optional[str] = typer.Option(None, envvar="CLASSIFIRE_MISSION_CONTROL_API_KEY"),
    repo_url: str = typer.Option("https://github.com/Slayde91/classifire"),
    create_tasks: bool = typer.Option(
        False,
        "--create-tasks",
        help="Also seed baseline architecture tasks. Default is agent registration only.",
    ),
) -> None:
    """Register CLASSIFIRE agent records in Mission Control; task seeding is opt-in."""
    settings = get_settings()
    key = api_key or settings.mission_control_api_key
    if not key:
        raise typer.BadParameter("Mission Control API key is required")
    client = MissionControlClient(url or settings.mission_control_url, key)
    registry = repo_root() / "mission-control" / "architecture-registry.yaml"
    result = bootstrap_mission_control(
        client,
        repo_url=repo_url,
        architecture_registry=registry,
        create_tasks=create_tasks,
    )
    console.print_json(data=result)


@app.command("branding-audit")
def branding_audit() -> None:
    """Run the repository branding compliance scanner."""
    script = repo_root() / "scripts" / "branding_audit.py"
    raise typer.Exit(subprocess.call([sys.executable, str(script), str(repo_root())]))


@app.command("source-hashes")
def source_hashes() -> None:
    """Regenerate the immutable source hash manifest."""
    root = repo_root()
    sources = root / "knowledge" / "source"
    rows = []
    for path in sorted(p for p in sources.rglob("*") if p.is_file()):
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        rows.append({"path": path.relative_to(root).as_posix(), "size": path.stat().st_size, "sha256": digest.hexdigest()})
    output = root / "knowledge" / "SOURCE_SHA256_MANIFEST.json"
    output.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    console.print(f"[green]Wrote {len(rows)} source hashes:[/green] {output}")


@app.command("register-adjudicated-admission")
def register_adjudicated_admission(
    manifest_path: Path = typer.Argument(..., exists=True, readable=True),
    preflight_receipt_path: Path = typer.Argument(..., exists=True, readable=True),
    operator_reference: str = typer.Option(..., "--operator-reference"),
) -> None:
    """Register one verified admission without a canonical write or physical lock."""
    settings = get_settings()
    if not settings.adjudicated_initial_submission_enabled:
        raise typer.BadParameter("ADJUDICATED_SUBMISSION_DISABLED")

    manifest = manifest_path.read_bytes()
    preflight_receipt = preflight_receipt_path.read_bytes()
    try:
        issuer, key_id = admission_identity(manifest)
        pinned_public_key = resolve_adjudicated_public_key(
            enabled=settings.adjudicated_initial_submission_enabled,
            public_keys=settings.adjudicated_admission_public_keys,
            issuer_key_ids=settings.adjudicated_admission_issuer_key_ids,
            issuer=issuer,
            key_id=key_id,
        )
        with SessionLocal() as db:
            admission, created = register_verified_admission_from_preflight(
                db,
                manifest=manifest,
                preflight_receipt=preflight_receipt,
                pinned_public_key=pinned_public_key,
                expected_issuer=issuer,
                expected_key_id=key_id,
                operator_reference=operator_reference,
            )
            db.commit()
    except (
        AdmissionRegistrationError,
        AdmissionVerificationError,
        AdjudicatedKeyPolicyError,
    ) as exc:
        raise typer.BadParameter(exc.code) from exc

    console.print_json(
        data={
            "admission_id": admission.admission_id,
            "state": admission.state,
            "issuer": admission.issuer_id,
            "key_id": admission.signing_key_id,
            "created": created,
            "canonical_write_performed": False,
            "physical_model_lock_created": False,
        }
    )


if __name__ == "__main__":
    app()
