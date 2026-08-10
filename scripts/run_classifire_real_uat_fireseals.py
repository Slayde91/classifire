from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import select

from classifire.canonical_models import Defect, EvidenceSource
from classifire.db import SessionLocal
from run_classifire_real_uat_assumptionaware import AssumptionAwareController
from run_classifire_real_uat_deterministic import (
    REQUIRED_PHYSICAL_WRITE_TOOLS,
    _json_from_payload,
)
from run_classifire_real_uat_integrated import TEXT_FACT_EVIDENCE_TYPE
from run_classifire_real_uat_intake import load_receipt, repo_root
from run_classifire_real_uat_photoaware import PHOTO_RECONCILIATION_EVIDENCE_TYPE


MAX_DEFECT_EVIDENCE_CHARS = 9000
MAX_STRING_CHARS = 420
MAX_LIST_ITEMS = 12

# Direct, defect-linked evidence is sufficient after the structured-text, layout,
# full-resolution-photo and photo-reconciliation stages. Generic page/image rows
# are deliberately excluded from physical synthesis to avoid both payload bloat and
# accidental same-page attribution.
EVIDENCE_PRIORITY = {
    TEXT_FACT_EVIDENCE_TYPE: 10,
    PHOTO_RECONCILIATION_EVIDENCE_TYPE: 20,
    "defect_page_layout_review": 30,
    "defect_photo_detail_review": 40,
    "defect_page_photo_linkage_review": 50,
    "defect_report_entry": 60,
    "scope_observation": 70,
}


def _trim_text(value: object, limit: int = MAX_STRING_CHARS) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _bounded(value: object, *, string_limit: int, list_limit: int) -> object:
    if isinstance(value, str):
        return _trim_text(value, string_limit)
    if isinstance(value, list):
        return [
            _bounded(item, string_limit=string_limit, list_limit=list_limit)
            for item in value[:list_limit]
        ]
    if isinstance(value, dict):
        return {
            str(key): _bounded(item, string_limit=string_limit, list_limit=list_limit)
            for key, item in value.items()
            if item not in (None, "", [], {})
        }
    return value


def _photo_visual_group(row: dict[str, Any]) -> str | None:
    if row.get("type") != "defect_photo_detail_review":
        return None
    for feature in row.get("distinctive_features") or []:
        text = str(feature)
        if text.startswith("EXACT_IMAGE_GROUP:"):
            return text.removeprefix("EXACT_IMAGE_GROUP:")
    photo_id = str(row.get("photo_id") or "").strip()
    return f"photo:{photo_id}" if photo_id else None


def _dedupe_ranked_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        rows,
        key=lambda row: (
            EVIDENCE_PRIORITY.get(str(row.get("type") or ""), 999),
            str(row.get("page") or ""),
            str(row.get("region") or ""),
        ),
    )
    seen_json: set[str] = set()
    seen_visuals: set[str] = set()
    result: list[dict[str, Any]] = []
    for row in ranked:
        visual_group = _photo_visual_group(row)
        if visual_group and visual_group in seen_visuals:
            continue
        key = json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)
        if key in seen_json:
            continue
        seen_json.add(key)
        if visual_group:
            seen_visuals.add(visual_group)
        result.append(row)
    return result


