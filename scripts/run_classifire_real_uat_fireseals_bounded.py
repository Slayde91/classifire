from __future__ import annotations

import argparse
import sys

from classifire.canonical_models import Defect, EvidenceSource
from run_classifire_real_uat_fireseals import (
    FireSealFocusedController,
    _trim_text,
    build_bounded_defect_bundle,
)
from run_classifire_real_uat_intake import load_receipt, repo_root


# The prior forensic threshold was 9,000 characters. The retained real-report
# evidence produced one deterministic direct-evidence bundle of 9,923 characters.
# A 12,000-character evidence budget remains comfortably below the Windows
# process/prompt budget while avoiding a lossy AI-to-AI reduction pass.
BOUNDED_DEFECT_EVIDENCE_CHARS = 12_000


class BoundedFireSealFocusedController(FireSealFocusedController):
    """Resume fire-seal UAT with a measured Windows-safe defect budget."""

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
        bundle = build_bounded_defect_bundle(
            defect_payload,
            compact_rows,
            max_chars=BOUNDED_DEFECT_EVIDENCE_CHARS,
        )
        if len(bundle) > BOUNDED_DEFECT_EVIDENCE_CHARS:
            raise RuntimeError(
                "Bounded fire-seal evidence exceeded its measured prompt budget. "
                "No model was submitted."
            )
        return bundle


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Resume the retained CLASSIFIRE real-report fire-seal UAT using a "
            "12,000-character deterministic per-defect evidence budget."
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
