from __future__ import annotations

import copy
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, update
from test_draft_pdf_intake import pdf_setup as _pdf_setup
from test_draft_pdf_intake import prepared
from test_draft_pdf_ui import pdf_app as _pdf_app
from test_draft_project_packages import save as save_package
from test_draft_scope_ui import _app, _csrf, _login
from test_draft_scope_ui import scope_password_hash as _password_hash
from test_shared_file_containment import postgresql_session_factory as _postgres

from classifire.draft_pdf_ui import router as pdf_router
from classifire.models import (
    AuditEvent,
    DraftScopeRevision,
    Estimate,
    EstimateLine,
    Opening,
    Service,
    StoredFile,
    User,
)
from classifire.physical_models import Defect, EvidenceSource, PhysicalModelLock, ServiceOpeningLink
from classifire.services import draft_package_import as inspection
from classifire.services import draft_package_materialization as imports
from classifire.services import draft_pdf_intake as intake
from classifire.services import draft_project_packages as packages
from classifire.services import draft_scope as scopes
from classifire.services.storage import quarantine_stored_file_bytes_for_update

pdf_setup = _pdf_setup
pdf_app = _pdf_app
postgresql_session_factory = _postgres
scope_password_hash = _password_hash


def _uid(number):
    return str(UUID(int=number))


def _graph(observations):
    return {
        "defects": [{"id": _uid(201), "label": "D-01", "description": "Reviewed shared opening"}],
        "openings": [
            {"id": _uid(202), "label": "Wall opening", "defect_id": _uid(201), "plane": "wall"},
            {"id": _uid(203), "label": "Second opening", "defect_id": _uid(201)},
        ],
        "services": [
            {
                "id": _uid(204),
                "label": "Pipe group",
                "opening_ids": [_uid(202), _uid(203)],
                "service_type": "Unverified pipes",
            },
            {
                "id": _uid(205),
                "label": "Cable group",
                "opening_ids": [_uid(202)],
                "service_type": "Unverified cables",
            },
        ],
        "observations": copy.deepcopy(observations),
        "assumptions": ["No concealed dimensions or service quantity inferred"],
        "exclusions": [],
    }


def _targets(payload):
    return [
        {"target_kind": kind, "target_id": item["id"]}
        for kind, collection in (
            ("service", "services"),
            ("opening", "openings"),
            ("defect", "defects"),
        )
        for item in payload[collection]
    ]


@pytest.fixture
def review_case(pdf_setup):
    x = pdf_setup
    with x.factory() as db:
        actor, source = prepared(db, x)
        old = intake.review_page(
            db,
            actor,
            x.ids[2],
            source.id,
            1,
            1,
            "The original observation must remain traceable.",
            "Unresolved",
            source.document_sha256,
            settings=x.settings,
        )
        x.source_id = source.id
        x.document_hash = source.document_sha256
        x.prior = scopes._json(old)
        x.observation_ref = copy.deepcopy(old["evidence_refs"][0])
        x.payload = _graph(old["content"]["observations"])
        x.targets = _targets(x.payload)
        db.commit()
    return x


def _arguments(x, changes):
    values = {
        "actor_id": x.ids[0],
        "draft_id": x.ids[2],
        "source_id": x.source_id,
        "revision": 2,
        "page": 1,
        "payload": copy.deepcopy(x.payload),
        "targets": copy.deepcopy(x.targets),
        "document_hash": x.document_hash,
    }
    values.update(changes)
    return values


def _preview(db, x, **changes):
    v = _arguments(x, changes)
    with db.no_autoflush:
        actor = db.get(User, v["actor_id"])
    return intake.preview_scope_page(
        db,
        actor,
        v["draft_id"],
        v["source_id"],
        v["revision"],
        v["page"],
        v["payload"],
        v["targets"],
        v["document_hash"],
        settings=x.settings,
    )


def _save(db, x, preview=None, **changes):
    v = _arguments(x, changes)
    if preview is None:
        preview = _preview(db, x, **changes)
    return intake.save_scope_page(
        db,
        db.get(User, v["actor_id"]),
        v["draft_id"],
        v["source_id"],
        v["revision"],
        v["page"],
        v["payload"],
        v["targets"],
        v["document_hash"],
        preview["review_sha256"],
        settings=x.settings,
    )


def _counts(db):
    with db.no_autoflush:
        return tuple(
            db.scalar(select(func.count()).select_from(model))
            for model in (DraftScopeRevision, AuditEvent)
        )


