-- Ticket 01: one-statement, read-only freeze of the company-eligible universe
-- and the canonical SEC company-ticker rows used to determine eligibility.
-- Query version: gleif-company-cohort-v1
-- Eligibility is settled: current active MDM rows where SEC entity_type is
-- operating OR CIK occurs in the captured canonical SEC ticker snapshot.

WITH
mdm_current AS (
    SELECT *
    FROM EDGARTOOLS_PROD.EDGARTOOLS_GOLD.MDM_COMPANY_ENTITY
    WHERE LOWER(COALESCE(TRACKING_STATUS, '')) = 'active'
      AND CIK IS NOT NULL
      AND VALID_TO IS NULL
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY CIK
        ORDER BY VALID_FROM DESC NULLS LAST, ENTITY_ID
    ) = 1
),
canonical_ticker_rows AS (
    SELECT
        CIK,
        TICKER,
        EXCHANGE,
        SOURCE_NAME,
        SOURCE_RANK,
        LAST_SYNC_RUN_ID,
        LAST_SYNCED_AT
    FROM EDGARTOOLS_PROD.EDGARTOOLS_SILVER.SEC_COMPANY_TICKER
    WHERE CIK IS NOT NULL
      AND LOWER(COALESCE(SOURCE_NAME, '')) = 'company_tickers_exchange'
),
ticker_by_cik AS (
    SELECT
        CIK,
        ARRAY_AGG(
            OBJECT_CONSTRUCT_KEEP_NULL(
                'ticker', TICKER,
                'exchange', EXCHANGE,
                'source_name', SOURCE_NAME,
                'source_rank', SOURCE_RANK,
                'last_sync_run_id', LAST_SYNC_RUN_ID,
                'last_synced_at', TO_VARCHAR(LAST_SYNCED_AT)
            )
        ) WITHIN GROUP (ORDER BY SOURCE_RANK NULLS LAST, TICKER, EXCHANGE) AS TICKERS
    FROM canonical_ticker_rows
    GROUP BY CIK
),
address_by_cik AS (
    SELECT
        CIK,
        ARRAY_AGG(
            OBJECT_CONSTRUCT_KEEP_NULL(
                'address_type', ADDRESS_TYPE,
                'street1', STREET1,
                'street2', STREET2,
                'city', CITY,
                'state_or_country', STATE_OR_COUNTRY,
                'zip_code', ZIP_CODE,
                'country', COUNTRY,
                'last_sync_run_id', LAST_SYNC_RUN_ID,
                'last_synced_at', TO_VARCHAR(LAST_SYNCED_AT)
            )
        ) WITHIN GROUP (ORDER BY ADDRESS_TYPE) AS ADDRESSES
    FROM EDGARTOOLS_PROD.EDGARTOOLS_SILVER.SEC_COMPANY_ADDRESS
    GROUP BY CIK
),
former_by_cik AS (
    SELECT
        CIK,
        ARRAY_AGG(
            OBJECT_CONSTRUCT_KEEP_NULL(
                'former_name', FORMER_NAME,
                'date_changed', TO_VARCHAR(DATE_CHANGED),
                'ordinal', ORDINAL,
                'last_sync_run_id', LAST_SYNC_RUN_ID
            )
        ) WITHIN GROUP (ORDER BY ORDINAL, FORMER_NAME) AS FORMER_NAMES
    FROM EDGARTOOLS_PROD.EDGARTOOLS_SILVER.SEC_COMPANY_FORMER_NAME
    GROUP BY CIK
),
subsidiary_by_cik AS (
    SELECT REGISTRANT_CIK AS CIK, COUNT(*) AS SUBSIDIARY_EVIDENCE_COUNT
    FROM EDGARTOOLS_PROD.EDGARTOOLS_SILVER.SEC_SUBSIDIARY_EVIDENCE
    GROUP BY REGISTRANT_CIK
),
eligible AS (
    SELECT
        m.*,
        s.ENTITY_NAME AS SEC_ENTITY_NAME,
        LOWER(COALESCE(s.ENTITY_TYPE, '')) AS SEC_ENTITY_TYPE,
        s.SIC AS SEC_SIC,
        s.SIC_DESCRIPTION AS SEC_SIC_DESCRIPTION,
        s.STATE_OF_INCORPORATION AS SEC_STATE_OF_INCORPORATION,
        s.STATE_OF_INCORPORATION_DESC AS SEC_STATE_OF_INCORPORATION_DESC,
        s.FISCAL_YEAR_END AS SEC_FISCAL_YEAR_END,
        s.EIN AS SEC_EIN,
        s.CATEGORY AS SEC_CATEGORY,
        s.FIRST_SYNC_RUN_ID AS SEC_FIRST_SYNC_RUN_ID,
        s.LAST_SYNC_RUN_ID AS SEC_LAST_SYNC_RUN_ID,
        TO_VARCHAR(s.LAST_SYNCED_AT) AS SEC_LAST_SYNCED_AT,
        t.TICKERS,
        a.ADDRESSES,
        f.FORMER_NAMES,
        COALESCE(sr.SUBSIDIARY_EVIDENCE_COUNT, 0) AS SUBSIDIARY_EVIDENCE_COUNT,
        IFF(LOWER(COALESCE(s.ENTITY_TYPE, '')) = 'operating', TRUE, FALSE) AS IS_OPERATING,
        IFF(t.CIK IS NOT NULL, TRUE, FALSE) AS HAS_CANONICAL_TICKER,
        IFF(m.PARENT_COMPANY_ENTITY_ID IS NOT NULL OR COALESCE(sr.SUBSIDIARY_EVIDENCE_COUNT, 0) > 0,
            TRUE, FALSE) AS HAS_RELATIONSHIP_EVIDENCE
    FROM mdm_current m
    JOIN EDGARTOOLS_PROD.EDGARTOOLS_SILVER.SEC_COMPANY s ON s.CIK = m.CIK
    LEFT JOIN ticker_by_cik t ON t.CIK = m.CIK
    LEFT JOIN address_by_cik a ON a.CIK = m.CIK
    LEFT JOIN former_by_cik f ON f.CIK = m.CIK
    LEFT JOIN subsidiary_by_cik sr ON sr.CIK = m.CIK
    WHERE LOWER(COALESCE(s.ENTITY_TYPE, '')) = 'operating'
       OR t.CIK IS NOT NULL
)
SELECT 'meta' AS ROW_TYPE,
       OBJECT_CONSTRUCT_KEEP_NULL(
           'captured_at_utc', TO_VARCHAR(CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP())),
           'account', CURRENT_ACCOUNT(),
           'database', CURRENT_DATABASE(),
           'role', CURRENT_ROLE(),
           'warehouse', CURRENT_WAREHOUSE(),
           'query_version', 'gleif-company-cohort-v1'
       ) AS PAYLOAD
