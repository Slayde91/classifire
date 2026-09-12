from __future__ import annotations

import copy
import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_client import rpc, tool
from test_draft_client_pdf_intake import (  # noqa: F401
    pdf_client_case as _pdf_client_case,
)
from test_draft_client_pdf_intake import postgresql_session_factory as _postgres_fixture
from test_draft_client_pdf_intake import scope_password_hash as _password_fixture
from test_draft_client_pdf_scope import decision_form, login
from test_draft_pdf_scope_review import _graph, _targets
from test_draft_scope_docx_review import word_graph_bytes
from test_draft_scope_ui import _assert_no_canonical_scope

from classifire import draft_client_word_tools as tools
from classifire.draft_client_auth import READ
from classifire.draft_scope_docx_ui import router
from classifire.models import DraftClientRequest, DraftScopeDocxSource, User
from classifire.services import draft_client_capabilities as capabilities
from classifire.services import draft_scope as scopes
from classifire.services.remote_file_retrieval import RetrievedFile

postgresql_session_factory = _postgres_fixture
scope_password_hash = _password_fixture

pdf_client_case = _pdf_client_case


@pytest.fixture
def word_case(pdf_client_case, monkeypatch):
    c = pdf_client_case
    c.app.include_router(router)
    # Production registers browser routes before the catch-all MCP mount. The
    # reused PDF fixture already mounted MCP, so restore that same ordering here.
    mount = next(
        route for route in c.app.router.routes if getattr(route, "name", None) == "draft-client-mcp"
    )
    c.app.router.routes.remove(mount)
    c.app.router.routes.append(mount)
    c.word_content = word_graph_bytes()
    monkeypatch.setattr(tools, "get_settings", lambda: c.settings)
    monkeypatch.setattr(capabilities, "get_settings", lambda: c.settings)
    monkeypatch.setattr("classifire.draft_scope_docx_ui.get_settings", lambda: c.settings)

    def retrieve(url, policy):
        c.fetched.append(url)
        assert policy.content_kind == "docx"
        assert policy.allowed_hosts == frozenset({"files.example.test"})
        assert policy.maximum_bytes <= 10 * 1024 * 1024
        return RetrievedFile(
            content=c.word_content,
            sha256=hashlib.sha256(c.word_content).hexdigest(),
            size_bytes=len(c.word_content),
            media_type=tools.WORD_MEDIA,
            host="files.example.test",
        )

    monkeypatch.setattr(tools, "retrieve_file", retrieve)
    return c


def prepare(client, c):
    args = {
        "draft_id": c.draft_id,
        "file": {
            "download_url": "https://files.example.test/report?token=synthetic-private",
            "file_id": "synthetic-word",
            "file_name": "defects.docx",
        },
    }
    response = tool(client, c.token(), "upload_draft_scope_word", args)
    assert response["review_url"].startswith("https://testserver/scopes/" + c.draft_id + "/word/")
    source = response["source"]
    assert source["ready"] is False
    tool(
        client,
        c.token(),
        "read_draft_scope_word_text",
        {"draft_id": c.draft_id, "source_id": source["id"]},
        error=True,
    )
    source = tool(
        client,
        c.token(),
        "scan_draft_scope_word",
        {"draft_id": c.draft_id, "source_id": source["id"]},
    )["source"]
    assert source["ready"] is True
    document = tool(
        client,
        c.token(),
        "read_draft_scope_word_text",
        {"draft_id": c.draft_id, "source_id": source["id"]},
    )
    assert len(document["blocks"]) == 4 and document["next_after_block"] is None
    assert document["blocks"][-1]["locator"] == "body-3"
    assert "separate blank opening" in document["blocks"][-1]["text"]
    image_id = document["pictures"][0]["id"]
    response = rpc(
        client,
        c.token(),
        "tools/call",
        {
            "name": "read_draft_scope_word_image",
            "arguments": {
                "draft_id": c.draft_id,
                "source_id": source["id"],
                "picture_id": image_id,
            },
        },
    ).json()["result"]
    assert any(item["type"] == "image" for item in response["content"])
    content = _graph([])
    content["openings"][0]["label"] = "O-01"
    content["openings"][1].update(label="O-02", blank=True)
    for service in content["services"]:
        service["opening_ids"] = [content["openings"][0]["id"]]
    targets = [dict(target, locator="body-1", image_ids=[]) for target in _targets(content)]
    next(target for target in targets if target["target_id"] == content["openings"][1]["id"])[
        "locator"
    ] = "body-3"
    targets[0]["image_ids"] = [image_id]
    return {
        "action": "review_word_scope",
        "draft_id": c.draft_id,
        "source_id": source["id"],
        "expected_revision": 1,
        "expected_document_hash": source["document_sha256"],
        "content": content,
        "targets": targets,
    }


