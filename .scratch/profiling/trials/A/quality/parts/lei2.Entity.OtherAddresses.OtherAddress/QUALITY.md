# Data quality plan: lei2.Entity.OtherAddresses.OtherAddress

Version **Trial A-lei2.Entity.OtherAddresses.OtherAddress-quality-trial**. Each check's `on_fail`, and each fix, is a proposal: the operator decides each one.

| Check or fix | Engine | Reads | on_fail | Rows found |
|---|---|---|---|---|
| placeholder_postal_code | placeholder@1 | fields.postal_code | withhold | 1 |
| code_list_xml_lang | in_set@1 | fields.xml_lang | flag | 0 |
| code_list_country | in_set@1 | fields.country | flag | 0 |

Examples per item are in the findings (`quality`), masked for a personal column.
