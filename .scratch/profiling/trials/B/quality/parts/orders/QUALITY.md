# Data quality plan: orders

Version **contoso-orders-quality-trial**. Each check's `on_fail`, and each fix, is a proposal: the operator decides each one.

| Check or fix | Engine | Reads | on_fail | Rows found |
|---|---|---|---|---|
| code_list_currency_code | in_set@1 | fields.currency_code | flag | 0 |

Examples per item are in the findings (`quality`), masked for a personal column.
