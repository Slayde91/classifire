from __future__ import annotations

import hashlib
import io
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from pypdf import PdfReader
from sqlalchemy import func, select
from test_draft_client import confirm, tool
from test_draft_client_capabilities import capability_case as _capability_case
from test_draft_client_capabilities import (  # noqa: F401
    client_case,
    propose,
    read,
    saved,
    scope_app,
    scope_password_hash,
)
from test_draft_constraint_review import inputs
from test_draft_scope import uid
from test_draft_scope_ui import _app, _assert_no_canonical_scope, _csrf, _login
from test_draft_service_size_review import size_inputs

from classifire.config import Settings
from classifire.draft_client import configure
from classifire.draft_client_auth import ESTIMATE, EXPORT, READ, TECHNICAL, WRITE
from classifire.models import (
    DraftClientRequest,
    DraftSystemMatch,
    StoredFile,
    TechnicalDocument,
    TechnicalVariant,
    User,
)
from classifire.services import draft_package_materialization as imports
from classifire.services import draft_project_packages as packages
from classifire.services.technical_release_publication import publish_governed_technical_release

capability_case = _capability_case
CONSTRAINTS = "review_match_constraints"
SERVICE_SIZE = "review_match_service_size"


@pytest.fixture
def measurement_case(capability_case):
    c = capability_case
    with c.scope.factory() as db:
        variant = db.get(TechnicalVariant, c.variant_id)
        variant.minimum_substrate_thickness_mm = 100
        variant.maximum_substrate_thickness_mm = 200
        variant.annular_gap_min_mm = 10
        variant.annular_gap_max_mm = 30
        variant.minimum_service_size_mm = 10
        variant.maximum_service_size_mm = 90
        document = db.get(TechnicalDocument, variant.technical_document_id)
        stored = db.get(StoredFile, document.stored_file_id)
        c.source_path, c.stored_id = Path(stored.storage_path), stored.id
        c.storage = c.source_path.parent
        release = publish_governed_technical_release(
            db,
            version="CLIENT-SYNTHETIC-MEASUREMENTS",
            notes="Synthetic bounded measurement fixture only",
            actor=db.get(User, c.scope.users["admin"]),
            storage_root=c.storage,
        )
        c.release_id = release.id
        db.commit()
    return c


def create_match(client, c, *, opening_id=uid(2)):
    return saved(
        client,
        c,
        propose(
            client,
            c,
            "create_match",
            scope_revision=2,
            release_id=c.release_id,
            opening_id=opening_id,
            service_id=uid(5),
        ),
    )["match_id"]


def review_args(c, match, action=CONSTRAINTS, revision=1, **overrides):
    return {
        "draft_id": c.draft_id,
        "action": action,
        "match_id": match,
        "expected_revision": revision,
        "candidate_id": c.variant_id,
        "inputs": size_inputs() if action == SERVICE_SIZE else inputs(),
        **overrides,
    }


def pending_review(client, c, match, action=CONSTRAINTS, revision=1, **overrides):
    return tool(
        client,
        c.full_token(),
        "propose_capability",
        {"operation": review_args(c, match, action, revision, **overrides)},
    )


def unchanged(c, match, pending, revision=1):
    with c.scope.factory() as db:
        assert db.get(DraftSystemMatch, match).latest_revision == revision
        assert db.get(DraftClientRequest, pending["request_id"]).status == "pending"


