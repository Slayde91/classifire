from __future__ import annotations

import copy
import hashlib

import pytest
from sqlalchemy import func, select, update
from test_draft_pdf_intake import pdf_setup as _pdf_setup
from test_draft_pdf_intake import prepared
from test_shared_file_containment import postgresql_session_factory as _postgres

from classifire.models import (
    AuditEvent,
    DraftPdfSuggestion,
    DraftScopeRevision,
    Estimate,
    EstimateLine,
    Opening,
    Service,
    StoredFile,
    User,
)
from classifire.physical_models import Defect, EvidenceSource, PhysicalModelLock, ServiceOpeningLink
from classifire.services import draft_pdf_intake as intake
from classifire.services import draft_pdf_suggestions as suggestions
from classifire.services import draft_scope as scopes
from classifire.services.draft_pdf_suggestion_contract import SuggestionResult
from classifire.services.draft_scope_evidence import reference_status

pdf_setup = _pdf_setup
postgresql_session_factory = _postgres


def output():
    claim = {
        "basis": "page_text",
        "quote": "Shared opening",
        "rationale": "Report text describes a shared opening; interpretation requires review.",
    }
    return {
        "defects": [dict(claim, key="d1", label="Proposed D-01", description="Unsealed services")],
        "openings": [
            dict(
                claim,
                key="o1",
                label="Possible shared opening",
                defect_key="d1",
                plane="unknown",
                substrate="",
            )
        ],
        "services": [
            dict(
                claim,
                key="s1",
                label="Possible pipe group",
                opening_keys=["o1"],
                service_type="Unverified pipe",
            )
        ],
        "observations": [
            dict(
                claim,
                key="q1",
                text="How many services are present? Dimensions and quantities remain unresolved.",
            )
        ],
    }


class ScriptedPort:
    def __init__(self, hook=None, value=None):
        self.calls = []
        self.hook = hook
        self.value = output() if value is None else value

    def complete(self, request):
        self.calls.append(request)
        assert request.page_png.startswith(b"\x89PNG")
        assert "Shared opening" in request.page_text
        if self.hook:
            self.hook()
        return SuggestionResult(
            provider="scripted",
            model="synthetic-fixture-v1",
            response_sha256=hashlib.sha256(scopes._json(self.value)).hexdigest(),
            output=copy.deepcopy(self.value),
        )


@pytest.fixture
def case(pdf_setup):
    x = pdf_setup
    with x.factory() as db:
        actor, source = prepared(db, x)
        x.source_id = source.id
        x.document_hash = source.document_sha256
        x.original = scopes.revision_bytes(db, actor, x.ids[2])
    return x


def generate(db, x, port=None, **changes):
    values = dict(
        draft_id=x.ids[2],
        source_id=x.source_id,
        expected_revision=1,
        page_number=1,
        expected_document_hash=x.document_hash,
    )
    values.update(changes)
    return suggestions.generate(
        db,
        db.get(User, x.ids[0]),
        **values,
        settings=x.settings,
        port=ScriptedPort() if port is None else port,
    )


def read(db, x, identity):
    return suggestions.read_suggestion(
        db, db.get(User, x.ids[0]), x.ids[2], identity, settings=x.settings
    )


def preview(db, x, identity, value=None, **changes):
    value = read(db, x, identity) if value is None else value
    values = dict(expected_revision=1, payload=value["payload"], targets=value["targets"])
    values.update(changes)
    return suggestions.preview_suggestion(
        db, db.get(User, x.ids[0]), x.ids[2], identity, **values, settings=x.settings
    )


def save(db, x, identity, value=None, review=None, **changes):
    value = read(db, x, identity) if value is None else value
    review = preview(db, x, identity, value) if review is None else review
    values = dict(
        expected_revision=1,
        payload=value["payload"],
        targets=value["targets"],
        expected_review_hash=review["review_sha256"],
    )
    values.update(changes)
    return suggestions.save_suggestion(
        db, db.get(User, x.ids[0]), x.ids[2], identity, **values, settings=x.settings
    )


def canonical_counts(db):
    return {
        model.__name__: db.scalar(select(func.count()).select_from(model))
        for model in (
            Estimate,
            EstimateLine,
            Defect,
            Opening,
            Service,
            EvidenceSource,
            ServiceOpeningLink,
            PhysicalModelLock,
        )
    }


