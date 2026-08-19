"""Create a provenance-bound, offline proposal revision from human adjudication.

This utility deliberately has no database, gateway, or model-client dependency.
It preserves the source proposal and all original UAT receipts, and writes a new
revision namespace only after validating the source-state and adjudication bindings.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from classifire.services.physical_scope import is_blank_opening_type

REVISION_SCHEMA = "CLASSIFIRE-ADJUDICATED-PROPOSAL-v1"
FINAL_STATE_SCHEMA = "CLASSIFIRE-ADJUDICATED-PROPOSAL-ONLY-FINAL-STATE-v1"
DIFF_SCHEMA = "CLASSIFIRE-ADJUDICATED-PROPOSAL-DIFF-v1"
VALIDATION_SCHEMA = "CLASSIFIRE-HUMAN-ADJUDICATION-PROPOSAL-COMPARISON-v1"
ADJUDICATION_SCHEMA = "CLASSIFIRE-HUMAN-ADJUDICATION-v1"

PROPOSAL_FILENAME = "20-fireseal-merged-proposal-adjudicated.json"
DIFF_FILENAME = "20-adjudicated-proposal-diff.json"
FINAL_STATE_FILENAME = "21-adjudicated-proposal-only-final-state.json"
VALIDATION_FILENAME = "22-human-adjudication-proposal-comparison-v1.json"

_SERVICE_TYPE_ALIASES = {
    "air_duct": "flexible_duct",
    "cable_group": "cable_bundle",
}


class AdjudicatedProposalError(RuntimeError):
    """Raised when an offline adjudicated revision cannot be proven safe."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _read_json(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    try:
        payload_bytes = path.read_bytes()
    except OSError as exc:
        raise AdjudicatedProposalError(f"Cannot read {label}.") from exc
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdjudicatedProposalError(f"{label} is not valid UTF-8 JSON.") from exc
    if not isinstance(payload, dict):
        raise AdjudicatedProposalError(f"{label} root must be an object.")
    return payload, _sha256_bytes(payload_bytes)


def _require_sha256(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdefABCDEF" for char in value)
    ):
        raise AdjudicatedProposalError(f"{label} must be a 64-character SHA-256.")
    return value.upper()


