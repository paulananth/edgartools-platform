"""silver-merge-engine-migration Ticket 06c: the ownership trio is landing-only.

Nothing reads these tables back in-process: their reader is MDM (Snowflake
reader), and the artifact pipeline's silver-once skip now asks only the
bookkeeping `sec_parse_run` (`parse-ownership-bronze` was retired by Ticket 15). Every dbt silver model partitions on the old ON CONFLICT key.
The rows stamp `last_sync_run_id`; the raw rows `@track_landing_rows`
recorded did not carry it.
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


def _owner_row(**overrides):
    base = {
        "accession_number": "0000320193-26-000001", "owner_index": 1, "owner_cik": 1214156,
        "owner_name": "COOK TIMOTHY D", "is_director": True, "is_officer": True,
        "is_ten_percent_owner": False, "is_other": False, "officer_title": "CEO",
        "parser_version": "ownership_v1",
    }
    base.update(overrides)
    return base


def _non_derivative_row(**overrides):
    base = {
        "accession_number": "0000320193-26-000001", "owner_index": 1, "txn_index": 1,
        "security_title": "Common Stock", "transaction_date": "2026-09-01",
        "transaction_code": "S", "transaction_shares": 1000, "transaction_price": 230.5,
        "acquired_disposed_code": "D", "shares_owned_after": 3_000_000,
        "ownership_nature": None, "ownership_direct_indirect": "D",
        "parser_version": "ownership_v1",
    }
    base.update(overrides)
    return base


def _derivative_row(**overrides):
    base = {
        **_non_derivative_row(security_title="Restricted Stock Unit", transaction_code="M"),
        "conversion_or_exercise_price": None, "exercise_date": None,
        "expiration_date": None, "underlying_security_title": "Common Stock",
        "underlying_security_shares": 1000,
    }
    base.update(overrides)
    return base


_WRITERS = [
    ("merge_ownership_reporting_owners", "sec_ownership_reporting_owner", _owner_row),
    ("merge_ownership_non_derivative_txns", "sec_ownership_non_derivative_txn", _non_derivative_row),
    ("merge_ownership_derivative_txns", "sec_ownership_derivative_txn", _derivative_row),
]


@pytest.mark.parametrize(("method", "table", "make_row"), _WRITERS)
def test_rows_land_with_last_sync_run_id(db, method, table, make_row):
    count = getattr(db, method)([make_row(last_sync_run_id="stale")], "run-1")

    assert count == 1
    recorded = db.landing_export.tables()[table][0]
    # The old values_fn always wrote the call's sync_run_id, whatever the row said.
    assert recorded["last_sync_run_id"] == "run-1"
    assert recorded["parser_version"] == "ownership_v1"


@pytest.mark.parametrize(("method", "table", "make_row"), _WRITERS)
def test_empty_rows_record_nothing(db, method, table, make_row):
    assert getattr(db, method)([], "run-1") == 0
    assert db.landing_export.total_row_count() == 0


@pytest.mark.parametrize(
    ("method", "row"),
    [
        ("merge_ownership_reporting_owners", _owner_row(owner_index=None)),
        ("merge_ownership_non_derivative_txns", _non_derivative_row(txn_index=None)),
        ("merge_ownership_derivative_txns", _derivative_row(accession_number=None)),
    ],
)
def test_row_missing_a_key_column_raises_before_recording(db, method, row):
    """The old values_fn read the key columns as row["..."] and the local
    primary key rejected NULLs; the passthrough's NOT NULL check still raises."""
    with pytest.raises(ValueError, match="NOT NULL"):
        getattr(db, method)([row], "run-1")

    assert db.landing_export.total_row_count() == 0


def test_absent_nullable_columns_are_not_filled(db):
    """The old values_fn used row.get(...) with no default for every
    non-key column, so an absent key lands as an absent key (NULL in Snowflake)."""
    db.merge_ownership_reporting_owners(
        [{"accession_number": "0000320193-26-000001", "owner_index": 1}], "run-1"
    )

    recorded = db.landing_export.tables()["sec_ownership_reporting_owner"][0]
    assert recorded == {
        "accession_number": "0000320193-26-000001", "owner_index": 1, "last_sync_run_id": "run-1",
    }

