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

## Answer

Resolved 2026-09-13 in code; live verification still owed.

- `merge_thirteenf_holdings` and `merge_thirteenf_filings` now call
  `_record_landing_passthrough` with `stamp=self._ingested_at_stamp()`. Their
  `@track_landing_rows` decorators, `_merge_rows` SQL and `values_fn` lambdas are gone. The
  passthrough records to `landing_export` itself, so keeping the decorator would record every
  row twice. DuckDB DDL kept (the helper reads its NOT NULL set).
- Old `values_fn` behaviour kept. `bool(confidential_omission)` is applied at the call site,
  since it replaces a present value. `effective_status` defaults to `"effective"` and
  `parser_version` to `"1"`, filled only when the key is absent. Every old `r["key"]` lookup
  is a NOT NULL column, so a missing one now raises `ValueError` before recording (was
  `KeyError`/DuckDB constraint error).
- **A real fix, not just parity:** same finding as Ticket 04. `@track_landing_rows` recorded
  raw rows with no `ingested_at`, and MDM's INSTITUTIONAL_HOLDS derivation filters
  `sec_thirteenf_holding` on `h.ingested_at > ?` (`pipeline.py`), so new holdings were
  invisible to its incremental watermark.
- **Collapse keys verified:** the dbt silver models partition on the old `ON CONFLICT` keys,
  `(cik, accession_number, holding_index)` and `(accession_number)`. Columns the old
  `DO UPDATE SET` never touched are first-insert-wins in DuckDB but last-seen in dbt:
  - holdings: `period_of_report`, `cusip`, `issuer_name`, `security_title`, `put_call`,
    `discretion_type`, `voting_auth_sole`/`_shared`/`_none`;
  - filings: `cik`, `period_of_report`, `filing_date`, `form`.

  This split already existed (landing received every raw write and dbt took the latest); it
  is not introduced here.
- **Volume check** (local, synthetic holdings rows):

  | Rows | Passthrough (record) | Flush (`from_pylist` + Parquet) |
  |---|---|---|
  | 20,000 | 0.12 s, +10 MB peak | 0.36 s, +13 MB peak |
  | 100,000 | 0.53 s, +48 MB peak | 1.43 s, +61 MB peak |
  | 1,000,000 | — | ~7.2 s `from_pylist` alone (Spec review's measurement) |

  The old per-row DuckDB INSERT path took about 156 s to run the same 20k-row test. The flush
  cost is not new: `@track_landing_rows` already buffered these rows and the same
  `write_landing_export` flush converted them. The buffer holds copies with one extra key
  instead of the caller's dicts, and the local DuckDB table no longer grows, so there is no
  net new memory pressure.
- `run_bootstrap_thirteenf`'s marker comment rewritten: it referred to per-row autocommit and
  `ON CONFLICT` repair, neither of which exists now.
- Tests: 13F cases in `test_fundamentals_landing_passthrough.py` (landing-only + `ingested_at`
  and `ingested_at` advancing, now one parametrized pair shared with the per-filing tables;
  the old coercions and defaults; NOT NULL raising; a 20k-row batch making at most one DuckDB
  call). `test_silver_store_ingested_at_bump.py` deleted — every table it covered is now
  landing-only. The ShardedSilverReader and MDM real-silver-schema tests seed through
  `tests/support/silver_rows.py` instead of the now landing-only writers.

**Still owed:** a live prod `bootstrap-fundamentals --mode thirteenf` run on a large filer,
reporting landing row counts with `ingested_at` populated plus flush time and peak memory.