def build_bounded_defect_bundle(
    defect_payload: dict[str, Any],
    evidence_rows: list[dict[str, Any]],
    *,
    max_chars: int = MAX_DEFECT_EVIDENCE_CHARS,
) -> str:
    """Build one Windows-safe defect bundle without an AI reduction pass.

    Evidence is selected and compacted deterministically. The function never asks
    a model to summarise a large model prompt into another model prompt, which was
    the source of the previous three-pass reduction failure.
    """

    allowed = [
        row
        for row in evidence_rows
        if str(row.get("type") or "") in EVIDENCE_PRIORITY
    ]
    rows = _dedupe_ranked_rows(allowed)

    # Progressively compact only representation detail. Evidence priority and the
    # distinction between confirmed/inferred/provisional facts are retained.
    profiles = (
        (MAX_STRING_CHARS, MAX_LIST_ITEMS, 24),
        (300, 9, 18),
        (220, 7, 14),
        (150, 5, 10),
    )
    last_text = ""
    for string_limit, list_limit, row_limit in profiles:
        payload = {
            "defect": _bounded(
                defect_payload,
                string_limit=max(string_limit, 300),
                list_limit=list_limit,
            ),
            "direct_evidence": [
                _bounded(row, string_limit=string_limit, list_limit=list_limit)
                for row in rows[:row_limit]
            ],
            "rules": {
                "same_page_is_not_association": True,
                "photo_count_is_not_quantity": True,
                "exact_duplicate_visuals_count_once": True,
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
        "Direct evidence for one fire-seal defect remains larger than the bounded "
        f"Windows-safe payload ({len(last_text)} > {max_chars} characters). "
        "The bundle was not submitted and no AI reduction pass was used."
    )


class FireSealFocusedController(AssumptionAwareController):
    """Resume the current UAT using only penetration/fire-seal physical scope."""

    def _retained_evidence_status(self) -> dict[str, object]:
        with SessionLocal() as db:
            defects = list(
                db.scalars(
                    select(Defect)
                    .where(Defect.estimate_id == self.estimate_id)
                    .order_by(Defect.created_at, Defect.id)
                ).all()
            )
            evidence = list(
                db.scalars(
                    select(EvidenceSource).where(
                        EvidenceSource.estimate_id == self.estimate_id,
                        EvidenceSource.status == "active",
                    )
                ).all()
            )
        by_defect: dict[str, set[str]] = {defect.id: set() for defect in defects}
        for item in evidence:
            if item.defect_id in by_defect:
                by_defect[item.defect_id].add(item.evidence_type)
        text_complete = bool(defects) and all(
            TEXT_FACT_EVIDENCE_TYPE in by_defect[defect.id] for defect in defects
        )
        photo_complete = bool(defects) and all(
            PHOTO_RECONCILIATION_EVIDENCE_TYPE in by_defect[defect.id]
            for defect in defects
        )
        return {
            "defect_count": len(defects),
            "text_complete": text_complete,
            "photo_reconciliation_complete": photo_complete,
            "evidence_type_counts": {
                evidence_type: sum(1 for item in evidence if item.evidence_type == evidence_type)
                for evidence_type in sorted({item.evidence_type for item in evidence})
            },
        }

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
        return build_bounded_defect_bundle(defect_payload, compact_rows)

    def defect_physical_prompt(self, defect: Defect, evidence_text: str) -> str:
        base = super().defect_physical_prompt(defect, evidence_text)
        return base + """

Current fire-seal / penetration UAT precedence clarification:
- This instruction supersedes any earlier prompt sentence that required
  INSUFFICIENT_EVIDENCE merely because photo reconciliation remained uncertain.
- Use explicit defect-linked text first, then defect-linked layout/photo evidence,
  then a clearly labelled provisional AI best estimate when a rational basis exists.
- Do not double-count uncertain photos. Exact duplicate visuals count once.
- Unknown exact size, unknown exact quantity, missing FRL, or an imperfect photo
  association is not by itself a reason to stop when the combined evidence supports
  a defensible provisional Opening and Service model.
- Return INSUFFICIENT_EVIDENCE only when no rational physical estimate can be made
  without inventing the existence, count, barrier plane or relationship of scope.
- This runner is limited to fire seals and service penetrations. Do not create
  structural-steel coating or complete fire-rated duct-run assets in this UAT.
"""

    def _cached_supported_model(
        self,
        defect_index: int,
        defect: Defect,
        bundle: str,
    ) -> dict | None:
        bundle_hash = hashlib.sha256(bundle.encode("utf-8")).hexdigest()
        metadata_path = self.receipt_dir / f"20-fireseal-defect-{defect_index:03d}-cache.json"
        payload_path = self.receipt_dir / f"20-fireseal-defect-{defect_index:03d}-synthesis.json"
        if not metadata_path.is_file() or not payload_path.is_file():
            return None
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if metadata.get("bundle_sha256") != bundle_hash:
            return None
        if metadata.get("canonical_defect_id") != defect.id:
            return None
        model = _json_from_payload(payload, context="Cached fire-seal defect synthesis")
        return model if str(model.get("status") or "").upper() == "MODEL_SUPPORTED" else None

    def _save_cache_metadata(self, defect_index: int, defect: Defect, bundle: str) -> None:
        self.save_json(
            f"20-fireseal-defect-{defect_index:03d}-cache.json",
            {
                "canonical_defect_id": defect.id,
                "external_defect_id": defect.external_defect_id,
                "bundle_sha256": hashlib.sha256(bundle.encode("utf-8")).hexdigest(),
            },
        )

    def _estimation_retry_prompt(
        self,
        defect: Defect,
        bundle: str,
        first_model: dict,
    ) -> str:
        limitations = json.dumps(
            first_model.get("limitations") or [],
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        return self.defect_physical_prompt(defect, bundle) + f"""

The first review returned INSUFFICIENT_EVIDENCE with these limitations:
{limitations}

Perform one independent bounded-estimation review. Recheck whether explicit text,
layout, reconciled photos, visible proportions, service descriptions and plural or
singular wording support a provisional base estimate. Record every estimated size,
quantity or relationship in notes and use provisional/inferred status with reduced
confidence. Do not invent unseen scope. Return INSUFFICIENT_EVIDENCE only if the
physical existence/count/plane/relationship still has no rational basis.
"""

    def _synthesise_defect(
        self,
        defect_index: int,
        defect: Defect,
        bundle: str,
    ) -> dict:
        cached = self._cached_supported_model(defect_index, defect, bundle)
        if cached is not None:
            print(
                f"PASS defect {defect_index} cache -> retained supported physical proposal"
            )
            return cached

        receipt = f"20-fireseal-defect-{defect_index:03d}-synthesis"
        payload = self.infer_model(
            prompt=self.defect_physical_prompt(defect, bundle),
            receipt_name=receipt,
            thinking="high",
        )
        model = _json_from_payload(
            payload,
            context=f"Fire-seal physical synthesis for defect {defect.external_defect_id or defect.id}",
        )
        self._save_cache_metadata(defect_index, defect, bundle)
        if str(model.get("status") or "").strip().upper() != "INSUFFICIENT_EVIDENCE":
            return model

        retry_payload = self.infer_model(
            prompt=self._estimation_retry_prompt(defect, bundle, model),
            receipt_name=f"20-fireseal-defect-{defect_index:03d}-estimate-retry",
            thinking="high",
        )
        return _json_from_payload(
            retry_payload,
            context=f"Fire-seal bounded estimation retry for defect {defect.external_defect_id or defect.id}",
        )

    def run_fireseal_physical(self) -> dict:
        existing = self.inspect_state()
        if existing["physical_lock_count"] > 0:
            print("PASS physical model already locked in retained canonical state")
            return existing
        if existing["opening_count"] or existing["service_count"]:
            raise RuntimeError(
                "Unapproved partial canonical Opening/Service rows already exist. "
                "Do not merge a resumed proposal into partial state."
            )

        session = self.initialize_session("cf-physical-model", "20-fireseal-physical")
        self.require_tools(
            "cf-physical-model",
            session,
            REQUIRED_PHYSICAL_WRITE_TOOLS,
            "20-fireseal-physical-effective.json",
        )
        self.invoke_tool(
            "cf-physical-model",
            session,
            "classifire_evidence_read",
            {"estimate_id": self.estimate_id},
            "20-fireseal-evidence-read.json",
        )

        defects, evidence = self._defects_and_evidence()
        if not defects:
            raise RuntimeError("No canonical defects exist for fire-seal physical synthesis")

        all_openings: list[dict] = []
        all_services: list[dict] = []
        limitations: list[dict] = []
        next_opening = 1
        next_service = 1

        for index, defect in enumerate(defects, start=1):
            identity = defect.external_defect_id or defect.defect_code or defect.id
            bundle = self._bundle_for_defect(defect, evidence)
            self.save_text(f"20-fireseal-defect-{index:03d}-evidence.json", bundle)
            model = self._synthesise_defect(index, defect, bundle)
            status = str(model.get("status") or "").strip().upper()
            if status == "INSUFFICIENT_EVIDENCE":
                limitations.append(
                    {
                        "canonical_defect_id": defect.id,
                        "external_defect_id": defect.external_defect_id,
                        "defect_code": defect.defect_code,
                        "limitations": model.get("limitations") or [],
                    }
                )
                print(f"LIMIT defect {index}/{len(defects)} {identity} -> insufficient evidence")
                continue
            if status != "MODEL_SUPPORTED":
                raise RuntimeError(
                    f"Defect {identity} synthesis returned unsupported status {status!r}"
                )

            try:
                openings, services, next_opening, next_service = (
                    self._validate_and_remap_defect_model(
                        defect,
                        model,
                        next_opening,
                        next_service,
                    )
                )
            except RuntimeError as exc:
                limitations.append(
                    {
                        "canonical_defect_id": defect.id,
                        "external_defect_id": defect.external_defect_id,
                        "defect_code": defect.defect_code,
                        "limitations": [str(exc)],
                    }
                )
                print(f"LIMIT defect {index}/{len(defects)} {identity} -> {exc}")
                continue

            all_openings.extend(openings)
            all_services.extend(services)
            print(
                f"PASS defect {index}/{len(defects)} {identity} -> "
                f"openings {len(openings)}, services {len(services)}"
            )

        proposal = {
            "defect_count": len(defects),
            "supported_defect_count": len(defects) - len(limitations),
            "limited_defect_count": len(limitations),
            "proposed_opening_count": len(all_openings),
            "proposed_service_count": len(all_services),
            "limitations": limitations,
            "openings": all_openings,
            "services": all_services,
        }
        self.save_json("20-fireseal-merged-proposal.json", proposal)

        if limitations:
            result = {
                "status": "PARTIAL_SOURCE_OR_PHYSICAL_LIMITATION",
                **{key: value for key, value in proposal.items() if key not in {"openings", "services"}},
                "model_submitted": False,
                "reason": (
                    "At least one fire-seal defect still lacks a rational physical estimate after "
                    "the bounded estimation retry. No partial canonical model was submitted."
                ),
            }
            self.save_json("20-fireseal-physical-limitations.json", result)
            print(json.dumps(result, indent=2, default=str))
            return self.inspect_state()

        if not all_openings or not all_services:
            raise RuntimeError("Fire-seal synthesis produced no physical scope")

        self.invoke_tool(
            "cf-physical-model",
            session,
            "classifire_submit_initial_physical_model",
            {
                "estimate_id": self.estimate_id,
                "openings": all_openings,
                "services": all_services,
            },
            "20-fireseal-physical-submit.json",
        )
        self.invoke_tool(
            "cf-physical-model",
            session,
            "classifire_lock_physical_model",
            {
                "estimate_id": self.estimate_id,
                "reason": (
                    "Complete fire-seal/penetration real-UAT Physical Model Lock after "
                    "bounded defect-wise evidence synthesis"
                ),
            },
            "20-fireseal-physical-lock.json",
            require_ok=False,
        )
        return self.inspect_state()

    def run(self) -> dict:
        print("CLASSIFIRE fire-seal / penetration focused real-report UAT")
        print(f"Run ID: {self.run_id}")
        print(f"Estimate ID: {self.estimate_id}")
        print(f"Receipts: {self.receipt_dir}")
        self.preflight()
        manifest = self.stage_visuals()
        intake_report = self.workspace_report("cf-intake-evidence")
        intake_state = self.run_windows_safe_intake(intake_report, manifest)

        retained = self._retained_evidence_status()
        if retained["text_complete"] is True:
            print("PASS structured text evidence already complete for all canonical defects")
            text_state: dict[str, object] = {"retained": True, **retained}
        else:
            text_state = self.run_structured_text_evidence(intake_report)

        retained = self._retained_evidence_status()
        if retained["photo_reconciliation_complete"] is True:
            print("PASS photo reconciliation evidence already complete for all canonical defects")
            photo_state: dict[str, object] = {"retained": True, **retained}
        else:
            photo_state = self.run_photo_aware_evidence(intake_report)

        final_state = self.run_fireseal_physical()
        final_state["run_id"] = self.run_id
        final_state["intake_coverage_ok"] = intake_state["coverage_ok"]
        final_state["text_evidence"] = text_state
        final_state["photo_evidence"] = photo_state
        final_state["status"] = (
            "PHYSICAL_MODEL_LOCKED"
            if final_state["physical_lock_count"] > 0
            else "PARTIAL_SOURCE_OR_PHYSICAL_LIMITATION"
        )
        self.save_json("91-fireseal-final-state.json", final_state)
        print(json.dumps(final_state, indent=2, default=str))
        return final_state


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Resume the real report using bounded, resumable fire-seal and penetration "
            "physical synthesis only."
        )
    )
    parser.add_argument("--run-id")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()

    root = repo_root()
    _receipt_path, receipt = load_receipt(root, args.run_id)
    controller = FireSealFocusedController(
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
        print(f"CLASSIFIRE fire-seal real-report UAT failed: {exc}", file=sys.stderr)
        return 1
    finally:
        controller.close()


if __name__ == "__main__":
    raise SystemExit(main())
