"""Complete reports select extra reviews without changing the exact saved Estimate."""

from __future__ import annotations

import io
import re
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from pypdf import PdfReader
from test_draft_multi_review_package_ui import candidate_app as _candidate_app
from test_draft_multi_review_package_ui import counts
from test_draft_multi_review_package_ui import package_app as _package_app
from test_draft_multi_review_package_ui import scope_app as _scope_app
from test_draft_multi_review_package_ui import scope_password_hash as _scope_password_hash
from test_draft_scope_ui import _assert_no_canonical_scope, _csrf, _login, _payload, _uid

from classifire.draft_estimate_ui import router
from classifire.models import User
from classifire.services import draft_estimate_reports as reports
from classifire.services import draft_estimates as estimates
from classifire.services import draft_scope as scopes
from classifire.services import draft_system_matches as matches

candidate_app = _candidate_app
scope_app = _scope_app
scope_password_hash = _scope_password_hash
package_app = _package_app


@pytest.fixture
def report_app(package_app, monkeypatch):
    x = package_app
    x.app.include_router(router)
    monkeypatch.setattr(
        "classifire.draft_estimate_ui.get_settings", lambda: SimpleNamespace(storage_root=x.storage)
    )
    x.report_path = f"/scopes/{x.draft_id}/estimates/{x.estimate_id}/reports"
    with x.factory() as db:
        actor = db.get(User, x.users["owner"])
        x.estimate = estimates.read_estimate_revision(db, actor, x.draft_id, x.estimate_id, 2)
    return x


def query(x):
    return [
        ("revision", "2"),
        ("profile", "complete"),
        *(("matches", f"{identity}:1") for identity in reversed(x.review_ids)),
    ]


