from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pytest
from fastapi import HTTPException
from physical_foundation_support import physical_session
from pydantic import ValidationError
from pypdf import PdfReader
from sqlalchemy import select
from starlette.requests import Request

from classifire.api.router import export_desk_quote
from classifire.config import Settings
from classifire.models import (
    AuditEvent,
    Estimate,
    LibraryRelease,
    PricingLibraryRecord,
    Project,
    ProjectEvidence,
    ReportEvidenceLocator,
    StoredFile,
    User,
)
from classifire.outputs import render_desk_quote_pdf, render_desk_quote_workbook
from classifire.physical_models import EvidenceSource, PhysicalModelLock
from classifire.services import desk_quote as desk_quote_module
from classifire.services.desk_quote import (
    DESK_QUOTE_DOCUMENT_CLASS,
    DESK_QUOTE_TECHNICAL_POSITION,
    DeskQuoteError,
    DeskQuoteProposal,
    build_desk_quote_snapshot,
    resolve_desk_quote_pricing_bindings,
    resolve_desk_quote_project_evidence,
    verify_desk_quote_snapshot,
)
from classifire.services.project_evidence import bind_project_evidence
from classifire.services.storage import StoredFileBindingError, VerifiedStoredFileContent


def _proposal(
    *,
    pricing_release_id: str = "pricing-release-1001",
    pricing_record_id: str = "pricing-record-1001",
    evidence_source_ids: tuple[str, str] = ("evidence-source-1001", "evidence-source-1002"),
    estimate_reference: str = "DQ-TEST-ESTIMATE",
    evidence_file_sha256s: tuple[str, str] = ("A" * 64, "B" * 64),
) -> dict[str, Any]:
    return {
        "schema_version": "CLASSIFIRE_DESK_QUOTE_V1",
        "quote_reference": "DQ-1001",
        "title": "Report-based fire-stopping allowance",
        "project_reference": "PROJECT-1001",
        "project_name": "Example Building",
        "estimate_reference": estimate_reference,
        "site_address": "1 Example Street",
        "client_name": "Example Client",
        "pricing_release_id": pricing_release_id,
        "report_scope": "Defect 17 shown in report photographs on pages 8 and 9.",
        "assumptions": [
            {
                "assumption_id": "A-OPENING-01",
                "subject_reference": "Defect 17 / apparent opening 1",
                "fact_type": "opening_dimensions",
                "status": "inferred",
                "value": "opening is approximately 300 mm by 150 mm",
                "probability_percent": 75,
                "confidence": "medium",
                "evidence_locators": [
                    {
                        "evidence_source_id": evidence_source_ids[0],
                        "evidence_reference": "Inspection report REP-1001",
                        "file_sha256": evidence_file_sha256s[0],
                        "locator": "page 8, photo 2",
                        "description": "Wall penetration image without a scale.",
                    }
                ],
                "rationale": (
                    "The visible conduit bundle occupies about half the apparent opening width."
                ),
                "alternative_explanation": (
                    "Perspective or crop scale may make the opening materially larger."
                ),
                "commercial_treatment": "included_allowance",
                "verification_action": (
                    "Measure the opening at first access before installing any system."
                ),
            },
            {
                "assumption_id": "A-SUBSTRATE-01",
                "subject_reference": "Defect 17 / wall substrate",
                "fact_type": "substrate",
                "status": "unresolved",
                "value": None,
                "probability_percent": 0,
                "confidence": "low",
                "evidence_locators": [
                    {
                        "evidence_source_id": evidence_source_ids[1],
                        "evidence_reference": "Inspection report REP-1001",
                        "file_sha256": evidence_file_sha256s[1],
                        "locator": "page 9, photo 4",
                    }
                ],
                "rationale": "The exposed edge is obscured by the existing seal.",
                "alternative_explanation": "The wall may be masonry, concrete, or framed lining.",
                "commercial_treatment": "excluded_pending_verification",
                "verification_action": (
                    "Confirm substrate and thickness at access before pricing any "
                    "substrate-specific work."
                ),
            },
        ],
        "allowances": [
            {
                "allowance_id": "AL-001",
                "description": (
                    "Allowance for opening preparation and service sealing based on A-OPENING-01."
                ),
                "quantity": "2",
                "pricing_record_id": pricing_record_id,
                "assumption_ids": ["A-OPENING-01"],
            }
        ],
        "additional_exclusions": [
            "No allowance for concealed conditions not visible in the report."
        ],
    }


