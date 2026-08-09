from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from classifire import canonical_models, commercial_models  # noqa: F401
from classifire.auxiliary_runtime_promotion import (
    CONFIRMATION_PHRASE,
    AuxiliaryRuntimePromotionError,
    _activity_name,
    _labour_records,
    promote_auxiliary_runtime_releases,
)
from classifire.db import Base
from classifire.models import LabourComponent, User


def _factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def test_labour_runtime_scope_excludes_uat_anchors() -> None:
    factory = _factory()
    with factory() as db:
        db.add_all(
            [
                LabourComponent(
                    code="LAB-PASSIVE-FIRE-INSTALLER",
                    revision=1,
                    name="Passive-fire installer",
                    unit="person_hour",
                    base_rate=Decimal("130"),
                    default_hours=Decimal("1"),
                    crew_size=Decimal("1"),
                    status="active",
                ),
                LabourComponent(
                    code="UAT-LAB-TEST",
                    revision=1,
                    name="Synthetic UAT anchor",
                    unit="person_hour",
                    base_rate=Decimal("130"),
                    default_hours=Decimal("0"),
                    crew_size=Decimal("1"),
                    status="active",
                ),
            ]
        )
        db.flush()
        records = _labour_records(db)
        assert [record.code for record in records] == ["LAB-PASSIVE-FIRE-INSTALLER"]


def test_missing_productivity_requires_explicit_acknowledgement(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = _factory()
    with factory() as db:
        approver = User(
            email="admin@example.com",
            full_name="Administrator",
            password_hash="not-used",
            role="administrator",
            is_active=True,
        )
        db.add(approver)
        db.flush()

        monkeypatch.setattr(
            "classifire.auxiliary_runtime_promotion.inspect_auxiliary_runtime_basis",
            lambda _db: {
                "missing_labour_activities": ["INSTALL_COLLAR"],
                "core_runtime_basis": {},
                "counts": {"excluded_active_uat_labour_anchors": 0},
            },
        )

        with pytest.raises(AuxiliaryRuntimePromotionError, match="Explicit acknowledgement is required"):
            promote_auxiliary_runtime_releases(
                db,
                approver=approver,
                confirmation_phrase=CONFIRMATION_PHRASE,
                acknowledge_missing_productivity=False,
            )


def test_activity_name_parses_string_and_dict_forms() -> None:
    assert _activity_name(" INSTALL_COLLAR ") == "INSTALL_COLLAR"
    assert _activity_name({"activity": "CUT_BATT"}) == "CUT_BATT"
    assert _activity_name({"labour_activity_id": "FIT_BATT"}) == "FIT_BATT"
    assert _activity_name({}) is None
