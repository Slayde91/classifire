"""Shared supplied-logo presentation for new Draft reports; source pixels unchanged."""

from pathlib import Path

from reportlab.lib.units import mm
from reportlab.platypus import Flowable


def supplied_logo_path() -> Path:
    return Path(__file__).resolve().parents[1] / "static" / "brand" / "classifire-logo.png"


class DraftLogo(Flowable):
    """Clip the supplied square canvas for display without changing its pixels."""

    def __init__(self) -> None:
        super().__init__()
        self.width = 70 * mm
        self.height = 22 * mm

    def draw(self) -> None:
        canvas = self.canv
        canvas.saveState()
        clip = canvas.beginPath()
        clip.rect(0, 0, self.width, self.height)
        canvas.clipPath(clip, stroke=0)
        canvas.drawImage(
            str(supplied_logo_path()),
            0,
            self.height / 2 - self.width * 0.513,
            width=self.width,
            height=self.width,
            mask="auto",
        )
        canvas.restoreState()
