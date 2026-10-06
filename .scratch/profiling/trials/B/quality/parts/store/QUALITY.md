# Data quality plan: store

Version **contoso-store-quality-trial**. Each check's `on_fail`, and each fix, is a proposal: the operator decides each one.

| Check or fix | Engine | Reads | on_fail | Rows found |
|---|---|---|---|---|
| code_list_country_code | in_set@1 | fields.country_code | flag | 0 |
| code_list_square_meters | in_set@1 | fields.square_meters | flag | 0 |
| code_list_status | in_set@1 | fields.status | flag | 0 |

Examples per item are in the findings (`quality`), masked for a personal column.
