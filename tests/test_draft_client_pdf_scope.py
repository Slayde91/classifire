from __future__ import annotations

import base64
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_client import tool
from test_draft_client_pdf_intake import pdf_client_case as _pdf_client_case
from test_draft_client_pdf_intake import (  # noqa: F401
    postgresql_session_factory,
    scope_password_hash,
)
from test_draft_pdf_scope_review import _graph, _targets
from test_draft_scope_ui import PASSWORD, _assert_no_canonical_scope, _csrf

from classifire.draft_client_auth import READ
from classifire.models import (
    DraftClientRequest,
    DraftEstimate,
    DraftEstimateReport,
    DraftPdfSource,
    DraftScopeReport,
    DraftSystemMatch,
    User,
)
from classifire.services import draft_client_capabilities as capabilities
from classifire.services import draft_scope as scopes

pdf_client_case = _pdf_client_case


@pytest.fixture
def review_case(pdf_client_case, monkeypatch):
    c = pdf_client_case
    monkeypatch.setattr(capabilities, "get_settings", lambda: c.settings)
    monkeypatch.setattr("classifire.draft_pdf_ui.get_settings", lambda: c.settings)
    return c


def login(client):
    page = client.get("/login")
    response = client.post("/login", data={
        "email": "owner@pdf-client.example.test", "password": PASSWORD,
        "csrf_token": _csrf(page.text),
    }, follow_redirects=False)
    assert response.status_code == 303


def prepare(client, c):
    source = tool(client, c.token(), "upload_draft_pdf", {
        "draft_id": c.draft_id, "file": {
            "download_url": "https://files.example.test/report.pdf",
            "file_id": "synthetic", "file_name": "inspection.pdf",
        },
    })["source"]
    source = tool(client, c.token(), "scan_draft_pdf", {
        "draft_id": c.draft_id, "source_id": source["id"],
    })["source"]
    content = _graph([])
    return {
        "action": "review_pdf_scope", "draft_id": c.draft_id,
        "source_id": source["id"], "expected_revision": 1,
        "page_number": 1, "expected_document_hash": source["document_sha256"],
        "content": content, "targets": _targets(content),
    }


def proposal(client, c, operation, **kwargs):
    return tool(client, c.token(), "propose_capability", {"operation": operation}, **kwargs)


def decision_form(page):
    return {"csrf_token": _csrf(page.text), "decision": "confirm",
            "payload_hash": re.search(r'name="payload_hash" value="([^"]+)"', page.text)[1]}


def test_client_pdf_review_saves_only_after_human_confirmation(review_case, tmp_path):
    c = review_case
    with TestClient(c.app, base_url="https://testserver") as client:
        login(client)
        operation = prepare(client, c)
        pending = proposal(client, c, operation)
        with c.factory() as db:
            scope = scopes.read_revision(db, db.get(User, c.owner_id), c.draft_id)
            assert scope["revision"] == 1
            assert not scope.get("evidence_refs")
            assert db.scalar(select(func.count()).select_from(DraftClientRequest)) == 1
            _assert_no_canonical_scope(c.factory)
        page = client.get(pending["review_url"])
        assert page.status_code == 200, page.text
        for text in ("Review Scope against the PDF page", "inspection.pdf",
                     "ChatGPT selected PDF evidence", "Pipe group", "Cable group",
                     "Proposed Scope content", "Page locator"):
            assert text in page.text
        image = client.get(f"/scopes/{c.draft_id}/evidence/{operation['source_id']}/pages/1.png")
        assert image.status_code == 200
        assert image.content.startswith(b"\x89PNG")
        rendered = page.text.replace(
            f'/scopes/{c.draft_id}/evidence/{operation["source_id"]}/pages/1.png',
            "data:image/png;base64," + base64.b64encode(image.content).decode("ascii"),
        )
        (tmp_path / "synthetic-review.html").write_text(rendered, encoding="utf-8")
        form = decision_form(page)
        response = client.post(pending["review_url"], data=form)
        assert response.status_code == 200, response.text
        assert client.post(pending["review_url"], data=form).status_code == 409
        saved = tool(client, c.token(), "read_draft_scope", {"draft_id": c.draft_id})
        # The source reader may return a wrapper; persisted envelope is authoritative below.
        assert saved
    with c.factory() as db:
        scope = scopes.read_revision(db, db.get(User, c.owner_id), c.draft_id)
        assert scope["revision"] == 2
        assert len(scope["evidence_refs"]) == 5
        for ref in scope["evidence_refs"]:
            assert ref["source_id"] == operation["source_id"]
            assert ref["document_sha256"] == operation["expected_document_hash"]
            assert ref["page_number"] == 1
            assert ref["reviewed_by"] == c.owner_id
            assert ref["method"] == "human_page_entity_review"
            assert ref["origin"] == "local_retained"
            assert ref["locator_key"] and ref["target_sha256"]
        assert len(scope["content"]["openings"]) == 2
        assert len(scope["content"]["services"]) == 2
        for model in (DraftSystemMatch, DraftEstimate, DraftScopeReport, DraftEstimateReport):
            assert db.scalar(select(func.count()).select_from(model)) == 0
        _assert_no_canonical_scope(c.factory)


def test_source_change_after_review_prevents_save(review_case):
    c = review_case
    with TestClient(c.app, base_url="https://testserver") as client:
        login(client)
        operation = prepare(client, c)
        pending = proposal(client, c, operation)
        page = client.get(pending["review_url"])
        assert page.status_code == 200
        form = decision_form(page)
        with c.factory() as db:
            source = db.get(DraftPdfSource, operation["source_id"])
            source.document_sha256 = "a" * 64
            db.commit()
        result = client.post(pending["review_url"], data=form)
        assert result.status_code == 409
    with c.factory() as db:
        assert scopes.read_revision(db, db.get(User, c.owner_id), c.draft_id)["revision"] == 1
        assert db.get(DraftClientRequest, pending["request_id"]).status == "pending"
        _assert_no_canonical_scope(c.factory)


def test_pdf_review_rejects_foreign_missing_scope_and_forged_target(review_case):
    c = review_case
    with TestClient(c.app, base_url="https://testserver") as client:
        operation = prepare(client, c)
        for token in (c.token(user="other"), c.token(scopes=(READ,))):
            result = tool(client, token, "propose_capability", {"operation": operation}, error=True)
            assert result["isError"]
        forged = dict(operation, targets=[{"target_kind": "service", "target_id": "missing"}])
        assert "PDF_REVIEW_TARGETS_INVALID" in str(proposal(client, c, forged, error=True))
        forged = dict(operation, reviewed_by=c.owner_id)
        assert proposal(client, c, forged, error=True)["isError"]
    with c.factory() as db:
        assert db.scalar(select(func.count()).select_from(DraftClientRequest)) == 0
        assert scopes.read_revision(db, db.get(User, c.owner_id), c.draft_id)["revision"] == 1
