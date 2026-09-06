"""Explicitly scripted, exact synthetic page fixture for local suggestion UI proof."""

from __future__ import annotations

import hashlib
import io
import json

from reportlab.lib import colors
from reportlab.pdfgen.canvas import Canvas


def pdf_bytes() -> bytes:
    out = io.BytesIO()
    page = Canvas(out, pagesize=(595, 842), invariant=1)
    page.setTitle("Synthetic PDF suggestion fixture v1")
    page.setFont("Helvetica-Bold", 20)
    page.drawString(45, 790, "Synthetic PDF suggestion fixture v1")
    page.setFont("Helvetica", 11)
    page.drawString(45, 758, "Shared opening carries pipe and cable groups.")
    page.drawString(45, 739, "Dimensions and counts are unresolved. Inspect before saving.")
    page.setFillColor(colors.HexColor("#eceef2"))
    page.rect(65, 420, 465, 260, fill=1, stroke=0)
    page.setFillColor(colors.HexColor("#ffffff"))
    page.rect(150, 455, 250, 175, fill=1, stroke=1)
    page.setFillColor(colors.HexColor("#6c7c86"))
    page.circle(222, 540, 41, fill=1, stroke=1)
    page.setFillColor(colors.HexColor("#dae3e8"))
    page.circle(222, 540, 28, fill=1, stroke=1)
    page.setFillColor(colors.HexColor("#383d46"))
    for x, y in ((327, 528), (342, 549), (315, 553)):
        page.circle(x, y, 10, fill=1, stroke=0)
    page.setFillColor(colors.black)
    page.drawString(177, 478, "Pipe group")
    page.drawString(303, 478, "Cable group")
    page.drawString(155, 645, "D-01: possible shared wall opening")
    page.drawString(45, 382, "Schematic only. Circle count is not a billable service quantity.")
    page.drawString(
        45, 362, "No fire rating, dimensions or technical compatibility is established."
    )
    page.setFont("Helvetica-Bold", 12)
    page.drawString(45, 290, "Development fixture - no customer evidence or real AI output")
    page.save()
    return out.getvalue()


class ScriptedSuggestionPort:
    """Refuse every input except the exact retained demonstration page."""

    def __init__(self) -> None:
        from classifire.services.draft_pdf_intake import _process

        source = pdf_bytes()
        document = json.loads(_process(source))
        self._text = document["pages"][0]["text"]
        self._image_hash = hashlib.sha256(_process(source, 1)).hexdigest()

    def complete(self, request):
        from classifire.services.draft_pdf_suggestion_contract import (
            SuggestionError,
            SuggestionResult,
        )

        if (
            request.page_text != self._text
            or hashlib.sha256(request.page_png).hexdigest() != self._image_hash
        ):
            raise SuggestionError("SCRIPTED_FIXTURE_ONLY")
        common = {
            "basis": "both",
            "quote": "Shared opening carries pipe and cable groups.",
            "rationale": ("Scripted example agrees with the schematic labels; "
                          "a human must review the grouping."),
        }
        output = {
            "defects": [
                dict(
                    common,
                    key="d1",
                    label="D-01",
                    description="Possible unsealed shared wall opening",
                )
            ],
            "openings": [
                dict(
                    common,
                    key="o1",
                    label="Shared wall opening",
                    defect_key="d1",
                    plane="wall",
                    substrate="",
                )
            ],
            "services": [
                dict(
                    common,
                    key="s1",
                    label="Pipe group",
                    opening_keys=["o1"],
                    service_type="Unverified pipe group",
                ),
                dict(
                    common,
                    key="s2",
                    label="Cable group",
                    opening_keys=["o1"],
                    service_type="Unverified cable group",
                ),
            ],
            "observations": [
                {
                    "key": "q1",
                    "basis": "page_text",
                    "quote": "Dimensions and counts are unresolved.",
                    "rationale": "The fixture explicitly withholds dimensions and quantities.",
                    "text": ("Confirm dimensions, substrate, service count and configuration "
                             "from suitable evidence."),
                }
            ],
        }
        raw = json.dumps(output, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return SuggestionResult(
            provider="scripted",
            model="synthetic-fixture-v1",
            response_sha256=hashlib.sha256(raw).hexdigest(),
            output=output,
        )
