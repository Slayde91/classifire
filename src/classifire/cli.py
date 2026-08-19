from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
import uvicorn
from rich.console import Console
from rich.table import Table
from sqlalchemy import func, select

from . import __version__
from . import canonical_models as _canonical_models  # noqa: F401
from . import commercial_models as _commercial_models  # noqa: F401
from .agent_security import AGENT_SCOPE_MAP, provision_agent_principal
from .audit import record_audit
from .config import get_settings
from .db import Base, SessionLocal, engine
from .importers import import_pricing_library, import_technical_variants, seed_database
from .mission_control import MissionControlClient, bootstrap_mission_control
from .models import AgentServicePrincipal, PricingLibraryRecord, Product, TechnicalVariant, User
from .security import hash_password
from .services.adjudicated_admission_registration import (
    OfflineAdmissionRegistrationError,
    read_admission_manifest,
    read_preflight_receipt,
    register_offline_adjudicated_admission,
)
from .services.adjudicated_physical_submission import ControlledPhysicalSubmissionError

app = typer.Typer(help="CLASSIFIRE administration, import, run and integration commands.", no_args_is_help=True)
console = Console()


def repo_root() -> Path:
    candidates = [Path.cwd(), Path(__file__).resolve().parents[2]]
    for candidate in candidates:
        if (candidate / "pyproject.toml").exists():
            return candidate
    return Path.cwd()


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
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        result = seed_database(db, settings)
    console.print("[green]Database initialised.[/green]")
    console.print_json(data=result)


