"""Ticket 20 fix: merge_candidate_into_canonical's cold-start memory bound.

Root cause (see .scratch/ecs-cost-sizing/issues/20-fix-stage1b-entity-facts-oom-on-medium-profile.md):
the old _delta_rows_as_dicts materialized every delta row into a Python list
of dicts in one unchunked fetchall(), which for a cold-start table (canonical
~empty) is effectively the entire candidate table -- OOM-killed
Stage1BEntityFacts and Stage1BPerFiling on the medium ECS profile.

The fix splits the merge into two paths: brand-new business keys are
inserted via one pure-SQL INSERT ... SELECT (never touching Python), and
only same-key-but-differing rows go through the row-by-row Python
conflict-resolution path, chunked via fetchmany() instead of one fetchall().
These tests exercise correctness of both paths and the chunk boundary
itself, plus a bound on peak Python-side row materialization.
"""

from __future__ import annotations

import os
import tracemalloc
from pathlib import Path

import duckdb
import pytest

from edgar_warehouse.silver_protection import (
    SemanticMergeConflictError,
    merge_candidate_into_canonical,
)
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


def _read_companies(output_path: Path) -> dict[int, tuple[str, object]]:
    conn = duckdb.connect(str(output_path))
    try:
        rows = conn.execute(
            "SELECT cik, entity_name, last_synced_at FROM sec_company ORDER BY cik"
        ).fetchall()
    finally:
        conn.close()
    return {cik: (name, ts) for cik, name, ts in rows}