def _canonical_empty(db):
    for model in (
        Estimate,
        EstimateLine,
        Opening,
        Service,
        Defect,
        EvidenceSource,
        ServiceOpeningLink,
        PhysicalModelLock,
    ):
        assert db.scalar(select(func.count()).select_from(model)) == 0, model.__name__


def _entity_refs(envelope):
    return [ref for ref in envelope["evidence_refs"] if "target_kind" in ref]


def test_graph_preview_is_pure_and_one_saved_revision_survives_reopening(review_case):
    x = review_case
    with x.factory() as db:
        before = _counts(db)
        pending = User(
            email="unflushed-review@example.test",
            full_name="Unrelated pending work",
            role="estimator",
            is_active=True,
            password_hash="unused",  # noqa: S106 - synthetic non-authenticating fixture
        )
        db.add(pending)
        statements = []
        event.listen(
            db.connection(),
            "before_cursor_execute",
            lambda _c, _u, statement, _p, _x, _m: statements.append(statement),
        )
        preview = _preview(db, x)
        repeated = _preview(db, x, targets=list(reversed(x.targets)))
        assert pending in db.new
        assert not any(
            sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for sql in statements
        )
        assert _counts(db) == before
        assert preview["review_sha256"] == repeated["review_sha256"]
        assert len(preview["targets"]) == 5
        assert "QUANTITY_UNRESOLVED" in {finding["code"] for finding in preview["findings"]}
        db.rollback()
        before = _counts(db)
        saved = _save(db, x, preview)
        assert saved["revision"] == 3 and saved["schema_version"] == "CLASSIFIRE-DRAFT-SCOPE-v4"
        assert _counts(db) == (before[0] + 1, before[1] + 1)
        assert saved["review_status"] == "unreviewed" and saved["state"] == "Draft"
        assert saved["content"]["services"][0]["opening_ids"] == [_uid(202), _uid(203)]
        assert all(item["quantity"] is None for item in saved["content"]["services"])
        assert all(item["width_mm"] is None for item in saved["content"]["openings"])
        assert x.observation_ref in saved["evidence_refs"]
        refs = _entity_refs(saved)
        assert {(ref["target_kind"], ref["target_id"]) for ref in refs} == {
            (target["target_kind"], target["target_id"]) for target in x.targets
        }
        assert all(ref["method"] == "human_page_entity_review" for ref in refs)
        assert all(ref["source_id"] == x.source_id and ref["page_number"] == 1 for ref in refs)
        raw = scopes._json(saved)
        assert scopes.validate_portable_artifact(raw) == saved
        assert (
            scopes._json(scopes.read_revision(db, db.get(User, x.ids[0]), x.ids[2], 2)) == x.prior
        )
        _canonical_empty(db)
        db.commit()
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        assert scopes._json(scopes.read_revision(db, actor, x.ids[2], 3)) == raw
        assert not intake.scope_evidence_staleness(
            db,
            actor,
            x.ids[2],
            saved,
            storage_root=x.settings.storage_root,
        )
        _canonical_empty(db)


@pytest.mark.parametrize(
    "change",
    [
        "payload",
        "targets",
        "document",
        "page",
        "revision",
        "source",
        "rescan",
        "bytes",
        "quarantine",
    ],
)
def test_changed_review_inputs_or_source_refuse_without_a_partial_graph(review_case, change):
    x = review_case
    with x.factory() as db:
        preview = _preview(db, x)
        values = {}
        actor = db.get(User, x.ids[0])
        if change == "payload":
            values["payload"] = copy.deepcopy(x.payload)
            values["payload"]["services"][0]["label"] = "Changed after preview"
        elif change == "targets":
            values["targets"] = x.targets[:-1]
        elif change == "document":
            values["document_hash"] = "0" * 64
        elif change == "page":
            values["page"] = 2
        elif change == "source":
            values["source_id"] = _uid(999)
        elif change == "revision":
            scopes.save_revision(db, actor, x.ids[2], 2, {"assumptions": ["Another saved change"]})
            db.commit()
        elif change == "rescan":
            intake.scan_source(db, actor, x.ids[2], x.source_id, settings=x.settings)
            db.commit()
        else:
            source, _document, _content = intake._document(
                db,
                actor,
                x.ids[2],
                x.source_id,
                x.settings.storage_root,
            )
            if change == "bytes":
                Path(db.get(StoredFile, source.stored_file_id).storage_path).write_bytes(
                    b"tampered synthetic PDF"
                )
            else:
                quarantine_stored_file_bytes_for_update(
                    db,
                    stored_file_id=source.stored_file_id,
                    observed_sha256=source.source_sha256,
                    observed_size_bytes=source.source_size_bytes,
                )
                db.commit()
        before = _counts(db)
        with pytest.raises(scopes.DraftScopeError) as rejected:
            _save(db, x, preview, **values)
        assert rejected.value.status_code == (404 if change in {"page", "source"} else 409)
        assert _counts(db) == before
        latest = scopes.read_revision(db, actor, x.ids[2])
        assert latest["revision"] == (3 if change == "revision" else 2)
        assert not latest["content"]["defects"]
        _canonical_empty(db)


