# 05 — Make the 13F tables landing-only

**Type:** task

## Question

`bootstrap-fundamentals --mode thirteenf` writes `sec_thirteenf_holding` and
`sec_thirteenf_filing` via DuckDB `merge_*` with no in-process reader (confirmed 2026-09-13).
Same shape as [Ticket 04](04-per-filing-tables-landing-only.md); split out because 13F holdings
are the platform's highest-volume table (6.8M rows in prod) — the passthrough's per-row Python
loop and `pa.Table.from_pylist` should be checked against a real 13F-HR payload size before
shipping, not assumed fine from the smaller tables.

**Done:** as Ticket 04, plus a live prod thirteenf run on a large filer.

**Blocked by:** [Ticket 04](04-per-filing-tables-landing-only.md) (proves the shape on
smaller tables first).
