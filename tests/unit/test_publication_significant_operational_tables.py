"""Publication-significant EXCLUDED_OPERATIONAL_TABLES (change-propagation Ticket 31).

Root cause (found live 2026-08-24, Ticket 29's prod dry run): two independent
bugs compounded so that ``load-daily-form-index-for-date`` -- whose entire
write footprint is ``stg_daily_index_filing``/``sec_daily_index_checkpoint``,
both ``EXCLUDED_OPERATIONAL_TABLES`` -- could never publish to canonical once
canonical already existed.

1. ``compute_silver_fingerprint`` only fingerprinted ``PROTECTED_TABLE_REGISTRY``
   tables, so a command writing only these two always computed a fingerprint
   identical to hydration's and got skipped by the skip-if-unchanged
   optimization, unconditionally.
2. Deeper: even without the skip, ``merge_candidate_into_canonical``'s only
   content-copying loop iterates ``PROTECTED_TABLE_REGISTRY`` exclusively --
   ``EXCLUDED_OPERATIONAL_TABLES`` tables were never copied into the merged
   output at all, contradicting that exclusion's own documented intent ("a
   candidate is always free to overwrite them").

These tests lock in the fix for both, for exactly the two tables with live
evidence (``sec_daily_index_checkpoint``, ``stg_daily_index_filing`` --
``PUBLICATION_SIGNIFICANT_OPERATIONAL_TABLES``), while proving the fix does
not widen scope to genuine bookkeeping tables like ``pipeline_run`` (Ticket
79's own regression, ``test_skip_noop_silver_publish.py``, must keep passing
unmodified).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

from edgar_warehouse.silver_protection import (
    PUBLICATION_SIGNIFICANT_OPERATIONAL_TABLES,
    compute_silver_fingerprint,
    merge_candidate_into_canonical,
)
from edgar_warehouse.silver_store import SilverDatabase


def _checkpoint_row(business_date: str) -> dict:
    return {
        "business_date": business_date,
        "source_name": "daily_form_index",
        "source_key": f"date:{business_date}",
        "source_url": "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/form.idx",
        "expected_available_at": datetime.now(UTC),
        "first_attempt_at": datetime.now(UTC),
        "last_attempt_at": datetime.now(UTC),
        "attempt_count": 1,
        "raw_object_id": None,
        "last_sha256": None,
        "row_count": 1,
        "distinct_cik_count": 1,
        "distinct_accession_count": 1,
        "status": "succeeded",
        "error_message": None,
        "finalized_at": datetime.now(UTC),
        "last_success_at": datetime.now(UTC),
    }


def test_publication_significant_tables_are_a_narrow_subset() -> None:
    """The fix must be scoped to evidenced tables only, not blanket-widened."""
    assert PUBLICATION_SIGNIFICANT_OPERATIONAL_TABLES == frozenset(
        {"sec_daily_index_checkpoint", "stg_daily_index_filing"}
    )


def test_fingerprint_detects_a_daily_index_checkpoint_only_change(tmp_path: Path) -> None:
    """Regression for bug #1: a checkpoint-only write must change the fingerprint."""
    db_path = tmp_path / "silver.duckdb"
    SilverDatabase(str(db_path)).close()
    baseline = compute_silver_fingerprint(db_path)

    db = SilverDatabase(str(db_path))
    db.upsert_daily_index_checkpoint(_checkpoint_row("2026-08-21"))
    db.close()

    after = compute_silver_fingerprint(db_path)
    assert after != baseline
    assert after["protected"]["sec_daily_index_checkpoint"] != baseline["protected"].get(
        "sec_daily_index_checkpoint"
    )