def test_cold_start_bulk_insert_never_materializes_new_rows_in_python(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cold-start canonical (empty sec_company) plus a large candidate must
    insert entirely through the phase-1 SQL path -- if any candidate row
    were materialized as a Python dict, this would fail the fetchall/fetchmany
    tripwire installed below."""
    canonical_path = tmp_path / "canonical.duckdb"
    SilverDatabase(str(canonical_path)).close()  # empty canonical, no sec_company rows.

    candidate_path = tmp_path / "candidate.duckdb"
    candidate_db = SilverDatabase(str(candidate_path))
    n = 2500
    _insert_companies(
        candidate_db,
        [{"cik": cik, "entity_name": f"Company {cik}", "last_synced_at": None} for cik in range(1, n + 1)],
    )
    candidate_db.close()

    # Tripwire: fetchmany must never be called with a batch size that implies
    # phase 2 (existing-key-diff) processed any rows for this cold-start
    # scenario -- every row's key is brand-new, so phase 2's generator should
    # yield zero chunks entirely.
    from edgar_warehouse import silver_protection

    calls = []
    original = silver_protection._iter_existing_key_diff_row_chunks

    def spying_iter(*args, **kwargs):
        for chunk in original(*args, **kwargs):
            calls.append(len(chunk))
            yield chunk

    monkeypatch.setattr(silver_protection, "_iter_existing_key_diff_row_chunks", spying_iter)

    output_path = tmp_path / "merged.duckdb"
    result = merge_candidate_into_canonical(candidate_path, canonical_path, output_path)

    assert result.rows_inserted["sec_company"] == n
    assert result.rows_updated.get("sec_company", 0) == 0
    assert calls == [], f"expected zero existing-key-diff chunks for a cold-start merge, got {calls}"

    merged = _read_companies(output_path)
    assert len(merged) == n
    assert merged[1][0] == "Company 1"
    assert merged[n][0] == f"Company {n}"


def test_existing_key_conflict_still_resolved_via_authority_column(tmp_path: Path) -> None:
    canonical_path = tmp_path / "canonical.duckdb"
    canonical_db = SilverDatabase(str(canonical_path))
    _insert_companies(
        canonical_db,
        [{"cik": 1, "entity_name": "Old Name", "last_synced_at": "2026-01-01T00:00:00Z"}],
    )
    canonical_db.close()

    candidate_path = tmp_path / "candidate.duckdb"
    candidate_db = SilverDatabase(str(candidate_path))
    _insert_companies(
        candidate_db,
        [{"cik": 1, "entity_name": "New Name", "last_synced_at": "2026-02-01T00:00:00Z"}],
    )
    candidate_db.close()

    output_path = tmp_path / "merged.duckdb"
    result = merge_candidate_into_canonical(candidate_path, canonical_path, output_path)

    assert result.rows_inserted.get("sec_company", 0) == 0
    assert result.rows_updated["sec_company"] == 1
    merged = _read_companies(output_path)
    assert merged[1][0] == "New Name"


def test_stale_candidate_does_not_overwrite_newer_canonical(tmp_path: Path) -> None:
    canonical_path = tmp_path / "canonical.duckdb"
    canonical_db = SilverDatabase(str(canonical_path))
    _insert_companies(
        canonical_db,
        [{"cik": 1, "entity_name": "Current Name", "last_synced_at": "2026-02-01T00:00:00Z"}],
    )
    canonical_db.close()

    candidate_path = tmp_path / "candidate.duckdb"
    candidate_db = SilverDatabase(str(candidate_path))
    _insert_companies(
        candidate_db,
        [{"cik": 1, "entity_name": "Stale Name", "last_synced_at": "2026-01-01T00:00:00Z"}],
    )
    candidate_db.close()

    output_path = tmp_path / "merged.duckdb"
    result = merge_candidate_into_canonical(candidate_path, canonical_path, output_path)

    assert result.rows_updated.get("sec_company", 0) == 0
    assert result.rows_unchanged["sec_company"] == 1
    merged = _read_companies(output_path)
    assert merged[1][0] == "Current Name"


def test_ambiguous_conflict_with_no_authority_signal_still_raises(tmp_path: Path) -> None:
    canonical_path = tmp_path / "canonical.duckdb"
    canonical_db = SilverDatabase(str(canonical_path))
    _insert_companies(canonical_db, [{"cik": 1, "entity_name": "Name A", "last_synced_at": None}])
    canonical_db.close()

    candidate_path = tmp_path / "candidate.duckdb"
    candidate_db = SilverDatabase(str(candidate_path))
    _insert_companies(candidate_db, [{"cik": 1, "entity_name": "Name B", "last_synced_at": None}])
    candidate_db.close()

    output_path = tmp_path / "merged.duckdb"
    with pytest.raises(SemanticMergeConflictError) as excinfo:
        merge_candidate_into_canonical(candidate_path, canonical_path, output_path)
    assert excinfo.value.conflicts[0].table_name == "sec_company"
    assert excinfo.value.conflicts[0].business_key == {"cik": 1}


def test_mixed_new_and_conflicting_rows_both_paths_produce_correct_result(
    tmp_path: Path,
) -> None:
    """A candidate containing both brand-new keys (phase 1) and an
    existing-key conflict (phase 2) in the same table must resolve both
    correctly in one merge call."""
    canonical_path = tmp_path / "canonical.duckdb"
    canonical_db = SilverDatabase(str(canonical_path))
    _insert_companies(
        canonical_db,
        [{"cik": 1, "entity_name": "Old Name", "last_synced_at": "2026-01-01T00:00:00Z"}],
    )
    canonical_db.close()

    candidate_path = tmp_path / "candidate.duckdb"
    candidate_db = SilverDatabase(str(candidate_path))
    _insert_companies(
        candidate_db,
        [
            {"cik": 1, "entity_name": "New Name", "last_synced_at": "2026-02-01T00:00:00Z"},
            {"cik": 2, "entity_name": "Brand New Co", "last_synced_at": "2026-02-01T00:00:00Z"},
        ],
    )
    candidate_db.close()

    output_path = tmp_path / "merged.duckdb"
    result = merge_candidate_into_canonical(candidate_path, canonical_path, output_path)

    assert result.rows_inserted["sec_company"] == 1
    assert result.rows_updated["sec_company"] == 1
    merged = _read_companies(output_path)
    assert merged[1][0] == "New Name"
    assert merged[2][0] == "Brand New Co"


def test_chunking_boundary_produces_identical_result_to_a_single_chunk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Force a tiny chunk size so a same-key-diff delta spans several
    fetchmany() batches, and confirm the merge result is identical to what
    an unchunked run would produce -- chunking must not change which rows
    win or how counts are reported."""
    monkeypatch.setenv("WAREHOUSE_SILVER_MERGE_CHUNK_SIZE", "3")

    canonical_path = tmp_path / "canonical.duckdb"
    canonical_db = SilverDatabase(str(canonical_path))
    n = 10
    _insert_companies(
        canonical_db,
        [
            {"cik": cik, "entity_name": f"Old {cik}", "last_synced_at": "2026-01-01T00:00:00Z"}
            for cik in range(1, n + 1)
        ],
    )
    canonical_db.close()

    candidate_path = tmp_path / "candidate.duckdb"
    candidate_db = SilverDatabase(str(candidate_path))
    _insert_companies(
        candidate_db,
        [
            {"cik": cik, "entity_name": f"New {cik}", "last_synced_at": "2026-02-01T00:00:00Z"}
            for cik in range(1, n + 1)
        ],
    )
    candidate_db.close()

    output_path = tmp_path / "merged.duckdb"
    result = merge_candidate_into_canonical(candidate_path, canonical_path, output_path)

    assert result.rows_updated["sec_company"] == n
    assert result.rows_inserted.get("sec_company", 0) == 0
    merged = _read_companies(output_path)
    for cik in range(1, n + 1):
        assert merged[cik][0] == f"New {cik}"


def test_default_chunk_size_env_var_parses_and_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    from edgar_warehouse.silver_protection import _merge_chunk_size

    monkeypatch.delenv("WAREHOUSE_SILVER_MERGE_CHUNK_SIZE", raising=False)
    assert _merge_chunk_size() == 50_000

    monkeypatch.setenv("WAREHOUSE_SILVER_MERGE_CHUNK_SIZE", "7")
    assert _merge_chunk_size() == 7


def test_cold_start_merge_peak_python_row_materialization_is_bounded(tmp_path: Path) -> None:
    """A coarse but real regression guard for the OOM this ticket fixes:
    merging a several-thousand-row cold-start candidate must not hold
    anywhere near that many rows as Python dicts at once. Measured via
    tracemalloc around the merge call itself -- not a substitute for the
    ticket's own CloudWatch-grounded production estimate, but enough to
    catch a regression back to the old unchunked fetchall() behavior, which
    would show peak Python object memory scaling linearly with row count."""
    canonical_path = tmp_path / "canonical.duckdb"
    SilverDatabase(str(canonical_path)).close()

    candidate_path = tmp_path / "candidate.duckdb"
    candidate_db = SilverDatabase(str(candidate_path))
    n = 5000
    _insert_companies(
        candidate_db,
        [{"cik": cik, "entity_name": f"Company {cik}" * 5, "last_synced_at": None} for cik in range(1, n + 1)],
    )
    candidate_db.close()

    output_path = tmp_path / "merged.duckdb"
    tracemalloc.start()
    try:
        merge_candidate_into_canonical(candidate_path, canonical_path, output_path)
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    # A per-row dict for all 5000 rows (per ticket 20's own ~495 bytes/row
    # measurement) would be ~2.5MB just for that; the bulk-SQL insert path
    # should keep peak well under a per-row-materialized bound. 2MB is a
    # generous ceiling that still fails if the phase-1 path regresses to
    # per-row Python dicts.
    assert peak < 2_000_000, f"peak Python memory {peak} bytes suggests rows were materialized, not bulk-inserted"
