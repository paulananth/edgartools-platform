# Data quality plan: product

Version **contoso-product-quality-trial**. Each check's `on_fail`, and each fix, is a proposal: the operator decides each one.

| Check or fix | Engine | Reads | on_fail | Rows found |
|---|---|---|---|---|
| code_list_manufacturer | in_set@1 | fields.manufacturer | flag | 0 |
| code_list_brand | in_set@1 | fields.brand | flag | 0 |
| code_list_color | in_set@1 | fields.color | flag | 0 |
| code_list_weight_unit | in_set@1 | fields.weight_unit | flag | 0 |
| code_list_category_key | in_set@1 | fields.category_key | flag | 0 |
| code_list_sub_category_key | in_set@1 | fields.sub_category_key | flag | 0 |

Examples per item are in the findings (`quality`), masked for a personal column.
