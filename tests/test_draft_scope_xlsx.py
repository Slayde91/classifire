from __future__ import annotations

import copy
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from uuid import UUID

import pytest
import xlsxwriter
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import event, select, update
from test_draft_pdf_intake import pdf_bytes
from test_draft_pdf_intake import pdf_setup as _pdf_setup
from test_draft_pdf_scope_review import _canonical_empty, _counts, _ReviewForms
from test_draft_pdf_ui import pdf_app as _pdf_app
from test_draft_project_packages import save as save_package
from test_draft_scope_ui import _app, _csrf, _login
from test_draft_scope_ui import scope_password_hash as _password_hash
from test_shared_file_containment import postgresql_session_factory as _postgres

from classifire.draft_scope_xlsx_ui import router as xlsx_router
from classifire.models import AuditEvent, StoredFile, User
from classifire.security import ROLE_PERMISSIONS
from classifire.services import draft_package_import as inspection
from classifire.services import draft_package_materialization as imports
from classifire.services import draft_pdf_intake as pdf
from classifire.services import draft_pricing_intake as pricing
from classifire.services import draft_project_packages as packages
from classifire.services import draft_scope as scopes
from classifire.services import draft_scope_xlsx as xlsx
from classifire.services.draft_scope_evidence import reference_status
from classifire.services.draft_scope_xlsx_contract import FIELDS
from classifire.services.storage import quarantine_stored_file_bytes_for_update

pdf_setup = _pdf_setup
pdf_app = _pdf_app
postgresql_session_factory = _postgres
scope_password_hash = _password_hash
MAPPING = {field: index for index, field in enumerate(FIELDS, 1)}


def _uid(number):
    return str(UUID(int=number))


def workbook_bytes():
    picture = io.BytesIO()
    Image.new("RGB", (12, 8), "red").save(picture, format="PNG")
    stream = io.BytesIO()
    book = xlsxwriter.Workbook(stream, {"in_memory": True, "strings_to_formulas": False})
    sheet = book.add_worksheet("Defects")
    sheet.write_row(0, 0, list(FIELDS))
    sheet.write_row(
        1,
        0,
        [
            "D-01",
            "Two services need explicit relationship review",
            "Level 1",
            "Shared opening",
            "wall",
            "Unverified masonry",
            None,
            "not measured",
            "Pipe group",
            "pipe",
            None,
            "each",
        ],
    )
    sheet.write_row(
        2,
        0,
        [
            "D-02",
            "Source relationship is unknown",
            "Level 1",
            None,
            None,
            None,
            None,
            None,
            "Cable group",
            "cable",
            0,
            "each",
        ],
    )
    sheet.write_row(
        3,
        0,
        [
            "D-03",
            "Formula quantity is unreviewed",
            "Level 2",
            None,
            None,
            None,
            None,
            None,
            "Formula group",
            "pipe",
            None,
            "box",
        ],
    )
    sheet.write_formula(3, 10, "=1+1", None, 2)
    sheet.insert_image("B2", "same.png", {"image_data": io.BytesIO(picture.getvalue())})
    sheet.insert_image("B3", "same.png", {"image_data": io.BytesIO(picture.getvalue())})
    second = book.add_worksheet("Other sheet")
    second.write_column(0, 0, ["Other notes", "Not selected"])
    book.close()
    return stream.getvalue()


def mapping_plan():
    return {
        "sheet_index": 1,
        "header_row": 1,
        "mapping": dict(MAPPING),
        "selections": [
            {"row": 2, "kinds": ["defect", "opening", "service"]},
            {"row": 3, "kinds": ["service"]},
        ],
    }


def _editing_state(db, x):
    actor = db.get(User, x.ids[0])
    prepared = xlsx.prepare_mapping(
        db,
        actor,
        x.ids[2],
        x.source_id,
        1,
        x.plan,
        x.document_hash,
        settings=x.settings,
    )
    x.payload = copy.deepcopy(prepared["payload"])
    x.payload["openings"][0]["defect_id"] = x.payload["defects"][0]["id"]
    for service in x.payload["services"]:
        service["opening_ids"] = [x.payload["openings"][0]["id"]]
    x.targets = copy.deepcopy(prepared["targets"])
    x.targets[0]["image_ids"] = [
        image["occurrence_id"] for image in x.document["sheets"][0]["images"]
    ]
    return prepared


