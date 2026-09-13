"""Actual PostgreSQL source/Draft locks preserve native proposal operations."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
import test_draft_workspace_proposal_decisions as cases
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from test_draft_workspace_chat import snapshot

from classifire.models import DraftScopeXlsxSource, User
from classifire.services import draft_workspace_chat as chat
from classifire.services import draft_workspace_proposals as saved

edit_app = cases.edit_app
evidence_app = cases.evidence_app
pdf_app = cases.pdf_app
pdf_evidence_app = cases.pdf_evidence_app
pdf_setup = cases.pdf_setup
scope_password_hash = cases.scope_password_hash
word_app = cases.word_app
xlsx_evidence_app = cases.xlsx_evidence_app
postgresql_session_factory = cases.postgresql_session_factory
standard_postgresql_session_factory = cases.standard_postgresql_session_factory


@pytest.mark.parametrize("operation", ["review", "reject"])
def test_retention_and_decision_take_source_locks_in_consistent_order(
    xlsx_evidence_app,
    monkeypatch,
    operation,
):
    x = xlsx_evidence_app
    with TestClient(x.app) as client:
        _path, fields, offer = cases.generated(client, x, "xlsx")
    before = snapshot(x)
    source_held, decision_started = Event(), Event()
    original_context = chat.workspace_context

    def ordered_context(db, *args, **kwargs):
        if db.info.get("race_operation") == "decision":
            # Signal before attempting the source lock. The old path already holds
            # the Draft here, while retention below still owns the source.
            decision_started.set()
        result = original_context(db, *args, **kwargs)
        if db.info.get("race_operation") == "retain" and not source_held.is_set():
            source_held.set()
            assert decision_started.wait(10), "Concurrent decision did not reach source read"
        return result

    monkeypatch.setattr(chat, "workspace_context", ordered_context)

    def worker(which):
        with x.factory() as db:
            assert db.bind.dialect.name == "postgresql"
            db.execute(text("SET LOCAL lock_timeout = '8s'"))
            db.execute(text("SET LOCAL statement_timeout = '12s'"))
            db.info["race_operation"] = which
            actor = db.get(User, x.ids[0])
            if which == "retain":
                row = saved.retain(
                    db,
                    actor,
                    x.ids[2],
                    offer["document"],
                    offer["authorization"],
                    settings=x.settings,
                )
                assert row.id == fields["native_proposal_id"]
            elif operation == "reject":
                saved.reject(
                    db,
                    actor,
                    x.ids[2],
                    fields["native_proposal_id"],
                    settings=x.settings,
                )
            else:
                proposal = offer["document"]["response"]["proposal"]
                link = saved.prepare_review_link(
                    db,
                    actor,
                    x.ids[2],
                    fields["native_proposal_id"],
                    proposal["expected_revision"],
                    proposal["payload"],
                    action="propose_xlsx_scope",
                    source_id=proposal["source_id"],
                    settings=x.settings,
                )
                assert link is not None and link.proposal_id == fields["native_proposal_id"]
            db.commit()

    with ThreadPoolExecutor(max_workers=2) as workers:
        retained = workers.submit(worker, "retain")
        assert source_held.wait(10), "Retention did not acquire its source lock"
        decided = workers.submit(worker, "decision")
        retained.result(timeout=20)
        decided.result(timeout=20)
    after = snapshot(x)
    excluded = {"draft_workspace_proposal_decisions", "audit_events"}
    assert {k: v for k, v in after.items() if k not in excluded} == {
        k: v for k, v in before.items() if k not in excluded
    }
    assert after["draft_workspace_proposals"] == before["draft_workspace_proposals"]
    assert len(after["draft_workspace_proposal_decisions"]) == (operation == "reject")
    if operation == "review":
        assert after == before, "Review preparation and duplicate retention must not write"
    else:
        assert set(before["audit_events"]).issubset(after["audit_events"])
        added_audits = set(after["audit_events"]) - set(before["audit_events"])
        assert len(added_audits) == 1
        assert "workspace_proposal.rejected" in added_audits.pop()
    with x.factory() as db:
        opened = saved.reopen(
            db,
            db.get(User, x.ids[0]),
            x.ids[2],
            fields["native_proposal_id"],
            settings=x.settings,
        )
        assert opened["document"] == offer["document"]
        assert (opened["decision"] or {}).get("outcome") == (
            "rejected" if operation == "reject" else None
        )
    assert len(x.calls) == 1, "No provider call, retry or implicit capability during race"


def test_rejection_rechecks_write_permission_after_waiting_on_source(
    xlsx_evidence_app,
    monkeypatch,
    tmp_path,
):
    x = xlsx_evidence_app
    entered = Event()
    blocked_pid = []
    original_context = chat.workspace_context

    def observed_context(db, *args, **kwargs):
        if not entered.is_set():
            blocked_pid.append(db.scalar(text("SELECT pg_backend_pid()")))
            entered.set()
        return original_context(db, *args, **kwargs)

    with TestClient(x.app) as client:
        _path, fields, offer = cases.generated(client, x, "xlsx")
        identity = fields["native_proposal_id"]
        path = f"/scopes/{x.ids[2]}/native-proposals/{identity}/reject"
        monkeypatch.setattr(chat, "workspace_context", observed_context)
        with x.factory() as locker, ThreadPoolExecutor(max_workers=1) as workers:
            locker_pid = locker.scalar(text("SELECT pg_backend_pid()"))
            locker.scalar(
                select(DraftScopeXlsxSource)
                .where(DraftScopeXlsxSource.id == x.xlsx_selection["source_id"])
                .with_for_update()
            )
            waiting = workers.submit(
                client.post,
                path,
                data={"csrf_token": fields["csrf_token"], "confirm": "reject"},
            )
            try:
                assert entered.wait(10), "Rejection never reached source context"
                deadline = time.monotonic() + 10
                with x.factory() as observer:
                    while True:
                        blockers = observer.scalar(
                            text("SELECT pg_blocking_pids(:pid)"),
                            {"pid": blocked_pid[0]},
                        )
                        if locker_pid in blockers:
                            break
                        assert time.monotonic() < deadline, "No actual source lock wait observed"
                        time.sleep(0.01)
                # Revoke only writing: the actor still owns the Draft and may read it.
                with x.factory() as admin:
                    admin.execute(update(User).where(User.id == x.ids[0]).values(role="read_only"))
                    admin.commit()
                before = snapshot(x)
            finally:
                locker.rollback()
            response = waiting.result(timeout=20)
        after = snapshot(x)
        result = {
            "source_lock_wait_observed": True,
            "response_status": response.status_code,
            "response": response.json(),
            "state_unchanged_after_role_revocation": after == before,
            "decision_count": len(after["draft_workspace_proposal_decisions"]),
            "provider_calls": len(x.calls),
        }
        (tmp_path / "rejection-race-result.json").write_text(json.dumps(result, indent=2))
        assert response.status_code == 403, result
        assert response.json()["detail"] == "DRAFT_PERMISSION_DENIED"
        assert after == before, "Refused rejection must not save a decision or audit event"
        value = cases.opened(client, x, identity)
        assert value["document"] == offer["document"]
        assert value["decision"] is None and value["can_reject"] is False
        assert snapshot(x) == after
        assert len(x.calls) == 1, "No model retry or implicit downstream capability"
