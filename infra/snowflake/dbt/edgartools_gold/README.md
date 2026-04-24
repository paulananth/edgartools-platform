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
- storage integrations, stages, source-side procedures, or tasks created by the Terraform-managed native-pull layer

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

All nine business tables are dbt-managed Snowflake dynamic tables with `TARGET_LAG = DOWNSTREAM`.
The deployment wrapper triggers and waits for these dynamic tables before marking a run
successful in `EDGARTOOLS_SOURCE.SNOWFLAKE_REFRESH_STATUS`.
