"""Untrusted selected-package inspection; no persistence, extraction or authority.

This is the semantic preview boundary for future transactional import. Binary report
members are inventoried and hash checked, never opened, rendered or made downloadable.
Their safety and agreement with a report snapshot are NOT established by this check.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..models import User
from . import draft_estimate_contract as estimate_contract
from . import draft_estimate_reports as estimate_reports
from . import draft_project_packages as packages
from . import draft_scope as scopes
from . import draft_scope_reports as scope_reports
from . import draft_system_match_contract as match_contract

Identity = Annotated[str, Field(min_length=1, max_length=36)]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Project(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: Identity
    reference: Annotated[str, Field(min_length=1, max_length=100)]
    name: Annotated[str, Field(min_length=1, max_length=300)]


class Member(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: Annotated[str, Field(max_length=100)]
    sha256: Hash
    size_bytes: Annotated[int, Field(ge=1, le=packages.MAX_ARCHIVE)]


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["CLASSIFIRE-DRAFT-PROJECT-PACKAGE-v1"]
    state: Literal["Draft"]
    authority: Literal["historical_only"]
    project: Project
    draft_scope_id: Identity
    package_id: str
    revision: Annotated[int, Field(ge=1, le=2147483647)]
    parent_hash: Hash | None
    created_by: Identity
    created_at: Annotated[str, Field(max_length=40)]
    selection: packages.Selection
    notice: Annotated[str, Field(max_length=2000)]
    capabilities: dict[str, str]
    source_manifest: Annotated[list[dict[str, str]], Field(max_length=2048)]
    members: Annotated[list[Member], Field(min_length=1, max_length=packages.MAX_MEMBERS - 1)]


@dataclass(frozen=True)
class InspectedPackage:
    manifest: dict[str, Any]
    members: dict[str, bytes]
    scope: dict[str, Any]
    match: dict[str, Any] | None
    estimate: dict[str, Any] | None
    reports: list[dict[str, Any]]
    archive_sha256: str


def _json(content: bytes, limit: int) -> dict[str, Any]:
    if not 1 <= len(content) <= limit:
        raise ValueError("size")
    value = json.loads(
        content.decode("utf-8"),
        object_pairs_hook=scopes._unique_json_object,
        parse_constant=scopes._reject_json_constant,
    )
    if type(value) is not dict or packages.encode(value) != content:
        raise ValueError("canonical object")
    return value


def inspect_package(content: bytes) -> InspectedPackage:
    """Validate every declared JSON artifact and its exact selected dependency graph.

    Hashes prove consistency with this input, never authenticity, clean binaries,
    local access, technical applicability, approval or complete historical coverage.
    """
    try:
        manifest, members = packages.inspect_archive(content)
        parsed = Manifest.model_validate(manifest)
        if parsed.model_dump(mode="json") != manifest:
            raise ValueError("manifest normalization")
        if str(UUID(parsed.package_id)) != parsed.package_id:
            raise ValueError("package identity")
        scope_reports._utc_text(parsed.created_at)
        if (parsed.revision == 1) != (parsed.parent_hash is None):
            raise ValueError("package parent")
        selected = parsed.selection
        if set(selected.scope_reports) & set(selected.estimate_reports):
            raise ValueError("duplicate report selection")
        wanted = {"artifacts/scope.json"}
        if selected.match_id:
            wanted.add("artifacts/system-match.json")
        if selected.estimate_id:
            wanted.add("artifacts/estimate.json")
        for report_id in selected.scope_reports + selected.estimate_reports:
            wanted.update(f"reports/{report_id}.{fmt}" for fmt in ("json", "pdf", "xlsx"))
        if set(members) != wanted or [m.path for m in parsed.members] != sorted(wanted):
            raise ValueError("selected membership")
        expected_capabilities = {
            "scope": "included",
            "system_match": "included" if selected.match_id else "not_selected",
            "estimate": "included" if selected.estimate_id else "not_selected",
            "reports": "included"
            if selected.scope_reports or selected.estimate_reports
            else "not_selected",
        }
        if parsed.capabilities != expected_capabilities:
            raise ValueError("capability claims")
        scope = scopes.validate_portable_artifact(members["artifacts/scope.json"])
        if (
            packages.encode(scope) != members["artifacts/scope.json"]
            or scope["artifact_id"] != parsed.draft_scope_id
            or scope["project_id"] != parsed.project.id
            or scope["revision"] != selected.scope_revision
        ):
            raise ValueError("scope selection")
        match = None
        if selected.match_id:
            match = _json(members["artifacts/system-match.json"], match_contract.MAX_MATCH_BYTES)
            match_contract.validate_envelope(match)
            if (
                match["artifact_id"] != selected.match_id
                or match["revision"] != selected.match_revision
                or match["scope"] != scope
            ):
                raise ValueError("review dependency")
        estimate = None
        if selected.estimate_id:
            estimate = _json(
                members["artifacts/estimate.json"], estimate_contract.MAX_ESTIMATE_BYTES
            )
            estimate_contract.validate_envelope(estimate)
            if (
                estimate["artifact_id"] != selected.estimate_id
                or estimate["revision"] != selected.estimate_revision
                or estimate["scope"] != scope
                or estimate["system_match"] != match
            ):
                raise ValueError("estimate dependency")
        if parsed.source_manifest != packages.source_manifest(scope, match, estimate):
            raise ValueError("source inventory")
        reports = []
        for report_id in selected.scope_reports + selected.estimate_reports:
            is_estimate = report_id in selected.estimate_reports
            limit = (
                estimate_reports.MAX_REPORT_SNAPSHOT_BYTES
                if is_estimate
                else scope_reports.MAX_REPORT_SNAPSHOT_BYTES
            )
            snapshot = _json(members[f"reports/{report_id}.json"], limit)
            if is_estimate:
                estimate_reports.validate_report_snapshot(snapshot)
                if snapshot["estimate"] != estimate:
                    raise ValueError("report estimate")
            else:
                scope_reports.validate_report_snapshot(snapshot)
                if snapshot["scope"] != scope or (
                    snapshot.get("system_match") is not None and snapshot["system_match"] != match
                ):
                    raise ValueError("report scope/review")
            # Labels can describe an earlier project-name revision; IDs must agree.
            if snapshot["report_id"] != report_id or snapshot["project"]["id"] != parsed.project.id:
                raise ValueError("report identity")
            for fmt in ("pdf", "xlsx"):
                scope_reports._output(members[f"reports/{report_id}.{fmt}"], fmt)
            reports.append(snapshot)
        return InspectedPackage(
            manifest, members, scope, match, estimate, reports, packages.digest(content)
        )
    except packages.PackageError:
        raise
    except (
        scopes.DraftScopeError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        RecursionError,
        ArithmeticError,
        UnicodeError,
    ) as exc:
        raise packages.PackageError("PACKAGE_CONTENT_INVALID", 422) from exc


def preview_import(db: Session, actor: User, content: bytes) -> dict[str, Any]:
    """Authorized read-only inspection; does not create a project or confer authority."""
    with db.no_autoflush:
        actor = scopes._actor(db, actor, "project:write")
        actor = scopes._actor(db, actor, "project:read")
        inspected = inspect_package(content)
        if inspected.match:
            actor = scopes._actor(db, actor, "technical:read")
        if inspected.estimate:
            actor = scopes._actor(db, actor, "estimate:read")
            if inspected.estimate.get("pricing_sources"):
                actor = scopes._actor(db, actor, "library:read")
        return {
            "manifest": inspected.manifest,
            "archive_sha256": inspected.archive_sha256,
            "scope_counts": scopes._content_counts(inspected.scope["content"]),
            "scope_findings": scopes.validate_payload(inspected.scope["content"])[1],
            "match_candidates": len(inspected.match["candidates"]) if inspected.match else 0,
            "estimate_lines": len(inspected.estimate["lines"]) if inspected.estimate else 0,
            "reports": [
                {"report_id": r["report_id"], "profile": r["profile"]} for r in inspected.reports
            ],
            "source_count": len(inspected.manifest["source_manifest"]),
            "import_available": False,
            "binary_status": "not_scanned_or_opened",
            "authority": "foreign_unverified",
        }