def test_measured_client_review_is_human_confirmed_and_retained_in_exact_reports(measurement_case):
    c = measurement_case
    with TestClient(c.scope.app, base_url="https://testserver") as client:
        _login(client)
        match = create_match(client, c)
        first = read(client, c, "system-match", match)["artifact"]
        rejected = pending_review(client, c, match)
        unchanged(c, match, rejected)
        confirm(client, rejected, decision="reject")
        assert read(client, c, "system-match", match)["artifact"] == first
        assert (
            tool(
                client,
                c.full_token(),
                "read_client_request",
                {"request_id": rejected["request_id"]},
            )["status"]
            == "rejected"
        )

        pending = pending_review(client, c, match)
        page = client.get(pending["review_url"])
        assert page.status_code == 200 and inputs()["measurement_note"] in page.text
        assert not re.search(r'<form[^>]+action="[^"]*/constraints"', page.text)
        unchanged(c, match, pending)
        saved(client, c, pending)
        second = read(client, c, "system-match", match)["artifact"]
        assert second["schema_version"] == "CLASSIFIRE-DRAFT-SYSTEM-MATCH-v2"
        assert second["parent_hash"] == first["sha256"]
        assert second["constraint_review"]["inputs"] == inputs()
        assert [check["status"] for check in second["constraint_review"]["checks"]] == [
            "within_limits"
        ] * 2

        pending = pending_review(client, c, match, SERVICE_SIZE, 2)
        page = client.get(pending["review_url"])
        assert "Saved measurement review" in page.text
        assert "Within limits" in page.text
        assert not re.search(r'<form[^>]+action="[^"]*/constraints"', page.text)
        unchanged(c, match, pending, 2)
        saved(client, c, pending)
        third = read(client, c, "system-match", match)["artifact"]
        assert third["schema_version"] == "CLASSIFIRE-DRAFT-SYSTEM-MATCH-v3"
        assert third["parent_hash"] == second["sha256"]
        review = third["constraint_review"]
        assert review["inputs"] == size_inputs()
        assert [check["status"] for check in review["checks"]] == ["within_limits"] * 3
        assert review["status"] == "partial_unapproved"
        assert review["reviewed_by"] == c.scope.users["owner"] and review["reviewed_at"]
        assert review["unassessed"] and third["review_status"] == "unreviewed"
        detail = f"/scopes/{c.draft_id}/system-matches/{match}"
        assert client.get(detail + "/download").json() == third
        assert "Measured service outside diameter range" in client.get(detail).text

        estimate = saved(
            client,
            c,
            propose(
                client, c, "create_estimate", scope_revision=2, match_id=match, match_revision=3
            ),
        )["estimate_id"]
        reports = []
        for action, args, kind, parent in (
            (
                "scope_report",
                {"scope_revision": 2, "match_id": match, "match_revision": 3},
                "scope-report",
                None,
            ),
            (
                "estimate_report",
                {"estimate_id": estimate, "estimate_revision": 1, "profile": "complete"},
                "estimate-report",
                estimate,
            ),
        ):
            report = saved(client, c, propose(client, c, action, **args))["report_id"]
            snapshot = read(client, c, kind, report, estimate_id=parent)["artifact"]
            selected = snapshot["estimate"]["system_match"] if parent else snapshot["system_match"]
            assert selected == third
            for fmt in ("pdf", "xlsx"):
                info = tool(
                    client,
                    c.full_token(),
                    "report_download",
                    {
                        "draft_id": c.draft_id,
                        "report_id": report,
                        "format_name": fmt,
                        "estimate_id": parent,
                    },
                )
                response = client.get(
                    info["authenticated_url"], headers={"Authorization": "Bearer " + c.full_token()}
                )
                assert response.status_code == 200
                assert hashlib.sha256(response.content).hexdigest() == info["sha256"]
                assert client.get(info["browser_url"]).content == response.content
                if fmt == "pdf":
                    text = "\n".join(
                        page.extract_text()
                        for page in PdfReader(io.BytesIO(response.content)).pages
                    )
                    assert "Measured Service Outside Diameter Range" in text
                else:
                    workbook = load_workbook(io.BytesIO(response.content), data_only=False)
                    values = [
                        str(cell.value)
                        for sheet in workbook
                        for row in sheet
                        for cell in row
                        if cell.value is not None
                    ]
                    assert "measured_service_outside_diameter_range" in values
                    assert "outside_diameter" in values
                    workbook.close()
                reports.append((info, response.content))

        saved(
            client,
            c,
            pending_review(client, c, match, SERVICE_SIZE, 3, inputs=size_inputs(high="90.0001")),
        )
        latest = read(client, c, "system-match", match)["artifact"]
        assert latest["constraint_review"]["checks"][2]["status"] == "outside_limits"
        assert read(client, c, "system-match", match, revision=1)["artifact"] == first
        assert read(client, c, "system-match", match, revision=2)["artifact"] == second
        assert read(client, c, "system-match", match, revision=3)["artifact"] == third
        assert read(client, c, "estimate", estimate)["staleness"]
        for info, content in reports:
            assert client.get(info["browser_url"]).content == content

    app = _app(c.scope.factory)
    mounted = configure(app, c.authority, c.scope.factory)

    @asynccontextmanager
    async def lifespan(app):
        async with mounted.router.lifespan_context(mounted):
            yield

    app.router.lifespan_context = lifespan
    with TestClient(app, base_url="https://testserver") as restarted:
        assert read(restarted, c, "system-match", match)["artifact"] == latest
        assert read(restarted, c, "system-match", match, revision=3)["artifact"] == third
        for info, content in reports:
            assert (
                restarted.get(
                    info["authenticated_url"], headers={"Authorization": "Bearer " + c.full_token()}
                ).content
                == content
            )
    _assert_no_canonical_scope(c.scope.factory)


