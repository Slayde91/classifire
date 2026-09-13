"""Portable native history keeps existing selected capability bytes and bounds."""

from __future__ import annotations

from uuid import UUID

import pytest
from test_draft_package_multi_review_import import _prepared
from test_draft_project_packages import base_case as _base_case
from test_draft_project_packages import case as _case

from classifire.config import Settings
from classifire.services import draft_native_history as history
from classifire.services import draft_package_import as inspection
from classifire.services import draft_package_materialization as materialization
from classifire.services import draft_project_packages as packages
from classifire.services import draft_scope as scopes
from classifire.services import draft_workspace_chat as chat
from classifire.services import draft_workspace_proposals as proposals

base_case = _base_case
case = _case


def test_multi_review_estimate_reports_keep_exact_bytes_with_selected_history(
    case, monkeypatch, tmp_path
):
    settings = Settings(_env_file=None, storage_root=case["storage_root"])
    for module in (packages, history):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    with case["factory"]() as db:
        actor, legacy = _prepared(db, case, with_reports=True, with_estimate=True)
        old_bytes = bytes(legacy.archive_bytes)
        old = inspection.inspect_package(old_bytes)
        assert old.manifest["schema_version"] == packages.SCHEMA_V6
        scope = old.scope
        request = chat.WorkspaceChatRequest(
            screen={"name": "scope"},
            action="propose_scope_edits",
            draft_id=case["draft_id"],
            revision=scope["revision"],
            ids=[scope["content"]["openings"][0]["id"]],
            matches=old.manifest["selection"]["matches"],
            estimate={
                "estimate_id": old.estimate["artifact_id"],
                "estimate_revision": old.estimate["revision"],
            },
            records=[{"kind": "library_release", "id": case["release_id"]}],
            question="Synthetic unchanged Scope proposal for package compatibility",
            consent=True,
            include_sensitive=True,
        )
        context = chat.workspace_context(db, actor, request, settings=settings)
        request = request.model_copy(update={"context_sha256": context["context_sha256"]})
        response = {
            "edit_proposal": {
                "payload": scope["content"],
                "expected_revision": scope["revision"],
                "review_url": f"/scopes/{case['draft_id']}/edit",
            }
        }
        offer = proposals.offer(
            actor, request, context, response, {"synthetic": True}, settings=settings, injected=True
        )
        assert offer is not None
        row = proposals.retain(
            db,
            actor,
            case["draft_id"],
            offer["document"],
            offer["authorization"],
            settings=settings,
        )
        chosen = old.manifest["selection"] | {
            "native_proposals": [{"proposal_id": row.id, "decision_id": None}]
        }
        previewed = packages.preview(db, actor, case["draft_id"], chosen)
        result = packages.create_package(
            db,
            actor,
            case["draft_id"],
            chosen,
            previewed["latest_revision"],
            previewed["preview_hash"],
        )
        value = inspection.inspect_package(result.archive_bytes)
        assert value.manifest["schema_version"] == packages.SCHEMA_V7
        for path, content in old.members.items():
            assert value.members[path] == content
        assert len(value.matches) == 2 and value.estimate == old.estimate
        assert value.reports == old.reports
        assert history.permissions(value.histories[0], export=True) == {
            "project:read",
            "technical:read",
            "library:read",
            "estimate:read",
            "estimate:export",
        }
        assert b"must-never-export-source-json" not in result.archive_bytes
        assert (
            packages.read_package(db, actor, case["draft_id"], legacy.id)[0].archive_bytes
            == old_bytes
        )
        (tmp_path / "multi-capability-history.zip").write_bytes(result.archive_bytes)
        (tmp_path / "history.json").write_bytes(value.members[history.member_path(row.id)])

        # Sensitive retained context still needs export rights even when the
        # Estimate and technical artifacts themselves are not selected.
        history_only = {
            "scope_revision": scope["revision"],
            "native_proposals": chosen["native_proposals"],
        }
        previewed = packages.preview(db, actor, case["draft_id"], history_only)
        selected_history = packages.create_package(
            db,
            actor,
            case["draft_id"],
            history_only,
            previewed["latest_revision"],
            previewed["preview_hash"],
        )
        portable = bytes(selected_history.archive_bytes)
        inspected = inspection.inspect_package(portable)
        assert inspected.estimate is None and not inspected.all_matches()
        imported = materialization.create_import(
            db,
            actor,
            portable,
            expected_sha256=packages.digest(portable),
            reference="HISTORY-CONTEXT",
            name="Synthetic context permissions",
            settings=settings,
        )
        proposals.reject(db, actor, case["draft_id"], row.id, settings=settings)
        decision = proposals.reopen(db, actor, case["draft_id"], row.id, settings=settings)[
            "decision"
        ]
        rejected_selection = {
            **history_only,
            "native_proposals": [{"proposal_id": row.id, "decision_id": decision["id"]}],
        }
        rejected_preview = packages.preview(db, actor, case["draft_id"], rejected_selection)
        rejected = packages.create_package(
            db,
            actor,
            case["draft_id"],
            rejected_selection,
            rejected_preview["latest_revision"],
            rejected_preview["preview_hash"],
        )
        rejected_value = inspection.inspect_package(rejected.archive_bytes)
        assert rejected_value.histories[0]["decision"] == decision
        assert decision["outcome"] == "rejected" and decision["scope_revision"] is None
        assert rejected_value.members["artifacts/scope.json"] == old.members["artifacts/scope.json"]
        assert packages.package_bytes(db, actor, case["draft_id"], selected_history.id) == portable
        (tmp_path / "rejected-history.zip").write_bytes(rejected.archive_bytes)
        actor.role = "read_only"
        db.flush()
        # Reading the same retained proposal is allowed; exporting it is not.
        assert (
            proposals.reopen(db, actor, case["draft_id"], row.id, settings=settings)["document"][
                "id"
            ]
            == row.id
        )
        assert materialization.read_import(db, actor, imported.draft_scope_id)[1].histories
        for operation in (
            lambda: packages.preview(db, actor, case["draft_id"], history_only),
            lambda: packages.package_bytes(db, actor, case["draft_id"], selected_history.id),
            lambda: materialization.read_import(db, actor, imported.draft_scope_id, export=True),
        ):
            with pytest.raises(scopes.DraftScopeError) as denied:
                operation()
            assert denied.value.status_code == 403
        assert bytes(selected_history.archive_bytes) == portable
        actor.role = "project_manager"
        db.flush()
        # Imported history cannot bypass technical/library read restrictions.
        with pytest.raises(scopes.DraftScopeError) as denied:
            materialization.read_import(db, actor, imported.draft_scope_id)
        assert denied.value.status_code == 403


