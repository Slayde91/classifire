from __future__ import annotations

import hashlib
import io
import json
import zipfile
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_draft_pdf_intake import pdf_setup as _pdf_setup
from test_draft_pdf_scope_review import _save as save_pdf
from test_draft_pdf_scope_review import review_case as _review_case
from test_draft_pdf_ui import pdf_app as _pdf_app
from test_draft_scope_docx_review import _save as save_word
from test_draft_scope_docx_review import word_case as _word_case
from test_draft_scope_docx_ui import word_app as _word_app
from test_draft_scope_ui import scope_password_hash as _password_hash
from test_draft_scope_xlsx import _save as save_xlsx
from test_draft_scope_xlsx import xlsx_case as _xlsx_case
from test_shared_file_containment import postgresql_session_factory as _postgres

from classifire.models import StoredFile, User
from classifire.services import draft_work_records as work
from classifire.services.draft_scope import DraftScopeError
from classifire.services.storage import quarantine_stored_file_bytes_for_update

pdf_setup = _pdf_setup
pdf_app = _pdf_app
review_case = _review_case
word_app = _word_app
word_case = _word_case
xlsx_case = _xlsx_case
scope_password_hash = _password_hash
postgresql_session_factory = _postgres


@pytest.mark.parametrize("kind", ["pdf", "docx", "xlsx"])
def test_exact_original_source_archive_and_quarantine_recheck(request, kind, tmp_path):
    fixture, save_scope = {
        "pdf": ("review_case", save_pdf),
        "docx": ("word_case", save_word),
        "xlsx": ("xlsx_case", save_xlsx),
    }[kind]
    x = request.getfixturevalue(fixture)
    with x.factory() as db:
        scope = save_scope(db, x)
        db.commit()
        actor = db.get(User, x.ids[0])
        payload = {
            "record_id": str(uuid4()),
            "expected_revision": 0,
            "scope_revision": scope["revision"],
            "opening_id": x.payload["openings"][0]["id"],
            "service_id": x.payload["services"][0]["id"],
            "note": "Synthetic reported work; source context only.",
            "evidence_indices": [],
        }
        context = work.choices(db, actor, x.ids[2], payload, settings=x.settings)
        payload["evidence_indices"] = [
            ref["index"] for ref in context["refs"] if ref["availability"] == "verified"
        ]
        assert payload["evidence_indices"]
        preview = work.preview(db, actor, x.ids[2], payload, settings=x.settings)
        saved = work.save(db, actor, x.ids[2], payload, preview["sha256"], settings=x.settings)
        db.commit()
        raw = work.report_archive(db, actor, x.ids[2], payload["record_id"], 1, settings=x.settings)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            assert archive.testzip() is None
            originals = [name for name in archive.namelist() if name.startswith("evidence/")]
            assert len(originals) == 1
            original = archive.read(originals[0])
            ref = saved["dependencies"]["evidence"][0]["reference"]
            assert hashlib.sha256(original).hexdigest() == ref["source_sha256"]
            assert len(original) == ref["source_size_bytes"]
            if kind == "docx":
                assert original == x.content
            assert json.loads(archive.read("work-record.json")) == saved
        (tmp_path / f"work-original-{kind}.zip").write_bytes(raw)
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        assert (
            work.report_archive(
                db,
                actor,
                x.ids[2],
                payload["record_id"],
                1,
                settings=x.settings,
            )
            == raw
        )
        next_payload = payload | {"expected_revision": 1, "note": "Pending amendment"}
        pending = work.preview(db, actor, x.ids[2], next_payload, settings=x.settings)
        quarantine_stored_file_bytes_for_update(
            db,
            stored_file_id=db.scalar(
                select(StoredFile.id).where(StoredFile.sha256 == ref["source_sha256"])
            ),
            observed_sha256=ref["source_sha256"],
            observed_size_bytes=ref["source_size_bytes"],
        )
        db.commit()
        with pytest.raises(DraftScopeError, match="EVIDENCE_UNAVAILABLE"):
            work.save(db, actor, x.ids[2], next_payload, pending["sha256"], settings=x.settings)
        with pytest.raises(DraftScopeError, match="EVIDENCE_UNAVAILABLE"):
            work.report_archive(
                db,
                actor,
                x.ids[2],
                payload["record_id"],
                1,
                settings=x.settings,
            )


def test_concurrent_confirmations_append_only_once(word_case):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy import func

    from classifire.models import DraftWorkRecordRevision

    x = word_case
    with x.factory() as db:
        scope = save_word(db, x)
        db.commit()
    payload = {
        "record_id": str(uuid4()),
        "expected_revision": 0,
        "scope_revision": scope["revision"],
        "opening_id": x.payload["openings"][1]["id"],
        "note": "One synthetic work assertion",
    }
    barrier = Barrier(2)

    def confirm():
        with x.factory() as db:
            actor = db.get(User, x.ids[0])
            proposed = work.preview(db, actor, x.ids[2], payload, settings=x.settings)
            db.commit()
            barrier.wait(timeout=15)
            try:
                saved = work.save(
                    db, actor, x.ids[2], payload, proposed["sha256"], settings=x.settings
                )
                db.commit()
                return saved["revision"]
            except DraftScopeError as exc:
                db.rollback()
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(confirm) for _ in range(2)]
        results = [future.result(timeout=30) for future in futures]
    assert results.count(1) == 1
    assert results.count("WORK_RECORD_REVISION_CONFLICT") == 1
    with x.factory() as db:
        assert db.scalar(select(func.count()).select_from(DraftWorkRecordRevision)) == 1
