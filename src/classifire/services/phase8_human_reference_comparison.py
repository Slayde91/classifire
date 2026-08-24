"""Post-inference comparison against a validation-only human reference.

This module deliberately has no inference, database, canonical-write, admission,
signing, registration, or lock interface. It accepts only explicit JSON
artifacts after a Phase 8 proposal run has finished.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .phase8_visual_proposal import (
    VISUAL_PROPOSAL_APPROVED,
    canonical_json_sha256,
    validate_phase8_visual_proposal_receipt,
    validate_visual_physical_proposal,
)
from .physical_scope import is_blank_opening_type

HUMAN_REFERENCE_SCHEMA = "CLASSIFIRE-HUMAN-PHYSICAL-REFERENCE-v1"
HUMAN_REFERENCE_PURPOSE = (
    "Regression reference only. Must never be used as runtime inference input."
)
HUMAN_COMPARISON_SCHEMA = "CLASSIFIRE-PHASE8-HUMAN-REFERENCE-COMPARISON-v1"
MAX_ARTIFACT_BYTES = 5 * 1024 * 1024

_OpeningSignature = tuple[bool, tuple[tuple[str, str | None, str | None], ...]]


class Phase8HumanReferenceComparisonError(RuntimeError):
    """Fail-closed validation error for comparison inputs."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        message = f"Phase 8 human-reference comparison failed: {code}."
        if detail:
            message += f" {detail}"
        super().__init__(message)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def _read_json_object(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    if not isinstance(path, Path) or not path.is_file():
        raise Phase8HumanReferenceComparisonError(
            "ARTIFACT_MISSING",
            f"{label}: {path}",
        )
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise Phase8HumanReferenceComparisonError(
            "ARTIFACT_UNREADABLE",
            label,
        ) from exc
    if not raw or len(raw) > MAX_ARTIFACT_BYTES:
        raise Phase8HumanReferenceComparisonError(
            "ARTIFACT_SIZE_INVALID",
            label,
        )
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Phase8HumanReferenceComparisonError(
            "ARTIFACT_JSON_INVALID",
            label,
        ) from exc
    if not isinstance(value, dict):
        raise Phase8HumanReferenceComparisonError(
            "ARTIFACT_ROOT_INVALID",
            f"{label} must be a JSON object",
        )
    return value, _sha256(raw)


def _nonblank(value: object) -> str:
    return str(value).strip() if isinstance(value, str) else ""


def _normalise_text(value: object) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").replace("-", " ").split())


def _normalise_service_type(value: object) -> str:
    text = _normalise_text(value)
    aliases = {
        "cables": "cable_bundle",
        "cable bundle": "cable_bundle",
        "flex duct": "flexible_duct",
        "flexi duct": "flexible_duct",
        "flexible duct": "flexible_duct",
        "aircon bundle": "aircon_bundle",
        "air con bundle": "aircon_bundle",
        "air conditioning bundle": "aircon_bundle",
    }
    normalised = aliases.get(text, text.replace(" ", "_"))
    if not normalised:
        raise Phase8HumanReferenceComparisonError(
            "SERVICE_TYPE_INVALID",
            "service type must be nonblank",
        )
    return normalised


def _normalise_material(value: object) -> str | None:
    text = _normalise_text(value)
    if not text:
        return None
    aliases = {
        "polyvinyl chloride": "pvc",
        "cu": "copper",
        "metallic": "metal",
    }
    return aliases.get(text, text)


def _quantity(value: object) -> str | None:
    if value is None:
        return None
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise Phase8HumanReferenceComparisonError(
            "SERVICE_QUANTITY_INVALID",
            repr(value),
        ) from exc
    if not quantity.is_finite() or quantity <= 0:
        raise Phase8HumanReferenceComparisonError(
            "SERVICE_QUANTITY_INVALID",
            repr(value),
        )
    return str(quantity.normalize())


def _service_signature(row: dict[str, Any]) -> tuple[str, str | None, str | None]:
    if "quantity" not in row:
        raise Phase8HumanReferenceComparisonError("SERVICE_QUANTITY_INVALID", "missing")
    return (
        _normalise_service_type(row.get("type") or row.get("service_type")),
        _normalise_material(row.get("material")),
        _quantity(row["quantity"]),
    )


def _opening_signature(row: dict[str, Any]) -> _OpeningSignature:
    blank = row.get("blank")
    if not isinstance(blank, bool):
        raise Phase8HumanReferenceComparisonError(
            "OPENING_BLANK_INVALID",
            "blank must be a boolean",
        )
    groups = row.get("service_groups")
    if not isinstance(groups, list) or any(not isinstance(item, dict) for item in groups):
        raise Phase8HumanReferenceComparisonError(
            "OPENING_SERVICE_GROUPS_INVALID",
            "service_groups must be a list of objects",
        )
    signatures = sorted(_service_signature(item) for item in groups)
    if blank and signatures:
        raise Phase8HumanReferenceComparisonError("BLANK_OPENING_HAS_SERVICES")
    if not blank and not signatures:
        raise Phase8HumanReferenceComparisonError("OCCUPIED_OPENING_HAS_NO_SERVICES")
    return blank, tuple(signatures)


def _load_reference(
    reference_path: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], str]:
    reference, reference_sha256 = _read_json_object(
        reference_path,
        label="human reference",
    )
    if reference.get("schema") != HUMAN_REFERENCE_SCHEMA:
        raise Phase8HumanReferenceComparisonError("HUMAN_REFERENCE_SCHEMA_INVALID")
    if reference.get("purpose") != HUMAN_REFERENCE_PURPOSE:
        raise Phase8HumanReferenceComparisonError("HUMAN_REFERENCE_PURPOSE_INVALID")
    if not _nonblank(reference.get("run_id")):
        raise Phase8HumanReferenceComparisonError("HUMAN_REFERENCE_RUN_ID_INVALID")
    defects = reference.get("defects")
    if not isinstance(defects, list):
        raise Phase8HumanReferenceComparisonError("HUMAN_REFERENCE_DEFECTS_INVALID")

    by_external_id: dict[str, dict[str, Any]] = {}
    for index, defect in enumerate(defects):
        if not isinstance(defect, dict):
            raise Phase8HumanReferenceComparisonError(
                "HUMAN_REFERENCE_DEFECT_INVALID",
                str(index),
            )
        external_id = _nonblank(defect.get("external_defect_id"))
        if not external_id:
            raise Phase8HumanReferenceComparisonError(
                "HUMAN_REFERENCE_DEFECT_ID_INVALID",
                str(index),
            )
        if external_id in by_external_id:
            raise Phase8HumanReferenceComparisonError(
                "HUMAN_REFERENCE_DEFECT_ID_DUPLICATE",
                external_id,
            )
        openings = defect.get("openings")
        opening_count = defect.get("opening_count")
        if (
            isinstance(opening_count, bool)
            or not isinstance(opening_count, int)
            or opening_count < 0
        ):
            raise Phase8HumanReferenceComparisonError(
                "HUMAN_REFERENCE_OPENING_COUNT_INVALID",
                external_id,
            )
        if not isinstance(openings, list) or any(
            not isinstance(opening, dict) for opening in openings
        ):
            raise Phase8HumanReferenceComparisonError(
                "HUMAN_REFERENCE_OPENINGS_INVALID",
                external_id,
            )
        if opening_count != len(openings):
            raise Phase8HumanReferenceComparisonError(
                "HUMAN_REFERENCE_OPENING_COUNT_MISMATCH",
                external_id,
            )
        for opening in openings:
            _opening_signature(opening)
        by_external_id[external_id] = defect
    return reference, by_external_id, reference_sha256


