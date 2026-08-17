"""Tests for the mdm_entity_id column added by the mdm-ahead-of-silver map.

Two things this covers, both found during implementation (not caught by any
of the map's 5 resolved wayfinder tickets):

1. Schema evolution: a pre-existing silver.duckdb (built before this change)
   gains `mdm_entity_id` on its next open, via migration
   `009_mdm_entity_id_columns`.
2. The two-phase design (parse writes NULL, an independent sweep backfills
   later -- mdm-ahead-of-silver map, tickets 02/05) means a later window's
   re-publish of an already-resolved row re-presents the stale parse-time
   NULL against canonical's already-backfilled value. Without excluding
   mdm_entity_id from `PROTECTED_TABLE_REGISTRY`'s comparable columns (via
   `provenance_columns`), this either hard-aborts the merge (tables with no
   `authority_column`, e.g. sec_adv_filing) or silently regresses the
   backfilled value back to NULL (tables with one, e.g. sec_company, whose
   `_update_row` previously overwrote every non-key column from the
   candidate unconditionally).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from edgar_warehouse.silver_protection import merge_candidate_into_canonical
from edgar_warehouse.silver_store import SilverDatabase

_MDM_ENTITY_ID_TABLES = (
    "sec_company",
    "sec_adv_filing",
    "sec_ownership_reporting_owner",
    "sec_adv_private_fund",
    "sec_ownership_non_derivative_txn",
    "sec_ownership_derivative_txn",
)


def test_fresh_db_has_mdm_entity_id_on_all_six_tables(tmp_path: Path) -> None:
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        for table in _MDM_ENTITY_ID_TABLES:
            columns = [row[0] for row in db._conn.execute(f"DESCRIBE {table}").fetchall()]
            assert "mdm_entity_id" in columns, f"{table} missing mdm_entity_id: {columns}"
    finally:
        db.close()


def test_pre_existing_table_gains_mdm_entity_id_via_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "silver.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute(
        "CREATE TABLE sec_company (cik BIGINT PRIMARY KEY, entity_name TEXT)"
    )
    conn.close()

    db = SilverDatabase(str(db_path))
    try:
        columns = [row[0] for row in db._conn.execute("DESCRIBE sec_company").fetchall()]
        assert "mdm_entity_id" in columns
        applied = db._conn.execute(
            "SELECT 1 FROM schema_migration WHERE migration_name = '009_mdm_entity_id_columns'"
        ).fetchone()
        assert applied is not None
    finally:
        db.close()


def _insert_company(db: SilverDatabase, *, entity_name: str, last_synced_at: str, mdm_entity_id) -> None:
    db._conn.execute(
        "INSERT INTO sec_company (cik, entity_name, last_synced_at, mdm_entity_id) "
        "VALUES (320193, ?, ?, ?)",
        [entity_name, last_synced_at, mdm_entity_id],
    )


def test_mdm_entity_id_only_difference_does_not_block_or_regress_sec_company(tmp_path: Path) -> None:
    """sec_company has an authority_column -- confirm an mdm_entity_id-only
    diff is invisible to comparable-column conflict detection entirely (not
    just resolved via the authority tiebreak)."""
    canonical_path = tmp_path / "canonical.duckdb"
    canonical_db = SilverDatabase(str(canonical_path))
    _insert_company(
        canonical_db,
        entity_name="Apple Inc",
        last_synced_at="2026-01-01",
        mdm_entity_id="entity-abc-123",
    )
    canonical_db.close()

    candidate_path = tmp_path / "candidate.duckdb"
    candidate_db = SilverDatabase(str(candidate_path))
    _insert_company(
        candidate_db,
        entity_name="Apple Inc",
        last_synced_at="2026-02-01",  # newer -- would win any authority tiebreak
        mdm_entity_id=None,  # candidate doesn't know the backfilled value yet
    )
    candidate_db.close()

    output_path = tmp_path / "merged.duckdb"
    result = merge_candidate_into_canonical(candidate_path, canonical_path, output_path)

    assert result.rows_updated.get("sec_company", 0) == 0
    assert result.rows_unchanged.get("sec_company", 0) == 1

    conn = duckdb.connect(str(output_path))
    try:
        row = conn.execute(
            "SELECT entity_name, mdm_entity_id FROM sec_company WHERE cik = 320193"
        ).fetchone()
    finally:
        conn.close()
    assert row == ("Apple Inc", "entity-abc-123")


def test_genuine_conflict_resolves_normally_without_regressing_mdm_entity_id(tmp_path: Path) -> None:
    """A real content correction that wins the authority-column tiebreak
    must still take effect -- but must not drag the candidate's NULL
    mdm_entity_id along and silently un-resolve an already-backfilled row."""
    canonical_path = tmp_path / "canonical.duckdb"
    canonical_db = SilverDatabase(str(canonical_path))
    _insert_company(
        canonical_db,
        entity_name="Apple Inc (OLD NAME)",
        last_synced_at="2026-01-01",
        mdm_entity_id="entity-abc-123",
    )
    canonical_db.close()

    candidate_path = tmp_path / "candidate.duckdb"
    candidate_db = SilverDatabase(str(candidate_path))
    _insert_company(
        candidate_db,
        entity_name="Apple Inc",  # a real correction
        last_synced_at="2026-02-01",  # newer -- wins the authority tiebreak
        mdm_entity_id=None,  # this window doesn't know the backfilled value
    )
    candidate_db.close()

    output_path = tmp_path / "merged.duckdb"
    result = merge_candidate_into_canonical(candidate_path, canonical_path, output_path)

    assert result.rows_updated.get("sec_company", 0) == 1

    conn = duckdb.connect(str(output_path))
    try:
        row = conn.execute(
            "SELECT entity_name, mdm_entity_id FROM sec_company WHERE cik = 320193"
        ).fetchone()
    finally:
        conn.close()
    assert row == ("Apple Inc", "entity-abc-123")


def test_mdm_entity_id_only_difference_does_not_block_table_without_authority_column(
    tmp_path: Path,
) -> None:
    """sec_adv_filing has no authority_column -- any comparable-column
    difference would normally hard-abort the whole merge
    (SemanticMergeConflictError). Confirm an mdm_entity_id-only diff is
    excluded from comparable columns here too."""
    canonical_path = tmp_path / "canonical.duckdb"
    canonical_db = SilverDatabase(str(canonical_path))
    canonical_db._conn.execute(
        "INSERT INTO sec_adv_filing (accession_number, cik, adviser_name, mdm_entity_id) "
        "VALUES ('0001-25-000001', 999, 'Acme Advisers', 'entity-adv-999')"
    )
    canonical_db.close()

    candidate_path = tmp_path / "candidate.duckdb"
    candidate_db = SilverDatabase(str(candidate_path))
    candidate_db._conn.execute(
        "INSERT INTO sec_adv_filing (accession_number, cik, adviser_name, mdm_entity_id) "
        "VALUES ('0001-25-000001', 999, 'Acme Advisers', NULL)"
    )
    candidate_db.close()

    output_path = tmp_path / "merged.duckdb"
    result = merge_candidate_into_canonical(candidate_path, canonical_path, output_path)

    assert result.rows_updated.get("sec_adv_filing", 0) == 0
    assert result.rows_unchanged.get("sec_adv_filing", 0) == 1

    conn = duckdb.connect(str(output_path))
    try:
        row = conn.execute(
            "SELECT adviser_name, mdm_entity_id FROM sec_adv_filing "
            "WHERE accession_number = '0001-25-000001'"
        ).fetchone()
    finally:
        conn.close()
    assert row == ("Acme Advisers", "entity-adv-999")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
