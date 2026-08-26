from __future__ import annotations

import hashlib
import json
import stat
import sys
from contextlib import contextmanager
from copy import deepcopy
from functools import partial
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pymupdf
import pytest
from malware_scan_support import (
    CleanMalwareScanner as _CleanScanner,
)
from malware_scan_support import (
    append_clean_attestation,
)
from physical_foundation_support import add_estimate, physical_session
from PIL import Image, ImageDraw
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import classifire.services.phase8_representative_run as representative_run_module
from classifire.db import Base
from classifire.models import StoredFile
from classifire.physical_models import Defect, EvidenceSource
from classifire.services.canonical_submission_state import initial_submission_state
from classifire.services.linked_image_retrieval import _FetchHop
from classifire.services.phase8_human_reference_comparison import (
    HUMAN_REFERENCE_PURPOSE,
    HUMAN_REFERENCE_SCHEMA,
)
from classifire.services.phase8_representative_run import (
    REPRESENTATIVE_RUN_APPROVAL_SCOPE,
    REPRESENTATIVE_RUN_PACKAGE_SCHEMA,
    REPRESENTATIVE_RUN_PREFLIGHT_RECEIPT_SCHEMA,
    Phase8RepresentativeRunError,
    load_phase8_representative_run_package,
    phase8_representative_source_tree_sha256,
    verify_phase8_representative_run_package,
)
from classifire.services.phase8_representative_run import (
    execute_phase8_representative_run as _execute_phase8_representative_run,
)
from classifire.services.phase8_visual_proposal import VISUAL_INFERENCE_RESPONSE_SCHEMA

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPOSITORY_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_phase8_representative_package as representative_package_cli  # noqa: E402

execute_phase8_representative_run = partial(
    _execute_phase8_representative_run,
    malware_scanner=_CleanScanner(),
)


def test_representative_package_requires_a_configured_scanner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(representative_package_cli, "get_settings", object)
    monkeypatch.setattr(
        representative_package_cli,
        "configured_malware_scanner",
        lambda _settings: None,
    )

    with pytest.raises(representative_package_cli.MalwareScanError) as captured:
        representative_package_cli._configured_ready_malware_scanner()

    assert captured.value.code == "MALWARE_SCANNER_UNAVAILABLE"


def _detailed_jpeg() -> bytes:
    image = Image.new("RGB", (1000, 1000), (20, 80, 160))
    draw = ImageDraw.Draw(image)
    draw.ellipse((200, 200, 800, 800), fill=(220, 170, 30))
    for offset in range(0, 1000, 25):
        draw.line((offset, 0, offset, 1000), fill=(35, 95, 175), width=1)
        draw.line((0, offset, 1000, offset), fill=(15, 65, 145), width=1)
    output = BytesIO()
    image.save(output, format="JPEG", quality=95)
    return output.getvalue()


def _embedded(source: bytes, path: Path) -> None:
    with Image.open(BytesIO(source)) as image:
        image.resize((50, 50), Image.Resampling.LANCZOS).save(path, format="JPEG")


def _report(path: Path) -> str:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_link(
        {
            "kind": pymupdf.LINK_URI,
            "from": pymupdf.Rect(10, 10, 60, 60),
            "uri": (
                "https://twiddle.onuptick.com/media/original.jpg?Expires=32503680000"
                "&Key-Pair-Id=PAIR&Signature=TEST-SIGNATURE&public_id=PUBLIC-ID"
                "&transform=FULL-SIZE"
            ),
        }
    )
    document.save(path)
    document.close()
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _parent(session, storage_root: Path, embedded_path: Path):
    estimate = add_estimate(session)
    defect = Defect(
        estimate_id=estimate.id,
        external_defect_id="D-001",
        evidence_status="confirmed",
        status="draft",
    )
    session.add(defect)
    session.flush()
    digest = hashlib.sha256(embedded_path.read_bytes()).hexdigest()
    stored = StoredFile(
        original_filename="embedded.jpg",
        media_type="image/jpeg",
        storage_path=str(embedded_path),
        sha256=digest,
        size_bytes=embedded_path.stat().st_size,
        purpose="technical_evidence",
        malware_scan_status="clean",
        immutable=True,
    )
    session.add(stored)
    session.flush()
    append_clean_attestation(session, stored)
    evidence = EvidenceSource(
        estimate_id=estimate.id,
        defect_id=defect.id,
        stored_file_id=stored.id,
        evidence_type="inspection_photo",
        source_reference="synthetic-report-thumbnail",
        page_number="1",
        region_reference="P001-I01",
        sha256=digest,
        evidence_class="observed",
        status="active",
        source_json={
            "phase8_visual_inference": {
                "evidence_role": "primary_detail",
                "relationship": "embedded_image",
                "parent_evidence_source_id": None,
                "inference_allowed": True,
                "validation_only": False,
            }
        },
    )
    session.add(evidence)
    session.flush()
    return estimate, evidence, stored


