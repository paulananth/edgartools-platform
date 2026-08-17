-- dbt-gold-silver-rewiring map, Ticket 02: digest-based Table-Specific
-- Reconciliation (duckdb-retirement map, Ticket 07's cutover validation
-- standard) for the six near-mechanical passthrough models this ticket
-- rewired from EDGARTOOLS_SOURCE (Python-builder mirror) onto EDGARTOOLS_SILVER
-- (dbt-collapsed native-pull landing zone), via ref().
--
-- Run in the target Snowflake database (dev or prod) with a role that has
-- SELECT on both EDGARTOOLS_SOURCE and EDGARTOOLS_SILVER. Reporting query,
-- not a deployment gate -- per this repo's validation standard, an
-- automated assertion (a future dbt test or CI step, not built here) should
-- gate the actual DuckDB-path deletion in Ticket 07; a human still reviews
-- this output before that gate is added.
--
-- HASH_AGG() is Snowflake's order-independent aggregate hash -- two row
-- sets with identical content hash identically regardless of row order,
-- which is exactly the "same semantic content" property this standard asks
-- for. Compared on business-key content only: none of these six tables
-- carry a hash-derived surrogate key (that's Ticket 01's scope, for
-- filing_activity/company/etc.), so no key-column exclusion is needed here.
--
-- A HASH_AGG mismatch here means the two sourcing paths genuinely disagree
-- on content and must be investigated before this table's dbt run
-- --full-refresh is trusted; a match is the pass signal this ticket's
-- acceptance criterion asks for.

-- ── financial_facts (SEC_FINANCIAL_FACT) ──────────────────────────────────
-- Old: EDGARTOOLS_SOURCE mirror. New: dbt silver sec_financial_fact.
select
    'financial_facts' as gold_model,
    (select hash_agg(cik, accession_number, concept, fiscal_period, segment,
                      period_end, period_start, fiscal_year, form_type, unit,
                      value, decimals, parser_version)
     from EDGARTOOLS_SOURCE.SEC_FINANCIAL_FACT) as old_digest,
    (select hash_agg(cik, accession_number, concept, fiscal_period, segment,
                      period_end, period_start, fiscal_year, form_type, unit,
                      value, decimals, parser_version)
     from EDGARTOOLS_SILVER.SEC_FINANCIAL_FACT) as new_digest,
    (select count(*) from EDGARTOOLS_SOURCE.SEC_FINANCIAL_FACT) as old_row_count,
    (select count(*) from EDGARTOOLS_SILVER.SEC_FINANCIAL_FACT) as new_row_count

union all

-- ── institutional_holdings (SEC_THIRTEENF_HOLDING) ────────────────────────
select
    'institutional_holdings',
    (select hash_agg(cik, accession_number, holding_index, period_of_report,
                      cusip, issuer_name, security_title, security_class,
                      shares_held, market_value, put_call, discretion_type,
                      voting_auth_sole, voting_auth_shared, voting_auth_none,
                      parser_version)
     from EDGARTOOLS_SOURCE.SEC_THIRTEENF_HOLDING),
    (select hash_agg(cik, accession_number, holding_index, period_of_report,
                      cusip, issuer_name, security_title, security_class,
                      shares_held, market_value, put_call, discretion_type,
                      voting_auth_sole, voting_auth_shared, voting_auth_none,
                      parser_version)
     from EDGARTOOLS_SILVER.SEC_THIRTEENF_HOLDING),
    (select count(*) from EDGARTOOLS_SOURCE.SEC_THIRTEENF_HOLDING),
    (select count(*) from EDGARTOOLS_SILVER.SEC_THIRTEENF_HOLDING)

union all

