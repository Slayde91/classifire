from __future__ import annotations

import copy
import hashlib
import json
import traceback

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select, update
from test_draft_pdf_suggestions import (
    ScriptedPort,
    canonical_counts,
    generate,
    preview,
    read,
)
from test_draft_pdf_suggestions import case as _case
from test_draft_pdf_suggestions import pdf_setup as _pdf_setup
from test_draft_pdf_suggestions import postgresql_session_factory as _postgres

from classifire.models import (
    AuditEvent,
    DraftPdfSuggestion,
    DraftScopeRevision,
    StoredFile,
    User,
    new_id,
)
from classifire.security import has_permission
from classifire.services import draft_pdf_intake as intake
from classifire.services import draft_pdf_suggestions as suggestions
from classifire.services import draft_scope as scopes
from classifire.services.draft_pdf_suggestion_contract import SuggestionResult

case = _case
pdf_setup = _pdf_setup
postgresql_session_factory = _postgres


def _no_proposal_writes(db, *, revisions=1):
    assert db.scalar(select(func.count()).select_from(DraftPdfSuggestion)) == 0
    assert db.scalar(select(func.count()).select_from(DraftScopeRevision)) == revisions
    assert not db.scalars(
        select(AuditEvent).where(AuditEvent.action.like("draft_pdf_suggestion.%"))
    ).all()
    assert set(canonical_counts(db).values()) == {0}


def _reseal(db, row, document):
    raw = scopes._json(document)
    db.execute(
        update(DraftPdfSuggestion)
        .where(DraftPdfSuggestion.id == row.id)
        .values(proposal_json=raw.decode(), proposal_sha256=hashlib.sha256(raw).hexdigest())
    )


def test_empty_results_require_metadata_and_can_be_retained_then_rejected(case):
    x = case
    empty = dict(defects=[], openings=[], services=[], observations=[])
    with x.factory() as db:
        for field, invalid in (
            ("model", ""),
            ("model", "m" * 101),
            ("response_sha256", "bad"),
            ("provider", "other"),
        ):
            port = ScriptedPort(value=empty)
            original = port.complete

            def changed(request, original=original, field=field, invalid=invalid):
                result = original(request)
                metadata = dict(
                    provider=result.provider,
                    model=result.model,
                    response_sha256=result.response_sha256,
                    output=result.output,
                )
                metadata[field] = invalid
                return SuggestionResult(**metadata)

            port.complete = changed
            with pytest.raises(scopes.DraftScopeError, match="PDF_SUGGESTION_FAILED"):
                generate(db, x, port)
            assert len(port.calls) == 1
            _no_proposal_writes(db)
        port = ScriptedPort(value=empty)
        row = generate(db, x, port)
        original_json = row.proposal_json
        assert read(db, x, row.id)["items"] == []
        assert read(db, x, row.id)["targets"] == []
        with pytest.raises(scopes.DraftScopeError, match="PDF_REVIEW_TARGETS_INVALID"):
            preview(db, x, row.id)
        suggestions.reject_suggestion(
            db, db.get(User, x.ids[0]), x.ids[2], row.id, settings=x.settings
        )
        assert read(db, x, row.id)["status"] == "rejected"
        assert row.proposal_json == original_json
        assert scopes.revision_bytes(db, db.get(User, x.ids[0]), x.ids[2]) == x.original
        assert db.scalar(select(func.count()).select_from(DraftScopeRevision)) == 1
        assert set(canonical_counts(db).values()) == {0}


def test_invalid_live_configuration_returns_stable_error_without_provider_call(case, monkeypatch):
    x = case
    calls = []

    def unexpected(*args, **kwargs):
        calls.append(True)
        raise AssertionError("Provider must not run")

    from classifire.services.draft_pdf_suggestion_transport import OpenAIDraftPdfSuggestionPort

    monkeypatch.setattr(OpenAIDraftPdfSuggestionPort, "complete", unexpected)
    for model, key in (
        (None, None),
        ("configured-model", None),
        ("https://elsewhere.invalid", SecretStr("synthetic-key")),
        ("configured-model", SecretStr("two words")),
    ):
        settings = x.settings.model_copy(
            update=dict(
                draft_pdf_suggestions_enabled=True,
                draft_pdf_suggestions_model=model,
                draft_pdf_suggestions_api_key=key,
            )
        )
        with x.factory() as db:
            with pytest.raises(
                scopes.DraftScopeError, match="PDF_SUGGESTIONS_UNAVAILABLE"
            ) as caught:
                suggestions.generate(
                    db,
                    db.get(User, x.ids[0]),
                    x.ids[2],
                    x.source_id,
                    1,
                    1,
                    x.document_hash,
                    settings=settings,
                )
            assert "two words" not in "".join(traceback.format_exception(caught.value))
            _no_proposal_writes(db)
    assert calls == []


