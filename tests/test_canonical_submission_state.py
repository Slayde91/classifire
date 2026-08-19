from __future__ import annotations

import pytest
from physical_foundation_support import add_estimate, add_evidence, add_opening, physical_session

from classifire.services.canonical_submission_state import (
    CanonicalSubmissionStateError,
    initial_submission_state,
    require_initial_submission_state,
)


def test_empty_initial_state_can_be_rechecked_after_admission_registration() -> None:
    with physical_session() as db:
        estimate = add_estimate(db)
        add_evidence(db, estimate)
        before = initial_submission_state(db, estimate_id=estimate.id)
        checked = require_initial_submission_state(
            db, estimate_id=estimate.id, expected_fingerprint=before.fingerprint
        )
        assert checked.fingerprint == before.fingerprint
        assert checked.counts["opening_count"] == 0


def test_state_change_or_nonempty_model_fails_closed() -> None:
    with physical_session() as db:
        estimate = add_estimate(db)
        before = initial_submission_state(db, estimate_id=estimate.id)
        add_evidence(db, estimate)
        with pytest.raises(CanonicalSubmissionStateError) as changed:
            require_initial_submission_state(
                db, estimate_id=estimate.id, expected_fingerprint=before.fingerprint
            )
        assert changed.value.code == "INITIAL_SUBMISSION_STATE_CHANGED"

        add_opening(db, estimate)
        nonempty_state = initial_submission_state(db, estimate_id=estimate.id)
        with pytest.raises(CanonicalSubmissionStateError) as nonempty:
            require_initial_submission_state(
                db, estimate_id=estimate.id, expected_fingerprint=nonempty_state.fingerprint
            )
        assert nonempty.value.code == "INITIAL_SUBMISSION_STATE_NOT_EMPTY"
