# Mapping Document — `gleif.level1` vprototype-1

Generated from `contract.yaml` (digest `ec3155bbc0ce`). Do not edit by hand.

## `gleif_lei_record`  (one row per `.`)

| Silver column | Type | From the Bronze Artifact | Into MDM |
|---|---|---|---|
| `lei` | string | `text` `LEI.$` | identifier `lei` |
| `legal_name` | string | `text` `Entity.LegalName.$` | field `name` |
| `legal_name_language` | string? | `text` `Entity.LegalName.@xml:lang` | evidence only |
| `legal_jurisdiction` | string? | `text` `Entity.LegalJurisdiction.$` | field `jurisdiction` |
| `entity_category` | string? | `text` `Entity.EntityCategory.$` | evidence only |
| `entity_status` | string? | `text` `Entity.EntityStatus.$` | evidence only |
| `legal_form_code` | string? | `text` `Entity.LegalForm.EntityLegalFormCode.$` | evidence only |
| `legal_address_line1` | string? | `text` `Entity.LegalAddress.FirstAddressLine.$` | evidence only |
| `legal_address_more` | string? | `join` `Entity.LegalAddress.AdditionalAddressLine` | evidence only |
| `legal_city` | string? | `text` `Entity.LegalAddress.City.$` | evidence only |
| `legal_region` | string? | `text` `Entity.LegalAddress.Region.$` | evidence only |
| `legal_country` | string? | `text` `Entity.LegalAddress.Country.$` | field `country` |
| `hq_country` | string? | `text` `Entity.HeadquartersAddress.Country.$` | evidence only |
| `registration_status` | string? | `text` `Registration.RegistrationStatus.$` | evidence only |
| `initial_registration` | timestamp? | `timestamp` `Registration.InitialRegistrationDate.$` | evidence only |
| `last_update` | timestamp? | `timestamp` `Registration.LastUpdateDate.$` | evidence only |
| `managing_lou` | string? | `text` `Registration.ManagingLOU.$` | evidence only |

**MDM kind:** company.  **Custom:** 0 of 17 columns (0.0%).
