"""Bounded Word body evidence; structural positions are not rendered page numbers."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from typing import Any

from . import report_evidence_adapter as adapter
from .draft_xlsx_images import A, R, _image, _target

SCHEMA = "CLASSIFIRE-DRAFT-SCOPE-DOCX-v1"
MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
MAX_BLOCKS = 1000
MAX_PICTURES = 40


def encode(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def parse(content: bytes) -> tuple[dict[str, Any], dict[str, bytes]]:
    if not 1 <= len(content) <= 10 * 1024 * 1024:
        raise ValueError("Word source size")
    # Legacy canonical intake keeps its strict text-only policy. This opt-in adds
    # only retained static PNG/JPEG inspection, without execution or network I/O.
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        entries = archive.infolist()
        if (
            not 1 <= len(entries) <= 2000
            or sum(item.file_size for item in entries) > 32 * 1024 * 1024
        ):
            raise ValueError("Word archive limit")
        if any(
            item.file_size > 8 * 1024 * 1024
            or item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
            for item in entries
        ):
            raise ValueError("Word archive member limit")
    adapter._docx_archive_is_within_policy(content, allow_static_images=True)
    root = adapter._docx_xml(adapter._docx_document_xml(content))
    forbidden = (adapter._DOCX_FORBIDDEN_ELEMENT_NAMES - {"drawing"}) | {
        "txbxContent",
        "sdt",
        "vMerge",
        "gridSpan",
        "subDoc",
        "contentPart",
    }
    if root.tag != f"{{{W}}}document" or any(
        adapter._docx_local_name(node.tag) in forbidden for node in root.iter()
    ):
        raise ValueError("Word feature unsupported")
    bodies = root.findall(f"{{{W}}}body")
    if len(bodies) != 1:
        raise ValueError("Word body")
    body = bodies[0]
    adapter._docx_body_children(body)
    blocks: list[dict[str, Any]] = []
    pictures: list[dict[str, Any]] = []
    previews: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = set(archive.namelist())
        media = {name for name in names if name.startswith("word/media/")}
        if len(media) > MAX_PICTURES or any(
            not name.lower().endswith((".png", ".jpg", ".jpeg")) for name in media
        ):
            raise ValueError("Word pictures unsupported")
        relations: dict[str, str] = {}
        path = "word/_rels/document.xml.rels"
        if path in names:
            for rel in adapter._docx_xml(archive.read(path)):
                identity = rel.attrib.get("Id", "")
                if not identity or identity in relations:
                    raise ValueError("Word relationship identity")
                target = _target("word/document.xml", rel.attrib.get("Target", ""), names)
                # Non-image relationships are validated by the archive boundary,
                # but cannot act as evidence-image references.
                relations[identity] = target if rel.attrib.get("Type") == R + "/image" else ""
        used_media: set[str] = set()

        def paragraph(node: Any, locator: str) -> None:
            text = adapter._docx_paragraph_text(node)
            if len(text) > 16000 or len(blocks) >= MAX_BLOCKS:
                raise ValueError("Word text limit")
            block: dict[str, Any] = {
                "locator": locator,
                "text": text,
                "text_sha256": digest(text.encode("utf-8")),
                "pictures": [],
            }
            for drawing in node.iter(f"{{{W}}}drawing"):
                if len(drawing) != 1 or drawing[0].tag not in {
                    f"{{{WP}}}inline",
                    f"{{{WP}}}anchor",
                }:
                    raise ValueError("Word drawing placement")
                graphics = list(drawing.iter(f"{{{A}}}graphicData"))
                if (
                    len(graphics) != 1
                    or graphics[0].attrib.get("uri") != PIC
                    or len(graphics[0]) != 1
                    or graphics[0][0].tag != f"{{{PIC}}}pic"
                ):
                    raise ValueError("Word non-picture drawing")
                blips = list(drawing.iter(f"{{{A}}}blip"))
                if len(blips) != 1 or len(pictures) >= MAX_PICTURES:
                    raise ValueError("Word drawing unsupported")
                blip = blips[0]
                if set(blip.attrib) != {f"{{{R}}}embed"}:
                    raise ValueError("Word image relationship")
                member = relations.get(blip.attrib[f"{{{R}}}embed"], "")
                if member not in media:
                    raise ValueError("Word image target")
                descriptor, preview = _image(archive.read(member), member)
                identity = f"picture-{len(pictures) + 1}"
                descriptor.update(id=identity, locator=locator)
                pictures.append(descriptor)
                previews[identity] = preview
                block["pictures"].append(identity)
                used_media.add(member)
            blocks.append(block)

        for index, child in enumerate(body, 1):
            locator = f"body-{index}"
            if child.tag == f"{{{W}}}p":
                paragraph(child, locator)
            elif child.tag == f"{{{W}}}tbl":
                rows = child.findall(f"{{{W}}}tr")
                if not rows or any(
                    item.tag not in {f"{{{W}}}tblPr", f"{{{W}}}tblGrid", f"{{{W}}}tr"}
                    for item in child
                ):
                    raise ValueError("Word table structure")
                for row_index, row in enumerate(rows, 1):
                    if any(item.tag not in {f"{{{W}}}trPr", f"{{{W}}}tc"} for item in row):
                        raise ValueError("Word table row")
                    for cell_index, cell in enumerate(row.findall(f"{{{W}}}tc"), 1):
                        if any(item.tag not in {f"{{{W}}}tcPr", f"{{{W}}}p"} for item in cell):
                            raise ValueError("Word nested table unsupported")
                        for paragraph_index, node in enumerate(cell.findall(f"{{{W}}}p"), 1):
                            paragraph(
                                node,
                                f"{locator}/row-{row_index}/cell-{cell_index}/p-{paragraph_index}",
                            )
        if used_media != media:
            raise ValueError("Word unrepresented pictures")
    document = {
        "schema": SCHEMA,
        "manifest": {"source_sha256": digest(content), "source_size_bytes": len(content)},
        "blocks": blocks,
        "pictures": pictures,
    }
    if len(encode(document)) > 2 * 1024 * 1024 or not validate_document(document):
        raise ValueError("Word document limit")
    return document, previews


def validate_document(value: Any) -> bool:
    try:
        if type(value) is not dict or set(value) != {"schema", "manifest", "blocks", "pictures"}:
            return False
        manifest = value["manifest"]
        if value["schema"] != SCHEMA or set(manifest) != {"source_sha256", "source_size_bytes"}:
            return False
        if not re.fullmatch(r"[0-9a-f]{64}", manifest["source_sha256"]) or not (
            type(manifest["source_size_bytes"]) is int
            and 1 <= manifest["source_size_bytes"] <= 10485760
        ):
            return False
        blocks, pictures = value["blocks"], value["pictures"]
        if type(blocks) is not list or not 1 <= len(blocks) <= MAX_BLOCKS:
            return False
        if type(pictures) is not list or len(pictures) > MAX_PICTURES:
            return False
        locators: set[str] = set()
        claimed: list[str] = []
        for block in blocks:
            if set(block) != {"locator", "text", "text_sha256", "pictures"}:
                return False
            locator = block["locator"]
            if (
                not re.fullmatch(
                    r"body-[1-9][0-9]{0,3}(/row-[1-9][0-9]{0,3}/cell-[1-9][0-9]{0,3}/p-[1-9][0-9]{0,3})?",
                    locator,
                )
                or locator in locators
            ):
                return False
            locators.add(locator)
            if type(block["text"]) is not str or len(block["text"]) > 16000:
                return False
            if digest(block["text"].encode("utf-8")) != block["text_sha256"]:
                return False
            if type(block["pictures"]) is not list:
                return False
            claimed.extend(block["pictures"])
        ids = []
        for index, picture in enumerate(pictures, 1):
            if set(picture) != {
                "member",
                "sha256",
                "size_bytes",
                "media_type",
                "width",
                "height",
                "preview_sha256",
                "id",
                "locator",
            }:
                return False
            if picture["id"] != f"picture-{index}" or picture["locator"] not in locators:
                return False
            if not re.fullmatch(
                r"word/media/[A-Za-z0-9_.-]+\.(png|jpe?g)", picture["member"], re.I
            ):
                return False
            if any(
                not re.fullmatch(r"[0-9a-f]{64}", picture[key])
                for key in ("sha256", "preview_sha256")
            ):
                return False
            if picture["media_type"] not in {"image/png", "image/jpeg"}:
                return False
            if any(
                type(picture[key]) is not int or picture[key] <= 0
                for key in ("size_bytes", "width", "height")
            ):
                return False
            if not any(
                block["locator"] == picture["locator"] and picture["id"] in block["pictures"]
                for block in blocks
            ):
                return False
            if (
                picture["size_bytes"] > 2 * 1024 * 1024
                or picture["width"] * picture["height"] > 2_000_000
            ):
                return False
            ids.append(picture["id"])
        return claimed == ids
    except (KeyError, TypeError, ValueError, AttributeError):
        return False
