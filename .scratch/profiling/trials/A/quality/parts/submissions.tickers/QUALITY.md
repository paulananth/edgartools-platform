# Data quality plan: submissions.tickers

Version **Trial A-submissions.tickers-quality-trial**. Each check's `on_fail`, and each fix, is a proposal: the operator decides each one.

| Check or fix | Engine | Reads | on_fail | Rows found |
|---|---|---|---|---|

Examples per item are in the findings (`quality`), masked for a personal column.

## New code (log a ticket; not written)

| Check | Column | Rows | Notes |
|---|---|---|---|
| link_not_found | value | 460 | the value is a key of the part it points at (args.to) |
