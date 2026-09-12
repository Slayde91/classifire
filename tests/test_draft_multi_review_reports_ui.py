"""Explicit paired reports preserve selected review history and separate save actions."""

from __future__ import annotations

import html
import io
import re
from urllib.parse import parse_qs, urlencode, urlsplit

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
from test_draft_word_evidence_outputs import word_scope

from classifire.models import User
from classifire.services import draft_scope as scopes
from classifire.services import draft_scope_reports as reports
from classifire.services import draft_system_matches as matches
from classifire.ui import templates

candidate_app = _candidate_app
scope_app = _scope_app
scope_password_hash = _scope_password_hash
package_app = _package_app


def report_query(x):
    return [
        ("revision", "2"),
        *(("matches", f"{identity}:1") for identity in reversed(x.review_ids)),
    ]


def post(client, path, token, pairs):
    return client.post(
        path,
        content=urlencode([("csrf_token", token), *pairs]),
        headers={"content-type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )


def report_link(page):
    found = re.search(r'data-register-report\s+href="([^"]+)"', page)
    assert found is not None
    return html.unescape(found.group(1))


def test_exact_multi_review_preview_separate_save_and_frozen_downloads(
    package_app, monkeypatch, tmp_path
):
    x = package_app
    path = f"/scopes/{x.draft_id}/reports"

    def forbidden(*args, **kwargs):
        pytest.fail("Reporting must not invoke another capability")

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
        page = client.get(path + "?" + urlencode(report_query(x)))
        assert page.status_code == 200, page.text
        assert page.headers["cache-control"] == "no-store"
        assert "2 selected reviews" in page.text
        assert "Keeping a candidate is not technical approval" in page.text
        assert "Selected review is out of date:" in page.text
        assert "Unknown" in page.text
        for identity in x.review_ids:
            assert f'name="matches" value="{identity}:1" checked' in page.text
            assert f'data-report-review="{identity}"' in page.text
        assert f'name="matches" value="{x.review_ids[0]}:2"' not in page.text
        ids = re.findall(r'\bid="([^"]+)"', page.text)
        assert len(ids) == len(set(ids)), "Repeated review previews must have unique HTML IDs"
        assert counts(x) == before
        token = _csrf(page.text)
        assert post(client, path, "bad", report_query(x)).status_code == 403
        assert counts(x) == before
        saved = post(client, path, token, report_query(x))
        assert saved.status_code == 303, saved.text
        detail_path = saved.headers["location"]
        after = counts(x)
        assert after["draft_scope_reports"] == before["draft_scope_reports"] + 1
        assert after["audit_events"] == before["audit_events"] + 1
        assert {
            k: v for k, v in after.items() if k not in {"draft_scope_reports", "audit_events"}
        } == {k: v for k, v in before.items() if k not in {"draft_scope_reports", "audit_events"}}
        with x.factory() as db:
            actor = db.get(User, x.users["owner"])
            snapshot = reports.read_report(db, actor, x.draft_id, detail_path.rsplit("/", 1)[1])
            assert snapshot["schema_version"] == "CLASSIFIRE-DRAFT-SCOPE-REPORT-v3"
            assert snapshot["scope"] == x.scope
            assert [
                (item["artifact_id"], item["revision"]) for item in snapshot["system_matches"]
            ] == [(identity, 1) for identity in sorted(x.review_ids)]
        detail = client.get(detail_path)
        assert detail.status_code == 200, detail.text
        for identity in x.review_ids:
            assert f'data-report-review="{identity}"' in detail.text
        assert "No measured-limit review saved" in detail.text
        pdf = client.get(detail_path + "/download?format=pdf")
        xlsx = client.get(detail_path + "/download?format=xlsx")
        assert pdf.status_code == xlsx.status_code == 200
        assert "CLASSIFIRE-Scope-System-Report" in pdf.headers["content-disposition"]
        pdf_text = " ".join(
            page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages
        )
        book = load_workbook(io.BytesIO(xlsx.content), data_only=False)
        strings = " ".join(
            str(cell.value)
            for sheet in book
            for row in sheet
            for cell in row
            if cell.value is not None
        )
        for identity in x.review_ids:
            assert identity in pdf_text and identity in strings
        book.close()
        (tmp_path / "paired-report.html").write_text(detail.text, encoding="utf-8")
        (tmp_path / "paired-report.pdf").write_bytes(pdf.content)
        (tmp_path / "paired-report.xlsx").write_bytes(xlsx.content)
        with x.factory() as db:
            actor = db.get(User, x.users["owner"])
            changed = _payload()
            changed["services"][0]["quantity"] = "7"
            scopes.save_revision(db, actor, x.draft_id, 2, changed)
            db.commit()
        assert "Out of date:" in client.get(detail_path).text
        assert client.get(detail_path + "/download?format=pdf").content == pdf.content
        assert client.get(detail_path + "/download?format=xlsx").content == xlsx.content
        with x.factory() as db:
            db.get(User, x.users["owner"]).role = "project_manager"
            db.commit()
        before_denial = counts(x)
        for url in (
            path + "?" + urlencode(report_query(x)),
            detail_path,
            detail_path + "/download?format=pdf",
        ):
            assert client.get(url).status_code == 403
        assert post(client, path, token, report_query(x)).status_code == 403
        assert counts(x) == before_denial
        assert client.get(path).status_code == 200
    _assert_no_canonical_scope(x.factory)


def test_old_selected_reviews_survive_picker_and_register_preserves_exact_paths(package_app):
    x = package_app
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
        path = f"/scopes/{x.draft_id}"
        page = client.get(path + "/reports?" + urlencode(report_query(x)))
        assert page.status_code == 200, page.text
        for identity in x.review_ids:
            assert f'name="matches" value="{identity}:1" checked' in page.text
        editor = client.get(
            path
            + "?"
            + urlencode(
                [("revision", "2"), *(("match", f"{identity}:1") for identity in x.review_ids)]
            )
        )
        url = report_link(editor.text)
        assert parse_qs(urlsplit(url).query) == {
            "revision": ["2"],
            "matches": [f"{identity}:1" for identity in x.review_ids],
        }
        assert client.get(url).status_code == 200
        single = client.get(path + "?revision=2&match=" + x.review_ids[0] + ":1")
        assert (
            report_link(single.text)
            == path + "/system-matches/" + x.review_ids[0] + "/reports?revision=1"
        )
        empty = client.get(path + "?revision=2")
        assert report_link(empty.text) == path + "/reports?revision=2"
        invalid = client.get(path + "?revision=2&match=bad")
        assert "data-register-report" not in invalid.text
        assert counts(x) == before


@pytest.mark.parametrize(
    "case",
    [
        "blank",
        "malformed",
        "duplicate",
        "mixed",
        "scope-mismatch",
        "missing-scope",
        "missing-review",
        "conflicting-row",
    ],
)
def test_invalid_report_choices_fail_visibly_without_writes_or_scope_only_fallback(
    package_app, case
):
    x = package_app
    path = f"/scopes/{x.draft_id}/reports"
    valid = report_query(x)
    conflict_id = None
    if case == "conflicting-row":
        with x.factory() as db:
            actor = db.get(User, x.users["owner"])
            conflicting = matches.create_match(
                db,
                actor,
                x.draft_id,
                2,
                x.release_id,
                _uid(2),
                _uid(5),
                storage_root=x.storage,
            )
            conflict_id = conflicting.id
            db.commit()
    invalid = {
        "blank": [("revision", "2"), ("matches", "")],
        "malformed": [("revision", "2"), ("matches", "not-a-review")],
        "duplicate": [*valid, valid[-1]],
        "mixed": [*valid, ("match_id", x.review_ids[0]), ("match_revision", "1")],
        "scope-mismatch": [("revision", "1"), *valid[1:]],
        "missing-scope": valid[1:],
        "missing-review": [("revision", "2"), ("matches", _uid(99999) + ":1")],
        "conflicting-row": [*valid, ("matches", str(conflict_id) + ":1")],
    }[case]
    with TestClient(x.app) as client:
        _login(client)
        token = _csrf(client.get(path).text)
        before = counts(x)
        for response in (
            client.get(path + "?" + urlencode(invalid)),
            post(client, path, token, invalid),
        ):
            expected = {"scope-mismatch": 409, "missing-review": 404}.get(case, 422)
            assert response.status_code == expected, response.text
            assert "Create PDF and Excel report" not in response.text
        assert counts(x) == before


def test_legacy_partial_target_retains_its_single_report_route(package_app):
    x = package_app
    with x.factory() as db:
        actor = db.get(User, x.users["owner"])
        review = matches.create_match(
            db, actor, x.draft_id, 2, x.release_id, None, _uid(5), storage_root=x.storage
        )
        review_id = review.id
        db.commit()
    with TestClient(x.app) as client:
        _login(client)
        before = counts(x)
        path = f"/scopes/{x.draft_id}"
        editor = client.get(path + "?revision=2&match=" + review_id + ":1")
        legacy_path = path + "/system-matches/" + review_id + "/reports?revision=1"
        assert report_link(editor.text) == legacy_path
        assert client.get(legacy_path).status_code == 200
        picker = client.get(path + "/reports?revision=2")
        assert f'href="{legacy_path}"' in picker.text
        assert f'name="matches" value="{review_id}:1"' not in picker.text
        invalid = [("revision", "2"), ("matches", review_id + ":1")]
        assert client.get(path + "/reports?" + urlencode(invalid)).status_code == 422
        assert post(client, path + "/reports", _csrf(picker.text), invalid).status_code == 422
        assert counts(x) == before


def test_word_v7_saved_content_flattens_provenance_and_preserves_review_status():
    scope = word_scope()
    before = scopes._json(scope)
    rendered = templates.env.get_template("draft_scope_report_content.html").render(envelope=scope)
    assert "Saved evidence-review references" in rendered
    assert "Saved page-review references" not in rendered
    assert "word locator" in rendered and "word text sha256" in rendered
    assert "image picture-1 member" in rendered
    assert "word/media/image1.png" in rendered
    assert "saved revision review status" in rendered
    assert "untrusted Word text" in rendered
    assert "&#39;locator&#39;:" not in rendered
    assert "&#39;proposed_item&#39;:" not in rendered
    assert scopes._json(scope) == before
