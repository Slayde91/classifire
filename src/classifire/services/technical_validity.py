from __future__ import annotations

from datetime import date


def technical_document_temporal_blockers(
    *,
    expiry_date: date | None,
    as_of: date | None = None,
) -> tuple[str, ...]:
    """Return safe reasons a retained technical source is not currently usable.

    A source remains usable on its expiry date. Its retained bytes and review
    history remain available; this function only controls current authority.
    """
    current_day = as_of or date.today()
    return ("source_document_expired",) if expiry_date and expiry_date < current_day else ()


def technical_document_authority_blockers(
    *,
    status: str | None,
    expiry_date: date | None,
    stored_file_present: bool,
    stored_file_purpose: str | None = None,
    stored_file_scan_status: str | None = None,
    stored_file_immutable: bool | None = None,
    as_of: date | None = None,
) -> tuple[str, ...]:
    """Return safe reasons a bound technical source lacks current authority.

    This is a metadata guard for current use; callers that need source bytes
    still use the existing exact-byte reader at their own authority boundary.
    """
    blockers: list[str] = []
    if status != "approved":
        blockers.append("source_document_not_approved")
    blockers.extend(technical_document_temporal_blockers(expiry_date=expiry_date, as_of=as_of))
    if not stored_file_present:
        blockers.append("source_file_missing")
        return tuple(blockers)
    if stored_file_purpose != "technical_evidence":
        blockers.append("source_file_wrong_purpose")
    if stored_file_immutable is not True:
        blockers.append("source_file_not_immutable")
    if (
        not isinstance(stored_file_scan_status, str)
        or stored_file_scan_status != stored_file_scan_status.strip()
        or stored_file_scan_status.casefold() != "clean"
    ):
        blockers.append("source_file_not_clean")
    return tuple(blockers)


def technical_variant_temporal_blockers(
    *,
    effective_date: date | None,
    expiry_date: date | None,
    as_of: date | None = None,
) -> tuple[str, ...]:
    """Return safe reasons a technical variant is not currently usable.

    An expiry date remains usable on that date. A future effective date is not
    usable until the stated day arrives.
    """
    current_day = as_of or date.today()
    blockers: list[str] = []
    if effective_date and effective_date > current_day:
        blockers.append("not_yet_effective")
    if expiry_date and expiry_date < current_day:
        blockers.append("expired")
    return tuple(blockers)
