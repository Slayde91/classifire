from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select

from classifire.canonical_models import Defect, ServiceOpeningLink
from classifire.db import SessionLocal
from classifire.models import Opening, Service
from classifire.services.physical_scope import is_blank_opening_type

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE = ROOT / "tests" / "fixtures" / "real_uat_20260809_human_physical_reference.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _read_json_and_sha256(path: Path, *, label: str) -> tuple[Any, str]:
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} must be valid UTF-8 JSON: {path}") from exc
    return payload, hashlib.sha256(raw).hexdigest().upper()


def _norm_text(value: object) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").replace("-", " ").split())


def _norm_type(value: object) -> str:
    text = _norm_text(value)
    aliases = {
        "cable bundle": "cable_bundle",
        "cables": "cable_bundle",
        "cable_bundle": "cable_bundle",
        "flexi duct": "flexible_duct",
        "flex duct": "flexible_duct",
        "flexible duct": "flexible_duct",
        "aircon bundle": "aircon_bundle",
        "air con bundle": "aircon_bundle",
        "air conditioning bundle": "aircon_bundle",
    }
    return aliases.get(text, text.replace(" ", "_"))


def _norm_material(value: object) -> str | None:
    text = _norm_text(value)
    if not text:
        return None
    aliases = {
        "polyvinyl chloride": "pvc",
        "cu": "copper",
        "metallic": "metal",
    }
    return aliases.get(text, text)


def _qty(value: object) -> Decimal:
    try:
        quantity = Decimal(str(value))
    except Exception as exc:
        raise RuntimeError(f"Service quantity must be numeric, got {value!r}.") from exc
    if not quantity.is_finite() or quantity <= 0:
        raise RuntimeError(f"Service quantity must be positive and finite, got {value!r}.")
    return quantity


def _service_signature(row: dict[str, Any]) -> tuple[str, str | None, str]:
    return (
        _norm_type(row.get("type") or row.get("service_type")),
        _norm_material(row.get("material")),
        str(_qty(row.get("quantity")).normalize()),
    )


