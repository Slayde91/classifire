"""Untrusted selected-package inspection; no persistence, extraction or authority.

This is the semantic preview boundary for future transactional import. Binary report
members are inventoried and hash checked, never opened, rendered or made downloadable.
Their safety and agreement with a report snapshot are NOT established by this check.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
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


class OriginReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    import_id: str
    path: str
    sha256: Hash
    mapping: dict[str, Any]


class ManifestV2(Manifest):
    schema_version: Literal["CLASSIFIRE-DRAFT-PROJECT-PACKAGE-v2"]  # type: ignore[assignment]
    origins: Annotated[list[OriginReference], Field(min_length=1, max_length=1)]


class ManifestV3(ManifestV2):
    schema_version: Literal["CLASSIFIRE-DRAFT-PROJECT-PACKAGE-v3"]  # type: ignore[assignment]
    origins: Annotated[list[OriginReference], Field(max_length=1)] = Field(default_factory=list)


class ManifestV4(ManifestV3):
    schema_version: Literal["CLASSIFIRE-DRAFT-PROJECT-PACKAGE-v4"]  # type: ignore[assignment]


class ManifestV5(ManifestV4):
    schema_version: Literal["CLASSIFIRE-DRAFT-PROJECT-PACKAGE-v5"]  # type: ignore[assignment]


class ManifestV6(ManifestV5):
    schema_version: Literal["CLASSIFIRE-DRAFT-PROJECT-PACKAGE-v6"]  # type: ignore[assignment]


@dataclass(frozen=True)
class InspectedPackage:
    manifest: dict[str, Any]
    members: dict[str, bytes]
    scope: dict[str, Any]
    match: dict[str, Any] | None
    estimate: dict[str, Any] | None
    reports: list[dict[str, Any]]
    archive_sha256: str
    origins: dict[str, InspectedPackage] = field(default_factory=dict)
    matches: list[dict[str, Any]] = field(default_factory=list)

    def all_matches(self) -> list[dict[str, Any]]:
        return [self.match] if self.match is not None else self.matches

    def match_by_id(self, source_id: str) -> dict[str, Any] | None:
        return next((item for item in self.all_matches() if item["artifact_id"] == source_id), None)

    def walk(self):
        yield self
        for item in self.origins.values():
            yield from item.walk()

    def report_members(self, prefix: str = ""):
        for report in self.reports:
            yield (
                report,
                {fmt: prefix + f"reports/{report['report_id']}.{fmt}" for fmt in ("pdf", "xlsx")},
            )
        for path, item in self.origins.items():
            yield from item.report_members(prefix + path + "!")

    def evidence_members(self, prefix: str = ""):
        for source_id in self.manifest["selection"].get("pdf_sources", []):
            yield source_id, prefix + f"evidence/{source_id}.pdf"
        for source_id in self.manifest["selection"].get("xlsx_sources", []):
            yield source_id, prefix + f"evidence/{source_id}.xlsx"
        for source_id in self.manifest["selection"].get("docx_sources", []):
            yield source_id, prefix + f"evidence/{source_id}.docx"
        for path, item in self.origins.items():
            yield from item.evidence_members(prefix + path + "!")

    def resolve(self, path: str) -> bytes:
        if "!" not in path:
            return self.members[path]
        origin, nested = path.split("!", 1)
        return self.origins[origin].resolve(nested)


def match_mappings(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    """Read exact source/local bindings; legacy mappings keep their original shape."""
    return mapping.get("matches", []) or ([mapping["match"]] if mapping["match"] else [])


def report_match_mapping(
    report: dict[str, Any], paths: dict[str, str], mapping: dict[str, Any]
) -> dict[str, Any] | None:
    """Bind direct reports locally; ancestor-only reports retain source identity only."""
    source = (
        report["estimate"].get("system_match")
        if "estimate" in report
        else report.get("system_match")
    )
    if source is None:
        return None
    bound = None
    if "!" not in paths["pdf"]:
        bound = next(
            (
                item
                for item in match_mappings(mapping)
                if item["source_id"] == source["artifact_id"]
                and item["source_revision"] == source["revision"]
                and item["source_sha256"] == source["sha256"]
            ),
            None,
        )
        if bound is None:
            raise ValueError("report review mapping")
    return {
        "source_id": source["artifact_id"],
        "source_revision": source["revision"],
        "source_sha256": source["sha256"],
        "local_id": bound["local_id"] if bound is not None else None,
        "local_revision": bound["local_revision"] if bound is not None else None,
        "local_sha256": bound["local_sha256"] if bound is not None else None,
    }


def validate_origin_mapping(
    mapping: dict[str, Any], original: InspectedPackage, project_id: str, draft_id: str
) -> None:
    """Require a complete one-to-one retained origin inventory, including descendants."""
    evidence = list(original.evidence_members())
    collection = bool(original.matches)
    if set(mapping) != (
        {"schema_version", "project", "scope", "match", "estimate", "reports", "entity_ids"}
        | ({"evidence"} if evidence else set())
        | ({"matches"} if collection else set())
    ):
        raise ValueError("mapping fields")
    expected_version = (
        "CLASSIFIRE-IMPORT-MAPPING-v3"
        if collection
        else "CLASSIFIRE-IMPORT-MAPPING-v2"
        if evidence
        else "CLASSIFIRE-IMPORT-MAPPING-v1"
    )
    if (
        mapping["schema_version"] != expected_version
        or mapping["project"] != {"source_id": original.scope["project_id"], "local_id": project_id}
        or mapping["entity_ids"] != "retained_within_new_scope"
    ):
        raise ValueError("mapping project")
    artifact_bindings = [
        (kind, getattr(original, kind), mapping[kind]) for kind in ("scope", "match", "estimate")
    ]
    if collection:
        if type(mapping["matches"]) is not list or len(mapping["matches"]) != len(original.matches):
            raise ValueError("mapping review inventory")
        artifact_bindings.extend(
            ("match", source, bound)
            for source, bound in zip(original.matches, mapping["matches"], strict=True)
        )
    local_ids = []
    for kind, source, bound in artifact_bindings:
        if source is None:
            if bound is not None:
                raise ValueError("mapping unexpected artifact")
            continue
        if type(bound) is not dict or set(bound) != {
            "source_id",
            "source_revision",
            "source_sha256",
            "local_id",
            "local_revision",
            "local_sha256",
        }:
            raise ValueError("mapping artifact fields")
        for key, source_key in (
            ("source_id", "artifact_id"),
            ("source_revision", "revision"),
            ("source_sha256", "sha256"),
        ):
            if bound[key] != source[source_key]:
                raise ValueError("mapping source")
        if str(UUID(bound["local_id"])) != bound["local_id"]:
            raise ValueError("mapping local identity")
        local_ids.append(bound["local_id"])
        if (
            not scopes._valid_hash(bound["local_sha256"])
            or type(bound["local_revision"]) is not int
            or bound["local_revision"] != (2 if kind == "scope" else 1)
        ):
            raise ValueError("mapping local revision")
    if collection and len(local_ids) != len(set(local_ids)):
        raise ValueError("mapping duplicate local identity")
    if mapping["scope"]["local_id"] != draft_id:
        raise ValueError("mapping scope")
    expected = list(original.report_members())
    if type(mapping["reports"]) is not list or len(mapping["reports"]) != len(expected):
        raise ValueError("mapping report inventory")
    for record, (report, paths) in zip(mapping["reports"], expected, strict=True):
        if (
            set(record)
            != ({"source_report_id", "profile", "members"} | ({"match"} if collection else set()))
            or record["source_report_id"] != report["report_id"]
            or record["profile"] != report["profile"]
            or set(record["members"]) != {"pdf", "xlsx"}
        ):
            raise ValueError("mapping report")
        if collection and record["match"] != report_match_mapping(report, paths, mapping):
            raise ValueError("mapping report review")
        for fmt, member in record["members"].items():
            if (
                set(member) != {"source_id", "path", "sha256"}
                or member["path"] != paths[fmt]
                or member["sha256"] != packages.digest(original.resolve(paths[fmt]))
            ):
                raise ValueError("mapping report bytes")
            UUID(member["source_id"])

    if evidence:
        if type(mapping["evidence"]) is not list or len(mapping["evidence"]) != len(evidence):
            raise ValueError("mapping evidence inventory")
        for member, (source_id, path) in zip(mapping["evidence"], evidence, strict=True):
            if (
                set(member) != {"source_id", "original_source_id", "path", "sha256"}
                or member["original_source_id"] != source_id
                or member["path"] != path
                or member["sha256"] != packages.digest(original.resolve(path))
            ):
                raise ValueError("mapping evidence bytes")
            UUID(member["source_id"])


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


def inspect_package(
    content: bytes, *, _depth: int = 0, _budget: list[int] | None = None
) -> InspectedPackage:
    """Validate every declared JSON artifact and its exact selected dependency graph.

    Hashes prove consistency with this input, never authenticity, clean binaries,
    local access, technical applicability, approval or complete historical coverage.
    """
    try:
        if _budget is None:
            _budget = [packages.MAX_ARCHIVE * 2]
        _budget[0] -= len(content)
        if _depth >= 8 or _budget[0] < 0:
            raise ValueError("origin nesting bounds")
        manifest, members = packages.inspect_archive(content)
        parsed = (
            ManifestV6
            if manifest.get("schema_version") == packages.SCHEMA_V6
            else ManifestV5
            if manifest.get("schema_version") == packages.SCHEMA_V5
            else ManifestV4
            if manifest.get("schema_version") == packages.SCHEMA_V4
            else ManifestV3
            if manifest.get("schema_version") == packages.SCHEMA_V3
            else ManifestV2
            if manifest.get("schema_version") == packages.SCHEMA_V2
            else Manifest
        ).model_validate(manifest)
        origins = {}
        if isinstance(parsed, ManifestV2):
            for ref in parsed.origins:
                if (
                    str(UUID(ref.import_id)) != ref.import_id
                    or ref.path != f"origins/{ref.sha256}.zip"
                ):
                    raise ValueError("origin reference")
                raw = members[ref.path]
                if packages.digest(raw) != ref.sha256:
                    raise ValueError("origin archive hash")
                origins[ref.path] = inspect_package(raw, _depth=_depth + 1, _budget=_budget)
        if parsed.model_dump(mode="json") != manifest:
            raise ValueError("manifest normalization")
        if str(UUID(parsed.package_id)) != parsed.package_id:
            raise ValueError("package identity")
        scope_reports._utc_text(parsed.created_at)
        if (parsed.revision == 1) != (parsed.parent_hash is None):
            raise ValueError("package parent")
        selected = parsed.selection
        if bool(selected.matches) != isinstance(parsed, ManifestV6):
            raise ValueError("review collection version")
        if selected.docx_sources and not isinstance(parsed, ManifestV5):
            raise ValueError("legacy Word selection")
        if selected.xlsx_sources and not isinstance(parsed, ManifestV4):
            raise ValueError("legacy workbook selection")
        if selected.pdf_sources and not isinstance(parsed, ManifestV3):
            raise ValueError("legacy evidence selection")
        if set(selected.scope_reports) & set(selected.estimate_reports):
            raise ValueError("duplicate report selection")
        wanted = {"artifacts/scope.json", *origins}
        wanted.update(f"evidence/{sid}.pdf" for sid in selected.pdf_sources)
        wanted.update(f"evidence/{sid}.xlsx" for sid in selected.xlsx_sources)
        wanted.update(f"evidence/{sid}.docx" for sid in selected.docx_sources)
        if selected.match_id:
            wanted.add("artifacts/system-match.json")
        wanted.update(packages.match_member_path(ref.match_id) for ref in selected.matches)
        if selected.estimate_id:
            wanted.add("artifacts/estimate.json")
        for report_id in selected.scope_reports + selected.estimate_reports:
            wanted.update(f"reports/{report_id}.{fmt}" for fmt in ("json", "pdf", "xlsx"))
        if set(members) != wanted or [m.path for m in parsed.members] != sorted(wanted):
            raise ValueError("selected membership")
        expected_capabilities = {
            "scope": "included",
            "system_match": "included" if selected.match_id or selected.matches else "not_selected",
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
        matches = []
        for review_ref in selected.matches:
            value = _json(
                members[packages.match_member_path(review_ref.match_id)],
                match_contract.MAX_MATCH_BYTES,
            )
            match_contract.validate_envelope(value)
            if (
                value["artifact_id"] != review_ref.match_id
                or value["revision"] != review_ref.match_revision
            ):
                raise ValueError("review collection selection")
            matches.append(value)
        if matches:
            packages.validate_match_collection(scope, matches)

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
                or not packages.match_dependency_selected(estimate["system_match"], match, matches)
            ):
                raise ValueError("estimate dependency")
        for source_id in selected.pdf_sources:
            data = members[f"evidence/{source_id}.pdf"]
            refs = [
                ref for ref in scope.get("evidence_refs", []) if ref.get("source_id") == source_id
            ]
            if (
                not refs
                or not data.startswith(b"%PDF-")
                or any(
                    "page_number" not in ref
                    or ref.get("source_sha256") != packages.digest(data)
                    or ref.get("source_size_bytes") != len(data)
                    for ref in refs
                )
            ):
                raise ValueError("PDF evidence binding")
        for source_id in selected.xlsx_sources:
            data = members[f"evidence/{source_id}.xlsx"]
            refs = [
                ref for ref in scope.get("evidence_refs", []) if ref.get("source_id") == source_id
            ]
            if (
                not refs
                or not data.startswith(b"PK\x03\x04")
                or any(
                    ref.get("source_kind") != "xlsx"
                    or ref.get("source_sha256") != packages.digest(data)
                    or ref.get("source_size_bytes") != len(data)
                    for ref in refs
                )
            ):
                raise ValueError("XLSX evidence binding")
        for source_id in selected.docx_sources:
            data = members[f"evidence/{source_id}.docx"]
            refs = [
                ref for ref in scope.get("evidence_refs", []) if ref.get("source_id") == source_id
            ]
            if (
                not refs
                or not data.startswith(b"PK\x03\x04")
                or any(
                    ref.get("source_kind") != "docx"
                    or ref.get("source_sha256") != packages.digest(data)
                    or ref.get("source_size_bytes") != len(data)
                    for ref in refs
                )
            ):
                raise ValueError("DOCX evidence binding")
        if parsed.source_manifest != packages.source_manifest(
            scope,
            match,
            estimate,
            selected.pdf_sources,
            selected.xlsx_sources,
            selected.docx_sources,
            match_collection=matches or None,
        ):
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
                    snapshot.get("system_match") is not None
                    and not packages.match_dependency_selected(
                        snapshot["system_match"], match, matches
                    )
                ):
                    raise ValueError("report scope/review")
            # Labels can describe an earlier project-name revision; IDs must agree.
            if snapshot["report_id"] != report_id or snapshot["project"]["id"] != parsed.project.id:
                raise ValueError("report identity")
            for fmt in ("pdf", "xlsx"):
                scope_reports._output(members[f"reports/{report_id}.{fmt}"], fmt)
            reports.append(snapshot)
        from .draft_import_origin import origin_for

        refs = parsed.origins if isinstance(parsed, ManifestV2) else []
        for kind, artifact in [
            *(("match", item) for item in ([match] if match is not None else matches)),
            ("estimate", estimate),
        ]:
            if artifact is not None and "import_origin" in artifact:
                origin = artifact["import_origin"]
                bound_ref = next((r for r in refs if r.import_id == origin["import_id"]), None)
                if bound_ref is None:
                    raise ValueError("missing original archive")
                original = origins[bound_ref.path]
                source = (
                    original.match_by_id(origin["source_artifact_id"])
                    if kind == "match"
                    else original.estimate
                )
                if source is None or origin != origin_for(
                    bound_ref.import_id, bound_ref.sha256, source
                ):
                    raise ValueError("unbound original artifact")
                bound = (
                    next(
                        (
                            item
                            for item in match_mappings(bound_ref.mapping)
                            if item["source_id"] == origin["source_artifact_id"]
                        ),
                        None,
                    )
                    if kind == "match"
                    else bound_ref.mapping[kind]
                )
                if bound is None or bound["local_id"] != artifact["artifact_id"]:
                    raise ValueError("origin local identity")
        for ref in refs:
            original = origins[ref.path]
            mapping = ref.mapping
            validate_origin_mapping(mapping, original, parsed.project.id, parsed.draft_scope_id)
        return InspectedPackage(
            manifest,
            members,
            scope,
            match,
            estimate,
            reports,
            packages.digest(content),
            origins,
            matches,
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
        for included in inspected.walk():
            if included.all_matches():
                actor = scopes._actor(db, actor, "technical:read")
            if included.estimate:
                actor = scopes._actor(db, actor, "estimate:read")
                if included.estimate.get("pricing_sources"):
                    actor = scopes._actor(db, actor, "library:read")
        return {
            "manifest": inspected.manifest,
            "archive_sha256": inspected.archive_sha256,
            "scope_counts": scopes._content_counts(inspected.scope["content"]),
            "scope_findings": scopes.validate_payload(inspected.scope["content"])[1],
            "match_candidates": sum(len(item["candidates"]) for item in inspected.all_matches()),
            "match_count": len(inspected.all_matches()),
            "estimate_lines": len(inspected.estimate["lines"]) if inspected.estimate else 0,
            "reports": [
                {"report_id": r["report_id"], "profile": r["profile"]}
                for included in inspected.walk()
                for r in included.reports
            ],
            "source_count": len(inspected.manifest["source_manifest"]),
            "import_available": True,
            "binary_status": "not_scanned_or_opened",
            "authority": "foreign_unverified",
        }
