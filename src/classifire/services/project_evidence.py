'''Project and Estimate ownership for retained report evidence.'''

from __future__ import annotations

from pathlib import Path
from typing import NoReturn

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Estimate, Project, ProjectEvidence, StoredFile
from .storage import VerifiedStoredFileContent, read_clean_stored_file_for_update

_HEX_SHA256 = frozenset('0123456789abcdef')
_PROJECT_EVIDENCE_PURPOSE = 'project_evidence'


class ProjectEvidenceError(ValueError):
    '''A stable, path-free project-evidence ownership failure.'''

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise ProjectEvidenceError(code)


def _required_id(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f'{field_name.upper()}_INVALID')
    return value


def _normalise_sha256(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.casefold()
        or any(character not in _HEX_SHA256 for character in value)
    ):
        _fail('PROJECT_EVIDENCE_SOURCE_INVALID')
    return value


def _stored_source_binding(stored: StoredFile) -> tuple[str, int]:
    if stored.purpose != _PROJECT_EVIDENCE_PURPOSE:
        _fail('PROJECT_EVIDENCE_PURPOSE_FORBIDDEN')
    if stored.immutable is not True:
        _fail('PROJECT_EVIDENCE_FILE_NOT_IMMUTABLE')
    sha256 = _normalise_sha256(stored.sha256)
    size_bytes = stored.size_bytes
    if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 1:
        _fail('PROJECT_EVIDENCE_SOURCE_INVALID')
    return sha256, size_bytes


def _owner_ids(
    db: Session,
    *,
    project_id: str | None,
    estimate_id: str | None,
) -> tuple[str | None, str | None]:
    if (project_id is None) == (estimate_id is None):
        _fail('PROJECT_EVIDENCE_SINGLE_OWNER_REQUIRED')
    if project_id is not None:
        project_id = _required_id(project_id, field_name='project_id')
        if db.get(Project, project_id) is None:
            _fail('PROJECT_EVIDENCE_PROJECT_NOT_FOUND')
        return project_id, None

    estimate_id = _required_id(estimate_id, field_name='estimate_id')
    if db.get(Estimate, estimate_id) is None:
        _fail('PROJECT_EVIDENCE_ESTIMATE_NOT_FOUND')
    return None, estimate_id


def _same_owner(
    evidence: ProjectEvidence,
    *,
    project_id: str | None,
    estimate_id: str | None,
) -> bool:
    return evidence.project_id == project_id and evidence.estimate_id == estimate_id


def bind_project_evidence(
    db: Session,
    *,
    stored_file_id: str,
    project_id: str | None = None,
    estimate_id: str | None = None,
) -> ProjectEvidence:
    '''Bind one immutable project-evidence file to exactly one owner without commit.'''

    stored_file_id = _required_id(stored_file_id, field_name='stored_file_id')
    owner_project_id, owner_estimate_id = _owner_ids(
        db,
        project_id=project_id,
        estimate_id=estimate_id,
    )
    stored = db.get(StoredFile, stored_file_id)
    if stored is None:
        _fail('PROJECT_EVIDENCE_STORED_FILE_NOT_FOUND')
    source_sha256, source_size_bytes = _stored_source_binding(stored)

    existing = db.scalar(
        select(ProjectEvidence)
        .where(ProjectEvidence.stored_file_id == stored_file_id)
        .execution_options(populate_existing=True)
    )
    if existing is not None:
        if (
            _same_owner(
                existing,
                project_id=owner_project_id,
                estimate_id=owner_estimate_id,
            )
            and existing.source_sha256 == source_sha256
            and existing.source_size_bytes == source_size_bytes
        ):
            return existing
        _fail('PROJECT_EVIDENCE_OWNER_CONFLICT')

    evidence = ProjectEvidence(
        project_id=owner_project_id,
        estimate_id=owner_estimate_id,
        stored_file_id=stored_file_id,
        source_sha256=source_sha256,
        source_size_bytes=source_size_bytes,
    )
    db.add(evidence)
    try:
        db.flush()
    except IntegrityError:
        _fail('PROJECT_EVIDENCE_OWNER_CONFLICT')
    return evidence


