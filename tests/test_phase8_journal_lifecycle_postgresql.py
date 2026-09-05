"""Lifecycle acceptance on the existing guarded disposable PostgreSQL database."""

import pytest
import test_phase8_journal_lifecycle as cases
from test_shared_file_containment import postgresql_session_factory  # noqa: F401


@pytest.mark.parametrize("kind", ["visual", "report"])
@pytest.mark.parametrize("mode", ["valid", "interrupted"])
def test_postgresql_transport_lifecycle(
    tmp_path,
    postgresql_session_factory,  # noqa: F811
    kind,
    mode,
):
    cases.test_journal_transport_lifecycle(tmp_path, postgresql_session_factory, kind, mode)
