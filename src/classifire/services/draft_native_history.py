"""Selected portable native history: read-only claims, never review authorization."""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import DraftWorkspaceProposalDecision, User
from . import draft_scope as scopes
from . import draft_scope_reports as reports
from . import draft_workspace_chat as chat
from . import draft_workspace_proposals as proposals

SCHEMA = "CLASSIFIRE-NATIVE-PROPOSAL-HISTORY-v1"
MAX_SELECTED = 10
MAX_BYTES = proposals.MAX_BYTES + 32768


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    proposal_id: str
    # Required explicit null pins no selected decision; it never means latest.
    decision_id: str | None

    @field_validator("proposal_id", "decision_id")
    @classmethod
    def identity(cls, value: str | None) -> str | None:
        if value is not None and str(UUID(value)) != value:
            raise ValueError("identity")
        return value

    def query_value(self) -> str:
        return self.proposal_id + ":" + (self.decision_id or "none")


def member_path(identity: str) -> str:
    if str(UUID(identity)) != identity:
        raise ValueError("identity")
    return f"artifacts/native-proposal-{identity}.json"


def permissions(value: dict[str, Any], *, export: bool = False) -> set[str]:
    request = chat.parse_workspace(value["proposal"]["request"])
    needed = {"project:read"}
    if request.matches:
        needed.add("technical:read")
    for record in request.records:
        needed.add("technical:read" if record.kind.startswith("technical_") else "library:read")
    if request.estimate is not None:
        needed.add("estimate:read")
        if export:
            needed.add("estimate:export")
    return needed


def _hash_value(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def validate(content: bytes, reference: Reference, scope: dict[str, Any]) -> dict[str, Any]:
    """Check bounded historical structure/bindings, not authenticity or local authority."""
    try:
        if not 1 <= len(content) <= MAX_BYTES:
            raise ValueError("size")
        value: dict[str, Any] = json.loads(
            content,
            object_pairs_hook=scopes._unique_json_object,
            parse_constant=scopes._reject_json_constant,
        )
        if (
            not isinstance(value, dict)
            or set(value)
            != {"schema", "authority", "proposal", "proposal_sha256", "decision", "decision_sha256"}
            or scopes._json(value) != content
        ):
            raise ValueError("encoding")
        original, raw = proposals._document(value["proposal"])
        request = chat.parse_workspace(original["request"])
        if (
            value["schema"] != SCHEMA
            or value["authority"] != "historical_only"
            or value["proposal_sha256"] != proposals._hash(raw)
            or original["id"] != reference.proposal_id
            or original["draft_id"] != scope["artifact_id"]
            or type(original["base_revision"]) is not int
            or not 1 <= original["base_revision"] <= scope["revision"]
            or original["context"].get("draft_id") != original["draft_id"]
            or original["context"].get("revision") != original["base_revision"]
            or original["context"].get("project_id") != scope["project_id"]
            or original["provider"] not in {"openai", "injected"}
            or not isinstance(original["model"], str)
            or not 1 <= len(original["model"]) <= 200
        ):
            raise ValueError("proposal binding")
        reports._utc_text(original["generated_at"])
        if (
            original["base_revision"] == scope["revision"]
            and original["context"].get("scope_sha256") != scope["sha256"]
        ):
            raise ValueError("base Scope")
        prepared = original["response"][
            "edit_proposal" if request.action == "propose_scope_edits" else "proposal"
        ]
        scopes.validate_payload(prepared["payload"])
        if prepared["expected_revision"] != original["base_revision"]:
            raise ValueError("review revision")
        if request.action != "propose_scope_edits":
            source = getattr(request, request.action.split("_")[1])
            if (
                source is None
                or prepared["source_id"] != source.source_id
                or prepared["document_sha256"] != source.document_sha256
            ):
                raise ValueError("source selection")
        decision = value["decision"]
        if reference.decision_id is None:
            if decision is not None or value["decision_sha256"] is not None:
                raise ValueError("unselected decision")
            return value
        expected = {
            "schema",
            "id",
            "proposal_id",
            "proposal_sha256",
            "actor_id",
            "draft_id",
            "outcome",
            "decided_at",
            "base_revision",
            "scope_revision",
            "scope_sha256",
            "reviewed_payload_sha256",
            "proposal_payload_changed",
        }
        if (
            not isinstance(decision, dict)
            or set(decision) != expected
            or decision["schema"] != proposals.DECISION_SCHEMA
            or decision["id"] != reference.decision_id
            or decision["proposal_id"] != original["id"]
            or decision["proposal_sha256"] != value["proposal_sha256"]
            or decision["actor_id"] != original["actor_id"]
            or decision["draft_id"] != original["draft_id"]
            or type(decision["base_revision"]) is not int
            or decision["base_revision"] != original["base_revision"]
            or value["decision_sha256"] != proposals._hash(proposals._raw(decision))
        ):
            raise ValueError("decision binding")
        reports._utc_text(decision["decided_at"])
        if decision["outcome"] == "confirmed":
            if (
                type(decision["scope_revision"]) is not int
                or decision["scope_revision"] != original["base_revision"] + 1
                or decision["scope_revision"] > scope["revision"]
                or not _hash_value(decision["scope_sha256"])
                or not _hash_value(decision["reviewed_payload_sha256"])
                or type(decision["proposal_payload_changed"]) is not bool
                or decision["proposal_payload_changed"]
                != (
                    decision["reviewed_payload_sha256"]
                    != proposals._hash(proposals._raw(prepared["payload"]))
                )
            ):
                raise ValueError("confirmed decision")
            if decision["scope_revision"] == scope["revision"] and decision[
                "scope_sha256"
            ] != proposals._hash(scopes._json(scope).decode("utf-8")):
                raise ValueError("reviewed Scope")
        elif decision["outcome"] != "rejected" or any(
            decision[key] is not None
            for key in (
                "scope_revision",
                "scope_sha256",
                "reviewed_payload_sha256",
                "proposal_payload_changed",
            )
        ):
            raise ValueError("rejected decision")
        return value
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        RecursionError,
        scopes.DraftScopeError,
    ) as exc:
        raise scopes.DraftScopeError("PACKAGE_NATIVE_HISTORY_INVALID", 422) from exc


