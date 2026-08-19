"""Fail-closed, no-write preflight for an adjudicated Physical Model proposal.

This command validates the exact offline adjudicated proposal and the live
canonical baseline before a human may request an initial Physical Model write.
It never calls OpenClaw, an HTTP endpoint, or a canonical write/lock service.
The only permitted mutation is writing one new JSON receipt to a fresh output
directory supplied by the operator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from create_adjudicated_proposal_revision import (
    AdjudicatedProposalError,
    build_revision,
    validate_adjudicated_revision,
)
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from classifire.blind_visual_inventory import validate_blind_reconciliation_payload
from classifire.canonical_models import (
    Defect,
    EvidenceSource,
    Package15CandidateRequirement,
    PhysicalModelLock,
    RepairStrategy,
    RepairStrategyLock,
    ServiceMaterialHypothesis,
    ServiceOpeningLink,
    SystemRequiredComponent,
)
from classifire.commercial_models import (
    AuditTrail,
    CommercialMethodLock,
    CommercialRecoveryRecord,
    ComponentRequirementReconciliation,
    EstimateCertificate,
    GateEvidence,
    LabourActivity,
    PriceAnomalyReview,
    PricingComponent,
    Quantity,
    QuantityFormulaInput,
)
from classifire.db import SessionLocal
from classifire.models import (
    Approval,
    AuditEvent,
    Estimate,
    EstimateLine,
    Opening,
    RuleEvaluation,
    Service,
)
from classifire.physical_model_submission_schema import (
    AgentInitialPhysicalModelInput,
    AgentOpeningInput,
    AgentServiceInput,
)
from classifire.services.adjudicated_physical_submission import (
    CONTROLLED_CANONICAL_WRITER_POLICY_VERSION,
    controlled_writer_implementation_hashes,
)
from classifire.services.image_variant_resolution import (
    ImageVariantResolutionError,
    load_image_variant_resolution,
    validated_mandatory_secondary_paths,
    validated_primary_paths,
)
from classifire.services.linked_image_retrieval import preferred_verified_linked_path
from classifire.services.physical_scope import is_blank_opening_type
from classifire.services.protected_state_fingerprint import (
    PROTECTED_STATE_FINGERPRINT_VERSION,
    protected_component_fingerprints,
    protected_state_counts,
    protected_state_fingerprint,
    protected_state_snapshot_from_session,
)
from classifire.services.workflow import WorkflowAction
from classifire.services.workflow_guard import check_estimate_action
from classifire.visual_validation import visual_validator_approved

PREFLIGHT_SCHEMA = "CLASSIFIRE-ADJUDICATED-CANONICALISATION-PREFLIGHT-v2"
PREFLIGHT_FILENAME = "24-adjudicated-canonicalisation-preflight.json"
ADJUDICATED_PROPOSAL_SCHEMA = "CLASSIFIRE-ADJUDICATED-PROPOSAL-v1"
ADJUDICATED_FINAL_STATE_SCHEMA = "CLASSIFIRE-ADJUDICATED-PROPOSAL-ONLY-FINAL-STATE-v1"
ADJUDICATED_DIFF_SCHEMA = "CLASSIFIRE-ADJUDICATED-PROPOSAL-DIFF-v1"
ADJUDICATION_COMPARISON_SCHEMA = "CLASSIFIRE-HUMAN-ADJUDICATION-PROPOSAL-COMPARISON-v1"
HUMAN_ADJUDICATION_SCHEMA = "CLASSIFIRE-HUMAN-ADJUDICATION-v1"
VISUAL_FINAL_STATE_STATUS = "VISUAL_VALIDATED_PROPOSAL_READY"
SOURCE_VISUAL_FINAL_STATE_SCHEMA = "CLASSIFIRE-VISUAL-PROPOSAL-ONLY-FINAL-STATE-v1"
LEGACY_SOURCE_WITHHELD_TOOL = "classifire_submit_initial_physical_model"
TOPOLOGY_HIGHEST_DETAIL_POLICY_VERSION = (
    "CLASSIFIRE-FIRESEAL-PHYSICAL-v8-HIGHEST-USABLE-DETAIL-TOPOLOGY"
)
VISUAL_GATE_HIGHEST_DETAIL_POLICY_VERSION = (
    "CLASSIFIRE-FIRESEAL-VISUAL-GATE-v6-HIGHEST-USABLE-DETAIL"
)
MAX_ARTIFACT_BYTES = 5 * 1024 * 1024

PROPOSAL_FILENAME = "20-fireseal-merged-proposal-adjudicated.json"
FINAL_STATE_FILENAME = "21-adjudicated-proposal-only-final-state.json"
DIFF_FILENAME = "20-adjudicated-proposal-diff.json"
COMPARISON_FILENAME = "22-human-adjudication-proposal-comparison-v1.json"
PREPARED_FILENAME = "00-prepared.json"
LINKED_INVENTORY_FILENAME = "16b-photo-inventory-linked.json"
LINKED_MATERIALIZATION_FILENAME = "16b-photo-materialization.json"
IMAGE_VARIANT_FILENAME = "16c-image-variant-resolution.json"
MAX_VISUAL_DEFECTS = 100


class CanonicalisationPreflightError(RuntimeError):
    """Raised when an artifact or the current canonical state is not eligible."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _nonblank(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CanonicalisationPreflightError(f"{label} must be a nonblank string.")
    return value.strip()


def _sha256(value: Any, *, label: str) -> str:
    candidate = _nonblank(value, label=label).upper()
    if len(candidate) != 64 or any(character not in "0123456789ABCDEF" for character in candidate):
        raise CanonicalisationPreflightError(f"{label} must be a SHA-256 hexadecimal digest.")
    return candidate


def _false(value: Any, *, label: str) -> None:
    if value is not False:
        raise CanonicalisationPreflightError(f"{label} must be false.")


