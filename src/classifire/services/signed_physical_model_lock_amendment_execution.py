"""Atomically execute one registered signed Physical Model Lock amendment.

The transaction consumes only the exact registered payload, reconciles the
canonical physical topology, invalidates only its signed target lock, and
retains immutable before/after snapshots plus a row identity map. It never
creates a replacement lock or grants technical, commercial, or release
authority. The caller owns the surrounding transaction.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import Estimate, Opening, Service, User
from ..physical_model_submission_schema import InitialCanonicalPhysicalSubmission
from ..physical_models import (
    PhysicalModelLock,
    PhysicalModelLockAmendmentAdmission,
    PhysicalModelLockAmendmentOutcome,
    ServiceOpeningLink,
)
from ..security import has_permission
from .physical_model import build_current_physical_model_lock_snapshot
from .signed_physical_model_lock_amendment_admission import (
    SignedPhysicalModelLockAmendmentAdmissionError,
    preflight_registered_signed_physical_model_lock_amendment,
)

EXECUTION_RECEIPT_SCHEMA = "CLASSIFIRE-SIGNED-PHYSICAL-MODEL-LOCK-AMENDMENT-EXECUTION-v1"
ROW_IDENTITY_MAP_SCHEMA = "CLASSIFIRE-PHYSICAL-MODEL-ROW-IDENTITY-MAP-v1"


class SignedPhysicalModelLockAmendmentExecutionError(RuntimeError):
    """Safe-code failure while executing a registered signed amendment."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Signed Physical Model Lock amendment execution failed: {code}.")


