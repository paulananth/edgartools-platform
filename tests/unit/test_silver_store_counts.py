from __future__ import annotations

from edgar_warehouse.silver_store import SilverDatabase


def test_get_table_counts_reports_missing_legacy_tables_as_zero(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        counts = db.get_table_counts()
    finally:
        db.close()

    assert counts["sec_tracked_universe"] == 0
    assert counts["sec_company"] == 0
