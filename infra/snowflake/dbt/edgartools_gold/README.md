# EdgarTools dbt Gold Project

This project owns the business-facing gold mirror for Snowflake and Databricks.

## Ownership

This project owns:

- curated business-facing gold models
- Snowflake dynamic tables and Databricks tables/views
- tests on gold-facing objects
- the `EDGARTOOLS_GOLD_STATUS` view

It does not own:

- Snowflake platform objects created by Terraform
- storage integrations, Unity Catalog external locations, stages, source-side procedures, or tasks created by infrastructure automation

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

On Snowflake, the nine business tables are dbt-managed dynamic tables with
`TARGET_LAG = DOWNSTREAM`. On Databricks, the same models materialize as tables by
default through `dbt-databricks`; set `DBT_DATABRICKS_GOLD_MATERIALIZED=view` to
use views during development.

The status model now reads the provider-neutral source name `SERVING_REFRESH_STATUS`.
For Snowflake compatibility, `profiles.yml.example` defaults its physical identifier to
`SNOWFLAKE_REFRESH_STATUS`; set `DBT_REFRESH_STATUS_IDENTIFIER` when Databricks uses a
different source table name.
