from __future__ import annotations

import copy
import hashlib
import json
from contextlib import contextmanager

import pytest
from sqlalchemy import event, update
from test_draft_pdf_intake import pdf_setup as _pdf_setup
from test_draft_pdf_scope_review import _save as save_pdf
from test_draft_pdf_scope_review import review_case as _review_case
from test_draft_pdf_ui import pdf_app as _pdf_app
from test_draft_scope import sample_payload, uid
from test_draft_scope import setup as _setup
from test_draft_scope_docx_review import _save as save_word
from test_draft_scope_docx_review import word_case as _word_case
from test_draft_scope_docx_ui import word_app as _word_app
from test_draft_scope_ui import scope_password_hash as _password_hash
from test_draft_scope_xlsx import _save as save_xlsx
from test_draft_scope_xlsx import xlsx_case as _xlsx_case
from test_shared_file_containment import postgresql_session_factory as _postgres

from classifire.config import Settings
from classifire.models import DraftScopeDocxSource, User
from classifire.services import draft_scope as scopes
from classifire.services import draft_scope_docx as word
from classifire.services.draft_register import evidence_context, evidence_image
from classifire.services.draft_source_intake import DraftSourceIntake
from classifire.services.storage import quarantine_stored_file_bytes_for_update

setup = _setup
pdf_setup = _pdf_setup
pdf_app = _pdf_app
review_case = _review_case
word_app = _word_app
word_case = _word_case
xlsx_case = _xlsx_case
scope_password_hash = _password_hash
postgresql_session_factory = _postgres


@contextmanager
def no_writes(db):
    def check(_conn, _cursor, statement, _parameters, _context, _many):
        assert not statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")), statement

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", check)
    try:
        yield
    finally:
        event.remove(engine, "before_cursor_execute", check)


def context(db, x, revision, opening_index=0, service_index=0):
    return evidence_context(
        db,
        db.get(User, x.ids[0]),
        x.ids[2],
        revision,
        x.payload["openings"][opening_index]["id"],
        x.payload["services"][service_index]["id"] if service_index is not None else None,
        settings=x.settings,
    )


def image(db, x, revision, ref, image_id=None, service_index=0):
    return evidence_image(
        db,
        db.get(User, x.ids[0]),
        x.ids[2],
        revision,
        x.payload["openings"][0]["id"],
        x.payload["services"][service_index]["id"] if service_index is not None else None,
        ref_index=ref["index"],
        image_id=image_id or ref["images"][0]["id"],
        settings=x.settings,
    )


@pytest.mark.parametrize("kind", ["pdf", "docx", "xlsx"])
def test_exact_row_body_and_images_reopen_without_writes(request, kind):
    fixture, save = {
        "pdf": ("review_case", save_pdf),
        "docx": ("word_case", save_word),
        "xlsx": ("xlsx_case", save_xlsx),
    }[kind]
    x = request.getfixturevalue(fixture)
    with x.factory() as db:
        saved = save(db, x)
        db.commit()
        actor = db.get(User, x.ids[0])
        original = scopes.revision_bytes(db, actor, x.ids[2], saved["revision"])
        with no_writes(db):
            value = context(db, x, saved["revision"])
            assert len(value["refs"]) == 3
            assert {ref["role"] for ref in value["refs"]} == {
                "selected_service",
                "opening_context",
                "defect_context",
            }
            assert all(ref["availability"] == "verified" for ref in value["refs"])
            assert "evidence_refs" not in value["scope"]
            assert any("not proof" in notice for notice in value["notices"])
            pictured = next(ref for ref in value["refs"] if ref["images"])
            png, media_type = image(db, x, saved["revision"], pictured)
            assert media_type == "image/png" and png.startswith(b"\x89PNG")
            (x.settings.storage_root.parent / f"register-{kind}.png").write_bytes(png)
            (x.settings.storage_root.parent / f"register-{kind}.json").write_text(
                json.dumps(value, indent=2), encoding="utf-8"
            )
            assert (
                scopes._json(scopes.read_revision(db, actor, x.ids[2], saved["revision"]))
                == original
            )
            if kind == "docx":
                assert all("Synthetic D-01" in ref["text"] for ref in value["refs"])
                assert all(
                    item["quantity"] is None for item in value["scope"]["content"]["services"]
                )
                blank = context(db, x, saved["revision"], 1, None)
                assert blank["selection"]["blank"] is True
                assert {ref["role"] for ref in blank["refs"]} == {
                    "opening_context",
                    "defect_context",
                }
                assert any("dimensions unknown" in ref["text"] for ref in blank["refs"])
            elif kind == "pdf":
                assert all("Synthetic evidence" in ref["text"] for ref in value["refs"])
                assert value["selection"]["opening_ids"] == [
                    item["id"] for item in x.payload["openings"]
                ]
                other = context(db, x, saved["revision"], 1)
                assert other["selection"]["opening_id"] != value["selection"]["opening_id"]
                assert (
                    next(ref for ref in other["refs"] if ref["role"] == "opening_context")[
                        "metadata"
                    ]["target_id"]
                    == x.payload["openings"][1]["id"]
                )
            else:
                assert all(ref["text"] is None for ref in value["refs"])
                second = context(db, x, saved["revision"], service_index=1)
                service_ref = next(
                    ref for ref in second["refs"] if ref["role"] == "selected_service"
                )
                quantity = next(
                    field for field in service_ref["fields"] if field["label"] == "quantity"
                )
                assert quantity["value"] == "0" and quantity["kind"] == "number"
                first_ref = next(ref for ref in value["refs"] if ref["role"] == "selected_service")
                assert (
                    next(field for field in first_ref["fields"] if field["label"] == "quantity")[
                        "value"
                    ]
                    is None
                )
    with x.factory() as db, no_writes(db):
        assert context(db, x, saved["revision"]) == value
        assert image(db, x, saved["revision"], pictured)[0] == png