def _resolve_bound_path(base_path: Path, value: object, *, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise AdjudicatedProposalError(f"{label} must be a nonblank path.")
    path = Path(value)
    if not path.is_absolute():
        path = base_path.resolve().parent / path
    return path.resolve()


def _nonblank_string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdjudicatedProposalError(f"{label} must be a nonblank string.")
    return value.strip()


def _protected_state(source_state: dict[str, Any]) -> dict[str, Any]:
    protected = source_state.get("protected_state")
    if not isinstance(protected, dict):
        raise AdjudicatedProposalError("Source final-state receipt has no protected_state.")
    if protected.get("protected_state_unchanged") is not True:
        raise AdjudicatedProposalError(
            "Source final-state receipt does not prove protected_state_unchanged=true."
        )
    before = _require_sha256(
        protected.get("before_fingerprint"), label="Source protected before_fingerprint"
    )
    after = _require_sha256(
        protected.get("after_fingerprint"), label="Source protected after_fingerprint"
    )
    if before != after:
        raise AdjudicatedProposalError("Source protected-state fingerprints differ.")
    return copy.deepcopy(protected)


def _require_list(payload: dict[str, Any], key: str, *, label: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise AdjudicatedProposalError(f"{label} {key} must be a list.")
    if not all(isinstance(row, dict) for row in value):
        raise AdjudicatedProposalError(f"{label} {key} entries must be objects.")
    return value


def _proposal_collections(
    proposal: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    openings = _require_list(proposal, "openings", label="Source proposal")
    services = _require_list(proposal, "services", label="Source proposal")
    seen_openings: set[str] = set()
    opening_ids: set[str] = set()
    for opening in openings:
        code = _nonblank_string(opening.get("opening_code"), label="Source opening_code")
        external_id = _nonblank_string(
            opening.get("external_defect_id"), label="Source external_defect_id"
        )
        if code in seen_openings:
            raise AdjudicatedProposalError(f"Source proposal duplicates opening_code {code}.")
        seen_openings.add(code)
        opening_ids.add(external_id)
    seen_services: set[str] = set()
    for service in services:
        code = _nonblank_string(service.get("service_code"), label="Source service_code")
        if code in seen_services:
            raise AdjudicatedProposalError(f"Source proposal duplicates service_code {code}.")
        seen_services.add(code)
        codes = service.get("opening_codes")
        if not isinstance(codes, list) or not codes:
            raise AdjudicatedProposalError(
                f"Source service {code} opening_codes must be a nonempty list."
            )
        if any(not isinstance(item, str) or item not in seen_openings for item in codes):
            raise AdjudicatedProposalError(f"Source service {code} references an unknown opening.")
    if not opening_ids:
        raise AdjudicatedProposalError("Source proposal has no openings.")
    return openings, services


def _validate_inputs(
    *,
    proposal_path: Path,
    source_state_path: Path,
    adjudication_path: Path,
) -> dict[str, Any]:
    proposal, proposal_sha256 = _read_json(proposal_path, label="Source proposal")
    openings, services = _proposal_collections(proposal)
    source_state, source_state_sha256 = _read_json(
        source_state_path, label="Source final-state receipt"
    )
    if source_state.get("canonical_write_performed") is not False:
        raise AdjudicatedProposalError(
            "Source final-state receipt does not prove canonical_write_performed=false."
        )
    bound_proposal_path = _resolve_bound_path(
        source_state_path,
        source_state.get("proposal_receipt"),
        label="Source final-state receipt proposal_receipt",
    )
    if bound_proposal_path != proposal_path.resolve():
        raise AdjudicatedProposalError(
            "Source final-state receipt proposal_receipt does not bind the source proposal."
        )
    estimate_id = _nonblank_string(source_state.get("estimate_id"), label="Source estimate_id")
    run_id = _nonblank_string(source_state.get("run_id"), label="Source run_id")
    protected = _protected_state(source_state)

    adjudication, adjudication_sha256 = _read_json(
        adjudication_path, label="Human adjudication record"
    )
    if adjudication.get("schema") != ADJUDICATION_SCHEMA:
        raise AdjudicatedProposalError("Human adjudication record schema is not supported.")
    if adjudication.get("canonical_write_performed") is not False:
        raise AdjudicatedProposalError(
            "Human adjudication record does not prove canonical_write_performed=false."
        )
    if adjudication.get("estimate_id") != estimate_id or adjudication.get("run_id") != run_id:
        raise AdjudicatedProposalError(
            "Human adjudication record does not match source estimate_id and run_id."
        )
    comparison = adjudication.get("comparison_receipt")
    if not isinstance(comparison, dict):
        raise AdjudicatedProposalError("Human adjudication record has no comparison_receipt.")
    comparison_path = _resolve_bound_path(
        adjudication_path,
        comparison.get("path"),
        label="Human adjudication comparison_receipt.path",
    )
    _, comparison_sha256 = _read_json(comparison_path, label="Human comparison receipt")
    if comparison_sha256 != _require_sha256(
        comparison.get("sha256"), label="Human adjudication comparison_receipt.sha256"
    ):
        raise AdjudicatedProposalError(
            "Human adjudication comparison_receipt bytes do not match its declared SHA-256."
        )
    decisions = _require_list(adjudication, "decisions", label="Human adjudication record")
    decision_ids = [
        _nonblank_string(row.get("external_defect_id"), label="Adjudication external_defect_id")
        for row in decisions
    ]
    if len(decision_ids) != len(set(decision_ids)):
        raise AdjudicatedProposalError(
            "Human adjudication record duplicates an external_defect_id."
        )
    source_ids = {str(row["external_defect_id"]).strip() for row in openings}
    unknown_ids = sorted(set(decision_ids) - source_ids)
    if unknown_ids:
        raise AdjudicatedProposalError(
            "Human adjudication references source defects that are absent: "
            + ", ".join(unknown_ids)
        )
    return {
        "proposal": proposal,
        "proposal_sha256": proposal_sha256,
        "source_state": source_state,
        "source_state_sha256": source_state_sha256,
        "adjudication": adjudication,
        "adjudication_sha256": adjudication_sha256,
        "comparison_path": comparison_path,
        "comparison_sha256": comparison_sha256,
        "estimate_id": estimate_id,
        "run_id": run_id,
        "protected_state": protected,
        "openings": openings,
        "services": services,
    }


def _orientation_for_plane(plane: object, fallback: object) -> object:
    if plane == "wall":
        return "vertical"
    if plane == "floor":
        return "horizontal"
    return fallback


def _service_type(raw_type: object) -> str:
    service_type = _nonblank_string(raw_type, label="Adjudicated service_type")
    return _SERVICE_TYPE_ALIASES.get(service_type, service_type)


def _source_reference_for(
    *, services: list[dict[str, Any]], opening_codes: set[str], external_id: str
) -> str:
    references = [
        str(service["source_reference"]).strip()
        for service in services
        if set(service.get("opening_codes", [])) & opening_codes
        and isinstance(service.get("source_reference"), str)
        and service["source_reference"].strip()
    ]
    if references:
        return "; ".join(dict.fromkeys(references))
    return f"Human adjudication; defect {external_id}"


def _adjudicated_opening(
    *,
    descriptor: dict[str, Any],
    source_template: dict[str, Any],
    external_id: str,
    ordinal: int,
    adjudication_sha256: str,
    decision: str,
) -> dict[str, Any]:
    classification = _nonblank_string(
        descriptor.get("classification"), label=f"Adjudicated opening {external_id} classification"
    )
    blank = classification == "blank_opening_seal"
    plane = descriptor.get("substrate_plane", source_template.get("substrate_plane"))
    substrate = descriptor.get("substrate_type", source_template.get("substrate_type"))
    opening = {
        "external_defect_id": external_id,
        "opening_code": f"A-{external_id}-O-{ordinal:02d}",
        "opening_type": "blank_core_hole" if blank else "service_penetration",
        "substrate_type": substrate,
        "substrate_plane": plane,
        "orientation": _orientation_for_plane(plane, source_template.get("orientation")),
        "location": source_template.get("location"),
        "frl": source_template.get("frl"),
        "notes": (
            f"Human adjudication {adjudication_sha256} applied to decision {decision}. "
            "Attributes not supplied by the human adjudication preserve the source proposal."
        ),
    }
    return {key: value for key, value in opening.items() if value is not None}


def _adjudicated_services(
    *,
    descriptor: dict[str, Any],
    opening_code: str,
    external_id: str,
    opening_ordinal: int,
    adjudication_sha256: str,
    source_reference: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups = descriptor.get("service_groups")
    if not isinstance(groups, list):
        raise AdjudicatedProposalError(
            f"Adjudicated opening {external_id} service_groups must be a list."
        )
    services: list[dict[str, Any]] = []
    limitations: list[dict[str, Any]] = []
    for index, group in enumerate(groups, start=1):
        if not isinstance(group, dict):
            raise AdjudicatedProposalError(
                f"Adjudicated opening {external_id} service group must be an object."
            )
        raw_quantity = group.get("quantity")
        withheld = raw_quantity is None
        if withheld:
            quantity = 1
        elif isinstance(raw_quantity, bool) or not isinstance(raw_quantity, (int, float)):
            raise AdjudicatedProposalError(
                f"Adjudicated service quantity for {external_id} must be numeric or withheld."
            )
        elif raw_quantity <= 0:
            raise AdjudicatedProposalError(
                f"Adjudicated service quantity for {external_id} must be greater than zero."
            )
        else:
            quantity = raw_quantity
        service_type = _service_type(group.get("service_type"))
        quantity_status = group.get("quantity_status")
        notes = (
            f"Human adjudication {adjudication_sha256}; {service_type} group for defect "
            f"{external_id}."
        )
        if quantity_status == "APPROXIMATE":
            notes += " Quantity is approximate and must not be treated as a measured count."
        if withheld:
            notes += (
                " Individual cable count is withheld; quantity one represents the confirmed "
                "group only, not individual services."
            )
            limitations.append(
                {
                    "external_defect_id": external_id,
                    "opening_code": opening_code,
                    "service_type": service_type,
                    "status": "QUANTITY_WITHHELD",
                    "reason": (
                        "Human adjudication confirms the group but withholds an individual count."
                    ),
                }
            )
        service: dict[str, Any] = {
            "service_code": f"A-{external_id}-S-{opening_ordinal:02d}-{index:02d}",
            "service_type": service_type,
            "quantity": quantity,
            "primary_opening_code": opening_code,
            "opening_codes": [opening_code],
            "relationship_status": "confirmed",
            "evidence_status": "human_adjudicated",
            "confidence": 1.0,
            "link_type": "penetrates",
            "source_reference": source_reference,
            "notes": notes,
        }
        material = group.get("material")
        if material is not None:
            service["material"] = material
        services.append(service)
    return services, limitations


def _rebuild_full_decision(
    *,
    decision: dict[str, Any],
    source_openings: list[dict[str, Any]],
    source_services: list[dict[str, Any]],
    adjudication_sha256: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    external_id = _nonblank_string(
        decision.get("external_defect_id"), label="Adjudication external_defect_id"
    )
    descriptors = decision.get("openings")
    if not isinstance(descriptors, list) or not descriptors:
        raise AdjudicatedProposalError(
            f"Adjudication decision for {external_id} must provide a nonempty openings list."
        )
    source_for_defect = [
        row for row in source_openings if row.get("external_defect_id") == external_id
    ]
    if not source_for_defect:
        raise AdjudicatedProposalError(f"Source proposal has no openings for {external_id}.")
    source_codes = {
        _nonblank_string(row.get("opening_code"), label="Source opening_code")
        for row in source_for_defect
    }
    for service in source_services:
        service_codes = set(service.get("opening_codes", []))
        if service_codes & source_codes and not service_codes <= source_codes:
            raise AdjudicatedProposalError(
                f"Source service {service.get('service_code')} crosses adjudicated defect "
                f"{external_id}."
            )
    source_reference = _source_reference_for(
        services=source_services, opening_codes=source_codes, external_id=external_id
    )
    rebuilt_openings: list[dict[str, Any]] = []
    rebuilt_services: list[dict[str, Any]] = []
    limitations: list[dict[str, Any]] = []
    decision_name = _nonblank_string(decision.get("decision"), label="Adjudication decision")
    for ordinal, descriptor in enumerate(descriptors, start=1):
        if not isinstance(descriptor, dict):
            raise AdjudicatedProposalError(f"Adjudicated opening {external_id} must be an object.")
        template = source_for_defect[min(ordinal - 1, len(source_for_defect) - 1)]
        opening = _adjudicated_opening(
            descriptor=descriptor,
            source_template=template,
            external_id=external_id,
            ordinal=ordinal,
            adjudication_sha256=adjudication_sha256,
            decision=decision_name,
        )
        services, opening_limitations = _adjudicated_services(
            descriptor=descriptor,
            opening_code=str(opening["opening_code"]),
            external_id=external_id,
            opening_ordinal=ordinal,
            adjudication_sha256=adjudication_sha256,
            source_reference=source_reference,
        )
        if is_blank_opening_type(opening["opening_type"]) and services:
            raise AdjudicatedProposalError(
                f"Adjudicated blank opening {opening['opening_code']} has services."
            )
        if not is_blank_opening_type(opening["opening_type"]) and not services:
            raise AdjudicatedProposalError(
                f"Adjudicated nonblank opening {opening['opening_code']} has no services."
            )
        rebuilt_openings.append(opening)
        rebuilt_services.extend(services)
        limitations.extend(opening_limitations)
    return rebuilt_openings, rebuilt_services, limitations


def _apply_empty_core_decision(
    *,
    decision: dict[str, Any],
    openings: list[dict[str, Any]],
    services: list[dict[str, Any]],
    adjudication_sha256: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    external_id = _nonblank_string(
        decision.get("external_defect_id"), label="Adjudication external_defect_id"
    )
    opening_code = _nonblank_string(
        decision.get("revision_source_opening_code"),
        label=f"Adjudication {external_id} revision_source_opening_code",
    )
    target = [
        row
        for row in openings
        if row.get("external_defect_id") == external_id and row.get("opening_code") == opening_code
    ]
    if len(target) != 1:
        raise AdjudicatedProposalError(
            f"Adjudication {external_id} cannot bind source opening {opening_code}."
        )
    changed_openings: list[dict[str, Any]] = []
    for row in openings:
        if row is target[0]:
            changed = copy.deepcopy(row)
            changed["opening_type"] = "blank_core_hole"
            changed["notes"] = (
                f"{str(changed.get('notes', '')).strip()} | Human adjudication "
                f"{adjudication_sha256} confirms this is an empty core/blank opening seal; "
                "no service is modelled."
            ).strip()
            changed_openings.append(changed)
        else:
            changed_openings.append(row)
    changed_services = [
        row for row in services if opening_code not in set(row.get("opening_codes", []))
    ]
    return changed_openings, changed_services


def _count_by_external(
    openings: list[dict[str, Any]], services: list[dict[str, Any]]
) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = defaultdict(lambda: {"openings": 0, "services": 0})
    opening_by_code = {str(row["opening_code"]): str(row["external_defect_id"]) for row in openings}
    for row in openings:
        result[str(row["external_defect_id"])]["openings"] += 1
    for service in services:
        ids = {opening_by_code.get(str(code)) for code in service.get("opening_codes", [])}
        if len(ids) != 1 or None in ids:
            raise AdjudicatedProposalError(
                f"Revision service {service.get('service_code')} has invalid cross-defect links."
            )
        result[ids.pop()]["services"] += 1
    return {key: value for key, value in sorted(result.items())}


def build_revision(inputs: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    source = copy.deepcopy(inputs["proposal"])
    openings = copy.deepcopy(inputs["openings"])
    services = copy.deepcopy(inputs["services"])
    adjudication = inputs["adjudication"]
    decisions = adjudication["decisions"]
    decision_by_id = {str(row["external_defect_id"]): row for row in decisions}

    before_counts = _count_by_external(openings, services)
    limitations = list(source.get("limitations", []))
    if not all(isinstance(row, dict) for row in limitations):
        raise AdjudicatedProposalError("Source proposal limitations entries must be objects.")
    withheld_details: list[dict[str, Any]] = []

    full_decisions = [row for row in decisions if isinstance(row.get("openings"), list)]
    full_ids = {str(row["external_defect_id"]) for row in full_decisions}
    replacements: dict[
        str, tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]
    ] = {}
    for decision in full_decisions:
        external_id = str(decision["external_defect_id"])
        replacements[external_id] = _rebuild_full_decision(
            decision=decision,
            source_openings=inputs["openings"],
            source_services=inputs["services"],
            adjudication_sha256=inputs["adjudication_sha256"],
        )

    rebuilt_openings: list[dict[str, Any]] = []
    inserted_ids: set[str] = set()
    for opening in openings:
        external_id = str(opening["external_defect_id"])
        if external_id not in full_ids:
            rebuilt_openings.append(opening)
            continue
        if external_id not in inserted_ids:
            rebuilt_openings.extend(replacements[external_id][0])
            inserted_ids.add(external_id)
    rebuilt_services: list[dict[str, Any]] = []
    inserted_service_ids: set[str] = set()
    source_codes_by_full_id = {
        external_id: {
            str(row["opening_code"])
            for row in openings
            if str(row["external_defect_id"]) == external_id
        }
        for external_id in full_ids
    }
    for service in services:
        references = set(service.get("opening_codes", []))
        matched_ids = [
            external_id
            for external_id, source_codes in source_codes_by_full_id.items()
            if references & source_codes
        ]
        if not matched_ids:
            rebuilt_services.append(service)
            continue
        if len(matched_ids) != 1:
            raise AdjudicatedProposalError(
                f"Source service {service.get('service_code')} spans multiple adjudicated defects."
            )
        external_id = matched_ids[0]
        if external_id not in inserted_service_ids:
            rebuilt_services.extend(replacements[external_id][1])
            inserted_service_ids.add(external_id)
    for external_id in full_ids:
        withheld_details.extend(replacements[external_id][2])

    for decision in decisions:
        if decision.get("decision") != "EMPTY_CORE_IS_BLANK_OPENING_SEAL":
            continue
        if isinstance(decision.get("openings"), list):
            raise AdjudicatedProposalError(
                "EMPTY_CORE_IS_BLANK_OPENING_SEAL must not also replace a full topology."
            )
        rebuilt_openings, rebuilt_services = _apply_empty_core_decision(
            decision=decision,
            openings=rebuilt_openings,
            services=rebuilt_services,
            adjudication_sha256=inputs["adjudication_sha256"],
        )

    after_counts = _count_by_external(rebuilt_openings, rebuilt_services)
    revision = copy.deepcopy(source)
    revision.update(
        {
            "schema": REVISION_SCHEMA,
            "revision_scope": "OFFLINE_HUMAN_ADJUDICATION_ONLY",
            "source_proposal": {
                "path": str(Path(inputs["source_state"]["proposal_receipt"]).resolve()),
                "sha256": inputs["proposal_sha256"],
            },
            "human_adjudication": {
                "path": str(inputs["adjudication_path"]),
                "sha256": inputs["adjudication_sha256"],
            },
            "runtime_inference_performed": False,
            "gateway_call_performed": False,
            "database_write_performed": False,
            "canonical_write_performed": False,
            "openings": rebuilt_openings,
            "services": rebuilt_services,
            "limitations": limitations,
            "adjudication_withheld_details": withheld_details,
            "proposed_opening_count": len(rebuilt_openings),
            "proposed_service_count": len(rebuilt_services),
        }
    )
    diff_changes = []
    for external_id in sorted(decision_by_id):
        diff_changes.append(
            {
                "external_defect_id": external_id,
                "decision": decision_by_id[external_id]["decision"],
                "before": before_counts.get(external_id, {"openings": 0, "services": 0}),
                "after": after_counts.get(external_id, {"openings": 0, "services": 0}),
            }
        )
    diff = {
        "schema": DIFF_SCHEMA,
        "run_id": inputs["run_id"],
        "estimate_id": inputs["estimate_id"],
        "scope": "OFFLINE_HUMAN_ADJUDICATION_ONLY",
        "source_proposal_sha256": inputs["proposal_sha256"],
        "source_final_state_sha256": inputs["source_state_sha256"],
        "human_adjudication_sha256": inputs["adjudication_sha256"],
        "human_comparison_sha256": inputs["comparison_sha256"],
        "database_write_performed": False,
        "gateway_call_performed": False,
        "changes": diff_changes,
        "counts": {
            "before": {
                "openings": len(inputs["openings"]),
                "services": len(inputs["services"]),
            },
            "after": {"openings": len(rebuilt_openings), "services": len(rebuilt_services)},
        },
    }
    return revision, diff


def _simplified_revision_topology(
    proposal: dict[str, Any], external_id: str
) -> list[dict[str, Any]]:
    openings, services = _proposal_collections(proposal)
    opening_rows = [row for row in openings if row.get("external_defect_id") == external_id]
    opening_codes = {str(row["opening_code"]) for row in opening_rows}
    services_by_opening: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for service in services:
        for code in service.get("opening_codes", []):
            if code in opening_codes:
                services_by_opening[str(code)].append(service)
    result = []
    for opening in opening_rows:
        code = str(opening["opening_code"])
        groups = []
        for service in services_by_opening[code]:
            groups.append(
                {
                    "service_type": service.get("service_type"),
                    "material": service.get("material"),
                    "quantity": service.get("quantity"),
                }
            )
        result.append(
            {
                "opening_code": code,
                "blank": is_blank_opening_type(str(opening.get("opening_type") or "")),
                "substrate_type": opening.get("substrate_type"),
                "substrate_plane": opening.get("substrate_plane"),
                "services": sorted(groups, key=lambda row: json.dumps(row, sort_keys=True)),
            }
        )
    return result


def _expected_topology_from_decision(decision: dict[str, Any]) -> list[dict[str, Any]]:
    expected = []
    for descriptor in decision.get("openings", []):
        if not isinstance(descriptor, dict):
            raise AdjudicatedProposalError("Adjudication opening must be an object.")
        groups = []
        for service in descriptor.get("service_groups", []):
            if not isinstance(service, dict):
                raise AdjudicatedProposalError("Adjudication service group must be an object.")
            groups.append(
                {
                    "service_type": _service_type(service.get("service_type")),
                    "material": service.get("material"),
                    "quantity": 1 if service.get("quantity") is None else service.get("quantity"),
                }
            )
        expected.append(
            {
                "blank": descriptor.get("classification") == "blank_opening_seal",
                "substrate_type": descriptor.get("substrate_type"),
                "substrate_plane": descriptor.get("substrate_plane"),
                "services": sorted(groups, key=lambda row: json.dumps(row, sort_keys=True)),
            }
        )
    return expected


def validate_adjudicated_revision(
    *, proposal: dict[str, Any], adjudication: dict[str, Any]
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for decision in adjudication["decisions"]:
        external_id = str(decision["external_defect_id"])
        if decision.get("decision") == "EMPTY_CORE_IS_BLANK_OPENING_SEAL":
            target_code = _nonblank_string(
                decision.get("revision_source_opening_code"),
                label=f"Adjudication {external_id} revision_source_opening_code",
            )
            actual = _simplified_revision_topology(proposal, external_id)
            matched = [row for row in actual if row["opening_code"] == target_code]
            passed = len(matched) == 1 and matched[0]["blank"] and not matched[0]["services"]
            results.append(
                {
                    "external_defect_id": external_id,
                    "decision": decision["decision"],
                    "status": "PASS" if passed else "MISMATCH",
                    "issues": (
                        [] if passed else ["Target empty core was not rendered as a blank opening."]
                    ),
                }
            )
            continue
        actual = _simplified_revision_topology(proposal, external_id)
        expected = _expected_topology_from_decision(decision)
        compact_actual = [
            {
                "blank": row["blank"],
                "substrate_type": row["substrate_type"],
                "substrate_plane": row["substrate_plane"],
                "services": row["services"],
            }
            for row in actual
        ]
        # A human topology can deliberately omit substrate detail. Preserve source values then.
        for row in expected:
            if row["substrate_type"] is None:
                row.pop("substrate_type")
            if row["substrate_plane"] is None:
                row.pop("substrate_plane")
        if len(compact_actual) != len(expected):
            passed = False
        else:
            adjacency = [
                [
                    actual_index
                    for actual_index, actual_row in enumerate(compact_actual)
                    if all(actual_row.get(key) == value for key, value in expected_row.items())
                ]
                for expected_row in expected
            ]
            matched_actual: dict[int, int] = {}

            def assign(
                expected_index: int,
                seen: set[int],
                *,
                _adjacency: list[list[int]] = adjacency,
                _matched_actual: dict[int, int] = matched_actual,
            ) -> bool:
                for actual_index in _adjacency[expected_index]:
                    if actual_index in seen:
                        continue
                    seen.add(actual_index)
                    prior = _matched_actual.get(actual_index)
                    if prior is None or assign(prior, seen):
                        _matched_actual[actual_index] = expected_index
                        return True
                return False

            passed = all(assign(index, set()) for index in range(len(expected)))
        results.append(
            {
                "external_defect_id": external_id,
                "decision": decision["decision"],
                "status": "PASS" if passed else "MISMATCH",
                "issues": (
                    [] if passed else ["Revision topology does not match the human adjudication."]
                ),
            }
        )
    mismatch_count = sum(row["status"] != "PASS" for row in results)
    return {
        "schema": VALIDATION_SCHEMA,
        "status": "PASS" if mismatch_count == 0 else "MISMATCH",
        "defect_count": len(results),
        "passed_defect_count": len(results) - mismatch_count,
        "mismatch_defect_count": mismatch_count,
        "defects": results,
    }


def _write_new_json(path: Path, payload: dict[str, Any]) -> str:
    if path.exists():
        raise AdjudicatedProposalError(f"Refusing to overwrite existing artifact {path.name}.")
    encoded = _canonical_json_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            raise AdjudicatedProposalError(f"Refusing to overwrite existing artifact {path.name}.")
        Path(temporary_name).replace(path)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise
    return _sha256_bytes(encoded)


def create_revision(
    *,
    proposal_path: Path,
    source_state_path: Path,
    adjudication_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    proposal_path = proposal_path.resolve()
    source_state_path = source_state_path.resolve()
    adjudication_path = adjudication_path.resolve()
    output_dir = output_dir.resolve()
    if output_dir in {
        proposal_path.parent,
        source_state_path.parent,
        adjudication_path.parent,
    }:
        raise AdjudicatedProposalError(
            "Output directory must be a fresh revision namespace, not the source UAT directory."
        )
    inputs = _validate_inputs(
        proposal_path=proposal_path,
        source_state_path=source_state_path,
        adjudication_path=adjudication_path,
    )
    inputs["adjudication_path"] = adjudication_path
    revision, diff = build_revision(inputs)
    validation = validate_adjudicated_revision(
        proposal=revision, adjudication=inputs["adjudication"]
    )
    if validation["status"] != "PASS":
        raise AdjudicatedProposalError("Generated revision does not match human adjudication.")

    expected_paths = [
        output_dir / PROPOSAL_FILENAME,
        output_dir / DIFF_FILENAME,
        output_dir / FINAL_STATE_FILENAME,
        output_dir / VALIDATION_FILENAME,
    ]
    existing = [path.name for path in expected_paths if path.exists()]
    if existing:
        raise AdjudicatedProposalError(
            "Refusing to overwrite existing revision artifacts: " + ", ".join(existing)
        )
    proposal_sha256 = _write_new_json(output_dir / PROPOSAL_FILENAME, revision)
    diff["revision_proposal_sha256"] = proposal_sha256
    diff_sha256 = _write_new_json(output_dir / DIFF_FILENAME, diff)
    final_state = {
        "schema": FINAL_STATE_SCHEMA,
        "status": "ADJUDICATED_PROPOSAL_READY_FOR_HUMAN_REVIEW",
        "run_id": f"{inputs['run_id']}-adjudicated-v1",
        "source_run_id": inputs["run_id"],
        "estimate_id": inputs["estimate_id"],
        "proposal_receipt": PROPOSAL_FILENAME,
        "proposal_sha256": proposal_sha256,
        "source_proposal": {
            "path": str(proposal_path),
            "sha256": inputs["proposal_sha256"],
        },
        "source_final_state": {
            "path": str(source_state_path),
            "sha256": inputs["source_state_sha256"],
        },
        "human_adjudication": {
            "path": str(adjudication_path),
            "sha256": inputs["adjudication_sha256"],
        },
        "diff_receipt": {"path": DIFF_FILENAME, "sha256": diff_sha256},
        "withheld_tool": "classifire_submit_initial_physical_model",
        "canonical_write_performed": False,
        "database_write_performed": False,
        "gateway_call_performed": False,
        "runtime_inference_performed": False,
        "protected_state": inputs["protected_state"],
    }
    final_state_sha256 = _write_new_json(output_dir / FINAL_STATE_FILENAME, final_state)
    validation.update(
        {
            "estimate_id": inputs["estimate_id"],
            "source_run_id": inputs["run_id"],
            "revision_proposal": {"path": PROPOSAL_FILENAME, "sha256": proposal_sha256},
            "final_state_receipt": {
                "path": FINAL_STATE_FILENAME,
                "sha256": final_state_sha256,
            },
            "human_adjudication": {
                "path": str(adjudication_path),
                "sha256": inputs["adjudication_sha256"],
            },
            "comparison_interpretation": (
                "This receipt validates the offline revision against the human adjudication. "
                "It does not replace the historical source-reference comparison."
            ),
            "canonical_write_performed": False,
            "database_write_performed": False,
            "gateway_call_performed": False,
        }
    )
    validation_sha256 = _write_new_json(output_dir / VALIDATION_FILENAME, validation)
    return {
        "proposal_path": str((output_dir / PROPOSAL_FILENAME).resolve()),
        "proposal_sha256": proposal_sha256,
        "diff_path": str((output_dir / DIFF_FILENAME).resolve()),
        "diff_sha256": diff_sha256,
        "final_state_path": str((output_dir / FINAL_STATE_FILENAME).resolve()),
        "final_state_sha256": final_state_sha256,
        "validation_path": str((output_dir / VALIDATION_FILENAME).resolve()),
        "validation_sha256": validation_sha256,
        "status": validation["status"],
        "canonical_write_performed": False,
        "database_write_performed": False,
        "gateway_call_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--source-state", type=Path, required=True)
    parser.add_argument("--adjudication", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = create_revision(
            proposal_path=args.proposal,
            source_state_path=args.source_state,
            adjudication_path=args.adjudication,
            output_dir=args.output_dir,
        )
    except AdjudicatedProposalError as exc:
        print(f"ADJUDICATED_REVISION_FAILED: {exc}")
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
