from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
from pathlib import Path
import shutil
import sys
import time

from fastapi import UploadFile
from sqlalchemy import select
from starlette.datastructures import Headers

from classifire import canonical_models as _canonical_models  # noqa: F401
from classifire import commercial_models as _commercial_models  # noqa: F401
from classifire.audit import record_audit
from classifire.canonical_models import EvidenceSource
from classifire.config import get_settings
from classifire.db import Base, SessionLocal, engine
from classifire.models import Estimate, LibraryRelease, Project
from classifire.services.release_pinning import pin_current_releases, release_basis_for_estimate
from classifire.services.storage import save_upload


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _active_release(db, library_type: str) -> LibraryRelease | None:
    return db.scalar(
        select(LibraryRelease)
        .where(LibraryRelease.library_type == library_type, LibraryRelease.status == "active")
        .order_by(LibraryRelease.created_at.desc())
    )


def _stage_stored_file(db, source: Path):
    settings = get_settings()
    media_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    with source.open("rb") as handle:
        upload = UploadFile(
            file=handle,
            filename=source.name,
            headers=Headers({"content-type": media_type}),
        )
        return save_upload(db, settings, upload, purpose="project_evidence", user=None)


def prepare(
    report: Path,
    *,
    run_id: str,
    workspace_root: Path,
    project_reference: str | None,
    estimate_reference: str | None,
    project_name: str | None,
    site_address: str | None,
) -> dict:
    report = report.expanduser().resolve()
    if not report.is_file():
        raise FileNotFoundError(f"Real UAT report not found: {report}")
    if report.suffix.lower() != ".pdf":
        raise ValueError("The first real-report UAT currently requires a PDF evidence file.")

    Base.metadata.create_all(bind=engine)
    project_ref = project_reference or f"CF-REAL-UAT-{run_id}"
    estimate_ref = estimate_reference or f"CF-REAL-UAT-{run_id}-R1"
    project_title = project_name or f"CLASSIFIRE real report UAT {run_id}"

    with SessionLocal() as db:
        if db.scalar(select(Project.id).where(Project.reference == project_ref)):
            raise RuntimeError(f"Project reference already exists: {project_ref}")
        if db.scalar(select(Estimate.id).where(Estimate.reference == estimate_ref)):
            raise RuntimeError(f"Estimate reference already exists: {estimate_ref}")

        pricing = _active_release(db, "pricing")
        technical = _active_release(db, "technical")
        if pricing is None or technical is None:
            raise RuntimeError("Active Pricing and Technical runtime releases are required before real UAT.")
        if pricing.version != "2.13-runtime" or technical.version != "2.13-runtime":
            raise RuntimeError(
                "Real UAT requires the verified 2.13-runtime Pricing and Technical releases as the current active basis."
            )

        project = Project(
            reference=project_ref,
            name=project_title,
            site_address=site_address,
            jurisdiction=get_settings().jurisdiction,
            status="active",
        )
        db.add(project)
        db.flush()
        estimate = Estimate(
            project_id=project.id,
            revision=1,
            reference=estimate_ref,
            title=f"Real defect-report acceptance — {report.stem}",
            status="draft",
            currency=get_settings().currency,
            tax_name=get_settings().tax_name,
            tax_rate=get_settings().tax_rate,
        )
        db.add(estimate)
        db.flush()
        release_basis = pin_current_releases(db, estimate)
        stored = _stage_stored_file(db, report)
        evidence = EvidenceSource(
            estimate_id=estimate.id,
            stored_file_id=stored.id,
            evidence_type="source_defect_report",
            source_reference=report.name,
            page_number=None,
            region_reference=None,
            sha256=stored.sha256,
            evidence_class="observed",
            confidence=None,
            status="active",
            source_json={
                "real_uat_run_id": run_id,
                "original_path_name": report.name,
                "intake_role": "system_staging_only",
                "interpretation_performed": False,
            },
        )
        db.add(evidence)
        db.flush()
        record_audit(
            db,
            actor=None,
            actor_type="system",
            actor_name="CLASSIFIRE real UAT preparer",
            action="prepare_real_uat",
            entity_type="estimate",
            entity_id=estimate.id,
            project_id=project.id,
            new_value={
                "report_sha256": stored.sha256,
                "stored_file_id": stored.id,
                "evidence_source_id": evidence.id,
                "release_basis": release_basis,
            },
            reason="Create an empty governed estimate and stage immutable real-report evidence; no technical interpretation performed",
            correlation_id=run_id,
        )
        db.commit()
        basis = release_basis_for_estimate(db, estimate)
        estimate_id = estimate.id
        project_id = project.id
        stored_file_id = stored.id
        evidence_id = evidence.id
        stored_path = Path(stored.storage_path).resolve()
        stored_sha = stored.sha256

    copied: dict[str, str] = {}
    for agent_id in ("cf-intake-evidence", "cf-physical-model"):
        workspace = workspace_root.expanduser().resolve() / agent_id
        if not workspace.is_dir():
            raise RuntimeError(
                f"OpenClaw workspace for {agent_id} was not found at {workspace}. "
                "Run scripts/setup_classifire_openclaw.ps1 or pass --workspace-root."
            )
        target_dir = workspace / "evidence" / run_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / report.name
        shutil.copy2(stored_path, target)
        if sha256_file(target) != stored_sha:
            target.unlink(missing_ok=True)
            raise RuntimeError(f"Workspace evidence hash mismatch for {agent_id}")
        copied[agent_id] = str(target)

    receipt_dir = repo_root() / "data" / "real-uat" / run_id
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema": "CLASSIFIRE-REAL-UAT-PREP-v1",
        "ok": True,
        "run_id": run_id,
        "project_id": project_id,
        "project_reference": project_ref,
        "estimate_id": estimate_id,
        "estimate_reference": estimate_ref,
        "stored_file_id": stored_file_id,
        "source_evidence_id": evidence_id,
        "report_filename": report.name,
        "report_sha256": stored_sha,
        "stored_path": str(stored_path),
        "agent_workspace_evidence": copied,
        "release_basis": basis,
        "prepared_utc": datetime.now(timezone.utc).isoformat(),
        "interpretation_performed": False,
    }
    receipt_path = receipt_dir / "00-prepared.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    receipt["receipt_path"] = str(receipt_path)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare one immutable real defect-report PDF for controlled CLASSIFIRE/OpenClaw acceptance testing."
    )
    parser.add_argument("report", type=Path)
    parser.add_argument("--run-id", default=time.strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--workspace-root", type=Path, default=Path(r"C:\CLASSIFIRE-OpenClaw"))
    parser.add_argument("--project-reference")
    parser.add_argument("--estimate-reference")
    parser.add_argument("--project-name")
    parser.add_argument("--site-address")
    args = parser.parse_args()
    try:
        result = prepare(
            args.report,
            run_id=args.run_id,
            workspace_root=args.workspace_root,
            project_reference=args.project_reference,
            estimate_reference=args.estimate_reference,
            project_name=args.project_name,
            site_address=args.site_address,
        )
        print(json.dumps(result, indent=2, default=str))
        return 0
    except Exception as exc:
        print(f"CLASSIFIRE real UAT preparation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
