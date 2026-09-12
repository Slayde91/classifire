"""Read-only selected Scope context and optional bounded advisory conversation.

No domain writer, downstream capability or conversation persistence is available.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import User
from .draft_scope import DraftScopeError, get_draft, read_revision
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
    def complete(self, context: dict[str, Any], request: ChatRequest) -> dict[str, Any]: ...


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