def _pricing_binding(
    *,
    pricing_release_id: str = "pricing-release-1001",
    pricing_record_id: str = "pricing-record-1001",
) -> dict[str, Any]:
    return {
        "pricing_record_id": pricing_record_id,
        "pkb_entry_id": "PF-101",
        "entry_version": "1",
        "description": "Opening preparation and service sealing allowance",
        "unit": "each",
        "unit_rate_ex_tax": "200",
        "currency": "AUD",
        "pricing_release_id": pricing_release_id,
        "pricing_release_version": "PR-2026-08",
        "pricing_release_hash": "C" * 64,
        "record_source_hash": "D" * 64,
    }


def _snapshot() -> dict[str, Any]:
    return build_desk_quote_snapshot(
        _proposal(),
        pricing_bindings=[_pricing_binding()],
        generated_utc=datetime(2026, 8, 25, 10, 30, tzinfo=UTC),
    )


def _manifest_hash(manifest: dict[str, Any]) -> str:
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _pricing_manifest(record: PricingLibraryRecord) -> dict[str, Any]:
    return {
        "records": [
            {
                "id": record.id,
                "entry_version": record.entry_version,
                "rate_ex_tax": str(record.rate_ex_tax),
                "source_hash": record.source_hash,
                "record_version": record.record_version,
            }
        ]
    }


def _active_pricing_release(session: Any) -> tuple[LibraryRelease, PricingLibraryRecord]:
    release = LibraryRelease(
        library_type="pricing",
        version="PR-2026-08",
        status="active",
        effective_date=date.today(),
    )
    session.add(release)
    session.flush()
    record = PricingLibraryRecord(
        pkb_entry_id="PF-101",
        entry_version="1",
        description="Opening preparation and service sealing allowance",
        unit="each",
        rate_ex_tax=Decimal("200"),
        currency="AUD",
        status="active",
        effective_date=date.today(),
        source_hash="D" * 64,
        source_json={"fixture": "desk-quote"},
        release_id=release.id,
    )
    session.add(record)
    session.flush()
    manifest = _pricing_manifest(record)
    release.source_manifest = manifest
    release.release_hash = _manifest_hash(manifest)
    session.flush()
    return release, record


def _retained_project_evidence(
    session: Any,
    *,
    storage_root: Path,
) -> tuple[Project, Estimate, tuple[EvidenceSource, EvidenceSource]]:
    project = Project(reference="PROJECT-1001", name="Example Building")
    session.add(project)
    session.flush()
    estimate = Estimate(
        project_id=project.id,
        reference="DQ-TEST-ESTIMATE",
        title="Desk quote evidence test",
    )
    session.add(estimate)
    session.flush()

    storage_root.mkdir()
    evidence: list[EvidenceSource] = []
    locations = (("8", "photo 2"), ("9", "photo 4"))
    for index, (page_number, region_reference) in enumerate(locations, start=1):
        content = f"synthetic retained report {index}\\n".encode()
        path = storage_root / "project-evidence" / f"inspection-report-{index}.pdf"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        stored = StoredFile(
            original_filename=path.name,
            media_type="application/pdf",
            storage_path=str(path),
            sha256=digest,
            size_bytes=len(content),
            purpose="project_evidence",
            malware_scan_status="clean",
            immutable=True,
        )
        session.add(stored)
        session.flush()
        bind_project_evidence(session, stored_file_id=stored.id, estimate_id=estimate.id)
        item = EvidenceSource(
            estimate_id=estimate.id,
            stored_file_id=stored.id,
            evidence_type="inspection_report",
            source_reference="Inspection report REP-1001",
            page_number=page_number,
            region_reference=region_reference,
            sha256=digest,
            evidence_class="observed",
            status="active",
        )
        session.add(item)
        evidence.append(item)
    session.flush()
    return project, estimate, (evidence[0], evidence[1])


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "headers": [],
            "client": ("127.0.0.1", 50000),
        }
    )


