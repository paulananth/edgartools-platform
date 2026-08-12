"""Real end-to-end proof for decoupled-bronze-pipeline Phase 0 (ticket 12's
Answer): the per-event silver reducer must be safe regardless of delivery
order or duplicate delivery, against the REAL merge_candidate_into_canonical
and real DuckDB databases -- not a mock. This is exactly what Phase 0 exists
to prove before the reducer is ever wired to a live queue (SQS gives neither
ordering nor exactly-once delivery).

Uses sec_company_filing (business key: accession_number, authority column:
last_synced_at) since it's keyed by exactly the event granularity ticket 04
chose -- per accession.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import duckdb

from edgar_warehouse.application.silver_event_reducer import (
    AccessionDelta,
    reduce_silver_events,
)
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.silver_store import SilverDatabase


def _insert_filing(db_path: Path, *, accession_number: str, cik: int, form: str, last_synced_at: str) -> None:
    db = SilverDatabase(str(db_path))
    db._conn.execute(
        """
        INSERT INTO sec_company_filing
            (accession_number, cik, form, last_synced_at)
        VALUES (?, ?, ?, ?)
        """,
        [accession_number, cik, form, last_synced_at],
    )
    db.close()


def _upload_delta(storage: StorageLocation, relative: str, local_path: Path) -> AccessionDelta:
    payload = local_path.read_bytes()
    storage.write_bytes(relative, payload)
    return AccessionDelta(
        accession_number=relative.rsplit("/", 1)[-1].removesuffix(".duckdb"),
        delta_path=relative,
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def _filing_rows(canonical_path: Path) -> list[tuple]:
    conn = duckdb.connect(str(canonical_path))
    try:
        return conn.execute(
            "SELECT accession_number, cik, form FROM sec_company_filing ORDER BY accession_number"
        ).fetchall()
    finally:
        conn.close()


def test_two_independent_accessions_converge_to_the_same_state_regardless_of_order(tmp_path: Path):
    delta_a_path = tmp_path / "delta-a.duckdb"
    delta_b_path = tmp_path / "delta-b.duckdb"
    _insert_filing(delta_a_path, accession_number="0001-A", cik=100, form="10-K", last_synced_at="2026-08-01T00:00:00+00:00")
    _insert_filing(delta_b_path, accession_number="0001-B", cik=200, form="8-K", last_synced_at="2026-08-01T00:00:00+00:00")

    storage_ab = StorageLocation(str(tmp_path / "order-ab"))
    delta_a_ab = _upload_delta(storage_ab, "deltas/0001-A.duckdb", delta_a_path)
    delta_b_ab = _upload_delta(storage_ab, "deltas/0001-B.duckdb", delta_b_path)
    reduce_silver_events(storage_ab, deltas=[delta_a_ab, delta_b_ab])

    storage_ba = StorageLocation(str(tmp_path / "order-ba"))
    delta_a_ba = _upload_delta(storage_ba, "deltas/0001-A.duckdb", delta_a_path)
    delta_b_ba = _upload_delta(storage_ba, "deltas/0001-B.duckdb", delta_b_path)
    reduce_silver_events(storage_ba, deltas=[delta_b_ba, delta_a_ba])

    rows_ab = _filing_rows(Path(storage_ab.join("silver/sec/silver.duckdb")))
    rows_ba = _filing_rows(Path(storage_ba.join("silver/sec/silver.duckdb")))
    assert rows_ab == rows_ba == [("0001-A", 100, "10-K"), ("0001-B", 200, "8-K")]


def test_redelivering_the_same_accession_across_separate_calls_does_not_duplicate_the_row(tmp_path: Path):
    delta_a_path = tmp_path / "delta-a.duckdb"
    _insert_filing(delta_a_path, accession_number="0002-A", cik=300, form="10-Q", last_synced_at="2026-08-01T00:00:00+00:00")

    storage = StorageLocation(str(tmp_path / "warehouse"))
    delta_a = _upload_delta(storage, "deltas/0002-A.duckdb", delta_a_path)

    reduce_silver_events(storage, deltas=[delta_a])
    # Simulates SQS at-least-once redelivery: the exact same event arrives again.
    reduce_silver_events(storage, deltas=[delta_a])
    reduce_silver_events(storage, deltas=[delta_a])

    rows = _filing_rows(Path(storage.join("silver/sec/silver.duckdb")))
    assert rows == [("0002-A", 300, "10-Q")]  # exactly one row, not three


def test_a_later_delta_with_a_newer_authority_timestamp_wins_the_same_accession(tmp_path: Path):
    """Proves conflict resolution (not just disjoint-key merging) survives
    the per-event reducer path -- the declared authority_column contract
    from silver_protection.py, exercised for real."""
    original_path = tmp_path / "delta-original.duckdb"
    corrected_path = tmp_path / "delta-corrected.duckdb"
    _insert_filing(
        original_path, accession_number="0003-A", cik=400, form="10-K/A",
        last_synced_at="2026-08-01T00:00:00+00:00",
    )
    _insert_filing(
        corrected_path, accession_number="0003-A", cik=400, form="10-K",  # corrected form type
        last_synced_at="2026-08-02T00:00:00+00:00",  # strictly newer authority value
    )

    storage = StorageLocation(str(tmp_path / "warehouse"))
    delta_original = _upload_delta(storage, "deltas/0003-A-v1.duckdb", original_path)
    reduce_silver_events(storage, deltas=[delta_original])

    delta_corrected = _upload_delta(storage, "deltas/0003-A-v2.duckdb", corrected_path)
    reduce_silver_events(storage, deltas=[delta_corrected])

    rows = _filing_rows(Path(storage.join("silver/sec/silver.duckdb")))
    assert rows == [("0003-A", 400, "10-K")]  # the newer-authority correction won


def test_out_of_order_delivery_of_a_correction_does_not_regress_the_newer_value(tmp_path: Path):
    """The classic hazard SQS's lack of ordering creates: an older-authority
    delta arriving AFTER a newer one must not overwrite it."""
    older_path = tmp_path / "delta-older.duckdb"
    newer_path = tmp_path / "delta-newer.duckdb"
    _insert_filing(older_path, accession_number="0004-A", cik=500, form="10-K/A", last_synced_at="2026-08-01T00:00:00+00:00")
    _insert_filing(newer_path, accession_number="0004-A", cik=500, form="10-K", last_synced_at="2026-08-02T00:00:00+00:00")

    storage = StorageLocation(str(tmp_path / "warehouse"))
    delta_newer = _upload_delta(storage, "deltas/0004-A-newer.duckdb", newer_path)
    reduce_silver_events(storage, deltas=[delta_newer])  # newer arrives FIRST

    delta_older = _upload_delta(storage, "deltas/0004-A-older.duckdb", older_path)
    reduce_silver_events(storage, deltas=[delta_older])  # older arrives second, out of order

    rows = _filing_rows(Path(storage.join("silver/sec/silver.duckdb")))
    assert rows == [("0004-A", 500, "10-K")]  # newer value survives regardless of arrival order
