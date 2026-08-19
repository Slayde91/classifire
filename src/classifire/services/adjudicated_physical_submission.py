"""Admission-bound, one-shot writer for an adjudicated initial physical model.

This service never performs model inference and never creates a Physical Model
Lock.  Its only write is an already-signed, preflight-bound canonical model,
under one exclusive transaction.  It deliberately has no HTTP route for
creating admissions: governance must issue and register a signed bundle through
an independently controlled process.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from .. import canonical_models as canonical_models_module
from .. import commercial_models as commercial_models_module
from .. import models as models_module
from .. import physical_model_submission_schema as physical_model_schema_module
from ..audit import record_audit
from ..canonical_models import (
    Defect,
    PhysicalModelAdmission,
    PhysicalModelInitialSubmission,
    ServiceOpeningLink,
)
from ..models import Estimate, Opening, Service
from ..physical_model_submission_schema import AgentInitialPhysicalModelInput
from . import adjudicated_admission as adjudicated_admission_module
from . import canonical_submission_state as canonical_submission_state_module
from . import physical_scope as physical_scope_module
from . import protected_state_fingerprint as protected_state_module
from . import workflow as workflow_module
from . import workflow_db as workflow_db_module
from . import workflow_guard as workflow_guard_module
from .adjudicated_admission import (
    ADJUDICATED_ADMISSION_P256_MANIFEST_SCHEMA,
    ADJUDICATED_ADMISSION_P256_SIGNATURE_ALGORITHM,
    AdmissionVerificationError,
    ParsedAdjudicatedAdmission,
    VerifiedAdjudicatedAdmission,
    normalised_submission_payload_bytes,
    normalised_submission_payload_sha256,
    parse_adjudicated_admission_manifest,
    sha256_hex,
    verify_adjudicated_admission,
)
from .canonical_submission_state import (
    CanonicalSubmissionStateError,
    assess_empty_initial_submission_state,
)
from .protected_state_fingerprint import (
    PROTECTED_STATE_FINGERPRINT_VERSION,
    canonical_sha256,
    protected_state_fingerprint,
    protected_state_snapshot_from_session,
)

CONTROLLED_CANONICAL_WRITER_POLICY_VERSION = "CLASSIFIRE-ADJUDICATED-CANONICAL-WRITER-v5"
CONTROLLED_SUBMISSION_RECEIPT_SCHEMA = "CLASSIFIRE-ADJUDICATED-CANONICAL-SUBMISSION-v1"
PREFLIGHT_SCHEMA = "CLASSIFIRE-ADJUDICATED-CANONICALISATION-PREFLIGHT-v2"
PREFLIGHT_STATUS = "PRECHECK_PASSED_SIGNED_ADMISSION_REQUIRED"
MAX_PREFLIGHT_RECEIPT_BYTES = 5 * 1024 * 1024


class ControlledPhysicalSubmissionError(RuntimeError):
    """Sanitised error for an admission-bound canonical submission attempt."""

    def __init__(
        self,
        code: str,
        *,
        consume_admission: bool = False,
        terminal_state: str = "rejected",
    ) -> None:
        self.code = code
        self.consume_admission = consume_admission
        self.terminal_state = terminal_state
        super().__init__(f"Controlled canonical submission failed: {code}.")


@dataclass(frozen=True)
class PreflightAdmissionBinding:
    raw_sha256: str
    raw_text: str
    project_id: str
    estimate_id: str
    payload: dict[str, Any]
    payload_sha256: str
    protected_state_fingerprint: str
    protected_state_fingerprint_version: str
    protected_component_fingerprints: dict[str, str]
    protected_counts: dict[str, int]
    source_run_id: str
    adjudicated_run_id: str
    artifact_digests: dict[str, str]
    policy_versions: dict[str, str]


@dataclass(frozen=True)
class ControlledSubmissionResult:
    submission_id: str
    admission_id: str
    estimate_id: str
    receipt: dict[str, Any]
    replayed: bool


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(_: str) -> None:
    raise ValueError("non-JSON numeric constant")


def _parse_json_object(raw: bytes | str, *, code: str, limit: int) -> tuple[dict[str, Any], str]:
    if isinstance(raw, bytes):
        if not raw or len(raw) > limit:
            raise ControlledPhysicalSubmissionError(code)
        try:
            text_value = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ControlledPhysicalSubmissionError(code) from exc
    elif isinstance(raw, str):
        try:
            encoded = raw.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ControlledPhysicalSubmissionError(code) from exc
        if not encoded or len(encoded) > limit:
            raise ControlledPhysicalSubmissionError(code)
        text_value = raw
    else:  # pragma: no cover - static caller contract.
        raise ControlledPhysicalSubmissionError(code)
    try:
        value = json.loads(
            text_value,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError, RecursionError) as exc:
        raise ControlledPhysicalSubmissionError(code) from exc
    if not isinstance(value, dict):
        raise ControlledPhysicalSubmissionError(code)
    return value, text_value


def _require_mapping(value: Any, *, code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ControlledPhysicalSubmissionError(code)
    return value


def _require_bool(value: Any, *, expected: bool, code: str) -> None:
    if value is not expected:
        raise ControlledPhysicalSubmissionError(code)


def _require_string(value: Any, *, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ControlledPhysicalSubmissionError(code)
    return value


def _sha256_text(value: str) -> str:
    return sha256_hex(value.encode("utf-8"))


def _sha256_file(path: Path) -> str:
    try:
        return sha256_hex(path.read_bytes())
    except OSError as exc:
        raise ControlledPhysicalSubmissionError("PREFLIGHT_IMPLEMENTATION_UNAVAILABLE") from exc


def controlled_writer_implementation_hashes() -> dict[str, str]:
    repository_root = Path(__file__).resolve().parents[3]
    modules = {
        # The no-write preflight is part of the admission boundary.  Its
        # receipt must not remain usable after that script changes, even when
        # the writer modules themselves are unchanged.
        "preflight_script_sha256": repository_root
        / "scripts"
        / "preflight_adjudicated_canonicalisation.py",
        "controlled_writer_module_sha256": Path(__file__),
        "protected_state_fingerprint_module_sha256": Path(protected_state_module.__file__ or ""),
        "adjudicated_admission_module_sha256": Path(adjudicated_admission_module.__file__ or ""),
        "canonical_submission_state_module_sha256": Path(
            canonical_submission_state_module.__file__ or ""
        ),
        "physical_model_submission_schema_module_sha256": Path(
            physical_model_schema_module.__file__ or ""
        ),
        "canonical_models_module_sha256": Path(canonical_models_module.__file__ or ""),
        "canonical_models_data_module_sha256": Path(models_module.__file__ or ""),
        "commercial_models_module_sha256": Path(commercial_models_module.__file__ or ""),
        "physical_scope_module_sha256": Path(physical_scope_module.__file__ or ""),
        "workflow_module_sha256": Path(workflow_module.__file__ or ""),
        "workflow_db_module_sha256": Path(workflow_db_module.__file__ or ""),
        "workflow_guard_module_sha256": Path(workflow_guard_module.__file__ or ""),
    }
    if any(not path.is_file() for path in modules.values()):
        raise ControlledPhysicalSubmissionError("PREFLIGHT_IMPLEMENTATION_UNAVAILABLE")
    return {key: _sha256_file(path) for key, path in modules.items()}


def preflight_admission_binding(raw_receipt: bytes | str) -> PreflightAdmissionBinding:
    """Strictly derive the signed bindings from one freshly generated preflight."""

    receipt, raw_text = _parse_json_object(
        raw_receipt,
        code="PREFLIGHT_RECEIPT_INVALID",
        limit=MAX_PREFLIGHT_RECEIPT_BYTES,
    )
    if receipt.get("schema") != PREFLIGHT_SCHEMA or receipt.get("status") != PREFLIGHT_STATUS:
        raise ControlledPhysicalSubmissionError("PREFLIGHT_RECEIPT_INVALID")
    for key, expected in (
        ("canonical_write_performed", False),
        ("database_write_performed", False),
        ("gateway_call_performed", False),
        ("candidate_eligible", True),
        ("submission_eligible", False),
        ("lock_eligible", False),
        ("controlled_writer_implemented", True),
    ):
        _require_bool(receipt.get(key), expected=expected, code="PREFLIGHT_RECEIPT_INVALID")
    if (
        receipt.get("controlled_writer_policy_version")
        != CONTROLLED_CANONICAL_WRITER_POLICY_VERSION
    ):
        raise ControlledPhysicalSubmissionError("PREFLIGHT_RECEIPT_INVALID")

    project_id = _require_string(receipt.get("project_id"), code="PREFLIGHT_RECEIPT_INVALID")
    estimate_id = _require_string(receipt.get("estimate_id"), code="PREFLIGHT_RECEIPT_INVALID")

    payload_value = _require_mapping(
        receipt.get("normalised_submission_payload"), code="PREFLIGHT_RECEIPT_INVALID"
    )
    try:
        parsed_payload = AgentInitialPhysicalModelInput.model_validate(payload_value)
    except ValidationError as exc:
        raise ControlledPhysicalSubmissionError("PREFLIGHT_PAYLOAD_INVALID") from exc
    payload = parsed_payload.model_dump(mode="json")
    payload_sha256 = normalised_submission_payload_sha256(payload)
    if not hmac.compare_digest(
        _require_string(
            receipt.get("normalised_submission_payload_sha256"), code="PREFLIGHT_RECEIPT_INVALID"
        ),
        payload_sha256,
    ):
        raise ControlledPhysicalSubmissionError("PREFLIGHT_PAYLOAD_INVALID")

    protected = _require_mapping(receipt.get("protected_state"), code="PREFLIGHT_RECEIPT_INVALID")
    fingerprint = _require_string(protected.get("fingerprint"), code="PREFLIGHT_RECEIPT_INVALID")
    fingerprint_version = _require_string(
        protected.get("fingerprint_version"), code="PREFLIGHT_RECEIPT_INVALID"
    )
    if fingerprint_version != PROTECTED_STATE_FINGERPRINT_VERSION:
        raise ControlledPhysicalSubmissionError("PREFLIGHT_RECEIPT_INVALID")
    component_fingerprints = _require_mapping(
        protected.get("component_fingerprints"), code="PREFLIGHT_RECEIPT_INVALID"
    )
    counts = _require_mapping(protected.get("counts"), code="PREFLIGHT_RECEIPT_INVALID")
    if any(not isinstance(value, str) for value in component_fingerprints.values()) or any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in counts.values()
    ):
        raise ControlledPhysicalSubmissionError("PREFLIGHT_RECEIPT_INVALID")

    source_run_id = _require_string(receipt.get("source_run_id"), code="PREFLIGHT_RECEIPT_INVALID")
    adjudicated_run_id = _require_string(
        receipt.get("adjudicated_receipt_run_id"), code="PREFLIGHT_RECEIPT_INVALID"
    )
    artifact_references = _require_mapping(
        receipt.get("artifact_references"), code="PREFLIGHT_RECEIPT_INVALID"
    )
    full_resolution = _require_mapping(
        receipt.get("full_resolution_visual_evidence"), code="PREFLIGHT_RECEIPT_INVALID"
    )
    visual_basis = _require_mapping(
        receipt.get("visual_adjudication_basis"), code="PREFLIGHT_RECEIPT_INVALID"
    )
    implementation = _require_mapping(
        receipt.get("implementation"), code="PREFLIGHT_RECEIPT_INVALID"
    )
    for key, expected_hash in controlled_writer_implementation_hashes().items():
        actual_hash = _require_string(implementation.get(key), code="PREFLIGHT_RECEIPT_INVALID")
        if not hmac.compare_digest(actual_hash, expected_hash):
            raise ControlledPhysicalSubmissionError("PREFLIGHT_IMPLEMENTATION_MISMATCH")
    artifact_digests = {
        "preflight_artifact_references": canonical_sha256(artifact_references),
        "preflight_full_resolution_evidence": canonical_sha256(full_resolution),
        "preflight_implementation": canonical_sha256(implementation),
        "preflight_visual_adjudication_basis": canonical_sha256(visual_basis),
    }
    policy_versions = {
        "admission_signature_protocol": (
            f"{ADJUDICATED_ADMISSION_P256_MANIFEST_SCHEMA}:"
            f"{ADJUDICATED_ADMISSION_P256_SIGNATURE_ALGORITHM}"
        ),
        "controlled_writer": CONTROLLED_CANONICAL_WRITER_POLICY_VERSION,
        "preflight_schema": PREFLIGHT_SCHEMA,
        "protected_state_fingerprint": fingerprint_version,
    }
    return PreflightAdmissionBinding(
        raw_sha256=_sha256_text(raw_text),
        raw_text=raw_text,
        project_id=project_id,
        estimate_id=estimate_id,
        payload=payload,
        payload_sha256=payload_sha256,
        protected_state_fingerprint=fingerprint,
        protected_state_fingerprint_version=fingerprint_version,
        protected_component_fingerprints={
            str(key): str(value) for key, value in component_fingerprints.items()
        },
        protected_counts={str(key): int(value) for key, value in counts.items()},
        source_run_id=source_run_id,
        adjudicated_run_id=adjudicated_run_id,
        artifact_digests=artifact_digests,
        policy_versions=policy_versions,
    )


def _canonical_manifest_text(
    manifest: Mapping[str, Any] | bytes | str,
) -> tuple[dict[str, Any], str]:
    if isinstance(manifest, Mapping):
        source = dict(manifest)
    else:
        source, _ = _parse_json_object(
            manifest,
            code="ADMISSION_MANIFEST_INVALID",
            limit=128 * 1024,
        )
    try:
        encoded = normalised_submission_payload_bytes(source)
    except AdmissionVerificationError as exc:
        raise ControlledPhysicalSubmissionError(exc.code) from exc
    canonical_text = encoded.decode("utf-8")
    parsed, _ = _parse_json_object(
        canonical_text,
        code="ADMISSION_MANIFEST_INVALID",
        limit=128 * 1024,
    )
    return parsed, canonical_text


def _trusted_signer(
    parsed: ParsedAdjudicatedAdmission,
    *,
    pinned_public_keys: Mapping[str, str],
    issuer_key_ids: Mapping[str, Collection[str]],
) -> str:
    allowed_key_ids = issuer_key_ids.get(parsed.issuer)
    if (
        not isinstance(allowed_key_ids, Collection)
        or isinstance(allowed_key_ids, (str, bytes))
        or not allowed_key_ids
    ):
        raise ControlledPhysicalSubmissionError("ADMISSION_ISSUER_UNTRUSTED")
    if parsed.key_id not in set(allowed_key_ids):
        raise ControlledPhysicalSubmissionError("ADMISSION_SIGNER_UNTRUSTED")
    pinned_key = pinned_public_keys.get(parsed.key_id)
    if not isinstance(pinned_key, str) or not pinned_key:
        raise ControlledPhysicalSubmissionError("ADMISSION_KEY_UNTRUSTED")
    return pinned_key


def _verify_bundle(
    *,
    manifest: Mapping[str, Any] | bytes | str,
    binding: PreflightAdmissionBinding,
    expected_project_id: str,
    expected_estimate_id: str,
    pinned_public_keys: Mapping[str, str],
    issuer_key_ids: Mapping[str, Collection[str]],
    max_admission_ttl_seconds: int | None,
    now: datetime | None,
) -> tuple[ParsedAdjudicatedAdmission, VerifiedAdjudicatedAdmission]:
    try:
        parsed = parse_adjudicated_admission_manifest(manifest)
    except AdmissionVerificationError as exc:
        raise ControlledPhysicalSubmissionError(exc.code, consume_admission=True) from exc
    if (
        parsed.schema != ADJUDICATED_ADMISSION_P256_MANIFEST_SCHEMA
        or parsed.signature_algorithm != ADJUDICATED_ADMISSION_P256_SIGNATURE_ALGORITHM
    ):
        raise ControlledPhysicalSubmissionError("ADMISSION_PROTOCOL_UNSUPPORTED")
    pinned_key = _trusted_signer(
        parsed,
        pinned_public_keys=pinned_public_keys,
        issuer_key_ids=issuer_key_ids,
    )
    try:
        verified = verify_adjudicated_admission(
            manifest,
            pinned_public_key=pinned_key,
            expected_project_id=expected_project_id,
            expected_estimate_id=expected_estimate_id,
            expected_preflight_receipt_sha256=binding.raw_sha256,
            submission_payload=binding.payload,
            expected_protected_state_fingerprint=binding.protected_state_fingerprint,
            expected_protected_state_fingerprint_version=binding.protected_state_fingerprint_version,
            expected_artifact_digests=binding.artifact_digests,
            expected_policy_versions=binding.policy_versions,
            expected_source_run_id=binding.source_run_id,
            expected_adjudicated_run_id=binding.adjudicated_run_id,
            expected_issuer=parsed.issuer,
            expected_key_id=parsed.key_id,
            max_ttl_seconds=max_admission_ttl_seconds,
            now=now,
        )
    except AdmissionVerificationError as exc:
        if exc.code in {"ADMISSION_VERIFIER_UNAVAILABLE", "ADMISSION_PINNED_KEY_INVALID"}:
            raise ControlledPhysicalSubmissionError(exc.code) from exc
        terminal_state = "expired" if exc.code == "ADMISSION_EXPIRED" else "rejected"
        raise ControlledPhysicalSubmissionError(
            exc.code,
            consume_admission=True,
            terminal_state=terminal_state,
        ) from exc
    return parsed, verified


def register_adjudicated_admission(
    db: Session,
    *,
    manifest: Mapping[str, Any] | bytes | str,
    preflight_receipt_bytes: bytes,
    pinned_public_keys: Mapping[str, str],
    issuer_key_ids: Mapping[str, Collection[str]],
    max_admission_ttl_seconds: int | None = 900,
    now: datetime | None = None,
) -> PhysicalModelAdmission:
    """Persist one verified signed bundle through a non-HTTP governance process.

    Callers must commit explicitly.  There is intentionally no route that turns
    an arbitrary agent request into a signed admission.
    """

    binding = preflight_admission_binding(preflight_receipt_bytes)
    manifest_object, manifest_text = _canonical_manifest_text(manifest)
    parsed, verified = _verify_bundle(
        manifest=manifest_object,
        binding=binding,
        expected_project_id=binding.project_id,
        expected_estimate_id=binding.estimate_id,
        pinned_public_keys=pinned_public_keys,
        issuer_key_ids=issuer_key_ids,
        max_admission_ttl_seconds=max_admission_ttl_seconds,
        now=now,
    )
    estimate = db.get(Estimate, binding.estimate_id)
    if estimate is None or estimate.project_id != verified.project_id:
        raise ControlledPhysicalSubmissionError("ADMISSION_ESTIMATE_MISMATCH")
    existing = db.scalar(
        select(PhysicalModelAdmission).where(
            PhysicalModelAdmission.admission_id == verified.admission_id
        )
    )
    if existing is not None:
        if (
            hmac.compare_digest(
                existing.admission_envelope_sha256,
                verified.canonical_manifest_sha256,
            )
            and hmac.compare_digest(existing.preflight_receipt_sha256, binding.raw_sha256)
            and hmac.compare_digest(
                existing.normalised_submission_payload_sha256, binding.payload_sha256
            )
        ):
            return existing
        raise ControlledPhysicalSubmissionError("ADMISSION_ID_CONFLICT")

    payload_bytes = normalised_submission_payload_bytes(binding.payload)
    admission = PhysicalModelAdmission(
        admission_id=verified.admission_id,
        project_id=verified.project_id,
        estimate_id=verified.estimate_id,
        purpose=verified.purpose,
        preflight_receipt_sha256=binding.raw_sha256,
        normalised_submission_payload_sha256=binding.payload_sha256,
        protected_state_fingerprint=verified.protected_state_fingerprint,
        protected_state_fingerprint_version=verified.protected_state_fingerprint_version,
        source_run_id=verified.source_run_id,
        adjudicated_run_id=verified.adjudicated_run_id,
        artifact_manifest_sha256=canonical_sha256(dict(verified.artifact_digests)),
        implementation_manifest_sha256=canonical_sha256(dict(verified.policy_versions)),
        admission_envelope_json=manifest_text,
        admission_envelope_sha256=verified.canonical_manifest_sha256,
        preflight_receipt_json=binding.raw_text,
        normalised_submission_payload_json=payload_bytes.decode("utf-8"),
        issuer_id=verified.issuer,
        signing_key_id=verified.key_id,
        signature_algorithm=ADJUDICATED_ADMISSION_P256_SIGNATURE_ALGORITHM,
        signature=str(manifest_object["signature"]),
        issued_at=verified.issued_at,
        expires_at=verified.expires_at,
        state="issued",
    )
    db.add(admission)
    db.flush()
    return admission


def _normalise_db_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _admission_matches_verified(
    admission: PhysicalModelAdmission,
    *,
    binding: PreflightAdmissionBinding,
    verified: VerifiedAdjudicatedAdmission,
) -> bool:
    fields = (
        (admission.admission_id, verified.admission_id),
        (admission.project_id, verified.project_id),
        (admission.estimate_id, verified.estimate_id),
        (admission.purpose, verified.purpose),
        (admission.preflight_receipt_sha256, binding.raw_sha256),
        (admission.normalised_submission_payload_sha256, binding.payload_sha256),
        (admission.protected_state_fingerprint, verified.protected_state_fingerprint),
        (
            admission.protected_state_fingerprint_version,
            verified.protected_state_fingerprint_version,
        ),
        (admission.source_run_id, verified.source_run_id),
        (admission.adjudicated_run_id, verified.adjudicated_run_id),
        (admission.issuer_id, verified.issuer),
        (admission.signing_key_id, verified.key_id),
        (admission.signature_algorithm, ADJUDICATED_ADMISSION_P256_SIGNATURE_ALGORITHM),
        (admission.admission_envelope_sha256, verified.canonical_manifest_sha256),
        (admission.artifact_manifest_sha256, canonical_sha256(dict(verified.artifact_digests))),
        (
            admission.implementation_manifest_sha256,
            canonical_sha256(dict(verified.policy_versions)),
        ),
    )
    if not all(hmac.compare_digest(str(actual), str(expected)) for actual, expected in fields):
        return False
    return (
        _normalise_db_datetime(admission.issued_at) == verified.issued_at
        and _normalise_db_datetime(admission.expires_at) == verified.expires_at
    )


def _validate_persisted_admission(
    admission: PhysicalModelAdmission,
    *,
    estimate: Estimate,
    pinned_public_keys: Mapping[str, str],
    issuer_key_ids: Mapping[str, Collection[str]],
    max_admission_ttl_seconds: int | None,
    now: datetime | None,
) -> tuple[PreflightAdmissionBinding, dict[str, Any], VerifiedAdjudicatedAdmission]:
    binding = preflight_admission_binding(admission.preflight_receipt_json.encode("utf-8"))
    if binding.estimate_id != estimate.id or binding.project_id != estimate.project_id:
        raise ControlledPhysicalSubmissionError(
            "ADMISSION_BINDING_MISMATCH", consume_admission=True
        )
    payload_value, _ = _parse_json_object(
        admission.normalised_submission_payload_json,
        code="ADMISSION_PAYLOAD_INVALID",
        limit=5 * 1024 * 1024,
    )
    try:
        payload = AgentInitialPhysicalModelInput.model_validate(payload_value).model_dump(
            mode="json"
        )
    except ValidationError as exc:
        raise ControlledPhysicalSubmissionError(
            "ADMISSION_PAYLOAD_INVALID", consume_admission=True
        ) from exc
    if payload != binding.payload or not hmac.compare_digest(
        normalised_submission_payload_sha256(payload), binding.payload_sha256
    ):
        raise ControlledPhysicalSubmissionError(
            "ADMISSION_BINDING_MISMATCH", consume_admission=True
        )

    manifest, _ = _parse_json_object(
        admission.admission_envelope_json,
        code="ADMISSION_MANIFEST_INVALID",
        limit=128 * 1024,
    )
    parsed, verified = _verify_bundle(
        manifest=manifest,
        binding=binding,
        expected_project_id=estimate.project_id,
        expected_estimate_id=estimate.id,
        pinned_public_keys=pinned_public_keys,
        issuer_key_ids=issuer_key_ids,
        max_admission_ttl_seconds=max_admission_ttl_seconds,
        now=now,
    )
    if parsed.admission_id != admission.admission_id or not _admission_matches_verified(
        admission, binding=binding, verified=verified
    ):
        raise ControlledPhysicalSubmissionError(
            "ADMISSION_BINDING_MISMATCH", consume_admission=True
        )
    return binding, payload, verified


def _idempotency_hash(value: str) -> str:
    if not isinstance(value, str) or len(value) < 16 or len(value) > 200 or not value.strip():
        raise ControlledPhysicalSubmissionError("IDEMPOTENCY_KEY_INVALID")
    return hashlib.sha256(value.encode("utf-8")).hexdigest().upper()


def _begin_exclusive_transaction(db: Session) -> None:
    if db.in_transaction():
        raise ControlledPhysicalSubmissionError("SUBMISSION_SESSION_NOT_CLEAN")
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        try:
            db.execute(text("BEGIN IMMEDIATE"))
        except OperationalError as exc:
            db.rollback()
            raise ControlledPhysicalSubmissionError("SUBMISSION_CONCURRENT_RETRY_REQUIRED") from exc
        return
    if dialect == "postgresql":
        try:
            db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
        except OperationalError as exc:
            db.rollback()
            raise ControlledPhysicalSubmissionError("SUBMISSION_CONCURRENT_RETRY_REQUIRED") from exc
        return
    raise ControlledPhysicalSubmissionError("SUBMISSION_DATABASE_DIALECT_UNSUPPORTED")


def _locked_statement(statement: Any, db: Session) -> Any:
    if db.get_bind().dialect.name == "postgresql":
        return statement.with_for_update()
    return statement


def _require_existing_defect_map(db: Session, *, estimate_id: str) -> dict[str, Defect]:
    defects = list(db.scalars(select(Defect).where(Defect.estimate_id == estimate_id)).all())
    result: dict[str, Defect] = {}
    for defect in defects:
        external_id = defect.external_defect_id
        if not isinstance(external_id, str) or not external_id.strip() or external_id in result:
            raise ControlledPhysicalSubmissionError("RETAINED_DEFECT_BINDING_INVALID")
        result[external_id] = defect
    if not result:
        raise ControlledPhysicalSubmissionError("RETAINED_DEFECT_BINDING_INVALID")
    return result


def _create_canonical_model(
    db: Session,
    *,
    estimate: Estimate,
    payload: dict[str, Any],
) -> tuple[list[Opening], list[Service], list[ServiceOpeningLink]]:
    try:
        parsed = AgentInitialPhysicalModelInput.model_validate(payload)
    except ValidationError as exc:  # pragma: no cover - checked before this call.
        raise ControlledPhysicalSubmissionError("ADMISSION_PAYLOAD_INVALID") from exc
    opening_codes = [item.opening_code for item in parsed.openings]
    service_codes = [item.service_code for item in parsed.services]
    if len(set(opening_codes)) != len(opening_codes) or len(set(service_codes)) != len(
        service_codes
    ):
        raise ControlledPhysicalSubmissionError("ADMISSION_PAYLOAD_INVALID")
    defect_by_external_id = _require_existing_defect_map(db, estimate_id=estimate.id)
    openings_by_code: dict[str, Opening] = {}
    openings: list[Opening] = []
    for item in parsed.openings:
        if not item.external_defect_id or item.external_defect_id not in defect_by_external_id:
            raise ControlledPhysicalSubmissionError("RETAINED_DEFECT_BINDING_INVALID")
        defect = defect_by_external_id[item.external_defect_id]
        opening = Opening(
            estimate_id=estimate.id,
            defect_id=defect.external_defect_id,
            canonical_defect_id=defect.id,
            opening_code=item.opening_code,
            location=item.location,
            substrate_type=item.substrate_type,
            substrate_plane=item.substrate_plane,
            substrate_thickness_mm=item.substrate_thickness_mm,
            orientation=item.orientation,
            opening_type=item.opening_type,
            width_mm=item.width_mm,
            height_mm=item.height_mm,
            diameter_mm=item.diameter_mm,
            frl=item.frl,
            physical_model_status="modelled",
            technical_status="not_assessed",
            notes=item.notes,
        )
        db.add(opening)
        db.flush()
        openings_by_code[item.opening_code] = opening
        openings.append(opening)

    services: list[Service] = []
    links: list[ServiceOpeningLink] = []
    for item in parsed.services:
        if item.primary_opening_code not in openings_by_code:
            raise ControlledPhysicalSubmissionError("ADMISSION_PAYLOAD_INVALID")
        requested_codes = list(item.opening_codes)
        if item.primary_opening_code not in requested_codes or any(
            code not in openings_by_code for code in requested_codes
        ):
            raise ControlledPhysicalSubmissionError("ADMISSION_PAYLOAD_INVALID")
        primary = openings_by_code[item.primary_opening_code]
        service = Service(
            opening_id=primary.id,
            service_code=item.service_code,
            service_type=item.service_type,
            material=item.material,
            nominal_size_mm=item.nominal_size_mm,
            outside_diameter_mm=item.outside_diameter_mm,
            width_mm=item.width_mm,
            height_mm=item.height_mm,
            insulation_type=item.insulation_type,
            insulation_thickness_mm=item.insulation_thickness_mm,
            quantity=item.quantity,
            centre_x_mm=item.centre_x_mm,
            centre_y_mm=item.centre_y_mm,
            evidence_status=item.evidence_status,
            confidence=item.confidence,
            notes=item.notes,
        )
        db.add(service)
        db.flush()
        services.append(service)
        for opening_code in requested_codes:
            link = ServiceOpeningLink(
                service_id=service.id,
                opening_id=openings_by_code[opening_code].id,
                link_type=item.link_type,
                relationship_status=item.relationship_status,
                evidence_status=item.evidence_status,
                confidence=item.confidence,
                source_reference=item.source_reference,
                notes=item.notes,
            )
            db.add(link)
            links.append(link)
    db.flush()
    return openings, services, links


def _submission_receipt(
    *,
    admission: PhysicalModelAdmission,
    estimate: Estimate,
    fingerprint_before: str,
    fingerprint_after: str,
    openings: list[Opening],
    services: list[Service],
    links: list[ServiceOpeningLink],
) -> dict[str, Any]:
    return {
        "schema": CONTROLLED_SUBMISSION_RECEIPT_SCHEMA,
        "status": "COMMITTED_NO_LOCK",
        "admission_id": admission.admission_id,
        "estimate_id": estimate.id,
        "project_id": estimate.project_id,
        "preflight_receipt_sha256": admission.preflight_receipt_sha256,
        "normalised_submission_payload_sha256": admission.normalised_submission_payload_sha256,
        "protected_state_fingerprint_version": admission.protected_state_fingerprint_version,
        "protected_state_fingerprint_before": fingerprint_before,
        "protected_state_fingerprint_after": fingerprint_after,
        "opening_count": len(openings),
        "service_count": len(services),
        "service_opening_link_count": len(links),
        "physical_model_lock_created": False,
        "gateway_call_performed": False,
        "openings": [
            {
                "id": row.id,
                "opening_code": row.opening_code,
                "canonical_defect_id": row.canonical_defect_id,
            }
            for row in sorted(openings, key=lambda row: row.opening_code)
        ],
        "services": [
            {"id": row.id, "service_code": row.service_code, "quantity": str(row.quantity)}
            for row in sorted(services, key=lambda row: row.service_code)
        ],
    }


def _replay_result(
    submission: PhysicalModelInitialSubmission, admission_id: str
) -> ControlledSubmissionResult:
    receipt, _ = _parse_json_object(
        submission.submission_receipt_json,
        code="SUBMISSION_RECEIPT_INVALID",
        limit=5 * 1024 * 1024,
    )
    if not hmac.compare_digest(
        sha256_hex(submission.submission_receipt_json.encode("utf-8")),
        submission.submission_receipt_sha256,
    ):
        raise ControlledPhysicalSubmissionError("SUBMISSION_RECEIPT_INVALID")
    return ControlledSubmissionResult(
        submission_id=submission.id,
        admission_id=admission_id,
        estimate_id=submission.estimate_id,
        receipt=receipt,
        replayed=True,
    )


def _mark_rejected(
    admission: PhysicalModelAdmission,
    *,
    error: ControlledPhysicalSubmissionError,
    idempotency_hash: str,
    principal_id: str,
    now: datetime,
) -> None:
    admission.state = error.terminal_state
    admission.claim_idempotency_key_hash = idempotency_hash
    admission.claimed_by_agent_principal_id = principal_id
    admission.claimed_at = now
    admission.resolved_at = now
    admission.resolution_code = error.code
    admission.resolution_receipt_sha256 = sha256_hex(error.code.encode("utf-8"))


def execute_adjudicated_initial_submission(
    db: Session,
    *,
    estimate_id: str,
    admission_id: str,
    idempotency_key: str,
    principal_id: str,
    principal_agent_id: str,
    pinned_public_keys: Mapping[str, str],
    issuer_key_ids: Mapping[str, Collection[str]],
    max_admission_ttl_seconds: int | None = 900,
    now: datetime | None = None,
) -> ControlledSubmissionResult:
    """Atomically create the exact signed model or fail without canonical rows."""

    idempotency_hash = _idempotency_hash(idempotency_key)
    timestamp = (now or datetime.now(UTC)).astimezone(UTC)
    admission: PhysicalModelAdmission | None = None
    write_started = False
    _begin_exclusive_transaction(db)
    try:
        existing = db.scalar(
            _locked_statement(
                select(PhysicalModelInitialSubmission)
                .join(
                    PhysicalModelAdmission,
                    PhysicalModelInitialSubmission.admission_record_id == PhysicalModelAdmission.id,
                )
                .where(PhysicalModelAdmission.admission_id == admission_id),
                db,
            )
        )
        if existing is not None:
            if existing.estimate_id != estimate_id:
                raise ControlledPhysicalSubmissionError("ADMISSION_ESTIMATE_MISMATCH")
            if not hmac.compare_digest(existing.idempotency_key_hash, idempotency_hash):
                raise ControlledPhysicalSubmissionError("SUBMISSION_IDEMPOTENCY_CONFLICT")
            result = _replay_result(existing, admission_id)
            db.rollback()
            return result

        admission = db.scalar(
            _locked_statement(
                select(PhysicalModelAdmission).where(
                    PhysicalModelAdmission.admission_id == admission_id
                ),
                db,
            )
        )
        if admission is None:
            raise ControlledPhysicalSubmissionError("ADMISSION_NOT_FOUND")
        if admission.estimate_id != estimate_id:
            raise ControlledPhysicalSubmissionError(
                "ADMISSION_ESTIMATE_MISMATCH", consume_admission=True
            )
        if admission.state != "issued":
            raise ControlledPhysicalSubmissionError("ADMISSION_ALREADY_RESOLVED")

        estimate = db.scalar(
            _locked_statement(select(Estimate).where(Estimate.id == estimate_id), db)
        )
        if estimate is None:
            raise ControlledPhysicalSubmissionError("ESTIMATE_NOT_FOUND", consume_admission=True)
        binding, payload, _verified = _validate_persisted_admission(
            admission,
            estimate=estimate,
            pinned_public_keys=pinned_public_keys,
            issuer_key_ids=issuer_key_ids,
            max_admission_ttl_seconds=max_admission_ttl_seconds,
            now=timestamp,
        )
        try:
            state = assess_empty_initial_submission_state(
                db,
                estimate_id=estimate.id,
                expected_fingerprint=binding.protected_state_fingerprint,
                expected_component_fingerprints=binding.protected_component_fingerprints,
                expected_counts=binding.protected_counts,
            )
        except CanonicalSubmissionStateError as exc:
            raise ControlledPhysicalSubmissionError(
                "ADMISSION_STATE_DRIFT",
                consume_admission=True,
                terminal_state="stale",
            ) from exc
        fingerprint_before = state["protected_state"]["fingerprint"]

        if db.scalar(
            _locked_statement(
                select(PhysicalModelInitialSubmission.id).where(
                    PhysicalModelInitialSubmission.estimate_id == estimate.id
                ),
                db,
            )
        ):
            raise ControlledPhysicalSubmissionError("INITIAL_SUBMISSION_ALREADY_EXISTS")

        admission.state = "claimed"
        admission.claim_idempotency_key_hash = idempotency_hash
        admission.claimed_by_agent_principal_id = principal_id
        admission.claimed_at = timestamp
        db.flush()
        write_started = True
        openings, services, links = _create_canonical_model(db, estimate=estimate, payload=payload)
        fingerprint_after = protected_state_fingerprint(
            protected_state_snapshot_from_session(db, estimate.id)
        )
        receipt = _submission_receipt(
            admission=admission,
            estimate=estimate,
            fingerprint_before=fingerprint_before,
            fingerprint_after=fingerprint_after,
            openings=openings,
            services=services,
            links=links,
        )
        receipt_json = normalised_submission_payload_bytes(receipt).decode("utf-8")
        receipt_sha256 = sha256_hex(receipt_json.encode("utf-8"))
        submission = PhysicalModelInitialSubmission(
            admission_record_id=admission.id,
            project_id=estimate.project_id,
            estimate_id=estimate.id,
            idempotency_key_hash=idempotency_hash,
            preflight_receipt_sha256=binding.raw_sha256,
            normalised_submission_payload_sha256=binding.payload_sha256,
            protected_state_fingerprint_before=fingerprint_before,
            protected_state_fingerprint_after=fingerprint_after,
            protected_state_fingerprint_version=binding.protected_state_fingerprint_version,
            opening_count=len(openings),
            service_count=len(services),
            service_opening_link_count=len(links),
            submission_receipt_sha256=receipt_sha256,
            submission_receipt_json=receipt_json,
            committed_at=timestamp,
        )
        db.add(submission)
        admission.state = "consumed"
        admission.resolved_at = timestamp
        admission.resolution_code = "COMMITTED_NO_LOCK"
        admission.resolution_receipt_sha256 = receipt_sha256
        record_audit(
            db,
            actor=None,
            actor_type="agent",
            actor_name=principal_agent_id,
            action="agent_submit_adjudicated_initial_physical_model",
            entity_type="estimate",
            entity_id=estimate.id,
            project_id=estimate.project_id,
            new_value={
                "admission_id": admission.admission_id,
                "submission_receipt_sha256": receipt_sha256,
                "opening_ids": sorted(row.id for row in openings),
                "service_ids": sorted(row.id for row in services),
                "service_opening_link_count": len(links),
            },
            reason=(
                "Signed, admission-bound adjudicated initial canonical submission; no lock created"
            ),
        )
        db.flush()
        db.commit()
        return ControlledSubmissionResult(
            submission_id=submission.id,
            admission_id=admission.admission_id,
            estimate_id=estimate.id,
            receipt=receipt,
            replayed=False,
        )
    except ControlledPhysicalSubmissionError as exc:
        if admission is not None and exc.consume_admission and not write_started:
            _mark_rejected(
                admission,
                error=exc,
                idempotency_hash=idempotency_hash,
                principal_id=principal_id,
                now=timestamp,
            )
            db.commit()
        else:
            db.rollback()
        raise
    except (IntegrityError, OperationalError) as exc:
        db.rollback()
        raise ControlledPhysicalSubmissionError("SUBMISSION_TRANSACTION_FAILED") from exc
    except Exception as exc:  # Do not leak persistence or artifact internals through the API.
        db.rollback()
        raise ControlledPhysicalSubmissionError("SUBMISSION_TRANSACTION_FAILED") from exc


__all__ = [
    "CONTROLLED_CANONICAL_WRITER_POLICY_VERSION",
    "CONTROLLED_SUBMISSION_RECEIPT_SCHEMA",
    "ControlledPhysicalSubmissionError",
    "ControlledSubmissionResult",
    "controlled_writer_implementation_hashes",
    "PREFLIGHT_SCHEMA",
    "PREFLIGHT_STATUS",
    "PreflightAdmissionBinding",
    "execute_adjudicated_initial_submission",
    "preflight_admission_binding",
    "register_adjudicated_admission",
]