def _evidence_proposal(
    estimate: Estimate,
    evidence: tuple[EvidenceSource, EvidenceSource],
) -> DeskQuoteProposal:
    return DeskQuoteProposal.model_validate(
        _proposal(
            estimate_reference=estimate.reference,
            evidence_source_ids=(evidence[0].id, evidence[1].id),
            evidence_file_sha256s=(str(evidence[0].sha256), str(evidence[1].sha256)),
        )
    )


def _fake_clean_reader(session: Any, calls: list[tuple[str, str, str, Path]]):
    def read(
        _db: Any,
        *,
        stored_file_id: str,
        project_id: str,
        estimate_id: str,
        storage_root: Path,
    ) -> VerifiedStoredFileContent:
        stored = session.get(StoredFile, stored_file_id)
        assert stored is not None
        calls.append((stored_file_id, project_id, estimate_id, storage_root))
        return VerifiedStoredFileContent(
            sha256=stored.sha256.lower(),
            size_bytes=stored.size_bytes,
            media_type=stored.media_type,
            content=b'synthetic verified content',
        )

    return read


def test_desk_quote_snapshot_binds_assumptions_allowances_and_qualifications() -> None:
    snapshot = _snapshot()

    verify_desk_quote_snapshot(snapshot)

    assert snapshot["document_class"] == DESK_QUOTE_DOCUMENT_CLASS
    assert snapshot["technical_position"] == DESK_QUOTE_TECHNICAL_POSITION
    assert snapshot["totals"] == {
        "subtotal_ex_tax": "400",
        "tax_total": "40.00",
        "total_incl_tax": "440.00",
    }
    assert any("no site inspection" in item.lower() for item in snapshot["qualifications"])
    assert any("A-SUBSTRATE-01" in item for item in snapshot["exclusions"])
    assert snapshot["pricing_bindings"] == [_pricing_binding()]
    assert snapshot["allowances"][0]["rate_binding"] == _pricing_binding()
    assert snapshot["allowances"][0]["unit"] == "each"
    assert snapshot["allowances"][0]["unit_rate_ex_tax"] == "200"


def test_desk_quote_rejects_observed_or_unpriced_assumption_shortcuts() -> None:
    observed = _proposal()
    observed["assumptions"][0]["status"] = "observed"  # type: ignore[index]
    with pytest.raises(ValidationError):
        DeskQuoteProposal.model_validate(observed)

    missing_hash = _proposal()
    del missing_hash["assumptions"][0]["evidence_locators"][0]["file_sha256"]  # type: ignore[index]
    with pytest.raises(ValidationError, match="file_sha256"):
        DeskQuoteProposal.model_validate(missing_hash)

    unpriced = _proposal()
    unpriced["assumptions"][1]["commercial_treatment"] = "included_allowance"  # type: ignore[index]
    with pytest.raises(ValidationError, match="unresolved desk-quote assumptions"):
        DeskQuoteProposal.model_validate(unpriced)

    manual_rate = _proposal()
    manual_rate["allowances"][0]["unit_rate_ex_tax"] = "200"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DeskQuoteProposal.model_validate(manual_rate)

    excluded = _proposal()
    excluded["allowances"][0]["assumption_ids"] = ["A-SUBSTRATE-01"]  # type: ignore[index]
    with pytest.raises(ValidationError, match="excluded pending verification"):
        DeskQuoteProposal.model_validate(excluded)


