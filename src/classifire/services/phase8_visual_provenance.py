"""Fail-closed completeness assessment for current Phase 8 visual provenance.

This module verifies the content-free linked-visual-run receipt and its exact
evidence-family inventory together.  It does not open report or image bytes,
perform inference, access the database, create canonical state, or authorize a
Physical Model Lock.  A caller must supply the current artefacts explicitly;
the general database workflow deliberately cannot substitute older or inferred
visual provenance for them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .phase8_evidence_quality import (
    Phase8EvidenceQualityError,
    summarise_phase8_evidence_family_quality,
)
from .phase8_linked_visual_run import validate_phase8_linked_visual_run_receipt
from .phase8_visual_proposal import VISUAL_PROPOSAL_APPROVED

PHASE8_VISUAL_PROVENANCE_COMPLETENESS_SCHEMA = "CLASSIFIRE-PHASE8-VISUAL-PROVENANCE-COMPLETENESS-v1"


def _nonblank(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _same_sha256(left: object, right: object) -> bool:
    return (
        isinstance(left, str)
        and isinstance(right, str)
        and len(left) == 64
        and len(right) == 64
        and left.upper() == right.upper()
    )


@dataclass(frozen=True, slots=True)
class Phase8VisualProvenanceCompleteness:
    """Content-free result for one current visual provenance check."""

    estimate_id: str | None
    defect_reference: str | None
    linked_visual_run_id: str | None
    linked_visual_receipt_status: str | None
    evidence_manifest_sha256: str | None
    evidence_family_inventory_sha256: str | None
    controller_receipt_sha256: str | None
    family_count: int | None
    preserved_context_member_count: int | None
    errors: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": PHASE8_VISUAL_PROVENANCE_COMPLETENESS_SCHEMA,
            "status": "PASS" if self.complete else "INCOMPLETE",
            "complete": self.complete,
            "estimate_id": self.estimate_id,
            "defect_reference": self.defect_reference,
            "linked_visual_run_id": self.linked_visual_run_id,
            "linked_visual_receipt_status": self.linked_visual_receipt_status,
            "evidence_manifest_sha256": self.evidence_manifest_sha256,
            "evidence_family_inventory_sha256": self.evidence_family_inventory_sha256,
            "controller_receipt_sha256": self.controller_receipt_sha256,
            "family_count": self.family_count,
            "preserved_context_member_count": self.preserved_context_member_count,
            "errors": list(self.errors),
            "report_or_image_retrieval_performed": False,
            "runtime_inference_performed": False,
            "database_write_performed": False,
            "canonical_write_performed": False,
            "physical_model_lock_created": False,
        }


def assess_phase8_visual_provenance_completeness(
    *,
    estimate_id: object,
    defect_reference: object,
    linked_visual_run_receipt: object,
    evidence_family_inventory: object,
) -> Phase8VisualProvenanceCompleteness:
    """Assess supplied current visual artefacts without inferring or mutating state.

    The caller-provided estimate and defect identity protect against using a
    valid receipt from another scope.  The evidence-family inventory must be
    structurally valid, then match both its own canonical SHA-256 and the
    source manifest SHA-256 recorded by the linked visual run.
    """

    errors: list[str] = []
    expected_estimate_id = _nonblank(estimate_id)
    expected_defect_reference = _nonblank(defect_reference)
    if expected_estimate_id is None or expected_defect_reference is None:
        errors.append("EXPECTED_VISUAL_SCOPE_INVALID")

    receipt = linked_visual_run_receipt if isinstance(linked_visual_run_receipt, dict) else {}
    if validate_phase8_linked_visual_run_receipt(linked_visual_run_receipt):
        errors.append("LINKED_VISUAL_RUN_RECEIPT_INVALID")
    else:
        if receipt.get("status") != VISUAL_PROPOSAL_APPROVED:
            errors.append("CURRENT_VISUAL_RUN_NOT_APPROVED")
        if (
            receipt.get("estimate_id") != expected_estimate_id
            or receipt.get("defect_reference") != expected_defect_reference
        ):
            errors.append("CURRENT_VISUAL_RUN_SCOPE_MISMATCH")
        if receipt.get("runtime_inference_performed") is not True:
            errors.append("CURRENT_VISUAL_RUN_INFERENCE_NOT_PERFORMED")

    metrics: dict[str, Any] | None = None
    try:
        metrics = summarise_phase8_evidence_family_quality([evidence_family_inventory])
    except (Phase8EvidenceQualityError, TypeError, ValueError):
        errors.append("EVIDENCE_FAMILY_INVENTORY_INVALID")

    if metrics is not None and not _same_sha256(
        receipt.get("evidence_manifest_sha256"), metrics["source_manifest_sha256s"][0]
    ):
        errors.append("EVIDENCE_FAMILY_MANIFEST_HASH_MISMATCH")
    if metrics is not None and not _same_sha256(
        receipt.get("evidence_family_inventory_sha256"), metrics["inventory_sha256s"][0]
    ):
        errors.append("EVIDENCE_FAMILY_INVENTORY_HASH_MISMATCH")

    return Phase8VisualProvenanceCompleteness(
        estimate_id=expected_estimate_id,
        defect_reference=expected_defect_reference,
        linked_visual_run_id=_nonblank(receipt.get("run_id")),
        linked_visual_receipt_status=_nonblank(receipt.get("status")),
        evidence_manifest_sha256=(
            metrics["source_manifest_sha256s"][0] if metrics is not None else None
        ),
        evidence_family_inventory_sha256=(
            metrics["inventory_sha256s"][0] if metrics is not None else None
        ),
        controller_receipt_sha256=_nonblank(receipt.get("controller_receipt_sha256")),
        family_count=metrics["family_count"] if metrics is not None else None,
        preserved_context_member_count=(
            metrics["preserved_context_member_count"] if metrics is not None else None
        ),
        errors=tuple(dict.fromkeys(errors)),
    )


__all__ = [
    "PHASE8_VISUAL_PROVENANCE_COMPLETENESS_SCHEMA",
    "Phase8VisualProvenanceCompleteness",
    "assess_phase8_visual_provenance_completeness",
]