def test_client_measurement_inputs_reject_coercion_and_invalid_semantics(measurement_case):
    c = measurement_case
    with TestClient(c.scope.app, base_url="https://testserver") as client:
        _login(client)
        match = create_match(client, c)
        with c.scope.factory() as db:
            before = db.scalar(select(func.count()).select_from(DraftClientRequest))
        invalid = [
            (CONSTRAINTS, inputs(thickness=value))
            for value in (0, True, "0", "NaN", "1e2", "1.12345")
        ] + [
            (CONSTRAINTS, inputs(low="31", high="30")),
            (CONSTRAINTS, {**inputs(), "measurement_note": " "}),
            (
                CONSTRAINTS,
                {key: value for key, value in inputs().items() if key != "annular_gap_max_mm"},
            ),
            (CONSTRAINTS, {**inputs(), "approval": True}),
            (SERVICE_SIZE, size_inputs(low="91", high="90")),
            (SERVICE_SIZE, size_inputs(low="0")),
            (SERVICE_SIZE, size_inputs(source="automatic")),
            (SERVICE_SIZE, inputs()),
            (CONSTRAINTS, size_inputs()),
        ]
        for action, values in invalid:
            tool(
                client,
                c.full_token(),
                "propose_capability",
                {"operation": review_args(c, match, action, inputs=values)},
                error=True,
            )
        with c.scope.factory() as db:
            assert db.scalar(select(func.count()).select_from(DraftClientRequest)) == before
            assert db.get(DraftSystemMatch, match).latest_revision == 1


@pytest.mark.parametrize("action", [CONSTRAINTS, SERVICE_SIZE])
def test_measured_review_requires_current_scope_owner_role_and_unreplayed_request(
    measurement_case, action
):
    c = measurement_case
    with TestClient(c.scope.app, base_url="https://testserver") as client:
        _login(client)
        match = create_match(client, c)
        operation = {"operation": review_args(c, match, action)}
        assert "CLIENT_AUTHORIZATION_REQUIRED" in str(
            tool(client, c.token(), "propose_capability", operation, error=True)
        )
        foreign = c.token(user="admin", scope=" ".join([READ, WRITE, EXPORT, TECHNICAL, ESTIMATE]))
        assert "DRAFT_NOT_FOUND" in str(
            tool(client, foreign, "propose_capability", operation, error=True)
        )
        pending = pending_review(client, c, match, action)
        stale = pending_review(client, c, match, action)
        page = client.get(pending["review_url"])
        digest = re.search(r'name="payload_hash" value="([^"]+)"', page.text).group(1)
        saved(client, c, pending)
        assert (
            client.post(
                pending["review_url"],
                data={
                    "csrf_token": _csrf(page.text),
                    "payload_hash": digest,
                    "decision": "confirm",
                },
            ).status_code
            == 409
        )
        assert client.get(stale["review_url"]).status_code == 409
        unchanged(c, match, stale, 2)

        current = pending_review(client, c, match, action, 2)
        with c.scope.factory() as db:
            db.get(User, c.scope.users["owner"]).role = "project_manager"
            db.commit()
        assert client.get(current["review_url"]).status_code == 403
        # Completed history must not disclose saved technical inputs after role removal.
        assert client.get(pending["review_url"]).status_code == 403
        receipt = tool(
            client,
            c.full_token(),
            "read_client_request",
            {"request_id": pending["request_id"]},
        )
        assert "payload" not in receipt and "operation" not in receipt
        assert inputs()["measurement_note"] not in json.dumps(receipt)
        tool(
            client,
            c.full_token(),
            "read_capability_artifact",
            {"draft_id": c.draft_id, "kind": "system-match", "artifact_id": match},
            error=True,
        )
        with c.scope.factory() as db:
            db.get(User, c.scope.users["owner"]).role = "estimator"
            db.commit()
        c.policy["clients"]["synthetic-client"].remove(TECHNICAL)
        c.path.write_text(json.dumps(c.policy), encoding="utf-8")
        assert client.get(current["review_url"]).status_code == 403
        c.policy["clients"]["synthetic-client"].append(TECHNICAL)
        c.policy["revoked_token_ids"] = ["synthetic-token"]
        c.path.write_text(json.dumps(c.policy), encoding="utf-8")
        assert client.get(current["review_url"]).status_code == 403
        unchanged(c, match, current, 2)


