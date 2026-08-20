from __future__ import annotations

from pathlib import Path

import pytest
import typer

from classifire.cli import register_adjudicated_admission
from classifire.config import Settings


def test_registration_command_is_disabled_before_reading_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "classifire.cli.get_settings",
        lambda: Settings(adjudicated_initial_submission_enabled=False),
    )

    with pytest.raises(typer.BadParameter) as rejected:
        register_adjudicated_admission(
            Path("missing-manifest.json"),
            Path("missing-receipt.json"),
            "test-operator",
        )
    assert rejected.value.message == "ADJUDICATED_SUBMISSION_DISABLED"