def test_desk_quote_pricing_resolver_requires_active_hash_bound_records() -> None:
    with physical_session() as session:
        release, record = _active_pricing_release(session)
        proposal = DeskQuoteProposal.model_validate(
            _proposal(pricing_release_id=release.id, pricing_record_id=record.id)
        )

        bindings = resolve_desk_quote_pricing_bindings(session, proposal)
        assert bindings[0].pricing_record_id == record.id
        assert bindings[0].unit_rate_ex_tax == Decimal("200")
        assert bindings[0].pricing_release_hash == release.release_hash

        empty_manifest = {"records": [{"id": "another-pricing-record"}]}
        release.source_manifest = empty_manifest
        release.release_hash = _manifest_hash(empty_manifest)
        session.flush()
        with pytest.raises(DeskQuoteError, match="not present in the declared pricing release"):
            resolve_desk_quote_pricing_bindings(session, proposal)

        manifest = _pricing_manifest(record)
        release.source_manifest = manifest
        release.release_hash = _manifest_hash(manifest)
        record.source_hash = "E" * 64
        session.flush()
        with pytest.raises(DeskQuoteError, match="source hash does not match"):
            resolve_desk_quote_pricing_bindings(session, proposal)

        record.source_hash = "D" * 64
        record.rate_ex_tax = Decimal("250")
        session.flush()
        with pytest.raises(DeskQuoteError, match="rate does not match"):
            resolve_desk_quote_pricing_bindings(session, proposal)

        record.rate_ex_tax = Decimal("200")
        record.status = "draft"
        session.flush()
        with pytest.raises(DeskQuoteError, match="pricing record is not active"):
            resolve_desk_quote_pricing_bindings(session, proposal)


