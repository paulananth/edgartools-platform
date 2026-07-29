# 41 — Root-cause the empty/near-empty fundamentals gold pipeline (F4/F5/F9/F11)

Type: research
Status: resolved
Blocked by:

## Question

While grilling ticket 31 (Historical financials, F4 — "likely the most broadly-needed of all
12" F1-F12 products per ticket 27's survey), live checks found this product's entire gold layer
is non-functional in prod, and it is not isolated:

| Table (product) | Rows in prod (2026-07-29, direct `SELECT COUNT(*)`) |
|---|---|
| `EDGARTOOLS_GOLD.FINANCIAL_DERIVED` (F4) | 0 |
| `EDGARTOOLS_GOLD.FINANCIAL_FACTS` (F4) | 0 |
| `EDGARTOOLS_GOLD.FINANCIAL_FACTORS` (F4) | 0 |
| `EDGARTOOLS_SOURCE.SEC_FINANCIAL_DERIVED` | 0 |
| `EDGARTOOLS_SOURCE.SEC_FINANCIAL_FACT` | 0 |
| `EDGARTOOLS_GOLD.EARNINGS_RELEASES` (F5) | 13 (essentially empty at this universe's scale) |
| `EDGARTOOLS_GOLD.ACCOUNTING_FLAGS` (F11) | 0 |
| `EDGARTOOLS_GOLD.SEC_FINANCIAL_FACT.segment` (F9) | 0 (same root table as F4) |

By contrast, `EDGARTOOLS_GOLD.EXECUTIVE_RECORDS` (F10, a sibling "dimensional" gold table per
the same PR-1/Q1-C hybrid family — see `infra/snowflake/dbt/edgartools_gold/models/sources.yml`
comments) is genuinely healthy: **13,457 rows**. So this is not a blanket failure of the whole
dimensional-gold family — something specifically about the financial-facts/earnings-release/
accounting-flags path is broken or never executed, while the executive-records path works.

**Initial investigation this session (partial, not conclusive):**

1. All three dbt models (`financial_derived.sql`, `financial_facts.sql`, `earnings_releases.sql`,
   `executive_records.sql`, `accounting_flags.sql`) exist in the repo and are well-built —
   `financial_derived.sql`'s own header describes deliberate design work (YoY growth, TTM
   metrics, peer-rank percentiles, a self-join to handle current/comparative period rows). This
   does not look like unfinished or abandoned code.
2. `TODOS.md` (search for `SEC_FINANCIAL_DERIVED`/`SEC_FINANCIAL_FACT`) documents a prior
   session that fixed multiple pipeline stages for these exact tables (Snowflake MERGE key
   gaps missing `period_end`/`period_start`, a non-deterministic `lag()` window ordering bug)
   across several dated "Stage N resolution summary" entries — but explicitly flagged as
   **not done**: "re-export Apple CIK 320193 and confirm a real QTD/YTD pair survives the
   Snowflake MERGE into `EDGARTOOLS_SOURCE.SEC_FINANCIAL_FACT` as two rows (requires live
   Snowflake creds, not available in this session)." This strongly suggests the code fixes
   landed but were never actually run against live Snowflake to validate/populate real data —
   not a design gap, a "last mile never executed" gap.
3. The ingestion command that should populate these tables is `bootstrap-fundamentals --mode
   entity-facts` (per `edgar_warehouse/cli.py`'s help text: "Modes: per-filing (8-K/DEF 14A),
   entity-facts (XBRL companyfacts), thirteenf (13F INFORMATION TABLE), company-identity"). This
   mode does **not** appear anywhere in the `daily_incremental` Step Function's definition —
   only `bootstrap-fundamentals --mode company-identity` runs there (in `Stage0CompanyIdentity`).
   Whether `entity-facts` is wired into some *other* state machine (`load_history`,
   `bootstrap_batch`, a dedicated fundamentals-only state machine) or has never been wired into
   any operational Step Function at all was not checked this session.

## What this ticket needs to answer

1. Is `bootstrap-fundamentals --mode entity-facts` (or `per-filing`, or `thirteenf` — check
   whether any of these actually feed `SEC_FINANCIAL_FACT`/`SEC_FINANCIAL_DERIVED`/
   `EARNINGS_RELEASES`/`ACCOUNTING_FLAGS`, since the CLI help text groups multiple modes
   together and it isn't yet confirmed which mode maps to which output table) wired into **any**
   Step Function state machine in this AWS account (`load_history`, `daily_incremental`,
   `bootstrap`, `bootstrap_batch`, or a dedicated one)? Check both the Terraform/deploy-script
   source (`infra/scripts/deploy-aws-application.sh` and any state-machine JSON it registers)
   and the live AWS state (`aws stepfunctions list-state-machines` +
   `describe-state-machine --query definition` for every state machine, grep for
   `bootstrap-fundamentals` and each mode flag).
2. If it is wired somewhere, has it ever actually been invoked/succeeded in prod? Check
   CloudWatch logs / Step Functions execution history for any past execution of whichever state
   machine contains it, and check ECS task history for `bootstrap-fundamentals` command
   invocations.
3. If it has never run, or run and failed: does the underlying **bronze** data (raw XBRL
   companyfacts) even exist yet for this to ingest from, or is bronze itself also missing? Check
   S3 (`s3://edgartools-prod-bronze-690839588395/...` — find the right prefix for XBRL
   companyfacts/entity-facts bronze artifacts) and/or silver (the live silver DuckDB) for
   `sec_financial_fact`/`sec_financial_derived`/`sec_earnings_release`/`sec_accounting_flag`
   row counts, to determine whether this is a bronze-fetch gap, a silver-parse gap, or purely
   the Snowflake-export "last mile" TODOS.md flagged.
4. Why does `EARNINGS_RELEASES` have exactly 13 rows (not 0, not a real-scale number) — sample
   them (CIKs, dates, `last_sync_run_id`/equivalent provenance column) to determine if this is a
   stale one-off test/dev artifact, a tiny real pilot run, or partial real production data that
   stopped partway through.
5. Report a clear root cause (bronze gap vs. silver gap vs. export-wiring gap vs. never-invoked
   command) and a recommended fix path, mirroring ticket 40's shape — this is Type: research, a
   follow-up task ticket can implement the actual fix once the cause is clear. Do **not** trigger
   any live fundamentals ingestion/export run as part of this investigation without flagging the
   scope/cost/duration first — `daily_incremental`'s first-ever prod execution is running
   concurrently this session and a large-scale fundamentals backfill could be a long, expensive
   operation that deserves its own explicit go-ahead, separate from this research ticket.

This blocks tickets 31 (F4, Historical financials), 32 (F5, Earnings 8-K GAAP snapshot), 36
(F9, Segment/product-geo revenue — reads the same empty `SEC_FINANCIAL_FACT.segment`), and
possibly 38 (F11, Accounting forensic scores, `ACCOUNTING_FLAGS` = 0 rows) — none of those can
get a real, grounded promotion checklist until the cause and fix path are known. Tickets 30, 33,
34, 35, 37, 39 are unaffected (confirmed `EXECUTIVE_RECORDS`, the F10 sibling in the same
dimensional-gold family, is healthy at 13,457 rows) and can continue independently.

## Answer

### Root cause: this is a bronze/silver execution gap, not an export-wiring bug — different shape from ticket 40

Unlike ticket 40 (`TICKER_REFERENCE`), where the underlying data was healthy and only the
Snowflake export was mis-wired, this gap goes all the way down: pulled and queried the live prod
silver DuckDB directly (`s3://edgartools-prod-warehouse-690839588395/warehouse/silver/sec/
silver.duckdb`, 994 MB).

| Silver table | Rows | Matches Snowflake gold/source? |
|---|---|---|
| `sec_financial_fact` (F4) | **0** | Yes — 0 in both `EDGARTOOLS_SOURCE.SEC_FINANCIAL_FACT` and gold `FINANCIAL_FACTS` |
| `sec_financial_derived` (F4) | **0** | Yes — 0 in both source and gold `FINANCIAL_DERIVED` |
| `sec_earnings_release` (F5) | **13** | Yes — exactly 13 in gold `EARNINGS_RELEASES` too |
| `sec_accounting_flag` (F11) | **0** | Yes — 0 in gold `ACCOUNTING_FLAGS` |
| `sec_thirteenf_holding` (F7, for comparison) | 6,799,919 | Yes — matches gold/source exactly |

**The Snowflake export pipeline is not the problem — the data was never captured at the silver
layer in the first place** (except for the 13 stray `sec_earnings_release` rows). This is a
capture/backfill gap, not a wiring gap.

### Why: `load_history` — the only state machine ever wired to run these fundamentals
modes — has never executed

Searched every Step Function state machine's live definition (`describe-state-machine`) for
`bootstrap-fundamentals`. Only two contain it at all:

- `daily_incremental`: only `--mode company-identity` (confirmed earlier this session) — never
  `entity-facts`/`per-filing`/`thirteenf`.
- `load_history`: **all four modes** — `company-identity`, `entity-facts`, `per-filing`,
  `thirteenf` (run sequentially after Branch A, per the state machine's own comment: "Branch A
  is strict; Branch B stages catch failures so the pipeline can still advance (AD-13)").

`load_history` is the **only** place in this AWS account that ever invokes
`--mode entity-facts` or `--mode per-filing`. Checked its execution history directly:
`aws stepfunctions list-executions --state-machine-arn
arn:aws:states:us-east-1:690839588395:stateMachine:edgartools-prod-load-history` returns
**an empty list — zero executions, ever.** The one pipeline capable of populating F4/F5/F9/F11
has never run in this account's history.

### Then how did F7 (13F, `sec_thirteenf_holding`) get 6.8M real rows?

Not through `load_history` either (confirmed zero executions there). Checked
`sec_thirteenf_holding`'s own `ingested_at` timestamps: **all 6,799,919 rows were ingested within
a single 4-day window, 2026-07-21 to 2026-07-24** — a concentrated bulk-load event, not gradual
organic accumulation over months of real operation. This lines up with CLAUDE.md's own
documented "INSTITUTIONAL_HOLDS / EMPLOYED_BY 5-whys" entry (dated 2026-07-26, i.e. immediately
after this window) and the "residual holds graph pipeline" prod residual note on this same map —
a deliberate, targeted manual bulk-load effort specifically to fix the `INSTITUTIONAL_HOLDS`
relationship gap, run outside `load_history` entirely (most likely via direct `bootstrap-batch`/
`bootstrap-fundamentals --mode thirteenf` ECS task invocations, the same pattern this session
used for the rollback-rehearsal proof — launching tasks directly rather than through a full
Step Functions Map).

The 13 `sec_earnings_release` rows were **also** ingested inside that identical window
(2026-07-21 to 2026-07-24, `parser_version='2'` on all 13, spanning 13 different CIKs and filing
dates from 2024-09 through 2026-03) — almost certainly incidental/test artifacts from the same
adjacent activity, not a deliberate earnings-release backfill. `sec_financial_fact`/
`sec_financial_derived`/`sec_accounting_flag` show **zero** rows even from that window — the
`entity-facts` bootstrap-fundamentals mode has, as far as any evidence in this account shows,
**never successfully produced a single row**, not even in a small test.

### Reconciliation

Three genuinely distinct situations, not one:
- **F7 (13F) is fine** — real, complete production data, just landed via a targeted manual
  effort rather than the general `load_history` pipeline. Not a gap.
- **F5 (Earnings 8-K snapshot) has a tiny, incidental trickle (13 rows)** — not zero, but not
  remotely at production scale for a ~31,000-CIK tracked universe. The `per-filing` mode clearly
  works (it produced correctly-shaped rows), it has simply never been run at scale.
- **F4 (Historical financials) and F11 (Accounting forensic scores) have never produced a single
  row anywhere** — the `entity-facts` bootstrap-fundamentals mode's actual success/failure in
  practice is unverified by any evidence available in this account; it may work correctly and
  simply never have been invoked at scale, or it may have a real bug that's never been exercised.
  This ticket did not attempt to invoke it live to distinguish those two (see below).

### Recommendation (research only — not implemented, and deliberately not attempted live here)

1. **The fix is operational, not (necessarily) a code fix**: someone needs to actually run
   `bootstrap-fundamentals --mode entity-facts` and `--mode per-filing` at real scale against the
   full tracked universe — either by finally executing `load_history` for real (which would also
   re-run Branch A / company-identity / thirteenf redundantly against an already-loaded universe),
   or by replicating the apparent 13F precedent: direct, targeted `bootstrap-batch`/
   `bootstrap-fundamentals` ECS task invocations scoped to just the `entity-facts`/`per-filing`
   modes, without re-running the rest of `load_history`.
2. **Before running either at scale, do a small-CIK smoke test first** (e.g., 1-5 CIKs, mirroring
   this session's rollback-rehearsal proof pattern) to confirm `entity-facts` mode actually
   produces correct rows — its true correctness is unverified by any live evidence in this
   account; a full-universe run without a smoke test first risks discovering a real bug only
   after a long, expensive run.
3. **This is a substantial, separate decision from this research ticket** — a full-universe
   `entity-facts`/`per-filing` backfill is a real, non-trivial operation (comparable in kind to
   the `daily_incremental` first-ever-run decision earlier this session) and deserves its own
   explicit operator go-ahead and sequencing decision, not a default "just run it" follow-up.
4. **For tickets 31/32/36/38**: none of them can write a real, checkable promotion checklist
   while the underlying data is this sparse. Once a real backfill lands (even partially), those
   tickets should re-check actual row counts/coverage before drafting numbered criteria — do not
   draft criteria against a hypothetical "once it's fixed" state the way ticket 28 did for
   `TICKER_REFERENCE` (that case had healthy underlying data; this one does not).
