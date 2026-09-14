"""silver-merge-engine-migration Ticket 06d: filings, filing attachments and
raw objects are landing-only, and the run reads them back from its own
recorded rows (ADR 0011).

The same warehouse run looks these rows up again: daily candidate seeding,
configured-form selection, artifact capture, parsers, release evidence and
text extraction. `get_filing`, `get_filing_attachments` and `get_raw_object`
answer from an in-run lookup the writers fill, whether or not a landing
buffer is attached. When a key recurs in one run the lookup keeps the old
upsert's per-column rule: columns its DO UPDATE SET never touched keep their
first value, every other column takes the latest write. The dbt silver models
partition on the old ON CONFLICT keys.

The insert, second-call update, first-value, same-call dedupe and empty-rows
filing cases carry over the deleted DuckDB bulk-upsert tests, which pinned the
same rule against the old upsert.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from edgar_warehouse.silver_store import SilverDatabase
from tests.support.silver_rows import open_landing_db


@pytest.fixture()
def db(tmp_path):
    database = open_landing_db(tmp_path)
    try:
        yield database
    finally:
        database.close()


def _filing(**overrides):
    base = {
        "accession_number": "0000320193-25-000050",
        "cik": 320193,
        "form": "10-K",
        "filing_date": "2025-01-01",
        "report_date": "2024-12-31",
        "acceptance_datetime": "2025-01-01T12:00:00",
        "act": "34",
        "file_number": "001-12345",
        "film_number": "25000001",
        "items": None,
        "size": 1000,
        "is_xbrl": True,
        "is_inline_xbrl": True,
        "primary_document": "doc.htm",
        "primary_doc_desc": "10-K",
    }
    base.update(overrides)
    return base


def _attachment(**overrides):
    base = {
        "accession_number": "0000320193-25-000050",
        "sequence_number": "1",
        "document_name": "doc.htm",
        "document_type": "10-K",
        "document_description": "Annual report",
        "document_url": "https://www.sec.gov/Archives/doc.htm",
        "is_primary": True,
        "raw_object_id": "sha-1",
    }
    base.update(overrides)
    return base


def _raw_object(**overrides):
    base = {
        "raw_object_id": "sha-1",
        "source_type": "filing_document",
        "cik": 320193,
        "accession_number": "0000320193-25-000050",
        "form": "10-K",
        "source_url": "https://www.sec.gov/Archives/doc.htm",
        "storage_path": "s3://bronze/doc.htm",
        "content_type": "text/html",
        "content_encoding": None,
        "byte_size": 100,
        "sha256": "sha-1",
        "fetched_at": datetime(2025, 1, 1, tzinfo=UTC),
        "http_status": 200,
        "source_last_modified": None,
        "source_etag": None,
    }
    base.update(overrides)
    return base


# ------------------------------------------------------------------
# sec_company_filing
# ------------------------------------------------------------------


def test_filings_land_with_sync_stamp_and_never_touch_local_duckdb(db):
    count = db.merge_filings([_filing(last_sync_run_id="stale")], sync_run_id="run-1")

    assert count == 1
    recorded = db.landing_export.tables()["sec_company_filing"][0]
    assert recorded["last_sync_run_id"] == "run-1"
    assert isinstance(recorded["last_synced_at"], datetime)
    assert db.fetch("SELECT COUNT(*) AS n FROM sec_company_filing")[0]["n"] == 0


def test_merge_filings_inserts_new_rows(db):
    rows = [_filing(accession_number="acc-1", cik=1), _filing(accession_number="acc-2", cik=1, form="10-Q")]

    assert db.merge_filings(rows, sync_run_id="run-1") == 2
    assert db.get_filing("acc-1")["form"] == "10-K"
    assert db.get_filing("acc-2")["form"] == "10-Q"


def test_merge_filings_updates_mutable_columns_on_second_call(db):
    db.merge_filings([_filing(accession_number="acc-1", form="10-K", size=1000)], sync_run_id="run-1")
    db.merge_filings([_filing(accession_number="acc-1", form="10-K/A", size=2000)], sync_run_id="run-2")

    stored = db.get_filing("acc-1")
    assert stored["form"] == "10-K/A"
    assert stored["size"] == 2000
    assert stored["last_sync_run_id"] == "run-2"


def test_merge_filings_keeps_first_value_columns(db):
    """A multi-CIK accession staged twice (issuer, then reporting owner) must keep
    resolving fetch_filing_artifacts to the bronze path of its first cik."""
    db.merge_filings(
        [_filing(accession_number="acc-1", cik=1, act="34", file_number="001-AAA", film_number="111", items="1.01")],
        sync_run_id="run-1",
    )
    db.merge_filings(
        [_filing(accession_number="acc-1", cik=2, act="33", file_number="002-BBB", film_number="222", items="9.99")],
        sync_run_id="run-2",
    )

    stored = db.get_filing("acc-1")
    assert (stored["cik"], stored["act"], stored["file_number"], stored["film_number"], stored["items"]) == (
        1, "34", "001-AAA", "111", "1.01"
    )
    # Landing still gets both raw writes; the dbt collapse picks between them.
    assert len(db.landing_export.tables()["sec_company_filing"]) == 2


def test_merge_filings_dedupes_same_accession_within_one_call(db):
    rows = [
        _filing(accession_number="acc-1", cik=1, form="10-K", size=1000),
        _filing(accession_number="acc-1", cik=2, form="10-K/A", size=2000),
    ]

    assert db.merge_filings(rows, sync_run_id="run-1") == 2
    stored = db.get_filing("acc-1")
    assert (stored["cik"], stored["form"], stored["size"]) == (1, "10-K/A", 2000)


def test_merge_filings_empty_rows_is_noop(db):
    assert db.merge_filings([], sync_run_id="run-1") == 0
    assert db.landing_export.total_row_count() == 0


def test_get_filing_returns_every_ddl_column_as_a_copy(db):
    db.merge_filings([{"accession_number": "acc-1", "cik": 1, "form": "4"}], sync_run_id="run-1")

    stored = db.get_filing("acc-1")
    assert list(stored) == [
        "accession_number", "cik", "form", "filing_date", "report_date", "acceptance_datetime",
        "act", "file_number", "film_number", "items", "size", "is_xbrl", "is_inline_xbrl",
        "primary_document", "primary_doc_desc", "last_sync_run_id", "last_synced_at",
    ]
    assert stored["items"] is None

    stored["form"] = "mutated"
    assert db.get_filing("acc-1")["form"] == "4"
    assert db.landing_export.tables()["sec_company_filing"][0]["form"] == "4"


def test_get_filing_unknown_accession_is_none(db):
    assert db.get_filing("missing") is None


def test_merge_filings_row_without_cik_key_raises_before_recording(db):
    """The old values_fn read row["cik"]; cik is nullable in the DDL, so the
    passthrough's NOT NULL check alone would not catch a missing key."""
    with pytest.raises(ValueError, match="cik"):
        db.merge_filings([_filing(accession_number="acc-1"), {"accession_number": "acc-2"}], "run-1")

    assert db.landing_export.total_row_count() == 0
    assert db.get_filing("acc-1") is None


