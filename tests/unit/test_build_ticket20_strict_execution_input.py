from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from edgar_warehouse.application.relationship_bulk_load import (
    InventoryError,
    agent_coverage_by_document_type,
    build_ticket20_strict_execution_input,
    index_floor_coverage_start,
    normalize_s3_object_key,
)
from edgar_warehouse.scripts import build_ticket20_strict_execution_input as command


def _attestations() -> dict[str, str]:
    return {
        "warehouse": "W",
        "mdm": "M",
        "graph": "G",
        "release_data_operator": "O",
        "release_owner": "R",
    }


def test_normalize_s3_object_key() -> None:
    assert (
        normalize_s3_object_key(
            "s3://edgartools-prod-bronze-690839588395/warehouse/bronze/reference/x/candidate_manifest.json"
        )
        == "warehouse/bronze/reference/x/candidate_manifest.json"
    )
    assert normalize_s3_object_key("warehouse/bronze/x.json") == "warehouse/bronze/x.json"
    with pytest.raises(InventoryError):
        normalize_s3_object_key("s3://bucket-only")


def test_build_ticket20_strict_execution_input_shape() -> None:
    payload = build_ticket20_strict_execution_input(
        candidate_manifest_key=(
            "s3://edgartools-prod-bronze-690839588395/warehouse/bronze/reference/"
            "relationship_release/t20/candidate_manifest.json"
        ),
        candidate_batches_key=(
            "s3://edgartools-prod-bronze-690839588395/warehouse/bronze/reference/"
            "relationship_release/t20/candidate_batches.jsonl"
        ),
        attestations=_attestations(),
        batch_size=100,
        watermark=date(2026, 7, 2),
        fingerprint="fp",
    )
    assert payload["release_mode"] is True
    assert (
        payload["candidate_manifest_key"]
        == "warehouse/bronze/reference/relationship_release/t20/candidate_manifest.json"
    )
    assert (
        payload["candidate_batches_key"]
        == "warehouse/bronze/reference/relationship_release/t20/candidate_batches.jsonl"
    )
    assert payload["attestations"]["release_owner"] == "R"
    assert payload["watermark"] == "2026-07-02"
    assert payload["candidate_fingerprint"] == "fp"


def test_cli_writes_execution_input_with_preflight(tmp_path: Path, capsys) -> None:
    watermark = date(2026, 7, 2)
    windows = agent_coverage_by_document_type(watermark)
    manifest = {
        "coverage_start": index_floor_coverage_start(windows).isoformat(),
        "coverage_by_document_type": windows,
        "watermark": watermark.isoformat(),
        "fingerprint": "agent-fp",
        "candidates": [
            {
                "accession_number": "a",
                "cik": 1,
                "form": "13F-HR",
                "filing_date": "2025-08-14",
                "fingerprint": "c",
                "candidate_reason": "thirteenf_filing",
                "artifact_required": True,
            }
        ],
    }
    manifest_path = tmp_path / "candidate_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    out_path = tmp_path / "input.json"
    att = json.dumps(_attestations())
    assert (
        command.main(
            [
                "--candidate-manifest",
                str(manifest_path),
                "--attestations-json",
                att,
                "--preflight",
                "--output",
                str(out_path),
            ]
        )
        == 0
    )
    written = json.loads(out_path.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert written == printed
    assert written["release_mode"] is True
    assert written["candidate_batches_key"].endswith("candidate_batches.jsonl")
    assert written["candidate_fingerprint"] == "agent-fp"
