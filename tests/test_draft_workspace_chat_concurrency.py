"""A waiting context reader must not block unrelated HTTP requests."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event, Timer

import pytest
from fastapi.testclient import TestClient
from test_draft_scope_ui import _csrf, _login
from test_draft_workspace_chat import case as _case
from test_draft_workspace_chat import payload
from test_draft_workspace_chat import scope_app as _scope_app
from test_draft_workspace_chat import scope_password_hash as _password_hash

from classifire.services import draft_workspace_chat as chat

case = _case
scope_app = _scope_app
scope_password_hash = _password_hash


@pytest.mark.parametrize("workspace", [False, True])
def test_waiting_context_keeps_server_responsive(case, monkeypatch, workspace):
    entered, release = Event(), Event()

    def waiting_reader(*args, **kwargs):
        entered.set()
        assert release.wait(10), "Test rescue did not release reader"
        return {"context_sha256": "a" * 64}

    monkeypatch.setattr(
        chat, "workspace_context" if workspace else "selected_context", waiting_reader
    )
    path = (
        "/workspace/assistant/context"
        if workspace
        else f"/scopes/{case.draft_id}/assistant/context"
    )
    body = (
        {
            "screen": {"name": "scope"},
            "draft_id": case.draft_id,
            "revision": 2,
            "question": "Preview selected context",
        }
        if workspace
        else payload()
    )
    with TestClient(case.app) as client, ThreadPoolExecutor(max_workers=1) as workers:
        _login(client)
        headers = {"X-CSRF-Token": _csrf(client.get("/scopes").text)}
        pending = workers.submit(client.post, path, json=body, headers=headers)
        assert entered.wait(5), "Context reader was not reached"
        # Rescue lets the pre-fix test terminate rather than hang the test process.
        rescue = Timer(3, release.set)
        rescue.start()
        try:
            status = client.get("/workspace/assistant")
            responsive_before_release = not release.is_set()
        finally:
            release.set()
            rescue.cancel()
        assert pending.result(timeout=5).status_code == 200
        assert status.status_code == 200
        assert responsive_before_release, "Context work blocked unrelated HTTP traffic"
        assert not case.port.calls
