from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from run_classifire_real_uat_fireseals_visualvalidated import (
    PHYSICAL_VISUAL_GUARDED_WRITE_TOOLS,
    VisualValidatedTopologyController,
)
from run_classifire_real_uat_intake import (
    load_receipt,
    repo_root,
)


PROPOSAL_RECEIPT = "20-fireseal-merged-proposal.json"
WITHHELD_WRITE_RECEIPT = (
    "21-visual-proposal-only-withheld-write.json"
)
FINAL_RECEIPT = (
    "21-visual-proposal-only-final-state.json"
)

PARTIAL_STATUS = (
    "PARTIAL_SOURCE_OR_PHYSICAL_LIMITATION"
)
PROPOSAL_READY_STATUS = (
    "VISUAL_VALIDATED_PROPOSAL_READY"
)


class ProposalOnlyComplete(RuntimeError):
    """Signal that inference reached a canonical write boundary."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(
            "Proposal-only mode withheld canonical write: "
            + tool_name
        )
        self.tool_name = tool_name


class ProposalOnlyVisualValidatedTopologyController(
    VisualValidatedTopologyController
):
    """Run visual Physical/Validator inference without canonical writes."""

    def invoke_tool(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        tool_name = kwargs.get("tool_name")

        if tool_name is None and len(args) >= 3:
            tool_name = args[2]

        if not isinstance(tool_name, str):
            raise RuntimeError(
                "Unable to determine OpenClaw tool name "
                "for proposal-only write control"
            )

        if tool_name in PHYSICAL_VISUAL_GUARDED_WRITE_TOOLS:
            proposal_path = (
                self.receipt_dir /
                PROPOSAL_RECEIPT
            )

            if not proposal_path.is_file():
                raise RuntimeError(
                    "Proposal-only mode reached a canonical "
                    "write boundary before the merged proposal "
                    "receipt existed"
                )

            self.save_json(
                WITHHELD_WRITE_RECEIPT,
                {
                    "status": PROPOSAL_READY_STATUS,
                    "run_id": self.run_id,
                    "estimate_id": self.estimate_id,
                    "withheld_tool": tool_name,
                    "proposal_receipt": str(
                        proposal_path
                    ),
                    "canonical_write_performed": False,
                },
            )

            raise ProposalOnlyComplete(
                tool_name
            )

        return super().invoke_tool(
            *args,
            **kwargs,
        )


def _assert_no_canonical_physical_state(
    controller: ProposalOnlyVisualValidatedTopologyController,
    state: dict[str, Any],
) -> None:
    opening_count = int(
        state.get("opening_count") or 0
    )
    service_count = int(
        state.get("service_count") or 0
    )
    lock_count = int(
        state.get("physical_lock_count") or 0
    )

    if (
        opening_count != 0
        or service_count != 0
        or lock_count != 0
    ):
        raise RuntimeError(
            "Proposal-only invariant failed: canonical "
            "Physical state exists after inference "
            f"(openings={opening_count}, "
            f"services={service_count}, "
            f"active_locks={lock_count})"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run CLASSIFIRE corrected visual-validated "
            "Physical inference and independent validation "
            "without submitting or locking canonical state."
        )
    )

    parser.add_argument(
        "--run-id",
        required=True,
    )

    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8787",
    )

    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=1200,
    )

    args = parser.parse_args()

    root = repo_root()

    _receipt_path, receipt = load_receipt(
        root,
        args.run_id,
    )

    controller = (
        ProposalOnlyVisualValidatedTopologyController(
            receipt,
            base_url=args.base_url,
            timeout_seconds=args.timeout_seconds,
        )
    )

    try:
        withheld_tool: str | None = None

        try:
            state = controller.run()
        except ProposalOnlyComplete as exc:
            withheld_tool = exc.tool_name
            state = controller.inspect_state()

        _assert_no_canonical_physical_state(
            controller,
            state,
        )

        proposal_path = (
            controller.receipt_dir /
            PROPOSAL_RECEIPT
        )

        if (
            withheld_tool is not None
            and not proposal_path.is_file()
        ):
            raise RuntimeError(
                "Canonical write was withheld but the "
                "merged proposal receipt is missing"
            )

        if withheld_tool is not None:
            status = PROPOSAL_READY_STATUS
        else:
            status = str(
                state.get("status") or ""
            ).strip()

        result = {
            "status": status,
            "run_id": controller.run_id,
            "estimate_id": controller.estimate_id,
            "proposal_receipt": (
                str(proposal_path)
                if proposal_path.is_file()
                else None
            ),
            "withheld_tool": withheld_tool,
            "canonical_write_performed": False,
            "canonical_opening_count": int(
                state.get("opening_count") or 0
            ),
            "canonical_service_count": int(
                state.get("service_count") or 0
            ),
            "canonical_active_lock_count": int(
                state.get("physical_lock_count") or 0
            ),
            "underlying_state": state,
        }

        controller.save_json(
            FINAL_RECEIPT,
            result,
        )

        print(
            json.dumps(
                result,
                indent=2,
                default=str,
            )
        )

        if status in {
            PROPOSAL_READY_STATUS,
            PARTIAL_STATUS,
        }:
            return 0

        return 1

    except Exception as exc:
        print(
            "CLASSIFIRE proposal-only visual UAT failed: "
            f"{exc}",
            file=sys.stderr,
        )
        return 1

    finally:
        controller.close()


if __name__ == "__main__":
    raise SystemExit(main())
