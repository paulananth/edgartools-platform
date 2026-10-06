# Data quality plan: lei2.Extension.gleif:Geocoding

Version **Trial A-lei2.Extension.gleif:Geocoding-quality-trial**. Each check's `on_fail`, and each fix, is a proposal: the operator decides each one.

| Check or fix | Engine | Reads | on_fail | Rows found |
|---|---|---|---|---|
| placeholder_gleif_relevance | placeholder@1 | fields.gleif_relevance | withhold | 571 |
| placeholder_gleif_lat | placeholder@1 | fields.gleif_lat | withhold | 571 |
| placeholder_gleif_lng | placeholder@1 | fields.gleif_lng | withhold | 571 |
| placeholder_gleif_mapped_city | placeholder@1 | fields.gleif_mapped_city | withhold | 1 |
| code_list_gleif_match_type | in_set@1 | fields.gleif_match_type | flag | 0 |
| code_list_gleif_match_level | in_set@1 | fields.gleif_match_level | flag | 0 |
| code_list_gleif_geocoding_failed | in_set@1 | fields.gleif_geocoding_failed | flag | 0 |

Examples per item are in the findings (`quality`), masked for a personal column.

## New code (log a ticket; not written)

| Check | Column | Rows | Notes |
|---|---|---|---|
| no_natural_key | None | 0 | the designed record key is filled and unique |
| hierarchy_invalid | gleif:match_level | 301 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
