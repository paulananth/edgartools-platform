"""A worker takes units one at a time (`workers/__main__.py`): a claimed unit
never waits behind another while its lease runs out."""
from edgar_warehouse.workers.__main__ import one_at_a_time


def test_units_are_claimed_one_at_a_time_up_to_the_limit():
    asked, units = [], iter(range(5))

    def fetch(n):
        asked.append(n)
        return [{"claim": {"step": "main", "key": u}} for u in [next(units, None)] if u is not None]

    assert [u["claim"]["key"] for u in one_at_a_time(fetch, 3)] == [0, 1, 2]
    assert asked == [1, 1, 1]


def test_claiming_stops_when_no_unit_is_ready():
    asked = []
    assert list(one_at_a_time(lambda n: asked.append(n) or [], 1000)) == []
    assert asked == [1]


def test_a_unit_that_comes_back_ends_the_call():
    """A failed unit waits again at once; it is not retried within one call."""
    unit = {"claim": {"step": "main", "key": "main-0"}}
    assert list(one_at_a_time(lambda n: [unit], 1000)) == [unit]