def compose(
    db: Session, actor: User, draft_id: str, reference: Reference, scope: dict[str, Any]
) -> bytes:
    _draft, row, document = proposals.read_generation(
        db, actor, draft_id, reference.proposal_id, settings=get_settings()
    )
    decision = (
        proposals.read_decision(db, actor, draft_id, row)
        if reference.decision_id is not None
        else None
    )
    if reference.decision_id is not None and (
        decision is None or decision["id"] != reference.decision_id
    ):
        raise scopes.DraftScopeError("PACKAGE_NATIVE_HISTORY_CHANGED", 409)
    value: dict[str, Any] = {
        "schema": SCHEMA,
        "authority": "historical_only",
        "proposal": document,
        "proposal_sha256": row.proposal_sha256,
        "decision": decision,
        "decision_sha256": proposals._hash(proposals._raw(decision)) if decision else None,
    }
    for permission in permissions(value, export=True):
        scopes._actor(db, actor, permission)
    request = chat.parse_workspace(value["proposal"]["request"])
    if request.estimate is not None:
        from . import draft_estimates

        draft_estimates._estimate(db, actor, draft_id, request.estimate.estimate_id, export=True)
    content = scopes._json(value)
    validate(content, reference, scope)
    return content


def summary(value: dict[str, Any]) -> dict[str, Any]:
    original, decision = value["proposal"], value["decision"]
    return {
        "id": original["id"],
        "base_revision": original["base_revision"],
        "generated_at": original["generated_at"],
        "action": original["request"]["action"],
        "decision_id": decision["id"] if decision else None,
        "outcome": decision["outcome"] if decision else "no_decision_selected",
    }


def source_manifest(
    values: list[dict[str, Any]], selected: dict[str, list[str]]
) -> list[dict[str, str]]:
    result = []
    for value in values:
        request = chat.parse_workspace(value["proposal"]["request"])
        for kind in ("word", "pdf", "xlsx"):
            source = getattr(request, kind)
            if source is not None:
                included = source.source_id in selected[kind]
                result.append(
                    {
                        "kind": "native_proposal_source",
                        "reference": f"{kind}:{source.source_id}:document:{source.document_sha256}",
                        "membership": "included" if included else "external",
                        "reason": "History retains selected context and a processed-document hash. "
                        + (
                            "Original separately selected."
                            if included
                            else "Original not selected."
                        ),
                    }
                )
    return result


def choices(
    db: Session, actor: User, draft_id: str, selected: list[Reference]
) -> list[dict[str, Any]]:
    """List metadata only; selected content/decisions are verified by package preview."""
    saved = proposals.list_saved(db, actor, draft_id)
    decisions = {
        proposal_id: decision_id
        for proposal_id, decision_id in db.execute(
            select(
                DraftWorkspaceProposalDecision.proposal_id, DraftWorkspaceProposalDecision.id
            ).where(DraftWorkspaceProposalDecision.proposal_id.in_([item["id"] for item in saved]))
        )
    }
    pinned = {item.proposal_id: item for item in selected}
    return [
        {
            **item,
            "value": (
                pinned[item["id"]].query_value()
                if item["id"] in pinned
                else item["id"] + ":" + decisions.get(item["id"], "none")
            ),
            "selected": item["id"] in pinned,
            "has_decision": (
                pinned[item["id"]].decision_id is not None
                if item["id"] in pinned
                else item["id"] in decisions
            ),
        }
        for item in saved
    ]
