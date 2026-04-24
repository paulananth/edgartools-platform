"""Unit tests for MDMRuleEngine, normalize, and survivorship.

Tests run in-memory; no PostgreSQL needed. The engine's loaders talk to a
SQLAlchemy Session, so we construct the engine directly via its dataclass
fields instead of calling .load().
"""
from __future__ import annotations

from datetime import date

import pytest

from edgar_warehouse.mdm.rules import ALL, FieldRule, MDMRuleEngine
from edgar_warehouse.mdm.survivorship import Candidate, _pick_by_rule


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def engine() -> MDMRuleEngine:
    return MDMRuleEngine(
        _source_priority={
            (ALL, "edgar_cik"): 1,
            (ALL, "adv_filing"): 2,
            (ALL, "ownership_filing"): 3,
            (ALL, "derived"): 4,
            ("company", "derived"): 10,  # entity-specific override
        },
        _field_survivorship={
            ("company", "ein"): FieldRule(
                entity_type="company",
                field_name="ein",
                rule_type="immutable",
                source_system="edgar_cik",
                preferred_source_order=None,
            ),
            ("adviser", "canonical_name"): FieldRule(
                entity_type="adviser",
                field_name="canonical_name",
                rule_type="source_priority",
                source_system=None,
                preferred_source_order=["adv_filing", "edgar_cik"],
            ),
            ("adviser", "aum_total"): FieldRule(
                entity_type="adviser",
                field_name="aum_total",
                rule_type="most_recent",
                source_system="adv_filing",
                preferred_source_order=None,
            ),
            ("company", "primary_ticker"): FieldRule(
                entity_type="company",
                field_name="primary_ticker",
                rule_type="highest_source_rank",
                source_system=None,
                preferred_source_order=None,
            ),
        },
        _match_thresholds={
            ("person", "fuzzy_name"): (0.92, 0.80),
            ("company", "fuzzy_name"): (0.95, 0.85),
        },
        _normalization={
            "legal_suffix": {"INC": "", "LLC": "", "CORP": "", "LTD": ""},
            "title_alias": {"CHIEF EXECUTIVE OFFICER": "CEO", "CEO": "CEO", "DIRECTOR": "Director"},
            "address_abbr": {"ST": "Street", "AVE": "Avenue", "STE": "Suite"},
            "state_code": {"CALIFORNIA": "CA", "NEW YORK": "NY"},
            "country_code": {"UNITED STATES": "US"},
        },
    )


# ---------------------------------------------------------------------------
# Source priority + threshold accessors
# ---------------------------------------------------------------------------

def test_source_priority_entity_specific_overrides_all(engine: MDMRuleEngine) -> None:
    assert engine.get_source_priority("company", "derived") == 10
    assert engine.get_source_priority("adviser", "derived") == 4


def test_source_priority_falls_back_to_all(engine: MDMRuleEngine) -> None:
    assert engine.get_source_priority("person", "edgar_cik") == 1


def test_source_priority_missing_raises(engine: MDMRuleEngine) -> None:
    with pytest.raises(KeyError):
        engine.get_source_priority("person", "unknown_source")


def test_threshold_accessor(engine: MDMRuleEngine) -> None:
    assert engine.get_threshold("person", "fuzzy_name") == (0.92, 0.80)


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def test_normalize_name_strips_legal_suffix(engine: MDMRuleEngine) -> None:
    assert engine.normalize_name("BLACKROCK, INC.") == "Blackrock"
    assert engine.normalize_name("Apple Inc.") == "Apple"
    assert engine.normalize_name("Acme LLC") == "Acme"


def test_normalize_name_none_passthrough(engine: MDMRuleEngine) -> None:
    assert engine.normalize_name(None) is None
    assert engine.normalize_name("") == ""


def test_normalize_title_alias_hit(engine: MDMRuleEngine) -> None:
    assert engine.normalize_title("Chief Executive Officer") == "CEO"
    assert engine.normalize_title("ceo") == "CEO"
    assert engine.normalize_title("DIRECTOR") == "Director"


def test_normalize_title_unknown_falls_back(engine: MDMRuleEngine) -> None:
    assert engine.normalize_title("Senior Developer") == "Senior Developer"


def test_normalize_address_expands_abbrs(engine: MDMRuleEngine) -> None:
    result = engine.normalize_address(
        {"street": "100 Main ST STE 400", "state": "CALIFORNIA", "country": "UNITED STATES"}
    )
    assert result["street"] == "100 Main Street Suite 400"
    assert result["state"] == "CA"
    assert result["country"] == "US"