@pytest.mark.parametrize("change", ["foreign", "read_only", "inactive", "other_administrator"])
def test_current_actor_and_preview_identity_are_required(review_case, change):
    x = review_case
    with x.factory() as db:
        preview = _preview(db, x)
        actor_id = x.ids[0]
        if change in {"foreign", "other_administrator"}:
            actor_id = x.ids[1]
            if change == "other_administrator":
                db.execute(update(User).where(User.id == actor_id).values(role="administrator"))
        else:
            values = {"role": "read_only"} if change == "read_only" else {"is_active": False}
            db.execute(update(User).where(User.id == actor_id).values(**values))
        db.commit()
        before = _counts(db)
        with pytest.raises(scopes.DraftScopeError) as rejected:
            _save(db, x, preview, actor_id=actor_id)
        assert (
            rejected.value.status_code
            == {
                "foreign": 404,
                "read_only": 403,
                "inactive": 403,
                "other_administrator": 409,
            }[change]
        )
        assert _counts(db) == before
        _canonical_empty(db)


@pytest.mark.parametrize(
    "change", ["missing_target", "duplicate_target", "unknown_kind", "broken_graph"]
)
def test_invalid_selected_targets_and_graph_fail_before_preview_or_save(review_case, change):
    x = review_case
    values = {"payload": copy.deepcopy(x.payload), "targets": copy.deepcopy(x.targets)}
    if change == "missing_target":
        values["targets"][0]["target_id"] = _uid(999)
    elif change == "duplicate_target":
        values["targets"].append(values["targets"][0].copy())
    elif change == "unknown_kind":
        values["targets"][0]["target_kind"] = "technical_approval"
    else:
        values["payload"]["services"][0]["opening_ids"] = [_uid(999)]
    with x.factory() as db:
        before = _counts(db)
        with pytest.raises(scopes.DraftScopeError):
            _preview(db, x, **values)
        assert _counts(db) == before
        _canonical_empty(db)


def test_failed_audit_and_caller_rollback_leave_no_graph_revision(review_case, monkeypatch):
    x = review_case
    with x.factory() as db:
        preview = _preview(db, x)
        before = _counts(db)
        original_audit = scopes.record_audit

        def fail(*args, **kwargs):
            raise RuntimeError("synthetic audit storage failure")

        monkeypatch.setattr(scopes, "record_audit", fail)
        with pytest.raises(RuntimeError, match="synthetic audit storage failure"):
            _save(db, x, preview)
        assert _counts(db) == before
        assert scopes.read_revision(db, db.get(User, x.ids[0]), x.ids[2])["revision"] == 2
        monkeypatch.setattr(scopes, "record_audit", original_audit)
        _save(db, x, preview)
        db.rollback()
        assert _counts(db) == before
        assert scopes.read_revision(db, db.get(User, x.ids[0]), x.ids[2])["revision"] == 2
        _canonical_empty(db)


