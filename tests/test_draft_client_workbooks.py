from __future__ import annotations

import hashlib

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
from test_draft_scope_ui import _assert_no_canonical_scope
from test_draft_scope_xlsx import mapping_plan, workbook_bytes

from classifire import draft_client_workbook_tools as tools
from classifire.draft_client_auth import READ
from classifire.draft_scope_xlsx_ui import router
from classifire.models import DraftClientRequest, DraftScopeXlsxSource, User
from classifire.services import draft_client_capabilities as capabilities
from classifire.services import draft_scope as scopes
from classifire.services.remote_file_retrieval import RetrievedFile

postgresql_session_factory = _postgres_fixture
scope_password_hash = _password_fixture

pdf_client_case = _pdf_client_case


@pytest.fixture
def workbook_case(pdf_client_case, monkeypatch):
    c = pdf_client_case
    c.app.include_router(router)
    # Production registers browser routes before the catch-all MCP mount. The
    # reused PDF fixture already mounted MCP, so restore that same ordering here.
    mount = next(route for route in c.app.router.routes
                 if getattr(route, "name", None) == "draft-client-mcp")
    c.app.router.routes.remove(mount)
    c.app.router.routes.append(mount)
    c.xlsx_content = workbook_bytes()
    monkeypatch.setattr(tools, 'get_settings', lambda: c.settings)
    monkeypatch.setattr(capabilities, 'get_settings', lambda: c.settings)
    monkeypatch.setattr('classifire.draft_scope_xlsx_ui.get_settings', lambda: c.settings)

    def retrieve(url, policy):
        c.fetched.append(url)
        assert policy.content_kind == 'xlsx'
        assert policy.allowed_hosts == frozenset({'files.example.test'})
        assert policy.maximum_bytes <= 10 * 1024 * 1024
        return RetrievedFile(content=c.xlsx_content,
            sha256=hashlib.sha256(c.xlsx_content).hexdigest(), size_bytes=len(c.xlsx_content),
            media_type=tools.XLSX_MEDIA, host='files.example.test')

    monkeypatch.setattr(tools, 'retrieve_file', retrieve)
    return c


def prepare(client, c):
    args = {'draft_id': c.draft_id, 'file': {
        'download_url': 'https://files.example.test/book?token=synthetic-private',
        'file_id': 'synthetic-workbook', 'file_name': 'defects.xlsx'}}
    source = tool(client, c.token(), 'upload_draft_scope_xlsx', args)['source']
    assert source['ready'] is False
    tool(client, c.token(), 'read_draft_scope_xlsx_rows',
         {'draft_id': c.draft_id, 'source_id': source['id']}, error=True)
    source = tool(client, c.token(), 'scan_draft_scope_xlsx',
                  {'draft_id': c.draft_id, 'source_id': source['id']})['source']
    assert source['ready'] is True
    rows = tool(client, c.token(), 'read_draft_scope_xlsx_rows',
                {'draft_id': c.draft_id, 'source_id': source['id']})
    assert len(rows['sheets']) == 2
    assert any(cell['kind'] == 'formula' for cell in rows['cells'])
    image_id = rows['images'][0]['occurrence_id']
    response = rpc(client, c.token(), 'tools/call', {'name': 'read_draft_scope_xlsx_image',
        'arguments': {'draft_id': c.draft_id, 'source_id': source['id'],
                      'sheet_index': 1, 'occurrence_id': image_id}}).json()['result']
    assert any(item['type'] == 'image' for item in response['content'])
    preview = tool(client, c.token(), 'preview_draft_scope_xlsx_mapping', {
        'draft_id': c.draft_id, 'source_id': source['id'], 'expected_revision': 1,
        'expected_document_hash': source['document_sha256'], 'plan': mapping_plan()})
    content = preview['payload']
    content['openings'][0]['defect_id'] = content['defects'][0]['id']
    for service in content['services']:
        service['opening_ids'] = [content['openings'][0]['id']]
    preview['targets'][0]['image_ids'] = [image_id]
    return {'action': 'review_xlsx_scope', 'draft_id': c.draft_id,
        'source_id': source['id'], 'expected_revision': 1,
        'expected_document_hash': source['document_sha256'], 'plan': mapping_plan(),
        'content': content, 'targets': preview['targets']}