def _owner_project_id(db: Session, evidence: ProjectEvidence) -> str:
    if evidence.project_id is not None:
        return evidence.project_id
    if evidence.estimate_id is None:
        _fail('PROJECT_EVIDENCE_OWNER_INVALID')
    estimate = db.get(Estimate, evidence.estimate_id)
    if estimate is None:
        _fail('PROJECT_EVIDENCE_OWNER_INVALID')
    return estimate.project_id


def _require_access(
    db: Session,
    evidence: ProjectEvidence,
    *,
    project_id: str,
    estimate_id: str | None,
) -> None:
    project_id = _required_id(project_id, field_name='project_id')
    if _owner_project_id(db, evidence) != project_id:
        _fail('PROJECT_EVIDENCE_CROSS_PROJECT_FORBIDDEN')
    if estimate_id is None:
        return
    estimate_id = _required_id(estimate_id, field_name='estimate_id')
    estimate = db.get(Estimate, estimate_id)
    if estimate is None:
        _fail('PROJECT_EVIDENCE_ESTIMATE_NOT_FOUND')
    if estimate.project_id != project_id:
        _fail('PROJECT_EVIDENCE_CROSS_PROJECT_FORBIDDEN')
    if evidence.estimate_id is not None and evidence.estimate_id != estimate_id:
        _fail('PROJECT_EVIDENCE_ESTIMATE_FORBIDDEN')


def _require_bound_source(db: Session, evidence: ProjectEvidence) -> StoredFile:
    stored = db.get(StoredFile, evidence.stored_file_id)
    if stored is None:
        _fail('PROJECT_EVIDENCE_STORED_FILE_NOT_FOUND')
    source_sha256, source_size_bytes = _stored_source_binding(stored)
    if (
        evidence.source_sha256 != source_sha256
        or evidence.source_size_bytes != source_size_bytes
    ):
        _fail('PROJECT_EVIDENCE_SOURCE_BINDING_DRIFT')
    return stored


def require_project_evidence_access(
    db: Session,
    *,
    stored_file_id: str,
    project_id: str,
    estimate_id: str | None = None,
) -> ProjectEvidence:
    '''Resolve retained report evidence only within its bound Project context.'''

    stored_file_id = _required_id(stored_file_id, field_name='stored_file_id')
    evidence = db.scalar(
        select(ProjectEvidence)
        .where(ProjectEvidence.stored_file_id == stored_file_id)
        .execution_options(populate_existing=True)
    )
    if evidence is None:
        _fail('PROJECT_EVIDENCE_NOT_FOUND')
    _require_access(
        db,
        evidence,
        project_id=project_id,
        estimate_id=estimate_id,
    )
    _require_bound_source(db, evidence)
    return evidence


def read_project_evidence_for_update(
    db: Session,
    *,
    stored_file_id: str,
    project_id: str,
    storage_root: Path,
    estimate_id: str | None = None,
) -> VerifiedStoredFileContent:
    '''Read exact clean report bytes only after ownership and binding checks.'''

    stored_file_id = _required_id(stored_file_id, field_name='stored_file_id')
    evidence = db.scalar(
        select(ProjectEvidence)
        .where(ProjectEvidence.stored_file_id == stored_file_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if evidence is None:
        _fail('PROJECT_EVIDENCE_NOT_FOUND')
    _require_access(
        db,
        evidence,
        project_id=project_id,
        estimate_id=estimate_id,
    )
    stored = _require_bound_source(db, evidence)
    return read_clean_stored_file_for_update(
        db,
        stored_file_id=stored.id,
        storage_root=storage_root,
        required_purpose=_PROJECT_EVIDENCE_PURPOSE,
    )