-- ── financial_derived (SEC_FINANCIAL_DERIVED) ─────────────────────────────
-- financial_factors is not reconciled separately: it has never sourced from
-- EDGARTOOLS_SOURCE directly (only ref('financial_derived')), so a passing
-- financial_derived digest here transitively covers it -- there is no
-- separate old-vs-new sourcing path for financial_factors to compare.
select
    'financial_derived',
    (select hash_agg(cik, accession_number, fiscal_period, period_end,
                      fiscal_year, form_type, revenue, gross_profit, ebitda,
                      ebit, net_income, eps_diluted, total_assets,
                      total_liabilities, total_equity, cash_and_equivalents,
                      total_debt, current_assets, current_liabilities,
                      accounts_receivable, inventory,
                      selling_general_admin_expense, retained_earnings,
                      depreciation_amortization, property_plant_equipment_net,
                      shares_outstanding, operating_cash_flow, capex,
                      free_cash_flow, gross_margin, ebitda_margin, net_margin,
                      roic, roe, roa, parser_version)
     from EDGARTOOLS_SOURCE.SEC_FINANCIAL_DERIVED),
    (select hash_agg(cik, accession_number, fiscal_period, period_end,
                      fiscal_year, form_type, revenue, gross_profit, ebitda,
                      ebit, net_income, eps_diluted, total_assets,
                      total_liabilities, total_equity, cash_and_equivalents,
                      total_debt, current_assets, current_liabilities,
                      accounts_receivable, inventory,
                      selling_general_admin_expense, retained_earnings,
                      depreciation_amortization, property_plant_equipment_net,
                      shares_outstanding, operating_cash_flow, capex,
                      free_cash_flow, gross_margin, ebitda_margin, net_margin,
                      roic, roe, roa, parser_version)
     from EDGARTOOLS_SILVER.SEC_FINANCIAL_DERIVED),
    (select count(*) from EDGARTOOLS_SOURCE.SEC_FINANCIAL_DERIVED),
    (select count(*) from EDGARTOOLS_SILVER.SEC_FINANCIAL_DERIVED)

union all

-- ── adv_fund_count_reconciliation: filing-derived side (SEC_ADV_PRIVATE_FUND) ──
select
    'adv_fund_count_reconciliation (private_fund side)',
    (select hash_agg(adviser_crd_number, private_fund_id)
     from EDGARTOOLS_SOURCE.SEC_ADV_PRIVATE_FUND
     where adviser_crd_number is not null),
    (select hash_agg(adviser_crd_number, private_fund_id)
     from EDGARTOOLS_SILVER.SEC_ADV_PRIVATE_FUND
     where adviser_crd_number is not null),
    (select count(*) from EDGARTOOLS_SOURCE.SEC_ADV_PRIVATE_FUND where adviser_crd_number is not null),
    (select count(*) from EDGARTOOLS_SILVER.SEC_ADV_PRIVATE_FUND where adviser_crd_number is not null)

union all

-- ── adv_fund_count_reconciliation: roster side (SEC_ADV_FIRM_ROSTER) ──────
select
    'adv_fund_count_reconciliation (firm_roster side)',
    (select hash_agg(adviser_crd_number, dataset_period, private_fund_count_7b1, private_fund_count_7b2)
     from EDGARTOOLS_SOURCE.SEC_ADV_FIRM_ROSTER
     where adviser_crd_number is not null),
    (select hash_agg(adviser_crd_number, dataset_period, private_fund_count_7b1, private_fund_count_7b2)
     from EDGARTOOLS_SILVER.SEC_ADV_FIRM_ROSTER
     where adviser_crd_number is not null),
    (select count(*) from EDGARTOOLS_SOURCE.SEC_ADV_FIRM_ROSTER where adviser_crd_number is not null),
    (select count(*) from EDGARTOOLS_SILVER.SEC_ADV_FIRM_ROSTER where adviser_crd_number is not null)

union all

-- ── ticker_reference (TICKER_REFERENCE vs sec_company_ticker) ─────────────
-- The genuinely non-mechanical rewire in this batch: old side is the
-- seed-universe-loader-built EDGARTOOLS_SOURCE.TICKER_REFERENCE; new side
-- is EDGARTOOLS_SILVER.SEC_COMPANY_TICKER filtered to
-- source_name = 'company_tickers_exchange' (see ticker_reference.sql's
-- header comment for the full reasoning). A mismatch here is the most
-- likely of the six to reflect a genuine, expected difference -- the two
-- paths parse the same SEC payload independently -- so investigate row-level
-- diffs, not just the digest, before treating a mismatch as a defect.
select
    'ticker_reference',
    (select hash_agg(cik, ticker, exchange)
     from EDGARTOOLS_SOURCE.TICKER_REFERENCE),
    (select hash_agg(cik, ticker, exchange)
     from EDGARTOOLS_SILVER.SEC_COMPANY_TICKER
     where source_name = 'company_tickers_exchange'),
    (select count(*) from EDGARTOOLS_SOURCE.TICKER_REFERENCE),
    (select count(*) from EDGARTOOLS_SILVER.SEC_COMPANY_TICKER where source_name = 'company_tickers_exchange')

order by gold_model;
