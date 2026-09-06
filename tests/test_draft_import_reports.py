from __future__ import annotations

import io
import json
from dataclasses import replace
from zipfile import ZipFile

import pytest
import xlsxwriter
from sqlalchemy import func, select
from test_draft_pdf_intake import pdf_setup as _pdf_setup
from test_draft_pdf_intake import postgresql_session_factory as _postgres
from test_draft_project_packages import base_case as _base_case
from test_draft_project_packages import case as _case
from test_draft_project_packages import save

from classifire.models import (
    DraftImportedReportSource,
    Estimate,
    Opening,
    Project,
    Service,
    StoredFile,
    User,
)
from classifire.services import draft_estimate_reports as estimate_reports
from classifire.services import draft_estimates as estimates
from classifire.services import draft_import_reports as reports
from classifire.services import draft_package_import as inspection
from classifire.services import draft_package_materialization as imports
from classifire.services import draft_project_packages as packages
from classifire.services import draft_scope_reports as scope_reports
from classifire.services.draft_scope import DraftScopeError
from classifire.services.malware_scan import MalwareScanError
from classifire.services.report_evidence_adapter import _xlsx_archive_is_within_policy

base_case = _base_case
case = _case
pdf_setup = _pdf_setup
postgresql_session_factory = _postgres


