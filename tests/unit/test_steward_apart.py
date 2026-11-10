"""`apart_from`: a record made its own golden record keeps no identifier value another golden record holds."""

from edgar_warehouse.mastering.steward import apart_from


def test_values_another_golden_record_holds_leave_the_identifiers_and_stay_as_evidence():
    record = {"identifiers": {"cusip": ["C2"], "share_class_figi": "S1", "figi": ["F9", "F1"]},
              "cross_references": {"composite_figi": "K1"}}
    others = {"e1": {"share_class_figi": {"S1"}, "figi": {"F1"}}, "e2": {"cusip": {"C1"}}}
    own = apart_from(record, others)
    assert own["identifiers"] == {"cusip": ["C2"], "figi": ["F9"]}
    assert own["cross_references"] == {"composite_figi": "K1", "share_class_figi_held_by_another": ["S1"],
                                       "figi_held_by_another": ["F9", "F1"]}
    assert record["identifiers"]["share_class_figi"] == "S1"  # the stored record is not changed in place


def test_a_record_that_shares_nothing_is_unchanged():
    record = {"identifiers": {"cusip": ["C2"]}}
    assert apart_from(record, {"e1": {"cusip": {"C1"}}}) == {"identifiers": {"cusip": ["C2"]}, "cross_references": {}}
