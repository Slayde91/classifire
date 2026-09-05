"""Selected, immutable Draft project interchange. Callers own transactions.

Composition reads existing authorized artifacts, never their capability writers.
Source bodies remain external/withheld; only selected reports are binary members.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID
from zipfile import ZIP_STORED, BadZipFile, ZipFile, ZipInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, defer

from ..audit import record_audit
from ..models import DraftProjectPackage, User, new_id
from . import draft_estimate_reports as estimate_reports
from . import draft_estimates as estimates
from . import draft_scope as scopes
from . import draft_scope_reports as scope_reports
from . import draft_system_matches as matches

SCHEMA = "CLASSIFIRE-DRAFT-PROJECT-PACKAGE-v1"
MAX_ARCHIVE = 64 * 1024 * 1024
MAX_MANIFEST = 2 * 1024 * 1024
MAX_MEMBERS = 28
NOTICE = (
    "Selected Draft revisions only; not a complete database backup. Source files and "
    "unselected artifacts/history are not included. Retained review/provenance claims "
    "grant no local approval, lock or release authority. Package import is not yet available."
)


class PackageError(scopes.DraftScopeError):
    pass


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    scope_revision: Annotated[int, Field(ge=1)]
    match_id: str | None = None
    match_revision: Annotated[int, Field(ge=1)] | None = None
    estimate_id: str | None = None
    estimate_revision: Annotated[int, Field(ge=1)] | None = None
    scope_reports: Annotated[list[str], Field(max_length=4)] = Field(default_factory=list)
    estimate_reports: Annotated[list[str], Field(max_length=4)] = Field(default_factory=list)

    @field_validator("match_id", "estimate_id")
    @classmethod
    def identity(cls, value: str | None) -> str | None:
        if value is not None and str(UUID(value)) != value:
            raise ValueError("identity")
        return value

    @field_validator("scope_reports", "estimate_reports")
    @classmethod
    def identities(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(str(UUID(v)) != v for v in value):
            raise ValueError("identities")
        return sorted(value)

    @model_validator(mode="after")
    def paired(self) -> Selection:
        if (
            (self.match_id is None) != (self.match_revision is None)
            or (self.estimate_id is None) != (self.estimate_revision is None)
            or (self.estimate_reports and self.estimate_id is None)
        ):
            raise ValueError("selection")
        return self


def selection(value: Any) -> Selection:
    try:
        return Selection.model_validate(value)
    except (ValidationError, ValueError, TypeError) as exc:
        raise PackageError("PACKAGE_SELECTION_INVALID") from exc


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def encode(value: Any) -> bytes:
    return scopes._json(value)


def _archive(manifest: dict[str, Any], members: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    all_members = {**members, "manifest.json": encode(manifest)}
    if len(all_members) > MAX_MEMBERS or sum(map(len, all_members.values())) > MAX_ARCHIVE:
        raise PackageError("PACKAGE_TOO_LARGE", 413)
    with ZipFile(stream, "w", compression=ZIP_STORED) as archive:
        for name, content in sorted(all_members.items()):
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100600 << 16
            archive.writestr(info, content)
    result = stream.getvalue()
    if len(result) > MAX_ARCHIVE:
        raise PackageError("PACKAGE_TOO_LARGE", 413)
    return result


def inspect_archive(content: bytes) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Structural exact-byte validation only; never extraction, import or authority."""
    try:
        if type(content) is not bytes or not 1 <= len(content) <= MAX_ARCHIVE:
            raise ValueError("size")
        with ZipFile(io.BytesIO(content)) as archive:
            items = archive.infolist()
            names = [i.filename for i in items]
            if (
                not 1 <= len(items) <= MAX_MEMBERS
                or len(set(names)) != len(names)
                or sum(i.file_size for i in items) > MAX_ARCHIVE
                or any(i.compress_type != ZIP_STORED or i.flag_bits & 1 for i in items)
                or "manifest.json" not in names
                or archive.getinfo("manifest.json").file_size > MAX_MANIFEST
            ):
                raise ValueError("members")
            manifest = json.loads(archive.read("manifest.json"))
            if (
                manifest["schema_version"] != SCHEMA
                or manifest["state"] != "Draft"
                or manifest["authority"] != "historical_only"
                or encode(manifest) != archive.read("manifest.json")
            ):
                raise ValueError("manifest")
            entries = manifest["members"]
            if type(entries) is not list or len(entries) > MAX_MEMBERS - 1:
                raise ValueError("inventory")
            members = {}
            for entry in entries:
                name = entry["path"]
                if (
                    not re.fullmatch(r"(?:artifacts|reports)/[a-z0-9_-]+\.(?:json|pdf|xlsx)", name)
                    or name in members
                    or set(entry) != {"path", "sha256", "size_bytes"}
                ):
                    raise ValueError("path")
                value = archive.read(name)
                if len(value) != entry["size_bytes"] or digest(value) != entry["sha256"]:
                    raise ValueError("hash")
                members[name] = value
            if set(names) != {"manifest.json", *members} or _archive(manifest, members) != content:
                raise ValueError("encoding")
            return manifest, members
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        RecursionError,
        UnicodeError,
        BadZipFile,
        OverflowError,
        RuntimeError,
    ) as exc:
        raise PackageError("PACKAGE_ARCHIVE_INVALID", 409) from exc


