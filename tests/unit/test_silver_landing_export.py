from __future__ import annotations

from datetime import UTC, datetime

from edgar_warehouse.silver_protection import PROTECTED_TABLE_REGISTRY
from edgar_warehouse.silver_store import SilverDatabase
from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer


def _landing_scoped_tables() -> set[str]:
    """Mirrors infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql's
    scope: PROTECTED_TABLE_REGISTRY minus pipeline_run_lease (operational),
    plus sec_guidance_fact_reject (real domain data the registry doesn't
    cover for an unrelated reason)."""
    return (set(PROTECTED_TABLE_REGISTRY.keys()) | {"sec_guidance_fact_reject"}) - {"pipeline_run_lease"}


def test_landing_export_defaults_to_none_and_is_a_complete_noop(tmp_path):
    """SilverDatabase(db_path) with no landing_export must behave exactly as
    it did before this change -- every decorated method checks
    self.landing_export is not None before doing anything."""
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        assert db.landing_export is None
        db.merge_company([{"cik": 320193, "entity_name": "Apple Inc"}], "run-1")
    finally:
        db.close()


def test_merge_company_records_into_landing_buffer(tmp_path):
    buffer = LandingExportBuffer()
    db = SilverDatabase(str(tmp_path / "silver.duckdb"), landing_export=buffer)
    try:
        db.merge_company(
            [
                {"cik": 320193, "entity_name": "Apple Inc"},
                {"cik": 789019, "entity_name": "Microsoft Corp"},
            ],
            "run-1",
        )
    finally:
        db.close()

    assert buffer.row_count("sec_company") == 2
    assert buffer.total_row_count() == 2
    recorded = buffer.tables()["sec_company"]
    assert {row["cik"] for row in recorded} == {320193, 789019}


def test_upsert_singular_methods_record_a_single_row(tmp_path):
    buffer = LandingExportBuffer()
    db = SilverDatabase(str(tmp_path / "silver.duckdb"), landing_export=buffer)
    try:
        db.upsert_raw_object(
            {
                "raw_object_id": "abc123",
                "source_url": "https://example.test/doc",
                "storage_path": "bronze/abc123",
                "sha256": "deadbeef",
                "fetched_at": datetime.now(UTC),
                "http_status": 200,
            }
        )
    finally:
        db.close()

    assert buffer.row_count("sec_raw_object") == 1


def test_accounting_flag_score_backfill_only_records_on_real_match(tmp_path):
    """update_accounting_flag_scores must record a landing row only when a
    real row matched (its RETURNING-based success signal) -- an unmatched
    backfill call recording a spurious row would silently teach the dbt
    silver model's collapse to see a key that was never actually written."""
    buffer = LandingExportBuffer()
    db = SilverDatabase(str(tmp_path / "silver.duckdb"), landing_export=buffer)
    try:
        # No base row exists yet -- must not record.
        matched = db.update_accounting_flag_scores(320193, "0001-25-000001", 1.5, 2.5, 3)
        assert matched is False
        assert buffer.row_count("sec_accounting_flag") == 0

        # Insert the base row, then backfill -- now it must record.
        db.merge_accounting_flags(
            [{"cik": 320193, "accession_number": "0001-25-000001", "fiscal_year": 2025, "form_type": "10-K"}],
            "run-1",
        )
        matched = db.update_accounting_flag_scores(320193, "0001-25-000001", 1.5, 2.5, 3)
        assert matched is True
    finally:
        db.close()

    recorded = buffer.tables()["sec_accounting_flag"]
    assert len(recorded) == 2
    score_row = recorded[1]
    assert score_row.pop("ingested_at") is not None
    assert score_row.pop("valid_from") is not None
    assert score_row == {
        "cik": 320193,
        "accession_number": "0001-25-000001",
        "fiscal_year": 2025,
        "period_end": None,
        "form_type": "10-K",
        "auditor_name": None,
        "auditor_pcaob_id": None,
        "auditor_location": None,
        "icfr_attestation": None,
        "auditor_changed": None,
        "beneish_m_score": 1.5,
        "altman_z_score": 2.5,
        "piotroski_f_score": 3,
        "parser_version": None,
        "valid_to": None,
        "is_current": True,
    }


