"""merge_financial_facts / merge_financial_derived / merge_accounting_flags
are landing-only (silver-merge-engine-migration Tickets 02/03).

Each method records its rows to the landing export and nothing else; the
dbt silver models collapse them on the old ON CONFLICT key.
Replaces test_financial_fact_retirement.py's landing-row tests (its
retirement tests went with retire_*_not_in_snapshot, whose only caller was
the dormant company-facts acceptance driver).
"""

from __future__ import annotations

import time

import pytest

from edgar_warehouse.silver_landing_store import SilverLandingStore
from tests.support.silver_rows import open_landing_db


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
def db():
    database = open_landing_db()
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
def test_rows_go_to_the_landing_export(db, method, table, row):
    count = getattr(db, method)([row], "run-1")

    assert count == 1
    assert db.landing_export.row_count(table) == 1


@pytest.mark.parametrize("method", ["merge_financial_facts", "merge_financial_derived", "merge_accounting_flags"])
def test_empty_rows_record_nothing(db, method):
    assert getattr(db, method)([], "run-1") == 0
    assert db.landing_export.total_row_count() == 0


def test_duplicate_keys_are_passed_through_for_the_dbt_collapse(db):
    """No local dedup anymore: both raw rows land, and the dbt silver model's
    QUALIFY picks the winner (last-write-wins on value)."""
    count = db.merge_financial_facts([_fact_row(value=1.0), _fact_row(value=2.0)], "run-1")

    assert count == 2
    assert [r["value"] for r in db.landing_export.tables()["sec_financial_fact"]] == [1.0, 2.0]


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

    recorded = db.landing_export.tables()[table][0]
    assert recorded["is_current"] is True
    assert recorded["valid_to"] is None
    assert recorded["valid_from"] is not None
    assert recorded["ingested_at"] is not None


def test_derived_rows_are_recorded_as_given(db):
    """Including explicit None metrics -- the key stays, as it did under
    @track_landing_rows."""
    row = _derived_row(ebitda=None)

    db.merge_financial_derived([row], "run-1")

    assert db.landing_export.tables()["sec_financial_derived"] == [row]


def test_old_values_fn_defaults_are_applied(db):
    fact = _fact_row()
    for column in ("period_start", "form_type", "segment"):
        del fact[column]
    flag = _flag_row()
    del flag["form_type"]

    db.merge_financial_facts([fact], "run-1")
    db.merge_accounting_flags([flag], "run-1")

    recorded_fact = db.landing_export.tables()["sec_financial_fact"][0]
    assert recorded_fact["period_start"] == "0001-01-01"
    assert recorded_fact["form_type"] == ""
    assert recorded_fact["segment"] == "consolidated"
    assert db.landing_export.tables()["sec_accounting_flag"][0]["form_type"] == "10-K"


def test_scored_flag_row_lands_complete(db):
    """silver-retirement-integrity Ticket 04: the row carrying the forensic
    scores must be the full record, never a thin score-only row."""
    db.merge_accounting_flags(
        [_flag_row(beneish_m_score=1.5, altman_z_score=2.5, piotroski_f_score=3)], "run-1"
    )

    recorded = db.landing_export.tables()["sec_accounting_flag"][0]
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
    """Snowflake landing's NOT NULL would reject the whole Parquet file.
    Fail here, loudly, first."""
    with pytest.raises(ValueError, match="NOT NULL"):
        getattr(db, method)([row], "run-1")

    assert db.landing_export.total_row_count() == 0


def test_no_landing_export_is_a_noop():
    db = SilverLandingStore()
    try:
        assert db.merge_financial_facts([_fact_row()], "run-1") == 1
    finally:
        db.close()


def test_required_columns_fail_closed_on_an_unknown_table(db):
    """The NOT NULL set comes from the silver schema snapshot (Ticket 13); a
    table it does not know must never silently turn the guard into a no-op."""
    with pytest.raises(ValueError, match="not in the silver schema snapshot"):
        db._record_landing_passthrough("sec_no_such_table", [{"cik": 1}], defaults={}, stamp={})

    assert db.landing_export.total_row_count() == 0


# ---------------------------------------------------------------------------
# silver-merge-engine-migration Ticket 04: the per-filing fundamentals tables
# (bootstrap-fundamentals --mode per-filing, plus Branch A's Item 5.02 parse
# for sec_employment_event). Same passthrough; no Ticket 33 validity trio on
# these tables, but ingested_at is stamped -- MDM's EMPLOYED_BY derivation
# filters sec_executive_record/sec_employment_event on `ingested_at >
# watermark`, and the raw rows @track_landing_rows used to record carried no
# ingested_at at all.
# ---------------------------------------------------------------------------


