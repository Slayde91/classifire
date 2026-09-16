"""Deterministic, escaped Draft work report from one already validated saved record."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape


def render_work_report(record: dict[str, Any]) -> bytes:
    root = Path(__file__).resolve().parents[1]
    environment = Environment(
        loader=FileSystemLoader(root / "templates"),
        autoescape=select_autoescape(("html",)),
    )
    logo = base64.b64encode(
        (root / "static" / "brand" / "classifire-logo.png").read_bytes()
    ).decode("ascii")
    return (
        environment.get_template("draft_work_record_report.html")
        .render(
            record=record,
            logo_base64=logo,
        )
        .encode("utf-8")
    )
