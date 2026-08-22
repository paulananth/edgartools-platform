"""Skip-if-unchanged silver publish (release-readiness ticket 79).

Real DB-backed tests, matching this workstream's established discipline
(tickets 67-78): a genuine ``SilverDatabase``-created canonical file plays
the role of what's on S3, hydration is exercised for real (not mocked),
and only the S3-facing calls (``read_object_version``/``write_staged_bytes``/
``promote_staged``) are patched -- so a mismatch between the fingerprint
check and the real merge logic would show up as a real assertion failure,
not a mocked-away no-op.
"""

from __future__ import annotations

import duckdb
import pytest
from unittest.mock import patch

from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import (
    ObjectVersion,
    PromotionResult,
    StorageLocation,
)
from edgar_warehouse.silver_protection import SilverPublicationError
from edgar_warehouse.silver_store import SilverDatabase


def _build_context(tmp_path):
    return WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation("s3://bucket/warehouse"),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="dev@example.com",
        runtime_mode="bronze_capture",
    )


def _build_canonical_bytes(tmp_path) -> bytes:
    """A real canonical silver.duckdb (full DDL, one sec_company row)."""
    canonical_path = tmp_path / "canonical.duckdb"
    db = SilverDatabase(str(canonical_path))
    db._conn.execute(
        "INSERT INTO sec_company (cik, entity_name, last_synced_at) "
        "VALUES (1, 'Alpha Corp', '2026-01-01 00:00:00')"
    )
    db.close()
    return canonical_path.read_bytes()


def _hydrate(context, canonical_bytes):
    from edgar_warehouse.application.warehouse_orchestrator import (
        _hydrate_silver_database_from_storage,
    )

    def fake_download_file(relative_path, local_path, chunk_size=8 * 1024 * 1024):
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(canonical_bytes)
        return str(local_path)

    with patch(
        "edgar_warehouse.infrastructure.object_storage.StorageLocation.download_file",
        side_effect=fake_download_file,
    ):
        _hydrate_silver_database_from_storage(context)


def _local_silver_path(context) -> str:
    return context.silver_root.join("silver", "sec", "silver.duckdb")


def test_noop_publish_is_skipped_without_touching_s3(tmp_path):
    """Candidate identical to canonical -> publish is skipped entirely."""
    context = _build_context(tmp_path)
    canonical_bytes = _build_canonical_bytes(tmp_path)
    _hydrate(context, canonical_bytes)

    from edgar_warehouse.application.warehouse_orchestrator import (
        _publish_silver_database_if_remote,
    )

    with (
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.read_object_version"
        ) as mock_version,
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.write_staged_bytes"
        ) as mock_stage,
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.promote_staged"
        ) as mock_promote,
    ):
        result = _publish_silver_database_if_remote(context)

    mock_version.assert_not_called()
    mock_stage.assert_not_called()
    mock_promote.assert_not_called()
    assert result["skipped"] is True
    assert result["tables_merged"] == []


def test_real_change_still_runs_full_merge(tmp_path):
    """A genuine change to a protected table -> unchanged full-merge behavior."""
    context = _build_context(tmp_path)
    canonical_bytes = _build_canonical_bytes(tmp_path)
    _hydrate(context, canonical_bytes)

    conn = duckdb.connect(_local_silver_path(context))
    conn.execute(
        "INSERT INTO sec_company (cik, entity_name, last_synced_at) "
        "VALUES (2, 'Beta Corp', '2026-01-02 00:00:00')"
    )
    conn.close()

    from edgar_warehouse.application.warehouse_orchestrator import (
        _publish_silver_database_if_remote,
    )

    with (
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.read_object_version",
            return_value=ObjectVersion(exists=True, etag="old-etag", version_id=None),
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator.read_bytes",
            return_value=canonical_bytes,
        ),
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.write_staged_bytes",
            return_value="silverstage/token/silver/sec/silver.duckdb",
        ) as mock_stage,
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.promote_staged",
            return_value=PromotionResult(
                canonical_path="s3://bucket/warehouse/silver/sec/silver.duckdb",
                staged_relative_path="silverstage/token/silver/sec/silver.duckdb",
                previous_version=ObjectVersion(exists=True, etag="old-etag", version_id=None),
                new_version=ObjectVersion(exists=True, etag="new-etag", version_id=None),
            ),
        ) as mock_promote,
    ):
        result = _publish_silver_database_if_remote(context)

    mock_stage.assert_called_once()
    mock_promote.assert_called_once()
    assert "skipped" not in result
    assert "sec_company" in result["tables_merged"]


