from __future__ import annotations

import hashlib
import io
import json
import re
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from pypdf import PdfReader
from sqlalchemy import func, select
from test_draft_scope_import_ui import _confirm as _confirm_import
from test_draft_scope_import_ui import _preview as _preview_import
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

from classifire.models import AuditEvent, DraftScope, DraftScopeReport, Project, User

scope_app = _scope_app
scope_password_hash = _scope_password_hash


def _prepare(client: TestClient) -> str:
    path = _create(client, "SYNTHETIC-REPORT")
    assert _edit(client, path, _payload()).status_code == 303
    return path


def _generate(client: TestClient, path: str, revision: int = 2) -> str:
    page = client.get(f"{path}/reports?revision={revision}")
    assert page.status_code == 200, page.text
    response = client.post(
        f"{path}/reports",
        data={"csrf_token": _csrf(page.text), "revision": str(revision)},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    detail = response.headers["location"]
    assert re.fullmatch(rf"{re.escape(path)}/reports/[0-9a-f-]{{36}}", detail)
    return detail


def _counts(scope_app: ScopeApplication) -> tuple[int | None, ...]:
    with scope_app.factory() as db:
        return tuple(
            db.scalar(select(func.count()).select_from(model))
            for model in (DraftScopeReport, AuditEvent)
        )


def _workbook_values(content: bytes) -> Iterator[Any]:
    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=False)
    try:
        for sheet in workbook:
            for row in sheet:
                for cell in row:
                    if cell.value is not None:
                        yield cell.value
    finally:
        workbook.close()


def test_scope_only_report_generates_pdf_and_xlsx_from_one_frozen_snapshot(
    scope_app: ScopeApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_downstream(*args: object, **kwargs: object) -> None:
        pytest.fail("Scope reporting must not run AI, estimation or canonical workflows")

    for target in (
        "classifire.services.technical.search_for_opening",
        "classifire.services.calculation.recalculate_estimate",
        "classifire.services.snapshot.build_estimate_snapshot",
        "classifire.services.snapshot.lock_snapshot",
        "classifire.services.initial_canonicalisation_boundary.require_admission_bound_initial_canonicalisation",
        "classifire.services.phase8_openresponses_transport.Phase8OpenResponsesTransport.invoke",
    ):
        monkeypatch.setattr(target, forbidden_downstream)
    with TestClient(scope_app.app) as client:
        _login(client)
        path = _prepare(client)
        before = _counts(scope_app)
        selection = client.get(f"{path}/reports?revision=2")
        assert selection.status_code == 200
        assert "Insulation and fire rating require evidence" in selection.text
        assert _counts(scope_app) == before
        detail = _generate(client, path)
        page = client.get(detail)
        assert page.status_code == 200
        assert "Draft" in page.text
        assert "Synthetic shared opening review" in page.text
        pdf = client.get(f"{detail}/download?format=pdf")
        xlsx = client.get(f"{detail}/download?format=xlsx")
        for response, media_type, suffix in (
            (pdf, "application/pdf", ".pdf"),
            (xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
        ):
            assert response.status_code == 200
            assert response.headers["content-type"].startswith(media_type)
            assert "attachment;" in response.headers["content-disposition"]
            assert suffix in response.headers["content-disposition"]
            assert "SYNTHETIC-REPORT" not in response.headers["content-disposition"]
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-content-type-options"] == "nosniff"
        assert pdf.content.startswith(b"%PDF-")
        assert xlsx.content.startswith(b"PK")
        with scope_app.factory() as db:
            report = db.get(DraftScopeReport, detail.rsplit("/", 1)[1])
            assert report is not None
            frozen = json.loads(report.snapshot_json)
            assert frozen["profile"] == "scope-only"
            assert frozen["state"] == "Draft"
            assert frozen["review_status"] == "unreviewed"
            assert frozen["project"]["reference"] == "SYNTHETIC-REPORT"
            assert frozen["scope"]["revision"] == 2
            assert frozen["scope"]["artifact_id"] == path.rsplit("/", 1)[1]
            assert report.pdf_sha256 == hashlib.sha256(pdf.content).hexdigest()
            assert report.xlsx_sha256 == hashlib.sha256(xlsx.content).hexdigest()
            assert report.pdf_bytes == pdf.content
            assert report.xlsx_bytes == xlsx.content
            digest = report.snapshot_hash
        pdf_text = "\n".join(
            page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf.content)).pages
        )
        workbook_text = "\n".join(str(value) for value in _workbook_values(xlsx.content))
        for text in (pdf_text, workbook_text):
            assert digest in text
            assert "D-01" in text
            assert "Cable group" in text
            assert "Insulation and fire rating require evidence" in text
            assert "draft" in text.lower()
            assert "unresolved" in text.lower()
        assert client.get(f"{detail}/download?format=pdf").content == pdf.content
        assert client.get(f"{detail}/download?format=xlsx").content == xlsx.content
    _assert_no_canonical_scope(scope_app.factory)


