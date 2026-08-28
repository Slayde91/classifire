from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Approval,
    Estimate,
    EstimatingRule,
    LabourComponent,
    LibraryRelease,
    MarkupProfile,
    PricingLibraryRecord,
    Product,
    TechnicalVariant,
)
from .technical_governance import (
    GOVERNED_TECHNICAL_RELEASE_POLICY_V2,
    GOVERNED_TECHNICAL_RELEASE_POLICY_V3,
    TECHNICAL_REVIEW_APPROVAL_TYPE,
    TECHNICAL_REVIEW_POLICY_V2,
    TECHNICAL_REVIEW_POLICY_V3,
    TechnicalGovernanceError,
    require_technical_source_binding,
    technical_approval_binding,
    technical_review_snapshot_hash,
    technical_source_reviewer_ids,
    technical_variant_snapshot_hash,
)
from .technical_retirement import (
    TechnicalRetirementError,
    validate_technical_retirement_binding,
)

PIN_FIELDS = {
    "pricing": "pricing_release_id",
    "technical": "technical_release_id",
    "rules": "rules_release_id",
    "products": "products_release_id",
    "labour": "labour_release_id",
    "markups": "markups_release_id",
}

_GOVERNED_TECHNICAL_RECORD_FIELDS_V2 = frozenset(
    {
        "id",
        "key",
        "variant_id",
        "system_id",
        "frl",
        "source_document_reference",
        "source_page",
        "source_hash",
        "technical_document_id",
        "source_binding",
        "approval_binding",
        "record_hash",
        "record_version",
        "governance_basis",
    }
)
_GOVERNED_TECHNICAL_RECORD_FIELDS_V2_CARRY = (
    _GOVERNED_TECHNICAL_RECORD_FIELDS_V2 | {"record_binding_policy"}
)
_GOVERNED_TECHNICAL_RECORD_FIELDS_V3 = (
    _GOVERNED_TECHNICAL_RECORD_FIELDS_V2_CARRY
    | {"unpublished_supersedes_binding"}
)
_GOVERNED_TECHNICAL_V3_MANIFEST_FIELDS = frozenset(
    {
        "release_type",
        "version",
        "created_at",
        "created_by_id",
        "record_count",
        "activated_draft_ids",
        "previous_release_id",
        "records",
        "notes",
        "governance_policy",
        "previous_release",
        "activated_candidate_ids",
        "carried_record_ids",
        "carried_forward_v2_record_ids",
        "superseded_record_ids",
        "retired_record_ids",
        "runtime_authority",
    }
)


_GOVERNED_TECHNICAL_V3_MANIFEST_FIELDS = (
    _GOVERNED_TECHNICAL_V3_MANIFEST_FIELDS | {'retirement_bindings'}
)


class ReleaseScopeError(ValueError):
    pass


def manifest_hash(manifest: dict[str, Any]) -> str:
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _release_records(release: LibraryRelease) -> list[dict[str, Any]]:
    manifest = release.source_manifest or {}
    if (
        manifest.get('records') == []
        and manifest.get('governance_policy')
        == GOVERNED_TECHNICAL_RELEASE_POLICY_V3
        and release.library_type == 'technical'
        and release.supersedes_release_id is not None
        and isinstance(manifest.get('retired_record_ids'), list)
        and bool(manifest.get('retired_record_ids'))
        and isinstance(manifest.get('retirement_bindings'), list)
    ):
        return []
    records = (release.source_manifest or {}).get("records", [])
    if not isinstance(records, list) or not records:
        raise ReleaseScopeError(
            f"{release.library_type.title()} release contains no record identifiers."
        )
    if any(not isinstance(item, dict) for item in records):
        raise ReleaseScopeError(
            f"{release.library_type.title()} release contains a malformed record entry."
        )
    return records


def _validate_technical_runtime_state(
    release: LibraryRelease,
    variant: TechnicalVariant,
) -> None:
    allowed_statuses = {"active"} if release.status == "active" else {"active", "superseded"}
    if variant.status not in allowed_statuses:
        raise ReleaseScopeError(
            f"Technical release record {variant.variant_id!r} has invalid lifecycle "
            f"state {variant.status!r} for a {release.status!r} release."
        )
    today = date.today()
    if variant.effective_date and variant.effective_date > today:
        raise ReleaseScopeError(
            f"Technical release record {variant.variant_id!r} is not yet effective."
        )
    if variant.expiry_date and variant.expiry_date < today:
        raise ReleaseScopeError(f"Technical release record {variant.variant_id!r} is expired.")


