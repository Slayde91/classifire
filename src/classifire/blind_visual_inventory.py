from __future__ import annotations

from typing import Any


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

BLIND_RECONCILIATION_DISPOSITIONS = frozenset(
    {
        "ACCOUNTED_FOR",
        "DUPLICATE_OR_SAME_ITEM",
        "NOT_TOPOLOGY",
        "RESOLVED_NONSTRUCTURAL",
        "UNRESOLVED",
    }
)


def _blind_observation_rows(
    inventory: dict[str, Any],
) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []

    openings = inventory.get(
        "candidate_openings"
    )

    if isinstance(openings, list):
        for item in openings:
            if not isinstance(item, dict):
                continue

            candidate_id = str(
                item.get("candidate_id")
                or ""
            ).strip()

            if candidate_id:
                rows.append(
                    (
                        candidate_id,
                        "opening",
                    )
                )

    services = inventory.get(
        "candidate_services"
    )

    if isinstance(services, list):
        for item in services:
            if not isinstance(item, dict):
                continue

            candidate_id = str(
                item.get("candidate_id")
                or ""
            ).strip()

            if candidate_id:
                rows.append(
                    (
                        candidate_id,
                        "service",
                    )
                )

    unresolved = inventory.get(
        "unresolved_candidates"
    )

    if isinstance(unresolved, list):
        for index, item in enumerate(
            unresolved,
            start=1,
        ):
            if not isinstance(item, dict):
                continue

            candidate_id = str(
                item.get("candidate_id")
                or ""
            ).strip()

            if not candidate_id:
                candidate_id = (
                    f"V-U-{index:03d}"
                )

            kind = str(
                item.get("kind")
                or "unknown"
            ).strip().lower()

            rows.append(
                (
                    candidate_id,
                    f"unresolved:{kind}",
                )
            )

    limitations = inventory.get(
        "limitations"
    )

    if isinstance(limitations, list):
        for index, item in enumerate(
            limitations,
            start=1,
        ):
            if (
                isinstance(item, str)
                and item.strip()
            ):
                rows.append(
                    (
                        f"V-L-{index:03d}",
                        "limitation",
                    )
                )

    return rows


def blind_observation_catalog(
    inventory: dict[str, Any],
) -> dict[str, str]:
    """Return the IDs that the conditioned Validator must reconcile."""

    return {
        candidate_id: kind
        for candidate_id, kind
        in _blind_observation_rows(
            inventory
        )
    }


def _proposal_reference_sets(
    proposal: dict[str, Any],
) -> tuple[set[str], set[str]]:
    opening_refs: set[str] = set()
    service_refs: set[str] = set()

    openings = proposal.get(
        "openings"
    )

    if isinstance(openings, list):
        for item in openings:
            if not isinstance(item, dict):
                continue

            code = str(
                item.get("opening_code")
                or ""
            ).strip()

            if code:
                opening_refs.add(
                    code
                )

    services = proposal.get(
        "services"
    )

    if isinstance(services, list):
        for item in services:
            if not isinstance(item, dict):
                continue

            code = str(
                item.get("service_code")
                or ""
            ).strip()

            if code:
                service_refs.add(
                    code
                )

    return (
        opening_refs,
        service_refs,
    )


