from __future__ import annotations

from edgar_warehouse.serving.dashboard_workflows import (
    MAX_ADV_ROWS,
    MAX_COMPANY_ROWS,
    MAX_INSIDER_ROWS,
    MAX_SCREEN_ROWS,
    adv_query,
    company_query,
    data_state,
    fundamentals_query,
    insider_query,
    sec_filing_url,
)


def test_data_states_never_coerce_missing_to_zero() -> None:
    assert data_state(None, covered=False) == "coverage_unavailable"
    assert data_state(None, history_available=False) == "insufficient_history"
    assert data_state(None) == "value_unavailable"
    assert data_state(0) == "numeric_zero"
    assert data_state(1) == "available"


def test_company_queries_are_bound_and_capped() -> None:
    for surface in (
        "filings", "financials", "insiders", "earnings", "executives",
        "accounting_flags", "institutional_holders", "relationships",
    ):
        query = company_query(surface, 320193, limit=10_000)
        assert query.max_rows == MAX_COMPANY_ROWS
        assert "?" in query.sql
        assert f"limit {MAX_COMPANY_ROWS}" in query.sql
        assert query.params[0] == 320193


def test_fundamentals_query_has_all_accounting_filters() -> None:
    query = fundamentals_query(
        sic_pattern="35%", fiscal_period="FY", min_revenue=1,
        min_growth=0.1, min_current_ratio=1, max_debt_to_assets=0.8,
        min_cash_to_assets=0.1, min_fcf_to_revenue=0,
        max_accruals_to_assets=0.2, risk_tier="low", limit=999,
    )
    assert query.max_rows == MAX_SCREEN_ROWS
    assert "tracking_status" in query.sql
    assert "revenue_cagr_3y" in query.sql
    assert "beneish_risk_tier" in query.sql
    assert "limit 200" in query.sql
    assert "35%" in query.params


def test_insider_query_deduplicates_and_preserves_null_notional() -> None:
    query = insider_query(
        start_date="2026-01-01", end_date="2026-07-29",
        issuer_pattern="%APPLE%", form_pattern="4%",
        owner_role="officer",
        transaction_code="P", min_shares=1, min_notional=None,
        derivative="non_derivative", limit=999,
    )
    assert query.max_rows == MAX_INSIDER_ROWS
    assert "transaction_semantics" in query.sql
    assert "partition by o.accession_number, o.owner_index, o.txn_index" in query.sql
    assert "transaction_shares * o.transaction_price" in query.sql


def test_adv_query_is_bounded_and_searches_all_identifiers() -> None:
    query = adv_query("%VANGUARD%", limit=999)
    assert query.max_rows == MAX_ADV_ROWS
    assert query.params == ("%VANGUARD%",) * 5
    assert "private_fund_id ilike ?" in query.sql
    assert "MANAGES_FUND" in query.sql


def test_sec_evidence_link_normalizes_archive_path() -> None:
    url = sec_filing_url(320193, "0000320193-24-000123")
    assert url.endswith(
        "/320193/000032019324000123/0000320193-24-000123-index.html"
    )