def _validate_governed_release_envelope(
    release: LibraryRelease,
    *,
    expected_policy: str,
    records: list[dict[str, Any]],
) -> str:
    manifest = release.source_manifest or {}
    if manifest.get("governance_policy") != expected_policy:
        raise ReleaseScopeError("Technical release does not use the expected registry policy.")
    if manifest.get("release_type") != "technical":
        raise ReleaseScopeError("Governed Technical release type binding is invalid.")
    if manifest.get("version") != release.version:
        raise ReleaseScopeError("Governed Technical release version binding is invalid.")
    if manifest.get("record_count") != len(records):
        raise ReleaseScopeError("Governed Technical release record count binding is invalid.")
    if expected_policy == GOVERNED_TECHNICAL_RELEASE_POLICY_V3:
        manifest_created_at = manifest.get("created_at")
        if (
            not isinstance(manifest_created_at, str)
            or manifest_created_at != _canonical_release_timestamp(release.created_at)
            or manifest_created_at != _canonical_release_timestamp(release.approved_at)
        ):
            raise ReleaseScopeError(
                "Governed Technical release timestamp binding is invalid."
            )
    creator_id = manifest.get("created_by_id")
    if (
        not isinstance(creator_id, str)
        or not creator_id
        or release.created_by_id != creator_id
        or release.approved_by_id != creator_id
        or release.approved_at is None
    ):
        raise ReleaseScopeError("Governed Technical release creator binding is invalid.")
    if release.status == "active" and release.active_publication_slot != "technical":
        raise ReleaseScopeError(
            "Active governed Technical release does not own the publication slot."
        )
    if release.status != "active" and release.active_publication_slot is not None:
        raise ReleaseScopeError("Inactive Technical release still owns the publication slot.")
    return creator_id


def _canonical_release_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _governed_record_ids(records: list[dict[str, Any]]) -> list[str]:
    record_ids = [str(item.get("id") or "") for item in records]
    if any(not record_id for record_id in record_ids) or len(set(record_ids)) != len(
        record_ids
    ):
        raise ReleaseScopeError(
            "Governed Technical release contains missing or duplicate record IDs."
        )
    logical_keys = [item.get("key") for item in records]
    if (
        any(not isinstance(key, str) or not key for key in logical_keys)
        or len(set(logical_keys)) != len(logical_keys)
        or records
        != sorted(
            records,
            key=lambda item: (
                str(item.get("key") or ""),
                str(item.get("id") or ""),
            ),
        )
    ):
        raise ReleaseScopeError(
            "Governed Technical release logical keys or record ordering are invalid."
        )
    return record_ids


def _validate_governed_technical_record(
    db: Session,
    release: LibraryRelease,
    item: dict[str, Any],
    variant: TechnicalVariant,
    *,
    binding_policy: str,
    publisher_id: str,
    enforce_source_publisher_independence: bool,
) -> None:
    if binding_policy == GOVERNED_TECHNICAL_RELEASE_POLICY_V3:
        expected_fields = _GOVERNED_TECHNICAL_RECORD_FIELDS_V3
    elif "record_binding_policy" in item:
        expected_fields = _GOVERNED_TECHNICAL_RECORD_FIELDS_V2_CARRY
    else:
        expected_fields = _GOVERNED_TECHNICAL_RECORD_FIELDS_V2
    if set(item) != expected_fields:
        raise ReleaseScopeError(
            f"Technical release record projection is malformed for {variant.variant_id!r}."
        )
    _validate_technical_runtime_state(release, variant)
    record_hash = str(item.get("record_hash") or "")
    if not record_hash or technical_variant_snapshot_hash(variant) != record_hash:
        raise ReleaseScopeError(
            f"Technical release record {variant.variant_id!r} changed after publication."
        )
    source = variant.source_json or {}
    expected_projection = {
        "key": source.get("original_variant_id")
        or variant.variant_id.split("-QFREV")[0],
        "variant_id": variant.variant_id,
        "system_id": variant.system_id,
        "frl": variant.frl,
        "source_document_reference": variant.source_document_reference,
        "source_page": variant.source_page,
        "source_hash": variant.source_hash,
        "technical_document_id": variant.technical_document_id,
        "record_version": variant.record_version,
        "governance_basis": "approved_technical_review",
    }
    if any(item.get(field) != value for field, value in expected_projection.items()):
        raise ReleaseScopeError(
            f"Technical release identity mismatch for {variant.variant_id!r}."
        )
    source_manifest = item.get("source_binding")
    if not isinstance(source_manifest, dict):
        raise ReleaseScopeError(
            f"Technical release source binding is malformed for {variant.variant_id!r}."
        )
    try:
        source_binding = require_technical_source_binding(
            db,
            variant,
            binding_policy=binding_policy,
        )
    except TechnicalGovernanceError as exc:
        raise ReleaseScopeError(
            "Technical release source evidence mismatch for "
            f"{variant.variant_id!r}: {exc.code}."
        ) from exc
    if source_binding.manifest() != source_manifest:
        raise ReleaseScopeError(
            f"Technical release source evidence mismatch for {variant.variant_id!r}."
        )

    approval_manifest = item.get("approval_binding")
    if not isinstance(approval_manifest, dict):
        raise ReleaseScopeError(
            f"Technical release approval binding is malformed for {variant.variant_id!r}."
        )
    approval_id = approval_manifest.get("id")
    approval = db.get(Approval, approval_id) if approval_id else None
    review_policy = (
        TECHNICAL_REVIEW_POLICY_V3
        if binding_policy == GOVERNED_TECHNICAL_RELEASE_POLICY_V3
        else TECHNICAL_REVIEW_POLICY_V2
    )
    if (
        approval is None
        or technical_approval_binding(approval) != approval_manifest
        or approval.entity_type != "technical_variant"
        or approval.entity_id != variant.id
        or approval.approval_type != TECHNICAL_REVIEW_APPROVAL_TYPE
        or approval.status != "approved"
        or not approval.requested_by_id
        or not approval.decided_by_id
        or not approval.requested_at
        or not approval.decided_at
        or not approval.decision_reason
        or approval.requested_by_id == approval.decided_by_id
        or approval.decided_by_id == publisher_id
        or approval.snapshot_hash
        != technical_review_snapshot_hash(
            variant,
            source_binding,
            review_policy=review_policy,
        )
    ):
        raise ReleaseScopeError(
            f"Technical release approval mismatch for {variant.variant_id!r}."
        )
    if (
        enforce_source_publisher_independence
        and variant.technical_document_id
        and publisher_id
        in technical_source_reviewer_ids(db, variant.technical_document_id)
    ):
        raise ReleaseScopeError(
            f"Technical release source-review independence mismatch for {variant.variant_id!r}."
        )


