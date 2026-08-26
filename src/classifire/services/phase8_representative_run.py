"""Approved-package, rollback-only execution boundary for the Phase 8 runner.

This boundary is deliberately separate from canonical admission and submission.
It accepts only a self-contained, explicitly approved package, uses a database
copy, and always rolls back the caller-owned transaction after the existing
proposal-only runner has completed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..models import StoredFile
from ..physical_models import EvidenceSource
from .canonical_submission_state import InitialSubmissionState, initial_submission_state
from .linked_image_retrieval import (
    DEFAULT_LINKED_IMAGE_POLICY,
    LinkedImageError,
    Resolver,
    Transport,
    resolve_public_addresses,
    validate_linked_image_photo_inventory_structure,
)
from .malware_scanning import MalwareScanner
from .phase8_human_reference_comparison import (
    Phase8HumanReferenceComparisonError,
    validate_phase8_human_reference,
)
from .phase8_linked_visual_run import (
    Phase8LinkedVisualRunResult,
    Phase8VisualInferencePortFactory,
    run_phase8_linked_visual_proposal,
)
from .phase8_openresponses_transport import (
    Phase8OpenResponsesTransportError,
    build_phase8_openresponses_transport_receipt_bundle,
)
from .phase8_visual_prompts import build_visual_inference_profile
from .phase8_visual_proposal import canonical_json_sha256
from .phase8_visual_runtime import (
    Phase8GatewayRpcError,
    validate_phase8_loopback_gateway_url,
)
from .storage import StoredFileSecurityError, require_clean_stored_file_for_session

REPRESENTATIVE_RUN_PACKAGE_SCHEMA = "CLASSIFIRE-PHASE8-REPRESENTATIVE-RUN-PACKAGE-v1"
REPRESENTATIVE_RUN_PREFLIGHT_RECEIPT_SCHEMA = "CLASSIFIRE-PHASE8-REPRESENTATIVE-RUN-PREFLIGHT-v1"
LEGACY_REPRESENTATIVE_RUN_RECEIPT_SCHEMA = "CLASSIFIRE-PHASE8-REPRESENTATIVE-RUN-v1"
REPRESENTATIVE_RUN_RECEIPT_SCHEMA = "CLASSIFIRE-PHASE8-REPRESENTATIVE-RUN-v2"
REPRESENTATIVE_RUN_APPROVAL_SCOPE = "rollback_only_linked_visual_proposal"
_MAX_PACKAGE_BYTES = 5 * 1024 * 1024
_GIT_REVISION = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_PACKAGE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")
_SOURCE_TREE_SCHEMA = "CLASSIFIRE-PHASE8-REPRESENTATIVE-SOURCE-TREE-v1"
_SOURCE_TREE_PATHS = (
    Path("src") / "classifire",
    Path("scripts") / "run_phase8_representative_package.py",
    Path("pyproject.toml"),
)
_SOURCE_TREE_SUFFIXES = frozenset({".json", ".py", ".toml"})
_IS_WINDOWS = os.name == "nt"
_WINDOWS_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class Phase8RepresentativeRunError(RuntimeError):
    """Stable fail-closed error for approved-package execution."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Phase 8 representative run failed: {code}.")


@dataclass(frozen=True, slots=True)
class Phase8RepresentativeRunPackage:
    package_id: str
    package_path: Path
    package_sha256: str
    approval_reference: str
    authorised_by: str
    authorised_at_utc: str
    report_sha256: str
    retrieval_hosts: tuple[str, ...]
    expected_git_revision: str
    expected_source_tree_sha256: str
    estimate_id: str
    defect_reference: str
    operator_reference: str
    report_path: Path
    photo_rows: tuple[dict[str, Any], ...]
    parent_evidence_by_photo_id: dict[str, str]
    database_copy_path: Path
    storage_root: Path
    retrieval_root: Path
    human_reference_path: Path
    gateway_command: tuple[Path, ...]
    gateway_base_url: str
    provider: str
    physical_model: str
    validator_model: str
    physical_agent_id: str
    validator_agent_id: str


