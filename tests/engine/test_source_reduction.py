"""Configured complete-set reduction, authenticated EOF and bounded state."""
import copy
from pathlib import Path
from urllib.parse import urlparse

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import source_combine
from tests.engine.test_source_combine import envelope, reading


def member(table, *, last=None, exclude=None, limit=2, source="main"):
    spec = {"source": source, "table": table, "keys": ["key"], "mode": "members",
            "member": "holder", "count": "count", "sample": "sample", "sample_limit": limit}
    if last is not None:
        spec["last"] = last
    if exclude is not None:
        spec["exclude"] = exclude
    return spec


def plan(groups, **bounds):
    return {"execution": {"profile": "source.combine"}, "reduce": {
        "max_rows": 1000, "max_input_bytes": 1024**2, "max_state_bytes": 1024**2,
        "max_keys": 100, "max_members": 100, "max_output_rows": 100, "max_output_bytes": 1024**2,
        "groups": groups, **bounds}}


def partitioned(store, root, chunks):
    captured = store.put(root.as_uri(), {"captured": True})
    contract = store.put(root.as_uri(), {"recipe": True})
    parts = []
    for ordinal, tables in enumerate(chunks, 1):
        ref = store.put(root.as_uri(), {"version": 1, "tables": tables, "deferred": []})
        parts.append({"receipt": ref, "first_ordinal": ordinal, "record_count": 1,
                      "bytes": len(store.verified(ref))})
    return store.put(root.as_uri(), {"version": 2, "contract": contract, "artifacts": [{
        "input": captured, "table_names": list(chunks[0]), "record_count": len(parts),
        "expanded_bytes": 1000, "partitions": parts}]})


def test_complete_sets_last_occurrence_and_uncapped_subtraction(tmp_path):
    store = Artifacts()
    chunks = [{"legal": [{"key": "a", "holder": "Z", "time": "9999"},
                          {"key": "b", "holder": "Z", "time": "b-original"}],
               "other": [{"key": "a", "holder": value} for value in "ABCDZ"]},
              {"legal": [{"key": "a", "holder": "Z", "time": ""},
                          {"key": "a", "holder": "A", "time": "new"}],
               "other": [{"key": "a", "holder": "D"}]}]
    refs = {"main": partitioned(store, tmp_path, chunks)}
    body = plan({"legal": member("legal", last="time", limit=1),
                 "other": member("other", exclude="legal", limit=2)})
    work = envelope(store, tmp_path, body, refs)
    candidate = source_combine.execute(work, store)
    assert source_combine.execute(work, store) == candidate
    assert source_combine.verify({**work, "candidate": candidate}, store) == ({source_combine.CHECK: True}, [])
    output = store.json(candidate)
    tables = output["artifacts"][0]["tables"]
    assert tables["legal"] == [{"key": "a", "count": 2, "sample": [{"holder": "A", "time": "new"}]},
                               {"key": "b", "count": 1, "sample": [{"holder": "Z", "time": "b-original"}]}]
    assert tables["other"] == [{"key": "a", "count": 3, "sample": [{"holder": "B"}, {"holder": "C"}]}]
    # Inspect uncapped last occurrence: old lexically larger timestamps lose,
    # and a later record for another name does not rewrite this key's value.
    body["reduce"]["groups"]["legal"]["sample_limit"] = 5
    work2 = envelope(store, tmp_path / "wide", body, refs)
    result = store.json(source_combine.execute(work2, store))
    assert result["artifacts"][0]["tables"]["legal"][0]["sample"][-1] == {"holder": "Z", "time": ""}
    assert output["readings"] == refs
    assert store.json(output["artifacts"][0]["input"])["readings"] == refs


def test_count_preserves_duplicates_unselected_rows_consume_input_budget(tmp_path):
    store = Artifacts()
    tables = {"addresses": [{"key": "same"}, {"key": "same"}, {"key": "other"}],
              "unused": [{"ignored": True}]}
    refs = {"main": reading(store, tmp_path, tables)}
    spec = {"source": "main", "table": "addresses", "keys": ["key"], "mode": "count",
            "count": "frequency", "sample": None, "sample_limit": 0}
    work = envelope(store, tmp_path, plan({"frequencies": spec}), refs)
    output = store.json(source_combine.execute(work, store))
    assert output["artifacts"][0]["tables"]["frequencies"] == [
        {"key": "other", "frequency": 1}, {"key": "same", "frequency": 2}]
    bounded = envelope(store, tmp_path / "bounded", plan({"frequencies": spec}, max_rows=3), refs)
    with pytest.raises(ValueError, match="row budget"):
        source_combine.execute(bounded, store)
    assert not Path(urlparse(bounded["output"]).path).exists()


