"""Selected Scope replacements for human validation/save; no writes or new claims."""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..models import User
from .draft_scope import (
    DraftScopeError,
    DraftScopePayload,
    _revision_envelope,
    read_revision,
    validate_payload,
)
from .draft_scope_evidence import SUGGESTION_TARGET_COLLECTIONS, reference_changed
from .draft_workspace_chat import Advice, WorkspaceChatRequest, scope_response_schema


class EditReason(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    target_kind: Literal["defect", "opening", "service", "observation"]
    target_id: Annotated[str, Field(min_length=36, max_length=36)]
    rationale: Annotated[str, Field(min_length=1, max_length=1000)]


class ScopeEdits(Advice):
    replacements: DraftScopePayload
    reasons: Annotated[list[EditReason], Field(max_length=25)]


def response_schema() -> dict[str, Any]:
    return scope_response_schema(ScopeEdits, observations=True)


def validate_edits(value: Any, context: dict[str, Any]) -> ScopeEdits:
    model = ScopeEdits.model_validate(value)
    graph = model.replacements.model_dump(mode="json")
    if set(value["replacements"]) != set(DraftScopePayload.model_fields):
        raise ValueError("explicit fields required")
    selected = set(context["selected_ids"])
    current = {
        (row["kind"], row["id"]): {key: item for key, item in row.items() if key != "kind"}
        for row in context["records"]
        if row["kind"] in SUGGESTION_TARGET_COLLECTIONS.values()
    }
    touched = set()
    for collection in SUGGESTION_TARGET_COLLECTIONS.values():
        for raw, row in zip(value["replacements"][collection], graph[collection], strict=True):
            identity = row["id"]
            if (
                set(raw) != set(row)
                or identity not in selected
                or identity in touched
                or (collection, identity) not in current
            ):
                raise ValueError("unselected, duplicate or incomplete replacement")
            if row.get("state") == "Confirmed" or row == current[collection, identity]:
                raise ValueError("confirmed or unchanged replacement")
            if row.get("defect_id") is not None and ("defects", row["defect_id"]) not in current:
                raise ValueError("undisclosed defect link")
            if any(("openings", key) not in current for key in row.get("opening_ids", [])):
                raise ValueError("undisclosed opening link")
            touched.add(identity)
    if len(touched) > 25 or graph["assumptions"] or graph["exclusions"]:
        raise ValueError("unselected global edits or edit budget")
    reasons = set()
    for reason in model.reasons:
        collection = SUGGESTION_TARGET_COLLECTIONS[reason.target_kind]
        if (
            reason.target_id not in touched
            or reason.target_id in reasons
            or not any(row["id"] == reason.target_id for row in graph[collection])
        ):
            raise ValueError("unbound or duplicate reason")
        reasons.add(reason.target_id)
    if touched != reasons:
        raise ValueError("each edit needs a reason")
    return model


def prepare_edits(
    db: Session,
    actor: User,
    request: WorkspaceChatRequest,
    model: ScopeEdits,
) -> dict[str, Any] | None:
    if request.draft_id is None:
        raise DraftScopeError("CHAT_INPUT_INVALID")
    current = read_revision(db, actor, request.draft_id)
    if current["revision"] != request.revision:
        raise DraftScopeError("CHAT_CONTEXT_CHANGED", 409)
    graph = model.replacements.model_dump(mode="json")
    payload = copy.deepcopy(current["content"])
    reasons = {item.target_id: item.rationale for item in model.reasons}
    changes = []
    for kind, collection in SUGGESTION_TARGET_COLLECTIONS.items():
        proposed = {row["id"]: row for row in graph[collection]}
        for index, before in enumerate(payload[collection]):
            after = proposed.get(before["id"])
            if after is None:
                continue
            fields = [
                {"field": key, "before": before[key], "after": after[key]}
                for key in before
                if before[key] != after[key]
            ]
            changes.append(
                {
                    "kind": kind,
                    "id": before["id"],
                    "label": before.get("label", before.get("text")),
                    "fields": fields,
                    "rationale": reasons[before["id"]],
                }
            )
            payload[collection][index] = after
    if not changes:
        return None
    try:
        normalized, findings = validate_payload(payload)
        payload = normalized.model_dump(mode="json")
        _revision_envelope(
            draft_id=request.draft_id,
            project_id=current["project_id"],
            actor_id=actor.id,
            expected_revision=current["revision"],
            created=datetime.max.replace(tzinfo=UTC),
            content=payload,
            prior=current,
        )
    except DraftScopeError:
        raise DraftScopeError("CHAT_EDIT_CONFLICT", 422) from None
    query = [("match", f"{item.match_id}:{item.match_revision}") for item in request.matches]
    if request.estimate is not None:
        query.append(
            ("estimate", f"{request.estimate.estimate_id}:{request.estimate.estimate_revision}")
        )
    return {
        "expected_revision": current["revision"],
        "payload": payload,
        "changes": changes,
        "findings": findings,
        "changed_source_claims": sum(
            reference_changed(ref, payload) and not reference_changed(ref, current["content"])
            for ref in current.get("evidence_refs", [])
        ),
        "review_url": f"/scopes/{request.draft_id}" + ("?" + urlencode(query) if query else ""),
        "notice": "Unverified edits. Validate in the Draft editor, then save separately. "
        "Existing source claims are preserved and may need a new evidence review.",
    }