def validate_phase8_human_reference(reference_path: Path) -> None:
    """Validate a post-inference-only human reference before a runtime begins."""

    _load_reference(reference_path)


def _proposal_openings(
    proposal: dict[str, Any],
    *,
    defect_reference: str,
) -> list[dict[str, Any]]:
    errors = validate_visual_physical_proposal(
        proposal,
        defect_reference=defect_reference,
    )
    if errors or _nonblank(proposal.get("status")).upper() != "MODEL_SUPPORTED":
        detail = "; ".join(errors) if errors else "status is not MODEL_SUPPORTED"
        raise Phase8HumanReferenceComparisonError("PROPOSAL_INVALID", detail)

    raw_openings = proposal.get("openings")
    raw_services = proposal.get("services")
    if not isinstance(raw_openings, list) or not isinstance(raw_services, list):
        raise Phase8HumanReferenceComparisonError("PROPOSAL_INVALID")

    opening_by_code: dict[str, dict[str, Any]] = {}
    for raw_opening in raw_openings:
        if not isinstance(raw_opening, dict):
            raise Phase8HumanReferenceComparisonError("PROPOSAL_OPENING_INVALID")
        opening_code = _nonblank(raw_opening.get("opening_code"))
        if not opening_code or opening_code in opening_by_code:
            raise Phase8HumanReferenceComparisonError(
                "PROPOSAL_OPENING_CODE_INVALID",
                opening_code,
            )
        opening_by_code[opening_code] = {
            "opening_code": opening_code,
            "blank": is_blank_opening_type(raw_opening.get("opening_type")),
            "substrate_type": raw_opening.get("substrate_type"),
            "substrate_plane": raw_opening.get("substrate_plane"),
            "orientation": raw_opening.get("orientation"),
            "notes": raw_opening.get("notes"),
            "service_groups": [],
        }

    for raw_service in raw_services:
        if not isinstance(raw_service, dict):
            raise Phase8HumanReferenceComparisonError("PROPOSAL_SERVICE_INVALID")
        service_code = _nonblank(raw_service.get("service_code"))
        opening_codes = raw_service.get("opening_codes")
        if not service_code or not isinstance(opening_codes, list):
            raise Phase8HumanReferenceComparisonError(
                "PROPOSAL_SERVICE_INVALID",
                service_code,
            )
        service_group = {
            "service_code": service_code,
            "service_type": raw_service.get("service_type"),
            "material": raw_service.get("material"),
            "quantity": raw_service.get("quantity"),
            "notes": raw_service.get("notes"),
        }
        for opening_code in opening_codes:
            opening = opening_by_code.get(str(opening_code))
            if opening is None:
                raise Phase8HumanReferenceComparisonError(
                    "PROPOSAL_SERVICE_OPENING_UNKNOWN",
                    f"{service_code}: {opening_code}",
                )
            opening["service_groups"].append(dict(service_group))

    rows = list(opening_by_code.values())
    for row in rows:
        _opening_signature(row)
    return rows