def _validate_governed_technical_records_v2(
    db: Session,
    release: LibraryRelease,
    records: list[dict[str, Any]],
) -> None:
    publisher_id = _validate_governed_release_envelope(
        release,
        expected_policy=GOVERNED_TECHNICAL_RELEASE_POLICY_V2,
        records=records,
    )
    if any("record_binding_policy" in item for item in records):
        raise ReleaseScopeError("TAR v2 record contains an unexpected binding policy.")
    record_ids = _governed_record_ids(records)
    variants = {
        item.id: item
        for item in db.scalars(
            select(TechnicalVariant).where(TechnicalVariant.id.in_(set(record_ids)))
        ).all()
    }
    if len(variants) != len(record_ids):
        raise ReleaseScopeError("Governed Technical release refers to a missing variant.")
    for item in records:
        variant = variants[str(item["id"])]
        _validate_governed_technical_record(
            db,
            release,
            item,
            variant,
            binding_policy=GOVERNED_TECHNICAL_RELEASE_POLICY_V2,
            publisher_id=publisher_id,
            enforce_source_publisher_independence=False,
        )


def _manifest_id_list(manifest: dict[str, Any], field: str) -> list[str]:
    value = manifest.get(field)
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
        or value != sorted(set(value))
    ):
        raise ReleaseScopeError(f"TAR v3 {field} partition is malformed.")
    return value


def _normalised_predecessor_record(
    item: dict[str, Any],
    *,
    predecessor_policy: str,
) -> dict[str, Any]:
    normalised = dict(item)
    if predecessor_policy == GOVERNED_TECHNICAL_RELEASE_POLICY_V2:
        if "record_binding_policy" in normalised:
            raise ReleaseScopeError("TAR v2 predecessor record policy is malformed.")
        normalised["record_binding_policy"] = GOVERNED_TECHNICAL_RELEASE_POLICY_V2
    elif (
        predecessor_policy == GOVERNED_TECHNICAL_RELEASE_POLICY_V3
        and normalised.get("record_binding_policy")
        not in {
            GOVERNED_TECHNICAL_RELEASE_POLICY_V2,
            GOVERNED_TECHNICAL_RELEASE_POLICY_V3,
        }
    ):
        raise ReleaseScopeError("TAR v3 predecessor record policy is malformed.")
    return normalised


def _validate_retirement_bindings(
    db: Session,
    release: LibraryRelease,
    predecessor: LibraryRelease,
    predecessor_records: dict[str, dict[str, Any]],
    retired_ids: set[str],
    *,
    publisher_id: str,
) -> None:
    bindings = (release.source_manifest or {}).get('retirement_bindings')
    if not isinstance(bindings, list) or any(
        not isinstance(item, dict) for item in bindings
    ):
        raise ReleaseScopeError('TAR v3 retirement bindings are malformed.')
    binding_ids = [
        str((item.get('request_context') or {}).get('predecessor_record_id') or '')
        if isinstance(item.get('request_context'), dict)
        else ''
        for item in bindings
    ]
    if (
        any(not item_id for item_id in binding_ids)
        or binding_ids != sorted(binding_ids)
        or len(set(binding_ids)) != len(binding_ids)
        or set(binding_ids) != retired_ids
    ):
        raise ReleaseScopeError('TAR v3 retirement binding partition is invalid.')
    for binding, retired_id in zip(bindings, binding_ids, strict=True):
        approval_manifest = binding.get('approval_binding')
        approval_id = (
            approval_manifest.get('id')
            if isinstance(approval_manifest, dict)
            else None
        )
        approval = db.get(Approval, approval_id) if approval_id else None
        variant = db.get(TechnicalVariant, retired_id)
        predecessor_record = predecessor_records.get(retired_id)
        if (
            approval is None
            or variant is None
            or predecessor_record is None
            or variant.status != 'retired'
        ):
            raise ReleaseScopeError('TAR v3 retirement target or receipt is missing.')
        try:
            validate_technical_retirement_binding(
                binding,
                approval,
                predecessor,
                predecessor_record,
                variant,
                publisher_id=publisher_id,
            )
        except TechnicalRetirementError as exc:
            raise ReleaseScopeError(
                f'TAR v3 retirement receipt is invalid: {exc.code}.'
            ) from exc
        if (
            variant.technical_document_id
            and publisher_id
            in technical_source_reviewer_ids(db, variant.technical_document_id)
        ):
            raise ReleaseScopeError(
                'TAR v3 retirement publisher lacks source-review independence.'
            )


