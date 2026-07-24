from __future__ import annotations

import io
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
        "--uniform-coverage",
        "--watermark", "2024-03-31",
        "--output-path", str(manifest_path),
        "--batches-output-path", str(batches_path),
    ]) == 0

    manifest = json.loads(manifest_path.read_text())
    assert manifest["candidate_count"] == 1
    assert manifest["release_cik_count"] == 1
    assert manifest["coverage_start"] == "2024-01-01"
    assert manifest["coverage_by_document_type"]["proxy"]["start"] == "2024-01-01"
    assert manifest["candidates"][0]["source_manifest_fingerprint"] == "submission-sha"
    assert json.loads(batches_path.read_text()) == {"cik_list": "1"}


def test_local_silver_db_passthrough_for_non_s3_path(tmp_path: Path) -> None:
    from edgar_warehouse.scripts import build_relationship_release_manifest as command

    local = tmp_path / "silver.duckdb"
    local.write_bytes(b"local-bytes")

    with command._local_silver_db(str(local)) as resolved:
        assert resolved == str(local)

    assert local.exists()


def test_s3_silver_db_streams_to_temp_file_and_cleans_up(monkeypatch) -> None:
    from edgar_warehouse.scripts import build_relationship_release_manifest as command

    payload = b"fake production silver.duckdb bytes"
    captured: dict[str, str] = {}

    class FakeOpenFile:
        def __enter__(self) -> io.BytesIO:
            return io.BytesIO(payload)

        def __exit__(self, *exc: object) -> bool:
            return False

    def fake_fsspec_open(path: str, mode: str) -> FakeOpenFile:
        captured["path"] = path
        captured["mode"] = mode
        return FakeOpenFile()

    monkeypatch.setattr("fsspec.open", fake_fsspec_open)

    saved_path: Path
    with command._local_silver_db("s3://bucket/warehouse/silver/sec/silver.duckdb") as resolved:
        assert captured == {"path": "s3://bucket/warehouse/silver/sec/silver.duckdb", "mode": "rb"}
        saved_path = Path(resolved)
        assert saved_path.read_bytes() == payload

    assert not saved_path.exists()


def test_cli_subcommand_dispatches_to_build_relationship_release_manifest(
    tmp_path: Path, monkeypatch
) -> None:
    from edgar_warehouse.cli import build_parser
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

    args = build_parser().parse_args([
        "mdm", "build-relationship-release-manifest",
        "--silver-db", str(silver_path),
        "--coverage-start", "2024-01-01",
        "--uniform-coverage",
        "--watermark", "2024-03-31",
        "--output-path", str(manifest_path),
        "--batches-output-path", str(batches_path),
    ])

    assert args.handler(args) == 0

    manifest = json.loads(manifest_path.read_text())
    assert manifest["candidate_count"] == 1
    assert manifest["release_cik_count"] == 1
