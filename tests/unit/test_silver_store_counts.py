from __future__ import annotations

from edgar_warehouse.bookkeeping.models import BOOKKEEPING_TABLES
from edgar_warehouse.silver_store import SilverDatabase


def test_get_table_counts_reports_missing_legacy_tables_as_zero(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        counts = db.get_table_counts()
    finally:
        db.close()

    assert counts["sec_tracked_universe"] == 0
    assert counts["sec_company"] == 0


def test_get_table_counts_excludes_bookkeeping_tables(tmp_path):
    """DuckDB Retirement Cutover Ticket 14: the 10 bookkeeping tables moved to
    the Postgres-backed BookkeepingStore, so SilverDatabase.get_table_counts()
    must never report them -- even though _DDL still creates them locally --
    so a caller's dict-merge with BookkeepingStore.get_table_counts() can't
    collide or overwrite the real Postgres-side count with a stale DuckDB 0."""
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        # sec_company_sync_state is one of the 10 -- still physically present
        # in DuckDB's own DDL (Ticket 14 doesn't drop the tables, only stops
        # reading/writing them from warehouse_orchestrator.py), so this
        # asserts the exclusion is enforced explicitly, not just an artifact
        # of the table never existing.
        db._conn.execute("INSERT INTO sec_company_sync_state (cik, tracking_status) VALUES (1, 'active')")
        counts = db.get_table_counts()
    finally:
        db.close()

    for table_name in BOOKKEEPING_TABLES:
        assert table_name not in counts
