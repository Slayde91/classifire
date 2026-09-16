"""Fixed subprocess image validation for untrusted Draft work-photo bytes."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import warnings

from PIL import Image, UnidentifiedImageError

MAXIMUM_IMAGE_BYTES = 25 * 1024 * 1024
MAXIMUM_PIXELS = 50_000_000
MAXIMUM_SIDE_PX = 12_000


def inspect(content: bytes) -> dict[str, object]:
    if not 1 <= len(content) <= MAXIMUM_IMAGE_BYTES:
        raise ValueError("IMAGE_SIZE_INVALID")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(content)) as probe:
            image_format = str(probe.format or "").upper()
            width, height = probe.size
            if (
                image_format not in {"JPEG", "PNG"}
                or width < 1
                or height < 1
                or width > MAXIMUM_SIDE_PX
                or height > MAXIMUM_SIDE_PX
                or width * height > MAXIMUM_PIXELS
            ):
                raise ValueError("IMAGE_DIMENSIONS_INVALID")
            probe.verify()
        with Image.open(io.BytesIO(content)) as decoded:
            if str(decoded.format or "").upper() != image_format or decoded.size != (width, height):
                raise ValueError("IMAGE_BINDING_INVALID")
            decoded.load()
    media_type = "image/jpeg" if image_format == "JPEG" else "image/png"
    return {
        "schema": "CLASSIFIRE-DRAFT-WORK-PHOTO-v1",
        "manifest": {
            "source_sha256": hashlib.sha256(content).hexdigest(),
            "source_size_bytes": len(content),
            "media_type": media_type,
            "width_px": width,
            "height_px": height,
        },
    }


def main() -> int:
    content = sys.stdin.buffer.read(MAXIMUM_IMAGE_BYTES + 1)
    try:
        result = inspect(content)
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ):
        return 2
    sys.stdout.buffer.write(
        json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
