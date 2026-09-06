"""Independent capability tools and retained report transport for the Draft client."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
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
from .services import draft_scope as scopes
from .services import draft_scope_reports as scope_reports
from .services import draft_system_matches as matches

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
