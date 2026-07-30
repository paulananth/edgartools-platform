-- Subject Feature Screen (ticket 10 / ADR 0001)
-- Flat agent ranking surface over Decision Subject Universe.
--
-- Semantics (unit-tested): edgar_warehouse.serving.subject_feature_screen
-- Deploy after gold FINANCIAL_FACTORS + MDM entity tracking exist.
--
-- COMPANY is enriched by the MDM company export.  Decision Subject Universe
-- membership is therefore the explicit tracking_status='active' subset, not
-- every warehouse company.  The public bundle views add the active graph
-- generation and publication-alignment gates.
--
-- Pure-SEC features only — no price / PE / market cap columns.
-- Coverage flags: present | empty | unavailable | not_applicable

CREATE SCHEMA IF NOT EXISTS {{ database }}.EDGARTOOLS_DECISION;

CREATE OR REPLACE VIEW {{ database }}.EDGARTOOLS_DECISION.SUBJECT_FEATURE_SCREEN AS
WITH universe AS (
    SELECT DISTINCT cik::NUMBER AS cik
    FROM {{ database }}.EDGARTOOLS_GOLD.COMPANY
    WHERE LOWER(COALESCE(tracking_status, '')) = 'active'
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
    INNER JOIN fy ON fy.cik = f.cik
    WHERE UPPER(f.fiscal_period) IN ('Q1', 'Q2', 'Q3', 'Q4', 'H1', 'H2')
      AND f.period_end > fy.period_end
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
    fy.net_income AS fy_net_income,
    fy.total_assets AS fy_total_assets,
    fy.total_equity AS fy_total_equity,
    fy.free_cash_flow AS fy_free_cash_flow,
    fy.return_on_equity AS fy_roe,
    CASE
        WHEN fy.cik IS NULL THEN 'unavailable'
        WHEN fy.revenue IS NULL
             AND fy.net_income IS NULL
             AND fy.total_assets IS NULL THEN 'empty'
        ELSE 'present'
    END AS fy_features_coverage,
    interim.period_end AS interim_period_end,
    interim.fiscal_period AS interim_fiscal_period,
    interim.accession_number AS interim_accession_number,
    interim.revenue AS interim_revenue,
    interim.net_income AS interim_net_income,
    CASE
        WHEN interim.cik IS NULL THEN 'not_applicable'
        WHEN interim.revenue IS NULL AND interim.net_income IS NULL THEN 'empty'
        ELSE 'present'
    END AS interim_features_coverage,
    '1' AS decision_contract_version
FROM universe u
LEFT JOIN fy ON fy.cik = u.cik
LEFT JOIN interim ON interim.cik = u.cik
ORDER BY u.cik;
