"""Bounded, receipt-pinned combination independent of source loaders."""
import json

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import mdm_prepare, source_combine


def group(source, table, key, value, *, mode="collect", order_by=(), distinct=False, where=None, checks=None):
    return {"source": source, "table": table, "key": key, "value": value, "mode": mode,
            "order_by": list(order_by), "distinct": distinct, "skip_null_values": True,
            "checks": checks or {}, "where": where or {}}


def table(source, name, joins, *, checks=None):
    return {"source": source, "table": name, "checks": checks or {}, "where": {}, "joins": joins}


def join(name, key="cik", *, missing="empty", replace=False):
    return {"group": name, "key": key, "on_missing": missing, "replace": replace}


def reading(store, root, tables, *, deferred=None):
    captured = store.put(root.as_uri(), {"fixture": tables})
    return store.put(root.as_uri(), {"version": 1, "artifacts": [
        {"input": captured, "tables": tables, "deferred": deferred or []}]})


def envelope(store, root, body, refs):
    contract = store.put(root.as_uri(), body)
    manifest = store.put(root.as_uri(), {"version": 1, "contract": contract, "readings": refs})
    return {"input": manifest, "output": (root / "output/combined.json").as_uri(), "checks": [source_combine.CHECK], "keys": {}}


def plan(groups, tables, limit=1000):
    return {"execution": {"profile": "source.combine"}, "combine": {"max_rows": limit, "groups": groups, "tables": tables}}


def test_order_distinct_exact_keys_and_preparation_share_verified_scope(tmp_path):
    store = Artifacts()
    refs = {"main": reading(store, tmp_path, {"companies": [{"cik": 1}, {"cik": "1"}, {"cik": 2}]}),
            "aux": reading(store, tmp_path, {"listings": [{"cik": 1, "rank": 2, "ticker": "B"},
                          {"cik": 1, "rank": 1, "ticker": "A"}, {"cik": 1, "rank": 3, "ticker": "A"},
                          {"cik": "1", "rank": 1, "ticker": "TEXT"}, {"cik": None, "rank": 0, "ticker": "NULL"}]})}
    body = plan({"tickers": group("aux", "listings", "cik", "ticker", order_by=("rank", "ticker"), distinct=True)},
                {"companies": table("main", "companies", {"tickers": join("tickers")})})
    work = envelope(store, tmp_path, body, refs)
    result = source_combine.execute(work, store)
    assert source_combine.execute(work, store) == result  # repeat/lost acknowledgement
    assert source_combine.verify({**work, "candidate": result}, store) == ({source_combine.CHECK: True}, [])
    combined = store.json(result)
    assert combined["artifacts"][0]["tables"]["companies"] == [
        {"cik": 1, "tickers": ["A", "B"]}, {"cik": "1", "tickers": ["TEXT"]}, {"cik": 2, "tickers": []}]
    assert store.json(combined["artifacts"][0]["input"])["readings"] == refs
    keys = {"table": "companies", "dataset": "fixture.companies", "policy": "0" * 64,
            "consumer": "trial", "batch_id": "combined", "as_of": "2026-10-04T00:00:00Z"}
    prepare = {"input": result, "output": (tmp_path / "mdm/manifest.json").as_uri(), "keys": keys, "checks": ["mdm.prepared"]}
    prepared = mdm_prepare.execute(prepare, store)
    assert mdm_prepare.verify({**prepare, "candidate": prepared}, store) == ({"mdm.prepared": True}, [])
    first = store.json(prepared)["batches"][0]
    actual = [json.loads(line) for line in (tmp_path / "mdm" / first["input"]["path"]).read_text().splitlines()]
    assert actual == combined["artifacts"][0]["tables"]["companies"]


@pytest.mark.parametrize("mutation", ["bad_key", "missing_column", "mixed_order", "missing_match", "overwrite", "capture", "deferred"])
def test_refusal_never_writes_partial_output(tmp_path, mutation):
    store = Artifacts()
    rows = [{"cik": 1, "form": "10-K", "rank": 1, "capture": "run"}, {"cik": 1, "form": "10-Q", "rank": 2, "capture": "run"}]
    primary = [{"cik": 1}]
    groups = {"forms": group("aux", "filings", "cik", "form", order_by=("rank",), checks={"capture": "run"})}
    joins = {"forms": join("forms")}
    deferred = []
    if mutation == "bad_key": rows[0]["cik"] = True
    if mutation == "missing_column": del rows[0]["form"]
    if mutation == "mixed_order": rows[1]["rank"] = "2"
    if mutation == "missing_match": primary[0]["cik"] = 2; joins["forms"]["on_missing"] = "error"
    if mutation == "overwrite": primary[0]["forms"] = ["prior"]
    if mutation == "capture": rows[0]["capture"] = "foreign"
    if mutation == "deferred": deferred = [{"reason": "unresolved"}]
    refs = {"main": reading(store, tmp_path, {"companies": primary}),
            "aux": reading(store, tmp_path, {"filings": rows}, deferred=deferred)}
    work = envelope(store, tmp_path, plan(groups, {"companies": table("main", "companies", joins)}), refs)
    with pytest.raises(ValueError): source_combine.execute(work, store)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("budget", ["rows", "input_bytes", "total_bytes", "output_bytes"])
