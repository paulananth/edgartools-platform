-- Unity Catalog registration template for the Azure/Databricks parallel run.
-- Replace bracketed placeholders before running in a Databricks SQL warehouse.

CREATE CATALOG IF NOT EXISTS [CATALOG_NAME];
CREATE SCHEMA IF NOT EXISTS [CATALOG_NAME].[SOURCE_SCHEMA];

CREATE EXTERNAL LOCATION IF NOT EXISTS edgartools_serving_exports
URL 'abfss://serving@[STORAGE_ACCOUNT].dfs.core.windows.net/warehouse/serving_exports'
WITH (STORAGE CREDENTIAL [STORAGE_CREDENTIAL_NAME]);

CREATE TABLE IF NOT EXISTS [CATALOG_NAME].[SOURCE_SCHEMA].COMPANY
USING PARQUET
LOCATION 'abfss://serving@[STORAGE_ACCOUNT].dfs.core.windows.net/warehouse/serving_exports/company';

CREATE TABLE IF NOT EXISTS [CATALOG_NAME].[SOURCE_SCHEMA].FILING_ACTIVITY
USING PARQUET
LOCATION 'abfss://serving@[STORAGE_ACCOUNT].dfs.core.windows.net/warehouse/serving_exports/filing_activity';

CREATE TABLE IF NOT EXISTS [CATALOG_NAME].[SOURCE_SCHEMA].OWNERSHIP_ACTIVITY
USING PARQUET
LOCATION 'abfss://serving@[STORAGE_ACCOUNT].dfs.core.windows.net/warehouse/serving_exports/ownership_activity';

CREATE TABLE IF NOT EXISTS [CATALOG_NAME].[SOURCE_SCHEMA].OWNERSHIP_HOLDINGS
USING PARQUET
LOCATION 'abfss://serving@[STORAGE_ACCOUNT].dfs.core.windows.net/warehouse/serving_exports/ownership_holdings';

CREATE TABLE IF NOT EXISTS [CATALOG_NAME].[SOURCE_SCHEMA].ADVISER_OFFICES
USING PARQUET
LOCATION 'abfss://serving@[STORAGE_ACCOUNT].dfs.core.windows.net/warehouse/serving_exports/adviser_offices';

CREATE TABLE IF NOT EXISTS [CATALOG_NAME].[SOURCE_SCHEMA].ADVISER_DISCLOSURES
USING PARQUET
LOCATION 'abfss://serving@[STORAGE_ACCOUNT].dfs.core.windows.net/warehouse/serving_exports/adviser_disclosures';

CREATE TABLE IF NOT EXISTS [CATALOG_NAME].[SOURCE_SCHEMA].PRIVATE_FUNDS
USING PARQUET
LOCATION 'abfss://serving@[STORAGE_ACCOUNT].dfs.core.windows.net/warehouse/serving_exports/private_funds';

CREATE TABLE IF NOT EXISTS [CATALOG_NAME].[SOURCE_SCHEMA].FILING_DETAIL
USING PARQUET
LOCATION 'abfss://serving@[STORAGE_ACCOUNT].dfs.core.windows.net/warehouse/serving_exports/filing_detail';

CREATE TABLE IF NOT EXISTS [CATALOG_NAME].[SOURCE_SCHEMA].TICKER_REFERENCE
USING PARQUET
LOCATION 'abfss://serving@[STORAGE_ACCOUNT].dfs.core.windows.net/warehouse/serving_exports/ticker_reference';