def _earnings_row(**overrides):
    base = {
        "cik": 8818, "accession_number": "0000008818-26-000010", "filing_date": "2026-04-28",
        "fiscal_year": 2026, "fiscal_quarter": 1, "period_end": "2026-03-31",
        "revenue_gaap": 2298500000.0, "net_income_gaap": 168100000.0, "eps_gaap_diluted": None,
        "has_non_gaap": False, "has_guidance": True, "parser_version": "2",
    }
    base.update(overrides)
    return base


def _executive_row(**overrides):
    base = {
        "cik": 8818, "accession_number": "0000008818-26-000011", "fiscal_year": 2025,
        "exec_name": "Jane Doe", "exec_role": "CEO", "total_comp": 1000000.0, "parser_version": "1",
    }
    base.update(overrides)
    return base


def _employment_row(**overrides):
    base = {
        "accession_number": "0000008818-26-000012", "event_index": 1, "cik": 8818,
        "event_type": "appointment", "person_name": "Jane Doe", "exec_role": "CFO",
        "previous_role": None, "compensation_amount": None,
        "effective_date": "2026-04-01", "parser_version": "1",
    }
    base.update(overrides)
    return base


def _guidance_row(**overrides):
    base = {
        "fact_key": 1, "cik": 8818, "ticker": "AVY", "company_key": None,
        "accession_number": "0000008818-26-000010", "metric": "revenue",
        "period_type": "quarterly", "fiscal_year": 2026, "fiscal_quarter": 2,
        "value_low": 100.0, "value_mid": 110.0, "value_high": 120.0,
        "is_non_gaap": False, "as_of": "2026-04-28", "source_system": "sec_8k",
        "confidence": "high", "parser_version": "1",
    }
    base.update(overrides)
    return base


def _guidance_reject_row(**overrides):
    base = {
        "cik": 8818, "accession_number": "0000008818-26-000010", "metric": "revenue",
        "reject_reason": "low_gt_high", "raw_payload": "{}", "parser_version": "1",
    }
    base.update(overrides)
    return base


_PER_FILING_WRITERS = [
    ("merge_earnings_releases", "sec_earnings_release", _earnings_row),
    ("merge_executive_records", "sec_executive_record", _executive_row),
    ("merge_employment_events", "sec_employment_event", _employment_row),
    ("merge_guidance_facts", "sec_guidance_fact", _guidance_row),
    ("merge_guidance_fact_rejects", "sec_guidance_fact_reject", _guidance_reject_row),
]


def test_earnings_release_presence_flags_keep_the_old_bool_coercion(db):
    """The old `_merge_rows` values_fn was bool(r.get(flag, False)): absent or
    None -> False, truthy -> True."""
    absent = _earnings_row()
    del absent["has_non_gaap"]

    db.merge_earnings_releases([absent, _earnings_row(has_non_gaap=None, has_guidance=1)], "run-1")

    recorded = db.landing_export.tables()["sec_earnings_release"]
    assert [(r["has_non_gaap"], r["has_guidance"]) for r in recorded] == [(False, True), (False, True)]


def test_guidance_fact_keeps_the_old_coercions_and_defaults(db):
    """The old `_merge_rows` values_fn: accession_number `or ""`,
    bool(is_non_gaap), confidence default 'medium'."""
    row = _guidance_row(accession_number=None, is_non_gaap=None)
    del row["confidence"]

    db.merge_guidance_facts([row], "run-1")

    recorded = db.landing_export.tables()["sec_guidance_fact"][0]
    assert recorded["accession_number"] == ""
    assert recorded["is_non_gaap"] is False
    assert recorded["confidence"] == "medium"


def test_guidance_fact_reject_keeps_the_empty_accession_coercion(db):
    db.merge_guidance_fact_rejects([_guidance_reject_row(accession_number=None)], "run-1")

    assert db.landing_export.tables()["sec_guidance_fact_reject"][0]["accession_number"] == ""


@pytest.mark.parametrize(
    ("method", "row"),
    [
        ("merge_earnings_releases", _earnings_row(filing_date=None)),
        ("merge_executive_records", _executive_row(exec_name=None)),
        ("merge_employment_events", _employment_row(parser_version=None)),
        ("merge_guidance_facts", _guidance_row(metric=None)),
        ("merge_guidance_fact_rejects", _guidance_reject_row(reject_reason=None)),
    ],
)
def test_per_filing_row_missing_a_not_null_column_raises_before_recording(db, method, row):
    with pytest.raises(ValueError, match="NOT NULL"):
        getattr(db, method)([row], "run-1")

    assert db.landing_export.total_row_count() == 0


