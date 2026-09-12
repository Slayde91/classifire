from __future__ import annotations

import copy
import hashlib
import json

import pytest
from sqlalchemy import update
from test_draft_register_evidence import (
    no_writes,
    save_pdf,
    save_word,
    save_xlsx,
)
from test_draft_register_evidence import (
    pdf_app as _pdf_app,
)
from test_draft_register_evidence import (
    pdf_setup as _pdf_setup,
)
from test_draft_register_evidence import (
    postgresql_session_factory as _postgres,
)
from test_draft_register_evidence import (
    review_case as _review_case,
)
from test_draft_register_evidence import (
    scope_password_hash as _password_hash,
)
from test_draft_register_evidence import (
    setup as _setup,
)
from test_draft_register_evidence import (
    word_app as _word_app,
)
from test_draft_register_evidence import (
    word_case as _word_case,
)
from test_draft_register_evidence import (
    xlsx_case as _xlsx_case,
)
from test_draft_scope import sample_payload, uid

from classifire.config import Settings
from classifire.models import DraftScopeDocxSource, User
from classifire.services import draft_scope as scopes
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


def selected(db, x, revision, *, actor=None, draft_id=None, defect_id=None):
    return evidence_context(
        db,
        actor or db.get(User, x.ids[0]),
        draft_id or x.ids[2],
        revision,
        None,
        defect_id=defect_id or x.payload["defects"][0]["id"],
        settings=x.settings,
    )


def picture(db, x, revision, ref, *, actor=None, draft_id=None, defect_id=None):
    return evidence_image(
        db,
        actor or db.get(User, x.ids[0]),
        draft_id or x.ids[2],
        revision,
        None,
        defect_id=defect_id or x.payload["defects"][0]["id"],
        ref_index=ref["index"],
        image_id=ref["images"][0]["id"],
        settings=x.settings,
    )


