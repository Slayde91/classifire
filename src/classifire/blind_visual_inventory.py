from __future__ import annotations

from typing import Any

from classifire.services.physical_scope import (
    is_blank_opening_type,
)


BLIND_INVENTORY_COMPLETE = "COMPLETE"
BLIND_INVENTORY_BLOCKED = "BLOCKED"

BLIND_INVENTORY_STATUSES = frozenset(
    {
        BLIND_INVENTORY_COMPLETE,
        BLIND_INVENTORY_BLOCKED,
    }
)

BLIND_UNRESOLVED_KINDS = frozenset(
    {
        "barrier",
        "opening",
        "service",
        "link",
        "classification",
        "photo_relationship",
    }
)


def _non_negative_int(
    value: Any,
) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    )


def _positive_int_or_none(
    value: Any,
) -> bool:
    if value is None:
        return True

    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 1
    )


def _non_empty_string_list(
    value: Any,
) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(
            isinstance(item, str)
            and bool(item.strip())
            for item in value
        )
    )


def validate_blind_visual_inventory_payload(
    payload: dict[str, Any],
) -> list[str]:
    """Validate one proposal-blind visual inventory receipt."""

    if not isinstance(payload, dict):
        return [
            "blind validator inventory must be an object"
        ]

    errors: list[str] = []

    status = str(
        payload.get("status") or ""
    ).strip().upper()

    if status not in BLIND_INVENTORY_STATUSES:
        errors.append(
            "blind inventory status must be COMPLETE or BLOCKED"
        )

    openings = payload.get(
        "candidate_openings"
    )

    services = payload.get(
        "candidate_services"
    )

    unresolved = payload.get(
        "unresolved_candidates"
    )

    limitations = payload.get(
        "limitations"
    )

    if not isinstance(openings, list):
        errors.append(
            "candidate_openings must be an array"
        )
        openings = []

    if not isinstance(services, list):
        errors.append(
            "candidate_services must be an array"
        )
        services = []

    if not isinstance(unresolved, list):
        errors.append(
            "unresolved_candidates must be an array"
        )
        unresolved = []

    if not isinstance(limitations, list):
        errors.append(
            "limitations must be an array"
        )
        limitations = []
    else:
        for index, item in enumerate(
            limitations,
            start=1,
        ):
            if (
                not isinstance(item, str)
                or not item.strip()
            ):
                errors.append(
                    f"limitation {index} must be a non-empty string"
                )

    opening_count = payload.get(
        "observed_opening_count"
    )

    service_count = payload.get(
        "observed_service_group_count"
    )

    if not _non_negative_int(
        opening_count
    ):
        errors.append(
            "observed_opening_count must be a "
            "non-negative integer"
        )
    elif opening_count != len(openings):
        errors.append(
            "observed_opening_count must equal "
            "candidate_openings length"
        )

    if not _non_negative_int(
        service_count
    ):
        errors.append(
            "observed_service_group_count must be a "
            "non-negative integer"
        )
    elif service_count != len(services):
        errors.append(
            "observed_service_group_count must equal "
            "candidate_services length"
        )

    opening_ids: set[str] = set()
    opening_blank: dict[str, bool] = {}

    for index, item in enumerate(
        openings,
        start=1,
    ):
        if not isinstance(item, dict):
            errors.append(
                f"candidate opening {index} is not an object"
            )
            continue

        candidate_id = str(
            item.get("candidate_id") or ""
        ).strip()

        if not candidate_id:
            errors.append(
                f"candidate opening {index} has no candidate_id"
            )
        elif candidate_id in opening_ids:
            errors.append(
                "duplicate candidate opening id "
                + candidate_id
            )
        else:
            opening_ids.add(
                candidate_id
            )

        blank = item.get(
            "blank"
        )

        if not isinstance(blank, bool):
            errors.append(
                f"candidate opening {index} blank must be boolean"
            )
        elif candidate_id:
            opening_blank[
                candidate_id
            ] = blank

        detail = str(
            item.get("detail") or ""
        ).strip()

        if not detail:
            errors.append(
                f"candidate opening {index} has no detail"
            )

        if not _non_empty_string_list(
            item.get("evidence_refs")
        ):
            errors.append(
                f"candidate opening {index} must have evidence_refs"
            )

    service_ids: set[str] = set()
    opening_link_counts: dict[str, int] = {
        opening_id: 0
        for opening_id in opening_ids
    }

    for index, item in enumerate(
        services,
        start=1,
    ):
        if not isinstance(item, dict):
            errors.append(
                f"candidate service {index} is not an object"
            )
            continue

        candidate_id = str(
            item.get("candidate_id") or ""
        ).strip()

        if not candidate_id:
            errors.append(
                f"candidate service {index} has no candidate_id"
            )
        elif candidate_id in service_ids:
            errors.append(
                "duplicate candidate service id "
                + candidate_id
            )
        else:
            service_ids.add(
                candidate_id
            )

        detail = str(
            item.get("detail") or ""
        ).strip()

        if not detail:
            errors.append(
                f"candidate service {index} has no detail"
            )

        if not _non_empty_string_list(
            item.get("evidence_refs")
        ):
            errors.append(
                f"candidate service {index} must have evidence_refs"
            )

        service_type = str(
            item.get("service_type") or ""
        ).strip()

        if not service_type:
            errors.append(
                f"candidate service {index} has no service_type"
            )

        if not _positive_int_or_none(
            item.get("quantity")
        ):
            errors.append(
                f"candidate service {index} quantity "
                "must be a positive integer or null"
            )

        linked_openings = item.get(
            "candidate_opening_ids"
        )

        if not isinstance(
            linked_openings,
            list,
        ):
            errors.append(
                f"candidate service {index} "
                "candidate_opening_ids must be an array"
            )
            linked_openings = []

        if (
            status
            == BLIND_INVENTORY_COMPLETE
            and not linked_openings
        ):
            errors.append(
                f"COMPLETE inventory candidate service "
                f"{index} has no opening relationship"
            )

        seen_links: set[str] = set()

        for linked_id_value in linked_openings:
            linked_id = (
                linked_id_value.strip()
                if isinstance(
                    linked_id_value,
                    str,
                )
                else ""
            )

            if not linked_id:
                errors.append(
                    f"candidate service {index} has an "
                    "invalid candidate_opening_id"
                )
                continue

            if linked_id in seen_links:
                errors.append(
                    f"candidate service {index} repeats "
                    f"opening link {linked_id}"
                )
                continue

            seen_links.add(
                linked_id
            )

            if linked_id not in opening_ids:
                errors.append(
                    f"candidate service {index} references "
                    f"unknown opening {linked_id}"
                )
                continue

            opening_link_counts[
                linked_id
            ] += 1

    if (
        status
        == BLIND_INVENTORY_COMPLETE
    ):
        for opening_id in sorted(
            opening_ids
        ):
            blank = opening_blank.get(
                opening_id
            )

            linked_count = (
                opening_link_counts.get(
                    opening_id,
                    0,
                )
            )

            if blank is True and linked_count:
                errors.append(
                    f"COMPLETE blind opening {opening_id} "
                    "is blank but has Service links"
                )

            if blank is False and linked_count == 0:
                errors.append(
                    f"COMPLETE occupied opening {opening_id} "
                    "has no Service group"
                )

    for index, item in enumerate(
        unresolved,
        start=1,
    ):
        if not isinstance(item, dict):
            errors.append(
                f"unresolved candidate {index} is not an object"
            )
            continue

        kind = str(
            item.get("kind") or ""
        ).strip().lower()

        if kind not in BLIND_UNRESOLVED_KINDS:
            errors.append(
                f"unresolved candidate {index} has "
                f"unsupported kind {kind!r}"
            )

        detail = str(
            item.get("detail") or ""
        ).strip()

        if not detail:
            errors.append(
                f"unresolved candidate {index} has no detail"
            )

        if not _non_empty_string_list(
            item.get("evidence_refs")
        ):
            errors.append(
                f"unresolved candidate {index} must have "
                "evidence_refs"
            )

    if (
        status
        == BLIND_INVENTORY_COMPLETE
        and unresolved
    ):
        errors.append(
            "COMPLETE blind inventory cannot contain "
            "unresolved candidates"
        )

    if (
        status
        == BLIND_INVENTORY_BLOCKED
        and not unresolved
        and not limitations
    ):
        errors.append(
            "BLOCKED blind inventory must state an "
            "unresolved candidate or limitation"
        )

    return list(
        dict.fromkeys(
            errors
        )
    )


