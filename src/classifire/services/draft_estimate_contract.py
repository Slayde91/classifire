"""Strict, deterministic manual unit-sell Draft Estimate artifact contract."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .calculation import money
from .draft_scope import validate_portable_artifact
from .draft_system_match_contract import canonical, digest, envelope_hash
from .draft_system_match_contract import validate_envelope as validate_match

SCHEMA_VERSION = "CLASSIFIRE-DRAFT-ESTIMATE-v1"
MAX_ESTIMATE_BYTES = 2 * 1024 * 1024
MAX_LINES = 100
MAX_HISTORY = 100
Identity = Annotated[str, Field(min_length=1, max_length=36)]
Note = Annotated[str, Field(max_length=4000)]
Number = Annotated[str, Field(max_length=16)]
TargetKind = Literal["service", "blank_opening"]
Unit = Literal["each", "m", "mm", "m2"]


class Contract(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class AddLine(Contract):
    target_kind: TargetKind
    target_id: Identity
    unit: Unit
    quantity: Number | None
    unit_sell_rate: Number | None
    description: Annotated[str, Field(min_length=1, max_length=500)]
    source_note: Annotated[str, Field(min_length=1, max_length=4000)]
    reason: Note


class Override(Contract):
    quantity: Number | None
    unit_sell_rate: Number | None
    reason: Annotated[str, Field(min_length=1, max_length=4000)]


class History(Contract):
    event_id: Identity
    action: Literal["added", "override", "omitted", "restored"]
    before_quantity: Annotated[str, Field(max_length=100)] | None
    quantity: Number | None
    before_rate: Number | None
    unit_sell_rate: Number | None
    reason: Note
    created_by: Identity
    created_at: Annotated[str, Field(max_length=40)]


class Line(Contract):
    line_id: Identity
    recovery_key: Annotated[str, Field(max_length=60)]
    target_kind: TargetKind
    target_id: Identity
    label: Annotated[str, Field(max_length=200)]
    opening_ids: Annotated[list[Identity], Field(max_length=500)]
    unit: Unit
    work_basis: Literal[
        "service_specific_excluding_shared_opening_work", "blank_opening_closure_only"
    ]
    description: Annotated[str, Field(min_length=1, max_length=500)]
    source_note: Annotated[str, Field(min_length=1, max_length=4000)]
    original_quantity: Annotated[str, Field(max_length=100)] | None
    original_rate: Number | None
    quantity: Number | None
    unit_sell_rate: Number | None
    status: Literal["active", "omitted"]
    omission_reason: Note
    created_by: Identity
    created_at: Annotated[str, Field(max_length=40)]
    history: Annotated[list[History], Field(min_length=1, max_length=MAX_HISTORY)]
    subtotal_ex_tax: str | None
    pricing_status: Literal["priced", "unpriced", "omitted"]


class Target(Contract):
    target_kind: TargetKind
    target_id: Identity
    label: Annotated[str, Field(max_length=200)]


class Summary(Contract):
    priced_subtotal_ex_tax: str
    is_partial: Literal[True]
    technical_status: Literal["unapproved"]
    priced_line_count: Annotated[int, Field(ge=0, le=MAX_LINES)]
    unpriced_line_ids: Annotated[list[Identity], Field(max_length=MAX_LINES)]
    omitted_line_ids: Annotated[list[Identity], Field(max_length=MAX_LINES)]
    unrepresented_targets: Annotated[list[Target], Field(max_length=1000)]
    unassessed_opening_ids: Annotated[list[Identity], Field(max_length=500)]


class Envelope(Contract):
    schema_version: Literal["CLASSIFIRE-DRAFT-ESTIMATE-v1"]
    artifact_id: Identity
    project_id: Identity
    revision: Annotated[int, Field(ge=1)]
    parent_hash: str | None
    created_by: Identity
    created_at: Annotated[str, Field(max_length=40)]
    state: Literal["Draft"]
    review_status: Literal["unreviewed"]
    provenance: Literal["manual_unit_sell"]
    currency: Literal["AUD"]
    tax_treatment: Literal["excluded_not_calculated"]
    calculation_version: Literal[1]
    scope: dict[str, Any]
    system_match: dict[str, Any] | None
    lines: Annotated[list[Line], Field(max_length=MAX_LINES)]
    summary: Summary
    sha256: str


def decimal_string(value: Any, *, unit: str | None = None) -> str | None:
    """Never turn missing values into zero, coerce floats, or round input precision."""
    if value is None:
        return None
    if type(value) is not str or not re.fullmatch(r"[0-9]{1,9}(?:\.[0-9]{1,6})?", value):
        raise ValueError("decimal")
    number = Decimal(value)
    if unit == "each" and number != number.to_integral_value():
        raise ValueError("each_quantity")
    return format(number, "f").rstrip("0").rstrip(".") if "." in value else str(int(value))


def instant(value: str) -> None:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.astimezone(UTC).isoformat() != value:
        raise ValueError("timestamp")


def target_for(scope: dict[str, Any], kind: str, target_id: str) -> dict[str, Any]:
    content = scope["content"]
    if kind == "service":
        target = next((item for item in content["services"] if item["id"] == target_id), None)
        if target is not None:
            return {
                "target_kind": kind,
                "target_id": target_id,
                "label": target["label"],
                "opening_ids": target["opening_ids"],
                "unit": target["unit"],
                "original_quantity": target["quantity"],
                "work_basis": "service_specific_excluding_shared_opening_work",
            }
    elif kind == "blank_opening":
        target = next((item for item in content["openings"] if item["id"] == target_id), None)
        if target is not None and target["blank"]:
            return {
                "target_kind": kind,
                "target_id": target_id,
                "label": target["label"],
                "opening_ids": [target_id],
                "original_quantity": None,
                "work_basis": "blank_opening_closure_only",
            }
    raise ValueError("target")


def same_quantity(left: str | None, right: str | None) -> bool:
    return left is right if left is None or right is None else Decimal(left) == Decimal(right)


def line_amount(line: dict[str, Any]) -> tuple[str | None, str]:
    if line["status"] == "omitted":
        return None, "omitted"
    if line["quantity"] is None or line["unit_sell_rate"] is None:
        return None, "unpriced"
    with localcontext() as context:
        context.prec = 40
        return format(
            money(Decimal(line["quantity"]) * Decimal(line["unit_sell_rate"])), ".2f"
        ), "priced"


def summary_for(scope: dict[str, Any], lines: list[dict[str, Any]]) -> dict[str, Any]:
    targets = [
        {"target_kind": kind, "target_id": item["id"], "label": item["label"]}
        for kind, collection in (("service", "services"), ("blank_opening", "openings"))
        for item in scope["content"][collection]
        if kind == "service" or item["blank"]
    ]
    represented = {line["recovery_key"] for line in lines}
    with localcontext() as context:
        context.prec = 40
        amounts = [line_amount(line)[0] for line in lines]
        subtotal = sum((Decimal(amount) for amount in amounts if amount is not None), Decimal(0))
    return {
        "priced_subtotal_ex_tax": format(subtotal, ".2f"),
        "is_partial": True,
        "technical_status": "unapproved",
        "priced_line_count": sum(line_amount(line)[1] == "priced" for line in lines),
        "unpriced_line_ids": [
            line["line_id"] for line in lines if line_amount(line)[1] == "unpriced"
        ],
        "omitted_line_ids": [line["line_id"] for line in lines if line["status"] == "omitted"],
        "unrepresented_targets": [
            item
            for item in targets
            if item["target_kind"] + ":" + item["target_id"] not in represented
        ],
        "unassessed_opening_ids": [
            item["id"] for item in scope["content"]["openings"] if not item["blank"]
        ],
    }


def basis_hash(envelope: dict[str, Any]) -> str:
    return digest(
        {
            key: envelope[key]
            for key in ("scope", "system_match", "currency", "tax_treatment", "calculation_version")
        }
    )


def _line_valid(line: dict[str, Any], scope: dict[str, Any]) -> None:
    UUID(line["line_id"])
    UUID(line["created_by"])
    instant(line["created_at"])
    target = target_for(scope, line["target_kind"], line["target_id"])
    if any(line[key] != value for key, value in target.items()):
        raise ValueError("target_binding")
    if line["target_kind"] == "blank_opening" and line["unit"] not in ("each", "m2"):
        raise ValueError("unit")
    if line["recovery_key"] != line["target_kind"] + ":" + line["target_id"]:
        raise ValueError("recovery_key")
    for key in ("quantity", "unit_sell_rate", "original_rate"):
        if decimal_string(line[key], unit=line["unit"] if key == "quantity" else None) != line[key]:
            raise ValueError("normalized_decimal")
    if not line["description"].strip() or not line["source_note"].strip():
        raise ValueError("note")
    quantity, rate, status, omission = (
        line["original_quantity"],
        line["original_rate"],
        "active",
        "",
    )
    ids: set[str] = set()
    last_at = line["created_at"]
    for index, event in enumerate(line["history"]):
        UUID(event["event_id"])
        UUID(event["created_by"])
        instant(event["created_at"])
        if event["event_id"] in ids or datetime.fromisoformat(
            event["created_at"]
        ) < datetime.fromisoformat(last_at):
            raise ValueError("history")
        ids.add(event["event_id"])
        last_at = event["created_at"]
        if event["before_quantity"] != quantity or event["before_rate"] != rate:
            raise ValueError("history_before")
        if index == 0:
            if (
                event["action"] != "added"
                or event["created_by"] != line["created_by"]
                or event["created_at"] != line["created_at"]
                or event["unit_sell_rate"] != rate
            ):
                raise ValueError("initial_history")
            if not same_quantity(quantity, event["quantity"]) and not event["reason"].strip():
                raise ValueError("quantity_reason")
        else:
            if not event["reason"].strip() or event["action"] == "added":
                raise ValueError("reason")
            if event["action"] == "override":
                if event["quantity"] == quantity and event["unit_sell_rate"] == rate:
                    raise ValueError("unchanged")
            else:
                desired = "omitted" if event["action"] == "omitted" else "active"
                if (
                    desired == status
                    or event["quantity"] != quantity
                    or event["unit_sell_rate"] != rate
                ):
                    raise ValueError("status_history")
                status = desired
                omission = event["reason"] if status == "omitted" else ""
        quantity, rate = event["quantity"], event["unit_sell_rate"]
        if decimal_string(quantity, unit=line["unit"]) != quantity or decimal_string(rate) != rate:
            raise ValueError("history_decimal")
    if (quantity, rate, status, omission) != (
        line["quantity"],
        line["unit_sell_rate"],
        line["status"],
        line["omission_reason"],
    ):
        raise ValueError("history_final")
    if line_amount(line) != (line["subtotal_ex_tax"], line["pricing_status"]):
        raise ValueError("line_total")


def validate_envelope(value: dict[str, Any]) -> None:
    Envelope.model_validate(value, strict=True)
    if type(value["calculation_version"]) is not int or len(canonical(value)) > MAX_ESTIMATE_BYTES:
        raise ValueError("bounds")
    for key in ("artifact_id", "project_id", "created_by"):
        UUID(value[key])
    instant(value["created_at"])
    if value["revision"] == 1:
        if value["parent_hash"] is not None:
            raise ValueError("parent")
    elif (
        type(value["parent_hash"]) is not str
        or re.fullmatch(r"[0-9a-f]{64}", value["parent_hash"]) is None
    ):
        raise ValueError("parent")
    scope = value["scope"]
    validate_portable_artifact(canonical(scope))
    if scope["project_id"] != value["project_id"]:
        raise ValueError("scope")
    match = value["system_match"]
    if match is not None:
        validate_match(match)
        if match["scope"] != scope:
            raise ValueError("match_scope")
    ids: set[str] = set()
    recovery: set[str] = set()
    for line in value["lines"]:
        _line_valid(line, scope)
        if line["line_id"] in ids or line["recovery_key"] in recovery:
            raise ValueError("duplicate_line")
        ids.add(line["line_id"])
        recovery.add(line["recovery_key"])
    if value["summary"] != summary_for(scope, value["lines"]):
        raise ValueError("summary")
    if value["sha256"] != envelope_hash(value):
        raise ValueError("hash")