def test_manual_edits_rereview_and_deleted_targets_preserve_history_and_import_claims(review_case):
    x = review_case
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        saved = _save(db, x)
        original = scopes._json(saved)
        changed = copy.deepcopy(saved["content"])
        changed["services"][0]["label"] = "Human correction after page review"
        edited = scopes.save_revision(db, actor, x.ids[2], 3, changed)
        assert edited["evidence_refs"] == saved["evidence_refs"]
        assert intake.scope_evidence_staleness(
            db, actor, x.ids[2], edited, storage_root=x.settings.storage_root
        )
        target = [{"target_kind": "service", "target_id": _uid(204)}]
        reviewed = _save(db, x, revision=4, payload=changed, targets=target)
        assert len(reviewed["evidence_refs"]) == len(saved["evidence_refs"])
        old_ref = next(ref for ref in _entity_refs(saved) if ref["target_id"] == _uid(204))
        new_ref = next(ref for ref in _entity_refs(reviewed) if ref["target_id"] == _uid(204))
        assert new_ref["target_sha256"] != old_ref["target_sha256"]
        assert not intake.scope_evidence_staleness(
            db, actor, x.ids[2], reviewed, storage_root=x.settings.storage_root
        )
        deleted = copy.deepcopy(reviewed["content"])
        deleted["services"] = deleted["services"][1:]
        removed = scopes.save_revision(db, actor, x.ids[2], 5, deleted)
        assert removed["evidence_refs"] == reviewed["evidence_refs"]
        assert scopes.validate_portable_artifact(scopes._json(removed)) == removed
        assert intake.scope_evidence_staleness(
            db, actor, x.ids[2], removed, storage_root=x.settings.storage_root
        )
        target_draft = scopes.create_draft_project(
            db, actor, "V4-JSON-IMPORT", "Unverified review claims"
        )
        raw = scopes._json(removed)
        imported = scopes.apply_import(
            db, actor, target_draft.id, 1, raw, hashlib.sha256(raw).hexdigest()
        )
        assert len(imported["evidence_refs"]) == len(removed["evidence_refs"])
        assert all(ref["origin"] == "imported_unverified" for ref in imported["evidence_refs"])
        assert "SCOPE_SOURCE_UNVERIFIED" in intake.scope_evidence_staleness(
            db,
            actor,
            target_draft.id,
            imported,
            storage_root=x.settings.storage_root,
        )
        with pytest.raises(scopes.DraftScopeError):
            intake.read_document(db, actor, target_draft.id, x.source_id, settings=x.settings)
        assert scopes._json(scopes.read_revision(db, actor, x.ids[2], 3)) == original
        assert scopes._json(scopes.read_revision(db, actor, x.ids[2], 2)) == x.prior
        _canonical_empty(db)
        db.commit()


def test_v4_source_only_package_import_edit_and_reexport_preserve_originals(
    review_case, monkeypatch
):
    x = review_case
    monkeypatch.setattr(packages, "get_settings", lambda: x.settings)
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        saved = _save(db, x)
        payload = copy.deepcopy(saved["content"])
        payload["services"].pop()
        removed = scopes.save_revision(db, actor, x.ids[2], 3, payload)
        original = save_package(db, actor, x.ids[2], {"scope_revision": 4})
        raw = original.archive_bytes
        checked = inspection.inspect_package(raw)
        assert checked.scope["evidence_refs"] == removed["evidence_refs"]
        assert len(checked.manifest["source_manifest"]) == len(removed["evidence_refs"])
        imported = imports.create_import(
            db,
            actor,
            raw,
            expected_sha256=original.archive_hash,
            reference="V4-PACKAGE-IMPORT",
            name="Unverified source package",
            settings=x.settings,
        )
        imported_id = imported.draft_scope_id
        local = scopes.read_revision(db, actor, imported_id)
        assert len(local["evidence_refs"]) == len(removed["evidence_refs"])
        assert all(ref["origin"] == "imported_unverified" for ref in local["evidence_refs"])
        edited_payload = copy.deepcopy(local["content"])
        edited_payload["assumptions"].append("Local edit preserves foreign review claims")
        edited = scopes.save_revision(db, actor, imported_id, local["revision"], edited_payload)
        assert edited["evidence_refs"] == local["evidence_refs"]
        exported = save_package(db, actor, imported_id, {"scope_revision": edited["revision"]})
        exported_bytes = exported.archive_bytes
        reopened = inspection.inspect_package(exported_bytes)
        assert len(list(reopened.walk())) == 2
        assert next(iter(reopened.origins.values())).archive_sha256 == packages.digest(raw)
        assert reopened.scope["evidence_refs"] == edited["evidence_refs"]
        exported_id = exported.id
        _canonical_empty(db)
        db.commit()
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        assert imports.read_import(db, actor, imported_id)[0].archive_bytes == raw
        assert packages.package_bytes(db, actor, imported_id, exported_id) == exported_bytes
        assert (
            scopes.read_revision(db, actor, imported_id)["evidence_refs"] == edited["evidence_refs"]
        )
        _canonical_empty(db)


