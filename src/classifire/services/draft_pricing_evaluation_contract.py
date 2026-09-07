"""Sealed provider-neutral lineage rules for later pricing evaluation.

This module deliberately contains no prediction or persistence.  It freezes the
shape and contamination rules that normalized Firefly price observations must
satisfy before a future evaluator may use them.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, cast

from .draft_system_match_contract import canonical, digest

SCHEMA = "CLASSIFIRE-PRICING-EVALUATION-LINEAGE-MANIFEST-v1"
SPLITS = ("training", "validation", "holdout")
REQUIRED_LINEAGE_KEYS = (
    "system_identity",
    "alias_cluster",
    "configuration_cluster",
    "source_derivation",
    "version_lineage",
)
ALLOWED_FEATURE_ORIGINS = (
    "technical_feature",
    "independent_general_price",
    "independent_labour",
    "training_observation",
)
DENIED_FEATURE_ORIGINS = (
    "heldout_target",
    "target_alias",
    "target_derivative",
    "prior_prediction",
    "prediction_correction",
    "evaluation_result",
    "package14_target_derivative",
)
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_OBSERVATIONS = 10_000
MAX_FEATURE_DECLARATIONS = 500
TARGET_BLIND_SPLIT_CYCLE = ("training", "validation", "holdout", "training", "training")

_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_HASH = re.compile(r"[0-9a-f]{64}")


class PricingEvaluationLineageError(ValueError):
    """The proposed manifest is unsafe, unbound or not canonical."""


def _policy() -> dict[str, object]:
    return {
        "assignment_unit": "connected_price_observation_system_lineage",
        "allowed_splits": list(SPLITS),
        "required_lineage_keys": list(REQUIRED_LINEAGE_KEYS),
        "target_field": "rate",
        "target_access": "sealed_evaluator_only",
        "preprocessing_fit_scope": "training_only",
        "denied_feature_origins": list(DENIED_FEATURE_ORIGINS),
    }


def _exact_dict(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise PricingEvaluationLineageError(label)
    return cast(dict[str, Any], value)


def _token(value: Any, label: str) -> str:
    if type(value) is not str or _TOKEN.fullmatch(value) is None:
        raise PricingEvaluationLineageError(label)
    return value


def _hash(value: Any, label: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if type(value) is not str or _HASH.fullmatch(value) is None:
        raise PricingEvaluationLineageError(label)
    return value


def _timestamp(value: Any, label: str) -> datetime:
    if type(value) is not str:
        raise PricingEvaluationLineageError(label)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise PricingEvaluationLineageError(label) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise PricingEvaluationLineageError(label)
    return parsed


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 1:
        raise PricingEvaluationLineageError(label)
    return value


def _validate_member(value: Any) -> dict[str, Any]:
    member = _exact_dict(
        value,
        {
            "observation_id",
            "dataset",
            "source",
            "profile",
            "row",
            "target",
            "available_at",
            "lineage_keys",
        },
        "lineage member",
    )
    _token(member["observation_id"], "observation identity")

    dataset = _exact_dict(member["dataset"], {"id", "kind", "version"}, "dataset lineage")
    _token(dataset["id"], "dataset identity")
    if dataset["kind"] != "firefly_system_prices":
        raise PricingEvaluationLineageError("benchmark dataset kind")
    _positive_int(dataset["version"], "dataset version")

    source = _exact_dict(member["source"], {"id", "sha256"}, "source lineage")
    _token(source["id"], "source identity")
    _hash(source["sha256"], "source hash")

    profile = _exact_dict(member["profile"], {"id", "revision", "sha256"}, "profile lineage")
    _token(profile["id"], "profile identity")
    _positive_int(profile["revision"], "profile revision")
    _hash(profile["sha256"], "profile hash")

    row = _exact_dict(
        member["row"], {"sheet_index", "sheet_name", "number", "sha256"}, "row lineage"
    )
    _positive_int(row["sheet_index"], "sheet index")
    if type(row["sheet_name"]) is not str or not 1 <= len(row["sheet_name"]) <= 200:
        raise PricingEvaluationLineageError("sheet name")
    _positive_int(row["number"], "row number")
    _hash(row["sha256"], "row hash")

    target = _exact_dict(member["target"], {"field", "sha256"}, "target binding")
    if target["field"] != "rate":
        raise PricingEvaluationLineageError("target field")
    _hash(target["sha256"], "target hash")
    _timestamp(member["available_at"], "observation availability")

    lineage = _exact_dict(member["lineage_keys"], set(REQUIRED_LINEAGE_KEYS), "lineage keys")
    for key in REQUIRED_LINEAGE_KEYS:
        _token(lineage[key], f"lineage key {key}")
    return member


def _connected_groups(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build transitive groups from every declared duplicate/alias lineage dimension."""

    parents = list(range(len(observations)))

    def root(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = root(left)
        right_root = root(right)
        if left_root != right_root:
            parents[right_root] = left_root

    owners: dict[tuple[str, str], int] = {}
    for index, observation in enumerate(observations):
        lineage = cast(dict[str, str], observation["lineage_keys"])
        for key in REQUIRED_LINEAGE_KEYS:
            marker = (key, lineage[key])
            if marker in owners:
                union(index, owners[marker])
            else:
                owners[marker] = index

    components: dict[int, list[dict[str, Any]]] = {}
    for index, observation in enumerate(observations):
        components.setdefault(root(index), []).append(observation)

    groups: list[dict[str, Any]] = []
    for members in components.values():
        splits = {member.pop("split") for member in members}
        if len(splits) != 1:
            raise PricingEvaluationLineageError("connected lineage crosses splits")
        members.sort(key=lambda item: item["observation_id"])
        lineage_markers = sorted(
            {
                f"{key}:{cast(dict[str, str], member['lineage_keys'])[key]}"
                for member in members
                for key in REQUIRED_LINEAGE_KEYS
            }
        )
        group_id = (
            "lg-"
            + digest(
                {
                    "members": [member["observation_id"] for member in members],
                    "lineage": lineage_markers,
                }
            )[:24]
        )
        groups.append(
            {
                "lineage_group_id": group_id,
                "split": next(iter(splits)),
                "members": members,
            }
        )
    return sorted(groups, key=lambda item: item["lineage_group_id"])


def assign_target_blind_splits(
    lineage_members: Iterable[dict[str, Any]],
) -> dict[str, str]:
    prepared: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in lineage_members:
        member = _exact_dict(raw, {"observation_id", "lineage_keys"}, "split member")
        observation_id = _token(member["observation_id"], "observation identity")
        if observation_id in seen:
            raise PricingEvaluationLineageError("duplicate observation")
        seen.add(observation_id)
        lineage = _exact_dict(
            member["lineage_keys"], set(REQUIRED_LINEAGE_KEYS), "lineage keys"
        )
        for key in REQUIRED_LINEAGE_KEYS:
            _token(lineage[key], f"lineage key {key}")
        prepared.append(
            {
                "observation_id": observation_id,
                "lineage_keys": copy.deepcopy(lineage),
                "split": "training",
            }
        )
        if len(prepared) > MAX_OBSERVATIONS:
            raise PricingEvaluationLineageError("too many lineage members")
    if not prepared:
        raise PricingEvaluationLineageError("lineage members")

    groups = _connected_groups(prepared)
    if len(groups) < len(SPLITS):
        raise PricingEvaluationLineageError("insufficient independent lineage groups")
    assignments: dict[str, str] = {}
    for index, group in enumerate(groups):
        split = TARGET_BLIND_SPLIT_CYCLE[index % len(TARGET_BLIND_SPLIT_CYCLE)]
        for member in group["members"]:
            assignments[member["observation_id"]] = split
    return {key: assignments[key] for key in sorted(assignments)}


def _validate_features(
    features: Any,
    *,
    observation_splits: dict[str, str],
    feature_cutoff: datetime,
) -> None:
    if type(features) is not list or len(features) > MAX_FEATURE_DECLARATIONS:
        raise PricingEvaluationLineageError("feature declarations")
    names: set[str] = set()
    for raw in features:
        feature = _exact_dict(
            raw,
            {"name", "origin", "source_observation_ids", "available_at", "target_derived"},
            "feature declaration",
        )
        name = _token(feature["name"], "feature name")
        if name in names:
            raise PricingEvaluationLineageError("duplicate feature declaration")
        names.add(name)
        origin = feature["origin"]
        if origin in DENIED_FEATURE_ORIGINS or origin not in ALLOWED_FEATURE_ORIGINS:
            raise PricingEvaluationLineageError("target-derived feature origin")
        if feature["target_derived"] is not False:
            raise PricingEvaluationLineageError("target-derived feature declaration")
        source_ids = feature["source_observation_ids"]
        if type(source_ids) is not list or any(type(item) is not str for item in source_ids):
            raise PricingEvaluationLineageError("feature observation lineage")
        if len(source_ids) != len(set(source_ids)):
            raise PricingEvaluationLineageError("duplicate feature observation lineage")
        if origin == "training_observation" and not source_ids:
            raise PricingEvaluationLineageError("training feature lineage required")
        if origin != "training_observation" and source_ids:
            raise PricingEvaluationLineageError("independent feature has observation lineage")
        for observation_id in source_ids:
            if observation_splits.get(observation_id) != "training":
                raise PricingEvaluationLineageError("non-training observation used as feature")
        if _timestamp(feature["available_at"], "feature availability") > feature_cutoff:
            raise PricingEvaluationLineageError("feature unavailable at cutoff")


def _validate_body(value: Any) -> dict[str, Any]:
    body = _exact_dict(
        value,
        {
            "schema_version",
            "manifest_id",
            "draft_scope_id",
            "revision",
            "parent_manifest_sha256",
            "created_at",
            "created_by_id",
            "feature_cutoff_at",
            "policy",
            "groups",
            "feature_declarations",
            "effects",
        },
        "lineage manifest",
    )
    if body["schema_version"] != SCHEMA:
        raise PricingEvaluationLineageError("lineage schema")
    _token(body["manifest_id"], "manifest identity")
    _token(body["draft_scope_id"], "draft identity")
    revision = _positive_int(body["revision"], "manifest revision")
    parent = _hash(body["parent_manifest_sha256"], "parent manifest hash", optional=True)
    if (revision == 1) != (parent is None):
        raise PricingEvaluationLineageError("manifest parent lineage")
    created_at = _timestamp(body["created_at"], "manifest creation time")
    _token(body["created_by_id"], "manifest actor")
    cutoff = _timestamp(body["feature_cutoff_at"], "feature cutoff")
    if cutoff > created_at:
        raise PricingEvaluationLineageError("feature cutoff after seal")
    if body["policy"] != _policy():
        raise PricingEvaluationLineageError("lineage policy changed")

    if type(body["groups"]) is not list or not body["groups"]:
        raise PricingEvaluationLineageError("lineage groups")
    flat: list[dict[str, Any]] = []
    declared_splits: set[str] = set()
    declared_group_ids: set[str] = set()
    observation_splits: dict[str, str] = {}
    for raw_group in body["groups"]:
        group = _exact_dict(raw_group, {"lineage_group_id", "split", "members"}, "lineage group")
        group_id = _token(group["lineage_group_id"], "lineage group identity")
        if group_id in declared_group_ids:
            raise PricingEvaluationLineageError("duplicate lineage group")
        declared_group_ids.add(group_id)
        split = group["split"]
        if split not in SPLITS:
            raise PricingEvaluationLineageError("evaluation split")
        declared_splits.add(split)
        if type(group["members"]) is not list or not group["members"]:
            raise PricingEvaluationLineageError("lineage group members")
        for raw_member in group["members"]:
            member = _validate_member(raw_member)
            observation_id = member["observation_id"]
            if observation_id in observation_splits:
                raise PricingEvaluationLineageError("duplicate observation")
            observation_splits[observation_id] = split
            flat.append({**copy.deepcopy(member), "split": split})
            if _timestamp(member["available_at"], "observation availability") > created_at:
                raise PricingEvaluationLineageError("observation unavailable at seal")
    if declared_splits != set(SPLITS):
        raise PricingEvaluationLineageError("training validation and holdout required")
    if _connected_groups(copy.deepcopy(flat)) != body["groups"]:
        raise PricingEvaluationLineageError("lineage groups are not canonical")

    _validate_features(
        body["feature_declarations"],
        observation_splits=observation_splits,
        feature_cutoff=cutoff,
    )
    if body["effects"] != {
        "prediction_performed": False,
        "row_ingested": False,
        "library_activated": False,
        "estimate_changed": False,
        "release_performed": False,
    }:
        raise PricingEvaluationLineageError("lineage manifest authority")
    return body


def build_lineage_manifest(
    *,
    manifest_id: str,
    draft_scope_id: str,
    revision: int,
    parent_manifest_sha256: str | None,
    created_at: str,
    created_by_id: str,
    feature_cutoff_at: str,
    observations: Iterable[dict[str, Any]],
    feature_declarations: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Create and seal a deterministic manifest from explicit synthetic/normalized rows."""

    prepared: list[dict[str, Any]] = []
    for raw in observations:
        if type(raw) is not dict:
            raise PricingEvaluationLineageError("lineage member")
        observation = copy.deepcopy(raw)
        split = observation.pop("split", None)
        if split not in SPLITS:
            raise PricingEvaluationLineageError("evaluation split")
        _validate_member(observation)
        prepared.append({**observation, "split": split})
        if len(prepared) > MAX_OBSERVATIONS:
            raise PricingEvaluationLineageError("too many lineage members")
    features = copy.deepcopy(list(feature_declarations))
    if len(features) > MAX_FEATURE_DECLARATIONS or any(type(item) is not dict for item in features):
        raise PricingEvaluationLineageError("feature declaration")

    def feature_name(item: dict[str, Any]) -> str:
        name = item.get("name")
        return name if type(name) is str else ""

    features.sort(key=feature_name)
    body: dict[str, Any] = {
        "schema_version": SCHEMA,
        "manifest_id": manifest_id,
        "draft_scope_id": draft_scope_id,
        "revision": revision,
        "parent_manifest_sha256": parent_manifest_sha256,
        "created_at": created_at,
        "created_by_id": created_by_id,
        "feature_cutoff_at": feature_cutoff_at,
        "policy": _policy(),
        "groups": _connected_groups(prepared),
        "feature_declarations": features,
        "effects": {
            "prediction_performed": False,
            "row_ingested": False,
            "library_activated": False,
            "estimate_changed": False,
            "release_performed": False,
        },
    }
    _validate_body(body)
    return {**body, "manifest_sha256": digest(body)}


def validate_lineage_manifest(
    value: Any,
    *,
    expected_draft_scope_id: str | None = None,
    expected_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    envelope = _exact_dict(
        value,
        {
            "schema_version",
            "manifest_id",
            "draft_scope_id",
            "revision",
            "parent_manifest_sha256",
            "created_at",
            "created_by_id",
            "feature_cutoff_at",
            "policy",
            "groups",
            "feature_declarations",
            "effects",
            "manifest_sha256",
        },
        "lineage manifest envelope",
    )
    body = {key: item for key, item in envelope.items() if key != "manifest_sha256"}
    _validate_body(body)
    actual = digest(body)
    _hash(envelope["manifest_sha256"], "manifest hash")
    if envelope["manifest_sha256"] != actual:
        raise PricingEvaluationLineageError("lineage manifest hash changed")
    if (
        expected_draft_scope_id is not None
        and envelope["draft_scope_id"] != expected_draft_scope_id
    ):
        raise PricingEvaluationLineageError("foreign draft manifest")
    if expected_manifest_sha256 is not None and actual != expected_manifest_sha256:
        raise PricingEvaluationLineageError("unexpected lineage manifest")
    return envelope


def lineage_manifest_bytes(value: Any) -> bytes:
    return cast(bytes, canonical(validate_lineage_manifest(value)))


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PricingEvaluationLineageError("duplicate JSON key")
        result[key] = value
    return result


def load_lineage_manifest(
    content: bytes,
    *,
    expected_draft_scope_id: str | None = None,
    expected_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    if type(content) is not bytes or not 1 <= len(content) <= MAX_MANIFEST_BYTES:
        raise PricingEvaluationLineageError("lineage manifest size")
    try:
        value = json.loads(content, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PricingEvaluationLineageError("lineage manifest JSON") from exc
    envelope = validate_lineage_manifest(
        value,
        expected_draft_scope_id=expected_draft_scope_id,
        expected_manifest_sha256=expected_manifest_sha256,
    )
    if canonical(envelope) != content:
        raise PricingEvaluationLineageError("lineage manifest is not canonical")
    return envelope


def validate_new_revision(
    candidate: Any,
    *,
    previous: Any | None,
    seen_manifest_sha256s: Iterable[str] = (),
) -> dict[str, Any]:
    """Fail closed on stale parentage or replay before a future persistence boundary."""

    current = validate_lineage_manifest(candidate)
    seen = set(seen_manifest_sha256s)
    if current["manifest_sha256"] in seen:
        raise PricingEvaluationLineageError("lineage manifest replay")
    if previous is None:
        if current["revision"] != 1 or current["parent_manifest_sha256"] is not None:
            raise PricingEvaluationLineageError("initial manifest lineage")
        return current
    prior = validate_lineage_manifest(previous)
    if (
        current["manifest_id"] != prior["manifest_id"]
        or current["draft_scope_id"] != prior["draft_scope_id"]
        or current["revision"] != prior["revision"] + 1
        or current["parent_manifest_sha256"] != prior["manifest_sha256"]
    ):
        raise PricingEvaluationLineageError("stale manifest lineage")
    return current
