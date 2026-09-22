# Mapping Document — `sec.company_profile` vtrial-1

Generated from `contract.yaml` (digest `e05fd40e0dfa`). Do not edit by hand.

## `sec_company_profile`  (one row per `.`)

| Silver column | Type | From the Bronze Artifact | Into MDM |
|---|---|---|---|
| `cik` | string | `text` `cik` | identifier `cik` |
| `name` | string | `text` `name` | field `name` — **evidence only**: the Mastering Policy gives `sec.company_profile` no rank for it |
| `entity_type` | string | `text` `entityType` | identity kind |
| `sic` | string? | `text` `sic` → `empty_to_null` | evidence only |
| `sic_description` | string? | `text` `sicDescription` → `empty_to_null` | evidence only |
| `state_of_incorporation` | string? | `text` `stateOfIncorporation` → `empty_to_null` | evidence only |
| `fiscal_year_end` | string? | `text` `fiscalYearEnd` → `empty_to_null` | evidence only |
| `tickers` | string? | `join` `tickers` | evidence only |
| `exchanges` | string? | `join` `exchanges` | evidence only |
| `ticker_count` | bigint | `count` `tickers` | evidence only |
| `business_city` | string? | `text` `addresses.business.city` → `empty_to_null` | evidence only |
| `business_state` | string? | `text` `addresses.business.stateOrCountry` → `empty_to_null` | evidence only |
| `former_names` | string? | `join` `formerNames` | evidence only |
| `former_name_count` | bigint | `count` `formerNames` | evidence only |

## `sec_company_former_name`  (one row per `formerNames`)

| Silver column | Type | From the Bronze Artifact | Into MDM |
|---|---|---|---|
| `cik` | string | `text` `cik` | — |
| `name_index` | bigint | `ordinal` | — |
| `former_name` | string | `text` `name` | — |
| `valid_from` | timestamp? | `timestamp` `from` | — |
| `valid_to` | timestamp? | `timestamp` `to` | — |

**MDM kind:** from `entity_type`.  **Custom:** 0 of 19 columns (0.0%).
