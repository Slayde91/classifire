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
from physical_foundation_support import physical_session
from pydantic import ValidationError
from pypdf import PdfReader
from sqlalchemy import select
from starlette.requests import Request

from classifire.api.router import export_desk_quote
from classifire.config import Settings
from classifire.models import AuditEvent, LibraryRelease, PricingLibraryRecord, User
from classifire.outputs import render_desk_quote_pdf, render_desk_quote_workbook
from classifire.physical_models import PhysicalModelLock
from classifire.services.desk_quote import (
    DESK_QUOTE_DOCUMENT_CLASS,
    DESK_QUOTE_TECHNICAL_POSITION,
    DeskQuoteError,
    DeskQuoteProposal,
    build_desk_quote_snapshot,
    resolve_desk_quote_pricing_bindings,
    verify_desk_quote_snapshot,
)


def _proposal(
    *,
    pricing_release_id: str = "pricing-release-1001",
    pricing_record_id: str = "pricing-record-1001",
) -> dict[str, Any]:
    return {
        "schema_version": "CLASSIFIRE_DESK_QUOTE_V1",
        "quote_reference": "DQ-1001",
        "title": "Report-based fire-stopping allowance",
        "project_reference": "PROJECT-1001",
        "project_name": "Example Building",
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
                        "evidence_reference": "Inspection report REP-1001",
                        "file_sha256": "A" * 64,
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
                        "evidence_reference": "Inspection report REP-1001",
                        "file_sha256": "B" * 64,
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


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "headers": [],
            "client": ("127.0.0.1", 50000),
        }
    )


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
    assert "Governed Pricing Record" in workbook_text
    assert "PF-101" in workbook_text
    assert "PR-2026-08" in workbook_text

    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(pdf_path).pages)
    assert "ASSUMPTION-LED COMMERCIAL ALLOWANCE" in pdf_text
    assert "A-OPENING-01" in pdf_text
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


def test_desk_quote_export_route_renders_and_audits_without_a_physical_model_lock(
    tmp_path: Path,
) -> None:
    with physical_session() as session:
        release, record = _active_pricing_release(session)
        user = User(
            email="desk-quote@example.test",
            full_name="Desk Quote Estimator",
            password_hash="not-used-by-direct-handler-test",  # noqa: S106
            role="administrator",
        )
        session.add(user)
        session.flush()

        response = export_desk_quote(
            "desk-quote-pdf",
            DeskQuoteProposal.model_validate(
                _proposal(pricing_release_id=release.id, pricing_record_id=record.id)
            ),
            _request(),
            session,
            user,
            Settings(storage_root=tmp_path),
        )

        output_path = Path(response.path)
        assert output_path.exists()
        assert "desk-quote-exports" in output_path.parts
        audit = session.scalar(select(AuditEvent).where(AuditEvent.action == "render_desk_quote"))
        assert audit is not None
        assert audit.entity_type == "desk_quote"
        assert audit.new_value["technical_position"] == DESK_QUOTE_TECHNICAL_POSITION
        assert audit.new_value["pricing_release_id"] == release.id
        assert audit.new_value["pricing_release_version"] == release.version
        assert audit.new_value["pricing_release_hash"] == release.release_hash
        assert session.scalar(select(PhysicalModelLock)) is None
