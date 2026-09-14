"""Unverified Word/PDF/XLSX additions prepared for the existing separate human reviews.

No writer or provider is called here. Existing rows are copied unchanged; model
identities belong only to the proposed graph and are remapped before review.
"""

from __future__ import annotations

import copy
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import User, new_id
from .draft_scope import DraftScopeError, DraftScopePayload, read_revision, validate_payload
from .draft_scope_docx_review import preview_review
from .draft_scope_evidence import TARGET_COLLECTIONS
from .draft_workspace_chat import Advice, WorkspaceChatRequest, scope_response_schema


class WordClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    target_kind: Literal["defect", "opening", "service"]
    target_id: Annotated[str, Field(min_length=36, max_length=36)]
    locator: Annotated[str, Field(min_length=1, max_length=150)]
    image_ids: Annotated[list[str], Field(max_length=2)]
    basis: Literal["text", "picture", "both"]
    quote: Annotated[str, Field(max_length=2000)]
    rationale: Annotated[str, Field(min_length=1, max_length=1000)]


class WordProposal(Advice):
    additions: DraftScopePayload
    claims: Annotated[list[WordClaim], Field(max_length=50)]


Column = Annotated[int, Field(ge=1, le=50)] | None


class XlsxMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    defect_label: Column
    defect_description: Column
    location: Column
    opening_label: Column
    plane: Column
    substrate: Column
    width_mm: Column
    height_mm: Column
    service_label: Column
    service_type: Column
    quantity: Column
    unit: Column


class XlsxProposal(WordProposal):
    mapping: XlsxMapping


def response_schema(*, xlsx: bool = False) -> dict[str, Any]:
    return scope_response_schema(XlsxProposal if xlsx else WordProposal)


def validate_output(
    value: Any, context: dict[str, Any], *, source_kind: Literal["word", "pdf", "xlsx"] = "word"
) -> WordProposal:
    model = (
        XlsxProposal.model_validate(value)
        if source_kind == "xlsx"
        else WordProposal.model_validate(value)
    )
    graph = model.additions.model_dump(mode="json")
    # Enforce complete fields locally too, including injected/mock providers.
    raw_graph = value["additions"]
    if set(raw_graph) != set(DraftScopePayload.model_fields):
        raise ValueError("incomplete graph")
    rows = {}
    for kind, collection in TARGET_COLLECTIONS.items():
        for raw, row in zip(raw_graph[collection], graph[collection], strict=True):
            if set(raw) != set(row) or row.get("state") == "Confirmed":
                raise ValueError("incomplete or confirmed proposal")
            rows[kind, row["id"]] = row
    if len(rows) > 25 or any(graph[key] for key in ("observations", "assumptions", "exclusions")):
        raise ValueError("proposal budget or unbound assumptions")
    validate_payload(graph)
    evidence = context[source_kind + "_evidence"]
    blocks = {block["locator"]: block for block in evidence["blocks"]}
    if source_kind == "pdf":
        blocks.setdefault(evidence["page"]["locator"], {"text": ""})
    mapping: dict[str, int | None] = {}
    if isinstance(model, XlsxProposal):
        mapping = model.mapping.model_dump()
        if any(
            column is not None and column > evidence["sheet"]["columns"]
            for column in mapping.values()
        ):
            raise ValueError("unselected mapping column")
    images = {image["id"] for image in evidence["pictures"]}
    covered, seen = set(), set()
    for claim in model.claims:
        target = (claim.target_kind, claim.target_id)
        identity = (*target, claim.locator)
        if target not in rows or claim.locator not in blocks or identity in seen:
            raise ValueError("unbound or duplicate claim")
        if len(set(claim.image_ids)) != len(claim.image_ids) or not set(claim.image_ids) <= images:
            raise ValueError("unselected image")
        if claim.basis in {"text", "both"}:
            if not claim.quote.strip() or claim.quote not in blocks[claim.locator]["text"]:
                raise ValueError("unbound quote")
            if source_kind == "xlsx" and not any(
                cell["column"] in mapping.values()
                and cell["kind"] not in {"formula", "error"}
                and claim.quote in cell["value"]
                for cell in blocks[claim.locator]["cells"]
            ):
                raise ValueError("quote needs a selected mapped non-formula cell")
        elif claim.quote:
            raise ValueError("picture claim has text quote")
        if (claim.basis != "text") != bool(claim.image_ids):
            raise ValueError("evidence basis mismatch")
        covered.add(target)
        seen.add(identity)
    if covered != set(rows):
        raise ValueError("every proposed record needs evidence")
    return model


