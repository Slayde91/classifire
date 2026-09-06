"""Pure page-only proposal contract; no database identity or write authority."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

PROMPT_VERSION = "draft-pdf-suggestions-v1"
MAX_OUTPUT_BYTES = 64 * 1024
MAX_PAGE_TEXT = 20000
MAX_PAGE_PNG = 4 * 1024 * 1024
Key = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$", min_length=1, max_length=32)]
Label = Annotated[str, Field(min_length=1, max_length=200)]
LongText = Annotated[str, Field(max_length=4000)]


class SuggestionError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class SuggestionRequest:
    page_text: str = field(repr=False)
    page_png: bytes = field(repr=False)
    input_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.page_text) is not str
            or len(self.page_text) > MAX_PAGE_TEXT
            or type(self.page_png) is not bytes
            or not 8 < len(self.page_png) <= MAX_PAGE_PNG
            or not self.page_png.startswith(b"\x89PNG\r\n\x1a\n")
            or type(self.input_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", self.input_sha256) is None
        ):
            raise SuggestionError("SUGGESTION_INPUT_INVALID")


@dataclass(frozen=True, slots=True)
class SuggestionResult:
    provider: str
    model: str
    response_sha256: str
    output: dict[str, Any] = field(repr=False)


class SuggestionPort(Protocol):
    def complete(self, request: SuggestionRequest) -> SuggestionResult: ...


class _Claim(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    key: Key
    basis: Literal["page_text", "page_image", "both"]
    quote: Annotated[str, Field(max_length=500)]
    rationale: Annotated[str, Field(min_length=1, max_length=1000)]


class SuggestedDefect(_Claim):
    label: Label
    description: LongText


class SuggestedOpening(_Claim):
    label: Label
    defect_key: Key | None
    plane: Literal["wall", "floor", "soffit", "unknown"]
    substrate: Annotated[str, Field(max_length=500)]


class SuggestedService(_Claim):
    label: Label
    opening_keys: Annotated[list[Key], Field(max_length=10)]
    service_type: Annotated[str, Field(max_length=500)]


class SuggestedObservation(_Claim):
    text: Annotated[str, Field(min_length=1, max_length=4000)]


class SuggestionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    defects: Annotated[list[SuggestedDefect], Field(max_length=5)]
    openings: Annotated[list[SuggestedOpening], Field(max_length=10)]
    services: Annotated[list[SuggestedService], Field(max_length=10)]
    observations: Annotated[list[SuggestedObservation], Field(max_length=10)]


def output_schema() -> dict[str, Any]:
    return SuggestionOutput.model_json_schema()


def validate_suggestion_output(value: Any, *, page_text: str) -> dict[str, Any]:
    try:
        model = SuggestionOutput.model_validate(value)
        items: list[
            SuggestedDefect | SuggestedOpening | SuggestedService | SuggestedObservation
        ] = [*model.defects, *model.openings, *model.services, *model.observations]
        if len(items) > 25 or len({item.key for item in items}) != len(items):
            raise ValueError("item identities")
        for item in items:
            if not item.rationale.strip():
                raise ValueError("rationale")
            if item.basis in {"page_text", "both"}:
                if not item.quote.strip() or item.quote not in page_text:
                    raise ValueError("quote binding")
            elif item.quote != "":
                raise ValueError("image quote")
            if isinstance(item, SuggestedObservation):
                if not item.text.strip():
                    raise ValueError("observation")
            elif not item.label.strip():
                raise ValueError("label")
        defects = {item.key for item in model.defects}
        openings = {item.key for item in model.openings}
        if any(
            item.defect_key is not None and item.defect_key not in defects
            for item in model.openings
        ):
            raise ValueError("defect link")
        if any(
            len(set(item.opening_keys)) != len(item.opening_keys)
            or not set(item.opening_keys) <= openings
            for item in model.services
        ):
            raise ValueError("opening link")
        output = model.model_dump(mode="json")
        raw = json.dumps(
            output, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
        if len(raw) > MAX_OUTPUT_BYTES:
            raise ValueError("output size")
        return output
    except (ValidationError, ValueError, TypeError, RecursionError, UnicodeError):
        raise SuggestionError("SUGGESTION_OUTPUT_INVALID") from None
