from __future__ import annotations

import hashlib
import json
from datetime import timedelta

import pytest
from physical_foundation_support import physical_session
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from test_signed_physical_model_lock_amendment import (
    NOW,
    _manifest,
    _signed_lock,
    _visual_receipt,
)
from test_signed_physical_model_lock_amendment_admission import _register
from test_signed_physical_model_lock_amendment_preflight import _prepared_preflight

from classifire.models import AuditEvent, EstimateLine, Opening, Service, User
from classifire.physical_model_submission_schema import (
    InitialCanonicalPhysicalSubmission,
)
from classifire.physical_models import (
    PhysicalModelLock,
    PhysicalModelLockAmendmentOutcome,
    ServiceOpeningLink,
)
from classifire.services.physical_model import build_current_physical_model_lock_snapshot
from classifire.services.signed_physical_model_lock_amendment_execution import (
    EXECUTION_RECEIPT_SCHEMA,
    ROW_IDENTITY_MAP_SCHEMA,
    SignedPhysicalModelLockAmendmentExecutionError,
    execute_registered_signed_physical_model_lock_amendment,
)
from classifire.services.visual_validation_receipt import (
    register_visual_validation_receipt,
)


def _actor(db, *, role: str = "estimator", active: bool = True):  # type: ignore[no-untyped-def]
    actor = User(
        email=f"{role}-{active}@example.test",
        full_name="Synthetic amendment executor",
        password_hash="not-used",  # noqa: S106 - synthetic non-authenticating fixture
        role=role,
        is_active=active,
    )
    db.add(actor)
    db.flush()
    return actor


def _execute(db, admission, public_key, actor, *, now=NOW):  # type: ignore[no-untyped-def]
    return execute_registered_signed_physical_model_lock_amendment(
        db,
        amendment_admission_id=admission.amendment_admission_id,
        expected_amendment_envelope_sha256=admission.amendment_envelope_sha256,
        pinned_public_key=public_key,
        expected_issuer="classifire-governance",
        expected_key_id="amendment-p256-01",
        actor=actor,
        now=now,
        source_ip="127.0.0.1",
    )


def test_execution_atomically_reconciles_rows_and_invalidates_only_signed_lock() -> None:
    with physical_session() as db:
        estimate, opening, lock, payload, manifest, public_key = _prepared_preflight(db)
        old_opening_id = opening.id
        old_service = db.scalar(
            select(Service).where(
                Service.opening_id == opening.id, Service.service_code == "SVC-001"
            )
        )
        assert old_service is not None
        old_service_id = old_service.id
        old_link = db.scalar(
            select(ServiceOpeningLink).where(ServiceOpeningLink.service_id == old_service.id)
        )
        assert old_link is not None
        old_link_id = old_link.id
        admission, _ = _register(db, payload, manifest, public_key)
        actor = _actor(db)
        audit_before = db.scalar(select(func.count(AuditEvent.id)))
        before = build_current_physical_model_lock_snapshot(db, estimate)

        outcome, created = _execute(db, admission, public_key, actor)

        assert created is True
        assert outcome.pre_physical_model_content_hash == before.content_hash == lock.content_hash
        assert outcome.post_physical_model_content_hash != before.content_hash
        assert lock.invalidated_at == NOW
        assert lock.invalidation_reason == admission.amendment_reason
        assert db.scalar(select(func.count(PhysicalModelLock.id))) == 1
        assert (
            db.scalar(
                select(func.count(PhysicalModelLock.id)).where(
                    PhysicalModelLock.invalidated_at.is_(None)
                )
            )
            == 0
        )
        assert outcome.physical_model_lock_invalidated is True
        assert outcome.replacement_lock_created is False
        assert outcome.downstream_authority_granted is False
        assert (
            db.scalar(select(Opening.id).where(Opening.opening_code == "OP-001")) == old_opening_id
        )
        assert (
            db.scalar(select(Service.id).where(Service.service_code == "SVC-001")) == old_service_id
        )
        assert db.scalar(select(ServiceOpeningLink.id)) == old_link_id
        identity_map = json.loads(outcome.row_identity_map_json)
        receipt = json.loads(outcome.execution_receipt_json)
        assert identity_map["schema"] == ROW_IDENTITY_MAP_SCHEMA
        assert receipt["schema"] == EXECUTION_RECEIPT_SCHEMA
        assert receipt["replacement_lock_created"] is False
        assert receipt["downstream_authority_granted"] is False
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_before + 1