def test_empty_history_keeps_legacy_selection_and_reference_limits():
    legacy = {
        "scope_revision": 1,
        "match_id": None,
        "match_revision": None,
        "estimate_id": None,
        "estimate_revision": None,
        "scope_reports": [],
        "estimate_reports": [],
    }
    assert packages.selection({"scope_revision": 1}).model_dump() == legacy
    assert packages.selection({"scope_revision": 1, "native_proposals": []}).model_dump() == legacy
    refs = [{"proposal_id": str(UUID(int=i)), "decision_id": None} for i in range(1, 12)]
    assert (
        len(
            packages.selection(
                {"scope_revision": 1, "native_proposals": refs[:10]}
            ).native_proposals
        )
        == 10
    )
    for invalid in (
        refs,
        [refs[0], refs[0]],
        [{"proposal_id": refs[0]["proposal_id"]}],
        [{"proposal_id": "not-an-id", "decision_id": None}],
        [{"proposal_id": refs[0]["proposal_id"], "decision_id": "latest"}],
    ):
        with pytest.raises(packages.PackageError, match="SELECTION"):
            packages.selection({"scope_revision": 1, "native_proposals": invalid})


def test_portable_history_refuses_unbounded_or_nonobject_json():
    reference = history.Reference(proposal_id=str(UUID(int=1)), decision_id=None)
    for content in (
        b"x" * (history.MAX_BYTES + 1),
        b"[]",
        b"null",
        b"true",
        b'{"schema":1,"schema":2}',
    ):
        with pytest.raises(scopes.DraftScopeError, match="NATIVE_HISTORY_INVALID"):
            history.validate(content, reference, {})
