from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_phase8_proposal_review import _Port as VisualPort
from test_phase8_proposal_review import _profile as visual_profile
from test_phase8_report_assessment_runner import (
    _documentary_proposal,
    _report_profile,
    _visual_packet,
)
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

import classifire.services.phase8_report_assessment_runner as runner_module
from classifire.models import Opening, ReportDefectScope, Service, User
from classifire.services.canonical_submission_state import InitialSubmissionState
from classifire.services.phase8_report_assessment_runner import (
    Phase8ReportAssessmentRunnerError,
    Phase8ReportAssessmentRunnerRequest,
    execute_phase8_report_evidence_family_assessment_runner,
)
from classifire.services.phase8_report_evidence_family_review_package import (
    validate_phase8_report_evidence_family_review_package,
)
from classifire.services.phase8_visual_evidence import RetainedVisualEvidencePacket
from classifire.services.report_evidence_adapter import (
    ReportDefectScopeBinding,
    bind_approved_report_defect_scopes,
    normalise_verified_pdf_report,
)
from classifire.services.report_evidence_family_manifest import (
    record_approved_report_evidence_family_manifest,
)
from classifire.services.report_expected_label_manifest import (
    record_approved_report_expected_label_manifest,
)


class _FamilyReportPort:
    def __init__(self, proposal: dict[str, object]) -> None:
        self._visual = VisualPort(proposal)
        self.calls = 0

    def invoke(
        self,
        *,
        role: str,
        stage: str,
        request: dict[str, object],
        rendered_prompt: object,
        runtime_input: object,
        report_assessment_inference_profile: dict[str, object],
    ) -> object:
        del rendered_prompt, runtime_input
        assert report_assessment_inference_profile == _report_profile()
        self.calls += 1
        return self._visual.invoke(role=role, stage=stage, request=request)


def _state(estimate_id: str) -> InitialSubmissionState:
    return InitialSubmissionState(
        estimate_id=estimate_id,
        fingerprint="A" * 64,
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
        email="family-runner-reviewer@example.test",
        full_name="Family runner reviewer",
        password_hash="not-used-by-synthetic-tests",  # noqa: S106
        role="reviewer",
    )
    db.add(reviewer)
    db.flush()
    return reviewer


