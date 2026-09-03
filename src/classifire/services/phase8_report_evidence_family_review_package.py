"""Aggregate approved report-family reviews without combining their evidence or execution.

Each family member remains a complete, validated single-report review package. This
module only binds those packages to an immutable human-approved report family and
keeps their scope, expected-label, source, and protected-state boundaries separate.
It performs no retrieval, inference, materialisation, canonical write, technical
selection, commercial pricing, lock, deployment, release, or commit.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, NoReturn

from sqlalchemy.orm import Session

from .canonical_submission_state import InitialSubmissionState, initial_submission_state
from .phase8_report_review_package import (
    REPORT_EXPECTED_LABEL_MANIFEST_SCHEMA_V2,
    Phase8ReportReviewPackage,
    validate_phase8_report_review_package,
)
from .phase8_visual_proposal import canonical_json_sha256
from .report_evidence_family_manifest import (
    ApprovedReportEvidenceFamilyManifest,
    ReportEvidenceFamilyManifestError,
    ReportEvidenceFamilyMemberBinding,
    require_approved_report_evidence_family_manifest,
)
from .report_expected_label_manifest import (
    ReportExpectedLabelManifestError,
    require_approved_report_expected_label_manifest,
)

PHASE8_REPORT_EVIDENCE_FAMILY_REVIEW_PACKAGE_SCHEMA = (
    "CLASSIFIRE-PHASE8-REPORT-EVIDENCE-FAMILY-REVIEW-PACKAGE-v1"
)
PHASE8_REPORT_EVIDENCE_FAMILY_REVIEW_COMPLETION_SCHEMA = (
    "CLASSIFIRE-PHASE8-REPORT-EVIDENCE-FAMILY-REVIEW-COMPLETION-v1"
)

_PACKAGE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")
_UPPER_SHA256 = re.compile(r"^[0-9A-F]{64}$")
_SOURCE_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_STATE_COUNT_FIELDS = (
    "defect_count",
    "evidence_count",
    "opening_count",
    "service_count",
    "service_opening_link_count",
    "active_physical_model_lock_count",
)
_NOOP_FLAGS = (
    "canonical_submission_performed",
    "technical_selection_performed",
    "commercial_pricing_performed",
    "physical_model_lock_created",
    "human_release_performed",
)


class Phase8ReportEvidenceFamilyReviewPackageError(ValueError):
    """Stable, content-safe failure while assembling a family review package."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ReportEvidenceFamilyReviewArtifact:
    """One family member and its independently validated single-report package."""

    member: ReportEvidenceFamilyMemberBinding
    report_review_package: Phase8ReportReviewPackage


@dataclass(frozen=True, slots=True)
class Phase8ReportEvidenceFamilyReviewPackage:
    """An in-memory, proposal-only collection of separate report review packages."""

    manifest: dict[str, Any]
    artifacts: tuple[ReportEvidenceFamilyReviewArtifact, ...]
    completion_receipt: dict[str, Any]
    files: dict[str, bytes]

    @property
    def completion_receipt_file_sha256(self) -> str:
        return _sha256_bytes(self.files["completion-receipt.json"])


def _fail(code: str) -> NoReturn:
    raise Phase8ReportEvidenceFamilyReviewPackageError(code)


def _required_text(value: object, *, code: str, maximum: int) -> str:
    if not isinstance(value, str):
        _fail(code)
    text = value.strip()
    if not text or len(text) > maximum:
        _fail(code)
    return text


def _package_binding(
    *,
    package_id: object,
    package_sha256: object,
    approval_reference: object,
) -> tuple[str, str, str]:
    identifier = _required_text(
        package_id,
        code="REPORT_FAMILY_REVIEW_PACKAGE_ID_INVALID",
        maximum=128,
    )
    if _PACKAGE_ID.fullmatch(identifier) is None:
        _fail("REPORT_FAMILY_REVIEW_PACKAGE_ID_INVALID")
    package_hash = _required_text(
        package_sha256,
        code="REPORT_FAMILY_REVIEW_PACKAGE_SHA_INVALID",
        maximum=64,
    ).upper()
    if _UPPER_SHA256.fullmatch(package_hash) is None:
        _fail("REPORT_FAMILY_REVIEW_PACKAGE_SHA_INVALID")
    approval = _required_text(
        approval_reference,
        code="REPORT_FAMILY_REVIEW_PACKAGE_APPROVAL_INVALID",
        maximum=500,
    )
    return identifier, package_hash, approval


