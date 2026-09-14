# 11 — Restore release-mode Branch B same-run reads

**Type:** grilling

**Status:** open

## Question

Ticket 06d made `sec_company_filing`, `sec_filing_attachment` and `sec_raw_object` landing-only.
Same-run reads through `get_filing`/`get_filing_attachments`/`get_raw_object` answer from the
in-run lookup ([ADR 0011](../../../docs/adr/0011-same-run-silver-reads-from-recorded-rows.md)), but
raw SQL on the local store now finds nothing.

`bootstrap-batch --release-mode` (the `one_click_data_refresh` strict candidate-manifest Map)
captures submissions and artifacts, then `_run_release_branch_b_parsers` passes the local
`SilverDatabase` as `source` to `run_bootstrap_fundamentals_per_filing` and
`run_bootstrap_thirteenf`. Those query the three tables with raw SQL
(`fundamentals_ingest.py`: `cik IN ... AND form IN ...` on filings, then attachments and raw
objects by key). Before 06d they saw this run's rows in local DuckDB; after 06d they fail closed
with "required candidates missing from filing manifest". Found during 06d implementation, not
by its grilling. Its tests use hand-rolled `fetch()` stubs, so none of them caught it.

The last two `one_click_data_refresh` executions (2026-09-06) ran with `release_mode: false`, so
the path is dormant, not actively failing.

Options:

- Give `fundamentals_ingest` a reader interface instead of raw SQL (filings by CIKs and forms,
  attachments by accession, raw object by id), answered by the in-run lookup locally and by
  the Snowflake reader in `bootstrap-fundamentals`.
- Retire release-mode Branch B if the strict release Map is no longer used.
- Something else.

**Blocked by:** none — frontier.