def execute_registered_signed_physical_model_lock_amendment(
    db: Session,
    *,
    amendment_admission_id: str,
    expected_amendment_envelope_sha256: str,
    pinned_public_key: str,
    expected_issuer: str,
    expected_key_id: str,
    actor: User | None,
    now: datetime | None = None,
    source_ip: str | None = None,
) -> tuple[PhysicalModelLockAmendmentOutcome, bool]:
    """Execute one exact registered admission inside the caller's transaction."""

    current_time = _normalise_now(now)
    authorised_actor = _authorised_actor(db, actor)
    existing = db.scalar(
        select(PhysicalModelLockAmendmentOutcome)
        .where(PhysicalModelLockAmendmentOutcome.amendment_admission_id == amendment_admission_id)
        .with_for_update()
    )
    if existing is not None:
        _require_intact_outcome(
            db,
            existing,
            expected_amendment_envelope_sha256=expected_amendment_envelope_sha256,
        )
        return existing, False

    try:
        registered = preflight_registered_signed_physical_model_lock_amendment(
            db,
            amendment_admission_id=amendment_admission_id,
            expected_amendment_envelope_sha256=expected_amendment_envelope_sha256,
            pinned_public_key=pinned_public_key,
            expected_issuer=expected_issuer,
            expected_key_id=expected_key_id,
            now=current_time,
        )
    except SignedPhysicalModelLockAmendmentAdmissionError as exc:
        # A concurrent exact execution can commit while this transaction waits
        # for the registered admission. Re-read the immutable outcome before
        # returning the preflight failure.
        replay = db.scalar(
            select(PhysicalModelLockAmendmentOutcome)
            .where(
                PhysicalModelLockAmendmentOutcome.amendment_admission_id == amendment_admission_id
            )
            .with_for_update()
        )
        if replay is not None:
            _require_intact_outcome(
                db,
                replay,
                expected_amendment_envelope_sha256=expected_amendment_envelope_sha256,
            )
            return replay, False
        raise SignedPhysicalModelLockAmendmentExecutionError(exc.code) from exc

    admission = db.get(PhysicalModelLockAmendmentAdmission, registered.admission_record_id)
    if admission is None:
        raise SignedPhysicalModelLockAmendmentExecutionError("AMENDMENT_ADMISSION_NOT_FOUND")
    estimate = db.scalar(
        select(Estimate).where(Estimate.id == admission.estimate_id).with_for_update()
    )
    target_lock = db.scalar(
        select(PhysicalModelLock)
        .where(PhysicalModelLock.id == admission.target_lock_id)
        .with_for_update()
    )
    if estimate is None or target_lock is None:
        raise SignedPhysicalModelLockAmendmentExecutionError("AMENDMENT_EXECUTION_BINDING_INVALID")

    before = build_current_physical_model_lock_snapshot(db, estimate)
    if not (
        before.content_hash
        == admission.current_physical_model_content_hash
        == admission.target_lock_content_hash
        == target_lock.content_hash
    ):
        raise SignedPhysicalModelLockAmendmentExecutionError("AMENDMENT_EXECUTION_BINDING_INVALID")

    try:
        with db.begin_nested():
            identity_map = _reconcile_physical_rows(db, estimate, registered.amendment_submission)
            db.flush()
            after = build_current_physical_model_lock_snapshot(db, estimate)
            if after.content_hash == before.content_hash:
                raise SignedPhysicalModelLockAmendmentExecutionError("AMENDMENT_NO_PHYSICAL_CHANGE")

            identity_map_json = _canonical_json(identity_map)
            identity_map_sha256 = _sha256(identity_map_json)
            target_lock.invalidated_at = current_time
            target_lock.invalidation_reason = admission.amendment_reason
            target_lock.updated_at = current_time
            target_lock.record_version += 1

            outcome_id = str(uuid.uuid4())
            receipt = {
                "schema": EXECUTION_RECEIPT_SCHEMA,
                "outcome_id": outcome_id,
                "amendment_admission_id": admission.amendment_admission_id,
                "admission_record_id": admission.id,
                "project_id": admission.project_id,
                "estimate_id": admission.estimate_id,
                "target_lock_id": admission.target_lock_id,
                "target_lock_content_hash": admission.target_lock_content_hash,
                "amendment_envelope_sha256": admission.amendment_envelope_sha256,
                "amendment_submission_payload_sha256": (
                    admission.amendment_submission_payload_sha256
                ),
                "pre_physical_model_content_hash": before.content_hash,
                "post_physical_model_content_hash": after.content_hash,
                "row_identity_map_sha256": identity_map_sha256,
                "opening_count_before": len(before.as_dict()["openings"]),
                "opening_count_after": len(after.as_dict()["openings"]),
                "service_count_before": len(before.as_dict()["services"]),
                "service_count_after": len(after.as_dict()["services"]),
                "service_opening_link_count_before": len(before.as_dict()["service_opening_links"]),
                "service_opening_link_count_after": len(after.as_dict()["service_opening_links"]),
                "executed_by_user_id": authorised_actor.id,
                "executed_at": _timestamp_text(current_time),
                "physical_model_lock_invalidated": True,
                "replacement_lock_created": False,
                "downstream_authority_granted": False,
            }
            receipt_json = _canonical_json(receipt)
            outcome = PhysicalModelLockAmendmentOutcome(
                id=outcome_id,
                admission_record_id=admission.id,
                amendment_admission_id=admission.amendment_admission_id,
                project_id=admission.project_id,
                estimate_id=admission.estimate_id,
                target_lock_id=admission.target_lock_id,
                target_lock_content_hash=admission.target_lock_content_hash,
                amendment_envelope_sha256=admission.amendment_envelope_sha256,
                amendment_submission_payload_sha256=(admission.amendment_submission_payload_sha256),
                pre_physical_model_payload_json=before.canonical_payload_json,
                pre_physical_model_content_hash=before.content_hash,
                post_physical_model_payload_json=after.canonical_payload_json,
                post_physical_model_content_hash=after.content_hash,
                row_identity_map_json=identity_map_json,
                row_identity_map_sha256=identity_map_sha256,
                executed_by_user_id=authorised_actor.id,
                executed_at=current_time,
                physical_model_lock_invalidated=True,
                replacement_lock_created=False,
                downstream_authority_granted=False,
                execution_receipt_json=receipt_json,
                execution_receipt_sha256=_sha256(receipt_json),
            )
            db.add(outcome)
            record_audit(
                db,
                actor=authorised_actor,
                action="execute_signed_physical_model_lock_amendment",
                entity_type="physical_model_lock_amendment_outcome",
                entity_id=outcome.id,
                project_id=outcome.project_id,
                source_ip=source_ip,
                correlation_id=outcome.amendment_admission_id,
                previous_value={
                    "physical_model_content_hash": before.content_hash,
                    "active_physical_model_lock_id": target_lock.id,
                },
                new_value={
                    "physical_model_content_hash": after.content_hash,
                    "row_identity_map_sha256": identity_map_sha256,
                    "physical_model_lock_invalidated": True,
                    "replacement_lock_created": False,
                    "downstream_authority_granted": False,
                },
                reason=admission.amendment_reason,
            )
            db.flush()
    except SignedPhysicalModelLockAmendmentExecutionError:
        raise
    except SQLAlchemyError as exc:
        raise SignedPhysicalModelLockAmendmentExecutionError(
            "AMENDMENT_EXECUTION_WRITE_FAILED"
        ) from exc
    return outcome, True


