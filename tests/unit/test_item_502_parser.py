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


def test_item_502_not_poisoned_by_later_item_507_vote_tally() -> None:
    """Production regression: CIK 315213, accession 0000315213-26-000029.

    A combined 5.02+5.07 annual-meeting 8-K where Item 5.02 is pure boilerplate
    (cross-referencing the plan-approval vote) and Item 5.07's routine director
    vote tally uses "named" — an ambiguity keyword the unscoped fallback used to
    match anywhere in the document, wrongly marking the filing "unresolved".
    """
    result = parse_item_502(
        accession_number="0000315213-26-000029", cik=315213, filing_date=date(2026, 5, 14),
        content=(
            "Item 5.02 Departure of Directors or Certain Officers; Election of Directors; "
            "Appointment of Certain Officers; Compensatory Arrangements of Certain Officers. "
            "At the Annual Meeting, stockholders approved the amended and restated Stock "
            "Incentive Plan, as described in Item 5.07 below. "
            "Item 5.07 Submission of Matters to a Vote of Security Holders. "
            "At the Annual Meeting held on May 14, 2026, stockholders voted on the election "
            "of the eight directors named below, each of whom was elected. "
            "Item 9.01 Financial Statements and Exhibits."
        ),
    )
    assert result.applicability == "not_applicable"
    assert result.reason_code == "no_named_employment_event"
    assert result.events == ()


def test_item_502_active_voice_appointment_with_leading_date() -> None:
    """Production coverage gap: CIK 14693 (Brown-Forman), multiple accessions.

    Real 8-Ks overwhelmingly phrase appointments in ACTIVE voice (the Board/Company
    as grammatical subject: "the Board ... appointed [Name] as [Role]") rather than
    the passive voice ("[Name] was appointed as [Role]") this parser originally
    only recognized. The effective date is often a lead-in before the whole
    sentence ("On [Date], the Board ... appointed ...") rather than trailing the
    appointment clause. Survey of 2,689 real cached candidates found 52.8%
    unresolved before this fix, the overwhelming majority of which were this
    active-voice shape.
    """
    single = parse_item_502(
        accession_number="0000014693-17-000087", cik=14693, filing_date=date(2017, 1, 1),
        content=(
            "Item 5.02 Departure of Directors or Certain Officers; Election of Directors; "
            "Appointment of Certain Officers; Compensatory Arrangements of Certain Officers. "
            'On January 3, 2017, the Board of Directors (the "Board") of Brown-Forman '
            'Corporation (the "Company") appointed Kathleen M. Gutmann as a director of '
            "the Company."
        ),
    )
    assert single.applicability == "applicable"
    assert single.events[0].event_type == "appointment"
    assert single.events[0].person_name == "Kathleen M. Gutmann"
    assert single.events[0].effective_date == date(2017, 1, 3)

    multi = parse_item_502(
        accession_number="0000014693-15-000010", cik=14693, filing_date=date(2015, 1, 1),
        content=(
            "Item 5.02 Departure of Directors or Certain Officers. "
            'On May 21, 2015, the Board of Directors of Brown-Forman Corporation (the '
            '"Company") appointed Augusta Brown Holland and Stuart R. Brown as directors '
            "of the Company."
        ),
    )
    assert multi.applicability == "applicable"
    names = {event.person_name for event in multi.events}
    assert names == {"Augusta Brown Holland", "Stuart R. Brown"}
    assert all(event.effective_date == date(2015, 5, 21) for event in multi.events)


def test_item_502_active_voice_election_to_fill_vacancy() -> None:
    """Production coverage gap: CIK 14707, "elected [Name] to fill the vacancy"
    phrasing carries no explicit role -- filling a board vacancy implies Director."""
    result = parse_item_502(
        accession_number="0000014707-13-000069", cik=14707, filing_date=date(2013, 6, 1),
        content=(
            "Item 5.02 Election of Directors. "
            "On June 1, 2013, the Board of Directors of the Company, based on a "
            "recommendation of the Governance and Nominating Committee, elected W. Lee "
            "Capps to fill the vacancy on the Board of Directors."
        ),
    )
    assert result.applicability == "applicable"
    assert result.events[0].person_name == "W. Lee Capps"
    assert result.events[0].role == "Director"
    assert result.events[0].effective_date == date(2013, 6, 1)


def test_item_502_active_voice_termination() -> None:
    """Production coverage gap: CIK 14707 (Butler National), active-voice
    termination -- "[Company] terminated the employment of [Name]"."""
    result = parse_item_502(
        accession_number="0000014707-25-000101", cik=14707, filing_date=date(2025, 1, 2),
        content=(
            "Item 5.02 Departure of Certain Officers. "
            "Effective January 2, 2025, Butler National Corporation terminated the "
            "employment of Tad M. McMahon."
        ),
    )
    assert result.applicability == "applicable"
    assert result.events[0].event_type == "departure"
    assert result.events[0].person_name == "Tad M. McMahon"
    assert result.events[0].effective_date == date(2025, 1, 2)