def _proposal() -> dict[str, Any]:
    return {
        "status": "MODEL_SUPPORTED",
        "limitations": [],
        "openings": [
            {
                "external_defect_id": "D-001",
                "opening_code": "O-001",
                "substrate_type": "concrete",
                "substrate_plane": "wall",
                "orientation": "vertical",
                "opening_type": "service_penetration",
            }
        ],
        "services": [
            {
                "service_code": "S-001",
                "service_type": "pipe",
                "material": "PVC",
                "quantity": 1,
                "primary_opening_code": "O-001",
                "opening_codes": ["O-001"],
                "evidence_status": "confirmed",
                "relationship_status": "confirmed",
                "link_type": "penetrates",
                "source_reference": "synthetic-evidence",
                "confidence": "0.95",
            }
        ],
    }


def _blind(proposal: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "COMPLETE",
        "observed_opening_count": 1,
        "observed_service_group_count": 1,
        "candidate_openings": [
            {
                "candidate_id": "V-O-001",
                "blank": False,
                "detail": "synthetic opening",
                "evidence_refs": ["synthetic-evidence"],
            }
        ],
        "candidate_services": [
            {
                "candidate_id": "V-S-001",
                "service_type": "pipe",
                "material": "PVC",
                "quantity": 1,
                "candidate_opening_ids": ["V-O-001"],
                "detail": "synthetic service",
                "evidence_refs": ["synthetic-evidence"],
            }
        ],
        "unresolved_candidates": [],
        "limitations": [],
    }


def _matching_human_reference() -> dict[str, Any]:
    return {
        "schema": HUMAN_REFERENCE_SCHEMA,
        "run_id": "SYNTHETIC-REFERENCE-RUN-001",
        "purpose": HUMAN_REFERENCE_PURPOSE,
        "defects": [
            {
                "external_defect_id": "D-001",
                "opening_count": 1,
                "openings": [
                    {
                        "substrate": "concrete wall",
                        "blank": False,
                        "service_groups": [{"type": "pipe", "material": "PVC", "quantity": 1}],
                    }
                ],
            }
        ],
    }


