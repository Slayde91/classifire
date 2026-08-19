"""Offline, human-governed registration of signed physical-model admissions.

This service deliberately records a verified admission only.  It never calls
the controlled writer, creates canonical Openings or Services, creates a
Physical Model Lock, or contacts OpenClaw/Gateway services.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..audit import record_audit
from .adjudicated_admission import MAX_ADMISSION_MANIFEST_BYTES
from .adjudicated_physical_submission import (
    MAX_PREFLIGHT_RECEIPT_BYTES,
    ControlledPhysicalSubmissionError,
    register_adjudicated_admission,
)

OFFLINE_ADMISSION_REGISTRATION_RECEIPT_SCHEMA = "CLASSIFIRE-OFFLINE-ADMISSION-REGISTRATION-v1"
_REQUIRED_JOURNAL_TABLES = frozenset(
    {"physical_model_admissions", "physical_model_initial_submissions"}
)
_ADMISSION_JOURNAL_REVISION = "0006_adjudicated_canonical_admissions"
_OPERATOR_REFERENCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._:/@#-]{2,199}$")


class OfflineAdmissionRegistrationError(RuntimeError):
    """Sanitised failure suitable for an offline human operator."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class OfflineAdmissionRegistrationReceipt:
    """Safe, non-secret result of recording a signed admission."""

    admission_id: str
    project_id: str
    estimate_id: str
    state: str
    issuer: str
    key_id: str
    issued_at: datetime
    expires_at: datetime
    admission_envelope_sha256: str
    preflight_receipt_sha256: str
    normalised_submission_payload_sha256: str
    audit_event_id: str

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "schema": OFFLINE_ADMISSION_REGISTRATION_RECEIPT_SCHEMA,
            "status": "VERIFIED_ADMISSION_RECORDED_NO_MODEL_WRITE",
            "admission_id": self.admission_id,
            "project_id": self.project_id,
            "estimate_id": self.estimate_id,
            "state": self.state,
            "issuer": self.issuer,
            "key_id": self.key_id,
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "admission_envelope_sha256": self.admission_envelope_sha256,
            "preflight_receipt_sha256": self.preflight_receipt_sha256,
            "normalised_submission_payload_sha256": self.normalised_submission_payload_sha256,
            "audit_event_id": self.audit_event_id,
            "canonical_write_performed": False,
            "physical_model_lock_created": False,
            "gateway_call_performed": False,
        }


def read_registration_artifact(
    path: Path,
    *,
    maximum_bytes: int,
    unreadable_code: str,
) -> bytes:
    """Read exactly one bounded input file without exposing its path or bytes."""

    if not isinstance(path, Path) or not isinstance(maximum_bytes, int) or maximum_bytes <= 0:
        raise OfflineAdmissionRegistrationError(unreadable_code)
    try:
        resolved = path.expanduser().resolve(strict=True)
        if not resolved.is_file():
            raise OSError("not a regular file")
        if resolved.stat().st_size <= 0 or resolved.stat().st_size > maximum_bytes:
            raise OSError("input size is outside the permitted bound")
        value = resolved.read_bytes()
    except OSError as exc:
        raise OfflineAdmissionRegistrationError(unreadable_code) from exc
    if not value or len(value) > maximum_bytes:
        raise OfflineAdmissionRegistrationError(unreadable_code)
    return value


def read_admission_manifest(path: Path) -> bytes:
    """Read one bounded signed admission manifest."""

    return read_registration_artifact(
        path,
        maximum_bytes=MAX_ADMISSION_MANIFEST_BYTES,
        unreadable_code="ADMISSION_MANIFEST_UNREADABLE",
    )


def read_preflight_receipt(path: Path) -> bytes:
    """Read one bounded no-write preflight receipt."""

    return read_registration_artifact(
        path,
        maximum_bytes=MAX_PREFLIGHT_RECEIPT_BYTES,
        unreadable_code="PREFLIGHT_RECEIPT_UNREADABLE",
    )


def _require_operator_reference(value: str) -> str:
    if not isinstance(value, str):
        raise OfflineAdmissionRegistrationError("OPERATOR_REFERENCE_INVALID")
    result = value.strip()
    if _OPERATOR_REFERENCE_RE.fullmatch(result) is None:
        raise OfflineAdmissionRegistrationError("OPERATOR_REFERENCE_INVALID")
    return result