def _controller_context(
    *,
    receipt: dict[str, Any],
    receipt_path: Path,
    receipt_sha256: str,
    proposal: dict[str, Any],
    proposal_path: Path,
    proposal_sha256: str,
) -> tuple[str, str, dict[str, Any]]:
    receipt_errors = validate_phase8_visual_proposal_receipt(receipt)
    if receipt_errors:
        raise Phase8HumanReferenceComparisonError(
            "CONTROLLER_RECEIPT_INVALID",
            "; ".join(receipt_errors),
        )
    if receipt.get("status") != VISUAL_PROPOSAL_APPROVED:
        raise Phase8HumanReferenceComparisonError(
            "CONTROLLER_RECEIPT_NOT_APPROVED",
            str(receipt.get("status")),
        )
    estimate_id = _nonblank(receipt.get("estimate_id"))
    defect_reference = _nonblank(receipt.get("defect_reference"))
    if not estimate_id or not defect_reference:
        raise Phase8HumanReferenceComparisonError("CONTROLLER_RECEIPT_IDENTITY_INVALID")

    proposal_canonical_sha256 = canonical_json_sha256(proposal)
    result_hashes = receipt.get("result_hashes")
    bound_hash = result_hashes.get("proposal_sha256") if isinstance(result_hashes, dict) else None
    if bound_hash != proposal_canonical_sha256:
        raise Phase8HumanReferenceComparisonError("PROPOSAL_RECEIPT_HASH_MISMATCH")

    return (
        estimate_id,
        defect_reference,
        {
            "controller_receipt": {
                "path": str(receipt_path.resolve()),
                "sha256": receipt_sha256,
                "run_id": receipt["run_id"],
                "proposal_canonical_json_binding": "VERIFIED",
            },
            "proposal": {
                "path": str(proposal_path.resolve()),
                "sha256": proposal_sha256,
                "canonical_json_sha256": proposal_canonical_sha256,
            },
        },
    )