@pytest.fixture
def xlsx_case(pdf_setup):
    x = pdf_setup
    x.content = workbook_bytes()
    x.plan = mapping_plan()
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        source = xlsx.intake().retain(
            db,
            actor,
            x.ids[2],
            "synthetic-defects.xlsx",
            x.content,
            settings=x.settings,
        )
        db.commit()
        scan = xlsx.intake().scan_source(db, actor, x.ids[2], source.id, settings=x.settings)
        assert scan["status"] == "clean" and scan["processing_error"] is None, scan
        db.commit()
        x.source_id, x.document_hash = source.id, source.document_sha256
        _, x.document, _ = xlsx.intake()._document(
            db,
            actor,
            x.ids[2],
            source.id,
            x.settings.storage_root,
        )
        x.prior = scopes.revision_bytes(db, actor, x.ids[2], 1)
        _editing_state(db, x)
        db.commit()
    return x


@pytest.fixture
def xlsx_app(xlsx_case, pdf_app, monkeypatch):
    x = xlsx_case
    x.app = pdf_app.app
    x.app.include_router(xlsx_router)
    monkeypatch.setattr("classifire.draft_scope_xlsx_ui.get_settings", lambda: x.settings)
    return x


def _values(x, changes):
    result = {
        "actor_id": x.ids[0],
        "draft_id": x.ids[2],
        "source_id": x.source_id,
        "revision": 1,
        "payload": copy.deepcopy(x.payload),
        "plan": copy.deepcopy(x.plan),
        "targets": copy.deepcopy(x.targets),
        "document_hash": x.document_hash,
    }
    result.update(changes)
    return result


def _preview(db, x, **changes):
    v = _values(x, changes)
    with db.no_autoflush:
        actor = db.get(User, v["actor_id"])
    return xlsx.preview_review(
        db,
        actor,
        v["draft_id"],
        v["source_id"],
        v["revision"],
        v["payload"],
        v["plan"],
        v["targets"],
        v["document_hash"],
        settings=x.settings,
    )


def _save(db, x, preview=None, **changes):
    v = _values(x, changes)
    if preview is None:
        preview = _preview(db, x, **changes)
    return xlsx.save_review(
        db,
        db.get(User, v["actor_id"]),
        v["draft_id"],
        v["source_id"],
        v["revision"],
        v["payload"],
        v["plan"],
        v["targets"],
        v["document_hash"],
        preview["review_sha256"],
        settings=x.settings,
    )


def test_mapping_and_preview_write_nothing_and_saved_graph_preserves_exact_source(xlsx_case):
    x = xlsx_case
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        before = _counts(db)
        pending = User(
            email="unflushed-xlsx@example.test",
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
            lambda _c, _u, sql, _p, _x, _m: statements.append(sql),
        )
        prepared = xlsx.prepare_mapping(
            db,
            actor,
            x.ids[2],
            x.source_id,
            1,
            x.plan,
            x.document_hash,
            settings=x.settings,
        )
        assert prepared["payload"]["openings"][0]["defect_id"] is None
        assert all(not item["opening_ids"] for item in prepared["payload"]["services"])
        assert [item["quantity"] for item in prepared["payload"]["services"]] == [None, "0"]
        assert prepared["payload"]["openings"][0]["height_mm"] is None
        assert any("height_mm" in item["path"] for item in prepared["findings"])
        assert all(not target["image_ids"] for target in prepared["targets"])
        preview = _preview(db, x)
        repeated = _preview(db, x, targets=list(reversed(x.targets)))
        assert preview["review_sha256"] == repeated["review_sha256"]
        assert pending in db.new and _counts(db) == before
        assert not any(
            sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for sql in statements
        )
        db.rollback()
        before = _counts(db)
        saved = _save(db, x, preview)
        assert saved["revision"] == 2 and saved["schema_version"] == "CLASSIFIRE-DRAFT-SCOPE-v5"
        assert saved["state"] == "Draft" and saved["review_status"] == "unreviewed"
        assert _counts(db) == (before[0] + 1, before[1] + 1)
        assert len(saved["evidence_refs"]) == 4
        assert all(
            ref["source_kind"] == "xlsx" and ref["origin"] == "local_retained"
            for ref in saved["evidence_refs"]
        )
        assert all(
            ref["row"]["sheet"] == "Defects" and ref["row"]["header_row"] == 1
            for ref in saved["evidence_refs"]
        )
        defect_ref = next(ref for ref in saved["evidence_refs"] if ref["target_kind"] == "defect")
        assert defect_ref["row"]["fields"]["defect_label"]["address"] == "A2"
        assert defect_ref["row"]["fields"]["defect_label"]["value"] == "D-01"
        assert defect_ref["row"]["fields"]["width_mm"] is None
        images = defect_ref["images"]
        assert len(images) == 2 and images[0]["sha256"] == images[1]["sha256"]
        assert images[0]["occurrence_id"] != images[1]["occurrence_id"]
        assert images[0]["anchor"] != images[1]["anchor"]
        assert all(
            service["opening_ids"] == [saved["content"]["openings"][0]["id"]]
            for service in saved["content"]["services"]
        )
        raw = scopes._json(saved)
        assert scopes.validate_portable_artifact(raw) == saved
        assert scopes.revision_bytes(db, actor, x.ids[2], 1) == x.prior
        with pytest.raises(scopes.DraftScopeError, match="DRAFT_REVISION_CONFLICT"):
            _save(db, x, preview)
        _canonical_empty(db)
        db.commit()
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        assert scopes.revision_bytes(db, actor, x.ids[2], 2) == raw
        assert not pdf.scope_evidence_staleness(
            db, actor, x.ids[2], saved, storage_root=x.settings.storage_root
        )
        for image in images:
            picture = xlsx.image_preview(
                db, actor, x.ids[2], x.source_id, 1, image["occurrence_id"], settings=x.settings
            )
            assert hashlib.sha256(picture).hexdigest() == image["preview_sha256"]
        _canonical_empty(db)