class _Port:
    def __init__(self) -> None:
        proposal = _proposal()
        blind = _blind(proposal)
        self.responses = {
            "blind_inventory": blind,
            "physical_proposal": proposal,
            "conditioned_validator_0": {
                "verdict": "APPROVED",
                "issues": [],
                "limitations": [],
                "observed_opening_count": 1,
                "observed_service_group_count": 1,
                "blind_reconciliation": [
                    {
                        "blind_candidate_id": "V-O-001",
                        "disposition": "ACCOUNTED_FOR",
                        "proposal_refs": ["O-001"],
                        "detail": "synthetic opening accounted for",
                        "evidence_refs": ["synthetic-evidence"],
                    },
                    {
                        "blind_candidate_id": "V-S-001",
                        "disposition": "ACCOUNTED_FOR",
                        "proposal_refs": ["S-001"],
                        "detail": "synthetic service accounted for",
                        "evidence_refs": ["synthetic-evidence"],
                    },
                ],
            },
        }

    def invoke(self, *, role: str, stage: str, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema": VISUAL_INFERENCE_RESPONSE_SCHEMA,
            "agent_id": role,
            "provider": "test-provider",
            "model": "validator-test-model" if role == "cf-validator" else "physical-test-model",
            "session_id_sha256": "7" * 64,
            "transport_receipt_sha256": "8" * 64,
            "tool_calls": [],
            "payload": deepcopy(self.responses[stage]),
        }


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _package(
    tmp_path: Path,
    *,
    estimate_id: str,
    parent_evidence_id: str,
) -> Path:
    package_dir = tmp_path / "package"
    storage_root = package_dir / "storage"
    retrieval_root = package_dir / "retrieval"
    storage_root.mkdir(parents=True, exist_ok=True)
    retrieval_root.mkdir()
    embedded = storage_root / "embedded.jpg"
    if not embedded.exists():
        _embedded(_detailed_jpeg(), embedded)
    report = package_dir / "report.pdf"
    actual_report_sha256 = _report(report)
    (package_dir / "snapshot.db").write_bytes(b"synthetic database snapshot")
    _write_json(package_dir / "human-reference.json", _matching_human_reference())
    _write_json(
        package_dir / "photo-rows.json",
        {
            "photo_rows": [
                {
                    "photo_id": "P001-I01",
                    "page_number": 1,
                    "bbox": [10.0, 10.0, 60.0, 60.0],
                    "native_path": "embedded.jpg",
                    "native_width": 50,
                    "native_height": 50,
                    "width": 50,
                    "height": 50,
                    "tiny_artifact": False,
                    "decorative_candidate": False,
                }
            ]
        },
    )
    _write_json(
        package_dir / "parent-evidence.json",
        {"parent_evidence_by_photo_id": {"P001-I01": parent_evidence_id}},
    )
    _write_json(
        package_dir / "package.json",
        {
            "schema": REPRESENTATIVE_RUN_PACKAGE_SCHEMA,
            "package_id": "REPRESENTATIVE-RUN-001",
            "approval": {
                "reference": "CHG-REPRESENTATIVE-001",
                "authorised_by": "Test operator",
                "authorised_at_utc": "2026-08-23T00:00:00Z",
                "scope": REPRESENTATIVE_RUN_APPROVAL_SCOPE,
                "report_sha256": actual_report_sha256,
                "retrieval_hosts": ["twiddle.onuptick.com"],
            },
            "execution": {
                "expected_git_revision": "a" * 40,
                "source_tree_sha256": phase8_representative_source_tree_sha256(REPOSITORY_ROOT),
                "estimate_id": estimate_id,
                "defect_reference": "D-001",
                "operator_reference": "Test operator",
                "rollback_only": True,
                "canonical_submission_allowed": False,
                "physical_model_lock_allowed": False,
                "human_reference_visible_to_inference": False,
            },
            "inputs": {
                "report": "report.pdf",
                "photo_rows": "photo-rows.json",
                "parent_evidence_by_photo_id": "parent-evidence.json",
                "database_copy": "snapshot.db",
                "storage_root": "storage",
                "retrieval_root": "retrieval",
                "human_reference": "human-reference.json",
            },
            "runtime": {
                "gateway_command": [str(Path(sys.executable).resolve())],
                "gateway_base_url": "http://127.0.0.1:18789",
                "provider": "test-provider",
                "physical_model": "physical-test-model",
                "validator_model": "validator-test-model",
                "physical_agent_id": "cf-phase8-visual-physical",
                "validator_agent_id": "cf-phase8-visual-validator",
            },
        },
    )
    return package_dir / "package.json"


