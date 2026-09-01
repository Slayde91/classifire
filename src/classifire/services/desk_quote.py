"""Strict, no-write desk-quote contracts for assumption-led proposals.

Desk quotes are useful when a report and photographs are the only available
evidence.  They must remain visibly different from observed evidence, a
canonical Physical Model, or a technical suitability determination.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Estimate,
    LibraryRelease,
    PricingLibraryRecord,
    Project,
    ProjectEvidence,
    ReportEvidenceLocator,
    StoredFile,
)
from ..physical_models import EvidenceSource
from .project_evidence import (
    ProjectEvidenceError,
    read_project_evidence_for_update,
    require_project_evidence_access,
)
from .storage import StoredFileBindingError

DESK_QUOTE_SCHEMA = "CLASSIFIRE_DESK_QUOTE_V1"
DESK_QUOTE_SNAPSHOT_SCHEMA = "CLASSIFIRE_DESK_QUOTE_SNAPSHOT_V1"
DESK_QUOTE_DOCUMENT_CLASS = "ASSUMPTION_LED_DESK_QUOTE_PROPOSAL"
DESK_QUOTE_TECHNICAL_POSITION = "UNVERIFIED_NOT_A_TECHNICAL_DETERMINATION"


class DeskQuoteError(ValueError):
    """Raised when a desk-quote payload or receipt crosses its safety boundary."""


class _StrictDeskQuoteModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DeskQuoteEvidenceLocator(_StrictDeskQuoteModel):
    """One retained report, drawing, register, or image location supporting an assumption."""

    evidence_source_id: str = Field(min_length=1, max_length=100)
    evidence_reference: str = Field(min_length=1, max_length=300)
    file_sha256: str = Field(pattern=r"^[A-Fa-f0-9]{64}$")
    locator: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=1000)


class DeskQuoteAssumption(_StrictDeskQuoteModel):
    """A non-observed fact used only to state a bounded commercial scenario."""

    assumption_id: str = Field(min_length=1, max_length=100)
    subject_reference: str = Field(min_length=1, max_length=300)
    fact_type: Literal[
        "opening_dimensions",
        "opening_depth_or_boundary",
        "substrate",
        "substrate_plane_or_orientation",
        "frl",
        "service_identification",
        "service_material",
        "service_size",
        "service_quantity",
        "opposite_face_continuity",
        "access_or_working_conditions",
        "other_scope_condition",
    ]
    status: Literal["inferred", "provisional", "assumed", "unresolved"]
    value: str | None = Field(default=None, max_length=1000)
    probability_percent: int = Field(ge=0, le=99)
    confidence: Literal["low", "medium", "high"]
    evidence_locators: list[DeskQuoteEvidenceLocator] = Field(min_length=1, max_length=25)
    rationale: str = Field(min_length=1, max_length=2000)
    alternative_explanation: str = Field(min_length=1, max_length=2000)
    commercial_treatment: Literal[
        "included_allowance",
        "variation_risk",
        "excluded_pending_verification",
    ]
    verification_action: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_uncertainty(self) -> DeskQuoteAssumption:
        if self.status == "unresolved":
            if self.value is not None:
                raise ValueError("unresolved desk-quote assumptions must not provide a value")
            if self.probability_percent != 0:
                raise ValueError(
                    "unresolved desk-quote assumptions must have probability_percent 0"
                )
            if self.commercial_treatment != "excluded_pending_verification":
                raise ValueError(
                    "unresolved desk-quote assumptions must be excluded pending verification"
                )
        elif not self.value:
            raise ValueError(
                "inferred, provisional, and assumed desk-quote assumptions require a value"
            )
        elif self.probability_percent == 0:
            raise ValueError("resolved desk-quote assumptions require probability_percent above 0")
        return self


class DeskQuoteAllowance(_StrictDeskQuoteModel):
    """A priced commercial allowance, explicitly linked to its assumptions."""

    allowance_id: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=4)
    pricing_record_id: str = Field(min_length=1, max_length=100)
    assumption_ids: list[str] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_assumption_ids(self) -> DeskQuoteAllowance:
        if len(set(self.assumption_ids)) != len(self.assumption_ids):
            raise ValueError("desk-quote allowance assumption_ids must be unique")
        return self


class DeskQuoteProposal(_StrictDeskQuoteModel):
    """Input for one source-linked, assumption-led commercial proposal."""

    schema_version: Literal["CLASSIFIRE_DESK_QUOTE_V1"]
    quote_reference: str = Field(min_length=1, max_length=150)
    title: str = Field(min_length=1, max_length=300)
    project_reference: str = Field(min_length=1, max_length=150)
    estimate_reference: str = Field(min_length=1, max_length=150)
    project_name: str = Field(min_length=1, max_length=300)
    site_address: str | None = Field(default=None, max_length=1000)
    client_name: str | None = Field(default=None, max_length=300)
    currency: str = Field(default="AUD", pattern=r"^[A-Z]{3}$")
    pricing_release_id: str = Field(min_length=1, max_length=100)
    tax_name: str = Field(default="GST", min_length=1, max_length=50)
    tax_rate: Decimal = Field(default=Decimal("0.10"), ge=0, le=1, max_digits=7, decimal_places=6)
    report_scope: str = Field(min_length=1, max_length=2000)
    assumptions: list[DeskQuoteAssumption] = Field(min_length=1, max_length=500)
    allowances: list[DeskQuoteAllowance] = Field(min_length=1, max_length=500)
    additional_exclusions: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_references(self) -> DeskQuoteProposal:
        assumption_ids = [item.assumption_id for item in self.assumptions]
        if len(set(assumption_ids)) != len(assumption_ids):
            raise ValueError("desk-quote assumption_id values must be unique")
        allowance_ids = [item.allowance_id for item in self.allowances]
        if len(set(allowance_ids)) != len(allowance_ids):
            raise ValueError("desk-quote allowance_id values must be unique")

        by_id = {item.assumption_id: item for item in self.assumptions}
        referenced: set[str] = set()
        for allowance in self.allowances:
            unknown = set(allowance.assumption_ids) - set(by_id)
            if unknown:
                raise ValueError(
                    "desk-quote allowance references unknown assumption_ids: "
                    + ", ".join(sorted(unknown))
                )
            for assumption_id in allowance.assumption_ids:
                treatment = by_id[assumption_id].commercial_treatment
                if treatment == "excluded_pending_verification":
                    raise ValueError(
                        "desk-quote allowance cannot price an assumption excluded "
                        "pending verification: " + assumption_id
                    )
                referenced.add(assumption_id)

        included = {
            item.assumption_id
            for item in self.assumptions
            if item.commercial_treatment == "included_allowance"
        }
        missing = included - referenced
        if missing:
            raise ValueError(
                "included_allowance assumptions must support a priced allowance: "
                + ", ".join(sorted(missing))
            )
        return self


class DeskQuotePricingBinding(_StrictDeskQuoteModel):
    """An immutable commercial rate record resolved from an active pricing release."""

    pricing_record_id: str = Field(min_length=1, max_length=100)
    pkb_entry_id: str = Field(min_length=1, max_length=100)
    entry_version: str | None = Field(default=None, max_length=50)
    description: str = Field(min_length=1, max_length=2000)
    unit: str = Field(min_length=1, max_length=100)
    unit_rate_ex_tax: Decimal = Field(ge=0, max_digits=14, decimal_places=4)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    pricing_release_id: str = Field(min_length=1, max_length=100)
    pricing_release_version: str = Field(min_length=1, max_length=50)
    pricing_release_hash: str = Field(pattern=r"^[A-Fa-f0-9]{64}$")
    record_source_hash: str = Field(pattern=r"^[A-Fa-f0-9]{64}$")


def _serial(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=_serial, ensure_ascii=False
    )


def _snapshot_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _manifest_hash(manifest: dict[str, Any]) -> str:
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _normalise_token(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _release_record_snapshots(release: LibraryRelease) -> dict[str, dict[str, Any]]:
    manifest = release.source_manifest
    if not isinstance(manifest, dict) or not release.release_hash:
        raise DeskQuoteError("desk-quote pricing release is not immutable")
    if _manifest_hash(manifest) != release.release_hash:
        raise DeskQuoteError("desk-quote pricing release hash does not match its manifest")
    records = manifest.get("records", [])
    if not isinstance(records, list):
        raise DeskQuoteError("desk-quote pricing release records are invalid")
    snapshots: dict[str, dict[str, Any]] = {}
    for item in records:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            raise DeskQuoteError("desk-quote pricing release record snapshot is invalid")
        record_id = str(item["id"])
        if record_id in snapshots:
            raise DeskQuoteError("desk-quote pricing release has duplicate record identifiers")
        snapshots[record_id] = item
    if not snapshots:
        raise DeskQuoteError("desk-quote pricing release contains no record identifiers")
    return snapshots


def resolve_desk_quote_pricing_bindings(
    db: Session, proposal: DeskQuoteProposal
) -> list[DeskQuotePricingBinding]:
    """Resolve only active, hash-bound pricing records for a desk-quote proposal."""

    release = db.get(LibraryRelease, proposal.pricing_release_id)
    if not release:
        raise DeskQuoteError("desk-quote pricing release is missing")
    if release.library_type != "pricing":
        raise DeskQuoteError("desk-quote pricing release has the wrong library type")
    if release.status != "active":
        raise DeskQuoteError("desk-quote pricing release is not active")
    if release.effective_date and release.effective_date > date.today():
        raise DeskQuoteError("desk-quote pricing release is not yet effective")

    release_records = _release_record_snapshots(release)
    requested_ids = {item.pricing_record_id for item in proposal.allowances}
    if not requested_ids <= set(release_records):
        missing = ", ".join(sorted(requested_ids - set(release_records)))
        raise DeskQuoteError(
            "desk-quote pricing record is not present in the declared pricing release: " + missing
        )

    records = list(
        db.scalars(
            select(PricingLibraryRecord).where(PricingLibraryRecord.id.in_(requested_ids))
        ).all()
    )
    by_id = {record.id: record for record in records}
    if set(by_id) != requested_ids:
        missing = ", ".join(sorted(requested_ids - set(by_id)))
        raise DeskQuoteError("desk-quote pricing record is missing: " + missing)

    bindings: list[DeskQuotePricingBinding] = []
    for record_id in sorted(requested_ids):
        record = by_id[record_id]
        if record.status != "active":
            raise DeskQuoteError("desk-quote pricing record is not active")
        if record.effective_date and record.effective_date > date.today():
            raise DeskQuoteError("desk-quote pricing record is not yet effective")
        if record.expiry_date and record.expiry_date < date.today():
            raise DeskQuoteError("desk-quote pricing record has expired")
        if not record.source_hash or not re.fullmatch(r"[A-Fa-f0-9]{64}", record.source_hash):
            raise DeskQuoteError("desk-quote pricing record has no valid source hash")
        release_record = release_records[record_id]
        release_source_hash = release_record.get("source_hash")
        if not isinstance(release_source_hash, str) or not re.fullmatch(
            r"[A-Fa-f0-9]{64}", release_source_hash
        ):
            raise DeskQuoteError("desk-quote pricing release record source hash is invalid")
        if record.source_hash.lower() != release_source_hash.lower():
            raise DeskQuoteError(
                "desk-quote pricing record source hash does not match declared release"
            )
        try:
            release_rate = Decimal(str(release_record.get("rate_ex_tax")))
        except (InvalidOperation, ValueError) as exc:
            raise DeskQuoteError("desk-quote pricing release record rate is invalid") from exc
        if release_rate != record.rate_ex_tax:
            raise DeskQuoteError("desk-quote pricing record rate does not match declared release")
        if release_record.get("entry_version") != record.entry_version:
            raise DeskQuoteError(
                "desk-quote pricing record entry version does not match declared release"
            )
        if release_record.get("record_version") != record.record_version:
            raise DeskQuoteError(
                "desk-quote pricing record version does not match declared release"
            )
        if record.currency.upper() != proposal.currency:
            raise DeskQuoteError("desk-quote pricing record currency does not match the proposal")
        bindings.append(
            DeskQuotePricingBinding(
                pricing_record_id=record.id,
                pkb_entry_id=record.pkb_entry_id,
                entry_version=record.entry_version,
                description=record.description,
                unit=record.unit,
                unit_rate_ex_tax=record.rate_ex_tax,
                currency=record.currency.upper(),
                pricing_release_id=release.id,
                pricing_release_version=release.version,
                pricing_release_hash=release.release_hash,
                record_source_hash=record.source_hash,
            )
        )
    return bindings


def _source_location_values(source: EvidenceSource) -> frozenset[str]:
    page_number = source.page_number.strip() if isinstance(source.page_number, str) else ''
    region_reference = (
        source.region_reference.strip() if isinstance(source.region_reference, str) else ''
    )
    values: set[str] = set()
    page = ''
    if page_number:
        page = page_number if page_number.casefold().startswith('page ') else f'page {page_number}'
        values.add(page)
    if region_reference:
        values.add(region_reference)
    if page and region_reference:
        values.add(f'{page}, {region_reference}')
    return frozenset(values)


def _project_evidence_failure(
    error: ProjectEvidenceError | StoredFileBindingError,
) -> DeskQuoteError:
    return DeskQuoteError(f'desk-quote project evidence is unavailable: {error.code}')


def _report_locator_keys(
    db: Session,
    evidence_by_source_id: dict[str, ProjectEvidence],
) -> dict[str, frozenset[str]]:
    records = list(
        db.scalars(
            select(ReportEvidenceLocator).where(
                ReportEvidenceLocator.project_evidence_id.in_(
                    [evidence.id for evidence in evidence_by_source_id.values()]
                )
            )
        ).all()
    )
    keys: dict[str, set[str]] = {source_id: set() for source_id in evidence_by_source_id}
    source_id_by_evidence_id = {
        evidence.id: source_id for source_id, evidence in evidence_by_source_id.items()
    }
    for record in records:
        source_id = source_id_by_evidence_id.get(record.project_evidence_id)
        if source_id is not None:
            keys[source_id].add(record.locator_key)
    return {source_id: frozenset(values) for source_id, values in keys.items()}


def resolve_desk_quote_project_evidence(
    db: Session,
    proposal: DeskQuoteProposal,
    *,
    storage_root: Path,
) -> Project:
    """Read and bind every desk-quote locator to one owned retained report."""

    project = db.scalar(select(Project).where(Project.reference == proposal.project_reference))
    if project is None:
        raise DeskQuoteError("desk-quote project is missing")
    estimate = db.scalar(
        select(Estimate).where(
            Estimate.project_id == project.id,
            Estimate.reference == proposal.estimate_reference,
        )
    )
    if estimate is None:
        raise DeskQuoteError("desk-quote estimate is missing or does not belong to the project")

    locators = [
        locator for assumption in proposal.assumptions for locator in assumption.evidence_locators
    ]
    source_ids = {locator.evidence_source_id for locator in locators}
    sources = list(
        db.scalars(select(EvidenceSource).where(EvidenceSource.id.in_(source_ids))).all()
    )
    sources_by_id = {source.id: source for source in sources}
    if set(sources_by_id) != source_ids:
        missing = ", ".join(sorted(source_ids - set(sources_by_id)))
        raise DeskQuoteError("desk-quote evidence source is missing: " + missing)

    stored_file_ids = {source.stored_file_id for source in sources if source.stored_file_id}
    stored_files = list(
        db.scalars(select(StoredFile).where(StoredFile.id.in_(stored_file_ids))).all()
    )
    stored_files_by_id = {stored.id: stored for stored in stored_files}
    evidence_by_source_id: dict[str, ProjectEvidence] = {}

    for source in sources:
        if source.status != "active":
            raise DeskQuoteError("desk-quote evidence source is not active")
        if source.estimate_id != estimate.id:
            raise DeskQuoteError("desk-quote evidence source does not belong to the estimate")
        if not source.stored_file_id:
            raise DeskQuoteError("desk-quote evidence source has no retained file")
        stored = stored_files_by_id.get(source.stored_file_id)
        if stored is None:
            raise DeskQuoteError("desk-quote retained evidence file is missing")
        if not stored.immutable:
            raise DeskQuoteError("desk-quote retained evidence file is not immutable")
        if _normalise_token(stored.purpose) != "project_evidence":
            raise DeskQuoteError("desk-quote retained evidence file has the wrong purpose")
        if _normalise_token(stored.malware_scan_status) != "clean":
            raise DeskQuoteError("desk-quote retained evidence file has an unsafe scan status")
        if not source.sha256 or source.sha256.lower() != stored.sha256.lower():
            raise DeskQuoteError(
                "desk-quote evidence source digest does not match its retained file"
            )
        try:
            evidence_by_source_id[source.id] = require_project_evidence_access(
                db,
                stored_file_id=stored.id,
                project_id=project.id,
                estimate_id=estimate.id,
            )
        except ProjectEvidenceError as error:
            raise _project_evidence_failure(error) from error

    report_locator_keys = _report_locator_keys(db, evidence_by_source_id)
    for locator in locators:
        source = sources_by_id[locator.evidence_source_id]
        stored_file_id = source.stored_file_id
        stored = stored_files_by_id.get(stored_file_id) if stored_file_id else None
        if stored is None:
            raise DeskQuoteError("desk-quote retained evidence file is missing")
        if locator.file_sha256.lower() != stored.sha256.lower():
            raise DeskQuoteError(
                "desk-quote evidence locator digest does not match its retained file"
            )
        if source.source_reference != locator.evidence_reference:
            raise DeskQuoteError(
                "desk-quote evidence locator reference does not match retained evidence"
            )
        if locator.locator not in (
            _source_location_values(source) | report_locator_keys[locator.evidence_source_id]
        ):
            raise DeskQuoteError("desk-quote locator does not match retained evidence")

    for source_id in sorted(sources_by_id):
        source = sources_by_id[source_id]
        stored_file_id = source.stored_file_id
        stored = stored_files_by_id.get(stored_file_id) if stored_file_id else None
        if stored is None:
            raise DeskQuoteError("desk-quote retained evidence file is missing")
        try:
            content = read_project_evidence_for_update(
                db,
                stored_file_id=stored.id,
                project_id=project.id,
                estimate_id=estimate.id,
                storage_root=storage_root,
            )
        except (ProjectEvidenceError, StoredFileBindingError) as error:
            raise _project_evidence_failure(error) from error
        if content.sha256 != stored.sha256.lower() or content.size_bytes != stored.size_bytes:
            raise DeskQuoteError("desk-quote retained evidence bytes do not match their binding")
    return project


def _qualification_messages() -> list[str]:
    return [
        (
            "This is an assumption-led desk quote prepared from the retained report, "
            "drawings and/or images named in the assumption register; no site inspection is "
            "represented."
        ),
        (
            "Every allowance depends on the stated assumptions. Material differences found at "
            "access or before work must be assessed as a scope and price variation before "
            "proceeding."
        ),
        (
            "This proposal is not a technical system selection, installation certification, or "
            "compliance determination. Technical suitability must be verified against the actual "
            "construction and authorised technical evidence before installation."
        ),
    ]


def _normalised_pricing_bindings(
    proposal: DeskQuoteProposal,
    pricing_bindings: Sequence[DeskQuotePricingBinding | dict[str, Any]] | None,
) -> list[DeskQuotePricingBinding]:
    if not pricing_bindings:
        raise DeskQuoteError("desk-quote snapshot requires resolved pricing bindings")
    parsed = [
        item
        if isinstance(item, DeskQuotePricingBinding)
        else DeskQuotePricingBinding.model_validate(item)
        for item in pricing_bindings
    ]
    by_record_id = {item.pricing_record_id: item for item in parsed}
    if len(by_record_id) != len(parsed):
        raise DeskQuoteError(
            "desk-quote pricing bindings must have unique pricing_record_id values"
        )
    expected_ids = {item.pricing_record_id for item in proposal.allowances}
    if set(by_record_id) != expected_ids:
        raise DeskQuoteError("desk-quote pricing bindings must exactly match allowance records")
    for binding in parsed:
        if binding.pricing_release_id != proposal.pricing_release_id:
            raise DeskQuoteError("desk-quote pricing binding release does not match the proposal")
        if binding.currency != proposal.currency:
            raise DeskQuoteError("desk-quote pricing binding currency does not match the proposal")
    return sorted(parsed, key=lambda item: item.pricing_record_id)


def _bound_allowances(
    proposal: DeskQuoteProposal, bindings: list[DeskQuotePricingBinding]
) -> list[dict[str, Any]]:
    by_record_id = {item.pricing_record_id: item for item in bindings}
    allowances: list[dict[str, Any]] = []
    for allowance in proposal.model_dump(mode="json")["allowances"]:
        binding = by_record_id[allowance["pricing_record_id"]]
        allowances.append(
            {
                **allowance,
                "unit": binding.unit,
                "unit_rate_ex_tax": str(binding.unit_rate_ex_tax),
                "rate_binding": binding.model_dump(mode="json"),
            }
        )
    return sorted(allowances, key=lambda item: item["allowance_id"])


def build_desk_quote_snapshot(
    proposal: DeskQuoteProposal | dict[str, Any],
    *,
    pricing_bindings: Sequence[DeskQuotePricingBinding | dict[str, Any]] | None = None,
    generated_utc: datetime | None = None,
) -> dict[str, Any]:
    """Build a deterministic, renderable desk-quote receipt without database access."""

    parsed = (
        proposal
        if isinstance(proposal, DeskQuoteProposal)
        else DeskQuoteProposal.model_validate(proposal)
    )
    bindings = _normalised_pricing_bindings(parsed, pricing_bindings)
    generated = generated_utc or datetime.now(UTC)
    if generated.tzinfo is None or generated.utcoffset() is None:
        raise DeskQuoteError("generated_utc must include a timezone offset")

    quote = parsed.model_dump(mode="json")
    assumptions = sorted(quote["assumptions"], key=lambda item: item["assumption_id"])
    allowances = _bound_allowances(parsed, bindings)
    subtotal = sum(
        (Decimal(item["quantity"]) * Decimal(item["unit_rate_ex_tax"]) for item in allowances),
        Decimal("0"),
    )
    tax_total = subtotal * Decimal(quote["tax_rate"])
    rendered_bindings = [item.model_dump(mode="json") for item in bindings]

    exclusions = list(quote["additional_exclusions"])
    verification_requirements: list[dict[str, str]] = []
    for item in assumptions:
        verification_requirements.append(
            {
                "assumption_id": item["assumption_id"],
                "subject_reference": item["subject_reference"],
                "verification_action": item["verification_action"],
            }
        )
        if item["commercial_treatment"] == "excluded_pending_verification":
            exclusions.append(
                f"{item['assumption_id']} ({item['subject_reference']}): "
                "excluded pending verification - "
                f"{item['verification_action']}"
            )
        elif item["commercial_treatment"] == "variation_risk":
            exclusions.append(
                f"{item['assumption_id']} ({item['subject_reference']}): "
                "pricing variation risk if the assumed condition differs - "
                f"{item['verification_action']}"
            )

    snapshot: dict[str, Any] = {
        "schema": DESK_QUOTE_SNAPSHOT_SCHEMA,
        "document_class": DESK_QUOTE_DOCUMENT_CLASS,
        "technical_position": DESK_QUOTE_TECHNICAL_POSITION,
        "generated_utc": generated.isoformat(),
        "quote": quote,
        "pricing_bindings": rendered_bindings,
        "assumptions": assumptions,
        "allowances": allowances,
        "totals": {
            "subtotal_ex_tax": str(subtotal),
            "tax_total": str(tax_total),
            "total_incl_tax": str(subtotal + tax_total),
        },
        "qualifications": _qualification_messages(),
        "exclusions": exclusions,
        "verification_requirements": verification_requirements,
    }
    snapshot["snapshot_hash"] = _snapshot_hash(snapshot)
    return snapshot


def verify_desk_quote_snapshot(snapshot: dict[str, Any]) -> None:
    """Fail closed before rendering a tampered or misclassified desk quote."""

    if not isinstance(snapshot, dict):
        raise DeskQuoteError("desk-quote snapshot must be an object")
    if snapshot.get("schema") != DESK_QUOTE_SNAPSHOT_SCHEMA:
        raise DeskQuoteError("desk-quote snapshot schema is invalid")
    if snapshot.get("document_class") != DESK_QUOTE_DOCUMENT_CLASS:
        raise DeskQuoteError("desk-quote document class is invalid")
    if snapshot.get("technical_position") != DESK_QUOTE_TECHNICAL_POSITION:
        raise DeskQuoteError("desk-quote technical position is invalid")
    quote = snapshot.get("quote")
    try:
        parsed = DeskQuoteProposal.model_validate(quote)
    except Exception as exc:
        raise DeskQuoteError("desk-quote snapshot payload is invalid") from exc

    try:
        pricing_bindings = _normalised_pricing_bindings(parsed, snapshot.get("pricing_bindings"))
    except Exception as exc:
        raise DeskQuoteError("desk-quote snapshot pricing bindings are invalid") from exc

    assumptions = snapshot.get("assumptions")
    allowances = snapshot.get("allowances")
    if assumptions != sorted(
        parsed.model_dump(mode="json")["assumptions"], key=lambda item: item["assumption_id"]
    ):
        raise DeskQuoteError("desk-quote snapshot assumptions do not match the source payload")
    if allowances != _bound_allowances(parsed, pricing_bindings):
        raise DeskQuoteError("desk-quote snapshot allowances do not match the pricing bindings")

    generated = snapshot.get("generated_utc")
    try:
        parsed_generated = datetime.fromisoformat(str(generated))
    except ValueError as exc:
        raise DeskQuoteError("desk-quote snapshot generated_utc is invalid") from exc
    if parsed_generated.tzinfo is None or parsed_generated.utcoffset() is None:
        raise DeskQuoteError("desk-quote snapshot generated_utc must include a timezone offset")

    expected_snapshot = build_desk_quote_snapshot(
        parsed, pricing_bindings=pricing_bindings, generated_utc=parsed_generated
    )
    expected_payload = dict(expected_snapshot)
    expected_payload.pop("snapshot_hash", None)
    received_payload = dict(snapshot)
    received_payload.pop("snapshot_hash", None)
    if received_payload != expected_payload:
        raise DeskQuoteError("desk-quote snapshot contents do not match the source payload")
    expected = snapshot.get("snapshot_hash")
    if not isinstance(expected, str) or expected != expected_snapshot["snapshot_hash"]:
        raise DeskQuoteError("desk-quote snapshot hash is missing or invalid")


__all__ = [
    "DESK_QUOTE_DOCUMENT_CLASS",
    "DESK_QUOTE_SCHEMA",
    "DESK_QUOTE_SNAPSHOT_SCHEMA",
    "DESK_QUOTE_TECHNICAL_POSITION",
    "DeskQuoteAllowance",
    "DeskQuoteAssumption",
    "DeskQuoteError",
    "DeskQuoteEvidenceLocator",
    "DeskQuoteProposal",
    "DeskQuotePricingBinding",
    "build_desk_quote_snapshot",
    "resolve_desk_quote_pricing_bindings",
    "resolve_desk_quote_project_evidence",
    "verify_desk_quote_snapshot",
]
