from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIGNER = ROOT / "mobile" / "classifire-admission-signer"


def test_material_admission_review_bindings_use_one_resource_template() -> None:
    activity = (
        SIGNER
        / "app"
        / "src"
        / "main"
        / "java"
        / "au"
        / "com"
        / "classifire"
        / "admissionsigner"
        / "OfflineSignerActivity.java"
    ).read_text(encoding="utf-8")
    strings = (
        SIGNER / "app" / "src" / "main" / "res" / "values" / "strings.xml"
    ).read_text(encoding="utf-8")

    review_method = activity.split("private String reviewText", maxsplit=1)[1].split(
        "private static String mapText", maxsplit=1
    )[0]
    assert "R.string.validated_admission_review" in review_method
    assert 'return "Validated admission' not in review_method
    for position in range(1, 17):
        assert f"%{position}$s" in strings