def test_execution_records_created_and_retired_topology_identities() -> None:
    with physical_session() as db:
        estimate, opening, lock = _signed_lock(db)
        old_opening_id = opening.id
        old_service = db.scalar(select(Service).where(Service.service_code == "SVC-001"))
        assert old_service is not None
        old_service_id = old_service.id
        old_link = db.scalar(select(ServiceOpeningLink))
        assert old_link is not None
        old_link_id = old_link.id
        payload = {
            "openings": [
                {
                    "opening_code": "OP-NEW",
                    "canonical_defect_id": opening.canonical_defect_id,
                    "opening_type": "service penetration",
                    "substrate_type": "concrete",
                    "substrate_plane": "wall",
                    "orientation": "horizontal",
                    "frl": "-/120/120",
                }
            ],
            "services": [
                {
                    "service_code": "SVC-NEW",
                    "service_type": "pipe",
                    "material": "copper",
                    "nominal_size_mm": "50",
                    "quantity": "1",
                }
            ],
            "service_opening_links": [
                {
                    "service_code": "SVC-NEW",
                    "opening_code": "OP-NEW",
                    "relationship_status": "confirmed",
                    "evidence_status": "confirmed",
                }
            ],
        }
        payload = InitialCanonicalPhysicalSubmission.model_validate(payload).model_dump(mode="json")
        visual_receipt, _ = register_visual_validation_receipt(
            db,
            receipt=_visual_receipt(estimate, payload),
            operator_reference="Synthetic human governance reviewer",
        )
        manifest, public_key = _manifest(db, estimate, lock, payload, visual_receipt.receipt_sha256)
        admission, _ = _register(db, payload, manifest, public_key)
        actor = _actor(db)

        outcome, created = _execute(db, admission, public_key, actor)

        assert created is True
        assert db.get(Opening, old_opening_id) is None
        assert db.get(Service, old_service_id) is None
        assert db.get(ServiceOpeningLink, old_link_id) is None
        new_opening = db.scalar(select(Opening).where(Opening.opening_code == "OP-NEW"))
        new_service = db.scalar(select(Service).where(Service.service_code == "SVC-NEW"))
        assert new_opening is not None
        assert new_service is not None
        assert new_service.opening_id == new_opening.id
        identity_map = json.loads(outcome.row_identity_map_json)
        assert {row["disposition"] for row in identity_map["openings"]} == {
            "created",
            "retired",
        }
        assert {row["disposition"] for row in identity_map["services"]} == {
            "created",
            "retired",
        }
        assert {row["disposition"] for row in identity_map["service_opening_links"]} == {
            "created",
            "retired",
        }


def test_execution_repoints_retained_service_before_retiring_primary_opening() -> None:
    with physical_session() as db:
        estimate, opening, lock = _signed_lock(db)
        service = db.scalar(select(Service).where(Service.service_code == "SVC-001"))
        assert service is not None
        service_id = service.id
        payload = InitialCanonicalPhysicalSubmission.model_validate(
            {
                "openings": [
                    {
                        "opening_code": "OP-NEW",
                        "canonical_defect_id": opening.canonical_defect_id,
                        "opening_type": "service penetration",
                        "substrate_type": "concrete",
                        "substrate_plane": "wall",
                        "orientation": "horizontal",
                        "frl": "-/120/120",
                    }
                ],
                "services": [
                    {
                        "service_code": service.service_code,
                        "service_type": service.service_type,
                        "material": service.material,
                        "nominal_size_mm": service.nominal_size_mm,
                        "quantity": service.quantity,
                    }
                ],
                "service_opening_links": [
                    {
                        "service_code": service.service_code,
                        "opening_code": "OP-NEW",
                        "relationship_status": "confirmed",
                        "evidence_status": "confirmed",
                    }
                ],
            }
        ).model_dump(mode="json")
        visual_receipt, _ = register_visual_validation_receipt(
            db,
            receipt=_visual_receipt(estimate, payload),
            operator_reference="Synthetic human governance reviewer",
        )
        manifest, public_key = _manifest(db, estimate, lock, payload, visual_receipt.receipt_sha256)
        admission, _ = _register(db, payload, manifest, public_key)

        outcome, created = _execute(db, admission, public_key, _actor(db))

        assert created is True
        retained_service = db.get(Service, service_id)
        new_opening = db.scalar(select(Opening).where(Opening.opening_code == "OP-NEW"))
        assert retained_service is not None
        assert new_opening is not None
        assert retained_service.opening_id == new_opening.id
        assert db.get(Opening, opening.id) is None
        identity_map = json.loads(outcome.row_identity_map_json)
        assert identity_map["services"] == [
            {
                "after_id": service_id,
                "before_id": service_id,
                "disposition": "preserved",
                "logical_key": "SVC-001",
            }
        ]