UNION ALL
SELECT 'ticker' AS ROW_TYPE,
       OBJECT_CONSTRUCT_KEEP_NULL(
           'cik', CIK,
           'ticker', TICKER,
           'exchange', EXCHANGE,
           'source_name', SOURCE_NAME,
           'source_rank', SOURCE_RANK,
           'last_sync_run_id', LAST_SYNC_RUN_ID,
           'last_synced_at', TO_VARCHAR(LAST_SYNCED_AT)
       ) AS PAYLOAD
FROM canonical_ticker_rows
UNION ALL
SELECT 'eligible' AS ROW_TYPE,
       OBJECT_CONSTRUCT_KEEP_NULL(
           'entity_id', ENTITY_ID,
           'cik', CIK,
           'canonical_name', CANONICAL_NAME,
           'ein', EIN,
           'sic_code', SIC_CODE,
           'sic_description', SIC_DESCRIPTION,
           'state_of_incorporation', STATE_OF_INCORPORATION,
           'fiscal_year_end', FISCAL_YEAR_END,
           'ticker', TICKER,
           'primary_ticker', PRIMARY_TICKER,
           'primary_exchange', PRIMARY_EXCHANGE,
           'tracking_status', TRACKING_STATUS,
           'parent_company_entity_id', PARENT_COMPANY_ENTITY_ID,
           'valid_from', TO_VARCHAR(VALID_FROM),
           'valid_to', TO_VARCHAR(VALID_TO),
           'sec_entity_name', SEC_ENTITY_NAME,
           'sec_entity_type', SEC_ENTITY_TYPE,
           'sec_sic', SEC_SIC,
           'sec_sic_description', SEC_SIC_DESCRIPTION,
           'sec_state_of_incorporation', SEC_STATE_OF_INCORPORATION,
           'sec_state_of_incorporation_desc', SEC_STATE_OF_INCORPORATION_DESC,
           'sec_fiscal_year_end', SEC_FISCAL_YEAR_END,
           'sec_ein', SEC_EIN,
           'sec_category', SEC_CATEGORY,
           'sec_first_sync_run_id', SEC_FIRST_SYNC_RUN_ID,
           'sec_last_sync_run_id', SEC_LAST_SYNC_RUN_ID,
           'sec_last_synced_at', SEC_LAST_SYNCED_AT,
           'tickers', COALESCE(TICKERS, ARRAY_CONSTRUCT()),
           'addresses', COALESCE(ADDRESSES, ARRAY_CONSTRUCT()),
           'former_names', COALESCE(FORMER_NAMES, ARRAY_CONSTRUCT()),
           'subsidiary_evidence_count', SUBSIDIARY_EVIDENCE_COUNT,
           'is_operating', IS_OPERATING,
           'has_canonical_ticker', HAS_CANONICAL_TICKER,
           'has_relationship_evidence', HAS_RELATIONSHIP_EVIDENCE
       ) AS PAYLOAD
FROM eligible
ORDER BY ROW_TYPE, PAYLOAD:cik::NUMBER, PAYLOAD:ticker::TEXT;
