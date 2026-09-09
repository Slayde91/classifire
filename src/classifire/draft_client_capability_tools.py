"""Independent capability tools and retained report transport for the Draft client."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import StrictInt
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings
from .draft_client_auth import (
    ESTIMATE,
    EXPORT,
    READ,
    TECHNICAL,
    WRITE,
    ClientAuthority,
    ClientIdentity,
)
from .services import draft_client_capabilities as capabilities
from .services import draft_client_requests as commands
from .services import draft_estimate_reports as estimate_reports
from .services import draft_estimates as estimates
from .services import draft_pricing_coverage as pricing_coverage
from .services import draft_pricing_evaluation_rosters as pricing_rosters
from .services import draft_pricing_intake as pricing
from .services import draft_pricing_recipes as pricing_recipes
from .services import draft_scope as scopes
from .services import draft_scope_reports as scope_reports
from .services import draft_system_matches as matches
from .services.draft_source_intake import MAX_SOURCES

Kind = Literal["system-match", "estimate", "scope-report", "estimate-report"]


def read_artifact(
    db: Session,
    authority: ClientAuthority,
    principal: ClientIdentity,
    draft_id: str,
    kind: Kind,
    artifact_id: str,
    revision: int | None,
    estimate_id: str | None,
) -> dict[str, Any]:
    actor = commands.authorize(db, authority, principal, READ, draft_id)
    root = get_settings().storage_root
    stale: list[str] | bool
    if kind == "system-match":
        capabilities.require(db, authority, principal, TECHNICAL)
        content = matches.read_match_revision(db, actor, draft_id, artifact_id, revision)
        stale = matches.match_staleness(
            db, actor, draft_id, artifact_id, revision, storage_root=root
        )
    elif kind == "estimate":
        capabilities.require(db, authority, principal, ESTIMATE)
        content = estimates.read_estimate_revision(db, actor, draft_id, artifact_id, revision)
        capabilities.protect_content(db, authority, principal, content)
        stale = estimates.estimate_staleness(
            db, actor, draft_id, artifact_id, revision, storage_root=root
        )
    elif kind == "scope-report":
        if revision is not None or estimate_id is not None:
            raise scopes.DraftScopeError("CLIENT_REPORT_INPUT_INVALID", 422)
        content = scope_reports.read_report(db, actor, draft_id, artifact_id)
        capabilities.protect_content(db, authority, principal, content)
        stale = scope_reports.report_freshness(db, actor, draft_id, artifact_id, storage_root=root)
    else:
        if revision is not None or estimate_id is None:
            raise scopes.DraftScopeError("CLIENT_REPORT_INPUT_INVALID", 422)
        capabilities.require(db, authority, principal, ESTIMATE)
        content = estimate_reports.read_report(db, actor, draft_id, estimate_id, artifact_id)
        capabilities.protect_content(db, authority, principal, content)
        stale = estimate_reports.report_staleness(
            db, actor, draft_id, estimate_id, artifact_id, storage_root=root
        )
    return {"artifact": content, "staleness": stale}


def report_content(
    db: Session,
    authority: ClientAuthority,
    principal: ClientIdentity,
    draft_id: str,
    report_id: str,
    format_name: str,
    estimate_id: str | None,
) -> bytes:
    actor = commands.authorize(db, authority, principal, EXPORT, draft_id)
    # The shared retained reader checks ownership, integrity, source containment and
    # current domain rights. The client additionally limits nested capability access.
    if estimate_id is None:
        snapshot = scope_reports.read_report(db, actor, draft_id, report_id)
        capabilities.protect_content(db, authority, principal, snapshot)
        return scope_reports.report_bytes(db, actor, draft_id, report_id, format_name)
    capabilities.require(db, authority, principal, ESTIMATE)
    snapshot = estimate_reports.read_report(db, actor, draft_id, estimate_id, report_id)
    capabilities.protect_content(db, authority, principal, snapshot)
    return estimate_reports.report_bytes(db, actor, draft_id, estimate_id, report_id, format_name)


def register(
    app: FastAPI,
    server: MCPServer,
    authority: ClientAuthority,
    factory: sessionmaker[Session],
    identity: Callable[[], ClientIdentity],
    propose: Callable[[str, dict[str, Any]], dict[str, Any]],
) -> None:
    from .draft_client import _client_session

    base = authority.initial.base_url
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)

    @server.tool(
        annotations=write, meta={"securitySchemes": [{"type": "oauth2", "scopes": [READ, WRITE]}]}
    )
    def propose_capability(operation: capabilities.CapabilityCommand) -> dict[str, Any]:
        """Propose ONE independent Match, Estimate or report operation. Requires technical/estimate
        scope for relevant content. Report inputs are saved revisions; nothing runs downstream.
        Human confirmation executes shared validation and may refuse invalid domain inputs.
        """
        return propose("capability", operation.model_dump(mode="json"))

    @server.tool(
        annotations=read,
        meta={"securitySchemes": [{"type": "oauth2", "scopes": [READ, TECHNICAL]}]},
    )
    def list_technical_releases() -> dict[str, Any]:
        """List current technical release IDs. A listed release is not proof of applicability."""
        with _client_session(factory) as db:
            try:
                principal = identity()
                actor = commands.authorize(db, authority, principal, READ)
                capabilities.require(db, authority, principal, TECHNICAL)
                return {"releases": matches.list_technical_releases(db, actor)}
            except scopes.DraftScopeError as exc:
                raise ToolError(exc.code) from None

    @server.tool(
        annotations=read,
        meta={"securitySchemes": [{"type": "oauth2", "scopes": [READ, ESTIMATE]}]},
    )
    def list_pricing_sources(draft_id: str) -> dict[str, Any]:
        """List retained workbook metadata for an owned Draft. Library read permission is
        also required. Ready is metadata only; preview verifies current source bytes.
        Upload and scan remain separate actions in the standalone UI.
        """
        with _client_session(factory) as db:
            try:
                principal = identity()
                actor = commands.authorize(db, authority, principal, READ, draft_id)
                capabilities.require(db, authority, principal, ESTIMATE)
                return {
                    "sources": pricing.intake().list_sources(db, actor, draft_id),
                    "limit": MAX_SOURCES,
                }
            except scopes.DraftScopeError as exc:
                raise ToolError(exc.code) from None

    @server.tool(
        annotations=read,
        meta={"securitySchemes": [{"type": "oauth2", "scopes": [READ, ESTIMATE]}]},
    )
    def preview_pricing_rows(
        draft_id: str,
        source_id: str,
        sheet_index: StrictInt = 1,
        header_row: StrictInt = 1,
        mapping: capabilities.PricingMapping | None = None,
        after_row: StrictInt = 0,
    ) -> dict[str, Any]:
        """Inspect five workbook rows after an actual worksheet row number. Without a
        mapping, show sheet summaries and sample cells capped at 200 characters with
        explicit truncation markers. With a complete mapping, return exact mapped cells,
        row hashes and unresolved problems. No rate is applied or formula evaluated.
        Requires estimating scope, current library read permission and verified source.
        """
        with _client_session(factory) as db:
            try:
                principal = identity()
                actor = commands.authorize(db, authority, principal, READ, draft_id)
                capabilities.require(db, authority, principal, ESTIMATE)
                if any(type(value) is not int for value in (sheet_index, header_row, after_row)):
                    raise scopes.DraftScopeError("PRICING_MAPPING_INVALID", 422)
                settings = get_settings()
                source, document, _ = pricing.intake()._document(
                    db, actor, draft_id, source_id, settings.storage_root
                )
                sheets = document["sheets"]
                if not 1 <= sheet_index <= len(sheets):
                    raise scopes.DraftScopeError("PRICING_MAPPING_INVALID", 422)
                sheet = sheets[sheet_index - 1]
                if not 1 <= header_row <= sheet["rows"] or not 0 <= after_row <= sheet["rows"]:
                    raise scopes.DraftScopeError("PRICING_MAPPING_INVALID", 422)
                limit = 5
                if mapping is not None:
                    source, mapped = pricing.preview(
                        db,
                        actor,
                        draft_id,
                        source_id,
                        sheet_index,
                        header_row,
                        mapping.model_dump(),
                        settings=settings,
                    )
                    remaining = [row for row in mapped if row["row"] > after_row]
                    rows = remaining[:limit]
                    return {
                        "mode": "mapped",
                        "source": capabilities.pricing_source_binding(source),
                        "rows": rows,
                        "next_after_row": rows[-1]["row"] if len(remaining) > limit else None,
                        "limit": limit,
                    }
                end_row = min(after_row + limit, sheet["rows"])
                samples = []
                for number in range(after_row + 1, end_row + 1):
                    cells = []
                    for cell in sheet["cells"]:
                        if cell["row"] != number:
                            continue
                        value = cell["value"]
                        cells.append(
                            cell
                            | {
                                "value": value[:200],
                                "truncated": len(value) > 200,
                                "original_length": len(value),
                            }
                        )
                    samples.append({"row": number, "cells": cells})
                return {
                    "mode": "unmapped",
                    "source": capabilities.pricing_source_binding(source),
                    "sheets": [
                        {key: item[key] for key in ("index", "name", "rows", "columns")}
                        for item in sheets
                    ],
                    "rows": samples,
                    "next_after_row": end_row if end_row < sheet["rows"] else None,
                    "limit": limit,
                }
            except scopes.DraftScopeError as exc:
                raise ToolError(exc.code) from None
            except (ValueError, TypeError, KeyError, IndexError):
                raise ToolError("PRICING_MAPPING_INVALID") from None

    @server.tool(
        annotations=read,
        meta={
            "securitySchemes": [
                {"type": "oauth2", "scopes": [READ, ESTIMATE, TECHNICAL]}
            ]
        },
    )
    def preview_pricing_coverage(draft_id: str, technical_release_id: str) -> dict[str, Any]:
        """Preview exact evidence coverage for every target in one technical release.

        This read-only result contains evidence identities and hashes, not prices. It does
        not assess project applicability, create a proposal, change an Estimate, activate
        pricing evidence or grant technical approval.
        """
        with _client_session(factory) as db:
            try:
                principal = identity()
                actor = commands.authorize(db, authority, principal, READ, draft_id)
                capabilities.require(db, authority, principal, ESTIMATE)
                capabilities.require(db, authority, principal, TECHNICAL)
                return pricing_coverage.preview_coverage(
                    db,
                    actor,
                    draft_id,
                    technical_release_id,
                    settings=get_settings(),
                )
            except scopes.DraftScopeError as exc:
                raise ToolError(exc.code) from None

    @server.tool(
        annotations=read,
        meta={
            "securitySchemes": [
                {"type": "oauth2", "scopes": [READ, ESTIMATE, TECHNICAL]}
            ]
        },
    )
    def list_pricing_evaluation_rosters(
        draft_id: str, before_revision: StrictInt | None = None
    ) -> dict[str, Any]:
        """List up to 20 saved target-blind evaluation-roster summaries.

        Results contain commitments and hashes, never target price values. Pass the
        returned next_before_revision to read an older page. No roster is created or
        changed and no evaluation is performed.
        """
        with _client_session(factory) as db:
            try:
                principal = identity()
                actor = commands.authorize(db, authority, principal, READ, draft_id)
                capabilities.require(db, authority, principal, ESTIMATE)
                capabilities.require(db, authority, principal, TECHNICAL)
                if before_revision is not None and (
                    type(before_revision) is not int or before_revision < 1
                ):
                    raise scopes.DraftScopeError(
                        "PRICING_EVALUATION_ROSTER_LIST_INVALID", 422
                    )
                rows = pricing_rosters.list_rosters(
                    db,
                    actor,
                    draft_id,
                    settings=get_settings(),
                    before_revision=before_revision,
                    limit=21,
                )
                page = rows[:20]
                return {
                    "rosters": [
                        {
                            "roster_id": item["id"],
                            "revision": item["revision"],
                            "created_at": item["value"]["created_at"],
                            "roster_sha256": item["value"]["roster_sha256"],
                            "content_sha256": item["roster_sha256"],
                            "manifest_sha256": item["manifest_sha256"],
                            "mapping_inventory_sha256": item[
                                "mapping_inventory_sha256"
                            ],
                            "is_current": item["is_current"],
                        }
                        for item in page
                    ],
                    "next_before_revision": (
                        page[-1]["revision"] if len(rows) > len(page) else None
                    ),
                    "limit": 20,
                }
            except scopes.DraftScopeError as exc:
                raise ToolError(exc.code) from None

    @server.tool(
        annotations=read,
        meta={
            "securitySchemes": [
                {"type": "oauth2", "scopes": [READ, ESTIMATE, TECHNICAL]}
            ]
        },
    )
    def read_pricing_evaluation_roster(draft_id: str, roster_id: str) -> dict[str, Any]:
        """Read one exact saved target-blind evaluation roster.

        The roster commits target fields by hash without revealing target price values.
        This operation does not run evaluation, change pricing or grant approval.
        """
        with _client_session(factory) as db:
            try:
                principal = identity()
                actor = commands.authorize(db, authority, principal, READ, draft_id)
                capabilities.require(db, authority, principal, ESTIMATE)
                capabilities.require(db, authority, principal, TECHNICAL)
                content = pricing_rosters.roster_bytes(db, actor, draft_id, roster_id)
                return {
                    "roster": json.loads(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size_bytes": len(content),
                }
            except scopes.DraftScopeError as exc:
                raise ToolError(exc.code) from None

    @server.tool(
        annotations=read,
        meta={
            "securitySchemes": [
                {"type": "oauth2", "scopes": [READ, ESTIMATE, TECHNICAL]}
            ]
        },
    )
    def list_pricing_recipe_links(
        draft_id: str, before_link_id: str | None = None
    ) -> dict[str, Any]:
        """List up to 20 saved recipe-link summaries without changing them.

        Pass next_before_link_id to read an older page. Results expose reviewed
        evidence state and dependency hashes but do not calculate or activate prices.
        """
        with _client_session(factory) as db:
            try:
                principal = identity()
                actor = commands.authorize(db, authority, principal, READ, draft_id)
                capabilities.require(db, authority, principal, ESTIMATE)
                capabilities.require(db, authority, principal, TECHNICAL)
                rows = pricing_recipes.list_recipe_links(
                    db,
                    actor,
                    draft_id,
                    settings=get_settings(),
                    before_link_id=before_link_id,
                    limit=21,
                )
                page = rows[:20]
                return {
                    "links": [
                        {
                            "link_id": item["id"],
                            "reviewed_at": item["value"]["reviewed_at"],
                            "link_sha256": item["link_sha256"],
                            "definition_sha256": item["value"]["definition_sha256"],
                            "technical_release_id": item["value"]["definition"][
                                "technical_release"
                            ]["id"],
                            "technical_release_sha256": item["value"]["definition"][
                                "technical_release"
                            ]["sha256"],
                            "technical_target_id": item["value"]["definition"][
                                "technical_target"
                            ]["id"],
                            "technical_variant_snapshot_sha256": item["value"][
                                "definition"
                            ]["technical_target"]["snapshot_sha256"],
                            "recipe_snapshot_sha256": item["value"]["definition"][
                                "technical_target"
                            ]["recipe_snapshot_sha256"],
                            "requirement_id": item["value"]["definition"]["requirement"][
                                "id"
                            ],
                            "requirement_kind": item["value"]["definition"][
                                "requirement"
                            ]["kind"],
                            "requirement_path": item["value"]["definition"][
                                "requirement"
                            ]["path"],
                            "requirement_label": item["value"]["definition"][
                                "requirement"
                            ]["label"],
                            "status": item["value"]["definition"]["interpretation"][
                                "status"
                            ],
                            "evidence_state": item["value"]["definition"][
                                "interpretation"
                            ]["evidence_state"],
                            "observation_count": len(
                                item["value"]["definition"]["observations"]
                            ),
                            "current": item["current"],
                        }
                        for item in page
                    ],
                    "next_before_link_id": (
                        page[-1]["id"] if len(rows) > len(page) else None
                    ),
                    "limit": 20,
                }
            except scopes.DraftScopeError as exc:
                raise ToolError(exc.code) from None

    @server.tool(
        annotations=read,
        meta={
            "securitySchemes": [
                {"type": "oauth2", "scopes": [READ, ESTIMATE, TECHNICAL]}
            ]
        },
    )
    def read_pricing_recipe_link(draft_id: str, link_id: str) -> dict[str, Any]:
        """Read one exact saved recipe link without changing authority or pricing."""
        with _client_session(factory) as db:
            try:
                principal = identity()
                actor = commands.authorize(db, authority, principal, READ, draft_id)
                capabilities.require(db, authority, principal, ESTIMATE)
                capabilities.require(db, authority, principal, TECHNICAL)
                content = pricing_recipes.recipe_link_bytes(db, actor, draft_id, link_id)
                return {
                    "link": json.loads(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size_bytes": len(content),
                }
            except scopes.DraftScopeError as exc:
                raise ToolError(exc.code) from None

    @server.tool(annotations=read, meta={"securitySchemes": [{"type": "oauth2", "scopes": [READ]}]})
    def list_capability_artifacts(
        draft_id: str, kind: Kind, estimate_id: str | None = None
    ) -> dict[str, Any]:
        """List saved artifacts of ONE kind. Estimate reports require their parent estimate ID.
        Match and commercial records require their respective technical/estimate client scopes.
        """
        with _client_session(factory) as db:
            try:
                principal = identity()
                actor = commands.authorize(db, authority, principal, READ, draft_id)
                rows: Any
                if kind == "system-match":
                    capabilities.require(db, authority, principal, TECHNICAL)
                    rows = matches.list_matches(db, actor, draft_id)
                elif kind == "estimate":
                    capabilities.require(db, authority, principal, ESTIMATE)
                    rows = estimates.list_estimates(db, actor, draft_id)
                elif kind == "scope-report":
                    rows = scope_reports.list_reports(db, actor, draft_id)
                else:
                    capabilities.require(db, authority, principal, ESTIMATE)
                    if estimate_id is None:
                        raise scopes.DraftScopeError("CLIENT_REPORT_INPUT_INVALID", 422)
                    rows = estimate_reports.list_reports(db, actor, draft_id, estimate_id)
                visible = []
                for row in rows:
                    # Do not leak nested technical artifact metadata through a weaker grant.
                    try:
                        if kind == "estimate":
                            content = estimates.read_estimate_revision(db, actor, draft_id, row.id)
                        elif kind == "scope-report":
                            content = scope_reports.read_report(db, actor, draft_id, row.id)
                        elif kind == "estimate-report" and estimate_id is not None:
                            content = estimate_reports.read_report(
                                db, actor, draft_id, estimate_id, row.id
                            )
                        else:
                            content = {}
                        capabilities.protect_content(db, authority, principal, content)
                    except scopes.DraftScopeError as exc:
                        if exc.status_code == 403:
                            continue
                        raise
                    visible.append(
                        {"artifact_id": row.id, "revision": getattr(row, "latest_revision", None)}
                    )
                return {"artifacts": visible, "limit": 20}
            except scopes.DraftScopeError as exc:
                raise ToolError(exc.code) from None

    @server.tool(annotations=read, meta={"securitySchemes": [{"type": "oauth2", "scopes": [READ]}]})
    def read_capability_artifact(
        draft_id: str,
        kind: Kind,
        artifact_id: str,
        revision: int | None = None,
        estimate_id: str | None = None,
    ) -> dict[str, Any]:
        """Read a saved artifact and current staleness. Reports use saved report IDs.
        Technical/estimate scopes are enforced for the content, including nested saved inputs.
        """
        with _client_session(factory) as db:
            try:
                return read_artifact(
                    db, authority, identity(), draft_id, kind, artifact_id, revision, estimate_id
                )
            except scopes.DraftScopeError as exc:
                raise ToolError(exc.code) from None

    @server.tool(
        annotations=read, meta={"securitySchemes": [{"type": "oauth2", "scopes": [READ, EXPORT]}]}
    )
    def report_download(
        draft_id: str,
        report_id: str,
        format_name: Literal["pdf", "xlsx"],
        estimate_id: str | None = None,
    ) -> dict[str, Any]:
        """Get an exact saved PDF/XLSX link without rerendering or running another capability."""
        with _client_session(factory) as db:
            try:
                content = report_content(
                    db, authority, identity(), draft_id, report_id, format_name, estimate_id
                )
                suffix = f"/estimates/{estimate_id}" if estimate_id else ""
                path = f"/{draft_id}{suffix}/reports/{report_id}/{format_name}"
                db.commit()
                return {
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size_bytes": len(content),
                    "authenticated_url": base + "/api/draft-client" + path,
                    "browser_url": (
                        base
                        + f"/scopes/{draft_id}{suffix}/reports/{report_id}"
                        + f"/download?format={format_name}"
                    ),
                    "authentication": "OAuth bearer for authenticated_url; login for browser_url",
                }
            except scopes.DraftScopeError as exc:
                raise ToolError(exc.code) from None

    def download(
        request: Request,
        draft_id: str,
        report_id: str,
        format_name: str,
        estimate_id: str | None = None,
    ) -> Response:
        header = request.headers.get("authorization", "")
        principal = authority.verify(header[7:]) if header.startswith("Bearer ") else None
        if principal is None:
            return JSONResponse(
                {"detail": "CLIENT_AUTHORIZATION_REQUIRED"},
                status_code=401,
                headers={
                    "WWW-Authenticate": 'Bearer resource_metadata="'
                    + base
                    + '/.well-known/oauth-protected-resource/mcp"'
                },
            )
        with factory() as db:
            try:
                content = report_content(
                    db, authority, principal, draft_id, report_id, format_name, estimate_id
                )
                db.commit()
                return Response(
                    content,
                    media_type="application/pdf"
                    if format_name == "pdf"
                    else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={
                        "Cache-Control": "no-store",
                        "X-Content-Type-Options": "nosniff",
                        "Content-Disposition": (
                            f'attachment; filename="classifire-draft.{format_name}"'
                        ),
                    },
                )
            except scopes.DraftScopeError as exc:
                return JSONResponse({"detail": exc.code}, status_code=exc.status_code)

    app.add_api_route(
        "/api/draft-client/{draft_id}/reports/{report_id}/{format_name}",
        download,
        methods=["GET"],
        include_in_schema=False,
    )
    app.add_api_route(
        "/api/draft-client/{draft_id}/estimates/{estimate_id}/reports/{report_id}/{format_name}",
        download,
        methods=["GET"],
        include_in_schema=False,
    )
