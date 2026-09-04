"""Bounded, proposal-only composition for selected report-Defect assessments.

The runner deliberately owns no OpenClaw, provider, canonical-write, technical,
commercial, lock, deployment, or release capability.  Its caller supplies a
no-tool inference port only after this module has read retained report bytes
under the established PostgreSQL containment lock and validated every selected
scope against those exact bytes.

An explicitly approved report family may use the same bounded runner only after
every member has completed this module's no-provider preflight. Family support
keeps member reports, scopes, runtime inputs, and resulting review packages
separate; it does not join evidence or create any new authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from sqlalchemy.orm import Session

from .canonical_submission_state import InitialSubmissionState
from .phase8_proposal_review import build_phase8_proposal_review
from .phase8_report_assessment_controller import (
    Phase8ReportAssessmentController,
    Phase8ReportAssessmentInferencePort,
)
from .phase8_report_assessment_input import (
    Phase8ReportAssessmentInputError,
    build_phase8_report_assessment_input,
)
from .phase8_report_assessment_prompts import validate_report_assessment_inference_profile
from .phase8_report_documentary_context import build_phase8_report_documentary_context
from .phase8_report_evidence_family_review_package import (
    Phase8ReportEvidenceFamilyReviewPackage,
    Phase8ReportEvidenceFamilyReviewPackageError,
    build_phase8_report_evidence_family_review_package,
)
from .phase8_report_review_package import (
    REPORT_EXPECTED_LABEL_MANIFEST_SCHEMA_V2,
    Phase8ReportReviewPackage,
    ReportDefectReviewOutcome,
    ReportDefectReviewSupportingFiles,
    build_phase8_report_review_package,
)
from .phase8_report_runtime_input import (
    Phase8ReportRuntimeInput,
    Phase8ReportRuntimeInputError,
    build_phase8_report_runtime_input,
)
from .phase8_visual_proposal import validate_visual_inference_profile
from .project_evidence import read_project_evidence_for_update
from .report_evidence_adapter import (
    REPORT_DEFECT_EVIDENCE_PACKET_SCHEMA_V2,
    ReportDefectEvidencePacket,
    build_report_defect_evidence_packets,
)
from .report_evidence_family_manifest import (
    ReportEvidenceFamilyManifestError,
    require_approved_report_evidence_family_manifest,
)
from .report_expected_label_manifest import (
    ApprovedReportExpectedLabelManifest,
    ReportExpectedLabelManifestError,
    require_approved_report_expected_label_manifest,
)

_PACKAGE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class Phase8ReportAssessmentRunnerError(RuntimeError):
    """Stable, content-safe failure before the proposal-only runner can proceed."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class Phase8ReportAssessmentRunnerResult:
    """One complete in-memory, proposal-only package for one retained report."""

    package: Phase8ReportReviewPackage

    @property
    def completion_receipt_sha256(self) -> str:
        return self.package.completion_receipt_file_sha256


def _fail(code: str) -> NoReturn:
    raise Phase8ReportAssessmentRunnerError(code)


def _required_text(value: object, *, code: str, maximum: int) -> str:
    if not isinstance(value, str):
        _fail(code)
    text = value.strip()
    if not text or len(text) > maximum:
        _fail(code)
    return text


def _bound_identifiers(
    *,
    project_id: object,
    estimate_id: object,
    stored_file_id: object,
    report_sha256: object,
) -> tuple[str, str, str, str]:
    project = _required_text(project_id, code="REPORT_RUNNER_PROJECT_INVALID", maximum=36)
    estimate = _required_text(estimate_id, code="REPORT_RUNNER_ESTIMATE_INVALID", maximum=36)
    stored_file = _required_text(
        stored_file_id,
        code="REPORT_RUNNER_STORED_FILE_INVALID",
        maximum=36,
    )
    report_hash = _required_text(
        report_sha256,
        code="REPORT_RUNNER_REPORT_SHA_INVALID",
        maximum=64,
    ).casefold()
    if _SHA256.fullmatch(report_hash) is None:
        _fail("REPORT_RUNNER_REPORT_SHA_INVALID")
    return project, estimate, stored_file, report_hash