def test_budgets_fail_before_any_output(tmp_path, monkeypatch, budget):
    store = Artifacts()
    refs = {"main": reading(store, tmp_path, {"companies": [{"cik": 1}, {"cik": 2}]})}
    body = plan({}, {"companies": table("main", "companies", {})}, limit=1 if budget == "rows" else 1000)
    if budget != "rows": monkeypatch.setattr(source_combine, {"input_bytes": "INPUT_BYTES", "total_bytes": "TOTAL_BYTES", "output_bytes": "OUTPUT_BYTES"}[budget], 1)
    work = envelope(store, tmp_path, body, refs)
    with pytest.raises(ValueError): source_combine.execute(work, store)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("changed", ["reading", "candidate", "scope"])
def test_verifier_rejects_changed_receipts(tmp_path, changed):
    store = Artifacts()
    ref = reading(store, tmp_path, {"companies": [{"cik": 1}]})
    work = envelope(store, tmp_path, plan({}, {"companies": table("main", "companies", {})}), {"main": ref})
    result = source_combine.execute(work, store)
    target = {"reading": ref, "candidate": result, "scope": store.json(result)["artifacts"][0]["input"]}[changed]
    from urllib.parse import urlparse
    from pathlib import Path
    Path(urlparse(target["uri"]).path).write_bytes(b'{}')
    with pytest.raises(ValueError): source_combine.verify({**work, "candidate": result}, store)


def test_predecessor_reading_and_changed_contract_have_distinct_mdm_scope(tmp_path):
    store = Artifacts()
    primary = reading(store, tmp_path, {"companies": [{"cik": 1, "name": "A"}]})
    body = plan({"names": group("main", "companies", "cik", "name")},
                {"companies": table("main", "companies", {"names": join("names")})})
    contract = store.put(tmp_path.as_uri(), body)
    work = {"input": primary, "output": (tmp_path / "one/combined.json").as_uri(), "checks": [source_combine.CHECK],
            "keys": {"combine_contract": contract, "reading_name": "main", "readings": {}}}
    result = source_combine.execute(work, store)
    assert source_combine.verify({**work, "candidate": result}, store) == ({source_combine.CHECK: True}, [])
    original = store.json(result)["artifacts"][0]["input"]
    body["combine"]["groups"]["names"]["distinct"] = True
    changed = {**work, "output": (tmp_path / "two/combined.json").as_uri(),
               "keys": {**work["keys"], "combine_contract": store.put(tmp_path.as_uri(), body)}}
    second = source_combine.execute(changed, store)
    assert store.json(second)["artifacts"][0]["input"]["sha256"] != original["sha256"]


@pytest.mark.parametrize("mutation", ["profile", "unknown", "limit_bool", "group", "join", "source", "empty_table", "readings", "partial_predecessor"])
def test_invalid_configuration_fails_before_reading_or_writing(tmp_path, mutation):
    store = Artifacts()
    refs = {"main": reading(store, tmp_path, {"companies": []})}
    body = plan({"names": group("main", "companies", "cik", "name")}, {"companies": table("main", "companies", {"names": join("names")})})
    if mutation == "profile": body["execution"]["profile"] = "company.prepare"
    if mutation == "unknown": body["combine"]["typo"] = True
    if mutation == "limit_bool": body["combine"]["max_rows"] = True
    if mutation == "group": body["combine"]["groups"]["names"]["distinct"] = 1
    if mutation == "join": body["combine"]["tables"]["companies"]["joins"]["names"]["group"] = "absent"
    if mutation == "source": body["combine"]["groups"]["names"]["source"] = "absent"
    if mutation == "empty_table": body["combine"]["tables"] = {}
    if mutation == "readings": refs = {}
    work = envelope(store, tmp_path, body, refs)
    if mutation == "partial_predecessor": work["keys"] = {"reading_name": "main"}
    with pytest.raises(ValueError): source_combine.execute(work, store)
    assert not (tmp_path / "output").exists()
