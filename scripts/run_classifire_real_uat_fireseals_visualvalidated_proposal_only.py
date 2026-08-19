from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from run_classifire_real_uat_fireseals_visualvalidated import (
    RETIRED_PHYSICAL_VISUAL_MUTATION_TOOLS,
    VisualValidatedTopologyController,
)
from run_classifire_real_uat_intake import (
    load_receipt,
    repo_root,
)
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from classifire.canonical_models import (
    Defect,
    EvidenceSource,
    PhysicalModelLock,
    ServiceMaterialHypothesis,
    ServiceOpeningLink,
)
from classifire.db import SessionLocal
from classifire.models import Estimate, Opening, Service
from classifire.services.workflow_db import (
    assess_estimate_workflow,
)

PROPOSAL_RECEIPT = "20-fireseal-merged-proposal.json"
WITHHELD_WRITE_RECEIPT = "21-visual-proposal-only-withheld-write.json"
FINAL_RECEIPT = "21-visual-proposal-only-final-state.json"
PROTECTED_STATE_RECEIPT = "21-visual-proposal-only-protected-state.json"

PROTECTED_STATE_FINGERPRINT_VERSION = "CLASSIFIRE-PROTECTED-CANONICAL-STATE-v1"

PROTECTED_STATE_COLUMN_MANIFEST: dict[str, tuple[str, ...]] = {
    "estimate": (
        "project_id",
        "revision",
        "reference",
        "title",
        "status",
        "currency",
        "tax_name",
        "tax_rate",
        "product_markup_override",
        "material_markup_override",
        "labour_markup_override",
        "assumptions",
        "exclusions",
        "qualifications",
        "pricing_release_id",
        "technical_release_id",
        "rules_release_id",
        "products_release_id",
        "labour_release_id",
        "markups_release_id",
        "formula_release_id",
        "brand_release_id",
        "subtotal_ex_tax",
        "tax_total",
        "total_incl_tax",
        "snapshot_json",
        "snapshot_hash",
        "locked_at",
        "approved_at",
        "approved_by_id",
        "id",
        "created_at",
        "updated_at",
        "record_version",
    ),
    "defects": (
        "estimate_id",
        "external_defect_id",
        "defect_code",
        "description",
        "location",
        "classification",
        "evidence_status",
        "status",
        "source_json",
        "id",
        "created_at",
        "updated_at",
        "record_version",
    ),
    "evidence_sources": (
        "estimate_id",
        "defect_id",
        "stored_file_id",
        "evidence_type",
        "source_reference",
        "page_number",
        "region_reference",
        "sha256",
        "evidence_class",
        "confidence",
        "status",
        "source_json",
        "id",
        "created_at",
        "updated_at",
        "record_version",
    ),
    "openings": (
        "estimate_id",
        "defect_id",
        "canonical_defect_id",
        "opening_code",
        "location",
        "substrate_type",
        "substrate_plane",
        "substrate_thickness_mm",
        "orientation",
        "opening_type",
        "width_mm",
        "height_mm",
        "diameter_mm",
        "frl",
        "physical_model_status",
        "technical_status",
        "selected_technical_variant_id",
        "notes",
        "id",
        "created_at",
        "updated_at",
        "record_version",
    ),
    "services": (
        "opening_id",
        "primary_opening_legacy",
        "service_code",
        "service_type",
        "material",
        "nominal_size_mm",
        "outside_diameter_mm",
        "width_mm",
        "height_mm",
        "insulation_type",
        "insulation_thickness_mm",
        "quantity",
        "centre_x_mm",
        "centre_y_mm",
        "evidence_status",
        "confidence",
        "notes",
        "id",
        "created_at",
        "updated_at",
        "record_version",
    ),
    "service_opening_links": (
        "service_id",
        "opening_id",
        "link_type",
        "relationship_status",
        "evidence_status",
        "confidence",
        "source_reference",
        "notes",
        "id",
        "created_at",
        "updated_at",
        "record_version",
    ),
    "service_material_hypotheses": (
        "service_id",
        "material",
        "evidence_status",
        "evidence_ids",
        "confidence",
        "technical_consequence",
        "pricing_consequence",
        "final_status",
        "id",
        "created_at",
        "updated_at",
        "record_version",
    ),
    "physical_model_locks": (
        "project_id",
        "estimate_id",
        "defect_ids",
        "evidence_hashes",
        "service_ids",
        "opening_ids",
        "service_count_status",
        "material_hypothesis_status",
        "critical_unknowns",
        "validator_result",
        "permitted_classes",
        "content_hash",
        "signature",
        "invalidated_at",
        "invalidation_reason",
        "id",
        "created_at",
        "updated_at",
        "record_version",
    ),
}

