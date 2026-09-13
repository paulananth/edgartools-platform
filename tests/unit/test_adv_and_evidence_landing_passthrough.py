"""silver-merge-engine-migration Ticket 06a: the ADV tables, the relationship-
source evidence tables and the current filing feed are landing-only.

None of them is read back in-process: their readers are MDM (Snowflake
reader), and `_run_parse_adv_bronze`'s `already_parsed` gate keeps its own
in-run set. Every dbt silver model partitions on the old ON CONFLICT key.
These tables stamp `last_sync_run_id` (the feed also `last_synced_at`);
the raw rows `@track_landing_rows` recorded carried neither.
"""

from __future__ import annotations

import pytest

from tests.support.silver_rows import CountingConnection, open_landing_db


@pytest.fixture()
def db(tmp_path):
    database = open_landing_db(tmp_path)
    try:
        yield database
    finally:
        database.close()


def _adv_filing_row(**overrides):
    base = {
        "accession_number": "iapd-adv:2115188", "cik": None, "form": "ADV",
        "adviser_name": "PNC WEALTH", "sec_file_number": "801-66195", "crd_number": "129052",
        "effective_date": "2026-06-24", "filing_status": "effective",
        "filing_action": "current_compilation", "source_format": "iapd_bulk_csv",
        "parser_version": "iapd_bulk_v1",
    }
    base.update(overrides)
    return base


def _adv_office_row(**overrides):
    base = {
        "accession_number": "iapd-adv:2115188", "office_index": 1, "office_name": "HQ",
        "city": "Pittsburgh", "state_or_country": "PA", "country": "United States",
        "is_headquarters": True, "parser_version": "adv_v1",
    }
    base.update(overrides)
    return base


def _adv_disclosure_row(**overrides):
    base = {
        "accession_number": "iapd-adv:2115188", "event_index": 1,
        "disclosure_category": "regulatory", "event_date": "2025-01-01",
        "is_reported": True, "description": "x", "parser_version": "adv_v1",
    }
    base.update(overrides)
    return base


def _adv_fund_row(**overrides):
    base = {
        "accession_number": "iapd-adv:2115188", "fund_index": 1, "filing_id": "2115188",
        "adviser_crd_number": "129052", "private_fund_id": "805-123", "reference_id": "518607",
        "schedule_section": "7B1", "reporting_role": "detailed_reporter",
        "filing_action": "current_compilation", "fund_name": "ALPHA FUND",
        "fund_type": "Private Equity Fund", "jurisdiction": "Delaware / United States",
        "aum_amount": None, "effective_date": "2026-06-24", "source_dataset_period": "2026-06",
        "source_sha256": "abc123", "parser_version": "iapd_bulk_v1",
    }
    base.update(overrides)
    return base


def _firm_roster_row(**overrides):
    base = {
        "adviser_crd_number": "1588", "dataset_period": "2026-07",
        "private_funds_reported": True, "private_fund_count_7b1": 3,
        "any_hedge_funds": True, "hedge_fund_count": 3, "any_pe_funds": False,
        "pe_fund_count": None, "total_gross_assets_private_funds": 709905606,
        "private_fund_count_7b2": 0, "source_sha256": "abc123", "parser_version": "firm_roster_v1",
    }
    base.update(overrides)
    return base


def _subsidiary_row(**overrides):
    base = {
        "accession_number": "0000320193-25-000079", "registrant_cik": 320193,
        "document_name": "ex21.htm", "document_type": "EX-21", "row_ordinal": 1,
        "legal_name": "Apple Operations International", "jurisdiction": "Ireland",
        "parent_scope": "registrant_disclosed", "immediate_parent_known": False,
        "effective_date": "2025-09-27", "row_locator": "tr[1]", "source_sha256": "s",
        "parser_version": "subsidiary_exhibit_v1",
    }
    base.update(overrides)
    return base


def _auditor_row(**overrides):
    base = {
        "accession_number": "0000320193-25-000079", "registrant_cik": 320193,
        "form_type": "10-K", "document_name": "aapl-10k.htm",
        "audited_period_end": "2025-09-27", "report_date": "2025-10-31",
        "principal_firm_name": "Ernst & Young LLP", "principal_firm_location": "San Jose, CA",
        "pcaob_firm_id": "42", "evidence_source": "form_10k", "raw_locator": "p[12]",
        "source_sha256": "s", "evidence_fingerprint": "f1", "form_ap_filing_id": None,
        "original_form_ap_filing_id": None, "latest_amendment": None,
        "parser_version": "auditor_evidence_v1",
    }
    base.update(overrides)
    return base


def _pcaob_row(**overrides):
    base = {
        "pcaob_firm_id": "42", "canonical_name": "Ernst & Young LLP", "city": "New York",
        "state": "NY", "country": "United States", "status": "registered",
        "snapshot_uri": "s3://x/firms.csv", "snapshot_sha256": "s",
    }
    base.update(overrides)
    return base


def _feed_row(**overrides):
    base = {
        "accession_number": "0000320193-26-000010", "cik": 320193, "form": "8-K",
        "company_name": "Apple Inc.", "filing_date": "2026-09-12",
        "accepted_at": "2026-09-12T16:30:00", "filing_href": "h", "index_href": "i",
        "summary": "s", "source_url": "u", "feed_published_at": "2026-09-12T16:31:00",
        "raw_object_id": "r",
    }
    base.update(overrides)
    return base