def test_approved_package_runs_only_through_factory_and_rolls_back(
    tmp_path: Path,
) -> None:
    with physical_session() as session:
        package_dir = tmp_path / "package"
        storage_root = package_dir / "storage"
        storage_root.mkdir(parents=True, exist_ok=True)
        embedded = storage_root / "embedded.jpg"
        _embedded(_detailed_jpeg(), embedded)
        estimate, parent, _stored = _parent(session, storage_root, embedded)
        session.commit()

        package_path = _package(
            tmp_path,
            estimate_id=estimate.id,
            parent_evidence_id=parent.id,
        )
        package = load_phase8_representative_run_package(package_path)
        port = _Port()
        packet_count: list[int] = []
        closed: list[bool] = []

        @contextmanager
        def factory(packet):
            packet_count.append(len(packet.files))
            try:
                yield port
            finally:
                closed.append(True)

        before = initial_submission_state(session, estimate_id=estimate.id)
        result = execute_phase8_representative_run(
            session,
            package,
            actual_git_revision="a" * 40,
            repository_root=REPOSITORY_ROOT,
            inference_port_factory=factory,
            transport=lambda _uri, _policy, _resolver: _FetchHop(
                status=200,
                content_type="image/jpeg",
                declared_length=len(_detailed_jpeg()),
                body=_detailed_jpeg(),
                resolved_address_count=1,
                tls_version="TLSv1.3",
            ),
        )
        after = initial_submission_state(session, estimate_id=estimate.id)

        assert result.receipt["rollback_only"] is True
        assert result.receipt["canonical_submission_performed"] is False
        assert result.receipt["physical_model_lock_created"] is False
        assert result.receipt["protected_state"]["unchanged_after_rollback"] is True
        assert result.runner_result.visual_result is not None
        assert packet_count == [2]
        assert closed == [True]
        assert before.fingerprint == after.fingerprint
        assert before.counts == after.counts


def test_package_rejects_missing_approval_reference_before_execution(tmp_path: Path) -> None:
    package_dir = tmp_path / "package"
    storage_root = package_dir / "storage"
    storage_root.mkdir(parents=True, exist_ok=True)
    embedded = storage_root / "embedded.jpg"
    _embedded(_detailed_jpeg(), embedded)

    package_path = _package(
        tmp_path,
        estimate_id="estimate-id",
        parent_evidence_id="parent-id",
    )
    raw = json.loads(package_path.read_text(encoding="utf-8"))
    raw["approval"]["reference"] = ""
    _write_json(package_path, raw)

    with pytest.raises(Phase8RepresentativeRunError) as caught:
        load_phase8_representative_run_package(package_path)

    assert caught.value.code == "APPROVAL_INVALID"


def test_package_rejects_dns_gateway_name_before_execution(tmp_path: Path) -> None:
    package_path = _package(
        tmp_path,
        estimate_id="estimate-id",
        parent_evidence_id="parent-id",
    )
    raw = json.loads(package_path.read_text(encoding="utf-8"))
    raw["runtime"]["gateway_base_url"] = "http://localhost:18789"
    _write_json(package_path, raw)

    with pytest.raises(Phase8RepresentativeRunError) as caught:
        load_phase8_representative_run_package(package_path)

    assert caught.value.code == "RUNTIME_INVALID"


def test_package_rejects_invalid_human_reference_before_execution(tmp_path: Path) -> None:
    package_path = _package(
        tmp_path,
        estimate_id="estimate-id",
        parent_evidence_id="parent-id",
    )
    reference_path = package_path.parent / "human-reference.json"
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    reference["purpose"] = "invalid"
    _write_json(reference_path, reference)

    with pytest.raises(Phase8RepresentativeRunError) as caught:
        load_phase8_representative_run_package(package_path)

    assert caught.value.code == "HUMAN_REFERENCE_INVALID"


def test_package_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    package_path = _package(
        tmp_path,
        estimate_id="estimate-id",
        parent_evidence_id="parent-id",
    )
    raw = package_path.read_text(encoding="utf-8")
    package_path.write_text(
        raw[:-1] + ',"schema":"duplicate"}',
        encoding="utf-8",
    )

    with pytest.raises(Phase8RepresentativeRunError) as caught:
        load_phase8_representative_run_package(package_path)

    assert caught.value.code == "PACKAGE_INVALID"