@pytest.mark.parametrize("change", ["bytes", "quarantine", "published_limits"])
def test_measured_confirmation_rechecks_current_source_and_rolls_back(measurement_case, change):
    c = measurement_case
    with TestClient(c.scope.app, base_url="https://testserver") as client:
        _login(client)
        match = create_match(client, c)
        pending = pending_review(client, c, match, SERVICE_SIZE)
        with c.scope.factory() as db:
            if change == "bytes":
                c.source_path.write_bytes(b"changed synthetic source")
            elif change == "quarantine":
                db.get(StoredFile, c.stored_id).malware_scan_status = "malware_detected"
            else:
                db.get(TechnicalVariant, c.variant_id).minimum_substrate_thickness_mm = 99
            db.commit()
        response = confirm(client, pending, status=409 if change == "bytes" else 422)
        assert (
            "MATCH_BASIS_STALE" if change == "bytes" else "MATCH_RELEASE_INVALID"
        ) in response.text
        unchanged(c, match, pending)


def test_measured_v3_cannot_be_downgraded_and_unknown_candidates_fail_atomically(measurement_case):
    c = measurement_case
    with TestClient(c.scope.app, base_url="https://testserver") as client:
        _login(client)
        match = create_match(client, c)
        invalid = pending_review(client, c, match, candidate_id=uid(999))
        assert "MATCH_CANDIDATE_INVALID" in confirm(client, invalid, status=422).text
        unchanged(c, match, invalid)
        saved(client, c, pending_review(client, c, match, SERVICE_SIZE))
        downgrade = pending_review(client, c, match, revision=2)
        assert "MATCH_MEASUREMENT_VERSION_REQUIRED" in confirm(client, downgrade, status=422).text
        unchanged(c, match, downgrade, 2)


def test_imported_match_cannot_gain_local_measurement_authority(measurement_case):
    c = measurement_case
    with TestClient(c.scope.app, base_url="https://testserver") as client:
        _login(client)
        match = create_match(client, c)
        with c.scope.factory() as db:
            actor = db.get(User, c.scope.users["owner"])
            selection = {"scope_revision": 2, "match_id": match, "match_revision": 1}
            preview = packages.preview(db, actor, c.draft_id, selection)
            package = packages.create_package(
                db,
                actor,
                c.draft_id,
                selection,
                preview["latest_revision"],
                preview["preview_hash"],
            )
            imported = imports.create_import(
                db,
                actor,
                package.archive_bytes,
                expected_sha256=package.archive_hash,
                reference="CLIENT-FOREIGN",
                name="Synthetic foreign Match",
                settings=Settings(storage_root=c.storage),
            )
            c.draft_id = imported.draft_scope_id
            match = json.loads(imported.mapping_json)["match"]["local_id"]
            db.commit()
        pending = pending_review(client, c, match, SERVICE_SIZE)
        assert "MATCH_FOREIGN_SOURCE_UNVERIFIED" in confirm(client, pending, status=409).text
        unchanged(c, match, pending)