def _validate_static_governed_release(
    db: Session,
    release: LibraryRelease,
    *,
    visiting: frozenset[str] = frozenset(),
) -> None:
    """Validate immutable governed lineage without current runtime eligibility checks."""

    if release.id in visiting:
        raise ReleaseScopeError("Governed Technical release predecessor cycle detected.")
    visiting = visiting | {release.id}
    manifest = release.source_manifest or {}
    policy = manifest.get("governance_policy")
    if policy not in {
        GOVERNED_TECHNICAL_RELEASE_POLICY_V2,
        GOVERNED_TECHNICAL_RELEASE_POLICY_V3,
    }:
        raise ReleaseScopeError("Governed Technical predecessor policy is invalid.")
    if not release.release_hash or manifest_hash(manifest) != release.release_hash:
        raise ReleaseScopeError("Governed Technical predecessor hash is invalid.")
    records = _release_records(release)
    publisher_id = _validate_governed_release_envelope(
        release,
        expected_policy=policy,
        records=records,
    )
    record_ids = set(_governed_record_ids(records))
    if policy == GOVERNED_TECHNICAL_RELEASE_POLICY_V2:
        malformed_record_shape = any(
            set(item) != _GOVERNED_TECHNICAL_RECORD_FIELDS_V2 for item in records
        )
    else:
        malformed_record_shape = any(
            set(item)
            != (
                _GOVERNED_TECHNICAL_RECORD_FIELDS_V3
                if item.get("record_binding_policy")
                == GOVERNED_TECHNICAL_RELEASE_POLICY_V3
                else _GOVERNED_TECHNICAL_RECORD_FIELDS_V2_CARRY
            )
            for item in records
        )
    if malformed_record_shape:
        raise ReleaseScopeError("Governed Technical predecessor record shape is invalid.")
    if policy == GOVERNED_TECHNICAL_RELEASE_POLICY_V2:
        return
    if (
        set(manifest) != _GOVERNED_TECHNICAL_V3_MANIFEST_FIELDS
        or manifest.get("runtime_authority") != "release_manifest_membership"
        or manifest.get("activated_draft_ids") != []
        or manifest.get("notes") != release.notes
    ):
        raise ReleaseScopeError("TAR v3 manifest envelope projection is invalid.")

    activated_ids = set(_manifest_id_list(manifest, "activated_candidate_ids"))
    carried_ids = set(_manifest_id_list(manifest, "carried_record_ids"))
    carried_v2_ids = set(_manifest_id_list(manifest, "carried_forward_v2_record_ids"))
    superseded_ids = set(_manifest_id_list(manifest, "superseded_record_ids"))
    retired_ids = set(_manifest_id_list(manifest, "retired_record_ids"))
    removed_ids = superseded_ids | retired_ids
    if (
        activated_ids & carried_ids
        or record_ids != activated_ids | carried_ids
        or record_ids & removed_ids
        or superseded_ids & retired_ids
        or not carried_v2_ids <= carried_ids
    ):
        raise ReleaseScopeError("TAR v3 static record partitions are inconsistent.")
    records_by_id = {str(item["id"]): item for item in records}
    actual_carried_v2_ids = {
        record_id
        for record_id in carried_ids
        if records_by_id[record_id].get("record_binding_policy")
        == GOVERNED_TECHNICAL_RELEASE_POLICY_V2
    }
    if actual_carried_v2_ids != carried_v2_ids or any(
        records_by_id[record_id].get("record_binding_policy")
        != GOVERNED_TECHNICAL_RELEASE_POLICY_V3
        for record_id in activated_ids
    ):
        raise ReleaseScopeError("TAR v3 static binding-policy partitions are inconsistent.")

    predecessor_binding = manifest.get("previous_release")
    previous_release_id = manifest.get("previous_release_id")
    if release.supersedes_release_id is None:
        if (
            predecessor_binding is not None
            or previous_release_id is not None
            or carried_ids
            or removed_ids
            or manifest.get('retirement_bindings') != []
        ):
            raise ReleaseScopeError("TAR v3 static predecessor binding is invalid.")
        return
    if (
        not isinstance(predecessor_binding, dict)
        or set(predecessor_binding) != {"id", "hash", "policy"}
        or predecessor_binding.get("id") != release.supersedes_release_id
        or previous_release_id != release.supersedes_release_id
    ):
        raise ReleaseScopeError("TAR v3 static predecessor identity is invalid.")
    predecessor = db.get(LibraryRelease, release.supersedes_release_id)
    if (
        predecessor is None
        or predecessor.library_type != "technical"
        or predecessor.status != "superseded"
        or predecessor.active_publication_slot is not None
    ):
        raise ReleaseScopeError("TAR v3 static predecessor release is missing.")
    predecessor_manifest = predecessor.source_manifest or {}
    predecessor_policy = predecessor_manifest.get("governance_policy")
    if (
        predecessor_binding.get("hash") != predecessor.release_hash
        or predecessor_binding.get("policy") != predecessor_policy
    ):
        raise ReleaseScopeError("TAR v3 static predecessor binding changed.")
    _validate_static_governed_release(db, predecessor, visiting=visiting)
    raw_predecessor_records = {
        str(item['id']): item for item in _release_records(predecessor)
    }
    predecessor_records = {
        str(item["id"]): _normalised_predecessor_record(
            item,
            predecessor_policy=str(predecessor_policy),
        )
        for item in _release_records(predecessor)
    }
    if set(predecessor_records) != carried_ids | removed_ids:
        raise ReleaseScopeError("TAR v3 static predecessor partition is incomplete.")
    if any(
        records_by_id[record_id] != predecessor_records.get(record_id)
        for record_id in carried_ids
    ):
        raise ReleaseScopeError("TAR v3 static carried record changed.")


    _validate_retirement_bindings(
        db,
        release,
        predecessor,
        raw_predecessor_records,
        retired_ids,
        publisher_id=publisher_id,
    )


