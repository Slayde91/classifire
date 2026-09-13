"""Actual PostgreSQL source/Draft locks preserve native proposal operations."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
import test_draft_workspace_proposal_decisions as cases
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_draft_workspace_chat import snapshot

from classifire.models import User
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
