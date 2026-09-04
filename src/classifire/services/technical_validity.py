from __future__ import annotations

from datetime import date
from typing import Any

TECHNICAL_RELEASE_SOURCE_BINDING_SCHEMA = "technical-release-source-binding-v1"


def technical_variant_logical_key(*, variant_id: str, source_json: dict[str, Any] | None) -> str:
    """Return the stable lineage key shared by snapshots and publication."""

    source = source_json or {}
    original_variant_id = source.get("original_variant_id")
    return str(original_variant_id or variant_id.split("-QFREV")[0])


def technical_release_source_binding(
    *,
    technical_document_id: str | None,
    technical_document_key: str | None = None,
    technical_document_reference: str | None = None,
    technical_document_revision: str | None = None,
    stored_file_id: str | None = None,
    stored_file_sha256: str | None = None,
    stored_file_size_bytes: int | None = None,
    source_document_reference: str | None,
    source_page: str | None,
    source_table: str | None,
    source_figure: str | None,
) -> dict[str, Any]:
    """Build the immutable source-lineage snapshot for one technical release record.

    Legacy active variants that predate retained-document binding remain explicit
    in release history, rather than being represented as a misleading blank
    document reference. Bound records capture only identifiers, a digest, and
    the safe locator; source bytes remain in governed storage.
    """
    binding: dict[str, Any] = {
        "schema": TECHNICAL_RELEASE_SOURCE_BINDING_SCHEMA,
        "state": "bound" if technical_document_id else "legacy_unbound",
        "source_locator": {
            "document_reference": source_document_reference,
            "page": source_page,
            "table": source_table,
            "figure": source_figure,
        },
    }
    if technical_document_id:
        binding["technical_document"] = {
            "id": technical_document_id,
            "document_id": technical_document_key,
            "reference": technical_document_reference,
            "revision": technical_document_revision,
            "stored_file": {
                "id": stored_file_id,
                "sha256": stored_file_sha256,
                "size_bytes": stored_file_size_bytes,
            },
        }
    return binding


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
