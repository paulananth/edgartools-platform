"""only_tables scoping for merge_candidate_into_canonical.

Root cause (found live 2026-08-22, seed-universe OOM investigation):
merge_candidate_into_canonical iterates every table in
PROTECTED_TABLE_REGISTRY present in the candidate file -- unconditionally,
regardless of whether the calling command actually wrote to it. A command
like seed-universe, whose entire write footprint is sec_company_ticker and
sec_company_sync_state, still drags every other table (including
sec_thirteenf_holding's 6.8M rows) through a full compare/merge pass,
because its local candidate file is the full hydrated canonical copy, not
something scoped to what it actually changed.

only_tables lets a caller that knows exactly which tables it touched skip
merge work for everything else -- the skipped tables' content in the output
is left exactly as canonical's own copy already had it (merge_candidate_
into_canonical already starts output_path as a full copy of canonical_path,
so "don't touch it" is correct by construction, not just an optimization).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from edgar_warehouse.silver_protection import merge_candidate_into_canonical
from edgar_warehouse.silver_store import SilverDatabase


def _insert_companies(db: SilverDatabase, rows: list[dict]) -> None:
    for row in rows:
        db._conn.execute(
            """
            INSERT INTO sec_company (cik, entity_name, last_synced_at)
            VALUES (?, ?, ?)
            """,
            [row["cik"], row["entity_name"], row.get("last_synced_at")],
        )


def _insert_tickers(db: SilverDatabase, rows: list[dict]) -> None:
    for row in rows:
        db._conn.execute(
            """
            INSERT INTO sec_company_ticker
                (cik, ticker, exchange, source_name, source_rank, last_sync_run_id, last_synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                row["cik"],
                row["ticker"],
                row.get("exchange"),
                row.get("source_name", "company_tickers_exchange"),
                row.get("source_rank", 1),
                row.get("last_sync_run_id", "test-run"),
                row.get("last_synced_at"),
            ],
        )


def _read_companies(db_path: Path) -> dict[int, str]:
    conn = duckdb.connect(str(db_path))
    try:
        rows = conn.execute("SELECT cik, entity_name FROM sec_company ORDER BY cik").fetchall()
    finally:
        conn.close()
    return {cik: name for cik, name in rows}


def _read_tickers(db_path: Path) -> dict[int, str]:
    conn = duckdb.connect(str(db_path))
    try:
        rows = conn.execute("SELECT cik, ticker FROM sec_company_ticker ORDER BY cik").fetchall()
    finally:
        conn.close()
    return {cik: ticker for cik, ticker in rows}


def test_only_tables_skips_merge_work_for_tables_outside_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reproduces the actual bug: a candidate that touched only tickers must
    not trigger any merge work for sec_company, even though sec_company is
    present (unchanged) in both files -- without this fix, the merge loop
    processes it anyway."""
    canonical_path = tmp_path / "canonical.duckdb"
    canonical_db = SilverDatabase(str(canonical_path))
    _insert_companies(canonical_db, [{"cik": 1, "entity_name": "Acme Corp", "last_synced_at": None}])
    canonical_db.close()

    candidate_path = tmp_path / "candidate.duckdb"
    candidate_db = SilverDatabase(str(candidate_path))
    # Candidate is a full hydrated copy of canonical (same sec_company row,
    # untouched) plus a genuinely new ticker row -- exactly seed-universe's shape.
    _insert_companies(candidate_db, [{"cik": 1, "entity_name": "Acme Corp", "last_synced_at": None}])
    _insert_tickers(candidate_db, [{"cik": 1, "ticker": "ACME", "exchange": "NASDAQ"}])
    candidate_db.close()

    from edgar_warehouse import silver_protection

    started_tables: list[str] = []
    original = silver_protection._emit_table_merge_started_event

    def spying_start(table_name: str) -> None:
        started_tables.append(table_name)
        original(table_name)

    monkeypatch.setattr(silver_protection, "_emit_table_merge_started_event", spying_start)

    output_path = tmp_path / "merged.duckdb"
    result = merge_candidate_into_canonical(
        candidate_path, canonical_path, output_path, only_tables=frozenset({"sec_company_ticker"})
    )

    assert "sec_company" not in started_tables, (
        "sec_company was outside only_tables scope but merge work started for it anyway"
    )
    assert "sec_company_ticker" in started_tables
    assert "sec_company" not in result.tables_merged
    assert "sec_company_ticker" in result.tables_merged

    # Correctness: the in-scope table's new row landed; the out-of-scope
    # table is untouched (still exactly canonical's own content).
    assert _read_tickers(output_path) == {1: "ACME"}
    assert _read_companies(output_path) == {1: "Acme Corp"}


def test_only_tables_none_processes_every_table_unchanged_default(tmp_path: Path) -> None:
    """Backward-compat: omitting only_tables (the default) must behave
    exactly as before -- every table in the candidate gets merged."""
    canonical_path = tmp_path / "canonical.duckdb"
    SilverDatabase(str(canonical_path)).close()

    candidate_path = tmp_path / "candidate.duckdb"
    candidate_db = SilverDatabase(str(candidate_path))
    _insert_companies(candidate_db, [{"cik": 1, "entity_name": "Acme Corp", "last_synced_at": None}])
    _insert_tickers(candidate_db, [{"cik": 1, "ticker": "ACME", "exchange": "NASDAQ"}])
    candidate_db.close()

    output_path = tmp_path / "merged.duckdb"
    result = merge_candidate_into_canonical(candidate_path, canonical_path, output_path)

    assert "sec_company" in result.tables_merged
    assert "sec_company_ticker" in result.tables_merged


def test_only_tables_empty_set_processes_no_tables(tmp_path: Path) -> None:
    """An explicit empty scope (e.g. the fingerprint diff found zero real
    changes) must be a genuine no-op merge, not fall back to full scope."""
    canonical_path = tmp_path / "canonical.duckdb"
    canonical_db = SilverDatabase(str(canonical_path))
    _insert_companies(canonical_db, [{"cik": 1, "entity_name": "Acme Corp", "last_synced_at": None}])
    canonical_db.close()

    candidate_path = tmp_path / "candidate.duckdb"
    candidate_db = SilverDatabase(str(candidate_path))
    _insert_companies(candidate_db, [{"cik": 1, "entity_name": "Different Name", "last_synced_at": None}])
    candidate_db.close()

    output_path = tmp_path / "merged.duckdb"
    result = merge_candidate_into_canonical(
        candidate_path, canonical_path, output_path, only_tables=frozenset()
    )

    assert result.tables_merged == ()
    # Untouched -- output must retain canonical's own content, not candidate's.
    assert _read_companies(output_path) == {1: "Acme Corp"}