def test_accounting_flag_score_backfill_preserves_other_columns_in_landing_row(tmp_path):
    """silver-retirement-integrity Ticket 04: a thin backfill row (only the
    score columns + key) would win the dbt collapse's per-key QUALIFY once it
    had the newest parse_sequence, silently nulling out every column it
    didn't carry (auditor_name, fiscal_year, period_end, form_type, the
    Ticket-33 validity-interval trio, ...). The recorded landing row must
    carry the full sec_accounting_flag record, including columns this call
    never touches, so the collapse never sees a thin row for this table at
    all."""
    buffer = LandingExportBuffer()
    db = SilverDatabase(str(tmp_path / "silver.duckdb"), landing_export=buffer)
    try:
        db.merge_accounting_flags(
            [
                {
                    "cik": 320193,
                    "accession_number": "0001-25-000001",
                    "fiscal_year": 2025,
                    "period_end": "2025-09-30",
                    "form_type": "10-K",
                    "auditor_name": "Deloitte",
                    "auditor_pcaob_id": "34",
                    "auditor_location": "San Jose, CA",
                    "icfr_attestation": True,
                    "auditor_changed": False,
                    "parser_version": "v1",
                }
            ],
            "run-1",
        )
        matched = db.update_accounting_flag_scores(320193, "0001-25-000001", 1.5, 2.5, 3)
        assert matched is True
    finally:
        db.close()

    recorded = buffer.tables()["sec_accounting_flag"]
    backfill_row = recorded[1]
    assert backfill_row["auditor_name"] == "Deloitte"
    assert backfill_row["auditor_pcaob_id"] == "34"
    assert backfill_row["auditor_location"] == "San Jose, CA"
    assert backfill_row["icfr_attestation"] is True
    assert backfill_row["auditor_changed"] is False
    assert backfill_row["fiscal_year"] == 2025
    assert backfill_row["form_type"] == "10-K"
    assert backfill_row["is_current"] is True
    assert backfill_row["valid_to"] is None
    assert backfill_row["beneish_m_score"] == 1.5
    assert backfill_row["altman_z_score"] == 2.5
    assert backfill_row["piotroski_f_score"] == 3


def test_replace_company_tickers_records_the_enriched_row_not_the_raw_input(tmp_path):
    """replace_company_tickers enriches each caller-supplied {cik, ticker,
    exchange} row internally (source_name, source_rank, last_sync_run_id,
    last_synced_at added inside its own loop) before the DuckDB INSERT --
    unlike every other landing-tracked method here, whose callers already
    pass fully-shaped rows. Confirmed live (silver-snowflake-migration
    issue 08) that recording the raw 3-column input instead of the
    enriched row landed source_name (a NOT NULL column in the Snowflake
    schema) as NULL on every row, which suspended LOAD_SILVER_LANDING_TASK.
    The recorded row must carry every column the DuckDB INSERT does."""
    buffer = LandingExportBuffer()
    db = SilverDatabase(str(tmp_path / "silver.duckdb"), landing_export=buffer)
    try:
        db.replace_company_tickers(
            [{"cik": 320193, "ticker": "AAPL", "exchange": "Nasdaq"}],
            "run-1",
            source_name="company_tickers_exchange",
        )
    finally:
        db.close()

    recorded = buffer.tables()["sec_company_ticker"]
    assert len(recorded) == 1
    row = recorded[0]
    assert row["cik"] == 320193
    assert row["ticker"] == "AAPL"
    assert row["exchange"] == "Nasdaq"
    assert row["source_name"] == "company_tickers_exchange"
    assert row["source_rank"] == 1
    assert row["last_sync_run_id"] == "run-1"
    assert row["last_synced_at"] is not None


def test_replace_company_tickers_skips_rows_missing_cik_or_ticker(tmp_path):
    buffer = LandingExportBuffer()
    db = SilverDatabase(str(tmp_path / "silver.duckdb"), landing_export=buffer)
    try:
        db.replace_company_tickers(
            [
                {"cik": None, "ticker": "AAPL"},
                {"cik": 320193, "ticker": ""},
                {"cik": 789019, "ticker": "MSFT"},
            ],
            "run-1",
        )
    finally:
        db.close()

    recorded = buffer.tables()["sec_company_ticker"]
    assert len(recorded) == 1
    assert recorded[0]["cik"] == 789019


