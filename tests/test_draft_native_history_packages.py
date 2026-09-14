"""Synthetic selected history remains separate from decisions, import and package save."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from starlette.requests import Request
from test_draft_project_package_ui import fields as package_fields
from test_draft_workspace_chat import snapshot
from test_draft_workspace_proposal_decisions import (  # noqa: F401
    commit,
    evidence_app,
    generated,
    opened,
    pdf_app,
    pdf_evidence_app,
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


@pytest.mark.parametrize("kind,fixture", [("word", "evidence_app"), ("pdf", "pdf_evidence_app")])
def test_word_pdf_history_keeps_original_and_foreign_decision_read_only(
    request, kind, fixture, monkeypatch, tmp_path
):
    x = request.getfixturevalue(fixture)
    configure(x, monkeypatch)
    with TestClient(x.app) as client:
        review_path, fields, offer = generated(client, x, kind)
        identity = fields["native_proposal_id"]
        source_id = offer["document"]["request"][kind]["source_id"]
        if kind == "word":
            downloaded = client.get(f"/scopes/{x.ids[2]}/word/{source_id}/original")
            assert downloaded.status_code == 200
            original = downloaded.content
        else:
            original = x.pdf_original
        pending = history.Reference(proposal_id=identity, decision_id=None)
        old_url, old_bytes = package(client, x, pending, int(fields["expected_revision"]))
        confirmation = preview(client, review_path, fields, kind)
        assert commit(client, review_path, confirmation, kind).status_code == 303
        decision = opened(client, x, identity)["decision"]
        assert decision["outcome"] == "confirmed"
        assert client.get(old_url + "/download").content == old_bytes
        selected = history.Reference(proposal_id=identity, decision_id=decision["id"])
        collection, extension = (
            ("docx_sources", "docx") if kind == "word" else ("pdf_sources", "pdf")
        )
        path = f"/scopes/{x.ids[2]}/packages"
        query = [
            ("scope_revision", str(decision["scope_revision"])),
            ("native_proposals", selected.query_value()),
            (collection, source_id),
        ]
        before = snapshot(x)
        shown = client.get(path + "?" + urlencode(query))
        assert shown.status_code == 200 and snapshot(x) == before
        saved = client.post(path, data=package_fields(shown), follow_redirects=False)
        assert saved.status_code == 303
        saved_url = saved.headers["location"]
        archive_response = client.get(saved_url + "/download")
        assert archive_response.status_code == 200
        content = archive_response.content
        inspected = inspection.inspect_package(content)
        assert inspected.manifest["schema_version"] == packages.SCHEMA_V7
        assert inspected.members[f"evidence/{source_id}.{extension}"] == original
        member = history.member_path(identity)
        retained = inspected.histories[0]
        assert retained["proposal"] == offer["document"] and retained["decision"] == decision
        raw = client.get(saved_url + "/native-history?" + urlencode({"member": member}))
        assert raw.status_code == 200 and raw.content == inspected.members[member]
        assert any(
            item["kind"] == "native_proposal_source"
            and item["membership"] == "included"
            and item["reference"].startswith(kind + ":" + source_id + ":document:")
            for item in inspected.manifest["source_manifest"]
        )
        before = snapshot(x)
        inspected_page = client.post(
            "/package-import/preview",
            data={"csrf_token": fields["csrf_token"]},
            files={"file": ("synthetic-history.zip", content, "application/zip")},
        )
        assert inspected_page.status_code == 200 and snapshot(x) == before
        assert "1 retained AI history items" in inspected_page.text
        imported = client.post(
            "/package-import/confirm",
            data={
                **package_fields(inspected_page),
                "reference": "HISTORY-" + kind.upper(),
                "name": "Synthetic " + kind + " history",
                "confirm": "yes",
            },
            files={"file": ("synthetic-history.zip", content, "application/zip")},
            follow_redirects=False,
        )
        assert imported.status_code == 303, imported.text
        imported_url = imported.headers["location"]
        page = client.get(imported_url + "?" + urlencode({"history": member}))
        assert page.status_code == 200 and "foreign and unverified" in page.text
        imported_raw = client.get(imported_url + "/native-history?" + urlencode({"member": member}))
        assert imported_raw.status_code == 200 and imported_raw.content == raw.content
        imported_id = imported_url.split("/")[2]
        assert client.get(f"/scopes/{imported_id}/native-proposals").json() == {"proposals": []}
        assert client.get(f"/scopes/{imported_id}/native-proposals/{identity}").status_code == 404
        with x.factory() as db:
            assert db.scalar(select(func.count()).select_from(DraftWorkspaceProposal)) == 1
            assert db.scalar(select(func.count()).select_from(DraftWorkspaceProposalDecision)) == 1
        assert len(x.calls) == 1
        (tmp_path / (kind + "-original." + extension)).write_bytes(original)
        (tmp_path / (kind + "-history.zip")).write_bytes(content)
        (tmp_path / (kind + "-history.json")).write_bytes(raw.content)
        (tmp_path / (kind + "-imported-history.html")).write_text(page.text, encoding="utf-8")


class HistoryOptions(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.options = {}
        self.values = set()
        self.chosen = set()
        self.current = None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and attrs.get("name") == "native_proposals":
            self.values.add(attrs["value"])
            if "checked" in attrs:
                self.chosen.add(attrs["value"])
        if tag == "select" and attrs.get("name") == "native_proposals":
            self.current = attrs["id"]
            self.options[self.current] = {}
        elif tag == "option" and self.current is not None:
            self.options[self.current][attrs["value"]] = "selected" in attrs
            self.values.add(attrs["value"])
            if "selected" in attrs and attrs["value"]:
                self.chosen.add(attrs["value"])

    def handle_endtag(self, tag):
        if tag == "select":
            self.current = None


def test_package_form_can_export_generation_without_recorded_decision(
    xlsx_evidence_app, monkeypatch, tmp_path
):
    x = xlsx_evidence_app
    configure(x, monkeypatch)
    with TestClient(x.app) as client:
        path, fields, _ = generated(client, x, "xlsx")
        identity = fields["native_proposal_id"]
        control = "native-history-" + identity
        package_path = f"/scopes/{x.ids[2]}/packages"
        before = snapshot(x)
        pending_page = client.get(package_path)
        assert pending_page.status_code == 200 and snapshot(x) == before
        pending_options = HistoryOptions(pending_page.text)
        assert identity + ":none" in pending_options.values
        assert not pending_options.chosen
        assert (
            commit(client, path, preview(client, path, fields, "xlsx"), "xlsx").status_code == 303
        )
        decision = opened(client, x, identity)["decision"]
        decision_value = identity + ":" + decision["id"]
        before = snapshot(x)
        page = client.get(package_path)
        assert page.status_code == 200 and snapshot(x) == before
        options = HistoryOptions(page.text)
        assert identity + ":none" in options.values, (
            "A recorded decision must not remove the proposal-only choice"
        )
        assert decision_value in options.values and not options.chosen
        archives = []
        for chosen, expected_decision in ((identity + ":none", None), (decision_value, decision)):
            before = snapshot(x)
            shown = client.get(
                package_path
                + "?"
                + urlencode(
                    [
                        ("scope_revision", str(decision["scope_revision"])),
                        ("native_proposals", ""),
                        ("native_proposals", chosen),
                    ]
                )
            )
            assert shown.status_code == 200 and snapshot(x) == before
            selected = HistoryOptions(shown.text).options[control]
            assert selected[chosen] and sum(selected.values()) == 1
            response = client.post(package_path, data=package_fields(shown), follow_redirects=False)
            assert response.status_code == 303
            url = response.headers["location"] + "/download"
            content = client.get(url).content
            parsed = inspection.inspect_package(content)
            assert parsed.histories[0]["decision"] == expected_decision
            assert parsed.manifest["selection"]["native_proposals"] == [
                {
                    "proposal_id": identity,
                    "decision_id": decision["id"] if expected_decision else None,
                }
            ]
            archives.append((url, content))
            (
                tmp_path / ("with-decision.zip" if expected_decision else "generation-only.zip")
            ).write_bytes(content)
            (
                tmp_path / ("with-decision.html" if expected_decision else "generation-only.html")
            ).write_text(shown.text, encoding="utf-8")
        assert all(client.get(url).content == content for url, content in archives)
        assert opened(client, x, identity)["decision"] == decision
        assert len(x.calls) == 1


def test_package_history_form_empty_choices_keep_strict_reference_limits():
    identity = "00000000-0000-4000-8000-000000000001"
    decision = "00000000-0000-4000-8000-000000000002"

    def parsed(values):
        request = Request(
            {
                "type": "http",
                "query_string": urlencode(
                    [("native_proposals", value) for value in values]
                ).encode(),
            }
        )
        return packages.selection(ui._query(request, 1))

    assert parsed(["", ""]).model_dump() == parsed([]).model_dump()
    selected = parsed(["", identity + ":none", ""])
    assert selected.native_proposals == [history.Reference(proposal_id=identity, decision_id=None)]
    maximum = [f"00000000-0000-4000-8000-{index:012}:none" for index in range(1, 11)]
    assert len(parsed(["", *maximum, ""]).native_proposals) == 10
    for invalid in (
        [" "],
        [identity],
        [identity + ":"],
        [identity + ":latest"],
        [identity + ":none", identity + ":" + decision],
        [*maximum, "00000000-0000-4000-8000-000000000011:none"],
    ):
        with pytest.raises((ui.HTTPException, packages.PackageError)):
            parsed(invalid)
