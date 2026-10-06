# Data quality plan: submissions.filings.recent

Version **Trial A-submissions.filings.recent-quality-trial**. Each check's `on_fail`, and each fix, is a proposal: the operator decides each one.

| Check or fix | Engine | Reads | on_fail | Rows found |
|---|---|---|---|---|
| placeholder_file_number | placeholder@1 | fields.file_number | withhold | 48 |
| placeholder_film_number | placeholder@1 | fields.film_number | withhold | 276 |
| placeholder_primary_doc_description | placeholder@1 | fields.primary_doc_description | withhold | 7627 |
| code_list_act | in_set@1 | fields.act | flag | 0 |
| code_list_is_xbrl | in_set@1 | fields.is_xbrl | flag | 0 |
| code_list_is_inline_xbrl | in_set@1 | fields.is_inline_xbrl | flag | 0 |
| code_list_is_xbrlnumeric | in_set@1 | fields.is_xbrlnumeric | flag | 0 |

Examples per item are in the findings (`quality`), masked for a personal column.

## New code (log a ticket; not written)

| Check | Column | Rows | Notes |
|---|---|---|---|
| hierarchy_invalid | isXBRLNumeric | 987 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