def test_desk_quote_evidence_resolver_requires_retained_project_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with physical_session() as session:
        storage_root = tmp_path / "storage"
        project, estimate, evidence = _retained_project_evidence(
            session,
            storage_root=storage_root,
        )
        proposal = _evidence_proposal(estimate, evidence)
        calls: list[tuple[str, str, str, Path]] = []
        monkeypatch.setattr(
            desk_quote_module,
            "read_project_evidence_for_update",
            _fake_clean_reader(session, calls),
        )

        def resolve(value: DeskQuoteProposal) -> Project:
            return resolve_desk_quote_project_evidence(
                session,
                value,
                storage_root=storage_root,
            )

        resolved = resolve(proposal)
        assert resolved.id == project.id
        assert {(item[0], item[1], item[2]) for item in calls} == {
            (evidence[0].stored_file_id, project.id, estimate.id),
            (evidence[1].stored_file_id, project.id, estimate.id),
        }

        missing = _proposal(evidence_source_ids=("missing-evidence-source", evidence[1].id))
        with pytest.raises(DeskQuoteError, match="evidence source is missing"):
            resolve(DeskQuoteProposal.model_validate(missing))

        evidence[0].status = "draft"
        session.flush()
        with pytest.raises(DeskQuoteError, match="evidence source is not active"):
            resolve(proposal)

        evidence[0].status = "active"
        stored = session.get(StoredFile, evidence[0].stored_file_id)
        assert stored is not None
        stored.immutable = False
        session.flush()
        with pytest.raises(DeskQuoteError, match="retained evidence file is not immutable"):
            resolve(proposal)

        stored.immutable = True
        original_sha256 = str(evidence[0].sha256)
        evidence[0].sha256 = "c" * 64
        session.flush()
        with pytest.raises(DeskQuoteError, match="source digest does not match"):
            resolve(proposal)

        evidence[0].sha256 = original_sha256
        mismatched_digest = _proposal(
            estimate_reference=estimate.reference,
            evidence_source_ids=(evidence[0].id, evidence[1].id),
            evidence_file_sha256s=("c" * 64, str(evidence[1].sha256)),
        )
        with pytest.raises(DeskQuoteError, match="locator digest does not match"):
            resolve(DeskQuoteProposal.model_validate(mismatched_digest))

        mismatched_reference = _proposal(
            estimate_reference=estimate.reference,
            evidence_source_ids=(evidence[0].id, evidence[1].id),
            evidence_file_sha256s=(str(evidence[0].sha256), str(evidence[1].sha256)),
        )
        mismatched_reference["assumptions"][0]["evidence_locators"][0]["evidence_reference"] = (
            "Other report"
        )
        with pytest.raises(DeskQuoteError, match="reference does not match"):
            resolve(DeskQuoteProposal.model_validate(mismatched_reference))

        mismatched_locator = _proposal(
            estimate_reference=estimate.reference,
            evidence_source_ids=(evidence[0].id, evidence[1].id),
            evidence_file_sha256s=(str(evidence[0].sha256), str(evidence[1].sha256)),
        )
        mismatched_locator["assumptions"][0]["evidence_locators"][0]["locator"] = "page 8, photo 3"
        calls.clear()
        with pytest.raises(DeskQuoteError, match="locator does not match"):
            resolve(DeskQuoteProposal.model_validate(mismatched_locator))
        assert calls == []

        bound = session.scalar(
            select(ProjectEvidence).where(
                ProjectEvidence.stored_file_id == evidence[0].stored_file_id
            )
        )
        assert bound is not None
        report_locator = ReportEvidenceLocator(
            project_evidence_id=bound.id,
            source_sha256=bound.source_sha256,
            sequence=1,
            locator_key="report-locator-for-desk-quote",
            item_kind="page",
            page_number=8,
            content_sha256="d" * 64,
            locator_json={"item_kind": "page", "page_number": 8, "sequence": 1},
        )
        session.add(report_locator)
        evidence[0].page_number = None
        evidence[0].region_reference = None
        session.flush()
        stable_locator = _proposal(
            estimate_reference=estimate.reference,
            evidence_source_ids=(evidence[0].id, evidence[1].id),
            evidence_file_sha256s=(str(evidence[0].sha256), str(evidence[1].sha256)),
        )
        stable_locator["assumptions"][0]["evidence_locators"][0]["locator"] = (
            report_locator.locator_key
        )
        resolve(DeskQuoteProposal.model_validate(stable_locator))

        evidence[0].page_number = "8"
        evidence[0].region_reference = "photo 2"
        stored.malware_scan_status = "not_configured"
        session.flush()
        with pytest.raises(DeskQuoteError, match="unsafe scan status"):
            resolve(proposal)

        stored.malware_scan_status = "clean"
        stored.purpose = "technical_evidence"
        session.flush()
        with pytest.raises(DeskQuoteError, match="wrong purpose"):
            resolve(proposal)

        stored.purpose = "project_evidence"
        foreign_project = Project(reference="OTHER-PROJECT", name="Other project")
        session.add(foreign_project)
        session.flush()
        foreign_estimate = Estimate(
            project_id=foreign_project.id,
            reference="OTHER-ESTIMATE",
            title="Other project evidence",
        )
        session.add(foreign_estimate)
        session.flush()
        evidence[0].estimate_id = foreign_estimate.id
        session.flush()
        with pytest.raises(DeskQuoteError, match="does not belong to the estimate"):
            resolve(proposal)

        evidence[0].estimate_id = estimate.id
        session.flush()

        def unavailable_reader(*_args: Any, **_kwargs: Any) -> VerifiedStoredFileContent:
            raise StoredFileBindingError("STORED_FILE_HASH_MISMATCH")

        monkeypatch.setattr(
            desk_quote_module,
            "read_project_evidence_for_update",
            unavailable_reader,
        )
        with pytest.raises(DeskQuoteError, match="STORED_FILE_HASH_MISMATCH"):
            resolve(proposal)

        bound = session.scalar(
            select(ProjectEvidence).where(
                ProjectEvidence.stored_file_id == evidence[0].stored_file_id
            )
        )
        assert bound is not None
        session.delete(bound)
        session.flush()
        with pytest.raises(DeskQuoteError, match="PROJECT_EVIDENCE_NOT_FOUND"):
            resolve(proposal)


