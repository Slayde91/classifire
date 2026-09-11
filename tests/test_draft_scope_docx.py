from __future__ import annotations

import copy
import io
import zipfile

import pytest
from PIL import Image

from classifire.services import draft_scope_docx as word
from classifire.services import report_evidence_adapter as adapter
from classifire.services.draft_scope_docx_document import (
    PIC,
    WP,
    A,
    R,
    W,
    digest,
    parse,
    validate_document,
)


def word_bytes(
    *, extra: dict[str, bytes] | None = None, body: str | None = None, relationship: str = ""
) -> bytes:
    picture = io.BytesIO()
    Image.new("RGB", (12, 8), "red").save(picture, format="PNG")
    body = (
        body
        if body is not None
        else (
            "<w:p><w:r><w:t>Synthetic D-01: one shared opening, "
            "quantities unknown.</w:t></w:r></w:p>"
            "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Illustrated pipe and cable group.</w:t>"
            "</w:r></w:p></w:tc><w:tc><w:p><w:r><w:drawing>"
            '<wp:inline><wp:extent cx="114300" cy="76200"/>'
            '<wp:docPr id="1" name="Synthetic picture"/>'
            f'<a:graphic><a:graphicData uri="{PIC}"><pic:pic>'
            '<pic:nvPicPr><pic:cNvPr id="0" name="image1.png"/><pic:cNvPicPr/></pic:nvPicPr>'
            '<pic:blipFill><a:blip r:embed="image1"/>'
            '<a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="114300" cy="76200"/></a:xfrm>'
            '<a:prstGeom prst="rect"/></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline>'
            "</w:drawing></w:r></w:p></w:tc></w:tr></w:tbl>"
        )
    )
    entries = {
        "[Content_Types].xml": (
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            b'<Override PartName="/word/document.xml" ContentType="'
            b'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            b"</Types>"
        ),
        "_rels/.rels": (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="r1" Type="{R}/officeDocument" Target="word/document.xml"/>'
            "</Relationships>"
        ).encode(),
        "word/document.xml": (
            f'<w:document xmlns:w="{W}" xmlns:a="{A}" xmlns:r="{R}" '
            f'xmlns:wp="{WP}" xmlns:pic="{PIC}">'
            f"<w:body>{body}</w:body></w:document>"
        ).encode(),
        "word/_rels/document.xml.rels": (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="image1" Type="{R}/image" Target="media/image1.png"/>'
            f"{relationship}</Relationships>"
        ).encode(),
        "word/media/image1.png": picture.getvalue(),
    }
    entries.update(extra or {})
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    return output.getvalue()


def test_word_text_picture_and_exact_source_binding():
    content = word_bytes()
    document, previews = parse(content)
    assert validate_document(document)
    assert document["manifest"] == {
        "source_sha256": digest(content),
        "source_size_bytes": len(content),
    }
    assert [block["locator"] for block in document["blocks"]] == [
        "body-1",
        "body-2/row-1/cell-1/p-1",
        "body-2/row-1/cell-2/p-1",
    ]
    assert "quantities unknown" in document["blocks"][0]["text"]
    picture = document["pictures"][0]
    assert picture["locator"] == document["blocks"][2]["locator"]
    assert picture["preview_sha256"] == digest(previews["picture-1"])
    assert previews["picture-1"].startswith(b"\x89PNG")
    assert word._process(content) == word._process(content)
    tampered = copy.deepcopy(document)
    tampered["pictures"][0]["locator"] = "body-1"
    assert not validate_document(tampered)
    with pytest.raises(adapter.ReportEvidenceAdapterError):
        adapter._docx_archive_is_within_policy(content)


@pytest.mark.parametrize(
    "extra",
    [
        {"word/header1.xml": b"hidden evidence"},
        {"word/vbaProject.bin": b"macro"},
        {"word/embeddings/object.bin": b"object"},
        {"../escape.xml": b"escape"},
        {"word/media/orphan.png": b"unrepresented image"},
    ],
)
def test_word_refuses_unrepresented_or_unsafe_parts(extra):
    with pytest.raises((ValueError, adapter.ReportEvidenceAdapterError)):
        parse(word_bytes(extra=extra))


def test_word_refuses_network_and_tracked_content():
    with pytest.raises(adapter.ReportEvidenceAdapterError):
        parse(
            word_bytes(
                relationship=f'<Relationship Id="external" Type="{R}/image" TargetMode="External" Target="https://example.test/image.png"/>'
            )
        )
    with pytest.raises(ValueError):
        parse(word_bytes(body="<w:p><w:ins><w:r><w:t>unreviewed change</w:t></w:r></w:ins></w:p>"))
