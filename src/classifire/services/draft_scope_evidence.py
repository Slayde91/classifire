"""Portable page-reference claims; local authority is checked by intake services."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

EVIDENCE_SCHEMA_VERSION = "CLASSIFIRE-DRAFT-SCOPE-v3"
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


def validate_evidence_refs(envelope: dict[str, Any]) -> None:
    refs = envelope["evidence_refs"]
    if type(refs) is not list or len(refs) > MAX_EVIDENCE_REFS:
        raise ValueError("evidence")
    observations = {item["id"] for item in envelope["content"]["observations"]}
    seen = set()
    for ref in refs:
        if type(ref) is not dict or set(ref) != REF_KEYS:
            raise ValueError("evidence")
        for key in ("observation_id", "source_id", "reviewed_by"):
            if type(ref[key]) is not str or str(UUID(ref[key])) != ref[key]:
                raise ValueError("evidence identity")
        if ref["observation_id"] not in observations:
            raise ValueError("evidence target")
        identity = (ref["observation_id"], ref["source_id"], ref["page_number"])
        if identity in seen:
            raise ValueError("duplicate evidence")
        seen.add(identity)
        for key in (
            "observation_sha256",
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
        if ref["method"] != "human_page_review" or ref["origin"] not in (
            "local_retained",
            "imported_unverified",
        ):
            raise ValueError("evidence authority")
        if type(ref["reviewed_at"]) is not str or len(ref["reviewed_at"]) > 40:
            raise ValueError("evidence time")
        created = datetime.fromisoformat(ref["reviewed_at"])
        if created.tzinfo is None or created.astimezone(UTC).isoformat() != ref["reviewed_at"]:
            raise ValueError("evidence time")


def reference_status(ref: dict[str, Any], observations: list[dict[str, Any]]) -> str:
    if ref["origin"] != "local_retained":
        return "Imported source and review claims are unverified"
    observation = next((item for item in observations if item["id"] == ref["observation_id"]), None)
    if observation is None or observation_hash(observation) != ref["observation_sha256"]:
        return "Observation changed since page review; review again"
    return "Page reviewed for this Draft observation; no technical or physical approval"
