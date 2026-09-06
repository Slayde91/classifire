"""Bounded single-file multipart forms shared by Draft UI entry points."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from starlette.datastructures import UploadFile

from .security import verify_csrf


async def single_file(request: Request, max_bytes: int) -> dict[str, Any]:
    """Callers authorize before reading; multipart temporary files close on every exit."""
    if request.headers.get("content-type", "").split(";")[0].strip() != "multipart/form-data":
        raise HTTPException(415, "Choose a file using the upload form")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > max_bytes + 16384:
            raise HTTPException(413, "Source upload exceeds the size limit")
        body.extend(chunk)
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": bytes(body), "more_body": False}

    parsed_request = Request(request.scope, receive=receive)
    async with parsed_request.form(max_files=1, max_fields=1) as form:
        if set(form) != {"csrf_token", "file"} or any(len(form.getlist(k)) != 1 for k in form):
            raise HTTPException(422, "Choose one source file")
        token = form.get("csrf_token")
        verify_csrf(request, token if isinstance(token, str) else None)
        file = form["file"]
        if not isinstance(file, UploadFile):
            raise HTTPException(422, "Choose one source file")
        if file.size is not None and file.size > max_bytes:
            raise HTTPException(413, "Source upload exceeds the size limit")
        content = await file.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise HTTPException(413, "Source upload exceeds the size limit")
        return {"filename": file.filename or "", "content": content}
