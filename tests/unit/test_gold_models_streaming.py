from __future__ import annotations

import itertools
from unittest.mock import patch

import pyarrow as pa

from edgar_warehouse.serving.gold_models import build_gold, iter_gold_tables
from edgar_warehouse.silver_store import SilverDatabase


EXPECTED_GOLD_TABLE_NAMES = {
    "dim_company", "dim_form", "dim_date", "dim_filing", "fact_filing_activity",
    "dim_party", "dim_security", "dim_ownership_txn_type", "dim_geography",
    "dim_disclosure_category", "dim_private_fund", "fact_ownership_transaction",
    "fact_ownership_holding_snapshot", "fact_adv_office", "fact_adv_disclosure",
    "fact_adv_private_fund", "sec_financial_fact", "sec_thirteenf_holding",
    "sec_financial_derived", "fact_earnings_release", "fact_guidance",
    "fact_executive_record", "fact_accounting_flag", "sec_subsidiary_evidence",
    "sec_auditor_report_evidence", "sec_employment_event", "sec_adv_firm_roster",
    "sec_adv_private_fund",
}


def _empty_silver_db(tmp_path) -> SilverDatabase:
    """A real, schema-backed SilverDatabase (via the production DDL) with no
    rows -- not a hand-rolled stub. Every builder should run against it and
    return its declared empty-schema table."""
    return SilverDatabase(str(tmp_path / "silver.duckdb"))


def test_iter_gold_tables_produces_the_full_expected_table_set(tmp_path) -> None:
    """Guards against the streaming refactor silently dropping, renaming, or
    reordering a builder -- pinned against a hardcoded name set independent
    of build_gold()'s own implementation, so this can't pass by construction
    the way an iter_gold_tables()-vs-build_gold() comparison alone would."""
    db = _empty_silver_db(tmp_path)
    try:
        names = [name for name, _ in iter_gold_tables(db)]
    finally:
        db.close()

    assert set(names) == EXPECTED_GOLD_TABLE_NAMES
    assert len(names) == len(set(names)), "duplicate table name in iter_gold_tables()"


def test_iter_gold_tables_matches_build_gold_with_real_rows(tmp_path) -> None:
    """iter_gold_tables() must be a drop-in streaming equivalent of
    build_gold(): same table names, same per-table schema and row counts,
    exercised against a non-empty silver database (not just the degenerate
    empty-schema case, which every builder returns identically regardless of
    how it's invoked)."""
    db = _empty_silver_db(tmp_path)
    try:
        db._conn.execute(
            """
            INSERT INTO sec_company (cik, entity_name, entity_type, sic, last_sync_run_id)
            VALUES (320193, 'Apple Inc.', 'operating', '3571', 'run-1')
            """
        )
        streamed = dict(iter_gold_tables(db))
        materialized = build_gold(db)
    finally:
        db.close()

    assert set(streamed.keys()) == set(materialized.keys()) == EXPECTED_GOLD_TABLE_NAMES

    assert streamed["dim_company"].num_rows == materialized["dim_company"].num_rows == 1

    for name, streamed_table in streamed.items():
        materialized_table = materialized[name]
        assert isinstance(streamed_table, pa.Table)
        assert streamed_table.schema.equals(materialized_table.schema), name
        assert streamed_table.num_rows == materialized_table.num_rows, name


def test_iter_gold_tables_is_lazy(tmp_path) -> None:
    """Builders must not run until the generator is actually advanced to
    them -- the whole point of streaming is that a later table (e.g.
    sec_thirteenf_holding, the table that OOM'd daily_incremental in prod)
    isn't built while earlier tables are still being written out."""
    db = _empty_silver_db(tmp_path)
    try:
        with patch(
            "edgar_warehouse.serving.gold_models._build_sec_thirteenf_holding"
        ) as mock_thirteenf:
            gen = iter_gold_tables(db)
            mock_thirteenf.assert_not_called()

            # sec_thirteenf_holding is well past the first few entries in the
            # builder registry -- consuming only the first 3 must not reach it.
            list(itertools.islice(gen, 3))
            mock_thirteenf.assert_not_called()

            # Draining the rest of the generator does reach it.
            list(gen)
            mock_thirteenf.assert_called_once()
    finally:
        db.close()
