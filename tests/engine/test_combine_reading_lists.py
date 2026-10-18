"""A combination's name lists several readings, read in order as one (ticket 112):
a Bookkeeping list slot fills one name with many units' readings, so a rules file
names one source, not one per unit."""
import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import source_combine
from tests.engine import test_source_combine as combine_case
from tests.engine.test_source_reduction import member, partitioned, plan

FIRST = [{"key": "a", "holder": "B"}, {"key": "b", "holder": "A"}]
SECOND = [{"key": "a", "holder": "A"}, {"key": "a", "holder": "B"}]


def run(store, root, body, readings):
    envelope = combine_case.envelope(store, root, body, readings)
    out = source_combine.execute(envelope, store)
    assert source_combine.verify({**envelope, "candidate": out}, store) == ({source_combine.CHECK: True}, [])
    assert source_combine.confirm({**envelope, "candidate": out}, store)[0] == {source_combine.CHECK: True}
    return store.json(out)


def test_a_reduction_over_a_listed_name_gives_one_reading_of_their_rows(tmp_path):
    store = Artifacts()
    listed = [partitioned(store, tmp_path, [{"rows": FIRST}]), partitioned(store, tmp_path, [{"rows": SECOND}])]
    whole = partitioned(store, tmp_path, [{"rows": FIRST + SECOND}])

    many = run(store, tmp_path / "many", plan({"rows": member("rows")}), {"main": listed})
    one = run(store, tmp_path / "one", plan({"rows": member("rows")}), {"main": whole})

    assert many["artifacts"][0]["tables"] == one["artifacts"][0]["tables"]
    assert many["readings"] == {"main": listed}  # the output names every listed reading, in order


def test_a_combination_over_a_listed_name_joins_every_reading(tmp_path):
    store = Artifacts()
    listed = [combine_case.reading(store, tmp_path, {"rows": FIRST}),
              combine_case.reading(store, tmp_path, {"rows": SECOND})]
    body = combine_case.plan({"keys": combine_case.group("main", "rows", "key", "holder")},
                             {"out": combine_case.table("main", "rows", {"holders": combine_case.join("keys", "key")})})

    tables = run(store, tmp_path / "c", body, {"main": listed})["artifacts"][0]["tables"]

    assert len(tables["out"]) == 4
    assert {row["key"]: row["holders"] for row in tables["out"]}["a"] == ["B", "A", "B"]


def test_last_over_a_listed_name_is_refused(tmp_path):
    store = Artifacts()
    single = [partitioned(store, tmp_path, [{"rows": [{"key": "a", "holder": "B", "holder2": "x"}]}])]
    run(store, tmp_path / "one", plan({"rows": member("rows", last="holder2")}), {"main": single})  # one reading: allowed

    listed = [partitioned(store, tmp_path, [{"rows": FIRST}]), partitioned(store, tmp_path, [{"rows": SECOND}])]
    spec = member("rows", last="holder2")

    with pytest.raises(ValueError, match="single source"):
        run(store, tmp_path / "last", plan({"rows": spec}), {"main": listed})


@pytest.mark.parametrize("count", [0, 257])
def test_a_list_holds_1_to_256_readings(tmp_path, count):
    store = Artifacts()
    one = partitioned(store, tmp_path, [{"rows": FIRST}])

    with pytest.raises(ValueError, match="1..256 readings"):
        run(store, tmp_path / "n", plan({"rows": member("rows")}), {"main": [one] * count})


def test_a_reading_listed_twice_is_refused(tmp_path):
    store = Artifacts()
    one = partitioned(store, tmp_path, [{"rows": FIRST}])

    with pytest.raises(ValueError, match="each reading once"):
        run(store, tmp_path / "twice", plan({"rows": member("rows")}), {"main": [one, one]})


def test_the_row_budget_is_spent_across_a_list(tmp_path):
    store = Artifacts()
    listed = [partitioned(store, tmp_path, [{"rows": FIRST}]), partitioned(store, tmp_path, [{"rows": SECOND}])]

    run(store, tmp_path / "fits", plan({"rows": member("rows")}, max_rows=4), {"main": listed})
    with pytest.raises(ValueError, match="row budget"):
        run(store, tmp_path / "over", plan({"rows": member("rows")}, max_rows=3), {"main": listed})