def test_merge_filings_row_without_accession_number_raises_before_recording(db):
    with pytest.raises(ValueError, match="accession_number"):
        db.merge_filings([_filing(accession_number=None)], "run-1")

    assert db.landing_export.total_row_count() == 0


def test_lookup_is_filled_without_a_landing_buffer(tmp_path):
    database = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        database.merge_filings([_filing(accession_number="acc-1")], sync_run_id="run-1")
        database.merge_filing_attachments([_attachment(accession_number="acc-1")], sync_run_id="run-1")
        database.upsert_raw_object(_raw_object())

        assert database.get_filing("acc-1")["form"] == "10-K"
        assert [row["document_name"] for row in database.get_filing_attachments("acc-1")] == ["doc.htm"]
        assert database.get_raw_object("sha-1")["storage_path"] == "s3://bronze/doc.htm"
    finally:
        database.close()


# ------------------------------------------------------------------
# sec_filing_attachment
# ------------------------------------------------------------------


def test_attachments_land_with_sync_run_id_and_default_is_primary(db):
    row = _attachment()
    del row["is_primary"]

    assert db.merge_filing_attachments([row], sync_run_id="run-1") == 1
    recorded = db.landing_export.tables()["sec_filing_attachment"][0]
    assert recorded["last_sync_run_id"] == "run-1"
    assert recorded["is_primary"] is False
    assert db.fetch("SELECT COUNT(*) AS n FROM sec_filing_attachment")[0]["n"] == 0


