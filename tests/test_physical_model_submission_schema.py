from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from classifire.physical_model_submission_schema import InitialCanonicalPhysicalSubmission


def _payload() -> dict[str, object]:
    return {
        "openings": [
            {
                "opening_code": "O-001",
                "canonical_defect_id": str(uuid4()),
                "opening_type": "service_penetration",
            }
        ],
        "services": [{"service_code": "S-001", "service_type": "pipe", "quantity": "1"}],
        "service_opening_links": [{"service_code": "S-001", "opening_code": "O-001"}],
    }


def test_initial_submission_payload_requires_explicit_complete_links() -> None:
    payload = _payload()
    parsed = InitialCanonicalPhysicalSubmission.model_validate(payload)
    assert parsed.service_opening_links[0].opening_code == "O-001"

    payload["service_opening_links"] = []
    with pytest.raises(ValidationError, match="every declared service"):
        InitialCanonicalPhysicalSubmission.model_validate(payload)


def test_initial_submission_payload_rejects_implicit_or_unknown_records() -> None:
    payload = _payload()
    payload["service_opening_links"] = [{"service_code": "S-001", "opening_code": "O-UNKNOWN"}]
    with pytest.raises(ValidationError, match="reference declared"):
        InitialCanonicalPhysicalSubmission.model_validate(payload)

    payload = _payload()
    payload["openings"][0]["unexpected"] = "not allowed"  # type: ignore[index]
    with pytest.raises(ValidationError, match="Extra inputs"):
        InitialCanonicalPhysicalSubmission.model_validate(payload)
