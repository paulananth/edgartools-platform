"""Regression: an empty {"sources": []} manifest is a valid no-op, not an
error. ticket 06 (adv-pipeline map) wires fetch-adv-bulk to run daily and
legitimately find nothing new on most days -- ingest-relationship-sources
must not hard-fail that path. A malformed manifest (non-list "sources")
must still fail closed."""

from __future__ import annotations

import json

import pytest

from edgar_warehouse.application import warehouse_orchestrator
from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from tests.support.bookkeeping_fixtures import bookkeeping_fixture


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


def _write_manifest(tmp_path, payload: dict) -> str:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    return str(manifest_path)


def test_empty_sources_list_is_a_clean_no_op(tmp_path, monkeypatch) -> None:
    context = _context(tmp_path)
    manifest_path = _write_manifest(tmp_path, {"sources": []})
    monkeypatch.setattr(
        warehouse_orchestrator, "_bookkeeping_store", lambda: bookkeeping_fixture()
    )

    result = warehouse_orchestrator._execute_warehouse(
        context=context,
        command_name="ingest-relationship-sources",
        arguments={"source_manifest": manifest_path, "run_id": "empty-manifest-test"},
    )

    assert result["status"] == "ok"


def test_missing_sources_key_still_fails_closed(tmp_path, monkeypatch) -> None:
    context = _context(tmp_path)
    manifest_path = _write_manifest(tmp_path, {})
    monkeypatch.setattr(
        warehouse_orchestrator, "_bookkeeping_store", lambda: bookkeeping_fixture()
    )

    with pytest.raises(WarehouseRuntimeError, match="requires a sources list"):
        warehouse_orchestrator._execute_warehouse(
            context=context,
            command_name="ingest-relationship-sources",
            arguments={"source_manifest": manifest_path, "run_id": "missing-sources-test"},
        )


def test_non_list_sources_still_fails_closed(tmp_path, monkeypatch) -> None:
    context = _context(tmp_path)
    manifest_path = _write_manifest(tmp_path, {"sources": "not-a-list"})
    monkeypatch.setattr(
        warehouse_orchestrator, "_bookkeeping_store", lambda: bookkeeping_fixture()
    )

    with pytest.raises(WarehouseRuntimeError, match="requires a sources list"):
        warehouse_orchestrator._execute_warehouse(
            context=context,
            command_name="ingest-relationship-sources",
            arguments={"source_manifest": manifest_path, "run_id": "non-list-sources-test"},
        )