def test_execution_rejects_source_revision_drift_before_retrieval(tmp_path: Path) -> None:
    with physical_session() as session:
        package_dir = tmp_path / "package"
        storage_root = package_dir / "storage"
        storage_root.mkdir(parents=True, exist_ok=True)
        embedded = storage_root / "embedded.jpg"
        _embedded(_detailed_jpeg(), embedded)
        estimate, parent, _stored = _parent(session, storage_root, embedded)
        session.commit()

        package = load_phase8_representative_run_package(
            _package(
                tmp_path,
                estimate_id=estimate.id,
                parent_evidence_id=parent.id,
            )
        )

        with pytest.raises(Phase8RepresentativeRunError) as caught:
            execute_phase8_representative_run(
                session,
                package,
                actual_git_revision="b" * 40,
                repository_root=REPOSITORY_ROOT,
                inference_port_factory=lambda _packet: pytest.fail("must not run"),
            )

        assert caught.value.code == "SOURCE_REVISION_MISMATCH"


def test_preflight_rejects_source_tree_drift_before_database_access(tmp_path: Path) -> None:
    with physical_session() as session:
        package_dir = tmp_path / "package"
        storage_root = package_dir / "storage"
        storage_root.mkdir(parents=True, exist_ok=True)
        embedded = storage_root / "embedded.jpg"
        _embedded(_detailed_jpeg(), embedded)
        estimate, parent, _stored = _parent(session, storage_root, embedded)
        session.commit()

        package_path = _package(
            tmp_path,
            estimate_id=estimate.id,
            parent_evidence_id=parent.id,
        )
        raw = json.loads(package_path.read_text(encoding="utf-8"))
        raw["execution"]["source_tree_sha256"] = "0" * 64
        _write_json(package_path, raw)
        package = load_phase8_representative_run_package(package_path)

        with pytest.raises(Phase8RepresentativeRunError) as caught:
            verify_phase8_representative_run_package(
                session,
                package,
                actual_git_revision="a" * 40,
                repository_root=REPOSITORY_ROOT,
                protected_state_reader=lambda: pytest.fail("must not read database"),
            )

        assert caught.value.code == "SOURCE_TREE_MISMATCH"


def test_source_tree_hash_rejects_nested_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root = tmp_path / "repository"
    source_root = repository_root / "src" / "classifire"
    scripts_root = repository_root / "scripts"
    source_root.mkdir(parents=True)
    scripts_root.mkdir(parents=True)
    linked_source = source_root / "linked.py"
    linked_source.write_text("VALUE = 1\n", encoding="utf-8")
    (scripts_root / "run_phase8_representative_package.py").write_text(
        "raise SystemExit(0)\n", encoding="utf-8"
    )
    (repository_root / "pyproject.toml").write_text(
        "[project]\nname = 'classifire'\n", encoding="utf-8"
    )

    original_is_symlink = Path.is_symlink

    def is_symlink(path: Path) -> bool:
        return path == linked_source or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", is_symlink)

    with pytest.raises(Phase8RepresentativeRunError) as caught:
        phase8_representative_source_tree_sha256(repository_root)

    assert caught.value.code == "SOURCE_TREE_INVALID"


