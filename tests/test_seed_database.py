from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from classifire import physical_models  # noqa: F401
from classifire.db import Base
from classifire.importers.seed import (
    ACTIVE_ADMINISTRATOR_REQUIRED,
    INITIALIZATION_ALREADY_RECORDED,
    INITIALIZATION_AUDIT_REQUIRED,
    LEGACY_BASELINE_ADOPTION_REQUIRED,
    OPERATOR_REFERENCE_REQUIRED,
    SeedDatabaseError,
    require_seed_database_ready,
    seed_database,
)
from classifire.models import (
    AuditEvent,
    EstimatingRule,
    LabourComponent,
    LibraryRelease,
    MarkupProfile,
    User,
)

_OPERATOR_REFERENCE = "CHANGE-SEED-TEST"


@pytest.fixture
def factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    engine.dispose()


def _user(
    db: Session,
    *,
    email: str,
    role: str = "administrator",
    is_active: bool = True,
    user_id: str | None = None,
) -> User:
    user = User(
        email=email,
        full_name="Seed prerequisite user",
        password_hash=f"unused-existing-hash-for-{email}",
        role=role,
        is_active=is_active,
    )
    if user_id is not None:
        user.id = user_id
    db.add(user)
    db.flush()
    return user


def _count(db: Session, model: Any) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def _seed(
    db: Session,
    *,
    administrator_email: str = "administrator@example.test",
) -> dict[str, str]:
    return seed_database(
        db,
        administrator_email=administrator_email,
        operator_reference=_OPERATOR_REFERENCE,
        jurisdiction="Australia",
    )


def _assert_no_controlled_defaults(db: Session) -> None:
    assert _count(db, LibraryRelease) == 0
    assert _count(db, MarkupProfile) == 0
    assert _count(db, LabourComponent) == 0
    assert _count(db, EstimatingRule) == 0


def test_seed_database_fails_closed_without_creating_an_administrator(
    factory: sessionmaker[Session],
) -> None:
    with factory() as db:
        with pytest.raises(SeedDatabaseError) as exc_info:
            _seed(db)

        assert exc_info.value.code == ACTIVE_ADMINISTRATOR_REQUIRED
        assert str(exc_info.value) == ACTIVE_ADMINISTRATOR_REQUIRED
        assert _count(db, User) == 0
        _assert_no_controlled_defaults(db)


def test_seed_database_rejects_inactive_administrators_and_active_non_admins(
    factory: sessionmaker[Session],
) -> None:
    with factory() as db:
        _user(db, email="inactive-admin@example.test", is_active=False)
        _user(db, email="active-estimator@example.test", role="estimator")
        db.commit()

        with pytest.raises(SeedDatabaseError, match=f"^{ACTIVE_ADMINISTRATOR_REQUIRED}$"):
            _seed(db, administrator_email="inactive-admin@example.test")

        assert _count(db, User) == 2
        _assert_no_controlled_defaults(db)


def test_seed_database_uses_existing_active_administrator_without_creating_users(
    factory: sessionmaker[Session],
) -> None:
    with factory() as db:
        administrator = _user(db, email="administrator@example.test")
        administrator_id = administrator.id
        db.commit()

        result = _seed(db)

        assert result["admin_user_id"] == administrator_id
        assert _count(db, User) == 1
        assert _count(db, LibraryRelease) == 3
        assert _count(db, MarkupProfile) == 1
        assert _count(db, LabourComponent) == 1
        assert _count(db, EstimatingRule) == 1

        releases = list(db.scalars(select(LibraryRelease)))
        assert all(release.created_by_id == administrator_id for release in releases)
        assert all(release.approved_by_id == administrator_id for release in releases)
        assert all(release.approved_at is not None for release in releases)

        markup = db.scalar(select(MarkupProfile))
        assert markup is not None
        assert markup.created_by_id == administrator_id
        assert markup.approved_by_id == administrator_id

        rule = db.scalar(select(EstimatingRule))
        audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "seed_controlled_defaults"))
        assert rule is not None
        assert audit is not None
        assert rule.jurisdiction == "Australia"
        assert rule.author_id == administrator_id
        assert rule.reviewer_id == administrator_id
        assert rule.approver_id == administrator_id
        assert audit.actor_user_id == administrator_id
        assert audit.reason == _OPERATOR_REFERENCE

        ready_administrator = require_seed_database_ready(db)
        assert ready_administrator.id == administrator_id

        with pytest.raises(SeedDatabaseError) as repeated:
            _seed(db)
        assert repeated.value.code == INITIALIZATION_ALREADY_RECORDED
        assert _count(db, AuditEvent) == 1


def test_seed_database_readiness_requires_explicit_initialization_audit(
    factory: sessionmaker[Session],
) -> None:
    with factory() as db:
        _user(db, email="administrator@example.test")
        db.commit()

        with pytest.raises(SeedDatabaseError) as rejected:
            require_seed_database_ready(db)

        assert rejected.value.code == INITIALIZATION_AUDIT_REQUIRED
        assert _count(db, User) == 1
        _assert_no_controlled_defaults(db)


def test_seed_database_refuses_ambiguous_legacy_baseline_adoption(
    factory: sessionmaker[Session],
) -> None:
    with factory() as db:
        _user(db, email="administrator@example.test")
        db.add(
            LibraryRelease(
                library_type="rules",
                version="QF-RULES-1",
                status="active",
            )
        )
        db.commit()

        with pytest.raises(SeedDatabaseError) as rejected:
            _seed(db)

        assert rejected.value.code == LEGACY_BASELINE_ADOPTION_REQUIRED
        assert _count(db, User) == 1
        assert _count(db, LibraryRelease) == 1
        assert _count(db, AuditEvent) == 0
        assert _count(db, MarkupProfile) == 0
        assert _count(db, LabourComponent) == 0
        assert _count(db, EstimatingRule) == 0


def test_seed_database_requires_an_operator_reference(
    factory: sessionmaker[Session],
) -> None:
    with factory() as db:
        _user(db, email="administrator@example.test")
        db.commit()

        with pytest.raises(SeedDatabaseError) as rejected:
            seed_database(
                db,
                administrator_email="administrator@example.test",
                operator_reference="   ",
                jurisdiction="Australia",
            )

        assert rejected.value.code == OPERATOR_REFERENCE_REQUIRED
        assert _count(db, AuditEvent) == 0
        _assert_no_controlled_defaults(db)


def test_seed_database_uses_the_explicit_active_administrator(
    factory: sessionmaker[Session],
) -> None:
    with factory() as db:
        later = _user(
            db,
            email="zeta-admin@example.test",
            user_id="00000000-0000-0000-0000-000000000001",
        )
        expected = _user(
            db,
            email="Alpha-admin@example.test",
            user_id="ffffffff-ffff-ffff-ffff-ffffffffffff",
        )
        db.commit()

        result = _seed(db, administrator_email=later.email)

        assert result["admin_user_id"] == later.id
        assert result["admin_user_id"] != expected.id
        assert _count(db, User) == 2

        markup = db.scalar(select(MarkupProfile))
        rule = db.scalar(select(EstimatingRule))
        assert markup is not None
        assert rule is not None
        assert markup.created_by_id == later.id
        assert markup.approved_by_id == later.id
        assert rule.author_id == later.id
        assert rule.reviewer_id == later.id
        assert rule.approver_id == later.id
