from __future__ import annotations

import json
from pathlib import Path

import duckdb


def test_cli_writes_manifest_and_distributed_map_batches(tmp_path: Path, monkeypatch) -> None:
    from edgar_warehouse.scripts import build_relationship_release_manifest as command

    silver_path = tmp_path / "silver.duckdb"
    conn = duckdb.connect(str(silver_path))
    conn.execute(
        "CREATE TABLE sec_company_sync_state (cik BIGINT, tracking_status TEXT, last_main_sha256 TEXT)"
    )
    conn.execute("INSERT INTO sec_company_sync_state VALUES (1, 'active', 'submission-sha')")
    conn.execute(
        "CREATE TABLE sec_company_filing ("
        "accession_number TEXT, cik BIGINT, form TEXT, filing_date DATE, "
        "report_date DATE, items TEXT)"
    )
    conn.execute(
        "INSERT INTO sec_company_filing VALUES "
        "('proxy', 1, 'DEF 14A', DATE '2024-02-01', NULL, NULL)"
    )
    conn.close()

    monkeypatch.setattr(
        command,
        "fetch_quarter_indexes",
        lambda **_: {
            "2024Q1": [{
                "accession_number": "proxy",
                "cik": 1,
                "form": "DEF 14A",
                "filing_date": "2024-02-01",
            }]
        },
    )
    manifest_path = tmp_path / "candidate-manifest.json"
    batches_path = tmp_path / "candidate-batches.jsonl"

    assert command.main([
        "--silver-db", str(silver_path),
        "--coverage-start", "2024-01-01",
        "--watermark", "2024-03-31",
        "--output-path", str(manifest_path),
        "--batches-output-path", str(batches_path),
    ]) == 0

    manifest = json.loads(manifest_path.read_text())
    assert manifest["candidate_count"] == 1
    assert manifest["release_cik_count"] == 1
    assert manifest["candidates"][0]["source_manifest_fingerprint"] == "submission-sha"
    assert json.loads(batches_path.read_text()) == {"cik_list": "1"}
