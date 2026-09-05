from __future__ import annotations

import io
import json
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from sqlalchemy import func, select
from test_draft_constraint_review import base_case as _base_case
from test_draft_constraint_review import case as _case
from test_draft_estimates import add_payload, prepare
from test_draft_scope import setup, uid  # noqa: F401
from test_draft_system_matches import counts, create

from classifire.models import AuditEvent, DraftProjectPackage, User
from classifire.services import draft_estimate_reports as reports
from classifire.services import draft_estimates as estimates
from classifire.services import draft_project_packages as packages
from classifire.services import draft_scope as scopes

base_case = _base_case
case = _case


def save(db, actor, draft_id, selected, revision=0):
    preview = packages.preview(db, actor, draft_id, selected)
    return packages.create_package(db, actor, draft_id, selected, revision, preview["preview_hash"])


def test_scope_only_preview_is_read_only_and_exact_after_restart(setup, tmp_path):  # noqa: F811
    with setup() as db:
        actor, draft, _ = prepare(db)
        selected = {"scope_revision": 2}
        before = db.scalar(select(func.count()).select_from(AuditEvent))
        preview = packages.preview(db, actor, draft.id, selected)
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == before
        assert db.scalar(select(func.count()).select_from(DraftProjectPackage)) == 0
        row = save(db, actor, draft.id, selected)
        content = packages.package_bytes(db, actor, draft.id, row.id)
        manifest, members = packages.inspect_archive(content)
        assert list(members) == ["artifacts/scope.json"]
        assert json.loads(members["artifacts/scope.json"]) == scopes.read_revision(
            db, actor, draft.id, 2
        )
        assert manifest["capabilities"]["estimate"] == "not_selected"
        assert manifest["authority"] == "historical_only"
        ids = (actor.id, draft.id, row.id)
        with pytest.raises(packages.PackageError, match="REVISION_CONFLICT"):
            packages.create_package(db, actor, draft.id, selected, 0, preview["preview_hash"])
        newer = save(db, actor, draft.id, selected, 1)
        assert newer.parent_hash == row.manifest_hash and newer.revision == 2
        db.commit()
    with setup() as db:
        actor = db.get(User, ids[0])
        assert packages.package_bytes(db, actor, ids[1], ids[2]) == content
        row = db.get(DraftProjectPackage, ids[2])
        row.archive_bytes += b"tampered"
        db.flush()
        with pytest.raises(packages.PackageError, match="INTEGRITY"):
            packages.read_package(db, actor, ids[1], ids[2])


def test_complete_selected_dependencies_rights_and_history(case):
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        match = create(db, case)
        estimate = estimates.create_estimate(
            db, actor, case["draft_id"], 2, match_id=match.id, match_revision=1
        )
        estimates.add_line(db, actor, case["draft_id"], estimate.id, 1, add_payload())
        report = reports.create_report(
            db, actor, case["draft_id"], estimate.id, 2, profile="complete"
        )
        selected = {
            "scope_revision": 2,
            "match_id": match.id,
            "match_revision": 1,
            "estimate_id": estimate.id,
            "estimate_revision": 2,
            "estimate_reports": [report.id],
        }
        before = counts(db)
        row = save(db, actor, case["draft_id"], selected)
        content = packages.package_bytes(db, actor, case["draft_id"], row.id)
        manifest, members = packages.inspect_archive(content)
        assert len(members) == 6
        assert members[f"reports/{report.id}.pdf"] == reports.report_bytes(
            db, actor, case["draft_id"], estimate.id, report.id, "pdf"
        )
        assert any(s["membership"] == "withheld" for s in manifest["source_manifest"])
        after = counts(db)
        assert after.pop("audit_events") == before.pop("audit_events") + 3
        assert after == before
        for changed in [
            {"scope_revision": 1},
            {"match_id": None, "match_revision": None},
            {"estimate_revision": 1},
        ]:
            with pytest.raises(packages.PackageError, match="DEPENDENCIES_DIFFER"):
                packages.preview(db, actor, case["draft_id"], {**selected, **changed})
        old = estimates.read_estimate_revision(db, actor, case["draft_id"], estimate.id)
        estimates.override_line(
            db,
            actor,
            case["draft_id"],
            estimate.id,
            2,
            old["lines"][0]["line_id"],
            {"quantity": "3", "unit_sell_rate": "2", "reason": "Later synthetic change"},
        )
        assert "PACKAGE_ESTIMATE_CHANGED" in packages.staleness(
            db, actor, case["draft_id"], manifest, storage_root=case["storage_root"]
        )
        assert packages.package_bytes(db, actor, case["draft_id"], row.id) == content
        actor.role = "project_manager"
        db.flush()
        with pytest.raises(scopes.DraftScopeError) as exc:
            packages.package_bytes(db, actor, case["draft_id"], row.id)
        assert exc.value.status_code == 403
        assert packages.list_packages(db, actor, case["draft_id"]) == []


@pytest.mark.parametrize(
    "mutation", ["extra", "duplicate", "unsafe", "compressed", "hash", "authority"]
)
def test_archive_rejects_unsafe_or_altered_members(setup, mutation):  # noqa: F811
    with setup() as db:
        actor, draft, _ = prepare(db)
        row = save(db, actor, draft.id, {"scope_revision": 2})
        manifest, members = packages.inspect_archive(row.archive_bytes)
    output = io.BytesIO()
    if mutation == "hash":
        members["artifacts/scope.json"] += b" "
    if mutation == "authority":
        manifest["authority"] = "approved"
    with ZipFile(output, "w", compression=ZIP_DEFLATED if mutation == "compressed" else 0) as z:
        z.writestr("manifest.json", packages.encode(manifest))
        for name, content in members.items():
            z.writestr(name, content)
        if mutation in ("extra", "unsafe", "duplicate"):
            z.writestr(
                {"extra": "extra.txt", "unsafe": "../secret", "duplicate": "manifest.json"}[
                    mutation
                ],
                b"x",
            )
    with pytest.raises(packages.PackageError):
        packages.inspect_archive(output.getvalue())


@pytest.mark.parametrize(
    "value",
    [
        {"scope_revision": True},
        {"scope_revision": 1, "approval": "approved"},
        {"scope_revision": 1, "match_id": uid(1)},
        {"scope_revision": 1, "scope_reports": [uid(1), uid(1)]},
    ],
)
def test_invalid_selection(value):
    with pytest.raises(packages.PackageError):
        packages.selection(value)


def test_caller_rollback_and_changed_preview_leave_no_package(setup):  # noqa: F811
    with setup() as db:
        actor, draft, _ = prepare(db)
        selected = {"scope_revision": 2}
        packages.preview(db, actor, draft.id, selected)
        with pytest.raises(packages.PackageError, match="PREVIEW_CHANGED"):
            packages.create_package(db, actor, draft.id, selected, 0, "0" * 64)
        row = save(db, actor, draft.id, selected)
        identifier = row.id
        db.rollback()
    with setup() as db:
        assert db.get(DraftProjectPackage, identifier) is None
        assert db.scalar(select(func.count()).select_from(DraftProjectPackage)) == 0
