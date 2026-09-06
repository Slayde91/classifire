"""Strict static-picture XML and sanitized previews for Scope workbook evidence."""

from __future__ import annotations

import hashlib
import io
import posixpath
import re
import zipfile
from typing import Any, NoReturn

from .draft_xlsx_image_contract import (
    MAX_ANCHOR_EMU,
    MAX_IMAGE_BYTES,
    MAX_IMAGE_PIXELS,
    MAX_IMAGES,
    validate_anchor,
    validate_image_descriptor,
)

S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
P = "http://schemas.openxmlformats.org/package/2006/relationships"
D = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
MAX_PREVIEW_BYTES = 4 * 1024 * 1024
_ALLOWED_RELATIONSHIPS = {
    R + "/" + name
    for name in (
        "officeDocument",
        "worksheet",
        "styles",
        "theme",
        "sharedStrings",
        "drawing",
        "image",
        "calcChain",
        "extended-properties",
        "custom-properties",
    )
} | {P + "/metadata/core-properties"}


def _fail() -> NoReturn:
    raise ValueError("SCOPE_XLSX_IMAGE_OR_LAYOUT_UNSUPPORTED")


def _xml(data: bytes) -> Any:
    from defusedxml.ElementTree import fromstring  # type: ignore[import-untyped]

    return fromstring(data)


def _attributes(node: Any, allowed: set[str]) -> None:
    if set(node.attrib) - allowed or any(len(value) > 4000 for value in node.attrib.values()):
        _fail()


def _tags(node: Any, expected: list[str]) -> None:
    if [child.tag for child in node] != expected:
        _fail()


def _number(value: Any, *, positive: bool = False) -> int:
    if type(value) is not str or re.fullmatch(r"0|[1-9][0-9]{0,9}", value) is None:
        _fail()
    number = int(value)
    if not (1 if positive else 0) <= number <= MAX_ANCHOR_EMU:
        _fail()
    return number


def _target(owner: str, target: str, names: set[str]) -> str:
    if (
        not target
        or any(c in target for c in ("\\", ":", "?", "#", "%"))
        or any(ord(c) < 32 for c in target)
    ):
        _fail()
    path = posixpath.normpath(
        target[1:] if target.startswith("/") else posixpath.join(posixpath.dirname(owner), target)
    )
    if path.startswith("../") or path not in names:
        _fail()
    return path


def _relationships(archive: zipfile.ZipFile) -> dict[str, dict[str, tuple[str, str]]]:
    names = set(archive.namelist())
    result = {}
    for path in names:
        if not path.endswith(".rels"):
            continue
        if path == "_rels/.rels":
            owner = ""
        elif "/_rels/" in path:
            directory, filename = path.rsplit("/_rels/", 1)
            owner = directory + "/" + filename[:-5]
            if owner not in names:
                _fail()
        else:
            _fail()
        root = _xml(archive.read(path))
        if root.tag != "{" + P + "}Relationships" or root.attrib:
            _fail()
        relationships: dict[str, tuple[str, str]] = {}
        for child in root:
            if child.tag != "{" + P + "}Relationship" or len(child):
                _fail()
            _attributes(child, {"Id", "Type", "Target", "TargetMode"})
            identity, kind = child.attrib.get("Id"), child.attrib.get("Type")
            if (
                not identity
                or identity in relationships
                or kind not in _ALLOWED_RELATIONSHIPS
                or child.attrib.get("TargetMode", "Internal") != "Internal"
            ):
                _fail()
            relationships[identity] = (kind, _target(owner, child.attrib.get("Target", ""), names))
        result[owner] = relationships
    return result


def _marker(node: Any) -> dict[str, int]:
    _attributes(node, set())
    _tags(node, ["{" + D + "}" + name for name in ("col", "colOff", "row", "rowOff")])
    values = []
    for child in node:
        if child.attrib or len(child):
            _fail()
        values.append(_number(child.text))
    return {
        "row": values[2] + 1,
        "column": values[0] + 1,
        "row_offset_emu": values[3],
        "column_offset_emu": values[1],
    }


