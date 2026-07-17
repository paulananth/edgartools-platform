-- Subject Bundle Read — issuer (ticket 11 / ADR 0001)
-- Sketch of Snowflake projections for Trading-Relevant Neighborhood sections.
--
-- Canonical semantics (unit-tested):
--   edgar_warehouse.serving.subject_bundle_read.build_issuer_subject_bundle
--
-- This file documents intended object shapes; wire MDM/graph gold tables per
-- environment before treating views as agent-grade.

CREATE SCHEMA IF NOT EXISTS EDGARTOOLS_DECISION;

-- Example: holders_of_subject with holdings-period lag metadata (Latest Complete Holdings Period)
CREATE OR REPLACE VIEW EDGARTOOLS_DECISION.BUNDLE_HOLDERS_OF_SUBJECT AS
SELECT
    h.issuer_cik AS bundle_subject_cik,
    h.manager_cik,
    h.cusip,
    h.shares,
    h.period_of_report AS latest_complete_holdings_period,
    DATEDIFF('day', h.period_of_report, CURRENT_DATE()) AS lag_days
FROM EDGARTOOLS_GOLD.INSTITUTIONAL_HOLDINGS h
WHERE h.issuer_cik IS NOT NULL;

-- Example: auditor preference for PCAOB identity
CREATE OR REPLACE VIEW EDGARTOOLS_DECISION.BUNDLE_AUDITOR AS
SELECT
    a.registrant_cik AS bundle_subject_cik,
    a.auditor_name,
    a.pcaob_id,
    'AUDITED_BY' AS relationship_type,
    'prefer_auditor_evidence_pcaob_id' AS identity_rule
FROM EDGARTOOLS_GOLD.SEC_AUDITOR_REPORT_EVIDENCE a
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY a.registrant_cik
    ORDER BY CASE WHEN a.pcaob_id IS NOT NULL THEN 0 ELSE 1 END, a.auditor_name
) = 1;

-- ADV is not_applicable for pure issuer bundles (no view required for ADV rows).
-- Manager ADV sections are ticket 12.
