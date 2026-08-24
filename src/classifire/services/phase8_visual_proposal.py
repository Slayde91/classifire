"""Proposal-only Phase 8 visual orchestration with deterministic receipts.

The controller in this module can invoke inference ports, but it has no
canonical write, admission, signing, registration, or lock interface. It binds
each inference exchange to a validated evidence manifest and verifies the
current canonical protected-state fingerprint after every exchange.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from ..blind_visual_inventory import (
    validate_blind_reconciliation_payload,
    validate_blind_visual_inventory_payload,
)
from ..visual_validation import (
    validate_visual_correction_scope,
    validate_visual_validator_payload,
    visual_validator_approved,
)
from .canonical_submission_state import InitialSubmissionState
from .physical_scope import is_blank_opening_type

VISUAL_PROPOSAL_POLICY_VERSION = "CLASSIFIRE-PHASE8-VISUAL-PROPOSAL-v1"
VISUAL_EVIDENCE_MANIFEST_SCHEMA = "CLASSIFIRE-PHASE8-INFERENCE-EVIDENCE-v1"
VISUAL_INFERENCE_PROFILE_SCHEMA = "CLASSIFIRE-PHASE8-VISUAL-INFERENCE-PROFILE-v1"
VISUAL_INFERENCE_REQUEST_SCHEMA = "CLASSIFIRE-PHASE8-VISUAL-INFERENCE-REQUEST-v1"
VISUAL_INFERENCE_RESPONSE_SCHEMA = "CLASSIFIRE-PHASE8-VISUAL-INFERENCE-RESPONSE-v1"
VISUAL_PROPOSAL_RECEIPT_SCHEMA = "CLASSIFIRE-PHASE8-VISUAL-PROPOSAL-RECEIPT-v1"

VISUAL_PROPOSAL_APPROVED = "VISUAL_PROPOSAL_APPROVED"
VISUAL_PROPOSAL_BLOCKED = "VISUAL_PROPOSAL_BLOCKED"
VISUAL_PROPOSAL_FAILED = "VISUAL_PROPOSAL_FAILED"
VISUAL_PROPOSAL_PROTECTED_STATE_CHANGED = "VISUAL_PROPOSAL_PROTECTED_STATE_CHANGED"

_PROPOSAL_STATUSES = frozenset({"MODEL_SUPPORTED", "INSUFFICIENT_EVIDENCE"})
_RECEIPT_STATUSES = frozenset(
    {
        VISUAL_PROPOSAL_APPROVED,
        VISUAL_PROPOSAL_BLOCKED,
        VISUAL_PROPOSAL_FAILED,
        VISUAL_PROPOSAL_PROTECTED_STATE_CHANGED,
    }
)
_EMPTY_PROTECTED_COMPONENTS = (
    "opening_count",
    "service_count",
    "service_opening_link_count",
    "active_physical_model_lock_count",
)
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


class Phase8VisualProposalError(RuntimeError):
    """A configuration or precondition error before safe orchestration."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        message = f"Phase 8 visual proposal failed: {code}."
        if detail:
            message += f" {detail}"
        super().__init__(message)


class Phase8VisualInferencePort(Protocol):
    """The only runtime capability exposed to the proposal-only controller."""

    def invoke(
        self,
        *,
        role: str,
        stage: str,
        request: dict[str, Any],
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class Phase8VisualProposalResult:
    status: str
    approved: bool
    blind_inventory: dict[str, Any] | None
    proposal: dict[str, Any] | None
    validator: dict[str, Any] | None
    errors: tuple[str, ...]
    receipt: dict[str, Any]

    @property
    def receipt_sha256(self) -> str:
        return canonical_json_sha256(self.receipt)


def canonical_json_sha256(value: Any) -> str:
    """Hash JSON primitives exactly as CLASSIFIRE receipt contracts do."""

    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise Phase8VisualProposalError("NON_JSON_VALUE") from exc
    return hashlib.sha256(encoded).hexdigest().upper()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX_DIGITS for character in value)
    )


def _is_git_revision(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) in {40, 64}
        and all(character in _HEX_DIGITS for character in value)
    )