def _identifier(value: object, *, code: str) -> str:
    return _required_text(value, code=code, maximum=36)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _json_file_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise Phase8ReportEvidenceFamilyReviewPackageError(
            "REPORT_FAMILY_REVIEW_PACKAGE_JSON_INVALID"
        ) from exc


def _require_clean_session(db: Session) -> None:
    if db.new or db.dirty or db.deleted:
        _fail("REPORT_FAMILY_REVIEW_PACKAGE_SESSION_DIRTY")


def _state_binding(state: object, *, estimate_id: str) -> dict[str, Any]:
    if not isinstance(state, InitialSubmissionState) or state.estimate_id != estimate_id:
        _fail("REPORT_FAMILY_REVIEW_PACKAGE_PROTECTED_STATE_INVALID")
    fingerprint = state.fingerprint
    counts = state.counts
    snapshot = state.snapshot
    if (
        not isinstance(fingerprint, str)
        or _UPPER_SHA256.fullmatch(fingerprint) is None
        or not isinstance(counts, dict)
        or set(counts) != set(_STATE_COUNT_FIELDS)
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in counts.values()
        )
        or not isinstance(snapshot, dict)
    ):
        _fail("REPORT_FAMILY_REVIEW_PACKAGE_PROTECTED_STATE_INVALID")
    return {
        "fingerprint": fingerprint,
        "snapshot_canonical_sha256": canonical_json_sha256(snapshot),
        "counts": {field: counts[field] for field in _STATE_COUNT_FIELDS},
    }


def _protected_state(
    reader: Callable[[], InitialSubmissionState],
    *,
    estimate_id: str,
) -> dict[str, Any]:
    try:
        state = reader()
    except Exception as exc:
        raise Phase8ReportEvidenceFamilyReviewPackageError(
            "REPORT_FAMILY_REVIEW_PACKAGE_PROTECTED_STATE_UNAVAILABLE"
        ) from exc
    return _state_binding(state, estimate_id=estimate_id)


def _expected_label_manifest(
    package: Phase8ReportReviewPackage,
) -> dict[str, Any]:
    value = package.expected_label_manifest_file_bytes
    if not isinstance(value, bytes):
        _fail("REPORT_FAMILY_REVIEW_PACKAGE_EXPECTED_LABEL_MANIFEST_REQUIRED")
    try:
        manifest = json.loads(value)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise Phase8ReportEvidenceFamilyReviewPackageError(
            "REPORT_FAMILY_REVIEW_PACKAGE_EXPECTED_LABEL_MANIFEST_INVALID"
        ) from exc
    expected_fields = {
        "schema",
        "project_evidence_id",
        "report_sha256",
        "estimate_id",
        "package_id",
        "package_sha256",
        "approval_reference",
        "approved_expected_label_manifest_id",
        "approved_expected_label_manifest_sha256",
        "approved_expected_label_manifest_approval_reference",
        "expected_report_defect_labels",
    }
    if (
        not isinstance(manifest, dict)
        or set(manifest) != expected_fields
        or manifest.get("schema") != REPORT_EXPECTED_LABEL_MANIFEST_SCHEMA_V2
        or value != _json_file_bytes(manifest)
    ):
        _fail("REPORT_FAMILY_REVIEW_PACKAGE_EXPECTED_LABEL_MANIFEST_INVALID")
    expected_labels = [
        str(artifact.packet.manifest["report_defect_label"]) for artifact in package.artifacts
    ]
    if manifest.get("expected_report_defect_labels") != expected_labels:
        _fail("REPORT_FAMILY_REVIEW_PACKAGE_EXPECTED_LABEL_MANIFEST_INVALID")
    return manifest


