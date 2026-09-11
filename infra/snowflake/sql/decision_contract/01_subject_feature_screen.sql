-- Subject Feature Screen (ticket 10 / ADR 0001)
-- Flat agent ranking surface over Decision Subject Universe.
--
-- Semantics (unit-tested): edgar_warehouse.serving.subject_feature_screen
-- Deploy after gold FINANCIAL_FACTORS + MDM entity tracking exist.
--
-- Decision Subject Universe is MDM_COMPANY_ENTITY (tracking_status='active'),
-- not warehouse COMPANY. Ticket 41: the previous COMPANY self-join treated
-- every gold company as MDM-active.
--
-- Pure-SEC features only — no price / PE / market cap columns.
-- Coverage flags: present | empty | unavailable | not_applicable
-- v1 vector is the 19 Python PURE_SEC_FEATURE_KEYS. Gold return_on_equity /
-- return_on_assets bind as fy_roe / fy_roa. ebitda, eps_diluted, and
-- ebitda_margin come from FINANCIAL_FACTORS (passed through from derived).
-- Do not alias operating_margin to ebitda_margin. Interim does not require FY.

CREATE SCHEMA IF NOT EXISTS {{ database }}.EDGARTOOLS_DECISION;

CREATE OR REPLACE VIEW {{ database }}.EDGARTOOLS_DECISION.SUBJECT_FEATURE_SCREEN AS
WITH universe AS (
    SELECT DISTINCT cik::NUMBER AS cik
    FROM {{ database }}.EDGARTOOLS_GOLD.MDM_COMPANY_ENTITY
    WHERE cik IS NOT NULL
      AND LOWER(COALESCE(tracking_status, '')) = 'active'
),
factors AS (
    SELECT *
    FROM {{ database }}.EDGARTOOLS_GOLD.FINANCIAL_FACTORS
),
fy AS (
    SELECT *
    FROM factors
    WHERE UPPER(fiscal_period) = 'FY'
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY cik
        ORDER BY period_end DESC, accession_number DESC
    ) = 1
),
interim AS (
    SELECT f.*
    FROM factors f
    LEFT JOIN fy ON fy.cik = f.cik
    WHERE UPPER(f.fiscal_period) IN ('Q1', 'Q2', 'Q3', 'Q4', 'H1', 'H2')
      AND (fy.period_end IS NULL OR f.period_end > fy.period_end)
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY f.cik
        ORDER BY f.period_end DESC, f.accession_number DESC
    ) = 1
)
SELECT
    u.cik,
    fy.period_end AS fy_period_end,
    fy.fiscal_year AS fy_fiscal_year,
    fy.accession_number AS fy_accession_number,
    fy.revenue AS fy_revenue,
    fy.gross_profit AS fy_gross_profit,
    fy.ebitda AS fy_ebitda,
    fy.ebit AS fy_ebit,
    fy.net_income AS fy_net_income,
    fy.eps_diluted AS fy_eps_diluted,
    fy.total_assets AS fy_total_assets,
    fy.total_liabilities AS fy_total_liabilities,
    fy.total_equity AS fy_total_equity,
    fy.cash_and_equivalents AS fy_cash_and_equivalents,
    fy.total_debt AS fy_total_debt,
    fy.operating_cash_flow AS fy_operating_cash_flow,
    fy.free_cash_flow AS fy_free_cash_flow,
    fy.gross_margin AS fy_gross_margin,
    fy.ebitda_margin AS fy_ebitda_margin,
    fy.net_margin AS fy_net_margin,
    fy.return_on_equity AS fy_roe,
    fy.return_on_assets AS fy_roa,
    fy.roic AS fy_roic,
    CASE
        WHEN fy.cik IS NULL THEN 'unavailable'
        WHEN fy.revenue IS NULL
             AND fy.gross_profit IS NULL
             AND fy.ebitda IS NULL
             AND fy.ebit IS NULL
             AND fy.net_income IS NULL
             AND fy.eps_diluted IS NULL
             AND fy.total_assets IS NULL
             AND fy.total_liabilities IS NULL
             AND fy.total_equity IS NULL
             AND fy.cash_and_equivalents IS NULL
             AND fy.total_debt IS NULL
             AND fy.operating_cash_flow IS NULL
             AND fy.free_cash_flow IS NULL
             AND fy.gross_margin IS NULL
             AND fy.ebitda_margin IS NULL
             AND fy.net_margin IS NULL
             AND fy.return_on_equity IS NULL
             AND fy.return_on_assets IS NULL
             AND fy.roic IS NULL THEN 'empty'
        ELSE 'present'
    END AS fy_features_coverage,
    interim.period_end AS interim_period_end,
    interim.fiscal_period AS interim_fiscal_period,
    interim.accession_number AS interim_accession_number,
    interim.revenue AS interim_revenue,
    interim.gross_profit AS interim_gross_profit,
    interim.ebitda AS interim_ebitda,
    interim.ebit AS interim_ebit,
    interim.net_income AS interim_net_income,
    interim.eps_diluted AS interim_eps_diluted,
    interim.total_assets AS interim_total_assets,
    interim.total_liabilities AS interim_total_liabilities,
    interim.total_equity AS interim_total_equity,
    interim.cash_and_equivalents AS interim_cash_and_equivalents,
    interim.total_debt AS interim_total_debt,
    interim.operating_cash_flow AS interim_operating_cash_flow,
    interim.free_cash_flow AS interim_free_cash_flow,
    interim.gross_margin AS interim_gross_margin,
    interim.ebitda_margin AS interim_ebitda_margin,
    interim.net_margin AS interim_net_margin,
    interim.return_on_equity AS interim_roe,
    interim.return_on_assets AS interim_roa,
    interim.roic AS interim_roic,
    CASE
        WHEN interim.cik IS NULL THEN 'not_applicable'
        WHEN interim.revenue IS NULL
             AND interim.gross_profit IS NULL
             AND interim.ebitda IS NULL
             AND interim.ebit IS NULL
             AND interim.net_income IS NULL
             AND interim.eps_diluted IS NULL
             AND interim.total_assets IS NULL
             AND interim.total_liabilities IS NULL
             AND interim.total_equity IS NULL
             AND interim.cash_and_equivalents IS NULL
             AND interim.total_debt IS NULL
             AND interim.operating_cash_flow IS NULL
             AND interim.free_cash_flow IS NULL
             AND interim.gross_margin IS NULL
             AND interim.ebitda_margin IS NULL
             AND interim.net_margin IS NULL
             AND interim.return_on_equity IS NULL
             AND interim.return_on_assets IS NULL
             AND interim.roic IS NULL THEN 'empty'
        ELSE 'present'
    END AS interim_features_coverage,
    '1' AS decision_contract_version
FROM universe u
LEFT JOIN fy ON fy.cik = u.cik
LEFT JOIN interim ON interim.cik = u.cik
ORDER BY u.cik;