def test_execution_replay_returns_same_immutable_outcome_after_expiry() -> None:
    with physical_session() as db:
        _estimate, _opening, _lock, payload, manifest, public_key = _prepared_preflight(db)
        admission, _ = _register(db, payload, manifest, public_key)
        actor = _actor(db)
        outcome, created = _execute(db, admission, public_key, actor)
        assert created is True
        audit_count = db.scalar(select(func.count(AuditEvent.id)))

        replay, replay_created = _execute(
            db, admission, public_key, actor, now=NOW + timedelta(days=1)
        )

        assert replay.id == outcome.id
        assert replay_created is False
        assert db.scalar(select(func.count(PhysicalModelLockAmendmentOutcome.id))) == 1
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_count


def test_execution_rejects_noop_and_rolls_back_version_changes() -> None:
    with physical_session() as db:
        estimate, opening, lock = _signed_lock(db)
        service = db.scalar(select(Service).where(Service.service_code == "SVC-001"))
        link = db.scalar(select(ServiceOpeningLink))
        assert service is not None
        assert link is not None
        payload = InitialCanonicalPhysicalSubmission.model_validate(
            {
                "openings": [
                    {
                        "opening_code": opening.opening_code,
                        "canonical_defect_id": opening.canonical_defect_id,
                        "location": opening.location,
                        "substrate_type": opening.substrate_type,
                        "substrate_plane": opening.substrate_plane,
                        "substrate_thickness_mm": opening.substrate_thickness_mm,
                        "orientation": opening.orientation,
                        "opening_type": opening.opening_type,
                        "width_mm": opening.width_mm,
                        "height_mm": opening.height_mm,
                        "diameter_mm": opening.diameter_mm,
                        "frl": opening.frl,
                        "notes": opening.notes,
                    }
                ],
                "services": [
                    {
                        "service_code": service.service_code,
                        "service_type": service.service_type,
                        "material": service.material,
                        "nominal_size_mm": service.nominal_size_mm,
                        "outside_diameter_mm": service.outside_diameter_mm,
                        "width_mm": service.width_mm,
                        "height_mm": service.height_mm,
                        "insulation_type": service.insulation_type,
                        "insulation_thickness_mm": service.insulation_thickness_mm,
                        "quantity": service.quantity,
                        "centre_x_mm": service.centre_x_mm,
                        "centre_y_mm": service.centre_y_mm,
                        "evidence_status": service.evidence_status,
                        "confidence": service.confidence,
                        "notes": service.notes,
                    }
                ],
                "service_opening_links": [
                    {
                        "service_code": service.service_code,
                        "opening_code": opening.opening_code,
                        "link_type": link.link_type,
                        "relationship_status": link.relationship_status,
                        "evidence_status": link.evidence_status,
                        "confidence": link.confidence,
                        "source_reference": link.source_reference,
                        "notes": link.notes,
                    }
                ],
            }
        ).model_dump(mode="json")
        visual_receipt, _ = register_visual_validation_receipt(
            db,
            receipt=_visual_receipt(estimate, payload),
            operator_reference="Synthetic human governance reviewer",
        )
        manifest, public_key = _manifest(db, estimate, lock, payload, visual_receipt.receipt_sha256)
        admission, _ = _register(db, payload, manifest, public_key)
        actor = _actor(db)
        versions_before = (opening.record_version, service.record_version, link.record_version)

        with pytest.raises(SignedPhysicalModelLockAmendmentExecutionError) as rejected:
            _execute(db, admission, public_key, actor)

        assert rejected.value.code == "AMENDMENT_NO_PHYSICAL_CHANGE"
        assert lock.invalidated_at is None
        assert db.scalar(select(func.count(PhysicalModelLockAmendmentOutcome.id))) == 0
        db.refresh(opening)
        db.refresh(service)
        db.refresh(link)
        assert (
            opening.record_version,
            service.record_version,
            link.record_version,
        ) == versions_before