def test_manual_shared_blank_and_unlinked_rows_preserve_unknowns_and_no_autoflush(setup, tmp_path):
    settings = Settings(storage_root=tmp_path, _env_file=None)
    with setup() as db:
        actor = db.get(User, uid(100))
        foreign = db.get(User, uid(101))
        draft = scopes.create_draft_project(db, actor, "EVIDENCE-MANUAL", "Synthetic row context")
        payload = sample_payload()
        payload["services"][1]["opening_ids"] = []
        saved = scopes.save_revision(db, actor, draft.id, 1, payload)
        db.commit()
        pending = User(
            email="unflushed-evidence@example.test",
            full_name="Pending",
            role="estimator",
            is_active=True,
            password_hash="unused",  # noqa: S106 - synthetic, never authenticates
        )
        db.add(pending)
        with no_writes(db):
            unlinked = evidence_context(db, actor, draft.id, 2, None, uid(6), settings=settings)
            assert unlinked["selection"]["opening_id"] is None
            assert unlinked["selection"]["defect_id"] is None
            assert unlinked["selection"]["opening_ids"] == []
            assert unlinked["selection"]["relationship_warnings"]
            assert unlinked["refs"] == [] and pending.id is None
            assert unlinked["scope"]["content"] == saved["content"]
            blank = evidence_context(db, actor, draft.id, 2, uid(4), settings=settings)
            assert blank["selection"]["blank"] and blank["selection"]["defect_id"] is None
            for opening_id in (uid(2), uid(3)):
                shared = evidence_context(
                    db, actor, draft.id, 2, opening_id, uid(5), settings=settings
                )
                assert shared["selection"]["opening_ids"] == [uid(2), uid(3)]
            for opening_id, service_id in (
                (None, None),
                (None, uid(5)),
                (uid(4), uid(5)),
                (uid(2), uid(6)),
                (uid(999), None),
            ):
                with pytest.raises(
                    scopes.DraftScopeError, match="REGISTER_EVIDENCE_SELECTION_INVALID"
                ):
                    evidence_context(
                        db, actor, draft.id, 2, opening_id, service_id, settings=settings
                    )
            for revision in (None, True, 0, "2"):
                with pytest.raises(
                    scopes.DraftScopeError, match="REGISTER_EVIDENCE_SELECTION_INVALID"
                ):
                    evidence_context(db, actor, draft.id, revision, uid(4), settings=settings)
            with pytest.raises(scopes.DraftScopeError) as denied:
                evidence_context(db, foreign, draft.id, 2, uid(4), settings=settings)
            assert denied.value.status_code in (403, 404)
        db.expunge(pending)
        db.execute(update(User).where(User.id == actor.id).values(is_active=False))
        db.commit()
        with no_writes(db), pytest.raises(scopes.DraftScopeError) as denied:
            evidence_context(db, actor, draft.id, 2, uid(4), settings=settings)
        assert denied.value.status_code == 403


def test_historical_source_remains_inspectable_when_target_claim_is_stale(word_case):
    x = word_case
    with x.factory() as db:
        saved = save_word(db, x)
        db.commit()
        old = context(db, x, 2)
        edited = copy.deepcopy(saved["content"])
        edited["services"][0]["service_type"] = "Changed after review"
        scopes.save_revision(db, db.get(User, x.ids[0]), x.ids[2], 2, edited)
        db.commit()
        with no_writes(db):
            current = context(db, x, 3)
            stale = next(ref for ref in current["refs"] if ref["role"] == "selected_service")
            assert stale["availability"] == "verified" and stale["claim_changed"] is True
            assert "changed since Word review" in stale["status"]
            original_ref = next(ref for ref in old["refs"] if ref["role"] == "selected_service")
            assert stale["text"] == original_ref["text"]
            assert stale["images"] == original_ref["images"]
            assert stale["metadata"]["source_sha256"] == hashlib.sha256(x.content).hexdigest()
            assert all(ref["availability"] == "verified" for ref in current["refs"] if ref != stale)
            assert context(db, x, 2) == old
            pictured = next(ref for ref in old["refs"] if ref["images"])
            assert image(db, x, 3, pictured) == image(db, x, 2, pictured)


