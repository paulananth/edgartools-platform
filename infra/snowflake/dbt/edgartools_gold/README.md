# EdgarTools dbt Gold Project

This project owns the business-facing gold mirror for Snowflake.

## Ownership

This project owns:

- curated business-facing gold models
- Snowflake dynamic tables
- tests on gold-facing objects
- the `EDGARTOOLS_GOLD_STATUS` view

It does not own:

- Snowflake platform objects created by Terraform
- storage integrations, stages, source-side procedures, or tasks created by infrastructure automation

## Current scope

The project publishes these objects in `EDGARTOOLS_GOLD`:

- `COMPANY`
- `FILING_ACTIVITY`
- `OWNERSHIP_ACTIVITY`
- `OWNERSHIP_HOLDINGS`
- `ADVISER_OFFICES`
- `ADVISER_DISCLOSURES`
- `PRIVATE_FUNDS`
- `FILING_DETAIL`
- `TICKER_REFERENCE`
- `EDGARTOOLS_GOLD_STATUS`

The nine business tables are dbt-managed Snowflake dynamic tables with
`TARGET_LAG = DOWNSTREAM`.

The status model reads the source name `SERVING_REFRESH_STATUS`.
`profiles.yml.example` defaults its physical identifier to
`SNOWFLAKE_REFRESH_STATUS`; set `DBT_REFRESH_STATUS_IDENTIFIER` only when the
physical Snowflake source table name differs.