def _validate_member_package(
    db: Session,
    *,
    member: ReportEvidenceFamilyMemberBinding,
    package: object,
    project_id: str,
    estimate_id: str,
) -> Phase8ReportReviewPackage:
    if not isinstance(package, Phase8ReportReviewPackage) or validate_phase8_report_review_package(
        package
    ):
        _fail("REPORT_FAMILY_REVIEW_PACKAGE_MEMBER_PACKAGE_INVALID")
    manifest = package.manifest
    if (
        manifest.get("project_evidence_id") != member.project_evidence_id
        or manifest.get("report_sha256") != member.source_sha256
        or manifest.get("estimate_id") != estimate_id
    ):
        _fail("REPORT_FAMILY_REVIEW_PACKAGE_MEMBER_SOURCE_MISMATCH")
    approved_file = _expected_label_manifest(package)
    if (
        approved_file.get("project_evidence_id") != member.project_evidence_id
        or approved_file.get("report_sha256") != member.source_sha256
        or approved_file.get("estimate_id") != estimate_id
        or approved_file.get("package_id") != manifest.get("package_id")
        or approved_file.get("package_sha256") != manifest.get("package_sha256")
        or approved_file.get("approval_reference") != manifest.get("approval_reference")
    ):
        _fail("REPORT_FAMILY_REVIEW_PACKAGE_MEMBER_SOURCE_MISMATCH")
    try:
        approved = require_approved_report_expected_label_manifest(
            db,
            expected_label_manifest_id=approved_file["approved_expected_label_manifest_id"],
            project_id=project_id,
            estimate_id=estimate_id,
            stored_file_id=member.stored_file_id,
            report_sha256=member.source_sha256,
        )
    except (KeyError, ReportExpectedLabelManifestError) as exc:
        raise Phase8ReportEvidenceFamilyReviewPackageError(
            "REPORT_FAMILY_REVIEW_PACKAGE_EXPECTED_LABEL_MANIFEST_INVALID"
        ) from exc
    if (
        approved_file.get("approved_expected_label_manifest_sha256") != approved.manifest_sha256
        or approved_file.get("approved_expected_label_manifest_approval_reference")
        != approved.approval_reference
        or approved_file.get("expected_report_defect_labels")
        != list(approved.expected_report_defect_labels)
    ):
        _fail("REPORT_FAMILY_REVIEW_PACKAGE_EXPECTED_LABEL_MANIFEST_INVALID")
    return package


def _approved_family(
    db: Session,
    *,
    report_evidence_family_manifest_id: object,
    project_id: str,
    estimate_id: str,
) -> ApprovedReportEvidenceFamilyManifest:
    try:
        return require_approved_report_evidence_family_manifest(
            db,
            report_evidence_family_manifest_id=report_evidence_family_manifest_id,
            project_id=project_id,
            estimate_id=estimate_id,
        )
    except ReportEvidenceFamilyManifestError as exc:
        raise Phase8ReportEvidenceFamilyReviewPackageError(
            "REPORT_FAMILY_REVIEW_PACKAGE_FAMILY_MANIFEST_INVALID"
        ) from exc


def _selected_artifacts(
    db: Session,
    *,
    approved_family: ApprovedReportEvidenceFamilyManifest,
    report_review_packages_by_stored_file: object,
) -> tuple[ReportEvidenceFamilyReviewArtifact, ...]:
    if not isinstance(report_review_packages_by_stored_file, Mapping):
        _fail("REPORT_FAMILY_REVIEW_PACKAGE_MEMBER_PACKAGES_INVALID")
    expected_stored_file_ids = {member.stored_file_id for member in approved_family.members}
    if set(report_review_packages_by_stored_file) != expected_stored_file_ids:
        _fail("REPORT_FAMILY_REVIEW_PACKAGE_MEMBER_PACKAGES_MISMATCH")
    artifacts: list[ReportEvidenceFamilyReviewArtifact] = []
    for member in approved_family.members:
        package = _validate_member_package(
            db,
            member=member,
            package=report_review_packages_by_stored_file[member.stored_file_id],
            project_id=approved_family.project_id,
            estimate_id=approved_family.estimate_id,
        )
        artifacts.append(
            ReportEvidenceFamilyReviewArtifact(
                member=member,
                report_review_package=package,
            )
        )
    return tuple(artifacts)


def _receipt_state(package: Phase8ReportReviewPackage) -> dict[str, Any]:
    receipt = package.completion_receipt
    before = receipt.get("protected_state_before") if isinstance(receipt, dict) else None
    after = receipt.get("protected_state_after") if isinstance(receipt, dict) else None
    if not isinstance(before, dict) or before != after:
        _fail("REPORT_FAMILY_REVIEW_PACKAGE_PROTECTED_STATE_MISMATCH")
    return before


def _common_protected_state(
    artifacts: tuple[ReportEvidenceFamilyReviewArtifact, ...],
    *,
    live_state: dict[str, Any],
) -> dict[str, Any]:
    states = tuple(_receipt_state(artifact.report_review_package) for artifact in artifacts)
    if not states or any(state != states[0] for state in states[1:]) or states[0] != live_state:
        _fail("REPORT_FAMILY_REVIEW_PACKAGE_PROTECTED_STATE_MISMATCH")
    return states[0]