def _read_json(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        raise CanonicalisationPreflightError(f"{label} is missing or is not a regular file.")
    size = path.stat().st_size
    if size <= 0 or size > MAX_ARTIFACT_BYTES:
        raise CanonicalisationPreflightError(
            f"{label} exceeds the permitted artifact-size boundary."
        )
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CanonicalisationPreflightError(f"{label} is not valid UTF-8 JSON.") from exc
    if not isinstance(payload, dict):
        raise CanonicalisationPreflightError(f"{label} root must be an object.")
    return payload, _sha256_bytes(raw)


def _require_within(root: Path, value: Any, *, label: str) -> Path:
    raw = _nonblank(value, label=label)
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved_root = root.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise CanonicalisationPreflightError(
            f"{label} must resolve within its approved artifact directory."
        ) from exc
    if not resolved.is_file():
        raise CanonicalisationPreflightError(f"{label} is not a regular file.")
    return resolved


def _assert_binding(
    path: Path,
    declared_sha256: Any,
    *,
    label: str,
) -> tuple[dict[str, Any], str]:
    payload, actual_sha256 = _read_json(path, label=label)
    expected_sha256 = _sha256(declared_sha256, label=f"{label} SHA-256")
    if actual_sha256 != expected_sha256:
        raise CanonicalisationPreflightError(f"{label} bytes do not match their declared SHA-256.")
    return payload, actual_sha256


def _safe_path_for_receipt(path: Path) -> str:
    root = Path(__file__).resolve().parents[1]
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.name


def _receipt_reference(path: Path, sha256: str) -> dict[str, str]:
    return {"path": _safe_path_for_receipt(path), "sha256": sha256}


def _implementation_hashes() -> dict[str, str]:
    try:
        writer_hashes = controlled_writer_implementation_hashes()
    except Exception as exc:
        raise CanonicalisationPreflightError(
            "Protected-state fingerprint or controlled-writer implementation is unavailable "
            "for receipt binding."
        ) from exc
    return writer_hashes


def _require_schema(payload: dict[str, Any], expected: str, *, label: str) -> None:
    if payload.get("schema") != expected:
        raise CanonicalisationPreflightError(f"{label} has an unsupported schema.")


def _source_visual_receipt_contract(source_final: dict[str, Any]) -> str:
    """Validate the canonical-write boundary of a source visual final receipt.

    The retained full-resolution UAT predates a schema on this particular final
    receipt and truthfully involved model/Gateway inference.  It must therefore
    be admitted only through this narrow legacy shape, never by accepting an
    arbitrary schema-less object.  Future schema-v1 receipts carry explicit
    operation flags; only the database/canonical-write flags are no-write
    requirements because inference itself is an expected source-run action.
    """

    schema = source_final.get("schema")
    if schema == SOURCE_VISUAL_FINAL_STATE_SCHEMA:
        _false(
            source_final.get("database_write_performed"),
            label="Source visual final-state receipt.database_write_performed",
        )
        for field in ("gateway_call_performed", "runtime_inference_performed"):
            if not isinstance(source_final.get(field), bool):
                raise CanonicalisationPreflightError(
                    f"Source visual final-state receipt.{field} must be a boolean."
                )
        if source_final.get("withheld_tool") != LEGACY_SOURCE_WITHHELD_TOOL:
            raise CanonicalisationPreflightError(
                "Source visual final-state receipt does not name the withheld canonical-write tool."
            )
        return "SCHEMA_V1_EXPLICIT_OPERATION_FLAGS"

    if schema is None:
        # This precisely identifies the retained, pre-schema visual receipt.
        # Do not infer generic non-write authority from a missing schema alone.
        if source_final.get("withheld_tool") != LEGACY_SOURCE_WITHHELD_TOOL:
            raise CanonicalisationPreflightError(
                "Legacy source visual final-state receipt does not name the "
                "withheld canonical-write tool."
            )
        if "database_write_performed" in source_final:
            _false(
                source_final.get("database_write_performed"),
                label="Legacy source visual final-state receipt.database_write_performed",
            )
        for field in ("gateway_call_performed", "runtime_inference_performed"):
            if field in source_final and not isinstance(source_final.get(field), bool):
                raise CanonicalisationPreflightError(
                    "Legacy source visual final-state receipt."
                    f"{field} must be a boolean when present."
                )
        return "LEGACY_SCHEMALESS_WITHHELD_TOOL_V0"

    raise CanonicalisationPreflightError(
        "Source visual final-state receipt has an unsupported schema."
    )


def _read_json_array(path: Path, *, label: str) -> tuple[list[dict[str, Any]], str]:
    if not path.is_file():
        raise CanonicalisationPreflightError(f"{label} is missing or is not a regular file.")
    size = path.stat().st_size
    if size <= 0 or size > MAX_ARTIFACT_BYTES:
        raise CanonicalisationPreflightError(
            f"{label} exceeds the permitted artifact-size boundary."
        )
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CanonicalisationPreflightError(f"{label} is not valid UTF-8 JSON.") from exc
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise CanonicalisationPreflightError(f"{label} must be an array of objects.")
    return payload, _sha256_bytes(raw)


def _require_rows(payload: dict[str, Any], key: str, *, label: str) -> list[dict[str, Any]]:
    rows = payload.get(key)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise CanonicalisationPreflightError(f"{label}.{key} must be an array of objects.")
    return rows


def _proposal_topology_by_defect(
    proposal: dict[str, Any],
    *,
    label: str,
) -> tuple[dict[str, dict[str, list[dict[str, Any]]]], dict[str, dict[str, int]]]:
    """Return a complete, deterministic topology projection keyed by external defect ID."""

    openings = _require_rows(proposal, "openings", label=label)
    services = _require_rows(proposal, "services", label=label)
    opening_by_code: dict[str, dict[str, Any]] = {}
    openings_by_defect: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, opening in enumerate(openings, start=1):
        code = _nonblank(opening.get("opening_code"), label=f"{label} Opening {index} code")
        external_defect_id = _nonblank(
            opening.get("external_defect_id"),
            label=f"{label} Opening {code} external_defect_id",
        )
        if code in opening_by_code:
            raise CanonicalisationPreflightError(f"{label} repeats Opening code {code!r}.")
        opening_by_code[code] = opening
        openings_by_defect[external_defect_id].append(opening)

    services_by_defect: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_service_codes: set[str] = set()
    for index, service in enumerate(services, start=1):
        service_code = _nonblank(service.get("service_code"), label=f"{label} Service {index} code")
        if service_code in seen_service_codes:
            raise CanonicalisationPreflightError(f"{label} repeats Service code {service_code!r}.")
        seen_service_codes.add(service_code)
        opening_codes = service.get("opening_codes")
        if not isinstance(opening_codes, list) or not opening_codes:
            raise CanonicalisationPreflightError(
                f"{label} Service {service_code} opening_codes must be a nonempty array."
            )
        normalized_codes = [
            _nonblank(value, label=f"{label} Service {service_code} opening code")
            for value in opening_codes
        ]
        if len(normalized_codes) != len(set(normalized_codes)):
            raise CanonicalisationPreflightError(
                f"{label} Service {service_code} repeats an Opening code."
            )
        primary = _nonblank(
            service.get("primary_opening_code"),
            label=f"{label} Service {service_code} primary_opening_code",
        )
        if primary not in normalized_codes:
            raise CanonicalisationPreflightError(
                f"{label} Service {service_code} primary Opening is not linked."
            )
        missing_codes = sorted(set(normalized_codes) - set(opening_by_code))
        if missing_codes:
            raise CanonicalisationPreflightError(
                f"{label} Service {service_code} references unknown Openings: "
                + ", ".join(missing_codes)
            )
        external_defect_ids = {
            _nonblank(
                opening_by_code[code].get("external_defect_id"),
                label=f"{label} Opening {code} external_defect_id",
            )
            for code in normalized_codes
        }
        if len(external_defect_ids) != 1:
            raise CanonicalisationPreflightError(
                f"{label} Service {service_code} crosses defects without authority."
            )
        services_by_defect[external_defect_ids.pop()].append(service)

    topologies: dict[str, dict[str, list[dict[str, Any]]]] = {}
    counts: dict[str, dict[str, int]] = {}
    for external_defect_id in sorted(set(openings_by_defect) | set(services_by_defect)):
        defect_openings = openings_by_defect.get(external_defect_id, [])
        defect_services = services_by_defect.get(external_defect_id, [])
        if not defect_openings:
            raise CanonicalisationPreflightError(
                f"{label} has Services without an Opening for defect {external_defect_id}."
            )

        def normalized_opening(row: dict[str, Any]) -> dict[str, Any]:
            return json.loads(json.dumps(row, sort_keys=True, ensure_ascii=False, allow_nan=False))

        def normalized_service(row: dict[str, Any]) -> dict[str, Any]:
            value = json.loads(json.dumps(row, sort_keys=True, ensure_ascii=False, allow_nan=False))
            value["opening_codes"] = sorted(str(code).strip() for code in value["opening_codes"])
            return value

        topologies[external_defect_id] = {
            "openings": sorted(
                (normalized_opening(row) for row in defect_openings),
                key=lambda row: str(row["opening_code"]),
            ),
            "services": sorted(
                (normalized_service(row) for row in defect_services),
                key=lambda row: str(row["service_code"]),
            ),
        }
        counts[external_defect_id] = {
            "openings": len(defect_openings),
            "services": len(defect_services),
        }
    return topologies, counts


_VISUAL_OPENING_SEMANTIC_FIELDS = (
    "location",
    "substrate_type",
    "substrate_plane",
    "substrate_thickness_mm",
    "orientation",
    "opening_type",
    "width_mm",
    "height_mm",
    "diameter_mm",
)
_VISUAL_SERVICE_SEMANTIC_FIELDS = (
    "service_type",
    "material",
    "nominal_size_mm",
    "outside_diameter_mm",
    "width_mm",
    "height_mm",
    "insulation_type",
    "insulation_thickness_mm",
    "quantity",
    "centre_x_mm",
    "centre_y_mm",
    "link_type",
)


def _normalised_semantic_value(value: Any) -> Any:
    """Normalize presentation-only string differences without dropping physical meaning."""

    if isinstance(value, str):
        return " ".join(value.strip().split()).casefold()
    return value


def _visual_semantic_topology(
    proposal: dict[str, Any],
    *,
    external_defect_id: str,
    label: str,
) -> list[dict[str, Any]]:
    """Project one visual model into ID-independent physical graph semantics.

    The merge stage deliberately renumbers codes and can add non-physical notes,
    FRL defaults, confidence, and evidence-status detail.  Those deterministic
    presentation changes are excluded, while opening dimensions/types/substrate
    and every service-to-opening relationship remain part of the comparison.
    """

    topologies, _ = _proposal_topology_by_defect(proposal, label=label)
    topology = topologies.get(external_defect_id)
    if topology is None:
        raise CanonicalisationPreflightError(
            f"{label} does not contain defect {external_defect_id}."
        )
    openings = topology["openings"]
    services = topology["services"]
    opening_by_code = {
        _nonblank(row.get("opening_code"), label=f"{label} opening code"): row for row in openings
    }

    def opening_descriptor(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "blank_opening": is_blank_opening_type(row.get("opening_type")),
            **{
                field: _normalised_semantic_value(row.get(field))
                for field in _VISUAL_OPENING_SEMANTIC_FIELDS
            },
        }

    opening_descriptor_by_code = {
        code: opening_descriptor(row) for code, row in opening_by_code.items()
    }

    def sort_key(value: dict[str, Any]) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def service_descriptor(row: dict[str, Any]) -> dict[str, Any]:
        opening_codes = [
            _nonblank(value, label=f"{label} visual service opening code")
            for value in row["opening_codes"]
        ]
        primary_code = _nonblank(
            row.get("primary_opening_code"),
            label=f"{label} visual service primary opening code",
        )
        return {
            "service": {
                field: _normalised_semantic_value(row.get(field))
                for field in _VISUAL_SERVICE_SEMANTIC_FIELDS
            },
            "primary_opening": opening_descriptor_by_code[primary_code],
            "linked_openings": sorted(
                (opening_descriptor_by_code[code] for code in opening_codes),
                key=sort_key,
            ),
        }

    descriptors: list[dict[str, Any]] = []
    for opening_code, opening in opening_by_code.items():
        associated_services = [
            service_descriptor(service)
            for service in services
            if opening_code in service["opening_codes"]
        ]
        descriptors.append(
            {
                "opening": opening_descriptor(opening),
                "services": sorted(associated_services, key=sort_key),
            }
        )
    return sorted(descriptors, key=sort_key)


def _require_visual_model_source_semantic_match(
    *,
    source_proposal: dict[str, Any],
    model: dict[str, Any],
    external_defect_id: str,
    defect_index: int,
) -> None:
    source_semantics = _visual_semantic_topology(
        source_proposal,
        external_defect_id=external_defect_id,
        label="Source visual proposal",
    )
    model_semantics = _visual_semantic_topology(
        model,
        external_defect_id=external_defect_id,
        label=f"Visual model {defect_index}",
    )
    if source_semantics != model_semantics:
        raise CanonicalisationPreflightError(
            f"Visual model {defect_index} does not semantically bind the source proposal topology."
        )


def _validate_adjudication_change_chain(
    *,
    source_proposal: dict[str, Any],
    adjudicated_proposal: dict[str, Any],
    human_adjudication: dict[str, Any],
    diff: dict[str, Any],
    comparison: dict[str, Any],
) -> tuple[list[str], dict[str, dict[str, int]]]:
    """Fail closed unless every actual topology revision is an explicit human decision."""

    source_topologies, source_counts = _proposal_topology_by_defect(
        source_proposal, label="Source visual proposal"
    )
    revised_topologies, revised_counts = _proposal_topology_by_defect(
        adjudicated_proposal, label="Adjudicated proposal"
    )
    if set(source_topologies) != set(revised_topologies):
        raise CanonicalisationPreflightError(
            "Adjudicated proposal changes the represented external-defect set."
        )
    changed_ids = sorted(
        external_defect_id
        for external_defect_id in source_topologies
        if source_topologies[external_defect_id] != revised_topologies[external_defect_id]
    )

    decisions = _require_rows(human_adjudication, "decisions", label="Human adjudication record")
    decision_by_id: dict[str, str] = {}
    for index, decision in enumerate(decisions, start=1):
        external_defect_id = _nonblank(
            decision.get("external_defect_id"),
            label=f"Human adjudication decision {index} external_defect_id",
        )
        name = _nonblank(
            decision.get("decision"), label=f"Human adjudication decision {index} decision"
        )
        if external_defect_id in decision_by_id:
            raise CanonicalisationPreflightError(
                f"Human adjudication repeats external defect ID {external_defect_id!r}."
            )
        decision_by_id[external_defect_id] = name
    if set(decision_by_id) != set(changed_ids):
        raise CanonicalisationPreflightError(
            "Every adjudicated topology change must have exactly one human decision."
        )

    changes = _require_rows(diff, "changes", label="Adjudicated diff receipt")
    change_by_id: dict[str, dict[str, Any]] = {}
    for index, change in enumerate(changes, start=1):
        external_defect_id = _nonblank(
            change.get("external_defect_id"),
            label=f"Adjudicated diff change {index} external_defect_id",
        )
        if external_defect_id in change_by_id:
            raise CanonicalisationPreflightError(
                f"Adjudicated diff repeats external defect ID {external_defect_id!r}."
            )
        change_by_id[external_defect_id] = change
    if set(change_by_id) != set(changed_ids):
        raise CanonicalisationPreflightError(
            "Adjudicated diff must describe exactly the actual topology changes."
        )
    for external_defect_id in changed_ids:
        change = change_by_id[external_defect_id]
        if (
            _nonblank(
                change.get("decision"), label=f"Adjudicated diff {external_defect_id} decision"
            )
            != decision_by_id[external_defect_id]
        ):
            raise CanonicalisationPreflightError(
                "Adjudicated diff decision does not match human adjudication for "
                f"{external_defect_id}."
            )
        for key, expected in (
            ("before", source_counts[external_defect_id]),
            ("after", revised_counts[external_defect_id]),
        ):
            value = change.get(key)
            if value != expected:
                raise CanonicalisationPreflightError(
                    f"Adjudicated diff {key} counts do not match topology for {external_defect_id}."
                )

    all_counts = diff.get("counts")
    if (
        not isinstance(all_counts, dict)
        or all_counts.get("before")
        != {
            "openings": sum(value["openings"] for value in source_counts.values()),
            "services": sum(value["services"] for value in source_counts.values()),
        }
        or all_counts.get("after")
        != {
            "openings": sum(value["openings"] for value in revised_counts.values()),
            "services": sum(value["services"] for value in revised_counts.values()),
        }
    ):
        raise CanonicalisationPreflightError(
            "Adjudicated diff aggregate counts do not match source and revised topology."
        )

    comparison_rows = _require_rows(comparison, "defects", label="Adjudicated comparison receipt")
    comparison_by_id: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(comparison_rows, start=1):
        external_defect_id = _nonblank(
            row.get("external_defect_id"),
            label=f"Adjudicated comparison defect {index} external_defect_id",
        )
        if external_defect_id in comparison_by_id:
            raise CanonicalisationPreflightError(
                f"Adjudicated comparison repeats external defect ID {external_defect_id!r}."
            )
        comparison_by_id[external_defect_id] = row
    if set(comparison_by_id) != set(changed_ids):
        raise CanonicalisationPreflightError(
            "Adjudicated comparison must cover exactly the changed defects."
        )
    for external_defect_id in changed_ids:
        row = comparison_by_id[external_defect_id]
        if (
            row.get("status") != "PASS"
            or _nonblank(
                row.get("decision"),
                label=f"Adjudicated comparison {external_defect_id} decision",
            )
            != decision_by_id[external_defect_id]
        ):
            raise CanonicalisationPreflightError(
                f"Adjudicated comparison does not pass for human decision {external_defect_id}."
            )
    if (
        comparison.get("defect_count") != len(changed_ids)
        or comparison.get("passed_defect_count") != len(changed_ids)
        or comparison.get("mismatch_defect_count") != 0
    ):
        raise CanonicalisationPreflightError(
            "Adjudicated comparison aggregate result is inconsistent with human decisions."
        )
    return changed_ids, source_counts


def _require_deterministic_adjudicated_revision(
    *,
    source_proposal: dict[str, Any],
    source_proposal_sha256: str,
    source_final_state: dict[str, Any],
    source_final_state_sha256: str,
    source_run_id: str,
    estimate_id: str,
    human_adjudication: dict[str, Any],
    human_adjudication_sha256: str,
    human_adjudication_path: Path,
    historical_comparison_sha256: str,
    protected_state: dict[str, Any],
    adjudicated_proposal: dict[str, Any],
    adjudicated_proposal_sha256: str,
    diff: dict[str, Any],
) -> None:
    """Require the proposal/diff to be the exact pure human-adjudication revision.

    Human decisions intentionally do not restate every visual field.  The
    generator therefore preserves source attributes that a decision does not
    explicitly change.  Rebuilding from the bound source and decision is the
    only reliable way to reject a silent opening/service mutation in an
    otherwise human-approved defect.
    """

    try:
        expected_proposal, expected_diff = build_revision(
            {
                "proposal": source_proposal,
                "proposal_sha256": source_proposal_sha256,
                "source_state": source_final_state,
                "source_state_sha256": source_final_state_sha256,
                "adjudication": human_adjudication,
                "adjudication_sha256": human_adjudication_sha256,
                "adjudication_path": human_adjudication_path.resolve(strict=True),
                "comparison_sha256": historical_comparison_sha256,
                "estimate_id": estimate_id,
                "run_id": source_run_id,
                "protected_state": protected_state,
                "openings": _require_rows(
                    source_proposal,
                    "openings",
                    label="Source visual proposal",
                ),
                "services": _require_rows(
                    source_proposal,
                    "services",
                    label="Source visual proposal",
                ),
            }
        )
    except (AdjudicatedProposalError, OSError) as exc:
        raise CanonicalisationPreflightError(
            "Adjudicated proposal cannot be deterministically rebuilt from the "
            "bound human decision."
        ) from exc

    if expected_proposal != adjudicated_proposal:
        raise CanonicalisationPreflightError(
            "Adjudicated proposal contains physical fields not produced by the "
            "bound human-decision revision."
        )
    expected_diff["revision_proposal_sha256"] = adjudicated_proposal_sha256
    if expected_diff != diff:
        raise CanonicalisationPreflightError(
            "Adjudicated diff does not match the deterministic human-decision revision."
        )


def _validated_unchanged_protected_state(
    value: Any,
    *,
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CanonicalisationPreflightError(f"{label} has no protected-state evidence.")
    if value.get("fingerprint_version") != PROTECTED_STATE_FINGERPRINT_VERSION:
        raise CanonicalisationPreflightError(f"{label} has an unsupported fingerprint version.")
    before = _sha256(value.get("before_fingerprint"), label=f"{label} before_fingerprint")
    after = _sha256(value.get("after_fingerprint"), label=f"{label} after_fingerprint")
    if before != after or value.get("protected_state_unchanged") is not True:
        raise CanonicalisationPreflightError(f"{label} does not prove unchanged protected state.")
    if value.get("changed_components") != []:
        raise CanonicalisationPreflightError(f"{label} lists changed protected components.")
    before_components = value.get("before_component_fingerprints")
    after_components = value.get("after_component_fingerprints")
    before_counts = value.get("before_counts")
    after_counts = value.get("after_counts")
    if (
        not isinstance(before_components, dict)
        or not isinstance(after_components, dict)
        or not isinstance(before_counts, dict)
        or not isinstance(after_counts, dict)
        or not before_components
        or not before_counts
    ):
        raise CanonicalisationPreflightError(f"{label} has incomplete component/count evidence.")
    if set(before_components) != set(after_components) or set(before_counts) != set(after_counts):
        raise CanonicalisationPreflightError(f"{label} has asymmetric component/count evidence.")
    normalized_before_components = {
        _nonblank(key, label=f"{label} component name"): _sha256(
            component, label=f"{label} component {key}"
        )
        for key, component in before_components.items()
    }
    normalized_after_components = {
        _nonblank(key, label=f"{label} component name"): _sha256(
            component, label=f"{label} component {key}"
        )
        for key, component in after_components.items()
    }
    if normalized_before_components != normalized_after_components:
        raise CanonicalisationPreflightError(f"{label} component fingerprints differ.")
    if before_counts != after_counts or any(
        isinstance(count, bool) or not isinstance(count, int) or count < 0
        for count in before_counts.values()
    ):
        raise CanonicalisationPreflightError(f"{label} component counts are invalid or changed.")
    return {
        "fingerprint_version": value["fingerprint_version"],
        "fingerprint": before,
        "component_fingerprints": normalized_before_components,
        "counts": dict(before_counts),
    }


def _artifact_chain(
    *,
    source_run_dir: Path,
    adjudicated_dir: Path,
    estimate_id: str,
) -> dict[str, Any]:
    """Validate the complete offline proposal/adjudication chain by path and hash."""

    source_run_dir = source_run_dir.resolve(strict=True)
    adjudicated_dir = adjudicated_dir.resolve(strict=True)
    if source_run_dir == adjudicated_dir:
        raise CanonicalisationPreflightError(
            "Source-run and adjudicated-revision directories must be distinct."
        )

    proposal_path = _require_within(
        adjudicated_dir, PROPOSAL_FILENAME, label="Adjudicated proposal"
    )
    final_state_path = _require_within(
        adjudicated_dir, FINAL_STATE_FILENAME, label="Adjudicated final-state receipt"
    )
    diff_path = _require_within(adjudicated_dir, DIFF_FILENAME, label="Adjudicated diff receipt")
    comparison_path = _require_within(
        adjudicated_dir,
        COMPARISON_FILENAME,
        label="Adjudicated comparison receipt",
    )

    proposal, proposal_sha256 = _read_json(proposal_path, label="Adjudicated proposal")
    final_state, final_state_sha256 = _read_json(
        final_state_path, label="Adjudicated final-state receipt"
    )
    diff, diff_sha256 = _read_json(diff_path, label="Adjudicated diff receipt")
    comparison, comparison_sha256 = _read_json(
        comparison_path, label="Adjudicated comparison receipt"
    )

    _require_schema(proposal, ADJUDICATED_PROPOSAL_SCHEMA, label="Adjudicated proposal")
    _require_schema(
        final_state, ADJUDICATED_FINAL_STATE_SCHEMA, label="Adjudicated final-state receipt"
    )
    _require_schema(diff, ADJUDICATED_DIFF_SCHEMA, label="Adjudicated diff receipt")
    _require_schema(
        comparison, ADJUDICATION_COMPARISON_SCHEMA, label="Adjudicated comparison receipt"
    )

    for payload, label in (
        (proposal, "Adjudicated proposal"),
        (final_state, "Adjudicated final-state receipt"),
        (comparison, "Adjudicated comparison receipt"),
    ):
        _false(payload.get("canonical_write_performed"), label=f"{label}.canonical_write_performed")
    for payload, label in (
        (proposal, "Adjudicated proposal"),
        (final_state, "Adjudicated final-state receipt"),
        (diff, "Adjudicated diff receipt"),
        (comparison, "Adjudicated comparison receipt"),
    ):
        if "database_write_performed" in payload:
            _false(
                payload.get("database_write_performed"), label=f"{label}.database_write_performed"
            )
        if "gateway_call_performed" in payload:
            _false(payload.get("gateway_call_performed"), label=f"{label}.gateway_call_performed")

    if proposal.get("revision_scope") != "OFFLINE_HUMAN_ADJUDICATION_ONLY":
        raise CanonicalisationPreflightError(
            "Adjudicated proposal has an unsupported revision scope."
        )
    if final_state.get("status") != "ADJUDICATED_PROPOSAL_READY_FOR_HUMAN_REVIEW":
        raise CanonicalisationPreflightError(
            "Adjudicated final-state receipt is not ready for review."
        )
    if comparison.get("status") != "PASS":
        raise CanonicalisationPreflightError(
            "Adjudicated comparison receipt must pass before preflight."
        )

    for payload, label in (
        (final_state, "Adjudicated final-state receipt"),
        (diff, "Adjudicated diff receipt"),
        (comparison, "Adjudicated comparison receipt"),
    ):
        if payload.get("estimate_id") != estimate_id:
            raise CanonicalisationPreflightError(f"{label} does not match the requested estimate.")

    if (
        _sha256(final_state.get("proposal_sha256"), label="Final-state proposal SHA-256")
        != proposal_sha256
    ):
        raise CanonicalisationPreflightError(
            "Final-state receipt does not bind the adjudicated proposal bytes."
        )
    if final_state.get("proposal_receipt") != PROPOSAL_FILENAME:
        raise CanonicalisationPreflightError(
            "Final-state receipt names an unexpected adjudicated proposal file."
        )
    if (
        _sha256(diff.get("revision_proposal_sha256"), label="Diff revision proposal SHA-256")
        != proposal_sha256
    ):
        raise CanonicalisationPreflightError(
            "Diff receipt does not bind the adjudicated proposal bytes."
        )

    comparison_proposal = comparison.get("revision_proposal")
    comparison_final = comparison.get("final_state_receipt")
    if not isinstance(comparison_proposal, dict) or not isinstance(comparison_final, dict):
        raise CanonicalisationPreflightError(
            "Adjudicated comparison has incomplete proposal/final-state bindings."
        )
    if comparison_proposal.get("path") != PROPOSAL_FILENAME:
        raise CanonicalisationPreflightError(
            "Adjudicated comparison names an unexpected proposal file."
        )
    if (
        _sha256(comparison_proposal.get("sha256"), label="Comparison proposal SHA-256")
        != proposal_sha256
    ):
        raise CanonicalisationPreflightError(
            "Adjudicated comparison does not bind the proposal bytes."
        )
    if comparison_final.get("path") != FINAL_STATE_FILENAME:
        raise CanonicalisationPreflightError(
            "Adjudicated comparison names an unexpected final-state file."
        )
    if (
        _sha256(comparison_final.get("sha256"), label="Comparison final-state SHA-256")
        != final_state_sha256
    ):
        raise CanonicalisationPreflightError(
            "Adjudicated comparison does not bind the final-state bytes."
        )

    source_final_ref = final_state.get("source_final_state")
    source_proposal_ref = final_state.get("source_proposal")
    human_adjudication_ref = final_state.get("human_adjudication")
    diff_ref = final_state.get("diff_receipt")
    if not all(
        isinstance(value, dict)
        for value in (source_final_ref, source_proposal_ref, human_adjudication_ref, diff_ref)
    ):
        raise CanonicalisationPreflightError(
            "Adjudicated final-state receipt has incomplete source bindings."
        )
    if (
        diff_ref.get("path") != DIFF_FILENAME
        or _sha256(diff_ref.get("sha256"), label="Final-state diff SHA-256") != diff_sha256
    ):
        raise CanonicalisationPreflightError(
            "Adjudicated final-state receipt does not bind the diff bytes."
        )

    source_final_path = _require_within(
        source_run_dir,
        source_final_ref.get("path"),
        label="Source visual final-state receipt",
    )
    source_final, source_final_sha256 = _assert_binding(
        source_final_path,
        source_final_ref.get("sha256"),
        label="Source visual final-state receipt",
    )
    source_proposal_path = _require_within(
        source_run_dir,
        source_proposal_ref.get("path"),
        label="Source visual proposal",
    )
    source_proposal, source_proposal_sha256 = _assert_binding(
        source_proposal_path,
        source_proposal_ref.get("sha256"),
        label="Source visual proposal",
    )
    human_adjudication_path = _require_within(
        source_run_dir,
        human_adjudication_ref.get("path"),
        label="Human adjudication record",
    )
    human_adjudication, human_adjudication_sha256 = _assert_binding(
        human_adjudication_path,
        human_adjudication_ref.get("sha256"),
        label="Human adjudication record",
    )

    proposal_source_ref = proposal.get("source_proposal")
    proposal_human_ref = proposal.get("human_adjudication")
    if not isinstance(proposal_source_ref, dict) or not isinstance(proposal_human_ref, dict):
        raise CanonicalisationPreflightError(
            "Adjudicated proposal has incomplete source/adjudication bindings."
        )
    if (
        _require_within(
            source_run_dir,
            proposal_source_ref.get("path"),
            label="Adjudicated proposal.source_proposal",
        )
        != source_proposal_path
        or _sha256(
            proposal_source_ref.get("sha256"),
            label="Adjudicated proposal source-proposal SHA-256",
        )
        != source_proposal_sha256
    ):
        raise CanonicalisationPreflightError(
            "Adjudicated proposal does not bind the source proposal bytes and path."
        )
    if (
        _require_within(
            source_run_dir,
            proposal_human_ref.get("path"),
            label="Adjudicated proposal.human_adjudication",
        )
        != human_adjudication_path
        or _sha256(
            proposal_human_ref.get("sha256"),
            label="Adjudicated proposal human-adjudication SHA-256",
        )
        != human_adjudication_sha256
    ):
        raise CanonicalisationPreflightError(
            "Adjudicated proposal does not bind the human adjudication bytes and path."
        )

    _require_schema(
        human_adjudication, HUMAN_ADJUDICATION_SCHEMA, label="Human adjudication record"
    )
    _false(
        human_adjudication.get("canonical_write_performed"),
        label="Human adjudication record.canonical_write_performed",
    )
    if (
        source_final.get("estimate_id") != estimate_id
        or human_adjudication.get("estimate_id") != estimate_id
    ):
        raise CanonicalisationPreflightError(
            "Source visual/adjudication evidence does not match the requested estimate."
        )
    if source_final.get("status") != VISUAL_FINAL_STATE_STATUS:
        raise CanonicalisationPreflightError(
            "Source visual final-state receipt is not visually validated."
        )
    source_final_receipt_contract = _source_visual_receipt_contract(source_final)
    _false(
        source_final.get("canonical_write_performed"),
        label="Source visual final-state receipt.canonical_write_performed",
    )
    source_final_proposal_path = _require_within(
        source_run_dir,
        source_final.get("proposal_receipt"),
        label="Source visual final-state receipt.proposal_receipt",
    )
    if source_final_proposal_path != source_proposal_path:
        raise CanonicalisationPreflightError(
            "Source visual final-state receipt does not bind the source proposal path."
        )
    for field in (
        "canonical_opening_count",
        "canonical_service_count",
        "canonical_active_lock_count",
    ):
        if source_final.get(field) != 0:
            raise CanonicalisationPreflightError(
                f"Source visual final-state receipt {field} must be zero."
            )

    source_run_id = _nonblank(final_state.get("source_run_id"), label="Final-state source_run_id")
    if (
        source_final.get("run_id") != source_run_id
        or human_adjudication.get("run_id") != source_run_id
    ):
        raise CanonicalisationPreflightError(
            "Source visual/adjudication run identity does not bind to the final-state receipt."
        )
    if comparison.get("source_run_id") != source_run_id or diff.get("run_id") != source_run_id:
        raise CanonicalisationPreflightError("Adjudicated artifact run identity is inconsistent.")
    if (
        _sha256(diff.get("source_final_state_sha256"), label="Diff source final-state SHA-256")
        != source_final_sha256
    ):
        raise CanonicalisationPreflightError(
            "Diff receipt does not bind the source visual final-state bytes."
        )
    if (
        _sha256(diff.get("source_proposal_sha256"), label="Diff source proposal SHA-256")
        != source_proposal_sha256
    ):
        raise CanonicalisationPreflightError(
            "Diff receipt does not bind the source visual proposal bytes."
        )
    if (
        _sha256(diff.get("human_adjudication_sha256"), label="Diff human adjudication SHA-256")
        != human_adjudication_sha256
    ):
        raise CanonicalisationPreflightError(
            "Diff receipt does not bind the human adjudication bytes."
        )

    historical_comparison_ref = human_adjudication.get("comparison_receipt")
    if not isinstance(historical_comparison_ref, dict):
        raise CanonicalisationPreflightError(
            "Human adjudication record has no historical comparison binding."
        )
    historical_comparison_path = _require_within(
        source_run_dir,
        historical_comparison_ref.get("path"),
        label="Historical comparison receipt",
    )
    historical_comparison, historical_comparison_sha256 = _assert_binding(
        historical_comparison_path,
        historical_comparison_ref.get("sha256"),
        label="Historical comparison receipt",
    )
    if (
        _sha256(diff.get("human_comparison_sha256"), label="Diff historical comparison SHA-256")
        != historical_comparison_sha256
    ):
        raise CanonicalisationPreflightError(
            "Diff receipt does not bind the historical comparison bytes."
        )

    comparison_human = comparison.get("human_adjudication")
    if not isinstance(comparison_human, dict):
        raise CanonicalisationPreflightError(
            "Adjudicated comparison has no human-adjudication binding."
        )
    if (
        _sha256(comparison_human.get("sha256"), label="Comparison human adjudication SHA-256")
        != human_adjudication_sha256
    ):
        raise CanonicalisationPreflightError(
            "Adjudicated comparison does not bind the human adjudication bytes."
        )
    if (
        _require_within(
            source_run_dir,
            comparison_human.get("path"),
            label="Adjudicated comparison human-adjudication path",
        )
        != human_adjudication_path
    ):
        raise CanonicalisationPreflightError(
            "Adjudicated comparison does not bind the human adjudication path."
        )

    protected_state = final_state.get("protected_state")
    adjudicated_protected = _validated_unchanged_protected_state(
        protected_state,
        label="Adjudicated final-state receipt",
    )
    source_protected = _validated_unchanged_protected_state(
        source_final.get("protected_state"),
        label="Source visual final-state receipt",
    )
    if source_protected != adjudicated_protected:
        raise CanonicalisationPreflightError(
            "Source and adjudicated final-state protected evidence do not match."
        )
    changed_defects, source_counts = _validate_adjudication_change_chain(
        source_proposal=source_proposal,
        adjudicated_proposal=proposal,
        human_adjudication=human_adjudication,
        diff=diff,
        comparison=comparison,
    )
    _require_deterministic_adjudicated_revision(
        source_proposal=source_proposal,
        source_proposal_sha256=source_proposal_sha256,
        source_final_state=source_final,
        source_final_state_sha256=source_final_sha256,
        source_run_id=source_run_id,
        estimate_id=estimate_id,
        human_adjudication=human_adjudication,
        human_adjudication_sha256=human_adjudication_sha256,
        human_adjudication_path=human_adjudication_path,
        historical_comparison_sha256=historical_comparison_sha256,
        protected_state=protected_state,
        adjudicated_proposal=proposal,
        adjudicated_proposal_sha256=proposal_sha256,
        diff=diff,
    )
    try:
        regenerated_comparison = validate_adjudicated_revision(
            proposal=proposal,
            adjudication=human_adjudication,
        )
    except AdjudicatedProposalError as exc:
        raise CanonicalisationPreflightError(
            "Human adjudication semantics cannot be revalidated against the revised proposal."
        ) from exc
    comparison_core = {
        key: comparison.get(key)
        for key in (
            "schema",
            "status",
            "defect_count",
            "passed_defect_count",
            "mismatch_defect_count",
            "defects",
        )
    }
    if regenerated_comparison.get("status") != "PASS" or comparison_core != regenerated_comparison:
        raise CanonicalisationPreflightError(
            "Adjudicated comparison does not match the regenerated human-decision semantics."
        )

    return {
        "proposal": proposal,
        "proposal_sha256": proposal_sha256,
        "final_state": final_state,
        "final_state_sha256": final_state_sha256,
        "diff": diff,
        "diff_sha256": diff_sha256,
        "comparison": comparison,
        "comparison_sha256": comparison_sha256,
        "source_final_state": source_final,
        "source_final_state_sha256": source_final_sha256,
        "source_proposal": source_proposal,
        "source_proposal_sha256": source_proposal_sha256,
        "human_adjudication": human_adjudication,
        "human_adjudication_sha256": human_adjudication_sha256,
        "historical_comparison": historical_comparison,
        "historical_comparison_sha256": historical_comparison_sha256,
        "source_run_id": source_run_id,
        "source_final_receipt_contract": source_final_receipt_contract,
        "protected_state": protected_state,
        "changed_defects": changed_defects,
        "source_topology_counts": source_counts,
        "references": {
            "adjudicated_proposal": _receipt_reference(proposal_path, proposal_sha256),
            "adjudicated_final_state": _receipt_reference(final_state_path, final_state_sha256),
            "adjudicated_diff": _receipt_reference(diff_path, diff_sha256),
            "adjudication_comparison": _receipt_reference(comparison_path, comparison_sha256),
            "source_visual_final_state": _receipt_reference(source_final_path, source_final_sha256),
            "source_visual_proposal": _receipt_reference(
                source_proposal_path, source_proposal_sha256
            ),
            "human_adjudication": _receipt_reference(
                human_adjudication_path, human_adjudication_sha256
            ),
            "historical_comparison": _receipt_reference(
                historical_comparison_path, historical_comparison_sha256
            ),
        },
    }


def _sha256_file(path: Path, *, label: str, maximum_bytes: int = 64 * 1024 * 1024) -> str:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise CanonicalisationPreflightError(f"{label} is unavailable.") from exc
    if size <= 0 or size > maximum_bytes:
        raise CanonicalisationPreflightError(f"{label} exceeds the permitted file-size boundary.")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(64 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise CanonicalisationPreflightError(f"{label} cannot be read.") from exc
    return digest.hexdigest().upper()


def _cache_manifest(manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            key: (Path(str(value)).name if key == "path" else value)
            for key, value in row.items()
            if key != "path" or value
        }
        for row in manifest
    ]


def _nonnegative_int(value: Any, *, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise CanonicalisationPreflightError(f"{label} must be an integer of at least {minimum}.")
    return value


def _linked_inventory_by_photo_id(
    linked_inventory: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    photos = _require_rows(linked_inventory, "photos", label="Linked-photo inventory")
    declared_count = _nonnegative_int(
        linked_inventory.get("photo_occurrence_count"),
        label="Linked-photo inventory.photo_occurrence_count",
    )
    if declared_count != len(photos):
        raise CanonicalisationPreflightError(
            "Linked-photo inventory occurrence count does not match its photo rows."
        )
    by_photo_id: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(photos, start=1):
        photo_id = _nonblank(row.get("photo_id"), label=f"Linked-photo inventory photo {index}")
        _nonnegative_int(
            row.get("page_number"),
            label=f"Linked-photo inventory {photo_id} page_number",
            minimum=1,
        )
        _nonnegative_int(
            row.get("occurrence"),
            label=f"Linked-photo inventory {photo_id} occurrence",
            minimum=1,
        )
        if photo_id in by_photo_id:
            raise CanonicalisationPreflightError(
                "Linked-photo inventory repeats a photo_id; one occurrence is required per ID."
            )
        by_photo_id[photo_id] = row
    return by_photo_id


def _validate_linked_materialization_items(
    *,
    linked_inventory: dict[str, Any],
    materialization: dict[str, Any],
    inventory_by_photo_id: dict[str, dict[str, Any]],
) -> None:
    """Bind every inventory row to exactly one sanitized retrieval result."""

    items = _require_rows(materialization, "items", label="Linked-photo materialization receipt")
    declared_count = _nonnegative_int(
        materialization.get("photo_occurrence_count"),
        label="Linked-photo materialization receipt.photo_occurrence_count",
    )
    if declared_count != len(items) or declared_count != len(inventory_by_photo_id):
        raise CanonicalisationPreflightError(
            "Linked-photo materialization count does not match the linked-photo inventory."
        )
    items_by_photo_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items, start=1):
        photo_id = _nonblank(
            item.get("photo_id"), label=f"Linked-photo materialization item {index} photo_id"
        )
        if photo_id in items_by_photo_id:
            raise CanonicalisationPreflightError(
                "Linked-photo materialization receipt repeats a photo_id."
            )
        items_by_photo_id[photo_id] = item
    if set(items_by_photo_id) != set(inventory_by_photo_id):
        raise CanonicalisationPreflightError(
            "Linked-photo inventory and materialization do not cover the same photo IDs."
        )

    bound_fields = (
        ("page_number", "page_number"),
        ("full_resolution_required", "full_resolution_required"),
        ("full_resolution_status", "status"),
        ("full_resolution_path", "stored_path"),
        ("full_resolution_sha256", "content_sha256"),
        ("full_resolution_width", "decoded_width"),
        ("full_resolution_height", "decoded_height"),
        ("full_resolution_binding_transform", "thumbnail_transform"),
        ("full_resolution_binding_crop_box", "thumbnail_crop_box_normalized"),
        ("full_resolution_embedded_pixel_sha256", "embedded_pixel_sha256"),
        (
            "full_resolution_usable_detail_gradient_gain_ratio",
            "usable_detail_gradient_gain_ratio",
        ),
        ("full_resolution_usable_detail_residual", "usable_detail_residual"),
        ("full_resolution_usable_detail_matching_tiles", "usable_detail_matching_tiles"),
    )
    for photo_id, inventory_row in inventory_by_photo_id.items():
        item = items_by_photo_id[photo_id]
        for inventory_field, item_field in bound_fields:
            if inventory_row.get(inventory_field) != item.get(item_field):
                raise CanonicalisationPreflightError(
                    "Linked-photo inventory/materialization item mismatch for "
                    f"{photo_id}: {inventory_field}."
                )


def _append_declared_photo_ids(
    value: Any,
    *,
    label: str,
    destination: list[str],
) -> None:
    if not isinstance(value, list):
        raise CanonicalisationPreflightError(f"{label} must be an array of photo IDs.")
    for index, photo_id in enumerate(value, start=1):
        destination.append(_nonblank(photo_id, label=f"{label}[{index}]"))


def _evidence_page_number(value: Any, *, label: str) -> int:
    if isinstance(value, bool):
        raise CanonicalisationPreflightError(f"{label} must be a positive page number.")
    try:
        page = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise CanonicalisationPreflightError(f"{label} must be a positive page number.") from exc
    if page < 1:
        raise CanonicalisationPreflightError(f"{label} must be a positive page number.")
    return page


def _requested_photo_ids_from_bound_evidence(
    db: Session,
    *,
    estimate_id: str,
    external_defect_id: str,
    inventory_by_photo_id: dict[str, dict[str, Any]],
    image_variant_sha256: str,
) -> tuple[list[str], set[int]]:
    """Reconstruct current visual routing after protected-state verification.

    This mirrors the runner's conservative stale-route expansion.  Unlike the
    runtime selector, an unknown declared photo ID is an error rather than a
    silently discarded value: the preflight is validating retained evidence,
    not trying to recover from it.
    """

    defect_rows = list(
        db.scalars(
            select(Defect).where(
                Defect.estimate_id == estimate_id,
                Defect.external_defect_id == external_defect_id,
            )
        ).all()
    )
    if len(defect_rows) != 1:
        raise CanonicalisationPreflightError(
            f"Current canonical evidence has no unique defect {external_defect_id}."
        )
    evidence_rows = list(
        db.scalars(
            select(EvidenceSource)
            .where(
                EvidenceSource.estimate_id == estimate_id,
                EvidenceSource.defect_id == defect_rows[0].id,
                EvidenceSource.status == "active",
            )
            .order_by(EvidenceSource.created_at, EvidenceSource.id)
        ).all()
    )
    requested: list[str] = []
    pages: set[int] = set()
    stale_link_pages: set[int] = set()
    relevant_types = {
        "defect_page_photo_linkage_review",
        "defect_photo_detail_review",
        "defect_photo_reconciliation",
        "defect_page_layout_review",
    }
    for evidence in evidence_rows:
        evidence_type = evidence.evidence_type
        if evidence_type not in relevant_types:
            continue
        page = _evidence_page_number(
            evidence.page_number,
            label=f"Evidence {evidence.id} page_number",
        )
        pages.add(page)
        source = evidence.source_json
        if evidence_type == "defect_page_layout_review":
            continue
        if not isinstance(source, dict):
            raise CanonicalisationPreflightError(
                f"Evidence {evidence.id} has no structured photo-routing source_json."
            )
        if evidence_type == "defect_photo_detail_review":
            requested.append(
                _nonblank(source.get("photo_id"), label=f"Evidence {evidence.id} photo_id")
            )
            continue

        declared_variant_sha = source.get("image_variant_receipt_sha256")
        current_variant = False
        if declared_variant_sha is not None:
            current_variant = (
                _sha256(
                    declared_variant_sha,
                    label=f"Evidence {evidence.id} image-variant SHA-256",
                ).lower()
                == image_variant_sha256.lower()
            )
        if evidence_type == "defect_page_photo_linkage_review":
            routing_keys = (
                ("associated_photo_ids", "uncertain_photo_ids")
                if current_variant
                else ("associated_photo_ids", "uncertain_photo_ids", "ignored_photo_ids")
            )
            for key in routing_keys:
                _append_declared_photo_ids(
                    source.get(key, []),
                    label=f"Evidence {evidence.id} {key}",
                    destination=requested,
                )
            if not current_variant:
                stale_link_pages.add(page)
            continue

        for group_index, group in enumerate(source.get("photo_groups", []), start=1):
            if not isinstance(group, dict):
                raise CanonicalisationPreflightError(
                    f"Evidence {evidence.id} photo_groups[{group_index}] must be an object."
                )
            _append_declared_photo_ids(
                group.get("photo_ids", []),
                label=f"Evidence {evidence.id} photo_groups[{group_index}].photo_ids",
                destination=requested,
            )
        _append_declared_photo_ids(
            source.get("photo_ids_reviewed", []),
            label=f"Evidence {evidence.id} photo_ids_reviewed",
            destination=requested,
        )
        if not current_variant:
            _append_declared_photo_ids(
                source.get("ignored_photo_ids", []),
                label=f"Evidence {evidence.id} ignored_photo_ids",
                destination=requested,
            )

    for photo_id in requested:
        if photo_id not in inventory_by_photo_id:
            raise CanonicalisationPreflightError(
                f"Retained evidence references unknown photo {photo_id}."
            )
    for photo_id, row in sorted(
        inventory_by_photo_id.items(),
        key=lambda item: (
            int(item[1]["page_number"]),
            int(item[1]["occurrence"]),
            item[0],
        ),
    ):
        if (
            int(row["page_number"]) in stale_link_pages
            and not bool(row.get("tiny_artifact"))
            and not bool(row.get("decorative_candidate"))
        ):
            requested.append(photo_id)
    selected = list(dict.fromkeys(requested))
    if not selected:
        raise CanonicalisationPreflightError(
            f"No retained photo evidence is available for defect {external_defect_id}."
        )
    return selected, pages


def _expected_variant_selection(
    *,
    resolution: Any,
    primary_paths: dict[str, Path],
    secondary_paths: dict[str, Path],
    requested_photo_ids: list[str],
) -> tuple[list[tuple[str, str]], dict[tuple[str, str], dict[str, Any]]]:
    """Return all primary/context candidates permitted for the retained manifest."""

    rows_by_candidate = {
        _nonblank(row.get("candidate_id"), label="Image-variant candidate ID"): row
        for row in resolution.rows
    }
    if len(rows_by_candidate) != len(resolution.rows):
        raise CanonicalisationPreflightError("Image-variant resolution repeats a candidate ID.")
    groups_by_photo_id: dict[str, dict[str, Any]] = {}
    for group in resolution.groups:
        if not isinstance(group, dict):
            raise CanonicalisationPreflightError(
                "Image-variant resolution group must be an object."
            )
        _nonblank(group.get("group_id"), label="Image-variant group ID")
        members = group.get("member_occurrences")
        if not isinstance(members, list):
            raise CanonicalisationPreflightError("Image-variant group members must be an array.")
        for member in members:
            if not isinstance(member, dict):
                raise CanonicalisationPreflightError(
                    "Image-variant group member must be an object."
                )
            photo_id = _nonblank(member.get("occurrence_id"), label="Image-variant occurrence ID")
            if photo_id in groups_by_photo_id:
                raise CanonicalisationPreflightError(
                    f"Image-variant resolution maps photo {photo_id} to multiple groups."
                )
            groups_by_photo_id[photo_id] = group

    expected_sequence: list[tuple[str, str]] = []
    seen_candidate_ids: set[str] = set()
    permitted: dict[tuple[str, str], dict[str, Any]] = {}
    for requested_photo_id in requested_photo_ids:
        group = groups_by_photo_id.get(requested_photo_id)
        if group is None:
            raise CanonicalisationPreflightError(
                f"Image-variant resolution has no group for requested photo {requested_photo_id}."
            )
        group_id = _nonblank(group.get("group_id"), label="Image-variant group ID")
        selections: list[tuple[str, str, str]] = [
            (
                _nonblank(
                    group.get("primary_candidate_id"), label="Image-variant primary candidate"
                ),
                "PRIMARY",
                "SELF",
            )
        ]
        secondaries = group.get("mandatory_secondary")
        if not isinstance(secondaries, list):
            raise CanonicalisationPreflightError(
                "Image-variant group mandatory_secondary must be an array."
            )
        for secondary in secondaries:
            if not isinstance(secondary, dict):
                raise CanonicalisationPreflightError(
                    "Image-variant mandatory-secondary entry must be an object."
                )
            selections.append(
                (
                    _nonblank(
                        secondary.get("candidate_id"),
                        label="Image-variant mandatory-secondary candidate",
                    ),
                    "MANDATORY_SECONDARY",
                    str(secondary.get("relationship") or "AMBIGUOUS"),
                )
            )
        for candidate_id, variant_role, relationship in selections:
            # This is the same first-seen de-duplication used when constructing
            # the model-visible attachment list.  A later request may share a
            # group/candidate but must not move that candidate's manifest slot.
            if candidate_id in seen_candidate_ids:
                continue
            candidate = rows_by_candidate.get(candidate_id)
            paths = primary_paths if variant_role == "PRIMARY" else secondary_paths
            path = paths.get(candidate_id)
            if candidate is None or path is None:
                raise CanonicalisationPreflightError(
                    "Image-variant group references a candidate that failed "
                    "central path validation."
                )
            seen_candidate_ids.add(candidate_id)
            expected_sequence.append((requested_photo_id, candidate_id))
            permitted[(requested_photo_id, candidate_id)] = {
                "candidate": candidate,
                "path": Path(path).resolve(),
                "variant_group_id": group_id,
                "variant_role": variant_role,
                "primary_secondary": "PRIMARY" if variant_role == "PRIMARY" else "SECONDARY",
                "relationship_to_primary": relationship,
            }
    return expected_sequence, permitted


def _validate_defect_attachment_manifest(
    *,
    source_run_dir: Path,
    defect_index: int,
    manifest: list[dict[str, Any]],
    expected_detail_sequence: list[tuple[str, str]],
    permitted_candidates: dict[tuple[str, str], dict[str, Any]],
    requested_photo_ids: list[str],
    expected_pages: set[int],
    inventory_by_photo_id: dict[str, dict[str, Any]],
    image_variant_sha256: str,
) -> None:
    """Prove a defect manifest contains exactly its selected detail/context pixels."""

    if not manifest:
        raise CanonicalisationPreflightError(f"Visual manifest {defect_index} has no attachments.")
    if len(expected_detail_sequence) > 38:
        raise CanonicalisationPreflightError(
            f"Visual manifest {defect_index} requires too many detail attachments."
        )
    if len(expected_pages) > 3:
        raise CanonicalisationPreflightError(
            f"Visual manifest {defect_index} requires too many labelled page attachments."
        )

    actual_detail_sequence: list[tuple[str, str]] = []
    labelled_pages: set[int] = set()
    contact_entries: list[tuple[dict[str, Any], Path, str]] = []
    detail_entries: list[tuple[dict[str, Any], Path, str]] = []
    requested_set = set(requested_photo_ids)
    last_role_stage = -1
    last_labelled_page = 0
    for attachment_index, entry in enumerate(manifest, start=1):
        if entry.get("attachment_index") != attachment_index:
            raise CanonicalisationPreflightError(
                f"Visual manifest {defect_index} attachment indexes are not contiguous."
            )
        path = _require_within(
            source_run_dir,
            entry.get("path"),
            label=f"Visual manifest {defect_index} attachment {attachment_index}",
        )
        if entry.get("filename") != path.name:
            raise CanonicalisationPreflightError(
                f"Visual manifest {defect_index} attachment filename is inconsistent."
            )
        expected_sha256 = _sha256(
            entry.get("expected_sha256"),
            label=f"Visual manifest {defect_index} attachment {attachment_index} SHA-256",
        ).lower()
        if (
            _sha256_file(
                path, label=f"Visual manifest {defect_index} attachment {attachment_index}"
            ).lower()
            != expected_sha256
        ):
            raise CanonicalisationPreflightError(
                f"Visual manifest {defect_index} attachment bytes have changed."
            )
        role = _nonblank(entry.get("role"), label=f"Visual manifest {defect_index} attachment role")
        role_stage = {"defect_photo": 0, "labelled_full_page": 1, "contact_sheet": 2}.get(role)
        if role_stage is None or role_stage < last_role_stage:
            raise CanonicalisationPreflightError(
                f"Visual manifest {defect_index} attachment order is inconsistent."
            )
        last_role_stage = role_stage
        if role == "defect_photo":
            requested_photo_id = _nonblank(
                entry.get("requested_photo_id"),
                label=f"Visual manifest {defect_index} requested_photo_id",
            )
            candidate_id = _nonblank(
                entry.get("candidate_id"),
                label=f"Visual manifest {defect_index} candidate_id",
            )
            if requested_photo_id not in requested_set:
                raise CanonicalisationPreflightError(
                    f"Visual manifest {defect_index} names an unrequested photo source."
                )
            expected = permitted_candidates.get((requested_photo_id, candidate_id))
            if expected is None:
                raise CanonicalisationPreflightError(
                    f"Visual manifest {defect_index} is missing the selected high-detail evidence."
                )
            if candidate_id in {candidate for _, candidate in actual_detail_sequence}:
                raise CanonicalisationPreflightError(
                    f"Visual manifest {defect_index} repeats an image-variant candidate."
                )
            candidate = expected["candidate"]
            candidate_photo_id = _nonblank(
                candidate.get("photo_id"), label="Image-variant candidate photo_id"
            )
            inventory_row = inventory_by_photo_id.get(
                candidate_photo_id
            ) or inventory_by_photo_id.get(requested_photo_id)
            if inventory_row is None:
                raise CanonicalisationPreflightError(
                    "Image-variant candidate has no linked-photo inventory row."
                )
            provenance = _nonblank(candidate.get("provenance"), label="Image-variant provenance")
            candidate_sha256 = _sha256(
                candidate.get("file_sha256"), label="Image-variant candidate SHA-256"
            ).lower()
            expected_fields = {
                "photo_id": candidate_photo_id,
                "page": candidate.get("page_number"),
                "variant_group_id": expected["variant_group_id"],
                "variant_role": expected["variant_role"],
                "primary_secondary": expected["primary_secondary"],
                "relationship_to_primary": expected["relationship_to_primary"],
                "provenance": provenance,
                "source_resolution": (
                    "linked_original"
                    if provenance == "REPORT_LINKED_ORIGINAL"
                    else "embedded_or_occurrence_context"
                ),
                "full_resolution_status": (
                    str(inventory_row.get("full_resolution_status") or "").strip().upper() or None
                ),
                "pixel_width": candidate.get("width"),
                "pixel_height": candidate.get("height"),
                "expected_sha256": candidate_sha256,
            }
            if path != expected["path"] or any(
                entry.get(field) != value for field, value in expected_fields.items()
            ):
                raise CanonicalisationPreflightError(
                    f"Visual manifest {defect_index} candidate metadata does not "
                    "match 16c selection."
                )
            actual_detail_sequence.append((requested_photo_id, candidate_id))
            detail_entries.append((entry, path, expected_sha256))
            continue

        if role == "labelled_full_page":
            page = _nonnegative_int(
                entry.get("page"),
                label=f"Visual manifest {defect_index} labelled page",
                minimum=1,
            )
            expected_path = (
                source_run_dir / "photo-layout-labelled" / f"page-{page:04d}-labelled.png"
            ).resolve()
            if (
                page not in expected_pages
                or page in labelled_pages
                or page <= last_labelled_page
                or entry.get("candidate_id") is not None
                or entry.get("primary_secondary") != "SECONDARY"
                or entry.get("relationship_to_primary") != "REPORT_PAGE_CONTEXT"
                or path != expected_path
            ):
                raise CanonicalisationPreflightError(
                    f"Visual manifest {defect_index} labelled-page context is inconsistent."
                )
            labelled_pages.add(page)
            last_labelled_page = page
            continue

        if role == "contact_sheet":
            if (
                entry.get("candidate_id") is not None
                or entry.get("primary_secondary") != "SECONDARY"
                or entry.get("relationship_to_primary") != "MULTI_IMAGE_CONTEXT"
            ):
                raise CanonicalisationPreflightError(
                    f"Visual manifest {defect_index} contact-sheet metadata is inconsistent."
                )
            contact_entries.append((entry, path, expected_sha256))
            continue

        raise CanonicalisationPreflightError(
            f"Visual manifest {defect_index} has an unsupported attachment role."
        )

    if actual_detail_sequence != expected_detail_sequence or not detail_entries:
        raise CanonicalisationPreflightError(
            f"Visual manifest {defect_index} does not cover exactly the selected detail evidence."
        )
    if labelled_pages != expected_pages:
        raise CanonicalisationPreflightError(
            f"Visual manifest {defect_index} does not cover exactly the required labelled pages."
        )
    requires_contact_sheet = len(detail_entries) > 1
    if len(contact_entries) != int(requires_contact_sheet):
        raise CanonicalisationPreflightError(
            f"Visual manifest {defect_index} contact-sheet coverage is inconsistent."
        )
    if not requires_contact_sheet:
        return

    contact_entry, contact_path, contact_sha256 = contact_entries[0]
    expected_contact_path = (
        source_run_dir / "photo-contact-sheets" / f"defect-{defect_index:03d}.png"
    ).resolve()
    if contact_path != expected_contact_path:
        raise CanonicalisationPreflightError(
            f"Visual manifest {defect_index} contact-sheet path is inconsistent."
        )
    binding_path = _require_within(
        source_run_dir,
        f"photo-contact-sheets/defect-{defect_index:03d}-binding.json",
        label=f"Visual manifest {defect_index} contact-sheet binding",
    )
    binding_payload, _binding_sha256 = _read_json(
        binding_path, label=f"Visual manifest {defect_index} contact-sheet binding"
    )
    binding = binding_payload.get("binding")
    if not isinstance(binding, dict):
        raise CanonicalisationPreflightError(
            f"Visual manifest {defect_index} contact-sheet binding is malformed."
        )
    expected_inputs = [
        {
            "label": f"{entry['photo_id']} [{entry['variant_role']}]",
            "filename": path.name,
            "sha256": sha256,
        }
        for entry, path, sha256 in detail_entries
    ]
    if (
        binding.get("policy_version") != "CLASSIFIRE-PHOTO-VISUAL-v2-HIGHEST-USABLE-DETAIL"
        or str(binding.get("image_variant_receipt_sha256") or "").lower()
        != image_variant_sha256.lower()
        or binding.get("contact_thumbnail") != [900, 650]
        or binding.get("inputs") != expected_inputs
        or _sha256(
            binding_payload.get("output_sha256"),
            label=f"Visual manifest {defect_index} contact-sheet output SHA-256",
        ).lower()
        != contact_sha256
    ):
        raise CanonicalisationPreflightError(
            f"Visual manifest {defect_index} contact-sheet binding is inconsistent."
        )


def _validate_full_resolution_visual_evidence(
    db: Session,
    *,
    source_run_dir: Path,
    source_proposal: dict[str, Any],
    estimate_id: str,
    source_run_id: str,
) -> dict[str, Any]:
    """Revalidate the retained high-detail source assets and their visual gate receipts."""

    prepared_path = _require_within(
        source_run_dir, PREPARED_FILENAME, label="Prepared source receipt"
    )
    linked_inventory_path = _require_within(
        source_run_dir, LINKED_INVENTORY_FILENAME, label="Linked-photo inventory"
    )
    materialization_path = _require_within(
        source_run_dir,
        LINKED_MATERIALIZATION_FILENAME,
        label="Linked-photo materialization receipt",
    )
    image_variant_path = _require_within(
        source_run_dir, IMAGE_VARIANT_FILENAME, label="Image-variant resolution receipt"
    )
    prepared, prepared_sha256 = _read_json(prepared_path, label="Prepared source receipt")
    linked_inventory, linked_inventory_sha256 = _read_json(
        linked_inventory_path, label="Linked-photo inventory"
    )
    materialization, materialization_sha256 = _read_json(
        materialization_path, label="Linked-photo materialization receipt"
    )
    _require_schema(prepared, "CLASSIFIRE-REAL-UAT-PREP-v1", label="Prepared source receipt")
    if (
        prepared.get("ok") is not True
        or prepared.get("estimate_id") != estimate_id
        or prepared.get("run_id") != source_run_id
    ):
        raise CanonicalisationPreflightError(
            "Prepared source receipt does not bind the requested run and estimate."
        )
    _require_schema(
        linked_inventory,
        "CLASSIFIRE-LINKED-PHOTO-INVENTORY-v1",
        label="Linked-photo inventory",
    )
    if materialization.get("schema") != "CLASSIFIRE-REAL-UAT-LINKED-IMAGE-RETRIEVAL-v2":
        raise CanonicalisationPreflightError(
            "Linked-photo materialization receipt has an unsupported schema."
        )
    report_sha256 = _sha256(
        linked_inventory.get("report_sha256"), label="Linked-photo inventory report SHA-256"
    )
    if (
        _sha256(prepared.get("report_sha256"), label="Prepared source report SHA-256")
        != report_sha256
    ):
        raise CanonicalisationPreflightError(
            "Prepared source receipt and linked-photo inventory name different reports."
        )
    workspace_root = Path(__file__).resolve().parents[1]
    report_path = _require_within(
        workspace_root, prepared.get("stored_path"), label="Prepared source report path"
    )
    if _sha256_file(report_path, label="Prepared source report") != report_sha256:
        raise CanonicalisationPreflightError(
            "Prepared source report bytes no longer match the evidence report SHA-256."
        )
    if (
        linked_inventory.get("materialization_receipt") != LINKED_MATERIALIZATION_FILENAME
        or linked_inventory.get("materialization_ok") is not True
        or linked_inventory.get("cache_verification_ok") is not True
        or materialization.get("ok") is not True
        or _sha256(
            materialization.get("report_sha256"),
            label="Linked-photo materialization report SHA-256",
        )
        != report_sha256
        or materialization.get("failure_count") != 0
        or materialization.get("unresolved_image_link_count") != 0
    ):
        raise CanonicalisationPreflightError(
            "Linked-photo materialization does not prove a complete verified result."
        )
    inventory_by_photo_id = _linked_inventory_by_photo_id(linked_inventory)
    _validate_linked_materialization_items(
        linked_inventory=linked_inventory,
        materialization=materialization,
        inventory_by_photo_id=inventory_by_photo_id,
    )
    required_photo_ids: set[str] = set()
    for photo_id, photo in inventory_by_photo_id.items():
        if photo.get("full_resolution_required") is True:
            required_photo_ids.add(photo_id)
            status = _nonblank(
                photo.get("full_resolution_status"),
                label=f"Linked-photo inventory {photo_id} full-resolution status",
            ).upper()
            if status not in {"VERIFIED", "CACHED"}:
                raise CanonicalisationPreflightError(
                    f"Required linked photo {photo_id} is not verified."
                )
            _sha256(
                photo.get("full_resolution_sha256"),
                label=f"Linked-photo inventory {photo_id} content SHA-256",
            )
            _require_within(
                source_run_dir,
                photo.get("full_resolution_path"),
                label=f"Linked-photo inventory {photo_id} content path",
            )
            if preferred_verified_linked_path(photo, source_run_dir) is None:
                raise CanonicalisationPreflightError(
                    f"Required linked photo {photo_id} cannot be revalidated from its cached bytes."
                )
    if not required_photo_ids:
        raise CanonicalisationPreflightError(
            "Linked-photo inventory has no required high-resolution evidence."
        )
    if materialization.get("required_count") != len(required_photo_ids) or materialization.get(
        "verified_count", 0
    ) + materialization.get("cached_count", 0) != len(required_photo_ids):
        raise CanonicalisationPreflightError(
            "Linked-photo materialization counts do not match required photo evidence."
        )

    try:
        resolution = load_image_variant_resolution(
            image_variant_path,
            artifact_root=source_run_dir,
            expected_report_sha256=report_sha256.lower(),
            expected_inventory_sha256=linked_inventory_sha256.lower(),
        )
        primary_paths = validated_primary_paths(resolution, artifact_root=source_run_dir)
        secondary_paths = validated_mandatory_secondary_paths(
            resolution, artifact_root=source_run_dir
        )
    except ImageVariantResolutionError as exc:
        raise CanonicalisationPreflightError(
            "Image-variant resolution receipt cannot be revalidated."
        ) from exc
    image_variant_sha256 = _sha256_file(
        image_variant_path, label="Image-variant resolution receipt"
    )
    if set(primary_paths) & set(secondary_paths):
        raise CanonicalisationPreflightError(
            "Image-variant resolution reuses a candidate as both primary and mandatory context."
        )
    source_topologies, _source_counts = _proposal_topology_by_defect(
        source_proposal, label="Source visual proposal"
    )
    if (
        source_proposal.get("defect_count") != len(source_topologies)
        or source_proposal.get("supported_defect_count") != len(source_topologies)
        or source_proposal.get("limited_defect_count") != 0
    ):
        raise CanonicalisationPreflightError(
            "Source visual proposal is not a complete supported visual result."
        )
    receipt_rows: list[dict[str, Any]] = []
    seen_model_defects: set[str] = set()
    for defect_index in range(1, len(source_topologies) + 1):
        prefix = f"21-visual-defect-{defect_index:03d}"
        model_path = _require_within(
            source_run_dir, f"{prefix}-approved-model.json", label=f"Visual model {defect_index}"
        )
        evidence_path = _require_within(
            source_run_dir,
            f"20-fireseal-defect-{defect_index:03d}-evidence.json",
            label=f"Defect evidence {defect_index}",
        )
        validator_path = _require_within(
            source_run_dir,
            f"{prefix}-approved-validator.json",
            label=f"Visual validator {defect_index}",
        )
        blind_path = _require_within(
            source_run_dir,
            f"{prefix}-blind-inventory.json",
            label=f"Blind inventory {defect_index}",
        )
        cache_path = _require_within(
            source_run_dir, f"{prefix}-cache.json", label=f"Visual cache {defect_index}"
        )
        manifest_path = _require_within(
            source_run_dir, f"{prefix}-manifest.json", label=f"Visual manifest {defect_index}"
        )
        model, model_sha256 = _read_json(model_path, label=f"Visual model {defect_index}")
        evidence, evidence_sha256 = _read_json(
            evidence_path, label=f"Defect evidence {defect_index}"
        )
        validator, validator_sha256 = _read_json(
            validator_path, label=f"Visual validator {defect_index}"
        )
        blind, blind_sha256 = _read_json(blind_path, label=f"Blind inventory {defect_index}")
        cache, cache_sha256 = _read_json(cache_path, label=f"Visual cache {defect_index}")
        manifest, manifest_sha256 = _read_json_array(
            manifest_path, label=f"Visual manifest {defect_index}"
        )
        if model.get("status") != "MODEL_SUPPORTED" or not visual_validator_approved(
            validator, model
        ):
            raise CanonicalisationPreflightError(
                f"Visual model/validator {defect_index} is not a structurally approved result."
            )
        reconciliation_errors = validate_blind_reconciliation_payload(blind, model, validator)
        if reconciliation_errors:
            raise CanonicalisationPreflightError(
                f"Blind reconciliation {defect_index} is structurally invalid."
            )
        model_openings = _require_rows(model, "openings", label=f"Visual model {defect_index}")
        _require_rows(model, "services", label=f"Visual model {defect_index}")
        model_defect_ids = {
            _nonblank(
                row.get("external_defect_id"),
                label=f"Visual model {defect_index} Opening external_defect_id",
            )
            for row in model_openings
        }
        if len(model_defect_ids) != 1:
            raise CanonicalisationPreflightError(
                f"Visual model {defect_index} does not represent exactly one defect."
            )
        external_defect_id = next(iter(model_defect_ids))
        if external_defect_id in seen_model_defects or external_defect_id not in source_topologies:
            raise CanonicalisationPreflightError(
                f"Visual model {defect_index} has an unknown or duplicate defect identity."
            )
        seen_model_defects.add(external_defect_id)
        evidence_defect = evidence.get("defect")
        if (
            not isinstance(evidence_defect, dict)
            or evidence_defect.get("external_defect_id") != external_defect_id
        ):
            raise CanonicalisationPreflightError(
                f"Defect evidence {defect_index} does not bind visual model identity."
            )
        _require_visual_model_source_semantic_match(
            source_proposal=source_proposal,
            model=model,
            external_defect_id=external_defect_id,
            defect_index=defect_index,
        )
        requested_photo_ids, expected_pages = _requested_photo_ids_from_bound_evidence(
            db,
            estimate_id=estimate_id,
            external_defect_id=external_defect_id,
            inventory_by_photo_id=inventory_by_photo_id,
            image_variant_sha256=image_variant_sha256,
        )
        expected_detail_sequence, permitted_candidates = _expected_variant_selection(
            resolution=resolution,
            primary_paths=primary_paths,
            secondary_paths=secondary_paths,
            requested_photo_ids=requested_photo_ids,
        )
        if (
            _sha256(
                cache.get("image_variant_receipt_sha256"),
                label=f"Visual cache {defect_index} image-variant SHA-256",
            )
            != image_variant_sha256
            or cache.get("policy_version") != TOPOLOGY_HIGHEST_DETAIL_POLICY_VERSION
            or cache.get("visual_gate_policy_version") != VISUAL_GATE_HIGHEST_DETAIL_POLICY_VERSION
            or cache.get("blind_inventory") != blind
            or not isinstance(cache.get("ordered_attachment_manifest"), list)
            or not isinstance(cache.get("visual_files"), list)
        ):
            raise CanonicalisationPreflightError(
                f"Visual cache {defect_index} is not bound to current image/Blind evidence."
            )
        _validate_defect_attachment_manifest(
            source_run_dir=source_run_dir,
            defect_index=defect_index,
            manifest=manifest,
            expected_detail_sequence=expected_detail_sequence,
            permitted_candidates=permitted_candidates,
            requested_photo_ids=requested_photo_ids,
            expected_pages=expected_pages,
            inventory_by_photo_id=inventory_by_photo_id,
            image_variant_sha256=image_variant_sha256,
        )
        if cache.get("ordered_attachment_manifest") != _cache_manifest(manifest):
            raise CanonicalisationPreflightError(
                f"Visual cache {defect_index} attachment manifest does not match retained evidence."
            )
        expected_visual_files = [
            {
                "name": Path(str(entry["path"])).name,
                "sha256": _sha256(
                    entry["expected_sha256"], label="Visual manifest SHA-256"
                ).lower(),
            }
            for entry in manifest
        ]
        if cache.get("visual_files") != expected_visual_files:
            raise CanonicalisationPreflightError(
                f"Visual cache {defect_index} file hashes do not match retained evidence."
            )
        receipt_rows.append(
            {
                "defect_index": defect_index,
                "external_defect_id": external_defect_id,
                "defect_evidence_sha256": evidence_sha256,
                "model_sha256": model_sha256,
                "validator_sha256": validator_sha256,
                "blind_inventory_sha256": blind_sha256,
                "cache_sha256": cache_sha256,
                "manifest_sha256": manifest_sha256,
                "requested_photo_count": len(requested_photo_ids),
                "selected_detail_candidate_count": len(expected_detail_sequence),
                "labelled_page_count": len(expected_pages),
            }
        )
    if seen_model_defects != set(source_topologies):
        raise CanonicalisationPreflightError(
            "Visual gate receipts do not cover every source proposal defect."
        )
    return {
        "report_sha256": report_sha256,
        "prepared_source": _receipt_reference(prepared_path, prepared_sha256),
        "report": _receipt_reference(report_path, report_sha256),
        "linked_inventory": _receipt_reference(linked_inventory_path, linked_inventory_sha256),
        "linked_materialization": _receipt_reference(materialization_path, materialization_sha256),
        "image_variant_resolution": _receipt_reference(image_variant_path, image_variant_sha256),
        "required_linked_photo_count": len(required_photo_ids),
        "validated_primary_count": len(primary_paths),
        "validated_mandatory_secondary_count": len(secondary_paths),
        "visual_defects": receipt_rows,
    }


def _model_fields(model: type[Any]) -> set[str]:
    fields = getattr(model, "model_fields", None)
    if not isinstance(fields, dict):
        raise CanonicalisationPreflightError(
            "Pydantic v2 model fields are unavailable for strict preflight."
        )
    return set(fields)


def _normalised_payload(
    proposal: dict[str, Any],
    *,
    known_defect_ids: set[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw_openings = proposal.get("openings")
    raw_services = proposal.get("services")
    if not isinstance(raw_openings, list) or not isinstance(raw_services, list):
        raise CanonicalisationPreflightError(
            "Adjudicated proposal openings and services must be arrays."
        )
    if proposal.get("proposed_opening_count") != len(raw_openings) or proposal.get(
        "proposed_service_count"
    ) != len(raw_services):
        raise CanonicalisationPreflightError(
            "Adjudicated proposal declared counts do not match its arrays."
        )
    if proposal.get("defect_count") != len(
        {str(row.get("external_defect_id") or "").strip() for row in raw_openings}
    ):
        raise CanonicalisationPreflightError(
            "Adjudicated proposal defect count does not match its Opening records."
        )

    opening_fields = _model_fields(AgentOpeningInput)
    service_fields = _model_fields(AgentServiceInput)
    for index, row in enumerate(raw_openings, start=1):
        if not isinstance(row, dict):
            raise CanonicalisationPreflightError(f"Adjudicated Opening {index} is not an object.")
        unexpected = sorted(set(row) - opening_fields)
        if unexpected:
            raise CanonicalisationPreflightError(
                f"Adjudicated Opening {index} contains unexpected fields: {', '.join(unexpected)}."
            )
    for index, row in enumerate(raw_services, start=1):
        if not isinstance(row, dict):
            raise CanonicalisationPreflightError(f"Adjudicated Service {index} is not an object.")
        unexpected = sorted(set(row) - service_fields)
        if unexpected:
            raise CanonicalisationPreflightError(
                f"Adjudicated Service {index} contains unexpected fields: {', '.join(unexpected)}."
            )
    try:
        parsed = AgentInitialPhysicalModelInput.model_validate(
            {"openings": raw_openings, "services": raw_services}
        )
    except ValidationError as exc:
        raise CanonicalisationPreflightError(
            "Adjudicated proposal does not satisfy the controlled-write input schema."
        ) from exc

    payload = parsed.model_dump(mode="json")
    openings = payload["openings"]
    services = payload["services"]
    opening_by_code: dict[str, dict[str, Any]] = {}
    for opening in openings:
        code = _nonblank(opening.get("opening_code"), label="Opening code")
        if code in opening_by_code:
            raise CanonicalisationPreflightError(
                f"Adjudicated proposal repeats Opening code {code!r}."
            )
        external_defect_id = _nonblank(
            opening.get("external_defect_id"), label=f"Opening {code} external_defect_id"
        )
        if external_defect_id not in known_defect_ids:
            raise CanonicalisationPreflightError(
                f"Opening {code} refers to an unknown retained defect ID."
            )
        for field in ("substrate_type", "substrate_plane", "orientation", "frl"):
            _nonblank(opening.get(field), label=f"Opening {code} {field}")
        opening_by_code[code] = opening

    pairs: set[tuple[str, str]] = set()
    linked_opening_codes: Counter[str] = Counter()
    service_codes: set[str] = set()
    unknown_material_services: list[str] = []
    for service in services:
        service_code = _nonblank(service.get("service_code"), label="Service code")
        if service_code in service_codes:
            raise CanonicalisationPreflightError(
                f"Adjudicated proposal repeats Service code {service_code!r}."
            )
        service_codes.add(service_code)
        primary = _nonblank(
            service.get("primary_opening_code"),
            label=f"Service {service_code} primary_opening_code",
        )
        opening_codes = service.get("opening_codes")
        if not isinstance(opening_codes, list) or not opening_codes:
            raise CanonicalisationPreflightError(
                f"Service {service_code} opening_codes must be a nonempty array."
            )
        codes = [
            _nonblank(code, label=f"Service {service_code} opening code") for code in opening_codes
        ]
        if len(set(codes)) != len(codes):
            raise CanonicalisationPreflightError(
                f"Service {service_code} has duplicate opening codes."
            )
        if primary not in codes:
            raise CanonicalisationPreflightError(
                f"Service {service_code} primary opening is not in opening_codes."
            )
        if any(code not in opening_by_code for code in codes):
            raise CanonicalisationPreflightError(
                f"Service {service_code} refers to an unknown Opening."
            )
        defect_ids = {str(opening_by_code[code]["external_defect_id"]) for code in codes}
        if len(defect_ids) != 1:
            raise CanonicalisationPreflightError(
                f"Service {service_code} crosses defects without explicit authority."
            )
        for code in codes:
            if is_blank_opening_type(opening_by_code[code].get("opening_type")):
                raise CanonicalisationPreflightError(
                    f"Service {service_code} is linked to explicit blank Opening {code}."
                )
            pair = (service_code, code)
            if pair in pairs:
                raise CanonicalisationPreflightError(
                    f"Adjudicated proposal repeats Service/Opening pair {pair!r}."
                )
            pairs.add(pair)
            linked_opening_codes[code] += 1
        material = service.get("material")
        if material is None or not str(material).strip():
            unknown_material_services.append(service_code)
        service["opening_codes"] = sorted(codes)

    for code, opening in opening_by_code.items():
        blank = is_blank_opening_type(opening.get("opening_type"))
        link_count = linked_opening_codes.get(code, 0)
        if blank and link_count:
            raise CanonicalisationPreflightError(f"Explicit blank Opening {code} has Services.")
        if not blank and not link_count:
            raise CanonicalisationPreflightError(f"Nonblank Opening {code} has no Service link.")

    normalised = {
        "openings": sorted(openings, key=lambda row: str(row["opening_code"])),
        "services": sorted(services, key=lambda row: str(row["service_code"])),
    }
    withheld = proposal.get("adjudication_withheld_details")
    if not isinstance(withheld, list) or any(not isinstance(row, dict) for row in withheld):
        raise CanonicalisationPreflightError(
            "Adjudication withheld details must be an array of objects."
        )
    quantity_withholds = sorted(
        {
            _nonblank(row.get("opening_code"), label="Withheld-detail opening_code")
            for row in withheld
            if str(row.get("status") or "").strip().upper() == "QUANTITY_WITHHELD"
        }
    )
    return normalised, {
        "unknown_material_service_codes": sorted(unknown_material_services),
        "quantity_withheld_opening_codes": quantity_withholds,
        "service_opening_link_count": len(pairs),
        "blank_opening_codes": sorted(
            code
            for code, row in opening_by_code.items()
            if is_blank_opening_type(row.get("opening_type"))
        ),
    }


def _count(db: Session, model: type[Any], *conditions: Any) -> int:
    statement = select(func.count()).select_from(model)
    if conditions:
        statement = statement.where(*conditions)
    return int(db.scalar(statement) or 0)


def _historical_snapshot_ids(lock: PhysicalModelLock, *, field: str) -> set[str]:
    value = getattr(lock, field)
    if not isinstance(value, list):
        raise CanonicalisationPreflightError(
            f"Historical Physical Model Lock {lock.id} has malformed {field}."
        )
    normalized: set[str] = set()
    for index, item in enumerate(value, start=1):
        normalized.add(
            _nonblank(
                item,
                label=f"Historical Physical Model Lock {lock.id} {field}[{index}]",
            )
        )
    return normalized


def _historical_physical_descendant_counts(
    db: Session,
    *,
    estimate_id: str,
) -> dict[str, int]:
    """Find orphaned descendants of invalidated Physical Model Locks.

    A prior model can have had its Opening rows removed while later technical or
    commercial records still point to the lock's persisted opening/service
    snapshot.  Current-opening queries cannot see that lineage, so all of these
    checks intentionally include invalidated locks and orphan identifiers.
    """

    locks = list(
        db.scalars(
            select(PhysicalModelLock).where(PhysicalModelLock.estimate_id == estimate_id)
        ).all()
    )
    if not locks:
        return {
            "historical_lock_repair_strategy_count": 0,
            "historical_lock_repair_strategy_lock_count": 0,
            "historical_lock_system_required_component_count": 0,
            "historical_lock_candidate_requirement_count": 0,
            "historical_lock_service_material_hypothesis_count": 0,
            "historical_lock_service_count": 0,
            "historical_lock_service_opening_link_count": 0,
            "historical_lock_quantity_count": 0,
            "historical_lock_quantity_formula_input_count": 0,
            "historical_lock_labour_activity_count": 0,
            "historical_lock_pricing_component_count": 0,
            "historical_lock_commercial_method_lock_count": 0,
            "historical_lock_commercial_recovery_record_count": 0,
            "historical_lock_component_reconciliation_count": 0,
        }

    lock_ids = {lock.id for lock in locks}
    historical_opening_ids: set[str] = set()
    historical_service_ids: set[str] = set()
    for lock in locks:
        historical_opening_ids.update(_historical_snapshot_ids(lock, field="opening_ids"))
        historical_service_ids.update(_historical_snapshot_ids(lock, field="service_ids"))

    strategy_conditions = [RepairStrategy.physical_model_lock_id.in_(lock_ids)]
    if historical_opening_ids:
        strategy_conditions.append(RepairStrategy.opening_id.in_(historical_opening_ids))
    strategies = list(db.scalars(select(RepairStrategy).where(or_(*strategy_conditions))).all())
    strategy_ids = {strategy.id for strategy in strategies}

    repair_lock_conditions = []
    if strategy_ids:
        repair_lock_conditions.append(RepairStrategyLock.repair_strategy_id.in_(strategy_ids))
    if historical_opening_ids:
        repair_lock_conditions.append(RepairStrategyLock.opening_id.in_(historical_opening_ids))
    component_conditions = []
    if historical_opening_ids:
        component_conditions.append(SystemRequiredComponent.opening_id.in_(historical_opening_ids))
    if historical_service_ids:
        component_conditions.append(SystemRequiredComponent.service_id.in_(historical_service_ids))
    components = list(
        db.scalars(select(SystemRequiredComponent).where(or_(*component_conditions))).all()
        if component_conditions
        else []
    )
    component_ids = {component.id for component in components}

    service_conditions = []
    if historical_opening_ids:
        service_conditions.append(Service.opening_id.in_(historical_opening_ids))
    if historical_service_ids:
        service_conditions.append(Service.id.in_(historical_service_ids))
    services = list(
        db.scalars(select(Service).where(or_(*service_conditions))).all()
        if service_conditions
        else []
    )
    service_ids = historical_service_ids | {service.id for service in services}
    link_conditions = []
    if historical_opening_ids:
        link_conditions.append(ServiceOpeningLink.opening_id.in_(historical_opening_ids))
    if service_ids:
        link_conditions.append(ServiceOpeningLink.service_id.in_(service_ids))

    quantities = list(
        db.scalars(select(Quantity).where(Quantity.required_component_id.in_(component_ids))).all()
        if component_ids
        else []
    )
    quantity_ids = {quantity.id for quantity in quantities}
    pricing_components = list(
        db.scalars(
            select(PricingComponent).where(
                or_(
                    PricingComponent.required_component_id.in_(component_ids),
                    PricingComponent.opening_id.in_(historical_opening_ids),
                    PricingComponent.service_id.in_(service_ids),
                )
            )
        ).all()
        if component_ids or historical_opening_ids or service_ids
        else []
    )
    pricing_component_ids = {component.id for component in pricing_components}
    reconciliation_conditions = []
    if component_ids:
        reconciliation_conditions.append(
            ComponentRequirementReconciliation.required_component_id.in_(component_ids)
        )
    if historical_opening_ids:
        reconciliation_conditions.append(
            ComponentRequirementReconciliation.opening_id.in_(historical_opening_ids)
        )

    return {
        "historical_lock_repair_strategy_count": len(strategies),
        "historical_lock_repair_strategy_lock_count": _count(
            db, RepairStrategyLock, or_(*repair_lock_conditions)
        )
        if repair_lock_conditions
        else 0,
        "historical_lock_system_required_component_count": len(components),
        "historical_lock_candidate_requirement_count": _count(
            db,
            Package15CandidateRequirement,
            Package15CandidateRequirement.opening_id.in_(historical_opening_ids),
        )
        if historical_opening_ids
        else 0,
        "historical_lock_service_material_hypothesis_count": _count(
            db,
            ServiceMaterialHypothesis,
            ServiceMaterialHypothesis.service_id.in_(service_ids),
        )
        if service_ids
        else 0,
        "historical_lock_service_count": len(services),
        "historical_lock_service_opening_link_count": _count(
            db, ServiceOpeningLink, or_(*link_conditions)
        )
        if link_conditions
        else 0,
        "historical_lock_quantity_count": len(quantities),
        "historical_lock_quantity_formula_input_count": _count(
            db, QuantityFormulaInput, QuantityFormulaInput.quantity_record_id.in_(quantity_ids)
        )
        if quantity_ids
        else 0,
        "historical_lock_labour_activity_count": _count(
            db, LabourActivity, LabourActivity.required_component_id.in_(component_ids)
        )
        if component_ids
        else 0,
        "historical_lock_pricing_component_count": len(pricing_components),
        "historical_lock_commercial_method_lock_count": _count(
            db, CommercialMethodLock, CommercialMethodLock.component_id.in_(pricing_component_ids)
        )
        if pricing_component_ids
        else 0,
        "historical_lock_commercial_recovery_record_count": _count(
            db,
            CommercialRecoveryRecord,
            CommercialRecoveryRecord.component_id.in_(pricing_component_ids),
        )
        if pricing_component_ids
        else 0,
        "historical_lock_component_reconciliation_count": _count(
            db,
            ComponentRequirementReconciliation,
            or_(*reconciliation_conditions),
        )
        if reconciliation_conditions
        else 0,
    }


def _current_state(
    db: Session,
    *,
    estimate_id: str,
    expected_protected_state: dict[str, Any],
) -> dict[str, Any]:
    estimate = db.get(Estimate, estimate_id)
    if estimate is None:
        raise CanonicalisationPreflightError("Requested estimate no longer exists.")
    if (estimate.status or "").strip().lower() not in {"draft", "in_review"}:
        raise CanonicalisationPreflightError("Requested estimate is no longer editable.")

    snapshot = protected_state_snapshot_from_session(db, estimate_id)
    fingerprint = protected_state_fingerprint(snapshot)
    components = protected_component_fingerprints(snapshot)
    counts = protected_state_counts(snapshot)
    expected_fingerprint = _sha256(
        expected_protected_state.get("before_fingerprint"),
        label="Expected protected-state fingerprint",
    )
    if fingerprint != expected_fingerprint:
        raise CanonicalisationPreflightError(
            "Current protected-state fingerprint no longer matches adjudicated evidence."
        )
    expected_components = expected_protected_state.get("before_component_fingerprints")
    expected_counts = expected_protected_state.get("before_counts")
    if not isinstance(expected_components, dict) or not isinstance(expected_counts, dict):
        raise CanonicalisationPreflightError(
            "Adjudicated protected-state receipt lacks component/count evidence."
        )
    if {
        key: _sha256(value, label=f"Protected component {key}")
        for key, value in expected_components.items()
    } != components:
        raise CanonicalisationPreflightError(
            "Current protected-state component fingerprints no longer match adjudicated evidence."
        )
    if expected_counts != counts:
        raise CanonicalisationPreflightError(
            "Current protected-state component counts no longer match adjudicated evidence."
        )

    opening_count = _count(db, Opening, Opening.estimate_id == estimate_id)
    opening_ids = list(
        db.scalars(select(Opening.id).where(Opening.estimate_id == estimate_id)).all()
    )
    service_count = _count(db, Service, Service.opening_id.in_(opening_ids)) if opening_ids else 0
    link_count = (
        _count(db, ServiceOpeningLink, ServiceOpeningLink.opening_id.in_(opening_ids))
        if opening_ids
        else 0
    )
    active_lock_count = _count(
        db,
        PhysicalModelLock,
        PhysicalModelLock.estimate_id == estimate_id,
        PhysicalModelLock.invalidated_at.is_(None),
    )
    if opening_count or service_count or link_count or active_lock_count:
        raise CanonicalisationPreflightError(
            "Canonical Physical Model is no longer empty and unlocked for one-shot "
            "initial submission."
        )

    evidence_count = _count(db, EvidenceSource, EvidenceSource.estimate_id == estimate_id)
    defect_count = _count(db, Defect, Defect.estimate_id == estimate_id)
    if evidence_count <= 0 or defect_count <= 0:
        raise CanonicalisationPreflightError(
            "Retained evidence or defects are missing from the canonical estimate."
        )

    required_component_ids = (
        list(
            db.scalars(
                select(SystemRequiredComponent.id).where(
                    SystemRequiredComponent.opening_id.in_(opening_ids)
                )
            ).all()
        )
        if opening_ids
        else []
    )
    pricing_component_ids = list(
        db.scalars(
            select(PricingComponent.id).where(PricingComponent.estimate_id == estimate_id)
        ).all()
    )

    historical_descendants = _historical_physical_descendant_counts(db, estimate_id=estimate_id)
    downstream = {
        "repair_strategy_count": _count(
            db, RepairStrategy, RepairStrategy.opening_id.in_(opening_ids)
        )
        if opening_ids
        else 0,
        "repair_strategy_lock_count": _count(
            db, RepairStrategyLock, RepairStrategyLock.opening_id.in_(opening_ids)
        )
        if opening_ids
        else 0,
        "system_required_component_count": _count(
            db, SystemRequiredComponent, SystemRequiredComponent.opening_id.in_(opening_ids)
        )
        if opening_ids
        else 0,
        "estimate_line_count": _count(db, EstimateLine, EstimateLine.estimate_id == estimate_id),
        "quantity_count": _count(db, Quantity, Quantity.estimate_id == estimate_id),
        "labour_activity_count": _count(
            db, LabourActivity, LabourActivity.estimate_id == estimate_id
        ),
        "pricing_component_count": _count(
            db, PricingComponent, PricingComponent.estimate_id == estimate_id
        ),
        "commercial_method_lock_count": _count(
            db, CommercialMethodLock, CommercialMethodLock.component_id.in_(pricing_component_ids)
        )
        if pricing_component_ids
        else 0,
        "commercial_recovery_record_count": _count(
            db,
            CommercialRecoveryRecord,
            CommercialRecoveryRecord.component_id.in_(pricing_component_ids),
        )
        if pricing_component_ids
        else 0,
        "component_requirement_reconciliation_count": _count(
            db,
            ComponentRequirementReconciliation,
            ComponentRequirementReconciliation.required_component_id.in_(required_component_ids),
        )
        if required_component_ids
        else 0,
        "gate_evidence_count": _count(db, GateEvidence, GateEvidence.estimate_id == estimate_id),
        "rule_evaluation_count": _count(
            db, RuleEvaluation, RuleEvaluation.estimate_id == estimate_id
        ),
        "price_anomaly_review_count": _count(
            db, PriceAnomalyReview, PriceAnomalyReview.estimate_id == estimate_id
        ),
        "estimate_certificate_count": _count(
            db, EstimateCertificate, EstimateCertificate.estimate_id == estimate_id
        ),
        "audit_trail_count": _count(db, AuditTrail, AuditTrail.estimate_id == estimate_id),
        "approval_count": _count(
            db,
            Approval,
            Approval.entity_type == "estimate",
            Approval.entity_id == estimate_id,
        ),
        "render_output_audit_event_count": _count(
            db,
            AuditEvent,
            AuditEvent.entity_type == "estimate",
            AuditEvent.entity_id == estimate_id,
            AuditEvent.action == "render_output",
        ),
        "snapshot_present": estimate.snapshot_hash is not None
        or estimate.snapshot_json is not None,
        "estimate_locked_or_approved": bool(estimate.locked_at or estimate.approved_at),
        **historical_descendants,
    }
    downstream_blockers = sorted(
        key
        for key, value in downstream.items()
        if (isinstance(value, int) and value > 0) or (isinstance(value, bool) and value)
    )
    if downstream_blockers:
        raise CanonicalisationPreflightError(
            "Downstream estimate records would be invalidated: " + ", ".join(downstream_blockers)
        )
    edit_guard = check_estimate_action(db, estimate, WorkflowAction.EDIT_PHYSICAL_MODEL)
    if not edit_guard.allowed:
        raise CanonicalisationPreflightError(
            "Workflow does not permit physical-model editing: " + "; ".join(edit_guard.blockers)
        )
    return {
        "protected_state": {
            "fingerprint_version": PROTECTED_STATE_FINGERPRINT_VERSION,
            "fingerprint": fingerprint,
            "component_fingerprints": components,
            "counts": counts,
        },
        "canonical_counts": {
            "openings": opening_count,
            "services": service_count,
            "service_opening_links": link_count,
            "active_physical_model_locks": active_lock_count,
            "historical_physical_model_locks": _count(
                db, PhysicalModelLock, PhysicalModelLock.estimate_id == estimate_id
            ),
            "evidence_sources": evidence_count,
            "defects": defect_count,
        },
        "downstream": downstream,
        "workflow_edit_physical_model": edit_guard.as_dict(),
    }


def build_preflight(
    db: Session,
    *,
    source_run_dir: Path,
    adjudicated_dir: Path,
    estimate_id: str,
) -> dict[str, Any]:
    """Build a no-write receipt for an exact adjudicated canonicalisation candidate."""

    estimate_id = _nonblank(estimate_id, label="estimate_id")
    artifacts = _artifact_chain(
        source_run_dir=source_run_dir,
        adjudicated_dir=adjudicated_dir,
        estimate_id=estimate_id,
    )
    known_defect_ids = {
        value
        for value in db.scalars(
            select(Defect.external_defect_id).where(Defect.estimate_id == estimate_id)
        ).all()
        if isinstance(value, str) and value.strip()
    }
    payload, topology = _normalised_payload(
        artifacts["proposal"], known_defect_ids=known_defect_ids
    )
    current = _current_state(
        db,
        estimate_id=estimate_id,
        expected_protected_state=artifacts["protected_state"],
    )
    estimate = db.get(Estimate, estimate_id)
    if estimate is None:  # Defensive: _current_state already checks this.
        raise CanonicalisationPreflightError("Requested estimate no longer exists.")
    # The protected-state check above binds the active EvidenceSource.source_json
    # rows before they are used to reconstruct the retained visual routing.
    visual_evidence = _validate_full_resolution_visual_evidence(
        db,
        source_run_dir=source_run_dir.resolve(strict=True),
        source_proposal=artifacts["source_proposal"],
        estimate_id=estimate_id,
        source_run_id=artifacts["source_run_id"],
    )

    lock_blockers: list[str] = []
    if topology["unknown_material_service_codes"]:
        lock_blockers.append(
            "Service material remains unresolved for: "
            + ", ".join(topology["unknown_material_service_codes"])
        )
    if topology["quantity_withheld_opening_codes"]:
        lock_blockers.append(
            "Service quantity remains withheld for: "
            + ", ".join(topology["quantity_withheld_opening_codes"])
        )

    visual_status_by_defect: list[dict[str, str]] = []
    for external_defect_id in sorted(
        {str(row.get("external_defect_id")) for row in artifacts["proposal"].get("openings", [])}
    ):
        visual_status_by_defect.append(
            {
                "external_defect_id": external_defect_id,
                "evidence_basis": (
                    "VISUAL_EVIDENCE_PLUS_HUMAN_ADJUDICATED_OVERRIDE"
                    if external_defect_id in artifacts["changed_defects"]
                    else "VISUAL_APPROVED_UNCHANGED"
                ),
            }
        )

    projected_lock_eligible = not lock_blockers
    return {
        "schema": PREFLIGHT_SCHEMA,
        "status": "PRECHECK_PASSED_SIGNED_ADMISSION_REQUIRED",
        "project_id": estimate.project_id,
        "estimate_id": estimate_id,
        "source_run_id": artifacts["source_run_id"],
        "adjudicated_receipt_run_id": artifacts["final_state"].get("run_id"),
        "canonical_write_performed": False,
        "database_write_performed": False,
        "gateway_call_performed": False,
        "candidate_eligible": True,
        "submission_eligible": False,
        "lock_eligible": False,
        "projected_lock_eligible": projected_lock_eligible,
        "lock_blockers": [
            "The canonical Physical Model has not been safely submitted by a controlled writer.",
            *lock_blockers,
        ],
        "controlled_writer_implemented": True,
        "controlled_writer_policy_version": CONTROLLED_CANONICAL_WRITER_POLICY_VERSION,
        "controlled_writer_requirements": [
            "A governance process must create a one-time "
            "ECDSA_P256_SHA256-signed admission manifest that binds this receipt SHA-256, "
            "the normalized payload SHA-256, protected "
            "fingerprint, artifact digests, and policy versions.",
            "The writer must recompute protected state and recheck the empty, unlocked, "
            "downstream-clean estimate inside its exclusive database transaction.",
            "The generic initial-Physical-Model and agent lock paths are disabled; only the "
            "admission-bound writer may create this initial model.",
        ],
        "next_authority_required": (
            "A governance process must issue a signed admission after this fresh preflight. "
            "After that, a fresh explicit human authorisation is required before any initial "
            "Physical Model submission. This preflight cannot authorise a write."
        ),
        "artifact_references": artifacts["references"],
        "implementation": _implementation_hashes(),
        "protected_state": current["protected_state"],
        "canonical_counts": current["canonical_counts"],
        "downstream": current["downstream"],
        "workflow_edit_physical_model": current["workflow_edit_physical_model"],
        "normalised_submission_payload": payload,
        "normalised_submission_payload_sha256": _canonical_sha256(payload),
        "projected_topology": topology,
        "full_resolution_visual_evidence": visual_evidence,
        "visual_adjudication_basis": {
            "source_visual_final_state_status": artifacts["source_final_state"].get("status"),
            "source_final_receipt_contract": artifacts["source_final_receipt_contract"],
            "human_adjudication_sha256": artifacts["human_adjudication_sha256"],
            "historical_comparison_status": artifacts["historical_comparison"].get("status"),
            "per_defect": visual_status_by_defect,
        },
        "metadata_notes": [
            "Artifact directory names are not used as identity evidence; receipt paths "
            "and SHA-256 bindings are authoritative.",
            "The historical human-reference comparison is preserved as diagnostic evidence "
            "and is not treated as an adjudication-release gate.",
            "The retained artifact chain is locally hash-bound and revalidated, but has no "
            "independent immutable or signed trust root; this preflight cannot elevate it "
            "to write authority.",
        ],
    }


def _write_new_json(output_dir: Path, payload: dict[str, Any]) -> Path:
    if output_dir.exists():
        raise CanonicalisationPreflightError("Output directory must be a fresh namespace.")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir()
    destination = output_dir / PREFLIGHT_FILENAME
    encoded = (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".preflight-", suffix=".tmp", dir=str(output_dir)
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise
    return destination


def _failure_receipt(*, estimate_id: str, error: Exception) -> dict[str, Any]:
    return {
        "schema": PREFLIGHT_SCHEMA,
        "status": "BLOCKED",
        "estimate_id": estimate_id,
        "canonical_write_performed": False,
        "database_write_performed": False,
        "gateway_call_performed": False,
        "candidate_eligible": False,
        "submission_eligible": False,
        "lock_eligible": False,
        "projected_lock_eligible": False,
        "controlled_writer_implemented": True,
        "controlled_writer_policy_version": CONTROLLED_CANONICAL_WRITER_POLICY_VERSION,
        "errors": [str(error)],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run-dir", type=Path, required=True)
    parser.add_argument("--adjudicated-dir", type=Path, required=True)
    parser.add_argument("--estimate-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    estimate_id = str(args.estimate_id).strip()
    try:
        with SessionLocal() as db:
            receipt = build_preflight(
                db,
                source_run_dir=args.source_run_dir,
                adjudicated_dir=args.adjudicated_dir,
                estimate_id=estimate_id,
            )
        output_path = _write_new_json(args.output_dir, receipt)
    except (CanonicalisationPreflightError, OSError) as exc:
        try:
            output_path = _write_new_json(
                args.output_dir,
                _failure_receipt(estimate_id=estimate_id, error=exc),
            )
        except (CanonicalisationPreflightError, OSError) as write_exc:
            print(f"CANONICALISATION_PREFLIGHT_FAILED: {write_exc}")
            return 1
        print(json.dumps({"status": "BLOCKED", "receipt": str(output_path)}, sort_keys=True))
        return 2
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "lock_eligible": receipt["lock_eligible"],
                "receipt": str(output_path),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
