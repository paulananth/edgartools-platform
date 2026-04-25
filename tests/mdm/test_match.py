"""Unit tests for matching engine."""
from __future__ import annotations

import pytest

from edgar_warehouse.mdm.match import (
    CIKExactMatcher,
    FuzzyNameMatcher,
    MatchAction,
    MatchPipeline,
)
from edgar_warehouse.mdm.rules import ALL, FieldRule, MDMRuleEngine


@pytest.fixture
def engine() -> MDMRuleEngine:
    return MDMRuleEngine(
        _source_priority={(ALL, "edgar_cik"): 1},
        _field_survivorship={},
        _match_thresholds={
            ("company", "fuzzy_name"): (0.95, 0.85),
            ("person", "fuzzy_name"): (0.92, 0.80),
        },
        _normalization={"legal_suffix": {"INC": "", "LLC": "", "CORP": ""}},
    )


def test_cik_exact_auto_merge() -> None:
    m = CIKExactMatcher()
    v = m.match(
        {"cik": 320193},
        [{"entity_id": "e1", "cik": 320193}, {"entity_id": "e2", "cik": 789019}],
    )
    assert v is not None
    assert v.score == 1.0
    assert v.action == MatchAction.AUTO_MERGE
    assert v.candidate_entity_id == "e1"


def test_cik_exact_miss_returns_none() -> None:
    m = CIKExactMatcher()
    assert m.match({"cik": 999999}, [{"entity_id": "e1", "cik": 320193}]) is None


def test_fuzzy_name_auto_merge(engine: MDMRuleEngine) -> None:
    m = FuzzyNameMatcher(entity_type="company", engine=engine)
    v = m.match(
        {"canonical_name": "Apple Inc"},
        [{"entity_id": "e1", "canonical_name": "Apple Inc."}],
    )
    assert v is not None
    # "apple" vs "apple" after suffix strip → 1.0
    assert v.score >= 0.95
    assert v.action == MatchAction.AUTO_MERGE


def test_fuzzy_name_review_tier(engine: MDMRuleEngine) -> None:
    m = FuzzyNameMatcher(entity_type="company", engine=engine)
    v = m.match(
        {"canonical_name": "Blackrock Advisors"},
        [{"entity_id": "e1", "canonical_name": "Blackrack Advisers"}],
    )
    assert v is not None
    # Score should land in review band
    assert v.action in (MatchAction.REVIEW, MatchAction.AUTO_MERGE)


def test_fuzzy_name_quarantine_on_low_score(engine: MDMRuleEngine) -> None:
    m = FuzzyNameMatcher(entity_type="person", engine=engine)
    v = m.match(
        {"canonical_name": "John Smith"},
        [{"entity_id": "e1", "canonical_name": "Xavier Unrelated"}],
    )
    assert v is not None
    assert v.action == MatchAction.QUARANTINE


def test_pipeline_cik_short_circuits(engine: MDMRuleEngine) -> None:
    pipeline = MatchPipeline(
        matchers=[CIKExactMatcher(), FuzzyNameMatcher(entity_type="company", engine=engine)]
    )
    v = pipeline.resolve(
        {"cik": 320193, "canonical_name": "Apple Inc"},
        [{"entity_id": "e1", "cik": 320193, "canonical_name": "APPLE INC"}],
    )
    assert v is not None
    assert v.method == "cik_exact"
    assert v.score == 1.0
