from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import func, select
from test_draft_scope_ui import (
    ScopeApplication,
    _assert_no_canonical_scope,
    _create,
    _csrf,
    _edit,
    _login,
    _payload,
    _uid,
)
from test_draft_scope_ui import scope_app as _scope_app
from test_draft_scope_ui import scope_password_hash as _scope_password_hash

from classifire.draft_system_match_ui import router as candidate_router
from classifire.models import (
    AuditEvent,
    DraftSystemMatch,
    DraftSystemMatchRevision,
    LibraryRelease,
    StoredFile,
    TechnicalDocument,
    TechnicalVariant,
    User,
)
from classifire.technical_admin import router as technical_router
from scripts.draft_system_match_demo_fixture import FIXTURE_NOTES, seed_demo_library

scope_app = _scope_app
scope_password_hash = _scope_password_hash


@dataclass(frozen=True)
class CandidateApplication:
    scope: ScopeApplication
    storage: Path
    release_id: str


@pytest.fixture
def candidate_app(
    scope_app: ScopeApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> CandidateApplication:
    storage = (tmp_path / "synthetic-library").resolve()
    with scope_app.factory() as db:
        actor = db.get(User, scope_app.users["admin"])
        assert actor is not None
        release = seed_demo_library(db, storage, actor)
        db.commit()
        release_id = release.id
    scope_app.app.include_router(candidate_router)
    scope_app.app.include_router(technical_router)
    monkeypatch.setattr(
        "classifire.draft_system_match_ui.get_settings",
        lambda: SimpleNamespace(storage_root=storage),
    )
    return CandidateApplication(scope_app, storage, release_id)


def _prepare(client: TestClient) -> str:
    path = _create(client, "CANDIDATE-SCOPE")
    assert _edit(client, path, _payload()).status_code == 303
    return path


def _create_form(client: TestClient, path: str, release_id: str) -> dict[str, str]:
    picker = client.get(f"{path}/system-matches?scope_revision=2")
    assert picker.status_code == 200, picker.text
    return {
        "csrf_token": _csrf(picker.text),
        "scope_revision": "2",
        "release_id": release_id,
        "opening_id": _uid(2),
        "service_id": _uid(6),
    }


def _find(client: TestClient, path: str, release_id: str) -> str:
    response = client.post(
        f"{path}/system-matches",
        data=_create_form(client, path, release_id),
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    detail = response.headers["location"]
    assert re.fullmatch(rf"{re.escape(path)}/system-matches/[0-9a-f-]{{36}}", detail)
    return detail


def _review_form(client: TestClient, detail: str, envelope: dict[str, Any]) -> dict[str, str]:
    page = client.get(detail)
    assert page.status_code == 200
    form = {"csrf_token": _csrf(page.text), "expected_revision": str(envelope["revision"])}
    for index, candidate in enumerate(envelope["candidates"]):
        form[f"candidate_{candidate['candidate_id']}"] = "keep" if index == 0 else "reject"
        form[f"notes_{candidate['candidate_id']}"] = (
            "Retain for expert review" if index == 0 else "Alternative not selected"
        )
    return form


def _counts(app: CandidateApplication) -> tuple[int | None, ...]:
    with app.scope.factory() as db:
        return tuple(
            db.scalar(select(func.count()).select_from(model))
            for model in (DraftSystemMatch, DraftSystemMatchRevision, AuditEvent)
        )


def test_synthetic_library_refuses_unapproved_actor_before_file_or_record_writes(
    scope_app: ScopeApplication,
    tmp_path: Path,
) -> None:
    storage = tmp_path / "must-not-be-created"
    models = (StoredFile, TechnicalDocument, TechnicalVariant, LibraryRelease, AuditEvent)
    with scope_app.factory() as db:
        actor = db.get(User, scope_app.users["owner"])
        assert actor is not None
        before = [db.scalar(select(func.count()).select_from(model)) for model in models]
        with pytest.raises(ValueError, match="active technical approver"):
            seed_demo_library(db, storage, actor)
        assert [db.scalar(select(func.count()).select_from(model)) for model in models] == before
        assert not storage.exists()


def test_synthetic_library_has_true_pdf_locators_and_idempotent_verified_publication(
    candidate_app: CandidateApplication,
) -> None:
    app = candidate_app
    with app.scope.factory() as db:
        release = db.get(LibraryRelease, app.release_id)
        assert release is not None
        assert release.notes == FIXTURE_NOTES
        assert release.source_manifest["activated_draft_ids"] == []
        assert len(release.source_manifest["records"]) == 2
        stored = db.scalar(select(StoredFile).where(StoredFile.purpose == "technical_evidence"))
        assert stored is not None
        content = Path(stored.storage_path).read_bytes()
        assert stored.sha256 == hashlib.sha256(content).hexdigest()
        pages = PdfReader(io.BytesIO(content)).pages
        assert len(pages) == 1
        text = pages[0].extract_text()
        assert "NOT TECHNICAL APPROVAL" in text
        assert "Table 1: Synthetic retrieval fields" in text
        assert "DEMO-PIPE-CONCRETE" in text
        document = db.scalar(select(TechnicalDocument))
        assert document is not None
        assert document.metadata_json["scanner_executed"] is False
        before = db.scalar(select(func.count()).select_from(AuditEvent))
        actor = db.get(User, app.scope.users["admin"])
        assert actor is not None
        assert seed_demo_library(db, app.storage, actor).id == release.id
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == before


def test_candidate_review_creates_saves_reopens_and_downloads_exact_unapproved_revisions(
    candidate_app: CandidateApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = candidate_app

    def forbidden_downstream(*args: object, **kwargs: object) -> None:
        pytest.fail("Candidate review must not run AI, estimating or canonical writes")

    for target in (
        "classifire.services.technical.search_for_opening",
        "classifire.services.calculation.recalculate_estimate",
        "classifire.services.snapshot.build_estimate_snapshot",
        "classifire.services.initial_canonicalisation_boundary.require_admission_bound_initial_canonicalisation",
        "classifire.services.phase8_openresponses_transport.Phase8OpenResponsesTransport.invoke",
    ):
        monkeypatch.setattr(target, forbidden_downstream)
    with TestClient(app.scope.app) as client:
        _login(client)
        path = _prepare(client)
        before = _counts(app)
        picker = client.get(f"{path}/system-matches")
        assert picker.status_code == 200
        assert _counts(app) == before
        detail = _find(client, path, app.release_id)
        first = client.get(f"{detail}/download?revision=1")
        assert first.status_code == 200
        envelope = first.json()
        assert envelope["schema_version"] == "CLASSIFIRE-DRAFT-SYSTEM-MATCH-v1"
        assert envelope["state"] == "Draft"
        assert envelope["review_status"] == "unreviewed"
        assert envelope["coverage"] == "selected_target_only"
        assert envelope["scope"]["revision"] == 2
        assert envelope["release"]["id"] == app.release_id
        assert envelope["target"]["opening_id"] == _uid(2)
        assert envelope["target"]["service_id"] == _uid(6)
        assert _uid(5) in envelope["target"]["not_assessed_service_ids"]
        assert envelope["retrieval"]["inputs"]["orientation"] is None
        assert envelope["retrieval"]["missing_criteria"]
        assert len(envelope["candidates"]) == 2
        for candidate in envelope["candidates"]:
            assert candidate["source"]["verification"] == "exact_bytes"
            assert candidate["source"]["binding"]["source_locator"]["page"] == "1"
            assert candidate["comparisons"]["frl"] == "UNKNOWN"
        page = client.get(detail)
        assert page.status_code == 200
        assert "review" in page.text.lower()
        for candidate in envelope["candidates"]:
            document_id = candidate["source"]["binding"]["technical_document"]["id"]
            assert f"/technical/documents/{document_id}" in page.text
            assert client.get(f"/technical/documents/{document_id}").status_code == 200
        form = _review_form(client, detail, envelope)
        saved = client.post(f"{detail}/review", data=form, follow_redirects=False)
        assert saved.status_code == 303, saved.text
        reopened = client.get(detail)
        assert reopened.status_code == 200
        assert "Retain for expert review" in reopened.text
        second = client.get(f"{detail}/download?revision=2")
        assert second.status_code == 200
        assert second.headers["content-type"].startswith("application/json")
        assert "attachment;" in second.headers["content-disposition"]
        assert second.headers["cache-control"] == "no-store"
        assert second.headers["x-content-type-options"] == "nosniff"
        changed = second.json()
        assert changed["parent_hash"] == envelope["sha256"]
        assert changed["decisions"][0]["decision"] == "keep"
        assert changed["decisions"][1]["decision"] == "reject"
        assert changed["review_status"] == "unreviewed"
        assert changed["candidates"] == envelope["candidates"]
        assert client.get(f"{detail}/download?revision=1").content == first.content
    _assert_no_canonical_scope(app.scope.factory)


def test_stale_review_save_keeps_submitted_notes_without_overwriting_revision(
    candidate_app: CandidateApplication,
) -> None:
    app = candidate_app
    with TestClient(app.scope.app) as client:
        _login(client)
        path = _prepare(client)
        detail = _find(client, path, app.release_id)
        envelope = client.get(f"{detail}/download?revision=1").json()
        form = _review_form(client, detail, envelope)
        assert client.post(f"{detail}/review", data=form, follow_redirects=False).status_code == 303
        accepted = client.get(f"{detail}/download?revision=2").content
        first_id = envelope["candidates"][0]["candidate_id"]
        form[f"notes_{first_id}"] = "Unsaved old-tab review notes"
        before = _counts(app)
        refused = client.post(f"{detail}/review", data=form, follow_redirects=False)
        assert refused.status_code == 409
        assert "Unsaved old-tab review notes" in refused.text
        assert _counts(app) == before
        assert client.get(f"{detail}/download?revision=2").content == accepted
        assert client.get(f"{detail}/download?revision=3").status_code == 404


@pytest.mark.parametrize("change", ["scope", "release", "scan", "bytes", "fields"])
def test_changed_dependency_is_visible_while_historical_review_bytes_remain_exact(
    candidate_app: CandidateApplication,
    change: str,
) -> None:
    app = candidate_app
    with TestClient(app.scope.app) as client:
        _login(client)
        path = _prepare(client)
        detail = _find(client, path, app.release_id)
        original = client.get(f"{detail}/download?revision=1").content
        assert "<strong>Out of date.</strong>" not in client.get(detail).text
        if change == "scope":
            assert (
                _edit(
                    client, path, {"assumptions": ["Later Scope replacement"]}, revision=2
                ).status_code
                == 303
            )
        else:
            with app.scope.factory() as db:
                if change == "release":
                    release = db.get(LibraryRelease, app.release_id)
                    release.status = "superseded"
                elif change == "fields":
                    variant = db.scalar(select(TechnicalVariant))
                    variant.substrate_type = "Changed after review"
                else:
                    stored = db.scalar(
                        select(StoredFile).where(StoredFile.purpose == "technical_evidence")
                    )
                    if change == "scan":
                        stored.malware_scan_status = "malware_detected"
                    else:
                        Path(stored.storage_path).write_bytes(b"changed retained source")
                db.commit()
        before = _counts(app)
        page = client.get(detail)
        assert page.status_code == 200, page.text
        assert "<strong>Out of date.</strong>" in page.text
        assert {
            "scope": "Scope changed",
            "release": "Release no longer active",
            "scan": "Source authority changed",
            "bytes": "Source bytes unavailable or changed",
            "fields": "Candidate changed",
        }[change] in page.text
        assert _counts(app) == before
        assert client.get(f"{detail}/download?revision=1").content == original


@pytest.mark.parametrize(
    "invalid", ["decision", "missing-candidate", "extra-candidate", "notes", "missing-notes"]
)
def test_invalid_review_fields_cannot_change_saved_revision(
    candidate_app: CandidateApplication,
    invalid: str,
) -> None:
    app = candidate_app
    with TestClient(app.scope.app) as client:
        _login(client)
        path = _prepare(client)
        detail = _find(client, path, app.release_id)
        envelope = client.get(f"{detail}/download?revision=1").json()
        form = _review_form(client, detail, envelope)
        candidate_id = envelope["candidates"][0]["candidate_id"]
        if invalid == "decision":
            form[f"candidate_{candidate_id}"] = "applicable"
        elif invalid == "missing-candidate":
            form.pop(f"candidate_{candidate_id}")
        elif invalid == "extra-candidate":
            form[f"candidate_{_uid(900)}"] = "keep"
        elif invalid == "missing-notes":
            form.pop(f"notes_{candidate_id}")
        else:
            form[f"notes_{candidate_id}"] = "x" * 4001
        before = _counts(app)
        refused = client.post(f"{detail}/review", data=form, follow_redirects=False)
        assert refused.status_code == 422
        assert _counts(app) == before
        assert client.get(f"{detail}/download?revision=2").status_code == 404


@pytest.mark.parametrize(
    "invalid", ["missing-target", "foreign-opening", "unlinked", "bad-revision"]
)
def test_invalid_candidate_creation_is_refused_without_partial_artifact(
    candidate_app: CandidateApplication,
    invalid: str,
) -> None:
    app = candidate_app
    with TestClient(app.scope.app) as client:
        _login(client)
        path = _prepare(client)
        form = _create_form(client, path, app.release_id)
        if invalid == "missing-target":
            form["opening_id"] = ""
            form["service_id"] = ""
        elif invalid == "foreign-opening":
            form["opening_id"] = _uid(901)
        elif invalid == "unlinked":
            form["opening_id"] = _uid(4)
        else:
            form["scope_revision"] = "-1"
        before = _counts(app)
        refused = client.post(f"{path}/system-matches", data=form, follow_redirects=False)
        assert refused.status_code == 422
        assert _counts(app) == before


def test_private_review_owner_admin_csrf_and_unauthenticated_boundaries(
    candidate_app: CandidateApplication,
) -> None:
    app = candidate_app
    with TestClient(app.scope.app) as owner:
        _login(owner)
        path = _prepare(owner)
        detail = _find(owner, path, app.release_id)
        envelope = owner.get(f"{detail}/download?revision=1").json()
        create_form = _create_form(owner, path, app.release_id)
        review_form = _review_form(owner, detail, envelope)
        before = _counts(app)
        assert (
            owner.post(
                f"{path}/system-matches", data={**create_form, "csrf_token": "forged"}
            ).status_code
            == 403
        )
        assert (
            owner.post(f"{detail}/review", data={**review_form, "csrf_token": "forged"}).status_code
            == 403
        )
        assert _counts(app) == before
    with TestClient(app.scope.app) as anonymous:
        assert anonymous.get(f"{path}/system-matches").status_code == 401
        assert anonymous.get(detail).status_code == 401
        assert anonymous.get(f"{detail}/download?revision=1").status_code == 401
    with TestClient(app.scope.app) as other:
        _login(other, "other")
        assert other.get(f"{path}/system-matches").status_code == 404
        assert other.get(detail).status_code == 404
        assert other.get(f"{detail}/download?revision=1").status_code == 404
        csrf = _csrf(other.get("/scopes").text)
        assert (
            other.post(f"{detail}/review", data={**review_form, "csrf_token": csrf}).status_code
            == 404
        )
    with TestClient(app.scope.app) as admin:
        _login(admin, "admin")
        assert admin.get(detail).status_code == 200
        assert admin.get(f"{detail}/download?revision=1").status_code == 200


@pytest.mark.parametrize("revoked", ["inactive", "technical", "agent"])
def test_revoked_or_agent_accounts_cannot_read_or_change_review(
    candidate_app: CandidateApplication,
    revoked: str,
) -> None:
    app = candidate_app
    with TestClient(app.scope.app) as client:
        _login(client)
        path = _prepare(client)
        detail = _find(client, path, app.release_id)
        envelope = client.get(f"{detail}/download?revision=1").json()
        form = _review_form(client, detail, envelope)
        with app.scope.factory() as db:
            user = db.get(User, app.scope.users["owner"])
            if revoked == "inactive":
                user.is_active = False
            else:
                user.role = "project_manager" if revoked == "technical" else "agent"
            db.commit()
        expected = 401 if revoked == "inactive" else 403
        before = _counts(app)
        # Submit before an inactive-user read revokes the existing CSRF session.
        assert client.post(f"{detail}/review", data=form).status_code == expected
        assert client.get(detail).status_code == expected
        assert client.get(f"{detail}/download?revision=1").status_code == expected
        assert _counts(app) == before


def test_candidate_projection_and_review_notes_do_not_expose_storage_or_execute_markup(
    candidate_app: CandidateApplication,
) -> None:
    app = candidate_app
    private_url = "https://private.invalid/source?token=DO-NOT-EXPOSE"
    with app.scope.factory() as db:
        for variant in db.scalars(select(TechnicalVariant)):
            variant.source_json = {
                "synthetic_fixture": "SYNTHETIC-P2A-001",
                "private_url": private_url,
            }
        db.commit()
    with TestClient(app.scope.app) as client:
        _login(client)
        path = _prepare(client)
        detail = _find(client, path, app.release_id)
        first = client.get(f"{detail}/download?revision=1")
        envelope = first.json()
        page = client.get(detail)
        for text in (first.text, page.text):
            assert private_url not in text
            assert "storage_path" not in text
            assert str(app.storage) not in text
        hostile = "</textarea><img src=x onerror=alert(1)>"
        form = _review_form(client, detail, envelope)
        form[f"notes_{envelope['candidates'][0]['candidate_id']}"] = hostile
        assert client.post(f"{detail}/review", data=form, follow_redirects=False).status_code == 303
        assert hostile not in client.get(detail).text
        assert (
            client.get(f"{detail}/download?revision=2").json()["decisions"][0]["notes"] == hostile
        )


@pytest.mark.parametrize("invalid", ["oversized", "duplicate", "content-type"])
def test_candidate_review_http_bounds_refuse_unsafe_forms(
    candidate_app: CandidateApplication,
    invalid: str,
) -> None:
    app = candidate_app
    with TestClient(app.scope.app) as client:
        _login(client)
        path = _prepare(client)
        form = _create_form(client, path, app.release_id)
        before = _counts(app)
        if invalid == "content-type":
            response = client.post(f"{path}/system-matches", json=form)
        else:
            content = (
                "x" * (384 * 1024 + 1)
                if invalid == "oversized"
                else urlencode(form) + "&release_id=duplicate"
            )
            response = client.post(
                f"{path}/system-matches",
                content=content,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        assert (
            response.status_code
            == {"oversized": 413, "duplicate": 422, "content-type": 415}[invalid]
        )
        assert _counts(app) == before
