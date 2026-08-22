"""Rehearse adjudicated registration and submission on a disposable SQLite copy.

The source database is opened read-only and copied through SQLite's online
backup API.  A synthetic P-256 key exists only in memory for the duration of
the rehearsal.  The signed manifest and disposable database are not retained;
the only durable output is a non-secret summary receipt.
"""

from __future__ import annotations

import argparse
import base64
import json
import sqlite3
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import Engine, create_engine, event, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from classifire.agent_security import provision_agent_principal
from classifire.canonical_models import (
    PhysicalModelAdmission,
    PhysicalModelLock,
    PhysicalModelSubmissionReceipt,
    ServiceOpeningLink,
)
from classifire.models import Estimate, Opening, Service
from classifire.services.adjudicated_admission import (
    ADJUDICATED_ADMISSION_P256_MANIFEST_SCHEMA,
    ADJUDICATED_ADMISSION_P256_SIGNATURE_ALGORITHM,
    ADJUDICATED_ADMISSION_PURPOSE,
    admission_signing_bytes,
    normalised_submission_payload_bytes,
)
from classifire.services.adjudicated_admission_registration import (
    OfflineAdmissionRegistrationError,
    register_offline_adjudicated_admission,
)
from classifire.services.adjudicated_physical_submission import (
    ControlledPhysicalSubmissionError,
    execute_adjudicated_initial_submission,
    preflight_admission_binding,
)
from classifire.services.protected_state_fingerprint import (
    protected_state_counts,
    protected_state_fingerprint,
    protected_state_snapshot_from_session,
)

REHEARSAL_RECEIPT_SCHEMA = "CLASSIFIRE-ADJUDICATED-CANONICALISATION-REHEARSAL-v1"
REHEARSAL_RECEIPT_FILENAME = "adjudicated-canonicalisation-rehearsal.json"
REQUIRED_ALEMBIC_REVISION = "0007_reconcile_adjudicated_admission_lineages"
REHEARSAL_ISSUER = "disposable-rehearsal.classifire"
REHEARSAL_KEY_ID = "ephemeral-p256-rehearsal"
SUBMISSION_AGENT_ID = "cf-physical-model"
MAX_PREFLIGHT_BYTES = 5 * 1024 * 1024


class AdjudicatedCanonicalisationRehearsalError(RuntimeError):
    """Fail-closed rehearsal error with an operator-safe message."""


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _sqlite_creator(path: Path, *, read_only: bool) -> Callable[[], sqlite3.Connection]:
    uri = path.as_uri()
    if read_only:
        uri += "?mode=ro"

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(uri, uri=True, check_same_thread=False)

    return connect


