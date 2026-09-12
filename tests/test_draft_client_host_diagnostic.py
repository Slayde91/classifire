from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, select
from test_draft_client import rpc
from test_draft_client_pdf_intake import pdf_client_case as _case
from test_draft_client_pdf_intake import postgresql_session_factory as _postgres
from test_draft_client_pdf_intake import scope_password_hash as _password

from classifire import draft_client_evidence_tools as pdf
from classifire import draft_client_word_tools as word
from classifire import draft_client_workbook_tools as xlsx
from classifire.services import remote_file_retrieval as retrieval

pdf_client_case = _case
postgresql_session_factory = _postgres
scope_password_hash = _password


def database_rows(factory):
    with factory() as db:
        metadata = MetaData()
        metadata.reflect(bind=db.bind)
        return {
            name: sorted([dict(row) for row in db.execute(select(table)).mappings()], key=str)
            for name, table in metadata.tables.items()
        }


@pytest.mark.parametrize(
    "adapter,tool_name,extension",
    [
        (pdf, "upload_draft_pdf", "pdf"),
        (xlsx, "upload_draft_scope_xlsx", "xlsx"),
        (word, "upload_draft_scope_word", "docx"),
    ],
)
def test_authenticated_upload_returns_host_only_without_retaining_or_saving(
    pdf_client_case, monkeypatch, adapter, tool_name, extension
):
    case = pdf_client_case
    monkeypatch.setattr(adapter, "get_settings", lambda: case.settings)
    monkeypatch.setattr(adapter, "retrieve_file", retrieval.retrieve_file)
    before = database_rows(case.factory)
    with TestClient(case.app, base_url="https://testserver") as client:
        response = rpc(
            client,
            case.token(),
            "tools/call",
            {
                "name": tool_name,
                "arguments": {
                    "draft_id": case.draft_id,
                    "file": {
                        "file_id": "synthetic-private-file-id",
                        "file_name": "private-name." + extension,
                        "download_url": "https://delivery.example.test/private-path?sig=secret-query",
                    },
                },
            },
        ).json()["result"]
    assert response["isError"] is True
    body = json.loads(response["content"][0]["text"].split(": ", 1)[-1])
    assert body["code"] == "CLIENT_FILE_UNAPPROVED_HOST"
    assert body["rejected_host"] == "delivery.example.test"
    serialized = json.dumps(response)
    for secret in ("private-path", "secret-query", "private-name", "synthetic-private-file-id"):
        assert secret not in serialized
    assert database_rows(case.factory) == before
    assert list(case.settings.storage_root.iterdir()) == []