def test_attachment_latest_write_replaces_the_row(db):
    db.merge_filing_attachments([_attachment(raw_object_id="sha-1", sequence_number="1")], "run-1")
    db.merge_filing_attachments([_attachment(raw_object_id="sha-2", sequence_number="2")], "run-2")
    db.merge_filing_attachments([_attachment(document_name="ex21.htm", is_primary=False)], "run-2")

    rows = {row["document_name"]: row for row in db.get_filing_attachments("0000320193-25-000050")}
    assert set(rows) == {"doc.htm", "ex21.htm"}
    assert (rows["doc.htm"]["raw_object_id"], rows["doc.htm"]["sequence_number"]) == ("sha-2", "2")
    assert rows["doc.htm"]["last_sync_run_id"] == "run-2"
    assert db.get_filing_attachments("other-accession") == []


def test_get_filing_attachments_returns_copies(db):
    db.merge_filing_attachments([_attachment()], "run-1")

    db.get_filing_attachments("0000320193-25-000050")[0]["raw_object_id"] = "mutated"
    assert db.get_filing_attachments("0000320193-25-000050")[0]["raw_object_id"] == "sha-1"


@pytest.mark.parametrize("field", ["accession_number", "document_name", "document_type", "document_url"])
def test_attachment_with_falsy_required_field_raises_before_recording(db, field):
    with pytest.raises(ValueError, match=field):
        db.merge_filing_attachments([_attachment(document_name="ok.htm"), _attachment(**{field: ""})], "run-1")

    assert db.landing_export.total_row_count() == 0
    assert db.get_filing_attachments("0000320193-25-000050") == []


# ------------------------------------------------------------------
# sec_raw_object
# ------------------------------------------------------------------


def test_raw_object_lands_as_given_and_never_touches_local_duckdb(db):
    assert db.upsert_raw_object(_raw_object()) is None

    assert db.landing_export.tables()["sec_raw_object"] == [_raw_object()]
    assert db.fetch("SELECT COUNT(*) AS n FROM sec_raw_object")[0]["n"] == 0


def test_raw_object_keeps_first_fetched_at_and_takes_latest_otherwise(db):
    first = datetime(2025, 1, 1, tzinfo=UTC)
    db.upsert_raw_object(_raw_object(fetched_at=first, storage_path="s3://bronze/a.htm"))
    db.upsert_raw_object(_raw_object(fetched_at=datetime(2025, 2, 1, tzinfo=UTC), storage_path="s3://bronze/b.htm"))

    stored = db.get_raw_object("sha-1")
    assert stored["fetched_at"] == first
    assert stored["storage_path"] == "s3://bronze/b.htm"
    assert db.get_raw_object("missing") is None


@pytest.mark.parametrize(
    "field", ["raw_object_id", "source_url", "storage_path", "sha256", "fetched_at", "http_status"]
)
def test_raw_object_with_none_required_field_raises_before_recording(db, field):
    with pytest.raises(ValueError, match=field):
        db.upsert_raw_object(_raw_object(**{field: None}))

    assert db.landing_export.total_row_count() == 0
    assert db.get_raw_object("sha-1") is None
