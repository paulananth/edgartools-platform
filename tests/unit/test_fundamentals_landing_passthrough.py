"""merge_financial_facts / merge_financial_derived / merge_accounting_flags
are landing-only (silver-merge-engine-migration Tickets 02/03).

Their local DuckDB merge (QUALIFY ROW_NUMBER dedup + ON CONFLICT upsert)
computed a result nothing read back once DuckDB Retirement Cutover Ticket 10
made the local store ephemeral. Each method now records its rows to the
landing export and nothing else; the dbt silver models collapse them.
Replaces test_financial_fact_retirement.py's landing-row tests (its
retirement tests went with retire_*_not_in_snapshot, whose only caller was
the dormant company-facts acceptance driver).
"""

from __future__ import annotations

import pytest

from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer
from edgar_warehouse.silver_store import SilverDatabase


def _fact_row(**overrides):
    base = {
        "cik": 320193,
        "accession_number": "0000320193-23-000106",
        "fiscal_year": 2023,
        "fiscal_period": "FY",
        "period_end": "2023-09-30",
        "period_start": "2022-10-01",
        "form_type": "10-K",
        "concept": "Assets",
        "value": 1000.0,
        "unit": "USD",
        "decimals": -6,
        "segment": "consolidated",
        "parser_version": "1",
    }
    base.update(overrides)
    return base


def _flag_row(**overrides):
    base = {
        "cik": 320193,
        "accession_number": "0000320193-23-000106",
        "fiscal_year": 2023,
        "period_end": "2023-09-30",
        "form_type": "10-K",
        "auditor_name": "Ernst & Young LLP",
        "parser_version": "1",
    }
    base.update(overrides)
    return base


def _derived_row(**overrides):
    base = {
        "cik": 320193,
        "accession_number": "0000320193-23-000106",
        "fiscal_year": 2023,
        "fiscal_period": "FY",
        "period_end": "2023-09-30",
        "form_type": "10-K",
        "revenue": 383285000000.0,
        "parser_version": "1",
    }
    base.update(overrides)
    return base


@pytest.fixture()
def db(tmp_path):
    landing = LandingExportBuffer()
    database = SilverDatabase(str(tmp_path / "silver.duckdb"), landing_export=landing)
    database.landing = landing
    try:
        yield database
    finally:
        database.close()


@pytest.mark.parametrize(
    ("method", "table", "row"),
    [
        ("merge_financial_facts", "sec_financial_fact", _fact_row()),
        ("merge_financial_derived", "sec_financial_derived", _derived_row()),
        ("merge_accounting_flags", "sec_accounting_flag", _flag_row()),
    ],
)
def test_rows_go_to_the_landing_export_and_never_local_duckdb(db, method, table, row):
    count = getattr(db, method)([row], "run-1")

    assert count == 1
    assert db.landing.row_count(table) == 1
    assert db.fetch(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"] == 0


@pytest.mark.parametrize("method", ["merge_financial_facts", "merge_financial_derived", "merge_accounting_flags"])
def test_empty_rows_record_nothing(db, method):
    assert getattr(db, method)([], "run-1") == 0
    assert db.landing.total_row_count() == 0


def test_duplicate_keys_are_passed_through_for_the_dbt_collapse(db):
    """No local dedup anymore: both raw rows land, and the dbt silver model's
    QUALIFY picks the winner (last-write-wins on value)."""
    count = db.merge_financial_facts([_fact_row(value=1.0), _fact_row(value=2.0)], "run-1")

    assert count == 2
    assert [r["value"] for r in db.landing.tables()["sec_financial_fact"]] == [1.0, 2.0]


@pytest.mark.parametrize(
    ("method", "table", "row"),
    [
        ("merge_financial_facts", "sec_financial_fact", _fact_row()),
        ("merge_accounting_flags", "sec_accounting_flag", _flag_row()),
    ],
)
def test_facts_and_flags_carry_current_state_and_ingested_at(db, method, table, row):
    """Ticket 33's validity trio plus ingested_at (which DuckDB used to
    supply via DEFAULT and the gold accounting_flags model still outputs)
    are stamped per write -- never left for the collapse to NULL."""
    getattr(db, method)([row], "run-1")

    recorded = db.landing.tables()[table][0]
    assert recorded["is_current"] is True
    assert recorded["valid_to"] is None
    assert recorded["valid_from"] is not None
    assert recorded["ingested_at"] is not None


def test_derived_rows_are_recorded_as_given(db):
    """Including explicit None metrics -- the key stays, as it did under
    @track_landing_rows."""
    row = _derived_row(ebitda=None)

    db.merge_financial_derived([row], "run-1")

    assert db.landing.tables()["sec_financial_derived"] == [row]


def test_old_values_fn_defaults_are_applied(db):
    fact = _fact_row()
    for column in ("period_start", "form_type", "segment"):
        del fact[column]
    flag = _flag_row()
    del flag["form_type"]

    db.merge_financial_facts([fact], "run-1")
    db.merge_accounting_flags([flag], "run-1")

    recorded_fact = db.landing.tables()["sec_financial_fact"][0]
    assert recorded_fact["period_start"] == "0001-01-01"
    assert recorded_fact["form_type"] == ""
    assert recorded_fact["segment"] == "consolidated"
    assert db.landing.tables()["sec_accounting_flag"][0]["form_type"] == "10-K"


def test_scored_flag_row_lands_complete(db):
    """silver-retirement-integrity Ticket 04: the row carrying the forensic
    scores must be the full record, never a thin score-only row."""
    db.merge_accounting_flags(
        [_flag_row(beneish_m_score=1.5, altman_z_score=2.5, piotroski_f_score=3)], "run-1"
    )

    recorded = db.landing.tables()["sec_accounting_flag"][0]
    assert recorded["auditor_name"] == "Ernst & Young LLP"
    assert recorded["beneish_m_score"] == 1.5
    assert recorded["piotroski_f_score"] == 3


@pytest.mark.parametrize(
    ("method", "row"),
    [
        ("merge_financial_facts", _fact_row(fiscal_year=None)),
        ("merge_financial_facts", _fact_row(period_end=None)),
        # A present None on a defaulted column is not "absent" -- the old
        # r.get(col, default) passed it through and DuckDB rejected it.
        ("merge_financial_facts", _fact_row(segment=None)),
        ("merge_financial_facts", _fact_row(period_start=None)),
        ("merge_financial_derived", _derived_row(fiscal_year=None)),
        ("merge_accounting_flags", _flag_row(fiscal_year=None)),
        ("merge_accounting_flags", _flag_row(form_type=None)),
    ],
)
def test_a_row_missing_a_not_null_column_raises_before_recording(db, method, row):
    """DuckDB's NOT NULL DDL rejected these; Snowflake landing's NOT NULL
    would reject the whole Parquet file. Fail here, loudly, first."""
    with pytest.raises(ValueError, match="NOT NULL"):
        getattr(db, method)([row], "run-1")

    assert db.landing.total_row_count() == 0


def test_no_landing_export_is_a_noop(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        assert db.merge_financial_facts([_fact_row()], "run-1") == 1
    finally:
        db.close()


def test_required_columns_fail_closed_on_an_unknown_table(db):
    """The NOT NULL set comes from the DuckDB DDL this map is retiring; an
    empty result must never silently turn the guard into a no-op."""
    with pytest.raises(ValueError, match="no NOT NULL columns"):
        db._record_landing_passthrough("sec_no_such_table", [{"cik": 1}], defaults={}, stamp={})

    assert db.landing.total_row_count() == 0
