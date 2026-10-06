# Data quality plan: submissions

Version **Trial A-submissions-quality-trial**. Each check's `on_fail`, and each fix, is a proposal: the operator decides each one.

| Check or fix | Engine | Reads | on_fail | Rows found |
|---|---|---|---|---|
| placeholder_sic | placeholder@1 | fields.sic | withhold | 38 |
| placeholder_ein | placeholder@1 | fields.ein | withhold | 15061 |
| placeholder_lei | placeholder@1 | fields.lei | withhold | 1 |
| placeholder_addresses_mailing_street | placeholder@1 | fields.addresses_mailing_street | withhold | 3 |
| placeholder_addresses_mailing_city | placeholder@1 | fields.addresses_mailing_city | withhold | 1 |
| placeholder_addresses_mailing_zip_code | placeholder@1 | fields.addresses_mailing_zip_code | withhold | 953 |
| placeholder_addresses_mailing_foreign_state_territory | placeholder@1 | fields.addresses_mailing_foreign_state_territory | withhold | 1 |
| placeholder_addresses_mailing_country | placeholder@1 | fields.addresses_mailing_country | withhold | 2 |
| placeholder_addresses_business_street | placeholder@1 | fields.addresses_business_street | withhold | 2 |
| placeholder_addresses_business_zip_code | placeholder@1 | fields.addresses_business_zip_code | withhold | 528 |
| placeholder_addresses_business_foreign_state_territory | placeholder@1 | fields.addresses_business_foreign_state_territory | withhold | 2 |
| placeholder_addresses_business_country | placeholder@1 | fields.addresses_business_country | withhold | 1 |
| placeholder_phone | placeholder@1 | fields.phone | withhold | 69 |
| shape_outlier_ein | pattern@1 | fields.ein | flag | 2 |
| code_list_entity_type | in_set@1 | fields.entity_type | flag | 0 |
| code_list_owner_org | in_set@1 | fields.owner_org | flag | 0 |
| code_list_insider_transaction_for_owner_exists | in_set@1 | fields.insider_transaction_for_owner_exists | flag | 0 |
| code_list_insider_transaction_for_issuer_exists | in_set@1 | fields.insider_transaction_for_issuer_exists | flag | 0 |
| code_list_category | in_set@1 | fields.category | flag | 0 |
| code_list_addresses_mailing_is_foreign_location | in_set@1 | fields.addresses_mailing_is_foreign_location | flag | 0 |
| code_list_flags | in_set@1 | fields.flags | flag | 0 |

Examples per item are in the findings (`quality`), masked for a personal column.

## New code (log a ticket; not written)

| Check | Column | Rows | Notes |
|---|---|---|---|
| hierarchy_invalid | flags | 310 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
| hierarchy_invalid | flags | 13 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
| hierarchy_invalid | flags | 12 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
| hierarchy_invalid | addresses.mailing.isForeignLocation | 5 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
| hierarchy_invalid | flags | 13 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
| hierarchy_invalid | flags | 13 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
| hierarchy_invalid | flags | 13 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