def _package_manifest_sha256(package: Phase8ReportReviewPackage) -> str:
    return canonical_json_sha256(package.manifest)


def _artifact_binding(artifact: ReportEvidenceFamilyReviewArtifact) -> dict[str, Any]:
    member = artifact.member
    package = artifact.report_review_package
    return {
        "member_sequence": member.member_sequence,
        "project_evidence_id": member.project_evidence_id,
        "stored_file_id": member.stored_file_id,
        "source_sha256": member.source_sha256,
        "report_review_package_manifest_canonical_sha256": _package_manifest_sha256(package),
        "report_review_completion_receipt_file_sha256": package.completion_receipt_file_sha256,
    }


def _manifest(
    *,
    package_id: str,
    package_sha256: str,
    approval_reference: str,
    report_evidence_family_manifest_id: str,
    report_evidence_family_manifest_sha256: str,
    report_evidence_family_manifest_approval_reference: str,
    project_id: str,
    estimate_id: str,
    artifacts: tuple[ReportEvidenceFamilyReviewArtifact, ...],
) -> dict[str, Any]:
    return {
        "schema": PHASE8_REPORT_EVIDENCE_FAMILY_REVIEW_PACKAGE_SCHEMA,
        "package_id": package_id,
        "package_sha256": package_sha256,
        "approval_reference": approval_reference,
        "report_evidence_family_manifest_id": report_evidence_family_manifest_id,
        "report_evidence_family_manifest_sha256": report_evidence_family_manifest_sha256,
        "report_evidence_family_manifest_approval_reference": (
            report_evidence_family_manifest_approval_reference
        ),
        "project_id": project_id,
        "estimate_id": estimate_id,
        "member_count": len(artifacts),
        "members": [_artifact_binding(artifact) for artifact in artifacts],
        "proposal_only": True,
        "canonical_submission_performed": False,
        "technical_selection_performed": False,
        "commercial_pricing_performed": False,
        "physical_model_lock_created": False,
        "human_release_performed": False,
    }


def _member_prefix(ordinal: int) -> str:
    return f"member-report-review-packages/{ordinal:04d}"


def _base_files(
    manifest: dict[str, Any],
    artifacts: tuple[ReportEvidenceFamilyReviewArtifact, ...],
) -> dict[str, bytes]:
    files = {"report-evidence-family-review-package.json": _json_file_bytes(manifest)}
    for ordinal, artifact in enumerate(artifacts, start=1):
        prefix = _member_prefix(ordinal)
        package_files = artifact.report_review_package.files
        for path in sorted(package_files):
            files[f"{prefix}/{path}"] = package_files[path]
    return files


def _completion_receipt(
    *,
    manifest: dict[str, Any],
    files: dict[str, bytes],
    protected_state: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": PHASE8_REPORT_EVIDENCE_FAMILY_REVIEW_COMPLETION_SCHEMA,
        "status": "COMPLETE_PROPOSAL_ONLY",
        "package_id": manifest["package_id"],
        "package_sha256": manifest["package_sha256"],
        "approval_reference": manifest["approval_reference"],
        "report_evidence_family_manifest_id": manifest["report_evidence_family_manifest_id"],
        "report_evidence_family_manifest_sha256": manifest[
            "report_evidence_family_manifest_sha256"
        ],
        "project_id": manifest["project_id"],
        "estimate_id": manifest["estimate_id"],
        "report_evidence_family_review_package_manifest_canonical_sha256": canonical_json_sha256(
            manifest
        ),
        "member_count": manifest["member_count"],
        "members": manifest["members"],
        "artifacts": {path: _sha256_bytes(value) for path, value in files.items()},
        "protected_state_before": protected_state,
        "protected_state_after": protected_state,
        "protected_state_unchanged": True,
        "proposal_only": True,
        "canonical_submission_performed": False,
        "technical_selection_performed": False,
        "commercial_pricing_performed": False,
        "physical_model_lock_created": False,
        "human_release_performed": False,
    }