def test_generate_preview_edit_save_reopen_and_preserve_original(case):
    x = case
    port = ScriptedPort()
    with x.factory() as db:
        row = generate(db, x, port)
        identity = row.id
        db.commit()
        assert generate(db, x, port).id == identity
        assert len(port.calls) == 1
        assert scopes.revision_bytes(db, db.get(User, x.ids[0]), x.ids[2]) == x.original
        assert set(canonical_counts(db).values()) == {0}
        value = read(db, x, identity)
        assert value["payload"]["services"][0]["quantity"] is None
        assert value["payload"]["openings"][0]["width_mm"] is None
        assert len(value["targets"]) == 4
        assert value["payload"]["services"][0]["opening_ids"] == [
            value["payload"]["openings"][0]["id"]
        ]
        value["payload"]["services"][0]["label"] = "Human corrected pipe group"
        review = preview(db, x, identity, value)
        assert db.scalar(select(func.count()).select_from(DraftScopeRevision)) == 1
        assert db.scalar(select(func.count()).select_from(DraftPdfSuggestion)) == 1
        result = save(db, x, identity, value, review)
        assert result["revision"] == 2 and result["schema_version"] == "CLASSIFIRE-DRAFT-SCOPE-v6"
        assert len(result["evidence_refs"]) == 4
        ref = next(ref for ref in result["evidence_refs"] if ref["target_kind"] == "service")
        assert ref["suggestion"]["proposed_item"]["label"] == "Possible pipe group"
        assert result["content"]["services"][0]["label"] == "Human corrected pipe group"
        assert scopes.validate_portable_artifact(scopes._json(result)) == result
        original_revision = scopes._json(result)
        original_proposal = row.proposal_json
        db.commit()
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        reopened = read(db, x, identity)
        assert reopened["status"] == "applied" and reopened["applied_revision"] == 2
        assert scopes.revision_bytes(db, actor, x.ids[2], 2) == original_revision
        assert db.get(DraftPdfSuggestion, identity).proposal_json == original_proposal
        assert (
            suggestions.list_suggestions(db, actor, x.ids[2], x.source_id, settings=x.settings)[0][
                "id"
            ]
            == identity
        )
        with pytest.raises(scopes.DraftScopeError, match="NOT_PENDING"):
            save(db, x, identity)
        assert set(canonical_counts(db).values()) == {0}


def test_partial_rejection_removes_proposed_observation_but_preserves_graph(case):
    x = case
    with x.factory() as db:
        row = generate(db, x)
        value = read(db, x, row.id)
        value["payload"]["observations"] = []
        value["targets"] = [
            target for target in value["targets"] if target["target_kind"] != "observation"
        ]
        saved = save(db, x, row.id, value)
        assert len(saved["evidence_refs"]) == 3
        assert saved["content"]["observations"] == []
        assert len(read(db, x, row.id)["items"]) == 4


@pytest.mark.parametrize(
    "change", ["unchecked", "forged_target", "duplicate", "wrong_revision", "changed_preview"]
)
def test_review_cannot_bypass_exact_targets_or_revision(case, change):
    x = case
    with x.factory() as db:
        row = generate(db, x)
        value = read(db, x, row.id)
        review = preview(db, x, row.id, value)
        if change == "unchecked":
            value["targets"].pop()
        elif change == "forged_target":
            value["targets"][0]["target_id"] = x.ids[1]
        elif change == "duplicate":
            value["targets"].append(value["targets"][0])
        elif change == "changed_preview":
            value["payload"]["services"][0]["label"] = "Edited after preview"
        with pytest.raises(scopes.DraftScopeError):
            save(
                db,
                x,
                row.id,
                value,
                review,
                **({"expected_revision": 2} if change == "wrong_revision" else {}),
            )
        assert db.scalar(select(func.count()).select_from(DraftScopeRevision)) == 1
        assert db.get(DraftPdfSuggestion, row.id).status == "pending"


@pytest.mark.parametrize(
    "change", ["foreign", "inactive", "quarantine", "rescan", "stale", "corrupt"]
)
def test_source_owner_integrity_and_stale_refusals(case, change):
    x = case
    with x.factory() as db:
        row = generate(db, x)
        db.commit()
        identity = row.id
        value = read(db, x, identity)
        actor = db.get(User, x.ids[0])
        if change == "foreign":
            with pytest.raises(scopes.DraftScopeError):
                suggestions.read_suggestion(
                    db, db.get(User, x.ids[1]), x.ids[2], identity, settings=x.settings
                )
            return
        if change == "inactive":
            db.execute(update(User).where(User.id == actor.id).values(is_active=False))
        elif change == "quarantine":
            db.execute(update(StoredFile).values(malware_scan_status="malware_detected"))
        elif change == "rescan":
            intake.scan_source(db, actor, x.ids[2], x.source_id, settings=x.settings)
        elif change == "stale":
            scopes.save_revision(db, actor, x.ids[2], 1, value["payload"])
        else:
            db.execute(
                update(DraftPdfSuggestion)
                .where(DraftPdfSuggestion.id == identity)
                .values(proposal_json="{}")
            )
        db.commit()
        with pytest.raises(scopes.DraftScopeError):
            preview(db, x, identity, value)
        assert db.get(DraftPdfSuggestion, identity).status == "pending"


