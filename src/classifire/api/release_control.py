from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..config import Settings, get_settings
from ..db import get_db
from ..models import Estimate, User
from ..outputs import render_estimate_pdf, render_proposal_workbook, render_technical_workbook
from ..security import require_permission
from ..services.validated_snapshot import (
    SNAPSHOT_SCHEMA,
    ValidatedSnapshotError,
    lock_validated_snapshot,
)
from ..services.validation import (
    IndependentValidationError,
    latest_passing_gate,
    run_independent_validation,
)
from ..services.workflow import WorkflowAction, WorkflowTransitionError
from ..services.workflow_guard import require_estimate_action

router = APIRouter(prefix="/api/v1", tags=["QUANTIFIRE Validation and Release Control"])
Db = Annotated[Session, Depends(get_db)]


def _estimate(db: Session, estimate_id: str) -> Estimate:
    estimate = db.get(Estimate, estimate_id)
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return estimate


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@router.post("/estimates/{estimate_id}/independent-validation")
def independent_validation(
    estimate_id: str,
    db: Db,
    user: Annotated[User, Depends(require_permission("estimate:approve"))],
) -> dict[str, Any]:
    estimate = _estimate(db, estimate_id)
    try:
        result = run_independent_validation(db, estimate)
    except WorkflowTransitionError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    record_audit(
        db,
        actor=user,
        action="independent_validation",
        entity_type="estimate",
        entity_id=estimate.id,
        project_id=estimate.project_id,
        new_value={
            "gate_evidence_id": result.gate_evidence.id,
            "result": result.gate_evidence.result,
            "state_hash": result.state_hash,
            "exception_count": len(result.issues),
        },
        reason="Deterministic v2.13 final independent validation",
    )
    db.commit()
    return result.as_dict()


@router.post("/estimates/{estimate_id}/lock")
def lock_validated_estimate(
    estimate_id: str,
    reason: str,
    db: Db,
    user: Annotated[User, Depends(require_permission("estimate:approve"))],
) -> dict[str, Any]:
    estimate = _estimate(db, estimate_id)
    try:
        gate = latest_passing_gate(db, estimate)
        snapshot, created = lock_validated_snapshot(db, estimate)
    except (WorkflowTransitionError, IndependentValidationError, ValidatedSnapshotError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    record_audit(
        db,
        actor=user,
        action="lock_validated_snapshot",
        entity_type="estimate",
        entity_id=estimate.id,
        project_id=estimate.project_id,
        new_value={
            "snapshot_hash": snapshot["snapshot_hash"],
            "validation_gate_id": gate.id,
            "certificate_hash": (snapshot.get("estimate_certificate") or {}).get("final_certificate_hash"),
            "created": created,
            "status": "locked",
        },
        reason=reason,
    )
    db.commit()
    return {
        "snapshot_hash": snapshot["snapshot_hash"],
        "validation_gate_id": gate.id,
        "certificate_hash": (snapshot.get("estimate_certificate") or {}).get("final_certificate_hash"),
        "created": created,
        "status": estimate.status,
    }


@router.get("/estimates/{estimate_id}/export/{artifact_type}")
def export_validated_estimate(
    estimate_id: str,
    artifact_type: str,
    db: Db,
    user: Annotated[User, Depends(require_permission("estimate:export"))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    estimate = _estimate(db, estimate_id)
    try:
        require_estimate_action(db, estimate, WorkflowAction.RENDER_OUTPUT)
        gate = latest_passing_gate(db, estimate)
    except (WorkflowTransitionError, IndependentValidationError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    snapshot = estimate.snapshot_json
    if not snapshot or not estimate.snapshot_hash:
        raise HTTPException(status_code=409, detail="Validated snapshot is missing")
    if snapshot.get("schema") != SNAPSHOT_SCHEMA:
        raise HTTPException(status_code=409, detail="Only the canonical v2.13 validated snapshot may be exported")
    certificate_hash = (snapshot.get("estimate_certificate") or {}).get("final_certificate_hash")
    if not certificate_hash:
        raise HTTPException(status_code=409, detail="Validated snapshot has no EstimateCertificate hash")
    if snapshot.get("validation_state_hash") != str(gate.run_id or "").removeprefix("QF-IV:"):
        raise HTTPException(
            status_code=409,
            detail="Validated snapshot does not match the current independent-validation state hash",
        )

    export_dir = settings.storage_root / "exports" / estimate.id / estimate.snapshot_hash
    export_dir.mkdir(parents=True, exist_ok=True)
    safe_ref = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in estimate.reference)
    mapping = {
        "technical-xlsx": (
            f"CLASSIFIRE_{safe_ref}_R{estimate.revision}_Technical_Estimate.xlsx",
            render_technical_workbook,
        ),
        "proposal-xlsx": (
            f"CLASSIFIRE_{safe_ref}_R{estimate.revision}_Proposal.xlsx",
            render_proposal_workbook,
        ),
        "technical-pdf": (
            f"CLASSIFIRE_{safe_ref}_R{estimate.revision}_Technical_Estimate.pdf",
            lambda s, p: render_estimate_pdf(s, p, proposal=False),
        ),
        "proposal-pdf": (
            f"CLASSIFIRE_{safe_ref}_R{estimate.revision}_Proposal.pdf",
            lambda s, p: render_estimate_pdf(s, p, proposal=True),
        ),
    }
    if artifact_type not in mapping:
        raise HTTPException(status_code=404, detail="Unknown artifact type")
    filename, renderer = mapping[artifact_type]
    path = export_dir / filename
    if not path.exists():
        renderer(snapshot, path)
    artifact_hash = _file_sha256(path)

    record_audit(
        db,
        actor=user,
        action="render_output",
        entity_type="estimate",
        entity_id=estimate.id,
        project_id=estimate.project_id,
        new_value={
            "artifact_type": artifact_type,
            "filename": filename,
            "artifact_sha256": artifact_hash,
            "snapshot_hash": estimate.snapshot_hash,
            "validation_gate_id": gate.id,
            "certificate_hash": certificate_hash,
        },
        reason="Render controlled output from validated immutable snapshot",
    )
    db.commit()

    media_type = (
        "application/pdf"
        if path.suffix == ".pdf"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return FileResponse(path, filename=filename, media_type=media_type)
