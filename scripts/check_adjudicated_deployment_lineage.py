"""Report whether the configured database matches the reviewed clean migration head."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.engine import make_url

from classifire.config import get_settings
from classifire.db import SessionLocal
from classifire.services.deployment_lineage import assess_deployment_lineage


def _safe_target() -> str:
    url = make_url(get_settings().database_url)
    if url.get_backend_name() == "sqlite":
        database = Path(url.database or "")
        if not database.is_absolute():
            database = Path.cwd() / database
        return str(database.resolve())
    host = url.host or "<local>"
    port = f":{url.port}" if url.port is not None else ""
    return f"{url.drivername}://{host}{port}/{url.database or ''}"


def main() -> int:
    try:
        with SessionLocal() as db:
            result = assess_deployment_lineage(db)
    except Exception:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "code": "DEPLOYMENT_DATABASE_UNAVAILABLE",
                    "database_write_performed": False,
                },
                sort_keys=True,
            )
        )
        return 2
    output = {**result.as_dict(), "configured_target": _safe_target()}
    print(json.dumps(output, sort_keys=True))
    return 0 if result.status == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