def _validate_governed_technical_records_v3(
    db: Session,
    release: LibraryRelease,
    records: list[dict[str, Any]],
) -> None:
    _validate_static_governed_release(db, release)
    manifest = release.source_manifest or {}
    publisher_id = _validate_governed_release_envelope(
        release,
        expected_policy=GOVERNED_TECHNICAL_RELEASE_POLICY_V3,
        records=records,
    )
    record_ids = _governed_record_ids(records)
    record_id_set = set(record_ids)
    activated_ids = set(_manifest_id_list(manifest, "activated_candidate_ids"))
    carried_ids = set(_manifest_id_list(manifest, "carried_record_ids"))
    carried_v2_ids = set(_manifest_id_list(manifest, "carried_forward_v2_record_ids"))
    superseded_ids = set(_manifest_id_list(manifest, "superseded_record_ids"))
    retired_ids = set(_manifest_id_list(manifest, "retired_record_ids"))
    if activated_ids & carried_ids or record_id_set != activated_ids | carried_ids:
        raise ReleaseScopeError("TAR v3 final record partition is inconsistent.")
    if not carried_v2_ids <= carried_ids:
        raise ReleaseScopeError("TAR v3 carried v2 partition is inconsistent.")
    if record_id_set & (superseded_ids | retired_ids) or superseded_ids & retired_ids:
        raise ReleaseScopeError("TAR v3 predecessor removal partition is inconsistent.")

    predecessor_binding = manifest.get("previous_release")
    previous_release_id = manifest.get("previous_release_id")
    predecessor: LibraryRelease | None = None
    predecessor_records: dict[str, dict[str, Any]] = {}
    predecessor_policy: str | None = None
    if release.supersedes_release_id is None:
        if (
            predecessor_binding is not None
            or previous_release_id is not None
            or carried_ids
            or superseded_ids
            or retired_ids
        ):
            raise ReleaseScopeError("TAR v3 has an invalid predecessor binding.")
    else:
        if (
            not isinstance(predecessor_binding, dict)
            or set(predecessor_binding) != {"id", "hash", "policy"}
            or predecessor_binding.get("id") != release.supersedes_release_id
            or previous_release_id != release.supersedes_release_id
        ):
            raise ReleaseScopeError("TAR v3 predecessor identity binding is invalid.")
        predecessor = db.get(LibraryRelease, release.supersedes_release_id)
        if predecessor is None or predecessor.library_type != "technical":
            raise ReleaseScopeError("TAR v3 predecessor release is missing.")
        predecessor_manifest = predecessor.source_manifest or {}
        predecessor_policy = predecessor_manifest.get("governance_policy")
        if predecessor_policy not in {
            GOVERNED_TECHNICAL_RELEASE_POLICY_V2,
            GOVERNED_TECHNICAL_RELEASE_POLICY_V3,
        }:
            raise ReleaseScopeError("TAR v3 predecessor policy is invalid.")
        if (
            predecessor_binding.get("hash") != predecessor.release_hash
            or predecessor_binding.get("policy") != predecessor_policy
            or not predecessor.release_hash
            or manifest_hash(predecessor_manifest) != predecessor.release_hash
        ):
            raise ReleaseScopeError("TAR v3 predecessor hash binding is invalid.")
        raw_predecessor_records = predecessor_manifest.get("records")
        if not isinstance(raw_predecessor_records, list) or any(
            not isinstance(item, dict) for item in raw_predecessor_records
        ):
            raise ReleaseScopeError("TAR v3 predecessor records are malformed.")
        for predecessor_item in raw_predecessor_records:
            predecessor_id = str(predecessor_item.get("id") or "")
            if not predecessor_id or predecessor_id in predecessor_records:
                raise ReleaseScopeError("TAR v3 predecessor record IDs are malformed.")
            predecessor_records[predecessor_id] = _normalised_predecessor_record(
                predecessor_item,
                predecessor_policy=predecessor_policy,
            )
        if set(predecessor_records) != carried_ids | superseded_ids | retired_ids:
            raise ReleaseScopeError("TAR v3 predecessor partition is incomplete.")

    records_by_id = {str(item["id"]): item for item in records}
    for carried_id in carried_ids:
        if records_by_id[carried_id] != predecessor_records.get(carried_id):
            raise ReleaseScopeError("TAR v3 carried record differs from its predecessor.")
    actual_carried_v2_ids = {
        record_id
        for record_id in carried_ids
        if records_by_id[record_id].get("record_binding_policy")
        == GOVERNED_TECHNICAL_RELEASE_POLICY_V2
    }
    if actual_carried_v2_ids != carried_v2_ids:
        raise ReleaseScopeError("TAR v3 carried v2 partition is incomplete.")
    if any(
        records_by_id[record_id].get("record_binding_policy")
        != GOVERNED_TECHNICAL_RELEASE_POLICY_V3
        for record_id in activated_ids
    ):
        raise ReleaseScopeError("TAR v3 newly activated record is not v3-bound.")

    variants = {
        item.id: item
        for item in db.scalars(
            select(TechnicalVariant).where(TechnicalVariant.id.in_(record_id_set))
        ).all()
    }
    if len(variants) != len(record_id_set):
        raise ReleaseScopeError("Governed Technical release refers to a missing variant.")
    governed_member_ids = {
        str(governed_item.get("id") or "")
        for governed_release in db.scalars(
            select(LibraryRelease).where(LibraryRelease.library_type == "technical")
        ).all()
        if (governed_release.source_manifest or {}).get("governance_policy")
        in {
            GOVERNED_TECHNICAL_RELEASE_POLICY_V2,
            GOVERNED_TECHNICAL_RELEASE_POLICY_V3,
        }
        for governed_item in (governed_release.source_manifest or {}).get("records", [])
        if isinstance(governed_item, dict) and governed_item.get("id")
    }
    for item in records:
        binding_policy = item.get("record_binding_policy")
        if binding_policy not in {
            GOVERNED_TECHNICAL_RELEASE_POLICY_V2,
            GOVERNED_TECHNICAL_RELEASE_POLICY_V3,
        }:
            raise ReleaseScopeError("TAR v3 record binding policy is missing or unknown.")
        variant = variants[str(item["id"])]
        _validate_governed_technical_record(
            db,
            release,
            item,
            variant,
            binding_policy=binding_policy,
            publisher_id=publisher_id,
            enforce_source_publisher_independence=True,
        )
        if binding_policy == GOVERNED_TECHNICAL_RELEASE_POLICY_V3:
            unpublished_binding = item.get("unpublished_supersedes_binding")
            if unpublished_binding is not None:
                ancestor_id = unpublished_binding.get("id") if isinstance(
                    unpublished_binding, dict
                ) else None
                ancestor = db.get(TechnicalVariant, ancestor_id) if ancestor_id else None
                ancestor_key = (
                    (ancestor.source_json or {}).get("original_variant_id")
                    or ancestor.variant_id.split("-QFREV")[0]
                    if ancestor is not None
                    else None
                )
                if (
                    not isinstance(unpublished_binding, dict)
                    or set(unpublished_binding) != {"id", "key", "record_hash"}
                    or ancestor is None
                    or ancestor.id == variant.id
                    or variant.supersedes_id != ancestor.id
                    or unpublished_binding.get("key") != ancestor_key
                    or unpublished_binding.get("key") != item.get("key")
                    or unpublished_binding.get("record_hash")
                    != technical_variant_snapshot_hash(ancestor)
                    or ancestor.id in governed_member_ids
                ):
                    raise ReleaseScopeError(
                        "TAR v3 unpublished intake predecessor binding is invalid."
                    )
    predecessor_key_by_id = {
        predecessor_id: str(predecessor_item.get("key") or "")
        for predecessor_id, predecessor_item in predecessor_records.items()
    }
    predecessor_id_by_key = {
        key: predecessor_id
        for predecessor_id, key in predecessor_key_by_id.items()
    }
    for activated_id in activated_ids:
        activated_variant = variants[activated_id]
        activated_item = records_by_id[activated_id]
        claimed_predecessor_id = activated_variant.supersedes_id
        if claimed_predecessor_id in predecessor_key_by_id and (
            claimed_predecessor_id not in superseded_ids
            or predecessor_key_by_id[claimed_predecessor_id]
            != activated_item.get("key")
        ):
            raise ReleaseScopeError(
                "TAR v3 activated record claims a predecessor under a different key."
            )
        prior_same_key_id = predecessor_id_by_key.get(
            str(activated_item.get("key") or "")
        )
        if (
            prior_same_key_id is not None
            and prior_same_key_id in superseded_ids
            and claimed_predecessor_id != prior_same_key_id
        ):
            raise ReleaseScopeError(
                "TAR v3 same-key replacement lacks exact supersession lineage."
            )
        unpublished_binding = activated_item.get("unpublished_supersedes_binding")
        if claimed_predecessor_id in predecessor_key_by_id or claimed_predecessor_id is None:
            if unpublished_binding is not None:
                raise ReleaseScopeError(
                    "TAR v3 published-predecessor lineage has an unexpected intake binding."
                )
        else:
            if (
                not isinstance(unpublished_binding, dict)
                or unpublished_binding.get("id") != claimed_predecessor_id
            ):
                raise ReleaseScopeError(
                    "TAR v3 unpublished intake predecessor binding is invalid."
                )
    for superseded_id in superseded_ids:
        superseded_variant = db.get(TechnicalVariant, superseded_id)
        if superseded_variant is None or superseded_variant.status != "superseded":
            raise ReleaseScopeError("TAR v3 superseded predecessor state is invalid.")
        if not any(
            variant.supersedes_id == superseded_id
            for variant_id, variant in variants.items()
            if variant_id in activated_ids
        ):
            raise ReleaseScopeError("TAR v3 superseded record lacks an exact replacement.")
    for retired_id in retired_ids:
        retired = db.get(TechnicalVariant, retired_id)
        if retired is None or retired.status != "retired":
            raise ReleaseScopeError("TAR v3 retired predecessor state is invalid.")