def test_fingerprint_still_ignores_pipeline_run_only_change(tmp_path: Path) -> None:
    """Inverse of the above: genuine bookkeeping (pipeline_run) must stay excluded --
    the fix must not over-widen past the two evidenced tables."""
    db_path = tmp_path / "silver.duckdb"
    SilverDatabase(str(db_path)).close()
    baseline = compute_silver_fingerprint(db_path)

    db = SilverDatabase(str(db_path))
    db.start_pipeline_run(
        {
            "pipeline_run_id": "run-1",
            "command_name": "gold-refresh",
            "runtime_mode": "bronze_capture",
        }
    )
    db.close()

    after = compute_silver_fingerprint(db_path)
    assert after == baseline


def test_merge_copies_checkpoint_only_candidate_content_into_canonical(tmp_path: Path) -> None:
    """Regression for bug #2, at the merge seam directly: a candidate whose
    only content is a new sec_daily_index_checkpoint row must have that row
    land in the merged output -- reproduces the exact prod failure
    (tables_merged staying empty for an excluded-but-significant table)."""
    canonical_path = tmp_path / "canonical.duckdb"
    SilverDatabase(str(canonical_path)).close()

    candidate_path = tmp_path / "candidate.duckdb"
    candidate_db = SilverDatabase(str(candidate_path))
    candidate_db.upsert_daily_index_checkpoint(_checkpoint_row("2026-08-21"))
    candidate_db.close()

    output_path = tmp_path / "merged.duckdb"
    result = merge_candidate_into_canonical(candidate_path, canonical_path, output_path)

    assert "sec_daily_index_checkpoint" in result.tables_merged

    conn = duckdb.connect(str(output_path))
    try:
        row = conn.execute(
            "SELECT business_date, status FROM sec_daily_index_checkpoint"
        ).fetchall()
    finally:
        conn.close()
    assert row == [(date(2026, 8, 21), "succeeded")]


def test_merge_only_tables_scoping_still_applies_to_significant_tables(tmp_path: Path) -> None:
    """only_tables=frozenset() (the fingerprint found zero real changes) must
    still be a genuine no-op for these tables too, not a hidden bypass."""
    canonical_path = tmp_path / "canonical.duckdb"
    SilverDatabase(str(canonical_path)).close()

    candidate_path = tmp_path / "candidate.duckdb"
    candidate_db = SilverDatabase(str(candidate_path))
    candidate_db.upsert_daily_index_checkpoint(_checkpoint_row("2026-08-21"))
    candidate_db.close()

    output_path = tmp_path / "merged.duckdb"
    result = merge_candidate_into_canonical(
        candidate_path, canonical_path, output_path, only_tables=frozenset()
    )

    assert result.tables_merged == ()
    conn = duckdb.connect(str(output_path))
    try:
        count = conn.execute("SELECT COUNT(*) FROM sec_daily_index_checkpoint").fetchone()[0]
    finally:
        conn.close()
    assert count == 0


def test_merge_still_ignores_pipeline_run_content(tmp_path: Path) -> None:
    """Genuine bookkeeping tables (pipeline_run) must remain untouched by the
    merge, matching their EXCLUDED_OPERATIONAL_TABLES-but-not-significant
    classification -- output keeps canonical's own copy, not candidate's."""
    canonical_path = tmp_path / "canonical.duckdb"
    SilverDatabase(str(canonical_path)).close()

    candidate_path = tmp_path / "candidate.duckdb"
    candidate_db = SilverDatabase(str(candidate_path))
    candidate_db.start_pipeline_run(
        {
            "pipeline_run_id": "run-1",
            "command_name": "gold-refresh",
            "runtime_mode": "bronze_capture",
        }
    )
    candidate_db.close()

    output_path = tmp_path / "merged.duckdb"
    result = merge_candidate_into_canonical(candidate_path, canonical_path, output_path)

    assert "pipeline_run" not in result.tables_merged
    conn = duckdb.connect(str(output_path))
    try:
        count = conn.execute("SELECT COUNT(*) FROM pipeline_run").fetchone()[0]
    finally:
        conn.close()
    assert count == 0