def _valid_manifest(manifest: object) -> bool:
    expected_fields = {
        "schema",
        "package_id",
        "package_sha256",
        "approval_reference",
        "report_evidence_family_manifest_id",
        "report_evidence_family_manifest_sha256",
        "report_evidence_family_manifest_approval_reference",
        "project_id",
        "estimate_id",
        "member_count",
        "members",
        "proposal_only",
        *_NOOP_FLAGS,
    }
    if not isinstance(manifest, dict) or set(manifest) != expected_fields:
        return False
    if (
        manifest.get("schema") != PHASE8_REPORT_EVIDENCE_FAMILY_REVIEW_PACKAGE_SCHEMA
        or _PACKAGE_ID.fullmatch(str(manifest.get("package_id") or "")) is None
        or _UPPER_SHA256.fullmatch(str(manifest.get("package_sha256") or "")) is None
        or _UPPER_SHA256.fullmatch(
            str(manifest.get("report_evidence_family_manifest_sha256") or "")
        )
        is None
        or manifest.get("proposal_only") is not True
        or any(manifest.get(flag) is not False for flag in _NOOP_FLAGS)
    ):
        return False
    try:
        for field, maximum in (
            ("approval_reference", 500),
            ("report_evidence_family_manifest_id", 36),
            ("report_evidence_family_manifest_approval_reference", 500),
            ("project_id", 36),
            ("estimate_id", 36),
        ):
            _required_text(manifest.get(field), code="VALUE_INVALID", maximum=maximum)
    except Phase8ReportEvidenceFamilyReviewPackageError:
        return False
    members = manifest.get("members")
    return (
        not isinstance(manifest.get("member_count"), bool)
        and isinstance(manifest.get("member_count"), int)
        and manifest["member_count"] >= 2
        and isinstance(members, list)
        and len(members) == manifest["member_count"]
    )


def _validate_artifact_bindings(
    artifacts: object,
    *,
    manifest: dict[str, Any],
) -> list[str]:
    if not isinstance(artifacts, tuple) or len(artifacts) != manifest["member_count"]:
        return ["report family review package artifact count is invalid"]
    expected_members = manifest["members"]
    errors: list[str] = []
    for ordinal, artifact in enumerate(artifacts, start=1):
        if not isinstance(artifact, ReportEvidenceFamilyReviewArtifact):
            errors.append(f"report family review package artifact {ordinal} is invalid")
            continue
        package = artifact.report_review_package
        if validate_phase8_report_review_package(package):
            errors.append(f"report family review package member package {ordinal} is invalid")
            continue
        binding = _artifact_binding(artifact)
        if binding != expected_members[ordinal - 1]:
            errors.append(f"report family review package member binding {ordinal} is invalid")
        if binding["member_sequence"] != ordinal:
            errors.append(f"report family review package member order {ordinal} is invalid")
        if _SOURCE_SHA256.fullmatch(binding["source_sha256"]) is None:
            errors.append(f"report family review package source hash {ordinal} is invalid")
    if len(
        {
            artifact.member.stored_file_id
            for artifact in artifacts
            if isinstance(artifact, ReportEvidenceFamilyReviewArtifact)
        }
    ) != len(artifacts):
        errors.append("report family review package members are duplicated")
    return list(dict.fromkeys(errors))


def validate_phase8_report_evidence_family_review_package(package: object) -> list[str]:
    """Validate every retained member package and the aggregate no-write bindings."""

    if not isinstance(package, Phase8ReportEvidenceFamilyReviewPackage):
        return ["report family review package has an unsupported type"]
    manifest = package.manifest
    if not _valid_manifest(manifest):
        return ["report family review package manifest is invalid"]
    errors = _validate_artifact_bindings(package.artifacts, manifest=manifest)
    if errors:
        return errors
    artifacts = package.artifacts
    expected_manifest = _manifest(
        package_id=str(manifest["package_id"]),
        package_sha256=str(manifest["package_sha256"]),
        approval_reference=str(manifest["approval_reference"]),
        report_evidence_family_manifest_id=str(manifest["report_evidence_family_manifest_id"]),
        report_evidence_family_manifest_sha256=str(
            manifest["report_evidence_family_manifest_sha256"]
        ),
        report_evidence_family_manifest_approval_reference=str(
            manifest["report_evidence_family_manifest_approval_reference"]
        ),
        project_id=str(manifest["project_id"]),
        estimate_id=str(manifest["estimate_id"]),
        artifacts=artifacts,
    )
    if manifest != expected_manifest:
        errors.append("report family review package manifest is not member-bound")
        return errors
    base_files = _base_files(manifest, artifacts)
    receipt = package.completion_receipt
    state_before = receipt.get("protected_state_before") if isinstance(receipt, dict) else None
    state_after = receipt.get("protected_state_after") if isinstance(receipt, dict) else None
    if not isinstance(state_before, dict) or state_before != state_after:
        errors.append("report family review package protected state is invalid")
    else:
        expected_receipt = _completion_receipt(
            manifest=manifest,
            files=base_files,
            protected_state=state_before,
        )
        if receipt != expected_receipt:
            errors.append("report family review completion receipt is invalid")
    expected_files = dict(base_files)
    expected_files["completion-receipt.json"] = _json_file_bytes(receipt)
    if not isinstance(package.files, dict) or set(package.files) != set(expected_files):
        errors.append("report family review package file paths are invalid")
    elif any(not isinstance(value, bytes) for value in package.files.values()):
        errors.append("report family review package file bytes are invalid")
    elif any(package.files[path] != value for path, value in expected_files.items()):
        errors.append("report family review package file bytes are invalid")
    return list(dict.fromkeys(errors))