def test_every_landing_scoped_table_has_a_decorated_writer(tmp_path):
    """Regression guard for exactly the failure shape this migration keeps
    finding and fixing (pipeline_run_lease, sec_guidance_fact_reject,
    sec_accounting_flag's COALESCE columns): if a new landing-scoped table
    is ever added to PROTECTED_TABLE_REGISTRY without also wiring a
    @track_landing_rows/@track_landing_row decorator onto its writer, this
    test fails loudly instead of silently shipping a table nothing ever
    populates.

    Drives every SilverDatabase writer whose name plausibly touches a
    landing-scoped table with a minimal row, then asserts the landing
    buffer captured something for every expected table. This is a coverage
    floor, not a correctness check -- the four tests above cover
    correctness for the tricky cases.
    """
    buffer = LandingExportBuffer()
    db = SilverDatabase(str(tmp_path / "silver.duckdb"), landing_export=buffer)
    try:
        db.merge_company([{"cik": 1, "entity_name": "x"}], "r")
        db.merge_addresses([{"cik": 1, "address_type": "business"}], "r")
        db.merge_former_names([{"cik": 1, "former_name": "y", "ordinal": 1}], "r")
        db.merge_submission_files([{"cik": 1, "file_name": "f.json"}], "r")
        db.replace_company_tickers([{"cik": 1, "ticker": "X"}], "r")
        db.merge_filings([{"accession_number": "0001-25-000001", "cik": 1}], "r")
        db.merge_current_filing_feed([{"accession_number": "0001-25-000001", "cik": 1}], "r")
        db.merge_ownership_reporting_owners([{"accession_number": "0001-25-000001", "owner_index": 1}], "r")
        db.merge_ownership_non_derivative_txns(
            [{"accession_number": "0001-25-000001", "owner_index": 1, "txn_index": 1}], "r"
        )
        db.merge_ownership_derivative_txns(
            [{"accession_number": "0001-25-000001", "owner_index": 1, "txn_index": 1}], "r"
        )
        db.merge_adv_filings([{"accession_number": "0002-25-000001"}], "r")
        db.merge_adv_offices([{"accession_number": "0002-25-000001", "office_index": 1}], "r")
        db.merge_adv_disclosure_events([{"accession_number": "0002-25-000001", "event_index": 1}], "r")
        db.merge_adv_private_funds([{"accession_number": "0002-25-000001", "fund_index": 1}], "r")
        db.merge_adv_firm_roster(
            [
                {
                    "adviser_crd_number": "1",
                    "dataset_period": "2026Q1",
                    "private_funds_reported": True,
                    "private_fund_count_7b1": 0,
                    "any_hedge_funds": False,
                    "any_pe_funds": False,
                    "private_fund_count_7b2": 0,
                }
            ],
            "r",
        )
        db.merge_subsidiary_evidence(
            [
                {
                    "accession_number": "0001-25-000001",
                    "registrant_cik": 1,
                    "document_name": "ex21",
                    "document_type": "x",
                    "row_ordinal": 1,
                    "legal_name": "x",
                    "parent_scope": "x",
                    "effective_date": "2026-01-01",
                    "row_locator": "x",
                    "source_sha256": "s",
                }
            ],
            "r",
        )
        db.merge_auditor_report_evidence(
            [
                {
                    "accession_number": "0001-25-000001",
                    "registrant_cik": 1,
                    "form_type": "10-K",
                    "document_name": "x",
                    "audited_period_end": "2026-01-01",
                    "report_date": "2026-01-01",
                    "principal_firm_name": "x",
                    "principal_firm_location": "x",
                    "pcaob_firm_id": "1",
                    "evidence_source": "x",
                    "raw_locator": "x",
                    "source_sha256": "s",
                    "evidence_fingerprint": "f1",
                }
            ],
            "r",
        )
        db.merge_pcaob_firm_identities(
            [{"pcaob_firm_id": "1", "canonical_name": "x", "snapshot_uri": "x", "snapshot_sha256": "s"}], "r"
        )
        db.upsert_raw_object(
            {
                "raw_object_id": "abc",
                "source_url": "u",
                "storage_path": "p",
                "sha256": "s",
                "fetched_at": datetime.now(UTC),
                "http_status": 200,
            }
        )
        db.merge_filing_attachments(
            [
                {
                    "accession_number": "0001-25-000001",
                    "document_name": "doc.htm",
                    "document_type": "10-K",
                    "document_url": "u",
                    "is_primary": True,
                }
            ],
            "r",
        )
        db.upsert_filing_text(
            {
                "accession_number": "0001-25-000001",
                "text_version": "v1",
                "source_document_name": "doc.htm",
                "text_storage_path": "p",
                "text_sha256": "s",
                "char_count": 1,
                "extracted_at": datetime.now(UTC),
            }
        )
        db.merge_financial_facts(
            [
                {
                    "cik": 1,
                    "accession_number": "0001-25-000001",
                    "fiscal_year": 2025,
                    "fiscal_period": "FY",
                    "period_end": "2025-12-31",
                    "period_start": "2025-01-01",
                    "form_type": "10-K",
                    "concept": "Revenue",
                    "segment": "consolidated",
                }
            ],
            "r",
        )
        db.merge_financial_derived(
            [
                {
                    "cik": 1,
                    "accession_number": "0001-25-000001",
                    "fiscal_year": 2025,
                    "fiscal_period": "FY",
                    "period_end": "2025-12-31",
                    "form_type": "10-K",
                }
            ],
            "r",
        )
        db.merge_earnings_releases(
            [
                {
                    "cik": 1,
                    "accession_number": "0001-25-000001",
                    "filing_date": "2026-01-01",
                    "fiscal_year": 2025,
                    "fiscal_quarter": 1,
                    "has_non_gaap": False,
                    "has_guidance": False,
                }
            ],
            "r",
        )
        db.merge_guidance_facts(
            [
                {
                    "fact_key": 1,
                    "cik": 1,
                    "accession_number": "0001-25-000001",
                    "metric": "revenue",
                    "period_type": "Q",
                    "fiscal_year": 2025,
                    "fiscal_quarter": 1,
                    "is_non_gaap": False,
                    "as_of": "2026-01-01",
                    "source_system": "sec_10q",
                    "confidence": "high",
                }
            ],
            "r",
        )
        db.merge_guidance_fact_rejects(
            [{"cik": 1, "accession_number": "0001-25-000001", "reject_reason": "bad"}], "r"
        )
        db.merge_accounting_flags(
            [{"cik": 1, "accession_number": "0001-25-000001", "fiscal_year": 2025, "form_type": "10-K"}], "r"
        )
        db.merge_executive_records(
            [{"cik": 1, "accession_number": "0001-25-000001", "fiscal_year": 2025, "exec_name": "x"}], "r"
        )
        db.merge_employment_events(
            [
                {
                    "accession_number": "0001-25-000001",
                    "event_index": 1,
                    "cik": 1,
                    "event_type": "hire",
                    "person_name": "x",
                    "effective_date": "2026-01-01",
                    "parser_version": "v1",
                }
            ],
            "r",
        )
        db.merge_thirteenf_holdings(
            [
                {
                    "cik": 1,
                    "accession_number": "0001-25-000001",
                    "holding_index": 1,
                    "period_of_report": "2026-01-01",
                }
            ],
            "r",
        )
        db.merge_thirteenf_filings(
            [
                {
                    "accession_number": "0001-25-000001",
                    "cik": 1,
                    "period_of_report": "2026-01-01",
                    "filing_date": "2026-01-01",
                    "form": "13F-HR",
                    "confidential_omission": False,
                    "effective_status": "active",
                    "parser_version": "v1",
                }
            ],
            "r",
        )
    finally:
        db.close()

    populated = set(buffer.tables().keys())
    missing = _landing_scoped_tables() - populated
    assert not missing, f"Landing-scoped tables with no wired writer: {sorted(missing)}"
