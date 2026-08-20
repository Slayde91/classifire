"""Stack-native, no-write preflight for one adjudicated initial submission."""

from __future__ import annotations

import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from .. import physical_model_submission_schema as payload_schema_module
from ..models import Estimate
from ..physical_model_submission_schema import InitialCanonicalPhysicalSubmission
from . import adjudicated_admission as admission_module
from . import adjudicated_physical_submission as writer_module
from . import canonical_submission_state as state_module
from .adjudicated_admission import (
    ADMISSION_MANIFEST_SCHEMA,
    ADMISSION_SIGNATURE_ALGORITHM,
    normalised_submission_payload_sha256,
    sha256_hex,
)
from .adjudicated_physical_submission import CONTROLLED_CANONICAL_WRITER_POLICY_VERSION
from .canonical_submission_state import (
    INITIAL_SUBMISSION_STATE_FINGERPRINT_VERSION,
    CanonicalSubmissionStateError,
    initial_submission_state,
)
from .deployment_lineage import assess_deployment_lineage
from .phase8_adjudicated_payload import (
    Phase8AdjudicatedPayloadError,
    derive_phase8_adjudicated_payload,
)

PREFLIGHT_SCHEMA = "CLASSIFIRE-ADJUDICATED-CANONICALISATION-PREFLIGHT-v3"
PREFLIGHT_STATUS = "PRECHECK_PASSED_SIGNED_ADMISSION_REQUIRED"
MAX_PREFLIGHT_RECEIPT_BYTES = 5 * 1024 * 1024
MAX_ARTIFACT_BYTES = 25 * 1024 * 1024
DEFAULT_MAX_PREFLIGHT_AGE_SECONDS = 15 * 60
REQUIRED_ARTIFACT_NAMES = frozenset(
    {
        "adjudicated_proposal",
        "adjudicated_final_state",
        "adjudicated_diff",
        "human_adjudication_comparison",
        "canonical_submission_payload",
    }
)
_PROTECTED_COUNT_NAMES = frozenset(
    {
        "defect_count",
        "evidence_count",
        "opening_count",
        "service_count",
        "service_opening_link_count",
        "active_physical_model_lock_count",
    }
)
_SHA256 = re.compile(r"^[0-9A-F]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,159}$")
_RECEIPT_FIELDS = frozenset(
    {
        "schema",
        "status",
        "generated_at",
        "project_id",
        "estimate_id",
        "source_run_id",
        "adjudicated_run_id",
        "canonical_write_performed",
        "database_write_performed",
        "gateway_call_performed",
        "submission_eligible",
        "lock_eligible",
        "normalised_submission_payload",
        "normalised_submission_payload_sha256",
        "protected_state",
        "artifact_digests",
        "policy_versions",
        "implementation_hashes",
    }
)


class AdjudicatedPreflightError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Adjudicated preflight failed: {code}.")


@dataclass(frozen=True)
class AdjudicatedPreflightBinding:
    receipt_sha256: str
    project_id: str
    estimate_id: str
    source_run_id: str
    adjudicated_run_id: str
    submission_payload: dict[str, Any]
    submission_payload_sha256: str
    protected_state_fingerprint: str
    protected_state_fingerprint_version: str
    artifact_digests: dict[str, str]
    policy_versions: dict[str, str]
    generated_at: datetime


def canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise AdjudicatedPreflightError("PREFLIGHT_JSON_INVALID") from exc


