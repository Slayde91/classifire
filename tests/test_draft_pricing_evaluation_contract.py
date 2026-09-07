from __future__ import annotations

import copy

import pytest

from classifire.services.draft_pricing_evaluation_contract import (
    PricingEvaluationLineageError,
    assign_target_blind_splits,
    build_lineage_manifest,
    lineage_manifest_bytes,
    load_lineage_manifest,
    validate_lineage_manifest,
    validate_new_revision,
)
from classifire.services.draft_system_match_contract import digest


def _hash(character: str) -> str:
    return character * 64


def _observation(number: int, split: str, *, alias: str | None = None) -> dict[str, object]:
    return {
        "observation_id": f"price-observation-{number}",
        "split": split,
        "dataset": {"id": "firefly-b", "kind": "firefly_system_prices", "version": 2},
        "source": {"id": f"source-{number}", "sha256": _hash(str(number))},
        "profile": {"id": f"profile-{number}", "revision": 1, "sha256": _hash("a")},
        "row": {
            "sheet_index": 1,
            "sheet_name": "Systems",
            "number": number + 1,
            "sha256": _hash("b"),
        },
        "target": {"field": "rate", "sha256": _hash("c")},
        "available_at": "2026-08-31T00:00:00+00:00",
        "lineage_keys": {
            "system_identity": f"system-{number}",
            "alias_cluster": alias or f"alias-{number}",
            "configuration_cluster": f"configuration-cluster-{number}",
            "source_derivation": f"source-line-{number}",
            "version_lineage": f"version-family-{number}",
        },
    }


def _manifest(*, observations: list[dict[str, object]] | None = None):
    return build_lineage_manifest(
        manifest_id="pricing-evaluation-benchmark",
        draft_scope_id="draft-synthetic",
        revision=1,
        parent_manifest_sha256=None,
        created_at="2026-09-01T00:00:00+00:00",
        created_by_id="reviewer-synthetic",
        feature_cutoff_at="2026-08-31T00:00:00+00:00",
        observations=observations
        or [
            _observation(1, "training"),
            _observation(2, "validation"),
            _observation(3, "holdout"),
        ],
        feature_declarations=[
            {
                "name": "substrate-family",
                "origin": "technical_feature",
                "source_observation_ids": [],
                "available_at": "2026-08-30T00:00:00+00:00",
                "target_derived": False,
            },
            {
                "name": "eligible-training-rate",
                "origin": "training_observation",
                "source_observation_ids": ["price-observation-1"],
                "available_at": "2026-08-31T00:00:00+00:00",
                "target_derived": False,
            },
        ],
    )


def test_manifest_is_sealed_canonical_and_has_no_runtime_authority() -> None:
    manifest = _manifest()
    content = lineage_manifest_bytes(manifest)

    reopened = load_lineage_manifest(
        content,
        expected_draft_scope_id="draft-synthetic",
        expected_manifest_sha256=manifest["manifest_sha256"],
    )

    assert reopened == manifest
    assert reopened["policy"]["target_access"] == "sealed_evaluator_only"
    assert reopened["effects"] == {
        "prediction_performed": False,
        "row_ingested": False,
        "library_activated": False,
        "estimate_changed": False,
        "release_performed": False,
    }
    assert b'"rate"' in content
    assert b"123.45" not in content


def test_manifest_order_and_transitive_lineage_groups_are_deterministic() -> None:
    first = _observation(1, "training", alias="connected-alias")
    second = _observation(2, "training", alias="connected-alias")
    third = _observation(3, "holdout")
    fourth = _observation(4, "validation")

    forward = _manifest(observations=[first, second, third, fourth])
    reverse = _manifest(observations=[fourth, third, second, first])

    assert lineage_manifest_bytes(forward) == lineage_manifest_bytes(reverse)
    training = next(group for group in forward["groups"] if group["split"] == "training")
    assert [member["observation_id"] for member in training["members"]] == [
        "price-observation-1",
        "price-observation-2",
    ]


def test_target_blind_split_assignment_is_deterministic_and_keeps_groups_together() -> None:
    members = [
        {
            "observation_id": item["observation_id"],
            "lineage_keys": item["lineage_keys"],
        }
        for item in [
            _observation(1, "training", alias="connected-alias"),
            _observation(2, "training", alias="connected-alias"),
            _observation(3, "validation"),
            _observation(4, "holdout"),
        ]
    ]

    forward = assign_target_blind_splits(members)
    reverse = assign_target_blind_splits(list(reversed(members)))

    assert forward == reverse
    assert forward["price-observation-1"] == forward["price-observation-2"]
    assert set(forward.values()) == {"training", "validation", "holdout"}


def test_target_blind_split_assignment_rejects_targets_and_insufficient_groups() -> None:
    member = {
        "observation_id": "price-observation-1",
        "lineage_keys": _observation(1, "training")["lineage_keys"],
    }
    with pytest.raises(PricingEvaluationLineageError, match="split member"):
        assign_target_blind_splits([{**member, "target": {"rate": "123.45"}}])
    with pytest.raises(PricingEvaluationLineageError, match="insufficient independent"):
        assign_target_blind_splits(
            [
                member,
                {
                    "observation_id": "price-observation-2",
                    "lineage_keys": _observation(2, "validation")["lineage_keys"],
                },
            ]
        )


