"""Seed actual historical schemas through reflected columns, never today's ORM."""

from __future__ import annotations

from sqlalchemy import JSON, MetaData, Table, Text, create_engine, event, inspect, select
from sqlalchemy.orm import Session
from test_draft_estimates import add_payload
from test_draft_project_packages import save
from test_draft_scope import uid
from test_draft_system_matches import create
from test_migrations_physical_foundation import _migration_environment, _upgrade

from classifire.models import DraftPdfSource, DraftPricingSource, StoredFile, User
from classifire.services import draft_estimate_reports as reports
from classifire.services import draft_estimates as estimates
from classifire.services import draft_system_matches as matches


def seed(source, target, *, tables=None):
    """Copy only native fixture rows and only columns that exist at this revision."""
    metadata = MetaData()
    metadata.reflect(target)
    with source.connect() as reader, target.begin() as writer:
        for table in metadata.sorted_tables:
            if table.name == "alembic_version" or (tables is not None and table.name not in tables):
                continue
            source_table = Table(table.name, MetaData(), autoload_with=source)
            # Preserve SQL NULL versus JSON null and exact retained JSON text.
            for column in table.c:
                if isinstance(column.type, JSON):
                    column.type = Text()
                    source_table.c[column.name].type = Text()
            if "import_id" in source_table.c:
                assert (
                    reader.scalar(
                        select(source_table.c.import_id).where(
                            source_table.c.import_id.is_not(None)
                        )
                    )
                    is None
                )
            records = (
                reader.execute(select(*(source_table.c[c.name] for c in table.c))).mappings().all()
            )
            if records:
                writer.execute(table.insert(), [dict(row) for row in records])


def fixture(case, tmp_path, baseline):
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        match = create(db, case)
        estimate = estimates.create_estimate(
            db, actor, case["draft_id"], 2, match_id=match.id, match_revision=1
        )
        estimates.add_line(db, actor, case["draft_id"], estimate.id, 1, add_payload())
        report = reports.create_report(db, actor, case["draft_id"], estimate.id, 2)
        package = save(
            db,
            actor,
            case["draft_id"],
            {
                "scope_revision": 2,
                "match_id": match.id,
                "match_revision": 1,
                "estimate_id": estimate.id,
                "estimate_revision": 2,
                "estimate_reports": [report.id],
            },
        )
        source_ids = {}
        for model, fmt, purpose in (
            (DraftPdfSource, "pdf", "draft_scope_pdf"),
            (DraftPricingSource, "xlsx", "draft_pricing_xlsx"),
        ):
            stored = StoredFile(
                original_filename="synthetic." + fmt,
                storage_path="not-read." + fmt,
                sha256=("a" if fmt == "pdf" else "b") * 64,
                size_bytes=100,
                purpose=purpose,
                malware_scan_status="pending",
                uploaded_by_id=actor.id,
                immutable=True,
            )
            db.add(stored)
            db.flush()
            source = model(
                draft_scope_id=case["draft_id"],
                stored_file_id=stored.id,
                source_sha256=stored.sha256,
                source_size_bytes=100,
                original_filename=stored.original_filename,
                created_by_id=actor.id,
            )
            db.add(source)
            db.flush()
            source_ids[model.__tablename__] = source.id
        expected = {
            "match": matches.revision_bytes(db, actor, case["draft_id"], match.id),
            "estimate": estimates.revision_bytes(db, actor, case["draft_id"], estimate.id),
            "pdf": reports.report_bytes(db, actor, case["draft_id"], estimate.id, report.id, "pdf"),
            "xlsx": reports.report_bytes(
                db, actor, case["draft_id"], estimate.id, report.id, "xlsx"
            ),
            "package": package.archive_bytes,
        }
        identifiers = {
            "draft": case["draft_id"],
            "draft_system_matches": match.id,
            "draft_estimates": estimate.id,
            "draft_estimate_reports": report.id,
            "draft_project_packages": package.id,
            **source_ids,
        }
        db.commit()
        source_engine = db.get_bind()
    url = "sqlite:///" + (tmp_path / "historical.sqlite").as_posix()
    environment = _migration_environment(tmp_path, url)
    _upgrade(url, environment, baseline)
    historical = create_engine(url)

    @event.listens_for(historical, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    seed(source_engine, historical)
    return url, environment, historical, source_engine, identifiers, expected


def verify_current(historical, identifiers, expected):
    with Session(historical) as db:
        actor = db.get(User, uid(100))
        draft = identifiers["draft"]
        assert (
            matches.revision_bytes(db, actor, draft, identifiers["draft_system_matches"])
            == expected["match"]
        )
        assert (
            estimates.revision_bytes(db, actor, draft, identifiers["draft_estimates"])
            == expected["estimate"]
        )
        for fmt in ("pdf", "xlsx"):
            assert (
                reports.report_bytes(
                    db,
                    actor,
                    draft,
                    identifiers["draft_estimates"],
                    identifiers["draft_estimate_reports"],
                    fmt,
                )
                == expected[fmt]
            )
        assert not inspect(historical).get_table_names().count("_alembic_tmp_draft_system_matches")