def controlled_boundary_implementation_hashes() -> dict[str, str]:
    repository_root = Path(__file__).resolve().parents[3]
    paths = {
        "preflight_script_sha256": repository_root
        / "scripts"
        / "preflight_adjudicated_canonicalisation.py",
        "phase8_payload_adapter_script_sha256": repository_root
        / "scripts"
        / "derive_phase8_adjudicated_payload.py",
        "phase8_payload_adapter_module_sha256": Path(__file__).with_name(
            "phase8_adjudicated_payload.py"
        ),
        "preflight_module_sha256": Path(__file__),
        "admission_verifier_module_sha256": Path(admission_module.__file__ or ""),
        "admission_registration_module_sha256": Path(__file__).with_name(
            "adjudicated_admission_registration.py"
        ),
        "controlled_writer_module_sha256": Path(writer_module.__file__ or ""),
        "canonical_submission_state_module_sha256": Path(state_module.__file__ or ""),
        "deployment_lineage_module_sha256": Path(__file__).with_name("deployment_lineage.py"),
        "submission_payload_schema_module_sha256": Path(payload_schema_module.__file__ or ""),
        "admission_journal_migration_sha256": repository_root
        / "migrations"
        / "versions"
        / "0005_adjudicated_admission_journal.py",
        "submission_receipt_migration_sha256": repository_root
        / "migrations"
        / "versions"
        / "0006_physical_submission_receipts.py",
    }
    if any(not path.is_file() for path in paths.values()):
        raise AdjudicatedPreflightError("PREFLIGHT_IMPLEMENTATION_UNAVAILABLE")
    try:
        return {name: sha256_hex(path.read_bytes()) for name, path in sorted(paths.items())}
    except OSError as exc:
        raise AdjudicatedPreflightError("PREFLIGHT_IMPLEMENTATION_UNAVAILABLE") from exc


