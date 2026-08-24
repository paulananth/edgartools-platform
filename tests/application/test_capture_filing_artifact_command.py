from __future__ import annotations

import hashlib
import json
from argparse import Namespace
from unittest.mock import patch

import pytest

from datetime import date

from edgar_warehouse.acquisition.models import AcquisitionBase
from edgar_warehouse.acquisition.registry_ledger import CoverageSpec, SourceRegistryLedger


@pytest.fixture()
def _acquisition_db(tmp_path, monkeypatch: pytest.MonkeyPatch) -> str:
    from sqlalchemy import create_engine

    db_path = tmp_path / "mdm.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    AcquisitionBase.metadata.create_all(engine)
    monkeypatch.setenv("MDM_DATABASE_URL", url)
    _activate_filing_artifact_registry(engine)
    return url


def _activate_filing_artifact_registry(engine) -> None:
    """Ticket 20: no acquisition command runs without an active Source Family
    Registry version -- seed and activate one covering filing_artifact,
    mirroring the real bootstrap a fresh deployment needs.
    """

    ledger = SourceRegistryLedger(engine)
    version = ledger.open_draft(
        [
            CoverageSpec(
                source_family="filing_artifact",
                coverage_action="add",
                in_scope_forms=("3", "3/A", "4", "4/A", "5", "5/A"),
                acquisition_mode="on_demand_fetch",
                completeness_policy="non_empty_payload",
                discovery_policy="daily_index_driven",
                required_producers=("sec_raw_object",),
                coverage_start_date=date(2026, 1, 1),
                catchup_required_through_date=date(2026, 1, 1),
            )
        ],
        operator_authorization_reference="test-bootstrap",
    )
    ledger.record_catchup_progress("filing_artifact", date(2026, 1, 1))
    activated = ledger.activate(version.version_id)
    assert activated.status == "active"


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