def _expected_substrate_supported(expected: object, actual: dict[str, Any]) -> bool:
    if expected is None:
        return True
    target = _normalise_text(expected)
    combined = " ".join(
        _normalise_text(actual.get(key))
        for key in ("substrate_type", "substrate_plane", "orientation", "notes")
    )
    if target == "concrete slab":
        return "concrete" in combined and any(
            word in combined for word in ("slab", "floor", "soffit", "horizontal")
        )
    if target == "concrete wall":
        return "concrete" in combined and any(word in combined for word in ("wall", "vertical"))
    if target == "block wall":
        return any(word in combined for word in ("block", "masonry", "concrete block")) and any(
            word in combined for word in ("wall", "vertical")
        )
    return bool(target) and all(token in combined for token in target.split())


def _matched_expected_indices(adjacency: list[list[int]]) -> set[int]:
    matched_expected_by_candidate: dict[int, int] = {}

    def assign(expected_index: int, seen: set[int]) -> bool:
        for candidate_index in adjacency[expected_index]:
            if candidate_index in seen:
                continue
            seen.add(candidate_index)
            previous = matched_expected_by_candidate.get(candidate_index)
            if previous is None or assign(previous, seen):
                matched_expected_by_candidate[candidate_index] = expected_index
                return True
        return False

    for expected_index in range(len(adjacency)):
        assign(expected_index, set())
    return set(matched_expected_by_candidate.values())


def _substrate_observations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "opening_code": row.get("opening_code"),
            "substrate_type": row.get("substrate_type"),
            "substrate_plane": row.get("substrate_plane"),
            "orientation": row.get("orientation"),
        }
        for row in rows
    ]