def test_desk_quote_outputs_show_assumption_led_position_and_fail_closed_on_tamper(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()
    workbook_path = render_desk_quote_workbook(snapshot, tmp_path / "desk-quote.xlsx")
    pdf_path = render_desk_quote_pdf(snapshot, tmp_path / "desk-quote.pdf")

    with ZipFile(workbook_path) as workbook:
        workbook_text = "\n".join(
            workbook.read(name).decode("utf-8", errors="ignore")
            for name in workbook.namelist()
            if name.endswith(".xml")
        )
    assert "ASSUMPTION-LED COMMERCIAL ALLOWANCE" in workbook_text
    assert "A-OPENING-01" in workbook_text
    assert "A-SUBSTRATE-01" in workbook_text
    assert "evidence-source-1001" in workbook_text
    assert "Governed Pricing Record" in workbook_text
    assert "PF-101" in workbook_text
    assert "PR-2026-08" in workbook_text

    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(pdf_path).pages)
    assert "ASSUMPTION-LED COMMERCIAL ALLOWANCE" in pdf_text
    assert "A-OPENING-01" in pdf_text
    assert "evidence-source-1001" in pdf_text
    assert "Commercial pricing basis" in pdf_text
    assert "PF-101" in pdf_text
    assert "PR-2026-08" in pdf_text

    assert "not a technical system selection" in pdf_text

    tampered = deepcopy(snapshot)
    tampered["totals"]["total_incl_tax"] = "0"  # type: ignore[index]
    with pytest.raises(DeskQuoteError, match="contents"):
        render_desk_quote_workbook(tampered, tmp_path / "tampered-content.xlsx")

    binding_tampered = deepcopy(snapshot)
    binding_tampered["pricing_bindings"][0]["record_source_hash"] = "E" * 64
    with pytest.raises(DeskQuoteError, match="pricing bindings"):
        render_desk_quote_workbook(binding_tampered, tmp_path / "tampered-binding.xlsx")

    hash_tampered = deepcopy(snapshot)
    hash_tampered["snapshot_hash"] = "0" * 64
    with pytest.raises(DeskQuoteError, match="hash"):
        render_desk_quote_workbook(hash_tampered, tmp_path / "tampered-hash.xlsx")