@pytest.mark.parametrize("change", ["write_revoked", "quarantine", "revision"])
def test_render_to_provider_boundary_rechecks_permissions_source_and_revision(
    case, monkeypatch, change
):
    x = case
    original = intake.page_preview
    port = ScriptedPort()
    with x.factory() as db:

        def changed(*args, **kwargs):
            png = original(*args, **kwargs)
            if change == "write_revoked":
                db.execute(update(User).where(User.id == x.ids[0]).values(role="read_only"))
                actor = db.get(User, x.ids[0], populate_existing=True)
                assert has_permission(actor, "project:read")
                assert not has_permission(actor, "project:write")
            elif change == "quarantine":
                db.execute(update(StoredFile).values(malware_scan_status="malware_detected"))
            else:
                actor = db.get(User, x.ids[0])
                current = scopes.read_revision(db, actor, x.ids[2])
                scopes.save_revision(db, actor, x.ids[2], 1, current["content"])
            return png

        monkeypatch.setattr(intake, "page_preview", changed)
        with pytest.raises(scopes.DraftScopeError):
            generate(db, x, port)
        assert port.calls == []
        _no_proposal_writes(db, revisions=2 if change == "revision" else 1)
        assert scopes.revision_bytes(db, db.get(User, x.ids[0]), x.ids[2], 1) == x.original


def test_resealed_proposal_still_requires_consistent_request_source_and_exact_quotes(case):
    x = case
    with x.factory() as db:
        row = generate(db, x)
        original = json.loads(row.proposal_json)
        for change in ("request_source", "source_page", "request_text", "quote", "image_quote"):
            changed = copy.deepcopy(original)
            if change == "request_source":
                changed["request_binding"]["source"]["page"] = 2
            elif change == "source_page":
                changed["source"]["page"] = 2
                changed["request_binding"]["source"] = copy.deepcopy(changed["source"])
            elif change == "request_text":
                changed["request_binding"]["text_sha256"] = "b" * 64
            elif change == "quote":
                changed["items"][0]["quote"] = "private text absent from source"
            else:
                changed["items"][0]["basis"] = "page_image"
            changed["input_sha256"] = suggestions._digest(changed["request_binding"])
            _reseal(db, row, changed)
            with pytest.raises(scopes.DraftScopeError):
                read(db, x, row.id)
            assert db.scalar(select(func.count()).select_from(DraftScopeRevision)) == 1
        _reseal(db, row, original)
        assert read(db, x, row.id)["status"] == "pending"
        assert scopes.revision_bytes(db, db.get(User, x.ids[0]), x.ids[2]) == x.original


def test_empty_retained_record_metadata_is_checked_even_after_resealing(case):
    x = case
    with x.factory() as db:
        row = generate(
            db, x, ScriptedPort(value=dict(defects=[], openings=[], services=[], observations=[]))
        )
        original = json.loads(row.proposal_json)
        for field, invalid in (
            ("model", ""),
            ("response_sha256", "invalid"),
            ("prompt_version", "future-version"),
            ("generated_at", "2026-09-06T00:00:00"),
        ):
            changed = copy.deepcopy(original)
            changed[field] = invalid
            _reseal(db, row, changed)
            with pytest.raises(scopes.DraftScopeError, match="PDF_SUGGESTION_INTEGRITY_FAILED"):
                read(db, x, row.id)
        _reseal(db, row, original)
        assert read(db, x, row.id)["items"] == []
        assert db.scalar(select(func.count()).select_from(DraftScopeRevision)) == 1


def test_source_bearing_provider_and_integrity_errors_are_not_chained(case):
    x = case
    with x.factory() as db:

        def fail():
            raise ValueError("private provider source content")

        with pytest.raises(scopes.DraftScopeError, match="PDF_SUGGESTION_FAILED") as caught:
            generate(db, x, ScriptedPort(hook=fail))
        assert "private provider source content" not in "".join(
            traceback.format_exception(caught.value)
        )
        _no_proposal_writes(db)
        row = generate(db, x)
        changed = json.loads(row.proposal_json)
        changed["items"][0]["proposed_item"]["description"] = ["private malformed item content"]
        _reseal(db, row, changed)
        with pytest.raises(
            scopes.DraftScopeError, match="PDF_SUGGESTION_INTEGRITY_FAILED"
        ) as caught:
            read(db, x, row.id)
        assert "private malformed item content" not in "".join(
            traceback.format_exception(caught.value)
        )
        assert db.scalar(select(func.count()).select_from(DraftScopeRevision)) == 1


def test_retained_quota_blocks_before_another_provider_call(case):
    x = case
    with x.factory() as db:
        row = generate(db, x)
        original = json.loads(row.proposal_json)
        for _ in range(suggestions.MAX_SUGGESTIONS - 1):
            document = copy.deepcopy(original)
            document["id"] = new_id()
            raw = scopes._json(document)
            db.add(
                DraftPdfSuggestion(
                    id=document["id"],
                    draft_scope_id=x.ids[2],
                    source_id=x.source_id,
                    created_by_id=x.ids[0],
                    base_revision=1,
                    proposal_json=raw.decode(),
                    proposal_sha256=hashlib.sha256(raw).hexdigest(),
                    status="rejected",
                )
            )
        db.flush()
        port = ScriptedPort()
        with pytest.raises(scopes.DraftScopeError, match="PDF_SUGGESTION_LIMIT"):
            generate(db, x, port)
        assert port.calls == []
        assert (
            db.scalar(select(func.count()).select_from(DraftPdfSuggestion))
            == suggestions.MAX_SUGGESTIONS
        )
        assert db.scalar(select(func.count()).select_from(DraftScopeRevision)) == 1
        assert scopes.revision_bytes(db, db.get(User, x.ids[0]), x.ids[2]) == x.original
