"""Synthetic selected history remains separate from decisions, import and package save."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_project_package_ui import fields as package_fields
from test_draft_workspace_chat import snapshot
from test_draft_workspace_proposal_decisions import (  # noqa: F401
    commit,
    evidence_app,
    generated,
    opened,
    pdf_app,
    pdf_setup,
    postgresql_session_factory,
    preview,
    scope_password_hash,
    standard_postgresql_session_factory,
    word_app,
)
from test_draft_workspace_proposal_decisions import (
    xlsx_evidence_app as _xlsx_evidence_app,
)

from classifire import draft_project_package_ui as ui
from classifire.models import (
    DraftScopeXlsxSource,
    DraftWorkspaceProposal,
    DraftWorkspaceProposalDecision,
    User,
)
from classifire.services import draft_native_history as history
from classifire.services import draft_package_import as inspection
from classifire.services import draft_package_materialization as materialization
from classifire.services import draft_project_packages as packages
from classifire.services import draft_workspace_proposals as proposals

xlsx_evidence_app = _xlsx_evidence_app


def configure(x, monkeypatch):
    x.app.include_router(ui.router)
    for module in (ui, packages, history):
        monkeypatch.setattr(module, "get_settings", lambda: x.settings)


def package(client, x, reference, revision, *, original=False):
    query = [("scope_revision", str(revision)), ("native_proposals", reference.query_value())]
    if original:
        query.append(("xlsx_sources", x.xlsx_selection["source_id"]))
    path = f"/scopes/{x.ids[2]}/packages"
    before = snapshot(x)
    page = client.get(path + "?" + urlencode(query))
    assert page.status_code == 200 and "Save package revision" in page.text, page.text
    assert snapshot(x) == before
    response = client.post(path, data=package_fields(page), follow_redirects=False)
    assert response.status_code == 303, response.text
    location = response.headers["location"]
    content = client.get(location + "/download").content
    return location, content


def test_pending_package_stays_exact_after_confirmation_and_new_original_package(
    xlsx_evidence_app, monkeypatch, tmp_path
):
    x = xlsx_evidence_app
    configure(x, monkeypatch)
    with TestClient(x.app) as client:
        path, fields, offer = generated(client, x, "xlsx")
        draft_id, identity = x.ids[2], fields["native_proposal_id"]
        base = int(fields["expected_revision"])
        page = client.get(f"/scopes/{draft_id}/packages")
        assert 'name="native_proposals"' in page.text
        assert f'value="{identity}:none" checked' not in page.text
        assert "included conversation" in page.text
        pending = history.Reference(proposal_id=identity, decision_id=None)
        old_url, old_bytes = package(client, x, pending, base)
        inspected = inspection.inspect_package(old_bytes)
        assert inspected.manifest["schema_version"] == packages.SCHEMA_V7
        member = history.member_path(identity)
        value = json.loads(inspected.members[member])
        assert value["proposal"] == offer["document"] and value["decision"] is None
        assert value["proposal_sha256"] == proposals._hash(proposals._raw(offer["document"]))
        confirmation = preview(client, path, fields, "xlsx")
        assert commit(client, path, confirmation, "xlsx").status_code == 303
        decision = opened(client, x, identity)["decision"]
        assert client.get(old_url + "/download").content == old_bytes
        old_page = client.get(old_url + "?" + urlencode({"history": member}))
        assert old_page.status_code == 200
        assert old_page.text.count("<h2>Retained AI proposal history</h2>") == 1
        assert "Retained AI proposal history" not in old_page.text.split("</head>", 1)[0]
        (tmp_path / "saved-history.html").write_text(old_page.text, encoding="utf-8")
        pinned = history.Reference(proposal_id=identity, decision_id=decision["id"])
        new_url, new_bytes = package(client, x, pinned, base + 1, original=True)
        inspected = inspection.inspect_package(new_bytes)
        assert inspected.histories[0]["decision"] == decision
        assert (
            inspected.members[f"evidence/{x.xlsx_selection['source_id']}.xlsx"] == x.xlsx_original
        )
        raw_history = client.get(new_url + "/native-history?" + urlencode({"member": member}))
        assert raw_history.status_code == 200 and raw_history.content == inspected.members[member]
        assert raw_history.headers["x-content-type-options"] == "nosniff"
        before = snapshot(x)
        assert client.get(new_url + "/native-history?member=manifest.json").status_code == 404
        assert client.get(new_url + "?history=missing").status_code == 404
        assert snapshot(x) == before
        assert len(x.calls) == 1
        (tmp_path / "pending.zip").write_bytes(old_bytes)
        (tmp_path / "confirmed-with-original.zip").write_bytes(new_bytes)

        with x.factory() as db:
            source = db.get(DraftScopeXlsxSource, x.xlsx_selection["source_id"])
            scan = json.loads(source.scan_json)
            scan["database_date"] = (datetime.now(UTC) - timedelta(days=90)).isoformat()
            source.scan_json = json.dumps(scan)
            db.commit()
        before = snapshot(x)
        for suffix in ("", "/download", "/native-history?" + urlencode({"member": member})):
            refused = client.get(new_url + suffix)
            assert refused.status_code == 409, refused.text
            assert offer["document"]["request"]["question"] not in refused.text
        assert snapshot(x) == before and len(x.calls) == 1


def test_imported_history_reopens_and_reexports_without_local_proposal_authority(
    xlsx_evidence_app, monkeypatch, tmp_path
):
    x = xlsx_evidence_app
    configure(x, monkeypatch)
    with TestClient(x.app) as client:
        _path, fields, _offer = generated(client, x, "xlsx")
        identity = fields["native_proposal_id"]
        selected = history.Reference(proposal_id=identity, decision_id=None)
        _url, content = package(client, x, selected, int(fields["expected_revision"]))
        before = snapshot(x)
        with x.factory() as db:
            actor = db.get(User, x.ids[0])
            result = inspection.preview_import(db, actor, content)
            assert result["native_history_count"] == 1
        assert snapshot(x) == before
        with x.factory() as db:
            actor = db.get(User, x.ids[0])
            row = materialization.create_import(
                db,
                actor,
                content,
                expected_sha256=packages.digest(content),
                reference="HISTORY-IMPORT",
                name="Synthetic historical claims",
                settings=x.settings,
            )
            imported_id = row.draft_scope_id
            db.commit()
        member = history.member_path(identity)
        imported_url = f"/scopes/{imported_id}/imported-package"
        page = client.get(imported_url + "?" + urlencode({"history": member}))
        assert page.status_code == 200 and "foreign and unverified" in page.text
        assert page.text.count("<h2>Retained AI proposal history</h2>") == 1
        assert "Retained AI proposal history" not in page.text.split("</head>", 1)[0]
        assert "Original generation and selected decision" in page.text
        (tmp_path / "imported-history.html").write_text(page.text, encoding="utf-8")
        raw = client.get(imported_url + "/native-history?" + urlencode({"member": member}))
        assert raw.status_code == 200
        assert raw.content == inspection.inspect_package(content).members[member]
        assert client.get(f"/scopes/{imported_id}/native-proposals").json() == {"proposals": []}
        assert client.get(f"/scopes/{imported_id}/native-proposals/{identity}").status_code == 404
        with x.factory() as db:
            actor = db.get(User, x.ids[0])
            value = {"scope_revision": 1}
            previewed = packages.preview(db, actor, imported_id, value)
            exported = packages.create_package(
                db, actor, imported_id, value, 0, previewed["preview_hash"]
            )
            exported_bytes = bytes(exported.archive_bytes)
            assert db.scalar(select(func.count()).select_from(DraftWorkspaceProposal)) == 1
            assert db.scalar(select(func.count()).select_from(DraftWorkspaceProposalDecision)) == 0
            db.commit()
        nested = inspection.inspect_package(exported_bytes)
        entries = list(nested.history_members())
        assert len(entries) == 1 and "!" in entries[0][1]
        assert nested.resolve(entries[0][1]) == raw.content
        assert next(iter(nested.origins.values())).archive_sha256 == packages.digest(content)

        saved_url = f"/scopes/{imported_id}/packages/{exported.id}"
        saved_page = client.get(saved_url + "?" + urlencode({"history": entries[0][1]}))
        assert saved_page.status_code == 200, saved_page.text
        assert "Original generation and selected decision" in saved_page.text
        saved_raw = client.get(
            saved_url + "/native-history?" + urlencode({"member": entries[0][1]})
        )
        assert saved_raw.status_code == 200 and saved_raw.content == raw.content
        (tmp_path / "nested-history.zip").write_bytes(exported_bytes)
        assert len(x.calls) == 1


def test_rehashed_history_lies_and_implicit_decision_selection_are_refused(
    xlsx_evidence_app, monkeypatch
):
    x = xlsx_evidence_app
    configure(x, monkeypatch)
    with TestClient(x.app) as client:
        path, fields, _ = generated(client, x, "xlsx")
        assert (
            commit(client, path, preview(client, path, fields, "xlsx"), "xlsx").status_code == 303
        )
        decision = opened(client, x, fields["native_proposal_id"])["decision"]
        reference = history.Reference(
            proposal_id=fields["native_proposal_id"], decision_id=decision["id"]
        )
        _url, content = package(client, x, reference, int(fields["expected_revision"]) + 1)
        parsed = inspection.inspect_package(content)
        member = history.member_path(reference.proposal_id)
        for change in ("decision", "changed_flag", "scope", "draft", "version", "inventory"):
            manifest, members = copy.deepcopy(parsed.manifest), dict(parsed.members)
            value = json.loads(members[member])
            if change == "decision":
                manifest["selection"]["native_proposals"][0]["decision_id"] = None
            elif change == "changed_flag":
                value["decision"]["proposal_payload_changed"] = True
                value["decision_sha256"] = proposals._hash(proposals._raw(value["decision"]))
            elif change == "scope":
                value["decision"]["scope_sha256"] = "0" * 64
                value["decision_sha256"] = proposals._hash(proposals._raw(value["decision"]))
            elif change == "draft":
                value["proposal"]["context"]["draft_id"] = x.ids[0]
                value["proposal_sha256"] = proposals._hash(proposals._raw(value["proposal"]))
            elif change == "version":
                manifest["schema_version"] = packages.SCHEMA_V6
            else:
                manifest["selection"]["native_proposals"] = []
            members[member] = packages.encode(value)
            manifest["members"] = [
                {"path": name, "sha256": packages.digest(raw), "size_bytes": len(raw)}
                for name, raw in sorted(members.items())
            ]
            bad = packages._archive(manifest, members)
            with pytest.raises(packages.PackageError):
                inspection.inspect_package(bad)
        with pytest.raises(packages.PackageError, match="SELECTION"):
            packages.selection(
                {"scope_revision": 1, "native_proposals": [{"proposal_id": reference.proposal_id}]}
            )
        with pytest.raises(packages.PackageError, match="SELECTION"):
            packages.selection(
                {"scope_revision": 1, "native_proposals": [reference.model_dump()] * 2}
            )


def test_unselected_later_decision_corruption_does_not_invalidate_old_package(
    xlsx_evidence_app, monkeypatch
):
    x = xlsx_evidence_app
    configure(x, monkeypatch)
    with TestClient(x.app) as client:
        _path, fields, _ = generated(client, x, "xlsx")
        identity = fields["native_proposal_id"]
        pending = history.Reference(proposal_id=identity, decision_id=None)
        old_url, old_bytes = package(client, x, pending, int(fields["expected_revision"]))
        with x.factory() as db:
            actor = db.get(User, x.ids[0])
            proposals.reject(db, actor, x.ids[2], identity, settings=x.settings)
            db.commit()
        decision = opened(client, x, identity)["decision"]
        selected = history.Reference(proposal_id=identity, decision_id=decision["id"])
        selected_url, selected_bytes = package(
            client, x, selected, int(fields["expected_revision"])
        )
        assert (
            inspection.inspect_package(selected_bytes).histories[0]["decision"]["outcome"]
            == "rejected"
        )
        with x.factory() as db:
            row = db.get(DraftWorkspaceProposalDecision, decision["id"])
            row.decision_sha256 = "0" * 64
            db.commit()
        before = snapshot(x)
        with x.factory() as db:
            actor = db.get(User, x.ids[0])
            row, _ = packages.read_package(db, actor, x.ids[2], old_url.rsplit("/", 1)[1])
            assert row.archive_bytes == old_bytes
            with pytest.raises(packages.PackageError, match="INTEGRITY"):
                packages.read_package(db, actor, x.ids[2], selected_url.rsplit("/", 1)[1])
        assert snapshot(x) == before
