"""Records of one batch that share a matching key get one master, whatever their order."""

from edgar_warehouse.rules.source_engine import group_batch_records


def test_records_sharing_a_key_through_a_chain_form_one_group():
    records = [["c", ["cik=2"]], ["b", ["cik=1", "cik=2"]], ["a", ["cik=1"]], ["d", ["cik=3"]]]
    assert group_batch_records(records) == {"a": "a", "b": "a", "c": "a", "d": "d"}
    assert group_batch_records(records[::-1]) == {"a": "a", "b": "a", "c": "a", "d": "d"}
