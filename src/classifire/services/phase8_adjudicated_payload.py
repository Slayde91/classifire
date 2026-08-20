"""Validate Phase 8 adjudication receipts and derive the sealed clean-stack payload."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..physical_model_submission_schema import InitialCanonicalPhysicalSubmission
from ..physical_models import Defect
from .adjudicated_admission import normalised_submission_payload_sha256, sha256_hex

PROPOSAL_SCHEMA = "CLASSIFIRE-ADJUDICATED-PROPOSAL-v1"
FINAL_STATE_SCHEMA = "CLASSIFIRE-ADJUDICATED-PROPOSAL-ONLY-FINAL-STATE-v1"
DIFF_SCHEMA = "CLASSIFIRE-ADJUDICATED-PROPOSAL-DIFF-v1"
COMPARISON_SCHEMA = "CLASSIFIRE-HUMAN-ADJUDICATION-PROPOSAL-COMPARISON-v1"
FINAL_STATE_STATUS = "ADJUDICATED_PROPOSAL_READY_FOR_HUMAN_REVIEW"
DIFF_SCOPE = "OFFLINE_HUMAN_ADJUDICATION_ONLY"
WITHHELD_TOOL = "classifire_submit_initial_physical_model"
MAX_ARTIFACT_BYTES = 5 * 1024 * 1024


class Phase8AdjudicatedPayloadError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Phase 8 adjudicated payload derivation failed: {code}.")


@dataclass(frozen=True)
class Phase8AdjudicatedPayload:
    payload: dict[str, Any]
    payload_sha256: str
    source_run_id: str
    adjudicated_run_id: str
    artifact_digests: dict[str, str]


def derive_phase8_adjudicated_payload(
    db: Session,
    *,
    estimate_id: str,
    adjudicated_proposal_path: Path,
    adjudicated_final_state_path: Path,
    adjudicated_diff_path: Path,
    human_comparison_path: Path,
) -> Phase8AdjudicatedPayload:
    """Validate the four approved receipts and map external defects to canonical IDs."""

    proposal, proposal_hash = _read_json(adjudicated_proposal_path)
    final_state, final_state_hash = _read_json(adjudicated_final_state_path)
    diff, diff_hash = _read_json(adjudicated_diff_path)
    comparison, comparison_hash = _read_json(human_comparison_path)
    _validate_receipt_graph(
        estimate_id=estimate_id,
        proposal=proposal,
        proposal_hash=proposal_hash,
        final_state=final_state,
        final_state_hash=final_state_hash,
        diff=diff,
        diff_hash=diff_hash,
        comparison=comparison,
        comparison_hash=comparison_hash,
    )
    openings = _require_list(proposal.get("openings"))
    services = _require_list(proposal.get("services"))
    opening_codes = [_nonblank(item.get("opening_code")) for item in openings]
    service_codes = [_nonblank(item.get("service_code")) for item in services]
    if len(opening_codes) != len(set(opening_codes)) or len(service_codes) != len(
        set(service_codes)
    ):
        raise Phase8AdjudicatedPayloadError("ADJUDICATED_CODE_DUPLICATE")

    external_defect_ids = {_nonblank(item.get("external_defect_id")) for item in openings}
    defects = list(
        db.scalars(
            select(Defect).where(
                Defect.estimate_id == estimate_id,
                Defect.external_defect_id.in_(sorted(external_defect_ids)),
            )
        ).all()
    )
    defect_by_external_id = {item.external_defect_id: item.id for item in defects}
    if set(defect_by_external_id) != external_defect_ids:
        raise Phase8AdjudicatedPayloadError("ADJUDICATED_DEFECT_BINDING_INVALID")

    payload_openings = []
    for item in openings:
        external_defect_id = _nonblank(item.get("external_defect_id"))
        payload_openings.append(
            {
                "opening_code": _nonblank(item.get("opening_code")),
                "canonical_defect_id": defect_by_external_id[external_defect_id],
                **_optional_fields(
                    item,
                    {
                        "location",
                        "substrate_type",
                        "substrate_plane",
                        "orientation",
                        "opening_type",
                        "frl",
                        "notes",
                    },
                ),
            }
        )

    known_opening_codes = set(opening_codes)
    payload_services = []
    payload_links = []
    for item in services:
        service_code = _nonblank(item.get("service_code"))
        linked_opening_codes = item.get("opening_codes")
        if (
            not isinstance(linked_opening_codes, list)
            or not linked_opening_codes
            or any(
                not isinstance(value, str) or not value.strip()
                for value in linked_opening_codes
            )
            or len(linked_opening_codes) != len(set(linked_opening_codes))
            or not set(linked_opening_codes).issubset(known_opening_codes)
        ):
            raise Phase8AdjudicatedPayloadError("ADJUDICATED_LINK_BINDING_INVALID")
        if item.get("primary_opening_code") not in linked_opening_codes:
            raise Phase8AdjudicatedPayloadError("ADJUDICATED_LINK_BINDING_INVALID")
        payload_services.append(
            {
                "service_code": service_code,
                "service_type": _nonblank(item.get("service_type")),
                **_optional_fields(
                    item,
                    {
                        "material",
                        "nominal_size_mm",
                        "quantity",
                        "evidence_status",
                        "confidence",
                        "notes",
                    },
                ),
            }
        )
        for opening_code in linked_opening_codes:
            payload_links.append(
                {
                    "service_code": service_code,
                    "opening_code": opening_code,
                    **_optional_fields(
                        item,
                        {
                            "link_type",
                            "relationship_status",
                            "evidence_status",
                            "confidence",
                            "source_reference",
                            "notes",
                        },
                    ),
                }
            )

    try:
        payload = InitialCanonicalPhysicalSubmission.model_validate(
            {
                "openings": payload_openings,
                "services": payload_services,
                "service_opening_links": payload_links,
            }
        ).model_dump(mode="json")
    except ValidationError as exc:
        raise Phase8AdjudicatedPayloadError("ADJUDICATED_PAYLOAD_INVALID") from exc
    if len(payload["openings"]) != proposal.get("proposed_opening_count") or len(
        payload["services"]
    ) != proposal.get("proposed_service_count"):
        raise Phase8AdjudicatedPayloadError("ADJUDICATED_COUNT_MISMATCH")
    return Phase8AdjudicatedPayload(
        payload=payload,
        payload_sha256=normalised_submission_payload_sha256(payload),
        source_run_id=_nonblank(final_state.get("source_run_id")),
        adjudicated_run_id=_nonblank(final_state.get("run_id")),
        artifact_digests={
            "adjudicated_proposal": proposal_hash,
            "adjudicated_final_state": final_state_hash,
            "adjudicated_diff": diff_hash,
            "human_adjudication_comparison": comparison_hash,
        },
    )


def _validate_receipt_graph(
    *,
    estimate_id: str,
    proposal: dict[str, Any],
    proposal_hash: str,
    final_state: dict[str, Any],
    final_state_hash: str,
    diff: dict[str, Any],
    diff_hash: str,
    comparison: dict[str, Any],
    comparison_hash: str,
) -> None:
    if proposal.get("schema") != PROPOSAL_SCHEMA:
        raise Phase8AdjudicatedPayloadError("ADJUDICATED_PROPOSAL_INVALID")
    _require_no_write(proposal, include_runtime=True)
    openings = _require_list(proposal.get("openings"))
    services = _require_list(proposal.get("services"))
    defect_ids = {_nonblank(item.get("external_defect_id")) for item in openings}
    if (
        proposal.get("proposed_opening_count") != len(openings)
        or proposal.get("proposed_service_count") != len(services)
        or proposal.get("defect_count") != len(defect_ids)
        or proposal.get("supported_defect_count") != proposal.get("defect_count")
        or proposal.get("limited_defect_count") != 0
        or proposal.get("limitations") != []
    ):
        raise Phase8AdjudicatedPayloadError("ADJUDICATED_PROPOSAL_INVALID")

    if (
        final_state.get("schema") != FINAL_STATE_SCHEMA
        or final_state.get("status") != FINAL_STATE_STATUS
        or final_state.get("estimate_id") != estimate_id
        or final_state.get("proposal_sha256") != proposal_hash
        or _reference_hash(final_state.get("diff_receipt")) != diff_hash
        or final_state.get("withheld_tool") != WITHHELD_TOOL
    ):
        raise Phase8AdjudicatedPayloadError("ADJUDICATED_FINAL_STATE_INVALID")
    _require_no_write(final_state, include_runtime=True)
    protected = final_state.get("protected_state")
    if (
        not isinstance(protected, dict)
        or protected.get("protected_state_unchanged") is not True
        or protected.get("changed_components") != []
        or protected.get("before_fingerprint") != protected.get("after_fingerprint")
        or protected.get("before_counts") != protected.get("after_counts")
        or protected.get("before_component_fingerprints")
        != protected.get("after_component_fingerprints")
    ):
        raise Phase8AdjudicatedPayloadError("ADJUDICATED_PROTECTED_STATE_INVALID")

    if (
        diff.get("schema") != DIFF_SCHEMA
        or diff.get("scope") != DIFF_SCOPE
        or diff.get("estimate_id") != estimate_id
        or diff.get("revision_proposal_sha256") != proposal_hash
    ):
        raise Phase8AdjudicatedPayloadError("ADJUDICATED_DIFF_INVALID")
    _require_no_write(diff, include_runtime=False)

    defects = _require_list(comparison.get("defects"))
    if (
        comparison.get("schema") != COMPARISON_SCHEMA
        or comparison.get("status") != "PASS"
        or comparison.get("estimate_id") != estimate_id
        or comparison.get("mismatch_defect_count") != 0
        or comparison.get("passed_defect_count") != comparison.get("defect_count")
        or comparison.get("defect_count") != len(defects)
        or _reference_hash(comparison.get("revision_proposal")) != proposal_hash
        or _reference_hash(comparison.get("final_state_receipt")) != final_state_hash
    ):
        raise Phase8AdjudicatedPayloadError("ADJUDICATED_COMPARISON_INVALID")
    _require_no_write(comparison, include_runtime=False)
    source_run_id = final_state.get("source_run_id")
    if source_run_id != diff.get("run_id") or source_run_id != comparison.get("source_run_id"):
        raise Phase8AdjudicatedPayloadError("ADJUDICATED_RUN_BINDING_INVALID")
    if diff.get("human_comparison_sha256") == comparison_hash:
        raise Phase8AdjudicatedPayloadError("ADJUDICATED_RECEIPT_CYCLE_INVALID")


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    if not isinstance(path, Path) or not path.is_file():
        raise Phase8AdjudicatedPayloadError("ADJUDICATED_ARTIFACT_MISSING")
    try:
        raw = path.read_bytes()
        if not raw or len(raw) > MAX_ARTIFACT_BYTES:
            raise Phase8AdjudicatedPayloadError("ADJUDICATED_ARTIFACT_INVALID")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise Phase8AdjudicatedPayloadError("ADJUDICATED_ARTIFACT_INVALID") from exc
    if not isinstance(value, dict):
        raise Phase8AdjudicatedPayloadError("ADJUDICATED_ARTIFACT_INVALID")
    return value, sha256_hex(raw)


def _require_no_write(value: dict[str, Any], *, include_runtime: bool) -> None:
    names = ["database_write_performed", "gateway_call_performed"]
    if "canonical_write_performed" in value:
        names.append("canonical_write_performed")
    if include_runtime:
        names.append("runtime_inference_performed")
    if any(value.get(name) is not False for name in names):
        raise Phase8AdjudicatedPayloadError("ADJUDICATED_WRITE_CLAIM_INVALID")


def _reference_hash(value: object) -> str:
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        raise Phase8AdjudicatedPayloadError("ADJUDICATED_REFERENCE_INVALID")
    _nonblank(value.get("path"))
    return _nonblank(value.get("sha256"))


def _require_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise Phase8AdjudicatedPayloadError("ADJUDICATED_ARTIFACT_INVALID")
    return value


def _optional_fields(value: dict[str, Any], names: set[str]) -> dict[str, Any]:
    return {name: value[name] for name in sorted(names) if name in value}


def _nonblank(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Phase8AdjudicatedPayloadError("ADJUDICATED_ARTIFACT_INVALID")
    return value.strip()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


__all__ = [
    "Phase8AdjudicatedPayload",
    "Phase8AdjudicatedPayloadError",
    "derive_phase8_adjudicated_payload",
]