def build_phase8_report_evidence_family_review_package(
    db: Session,
    *,
    project_id: object,
    estimate_id: object,
    report_evidence_family_manifest_id: object,
    package_id: object,
    package_sha256: object,
    approval_reference: object,
    report_review_packages_by_stored_file: object,
    protected_state_reader: Callable[[], InitialSubmissionState] | None = None,
) -> Phase8ReportEvidenceFamilyReviewPackage:
    """Aggregate exact single-report packages under one approved family without execution."""

    if not isinstance(db, Session):
        _fail("REPORT_FAMILY_REVIEW_PACKAGE_SESSION_INVALID")
    project = _identifier(project_id, code="REPORT_FAMILY_REVIEW_PACKAGE_PROJECT_INVALID")
    estimate = _identifier(estimate_id, code="REPORT_FAMILY_REVIEW_PACKAGE_ESTIMATE_INVALID")
    identifier, package_hash, approval = _package_binding(
        package_id=package_id,
        package_sha256=package_sha256,
        approval_reference=approval_reference,
    )
    _require_clean_session(db)
    if protected_state_reader is None:

        def protected_state_reader() -> InitialSubmissionState:
            return initial_submission_state(db, estimate_id=estimate)

    with db.no_autoflush:
        approved_family = _approved_family(
            db,
            report_evidence_family_manifest_id=report_evidence_family_manifest_id,
            project_id=project,
            estimate_id=estimate,
        )
        artifacts = _selected_artifacts(
            db,
            approved_family=approved_family,
            report_review_packages_by_stored_file=report_review_packages_by_stored_file,
        )
        _require_clean_session(db)
        before = _common_protected_state(
            artifacts,
            live_state=_protected_state(protected_state_reader, estimate_id=estimate),
        )
        manifest = _manifest(
            package_id=identifier,
            package_sha256=package_hash,
            approval_reference=approval,
            report_evidence_family_manifest_id=approved_family.id,
            report_evidence_family_manifest_sha256=approved_family.manifest_sha256,
            report_evidence_family_manifest_approval_reference=approved_family.approval_reference,
            project_id=approved_family.project_id,
            estimate_id=approved_family.estimate_id,
            artifacts=artifacts,
        )
        files = _base_files(manifest, artifacts)
        receipt = _completion_receipt(
            manifest=manifest,
            files=files,
            protected_state=before,
        )
        files["completion-receipt.json"] = _json_file_bytes(receipt)
        _require_clean_session(db)
        after = _protected_state(protected_state_reader, estimate_id=estimate)
    if after != before:
        _fail("REPORT_FAMILY_REVIEW_PACKAGE_PROTECTED_STATE_MISMATCH")
    result = Phase8ReportEvidenceFamilyReviewPackage(
        manifest=manifest,
        artifacts=artifacts,
        completion_receipt=receipt,
        files=files,
    )
    if validate_phase8_report_evidence_family_review_package(result):
        _fail("REPORT_FAMILY_REVIEW_PACKAGE_BUILD_INVALID")
    return result


__all__ = [
    "PHASE8_REPORT_EVIDENCE_FAMILY_REVIEW_COMPLETION_SCHEMA",
    "PHASE8_REPORT_EVIDENCE_FAMILY_REVIEW_PACKAGE_SCHEMA",
    "Phase8ReportEvidenceFamilyReviewPackage",
    "Phase8ReportEvidenceFamilyReviewPackageError",
    "ReportEvidenceFamilyReviewArtifact",
    "build_phase8_report_evidence_family_review_package",
    "validate_phase8_report_evidence_family_review_package",
]