def _require_journal_schema(db: Session) -> None:
    try:
        tables = set(inspect(db.get_bind()).get_table_names())
    except SQLAlchemyError as exc:
        raise OfflineAdmissionRegistrationError("ADMISSION_JOURNAL_SCHEMA_UNAVAILABLE") from exc
    if not _REQUIRED_JOURNAL_TABLES.issubset(tables):
        raise OfflineAdmissionRegistrationError("ADMISSION_JOURNAL_SCHEMA_MISSING")
    if "alembic_version" not in tables:
        raise OfflineAdmissionRegistrationError("ADMISSION_JOURNAL_MIGRATION_UNVERIFIED")
    try:
        versions = [
            value
            for value in db.scalars(text("SELECT version_num FROM alembic_version"))
            if isinstance(value, str) and value
        ]
        repository_root = Path(__file__).resolve().parents[3]
        scripts = ScriptDirectory.from_config(Config(str(repository_root / "alembic.ini")))
        migration_applied = any(
            _ADMISSION_JOURNAL_REVISION
            in {item.revision for item in scripts.iterate_revisions(version, "base")}
            for version in versions
        )
    except Exception as exc:
        raise OfflineAdmissionRegistrationError("ADMISSION_JOURNAL_MIGRATION_UNVERIFIED") from exc
    if not migration_applied:
        raise OfflineAdmissionRegistrationError("ADMISSION_JOURNAL_MIGRATION_UNVERIFIED")


def register_offline_adjudicated_admission(
    db: Session,
    *,
    manifest_bytes: bytes,
    preflight_receipt_bytes: bytes,
    operator_reference: str,
    pinned_public_keys: Mapping[str, str],
    issuer_key_ids: Mapping[str, Collection[str]],
    max_admission_ttl_seconds: int | None,
    now: datetime | None = None,
) -> OfflineAdmissionRegistrationReceipt:
    """Verify and persist one signed admission, without creating a model or lock."""

    reference = _require_operator_reference(operator_reference)
    _require_journal_schema(db)
    try:
        admission = register_adjudicated_admission(
            db,
            manifest=manifest_bytes,
            preflight_receipt_bytes=preflight_receipt_bytes,
            pinned_public_keys=pinned_public_keys,
            issuer_key_ids=issuer_key_ids,
            max_admission_ttl_seconds=max_admission_ttl_seconds,
            now=now,
        )
        audit = record_audit(
            db,
            actor=None,
            actor_type="human_governance",
            actor_name=reference,
            action="register_adjudicated_physical_model_admission",
            entity_type="physical_model_admission",
            entity_id=admission.id,
            project_id=admission.project_id,
            new_value={
                "admission_id": admission.admission_id,
                "state": admission.state,
                "issuer": admission.issuer_id,
                "key_id": admission.signing_key_id,
                "admission_envelope_sha256": admission.admission_envelope_sha256,
                "preflight_receipt_sha256": admission.preflight_receipt_sha256,
                "normalised_submission_payload_sha256": (
                    admission.normalised_submission_payload_sha256
                ),
                "canonical_write_performed": False,
                "physical_model_lock_created": False,
                "gateway_call_performed": False,
            },
            reason=(
                "Offline human-governance registration of a verified signed admission; "
                "no model or Physical Model Lock was created."
            ),
        )
        db.flush()
        result = OfflineAdmissionRegistrationReceipt(
            admission_id=admission.admission_id,
            project_id=admission.project_id,
            estimate_id=admission.estimate_id,
            state=admission.state,
            issuer=admission.issuer_id,
            key_id=admission.signing_key_id,
            issued_at=admission.issued_at,
            expires_at=admission.expires_at,
            admission_envelope_sha256=admission.admission_envelope_sha256,
            preflight_receipt_sha256=admission.preflight_receipt_sha256,
            normalised_submission_payload_sha256=admission.normalised_submission_payload_sha256,
            audit_event_id=audit.id,
        )
        db.commit()
        return result
    except ControlledPhysicalSubmissionError:
        db.rollback()
        raise
    except OfflineAdmissionRegistrationError:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise OfflineAdmissionRegistrationError(
            "ADMISSION_REGISTRATION_PERSISTENCE_FAILED"
        ) from exc


__all__ = [
    "OFFLINE_ADMISSION_REGISTRATION_RECEIPT_SCHEMA",
    "OfflineAdmissionRegistrationError",
    "OfflineAdmissionRegistrationReceipt",
    "read_admission_manifest",
    "read_preflight_receipt",
    "register_offline_adjudicated_admission",
]
