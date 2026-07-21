from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from edgar_warehouse.application.relationship_bulk_load import (
    agent_coverage_by_document_type,
    index_floor_coverage_start,
)
from edgar_warehouse.scripts import validate_relationship_release_manifest as command


def test_cli_ready_for_strict_load(tmp_path: Path, capsys) -> None:
    watermark = date(2026, 7, 2)
    windows = agent_coverage_by_document_type(watermark)
    payload = {
        "schema_version": 1,
        "coverage_start": index_floor_coverage_start(windows).isoformat(),
        "coverage_by_document_type": windows,
        "watermark": watermark.isoformat(),
        "fingerprint": "agent-fp",
        "candidates": [
            {
                "accession_number": "new-13f",
                "cik": 9,
                "form": "13F-HR",
                "filing_date": "2025-08-14",
                "fingerprint": "c-fp",
                "candidate_reason": "thirteenf_filing",
                "artifact_required": True,
            }
        ],
        "cik_batches": [{"cik_list": "9"}],
    }
    path = tmp_path / "candidate_manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert command.main(["--candidate-manifest", str(path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["disposition"] == "READY_FOR_STRICT_LOAD"
    assert report["strict_release_eligible"] is True


def test_cli_rejects_legacy_freeze(tmp_path: Path, capsys) -> None:
    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps(
            {
                "coverage_start": "2013-05-20",
                "watermark": "2026-07-02",
                "fingerprint": "legacy",
                "candidates": [
                    {
                        "accession_number": "x",
                        "cik": 1,
                        "form": "13F-HR",
                        "filing_date": "2014-01-01",
                        "fingerprint": "c",
                        "artifact_required": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert command.main(["--candidate-manifest", str(path)]) == 2
    err = json.loads(capsys.readouterr().err)
    assert err["disposition"] == "NO_GO"
    assert err["strict_release_eligible"] is False