def _engine(path: Path, *, read_only: bool) -> Engine:
    engine = create_engine(
        "sqlite+pysqlite://",
        creator=_sqlite_creator(path, read_only=read_only),
        future=True,
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite(dbapi_connection: sqlite3.Connection, _record: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _backup_sqlite(source: Path, target: Path) -> None:
    source_connection = _sqlite_creator(source, read_only=True)()
    target_connection = sqlite3.connect(target)
    try:
        source_connection.backup(target_connection)
        target_connection.commit()
    finally:
        target_connection.close()
        source_connection.close()


def _read_preflight(path: Path) -> bytes:
    try:
        resolved = path.resolve(strict=True)
        size = resolved.stat().st_size
        if not resolved.is_file() or size <= 0 or size > MAX_PREFLIGHT_BYTES:
            raise OSError("preflight is outside the permitted file boundary")
        return resolved.read_bytes()
    except OSError as exc:
        raise AdjudicatedCanonicalisationRehearsalError(
            "The preflight receipt is missing, unreadable, or outside the permitted size."
        ) from exc


def _database_state(db: Session, estimate_id: str) -> dict[str, Any]:
    snapshot = protected_state_snapshot_from_session(db, estimate_id)
    return {
        "protected_state_fingerprint": protected_state_fingerprint(snapshot),
        "protected_counts": protected_state_counts(snapshot),
        "opening_count": db.scalar(
            select(func.count()).select_from(Opening).where(Opening.estimate_id == estimate_id)
        ),
        "service_count": db.scalar(
            select(func.count())
            .select_from(Service)
            .join(Opening, Service.opening_id == Opening.id)
            .where(Opening.estimate_id == estimate_id)
        ),
        "service_opening_link_count": db.scalar(
            select(func.count())
            .select_from(ServiceOpeningLink)
            .join(Opening, ServiceOpeningLink.opening_id == Opening.id)
            .where(Opening.estimate_id == estimate_id)
        ),
        "active_physical_model_lock_count": db.scalar(
            select(func.count())
            .select_from(PhysicalModelLock)
            .where(
                PhysicalModelLock.estimate_id == estimate_id,
                PhysicalModelLock.invalidated_at.is_(None),
            )
        ),
        "admission_count": db.scalar(
            select(func.count())
            .select_from(PhysicalModelAdmission)
            .where(PhysicalModelAdmission.estimate_id == estimate_id)
        ),
        "submission_receipt_count": db.scalar(
            select(func.count())
            .select_from(PhysicalModelSubmissionReceipt)
            .where(PhysicalModelSubmissionReceipt.estimate_id == estimate_id)
        ),
    }


def _require_current_revision(db: Session) -> None:
    try:
        revisions = set(db.scalars(text("SELECT version_num FROM alembic_version")))
    except Exception as exc:
        raise AdjudicatedCanonicalisationRehearsalError(
            "The source database does not expose a readable Alembic revision."
        ) from exc
    if revisions != {REQUIRED_ALEMBIC_REVISION}:
        raise AdjudicatedCanonicalisationRehearsalError(
            f"The source database must be exactly at {REQUIRED_ALEMBIC_REVISION}."
        )


def _signed_manifest(
    *,
    private_key: ec.EllipticCurvePrivateKey,
    binding: Any,
    now: datetime,
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema": ADJUDICATED_ADMISSION_P256_MANIFEST_SCHEMA,
        "admission_id": str(uuid4()),
        "purpose": ADJUDICATED_ADMISSION_PURPOSE,
        "project_id": binding.project_id,
        "estimate_id": binding.estimate_id,
        "preflight_receipt_sha256": binding.raw_sha256,
        "normalised_submission_payload_sha256": binding.payload_sha256,
        "protected_state_fingerprint": binding.protected_state_fingerprint,
        "protected_state_fingerprint_version": binding.protected_state_fingerprint_version,
        "source_run_id": binding.source_run_id,
        "adjudicated_run_id": binding.adjudicated_run_id,
        "artifact_digests": dict(binding.artifact_digests),
        "policy_versions": dict(binding.policy_versions),
        "issuer": REHEARSAL_ISSUER,
        "key_id": REHEARSAL_KEY_ID,
        "issued_at": (now - timedelta(seconds=30)).isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        "signature_algorithm": ADJUDICATED_ADMISSION_P256_SIGNATURE_ALGORITHM,
        "signature": _base64url(b"\x30\x06\x02\x01\x01\x02\x01\x01"),
    }
    manifest["signature"] = _base64url(
        private_key.sign(admission_signing_bytes(manifest), ec.ECDSA(hashes.SHA256()))
    )
    return manifest


def _public_key(private_key: ec.EllipticCurvePrivateKey) -> str:
    return _base64url(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )


def _assert_exact_topology(db: Session, estimate_id: str, payload: dict[str, Any]) -> None:
    actual_openings = set(
        db.scalars(select(Opening.opening_code).where(Opening.estimate_id == estimate_id))
    )
    expected_openings = {item["opening_code"] for item in payload["openings"]}
    actual_services = set(
        db.scalars(
            select(Service.service_code)
            .join(Opening, Service.opening_id == Opening.id)
            .where(Opening.estimate_id == estimate_id)
        )
    )
    expected_services = {item["service_code"] for item in payload["services"]}
    actual_links = set(
        db.execute(
            select(Service.service_code, Opening.opening_code)
            .select_from(ServiceOpeningLink)
            .join(Service, ServiceOpeningLink.service_id == Service.id)
            .join(Opening, ServiceOpeningLink.opening_id == Opening.id)
            .where(Opening.estimate_id == estimate_id)
        )
    )
    expected_links = {
        (item["service_code"], opening_code)
        for item in payload["services"]
        for opening_code in item["opening_codes"]
    }
    if (
        actual_openings != expected_openings
        or actual_services != expected_services
        or actual_links != expected_links
    ):
        raise AdjudicatedCanonicalisationRehearsalError(
            "The disposable canonical model does not match the signed Opening-Service topology."
        )


def _write_summary(output_dir: Path, summary: dict[str, Any]) -> Path:
    if output_dir.exists():
        raise AdjudicatedCanonicalisationRehearsalError(
            "The rehearsal output directory already exists; refusing to overwrite it."
        )
    output_dir.mkdir(parents=True, exist_ok=False)
    output_path = output_dir / REHEARSAL_RECEIPT_FILENAME
    output_path.write_bytes(normalised_submission_payload_bytes(summary))
    return output_path


def run_rehearsal(
    *,
    source_database: Path,
    preflight_receipt: Path,
    output_dir: Path,
) -> tuple[Path, dict[str, Any]]:
    """Execute one no-live-write rehearsal and return its safe summary receipt."""

    try:
        source = source_database.resolve(strict=True)
    except OSError as exc:
        raise AdjudicatedCanonicalisationRehearsalError(
            "The source database does not exist or is unreadable."
        ) from exc
    if not source.is_file() or source.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        raise AdjudicatedCanonicalisationRehearsalError(
            "The source must be an existing SQLite database file."
        )
    if output_dir.exists():
        raise AdjudicatedCanonicalisationRehearsalError(
            "The rehearsal output directory already exists; refusing to overwrite it."
        )

    preflight_bytes = _read_preflight(preflight_receipt)
    try:
        binding = preflight_admission_binding(preflight_bytes)
    except ControlledPhysicalSubmissionError as exc:
        raise AdjudicatedCanonicalisationRehearsalError(
            f"The preflight receipt is not usable by the current writer: {exc.code}."
        ) from exc
    now = datetime.now(UTC).replace(microsecond=0)

    source_engine = _engine(source, read_only=True)
    source_factory = sessionmaker(bind=source_engine, expire_on_commit=False, future=True)
    try:
        with source_factory() as db:
            _require_current_revision(db)
            estimate = db.get(Estimate, binding.estimate_id)
            if estimate is None or estimate.project_id != binding.project_id:
                raise AdjudicatedCanonicalisationRehearsalError(
                    "The preflight project and estimate are not present in the source database."
                )
            source_before = _database_state(db, binding.estimate_id)
        if (
            source_before["protected_state_fingerprint"]
            != binding.protected_state_fingerprint
            or source_before["protected_counts"] != binding.protected_counts
        ):
            raise AdjudicatedCanonicalisationRehearsalError(
                "The source protected state no longer matches the retained preflight."
            )

        with tempfile.TemporaryDirectory(prefix="classifire-adjudicated-rehearsal-") as temp:
            disposable_path = Path(temp) / "disposable.sqlite"
            _backup_sqlite(source, disposable_path)
            disposable_engine = _engine(disposable_path, read_only=False)
            disposable_factory = sessionmaker(
                bind=disposable_engine,
                autoflush=False,
                expire_on_commit=False,
                future=True,
            )
            try:
                private_key = ec.generate_private_key(ec.SECP256R1())
                public_key = _public_key(private_key)
                pinned_keys = {REHEARSAL_KEY_ID: public_key}
                issuer_keys = {REHEARSAL_ISSUER: [REHEARSAL_KEY_ID]}
                manifest = _signed_manifest(private_key=private_key, binding=binding, now=now)

                with disposable_factory() as db:
                    _require_current_revision(db)
                    copy_before = _database_state(db, binding.estimate_id)
                    if copy_before != source_before:
                        raise AdjudicatedCanonicalisationRehearsalError(
                            "The disposable backup does not match the source protected baseline."
                        )
                    principal, token = provision_agent_principal(
                        db, agent_id=SUBMISSION_AGENT_ID
                    )
                    principal_id = principal.id
                    principal_agent_id = principal.agent_id
                    principal_scopes = list(principal.scopes or [])
                    del token
                    db.commit()

                try:
                    with disposable_factory() as db:
                        registration = register_offline_adjudicated_admission(
                            db,
                            manifest_bytes=normalised_submission_payload_bytes(manifest),
                            preflight_receipt_bytes=preflight_bytes,
                            operator_reference=f"DISPOSABLE-REHEARSAL-{now:%Y%m%d-%H%M%S}",
                            pinned_public_keys=pinned_keys,
                            issuer_key_ids=issuer_keys,
                            max_admission_ttl_seconds=900,
                            now=now,
                        )
                except (
                    ControlledPhysicalSubmissionError,
                    OfflineAdmissionRegistrationError,
                ) as exc:
                    raise AdjudicatedCanonicalisationRehearsalError(
                        f"Disposable admission registration failed closed: {exc.code}."
                    ) from exc

                idempotency_key = f"disposable-rehearsal-{uuid4()}"
                try:
                    with disposable_factory() as db:
                        submission = execute_adjudicated_initial_submission(
                            db,
                            estimate_id=binding.estimate_id,
                            admission_id=registration.admission_id,
                            idempotency_key=idempotency_key,
                            principal_id=principal_id,
                            principal_agent_id=principal_agent_id,
                            pinned_public_keys=pinned_keys,
                            issuer_key_ids=issuer_keys,
                            max_admission_ttl_seconds=900,
                            now=now,
                        )
                    with disposable_factory() as db:
                        replay = execute_adjudicated_initial_submission(
                            db,
                            estimate_id=binding.estimate_id,
                            admission_id=registration.admission_id,
                            idempotency_key=idempotency_key,
                            principal_id=principal_id,
                            principal_agent_id=principal_agent_id,
                            pinned_public_keys=pinned_keys,
                            issuer_key_ids=issuer_keys,
                            max_admission_ttl_seconds=900,
                            now=now,
                        )
                except ControlledPhysicalSubmissionError as exc:
                    raise AdjudicatedCanonicalisationRehearsalError(
                        f"Disposable controlled submission failed closed: {exc.code}."
                    ) from exc
                with disposable_factory() as db:
                    copy_after = _database_state(db, binding.estimate_id)
                    _assert_exact_topology(db, binding.estimate_id, binding.payload)
                    admission_state = db.scalar(
                        select(PhysicalModelAdmission.state).where(
                            PhysicalModelAdmission.admission_id == registration.admission_id
                        )
                    )
                    receipt_hash = db.scalar(
                        select(PhysicalModelSubmissionReceipt.receipt_sha256).where(
                            PhysicalModelSubmissionReceipt.admission_id
                            == registration.admission_id
                        )
                    )
            finally:
                disposable_engine.dispose()

        with source_factory() as db:
            source_after = _database_state(db, binding.estimate_id)
    finally:
        source_engine.dispose()

    expected_openings = len(binding.payload["openings"])
    expected_services = len(binding.payload["services"])
    expected_links = sum(len(item["opening_codes"]) for item in binding.payload["services"])
    if source_after != source_before:
        raise AdjudicatedCanonicalisationRehearsalError(
            "The source database protected state changed during rehearsal."
        )
    if (
        submission.replayed
        or not replay.replayed
        or replay.submission_id != submission.submission_id
        or admission_state != "consumed"
        or copy_after["opening_count"] != expected_openings
        or copy_after["service_count"] != expected_services
        or copy_after["service_opening_link_count"] != expected_links
        or copy_after["active_physical_model_lock_count"] != 0
        or copy_after["admission_count"] != 1
        or copy_after["submission_receipt_count"] != 1
        or submission.receipt.get("physical_model_lock_created") is not False
        or submission.receipt.get("gateway_call_performed") is not False
        or "physical:adjudicated:submit" not in principal_scopes
        or not isinstance(receipt_hash, str)
    ):
        raise AdjudicatedCanonicalisationRehearsalError(
            "The disposable registration/submission result did not satisfy the rehearsal gates."
        )

    summary = {
        "schema": REHEARSAL_RECEIPT_SCHEMA,
        "status": "DISPOSABLE_REHEARSAL_PASSED_SOURCE_UNCHANGED",
        "performed_at": now.isoformat().replace("+00:00", "Z"),
        "source_database": {
            "file_name": source.name,
            "write_performed": False,
            "protected_state_before": source_before,
            "protected_state_after": source_after,
        },
        "disposable_copy": {
            "retained": False,
            "alembic_revision": REQUIRED_ALEMBIC_REVISION,
            "protected_state_before": copy_before,
            "protected_state_after": copy_after,
        },
        "preflight": {
            "receipt_sha256": binding.raw_sha256,
            "project_id": binding.project_id,
            "estimate_id": binding.estimate_id,
            "source_run_id": binding.source_run_id,
            "adjudicated_run_id": binding.adjudicated_run_id,
            "normalised_submission_payload_sha256": binding.payload_sha256,
        },
        "synthetic_admission": {
            "ephemeral_private_key_retained": False,
            "manifest_retained": False,
            "issuer": REHEARSAL_ISSUER,
            "key_id": REHEARSAL_KEY_ID,
            "registration_status": registration.as_dict()["status"],
            "state_after_submission": admission_state,
        },
        "controlled_submission": {
            "writer_agent_id": principal_agent_id,
            "writer_scope_verified": True,
            "opening_count": expected_openings,
            "service_count": expected_services,
            "service_opening_link_count": expected_links,
            "canonical_write_performed_on_disposable_copy": True,
            "physical_model_lock_created": False,
            "gateway_call_performed": False,
            "idempotent_replay_verified": True,
            "submission_receipt_sha256": receipt_hash,
        },
    }
    output_path = _write_summary(output_dir.resolve(), summary)
    return output_path, summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Rehearse one adjudicated admission and canonical submission on a disposable "
            "SQLite backup without writing to the source database."
        )
    )
    parser.add_argument("--source-database", required=True, type=Path)
    parser.add_argument("--preflight-receipt", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        output_path, summary = run_rehearsal(
            source_database=args.source_database,
            preflight_receipt=args.preflight_receipt,
            output_dir=args.output_dir,
        )
    except AdjudicatedCanonicalisationRehearsalError as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "status": summary["status"],
                "receipt": str(output_path),
                "opening_count": summary["controlled_submission"]["opening_count"],
                "service_count": summary["controlled_submission"]["service_count"],
                "physical_model_lock_created": False,
                "source_database_write_performed": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