class _ReviewForms(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.current = None
        self.textarea = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "form":
            self.current = {"action": values.get("action", ""), "values": {}}
        elif self.current is not None and tag == "input" and values.get("name"):
            self.current["values"][values["name"]] = values.get("value", "")
        elif self.current is not None and tag == "textarea" and values.get("name"):
            self.textarea = values["name"]
            self.current["values"][self.textarea] = ""

    def handle_data(self, data):
        if self.current is not None and self.textarea:
            self.current["values"][self.textarea] += data

    def handle_endtag(self, tag):
        if tag == "textarea":
            self.textarea = None
        elif tag == "form" and self.current is not None:
            self.forms.append(self.current)
            self.current = None


def _confirmation(response):
    assert response.status_code == 200, response.text
    parser = _ReviewForms()
    parser.feed(response.text)
    form = next(form for form in parser.forms if "preview_token" in form["values"])
    assert form["action"].endswith("/scope/confirm")
    return form["action"], form["values"] | {"confirm": "save"}


def _http_preview(client, x, **changes):
    path = f"/scopes/{x.ids[2]}/evidence/{x.source_id}"
    page = client.get(path)
    assert page.status_code == 200
    assert "/scope/preview" in page.text
    values = {
        "csrf_token": _csrf(page.text),
        "expected_revision": "2",
        "page": "1",
        "document_hash": x.document_hash,
        "payload": json.dumps(x.payload),
        "targets": json.dumps(x.targets),
    }
    values.update(changes)
    return client.post(path + "/scope/preview", data=values)


def test_browser_preview_explicit_confirmation_replay_and_reconstructed_app(review_case, pdf_app):
    x = review_case
    with x.factory() as db:
        before = _counts(db)
    with TestClient(pdf_app.app) as client:
        _login(client)
        preview = _http_preview(client, x)
        path, values = _confirmation(preview)
        assert "Pipe group" in preview.text and "Cable group" in preview.text
        editing = {
            key: value for key, value in values.items() if key not in {"preview_token", "confirm"}
        }
        preview_path = path.removesuffix("confirm") + "preview"
        returned = client.post(preview_path, data=editing | {"action": "edit"})
        assert returned.status_code == 200 and "Pipe group" in returned.text
        bad = client.post(preview_path, data=editing | {"targets": "[]"})
        assert bad.status_code == 422 and "Pipe group" in bad.text
        assert 'name="preview_token"' not in bad.text
        with x.factory() as db:
            assert _counts(db) == before
        assert client.post(path, data=values | {"csrf_token": "wrong"}).status_code == 403
        assert (
            client.post(path, data={k: v for k, v in values.items() if k != "confirm"}).status_code
            == 422
        )
        saved = client.post(path, data=values, follow_redirects=False)
        assert saved.status_code == 303, saved.text
        assert client.post(path, data=values, follow_redirects=False).status_code == 409
        download = client.get(f"/scopes/{x.ids[2]}/download?revision=3")
        assert download.status_code == 200
        assert download.json()["schema_version"] == "CLASSIFIRE-DRAFT-SCOPE-v4"
        content = download.content
    fresh_app = _app(x.factory)
    fresh_app.include_router(pdf_router)
    with TestClient(fresh_app) as client:
        _login(client)
        assert client.get(f"/scopes/{x.ids[2]}/download?revision=3").content == content
        assert (
            client.get(f"/scopes/{x.ids[2]}/evidence/{x.source_id}/pages/1.png").status_code == 200
        )
    with x.factory() as db:
        _canonical_empty(db)


@pytest.mark.parametrize("change", ["payload", "token", "permission", "session"])
def test_browser_changed_or_unowned_confirmation_does_not_save(review_case, pdf_app, change):
    x = review_case
    with TestClient(pdf_app.app) as client:
        _login(client)
        path, values = _confirmation(_http_preview(client, x))
        if change == "payload":
            payload = json.loads(values["payload"])
            payload["defects"][0]["label"] = "Not what the human previewed"
            values["payload"] = json.dumps(payload)
        elif change == "token":
            values["preview_token"] = "invalid-preview-token"  # noqa: S105 - invalid test token
        elif change == "permission":
            with x.factory() as db:
                db.execute(update(User).where(User.id == x.ids[0]).values(role="read_only"))
                db.commit()
        with x.factory() as db:
            before = _counts(db)
        if change == "session":
            with TestClient(pdf_app.app) as another_session:
                _login(another_session)
                page = another_session.get(f"/scopes/{x.ids[2]}/evidence/{x.source_id}")
                values["csrf_token"] = _csrf(page.text)
                response = another_session.post(path, data=values, follow_redirects=False)
        else:
            response = client.post(path, data=values, follow_redirects=False)
        assert (
            response.status_code
            == {
                "payload": 409,
                "token": 422,
                "permission": 403,
                "session": 422,
            }[change]
        ), response.text
        with x.factory() as db:
            assert _counts(db) == before
            assert db.scalar(select(func.count()).select_from(DraftScopeRevision)) == 2
            _canonical_empty(db)
