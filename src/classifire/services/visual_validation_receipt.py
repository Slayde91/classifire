"""Immutable, hash-bound Phase 8 visual-validation receipt handling.

This module records reviewed evidence for a future signed lock-admission boundary.
It does not create canonical physical-model records, consume admissions, or create
Physical Model Locks.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, NoReturn, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import Estimate
from ..physical_models import VisualValidationReceipt

VISUAL_VALIDATION_RECEIPT_SCHEMA = "CLASSIFIRE-PHASE8-VISUAL-VALIDATION-RECEIPT-v1"
VISUAL_VALIDATION_RECEIPT_APPROVED = "SEMANTICALLY_APPROVED"
VISUAL_VALIDATION_RECEIPT_WITHHELD = "WITHHELD"
VISUAL_VALIDATION_RECEIPT_STATUSES = frozenset(
    {VISUAL_VALIDATION_RECEIPT_APPROVED, VISUAL_VALIDATION_RECEIPT_WITHHELD}
)
MAX_VISUAL_VALIDATION_RECEIPT_BYTES = 128 * 1024

_RECEIPT_FIELDS = frozenset(
    {
        "schema",
        "receipt_id",
        "project_id",
        "estimate_id",
        "source_run_id",
        "candidate_submission_payload_sha256",
        "controller_receipt_sha256",
        "evidence_manifest_sha256",
        "evidence_family_inventory_sha256",
        "evidence_family_review_sha256",
        "human_review_request_sha256",
        "human_review_response_sha256",
        "approval_reference",
        "reviewed_at",
        "status",
        "reviewed_defect_references",
        "unresolved_items",
        "policy_versions",
        "implementation_revision",
    }
)
_SHA256_RE = re.compile(r"^[A-F0-9]{64}$")
_GIT_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")


class VisualValidationReceiptError(RuntimeError):
    """Raised when receipt evidence is malformed, stale, or not lock-eligible."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Visual validation receipt failed: {code}.")


@dataclass(frozen=True, slots=True)
class VerifiedVisualValidationReceipt:
    """A canonical, side-effect-free representation of a validation receipt."""

    receipt: dict[str, Any]
    receipt_json: str
    receipt_sha256: str


def _fail(code: str) -> NoReturn:
    raise VisualValidationReceiptError(code)


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise VisualValidationReceiptError("VISUAL_VALIDATION_RECEIPT_INVALID") from exc