def _authorised_actor(db: Session, actor: User | None) -> User:
    if actor is None or not actor.id:
        raise SignedPhysicalModelLockAmendmentExecutionError(
            "AMENDMENT_EXECUTION_PERMISSION_DENIED"
        )
    retained = db.scalar(select(User).where(User.id == actor.id).with_for_update())
    if retained is None or not retained.is_active or not has_permission(retained, "estimate:write"):
        raise SignedPhysicalModelLockAmendmentExecutionError(
            "AMENDMENT_EXECUTION_PERMISSION_DENIED"
        )
    return retained


def _reconcile_physical_rows(
    db: Session,
    estimate: Estimate,
    payload: InitialCanonicalPhysicalSubmission,
) -> dict[str, object]:
    item: Any
    opening: Opening | None
    service: Service | None
    link: ServiceOpeningLink | None
    openings = list(
        db.scalars(
            select(Opening).where(Opening.estimate_id == estimate.id).order_by(Opening.id)
        ).all()
    )
    opening_by_code = _unique_by(openings, "opening_code")
    opening_ids = [item.id for item in openings]
    links = (
        list(
            db.scalars(
                select(ServiceOpeningLink)
                .where(ServiceOpeningLink.opening_id.in_(opening_ids))
                .order_by(ServiceOpeningLink.id)
            ).all()
        )
        if opening_ids
        else []
    )
    service_ids = sorted({item.service_id for item in links})
    services = (
        list(db.scalars(select(Service).where(Service.id.in_(service_ids))).all())
        if service_ids
        else []
    )
    service_by_code = _unique_by(services, "service_code")
    opening_code_by_id = {item.id: item.opening_code for item in openings}
    service_code_by_id = {item.id: item.service_code for item in services}
    link_by_key = {
        (service_code_by_id[item.service_id], opening_code_by_id[item.opening_id]): item
        for item in links
    }
    before_keys = {
        "openings": {item.opening_code: item.id for item in openings},
        "services": {item.service_code: item.id for item in services},
        "service_opening_links": {
            f"{service_code_by_id[item.service_id]}->{opening_code_by_id[item.opening_id]}": item.id
            for item in links
        },
    }

    desired_opening_codes = {item.opening_code for item in payload.openings}
    desired_service_codes = {item.service_code for item in payload.services}
    desired_link_keys = {
        (item.service_code, item.opening_code) for item in payload.service_opening_links
    }
    for key, link in link_by_key.items():
        if key not in desired_link_keys:
            db.delete(link)
    db.flush()

    resolved_openings: dict[str, Opening] = {}
    for item in payload.openings:
        opening = opening_by_code.get(item.opening_code)
        if opening is None:
            opening = Opening(estimate_id=estimate.id, opening_code=item.opening_code)
            db.add(opening)
        else:
            opening.record_version += 1
            if opening.canonical_defect_id != item.canonical_defect_id:
                opening.defect_id = None
        opening.canonical_defect_id = item.canonical_defect_id
        opening.location = item.location
        opening.substrate_type = item.substrate_type
        opening.substrate_plane = item.substrate_plane
        opening.substrate_thickness_mm = item.substrate_thickness_mm
        opening.orientation = item.orientation
        opening.opening_type = item.opening_type
        opening.width_mm = item.width_mm
        opening.height_mm = item.height_mm
        opening.diameter_mm = item.diameter_mm
        opening.frl = item.frl
        opening.physical_model_status = "draft"
        opening.technical_status = "not_assessed"
        opening.selected_technical_variant_id = None
        opening.notes = item.notes
        resolved_openings[item.opening_code] = opening
    db.flush()

    first_opening_by_service = {
        service.service_code: next(
            link.opening_code
            for link in payload.service_opening_links
            if link.service_code == service.service_code
        )
        for service in payload.services
    }
    resolved_services: dict[str, Service] = {}
    for item in payload.services:
        service = service_by_code.get(item.service_code)
        if service is None:
            service = Service(
                service_code=item.service_code,
                opening_id=resolved_openings[first_opening_by_service[item.service_code]].id,
            )
            db.add(service)
        else:
            service.record_version += 1
        service.opening_id = resolved_openings[first_opening_by_service[item.service_code]].id
        service.primary_opening_legacy = True
        service.service_type = item.service_type
        service.material = item.material
        service.nominal_size_mm = item.nominal_size_mm
        service.outside_diameter_mm = item.outside_diameter_mm
        service.width_mm = item.width_mm
        service.height_mm = item.height_mm
        service.insulation_type = item.insulation_type
        service.insulation_thickness_mm = item.insulation_thickness_mm
        service.quantity = item.quantity
        service.centre_x_mm = item.centre_x_mm
        service.centre_y_mm = item.centre_y_mm
        service.evidence_status = item.evidence_status
        service.confidence = item.confidence
        service.notes = item.notes
        resolved_services[item.service_code] = service
    db.flush()

    resolved_links: dict[str, ServiceOpeningLink] = {}
    for item in payload.service_opening_links:
        key = (item.service_code, item.opening_code)
        link = link_by_key.get(key)
        if link is None:
            link = ServiceOpeningLink(
                service_id=resolved_services[item.service_code].id,
                opening_id=resolved_openings[item.opening_code].id,
            )
            db.add(link)
        else:
            link.record_version += 1
        link.link_type = item.link_type
        link.relationship_status = item.relationship_status
        link.evidence_status = item.evidence_status
        link.confidence = item.confidence
        link.source_reference = item.source_reference
        link.notes = item.notes
        resolved_links[f"{item.service_code}->{item.opening_code}"] = link
    db.flush()
    for service in services:
        if service.service_code not in desired_service_codes:
            db.delete(service)
    db.flush()
    for opening in openings:
        if opening.opening_code not in desired_opening_codes:
            db.delete(opening)
    db.flush()

    after_keys = {
        "openings": {key: item.id for key, item in resolved_openings.items()},
        "services": {key: item.id for key, item in resolved_services.items()},
        "service_opening_links": {key: item.id for key, item in resolved_links.items()},
    }
    before_snapshot = build_current_physical_model_lock_snapshot(db, estimate).as_dict()
    identity_map: dict[str, object] = {
        "schema": ROW_IDENTITY_MAP_SCHEMA,
        "defects": _unchanged_identity_rows(before_snapshot["defects"]),
        "evidence": _unchanged_identity_rows(before_snapshot["evidence"]),
    }
    for category in ("openings", "services", "service_opening_links"):
        identity_map[category] = _identity_rows(before_keys[category], after_keys[category])
    return identity_map


