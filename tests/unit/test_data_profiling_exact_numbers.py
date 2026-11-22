"""Exact numeric inference through the public Data Profiling CLI seam."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills/data-profiling/scripts"))
import profile_data


def _column(part: dict, name: str) -> dict:
    return next(column for column in part["columns"] if column["name"] == name)


def _silver_column(part: dict, name: str) -> dict:
    return next(column for column in part["silver"]["columns"] if column["name"] == name)


def test_mixed_inputs_keep_repeated_identifiers_and_exact_decimals(tmp_path: Path) -> None:
    measurements = tmp_path / "measurements.csv"
    lines = ["identifier,name,amount,observed,active"]
    for index in range(40):
        identifier = f"{index % 30:020d}"
        lines.append(f"{identifier},Name {index % 30},12345678901234567.01,2026-01-02,true")
    measurements.write_text("\n".join(lines) + "\n", encoding="utf-8")

    identifiers = tmp_path / "identifiers.json"
    identifiers.write_text(json.dumps([
        {"identifier": 10**21 + index} for index in range(60)
    ]), encoding="utf-8")

    out = tmp_path / "findings"
    assert profile_data.main([
        "run", "--name", "exact-number-fixture",
        "--input", f"measurements={measurements}",
        "--input", f"identifiers={identifiers}",
        "--out", str(out),
    ]) == 0
    findings = yaml.safe_load((out / "findings.yaml").read_text(encoding="utf-8"))
    parts = {part["part"]: part for part in findings["parts"]}

    measurements_part = parts["measurements"]
    assert measurements_part["record_key"]["columns"] != ["identifier"]
    derived = next(part for part in findings["parts"] if part.get("derived_from") == "measurements")
    assert derived["rows"] == 30
    assert _column(derived, "identifier")["distinct"] == 30

    identifier = _column(measurements_part, "identifier")
    assert identifier["stored_type"] == "VARCHAR"
    assert identifier["distinct"] == 30
    amount = _column(measurements_part, "amount")
    assert amount["stored_type"] == "DECIMAL(19,2)"
    assert amount["decimal_places"] == 2
    assert amount["distinct"] == 1
    assert _silver_column(measurements_part, "amount")["type"] == "DECIMAL(19,2)"
    assert _column(measurements_part, "observed")["stored_type"].startswith("DATE")
    assert _column(measurements_part, "active")["stored_type"] == "BOOLEAN"

    json_identifier = _column(parts["identifiers"], "identifier")
    assert json_identifier["stored_type"] == "HUGEINT"
    assert json_identifier["distinct"] == 60
    assert _silver_column(parts["identifiers"], "identifier")["type"] == "VARCHAR"
