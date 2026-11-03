"""A steward's split of a consolidation (ticket 142): the decision it writes, without a database.
The Merge Stage's replay of it runs on PostgreSQL and MySQL in tests/storage_adapters/test_steward_split.py."""
import pytest

from edgar_warehouse.mdm.clean import steward
from edgar_warehouse.mdm.clean.evidence import decision
from edgar_warehouse.mdm.clean.store import Conflict

MERGE = decision("merge", actor="rule:fixture@1", reason="same FIGI", at="2026-01-01T00:00:00Z",
                 left="entity-a", right="entity-b")


def test_a_split_is_a_reverse_naming_the_merge_with_who_and_why():
    verdict = steward.reversal(MERGE, actor=" Sam ", reason=" two different issuers ", at="2026-02-01T00:00:00Z")
    assert (verdict["operation"], verdict["target"], verdict["actor"], verdict["reason"]) == (
        "reverse", MERGE["decision_id"], "Sam", "two different issuers")
    assert verdict["decision_id"] and verdict == steward.reversal(
        MERGE, actor="Sam", reason="two different issuers", at="2026-02-01T00:00:00Z")  # the same words, the same id


@pytest.mark.parametrize("change, error, words", [
    ({"actor": " "}, ValueError, "who made it"),
    ({"reason": ""}, ValueError, "and why"),
    ({"at": "2026-01-01T00:00:00Z"}, Conflict, "later than the merge"),
])
def test_a_split_without_who_why_or_a_later_time_is_refused(change, error, words):
    args = {"actor": "Sam", "reason": "wrong", "at": "2026-02-01T00:00:00Z", **change}
    with pytest.raises(error, match=words):
        steward.reversal(MERGE, **args)


def test_only_a_merge_can_be_split():
    other = decision("exclude", actor="Sam", reason="x", at="2026-01-01T00:00:00Z", left="a", right="b")
    with pytest.raises(Conflict, match="not a merge"):
        steward.reversal(other, actor="Sam", reason="wrong", at="2026-02-01T00:00:00Z")
