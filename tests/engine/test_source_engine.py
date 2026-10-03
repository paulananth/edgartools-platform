"""The configured source engine through its Python facade (mastering to-do 15).

The Rust acceptance suite (`crates/source-contract/tests/acceptance.rs`) proves
the readers and checks. These prove the facade: contracts as rules-file
dicts, Python custom steps, lookups, the records set aside and the error.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from edgar_warehouse.rules import steps
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected

CRATE = Path(__file__).resolve().parents[2] / "crates" / "source-contract"
FIXTURES = CRATE / "tests" / "fixtures"
LEIS = ["5493001KJTIIGC8Y1R12", "529900T8BM49AURSDO55"]


def gleif() -> SourceEngine:
    return SourceEngine(yaml.safe_load((FIXTURES / "gleif-level1.yaml").read_text()))


def xml() -> bytes:
    return (FIXTURES / "gleif-two-records.xml").read_bytes()


def test_a_rules_file_contract_reads_its_rows():
    reading = gleif().read(xml(), lookups={"eligible_leis": LEIS})
    rows = reading.tables["gleif_projection"]
    assert [(r["ordinal"], r["lei"], r["name"], r["postal_code"]) for r in rows] == [
        (1, LEIS[0], "Acme & Company", "10001"), (2, LEIS[1], "Example Limited", None)]
    assert reading.deferred == []


def test_a_record_out_of_scope_is_set_aside_with_its_raw_record():
    reading = gleif().read(xml(), lookups={"eligible_leis": {LEIS[1]}})
    (record,) = reading.deferred
    assert (record["table"], record["ordinal"], record["reason"]) == (
        "gleif_projection", 1, "outside_approved_company_scope")
    # Shaped as the Python readers shape a record: text under `$`.
    assert record["raw"]["LEI"] == {"$": LEIS[0]}
    assert record["raw"]["Entity"]["LegalName"] == {"$": "Acme & Company", "@lang": "en"}


def test_a_failed_artifact_raises_with_its_code():
    with pytest.raises(SourceRejected) as error:
        gleif().read(xml().replace(b"lei:LEIData", b"lei:OtherData"), lookups={"eligible_leis": LEIS})
    assert error.value.code == "wrong_root"
    with pytest.raises(SourceRejected, match="missing_lookup"):
        gleif().read(xml())


def test_13f_text_nullification_is_expressed_in_yaml_and_runs_through_the_facade():
    contract = yaml.safe_load((CRATE / "contracts" / "thirteenf" / "contract.yaml").read_text())
    data = (CRATE / "contracts" / "thirteenf" / "fixtures" / "one-row.xml").read_bytes()
    (row,) = SourceEngine(contract).read(data).tables["sec_thirteenf_holding"]
    assert (row["cusip"], row["put_call"], row["shares_held"]) == ("88579Y101", None, 54242.0)


def test_a_step_missing_from_the_registry_is_refused_when_the_contract_loads():
    contract = {"read": {"format": "jsonl", "tables": {"rows": {"each": "record", "columns": {
        "a": {"custom": {"step": "nowhere@1", "inputs": {"value": {"text": {"path": "a"}}}}}}}}}}
    with pytest.raises(SourceRejected) as error:
        SourceEngine(contract)
    assert (error.value.code, error.value.detail) == ("contract", "no value step nowhere@1")


def test_a_step_that_fails_fails_the_artifact(monkeypatch):
    def broken(value):
        raise ValueError("no")

    monkeypatch.setitem(steps.STEPS, "broken@1", broken)
    contract = {"read": {"format": "jsonl", "tables": {"rows": {"each": "record", "columns": {
        "a": {"custom": {"step": "broken@1", "inputs": {"value": {"text": {"path": "a"}}}}}}}}}}
    with pytest.raises(SourceRejected) as error:
        SourceEngine(contract).read(b'{"a": "x"}\n')
    assert error.value.code == "step_failed" and "no" in error.value.detail


def test_a_lookup_given_as_one_string_is_refused():
    with pytest.raises(TypeError, match="one string"):
        gleif().read(xml(), lookups={"eligible_leis": LEIS[0]})
