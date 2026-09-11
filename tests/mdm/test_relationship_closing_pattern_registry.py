"""relationship-closing-pattern-framework map, Ticket 02: RELATIONSHIP_TYPES
has grown three times in this repo's history (one commit per new
relationship type), with no enforcement that a new type is ever classified
against a known relationship-closing pattern (docs/adr/0008-name-
relationship-closing-patterns.md). These tests fail closed if a future
relationship type is added to RELATIONSHIP_TYPES without a corresponding
RELATIONSHIP_CLOSING_PATTERNS entry, or if an entry uses a pattern name
that isn't one of the four named in the ADR."""

from __future__ import annotations

from edgar_warehouse.mdm.pipeline import (
    KNOWN_RELATIONSHIP_CLOSING_PATTERNS,
    RELATIONSHIP_CLOSING_PATTERNS,
    RELATIONSHIP_TYPES,
)


def test_every_relationship_type_is_classified():
    missing = set(RELATIONSHIP_TYPES) - set(RELATIONSHIP_CLOSING_PATTERNS)
    assert missing == set(), (
        f"RELATIONSHIP_TYPES has type(s) with no RELATIONSHIP_CLOSING_PATTERNS "
        f"entry: {sorted(missing)} -- classify each against a pattern in "
        f"docs/adr/0008-name-relationship-closing-patterns.md before adding "
        f"a new relationship type."
    )


def test_no_stale_registry_entries():
    stale = set(RELATIONSHIP_CLOSING_PATTERNS) - set(RELATIONSHIP_TYPES)
    assert stale == set(), (
        f"RELATIONSHIP_CLOSING_PATTERNS has entry/entries for type(s) no "
        f"longer in RELATIONSHIP_TYPES: {sorted(stale)}"
    )


def test_every_registry_value_is_a_known_pattern():
    unknown = {
        rel_type: pattern
        for rel_type, pattern in RELATIONSHIP_CLOSING_PATTERNS.items()
        if pattern not in KNOWN_RELATIONSHIP_CLOSING_PATTERNS
    }
    assert unknown == {}, (
        f"RELATIONSHIP_CLOSING_PATTERNS has unrecognized pattern name(s): "
        f"{unknown} -- must be one of {sorted(KNOWN_RELATIONSHIP_CLOSING_PATTERNS)}"
    )


def test_expected_classification_snapshot():
    """Pins today's actual classification (not just structural validity) so
    a silent, unreviewed reclassification shows up as a diff in code review."""
    assert RELATIONSHIP_CLOSING_PATTERNS == {
        "IS_INSIDER": "property_differs_from_prior",
        "HOLDS": "value_signals_disposal",
        "COMPANY_HOLDS": "value_signals_disposal",
        "ISSUED_BY": "no_versioning_needed",
        "IS_ENTITY_OF": "no_versioning_needed",
        "HAS_PARENT_COMPANY": "property_differs_from_prior",
        "MANAGES_FUND": "periodic_snapshot_diff",
        "IS_PERSON_OF": "no_versioning_needed",
        "EMPLOYED_BY": "property_differs_from_prior",
        "AUDITED_BY": "property_differs_from_prior",
        "INSTITUTIONAL_HOLDS": "periodic_snapshot_diff",
    }