PROTECTED_WORKFLOW_FACT_FIELDS = (
    "evidence_intake_complete",
    "physical_model_complete",
    "physical_model_locked",
    "technical_search_complete",
    "repair_strategy_locked",
    "components_derived",
    "quantity_and_labour_complete",
    "commercial_pricing_and_recovery_complete",
    "independent_validation_passed",
    "validated_snapshot_created",
    "output_rendered",
    "human_release_approved",
)

PROTECTED_STATE_COMPONENTS = (
    "estimate",
    "workflow",
    "defects",
    "evidence_sources",
    "openings",
    "services",
    "service_opening_links",
    "service_material_hypotheses",
    "physical_model_locks",
)

_PROTECTED_STATE_MODEL_BY_COMPONENT = {
    "estimate": Estimate,
    "defects": Defect,
    "evidence_sources": EvidenceSource,
    "openings": Opening,
    "services": Service,
    "service_opening_links": ServiceOpeningLink,
    "service_material_hypotheses": ServiceMaterialHypothesis,
    "physical_model_locks": PhysicalModelLock,
}

PARTIAL_STATUS = "PARTIAL_SOURCE_OR_PHYSICAL_LIMITATION"
PROPOSAL_READY_STATUS = "VISUAL_VALIDATED_PROPOSAL_READY"


class ProposalOnlyComplete(RuntimeError):
    """Signal that inference reached a canonical write boundary."""

    def __init__(self, tool_name: str) -> None:
        super().__init__("Proposal-only mode withheld canonical write: " + tool_name)
        self.tool_name = tool_name