@pytest.mark.parametrize("change", ["quarantine", "bytes", "document", "scan"])
def test_changed_source_after_context_read_blocks_text_and_saved_image_url(word_case, change):
    x = word_case
    with x.factory() as db:
        save_word(db, x)
        db.commit()
        prior = context(db, x, 2)
        pictured = next(ref for ref in prior["refs"] if ref["images"])
        source = db.get(DraftScopeDocxSource, x.source_id)
        stored = word.intake()._file(db, source)
        if change == "quarantine":
            quarantine_stored_file_bytes_for_update(
                db,
                stored_file_id=stored.id,
                observed_sha256=source.source_sha256,
                observed_size_bytes=source.source_size_bytes,
            )
        elif change == "bytes":
            from classifire.services.storage import read_clean_stored_file_for_update

            verified = read_clean_stored_file_for_update(
                db,
                stored_file_id=stored.id,
                storage_root=x.settings.storage_root,
                required_purpose="draft_scope_docx",
            )
            assert verified.content == x.content
            path = x.settings.storage_root / stored.storage_path
            path.write_bytes(x.content + b"changed")
        elif change == "document":
            document = json.loads(source.document_json)
            document["blocks"][0]["text"] += " changed"
            document["blocks"][0]["text_sha256"] = hashlib.sha256(
                document["blocks"][0]["text"].encode()
            ).hexdigest()
            source.document_json = json.dumps(document, sort_keys=True, separators=(",", ":"))
            source.document_sha256 = hashlib.sha256(source.document_json.encode()).hexdigest()
        else:
            scan = json.loads(source.scan_json)
            scan["scanner_version"] = "Changed synthetic scanner claim"
            source.scan_json = json.dumps(scan, sort_keys=True, separators=(",", ":"))
        db.commit()
        with no_writes(db):
            changed = context(db, x, 2)
            assert all(
                ref["availability"]
                == ("source_changed" if change in ("document", "scan") else "unavailable")
                for ref in changed["refs"]
            )
            assert all(
                ref["text"] is None and ref["fields"] == [] and ref["images"] == []
                for ref in changed["refs"]
            )
            assert "Synthetic D-01" not in json.dumps(changed)
            assert [ref["metadata"] for ref in changed["refs"]] == [
                ref["metadata"] for ref in prior["refs"]
            ]
            with pytest.raises(
                scopes.DraftScopeError, match="REGISTER_EVIDENCE_SOURCE_UNAVAILABLE"
            ):
                image(db, x, 2, pictured)


def test_image_cannot_select_another_rows_reference_or_unselected_picture(word_case):
    x = word_case
    with x.factory() as db:
        saved = save_word(db, x)
        db.commit()
        value = context(db, x, 2)
        pictured = next(ref for ref in value["refs"] if ref["images"])
        foreign_index = next(
            index
            for index, ref in enumerate(saved["evidence_refs"])
            if ref["target_id"] == x.payload["openings"][1]["id"]
        )
        with no_writes(db):
            for index, identity in (
                (foreign_index, "picture-1"),
                (pictured["index"], "picture-999"),
                (True, "picture-1"),
            ):
                with pytest.raises(
                    scopes.DraftScopeError, match="REGISTER_EVIDENCE_IMAGE_NOT_FOUND"
                ):
                    evidence_image(
                        db,
                        db.get(User, x.ids[0]),
                        x.ids[2],
                        2,
                        x.payload["openings"][0]["id"],
                        x.payload["services"][0]["id"],
                        ref_index=index,
                        image_id=identity,
                        settings=x.settings,
                    )
            with pytest.raises(scopes.DraftScopeError) as denied:
                evidence_image(
                    db,
                    db.get(User, x.ids[1]),
                    x.ids[2],
                    2,
                    x.payload["openings"][0]["id"],
                    x.payload["services"][0]["id"],
                    ref_index=pictured["index"],
                    image_id="picture-1",
                    settings=x.settings,
                )
            assert denied.value.status_code in (403, 404)