def build_adjudicated_preflight(
    db: Session,
    *,
    estimate_id: str,
    submission_payload: object,
    source_run_id: str,
    adjudicated_run_id: str,
    artifact_files: Mapping[str, Path],
    policy_versions: Mapping[str, str],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a deterministic receipt in memory without writing canonical state."""

    source_run_id = _identifier(source_run_id)
    adjudicated_run_id = _identifier(adjudicated_run_id)
    lineage = assess_deployment_lineage(db)
    if lineage.status != "READY":
        raise AdjudicatedPreflightError(lineage.code)
    try:
        payload = InitialCanonicalPhysicalSubmission.model_validate(
            submission_payload
        ).model_dump(mode="json")
    except ValidationError as exc:
        raise AdjudicatedPreflightError("PREFLIGHT_PAYLOAD_INVALID") from exc
    try:
        state = initial_submission_state(db, estimate_id=estimate_id)
    except CanonicalSubmissionStateError as exc:
        raise AdjudicatedPreflightError(exc.code) from exc
    for count_name in (
        "opening_count",
        "service_count",
        "service_opening_link_count",
        "active_physical_model_lock_count",
    ):
        if state.counts[count_name] != 0:
            raise AdjudicatedPreflightError("PREFLIGHT_CANONICAL_STATE_NOT_EMPTY")
    known_defect_ids = {item["id"] for item in state.snapshot["defects"]}
    if any(item["canonical_defect_id"] not in known_defect_ids for item in payload["openings"]):
        raise AdjudicatedPreflightError("PREFLIGHT_DEFECT_BINDING_INVALID")

    artifact_digests = _artifact_digests(artifact_files)
    _require_payload_artifact_matches(
        artifact_files["canonical_submission_payload"],
        expected_payload=payload,
    )
    try:
        derived = derive_phase8_adjudicated_payload(
            db,
            estimate_id=estimate_id,
            adjudicated_proposal_path=artifact_files["adjudicated_proposal"],
            adjudicated_final_state_path=artifact_files["adjudicated_final_state"],
            adjudicated_diff_path=artifact_files["adjudicated_diff"],
            human_comparison_path=artifact_files["human_adjudication_comparison"],
        )
    except Phase8AdjudicatedPayloadError as exc:
        raise AdjudicatedPreflightError(exc.code) from exc
    if (
        derived.payload != payload
        or derived.source_run_id != source_run_id
        or derived.adjudicated_run_id != adjudicated_run_id
        or any(
            artifact_digests[name] != digest
            for name, digest in derived.artifact_digests.items()
        )
    ):
        raise AdjudicatedPreflightError("PREFLIGHT_PHASE8_BINDING_MISMATCH")
    supplied_policies = _string_map(policy_versions, code="PREFLIGHT_POLICY_INVALID")
    reserved_policies = {
        "admission_signature_protocol": (
            f"{ADMISSION_MANIFEST_SCHEMA}:{ADMISSION_SIGNATURE_ALGORITHM}"
        ),
        "controlled_writer": CONTROLLED_CANONICAL_WRITER_POLICY_VERSION,
        "preflight_schema": PREFLIGHT_SCHEMA,
        "protected_state_fingerprint": INITIAL_SUBMISSION_STATE_FINGERPRINT_VERSION,
    }
    if set(supplied_policies) & set(reserved_policies):
        raise AdjudicatedPreflightError("PREFLIGHT_POLICY_INVALID")
    generated_at = _utc_now(now)
    estimate = db.get(Estimate, estimate_id)
    if estimate is None:  # Defensive: initial_submission_state already checked this.
        raise AdjudicatedPreflightError("INITIAL_SUBMISSION_ESTIMATE_MISSING")
    return {
        "schema": PREFLIGHT_SCHEMA,
        "status": PREFLIGHT_STATUS,
        "generated_at": generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "project_id": estimate.project_id,
        "estimate_id": estimate.id,
        "source_run_id": source_run_id,
        "adjudicated_run_id": adjudicated_run_id,
        "canonical_write_performed": False,
        "database_write_performed": False,
        "gateway_call_performed": False,
        "submission_eligible": False,
        "lock_eligible": False,
        "normalised_submission_payload": payload,
        "normalised_submission_payload_sha256": normalised_submission_payload_sha256(payload),
        "protected_state": {
            "fingerprint_version": INITIAL_SUBMISSION_STATE_FINGERPRINT_VERSION,
            "fingerprint": state.fingerprint,
            "counts": dict(sorted(state.counts.items())),
        },
        "artifact_digests": artifact_digests,
        "policy_versions": dict(sorted({**supplied_policies, **reserved_policies}.items())),
        "implementation_hashes": controlled_boundary_implementation_hashes(),
    }


def preflight_receipt_bytes(receipt: Mapping[str, Any]) -> bytes:
    return canonical_json_bytes(dict(receipt))


def parse_adjudicated_preflight(
    raw_receipt: bytes,
    *,
    now: datetime | None = None,
    max_age_seconds: int = DEFAULT_MAX_PREFLIGHT_AGE_SECONDS,
) -> AdjudicatedPreflightBinding:
    if (
        not isinstance(raw_receipt, bytes)
        or not raw_receipt
        or len(raw_receipt) > MAX_PREFLIGHT_RECEIPT_BYTES
    ):
        raise AdjudicatedPreflightError("PREFLIGHT_RECEIPT_INVALID")
    try:
        receipt = json.loads(raw_receipt.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise AdjudicatedPreflightError("PREFLIGHT_RECEIPT_INVALID") from exc
    if not isinstance(receipt, dict) or set(receipt) != _RECEIPT_FIELDS:
        raise AdjudicatedPreflightError("PREFLIGHT_RECEIPT_INVALID")
    if raw_receipt != canonical_json_bytes(receipt):
        raise AdjudicatedPreflightError("PREFLIGHT_RECEIPT_NOT_CANONICAL")
    if receipt["schema"] != PREFLIGHT_SCHEMA or receipt["status"] != PREFLIGHT_STATUS:
        raise AdjudicatedPreflightError("PREFLIGHT_RECEIPT_INVALID")
    for field, expected in (
        ("canonical_write_performed", False),
        ("database_write_performed", False),
        ("gateway_call_performed", False),
        ("submission_eligible", False),
        ("lock_eligible", False),
    ):
        if receipt[field] is not expected:
            raise AdjudicatedPreflightError("PREFLIGHT_RECEIPT_INVALID")

    generated_at = _timestamp(receipt["generated_at"])
    current_time = _utc_now(now)
    if max_age_seconds <= 0 or generated_at > current_time:
        raise AdjudicatedPreflightError("PREFLIGHT_TIME_INVALID")
    if generated_at + timedelta(seconds=max_age_seconds) < current_time:
        raise AdjudicatedPreflightError("PREFLIGHT_EXPIRED")

    project_id = _uuid(receipt["project_id"])
    estimate_id = _uuid(receipt["estimate_id"])
    source_run_id = _identifier(receipt["source_run_id"])
    adjudicated_run_id = _identifier(receipt["adjudicated_run_id"])
    try:
        payload = InitialCanonicalPhysicalSubmission.model_validate(
            receipt["normalised_submission_payload"]
        ).model_dump(mode="json")
    except ValidationError as exc:
        raise AdjudicatedPreflightError("PREFLIGHT_PAYLOAD_INVALID") from exc
    payload_hash = normalised_submission_payload_sha256(payload)
    if not hmac.compare_digest(_sha(receipt["normalised_submission_payload_sha256"]), payload_hash):
        raise AdjudicatedPreflightError("PREFLIGHT_PAYLOAD_INVALID")

    protected_state = receipt["protected_state"]
    if not isinstance(protected_state, dict) or set(protected_state) != {
        "fingerprint_version",
        "fingerprint",
        "counts",
    }:
        raise AdjudicatedPreflightError("PREFLIGHT_RECEIPT_INVALID")
    if protected_state["fingerprint_version"] != INITIAL_SUBMISSION_STATE_FINGERPRINT_VERSION:
        raise AdjudicatedPreflightError("PREFLIGHT_RECEIPT_INVALID")
    protected_fingerprint = _sha(protected_state["fingerprint"])
    counts = protected_state["counts"]
    if not isinstance(counts, dict) or set(counts) != _PROTECTED_COUNT_NAMES or any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in counts.values()
    ):
        raise AdjudicatedPreflightError("PREFLIGHT_RECEIPT_INVALID")
    if any(
        counts[name] != 0
        for name in (
            "opening_count",
            "service_count",
            "service_opening_link_count",
            "active_physical_model_lock_count",
        )
    ):
        raise AdjudicatedPreflightError("PREFLIGHT_CANONICAL_STATE_NOT_EMPTY")

    artifact_digests = _digest_map(receipt["artifact_digests"], code="PREFLIGHT_RECEIPT_INVALID")
    if not REQUIRED_ARTIFACT_NAMES.issubset(artifact_digests):
        raise AdjudicatedPreflightError("PREFLIGHT_ARTIFACT_INVALID")
    policies = _string_map(receipt["policy_versions"], code="PREFLIGHT_RECEIPT_INVALID")
    required_policies = {
        "admission_signature_protocol": (
            f"{ADMISSION_MANIFEST_SCHEMA}:{ADMISSION_SIGNATURE_ALGORITHM}"
        ),
        "controlled_writer": CONTROLLED_CANONICAL_WRITER_POLICY_VERSION,
        "preflight_schema": PREFLIGHT_SCHEMA,
        "protected_state_fingerprint": INITIAL_SUBMISSION_STATE_FINGERPRINT_VERSION,
    }
    if any(policies.get(key) != value for key, value in required_policies.items()):
        raise AdjudicatedPreflightError("PREFLIGHT_POLICY_MISMATCH")
    actual_implementation = _digest_map(
        receipt["implementation_hashes"], code="PREFLIGHT_RECEIPT_INVALID"
    )
    expected_implementation = controlled_boundary_implementation_hashes()
    if actual_implementation != expected_implementation:
        raise AdjudicatedPreflightError("PREFLIGHT_IMPLEMENTATION_MISMATCH")
    bound_artifacts = {
        **artifact_digests,
        "preflight_implementation": sha256_hex(canonical_json_bytes(actual_implementation)),
    }
    return AdjudicatedPreflightBinding(
        receipt_sha256=sha256_hex(raw_receipt),
        project_id=project_id,
        estimate_id=estimate_id,
        source_run_id=source_run_id,
        adjudicated_run_id=adjudicated_run_id,
        submission_payload=payload,
        submission_payload_sha256=payload_hash,
        protected_state_fingerprint=protected_fingerprint,
        protected_state_fingerprint_version=INITIAL_SUBMISSION_STATE_FINGERPRINT_VERSION,
        artifact_digests=dict(sorted(bound_artifacts.items())),
        policy_versions=dict(sorted(policies.items())),
        generated_at=generated_at,
    )


def _artifact_digests(files: Mapping[str, Path]) -> dict[str, str]:
    if not isinstance(files, Mapping) or not files:
        raise AdjudicatedPreflightError("PREFLIGHT_ARTIFACT_INVALID")
    result: dict[str, str] = {}
    for name, path in files.items():
        key = _identifier(name)
        if key == "preflight_implementation" or not isinstance(path, Path) or not path.is_file():
            raise AdjudicatedPreflightError("PREFLIGHT_ARTIFACT_INVALID")
        try:
            size = path.stat().st_size
            if size <= 0 or size > MAX_ARTIFACT_BYTES:
                raise AdjudicatedPreflightError("PREFLIGHT_ARTIFACT_INVALID")
            result[key] = sha256_hex(path.read_bytes())
        except OSError as exc:
            raise AdjudicatedPreflightError("PREFLIGHT_ARTIFACT_INVALID") from exc
    if len(result) != len(files):
        raise AdjudicatedPreflightError("PREFLIGHT_ARTIFACT_INVALID")
    if not REQUIRED_ARTIFACT_NAMES.issubset(result):
        raise AdjudicatedPreflightError("PREFLIGHT_ARTIFACT_INVALID")
    return dict(sorted(result.items()))


def _require_payload_artifact_matches(path: Path, *, expected_payload: dict[str, Any]) -> None:
    try:
        artifact_payload = json.loads(path.read_text(encoding="utf-8"))
        parsed = InitialCanonicalPhysicalSubmission.model_validate(artifact_payload).model_dump(
            mode="json"
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
        raise AdjudicatedPreflightError("PREFLIGHT_PAYLOAD_ARTIFACT_INVALID") from exc
    if parsed != expected_payload:
        raise AdjudicatedPreflightError("PREFLIGHT_PAYLOAD_ARTIFACT_MISMATCH")


def _digest_map(value: object, *, code: str) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise AdjudicatedPreflightError(code)
    result = {_identifier(key): _sha(item) for key, item in value.items()}
    if len(result) != len(value):
        raise AdjudicatedPreflightError(code)
    return dict(sorted(result.items()))


def _string_map(value: object, *, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise AdjudicatedPreflightError(code)
    try:
        result = {_identifier(key): _identifier(item) for key, item in value.items()}
    except AdjudicatedPreflightError as exc:
        raise AdjudicatedPreflightError(code) from exc
    if len(result) != len(value):
        raise AdjudicatedPreflightError(code)
    return dict(sorted(result.items()))


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _identifier(value: object) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise AdjudicatedPreflightError("PREFLIGHT_IDENTIFIER_INVALID")
    return value


def _sha(value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise AdjudicatedPreflightError("PREFLIGHT_DIGEST_INVALID")
    return value


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise AdjudicatedPreflightError("PREFLIGHT_IDENTIFIER_INVALID")
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise AdjudicatedPreflightError("PREFLIGHT_IDENTIFIER_INVALID") from exc


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise AdjudicatedPreflightError("PREFLIGHT_TIME_INVALID")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise AdjudicatedPreflightError("PREFLIGHT_TIME_INVALID") from exc


def _utc_now(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        raise AdjudicatedPreflightError("PREFLIGHT_TIME_INVALID")
    return current.astimezone(UTC).replace(microsecond=0)


__all__ = [
    "AdjudicatedPreflightBinding",
    "AdjudicatedPreflightError",
    "PREFLIGHT_SCHEMA",
    "PREFLIGHT_STATUS",
    "build_adjudicated_preflight",
    "controlled_boundary_implementation_hashes",
    "parse_adjudicated_preflight",
    "preflight_receipt_bytes",
]
