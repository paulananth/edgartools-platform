# EdgarTools Snowflake dbt Project

This project owns the business-facing Snowflake gold mirror.

## Ownership

This project owns:

- curated business-facing gold models
- Snowflake dynamic tables
- tests on gold-facing objects
- the `EDGARTOOLS_GOLD_STATUS` view

It does not own:

- Snowflake platform objects created by Terraform
- storage integrations, stages, or procedures created by SnowCLI bootstrap SQL

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
- `EDGARTOOLS_GOLD_STATUS`

All eight business tables are dbt-managed Snowflake dynamic tables with `TARGET_LAG = DOWNSTREAM`.
The Snowflake bootstrap wrapper triggers and waits for these dynamic tables before marking a run
successful in `EDGARTOOLS_SOURCE.SNOWFLAKE_REFRESH_STATUS`.