@pytest.mark.parametrize(("role", "active"), [("read_only", True), ("estimator", False)])
def test_execution_requires_active_human_write_permission(role: str, active: bool) -> None:
    with physical_session() as db:
        _estimate, _opening, lock, payload, manifest, public_key = _prepared_preflight(db)
        admission, _ = _register(db, payload, manifest, public_key)
        actor = _actor(db, role=role, active=active)

        with pytest.raises(SignedPhysicalModelLockAmendmentExecutionError) as rejected:
            _execute(db, admission, public_key, actor)

        assert rejected.value.code == "AMENDMENT_EXECUTION_PERMISSION_DENIED"
        assert lock.invalidated_at is None
        assert db.scalar(select(func.count(PhysicalModelLockAmendmentOutcome.id))) == 0


def test_execution_rechecks_later_downstream_dependencies_without_writing() -> None:
    with physical_session() as db:
        estimate, _opening, lock, payload, manifest, public_key = _prepared_preflight(db)
        admission, _ = _register(db, payload, manifest, public_key)
        actor = _actor(db)
        db.add(
            EstimateLine(
                estimate_id=estimate.id,
                line_number=1,
                component_type="labour",
                description="Later commercial dependency",
            )
        )
        db.flush()

        with pytest.raises(SignedPhysicalModelLockAmendmentExecutionError) as rejected:
            _execute(db, admission, public_key, actor)

        assert rejected.value.code == "AMENDMENT_COMMERCIAL_DEPENDENCY_PRESENT"
        assert lock.invalidated_at is None
        assert db.scalar(select(func.count(PhysicalModelLockAmendmentOutcome.id))) == 0


def test_execution_rolls_back_rows_lock_outcome_and_audit_on_write_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with physical_session() as db:
        estimate, opening, lock, payload, manifest, public_key = _prepared_preflight(db)
        admission, _ = _register(db, payload, manifest, public_key)
        actor = _actor(db)
        before = build_current_physical_model_lock_snapshot(db, estimate)
        audit_before = db.scalar(select(func.count(AuditEvent.id)))

        def fail_audit(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise SQLAlchemyError("synthetic audit failure")

        monkeypatch.setattr(
            "classifire.services.signed_physical_model_lock_amendment_execution.record_audit",
            fail_audit,
        )
        with pytest.raises(SignedPhysicalModelLockAmendmentExecutionError) as rejected:
            _execute(db, admission, public_key, actor)

        assert rejected.value.code == "AMENDMENT_EXECUTION_WRITE_FAILED"
        db.expire_all()
        assert db.get(PhysicalModelLock, lock.id).invalidated_at is None
        assert (
            build_current_physical_model_lock_snapshot(db, estimate).content_hash
            == before.content_hash
        )
        assert db.get(Opening, opening.id) is not None
        assert db.scalar(select(func.count(PhysicalModelLockAmendmentOutcome.id))) == 0
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_before


def test_execution_replay_rejects_tampered_outcome() -> None:
    with physical_session() as db:
        _estimate, _opening, _lock, payload, manifest, public_key = _prepared_preflight(db)
        admission, _ = _register(db, payload, manifest, public_key)
        actor = _actor(db)
        outcome, _ = _execute(db, admission, public_key, actor)
        receipt = json.loads(outcome.execution_receipt_json)
        receipt["estimate_id"] = "00000000-0000-0000-0000-000000000000"
        outcome.execution_receipt_json = json.dumps(
            receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        outcome.execution_receipt_sha256 = (
            hashlib.sha256(outcome.execution_receipt_json.encode("utf-8")).hexdigest().upper()
        )
        db.flush()

        with pytest.raises(SignedPhysicalModelLockAmendmentExecutionError) as rejected:
            _execute(db, admission, public_key, actor, now=NOW + timedelta(days=1))

        assert rejected.value.code == "AMENDMENT_EXECUTION_OUTCOME_CORRUPT"