def test_large_input_uses_incremental_state_not_materializing_loader(tmp_path, monkeypatch):
    from edgar_warehouse.workers import source_readings
    store = Artifacts()
    chunks = [{"rows": [{"key": "a", "holder": str(i % 7)} for i in range(25001)]} for _ in range(4)]
    ref = partitioned(store, tmp_path, chunks)
    monkeypatch.setattr(source_readings, "load", lambda *a, **k: pytest.fail("materialized input"))
    work = envelope(store, tmp_path, plan({"members": member("rows")}, max_rows=200000,
                                         max_input_bytes=16*1024**2), {"main": ref})
    candidate = source_combine.execute(work, store)
    assert source_combine.verify({**work, "candidate": candidate}, store) == ({source_combine.CHECK: True}, [])
    assert store.json(candidate)["artifacts"][0]["tables"]["members"] == [
        {"key": "a", "count": 7, "sample": [{"holder": "0"}, {"holder": "1"}]}]


def test_explicit_null_last_replacement_and_state_growth_budget(tmp_path):
    store = Artifacts()
    spec = member("rows", last="time")
    spec["last_null"] = ""
    refs = {"main": reading(store, tmp_path, {"rows": [
        {"key": "a", "holder": "A", "time": "later"}, {"key": "a", "holder": "A", "time": None}]})}
    work = envelope(store, tmp_path, plan({"members": spec}), refs)
    result = store.json(source_combine.execute(work, store))
    assert result["artifacts"][0]["tables"]["members"][0]["sample"] == [{"holder": "A", "time": ""}]
    wide = reading(store, tmp_path, {"rows": [{"key": "a", "holder": "A", "time": ""},
                                               {"key": "a", "holder": "A", "time": "X"*100}]})
    refused = envelope(store, tmp_path / "growth", plan({"members": spec}, max_state_bytes=20), {"main": wide})
    with pytest.raises(ValueError, match="state budget"):
        source_combine.execute(refused, store)
    assert not (tmp_path / "growth/output").exists()


def test_union_tables_deduplicate_before_legal_subtraction(tmp_path):
    store = Artifacts()
    tables = {"legal": [{"key": "a", "holder": "A"}],
              "aliases": [{"key": "a", "holder": "A"}, {"key": "a", "holder": "B"}],
              "translated": [{"key": "a", "holder": "B"}, {"key": "a", "holder": "C"}]}
    groups = {"legal": member("legal"), "other": member(["aliases", "translated"], exclude="legal")}
    refs = {"main": reading(store, tmp_path, tables)}
    work = envelope(store, tmp_path, plan(groups), refs)
    candidate = source_combine.execute(work, store)
    assert source_combine.verify({**work, "candidate": candidate}, store) == ({source_combine.CHECK: True}, [])
    assert store.json(candidate)["artifacts"][0]["tables"]["other"] == [
        {"key": "a", "count": 2, "sample": [{"holder": "B"}, {"holder": "C"}]}]


def test_codec_dependency_is_pinned_without_relocating_on_wrapper_mutation(tmp_path, monkeypatch):
    import edgar_warehouse.bookkeeping.clean.artifacts as artifact_store
    expected = source_combine.ARTIFACT_CODEC_FILE
    assert expected.is_file() and expected in source_combine.runtime_files()
    monkeypatch.setattr(artifact_store, "__file__", str(tmp_path / "wrapped.py"))
    assert expected in source_combine.runtime_files()


@pytest.mark.parametrize("split", [False, True])
def test_cross_table_last_refuses_partition_dependent_source_order(tmp_path, split):
    store = Artifacts()
    first = {"earlier_table": [], "later_table": [{"key": "a", "holder": "A", "time": "old"}]}
    second = {"earlier_table": [{"key": "a", "holder": "A", "time": "new"}], "later_table": []}
    chunks = [first, second] if split else [{name: first[name] + second[name] for name in first}]
    ref = partitioned(store, tmp_path, chunks)
    groups = {"members": member(["earlier_table", "later_table"], last="time")}
    work = envelope(store, tmp_path, plan(groups), {"main": ref})
    with pytest.raises(ValueError, match="single table"):
        source_combine.execute(work, store)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("bound,value", [("max_keys", 1), ("max_members", 1),
                                         ("max_state_bytes", 1), ("max_output_rows", 1),
                                         ("max_input_bytes", 1), ("max_rows", 1), ("max_output_bytes", 1)])
