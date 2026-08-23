"""Bounded orchestration for linked originals and proposal-only visual inference.

This service composes the existing retrieval, governed evidence-retention,
retained-evidence adapter, and proposal-only controller boundaries.  It never
commits its database transaction and exposes no admission, canonical physical
write, or lock operation.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from .canonical_submission_state import InitialSubmissionState
from .linked_image_evidence import (
    LinkedImageEvidenceRetention,
    retain_verified_linked_image,
)
from .linked_image_retrieval import (
    DEFAULT_LINKED_IMAGE_POLICY,
    READY_STATUSES,
    LinkedImageBatch,
    LinkedImagePolicy,
    Resolver,
    Transport,
    materialize_linked_images,
    resolve_public_addresses,
)
from .phase8_visual_evidence import (
    RetainedVisualEvidencePacket,
    build_retained_visual_evidence_packet,
)
from .phase8_visual_proposal import (
    Phase8VisualInferencePort,
    Phase8VisualProposalError,
    Phase8VisualProposalResult,
    ProposalOnlyVisualController,
    canonical_json_sha256,
)

LINKED_VISUAL_RUN_RECEIPT_SCHEMA = "CLASSIFIRE-PHASE8-LINKED-VISUAL-RUN-v1"
LINKED_VISUAL_RETRIEVAL_BLOCKED = "LINKED_VISUAL_RETRIEVAL_BLOCKED"
_PHYSICAL_COUNT_FIELDS = (
    "opening_count",
    "service_count",
    "service_opening_link_count",
    "active_physical_model_lock_count",
)
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


class Phase8LinkedVisualRunError(RuntimeError):
    """A stable, path-free orchestration failure before a safe result exists."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Phase 8 linked visual run failed: {code}.")


@dataclass(frozen=True, slots=True)
class Phase8LinkedVisualRunResult:
    retrieval: LinkedImageBatch
    retentions: tuple[LinkedImageEvidenceRetention, ...]
    evidence_packet: RetainedVisualEvidencePacket | None
    visual_result: Phase8VisualProposalResult | None
    receipt: dict[str, Any]

    @property
    def receipt_sha256(self) -> str:
        return canonical_json_sha256(self.receipt)


def _token(value: object, *, code: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise Phase8LinkedVisualRunError(code)
    return text


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX_DIGITS for character in value)
    )


