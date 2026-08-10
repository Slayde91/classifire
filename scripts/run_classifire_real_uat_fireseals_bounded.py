from __future__ import annotations

import argparse
import hashlib
import json
import sys
from typing import Any

from classifire.canonical_models import Defect, EvidenceSource
from run_classifire_real_uat_deterministic import _json_from_payload
from run_classifire_real_uat_fireseals import (
    EVIDENCE_PRIORITY,
    FireSealFocusedController,
    _dedupe_ranked_rows,
    _trim_text,
)
from run_classifire_real_uat_intake import load_receipt, repo_root


# Keep the evidence portion comfortably below the Windows command-line budget.
# The fix is deterministic physical-fact projection and consolidation, not repeated
# increases to this threshold and not an AI reduction pass.
BOUNDED_DEFECT_EVIDENCE_CHARS = 12_000


def _clip(value: object, *, string_limit: int, list_limit: int, depth: int = 0) -> object:
    if value is None:
        return None
    if isinstance(value, str):
        return _trim_text(value, string_limit)
    if isinstance(value, (int, float, bool)):
        return value
    if depth >= 4:
        return _trim_text(value, string_limit)
    if isinstance(value, list):
        return [
            _clip(item, string_limit=string_limit, list_limit=list_limit, depth=depth + 1)
            for item in value[:list_limit]
        ]
    if isinstance(value, dict):
        return {
            str(key): _clip(
                item,
                string_limit=string_limit,
                list_limit=list_limit,
                depth=depth + 1,
            )
            for key, item in value.items()
            if item not in (None, "", [], {})
        }
    return _trim_text(value, string_limit)


