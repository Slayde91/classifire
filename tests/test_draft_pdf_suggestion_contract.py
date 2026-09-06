from __future__ import annotations

import base64
import traceback
from copy import deepcopy
from typing import Any

import pytest

from classifire.services.draft_pdf_suggestion_contract import (
    MAX_PAGE_PNG,
    MAX_PAGE_TEXT,
    SuggestionError,
    SuggestionRequest,
    SuggestionResult,
    output_schema,
    validate_suggestion_output,
)

PAGE_TEXT = "Two pipes share the wall opening. Inspect the seal."
PAGE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def output() -> dict[str, Any]:
    claim = dict(basis="page_text", quote="wall opening", rationale="The page identifies it.")
    return {
        "defects": [dict(claim, key="d1", label="Seal review", description="Inspect seal.")],
        "openings": [
            dict(
                claim, key="o1", label="Shared opening", defect_key="d1", plane="wall", substrate=""
            )
        ],
        "services": [
            dict(claim, key="s1", label="First pipe", opening_keys=["o1"], service_type="pipe"),
            dict(claim, key="s2", label="Second pipe", opening_keys=["o1"], service_type="pipe"),
        ],
        "observations": [dict(claim, key="n1", text="Seal condition needs human review.")],
    }


def request() -> SuggestionRequest:
    return SuggestionRequest(PAGE_TEXT, PAGE_PNG, "a" * 64)


def test_source_quotes_shared_opening_and_empty_output_are_preserved() -> None:
    candidate = output()
    candidate["services"][0].update(basis="page_image", quote="")
    candidate["services"][1]["basis"] = "both"
    candidate["observations"][0]["quote"] = "Inspect the seal."
    assert validate_suggestion_output(candidate, page_text=PAGE_TEXT) == candidate
    empty = {key: [] for key in candidate}
    assert validate_suggestion_output(empty, page_text="") == empty


@pytest.mark.parametrize(
    "field,value",
    [
        ("state", "Confirmed"),
        ("approval", True),
        ("diameter_mm", 100),
        ("quantity", 2),
        ("technical_system_id", "system-1"),
        ("id", "e5b4f15d-29f1-4508-b9de-a5a50c65388d"),
    ],
)
def test_untrusted_provider_cannot_add_authority_or_numeric_fields(field: str, value: Any) -> None:
    candidate = output()
    candidate["services"][0][field] = value
    with pytest.raises(SuggestionError, match="SUGGESTION_OUTPUT_INVALID"):
        validate_suggestion_output(candidate, page_text=PAGE_TEXT)


@pytest.mark.parametrize(
    "section,index,field,value",
    [
        ("defects", 0, "key", "e5b4f15d-29f1-4508-b9de-a5a50c65388d"),
        ("defects", 0, "key", "D1"),
        ("defects", 0, "label", " "),
        ("defects", 0, "description", "x" * 4001),
        ("openings", 0, "key", "d1"),
        ("openings", 0, "defect_key", "missing"),
        ("openings", 0, "plane", "ceiling"),
        ("openings", 0, "substrate", 42),
        ("services", 0, "opening_keys", ["missing"]),
        ("services", 0, "opening_keys", ["o1", "o1"]),
        ("services", 0, "opening_keys", "o1"),
        ("services", 0, "quote", "not on the source page"),
        ("services", 0, "quote", ""),
        ("services", 0, "quote", " "),
        ("services", 0, "quote", "x" * 501),
        ("services", 0, "rationale", "x" * 1001),
        ("services", 0, "rationale", " "),
        ("services", 0, "basis", "assumed"),
        ("observations", 0, "text", " "),
    ],
)
def test_bad_claims_or_links_are_rejected(section: str, index: int, field: str, value: Any) -> None:
    candidate = output()
    candidate[section][index][field] = value
    with pytest.raises(SuggestionError, match="SUGGESTION_OUTPUT_INVALID"):
        validate_suggestion_output(candidate, page_text=PAGE_TEXT)


def test_image_claim_cannot_carry_an_unverified_text_quote() -> None:
    candidate = output()
    candidate["services"][0]["basis"] = "page_image"
    with pytest.raises(SuggestionError, match="SUGGESTION_OUTPUT_INVALID"):
        validate_suggestion_output(candidate, page_text=PAGE_TEXT)


def _many(counts: tuple[int, int, int, int]) -> dict[str, Any]:
    candidate = output()
    prefixes = dict(defects="d", openings="o", services="s", observations="n")
    for (section, rows), count in zip(candidate.items(), counts, strict=True):
        candidate[section] = [
            dict(deepcopy(rows[0]), key=f"{prefixes[section]}{i}") for i in range(count)
        ]
    for row in candidate["openings"]:
        row["defect_key"] = None
    for row in candidate["services"]:
        row["opening_keys"] = []
    return candidate


@pytest.mark.parametrize(
    "counts", [(6, 0, 0, 0), (0, 11, 0, 0), (0, 0, 11, 0), (0, 0, 0, 11), (5, 10, 10, 1)]
)
def test_per_kind_and_combined_counts_are_bounded(counts: tuple[int, int, int, int]) -> None:
    with pytest.raises(SuggestionError, match="SUGGESTION_OUTPUT_INVALID"):
        validate_suggestion_output(_many(counts), page_text=PAGE_TEXT)
    assert validate_suggestion_output(_many((5, 10, 10, 0)), page_text=PAGE_TEXT)


def test_normalized_utf8_bytes_are_bounded_and_errors_do_not_echo_evidence() -> None:
    candidate = _many((5, 0, 0, 10))
    for row in candidate["defects"]:
        row["description"] = "\u20ac" * 4000
    for row in candidate["observations"]:
        row["text"] = "\u20ac" * 4000
    with pytest.raises(SuggestionError, match="SUGGESTION_OUTPUT_INVALID"):
        validate_suggestion_output(candidate, page_text=PAGE_TEXT)
    candidate = output()
    candidate["services"][0]["quantity"] = "private source value"
    with pytest.raises(SuggestionError) as caught:
        validate_suggestion_output(candidate, page_text=PAGE_TEXT)
    assert "private source value" not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize(
    "changes",
    [
        {"page_text": "x" * (MAX_PAGE_TEXT + 1)},
        {"page_text": None},
        {"page_png": b"not PNG"},
        {"page_png": PAGE_PNG.decode("latin1")},
        {"page_png": PAGE_PNG + b"x" * MAX_PAGE_PNG},
        {"input_sha256": "A" * 64},
        {"input_sha256": "not a hash"},
    ],
)
def test_request_refuses_unbounded_or_unbound_source(changes: dict[str, Any]) -> None:
    fields = dict(page_text=PAGE_TEXT, page_png=PAGE_PNG, input_sha256="a" * 64)
    fields.update(changes)
    with pytest.raises(SuggestionError, match="SUGGESTION_INPUT_INVALID"):
        SuggestionRequest(**fields)


def test_payloads_do_not_appear_in_dataclass_repr() -> None:
    assert PAGE_TEXT not in repr(request())
    assert "PNG" not in repr(request())
    assert "Seal review" not in repr(SuggestionResult("test", "test", "b" * 64, output()))


def test_schema_requires_all_fields_and_disallows_nested_extras() -> None:
    schema = output_schema()
    for item in [schema, *schema["$defs"].values()]:
        assert item["type"] == "object"
        assert item["additionalProperties"] is False
        assert set(item["required"]) == set(item["properties"])
    assert schema["$defs"]["SuggestedOpening"]["properties"]["defect_key"]["anyOf"][-1] == {
        "type": "null"
    }
