from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from classifire import models, physical_models  # noqa: F401
from classifire.db import Base
from classifire.models import Estimate, Opening, Project, Service, StoredFile
from classifire.physical_models import EvidenceSource, ServiceOpeningLink
from classifire.services.physical_defects import bind_canonical_defect


@contextmanager
def physical_session() -> Iterator[Session]:
    """Create an isolated, in-memory canonical physical-model database."""
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with TemporaryDirectory(prefix="classifire-physical-test-") as retained_root:
        session = Session(engine)
        session.info["retained_storage_root"] = Path(retained_root)
        try:
            yield session
        finally:
            session.close()
            engine.dispose()


def add_estimate(session: Session, *, status: str = "draft") -> Estimate:
    project = Project(reference="PHYS-TEST-PROJECT", name="Physical foundation test")
    session.add(project)
    session.flush()

    estimate = Estimate(
        project_id=project.id,
        reference="PHYS-TEST-ESTIMATE",
        title="Physical foundation test estimate",
        status=status,
    )
    session.add(estimate)
    session.flush()
    return estimate


def add_opening(
    session: Session,
    estimate: Estimate,
    *,
    opening_code: str = "OP-001",
    opening_type: str = "service penetration",
    defect_id: str | None = "D-001",
) -> Opening:
    defect = bind_canonical_defect(session, estimate, defect_id)
    opening = Opening(
        estimate_id=estimate.id,
        opening_code=opening_code,
        defect_id=defect_id,
        canonical_defect_id=defect.id if defect else None,
        opening_type=opening_type,
        substrate_type="concrete",
        substrate_plane="wall",
        orientation="horizontal",
        frl="-/120/120",
    )
    session.add(opening)
    session.flush()
    return opening


def add_service(
    session: Session,
    opening: Opening,
    *,
    service_code: str = "SVC-001",
    material: str | None = "PVC",
) -> Service:
    service = Service(
        opening_id=opening.id,
        service_code=service_code,
        service_type="pipe",
        material=material,
        nominal_size_mm=Decimal("100"),
    )
    session.add(service)
    session.flush()
    return service


def add_service_link(session: Session, service: Service, opening: Opening) -> ServiceOpeningLink:
    link = ServiceOpeningLink(
        service_id=service.id,
        opening_id=opening.id,
        evidence_status="confirmed",
        confidence=Decimal("0.95"),
    )
    session.add(link)
    session.flush()
    return link


def add_evidence(session: Session, estimate: Estimate) -> EvidenceSource:
    payload = b"controlled physical-model evidence bytes"
    digest = hashlib.sha256(payload).hexdigest()
    storage_root = session.info.get("retained_storage_root")
    if not isinstance(storage_root, Path):
        raise AssertionError("physical_session must provide retained storage")
    retained_path = storage_root / f"{digest}.jpg"
    retained_path.write_bytes(payload)
    stored = session.scalar(select(StoredFile).where(StoredFile.sha256 == digest))
    if stored is None:
        stored = StoredFile(
            original_filename="test-report-page-1.jpg",
            media_type="image/jpeg",
            storage_path=str(retained_path),
            sha256=digest,
            size_bytes=len(payload),
            purpose="technical_evidence",
            malware_scan_status="clean",
            immutable=True,
        )
        session.add(stored)
        session.flush()
    evidence = EvidenceSource(
        estimate_id=estimate.id,
        stored_file_id=stored.id,
        evidence_type="inspection_photo",
        source_reference="test-report-page-1",
        sha256=digest,
        evidence_class="observed",
        confidence=Decimal("0.95"),
    )
    session.add(evidence)
    session.flush()
    return evidence