_WRITERS = [
    ("merge_adv_filings", "sec_adv_filing", _adv_filing_row),
    ("merge_adv_offices", "sec_adv_office", _adv_office_row),
    ("merge_adv_disclosure_events", "sec_adv_disclosure_event", _adv_disclosure_row),
    ("merge_adv_private_funds", "sec_adv_private_fund", _adv_fund_row),
    ("merge_adv_firm_roster", "sec_adv_firm_roster", _firm_roster_row),
    ("merge_subsidiary_evidence", "sec_subsidiary_evidence", _subsidiary_row),
    ("merge_auditor_report_evidence", "sec_auditor_report_evidence", _auditor_row),
    ("merge_pcaob_firm_identities", "sec_pcaob_firm_identity", _pcaob_row),
    ("merge_current_filing_feed", "sec_current_filing_feed", _feed_row),
]


@pytest.mark.parametrize(("method", "table", "make_row"), _WRITERS)
def test_rows_land_with_last_sync_run_id_and_never_touch_local_duckdb(db, method, table, make_row):
    count = getattr(db, method)([make_row(last_sync_run_id="stale")], "run-1")

    assert count == 1
    recorded = db.landing_export.tables()[table][0]
    # The old values_fn always wrote the call's sync_run_id, whatever the row said.
    assert recorded["last_sync_run_id"] == "run-1"
    assert db.fetch(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"] == 0


@pytest.mark.parametrize(("method", "table", "make_row"), _WRITERS)
def test_empty_rows_record_nothing(db, method, table, make_row):
    assert getattr(db, method)([], "run-1") == 0
    assert db.landing_export.total_row_count() == 0


def test_current_filing_feed_stamps_last_synced_at(db):
    db.merge_current_filing_feed([_feed_row()], "run-1")

    assert db.landing_export.tables()["sec_current_filing_feed"][0]["last_synced_at"] is not None


def test_current_filing_feed_still_skips_rows_without_an_accession_number(db):
    """The old loop `continue`d past a falsy accession_number -- skipped and
    not counted, never raised."""
    count = db.merge_current_filing_feed(
        [_feed_row(accession_number=None), _feed_row(accession_number=""), _feed_row()], "run-1"
    )

    assert count == 1
    assert db.landing_export.row_count("sec_current_filing_feed") == 1


def test_duplicate_keys_are_passed_through_for_the_dbt_collapse(db):
    """merge_adv_filings/merge_adv_private_funds used to dedupe within a call
    (QUALIFY on seq, last occurrence wins); both rows now land and the dbt
    silver model's QUALIFY picks one. Which duplicate wins inside a single
    call is not guaranteed there -- parse_sequence is assigned per load, not
    per row order -- but callers never send conflicting duplicates
    (adv_bulk_ingest rejects them)."""
    count = db.merge_adv_filings(
        [_adv_filing_row(adviser_name="A"), _adv_filing_row(adviser_name="B")], "run-1"
    )

    assert count == 2
    assert [r["adviser_name"] for r in db.landing_export.tables()["sec_adv_filing"]] == ["A", "B"]


def test_evidence_writers_keep_the_old_absent_key_defaults(db):
    """The old values_fn: subsidiary immediate_parent_known False and
    parser_version 'subsidiary_exhibit_v1'; auditor parser_version
    'auditor_evidence_v1' -- filled only when the key is absent."""
    subsidiary = _subsidiary_row()
    del subsidiary["immediate_parent_known"]
    del subsidiary["parser_version"]
    auditor = _auditor_row()
    del auditor["parser_version"]

    db.merge_subsidiary_evidence([subsidiary], "run-1")
    db.merge_auditor_report_evidence([auditor], "run-1")

    recorded_subsidiary = db.landing_export.tables()["sec_subsidiary_evidence"][0]
    assert recorded_subsidiary["immediate_parent_known"] is False
    assert recorded_subsidiary["parser_version"] == "subsidiary_exhibit_v1"
    assert db.landing_export.tables()["sec_auditor_report_evidence"][0]["parser_version"] == "auditor_evidence_v1"


@pytest.mark.parametrize(
    ("method", "row"),
    [
        ("merge_adv_filings", _adv_filing_row(accession_number=None)),
        ("merge_adv_offices", _adv_office_row(office_index=None)),
        ("merge_adv_disclosure_events", _adv_disclosure_row(event_index=None)),
        ("merge_adv_private_funds", _adv_fund_row(fund_index=None)),
        ("merge_adv_firm_roster", _firm_roster_row(dataset_period=None)),
        ("merge_subsidiary_evidence", _subsidiary_row(row_ordinal=None)),
        ("merge_auditor_report_evidence", _auditor_row(evidence_fingerprint=None)),
        ("merge_pcaob_firm_identities", _pcaob_row(snapshot_sha256=None)),
    ],
)
def test_row_missing_a_not_null_column_raises_before_recording(db, method, row):
    with pytest.raises(ValueError, match="NOT NULL"):
        getattr(db, method)([row], "run-1")

    assert db.landing_export.total_row_count() == 0


def test_adv_private_fund_window_does_no_per_row_duckdb_io(db):
    """A 13-month advFilingData window stages ~384K fund rows in one call.
    The passthrough makes at most the one cached NOT NULL lookup."""
    rows = [_adv_fund_row(fund_index=i) for i in range(1, 20_001)]
    counting = CountingConnection(db._conn)
    db._conn = counting
    try:
        count = db.merge_adv_private_funds(rows, "run-1")
    finally:
        db._conn = counting.wrapped

    assert count == 20_000
    assert db.landing_export.row_count("sec_adv_private_fund") == 20_000
    assert counting.executes <= 1
