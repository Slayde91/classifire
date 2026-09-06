"""Portable page-reference claims; local authority is checked by intake services."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

EVIDENCE_SCHEMA_VERSION = "CLASSIFIRE-DRAFT-SCOPE-v3"
ENTITY_EVIDENCE_SCHEMA_VERSION = "CLASSIFIRE-DRAFT-SCOPE-v4"
XLSX_EVIDENCE_SCHEMA_VERSION = "CLASSIFIRE-DRAFT-SCOPE-v5"
SUGGESTION_EVIDENCE_SCHEMA_VERSION = "CLASSIFIRE-DRAFT-SCOPE-v6"
WORKBOOK_EVIDENCE_SCHEMAS = (XLSX_EVIDENCE_SCHEMA_VERSION, SUGGESTION_EVIDENCE_SCHEMA_VERSION)
ENTITY_EVIDENCE_SCHEMAS = (ENTITY_EVIDENCE_SCHEMA_VERSION, *WORKBOOK_EVIDENCE_SCHEMAS)
EVIDENCE_SCHEMAS = (EVIDENCE_SCHEMA_VERSION, *ENTITY_EVIDENCE_SCHEMAS)
MAX_EVIDENCE_REFS = 100
REF_KEYS = frozenset(
    {
        "observation_id",
        "observation_sha256",
        "source_id",
        "source_sha256",
        "source_size_bytes",
        "original_filename",
        "page_number",
        "locator_key",
        "page_text_sha256",
        "document_sha256",
        "scan_sha256",
        "reviewed_by",
        "reviewed_at",
        "method",
        "origin",
    }
)


def observation_hash(observation: dict[str, Any]) -> str:
    import json

    return hashlib.sha256(
        json.dumps(
            observation, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


COMMON_REF_KEYS = REF_KEYS - {"observation_id", "observation_sha256"}
ENTITY_REF_KEYS = COMMON_REF_KEYS | {"target_kind", "target_id", "target_sha256"}
XLSX_REF_KEYS = (ENTITY_REF_KEYS - {"page_number", "locator_key", "page_text_sha256"}) | {
    "source_kind",
    "row",
    "images",
}
TARGET_COLLECTIONS = {"defect": "defects", "opening": "openings", "service": "services"}
SUGGESTION_TARGET_COLLECTIONS = TARGET_COLLECTIONS | {"observation": "observations"}
SUGGESTION_CLAIM_SCHEMA = "CLASSIFIRE-DRAFT-PDF-SUGGESTION-CLAIM-v1"
SUGGESTION_CLAIM_KEYS = frozenset(
    {
        "schema",
        "suggestion_id",
        "provider",
        "model",
        "prompt_version",
        "input_sha256",
        "response_sha256",
        "page_image_sha256",
        "generated_at",
        "proposed_item",
        "basis",
        "quote",
        "rationale",
    }
)


def validate_suggestion_claim(value: Any, *, target_kind: str, target_id: str) -> None:
    """Validate portable AI-origin claims, never local execution or review authority."""
    if type(value) is not dict or set(value) != SUGGESTION_CLAIM_KEYS:
        raise ValueError("suggestion shape")
    if (
        value["schema"] != SUGGESTION_CLAIM_SCHEMA
        or value["provider"] not in ("openai", "scripted")
        or value["prompt_version"] != "draft-pdf-suggestions-v1"
        or value["basis"] not in ("page_text", "page_image", "both")
    ):
        raise ValueError("suggestion contract")
    identity = value["suggestion_id"]
    if type(identity) is not str or str(UUID(identity)) != identity:
        raise ValueError("suggestion identity")
    for key in ("input_sha256", "response_sha256", "page_image_sha256"):
        if type(value[key]) is not str or not re.fullmatch(r"[0-9a-f]{64}", value[key]):
            raise ValueError("suggestion hash")
    for key, minimum, maximum in (("model", 1, 100), ("quote", 0, 500), ("rationale", 0, 1000)):
        if type(value[key]) is not str or not minimum <= len(value[key]) <= maximum:
            raise ValueError("suggestion text")
    generated = value["generated_at"]
    if type(generated) is not str or len(generated) > 40:
        raise ValueError("suggestion time")
    timestamp = datetime.fromisoformat(generated)
    if timestamp.tzinfo is None or timestamp.astimezone(UTC).isoformat() != generated:
        raise ValueError("suggestion time")
    # Local import avoids duplicating the existing normalized Draft item contracts.
    from .draft_scope import DraftDefect, DraftObservation, DraftOpening, DraftService

    models: dict[str, type[BaseModel]] = {
        "defect": DraftDefect,
        "opening": DraftOpening,
        "service": DraftService,
        "observation": DraftObservation,
    }
    item = value["proposed_item"]
    if target_kind not in models or type(item) is not dict:
        raise ValueError("suggestion target")
    normalized = models[target_kind].model_validate(item).model_dump(mode="json")
    if normalized != item or item["id"] != target_id:
        raise ValueError("suggestion item")
    if target_kind != "defect" and item["state"] not in ("Inferred", "Unresolved"):
        raise ValueError("suggestion authority")
    if target_kind == "opening" and any(item[key] is not None for key in ("width_mm", "height_mm")):
        raise ValueError("suggestion dimensions")
    if target_kind == "service" and item["quantity"] is not None:
        raise ValueError("suggestion quantity")


def reference_target(ref: dict[str, Any], content: dict[str, Any]) -> dict[str, Any] | None:
    collection = SUGGESTION_TARGET_COLLECTIONS.get(ref.get("target_kind", ""), "observations")
    target_id = ref.get("target_id", ref.get("observation_id"))
    return next((item for item in content.get(collection, []) if item["id"] == target_id), None)


def reference_changed(ref: dict[str, Any], content: dict[str, Any]) -> bool:
    target = reference_target(ref, content)
    return target is None or observation_hash(target) != ref.get(
        "target_sha256", ref.get("observation_sha256")
    )


def reference_label(ref: dict[str, Any], content: dict[str, Any]) -> str:
    target = reference_target(ref, content)
    kind = ref.get("target_kind", "observation").capitalize()
    identity = ref.get("target_id", ref.get("observation_id"))
    return f"{kind}: {target.get('label', identity) if target else identity}"


def reference_identity(ref: dict[str, Any]) -> tuple[str, str, str, int | str]:
    return (
        ref.get("target_kind", "observation"),
        ref.get("target_id", ref.get("observation_id", "")),
        ref["source_id"],
        f"xlsx:{ref['row']['sheet_index']}:{ref['row']['row']}"
        if ref.get("source_kind") == "xlsx"
        else ref["page_number"],
    )


def validate_evidence_refs(envelope: dict[str, Any]) -> None:
    refs = envelope["evidence_refs"]
    if type(refs) is not list or len(refs) > MAX_EVIDENCE_REFS:
        raise ValueError("evidence")
    observations = {item["id"] for item in envelope["content"]["observations"]}
    seen = set()
    for ref in refs:
        if type(ref) is not dict:
            raise ValueError("evidence")
        entity = "target_kind" in ref
        xlsx = ref.get("source_kind") == "xlsx"
        assisted = "suggestion" in ref
        expected_keys = XLSX_REF_KEYS if xlsx else ENTITY_REF_KEYS if entity else REF_KEYS
        if assisted:
            if (
                envelope["schema_version"] != SUGGESTION_EVIDENCE_SCHEMA_VERSION
                or not entity
                or xlsx
            ):
                raise ValueError("suggestion evidence version")
            expected_keys = expected_keys | {"suggestion"}
        if set(ref) != expected_keys:
            raise ValueError("evidence")
        if entity:
            if (
                envelope["schema_version"] not in ENTITY_EVIDENCE_SCHEMAS
                or type(ref["target_kind"]) is not str
                or ref["target_kind"]
                not in (SUGGESTION_TARGET_COLLECTIONS if assisted else TARGET_COLLECTIONS)
            ):
                raise ValueError("evidence target kind")
            target_key, hash_key = "target_id", "target_sha256"
            if assisted:
                validate_suggestion_claim(
                    ref["suggestion"], target_kind=ref["target_kind"], target_id=ref[target_key]
                )
        else:
            target_key, hash_key = "observation_id", "observation_sha256"
            if ref[target_key] not in observations:
                raise ValueError("evidence target")
        for key in (target_key, "source_id", "reviewed_by"):
            if type(ref[key]) is not str or str(UUID(ref[key])) != ref[key]:
                raise ValueError("evidence identity")
        if xlsx:
            from .draft_scope_xlsx_contract import validate_row
            from .draft_xlsx_image_contract import validate_image_descriptor

            if envelope["schema_version"] not in WORKBOOK_EVIDENCE_SCHEMAS or not entity:
                raise ValueError("workbook evidence version")
            validate_row(ref["row"])
            if type(ref["images"]) is not list or len(ref["images"]) > 50:
                raise ValueError("workbook image claims")
            image_ids = set()
            for image in ref["images"]:
                validate_image_descriptor(image)
                if image["occurrence_id"] in image_ids:
                    raise ValueError("duplicate workbook image")
                image_ids.add(image["occurrence_id"])
        identity = reference_identity(ref)
        if identity in seen:
            raise ValueError("duplicate evidence")
        seen.add(identity)
        for key in (
            hash_key,
            "source_sha256",
            *(("page_text_sha256",) if not xlsx else ()),
            "document_sha256",
            "scan_sha256",
        ):
            if type(ref[key]) is not str or not re.fullmatch(r"[0-9a-f]{64}", ref[key]):
                raise ValueError("evidence hash")
        if (
            type(ref["source_size_bytes"]) is not int
            or not 1 <= ref["source_size_bytes"] <= 10485760
            or (
                not xlsx
                and (type(ref["page_number"]) is not int or not 1 <= ref["page_number"] <= 50)
            )
        ):
            raise ValueError("evidence range")
        for key in ("original_filename", *(("locator_key",) if not xlsx else ())):
            if type(ref[key]) is not str or not 1 <= len(ref[key]) <= 200:
                raise ValueError("evidence label")
        expected_method = (
            "human_xlsx_row_entity_review"
            if xlsx
            else "human_page_entity_review"
            if entity
            else "human_page_review"
        )
        if ref["method"] != expected_method or ref["origin"] not in (
            "local_retained",
            "imported_unverified",
        ):
            raise ValueError("evidence authority")
        if type(ref["reviewed_at"]) is not str or len(ref["reviewed_at"]) > 40:
            raise ValueError("evidence time")
        created = datetime.fromisoformat(ref["reviewed_at"])
        if created.tzinfo is None or created.astimezone(UTC).isoformat() != ref["reviewed_at"]:
            raise ValueError("evidence time")


def reference_status(
    ref: dict[str, Any], observations_or_content: list[dict[str, Any]] | dict[str, Any]
) -> str:
    content = (
        {"observations": observations_or_content}
        if isinstance(observations_or_content, list)
        else observations_or_content
    )
    if ref["origin"] != "local_retained":
        return "Imported source and review claims are unverified"
    if "suggestion" in ref:
        if reference_target(ref, content) is None:
            return "Item removed since AI-assisted page review; original suggestion retained"
        if reference_changed(ref, content):
            return (
                "Item changed since AI-assisted page review; "
                "original suggestion retained; review again"
            )
        return (
            "AI suggestion edited/reviewed by a human against this page; "
            "no technical or physical approval"
        )
    if ref.get("source_kind") == "xlsx":
        if reference_target(ref, content) is None:
            return "Item removed since workbook review; historical source reference retained"
        if reference_changed(ref, content):
            return "Item changed since workbook review; review again"
        return (
            "Item reviewed against selected workbook cells/images; "
            "no technical or physical approval"
        )
    if "target_kind" in ref:
        if reference_target(ref, content) is None:
            return "Item removed since page review; historical page reference retained"
        if reference_changed(ref, content):
            return "Item changed since page review; review again"
        return "Item reviewed against this page; no technical or physical approval"
    if reference_changed(ref, content):
        return "Observation changed since page review; review again"
    return "Page reviewed for this Draft observation; no technical or physical approval"