def post(client, path, token, pairs):
    return client.post(
        path,
        content=urlencode([("csrf_token", token), *pairs]),
        headers={"content-type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )


def save(client, x):
    page = client.get(x.report_path + "?" + urlencode(query(x)))
    assert page.status_code == 200, page.text
    response = post(client, x.report_path, _csrf(page.text), query(x))
    assert response.status_code == 303, response.text
    return response.headers["location"]


def test_complete_preview_separate_save_frozen_pair_and_exact_estimate(
    report_app, monkeypatch, tmp_path
):
    x = report_app

    def forbidden(*args, **kwargs):
        pytest.fail("Complete reporting must not run another capability")

    for target in (
        "classifire.services.draft_system_matches.create_match",
        "classifire.services.draft_estimates.create_estimate",
        "classifire.services.technical.search_for_opening",
        "classifire.services.calculation.recalculate_estimate",
        "classifire.services.snapshot.lock_snapshot",
        "classifire.services.phase8_openresponses_transport.Phase8OpenResponsesTransport.invoke",
    ):
        monkeypatch.setattr(target, forbidden)
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        page = client.get(x.report_path + "?" + urlencode(query(x)))
        assert page.status_code == 200, page.text
        assert page.headers["cache-control"] == "no-store"
        assert "2 explicitly selected reviews" in page.text
        assert "Estimate-bound review" in page.text
        assert "Additional report-only context" in page.text
        assert "no price or Estimate change" in page.text
        assert "Unknown" in page.text and "Unapproved" in page.text
        assert "Report review changed" in page.text
        assert "Save line changes" not in page.text
        for identity in x.review_ids:
            assert f'name="matches" value="{identity}:1" checked' in page.text
            assert f'data-report-review="{identity}"' in page.text
        assert f'name="matches" value="{x.review_ids[0]}:2"' not in page.text
        ids = re.findall(r'\bid="([^"]+)"', page.text)
        assert len(ids) == len(set(ids))
        assert counts(x) == before
        assert post(client, x.report_path, "bad", query(x)).status_code == 403
        assert counts(x) == before
        saved_path = save(client, x)
        after = counts(x)
        assert after["draft_estimate_reports"] == before["draft_estimate_reports"] + 1
        assert after["audit_events"] == before["audit_events"] + 1
        assert {
            k: v for k, v in after.items() if k not in {"draft_estimate_reports", "audit_events"}
        } == {
            k: v for k, v in before.items() if k not in {"draft_estimate_reports", "audit_events"}
        }
        with x.factory() as db:
            actor = db.get(User, x.users["owner"])
            snapshot = reports.read_report(
                db, actor, x.draft_id, x.estimate_id, saved_path.rsplit("/", 1)[1]
            )
            assert snapshot["schema_version"] == "CLASSIFIRE-DRAFT-ESTIMATE-REPORT-v3"
            assert snapshot["render_version"] == 12
            assert snapshot["estimate"] == x.estimate
            assert [(r["artifact_id"], r["revision"]) for r in snapshot["system_matches"]] == [
                (identity, 1) for identity in sorted(x.review_ids)
            ]
            assert (
                estimates.read_estimate_revision(db, actor, x.draft_id, x.estimate_id) == x.estimate
            )
        saved = client.get(saved_path)
        assert saved.status_code == 200
        assert "Save line changes" not in saved.text
        assert "Create saved Complete PDF" not in saved.text
        for identity in x.review_ids:
            assert f'data-report-review="{identity}"' in saved.text
        pdf = client.get(saved_path + "/download?format=pdf")
        xlsx = client.get(saved_path + "/download?format=xlsx")
        assert pdf.status_code == xlsx.status_code == 200
        assert "CLASSIFIRE-Draft-Complete-Report" in pdf.headers["content-disposition"]
        assert pdf.headers["cache-control"] == "no-store"
        text = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
        book = load_workbook(io.BytesIO(xlsx.content), data_only=False)
        cells = [cell for sheet in book for row in sheet for cell in row]
        strings = " ".join(str(cell.value) for cell in cells if cell.value is not None)
        for identity in x.review_ids:
            assert identity in text and identity in strings
        assert x.estimate["summary"]["priced_subtotal_ex_tax"] in text
        assert all(cell.data_type != "f" and cell.hyperlink is None for cell in cells)
        book.close()
        (tmp_path / "complete-report.html").write_text(saved.text, encoding="utf-8")
        (tmp_path / "complete-report.pdf").write_bytes(pdf.content)
        (tmp_path / "complete-report.xlsx").write_bytes(xlsx.content)
        with x.factory() as db:
            actor = db.get(User, x.users["owner"])
            estimates.override_line(
                db,
                actor,
                x.draft_id,
                x.estimate_id,
                2,
                x.estimate["lines"][0]["line_id"],
                {
                    "quantity": "7",
                    "unit_sell_rate": "2",
                    "reason": "Later independent Estimate edit",
                },
            )
            db.commit()
        assert "Saved inputs are out of date" in client.get(saved_path).text
        assert client.get(saved_path + "/download?format=pdf").content == pdf.content
        assert client.get(saved_path + "/download?format=xlsx").content == xlsx.content
        historical = client.get(x.report_path + "?" + urlencode(query(x)))
        assert historical.status_code == 200 and "Report estimate changed" in historical.text
    _assert_no_canonical_scope(x.factory)


def test_old_selected_and_bound_reviews_remain_exact_and_unselected_legacy_stays_legacy(report_app):
    x = report_app
    with x.factory() as db:
        actor = db.get(User, x.users["owner"])
        for _ in range(matches.MATCH_LIST_LIMIT):
            matches.create_match(
                db, actor, x.draft_id, 2, x.release_id, _uid(2), _uid(6), storage_root=x.storage
            )
        assert not set(x.review_ids) & {
            row.id for row in matches.list_matches(db, actor, x.draft_id)
        }
        db.commit()
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        selected = client.get(x.report_path + "?" + urlencode(query(x)))
        assert selected.status_code == 200, selected.text
        for identity in x.review_ids:
            assert f'name="matches" value="{identity}:1" checked' in selected.text
        legacy = client.get(x.report_path + "?revision=2&profile=complete")
        assert legacy.status_code == 200, legacy.text
        assert f'name="matches" value="{x.review_ids[0]}:1">' in legacy.text
        assert 'name="matches" value="' in legacy.text
        assert not re.search(r'name="matches"[^>]*checked', legacy.text)
        assert counts(x) == before
        response = post(
            client, x.report_path, _csrf(legacy.text), [("revision", "2"), ("profile", "complete")]
        )
        assert response.status_code == 303
        with x.factory() as db:
            actor = db.get(User, x.users["owner"])
            snapshot = reports.read_report(
                db, actor, x.draft_id, x.estimate_id, response.headers["location"].rsplit("/", 1)[1]
            )
            assert snapshot["schema_version"] == "CLASSIFIRE-DRAFT-ESTIMATE-REPORT-v2"
            assert "system_matches" not in snapshot
            assert snapshot["estimate"] == x.estimate


@pytest.mark.parametrize(
    "case",
    [
        "blank",
        "duplicate",
        "mixed",
        "estimate-only",
        "missing-bound",
        "newer-bound",
        "missing-review",
        "conflicting-row",
        "scope-mismatch",
    ],
)
def test_invalid_complete_selection_is_visible_and_never_substituted(report_app, case):
    x = report_app
    valid = query(x)
    other_ref = _uid(99999) + ":1"
    if case in {"conflicting-row", "scope-mismatch"}:
        with x.factory() as db:
            actor = db.get(User, x.users["owner"])
            revision = 2
            if case == "scope-mismatch":
                changed = _payload()
                changed["defects"][0]["description"] = "Later Scope"
                scopes.save_revision(db, actor, x.draft_id, 2, changed)
                revision = 3
            other = matches.create_match(
                db,
                actor,
                x.draft_id,
                revision,
                x.release_id,
                _uid(2),
                _uid(5),
                storage_root=x.storage,
            )
            other_ref = other.id + ":1"
            db.commit()
    invalid = {
        "blank": [*valid[:2], ("matches", "")],
        "duplicate": [*valid, valid[-1]],
        "mixed": [*valid, ("match_id", x.review_ids[0])],
        "estimate-only": [("revision", "2"), ("profile", "estimate-only"), *valid[2:]],
        "missing-bound": [*valid[:2], ("matches", x.review_ids[1] + ":1")],
        "newer-bound": [
            *valid[:2],
            ("matches", x.review_ids[0] + ":2"),
            ("matches", x.review_ids[1] + ":1"),
        ],
        "missing-review": [*valid, ("matches", other_ref)],
        "conflicting-row": [*valid, ("matches", other_ref)],
        "scope-mismatch": [*valid, ("matches", other_ref)],
    }[case]
    expected = {
        "missing-bound": 409,
        "newer-bound": 409,
        "scope-mismatch": 409,
        "missing-review": 404,
    }.get(case, 422)
    with TestClient(x.app) as client:
        _login(client)
        token = _csrf(client.get(x.report_path).text)
        before = counts(x)
        for result in (
            client.get(x.report_path + "?" + urlencode(invalid)),
            post(client, x.report_path, token, invalid),
        ):
            assert result.status_code == expected, result.text
            assert "Create saved Complete" not in result.text
        assert counts(x) == before


@pytest.mark.parametrize("role", ["project_manager", "read_only", "approver"])
def test_complete_report_permission_preview_save_read_and_export_boundaries(report_app, role):
    x = report_app
    with TestClient(x.app) as client:
        _login(client)
        saved_path = save(client, x)
        token = _csrf(client.get(x.report_path).text)
        with x.factory() as db:
            db.get(User, x.users["owner"]).role = role
            db.commit()
        before = counts(x)
        preview = client.get(x.report_path + "?" + urlencode(query(x)))
        saved = client.get(saved_path)
        assert (
            preview.status_code == saved.status_code == (403 if role == "project_manager" else 200)
        )
        assert "Create saved Complete PDF and XLSX" not in preview.text
        assert "Save line changes" not in saved.text
        assert post(client, x.report_path, token, query(x)).status_code == 403
        if role != "approver":
            assert client.get(saved_path + "/download?format=pdf").status_code == 403
            assert counts(x) == before
        else:
            assert client.get(saved_path + "/download?format=pdf").status_code == 200
    with TestClient(x.app) as outsider:
        assert outsider.get(saved_path).status_code == 401
        _login(outsider, "other")
        before = counts(x)
        for path in (
            saved_path,
            saved_path + "/download?format=xlsx",
            x.report_path + "?" + urlencode(query(x)),
        ):
            assert outsider.get(path).status_code in {403, 404}
        token = _csrf(outsider.get("/scopes").text)
        assert post(outsider, x.report_path, token, query(x)).status_code in {403, 404}
        assert counts(x) == before


def test_unbound_estimate_keeps_no_embedded_review_with_extra_report_context(report_app):
    x = report_app
    with x.factory() as db:
        actor = db.get(User, x.users["owner"])
        estimate = estimates.create_estimate(db, actor, x.draft_id, 2)
        x.estimate_id = estimate.id
        x.report_path = f"/scopes/{x.draft_id}/estimates/{estimate.id}/reports"
        expected = estimates.read_estimate_revision(db, actor, x.draft_id, estimate.id, 1)
        db.commit()
    selected = [("revision", "1"), *query(x)[1:]]
    with TestClient(x.app) as client:
        _login(client)
        preview = client.get(x.report_path + "?" + urlencode(selected))
        assert preview.status_code == 200, preview.text
        assert "None attached to this Estimate" in preview.text
        assert "2 additional saved row reviews" in preview.text
        result = post(client, x.report_path, _csrf(preview.text), selected)
        assert result.status_code == 303, result.text
        with x.factory() as db:
            actor = db.get(User, x.users["owner"])
            snapshot = reports.read_report(
                db, actor, x.draft_id, x.estimate_id, result.headers["location"].rsplit("/", 1)[1]
            )
            assert snapshot["estimate"] == expected
            assert snapshot["estimate"]["system_match"] is None
            assert len(snapshot["system_matches"]) == 2


@pytest.mark.parametrize("target", ["service-only", "opening-only"])
def test_legacy_partial_target_complete_report_remains_available_without_collection(
    report_app, target
):
    x = report_app
    with x.factory() as db:
        actor = db.get(User, x.users["owner"])
        match = matches.create_match(
            db,
            actor,
            x.draft_id,
            2,
            x.release_id,
            _uid(2) if target == "opening-only" else None,
            _uid(5) if target == "service-only" else None,
            storage_root=x.storage,
        )
        review_id = match.id
        estimate = estimates.create_estimate(
            db, actor, x.draft_id, 2, match_id=review_id, match_revision=1
        )
        estimate_id = estimate.id
        expected = estimates.read_estimate_revision(db, actor, x.draft_id, estimate_id, 1)
        db.commit()
    path = f"/scopes/{x.draft_id}/estimates/{estimate_id}/reports"
    legacy = [("revision", "1"), ("profile", "complete")]
    selected = [*legacy, ("matches", review_id + ":1")]
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        preview = client.get(path + "?" + urlencode(legacy))
        assert preview.status_code == 200, preview.text
        assert "This historical target remains available" in preview.text
        assert f'name="matches" value="{review_id}:1"' not in preview.text
        assert counts(x) == before
        token = _csrf(preview.text)
        assert client.get(path + "?" + urlencode(selected)).status_code == 422
        assert post(client, path, token, selected).status_code == 422
        assert counts(x) == before
        saved = post(client, path, token, legacy)
        assert saved.status_code == 303, saved.text
        with x.factory() as db:
            actor = db.get(User, x.users["owner"])
            snapshot = reports.read_report(
                db, actor, x.draft_id, estimate_id, saved.headers["location"].rsplit("/", 1)[1]
            )
            assert snapshot["schema_version"] == "CLASSIFIRE-DRAFT-ESTIMATE-REPORT-v2"
            assert snapshot["estimate"] == expected
            assert "system_matches" not in snapshot
