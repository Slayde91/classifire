from __future__ import annotations

import argparse
import hashlib
import json
import sys

from classifire.canonical_models import Defect, EvidenceSource
from classifire.services.physical_scope import canonical_opening_type, is_blank_opening_type
from run_classifire_real_uat_deterministic import _json_from_payload
from run_classifire_real_uat_fireseals_resumable import ResumableFireSealFocusedController
from run_classifire_real_uat_intake import load_receipt, repo_root


PHYSICAL_SYNTHESIS_POLICY_VERSION = "CLASSIFIRE-FIRESEAL-PHYSICAL-v4-BLANK-OPENING-PHOTO-ASSUMPTIONS"


def _nonempty(value: object) -> bool:
    return value is not None and bool(str(value).strip())


def _model_completeness_issues(model: dict) -> list[str]:
    if str(model.get("status") or "").strip().upper() != "MODEL_SUPPORTED":
        return []
    openings = model.get("openings")
    services = model.get("services")
    if not isinstance(openings, list) or not openings:
        return ["MODEL_SUPPORTED requires at least one Opening"]
    if not isinstance(services, list):
        return ["services must be an array; it may be empty only for explicit blank openings"]

    opening_codes: set[str] = set()
    link_counts: dict[str, int] = {}
    opening_rows: dict[str, dict] = {}
    issues: list[str] = []
    for index, row in enumerate(openings, start=1):
        if not isinstance(row, dict):
            issues.append(f"Opening {index} is not an object")
            continue
        code = str(row.get("opening_code") or "").strip()
        if not code:
            issues.append(f"Opening {index} has no opening_code")
            continue
        if code in opening_codes:
            issues.append(f"Opening code {code} is duplicated")
            continue
        opening_codes.add(code)
        opening_rows[code] = row
        link_counts[code] = 0
        for field_name in ("substrate_type", "substrate_plane", "orientation"):
            if not _nonempty(row.get(field_name)):
                issues.append(
                    f"Opening {code} is missing {field_name}; use report/photos for a provisional assumption where rational"
                )

    for index, row in enumerate(services, start=1):
        if not isinstance(row, dict):
            issues.append(f"Service {index} is not an object")
            continue
        primary = str(row.get("primary_opening_code") or "").strip()
        linked = row.get("opening_codes")
        if primary not in opening_codes:
            issues.append(f"Service {index} references unknown primary opening {primary!r}")
            continue
        if not isinstance(linked, list) or not linked:
            issues.append(f"Service {index} has no opening_codes")
            continue
        for code in dict.fromkeys(str(item).strip() for item in linked if str(item).strip()):
            if code not in opening_codes:
                issues.append(f"Service {index} references unknown opening {code!r}")
            else:
                link_counts[code] = link_counts.get(code, 0) + 1

    for code, row in opening_rows.items():
        opening_type = canonical_opening_type(row.get("opening_type"))
        links = link_counts.get(code, 0)
        if links == 0 and not is_blank_opening_type(opening_type):
            issues.append(
                f"Opening {code} has no Service: classify it as blank_opening/blank_core_hole only when evidence supports an empty opening"
            )
        if links > 0 and is_blank_opening_type(opening_type):
            issues.append(
                f"Opening {code} is classified blank but has linked Services; resolve the physical contradiction"
            )

    return list(dict.fromkeys(issues))


