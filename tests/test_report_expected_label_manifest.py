from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_report_evidence_adapter import (
    _bound_report,
    _estimate,
    _project,
    _report_content,
    adapter_session,
)

from classifire.models import ReportExpectedLabelManifest, User
from classifire.services.report_expected_label_manifest import (
    ReportExpectedLabelManifestError,
    record_approved_report_expected_label_manifest,
    require_approved_report_expected_label_manifest,
)


def _reviewer(db: Session, *, ordinal: int) -> User:
    reviewer = User(
        email=f"expected-label-reviewer-{ordinal}@example.test",
        full_name="Expected label reviewer",
        password_hash="not-used-by-synthetic-tests",  # noqa: S106
        role="reviewer",
    )
    db.add(reviewer)
    db.flush()
    return reviewer


def _approved_manifest(
    db: Session,
    *,
    ordinal: int,
    labels: list[str] | None = None,
) -> tuple[object, object, object, object, object]:
    content = _report_content()
    project = _project(db, ordinal)
    estimate = _estimate(db, project, ordinal)
    stored = _bound_report(db, project, content)
    reviewer = _reviewer(db, ordinal=ordinal)
    manifest = record_approved_report_expected_label_manifest(
        db,
        project_id=project.id,
        estimate_id=estimate.id,
        stored_file_id=stored.id,
        report_sha256=content.sha256,
        expected_report_defect_labels=labels or ["D-002", "D-001"],
        approval_reference="synthetic human expected-label approval",
        approved_by_user_id=reviewer.id,
    )
    return project, estimate, stored, content, manifest


def test_recorded_manifest_is_deterministic_idempotent_and_source_bound() -> None:
    with adapter_session() as db:
        project, estimate, stored, content, first = _approved_manifest(db, ordinal=1201)
        reviewer_id = first.approved_by_user_id
        second = record_approved_report_expected_label_manifest(
            db,
            project_id=project.id,
            estimate_id=estimate.id,
            stored_file_id=stored.id,
            report_sha256=content.sha256,
            expected_report_defect_labels=["D-001", "D-002"],
            approval_reference="synthetic human expected-label approval",
            approved_by_user_id=reviewer_id,
        )
        loaded = require_approved_report_expected_label_manifest(
            db,
            expected_label_manifest_id=first.id,
            project_id=project.id,
            estimate_id=estimate.id,
            stored_file_id=stored.id,
            report_sha256=content.sha256,
        )

        assert second.id == first.id
        assert loaded == first
        assert first.expected_report_defect_labels == ("D-001", "D-002")
        assert len(first.manifest_sha256) == 64
        assert first.manifest_sha256 == first.manifest_sha256.upper()
        assert db.scalars(select(ReportExpectedLabelManifest)).all()


def test_manifest_tampering_or_foreign_estimate_fails_closed() -> None:
    with adapter_session() as db:
        project, estimate, stored, content, manifest = _approved_manifest(db, ordinal=1202)
        record = db.get(ReportExpectedLabelManifest, manifest.id)
        assert record is not None
        record.expected_report_defect_labels = ["D-999"]
        db.flush()

        with pytest.raises(ReportExpectedLabelManifestError) as raised:
            require_approved_report_expected_label_manifest(
                db,
                expected_label_manifest_id=manifest.id,
                project_id=project.id,
                estimate_id=estimate.id,
                stored_file_id=stored.id,
                report_sha256=content.sha256,
            )

        assert raised.value.code == "REPORT_EXPECTED_LABEL_MANIFEST_INTEGRITY_INVALID"

    with adapter_session() as db:
        project, estimate, stored, content, manifest = _approved_manifest(db, ordinal=1203)
        other_project = _project(db, 1204)
        other_estimate = _estimate(db, other_project, 1204)

        with pytest.raises(ReportExpectedLabelManifestError) as raised:
            require_approved_report_expected_label_manifest(
                db,
                expected_label_manifest_id=manifest.id,
                project_id=other_project.id,
                estimate_id=other_estimate.id,
                stored_file_id=stored.id,
                report_sha256=content.sha256,
            )

        assert raised.value.code == "REPORT_EXPECTED_LABEL_MANIFEST_SOURCE_MISMATCH"


@pytest.mark.parametrize("labels", ([], ["D-001", "d-001"], [" "]))
def test_record_rejects_missing_or_duplicate_labels(labels: list[str]) -> None:
    with adapter_session() as db:
        content = _report_content()
        project = _project(db, 1205)
        estimate = _estimate(db, project, 1205)
        stored = _bound_report(db, project, content)
        reviewer = _reviewer(db, ordinal=1205)

        with pytest.raises(ReportExpectedLabelManifestError) as raised:
            record_approved_report_expected_label_manifest(
                db,
                project_id=project.id,
                estimate_id=estimate.id,
                stored_file_id=stored.id,
                report_sha256=content.sha256,
                expected_report_defect_labels=labels,
                approval_reference="synthetic invalid expected-label approval",
                approved_by_user_id=reviewer.id,
            )

        assert raised.value.code == "REPORT_EXPECTED_LABEL_MANIFEST_LABELS_INVALID"