# ---------------------------------------------------------------------------
# Survivorship — Priority Merge
# ---------------------------------------------------------------------------

def _c(
    sid: str,
    source: str,
    value: str | None,
    priority: int,
    eff: date | None = None,
) -> Candidate:
    return Candidate(
        stage_id=sid,
        source_system=source,
        source_id=f"{source}-{sid}",
        field_value=value,
        global_priority=priority,
        effective_date=eff,
    )


def test_survivorship_source_priority_default(engine: MDMRuleEngine) -> None:
    # No explicit rule — falls back to global priority; edgar_cik (1) wins.
    rule = FieldRule("company", "canonical_name", "source_priority", None, None)
    cands = [
        _c("a", "adv_filing", "Apple Adv", 2),
        _c("b", "edgar_cik", "Apple Inc", 1),
        _c("c", "ownership_filing", "APPLE", 3),
    ]
    winner = _pick_by_rule(rule, cands, existing_value=None)
    assert winner is not None
    assert winner.source_system == "edgar_cik"


def test_survivorship_preferred_source_order_beats_global(engine: MDMRuleEngine) -> None:
    # adviser.canonical_name prefers adv_filing even though edgar_cik has higher global rank
    rule = engine.get_field_rule("adviser", "canonical_name")
    assert rule is not None
    cands = [
        _c("a", "edgar_cik", "Blackrock Inc", 1),
        _c("b", "adv_filing", "BlackRock Advisors LLC", 2),
    ]
    winner = _pick_by_rule(rule, cands, existing_value=None)
    assert winner is not None
    assert winner.source_system == "adv_filing"


def test_survivorship_preferred_order_falls_back(engine: MDMRuleEngine) -> None:
    # If preferred sources have no value, fall through to global priority
    rule = engine.get_field_rule("adviser", "canonical_name")
    assert rule is not None
    cands = [
        _c("a", "ownership_filing", "Owner View", 3),
        _c("b", "derived", "Derived View", 4),
    ]
    winner = _pick_by_rule(rule, cands, existing_value=None)
    assert winner is not None
    assert winner.source_system == "ownership_filing"


def test_survivorship_immutable_never_overrides_existing(engine: MDMRuleEngine) -> None:
    rule = engine.get_field_rule("company", "ein")
    assert rule is not None
    cands = [_c("a", "edgar_cik", "12-3456789", 1)]
    winner = _pick_by_rule(rule, cands, existing_value="99-9999999")
    assert winner is None


def test_survivorship_immutable_accepts_first_write(engine: MDMRuleEngine) -> None:
    rule = engine.get_field_rule("company", "ein")
    assert rule is not None
    cands = [
        _c("a", "adv_filing", "12-3456789", 2),  # wrong source, ignored
        _c("b", "edgar_cik", "88-8888888", 1),   # correct source
    ]
    winner = _pick_by_rule(rule, cands, existing_value=None)
    assert winner is not None
    assert winner.source_system == "edgar_cik"
    assert winner.field_value == "88-8888888"


def test_survivorship_most_recent_wins(engine: MDMRuleEngine) -> None:
    rule = engine.get_field_rule("adviser", "aum_total")
    assert rule is not None
    cands = [
        _c("a", "adv_filing", "1000000", 2, eff=date(2023, 3, 15)),
        _c("b", "adv_filing", "1500000", 2, eff=date(2024, 6, 30)),
        _c("c", "adv_filing", "900000", 2, eff=date(2022, 1, 1)),
    ]
    winner = _pick_by_rule(rule, cands, existing_value=None)
    assert winner is not None
    assert winner.field_value == "1500000"


def test_survivorship_highest_source_rank(engine: MDMRuleEngine) -> None:
    rule = engine.get_field_rule("company", "primary_ticker")
    assert rule is not None
    cands = [
        _c("a", "ownership_filing", "AAPL", 3),
        _c("b", "edgar_cik", "AAPL", 1),
        _c("c", "adv_filing", "APL", 2),
    ]
    winner = _pick_by_rule(rule, cands, existing_value=None)
    assert winner is not None
    assert winner.source_system == "edgar_cik"


def test_survivorship_skips_null_values(engine: MDMRuleEngine) -> None:
    rule = FieldRule("company", "canonical_name", "source_priority", None, None)
    cands = [
        _c("a", "edgar_cik", None, 1),
        _c("b", "adv_filing", "Real Name", 2),
    ]
    winner = _pick_by_rule(rule, cands, existing_value=None)
    assert winner is not None
    assert winner.source_system == "adv_filing"
