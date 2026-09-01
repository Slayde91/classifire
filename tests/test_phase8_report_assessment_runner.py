from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_phase8_proposal_review import _Port as VisualPort
from test_phase8_proposal_review import _profile as visual_profile
from test_phase8_report_runtime_input import _visual_packet as _source_visual_packet
from test_phase8_visual_proposal import _proposal
from test_report_evidence_adapter import (
    _bound_report,
    _defect,
    _estimate,
    _project,
    _register_report_evidence_locators,
    _report_content,
    adapter_session,
)

import classifire.services.phase8_report_assessment_runner as runner_module
from classifire.models import (
    Opening,
    ReportEvidenceLocator,
    ReportExpectedLabelManifest,
    Service,
    User,
)
from classifire.services.canonical_submission_state import InitialSubmissionState
from classifire.services.phase8_openresponses_transport import (
    Phase8OpenResponsesTransportError,
)
from classifire.services.phase8_report_assessment_prompts import (
    build_report_assessment_inference_profile,
)
from classifire.services.phase8_report_assessment_runner import (
    Phase8ReportAssessmentRunnerError,
    execute_phase8_report_assessment_runner,
)
from classifire.services.phase8_report_review_package import (
    REPORT_EXPECTED_LABEL_MANIFEST_SCHEMA_V2,
    materialise_phase8_report_review_package,
    validate_phase8_report_review_package,
)
from classifire.services.phase8_visual_evidence import RetainedVisualEvidencePacket
from classifire.services.report_evidence_adapter import (
    bind_report_defect_scope,
    normalise_verified_pdf_report,
)
from classifire.services.report_expected_label_manifest import (
    record_approved_report_expected_label_manifest,
)
from classifire.services.storage import StoredFileBindingError


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
        email="report-runner-reviewer@example.test",
        full_name="Report runner reviewer",
        password_hash="not-used-by-synthetic-tests",  # noqa: S106
        role="reviewer",
    )
    db.add(reviewer)
    db.flush()
    return reviewer


def _approved_label_manifest_id(db: Session, *, estimate_id: str) -> str:
    manifest_id = db.scalar(
        select(ReportExpectedLabelManifest.id).where(
            ReportExpectedLabelManifest.estimate_id == estimate_id
        )
    )
    assert isinstance(manifest_id, str)
    return manifest_id


def _report_profile() -> dict[str, object]:
    return build_report_assessment_inference_profile(
        implementation_revision="a" * 40,
        provider="test-provider",
        physical_model="physical-test-model",
        validator_model="validator-test-model",
    )


def _scoped_report(db: Session) -> tuple[object, object, object, object]:
    content = _report_content()
    project = _project(db, 901)
    estimate = _estimate(db, project, 901)
    stored = _bound_report(db, project, content)
    reviewer = _reviewer(db)
    record_approved_report_expected_label_manifest(
        db,
        project_id=project.id,
        estimate_id=estimate.id,
        stored_file_id=stored.id,
        report_sha256=content.sha256,
        expected_report_defect_labels=["D-001"],
        approval_reference="synthetic expected-label approval",
        approved_by_user_id=reviewer.id,
    )
    defect = _defect(db, estimate)
    locators = _register_report_evidence_locators(
        db,
        stored_file_id=stored.id,
        project_id=project.id,
        estimate_id=estimate.id,
        report=normalise_verified_pdf_report(content),
    )
    page_locators = tuple(locator for locator in locators if locator.page_number == 1)
    bind_report_defect_scope(
        db,
        stored_file_id=stored.id,
        project_id=project.id,
        estimate_id=estimate.id,
        defect_id=defect.id,
        report_defect_label="D-001",
        start_locator_key=page_locators[0].locator_key,
        end_locator_key=page_locators[-1].locator_key,
    )
    return project, estimate, stored, content


def _visual_packet(*, estimate_id: str) -> RetainedVisualEvidencePacket:
    source = _source_visual_packet()
    manifest = deepcopy(source.manifest)
    manifest["estimate_id"] = estimate_id
    return RetainedVisualEvidencePacket(
        manifest=manifest,
        files=tuple(replace(item) for item in source.files),
    )


def _documentary_proposal(runtime: object) -> dict[str, object]:
    allowed_refs = runtime.allowed_evidence_refs
    documentary_ref = next(value for value in allowed_refs if value.startswith("report-locator:"))
    proposal = _proposal()
    for subject in ("openings", "services"):
        for row in proposal[subject]:
            for assessment in row["property_assessments"].values():
                assessment["evidence_refs"] = [documentary_ref]
    proposal["services"][0]["source_reference"] = documentary_ref
    return proposal


