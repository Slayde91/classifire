"""Transactional new-project Draft import. Original archive never confers authority."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..config import Settings
from ..models import (
    DraftEstimate,
    DraftEstimateRevision,
    DraftPackageImport,
    DraftScopeRevision,
    DraftSystemMatch,
    DraftSystemMatchRevision,
    User,
    new_id,
)
from . import draft_estimate_contract as estimate_contract
from . import draft_import_origin as origins
from . import draft_package_import as inspection
from . import draft_project_packages as packages
from . import draft_scope as scopes
from . import draft_system_match_contract as match_contract


def _access(
    db: Session,
    actor: User,
    value: inspection.InspectedPackage,
    *,
    write: bool = False,
    export: bool = False,
) -> User:
    actor = scopes._actor(db, actor, "project:read")
    if write:
        actor = scopes._actor(db, actor, "project:write")
    for included in value.walk():
        if included.match:
            actor = scopes._actor(db, actor, "technical:read")
        if included.estimate:
            actor = scopes._actor(db, actor, "estimate:read")
            if write:
                actor = scopes._actor(db, actor, "estimate:write")
            if export:
                actor = scopes._actor(db, actor, "estimate:export")
            if included.estimate.get("pricing_sources"):
                actor = scopes._actor(db, actor, "library:read")
    return actor


def _retained(
    db: Session, draft_id: str, import_id: str
) -> tuple[DraftPackageImport, inspection.InspectedPackage, dict[str, Any]]:
    row = db.scalar(
        select(DraftPackageImport)
        .where(DraftPackageImport.id == import_id, DraftPackageImport.draft_scope_id == draft_id)
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise ValueError("import unavailable")
    if (
        packages.digest(row.archive_bytes) != row.archive_hash
        or packages.digest(row.mapping_json.encode()) != row.mapping_hash
    ):
        raise ValueError("import integrity")
    original = inspection.inspect_package(row.archive_bytes)
    mapping = json.loads(row.mapping_json)
    if packages.encode(mapping).decode() != row.mapping_json or mapping.get(
        "schema_version"
    ) not in ("CLASSIFIRE-IMPORT-MAPPING-v1", "CLASSIFIRE-IMPORT-MAPPING-v2"):
        raise ValueError("mapping integrity")
    if (
        mapping["scope"]["local_id"] != draft_id
        or mapping["project"]["source_id"] != original.scope["project_id"]
    ):
        raise ValueError("mapping identity")
    inspection.validate_origin_mapping(mapping, original, mapping["project"]["local_id"], draft_id)
    for kind, model, owner_column in (
        ("scope", DraftScopeRevision, DraftScopeRevision.draft_scope_id),
        ("match", DraftSystemMatchRevision, DraftSystemMatchRevision.match_id),
        ("estimate", DraftEstimateRevision, DraftEstimateRevision.estimate_id),
    ):
        bound = mapping[kind]
        if bound is not None:
            initial_hash = db.scalar(
                select(model.content_hash).where(
                    owner_column == bound["local_id"], model.revision == bound["local_revision"]
                )
            )
            if initial_hash != bound["local_sha256"]:
                raise ValueError("initial local revision binding")
    return row, original, mapping


def read_import(
    db: Session, actor: User, draft_id: str, *, export: bool = False
) -> tuple[DraftPackageImport, inspection.InspectedPackage, dict[str, Any]]:
    draft = scopes.get_draft(db, actor, draft_id)
    row = db.scalar(select(DraftPackageImport).where(DraftPackageImport.draft_scope_id == draft_id))
    if row is None:
        raise scopes.DraftScopeError("PACKAGE_IMPORT_NOT_FOUND", 404)
    try:
        row, original, mapping = _retained(db, draft_id, row.id)
        if mapping["project"]["local_id"] != draft.project_id:
            raise ValueError("local project mismatch")
        _access(db, actor, original, export=export)
        return row, original, mapping
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        raise scopes.DraftScopeError("PACKAGE_IMPORT_INTEGRITY_FAILED", 409) from exc


def verify_local_origin(
    db: Session, draft_id: str, import_id: str | None, envelope: dict[str, Any], kind: str
) -> None:
    if import_id is None:
        if origins.imported(envelope):
            raise ValueError("unbound imported artifact")
        return
    row, original, mapping = _retained(db, draft_id, import_id)
    source = original.match if kind == "match" else original.estimate
    if source is None or envelope.get("import_origin") != origins.origin_for(
        row.id, row.archive_hash, source
    ):
        raise ValueError("foreign origin binding")
    if (
        mapping[kind]["local_id"] != envelope["artifact_id"]
        or mapping["project"]["local_id"] != envelope["project_id"]
    ):
        raise ValueError("local origin binding")
    if kind == "match":
        if any(envelope[k] != source[k] for k in ("candidates", "release", "target", "retrieval")):
            raise ValueError("foreign review basis changed")
        if envelope.get("constraint_review") != source.get("constraint_review"):
            raise ValueError("foreign constraints changed")
    else:
        by_id = {line["line_id"]: line for line in envelope["lines"]}
        for old in source["lines"]:
            line = by_id.get(old["line_id"])
            if line is None or line["history"][: len(old["history"])] != old["history"]:
                raise ValueError("foreign estimate history changed")
            for key in (
                "original_quantity",
                "original_rate",
                "created_by",
                "created_at",
                "unit",
                "target_kind",
                "target_id",
                "opening_ids",
                "work_basis",
            ):
                if line[key] != old[key]:
                    raise ValueError("foreign line basis changed")
        history = source.get("pricing_sources", [])
        if envelope.get("pricing_sources", [])[: len(history)] != history:
            raise ValueError("foreign pricing history changed")


def _mapping(source: dict[str, Any], local: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": source["artifact_id"],
        "source_revision": source["revision"],
        "source_sha256": source["sha256"],
        "local_id": local["artifact_id"],
        "local_revision": local["revision"],
        "local_sha256": local["sha256"],
    }


def create_import(
    db: Session,
    actor: User,
    content: bytes,
    *,
    expected_sha256: str,
    reference: str,
    name: str,
    settings: Settings,
) -> DraftPackageImport:
    actor = scopes._actor(db, actor, "project:write")
    if packages.digest(content) != expected_sha256:
        raise scopes.DraftScopeError("PACKAGE_IMPORT_PREVIEW_CHANGED", 409)
    original = inspection.inspect_package(content)
    if len(list(original.walk())) >= 8:
        raise scopes.DraftScopeError("PACKAGE_IMPORT_ORIGIN_LIMIT", 422)
    actor = _access(db, actor, original, write=True)
    from . import draft_estimates as estimates
    from . import draft_import_reports as reports

    with scopes._atomic(db):
        draft = scopes.create_draft_project(db, actor, reference, name)
        local_scope = scopes.apply_import(
            db,
            actor,
            draft.id,
            1,
            original.members["artifacts/scope.json"],
            expected_source_hash=packages.digest(original.members["artifacts/scope.json"]),
        )
        created = datetime.now(UTC)
        row = DraftPackageImport(
            id=new_id(),
            draft_scope_id=draft.id,
            archive_bytes=content,
            archive_hash=expected_sha256,
            mapping_json="{}",
            mapping_hash=packages.digest(b"{}"),
            created_by_id=actor.id,
            created_at=created,
        )
        db.add(row)
        db.flush()
        mapping: dict[str, Any] = {
            "schema_version": "CLASSIFIRE-IMPORT-MAPPING-v1",
            "project": {"source_id": original.scope["project_id"], "local_id": draft.project_id},
            "scope": _mapping(original.scope, local_scope),
            "match": None,
            "estimate": None,
            "reports": [],
            "entity_ids": "retained_within_new_scope",
        }
        match = None
        if original.match:
            match = copy.deepcopy(original.match)
            match.update(
                artifact_id=new_id(),
                project_id=draft.project_id,
                revision=1,
                parent_hash=None,
                created_by=actor.id,
                created_at=created.isoformat(),
                scope=local_scope,
            )
            match = origins.wrap(
                match,
                "match",
                origins.origin_for(row.id, row.archive_hash, original.match),
                origins.content_schema(original.match),
            )
            match_contract.validate_envelope(match)
            db.add(
                DraftSystemMatch(
                    id=match["artifact_id"],
                    draft_scope_id=draft.id,
                    scope_revision=local_scope["revision"],
                    scope_hash=local_scope["sha256"],
                    release_id=None,
                    release_hash=match["release"]["sha256"],
                    import_id=row.id,
                    latest_revision=1,
                    latest_hash=match["sha256"],
                    basis_hash=match_contract.basis_hash(match),
                    created_by_id=actor.id,
                    created_at=created,
                )
            )
            db.flush()
            db.add(
                DraftSystemMatchRevision(
                    match_id=match["artifact_id"],
                    revision=1,
                    parent_hash=None,
                    content_hash=match["sha256"],
                    envelope_json=packages.encode(match).decode(),
                    created_by_id=actor.id,
                    created_at=created,
                )
            )
            db.flush()  # Persist the referenced Match revision before its Estimate.
            mapping["match"] = _mapping(original.match, match)
        if original.estimate:
            estimate = copy.deepcopy(original.estimate)
            estimate.update(
                artifact_id=new_id(),
                project_id=draft.project_id,
                revision=1,
                parent_hash=None,
                created_by=actor.id,
                created_at=created.isoformat(),
                scope=local_scope,
                system_match=match,
            )
            estimate = origins.wrap(
                estimate,
                "estimate",
                origins.origin_for(row.id, row.archive_hash, original.estimate),
                origins.content_schema(original.estimate),
            )
            estimate_contract.validate_envelope(estimate)
            db.add(
                DraftEstimate(
                    id=estimate["artifact_id"],
                    draft_scope_id=draft.id,
                    scope_revision=local_scope["revision"],
                    scope_hash=local_scope["sha256"],
                    import_id=row.id,
                    match_id=match["artifact_id"] if match else None,
                    match_revision=1 if match else None,
                    match_hash=match["sha256"] if match else None,
                    latest_revision=1,
                    latest_hash=estimate["sha256"],
                    basis_hash=estimate_contract.basis_hash(estimate),
                    created_by_id=actor.id,
                    created_at=created,
                )
            )
            db.flush()
            db.add(estimates._row(estimate["artifact_id"], estimate, created))
            mapping["estimate"] = _mapping(original.estimate, estimate)
        for report, report_paths in original.report_members():
            members: dict[str, Any] = {}
            for fmt in ("pdf", "xlsx"):
                path = report_paths[fmt]
                source = reports.intake(fmt).retain(
                    db,
                    actor,
                    draft.id,
                    f"{report['report_id']}.{fmt}",
                    original.resolve(path),
                    settings=settings,
                )
                members[fmt] = {
                    "source_id": source.id,
                    "path": path,
                    "sha256": source.source_sha256,
                }
            mapping["reports"].append(
                {
                    "source_report_id": report["report_id"],
                    "profile": report["profile"],
                    "members": members,
                }
            )
        evidence = list(original.evidence_members())
        if evidence:
            mapping["schema_version"] = "CLASSIFIRE-IMPORT-MAPPING-v2"
            mapping["evidence"] = []
            for source_id, path in evidence:
                fmt = path.rsplit(".", 1)[-1]
                source = reports.evidence_intake(fmt).retain(
                    db,
                    actor,
                    draft.id,
                    f"{source_id}.{fmt}",
                    original.resolve(path),
                    settings=settings,
                )
                mapping["evidence"].append(
                    {
                        "source_id": source.id,
                        "original_source_id": source_id,
                        "path": path,
                        "sha256": source.source_sha256,
                    }
                )
        row.mapping_json = packages.encode(mapping).decode()
        row.mapping_hash = packages.digest(row.mapping_json.encode())
        db.flush()
        if match:
            verify_local_origin(db, draft.id, row.id, match, "match")
        if original.estimate:
            verify_local_origin(db, draft.id, row.id, estimate, "estimate")
        _access(db, actor, original, write=True)
        record_audit(
            db,
            actor=actor,
            action="draft_package.import",
            entity_type="draft_package_import",
            entity_id=row.id,
            project_id=draft.project_id,
            new_value={"archive_sha256": row.archive_hash, "mapping_sha256": row.mapping_hash},
        )
        db.flush()
    return row
