from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from copy import deepcopy
from functools import partial
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from malware_scan_support import (
    CleanMalwareScanner as _CleanScanner,
)
from malware_scan_support import (
    append_clean_attestation,
    malware_scan_result,
)
from physical_foundation_support import add_estimate, physical_session
from PIL import Image, ImageDraw
from sqlalchemy import event, func, select

import classifire.services.phase8_linked_visual_run as linked_run_service
from classifire.models import MalwareScanAttestation, Opening, StoredFile
from classifire.physical_models import Defect, EvidenceSource
from classifire.services.canonical_submission_state import initial_submission_state
from classifire.services.linked_image_evidence import LinkedImageMalwareQuarantinedError
from classifire.services.linked_image_retrieval import _FetchHop
from classifire.services.malware_scan_attestations import (
    append_malware_scan_attestation,
)
from classifire.services.phase8_linked_visual_run import (
    LINKED_VISUAL_RETRIEVAL_BLOCKED,
    LINKED_VISUAL_RUN_RECEIPT_SCHEMA,
    Phase8LinkedVisualRunError,
    validate_phase8_linked_visual_run_receipt,
)
from classifire.services.phase8_linked_visual_run import (
    run_phase8_linked_visual_proposal as _run_phase8_linked_visual_proposal,
)
from classifire.services.phase8_visual_prompts import build_visual_inference_profile
from classifire.services.phase8_visual_proposal import (
    VISUAL_INFERENCE_RESPONSE_SCHEMA,
    VISUAL_PROPOSAL_APPROVED,
    VISUAL_PROPOSAL_PROTECTED_STATE_CHANGED,
)
from classifire.services.phase8_visual_provenance import (
    assess_phase8_visual_provenance_completeness,
)
from classifire.services.physical_scope import is_blank_opening_type
from classifire.services.storage import record_detected_sha

LEAK_MARKER = "SIGNED-CAPABILITY-MUST-NOT-LEAK"


run_phase8_linked_visual_proposal = partial(
    _run_phase8_linked_visual_proposal,
    malware_scanner=_CleanScanner(),
)


def _uri() -> str:
    return (
        "https://twiddle.onuptick.com/media/original.jpg?Expires=32503680000"
        f"&Key-Pair-Id=PAIR&Signature={LEAK_MARKER}"
        "&public_id=PUBLIC-ID&transform=FULL-SIZE"
    )


def _detailed_jpeg() -> bytes:
    size = (1000, 1000)
    image = Image.new("RGB", size, (20, 80, 160))
    draw = ImageDraw.Draw(image)
    draw.ellipse((200, 200, 800, 800), fill=(220, 170, 30))
    draw.line((0, 0, 1000, 1000), fill=(245, 245, 245), width=50)
    for index, offset in enumerate(range(0, 1000, 25)):
        vertical = tuple(min(255, value + (index % 7) * 4) for value in (35, 95, 175))
        horizontal = tuple(min(255, value + (index % 5) * 5) for value in (15, 65, 145))
        draw.line((offset, 0, offset, 1000), fill=vertical, width=1)
        draw.line((0, offset, 1000, offset), fill=horizontal, width=1)
    output = BytesIO()
    image.save(output, format="JPEG", quality=95)
    return output.getvalue()


def _embedded(source: bytes, path: Path) -> None:
    with Image.open(BytesIO(source)) as image:
        image.resize((50, 50), Image.Resampling.LANCZOS).save(
            path,
            format="JPEG",
            quality=92,
        )