def _nonblank(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _positive_number_or_none(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    try:
        number = Decimal(str(value))
        return number.is_finite() and number > 0
    except (InvalidOperation, ValueError):
        return False


def _probability_or_none(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    try:
        number = Decimal(str(value))
        return number.is_finite() and Decimal("0") <= number <= Decimal("1")
    except (InvalidOperation, ValueError):
        return False


def validate_visual_evidence_manifest(
    manifest: Any,
    *,
    estimate_id: str,
) -> list[str]:
    """Validate the content-free manifest made visible to inference."""

    if not isinstance(manifest, dict):
        return ["evidence manifest must be an object"]

    errors: list[str] = []
    expected_keys = {
        "schema",
        "estimate_id",
        "defect_reference",
        "human_reference_included",
        "artifacts",
    }
    if set(manifest) != expected_keys:
        errors.append("evidence manifest fields do not match the approved schema")
    if manifest.get("schema") != VISUAL_EVIDENCE_MANIFEST_SCHEMA:
        errors.append("evidence manifest schema is unsupported")
    if manifest.get("estimate_id") != estimate_id:
        errors.append("evidence manifest estimate_id does not match the controller")
    if not _nonblank(manifest.get("defect_reference")):
        errors.append("evidence manifest requires a defect_reference")
    if manifest.get("human_reference_included") is not False:
        errors.append("human-reference or adjudication evidence is forbidden from inference")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("evidence manifest artifacts must be a non-empty array")
        artifacts = []

    expected_artifact_keys = {
        "evidence_id",
        "sha256",
        "size_bytes",
        "media_type",
        "inference_allowed",
        "validation_only",
        "provenance",
    }
    evidence_ids: set[str] = set()
    parent_links: list[tuple[int, str, str, str]] = []
    for index, artifact in enumerate(artifacts, start=1):
        if not isinstance(artifact, dict):
            errors.append(f"evidence artifact {index} must be an object")
            continue
        if set(artifact) != expected_artifact_keys:
            errors.append(f"evidence artifact {index} fields do not match the approved schema")
        evidence_id = _nonblank(artifact.get("evidence_id"))
        if not evidence_id:
            errors.append(f"evidence artifact {index} requires evidence_id")
        elif evidence_id in evidence_ids:
            errors.append(f"evidence artifact id is duplicated: {evidence_id}")
        else:
            evidence_ids.add(evidence_id)
        if not _is_sha256(artifact.get("sha256")):
            errors.append(f"evidence artifact {index} requires a SHA-256 digest")
        size_bytes = artifact.get("size_bytes")
        if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes < 1:
            errors.append(f"evidence artifact {index} size_bytes must be a positive integer")
        if not _nonblank(artifact.get("media_type")):
            errors.append(f"evidence artifact {index} requires media_type")
        if artifact.get("inference_allowed") is not True:
            errors.append(f"evidence artifact {index} is not approved for inference")
        if artifact.get("validation_only") is not False:
            errors.append(
                f"evidence artifact {index} is validation-only and cannot enter inference"
            )
        provenance = artifact.get("provenance")
        if not isinstance(provenance, dict):
            errors.append(f"evidence artifact {index} provenance must be an object")
            continue
        expected_provenance_keys = {
            "source_reference",
            "page_number",
            "region_reference",
            "evidence_class",
            "evidence_role",
            "relationship",
            "parent_evidence_id",
            "pixel_width",
            "pixel_height",
        }
        if set(provenance) != expected_provenance_keys:
            errors.append(
                f"evidence artifact {index} provenance fields do not match the approved schema"
            )
        for field_name in (
            "source_reference",
            "evidence_class",
            "evidence_role",
            "relationship",
        ):
            if not _nonblank(provenance.get(field_name)):
                errors.append(f"evidence artifact {index} provenance requires {field_name}")
        forbidden_labels = " ".join(
            _nonblank(provenance.get(name)).lower()
            for name in ("evidence_class", "evidence_role", "relationship")
        )
        if any(
            token in forbidden_labels
            for token in ("human_reference", "reference_fixture", "adjudication", "holdout")
        ):
            errors.append(f"evidence artifact {index} provenance is forbidden from inference")
        page_number = provenance.get("page_number")
        if page_number is not None and (
            isinstance(page_number, bool) or not isinstance(page_number, int) or page_number < 1
        ):
            errors.append(f"evidence artifact {index} page_number must be positive or null")
        region_reference = provenance.get("region_reference")
        if region_reference is not None and not _nonblank(region_reference):
            errors.append(f"evidence artifact {index} region_reference must be non-empty or null")
        relationship = _nonblank(provenance.get("relationship"))
        parent_id = provenance.get("parent_evidence_id")
        if parent_id is not None:
            parent_id = _nonblank(parent_id)
            if not parent_id:
                errors.append(
                    f"evidence artifact {index} parent_evidence_id must be non-empty or null"
                )
            elif evidence_id:
                parent_links.append((index, evidence_id, parent_id, relationship))
        dimensions: list[int | None] = []
        for field_name in ("pixel_width", "pixel_height"):
            value = provenance.get(field_name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 1
            ):
                errors.append(f"evidence artifact {index} {field_name} must be positive or null")
            dimensions.append(
                value if isinstance(value, int) and not isinstance(value, bool) else None
            )
        if _nonblank(artifact.get("media_type")).lower().startswith("image/") and any(
            value is None for value in dimensions
        ):
            errors.append(f"image evidence artifact {index} requires pixel dimensions")

    for index, evidence_id, parent_id, relationship in parent_links:
        if parent_id == evidence_id:
            errors.append(f"evidence artifact {index} cannot parent itself")
        elif parent_id not in evidence_ids and relationship != "linked_original":
            errors.append(
                f"evidence artifact {index} references unknown parent evidence {parent_id}"
            )
    parents = {
        evidence_id: parent_id
        for _index, evidence_id, parent_id, _relationship in parent_links
        if parent_id in evidence_ids
    }
    for evidence_id in parents:
        visited: set[str] = set()
        current: str | None = evidence_id
        while current in parents:
            if current in visited:
                errors.append("evidence provenance parent relationships contain a cycle")
                break
            visited.add(current)
            current = parents[current]

    try:
        canonical_json_sha256(manifest)
    except Phase8VisualProposalError:
        errors.append("evidence manifest must contain JSON values only")
    return list(dict.fromkeys(errors))


def validate_visual_inference_profile(profile: Any) -> list[str]:
    """Validate the versioned model, prompt, implementation, and policy binding."""

    if not isinstance(profile, dict):
        return ["visual inference profile must be an object"]
    errors: list[str] = []
    expected_keys = {
        "schema",
        "implementation_revision",
        "provider",
        "physical_model",
        "validator_model",
        "blind_prompt_sha256",
        "physical_prompt_sha256",
        "validator_prompt_sha256",
        "correction_prompt_sha256",
        "runtime_policy_sha256",
    }
    if set(profile) != expected_keys:
        errors.append("visual inference profile fields do not match the approved schema")
    if profile.get("schema") != VISUAL_INFERENCE_PROFILE_SCHEMA:
        errors.append("visual inference profile schema is unsupported")
    if not _is_git_revision(profile.get("implementation_revision")):
        errors.append("visual inference profile requires an implementation revision")
    for field_name in ("provider", "physical_model", "validator_model"):
        if not _nonblank(profile.get(field_name)):
            errors.append(f"visual inference profile requires {field_name}")
    for field_name in (
        "blind_prompt_sha256",
        "physical_prompt_sha256",
        "validator_prompt_sha256",
        "correction_prompt_sha256",
        "runtime_policy_sha256",
    ):
        if not _is_sha256(profile.get(field_name)):
            errors.append(f"visual inference profile requires {field_name}")
    try:
        canonical_json_sha256(profile)
    except Phase8VisualProposalError:
        errors.append("visual inference profile must contain JSON values only")
    return list(dict.fromkeys(errors))


def _stage_kind(stage_name: str) -> str | None:
    if stage_name in {"blind_inventory", "blind_inventory_retry", "physical_proposal"}:
        return stage_name
    for prefix, kind in (
        ("physical_structural_retry_", "physical_structural_retry"),
        ("conditioned_validator_retry_", "conditioned_validator_retry"),
        ("conditioned_validator_", "conditioned_validator"),
        ("physical_correction_", "physical_correction"),
    ):
        suffix = stage_name.removeprefix(prefix)
        if suffix != stage_name and suffix.isdigit():
            return kind
    return None


def _validate_stage_order(stages: list[Any], *, status: object) -> list[str]:
    """Validate that a receipt is a prefix of the approved controller state machine."""

    names = [_nonblank(stage.get("stage")) if isinstance(stage, dict) else "" for stage in stages]
    if not names:
        return []
    errors: list[str] = []
    if names[0] != "blind_inventory":
        errors.append("visual proposal stages must begin with blind_inventory")
    if len(names) != len(set(names)):
        errors.append("visual proposal stage names must be unique")
    failed_indexes = [
        index
        for index, stage in enumerate(stages)
        if isinstance(stage, dict) and stage.get("failed") is True
    ]
    if failed_indexes and failed_indexes != [len(stages) - 1]:
        errors.append("a failed inference stage must terminate the receipt")

    index = 1
    if index < len(names) and names[index] == "blind_inventory_retry":
        index += 1
    if index >= len(names):
        return errors
    if names[index] != "physical_proposal":
        errors.append("physical_proposal must immediately follow the blind phase")
        return errors
    index += 1
    seen_validator = False
    after_correction = False
    validator_stage: str | None = None
    current_pass = 0
    while index < len(names):
        name = names[index]
        kind = _stage_kind(name)
        if kind == "physical_structural_retry":
            if seen_validator or after_correction:
                errors.append("structural retry cannot follow conditioned validation")
            expected_name = f"physical_structural_retry_{current_pass + 1}"
            if name != expected_name:
                errors.append("physical structural retry pass is out of sequence")
            current_pass += 1
        elif kind == "conditioned_validator":
            previous_kind = _stage_kind(names[index - 1])
            if previous_kind not in {
                "physical_proposal",
                "physical_structural_retry",
                "physical_correction",
            }:
                errors.append("conditioned Validator pass requires a preceding Physical proposal")
            if name != f"conditioned_validator_{current_pass}":
                errors.append("conditioned Validator pass is out of sequence")
            seen_validator = True
            after_correction = False
            validator_stage = name
        elif kind == "conditioned_validator_retry":
            expected = (
                validator_stage.replace("conditioned_validator_", "conditioned_validator_retry_", 1)
                if validator_stage
                else None
            )
            if expected != name or index == 0 or names[index - 1] != validator_stage:
                errors.append("conditioned validator retry must immediately follow its pass")
        elif kind == "physical_correction":
            previous_kind = _stage_kind(names[index - 1])
            if (
                not seen_validator
                or after_correction
                or previous_kind not in {"conditioned_validator", "conditioned_validator_retry"}
            ):
                errors.append("physical correction requires a preceding conditioned Validator pass")
            if name != f"physical_correction_{current_pass + 1}":
                errors.append("physical correction pass is out of sequence")
            after_correction = True
            validator_stage = None
            current_pass += 1
        elif kind in {"blind_inventory", "blind_inventory_retry", "physical_proposal"}:
            errors.append(f"visual proposal stage is out of order: {name}")
        elif kind is None:
            errors.append(f"visual proposal stage name is unsupported: {name}")
        index += 1
    if status == VISUAL_PROPOSAL_APPROVED and _stage_kind(names[-1]) not in {
        "conditioned_validator",
        "conditioned_validator_retry",
    }:
        errors.append("approved visual proposal must end with conditioned validation")
    return errors


def validate_visual_physical_proposal(
    payload: Any,
    *,
    defect_reference: str,
) -> list[str]:
    """Validate one defect-level Physical proposal before visual approval."""

    if not isinstance(payload, dict):
        return ["Physical proposal must be an object"]

    errors: list[str] = []
    status = _nonblank(payload.get("status")).upper()
    if status not in _PROPOSAL_STATUSES:
        errors.append("Physical proposal status must be MODEL_SUPPORTED or INSUFFICIENT_EVIDENCE")

    openings = payload.get("openings")
    services = payload.get("services")
    limitations = payload.get("limitations")
    if not isinstance(openings, list):
        errors.append("Physical proposal openings must be an array")
        openings = []
    if not isinstance(services, list):
        errors.append("Physical proposal services must be an array")
        services = []
    if not isinstance(limitations, list):
        errors.append("Physical proposal limitations must be an array")
        limitations = []
    elif any(not _nonblank(item) for item in limitations):
        errors.append("Physical proposal limitations must contain non-empty strings")

    if status == "INSUFFICIENT_EVIDENCE":
        if not limitations:
            errors.append("INSUFFICIENT_EVIDENCE requires at least one limitation")
        if openings or services:
            errors.append("INSUFFICIENT_EVIDENCE cannot contain proposed physical records")
        return list(dict.fromkeys(errors))

    if status != "MODEL_SUPPORTED":
        return list(dict.fromkeys(errors))
    if not openings:
        errors.append("MODEL_SUPPORTED requires at least one Opening")

    opening_rows: dict[str, dict[str, Any]] = {}
    opening_link_counts: dict[str, int] = {}
    for index, item in enumerate(openings, start=1):
        if not isinstance(item, dict):
            errors.append(f"Opening {index} must be an object")
            continue
        code = _nonblank(item.get("opening_code"))
        if not code:
            errors.append(f"Opening {index} requires opening_code")
            continue
        if code in opening_rows:
            errors.append(f"Opening code is duplicated: {code}")
            continue
        opening_rows[code] = item
        opening_link_counts[code] = 0
        if _nonblank(item.get("external_defect_id")) != defect_reference:
            errors.append(f"Opening {code} is not bound to defect {defect_reference}")
        for field_name in (
            "substrate_type",
            "substrate_plane",
            "orientation",
            "opening_type",
        ):
            if not _nonblank(item.get(field_name)):
                errors.append(f"Opening {code} requires {field_name}")

    service_codes: set[str] = set()
    for index, item in enumerate(services, start=1):
        if not isinstance(item, dict):
            errors.append(f"Service {index} must be an object")
            continue
        service_code = _nonblank(item.get("service_code"))
        if not service_code:
            errors.append(f"Service {index} requires service_code")
        elif service_code in service_codes:
            errors.append(f"Service code is duplicated: {service_code}")
        else:
            service_codes.add(service_code)
        if not _nonblank(item.get("service_type")):
            errors.append(f"Service {service_code or index} requires service_type")
        if "material" not in item:
            errors.append(f"Service {service_code or index} must state material or null")
        if "quantity" not in item:
            errors.append(f"Service {service_code or index} must state quantity or null")
        if not _positive_number_or_none(item.get("quantity")):
            errors.append(f"Service {service_code or index} quantity must be positive or null")
        for field_name in (
            "evidence_status",
            "relationship_status",
            "link_type",
            "source_reference",
        ):
            if not _nonblank(item.get(field_name)):
                errors.append(f"Service {service_code or index} requires {field_name}")
        if not _probability_or_none(item.get("confidence")):
            errors.append(f"Service {service_code or index} confidence must be 0..1 or null")

        primary = _nonblank(item.get("primary_opening_code"))
        raw_links = item.get("opening_codes")
        if not isinstance(raw_links, list) or not raw_links:
            errors.append(f"Service {service_code or index} requires opening_codes")
            continue
        links = [_nonblank(value) for value in raw_links]
        if any(not value for value in links):
            errors.append(f"Service {service_code or index} has an invalid opening_code")
        if len(links) != len(set(links)):
            errors.append(f"Service {service_code or index} repeats an opening_code")
        if not primary or primary not in links:
            errors.append(
                f"Service {service_code or index} primary opening must be in opening_codes"
            )
        for opening_code in dict.fromkeys(value for value in links if value):
            if opening_code not in opening_rows:
                errors.append(
                    f"Service {service_code or index} references unknown Opening {opening_code}"
                )
                continue
            opening_link_counts[opening_code] += 1

    for opening_code, opening in opening_rows.items():
        link_count = opening_link_counts[opening_code]
        blank = is_blank_opening_type(opening.get("opening_type"))
        if blank and link_count:
            errors.append(f"Opening {opening_code} is blank but has linked Services")
        if not blank and link_count == 0:
            errors.append(
                f"Opening {opening_code} has no Service and is not an explicit blank opening"
            )

    return list(dict.fromkeys(errors))


def validate_visual_inference_response(
    response: Any,
    *,
    role: str,
    profile: dict[str, Any],
) -> list[str]:
    """Validate one model exchange and prove that it used no tool capability."""

    if not isinstance(response, dict):
        return ["visual inference response must be an object"]
    errors: list[str] = []
    expected_keys = {
        "schema",
        "agent_id",
        "provider",
        "model",
        "session_id_sha256",
        "transport_receipt_sha256",
        "tool_calls",
        "payload",
    }
    if set(response) != expected_keys:
        errors.append("visual inference response fields do not match the approved schema")
    if response.get("schema") != VISUAL_INFERENCE_RESPONSE_SCHEMA:
        errors.append("visual inference response schema is unsupported")
    if response.get("agent_id") != role:
        errors.append("visual inference response agent does not match the requested role")
    if response.get("provider") != profile.get("provider"):
        errors.append("visual inference response provider does not match the profile")
    expected_model = (
        profile.get("validator_model") if role == "cf-validator" else profile.get("physical_model")
    )
    if response.get("model") != expected_model:
        errors.append("visual inference response model does not match the profile")
    for field_name in ("session_id_sha256", "transport_receipt_sha256"):
        if not _is_sha256(response.get(field_name)):
            errors.append(f"visual inference response requires {field_name}")
    tool_calls = response.get("tool_calls")
    if not isinstance(tool_calls, list):
        errors.append("visual inference response tool_calls must be an array")
    elif tool_calls:
        errors.append("visual inference response recorded a forbidden tool call")
    try:
        canonical_json_sha256(response.get("payload"))
    except Phase8VisualProposalError:
        errors.append("visual inference payload must contain JSON values only")
    return list(dict.fromkeys(errors))


def validate_phase8_visual_proposal_receipt(receipt: Any) -> list[str]:
    """Validate a controller receipt before it is persisted or consumed."""

    if not isinstance(receipt, dict):
        return ["visual proposal receipt must be an object"]
    errors: list[str] = []
    expected_receipt_keys = {
        "schema",
        "policy_version",
        "status",
        "run_id",
        "estimate_id",
        "defect_reference",
        "evidence_manifest_sha256",
        "inference_profile_sha256",
        "implementation_revision",
        "stages",
        "result_hashes",
        "protected_state",
        "errors",
        "runtime_inference_performed",
        "controller_database_write_performed",
        "controller_canonical_write_performed",
        "write_or_lock_capability_exposed",
        "human_reference_visible_to_inference",
    }
    if set(receipt) != expected_receipt_keys:
        errors.append("visual proposal receipt fields do not match the approved schema")
    if receipt.get("schema") != VISUAL_PROPOSAL_RECEIPT_SCHEMA:
        errors.append("visual proposal receipt schema is unsupported")
    if receipt.get("policy_version") != VISUAL_PROPOSAL_POLICY_VERSION:
        errors.append("visual proposal receipt policy version is unsupported")
    status = receipt.get("status")
    if status not in _RECEIPT_STATUSES:
        errors.append("visual proposal receipt status is unsupported")
    for field_name in ("run_id", "estimate_id", "defect_reference"):
        if not _nonblank(receipt.get(field_name)):
            errors.append(f"visual proposal receipt requires {field_name}")
    if not _is_sha256(receipt.get("evidence_manifest_sha256")):
        errors.append("visual proposal receipt requires evidence_manifest_sha256")
    if not _is_sha256(receipt.get("inference_profile_sha256")):
        errors.append("visual proposal receipt requires inference_profile_sha256")
    if not _is_git_revision(receipt.get("implementation_revision")):
        errors.append("visual proposal receipt requires implementation_revision")
    for flag in (
        "controller_database_write_performed",
        "controller_canonical_write_performed",
        "write_or_lock_capability_exposed",
        "human_reference_visible_to_inference",
    ):
        if receipt.get(flag) is not False:
            errors.append(f"visual proposal receipt {flag} must be false")

    stages = receipt.get("stages")
    if not isinstance(stages, list):
        errors.append("visual proposal receipt stages must be an array")
        stages = []
    errors.extend(_validate_stage_order(stages, status=status))
    for index, stage in enumerate(stages, start=1):
        if not isinstance(stage, dict):
            errors.append(f"visual proposal receipt stage {index} must be an object")
            continue
        common_stage_keys = {
            "sequence",
            "stage",
            "role",
            "request_sha256",
            "response_sha256",
            "protected_state_fingerprint_after",
            "allowed_tools",
        }
        expected_stage_keys = (
            common_stage_keys | {"failed"}
            if stage.get("failed") is True
            else common_stage_keys
            | {
                "payload_sha256",
                "provider",
                "model",
                "session_id_sha256",
                "transport_receipt_sha256",
            }
        )
        if set(stage) != expected_stage_keys:
            errors.append(
                f"visual proposal receipt stage {index} fields do not match the approved schema"
            )
        if stage.get("sequence") != index:
            errors.append(f"visual proposal receipt stage {index} sequence is invalid")
        if not _nonblank(stage.get("stage")) or not _nonblank(stage.get("role")):
            errors.append(f"visual proposal receipt stage {index} identity is invalid")
        for digest_field in ("request_sha256", "response_sha256"):
            if not _is_sha256(stage.get(digest_field)):
                errors.append(f"visual proposal receipt stage {index} requires {digest_field}")
        if stage.get("allowed_tools") != []:
            errors.append(f"visual proposal receipt stage {index} exposed a tool")
        if not _is_sha256(stage.get("protected_state_fingerprint_after")):
            errors.append(
                f"visual proposal receipt stage {index} requires protected state fingerprint"
            )
        failed = stage.get("failed")
        if failed not in (None, True):
            errors.append(f"visual proposal receipt stage {index} failed flag is invalid")
        stage_name = _nonblank(stage.get("stage"))
        stage_kind = _stage_kind(stage_name)
        expected_role = (
            "cf-validator"
            if stage_kind
            in {
                "blind_inventory",
                "blind_inventory_retry",
                "conditioned_validator",
                "conditioned_validator_retry",
            }
            else "cf-physical-model"
            if stage_kind
            in {"physical_proposal", "physical_structural_retry", "physical_correction"}
            else None
        )
        if expected_role is None:
            errors.append(f"visual proposal receipt stage {index} name is unsupported")
        elif stage.get("role") != expected_role:
            errors.append(f"visual proposal receipt stage {index} role does not match stage")
        if failed is not True:
            for field_name in (
                "payload_sha256",
                "session_id_sha256",
                "transport_receipt_sha256",
            ):
                if not _is_sha256(stage.get(field_name)):
                    errors.append(f"visual proposal receipt stage {index} requires {field_name}")
            if not _nonblank(stage.get("provider")) or not _nonblank(stage.get("model")):
                errors.append(f"visual proposal receipt stage {index} model identity is invalid")

    protected = receipt.get("protected_state")
    if not isinstance(protected, dict):
        errors.append("visual proposal receipt protected_state must be an object")
    else:
        if set(protected) != {
            "before_fingerprint",
            "after_fingerprint",
            "before_counts",
            "after_counts",
            "unchanged",
        }:
            errors.append("protected_state fields do not match the approved schema")
        for digest_field in ("before_fingerprint", "after_fingerprint"):
            if not _is_sha256(protected.get(digest_field)):
                errors.append(f"protected_state requires {digest_field}")
        unchanged = protected.get("unchanged")
        same_fingerprint = protected.get("before_fingerprint") == protected.get("after_fingerprint")
        same_counts = protected.get("before_counts") == protected.get("after_counts")
        if status == VISUAL_PROPOSAL_PROTECTED_STATE_CHANGED:
            if unchanged is not False or (same_fingerprint and same_counts):
                errors.append("protected-state-changed receipt must prove a state change")
        elif unchanged is not True or not same_fingerprint or not same_counts:
            errors.append("visual proposal receipt requires unchanged protected state")

    result_hashes = receipt.get("result_hashes")
    if not isinstance(result_hashes, dict):
        errors.append("visual proposal receipt result_hashes must be an object")
    else:
        expected_result_hash_fields = {
            "blind_inventory_sha256",
            "proposal_sha256",
            "validator_sha256",
        }
        if set(result_hashes) != expected_result_hash_fields:
            errors.append("result_hashes fields do not match the approved schema")
        if status == VISUAL_PROPOSAL_APPROVED:
            for name in expected_result_hash_fields:
                if not _is_sha256(result_hashes.get(name)):
                    errors.append(f"approved visual proposal requires {name}")
    receipt_errors = receipt.get("errors")
    if not isinstance(receipt_errors, list) or any(not _nonblank(item) for item in receipt_errors):
        errors.append("visual proposal receipt errors must be an array of non-empty strings")
    if status == VISUAL_PROPOSAL_APPROVED and receipt_errors:
        errors.append("approved visual proposal receipt cannot contain errors")
    if status != VISUAL_PROPOSAL_APPROVED and not receipt_errors:
        errors.append("non-approved visual proposal receipt requires an error")
    if receipt.get("runtime_inference_performed") is not bool(stages):
        errors.append("runtime_inference_performed does not match recorded stages")
    if status == VISUAL_PROPOSAL_APPROVED and any(stage.get("failed") for stage in stages):
        errors.append("approved visual proposal receipt cannot contain a failed stage")
    if status in {VISUAL_PROPOSAL_APPROVED, VISUAL_PROPOSAL_BLOCKED} and isinstance(
        result_hashes, dict
    ):
        expected_result_hashes: dict[str, str | None] = {
            "blind_inventory_sha256": None,
            "proposal_sha256": None,
            "validator_sha256": None,
        }
        for stage in stages:
            if not isinstance(stage, dict):
                continue
            stage_name = _nonblank(stage.get("stage"))
            stage_kind = _stage_kind(stage_name)
            if stage_kind in {"blind_inventory", "blind_inventory_retry"}:
                expected_result_hashes["blind_inventory_sha256"] = stage.get("payload_sha256")
            elif stage_kind in {
                "physical_proposal",
                "physical_structural_retry",
                "physical_correction",
            }:
                expected_result_hashes["proposal_sha256"] = stage.get("payload_sha256")
            elif stage_kind in {"conditioned_validator", "conditioned_validator_retry"}:
                expected_result_hashes["validator_sha256"] = stage.get("payload_sha256")
        for name, expected_hash in expected_result_hashes.items():
            if result_hashes.get(name) != expected_hash:
                errors.append(f"{name} is not bound to its final inference stage")
    return list(dict.fromkeys(errors))


class _ProtectedStateChanged(RuntimeError):
    pass


class ProposalOnlyVisualController:
    """Run the independent Phase 8 visual gate without a write capability."""

    def __init__(
        self,
        *,
        run_id: str,
        estimate_id: str,
        evidence_manifest: Any,
        inference_profile: Any,
        inference_port: Phase8VisualInferencePort,
        protected_state_reader: Callable[[], InitialSubmissionState],
        max_correction_passes: int = 2,
    ) -> None:
        self.run_id = _nonblank(run_id)
        self.estimate_id = _nonblank(estimate_id)
        if not self.run_id:
            raise Phase8VisualProposalError("RUN_ID_REQUIRED")
        if not self.estimate_id:
            raise Phase8VisualProposalError("ESTIMATE_ID_REQUIRED")
        if isinstance(max_correction_passes, bool) or not isinstance(max_correction_passes, int):
            raise Phase8VisualProposalError("CORRECTION_LIMIT_INVALID")
        if max_correction_passes < 0 or max_correction_passes > 5:
            raise Phase8VisualProposalError("CORRECTION_LIMIT_INVALID")

        manifest_errors = validate_visual_evidence_manifest(
            evidence_manifest,
            estimate_id=self.estimate_id,
        )
        if manifest_errors:
            raise Phase8VisualProposalError(
                "EVIDENCE_MANIFEST_INVALID",
                "; ".join(manifest_errors),
            )
        self.evidence_manifest = deepcopy(evidence_manifest)
        self.defect_reference = str(evidence_manifest["defect_reference"]).strip()
        self.evidence_manifest_sha256 = canonical_json_sha256(self.evidence_manifest)
        profile_errors = validate_visual_inference_profile(inference_profile)
        if profile_errors:
            raise Phase8VisualProposalError(
                "INFERENCE_PROFILE_INVALID",
                "; ".join(profile_errors),
            )
        self.inference_profile = deepcopy(inference_profile)
        self.inference_profile_sha256 = canonical_json_sha256(self.inference_profile)
        self.inference_port = inference_port
        self.protected_state_reader = protected_state_reader
        self.max_correction_passes = max_correction_passes
        self._stages: list[dict[str, Any]] = []
        self._before_state: InitialSubmissionState | None = None
        self._has_run = False

    def _read_protected_state(self) -> InitialSubmissionState:
        try:
            state = self.protected_state_reader()
        except Exception as exc:
            raise Phase8VisualProposalError("PROTECTED_STATE_UNAVAILABLE") from exc
        if not isinstance(state, InitialSubmissionState):
            raise Phase8VisualProposalError("PROTECTED_STATE_INVALID")
        if state.estimate_id != self.estimate_id:
            raise Phase8VisualProposalError("PROTECTED_STATE_ESTIMATE_MISMATCH")
        if not _is_sha256(state.fingerprint):
            raise Phase8VisualProposalError("PROTECTED_STATE_FINGERPRINT_INVALID")
        return state

    @staticmethod
    def _protected_state_is_empty(state: InitialSubmissionState) -> bool:
        return all(state.counts.get(name) == 0 for name in _EMPTY_PROTECTED_COMPONENTS)

    def _require_state_unchanged(self, state: InitialSubmissionState) -> None:
        before = self._before_state
        if before is None:
            raise Phase8VisualProposalError("PROTECTED_STATE_BASELINE_MISSING")
        if state.fingerprint != before.fingerprint or state.counts != before.counts:
            raise _ProtectedStateChanged

    def _request(self, *, stage_input: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema": VISUAL_INFERENCE_REQUEST_SCHEMA,
            "policy_version": VISUAL_PROPOSAL_POLICY_VERSION,
            "run_id": self.run_id,
            "estimate_id": self.estimate_id,
            "defect_reference": self.defect_reference,
            "evidence_manifest": deepcopy(self.evidence_manifest),
            "evidence_manifest_sha256": self.evidence_manifest_sha256,
            "inference_profile": deepcopy(self.inference_profile),
            "inference_profile_sha256": self.inference_profile_sha256,
            "human_reference_visible": False,
            "allowed_tools": [],
            "stage_input": deepcopy(stage_input),
        }

    def _invoke(
        self,
        *,
        role: str,
        stage: str,
        stage_input: dict[str, Any],
    ) -> Any:
        request = self._request(stage_input=stage_input)
        request_sha256 = canonical_json_sha256(request)
        try:
            response = self.inference_port.invoke(
                role=role,
                stage=stage,
                request=deepcopy(request),
            )
        except Exception as exc:
            current_state = self._read_protected_state()
            failure = {"error_type": type(exc).__name__}
            self._stages.append(
                {
                    "sequence": len(self._stages) + 1,
                    "stage": stage,
                    "role": role,
                    "request_sha256": request_sha256,
                    "response_sha256": canonical_json_sha256(failure),
                    "protected_state_fingerprint_after": current_state.fingerprint,
                    "allowed_tools": [],
                    "failed": True,
                }
            )
            self._require_state_unchanged(current_state)
            raise Phase8VisualProposalError(
                "INFERENCE_PORT_FAILED",
                f"{stage}: {type(exc).__name__}",
            ) from exc
        response = deepcopy(response)
        try:
            response_sha256 = canonical_json_sha256(response)
        except Phase8VisualProposalError as exc:
            current_state = self._read_protected_state()
            failure = {"error_type": exc.code}
            self._stages.append(
                {
                    "sequence": len(self._stages) + 1,
                    "stage": stage,
                    "role": role,
                    "request_sha256": request_sha256,
                    "response_sha256": canonical_json_sha256(failure),
                    "protected_state_fingerprint_after": current_state.fingerprint,
                    "allowed_tools": [],
                    "failed": True,
                }
            )
            self._require_state_unchanged(current_state)
            raise Phase8VisualProposalError(
                "INFERENCE_RESPONSE_NOT_JSON",
                stage,
            ) from exc
        response_errors = validate_visual_inference_response(
            response,
            role=role,
            profile=self.inference_profile,
        )
        if response_errors:
            current_state = self._read_protected_state()
            self._stages.append(
                {
                    "sequence": len(self._stages) + 1,
                    "stage": stage,
                    "role": role,
                    "request_sha256": request_sha256,
                    "response_sha256": response_sha256,
                    "protected_state_fingerprint_after": current_state.fingerprint,
                    "allowed_tools": [],
                    "failed": True,
                }
            )
            self._require_state_unchanged(current_state)
            raise Phase8VisualProposalError(
                "INFERENCE_RESPONSE_INVALID",
                stage + ": " + "; ".join(response_errors),
            )
        payload = deepcopy(response["payload"])
        payload_sha256 = canonical_json_sha256(payload)
        current_state = self._read_protected_state()
        self._stages.append(
            {
                "sequence": len(self._stages) + 1,
                "stage": stage,
                "role": role,
                "request_sha256": request_sha256,
                "response_sha256": response_sha256,
                "payload_sha256": payload_sha256,
                "provider": response["provider"],
                "model": response["model"],
                "session_id_sha256": response["session_id_sha256"],
                "transport_receipt_sha256": response["transport_receipt_sha256"],
                "protected_state_fingerprint_after": current_state.fingerprint,
                "allowed_tools": [],
            }
        )
        self._require_state_unchanged(current_state)
        return payload

    @staticmethod
    def _hash_or_none(value: Any) -> str | None:
        return canonical_json_sha256(value) if value is not None else None

    def _finish(
        self,
        *,
        status: str,
        errors: list[str],
        blind_inventory: Any = None,
        proposal: Any = None,
        validator: Any = None,
    ) -> Phase8VisualProposalResult:
        before = self._before_state
        if before is None:
            raise Phase8VisualProposalError("PROTECTED_STATE_BASELINE_MISSING")
        after = self._read_protected_state()
        unchanged = after.fingerprint == before.fingerprint and after.counts == before.counts
        if not unchanged:
            status = VISUAL_PROPOSAL_PROTECTED_STATE_CHANGED
            errors = [*errors, "canonical protected state changed during proposal-only inference"]

        errors = list(dict.fromkeys(item for item in errors if item))
        receipt = {
            "schema": VISUAL_PROPOSAL_RECEIPT_SCHEMA,
            "policy_version": VISUAL_PROPOSAL_POLICY_VERSION,
            "status": status,
            "run_id": self.run_id,
            "estimate_id": self.estimate_id,
            "defect_reference": self.defect_reference,
            "evidence_manifest_sha256": self.evidence_manifest_sha256,
            "inference_profile_sha256": self.inference_profile_sha256,
            "implementation_revision": self.inference_profile["implementation_revision"],
            "stages": deepcopy(self._stages),
            "result_hashes": {
                "blind_inventory_sha256": self._hash_or_none(blind_inventory),
                "proposal_sha256": self._hash_or_none(proposal),
                "validator_sha256": self._hash_or_none(validator),
            },
            "protected_state": {
                "before_fingerprint": before.fingerprint,
                "after_fingerprint": after.fingerprint,
                "before_counts": deepcopy(before.counts),
                "after_counts": deepcopy(after.counts),
                "unchanged": unchanged,
            },
            "errors": errors,
            "runtime_inference_performed": bool(self._stages),
            "controller_database_write_performed": False,
            "controller_canonical_write_performed": False,
            "write_or_lock_capability_exposed": False,
            "human_reference_visible_to_inference": False,
        }
        receipt_errors = validate_phase8_visual_proposal_receipt(receipt)
        if receipt_errors:
            raise Phase8VisualProposalError(
                "RECEIPT_INVALID",
                "; ".join(receipt_errors),
            )
        return Phase8VisualProposalResult(
            status=status,
            approved=status == VISUAL_PROPOSAL_APPROVED,
            blind_inventory=(
                deepcopy(blind_inventory) if isinstance(blind_inventory, dict) else None
            ),
            proposal=deepcopy(proposal) if isinstance(proposal, dict) else None,
            validator=deepcopy(validator) if isinstance(validator, dict) else None,
            errors=tuple(errors),
            receipt=receipt,
        )

    @staticmethod
    def _validator_errors(
        blind_inventory: Any,
        proposal: Any,
        validator: Any,
    ) -> list[str]:
        return list(
            dict.fromkeys(
                [
                    *validate_visual_validator_payload(validator, proposal),
                    *validate_blind_reconciliation_payload(
                        blind_inventory,
                        proposal,
                        validator,
                    ),
                ]
            )
        )

    @staticmethod
    def _validator_blockers(validator: dict[str, Any]) -> list[str]:
        blockers = [
            _nonblank(item.get("detail")) or _nonblank(item.get("code"))
            for item in validator.get("issues", [])
            if isinstance(item, dict)
        ]
        limitations = validator.get("limitations")
        if isinstance(limitations, list):
            blockers.extend(_nonblank(item) for item in limitations)
        return [item for item in blockers if item]

    def _run_workflow(self) -> Phase8VisualProposalResult:
        blind_inventory = self._invoke(
            role="cf-validator",
            stage="blind_inventory",
            stage_input={
                "proposal_visible": False,
                "validator_receipt_visible": False,
            },
        )
        blind_errors = validate_blind_visual_inventory_payload(blind_inventory)
        if blind_errors:
            blind_inventory = self._invoke(
                role="cf-validator",
                stage="blind_inventory_retry",
                stage_input={
                    "proposal_visible": False,
                    "validator_receipt_visible": False,
                    "previous_inventory": blind_inventory,
                    "validation_errors": blind_errors,
                },
            )
            blind_errors = validate_blind_visual_inventory_payload(blind_inventory)
        if blind_errors:
            return self._finish(
                status=VISUAL_PROPOSAL_BLOCKED,
                errors=["blind inventory remained invalid: " + "; ".join(blind_errors)],
                blind_inventory=blind_inventory,
            )

        proposal = self._invoke(
            role="cf-physical-model",
            stage="physical_proposal",
            stage_input={
                "blind_inventory_visible": False,
                "validator_receipt_visible": False,
            },
        )
        validator: Any = None

        for pass_index in range(self.max_correction_passes + 1):
            proposal_errors = validate_visual_physical_proposal(
                proposal,
                defect_reference=self.defect_reference,
            )
            proposal_status = (
                _nonblank(proposal.get("status")).upper() if isinstance(proposal, dict) else ""
            )
            if proposal_status != "MODEL_SUPPORTED" or proposal_errors:
                if pass_index >= self.max_correction_passes:
                    reasons = proposal_errors
                    if not reasons and isinstance(proposal, dict):
                        raw_limitations = proposal.get("limitations")
                        if isinstance(raw_limitations, list):
                            reasons = [
                                _nonblank(item) for item in raw_limitations if _nonblank(item)
                            ]
                    return self._finish(
                        status=VISUAL_PROPOSAL_BLOCKED,
                        errors=[
                            "Physical proposal remained incomplete: "
                            + "; ".join(reasons or [proposal_status or "status missing"])
                        ],
                        blind_inventory=blind_inventory,
                        proposal=proposal,
                    )
                proposal = self._invoke(
                    role="cf-physical-model",
                    stage=f"physical_structural_retry_{pass_index + 1}",
                    stage_input={
                        "blind_inventory_visible": False,
                        "validator_receipt_visible": False,
                        "previous_proposal": proposal,
                        "validation_errors": proposal_errors,
                    },
                )
                continue

            validator = self._invoke(
                role="cf-validator",
                stage=f"conditioned_validator_{pass_index}",
                stage_input={
                    "blind_inventory": blind_inventory,
                    "proposal": proposal,
                },
            )
            validator_errors = self._validator_errors(
                blind_inventory,
                proposal,
                validator,
            )
            if validator_errors:
                validator = self._invoke(
                    role="cf-validator",
                    stage=f"conditioned_validator_retry_{pass_index}",
                    stage_input={
                        "blind_inventory": blind_inventory,
                        "proposal": proposal,
                        "previous_validator": validator,
                        "validation_errors": validator_errors,
                    },
                )
                validator_errors = self._validator_errors(
                    blind_inventory,
                    proposal,
                    validator,
                )
            if validator_errors:
                return self._finish(
                    status=VISUAL_PROPOSAL_BLOCKED,
                    errors=["Validator receipt remained invalid: " + "; ".join(validator_errors)],
                    blind_inventory=blind_inventory,
                    proposal=proposal,
                    validator=validator,
                )

            if visual_validator_approved(validator, proposal):
                return self._finish(
                    status=VISUAL_PROPOSAL_APPROVED,
                    errors=[],
                    blind_inventory=blind_inventory,
                    proposal=proposal,
                    validator=validator,
                )

            verdict = _nonblank(validator.get("verdict")).upper()
            if verdict == "BLOCKED":
                return self._finish(
                    status=VISUAL_PROPOSAL_BLOCKED,
                    errors=[
                        "Validator blocked the proposal: "
                        + "; ".join(self._validator_blockers(validator))
                    ],
                    blind_inventory=blind_inventory,
                    proposal=proposal,
                    validator=validator,
                )
            if pass_index >= self.max_correction_passes:
                return self._finish(
                    status=VISUAL_PROPOSAL_BLOCKED,
                    errors=["Validator remained REJECTED after bounded corrections"],
                    blind_inventory=blind_inventory,
                    proposal=proposal,
                    validator=validator,
                )

            correction_preflight_errors = validate_visual_correction_scope(
                proposal,
                proposal,
                validator,
            )
            if correction_preflight_errors:
                return self._finish(
                    status=VISUAL_PROPOSAL_BLOCKED,
                    errors=[
                        "Physical correction was not authorised: "
                        + "; ".join(correction_preflight_errors)
                    ],
                    blind_inventory=blind_inventory,
                    proposal=proposal,
                    validator=validator,
                )

            corrected_proposal = self._invoke(
                role="cf-physical-model",
                stage=f"physical_correction_{pass_index + 1}",
                stage_input={
                    "blind_inventory_visible": False,
                    "proposal": proposal,
                    "validator": validator,
                },
            )
            correction_scope_errors = validate_visual_correction_scope(
                proposal,
                corrected_proposal,
                validator,
            )
            if correction_scope_errors:
                return self._finish(
                    status=VISUAL_PROPOSAL_BLOCKED,
                    errors=[
                        "Physical correction exceeded Validator authority: "
                        + "; ".join(correction_scope_errors)
                    ],
                    blind_inventory=blind_inventory,
                    proposal=corrected_proposal,
                    validator=validator,
                )
            corrected_errors = validate_visual_physical_proposal(
                corrected_proposal,
                defect_reference=self.defect_reference,
            )
            corrected_status = (
                _nonblank(corrected_proposal.get("status")).upper()
                if isinstance(corrected_proposal, dict)
                else ""
            )
            if corrected_status != "MODEL_SUPPORTED" or corrected_errors:
                return self._finish(
                    status=VISUAL_PROPOSAL_BLOCKED,
                    errors=[
                        "Physical correction remained incomplete within Validator authority: "
                        + "; ".join(corrected_errors or [corrected_status or "status missing"])
                    ],
                    blind_inventory=blind_inventory,
                    proposal=corrected_proposal,
                    validator=validator,
                )
            proposal = corrected_proposal

        return self._finish(
            status=VISUAL_PROPOSAL_BLOCKED,
            errors=["visual proposal workflow exhausted without approval"],
            blind_inventory=blind_inventory,
            proposal=proposal,
            validator=validator,
        )

    def run(self) -> Phase8VisualProposalResult:
        """Execute proposal-only inference and always recheck protected state."""

        if self._has_run:
            raise Phase8VisualProposalError("CONTROLLER_ALREADY_RUN")
        self._has_run = True
        self._stages = []
        self._before_state = self._read_protected_state()
        if not self._protected_state_is_empty(self._before_state):
            raise Phase8VisualProposalError("PROTECTED_STATE_NOT_EMPTY")
        try:
            return self._run_workflow()
        except _ProtectedStateChanged:
            return self._finish(
                status=VISUAL_PROPOSAL_PROTECTED_STATE_CHANGED,
                errors=["canonical protected state changed during proposal-only inference"],
            )
        except Phase8VisualProposalError as exc:
            return self._finish(
                status=VISUAL_PROPOSAL_FAILED,
                errors=[exc.code + (f": {exc.detail}" if exc.detail else "")],
            )
        except Exception as exc:
            return self._finish(
                status=VISUAL_PROPOSAL_FAILED,
                errors=[f"UNEXPECTED_CONTROLLER_ERROR: {type(exc).__name__}"],
            )


__all__ = [
    "Phase8VisualInferencePort",
    "Phase8VisualProposalError",
    "Phase8VisualProposalResult",
    "ProposalOnlyVisualController",
    "VISUAL_EVIDENCE_MANIFEST_SCHEMA",
    "VISUAL_INFERENCE_PROFILE_SCHEMA",
    "VISUAL_INFERENCE_RESPONSE_SCHEMA",
    "VISUAL_PROPOSAL_APPROVED",
    "VISUAL_PROPOSAL_BLOCKED",
    "VISUAL_PROPOSAL_FAILED",
    "VISUAL_PROPOSAL_POLICY_VERSION",
    "VISUAL_PROPOSAL_PROTECTED_STATE_CHANGED",
    "VISUAL_PROPOSAL_RECEIPT_SCHEMA",
    "canonical_json_sha256",
    "validate_phase8_visual_proposal_receipt",
    "validate_visual_evidence_manifest",
    "validate_visual_inference_profile",
    "validate_visual_inference_response",
    "validate_visual_physical_proposal",
]