class BlankAwareFireSealFocusedController(ResumableFireSealFocusedController):
    """Correct fire-seal UAT policy for service-free blank openings and photo assumptions."""

    def defect_physical_prompt(self, defect: Defect, evidence_text: str) -> str:
        base = super().defect_physical_prompt(defect, evidence_text)
        return base + f"""

Current binding CLASSIFIRE fire-seal physical-scope policy ({PHYSICAL_SYNTHESIS_POLICY_VERSION}):
- An Opening does NOT require a Service merely because it requires a fire seal.
- An empty aperture, redundant core or empty core hole that itself requires sealing is valid physical scope.
  Use opening_type `blank_opening` or `blank_core_hole` and return NO placeholder Service for it.
- Use opening_type `service_penetration` for an Opening containing one or more actual Services.
- Never invent a pipe, cable, conduit or other Service simply to give an Opening a Service relationship.
- If report text does not state substrate_type, substrate_plane or orientation, use the defect-linked full-page
  layout and photographs to make the most defensible provisional/inferred assumption when a rational visual basis
  exists. Record the assumption and visual basis in Opening notes. Do not stop merely because the report text is silent.
- Substrate plane and orientation are separate fields. A wall normally supports vertical orientation; a floor/slab/
  soffit normally supports horizontal orientation, subject to the actual visual evidence.
- If no rational basis exists even after reviewing the photographs, leave the field unresolved and return
  INSUFFICIENT_EVIDENCE rather than inventing it.
- FRL source evidence controls when present. If FRL is absent, leave `frl` null here; the CLASSIFIRE controller will
  apply the governed current-scope estimating assumption `-/120/120`, record it as assumed and require verification
  before technical approval or Human Release.
- Blank-opening status affects only the physical Service relationship. Package 15/17 technical selection remains
  a later Opening-specific stage and must still identify an applicable blank-aperture/core-hole system.
"""

    def _save_cache_metadata(self, defect_index: int, defect: Defect, bundle: str) -> None:
        self.save_json(
            f"20-fireseal-defect-{defect_index:03d}-cache.json",
            {
                "canonical_defect_id": defect.id,
                "external_defect_id": defect.external_defect_id,
                "bundle_sha256": hashlib.sha256(bundle.encode("utf-8")).hexdigest(),
                "physical_synthesis_policy_version": PHYSICAL_SYNTHESIS_POLICY_VERSION,
            },
        )

    def _cached_supported_model(
        self,
        defect_index: int,
        defect: Defect,
        bundle: str,
    ) -> dict | None:
        bundle_hash = hashlib.sha256(bundle.encode("utf-8")).hexdigest()
        metadata_path = self.receipt_dir / f"20-fireseal-defect-{defect_index:03d}-cache.json"
        candidate_paths = (
            self.receipt_dir / f"20-fireseal-defect-{defect_index:03d}-physical-completeness-repair.json",
            self.receipt_dir / f"20-fireseal-defect-{defect_index:03d}-estimate-retry.json",
            self.receipt_dir / f"20-fireseal-defect-{defect_index:03d}-synthesis.json",
        )
        if not metadata_path.is_file():
            return None
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if metadata.get("bundle_sha256") != bundle_hash:
            return None
        if metadata.get("canonical_defect_id") != defect.id:
            return None
        if metadata.get("physical_synthesis_policy_version") != PHYSICAL_SYNTHESIS_POLICY_VERSION:
            return None

        for path in candidate_paths:
            if not path.is_file():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                model = _json_from_payload(payload, context="Cached blank-aware fire-seal synthesis")
            except (OSError, json.JSONDecodeError, RuntimeError):
                continue
            if (
                str(model.get("status") or "").strip().upper() == "MODEL_SUPPORTED"
                and not _model_completeness_issues(model)
            ):
                print(
                    f"PASS defect {defect_index} cache -> retained blank-aware supported physical proposal"
                )
                return model
        return None

    def _physical_completeness_repair_prompt(
        self,
        defect: Defect,
        bundle: str,
        model: dict,
        issues: list[str],
    ) -> str:
        return self.defect_physical_prompt(defect, bundle) + f"""

The previous physical proposal is not complete under the current fire-seal policy.
Issues:
{json.dumps(issues, ensure_ascii=False, separators=(",", ":"))}

Re-evaluate the SAME direct evidence. Use defect-linked photographs/layout to make provisional substrate_type,
substrate_plane and orientation assumptions wherever a rational visual basis exists. If the physical condition is an
empty/redundant core or blank aperture, return the Opening with opening_type blank_core_hole/blank_opening and do NOT
invent a Service. If it contains an actual service, return service_penetration and the supported Services. Preserve
assumptions in notes. Return INSUFFICIENT_EVIDENCE only when the photographs and text still provide no rational basis.
"""

    def _synthesise_defect(
        self,
        defect_index: int,
        defect: Defect,
        bundle: str,
    ) -> dict:
        cached = self._cached_supported_model(defect_index, defect, bundle)
        if cached is not None:
            return cached

        payload = self.infer_model(
            prompt=self.defect_physical_prompt(defect, bundle),
            receipt_name=f"20-fireseal-defect-{defect_index:03d}-synthesis",
            thinking="high",
        )
        model = _json_from_payload(
            payload,
            context=f"Blank-aware fire-seal synthesis for defect {defect.external_defect_id or defect.id}",
        )
        self._save_cache_metadata(defect_index, defect, bundle)

        if str(model.get("status") or "").strip().upper() == "INSUFFICIENT_EVIDENCE":
            retry_payload = self.infer_model(
                prompt=self._estimation_retry_prompt(defect, bundle, model),
                receipt_name=f"20-fireseal-defect-{defect_index:03d}-estimate-retry",
                thinking="high",
            )
            model = _json_from_payload(
                retry_payload,
                context=f"Blank-aware estimation retry for defect {defect.external_defect_id or defect.id}",
            )

        issues = _model_completeness_issues(model)
        if str(model.get("status") or "").strip().upper() == "MODEL_SUPPORTED" and issues:
            repair_payload = self.infer_model(
                prompt=self._physical_completeness_repair_prompt(defect, bundle, model, issues),
                receipt_name=f"20-fireseal-defect-{defect_index:03d}-physical-completeness-repair",
                thinking="high",
            )
            model = _json_from_payload(
                repair_payload,
                context=f"Blank-aware physical-completeness repair for defect {defect.external_defect_id or defect.id}",
            )
            issues = _model_completeness_issues(model)

        if str(model.get("status") or "").strip().upper() == "MODEL_SUPPORTED" and issues:
            return {
                "status": "INSUFFICIENT_EVIDENCE",
                "limitations": issues,
                "openings": [],
                "services": [],
            }
        return model

    def _validate_and_remap_defect_model(
        self,
        defect: Defect,
        model: dict,
        opening_start: int,
        service_start: int,
    ) -> tuple[list[dict], list[dict], int, int]:
        self._apply_estimation_defaults(model)
        openings_raw = model.get("openings")
        services_raw = model.get("services")
        if not isinstance(openings_raw, list) or not openings_raw:
            raise RuntimeError("Defect synthesis must return at least one Opening")
        if not isinstance(services_raw, list):
            raise RuntimeError("Defect synthesis services must be an array")

        local_openings = [self._clean_opening(row) for row in openings_raw if isinstance(row, dict)]
        local_services = [self._clean_service(row) for row in services_raw if isinstance(row, dict)]
        if not local_openings:
            raise RuntimeError("Defect synthesis returned no valid Openings")

        local_codes: list[str] = []
        local_opening_by_code: dict[str, dict] = {}
        for row in local_openings:
            code = str(row.get("opening_code") or "").strip()
            if not code or code in local_codes:
                raise RuntimeError("Defect synthesis returned blank or duplicate opening codes")
            local_codes.append(code)
            local_opening_by_code[code] = row

        opening_map = {
            local_code: f"O-{opening_start + index:03d}"
            for index, local_code in enumerate(local_codes)
        }
        linked_counts = {code: 0 for code in local_codes}

        services: list[dict] = []
        seen_service_codes: set[str] = set()
        for index, row in enumerate(local_services):
            local_service_code = str(row.get("service_code") or "").strip()
            if not local_service_code or local_service_code in seen_service_codes:
                raise RuntimeError("Defect synthesis returned blank or duplicate service codes")
            seen_service_codes.add(local_service_code)

            primary = str(row.get("primary_opening_code") or "").strip()
            linked = row.get("opening_codes")
            if primary not in opening_map or not isinstance(linked, list) or not linked:
                raise RuntimeError(f"Service {local_service_code} has invalid opening linkage")
            requested_codes = list(dict.fromkeys(str(item) for item in linked))
            if any(code not in opening_map for code in requested_codes):
                raise RuntimeError(f"Service {local_service_code} references an unknown opening")
            try:
                quantity = float(row.get("quantity"))
            except (TypeError, ValueError) as exc:
                raise RuntimeError(f"Service {local_service_code} has no explicit numeric quantity") from exc
            if quantity <= 0:
                raise RuntimeError(f"Service {local_service_code} quantity must be greater than zero")

            mapped = dict(row)
            mapped["service_code"] = f"S-{service_start + index:03d}"
            mapped["primary_opening_code"] = opening_map[primary]
            mapped["opening_codes"] = [opening_map[code] for code in requested_codes]
            services.append(mapped)
            for code in requested_codes:
                linked_counts[code] += 1

        openings: list[dict] = []
        for local_code in local_codes:
            row = local_opening_by_code[local_code]
            opening_type = canonical_opening_type(row.get("opening_type"))
            link_count = linked_counts.get(local_code, 0)
            if link_count == 0:
                if not is_blank_opening_type(opening_type):
                    raise RuntimeError(
                        f"Opening {local_code} has no Service but is not explicitly a blank opening/core hole"
                    )
            else:
                if is_blank_opening_type(opening_type):
                    raise RuntimeError(
                        f"Opening {local_code} is classified blank but has linked Services"
                    )
                if not opening_type:
                    opening_type = "service_penetration"

            missing = [
                field_name
                for field_name in ("substrate_type", "substrate_plane", "orientation", "frl")
                if not _nonempty(row.get(field_name))
            ]
            if missing:
                raise RuntimeError(
                    f"Opening {local_code} remains incomplete after assumption policy: {', '.join(missing)}"
                )

            mapped = dict(row)
            mapped["opening_code"] = opening_map[local_code]
            mapped["external_defect_id"] = defect.external_defect_id or defect.defect_code
            mapped["opening_type"] = opening_type
            openings.append(mapped)

        return (
            openings,
            services,
            opening_start + len(openings),
            service_start + len(services),
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild the retained CLASSIFIRE fire-seal/penetration physical model with "
            "service-free blank openings, photo-based provisional substrate/orientation "
            "assumptions and the governed missing-FRL policy."
        )
    )
    parser.add_argument("--run-id")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()

    root = repo_root()
    _receipt_path, receipt = load_receipt(root, args.run_id)
    controller = BlankAwareFireSealFocusedController(
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
        print(
            f"CLASSIFIRE blank-aware fire-seal real-report UAT failed: {exc}",
            file=sys.stderr,
        )
        return 1
    finally:
        controller.close()


if __name__ == "__main__":
    raise SystemExit(main())