def _canonical_fingerprint_value(
    value: Any,
) -> Any:
    """Return a deterministic JSON-safe representation of one DB value."""

    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        else:
            value = value.astimezone(UTC)
        return value.isoformat(timespec="microseconds")

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, Decimal):
        return format(value, "f")

    if isinstance(value, dict):
        return {
            str(key): _canonical_fingerprint_value(item)
            for key, item in sorted(
                value.items(),
                key=lambda pair: str(pair[0]),
            )
        }

    if isinstance(value, (list, tuple)):
        return [_canonical_fingerprint_value(item) for item in value]

    if isinstance(value, (set, frozenset)):
        normalised = [_canonical_fingerprint_value(item) for item in value]
        return sorted(
            normalised,
            key=lambda item: json.dumps(
                item,
                allow_nan=False,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )

    if isinstance(value, bytes):
        return value.hex()

    if value is None or isinstance(
        value,
        (str, int, float, bool),
    ):
        return value

    raise TypeError(
        f"Protected-state fingerprint cannot canonicalize value of type {type(value).__name__}"
    )


def _canonical_sha256(
    value: Any,
) -> str:
    encoded = json.dumps(
        _canonical_fingerprint_value(value),
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


def _protected_row_payload(
    row: Any,
    component: str,
) -> dict[str, Any]:
    expected_columns = PROTECTED_STATE_COLUMN_MANIFEST[component]

    return {
        column_name: _canonical_fingerprint_value(
            getattr(
                row,
                column_name,
            )
        )
        for column_name in expected_columns
    }


def _protected_rows_payload(
    rows: list[Any],
    component: str,
) -> list[dict[str, Any]]:
    payload = [_protected_row_payload(row, component) for row in rows]
    return sorted(
        payload,
        key=lambda item: (
            str(item.get("id") or ""),
            json.dumps(
                item,
                allow_nan=False,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        ),
    )


def _validate_protected_state_schema() -> None:
    for component, model in _PROTECTED_STATE_MODEL_BY_COMPONENT.items():
        expected_columns = PROTECTED_STATE_COLUMN_MANIFEST[component]
        actual_columns = tuple(column.key for column in model.__table__.columns)

        if actual_columns != expected_columns:
            raise RuntimeError(
                "Protected-state fingerprint schema drift detected for "
                f"{component}; bump {PROTECTED_STATE_FINGERPRINT_VERSION} "
                "and update its explicit column manifest before running proposal-only UAT"
            )


def _protected_state_snapshot_from_session(
    db: Session,
    estimate_id: str,
) -> dict[str, Any]:
    """Snapshot canonical estimate rows that proposal-only inference must not mutate."""

    _validate_protected_state_schema()

    estimate = db.get(
        Estimate,
        estimate_id,
    )

    if estimate is None:
        raise RuntimeError(
            "Protected-state fingerprint failed: prepared estimate disappeared from the database"
        )

    defects = list(db.scalars(select(Defect).where(Defect.estimate_id == estimate_id)).all())
    evidence_sources = list(
        db.scalars(select(EvidenceSource).where(EvidenceSource.estimate_id == estimate_id)).all()
    )
    openings = list(db.scalars(select(Opening).where(Opening.estimate_id == estimate_id)).all())

    opening_ids = {row.id for row in openings}

    services = (
        list(db.scalars(select(Service).where(Service.opening_id.in_(opening_ids))).all())
        if opening_ids
        else []
    )

    service_ids = {row.id for row in services}

    opening_links = (
        list(
            db.scalars(
                select(ServiceOpeningLink).where(ServiceOpeningLink.opening_id.in_(opening_ids))
            ).all()
        )
        if opening_ids
        else []
    )

    linked_service_ids = {row.service_id for row in opening_links}

    missing_service_ids = linked_service_ids - service_ids

    if missing_service_ids:
        services.extend(
            list(db.scalars(select(Service).where(Service.id.in_(missing_service_ids))).all())
        )
        service_ids.update(missing_service_ids)

    service_opening_links = (
        list(
            db.scalars(
                select(ServiceOpeningLink).where(
                    or_(
                        ServiceOpeningLink.opening_id.in_(opening_ids),
                        ServiceOpeningLink.service_id.in_(service_ids),
                    )
                )
            ).all()
        )
        if (opening_ids or service_ids)
        else []
    )

    service_material_hypotheses = (
        list(
            db.scalars(
                select(ServiceMaterialHypothesis).where(
                    ServiceMaterialHypothesis.service_id.in_(service_ids)
                )
            ).all()
        )
        if service_ids
        else []
    )

    physical_model_locks = list(
        db.scalars(
            select(PhysicalModelLock).where(PhysicalModelLock.estimate_id == estimate_id)
        ).all()
    )
    workflow_assessment = assess_estimate_workflow(
        db,
        estimate,
    )
    workflow_facts = asdict(workflow_assessment.facts)

    if tuple(workflow_facts) != PROTECTED_WORKFLOW_FACT_FIELDS:
        raise RuntimeError(
            "Protected-state fingerprint workflow schema drift detected; "
            f"bump {PROTECTED_STATE_FINGERPRINT_VERSION} and update its explicit "
            "workflow fact manifest before running proposal-only UAT"
        )

    return {
        "fingerprint_version": (PROTECTED_STATE_FINGERPRINT_VERSION),
        "estimate_id": estimate_id,
        "estimate": _protected_row_payload(estimate, "estimate"),
        "workflow": {
            "stage": workflow_assessment.stage,
            "facts": workflow_facts,
        },
        "defects": _protected_rows_payload(defects, "defects"),
        "evidence_sources": _protected_rows_payload(evidence_sources, "evidence_sources"),
        "openings": _protected_rows_payload(openings, "openings"),
        "services": _protected_rows_payload(services, "services"),
        "service_opening_links": _protected_rows_payload(
            service_opening_links,
            "service_opening_links",
        ),
        "service_material_hypotheses": _protected_rows_payload(
            service_material_hypotheses,
            "service_material_hypotheses",
        ),
        "physical_model_locks": _protected_rows_payload(
            physical_model_locks,
            "physical_model_locks",
        ),
    }


def _protected_state_snapshot(
    estimate_id: str,
) -> dict[str, Any]:
    with SessionLocal() as db:
        return _protected_state_snapshot_from_session(
            db,
            estimate_id,
        )


def _protected_state_fingerprint(
    snapshot: dict[str, Any],
) -> str:
    return _canonical_sha256(snapshot)


def _protected_component_fingerprints(
    snapshot: dict[str, Any],
) -> dict[str, str]:
    return {
        component: _canonical_sha256(snapshot.get(component))
        for component in PROTECTED_STATE_COMPONENTS
    }


def _protected_state_counts(
    snapshot: dict[str, Any],
) -> dict[str, int]:
    return {
        component: (
            1
            if component
            in {
                "estimate",
                "workflow",
            }
            and isinstance(
                snapshot.get(component),
                dict,
            )
            else len(snapshot.get(component) or [])
        )
        for component in PROTECTED_STATE_COMPONENTS
    }


@contextmanager
def _proposal_only_protected_state_guard(
    controller: (ProposalOnlyVisualValidatedTopologyController),
) -> Iterator[dict[str, Any]]:
    before_snapshot = _protected_state_snapshot(controller.estimate_id)
    before_fingerprint = _protected_state_fingerprint(before_snapshot)
    before_components = _protected_component_fingerprints(before_snapshot)

    guard_result: dict[str, Any] = {
        "fingerprint_version": (PROTECTED_STATE_FINGERPRINT_VERSION),
        "before_fingerprint": (before_fingerprint),
        "before_counts": (_protected_state_counts(before_snapshot)),
        "before_component_fingerprints": (before_components),
        "after_fingerprint": None,
        "after_counts": None,
        "after_component_fingerprints": None,
        "changed_components": None,
        "protected_state_unchanged": None,
        "guarded_operation_error": None,
    }

    guarded_error: Exception | None = None

    try:
        yield guard_result
    except Exception as exc:
        guarded_error = exc
        guard_result["guarded_operation_error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
        raise
    finally:
        after_snapshot = _protected_state_snapshot(controller.estimate_id)
        after_fingerprint = _protected_state_fingerprint(after_snapshot)
        after_components = _protected_component_fingerprints(after_snapshot)
        changed_components = sorted(
            component
            for component in PROTECTED_STATE_COMPONENTS
            if (before_components[component] != after_components[component])
        )
        unchanged = before_fingerprint == after_fingerprint

        guard_result.update(
            {
                "after_fingerprint": (after_fingerprint),
                "after_counts": (_protected_state_counts(after_snapshot)),
                "after_component_fingerprints": (after_components),
                "changed_components": (changed_components),
                "protected_state_unchanged": (unchanged),
            }
        )

        controller.save_json(
            PROTECTED_STATE_RECEIPT,
            {
                "status": ("PASS" if unchanged else "FAIL"),
                "run_id": controller.run_id,
                "estimate_id": (controller.estimate_id),
                **guard_result,
            },
        )

        if not unchanged:
            message = (
                "Proposal-only invariant failed: "
                "protected canonical state changed "
                "during inference; changed components: " + ", ".join(changed_components)
            )

            if guarded_error is not None:
                message += (
                    "; guarded operation also failed with "
                    f"{type(guarded_error).__name__}: {guarded_error}"
                )

            raise RuntimeError(message) from guarded_error


class ProposalOnlyVisualValidatedTopologyController(VisualValidatedTopologyController):
    """Run visual Physical/Validator inference without canonical writes."""

    def preflight(self) -> None:
        """Verify Gateway RPC without mutating its managed service state."""
        config = self.openclaw(
            "config",
            "validate",
            "--json",
        )
        self.save_text(
            "01-openclaw-config.json",
            config.stdout,
        )

        status = self.openclaw(
            "gateway",
            "status",
            "--require-rpc",
            "--timeout",
            "60000",
            timeout=90,
            check=False,
        )

        if status.returncode != 0:
            detail = "\n".join(
                item
                for item in (
                    status.stdout.strip(),
                    status.stderr.strip(),
                )
                if item
            )
            raise RuntimeError(
                "OpenClaw Gateway RPC preflight failed; "
                "proposal-only mode will not restart the managed Gateway."
                + (f" Details: {detail}" if detail else "")
            )

        self.save_text(
            "02-openclaw-gateway.txt",
            status.stdout + status.stderr,
        )
        print("PASS OpenClaw Gateway RPC")
        self.ensure_api()

    def _withhold_retired_legacy_mutation(
        self,
        *,
        tool_name: str,
        proposal_receipt: str | None,
    ) -> None:
        proposal_path = self.receipt_dir / (proposal_receipt or PROPOSAL_RECEIPT)

        if not proposal_path.is_file():
            raise RuntimeError(
                "Proposal-only mode reached a retired canonical mutation boundary "
                "before the merged proposal receipt existed"
            )

        self.save_json(
            WITHHELD_WRITE_RECEIPT,
            {
                "status": PROPOSAL_READY_STATUS,
                "reason_code": "RETIRED_RAW_PHYSICAL_MUTATION_TOOL",
                "run_id": self.run_id,
                "estimate_id": self.estimate_id,
                "agent_id": "cf-physical-model",
                "withheld_tool": tool_name,
                "retired_tools": sorted(RETIRED_PHYSICAL_VISUAL_MUTATION_TOOLS),
                "proposal_receipt": str(proposal_path),
                "canonical_write_performed": False,
                "physical_model_lock_created": False,
                "next_action": (
                    "Proposal-only UAT stops here. A fresh controlled preflight and "
                    "independently signed admission are required before the separate "
                    "cf-adjudicated-physical-writer can submit canonical state."
                ),
            },
        )

        raise ProposalOnlyComplete(tool_name)

    def withhold_legacy_physical_mutation(
        self,
        *,
        source_stage: str,
        proposal_receipt: str | None,
        proposed_opening_count: int | None,
        proposed_service_count: int | None,
        receipt_name: str,
    ) -> dict[str, Any]:
        del source_stage, proposed_opening_count, proposed_service_count, receipt_name
        self._withhold_retired_legacy_mutation(
            tool_name="classifire_submit_initial_physical_model",
            proposal_receipt=proposal_receipt,
        )

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
                "Unable to determine OpenClaw tool name for proposal-only write control"
            )

        if tool_name in RETIRED_PHYSICAL_VISUAL_MUTATION_TOOLS:
            self._withhold_retired_legacy_mutation(
                tool_name=tool_name,
                proposal_receipt=PROPOSAL_RECEIPT,
            )

        return super().invoke_tool(
            *args,
            **kwargs,
        )


def _assert_no_canonical_physical_state(
    controller: ProposalOnlyVisualValidatedTopologyController,
    state: dict[str, Any],
) -> None:
    opening_count = int(state.get("opening_count") or 0)
    service_count = int(state.get("service_count") or 0)
    lock_count = int(state.get("physical_lock_count") or 0)

    if opening_count != 0 or service_count != 0 or lock_count != 0:
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

    controller = ProposalOnlyVisualValidatedTopologyController(
        receipt,
        base_url=args.base_url,
        timeout_seconds=args.timeout_seconds,
    )

    try:
        withheld_tool: str | None = None

        with _proposal_only_protected_state_guard(controller) as protected_state:
            try:
                state = controller.run()
            except ProposalOnlyComplete as exc:
                withheld_tool = exc.tool_name
                state = controller.inspect_state()

            _assert_no_canonical_physical_state(
                controller,
                state,
            )

        proposal_path = controller.receipt_dir / PROPOSAL_RECEIPT

        if withheld_tool is not None and not proposal_path.is_file():
            raise RuntimeError(
                "Canonical write was withheld but the merged proposal receipt is missing"
            )

        if withheld_tool is not None:
            status = PROPOSAL_READY_STATUS
        else:
            status = str(state.get("status") or "").strip()

        result = {
            "status": status,
            "run_id": controller.run_id,
            "estimate_id": controller.estimate_id,
            "proposal_receipt": (str(proposal_path) if proposal_path.is_file() else None),
            "withheld_tool": withheld_tool,
            "canonical_write_performed": False,
            "canonical_opening_count": int(state.get("opening_count") or 0),
            "canonical_service_count": int(state.get("service_count") or 0),
            "canonical_active_lock_count": int(state.get("physical_lock_count") or 0),
            "protected_state": {
                "fingerprint_version": (protected_state["fingerprint_version"]),
                "before_fingerprint": (protected_state["before_fingerprint"]),
                "after_fingerprint": (protected_state["after_fingerprint"]),
                "before_counts": (protected_state["before_counts"]),
                "before_component_fingerprints": (protected_state["before_component_fingerprints"]),
                "after_counts": (protected_state["after_counts"]),
                "after_component_fingerprints": (protected_state["after_component_fingerprints"]),
                "changed_components": (protected_state["changed_components"]),
                "protected_state_unchanged": (protected_state["protected_state_unchanged"]),
            },
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
            f"CLASSIFIRE proposal-only visual UAT failed: {exc}",
            file=sys.stderr,
        )
        return 1

    finally:
        controller.close()


if __name__ == "__main__":
    raise SystemExit(main())
