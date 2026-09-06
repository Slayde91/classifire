"""Run the manual Draft Scope prototype on isolated synthetic local storage.

No existing application .env or project database is used. Reuse the printed
--data-dir to verify reopening after restart; only marked demo directories work.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
import tempfile
from pathlib import Path

DEMO_EMAIL = "scope-demo@example.test"
DEMO_PASSWORD = "synthetic-scope-demo-only"  # noqa: S105 - synthetic loopback demo account
MARKER = "classifire-draft-scope-demo.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--port", type=int, default=8796)
    parser.add_argument(
        "--client-demo",
        action="store_true",
        help="Enable synthetic signed-token MCP client proof on loopback only",
    )
    parser.add_argument(
        "--postgres-demo-port",
        type=int,
        help="Use loopback classifire_draft_pdf_demo database for PDF evidence",
    )
    parser.add_argument(
        "--postgres-demo-database",
        choices=(
            "classifire_draft_pdf_demo",
            "classifire_draft_pricing_demo",
            "classifire_draft_client_pricing_demo",
            "classifire_draft_defect_report_demo",
            "classifire_draft_xlsx_report_demo",
            "classifire_draft_import_demo",
        ),
        default="classifire_draft_pdf_demo",
        help="Choose a separately marked synthetic database",
    )
    parser.add_argument(
        "--clamav-port",
        type=int,
        default=13310,
        help="Loopback ClamD port for the PostgreSQL evidence demo",
    )
    parser.add_argument(
        "--seed-technical-library",
        action="store_true",
        help="Seed a labelled synthetic library in this isolated demo only",
    )
    parser.add_argument(
        "--seed-constraint-library",
        action="store_true",
        help="Seed the versioned synthetic measured-limit fixture in a new SQLite demo",
    )
    parser.add_argument(
        "--seed-service-size-library",
        action="store_true",
        help="Seed a separate synthetic outside-diameter fixture in a new SQLite demo",
    )
    args = parser.parse_args()
    named_database = args.postgres_demo_database != "classifire_draft_pdf_demo"
    if named_database and args.postgres_demo_port is None:
        parser.error("The named demo database requires an explicit loopback PostgreSQL port")
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a local port from 1024 to 65535")
    if args.postgres_demo_port is not None and not 1024 <= args.postgres_demo_port <= 65535:
        parser.error("Choose a loopback PostgreSQL demo port from 1024 to 65535")
    if not 1024 <= args.clamav_port <= 65535:
        parser.error("Choose a loopback scanner port from 1024 to 65535")
    task_dir = (
        args.data_dir.expanduser().resolve()
        if args.data_dir
        else Path(tempfile.mkdtemp(prefix="classifire-scope-demo-"))
    )
    task_dir.mkdir(parents=True, exist_ok=True)
    marker = task_dir / MARKER
    if marker.exists():
        if marker.is_symlink() or marker.stat().st_size > 4096:
            parser.error("Invalid demo directory marker")
        config = json.loads(marker.read_text(encoding="utf-8"))
        expected_keys = {"kind", "session_key"} | (
            {"postgres_port"} if args.postgres_demo_port is not None else set()
        )
        if named_database:
            expected_keys.add("postgres_database")
        if (
            set(config) != expected_keys
            or config.get("postgres_database")
            != (args.postgres_demo_database if named_database else None)
            or config["kind"] != "synthetic-scope-demo-v1"
            or config.get("postgres_port") != args.postgres_demo_port
        ):
            parser.error("This is not a Draft Scope demo directory")
        session_key = config["session_key"]
        if not isinstance(session_key, str) or len(session_key) < 32:
            parser.error("Invalid demo session key")
    else:
        if any(task_dir.iterdir()):
            parser.error("Use a new empty directory; existing application data is never adopted")
        session_key = secrets.token_urlsafe(48)
        marker.write_text(
            json.dumps(
                {
                    **(
                        {"postgres_database": args.postgres_demo_database} if named_database else {}
                    ),
                    "kind": "synthetic-scope-demo-v1",
                    "session_key": session_key,
                    **(
                        {"postgres_port": args.postgres_demo_port}
                        if args.postgres_demo_port is not None
                        else {}
                    ),
                }
            ),
            encoding="utf-8",
        )
    if any((task_dir / name).is_symlink() for name in ("demo.sqlite3", "storage", ".env")):
        parser.error("Demo storage must not contain symbolic links")
    if (task_dir / ".env").exists():
        parser.error("The demo directory must not contain an application .env")
    source = Path(__file__).resolve().parents[1] / "src"
    sys.path.insert(0, str(source))
    os.chdir(task_dir)
    database_url = (
        "postgresql+psycopg://classifire_test@127.0.0.1:"
        + str(args.postgres_demo_port)
        + "/"
        + args.postgres_demo_database
        if args.postgres_demo_port is not None
        else "sqlite:///" + (task_dir / "demo.sqlite3").as_posix()
    )
    os.environ.update(
        {
            "CLASSIFIRE_ENV": "test",
            "CLASSIFIRE_DATABASE_URL": database_url,
            "CLASSIFIRE_STORAGE_ROOT": str(task_dir / "storage"),
            "CLASSIFIRE_SECRET_KEY": session_key,
            "CLASSIFIRE_SESSION_HTTPS_ONLY": "false",
            "CLASSIFIRE_TRUSTED_HOSTS": '["127.0.0.1", "localhost"]',
            "CLASSIFIRE_ALLOWED_ORIGINS": '["http://127.0.0.1:' + str(args.port) + '"]',
        }
    )
    if args.postgres_demo_port is not None:
        os.environ["CLASSIFIRE_CLAMAV_HOST"] = "127.0.0.1"
        os.environ["CLASSIFIRE_CLAMAV_PORT"] = str(args.clamav_port)
    if args.client_demo:
        os.environ["CLASSIFIRE_DRAFT_CLIENT_CONFIG"] = str(
            task_dir / "synthetic-client-policy.json"
        )
    else:
        os.environ.pop("CLASSIFIRE_DRAFT_CLIENT_CONFIG", None)
    import uvicorn
    from sqlalchemy import inspect, select, text

    from classifire import physical_models  # noqa: F401 - register canonical schema
    from classifire.db import Base, SessionLocal, engine
    from classifire.models import User
    from classifire.security import hash_password

    if args.postgres_demo_port is not None:
        # Never adopt an existing project database. A marker binds this disposable
        # database to the explicitly selected synthetic directory across restarts.
        token = hashlib.sha256(session_key.encode("utf-8")).hexdigest()
        with engine.begin() as connection:
            tables = set(inspect(connection).get_table_names())
            if "classifire_demo_guard" in tables:
                if connection.scalar(text("SELECT token FROM classifire_demo_guard")) != token:
                    parser.error("The PostgreSQL demo belongs to a different synthetic directory")
            elif tables:
                parser.error("Refusing an unmarked nonempty PostgreSQL database")
            else:
                connection.execute(
                    text("CREATE TABLE classifire_demo_guard (token VARCHAR(64) NOT NULL)")
                )
                connection.execute(
                    text("INSERT INTO classifire_demo_guard (token) VALUES (:token)"),
                    {"token": token},
                )
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.scalar(select(User.id).limit(1)) is None:
            db.add(
                User(
                    email=DEMO_EMAIL,
                    full_name="Synthetic Scope Demo",
                    password_hash=hash_password(DEMO_PASSWORD),
                    role="administrator",
                    is_active=True,
                )
            )
            db.commit()
        if (
            args.seed_technical_library
            or args.seed_constraint_library
            or args.seed_service_size_library
        ):
            from draft_system_match_demo_fixture import seed_demo_library

            actor = db.scalar(select(User).where(User.email == DEMO_EMAIL))
            if actor is None:
                parser.error("The synthetic demo administrator is missing")
            release = seed_demo_library(
                db,
                task_dir / "storage",
                actor,
                constraints=args.seed_constraint_library,
                service_size=args.seed_service_size_library,
            )
            db.commit()
            print(f"Synthetic technical release: {release.version} ({release.id})", flush=True)
    if args.client_demo:
        # This fixture issues a local test token, not a production OAuth authorization flow.
        import time

        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa

        from classifire.draft_client_auth import ESTIMATE, EXPORT, READ, TECHNICAL, WRITE

        with SessionLocal() as db:
            actor = db.scalar(select(User).where(User.email == DEMO_EMAIL))
            if actor is None:
                parser.error("Synthetic demo account is missing")
            user_id = actor.id
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
        public.update(alg="RS256", use="sig", kid="synthetic-local")
        origin = f"http://127.0.0.1:{args.port}"
        policy = {
            "base_url": origin,
            "issuer": origin,
            "public_keys": {"synthetic-local": public},
            "subjects": {"synthetic-human": user_id},
            "clients": {"synthetic-client": [READ, WRITE, EXPORT, TECHNICAL, ESTIMATE]},
        }
        policy_path = task_dir / "synthetic-client-policy.json"
        token_path = task_dir / "synthetic-client-token.txt"
        if policy_path.is_symlink() or token_path.is_symlink():
            parser.error("Client demo files must not be symbolic links")
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        now = int(time.time())
        token = jwt.encode(
            {
                "iss": origin,
                "aud": origin + "/mcp",
                "sub": "synthetic-human",
                "client_id": "synthetic-client",
                "jti": secrets.token_urlsafe(24),
                "iat": now,
                "nbf": now,
                "exp": now + 900,
                "scope": " ".join([READ, WRITE, EXPORT, TECHNICAL, ESTIMATE]),
            },
            key,
            algorithm="RS256",
            headers={"kid": "synthetic-local", "typ": "at+jwt"},
        )
        token_path.write_text(token, encoding="utf-8")
        os.environ["CLASSIFIRE_DRAFT_CLIENT_CONFIG"] = str(policy_path)
        print(
            "Synthetic MCP enabled; local token expires in 15 minutes. No real OAuth link.",
            flush=True,
        )
    else:
        os.environ.pop("CLASSIFIRE_DRAFT_CLIENT_CONFIG", None)
    print(f"Synthetic local prototype: http://127.0.0.1:{args.port}/scopes", flush=True)
    print(f"Demo login: {DEMO_EMAIL} / {DEMO_PASSWORD}", flush=True)
    print(f"Data directory (reuse after restart): {task_dir}", flush=True)
    print(
        "Synthetic/manual Draft data only. No provider or operational release is invoked.",
        flush=True,
    )
    uvicorn.run("classifire.main:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