def prepare_review(
    db: Session,
    actor: User,
    request: WorkspaceChatRequest,
    model: WordProposal,
    *,
    settings: Settings,
) -> dict[str, Any] | None:
    selected = request.word or request.pdf or request.xlsx
    if selected is None or request.draft_id is None:
        raise DraftScopeError("CHAT_INPUT_INVALID")
    additions = model.additions.model_dump(mode="json")
    identities = {
        row["id"]: new_id()
        for collection in TARGET_COLLECTIONS.values()
        for row in additions[collection]
    }
    if not identities:
        return None
    current = read_revision(db, actor, request.draft_id)
    if current["revision"] != request.revision:
        raise DraftScopeError("CHAT_CONTEXT_CHANGED", 409)
    payload = copy.deepcopy(current["content"])
    for collection in TARGET_COLLECTIONS.values():
        for row in additions[collection]:
            row["id"] = identities[row["id"]]
            if row.get("defect_id") is not None:
                row["defect_id"] = identities[row["defect_id"]]
            if "opening_ids" in row:
                row["opening_ids"] = [identities[key] for key in row["opening_ids"]]
        payload[collection].extend(additions[collection])
    claims = [
        claim.model_dump() | {"target_id": identities[claim.target_id]} for claim in model.claims
    ]
    targets = [
        {key: claim[key] for key in ("target_kind", "target_id", "locator", "image_ids")}
        for claim in claims
    ]
    extra: dict[str, Any] = {}
    if request.xlsx is not None:
        from .draft_scope_xlsx import preview_review as xlsx_preview

        if not isinstance(model, XlsxProposal):
            raise DraftScopeError("CHAT_INPUT_INVALID")
        targets = [
            {
                "target_kind": claim["target_kind"],
                "target_id": claim["target_id"],
                "row": int(claim["locator"].rsplit(":", 1)[1]),
                "image_ids": claim["image_ids"],
            }
            for claim in claims
        ]
        plan = {
            "sheet_index": request.xlsx.sheet_index,
            "header_row": request.xlsx.header_row,
            "mapping": model.mapping.model_dump(),
            "selections": [
                {
                    "row": row,
                    "kinds": sorted(
                        {target["target_kind"] for target in targets if target["row"] == row}
                    ),
                }
                for row in sorted({target["row"] for target in targets})
            ],
        }
        checked = xlsx_preview(
            db,
            actor,
            request.draft_id,
            selected.source_id,
            current["revision"],
            payload,
            plan,
            targets,
            selected.document_sha256,
            settings=settings,
        )
        extra = {"source_kind": "xlsx", "plan": checked["plan"]}
    elif request.pdf is not None:
        from .draft_pdf_intake import preview_scope_page

        targets = [{key: claim[key] for key in ("target_kind", "target_id")} for claim in claims]
        checked = preview_scope_page(
            db,
            actor,
            request.draft_id,
            selected.source_id,
            current["revision"],
            request.pdf.page_number,
            payload,
            targets,
            selected.document_sha256,
            settings=settings,
        )
    else:
        checked = preview_review(
            db,
            actor,
            request.draft_id,
            selected.source_id,
            current["revision"],
            payload,
            targets,
            selected.document_sha256,
            settings=settings,
        )
    return {
        **extra,
        **({"source_kind": "pdf", "page_number": request.pdf.page_number} if request.pdf else {}),
        "additions": additions,
        "claims": claims,
        "findings": checked["findings"],
        "expected_revision": current["revision"],
        "source_id": selected.source_id,
        "document_sha256": selected.document_sha256,
        "payload": checked["payload"],
        "targets": checked["targets"],
        "notice": "Unverified additions only. Review separately before saving one Draft revision.",
    }