def _substrate_pairing_issues(
    expected_openings: list[dict[str, Any]],
    candidate_openings: list[dict[str, Any]],
) -> list[str]:
    """Match substrate expectations only within the same opening topology."""

    candidate_by_signature: dict[_OpeningSignature, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidate_openings:
        candidate_by_signature[_opening_signature(candidate)].append(candidate)

    expected_by_signature: dict[_OpeningSignature, list[dict[str, Any]]] = defaultdict(list)
    for expected in expected_openings:
        if expected.get("substrate") is not None:
            expected_by_signature[_opening_signature(expected)].append(expected)

    issues: list[str] = []
    for signature, expected_rows in expected_by_signature.items():
        candidates = candidate_by_signature.get(signature, [])
        adjacency = [
            [
                index
                for index, candidate in enumerate(candidates)
                if _expected_substrate_supported(expected.get("substrate"), candidate)
            ]
            for expected in expected_rows
        ]
        matched_expected = _matched_expected_indices(adjacency)
        for expected_index, expected in enumerate(expected_rows):
            if expected_index not in matched_expected:
                issues.append(
                    "no candidate opening supports expected "
                    f"substrate {expected.get('substrate')!r} within matching service "
                    f"topology {signature!r}; matching-topology observations "
                    f"{_substrate_observations(candidates)!r}; all observations "
                    f"{_substrate_observations(candidate_openings)!r}"
                )
    return issues


def compare_phase8_human_reference(
    *,
    proposal_path: Path,
    controller_receipt_path: Path,
    reference_path: Path,
) -> dict[str, Any]:
    """Compare one completed proposal with one validation-only reference row."""

    proposal, proposal_sha256 = _read_json_object(proposal_path, label="proposal")
    controller_receipt, controller_receipt_sha256 = _read_json_object(
        controller_receipt_path,
        label="controller receipt",
    )
    estimate_id, defect_reference, bindings = _controller_context(
        receipt=controller_receipt,
        receipt_path=controller_receipt_path,
        receipt_sha256=controller_receipt_sha256,
        proposal=proposal,
        proposal_path=proposal_path,
        proposal_sha256=proposal_sha256,
    )
    candidate_openings = _proposal_openings(
        proposal,
        defect_reference=defect_reference,
    )
    reference, reference_by_external, reference_sha256 = _load_reference(reference_path)
    expected = reference_by_external.get(defect_reference)

    issues: list[str] = []
    expected_openings: list[dict[str, Any]] = []
    expected_opening_count: int | None = None
    if expected is None:
        issues.append("controller defect_reference is absent from the human reference")
    else:
        expected_openings = expected["openings"]
        expected_opening_count = expected["opening_count"]
        if len(candidate_openings) != expected_opening_count:
            issues.append(
                f"opening_count expected {expected_opening_count} got {len(candidate_openings)}"
            )
        expected_signatures = Counter(_opening_signature(row) for row in expected_openings)
        candidate_signatures = Counter(_opening_signature(row) for row in candidate_openings)
        if expected_signatures != candidate_signatures:
            issues.append(
                "opening/service-group topology differs: expected "
                + json.dumps(
                    {str(key): value for key, value in expected_signatures.items()},
                    sort_keys=True,
                )
                + " candidate "
                + json.dumps(
                    {str(key): value for key, value in candidate_signatures.items()},
                    sort_keys=True,
                )
            )
        issues.extend(
            _substrate_pairing_issues(
                expected_openings,
                candidate_openings,
            )
        )

    status = "PASS" if not issues else "MISMATCH"
    return {
        "schema": HUMAN_COMPARISON_SCHEMA,
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "run_id": controller_receipt["run_id"],
        "estimate_id": estimate_id,
        "defect_reference": defect_reference,
        "implementation_revision": controller_receipt["implementation_revision"],
        "input_bindings": {
            **bindings,
            "human_reference": {
                "path": str(reference_path.resolve()),
                "sha256": reference_sha256,
                "schema": HUMAN_REFERENCE_SCHEMA,
                "run_id": reference["run_id"],
                "purpose": HUMAN_REFERENCE_PURPOSE,
            },
        },
        "human_reference_visible_to_inference": False,
        "canonical_database_read_performed": False,
        "canonical_write_performed": False,
        "physical_model_lock_created": False,
        "reference_defect_count": len(reference_by_external),
        "defect_count": 1,
        "passed_defect_count": 1 if status == "PASS" else 0,
        "mismatch_defect_count": 0 if status == "PASS" else 1,
        "defects": [
            {
                "external_defect_id": defect_reference,
                "status": status,
                "expected_opening_count": expected_opening_count,
                "actual_opening_count": len(candidate_openings),
                "issues": issues,
                "candidate_openings": candidate_openings,
            }
        ],
        "comparator_sha256": _sha256(Path(__file__).read_bytes()),
    }


__all__ = [
    "HUMAN_COMPARISON_SCHEMA",
    "HUMAN_REFERENCE_PURPOSE",
    "HUMAN_REFERENCE_SCHEMA",
    "Phase8HumanReferenceComparisonError",
    "compare_phase8_human_reference",
    "validate_phase8_human_reference",
]