def _load_receipt(raw: Mapping[str, Any] | bytes | str) -> dict[str, Any]:
    if isinstance(raw, bytes):
        if not raw or len(raw) > MAX_VISUAL_VALIDATION_RECEIPT_BYTES:
            _fail("VISUAL_VALIDATION_RECEIPT_INVALID")
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VisualValidationReceiptError("VISUAL_VALIDATION_RECEIPT_INVALID") from exc
    elif isinstance(raw, str):
        encoded = raw.encode("utf-8")
        if not encoded or len(encoded) > MAX_VISUAL_VALIDATION_RECEIPT_BYTES:
            _fail("VISUAL_VALIDATION_RECEIPT_INVALID")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise VisualValidationReceiptError("VISUAL_VALIDATION_RECEIPT_INVALID") from exc
    elif isinstance(raw, Mapping):
        value = dict(raw)
    else:
        _fail("VISUAL_VALIDATION_RECEIPT_INVALID")
    if not isinstance(value, dict):
        _fail("VISUAL_VALIDATION_RECEIPT_INVALID")
    return cast(dict[str, Any], value)


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        _fail("VISUAL_VALIDATION_RECEIPT_INVALID")
    try:
        parsed = str(UUID(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise VisualValidationReceiptError("VISUAL_VALIDATION_RECEIPT_INVALID") from exc
    if value != parsed:
        _fail("VISUAL_VALIDATION_RECEIPT_INVALID")
    return parsed


def _sha256(value: object) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        _fail("VISUAL_VALIDATION_RECEIPT_INVALID")
    return value


def _text(value: object, *, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        _fail("VISUAL_VALIDATION_RECEIPT_INVALID")
    return value


def _utc_timestamp(value: object) -> str:
    if not isinstance(value, str):
        _fail("VISUAL_VALIDATION_RECEIPT_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise VisualValidationReceiptError("VISUAL_VALIDATION_RECEIPT_INVALID") from exc
    if parsed.tzinfo is None:
        _fail("VISUAL_VALIDATION_RECEIPT_INVALID")
    normalised = parsed.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if value != normalised:
        _fail("VISUAL_VALIDATION_RECEIPT_INVALID")
    return normalised


def _sorted_text_list(value: object, *, allow_empty: bool) -> list[str]:
    if not isinstance(value, list):
        _fail("VISUAL_VALIDATION_RECEIPT_INVALID")
    values = [_text(item, maximum=300) for item in value]
    if values != sorted(set(values)) or (not allow_empty and not values):
        _fail("VISUAL_VALIDATION_RECEIPT_INVALID")
    return values


def _policy_versions(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        _fail("VISUAL_VALIDATION_RECEIPT_INVALID")
    normalised: dict[str, str] = {}
    for key, item in value.items():
        normalised[_text(key, maximum=100)] = _text(item, maximum=100)
    if list(normalised) != sorted(normalised):
        _fail("VISUAL_VALIDATION_RECEIPT_INVALID")
    return normalised


def verify_visual_validation_receipt(
    raw: Mapping[str, Any] | bytes | str,
) -> VerifiedVisualValidationReceipt:
    """Validate and canonically hash a reviewed visual-validation receipt."""

    value = _load_receipt(raw)
    if set(value) != _RECEIPT_FIELDS:
        _fail("VISUAL_VALIDATION_RECEIPT_INVALID")
    status = _text(value["status"], maximum=40)
    if status not in VISUAL_VALIDATION_RECEIPT_STATUSES:
        _fail("VISUAL_VALIDATION_RECEIPT_INVALID")
    unresolved_items = _sorted_text_list(value["unresolved_items"], allow_empty=True)
    if status == VISUAL_VALIDATION_RECEIPT_APPROVED and unresolved_items:
        _fail("VISUAL_VALIDATION_RECEIPT_UNRESOLVED")
    if status == VISUAL_VALIDATION_RECEIPT_WITHHELD and not unresolved_items:
        _fail("VISUAL_VALIDATION_RECEIPT_INVALID")
    revision = value["implementation_revision"]
    if not isinstance(revision, str) or not _GIT_REVISION_RE.fullmatch(revision):
        _fail("VISUAL_VALIDATION_RECEIPT_INVALID")

    receipt = {
        "schema": VISUAL_VALIDATION_RECEIPT_SCHEMA,
        "receipt_id": _uuid(value["receipt_id"]),
        "project_id": _uuid(value["project_id"]),
        "estimate_id": _uuid(value["estimate_id"]),
        "source_run_id": _text(value["source_run_id"], maximum=160),
        "candidate_submission_payload_sha256": _sha256(
            value["candidate_submission_payload_sha256"]
        ),
        "controller_receipt_sha256": _sha256(value["controller_receipt_sha256"]),
        "evidence_manifest_sha256": _sha256(value["evidence_manifest_sha256"]),
        "evidence_family_inventory_sha256": _sha256(value["evidence_family_inventory_sha256"]),
        "evidence_family_review_sha256": _sha256(value["evidence_family_review_sha256"]),
        "human_review_request_sha256": _sha256(value["human_review_request_sha256"]),
        "human_review_response_sha256": _sha256(value["human_review_response_sha256"]),
        "approval_reference": _text(value["approval_reference"], maximum=200),
        "reviewed_at": _utc_timestamp(value["reviewed_at"]),
        "status": status,
        "reviewed_defect_references": _sorted_text_list(
            value["reviewed_defect_references"], allow_empty=False
        ),
        "unresolved_items": unresolved_items,
        "policy_versions": _policy_versions(value["policy_versions"]),
        "implementation_revision": revision,
    }
    if value["schema"] != VISUAL_VALIDATION_RECEIPT_SCHEMA:
        _fail("VISUAL_VALIDATION_RECEIPT_INVALID")
    receipt_json = _canonical_json(receipt)
    return VerifiedVisualValidationReceipt(
        receipt=receipt,
        receipt_json=receipt_json,
        receipt_sha256=hashlib.sha256(receipt_json.encode("utf-8")).hexdigest().upper(),
    )


def register_visual_validation_receipt(
    db: Session,
    *,
    receipt: Mapping[str, Any] | bytes | str,
    operator_reference: str,
) -> tuple[VisualValidationReceipt, bool]:
    """Persist one verified receipt without a canonical write or lock creation.

    The caller owns the surrounding transaction and must supply an accountable
    human-governance reference. Replays are idempotent only for exact receipt bytes.
    """

    verified = verify_visual_validation_receipt(receipt)
    operator = _text(operator_reference, maximum=200)
    estimate = db.get(Estimate, verified.receipt["estimate_id"])
    if estimate is None or estimate.project_id != verified.receipt["project_id"]:
        _fail("VISUAL_VALIDATION_RECEIPT_ESTIMATE_BINDING_INVALID")

    existing_by_id = db.scalar(
        select(VisualValidationReceipt).where(
            VisualValidationReceipt.receipt_id == verified.receipt["receipt_id"]
        )
    )
    if existing_by_id is not None:
        if existing_by_id.receipt_sha256 != verified.receipt_sha256:
            _fail("VISUAL_VALIDATION_RECEIPT_REPLAY_CONFLICT")
        return existing_by_id, False
    existing_by_hash = db.scalar(
        select(VisualValidationReceipt).where(
            VisualValidationReceipt.receipt_sha256 == verified.receipt_sha256
        )
    )
    if existing_by_hash is not None:
        return existing_by_hash, False

    item = VisualValidationReceipt(
        receipt_id=verified.receipt["receipt_id"],
        project_id=verified.receipt["project_id"],
        estimate_id=verified.receipt["estimate_id"],
        source_run_id=verified.receipt["source_run_id"],
        candidate_submission_payload_sha256=verified.receipt["candidate_submission_payload_sha256"],
        controller_receipt_sha256=verified.receipt["controller_receipt_sha256"],
        evidence_manifest_sha256=verified.receipt["evidence_manifest_sha256"],
        evidence_family_inventory_sha256=verified.receipt["evidence_family_inventory_sha256"],
        evidence_family_review_sha256=verified.receipt["evidence_family_review_sha256"],
        human_review_request_sha256=verified.receipt["human_review_request_sha256"],
        human_review_response_sha256=verified.receipt["human_review_response_sha256"],
        approval_reference=verified.receipt["approval_reference"],
        reviewed_at=datetime.fromisoformat(verified.receipt["reviewed_at"].replace("Z", "+00:00")),
        status=verified.receipt["status"],
        unresolved_items=verified.receipt["unresolved_items"],
        policy_versions=verified.receipt["policy_versions"],
        implementation_revision=verified.receipt["implementation_revision"],
        receipt_json=verified.receipt_json,
        receipt_sha256=verified.receipt_sha256,
    )
    db.add(item)
    try:
        db.flush()
    except IntegrityError as exc:
        raise VisualValidationReceiptError("VISUAL_VALIDATION_RECEIPT_REPLAY_CONFLICT") from exc
    record_audit(
        db,
        actor=None,
        actor_type="human_governance",
        actor_name=operator,
        action="register_visual_validation_receipt",
        entity_type="visual_validation_receipt",
        entity_id=item.id,
        project_id=item.project_id,
        new_value={
            "receipt_id": item.receipt_id,
            "receipt_sha256": item.receipt_sha256,
            "status": item.status,
            "candidate_submission_payload_sha256": item.candidate_submission_payload_sha256,
            "physical_model_lock_created": False,
        },
        reason="Recorded reviewed visual-validation evidence without canonical submission or lock.",
    )
    return item, True


def require_semantically_approved_visual_validation_receipt(
    db: Session,
    *,
    receipt_sha256: str,
    project_id: str,
    estimate_id: str,
    candidate_submission_payload_sha256: str,
    controller_receipt_sha256: str,
    evidence_manifest_sha256: str,
    evidence_family_inventory_sha256: str,
    evidence_family_review_sha256: str,
    human_review_request_sha256: str,
    human_review_response_sha256: str,
) -> VisualValidationReceipt:
    """Return only an intact receipt exactly bound for a future lock admission.

    This is intentionally side-effect free. The generic lock route does not call
    it: a separately designed and signed lock-admission boundary must do so.
    """

    expected = {
        "project_id": _uuid(project_id),
        "estimate_id": _uuid(estimate_id),
        "candidate_submission_payload_sha256": _sha256(candidate_submission_payload_sha256),
        "controller_receipt_sha256": _sha256(controller_receipt_sha256),
        "evidence_manifest_sha256": _sha256(evidence_manifest_sha256),
        "evidence_family_inventory_sha256": _sha256(evidence_family_inventory_sha256),
        "evidence_family_review_sha256": _sha256(evidence_family_review_sha256),
        "human_review_request_sha256": _sha256(human_review_request_sha256),
        "human_review_response_sha256": _sha256(human_review_response_sha256),
    }
    stored_sha256 = _sha256(receipt_sha256)
    item = db.scalar(
        select(VisualValidationReceipt).where(
            VisualValidationReceipt.receipt_sha256 == stored_sha256
        )
    )
    if item is None:
        _fail("VISUAL_VALIDATION_RECEIPT_REQUIRED")
    try:
        verified = verify_visual_validation_receipt(item.receipt_json)
    except VisualValidationReceiptError as exc:
        raise VisualValidationReceiptError("VISUAL_VALIDATION_RECEIPT_CORRUPT") from exc
    if verified.receipt_sha256 != item.receipt_sha256:
        _fail("VISUAL_VALIDATION_RECEIPT_CORRUPT")
    for field_name, expected_value in expected.items():
        if (
            getattr(item, field_name) != expected_value
            or verified.receipt[field_name] != expected_value
        ):
            _fail("VISUAL_VALIDATION_RECEIPT_BINDING_MISMATCH")
    for field_name in (
        "receipt_id",
        "source_run_id",
        "human_review_request_sha256",
        "approval_reference",
        "status",
        "unresolved_items",
        "policy_versions",
        "implementation_revision",
    ):
        if getattr(item, field_name) != verified.receipt[field_name]:
            _fail("VISUAL_VALIDATION_RECEIPT_CORRUPT")
    stored_reviewed_at = item.reviewed_at
    if stored_reviewed_at.tzinfo is None:
        stored_reviewed_at = stored_reviewed_at.replace(tzinfo=UTC)
    else:
        stored_reviewed_at = stored_reviewed_at.astimezone(UTC)
    if stored_reviewed_at.strftime("%Y-%m-%dT%H:%M:%SZ") != verified.receipt["reviewed_at"]:
        _fail("VISUAL_VALIDATION_RECEIPT_CORRUPT")
    if item.status != VISUAL_VALIDATION_RECEIPT_APPROVED or item.unresolved_items:
        _fail("VISUAL_VALIDATION_RECEIPT_NOT_APPROVED")
    return item


__all__ = [
    "MAX_VISUAL_VALIDATION_RECEIPT_BYTES",
    "VISUAL_VALIDATION_RECEIPT_APPROVED",
    "VISUAL_VALIDATION_RECEIPT_SCHEMA",
    "VISUAL_VALIDATION_RECEIPT_STATUSES",
    "VISUAL_VALIDATION_RECEIPT_WITHHELD",
    "VerifiedVisualValidationReceipt",
    "VisualValidationReceiptError",
    "register_visual_validation_receipt",
    "require_semantically_approved_visual_validation_receipt",
    "verify_visual_validation_receipt",
]
