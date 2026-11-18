"""How a batch is cut into parts that each claim at most the cap's identifier values."""

from edgar_warehouse.mastering.merge import _parts


def rec(name, **identifiers):
    return {"assertion_id": name, "identifiers": identifiers}


def test_a_batch_is_cut_in_order_into_parts_of_at_most_the_cap_distinct_values():
    batch = [rec(str(n), cik=f"{n:010d}") for n in range(7)]
    parts = _parts(batch, 3)
    assert [[r["assertion_id"] for r in part] for part in parts] == [["0", "1", "2"], ["3", "4", "5"], ["6"]]


def test_a_value_two_records_share_counts_once_and_lists_and_empty_values_are_read_as_the_store_reads_them():
    batch = [rec("a", cik="1"), rec("b", cik="1"), rec("c", figi=["x", "y"]), rec("d", cik=None), rec("e")]
    assert [[r["assertion_id"] for r in part] for part in _parts(batch, 3)] == [["a", "b", "c", "d", "e"]]  # 1, x, y: three
    assert [[r["assertion_id"] for r in part] for part in _parts(batch, 2)] == [["a", "b"], ["c", "d", "e"]]


def test_a_record_over_the_cap_alone_is_a_part_of_its_own_and_the_cut_is_the_same_every_time():
    batch = [rec("a", cik="1"), rec("big", figi=["1", "2", "3", "4", "5"]), rec("z", cik="2")]
    first = _parts(batch, 3)
    assert [[r["assertion_id"] for r in part] for part in first] == [["a"], ["big"], ["z"]]  # it cannot be cut: it merges alone
    assert _parts(batch, 3) == first  # a rerun cuts the same parts, so each part's file is found done
    assert _parts([], 3) == []
