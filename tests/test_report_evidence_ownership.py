from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from classifire import physical_models  # noqa: F401
from classifire.db import Base
from classifire.models import Estimate, Project, ProjectEvidence, StoredFile
from classifire.services.project_evidence import (
    ProjectEvidenceError,
    bind_project_evidence,
    require_project_evidence_access,
)


@contextmanager
def ownership_session() -> Iterator[Session]:
    engine = create_engine(
        'sqlite+pysqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _project(db: Session, ordinal: int) -> Project:
    project = Project(
        reference=f'PROJECT-EVIDENCE-{ordinal}',
        name=f'Project evidence {ordinal}',
    )
    db.add(project)
    db.flush()
    return project


def _estimate(db: Session, project: Project, ordinal: int) -> Estimate:
    estimate = Estimate(
        project_id=project.id,
        revision=ordinal,
        reference=f'PROJECT-EVIDENCE-ESTIMATE-{ordinal}',
        title=f'Project evidence estimate {ordinal}',
    )
    db.add(estimate)
    db.flush()
    return estimate


def _stored_file(db: Session, ordinal: int, *, purpose: str = 'project_evidence') -> StoredFile:
    stored = StoredFile(
        original_filename=f'report-{ordinal}.pdf',
        media_type='application/pdf',
        storage_path=f'storage/report-{ordinal}.pdf',
        sha256=f'{ordinal:064x}',
        size_bytes=ordinal + 1,
        purpose=purpose,
        malware_scan_status='pending',
        immutable=True,
    )
    db.add(stored)
    db.flush()
    return stored


def test_project_evidence_binding_is_exact_and_idempotent() -> None:
    with ownership_session() as db:
        project = _project(db, 1)
        estimate = _estimate(db, project, 1)
        stored = _stored_file(db, 1)

        first = bind_project_evidence(db, stored_file_id=stored.id, project_id=project.id)
        second = bind_project_evidence(db, stored_file_id=stored.id, project_id=project.id)
        resolved = require_project_evidence_access(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
        )
        resolved_for_estimate = require_project_evidence_access(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
        )

        assert first.id == second.id == resolved.id == resolved_for_estimate.id
        assert resolved.source_sha256 == stored.sha256
        assert resolved.source_size_bytes == stored.size_bytes
        assert db.scalars(select(ProjectEvidence)).all() == [first]


def test_project_evidence_rejects_non_project_evidence_file() -> None:
    with ownership_session() as db:
        project = _project(db, 2)
        stored = _stored_file(db, 2, purpose='technical_evidence')

        with pytest.raises(ProjectEvidenceError) as raised:
            bind_project_evidence(db, stored_file_id=stored.id, project_id=project.id)

    assert raised.value.code == 'PROJECT_EVIDENCE_PURPOSE_FORBIDDEN'


def test_estimate_evidence_rejects_cross_project_and_other_estimate_access() -> None:
    with ownership_session() as db:
        project = _project(db, 3)
        estimate = _estimate(db, project, 3)
        other_estimate = _estimate(db, project, 4)
        other_project = _project(db, 4)
        stored = _stored_file(db, 3)
        evidence = bind_project_evidence(db, stored_file_id=stored.id, estimate_id=estimate.id)

        assert require_project_evidence_access(
            db,
            stored_file_id=stored.id,
            project_id=project.id,
            estimate_id=estimate.id,
        ).id == evidence.id
        with pytest.raises(ProjectEvidenceError) as cross_project:
            require_project_evidence_access(
                db,
                stored_file_id=stored.id,
                project_id=other_project.id,
            )
        with pytest.raises(ProjectEvidenceError) as other_estimate_access:
            require_project_evidence_access(
                db,
                stored_file_id=stored.id,
                project_id=project.id,
                estimate_id=other_estimate.id,
            )

    assert cross_project.value.code == 'PROJECT_EVIDENCE_CROSS_PROJECT_FORBIDDEN'
    assert other_estimate_access.value.code == 'PROJECT_EVIDENCE_ESTIMATE_FORBIDDEN'


def test_project_evidence_rejects_a_conflicting_second_owner() -> None:
    with ownership_session() as db:
        project = _project(db, 5)
        estimate = _estimate(db, project, 5)
        stored = _stored_file(db, 5)
        bind_project_evidence(db, stored_file_id=stored.id, project_id=project.id)

        with pytest.raises(ProjectEvidenceError) as raised:
            bind_project_evidence(db, stored_file_id=stored.id, estimate_id=estimate.id)

    assert raised.value.code == 'PROJECT_EVIDENCE_OWNER_CONFLICT'


def test_project_evidence_database_rule_requires_exactly_one_owner() -> None:
    with ownership_session() as db:
        project = _project(db, 6)
        estimate = _estimate(db, project, 6)
        stored = _stored_file(db, 6)
        db.add(
            ProjectEvidence(
                project_id=project.id,
                estimate_id=estimate.id,
                stored_file_id=stored.id,
                source_sha256=stored.sha256,
                source_size_bytes=stored.size_bytes,
            )
        )

        with pytest.raises(IntegrityError):
            db.flush()


def test_project_evidence_database_rule_requires_positive_source_size() -> None:
    with ownership_session() as db:
        project = _project(db, 7)
        stored = _stored_file(db, 7)
        db.add(
            ProjectEvidence(
                project_id=project.id,
                stored_file_id=stored.id,
                source_sha256=stored.sha256,
                source_size_bytes=0,
            )
        )

        with pytest.raises(IntegrityError):
            db.flush()
