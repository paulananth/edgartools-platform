# Data quality plan: customer

Version **contoso-customer-quality-trial**. Each check's `on_fail`, and each fix, is a proposal: the operator decides each one.

| Check or fix | Engine | Reads | on_fail | Rows found |
|---|---|---|---|---|
| placeholder_given_name | placeholder@1 | fields.given_name | withhold | 3 |
| placeholder_middle_initial | placeholder@1 | fields.middle_initial | withhold | 1 |
| shape_outlier_middle_initial | pattern@1 | fields.middle_initial | flag | 126 |
| code_list_continent | in_set@1 | fields.continent | flag | 0 |
| code_list_country | in_set@1 | fields.country | flag | 0 |

Examples per item are in the findings (`quality`), masked for a personal column.

## New code (log a ticket; not written)

| Check | Column | Rows | Notes |
|---|---|---|---|
| hierarchy_invalid | State | 4 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
