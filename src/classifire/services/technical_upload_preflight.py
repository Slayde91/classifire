"""Authenticated request-size routing for technical evidence uploads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session
from starlette.requests import Request

from ..config import Settings
from ..models import User
from ..upload_ingress import TECHNICAL_UPLOAD_MULTIPART_OVERHEAD_BYTES
from .technical_intake_batch import (
    TechnicalIntakeBatchError,
    get_owned_technical_intake_batch,
    require_technical_intake_batch_item_upload_eligible,
)

TECHNICAL_INTAKE_BATCH_ID_HEADER = "x-classifire-intake-batch-id"
TECHNICAL_INTAKE_ITEM_ID_HEADER = "x-classifire-intake-item-id"


@dataclass(frozen=True, slots=True)
class TechnicalUploadPreflight:
    """The authenticated request identity used only to select a body limit."""

    batch_id: str | None
    item_id: str | None
    declared_content_length: int

    @property
    def is_batch(self) -> bool:
        return self.batch_id is not None


class TechnicalUploadPreflightError(RuntimeError):
    """A stable rejection raised before multipart parsing or canonical claims."""

    def __init__(
        self,
        code: str,
        *,
        status_code: int,
        batch_request: bool,
        retryable: bool = False,
        fatal: bool = True,
    ) -> None:
        self.code = code
        self.status_code = status_code
        self.batch_request = batch_request
        self.retryable = retryable
        self.fatal = fatal
        super().__init__(code)


def _canonical_uuid4(value: str, *, code: str, batch_request: bool) -> str:
    try:
        parsed = UUID(value)
        normalised = str(parsed)
    except (AttributeError, ValueError):
        raise TechnicalUploadPreflightError(
            code,
            status_code=422,
            batch_request=batch_request,
        ) from None
    if parsed.version != 4 or normalised != value:
        raise TechnicalUploadPreflightError(
            code,
            status_code=422,
            batch_request=batch_request,
        )
    return normalised


def _single_content_length(
    request: Request,
    maximum_body_bytes: int,
    *,
    batch_request: bool,
) -> int:
    values = request.headers.getlist("content-length")
    if not values:
        raise TechnicalUploadPreflightError(
            "UPLOAD_CONTENT_LENGTH_REQUIRED",
            status_code=411,
            batch_request=batch_request,
        )
    if len(values) != 1 or not values[0]:
        raise TechnicalUploadPreflightError(
            "UPLOAD_CONTENT_LENGTH_INVALID",
            status_code=400,
            batch_request=batch_request,
        )
    declared = 0
    for character in values[0]:
        if character < "0" or character > "9":
            raise TechnicalUploadPreflightError(
                "UPLOAD_CONTENT_LENGTH_INVALID",
                status_code=400,
                batch_request=batch_request,
            )
        declared = declared * 10 + ord(character) - ord("0")
        if declared > maximum_body_bytes:
            raise TechnicalUploadPreflightError(
                "UPLOAD_SIZE_LIMIT_EXCEEDED",
                status_code=413,
                batch_request=batch_request,
            )
    return declared


def _batch_error(
    error: TechnicalIntakeBatchError,
    *,
    fatal: bool | None = None,
) -> TechnicalUploadPreflightError:
    return TechnicalUploadPreflightError(
        error.code,
        status_code=error.status_code,
        batch_request=True,
        retryable=error.retryable,
        fatal=error.fatal if fatal is None else fatal,
    )


def preflight_technical_upload(
    request: Request,
    db: Session,
    settings: Settings,
    *,
    actor: User,
) -> TechnicalUploadPreflight:
    """Select and enforce the authenticated request limit before form parsing."""

    batch_values = request.headers.getlist(TECHNICAL_INTAKE_BATCH_ID_HEADER)
    item_values = request.headers.getlist(TECHNICAL_INTAKE_ITEM_ID_HEADER)
    batch_request = bool(batch_values or item_values)
    if not batch_request:
        maximum_body_bytes = (
            settings.max_upload_bytes + TECHNICAL_UPLOAD_MULTIPART_OVERHEAD_BYTES
        )
        return TechnicalUploadPreflight(
            None,
            None,
            _single_content_length(
                request,
                maximum_body_bytes,
                batch_request=False,
            ),
        )

    if len(batch_values) != 1:
        raise TechnicalUploadPreflightError(
            "INTAKE_BATCH_ID_INVALID",
            status_code=422,
            batch_request=True,
        )
    if len(item_values) != 1:
        raise TechnicalUploadPreflightError(
            "INTAKE_BATCH_ITEM_ID_INVALID",
            status_code=422,
            batch_request=True,
        )
    batch_id = _canonical_uuid4(
        batch_values[0],
        code="INTAKE_BATCH_ID_INVALID",
        batch_request=True,
    )
    item_id = _canonical_uuid4(
        item_values[0],
        code="INTAKE_BATCH_ITEM_ID_INVALID",
        batch_request=True,
    )
    try:
        batch, items = get_owned_technical_intake_batch(
            db,
            actor=actor,
            batch_id=batch_id,
        )
    except TechnicalIntakeBatchError as exc:
        raise _batch_error(exc, fatal=True) from None
    item = next((candidate for candidate in items if candidate.id == item_id), None)
    if item is None:
        raise TechnicalUploadPreflightError(
            "INTAKE_BATCH_ITEM_NOT_FOUND",
            status_code=404,
            batch_request=True,
        )
    try:
        require_technical_intake_batch_item_upload_eligible(
            item,
            now=datetime.now(UTC),
        )
    except TechnicalIntakeBatchError as exc:
        raise _batch_error(exc) from None
    maximum_body_bytes = (
        item.declared_size_bytes + TECHNICAL_UPLOAD_MULTIPART_OVERHEAD_BYTES
    )
    return TechnicalUploadPreflight(
        batch.id,
        item.id,
        _single_content_length(
            request,
            maximum_body_bytes,
            batch_request=True,
        ),
    )


def require_matching_technical_upload_identity(
    preflight: TechnicalUploadPreflight,
    *,
    batch_id: str | None,
    item_id: str | None,
) -> None:
    """Bind the parsed form back to the authenticated preflight routing hints."""

    if batch_id != preflight.batch_id or item_id != preflight.item_id:
        raise TechnicalUploadPreflightError(
            "INTAKE_BATCH_HEADER_MISMATCH",
            status_code=409,
            batch_request=(
                preflight.is_batch or batch_id is not None or item_id is not None
            ),
        )


__all__ = [
    "TECHNICAL_INTAKE_BATCH_ID_HEADER",
    "TECHNICAL_INTAKE_ITEM_ID_HEADER",
    "TechnicalUploadPreflight",
    "TechnicalUploadPreflightError",
    "preflight_technical_upload",
    "require_matching_technical_upload_identity",
]