def _picture(node: Any) -> str:
    _attributes(node, set())
    _tags(node, ["{" + D + "}" + tag for tag in ("nvPicPr", "blipFill", "spPr")])
    nonvisual, fill, shape = node
    _attributes(nonvisual, set())
    _tags(nonvisual, ["{" + D + "}cNvPr", "{" + D + "}cNvPicPr"])
    properties, picture_properties = nonvisual
    _attributes(properties, {"id", "name", "descr", "title", "hidden"})
    _number(properties.attrib.get("id"), positive=True)
    if len(properties) or properties.attrib.get("hidden", "0") not in ("0", "false"):
        _fail()
    _attributes(picture_properties, set())
    if len(picture_properties):
        _tags(picture_properties, ["{" + A + "}picLocks"])
        lock = picture_properties[0]
        _attributes(lock, {"noChangeAspect"})
        if len(lock) or lock.attrib.get("noChangeAspect", "0") not in ("0", "1", "false", "true"):
            _fail()
    _attributes(fill, set())
    _tags(fill, ["{" + A + "}blip", "{" + A + "}stretch"])
    blip, stretch = fill
    _attributes(blip, {"{" + R + "}embed", "cstate"})
    if len(blip) or blip.attrib.get("cstate", "none") not in (
        "none",
        "email",
        "screen",
        "print",
        "hqprint",
    ):
        _fail()
    embed = blip.attrib.get("{" + R + "}embed", "")
    if not embed:
        _fail()
    _attributes(stretch, set())
    _tags(stretch, ["{" + A + "}fillRect"])
    if stretch[0].attrib or len(stretch[0]):
        _fail()
    _attributes(shape, set())
    children = list(shape)
    if children and children[0].tag == "{" + A + "}xfrm":
        transform = children.pop(0)
        if transform.attrib:
            _fail()  # Rotation/reflection requires a separate faithful rendering contract.
        _tags(transform, ["{" + A + "}off", "{" + A + "}ext"])
        for element, keys in zip(transform, (("x", "y"), ("cx", "cy")), strict=True):
            if set(element.attrib) != set(keys) or len(element):
                _fail()
            for key in keys:
                _number(element.attrib[key], positive=key in ("cx", "cy"))
    if len(children) != 1 or children[0].tag != "{" + A + "}prstGeom":
        _fail()
    geometry = children[0]
    if geometry.attrib != {"prst": "rect"}:
        _fail()
    if len(geometry):
        _tags(geometry, ["{" + A + "}avLst"])
        if geometry[0].attrib or len(geometry[0]):
            _fail()
    return str(embed)


def _anchor(node: Any) -> tuple[dict[str, Any], str]:
    kind = {"{" + D + "}oneCellAnchor": "oneCell", "{" + D + "}twoCellAnchor": "twoCell"}.get(
        node.tag
    )
    if kind is None:
        _fail()
    _attributes(node, {"editAs"} if kind == "twoCell" else set())
    if node.attrib.get("editAs", "twoCell") not in ("oneCell", "twoCell", "absolute"):
        _fail()
    _tags(
        node,
        [
            "{" + D + "}" + tag
            for tag in ("from", "to" if kind == "twoCell" else "ext", "pic", "clientData")
        ],
    )
    origin, second, picture, client = node
    _attributes(client, {"fLocksWithSheet", "fPrintsWithSheet"})
    if len(client) or any(v not in ("0", "1", "true", "false") for v in client.attrib.values()):
        _fail()
    anchor: dict[str, Any] = {"kind": kind, "from": _marker(origin), "to": None, "extent": None}
    if kind == "twoCell":
        anchor["to"] = _marker(second)
    else:
        if set(second.attrib) != {"cx", "cy"} or len(second):
            _fail()
        anchor["extent"] = {
            "width_emu": _number(second.attrib["cx"], positive=True),
            "height_emu": _number(second.attrib["cy"], positive=True),
        }
    validate_anchor(anchor)
    return anchor, _picture(picture)


