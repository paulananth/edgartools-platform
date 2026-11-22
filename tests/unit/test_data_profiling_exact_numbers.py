"""Exact numeric inference through the public Data Profiling CLI seam."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills/data-profiling/scripts"))
import profile_data


def _column(part: dict, name: str) -> dict:
    return next(column for column in part["columns"] if column["name"] == name)


def _silver_column(part: dict, name: str) -> dict:
    return next(column for column in part["silver"]["columns"] if column["name"] == name)


def test_mixed_inputs_keep_repeated_identifiers_and_exact_decimals(tmp_path: Path) -> None:
    measurements = tmp_path / "measurements.csv"
    lines = ["identifier,name,amount,observed,active,ordinary_count"]
    for index in range(160):
        identifier = f"{index % 60 + 1:020d}"
        lines.append(f"{identifier},Name {index % 60 + 1},12345678901234567.01,2026-01-02,true,7")
    measurements.write_text("\n".join(lines) + "\n", encoding="utf-8")

    identifiers = tmp_path / "identifiers.json"
    identifiers.write_text(json.dumps([
        {"identifier": 10**21 + index} for index in range(60)
    ]), encoding="utf-8")

    text_dates = tmp_path / "text-dates.parquet"
    connection = duckdb.connect()
    connection.execute("CREATE TABLE text_dates AS SELECT value AS reported_on FROM "
                       "(VALUES ('2026-01-02'), ('2026-01-03')) AS dates(value)")
    path = str(text_dates).replace("'", "''")
    connection.execute(f"COPY text_dates TO '{path}' (FORMAT PARQUET)")
    connection.close()
    out = tmp_path / "findings"
    assert profile_data.main([
        "run", "--name", "exact-number-fixture",
        "--input", f"measurements={measurements}",
        "--input", f"identifiers={identifiers}",
        "--input", f"text_dates={text_dates}",
        "--out", str(out),
    ]) == 0
    findings = yaml.safe_load((out / "findings.yaml").read_text(encoding="utf-8"))
    parts = {part["part"]: part for part in findings["parts"]}

    measurements_part = parts["measurements"]
    assert measurements_part["record_key"]["columns"] != ["identifier"]
    derived = next(part for part in findings["parts"] if part.get("derived_from") == "measurements")
    assert derived["rows"] == 60
    assert _column(derived, "identifier")["distinct"] == 60

    identifier = _column(measurements_part, "identifier")
    assert identifier["stored_type"] == "VARCHAR"
    assert identifier["distinct"] == 60
    amount = _column(measurements_part, "amount")
    assert amount["stored_type"] == "DECIMAL(19,2)"
    assert amount["decimal_places"] == 2
    assert amount["distinct"] == 1
    assert _silver_column(measurements_part, "amount")["type"] == "DECIMAL(19,2)"
    count = _column(measurements_part, "ordinary_count")
    assert count["stored_type"] == "BIGINT"
    assert count["outside_bigint"] is False
    assert _silver_column(measurements_part, "ordinary_count")["type"] == "BIGINT"
    assert _column(measurements_part, "observed")["stored_type"].startswith("DATE")
    assert _column(measurements_part, "active")["stored_type"] == "BOOLEAN"

    text_date = _column(parts["text_dates"], "reported_on")
    assert text_date["stored_type"] == "VARCHAR"
    assert text_date["type"] == "DATE"
    assert _silver_column(parts["text_dates"], "reported_on")["type"] == "DATE"

    json_identifier = _column(parts["identifiers"], "identifier")
    assert json_identifier["stored_type"] == "HUGEINT"
    assert json_identifier["distinct"] == 60
    assert json_identifier["outside_bigint"] is True
    assert _silver_column(parts["identifiers"], "identifier")["type"] == "VARCHAR"


def test_sampled_csv_and_json_numbers_stay_exact_text(tmp_path: Path) -> None:
    csv_values = ["12345678901234567.12345678", "98765432101234567.87654321"]
    csv_path = tmp_path / "sampled.csv"
    csv_path.write_text("amount\n" + "\n".join(csv_values) + "\n", encoding="utf-8")
    json_values = ["12345678901234567.12345678", "98765432101234567.87654321"]
    json_identifiers = ["1234567890123456789012", "9876543210987654321098"]
    json_path = tmp_path / "sampled.json"
    records = [f'{{"identifier":{identifier},"amount":{amount}}}'
               for identifier, amount in zip(json_identifiers, json_values)]
    json_path.write_text("[" + ",".join(records) + "]", encoding="utf-8")

    out = tmp_path / "sampled-findings"
    assert profile_data.main([
        "run", "--name", "sampled-exact-number-fixture",
        "--input", f"csv={csv_path}",
        "--input", f"json={json_path}",
        "--out", str(out), "--limit-gb", "0.000000001", "--sample", "1", "--seed", "11",
    ]) == 0
    findings = yaml.safe_load((out / "findings.yaml").read_text(encoding="utf-8"))
    parts = {part["part"]: part for part in findings["parts"]}
    assert all(parts[name]["scan"] == "sampled" and parts[name]["rows"] == 1 for name in ("csv", "json"))

    csv_amount = _column(parts["csv"], "amount")
    assert csv_amount["stored_type"] == "VARCHAR"
    assert "outside_bigint" not in csv_amount and "decimal_places" not in csv_amount
    assert csv_amount["top"][0]["value"] in csv_values
    assert _silver_column(parts["csv"], "amount")["type"] == "VARCHAR"
    assert len(csv_values) > csv_amount["distinct"]  # at least one wide value was outside the sample

    json_amount = _column(parts["json"], "amount")
    assert json_amount["stored_type"] == "VARCHAR"
    assert "outside_bigint" not in json_amount and "decimal_places" not in json_amount
    assert json_amount["top"][0]["value"] in json_values
    assert len(json_values) > json_amount["distinct"]
    assert _silver_column(parts["json"], "amount")["type"] == "VARCHAR"
    json_identifier = _column(parts["json"], "identifier")
    assert json_identifier["stored_type"] == "VARCHAR"
    assert "outside_bigint" not in json_identifier
    assert json_identifier["top"][0]["value"] in json_identifiers
    assert _silver_column(parts["json"], "identifier")["type"] == "VARCHAR"
