from __future__ import annotations

from types import SimpleNamespace

import pytest

import classifire.v213_release_promotion as promotion
from classifire.models import User
from classifire.services.release_scope import _manifest_hash


def _user(role: str, email: str) -> User:
    return User(
        id=f"user-{role}-{email}",
        email=email,
        full_name=email,
        password_hash="test-only",
        role=role,
        is_active=True,
    )


def _validation(*, token: str = "token-123", conditions: list[str] | None = None) -> dict:
    condition_ids = conditions or []
    return {
        "schema": "CLASSIFIRE-V213-RELEASE-VALIDATION-v1",
        "hard_gates_passed": True,
        "approval_token": token,
        "conditions": [{"condition_id": value} for value in condition_ids],
        "approval_basis": {
            "pricing_source_release_id": "pricing-source",
            "technical_source_release_id": "technical-source",
            "source_hashes": {
                "package14": "a" * 64,
                "package15": "b" * 64,
                "package17": "c" * 64,
            },
        },
    }


def test_runtime_manifest_hash_matches_release_scope_hash() -> None:
    payload = {
        "schema": "CLASSIFIRE-V213-RUNTIME-RELEASE-v1",
        "version": "2.13-runtime",
        "records": [{"id": "r1", "key": "PKB-1", "rate_ex_tax": "123.45"}],
        "approved_by_email": "approver@example.com",
    }
    assert promotion._canonical_hash(payload) == _manifest_hash(payload)


def test_technical_manifest_preserves_collision_provenance() -> None:
    record = SimpleNamespace(
        id="db-1",
        variant_id="TSL-X-QFSRC-ABCDEF123456",
        system_id="TSL-X",
        frl="-/60/60",
        source_document_reference="FAS-1",
        source_page="p.1",
        source_hash="d" * 64,
        record_version=1,
        source_json={
            "CLASSIFIRE_Migration": {
                "identity_collision": True,
                "source_variant_id": "TSL-X",
            }
        },
    )
    manifest = promotion._technical_manifest_records([record])
    assert manifest[0]["id"] == "db-1"
    assert manifest[0]["variant_id"] == "TSL-X-QFSRC-ABCDEF123456"
    assert manifest[0]["migration_provenance"]["identity_collision"] is True
    assert manifest[0]["migration_provenance"]["source_variant_id"] == "TSL-X"


def test_promotion_rejects_stale_approval_token(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        promotion,
        "validate_v213_releases",
        lambda db, source_root: _validation(token="live-token"),
    )
    admin = _user("administrator", "admin@example.com")
    with pytest.raises(promotion.V213PromotionError, match="Approval token"):
        promotion.promote_v213_runtime_releases(
            object(),
            tmp_path,
            approval_token="old-token",
            acknowledged_condition_ids=set(),
            pricing_approver=admin,
            technical_approver=admin,
        )


def test_promotion_requires_every_validation_condition(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        promotion,
        "validate_v213_releases",
        lambda db, source_root: _validation(conditions=["COND-A", "COND-B"]),
    )
    admin = _user("administrator", "admin@example.com")
    with pytest.raises(promotion.V213PromotionError, match="COND-B"):
        promotion.promote_v213_runtime_releases(
            object(),
            tmp_path,
            approval_token="token-123",
            acknowledged_condition_ids={"COND-A"},
            pricing_approver=admin,
            technical_approver=admin,
        )


def test_promotion_requires_pricing_approval_authority(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        promotion,
        "validate_v213_releases",
        lambda db, source_root: _validation(),
    )
    estimator = _user("estimator", "estimator@example.com")
    admin = _user("administrator", "admin@example.com")
    with pytest.raises(promotion.V213PromotionError, match="pricing:approve"):
        promotion.promote_v213_runtime_releases(
            object(),
            tmp_path,
            approval_token="token-123",
            acknowledged_condition_ids=set(),
            pricing_approver=estimator,
            technical_approver=admin,
        )


def test_promotion_requires_technical_approval_authority(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        promotion,
        "validate_v213_releases",
        lambda db, source_root: _validation(),
    )
    pricing_manager = _user("pricing_manager", "pricing@example.com")
    estimator = _user("estimator", "estimator@example.com")
    with pytest.raises(promotion.V213PromotionError, match="technical:approve"):
        promotion.promote_v213_runtime_releases(
            object(),
            tmp_path,
            approval_token="token-123",
            acknowledged_condition_ids=set(),
            pricing_approver=pricing_manager,
            technical_approver=estimator,
        )