def test_excluded_table_only_change_is_still_skipped(tmp_path):
    """A write to pipeline_run alone (bookkeeping) must not defeat the skip.

    This is the specific case a naive "is the local file byte-identical to
    what was hydrated" check would get wrong -- pipeline_run/sec_sync_run
    are written on every command's local copy regardless of whether any
    real domain data changed.
    """
    context = _build_context(tmp_path)
    canonical_bytes = _build_canonical_bytes(tmp_path)
    _hydrate(context, canonical_bytes)

    db = SilverDatabase(_local_silver_path(context))
    db.start_pipeline_run(
        {
            "pipeline_run_id": "run-1",
            "command_name": "gold-refresh",
            "runtime_mode": "bronze_capture",
        }
    )
    db.close()

    from edgar_warehouse.application.warehouse_orchestrator import (
        _publish_silver_database_if_remote,
    )

    with (
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.read_object_version"
        ) as mock_version,
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.write_staged_bytes"
        ) as mock_stage,
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.promote_staged"
        ) as mock_promote,
    ):
        result = _publish_silver_database_if_remote(context)

    mock_version.assert_not_called()
    mock_stage.assert_not_called()
    mock_promote.assert_not_called()
    assert result["skipped"] is True


def test_new_unregistered_table_forces_merge_and_guard_still_fires(tmp_path):
    """A brand-new, unclassified table must never slip past the skip check.

    The fingerprint's table-name set (not just PROTECTED_TABLE_REGISTRY
    content) must change when a new table appears locally, or an
    unregistered domain table could be silently dropped by the skip path
    instead of tripping merge_candidate_into_canonical's fail-closed
    unclassified-table guard.
    """
    context = _build_context(tmp_path)
    canonical_bytes = _build_canonical_bytes(tmp_path)
    _hydrate(context, canonical_bytes)

    conn = duckdb.connect(_local_silver_path(context))
    conn.execute("CREATE TABLE totally_new_domain_table (id INTEGER)")
    conn.execute("INSERT INTO totally_new_domain_table VALUES (1)")
    conn.close()

    from edgar_warehouse.application.warehouse_orchestrator import (
        _publish_silver_database_if_remote,
    )

    with (
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.read_object_version",
            return_value=ObjectVersion(exists=True, etag="old-etag", version_id=None),
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator.read_bytes",
            return_value=canonical_bytes,
        ),
    ):
        with pytest.raises(SilverPublicationError, match="Unclassified"):
            _publish_silver_database_if_remote(context)


def test_real_change_only_merges_the_actually_changed_table(tmp_path):
    """seed-universe OOM root cause (found live 2026-08-22): a candidate that
    only changed sec_company_ticker must not drag sec_company (or any other
    untouched table) through a real merge pass -- the per-table fingerprint
    diff between hydration-time and publish-time must scope the merge to
    exactly the tables that actually changed, not "differs at all ->
    full scope"."""
    context = _build_context(tmp_path)
    canonical_bytes = _build_canonical_bytes(tmp_path)
    _hydrate(context, canonical_bytes)

    conn = duckdb.connect(_local_silver_path(context))
    conn.execute(
        "INSERT INTO sec_company_ticker "
        "(cik, ticker, exchange, source_name, source_rank, last_sync_run_id, last_synced_at) "
        "VALUES (1, 'ALPHA', 'NASDAQ', 'company_tickers_exchange', 1, 'run-1', '2026-01-01 00:00:00')"
    )
    conn.close()

    from edgar_warehouse.application.warehouse_orchestrator import (
        _publish_silver_database_if_remote,
    )

    with (
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.read_object_version",
            return_value=ObjectVersion(exists=True, etag="old-etag", version_id=None),
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator.read_bytes",
            return_value=canonical_bytes,
        ),
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.write_staged_bytes",
            return_value="silverstage/token/silver/sec/silver.duckdb",
        ),
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.promote_staged",
            return_value=PromotionResult(
                canonical_path="s3://bucket/warehouse/silver/sec/silver.duckdb",
                staged_relative_path="silverstage/token/silver/sec/silver.duckdb",
                previous_version=ObjectVersion(exists=True, etag="old-etag", version_id=None),
                new_version=ObjectVersion(exists=True, etag="new-etag", version_id=None),
            ),
        ),
    ):
        result = _publish_silver_database_if_remote(context)

    assert "sec_company_ticker" in result["tables_merged"]
    assert "sec_company" not in result["tables_merged"], (
        "sec_company was untouched since hydration but still went through a full merge pass"
    )
