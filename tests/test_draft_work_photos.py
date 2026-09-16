from __future__ import annotations

import hashlib
import io
import json
import zipfile
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import select
from test_draft_pdf_intake import pdf_setup as _pdf_setup
from test_draft_scope import sample_payload
from test_shared_file_containment import postgresql_session_factory as _postgres

from classifire.models import StoredFile, User
from classifire.services import draft_scope as scopes
from classifire.services import draft_work_photos as photos
from classifire.services import draft_work_records as work
from classifire.services.draft_scope import DraftScopeError
from classifire.services.storage import quarantine_stored_file_bytes_for_update

pdf_setup = _pdf_setup
postgresql_session_factory = _postgres


def photo_bytes(image_format: str = "PNG") -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (9, 7), color=(192, 51, 35)).save(output, format=image_format)
    return output.getvalue()


@pytest.fixture
def photo_case(pdf_setup):
    x = pdf_setup
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        scope = scopes.save_revision(db, actor, x.ids[2], 1, sample_payload())
        db.commit()
        x.scope_revision = scope["revision"]
    return x


@pytest.mark.parametrize(
    ("filename", "image_format", "media_type"),
    [("site.png", "PNG", "image/png"), ("site.jpeg", "JPEG", "image/jpeg")],
)
def test_photo_scan_work_record_restart_and_exact_export(
    photo_case, filename, image_format, media_type
):
    x = photo_case
    raw = photo_bytes(image_format)
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        source = photos.retain_photo(
            db, actor, x.ids[2], filename, raw, settings=x.settings
        )
        db.commit()
        assert photos.source_info(db, actor, x.ids[2], source.id)["status"] == "pending"
        with pytest.raises(DraftScopeError, match="SOURCE_NOT_READY"):
            photos.read_photo(db, actor, x.ids[2], source.id, settings=x.settings)
        assert photos.scan_source(
            db, actor, x.ids[2], source.id, settings=x.settings
        ) == {"status": "clean", "processing_error": None}
        db.commit()
        document, exact = photos.read_photo(
            db, actor, x.ids[2], source.id, settings=x.settings
        )
        assert exact.content == raw
        assert document["manifest"] == {
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "source_size_bytes": len(raw),
            "media_type": media_type,
            "width_px": 9,
            "height_px": 7,
        }
        payload = {
            "record_id": str(uuid4()),
            "expected_revision": 0,
            "scope_revision": x.scope_revision,
            "opening_id": sample_payload()["openings"][0]["id"],
            "service_id": sample_payload()["services"][1]["id"],
            "note": "Synthetic reported work; direct photo remains unverified.",
            "photo_source_ids": [source.id],
        }
        preview = work.preview(db, actor, x.ids[2], payload, settings=x.settings)
        assert preview["dependencies"]["photos"][0]["source_sha256"] == exact.sha256
        saved = work.save(
            db, actor, x.ids[2], payload, preview["sha256"], settings=x.settings
        )
        assert saved["schema_version"] == work.SCHEMA
        db.commit()
        archive = work.report_archive(
            db, actor, x.ids[2], payload["record_id"], 1, settings=x.settings
        )
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        assert work.read(
            db, actor, x.ids[2], payload["record_id"], 1, settings=x.settings
        )["record"] == saved
        assert work.report_archive(
            db, actor, x.ids[2], payload["record_id"], 1, settings=x.settings
        ) == archive
        with zipfile.ZipFile(io.BytesIO(archive)) as package:
            names = [name for name in package.namelist() if name.startswith("evidence/photos/")]
            assert len(names) == 1 and package.read(names[0]) == raw
            assert "Selected direct photos" in package.read("report.html").decode("utf-8")
            assert json.loads(package.read("manifest.json"))["schema_version"] == work.SCHEMA
        stored_id = db.scalar(select(StoredFile.id).where(StoredFile.sha256 == exact.sha256))
        quarantine_stored_file_bytes_for_update(
            db,
            stored_file_id=stored_id,
            observed_sha256=exact.sha256,
            observed_size_bytes=exact.size_bytes,
        )
        db.commit()
        with pytest.raises(DraftScopeError, match="WORK_RECORD_PHOTO_UNAVAILABLE"):
            work.read(db, actor, x.ids[2], payload["record_id"], 1, settings=x.settings)


def test_photo_input_foreign_owner_conflict_and_corrupt_decode_fail_closed(photo_case):
    x = photo_case
    raw = photo_bytes()
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        source = photos.retain_photo(db, actor, x.ids[2], "site.png", raw, settings=x.settings)
        db.commit()
        with pytest.raises(DraftScopeError, match="DRAFT_NOT_FOUND"):
            photos.source_info(db, db.get(User, x.ids[1]), x.ids[2], source.id)
        other = scopes.create_draft_project(db, actor, "PHOTO-OTHER", "Other synthetic Draft")
        db.commit()
        with pytest.raises(DraftScopeError, match="PHOTO_UPLOAD_CONFLICT"):
            photos.retain_photo(db, actor, other.id, "same.png", raw, settings=x.settings)
        with pytest.raises(DraftScopeError, match="PHOTO_UPLOAD_INVALID"):
            photos.retain_photo(db, actor, x.ids[2], "wrong.jpg", raw, settings=x.settings)
        corrupt = photos.retain_photo(
            db, actor, x.ids[2], "corrupt.jpg", b"\xff\xd8\xffnot-an-image", settings=x.settings
        )
        db.commit()
        result = photos.scan_source(db, actor, x.ids[2], corrupt.id, settings=x.settings)
        assert result == {"status": "clean", "processing_error": "PHOTO_PROCESSING_FAILED"}
        db.commit()
        assert photos.source_info(db, actor, x.ids[2], corrupt.id)["ready"] is False
        with pytest.raises(DraftScopeError, match="SOURCE_NOT_READY"):
            photos.read_photo(db, actor, x.ids[2], corrupt.id, settings=x.settings)
