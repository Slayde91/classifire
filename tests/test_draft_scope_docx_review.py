from __future__ import annotations

import copy
import io
import json
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from test_draft_pdf_intake import pdf_setup as _pdf_setup
from test_draft_pdf_scope_review import _canonical_empty, _graph, _ReviewForms, _targets
from test_draft_pdf_ui import pdf_app as _pdf_app
from test_draft_project_packages import save as save_package
from test_draft_scope_docx import word_bytes
from test_draft_scope_docx_ui import word_app as _word_app
from test_draft_scope_ui import _csrf, _login
from test_draft_scope_ui import scope_password_hash as _password_hash
from test_shared_file_containment import postgresql_session_factory as _postgres

from classifire.models import User
from classifire.services import draft_import_reports as imported_reports
from classifire.services import draft_package_import as inspection
from classifire.services import draft_package_materialization as imports
from classifire.services import draft_pdf_intake as pdf
from classifire.services import draft_project_packages as packages
from classifire.services import draft_scope as scopes
from classifire.services import draft_scope_docx as word
from classifire.services import draft_scope_docx_review as review
from classifire.services import draft_scope_reports as reports
from classifire.services.storage import quarantine_stored_file_bytes_for_update

pdf_setup = _pdf_setup
pdf_app = _pdf_app
word_app = _word_app
scope_password_hash = _password_hash
postgresql_session_factory = _postgres


def word_graph_bytes():
    original = word_bytes()
    output = io.BytesIO()
    with ZipFile(io.BytesIO(original)) as source, ZipFile(output, "w") as target:
        for info in source.infolist():
            content = source.read(info.filename)
            if info.filename == "word/document.xml":
                content = content.replace(
                    b"one shared opening",
                    b"O-01 shared opening containing an illustrated metal pipe and cable bundle",
                )
                content = content.replace(
                    b"</w:body>",
                    b"<w:p><w:r><w:t>Synthetic O-02: separate blank opening; dimensions unknown. "
                    b"This is demonstration material, not site evidence or technical approval."
                    b"</w:t></w:r></w:p></w:body>",
                )
            target.writestr(info, content)
    return output.getvalue()


@pytest.fixture
def word_case(word_app):
    x = word_app
    x.content = word_graph_bytes()
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        source = word.intake().retain(
            db, actor, x.ids[2], "synthetic.docx", x.content, settings=x.settings
        )
        db.commit()
        result = word.intake().scan_source(db, actor, x.ids[2], source.id, settings=x.settings)
        assert result["status"] == "clean" and result["processing_error"] is None, result
        db.commit()
        x.source_id, x.document_hash = source.id, source.document_sha256
        x.prior = scopes.revision_bytes(db, actor, x.ids[2])
    x.payload = _graph([])
    x.payload["openings"][0]["label"] = "O-01"
    x.payload["openings"][1].update(label="O-02", blank=True)
    for service in x.payload["services"]:
        service["opening_ids"] = [x.payload["openings"][0]["id"]]
    x.targets = [dict(target, locator="body-1", image_ids=[]) for target in _targets(x.payload)]
    x.targets[0]["image_ids"] = ["picture-1"]
    next(target for target in x.targets if target["target_id"] == x.payload["openings"][1]["id"])[
        "locator"
    ] = "body-3"
    return x


def _preview(db, x, **changes):
    values = dict(
        expected_revision=1,
        payload=copy.deepcopy(x.payload),
        targets=copy.deepcopy(x.targets),
        expected_document_hash=x.document_hash,
    )
    values.update(changes)
    return review.preview_review(
        db, db.get(User, x.ids[0]), x.ids[2], x.source_id, settings=x.settings, **values
    )


def test_word_review_preserves_graph_unknowns_history_and_reference_integrity(word_case):
    x = word_case
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        checked = _preview(db, x)
        assert scopes.revision_bytes(db, actor, x.ids[2]) == x.prior
        result = review.save_review(
            db,
            actor,
            x.ids[2],
            x.source_id,
            1,
            x.payload,
            x.targets,
            x.document_hash,
            checked["review_sha256"],
            settings=x.settings,
        )
        db.commit()
        assert result["schema_version"] == "CLASSIFIRE-DRAFT-SCOPE-v7"
        assert result["revision"] == 2
        assert len(result["evidence_refs"]) == 5
        assert all(
            ref["source_kind"] == "docx" and ref["block"]["locator"] in {"body-1", "body-3"}
            for ref in result["evidence_refs"]
        )
        assert sum(len(ref["images"]) for ref in result["evidence_refs"]) == 1
        assert all(item["quantity"] is None for item in result["content"]["services"])
        assert all(
            item["width_mm"] is None and item["height_mm"] is None
            for item in result["content"]["openings"]
        )
        assert result["content"]["openings"][1]["blank"] is True
        assert all(
            item["opening_ids"] == [result["content"]["openings"][0]["id"]]
            for item in result["content"]["services"]
        )
        assert scopes.revision_bytes(db, actor, x.ids[2], 1) == x.prior
        scopes._envelope_shape(result)
        altered = copy.deepcopy(result)
        altered["evidence_refs"][0]["block"]["text"] += " forged"
        with pytest.raises(ValueError):
            scopes._envelope_shape(altered)
        _canonical_empty(db)


