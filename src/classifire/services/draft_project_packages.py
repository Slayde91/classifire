"""Selected, immutable Draft project interchange. Callers own transactions.

Composition reads existing authorized artifacts, never their capability writers.
Project PDFs/workbooks may be explicitly included; library source bodies stay withheld.
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

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    ValidationError,
    field_validator,
    model_serializer,
    model_validator,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, defer

from ..audit import record_audit
from ..config import get_settings
from ..models import DraftPackageImport, DraftProjectPackage, User, new_id
from . import draft_estimate_reports as estimate_reports
from . import draft_estimates as estimates
from . import draft_scope as scopes
from . import draft_scope_reports as scope_reports
from . import draft_system_matches as matches

SCHEMA = "CLASSIFIRE-DRAFT-PROJECT-PACKAGE-v1"
SCHEMA_V2 = "CLASSIFIRE-DRAFT-PROJECT-PACKAGE-v2"
SCHEMA_V3 = "CLASSIFIRE-DRAFT-PROJECT-PACKAGE-v3"
SCHEMA_V4 = "CLASSIFIRE-DRAFT-PROJECT-PACKAGE-v4"
SCHEMA_V5 = "CLASSIFIRE-DRAFT-PROJECT-PACKAGE-v5"
SCHEMA_V6 = "CLASSIFIRE-DRAFT-PROJECT-PACKAGE-v6"
MAX_ARCHIVE = 128 * 1024 * 1024
MAX_V1_ARCHIVE = 64 * 1024 * 1024
MAX_MANIFEST = 2 * 1024 * 1024
MAX_MEMBERS = 32
MAX_V1_MEMBERS = 28
MAX_SELECTED_MATCHES = MAX_MEMBERS - 2
NOTICE = (
    "Selected Draft revisions only; not a complete database backup. Source files and "
    "unselected artifacts/history are not included. Retained review/provenance claims "
    "grant no local approval, lock or release authority. Package import is not yet available."
)


class PackageError(scopes.DraftScopeError):
    pass


class MatchSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    match_id: str
    match_revision: Annotated[int, Field(ge=1, le=2_147_483_647)]

    @field_validator("match_id")
    @classmethod
    def identity(cls, value: str) -> str:
        if str(UUID(value)) != value:
            raise ValueError("identity")
        return value


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    scope_revision: Annotated[int, Field(ge=1)]
    pdf_sources: Annotated[list[str], Field(max_length=4)] = Field(default_factory=list)
    xlsx_sources: Annotated[list[str], Field(max_length=4)] = Field(default_factory=list)
    docx_sources: Annotated[list[str], Field(max_length=4)] = Field(default_factory=list)
    matches: Annotated[list[MatchSelection], Field(max_length=MAX_SELECTED_MATCHES)] = Field(
        default_factory=list
    )
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

    @field_validator(
        "scope_reports", "estimate_reports", "pdf_sources", "xlsx_sources", "docx_sources"
    )
    @classmethod
    def identities(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(str(UUID(v)) != v for v in value):
            raise ValueError("identities")
        return sorted(value)

    @field_validator("matches")
    @classmethod
    def match_identities(cls, value: list[MatchSelection]) -> list[MatchSelection]:
        if len({item.match_id for item in value}) != len(value):
            raise ValueError("duplicate review")
        return sorted(value, key=lambda item: item.match_id)

    @model_serializer(mode="wrap")
    def portable_selection(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        value: dict[str, Any] = dict(handler(self))
        if not self.pdf_sources:
            value.pop("pdf_sources", None)
        if not self.xlsx_sources:
            value.pop("xlsx_sources", None)
        if not self.docx_sources:
            value.pop("docx_sources", None)
        if not self.matches:
            value.pop("matches", None)
        return value

    @model_validator(mode="after")
    def paired(self) -> Selection:
        if set(self.pdf_sources) & set(self.xlsx_sources) or set(self.docx_sources) & (
            set(self.pdf_sources) | set(self.xlsx_sources)
        ):
            raise ValueError("source format selection")
        if (
            (self.match_id is None) != (self.match_revision is None)
            or (self.estimate_id is None) != (self.estimate_revision is None)
            or (self.estimate_reports and self.estimate_id is None)
            or (self.matches and (self.match_id is not None or self.match_revision is not None))
        ):
            raise ValueError("selection")
        return self


def selection(value: Any) -> Selection:
    try:
        return Selection.model_validate(value)
    except ValidationError as exc:
        findings = [
            {
                "path": ".".join(
                    str(part)
                    if isinstance(part, int) or part in Selection.model_fields
                    else "[unknown]"
                    for part in error["loc"]
                ),
                "code": "INVALID_FIELD",
                "message": "Check the selection field and paired IDs/revisions.",
                "severity": "error",
            }
            for error in exc.errors(include_input=False, include_url=False)[:50]
        ]
        raise PackageError("PACKAGE_SELECTION_INVALID", findings=findings) from exc
    except (ValueError, TypeError) as exc:
        raise PackageError("PACKAGE_SELECTION_INVALID") from exc


def selected_match_references(selected: Selection) -> list[MatchSelection]:
    """Return only explicitly selected revisions, including the legacy singular form."""
    if selected.matches:
        return list(selected.matches)
    if selected.match_id is not None and selected.match_revision is not None:
        return [MatchSelection(match_id=selected.match_id, match_revision=selected.match_revision)]
    return []


def match_member_path(match_id: str | None = None) -> str:
    if match_id is None:
        return "artifacts/system-match.json"
    if str(UUID(match_id)) != match_id:
        raise ValueError("identity")
    return f"artifacts/system-match-{match_id}.json"


def validate_match_collection(scope: dict[str, Any], collection: list[dict[str, Any]]) -> None:
    """Validate already-authorized/structurally-validated reviews without choosing a row."""
    if len(collection) > MAX_SELECTED_MATCHES:
        raise PackageError("PACKAGE_SELECTION_INVALID")
    targets: set[tuple[str, str | None]] = set()
    for review in collection:
        if review["scope"] != scope:
            raise PackageError("PACKAGE_DEPENDENCIES_DIFFER", 409)
        target = review["target"]
        opening_id, service_id = target["opening_id"], target["service_id"]
        if (
            opening_id is None
            or (service_id is None and not target["blank_opening"])
            or (service_id is not None and target["blank_opening"])
        ):
            raise PackageError("PACKAGE_MATCH_TARGET_INVALID", 422)
        key = (opening_id, service_id)
        if key in targets:
            raise PackageError("PACKAGE_MATCH_TARGET_CONFLICT", 422)
        targets.add(key)


def match_dependency_selected(
    dependency: dict[str, Any] | None,
    legacy_match: dict[str, Any] | None,
    collection: list[dict[str, Any]],
) -> bool:
    """Extra v6 reviews remain independent; embedded dependencies must be exact members."""
    if collection:
        return dependency is None or dependency in collection
    return dependency == legacy_match


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def encode(value: Any) -> bytes:
    return scopes._json(value)


def _archive(manifest: dict[str, Any], members: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    all_members = {**members, "manifest.json": encode(manifest)}
    extended = manifest.get("schema_version") in (
        SCHEMA_V2,
        SCHEMA_V3,
        SCHEMA_V4,
        SCHEMA_V5,
        SCHEMA_V6,
    )
    limit = MAX_ARCHIVE if extended else MAX_V1_ARCHIVE
    member_limit = MAX_MEMBERS if extended else MAX_V1_MEMBERS
    if len(all_members) > member_limit or sum(map(len, all_members.values())) > limit:
        raise PackageError("PACKAGE_TOO_LARGE", 413)
    with ZipFile(stream, "w", compression=ZIP_STORED) as archive:
        for name, content in sorted(all_members.items()):
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100600 << 16
            archive.writestr(info, content)
    result = stream.getvalue()
    if len(result) > limit:
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
                manifest["schema_version"]
                not in (SCHEMA, SCHEMA_V2, SCHEMA_V3, SCHEMA_V4, SCHEMA_V5, SCHEMA_V6)
                or manifest["state"] != "Draft"
                or manifest["authority"] != "historical_only"
                or encode(manifest) != archive.read("manifest.json")
            ):
                raise ValueError("manifest")
            if manifest["schema_version"] == SCHEMA and (
                len(content) > MAX_V1_ARCHIVE or len(items) > MAX_V1_MEMBERS
            ):
                raise ValueError("legacy bounds")
            entries = manifest["members"]
            if type(entries) is not list or len(entries) > MAX_MEMBERS - 1:
                raise ValueError("inventory")
            members = {}
            for entry in entries:
                name = entry["path"]
                if (
                    not (
                        re.fullmatch(r"(?:artifacts|reports)/[a-z0-9_-]+\.(?:json|pdf|xlsx)", name)
                        or (
                            manifest["schema_version"]
                            in (SCHEMA_V2, SCHEMA_V3, SCHEMA_V4, SCHEMA_V5, SCHEMA_V6)
                            and re.fullmatch(r"origins/[0-9a-f]{64}\.zip", name)
                        )
                        or (
                            manifest["schema_version"]
                            in (SCHEMA_V3, SCHEMA_V4, SCHEMA_V5, SCHEMA_V6)
                            and re.fullmatch(r"evidence/[a-z0-9-]+\.pdf", name)
                        )
                        or (
                            manifest["schema_version"] in (SCHEMA_V4, SCHEMA_V5, SCHEMA_V6)
                            and re.fullmatch(r"evidence/[a-z0-9-]+\.xlsx", name)
                        )
                        or (
                            manifest["schema_version"] in (SCHEMA_V5, SCHEMA_V6)
                            and re.fullmatch(r"evidence/[a-z0-9-]+\.docx", name)
                        )
                    )
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


def source_manifest(
    scope: dict[str, Any],
    match: dict[str, Any] | None,
    estimate: dict[str, Any] | None,
    pdf_sources: list[str] | None = None,
    xlsx_sources: list[str] | None = None,
    docx_sources: list[str] | None = None,
    *,
    match_collection: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Exact source inventory shared by export and foreign-package validation."""
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
    for index, ref in enumerate(scope.get("evidence_refs", [])):
        if ref.get("source_id") in (pdf_sources or []):
            sources[index].update(
                membership="included",
                path=f"evidence/{ref['source_id']}.pdf",
                reason=(
                    "Exact project PDF bytes included; review claims do not grant local authority"
                ),
            )
    for index, ref in enumerate(scope.get("evidence_refs", [])):
        if ref.get("source_id") in (xlsx_sources or []):
            sources[index].update(
                membership="included",
                path=f"evidence/{ref['source_id']}.xlsx",
                reason="Exact project workbook bytes included; imported claims stay unverified",
            )
    for index, ref in enumerate(scope.get("evidence_refs", [])):
        if ref.get("source_id") in (docx_sources or []):
            sources[index].update(
                membership="included",
                path=f"evidence/{ref['source_id']}.docx",
                reason="Exact project Word bytes included; imported claims stay unverified",
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
    for review in sorted(match_collection or [], key=lambda item: item["artifact_id"]):
        path = match_member_path(review["artifact_id"])
        for index, _candidate in enumerate(review["candidates"]):
            sources.append(
                {
                    "kind": "technical_source",
                    "membership": "withheld",
                    "reference": f"{path}#/candidates/{index}/source",
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
    return sources


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
    collection = [
        matches.read_match_revision(db, actor, draft_id, item.match_id, item.match_revision)
        for item in selected.matches
    ]
    validate_match_collection(scope, collection)
    estimate = None
    if selected.estimate_id:
        estimates._estimate(db, actor, draft_id, selected.estimate_id, export=True)
        estimate = estimates.read_estimate_revision(
            db, actor, draft_id, selected.estimate_id, selected.estimate_revision
        )
        if estimate["scope"] != scope or not match_dependency_selected(
            estimate["system_match"], match, collection
        ):
            raise PackageError("PACKAGE_DEPENDENCIES_DIFFER", 409)
    if match and (match["scope"]["sha256"] != scope["sha256"] or match["scope"] != scope):
        raise PackageError("PACKAGE_DEPENDENCIES_DIFFER", 409)
    members = {"artifacts/scope.json": encode(scope)}
    if match:
        members["artifacts/system-match.json"] = encode(match)
    for review in collection:
        members[match_member_path(review["artifact_id"])] = encode(review)
    if estimate:
        members["artifacts/estimate.json"] = encode(estimate)
    for report_id in selected.scope_reports:
        row, snapshot = scope_reports._retained(db, actor, draft_id, report_id)
        if snapshot["scope"] != scope or any(
            not match_dependency_selected(review, match, collection)
            for review in scope_reports.report_matches(snapshot)
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
        if snapshot["estimate"] != estimate or any(
            not match_dependency_selected(review, match, collection)
            for review in estimate_reports.report_matches(snapshot)
        ):
            raise PackageError("PACKAGE_REPORT_DEPENDENCIES_DIFFER", 409)
        members[f"reports/{report_id}.json"] = encode(snapshot)
        for fmt in ("pdf", "xlsx"):
            members[f"reports/{report_id}.{fmt}"] = getattr(estimate_row, fmt + "_bytes")
    if selected.pdf_sources:
        from . import draft_pdf_intake as pdf

        for source_id in selected.pdf_sources:
            refs = [
                ref for ref in scope.get("evidence_refs", []) if ref.get("source_id") == source_id
            ]
            if not refs or any(
                ref.get("origin") != "local_retained" or "page_number" not in ref for ref in refs
            ):
                raise PackageError("PACKAGE_PDF_SELECTION_INVALID", 409)
            source, _document, content = pdf._document(
                db,
                actor,
                draft_id,
                source_id,
                get_settings().storage_root,
            )
            if any(
                ref["source_sha256"] != content.sha256
                or ref["source_size_bytes"] != len(content.content)
                or ref["document_sha256"] != source.document_sha256
                for ref in refs
            ):
                raise PackageError("PACKAGE_PDF_SOURCE_CHANGED", 409)
            members[f"evidence/{source_id}.pdf"] = content.content
    if selected.xlsx_sources:
        from . import draft_scope_xlsx as xlsx

        for source_id in selected.xlsx_sources:
            refs = [
                ref for ref in scope.get("evidence_refs", []) if ref.get("source_id") == source_id
            ]
            if not refs or any(
                ref.get("origin") != "local_retained" or ref.get("source_kind") != "xlsx"
                for ref in refs
            ):
                raise PackageError("PACKAGE_XLSX_SELECTION_INVALID", 409)
            workbook_source, _document, content = xlsx.intake()._document(
                db, actor, draft_id, source_id, get_settings().storage_root
            )
            if any(
                ref["source_sha256"] != content.sha256
                or ref["source_size_bytes"] != len(content.content)
                or ref["document_sha256"] != workbook_source.document_sha256
                for ref in refs
            ):
                raise PackageError("PACKAGE_XLSX_SOURCE_CHANGED", 409)
            members[f"evidence/{source_id}.xlsx"] = content.content
    if selected.docx_sources:
        from . import draft_scope_docx as docx

        for source_id in selected.docx_sources:
            refs = [
                ref for ref in scope.get("evidence_refs", []) if ref.get("source_id") == source_id
            ]
            if not refs or any(
                ref.get("origin") != "local_retained" or ref.get("source_kind") != "docx"
                for ref in refs
            ):
                raise PackageError("PACKAGE_DOCX_SELECTION_INVALID", 409)
            word_source, _document, content = docx.intake()._document(
                db, actor, draft_id, source_id, get_settings().storage_root
            )
            if any(
                ref["source_sha256"] != content.sha256
                or ref["source_size_bytes"] != len(content.content)
                or ref["document_sha256"] != word_source.document_sha256
                for ref in refs
            ):
                raise PackageError("PACKAGE_DOCX_SOURCE_CHANGED", 409)
            members[f"evidence/{source_id}.docx"] = content.content
    sources = source_manifest(
        scope,
        match,
        estimate,
        selected.pdf_sources,
        selected.xlsx_sources,
        selected.docx_sources,
        match_collection=collection,
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
            "system_match": "included" if match or collection else "not_selected",
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
    origin_row = db.scalar(
        select(DraftPackageImport).where(DraftPackageImport.draft_scope_id == draft_id)
    )
    if origin_row is not None:
        from .draft_import_reports import original_archive
        from .draft_package_materialization import read_import

        origin_row, _original, mapping = read_import(db, actor, draft_id, export=True)
        origin_content = original_archive(db, actor, draft_id, settings=get_settings())
        path = f"origins/{origin_row.archive_hash}.zip"
        members[path] = origin_content
        manifest.update(
            schema_version=SCHEMA_V2,
            origins=[
                {
                    "import_id": origin_row.id,
                    "path": path,
                    "sha256": origin_row.archive_hash,
                    "mapping": mapping,
                }
            ],
            notice=(
                "Selected Draft revisions plus original imported archives; "
                "foreign history and source claims remain unverified."
            ),
        )
        manifest["members"] = [
            {"path": name, "sha256": digest(value), "size_bytes": len(value)}
            for name, value in sorted(members.items())
        ]
    if selected.pdf_sources:
        manifest.update(
            schema_version=SCHEMA_V3,
            origins=manifest.get("origins", []),
            notice=(
                "Selected Draft revisions and explicitly selected project PDFs. "
                "Unselected sources stay external or withheld; "
                "imported claims remain unverified."
            ),
        )
    if selected.xlsx_sources:
        manifest.update(
            schema_version=SCHEMA_V4,
            origins=manifest.get("origins", []),
            notice=(
                "Selected Draft revisions and explicitly selected project evidence files. "
                "Unselected sources stay external or withheld; imported claims stay unverified."
            ),
        )
    if selected.docx_sources:
        manifest.update(
            schema_version=SCHEMA_V5,
            origins=manifest.get("origins", []),
            notice=(
                "Selected Draft revisions and explicitly selected project evidence files. "
                "Unselected sources stay external or withheld; imported claims stay unverified."
            ),
        )
    if selected.matches:
        manifest.update(
            schema_version=SCHEMA_V6,
            origins=manifest.get("origins", []),
            notice=(
                "Explicitly selected Draft revisions and row reviews only. "
                "Additional reviews do not become estimate or report inputs. "
                "Source membership stays explicit; imported claims remain unverified."
            ),
        )
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
    for reference in selected_match_references(chosen):
        old = matches.read_match_revision(
            db, actor, draft_id, reference.match_id, reference.match_revision
        )
        if (
            matches.read_match_revision(db, actor, draft_id, reference.match_id)["sha256"]
            != old["sha256"]
        ):
            reasons.append("PACKAGE_REVIEW_CHANGED")
        reasons.extend(
            matches.match_staleness(
                db,
                actor,
                draft_id,
                reference.match_id,
                reference.match_revision,
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
