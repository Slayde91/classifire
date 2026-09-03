from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

from sqlalchemy.orm import Session

from ..models import StoredFile, TechnicalDocument
from .storage import StoredFileBindingError, read_verified_stored_file

TECHNICAL_DOCUMENT_SUPERSESSION_SCHEMA = "technical-document-supersession-v1"


class TechnicalDocumentLineageError(ValueError):
    """A safe reason why a Draft document cannot declare a predecessor."""


def _canonical_hash(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _snapshot(predecessor: TechnicalDocument, stored: StoredFile) -> dict[str, object]:
    return {
        "schema": TECHNICAL_DOCUMENT_SUPERSESSION_SCHEMA,
        "predecessor": {
            "id": predecessor.id,
            "document_id": predecessor.document_id,
            "document_type": predecessor.document_type,
            "manufacturer": predecessor.manufacturer,
            "issuing_organisation": predecessor.issuing_organisation,
            "reference": predecessor.reference,
            "revision": predecessor.revision,
            "stored_file": {
                "id": stored.id,
                "sha256": stored.sha256,
                "size_bytes": stored.size_bytes,
            },
        },
    }


def prepare_technical_document_supersession(
    db: Session,
    *,
    supersedes_document_id: str | None,
    storage_root: Path,
) -> tuple[str | None, dict[str, object] | None, str | None]:
    """Return a verified historical predecessor snapshot for a new Draft.

    Linking is permitted only to an independently approved prior source whose
    retained bytes remain clean and unchanged. This does not retire the prior
    source, approve the new document, activate a variant, or create a release.
    """
    if supersedes_document_id is None:
        return None, None, None
    if not isinstance(supersedes_document_id, str):
        # FastAPI supplies a Form default when this handler is called directly
        # in a unit test; it represents the same omitted optional field.
        if getattr(supersedes_document_id, "default", object()) is None:
            return None, None, None
        raise TechnicalDocumentLineageError(
            "TECHNICAL_DOCUMENT_SUPERSESSION_PREDECESSOR_INVALID"
        )
    predecessor_id = supersedes_document_id.strip()
    if not predecessor_id:
        return None, None, None
    predecessor = db.get(TechnicalDocument, predecessor_id)
    if predecessor is None:
        raise TechnicalDocumentLineageError(
            "TECHNICAL_DOCUMENT_SUPERSESSION_PREDECESSOR_NOT_FOUND"
        )
    if predecessor.status != "approved":
        raise TechnicalDocumentLineageError(
            "TECHNICAL_DOCUMENT_SUPERSESSION_PREDECESSOR_NOT_APPROVED"
        )
    stored = db.get(StoredFile, predecessor.stored_file_id)
    if stored is None:
        raise TechnicalDocumentLineageError(
            "TECHNICAL_DOCUMENT_SUPERSESSION_PREDECESSOR_SOURCE_MISSING"
        )
    try:
        read_verified_stored_file(
            stored,
            storage_root=storage_root,
            required_purpose="technical_evidence",
        )
    except StoredFileBindingError as exc:
        raise TechnicalDocumentLineageError(
            "TECHNICAL_DOCUMENT_SUPERSESSION_PREDECESSOR_SOURCE_INVALID"
        ) from exc
    lineage = _snapshot(predecessor, stored)
    return predecessor.id, lineage, _canonical_hash(lineage)


def technical_document_lineage_state(
    document: TechnicalDocument,
) -> tuple[str, dict[str, object] | None]:
    """Classify a persisted historical link without changing current authority."""
    if (
        document.supersedes_document_id is None
        and document.source_lineage_json is None
        and document.source_lineage_sha256 is None
    ):
        return "unlinked", None
    lineage = document.source_lineage_json
    if (
        not document.supersedes_document_id
        or not isinstance(lineage, dict)
        or not isinstance(document.source_lineage_sha256, str)
        or _canonical_hash(lineage) != document.source_lineage_sha256
    ):
        return "invalid", None
    predecessor = lineage.get("predecessor")
    if (
        lineage.get("schema") != TECHNICAL_DOCUMENT_SUPERSESSION_SCHEMA
        or not isinstance(predecessor, dict)
        or predecessor.get("id") != document.supersedes_document_id
    ):
        return "invalid", None
    return "verified", lineage