@pytest.mark.parametrize(
    "change", ["locator", "image", "duplicate", "target", "document", "revision"]
)
def test_word_preview_rejects_unbound_or_stale_inputs_without_writes(word_case, change):
    x = word_case
    targets = copy.deepcopy(x.targets)
    values = {"targets": targets}
    if change == "locator":
        targets[0]["locator"] = "body-999"
    if change == "image":
        targets[0]["image_ids"] = ["picture-999"]
    if change == "duplicate":
        targets.append(copy.deepcopy(targets[0]))
    if change == "target":
        targets[0]["target_id"] = "not-an-entity"
    if change == "document":
        values["expected_document_hash"] = "0" * 64
    if change == "revision":
        values["expected_revision"] = 2
    with x.factory() as db:
        with pytest.raises(scopes.DraftScopeError):
            _preview(db, x, **values)
        assert scopes.revision_bytes(db, db.get(User, x.ids[0]), x.ids[2]) == x.prior


def test_word_http_confirmation_binds_payload_and_preserves_reopen(word_case):
    x = word_case
    path = f"/scopes/{x.ids[2]}/word/{x.source_id}"
    with TestClient(x.app) as client:
        _login(client)
        page = client.get(path)
        assert page.status_code == 200
        assert 'data-word-review="true"' in page.text
        form = {
            "csrf_token": _csrf(page.text),
            "expected_revision": "1",
            "document_sha256": x.document_hash,
            "payload": json.dumps(x.payload),
            "targets": json.dumps(x.targets),
        }
        preview = client.post(path + "/preview", data=form)
        assert preview.status_code == 200, preview.text
        assert "nothing saved yet" in preview.text
        parser = _ReviewForms()
        parser.feed(preview.text)
        confirm = next(item for item in parser.forms if item["action"].endswith("/confirm"))
        fields = dict(confirm["values"])
        fields["confirm"] = "save"
        tampered = dict(fields, targets="[]")
        assert client.post(path + "/confirm", data=tampered).status_code == 422
        saved = client.post(path + "/confirm", data=fields, follow_redirects=False)
        assert saved.status_code == 303, saved.text
    with TestClient(x.app) as client:
        _login(client)
        saved = client.get(f"/scopes/{x.ids[2]}")
        assert saved.status_code == 200
        assert "Inspect Word source" in saved.text
    with x.factory() as db:
        assert scopes.read_revision(db, db.get(User, x.ids[0]), x.ids[2])["revision"] == 2


def _save(db, x):
    checked = _preview(db, x)
    return review.save_review(
        db,
        db.get(User, x.ids[0]),
        x.ids[2],
        x.source_id,
        1,
        x.payload,
        x.targets,
        x.document_hash,
        checked["review_sha256"],
        settings=x.settings,
    )


@pytest.mark.parametrize("change", ["payload", "permission", "quarantine", "revision"])
def test_word_confirmation_rechecks_dependencies(word_case, change):
    x = word_case
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        checked = _preview(db, x)
        payload = copy.deepcopy(x.payload)
        if change == "payload":
            payload["defects"][0]["description"] += " changed"
        if change == "permission":
            db.execute(update(User).where(User.id == actor.id).values(role="read_only"))
        if change == "quarantine":
            source, _, verified = word.intake()._document(
                db, actor, x.ids[2], x.source_id, x.settings.storage_root
            )
            quarantine_stored_file_bytes_for_update(
                db,
                stored_file_id=source.stored_file_id,
                observed_sha256=verified.sha256,
                observed_size_bytes=verified.size_bytes,
            )
        if change == "revision":
            scopes.save_revision(db, actor, x.ids[2], 1, x.payload)
        db.commit()
        before = scopes.revision_bytes(db, actor, x.ids[2])
        with pytest.raises(scopes.DraftScopeError):
            review.save_review(
                db,
                actor,
                x.ids[2],
                x.source_id,
                1,
                payload,
                x.targets,
                x.document_hash,
                checked["review_sha256"],
                settings=x.settings,
            )
        assert scopes.revision_bytes(db, actor, x.ids[2]) == before
        _canonical_empty(db)


