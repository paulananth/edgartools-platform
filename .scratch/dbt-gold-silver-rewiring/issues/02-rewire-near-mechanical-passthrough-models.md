# 02 — Rewire Gold's Near-Mechanical Passthrough Models onto Silver

**What to build:** `financial_facts`, `institutional_holdings`,
`financial_derived`, `financial_factors`, `adv_fund_count_reconciliation`,
and `ticker_reference` read from dbt silver via `ref()` instead of the
`EDGARTOOLS_SOURCE`-mirrored tables `gold_models.py`'s Python builders
currently populate. These six are the lowest-risk batch — each is either a
pure passthrough or already has its real business logic (YoY growth,
peer-rank percentiles, roster reconciliation) living in dbt SQL layered on
top of the Python passthrough today. This batch proves the `ref()` cutover
pattern end-to-end before the harder, multi-join tables in Ticket 04 follow.

**Blocked by:** 01

**Status:** resolved — SQL rewiring, unit-test fixture updates, and a
runnable reconciliation script are all committed. Two criteria below need
someone with dbt/Snowflake prod credentials to actually execute them (same
constraint as Ticket 01 — see "Verification performed, and its limit"
below).

- [x] All 6 models source exclusively via `ref()` from dbt silver models;
      zero `source("edgartools_source", ...)` references remain for these six
      tables