def _expected_substrate_supported(expected: object, actual: dict[str, Any]) -> bool:
    if expected is None:
        return True
    target = _norm_text(expected)
    combined = " ".join(
        _norm_text(actual.get(key))
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
    return all(token in combined for token in target.split())


def _current_opening_row(
    opening: Opening,
    links: list[ServiceOpeningLink],
    service_by_id: dict[str, Service],
) -> dict[str, Any]:
    groups = []
    for link in links:
        service = service_by_id.get(link.service_id)
        if service is None:
            continue
        groups.append(
            {
                "service_code": service.service_code,
                "service_type": service.service_type,
                "material": service.material,
                "quantity": str(service.quantity),
                "notes": service.notes,
            }
        )
    return {
        "opening_code": opening.opening_code,
        "opening_type": opening.opening_type,
        "blank": is_blank_opening_type(opening.opening_type),
        "substrate_type": opening.substrate_type,
        "substrate_plane": opening.substrate_plane,
        "orientation": opening.orientation,
        "notes": opening.notes,
        "service_groups": groups,
    }


def _proposal_openings_by_external(
    proposal_path: Path,
) -> tuple[dict[str, list[dict[str, Any]]], set[str], str]:
    proposal, proposal_sha256 = _read_json_and_sha256(
        proposal_path,
        label="Proposal",
    )
    if not isinstance(proposal, dict):
        raise RuntimeError("Proposal root must be an object.")

    raw_openings = proposal.get("openings", [])
    raw_services = proposal.get("services", [])
    raw_limitations = proposal.get("limitations", [])

    if not isinstance(raw_openings, list):
        raise RuntimeError("Proposal openings must be a list.")
    if not isinstance(raw_services, list):
        raise RuntimeError("Proposal services must be a list.")
    if not isinstance(raw_limitations, list):
        raise RuntimeError("Proposal limitations must be a list.")

    opening_by_code: dict[str, dict[str, Any]] = {}
    openings_by_external: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)
    external_by_opening_code: dict[str, str] = {}

    for raw_opening in raw_openings:
        if not isinstance(raw_opening, dict):
            raise RuntimeError("Every proposal opening must be an object.")

        raw_opening_code = raw_opening.get("opening_code")
        raw_external_id = raw_opening.get("external_defect_id")
        if not isinstance(raw_opening_code, str) or not raw_opening_code.strip():
            raise RuntimeError("Proposal opening_code must not be blank.")
        if not isinstance(raw_external_id, str) or not raw_external_id.strip():
            raise RuntimeError("Proposal external_defect_id must not be blank.")

        opening_code = raw_opening_code.strip()
        external_id = raw_external_id.strip()
        if opening_code in opening_by_code:
            raise RuntimeError(f"Proposal opening_code values must be unique: {opening_code}")

        opening_type = raw_opening.get("opening_type")
        opening_row = {
            "opening_code": opening_code,
            "opening_type": opening_type,
            "blank": is_blank_opening_type(str(opening_type or "")),
            "substrate_type": raw_opening.get("substrate_type"),
            "substrate_plane": raw_opening.get("substrate_plane"),
            "orientation": raw_opening.get("orientation"),
            "notes": raw_opening.get("notes"),
            "service_groups": [],
        }
        opening_by_code[opening_code] = opening_row
        external_by_opening_code[opening_code] = external_id
        openings_by_external[external_id].append(opening_row)

    seen_service_codes: set[str] = set()

    for raw_service in raw_services:
        if not isinstance(raw_service, dict):
            raise RuntimeError("Every proposal service must be an object.")

        raw_service_code = raw_service.get("service_code")
        if not isinstance(raw_service_code, str) or not raw_service_code.strip():
            raise RuntimeError("Proposal service_code must not be blank.")
        service_code = raw_service_code.strip()
        if service_code in seen_service_codes:
            raise RuntimeError(f"Proposal service_code values must be unique: {service_code}")
        seen_service_codes.add(service_code)

        raw_opening_codes = raw_service.get("opening_codes", [])
        if not isinstance(raw_opening_codes, list):
            raise RuntimeError(f"Proposal service {service_code} opening_codes must be a list.")
        if any(not isinstance(value, str) or not value.strip() for value in raw_opening_codes):
            raise RuntimeError(
                f"Proposal service {service_code} opening_codes must contain nonblank strings."
            )
        opening_codes = [value.strip() for value in raw_opening_codes]
        if len(opening_codes) != len(set(opening_codes)):
            raise RuntimeError(f"Proposal service {service_code} opening_codes must be unique.")

        raw_primary_opening_code = raw_service.get("primary_opening_code")
        if raw_primary_opening_code is not None and not isinstance(
            raw_primary_opening_code,
            str,
        ):
            raise RuntimeError(
                f"Proposal service {service_code} primary_opening_code must be a string."
            )
        primary_opening_code = str(raw_primary_opening_code or "").strip()

        if not primary_opening_code:
            raise RuntimeError(f"Proposal service {service_code} has no primary_opening_code.")
        if not opening_codes:
            raise RuntimeError(f"Proposal service {service_code} has no opening_codes.")
        if primary_opening_code not in opening_codes:
            raise RuntimeError(
                f"Proposal service {service_code} primary_opening_code is not included "
                "in opening_codes."
            )

        unknown_opening_codes = sorted(set(opening_codes) - set(opening_by_code))
        if unknown_opening_codes:
            raise RuntimeError(
                f"Proposal service {service_code} references unknown opening "
                f"{unknown_opening_codes[0]}."
            )
        linked_external_ids = {
            external_by_opening_code[opening_code] for opening_code in opening_codes
        }
        if len(linked_external_ids) != 1:
            raise RuntimeError(
                f"Proposal service {service_code} links openings from multiple defects."
            )

        service_group = {
            "service_code": service_code,
            "service_type": raw_service.get("service_type"),
            "material": raw_service.get("material"),
            "quantity": _qty(raw_service.get("quantity")),
            "notes": raw_service.get("notes"),
        }

        for opening_code in opening_codes:
            opening = opening_by_code[opening_code]
            opening["service_groups"].append(dict(service_group))

    limitation_external_ids: set[str] = set()
    for raw_limitation in raw_limitations:
        if not isinstance(raw_limitation, dict):
            raise RuntimeError("Every proposal limitation must be an object.")
        raw_external_id = raw_limitation.get("external_defect_id")
        if not isinstance(raw_external_id, str) or not raw_external_id.strip():
            raise RuntimeError("Proposal limitation external_defect_id must not be blank.")
        external_id = raw_external_id.strip()
        if external_id in limitation_external_ids:
            raise RuntimeError(
                f"Proposal limitation external_defect_id values must be unique: {external_id}"
            )
        limitation_external_ids.add(external_id)
        limitations = raw_limitation.get("limitations")
        if not isinstance(limitations, list) or any(
            not isinstance(item, str) or not item.strip() for item in limitations
        ):
            raise RuntimeError(
                f"Proposal limitation {external_id} limitations must be a list of nonblank strings."
            )

    supported_external_ids = set(openings_by_external)
    overlap = sorted(supported_external_ids & limitation_external_ids)
    if overlap:
        raise RuntimeError(
            "Proposal defect cannot be both supported and limited: " + ", ".join(overlap)
        )
    declared_external_ids = supported_external_ids | limitation_external_ids

    declared_counts = {
        "defect_count": len(declared_external_ids),
        "supported_defect_count": len(supported_external_ids),
        "limited_defect_count": len(limitation_external_ids),
        "proposed_opening_count": len(raw_openings),
        "proposed_service_count": len(raw_services),
    }
    for field, actual in declared_counts.items():
        if field not in proposal:
            continue
        declared = proposal[field]
        if isinstance(declared, bool) or not isinstance(declared, int):
            raise RuntimeError(f"Proposal {field} must be an integer.")
        if declared != actual:
            raise RuntimeError(
                f"Proposal {field} declares {declared}, but parsed content contains {actual}."
            )

    for opening_code, opening in opening_by_code.items():
        groups = opening["service_groups"]
        if opening["blank"] and groups:
            raise RuntimeError(f"Proposal blank opening {opening_code} cannot have services.")
        if not opening["blank"] and not groups:
            raise RuntimeError(
                f"Proposal nonblank opening {opening_code} must have at least one service."
            )

    return dict(openings_by_external), declared_external_ids, proposal_sha256