def _report(path: Path, *, linked: bool = True) -> str:
    import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    if linked:
        page.insert_link(
            {
                "kind": pymupdf.LINK_URI,
                "from": pymupdf.Rect(10, 10, 60, 60),
                "uri": _uri(),
            }
        )
    document.save(path)
    document.close()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _two_link_report(path: Path) -> str:
    import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    for left in (10, 70):
        page.insert_link(
            {
                "kind": pymupdf.LINK_URI,
                "from": pymupdf.Rect(left, 10, left + 50, 60),
                "uri": _uri(),
            }
        )
    document.save(path)
    document.close()
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    embedded_sha256 = hashlib.sha256(embedded_path.read_bytes()).hexdigest()
    stored = StoredFile(
        original_filename="embedded.jpg",
        media_type="image/jpeg",
        storage_path=str(embedded_path),
        sha256=embedded_sha256,
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
        sha256=embedded_sha256,
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
    return estimate, defect, evidence


def _photo_row(embedded_path: Path) -> dict[str, Any]:
    return {
        "photo_id": "P001-I01",
        "page_number": 1,
        "bbox": [10.0, 10.0, 60.0, 60.0],
        "native_path": str(embedded_path),
        "native_width": 50,
        "native_height": 50,
        "width": 50,
        "height": 50,
        "tiny_artifact": False,
        "decorative_candidate": False,
    }


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


def _blind_inventory(proposal: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "COMPLETE",
        "observed_opening_count": len(proposal["openings"]),
        "observed_service_group_count": len(proposal["services"]),
        "candidate_openings": [
            {
                "candidate_id": f"V-{opening['opening_code']}",
                "blank": is_blank_opening_type(opening["opening_type"]),
                "detail": "synthetic opening observation",
                "evidence_refs": ["synthetic-evidence"],
            }
            for opening in proposal["openings"]
        ],
        "candidate_services": [
            {
                "candidate_id": f"V-{service['service_code']}",
                "service_type": service["service_type"],
                "material": service.get("material"),
                "quantity": service["quantity"],
                "candidate_opening_ids": [
                    f"V-{opening_code}" for opening_code in service["opening_codes"]
                ],
                "detail": "synthetic service observation",
                "evidence_refs": ["synthetic-evidence"],
            }
            for service in proposal["services"]
        ],
        "unresolved_candidates": [],
        "limitations": [],
    }


def _validator(proposal: dict[str, Any], blind: dict[str, Any]) -> dict[str, Any]:
    candidates = [*blind["candidate_openings"], *blind["candidate_services"]]
    return {
        "verdict": "APPROVED",
        "issues": [],
        "limitations": [],
        "observed_opening_count": len(proposal["openings"]),
        "observed_service_group_count": len(proposal["services"]),
        "blind_reconciliation": [
            {
                "blind_candidate_id": candidate["candidate_id"],
                "disposition": "ACCOUNTED_FOR",
                "proposal_refs": [candidate["candidate_id"].removeprefix("V-")],
                "detail": "synthetic candidate accounted for",
                "evidence_refs": ["synthetic-evidence"],
            }
            for candidate in candidates
        ],
    }


class _ScriptedPort:
    def __init__(self, *, mutation=None) -> None:
        proposal = _proposal()
        blind = _blind_inventory(proposal)
        self.responses = {
            "blind_inventory": blind,
            "physical_proposal": proposal,
            "conditioned_validator_0": _validator(proposal, blind),
        }
        self.calls: list[dict[str, Any]] = []
        self.mutation = mutation

    def invoke(
        self,
        *,
        role: str,
        stage: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append({"role": role, "stage": stage, "request": deepcopy(request)})
        if self.mutation is not None and len(self.calls) == 1:
            self.mutation()
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


def _profile() -> dict[str, Any]:
    return build_visual_inference_profile(
        implementation_revision="a" * 40,
        provider="test-provider",
        physical_model="physical-test-model",
        validator_model="validator-test-model",
    )


def _run(
    session,
    *,
    tmp_path: Path,
    linked: bool = True,
    port: _ScriptedPort | None = None,
    parent_map: dict[str, str] | None = None,
    unbound_visual_ids: list[str] | None = None,
):
    storage_root = tmp_path / "storage"
    retrieval_root = tmp_path / "retrieval"
    storage_root.mkdir()
    retrieval_root.mkdir()
    source = _detailed_jpeg()
    embedded_path = storage_root / "embedded.jpg"
    _embedded(source, embedded_path)
    report = tmp_path / "report.pdf"
    report_sha256 = _report(report, linked=linked)
    estimate, defect, parent = _parent(session, storage_root, embedded_path)
    if unbound_visual_ids is not None:
        unbound_visual = EvidenceSource(
            estimate_id=estimate.id,
            defect_id=defect.id,
            stored_file_id=parent.stored_file_id,
            evidence_type="inspection_photo",
            source_reference="synthetic-unbound-visual-evidence",
            page_number="1",
            region_reference="UNBOUND-001",
            sha256=parent.sha256,
            evidence_class="observed",
            status="active",
            source_json=deepcopy(parent.source_json),
        )
        session.add(unbound_visual)
        session.flush()
        unbound_visual_ids.append(unbound_visual.id)
    selected_port = port or _ScriptedPort()
    result = run_phase8_linked_visual_proposal(
        session,
        run_id="RUN-LINKED-001",
        estimate_id=estimate.id,
        defect_reference="D-001",
        report=report,
        report_sha256=report_sha256,
        photo_rows=[_photo_row(embedded_path)],
        parent_evidence_by_photo_id=(
            parent_map if parent_map is not None else {"P001-I01": parent.id}
        ),
        storage_root=storage_root,
        retrieval_root=retrieval_root,
        operator_reference="Synthetic test operator",
        inference_profile=_profile(),
        inference_port=selected_port,
        protected_state_reader=lambda: initial_submission_state(
            session,
            estimate_id=estimate.id,
        ),
        transport=lambda _uri_value, _policy, _resolver: _FetchHop(
            status=200,
            content_type="image/jpeg",
            declared_length=len(source),
            body=source,
            resolved_address_count=1,
            tls_version="TLSv1.3",
        ),
    )
    return result, estimate, defect, parent, selected_port, storage_root, report


def test_runner_composes_retrieval_retention_and_approved_controller_without_commit(
    tmp_path: Path,
) -> None:
    with physical_session() as session:
        commits: list[bool] = []
        event.listen(session.get_bind(), "commit", lambda _connection: commits.append(True))

        result, estimate, _defect, parent, port, storage_root, report = _run(
            session,
            tmp_path=tmp_path,
        )

        assert commits == []
        assert result.receipt["schema"] == LINKED_VISUAL_RUN_RECEIPT_SCHEMA
        assert validate_phase8_linked_visual_run_receipt(result.receipt) == []
        assert result.visual_result is not None
        assert result.visual_result.status == VISUAL_PROPOSAL_APPROVED
        assert len(result.retentions) == 1
        linked = result.retentions[0]
        assert (
            linked.evidence.source_json["phase8_visual_inference"]["parent_evidence_source_id"]
            == parent.id
        )
        assert result.evidence_packet is not None
        assert (
            result.receipt["evidence_family_inventory_sha256"]
            == result.evidence_packet.evidence_family_inventory_sha256
        )
        packet_ids = {item.evidence_id for item in result.evidence_packet.files}
        assert packet_ids == {parent.id, linked.evidence.id}
        assert linked.evidence.id in packet_ids
        provenance = assess_phase8_visual_provenance_completeness(
            estimate_id=estimate.id,
            defect_reference="D-001",
            linked_visual_run_receipt=result.receipt,
            evidence_family_inventory=result.evidence_packet.evidence_family_inventory,
        )
        assert provenance.complete is True
        assert provenance.as_dict() == {
            "schema": "CLASSIFIRE-PHASE8-VISUAL-PROVENANCE-COMPLETENESS-v1",
            "status": "PASS",
            "complete": True,
            "estimate_id": estimate.id,
            "defect_reference": "D-001",
            "linked_visual_run_id": "RUN-LINKED-001",
            "linked_visual_receipt_status": VISUAL_PROPOSAL_APPROVED,
            "evidence_manifest_sha256": result.receipt["evidence_manifest_sha256"].upper(),
            "evidence_family_inventory_sha256": result.receipt["evidence_family_inventory_sha256"],
            "controller_receipt_sha256": result.receipt["controller_receipt_sha256"],
            "family_count": 1,
            "preserved_context_member_count": 1,
            "errors": [],
            "report_or_image_retrieval_performed": False,
            "runtime_inference_performed": False,
            "database_write_performed": False,
            "canonical_write_performed": False,
            "physical_model_lock_created": False,
        }
        tampered_inventory = deepcopy(result.evidence_packet.evidence_family_inventory)
        tampered_inventory["families"][0]["family_id"] = "FAMILY-TAMPERED"
        tampered_provenance = assess_phase8_visual_provenance_completeness(
            estimate_id=estimate.id,
            defect_reference="D-001",
            linked_visual_run_receipt=result.receipt,
            evidence_family_inventory=tampered_inventory,
        )
        assert tampered_provenance.complete is False
        assert tampered_provenance.errors == ("EVIDENCE_FAMILY_INVENTORY_HASH_MISMATCH",)
        wrong_scope_provenance = assess_phase8_visual_provenance_completeness(
            estimate_id=estimate.id,
            defect_reference="D-OTHER",
            linked_visual_run_receipt=result.receipt,
            evidence_family_inventory=result.evidence_packet.evidence_family_inventory,
        )
        assert wrong_scope_provenance.complete is False
        assert wrong_scope_provenance.errors == ("CURRENT_VISUAL_RUN_SCOPE_MISMATCH",)
        assert [call["stage"] for call in port.calls] == [
            "blind_inventory",
            "physical_proposal",
            "conditioned_validator_0",
        ]
        protected = result.receipt["protected_state"]
        assert protected["retrieval_database_state_unchanged"] is True
        assert protected["physical_components_unchanged"] is True
        assert protected["inference_state_unchanged"] is True
        assert protected["protected_state_changed_during_inference"] is False
        assert protected["before_retrieval"]["counts"]["evidence_count"] == 1
        assert protected["before_inference"]["counts"]["evidence_count"] == 2
        assert result.receipt["runner_database_commit_performed"] is False
        assert result.receipt["runner_canonical_write_performed"] is False
        assert result.receipt["runner_physical_model_lock_created"] is False
        serialized = json.dumps(result.receipt)
        assert LEAK_MARKER not in serialized
        assert "https://" not in serialized
        assert str(storage_root) not in serialized
        assert str(report) not in serialized
        tampered_receipt = deepcopy(result.receipt)
        tampered_receipt["runner_database_commit_performed"] = True
        tampered_receipt["run_id"] = _uri()
        tampered_receipt["evidence_family_inventory_sha256"] = "not-a-sha256"
        tamper_errors = validate_phase8_linked_visual_run_receipt(tampered_receipt)
        assert any("commit" in error for error in tamper_errors)
        assert any("signed capability" in error for error in tamper_errors)
        assert any("evidence_family_inventory_sha256" in error for error in tamper_errors)
        assert (
            initial_submission_state(session, estimate_id=estimate.id).counts["opening_count"] == 0
        )


def test_runner_excludes_unbound_preexisting_visual_evidence(
    tmp_path: Path,
) -> None:
    with physical_session() as session:
        unbound_visual_ids: list[str] = []
        result, _estimate, _defect, parent, _port, _storage_root, _report = _run(
            session,
            tmp_path=tmp_path,
            unbound_visual_ids=unbound_visual_ids,
        )

        assert len(unbound_visual_ids) == 1
        assert result.evidence_packet is not None
        retained_id = result.retentions[0].evidence.id
        packet_ids = {item.evidence_id for item in result.evidence_packet.files}
        assert packet_ids == {parent.id, retained_id}
        assert unbound_visual_ids[0] not in packet_ids


def test_runner_verifies_full_report_but_retains_only_target_defect_evidence(
    tmp_path: Path,
) -> None:
    with physical_session() as session:
        storage_root = tmp_path / "storage"
        retrieval_root = tmp_path / "retrieval"
        storage_root.mkdir()
        retrieval_root.mkdir()
        source = _detailed_jpeg()
        embedded_path = storage_root / "embedded.jpg"
        _embedded(source, embedded_path)
        report = tmp_path / "report.pdf"
        report_sha256 = _two_link_report(report)
        estimate, _target_defect, target_parent = _parent(
            session,
            storage_root,
            embedded_path,
        )
        other_defect = Defect(
            estimate_id=estimate.id,
            external_defect_id="D-OTHER",
            evidence_status="confirmed",
            status="draft",
        )
        session.add(other_defect)
        session.flush()
        other_parent = EvidenceSource(
            estimate_id=estimate.id,
            defect_id=other_defect.id,
            stored_file_id=target_parent.stored_file_id,
            evidence_type="inspection_photo",
            source_reference="synthetic-report-thumbnail",
            page_number="1",
            region_reference="P001-I02",
            sha256=target_parent.sha256,
            evidence_class="observed",
            status="active",
            source_json={},
        )
        session.add(other_parent)
        session.flush()
        target_row = _photo_row(embedded_path)
        other_row = {
            **_photo_row(embedded_path),
            "photo_id": "P001-I02",
            "bbox": [70.0, 10.0, 120.0, 60.0],
        }
        decorative_row = {
            **_photo_row(embedded_path),
            "photo_id": "P001-I03",
            "bbox": [130.0, 10.0, 180.0, 60.0],
            "decorative_candidate": True,
        }
        port = _ScriptedPort()

        result = run_phase8_linked_visual_proposal(
            session,
            run_id="RUN-LINKED-FULL-REPORT-001",
            estimate_id=estimate.id,
            defect_reference="D-001",
            report=report,
            report_sha256=report_sha256,
            photo_rows=[target_row, other_row, decorative_row],
            parent_evidence_by_photo_id={
                target_row["photo_id"]: target_parent.id,
                other_row["photo_id"]: other_parent.id,
                decorative_row["photo_id"]: other_parent.id,
            },
            storage_root=storage_root,
            retrieval_root=retrieval_root,
            operator_reference="Synthetic test operator",
            inference_profile=_profile(),
            inference_port=port,
            protected_state_reader=lambda: initial_submission_state(
                session,
                estimate_id=estimate.id,
            ),
            transport=lambda _uri_value, _policy, _resolver: _FetchHop(
                status=200,
                content_type="image/jpeg",
                declared_length=len(source),
                body=source,
                resolved_address_count=1,
                tls_version="TLSv1.3",
            ),
        )

        assert result.retrieval.ok is True
        assert len(result.retrieval.results) == 3
        assert len(result.retentions) == 1
        assert (
            result.retentions[0].evidence.source_json["phase8_visual_inference"][
                "parent_evidence_source_id"
            ]
            == target_parent.id
        )
        assert result.evidence_packet is not None
        assert other_parent.id not in {item.evidence_id for item in result.evidence_packet.files}
        assert result.receipt["retrieval"]["ready_count"] == 2
        assert result.receipt["retrieval"]["required_count"] == 2
        assert len(result.receipt["retained_evidence"]) == 1
        assert validate_phase8_linked_visual_run_receipt(result.receipt) == []
        assert [call["stage"] for call in port.calls] == [
            "blind_inventory",
            "physical_proposal",
            "conditioned_validator_0",
        ]


def test_runner_blocks_before_retention_and_inference_when_required_link_is_missing(
    tmp_path: Path,
) -> None:
    with physical_session() as session:
        result, estimate, _defect, _parent, port, _storage_root, _report_path = _run(
            session,
            tmp_path=tmp_path,
            linked=False,
        )

        assert result.receipt["status"] == LINKED_VISUAL_RETRIEVAL_BLOCKED
        assert result.retentions == ()
        assert result.evidence_packet is None
        assert result.visual_result is None
        assert result.receipt["evidence_family_inventory_sha256"] is None
        assert port.calls == []
        assert result.receipt["runtime_inference_performed"] is False
        assert result.receipt["protected_state"]["retrieval_database_state_unchanged"] is True
        assert (
            initial_submission_state(session, estimate_id=estimate.id).counts["evidence_count"] == 1
        )
        optional_no_link = deepcopy(result.receipt)
        optional_no_link["retrieval"]["ok"] = True
        optional_no_link["retrieval"]["required_count"] = 0
        optional_no_link["retrieval"]["status_counts"] = {"NOT_REQUIRED": 1}
        assert validate_phase8_linked_visual_run_receipt(optional_no_link) == []


def test_runner_rejects_parent_mapping_mismatch_before_evidence_retention(tmp_path: Path) -> None:
    with physical_session() as session:
        with pytest.raises(Phase8LinkedVisualRunError) as caught:
            _run(
                session,
                tmp_path=tmp_path,
                parent_map={},
            )

        assert caught.value.code == "PARENT_MAPPING_MISMATCH"
        assert session.scalar(select(func.count()).select_from(EvidenceSource)) == 1


def test_runner_rejects_unclean_parent_before_network_access(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    retrieval_root = tmp_path / "retrieval"
    storage_root.mkdir()
    retrieval_root.mkdir()
    source = _detailed_jpeg()
    embedded_path = storage_root / "embedded.jpg"
    _embedded(source, embedded_path)
    report = tmp_path / "report.pdf"
    report_sha256 = _report(report)

    with physical_session() as session:
        estimate, _defect, parent = _parent(session, storage_root, embedded_path)
        stored = session.get(StoredFile, parent.stored_file_id)
        assert stored is not None
        stored.malware_scan_status = "pending"
        session.flush()

        with pytest.raises(Phase8LinkedVisualRunError) as caught:
            run_phase8_linked_visual_proposal(
                session,
                run_id="RUN-LINKED-UNCLEAN-PARENT",
                estimate_id=estimate.id,
                defect_reference="D-001",
                report=report,
                report_sha256=report_sha256,
                photo_rows=[_photo_row(embedded_path)],
                parent_evidence_by_photo_id={"P001-I01": parent.id},
                storage_root=storage_root,
                retrieval_root=retrieval_root,
                operator_reference="Synthetic test operator",
                inference_profile=_profile(),
                inference_port=_ScriptedPort(),
                protected_state_reader=lambda: initial_submission_state(
                    session,
                    estimate_id=estimate.id,
                ),
                transport=lambda *_args: pytest.fail("network must not be reached"),
            )

        assert caught.value.code == "PARENT_EVIDENCE_INVALID"


def test_runner_rejects_nonempty_physical_model_before_network_access(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    retrieval_root = tmp_path / "retrieval"
    storage_root.mkdir()
    retrieval_root.mkdir()
    source = _detailed_jpeg()
    embedded_path = storage_root / "embedded.jpg"
    _embedded(source, embedded_path)
    report = tmp_path / "report.pdf"
    report_sha256 = _report(report)

    with physical_session() as session:
        estimate, _defect, parent = _parent(session, storage_root, embedded_path)
        session.add(Opening(estimate_id=estimate.id, opening_code="EXISTING-001"))
        session.flush()

        with pytest.raises(Phase8LinkedVisualRunError) as caught:
            run_phase8_linked_visual_proposal(
                session,
                run_id="RUN-LINKED-001",
                estimate_id=estimate.id,
                defect_reference="D-001",
                report=report,
                report_sha256=report_sha256,
                photo_rows=[_photo_row(embedded_path)],
                parent_evidence_by_photo_id={"P001-I01": parent.id},
                storage_root=storage_root,
                retrieval_root=retrieval_root,
                operator_reference="Synthetic test operator",
                inference_profile=_profile(),
                inference_port=_ScriptedPort(),
                protected_state_reader=lambda: initial_submission_state(
                    session,
                    estimate_id=estimate.id,
                ),
                transport=lambda *_args: pytest.fail("network must not be reached"),
            )

        assert caught.value.code == "PROTECTED_PHYSICAL_MODEL_NOT_EMPTY"


def test_runner_receipt_exposes_inference_time_protected_state_change(tmp_path: Path) -> None:
    with physical_session() as session:
        pending: dict[str, Any] = {}

        def mutate() -> None:
            session.add(
                Opening(
                    estimate_id=pending["estimate_id"],
                    opening_code="UNAUTHORISED-001",
                )
            )
            session.flush()

        port = _ScriptedPort(mutation=mutate)

        storage_root = tmp_path / "storage"
        retrieval_root = tmp_path / "retrieval"
        storage_root.mkdir()
        retrieval_root.mkdir()
        source = _detailed_jpeg()
        embedded_path = storage_root / "embedded.jpg"
        _embedded(source, embedded_path)
        report = tmp_path / "report.pdf"
        report_sha256 = _report(report)
        estimate, _defect, parent = _parent(session, storage_root, embedded_path)
        pending["estimate_id"] = estimate.id

        result = run_phase8_linked_visual_proposal(
            session,
            run_id="RUN-LINKED-STATE-CHANGE",
            estimate_id=estimate.id,
            defect_reference="D-001",
            report=report,
            report_sha256=report_sha256,
            photo_rows=[_photo_row(embedded_path)],
            parent_evidence_by_photo_id={"P001-I01": parent.id},
            storage_root=storage_root,
            retrieval_root=retrieval_root,
            operator_reference="Synthetic test operator",
            inference_profile=_profile(),
            inference_port=port,
            protected_state_reader=lambda: initial_submission_state(
                session,
                estimate_id=estimate.id,
            ),
            transport=lambda _uri_value, _policy, _resolver: _FetchHop(
                status=200,
                content_type="image/jpeg",
                declared_length=len(source),
                body=source,
                resolved_address_count=1,
                tls_version="TLSv1.3",
            ),
        )

        assert result.visual_result is not None
        assert result.visual_result.status == VISUAL_PROPOSAL_PROTECTED_STATE_CHANGED
        protected = result.receipt["protected_state"]
        assert protected["inference_state_unchanged"] is False
        assert protected["protected_state_changed_during_inference"] is True
        assert protected["physical_components_unchanged"] is False
        assert result.receipt["runner_database_commit_performed"] is False


def test_runner_rejects_a_newer_infected_attestation_during_inference(
    tmp_path: Path,
) -> None:
    with physical_session() as session:

        def mutate() -> None:
            stored = session.scalar(
                select(StoredFile).where(
                    StoredFile.original_filename.like("linked-image-%")
                )
            )
            assert stored is not None
            payload = Path(stored.storage_path).read_bytes()
            append_malware_scan_attestation(
                session,
                stored_file_id=stored.id,
                result=malware_scan_result(payload, verdict="infected"),
                scan_source="governed_rescan",
                actor=None,
            )

        port = _ScriptedPort(mutation=mutate)

        with pytest.raises(Phase8LinkedVisualRunError) as caught:
            _run(session, tmp_path=tmp_path, port=port)

        assert caught.value.code == "STORED_FILE_ATTESTATION_STALE"
        assert len(port.calls) == 3


def test_runner_builds_and_closes_managed_port_from_retained_evidence_packet(
    tmp_path: Path,
) -> None:
    with physical_session() as session:
        created_for: list[object] = []
        closed: list[bool] = []
        port = _ScriptedPort()

        @contextmanager
        def factory(packet):
            created_for.append(packet)
            try:
                yield port
            finally:
                closed.append(True)

        storage_root = tmp_path / "storage"
        retrieval_root = tmp_path / "retrieval"
        storage_root.mkdir()
        retrieval_root.mkdir()
        source = _detailed_jpeg()
        embedded_path = storage_root / "embedded.jpg"
        _embedded(source, embedded_path)
        report = tmp_path / "report.pdf"
        report_sha256 = _report(report)
        estimate, _defect, parent = _parent(session, storage_root, embedded_path)

        result = run_phase8_linked_visual_proposal(
            session,
            run_id="RUN-LINKED-FACTORY-001",
            estimate_id=estimate.id,
            defect_reference="D-001",
            report=report,
            report_sha256=report_sha256,
            photo_rows=[_photo_row(embedded_path)],
            parent_evidence_by_photo_id={"P001-I01": parent.id},
            storage_root=storage_root,
            retrieval_root=retrieval_root,
            operator_reference="Synthetic test operator",
            inference_profile=_profile(),
            inference_port=None,
            inference_port_factory=factory,
            protected_state_reader=lambda: initial_submission_state(
                session,
                estimate_id=estimate.id,
            ),
            transport=lambda _uri_value, _policy, _resolver: _FetchHop(
                status=200,
                content_type="image/jpeg",
                declared_length=len(source),
                body=source,
                resolved_address_count=1,
                tls_version="TLSv1.3",
            ),
        )

        assert result.visual_result is not None
        assert len(created_for) == 1
        assert created_for[0] is result.evidence_packet
        assert closed == [True]
        assert [call["stage"] for call in port.calls] == [
            "blind_inventory",
            "physical_proposal",
            "conditioned_validator_0",
        ]


def test_visual_provenance_cli_assesses_current_content_free_artifacts(tmp_path: Path) -> None:
    with physical_session() as session:
        result, estimate, _defect, _parent, _port, _storage, _report = _run(
            session,
            tmp_path=tmp_path,
        )
        assert result.evidence_packet is not None
        receipt_path = tmp_path / "linked-visual-run-receipt.json"
        inventory_path = tmp_path / "evidence-family-inventory.json"
        receipt_path.write_text(json.dumps(result.receipt), encoding="utf-8")
        inventory_path.write_text(
            json.dumps(result.evidence_packet.evidence_family_inventory),
            encoding="utf-8",
        )
        repository_root = Path(__file__).parents[1]
        command_result = subprocess.run(  # noqa: S603 -- fixed local CLI test fixture
            [
                sys.executable,
                str(repository_root / "scripts" / "assess_phase8_visual_provenance.py"),
                "--linked-visual-run-receipt",
                str(receipt_path),
                "--evidence-family-inventory",
                str(inventory_path),
                "--estimate-id",
                estimate.id,
                "--defect-reference",
                "D-001",
            ],
            capture_output=True,
            check=False,
            cwd=repository_root,
            env={**os.environ, "PYTHONPATH": str(repository_root / "src")},
            text=True,
        )

        assert command_result.returncode == 0, command_result.stderr
        assert json.loads(command_result.stdout)["complete"] is True


def test_infected_retention_receipt_survives_atomic_runner_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detected_sha256: list[str] = []

    def reject_after_containment(
        session,
        *,
        storage_root: Path,
        retrieval_root: Path,
        result,
        operator_reference: str,
        **_kwargs,
    ):
        source_path = Path(result.stored_path)
        if not source_path.is_absolute():
            source_path = retrieval_root / source_path
        infected = malware_scan_result(source_path.read_bytes(), verdict="infected")
        record_detected_sha(
            session,
            storage_root,
            sha=infected.content_sha256,
            size=infected.content_size_bytes,
            filename=f"linked-image-{infected.content_sha256[:12]}.jpg",
            media_type="image/jpeg",
            purpose="technical_evidence",
            user=None,
            result=infected,
            scan_source="linked_image_retention",
            actor_type="human_operator",
            actor_name=operator_reference,
        )
        detected_sha256.append(infected.content_sha256)
        raise LinkedImageMalwareQuarantinedError(infected)

    monkeypatch.setattr(
        linked_run_service,
        "retain_verified_linked_image",
        reject_after_containment,
    )

    with physical_session() as session:
        with pytest.raises(Phase8LinkedVisualRunError) as rejected:
            _run(session, tmp_path=tmp_path)

        assert rejected.value.code == "MALWARE_DETECTED"
        assert len(detected_sha256) == 1
        stored = session.scalar(
            select(StoredFile).where(StoredFile.sha256 == detected_sha256[0])
        )
        assert stored is not None
        assert stored.malware_scan_status == "infected"
        assert not Path(stored.storage_path).exists()
        attestations = session.scalars(
            select(MalwareScanAttestation).where(
                MalwareScanAttestation.stored_file_id == stored.id
            )
        ).all()
        assert len(attestations) == 1
        assert attestations[0].verdict == "infected"
        assert attestations[0].scan_source == "linked_image_retention"

        # The runner still never commits; the caller can durably preserve the
        # independent safety receipt after the failed proposal transaction.
        session.commit()
        session.expire_all()
        persisted = session.get(StoredFile, stored.id)
        assert persisted is not None
        assert persisted.malware_scan_status == "infected"
