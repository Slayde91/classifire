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
# The fix is field-aware deterministic projection, not repeated increases to this
# threshold and not an AI-to-AI reduction pass.
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
    for raw in value[:max_items]:
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
        if row:
            result.append(row)
    return result


def _project_strings(value: object, *, max_items: int, string_limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value[:max_items]:
        text = _trim_text(item, string_limit)
        if text and text not in result:
            result.append(text)
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
        "region": _trim_text(row.get("region"), 180),
    }

    if evidence_type == "defect_text_fact_review":
        base.update(
            {
                "association_status": row.get("association_status"),
                "attributes": _project_dict_list(
                    row.get("attributes"),
                    keys=("name", "value", "status", "source_role", "basis"),
                    max_items=max(list_limit + 3, 7),
                    string_limit=string_limit,
                    list_limit=list_limit,
                ),
                "quantities": _project_dict_list(
                    row.get("quantities"),
                    keys=("kind", "value", "unit", "status", "source_role", "basis"),
                    max_items=max(list_limit + 1, 5),
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
                        "basis",
                    ),
                    max_items=max(list_limit + 3, 7),
                    string_limit=string_limit,
                    list_limit=list_limit,
                ),
                # Treatment clues are deliberately omitted here. They are retained
                # canonically for the later technical-system stage but are not needed
                # to establish the physical Opening/Service model.
                "technical_details": _project_strings(
                    row.get("technical_details"),
                    max_items=list_limit,
                    string_limit=string_limit,
                ),
                "physical_facts": _project_strings(
                    row.get("physical_facts"),
                    max_items=list_limit + 2,
                    string_limit=string_limit,
                ),
                "uncertainties": _project_strings(
                    row.get("uncertainties"),
                    max_items=list_limit + 2,
                    string_limit=string_limit,
                ),
            }
        )
        return {key: value for key, value in base.items() if value not in (None, "", [], {})}

    if evidence_type == "defect_photo_reconciliation":
        base.update(
            {
                "status": row.get("status"),
                "opening_count": _clip(
                    row.get("opening_count"), string_limit=string_limit, list_limit=list_limit
                ),
                "service_count": _clip(
                    row.get("service_count"), string_limit=string_limit, list_limit=list_limit
                ),
                "counting_decisions": _clip(
                    row.get("counting_decisions"),
                    string_limit=string_limit,
                    list_limit=list_limit,
                ),
                "openings": _clip(
                    row.get("openings"), string_limit=string_limit, list_limit=list_limit
                ),
                "services": _clip(
                    row.get("services"), string_limit=string_limit, list_limit=list_limit
                ),
                "relationships": _clip(
                    row.get("relationships"), string_limit=string_limit, list_limit=list_limit
                ),
                "physical_facts": _project_strings(
                    row.get("physical_facts"),
                    max_items=list_limit + 2,
                    string_limit=string_limit,
                ),
                "uncertainties": _project_strings(
                    row.get("uncertainties"),
                    max_items=list_limit + 2,
                    string_limit=string_limit,
                ),
            }
        )
        return {key: value for key, value in base.items() if value not in (None, "", [], {})}

    if evidence_type == "defect_page_layout_review":
        for key in (
            "association_status",
            "association_confidence",
            "opening_count",
            "service_count",
            "openings",
            "services",
            "relationships",
        ):
            value = row.get(key)
            if value not in (None, "", [], {}):
                base[key] = _clip(value, string_limit=string_limit, list_limit=list_limit)
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
            "visible_services",
            "visible_openings",
        ):
            value = row.get(key)
            if value not in (None, "", [], {}):
                base[key] = _clip(value, string_limit=string_limit, list_limit=list_limit)
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
            "association_basis",
            "associated_photo_ids",
            "uncertain_photo_ids",
        ):
            value = row.get(key)
            if value not in (None, "", [], {}):
                base[key] = _clip(value, string_limit=string_limit, list_limit=list_limit)
        base["physical_facts"] = _project_strings(
            row.get("physical_facts"), max_items=list_limit + 1, string_limit=string_limit
        )
        base["uncertainties"] = _project_strings(
            row.get("uncertainties"), max_items=list_limit + 1, string_limit=string_limit
        )
        return {key: value for key, value in base.items() if value not in (None, "", [], {})}

    # Retain only the compact physical fields for lower-priority direct records.
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

    # The profiles reduce representational detail only. Evidence source order,
    # direct defect linkage, counts, service/opening facts and uncertainty remain.
    profiles = (
        (150, 7, 14),
        (120, 6, 12),
        (95, 5, 10),
        (75, 4, 8),
    )
    last_text = ""
    for string_limit, list_limit, row_limit in profiles:
        payload = {
            "defect": _clip(
                defect_payload,
                string_limit=max(string_limit, 260),
                list_limit=list_limit,
            ),
            "direct_evidence": [
                _project_evidence_row(
                    row,
                    string_limit=string_limit,
                    list_limit=list_limit,
                )
                for row in ranked[:row_limit]
            ],
            "rules": {
                "same_page_is_not_association": True,
                "photo_count_is_not_quantity": True,
                "exact_duplicate_visuals_count_once": True,
                "best_estimate_unknown_size_quantity_when_rational": True,
                "technical_selection_deferred": True,
                "pricing_deferred": True,
            },
        }
        last_text = json.dumps(
            payload,
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
            "field-aware deterministic evidence projection and a 12,000-character "
            "per-defect evidence budget."
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