def test_imported_foreign_claims_never_resolve_local_ids_or_expose_saved_body(
    word_case, monkeypatch
):
    x = word_case
    with x.factory() as db:
        saved = save_word(db, x)
        actor = db.get(User, x.ids[0])
        original = scopes._json(saved)
        target = scopes.create_draft_project(db, actor, "IMPORTED-EVIDENCE", "Unverified reference")
        scopes.apply_import(
            db,
            actor,
            target.id,
            1,
            original,
            expected_source_hash=hashlib.sha256(original).hexdigest(),
        )
        db.commit()

        def forbidden(*args, **kwargs):
            raise AssertionError("A foreign source ID must never be resolved as a local source.")

        monkeypatch.setattr(DraftSourceIntake, "_document", forbidden)
        with no_writes(db):
            value = evidence_context(
                db,
                actor,
                target.id,
                2,
                x.payload["openings"][0]["id"],
                x.payload["services"][0]["id"],
                settings=x.settings,
            )
            assert len(value["refs"]) == 3
            assert all(ref["availability"] == "imported_unverified" for ref in value["refs"])
            assert all(
                ref["text"] is None and ref["fields"] == [] and ref["images"] == []
                for ref in value["refs"]
            )
            assert all(ref["metadata"]["source_id"] == x.source_id for ref in value["refs"])
            pictured = next(ref for ref in value["refs"] if "picture-1_sha256" in ref["metadata"])
            original_picture = next(
                ref["images"][0] for ref in saved["evidence_refs"] if ref["images"]
            )
            assert pictured["metadata"]["picture-1_sha256"] == original_picture["sha256"]
            assert pictured["metadata"]["picture-1_locator"] == original_picture["locator"]
            assert "Synthetic D-01" not in json.dumps(value)


@pytest.mark.parametrize("change", ["quarantine", "permission"])
def test_image_rechecks_containment_and_actor_after_renderer(word_case, monkeypatch, change):
    x = word_case
    with x.factory() as db:
        saved = save_word(db, x)
        db.commit()
        value = context(db, x, 2)
        pictured = next(ref for ref in value["refs"] if ref["images"])
        original = word.image_preview

        def change_after_render(*args, **kwargs):
            rendered = original(*args, **kwargs)
            assert rendered.startswith(b"\x89PNG")
            if change == "quarantine":
                source = db.get(DraftScopeDocxSource, x.source_id)
                quarantine_stored_file_bytes_for_update(
                    db,
                    stored_file_id=source.stored_file_id,
                    observed_sha256=source.source_sha256,
                    observed_size_bytes=source.source_size_bytes,
                )
            else:
                db.execute(update(User).where(User.id == x.ids[0]).values(is_active=False))
            return rendered

        monkeypatch.setattr(word, "image_preview", change_after_render)
        with pytest.raises(scopes.DraftScopeError) as denied:
            image(db, x, 2, pictured)
        assert denied.value.status_code == (409 if change == "quarantine" else 403)
        db.rollback()
        assert scopes.read_revision(db, db.get(User, x.ids[0]), x.ids[2], 2) == saved


def test_imported_suggestion_lineage_and_workbook_coordinates_omit_source_values(
    setup, tmp_path, monkeypatch
):
    from test_draft_suggestion_evidence import suggestion_scope

    source = suggestion_scope()
    original = scopes._json(source)
    settings = Settings(storage_root=tmp_path, _env_file=None)
    with setup() as db:
        actor = db.get(User, uid(100))
        draft = scopes.create_draft_project(
            db, actor, "IMPORTED-MIXED-EVIDENCE", "Unverified claims"
        )
        scopes.apply_import(
            db,
            actor,
            draft.id,
            1,
            original,
            expected_source_hash=hashlib.sha256(original).hexdigest(),
        )
        db.commit()

        def forbidden(*args, **kwargs):
            raise AssertionError("Imported claims must never trigger local source lookup.")

        monkeypatch.setattr(DraftSourceIntake, "_document", forbidden)
        with no_writes(db):
            value = evidence_context(
                db, actor, draft.id, 2, source["content"]["openings"][0]["id"], settings=settings
            )
            assert all(ref["availability"] == "imported_unverified" for ref in value["refs"])
            suggestion = next(
                ref for ref in value["refs"] if "suggestion_schema" in ref["metadata"]
            )
            assert suggestion["metadata"]["suggestion_provider"] == "scripted"
            assert suggestion["metadata"]["suggestion_model"] == "synthetic-page-suggester"
            assert suggestion["metadata"]["suggestion_input_sha256"] == "1" * 64
            workbook = next(
                ref for ref in value["refs"] if ref["metadata"]["source_kind"] == "xlsx"
            )
            assert workbook["metadata"]["quantity_cell"] == "C14"
            assert workbook["metadata"]["quantity_mapped_column"] == 3
            assert workbook["metadata"]["height_mm_mapped_column"] is None
            assert workbook["metadata"]["image-1_preview_sha256"] == "b" * 64
            serialized = json.dumps(value)
            assert "untrusted source text" not in serialized
            assert "untrusted suggested rationale" not in serialized
            assert "Original proposed defect" not in serialized
            assert "=1+2" not in serialized