def _canonical_openings_by_external(
    estimate_id: str,
) -> dict[str, list[dict[str, Any]]]:
    with SessionLocal() as db:
        defects = list(db.scalars(select(Defect).where(Defect.estimate_id == estimate_id)).all())
        openings = list(db.scalars(select(Opening).where(Opening.estimate_id == estimate_id)).all())
        opening_ids = [item.id for item in openings]
        links = (
            list(
                db.scalars(
                    select(ServiceOpeningLink).where(ServiceOpeningLink.opening_id.in_(opening_ids))
                ).all()
            )
            if opening_ids
            else []
        )
        service_ids = sorted({item.service_id for item in links})
        services = (
            list(db.scalars(select(Service).where(Service.id.in_(service_ids))).all())
            if service_ids
            else []
        )

    defect_by_id = {item.id: item for item in defects}
    service_by_id = {item.id: item for item in services}
    links_by_opening: dict[
        str,
        list[ServiceOpeningLink],
    ] = defaultdict(list)
    for link in links:
        links_by_opening[link.opening_id].append(link)
    openings_by_external: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)
    for opening in openings:
        defect = defect_by_id.get(opening.canonical_defect_id or "")
        external = str(defect.external_defect_id if defect else opening.defect_id or "")
        openings_by_external[external].append(
            _current_opening_row(
                opening,
                links_by_opening.get(opening.id, []),
                service_by_id,
            )
        )

    return dict(openings_by_external)