# ---------------------------------------------------------------------------
# silver-merge-engine-migration Ticket 05: the two 13F tables
# (bootstrap-fundamentals --mode thirteenf). sec_thirteenf_holding is the
# platform's highest-volume table (6.8M rows in prod), so this section also
# pins the passthrough's cost on a realistic per-filing batch.
# ---------------------------------------------------------------------------


def _holding_row(**overrides):
    base = {
        "cik": 1067983, "accession_number": "0000950123-26-000123", "holding_index": 1,
        "period_of_report": "2026-03-31", "cusip": "037833100", "issuer_name": "Apple Inc",
        "security_title": "COM", "shares_held": 400000000.0, "market_value": 70000000000.0,
        "security_class": "equity", "put_call": None, "discretion_type": "SOLE",
        "voting_auth_sole": 400000000.0, "voting_auth_shared": 0.0, "voting_auth_none": 0.0,
        "parser_version": "1",
    }
    base.update(overrides)
    return base


def _thirteenf_filing_row(**overrides):
    base = {
        "accession_number": "0000950123-26-000123", "cik": 1067983,
        "period_of_report": "2026-03-31", "filing_date": "2026-05-15", "form": "13F-HR",
        "amendment_type": None, "confidential_omission": False, "parser_version": "1",
    }
    base.update(overrides)
    return base


_THIRTEENF_WRITERS = [
    ("merge_thirteenf_holdings", "sec_thirteenf_holding", _holding_row),
    ("merge_thirteenf_filings", "sec_thirteenf_filing", _thirteenf_filing_row),
]


# Tables stamped with `ingested_at` only: the per-filing tables (Ticket 04)
# and the 13F tables (Ticket 05).
_INGESTED_AT_WRITERS = _PER_FILING_WRITERS + _THIRTEENF_WRITERS


@pytest.mark.parametrize(("method", "table", "make_row"), _INGESTED_AT_WRITERS)
def test_ingested_at_rows_land(db, method, table, make_row):
    count = getattr(db, method)([make_row()], "run-1")

    assert count == 1
    recorded = db.landing_export.tables()[table][0]
    assert recorded["ingested_at"] is not None
    # No validity trio on these tables -- that stamp is facts/flags only.
    assert "is_current" not in recorded


@pytest.mark.parametrize(("method", "table", "make_row"), _INGESTED_AT_WRITERS)
def test_ingested_at_advances_on_every_write(db, method, table, make_row):
    """The intent of the retired DuckDB bump tests (release-readiness Ticket
    98): re-processing the same business key must carry a newer ingested_at
    than the prior write -- MDM's EMPLOYED_BY and INSTITUTIONAL_HOLDS
    watermarks and the gold models read it."""
    getattr(db, method)([make_row()], "run-1")
    time.sleep(0.01)
    getattr(db, method)([make_row()], "run-2")

    first, second = (row["ingested_at"] for row in db.landing_export.tables()[table])
    assert second > first


def test_thirteenf_filing_keeps_the_old_coercions_and_defaults(db):
    """The old `_merge_rows` values_fn: bool(confidential_omission),
    effective_status default 'effective', parser_version default '1'."""
    row = _thirteenf_filing_row(confidential_omission=None)
    del row["parser_version"]

    db.merge_thirteenf_filings([row], "run-1")

    recorded = db.landing_export.tables()["sec_thirteenf_filing"][0]
    assert recorded["confidential_omission"] is False
    assert recorded["effective_status"] == "effective"
    assert recorded["parser_version"] == "1"


@pytest.mark.parametrize(
    ("method", "row"),
    [
        ("merge_thirteenf_holdings", _holding_row(period_of_report=None)),
        ("merge_thirteenf_holdings", _holding_row(holding_index=None)),
        ("merge_thirteenf_filings", _thirteenf_filing_row(filing_date=None)),
        ("merge_thirteenf_filings", _thirteenf_filing_row(form=None)),
    ],
)
def test_thirteenf_row_missing_a_not_null_column_raises_before_recording(db, method, row):
    with pytest.raises(ValueError, match="NOT NULL"):
        getattr(db, method)([row], "run-1")

    assert db.landing_export.total_row_count() == 0


def test_thirteenf_holdings_batch_of_a_large_filer_records_every_row(db):
    """Ticket 05's volume check. A large 13F-HR filer reports a few thousand
    holdings per quarter; the very largest (broker-dealer aggregators) reach
    tens of thousands."""
    rows = [_holding_row(holding_index=i, cusip=f"{i:09d}") for i in range(1, 20_001)]

    count = db.merge_thirteenf_holdings(rows, "run-1")

    assert count == 20_000
    assert db.landing_export.row_count("sec_thirteenf_holding") == 20_000