def _valid_state_summary(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {"fingerprint", "counts"}:
        return False
    counts = value.get("counts")
    required_counts = {"defect_count", "evidence_count", *_PHYSICAL_COUNT_FIELDS}
    return (
        _is_sha256(value.get("fingerprint"))
        and isinstance(counts, dict)
        and required_counts.issubset(counts)
        and all(
            isinstance(name, str)
            and isinstance(count, int)
            and not isinstance(count, bool)
            and count >= 0
            for name, count in counts.items()
        )
    )


def validate_phase8_linked_visual_run_receipt(receipt: Any) -> list[str]:
    """Validate the content-free orchestration receipt."""

    if not isinstance(receipt, dict):
        return ["linked visual run receipt must be an object"]
    expected_keys = {
        "schema",
        "status",
        "run_id",
        "estimate_id",
        "defect_reference",
        "report_sha256",
        "retrieval",
        "retained_evidence",
        "evidence_manifest_sha256",
        "controller_receipt_sha256",
        "protected_state",
        "runtime_inference_performed",
        "runner_database_commit_performed",
        "runner_canonical_write_performed",
        "runner_physical_model_lock_created",
        "human_reference_visible_to_inference",
    }
    errors: list[str] = []
    if set(receipt) != expected_keys:
        errors.append("linked visual run receipt fields do not match the approved schema")
    if receipt.get("schema") != LINKED_VISUAL_RUN_RECEIPT_SCHEMA:
        errors.append("linked visual run receipt schema is invalid")
    for field in ("status", "run_id", "estimate_id", "defect_reference"):
        if not isinstance(receipt.get(field), str) or not receipt[field].strip():
            errors.append(f"linked visual run receipt {field} is invalid")
    if not _is_sha256(receipt.get("report_sha256")):
        errors.append("linked visual run report SHA-256 is invalid")
    retrieval = receipt.get("retrieval")
    if not isinstance(retrieval, dict) or set(retrieval) != {
        "ok",
        "receipt_sha256",
        "photo_occurrence_count",
        "ready_count",
        "required_count",
        "status_counts",
    }:
        errors.append("linked visual run retrieval summary is invalid")
    elif (
        not isinstance(retrieval.get("ok"), bool)
        or not _is_sha256(retrieval.get("receipt_sha256"))
        or any(
            isinstance(retrieval.get(field), bool)
            or not isinstance(retrieval.get(field), int)
            or retrieval[field] < 0
            for field in ("photo_occurrence_count", "ready_count", "required_count")
        )
        or not isinstance(retrieval.get("status_counts"), dict)
        or any(
            not isinstance(status, str)
            or not status
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
            for status, count in retrieval.get("status_counts", {}).items()
        )
        or sum(retrieval.get("status_counts", {}).values())
        != retrieval.get("photo_occurrence_count")
    ):
        errors.append("linked visual run retrieval summary is invalid")
    retained = receipt.get("retained_evidence")
    if not isinstance(retained, list) or any(
        not isinstance(item, dict)
        or set(item)
        != {
            "photo_id",
            "evidence_source_id",
            "parent_evidence_source_id",
            "sha256",
            "evidence_created",
            "stored_file_created",
        }
        or not all(
            isinstance(item.get(field), str) and bool(item[field])
            for field in ("photo_id", "evidence_source_id", "parent_evidence_source_id")
        )
        or not _is_sha256(item.get("sha256"))
        or not isinstance(item.get("evidence_created"), bool)
        or not isinstance(item.get("stored_file_created"), bool)
        for item in retained
    ):
        errors.append("linked visual run retention summary is invalid")
    runtime_performed = receipt.get("runtime_inference_performed")
    if not isinstance(runtime_performed, bool):
        errors.append("linked visual run inference flag is invalid")
    for field in ("evidence_manifest_sha256", "controller_receipt_sha256"):
        value = receipt.get(field)
        if (runtime_performed and not _is_sha256(value)) or (
            not runtime_performed and value is not None
        ):
            errors.append(f"linked visual run {field} is invalid")
    protected = receipt.get("protected_state")
    if not isinstance(protected, dict) or set(protected) != {
        "before_retrieval",
        "after_retrieval",
        "before_inference",
        "after_inference",
        "retrieval_database_state_unchanged",
        "physical_components_unchanged",
        "inference_state_unchanged",
        "protected_state_changed_during_inference",
    }:
        errors.append("linked visual run protected-state summary is invalid")
    elif protected.get("retrieval_database_state_unchanged") is not True:
        errors.append("linked visual run retrieval changed database state")
    elif (
        not _valid_state_summary(protected.get("before_retrieval"))
        or not _valid_state_summary(protected.get("after_retrieval"))
        or any(
            not isinstance(protected.get(field), bool)
            for field in (
                "retrieval_database_state_unchanged",
                "physical_components_unchanged",
                "inference_state_unchanged",
                "protected_state_changed_during_inference",
            )
        )
        or (
            runtime_performed
            and (
                not _valid_state_summary(protected.get("before_inference"))
                or not _valid_state_summary(protected.get("after_inference"))
            )
        )
        or (
            not runtime_performed
            and (
                protected.get("before_inference") is not None
                or protected.get("after_inference") is not None
            )
        )
        or (
            runtime_performed
            and protected.get("protected_state_changed_during_inference")
            is protected.get("inference_state_unchanged")
        )
        or (
            not runtime_performed
            and (
                protected.get("protected_state_changed_during_inference") is not False
                or protected.get("inference_state_unchanged") is not False
            )
        )
    ):
        errors.append("linked visual run protected-state summary is invalid")
    if isinstance(retrieval, dict) and isinstance(retained, list):
        if runtime_performed:
            if retrieval.get("ok") is not True or retrieval.get("ready_count") != len(retained):
                errors.append("linked visual run execution counts are inconsistent")
        elif (
            receipt.get("status") != LINKED_VISUAL_RETRIEVAL_BLOCKED
            or retained
            or (retrieval.get("ok") is True and retrieval.get("ready_count") != 0)
        ):
            errors.append("linked visual run blocked receipt is inconsistent")
    for field in (
        "runner_database_commit_performed",
        "runner_canonical_write_performed",
        "runner_physical_model_lock_created",
        "human_reference_visible_to_inference",
    ):
        if receipt.get(field) is not False:
            errors.append(f"linked visual run {field} must be false")
    try:
        serialized = json.dumps(
            receipt,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        errors.append("linked visual run receipt is not canonical JSON")
    else:
        if "https://" in serialized or "Signature=" in serialized or "Key-Pair-Id=" in serialized:
            errors.append("linked visual run receipt exposes a signed capability")
    return list(dict.fromkeys(errors))


def _state(
    reader: Callable[[], InitialSubmissionState], estimate_id: str
) -> InitialSubmissionState:
    try:
        state = reader()
    except Exception as exc:
        raise Phase8LinkedVisualRunError("PROTECTED_STATE_UNAVAILABLE") from exc
    if not isinstance(state, InitialSubmissionState) or state.estimate_id != estimate_id:
        raise Phase8LinkedVisualRunError("PROTECTED_STATE_INVALID")
    if len(state.fingerprint) != 64:
        raise Phase8LinkedVisualRunError("PROTECTED_STATE_INVALID")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in state.counts.values()
    ):
        raise Phase8LinkedVisualRunError("PROTECTED_STATE_INVALID")
    return state


def _state_summary(state: InitialSubmissionState) -> dict[str, Any]:
    return {
        "fingerprint": state.fingerprint,
        "counts": dict(sorted(state.counts.items())),
    }


def _same_state(left: InitialSubmissionState, right: InitialSubmissionState) -> bool:
    return left.fingerprint == right.fingerprint and left.counts == right.counts


def _physical_counts_unchanged(
    before: InitialSubmissionState,
    after: InitialSubmissionState,
) -> bool:
    return all(
        before.counts.get(field) == after.counts.get(field) for field in _PHYSICAL_COUNT_FIELDS
    )


def _physical_model_empty(state: InitialSubmissionState) -> bool:
    return all(state.counts.get(field) == 0 for field in _PHYSICAL_COUNT_FIELDS)


def _retrieval_summary(batch: LinkedImageBatch) -> dict[str, Any]:
    statuses = Counter(result.status for result in batch.results)
    return {
        "ok": batch.ok,
        "receipt_sha256": canonical_json_sha256(batch.receipt),
        "photo_occurrence_count": len(batch.results),
        "ready_count": sum(result.status in READY_STATUSES for result in batch.results),
        "required_count": sum(result.required for result in batch.results),
        "status_counts": dict(sorted(statuses.items())),
    }


def _retention_summary(item: LinkedImageEvidenceRetention) -> dict[str, Any]:
    source_json = item.evidence.source_json
    visual = source_json.get("phase8_visual_inference") if isinstance(source_json, dict) else None
    parent_id = visual.get("parent_evidence_source_id") if isinstance(visual, dict) else None
    if not isinstance(parent_id, str) or not parent_id:
        raise Phase8LinkedVisualRunError("RETENTION_PROVENANCE_INVALID")
    return {
        "photo_id": item.evidence.region_reference,
        "evidence_source_id": item.evidence.id,
        "parent_evidence_source_id": parent_id,
        "sha256": item.evidence.sha256,
        "evidence_created": item.evidence_created,
        "stored_file_created": item.stored_file_created,
    }


def _receipt(
    *,
    run_id: str,
    estimate_id: str,
    defect_reference: str,
    report_sha256: str,
    retrieval: LinkedImageBatch,
    retentions: Sequence[LinkedImageEvidenceRetention],
    state_before_retrieval: InitialSubmissionState,
    state_after_retrieval: InitialSubmissionState,
    state_before_inference: InitialSubmissionState | None,
    state_after_inference: InitialSubmissionState | None,
    evidence_packet: RetainedVisualEvidencePacket | None,
    visual_result: Phase8VisualProposalResult | None,
) -> dict[str, Any]:
    retrieval_unchanged = _same_state(state_before_retrieval, state_after_retrieval)
    physical_unchanged = state_before_inference is None or (
        _physical_counts_unchanged(state_before_retrieval, state_before_inference)
        and state_after_inference is not None
        and _physical_counts_unchanged(state_before_inference, state_after_inference)
    )
    inference_unchanged = (
        state_before_inference is not None
        and state_after_inference is not None
        and _same_state(state_before_inference, state_after_inference)
    )
    retention_rows = [_retention_summary(item) for item in retentions]
    return {
        "schema": LINKED_VISUAL_RUN_RECEIPT_SCHEMA,
        "status": (
            visual_result.status if visual_result is not None else LINKED_VISUAL_RETRIEVAL_BLOCKED
        ),
        "run_id": run_id,
        "estimate_id": estimate_id,
        "defect_reference": defect_reference,
        "report_sha256": report_sha256.lower(),
        "retrieval": _retrieval_summary(retrieval),
        "retained_evidence": retention_rows,
        "evidence_manifest_sha256": (
            evidence_packet.manifest_sha256 if evidence_packet is not None else None
        ),
        "controller_receipt_sha256": (
            visual_result.receipt_sha256 if visual_result is not None else None
        ),
        "protected_state": {
            "before_retrieval": _state_summary(state_before_retrieval),
            "after_retrieval": _state_summary(state_after_retrieval),
            "before_inference": (
                _state_summary(state_before_inference)
                if state_before_inference is not None
                else None
            ),
            "after_inference": (
                _state_summary(state_after_inference) if state_after_inference is not None else None
            ),
            "retrieval_database_state_unchanged": retrieval_unchanged,
            "physical_components_unchanged": physical_unchanged,
            "inference_state_unchanged": inference_unchanged,
            "protected_state_changed_during_inference": (
                state_before_inference is not None and not inference_unchanged
            ),
        },
        "runtime_inference_performed": visual_result is not None,
        "runner_database_commit_performed": False,
        "runner_canonical_write_performed": False,
        "runner_physical_model_lock_created": False,
        "human_reference_visible_to_inference": False,
    }


def run_phase8_linked_visual_proposal(
    db: Session,
    *,
    run_id: str,
    estimate_id: str,
    defect_reference: str,
    report: Path,
    report_sha256: str,
    photo_rows: Sequence[Mapping[str, Any]],
    parent_evidence_by_photo_id: Mapping[str, str],
    storage_root: Path,
    retrieval_root: Path,
    operator_reference: str,
    inference_profile: Mapping[str, Any],
    inference_port: Phase8VisualInferencePort,
    protected_state_reader: Callable[[], InitialSubmissionState],
    policy: LinkedImagePolicy = DEFAULT_LINKED_IMAGE_POLICY,
    prior_retrieval_receipt: Mapping[str, Any] | None = None,
    resolver: Resolver = resolve_public_addresses,
    transport: Transport | None = None,
    max_correction_passes: int = 2,
) -> Phase8LinkedVisualRunResult:
    """Run linked retrieval, evidence retention, and proposal-only inference.

    The caller owns the outer database transaction. This function creates a
    nested savepoint for atomic retention but never commits the outer
    transaction.
    """

    run_id = _token(run_id, code="RUN_ID_REQUIRED")
    estimate_id = _token(estimate_id, code="ESTIMATE_ID_REQUIRED")
    defect_reference = _token(defect_reference, code="DEFECT_REFERENCE_REQUIRED")
    operator_reference = _token(operator_reference, code="OPERATOR_REFERENCE_REQUIRED")
    if not report.is_file() or not storage_root.is_dir() or not retrieval_root.is_dir():
        raise Phase8LinkedVisualRunError("RUN_INPUT_UNAVAILABLE")
    rows = [dict(row) for row in photo_rows]
    parent_map = {
        _token(photo_id, code="PARENT_MAPPING_INVALID"): _token(
            evidence_id, code="PARENT_MAPPING_INVALID"
        )
        for photo_id, evidence_id in parent_evidence_by_photo_id.items()
    }

    state_before_retrieval = _state(protected_state_reader, estimate_id)
    if not _physical_model_empty(state_before_retrieval):
        raise Phase8LinkedVisualRunError("PROTECTED_PHYSICAL_MODEL_NOT_EMPTY")
    retrieval = materialize_linked_images(
        report,
        rows,
        retrieval_root,
        report_sha256=report_sha256,
        policy=policy,
        prior_receipt=dict(prior_retrieval_receipt) if prior_retrieval_receipt else None,
        resolver=resolver,
        transport=transport,
    )
    state_after_retrieval = _state(protected_state_reader, estimate_id)
    if not _same_state(state_before_retrieval, state_after_retrieval):
        raise Phase8LinkedVisualRunError("RETRIEVAL_CHANGED_DATABASE_STATE")

    ready = tuple(result for result in retrieval.results if result.status in READY_STATUSES)
    if not retrieval.ok or not ready:
        receipt = _receipt(
            run_id=run_id,
            estimate_id=estimate_id,
            defect_reference=defect_reference,
            report_sha256=report_sha256,
            retrieval=retrieval,
            retentions=(),
            state_before_retrieval=state_before_retrieval,
            state_after_retrieval=state_after_retrieval,
            state_before_inference=None,
            state_after_inference=None,
            evidence_packet=None,
            visual_result=None,
        )
        if validate_phase8_linked_visual_run_receipt(receipt):
            raise Phase8LinkedVisualRunError("RUN_RECEIPT_INVALID")
        result = Phase8LinkedVisualRunResult(
            retrieval=retrieval,
            retentions=(),
            evidence_packet=None,
            visual_result=None,
            receipt=receipt,
        )
        return result
    ready_ids = {result.photo_id for result in ready}
    if set(parent_map) != ready_ids:
        raise Phase8LinkedVisualRunError("PARENT_MAPPING_MISMATCH")

    with db.begin_nested():
        retentions = tuple(
            retain_verified_linked_image(
                db,
                storage_root=storage_root,
                retrieval_root=retrieval_root,
                estimate_id=estimate_id,
                parent_evidence_source_id=parent_map[result.photo_id],
                result=result,
                operator_reference=operator_reference,
                policy=policy,
            )
            for result in ready
        )
        state_before_inference = _state(protected_state_reader, estimate_id)
        if not _physical_counts_unchanged(state_before_retrieval, state_before_inference):
            raise Phase8LinkedVisualRunError("RETENTION_CHANGED_PHYSICAL_STATE")
        if state_before_inference.counts.get("defect_count") != state_before_retrieval.counts.get(
            "defect_count"
        ):
            raise Phase8LinkedVisualRunError("RETENTION_CHANGED_DEFECT_STATE")
        expected_evidence_count = state_before_retrieval.counts.get("evidence_count", 0) + sum(
            item.evidence_created for item in retentions
        )
        if state_before_inference.counts.get("evidence_count") != expected_evidence_count:
            raise Phase8LinkedVisualRunError("RETENTION_EVIDENCE_COUNT_INVALID")

        evidence_packet = build_retained_visual_evidence_packet(
            db,
            storage_root=storage_root,
            estimate_id=estimate_id,
            defect_reference=defect_reference,
        )
        packet_ids = {item.evidence_id for item in evidence_packet.files}
        if any(item.evidence.id not in packet_ids for item in retentions):
            raise Phase8LinkedVisualRunError("RETAINED_EVIDENCE_PACKET_MISMATCH")
        try:
            controller = ProposalOnlyVisualController(
                run_id=run_id,
                estimate_id=estimate_id,
                evidence_manifest=evidence_packet.manifest,
                inference_profile=dict(inference_profile),
                inference_port=inference_port,
                protected_state_reader=protected_state_reader,
                max_correction_passes=max_correction_passes,
            )
        except Phase8VisualProposalError as exc:
            raise Phase8LinkedVisualRunError(exc.code) from exc
        visual_result = controller.run()
        state_after_inference = _state(protected_state_reader, estimate_id)

    receipt = _receipt(
        run_id=run_id,
        estimate_id=estimate_id,
        defect_reference=defect_reference,
        report_sha256=report_sha256,
        retrieval=retrieval,
        retentions=retentions,
        state_before_retrieval=state_before_retrieval,
        state_after_retrieval=state_after_retrieval,
        state_before_inference=state_before_inference,
        state_after_inference=state_after_inference,
        evidence_packet=evidence_packet,
        visual_result=visual_result,
    )
    if validate_phase8_linked_visual_run_receipt(receipt):
        raise Phase8LinkedVisualRunError("RUN_RECEIPT_INVALID")
    return Phase8LinkedVisualRunResult(
        retrieval=retrieval,
        retentions=retentions,
        evidence_packet=evidence_packet,
        visual_result=visual_result,
        receipt=receipt,
    )


__all__ = [
    "LINKED_VISUAL_RETRIEVAL_BLOCKED",
    "LINKED_VISUAL_RUN_RECEIPT_SCHEMA",
    "Phase8LinkedVisualRunError",
    "Phase8LinkedVisualRunResult",
    "run_phase8_linked_visual_proposal",
    "validate_phase8_linked_visual_run_receipt",
]
