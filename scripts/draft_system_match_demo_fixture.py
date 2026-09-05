"""Explicitly seed a small synthetic library in an isolated SQLite demo.

The document and its approval/clean states are test fixtures, not a scanner verdict
or passive-fire approval. The normal application never invokes this module. The
marked demo launcher must opt in explicitly; callers retain transaction ownership.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from classifire.models import LibraryRelease, StoredFile, TechnicalDocument, TechnicalVariant, User
from classifire.security import has_permission
from classifire.services.release_scope import active_technical_release_ids
from classifire.services.storage import read_verified_stored_file
from classifire.services.technical_release_publication import publish_governed_technical_release

FIXTURE_VERSION = "SYNTHETIC-P2A-001"
FIXTURE_NOTES = (
    "Synthetic candidate-review fixture only. Approved/clean metadata is seeded test state; "
    "no malware scanner, technical assessment or human release is claimed."
)
FIXTURE_DOCUMENT_ID = "SYNTHETIC-P2A-SOURCE-001"
CONSTRAINT_VERSION = "SYNTHETIC-P2B-001"
CONSTRAINT_DOCUMENT_ID = "SYNTHETIC-P2B-SOURCE-001"
SIZE_VERSION = "SYNTHETIC-P2B-SIZE-001"
SIZE_DOCUMENT_ID = "SYNTHETIC-P2B-SIZE-SOURCE-001"


def _document_bytes(*, constraints: bool = False, service_size: bool = False) -> bytes:
    constraints = constraints or service_size
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=A4, invariant=1, pageCompression=1)
    document.setTitle("CLASSIFIRE synthetic candidate-review fixture")
    document.setAuthor("CLASSIFIRE synthetic demo")
    text = document.beginText(44, 790)
    text.setFont("Helvetica-Bold", 14)
    text.textLine("SYNTHETIC FIXTURE - NOT TECHNICAL APPROVAL")
    text.setFont("Helvetica", 10)
    text.setLeading(16)
    for line in (
        "This file exists only to demonstrate source-bound candidate review.",
        "It is not a fire test, assessment, product certificate or installation instruction.",
        "No real passive-fire system or performance claim is represented.",
        (
            "Document reference: SYNTHETIC-P2B-SIZE-SOURCE-001. Revision: DEMO-1."
            if service_size
            else "Document reference: SYNTHETIC-P2B-SOURCE-001. Revision: DEMO-1."
            if constraints
            else "Document reference: SYNTHETIC-P2A-SOURCE-001. Revision: DEMO-1."
        ),
        "",
        "Table 1: Synthetic retrieval fields",
        "Candidate DEMO-PIPE-CONCRETE: service type pipe; substrate concrete.",
        "Candidate DEMO-PIPE-MASONRY: service type pipe; substrate masonry.",
        *(
            (
                "Both synthetic candidates: substrate thickness 100 to 200 mm inclusive.",
                "Annular gap: every measured clearance must be 10 to 30 mm inclusive.",
                "Use the smallest and largest measured gap around the selected service.",
                "Other dimensions, material, FRL and installation limits are unknown.",
            )
            if constraints
            else ("All dimensions, material, FRL, insulation and installation limits are unknown.",)
        ),
        *(
            (
                "Service size: individual round service outside diameter, 10 to 90 mm inclusive.",
                "These fixture limits do not mean nominal diameter, bundle size or duct width.",
                "Compare only recorded outside diameters; instance coverage is unassessed.",
            )
            if service_size
            else ()
        ),
        "Both candidates require evidence and expert review; neither is applicable.",
        "",
        "The application's approved/clean labels are seeded synthetic test metadata.",
        "They do not establish a malware scan, source authenticity or technical approval.",
    ):
        text.textLine(line)
    document.drawText(text)
    document.showPage()
    document.save()
    return buffer.getvalue()


def _existing_fixture(
    db: Session,
    storage_root: Path,
    *,
    constraints: bool = False,
    service_size: bool = False,
) -> LibraryRelease | None:
    constraints = constraints or service_size
    version = (
        SIZE_VERSION if service_size else CONSTRAINT_VERSION if constraints else FIXTURE_VERSION
    )
    document_id = (
        SIZE_DOCUMENT_ID
        if service_size
        else CONSTRAINT_DOCUMENT_ID
        if constraints
        else FIXTURE_DOCUMENT_ID
    )
    releases = list(
        db.scalars(select(LibraryRelease).where(LibraryRelease.library_type == "technical"))
    )
    if not releases:
        return None
    if len(releases) != 1:
        raise ValueError("Refusing to seed a demo over an existing technical library")
    release = releases[0]
    if release.version != version or release.notes != FIXTURE_NOTES:
        raise ValueError("Refusing to adopt a non-fixture technical library")
    ids = active_technical_release_ids(db, release)
    variants = list(db.scalars(select(TechnicalVariant).where(TechnicalVariant.id.in_(ids))))
    if {variant.variant_id for variant in variants} != {"DEMO-PIPE-CONCRETE", "DEMO-PIPE-MASONRY"}:
        raise ValueError("The synthetic library has changed; refusing to reseed it")
    for variant in variants:
        if variant.source_json != {"synthetic_fixture": version}:
            raise ValueError("The synthetic library marker is invalid")
        document = db.get(TechnicalDocument, variant.technical_document_id)
        if document is None or document.document_id != document_id:
            raise ValueError("The synthetic document binding is invalid")
        stored = db.get(StoredFile, document.stored_file_id)
        if stored is None:
            raise ValueError("The synthetic retained source is missing")
        read_verified_stored_file(
            stored, storage_root=storage_root, required_purpose="technical_evidence"
        )
    return release


def seed_demo_library(
    db: Session,
    storage_root: Path,
    actor: User,
    *,
    constraints: bool = False,
    service_size: bool = False,
) -> LibraryRelease:
    """Seed only an explicitly isolated SQLite fixture, or verify its unchanged restart.

    The caller must enforce a marked synthetic demo directory and explicit opt-in.
    An unrelated existing technical catalog is never adopted, modified or replaced.
    No record is represented as a runtime scan result, and no Draft is activated.
    """
    if db.get_bind().dialect.name != "sqlite":
        raise ValueError("Synthetic library seeding requires isolated SQLite demo storage")
    retained_actor = db.get(User, actor.id, populate_existing=True)
    if (
        retained_actor is None
        or not retained_actor.is_active
        or not has_permission(retained_actor, "technical:approve")
    ):
        raise ValueError("Synthetic library seeding requires an active technical approver")
    constraints = constraints or service_size
    storage_root = storage_root.resolve()
    version = (
        SIZE_VERSION if service_size else CONSTRAINT_VERSION if constraints else FIXTURE_VERSION
    )
    document_id = (
        SIZE_DOCUMENT_ID
        if service_size
        else CONSTRAINT_DOCUMENT_ID
        if constraints
        else FIXTURE_DOCUMENT_ID
    )
    existing = _existing_fixture(
        db, storage_root, constraints=constraints, service_size=service_size
    )
    if existing is not None:
        return existing
    if any(
        db.scalar(select(func.count()).select_from(model))
        for model in (TechnicalDocument, TechnicalVariant)
    ):
        raise ValueError("Refusing to seed over existing technical records")
    storage_root.mkdir(parents=True, exist_ok=True)
    content = _document_bytes(constraints=constraints, service_size=service_size)
    digest = hashlib.sha256(content).hexdigest()
    source_path = storage_root / (
        "synthetic-service-size-review-source.pdf"
        if service_size
        else "synthetic-constraint-review-source.pdf"
        if constraints
        else "synthetic-candidate-review-source.pdf"
    )
    if source_path.exists():
        raise ValueError("Refusing to overwrite an existing demo source")
    with source_path.open("xb") as destination:
        destination.write(content)
    stored = StoredFile(
        original_filename=source_path.name,
        media_type="application/pdf",
        storage_path=str(source_path),
        sha256=digest,
        size_bytes=len(content),
        purpose="technical_evidence",
        malware_scan_status="clean",  # Explicit seeded fixture state; no scanner claim.
        immutable=True,
        uploaded_by_id=actor.id,
    )
    db.add(stored)
    db.flush()
    document = TechnicalDocument(
        document_id=document_id,
        stored_file_id=stored.id,
        document_type="synthetic_fixture",
        title="Synthetic candidate-review source - not technical approval",
        reference=document_id,
        revision="DEMO-1",
        status="approved",  # Explicit fixture setup, not a runtime approval workflow.
        approved_by_id=actor.id,
        metadata_json={"synthetic_fixture": version, "scanner_executed": False},
    )
    db.add(document)
    db.flush()
    for suffix, substrate in (("CONCRETE", "concrete"), ("MASONRY", "masonry")):
        db.add(
            TechnicalVariant(
                variant_id=f"DEMO-PIPE-{suffix}",
                system_id=f"SYNTHETIC-SYSTEM-{suffix}",
                technical_document_id=document.id,
                source_document_reference=document_id,
                source_page="1",
                source_table="Table 1: Synthetic retrieval fields",
                manufacturer="Synthetic fixture only",
                service_type="pipe",
                substrate_type=substrate,
                minimum_service_size_mm=10 if service_size else None,
                maximum_service_size_mm=90 if service_size else None,
                minimum_substrate_thickness_mm=100 if constraints else None,
                maximum_substrate_thickness_mm=200 if constraints else None,
                annular_gap_min_mm=10 if constraints else None,
                annular_gap_max_mm=30 if constraints else None,
                expert_review_required=True,
                search_eligibility="INCLUDE",
                status="active",  # Explicit synthetic fixture state.
                source_hash=digest,
                source_json={"synthetic_fixture": version},
            )
        )
    db.flush()
    return publish_governed_technical_release(
        db,
        version=version,
        notes=FIXTURE_NOTES,
        actor=actor,
        storage_root=storage_root,
    )
