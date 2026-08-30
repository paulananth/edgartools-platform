"""ingest-relationship-sources kind-dispatch coverage.

No dedicated test previously exercised the "iapd_adv_bulk" / "sec_subsidiary_
exhibit" / "iapd_firm_roster" branches inside warehouse_orchestrator.py's
ingest-relationship-sources handler end-to-end (confirmed by search before
writing this file) -- test_ingest_relationship_sources_empty_manifest.py only
covers the empty/malformed-manifest paths. This file adds the missing
"iapd_firm_roster" coverage (ticket 02), following that file's _context/
_write_manifest shape plus a real staged zip payload with a matching SHA-256.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

from edgar_warehouse.application import warehouse_orchestrator
from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.silver_store import SilverDatabase
from tests.support.bookkeeping_fixtures import bookkeeping_fixture

_HEADER = (
    '"Organization CRD#","7B","Count of Private Funds - 7B(1)",'
    '"Any Hedge Funds","Total number of Hedge funds",'
    '"Any PE Funds","Total number of PE funds",'
    '"Total Gross Assets of Private Funds","Count of Private Funds - 7B(2)"\n'
)
_ROW = '1588,"Y","3","Y","3","N","","709905606.00","0"\n'


def _context(tmp_path) -> WarehouseCommandContext:
    return WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation(str(tmp_path / "warehouse")),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="EdgarTools Platform test@example.com",
        runtime_mode="bronze_capture",
    )


def _db_path(context: WarehouseCommandContext) -> str:
    return context.silver_root.join("silver", "sec", "silver.duckdb")


def _write_manifest(tmp_path, payload: dict) -> str:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    return str(manifest_path)


def _firm_roster_archive() -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as bundle:
        bundle.writestr(
            "IA_SEC_-_FIRM_ROSTER_FOIA_DOWNLOAD_-_34622660.CSV", _HEADER + _ROW
        )
    return payload.getvalue()


def test_iapd_firm_roster_kind_dispatches_to_ingest_firm_roster_archive(tmp_path, monkeypatch) -> None:
    context = _context(tmp_path)
    archive = _firm_roster_archive()
    sha256 = hashlib.sha256(archive).hexdigest()
    staged_path = tmp_path / "staged" / "ia07012026.zip"
    staged_path.parent.mkdir(parents=True)
    staged_path.write_bytes(archive)
    monkeypatch.setattr(
        warehouse_orchestrator, "_bookkeeping_store", lambda: bookkeeping_fixture()
    )

    manifest_path = _write_manifest(tmp_path, {
        "sources": [
            {
                "kind": "iapd_firm_roster",
                "storage_path": str(staged_path),
                "sha256": sha256,
                "dataset_period": "2026-07",
            },
        ],
    })

    result = warehouse_orchestrator._execute_warehouse(
        context=context,
        command_name="ingest-relationship-sources",
        arguments={"source_manifest": manifest_path, "run_id": "firm-roster-dispatch-test"},
    )

    assert result["status"] == "ok"
    assert result["silver_table_counts"]["sec_adv_firm_roster"] == 1

    db = SilverDatabase(_db_path(context))
    try:
        rows = db.fetch(
            "SELECT adviser_crd_number, dataset_period, private_fund_count_7b1 "
            "FROM sec_adv_firm_roster"
        )
        assert rows == [
            {"adviser_crd_number": "1588", "dataset_period": "2026-07", "private_fund_count_7b1": 3}
        ]
    finally:
        db.close()
