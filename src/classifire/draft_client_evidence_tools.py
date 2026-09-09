"""ChatGPT/MCP tools for retained Draft PDF evidence intake and review."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings
from .draft_client_auth import READ, WRITE, ClientAuthority, ClientIdentity
from .services import draft_client_requests as commands
from .services import draft_pdf_intake as pdf
from .services import draft_scope as scopes
from .services.draft_pdf_worker import MAX_PDF_BYTES
from .services.malware_scan import MAX_SCAN_BYTES
from .services.remote_file_retrieval import (
    RemoteFilePolicy,
    RemoteFileRetrievalError,
    RetrievedFile,
    retrieve_file,
)


class ChatGPTFile(BaseModel):
    """The documented ChatGPT file parameter shape."""

    model_config = ConfigDict(extra="forbid", strict=True)

    download_url: str = Field(min_length=1, max_length=4096)
    file_id: str = Field(min_length=1, max_length=512)
    mime_type: str | None = Field(default=None, max_length=100)
    file_name: str | None = Field(default=None, max_length=200)


def _source_result(base: str, draft_id: str, source: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": source,
        "review_url": base + f"/scopes/{draft_id}/evidence/{source['id']}",
    }


def _validate_file_metadata(file: ChatGPTFile) -> None:
    if any(ord(character) < 32 or ord(character) == 127 for character in file.file_id):
        raise scopes.DraftScopeError("CLIENT_PDF_FILE_INVALID")
    if file.mime_type is not None and file.mime_type.strip().lower() not in {
        "application/pdf",
        "application/octet-stream",
    }:
        raise scopes.DraftScopeError("CLIENT_PDF_MEDIA_TYPE_INVALID")
    if file.file_name is not None:
        name = file.file_name.replace("\\", "/").rsplit("/", 1)[-1]
        if (
            name != file.file_name
            or not name.lower().endswith(".pdf")
            or any(ord(character) < 32 or ord(character) == 127 for character in name)
        ):
            raise scopes.DraftScopeError("CLIENT_PDF_FILE_INVALID")


def _filename(file: ChatGPTFile, retrieved: RetrievedFile) -> str:
    return file.file_name or f"chatgpt-{retrieved.sha256[:16]}.pdf"


def register(
    app: FastAPI,
    server: MCPServer,
    authority: ClientAuthority,
    factory: sessionmaker[Session],
    identity: Callable[[], ClientIdentity],
) -> None:
    """Register evidence tools over the same services used by the standalone UI."""

    del app
    from .draft_client import _client_session

    base = authority.initial.base_url
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
    remote_write = ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, openWorldHint=True
    )
    read_meta = {"securitySchemes": [{"type": "oauth2", "scopes": [READ]}]}
    write_meta = {"securitySchemes": [{"type": "oauth2", "scopes": [READ, WRITE]}]}

    @server.tool(
        annotations=remote_write,
        meta=write_meta | {"openai/fileParams": ["file"]},
    )
    def upload_draft_pdf(draft_id: str, file: ChatGPTFile) -> dict[str, Any]:
        """Retain one user-selected PDF as untrusted Draft evidence. This does not scan,
        interpret, approve, or change the saved Scope. Call scan_draft_pdf separately.
        """

        with _client_session(factory) as db:
            try:
                principal = identity()
                actor = commands.authorize(db, authority, principal, WRITE, draft_id)
                _validate_file_metadata(file)
                settings = get_settings()
                policy = RemoteFilePolicy(
                    allowed_hosts=frozenset(settings.draft_client_file_download_hosts),
                    maximum_bytes=min(
                        settings.max_upload_bytes,
                        MAX_SCAN_BYTES,
                        MAX_PDF_BYTES,
                    ),
                )
                retrieved = retrieve_file(file.download_url, policy)
                source = pdf.retain_pdf(
                    db,
                    actor,
                    draft_id,
                    _filename(file, retrieved),
                    retrieved.content,
                    settings=settings,
                )
                info = pdf.source_info(db, actor, draft_id, source.id)
                db.commit()
                result = _source_result(base, draft_id, info)
                result["retrieval"] = {
                    "file_id": file.file_id,
                    "sha256": retrieved.sha256,
                    "size_bytes": retrieved.size_bytes,
                    "media_type": retrieved.media_type,
                    "host": retrieved.host,
                    "redirect_count": retrieved.redirect_count,
                }
                return result
            except RemoteFileRetrievalError as exc:
                raise ToolError("CLIENT_FILE_" + exc.code) from None
            except scopes.DraftScopeError as exc:
                raise ToolError(exc.code) from None

    @server.tool(annotations=read, meta=read_meta)
    def list_draft_pdf_sources(draft_id: str) -> dict[str, Any]:
        """List retained PDF evidence for an owned Draft. Ready means the retained bytes
        passed the current scan and parser boundaries; it is not human approval.
        """

        with _client_session(factory) as db:
            try:
                actor = commands.authorize(db, authority, identity(), READ, draft_id)
                return {
                    "sources": [
                        _source_result(base, draft_id, source)
                        for source in pdf.list_sources(db, actor, draft_id)
                    ],
                    "limit": pdf.MAX_SOURCES,
                }
            except scopes.DraftScopeError as exc:
                raise ToolError(exc.code) from None

    @server.tool(annotations=write, meta=write_meta)
    def scan_draft_pdf(draft_id: str, source_id: str) -> dict[str, Any]:
        """Explicitly scan and parse one retained PDF. This updates evidence processing
        state only; it does not create observations, defects, openings, services, or Scope.
        """

        with _client_session(factory) as db:
            try:
                actor = commands.authorize(db, authority, identity(), WRITE, draft_id)
                settings = get_settings()
                pdf.scan_source(db, actor, draft_id, source_id, settings=settings)
                info = pdf.source_info(db, actor, draft_id, source_id)
                db.commit()
                return _source_result(base, draft_id, info)
            except scopes.DraftScopeError as exc:
                raise ToolError(exc.code) from None

    @server.tool(annotations=read, meta=read_meta)
    def read_draft_pdf_page(
        draft_id: str,
        source_id: str,
        page_number: StrictInt,
    ) -> dict[str, Any]:
        """Read one parsed PDF page with its exact page locator and hashes. The page text
        is evidence for review, not an approved defect or physical-model conclusion.
        """

        with _client_session(factory) as db:
            try:
                actor = commands.authorize(db, authority, identity(), READ, draft_id)
                settings = get_settings()
                document = pdf.read_document(
                    db, actor, draft_id, source_id, settings=settings
                )
                if not 1 <= page_number <= len(document["pages"]):
                    raise scopes.DraftScopeError("PDF_PAGE_NOT_FOUND", 404)
                source = pdf.source_info(db, actor, draft_id, source_id)
                return {
                    **_source_result(base, draft_id, source),
                    "document": {
                        "schema": document["schema"],
                        "parser": document["parser"],
                        "manifest": document["manifest"],
                        "page_count": len(document["pages"]),
                    },
                    "page": document["pages"][page_number - 1],
                }
            except scopes.DraftScopeError as exc:
                raise ToolError(exc.code) from None