def test_desk_quote_export_route_returns_audited_exact_bytes_and_rejects_tampered_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with physical_session() as session:
        storage_root = tmp_path / "storage"
        release, record = _active_pricing_release(session)
        project, estimate, evidence = _retained_project_evidence(
            session,
            storage_root=storage_root,
        )
        user = User(
            email="desk-quote@example.test",
            full_name="Desk Quote Estimator",
            password_hash="not-used-by-direct-handler-test",  # noqa: S106
            role="administrator",
        )
        session.add(user)
        session.flush()
        proposal = DeskQuoteProposal.model_validate(
            _proposal(
                pricing_release_id=release.id,
                pricing_record_id=record.id,
                estimate_reference=estimate.reference,
                evidence_source_ids=(evidence[0].id, evidence[1].id),
                evidence_file_sha256s=(str(evidence[0].sha256), str(evidence[1].sha256)),
            )
        )
        calls: list[tuple[str, str, str, Path]] = []
        monkeypatch.setattr(
            desk_quote_module,
            "read_project_evidence_for_update",
            _fake_clean_reader(session, calls),
        )
        fixed_snapshot = build_desk_quote_snapshot(
            proposal,
            pricing_bindings=resolve_desk_quote_pricing_bindings(session, proposal),
            generated_utc=datetime(2026, 8, 31, 12, 0, tzinfo=UTC),
        )
        monkeypatch.setitem(
            export_desk_quote.__globals__,
            "build_desk_quote_snapshot",
            lambda _proposal, *, pricing_bindings: fixed_snapshot,
        )
        settings = Settings(storage_root=storage_root)

        response = export_desk_quote(
            "desk-quote-pdf",
            proposal,
            _request(),
            session,
            user,
            settings,
        )

        output_path = (
            storage_root
            / "desk-quote-exports"
            / fixed_snapshot["snapshot_hash"]
            / "CLASSIFIRE_DQ-1001_Desk_Quote.pdf"
        )
        assert output_path.exists()
        assert response.body == output_path.read_bytes()
        audit = session.scalar(select(AuditEvent).where(AuditEvent.action == "render_desk_quote"))
        assert audit is not None
        assert audit.entity_type == "desk_quote"
        assert audit.new_value["artifact_sha256"] == hashlib.sha256(response.body).hexdigest()
        assert audit.new_value["artifact_size_bytes"] == len(response.body)
        assert audit.new_value["technical_position"] == DESK_QUOTE_TECHNICAL_POSITION
        assert audit.new_value["estimate_reference"] == estimate.reference
        assert audit.new_value["pricing_release_id"] == release.id
        assert audit.new_value["pricing_release_version"] == release.version
        assert audit.new_value["pricing_release_hash"] == release.release_hash
        assert audit.new_value["evidence_source_ids"] == sorted(item.id for item in evidence)
        assert audit.new_value["evidence_file_sha256"] == sorted(
            str(item.sha256) for item in evidence
        )
        assert session.scalar(select(PhysicalModelLock)) is None
        assert {item[1] for item in calls} == {project.id}

        cached = export_desk_quote(
            "desk-quote-pdf",
            proposal,
            _request(),
            session,
            user,
            settings,
        )
        assert cached.body == response.body
        assert len(list(session.scalars(select(AuditEvent)))) == 2

        output_path.write_bytes(b"tampered cached export")
        with pytest.raises(HTTPException, match="cached export bytes do not match"):
            export_desk_quote(
                "desk-quote-pdf",
                proposal,
                _request(),
                session,
                user,
                settings,
            )
        assert len(list(session.scalars(select(AuditEvent)))) == 2


def test_desk_quote_failed_evidence_read_creates_no_export_or_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with physical_session() as session:
        storage_root = tmp_path / "storage"
        release, record = _active_pricing_release(session)
        _project, estimate, evidence = _retained_project_evidence(
            session,
            storage_root=storage_root,
        )
        user = User(
            email="desk-quote-failure@example.test",
            full_name="Desk Quote Estimator",
            password_hash="not-used-by-direct-handler-test",  # noqa: S106
            role="administrator",
        )
        session.add(user)
        session.flush()
        proposal = DeskQuoteProposal.model_validate(
            _proposal(
                pricing_release_id=release.id,
                pricing_record_id=record.id,
                estimate_reference=estimate.reference,
                evidence_source_ids=(evidence[0].id, evidence[1].id),
                evidence_file_sha256s=(str(evidence[0].sha256), str(evidence[1].sha256)),
            )
        )

        def unavailable_reader(*_args: Any, **_kwargs: Any) -> VerifiedStoredFileContent:
            raise StoredFileBindingError("STORED_FILE_HASH_MISMATCH")

        monkeypatch.setattr(
            desk_quote_module,
            "read_project_evidence_for_update",
            unavailable_reader,
        )
        with pytest.raises(HTTPException, match="STORED_FILE_HASH_MISMATCH"):
            export_desk_quote(
                "desk-quote-pdf",
                proposal,
                _request(),
                session,
                user,
                Settings(storage_root=storage_root),
            )

        assert not (storage_root / "desk-quote-exports").exists()
        assert list(session.scalars(select(AuditEvent))) == []
        assert session.scalar(select(PhysicalModelLock)) is None
