"""Draft pricing workbook intake and explicit source-bound rate application."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess  # nosec B404
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy.orm import Session

from ..config import Settings
from ..models import DraftPricingSource, User
from . import draft_estimates as estimates
from .draft_estimate_contract import line_amount
from .draft_pricing_contract import preview_rows
from .draft_scope import DraftScopeError, _atomic
from .draft_source_intake import DraftSourceIntake, SourcePolicy

SCHEMA = "CLASSIFIRE-DRAFT-PRICING-XLSX-v1"


def _process(content: bytes) -> bytes:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}
    }
    environment.update(
        PYTHONPATH=str(Path(__file__).resolve().parents[2]),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONIOENCODING="utf-8",
    )
    try:
        result = subprocess.run(  # noqa: S603 # nosec B603
            [sys.executable, "-m", "classifire.services.draft_pricing_worker"],
            input=content,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
            env=environment,
        )
        if result.returncode != 0 or not 1 <= len(result.stdout) <= 2 * 1024 * 1024:
            raise ValueError("parser")
        value = json.loads(result.stdout)
        if (
            value["schema"] != SCHEMA
            or value["manifest"]["source_sha256"] != hashlib.sha256(content).hexdigest()
            or value["manifest"]["source_size_bytes"] != len(content)
            or not 1 <= len(value["sheets"]) <= 10
        ):
            raise ValueError("parser binding")
        return result.stdout
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError) as exc:
        raise DraftScopeError("PRICING_XLSX_PROCESSING_FAILED", 422) from exc


def intake() -> DraftSourceIntake:
    return DraftSourceIntake(
        SourcePolicy(
            model=DraftPricingSource,
            purpose="draft_pricing_xlsx",
            extension=".xlsx",
            magic=b"PK",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            schema=SCHEMA,
            code_prefix="PRICING_XLSX_",
            audit_name="draft_pricing",
            process=_process,
            valid_document=lambda value: 1 <= len(value["sheets"]) <= 10,
            read_permissions=("estimate:read", "library:read"),
            write_permissions=("estimate:write",),
        )
    )


def preview(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    sheet_index: int,
    header_row: int,
    mapping: dict[str, int | None],
    *,
    settings: Settings,
) -> tuple[DraftPricingSource, list[dict[str, Any]]]:
    source, document, _ = intake()._document(db, actor, draft_id, source_id, settings.storage_root)
    try:
        return cast(DraftPricingSource, source), preview_rows(
            document, sheet_index, header_row, mapping
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise DraftScopeError("PRICING_MAPPING_INVALID", 422) from exc


def apply_rate(
    db: Session,
    actor: User,
    draft_id: str,
    estimate_id: str,
    expected_revision: int,
    line_id: str,
    source_id: str,
    sheet_index: int,
    header_row: int,
    mapping: dict[str, int | None],
    row_number: int,
    expected_document_hash: str,
    expected_row_hash: str,
    recovery_note: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    with _atomic(db):
        actor, draft, estimate, prior = estimates._editable(
            db,
            actor,
            draft_id,
            estimate_id,
            expected_revision,
        )
        source, rows = preview(
            db, actor, draft_id, source_id, sheet_index, header_row, mapping, settings=settings
        )
        if source.document_sha256 != expected_document_hash:
            raise DraftScopeError("PRICING_SOURCE_CHANGED", 409)
        row = next((item for item in rows if item["row"] == row_number), None)
        if row is None or row["sha256"] != expected_row_hash:
            raise DraftScopeError("PRICING_ROW_CHANGED", 409)
        if row["problems"]:
            raise DraftScopeError("PRICING_RATE_UNRESOLVED", 422)
        envelope = copy.deepcopy(prior)
        line = estimates._line(envelope, line_id)
        if row["values"]["unit"] != line["unit"]:
            raise DraftScopeError("PRICING_UNIT_MISMATCH", 422)
        if type(recovery_note) is not str or not 1 <= len(recovery_note.strip()) <= 4000:
            raise DraftScopeError("PRICING_RECOVERY_NOTE_REQUIRED", 422)
        created = datetime.now(UTC)
        rate = row["values"]["rate"]
        event = estimates._event(
            actor,
            created,
            "override",
            line["quantity"],
            line["quantity"],
            line["unit_sell_rate"],
            rate,
            recovery_note,
        )
        line["history"].append(event)
        line["unit_sell_rate"] = rate
        line["subtotal_ex_tax"], line["pricing_status"] = line_amount(line)
        envelope["schema_version"] = "CLASSIFIRE-DRAFT-ESTIMATE-v2"
        envelope["provenance"] = "manual_and_workbook_unit_sell"
        envelope.setdefault("pricing_sources", []).append(
            {
                "line_id": line_id,
                "event_id": event["event_id"],
                "source_id": source.id,
                "source_sha256": source.source_sha256,
                "source_size_bytes": source.source_size_bytes,
                "original_filename": source.original_filename,
                "document_sha256": source.document_sha256,
                "scan_sha256": hashlib.sha256(
                    cast(str, source.scan_json).encode("utf-8")
                ).hexdigest(),
                "row": row,
                "method": "exact_library_rate",
                "approval_status": "unreviewed",
                "recovery_note": recovery_note,
            }
        )
        actor = intake()._actor(db, actor, write=True)
        return estimates._save(
            db, actor, draft, estimate, prior, envelope, "select_workbook_rate", created
        )


def pricing_staleness(
    db: Session, actor: User, draft_id: str, envelope: dict[str, Any], *, storage_root: Path
) -> list[str]:
    reasons = []
    checked = set()
    for ref in envelope.get("pricing_sources", []):
        key = (ref["source_id"], ref["document_sha256"], ref["scan_sha256"])
        if key in checked:
            continue
        checked.add(key)
        try:
            source, _, content = intake()._document(
                db, actor, draft_id, ref["source_id"], storage_root
            )
            if (
                content.sha256 != ref["source_sha256"]
                or source.document_sha256 != ref["document_sha256"]
                or hashlib.sha256(cast(str, source.scan_json).encode("utf-8")).hexdigest()
                != ref["scan_sha256"]
            ):
                reasons.append("PRICING_SOURCE_CHANGED")
        except DraftScopeError as exc:
            if exc.status_code == 403:
                raise
            reasons.append("PRICING_SOURCE_UNAVAILABLE")
    return list(dict.fromkeys(reasons))
