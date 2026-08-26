"""Regression tests for Ticket 33 (change-propagation map): validity-interval
retirement on sec_financial_fact / sec_accounting_flag.

Covers retire_financial_facts_not_in_snapshot/retire_accounting_flags_not_in_snapshot
directly, plus merge_financial_facts/merge_accounting_flags's reinstatement
branch (is_current/valid_to reset on ON CONFLICT). See
tests/acquisition/test_company_facts_silver_acceptance.py for the end-to-end
wiring test through _finalize_company_facts_candidate.
"""

from __future__ import annotations

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


def _fact_key(row: dict) -> tuple:
    return (
        row["accession_number"], row["concept"], row["fiscal_period"],
        row["segment"], row["period_end"], row["period_start"],
    )


def _flag_row(**overrides):
    base = {
        "cik": 320193,
        "accession_number": "0000320193-23-000106",
        "fiscal_year": 2023,
        "period_end": "2023-09-30",
        "form_type": "10-K",
        "auditor_name": "Ernst & Young LLP",
        "auditor_pcaob_id": "42",
        "auditor_location": "San Jose, CA",
        "icfr_attestation": True,
        "auditor_changed": False,
        "parser_version": "1",
    }
    base.update(overrides)
    return base


def test_retire_closes_the_interval_for_a_fact_absent_from_a_fresh_snapshot(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        assets = _fact_row(concept="Assets")
        revenue = _fact_row(concept="Revenues")
        db.merge_financial_facts([assets, revenue], sync_run_id="run-1")

        # A fresh, complete snapshot's membership set no longer has Revenues.
        retired_count = db.retire_financial_facts_not_in_snapshot(
            320193, [_fact_key(assets)], sync_run_id="run-2"
        )
        assert retired_count == 1

        rows = db.fetch(
            "SELECT concept, is_current, valid_to FROM sec_financial_fact "
            "WHERE cik = ? ORDER BY concept",
            [320193],
        )
        assert rows[0]["concept"] == "Assets"
        assert rows[0]["is_current"] is True
        assert rows[0]["valid_to"] is None

        assert rows[1]["concept"] == "Revenues"
        assert rows[1]["is_current"] is False
        assert rows[1]["valid_to"] is not None

        # Never physically deletes -- the retired row's history is still
        # queryable by value, not just by is_current status.
        retired_value = db.fetch(
            "SELECT value FROM sec_financial_fact WHERE cik = ? AND concept = 'Revenues'",
            [320193],
        )
        assert retired_value == [{"value": 1000.0}]
    finally:
        db.close()


def test_retire_with_empty_snapshot_retires_every_current_fact_for_the_cik(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        db.merge_financial_facts(
            [_fact_row(concept="Assets"), _fact_row(concept="Revenues")],
            sync_run_id="run-1",
        )

        retired_count = db.retire_financial_facts_not_in_snapshot(
            320193, [], sync_run_id="run-2"
        )
        assert retired_count == 2

        rows = db.fetch(
            "SELECT is_current FROM sec_financial_fact WHERE cik = ?", [320193]
        )
        assert all(r["is_current"] is False for r in rows)
    finally:
        db.close()


def test_retire_only_touches_the_named_cik(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        db.merge_financial_facts(
            [_fact_row(cik=320193, concept="Assets"), _fact_row(cik=1234, concept="Assets")],
            sync_run_id="run-1",
        )

        db.retire_financial_facts_not_in_snapshot(320193, [], sync_run_id="run-2")

        other_cik_rows = db.fetch(
            "SELECT is_current FROM sec_financial_fact WHERE cik = 1234"
        )
        assert other_cik_rows == [{"is_current": True}]
    finally:
        db.close()


def test_a_retired_fact_reappearing_in_a_later_snapshot_is_reinstated(tmp_path):
    """merge_financial_facts's ON CONFLICT branch, not the retire call
    itself, handles reinstatement -- ticket 33's own design note.
    """

    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        revenue = _fact_row(concept="Revenues")
        db.merge_financial_facts([revenue], sync_run_id="run-1")
        db.retire_financial_facts_not_in_snapshot(320193, [], sync_run_id="run-2")

        before = db.fetch(
            "SELECT is_current, valid_to FROM sec_financial_fact WHERE concept = 'Revenues'"
        )
        assert before[0]["is_current"] is False
        assert before[0]["valid_to"] is not None

        # Revenues reappears in a later complete snapshot.
        db.merge_financial_facts([revenue], sync_run_id="run-3")

        after = db.fetch(
            "SELECT is_current, valid_to FROM sec_financial_fact WHERE concept = 'Revenues'"
        )
        assert after == [{"is_current": True, "valid_to": None}]
    finally:
        db.close()


def test_retire_accounting_flags_closes_the_interval_for_an_absent_accession(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        kept = _flag_row(accession_number="0000320193-23-000106")
        dropped = _flag_row(accession_number="0000320193-22-000108")
        db.merge_accounting_flags([kept, dropped], sync_run_id="run-1")

        retired_count = db.retire_accounting_flags_not_in_snapshot(
            320193, ["0000320193-23-000106"], sync_run_id="run-2"
        )
        assert retired_count == 1

        rows = db.fetch(
            "SELECT accession_number, is_current FROM sec_accounting_flag "
            "WHERE cik = ? ORDER BY accession_number",
            [320193],
        )
        by_accession = {r["accession_number"]: r["is_current"] for r in rows}
        assert by_accession["0000320193-23-000106"] is True
        assert by_accession["0000320193-22-000108"] is False
    finally:
        db.close()


def test_retire_accounting_flags_with_empty_snapshot_retires_all_current_rows(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        db.merge_accounting_flags([_flag_row()], sync_run_id="run-1")

        retired_count = db.retire_accounting_flags_not_in_snapshot(
            320193, [], sync_run_id="run-2"
        )
        assert retired_count == 1
        rows = db.fetch("SELECT is_current FROM sec_accounting_flag WHERE cik = 320193")
        assert rows == [{"is_current": False}]
    finally:
        db.close()


def test_a_retired_accounting_flag_reappearing_is_reinstated(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        flag = _flag_row()
        db.merge_accounting_flags([flag], sync_run_id="run-1")
        db.retire_accounting_flags_not_in_snapshot(320193, [], sync_run_id="run-2")

        db.merge_accounting_flags([flag], sync_run_id="run-3")

        rows = db.fetch(
            "SELECT is_current, valid_to FROM sec_accounting_flag WHERE cik = 320193"
        )
        assert rows == [{"is_current": True, "valid_to": None}]
    finally:
        db.close()


def test_merge_financial_facts_records_deterministic_current_state_to_landing_export(tmp_path):
    """An ordinary (non-retiring) write must never leave is_current/valid_to
    unset in the landing-tracked row -- a row present in this call is
    current by construction, and needs no DB read-back to know that. Before
    this fix, every ordinary write's landing row lacked these keys
    entirely, which would collapse to is_current=NULL forever in
    Snowflake-native silver for any fact that's never been retired.
    """

    from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer

    landing = LandingExportBuffer()
    db = SilverDatabase(str(tmp_path / "silver.duckdb"), landing_export=landing)
    try:
        db.merge_financial_facts([_fact_row(concept="Assets")], sync_run_id="run-1")

        recorded = landing.tables()["sec_financial_fact"][-1]
        assert recorded["is_current"] is True
        assert recorded["valid_to"] is None
        assert recorded["valid_from"] is not None
    finally:
        db.close()


def test_merge_accounting_flags_records_deterministic_current_state_to_landing_export(tmp_path):
    from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer

    landing = LandingExportBuffer()
    db = SilverDatabase(str(tmp_path / "silver.duckdb"), landing_export=landing)
    try:
        db.merge_accounting_flags([_flag_row()], sync_run_id="run-1")

        recorded = landing.tables()["sec_accounting_flag"][-1]
        assert recorded["is_current"] is True
        assert recorded["valid_to"] is None
        assert recorded["valid_from"] is not None
    finally:
        db.close()


def test_retire_with_no_matching_rows_is_a_clean_zero_and_no_landing_export(tmp_path):
    from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer

    landing = LandingExportBuffer()
    db = SilverDatabase(str(tmp_path / "silver.duckdb"), landing_export=landing)
    try:
        # Nothing has ever been written for this CIK.
        retired_count = db.retire_financial_facts_not_in_snapshot(
            999999, [], sync_run_id="run-1"
        )
        assert retired_count == 0
        assert landing.total_row_count() == 0
    finally:
        db.close()


def test_retire_records_retired_rows_into_landing_export(tmp_path):
    from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer

    landing = LandingExportBuffer()
    db = SilverDatabase(str(tmp_path / "silver.duckdb"), landing_export=landing)
    try:
        db.merge_financial_facts([_fact_row(concept="Revenues")], sync_run_id="run-1")
        landing_after_merge = landing.row_count("sec_financial_fact")

        db.retire_financial_facts_not_in_snapshot(320193, [], sync_run_id="run-2")

        assert landing.row_count("sec_financial_fact") == landing_after_merge + 1
        recorded = landing.tables()["sec_financial_fact"][-1]
        assert recorded["concept"] == "Revenues"
        assert recorded["is_current"] is False
    finally:
        db.close()
