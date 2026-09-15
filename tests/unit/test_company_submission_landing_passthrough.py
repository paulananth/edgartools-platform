"""silver-merge-engine-migration Ticket 06b: the company submission tables
(sec_company, sec_company_address, sec_company_former_name,
sec_company_submission_file) are landing-only.

stage_submission is their only production writer. Nothing reads them back
in the same run: the one read-back (the dormant drive-submissions-discovery
acceptance driver's get_company) now settles on the recorded row count. The
dbt silver models partition on the old ON CONFLICT keys.
"""

from __future__ import annotations

import pytest

from tests.support.silver_rows import open_landing_db


@pytest.fixture()
def db():
    database = open_landing_db()
    try:
        yield database
    finally:
        database.close()


def _company_row(**overrides):
    base = {
        "cik": 320193, "entity_name": "Apple Inc.", "entity_type": "operating",
        "sic": "3571", "sic_description": "Electronic Computers",
        "state_of_incorporation": "CA", "state_of_incorporation_desc": "CA",
        "fiscal_year_end": "0927", "ein": "942404110", "description": "",
        "category": "Large accelerated filer",
    }
    base.update(overrides)
    return base


def _address_row(**overrides):
    base = {
        "cik": 320193, "address_type": "business", "street1": "One Apple Park Way",
        "street2": None, "city": "Cupertino", "state_or_country": "CA",
        "zip_code": "95014", "country": None,
    }
    base.update(overrides)
    return base


def _former_name_row(**overrides):
    base = {"cik": 320193, "former_name": "APPLE COMPUTER INC", "date_changed": "2007-01-04", "ordinal": 1}
    base.update(overrides)
    return base


def _submission_file_row(**overrides):
    base = {
        "cik": 320193, "file_name": "CIK0000320193-submissions-001.json",
        "filing_count": 1200, "filing_from": "1994-01-26", "filing_to": "2014-06-12",
    }
    base.update(overrides)
    return base


_WRITERS = [
    ("merge_company", "sec_company", _company_row),
    ("merge_addresses", "sec_company_address", _address_row),
    ("merge_former_names", "sec_company_former_name", _former_name_row),
    ("merge_submission_files", "sec_company_submission_file", _submission_file_row),
]


@pytest.mark.parametrize(("method", "table", "make_row"), _WRITERS)
def test_rows_land_with_last_sync_run_id(db, method, table, make_row):
    count = getattr(db, method)([make_row(last_sync_run_id="stale")], "run-1")

    assert count == 1
    recorded = db.landing_export.tables()[table][0]
    # The old SQL always wrote the call's sync_run_id, whatever the row said.
    assert recorded["last_sync_run_id"] == "run-1"


@pytest.mark.parametrize(("method", "table", "make_row"), _WRITERS)
def test_empty_rows_record_nothing(db, method, table, make_row):
    assert getattr(db, method)([], "run-1") == 0
    assert db.landing_export.total_row_count() == 0


@pytest.mark.parametrize(
    ("method", "table", "make_row"),
    [writer for writer in _WRITERS if writer[0] != "merge_former_names"],
)
def test_last_synced_at_is_stamped_where_the_table_carries_it(db, method, table, make_row):
    getattr(db, method)([make_row()], "run-1")

    assert db.landing_export.tables()[table][0]["last_synced_at"] is not None


def test_former_names_carry_no_last_synced_at(db):
    """sec_company_former_name has no last_synced_at column; the old INSERT
    never wrote one."""
    db.merge_former_names([_former_name_row()], "run-1")

    assert "last_synced_at" not in db.landing_export.tables()["sec_company_former_name"][0]


def test_company_first_sync_run_id_defaults_to_the_call_run_only_when_absent(db):
    """The old values were row.get("first_sync_run_id", sync_run_id)."""
    db.merge_company([_company_row(), _company_row(cik=789019, first_sync_run_id="run-0")], "run-1")

    first, second = db.landing_export.tables()["sec_company"]
    assert first["first_sync_run_id"] == "run-1"
    assert second["first_sync_run_id"] == "run-0"


@pytest.mark.parametrize(
    ("method", "row"),
    [
        ("merge_company", _company_row(cik=None)),
        ("merge_addresses", _address_row(address_type=None)),
        ("merge_former_names", _former_name_row(ordinal=None)),
        ("merge_submission_files", _submission_file_row(file_name=None)),
    ],
)
def test_row_missing_a_not_null_column_raises_before_recording(db, method, row):
    with pytest.raises(ValueError, match="NOT NULL"):
        getattr(db, method)([row], "run-1")

    assert db.landing_export.total_row_count() == 0
