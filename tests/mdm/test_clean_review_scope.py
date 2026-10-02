"""Which records a review names (platform validation 05b, part 1).

The database behaviour is in `tests/integration/test_clean_review_scope.py`;
these cover the cases that are hard to reach there.
"""

from __future__ import annotations

from edgar_warehouse.mdm.clean.merge import review_scope

MEMBERS = {"root": ["s1", "s2"], "other": ["s3"]}
CANONICAL = {"alias": "root", "root": "root", "other": "other"}
EVIDENCE = {"a1": {"subject": "s1"}, "a3": {"subject": "s3"}, "a9": {"subject": "s9"}}


def test_a_review_of_an_alias_company_names_the_current_company():
    review = {"reason": "kind_conflict", "entity_id": "alias"}
    assert review_scope(review, MEMBERS, CANONICAL, EVIDENCE, {}) == (["s1", "s2"], ["root"])


def test_a_link_review_names_the_records_of_its_companies():
    review = {"reason": "hierarchy_cycle", "entities": ["root", "other"]}
    assert review_scope(review, MEMBERS, CANONICAL, EVIDENCE, {}) == (["s1", "s2", "s3"], ["other", "root"])


def test_only_an_ownerless_override_review_reads_its_decision():
    decisions = {"d1": {"entity_id": "other", "evidence": ["a9"]}}
    owner = {"reason": "ambiguous_override_owner", "decision_id": "d1"}
    assert review_scope(owner, MEMBERS, CANONICAL, EVIDENCE, decisions) == (["s3", "s9"], ["other"])
    other = {"reason": "kind_conflict", "subject": "s1", "decision_id": "d1"}
    assert review_scope(other, MEMBERS, CANONICAL, EVIDENCE, decisions) == (["s1"], [])


def test_a_review_that_names_no_record_falls_back_to_its_closure():
    decisions = {"d1": {"entity_id": "gone", "evidence": ["missing"]}}
    review = {"reason": "ambiguous_override_owner", "decision_id": "d1"}
    assert review_scope(review, MEMBERS, CANONICAL, EVIDENCE, decisions) == (["s1", "s3", "s9"], ["gone"])