@app.command("create-admin")
def create_admin(
    email: str = typer.Option(..., prompt=True),
    full_name: str = typer.Option("CLASSIFIRE Administrator"),
    password: str = typer.Option(..., prompt=True, hide_input=True, confirmation_prompt=True),
) -> None:
    """Create or reset an administrator account."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email.lower()))
        if user:
            user.password_hash = hash_password(password)
            user.full_name = full_name
            user.role = "administrator"
            user.is_active = True
        else:
            user = User(
                email=email.lower(),
                full_name=full_name,
                password_hash=hash_password(password),
                role="administrator",
                is_active=True,
            )
            db.add(user)
        db.commit()
    console.print(f"[green]Administrator ready:[/green] {email.lower()}")


@app.command("provision-agent-tokens")
def provision_agent_tokens(
    output: Path = typer.Option(
        Path.home() / ".openclaw" / "classifire-agent-tokens.json",
        "--output",
        help="Local secret file consumed by the CLASSIFIRE OpenClaw plugin.",
    ),
    rotate: bool = typer.Option(
        False,
        "--rotate",
        help="Rotate existing agent credentials. Existing plaintext tokens become invalid immediately.",
    ),
) -> None:
    """Provision role-limited machine credentials for the nine cf-* agents."""
    Base.metadata.create_all(bind=engine)
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        existing = {
            item.agent_id
            for item in db.scalars(select(AgentServicePrincipal)).all()
            if item.agent_id in AGENT_SCOPE_MAP
        }
        if existing and not rotate:
            names = ", ".join(sorted(existing))
            raise typer.BadParameter(
                "Agent credentials already exist for: " + names + ". Use --rotate to replace them."
            )

        tokens: dict[str, str] = {}
        scopes: dict[str, list[str]] = {}
        for agent_id in sorted(AGENT_SCOPE_MAP):
            principal, token = provision_agent_principal(
                db,
                agent_id=agent_id,
                display_name=agent_id,
            )
            tokens[agent_id] = token
            scopes[agent_id] = list(principal.scopes or [])
            record_audit(
                db,
                actor=None,
                actor_type="system",
                actor_name="CLASSIFIRE agent credential provisioner",
                action="provision_agent_service_token",
                entity_type="agent_service_principal",
                entity_id=principal.id,
                new_value={
                    "agent_id": agent_id,
                    "token_hint": principal.token_hint,
                    "scopes": principal.scopes,
                    "rotated": agent_id in existing,
                },
                reason="Provision role-limited OpenClaw service credential",
            )
        db.commit()

    payload = {
        "schema": "CLASSIFIRE-AGENT-TOKENS-v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": "http://127.0.0.1:8787",
        "tokens": tokens,
        "scopes": scopes,
    }
    temp = output.with_suffix(output.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        os.chmod(temp, 0o600)
    except OSError:
        pass
    temp.replace(output)
    try:
        os.chmod(output, 0o600)
    except OSError:
        pass

    console.print(f"[green]Provisioned {len(tokens)} CLASSIFIRE agent credentials.[/green]")
    console.print(f"Secret token file: {output}")
    console.print("[yellow]Tokens are not printed. Protect this file and never commit it.[/yellow]")


def _offline_admission_registration_failure(code: str) -> None:
    """Return a machine-readable, no-write result for this local command."""

    console.print_json(
        data={
            "schema": "CLASSIFIRE-OFFLINE-ADMISSION-REGISTRATION-v1",
            "status": "BLOCKED",
            "code": code,
            "canonical_write_performed": False,
            "physical_model_lock_created": False,
            "gateway_call_performed": False,
        }
    )
    raise typer.Exit(code=2)


@app.command("register-adjudicated-admission")
def register_adjudicated_admission_command(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Signed admission manifest JSON. The command never accepts private signing keys.",
    ),
    preflight_receipt: Path = typer.Option(
        ...,
        "--preflight-receipt",
        help="Fresh no-write canonicalisation preflight receipt JSON.",
    ),
    operator_reference: str = typer.Option(
        ...,
        "--operator-reference",
        help="Human change-control or approval reference retained in the audit trail.",
    ),
    confirm: bool = typer.Option(
        False,
        "--confirm",
        help="Required confirmation to record the admission only; no model or lock is created.",
    ),
) -> None:
    """Verify and journal a signed admission without submitting a model or lock."""

    if not confirm:
        _offline_admission_registration_failure(
            "ADMISSION_REGISTRATION_CONFIRMATION_REQUIRED"
        )
    try:
        settings = get_settings()
    except Exception:
        _offline_admission_registration_failure("ADMISSION_REGISTRATION_CONFIGURATION_UNAVAILABLE")
    if not settings.adjudicated_initial_submission_enabled:
        _offline_admission_registration_failure("ADMISSION_REGISTRATION_DISABLED")
    if (
        not settings.adjudicated_admission_public_keys
        or not settings.adjudicated_admission_issuer_key_ids
    ):
        _offline_admission_registration_failure("ADMISSION_REGISTRATION_CONFIGURATION_INCOMPLETE")

    try:
        manifest_bytes = read_admission_manifest(manifest)
        preflight_receipt_bytes = read_preflight_receipt(preflight_receipt)
    except OfflineAdmissionRegistrationError as exc:
        _offline_admission_registration_failure(exc.code)

    with SessionLocal() as db:
        try:
            result = register_offline_adjudicated_admission(
                db,
                manifest_bytes=manifest_bytes,
                preflight_receipt_bytes=preflight_receipt_bytes,
                operator_reference=operator_reference,
                pinned_public_keys=settings.adjudicated_admission_public_keys,
                issuer_key_ids=settings.adjudicated_admission_issuer_key_ids,
                max_admission_ttl_seconds=settings.adjudicated_admission_max_ttl_seconds,
            )
        except (ControlledPhysicalSubmissionError, OfflineAdmissionRegistrationError) as exc:
            db.rollback()
            _offline_admission_registration_failure(exc.code)
        except Exception:
            db.rollback()
            _offline_admission_registration_failure("ADMISSION_REGISTRATION_PERSISTENCE_FAILED")

    response = result.as_dict()
    response["next_action"] = (
        "Admission recorded only. A separate fresh explicit authorization is required before "
        "the controlled writer may submit a canonical model."
    )
    console.print_json(data=response)


@app.command("import-pricing")
def import_pricing(
    path: Path = typer.Argument(..., exists=True, readable=True),
    version: str = typer.Option("2.13"),
) -> None:
    """Import Package 14 into the editable versioned pricing database."""
    Base.metadata.create_all(bind=engine)
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
    Base.metadata.create_all(bind=engine)
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
    Base.metadata.create_all(bind=engine)
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

    run_forever(interval)


@app.command()
def doctor() -> None:
    """Run non-destructive environment, source and database checks."""
    settings = get_settings()
    root = repo_root()
    checks: list[tuple[str, str, str]] = []
    checks.append(("Python", sys.version.split()[0], "PASS" if sys.version_info >= (3, 11) else "FAIL"))
    checks.append(("Repository", str(root), "PASS" if (root / "pyproject.toml").exists() else "WARN"))
    logo = root / "assets/brand/classifire-logo-master.png"
    checks.append(("Approved CLASSIFIRE logo", str(logo), "PASS" if logo.exists() else "WARN"))
    p14 = root / "knowledge/source/v2.13/QUANTIFIRE_14_Pricing_Library_v2.13.csv"
    p15 = root / "knowledge/source/v2.13/QUANTIFIRE_17_Technical_System_Variants_v2.13.jsonl"
    calc = root / "knowledge/source/raw-calculator/Penetration Calculator.xlsb"
    for label, path in [("Package 14", p14), ("Package 15 variants", p15), ("Raw calculator", calc)]:
        checks.append((label, str(path), "PASS" if path.exists() else "BLOCKED"))
    try:
        with SessionLocal() as db:
            db.execute(select(1))
            users = db.scalar(select(func.count()).select_from(User)) or 0
            pricing = db.scalar(select(func.count()).select_from(PricingLibraryRecord)) or 0
            technical = db.scalar(select(func.count()).select_from(TechnicalVariant)) or 0
        checks.append(("Database", settings.database_url, "PASS"))
        checks.append(("Users", str(users), "PASS" if users else "WARN"))
        checks.append(("Pricing rows", str(pricing), "PASS" if pricing else "WARN"))
        checks.append(("Technical variants", str(technical), "PASS" if technical else "WARN"))
    except Exception as exc:
        checks.append(("Database", str(exc), "FAIL"))
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


if __name__ == "__main__":
    app()