def _image(data: bytes, member: str) -> tuple[dict[str, Any], bytes]:
    from PIL import Image, ImageOps

    if not 1 <= len(data) <= MAX_IMAGE_BYTES:
        _fail()
    expected = "PNG" if member.lower().endswith(".png") else "JPEG"
    if not (
        expected == "PNG"
        and data.startswith(b"\x89PNG\r\n\x1a\n")
        or expected == "JPEG"
        and data.startswith(b"\xff\xd8\xff")
    ):
        _fail()
    with Image.open(io.BytesIO(data)) as original:
        width, height = original.size
        if (
            original.format != expected
            or not 1 <= width * height <= MAX_IMAGE_PIXELS
            or getattr(original, "n_frames", 1) != 1
        ):
            _fail()
        original.verify()
    with Image.open(io.BytesIO(data)) as original:
        original.load()
        oriented = ImageOps.exif_transpose(original)
        converted = oriented.convert(
            "RGBA" if "A" in oriented.getbands() or "transparency" in oriented.info else "RGB"
        )
        # New pixel image intentionally carries no EXIF, text, ICC profile or other metadata.
        clean = Image.frombytes(converted.mode, converted.size, converted.tobytes())
    clean.thumbnail((1200, 1600), Image.Resampling.LANCZOS)
    while True:
        output = io.BytesIO()
        clean.save(output, format="PNG", optimize=False, compress_level=6)
        preview = output.getvalue()
        if len(preview) <= MAX_PREVIEW_BYTES:
            break
        clean.thumbnail(
            (max(1, clean.width // 2), max(1, clean.height // 2)), Image.Resampling.LANCZOS
        )
    return {
        "member": member,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "media_type": "image/png" if expected == "PNG" else "image/jpeg",
        "width": width,
        "height": height,
        "preview_sha256": hashlib.sha256(preview).hexdigest(),
    }, preview


def inspect_scope_images(
    content: bytes,
) -> tuple[list[dict[str, Any]], dict[tuple[int, str], bytes]]:
    """Called only after shared ZIP byte/member bounds and archive checks have passed."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = set(archive.namelist())
        if any("\\" in name for name in names):
            _fail()
        relations = _relationships(archive)
        media = {name for name in names if name.startswith("xl/media/")}
        if len(media) > MAX_IMAGES:
            _fail()
        decoded = {}
        for member in media:
            if (
                re.fullmatch(
                    r"xl/media/[A-Za-z0-9_.-]{1,180}\.(?:png|jpe?g)", member, re.IGNORECASE
                )
                is None
            ):
                _fail()
            decoded[member] = _image(archive.read(member), member)
        book = _xml(archive.read("xl/workbook.xml"))
        sheet_nodes = book.find("{" + S + "}sheets")
        if (
            book.tag != "{" + S + "}workbook"
            or sheet_nodes is None
            or not 1 <= len(sheet_nodes) <= 10
        ):
            _fail()
        result, previews = [], {}
        used_media, used_drawings = set(), set()
        total = 0
        for index, sheet in enumerate(sheet_nodes, 1):
            rel = relations.get("xl/workbook.xml", {}).get(sheet.attrib.get("{" + R + "}id", ""))
            if sheet.tag != "{" + S + "}sheet" or rel is None or rel[0] != R + "/worksheet":
                _fail()
            part = rel[1]
            root = _xml(archive.read(part))
            if root.tag != "{" + S + "}worksheet":
                _fail()
            forbidden = {
                "extLst",
                "AlternateContent",
                "legacyDrawing",
                "legacyDrawingHF",
                "oleObjects",
                "controls",
                "tableParts",
            }
            if any(node.tag.rsplit("}", 1)[-1] in forbidden for node in root.iter()):
                _fail()
            drawings = root.findall("{" + S + "}drawing")
            if len(drawings) > 1:
                _fail()
            images: list[dict[str, Any]] = []
            if drawings:
                drawing = drawings[0]
                if set(drawing.attrib) != {"{" + R + "}id"} or len(drawing):
                    _fail()
                linked = relations.get(part, {}).get(drawing.attrib["{" + R + "}id"])
                if linked is None or linked[0] != R + "/drawing" or linked[1] in used_drawings:
                    _fail()
                drawing_part = linked[1]
                if re.fullmatch(r"xl/drawings/[A-Za-z0-9_.-]+\.xml", drawing_part) is None:
                    _fail()
                used_drawings.add(drawing_part)
                drawing_root = _xml(archive.read(drawing_part))
                if (
                    drawing_root.tag != "{" + D + "}wsDr"
                    or drawing_root.attrib
                    or not len(drawing_root)
                ):
                    _fail()
                image_relations = relations.get(drawing_part, {})
                used_relations = set()
                for node in drawing_root:
                    total += 1
                    if total > MAX_IMAGES:
                        _fail()
                    anchor, identity = _anchor(node)
                    linked_image = image_relations.get(identity)
                    if (
                        linked_image is None
                        or linked_image[0] != R + "/image"
                        or linked_image[1] not in decoded
                    ):
                        _fail()
                    member = linked_image[1]
                    used_relations.add(identity)
                    used_media.add(member)
                    metadata, preview = decoded[member]
                    occurrence = "image-" + str(len(images) + 1)
                    descriptor = metadata | {"occurrence_id": occurrence, "anchor": anchor}
                    validate_image_descriptor(descriptor)
                    images.append(descriptor)
                    previews[(index, occurrence)] = preview
                if set(image_relations) != used_relations:
                    _fail()
            result.append({"name": sheet.attrib.get("name"), "images": images})
        expected_drawings = used_drawings | {
            posixpath.dirname(part) + "/_rels/" + posixpath.basename(part) + ".rels"
            for part in used_drawings
        }
        if (
            used_media != media
            or {name for name in names if name.startswith("xl/drawings/")} != expected_drawings
        ):
            _fail()
        return result, previews