def _compose(
    db: Session,
    actor: User,
    draft_id: str,
    selected: Selection,
    *,
    project: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    actor = scopes._actor(db, actor, "project:read")
    draft = scopes.get_draft(db, actor, draft_id)
    scope = scopes.read_revision(db, actor, draft_id, selected.scope_revision)
    match = (
        matches.read_match_revision(db, actor, draft_id, selected.match_id, selected.match_revision)
        if selected.match_id
        else None
    )
    estimate = None
    if selected.estimate_id:
        estimates._estimate(db, actor, draft_id, selected.estimate_id, export=True)
        estimate = estimates.read_estimate_revision(
            db, actor, draft_id, selected.estimate_id, selected.estimate_revision
        )
        if estimate["scope"] != scope or estimate["system_match"] != match:
            raise PackageError("PACKAGE_DEPENDENCIES_DIFFER", 409)
    if match and (match["scope"]["sha256"] != scope["sha256"] or match["scope"] != scope):
        raise PackageError("PACKAGE_DEPENDENCIES_DIFFER", 409)
    members = {"artifacts/scope.json": encode(scope)}
    if match:
        members["artifacts/system-match.json"] = encode(match)
    if estimate:
        members["artifacts/estimate.json"] = encode(estimate)
    for report_id in selected.scope_reports:
        row, snapshot = scope_reports._retained(db, actor, draft_id, report_id)
        if snapshot["scope"] != scope or (
            snapshot.get("system_match") is not None and snapshot["system_match"] != match
        ):
            raise PackageError("PACKAGE_REPORT_DEPENDENCIES_DIFFER", 409)
        members[f"reports/{report_id}.json"] = encode(snapshot)
        for fmt in ("pdf", "xlsx"):
            members[f"reports/{report_id}.{fmt}"] = getattr(row, fmt + "_bytes")
    for report_id in selected.estimate_reports:
        if selected.estimate_id is None:
            raise PackageError("PACKAGE_SELECTION_INVALID")
        estimate_row, snapshot = estimate_reports._retained(
            db, actor, draft_id, selected.estimate_id, report_id, export=True
        )
        if snapshot["estimate"] != estimate:
            raise PackageError("PACKAGE_REPORT_DEPENDENCIES_DIFFER", 409)
        members[f"reports/{report_id}.json"] = encode(snapshot)
        for fmt in ("pdf", "xlsx"):
            members[f"reports/{report_id}.{fmt}"] = getattr(estimate_row, fmt + "_bytes")
    sources = []
    for index, _ref in enumerate(scope.get("evidence_refs", [])):
        sources.append(
            {
                "kind": "project_evidence",
                "membership": "external",
                "reference": f"artifacts/scope.json#/evidence_refs/{index}",
                "reason": "Source bytes not included; retained/imported claims stay unverified",
            }
        )
    if match:
        for index, _candidate in enumerate(match["candidates"]):
            sources.append(
                {
                    "kind": "technical_source",
                    "membership": "withheld",
                    "reference": f"artifacts/system-match.json#/candidates/{index}/source",
                    "reason": "Restricted library source body; saved review claims only",
                }
            )
    if estimate:
        for index, _source in enumerate(estimate.get("pricing_sources", [])):
            sources.append(
                {
                    "kind": "pricing_source",
                    "membership": "withheld",
                    "reference": f"artifacts/estimate.json#/pricing_sources/{index}",
                    "reason": "Restricted pricing workbook body; retained cell provenance only",
                }
            )
    manifest = {
        "schema_version": SCHEMA,
        "state": "Draft",
        "authority": "historical_only",
        "project": project or scope_reports._project(db, draft),
        "draft_scope_id": draft.id,
        "selection": selected.model_dump(),
        "notice": NOTICE,
        "capabilities": {
            "scope": "included",
            "system_match": "included" if match else "not_selected",
            "estimate": "included" if estimate else "not_selected",
            "reports": "included"
            if selected.scope_reports or selected.estimate_reports
            else "not_selected",
        },
        "source_manifest": sources,
        "members": [
            {"path": name, "sha256": digest(value), "size_bytes": len(value)}
            for name, value in sorted(members.items())
        ],
    }
    if len(encode(manifest)) > MAX_MANIFEST:
        raise PackageError("PACKAGE_TOO_LARGE", 413)
    _archive(manifest, members)
    return manifest, members


def latest_revision(db: Session, actor: User, draft_id: str) -> int:
    scopes.get_draft(db, actor, draft_id)
    return (
        db.scalar(
            select(func.max(DraftProjectPackage.revision)).where(
                DraftProjectPackage.draft_scope_id == draft_id
            )
        )
        or 0
    )


def preview(db: Session, actor: User, draft_id: str, value: Any) -> dict[str, Any]:
    """No writes, including no download audit events, during configuration/preview."""
    manifest, _members = _compose(db, actor, draft_id, selection(value))
    return {
        "manifest": manifest,
        "preview_hash": digest(encode(manifest)),
        "latest_revision": latest_revision(db, actor, draft_id),
    }


def create_package(
    db: Session, actor: User, draft_id: str, value: Any, expected_revision: int, preview_hash: str
) -> DraftProjectPackage:
    actor = scopes._actor(db, actor, "project:write")
    draft = scopes.get_draft(db, actor, draft_id)
    if type(expected_revision) is not int or expected_revision < 0:
        raise PackageError("PACKAGE_REVISION_INVALID")
    selected = selection(value)
    manifest, members = _compose(db, actor, draft_id, selected)
    if digest(encode(manifest)) != preview_hash:
        raise PackageError("PACKAGE_PREVIEW_CHANGED", 409)
    current = latest_revision(db, actor, draft_id)
    if current != expected_revision:
        raise PackageError("PACKAGE_REVISION_CONFLICT", 409)
    parent = db.scalar(
        select(DraftProjectPackage.manifest_hash).where(
            DraftProjectPackage.draft_scope_id == draft_id, DraftProjectPackage.revision == current
        )
    )
    created = datetime.now(UTC)
    identifier = new_id()
    manifest.update(
        package_id=identifier,
        revision=current + 1,
        parent_hash=parent,
        created_by=actor.id,
        created_at=created.isoformat(),
    )
    content = _archive(manifest, members)
    inspect_archive(content)
    checked, checked_members = _compose(db, actor, draft_id, selected)
    if digest(encode(checked)) != preview_hash or checked_members != members:
        raise PackageError("PACKAGE_PREVIEW_CHANGED", 409)
    actor = scopes._actor(db, actor, "project:write")
    row = DraftProjectPackage(
        id=identifier,
        created_at=created,
        updated_at=created,
        draft_scope_id=draft_id,
        revision=current + 1,
        parent_hash=parent,
        manifest_json=encode(manifest).decode("utf-8"),
        manifest_hash=digest(encode(manifest)),
        created_by_id=actor.id,
        archive_bytes=content,
        archive_hash=digest(content),
    )
    try:
        with scopes._atomic(db):
            db.add(row)
            db.flush()
    except IntegrityError as exc:
        raise PackageError("PACKAGE_REVISION_CONFLICT", 409) from exc
    record_audit(
        db,
        actor=actor,
        action="draft_project_package.create",
        entity_type="draft_project_package",
        entity_id=row.id,
        project_id=draft.project_id,
        new_value={
            "revision": row.revision,
            "manifest_sha256": row.manifest_hash,
            "archive_sha256": row.archive_hash,
        },
    )
    db.flush()
    return row


def read_package(
    db: Session, actor: User, draft_id: str, package_id: str
) -> tuple[DraftProjectPackage, dict[str, Any]]:
    scopes.get_draft(db, actor, draft_id)
    row = db.scalar(
        select(DraftProjectPackage)
        .where(DraftProjectPackage.id == package_id, DraftProjectPackage.draft_scope_id == draft_id)
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise PackageError("PACKAGE_NOT_FOUND", 404)
    try:
        manifest, members = inspect_archive(row.archive_bytes)
        created = (
            row.created_at.replace(tzinfo=UTC) if row.created_at.tzinfo is None else row.created_at
        )
        if (
            encode(manifest).decode("utf-8") != row.manifest_json
            or digest(encode(manifest)) != row.manifest_hash
            or digest(row.archive_bytes) != row.archive_hash
            or manifest["package_id"] != row.id
            or manifest["revision"] != row.revision
            or manifest["parent_hash"] != row.parent_hash
            or manifest["created_by"] != row.created_by_id
            or manifest["created_at"] != created.astimezone(UTC).isoformat()
        ):
            raise ValueError("binding")
        parent = db.scalar(
            select(DraftProjectPackage.manifest_hash).where(
                DraftProjectPackage.draft_scope_id == draft_id,
                DraftProjectPackage.revision == row.revision - 1,
            )
        )
        if row.parent_hash != parent or (row.revision > 1 and parent is None):
            raise ValueError("parent")
        expected, expected_members = _compose(
            db, actor, draft_id, selection(manifest["selection"]), project=manifest["project"]
        )
        identity = {
            key: manifest[key]
            for key in ("package_id", "revision", "parent_hash", "created_by", "created_at")
        }
        if manifest != {**expected, **identity} or members != expected_members:
            raise ValueError("source")
        draft = scopes.get_draft(db, actor, draft_id)
        if manifest["project"]["id"] != draft.project_id:
            raise ValueError("project")
        return row, manifest
    except scopes.DraftScopeError as exc:
        if exc.status_code == 403:
            raise
        raise PackageError("PACKAGE_INTEGRITY_FAILED", 409) from exc
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError) as exc:
        raise PackageError("PACKAGE_INTEGRITY_FAILED", 409) from exc


def list_packages(db: Session, actor: User, draft_id: str) -> list[DraftProjectPackage]:
    scopes.get_draft(db, actor, draft_id)
    rows = list(
        db.scalars(
            select(DraftProjectPackage)
            .options(defer(DraftProjectPackage.archive_bytes))
            .where(DraftProjectPackage.draft_scope_id == draft_id)
            .order_by(DraftProjectPackage.revision.desc())
            .limit(20)
        )
    )
    visible = []
    for row in rows:
        try:
            read_package(db, actor, draft_id, row.id)
        except scopes.DraftScopeError as exc:
            if exc.status_code == 403:
                continue
            raise
        visible.append(row)
        db.expire(row, ["archive_bytes"])
    return visible


def package_bytes(db: Session, actor: User, draft_id: str, package_id: str) -> bytes:
    row, _manifest = read_package(db, actor, draft_id, package_id)
    draft = scopes.get_draft(db, actor, draft_id)
    value = row.archive_bytes
    record_audit(
        db,
        actor=actor,
        action="draft_project_package.download",
        entity_type="draft_project_package",
        entity_id=row.id,
        project_id=draft.project_id,
        new_value={"archive_sha256": row.archive_hash, "revision": row.revision},
    )
    db.flush()
    return value


def staleness(
    db: Session, actor: User, draft_id: str, manifest: dict[str, Any], *, storage_root: Path
) -> list[str]:
    from .draft_pdf_intake import scope_evidence_staleness

    chosen = selection(manifest["selection"])
    draft = scopes.get_draft(db, actor, draft_id)
    scope = scopes.read_revision(db, actor, draft_id, chosen.scope_revision)
    reasons = list(scope_evidence_staleness(db, actor, draft_id, scope, storage_root=storage_root))
    if scopes.read_revision(db, actor, draft_id)["sha256"] != scope["sha256"]:
        reasons.append("PACKAGE_SCOPE_CHANGED")
    if scope_reports._project(db, draft) != manifest["project"]:
        reasons.append("PACKAGE_PROJECT_CHANGED")
    if chosen.match_id:
        old = matches.read_match_revision(
            db, actor, draft_id, chosen.match_id, chosen.match_revision
        )
        if (
            matches.read_match_revision(db, actor, draft_id, chosen.match_id)["sha256"]
            != old["sha256"]
        ):
            reasons.append("PACKAGE_REVIEW_CHANGED")
        reasons.extend(
            matches.match_staleness(
                db,
                actor,
                draft_id,
                chosen.match_id,
                chosen.match_revision,
                storage_root=storage_root,
            )
        )
    if chosen.estimate_id:
        old = estimates.read_estimate_revision(
            db, actor, draft_id, chosen.estimate_id, chosen.estimate_revision
        )
        if (
            estimates.read_estimate_revision(db, actor, draft_id, chosen.estimate_id)["sha256"]
            != old["sha256"]
        ):
            reasons.append("PACKAGE_ESTIMATE_CHANGED")
        reasons.extend(
            estimates.estimate_staleness(
                db,
                actor,
                draft_id,
                chosen.estimate_id,
                chosen.estimate_revision,
                storage_root=storage_root,
            )
        )
    return sorted(set(reasons))
