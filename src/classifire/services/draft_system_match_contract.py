"""Bounded, source-preserving contract for unapproved candidate review artifacts."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .draft_constraint_review import validate_review
from .draft_scope import _envelope_shape, _valid_hash, validate_payload
from .technical_field_snapshot import FIELD_NAMES as FIELD_NAMES

SCHEMA_VERSION = "CLASSIFIRE-DRAFT-SYSTEM-MATCH-v1"
MAX_MATCH_BYTES = 1024 * 1024
MAX_CANDIDATES = 20
MAX_SOURCE_BYTES = 64 * 1024 * 1024
COMPARISON_NAMES = ("service_type", "service_material", "substrate", "orientation", "frl")
MANIFEST_FIELDS = (
    "id",
    "key",
    "variant_id",
    "system_id",
    "frl",
    "source_document_reference",
    "source_page",
    "source_hash",
    "record_version",
    "source_binding",
)
Identity = Annotated[str, Field(min_length=1, max_length=36)]
Short = Annotated[str, Field(max_length=500)]
Code = Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_]+$")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Decision(Contract):
    candidate_id: Identity
    decision: Literal["unreviewed", "keep", "reject"]
    notes: Annotated[str, Field(max_length=4000)]


class Release(Contract):
    id: Identity
    version: Annotated[str, Field(min_length=1, max_length=50)]
    sha256: Digest
    effective_date: Annotated[str, Field(max_length=10)] | None


class Target(Contract):
    opening_id: Identity | None
    service_id: Identity | None
    opening_ids: Annotated[list[Identity], Field(max_length=500)]
    service_ids: Annotated[list[Identity], Field(max_length=500)]
    blank_opening: bool
    not_assessed_opening_ids: Annotated[list[Identity], Field(max_length=500)]
    not_assessed_service_ids: Annotated[list[Identity], Field(max_length=500)]


class Retrieval(Contract):
    version: Literal[1]
    inputs: dict[str, Short | None]
    missing_criteria: Annotated[list[Code], Field(max_length=40)]
    unassessed_criteria: Annotated[list[Code], Field(max_length=40)]
    truncated: bool
    candidate_limit: Literal[20]
    evaluated_at: Annotated[str, Field(max_length=40)]


class Source(Contract):
    variant_source_hash: Short | None
    state: Literal["bound", "legacy_unbound", "manifest_unbound"]
    binding: dict[str, Any] | None
    verified_at: Annotated[str, Field(max_length=40)] | None
    verification: Literal["exact_bytes", "unresolved"]


class Candidate(Contract):
    candidate_id: Identity
    variant_id: Annotated[str, Field(min_length=1, max_length=300)]
    system_id: Annotated[str, Field(min_length=1, max_length=300)]
    record_version: Annotated[int, Field(ge=1)]
    fields: dict[str, str | bool | None]
    fields_sha256: Digest
    release_record: dict[str, Any]
    source: Source
    score: Annotated[str, Field(max_length=100)]
    comparisons: dict[str, Literal["MATCH", "MISMATCH", "UNKNOWN"]]
    blockers: Annotated[list[Code], Field(max_length=40)]


class Envelope(Contract):
    schema_version: Literal["CLASSIFIRE-DRAFT-SYSTEM-MATCH-v1"]
    artifact_id: Identity
    project_id: Identity
    revision: Annotated[int, Field(ge=1, le=2_147_483_647)]
    parent_hash: Digest | None
    created_by: Identity
    created_at: Annotated[str, Field(max_length=40)]
    state: Literal["Draft"]
    review_status: Literal["unreviewed"]
    provenance: Literal["manual_review"]
    coverage: Literal["selected_target_only"]
    scope: dict[str, Any]
    release: Release
    target: Target
    retrieval: Retrieval
    candidates: Annotated[list[Candidate], Field(max_length=MAX_CANDIDATES)]
    decisions: Annotated[list[Decision], Field(max_length=MAX_CANDIDATES)]
    sha256: Digest


class ConstraintEnvelope(Envelope):
    schema_version: Literal["CLASSIFIRE-DRAFT-SYSTEM-MATCH-v2"]  # type: ignore[assignment]
    constraint_review: dict[str, Any]


class ServiceSizeEnvelope(ConstraintEnvelope):
    schema_version: Literal["CLASSIFIRE-DRAFT-SYSTEM-MATCH-v3"]  # type: ignore[assignment]


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def envelope_hash(value: dict[str, Any]) -> str:
    return digest({key: item for key, item in value.items() if key != "sha256"})


def basis_hash(value: dict[str, Any]) -> str:
    return digest(
        {key: value[key] for key in ("scope", "release", "target", "retrieval", "candidates")}
    )


def timestamp(value: str) -> None:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.astimezone(UTC).isoformat() != value:
        raise ValueError("timestamp")


def validate_binding(value: Any) -> None:
    if type(value) is not dict or value.get("schema") != "technical-release-source-binding-v1":
        raise ValueError("binding")
    state = value.get("state")
    keys = {"schema", "state", "source_locator"}
    if state == "bound":
        keys.add("technical_document")
    elif state != "legacy_unbound":
        raise ValueError("binding")
    if set(value) != keys:
        raise ValueError("binding")
    locator = value["source_locator"]
    if type(locator) is not dict or set(locator) != {
        "document_reference",
        "page",
        "table",
        "figure",
    }:
        raise ValueError("locator")
    for item in locator.values():
        if item is not None and (type(item) is not str or len(item) > 500):
            raise ValueError("locator")
    if state == "bound":
        document = value["technical_document"]
        if type(document) is not dict or set(document) != {
            "id",
            "document_id",
            "reference",
            "revision",
            "stored_file",
        }:
            raise ValueError("document")
        for key in ("id", "document_id", "reference", "revision"):
            item = document[key]
            if item is not None and (type(item) is not str or len(item) > 500):
                raise ValueError("document")
        stored = document["stored_file"]
        if type(stored) is not dict or set(stored) != {"id", "sha256", "size_bytes"}:
            raise ValueError("file")
        if (
            not document["id"]
            or not document["document_id"]
            or type(stored["id"]) is not str
            or not 1 <= len(stored["id"]) <= 36
        ):
            raise ValueError("file")
        if (
            not _valid_hash(stored["sha256"])
            or type(stored["size_bytes"]) is not int
            or not 1 <= stored["size_bytes"] <= MAX_SOURCE_BYTES
        ):
            raise ValueError("file")


def target_for(
    scope: dict[str, Any], opening_id: str | None, service_id: str | None
) -> dict[str, Any]:
    openings = {item["id"]: item for item in scope["content"]["openings"]}
    services = {item["id"]: item for item in scope["content"]["services"]}
    if opening_id is None and service_id is None:
        raise ValueError("target")
    if (opening_id is not None and opening_id not in openings) or (
        service_id is not None and service_id not in services
    ):
        raise ValueError("target")
    if (
        opening_id is not None
        and service_id is not None
        and opening_id not in services[service_id]["opening_ids"]
    ):
        raise ValueError("target_link")
    opening_ids = [opening_id] if opening_id else sorted(services[service_id]["opening_ids"])
    service_ids = (
        [service_id]
        if service_id
        else sorted(key for key, item in services.items() if opening_id in item["opening_ids"])
    )
    return {
        "opening_id": opening_id,
        "service_id": service_id,
        "opening_ids": opening_ids,
        "service_ids": service_ids,
        "blank_opening": bool(opening_id and openings[opening_id]["blank"]),
        "not_assessed_opening_ids": sorted(set(openings) - ({opening_id} if opening_id else set())),
        "not_assessed_service_ids": sorted(set(services) - ({service_id} if service_id else set())),
    }


def validate_envelope(value: dict[str, Any]) -> None:
    from .draft_import_origin import VERSIONS, native_projection

    if value.get("schema_version") == VERSIONS["match"][0]:
        if len(canonical(value)) > MAX_MATCH_BYTES:
            raise ValueError("size")
        validate_envelope(native_projection(value, "match"))
        return
    if len(canonical(value)) > MAX_MATCH_BYTES:
        raise ValueError("size")
    model: type[Envelope] = Envelope
    if value.get("schema_version") == "CLASSIFIRE-DRAFT-SYSTEM-MATCH-v3":
        model = ServiceSizeEnvelope
    elif value.get("schema_version") == "CLASSIFIRE-DRAFT-SYSTEM-MATCH-v2":
        model = ConstraintEnvelope
    parsed = model.model_validate(value)
    if "constraint_review" in value:
        validate_review(
            value["constraint_review"],
            value["candidates"],
            value["target"],
            service_size=value["schema_version"] == "CLASSIFIRE-DRAFT-SYSTEM-MATCH-v3",
        )
        timestamp(value["constraint_review"]["reviewed_at"])
    if (
        parsed.model_dump(mode="json") != value
        or type(value["retrieval"]["version"]) is not int
        or type(value["retrieval"]["candidate_limit"]) is not int
    ):
        raise ValueError("normalization")
    if str(UUID(value["artifact_id"])) != value["artifact_id"]:
        raise ValueError("identity")
    timestamp(value["created_at"])
    timestamp(value["retrieval"]["evaluated_at"])
    if (value["revision"] == 1) != (value["parent_hash"] is None):
        raise ValueError("parent")
    scope = value["scope"]
    _envelope_shape(scope)
    content, _ = validate_payload(scope["content"])
    if (
        content.model_dump(mode="json") != scope["content"]
        or envelope_hash(scope) != scope["sha256"]
        or scope["project_id"] != value["project_id"]
    ):
        raise ValueError("scope")
    if value["target"] != target_for(
        scope, value["target"]["opening_id"], value["target"]["service_id"]
    ):
        raise ValueError("target")
    if set(value["retrieval"]["inputs"]) != set(COMPARISON_NAMES):
        raise ValueError("inputs")
    candidate_ids = [item["candidate_id"] for item in value["candidates"]]
    if (
        len(set(candidate_ids)) != len(candidate_ids)
        or [item["candidate_id"] for item in value["decisions"]] != candidate_ids
    ):
        raise ValueError("decisions")
    for candidate in value["candidates"]:
        if not Decimal(candidate["score"]).is_finite() or set(candidate["comparisons"]) != set(
            COMPARISON_NAMES
        ):
            raise ValueError("score")
        fields = candidate["fields"]
        if set(fields) != set(FIELD_NAMES) or type(fields["expert_review_required"]) is not bool:
            raise ValueError("fields")
        for key, item in fields.items():
            if (
                key != "expert_review_required"
                and item is not None
                and (type(item) is not str or len(item) > 16000)
            ):
                raise ValueError("fields")
        if digest(fields) != candidate["fields_sha256"]:
            raise ValueError("fields_hash")
        record = candidate["release_record"]
        if (
            type(record) is not dict
            or set(record) - set(MANIFEST_FIELDS)
            or record.get("id") != candidate["candidate_id"]
        ):
            raise ValueError("record")
        for key, item in record.items():
            if key == "source_binding":
                validate_binding(item)
            elif key == "record_version":
                if type(item) is not int or item < 1:
                    raise ValueError("record")
            elif item is not None and (type(item) is not str or len(item) > 500):
                raise ValueError("record")
        source = candidate["source"]
        if source["binding"] is not None:
            validate_binding(source["binding"])
        if source["state"] == "bound":
            if (
                source["verification"] != "exact_bytes"
                or source["verified_at"] is None
                or source["binding"] is None
                or source["binding"]["state"] != "bound"
                or record.get("source_binding") != source["binding"]
            ):
                raise ValueError("source")
            timestamp(source["verified_at"])
        elif source["verification"] != "unresolved" or source["verified_at"] is not None:
            raise ValueError("source")
    if envelope_hash(value) != value["sha256"]:
        raise ValueError("checksum")
