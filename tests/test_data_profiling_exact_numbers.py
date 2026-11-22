"""Exact numeric inference through the public Data Profiling CLI seam."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/data-profiling/scripts"))
import profile_data


def _profile(tmp_path: Path, source: Path) -> dict:
    out = tmp_path / "findings"
    assert profile_data.main([
        "run", "--name", "exact-number-fixture", "--input", f"records={source}", "--out", str(out),
    ]) == 0
    return yaml.safe_load((out / "findings.yaml").read_text(encoding="utf-8"))


def _column(findings: dict, name: str) -> dict:
    part = next(part for part in findings["parts"] if part["part"] == "records")
    return next(column for column in part["columns"] if column["name"] == name)


def _silver_column(findings: dict, name: str) -> dict:
    part = next(part for part in findings["parts"] if part["part"] == "records")
    return next(column for column in part["silver"]["columns"] if column["name"] == name)


def test_csv_decimal_with_wide_integer_part_stays_exact(tmp_path: Path) -> None:
    source = tmp_path / "measurements.csv"
    source.write_text("amount\n12345678901234567.01\n98765432101234567.12\n", encoding="utf-8")

    findings = _profile(tmp_path, source)

    amount = _column(findings, "amount")
    assert amount["stored_type"] == "DECIMAL(19,2)"
    assert amount["decimal_places"] == 2
    assert amount["distinct"] == 2
    assert _silver_column(findings, "amount")["type"] == "DECIMAL(19,2)"


def test_json_decimal_keeps_lexical_precision(tmp_path: Path) -> None:
    source = tmp_path / "measurements.json"
    source.write_text(
        '[{"amount":12345678901234567.01},{"amount":98765432101234567.12}]',
        encoding="utf-8",
    )

    findings = _profile(tmp_path, source)

    amount = _column(findings, "amount")
    assert amount["stored_type"] == "DECIMAL(19,2)"
    assert amount["decimal_places"] == 2
    assert amount["distinct"] == 2
    assert _silver_column(findings, "amount")["type"] == "DECIMAL(19,2)"


def test_json_integer_identifiers_above_bigint_keep_all_distinct_values(tmp_path: Path) -> None:
    source = tmp_path / "identifiers.json"
    identifiers = [10**21 + i for i in range(60)]
    source.write_text(json.dumps([{"identifier": value} for value in identifiers]), encoding="utf-8")

    findings = _profile(tmp_path, source)

    identifier = _column(findings, "identifier")
    assert identifier["stored_type"] == "HUGEINT"
    assert identifier["distinct"] == 60
    assert _silver_column(findings, "identifier")["type"] == "HUGEINT"


def test_csv_integer_beyond_hugeint_remains_exact_text(tmp_path: Path) -> None:
    source = tmp_path / "wide-identifiers.csv"
    values = ["12345678901234567890123456789012345678901", "12345678901234567890123456789012345678902"]
    source.write_text("identifier\n" + "\n".join(values) + "\n", encoding="utf-8")

    findings = _profile(tmp_path, source)

    identifier = _column(findings, "identifier")
    assert identifier["stored_type"] == "VARCHAR"
    assert identifier["distinct"] == 2
    assert _silver_column(findings, "identifier")["type"] == "VARCHAR"