def _proposal_blank_opening_count(
    proposal: dict[str, Any],
) -> int:
    openings = proposal.get(
        "openings"
    )

    if not isinstance(
        openings,
        list,
    ):
        return -1

    count = 0

    for opening in openings:
        if not isinstance(
            opening,
            dict,
        ):
            continue

        opening_type = str(
            opening.get(
                "opening_type"
            )
            or ""
        )

        if is_blank_opening_type(
            opening_type
        ):
            count += 1

    return count


def blind_inventory_approval_errors(
    inventory: dict[str, Any],
    proposal: dict[str, Any],
) -> list[str]:
    """Return reasons a proposal cannot pass the blind gate."""

    errors = [
        "blind inventory invalid: " + item
        for item in (
            validate_blind_visual_inventory_payload(
                inventory
            )
        )
    ]

    status = str(
        inventory.get("status") or ""
    ).strip().upper()

    if status != BLIND_INVENTORY_COMPLETE:
        errors.append(
            "APPROVED validator requires a COMPLETE "
            "blind inventory"
        )

    unresolved = inventory.get(
        "unresolved_candidates"
    )

    if (
        isinstance(
            unresolved,
            list,
        )
        and unresolved
    ):
        errors.append(
            "APPROVED validator cannot leave blind "
            "inventory candidates unresolved"
        )

    proposal_openings = proposal.get(
        "openings"
    )

    proposal_services = proposal.get(
        "services"
    )

    if not isinstance(
        proposal_openings,
        list,
    ):
        errors.append(
            "proposal openings must be an array"
        )
        proposal_opening_count = -1
    else:
        proposal_opening_count = len(
            proposal_openings
        )

    if not isinstance(
        proposal_services,
        list,
    ):
        errors.append(
            "proposal services must be an array"
        )
        proposal_service_count = -1
    else:
        proposal_service_count = len(
            proposal_services
        )

    inventory_opening_count = inventory.get(
        "observed_opening_count"
    )

    inventory_service_count = inventory.get(
        "observed_service_group_count"
    )

    if (
        _non_negative_int(
            inventory_opening_count
        )
        and proposal_opening_count >= 0
        and inventory_opening_count
        != proposal_opening_count
    ):
        errors.append(
            "blind inventory / proposal Opening count "
            "contradiction: "
            f"blind={inventory_opening_count}, "
            f"proposal={proposal_opening_count}"
        )

    if (
        _non_negative_int(
            inventory_service_count
        )
        and proposal_service_count >= 0
        and inventory_service_count
        != proposal_service_count
    ):
        errors.append(
            "blind inventory / proposal Service-group count "
            "contradiction: "
            f"blind={inventory_service_count}, "
            f"proposal={proposal_service_count}"
        )

    blind_openings = inventory.get(
        "candidate_openings"
    )

    if (
        isinstance(
            blind_openings,
            list,
        )
        and proposal_opening_count >= 0
    ):
        blind_blank_count = sum(
            1
            for opening in blind_openings
            if (
                isinstance(
                    opening,
                    dict,
                )
                and opening.get("blank")
                is True
            )
        )

        proposal_blank_count = (
            _proposal_blank_opening_count(
                proposal
            )
        )

        if (
            proposal_blank_count >= 0
            and blind_blank_count
            != proposal_blank_count
        ):
            errors.append(
                "blind inventory / proposal blank-Opening "
                "count contradiction: "
                f"blind={blind_blank_count}, "
                f"proposal={proposal_blank_count}"
            )

    return list(
        dict.fromkeys(
            errors
        )
    )


def blind_inventory_block_reasons(
    inventory: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []

    unresolved = inventory.get(
        "unresolved_candidates"
    )

    if isinstance(
        unresolved,
        list,
    ):
        for item in unresolved:
            if not isinstance(
                item,
                dict,
            ):
                continue

            detail = str(
                item.get("detail") or ""
            ).strip()

            if detail:
                reasons.append(
                    detail
                )

    limitations = inventory.get(
        "limitations"
    )

    if isinstance(
        limitations,
        list,
    ):
        reasons.extend(
            str(item).strip()
            for item in limitations
            if str(item).strip()
        )

    if not reasons:
        reasons.append(
            "blind validator could not establish a "
            "complete physical inventory"
        )

    return list(
        dict.fromkeys(
            reasons
        )
    )
