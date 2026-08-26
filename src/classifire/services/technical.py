from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import (
    Opening,
    StoredFile,
    TechnicalDocument,
    TechnicalVariant,
)
from .release_scope import pinned_technical_ids
from .storage import StoredFileSecurityError, require_clean_stored_file_for_session


@dataclass(frozen=True)
class Candidate:
    variant: TechnicalVariant
    score: Decimal
    comparisons: dict[str, str]
    blockers: list[str]


def _normal(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", (value or "").upper()).strip()


def _compare(project_value: str | None, candidate_value: str | None) -> str:
    p, c = _normal(project_value), _normal(candidate_value)
    if not p or not c or "NOT STATED" in c or "UNKNOWN" in c:
        return "UNKNOWN"
    if p == c or p in c or c in p:
        return "MATCH"
    p_tokens, c_tokens = set(p.split()), set(c.split())
    return "MATCH" if p_tokens and len(p_tokens & c_tokens) / len(p_tokens) >= 0.6 else "MISMATCH"


def governed_unlinked_technical_source(db: Session, variant: TechnicalVariant) -> bool:
    """Keep unlinked release records as history, never runtime evidence."""

    return False


def _linked_source_is_admissible(
    db: Session,
    variant: TechnicalVariant,
    cache: dict[str, bool],
) -> bool:
    document_id = variant.technical_document_id
    if document_id is None:
        return governed_unlinked_technical_source(db, variant)
    if document_id in cache:
        return cache[document_id]
    document = db.get(TechnicalDocument, document_id)
    stored = db.get(StoredFile, document.stored_file_id) if document is not None else None
    admissible = document is not None and document.status == "approved" and stored is not None
    if admissible and stored is not None:
        try:
            require_clean_stored_file_for_session(
                db,
                stored,
                allowed_purposes={"technical_evidence"},
            )
        except StoredFileSecurityError:
            admissible = False
    cache[document_id] = admissible
    return admissible


def search_variants(
    db: Session,
    *,
    service_type: str | None = None,
    service_material: str | None = None,
    substrate: str | None = None,
    orientation: str | None = None,
    frl: str | None = None,
    limit: int = 20,
    include_draft: bool = False,
    release_record_ids: set[str] | None = None,
    _source_admissibility_cache: dict[str, bool] | None = None,
) -> list[Candidate]:
    if release_record_ids is not None:
        stmt = select(TechnicalVariant).where(TechnicalVariant.id.in_(release_record_ids))
    else:
        statuses = ["active"] if not include_draft else ["active", "draft", "in_review"]
        stmt = select(TechnicalVariant).where(TechnicalVariant.status.in_(statuses))
    # Broad SQL prefilter; final matching remains explicit and auditable.
    if service_type:
        stmt = stmt.where(or_(TechnicalVariant.service_type.ilike(f"%{service_type}%"), TechnicalVariant.service_type.is_(None)))
    if service_material:
        stmt = stmt.where(or_(TechnicalVariant.service_material.ilike(f"%{service_material}%"), TechnicalVariant.service_material.is_(None)))
    if frl:
        stmt = stmt.where(or_(TechnicalVariant.frl == frl, TechnicalVariant.frl.is_(None)))
    variants = db.scalars(stmt.limit(max(limit * 10, 100))).all()
    source_admissibility_cache = (
        _source_admissibility_cache
        if _source_admissibility_cache is not None
        else {}
    )
    candidates: list[Candidate] = []
    for variant in variants:
        if not _linked_source_is_admissible(db, variant, source_admissibility_cache):
            continue
        comparisons = {
            "service_type": _compare(service_type, variant.service_type),
            "service_material": _compare(service_material, variant.service_material),
            "substrate": _compare(substrate, variant.substrate_type),
            "orientation": _compare(orientation, variant.orientation),
            "frl": _compare(frl, variant.frl),
        }
        blockers: list[str] = []
        if "MISMATCH" in comparisons.values():
            blockers.append("critical_field_mismatch")
        if variant.expert_review_required:
            blockers.append("expert_review_required")
        if variant.search_eligibility and "EXCLUDE" in variant.search_eligibility.upper():
            blockers.append("search_excluded")
        matches = sum(value == "MATCH" for value in comparisons.values())
        unknowns = sum(value == "UNKNOWN" for value in comparisons.values())
        quality = Decimal(str(variant.quality_score or 0))
        score = quality * Decimal("0.45") + Decimal(matches * 11) - Decimal(unknowns * 3)
        if blockers and "critical_field_mismatch" in blockers:
            score -= Decimal("100")
        cap = Decimal(str(variant.confidence_cap or 75))
        score = min(score, cap)
        candidates.append(Candidate(variant=variant, score=score, comparisons=comparisons, blockers=blockers))
    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates[:limit]


def search_for_opening(db: Session, opening: Opening, limit: int = 20) -> dict[str, Any]:
    allowed_ids = pinned_technical_ids(db, opening.estimate)
    per_service: list[dict[str, Any]] = []
    source_admissibility_cache: dict[str, bool] = {}
    for service in opening.services:
        candidates = search_variants(
            db,
            service_type=service.service_type,
            service_material=service.material,
            substrate=opening.substrate_type,
            orientation=opening.orientation,
            frl=opening.frl,
            limit=limit,
            release_record_ids=allowed_ids,
            _source_admissibility_cache=source_admissibility_cache,
        )
        per_service.append(
            {
                "service_id": service.id,
                "service_code": service.service_code,
                "candidates": [
                    {
                        "variant_id": c.variant.variant_id,
                        "system_id": c.variant.system_id,
                        "score": str(c.score),
                        "comparisons": c.comparisons,
                        "blockers": c.blockers,
                        "source_document": c.variant.source_document_reference,
                        "source_page": c.variant.source_page,
                    }
                    for c in candidates
                ],
            }
        )
    return {
        "opening_id": opening.id,
        "opening_code": opening.opening_code,
        "status": "candidates_only_human_approval_required",
        "services": per_service,
    }


def mixed_service_candidate_available(db: Session, opening: Opening) -> dict[str, Any]:
    service_terms = {_normal(s.service_type) for s in opening.services}
    if len(service_terms) < 2:
        return {"available": False, "reason": "opening_is_not_mixed_service"}
    allowed_ids = pinned_technical_ids(db, opening.estimate)
    stmt = select(TechnicalVariant).where(
        TechnicalVariant.id.in_(allowed_ids),
        or_(
            TechnicalVariant.service_type.ilike("%mixed%"),
            TechnicalVariant.product_family.ilike("%mixed%"),
        ),
    )
    variants = db.scalars(stmt.limit(50)).all()
    supported: list[dict[str, Any]] = []
    source_admissibility_cache: dict[str, bool] = {}
    for variant in variants:
        if not _linked_source_is_admissible(db, variant, source_admissibility_cache):
            continue
        substrate_match = _compare(opening.substrate_type, variant.substrate_type)
        frl_match = _compare(opening.frl, variant.frl)
        if substrate_match != "MISMATCH" and frl_match != "MISMATCH":
            supported.append(
                {
                    "variant_id": variant.variant_id,
                    "system_id": variant.system_id,
                    "source_document": variant.source_document_reference,
                    "source_page": variant.source_page,
                    "expert_review_required": variant.expert_review_required,
                }
            )
    return {
        "available": bool(supported),
        "candidates": supported,
        "reason": "approved_candidate_requires_exact_configuration_review" if supported else "no_active_candidate_found",
    }


def extract_pdf_candidate_metadata(path: Path) -> dict[str, Any]:
    """Extract only candidate metadata. The result is never approved automatically."""
    reader = PdfReader(str(path))
    text_parts: list[str] = []
    pages: list[dict[str, Any]] = []
    for index, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        text_parts.append(text)
        pages.append({"page": index + 1, "characters": len(text)})
    text = "\n".join(text_parts)
    report_refs = sorted(set(re.findall(r"\b(?:FAS|EWFA|FCO|RIR|AS)[-\s]?[A-Z0-9./-]{3,}\b", text, re.I)))[:50]
    frls = sorted(set(re.findall(r"-?\s*/\s*\d{2,3}\s*/\s*\d{2,3}", text)))[:30]
    dimensions = sorted(set(re.findall(r"\b\d{1,4}(?:\.\d+)?\s*mm\b", text, re.I)))[:100]
    return {
        "extraction_status": "draft_candidate_only",
        "page_count": len(reader.pages),
        "pages": pages,
        "candidate_report_references": report_refs,
        "candidate_frl_values": frls,
        "candidate_dimensions": dimensions,
        "human_review_required": True,
        "automatic_activation_permitted": False,
    }
