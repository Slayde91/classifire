from __future__ import annotations

import argparse
import json
import sys

from rich.console import Console
from rich.table import Table

from classifire.config import get_settings
from classifire.mission_control import MissionControlClient, baseline_task_statuses


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Show the seven controlled CLASSIFIRE Mission Control baseline tasks without exposing credentials."
    )
    parser.add_argument("--json", action="store_true", help="Print the compact status snapshot as JSON.")
    args = parser.parse_args()

    settings = get_settings()
    key = settings.mission_control_api_key
    if not key:
        print("Mission Control API key is not configured for CLASSIFIRE.", file=sys.stderr)
        return 2

    client = MissionControlClient(settings.mission_control_url, key)
    rows = baseline_task_statuses(client)

    if args.json:
        print(json.dumps(rows, indent=2, default=str))
        return 0

    table = Table("Task", "MC ID", "Assigned Agent", "Status", "Dispatch", "Outcome / Error", "Linkage")
    for row in rows:
        outcome = row.get("outcome") or row.get("error_message") or ""
        linkage = row.get("linkage") or {}
        linkage_text = ", ".join(f"{key}={value}" for key, value in linkage.items())
        table.add_row(
            str(row.get("task_id") or ""),
            str(row.get("mission_control_id") or "-"),
            str(row.get("assigned_to") or ""),
            str(row.get("status") or ""),
            str(row.get("dispatch_attempts") or 0),
            str(outcome),
            linkage_text,
        )

    Console().print(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