def test_word_package_report_import_reexport_and_quarantine(word_case, monkeypatch):
    x = word_case
    monkeypatch.setattr(packages, "get_settings", lambda: x.settings)
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        saved = _save(db, x)
        assert (
            pdf.scope_evidence_staleness(
                db, actor, x.ids[2], saved, storage_root=x.settings.storage_root
            )
            == []
        )
        report = reports.create_report(db, actor, x.ids[2], 2)
        snapshot = reports.read_report(db, actor, x.ids[2], report.id)
        assert snapshot["render_version"] == 9
        original = save_package(
            db,
            actor,
            x.ids[2],
            {"scope_revision": 2, "docx_sources": [x.source_id], "scope_reports": [report.id]},
        )
        raw = original.archive_bytes
        checked = inspection.inspect_package(raw)
        assert checked.manifest["schema_version"] == packages.SCHEMA_V5
        assert checked.members[f"evidence/{x.source_id}.docx"] == x.content
        assert checked.scope["evidence_refs"] == saved["evidence_refs"]
        for old_version in (
            packages.SCHEMA,
            packages.SCHEMA_V2,
            packages.SCHEMA_V3,
            packages.SCHEMA_V4,
        ):
            downgraded = copy.deepcopy(checked.manifest)
            downgraded["schema_version"] = old_version
            with pytest.raises(scopes.DraftScopeError):
                inspection.inspect_package(packages._archive(downgraded, checked.members))
        changed = dict(checked.members)
        path = f"evidence/{x.source_id}.docx"
        changed[path] += b"changed"
        manifest = copy.deepcopy(checked.manifest)
        for entry in manifest["members"]:
            if entry["path"] == path:
                entry.update(sha256=packages.digest(changed[path]), size_bytes=len(changed[path]))
        with pytest.raises(scopes.DraftScopeError):
            inspection.inspect_package(packages._archive(manifest, changed))
        imported = imports.create_import(
            db,
            actor,
            raw,
            expected_sha256=original.archive_hash,
            reference="WORD-IMPORT",
            name="Synthetic Word evidence import",
            settings=x.settings,
        )
        db.commit()
        imported_id = imported.draft_scope_id
        local = scopes.read_revision(db, actor, imported_id)
        assert all(ref["origin"] == "imported_unverified" for ref in local["evidence_refs"])
        _, _, mapping = imports.read_import(db, actor, imported_id)
        for entry in mapping["evidence"]:
            imported_reports.scan(db, actor, imported_id, entry["source_id"], settings=x.settings)
        for entry in mapping["reports"]:
            for member in entry["members"].values():
                imported_reports.scan(
                    db, actor, imported_id, member["source_id"], settings=x.settings
                )
        db.commit()
        exported = save_package(db, actor, imported_id, {"scope_revision": local["revision"]})
        exported_bytes, exported_id = exported.archive_bytes, exported.id
        reopened = inspection.inspect_package(exported_bytes)
        assert next(iter(reopened.origins.values())).archive_sha256 == packages.digest(raw)
        assert list(reopened.evidence_members())[0][1].endswith(f"evidence/{x.source_id}.docx")
        db.commit()
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        assert packages.package_bytes(db, actor, imported_id, exported_id) == exported_bytes
        member = mapping["evidence"][0]
        assert (
            imported_reports.checked_bytes(
                db, actor, imported_id, member["source_id"], settings=x.settings
            )
            == x.content
        )
        source, _, verified = imported_reports.evidence_intake("docx")._document(
            db, actor, imported_id, member["source_id"], x.settings.storage_root
        )
        quarantine_stored_file_bytes_for_update(
            db,
            stored_file_id=source.stored_file_id,
            observed_sha256=verified.sha256,
            observed_size_bytes=verified.size_bytes,
        )
        db.commit()
        with pytest.raises(scopes.DraftScopeError):
            packages.package_bytes(db, actor, imported_id, exported_id)
        _canonical_empty(db)


def test_word_package_requires_review_and_correct_source_format(word_case, monkeypatch):
    x = word_case
    monkeypatch.setattr(packages, "get_settings", lambda: x.settings)
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        with pytest.raises(scopes.DraftScopeError, match="DOCX_SELECTION_INVALID"):
            packages.preview(
                db, actor, x.ids[2], {"scope_revision": 1, "docx_sources": [x.source_id]}
            )
        _save(db, x)
        for field in ("pdf_sources", "xlsx_sources"):
            with pytest.raises(scopes.DraftScopeError):
                packages.preview(db, actor, x.ids[2], {"scope_revision": 2, field: [x.source_id]})
        legacy = packages.preview(db, actor, x.ids[2], {"scope_revision": 2})
        assert legacy["manifest"]["schema_version"] == packages.SCHEMA
        assert "docx_sources" not in legacy["manifest"]["selection"]
        assert all(
            entry["membership"] == "external" for entry in legacy["manifest"]["source_manifest"]
        )
        with pytest.raises(scopes.DraftScopeError):
            packages.preview(
                db,
                db.get(User, x.ids[1]),
                x.ids[2],
                {"scope_revision": 2, "docx_sources": [x.source_id]},
            )


def test_word_selection_is_bounded_unique_and_disjoint():
    source = "00000000-0000-0000-0000-000000000001"
    for chosen in (
        {"docx_sources": [source, source]},
        {"docx_sources": [source], "xlsx_sources": [source]},
        {"docx_sources": [source], "pdf_sources": [source]},
        {"docx_sources": [str(i) for i in range(5)]},
    ):
        with pytest.raises(packages.PackageError):
            packages.selection({"scope_revision": 1, **chosen})
