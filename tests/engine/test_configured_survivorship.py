"""The generic native ranking seam: values remain opaque Python payloads."""
from edgar_warehouse.rules.source_engine import rank_claims


def test_configured_priority_recency_ties_clear_and_unknown_time():
    candidates = [
        ('secondary', 'value', 100.0, True, 'a', 's'),
        ('primary', 'value', 90.0, True, 'z', 'p1'),
        ('primary', 'value', 90.0, True, 'a', 'p2'),
        ('primary', 'clear', 110.0, True, 'b', 'clear'),
        ('primary', 'value', None, True, 'c', 'unknown'),
        ('primary', 'value', 80.0, False, 'd', 'old'),
        ('unlisted', 'value', 120.0, True, 'e', 'other'),
    ]
    eligible, unauthorized = rank_claims(['primary', 'secondary'], [], False, candidates)
    assert eligible == [2, 1, 0]
    assert unauthorized == [3]
    eligible, unauthorized = rank_claims(['primary', 'secondary'], ['primary'], True, candidates)
    assert eligible == [3, 2, 1, 4, 0]
    assert unauthorized == []
