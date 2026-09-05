
"""Exercise journal concurrency on the existing opt-in disposable PostgreSQL fixture."""
from uuid import uuid4

import pytest
import test_execution_journal as cases
from test_shared_file_containment import postgresql_session_factory  # noqa: F401


@pytest.fixture
def journal_postgresql_setup(postgresql_session_factory):  # noqa: F811
    return postgresql_session_factory, [100], str(uuid4()), str(uuid4())


def test_postgresql_journal_durable_restart(journal_postgresql_setup):
    cases.test_committed_capture_terminal_and_restart_verification(journal_postgresql_setup)


@pytest.mark.parametrize("interrupt", [False, True])
def test_postgresql_journal_competing_and_late_completion(journal_postgresql_setup, interrupt):
    cases.test_concurrent_duplicate_and_late_terminal_cannot_redispatch(
        journal_postgresql_setup, interrupt
    )