def test_later_scope_and_project_edits_mark_report_stale_without_rerendering(
    scope_app: ScopeApplication,
) -> None:
    with TestClient(scope_app.app) as client:
        _login(client)
        path = _prepare(client)
        detail = _generate(client, path)
        pdf = client.get(f"{detail}/download?format=pdf").content
        xlsx = client.get(f"{detail}/download?format=xlsx").content
        with scope_app.factory() as db:
            report = db.get(DraftScopeReport, detail.rsplit("/", 1)[1])
            assert report is not None
            original_snapshot = report.snapshot_json
            draft = db.get(DraftScope, path.rsplit("/", 1)[1])
            assert draft is not None
            project = db.get(Project, draft.project_id)
            assert project is not None
            project.name = "Changed after frozen reporting"
            project.reference = "CHANGED-AFTER-REPORT"
            db.commit()
        project_stale_page = client.get(detail)
        assert project_stale_page.status_code == 200
        assert "Out of date" in project_stale_page.text
        changed_scope = _payload()
        changed_scope["assumptions"] = ["Later scope change must not replace previous output"]
        assert _edit(client, path, changed_scope, revision=2).status_code == 303
        scope_stale_page = client.get(detail)
        assert scope_stale_page.status_code == 200
        assert "Out of date" in scope_stale_page.text
        assert client.get(f"{detail}/download?format=pdf").content == pdf
        assert client.get(f"{detail}/download?format=xlsx").content == xlsx
        with scope_app.factory() as db:
            report = db.get(DraftScopeReport, detail.rsplit("/", 1)[1])
            assert report is not None
            assert report.snapshot_json == original_snapshot
            assert db.scalar(select(func.count()).select_from(DraftScopeReport)) == 1


@pytest.mark.parametrize("revision", [None, "", "0", "-1", "not-a-revision"])
def test_report_creation_requires_an_explicit_valid_saved_revision(
    scope_app: ScopeApplication,
    revision: str | None,
) -> None:
    with TestClient(scope_app.app) as client:
        _login(client)
        path = _prepare(client)
        form = {"csrf_token": _csrf(client.get(f"{path}/reports").text)}
        if revision is not None:
            form["revision"] = revision
        before = _counts(scope_app)
        refused = client.post(f"{path}/reports", data=form, follow_redirects=False)
        assert refused.status_code == 422
        assert _counts(scope_app) == before


def test_reporting_refuses_unknown_revision_report_format_and_foreign_draft_binding(
    scope_app: ScopeApplication,
) -> None:
    with TestClient(scope_app.app) as client:
        _login(client)
        path = _prepare(client)
        detail = _generate(client, path)
        other = _create(client, "OTHER-REPORT-PROJECT")
        csrf = _csrf(client.get(f"{path}/reports").text)
        before = _counts(scope_app)
        assert (
            client.post(
                f"{path}/reports",
                data={"csrf_token": csrf, "revision": "99"},
            ).status_code
            == 404
        )
        assert client.get(f"{path}/reports/{_uid(999)}").status_code == 404
        assert client.get(f"{path}/reports/{_uid(999)}/download?format=pdf").status_code == 404
        assert client.get(f"{detail}/download?format=csv").status_code == 422
        wrong_binding = f"{other}/reports/{detail.rsplit('/', 1)[1]}"
        assert client.get(wrong_binding).status_code == 404
        assert client.get(f"{wrong_binding}/download?format=pdf").status_code == 404
        assert _counts(scope_app) == before


def test_report_routes_enforce_owner_admin_session_and_csrf_boundaries(
    scope_app: ScopeApplication,
) -> None:
    with TestClient(scope_app.app) as owner:
        _login(owner)
        path = _prepare(owner)
        detail = _generate(owner, path)
        before = _counts(scope_app)
        refused = owner.post(
            f"{path}/reports",
            data={"csrf_token": "forged", "revision": "2"},
        )
        assert refused.status_code == 403
        assert _counts(scope_app) == before
    with TestClient(scope_app.app) as anonymous:
        assert anonymous.get(f"{path}/reports").status_code == 401
        assert anonymous.get(detail).status_code == 401
        assert anonymous.get(f"{detail}/download?format=pdf").status_code == 401
    with TestClient(scope_app.app) as other:
        _login(other, "other")
        assert other.get(f"{path}/reports").status_code == 404
        assert other.get(detail).status_code == 404
        assert other.get(f"{detail}/download?format=pdf").status_code == 404
        csrf = _csrf(other.get("/scopes").text)
        assert (
            other.post(
                f"{path}/reports",
                data={"csrf_token": csrf, "revision": "2"},
            ).status_code
            == 404
        )
    with TestClient(scope_app.app) as admin:
        _login(admin, "admin")
        assert admin.get(detail).status_code == 200
        assert admin.get(f"{detail}/download?format=pdf").status_code == 200
    _assert_no_canonical_scope(scope_app.factory)