def _opening_signature(
    row: dict[str, Any],
) -> tuple[bool, tuple[tuple[str, str | None, str], ...]]:
    groups = row.get("service_groups", [])
    if not isinstance(groups, list) or any(not isinstance(item, dict) for item in groups):
        raise RuntimeError("Opening service_groups must be a list of objects.")
    signatures = sorted(_service_signature(item) for item in groups)
    return bool(row.get("blank")), tuple(signatures)


def _load_reference(
    reference_path: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], str]:
    reference, reference_sha256 = _read_json_and_sha256(
        reference_path,
        label="Human reference",
    )
    if not isinstance(reference, dict):
        raise RuntimeError("Human reference root must be an object.")
    raw_defects = reference.get("defects")
    if not isinstance(raw_defects, list):
        raise RuntimeError("Human reference defects must be a list.")

    expected_by_id: dict[str, dict[str, Any]] = {}
    for row in raw_defects:
        if not isinstance(row, dict):
            raise RuntimeError("Every human reference defect must be an object.")
        raw_external_id = row.get("external_defect_id")
        if not isinstance(raw_external_id, str) or not raw_external_id.strip():
            raise RuntimeError("Human reference external_defect_id must not be blank.")
        external_id = raw_external_id.strip()
        if external_id in expected_by_id:
            raise RuntimeError(
                f"Human reference external_defect_id values must be unique: {external_id}"
            )
        openings = row.get("openings")
        if not isinstance(openings, list) or any(
            not isinstance(opening, dict) for opening in openings
        ):
            raise RuntimeError(
                f"Human reference defect {external_id} openings must be a list of objects."
            )
        try:
            expected_count = int(row.get("opening_count"))
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Human reference defect {external_id} opening_count must be an integer."
            ) from exc
        if expected_count != len(openings):
            raise RuntimeError(
                f"Human reference defect {external_id} opening_count is {expected_count}, "
                f"but {len(openings)} openings are listed."
            )
        for opening in openings:
            _opening_signature(opening)
        expected_by_id[external_id] = row

    return reference, expected_by_id, reference_sha256


def _proposal_state_context(
    *,
    proposal_state_path: Path,
    proposal_path: Path,
    proposal_sha256: str,
    estimate_id: str,
    reference_run_id: object,
) -> dict[str, Any]:
    payload, state_sha256 = _read_json_and_sha256(
        proposal_state_path,
        label="Proposal final-state receipt",
    )
    if not isinstance(payload, dict):
        raise RuntimeError("Proposal final-state receipt root must be an object.")
    if payload.get("estimate_id") != estimate_id:
        raise RuntimeError(
            "Proposal final-state receipt estimate_id does not match the requested estimate."
        )

    state_run_id = payload.get("run_id")
    if reference_run_id is not None and state_run_id != reference_run_id:
        raise RuntimeError(
            "Proposal final-state receipt run_id does not match the human reference."
        )

    raw_receipt_path = payload.get("proposal_receipt")
    if not isinstance(raw_receipt_path, str) or not raw_receipt_path.strip():
        raise RuntimeError("Proposal final-state receipt has no proposal_receipt path.")
    bound_proposal_path = Path(raw_receipt_path)
    if not bound_proposal_path.is_absolute():
        bound_proposal_path = proposal_state_path.resolve().parent / bound_proposal_path
    if bound_proposal_path.resolve() != proposal_path.resolve():
        raise RuntimeError(
            "Proposal final-state receipt proposal_receipt does not match the proposal input."
        )

    if payload.get("canonical_write_performed") is not False:
        raise RuntimeError(
            "Proposal final-state receipt does not prove canonical_write_performed=false."
        )
    protected = payload.get("protected_state")
    if not isinstance(protected, dict):
        raise RuntimeError("Proposal final-state receipt has no protected_state object.")
    if protected.get("protected_state_unchanged") is not True:
        raise RuntimeError(
            "Proposal final-state receipt does not prove protected_state_unchanged=true."
        )
    before_fingerprint = protected.get("before_fingerprint")
    after_fingerprint = protected.get("after_fingerprint")
    for label, fingerprint in (
        ("before_fingerprint", before_fingerprint),
        ("after_fingerprint", after_fingerprint),
    ):
        if (
            not isinstance(fingerprint, str)
            or len(fingerprint) != 64
            or any(character not in "0123456789abcdefABCDEF" for character in fingerprint)
        ):
            raise RuntimeError(
                f"Proposal final-state receipt {label} must be a 64-character SHA-256."
            )
    if before_fingerprint.upper() != after_fingerprint.upper():
        raise RuntimeError(
            "Proposal final-state receipt protected-state fingerprints do not match."
        )

    producer_proposal_sha256 = payload.get("proposal_sha256")
    if producer_proposal_sha256 is not None:
        if not isinstance(producer_proposal_sha256, str):
            raise RuntimeError("Proposal final-state receipt proposal_sha256 must be a string.")
        if producer_proposal_sha256.upper() != proposal_sha256:
            raise RuntimeError(
                "Proposal bytes do not match proposal_sha256 in the final-state receipt."
            )

    return {
        "path": str(proposal_state_path.resolve()),
        "sha256": state_sha256,
        "run_id": state_run_id,
        "estimate_id": payload.get("estimate_id"),
        "proposal_path_binding": "VERIFIED",
        "proposal_content_binding": (
            "VERIFIED_SHA256" if producer_proposal_sha256 is not None else "PATH_ONLY"
        ),
    }


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