def test_generation_rechecks_permissions_after_provider(case):
    x = case
    with x.factory() as db:
        port = ScriptedPort(
            hook=lambda: db.execute(update(User).where(User.id == x.ids[0]).values(is_active=False))
        )
        with pytest.raises(scopes.DraftScopeError, match="PERMISSION"):
            generate(db, x, port)
        assert db.scalar(select(func.count()).select_from(DraftPdfSuggestion)) == 0
        assert db.scalar(select(func.count()).select_from(DraftScopeRevision)) == 1


@pytest.mark.parametrize("change", ["quote", "quantity", "provider", "hash"])
def test_untrusted_port_output_is_revalidated(case, change):
    x = case
    with x.factory() as db:
        port = ScriptedPort()
        if change == "quote":
            port.value["services"][0]["quote"] = "This quote never existed"
        elif change == "quantity":
            port.value["services"][0]["quantity"] = "1"
        else:
            original = port.complete

            def changed(request):
                result = original(request)
                return SuggestionResult(
                    provider="unapproved" if change == "provider" else result.provider,
                    model=result.model,
                    response_sha256="bad" if change == "hash" else result.response_sha256,
                    output=result.output,
                )

            port.complete = changed
        with pytest.raises(scopes.DraftScopeError):
            generate(db, x, port)
        assert db.scalar(select(func.count()).select_from(DraftPdfSuggestion)) == 0


def test_explicit_reject_keeps_scope_and_proposal_bytes(case):
    x = case
    with x.factory() as db:
        row = generate(db, x)
        raw = row.proposal_json
        suggestions.reject_suggestion(
            db, db.get(User, x.ids[0]), x.ids[2], row.id, settings=x.settings
        )
        assert read(db, x, row.id)["status"] == "rejected"
        assert row.proposal_json == raw
        assert scopes.revision_bytes(db, db.get(User, x.ids[0]), x.ids[2]) == x.original
        with pytest.raises(scopes.DraftScopeError, match="NOT_PENDING"):
            preview(db, x, row.id)


def test_apply_audit_failure_rolls_back_entire_savepoint(case, monkeypatch):
    x = case
    with x.factory() as db:
        row = generate(db, x)
        db.commit()
        identity = row.id
        value = read(db, x, identity)
        review = preview(db, x, identity, value)

        def fail(*args, **kwargs):
            raise RuntimeError("synthetic audit failure")

        with monkeypatch.context() as patch:
            patch.setattr(suggestions, "record_audit", fail)
            with pytest.raises(RuntimeError, match="synthetic audit"):
                save(db, x, identity, value, review)
        # No outer rollback: prove the service's own nested atomic operation restores both.
        assert db.scalar(select(func.count()).select_from(DraftScopeRevision)) == 1
        assert db.get(DraftPdfSuggestion, identity, populate_existing=True).status == "pending"
        assert scopes.revision_bytes(db, db.get(User, x.ids[0]), x.ids[2]) == x.original
        assert not db.scalars(
            select(AuditEvent).where(AuditEvent.action == "draft_pdf_suggestion.apply")
        ).all()


def test_optional_disabled_does_not_block_manual_pdf_review(case):
    x = case
    assert suggestions.availability(x.settings)["enabled"] is False
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        with pytest.raises(scopes.DraftScopeError, match="UNAVAILABLE"):
            suggestions.generate(
                db, actor, x.ids[2], x.source_id, 1, 1, x.document_hash, settings=x.settings
            )
        saved = intake.review_page(
            db,
            actor,
            x.ids[2],
            x.source_id,
            1,
            1,
            "Human observation",
            "Unresolved",
            x.document_hash,
            settings=x.settings,
        )
        assert saved["schema_version"] == "CLASSIFIRE-DRAFT-SCOPE-v3"
        assert "suggestion" not in saved["evidence_refs"][0]
        assert "review" in reference_status(saved["evidence_refs"][0], saved["content"]).lower()
