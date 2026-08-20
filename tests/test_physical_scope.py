from __future__ import annotations

from physical_foundation_support import (
    add_estimate,
    add_opening,
    add_service,
    add_service_link,
    physical_session,
)

from classifire.services.physical_scope import assess_physical_model_completeness


def test_blank_opening_without_a_service_link_is_complete() -> None:
    with physical_session() as session:
        estimate = add_estimate(session)
        opening = add_opening(session, estimate, opening_type="empty core hole")

        assessment = assess_physical_model_completeness(session, estimate.id)

        assert assessment.complete
        assert assessment.opening_count == 1
        assert assessment.openings[0].opening_id == opening.id
        assert assessment.openings[0].blank_opening
        assert assessment.openings[0].service_link_count == 0
        assert assessment.openings[0].missing_fields == ()


def test_blank_opening_seal_is_a_governed_blank_opening_alias() -> None:
    with physical_session() as session:
        estimate = add_estimate(session)
        add_opening(session, estimate, opening_type="blank opening seal")

        assessment = assess_physical_model_completeness(session, estimate.id)

        assert assessment.complete
        assert assessment.openings[0].blank_opening
        assert assessment.openings[0].opening_type == "blank_opening"


def test_blank_opening_with_a_service_link_is_rejected_as_inconsistent() -> None:
    with physical_session() as session:
        estimate = add_estimate(session)
        opening = add_opening(session, estimate, opening_type="blank core hole")
        service = add_service(session, opening)
        add_service_link(session, service, opening)

        assessment = assess_physical_model_completeness(session, estimate.id)
        row = assessment.openings[0]

        assert not assessment.complete
        assert row.blank_opening
        assert not row.service_relationship_complete
        assert row.service_link_count == 1
        assert "blank_opening_must_not_have_service_links" in row.missing_fields


def test_service_penetration_without_a_canonical_link_is_incomplete() -> None:
    with physical_session() as session:
        estimate = add_estimate(session)
        add_opening(session, estimate)

        assessment = assess_physical_model_completeness(session, estimate.id)
        row = assessment.openings[0]

        assert not assessment.complete
        assert not row.blank_opening
        assert not row.service_relationship_complete
        assert "service_opening_link_or_blank_opening_classification" in row.missing_fields


def test_multiple_services_linked_to_one_opening_are_complete() -> None:
    with physical_session() as session:
        estimate = add_estimate(session)
        opening = add_opening(session, estimate)
        first = add_service(session, opening, service_code="SVC-001")
        second = add_service(session, opening, service_code="SVC-002", material="copper")
        add_service_link(session, first, opening)
        add_service_link(session, second, opening)

        assessment = assess_physical_model_completeness(session, estimate.id)
        row = assessment.openings[0]

        assert assessment.complete
        assert row.service_relationship_complete
        assert row.service_link_count == 2