@pytest.mark.parametrize("kind", ["pdf", "docx", "xlsx"])
def test_native_defect_sources_remain_exact_without_inferred_descendants(request, kind):
    fixture, save = {
        "pdf": ("review_case", save_pdf),
        "docx": ("word_case", save_word),
        "xlsx": ("xlsx_case", save_xlsx),
    }[kind]
    x = request.getfixturevalue(fixture)
    if kind == "docx":
        next(target for target in x.targets if target["target_kind"] == "defect")["image_ids"] = [
            "picture-1"
        ]
    elif kind == "xlsx":
        next(target for target in x.targets if target["target_kind"] == "defect")["image_ids"] = [
            item["occurrence_id"] for item in x.document["sheets"][0]["images"]
        ]
    x.payload["defects"].append(
        {
            "id": uid(9500),
            "label": "Separate unreviewed Defect",
            "description": "Its sources are unknown",
        }
    )
    with x.factory() as db:
        saved = save(db, x)
        db.commit()
        actor = db.get(User, x.ids[0])
        with no_writes(db):
            value = selected(db, x, saved["revision"])
            assert len(value["refs"]) == 1
            ref = value["refs"][0]
            assert ref["role"] == "selected_defect" and ref["availability"] == "verified"
            assert ref["claim_changed"] is False
            assert ref["metadata"]["target_id"] == x.payload["defects"][0]["id"]
            assert (
                value["selection"]["opening_id"] is None
                and value["selection"]["service_id"] is None
            )
            assert value["selection"]["opening_ids"] == []
            assert value["selection"]["relationship_warnings"] == []
            assert not any("inherited" in notice for notice in value["notices"])
            own_ref_count = sum(
                item.get("target_kind") == "defect"
                and item["target_id"] == x.payload["defects"][0]["id"]
                for item in saved["evidence_refs"]
            )
            assert own_ref_count == 1 and len(saved["evidence_refs"]) > own_ref_count
            png, media_type = picture(db, x, saved["revision"], ref)
            assert media_type == "image/png" and png.startswith(b"\x89PNG")
            if kind == "xlsx":
                fields = {field["label"]: field for field in ref["fields"]}
                assert fields["defect label"]["value"] == "D-01"
                assert fields["quantity"]["value"] is None
            else:
                assert "Synthetic" in ref["text"]
            other = selected(db, x, saved["revision"], defect_id=uid(9500))
            assert other["refs"] == [] and other["selection"]["relationship_warnings"]
            with pytest.raises(scopes.DraftScopeError, match="REGISTER_EVIDENCE_IMAGE_NOT_FOUND"):
                picture(db, x, saved["revision"], ref, defect_id=uid(9500))
        before = scopes._json(scopes.read_revision(db, actor, x.ids[2], saved["revision"]))
        orphan_content = copy.deepcopy(saved["content"])
        orphan_content["openings"] = []
        orphan_content["services"] = []
        orphan = scopes.save_revision(db, actor, x.ids[2], saved["revision"], orphan_content)
        db.commit()
        with no_writes(db):
            orphan_view = selected(db, x, orphan["revision"])
            assert orphan_view["selection"]["relationship_warnings"] == [
                "No Opening is linked to this Defect; its physical relationships remain unresolved."
            ]
            assert orphan_view["refs"] == value["refs"]
            assert picture(db, x, orphan["revision"], ref)[0] == png
            assert (
                scopes._json(scopes.read_revision(db, actor, x.ids[2], saved["revision"])) == before
            )
            assert orphan_view["scope"]["content"] == orphan_content
        edited = copy.deepcopy(orphan_content)
        edited["defects"][0]["description"] = (
            "Human edit after source review; original evidence retained"
        )
        latest = scopes.save_revision(db, actor, x.ids[2], orphan["revision"], edited)
        db.commit()
        with no_writes(db):
            stale = selected(db, x, latest["revision"])
            stale_ref = stale["refs"][0]
            assert stale_ref["claim_changed"] is True and "changed" in stale_ref["status"]
            assert stale_ref["availability"] == "verified"
            assert stale_ref["text"] == ref["text"] and stale_ref["fields"] == ref["fields"]
            assert picture(db, x, latest["revision"], ref)[0] == png
            assert selected(db, x, saved["revision"]) == value
            assert scopes.read_revision(db, actor, x.ids[2], latest["revision"]) == latest
            (x.settings.storage_root.parent / f"defect-{kind}.png").write_bytes(png)
            (x.settings.storage_root.parent / f"defect-{kind}.json").write_text(
                json.dumps(stale, indent=2), encoding="utf-8"
            )
    with x.factory() as db, no_writes(db):
        assert selected(db, x, saved["revision"]) == value
        assert selected(db, x, latest["revision"]) == stale
        assert picture(db, x, latest["revision"], ref)[0] == png


def test_defect_selection_rejects_mixed_and_missing_ids_without_autoflush(setup, tmp_path):
    settings = Settings(storage_root=tmp_path, _env_file=None)
    with setup() as db:
        actor, foreign = db.get(User, uid(100)), db.get(User, uid(101))
        draft = scopes.create_draft_project(
            db, actor, "DEFECT-SELECT", "Synthetic explicit selection"
        )
        saved = scopes.save_revision(db, actor, draft.id, 1, sample_payload())
        db.commit()
        pending = User(
            email="pending-defect@example.test",
            full_name="Pending",
            role="estimator",
            is_active=True,
            password_hash="unused",  # noqa: S106 - synthetic, never authenticates
        )
        db.add(pending)
        with no_writes(db):
            for defect_id, opening_id, service_id in (
                (None, None, None),
                ("", None, None),
                (uid(9999), None, None),
                (uid(2), None, None),
                (uid(1), uid(2), None),
                (uid(1), None, uid(5)),
                (uid(1), uid(2), uid(5)),
                (uid(1), "", None),
            ):
                with pytest.raises(
                    scopes.DraftScopeError, match="REGISTER_EVIDENCE_SELECTION_INVALID"
                ):
                    evidence_context(
                        db,
                        actor,
                        draft.id,
                        2,
                        opening_id,
                        service_id,
                        defect_id=defect_id,
                        settings=settings,
                    )
                with pytest.raises(
                    scopes.DraftScopeError, match="REGISTER_EVIDENCE_SELECTION_INVALID"
                ):
                    evidence_image(
                        db,
                        actor,
                        draft.id,
                        2,
                        opening_id,
                        service_id,
                        defect_id=defect_id,
                        ref_index=0,
                        image_id="page",
                        settings=settings,
                    )
            value = evidence_context(
                db, actor, draft.id, 2, None, defect_id=uid(1), settings=settings
            )
            assert value["refs"] == [] and value["scope"]["content"] == saved["content"]
            assert pending.id is None
            with pytest.raises(scopes.DraftScopeError) as denied:
                evidence_context(
                    db, foreign, draft.id, 2, None, defect_id=uid(1), settings=settings
                )
            assert denied.value.status_code in (403, 404)
        db.expunge(pending)
        db.execute(update(User).where(User.id == actor.id).values(is_active=False))
        db.commit()
        with no_writes(db), pytest.raises(scopes.DraftScopeError) as denied:
            evidence_image(
                db,
                actor,
                draft.id,
                2,
                None,
                defect_id=uid(1),
                ref_index=0,
                image_id="page",
                settings=settings,
            )
        assert denied.value.status_code == 403