def _member(
    db: Session,
    *,
    project: object,
    estimate: object,
    reviewer: User,
    content: object,
    label: str,
    ordinal: int,
) -> tuple[object, object, object]:
    stored = _bound_report(db, project, content)
    approved_manifest = record_approved_report_expected_label_manifest(
        db,
        project_id=project.id,
        estimate_id=estimate.id,
        stored_file_id=stored.id,
        report_sha256=content.sha256,
        expected_report_defect_labels=[label],
        approval_reference=f"synthetic family expected-label approval {ordinal}",
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
    return stored, content, approved_manifest


def _visual_packet_for(*, estimate_id: str, label: str) -> RetainedVisualEvidencePacket:
    source = _visual_packet(estimate_id=estimate_id)
    manifest = deepcopy(source.manifest)
    manifest["defect_reference"] = label
    return RetainedVisualEvidencePacket(manifest=manifest, files=source.files)


def _request(
    *,
    stored: object,
    content: object,
    approved_manifest: object,
    estimate: object,
    label: str,
    ordinal: int,
) -> Phase8ReportAssessmentRunnerRequest:
    return Phase8ReportAssessmentRunnerRequest(
        stored_file_id=stored.id,
        report_sha256=content.sha256,
        package_id=f"FAMILY-MEMBER-{ordinal}",
        package_sha256=str(ordinal) * 64,
        approval_reference=f"synthetic family member approval {ordinal}",
        approved_expected_label_manifest_id=approved_manifest.id,
        visual_packets_by_report_defect_label={
            label: _visual_packet_for(estimate_id=estimate.id, label=label)
        },
    )


def _family_values(db: Session) -> tuple[object, ...]:
    project = _project(db, 2601)
    estimate = _estimate(db, project, 2601)
    reviewer = _reviewer(db)
    first = _member(
        db,
        project=project,
        estimate=estimate,
        reviewer=reviewer,
        content=_report_content(),
        label="D-001",
        ordinal=1,
    )
    second = _member(
        db,
        project=project,
        estimate=estimate,
        reviewer=reviewer,
        content=_caption_report_content(caption_text="Figure 26: family runner report"),
        label="D-002",
        ordinal=2,
    )
    first_stored, first_content, first_manifest = first
    second_stored, second_content, second_manifest = second
    family = record_approved_report_evidence_family_manifest(
        db,
        project_id=project.id,
        estimate_id=estimate.id,
        family_reference="Synthetic ordered family runner",
        report_members=(
            {"stored_file_id": second_stored.id, "report_sha256": second_content.sha256},
            {"stored_file_id": first_stored.id, "report_sha256": first_content.sha256},
        ),
        approval_reference="synthetic human family runner approval",
        approved_by_user_id=reviewer.id,
    )
    return (
        project,
        estimate,
        family,
        first_stored,
        first_content,
        first_manifest,
        second_stored,
        second_content,
        second_manifest,
    )


def _proposal_for_runtime(runtime: object) -> dict[str, object]:
    proposal = _documentary_proposal(runtime)
    defect_reference = runtime.visual_packet.manifest["defect_reference"]
    assert isinstance(defect_reference, str)
    for opening in proposal["openings"]:
        opening["external_defect_id"] = defect_reference
    return proposal


def _run(
    db: Session,
    *,
    project: object,
    estimate: object,
    family: object,
    requests: object,
    factory: object,
) -> object:
    return execute_phase8_report_evidence_family_assessment_runner(
        db,
        project_id=project.id,
        estimate_id=estimate.id,
        report_evidence_family_manifest_id=family.id,
        package_id="FAMILY-RUNNER-2601",
        package_sha256="F" * 64,
        approval_reference="synthetic family runner package approval",
        member_requests_by_stored_file=requests,
        visual_inference_profile=visual_profile(),
        report_assessment_inference_profile=_report_profile(),
        inference_port_factory=factory,
        protected_state_reader=lambda: _state(estimate.id),
        storage_root=Path("unused-by-synthetic-reader"),
        max_correction_passes=0,
    )


def test_family_runner_preflights_every_member_before_ordered_proposal_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with adapter_session() as db:
        (
            project,
            estimate,
            family,
            first_stored,
            first_content,
            first_manifest,
            second_stored,
            second_content,
            second_manifest,
        ) = _family_values(db)
        reads: list[str] = []
        ports: list[_FamilyReportPort] = []
        content_by_stored_file = {
            first_stored.id: first_content,
            second_stored.id: second_content,
        }

        def read_verified(*_args: object, **kwargs: object) -> object:
            stored_file_id = kwargs["stored_file_id"]
            assert isinstance(stored_file_id, str)
            reads.append(stored_file_id)
            return content_by_stored_file[stored_file_id]

        def factory(runtime: object) -> _FamilyReportPort:
            port = _FamilyReportPort(_proposal_for_runtime(runtime))
            ports.append(port)
            return port

        monkeypatch.setattr(runner_module, "read_project_evidence_for_update", read_verified)
        result = _run(
            db,
            project=project,
            estimate=estimate,
            family=family,
            requests={
                first_stored.id: _request(
                    stored=first_stored,
                    content=first_content,
                    approved_manifest=first_manifest,
                    estimate=estimate,
                    label="D-001",
                    ordinal=1,
                ),
                second_stored.id: _request(
                    stored=second_stored,
                    content=second_content,
                    approved_manifest=second_manifest,
                    estimate=estimate,
                    label="D-002",
                    ordinal=2,
                ),
            },
            factory=factory,
        )

        assert reads == [second_stored.id, first_stored.id]
        assert len(ports) == 2
        assert all(port.calls == 3 for port in ports)
        assert validate_phase8_report_evidence_family_review_package(result.package) == []
        assert [artifact.member.stored_file_id for artifact in result.package.artifacts] == [
            second_stored.id,
            first_stored.id,
        ]
        assert result.package.manifest["proposal_only"] is True
        assert all(
            result.package.manifest[flag] is False
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


def test_family_runner_rejects_a_later_member_before_creating_any_inference_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with adapter_session() as db:
        (
            project,
            estimate,
            family,
            first_stored,
            first_content,
            first_manifest,
            second_stored,
            second_content,
            second_manifest,
        ) = _family_values(db)
        legacy_scope = db.scalar(
            select(ReportDefectScope).where(
                ReportDefectScope.source_sha256 == first_content.sha256,
                ReportDefectScope.report_defect_label == "D-001",
            )
        )
        assert isinstance(legacy_scope, ReportDefectScope)
        legacy_scope.approved_expected_label_manifest_id = None
        db.flush()
        requests = {
            first_stored.id: _request(
                stored=first_stored,
                content=first_content,
                approved_manifest=first_manifest,
                estimate=estimate,
                label="D-001",
                ordinal=1,
            ),
            second_stored.id: _request(
                stored=second_stored,
                content=second_content,
                approved_manifest=second_manifest,
                estimate=estimate,
                label="D-002",
                ordinal=2,
            ),
        }
        reads: list[str] = []

        def read_verified(*_args: object, **kwargs: object) -> object:
            stored_file_id = kwargs["stored_file_id"]
            assert isinstance(stored_file_id, str)
            reads.append(stored_file_id)
            return {
                first_stored.id: first_content,
                second_stored.id: second_content,
            }[stored_file_id]

        monkeypatch.setattr(runner_module, "read_project_evidence_for_update", read_verified)
        factory_calls: list[object] = []

        def factory(_runtime: object) -> object:
            factory_calls.append(object())
            raise AssertionError("family preflight must finish before a port is created")

        with pytest.raises(Phase8ReportAssessmentRunnerError) as rejected:
            _run(
                db,
                project=project,
                estimate=estimate,
                family=family,
                requests=requests,
                factory=factory,
            )

        assert rejected.value.code == "REPORT_RUNNER_EXPECTED_LABEL_MANIFEST_INVALID"
        assert reads == [second_stored.id, first_stored.id]
        assert factory_calls == []