def _stable_key(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _project_dict_list(
    value: object,
    *,
    keys: tuple[str, ...],
    max_items: int,
    string_limit: int,
    list_limit: int,
) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw in value:
        if len(result) >= max_items:
            break
        if not isinstance(raw, dict):
            continue
        row = {
            key: _clip(
                raw.get(key),
                string_limit=string_limit,
                list_limit=list_limit,
            )
            for key in keys
            if raw.get(key) not in (None, "", [], {})
        }
        if not row:
            continue
        identity = _stable_key(row)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(row)
    return result


def _project_strings(value: object, *, max_items: int, string_limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if len(result) >= max_items:
            break
        text = _trim_text(item, string_limit)
        if text and text not in result:
            result.append(text)
    return result


def _project_count(value: object, *, string_limit: int, list_limit: int) -> object:
    if not isinstance(value, dict):
        return _clip(value, string_limit=string_limit, list_limit=list_limit)
    result = {
        key: _clip(value.get(key), string_limit=string_limit, list_limit=list_limit)
        for key in ("value", "status")
        if value.get(key) not in (None, "", [], {})
    }
    basis = _project_strings(
        value.get("basis"),
        max_items=min(list_limit, 3),
        string_limit=string_limit,
    )
    if basis:
        result["basis"] = basis
    return result


def _project_evidence_row(
    row: dict[str, Any],
    *,
    string_limit: int,
    list_limit: int,
) -> dict[str, object]:
    evidence_type = str(row.get("type") or "")
    base: dict[str, object] = {
        "type": evidence_type,
        "page": row.get("page"),
        "region": _trim_text(row.get("region"), 120),
    }

    if evidence_type == "defect_text_fact_review":
        base.update(
            {
                "association_status": row.get("association_status"),
                # The physical-model prompt needs the asserted value and epistemic
                # status. Repeated prose bases remain in canonical evidence and are
                # intentionally omitted from this inference projection.
                "attributes": _project_dict_list(
                    row.get("attributes"),
                    keys=("name", "value", "status", "source_role"),
                    max_items=max(list_limit + 1, 4),
                    string_limit=string_limit,
                    list_limit=list_limit,
                ),
                "quantities": _project_dict_list(
                    row.get("quantities"),
                    keys=("kind", "value", "unit", "status", "source_role"),
                    max_items=max(list_limit, 3),
                    string_limit=string_limit,
                    list_limit=list_limit,
                ),
                "services": _project_dict_list(
                    row.get("services"),
                    keys=(
                        "label",
                        "service_type",
                        "material",
                        "size",
                        "quantity",
                        "status",
                        "source_role",
                    ),
                    max_items=max(list_limit + 2, 5),
                    string_limit=string_limit,
                    list_limit=list_limit,
                ),
                "physical_facts": _project_strings(
                    row.get("physical_facts"),
                    max_items=list_limit + 1,
                    string_limit=string_limit,
                ),
                "uncertainties": _project_strings(
                    row.get("uncertainties"),
                    max_items=list_limit + 1,
                    string_limit=string_limit,
                ),
            }
        )
        return {key: value for key, value in base.items() if value not in (None, "", [], {})}

    if evidence_type == "defect_photo_reconciliation":
        base.update(
            {
                "status": row.get("status"),
                "opening_count": _project_count(
                    row.get("opening_count"),
                    string_limit=string_limit,
                    list_limit=list_limit,
                ),
                "service_count": _project_count(
                    row.get("service_count"),
                    string_limit=string_limit,
                    list_limit=list_limit,
                ),
                "openings": _project_dict_list(
                    row.get("openings"),
                    keys=(
                        "label",
                        "substrate_type",
                        "substrate_plane",
                        "opening_type",
                        "dimensions",
                        "evidence_status",
                        "source_region",
                    ),
                    max_items=max(list_limit, 3),
                    string_limit=string_limit,
                    list_limit=list_limit,
                ),
                "services": _project_dict_list(
                    row.get("services"),
                    keys=(
                        "label",
                        "service_type",
                        "material",
                        "size",
                        "quantity",
                        "evidence_status",
                    ),
                    max_items=max(list_limit + 2, 5),
                    string_limit=string_limit,
                    list_limit=list_limit,
                ),
                "relationships": _project_strings(
                    row.get("relationships"),
                    max_items=list_limit + 1,
                    string_limit=string_limit,
                ),
                "physical_facts": _project_strings(
                    row.get("physical_facts"),
                    max_items=list_limit + 1,
                    string_limit=string_limit,
                ),
                "uncertainties": _project_strings(
                    row.get("uncertainties"),
                    max_items=list_limit + 1,
                    string_limit=string_limit,
                ),
            }
        )
        return {key: value for key, value in base.items() if value not in (None, "", [], {})}

    if evidence_type == "defect_page_layout_review":
        base["association_status"] = row.get("association_status")
        base["association_confidence"] = row.get("association_confidence")
        base["opening_count"] = _project_count(
            row.get("opening_count"), string_limit=string_limit, list_limit=list_limit
        )
        base["service_count"] = _project_count(
            row.get("service_count"), string_limit=string_limit, list_limit=list_limit
        )
        base["openings"] = _project_dict_list(
            row.get("openings"),
            keys=(
                "label",
                "substrate_type",
                "substrate_plane",
                "opening_type",
                "dimensions",
                "evidence_status",
                "source_region",
            ),
            max_items=max(list_limit, 3),
            string_limit=string_limit,
            list_limit=list_limit,
        )
        base["services"] = _project_dict_list(
            row.get("services"),
            keys=(
                "label",
                "service_type",
                "material",
                "size",
                "quantity",
                "evidence_status",
                "source_region",
            ),
            max_items=max(list_limit + 2, 5),
            string_limit=string_limit,
            list_limit=list_limit,
        )
        base["relationships"] = _project_strings(
            row.get("relationships"), max_items=list_limit + 1, string_limit=string_limit
        )
        base["physical_facts"] = _project_strings(
            row.get("physical_facts"), max_items=list_limit + 1, string_limit=string_limit
        )
        base["uncertainties"] = _project_strings(
            row.get("uncertainties"), max_items=list_limit + 1, string_limit=string_limit
        )
        return {key: value for key, value in base.items() if value not in (None, "", [], {})}

    if evidence_type == "defect_photo_detail_review":
        for key in (
            "photo_id",
            "scope_relevance",
            "target_link",
            "viewpoint",
            "barrier_face",
        ):
            value = row.get(key)
            if value not in (None, "", [], {}):
                base[key] = _clip(value, string_limit=string_limit, list_limit=list_limit)
        base["visible_services"] = _project_dict_list(
            row.get("visible_services"),
            keys=("label", "service_type", "material", "size", "quantity", "status"),
            max_items=max(list_limit + 2, 5),
            string_limit=string_limit,
            list_limit=list_limit,
        )
        base["visible_openings"] = _project_dict_list(
            row.get("visible_openings"),
            keys=("label", "substrate_type", "substrate_plane", "opening_type", "dimensions"),
            max_items=max(list_limit, 3),
            string_limit=string_limit,
            list_limit=list_limit,
        )
        base["physical_facts"] = _project_strings(
            row.get("physical_facts"), max_items=list_limit + 1, string_limit=string_limit
        )
        base["uncertainties"] = _project_strings(
            row.get("uncertainties"), max_items=list_limit + 1, string_limit=string_limit
        )
        return {key: value for key, value in base.items() if value not in (None, "", [], {})}

    if evidence_type == "defect_page_photo_linkage_review":
        for key in (
            "association_status",
            "association_confidence",
        ):
            value = row.get(key)
            if value not in (None, "", [], {}):
                base[key] = value
        base["associated_photo_ids"] = _project_strings(
            row.get("associated_photo_ids"), max_items=list_limit + 1, string_limit=80
        )
        base["uncertain_photo_ids"] = _project_strings(
            row.get("uncertain_photo_ids"), max_items=list_limit + 1, string_limit=80
        )
        base["physical_facts"] = _project_strings(
            row.get("physical_facts"), max_items=list_limit + 1, string_limit=string_limit
        )
        base["uncertainties"] = _project_strings(
            row.get("uncertainties"), max_items=list_limit + 1, string_limit=string_limit
        )
        return {key: value for key, value in base.items() if value not in (None, "", [], {})}

    # Retain only compact physical fields for lower-priority direct records.
    for key in (
        "description",
        "location",
        "classification",
        "evidence_class",
        "confidence",
        "summary",
    ):
        value = row.get(key)
        if value not in (None, "", [], {}):
            base[key] = _clip(value, string_limit=string_limit, list_limit=list_limit)
    base["physical_facts"] = _project_strings(
        row.get("physical_facts"), max_items=list_limit, string_limit=string_limit
    )
    base["uncertainties"] = _project_strings(
        row.get("uncertainties"), max_items=list_limit, string_limit=string_limit
    )
    return {key: value for key, value in base.items() if value not in (None, "", [], {})}


def _consolidate_projected_rows(
    rows: list[dict[str, object]],
    *,
    provenance_limit: int,
) -> list[dict[str, object]]:
    """Collapse repeated physical content while retaining occurrence provenance."""

    groups: dict[str, dict[str, object]] = {}
    order: list[str] = []
    for row in rows:
        core = {key: value for key, value in row.items() if key not in {"page", "region"}}
        identity = _stable_key(core)
        provenance = {
            key: row.get(key)
            for key in ("page", "region")
            if row.get(key) not in (None, "")
        }
        if identity not in groups:
            groups[identity] = {**core, "provenance": []}
            order.append(identity)
        provenance_rows = groups[identity]["provenance"]
        if (
            provenance
            and isinstance(provenance_rows, list)
            and provenance not in provenance_rows
            and len(provenance_rows) < provenance_limit
        ):
            provenance_rows.append(provenance)

    result: list[dict[str, object]] = []
    for identity in order:
        row = groups[identity]
        if row.get("provenance") == []:
            row = {key: value for key, value in row.items() if key != "provenance"}
        result.append(row)
    return result


def _bundle_rules() -> dict[str, bool]:
    return {
        "same_page_is_not_association": True,
        "photo_count_is_not_quantity": True,
        "exact_duplicate_visuals_count_once": True,
        "best_estimate_unknown_size_quantity_when_rational": True,
        "technical_selection_deferred": True,
        "pricing_deferred": True,
    }


def _serialize_bundle(
    defect_payload: dict[str, Any],
    direct_evidence: list[dict[str, object]],
    *,
    defect_string_limit: int,
    defect_list_limit: int,
) -> str:
    return json.dumps(
        {
            "defect": _clip(
                defect_payload,
                string_limit=defect_string_limit,
                list_limit=defect_list_limit,
            ),
            "direct_evidence": direct_evidence,
            "rules": _bundle_rules(),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def _append_unique(target: list[object], value: object, *, limit: int) -> None:
    if value in (None, "", [], {}) or len(target) >= limit:
        return
    identity = _stable_key(value)
    if any(_stable_key(item) == identity for item in target):
        return
    target.append(value)


def _essential_summary(
    ranked: list[dict[str, Any]],
    *,
    string_limit: int,
    list_limit: int,
) -> dict[str, object]:
    """Final deterministic projection of only physical-model-relevant evidence."""

    summary: dict[str, list[object]] = {
        "provenance": [],
        "attributes": [],
        "quantities": [],
        "services": [],
        "openings": [],
        "opening_counts": [],
        "service_counts": [],
        "relationships": [],
        "physical_facts": [],
        "uncertainties": [],
    }

    for raw in ranked:
        projected = _project_evidence_row(
            raw,
            string_limit=string_limit,
            list_limit=list_limit,
        )
        _append_unique(
            summary["provenance"],
            {
                key: projected.get(key)
                for key in ("type", "page", "region")
                if projected.get(key) not in (None, "", [], {})
            },
            limit=max(list_limit * 2, 6),
        )
        for key, max_items in (
            ("attributes", max(list_limit * 2, 6)),
            ("quantities", max(list_limit * 2, 6)),
            ("services", max(list_limit * 3, 8)),
            ("openings", max(list_limit * 2, 5)),
            ("relationships", max(list_limit * 2, 6)),
            ("physical_facts", max(list_limit * 2, 8)),
            ("uncertainties", max(list_limit * 2, 8)),
        ):
            value = projected.get(key)
            if isinstance(value, list):
                for item in value:
                    _append_unique(summary[key], item, limit=max_items)
        if projected.get("opening_count") not in (None, "", [], {}):
            _append_unique(
                summary["opening_counts"],
                projected["opening_count"],
                limit=max(list_limit, 3),
            )
        if projected.get("service_count") not in (None, "", [], {}):
            _append_unique(
                summary["service_counts"],
                projected["service_count"],
                limit=max(list_limit, 3),
            )

    return {
        key: values
        for key, values in summary.items()
        if values
    }


def build_projected_defect_bundle(
    defect_payload: dict[str, Any],
    evidence_rows: list[dict[str, Any]],
    *,
    max_chars: int = BOUNDED_DEFECT_EVIDENCE_CHARS,
) -> str:
    allowed = [
        row for row in evidence_rows if str(row.get("type") or "") in EVIDENCE_PRIORITY
    ]
    ranked = _dedupe_ranked_rows(allowed)

    # First preserve evidence-row structure but collapse repeated content into one
    # row with bounded page/region provenance. This is important for reports that
    # repeat the same defect facts in several extraction/reconciliation records.
    profiles = (
        (150, 7, 14, 6),
        (110, 6, 12, 5),
        (85, 5, 10, 4),
        (65, 4, 8, 3),
    )
    last_text = ""
    for string_limit, list_limit, row_limit, provenance_limit in profiles:
        projected = [
            _project_evidence_row(
                row,
                string_limit=string_limit,
                list_limit=list_limit,
            )
            for row in ranked
        ]
        consolidated = _consolidate_projected_rows(
            projected,
            provenance_limit=provenance_limit,
        )
        last_text = _serialize_bundle(
            defect_payload,
            consolidated[:row_limit],
            defect_string_limit=max(string_limit, 240),
            defect_list_limit=list_limit,
        )
        if len(last_text) <= max_chars:
            return last_text

    # If a defect genuinely has many unique direct evidence records, switch to an
    # aggregate physical-fact summary. Canonical evidence is not deleted; only the
    # inference payload representation changes. No model-to-model summarisation is used.
    for string_limit, list_limit in ((60, 4), (45, 3), (36, 2)):
        summary = _essential_summary(
            ranked,
            string_limit=string_limit,
            list_limit=list_limit,
        )
        last_text = json.dumps(
            {
                "defect": _clip(
                    defect_payload,
                    string_limit=220,
                    list_limit=max(list_limit, 2),
                ),
                "evidence_summary": summary,
                "rules": _bundle_rules(),
            },
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        if len(last_text) <= max_chars:
            return last_text

    raise RuntimeError(
        "Projected direct evidence for one fire-seal defect still exceeds the "
        f"Windows-safe payload ({len(last_text)} > {max_chars} characters). "
        "No model was submitted and no AI reduction pass was used."
    )


def _supported_scope_present(model: dict) -> bool:
    if str(model.get("status") or "").strip().upper() != "MODEL_SUPPORTED":
        return False
    openings = model.get("openings")
    services = model.get("services")
    return (
        isinstance(openings, list)
        and isinstance(services, list)
        and len(openings) > 0
        and len(services) > 0
    )


class BoundedFireSealFocusedController(FireSealFocusedController):
    """Resume fire-seal UAT with projected, bounded direct evidence."""

    def _bundle_for_defect(
        self,
        defect: Defect,
        all_evidence: list[EvidenceSource],
    ) -> str:
        direct = [item for item in all_evidence if item.defect_id == defect.id]
        compact_rows = [self._compact_evidence_row(item) for item in direct]
        defect_payload = {
            "canonical_defect_id": defect.id,
            "external_defect_id": defect.external_defect_id,
            "defect_code": defect.defect_code,
            "description": _trim_text(defect.description, 900),
            "location": _trim_text(defect.location, 500),
            "classification": defect.classification,
            "evidence_status": defect.evidence_status,
        }
        bundle = build_projected_defect_bundle(
            defect_payload,
            compact_rows,
            max_chars=BOUNDED_DEFECT_EVIDENCE_CHARS,
        )
        if len(bundle) > BOUNDED_DEFECT_EVIDENCE_CHARS:
            raise RuntimeError(
                "Projected fire-seal evidence exceeded its prompt budget. No model was submitted."
            )
        return bundle

    def _cached_supported_model(
        self,
        defect_index: int,
        defect: Defect,
        bundle: str,
    ) -> dict | None:
        # Reject the earlier invalid cache state where the model claimed support
        # but returned no openings/services.
        cached = super()._cached_supported_model(defect_index, defect, bundle)
        if cached is not None and _supported_scope_present(cached):
            return cached

        bundle_hash = hashlib.sha256(bundle.encode("utf-8")).hexdigest()
        metadata_path = self.receipt_dir / f"20-fireseal-defect-{defect_index:03d}-cache.json"
        repair_path = self.receipt_dir / f"20-fireseal-defect-{defect_index:03d}-scope-repair.json"
        if not metadata_path.is_file() or not repair_path.is_file():
            return None
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            repair_payload = json.loads(repair_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if metadata.get("bundle_sha256") != bundle_hash:
            return None
        if metadata.get("canonical_defect_id") != defect.id:
            return None
        repaired = _json_from_payload(
            repair_payload,
            context="Cached fire-seal scope-repair synthesis",
        )
        return repaired if _supported_scope_present(repaired) else None

    def _scope_repair_prompt(self, defect: Defect, bundle: str, first_model: dict) -> str:
        return self.defect_physical_prompt(defect, bundle) + f"""

The previous response was internally invalid: it claimed MODEL_SUPPORTED but returned
no complete physical Opening/Service scope.
Previous response summary:
{json.dumps(first_model, ensure_ascii=False, separators=(",", ":"), default=str)[:1600]}

Re-evaluate the direct evidence independently. If a rational fire-seal/service-
penetration physical model is supported, return MODEL_SUPPORTED with at least one
Opening and every distinct supported or provisionally estimated Service linked to
its Opening. Estimate unknown size or quantity only where the evidence gives a
rational basis and label it provisional/inferred. If no rational physical scope can
be established, return INSUFFICIENT_EVIDENCE with specific limitations. Never
return MODEL_SUPPORTED with empty openings or services.
"""

    def _synthesise_defect(
        self,
        defect_index: int,
        defect: Defect,
        bundle: str,
    ) -> dict:
        model = super()._synthesise_defect(defect_index, defect, bundle)
        status = str(model.get("status") or "").strip().upper()
        if status != "MODEL_SUPPORTED" or _supported_scope_present(model):
            return model

        payload = self.infer_model(
            prompt=self._scope_repair_prompt(defect, bundle, model),
            receipt_name=f"20-fireseal-defect-{defect_index:03d}-scope-repair",
            thinking="high",
        )
        repaired = _json_from_payload(
            payload,
            context=(
                "Fire-seal scope-repair synthesis for defect "
                f"{defect.external_defect_id or defect.id}"
            ),
        )
        return repaired


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Resume the retained CLASSIFIRE real-report fire-seal UAT using "
            "consolidated deterministic physical-evidence projection and a "
            "12,000-character per-defect evidence budget."
        )
    )
    parser.add_argument("--run-id")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()

    root = repo_root()
    _receipt_path, receipt = load_receipt(root, args.run_id)
    controller = BoundedFireSealFocusedController(
        receipt,
        base_url=args.base_url,
        timeout_seconds=args.timeout_seconds,
    )
    try:
        state = controller.run()
        return 0 if state.get("status") in {
            "PHYSICAL_MODEL_LOCKED",
            "PARTIAL_SOURCE_OR_PHYSICAL_LIMITATION",
        } else 1
    except Exception as exc:
        print(f"CLASSIFIRE bounded fire-seal real-report UAT failed: {exc}", file=sys.stderr)
        return 1
    finally:
        controller.close()


if __name__ == "__main__":
    raise SystemExit(main())