def test_xlsx_client_to_evidence_visible_human_review(workbook_case):
    c = workbook_case
    with TestClient(c.app, base_url='https://testserver') as client:
        login(client)
        operation = prepare(client, c)
        pending = tool(client, c.token(), 'propose_capability', {'operation': operation})
        with c.factory() as db:
            assert scopes.read_revision(db, db.get(User, c.owner_id), c.draft_id)['revision'] == 1
            assert db.scalar(select(func.count()).select_from(DraftClientRequest)) == 1
        page = client.get(pending['review_url'])
        assert page.status_code == 200, page.text
        for text in ('Review Scope against workbook evidence', 'defects.xlsx',
                     'D-01', 'Pipe group', 'Cable group', 'A2'):
            assert text in page.text
        assert 'synthetic-private' not in page.text
        import re
        image_path = re.search(r'<img src="([^"]+)" alt="Selected workbook picture', page.text)[1]
        image = client.get(image_path)
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"

        form = decision_form(page)
        assert client.post(pending['review_url'], data=form).status_code == 200
        assert client.post(pending['review_url'], data=form).status_code == 409
    with c.factory() as db:
        saved = scopes.read_revision(db, db.get(User, c.owner_id), c.draft_id)
        assert saved['revision'] == 2
        assert len(saved['evidence_refs']) == 4
        assert saved['content']['services'][0]['quantity'] is None
        for ref in saved['evidence_refs']:
            assert ref['source_id'] == operation['source_id']
            assert ref['document_sha256'] == operation['expected_document_hash']
            assert ref['reviewed_by'] == c.owner_id
            assert ref['origin'] == 'local_retained'
    _assert_no_canonical_scope(c.factory)


def test_xlsx_review_refuses_changed_source_and_missing_client_scope(workbook_case):
    c = workbook_case
    with TestClient(c.app, base_url='https://testserver') as client:
        login(client)
        operation = prepare(client, c)
        denied = tool(client, c.token(scopes=(READ,)), 'propose_capability',
                      {'operation': operation}, error=True)
        assert denied['isError']
        pending = tool(client, c.token(), 'propose_capability', {'operation': operation})
        page = client.get(pending['review_url'])
        form = decision_form(page)
        with c.factory() as db:
            db.get(DraftScopeXlsxSource, operation['source_id']).document_sha256 = 'a' * 64
            db.commit()
        assert client.post(pending['review_url'], data=form).status_code == 409
    with c.factory() as db:
        assert scopes.read_revision(db, db.get(User, c.owner_id), c.draft_id)['revision'] == 1
    _assert_no_canonical_scope(c.factory)


def test_xlsx_upload_refuses_foreign_read_only_and_non_xlsx_metadata(workbook_case):
    c = workbook_case
    with TestClient(c.app, base_url="https://testserver") as client:
        args = {"draft_id": c.draft_id, "file": {
            "download_url": "https://files.example.test/book", "file_id": "synthetic",
            "file_name": "defects.xlsx"}}
        for token in (c.token(user="other"), c.token(scopes=(READ,))):
            tool(client, token, "upload_draft_scope_xlsx", args, error=True)
        for changes in ({"file_name": "../defects.xlsx"}, {"file_name": "defects.xlsm"},
                        {"mime_type": "application/pdf"}):
            tool(client, c.token(), "upload_draft_scope_xlsx",
                 {**args, "file": {**args["file"], **changes}}, error=True)
        assert not c.fetched
    with c.factory() as db:
        assert db.scalar(select(func.count()).select_from(DraftScopeXlsxSource)) == 0
    _assert_no_canonical_scope(c.factory)
