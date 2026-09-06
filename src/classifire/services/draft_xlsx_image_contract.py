"""Pure portable descriptor checks for bounded workbook picture occurrences."""

from __future__ import annotations

import re
from typing import Any

MAX_IMAGES = 50
MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_PIXELS = 2_000_000
MAX_ANCHOR_EMU = 1_000_000_000
IMAGE_KEYS = frozenset(
    {
        "occurrence_id",
        "member",
        "sha256",
        "size_bytes",
        "media_type",
        "width",
        "height",
        "anchor",
        "preview_sha256",
    }
)
MARKER_KEYS = frozenset({"row", "column", "row_offset_emu", "column_offset_emu"})


def _integer(value: Any, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def validate_anchor(anchor: Any) -> None:
    if type(anchor) is not dict or set(anchor) != {"kind", "from", "to", "extent"}:
        raise ValueError("SCOPE_XLSX_IMAGE_ANCHOR")
    if anchor["kind"] not in ("oneCell", "twoCell"):
        raise ValueError("SCOPE_XLSX_IMAGE_ANCHOR")
    markers = [anchor["from"]]
    if anchor["kind"] == "twoCell":
        if anchor["extent"] is not None:
            raise ValueError("SCOPE_XLSX_IMAGE_ANCHOR")
        markers.append(anchor["to"])
    else:
        extent = anchor["extent"]
        if (
            anchor["to"] is not None
            or type(extent) is not dict
            or set(extent) != {"width_emu", "height_emu"}
            or any(not _integer(v, 1, MAX_ANCHOR_EMU) for v in extent.values())
        ):
            raise ValueError("SCOPE_XLSX_IMAGE_ANCHOR")
    for marker in markers:
        if (
            type(marker) is not dict
            or set(marker) != MARKER_KEYS
            or not _integer(marker["row"], 1, 1000)
            or not _integer(marker["column"], 1, 50)
            or not _integer(marker["row_offset_emu"], 0, MAX_ANCHOR_EMU)
            or not _integer(marker["column_offset_emu"], 0, MAX_ANCHOR_EMU)
        ):
            raise ValueError("SCOPE_XLSX_IMAGE_ANCHOR")
    if anchor["kind"] == "twoCell":
        start, end = markers
        for axis in ("row", "column"):
            offset = axis + "_offset_emu"
            if (end[axis], end[offset]) <= (start[axis], start[offset]):
                raise ValueError("SCOPE_XLSX_IMAGE_ANCHOR")


def validate_image_descriptor(image: Any) -> None:
    if type(image) is not dict or set(image) != IMAGE_KEYS:
        raise ValueError("SCOPE_XLSX_IMAGE_DESCRIPTOR")
    if (
        type(image["occurrence_id"]) is not str
        or re.fullmatch(r"image-([1-9]|[1-4][0-9]|50)", image["occurrence_id"]) is None
        or type(image["member"]) is not str
        or re.fullmatch(
            r"xl/media/[A-Za-z0-9_.-]{1,180}\.(?:png|jpe?g)", image["member"], re.IGNORECASE
        )
        is None
        or not _integer(image["size_bytes"], 1, MAX_IMAGE_BYTES)
        or image["media_type"] not in ("image/png", "image/jpeg")
        or not _integer(image["width"], 1, MAX_IMAGE_PIXELS)
        or not _integer(image["height"], 1, MAX_IMAGE_PIXELS)
        or image["width"] * image["height"] > MAX_IMAGE_PIXELS
    ):
        raise ValueError("SCOPE_XLSX_IMAGE_DESCRIPTOR")
    expected_type = "image/png" if image["member"].lower().endswith(".png") else "image/jpeg"
    if image["media_type"] != expected_type:
        raise ValueError("SCOPE_XLSX_IMAGE_DESCRIPTOR")
    for key in ("sha256", "preview_sha256"):
        if type(image[key]) is not str or re.fullmatch(r"[0-9a-f]{64}", image[key]) is None:
            raise ValueError("SCOPE_XLSX_IMAGE_DESCRIPTOR")
    validate_anchor(image["anchor"])
