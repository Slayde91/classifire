from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_report_evidence_adapter import (
    _bound_report,
    _estimate,
    _project,
    _report_content,
    adapter_session,
)

from classifire.models import (
    Opening,
    ReportEvidenceFamilyManifest,
    ReportEvidenceFamilyMember,
    Service,
    User,
)
from classifire.services.report_evidence_family_manifest import (
    ReportEvidenceFamilyManifestError,
    record_approved_report_evidence_family_manifest,
    require_approved_report_evidence_family_manifest,
)


def _reviewer(db: Session, *, ordinal: int) -> User:
    reviewer = User(
        email=f"family-reviewer-{ordinal}@example.test",
        full_name="Family reviewer",
        password_hash="not-used-by-synthetic-tests",  # noqa: S106
        role="reviewer",
    )
    db.add(reviewer)
    db.flush()
    return reviewer


def _approved_family(
    db: Session,
    *,
    ordinal: int,
) -> tuple[object, object, object, object, object, object]:
    project = _project(db, ordinal)
    estimate = _estimate(db, project, ordinal)
    first_content = _report_content(b"synthetic family report one")
    second_content = _report_content(b"synthetic family report two")
    first_stored = _bound_report(db, project, first_content)
    second_stored = _bound_report(db, project, second_content)
    reviewer = _reviewer(db, ordinal=ordinal)
    manifest = record_approved_report_evidence_family_manifest(
        db,
        project_id=project.id,
        estimate_id=estimate.id,
        family_reference="Synthetic report set A",
        report_members=(
            {"stored_file_id": second_stored.id, "report_sha256": second_content.sha256},
            {"stored_file_id": first_stored.id, "report_sha256": first_content.sha256},
        ),
        approval_reference="synthetic human family approval",
        approved_by_user_id=reviewer.id,
    )
    return project, estimate, first_stored, second_stored, reviewer, manifest


def test_family_is_explicit_ordered_idempotent_and_source_bound() -> None:
    with adapter_session() as db:
        project, estimate, first_stored, second_stored, reviewer, first = _approved_family(
            db,
            ordinal=1501,
        )
        second = record_approved_report_evidence_family_manifest(
            db,
            project_id=project.id,
            estimate_id=estimate.id,
            family_reference="Synthetic report set A",
            report_members=(
                {"stored_file_id": second_stored.id, "report_sha256": second_stored.sha256},
                {"stored_file_id": first_stored.id, "report_sha256": first_stored.sha256},
            ),
            approval_reference="synthetic human family approval",
            approved_by_user_id=reviewer.id,
        )
        loaded = require_approved_report_evidence_family_manifest(
            db,
            report_evidence_family_manifest_id=first.id,
            project_id=project.id,
            estimate_id=estimate.id,
        )

        assert second.id == first.id
        assert loaded == first
        assert [member.stored_file_id for member in first.members] == [
            second_stored.id,
            first_stored.id,
        ]
        assert [member.member_sequence for member in first.members] == [1, 2]
        assert len(first.manifest_sha256) == 64
        assert first.manifest_sha256 == first.manifest_sha256.upper()
        assert db.scalar(select(func.count()).select_from(ReportEvidenceFamilyManifest)) == 1
        assert db.scalar(select(func.count()).select_from(ReportEvidenceFamilyMember)) == 2
        assert db.scalar(select(func.count()).select_from(Opening)) == 0
        assert db.scalar(select(func.count()).select_from(Service)) == 0


@pytest.mark.parametrize(
    "members",
    (
        (),
        ({"stored_file_id": "not-used", "report_sha256": "0" * 64},),
        (
            {"stored_file_id": "one", "report_sha256": "0" * 64},
            {"stored_file_id": "one", "report_sha256": "1" * 64},
        ),
        (
            {"stored_file_id": "one", "report_sha256": "0" * 64, "filename": "guess.pdf"},
            {"stored_file_id": "two", "report_sha256": "1" * 64},
        ),
    ),
)
def test_family_rejects_implicit_or_ambiguous_membership(members: object) -> None:
    with adapter_session() as db:
        project = _project(db, 1502)
        estimate = _estimate(db, project, 1502)
        reviewer = _reviewer(db, ordinal=1502)

        with pytest.raises(ReportEvidenceFamilyManifestError) as raised:
            record_approved_report_evidence_family_manifest(
                db,
                project_id=project.id,
                estimate_id=estimate.id,
                family_reference="Synthetic report set B",
                report_members=members,
                approval_reference="synthetic human family approval",
                approved_by_user_id=reviewer.id,
            )

        assert raised.value.code == "REPORT_EVIDENCE_FAMILY_MANIFEST_MEMBERS_INVALID"


def test_family_tampering_source_drift_and_foreign_estimate_fail_closed() -> None:
    with adapter_session() as db:
        project, estimate, first_stored, _, _, manifest = _approved_family(db, ordinal=1503)
        family = db.get(ReportEvidenceFamilyManifest, manifest.id)
        assert family is not None
        family.family_reference = "tampered family reference"
        db.flush()

        with pytest.raises(ReportEvidenceFamilyManifestError) as tampered:
            require_approved_report_evidence_family_manifest(
                db,
                report_evidence_family_manifest_id=manifest.id,
                project_id=project.id,
                estimate_id=estimate.id,
            )

        assert tampered.value.code == "REPORT_EVIDENCE_FAMILY_MANIFEST_INTEGRITY_INVALID"

    with adapter_session() as db:
        project, estimate, first_stored, _, _, manifest = _approved_family(db, ordinal=1504)
        first_stored.sha256 = "f" * 64
        db.flush()

        with pytest.raises(ReportEvidenceFamilyManifestError) as drifted:
            require_approved_report_evidence_family_manifest(
                db,
                report_evidence_family_manifest_id=manifest.id,
                project_id=project.id,
                estimate_id=estimate.id,
            )

        assert drifted.value.code == "REPORT_EVIDENCE_FAMILY_MANIFEST_SOURCE_MISMATCH"

    with adapter_session() as db:
        project, estimate, _, _, _, manifest = _approved_family(db, ordinal=1505)
        other_project = _project(db, 1506)
        other_estimate = _estimate(db, other_project, 1506)

        with pytest.raises(ReportEvidenceFamilyManifestError) as foreign:
            require_approved_report_evidence_family_manifest(
                db,
                report_evidence_family_manifest_id=manifest.id,
                project_id=other_project.id,
                estimate_id=other_estimate.id,
            )

        assert foreign.value.code == "REPORT_EVIDENCE_FAMILY_MANIFEST_SOURCE_MISMATCH"