def test_read_only_owner_can_read_retained_report_but_cannot_create_another(
    scope_app: ScopeApplication,
) -> None:
    with TestClient(scope_app.app) as client:
        _login(client)
        path = _prepare(client)
        detail = _generate(client, path)
        with scope_app.factory() as db:
            user = db.get(User, scope_app.users["owner"])
            assert user is not None
            user.role = "read_only"
            db.commit()
        assert client.get(detail).status_code == 200
        assert client.get(f"{detail}/download?format=xlsx").status_code == 200
        page = client.get(f"{path}/reports")
        assert page.status_code == 200
        before = _counts(scope_app)
        refused = client.post(
            f"{path}/reports",
            data={"csrf_token": _csrf(page.text), "revision": "2"},
        )
        assert refused.status_code == 403
        assert _counts(scope_app) == before


def test_inactive_session_cannot_read_or_generate_scope_reports(
    scope_app: ScopeApplication,
) -> None:
    with TestClient(scope_app.app) as client:
        _login(client)
        path = _prepare(client)
        detail = _generate(client, path)
        csrf = _csrf(client.get(f"{path}/reports").text)
        with scope_app.factory() as db:
            user = db.get(User, scope_app.users["owner"])
            assert user is not None
            user.is_active = False
            db.commit()
        before = _counts(scope_app)
        assert (
            client.post(
                f"{path}/reports",
                data={"csrf_token": csrf, "revision": "2"},
            ).status_code
            == 401
        )
        assert client.get(detail).status_code == 401
        assert client.get(f"{detail}/download?format=pdf").status_code == 401
        assert _counts(scope_app) == before


def test_report_preview_and_retained_detail_escape_untrusted_scope_text(
    scope_app: ScopeApplication,
) -> None:
    hostile = "</script><img src=x onerror=alert(1)>"
    with TestClient(scope_app.app) as client:
        _login(client)
        path = _create(client, "REPORT-XSS")
        payload = {"observations": [{"id": _uid(70), "text": hostile, "state": "Unresolved"}]}
        assert _edit(client, path, payload).status_code == 303
        selection = client.get(f"{path}/reports?revision=2")
        assert selection.status_code == 200
        assert hostile not in selection.text
        detail = _generate(client, path)
        retained = client.get(detail)
        assert retained.status_code == 200
        assert hostile not in retained.text
        with scope_app.factory() as db:
            report = db.get(DraftScopeReport, detail.rsplit("/", 1)[1])
            assert report is not None
            assert (
                json.loads(report.snapshot_json)["scope"]["content"]["observations"][0]["text"]
                == hostile
            )


@pytest.mark.parametrize("corrupted", ["snapshot_json", "pdf_bytes", "xlsx_bytes"])
def test_corrupted_retained_report_fails_closed_without_download_audit(
    scope_app: ScopeApplication,
    corrupted: str,
) -> None:
    with TestClient(scope_app.app) as client:
        _login(client)
        path = _prepare(client)
        detail = _generate(client, path)
        with scope_app.factory() as db:
            report = db.get(DraftScopeReport, detail.rsplit("/", 1)[1])
            assert report is not None
            if corrupted == "snapshot_json":
                data = json.loads(report.snapshot_json)
                data["project"]["name"] = "Tampered frozen project"
                report.snapshot_json = json.dumps(data)
            else:
                setattr(report, corrupted, b"tampered output")
            db.commit()
        before = _counts(scope_app)
        assert client.get(f"{detail}/download?format=pdf").status_code == 409
        assert client.get(detail).status_code == 409
        assert _counts(scope_app) == before


def test_reporting_imported_v2_scope_preserves_its_historical_provenance(
    scope_app: ScopeApplication,
) -> None:
    with TestClient(scope_app.app) as client:
        _login(client)
        source = _prepare(client)
        source_bytes = client.get(f"{source}/download?revision=2").content
        target = _create(client, "IMPORTED-REPORT-TARGET")
        preview = _preview_import(client, target, source_bytes)
        assert preview.status_code == 200
        assert _confirm_import(client, target, preview).status_code == 303
        imported = client.get(f"{target}/download?revision=2").json()
        assert imported["schema_version"] == "CLASSIFIRE-DRAFT-SCOPE-v2"
        detail = _generate(client, target)
        assert client.get(detail).status_code == 200
        with scope_app.factory() as db:
            report = db.get(DraftScopeReport, detail.rsplit("/", 1)[1])
            assert report is not None
            snapshot = json.loads(report.snapshot_json)
            assert snapshot["scope"] == imported
            assert snapshot["review_status"] == "unreviewed"
        pdf = client.get(f"{detail}/download?format=pdf")
        xlsx = client.get(f"{detail}/download?format=xlsx")
        assert pdf.status_code == 200
        assert xlsx.status_code == 200
        pdf_text = "\n".join(
            page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf.content)).pages
        )
        workbook_text = "\n".join(str(value) for value in _workbook_values(xlsx.content))
        for text in (pdf_text, workbook_text):
            assert snapshot["sha256"] in text
            assert imported["import_lineage"][0]["file_sha256"] in text
    _assert_no_canonical_scope(scope_app.factory)
