"""Portable page-reference claims; local authority is checked by intake services."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

EVIDENCE_SCHEMA_VERSION = "CLASSIFIRE-DRAFT-SCOPE-v3"
ENTITY_EVIDENCE_SCHEMA_VERSION = "CLASSIFIRE-DRAFT-SCOPE-v4"
EVIDENCE_SCHEMAS = (EVIDENCE_SCHEMA_VERSION, ENTITY_EVIDENCE_SCHEMA_VERSION)
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
TARGET_COLLECTIONS = {"defect": "defects", "opening": "openings", "service": "services"}


def reference_target(ref: dict[str, Any], content: dict[str, Any]) -> dict[str, Any] | None:
    collection = TARGET_COLLECTIONS.get(ref.get("target_kind", ""), "observations")
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


def reference_identity(ref: dict[str, Any]) -> tuple[str, str, str, int]:
    return (
        ref.get("target_kind", "observation"),
        ref.get("target_id", ref.get("observation_id", "")),
        ref["source_id"],
        ref["page_number"],
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
        expected_keys = ENTITY_REF_KEYS if entity else REF_KEYS
        if set(ref) != expected_keys:
            raise ValueError("evidence")
        if entity:
            if (
                envelope["schema_version"] != ENTITY_EVIDENCE_SCHEMA_VERSION
                or type(ref["target_kind"]) is not str
                or ref["target_kind"] not in TARGET_COLLECTIONS
            ):
                raise ValueError("evidence target kind")
            target_key, hash_key = "target_id", "target_sha256"
        else:
            target_key, hash_key = "observation_id", "observation_sha256"
            if ref[target_key] not in observations:
                raise ValueError("evidence target")
        for key in (target_key, "source_id", "reviewed_by"):
            if type(ref[key]) is not str or str(UUID(ref[key])) != ref[key]:
                raise ValueError("evidence identity")
        identity = reference_identity(ref)
        if identity in seen:
            raise ValueError("duplicate evidence")
        seen.add(identity)
        for key in (
            hash_key,
            "source_sha256",
            "page_text_sha256",
            "document_sha256",
            "scan_sha256",
        ):
            if type(ref[key]) is not str or not re.fullmatch(r"[0-9a-f]{64}", ref[key]):
                raise ValueError("evidence hash")
        if (
            type(ref["source_size_bytes"]) is not int
            or not 1 <= ref["source_size_bytes"] <= 10485760
            or type(ref["page_number"]) is not int
            or not 1 <= ref["page_number"] <= 50
        ):
            raise ValueError("evidence range")
        for key in ("original_filename", "locator_key"):
            if type(ref[key]) is not str or not 1 <= len(ref[key]) <= 200:
                raise ValueError("evidence label")
        expected_method = "human_page_entity_review" if entity else "human_page_review"
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
    if "target_kind" in ref:
        if reference_target(ref, content) is None:
            return "Item removed since page review; historical page reference retained"
        if reference_changed(ref, content):
            return "Item changed since page review; review again"
        return "Item reviewed against this page; no technical or physical approval"
    if reference_changed(ref, content):
        return "Observation changed since page review; review again"
    return "Page reviewed for this Draft observation; no technical or physical approval"