def _validate_legacy_technical_records(
    db: Session,
    release: LibraryRelease,
    records: list[dict[str, Any]],
) -> None:
    record_ids = [str(item.get("id") or "") for item in records]
    if any(not record_id for record_id in record_ids) or len(set(record_ids)) != len(record_ids):
        raise ReleaseScopeError(
            "Legacy Technical release contains missing or duplicate record IDs."
        )
    variants = {
        variant.id: variant
        for variant in db.scalars(
            select(TechnicalVariant).where(TechnicalVariant.id.in_(set(record_ids)))
        ).all()
    }
    if len(variants) != len(record_ids):
        raise ReleaseScopeError("Legacy Technical release refers to a missing variant.")
    required_fields = {
        "key",
        "variant_id",
        "system_id",
        "frl",
        "source_document_reference",
        "source_page",
        "source_hash",
        "record_version",
    }
    for item in records:
        variant = variants[str(item["id"])]
        if not required_fields.issubset(item):
            raise ReleaseScopeError(
                "Legacy Technical release lacks the canonical historical field bindings."
            )
        _validate_technical_runtime_state(release, variant)
        source = variant.source_json or {}
        expected = {
            "key": source.get("original_variant_id") or variant.variant_id.split("-QFREV")[0],
            "variant_id": variant.variant_id,
            "system_id": variant.system_id,
            "frl": variant.frl,
            "source_document_reference": variant.source_document_reference,
            "source_page": variant.source_page,
            "source_hash": variant.source_hash,
            "record_version": variant.record_version,
        }
        if any(item[field] != value for field, value in expected.items()):
            raise ReleaseScopeError("Legacy Technical release record binding mismatch.")


