"""Bounded, optional PDF interpretation with retained proposals and explicit Draft review.

Callers own transactions. Generation changes only proposal/audit records; application
uses the same Draft revision writer. No canonical Phase8 identity or writer is used.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..config import Settings
from ..models import DraftPdfSuggestion, DraftScope, User, new_id
from . import draft_pdf_intake as intake
from .draft_pdf_suggestion_contract import (
    PROMPT_VERSION,
    SuggestionError,
    SuggestionRequest,
    SuggestionResult,
    validate_suggestion_output,
)
from .draft_pdf_suggestion_transport import configured_port
from .draft_scope import (
    DraftScopeError,
    _actor,
    _append_revision,
    _atomic,
    _json,
    _revision_envelope,
    _unique_json_object,
    _valid_hash,
    get_draft,
    read_revision,
    validate_payload,
)
from .draft_scope_evidence import (
    SUGGESTION_TARGET_COLLECTIONS,
    observation_hash,
    reference_label,
    validate_suggestion_claim,
)

MAX_SUGGESTIONS = 20
MAX_PROPOSAL_BYTES = 128 * 1024
SCHEMA = "CLASSIFIRE-DRAFT-PDF-SUGGESTION-v1"


class SuggestionPort(Protocol):
    def complete(self, request: SuggestionRequest) -> SuggestionResult: ...


def availability(settings: Settings, port: SuggestionPort | None = None) -> dict[str, Any]:
    if port is not None:
        return {
            "enabled": True,
            "provider": "scripted",
            "model": "synthetic-fixture-v1",
            "demo": True,
        }
    enabled = bool(
        settings.draft_pdf_suggestions_enabled
        and settings.draft_pdf_suggestions_model
        and settings.draft_pdf_suggestions_api_key
    )
    return {
        "enabled": enabled,
        "provider": "openai" if enabled else None,
        "model": settings.draft_pdf_suggestions_model if enabled else None,
        "demo": False,
    }


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def _source_context(
    db: Session, actor: User, draft_id: str, source_id: str, page_number: int, settings: Settings
) -> tuple[dict[str, Any], dict[str, Any]]:
    source, document, content = intake._document(
        db, actor, draft_id, source_id, settings.storage_root
    )
    if type(page_number) is not int or not 1 <= page_number <= len(document["pages"]):
        raise DraftScopeError("PDF_PAGE_NOT_FOUND", 404)
    page = document["pages"][page_number - 1]
    if page["page_number"] != page_number:
        raise DraftScopeError("PDF_REVIEW_SOURCE_CHANGED", 409)
    binding = {
        "source_id": source.id,
        "source_sha256": content.sha256,
        "source_size_bytes": content.size_bytes,
        "original_filename": source.original_filename,
        "document_hash": source.document_sha256,
        "scan_sha256": hashlib.sha256((source.scan_json or "").encode("utf-8")).hexdigest(),
        "page": page_number,
        "locator_key": page["locator_key"],
        "page_text_sha256": page["page_text_sha256"],
    }
    return binding, page


def _items(output: dict[str, Any]) -> list[dict[str, Any]]:
    ids = {item["key"]: new_id() for collection in output.values() for item in collection}
    payload: dict[str, Any] = {name: [] for name in SUGGESTION_TARGET_COLLECTIONS.values()}
    evidence: dict[str, dict[str, str]] = {}
    for kind, collection in SUGGESTION_TARGET_COLLECTIONS.items():
        for source in output[collection]:
            identity = ids[source["key"]]
            evidence[identity] = {key: source[key] for key in ("basis", "quote", "rationale")}
            item: dict[str, Any] = {"id": identity}
            if kind != "observation":
                item["label"] = source["label"]
            if kind == "defect":
                item["description"] = source["description"]
            elif kind == "opening":
                item.update(
                    defect_id=ids[source["defect_key"]] if source["defect_key"] else None,
                    plane=source["plane"],
                    substrate=source["substrate"],
                    width_mm=None,
                    height_mm=None,
                    blank=False,
                    state="Inferred",
                )
            elif kind == "service":
                item.update(
                    opening_ids=[ids[key] for key in source["opening_keys"]],
                    service_type=source["service_type"],
                    quantity=None,
                    unit="each",
                    state="Inferred",
                )
            else:
                item.update(text=source["text"], state="Unresolved")
            payload[collection].append(item)
    normalized = validate_payload(payload)[0].model_dump(mode="json")
    return [
        {"target_kind": kind, "target_id": item["id"], "proposed_item": item} | evidence[item["id"]]
        for kind, collection in SUGGESTION_TARGET_COLLECTIONS.items()
        for item in normalized[collection]
    ]


def _claim(document: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "CLASSIFIRE-DRAFT-PDF-SUGGESTION-CLAIM-v1",
        "suggestion_id": document["id"],
        **{
            key: document[key]
            for key in (
                "provider",
                "model",
                "prompt_version",
                "input_sha256",
                "response_sha256",
                "page_image_sha256",
                "generated_at",
            )
        },
        **{key: item[key] for key in ("proposed_item", "basis", "quote", "rationale")},
    }


def _record(
    db: Session, actor: User, draft_id: str, suggestion_id: str, *, lock: bool = False
) -> tuple[DraftPdfSuggestion, dict[str, Any]]:
    get_draft(db, actor, draft_id)
    query = (
        select(DraftPdfSuggestion)
        .where(
            DraftPdfSuggestion.id == suggestion_id,
            DraftPdfSuggestion.draft_scope_id == draft_id,
            DraftPdfSuggestion.created_by_id == actor.id,
        )
        .execution_options(populate_existing=True)
    )
    row = db.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise DraftScopeError("PDF_SUGGESTION_NOT_FOUND", 404)
    try:
        raw = row.proposal_json.encode("utf-8")
        if (
            not 1 <= len(raw) <= MAX_PROPOSAL_BYTES
            or hashlib.sha256(raw).hexdigest() != row.proposal_sha256
        ):
            raise ValueError("integrity")
        value = json.loads(raw, object_pairs_hook=_unique_json_object)
        if set(value) != {
            "schema",
            "id",
            "actor_id",
            "draft_id",
            "base_revision",
            "base_hash",
            "source",
            "provider",
            "model",
            "prompt_version",
            "input_sha256",
            "response_sha256",
            "page_image_sha256",
            "generated_at",
            "items",
            "request_binding",
        } or any(
            value[key] != expected
            for key, expected in {
                "schema": SCHEMA,
                "id": row.id,
                "actor_id": actor.id,
                "draft_id": draft_id,
                "base_revision": row.base_revision,
            }.items()
        ):
            raise ValueError("binding")
        if value["source"]["source_id"] != row.source_id or not _valid_hash(value["base_hash"]):
            raise ValueError("source")
        if (
            value["provider"] not in ("openai", "scripted")
            or value["prompt_version"] != PROMPT_VERSION
            or type(value["model"]) is not str
            or not 1 <= len(value["model"]) <= 100
            or any(
                not _valid_hash(value[key])
                for key in ("input_sha256", "response_sha256", "page_image_sha256")
            )
            or type(value["generated_at"]) is not str
            or len(value["generated_at"]) > 40
        ):
            raise ValueError("metadata")
        generated = datetime.fromisoformat(value["generated_at"])
        if (
            generated.tzinfo is None
            or generated.astimezone(UTC).isoformat() != value["generated_at"]
        ):
            raise ValueError("metadata time")
        request_binding = value["request_binding"]
        if (
            type(request_binding) is not dict
            or set(request_binding)
            != {
                "source",
                "base_hash",
                "prompt_version",
                "page_image_sha256",
                "text_sha256",
                "provider",
                "requested_model",
            }
            or any(
                request_binding[key] != value[key]
                for key in (
                    "source",
                    "base_hash",
                    "prompt_version",
                    "page_image_sha256",
                    "provider",
                )
            )
            or type(request_binding["requested_model"]) is not str
            or not 1 <= len(request_binding["requested_model"]) <= 100
            or not _valid_hash(request_binding["text_sha256"])
            or _digest(request_binding) != value["input_sha256"]
        ):
            raise ValueError("input")
        if type(value["items"]) is not list or len(value["items"]) > 25:
            raise ValueError("items")
        identities = set()
        for item in value["items"]:
            if set(item) != {
                "target_kind",
                "target_id",
                "proposed_item",
                "basis",
                "quote",
                "rationale",
            }:
                raise ValueError("item")
            if item["target_id"] in identities:
                raise ValueError("duplicate")
            identities.add(item["target_id"])
            validate_suggestion_claim(
                _claim(value, item), target_kind=item["target_kind"], target_id=item["target_id"]
            )
        return row, value
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        raise DraftScopeError("PDF_SUGGESTION_INTEGRITY_FAILED", 409) from None


def _merge(base: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    payload = copy.deepcopy(base["content"])
    for item in items:
        payload[SUGGESTION_TARGET_COLLECTIONS[item["target_kind"]]].append(
            copy.deepcopy(item["proposed_item"])
        )
    return validate_payload(payload)[0].model_dump(mode="json")


def generate(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    expected_revision: int,
    page_number: int,
    expected_document_hash: str,
    *,
    settings: Settings,
    port: SuggestionPort | None = None,
) -> DraftPdfSuggestion:
    """One explicit inference call; retain a proposal, never apply it to Scope."""
    with db.no_autoflush:
        actor = _actor(db, actor, "project:write")
        draft = get_draft(db, actor, draft_id)
        # Serialize the bounded per-Draft request quota, including the one provider call.
        db.scalar(select(DraftScope.id).where(DraftScope.id == draft_id).with_for_update())
        current = read_revision(db, actor, draft_id)
        if type(expected_revision) is not int or expected_revision != current["revision"]:
            raise DraftScopeError("DRAFT_REVISION_CONFLICT", 409)
        if (
            db.scalar(
                select(func.count())
                .select_from(DraftPdfSuggestion)
                .where(DraftPdfSuggestion.draft_scope_id == draft_id)
            )
            or 0
        ) >= MAX_SUGGESTIONS:
            raise DraftScopeError("PDF_SUGGESTION_LIMIT", 409)
        binding, page = _source_context(db, actor, draft_id, source_id, page_number, settings)
        if binding["document_hash"] != expected_document_hash:
            raise DraftScopeError("PDF_REVIEW_SOURCE_CHANGED", 409)
        try:
            selected_port = port if port is not None else configured_port(settings)
        except SuggestionError:
            raise DraftScopeError("PDF_SUGGESTIONS_UNAVAILABLE", 409) from None
        if selected_port is None:
            raise DraftScopeError("PDF_SUGGESTIONS_UNAVAILABLE", 409)
        png = intake.page_preview(db, actor, draft_id, source_id, page_number, settings=settings)
        actor = _actor(db, actor, "project:write")
        if read_revision(db, actor, draft_id)["sha256"] != current["sha256"]:
            raise DraftScopeError("PDF_SUGGESTION_INPUT_CHANGED", 409)
        if _source_context(db, actor, draft_id, source_id, page_number, settings)[0] != binding:
            raise DraftScopeError("PDF_SUGGESTION_INPUT_CHANGED", 409)
        info = availability(settings, port)
        image_hash = hashlib.sha256(png).hexdigest()
        request_binding = {
            "source": binding,
            "base_hash": current["sha256"],
            "prompt_version": PROMPT_VERSION,
            "page_image_sha256": image_hash,
            "text_sha256": hashlib.sha256(page["text"].encode("utf-8")).hexdigest(),
            "provider": info["provider"],
            "requested_model": info["model"],
        }
        input_hash = _digest(request_binding)
        # Reuse an already retained identical request rather than charge for double-clicks.
        for existing in db.scalars(
            select(DraftPdfSuggestion).where(
                DraftPdfSuggestion.draft_scope_id == draft_id,
                DraftPdfSuggestion.created_by_id == actor.id,
                DraftPdfSuggestion.base_revision == expected_revision,
                DraftPdfSuggestion.status == "pending",
            )
        ):
            _, retained = _record(db, actor, draft_id, existing.id)
            if retained["input_sha256"] == input_hash:
                return existing
        try:
            result = selected_port.complete(
                SuggestionRequest(page_text=page["text"], page_png=png, input_sha256=input_hash)
            )
            if not isinstance(result, SuggestionResult):
                raise ValueError("result")
            output = validate_suggestion_output(result.output, page_text=page["text"])
            if (
                result.provider != info["provider"]
                or type(result.model) is not str
                or not 1 <= len(result.model) <= 100
                or not _valid_hash(result.response_sha256)
            ):
                raise ValueError("provider")
            items = _items(output)
        except (SuggestionError, ValueError, TypeError, KeyError):
            raise DraftScopeError("PDF_SUGGESTION_FAILED", 422) from None
        actor = _actor(db, actor, "project:write")
        latest = read_revision(db, actor, draft_id)
        final_binding, _ = _source_context(db, actor, draft_id, source_id, page_number, settings)
        if final_binding != binding or latest["sha256"] != current["sha256"]:
            raise DraftScopeError("PDF_SUGGESTION_INPUT_CHANGED", 409)
        identity = new_id()
        document = {
            "schema": SCHEMA,
            "id": identity,
            "actor_id": actor.id,
            "draft_id": draft_id,
            "base_revision": expected_revision,
            "base_hash": current["sha256"],
            "source": binding,
            "provider": result.provider,
            "model": result.model,
            "prompt_version": PROMPT_VERSION,
            "input_sha256": input_hash,
            "response_sha256": result.response_sha256,
            "page_image_sha256": image_hash,
            "generated_at": datetime.now(UTC).isoformat(),
            "items": items,
            "request_binding": request_binding,
        }
        try:
            for item in items:
                validate_suggestion_claim(
                    _claim(document, item),
                    target_kind=item["target_kind"],
                    target_id=item["target_id"],
                )
        except (ValueError, TypeError, KeyError):
            raise DraftScopeError("PDF_SUGGESTION_FAILED") from None
        _merge(current, items)
        raw = _json(document)
        if len(raw) > MAX_PROPOSAL_BYTES:
            raise DraftScopeError("PDF_SUGGESTION_TOO_LARGE")
    with _atomic(db):
        row = DraftPdfSuggestion(
            id=identity,
            draft_scope_id=draft_id,
            source_id=source_id,
            created_by_id=actor.id,
            base_revision=expected_revision,
            proposal_json=raw.decode("utf-8"),
            proposal_sha256=hashlib.sha256(raw).hexdigest(),
            status="pending",
        )
        db.add(row)
        db.flush()
        record_audit(
            db,
            actor=actor,
            action="draft_pdf_suggestion.prepare",
            entity_type="draft_pdf_suggestion",
            entity_id=row.id,
            project_id=draft.project_id,
            new_value={
                "sha256": row.proposal_sha256,
                "provider": result.provider,
                "base_revision": expected_revision,
            },
        )
        db.flush()
        return row


def read_suggestion(
    db: Session, actor: User, draft_id: str, suggestion_id: str, *, settings: Settings
) -> dict[str, Any]:
    with db.no_autoflush:
        actor = _actor(db, actor, "project:read")
        row, document = _record(db, actor, draft_id, suggestion_id)
        binding, page = _source_context(
            db, actor, draft_id, row.source_id, document["source"]["page"], settings
        )
        if binding != document["source"]:
            raise DraftScopeError("PDF_SUGGESTION_INPUT_CHANGED", 409)
        if (
            hashlib.sha256(page["text"].encode("utf-8")).hexdigest()
            != document["request_binding"]["text_sha256"]
        ):
            raise DraftScopeError("PDF_SUGGESTION_INTEGRITY_FAILED", 409)
        for item in document["items"]:
            if (
                item["basis"] in ("page_text", "both")
                and (not item["quote"].strip() or item["quote"] not in page["text"])
            ) or (item["basis"] == "page_image" and item["quote"] != ""):
                raise DraftScopeError("PDF_SUGGESTION_INTEGRITY_FAILED", 409)
        base = read_revision(db, actor, draft_id, row.base_revision)
        if base["sha256"] != document["base_hash"]:
            raise DraftScopeError("PDF_SUGGESTION_INTEGRITY_FAILED", 409)
        current = read_revision(db, actor, draft_id)
        return {
            **document,
            "status": row.status,
            "expected_revision": row.base_revision,
            "current_revision": current["revision"],
            "stale": current["sha256"] != document["base_hash"],
            "applied_revision": row.applied_revision,
            "source_id": row.source_id,
            "page_number": binding["page"],
            "document_hash": binding["document_hash"],
            "payload": _merge(base, document["items"]),
            "targets": [
                {key: item[key] for key in ("target_kind", "target_id")}
                for item in document["items"]
            ],
        }


def list_suggestions(
    db: Session, actor: User, draft_id: str, source_id: str, *, settings: Settings
) -> list[dict[str, Any]]:
    with db.no_autoflush:
        intake._document(db, actor, draft_id, source_id, settings.storage_root)
        current = read_revision(db, actor, draft_id)
        rows = list(
            db.scalars(
                select(DraftPdfSuggestion)
                .where(
                    DraftPdfSuggestion.draft_scope_id == draft_id,
                    DraftPdfSuggestion.source_id == source_id,
                    DraftPdfSuggestion.created_by_id == actor.id,
                )
                .order_by(DraftPdfSuggestion.created_at.desc())
                .limit(MAX_SUGGESTIONS)
            )
        )
        values = []
        for row in rows:
            _, document = _record(db, actor, draft_id, row.id)
            values.append(
                {
                    "id": row.id,
                    "page_number": document["source"]["page"],
                    "status": row.status,
                    "provider": document["provider"],
                    "model": document["model"],
                    "generated_at": document["generated_at"],
                    "expected_revision": row.base_revision,
                    "applied_revision": row.applied_revision,
                    "stale": current["sha256"] != document["base_hash"],
                }
            )
        return values


def _refs(preview: dict[str, Any], created: str) -> list[dict[str, Any]]:
    items = {
        (item["target_kind"], item["target_id"]): item
        for item in preview["suggestion_document"]["items"]
    }
    refs = []
    for target in preview["targets"]:
        kind, identity = target["target_kind"], target["target_id"]
        proposed = items[(kind, identity)]
        final = next(
            item
            for item in preview["payload"][SUGGESTION_TARGET_COLLECTIONS[kind]]
            if item["id"] == identity
        )
        refs.append(
            dict(target)
            | {
                "target_sha256": observation_hash(final),
                **{
                    key: preview[key]
                    for key in (
                        "source_id",
                        "source_sha256",
                        "source_size_bytes",
                        "original_filename",
                        "locator_key",
                        "page_text_sha256",
                        "scan_sha256",
                    )
                },
                "page_number": preview["page"],
                "document_sha256": preview["document_hash"],
                "reviewed_by": preview["actor_id"],
                "reviewed_at": created,
                "method": "human_page_entity_review",
                "origin": "local_retained",
                "suggestion": _claim(preview["suggestion_document"], proposed),
            }
        )
    return refs


def preview_suggestion(
    db: Session,
    actor: User,
    draft_id: str,
    suggestion_id: str,
    expected_revision: int,
    payload: dict[str, Any],
    targets: list[dict[str, str]],
    *,
    settings: Settings,
) -> dict[str, Any]:
    with db.no_autoflush:
        actor = _actor(db, actor, "project:write")
        value = read_suggestion(db, actor, draft_id, suggestion_id, settings=settings)
        if (
            value["status"] != "pending"
            or value["stale"]
            or type(expected_revision) is not int
            or expected_revision != value["expected_revision"]
        ):
            raise DraftScopeError("PDF_SUGGESTION_NOT_PENDING", 409)
        normalized, findings = validate_payload(payload)
        content = normalized.model_dump(mode="json")
        known = {(item["target_kind"], item["target_id"]) for item in value["items"]}
        selected: set[tuple[str, str]] = set()
        if type(targets) is not list or not 1 <= len(targets) <= 25:
            raise DraftScopeError("PDF_REVIEW_TARGETS_INVALID")
        for target in targets:
            if (
                type(target) is not dict
                or set(target) != {"target_kind", "target_id"}
                or any(type(v) is not str for v in target.values())
            ):
                raise DraftScopeError("PDF_REVIEW_TARGETS_INVALID")
            identity = target["target_kind"], target["target_id"]
            if identity not in known or identity in selected:
                raise DraftScopeError("PDF_REVIEW_TARGETS_INVALID")
            selected.add(identity)
        present = {
            (kind, item["id"])
            for kind, collection in SUGGESTION_TARGET_COLLECTIONS.items()
            for item in content[collection]
        }
        if selected != known & present:
            raise DraftScopeError("PDF_SUGGESTION_REVIEW_REQUIRED")
        row, document = _record(db, actor, draft_id, suggestion_id)
        binding = {
            "schema": "CLASSIFIRE-DRAFT-PDF-SUGGESTION-REVIEW-v1",
            "actor_id": actor.id,
            "draft_id": draft_id,
            "suggestion_id": suggestion_id,
            "suggestion_sha256": row.proposal_sha256,
            "current_hash": value["base_hash"],
            "expected_revision": expected_revision,
            "payload": content,
            "targets": [
                {"target_kind": kind, "target_id": identity} for kind, identity in sorted(selected)
            ],
            **value["source"],
        }
        preview = binding | {"suggestion_document": document}
        draft = get_draft(db, actor, draft_id)
        # Use the exact shared revision builder and maximum-width timestamps to refuse
        # oversized retained provenance during no-write preview, not after confirmation.
        latest = read_revision(db, actor, draft_id)
        _revision_envelope(
            draft_id=draft_id,
            project_id=draft.project_id,
            actor_id=actor.id,
            expected_revision=expected_revision,
            created=datetime.max.replace(tzinfo=UTC),
            content=content,
            prior=latest,
            entity_evidence_refs=_refs(preview, datetime.max.replace(tzinfo=UTC).isoformat()),
        )
        _actor(db, actor, "project:write")
        get_draft(db, actor, draft_id)
        return preview | {
            "review_sha256": _digest(binding),
            "findings": findings,
            "target_labels": [reference_label(target, content) for target in binding["targets"]],
        }


def save_suggestion(
    db: Session,
    actor: User,
    draft_id: str,
    suggestion_id: str,
    expected_revision: int,
    payload: dict[str, Any],
    targets: list[dict[str, str]],
    expected_review_hash: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    with db.no_autoflush:
        _actor(db, actor, "project:write")
        row, _ = _record(db, actor, draft_id, suggestion_id, lock=True)
        preview = preview_suggestion(
            db,
            actor,
            draft_id,
            suggestion_id,
            expected_revision,
            payload,
            targets,
            settings=settings,
        )
        if not _valid_hash(expected_review_hash) or not hmac.compare_digest(
            preview["review_sha256"], expected_review_hash
        ):
            raise DraftScopeError("PDF_REVIEW_PREVIEW_CHANGED", 409)
    with _atomic(db):
        envelope = _append_revision(
            db,
            actor,
            draft_id,
            expected_revision,
            preview["payload"],
            entity_evidence_refs=_refs(preview, datetime.now(UTC).isoformat()),
        )
        row.status = "applied"
        row.applied_revision = envelope["revision"]
        record_audit(
            db,
            actor=actor,
            action="draft_pdf_suggestion.apply",
            entity_type="draft_pdf_suggestion",
            entity_id=row.id,
            project_id=envelope["project_id"],
            new_value={"revision": envelope["revision"], "sha256": envelope["sha256"]},
        )
        db.flush()
        return envelope


def reject_suggestion(
    db: Session, actor: User, draft_id: str, suggestion_id: str, *, settings: Settings
) -> None:
    with db.no_autoflush:
        actor = _actor(db, actor, "project:write")
        row, _ = _record(db, actor, draft_id, suggestion_id, lock=True)
        read_suggestion(db, actor, draft_id, suggestion_id, settings=settings)
        if row.status != "pending":
            raise DraftScopeError("PDF_SUGGESTION_NOT_PENDING", 409)
    with _atomic(db):
        row.status = "rejected"
        record_audit(
            db,
            actor=actor,
            action="draft_pdf_suggestion.reject",
            entity_type="draft_pdf_suggestion",
            entity_id=row.id,
            project_id=get_draft(db, actor, draft_id).project_id,
            new_value={"status": "rejected"},
        )
        db.flush()
