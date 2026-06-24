"""Regression test: mdm run must read a monolith silver.duckdb when no shard
manifest exists yet (first-load recovery via bronze_seed_silver_gold), instead
of failing with "cannot open MDM_SILVER_DUCKDB -- shard-manifest.json"."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.mdm import cli as mdm_cli


def test_silver_reader_falls_back_to_monolith_when_shard_manifest_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("WAREHOUSE_STORAGE_ROOT", "s3://bucket/warehouse")
    monkeypatch.delenv("MDM_SILVER_DUCKDB", raising=False)

    silver_root = StorageLocation(str(tmp_path))
    monolith_path = Path(silver_root.join("silver", "sec", "silver.duckdb"))
    monolith_path.parent.mkdir(parents=True)
    monolith_path.write_bytes(b"")

    context = MagicMock()
    context.silver_root = silver_root

    with (
        patch(
            "edgar_warehouse.application.command_context_factory.build_warehouse_context",
            return_value=context,
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._hydrate_all_shards",
            side_effect=FileNotFoundError("shard-manifest.json"),
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._hydrate_silver_database_from_storage",
        ) as mock_hydrate,
        patch(
            "edgar_warehouse.silver_support.sharded_reader.ShardedSilverReader",
        ) as mock_reader_cls,
    ):
        mdm_cli._silver_reader()

    mock_hydrate.assert_called_once_with(context)
    mock_reader_cls.assert_called_once_with([str(monolith_path)])


def test_silver_reader_returns_none_when_monolith_also_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("WAREHOUSE_STORAGE_ROOT", "s3://bucket/warehouse")
    monkeypatch.delenv("MDM_SILVER_DUCKDB", raising=False)

    silver_root = StorageLocation(str(tmp_path))
    context = MagicMock()
    context.silver_root = silver_root

    with (
        patch(
            "edgar_warehouse.application.command_context_factory.build_warehouse_context",
            return_value=context,
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._hydrate_all_shards",
            side_effect=FileNotFoundError("shard-manifest.json"),
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._hydrate_silver_database_from_storage",
        ),
    ):
        result = mdm_cli._silver_reader()

    assert result is None