def test_defect_import_quarantine_and_permissions_keep_source_boundaries(word_case, monkeypatch):
    x = word_case
    next(target for target in x.targets if target["target_kind"] == "defect")["image_ids"] = [
        "picture-1"
    ]
    with x.factory() as db:
        saved = save_word(db, x)
        actor, foreign = db.get(User, x.ids[0]), db.get(User, x.ids[1])
        db.commit()
        value = selected(db, x, 2)
        ref = value["refs"][0]
        original = scopes._json(saved)
        target = scopes.create_draft_project(db, actor, "DEFECT-IMPORT", "Foreign source claims")
        scopes.apply_import(
            db,
            actor,
            target.id,
            1,
            original,
            expected_source_hash=hashlib.sha256(original).hexdigest(),
        )
        db.commit()
        with monkeypatch.context() as patch:

            def forbidden(*args, **kwargs):
                raise AssertionError("Foreign IDs must not resolve through local intake.")

            patch.setattr(DraftSourceIntake, "_document", forbidden)
            with no_writes(db):
                imported = selected(db, x, 2, draft_id=target.id)
                assert (
                    len(imported["refs"]) == 1 and imported["refs"][0]["role"] == "selected_defect"
                )
                assert imported["refs"][0]["availability"] == "imported_unverified"
                assert imported["refs"][0]["text"] is None and imported["refs"][0]["images"] == []
                assert "Synthetic D-01" not in json.dumps(imported)
                with pytest.raises(
                    scopes.DraftScopeError, match="REGISTER_EVIDENCE_SOURCE_UNAVAILABLE"
                ):
                    picture(db, x, 2, ref, draft_id=target.id)
        with no_writes(db):
            with pytest.raises(scopes.DraftScopeError) as denied:
                selected(db, x, 2, actor=foreign)
            assert denied.value.status_code in (403, 404)
            with pytest.raises(scopes.DraftScopeError) as denied:
                picture(db, x, 2, ref, actor=foreign)
            assert denied.value.status_code in (403, 404)
        source = db.get(DraftScopeDocxSource, x.source_id)
        quarantine_stored_file_bytes_for_update(
            db,
            stored_file_id=source.stored_file_id,
            observed_sha256=source.source_sha256,
            observed_size_bytes=source.source_size_bytes,
        )
        db.commit()
        with no_writes(db):
            quarantined = selected(db, x, 2)
            assert quarantined["refs"][0]["availability"] == "unavailable"
            assert quarantined["refs"][0]["metadata"] == ref["metadata"]
            assert quarantined["refs"][0]["text"] is None and quarantined["refs"][0]["images"] == []
            with pytest.raises(
                scopes.DraftScopeError, match="REGISTER_EVIDENCE_SOURCE_UNAVAILABLE"
            ):
                picture(db, x, 2, ref)
            assert scopes.read_revision(db, actor, x.ids[2], 2) == saved