def _unique_by(rows: list[Any], attribute: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for row in rows:
        key = str(getattr(row, attribute))
        if key in result:
            raise SignedPhysicalModelLockAmendmentExecutionError(
                "AMENDMENT_CURRENT_IDENTITY_AMBIGUOUS"
            )
        result[key] = row
    return result


def _unchanged_identity_rows(rows: list[dict[str, Any]]) -> list[dict[str, object]]:
    return [
        {
            "logical_key": str(row["id"]),
            "before_id": str(row["id"]),
            "after_id": str(row["id"]),
            "disposition": "preserved",
        }
        for row in sorted(rows, key=lambda item: str(item["id"]))
    ]


def _identity_rows(before: dict[str, str], after: dict[str, str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for key in sorted(set(before) | set(after)):
        before_id = before.get(key)
        after_id = after.get(key)
        disposition = (
            "created"
            if before_id is None
            else "retired"
            if after_id is None
            else "preserved"
            if before_id == after_id
            else "replaced"
        )
        rows.append(
            {
                "logical_key": key,
                "before_id": before_id,
                "after_id": after_id,
                "disposition": disposition,
            }
        )
    return rows


def _require_intact_outcome(
    db: Session,
    outcome: PhysicalModelLockAmendmentOutcome,
    *,
    expected_amendment_envelope_sha256: str,
) -> None:
    if outcome.amendment_envelope_sha256 != expected_amendment_envelope_sha256:
        raise SignedPhysicalModelLockAmendmentExecutionError("AMENDMENT_EXECUTION_BINDING_INVALID")
    admission = db.get(PhysicalModelLockAmendmentAdmission, outcome.admission_record_id)
    target_lock = db.get(PhysicalModelLock, outcome.target_lock_id)
    if admission is None or target_lock is None:
        raise SignedPhysicalModelLockAmendmentExecutionError("AMENDMENT_EXECUTION_OUTCOME_CORRUPT")
    expected_bindings = {
        "amendment_admission_id": admission.amendment_admission_id,
        "project_id": admission.project_id,
        "estimate_id": admission.estimate_id,
        "target_lock_id": admission.target_lock_id,
        "target_lock_content_hash": admission.target_lock_content_hash,
        "amendment_envelope_sha256": admission.amendment_envelope_sha256,
        "amendment_submission_payload_sha256": admission.amendment_submission_payload_sha256,
    }
    if any(getattr(outcome, key) != value for key, value in expected_bindings.items()) or not (
        _sha256(admission.amendment_envelope_json) == admission.amendment_envelope_sha256
        and _sha256(admission.amendment_submission_payload_json)
        == admission.amendment_submission_payload_sha256
    ):
        raise SignedPhysicalModelLockAmendmentExecutionError("AMENDMENT_EXECUTION_OUTCOME_CORRUPT")
    try:
        pre = _canonical_object(outcome.pre_physical_model_payload_json)
        post = _canonical_object(outcome.post_physical_model_payload_json)
        identity_map = _canonical_object(outcome.row_identity_map_json)
        receipt = _canonical_object(outcome.execution_receipt_json)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SignedPhysicalModelLockAmendmentExecutionError(
            "AMENDMENT_EXECUTION_OUTCOME_CORRUPT"
        ) from exc
    expected_receipt = {
        "outcome_id": outcome.id,
        "amendment_admission_id": outcome.amendment_admission_id,
        "admission_record_id": outcome.admission_record_id,
        "project_id": outcome.project_id,
        "estimate_id": outcome.estimate_id,
        "target_lock_id": outcome.target_lock_id,
        "target_lock_content_hash": outcome.target_lock_content_hash,
        "amendment_envelope_sha256": outcome.amendment_envelope_sha256,
        "amendment_submission_payload_sha256": outcome.amendment_submission_payload_sha256,
        "pre_physical_model_content_hash": outcome.pre_physical_model_content_hash,
        "post_physical_model_content_hash": outcome.post_physical_model_content_hash,
        "row_identity_map_sha256": outcome.row_identity_map_sha256,
        "opening_count_before": len(pre.get("openings", [])),
        "opening_count_after": len(post.get("openings", [])),
        "service_count_before": len(pre.get("services", [])),
        "service_count_after": len(post.get("services", [])),
        "service_opening_link_count_before": len(pre.get("service_opening_links", [])),
        "service_opening_link_count_after": len(post.get("service_opening_links", [])),
        "executed_by_user_id": outcome.executed_by_user_id,
        "executed_at": _timestamp_text(_aware_utc(outcome.executed_at)),
        "physical_model_lock_invalidated": True,
        "replacement_lock_created": False,
        "downstream_authority_granted": False,
    }
    if not (
        hashlib.sha256(_canonical_json(pre).encode("utf-8")).hexdigest()
        == outcome.pre_physical_model_content_hash
        and hashlib.sha256(_canonical_json(post).encode("utf-8")).hexdigest()
        == outcome.post_physical_model_content_hash
        and _sha256(_canonical_json(identity_map)) == outcome.row_identity_map_sha256
        and _sha256(_canonical_json(receipt)) == outcome.execution_receipt_sha256
        and identity_map.get("schema") == ROW_IDENTITY_MAP_SCHEMA
        and receipt.get("schema") == EXECUTION_RECEIPT_SCHEMA
        and all(receipt.get(key) == value for key, value in expected_receipt.items())
        and outcome.physical_model_lock_invalidated is True
        and outcome.replacement_lock_created is False
        and outcome.downstream_authority_granted is False
        and target_lock.invalidated_at is not None
        and target_lock.invalidation_reason == admission.amendment_reason
    ):
        raise SignedPhysicalModelLockAmendmentExecutionError("AMENDMENT_EXECUTION_OUTCOME_CORRUPT")


def _canonical_object(value: str) -> dict[str, Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict) or _canonical_json(parsed) != value:
        raise ValueError("not a canonical JSON object")
    return parsed


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest().upper()


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _timestamp_text(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalise_now(now: datetime | None) -> datetime:
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise SignedPhysicalModelLockAmendmentExecutionError("AMENDMENT_TIME_INVALID")
    return current.astimezone(UTC)


__all__ = [
    "EXECUTION_RECEIPT_SCHEMA",
    "ROW_IDENTITY_MAP_SCHEMA",
    "SignedPhysicalModelLockAmendmentExecutionError",
    "execute_registered_signed_physical_model_lock_amendment",
]
