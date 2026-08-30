from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Estimate, LibraryRelease
from .release_scope import (
    ReleaseScopeError,
    active_technical_release_ids,
    validate_runtime_scope,
)

PIN_FIELDS = {
    "pricing": "pricing_release_id",
    "technical": "technical_release_id",
    "rules": "rules_release_id",
    "products": "products_release_id",
    "labour": "labour_release_id",
    "markups": "markups_release_id",
}
OPTIONAL = {"formulas": "formula_release_id", "brand": "brand_release_id"}


def active_release(db: Session, kind: str) -> LibraryRelease | None:
    return db.scalar(
        select(LibraryRelease)
        .where(
            LibraryRelease.library_type == kind,
            LibraryRelease.status == "active",
        )
        .order_by(LibraryRelease.created_at.desc())
    )


def pin_current_releases(db: Session, estimate: Estimate) -> dict[str, dict[str, str | None]]:
    if (
        estimate.locked_at
        or estimate.snapshot_hash
        or estimate.status not in {"draft", "in_review"}
    ):
        raise ValueError("Release basis can only be refreshed while estimate is editable")

    basis = {kind: active_release(db, kind) for kind in PIN_FIELDS}
    missing = [kind for kind, release in basis.items() if release is None]
    if missing:
        raise ValueError("Missing active releases: " + ", ".join(sorted(missing)))

    technical_release = basis["technical"]
    if technical_release is None:
        raise ValueError("Missing active releases: technical")
    try:
        active_technical_release_ids(db, technical_release)
    except ReleaseScopeError as exc:
        raise ValueError(str(exc)) from exc

    result: dict[str, dict[str, str | None]] = {}
    pinned_at = datetime.now(UTC).isoformat()
    for kind, field in PIN_FIELDS.items():
        release = basis[kind]
        if release is None:
            raise ValueError(f"Missing active releases: {kind}")
        setattr(estimate, field, release.id)
        result[kind] = {
            "release_id": release.id,
            "version": release.version,
            "hash": release.release_hash,
            "effective_date": (
                release.effective_date.isoformat() if release.effective_date else None
            ),
            "status": release.status,
            "pinned_at": pinned_at,
        }
    return result


def release_basis_for_estimate(
    db: Session, estimate: Estimate
) -> dict[str, dict[str, object] | None]:
    result: dict[str, dict[str, object] | None] = {}
    for kind, field in {**PIN_FIELDS, **OPTIONAL}.items():
        release_id = getattr(estimate, field, None)
        release = db.get(LibraryRelease, release_id) if release_id else None
        result[kind] = (
            None
            if not release_id
            else {
                "release_id": release_id,
                "version": release.version if release else "Missing release record",
                "hash": release.release_hash if release else None,
                "effective_date": release.effective_date if release else None,
                "status": release.status if release else "missing",
            }
        )
    return result


def validate_estimate_release_basis(db: Session, estimate: Estimate) -> list[str]:
    errors: list[str] = []
    for kind, field in PIN_FIELDS.items():
        release_id = getattr(estimate, field, None)
        if not release_id:
            errors.append(f"{kind}: no release pinned")
            continue
        release = db.get(LibraryRelease, release_id)
        if not release:
            errors.append(f"{kind}: pinned release missing")
        elif not release.release_hash:
            errors.append(f"{kind}: pinned release has no hash")
    errors.extend(validate_runtime_scope(db, estimate))
    return list(dict.fromkeys(errors))