def test_report_import_scan_reexport_nested_import_and_sticky_quarantine(pdf_setup, monkeypatch):
    setup = pdf_setup
    monkeypatch.setattr(packages, "get_settings", lambda: setup.settings)
    with setup.factory() as db:
        actor = db.get(User, setup.ids[0])
        scoped = scope_reports.create_report(db, actor, setup.ids[2], 1)
        cost = estimates.create_estimate(db, actor, setup.ids[2], 1)
        reported = estimate_reports.create_report(db, actor, setup.ids[2], cost.id, 1)
        original = save(
            db,
            actor,
            setup.ids[2],
            {
                "scope_revision": 1,
                "estimate_id": cost.id,
                "estimate_revision": 1,
                "scope_reports": [scoped.id],
                "estimate_reports": [reported.id],
            },
        )
        raw = original.archive_bytes
        source_inspection = inspection.inspect_package(raw)
        item = imports.create_import(
            db,
            actor,
            raw,
            expected_sha256=original.archive_hash,
            reference="REPORT-IMPORT",
            name="Imported report project",
            settings=setup.settings,
        )
        draft_id = item.draft_scope_id
        mapping = json.loads(item.mapping_json)
        source_ids = [m["source_id"] for r in mapping["reports"] for m in r["members"].values()]
        assert len(source_ids) == 4
        db.commit()
        with pytest.raises(DraftScopeError):
            reports.original_archive(db, actor, draft_id, settings=setup.settings)
        db.rollback()
        for source_id in source_ids:
            verdict = reports.scan(db, actor, draft_id, source_id, settings=setup.settings)
            assert verdict == {"status": "clean", "processing_error": None}
        db.commit()
        assert reports.original_archive(db, actor, draft_id, settings=setup.settings) == raw
        for report in mapping["reports"]:
            for member in report["members"].values():
                assert reports.download(
                    db, actor, draft_id, member["source_id"], settings=setup.settings
                ) == source_inspection.resolve(member["path"])
        selected = {
            "scope_revision": 2,
            "estimate_id": mapping["estimate"]["local_id"],
            "estimate_revision": 1,
        }
        exported = save(db, actor, draft_id, selected)
        exported_id = exported.id
        assert len(inspection.preview_import(db, actor, exported.archive_bytes)["reports"]) == 2
        assert len(list(inspection.inspect_package(exported.archive_bytes).report_members())) == 2
        second = imports.create_import(
            db,
            actor,
            exported.archive_bytes,
            expected_sha256=exported.archive_hash,
            reference="REPORT-SECOND",
            name="Second imported report project",
            settings=setup.settings,
        )
        second_id = second.draft_scope_id
        second_mapping = json.loads(second.mapping_json)
        second_sources = [
            m["source_id"] for r in second_mapping["reports"] for m in r["members"].values()
        ]
        assert set(second_sources).isdisjoint(source_ids)
        assert db.scalar(select(func.count()).select_from(StoredFile)) == 4
        db.commit()
        with pytest.raises(DraftScopeError):
            reports.original_archive(db, actor, second_id, settings=setup.settings)
        db.rollback()
        for source_id in second_sources:
            assert (
                reports.scan(db, actor, second_id, source_id, settings=setup.settings)[
                    "processing_error"
                ]
                is None
            )
        db.commit()
        assert (
            reports.original_archive(db, actor, second_id, settings=setup.settings)
            == exported.archive_bytes
        )
        # Revoking access cannot be bypassed through an original ZIP or ancestor.
        foreign = db.get(User, setup.ids[1])
        with pytest.raises(DraftScopeError):
            reports.original_archive(db, foreign, draft_id, settings=setup.settings)
        # A later malware verdict is shared across owners and cached package downloads.
        monkeypatch.setattr(
            "classifire.services.malware_scan.scan_bytes",
            lambda data, **kw: replace(setup.clean(data), status="malware_detected"),
        )
        reports.scan(db, actor, second_id, second_sources[0], settings=setup.settings)
        db.commit()
        with pytest.raises(DraftScopeError):
            packages.package_bytes(db, actor, draft_id, exported_id)
        db.rollback()
        monkeypatch.setattr("classifire.services.malware_scan.scan_bytes", setup.clean)
        with pytest.raises(DraftScopeError):
            reports.scan(db, actor, draft_id, source_ids[0], settings=setup.settings)
        db.rollback()
        for model in (Estimate, Opening, Service):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_scan_unavailable_and_mid_import_failure_keep_data_unavailable(pdf_setup, monkeypatch):
    setup = pdf_setup
    with setup.factory() as db:
        actor = db.get(User, setup.ids[0])
        report = scope_reports.create_report(db, actor, setup.ids[2], 1)
        original = save(
            db, actor, setup.ids[2], {"scope_revision": 1, "scope_reports": [report.id]}
        )
        db.commit()
        before = db.scalar(select(func.count()).select_from(Project))
        from classifire.services.draft_source_intake import DraftSourceIntake

        retain = DraftSourceIntake.retain
        calls = []

        def fail_second(self, *args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise DraftScopeError("SYNTHETIC_RETENTION_FAILURE", 409)
            return retain(self, *args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(DraftSourceIntake, "retain", fail_second)
            with pytest.raises(DraftScopeError, match="RETENTION_FAILURE"):
                imports.create_import(
                    db,
                    actor,
                    original.archive_bytes,
                    expected_sha256=original.archive_hash,
                    reference="FAIL",
                    name="Failure rollback",
                    settings=setup.settings,
                )
        assert db.scalar(select(func.count()).select_from(Project)) == before
        assert db.scalar(select(func.count()).select_from(DraftImportedReportSource)) == 0
        item = imports.create_import(
            db,
            actor,
            original.archive_bytes,
            expected_sha256=original.archive_hash,
            reference="PENDING",
            name="Pending scanner",
            settings=setup.settings,
        )
        draft_id = item.draft_scope_id
        source_id = json.loads(item.mapping_json)["reports"][0]["members"]["pdf"]["source_id"]
        db.commit()

        def unavailable(*args, **kwargs):
            raise MalwareScanError("SCAN_NOT_CONFIGURED")

        monkeypatch.setattr("classifire.services.malware_scan.scan_bytes", unavailable)
        assert (
            reports.scan(db, actor, draft_id, source_id, settings=setup.settings)["status"]
            == "not_configured"
        )
        db.commit()
        with pytest.raises(DraftScopeError):
            reports.download(db, actor, draft_id, source_id, settings=setup.settings)


def test_report_worker_refuses_active_content_and_keeps_evidence_policy_strict():
    from reportlab.pdfgen.canvas import Canvas

    out = io.BytesIO()
    canvas = Canvas(out)
    canvas.drawString(30, 700, "Synthetic report")
    canvas.linkURL("https://example.test", (20, 20, 40, 40))
    canvas.save()
    with pytest.raises(DraftScopeError, match="PROCESSING_FAILED"):
        reports._process(out.getvalue(), format_name="pdf")
    out = io.BytesIO()
    with xlsxwriter.Workbook(out, {"in_memory": True}) as workbook:
        sheet = workbook.add_worksheet()
        sheet.write_formula(0, 0, "=1+1")
    with pytest.raises(DraftScopeError, match="PROCESSING_FAILED"):
        reports._process(out.getvalue(), format_name="xlsx")
    from classifire.outputs.draft_branding import supplied_logo_path

    out = io.BytesIO()
    with xlsxwriter.Workbook(out, {"in_memory": True}) as workbook:
        sheet = workbook.add_worksheet()
        sheet.write(0, 0, "Static report with exact CLASSIFIRE logo")
        sheet.insert_image(2, 0, str(supplied_logo_path()))
    raw = out.getvalue()
    assert json.loads(reports._process(raw, format_name="xlsx"))["format"] == "xlsx"
    with pytest.raises(Exception, match="XLSX_FEATURE_FORBIDDEN"):
        _xlsx_archive_is_within_policy(raw)
    with ZipFile(io.BytesIO(raw)) as archive:
        out = io.BytesIO()
        with ZipFile(out, "w") as changed:
            for entry in archive.infolist():
                changed.writestr(entry, archive.read(entry.filename))
            changed.writestr("xl/activeX/control.xml", b"<control/>")
    with pytest.raises(DraftScopeError, match="PROCESSING_FAILED"):
        reports._process(out.getvalue(), format_name="xlsx")


def test_foreign_match_estimate_and_complete_report_import_on_postgresql(
    case, pdf_setup, monkeypatch
):
    from test_draft_estimates import add_payload
    from test_draft_scope import uid
    from test_draft_system_matches import create

    from classifire.models import LibraryRelease
    from classifire.services import draft_system_matches as matches

    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        match = create(db, case)
        cost = estimates.create_estimate(
            db, actor, case["draft_id"], 2, match_id=match.id, match_revision=1
        )
        saved = estimates.add_line(db, actor, case["draft_id"], cost.id, 1, add_payload())
        report = estimate_reports.create_report(
            db, actor, case["draft_id"], cost.id, 2, profile="complete"
        )
        package = save(
            db,
            actor,
            case["draft_id"],
            {
                "scope_revision": 2,
                "match_id": match.id,
                "match_revision": 1,
                "estimate_id": cost.id,
                "estimate_revision": 2,
                "estimate_reports": [report.id],
            },
        )
        raw = package.archive_bytes
    setup = pdf_setup
    monkeypatch.setattr(packages, "get_settings", lambda: setup.settings)
    with setup.factory() as db:
        actor = db.get(User, setup.ids[0])
        item = imports.create_import(
            db,
            actor,
            raw,
            expected_sha256=packages.digest(raw),
            reference="FOREIGN-COMPLETE",
            name="Foreign complete project",
            settings=setup.settings,
        )
        mapping = json.loads(item.mapping_json)
        assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 0
        local = estimates.read_estimate_revision(
            db, actor, item.draft_scope_id, mapping["estimate"]["local_id"]
        )
        assert local["lines"] == saved["lines"] and local["summary"] == saved["summary"]
        assert matches.read_match_revision(
            db, actor, item.draft_scope_id, mapping["match"]["local_id"]
        )["import_origin"]
        for member in mapping["reports"][0]["members"].values():
            assert (
                reports.scan(
                    db, actor, item.draft_scope_id, member["source_id"], settings=setup.settings
                )["processing_error"]
                is None
            )
        # Both new native report profiles accept imported envelopes and show their authority limits.
        fresh = estimate_reports.create_report(
            db, actor, item.draft_scope_id, local["artifact_id"], 1, profile="complete"
        )
        for fmt in ("pdf", "xlsx"):
            assert estimate_reports.report_bytes(
                db, actor, item.draft_scope_id, local["artifact_id"], fresh.id, fmt
            )
        from test_draft_pricing import MAPPING, workbook_bytes

        from classifire.services import draft_pricing_intake as pricing

        source = pricing.intake().retain(
            db,
            actor,
            item.draft_scope_id,
            "local-pricing.xlsx",
            workbook_bytes(),
            settings=setup.settings,
        )
        pricing.intake().scan_source(
            db, actor, item.draft_scope_id, source.id, settings=setup.settings
        )
        _, rows = pricing.preview(
            db, actor, item.draft_scope_id, source.id, 1, 1, MAPPING, settings=setup.settings
        )
        changed = pricing.apply_rate(
            db,
            actor,
            item.draft_scope_id,
            local["artifact_id"],
            1,
            local["lines"][0]["line_id"],
            source.id,
            1,
            1,
            MAPPING,
            rows[0]["row"],
            source.document_sha256,
            rows[0]["sha256"],
            "Explicit local rate selection",
            settings=setup.settings,
        )
        assert changed["schema_version"] == "CLASSIFIRE-DRAFT-ESTIMATE-v3"
        assert changed["content_schema_version"] == "CLASSIFIRE-DRAFT-ESTIMATE-v2"
        assert changed["import_origin"] == local["import_origin"]
        assert changed["lines"][0]["history"][:-1] == local["lines"][0]["history"]
        assert changed["lines"][0]["unit_sell_rate"] == "120.25"
        db.commit()
