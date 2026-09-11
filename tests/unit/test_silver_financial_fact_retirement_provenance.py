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
be flagged as a conflict. But "flagged as a conflict" no longer means
"permanently ambiguous, always aborts": fundamentals-daily-integration map
Ticket 01 resolved the previously-open design question below by giving
sec_financial_fact/sec_accounting_flag a second, narrower tiebreak column,
retirement_state_observed_at (migration 011), consulted by _resolve_conflict
only when the primary authority_column (ingested_at) ties AND every
genuinely differing column is one of the table's declared retirement_columns
(valid_to/is_current). A genuine *value* conflict (e.g. `value` also
differs) alongside a retirement still correctly aborts as ambiguous --
proven below alongside the resolved-retirement case.
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
    """A real retirement performed by a raw UPDATE that bypasses
    retire_financial_facts_not_in_snapshot (and so never touches
    retirement_state_observed_at) must still raise
    SemanticMergeConflictError -- proves valid_to/is_current were NOT
    accidentally exempted alongside valid_from, and that Ticket 01's
    retirement_authority_column fallback only fires when the sanctioned
    write path actually advances it, not for any arbitrary same-key
    difference on those two columns.
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


def test_genuine_retirement_via_retire_method_now_publishes(tmp_path: Path) -> None:
    """Ticket 01 (fundamentals-daily-integration map), closing CLAUDE.md's
    'sec_financial_fact retirement publish-conflict' 5-whys Part B: a real
    retirement performed through retire_financial_facts_not_in_snapshot (the
    sanctioned write path, which now advances retirement_state_observed_at
    alongside is_current/valid_to) must publish cleanly instead of
    permanently aborting on the ingested_at tie.
    """
    canonical_path = tmp_path / "canonical.duckdb"
    canonical_db = SilverDatabase(str(canonical_path))
    canonical_db._conn.execute(
        f"""
        INSERT INTO sec_financial_fact ({_FACT_INSERT_COLUMNS})
        VALUES (320193, '0000320193-24-000123', 2024, 'FY', '2024-09-28', '2023-09-30',
                '10-K', 'us-gaap/Revenues', 391035000000, 'USD', 0, 'consolidated', 'test',
                '2026-01-01 00:00:00+00')
        """
    )
    canonical_db.close()

    candidate_path = tmp_path / "candidate.duckdb"
    import shutil

    shutil.copy(canonical_path, candidate_path)
    candidate_db = SilverDatabase(str(candidate_path))
    # The fact is absent from this fresh snapshot -- retire_financial_facts_
    # not_in_snapshot's real production call shape (empty fact_keys retires
    # everything current for the CIK).
    candidate_db.retire_financial_facts_not_in_snapshot(cik=320193, fact_keys=[], sync_run_id="test-run")
    candidate_db.close()

    output_path = tmp_path / "merged.duckdb"
    # Must not raise -- before this fix, this exact shape aborted the whole
    # publish with a "434805 ambiguous same-key conflict(s)"-style error.
    result = merge_candidate_into_canonical(candidate_path, canonical_path, output_path)

    assert result.rows_updated.get("sec_financial_fact", 0) == 1

    conn = duckdb.connect(str(output_path))
    try:
        row = conn.execute(
            "SELECT is_current, valid_to FROM sec_financial_fact "
            "WHERE accession_number = '0000320193-24-000123'"
        ).fetchone()
    finally:
        conn.close()
    assert row[0] is False  # the retirement won, not canonical's stale is_current=TRUE
    assert row[1] is not None


def test_genuine_value_conflict_alongside_retirement_still_blocks(tmp_path: Path) -> None:
    """A retirement is not a free pass for an unrelated content conflict:
    if `value` also genuinely differs between canonical and candidate (not
    just retirement state), the differing-columns set is no longer a subset
    of retirement_columns, so this must still abort as ambiguous even
    though retirement_state_observed_at correctly advanced.
    """
    canonical_path = tmp_path / "canonical.duckdb"
    canonical_db = SilverDatabase(str(canonical_path))
    canonical_db._conn.execute(
        f"""
        INSERT INTO sec_financial_fact ({_FACT_INSERT_COLUMNS})
        VALUES (320193, '0000320193-24-000123', 2024, 'FY', '2024-09-28', '2023-09-30',
                '10-K', 'us-gaap/Revenues', 391035000000, 'USD', 0, 'consolidated', 'test',
                '2026-01-01 00:00:00+00')
        """
    )
    canonical_db.close()

    candidate_path = tmp_path / "candidate.duckdb"
    import shutil

    shutil.copy(canonical_path, candidate_path)
    candidate_db = SilverDatabase(str(candidate_path))
    # A genuine value correction on top of the retirement -- differing now
    # includes `value`, not just valid_to/is_current.
    candidate_db._conn.execute(
        "UPDATE sec_financial_fact SET value = 999999999 WHERE cik = 320193"
    )
    candidate_db.retire_financial_facts_not_in_snapshot(cik=320193, fact_keys=[], sync_run_id="test-run")
    candidate_db.close()

    output_path = tmp_path / "merged.duckdb"
    with pytest.raises(SemanticMergeConflictError) as excinfo:
        merge_candidate_into_canonical(candidate_path, canonical_path, output_path)

    assert "sec_financial_fact" in str(excinfo.value)
    assert "value" in str(excinfo.value)


class TestResolveConflictRetirementFallback:
    """Direct unit coverage of _resolve_conflict's retirement_authority_column
    fallback (Ticket 01), isolated from the full merge_candidate_into_canonical
    seam the tests above exercise."""

    def test_falls_back_to_retirement_authority_column_on_authority_tie(self) -> None:
        from edgar_warehouse.silver_protection import PROTECTED_TABLE_REGISTRY, _resolve_conflict

        policy = PROTECTED_TABLE_REGISTRY["sec_financial_fact"]
        canonical_row = {"ingested_at": 100, "is_current": True, "valid_to": None,
                          "retirement_state_observed_at": 1}
        candidate_row = {"ingested_at": 100, "is_current": False, "valid_to": 200,
                          "retirement_state_observed_at": 2}

        winner = _resolve_conflict(policy, canonical_row, candidate_row,
                                    differing=("is_current", "valid_to"))

        assert winner == "candidate"

    def test_stays_ambiguous_when_differing_includes_non_retirement_column(self) -> None:
        from edgar_warehouse.silver_protection import PROTECTED_TABLE_REGISTRY, _resolve_conflict

        policy = PROTECTED_TABLE_REGISTRY["sec_financial_fact"]
        canonical_row = {"ingested_at": 100, "is_current": True, "valid_to": None,
                          "value": 1.0, "retirement_state_observed_at": 1}
        candidate_row = {"ingested_at": 100, "is_current": False, "valid_to": 200,
                          "value": 2.0, "retirement_state_observed_at": 2}

        winner = _resolve_conflict(policy, canonical_row, candidate_row,
                                    differing=("is_current", "valid_to", "value"))

        assert winner is None

    def test_stays_ambiguous_when_retirement_authority_column_also_ties(self) -> None:
        from edgar_warehouse.silver_protection import PROTECTED_TABLE_REGISTRY, _resolve_conflict

        policy = PROTECTED_TABLE_REGISTRY["sec_financial_fact"]
        canonical_row = {"ingested_at": 100, "is_current": True, "valid_to": None,
                          "retirement_state_observed_at": 5}
        candidate_row = {"ingested_at": 100, "is_current": False, "valid_to": 200,
                          "retirement_state_observed_at": 5}

        winner = _resolve_conflict(policy, canonical_row, candidate_row,
                                    differing=("is_current", "valid_to"))

        assert winner is None

    def test_unaffected_for_tables_without_retirement_authority_column(self) -> None:
        from edgar_warehouse.silver_protection import PROTECTED_TABLE_REGISTRY, _resolve_conflict

        policy = PROTECTED_TABLE_REGISTRY["sec_financial_derived"]
        assert policy.retirement_authority_column is None

        canonical_row = {"ingested_at": 100, "revenue": 1.0}
        candidate_row = {"ingested_at": 100, "revenue": 2.0}

        winner = _resolve_conflict(policy, canonical_row, candidate_row, differing=("revenue",))

        assert winner is None
