# Data quality plan: tickers

Version **Trial A-tickers-quality-trial**. Each check's `on_fail`, and each fix, is a proposal: the operator decides each one.

| Check or fix | Engine | Reads | on_fail | Rows found |
|---|---|---|---|---|
| placeholder_ticker | placeholder@1 | fields.ticker | withhold | 1 |
| code_list_exchange | in_set@1 | fields.exchange | flag | 0 |

Examples per item are in the findings (`quality`), masked for a personal column.

## New code (log a ticket; not written)

| Check | Column | Rows | Notes |
|---|---|---|---|
| link_not_found | cik | 10391 | the value is a key of the part it points at (args.to) |