def validate_release(
    db: Session,
    release: LibraryRelease,
    library_type: str,
    *,
    allowed_statuses: set[str],
    allow_legacy_technical: bool = False,
) -> list[dict[str, Any]]:
    if release.library_type != library_type:
        raise ReleaseScopeError(f"Pinned release type mismatch for {library_type}.")
    if release.status not in allowed_statuses:
        raise ReleaseScopeError(
            f"{library_type.title()} release status {release.status!r} is not runtime eligible."
        )
    if not release.release_hash or not release.source_manifest:
        raise ReleaseScopeError(f"Pinned {library_type} release is not immutable.")
    if manifest_hash(release.source_manifest) != release.release_hash:
        raise ReleaseScopeError(f"Pinned {library_type} release hash does not match its manifest.")
    records = _release_records(release)
    if library_type == "technical":
        manifest = release.source_manifest or {}
        governance_policy = manifest.get("governance_policy")
        if governance_policy == GOVERNED_TECHNICAL_RELEASE_POLICY_V2:
            _validate_governed_technical_records_v2(db, release, records)
        elif governance_policy == GOVERNED_TECHNICAL_RELEASE_POLICY_V3:
            _validate_governed_technical_records_v3(db, release, records)
        elif governance_policy is None and allow_legacy_technical:
            _validate_legacy_technical_records(db, release, records)
        elif governance_policy is not None:
            raise ReleaseScopeError("Technical release governance policy is unknown.")
        else:
            raise ReleaseScopeError(
                "Legacy Technical release cannot be used for new runtime selection or pinning."
            )
    return records


