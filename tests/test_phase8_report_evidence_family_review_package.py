from __future__ import annotations

import json
from dataclasses import replace

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_report_evidence_adapter import (
    _bound_report,
    _caption_report_content,
    _defect,
    _estimate,
    _project,
    _register_report_evidence_locators,
    _report_content,
    adapter_session,
)

from classifire.models import Opening, Service, User
from classifire.services.canonical_submission_state import InitialSubmissionState
from classifire.services.phase8_report_evidence_family_review_package import (
    Phase8ReportEvidenceFamilyReviewPackageError,
    build_phase8_report_evidence_family_review_package,
    validate_phase8_report_evidence_family_review_package,
)
from classifire.services.phase8_report_review_package import (
    REPORT_EXPECTED_LABEL_MANIFEST_SCHEMA_V2,
    ReportDefectReviewOutcome,
    build_phase8_report_review_package,
)
from classifire.services.report_evidence_adapter import (
    ReportDefectScopeBinding,
    bind_approved_report_defect_scopes,
    build_report_defect_evidence_packets,
    normalise_verified_pdf_report,
)
from classifire.services.report_evidence_family_manifest import (
    record_approved_report_evidence_family_manifest,
)
from classifire.services.report_expected_label_manifest import (
    record_approved_report_expected_label_manifest,
)


def _state(estimate_id: str, *, fingerprint: str = "A" * 64) -> InitialSubmissionState:
    return InitialSubmissionState(
        estimate_id=estimate_id,
        fingerprint=fingerprint,
        counts={
            "defect_count": 0,
            "evidence_count": 0,
            "opening_count": 0,
            "service_count": 0,
            "service_opening_link_count": 0,
            "active_physical_model_lock_count": 0,
        },
        snapshot={"schema": "CLASSIFIRE-INITIAL-SUBMISSION-STATE-v1"},
    )


def _reviewer(db: Session) -> User:
    reviewer = User(
        email="family-review-package-reviewer@example.test",
        full_name="Family review package reviewer",
        password_hash="not-used-by-synthetic-tests",  # noqa: S106
        role="reviewer",
    )
    db.add(reviewer)
    db.flush()
    return reviewer


