"""Typed client commands over existing independent Draft use cases.

Preparation reads and binds selected inputs. Only the separate human confirmation
calls execute; preparation never invokes a writer, renderer, or inference provider.
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator
from sqlalchemy.orm import Session

from ..config import get_settings
from ..draft_client_auth import ESTIMATE, TECHNICAL, ClientAuthority, ClientIdentity
from ..models import User
from . import draft_constraint_review as constraints
from . import draft_estimate_reports as estimate_reports
from . import draft_estimates as estimates
from . import draft_pricing_intake as pricing
from . import draft_scope as scopes
from . import draft_scope_reports as scope_reports
from . import draft_system_matches as matches
from .draft_estimate_contract import AddLine, Override
from .draft_source_intake import SourceRow
from .draft_system_match_contract import MAX_CANDIDATES, Decision, target_for

Identity = Annotated[str, Field(min_length=1, max_length=36)]
Revision = Annotated[int, Field(ge=1)]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Command(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    draft_id: Identity


class CreateMatch(Command):
    action: Literal["create_match"]
    scope_revision: Revision
    release_id: Identity
    opening_id: Identity | None = None
    service_id: Identity | None = None


class ReviewMatch(Command):
    action: Literal["review_match"]
    match_id: Identity
    expected_revision: Revision
    decisions: Annotated[list[Decision], Field(max_length=MAX_CANDIDATES)]


class ConstraintInputs(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    substrate_thickness_mm: str | None
    annular_gap_min_mm: str | None
    annular_gap_max_mm: str | None
    measurement_note: str

    @model_validator(mode="after")
    def validate_measurements(self) -> Self:
        # Use the same numeric, range and source-meaning rules as the UI.
        constraints.validate_inputs(
            self.model_dump(), service_size=isinstance(self, ServiceSizeInputs)
        )
        return self


class ServiceSizeInputs(ConstraintInputs):
    service_size_min_mm: str | None
    service_size_max_mm: str | None
    service_size_basis: str = Field(
        description="Meaning of measured sizes. One of: " + ", ".join(constraints.SIZE_BASES)
    )
    source_size_basis: str = Field(
        description="Unapproved interpretation of source limits. One of: "
        + ", ".join(constraints.SIZE_BASES)
    )


class ReviewMeasurements(Command):
    match_id: Identity
    expected_revision: Revision
    candidate_id: Identity


class ReviewMatchConstraints(ReviewMeasurements):
    action: Literal["review_match_constraints"]
    inputs: ConstraintInputs


class ReviewMatchServiceSize(ReviewMeasurements):
    action: Literal["review_match_service_size"]
    inputs: ServiceSizeInputs


class CreateEstimate(Command):
    action: Literal["create_estimate"]
    scope_revision: Revision
    currency: Literal["AUD"] = "AUD"
    match_id: Identity | None = None
    match_revision: Revision | None = None


class EditEstimate(Command):
    estimate_id: Identity
    expected_revision: Revision


class AddEstimateLine(EditEstimate):
    action: Literal["add_estimate_line"]
    line: AddLine


class OverrideEstimateLine(EditEstimate):
    action: Literal["override_estimate_line"]
    line_id: Identity
    override: Override


class SetEstimateLineStatus(EditEstimate):
    action: Literal["set_estimate_line_status"]
    line_id: Identity
    status: Literal["active", "omitted"]
    reason: Annotated[str, Field(min_length=1, max_length=4000)]


class PricingMapping(BaseModel):
    """Column shape only; shared preview validates actual columns and uniqueness."""

    model_config = ConfigDict(strict=True, extra="forbid")
    reference: Revision
    description: Revision
    unit: Revision
    rate: Revision
    currency: Revision
    tax_basis: Revision
    rate_date: Revision | None = None
    labour: Revision | None = None
    materials: Revision | None = None
    inclusions: Revision | None = None
    exclusions: Revision | None = None


class ApplyWorkbookRate(EditEstimate):
    action: Literal["apply_workbook_rate"]
    line_id: Identity
    source_id: Identity
    sheet_index: Revision
    header_row: Revision
    mapping: PricingMapping
    row_number: Revision
    expected_document_hash: Sha256
    expected_row_hash: Sha256
    recovery_note: Annotated[str, Field(min_length=1, max_length=4000)]


class ScopeReport(Command):
    action: Literal["scope_report"]
    scope_revision: Revision
    match_id: Identity | None = None
    match_revision: Revision | None = None


class EstimateReport(Command):
    action: Literal["estimate_report"]
    estimate_id: Identity
    estimate_revision: Revision
    profile: Literal["estimate-only", "complete"]


CapabilityCommand = Annotated[
    CreateMatch
    | ReviewMatch
    | ReviewMatchConstraints
    | ReviewMatchServiceSize
    | CreateEstimate
    | AddEstimateLine
    | OverrideEstimateLine
    | SetEstimateLineStatus
    | ApplyWorkbookRate
    | ScopeReport
    | EstimateReport,
    Field(discriminator="action"),
]


def parse(value: dict[str, Any]) -> CapabilityCommand:
    try:
        return TypeAdapter(CapabilityCommand).validate_python(value, strict=True)
    except ValidationError:
        raise scopes.DraftScopeError("CLIENT_CAPABILITY_INPUT_INVALID", 422) from None


def require(db: Session, authority: ClientAuthority, identity: ClientIdentity, scope: str) -> User:
    actor = authority.actor(db, identity, scope)
    scopes._actor(db, actor, "technical:read" if scope == TECHNICAL else "estimate:read")
    return actor


def protect_content(
    db: Session, authority: ClientAuthority, identity: ClientIdentity, value: dict[str, Any]
) -> None:
    """Nested saved technical/commercial content requires its own client grant."""
    if "estimate" in value or "lines" in value:
        require(db, authority, identity, ESTIMATE)
    if value.get("system_match") is not None or "candidates" in value:
        require(db, authority, identity, TECHNICAL)
    if isinstance(value.get("estimate"), dict):
        protect_content(db, authority, identity, value["estimate"])


def pricing_source_binding(source: SourceRow) -> dict[str, Any]:
    """Call only after the shared source reader has verified current retained bytes."""
    if source.scan_json is None or source.document_sha256 is None:
        raise scopes.DraftScopeError("PRICING_XLSX_SOURCE_NOT_READY", 409)
    return {
        "source_id": source.id,
        "source_sha256": source.source_sha256,
        "document_sha256": source.document_sha256,
        "scan_sha256": hashlib.sha256(source.scan_json.encode("utf-8")).hexdigest(),
        "filename": source.original_filename,
        "size_bytes": source.source_size_bytes,
    }


def inspect_inputs(
    db: Session,
    authority: ClientAuthority,
    identity: ClientIdentity,
    actor: User,
    command: CapabilityCommand,
) -> dict[str, Any]:
    """Read selected immutable inputs and current rights; no proposed domain writes."""
    c = command
    scope = None
    match = None
    estimate = None
    release = None
    if isinstance(c, (CreateMatch, ReviewMatch, ReviewMeasurements)):
        require(db, authority, identity, TECHNICAL)
        matches._access(db, actor, c.draft_id, write=True)
    if isinstance(c, (CreateEstimate, EditEstimate, EstimateReport)):
        require(db, authority, identity, ESTIMATE)
        estimates._access(db, actor, c.draft_id, write=True)
    if isinstance(c, (CreateMatch, CreateEstimate, ScopeReport)):
        scope = scopes.read_revision(db, actor, c.draft_id, c.scope_revision)
    if isinstance(c, CreateMatch):
        if scope is None:
            raise scopes.DraftScopeError("CLIENT_CAPABILITY_INPUT_INVALID", 422)
        try:
            target_for(scope, c.opening_id, c.service_id)
        except (ValueError, KeyError, TypeError):
            raise scopes.DraftScopeError("MATCH_TARGET_INVALID", 422) from None
        selected = matches._release(db, c.release_id)[0]
        release = {"id": selected.id, "version": selected.version, "sha256": selected.release_hash}
    if isinstance(c, (CreateEstimate, ScopeReport)):
        if (c.match_id is None) != (c.match_revision is None):
            raise scopes.DraftScopeError("CLIENT_MATCH_REVISION_REQUIRED", 422)
        if c.match_id is not None:
            require(db, authority, identity, TECHNICAL)
            match = matches.read_match_revision(db, actor, c.draft_id, c.match_id, c.match_revision)
            if match["scope"] != scope:
                raise scopes.DraftScopeError("CLIENT_MATCH_SCOPE_MISMATCH", 422)
    if isinstance(c, (ReviewMatch, ReviewMeasurements)):
        match = matches.read_match_revision(db, actor, c.draft_id, c.match_id)
        if match["revision"] != c.expected_revision:
            raise scopes.DraftScopeError("MATCH_REVISION_CONFLICT", 409)
    if isinstance(c, (EditEstimate, EstimateReport)):
        estimate = estimates.read_estimate_revision(
            db,
            actor,
            c.draft_id,
            c.estimate_id,
            c.estimate_revision if isinstance(c, EstimateReport) else None,
        )
        protect_content(db, authority, identity, estimate)
        if isinstance(c, EditEstimate) and estimate["revision"] != c.expected_revision:
            raise scopes.DraftScopeError("ESTIMATE_REVISION_CONFLICT", 409)
    project = scope_reports._project(db, scopes.get_draft(db, actor, c.draft_id))
    inputs = {
        "scope": scope,
        "match": match,
        "estimate": estimate,
        "release": release,
        "project": project,
    }
    if isinstance(c, ApplyWorkbookRate):
        scopes._actor(db, actor, "library:read")
        if estimate is None:
            raise scopes.DraftScopeError("CLIENT_CAPABILITY_INPUT_INVALID", 422)
        target = estimates._line(estimate, c.line_id)
        source, rows = pricing.preview(
            db,
            actor,
            c.draft_id,
            c.source_id,
            c.sheet_index,
            c.header_row,
            c.mapping.model_dump(),
            settings=get_settings(),
        )
        if source.document_sha256 != c.expected_document_hash:
            raise scopes.DraftScopeError("PRICING_SOURCE_CHANGED", 409)
        priced_row = next((row for row in rows if row["row"] == c.row_number), None)
        if priced_row is None or priced_row["sha256"] != c.expected_row_hash:
            raise scopes.DraftScopeError("PRICING_ROW_CHANGED", 409)
        # Keep the old five-key hash shape for every pre-existing command so
        # already-retained pending requests remain valid across this upgrade.
        inputs["pricing"] = {
            "source": pricing_source_binding(source),
            "row": priced_row,
            "target_line": target,
        }
    raw = json.dumps(inputs, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {"inputs": inputs, "input_hash": hashlib.sha256(raw.encode()).hexdigest()}


def execute(db: Session, actor: User, command: CapabilityCommand) -> dict[str, Any]:
    c = command
    result: dict[str, Any] = {"draft_id": c.draft_id}
    if isinstance(c, CreateMatch):
        row = matches.create_match(
            db,
            actor,
            c.draft_id,
            c.scope_revision,
            c.release_id,
            c.opening_id,
            c.service_id,
            storage_root=get_settings().storage_root,
        )
        result.update(match_id=row.id, revision=row.latest_revision)
    elif isinstance(c, ReviewMatch):
        saved = matches.save_review(
            db,
            actor,
            c.draft_id,
            c.match_id,
            c.expected_revision,
            [d.model_dump() for d in c.decisions],
        )
        result.update(match_id=c.match_id, revision=saved["revision"], sha256=saved["sha256"])
    elif isinstance(c, (ReviewMatchConstraints, ReviewMatchServiceSize)):
        saved = matches.save_constraint_review(
            db,
            actor,
            c.draft_id,
            c.match_id,
            c.expected_revision,
            c.candidate_id,
            c.inputs.model_dump(),
            storage_root=get_settings().storage_root,
            service_size=isinstance(c, ReviewMatchServiceSize),
        )
        result.update(match_id=c.match_id, revision=saved["revision"], sha256=saved["sha256"])
    elif isinstance(c, CreateEstimate):
        estimate = estimates.create_estimate(
            db,
            actor,
            c.draft_id,
            c.scope_revision,
            currency=c.currency,
            match_id=c.match_id,
            match_revision=c.match_revision,
        )
        result.update(estimate_id=estimate.id, revision=estimate.latest_revision)
    elif isinstance(c, EditEstimate):
        args = (db, actor, c.draft_id, c.estimate_id, c.expected_revision)
        if isinstance(c, AddEstimateLine):
            saved = estimates.add_line(*args, c.line.model_dump())
        elif isinstance(c, OverrideEstimateLine):
            saved = estimates.override_line(*args, c.line_id, c.override.model_dump())
        elif isinstance(c, SetEstimateLineStatus):
            saved = estimates.set_line_status(*args, c.line_id, c.status, c.reason)
        elif isinstance(c, ApplyWorkbookRate):
            saved = pricing.apply_rate(
                *args,
                c.line_id,
                c.source_id,
                c.sheet_index,
                c.header_row,
                c.mapping.model_dump(),
                c.row_number,
                c.expected_document_hash,
                c.expected_row_hash,
                c.recovery_note,
                settings=get_settings(),
            )
        else:
            raise scopes.DraftScopeError("CLIENT_CAPABILITY_INPUT_INVALID", 422)
        result.update(estimate_id=c.estimate_id, revision=saved["revision"], sha256=saved["sha256"])
    elif isinstance(c, ScopeReport):
        report = scope_reports.create_report(
            db,
            actor,
            c.draft_id,
            c.scope_revision,
            match_id=c.match_id,
            match_revision=c.match_revision,
        )
        result.update(report_id=report.id, sha256=report.snapshot_hash)
    elif isinstance(c, EstimateReport):
        estimate_report = estimate_reports.create_report(
            db, actor, c.draft_id, c.estimate_id, c.estimate_revision, profile=c.profile
        )
        result.update(
            estimate_id=c.estimate_id,
            report_id=estimate_report.id,
            sha256=estimate_report.snapshot_hash,
        )
    return result


def protect_package(
    db: Session,
    authority: ClientAuthority,
    identity: ClientIdentity,
    actor: User,
    draft_id: str,
    manifest: dict[str, Any],
) -> None:
    """Packages cannot bypass grants on included capabilities or retained ancestors."""
    from . import draft_project_packages as packages

    selected = packages.selection(manifest["selection"])
    if selected.match_id:
        require(db, authority, identity, TECHNICAL)
    if selected.estimate_id:
        require(db, authority, identity, ESTIMATE)
        protect_content(
            db,
            authority,
            identity,
            estimates.read_estimate_revision(
                db, actor, draft_id, selected.estimate_id, selected.estimate_revision
            ),
        )
    for report_id in selected.scope_reports:
        protect_content(
            db, authority, identity, scope_reports.read_report(db, actor, draft_id, report_id)
        )
    # Whole foreign archives can contain both kinds of sensitive content. No
    # weaker grant may disclose them merely because only Scope was selected.
    if manifest["schema_version"] == packages.SCHEMA_V2:
        require(db, authority, identity, TECHNICAL)
        require(db, authority, identity, ESTIMATE)