def test_declared_resource_limits_refuse_before_any_publication(tmp_path, bound, value):
    store = Artifacts()
    refs = {"main": reading(store, tmp_path, {"rows": [
        {"key": "a", "holder": "A"}, {"key": "b", "holder": "B"}]})}
    work = envelope(store, tmp_path, plan({"members": member("rows")}, **{bound: value}), refs)
    with pytest.raises(ValueError):
        source_combine.execute(work, store)
    assert not (tmp_path / "output").exists()


def test_late_partition_fault_and_late_unselected_reading_never_publish(tmp_path):
    store = Artifacts()
    ref = partitioned(store, tmp_path, [{"rows": [{"key": "a", "holder": "A"}]},
                                      {"rows": [{"key": "b", "holder": "B"}]}])
    work = envelope(store, tmp_path, plan({"members": member("rows")}), {"main": ref})
    last = store.json(ref)["artifacts"][0]["partitions"][-1]["receipt"]
    Path(urlparse(last["uri"]).path).write_bytes(b"{}")
    with pytest.raises(ValueError, match="hash mismatch"):
        source_combine.execute(work, store)
    assert not (tmp_path / "output").exists()
    first = reading(store, tmp_path / "fresh", {"rows": [{"key": "a", "holder": "A"}]})
    bad = {"uri": (tmp_path / "missing.json").as_uri(), "sha256": "0" * 64}
    work = envelope(store, tmp_path / "late", plan({"members": member("rows")}), {"main": first, "unused": bad})
    with pytest.raises(ValueError):
        source_combine.execute(work, store)
    assert not (tmp_path / "late/output").exists()


@pytest.mark.parametrize("fault", ["boolean_bound", "missing_bound", "unknown_group", "self_exclude",
                                   "count_exclude", "different_keys", "last_member", "column_collision",
                                   "bad_sample", "bad_member", "missing_table", "deferred"])
def test_grammar_and_row_shape_fail_closed(tmp_path, fault):
    store = Artifacts()
    groups = {"members": member("rows"), "other": member("rows")}
    body = plan(groups)
    rows, deferred = [{"key": "a", "holder": "A"}], []
    if fault == "boolean_bound": body["reduce"]["max_keys"] = True
    if fault == "missing_bound": del body["reduce"]["max_state_bytes"]
    if fault == "unknown_group": groups["members"]["unknown"] = 1
    if fault == "self_exclude": groups["members"]["exclude"] = "members"
    if fault == "count_exclude": groups["members"]["mode"] = "count"; groups["members"]["exclude"] = "other"
    if fault == "different_keys": groups["members"]["exclude"] = "other"; groups["other"]["keys"] = ["different"]
    if fault == "last_member": groups["members"]["last"] = "holder"
    if fault == "column_collision": groups["members"]["count"] = "key"
    if fault == "bad_sample": groups["members"]["sample_limit"] = -1
    if fault == "bad_member": rows[0]["holder"] = 1
    if fault == "missing_table": groups["members"]["table"] = "absent"
    if fault == "deferred": deferred = [{"reason": "unresolved"}]
    refs = {"main": reading(store, tmp_path, {"rows": rows}, deferred=deferred)}
    work = envelope(store, tmp_path, body, refs)
    with pytest.raises(ValueError):
        source_combine.execute(work, store)
    assert not (tmp_path / "output").exists()


def test_lookup_scope_changes_identity_even_when_reduced_values_agree(tmp_path):
    store = Artifacts()
    base = store.json(reading(store, tmp_path, {"rows": [{"key": "a", "holder": "A"}]}))
    outputs = []
    for label in ("one", "two"):
        body = copy.deepcopy(base)
        body["artifacts"][0]["lookups"] = store.put(tmp_path.as_uri(), {"scope": label})
        ref = store.put(tmp_path.as_uri(), body)
        work = envelope(store, tmp_path / label, plan({"members": member("rows")}), {"main": ref})
        candidate = source_combine.execute(work, store)
        output = store.json(candidate)
        assert source_combine.verify({**work, "candidate": candidate}, store) == ({source_combine.CHECK: True}, [])
        outputs.append(output)
    assert outputs[0]["artifacts"][0]["tables"] == outputs[1]["artifacts"][0]["tables"]
    assert outputs[0]["artifacts"][0]["input"]["sha256"] != outputs[1]["artifacts"][0]["input"]["sha256"]