def pinned_release(db: Session, estimate: Estimate, library_type: str) -> LibraryRelease:
    field = PIN_FIELDS.get(library_type)
    if not field:
        raise ReleaseScopeError(f"Unsupported pinned library type: {library_type}")
    release_id = getattr(estimate, field, None)
    if not release_id:
        raise ReleaseScopeError(f"Estimate has no pinned {library_type} release.")
    release = db.get(LibraryRelease, release_id)
    if not release:
        raise ReleaseScopeError(f"Pinned {library_type} release record is missing.")
    validate_release(
        db,
        release,
        library_type,
        allowed_statuses={"active", "superseded"},
    )
    return release


def release_record_ids(db: Session, estimate: Estimate, library_type: str) -> set[str]:
    release = pinned_release(db, estimate, library_type)
    records = validate_release(
        db,
        release,
        library_type,
        allowed_statuses={"active", "superseded"},
    )
    ids = {str(item["id"]) for item in records if isinstance(item, dict) and item.get("id")}
    return ids


def active_release_record_ids(db: Session, library_type: str) -> set[str]:
    statement = select(LibraryRelease).where(
        LibraryRelease.library_type == library_type,
        LibraryRelease.status == "active",
    )
    if library_type == "technical":
        statement = statement.where(LibraryRelease.active_publication_slot == "technical")
    release = db.scalar(statement.order_by(LibraryRelease.created_at.desc()))
    if release is None:
        raise ReleaseScopeError(f"No active {library_type} release exists.")
    records = validate_release(
        db,
        release,
        library_type,
        allowed_statuses={"active"},
    )
    return {str(item["id"]) for item in records if item.get("id")}


def pinned_product(db: Session, estimate: Estimate, sku: str) -> Product:
    ids = release_record_ids(db, estimate, "products")
    item = db.scalar(select(Product).where(Product.id.in_(ids), Product.sku == sku))
    if not item:
        raise ReleaseScopeError(
            f"Product/material {sku!r} is not present in the pinned Products release."
        )
    return item


def pinned_labour(db: Session, estimate: Estimate, code: str) -> LabourComponent:
    ids = release_record_ids(db, estimate, "labour")
    item = db.scalar(
        select(LabourComponent).where(LabourComponent.id.in_(ids), LabourComponent.code == code)
    )
    if not item:
        raise ReleaseScopeError(
            f"Labour component {code!r} is not present in the pinned Labour release."
        )
    return item


def pinned_pricing_record(
    db: Session, estimate: Estimate, pkb_entry_id: str
) -> PricingLibraryRecord:
    ids = release_record_ids(db, estimate, "pricing")
    item = db.scalar(
        select(PricingLibraryRecord).where(
            PricingLibraryRecord.id.in_(ids), PricingLibraryRecord.pkb_entry_id == pkb_entry_id
        )
    )
    if not item:
        raise ReleaseScopeError(
            f"Pricing record {pkb_entry_id!r} is not present in the pinned Pricing release."
        )
    return item


def pinned_markup_profiles(db: Session, estimate: Estimate) -> list[MarkupProfile]:
    ids = release_record_ids(db, estimate, "markups")
    return list(db.scalars(select(MarkupProfile).where(MarkupProfile.id.in_(ids))).all())


def pinned_technical_ids(db: Session, estimate: Estimate) -> set[str]:
    return release_record_ids(db, estimate, "technical")


def pinned_rule_ids(db: Session, estimate: Estimate) -> set[str]:
    return release_record_ids(db, estimate, "rules")


def pinned_rules(db: Session, estimate: Estimate) -> list[EstimatingRule]:
    ids = pinned_rule_ids(db, estimate)
    return list(
        db.scalars(
            select(EstimatingRule)
            .where(EstimatingRule.id.in_(ids))
            .order_by(EstimatingRule.priority.asc(), EstimatingRule.rule_code.asc())
        ).all()
    )


def validate_runtime_scope(db: Session, estimate: Estimate) -> list[str]:
    errors: list[str] = []
    for kind in PIN_FIELDS:
        try:
            release_record_ids(db, estimate, kind)
        except ReleaseScopeError as exc:
            errors.append(str(exc))
    if estimate.technical_release_id:
        try:
            allowed = pinned_technical_ids(db, estimate)
            for opening in estimate.openings:
                if (
                    opening.selected_technical_variant_id
                    and opening.selected_technical_variant_id not in allowed
                ):
                    errors.append(
                        f"Opening {opening.opening_code}: selected technical variant "
                        "is not in the pinned Technical release."
                    )
        except ReleaseScopeError:
            pass
    return errors