def test_source_tree_hash_rejects_nested_python311_windows_reparse_point(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root = tmp_path / "repository"
    source_root = repository_root / "src" / "classifire"
    scripts_root = repository_root / "scripts"
    source_root.mkdir(parents=True)
    scripts_root.mkdir(parents=True)
    linked_source = source_root / "linked.py"
    linked_source.write_text("VALUE = 1\n", encoding="utf-8")
    (scripts_root / "run_phase8_representative_package.py").write_text(
        "raise SystemExit(0)\n", encoding="utf-8"
    )
    (repository_root / "pyproject.toml").write_text(
        "[project]\nname = 'classifire'\n", encoding="utf-8"
    )

    reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

    monkeypatch.setattr(representative_run_module, "_IS_WINDOWS", True)
    monkeypatch.setattr(Path, "is_symlink", lambda _path: False)
    monkeypatch.setattr(
        Path,
        "lstat",
        lambda path: SimpleNamespace(
            st_file_attributes=reparse_point if path == linked_source else 0
        ),
    )

    with pytest.raises(Phase8RepresentativeRunError) as caught:
        phase8_representative_source_tree_sha256(repository_root)

    assert caught.value.code == "SOURCE_TREE_INVALID"


def test_package_preflight_validates_snapshot_without_runtime(tmp_path: Path) -> None:
    with physical_session() as session:
        package_dir = tmp_path / "package"
        storage_root = package_dir / "storage"
        storage_root.mkdir(parents=True, exist_ok=True)
        embedded = storage_root / "embedded.jpg"
        _embedded(_detailed_jpeg(), embedded)
        estimate, parent, _stored = _parent(session, storage_root, embedded)
        session.commit()

        package = load_phase8_representative_run_package(
            _package(
                tmp_path,
                estimate_id=estimate.id,
                parent_evidence_id=parent.id,
            )
        )
        before = initial_submission_state(session, estimate_id=estimate.id)
        preflight = verify_phase8_representative_run_package(
            session,
            package,
            actual_git_revision="a" * 40,
            repository_root=REPOSITORY_ROOT,
        )
        after = initial_submission_state(session, estimate_id=estimate.id)

        assert preflight.receipt["schema"] == REPRESENTATIVE_RUN_PREFLIGHT_RECEIPT_SCHEMA
        assert preflight.receipt["preflight_only"] is True
        assert preflight.receipt["runtime_started"] is False
        assert preflight.receipt["retrieval_performed"] is False
        assert preflight.receipt["canonical_submission_performed"] is False
        assert preflight.receipt["physical_model_lock_created"] is False
        assert before.fingerprint == after.fingerprint
        assert before.counts == after.counts


@pytest.mark.parametrize(
    "invalid_state",
    ["pending", "mutable", "wrong_purpose", "digest_mismatch", "tampered"],
)
def test_package_preflight_rejects_untrusted_parent_storage(
    tmp_path: Path,
    invalid_state: str,
) -> None:
    with physical_session() as session:
        package_dir = tmp_path / "package"
        storage_root = package_dir / "storage"
        storage_root.mkdir(parents=True, exist_ok=True)
        embedded = storage_root / "embedded.jpg"
        _embedded(_detailed_jpeg(), embedded)
        estimate, parent, stored = _parent(session, storage_root, embedded)
        session.commit()

        package = load_phase8_representative_run_package(
            _package(
                tmp_path,
                estimate_id=estimate.id,
                parent_evidence_id=parent.id,
            )
        )
        if invalid_state == "pending":
            stored.malware_scan_status = "pending"
        elif invalid_state == "mutable":
            stored.immutable = False
        elif invalid_state == "wrong_purpose":
            stored.purpose = "unrelated_upload"
        elif invalid_state == "digest_mismatch":
            parent.sha256 = "b" * 64
        else:
            embedded.write_bytes(b"tampered after retention")
        session.flush()

        with pytest.raises(Phase8RepresentativeRunError) as rejected:
            verify_phase8_representative_run_package(
                session,
                package,
                actual_git_revision="a" * 40,
                repository_root=REPOSITORY_ROOT,
            )

        assert rejected.value.code == "PARENT_EVIDENCE_INVALID"


def test_package_command_uses_snapshot_and_rolls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    package_path = _package(
        tmp_path,
        estimate_id="placeholder-estimate",
        parent_evidence_id="placeholder-parent",
    )
    package_dir = package_path.parent
    storage_root = package_dir / "storage"
    embedded = storage_root / "embedded.jpg"
    snapshot_path = package_dir / "snapshot.db"
    snapshot_path.unlink()
    engine = create_engine(f"sqlite+pysqlite:///{snapshot_path.as_posix()}")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            estimate, parent, _stored = _parent(session, storage_root, embedded)
            session.commit()
            before = initial_submission_state(session, estimate_id=estimate.id)

        manifest = json.loads(package_path.read_text(encoding="utf-8"))
        manifest["execution"]["estimate_id"] = estimate.id
        manifest["execution"]["expected_git_revision"] = representative_package_cli._git_revision(
            Path(__file__).resolve().parents[1]
        )
        parent_rows = json.loads((package_dir / "parent-evidence.json").read_text(encoding="utf-8"))
        parent_rows["parent_evidence_by_photo_id"]["P001-I01"] = parent.id
        _write_json(package_path, manifest)
        _write_json(package_dir / "parent-evidence.json", parent_rows)

        runtimes: list[object] = []

        class _ManagedRuntime:
            def __init__(self, **kwargs: Any) -> None:
                self.evidence_packet = kwargs["evidence_packet"]
                self.transport = _Port()
                runtimes.append(self)

            def __enter__(self) -> _ManagedRuntime:
                return self

            def __exit__(self, *_: object) -> None:
                return None

        source = _detailed_jpeg()
        execute_real = representative_package_cli.execute_phase8_representative_run
        configured_scanner = _CleanScanner()
        scanner_configuration_calls: list[bool] = []

        def configured_ready_scanner() -> _CleanScanner:
            scanner_configuration_calls.append(True)
            return configured_scanner

        def execute_synthetic(*args: Any, **kwargs: Any) -> Any:
            assert kwargs.get("malware_scanner") is configured_scanner
            return execute_real(
                *args,
                transport=lambda _uri, _policy, _resolver: _FetchHop(
                    status=200,
                    content_type="image/jpeg",
                    declared_length=len(source),
                    body=source,
                    resolved_address_count=1,
                    tls_version="TLSv1.3",
                ),
                **kwargs,
            )

        def execute_must_not_run(*_: Any, **__: Any) -> Any:
            pytest.fail("verify-only must not execute retrieval or inference")

        readiness_calls: list[dict[str, Any]] = []

        def readiness_ready(*_: Any, **kwargs: Any) -> None:
            readiness_calls.append(kwargs)

        monkeypatch.setattr(
            representative_package_cli,
            "verify_phase8_no_write_gateway_readiness",
            readiness_ready,
        )
        monkeypatch.setattr(
            representative_package_cli,
            "_configured_ready_malware_scanner",
            configured_ready_scanner,
        )

        preflight_output = tmp_path / "preflight-output"
        monkeypatch.setattr(
            representative_package_cli,
            "execute_phase8_representative_run",
            execute_must_not_run,
        )
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "run_phase8_representative_package.py",
                "--package",
                str(package_path),
                "--output",
                str(preflight_output),
                "--repository-root",
                str(Path(__file__).resolve().parents[1]),
                "--verify-only",
            ],
        )

        assert representative_package_cli.main() == 0
        preflight_result = json.loads(capsys.readouterr().out)
        preflight_receipt = json.loads(
            (preflight_output / "preflight-receipt.json").read_text(encoding="utf-8")
        )
        assert preflight_result["status"] == "PRECHECK_PASSED"
        assert preflight_result["preflight_only"] is True
        assert preflight_result["runtime_started"] is False
        assert preflight_result["retrieval_performed"] is False
        assert preflight_receipt["schema"] == REPRESENTATIVE_RUN_PREFLIGHT_RECEIPT_SCHEMA
        assert scanner_configuration_calls == []
        readiness_receipt = json.loads(
            (preflight_output / "runtime-readiness-receipt.json").read_text(encoding="utf-8")
        )
        assert (
            readiness_receipt["schema"]
            == representative_package_cli.RUNTIME_READINESS_RECEIPT_SCHEMA
        )
        assert readiness_receipt["runtime_started"] is False
        assert readiness_receipt["retrieval_performed"] is False
        assert readiness_receipt["inference_request_performed"] is False
        output = tmp_path / "output"
        monkeypatch.setattr(
            representative_package_cli,
            "ManagedPhase8VisualRuntime",
            _ManagedRuntime,
        )
        monkeypatch.setattr(
            representative_package_cli,
            "execute_phase8_representative_run",
            execute_synthetic,
        )
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "run_phase8_representative_package.py",
                "--package",
                str(package_path),
                "--output",
                str(output),
                "--repository-root",
                str(Path(__file__).resolve().parents[1]),
            ],
        )

        assert representative_package_cli.main() == 0
        assert scanner_configuration_calls == [True]
        result = json.loads(capsys.readouterr().out)
        completion = json.loads((output / "completion-receipt.json").read_text(encoding="utf-8"))
        with Session(engine) as session:
            after = initial_submission_state(session, estimate_id=estimate.id)

        assert result["status"] == "VISUAL_PROPOSAL_APPROVED"
        assert result["comparison_status"] == "PASS"
        assert len(runtimes) == 1
        assert runtimes[0].evidence_packet.manifest["human_reference_included"] is False
        assert completion["protected_state"]["unchanged_after_rollback"] is True
        assert completion["canonical_submission_performed"] is False
        assert completion["physical_model_lock_created"] is False
        assert "runtime_readiness_receipt_sha256" in completion["artifacts"]
        assert before.fingerprint == after.fingerprint
        assert before.counts == after.counts
        assert (output / "human-reference-comparison.json").is_file()

        def execute_failure(*_: Any, **__: Any) -> Any:
            raise Phase8RepresentativeRunError("SYNTHETIC_EXECUTION_FAILURE")

        failure_output = tmp_path / "failure-output"
        monkeypatch.setattr(
            representative_package_cli,
            "execute_phase8_representative_run",
            execute_failure,
        )
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "run_phase8_representative_package.py",
                "--package",
                str(package_path),
                "--output",
                str(failure_output),
                "--repository-root",
                str(Path(__file__).resolve().parents[1]),
            ],
        )

        assert representative_package_cli.main() == 2
        failure_result = json.loads(capsys.readouterr().out)
        failure_receipt = json.loads(
            (failure_output / "failure-receipt.json").read_text(encoding="utf-8")
        )
        assert failure_result["status"] == "EXECUTION_FAILED"
        assert failure_result["failure_code"] == "SYNTHETIC_EXECUTION_FAILURE"
        assert failure_receipt["failure_code"] == "SYNTHETIC_EXECUTION_FAILURE"
        assert failure_receipt["failure_type"] == "Phase8RepresentativeRunError"
        assert failure_receipt["rollback_only"] is True
        assert failure_receipt["canonical_submission_performed"] is False
        assert failure_receipt["physical_model_lock_created"] is False
        assert not (failure_output / "completion-receipt.json").exists()

        def readiness_unavailable(*_: Any, **__: Any) -> None:
            raise Phase8RepresentativeRunError("GATEWAY_TOKEN_UNAVAILABLE")

        readiness_failure_output = tmp_path / "readiness-failure-output"
        monkeypatch.setattr(
            representative_package_cli,
            "verify_phase8_no_write_gateway_readiness",
            readiness_unavailable,
        )
        monkeypatch.setattr(
            representative_package_cli,
            "execute_phase8_representative_run",
            execute_must_not_run,
        )
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "run_phase8_representative_package.py",
                "--package",
                str(package_path),
                "--output",
                str(readiness_failure_output),
                "--repository-root",
                str(Path(__file__).resolve().parents[1]),
            ],
        )

        assert representative_package_cli.main() == 2
        readiness_failure_result = json.loads(capsys.readouterr().out)
        readiness_failure_receipt = json.loads(
            (readiness_failure_output / "failure-receipt.json").read_text(encoding="utf-8")
        )
        assert readiness_failure_result["failure_code"] == "GATEWAY_TOKEN_UNAVAILABLE"
        assert readiness_failure_receipt["failure_code"] == "GATEWAY_TOKEN_UNAVAILABLE"
        assert (readiness_failure_output / "preflight-receipt.json").is_file()
        assert not (readiness_failure_output / "runtime-readiness-receipt.json").exists()
        assert not (readiness_failure_output / "completion-receipt.json").exists()
        assert len(readiness_calls) == 3
    finally:
        engine.dispose()
