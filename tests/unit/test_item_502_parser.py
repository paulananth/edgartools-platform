from __future__ import annotations

from datetime import date

from edgar_warehouse.parsers.item_502 import (
    EmploymentEvent,
    apply_employment_events,
    parse_item_502,
)


def test_parse_item_502_appointment_and_departure() -> None:
    appointment = parse_item_502(
        accession_number="a1",
        cik=1,
        filing_date=date(2024, 4, 2),
        content="<h2>Item 5.02</h2><p>Jane Doe was appointed as Chief Financial Officer, effective April 1, 2024.</p>",
    )
    assert appointment.applicability == "applicable"
    assert appointment.events[0].event_type == "appointment"
    assert appointment.events[0].person_name == "Jane Doe"
    assert appointment.events[0].effective_date == date(2024, 4, 1)

    departure = parse_item_502(
        accession_number="a2",
        cik=1,
        filing_date=date(2025, 1, 3),
        content="Item 5.02 Jane Doe resigned as Chief Financial Officer effective January 2, 2025.",
    )
    assert departure.events[0].event_type == "departure"


def test_item_502_stable_not_applicable_and_temporal_sequence() -> None:
    result = parse_item_502(
        accession_number="x",
        cik=1,
        filing_date=date(2024, 1, 1),
        content="Item 5.02. The board approved a director compensation policy.",
    )
    assert result.applicability == "not_applicable"
    assert result.reason_code == "no_named_employment_event"

    versions = apply_employment_events(
        [],
        [
            EmploymentEvent("a1", 1, "appointment", "Jane Doe", "CFO", date(2024, 4, 1)),
            EmploymentEvent("a2", 1, "departure", "Jane Doe", "CFO", date(2025, 1, 2)),
        ],
    )
    assert versions[0].valid_from == date(2024, 4, 1)
    assert versions[0].valid_to == date(2025, 1, 2)


def test_parse_item_502_role_and_compensation_changes() -> None:
    role_change = parse_item_502(
        accession_number="r1", cik=1, filing_date=date(2024, 6, 2),
        content=("Item 5.02 Jane Doe was promoted from Chief Financial Officer "
                 "to Chief Executive Officer effective June 1, 2024."),
    )
    assert role_change.events[0].event_type == "role_change"
    assert role_change.events[0].role == "Chief Executive Officer"

    compensation = parse_item_502(
        accession_number="c1", cik=1, filing_date=date(2024, 7, 2),
        content=("Item 5.02 The board approved an annual base salary of $750,000 "
                 "for Jane Doe effective July 1, 2024."),
    )
    assert compensation.events[0].event_type == "compensation_change"
    assert compensation.events[0].compensation_amount == 750000