def _substrate_pairing_issues(
    expected_openings: list[dict[str, Any]],
    current_openings: list[dict[str, Any]],
) -> list[str]:
    """Match substrate expectations only within the same opening topology."""

    current_by_signature: dict[
        tuple[bool, tuple[tuple[str, str | None, str], ...]],
        list[dict[str, Any]],
    ] = defaultdict(list)
    for current in current_openings:
        current_by_signature[_opening_signature(current)].append(current)

    expected_by_signature: dict[
        tuple[bool, tuple[tuple[str, str | None, str], ...]],
        list[dict[str, Any]],
    ] = defaultdict(list)
    for expected in expected_openings:
        if expected.get("substrate") is not None:
            expected_by_signature[_opening_signature(expected)].append(expected)

    issues: list[str] = []
    for signature, expected_rows in expected_by_signature.items():
        candidates = current_by_signature.get(signature, [])
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
            if expected_index in matched_expected:
                continue
            expected_substrate = expected.get("substrate")
            issues.append(
                "no current opening supports expected "
                f"substrate {expected_substrate!r} within matching service topology "
                f"{signature!r}; matching-topology observations "
                f"{_substrate_observations(candidates)!r}; all observations "
                f"{_substrate_observations(current_openings)!r}"
            )

    return issues


def validate(
    *,
    estimate_id: str,
    reference_path: Path,
    proposal_path: Path | None = None,
    proposal_state_path: Path | None = None,
) -> dict[str, Any]:
    if proposal_state_path is not None and proposal_path is None:
        raise RuntimeError("proposal_state_path requires proposal_path.")

    reference, expected_by_id, reference_sha256 = _load_reference(reference_path)
    proposal_sha256: str | None = None
    proposal_state: dict[str, Any] | None = None
    if proposal_path is not None:
        (
            openings_by_external,
            observed_external_ids,
            proposal_sha256,
        ) = _proposal_openings_by_external(proposal_path)
        if proposal_state_path is not None:
            proposal_state = _proposal_state_context(
                proposal_state_path=proposal_state_path,
                proposal_path=proposal_path,
                proposal_sha256=proposal_sha256,
                estimate_id=estimate_id,
                reference_run_id=reference.get("run_id"),
            )
    else:
        openings_by_external = _canonical_openings_by_external(estimate_id)
        observed_external_ids = set(openings_by_external)

    rows: list[dict[str, Any]] = []
    overall_pass = True
    for external_id, expected in expected_by_id.items():
        current = openings_by_external.get(external_id, [])
        expected_openings = expected["openings"]
        issues: list[str] = []
        if len(current) != int(expected.get("opening_count") or 0):
            issues.append(
                f"opening_count expected {expected.get('opening_count')} got {len(current)}"
            )

        expected_sigs = Counter(_opening_signature(row) for row in expected_openings)
        current_sigs = Counter(_opening_signature(row) for row in current)
        if expected_sigs != current_sigs:
            issues.append(
                "opening/service-group topology differs: expected "
                + json.dumps({str(k): v for k, v in expected_sigs.items()}, default=str)
                + " current "
                + json.dumps({str(k): v for k, v in current_sigs.items()}, default=str)
            )

        issues.extend(_substrate_pairing_issues(expected_openings, current))

        passed = not issues
        overall_pass = overall_pass and passed
        rows.append(
            {
                "external_defect_id": external_id,
                "status": "PASS" if passed else "MISMATCH",
                "expected_opening_count": expected.get("opening_count"),
                "actual_opening_count": len(current),
                "issues": issues,
                "current_openings": current,
            }
        )

    unexpected_external_ids = sorted(observed_external_ids - set(expected_by_id))
    for external_id in unexpected_external_ids:
        current = openings_by_external.get(external_id, [])
        overall_pass = False
        rows.append(
            {
                "external_defect_id": external_id,
                "status": "MISMATCH",
                "expected_opening_count": 0,
                "actual_opening_count": len(current),
                "issues": [
                    "proposal or canonical state contains an external defect ID "
                    "that is absent from the human reference"
                ],
                "current_openings": current,
            }
        )

    return {
        "schema": "CLASSIFIRE-HUMAN-PHYSICAL-REFERENCE-VALIDATION-v3",
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "estimate_id": estimate_id,
        "estimate_id_source": (
            "proposal_final_state_receipt"
            if proposal_state is not None
            else "caller_supplied"
            if proposal_path is not None
            else "canonical_query"
        ),
        "reference": str(reference_path.resolve()),
        "reference_sha256": reference_sha256,
        "validator_sha256": _sha256(Path(__file__).resolve()),
        "reference_run_id": reference.get("run_id"),
        "unexpected_external_defect_ids": unexpected_external_ids,
        "comparison_source": (
            {
                "kind": "proposal",
                "path": str(proposal_path.resolve()),
                "sha256": proposal_sha256,
                "final_state_receipt": proposal_state,
            }
            if proposal_path is not None
            else {
                "kind": "canonical_database",
            }
        ),
        "status": "PASS" if overall_pass else "MISMATCH",
        "defect_count": len(rows),
        "passed_defect_count": sum(1 for row in rows if row["status"] == "PASS"),
        "mismatch_defect_count": sum(1 for row in rows if row["status"] != "PASS"),
        "defects": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare a rebuilt real-UAT physical model against the separately retained "
            "human-reviewed topology reference. The reference is validation-only and is "
            "never used by runtime inference."
        )
    )
    parser.add_argument("--estimate-id", required=True)
    parser.add_argument("--reference", default=str(DEFAULT_REFERENCE))
    parser.add_argument(
        "--proposal",
        help=(
            "Compare a proposal JSON receipt instead of canonical "
            "database rows. This mode performs no canonical write."
        ),
    )
    parser.add_argument(
        "--proposal-state",
        help=(
            "Optionally bind proposal mode to its proposal-only final-state receipt, "
            "including estimate, run, path, and protected-state checks."
        ),
    )
    parser.add_argument(
        "--output",
        help="Optionally save the JSON comparison receipt.",
    )
    args = parser.parse_args()
    result = validate(
        estimate_id=args.estimate_id,
        reference_path=Path(args.reference),
        proposal_path=(Path(args.proposal) if args.proposal else None),
        proposal_state_path=(Path(args.proposal_state) if args.proposal_state else None),
    )
    rendered = json.dumps(
        result,
        indent=2,
        default=str,
    )
    if args.output:
        Path(args.output).write_text(
            rendered + "\n",
            encoding="utf-8",
        )
    print(rendered)
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