def validate_blind_reconciliation_payload(
    inventory: dict[str, Any],
    proposal: dict[str, Any],
    validator: dict[str, Any],
) -> list[str]:
    """
    Validate the v3 blind-observation reconciliation ledger.

    Raw blind counts are deliberately NOT required to equal Physical counts.
    Approval instead requires every independent blind observation to receive
    exactly one evidence-backed disposition, with no UNRESOLVED disposition.
    """

    errors: list[str] = [
        "blind inventory invalid: " + item
        for item in (
            validate_blind_visual_inventory_payload(
                inventory
            )
        )
    ]

    observation_rows = (
        _blind_observation_rows(
            inventory
        )
    )

    observation_catalog: dict[
        str,
        str,
    ] = {}

    for candidate_id, kind in observation_rows:
        if candidate_id in observation_catalog:
            errors.append(
                "duplicate blind observation id "
                + candidate_id
            )
            continue

        observation_catalog[
            candidate_id
        ] = kind

    opening_refs, service_refs = (
        _proposal_reference_sets(
            proposal
        )
    )

    all_proposal_refs = (
        opening_refs
        | service_refs
    )

    ledger = validator.get(
        "blind_reconciliation"
    )

    if not isinstance(ledger, list):
        errors.append(
            "blind_reconciliation must be an array"
        )

        return list(
            dict.fromkeys(
                errors
            )
        )

    seen: set[str] = set()
    dispositions: dict[str, str] = {}

    mapped_claims: dict[
        tuple[str, str],
        list[tuple[str, str]],
    ] = {}

    mapped_dispositions = {
        "ACCOUNTED_FOR",
        "DUPLICATE_OR_SAME_ITEM",
    }

    no_ref_dispositions = {
        "NOT_TOPOLOGY",
        "RESOLVED_NONSTRUCTURAL",
    }

    for index, item in enumerate(
        ledger,
        start=1,
    ):
        if not isinstance(item, dict):
            errors.append(
                f"blind reconciliation {index} "
                "is not an object"
            )
            continue

        candidate_id = str(
            item.get(
                "blind_candidate_id"
            )
            or ""
        ).strip()

        if not candidate_id:
            errors.append(
                f"blind reconciliation {index} "
                "has no blind_candidate_id"
            )
            continue

        if candidate_id not in observation_catalog:
            errors.append(
                f"blind reconciliation {index} "
                f"references unknown observation "
                f"{candidate_id}"
            )
            continue

        if candidate_id in seen:
            errors.append(
                "blind observation reconciled "
                f"more than once: {candidate_id}"
            )
            continue

        seen.add(
            candidate_id
        )

        disposition = str(
            item.get(
                "disposition"
            )
            or ""
        ).strip().upper()

        if (
            disposition
            not in BLIND_RECONCILIATION_DISPOSITIONS
        ):
            errors.append(
                f"blind reconciliation {index} "
                f"has unsupported disposition "
                f"{disposition!r}"
            )
            continue

        dispositions[
            candidate_id
        ] = disposition

        detail = str(
            item.get("detail")
            or ""
        ).strip()

        if not detail:
            errors.append(
                f"blind reconciliation {index} "
                "has no detail"
            )

        if not _non_empty_string_list(
            item.get(
                "evidence_refs"
            )
        ):
            errors.append(
                f"blind reconciliation {index} "
                "must have evidence_refs"
            )

        raw_refs = item.get(
            "proposal_refs"
        )

        if not isinstance(raw_refs, list):
            errors.append(
                f"blind reconciliation {index} "
                "proposal_refs must be an array"
            )
            refs: list[str] = []
        else:
            refs = []

            for raw_ref in raw_refs:
                if (
                    not isinstance(
                        raw_ref,
                        str,
                    )
                    or not raw_ref.strip()
                ):
                    errors.append(
                        f"blind reconciliation {index} "
                        "contains an invalid proposal_ref"
                    )
                    continue

                ref = raw_ref.strip()

                if ref in refs:
                    errors.append(
                        f"blind reconciliation {index} "
                        f"repeats proposal_ref {ref}"
                    )
                    continue

                refs.append(
                    ref
                )

                if ref not in all_proposal_refs:
                    errors.append(
                        f"blind reconciliation {index} "
                        f"references unknown proposal item "
                        f"{ref}"
                    )

        kind = observation_catalog[
            candidate_id
        ]

        if (
            disposition
            in mapped_dispositions
            and not refs
        ):
            errors.append(
                f"{candidate_id} disposition "
                f"{disposition} requires proposal_refs"
            )

        if (
            disposition
            in no_ref_dispositions
            and refs
        ):
            errors.append(
                f"{candidate_id} disposition "
                f"{disposition} cannot have proposal_refs"
            )

        if (
            disposition
            == "RESOLVED_NONSTRUCTURAL"
            and kind
            not in {
                "unresolved:barrier",
                "unresolved:classification",
                "unresolved:photo_relationship",
                "limitation",
            }
        ):
            errors.append(
                f"{candidate_id} cannot use "
                "RESOLVED_NONSTRUCTURAL for "
                f"observation kind {kind}"
            )

        if disposition in mapped_dispositions:
            if kind in {
                "opening",
                "unresolved:opening",
            }:
                invalid = [
                    ref
                    for ref in refs
                    if ref not in opening_refs
                ]

                if invalid:
                    errors.append(
                        f"{candidate_id} Opening observation "
                        "must map only to proposal Openings"
                    )

            elif kind in {
                "service",
                "unresolved:service",
            }:
                invalid = [
                    ref
                    for ref in refs
                    if ref not in service_refs
                ]

                if invalid:
                    errors.append(
                        f"{candidate_id} Service observation "
                        "must map only to proposal Services"
                    )

            elif kind == "unresolved:link":
                has_opening = any(
                    ref in opening_refs
                    for ref in refs
                )

                has_service = any(
                    ref in service_refs
                    for ref in refs
                )

                if not (
                    has_opening
                    and has_service
                ):
                    errors.append(
                        f"{candidate_id} link observation "
                        "must map to at least one proposal "
                        "Opening and one proposal Service"
                    )

        if (
            kind in {
                "opening",
                "service",
            }
            and disposition
            in mapped_dispositions
        ):
            for ref in refs:
                if (
                    kind == "opening"
                    and ref not in opening_refs
                ):
                    continue

                if (
                    kind == "service"
                    and ref not in service_refs
                ):
                    continue

                mapped_claims.setdefault(
                    (
                        kind,
                        ref,
                    ),
                    [],
                ).append(
                    (
                        candidate_id,
                        disposition,
                    )
                )

    expected_ids = set(
        observation_catalog
    )

    missing_ids = sorted(
        expected_ids
        - seen
    )

    for candidate_id in missing_ids:
        errors.append(
            "blind observation has no reconciliation: "
            + candidate_id
        )

    for (
        kind,
        proposal_ref,
    ), claims in mapped_claims.items():
        if len(claims) <= 1:
            continue

        accounted = [
            candidate_id
            for (
                candidate_id,
                disposition,
            )
            in claims
            if disposition
            == "ACCOUNTED_FOR"
        ]

        duplicates = [
            candidate_id
            for (
                candidate_id,
                disposition,
            )
            in claims
            if disposition
            == "DUPLICATE_OR_SAME_ITEM"
        ]

        if (
            len(accounted) != 1
            or (
                len(accounted)
                + len(duplicates)
                != len(claims)
            )
        ):
            errors.append(
                f"multiple blind {kind} observations "
                f"map to {proposal_ref}; exactly one must "
                "be ACCOUNTED_FOR and the others must be "
                "DUPLICATE_OR_SAME_ITEM"
            )

    verdict = str(
        validator.get("verdict")
        or ""
    ).strip().upper()

    if verdict == "APPROVED":
        unresolved_ids = sorted(
            candidate_id
            for (
                candidate_id,
                disposition,
            )
            in dispositions.items()
            if disposition
            == "UNRESOLVED"
        )

        if unresolved_ids:
            errors.append(
                "APPROVED validator cannot leave blind "
                "observations UNRESOLVED: "
                + ", ".join(
                    unresolved_ids
                )
            )

    return list(
        dict.fromkeys(
            errors
        )
    )