@dataclass(frozen=True, slots=True)
class Phase8RepresentativeRunPreflight:
    package: Phase8RepresentativeRunPackage
    protected_state: InitialSubmissionState
    receipt: dict[str, Any]

    @property
    def receipt_sha256(self) -> str:
        return canonical_json_sha256(self.receipt)


@dataclass(frozen=True, slots=True)
class Phase8RepresentativeRunResult:
    package: Phase8RepresentativeRunPackage
    preflight: Phase8RepresentativeRunPreflight
    runner_result: Phase8LinkedVisualRunResult
    receipt: dict[str, Any]
    transport_receipt_bundle: dict[str, Any] | None = None

    @property
    def receipt_sha256(self) -> str:
        return canonical_json_sha256(self.receipt)


def _nonblank(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise Phase8RepresentativeRunError("PACKAGE_INVALID")
        value[key] = item
    return value


def _reject_nonfinite_json_value(_: str) -> None:
    raise Phase8RepresentativeRunError("PACKAGE_INVALID")


def _read_json_object(path: Path, *, code: str) -> tuple[dict[str, Any], bytes]:
    if not path.is_file():
        raise Phase8RepresentativeRunError(code)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise Phase8RepresentativeRunError(code) from exc
    if not raw or len(raw) > _MAX_PACKAGE_BYTES:
        raise Phase8RepresentativeRunError(code)
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonfinite_json_value,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Phase8RepresentativeRunError(code) from exc
    if not isinstance(value, dict):
        raise Phase8RepresentativeRunError(code)
    return value, raw


def _resolve_inside(root: Path, value: object, *, code: str, directory: bool) -> Path:
    text = _nonblank(value)
    candidate = Path(text)
    if not text or candidate.is_absolute() or ".." in candidate.parts:
        raise Phase8RepresentativeRunError(code)
    try:
        resolved_root = root.resolve(strict=True)
        resolved = (resolved_root / candidate).resolve(strict=True)
    except OSError as exc:
        raise Phase8RepresentativeRunError(code) from exc
    if resolved_root != resolved and resolved_root not in resolved.parents:
        raise Phase8RepresentativeRunError(code)
    if directory != resolved.is_dir():
        raise Phase8RepresentativeRunError(code)
    return resolved


def _sha256_file(path: Path, *, code: str) -> str:
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    except OSError as exc:
        raise Phase8RepresentativeRunError(code) from exc
    return digest


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    if not _IS_WINDOWS:
        return False
    attributes = getattr(path.lstat(), "st_file_attributes", None)
    return not isinstance(attributes, int) or bool(attributes & _WINDOWS_REPARSE_POINT)


def phase8_representative_source_tree_sha256(repository_root: Path) -> str:
    """Hash the executable source set for an uncommitted candidate worktree."""

    try:
        root = repository_root.resolve(strict=True)
    except OSError as exc:
        raise Phase8RepresentativeRunError("SOURCE_TREE_INVALID") from exc

    entries: list[dict[str, str]] = []
    for relative_target in _SOURCE_TREE_PATHS:
        requested = root / relative_target
        try:
            if _is_link_or_junction(requested):
                raise Phase8RepresentativeRunError("SOURCE_TREE_INVALID")
            target = requested.resolve(strict=True)
        except OSError as exc:
            raise Phase8RepresentativeRunError("SOURCE_TREE_INVALID") from exc
        if root not in target.parents and target != root:
            raise Phase8RepresentativeRunError("SOURCE_TREE_INVALID")
        try:
            candidates = target.rglob("*") if target.is_dir() else (target,)
            for candidate in sorted(candidates, key=lambda item: item.as_posix()):
                if _is_link_or_junction(candidate):
                    raise Phase8RepresentativeRunError("SOURCE_TREE_INVALID")
                if not candidate.is_file():
                    continue
                if candidate.suffix.lower() not in _SOURCE_TREE_SUFFIXES:
                    continue
                resolved = candidate.resolve(strict=True)
                relative = resolved.relative_to(root).as_posix()
                digest = hashlib.sha256(resolved.read_bytes()).hexdigest().upper()
                entries.append({"path": relative, "sha256": digest})
        except (OSError, ValueError) as exc:
            raise Phase8RepresentativeRunError("SOURCE_TREE_INVALID") from exc
    if not entries:
        raise Phase8RepresentativeRunError("SOURCE_TREE_INVALID")
    return canonical_json_sha256({"schema": _SOURCE_TREE_SCHEMA, "files": entries})


def _strict_keys(value: object, keys: set[str], *, code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise Phase8RepresentativeRunError(code)
    return value


def _parse_utc(value: object) -> str:
    text = _nonblank(value)
    if not text:
        raise Phase8RepresentativeRunError("APPROVAL_INVALID")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Phase8RepresentativeRunError("APPROVAL_INVALID") from exc
    if parsed.tzinfo is None:
        raise Phase8RepresentativeRunError("APPROVAL_INVALID")
    return text


def _load_photo_rows(path: Path, storage_root: Path) -> tuple[dict[str, Any], ...]:
    value, _raw = _read_json_object(path, code="PHOTO_ROWS_INVALID")
    if set(value) != {"photo_rows"} or not isinstance(value["photo_rows"], list):
        raise Phase8RepresentativeRunError("PHOTO_ROWS_INVALID")
    rows: list[dict[str, Any]] = []
    photo_ids: set[str] = set()
    for raw_row in value["photo_rows"]:
        if not isinstance(raw_row, dict):
            raise Phase8RepresentativeRunError("PHOTO_ROWS_INVALID")
        row = dict(raw_row)
        photo_id = _nonblank(row.get("photo_id"))
        if not photo_id or photo_id in photo_ids:
            raise Phase8RepresentativeRunError("PHOTO_ROWS_INVALID")
        row["native_path"] = str(
            _resolve_inside(
                storage_root,
                row.get("native_path"),
                code="PHOTO_ROWS_INVALID",
                directory=False,
            )
        )
        photo_ids.add(photo_id)
        rows.append(row)
    try:
        validate_linked_image_photo_inventory_structure(rows)
    except LinkedImageError:
        raise Phase8RepresentativeRunError("PHOTO_ROWS_INVALID") from None
    return tuple(rows)


def _load_parent_mapping(path: Path, photo_rows: tuple[dict[str, Any], ...]) -> dict[str, str]:
    value, _raw = _read_json_object(path, code="PARENT_MAPPING_INVALID")
    if set(value) != {"parent_evidence_by_photo_id"}:
        raise Phase8RepresentativeRunError("PARENT_MAPPING_INVALID")
    mapping = value["parent_evidence_by_photo_id"]
    if not isinstance(mapping, dict):
        raise Phase8RepresentativeRunError("PARENT_MAPPING_INVALID")
    normalized = {_nonblank(key): _nonblank(item) for key, item in mapping.items()}
    photo_ids = {_nonblank(row.get("photo_id")) for row in photo_rows}
    if set(normalized) != photo_ids or any(not item for item in normalized.values()):
        raise Phase8RepresentativeRunError("PARENT_MAPPING_INVALID")
    return normalized


def load_phase8_representative_run_package(path: Path) -> Phase8RepresentativeRunPackage:
    """Load an explicit approval and self-contained input package fail-closed."""

    package_path = path.resolve(strict=True)
    package_dir = package_path.parent
    raw, raw_bytes = _read_json_object(package_path, code="PACKAGE_INVALID")
    expected_keys = {"schema", "package_id", "approval", "execution", "inputs", "runtime"}
    if set(raw) != expected_keys or raw.get("schema") != REPRESENTATIVE_RUN_PACKAGE_SCHEMA:
        raise Phase8RepresentativeRunError("PACKAGE_INVALID")

    package_id = _nonblank(raw.get("package_id"))
    if not _PACKAGE_ID.fullmatch(package_id):
        raise Phase8RepresentativeRunError("PACKAGE_INVALID")

    approval = _strict_keys(
        raw.get("approval"),
        {
            "reference",
            "authorised_by",
            "authorised_at_utc",
            "scope",
            "report_sha256",
            "retrieval_hosts",
        },
        code="APPROVAL_INVALID",
    )
    approval_reference = _nonblank(approval.get("reference"))
    authorised_by = _nonblank(approval.get("authorised_by"))
    authorised_at_utc = _parse_utc(approval.get("authorised_at_utc"))
    report_sha256 = _nonblank(approval.get("report_sha256")).upper()
    hosts = approval.get("retrieval_hosts")
    if (
        not approval_reference
        or not authorised_by
        or approval.get("scope") != REPRESENTATIVE_RUN_APPROVAL_SCOPE
        or not _SHA256.fullmatch(report_sha256)
        or not isinstance(hosts, list)
        or any(not isinstance(host, str) or not host for host in hosts)
    ):
        raise Phase8RepresentativeRunError("APPROVAL_INVALID")
    retrieval_hosts = tuple(sorted(set(host.lower() for host in hosts)))
    if retrieval_hosts != tuple(sorted(DEFAULT_LINKED_IMAGE_POLICY.allowed_hosts)):
        raise Phase8RepresentativeRunError("RETRIEVAL_APPROVAL_INVALID")

    execution = _strict_keys(
        raw.get("execution"),
        {
            "expected_git_revision",
            "source_tree_sha256",
            "estimate_id",
            "defect_reference",
            "operator_reference",
            "rollback_only",
            "canonical_submission_allowed",
            "physical_model_lock_allowed",
            "human_reference_visible_to_inference",
        },
        code="EXECUTION_POLICY_INVALID",
    )
    expected_git_revision = _nonblank(execution.get("expected_git_revision")).lower()
    expected_source_tree_sha256 = _nonblank(execution.get("source_tree_sha256")).upper()
    estimate_id = _nonblank(execution.get("estimate_id"))
    defect_reference = _nonblank(execution.get("defect_reference"))
    operator_reference = _nonblank(execution.get("operator_reference"))
    if (
        not _GIT_REVISION.fullmatch(expected_git_revision)
        or not _SHA256.fullmatch(expected_source_tree_sha256)
        or not estimate_id
        or not defect_reference
        or not operator_reference
        or execution.get("rollback_only") is not True
        or execution.get("canonical_submission_allowed") is not False
        or execution.get("physical_model_lock_allowed") is not False
        or execution.get("human_reference_visible_to_inference") is not False
    ):
        raise Phase8RepresentativeRunError("EXECUTION_POLICY_INVALID")

    inputs = _strict_keys(
        raw.get("inputs"),
        {
            "report",
            "photo_rows",
            "parent_evidence_by_photo_id",
            "database_copy",
            "storage_root",
            "retrieval_root",
            "human_reference",
        },
        code="INPUTS_INVALID",
    )
    report_path = _resolve_inside(
        package_dir,
        inputs.get("report"),
        code="INPUTS_INVALID",
        directory=False,
    )
    database_copy_path = _resolve_inside(
        package_dir, inputs.get("database_copy"), code="INPUTS_INVALID", directory=False
    )
    storage_root = _resolve_inside(
        package_dir, inputs.get("storage_root"), code="INPUTS_INVALID", directory=True
    )
    retrieval_root = _resolve_inside(
        package_dir, inputs.get("retrieval_root"), code="INPUTS_INVALID", directory=True
    )
    photo_rows_path = _resolve_inside(
        package_dir, inputs.get("photo_rows"), code="INPUTS_INVALID", directory=False
    )
    parent_mapping_path = _resolve_inside(
        package_dir,
        inputs.get("parent_evidence_by_photo_id"),
        code="INPUTS_INVALID",
        directory=False,
    )
    human_reference_path = _resolve_inside(
        package_dir, inputs.get("human_reference"), code="INPUTS_INVALID", directory=False
    )
    if _sha256_file(report_path, code="REPORT_UNAVAILABLE") != report_sha256:
        raise Phase8RepresentativeRunError("REPORT_SHA256_MISMATCH")
    photo_rows = _load_photo_rows(photo_rows_path, storage_root)
    parent_mapping = _load_parent_mapping(parent_mapping_path, photo_rows)
    try:
        validate_phase8_human_reference(human_reference_path)
    except Phase8HumanReferenceComparisonError as exc:
        raise Phase8RepresentativeRunError("HUMAN_REFERENCE_INVALID") from exc

    runtime = _strict_keys(
        raw.get("runtime"),
        {
            "gateway_command",
            "gateway_base_url",
            "provider",
            "physical_model",
            "validator_model",
            "physical_agent_id",
            "validator_agent_id",
        },
        code="RUNTIME_INVALID",
    )
    command = runtime.get("gateway_command")
    if not isinstance(command, list) or not command:
        raise Phase8RepresentativeRunError("RUNTIME_INVALID")
    gateway_command = tuple(Path(_nonblank(item)) for item in command)
    if any(not item.is_absolute() or not item.is_file() for item in gateway_command):
        raise Phase8RepresentativeRunError("RUNTIME_INVALID")
    gateway_base_url = _nonblank(runtime.get("gateway_base_url"))
    try:
        validate_phase8_loopback_gateway_url(gateway_base_url)
    except Phase8GatewayRpcError as exc:
        raise Phase8RepresentativeRunError("RUNTIME_INVALID") from exc
    provider = _nonblank(runtime.get("provider"))
    physical_model = _nonblank(runtime.get("physical_model"))
    validator_model = _nonblank(runtime.get("validator_model"))
    physical_agent_id = _nonblank(runtime.get("physical_agent_id"))
    validator_agent_id = _nonblank(runtime.get("validator_agent_id"))
    if (
        not all(
            (
                gateway_base_url,
                provider,
                physical_model,
                validator_model,
                physical_agent_id,
                validator_agent_id,
            )
        )
        or physical_agent_id != "cf-phase8-visual-physical"
        or validator_agent_id != "cf-phase8-visual-validator"
    ):
        raise Phase8RepresentativeRunError("RUNTIME_INVALID")

    return Phase8RepresentativeRunPackage(
        package_id=package_id,
        package_path=package_path,
        package_sha256=hashlib.sha256(raw_bytes).hexdigest().upper(),
        approval_reference=approval_reference,
        authorised_by=authorised_by,
        authorised_at_utc=authorised_at_utc,
        report_sha256=report_sha256,
        retrieval_hosts=retrieval_hosts,
        expected_git_revision=expected_git_revision,
        expected_source_tree_sha256=expected_source_tree_sha256,
        estimate_id=estimate_id,
        defect_reference=defect_reference,
        operator_reference=operator_reference,
        report_path=report_path,
        photo_rows=photo_rows,
        parent_evidence_by_photo_id=parent_mapping,
        database_copy_path=database_copy_path,
        storage_root=storage_root,
        retrieval_root=retrieval_root,
        human_reference_path=human_reference_path,
        gateway_command=gateway_command,
        gateway_base_url=gateway_base_url,
        provider=provider,
        physical_model=physical_model,
        validator_model=validator_model,
        physical_agent_id=physical_agent_id,
        validator_agent_id=validator_agent_id,
    )


def _state_summary(state: InitialSubmissionState) -> dict[str, Any]:
    return {"fingerprint": state.fingerprint, "counts": dict(sorted(state.counts.items()))}


def _validate_parent_storage(
    db: Session,
    package: Phase8RepresentativeRunPackage,
) -> None:
    for evidence_id in package.parent_evidence_by_photo_id.values():
        evidence = db.get(EvidenceSource, evidence_id)
        if (
            evidence is None
            or evidence.estimate_id != package.estimate_id
            or evidence.status != "active"
            or not isinstance(evidence.sha256, str)
            or not evidence.sha256.strip()
        ):
            raise Phase8RepresentativeRunError("PARENT_EVIDENCE_INVALID")
        stored = db.get(StoredFile, evidence.stored_file_id) if evidence.stored_file_id else None
        if stored is None:
            raise Phase8RepresentativeRunError("PARENT_EVIDENCE_INVALID")
        try:
            require_clean_stored_file_for_session(
                db,
                stored,
                storage_root=package.storage_root,
                allowed_purposes={"project_evidence", "technical_evidence"},
                expected_sha256=evidence.sha256,
            )
        except StoredFileSecurityError:
            raise Phase8RepresentativeRunError("PARENT_EVIDENCE_INVALID") from None


def verify_phase8_representative_run_package(
    db: Session,
    package: Phase8RepresentativeRunPackage,
    *,
    actual_git_revision: str,
    repository_root: Path,
    protected_state_reader: Callable[[], InitialSubmissionState] | None = None,
) -> Phase8RepresentativeRunPreflight:
    """Validate package, source tree, and database copy without runtime activity."""

    actual_git_revision = _nonblank(actual_git_revision).lower()
    if not _GIT_REVISION.fullmatch(actual_git_revision):
        raise Phase8RepresentativeRunError("SOURCE_REVISION_INVALID")
    if actual_git_revision != package.expected_git_revision:
        raise Phase8RepresentativeRunError("SOURCE_REVISION_MISMATCH")
    actual_source_tree_sha256 = phase8_representative_source_tree_sha256(repository_root)
    if actual_source_tree_sha256 != package.expected_source_tree_sha256:
        raise Phase8RepresentativeRunError("SOURCE_TREE_MISMATCH")
    if protected_state_reader is None:

        def protected_state_reader() -> InitialSubmissionState:
            return initial_submission_state(db, estimate_id=package.estimate_id)

    try:
        _validate_parent_storage(db, package)
        if db.get_bind().dialect.name != "sqlite":
            raise Phase8RepresentativeRunError("DATABASE_COPY_UNSUPPORTED")
        state = protected_state_reader()
        if state.estimate_id != package.estimate_id:
            raise Phase8RepresentativeRunError("PROTECTED_STATE_INVALID")
    finally:
        db.rollback()
        db.expire_all()

    receipt = {
        "schema": REPRESENTATIVE_RUN_PREFLIGHT_RECEIPT_SCHEMA,
        "package_id": package.package_id,
        "package_sha256": package.package_sha256,
        "approval_reference": package.approval_reference,
        "authorised_by": package.authorised_by,
        "authorised_at_utc": package.authorised_at_utc,
        "source_revision": actual_git_revision,
        "source_tree_sha256": actual_source_tree_sha256,
        "report_sha256": package.report_sha256,
        "retrieval_hosts": list(package.retrieval_hosts),
        "protected_state": _state_summary(state),
        "preflight_only": True,
        "runtime_started": False,
        "retrieval_performed": False,
        "canonical_submission_performed": False,
        "physical_model_lock_created": False,
        "human_reference_visible_to_inference": False,
    }
    return Phase8RepresentativeRunPreflight(
        package=package,
        protected_state=state,
        receipt=receipt,
    )


def execute_phase8_representative_run(
    db: Session,
    package: Phase8RepresentativeRunPackage,
    *,
    actual_git_revision: str,
    repository_root: Path,
    inference_port_factory: Phase8VisualInferencePortFactory,
    malware_scanner: MalwareScanner,
    protected_state_reader: Callable[[], InitialSubmissionState] | None = None,
    resolver: Resolver = resolve_public_addresses,
    transport: Transport | None = None,
) -> Phase8RepresentativeRunResult:
    """Execute only an approved package and always roll back its outer session."""

    if protected_state_reader is None:

        def protected_state_reader() -> InitialSubmissionState:
            return initial_submission_state(db, estimate_id=package.estimate_id)

    preflight = verify_phase8_representative_run_package(
        db,
        package,
        actual_git_revision=actual_git_revision,
        repository_root=repository_root,
        protected_state_reader=protected_state_reader,
    )
    actual_git_revision = _nonblank(actual_git_revision).lower()
    before = preflight.protected_state
    db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    runner_result: Phase8LinkedVisualRunResult | None = None
    failure: BaseException | None = None
    try:
        runner_result = run_phase8_linked_visual_proposal(
            db,
            run_id=package.package_id,
            estimate_id=package.estimate_id,
            defect_reference=package.defect_reference,
            report=package.report_path,
            report_sha256=package.report_sha256,
            photo_rows=package.photo_rows,
            parent_evidence_by_photo_id=package.parent_evidence_by_photo_id,
            storage_root=package.storage_root,
            retrieval_root=package.retrieval_root,
            operator_reference=package.operator_reference,
            inference_profile=build_visual_inference_profile(
                implementation_revision=actual_git_revision,
                provider=package.provider,
                physical_model=package.physical_model,
                validator_model=package.validator_model,
            ),
            inference_port=None,
            inference_port_factory=inference_port_factory,
            protected_state_reader=protected_state_reader,
            malware_scanner=malware_scanner,
            resolver=resolver,
            transport=transport,
        )
    except BaseException as exc:
        failure = exc
    finally:
        db.rollback()
    db.expire_all()
    after = protected_state_reader()
    if before.estimate_id != package.estimate_id or after.estimate_id != package.estimate_id:
        raise Phase8RepresentativeRunError("PROTECTED_STATE_INVALID")
    if before.fingerprint != after.fingerprint or before.counts != after.counts:
        raise Phase8RepresentativeRunError("ROLLBACK_STATE_CHANGED")
    if failure is not None:
        raise failure
    assert runner_result is not None

    transport_receipt_bundle: dict[str, Any] | None = None
    if runner_result.visual_result is not None:
        try:
            transport_receipt_bundle = (
                build_phase8_openresponses_transport_receipt_bundle(
                    runner_result.transport_receipt_records,
                    controller_receipt=runner_result.visual_result.receipt,
                )
            )
        except Phase8OpenResponsesTransportError as exc:
            raise Phase8RepresentativeRunError(exc.code) from None
    elif runner_result.transport_receipt_records:
        raise Phase8RepresentativeRunError("TRANSPORT_RECEIPT_BUNDLE_INVALID")

    receipt = {
        "schema": REPRESENTATIVE_RUN_RECEIPT_SCHEMA,
        "package_id": package.package_id,
        "package_sha256": package.package_sha256,
        "approval_reference": package.approval_reference,
        "authorised_by": package.authorised_by,
        "authorised_at_utc": package.authorised_at_utc,
        "source_revision": actual_git_revision,
        "source_tree_sha256": preflight.receipt["source_tree_sha256"],
        "report_sha256": package.report_sha256,
        "retrieval_hosts": list(package.retrieval_hosts),
        "preflight_receipt_sha256": preflight.receipt_sha256,
        "runner_receipt_sha256": runner_result.receipt_sha256,
        "controller_receipt_sha256": (
            runner_result.visual_result.receipt_sha256
            if runner_result.visual_result is not None
            else None
        ),
        "transport_receipt_bundle_sha256": (
            canonical_json_sha256(transport_receipt_bundle)
            if transport_receipt_bundle is not None
            else None
        ),
        "protected_state": {
            "before": _state_summary(before),
            "after_rollback": _state_summary(after),
            "unchanged_after_rollback": True,
        },
        "rollback_only": True,
        "canonical_submission_performed": False,
        "physical_model_lock_created": False,
        "human_reference_visible_to_inference": False,
    }
    return Phase8RepresentativeRunResult(
        package=package,
        preflight=preflight,
        runner_result=runner_result,
        transport_receipt_bundle=transport_receipt_bundle,
        receipt=receipt,
    )


__all__ = [
    "Phase8RepresentativeRunError",
    "Phase8RepresentativeRunPackage",
    "Phase8RepresentativeRunPreflight",
    "Phase8RepresentativeRunResult",
    "LEGACY_REPRESENTATIVE_RUN_RECEIPT_SCHEMA",
    "REPRESENTATIVE_RUN_APPROVAL_SCOPE",
    "REPRESENTATIVE_RUN_PACKAGE_SCHEMA",
    "REPRESENTATIVE_RUN_PREFLIGHT_RECEIPT_SCHEMA",
    "REPRESENTATIVE_RUN_RECEIPT_SCHEMA",
    "execute_phase8_representative_run",
    "load_phase8_representative_run_package",
    "phase8_representative_source_tree_sha256",
    "verify_phase8_representative_run_package",
]