def _expected_label_file(
    *,
    stored: object,
    estimate: object,
    approved_manifest: object,
    package_id: str,
    package_sha256: str,
    approval_reference: str,
    labels: list[str],
) -> bytes:
    return (
        json.dumps(
            {
                "schema": REPORT_EXPECTED_LABEL_MANIFEST_SCHEMA_V2,
                "project_evidence_id": approved_manifest.project_evidence_id,
                "report_sha256": stored.sha256,
                "estimate_id": estimate.id,
                "package_id": package_id,
                "package_sha256": package_sha256,
                "approval_reference": approval_reference,
                "approved_expected_label_manifest_id": approved_manifest.id,
                "approved_expected_label_manifest_sha256": approved_manifest.manifest_sha256,
                "approved_expected_label_manifest_approval_reference": (
                    approved_manifest.approval_reference
                ),
                "expected_report_defect_labels": labels,
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _member_package(
    db: Session,
    *,
    project: object,
    estimate: object,
    reviewer: User,
    content: object,
    label: str,
    ordinal: int,
    state: InitialSubmissionState,
    include_expected_label_file: bool = True,
) -> tuple[object, object]:
    stored = _bound_report(db, project, content)
    approved_manifest = record_approved_report_expected_label_manifest(
        db,
        project_id=project.id,
        estimate_id=estimate.id,
        stored_file_id=stored.id,
        report_sha256=content.sha256,
        expected_report_defect_labels=[label],
        approval_reference=f"synthetic expected-label approval {ordinal}",
        approved_by_user_id=reviewer.id,
    )
    defect = _defect(db, estimate, reference=label)
    locators = _register_report_evidence_locators(
        db,
        stored_file_id=stored.id,
        project_id=project.id,
        estimate_id=estimate.id,
        report=normalise_verified_pdf_report(content),
    )
    page_locators = tuple(locator for locator in locators if locator.page_number == 1)
    bind_approved_report_defect_scopes(
        db,
        stored_file_id=stored.id,
        project_id=project.id,
        estimate_id=estimate.id,
        expected_label_manifest_id=approved_manifest.id,
        scope_bindings=(
            ReportDefectScopeBinding(
                defect_id=defect.id,
                report_defect_label=label,
                start_locator_key=page_locators[0].locator_key,
                end_locator_key=page_locators[-1].locator_key,
            ),
        ),
    )
    package_id = f"REPORT-PACKAGE-{ordinal}"
    package_sha256 = str(ordinal % 10) * 64
    approval_reference = f"synthetic report-package approval {ordinal}"
    packets = build_report_defect_evidence_packets(
        db,
        stored_file_id=stored.id,
        project_id=project.id,
        estimate_id=estimate.id,
    )
    package = build_phase8_report_review_package(
        package_id=package_id,
        package_sha256=package_sha256,
        approval_reference=approval_reference,
        packets=packets,
        outcomes_by_scope={
            str(packet.manifest["scope_id"]): ReportDefectReviewOutcome(
                no_proposal_status="RETRIEVAL_BLOCKED",
                blocker_code="VISUAL_EVIDENCE_REQUIRED",
            )
            for packet in packets
        },
        protected_state_before=state,
        protected_state_after=state,
        expected_label_manifest_file_bytes=(
            _expected_label_file(
                stored=stored,
                estimate=estimate,
                approved_manifest=approved_manifest,
                package_id=package_id,
                package_sha256=package_sha256,
                approval_reference=approval_reference,
                labels=[label],
            )
            if include_expected_label_file
            else None
        ),
    )
    return stored, package


def _approved_family_with_packages(
    db: Session,
) -> tuple[object, object, object, object, object, object, object, InitialSubmissionState]:
    project = _project(db, 1601)
    estimate = _estimate(db, project, 1601)
    reviewer = _reviewer(db)
    state = _state(estimate.id)
    first_stored, first_package = _member_package(
        db,
        project=project,
        estimate=estimate,
        reviewer=reviewer,
        content=_report_content(),
        label="D-001",
        ordinal=1,
        state=state,
    )
    second_stored, second_package = _member_package(
        db,
        project=project,
        estimate=estimate,
        reviewer=reviewer,
        content=_caption_report_content(caption_text="Figure 13: second report"),
        label="D-002",
        ordinal=2,
        state=state,
    )
    family = record_approved_report_evidence_family_manifest(
        db,
        project_id=project.id,
        estimate_id=estimate.id,
        family_reference="Synthetic paired report set",
        report_members=(
            {"stored_file_id": second_stored.id, "report_sha256": second_stored.sha256},
            {"stored_file_id": first_stored.id, "report_sha256": first_stored.sha256},
        ),
        approval_reference="synthetic human family approval",
        approved_by_user_id=reviewer.id,
    )
    return (
        project,
        estimate,
        first_stored,
        first_package,
        second_stored,
        second_package,
        family,
        state,
    )


def _build(
    db: Session,
    *,
    project: object,
    estimate: object,
    first_stored: object,
    first_package: object,
    second_stored: object,
    second_package: object,
    family: object,
    state: InitialSubmissionState,
) -> object:
    return build_phase8_report_evidence_family_review_package(
        db,
        project_id=project.id,
        estimate_id=estimate.id,
        report_evidence_family_manifest_id=family.id,
        package_id="FAMILY-PACKAGE-1601",
        package_sha256="F" * 64,
        approval_reference="synthetic family package approval",
        report_review_packages_by_stored_file={
            first_stored.id: first_package,
            second_stored.id: second_package,
        },
        protected_state_reader=lambda: state,
    )


def test_family_package_is_ordered_source_bound_and_proposal_only() -> None:
    with adapter_session() as db:
        values = _approved_family_with_packages(db)
        (
            project,
            estimate,
            first_stored,
            first_package,
            second_stored,
            second_package,
            family,
            state,
        ) = values
        first = _build(
            db,
            project=project,
            estimate=estimate,
            first_stored=first_stored,
            first_package=first_package,
            second_stored=second_stored,
            second_package=second_package,
            family=family,
            state=state,
        )
        second = _build(
            db,
            project=project,
            estimate=estimate,
            first_stored=first_stored,
            first_package=first_package,
            second_stored=second_stored,
            second_package=second_package,
            family=family,
            state=state,
        )

        assert validate_phase8_report_evidence_family_review_package(first) == []
        assert first.files == second.files
        assert [artifact.member.stored_file_id for artifact in first.artifacts] == [
            second_stored.id,
            first_stored.id,
        ]
        assert [artifact.member.member_sequence for artifact in first.artifacts] == [1, 2]
        assert first.manifest["member_count"] == 2
        assert first.manifest["proposal_only"] is True
        assert all(
            first.manifest[flag] is False
            for flag in (
                "canonical_submission_performed",
                "technical_selection_performed",
                "commercial_pricing_performed",
                "physical_model_lock_created",
                "human_release_performed",
            )
        )
        assert db.scalar(select(func.count()).select_from(Opening)) == 0
        assert db.scalar(select(func.count()).select_from(Service)) == 0


def test_family_package_rejects_missing_unbound_or_swapped_member_packages() -> None:
    with adapter_session() as db:
        values = _approved_family_with_packages(db)
        (
            project,
            estimate,
            first_stored,
            first_package,
            second_stored,
            second_package,
            family,
            state,
        ) = values

        with pytest.raises(Phase8ReportEvidenceFamilyReviewPackageError) as missing:
            build_phase8_report_evidence_family_review_package(
                db,
                project_id=project.id,
                estimate_id=estimate.id,
                report_evidence_family_manifest_id=family.id,
                package_id="FAMILY-PACKAGE-1601",
                package_sha256="F" * 64,
                approval_reference="synthetic family package approval",
                report_review_packages_by_stored_file={first_stored.id: first_package},
                protected_state_reader=lambda: state,
            )
        assert missing.value.code == "REPORT_FAMILY_REVIEW_PACKAGE_MEMBER_PACKAGES_MISMATCH"

        with pytest.raises(Phase8ReportEvidenceFamilyReviewPackageError) as swapped:
            build_phase8_report_evidence_family_review_package(
                db,
                project_id=project.id,
                estimate_id=estimate.id,
                report_evidence_family_manifest_id=family.id,
                package_id="FAMILY-PACKAGE-1601",
                package_sha256="F" * 64,
                approval_reference="synthetic family package approval",
                report_review_packages_by_stored_file={
                    first_stored.id: second_package,
                    second_stored.id: first_package,
                },
                protected_state_reader=lambda: state,
            )
        assert swapped.value.code == "REPORT_FAMILY_REVIEW_PACKAGE_MEMBER_SOURCE_MISMATCH"

    with adapter_session() as db:
        values = _approved_family_with_packages(db)
        project, estimate, first_stored, _, second_stored, second_package, family, state = values
        reviewer = db.scalar(
            select(User).where(User.email == "family-review-package-reviewer@example.test")
        )
        assert reviewer is not None
        legacy_stored, legacy_package = _member_package(
            db,
            project=project,
            estimate=estimate,
            reviewer=reviewer,
            content=_caption_report_content(caption_text="Figure 14: legacy manifest"),
            label="D-003",
            ordinal=3,
            state=state,
            include_expected_label_file=False,
        )
        replacement_family = record_approved_report_evidence_family_manifest(
            db,
            project_id=project.id,
            estimate_id=estimate.id,
            family_reference="Synthetic family with unbound package",
            report_members=(
                {"stored_file_id": second_stored.id, "report_sha256": second_stored.sha256},
                {"stored_file_id": legacy_stored.id, "report_sha256": legacy_stored.sha256},
            ),
            approval_reference="synthetic human family approval",
            approved_by_user_id=reviewer.id,
        )

        with pytest.raises(Phase8ReportEvidenceFamilyReviewPackageError) as unbound:
            build_phase8_report_evidence_family_review_package(
                db,
                project_id=project.id,
                estimate_id=estimate.id,
                report_evidence_family_manifest_id=replacement_family.id,
                package_id="FAMILY-PACKAGE-1603",
                package_sha256="F" * 64,
                approval_reference="synthetic family package approval",
                report_review_packages_by_stored_file={
                    second_stored.id: second_package,
                    legacy_stored.id: legacy_package,
                },
                protected_state_reader=lambda: state,
            )
        assert unbound.value.code == "REPORT_FAMILY_REVIEW_PACKAGE_EXPECTED_LABEL_MANIFEST_REQUIRED"


def test_family_package_rejects_protected_state_drift_and_tampering() -> None:
    with adapter_session() as db:
        values = _approved_family_with_packages(db)
        (
            project,
            estimate,
            first_stored,
            first_package,
            second_stored,
            second_package,
            family,
            state,
        ) = values

        with pytest.raises(Phase8ReportEvidenceFamilyReviewPackageError) as drifted:
            _build(
                db,
                project=project,
                estimate=estimate,
                first_stored=first_stored,
                first_package=first_package,
                second_stored=second_stored,
                second_package=second_package,
                family=family,
                state=_state(estimate.id, fingerprint="B" * 64),
            )
        assert drifted.value.code == "REPORT_FAMILY_REVIEW_PACKAGE_PROTECTED_STATE_MISMATCH"

        package = _build(
            db,
            project=project,
            estimate=estimate,
            first_stored=first_stored,
            first_package=first_package,
            second_stored=second_stored,
            second_package=second_package,
            family=family,
            state=state,
        )
        forged = replace(package, files={**package.files, "completion-receipt.json": b"{}"})
        assert validate_phase8_report_evidence_family_review_package(forged)
