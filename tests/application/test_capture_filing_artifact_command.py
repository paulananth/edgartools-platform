from __future__ import annotations

import hashlib
import json
from argparse import Namespace
from unittest.mock import patch

import pytest

from edgar_warehouse.acquisition.models import AcquisitionBase


@pytest.fixture()
def _acquisition_db(tmp_path, monkeypatch: pytest.MonkeyPatch) -> str:
    from sqlalchemy import create_engine

    db_path = tmp_path / "mdm.db"
    url = f"sqlite:///{db_path}"
    AcquisitionBase.metadata.create_all(create_engine(url))
    monkeypatch.setenv("MDM_DATABASE_URL", url)
    return url


def _set_warehouse_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("EDGAR_IDENTITY", "EdgarTools Platform test@example.com")
    monkeypatch.setenv("WAREHOUSE_ENVIRONMENT", "test")
    monkeypatch.setenv("WAREHOUSE_RUNTIME_MODE", "infrastructure_validation")
    monkeypatch.setenv("WAREHOUSE_BRONZE_ROOT", str(tmp_path / "bronze"))
    monkeypatch.setenv("WAREHOUSE_STORAGE_ROOT", str(tmp_path / "warehouse"))
    monkeypatch.setenv("WAREHOUSE_SILVER_ROOT", str(tmp_path / "silver"))
    for variable in ("SERVING_EXPORT_ROOT", "SNOWFLAKE_EXPORT_ROOT", "SILVER_LANDING_EXPORT_ROOT"):
        monkeypatch.delenv(variable, raising=False)


def test_capture_filing_artifact_command_captures_bronze_and_finalizes_ledger(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], _acquisition_db: str
) -> None:
    from edgar_warehouse.application.command_router import run_command

    _set_warehouse_env(monkeypatch, tmp_path)
    payload = b"<XML>Form 4 ownership document</XML>"

    with patch(
        "edgar_warehouse.acquisition.source_family_registry.download_filing_content_bytes",
        return_value=payload,
    ) as mocked_fetch:
        exit_code = run_command(
            "capture-filing-artifact",
            Namespace(
                candidate_id="candidate-cli-1",
                logical_source_key="0000320193/0000320193-26-000001/primary-document",
                source_url="https://www.sec.gov/Archives/example.xml",
                cause_reference="operator-backfill-cli-1",
                worker_id="cli-worker-1",
                lease_seconds=None,
                run_id="run-cli-1",
            ),
        )

    assert exit_code == 0
    mocked_fetch.assert_called_once_with(
        "https://www.sec.gov/Archives/example.xml", "EdgarTools Platform test@example.com"
    )
    result = json.loads(capsys.readouterr().out)
    assert result["candidate_id"] == "candidate-cli-1"
    assert result["source_family"] == "filing_artifact"
    assert result["fetch_disposition"] == "FETCH_AUTHORIZED"
    expected_hash = hashlib.sha256(payload).hexdigest()
    assert result["artifact"]["raw_evidence_hash"] == expected_hash
    assert result["artifact"]["bronze_relative_path"] == f"filing_artifact/{expected_hash}"

    stored = (tmp_path / "bronze" / "filing_artifact" / expected_hash).read_bytes()
    assert stored == payload

    # The registration's resolve_scope/planned_writes are genuinely exercised at
    # runtime, not just unit-tested in isolation (code-review finding).
    run_manifest_path = tmp_path / "bronze" / "runs" / "capture-filing-artifact" / "run-cli-1" / "run_manifest.json"
    assert run_manifest_path.exists()
    run_manifest_doc = json.loads(run_manifest_path.read_text())
    assert run_manifest_doc["command"] == "capture-filing-artifact"
    assert run_manifest_doc["scope"] == {"candidate_id": "candidate-cli-1"}
    written_layers = {entry["layer"] for entry in run_manifest_doc["manifests"]}
    assert written_layers == {"bronze", "staging", "artifacts"}
