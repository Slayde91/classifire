"""Explicit unverified origin for locally editable imported Draft artifacts."""

from __future__ import annotations

import copy
import hashlib
from typing import Any
from uuid import UUID

from .draft_scope import _json, _valid_hash

VERSIONS = {
    "match": (
        "CLASSIFIRE-DRAFT-SYSTEM-MATCH-v4",
        tuple(f"CLASSIFIRE-DRAFT-SYSTEM-MATCH-v{i}" for i in (1, 2, 3)),
    ),
    "estimate": (
        "CLASSIFIRE-DRAFT-ESTIMATE-v3",
        tuple(f"CLASSIFIRE-DRAFT-ESTIMATE-v{i}" for i in (1, 2)),
    ),
}
ORIGIN_KEYS = {
    "schema_version",
    "import_id",
    "archive_sha256",
    "source_schema_version",
    "source_artifact_id",
    "source_revision",
    "source_sha256",
    "source_file_sha256",
    "authority",
}


def checksum(value: dict[str, Any]) -> str:
    return hashlib.sha256(_json({k: v for k, v in value.items() if k != "sha256"})).hexdigest()


def imported(value: dict[str, Any]) -> bool:
    return "import_origin" in value


def content_schema(value: dict[str, Any]) -> str:
    version = value.get("content_schema_version", value["schema_version"])
    if not isinstance(version, str):
        raise ValueError("content schema")
    return version


def origin_for(import_id: str, archive_hash: str, source: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "CLASSIFIRE-IMPORTED-ORIGIN-v1",
        "import_id": import_id,
        "archive_sha256": archive_hash,
        "source_schema_version": source["schema_version"],
        "source_artifact_id": source["artifact_id"],
        "source_revision": source["revision"],
        "source_sha256": source["sha256"],
        "source_file_sha256": hashlib.sha256(_json(source)).hexdigest(),
        "authority": "foreign_unverified",
    }


def wrap(value: dict[str, Any], kind: str, origin: dict[str, Any], base: str) -> dict[str, Any]:
    value = copy.deepcopy(value)
    value.update(
        schema_version=VERSIONS[kind][0],
        content_schema_version=base,
        provenance="package_import",
        import_origin=copy.deepcopy(origin),
    )
    value["sha256"] = checksum(value)
    return value


def native_projection(value: dict[str, Any], kind: str) -> dict[str, Any]:
    """Validate wrapper, then project only for the unchanged native content validator."""
    current, supported = VERSIONS[kind]
    origin = value["import_origin"]
    if (
        value["schema_version"] != current
        or value["provenance"] != "package_import"
        or value["content_schema_version"] not in supported
        or type(origin) is not dict
        or set(origin) != ORIGIN_KEYS
        or origin["schema_version"] != "CLASSIFIRE-IMPORTED-ORIGIN-v1"
        or origin["authority"] != "foreign_unverified"
        or origin["source_schema_version"] not in (*supported, current)
        or type(origin["source_revision"]) is not int
        or not 1 <= origin["source_revision"] <= 2147483647
        or any(
            not _valid_hash(origin[k])
            for k in ("archive_sha256", "source_sha256", "source_file_sha256")
        )
        or value["sha256"] != checksum(value)
    ):
        raise ValueError("import origin")
    for key in ("import_id", "source_artifact_id"):
        if type(origin[key]) is not str or str(UUID(origin[key])) != origin[key]:
            raise ValueError("import identity")
    native = copy.deepcopy(value)
    native.pop("import_origin")
    native["schema_version"] = native.pop("content_schema_version")
    native["provenance"] = (
        "manual_review"
        if kind == "match"
        else "manual_and_workbook_unit_sell"
        if native["schema_version"].endswith("v2")
        else "manual_unit_sell"
    )
    native["sha256"] = checksum(native)
    return native
