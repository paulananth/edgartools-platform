-- Canonical accession-level authority for year-based S3 artifact retention.
-- Read-only: this query does not mutate Snowflake or AWS.
--
-- The mixed Bronze filing prefix does not encode form type. This query binds
-- each accession to canonical Snowflake Silver form/date/items and every known
-- Bronze filing/text object key. COMPLETE is false when an attachment lacks a
-- raw-object registration; the retention planner rejects incomplete bundles.

WITH filing AS (
  SELECT
    accession_number,
    cik,
    form,
    filing_date,
    REGEXP_LIKE(COALESCE(items, ''), '(^|[, ]+)5\\.02([, ]+|$)') AS item_502,
    form IN ('ADV', 'ADV/A')
      AND ROW_NUMBER() OVER (
        PARTITION BY cik, IFF(form IN ('ADV', 'ADV/A'), 'ADV', form)
        ORDER BY filing_date DESC, accession_number DESC
      ) = 1 AS retain_current
  FROM EDGARTOOLS_PROD.EDGARTOOLS_SILVER.SEC_COMPANY_FILING
),
raw_objects AS (
  SELECT DISTINCT
    raw_object_id,
    accession_number,
    REGEXP_REPLACE(storage_path, '^s3://[^/]+/', '') AS object_key
  FROM EDGARTOOLS_PROD.EDGARTOOLS_SILVER.SEC_RAW_OBJECT
  WHERE accession_number IS NOT NULL
    AND (
      storage_path LIKE 's3://%/warehouse/bronze/filings/%'
      OR storage_path LIKE 's3://%/warehouse/bronze/text/%'
    )
),
text_paths AS (
  SELECT DISTINCT
    accession_number,
    REGEXP_REPLACE(text_storage_path, '^s3://[^/]+/', '') AS object_key
  FROM EDGARTOOLS_PROD.EDGARTOOLS_SILVER.SEC_FILING_TEXT
  WHERE accession_number IS NOT NULL
    AND text_storage_path LIKE 's3://%/warehouse/bronze/text/%'
),
all_paths AS (
  SELECT accession_number, object_key FROM raw_objects
  UNION
  SELECT * FROM text_paths
),
attachment_completeness AS (
  SELECT
    attachment.accession_number,
    COUNT(*) AS attachment_count,
    COUNT_IF(attachment.is_primary) AS primary_attachment_count,
    COUNT_IF(raw.raw_object_id IS NULL) AS missing_raw_object_count
  FROM EDGARTOOLS_PROD.EDGARTOOLS_SILVER.SEC_FILING_ATTACHMENT AS attachment
  LEFT JOIN EDGARTOOLS_PROD.EDGARTOOLS_SILVER.SEC_RAW_OBJECT AS raw
    ON raw.raw_object_id = attachment.raw_object_id
  GROUP BY attachment.accession_number
),
cross_accession_reference_rows AS (
  SELECT DISTINCT
    raw.accession_number AS owner_accession_number,
    attachment.accession_number AS reference_accession_number,
    reference.form,
    reference.filing_date,
    reference.item_502,
    reference.retain_current
  FROM EDGARTOOLS_PROD.EDGARTOOLS_SILVER.SEC_FILING_ATTACHMENT AS attachment
  JOIN raw_objects AS raw
    ON raw.raw_object_id = attachment.raw_object_id
  LEFT JOIN filing AS reference
    ON reference.accession_number = attachment.accession_number
  WHERE raw.accession_number IS NOT NULL
    AND attachment.accession_number <> raw.accession_number
),
cross_accession_references AS (
  SELECT
    owner_accession_number,
    ARRAY_AGG(
      OBJECT_CONSTRUCT_KEEP_NULL(
        'accession_number', reference_accession_number,
        'form', form,
        'filing_date', filing_date,
        'item_502', item_502,
        'retain_current', retain_current
      )
    ) WITHIN GROUP (ORDER BY reference_accession_number) AS retention_references
  FROM cross_accession_reference_rows
  GROUP BY owner_accession_number
)
SELECT
  filing.accession_number,
  filing.form,
  filing.filing_date,
  filing.item_502,
  filing.retain_current,
  COALESCE(completeness.attachment_count, 0) > 0
    AND COALESCE(completeness.primary_attachment_count, 0) > 0
    AND COALESCE(completeness.missing_raw_object_count, 0) = 0
    AND COUNT_IF(paths.object_key LIKE 'warehouse/bronze/text/%') > 0
    AS complete,
  COALESCE(
    ANY_VALUE(references.retention_references),
    ARRAY_CONSTRUCT()
  ) AS retention_references,
  ARRAY_AGG(DISTINCT paths.object_key) WITHIN GROUP (ORDER BY paths.object_key) AS object_keys
FROM filing
LEFT JOIN all_paths AS paths
  ON paths.accession_number = filing.accession_number
LEFT JOIN attachment_completeness AS completeness
  ON completeness.accession_number = filing.accession_number
LEFT JOIN cross_accession_references AS references
  ON references.owner_accession_number = filing.accession_number
WHERE filing.form IN (
  '13F-HR', '13F-HR/A',
  'DEF 14A', 'DEF 14A/A', 'DEFA14A', 'PRE 14A',
  '3', '3/A', '4', '4/A', '5', '5/A',
  '8-K', '8-K/A', 'ADV', 'ADV/A'
)
GROUP BY
  filing.accession_number,
  filing.form,
  filing.filing_date,
  filing.item_502,
  filing.retain_current,
  completeness.attachment_count,
  completeness.primary_attachment_count,
  completeness.missing_raw_object_count
ORDER BY filing.accession_number;
