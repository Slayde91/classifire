"""Read-only selected Scope context and optional bounded advisory conversation.

No domain writer, downstream capability or conversation persistence is available.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models
from ..config import Settings
from ..models import User
from ..security import has_permission
from .draft_scope import DraftScopeError, _actor, get_draft, read_revision
from .draft_scope_evidence import reference_status

MAX_BODY_BYTES = 32768
MAX_CONTEXT_BYTES = 65536
NOTICE = (
    "AI advice is unverified. Check source evidence; no Scope, system, price or approval was saved."
)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    revision: Annotated[int, Field(ge=1)]
    ids: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=36)]], Field(min_length=1, max_length=50)
    ]
    question: Annotated[str, Field(min_length=1, max_length=4000)]
    previous_questions: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=4000)]], Field(max_length=6)
    ] = Field(default_factory=list)
    consent: bool = False


class Advice(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    answer: Annotated[str, Field(min_length=1, max_length=12000)]
    uncertainty: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=1000)]],
        Field(min_length=1, max_length=15),
    ]
    record_ids: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=36)]], Field(max_length=150)
    ]
    source_ids: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=36)]], Field(max_length=100)
    ]


class ChatPort(Protocol):
    def complete(
        self, context: dict[str, Any], request: ChatRequest | WorkspaceChatRequest
    ) -> dict[str, Any]: ...


def parse(value: Any) -> ChatRequest:
    try:
        parsed = ChatRequest.model_validate(value)
        if not parsed.question.strip() or len(set(parsed.ids)) != len(parsed.ids):
            raise ValueError("invalid input")
        return parsed
    except (ValidationError, ValueError):
        raise DraftScopeError("CHAT_INPUT_INVALID", 422) from None


def selected_context(
    db: Session, actor: User, draft_id: str, request: ChatRequest
) -> dict[str, Any]:
    draft = get_draft(db, actor, draft_id)
    scope = read_revision(db, actor, draft_id, request.revision)
    content = scope["content"]
    collections = ("defects", "openings", "services", "observations")
    by_id = {row["id"]: (kind, row) for kind in collections for row in content[kind]}
    chosen = set(request.ids)
    if not chosen <= by_id.keys():
        raise DraftScopeError("CHAT_SELECTION_INVALID", 422)
    for key in list(chosen):
        kind, row = by_id[key]
        if kind == "services":
            chosen.update(row["opening_ids"])
    for key in list(chosen):
        kind, row = by_id[key]
        if kind == "openings" and row["defect_id"]:
            chosen.add(row["defect_id"])
    if len(chosen) > 150:
        raise DraftScopeError("CHAT_CONTEXT_TOO_LARGE", 422)
    refs = []
    for ref in scope.get("evidence_refs", []):
        target = ref.get("target_id", ref.get("observation_id"))
        if target in chosen:
            source_kind = ref.get("source_kind", "pdf")
            descriptor = {
                "record_id": target,
                "source_id": ref["source_id"],
                "source_kind": source_kind,
                "origin": ref["origin"],
                "source_sha256": ref["source_sha256"],
                "claim_status": reference_status(ref, content),
                "verification": "Source bytes and present access were not checked; claims only.",
            }
            if source_kind == "docx":
                descriptor["locator"] = ref["block"]["locator"]
                descriptor["text_sha256"] = ref["block"]["text_sha256"]
            elif source_kind == "xlsx":
                descriptor["row"] = {
                    key: ref["row"][key] for key in ("sheet", "sheet_index", "row", "sha256")
                }
                descriptor["cell_addresses"] = [
                    cell["address"] for cell in ref["row"]["fields"].values() if cell is not None
                ]
            else:
                descriptor["locator"] = ref["locator_key"]
                descriptor["page_number"] = ref["page_number"]
            descriptor["image_claims"] = [
                {
                    key: image[key]
                    for key in (
                        "id",
                        "occurrence_id",
                        "locator",
                        "anchor",
                        "sha256",
                        "preview_sha256",
                        "width",
                        "height",
                    )
                    if key in image
                }
                for image in ref.get("images", [])
            ]
            refs.append(descriptor)
    if len(refs) > 100:
        raise DraftScopeError("CHAT_CONTEXT_TOO_LARGE", 422)
    context = {
        "draft_id": draft.id,
        "project_id": draft.project_id,
        "revision": scope["revision"],
        "scope_sha256": scope["sha256"],
        "selected_ids": request.ids,
        "records": [{"kind": by_id[key][0], **by_id[key][1]} for key in sorted(chosen)],
        "source_references": refs,
        "limitations": [
            "Saved Draft only; source reference claims are not independently verified.",
            "Source images, full documents, systems, libraries and prices are not sent.",
            "Unlinked records and unknown values remain unresolved; no hierarchy is invented.",
        ],
    }
    if len(json.dumps(context, ensure_ascii=False).encode("utf-8")) > MAX_CONTEXT_BYTES:
        raise DraftScopeError("CHAT_CONTEXT_TOO_LARGE", 422)
    return context


def availability(settings: Settings) -> dict[str, Any]:
    enabled = bool(
        settings.workspace_chat_enabled
        and settings.workspace_chat_model
        and settings.workspace_chat_api_key
    )
    return {
        "enabled": enabled,
        "model": settings.workspace_chat_model if enabled else None,
        "notice": NOTICE,
        "provider": "OpenAI" if enabled else None,
    }


def answer(
    db: Session,
    actor: User,
    draft_id: str,
    request: ChatRequest,
    *,
    settings: Settings,
    port: ChatPort | None = None,
) -> dict[str, Any]:
    context = selected_context(db, actor, draft_id, request)
    if not availability(settings)["enabled"]:
        raise DraftScopeError("CHAT_UNAVAILABLE", 409)
    if not request.consent:
        raise DraftScopeError("CHAT_CONSENT_REQUIRED", 422)
    if port is None:
        from .draft_workspace_chat_transport import OpenAIWorkspaceChatPort

        port = OpenAIWorkspaceChatPort(settings)
    # Recheck current local authority at the provider boundary, including injected ports.
    context = selected_context(db, actor, draft_id, request)
    try:
        value = Advice.model_validate(port.complete(context, request)).model_dump()
        if not set(value["record_ids"]) <= {row["id"] for row in context["records"]} or not set(
            value["source_ids"]
        ) <= {row["source_id"] for row in context["source_references"]}:
            raise ValueError("unbound reference")
    except DraftScopeError:
        raise DraftScopeError("CHAT_PROVIDER_FAILED", 502) from None
    except (ValueError, TypeError, ValidationError):
        raise DraftScopeError("CHAT_RESPONSE_INVALID", 502) from None
    # A revoked user must not receive a pending provider result.
    selected_context(db, actor, draft_id, request)
    return {**value, "notice": NOTICE, "context": context}


# Workspace requests extend the existing advisory port; legacy Scope requests keep
# their original selection and user-question history contract.
MAX_WORKSPACE_BODY_BYTES = 65536
MAX_TURN_BYTES = 24000
Identity = Annotated[str, Field(min_length=36, max_length=36)]
Revision = Annotated[int, Field(ge=1, le=2_147_483_647)]
RecordKind = Literal[
    "technical_variant",
    "technical_document",
    "pricing_record",
    "product",
    "labour",
    "library_release",
    "markup_profile",
]


class ContextScreen(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: Annotated[str, Field(pattern=r"^[a-z][a-z-]{0,39}$")]
    title: Annotated[str, Field(min_length=1, max_length=160)] | None = None


class ContextMatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    match_id: Identity
    match_revision: Revision


class ContextEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    estimate_id: Identity
    estimate_revision: Revision


class ContextRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: RecordKind
    id: Identity


class ConversationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    role: Literal["user", "assistant"]
    content: Annotated[str, Field(min_length=1, max_length=12000)]


class WorkspaceChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    screen: ContextScreen
    project_id: Identity | None = None
    draft_id: Identity | None = None
    revision: Revision | None = None
    ids: Annotated[list[Identity], Field(max_length=50)] = Field(default_factory=list)
    matches: Annotated[list[ContextMatch], Field(max_length=30)] = Field(default_factory=list)
    estimate: ContextEstimate | None = None
    records: Annotated[list[ContextRecord], Field(max_length=20)] = Field(default_factory=list)
    question: Annotated[str, Field(min_length=1, max_length=4000)]
    turns: Annotated[list[ConversationTurn], Field(max_length=6)] = Field(default_factory=list)
    include_sensitive: bool = False
    consent: bool = False
    context_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")] | None = None

    @model_validator(mode="after")
    def bounded_selection(self) -> WorkspaceChatRequest:
        identities = [self.project_id, self.draft_id, *self.ids]
        identities.extend(item.match_id for item in self.matches)
        identities.extend(item.id for item in self.records)
        if self.estimate is not None:
            identities.append(self.estimate.estimate_id)
        if any(value is not None and str(UUID(value)) != value for value in identities):
            raise ValueError("canonical identity required")
        if (self.draft_id is None) != (self.revision is None):
            raise ValueError("exact Scope revision required")
        if not self.draft_id and (self.ids or self.matches or self.estimate):
            raise ValueError("Scope required")
        if (
            len(set(self.ids)) != len(self.ids)
            or len({item.match_id for item in self.matches}) != len(self.matches)
            or len({(item.kind, item.id) for item in self.records}) != len(self.records)
        ):
            raise ValueError("duplicate selection")
        if not self.question.strip() or any(not turn.content.strip() for turn in self.turns):
            raise ValueError("blank conversation")
        if sum(len(turn.content.encode("utf-8")) for turn in self.turns) > MAX_TURN_BYTES:
            raise ValueError("conversation budget")
        self.ids.sort()
        self.matches.sort(key=lambda item: item.match_id)
        self.records.sort(key=lambda item: (item.kind, item.id))
        return self


def parse_workspace(value: Any) -> WorkspaceChatRequest:
    try:
        return WorkspaceChatRequest.model_validate(value)
    except (ValueError, TypeError, ValidationError):
        raise DraftScopeError("CHAT_INPUT_INVALID", 422) from None


def _encoded(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _projection(row: Any, names: tuple[str, ...]) -> dict[str, Any]:
    result = {}
    for name in names:
        value = getattr(row, name)
        result[name] = (
            value.isoformat()
            if isinstance(value, (date, datetime))
            else (str(value) if isinstance(value, Decimal) else value)
        )
    return result


# Existing technical/library detail-view permissions, explicit field allowlists.
# No ORM dump, source_json, source_manifest, metadata_json, file path or attachment.
_LIBRARY_MODELS: dict[str, tuple[Any, str, str]] = {
    "technical_variant": (models.TechnicalVariant, "technical:read", "variant_id"),
    "technical_document": (models.TechnicalDocument, "technical:read", "document_id"),
    "pricing_record": (models.PricingLibraryRecord, "library:read", "pkb_entry_id"),
    "product": (models.Product, "library:read", "name"),
    "labour": (models.LabourComponent, "library:read", "name"),
    "library_release": (models.LibraryRelease, "library:read", "version"),
    "markup_profile": (models.MarkupProfile, "library:read", "name"),
}
_LIBRARY_DETAILS = {
    "technical_variant": (
        "system_id",
        "manufacturer",
        "product_family",
        "service_type",
        "service_material",
        "substrate_type",
        "minimum_substrate_thickness_mm",
        "orientation",
        "opening_type",
        "annular_gap_min_mm",
        "annular_gap_max_mm",
        "frl",
        "jurisdiction",
        "expert_review_required",
        "search_eligibility",
        "effective_date",
        "expiry_date",
        "source_document_reference",
        "source_page",
        "source_hash",
        "release_id",
    ),
    "technical_document": (
        "title",
        "document_type",
        "reference",
        "revision",
        "manufacturer",
        "issuing_organisation",
        "publication_date",
        "review_date",
        "expiry_date",
        "jurisdiction",
        "extraction_status",
    ),
    "pricing_record": (
        "description",
        "system_description",
        "unit",
        "entry_version",
        "rate_ex_tax",
        "direct_labour_cost",
        "direct_material_cost",
        "material_markup",
        "currency",
        "tax_basis",
        "service_type",
        "service_material",
        "substrate",
        "frl",
        "commercial_confidence",
        "technical_status",
        "effective_date",
        "expiry_date",
        "source_hash",
        "release_id",
    ),
    "product": (
        "sku",
        "revision",
        "item_type",
        "category",
        "manufacturer",
        "unit",
        "pack_size",
        "base_cost",
        "currency",
        "tax_treatment",
        "waste_factor",
        "default_markup",
        "effective_date",
        "expiry_date",
        "release_id",
    ),
    "labour": (
        "code",
        "revision",
        "trade_or_grade",
        "category",
        "unit",
        "base_rate",
        "default_hours",
        "crew_size",
        "default_markup",
        "effective_date",
        "expiry_date",
        "release_id",
    ),
    "library_release": ("library_type", "version", "effective_date", "release_hash"),
    "markup_profile": (
        "scope_type",
        "scope_id",
        "product_markup",
        "material_markup",
        "labour_markup",
        "effective_date",
        "expiry_date",
    ),
}


def _library_record(
    db: Session, actor: User, selected: ContextRecord, sensitive: bool
) -> dict[str, Any]:
    model, permission, label = _LIBRARY_MODELS[selected.kind]
    _actor(db, actor, permission)
    row = db.get(model, selected.id, populate_existing=True)
    if row is None:
        raise DraftScopeError("CHAT_RECORD_NOT_FOUND", 404)
    if isinstance(row, models.LibraryRelease) and row.library_type == "technical":
        _actor(db, actor, "technical:read")
    result = {
        "kind": selected.kind,
        "id": row.id,
        "label": getattr(row, label),
        **_projection(row, ("status", "updated_at")),
    }
    if sensitive:
        result["details"] = _projection(row, _LIBRARY_DETAILS[selected.kind])
    else:
        result["details_withheld"] = (
            "Include technical and commercial details in a new preview to share them."
        )
    result["context_record_sha256"] = hashlib.sha256(_encoded(result)).hexdigest()
    return result


def _project_identity(db: Session, actor: User, project_id: str) -> dict[str, Any]:
    _actor(db, actor, "project:read")
    # Match existing project-workspace visibility. Never pick an implicit Draft.
    visible_drafts = select(models.DraftScope.project_id)
    if actor.role != "administrator":
        visible_drafts = visible_drafts.where(models.DraftScope.owner_user_id == actor.id)
    conditions: list[Any] = [
        ~models.Project.id.in_(select(models.DraftScope.project_id)),
        models.Project.id.in_(visible_drafts),
    ]
    if has_permission(actor, "estimate:read"):
        conditions.append(models.Project.estimates.any())
    row = db.scalar(
        select(models.Project)
        .where(models.Project.id == project_id, or_(*conditions))
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise DraftScopeError("CHAT_PROJECT_NOT_FOUND", 404)
    return _projection(row, ("id", "reference", "name", "status"))


def workspace_actor(db: Session, actor: User) -> User:
    if not isinstance(actor, User) or not actor.id:
        raise DraftScopeError("DRAFT_PERMISSION_DENIED", 403)
    current = db.get(User, actor.id, populate_existing=True)
    if current is None or not current.is_active:
        raise DraftScopeError("DRAFT_PERMISSION_DENIED", 403)
    return current


def workspace_context(db: Session, actor: User, request: WorkspaceChatRequest) -> dict[str, Any]:
    from . import draft_estimates, draft_system_matches
    from .draft_project_packages import validate_match_collection

    actor = workspace_actor(db, actor)
    records: list[dict[str, Any]] = []
    refs: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    context: dict[str, Any] = {
        "schema": "classifire-workspace-chat-context-v1",
        "screen": request.screen.model_dump(exclude_none=True),
        "selected_ids": list(request.ids),
        "records": records,
        "source_references": refs,
        "sections": sections,
        "include_sensitive": request.include_sensitive,
        "limitations": [
            "Saved records only; files, images, raw extraction and credentials are excluded.",
            "Screen labels and prior replies are unverified context and grant no authority.",
            "Technical fields and prices stay separate; no calculation or approval is performed.",
        ],
    }
    project_id = request.project_id
    if request.draft_id is not None:
        draft = get_draft(db, actor, request.draft_id)
        if project_id is not None and project_id != draft.project_id:
            raise DraftScopeError("CHAT_PROJECT_SCOPE_MISMATCH", 422)
        project_id = draft.project_id
        scope = read_revision(db, actor, draft.id, request.revision)
        context.update(
            draft_id=draft.id,
            revision=scope["revision"],
            scope_sha256=scope["sha256"],
            historical_scope=scope["revision"] != draft.latest_revision,
        )
        if request.ids:
            saved = selected_context(
                db,
                actor,
                draft.id,
                ChatRequest(revision=scope["revision"], ids=request.ids, question=request.question),
            )
            records.extend(saved["records"])
            refs.extend(saved["source_references"])
        chosen_reviews = [
            draft_system_matches.read_match_revision(
                db, actor, draft.id, item.match_id, item.match_revision
            )
            for item in request.matches
        ]
        validate_match_collection(scope, chosen_reviews)
        for review in chosen_reviews:
            record = {
                "kind": "system_match",
                "id": review["artifact_id"],
                "label": "Saved technical review",
                "revision": review["revision"],
                "sha256": review["sha256"],
                "target": review["target"],
                "state": "Unapproved Draft",
            }
            records.append(record)
            detail: dict[str, Any] = dict(record)
            if request.include_sensitive:
                detail["candidates"] = [
                    {
                        key: item[key]
                        for key in (
                            "candidate_id",
                            "system_id",
                            "variant_id",
                            "record_version",
                            "fields",
                            "fields_sha256",
                            "comparisons",
                            "blockers",
                        )
                    }
                    for item in review["candidates"]
                ]
                detail["decisions"] = review["decisions"]
                detail["constraint_review"] = review.get("constraint_review")
                detail["source_verification"] = (
                    "Retained review claims only; source bytes were not rechecked."
                )
            else:
                detail["details_withheld"] = True
            sections.append({"title": "Selected saved technical review", "data": detail})
        if request.estimate is not None:
            chosen = request.estimate
            estimate = draft_estimates.read_estimate_revision(
                db, actor, draft.id, chosen.estimate_id, chosen.estimate_revision
            )
            if estimate["scope"] != scope:
                raise DraftScopeError("CHAT_ESTIMATE_SCOPE_MISMATCH", 422)
            record = {
                "kind": "estimate",
                "id": estimate["artifact_id"],
                "label": "Saved Draft Estimate",
                "revision": estimate["revision"],
                "sha256": estimate["sha256"],
            }
            records.append(record)
            detail = dict(record)
            embedded = estimate["system_match"]
            detail["estimate_review"] = (
                {key: embedded[key] for key in ("artifact_id", "revision", "sha256")}
                if embedded
                else None
            )
            if request.include_sensitive:
                detail.update(
                    currency=estimate["currency"],
                    tax_treatment=estimate["tax_treatment"],
                    summary=estimate["summary"],
                    lines=[
                        {
                            key: line[key]
                            for key in (
                                "line_id",
                                "target_kind",
                                "target_id",
                                "label",
                                "opening_ids",
                                "unit",
                                "work_basis",
                                "description",
                                "quantity",
                                "unit_sell_rate",
                                "status",
                                "subtotal_ex_tax",
                                "pricing_status",
                                "omission_reason",
                            )
                        }
                        for line in estimate["lines"]
                    ],
                )
            else:
                detail["details_withheld"] = True
            sections.append({"title": "Selected saved Estimate; no recalculation", "data": detail})
    if project_id is not None:
        context["project_id"] = project_id
        sections.insert(0, {"title": "Project", "data": _project_identity(db, actor, project_id)})
    for selected in request.records:
        record = _library_record(db, actor, selected, request.include_sensitive)
        records.append(record)
        sections.append({"title": "Selected library record", "data": record})
    if len(records) > 201:
        raise DraftScopeError("CHAT_CONTEXT_TOO_LARGE", 422)
    context["summary"] = (
        f"{len(request.ids)} selected Scope records; {len(request.matches)} saved reviews; "
        f"{1 if request.estimate else 0} saved Estimate; {len(request.records)} library records."
    )
    if not records:
        context["limitations"].append(
            "No records are selected. Only the displayed screen/project identity is included."
        )
    raw = _encoded(context)
    if len(raw) > MAX_CONTEXT_BYTES:
        raise DraftScopeError("CHAT_CONTEXT_TOO_LARGE", 422)
    context["context_sha256"] = hashlib.sha256(raw).hexdigest()
    return context


def workspace_answer(
    db: Session,
    actor: User,
    request: WorkspaceChatRequest,
    *,
    settings: Settings,
    port: ChatPort | None = None,
) -> dict[str, Any]:
    context = workspace_context(db, actor, request)
    if not availability(settings)["enabled"]:
        raise DraftScopeError("CHAT_UNAVAILABLE", 409)
    if not request.consent:
        raise DraftScopeError("CHAT_CONSENT_REQUIRED", 422)
    if request.context_sha256 is None:
        raise DraftScopeError("CHAT_PREVIEW_REQUIRED", 422)
    if request.context_sha256 != context["context_sha256"]:
        raise DraftScopeError("CHAT_CONTEXT_CHANGED", 409)
    if port is None:
        from .draft_workspace_chat_transport import OpenAIWorkspaceChatPort

        port = OpenAIWorkspaceChatPort(settings)
    if workspace_context(db, actor, request) != context:
        raise DraftScopeError("CHAT_CONTEXT_CHANGED", 409)
    try:
        value = Advice.model_validate(port.complete(context, request)).model_dump()
        if not set(value["record_ids"]) <= {row["id"] for row in context["records"]} or not set(
            value["source_ids"]
        ) <= {row["source_id"] for row in context["source_references"]}:
            raise ValueError("unbound reference")
    except DraftScopeError:
        raise DraftScopeError("CHAT_PROVIDER_FAILED", 502) from None
    except (ValueError, TypeError, ValidationError):
        raise DraftScopeError("CHAT_RESPONSE_INVALID", 502) from None
    if workspace_context(db, actor, request) != context:
        raise DraftScopeError("CHAT_CONTEXT_CHANGED", 409)
    return {**value, "notice": NOTICE, "context": context}


def workspace_descriptor(path: str, values: dict[str, Any]) -> dict[str, Any]:
    """Identifiers from already-authorized template values, never page text or data dumps."""
    family = path.strip("/").split("/", 1)[0] or "workspace"
    if not family.replace("-", "").isalpha() or len(family) > 40:
        family = "workspace"
    result: dict[str, Any] = {
        "screen": {"name": family},
        "ids": [],
        "matches": [],
        "estimate": None,
        "records": [],
    }
    project = values.get("project")
    if isinstance(project, models.Project):
        result["project_id"] = project.id
    draft = values.get("draft")
    if isinstance(draft, models.DraftScope):
        result["project_id"] = draft.project_id
        scope = values.get("scope")
        envelope = values.get("envelope")
        if isinstance(envelope, dict) and isinstance(envelope.get("scope"), dict):
            scope = envelope["scope"]
        revision = scope.get("revision") if isinstance(scope, dict) else None
        if revision is None:
            revision = values.get("scope_revision", values.get("expected_revision"))
        if type(revision) is int and revision >= 1:
            result.update(draft_id=draft.id, revision=revision)
            register = values.get("register")
            if isinstance(register, dict):
                for value in register.get("match_selections", []):
                    identity, number = value.rsplit(":", 1)
                    result["matches"].append({"match_id": identity, "match_revision": int(number)})
                selected_estimate = register.get("estimate_selection")
                if selected_estimate:
                    identity, number = selected_estimate.rsplit(":", 1)
                    result["estimate"] = {"estimate_id": identity, "estimate_revision": int(number)}
            if isinstance(envelope, dict):
                schema = envelope.get("schema_version", "")
                if schema.startswith("CLASSIFIRE-DRAFT-SYSTEM-MATCH-"):
                    result["matches"] = [
                        {
                            "match_id": envelope["artifact_id"],
                            "match_revision": envelope["revision"],
                        }
                    ]
                    result["ids"] = [
                        key
                        for key in (
                            envelope["target"].get("opening_id"),
                            envelope["target"].get("service_id"),
                        )
                        if key
                    ]
                elif schema.startswith("CLASSIFIRE-DRAFT-ESTIMATE-"):
                    result["estimate"] = {
                        "estimate_id": envelope["artifact_id"],
                        "estimate_revision": envelope["revision"],
                    }
    for key in ("record", "product", "item", "variant", "document", "release", "profile"):
        row = values.get(key)
        for kind, (model, _permission, _label) in _LIBRARY_MODELS.items():
            if isinstance(row, model):
                selected = {"kind": kind, "id": row.id}
                if selected not in result["records"]:
                    result["records"].append(selected)
    return result
