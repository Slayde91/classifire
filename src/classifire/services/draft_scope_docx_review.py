"""Explicit Word-to-Scope claims through the existing guarded Draft revision writer."""

from __future__ import annotations

import copy
import hmac
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from ..config import Settings
from ..models import User
from .draft_scope import (
    DraftScopeError,
    _actor,
    _append_revision,
    _revision_envelope,
    _valid_hash,
    read_revision,
    validate_payload,
)
from .draft_scope_docx import intake
from .draft_scope_evidence import MAX_EVIDENCE_REFS, TARGET_COLLECTIONS, observation_hash
from .draft_scope_xlsx import _review_context
from .draft_scope_xlsx_contract import digest


def _refs(preview: dict[str, Any], reviewed_at: str) -> list[dict[str, Any]]:
    refs = []
    for target in preview["targets"]:
        item = next(
            item
            for item in preview["payload"][TARGET_COLLECTIONS[target["target_kind"]]]
            if item["id"] == target["target_id"]
        )
        ref = {
            key: preview[key]
            for key in (
                "source_id",
                "source_sha256",
                "source_size_bytes",
                "original_filename",
                "document_sha256",
                "scan_sha256",
            )
        }
        ref.update(
            source_kind="docx",
            target_kind=target["target_kind"],
            target_id=target["target_id"],
            target_sha256=observation_hash(item),
            block=preview["blocks"][target["locator"]],
            images=[preview["selected_images"][identity] for identity in target["image_ids"]],
            reviewed_by=preview["actor_id"],
            reviewed_at=reviewed_at,
            method="human_docx_entity_review",
            origin="local_retained",
        )
        refs.append(ref)
    return refs


def preview_review(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    expected_revision: int,
    payload: dict[str, Any],
    targets: list[dict[str, Any]],
    expected_document_hash: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    with db.no_autoflush:
        actor, current, document, binding = _review_context(
            db,
            actor,
            draft_id,
            source_id,
            expected_revision,
            expected_document_hash,
            settings,
            source_api=intake(),
            review_schema="CLASSIFIRE-DRAFT-DOCX-SCOPE-REVIEW-v1",
        )
        model, findings = validate_payload(payload)
        normalized = model.model_dump(mode="json")
        blocks = {
            block["locator"]: {key: block[key] for key in ("locator", "text", "text_sha256")}
            for block in document["blocks"]
        }
        images = {image["id"]: image for image in document["pictures"]}
        if type(targets) is not list or not 1 <= len(targets) <= MAX_EVIDENCE_REFS:
            raise DraftScopeError("SCOPE_DOCX_TARGETS_INVALID")
        selected, seen = [], set()
        for target in targets:
            if (
                type(target) is not dict
                or set(target) != {"target_kind", "target_id", "locator", "image_ids"}
                or type(target["target_kind"]) is not str
                or target["target_kind"] not in TARGET_COLLECTIONS
                or type(target["target_id"]) is not str
                or type(target["locator"]) is not str
                or target["locator"] not in blocks
                or type(target["image_ids"]) is not list
                or len(target["image_ids"]) > 40
                or any(
                    type(identity) is not str or identity not in images
                    for identity in target["image_ids"]
                )
            ):
                raise DraftScopeError("SCOPE_DOCX_TARGETS_INVALID")
            identity = (target["target_kind"], target["target_id"], target["locator"])
            if identity in seen or len(set(target["image_ids"])) != len(target["image_ids"]):
                raise DraftScopeError("SCOPE_DOCX_TARGETS_INVALID")
            if not any(
                item["id"] == target["target_id"]
                for item in normalized[TARGET_COLLECTIONS[target["target_kind"]]]
            ):
                raise DraftScopeError("SCOPE_DOCX_TARGETS_INVALID")
            seen.add(identity)
            selected.append(copy.deepcopy(target))
        selected.sort(
            key=lambda target: (target["target_kind"], target["target_id"], target["locator"])
        )
        for target in selected:
            target["image_ids"].sort()
        binding.update(
            payload=normalized,
            targets=selected,
            blocks={target["locator"]: blocks[target["locator"]] for target in selected},
            selected_images={
                identity: images[identity]
                for target in selected
                for identity in target["image_ids"]
            },
        )
        budget_time = datetime.max.replace(tzinfo=UTC)
        _revision_envelope(
            draft_id=draft_id,
            project_id=current["project_id"],
            actor_id=actor.id,
            expected_revision=expected_revision,
            created=budget_time,
            content=normalized,
            prior=current,
            entity_evidence_refs=_refs(binding, budget_time.isoformat()),
        )
        _actor(db, actor, "project:write")
        read_revision(db, actor, draft_id)
        return binding | {"review_sha256": digest(binding), "findings": findings}


def save_review(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    expected_revision: int,
    payload: dict[str, Any],
    targets: list[dict[str, Any]],
    expected_document_hash: str,
    expected_review_hash: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    preview = preview_review(
        db,
        actor,
        draft_id,
        source_id,
        expected_revision,
        payload,
        targets,
        expected_document_hash,
        settings=settings,
    )
    if not _valid_hash(expected_review_hash) or not hmac.compare_digest(
        preview["review_sha256"], expected_review_hash
    ):
        raise DraftScopeError("SCOPE_DOCX_PREVIEW_CHANGED", 409)
    return _append_revision(
        db,
        actor,
        draft_id,
        expected_revision,
        preview["payload"],
        entity_evidence_refs=_refs(preview, datetime.now(UTC).isoformat()),
    )