def _package_binding(
    *,
    package_id: object,
    package_sha256: object,
    approval_reference: object,
) -> tuple[str, str, str]:
    identifier = _required_text(package_id, code="REPORT_RUNNER_PACKAGE_ID_INVALID", maximum=128)
    if _PACKAGE_ID.fullmatch(identifier) is None:
        _fail("REPORT_RUNNER_PACKAGE_ID_INVALID")
    package_hash = _required_text(
        package_sha256,
        code="REPORT_RUNNER_PACKAGE_SHA_INVALID",
        maximum=64,
    ).casefold()
    if _SHA256.fullmatch(package_hash) is None:
        _fail("REPORT_RUNNER_PACKAGE_SHA_INVALID")
    approval = _required_text(
        approval_reference,
        code="REPORT_RUNNER_APPROVAL_REFERENCE_INVALID",
        maximum=500,
    )
    return identifier, package_hash.upper(), approval


def _profiles(
    *,
    visual_inference_profile: object,
    report_assessment_inference_profile: object,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(visual_inference_profile, dict) or validate_visual_inference_profile(
        visual_inference_profile
    ):
        _fail("REPORT_RUNNER_VISUAL_PROFILE_INVALID")
    if not isinstance(report_assessment_inference_profile, dict) or (
        validate_report_assessment_inference_profile(report_assessment_inference_profile)
    ):
        _fail("REPORT_RUNNER_REPORT_PROFILE_INVALID")
    for field in ("implementation_revision", "provider", "physical_model", "validator_model"):
        if visual_inference_profile.get(field) != report_assessment_inference_profile.get(field):
            _fail("REPORT_RUNNER_PROFILE_MISMATCH")
    return visual_inference_profile, report_assessment_inference_profile


def _visual_packets(
    value: object,
    *,
    expected_labels: Mapping[str, str],
) -> dict[str, object | None]:
    if not isinstance(value, Mapping):
        _fail("REPORT_RUNNER_VISUAL_PACKETS_INVALID")
    packets: dict[str, object | None] = {}
    for raw_label, packet in value.items():
        label = _required_text(
            raw_label,
            code="REPORT_RUNNER_VISUAL_PACKETS_INVALID",
            maximum=150,
        )
        normalised = label.casefold()
        if normalised not in expected_labels or normalised in packets:
            _fail("REPORT_RUNNER_VISUAL_LABEL_MISMATCH")
        packets[normalised] = packet
    return packets


def _selected_packets(
    packets: tuple[ReportDefectEvidencePacket, ...],
    *,
    project_id: str,
    estimate_id: str,
    report_sha256: str,
    expected_labels: Mapping[str, str],
) -> dict[str, ReportDefectEvidencePacket]:
    by_label: dict[str, ReportDefectEvidencePacket] = {}
    for packet in packets:
        manifest = packet.manifest
        if (
            manifest.get("estimate_id") != estimate_id
            or manifest.get("report_sha256") != report_sha256
            or not isinstance(manifest.get("project_evidence_id"), str)
        ):
            _fail("REPORT_RUNNER_PACKET_BINDING_INVALID")
        label = manifest.get("report_defect_label")
        if not isinstance(label, str) or not label.strip():
            _fail("REPORT_RUNNER_PACKET_BINDING_INVALID")
        normalised = label.casefold()
        if normalised not in expected_labels or normalised in by_label:
            _fail("REPORT_RUNNER_EXPECTED_LABELS_MISMATCH")
        by_label[normalised] = packet
    if set(by_label) != set(expected_labels):
        _fail("REPORT_RUNNER_EXPECTED_LABELS_MISMATCH")
    # ``project_id`` is deliberately retained in this signature: access to the
    # report is asserted by the contained reader before these packet checks.
    del project_id
    return by_label


def _expected_label_manifest_bytes(
    *,
    packets_by_label: Mapping[str, ReportDefectEvidencePacket],
    package_id: str,
    package_sha256: str,
    approval_reference: str,
    approved_expected_label_manifest: ApprovedReportExpectedLabelManifest,
) -> bytes:
    packets = tuple(
        sorted(
            packets_by_label.values(),
            key=lambda packet: (
                str(packet.manifest["report_defect_label"]).casefold(),
                str(packet.manifest["defect_reference"]),
                str(packet.manifest["scope_id"]),
            ),
        )
    )
    first = packets[0].manifest
    return _json_bytes(
        {
            "schema": REPORT_EXPECTED_LABEL_MANIFEST_SCHEMA_V2,
            "project_evidence_id": first["project_evidence_id"],
            "report_sha256": first["report_sha256"],
            "estimate_id": first["estimate_id"],
            "package_id": package_id,
            "package_sha256": package_sha256,
            "approval_reference": approval_reference,
            "approved_expected_label_manifest_id": approved_expected_label_manifest.id,
            "approved_expected_label_manifest_sha256": (
                approved_expected_label_manifest.manifest_sha256
            ),
            "approved_expected_label_manifest_approval_reference": (
                approved_expected_label_manifest.approval_reference
            ),
            "expected_report_defect_labels": [
                packet.manifest["report_defect_label"] for packet in packets
            ],
        }
    )


def _json_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise Phase8ReportAssessmentRunnerError("REPORT_RUNNER_ARTIFACT_INVALID") from exc


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _protected_state(
    reader: Callable[[], InitialSubmissionState],
    *,
    estimate_id: str,
) -> InitialSubmissionState:
    try:
        state = reader()
    except Exception as exc:
        raise Phase8ReportAssessmentRunnerError(
            "REPORT_RUNNER_PROTECTED_STATE_UNAVAILABLE"
        ) from exc
    if not isinstance(state, InitialSubmissionState) or state.estimate_id != estimate_id:
        _fail("REPORT_RUNNER_PROTECTED_STATE_INVALID")
    return state


def _review_from_controller(
    *,
    controller_result: object,
    packet: ReportDefectEvidencePacket,
    package_id: str,
    runtime_input: Phase8ReportRuntimeInput,
    package_sha256: str,
    approval_reference: str,
) -> tuple[dict[str, Any], ReportDefectReviewSupportingFiles]:
    visual_result = getattr(controller_result, "visual_result", None)
    report_receipt = getattr(controller_result, "receipt", None)
    visual_receipt = getattr(visual_result, "receipt", None)
    proposal = getattr(visual_result, "proposal", None)
    if not isinstance(visual_receipt, dict) or not isinstance(report_receipt, dict):
        _fail("REPORT_RUNNER_CONTROLLER_RESULT_INVALID")
    proposal_bytes = _json_bytes(proposal) if isinstance(proposal, dict) else None
    visual_receipt_bytes = _json_bytes(visual_receipt)
    report_receipt_bytes = _json_bytes(report_receipt)
    review = build_phase8_proposal_review(
        package_id=package_id,
        package_sha256=package_sha256,
        approval_reference=approval_reference,
        proposal_file_bytes=proposal_bytes,
        proposal_file_sha256=_sha256(proposal_bytes) if proposal_bytes is not None else None,
        controller_receipt_file_bytes=visual_receipt_bytes,
        controller_receipt_file_sha256=_sha256(visual_receipt_bytes),
        evidence_manifest=runtime_input.visual_packet.manifest,
        documentary_evidence_packet=packet,
        report_assessment_controller_receipt_file_bytes=report_receipt_bytes,
        report_assessment_controller_receipt_file_sha256=_sha256(report_receipt_bytes),
    )
    return review, ReportDefectReviewSupportingFiles(
        visual_controller_receipt_file_bytes=visual_receipt_bytes,
        report_assessment_controller_receipt_file_bytes=report_receipt_bytes,
        phase8_proposal_review_file_bytes=_json_bytes(review),
        proposal_file_bytes=proposal_bytes,
    )


@dataclass(frozen=True, slots=True)
class Phase8ReportAssessmentRunnerRequest:
    """One explicitly bound single-report request inside a family run."""

    stored_file_id: object
    report_sha256: object
    package_id: object
    package_sha256: object
    approval_reference: object
    approved_expected_label_manifest_id: object
    visual_packets_by_report_defect_label: object


@dataclass(frozen=True, slots=True)
class _PreparedPhase8ReportAssessment:
    """Validated report inputs held before any inference port is created."""

    project_id: str
    estimate_id: str
    package_id: str
    package_sha256: str
    approval_reference: str
    visual_profile: dict[str, Any]
    report_profile: dict[str, Any]
    packets: tuple[ReportDefectEvidencePacket, ...]
    expected_label_manifest_file_bytes: bytes
    outcomes: dict[str, ReportDefectReviewOutcome]
    runnable: tuple[tuple[ReportDefectEvidencePacket, Phase8ReportRuntimeInput], ...]


@dataclass(frozen=True, slots=True)
class Phase8ReportEvidenceFamilyAssessmentRunnerResult:
    """A complete, ordered family package made from separately run report members."""

    package: Phase8ReportEvidenceFamilyReviewPackage

    @property
    def completion_receipt_sha256(self) -> str:
        return self.package.completion_receipt_file_sha256


def _prepare_phase8_report_assessment(
    db: Session,
    *,
    project_id: object,
    estimate_id: object,
    stored_file_id: object,
    report_sha256: object,
    package_id: object,
    package_sha256: object,
    approval_reference: object,
    approved_expected_label_manifest_id: object,
    visual_packets_by_report_defect_label: object,
    visual_inference_profile: object,
    report_assessment_inference_profile: object,
    storage_root: Path,
) -> _PreparedPhase8ReportAssessment:
    """Read and validate one report without creating an inference port."""

    project, estimate, stored_file, expected_sha = _bound_identifiers(
        project_id=project_id,
        estimate_id=estimate_id,
        stored_file_id=stored_file_id,
        report_sha256=report_sha256,
    )
    package_identifier, package_hash, approval = _package_binding(
        package_id=package_id,
        package_sha256=package_sha256,
        approval_reference=approval_reference,
    )
    visual_profile, report_profile = _profiles(
        visual_inference_profile=visual_inference_profile,
        report_assessment_inference_profile=report_assessment_inference_profile,
    )
    verified_content = read_project_evidence_for_update(
        db,
        stored_file_id=stored_file,
        project_id=project,
        estimate_id=estimate,
        storage_root=storage_root,
    )
    if verified_content.sha256 != expected_sha:
        _fail("REPORT_RUNNER_REPORT_SHA_MISMATCH")
    try:
        approved_expected_label_manifest = require_approved_report_expected_label_manifest(
            db,
            expected_label_manifest_id=approved_expected_label_manifest_id,
            project_id=project,
            estimate_id=estimate,
            stored_file_id=stored_file,
            report_sha256=expected_sha,
        )
    except ReportExpectedLabelManifestError as exc:
        raise Phase8ReportAssessmentRunnerError(
            "REPORT_RUNNER_EXPECTED_LABEL_MANIFEST_INVALID"
        ) from exc
    expected_labels = {
        label.casefold(): label
        for label in approved_expected_label_manifest.expected_report_defect_labels
    }
    visual_packets = _visual_packets(
        visual_packets_by_report_defect_label,
        expected_labels=expected_labels,
    )
    packets = build_report_defect_evidence_packets(
        db,
        stored_file_id=stored_file,
        project_id=project,
        estimate_id=estimate,
    )
    packets_by_label = _selected_packets(
        packets,
        project_id=project,
        estimate_id=estimate,
        report_sha256=expected_sha,
        expected_labels=expected_labels,
    )
    for packet in packets_by_label.values():
        manifest = packet.manifest
        if (
            manifest.get("schema") != REPORT_DEFECT_EVIDENCE_PACKET_SCHEMA_V2
            or manifest.get("approved_expected_label_manifest_id")
            != approved_expected_label_manifest.id
            or manifest.get("approved_expected_label_manifest_sha256")
            != approved_expected_label_manifest.manifest_sha256
            or manifest.get("approved_expected_label_manifest_approval_reference")
            != approved_expected_label_manifest.approval_reference
        ):
            _fail("REPORT_RUNNER_EXPECTED_LABEL_MANIFEST_INVALID")
    expected_label_manifest_file_bytes = _expected_label_manifest_bytes(
        packets_by_label=packets_by_label,
        package_id=package_identifier,
        package_sha256=package_hash,
        approval_reference=approval,
        approved_expected_label_manifest=approved_expected_label_manifest,
    )
    documentary_contexts = {
        label: build_phase8_report_documentary_context(
            report_packet=packet,
            verified_content=verified_content,
        )
        for label, packet in packets_by_label.items()
    }
    outcomes: dict[str, ReportDefectReviewOutcome] = {}
    runnable: list[tuple[ReportDefectEvidencePacket, Phase8ReportRuntimeInput]] = []
    for label, packet in packets_by_label.items():
        visual_packet = visual_packets.get(label)
        if visual_packet is None:
            outcomes[str(packet.manifest["scope_id"])] = ReportDefectReviewOutcome(
                no_proposal_status="RETRIEVAL_BLOCKED",
                blocker_code="VISUAL_EVIDENCE_REQUIRED",
            )
            continue
        try:
            assessment_input = build_phase8_report_assessment_input(
                report_packet=packet,
                visual_packet=visual_packet,
            )
            runtime_input = build_phase8_report_runtime_input(
                assessment_input=assessment_input,
                documentary_context=documentary_contexts[label],
            )
        except (Phase8ReportAssessmentInputError, Phase8ReportRuntimeInputError):
            outcomes[str(packet.manifest["scope_id"])] = ReportDefectReviewOutcome(
                no_proposal_status="MALFORMED_INPUT",
                blocker_code="VISUAL_EVIDENCE_INVALID",
            )
            continue
        runnable.append((packet, runtime_input))
    return _PreparedPhase8ReportAssessment(
        project_id=project,
        estimate_id=estimate,
        package_id=package_identifier,
        package_sha256=package_hash,
        approval_reference=approval,
        visual_profile=visual_profile,
        report_profile=report_profile,
        packets=packets,
        expected_label_manifest_file_bytes=expected_label_manifest_file_bytes,
        outcomes=outcomes,
        runnable=tuple(runnable),
    )


def _execute_prepared_phase8_report_assessment(
    prepared: _PreparedPhase8ReportAssessment,
    *,
    inference_port_factory: Callable[
        [Phase8ReportRuntimeInput], Phase8ReportAssessmentInferencePort
    ],
    protected_state_reader: Callable[[], InitialSubmissionState],
    max_correction_passes: int,
) -> dict[str, ReportDefectReviewOutcome]:
    """Run a preflighted report without rereading or changing its scope bindings."""

    outcomes = dict(prepared.outcomes)
    for packet, runtime_input in prepared.runnable:
        try:
            inference_port = inference_port_factory(runtime_input)
        except Exception as exc:
            raise Phase8ReportAssessmentRunnerError(
                "REPORT_RUNNER_INFERENCE_PORT_UNAVAILABLE"
            ) from exc
        controller = Phase8ReportAssessmentController(
            run_id=f"{prepared.package_id}-{packet.manifest['scope_id']}",
            runtime_input=runtime_input,
            visual_inference_profile=prepared.visual_profile,
            report_assessment_inference_profile=prepared.report_profile,
            inference_port=inference_port,
            protected_state_reader=protected_state_reader,
            max_correction_passes=max_correction_passes,
        )
        phase8_review, supporting_files = _review_from_controller(
            controller_result=controller.run(),
            packet=packet,
            runtime_input=runtime_input,
            package_id=prepared.package_id,
            package_sha256=prepared.package_sha256,
            approval_reference=prepared.approval_reference,
        )
        outcomes[str(packet.manifest["scope_id"])] = ReportDefectReviewOutcome(
            phase8_proposal_review=phase8_review,
            supporting_files=supporting_files,
        )
    return outcomes


def _package_from_prepared_phase8_report_assessment(
    prepared: _PreparedPhase8ReportAssessment,
    *,
    outcomes: dict[str, ReportDefectReviewOutcome],
    protected_state_before: InitialSubmissionState,
    protected_state_after: InitialSubmissionState,
) -> Phase8ReportReviewPackage:
    return build_phase8_report_review_package(
        package_id=prepared.package_id,
        package_sha256=prepared.package_sha256,
        approval_reference=prepared.approval_reference,
        packets=prepared.packets,
        outcomes_by_scope=outcomes,
        protected_state_before=protected_state_before,
        protected_state_after=protected_state_after,
        expected_label_manifest_file_bytes=prepared.expected_label_manifest_file_bytes,
    )


def execute_phase8_report_assessment_runner(
    db: Session,
    *,
    project_id: object,
    estimate_id: object,
    stored_file_id: object,
    report_sha256: object,
    package_id: object,
    package_sha256: object,
    approval_reference: object,
    approved_expected_label_manifest_id: object,
    visual_packets_by_report_defect_label: object,
    visual_inference_profile: object,
    report_assessment_inference_profile: object,
    inference_port_factory: Callable[
        [Phase8ReportRuntimeInput], Phase8ReportAssessmentInferencePort
    ],
    protected_state_reader: Callable[[], InitialSubmissionState],
    storage_root: Path,
    max_correction_passes: int = 2,
) -> Phase8ReportAssessmentRunnerResult:
    """Compose one retained report into deterministic, proposal-only review artifacts.

    The caller must own an active PostgreSQL transaction for the entire call.
    Retained report bytes are held under the existing clean-byte containment
    lock until every documentary context has been validated and every injected
    no-tool inference call has returned. This function never commits.
    """

    if not callable(inference_port_factory) or not callable(protected_state_reader):
        _fail("REPORT_RUNNER_EXECUTION_CAPABILITY_INVALID")
    prepared = _prepare_phase8_report_assessment(
        db,
        project_id=project_id,
        estimate_id=estimate_id,
        stored_file_id=stored_file_id,
        report_sha256=report_sha256,
        package_id=package_id,
        package_sha256=package_sha256,
        approval_reference=approval_reference,
        approved_expected_label_manifest_id=approved_expected_label_manifest_id,
        visual_packets_by_report_defect_label=visual_packets_by_report_defect_label,
        visual_inference_profile=visual_inference_profile,
        report_assessment_inference_profile=report_assessment_inference_profile,
        storage_root=storage_root,
    )
    before = _protected_state(protected_state_reader, estimate_id=prepared.estimate_id)
    outcomes = _execute_prepared_phase8_report_assessment(
        prepared,
        inference_port_factory=inference_port_factory,
        protected_state_reader=protected_state_reader,
        max_correction_passes=max_correction_passes,
    )
    after = _protected_state(protected_state_reader, estimate_id=prepared.estimate_id)
    package = _package_from_prepared_phase8_report_assessment(
        prepared,
        outcomes=outcomes,
        protected_state_before=before,
        protected_state_after=after,
    )
    return Phase8ReportAssessmentRunnerResult(package=package)


def _family_member_requests(
    value: object,
    *,
    approved_family_stored_file_ids: tuple[str, ...],
) -> tuple[Phase8ReportAssessmentRunnerRequest, ...]:
    if not isinstance(value, Mapping) or set(value) != set(approved_family_stored_file_ids):
        _fail("REPORT_FAMILY_RUNNER_MEMBER_REQUESTS_MISMATCH")
    requests: list[Phase8ReportAssessmentRunnerRequest] = []
    package_ids: set[str] = set()
    for stored_file_id in approved_family_stored_file_ids:
        request = value[stored_file_id]
        if not isinstance(request, Phase8ReportAssessmentRunnerRequest):
            _fail("REPORT_FAMILY_RUNNER_MEMBER_REQUESTS_INVALID")
        bound_stored_file_id = _required_text(
            request.stored_file_id,
            code="REPORT_FAMILY_RUNNER_MEMBER_REQUESTS_INVALID",
            maximum=36,
        )
        if bound_stored_file_id != stored_file_id:
            _fail("REPORT_FAMILY_RUNNER_MEMBER_SOURCE_MISMATCH")
        identifier, _, _ = _package_binding(
            package_id=request.package_id,
            package_sha256=request.package_sha256,
            approval_reference=request.approval_reference,
        )
        if identifier in package_ids:
            _fail("REPORT_FAMILY_RUNNER_MEMBER_PACKAGES_INVALID")
        package_ids.add(identifier)
        requests.append(request)
    return tuple(requests)


def execute_phase8_report_evidence_family_assessment_runner(
    db: Session,
    *,
    project_id: object,
    estimate_id: object,
    report_evidence_family_manifest_id: object,
    package_id: object,
    package_sha256: object,
    approval_reference: object,
    member_requests_by_stored_file: object,
    visual_inference_profile: object,
    report_assessment_inference_profile: object,
    inference_port_factory: Callable[
        [Phase8ReportRuntimeInput], Phase8ReportAssessmentInferencePort
    ],
    protected_state_reader: Callable[[], InitialSubmissionState],
    storage_root: Path,
    max_correction_passes: int = 2,
) -> Phase8ReportEvidenceFamilyAssessmentRunnerResult:
    """Run each approved family member only after the complete family preflight passes.

    The caller must own one active PostgreSQL clean-byte transaction for the
    whole call. Member reports keep their separate V2 expected-label scopes and
    runtime inputs. No inference port is created until every member has passed
    retained-byte, approved-manifest, and scope validation. This function never
    commits or grants canonical, technical, commercial, lock, deployment, or
    release authority.
    """

    if not isinstance(db, Session):
        _fail("REPORT_FAMILY_RUNNER_SESSION_INVALID")
    project = _required_text(project_id, code="REPORT_FAMILY_RUNNER_PROJECT_INVALID", maximum=36)
    estimate = _required_text(estimate_id, code="REPORT_FAMILY_RUNNER_ESTIMATE_INVALID", maximum=36)
    family_identifier = _required_text(
        report_evidence_family_manifest_id,
        code="REPORT_FAMILY_RUNNER_FAMILY_MANIFEST_INVALID",
        maximum=36,
    )
    family_package_id, family_package_hash, family_approval = _package_binding(
        package_id=package_id,
        package_sha256=package_sha256,
        approval_reference=approval_reference,
    )
    if not callable(inference_port_factory) or not callable(protected_state_reader):
        _fail("REPORT_FAMILY_RUNNER_EXECUTION_CAPABILITY_INVALID")
    try:
        approved_family = require_approved_report_evidence_family_manifest(
            db,
            report_evidence_family_manifest_id=family_identifier,
            project_id=project,
            estimate_id=estimate,
        )
    except ReportEvidenceFamilyManifestError as exc:
        raise Phase8ReportAssessmentRunnerError(
            "REPORT_FAMILY_RUNNER_FAMILY_MANIFEST_INVALID"
        ) from exc
    member_requests = _family_member_requests(
        member_requests_by_stored_file,
        approved_family_stored_file_ids=tuple(
            member.stored_file_id for member in approved_family.members
        ),
    )
    if family_package_id in {
        _package_binding(
            package_id=request.package_id,
            package_sha256=request.package_sha256,
            approval_reference=request.approval_reference,
        )[0]
        for request in member_requests
    }:
        _fail("REPORT_FAMILY_RUNNER_MEMBER_PACKAGES_INVALID")
    prepared_members: list[_PreparedPhase8ReportAssessment] = []
    for member, request in zip(approved_family.members, member_requests, strict=True):
        report_hash = _required_text(
            request.report_sha256,
            code="REPORT_FAMILY_RUNNER_MEMBER_SOURCE_MISMATCH",
            maximum=64,
        ).casefold()
        if report_hash != member.source_sha256:
            _fail("REPORT_FAMILY_RUNNER_MEMBER_SOURCE_MISMATCH")
        prepared_members.append(
            _prepare_phase8_report_assessment(
                db,
                project_id=project,
                estimate_id=estimate,
                stored_file_id=request.stored_file_id,
                report_sha256=request.report_sha256,
                package_id=request.package_id,
                package_sha256=request.package_sha256,
                approval_reference=request.approval_reference,
                approved_expected_label_manifest_id=request.approved_expected_label_manifest_id,
                visual_packets_by_report_defect_label=(
                    request.visual_packets_by_report_defect_label
                ),
                visual_inference_profile=visual_inference_profile,
                report_assessment_inference_profile=report_assessment_inference_profile,
                storage_root=storage_root,
            )
        )
    before = _protected_state(protected_state_reader, estimate_id=estimate)
    member_outcomes = tuple(
        _execute_prepared_phase8_report_assessment(
            prepared,
            inference_port_factory=inference_port_factory,
            protected_state_reader=protected_state_reader,
            max_correction_passes=max_correction_passes,
        )
        for prepared in prepared_members
    )
    after = _protected_state(protected_state_reader, estimate_id=estimate)
    if after != before:
        _fail("REPORT_FAMILY_RUNNER_PROTECTED_STATE_CHANGED")
    member_packages = {
        member.stored_file_id: _package_from_prepared_phase8_report_assessment(
            prepared,
            outcomes=outcomes,
            protected_state_before=before,
            protected_state_after=after,
        )
        for member, prepared, outcomes in zip(
            approved_family.members,
            prepared_members,
            member_outcomes,
            strict=True,
        )
    }
    try:
        package = build_phase8_report_evidence_family_review_package(
            db,
            project_id=project,
            estimate_id=estimate,
            report_evidence_family_manifest_id=approved_family.id,
            package_id=family_package_id,
            package_sha256=family_package_hash,
            approval_reference=family_approval,
            report_review_packages_by_stored_file=member_packages,
            protected_state_reader=protected_state_reader,
        )
    except Phase8ReportEvidenceFamilyReviewPackageError as exc:
        raise Phase8ReportAssessmentRunnerError(
            "REPORT_FAMILY_RUNNER_PACKAGE_INVALID"
        ) from exc
    return Phase8ReportEvidenceFamilyAssessmentRunnerResult(package=package)


__all__ = [
    "Phase8ReportAssessmentRunnerError",
    "Phase8ReportAssessmentRunnerRequest",
    "Phase8ReportAssessmentRunnerResult",
    "Phase8ReportEvidenceFamilyAssessmentRunnerResult",
    "execute_phase8_report_assessment_runner",
    "execute_phase8_report_evidence_family_assessment_runner",
]
