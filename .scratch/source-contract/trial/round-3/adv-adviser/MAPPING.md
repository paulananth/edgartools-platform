# Mapping Document — `iapd.adv_adviser` v1

Generated from `contract.yaml` (digest `b7c2c8de7e3e`). Do not edit by hand.

## `iapd_adv_filing`  (one row per `.`)

| Silver column | Type | From the Bronze Artifact | Into MDM |
|---|---|---|---|
| `filing_id` | string | `text` `filing_id` | evidence only |
| `date_submitted_raw` | string | `text` `date_submitted` | evidence only |
| `submitted_date` | date | **custom** `adv_submitted_date@1` | evidence only |
| `crd` | string | `text` `crd` | identifier `crd` |
| `sec_file_number` | string? | `text` `sec_file_number` → `empty_to_null` | evidence only |
| `legal_name` | string | `text` `legal_name` | field `name` — **evidence only**: the Mastering Policy gives `iapd.adv_adviser` no rank for it |
| `business_name` | string? | `text` `business_name` → `empty_to_null` | evidence only |
| `office_city` | string? | `text` `office_city` → `empty_to_null` | evidence only |
| `office_state` | string? | `text` `office_state` → `empty_to_null` | evidence only |
| `office_country_name` | string? | `text` `office_country` → `empty_to_null` | evidence only |
| `office_is_residence` | boolean | `flag` `office_private` | evidence only |
| `is_public_reporting` | boolean | `flag` `public_reporting` | evidence only |
| `public_reporting_cik` | string? | `text` `public_reporting_cik` → `empty_to_null` | evidence only |
| `reports_raum` | boolean | `flag` `has_raum` | evidence only |
| `raum_total_usd` | bigint? | `int` `raum_total` | evidence only |

**MDM kind:** company.  **Custom:** 1 of 15 columns (6.7%).
