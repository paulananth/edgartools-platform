"""silver.land groups a unit's artifacts into few deliveries: a delivery costs a fixed number of round trips."""
from edgar_warehouse.workers import silver_land

APPEND = {"key": ["id"], "load_mode": "append"}
SNAPSHOT = {"key": ["id"], "load_mode": "snapshot"}


def _row(key, value="v"):
    return {"id": key, "value": value}


def test_the_artifacts_of_a_unit_land_in_one_delivery():
    artifacts = [[_row(1), _row(2)], [_row(3)], [_row(4), _row(5)]]
    assert list(silver_land._deliveries(APPEND, iter(artifacts))) == [[_row(1), _row(2), _row(3), _row(4), _row(5)]]


def test_an_artifact_without_rows_lands_nothing():
    assert list(silver_land._deliveries(APPEND, iter([[], [], []]))) == []


def test_a_row_repeating_a_key_with_the_same_values_is_dropped():
    assert list(silver_land._deliveries(APPEND, iter([[_row(1), _row(2)], [_row(1)]]))) == [[_row(1), _row(2)]]


def test_a_row_repeating_a_key_with_other_values_starts_the_next_delivery_in_order():
    artifacts = [[_row(1, "a"), _row(2)], [_row(1, "b"), _row(3)]]
    assert list(silver_land._deliveries(APPEND, iter(artifacts))) == [[_row(1, "a"), _row(2)], [_row(1, "b"), _row(3)]]


def test_a_delivery_ends_at_the_end_of_the_artifact_that_reaches_its_size(monkeypatch):
    monkeypatch.setattr(silver_land, "DELIVERY_ROWS", 3)
    artifacts = [[_row(1), _row(2)], [_row(3), _row(4)], [_row(5)]]
    assert list(silver_land._deliveries(APPEND, iter(artifacts))) == [[_row(1), _row(2), _row(3), _row(4)], [_row(5)]]


def test_a_snapshot_table_keeps_one_delivery_for_each_artifact_even_when_empty():
    artifacts = [[_row(1)], [], [_row(2)]]
    assert list(silver_land._deliveries(SNAPSHOT, iter(artifacts))) == artifacts