def test_formula_and_unsupported_units_remain_unresolved_in_source_and_graph(xlsx_case):
    x = xlsx_case
    plan = mapping_plan()
    plan["selections"] = [{"row": 4, "kinds": ["service"]}]
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        before = _counts(db)
        prepared = xlsx.prepare_mapping(
            db, actor, x.ids[2], x.source_id, 1, plan, x.document_hash, settings=x.settings
        )
        service = prepared["payload"]["services"][0]
        assert service["quantity"] is None and service["state"] == "Unresolved"
        field = prepared["rows"][0]["fields"]["quantity"]
        assert field["address"] == "K4" and field["kind"] == "formula" and field["value"] == "=1+1"
        assert {item["path"].rsplit(".", 1)[-1] for item in prepared["findings"]} >= {
            "quantity",
            "unit",
        }
        assert _counts(db) == before
        saved = _save(
            db,
            x,
            prepared,
            payload=prepared["payload"],
            targets=prepared["targets"],
            plan=prepared["plan"],
        )
        assert saved["content"]["services"][0]["quantity"] is None
        assert saved["evidence_refs"][0]["row"]["fields"]["quantity"] == field
        assert any("formula" in item["text"].lower() for item in saved["content"]["observations"])
        _canonical_empty(db)


@pytest.mark.parametrize(
    "change",
    [
        "payload",
        "mapping",
        "selected_rows",
        "target_row",
        "image_selection",
        "document",
        "revision",
        "source",
        "rescan",
        "bytes",
        "quarantine",
    ],
)
def test_changed_confirmation_input_or_source_never_saves_partial_graph(xlsx_case, change):
    x = xlsx_case
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        preview = _preview(db, x)
        values = {}
        if change == "payload":
            values["payload"] = copy.deepcopy(x.payload)
            values["payload"]["services"][0]["label"] = "Changed after preview"
        elif change == "mapping":
            values["plan"] = copy.deepcopy(x.plan)
            values["plan"]["mapping"]["defect_description"] = 3
        elif change == "selected_rows":
            values["plan"], values["targets"] = copy.deepcopy(x.plan), copy.deepcopy(x.targets)
            values["plan"]["selections"][0]["row"] = 4
            for target in values["targets"]:
                if target["row"] == 2:
                    target["row"] = 4
        elif change in {"target_row", "image_selection"}:
            values["targets"] = copy.deepcopy(x.targets)
            if change == "target_row":
                values["targets"][0]["row"] = 3
            else:
                values["targets"][0]["image_ids"].pop()
        elif change == "document":
            values["document_hash"] = "0" * 64
        elif change == "revision":
            scopes.save_revision(
                db, actor, x.ids[2], 1, {"assumptions": ["Concurrent manual edit"]}
            )
            db.commit()
        elif change == "source":
            values["source_id"] = _uid(999)
        elif change == "rescan":
            scan = xlsx.intake().scan_source(db, actor, x.ids[2], x.source_id, settings=x.settings)
            assert scan["status"] == "clean" and scan["processing_error"] is None
            db.commit()
        else:
            source, _, _ = xlsx.intake()._document(
                db, actor, x.ids[2], x.source_id, x.settings.storage_root
            )
            if change == "bytes":
                Path(db.get(StoredFile, source.stored_file_id).storage_path).write_bytes(
                    b"tampered synthetic workbook"
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
        assert rejected.value.status_code == (404 if change == "source" else 409)
        assert _counts(db) == before
        current = scopes.read_revision(db, actor, x.ids[2])
        assert current["revision"] == (2 if change == "revision" else 1)
        assert not current["content"]["defects"]
        _canonical_empty(db)


@pytest.mark.parametrize("change", ["foreign", "read_only", "inactive", "other_administrator"])
def test_current_actor_rights_and_exact_preview_identity_are_required(xlsx_case, change):
    x = xlsx_case
    with x.factory() as db:
        preview = _preview(db, x)
        actor_id = x.ids[0]
        if change in {"foreign", "other_administrator"}:
            actor_id = x.ids[1]
            if change == "other_administrator":
                db.execute(update(User).where(User.id == actor_id).values(role="administrator"))
        else:
            changes = {"role": "read_only"} if change == "read_only" else {"is_active": False}
            db.execute(update(User).where(User.id == actor_id).values(**changes))
        db.commit()
        before = _counts(db)
        with pytest.raises(scopes.DraftScopeError) as rejected:
            _save(db, x, preview, actor_id=actor_id)
        assert (
            rejected.value.status_code
            == {"foreign": 404, "read_only": 403, "inactive": 403, "other_administrator": 409}[
                change
            ]
        )
        assert _counts(db) == before
        _canonical_empty(db)


def test_malformed_plan_targets_and_broken_graph_refuse_without_writes(xlsx_case):
    x = xlsx_case
    cases = []
    for change in ("boolean_column", "extra_mapping", "oversized_batch", "duplicate_row"):
        plan = copy.deepcopy(x.plan)
        if change == "boolean_column":
            plan["mapping"]["defect_label"] = True
        elif change == "extra_mapping":
            plan["mapping"]["unit_sell_rate"] = 1
        elif change == "oversized_batch":
            plan["selections"] *= 13
        else:
            plan["selections"].append(copy.deepcopy(plan["selections"][0]))
        cases.append({"plan": plan})
    for change in (
        "missing_target",
        "unknown_kind",
        "boolean_row",
        "unknown_image",
        "duplicate_image",
        "duplicate_target",
    ):
        targets = copy.deepcopy(x.targets)
        if change == "missing_target":
            targets[0]["target_id"] = _uid(998)
        elif change == "unknown_kind":
            targets[0]["target_kind"] = "estimate"
        elif change == "boolean_row":
            targets[0]["row"] = True
        elif change == "unknown_image":
            targets[0]["image_ids"] = ["foreign-image"]
        elif change == "duplicate_image":
            targets[0]["image_ids"] *= 2
        else:
            targets.append(copy.deepcopy(targets[0]))
        cases.append({"targets": targets})
    payload = copy.deepcopy(x.payload)
    payload["services"][0]["opening_ids"] = [_uid(997)]
    cases.append({"payload": payload})
    with x.factory() as db:
        before = _counts(db)
        for changed in cases:
            with pytest.raises(scopes.DraftScopeError) as rejected:
                _preview(db, x, **changed)
            assert rejected.value.status_code == 422
            assert _counts(db) == before
        _canonical_empty(db)


def test_scope_workbook_authority_is_independent_of_pricing_and_source_purpose(
    xlsx_case, monkeypatch
):
    x = xlsx_case
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        with monkeypatch.context() as limited:
            limited.setitem(
                ROLE_PERMISSIONS,
                "estimator",
                ROLE_PERMISSIONS["estimator"]
                - {"estimate:read", "estimate:write", "library:read", "library:write"},
            )
            assert xlsx.intake().source_info(db, actor, x.ids[2], x.source_id)["ready"]
            saved = _save(db, x)
            assert saved["schema_version"] == "CLASSIFIRE-DRAFT-SCOPE-v5"
            with pytest.raises(scopes.DraftScopeError) as rejected:
                pricing.intake().list_sources(db, actor, x.ids[2])
            assert rejected.value.status_code == 403
        with pytest.raises(scopes.DraftScopeError) as rejected:
            pricing.intake()._document(db, actor, x.ids[2], x.source_id, x.settings.storage_root)
        assert rejected.value.status_code == 404
        before = _counts(db)
        with pytest.raises(scopes.DraftScopeError, match="PRICING_XLSX_UPLOAD_CONFLICT"):
            pricing.intake().retain(
                db, actor, x.ids[2], "same-bytes-pricing.xlsx", x.content, settings=x.settings
            )
        assert _counts(db) == before
        assert (
            db.scalar(
                select(StoredFile.purpose).where(
                    StoredFile.sha256 == hashlib.sha256(x.content).hexdigest()
                )
            )
            == "draft_scope_xlsx"
        )
        _canonical_empty(db)


def test_image_render_rechecks_permissions_after_worker_returns(xlsx_case, monkeypatch):
    x = xlsx_case
    real_worker = xlsx._run_worker
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        occurrence = x.document["sheets"][0]["images"][0]["occurrence_id"]

        def revoke_after_render(*args, **kwargs):
            result = real_worker(*args, **kwargs)
            db.execute(update(User).where(User.id == actor.id).values(is_active=False))
            db.flush()
            return result

        monkeypatch.setattr(xlsx, "_run_worker", revoke_after_render)
        before = _counts(db)
        with pytest.raises(scopes.DraftScopeError) as rejected:
            xlsx.image_preview(db, actor, x.ids[2], x.source_id, 1, occurrence, settings=x.settings)
        assert rejected.value.status_code == 403
        assert _counts(db) == before
        _canonical_empty(db)
        db.rollback()


def test_failed_revision_audit_rolls_back_the_entire_workbook_save(xlsx_case, monkeypatch):
    x = xlsx_case

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("Synthetic audit failure")

    with x.factory() as db:
        preview = _preview(db, x)
        before = _counts(db)
        with monkeypatch.context() as failure:
            failure.setattr(scopes, "record_audit", fail_audit)
            with pytest.raises(RuntimeError, match="Synthetic audit failure"):
                _save(db, x, preview)
        db.rollback()
        assert _counts(db) == before
        assert scopes.revision_bytes(db, db.get(User, x.ids[0]), x.ids[2], 1) == x.prior
        assert scopes.read_revision(db, db.get(User, x.ids[0]), x.ids[2])["revision"] == 1
        _canonical_empty(db)


def test_pdf_history_and_workbook_edit_rereview_delete_import_keep_all_claims(xlsx_case):
    x = xlsx_case
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        source = pdf.retain_pdf(
            db, actor, x.ids[2], "historical.pdf", pdf_bytes(), settings=x.settings
        )
        db.commit()
        result = pdf.scan_source(db, actor, x.ids[2], source.id, settings=x.settings)
        assert result["status"] == "clean" and result["processing_error"] is None
        db.commit()
        observation = pdf.review_page(
            db,
            actor,
            x.ids[2],
            source.id,
            1,
            1,
            "Historical page observation",
            "Unresolved",
            source.document_sha256,
            settings=x.settings,
        )
        old_v3 = scopes._json(observation)
        payload = copy.deepcopy(x.payload)
        payload["observations"] = (
            copy.deepcopy(observation["content"]["observations"]) + payload["observations"]
        )
        page_targets = [{"target_kind": "defect", "target_id": payload["defects"][0]["id"]}]
        page_preview = pdf.preview_scope_page(
            db,
            actor,
            x.ids[2],
            source.id,
            2,
            1,
            payload,
            page_targets,
            source.document_sha256,
            settings=x.settings,
        )
        page_review = pdf.save_scope_page(
            db,
            actor,
            x.ids[2],
            source.id,
            2,
            1,
            payload,
            page_targets,
            source.document_sha256,
            page_preview["review_sha256"],
            settings=x.settings,
        )
        old_v4 = scopes._json(page_review)
        saved = _save(db, x, revision=3, payload=page_review["content"])
        old_v5 = scopes._json(saved)
        assert saved["schema_version"] == "CLASSIFIRE-DRAFT-SCOPE-v5"
        assert all(ref in saved["evidence_refs"] for ref in page_review["evidence_refs"])
        assert len(saved["evidence_refs"]) == 6
        service_id = saved["content"]["services"][0]["id"]
        old_ref = next(
            ref
            for ref in saved["evidence_refs"]
            if ref.get("source_kind") == "xlsx" and ref["target_id"] == service_id
        )
        changed = copy.deepcopy(saved["content"])
        changed["services"][0]["label"] = "Reviewed wording changed"
        edited = scopes.save_revision(db, actor, x.ids[2], 4, changed)
        assert edited["evidence_refs"] == saved["evidence_refs"]
        assert "changed" in reference_status(old_ref, edited["content"])
        assert "SCOPE_WORKBOOK_REVIEW_CHANGED" in pdf.scope_evidence_staleness(
            db, actor, x.ids[2], edited, storage_root=x.settings.storage_root
        )
        target = next(target for target in x.targets if target["target_id"] == service_id)
        reviewed = _save(db, x, revision=5, payload=edited["content"], targets=[target])
        assert len(reviewed["evidence_refs"]) == 6
        new_ref = next(
            ref
            for ref in reviewed["evidence_refs"]
            if ref.get("source_kind") == "xlsx" and ref["target_id"] == service_id
        )
        assert new_ref["target_sha256"] != old_ref["target_sha256"]
        assert not pdf.scope_evidence_staleness(
            db, actor, x.ids[2], reviewed, storage_root=x.settings.storage_root
        )
        deleted = copy.deepcopy(reviewed["content"])
        deleted["services"] = deleted["services"][1:]
        removed = scopes.save_revision(db, actor, x.ids[2], 6, deleted)
        assert removed["evidence_refs"] == reviewed["evidence_refs"]
        assert "removed" in reference_status(new_ref, removed["content"])
        raw = scopes._json(removed)
        target_draft = scopes.create_draft_project(
            db, actor, "XLSX-JSON-IMPORT", "Unverified source history"
        )
        imported = scopes.apply_import(
            db, actor, target_draft.id, 1, raw, hashlib.sha256(raw).hexdigest()
        )
        assert len(imported["evidence_refs"]) == 6
        assert all(ref["origin"] == "imported_unverified" for ref in imported["evidence_refs"])
        assert "SCOPE_SOURCE_UNVERIFIED" in pdf.scope_evidence_staleness(
            db, actor, target_draft.id, imported, storage_root=x.settings.storage_root
        )
        with pytest.raises(scopes.DraftScopeError) as rejected:
            xlsx.intake()._document(
                db, actor, target_draft.id, x.source_id, x.settings.storage_root
            )
        assert rejected.value.status_code == 404
        for revision, content in ((2, old_v3), (3, old_v4), (4, old_v5)):
            assert scopes.revision_bytes(db, actor, x.ids[2], revision) == content
        workbook_refs = [
            ref for ref in removed["evidence_refs"] if ref.get("source_kind") == "xlsx"
        ]
        later_observation = pdf.review_page(
            db,
            actor,
            x.ids[2],
            source.id,
            7,
            1,
            "Later PDF observation preserves workbook history",
            "Unresolved",
            source.document_sha256,
            settings=x.settings,
        )
        assert later_observation["schema_version"] == "CLASSIFIRE-DRAFT-SCOPE-v5"
        assert [
            ref for ref in later_observation["evidence_refs"] if ref.get("source_kind") == "xlsx"
        ] == workbook_refs
        later_preview = pdf.preview_scope_page(
            db,
            actor,
            x.ids[2],
            source.id,
            8,
            1,
            later_observation["content"],
            page_targets,
            source.document_sha256,
            settings=x.settings,
        )
        later_entity = pdf.save_scope_page(
            db,
            actor,
            x.ids[2],
            source.id,
            8,
            1,
            later_observation["content"],
            page_targets,
            source.document_sha256,
            later_preview["review_sha256"],
            settings=x.settings,
        )
        assert later_entity["schema_version"] == "CLASSIFIRE-DRAFT-SCOPE-v5"
        assert [
            ref for ref in later_entity["evidence_refs"] if ref.get("source_kind") == "xlsx"
        ] == workbook_refs
        assert scopes.revision_bytes(db, actor, x.ids[2], 4) == old_v5
        _canonical_empty(db)
        db.commit()


def test_workbook_package_import_manual_edit_and_reexport_preserve_originals(
    xlsx_case, monkeypatch
):
    x = xlsx_case
    monkeypatch.setattr(packages, "get_settings", lambda: x.settings)
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        saved = _save(db, x)
        payload = copy.deepcopy(saved["content"])
        payload["services"].pop()
        removed = scopes.save_revision(db, actor, x.ids[2], 2, payload)
        original = save_package(db, actor, x.ids[2], {"scope_revision": 3})
        raw = original.archive_bytes
        checked = inspection.inspect_package(raw)
        assert checked.scope["evidence_refs"] == removed["evidence_refs"]
        assert len(checked.manifest["source_manifest"]) == len(removed["evidence_refs"])
        imported = imports.create_import(
            db,
            actor,
            raw,
            expected_sha256=original.archive_hash,
            reference="XLSX-PACKAGE-IMPORT",
            name="Unverified workbook package",
            settings=x.settings,
        )
        imported_id = imported.draft_scope_id
        local = scopes.read_revision(db, actor, imported_id)
        assert all(ref["origin"] == "imported_unverified" for ref in local["evidence_refs"])
        assert len(local["evidence_refs"]) == len(removed["evidence_refs"])
        edited_payload = copy.deepcopy(local["content"])
        edited_payload["assumptions"].append("Local change keeps imported source history")
        edited = scopes.save_revision(db, actor, imported_id, local["revision"], edited_payload)
        assert edited["evidence_refs"] == local["evidence_refs"]
        exported = save_package(db, actor, imported_id, {"scope_revision": edited["revision"]})
        exported_bytes, exported_id = exported.archive_bytes, exported.id
        reopened = inspection.inspect_package(exported_bytes)
        assert len(list(reopened.walk())) == 2
        assert next(iter(reopened.origins.values())).archive_sha256 == packages.digest(raw)
        assert reopened.scope["evidence_refs"] == edited["evidence_refs"]
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


def _http_values(client, x):
    path = f"/scopes/{x.ids[2]}/workbooks/{x.source_id}"
    page = client.get(path)
    assert page.status_code == 200, page.text
    return path, {
        "csrf_token": _csrf(page.text),
        "expected_revision": "1",
        "document_sha256": x.document_hash,
        "plan": json.dumps(x.plan),
        "payload": json.dumps(x.payload),
        "targets": json.dumps(x.targets),
    }


def _confirmation(response):
    assert response.status_code == 200, response.text
    parser = _ReviewForms()
    parser.feed(response.text)
    form = next(form for form in parser.forms if "preview_token" in form["values"])
    assert form["action"].endswith("/confirm")
    return form["action"], form["values"] | {"confirm": "save"}


def test_ui_map_edit_back_confirm_replay_and_reconstructed_app(xlsx_app):
    x = xlsx_app
    with x.factory() as db:
        before = _counts(db)
        before_audits = set(db.scalars(select(AuditEvent.id)))
    with TestClient(x.app) as client:
        _login(client)
        path, values = _http_values(client, x)
        mapped = client.post(
            path + "/map",
            data={key: value for key, value in values.items() if key not in {"payload", "targets"}},
        )
        assert mapped.status_code == 200 and "D-01" in mapped.text
        preview = client.post(path + "/preview", data=values)
        confirm_path, confirmed = _confirmation(preview)
        assert (
            "D-01" in preview.text
            and "Pipe group" in preview.text
            and "Cable group" in preview.text
        )
        edit_values = {
            key: value
            for key, value in confirmed.items()
            if key not in {"preview_token", "confirm"}
        }
        editing = client.post(path + "/preview", data=edit_values | {"action": "edit"})
        assert editing.status_code == 200 and "preview_token" not in editing.text
        invalid_plan = copy.deepcopy(x.plan)
        invalid_plan["mapping"]["defect_label"] = []
        invalid = client.post(
            path + "/map",
            data={key: value for key, value in values.items() if key not in {"payload", "targets"}}
            | {"plan": json.dumps(invalid_plan)},
        )
        assert invalid.status_code == 422 and "preview_token" not in invalid.text
        with x.factory() as db:
            assert _counts(db) == before
        assert (
            client.post(confirm_path, data=confirmed | {"csrf_token": "wrong"}).status_code == 403
        )
        assert (
            client.post(
                confirm_path,
                data={key: value for key, value in confirmed.items() if key != "confirm"},
            ).status_code
            == 422
        )
        saved = client.post(confirm_path, data=confirmed, follow_redirects=False)
        assert saved.status_code == 303, saved.text
        assert client.post(confirm_path, data=confirmed).status_code == 409
        download = client.get(f"/scopes/{x.ids[2]}/download?revision=2")
        assert (
            download.status_code == 200
            and download.json()["schema_version"] == "CLASSIFIRE-DRAFT-SCOPE-v5"
        )
        raw = download.content
        image = x.document["sheets"][0]["images"][0]
        image_path = path + f"/images/1/{image['occurrence_id']}.png"
        picture = client.get(image_path)
        assert picture.status_code == 200
        assert picture.headers["cache-control"] == "no-store"
        assert picture.headers["x-content-type-options"] == "nosniff"
        assert hashlib.sha256(picture.content).hexdigest() == image["preview_sha256"]
    rebuilt = _app(x.factory)
    rebuilt.include_router(xlsx_router)
    with TestClient(rebuilt) as client:
        _login(client)
        assert client.get(f"/scopes/{x.ids[2]}/download?revision=2").content == raw
        assert client.get(image_path).content == picture.content
        assert "D-01" in client.get(path).text
    with x.factory() as db:
        assert _counts(db) == (before[0] + 1, before[1] + 3)
        added_actions = Counter(
            item.action for item in db.scalars(select(AuditEvent)) if item.id not in before_audits
        )
        assert added_actions == {"draft_scope.save": 1, "draft_scope.download": 2}
        _canonical_empty(db)


@pytest.mark.parametrize("change", ["payload", "token", "session", "permission", "expired"])
def test_ui_confirmation_rejects_changed_content_or_authority(xlsx_app, monkeypatch, change):
    x = xlsx_app
    with x.factory() as db:
        before = _counts(db)
    with TestClient(x.app) as client:
        _login(client)
        path, values = _http_values(client, x)
        if change == "expired":
            from itsdangerous import TimestampSigner

            from classifire import draft_scope_xlsx_ui as ui

            class OldSigner(TimestampSigner):
                def get_timestamp(self):
                    return super().get_timestamp() - 901

            serializer = ui._signer()
            serializer.signer = OldSigner
            with monkeypatch.context() as expired:
                expired.setattr(ui, "_signer", lambda: serializer)
                response = client.post(path + "/preview", data=values)
        else:
            response = client.post(path + "/preview", data=values)
        confirm_path, confirmed = _confirmation(response)
        if change == "payload":
            payload = json.loads(confirmed["payload"])
            payload["services"][0]["label"] = "Changed after confirmation preview"
            confirmed["payload"] = json.dumps(payload)
        elif change == "token":
            confirmed["preview_token"] += "tampered"
        elif change == "permission":
            with x.factory() as db:
                db.execute(update(User).where(User.id == x.ids[0]).values(role="read_only"))
                db.commit()
        if change == "session":
            with TestClient(x.app) as other_session:
                _login(other_session)
                confirmed["csrf_token"] = _csrf(other_session.get(path).text)
                rejected = other_session.post(confirm_path, data=confirmed)
        else:
            rejected = client.post(confirm_path, data=confirmed)
        assert (
            rejected.status_code
            == {"payload": 409, "token": 422, "session": 422, "permission": 403, "expired": 422}[
                change
            ]
        )
    with x.factory() as db:
        assert _counts(db) == before
        _canonical_empty(db)


def test_http_upload_scan_and_foreign_source_boundary(pdf_app, monkeypatch):
    x = pdf_app
    x.app.include_router(xlsx_router)
    monkeypatch.setattr("classifire.draft_scope_xlsx_ui.get_settings", lambda: x.settings)
    path = f"/scopes/{x.ids[2]}/workbooks"
    with TestClient(x.app) as client, TestClient(x.app) as foreign:
        _login(client)
        _login(foreign, "other")
        page = client.get(path)
        assert page.status_code == 200
        csrf = _csrf(page.text)
        with x.factory() as db:
            before = _counts(db)
        bad = client.post(
            path + "/upload",
            data={"csrf_token": csrf},
            files={"file": ("wrong.pdf", pdf_bytes(), "application/pdf")},
        )
        assert bad.status_code == 422
        with x.factory() as db:
            assert _counts(db) == before
        upload = client.post(
            path + "/upload",
            data={"csrf_token": csrf},
            files={
                "file": (
                    "synthetic-defects.xlsx",
                    workbook_bytes(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
            follow_redirects=False,
        )
        assert upload.status_code == 303, upload.text
        source_path = upload.headers["location"]
        source_id = source_path.rsplit("/", 1)[1]
        pending = client.get(source_path)
        assert pending.status_code == 200 and "Scan status: pending" in pending.text
        assert foreign.get(source_path).status_code == 404
        assert client.get(source_path + "/images/1/image-1.png").status_code == 409
        assert client.post(source_path + "/scan", data={"csrf_token": "wrong"}).status_code == 403
        scanned = client.post(
            source_path + "/scan", data={"csrf_token": _csrf(pending.text)}, follow_redirects=False
        )
        assert scanned.status_code == 303, scanned.text
        ready = client.get(source_path)
        assert ready.status_code == 200 and "Scan status: clean" in ready.text
        assert "Defects" in ready.text and "Other sheet" in ready.text
        assert client.get(source_path + "/images/1/image-1.png").status_code == 200
    with x.factory() as db:
        assert _counts(db)[0] == before[0]
        info = xlsx.intake().source_info(db, db.get(User, x.ids[0]), x.ids[2], source_id)
        assert info["ready"]
        stored = db.scalar(select(StoredFile).where(StoredFile.sha256 == info["sha256"]))
        assert stored.purpose == "draft_scope_xlsx"
        _canonical_empty(db)
