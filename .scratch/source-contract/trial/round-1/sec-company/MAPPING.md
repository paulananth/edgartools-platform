# Mapping Document — `sec.company_profile` vtrial-1

Generated from `contract.yaml` (digest `f9e1182a6181`). Do not edit by hand.

## `sec_company_profile`  (one row per `.`)

| Silver column | Type | From the Bronze Artifact | Into MDM |
|---|---|---|---|
| `cik` | string | `text` `cik` | identifier `sec_cik` |
| `name` | string | `text` `name` | field `name` |
| `entity_type` | string | `text` `entityType` | identity kind |
| `sic` | string? | `text` `sic` → `empty_to_null` | field `sic` |
| `sic_description` | string? | `text` `sicDescription` → `empty_to_null` | evidence only |
| `state_of_incorporation` | string? | `text` `stateOfIncorporation` → `empty_to_null` | field `state_of_incorporation` |
| `fiscal_year_end` | string? | `text` `fiscalYearEnd` | field `fiscal_year_end` |
| `tickers` | string? | `join` `tickers` | field `tickers` |
| `exchanges` | string? | `join` `exchanges` | evidence only |
| `ticker_count` | bigint | `count` `tickers` | evidence only |
| `exchange_count` | bigint | `count` `exchanges` | evidence only |
| `business_city` | string? | `text` `addresses.business.city` → `empty_to_null` | evidence only |
| `business_state` | string? | `text` `addresses.business.stateOrCountry` → `empty_to_null` | evidence only |
| `former_names` | string? | `join` `formerNames` | evidence only |
| `former_name_count` | bigint | `count` `formerNames` | evidence only |

**MDM kind:** from `entity_type`.  **Custom:** 0 of 15 columns (0.0%).
