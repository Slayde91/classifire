from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select

from classifire.canonical_models import Defect, ServiceOpeningLink
from classifire.db import SessionLocal
from classifire.models import Opening, Service
from classifire.services.physical_scope import is_blank_opening_type


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE = ROOT / "tests" / "fixtures" / "real_uat_20260809_human_physical_reference.json"


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
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


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
        return "concrete" in combined and any(word in combined for word in ("slab", "floor", "soffit", "horizontal"))
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


def _opening_signature(row: dict[str, Any], *, reference: bool) -> tuple[bool, tuple[tuple[str, str | None, str], ...]]:
    groups = row.get("service_groups") or []
    signatures = sorted(_service_signature(item) for item in groups)
    return bool(row.get("blank")), tuple(signatures)


def validate(*, estimate_id: str, reference_path: Path) -> dict[str, Any]:
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    expected_by_id = {str(row["external_defect_id"]): row for row in reference.get("defects") or []}

    with SessionLocal() as db:
        defects = list(db.scalars(select(Defect).where(Defect.estimate_id == estimate_id)).all())
        openings = list(db.scalars(select(Opening).where(Opening.estimate_id == estimate_id)).all())
        opening_ids = [item.id for item in openings]
        links = (
            list(db.scalars(select(ServiceOpeningLink).where(ServiceOpeningLink.opening_id.in_(opening_ids))).all())
            if opening_ids
            else []
        )
        service_ids = sorted({item.service_id for item in links})
        services = (
            list(db.scalars(select(Service).where(Service.id.in_(service_ids))).all()) if service_ids else []
        )

    defect_by_id = {item.id: item for item in defects}
    service_by_id = {item.id: item for item in services}
    links_by_opening: dict[str, list[ServiceOpeningLink]] = defaultdict(list)
    for link in links:
        links_by_opening[link.opening_id].append(link)
    openings_by_external: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for opening in openings:
        defect = defect_by_id.get(opening.canonical_defect_id or "")
        external = str(defect.external_defect_id if defect else opening.defect_id or "")
        openings_by_external[external].append(
            _current_opening_row(opening, links_by_opening.get(opening.id, []), service_by_id)
        )

    rows: list[dict[str, Any]] = []
    overall_pass = True
    for external_id, expected in expected_by_id.items():
        current = openings_by_external.get(external_id, [])
        expected_openings = expected.get("openings") or []
        issues: list[str] = []
        if len(current) != int(expected.get("opening_count") or 0):
            issues.append(f"opening_count expected {expected.get('opening_count')} got {len(current)}")

        expected_sigs = Counter(_opening_signature(row, reference=True) for row in expected_openings)
        current_sigs = Counter(_opening_signature(row, reference=False) for row in current)
        if expected_sigs != current_sigs:
            issues.append(
                "opening/service-group topology differs: expected "
                + json.dumps({str(k): v for k, v in expected_sigs.items()}, default=str)
                + " current "
                + json.dumps({str(k): v for k, v in current_sigs.items()}, default=str)
            )

        unmatched_current = list(current)
        substrate_issues: list[str] = []
        for expected_opening in expected_openings:
            expected_sig = _opening_signature(expected_opening, reference=True)
            match_index = next(
                (
                    index
                    for index, candidate in enumerate(unmatched_current)
                    if _opening_signature(candidate, reference=False) == expected_sig
                ),
                None,
            )
            if match_index is None:
                continue
            candidate = unmatched_current.pop(match_index)
            if not _expected_substrate_supported(expected_opening.get("substrate"), candidate):
                substrate_issues.append(
                    f"{candidate.get('opening_code')} substrate expected {expected_opening.get('substrate')!r}; "
                    f"got type={candidate.get('substrate_type')!r}, plane={candidate.get('substrate_plane')!r}, "
                    f"orientation={candidate.get('orientation')!r}"
                )
        issues.extend(substrate_issues)

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

    return {
        "schema": "CLASSIFIRE-HUMAN-PHYSICAL-REFERENCE-VALIDATION-v1",
        "estimate_id": estimate_id,
        "reference": str(reference_path),
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
    args = parser.parse_args()
    result = validate(estimate_id=args.estimate_id, reference_path=Path(args.reference))
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