def test_connected_alias_or_group_crossing_splits_fails_closed() -> None:
    observations = [
        _observation(1, "training", alias="same-system-alias"),
        _observation(2, "validation", alias="same-system-alias"),
        _observation(3, "holdout"),
    ]

    with pytest.raises(PricingEvaluationLineageError, match="crosses splits"):
        _manifest(observations=observations)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda value: value["lineage_keys"].pop("version_lineage"),
            "lineage keys",
        ),
        (
            lambda value: value["dataset"].update(kind="general_pricelist"),
            "benchmark dataset kind",
        ),
        (
            lambda value: value["target"].update(field="description"),
            "target field",
        ),
    ],
)
def test_incomplete_or_wrong_observation_lineage_fails_closed(mutation, message: str) -> None:
    observation = _observation(1, "training")
    mutation(observation)

    with pytest.raises(PricingEvaluationLineageError, match=message):
        _manifest(
            observations=[observation, _observation(2, "validation"), _observation(3, "holdout")]
        )


@pytest.mark.parametrize(
    ("feature", "message"),
    [
        (
            {
                "name": "leaked-target",
                "origin": "heldout_target",
                "source_observation_ids": [],
                "available_at": "2026-08-30T00:00:00+00:00",
                "target_derived": False,
            },
            "target-derived feature origin",
        ),
        (
            {
                "name": "hidden-derivative",
                "origin": "technical_feature",
                "source_observation_ids": [],
                "available_at": "2026-08-30T00:00:00+00:00",
                "target_derived": True,
            },
            "target-derived feature declaration",
        ),
        (
            {
                "name": "holdout-as-comparable",
                "origin": "training_observation",
                "source_observation_ids": ["price-observation-3"],
                "available_at": "2026-08-30T00:00:00+00:00",
                "target_derived": False,
            },
            "non-training observation used as feature",
        ),
        (
            {
                "name": "future-price",
                "origin": "independent_general_price",
                "source_observation_ids": [],
                "available_at": "2026-09-01T00:00:00+00:00",
                "target_derived": False,
            },
            "feature unavailable at cutoff",
        ),
    ],
)
def test_target_derived_heldout_or_future_features_fail_closed(feature, message: str) -> None:
    with pytest.raises(PricingEvaluationLineageError, match=message):
        build_lineage_manifest(
            manifest_id="pricing-evaluation-benchmark",
            draft_scope_id="draft-synthetic",
            revision=1,
            parent_manifest_sha256=None,
            created_at="2026-09-01T00:00:00+00:00",
            created_by_id="reviewer-synthetic",
            feature_cutoff_at="2026-08-31T00:00:00+00:00",
            observations=[
                _observation(1, "training"),
                _observation(2, "validation"),
                _observation(3, "holdout"),
            ],
            feature_declarations=[feature],
        )


def test_changed_foreign_noncanonical_and_duplicate_key_content_fails_closed() -> None:
    manifest = _manifest()
    changed = copy.deepcopy(manifest)
    changed["groups"][0]["members"][0]["row"]["number"] += 1
    with pytest.raises(PricingEvaluationLineageError, match="hash changed"):
        validate_lineage_manifest(changed)
    with pytest.raises(PricingEvaluationLineageError, match="foreign draft"):
        validate_lineage_manifest(manifest, expected_draft_scope_id="another-draft")
    with pytest.raises(PricingEvaluationLineageError, match="not canonical"):
        load_lineage_manifest(b" " + lineage_manifest_bytes(manifest))
    with pytest.raises(PricingEvaluationLineageError, match="duplicate JSON key"):
        load_lineage_manifest(b'{"schema_version":"one","schema_version":"two"}')

    changed_policy = copy.deepcopy(manifest)
    changed_policy["policy"]["target_access"] = "available_to_predictor"
    changed_policy["manifest_sha256"] = digest(
        {key: value for key, value in changed_policy.items() if key != "manifest_sha256"}
    )
    with pytest.raises(PricingEvaluationLineageError, match="policy changed"):
        validate_lineage_manifest(changed_policy)


def test_revision_parent_and_replay_checks_are_enforceable_before_persistence() -> None:
    first = _manifest()
    second = build_lineage_manifest(
        manifest_id=first["manifest_id"],
        draft_scope_id=first["draft_scope_id"],
        revision=2,
        parent_manifest_sha256=first["manifest_sha256"],
        created_at="2026-09-02T00:00:00+00:00",
        created_by_id="reviewer-synthetic",
        feature_cutoff_at="2026-08-31T00:00:00+00:00",
        observations=[
            _observation(1, "training"),
            _observation(2, "validation"),
            _observation(3, "holdout"),
        ],
    )

    assert validate_new_revision(second, previous=first) == second
    with pytest.raises(PricingEvaluationLineageError, match="replay"):
        validate_new_revision(
            second, previous=first, seen_manifest_sha256s=[second["manifest_sha256"]]
        )
    stale = copy.deepcopy(second)
    stale["parent_manifest_sha256"] = _hash("f")
    stale["manifest_sha256"] = "0" * 64
    with pytest.raises(PricingEvaluationLineageError, match="hash changed"):
        validate_new_revision(stale, previous=first)
