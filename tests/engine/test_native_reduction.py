"""Native core semantics at the Python facade; worker tests cover receipts/EOF."""
import random

import pytest

from edgar_warehouse.control_contract import canonical
from edgar_warehouse.rules import source_engine
from edgar_warehouse.rules.source_engine import ReductionEngine
from edgar_warehouse.workers import source_combine
from tests.engine.test_source_reduction import member, plan


def engine(groups, **bounds):
    return ReductionEngine(plan(groups, **bounds)["reduce"])


@pytest.mark.parametrize("seed", range(10))
def test_chunked_members_counts_and_cross_source_exclusion(seed):
    rng = random.Random(seed)
    keys = ["", "a", "é", "𐀀", 'quote"', "\n\0"]
    holders = ["", "A", "é", "𐀀", "\t\\"]
    rows = [{"key": rng.choice(keys), "holder": rng.choice(holders), "time": str(i)}
            for i in range(2100)]
    blocked = [{"key": rng.choice(keys), "holder": rng.choice(holders)} for _ in range(60)]
    groups = {"blocked": member("rows", source="second"),
              "members": member("rows", last="time", exclude="blocked", limit=3),
              "counts": {"source": "main", "table": "rows", "keys": ["key"],
                         "mode": "count", "count": "frequency", "sample": None, "sample_limit": 0}}
    reducer = engine(groups, max_rows=10000)
    chunk_size = rng.randrange(1, 1100)
    for offset in range(0, len(rows), chunk_size):
        reducer.push("members", rows[offset:offset + chunk_size])
        reducer.push("counts", rows[offset:offset + chunk_size])
    # Exclusion is complete-set, independent of source processing order.
    reducer.push("blocked", blocked)
    excluded = {(r["key"], r["holder"]) for r in blocked}
    latest = {(r["key"], r["holder"]): r["time"] for r in rows}
    expected = []
    for key in sorted({r["key"] for r in rows}):
        kept = sorted(h for k, h in latest if k == key and (k, h) not in excluded)
        expected.append({"key": key, "count": len(kept),
                         "sample": [{"holder": h, "time": latest[key, h]} for h in kept[:3]]})
    result = reducer.finish()
    assert result["members"] == expected
    assert result["counts"] == [{"key": k, "frequency": sum(r["key"] == k for r in rows)}
                                for k in sorted({r["key"] for r in rows})]


@pytest.mark.parametrize("key,holder,last", [("", "", ""), ('a"\0', "é𐀀", "\n\\"),
                                           ("é", "\x08\x0c", "\u2028")])
def test_exact_canonical_state_bytes_and_failure_is_terminal(key, holder, last):
    spec = member("rows", last="time")
    size = sum(len(canonical(x).encode()) for x in ([key], holder, last))
    rows = [{"key": key, "holder": holder, "time": last}]
    reducer = engine({"members": spec}, max_state_bytes=size)
    reducer.push("members", rows)
    assert reducer.finish()["members"][0]["sample"] == [{"holder": holder, "time": last}]
    refused = engine({"members": spec}, max_state_bytes=size - 1)
    with pytest.raises(ValueError, match="state budget"):
        refused.push("members", rows)
    with pytest.raises(ValueError, match="failed"):
        refused.finish()


def test_last_value_shrinks_state_and_missing_differs_from_explicit_null():
    spec = member("rows", last="time")
    spec["last_null"] = ""
    reducer = engine({"members": spec}, max_state_bytes=20)
    reducer.push("members", [{"key": "a", "holder": "A", "time": "123456"}])
    reducer.push("members", [{"key": "a", "holder": "A", "time": None},
                             {"key": "a", "holder": "B", "time": ""}])
    assert reducer.finish()["members"] == [{"key": "a", "count": 2,
        "sample": [{"holder": "A", "time": ""}, {"holder": "B", "time": ""}]}]
    refused = engine({"members": spec})
    with pytest.raises(ValueError, match="exact text"):
        refused.push("members", [{"key": "a", "holder": "A"}])
    with pytest.raises(ValueError, match="failed"):
        refused.push("members", [])


def test_budget_failure_precedes_later_invalid_row_and_finish_is_single_use():
    reducer = engine({"members": member("rows")}, max_keys=1)
    with pytest.raises(ValueError, match="state budget"):
        reducer.push("members", [{"key": "a", "holder": "A"},
                                 {"key": "b", "holder": "B"}, {"key": False}])
    with pytest.raises(ValueError, match="failed"):
        reducer.finish()
    empty = engine({"members": member("rows")})
    assert empty.finish() == {"members": []}
    with pytest.raises(ValueError, match="finished"):
        empty.finish()
    with pytest.raises(ValueError, match="finished"):
        empty.push("members", [])


def test_count_digit_growth_and_multiple_key_columns():
    spec = {"source": "main", "table": "rows", "keys": ["a", "b"], "mode": "count",
            "count": "frequency", "sample": None, "sample_limit": 0}
    key_size = len(canonical(["x", "y"]).encode())
    reducer = engine({"counts": spec}, max_state_bytes=key_size + 1)
    reducer.push("counts", [{"a": "x", "b": "y"}] * 9)
    with pytest.raises(ValueError, match="state budget"):
        reducer.push("counts", [{"a": "x", "b": "y"}])
    accepted = engine({"counts": spec}, max_state_bytes=key_size + 2)
    accepted.push("counts", [{"a": "x", "b": "y"}] * 10)
    assert accepted.finish() == {"counts": [{"a": "x", "b": "y", "frequency": 10}]}


@pytest.mark.parametrize("fault", ["sample_missing", "last_null_without_last", "count_extra", "null_last"])
def test_native_constructor_rejects_invalid_configuration(fault):
    body = plan({"members": member("rows")})["reduce"]
    group = body["groups"]["members"]
    if fault == "sample_missing": del group["sample"]
    if fault == "last_null_without_last": group["last_null"] = ""
    if fault == "null_last": group["last"] = None
    if fault == "count_extra": group.update(mode="count", sample=None, sample_limit=0, member=None)
    with pytest.raises(ValueError):
        ReductionEngine(body)


def test_reduction_execution_identity_includes_native_binary_and_facade():
    assert set(source_engine.runtime_files()) <= set(source_combine.runtime_files())


def test_most_keeps_the_value_the_most_rows_file_through_the_facade():
    # Ticket 138, "Most-filed value": a null value is a row that files none, and a tie keeps none.
    spec = {"source": "main", "table": "rows", "keys": ["key"], "mode": "most",
            "member": "category", "count": "filed", "sample": "value", "sample_limit": 0}
    reducer = engine({"most": spec})
    reducer.push("most", [{"key": "x", "category": "EC"}, {"key": "x", "category": None},
                          {"key": "x", "category": "EC"}, {"key": "x", "category": "DBT"},
                          {"key": "y", "category": "EC"}, {"key": "y", "category": "DBT"},
                          {"key": "z"}])
    assert reducer.finish()["most"] == [{"key": "x", "filed": 2, "value": "EC"},
                                        {"key": "y", "filed": 1, "value": None}]