- [~] The cutover validation standard (digest-based Table-Specific
      Reconciliation, per the duckdb-retirement map's resolved Ticket 07)
      passes for each table against its current `EDGARTOOLS_SOURCE`-backed
      output — compared on business-key content, not surrogate-key columns,
      per Ticket 01's key-regeneration decision. A runnable HASH_AGG()-based
      reconciliation script exists
      (`infra/snowflake/sql/validation/ticket02_gold_silver_cutover_reconciliation.sql`)
      covering all six tables, but it has not been executed against prod (no
      session credentials) — "passes" isn't true until someone runs it and
      reports six matching digests
- [~] `dbt run --full-refresh` succeeds for each model against prod — not
      run; `dbt parse`/`dbt compile` reach the live-connection step cleanly
      (see below) but the actual redeploy is unverified
- [x] The corresponding `gold_models.py` Python builders for these 6 tables
      are left in place but unreferenced by any live path (removal happens in
      Ticket 07 of this batch, once every table has cut over) — automatic
      consequence of the `source()`→`ref()` swap above: nothing in the dbt
      DAG reads `EDGARTOOLS_SOURCE` for these six tables anymore, but the
      Python builder code and its writes to `EDGARTOOLS_SOURCE` are untouched

## Answer

**The five mechanical swaps:** `financial_facts`, `institutional_holdings`,
`financial_derived`, and both `adv_fund_count_reconciliation` sources now
read via `{{ ref(...) }}` from their column-and-grain-identical dbt silver
counterparts (`sec_financial_fact`, `sec_thirteenf_holding`,
`sec_financial_derived`, `sec_adv_private_fund`, `sec_adv_firm_roster`).
Verified column-for-column against each auto-generated silver model
(`infra/scripts/generate_silver_dbt_models.py`'s output) before editing —
every column each gold model already selects by name exists in its silver
counterpart under the same name. `financial_factors` needed **zero**
changes: it has never sourced `EDGARTOOLS_SOURCE` directly, only
`ref("financial_derived")`, so it inherits the cutover transitively once
`financial_derived` itself moved.

**`ticker_reference` is the one genuinely non-mechanical case in this
"near-mechanical" batch.** Investigation found it was never a silver
passthrough at all: the Python builder
(`build_ticker_reference_table`/`gold_models.py`) projects it directly from
`seed_universe_loader`'s raw parse of SEC's `company_tickers_exchange.json`
payload (`edgar_warehouse/loaders/bronze_reference_extractors.py`),
completely bypassing DuckDB silver. There is no `sec_ticker_reference`
silver table. The closest silver equivalent is `sec_company_ticker`
(`silver_store.replace_company_tickers`), which parses the *same* SEC
payload into a durable table carrying an explicit `source_name`
discriminator per row (`'company_tickers_exchange'`, which carries
`exchange`, vs. `'company_tickers'`, ticker-source data used elsewhere only
for tracking-universe eligibility). Filtering
`ref("sec_company_ticker")` to `source_name = 'company_tickers_exchange'`
reproduces `TICKER_REFERENCE`'s exact grain and column set — confirmed via
the silver model's own `qualify row_number() over (partition by cik,
ticker, source_name order by parse_sequence desc) = 1`, which already
guarantees one row per `(cik, ticker, source_name)`. This is a judgment
call (two independent parsers of the same upstream file, not one
mechanical passthrough), documented in the model's own header comment and
flagged again in the reconciliation script as the digest most likely to
show an expected, non-defect mismatch.

**Reconciliation script:** `infra/snowflake/sql/validation/ticket02_gold_silver_cutover_reconciliation.sql`,
modeled on the existing `infra/snowflake/sql/validation/fundamental_factor_coverage.sql`
convention (plain reporting SQL, run manually, not a deployment gate).
Uses Snowflake's `HASH_AGG()` (order-independent aggregate hash) per table,
comparing `EDGARTOOLS_SOURCE` (old path) against `EDGARTOOLS_SILVER` (new
path) on business-key + content columns only — run-metadata columns
(`ingested_at`, `last_sync_run_id`, `source_sha256`, `source_dataset_period`)
are deliberately excluded from every digest since the two paths are
independent writers and their sync bookkeeping legitimately differs even
when business content matches; including them would produce false-positive
mismatches. Row counts are reported alongside each digest pair for a
cheaper first signal before trusting the hash comparison.

**A real regression caught before commit, not by a reviewer:** three unit
test YAML files mock specific `given.input` sources
(`_financial_derived_unit_tests.yml`, `_adv_fund_count_reconciliation_unit_tests.yml`)
that still pointed at `source('edgartools_source', ...)` after the model
SQL swapped to `ref(...)`. `dbt parse` does **not** catch this mismatch
(confirmed empirically — parse succeeds either way; unit-test `given`
resolution is validated at `dbt test` time, not parse time), so this would
have silently left `dbt test` either erroring or, worse, running against
whatever it fell back to instead of the intended mock. Fixed all 21
occurrences across both files to `ref('sec_financial_derived')` /
`ref('sec_adv_private_fund')` / `ref('sec_adv_firm_roster')`, matching each
model's new source exactly. `_financial_factors_unit_tests.yml` needed no
change — it already mocks `ref('financial_derived')`, which is unaffected
by financial_derived's own upstream source.

**Verification performed, and its limit:** `dbt parse --no-partial-parse`
succeeds cleanly against the full project after every edit (54 models, 57
sources, 553 macros, 25 unit tests). Empirically confirmed `dbt parse`
genuinely validates every `ref()` target (deliberately introduced a typo in
`ticker_reference.sql`'s `ref()` call, reproduced the exact "depends on a
node ... which was not found" failure, then reverted) — so the six models'
`ref()` edges are proven to resolve against real silver nodes, not just
syntactically well-formed. `dbt compile` reaches the live-connection step
(fails only on placeholder credentials) but — unlike Ticket 01's
finding — does **not** write fresh compiled SQL before erroring in this dbt
version, so compile is not independent evidence beyond what parse already
proved; this correction is noted here rather than repeating Ticket 01's
over-broad claim. **Not run:** the reconciliation script (no live
Snowflake access this session) and `dbt run --select <model>
--full-refresh` for any of the six models (per this repo's own documented
gotcha, a config-unchanged `dbt run` is a silent no-op on a dynamic table,
so `--full-refresh` is required and has not happened). Whoever has dbt
prod credentials should run the reconciliation script first, then `dbt
test --select financial_derived adv_fund_count_reconciliation` (the two
models with edited unit-test fixtures) to confirm the fixture fixes are
actually correct, then `dbt run --full-refresh` for all six models.