def test_word_client_to_evidence_visible_human_review(word_case):
    c = word_case
    with TestClient(c.app, base_url="https://testserver") as client:
        login(client)
        operation = prepare(client, c)
        malformed = copy.deepcopy(operation)
        malformed["content"]["services"][0]["quantity"] = "PRIVATE-SYNTHETIC-VALUE"
        failure = tool(
            client, c.token(), "propose_capability", {"operation": malformed}, error=True
        )
        error_text = json.dumps(failure)
        assert "DRAFT_PAYLOAD_INVALID" in error_text
        assert "services.0.quantity" in error_text
        assert "PRIVATE-SYNTHETIC-VALUE" not in error_text
        pending = tool(client, c.token(), "propose_capability", {"operation": operation})
        with c.factory() as db:
            assert scopes.read_revision(db, db.get(User, c.owner_id), c.draft_id)["revision"] == 1
            assert db.scalar(select(func.count()).select_from(DraftClientRequest)) == 1
        page = client.get(pending["review_url"])
        assert page.status_code == 200, page.text
        for text in (
            "Review Scope against Word evidence",
            "defects.docx",
            "D-01",
            "Pipe group",
            "Cable group",
            "body-3",
        ):
            assert text in page.text
        assert "synthetic-private" not in page.text
        import re

        image_path = re.search(r'<img src="([^"]+)" alt="Selected Word picture', page.text)[1]
        image = client.get(image_path)
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"

        form = decision_form(page)
        assert client.post(pending["review_url"], data=form).status_code == 200
        assert client.post(pending["review_url"], data=form).status_code == 409
    with c.factory() as db:
        saved = scopes.read_revision(db, db.get(User, c.owner_id), c.draft_id)
        assert saved["revision"] == 2
        assert len(saved["evidence_refs"]) == 5
        assert saved["content"]["services"][0]["quantity"] is None
        for ref in saved["evidence_refs"]:
            assert ref["source_id"] == operation["source_id"]
            assert ref["document_sha256"] == operation["expected_document_hash"]
            assert ref["reviewed_by"] == c.owner_id
            assert ref["origin"] == "local_retained"
    _assert_no_canonical_scope(c.factory)


def test_word_review_refuses_changed_source_and_missing_client_scope(word_case):
    c = word_case
    with TestClient(c.app, base_url="https://testserver") as client:
        login(client)
        operation = prepare(client, c)
        denied = tool(
            client,
            c.token(scopes=(READ,)),
            "propose_capability",
            {"operation": operation},
            error=True,
        )
        assert denied["isError"]
        pending = tool(client, c.token(), "propose_capability", {"operation": operation})
        page = client.get(pending["review_url"])
        form = decision_form(page)
        with c.factory() as db:
            db.get(DraftScopeDocxSource, operation["source_id"]).document_sha256 = "a" * 64
            db.commit()
        assert client.post(pending["review_url"], data=form).status_code == 409
    with c.factory() as db:
        assert scopes.read_revision(db, db.get(User, c.owner_id), c.draft_id)["revision"] == 1
    _assert_no_canonical_scope(c.factory)


def test_word_upload_refuses_foreign_read_only_and_non_word_metadata(word_case):
    c = word_case
    with TestClient(c.app, base_url="https://testserver") as client:
        args = {
            "draft_id": c.draft_id,
            "file": {
                "download_url": "https://files.example.test/book",
                "file_id": "synthetic",
                "file_name": "defects.docx",
            },
        }
        for token in (c.token(user="other"), c.token(scopes=(READ,))):
            tool(client, token, "upload_draft_scope_word", args, error=True)
        for changes in (
            {"file_name": "../defects.docx"},
            {"file_name": "defects.docm"},
            {"mime_type": "application/pdf"},
        ):
            tool(
                client,
                c.token(),
                "upload_draft_scope_word",
                {**args, "file": {**args["file"], **changes}},
                error=True,
            )
        assert not c.fetched
    with c.factory() as db:
        assert db.scalar(select(func.count()).select_from(DraftScopeDocxSource)) == 0
    _assert_no_canonical_scope(c.factory)


def test_word_discovery_exposes_exact_review_schema_without_confirmation_tool(word_case):
    c = word_case
    with TestClient(c.app, base_url="https://testserver") as client:
        discovery = rpc(client, c.token(), "tools/list", {}).json()["result"]["tools"]
        names = {entry["name"] for entry in discovery}
        assert {
            "upload_draft_scope_word",
            "list_draft_scope_word_sources",
            "scan_draft_scope_word",
            "read_draft_scope_word_text",
            "read_draft_scope_word_image",
        } <= names
        assert not any("confirm" in name or "execute" in name for name in names)
        proposal = next(entry for entry in discovery if entry["name"] == "propose_capability")
        definitions = proposal["inputSchema"]["$defs"]
        schema = definitions["ReviewWordScope"]
        assert schema["properties"]["action"]["const"] == "review_word_scope"
        assert definitions["WordReviewTarget"]["properties"]["locator"]["pattern"].startswith(
            "^body-"
        )
        assert "content" in schema["required"]