class _ReportPort:
    def __init__(
        self, proposal: dict[str, object] | None = None, *, transport_failure: bool = False
    ):
        self._visual = VisualPort(proposal or _proposal())
        self._transport_failure = transport_failure
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
        self.calls += 1
        assert report_assessment_inference_profile == _report_profile()
        assert "Private annotation content" in rendered_prompt.text
        if self._transport_failure:
            raise Phase8OpenResponsesTransportError("GATEWAY_TIMEOUT")
        return self._visual.invoke(role=role, stage=stage, request=request)


def _run(
    db: Session,
    *,
    project: object,
    estimate: object,
    stored: object,
    content: object,
    visual_packets: object,
    factory: object,
    **overrides: object,
) -> object:
    if "approved_expected_label_manifest_id" in overrides:
        approved_expected_label_manifest_id = overrides["approved_expected_label_manifest_id"]
    else:
        approved_expected_label_manifest_id = _approved_label_manifest_id(
            db, estimate_id=estimate.id
        )
    values = {
        "project_id": project.id,
        "estimate_id": estimate.id,
        "stored_file_id": stored.id,
        "report_sha256": content.sha256,
        "package_id": "REPORT-RUNNER-901",
        "package_sha256": "9" * 64,
        "approval_reference": "synthetic report assessment runner test",
        "approved_expected_label_manifest_id": approved_expected_label_manifest_id,
        "visual_packets_by_report_defect_label": visual_packets,
        "visual_inference_profile": visual_profile(),
        "report_assessment_inference_profile": _report_profile(),
        "inference_port_factory": factory,
        "protected_state_reader": lambda: _state(estimate.id),
        "storage_root": Path("unused-by-synthetic-reader"),
        "max_correction_passes": 0,
    }
    values.update(overrides)
    return execute_phase8_report_assessment_runner(db, **values)


def test_runner_composes_exact_report_context_and_deterministic_success_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    with adapter_session() as db:
        project, estimate, stored, content = _scoped_report(db)
        reads: list[object] = []
        ports: list[_ReportPort] = []

        def read_verified(*_args: object, **_kwargs: object) -> object:
            reads.append(object())
            return content

        def factory(runtime: object) -> _ReportPort:
            port = _ReportPort(_documentary_proposal(runtime))
            ports.append(port)
            return port

        monkeypatch.setattr(runner_module, "read_project_evidence_for_update", read_verified)
        first = _run(
            db,
            project=project,
            estimate=estimate,
            stored=stored,
            content=content,
            visual_packets={"D-001": _visual_packet(estimate_id=estimate.id)},
            factory=factory,
        )
        second = _run(
            db,
            project=project,
            estimate=estimate,
            stored=stored,
            content=content,
            visual_packets={"d-001": _visual_packet(estimate_id=estimate.id)},
            factory=factory,
        )

        assert len(reads) == 2
        assert len(ports) == 2
        assert all(port.calls == 3 for port in ports)
        assert first.package.files == second.package.files
        assert first.completion_receipt_sha256 == second.completion_receipt_sha256
        review = first.package.artifacts[0].review
        assert review["review_status"] == "PHASE8_REVIEW_AVAILABLE"
        assert review["phase8_review_binding"]["phase8_review_status"] == "ASSESSMENT_AVAILABLE"
        phase8_review_path = "phase8-proposal-reviews/0001.json"
        assert phase8_review_path in first.package.files
        assert phase8_review_path in first.package.completion_receipt["artifacts"]
        expected_labels_path = "expected-report-defect-labels.json"
        assert expected_labels_path in first.package.files
        assert expected_labels_path in first.package.completion_receipt["artifacts"]
        expected_labels = json.loads(first.package.files[expected_labels_path])
        assert expected_labels["schema"] == REPORT_EXPECTED_LABEL_MANIFEST_SCHEMA_V2
        assert expected_labels[
            "approved_expected_label_manifest_id"
        ] == _approved_label_manifest_id(db, estimate_id=estimate.id)
        assert len(expected_labels["approved_expected_label_manifest_sha256"]) == 64
        assert expected_labels["expected_report_defect_labels"] == ["D-001"]

        assert first.package.artifacts[0].supporting_files is not None
        assert "Private report heading" not in str(first.package)
        assert "Private annotation content" not in str(first.package)
        assert all(
            first.package.completion_receipt[field] is False
            for field in (
                "canonical_submission_performed",
                "technical_selection_performed",
                "commercial_pricing_performed",
                "physical_model_lock_created",
                "human_release_performed",
            )
        )
        output = tmp_path / "package"
        materialise_phase8_report_review_package(first.package, output=output)
        assert (output / "completion-receipt.json").read_bytes() == first.package.files[
            "completion-receipt.json"
        ]
        assert (output / phase8_review_path).read_bytes() == first.package.files[phase8_review_path]
        assert db.scalars(select(Opening)).all() == []
        assert db.scalars(select(Service)).all() == []


