# Data quality plan: lei2

Version **Trial A-lei2-quality-trial**. Each check's `on_fail`, and each fix, is a proposal: the operator decides each one.

| Check or fix | Engine | Reads | on_fail | Rows found |
|---|---|---|---|---|
| placeholder_entity_legal_address_city | placeholder@1 | fields.entity_legal_address_city | withhold | 36 |
| placeholder_entity_legal_address_postal_code | placeholder@1 | fields.entity_legal_address_postal_code | withhold | 12 |
| placeholder_entity_headquarters_address_city | placeholder@1 | fields.entity_headquarters_address_city | withhold | 36 |
| placeholder_entity_headquarters_address_postal_code | placeholder@1 | fields.entity_headquarters_address_postal_code | withhold | 13 |
| placeholder_entity_entity_status | placeholder@1 | fields.entity_entity_status | withhold | 275 |
| placeholder_registration_validation_authority_validation_authority_entity_id | placeholder@1 | fields.registration_validation_authority_validation_authority_entity_id | withhold | 4 |
| placeholder_extension_gleif_conformity_gleif_conformityflag | placeholder@1 | fields.extension_gleif_conformity_gleif_conformityflag | withhold | 7521 |
| placeholder_entity_legal_address_address_number | placeholder@1 | fields.entity_legal_address_address_number | withhold | 19 |
| placeholder_entity_headquarters_address_address_number | placeholder@1 | fields.entity_headquarters_address_address_number | withhold | 18 |
| placeholder_extension_leifr_economic_activity_leifr_naceclass_code | placeholder@1 | fields.extension_leifr_economic_activity_leifr_naceclass_code | withhold | 6 |
| placeholder_entity_legal_address_address_number_within_building | placeholder@1 | fields.entity_legal_address_address_number_within_building | withhold | 11 |
| placeholder_entity_headquarters_address_address_number_within_building | placeholder@1 | fields.entity_headquarters_address_address_number_within_building | withhold | 15 |
| shape_outlier_extension_leifr_fund_number | pattern@1 | fields.extension_leifr_fund_number | flag | 1 |
| shape_outlier_extension_ext_cif | pattern@1 | fields.extension_ext_cif | flag | 65 |
| check_digit_lei | lei_check_digit@1 | fields.lei | withhold | 8 |
| code_list_entity_entity_category | in_set@1 | fields.entity_entity_category | flag | 0 |
| code_list_entity_entity_status | in_set@1 | fields.entity_entity_status | flag | 0 |
| code_list_registration_registration_status | in_set@1 | fields.registration_registration_status | flag | 0 |
| code_list_registration_managing_lou | in_set@1 | fields.registration_managing_lou | flag | 0 |
| code_list_registration_validation_sources | in_set@1 | fields.registration_validation_sources | flag | 0 |
| code_list_extension_gleif_conformity_gleif_conformityflag | in_set@1 | fields.extension_gleif_conformity_gleif_conformityflag | flag | 0 |
| code_list_extension_leifr_legal_form_codification | in_set@1 | fields.extension_leifr_legal_form_codification | flag | 0 |
| code_list_entity_entity_sub_category | in_set@1 | fields.entity_entity_sub_category | flag | 0 |

Examples per item are in the findings (`quality`), masked for a personal column.

## New code (log a ticket; not written)

| Check | Column | Rows | Notes |
|---|---|---|---|
| hierarchy_invalid | Entity.LegalAddress.Country | 1 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
| hierarchy_invalid | Entity.HeadquartersAddress.Country | 2 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
| hierarchy_invalid | Entity.EntityCategory | 2 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
| hierarchy_invalid | Entity.RegistrationAuthority.RegistrationAuthorityID | 464 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
| hierarchy_invalid | Entity.LegalAddress.Country | 205 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
| hierarchy_invalid | Entity.LegalAddress.@xml:lang | 359 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
| hierarchy_invalid | Entity.EntityStatus | 22 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
| hierarchy_invalid | Entity.EntityStatus | 1 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
