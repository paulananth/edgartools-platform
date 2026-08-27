"""Tests for sec_financial_fact/sec_accounting_flag's valid_from/is_current/
valid_to columns (Ticket 33, change-propagation map) at the silver-publish
merge seam.

Found live during this session's Ticket 46 verification run in prod: the
first-ever publish attempt since Ticket 33 shipped failed with
`SemanticMergeConflictError` ("434805 ambiguous same-key conflict(s) block
publication"), because `merge_candidate_into_canonical`'s additive schema
reconciliation (canonical learning about valid_from/valid_to/is_current for
the first time) backfilled every pre-existing canonical row with a bare
NULL, while the candidate's own local schema migration
(_add_company_facts_retirement_columns) had already backfilled real values
-- a false conflict on every single row.

Fixed two ways:
1. The additive ALTER TABLE now reuses the candidate's own declared DEFAULT
   (e.g. `is_current BOOLEAN DEFAULT TRUE`) instead of leaving the column
   NULL -- see `_column_defaults`/the additive loop in silver_protection.py.
2. `valid_from` specifically still needed a `provenance_columns` exemption
   on top of that: DEFAULT NOW() evaluates to a genuinely different literal
   each time it runs, so no shared default expression can make canonical's
   backfill match the candidate's. Safe because valid_from is set once at
   first capture and never touched again by design (mirrors mdm_entity_id's
   existing exemption in this same registry).

Deliberately does NOT exempt valid_to/is_current -- a genuine retirement
conflict (candidate retires a row canonical still shows current) must still
be flagged. See CLAUDE.md's "sec_financial_fact retirement publish-conflict"
5-whys: how such a conflict *should* resolve is a separate, still-open
design question this fix does not attempt to answer.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from edgar_warehouse.silver_protection import (
    SemanticMergeConflictError,
    merge_candidate_into_canonical,
)
from edgar_warehouse.silver_store import SilverDatabase

_FACT_INSERT_COLUMNS = (
    "cik, accession_number, fiscal_year, fiscal_period, period_end, period_start, "
    "form_type, concept, value, unit, decimals, segment, parser_version, ingested_at"
)

# Pre-Ticket-33 sec_financial_fact -- no valid_from/valid_to/is_current at all,
# the exact real-prod shape this test builds canonical from.
_PRE_RETIREMENT_FACT_DDL = """
CREATE TABLE sec_financial_fact (
    cik                 BIGINT NOT NULL,
    accession_number    TEXT NOT NULL,
    fiscal_year         INTEGER NOT NULL,
    fiscal_period       TEXT NOT NULL,
    period_end          DATE NOT NULL,
    period_start        DATE NOT NULL,
    form_type           TEXT NOT NULL,
    concept             TEXT NOT NULL,
    value               DOUBLE,
    unit                TEXT,
    decimals            INTEGER,
    segment             TEXT NOT NULL DEFAULT 'consolidated',
    parser_version      TEXT,
    ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (cik, accession_number, concept, fiscal_period, segment, period_end, period_start)
);
"""


def _insert_fact(conn: duckdb.DuckDBPyConnection, *, ingested_at: str) -> None:
    conn.execute(
        f"""
        INSERT INTO sec_financial_fact ({_FACT_INSERT_COLUMNS})
        VALUES (320193, '0000320193-24-000123', 2024, 'FY', '2024-09-28', '2023-09-30',
                '10-K', 'us-gaap/Revenues', 391035000000, 'USD', 0, 'consolidated', 'test', ?)
        """,
        [ingested_at],
    )


def test_first_publish_after_ticket_33_backfills_without_false_conflict(tmp_path: Path) -> None:
    """The exact regression: canonical predates Ticket 33 entirely, candidate
    already ran the local migration. Must merge cleanly (not raise
    SemanticMergeConflictError), and the merged row must carry real
    valid_from/is_current values, not NULL.
    """
    canonical_path = tmp_path / "canonical.duckdb"
    conn = duckdb.connect(str(canonical_path))
    conn.execute(_PRE_RETIREMENT_FACT_DDL)
    _insert_fact(conn, ingested_at="2026-01-01 00:00:00+00")
    conn.close()

    candidate_path = tmp_path / "candidate.duckdb"
    import shutil

    shutil.copy(canonical_path, candidate_path)
    candidate_db = SilverDatabase(str(candidate_path))  # runs migration 010 locally
    candidate_db.close()

    output_path = tmp_path / "merged.duckdb"
    result = merge_candidate_into_canonical(candidate_path, canonical_path, output_path)

    assert result.rows_updated.get("sec_financial_fact", 0) == 0
    assert result.rows_unchanged.get("sec_financial_fact", 0) == 1

    conn = duckdb.connect(str(output_path))
    try:
        row = conn.execute(
            "SELECT value, valid_from, valid_to, is_current FROM sec_financial_fact "
            "WHERE accession_number = '0000320193-24-000123'"
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == 391035000000.0
    assert row[1] is not None  # valid_from backfilled, not NULL
    assert row[2] is None  # valid_to correctly stays NULL (not retired)
    assert row[3] is True  # is_current backfilled to TRUE, not NULL


def test_valid_from_only_difference_does_not_block_or_get_copied(tmp_path: Path) -> None:
    """Two independently-backfilled valid_from timestamps for the same
    already-migrated row (e.g. two different tasks each ran the local
    migration once) must not conflict, and canonical's original value must
    win -- valid_from is write-once, a later task's own backfill timestamp
    must never overwrite it.
    """
    canonical_path = tmp_path / "canonical.duckdb"
    canonical_db = SilverDatabase(str(canonical_path))
    canonical_db._conn.execute(
        f"""
        INSERT INTO sec_financial_fact
            ({_FACT_INSERT_COLUMNS}, valid_from, valid_to, is_current)
        VALUES (320193, '0000320193-24-000123', 2024, 'FY', '2024-09-28', '2023-09-30',
                '10-K', 'us-gaap/Revenues', 391035000000, 'USD', 0, 'consolidated', 'test',
                '2026-01-01 00:00:00+00', '2026-06-01 00:00:00+00', NULL, TRUE)
        """
    )
    canonical_db.close()

    candidate_path = tmp_path / "candidate.duckdb"
    candidate_db = SilverDatabase(str(candidate_path))
    candidate_db._conn.execute(
        f"""
        INSERT INTO sec_financial_fact
            ({_FACT_INSERT_COLUMNS}, valid_from, valid_to, is_current)
        VALUES (320193, '0000320193-24-000123', 2024, 'FY', '2024-09-28', '2023-09-30',
                '10-K', 'us-gaap/Revenues', 391035000000, 'USD', 0, 'consolidated', 'test',
                '2026-01-01 00:00:00+00', '2026-08-27 00:00:00+00', NULL, TRUE)
        """
    )
    candidate_db.close()

    output_path = tmp_path / "merged.duckdb"
    result = merge_candidate_into_canonical(candidate_path, canonical_path, output_path)

    assert result.rows_updated.get("sec_financial_fact", 0) == 0
    assert result.rows_unchanged.get("sec_financial_fact", 0) == 1

    conn = duckdb.connect(str(output_path))
    try:
        row = conn.execute(
            "SELECT valid_from = TIMESTAMPTZ '2026-06-01 00:00:00+00' FROM sec_financial_fact"
        ).fetchone()
    finally:
        conn.close()
    assert row[0] is True  # canonical's original value, unchanged -- not candidate's


def test_genuine_retirement_conflict_still_blocks_publication(tmp_path: Path) -> None:
    """Deliberately NOT fixed by this change: a real retirement (candidate
    sets is_current=FALSE/valid_to, canonical still shows the row current)
    must still raise SemanticMergeConflictError. Proves valid_to/is_current
    were NOT accidentally exempted alongside valid_from -- how this should
    actually resolve is a separate, open design question (CLAUDE.md).
    """
    canonical_path = tmp_path / "canonical.duckdb"
    canonical_db = SilverDatabase(str(canonical_path))
    canonical_db._conn.execute(
        f"""
        INSERT INTO sec_financial_fact
            ({_FACT_INSERT_COLUMNS}, valid_from, valid_to, is_current)
        VALUES (320193, '0000320193-24-000123', 2024, 'FY', '2024-09-28', '2023-09-30',
                '10-K', 'us-gaap/Revenues', 391035000000, 'USD', 0, 'consolidated', 'test',
                '2026-01-01 00:00:00+00', '2026-01-01 00:00:00+00', NULL, TRUE)
        """
    )
    canonical_db.close()

    candidate_path = tmp_path / "candidate.duckdb"
    import shutil

    shutil.copy(canonical_path, candidate_path)
    candidate_db = SilverDatabase(str(candidate_path))
    candidate_db._conn.execute(
        "UPDATE sec_financial_fact SET is_current = FALSE, valid_to = '2026-02-01 00:00:00+00' "
        "WHERE cik = 320193"
    )
    candidate_db.close()

    output_path = tmp_path / "merged.duckdb"
    with pytest.raises(SemanticMergeConflictError) as excinfo:
        merge_candidate_into_canonical(candidate_path, canonical_path, output_path)

    assert "sec_financial_fact" in str(excinfo.value)
    assert "is_current" in str(excinfo.value) or "valid_to" in str(excinfo.value)