@pytest.mark.parametrize(
    "path",
    (
        "visual-controller-receipts/0001.json",
        "report-assessment-controller-receipts/0001.json",
        "phase8-proposal-reviews/0001.json",
        "expected-report-defect-labels.json",
    ),
)
def test_runner_receipt_hashes_every_supporting_artifact(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    with adapter_session() as db:
        project, estimate, stored, content = _scoped_report(db)

        monkeypatch.setattr(
            runner_module,
            "read_project_evidence_for_update",
            lambda *_args, **_kwargs: content,
        )

        result = _run(
            db,
            project=project,
            estimate=estimate,
            stored=stored,
            content=content,
            visual_packets={"D-001": _visual_packet(estimate_id=estimate.id)},
            factory=lambda runtime: _ReportPort(_documentary_proposal(runtime)),
        )
        files = dict(result.package.files)
        files[path] += b" "

        errors = validate_phase8_report_review_package(replace(result.package, files=files))

        assert any("file bytes are invalid" in error for error in errors)


@pytest.mark.parametrize(
    ("visual_packets", "factory_kind", "review_status", "phase8_status"),
    [
        ({}, "unexpected", "RETRIEVAL_BLOCKED", None),
        ({"D-001": object()}, "unexpected", "MALFORMED_INPUT", None),
        (
            {"D-001": "insufficient"},
            "insufficient",
            "PHASE8_REVIEW_AVAILABLE",
            "INSUFFICIENT_EVIDENCE",
        ),
        ({"D-001": "transport"}, "transport", "PHASE8_REVIEW_AVAILABLE", "NO_PROPOSAL"),
    ],
)
def test_runner_emits_one_safe_outcome_for_each_synthetic_case(
    monkeypatch: pytest.MonkeyPatch,
    visual_packets: dict[str, object],
    factory_kind: str,
    review_status: str,
    phase8_status: str | None,
) -> None:
    with adapter_session() as db:
        project, estimate, stored, content = _scoped_report(db)
        factory_calls = 0

        monkeypatch.setattr(
            runner_module,
            "read_project_evidence_for_update",
            lambda *_args, **_kwargs: content,
        )

        def factory(runtime: object) -> _ReportPort:
            nonlocal factory_calls
            factory_calls += 1
            if factory_kind == "unexpected":
                raise AssertionError("retrieval and malformed outcomes must not invoke a port")
            if factory_kind == "insufficient":
                proposal = {
                    "status": "INSUFFICIENT_EVIDENCE",
                    "assessment_schema": "CLASSIFIRE-PHASE8-PROPERTY-ASSESSMENTS-v2",
                    "limitations": ["The supplied views cannot resolve the opening boundary."],
                    "openings": [],
                    "services": [],
                }
                return _ReportPort(proposal)
            return _ReportPort(transport_failure=True)

        packets = {
            label: (
                _visual_packet(estimate_id=estimate.id)
                if value in {"insufficient", "transport"}
                else value
            )
            for label, value in visual_packets.items()
        }
        result = _run(
            db,
            project=project,
            estimate=estimate,
            stored=stored,
            content=content,
            visual_packets=packets,
            factory=factory,
        )

        assert len(result.package.artifacts) == 1
        review = result.package.artifacts[0].review
        assert review["review_status"] == review_status
        assert review["phase8_review_binding"]["phase8_review_status"] == phase8_status
        if review_status == "RETRIEVAL_BLOCKED":
            assert review["blocker_code"] == "VISUAL_EVIDENCE_REQUIRED"
        if review_status == "MALFORMED_INPUT":
            assert review["blocker_code"] == "VISUAL_EVIDENCE_INVALID"
        if factory_kind == "unexpected":
            assert factory_calls == 0
        if factory_kind == "transport":
            assert factory_calls == 1
            controller_receipt = result.package.files[
                "visual-controller-receipts/0001.json"
            ].decode("utf-8")
            assert "GATEWAY_TIMEOUT" in controller_receipt


def test_runner_rejects_hash_label_profile_and_locator_drift_before_port_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with adapter_session() as db:
        project, estimate, stored, content = _scoped_report(db)
        calls = 0

        monkeypatch.setattr(
            runner_module,
            "read_project_evidence_for_update",
            lambda *_args, **_kwargs: content,
        )

        def factory(_runtime: object) -> _ReportPort:
            nonlocal calls
            calls += 1
            return _ReportPort()

        packet = _visual_packet(estimate_id=estimate.id)
        approved_manifest = db.scalar(
            select(ReportExpectedLabelManifest).where(
                ReportExpectedLabelManifest.estimate_id == estimate.id
            )
        )
        assert isinstance(approved_manifest, ReportExpectedLabelManifest)
        missing_scope_manifest = record_approved_report_expected_label_manifest(
            db,
            project_id=project.id,
            estimate_id=estimate.id,
            stored_file_id=stored.id,
            report_sha256=content.sha256,
            expected_report_defect_labels=["D-001", "D-002"],
            approval_reference="synthetic expected-label approval with a missing scope",
            approved_by_user_id=approved_manifest.approved_by_user_id,
        )
        with pytest.raises(
            Phase8ReportAssessmentRunnerError, match="REPORT_RUNNER_REPORT_SHA_MISMATCH"
        ):
            _run(
                db,
                project=project,
                estimate=estimate,
                stored=stored,
                content=content,
                visual_packets={"D-001": packet},
                factory=factory,
                report_sha256="0" * 64,
            )
        with pytest.raises(
            Phase8ReportAssessmentRunnerError, match="REPORT_RUNNER_EXPECTED_LABELS_MISMATCH"
        ):
            _run(
                db,
                project=project,
                estimate=estimate,
                stored=stored,
                content=content,
                visual_packets={"D-001": packet},
                factory=factory,
                approved_expected_label_manifest_id=missing_scope_manifest.id,
            )
        profile = _report_profile()
        profile["physical_model"] = "wrong-model"
        with pytest.raises(
            Phase8ReportAssessmentRunnerError, match="REPORT_RUNNER_PROFILE_MISMATCH"
        ):
            _run(
                db,
                project=project,
                estimate=estimate,
                stored=stored,
                content=content,
                visual_packets={"D-001": packet},
                factory=factory,
                report_assessment_inference_profile=profile,
            )

        locator = next(
            locator
            for locator in db.scalars(
                select(ReportEvidenceLocator).where(ReportEvidenceLocator.page_number == 1)
            )
        )
        locator.content_sha256 = "0" * 64
        db.flush()
        with pytest.raises(Exception, match="REPORT_DOCUMENTARY_CONTEXT_SOURCE_MISMATCH"):
            _run(
                db,
                project=project,
                estimate=estimate,
                stored=stored,
                content=content,
                visual_packets={"D-001": packet},
                factory=factory,
            )

        assert calls == 0


def test_runner_rejects_cross_project_report_before_port_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with adapter_session() as db:
        project, estimate, stored, content = _scoped_report(db)
        other_project = _project(db, 902)
        other_estimate = _estimate(db, other_project, 902)
        calls = 0

        monkeypatch.setattr(
            runner_module,
            "read_project_evidence_for_update",
            lambda *_args, **_kwargs: content,
        )

        def factory(_runtime: object) -> _ReportPort:
            nonlocal calls
            calls += 1
            return _ReportPort()

        with pytest.raises(Phase8ReportAssessmentRunnerError) as raised:
            _run(
                db,
                project=other_project,
                estimate=other_estimate,
                stored=stored,
                content=content,
                visual_packets={"D-001": _visual_packet(estimate_id=estimate.id)},
                factory=factory,
                approved_expected_label_manifest_id=_approved_label_manifest_id(
                    db, estimate_id=estimate.id
                ),
            )

        assert raised.value.code == "REPORT_RUNNER_EXPECTED_LABEL_MANIFEST_INVALID"
        assert calls == 0


def test_runner_calls_the_contained_reader_before_any_provider_in_sqlite(
    tmp_path: Path,
) -> None:
    with adapter_session() as db:
        project, estimate, stored, content = _scoped_report(db)
        calls = 0

        def factory(_runtime: object) -> _ReportPort:
            nonlocal calls
            calls += 1
            return _ReportPort()

        with pytest.raises(StoredFileBindingError) as raised:
            _run(
                db,
                project=project,
                estimate=estimate,
                stored=stored,
                content=content,
                visual_packets={"D-001": _visual_packet(estimate_id=estimate.id)},
                factory=factory,
                storage_root=tmp_path,
            )

        assert raised.value.code == "STORED_FILE_CONTAINMENT_SERIALIZATION_UNAVAILABLE"
        assert calls == 0
