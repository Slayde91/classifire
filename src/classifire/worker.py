from __future__ import annotations

import time
from datetime import UTC, datetime

from sqlalchemy import select

from .db import SessionLocal
from .models import BackgroundJob


def run_once() -> bool:
    with SessionLocal() as db:
        job = db.scalar(
            select(BackgroundJob)
            .where(BackgroundJob.status == "queued")
            .order_by(BackgroundJob.created_at)
            .with_for_update(skip_locked=True)
        )
        if not job:
            return False
        job.status = "running"
        job.started_at = datetime.now(UTC)
        job.attempts += 1
        db.commit()
        try:
            # Import and document-processing jobs are intentionally explicit.
            # Add new job handlers here with deterministic inputs and auditable outputs.
            job.result = {"message": "No registered handler", "job_type": job.job_type}
            job.status = "failed"
            job.error = f"No registered handler for {job.job_type}"
        except Exception as exc:  # pragma: no cover - defensive worker boundary
            job.status = "failed"
            job.error = str(exc)
        finally:
            job.finished_at = datetime.now(UTC)
            db.commit()
        return True


def run_forever(interval_seconds: float = 2.0) -> None:
    while True:
        processed = run_once()
        if not processed:
            time.sleep(interval_seconds)
