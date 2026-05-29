-- FINANCIAL_FACTS: XBRL financial facts per (cik, accession, concept, fiscal_period).
--
-- Isolated DAG branch — zero ref() edges into the existing 9-table chain.
-- TARGET_LAG=DOWNSTREAM: refreshes only after upstream silver export completes.
-- A NULL source (no fundamentals bootstrap yet) produces an empty table; the
-- existing gold chain is unaffected.
--
-- Grain: one row per (cik, accession_number, concept, fiscal_period, segment).
{{ gold_model_config('FINANCIAL_FACTS') }}

select
    cik,
    accession_number,
    fiscal_year,
    fiscal_period,
    period_end,
    form_type,
    concept,
    value,
    unit,
    decimals,
    segment,
    parser_version,
    ingested_at
from {{ source("edgartools_source", "SEC_FINANCIAL_FACT") }}
